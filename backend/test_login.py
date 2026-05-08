import sys
import os
import asyncio
import hashlib

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__)))

from app.auth import verify_password, hash_password

def test_password():
    # 测试密码验证
    test_passwords = ["admin123", "change-this-default-password", "admin"]
    
    # 获取数据库中的密码哈希
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), 'videogen.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('SELECT hashed_password FROM users WHERE username=?', ('admin',))
    result = cursor.fetchone()
    
    if result:
        stored_hash = result[0]
        print("测试可能的密码:")
        for pwd in test_passwords:
            is_valid = verify_password(pwd, stored_hash)
            print(f"  密码: {pwd} -> {'✓ 匹配' if is_valid else '✗ 不匹配'}")
    else:
        print("未找到admin用户")
    
    conn.close()

async def test_login():
    test_password()

if __name__ == "__main__":
    asyncio.run(test_login())