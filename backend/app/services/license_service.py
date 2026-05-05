import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.models import License, LicenseType
from app.schemas import LicenseData


def _compute_signature(data: Dict[str, Any]) -> str:
    sign_data = {k: v for k, v in data.items() if k != "_sig" and v is not None}
    sorted_json = json.dumps(sign_data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hmac.new(
        settings.HMAC_SIGN_KEY.encode("utf-8"),
        sorted_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_license_data(data: Dict[str, Any]) -> Dict[str, Any]:
    data["_sig"] = _compute_signature(data)
    return data


def verify_signature(data: Dict[str, Any]) -> bool:
    if "_sig" not in data:
        return False
    expected = _compute_signature(data)
    return hmac.compare_digest(expected, data["_sig"])


def _ensure_aware(dt):
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_license_response(license_obj: License, username: str) -> LicenseData:
    now = datetime.now(timezone.utc)
    days_left = 0

    if license_obj.license_type == LicenseType.TRIAL:
        trial_end = _ensure_aware(license_obj.trial_end)
        if trial_end:
            remaining = trial_end - now
            days_left = max(0, remaining.days)
    elif license_obj.license_type == LicenseType.PRO:
        expiry_date = _ensure_aware(license_obj.expiry_date)
        if expiry_date:
            remaining = expiry_date - now
            days_left = max(0, remaining.days)

    raw_data = {
        "username": username,
        "license_type": license_obj.license_type.value,
        "is_valid": license_obj.is_valid,
        "days_left": days_left,
    }

    if license_obj.trial_start:
        raw_data["trial_start"] = license_obj.trial_start.isoformat()
    if license_obj.trial_end:
        raw_data["trial_end"] = license_obj.trial_end.isoformat()
    if license_obj.expiry_date:
        raw_data["expiry_date"] = license_obj.expiry_date.isoformat()
    if license_obj.license_key:
        raw_data["license_key"] = license_obj.license_key

    signed = sign_license_data(raw_data)

    return LicenseData(
        _sig=signed.get("_sig"),
        username=signed["username"],
        license_type=signed["license_type"],
        is_valid=signed["is_valid"],
        days_left=signed["days_left"],
        trial_start=signed.get("trial_start"),
        trial_end=signed.get("trial_end"),
        expiry_date=signed.get("expiry_date"),
        license_key=signed.get("license_key"),
    )


def create_trial_license(user_id: int) -> License:
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=settings.TRIAL_DAYS)
    return License(
        user_id=user_id,
        license_type=LicenseType.TRIAL,
        is_valid=True,
        trial_start=now,
        trial_end=trial_end,
    )


def generate_license_key() -> str:
    import secrets
    import string
    chars = string.ascii_uppercase + string.digits
    parts = ["".join(secrets.choice(chars) for _ in range(4)) for _ in range(4)]
    return f"VG-{'-'.join(parts)}"


def is_license_expired(license_obj: License) -> bool:
    now = datetime.now(timezone.utc)
    if license_obj.license_type == LicenseType.TRIAL:
        trial_end = _ensure_aware(license_obj.trial_end)
        if trial_end:
            grace_end = trial_end + timedelta(hours=settings.GRACE_HOURS)
            return now > grace_end
        return True
    elif license_obj.license_type == LicenseType.PRO:
        expiry_date = _ensure_aware(license_obj.expiry_date)
        if expiry_date:
            return now > expiry_date
        return True
    return True


PLAN_PRICING = {
    "monthly": {"price": 29.9, "days": 30},
    "yearly": {"price": 299.0, "days": 365},
    "lifetime": {"price": 999.0, "days": 36500},
}


async def extend_license(db, user_id: int, days: int) -> License:
    from sqlalchemy import select
    from app.database import engine
    q = select(License).where(License.user_id == user_id)
    if not str(engine.url).startswith("sqlite"):
        q = q.with_for_update()
    result = await db.execute(q)
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        return None

    now = datetime.now(timezone.utc)
    license_obj.license_type = LicenseType.PRO
    license_obj.is_valid = True

    expiry_date = _ensure_aware(license_obj.expiry_date)
    if expiry_date and expiry_date > now:
        license_obj.expiry_date = expiry_date + timedelta(days=days)
    else:
        license_obj.expiry_date = now + timedelta(days=days)

    if not license_obj.license_key:
        license_obj.license_key = generate_license_key()

    await db.flush()
    await db.refresh(license_obj)
    return license_obj
