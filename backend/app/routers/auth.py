import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import time
from typing import Optional

from ..database import get_db  # 修复导入路径
from ..models import User
from ..schemas import UserRegister, UserLogin, LoginResponse, LicenseActivate, ActivateResponse, HeartbeatRequest, HeartbeatResponse
from ..auth import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    check_login_rate_limit,
    record_login_failure,
    clear_login_failures,
    require_admin
)
from ..services.license_service import (
    create_trial_license,
    activate_license,
    encode_license_data
)
from ..config import settings


router = APIRouter(prefix="/auth", tags=["auth"])

security = HTTPBearer()


@router.post("/register", summary="用户注册")
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    if not check_login_rate_limit(user_data.username):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")

    # 检查用户名和邮箱是否已存在
    from sqlalchemy import select
    result = await db.execute(
        select(User).filter((User.username == user_data.username) | (User.email == user_data.email))
    )
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")

    # 创建新用户
    hashed_pwd = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_pwd
    )
    db.add(new_user)
    await db.flush()

    # 为新用户创建试用许可证
    await create_trial_license(db, new_user.id)

    await db.commit()

    # 清除登录失败记录
    clear_login_failures(user_data.username)

    return {"message": "注册成功"}


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(user_data: UserLogin, db: AsyncSession = Depends(get_db)):
    if not check_login_rate_limit(user_data.username):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")

    # 检查用户是否存在
    from sqlalchemy import select
    result = await db.execute(select(User).filter(User.username == user_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_data.password, user.hashed_password):
        record_login_failure(user_data.username)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")

    # 创建访问令牌
    access_token = create_access_token(
        data={"user_id": user.id, "username": user.username}
    )

    # 获取用户许可证信息
    from ..models import License
    license_result = await db.execute(
        select(License).filter(License.user_id == user.id)
    )
    license_obj = license_result.scalar_one_or_none()

    license_data = None
    if license_obj:
        license_data = encode_license_data(license_obj, user.username)

    # 清除登录失败记录
    clear_login_failures(user_data.username)

    return LoginResponse(access_token=access_token, license=license_data)


@router.post("/activate-license", response_model=ActivateResponse, summary="激活许可证")
async def activate_license_endpoint(
    license_data: LicenseActivate, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from ..models import License
    from sqlalchemy import select
    
    # 尝试激活许可证
    activated_license = await activate_license(db, current_user.id, license_data.license_key)
    if not activated_license:
        raise HTTPException(status_code=400, detail="许可证激活失败，可能密钥无效或已被使用")
    
    # 获取最新的许可证信息
    license_result = await db.execute(
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = license_result.scalar_one_or_none()
    
    license_resp_data = None
    if license_obj:
        license_resp_data = encode_license_data(license_obj, current_user.username)
    
    return ActivateResponse(license=license_resp_data)


@router.post("/heartbeat", response_model=HeartbeatResponse, summary="心跳检测")
async def heartbeat(
    req: HeartbeatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from ..models import License, HeartbeatLog
    from sqlalchemy import select
    import secrets
    
    # 获取用户许可证
    license_result = await db.execute(
        select(License).filter(License.user_id == current_user.id)
    )
    license_obj = license_result.scalar_one_or_none()
    
    if not license_obj:
        return HeartbeatResponse(is_valid=False, reason="未找到许可证")
    
    # 检查许可证是否有效
    is_valid = license_obj.is_valid
    if license_obj.expiry_date:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        is_valid = is_valid and license_obj.expiry_date >= now
    
    # 创建心跳日志
    heartbeat_log = HeartbeatLog(
        user_id=current_user.id,
        fingerprint=req.fingerprint,
        app_version=req.app_version,
        license_type=license_obj.license_type.value,
        ip_address=None  # 可以从request获取IP
    )
    db.add(heartbeat_log)
    await db.flush()
    await db.commit()
    
    # 更新许可证最后心跳时间
    license_obj.last_heartbeat = datetime.datetime.now(datetime.timezone.utc)
    if req.fingerprint:
        license_obj.heartbeat_fingerprint = req.fingerprint
    await db.flush()
    await db.commit()
    
    license_data = encode_license_data(license_obj, current_user.username) if is_valid else None
    
    return HeartbeatResponse(is_valid=is_valid, license=license_data)


@router.get("/profile", summary="获取用户资料")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_admin": current_user.is_admin,
        "created_at": current_user.created_at,
    }


@router.post("/admin/change-password", summary="修改密码")
async def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    
    # 验证新密码强度
    try:
        UserRegister.validate_password_strength.__func__(None, new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 更新密码
    current_user.hashed_password = hash_password(new_password)
    current_user.password_changed_at = datetime.datetime.now(datetime.timezone.utc)
    await db.flush()
    await db.commit()
    
    return {"message": "密码修改成功"}
