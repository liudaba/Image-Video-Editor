import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, License, HeartbeatLog
from ..auth import get_current_user
from ..schemas import HeartbeatRequest, HeartbeatResponse, LicenseStatusResponse
from ..services.license_service import encode_license_data

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/heartbeat", response_model=HeartbeatResponse, summary="心跳检测")
async def heartbeat(
    req: HeartbeatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    from ..services.heartbeat_service import check_and_bind_machine
    from ..main import _get_real_ip

    client_ip = _get_real_ip(request)

    license_result = await db.execute(
        select(License).filter(License.user_id == current_user.id).with_for_update()
    )
    license_obj = license_result.scalar_one_or_none()

    if not license_obj:
        return HeartbeatResponse(is_valid=False, reason="未找到许可证", timestamp=time.time())

    is_valid = license_obj.is_valid
    reason = None
    if not current_user.is_active:
        is_valid = False
        reason = "账户已被禁用"
        license_obj.is_valid = False
    if license_obj.expiry_date:
        expiry = license_obj.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if expiry < now:
            is_valid = False
            reason = reason or "许可证已过期"
            license_obj.is_valid = False

    if is_valid and req.fingerprint:
        can_bind = await check_and_bind_machine(db, current_user.id, req.fingerprint)
        if not can_bind:
            is_valid = False
            reason = "设备绑定数量已达上限(最多3台)"
            # 设备绑定限制是运行时限制，不修改数据库is_valid
            # 用户在其他设备解绑后，此设备应能正常使用

    # 只有许可证有效时才更新心跳字段，避免无效许可证显示"在线"
    if is_valid:
        heartbeat_log = HeartbeatLog(
            user_id=current_user.id,
            fingerprint=req.fingerprint,
            app_version=req.app_version,
            license_type=license_obj.license_type.value,
            ip_address=client_ip
        )
        db.add(heartbeat_log)

        license_obj.last_heartbeat = datetime.now(timezone.utc)
        if req.fingerprint:
            license_obj.heartbeat_fingerprint = req.fingerprint
            # 首次心跳时记录machine_fingerprint
            if not license_obj.machine_fingerprint:
                license_obj.machine_fingerprint = req.fingerprint
    else:
        # 即使无效也记录心跳日志（用于审计），但不更新last_heartbeat
        heartbeat_log = HeartbeatLog(
            user_id=current_user.id,
            fingerprint=req.fingerprint,
            app_version=req.app_version,
            license_type=license_obj.license_type.value,
            ip_address=client_ip
        )
        db.add(heartbeat_log)

    await db.flush()
    await db.commit()

    # 生成签名数据：设备绑定限制是运行时限制，不修改数据库is_valid
    # 使用副本签名，避免修改ORM对象导致意外持久化
    if not is_valid and license_obj.is_valid:
        # 设备绑定超限等运行时原因：签名标记为无效，但不修改数据库
        import copy
        sign_license = copy.copy(license_obj)
        # 使SQLAlchemy不再追踪此对象，避免影响session
        from sqlalchemy import inspect as sa_inspect
        sa_inspect(sign_license).detach()
        sign_license.is_valid = False
        license_data = encode_license_data(sign_license, current_user.username)
    else:
        license_data = encode_license_data(license_obj, current_user.username)

    return HeartbeatResponse(is_valid=is_valid, license=license_data, reason=reason, timestamp=time.time())


@router.get("/license_status", response_model=LicenseStatusResponse, summary="获取许可证状态")
async def get_license_status(
    fingerprint: str = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    result = await db.execute(
        select(License).filter(License.user_id == current_user.id).with_for_update()
    )
    license_obj = result.scalar_one_or_none()

    if not license_obj:
        return LicenseStatusResponse(license=None)

    from ..services.license_service import is_license_expired
    # 如果许可证已过期但is_valid仍为True，同步更新数据库
    reason = None
    if license_obj.is_valid and is_license_expired(license_obj):
        license_obj.is_valid = False
        reason = "许可证已过期"
        await db.flush()
        await db.commit()
    # 如果用户被禁用，许可证也应无效
    if license_obj.is_valid and not current_user.is_active:
        license_obj.is_valid = False
        reason = "账户已被禁用"
        await db.flush()
        await db.commit()
    # 如果提供了fingerprint，检查设备绑定限制
    if license_obj.is_valid and fingerprint:
        from ..services.heartbeat_service import check_and_bind_machine
        can_bind = await check_and_bind_machine(db, current_user.id, fingerprint)
        if not can_bind:
            reason = "设备绑定数量已达上限(最多3台)"
    # 如果is_valid=False，判断具体原因
    if not license_obj.is_valid and not reason:
        if not current_user.is_active:
            reason = "账户已被禁用"
        else:
            reason = "许可证已失效"

    # 生成签名数据：设备绑定限制是运行时限制，不修改数据库is_valid
    # 使用副本签名，避免修改ORM对象导致意外持久化
    if reason and license_obj.is_valid:
        import copy
        sign_license = copy.copy(license_obj)
        from sqlalchemy import inspect as sa_inspect
        sa_inspect(sign_license).detach()
        sign_license.is_valid = False
        license_data = encode_license_data(sign_license, current_user.username)
    else:
        license_data = encode_license_data(license_obj, current_user.username)

    return LicenseStatusResponse(license=license_data, reason=reason)


@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at
    }



