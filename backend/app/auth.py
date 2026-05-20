import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import time

from .config import settings
from .database import get_db
from .models import User
from .schemas import TokenData

logger = logging.getLogger("videogen")
security = HTTPBearer(auto_error=False)

MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 900


_redis_pool = None


def _get_redis():
    global _redis_pool
    if _redis_pool is None:
        try:
            import redis
            _redis_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL, socket_timeout=2, max_connections=10
            )
        except Exception:
            return None
    try:
        import redis
        return redis.Redis(connection_pool=_redis_pool)
    except Exception:
        return None


def hash_password(password: str) -> str:
    # bcrypt限制72字节，超长密码截断
    pwd_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # bcrypt限制72字节，超长密码截断
    pwd_bytes = plain_password.encode("utf-8")[:72]
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except Exception:
        return None


def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = payload.get("user_id")
        username: str = payload.get("username")
        exp: float = payload.get("exp", 0)
        if user_id is None or username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭据")
        return TokenData(user_id=user_id, username=username, exp=exp)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="认证凭据已过期或无效")


_memory_rate_limit: dict = {}

def check_login_rate_limit(identifier: str) -> bool:
    r = _get_redis()
    if r is not None:
        try:
            lock_key = f"login_lockout:{identifier}"
            if r.exists(lock_key):
                return False
            fail_key = f"login_fail:{identifier}"
            fails = int(r.get(fail_key) or 0)
            if fails >= MAX_LOGIN_ATTEMPTS:
                r.setex(lock_key, LOCKOUT_SECONDS, "1")
                r.delete(fail_key)
                return False
            return True
        except Exception:
            pass
    # Fallback to in-memory rate limiting
    now = time.time()
    entry = _memory_rate_limit.get(identifier)
    if entry is None:
        return True
    lockout_until = entry.get("lockout_until")
    if lockout_until and now < lockout_until:
        return False
    if lockout_until and now >= lockout_until:
        del _memory_rate_limit[identifier]
        return True
    fails = entry.get("fails", 0)
    if fails >= MAX_LOGIN_ATTEMPTS:
        entry["lockout_until"] = now + LOCKOUT_SECONDS
        return False
    return True


def record_login_failure(identifier: str):
    r = _get_redis()
    if r is not None:
        try:
            fail_key = f"login_fail:{identifier}"
            lock_key = f"login_lockout:{identifier}"
            fails = r.incr(fail_key)
            r.expire(fail_key, LOCKOUT_SECONDS)
            if fails >= MAX_LOGIN_ATTEMPTS:
                r.setex(lock_key, LOCKOUT_SECONDS, "1")
            return
        except Exception:
            pass
    # Fallback to in-memory
    now = time.time()
    entry = _memory_rate_limit.get(identifier, {"fails": 0, "first_fail": now, "lockout_until": None})
    entry["fails"] += 1
    if entry["fails"] >= MAX_LOGIN_ATTEMPTS:
        entry["lockout_until"] = now + LOCKOUT_SECONDS
    _memory_rate_limit[identifier] = entry


def clear_login_failures(identifier: str):
    r = _get_redis()
    if r is not None:
        try:
            r.delete(f"login_fail:{identifier}")
            r.delete(f"login_lockout:{identifier}")
        except Exception:
            pass
    _memory_rate_limit.pop(identifier, None)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("admin_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token_data = decode_access_token(token)
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")
    if user.password_changed_at:
        token_issued = token_data.exp - settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
        if token_issued < user.password_changed_at.timestamp():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码已修改,请重新登录")
    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        token = request.cookies.get("admin_session")
    if not token:
        return None
    try:
        token_data = decode_access_token(token)
        result = await db.execute(select(User).where(User.id == token_data.user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
    except Exception:
        pass
    return None


async def require_admin(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
