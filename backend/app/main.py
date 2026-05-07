import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import sqlalchemy

from app.config import settings, check_production_safety
from app.database import init_db, engine
from app.routers import auth, license, payment, user, version, admin

logger = logging.getLogger("videogen")


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


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self._fallback_requests = {}
        self._redis_pool = None
        self._last_cleanup = time.time()

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
        if self._redis_pool is None:
            try:
                import redis
                self._redis_pool = redis.ConnectionPool.from_url(
                    settings.REDIS_URL, socket_timeout=1, max_connections=10
                )
            except Exception:
                pass
        return self._redis_pool

    def _check_redis_rate(self, client_ip: str, path: str) -> bool:
        try:
            import redis
            pool = self._get_redis_pool()
            if pool is None:
                return self._check_memory_rate(client_ip, path)
            r = redis.Redis(connection_pool=pool)
            now = int(time.time())
            window_key = f"ratelimit:{client_ip}:{path}:{now // 60}"
            count = r.incr(window_key)
            if count == 1:
                r.expire(window_key, 120)
            return count <= self.rate_limit
        except Exception:
            return self._check_memory_rate(client_ip, path)

    def _check_memory_rate(self, client_ip: str, path: str) -> bool:
        now = time.time()
        key = f"{client_ip}:{path}"
        if key not in self._fallback_requests:
            self._fallback_requests[key] = []
        self._fallback_requests[key] = [t for t in self._fallback_requests[key] if now - t < 60]
        if len(self._fallback_requests[key]) >= self.rate_limit:
            return False
        self._fallback_requests[key].append(now)
        self._cleanup_stale_entries()
        return True

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not self._check_redis_rate(client_ip, request.url.path):
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁,请稍后再试"})
        return await call_next(request)


MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    check_production_safety()
    await init_db()
    logger.info("Application started")
    yield
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
    return JSONResponse(status_code=409, content={"detail": "数据冲突,请检查输入"})


@app.exception_handler(sqlalchemy.exc.DBAPIError)
async def db_error_handler(request: Request, exc: sqlalchemy.exc.DBAPIError):
    return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用,请稍后重试"})


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
    checks = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:50]}"

    try:
        import redis as _redis
        loop = asyncio.get_event_loop()
        if RateLimitMiddleware._redis_pool:
            r = _redis.Redis(connection_pool=RateLimitMiddleware._redis_pool)
        else:
            r = await loop.run_in_executor(None, lambda: _redis.from_url(settings.REDIS_URL, socket_timeout=2))
        await loop.run_in_executor(None, r.ping)
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    try:
        import shutil
        loop = asyncio.get_event_loop()
        disk = await loop.run_in_executor(None, shutil.disk_usage, "/")
        checks["disk_free_gb"] = round(disk.free / (1024 ** 3), 2)
        checks["disk_percent"] = round(disk.used / disk.total * 100, 1)
    except Exception:
        pass

    all_ok = checks.get("database") == "ok"
    return {"status": "ok" if all_ok else "degraded", **checks}
