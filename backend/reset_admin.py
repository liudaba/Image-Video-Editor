import sqlite3
import hashlib
import os
import sys
import secrets
import string

sys.path.append(os.path.join(os.path.dirname(__file__)))

from app.auth import hash_password

def _generate_secure_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = ''.join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        if has_upper and has_lower and has_digit:
            return pwd

def reset_admin_password():
    db_path = os.path.join(os.path.dirname(__file__), 'videogen.db')
    
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, username FROM users WHERE username = 'admin'")
        result = cursor.fetchone()

        new_password = _generate_secure_password()
        hashed_password = hash_password(new_password)

        if result:
            admin_id, username = result
            cursor.execute(
                "UPDATE users SET hashed_password = ? WHERE username = ?",
                (hashed_password, 'admin')
            )
            print(f"已更新用户 '{username}' (ID: {admin_id}) 的密码")
        else:
            cursor.execute(
                """INSERT INTO users 
                (username, email, hashed_password, is_active, is_admin, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                ('admin', 'admin@videogen.local', hashed_password, True, True)
            )
            print("已创建新管理员用户: admin")

        conn.commit()
        conn.close()
        print("数据库更新完成！")
        print("请妥善保管以下凭据（仅显示一次）:")
        print(f"- 用户名: admin")
        print(f"- 密码: {new_password}")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        return False

if __name__ == "__main__":
    reset_admin_password()