"""重置管理员密码

在服务器上运行: python reset_admin_password.py <新密码>
例如: python reset_admin_password.py Admin123456
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import async_session
from app.models import User
from app.auth import hash_password
from app.config import settings
from sqlalchemy import select


async def reset_password(new_password: str):
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        admin = result.scalar_one_or_none()

        if not admin:
            print(f"❌ 管理员账号不存在: {settings.ADMIN_USERNAME}")
            return

        old_hash = admin.hashed_password
        admin.hashed_password = hash_password(new_password)
        await db.commit()

        print(f"✅ 管理员密码已重置")
        print(f"   用户名: {admin.username}")
        print(f"   新密码: {new_password}")
        print(f"   旧哈希: {old_hash[:20]}...")
        print(f"   新哈希: {admin.hashed_password[:20]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python reset_admin_password.py <新密码>")
        print("例如: python reset_admin_password.py Admin123456")
        sys.exit(1)

    new_pwd = sys.argv[1]
    asyncio.run(reset_password(new_pwd))
