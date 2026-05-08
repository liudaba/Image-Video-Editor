from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..database import get_db
from ..models import LicenseKey, License, User, LicenseKeyStatus, PlanType
from ..auth import require_admin, get_current_user
from ..services.license_service import generate_license_key, encode_license_data
from ..schemas import LicenseStatusResponse

router = APIRouter(prefix="/license", tags=["license"])


@router.post("/generate-key", summary="生成许可证密钥（仅管理员）")
async def generate_key(
    plan_type: PlanType,
    quantity: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    if quantity <= 0 or quantity > 100:
        raise HTTPException(status_code=400, detail="数量必须在1-100之间")

    keys = []
    for _ in range(quantity):
        key = generate_license_key()
        license_key = LicenseKey(
            license_key=key,
            plan_type=plan_type,
            status=LicenseKeyStatus.UNUSED
        )
        db.add(license_key)
        keys.append(key)

    await db.flush()
    await db.commit()

    return {"keys": keys}


@router.get("/status", response_model=LicenseStatusResponse, summary="获取许可证状态")
async def get_license_status(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    result = await db.execute(
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        return LicenseStatusResponse(license=None)

    license_data = encode_license_data(license_obj, current_user.username)
    return LicenseStatusResponse(license=license_data)


@router.get("/keys", summary="获取许可证密钥列表（仅管理员）")
async def list_license_keys(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    
    result = await db.execute(
        select(LicenseKey)
        .offset(skip)
        .limit(limit)
        .order_by(LicenseKey.created_at.desc())
    )
    keys = result.scalars().all()

    return {
        "keys": [
            {
                "key": key.license_key,
                "plan_type": key.plan_type,
                "status": key.status,
                "activated_by": key.activated_by,
                "activated_at": key.activated_at,
                "created_at": key.created_at
            }
            for key in keys
        ]
    }
