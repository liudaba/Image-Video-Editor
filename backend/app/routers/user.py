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

    # 先无锁读取License状态，减少锁竞争
    license_result = await db.execute(
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = license_result.scalar_one_or_none()

    if not license_obj:
        return HeartbeatResponse(is_valid=False, reason="未找到许可证", timestamp=time.time())

    is_valid = license_obj.is_valid
    reason = None
    needs_update = False
    if not current_user.is_active:
        is_valid = False
        reason = "账户已被禁用"
        needs_update = True
    if license_obj.expiry_date:
        expiry = license_obj.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if expiry < now:
            is_valid = False
            reason = reason or "许可证已过期"
            needs_update = True

    if is_valid and req.fingerprint:
        can_bind = await check_and_bind_machine(db, current_user.id, req.fingerprint)
        if not can_bind:
            is_valid = False
            reason = "设备绑定数量已达上限(最多3台)"

    # 只有需要更新数据库时才加锁，减少锁竞争
    if needs_update or is_valid:
        license_result = await db.execute(
            select(License).filter(License.user_id == current_user.id).with_for_update()
        )
        license_obj = license_result.scalar_one_or_none()
        if not license_obj:
            return HeartbeatResponse(is_valid=False, reason="未找到许可证", timestamp=time.time())

        # 双重检查：加锁后再次确认状态
        if needs_update:
            if not current_user.is_active:
                license_obj.is_valid = False
            if license_obj.expiry_date:
                expiry = license_obj.expiry_date
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                now2 = datetime.now(timezone.utc)
                if expiry < now2 and license_obj.is_valid:
                    license_obj.is_valid = False

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

    # 生成签名数据：设备绑定限制是运行时限制，不修改数据库is_valid
    # 如果运行时判定无效但数据库is_valid仍为True，构造签名时标记为无效
    if not is_valid and license_obj.is_valid:
        # 设备绑定超限等运行时原因：签名标记为无效，但不修改数据库
        # 临时修改is_valid用于签名，签名后立即恢复（在commit前恢复，避免持久化）
        original_is_valid = license_obj.is_valid
        license_obj.is_valid = False
        license_data = encode_license_data(license_obj, current_user.username)
        license_obj.is_valid = original_is_valid
    else:
        license_data = encode_license_data(license_obj, current_user.username)

    await db.flush()
    await db.commit()

    return HeartbeatResponse(is_valid=is_valid, license=license_data, reason=reason, timestamp=time.time())


@router.get("/license_status", response_model=LicenseStatusResponse, summary="获取许可证状态")
async def get_license_status(
    fingerprint: str = None,
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

    from ..services.license_service import is_license_expired
    # 如果许可证已过期但is_valid仍为True，同步更新数据库
    reason = None
    needs_update = False
    if license_obj.is_valid and is_license_expired(license_obj):
        # 需要更新数据库，此时加锁防止并发修改
        result = await db.execute(
            select(License).filter(License.user_id == current_user.id).with_for_update()
        )
        license_obj = result.scalar_one_or_none()
        # 双重检查：加锁后再次确认状态
        if license_obj and license_obj.is_valid and is_license_expired(license_obj):
            license_obj.is_valid = False
            reason = "许可证已过期"
            needs_update = True
    # 如果用户被禁用，许可证也应无效
    if license_obj.is_valid and not current_user.is_active:
        if not needs_update:
            result = await db.execute(
                select(License).filter(License.user_id == current_user.id).with_for_update()
            )
            license_obj = result.scalar_one_or_none()
            needs_update = True
        if license_obj and license_obj.is_valid and not current_user.is_active:
            license_obj.is_valid = False
            reason = "账户已被禁用"
    # 如果提供了fingerprint，检查设备绑定限制
    if license_obj.is_valid and fingerprint:
        from ..services.heartbeat_service import check_and_bind_machine
        can_bind = await check_and_bind_machine(db, current_user.id, fingerprint)
        if not can_bind:
            reason = "设备绑定数量已达上限(最多3台)"
        else:
            needs_update = True
    # 统一提交所有修改
    if needs_update:
        await db.flush()
        await db.commit()
    # 如果is_valid=False，判断具体原因
    if not license_obj.is_valid and not reason:
        if not current_user.is_active:
            reason = "账户已被禁用"
        else:
            reason = "许可证已失效"

    # 生成签名数据：设备绑定限制是运行时限制，不修改数据库is_valid
    # 如果运行时判定无效但数据库is_valid仍为True，构造签名时标记为无效
    if reason and license_obj.is_valid:
        original_is_valid = license_obj.is_valid
        license_obj.is_valid = False
        license_data = encode_license_data(license_obj, current_user.username)
        license_obj.is_valid = original_is_valid
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



