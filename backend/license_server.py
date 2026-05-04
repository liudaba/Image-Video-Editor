# -*- coding: utf-8 -*-
"""
短视频生成器 - 授权验证后端API
处理用户注册、登录、试用管理、付费订阅
"""

import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from passlib.hash import bcrypt
from pydantic import BaseModel, field_validator

app = FastAPI(title="VideoGen License Server")

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

DB_PATH = os.environ.get("VIDEOGEN_DB_PATH", os.path.join(os.path.dirname(__file__), "license.db"))

_login_attempts = defaultdict(list)
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = 300


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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少8位")
    if not re.search(r'[A-Z]', password):
        raise HTTPException(status_code=400, detail="密码必须包含至少一个大写字母")
    if not re.search(r'[a-z]', password):
        raise HTTPException(status_code=400, detail="密码必须包含至少一个小写字母")
    if not re.search(r'\d', password):
        raise HTTPException(status_code=400, detail="密码必须包含至少一个数字")


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


def generate_license_key():
    return f"VG-{uuid.uuid4().hex[:16].upper()}"


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
        trial_end = now + timedelta(days=7)
        c.execute(
            "INSERT INTO licenses (user_id, license_type, trial_start, trial_end) VALUES (?, 'trial', ?, ?)",
            (user_id, now.isoformat(), trial_end.isoformat())
        )
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
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        user_id, username, _ = result
        c.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.utcnow().isoformat(), user_id))
        access_token = create_access_token(data={"sub": username})
    _login_attempts.pop(user.username, None)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": username
    }


@app.post("/api/license/activate")
def activate_license(req: LicenseActivate, username: str = Depends(get_current_user)):
    license_key = req.license_key.strip()
    if not license_key:
        raise HTTPException(status_code=400, detail="授权码不能为空")
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        user_id = row[0]
        c.execute(
            "SELECT id, user_id FROM licenses WHERE license_key=? AND is_active=1",
            (license_key,)
        )
        lic = c.fetchone()
        if not lic:
            raise HTTPException(status_code=404, detail="授权码无效或已过期")
        if lic[1] != user_id:
            raise HTTPException(status_code=403, detail="该授权码不属于当前用户")
        expiry_date = datetime.utcnow() + timedelta(days=365)
        c.execute(
            "UPDATE licenses SET license_type='pro', expiry_date=? WHERE id=?",
            (expiry_date.isoformat(), lic[0])
        )
    return {"message": "授权激活成功", "expiry_date": expiry_date.isoformat(), "license_type": "pro"}


@app.post("/api/payment/create_order")
def create_order(req: CreateOrder, username: str = Depends(get_current_user)):
    if req.plan_type not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="无效的套餐类型")
    if req.payment_method not in ("alipay", "wechat"):
        raise HTTPException(status_code=400, detail="无效的支付方式")
    amount = 29.9 if req.plan_type == "monthly" else 299.0
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        user_id = row[0]
        order_no = f"ORD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"
        c.execute(
            "INSERT INTO orders (user_id, order_no, plan_type, amount, payment_method) VALUES (?, ?, ?, ?, ?)",
            (user_id, order_no, req.plan_type, amount, req.payment_method)
        )
    return {"order_no": order_no, "amount": amount, "plan_type": req.plan_type}


@app.get("/api/user/license_status")
def get_license_status(username: str = Depends(get_current_user)):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户不存在")
        user_id = row[0]
        c.execute(
            "SELECT license_type, trial_start, trial_end, expiry_date, is_active FROM licenses WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        lic = c.fetchone()
    if not lic:
        return {"license_type": "none", "is_valid": False, "days_left": 0}
    license_type, trial_start, trial_end, expiry_date, is_active = lic
    now = datetime.utcnow()
    if license_type == "trial" and trial_end:
        try:
            trial_end_dt = datetime.fromisoformat(trial_end)
            days_left = max(0, (trial_end_dt - now).days)
            return {"license_type": "trial", "days_left": days_left, "is_valid": days_left > 0}
        except (ValueError, TypeError):
            pass
    if license_type == "pro" and expiry_date:
        try:
            expiry_dt = datetime.fromisoformat(expiry_date)
            days_left = max(0, (expiry_dt - now).days)
            return {"license_type": "pro", "days_left": days_left, "is_valid": days_left > 0 and is_active}
        except (ValueError, TypeError):
            pass
    return {"license_type": license_type, "is_valid": False, "days_left": 0}


init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
