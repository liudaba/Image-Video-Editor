import asyncio
import json
import logging
import uuid
import secrets
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import sqlalchemy
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .config import settings, check_production_safety
from .database import init_db, engine, get_db
from .routers import auth, license, payment, user, version, admin
from .services.cleanup_service import cleanup_loop

logger = logging.getLogger("videogen")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


_TRUSTED_PROXY_COUNT = 1


def _get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",")]
        if len(parts) > _TRUSTED_PROXY_COUNT:
            return parts[-(_TRUSTED_PROXY_COUNT + 1)]
        return parts[0]
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def setup_logging():
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    formatter = JSONFormatter()

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    try:
        log_path = Path(settings.LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_path),
            maxBytes=settings.LOG_FILE_MAX_BYTES,
            backupCount=settings.LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception:
        pass


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self._fallback_requests = {}
        self._redis_pool = None
        self._last_cleanup = time.time()
        self._redis_available = None  # None=未检测, True=可用, False=不可用
        self._redis_check_time = 0
        self._lock = None  # 延迟初始化线程锁

    def _get_lock(self):
        if self._lock is None:
            import threading
            self._lock = threading.Lock()
        return self._lock

    def _cleanup_stale_entries(self):
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        stale_keys = [
            k for k, v in self._fallback_requests.items()
            if not v or now - v[-1] > 120
        ]
        for k in stale_keys:
            del self._fallback_requests[k]

    def _get_redis_pool(self):
        # 每30秒最多检测一次Redis可用性
        now = time.time()
        if self._redis_available is False and now - self._redis_check_time < 30:
            return None
        if self._redis_pool is None:
            try:
                import redis
                self._redis_pool = redis.ConnectionPool.from_url(
                    settings.REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5, max_connections=10
                )
                # 测试连接
                test_conn = redis.Redis(connection_pool=self._redis_pool)
                test_conn.ping()
                self._redis_available = True
            except Exception:
                self._redis_pool = None
                self._redis_available = False
                self._redis_check_time = now
        return self._redis_pool

    def _check_redis_rate(self, client_ip: str, path: str) -> bool:
        try:
            import redis
            pool = self._get_redis_pool()
            if pool is None:
                return self._check_memory_rate(client_ip, path)
            r = redis.Redis(connection_pool=pool, socket_timeout=0.5)
            now = int(time.time())
            window_key = f"ratelimit:{client_ip}:{path}:{now // 60}"
            count = r.incr(window_key)
            if count == 1:
                r.expire(window_key, 120)
            return count <= self.rate_limit
        except Exception:
            self._redis_available = False
            self._redis_check_time = time.time()
            return self._check_memory_rate(client_ip, path)

    def _check_memory_rate(self, client_ip: str, path: str) -> bool:
        now = time.time()
        key = f"{client_ip}:{path}"
        with self._get_lock():
            if key not in self._fallback_requests:
                self._fallback_requests[key] = []
            self._fallback_requests[key] = [t for t in self._fallback_requests[key] if now - t < 60]
            if len(self._fallback_requests[key]) >= self.rate_limit:
                return False
            self._fallback_requests[key].append(now)
            self._cleanup_stale_entries()
        return True

    def _is_admin_request(self, request: Request) -> bool:
        """检查请求是否来自管理员，管理员跳过限流"""
        try:
            from .auth import decode_access_token
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                token_data = decode_access_token(token)
                if token_data and token_data.username == "admin":
                    return True
        except Exception:
            pass
        return False

    async def dispatch(self, request: Request, call_next):
        # 管理员跳过限流
        if not self._is_admin_request(request):
            client_ip = _get_real_ip(request)
            if not self._check_redis_rate(client_ip, request.url.path):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁,请稍后再试"})
        return await call_next(request)


MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024


_cleanup_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    setup_logging()
    check_production_safety()
    await init_db()
    _cleanup_task = asyncio.create_task(cleanup_loop())
    logger.info("Application started (cleanup task running every %d hours)", settings.CLEANUP_INTERVAL_HOURS)
    yield
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutting down, draining connections...")
    await asyncio.sleep(2)
    await engine.dispose()
    logger.info("Application stopped")


app = FastAPI(
    title="短视频生成器 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.exception_handler(sqlalchemy.exc.IntegrityError)
async def integrity_error_handler(request: Request, exc: sqlalchemy.exc.IntegrityError):
    logger.error(f"IntegrityError: {exc}", exc_info=True)
    return JSONResponse(status_code=409, content={"detail": "数据冲突,请检查输入"})


@app.exception_handler(sqlalchemy.exc.DBAPIError)
async def db_error_handler(request: Request, exc: sqlalchemy.exc.DBAPIError):
    logger.error(f"DBAPIError: {exc}", exc_info=True)
    return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用,请稍后重试"})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


app.add_middleware(RateLimitMiddleware, rate_limit=settings.RATE_LIMIT_PER_MINUTE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.middleware("http")
async def verify_csrf(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    admin_paths = ("/admin/", "/api/admin/", "/auth/logout")
    if not any(request.url.path.startswith(p) for p in admin_paths):
        return await call_next(request)
    admin_session = request.cookies.get("admin_session")
    if not admin_session:
        return await call_next(request)
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_cookie or not csrf_header or csrf_header != csrf_cookie:
        return JSONResponse(status_code=403, content={"detail": "CSRF验证失败"})
    return await call_next(request)


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BODY_SIZE:
            return JSONResponse(status_code=413, content={"detail": "请求体过大"})
    return await call_next(request)


app.include_router(auth.router)
app.include_router(license.router)
app.include_router(payment.router)
app.include_router(user.router)
app.include_router(version.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    db_ok = False
    redis_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    try:
        from .auth import _get_redis
        r = _get_redis()
        if r:
            r.ping()
            redis_ok = True
    except Exception:
        pass

    status_code = 200 if db_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "unavailable",
            "version": "1.0.0",
        }
    )


@app.get("/")
async def root():
    return {"message": "短视频生成器 API"}


@app.get("/admin/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.post("/auth/login")
async def admin_login(request: Request, db=Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="无效的请求体")
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    from .auth import verify_password, create_access_token, check_login_rate_limit, record_login_failure, clear_login_failures
    from sqlalchemy import select
    from .models import User
    if not check_login_rate_limit(f"admin:{username}"):
        raise HTTPException(status_code=429, detail="请求过于频繁,请稍后再试")
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        record_login_failure(f"admin:{username}")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    clear_login_failures(f"admin:{username}")
    # 记录管理员登录审计日志
    from .models import AuditLog
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
    audit_log = AuditLog(
        operator_id=user.id,
        operator_name=user.username,
        action="admin_login",
        detail=f"username={username}, ip={client_ip}",
        ip_address=client_ip,
    )
    db.add(audit_log)
    await db.commit()
    access_token = create_access_token(data={"user_id": user.id, "username": user.username})
    csrf_token = secrets.token_hex(32)
    response = JSONResponse(content={"success": True, "access_token": access_token, "csrf_token": csrf_token})
    is_secure = request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https"
    response.set_cookie(
        key="admin_session",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        secure=is_secure,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        secure=is_secure,
    )
    return response


@app.post("/auth/logout")
async def admin_logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie(key="admin_session", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return response


@app.get("/admin/dashboard")
async def dashboard_page(request: Request, db=Depends(get_db)):
    session_token = request.cookies.get("admin_session")
    if not session_token:
        return templates.TemplateResponse(request, "login.html")
    try:
        from .auth import decode_access_token
        token_data = decode_access_token(session_token)
        from sqlalchemy import select
        from .models import User
        user = (await db.execute(select(User).where(User.id == token_data.user_id))).scalar_one_or_none()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="需要管理员权限")
    except HTTPException:
        return templates.TemplateResponse(request, "login.html")
    return templates.TemplateResponse(request, "admin_base.html")


@app.get("/admin/content/{section}")
async def get_content(request: Request, section: str, db=Depends(get_db)):
    session_token = request.cookies.get("admin_session")
    if not session_token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        from .auth import decode_access_token
        token_data = decode_access_token(session_token)
        from sqlalchemy import select
        from .models import User
        user = (await db.execute(select(User).where(User.id == token_data.user_id))).scalar_one_or_none()
        if not user or not user.is_admin:
            raise HTTPException(status_code=403, detail="需要管理员权限")
    except HTTPException:
        raise HTTPException(status_code=401, detail="登录已过期")

    template_files = {
        "dashboard": "dashboard_content.html",
        "users": "users_content.html",
        "licenses": "licenses_content.html",
        "trial_codes": "trial_codes_content.html",
        "versions": "versions_content.html",
        "orders": "orders_content.html",
        "analytics": "analytics_content.html",
        "audit_logs": "audit_logs_content.html"
    }

    template_file = template_files.get(section)
    if not template_file:
        raise HTTPException(status_code=404, detail="内容不存在")

    return templates.TemplateResponse(request, template_file)

