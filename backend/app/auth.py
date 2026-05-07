import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import TokenData

logger = logging.getLogger("videogen")
security = HTTPBearer()

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
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


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


def check_login_rate_limit(identifier: str) -> bool:
    r = _get_redis()
    if r is None:
        return True
    try:
        fail_key = f"login_fail:{identifier}"
        lock_key = f"login_lockout:{identifier}"
        if r.exists(lock_key):
            return False
        fails = int(r.get(fail_key) or 0)
        return fails < MAX_LOGIN_ATTEMPTS
    except Exception:
        return True


def record_login_failure(identifier: str):
    r = _get_redis()
    if r is None:
        return
    try:
        fail_key = f"login_fail:{identifier}"
        lock_key = f"login_lockout:{identifier}"
        fails = r.incr(fail_key)
        r.expire(fail_key, LOCKOUT_SECONDS)
        if fails >= MAX_LOGIN_ATTEMPTS:
            r.setex(lock_key, LOCKOUT_SECONDS, "1")
    except Exception:
        pass


def clear_login_failures(identifier: str):
    r = _get_redis()
    if r is None:
        return
    try:
        r.delete(f"login_fail:{identifier}")
        r.delete(f"login_lockout:{identifier}")
    except Exception:
        pass


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token_data = decode_access_token(credentials.credentials)
    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账户已被禁用")
    if user.password_changed_at:
        token_issued = token_data.exp - timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        if token_issued < user.password_changed_at.timestamp():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码已修改,请重新登录")
    return user


async def require_admin(
    request: Request,
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
