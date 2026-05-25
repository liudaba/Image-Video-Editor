from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import LicenseKey, License, User, LicenseKeyStatus, PlanType
from ..auth import require_admin, get_current_user
from ..services.license_service import generate_license_key, encode_license_data, activate_license
from ..schemas import LicenseActivate, ActivateResponse

router = APIRouter(prefix="/api/license", tags=["license"])


@router.post("/activate", response_model=ActivateResponse, summary="激活许可证")
async def activate_license_endpoint(
    license_data: LicenseActivate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    # activate_license内部会加锁，此处不再重复加锁，避免死锁
    key_result = await db.execute(
        select(LicenseKey).where(LicenseKey.license_key == license_data.license_key)
    )
    key_obj = key_result.scalar_one_or_none()
    if not key_obj:
        raise HTTPException(status_code=400, detail="密钥不存在，请检查输入")
    if key_obj.status == LicenseKeyStatus.REVOKED:
        raise HTTPException(status_code=400, detail="密钥已被撤销，请联系客服")
    if key_obj.status == LicenseKeyStatus.ACTIVATED:
        raise HTTPException(status_code=400, detail="密钥已被使用，每个密钥只能激活一次")

    activated = await activate_license(db, current_user.id, license_data.license_key)
    if activated == "already_pro":
        raise HTTPException(status_code=400, detail="您已是专业版会员，无需激活试用码")
    if activated == "already_lifetime":
        raise HTTPException(status_code=400, detail="您已是终身会员，无需再激活其他密钥")
    if activated == "user_disabled":
        raise HTTPException(status_code=403, detail="账户已被禁用，无法激活密钥")
    if not activated:
        raise HTTPException(status_code=400, detail="许可证激活失败，请检查密钥是否正确")

    await db.commit()

    license_result = await db.execute(
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = license_result.scalar_one_or_none()

    license_resp_data = None
    if license_obj:
        license_resp_data = encode_license_data(license_obj, current_user.username)

    return ActivateResponse(license=license_resp_data)


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
                "plan_type": key.plan_type.value if hasattr(key.plan_type, 'value') else key.plan_type,
                "status": key.status.value if hasattr(key.status, 'value') else key.status,
                "activated_by": key.activated_by,
                "activated_at": key.activated_at,
                "created_at": key.created_at
            }
            for key in keys
        ]
    }
