import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from ..database import get_db
from ..models import User, License, AuditLog, HeartbeatLog
from ..auth import require_admin, get_current_user
from ..schemas import UserRegister, HeartbeatRequest, HeartbeatResponse, LicenseStatusResponse
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
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = license_result.scalar_one_or_none()

    if not license_obj:
        return HeartbeatResponse(is_valid=False, reason="未找到许可证", timestamp=time.time())

    is_valid = license_obj.is_valid
    if not current_user.is_active:
        is_valid = False
    if license_obj.expiry_date:
        expiry = license_obj.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if expiry < now:
            is_valid = False
            license_obj.is_valid = False

    if is_valid and req.fingerprint:
        can_bind = await check_and_bind_machine(db, current_user.id, req.fingerprint)
        if not can_bind:
            return HeartbeatResponse(
                is_valid=False,
                reason="设备绑定数量已达上限(最多3台)",
                timestamp=time.time()
            )

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

    await db.flush()
    await db.commit()

    license_data = encode_license_data(license_obj, current_user.username) if is_valid else None

    return HeartbeatResponse(is_valid=is_valid, license=license_data, timestamp=time.time())


@router.get("/license_status", response_model=LicenseStatusResponse, summary="获取许可证状态")
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


@router.get("/", summary="获取用户列表（仅管理员）")
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    result = await db.execute(
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            for user in users
        ]
    }


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


@router.put("/{user_id}", summary="更新用户信息（仅管理员）")
async def update_user(
    user_id: int,
    username: str = None,
    email: str = None,
    is_active: bool = None,
    is_admin: bool = None,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if is_active is not None and is_active is False and user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
        from ..models import License as LicenseModel
        license_result = await db.execute(select(LicenseModel).where(LicenseModel.user_id == user_id))
        user_license = license_result.scalar_one_or_none()
        if user_license:
            user_license.is_valid = is_active
            await db.flush()
    if is_admin is not None:
        user.is_admin = is_admin

    await db.flush()

    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="update_user",
        target_type="user",
        target_id=user.id,
        detail=f"Updated user {user.username}",
        ip_address=None
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "用户更新成功"}


@router.delete("/{user_id}", summary="删除用户（仅管理员）")
async def delete_user(
    user_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select, delete

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账户")

    await db.execute(delete(User).where(User.id == user_id))

    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="delete_user",
        target_type="user",
        target_id=user_id,
        detail=f"Deleted user {user.username}",
        ip_address=None
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "用户删除成功"}


@router.post("/reset-password/{user_id}", summary="重置用户密码（仅管理员）")
async def reset_user_password(
    user_id: int,
    current_user=Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    from ..auth import hash_password
    import secrets
    import string

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    alphabet = string.ascii_letters + string.digits
    new_password = ''.join(secrets.choice(alphabet) for _ in range(16))
    user.hashed_password = hash_password(new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    await db.flush()

    audit_log = AuditLog(
        operator_id=current_user.id,
        operator_name=current_user.username,
        action="reset_password",
        target_type="user",
        target_id=user_id,
        detail=f"Reset password for user {user.username}",
        ip_address=None
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "密码重置成功", "new_password": new_password}
