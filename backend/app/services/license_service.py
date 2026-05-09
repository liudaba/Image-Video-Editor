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


def _get_signing_key() -> bytes:
    key_path = os.path.join(os.path.dirname(__file__), "..", "keys", ".license_verify_key")
    try:
        with open(key_path, "rb") as f:
            return f.read().strip()
    except FileNotFoundError:
        return settings.HMAC_SIGN_KEY.encode("utf-8")


def sign_license_data(data: dict) -> str:
    check = {k: v for k, v in data.items() if k != _SIG_KEY and v is not None}
    payload = json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    signing_key = _get_signing_key()
    return _hmac.new(signing_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(data: dict, signature: str) -> bool:
    expected = sign_license_data(data)
    return _hmac.compare_digest(expected, signature)


def is_license_expired(license_obj: License) -> bool:
    if not license_obj.is_valid:
        return True
    if license_obj.expiry_date is None:
        return False
    now = datetime.now(timezone.utc)
    if license_obj.expiry_date.tzinfo is None:
        from datetime import timezone as _tz
        license_obj.expiry_date = license_obj.expiry_date.replace(tzinfo=_tz.utc)
    return license_obj.expiry_date < now


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
    key_result = await db.execute(
        select(LicenseKey)
        .where(LicenseKey.license_key == license_key)
        .with_for_update()
    )
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
        expiry_date = datetime.now(timezone.utc) + expiry_delta
        license_type = "trial"
    else:
        if license_key_obj.plan_type == PlanType.MONTHLY:
            expiry_delta = timedelta(days=30)
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
        existing_license.license_type = license_type
        existing_license.license_key = license_key
        existing_license.is_valid = True
        existing_license.expiry_date = expiry_date
        if license_type == "trial" and not existing_license.trial_start:
            existing_license.trial_start = datetime.now(timezone.utc)
            existing_license.trial_end = expiry_date
        await db.flush()
        await db.commit()
        return existing_license
    else:
        license_obj = License(
            user_id=user_id,
            license_type=license_type,
            license_key=license_key,
            is_valid=True,
            expiry_date=expiry_date,
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

    sig = sign_license_data(data_without_sig)

    return LicenseData(
        sig=sig,
        username=username,
        license_type=license.license_type if isinstance(license.license_type, str) else license.license_type.value,
        is_valid=license.is_valid,
        days_left=days_left,
        trial_start=trial_start_str,
        trial_end=trial_end_str,
        expiry_date=expiry_str,
        license_key=license.license_key,
    )
