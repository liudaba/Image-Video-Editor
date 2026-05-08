import sqlite3
import os
import sys

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__)))

def check_users():
    # 数据库路径
    db_path = os.path.join(os.path.dirname(__file__), 'videogen.db')
    
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return

    try:
        # 连接到SQLite数据库
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 查询所有用户
        cursor.execute('SELECT id, username, email, is_admin, created_at, updated_at FROM users')
        users = cursor.fetchall()

        print('数据库中存在的用户:')
        if users:
            for user in users:
                print(f'  ID: {user[0]}, 用户名: {user[1]}, 邮箱: {user[2]}, 管理员: {bool(user[3])}, 创建时间: {user[4]}')
        else:
            print('  没有找到任何用户')

        # 检查admin用户是否存在
        cursor.execute('SELECT COUNT(id) FROM users WHERE username=?', ('admin',))
        admin_count = cursor.fetchone()[0]
        print(f'\n管理员用户数量: {admin_count}')

        # 检查admin用户密码字段
        cursor.execute('SELECT hashed_password FROM users WHERE username=?', ('admin',))
        pwd_result = cursor.fetchone()
        if pwd_result:
            print(f'admin用户密码哈希长度: {len(pwd_result[0]) if pwd_result[0] else 0}')
        else:
            print('admin用户不存在')

        # 关闭连接
        conn.close()
        
    except Exception as e:
        print(f"错误: {str(e)}")

if __name__ == "__main__":
    check_users()