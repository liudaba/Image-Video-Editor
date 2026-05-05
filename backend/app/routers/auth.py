from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import User, License
from app.schemas import UserRegister, UserLogin, LoginResponse, LicenseData
from app.auth import hash_password, verify_password, create_access_token
from app.services.license_service import create_trial_license, build_license_response, is_license_expired

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=LoginResponse)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where((User.username == body.username) | (User.email == body.email)))
    if result.scalar_one_or_none():
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

    return LoginResponse(access_token=token, license=license_data)


@router.post("/login", response_model=LoginResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
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

    license_data = None
    if license_obj:
        license_data = build_license_response(license_obj, user.username)

    return LoginResponse(access_token=token, license=license_data)
