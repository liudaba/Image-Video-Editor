from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, License, LicenseKey, LicenseKeyStatus, LicenseType
from app.schemas import LicenseActivate, ActivateResponse
from app.auth import get_current_user
from app.services.license_service import (
    build_license_response,
    is_license_expired,
    PLAN_PRICING,
)

router = APIRouter(prefix="/api/license", tags=["授权"])


@router.post("/activate", response_model=ActivateResponse)
async def activate_license(
    body: LicenseActivate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(License).where(License.user_id == user.id))
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到授权记录")

    key_result = await db.execute(
        select(LicenseKey).where(
            LicenseKey.license_key == body.license_key,
            LicenseKey.status == LicenseKeyStatus.UNUSED,
        )
    )
    license_key_obj = key_result.scalar_one_or_none()

    if not license_key_obj:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="许可证密钥无效或已被使用",
        )

    now = datetime.now(timezone.utc)
    plan = PLAN_PRICING.get(license_key_obj.plan_type.value)
    days = plan["days"] if plan else 365

    license_obj.license_type = LicenseType.PRO
    license_obj.license_key = body.license_key
    license_obj.is_valid = True
    if license_obj.expiry_date and _ensure_aware(license_obj.expiry_date) > now:
        license_obj.expiry_date = _ensure_aware(license_obj.expiry_date) + timedelta(days=days)
    else:
        license_obj.expiry_date = now + timedelta(days=days)

    license_key_obj.status = LicenseKeyStatus.ACTIVATED
    license_key_obj.activated_by = user.id
    license_key_obj.activated_at = now

    await db.commit()
    await db.refresh(license_obj)

    license_data = build_license_response(license_obj, user.username)
    return ActivateResponse(license=license_data)


def _ensure_aware(dt):
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
