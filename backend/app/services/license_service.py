import secrets
import string
import hashlib
import hmac as _hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..config import settings
from ..models import License, LicenseKey, User, LicenseKeyStatus, PlanType
from ..schemas import LicenseData

_SIG_KEY = "_sig"
_SIG_VERSION_KEY = "_sig_ver"

_ecdsa_private_key = None
_hmac_signing_key = None


def _get_ecdsa_private_key():
    global _ecdsa_private_key
    if _ecdsa_private_key is not None:
        return _ecdsa_private_key
    key_path = getattr(settings, "ECDSA_PRIVATE_KEY_PATH", "") or ""
    if not key_path:
        key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_sign_private.pem")
    if not os.path.isabs(key_path):
        key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", key_path)
    if os.path.exists(key_path):
        try:
            from cryptography.hazmat.primitives import serialization
            with open(key_path, "rb") as f:
                _ecdsa_private_key = serialization.load_pem_private_key(f.read(), password=None)
            return _ecdsa_private_key
        except Exception:
            pass
    return None


def _get_hmac_signing_key() -> bytes:
    global _hmac_signing_key
    if _hmac_signing_key is not None:
        return _hmac_signing_key
    if settings.HMAC_SIGN_KEY and settings.HMAC_SIGN_KEY.strip():
        _hmac_signing_key = settings.HMAC_SIGN_KEY.encode("utf-8")
        return _hmac_signing_key
    key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_verify_key")
    try:
        with open(key_path, "rb") as f:
            key = f.read().strip()
            if key:
                _hmac_signing_key = key
                return _hmac_signing_key
    except FileNotFoundError:
        pass
    return None


def _make_payload(data: dict) -> bytes:
    check = {k: v for k, v in data.items() if k != _SIG_KEY and k != _SIG_VERSION_KEY and v is not None}
    return json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign_license_data(data: dict) -> tuple:
    payload = _make_payload(data)
    ecdsa_key = _get_ecdsa_private_key()
    if ecdsa_key is not None:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        signature = ecdsa_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature.hex(), 2
    hmac_key = _get_hmac_signing_key()
    if hmac_key is not None:
        sig = _hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
        return sig, 1
    raise RuntimeError("No signing key configured. Set ECDSA_PRIVATE_KEY_PATH or HMAC_SIGN_KEY")


def verify_signature(data: dict, signature: str) -> bool:
    try:
        sig_ver = data.get(_SIG_VERSION_KEY, 1)
        payload = _make_payload(data)
        if sig_ver == 2:
            pubkey_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "keys", ".license_verify_pubkey.pem")
            if os.path.exists(pubkey_path):
                from cryptography.hazmat.primitives import serialization
                from cryptography.hazmat.primitives.asymmetric import ec
                from cryptography.hazmat.primitives import hashes
                with open(pubkey_path, "rb") as f:
                    public_key = serialization.load_pem_public_key(f.read())
                public_key.verify(bytes.fromhex(signature), payload, ec.ECDSA(hashes.SHA256()))
                return True
        elif sig_ver == 1:
            hmac_key = _get_hmac_signing_key()
            if hmac_key is not None:
                expected = _hmac.new(hmac_key, payload, hashlib.sha256).hexdigest()
                return _hmac.compare_digest(expected, signature)
    except Exception:
        pass
    return False


def is_license_expired(license_obj: License) -> bool:
    if license_obj.expiry_date is not None:
        now = datetime.now(timezone.utc)
        if license_obj.expiry_date.tzinfo is None:
            from datetime import timezone as _tz
            license_obj.expiry_date = license_obj.expiry_date.replace(tzinfo=_tz.utc)
        if license_obj.expiry_date < now:
            return True
        return False
    if not license_obj.is_valid:
        return True
    return False


def build_license_response(license_obj: License, username: str) -> LicenseData:
    return encode_license_data(license_obj, username)


def generate_license_key(length: int = 32) -> str:
    alphabet = string.ascii_uppercase + string.digits
    key = "-".join(
        "".join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(length // 4)
    )
    return key


async def create_trial_license(db: AsyncSession, user_id: int) -> License:
    trial_days = settings.TRIAL_DAYS
    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=trial_days)

    license_obj = License(
        user_id=user_id,
        license_type="trial",
        is_valid=True,
        trial_start=trial_start,
        trial_end=trial_end,
        expiry_date=trial_end,
    )

    db.add(license_obj)
    await db.flush()

    return license_obj


async def activate_license(db: AsyncSession, user_id: int, license_key: str) -> Optional[License]:
    from ..database import engine

    use_for_update = not str(engine.url).startswith("sqlite")

    q = select(LicenseKey).where(LicenseKey.license_key == license_key)
    if use_for_update:
        q = q.with_for_update()
    key_result = await db.execute(q)
    license_key_obj = key_result.scalar_one_or_none()

    if not license_key_obj:
        return None

    if license_key_obj.status == LicenseKeyStatus.REVOKED:
        return None

    if license_key_obj.status == LicenseKeyStatus.ACTIVATED:
        return None

    license_key_obj.status = LicenseKeyStatus.ACTIVATED
    license_key_obj.activated_at = datetime.now(timezone.utc)
    license_key_obj.activated_by = user_id

    if license_key_obj.plan_type == PlanType.LIFETIME:
        expiry_date = None
        license_type = "pro"
    elif license_key_obj.plan_type == PlanType.TRIAL_15D:
        expiry_delta = timedelta(days=15)
        license_type = "trial"
    else:
        if license_key_obj.plan_type == PlanType.MONTHLY:
            expiry_delta = timedelta(days=30)
        elif license_key_obj.plan_type == PlanType.QUARTERLY:
            expiry_delta = timedelta(days=90)
        elif license_key_obj.plan_type == PlanType.YEARLY:
            expiry_delta = timedelta(days=365)
        else:
            expiry_delta = timedelta(days=30)

        expiry_date = datetime.now(timezone.utc) + expiry_delta
        license_type = "pro"

    existing_result = await db.execute(
        select(License).where(License.user_id == user_id)
    )
    existing_license = existing_result.scalar_one_or_none()

    if existing_license:
        if license_key_obj.plan_type == PlanType.LIFETIME:
            existing_license.license_type = "pro"
            existing_license.license_key = license_key
            existing_license.is_valid = True
            existing_license.expiry_date = None
            await db.flush()
            await db.commit()
            return existing_license
        elif license_key_obj.plan_type == PlanType.TRIAL_15D:
            if existing_license.license_type in ("pro",) and not existing_license.expiry_date:
                await db.flush()
                await db.commit()
                return existing_license
            if existing_license.expiry_date:
                current_expiry = existing_license.expiry_date
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                remaining = max(current_expiry - now, timedelta(0))
                expiry_date = now + remaining + expiry_delta
            else:
                expiry_date = datetime.now(timezone.utc) + expiry_delta
            existing_license.trial_end = expiry_date
            if not existing_license.trial_start:
                existing_license.trial_start = datetime.now(timezone.utc)
        else:
            if existing_license.expiry_date:
                current_expiry = existing_license.expiry_date
                if current_expiry.tzinfo is None:
                    current_expiry = current_expiry.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                remaining = max(current_expiry - now, timedelta(0))
                expiry_date = now + remaining + expiry_delta
            else:
                expiry_date = datetime.now(timezone.utc) + expiry_delta

        if license_key_obj.plan_type != PlanType.TRIAL_15D or existing_license.license_type not in ("pro",):
            existing_license.license_type = license_type
        existing_license.license_key = license_key
        existing_license.is_valid = True
        existing_license.expiry_date = expiry_date
        if license_key_obj.plan_type != PlanType.TRIAL_15D:
            existing_license.trial_start = None
            existing_license.trial_end = None
        await db.flush()
        await db.commit()
        return existing_license
    else:
        if license_key_obj.plan_type == PlanType.TRIAL_15D:
            expiry_date = datetime.now(timezone.utc) + expiry_delta

        license_obj = License(
            user_id=user_id,
            license_type=license_type,
            license_key=license_key,
            is_valid=True,
            expiry_date=expiry_date,
            trial_start=datetime.now(timezone.utc) if license_type == "trial" else None,
            trial_end=expiry_date if license_type == "trial" else None,
        )
        db.add(license_obj)
        await db.flush()
        await db.commit()
        return license_obj


async def cleanup_expired_license_keys(db: AsyncSession) -> int:
    cutoff_time = datetime.now(timezone.utc) - timedelta(days=15)

    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
        .where(LicenseKey.status == LicenseKeyStatus.UNUSED)
        .where(LicenseKey.created_at < cutoff_time)
    )
    expired_keys = result.scalars().all()

    count = 0
    for key in expired_keys:
        key.status = LicenseKeyStatus.REVOKED
        count += 1

    if count > 0:
        await db.flush()

    return count


async def get_trial_key_status(db: AsyncSession, license_key: str) -> Optional[dict]:
    result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.license_key == license_key)
        .where(LicenseKey.plan_type == PlanType.TRIAL_15D)
    )
    key = result.scalar_one_or_none()

    if not key:
        return None

    now = datetime.now(timezone.utc)
    created_at = key.created_at.replace(tzinfo=timezone.utc)

    age_days = (now - created_at).days
    days_remaining = max(0, 15 - age_days)
    is_expired = age_days >= 15

    return {
        "license_key": key.license_key,
        "status": key.status.value,
        "is_expired": is_expired,
        "days_remaining": days_remaining,
        "created_at": key.created_at.isoformat(),
        "activated_at": key.activated_at.isoformat() if key.activated_at else None,
        "activated_by": key.activated_by,
    }


def encode_license_data(license: License, username: str) -> LicenseData:
    days_left = -1
    if license.expiry_date:
        now = datetime.now(timezone.utc)
        exp = license.expiry_date
        if exp.tzinfo is None:
            from datetime import timezone as _tz
            exp = exp.replace(tzinfo=_tz.utc)
        days_left = max(0, (exp - now).days)

    expiry_str = license.expiry_date.strftime("%Y-%m-%dT%H:%M:%SZ") if license.expiry_date else None
    trial_start_str = license.trial_start.strftime("%Y-%m-%dT%H:%M:%SZ") if license.trial_start else None
    trial_end_str = license.trial_end.strftime("%Y-%m-%dT%H:%M:%SZ") if license.trial_end else None

    data_without_sig = {
        "username": username,
        "license_type": license.license_type if isinstance(license.license_type, str) else license.license_type.value,
        "is_valid": license.is_valid,
        "days_left": days_left,
        "trial_start": trial_start_str,
        "trial_end": trial_end_str,
        "expiry_date": expiry_str,
        "license_key": license.license_key,
    }

    sig, sig_ver = sign_license_data(data_without_sig)

    return LicenseData(
        sig=sig,
        sig_ver=sig_ver,
        username=username,
        license_type=license.license_type if isinstance(license.license_type, str) else license.license_type.value,
        is_valid=license.is_valid,
        days_left=days_left,
        trial_start=trial_start_str,
        trial_end=trial_end_str,
        expiry_date=expiry_str,
        license_key=license.license_key,
    )
