import asyncio
import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://videogen:videogen@localhost:5432/videogen_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-unit-tests-only-64chars")
os.environ.setdefault("HMAC_SIGN_KEY", "test-hmac-sign-key-for-unit-tests-only")
os.environ.setdefault("VIDEOGEN_ENV", "test")

from app.database import Base, engine, async_session
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.services.license_service import (
    sign_license_data, verify_signature,
    create_trial_license, generate_license_key, is_license_expired,
)
from app.models import User, License, LicenseType


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def sample_user():
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("TestPass123!"),
        is_active=True,
        is_admin=False,
    )


@pytest.fixture
def sample_license():
    return License(
        id=1,
        user_id=1,
        license_type=LicenseType.TRIAL,
        is_valid=True,
    )


class TestAuth:
    def test_hash_password(self):
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_verify_password_wrong(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_create_access_token(self):
        token = create_access_token(data={"user_id": 1, "username": "test"})
        assert isinstance(token, str)
        assert len(token) > 20

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self, db, sample_user):
        db.add(sample_user)
        await db.commit()
        token = create_access_token(data={"user_id": sample_user.id, "username": sample_user.username})
        user = await get_current_user(token=token, db=db)
        assert user.username == "testuser"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, db):
        with pytest.raises(Exception):
            await get_current_user(token="invalidtoken", db=db)


class TestLicenseService:
    def test_sign_and_verify_signature(self):
        data = {"username": "test", "license_type": "trial", "is_valid": True, "days_left": 7}
        signed = sign_license_data(data)
        assert "_sig" in signed
        assert verify_signature(signed) is True

    def test_verify_signature_tampered(self):
        data = {"username": "test", "license_type": "trial", "is_valid": True, "days_left": 7}
        signed = sign_license_data(data)
        signed["days_left"] = 999
        assert verify_signature(signed) is False

    def test_verify_signature_missing_sig(self):
        data = {"username": "test", "license_type": "trial"}
        assert verify_signature(data) is False

    def test_create_trial_license(self):
        license_obj = create_trial_license(user_id=1)
        assert license_obj.user_id == 1
        assert license_obj.license_type == LicenseType.TRIAL
        assert license_obj.is_valid is True
        assert license_obj.trial_start is not None
        assert license_obj.trial_end is not None

    def test_generate_license_key(self):
        key = generate_license_key()
        assert key.startswith("VG-")
        parts = key.split("-")
        assert len(parts) == 5

    def test_generate_license_key_unique(self):
        keys = {generate_license_key() for _ in range(100)}
        assert len(keys) == 100

    def test_is_license_expired_valid_trial(self):
        from datetime import datetime, timezone, timedelta
        license_obj = License(
            user_id=1,
            license_type=LicenseType.TRIAL,
            is_valid=True,
            trial_end=datetime.now(timezone.utc) + timedelta(days=5),
        )
        assert is_license_expired(license_obj) is False

    def test_is_license_expired_expired_trial(self):
        from datetime import datetime, timezone, timedelta
        license_obj = License(
            user_id=1,
            license_type=LicenseType.TRIAL,
            is_valid=True,
            trial_end=datetime.now(timezone.utc) - timedelta(days=5),
        )
        assert is_license_expired(license_obj) is True


class TestSchemas:
    def test_user_register_validation(self):
        from app.schemas import UserRegister
        user = UserRegister(username="testuser", email="test@example.com", password="TestPass123!")
        assert user.username == "testuser"
        assert user.email == "test@example.com"

    def test_user_register_short_password(self):
        from pydantic import ValidationError
        from app.schemas import UserRegister
        with pytest.raises(ValidationError):
            UserRegister(username="testuser", email="test@example.com", password="123")

    def test_license_activate_schema(self):
        from app.schemas import LicenseActivate
        data = LicenseActivate(license_key="VG-ABCD-EFGH-IJKL-MNOP")
        assert data.license_key == "VG-ABCD-EFGH-IJKL-MNOP"

    def test_heartbeat_request_schema(self):
        from app.schemas import HeartbeatRequest
        data = HeartbeatRequest(fingerprint="abc123", app_version="2.0.0")
        assert data.fingerprint == "abc123"
        assert data.app_version == "2.0.0"


class TestPaymentService:
    def test_generate_order_no(self):
        from app.services.payment_service import generate_order_no
        order_no = generate_order_no()
        assert order_no.startswith("VG")
        assert len(order_no) > 10

    def test_generate_order_no_unique(self):
        from app.services.payment_service import generate_order_no
        orders = {generate_order_no() for _ in range(100)}
        assert len(orders) == 100

    @pytest.mark.asyncio
    async def test_verify_alipay_notification_no_instance(self):
        from app.services.payment_service import verify_alipay_notification
        result = await verify_alipay_notification({"sign": "fake", "trade_status": "TRADE_SUCCESS"})
        assert result is False

    @pytest.mark.asyncio
    async def test_verify_wechat_notification_no_key(self):
        from app.services.payment_service import verify_wechat_notification
        result = await verify_wechat_notification({}, b"<xml></xml>")
        assert result is False
