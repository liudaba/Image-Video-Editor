import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import sqlalchemy

from app.config import settings, check_production_safety
from app.database import init_db, engine
from app.routers import auth, license, payment, user, version, admin


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limit: int = 60):
        super().__init__(app)
        self.rate_limit = rate_limit
        self._requests = {}

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        key = f"{client_ip}:{request.url.path}"

        if key not in self._requests:
            self._requests[key] = []

        self._requests[key] = [t for t in self._requests[key] if now - t < 60]

        if len(self._requests[key]) >= self.rate_limit:
            return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})

        self._requests[key].append(now)

        if len(self._requests) > 10000:
            oldest_keys = sorted(self._requests.keys(), key=lambda k: self._requests[k][-1] if self._requests[k] else 0)[:5000]
            for k in oldest_keys:
                del self._requests[k]

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_production_safety()
    await init_db()
    yield
    await engine.dispose()


app = FastAPI(
    title="短视频生成器 API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.exception_handler(sqlalchemy.exc.IntegrityError)
async def integrity_error_handler(request: Request, exc: sqlalchemy.exc.IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "数据冲突，请检查输入"})


@app.exception_handler(sqlalchemy.exc.DBAPIError)
async def db_error_handler(request: Request, exc: sqlalchemy.exc.DBAPIError):
    return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请稍后重试"})


app.add_middleware(RateLimitMiddleware, rate_limit=settings.RATE_LIMIT_PER_MINUTE)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(license.router)
app.include_router(payment.router)
app.include_router(user.router)
app.include_router(version.router)
app.include_router(admin.router)


@app.get("/health")
async def health_check():
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(sqlalchemy.text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
    }
