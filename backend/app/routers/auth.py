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
from ..schemas import UserRegister, UserLogin, LoginResponse
from ..auth import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    check_login_rate_limit,
    record_login_failure,
    clear_login_failures,
)
from ..services.license_service import (
    create_trial_license,
    encode_license_data
)
from ..config import settings


router = APIRouter(prefix="/api/auth", tags=["auth"])

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
    current_user.password_changed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    
    return {"message": "密码修改成功"}
