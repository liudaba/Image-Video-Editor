后期我对软件进行更新优化"""
短视频生成器 - 授权验证后端API
处理用户注册、登录、试用管理、付费订阅
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from passlib.hash import bcrypt
import jwt
import sqlite3
from datetime import datetime, timedelta
from typing import Optional
import uuid

app = FastAPI(title="VideoGen License Server")

# 配置
SECRET_KEY = "your-super-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天

# 数据库初始化
def init_db():
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    # 用户表
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
    
    # 授权表
    c.execute('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            license_type TEXT DEFAULT 'trial',  -- trial, pro
            trial_start TIMESTAMP,
            trial_end TIMESTAMP,
            expiry_date TIMESTAMP,
            license_key TEXT UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # 订单表
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            order_no TEXT UNIQUE,
            plan_type TEXT,  -- monthly, yearly
            amount REAL,
            status TEXT DEFAULT 'pending',  -- pending, paid, cancelled
            payment_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# 数据模型
class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class LicenseActivate(BaseModel):
    license_key: str

class CreateOrder(BaseModel):
    plan_type: str  # monthly or yearly
    payment_method: str  # alipay or wechat

# 辅助函数
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def generate_license_key():
    """生成授权密钥"""
    return f"VG-{uuid.uuid4().hex[:16].upper()}"

# API路由
@app.post("/api/auth/register")
def register(user: UserRegister):
    """用户注册"""
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    # 检查用户名是否已存在
    c.execute("SELECT id FROM users WHERE username=?", (user.username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 检查邮箱是否已存在
    c.execute("SELECT id FROM users WHERE email=?", (user.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    # 创建用户
    password_hash = bcrypt.hash(user.password)
    c.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (user.username, user.email, password_hash)
    )
    user_id = c.lastrowid
    
    # 创建试用授权(7天)
    now = datetime.utcnow()
    trial_end = now + timedelta(days=7)
    c.execute(
        "INSERT INTO licenses (user_id, license_type, trial_start, trial_end) VALUES (?, 'trial', ?, ?)",
        (user_id, now, trial_end)
    )
    
    conn.commit()
    conn.close()
    
    return {"message": "注册成功", "username": user.username}

@app.post("/api/auth/login")
def login(user: UserLogin):
    """用户登录"""
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    c.execute("SELECT id, username, password_hash FROM users WHERE username=?", (user.username,))
    result = c.fetchone()
    
    if not result or not bcrypt.verify(user.password, result[2]):
        conn.close()
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    user_id, username, _ = result
    
    # 更新最后登录时间
    c.execute("UPDATE users SET last_login=? WHERE id=?", (datetime.utcnow(), user_id))
    conn.commit()
    conn.close()
    
    # 生成token
    access_token = create_access_token(data={"sub": username})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": username
    }

@app.post("/api/license/activate")
def activate_license(request: LicenseActivate, username: str = Depends(get_current_user)):
    """激活专业版授权"""
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    # 查询授权
    c.execute("""
        SELECT l.id, l.user_id, u.username 
        FROM licenses l 
        JOIN users u ON l.user_id = u.id 
        WHERE l.license_key = ? AND l.is_active = 1
    """, (request.license_key,))
    
    result = c.fetchone()
    
    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="授权码无效或已过期")
    
    license_id, user_id, license_username = result
    
    # 检查是否是当前用户
    if license_username != username:
        conn.close()
        raise HTTPException(status_code=403, detail="该授权码不属于当前用户")
    
    # 更新为专业版,有效期1年
    expiry_date = datetime.utcnow() + timedelta(days=365)
    c.execute(
        "UPDATE licenses SET license_type='pro', expiry_date=? WHERE id=?",
        (expiry_date, license_id)
    )
    conn.commit()
    conn.close()
    
    return {
        "message": "授权激活成功",
        "expiry_date": expiry_date.isoformat(),
        "license_type": "pro"
    }

@app.post("/api/payment/create_order")
def create_order(request: CreateOrder, username: str = Depends(get_current_user)):
    """创建支付订单"""
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    # 获取用户ID
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user_id = c.fetchone()[0]
    
    # 计算价格
    if request.plan_type == 'monthly':
        amount = 29.9
    elif request.plan_type == 'yearly':
        amount = 299.0
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="无效的套餐类型")
    
    # 生成订单号
    order_no = f"ORD{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"
    
    # 创建订单
    c.execute(
        "INSERT INTO orders (user_id, order_no, plan_type, amount, payment_method) VALUES (?, ?, ?, ?, ?)",
        (user_id, order_no, request.plan_type, amount, request.payment_method)
    )
    conn.commit()
    
    # TODO: 集成支付宝/微信支付SDK,生成支付二维码或链接
    # 这里返回模拟数据
    payment_url = f"https://pay.example.com/{order_no}"
    
    conn.close()
    
    return {
        "order_no": order_no,
        "amount": amount,
        "payment_url": payment_url,
        "plan_type": request.plan_type
    }

@app.get("/api/user/license_status")
def get_license_status(username: str = Depends(get_current_user)):
    """获取用户授权状态"""
    conn = sqlite3.connect('license.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user_id = c.fetchone()[0]
    
    c.execute("""
        SELECT license_type, trial_start, trial_end, expiry_date, is_active
        FROM licenses 
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
    """, (user_id,))
    
    result = c.fetchone()
    conn.close()
    
    if not result:
        raise HTTPException(status_code=404, detail="未找到授权信息")
    
    license_type, trial_start, trial_end, expiry_date, is_active = result
    
    now = datetime.utcnow()
    
    if license_type == 'trial':
        trial_end_dt = datetime.fromisoformat(trial_end)
        days_left = (trial_end_dt - now).days
        return {
            "license_type": "trial",
            "days_left": max(0, days_left),
            "is_valid": days_left > 0
        }
    elif license_type == 'pro':
        expiry_dt = datetime.fromisoformat(expiry_date)
        days_left = (expiry_dt - now).days
        return {
            "license_type": "pro",
            "days_left": max(0, days_left),
            "is_valid": days_left > 0 and is_active
        }

# 启动时初始化数据库
init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
