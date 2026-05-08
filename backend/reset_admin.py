import sqlite3
import hashlib
import os
import sys

# 将backend目录添加到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__)))

from app.auth import hash_password

def reset_admin_password():
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'videogen.db')
    
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return False

    try:
        # 连接到SQLite数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查admin用户是否存在
        cursor.execute("SELECT id, username FROM users WHERE username = 'admin'")
        result = cursor.fetchone()

        if result:
            # 如果admin用户存在，更新其密码
            admin_id, username = result
            new_password = "admin123"
            hashed_password = hash_password(new_password)
            
            cursor.execute(
                "UPDATE users SET hashed_password = ? WHERE username = ?",
                (hashed_password, 'admin')
            )
            print(f"已更新用户 '{username}' (ID: {admin_id}) 的密码为: {new_password}")
        else:
            # 如果admin用户不存在，创建一个
            new_password = "admin123"
            hashed_password = hash_password(new_password)
            
            cursor.execute(
                """INSERT INTO users 
                (username, email, hashed_password, is_active, is_admin, created_at, updated_at) 
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                ('admin', 'admin@videogen.local', hashed_password, True, True)
            )
            print(f"已创建新管理员用户: admin, 密码: {new_password}")

        # 提交更改并关闭连接
        conn.commit()
        conn.close()
        print("数据库更新完成！")
        print("现在您可以使用以下凭据登录:")
        print("- 用户名: admin")
        print("- 密码: admin123")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        return False

if __name__ == "__main__":
    reset_admin_password()