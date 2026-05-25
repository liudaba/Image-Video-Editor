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

MAX_LOGIN_ATTEMPTS = 5          # 单用户最大失败次数
MAX_IP_LOGIN_ATTEMPTS = 20      # 单IP最大失败次数（同一IP可能有多个用户）
LOCKOUT_SECONDS = 900


_redis_pool = None
_redis_available = None  # None=未检测, True=可用, False=不可用
_redis_check_time = 0

def _get_redis():
    global _redis_pool, _redis_available, _redis_check_time
    now = time.time()
    # 如果Redis不可用且距上次检测不到30秒，直接返回None
    if _redis_available is False and now - _redis_check_time < 30:
        return None
    if _redis_pool is None:
        try:
            import redis
            _redis_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, max_connections=10
            )
            # 测试连接
            test_conn = redis.Redis(connection_pool=_redis_pool)
            test_conn.ping()
            _redis_available = True
        except Exception:
            _redis_pool = None
            _redis_available = False
            _redis_check_time = now
            return None
    try:
        import redis
        conn = redis.Redis(connection_pool=_redis_pool, socket_timeout=0.5)
        return conn
    except Exception:
        _redis_available = False
        _redis_check_time = now
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


def _get_max_attempts(identifier: str) -> int:
    """根据标识符类型返回最大失败次数"""
    return MAX_IP_LOGIN_ATTEMPTS if identifier.startswith("ip:") else MAX_LOGIN_ATTEMPTS


def _memory_rate_limit_check(identifier: str) -> bool:
    """内存限流检查（单进程快速路径）"""
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
    return True


def _memory_record_failure(identifier: str):
    """内存记录登录失败"""
    now = time.time()
    max_attempts = _get_max_attempts(identifier)
    entry = _memory_rate_limit.get(identifier, {"fails": 0, "first_fail": now, "lockout_until": None})
    entry["fails"] += 1
    if entry["fails"] >= max_attempts:
        entry["lockout_until"] = now + LOCKOUT_SECONDS
    _memory_rate_limit[identifier] = entry


def _memory_clear_failures(identifier: str):
    """内存清除登录失败记录"""
    _memory_rate_limit.pop(identifier, None)


def check_login_rate_limit(identifier: str) -> bool:
    """检查登录限流：Redis > 内存"""
    max_attempts = _get_max_attempts(identifier)
    r = _get_redis()
    if r is not None:
        try:
            lock_key = f"login_lockout:{identifier}"
            if r.exists(lock_key):
                return False
            fail_key = f"login_fail:{identifier}"
            fails = int(r.get(fail_key) or 0)
            if fails >= max_attempts:
                r.setex(lock_key, LOCKOUT_SECONDS, "1")
                r.delete(fail_key)
                return False
            return True
        except Exception:
            pass
    return _memory_rate_limit_check(identifier)


def record_login_failure(identifier: str):
    """记录登录失败：Redis > 内存"""
    max_attempts = _get_max_attempts(identifier)
    r = _get_redis()
    if r is not None:
        try:
            fail_key = f"login_fail:{identifier}"
            lock_key = f"login_lockout:{identifier}"
            fails = r.incr(fail_key)
            r.expire(fail_key, LOCKOUT_SECONDS)
            if fails >= max_attempts:
                r.setex(lock_key, LOCKOUT_SECONDS, "1")
            return
        except Exception:
            pass
    _memory_record_failure(identifier)


def clear_login_failures(identifier: str):
    """清除登录失败记录：Redis + 内存"""
    r = _get_redis()
    if r is not None:
        try:
            r.delete(f"login_fail:{identifier}")
            r.delete(f"login_lockout:{identifier}")
        except Exception:
            pass
    _memory_clear_failures(identifier)


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
        # PostgreSQL保留时区信息，确保naive datetime按UTC处理
        pw_changed = user.password_changed_at
        if pw_changed.tzinfo is None:
            pw_changed = pw_changed.replace(tzinfo=timezone.utc)
        # 加1秒缓冲，避免浮点精度导致密码修改后旧token仍被认为有效
        if token_issued < pw_changed.timestamp() - 1:
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
