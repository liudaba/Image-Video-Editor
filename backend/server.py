# -*- coding: utf-8 -*-
"""
短视频生成器 - 统一后端服务
合并用户系统 + 授权管理 + 版本更新 + 支付回调

部署方式:
  开发: python server.py
  生产: gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlencode

import jwt
from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from passlib.hash import bcrypt
from pydantic import BaseModel, field_validator

logger = logging.getLogger("videogen")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

app = FastAPI(title="VideoGen API Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

SECRET_KEY = os.environ.get("VIDEOGEN_SECRET_KEY", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

if not SECRET_KEY:
    _key_file = os.path.join(os.path.dirname(__file__), ".secret_key")
    if os.path.exists(_key_file):
        with open(_key_file, "r") as _f:
            SECRET_KEY = _f.read().strip()
    if not SECRET_KEY:
        SECRET_KEY = secrets.token_urlsafe(64)
        try:
            with open(_key_file, "w") as _f:
                _f.write(SECRET_KEY)
        except Exception:
            pass

DB_PATH = os.environ.get("VIDEOGEN_DB_PATH", os.path.join(os.path.dirname(__file__), "videogen.db"))

_LICENSE_SIGN_SECRET = os.environ.get("VIDEOGEN_LICENSE_SIGN_KEY", "")
if not _LICENSE_SIGN_SECRET:
    _ls_file = os.path.join(os.path.dirname(__file__), ".license_sign_key")
    if os.path.exists(_ls_file):
        with open(_ls_file, "r") as _f:
            _LICENSE_SIGN_SECRET = _f.read().strip()
    if not _LICENSE_SIGN_SECRET:
        _LICENSE_SIGN_SECRET = secrets.token_urlsafe(48)
        try:
            with open(_ls_file, "w") as _f:
                _f.write(_LICENSE_SIGN_SECRET)
        except Exception:
            pass
_LICENSE_SIGN_SECRET = _LICENSE_SIGN_SECRET.encode("utf-8")

ADMIN_TOKEN = os.environ.get("VIDEOGEN_ADMIN_TOKEN", "")
if not ADMIN_TOKEN:
    _admin_file = os.path.join(os.path.dirname(__file__), ".admin_token")
    if os.path.exists(_admin_file):
        with open(_admin_file, "r") as _f:
            ADMIN_TOKEN = _f.read().strip()
    if not ADMIN_TOKEN:
        ADMIN_TOKEN = secrets.token_urlsafe(32)
        try:
            with open(_admin_file, "w") as _f:
                _f.write(ADMIN_TOKEN)
        except Exception:
            pass

_HUPPIAO_PID = os.environ.get("VIDEOGEN_HUPPIAO_PID", "")
_HUPPIAO_SECRET = os.environ.get("VIDEOGEN_HUPPIAO_SECRET", "")

TRIAL_DAYS = 7
GRACE_HOURS = 2

PRICING = {
    "monthly": {"amount": 29.9, "days": 30, "label": "月卡"},
    "quarterly": {"amount": 69.0, "days": 90, "label": "季卡"},
    "yearly": {"amount": 169.0, "days": 365, "label": "年卡"},
    "lifetime": {"amount": 299.0, "days": 36500, "label": "终身"},
}

_login_attempts = defaultdict(list)
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = 300

VALID_ACTION_TYPES = {
    "generate_video", "generate_script", "generate_images",
    "generate_audio", "export_video", "login", "other",
}


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                license_type TEXT DEFAULT 'trial',
                plan_type TEXT DEFAULT '',
                trial_start TEXT,
                trial_end TEXT,
                expiry_date TEXT,
                license_key TEXT UNIQUE,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                order_no TEXT UNIQUE NOT NULL,
                plan_type TEXT NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'pending',
                payment_method TEXT,
                trade_no TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_name TEXT NOT NULL,
                audio_file TEXT,
                settings TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_stats(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_projects_user ON user_projects(user_id)')

        try:
            c.execute("ALTER TABLE licenses ADD COLUMN plan_type TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码长度至少8位")
    if not re.search(r'[A-Z]', password):
        raise ValueError("密码必须包含至少一个大写字母")
    if not re.search(r'[a-z]', password):
        raise ValueError("密码必须包含至少一个小写字母")
    if not re.search(r'\d', password):
        raise ValueError("密码必须包含至少一个数字")


def _check_login_rate(username: str) -> None:
    now = time.time()
    attempts = _login_attempts[username]
    attempts[:] = [t for t in attempts if now - t < LOGIN_RATE_WINDOW]
    if len(attempts) >= LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过于频繁，请{int(LOGIN_RATE_WINDOW / 60)}分钟后再试"
        )


def _record_login_attempt(username: str) -> None:
    _login_attempts[username].append(time.time())


def _compute_license_signature(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hmac.new(_LICENSE_SIGN_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _sign_license_data(data: dict) -> dict:
    result = {k: v for k, v in data.items() if k != "signature"}
    result["signature"] = _compute_license_signature(result)
    return result


def _compare_versions(v1: str, v2: str) -> int:
    try:
        t1 = tuple(int(x) for x in v1.split("."))
        t2 = tuple(int(x) for x in v2.split("."))
        if t1 > t2:
            return 1
        elif t1 < t2:
            return -1
        return 0
    except (ValueError, AttributeError):
        return 0


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "jti": secrets.token_urlsafe(16)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = auth_header[7:]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def verify_admin(request: Request):
    token = request.headers.get("X-Admin-Token", "")
    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="管理员认证失败")


def _get_user_id(conn, username: str) -> int:
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    return row[0]


def _get_user_license(conn, user_id: int) -> Optional[dict]:
    c = conn.cursor()
    c.execute(
        "SELECT id, license_type, plan_type, trial_start, trial_end, expiry_date, license_key, is_active "
        "FROM licenses WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = c.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "license_type": row[1], "plan_type": row[2] if len(row) > 2 else "",
        "trial_start": row[3] if len(row) > 3 else row[2],
        "trial_end": row[4] if len(row) > 4 else row[3],
        "expiry_date": row[5] if len(row) > 5 else row[4],
        "license_key": row[6] if len(row) > 6 else row[5],
        "is_active": row[7] if len(row) > 7 else row[6],
    }


def _compute_license_status(lic: Optional[dict]) -> dict:
    if not lic:
        return {"license_type": "none", "is_valid": False, "days_left": 0}
    now = datetime.utcnow()
    if lic["license_type"] == "trial" and lic["trial_end"]:
        try:
            trial_end_dt = datetime.fromisoformat(lic["trial_end"])
            if now <= trial_end_dt + timedelta(hours=GRACE_HOURS):
                days_left = max(0, (trial_end_dt - now).days)
                return {"license_type": "trial", "days_left": days_left, "is_valid": days_left > 0}
        except (ValueError, TypeError):
            pass
    if lic["license_type"] == "pro" and lic["expiry_date"]:
        try:
            expiry_dt = datetime.fromisoformat(lic["expiry_date"])
            if now <= expiry_dt + timedelta(hours=GRACE_HOURS):
                days_left = max(0, (expiry_dt - now).days)
                return {"license_type": "pro", "days_left": days_left, "is_valid": days_left > 0 and lic["is_active"]}
        except (ValueError, TypeError):
            pass
    return {"license_type": lic["license_type"], "is_valid": False, "days_left": 0}


def _build_signed_license(username: str, lic: Optional[dict], lic_status: dict) -> dict:
    license_payload = {
        "username": username,
        "license_type": lic_status["license_type"],
        "is_valid": lic_status["is_valid"],
        "days_left": lic_status["days_left"],
    }
    if lic and lic.get("trial_end"):
        license_payload["trial_end"] = lic["trial_end"]
    if lic and lic.get("expiry_date"):
        license_payload["expiry_date"] = lic["expiry_date"]
    return _sign_license_data(license_payload)


class UserRegister(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]{3,20}$', v):
            raise ValueError("用户名仅支持3-20位字母、数字、下划线或中文")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
            raise ValueError("邮箱格式不正确")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, v):
        _validate_password(v)
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class LicenseActivate(BaseModel):
    license_key: str


class CreateOrder(BaseModel):
    plan_type: str
    payment_method: str


class ProjectSave(BaseModel):
    project_name: str
    audio_file: str
    settings: dict


class UsageTrackRequest(BaseModel):
    action_type: str


class VersionData(BaseModel):
    version: str
    release_date: str
    download_url: str
    file_size: int
    changelog: List[str]
    force_update: bool = False
    priority: str = "normal"


class AssignKeyRequest(BaseModel):
    order_no: str
    license_key: str


@app.post("/api/auth/register")
def register(user: UserRegister):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (user.username,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="用户名已存在")
        c.execute("SELECT id FROM users WHERE email=?", (user.email,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="邮箱已被注册")
        password_hash = bcrypt.hash(user.password)
        c.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (user.username, user.email, password_hash)
        )
        user_id = c.lastrowid
        now = datetime.utcnow()
        trial_end = now + timedelta(days=TRIAL_DAYS)
        c.execute(
            "INSERT INTO licenses (user_id, license_type, plan_type, trial_start, trial_end) VALUES (?, 'trial', 'trial', ?, ?)",
            (user_id, now.isoformat(), trial_end.isoformat())
        )
    logger.info(f"用户注册: {user.username}")
    return {"message": "注册成功", "username": user.username}


@app.post("/api/auth/login")
def login(user: UserLogin):
    _check_login_rate(user.username)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash FROM users WHERE username=?", (user.username,))
        result = c.fetchone()
        if not result or not bcrypt.verify(user.password, result[2]):
            _record_login_attempt(user.username)
            logger.warning(f"登录失败: {user.username}")
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        user_id, username, _ = result
        c.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.utcnow().isoformat(), user_id))
        access_token = create_access_token(data={"sub": username})
        lic = _get_user_license(conn, user_id)
        lic_status = _compute_license_status(lic)
        signed_license = _build_signed_license(username, lic, lic_status)
    _login_attempts.pop(user.username, None)
    logger.info(f"用户登录: {username}, 授权类型: {lic_status['license_type']}, 有效: {lic_status['is_valid']}")
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": username,
        "license": signed_license,
    }


@app.get("/api/auth/check")
def check_auth(username: str = Depends(get_current_user)):
    return {"authenticated": True, "username": username}


@app.get("/api/user/license_status")
def get_license_status(username: str = Depends(get_current_user)):
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        lic = _get_user_license(conn, user_id)
        lic_status = _compute_license_status(lic)
        signed_license = _build_signed_license(username, lic, lic_status)
    return {"status": lic_status, "license": signed_license}


@app.post("/api/license/activate")
def activate_license(req: LicenseActivate, username: str = Depends(get_current_user)):
    license_key = req.license_key.strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="授权码不能为空")
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        c = conn.cursor()
        c.execute(
            "SELECT id, user_id, plan_type FROM licenses WHERE license_key=? AND is_active=1",
            (license_key,)
        )
        lic = c.fetchone()
        if not lic:
            raise HTTPException(status_code=404, detail="授权码无效或已过期")
        lic_id, lic_user_id, plan_type = lic[0], lic[1], lic[2] if len(lic) > 2 else ""
        if lic_user_id != user_id:
            raise HTTPException(status_code=403, detail="该授权码不属于当前用户")
        plan = PRICING.get(plan_type) if plan_type else None
        days = plan["days"] if plan else 365
        expiry_date = datetime.utcnow() + timedelta(days=days)
        c.execute(
            "UPDATE licenses SET license_type='pro', expiry_date=? WHERE id=?",
            (expiry_date.isoformat(), lic_id)
        )
        updated_lic = _get_user_license(conn, user_id)
        lic_status = _compute_license_status(updated_lic)
        signed_license = _build_signed_license(username, updated_lic, lic_status)
    logger.info(f"授权激活: {username}, 授权码: {license_key[:8]}..., 天数: {days}")
    return {
        "message": "授权激活成功",
        "expiry_date": expiry_date.isoformat(),
        "license_type": "pro",
        "license": signed_license,
    }


@app.post("/api/payment/create_order")
def create_order(req: CreateOrder, username: str = Depends(get_current_user)):
    if req.plan_type not in PRICING:
        raise HTTPException(status_code=400, detail=f"无效的套餐类型，可选: {list(PRICING.keys())}")
    if req.payment_method not in ("alipay", "wechat"):
        raise HTTPException(status_code=400, detail="无效的支付方式")
    plan = PRICING[req.plan_type]
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        order_no = f"ORD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, order_no, plan_type, amount, payment_method) VALUES (?, ?, ?, ?, ?)",
            (user_id, order_no, req.plan_type, plan["amount"], req.payment_method)
        )
    pay_url = ""
    if _HUPPIAO_PID and _HUPPIAO_SECRET:
        try:
            pay_url = _create_hupijiao_order(order_no, plan["amount"], req.payment_method)
        except Exception as e:
            logger.error(f"创建支付订单失败: {e}")
    logger.info(f"创建订单: {username}, 订单号: {order_no}, 套餐: {req.plan_type}, 金额: {plan['amount']}")
    return {
        "order_no": order_no,
        "amount": plan["amount"],
        "plan_type": req.plan_type,
        "plan_label": plan["label"],
        "pay_url": pay_url,
    }


def _create_hupijiao_order(order_no: str, amount: float, payment_method: str) -> str:
    notify_url = os.environ.get("VIDEOGEN_PAY_NOTIFY_URL", "")
    if not notify_url:
        return ""
    params = {
        "pid": _HUPPIAO_PID,
        "type": "alipay" if payment_method == "alipay" else "wxpay",
        "out_trade_no": order_no,
        "notify_url": notify_url,
        "return_url": "",
        "name": f"VideoGen_{order_no}",
        "money": f"{amount:.2f}",
    }
    sorted_items = sorted(params.items())
    sign_str = "&".join(f"{k}={v}" for k, v in sorted_items if v) + _HUPPIAO_SECRET
    params["sign"] = hashlib.md5(sign_str.encode()).hexdigest()
    params["sign_type"] = "MD5"
    base_url = os.environ.get("VIDEOGEN_HUPPIAO_API", "https://api.xunhupay.com/payment/do.html")
    return f"{base_url}?{urlencode(params)}"


def _verify_hupijiao_sign(params: dict) -> bool:
    if not _HUPPIAO_PID or not _HUPPIAO_SECRET:
        logger.error("支付回调验证失败: 虎皮椒未配置，拒绝所有回调")
        return False
    sign = params.get("sign", "")
    verify_params = {k: v for k, v in params.items() if k not in ("sign", "sign_type") and v}
    sorted_items = sorted(verify_params.items())
    sign_str = "&".join(f"{k}={v}" for k, v in sorted_items) + _HUPPIAO_SECRET
    expected_sign = hashlib.md5(sign_str.encode()).hexdigest()
    return hmac.compare_digest(sign, expected_sign)


@app.post("/api/payment/notify")
async def payment_notify(request: Request):
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}
    trade_no = params.get("trade_no", "")
    out_trade_no = params.get("out_trade_no", "")
    trade_status = params.get("trade_status", "")

    if trade_status != "TRADE_SUCCESS":
        return PlainTextResponse("fail")

    if not _verify_hupijiao_sign(params):
        logger.warning(f"支付回调签名验证失败: order={out_trade_no}, trade={trade_no}")
        return PlainTextResponse("fail")

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, plan_type, status FROM orders WHERE order_no=?", (out_trade_no,))
        order = c.fetchone()
        if not order:
            logger.warning(f"支付回调订单不存在: {out_trade_no}")
            return PlainTextResponse("fail")
        order_id, user_id, plan_type, status = order
        if status == "paid":
            return PlainTextResponse("success")
        plan = PRICING.get(plan_type)
        if not plan:
            logger.error(f"支付回调套餐类型无效: {plan_type}")
            return PlainTextResponse("fail")
        now = datetime.utcnow()
        c.execute(
            "UPDATE orders SET status='paid', trade_no=?, paid_at=? WHERE id=?",
            (trade_no, now.isoformat(), order_id)
        )
        expiry_date = now + timedelta(days=plan["days"])
        c.execute(
            "UPDATE licenses SET license_type='pro', plan_type=?, expiry_date=?, is_active=1 WHERE user_id=?",
            (plan_type, expiry_date.isoformat(), user_id)
        )
    logger.info(f"支付成功: order={out_trade_no}, trade={trade_no}, plan={plan_type}, user_id={user_id}")
    return PlainTextResponse("success")


@app.post("/api/auth/projects/save")
def save_project(project: ProjectSave, username: str = Depends(get_current_user)):
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        c = conn.cursor()
        c.execute(
            "INSERT INTO user_projects (user_id, project_name, audio_file, settings) VALUES (?, ?, ?, ?)",
            (user_id, project.project_name, project.audio_file, json.dumps(project.settings, ensure_ascii=False))
        )
    return {"message": "项目保存成功"}


@app.get("/api/auth/projects/list")
def list_projects(username: str = Depends(get_current_user)):
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        c = conn.cursor()
        c.execute(
            "SELECT id, project_name, audio_file, created_at FROM user_projects WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        )
        projects = c.fetchall()
    return [
        {"id": p[0], "project_name": p[1], "audio_file": p[2], "created_at": p[3]}
        for p in projects
    ]


@app.post("/api/auth/track/usage")
def track_usage(req: UsageTrackRequest, username: str = Depends(get_current_user)):
    if req.action_type not in VALID_ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"无效的操作类型: {req.action_type}")
    with get_db() as conn:
        user_id = _get_user_id(conn, username)
        c = conn.cursor()
        c.execute(
            "INSERT INTO usage_stats (user_id, action_type) VALUES (?, ?)",
            (user_id, req.action_type)
        )
    return {"message": "使用记录已保存"}


@app.get("/api/version/latest")
def get_latest_version(current_version: str = Query(None)):
    versions_file = os.path.join(os.path.dirname(__file__), "versions.json")
    if not os.path.exists(versions_file):
        return {"has_update": False, "message": "暂无版本信息"}
    try:
        with open(versions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"has_update": False, "message": "版本信息读取失败"}
    latest = data.get("latest")
    if not latest:
        return {"has_update": False, "message": "暂无版本信息"}
    if current_version and _compare_versions(current_version, latest["version"]) >= 0:
        return {"has_update": False, "message": "已是最新版本"}
    return {
        "has_update": True,
        "version": latest["version"],
        "release_date": latest["release_date"],
        "download_url": latest["download_url"],
        "file_size": latest.get("file_size", 0),
        "changelog": latest.get("changelog", []),
        "force_update": latest.get("force_update", False),
        "priority": latest.get("priority", "normal"),
    }


@app.get("/api/version/history")
def get_version_history(limit: int = Query(10)):
    versions_file = os.path.join(os.path.dirname(__file__), "versions.json")
    if not os.path.exists(versions_file):
        return []
    try:
        with open(versions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []
    return data.get("history", [])[:limit]


@app.post("/api/version/publish")
def publish_new_version(version_data: VersionData, admin: None = Depends(verify_admin)):
    versions_file = os.path.join(os.path.dirname(__file__), "versions.json")
    data = {"latest": None, "history": []}
    if os.path.exists(versions_file):
        try:
            with open(versions_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = {"latest": None, "history": []}
    if data.get("latest"):
        data["history"].insert(0, data["latest"])
    data["latest"] = version_data.dict()
    with open(versions_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"发布新版本: v{version_data.version}")
    return {"message": f"版本 v{version_data.version} 发布成功", "version": version_data.version}


@app.get("/api/admin/stats")
def get_admin_stats(admin: None = Depends(verify_admin)):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE last_login > ?", ((datetime.utcnow() - timedelta(days=7)).isoformat(),))
        active_users_7d = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM orders WHERE status='paid'")
        paid_orders = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(amount), 0) FROM orders WHERE status='paid'")
        total_revenue = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM licenses WHERE license_type='pro' AND is_active=1")
        pro_users = c.fetchone()[0]
    return {
        "total_users": total_users,
        "active_users_7d": active_users_7d,
        "paid_orders": paid_orders,
        "total_revenue": round(total_revenue, 2),
        "pro_users": pro_users,
    }


@app.get("/api/admin/generate_key")
def generate_license_key_api(plan_type: str = Query("yearly"), admin: None = Depends(verify_admin)):
    if plan_type not in PRICING:
        raise HTTPException(status_code=400, detail=f"无效的套餐类型")
    key = f"VG-{uuid.uuid4().hex[:16].upper()}"
    with get_db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO licenses (license_key, plan_type, is_active) VALUES (?, ?, 1)", (key, plan_type))
    logger.info(f"生成授权码: {key[:8]}..., 套餐: {plan_type}")
    return {"license_key": key, "plan_type": plan_type, "plan_label": PRICING[plan_type]["label"]}


@app.post("/api/admin/assign_key")
def assign_license_key(req: AssignKeyRequest, admin: None = Depends(verify_admin)):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, plan_type FROM orders WHERE order_no=? AND status='paid'", (req.order_no,))
        order = c.fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在或未支付")
        _, user_id, plan_type = order
        plan = PRICING.get(plan_type)
        if not plan:
            raise HTTPException(status_code=400, detail="无效的套餐类型")
        c.execute(
            "SELECT id FROM licenses WHERE license_key=? AND is_active=1",
            (req.license_key,)
        )
        if not c.fetchone():
            raise HTTPException(status_code=404, detail="授权码不存在或已失效")
        expiry_date = datetime.utcnow() + timedelta(days=plan["days"])
        c.execute(
            "UPDATE licenses SET license_type='pro', user_id=?, plan_type=?, expiry_date=?, is_active=1 WHERE license_key=?",
            (user_id, plan_type, expiry_date.isoformat(), req.license_key)
        )
    logger.info(f"分配授权码: {req.license_key[:8]}... -> user_id={user_id}, plan={plan_type}")
    return {"message": "授权码分配成功", "license_key": req.license_key, "expiry_date": expiry_date.isoformat()}


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    if request.url.path != "/health":
        logger.info(f"{request.method} {request.url.path} {response.status_code} {duration:.3f}s")
    return response


init_db()

if __name__ == "__main__":
    import uvicorn
    print(f"🔑 管理员Token: {ADMIN_TOKEN}")
    print(f"🌐 请妥善保存此Token，用于版本发布和管理员接口")
    uvicorn.run(app, host="0.0.0.0", port=8000)
