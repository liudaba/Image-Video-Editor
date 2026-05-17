import logging
import random
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import time
from typing import Optional

from ..database import get_db
from ..models import User, MachineBinding, License
from ..schemas import UserRegister, UserLogin, LoginResponse, PasswordResetRequest, PasswordResetConfirm
from ..auth import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
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

_RESET_CODE_TTL = 600
_RESET_CODE_MAX_ATTEMPTS = 5


def _get_redis_for_reset():
    try:
        import redis
        pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL, socket_timeout=2, max_connections=5
        )
        return redis.Redis(connection_pool=pool)
    except Exception:
        return None


_memory_reset_codes = {}

def _store_reset_code(email: str, code: str) -> bool:
    r = _get_redis_for_reset()
    if r:
        try:
            key = f"pwd_reset:{email}"
            r.setex(key, _RESET_CODE_TTL, f"{code}:0")
            return True
        except Exception:
            pass
    _memory_reset_codes[email] = (code, 0, time.time() + _RESET_CODE_TTL)
    return True


def _verify_reset_code(email: str, code: str) -> tuple[bool, str]:
    r = _get_redis_for_reset()
    if r:
        try:
            key = f"pwd_reset:{email}"
            val = r.get(key)
            if not val:
                return False, "验证码已过期，请重新获取"
            stored_code, attempts = val.decode().split(":")
            attempts = int(attempts) + 1
            if attempts > _RESET_CODE_MAX_ATTEMPTS:
                r.delete(key)
                return False, "验证次数过多，请重新获取验证码"
            if stored_code != code:
                r.setex(key, r.ttl(key) or _RESET_CODE_TTL, f"{stored_code}:{attempts}")
                return False, "验证码错误"
            r.delete(key)
            return True, ""
        except Exception:
            pass
    if email in _memory_reset_codes:
        stored_code, attempts, expire_at = _memory_reset_codes[email]
        if time.time() > expire_at:
            del _memory_reset_codes[email]
            return False, "验证码已过期，请重新获取"
        attempts += 1
        if attempts > _RESET_CODE_MAX_ATTEMPTS:
            del _memory_reset_codes[email]
            return False, "验证次数过多，请重新获取验证码"
        if stored_code != code:
            _memory_reset_codes[email] = (stored_code, attempts, expire_at)
            return False, "验证码错误"
        del _memory_reset_codes[email]
        return True, ""
    return False, "验证码已过期，请重新获取"


def _send_reset_email(email: str, code: str) -> bool:
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = getattr(settings, "SMTP_HOST", "")
        smtp_port = getattr(settings, "SMTP_PORT", 465)
        smtp_user = getattr(settings, "SMTP_USER", "")
        smtp_pass = getattr(settings, "SMTP_PASSWORD", "")
        smtp_from = getattr(settings, "SMTP_FROM", smtp_user)

        if not smtp_host or not smtp_user:
            logger.warning("SMTP not configured, reset code for %s: %s", email, code)
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "短视频生成器 - 密码重置验证码"
        msg["From"] = smtp_from
        msg["To"] = email

        text_body = f"您的验证码为: {code}，10分钟内有效。如非本人操作请忽略。"
        html_body = f"""
        <div style="max-width:480px;margin:0 auto;font-family:sans-serif;padding:20px;">
            <h2 style="color:#2196f3;">密码重置验证码</h2>
            <p>您的验证码为:</p>
            <div style="font-size:32px;font-weight:bold;color:#2196f3;letter-spacing:4px;margin:20px 0;">{code}</div>
            <p style="color:#888;">验证码10分钟内有效，如非本人操作请忽略此邮件。</p>
        </div>
        """
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            server.starttls()

        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_from, [email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send reset email to {email}: {e}")
        return False


logger = logging.getLogger("videogen")


@router.post("/request-reset", summary="请求重置密码")
async def request_reset(data: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from ..main import _get_real_ip
    client_ip = _get_real_ip(request)
    if not check_login_rate_limit(f"reset:{client_ip}"):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")

    result = await db.execute(select(User).filter(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用，请联系客服")

    code = f"{secrets.randbelow(1000000):06d}"

    stored = _store_reset_code(data.email, code)
    if not stored:
        logger.warning("Redis unavailable for reset code storage, using in-memory fallback")

    email_sent = _send_reset_email(data.email, code)
    if not email_sent:
        logger.warning("Email send failed for %s, code: %s (display for debug only)", data.email, code)
        if stored:
            return {"message": "验证码已生成，邮件服务暂不可用，请联系客服获取验证码"}
        raise HTTPException(
            status_code=503,
            detail="验证码服务暂不可用，请稍后重试或联系客服重置密码"
        )

    return {"message": "验证码已发送到您的邮箱"}


@router.post("/confirm-reset", summary="确认重置密码")
async def confirm_reset(data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    success, error_msg = _verify_reset_code(data.email, data.code)
    if not success:
        raise HTTPException(status_code=400, detail=error_msg)

    result = await db.execute(select(User).filter(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用，请联系客服")

    user.hashed_password = hash_password(data.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    return {"message": "密码重置成功"}


@router.post("/register", summary="用户注册")
async def register(user_data: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    from ..main import _get_real_ip
    client_ip = _get_real_ip(request)
    if not check_login_rate_limit(f"reg:{client_ip}"):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")

    if user_data.fingerprint:
        from sqlalchemy import func as sa_func
        fp_user_count = await db.execute(
            select(sa_func.count(MachineBinding.id)).where(MachineBinding.fingerprint == user_data.fingerprint)
        )
        fp_count = fp_user_count.scalar() or 0
        if fp_count >= 3:
            raise HTTPException(status_code=429, detail="该设备注册账号数量已达上限")
        from ..models import License
        fp_active_trial = await db.execute(
            select(sa_func.count(License.id))
            .join(MachineBinding, MachineBinding.user_id == License.user_id)
            .where(
                MachineBinding.fingerprint == user_data.fingerprint,
                License.license_type == "trial",
                License.is_valid == True,
            )
        )
        active_trial_count = fp_active_trial.scalar() or 0
        if active_trial_count >= 1 and fp_count >= 1:
            raise HTTPException(status_code=429, detail="该设备已有试用账号，请购买正版授权")

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

    if user_data.fingerprint:
        binding = MachineBinding(
            user_id=new_user.id,
            fingerprint=user_data.fingerprint,
        )
        db.add(binding)
        await db.flush()

    await db.commit()

    # 清除登录失败记录
    clear_login_failures(user_data.username)

    return {"message": "注册成功"}


@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(user_data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    from ..main import _get_real_ip
    client_ip = _get_real_ip(request)
    if not check_login_rate_limit(user_data.username):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")
    if not check_login_rate_limit(f"ip:{client_ip}"):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")

    # 检查用户是否存在
    result = await db.execute(select(User).filter(User.username == user_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user_data.password, user.hashed_password):
        record_login_failure(user_data.username)
        record_login_failure(f"ip:{client_ip}")
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


@router.post("/token-renew", response_model=LoginResponse, summary="Token续期")
async def token_renew(request: Request, db: AsyncSession = Depends(get_db)):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少授权令牌")
    
    token = auth_header[7:]
    
    try:
        from ..auth import decode_token
        payload = decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="令牌无效或已过期")
        
        user_id = payload.get("user_id")
        username = payload.get("username")
        if not user_id or not username:
            raise HTTPException(status_code=401, detail="令牌数据不完整")
    except Exception:
        raise HTTPException(status_code=401, detail="令牌验证失败")
    
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="账户不可用")
    
    from ..auth import create_access_token
    new_token = create_access_token(
        data={"user_id": user.id, "username": user.username}
    )
    
    from ..models import License
    license_result = await db.execute(
        select(License).filter(License.user_id == user.id)
    )
    license_obj = license_result.scalar_one_or_none()
    
    license_data = None
    if license_obj:
        from ..services.license_service import encode_license_data
        license_data = encode_license_data(license_obj, user.username)
    
    return LoginResponse(access_token=new_token, license=license_data)


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
