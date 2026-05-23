# -*- coding: utf-8 -*-
"""
数据库初始化脚本
- 创建所有表
- 创建管理员账号（如不存在）
- 为管理员创建终身 License（如不存在）
"""
import asyncio
import sys
import os

# 确保可以导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, async_session
from app.models import Base, User, License, LicenseType, PlanType
from app.config import settings
from app.auth import hash_password
from sqlalchemy import select


async def init():
    # 1. 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 数据库表结构已就绪")

    # 2. 创建管理员账号
    async with async_session() as db:
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        admin = result.scalar_one_or_none()

        if not admin:
            if not settings.ADMIN_PASSWORD:
                print("❌ ADMIN_PASSWORD 未设置，无法创建管理员账号")
                print("   请在 .env 文件中设置 ADMIN_PASSWORD 后重试")
                return

            admin = User(
                username=settings.ADMIN_USERNAME,
                email=f"{settings.ADMIN_USERNAME}@videogen.local",
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
            db.add(admin)
            await db.flush()
            print(f"✅ 管理员账号已创建: {settings.ADMIN_USERNAME}")
        else:
            print(f"⏭️ 管理员账号已存在: {settings.ADMIN_USERNAME}")

        # 3. 为管理员创建终身 License（如不存在）
        lic_result = await db.execute(select(License).where(License.user_id == admin.id))
        existing_lic = lic_result.scalar_one_or_none()

        if not existing_lic:
            new_lic = License(
                user_id=admin.id,
                license_type=LicenseType.PRO,
                plan_type=PlanType.LIFETIME,
                is_valid=True,
                expiry_date=None,
            )
            db.add(new_lic)
            await db.flush()
            print("✅ 管理员终身授权已创建")
        else:
            print(f"⏭️ 管理员授权已存在: type={existing_lic.license_type}, plan={existing_lic.plan_type}")

        await db.commit()

    await engine.dispose()
    print("\n🎉 数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(init())
