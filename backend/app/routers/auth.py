import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import User, License
from app.schemas import UserRegister, UserLogin, LoginResponse, LicenseData
from app.auth import (
    hash_password, verify_password, create_access_token,
    check_login_rate_limit, record_login_failure, clear_login_failures,
)
from app.services.license_service import create_trial_license, build_license_response, is_license_expired

logger = logging.getLogger("videogen")
router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=LoginResponse)
async def register(body: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="注册尝试过多,请15分钟后再试")

    result = await db.execute(select(User).where((User.username == body.username) | (User.email == body.email)))
    if result.scalars().first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或邮箱已存在")

    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或邮箱已存在")

    trial = create_trial_license(user.id)
    db.add(trial)
    await db.flush()
    await db.refresh(user)
    await db.refresh(trial)

    token = create_access_token(data={"user_id": user.id, "username": user.username})
    license_data = build_license_response(trial, user.username)
    clear_login_failures(client_ip)

    return LoginResponse(access_token=token, license=license_data)


@router.post("/login", response_model=LoginResponse)
async def login(body: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"

    if not check_login_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="登录尝试过多,请15分钟后再试")
    if not check_login_rate_limit(body.username):
        raise HTTPException(status_code=429, detail="账号暂时锁定,请15分钟后再试")

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        record_login_failure(client_ip)
        record_login_failure(body.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")

    result = await db.execute(select(License).where(License.user_id == user.id))
    license_obj = result.scalar_one_or_none()

    if license_obj and is_license_expired(license_obj):
        license_obj.is_valid = False
        await db.flush()
        await db.refresh(license_obj)

    token = create_access_token(data={"user_id": user.id, "username": user.username})
    clear_login_failures(client_ip)
    clear_login_failures(body.username)

    license_data = None
    if license_obj:
        license_data = build_license_response(license_obj, user.username)

    return LoginResponse(access_token=token, license=license_data)
