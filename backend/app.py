"""
短视频生成器 - 用户账户系统后端
FastAPI实现,支持用户注册、登录、数据同步
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from passlib.hash import bcrypt
import sqlite3
import jwt
from datetime import datetime, timedelta
from typing import Optional

app = FastAPI(title="VideoGen User System")

# 配置
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 数据库初始化
def init_db():
    conn = sqlite3.connect('users.db')
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
        CREATE TABLE IF NOT EXISTS user_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            project_name TEXT,
            audio_file TEXT,
            settings TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action_type TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

# 数据模型
class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class ProjectSave(BaseModel):
    project_name: str
    audio_file: str
    settings: dict

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

# API路由
@app.post("/api/register")
def register(user: UserRegister):
    """用户注册"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # 检查用户名是否已存在
    c.execute("SELECT id FROM users WHERE username=?", (user.username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # 检查邮箱是否已存在
    c.execute("SELECT id FROM users WHERE email=?", (user.email,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 创建新用户
    password_hash = bcrypt.hash(user.password)
    c.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (user.username, user.email, password_hash)
    )
    conn.commit()
    conn.close()
    
    return {"message": "Registration successful", "username": user.username}

@app.post("/api/login")
def login(user: UserLogin):
    """用户登录"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT id, username, password_hash FROM users WHERE username=?", (user.username,))
    result = c.fetchone()
    conn.close()
    
    if not result or not bcrypt.verify(user.password, result[2]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 生成token
    access_token = create_access_token(data={"sub": user.username})
    
    # 更新最后登录时间
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET last_login=? WHERE username=?", 
              (datetime.utcnow(), user.username))
    conn.commit()
    conn.close()
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "username": user.username
    }

@app.post("/api/projects/save")
def save_project(project: ProjectSave, username: str = Depends(get_current_user)):
    """保存项目"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # 获取用户ID
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user_id = c.fetchone()[0]
    
    # 保存项目
    import json
    c.execute(
        "INSERT INTO user_projects (user_id, project_name, audio_file, settings) VALUES (?, ?, ?, ?)",
        (user_id, project.project_name, project.audio_file, json.dumps(project.settings))
    )
    conn.commit()
    conn.close()
    
    return {"message": "Project saved successfully"}

@app.get("/api/projects/list")
def list_projects(username: str = Depends(get_current_user)):
    """列出用户项目"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user_id = c.fetchone()[0]
    
    c.execute(
        "SELECT id, project_name, audio_file, created_at FROM user_projects WHERE user_id=? ORDER BY created_at DESC",
        (user_id,)
    )
    projects = c.fetchall()
    conn.close()
    
    return [
        {
            "id": p[0],
            "project_name": p[1],
            "audio_file": p[2],
            "created_at": p[3]
        }
        for p in projects
    ]

@app.post("/api/track/usage")
def track_usage(action_type: str, username: str = Depends(get_current_user)):
    """记录使用统计"""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    user_id = c.fetchone()[0]
    
    c.execute(
        "INSERT INTO usage_stats (user_id, action_type) VALUES (?, ?)",
        (user_id, action_type)
    )
    conn.commit()
    conn.close()
    
    return {"message": "Usage tracked"}

# 启动时初始化数据库
init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
