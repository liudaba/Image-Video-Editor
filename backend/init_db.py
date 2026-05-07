"""短视频生成器 - 后端初始化脚本

在服务器上首次部署时运行，完成以下操作：
1. 创建数据库表
2. 创建管理员账户
3. 生成 HMAC 签名密钥文件
4. 创建首个版本记录
"""

import asyncio
import os
import sys
import secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def init():
    from app.database import init_db, async_session
    from app.models import User, AppVersion
    from app.auth import hash_password
    from app.config import settings

    print("=" * 60)
    print("  短视频生成器 - 后端初始化")
    print("=" * 60)

    print("\n1️⃣ 创建数据库表...")
    await init_db()
    print("   ✅ 数据库表创建完成")

    print("\n2️⃣ 创建管理员账户...")
    async with async_session() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.username == settings.ADMIN_USERNAME))
        if result.scalars().first():
            print(f"   ⏭️ 管理员 {settings.ADMIN_USERNAME} 已存在，跳过")
        else:
            admin = User(
                username=settings.ADMIN_USERNAME,
                email="admin@videogen.local",
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                is_active=True,
                is_admin=True,
            )
            db.add(admin)
            await db.commit()
            print(f"   ✅ 管理员 {settings.ADMIN_USERNAME} 创建成功")

    print("\n3️⃣ 生成 HMAC 签名密钥...")
    key_dir = os.path.join(os.path.dirname(__file__), "keys")
    os.makedirs(key_dir, exist_ok=True)

    verify_key_path = os.path.join(key_dir, ".license_verify_key")
    if os.path.exists(verify_key_path):
        with open(verify_key_path, "r") as f:
            sign_key = f.read().strip()
        print("   ⏭️ 签名密钥已存在，跳过生成")
    else:
        sign_key = secrets.token_hex(32)
        with open(verify_key_path, "w") as f:
            f.write(sign_key)
        print(f"   ✅ 签名密钥已生成: {verify_key_path}")

    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_lines = f.readlines()

        updated = False
        new_lines = []
        for line in env_lines:
            if line.strip().startswith("HMAC_SIGN_KEY="):
                current_val = line.strip().split("=", 1)[1]
                if current_val in ("change-this-after-running-init-db", "dev-hmac-key-change-in-production", ""):
                    new_lines.append(f"HMAC_SIGN_KEY={sign_key}\n")
                    updated = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if updated:
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            print(f"   ✅ 已自动更新 .env 中的 HMAC_SIGN_KEY")
        else:
            print(f"   ⏭️ .env 中 HMAC_SIGN_KEY 已配置，跳过更新")
    else:
        print(f"   ⚠️  未找到 .env 文件，请手动设置 HMAC_SIGN_KEY（密钥已保存至 {verify_key_path}）")

    print(f"   📋 请将签名密钥复制到客户端项目的 .license_verify_key 文件中")

    print("\n4️⃣ 创建首个版本记录...")
    async with async_session() as db:
        result = await db.execute(select(AppVersion))
        if result.scalars().first():
            print("   ⏭️ 版本记录已存在，跳过")
        else:
            version = AppVersion(
                version="2.0.0",
                download_url="",
                file_size=0,
                changelog="首个商业发布版本\n- 完整的音频转视频功能\n- 用户注册登录系统\n- 7天免费试用\n- 专业版订阅",
                priority="normal",
                force_update=False,
                is_active=True,
            )
            db.add(version)
            await db.commit()
            print("   ✅ 首个版本记录创建完成")

    print("\n" + "=" * 60)
    print("  🎉 初始化完成!")
    print("=" * 60)
    print("""
  下一步操作:
  1. 编辑 .env 文件，更新以下配置:
     - HMAC_SIGN_KEY: 设置为上面生成的签名密钥
     - JWT_SECRET_KEY: 设置一个随机长字符串
     - DATABASE_URL: 确认数据库连接信息
     - ADMIN_PASSWORD: 修改管理员默认密码

  2. 启动服务:
     docker compose up -d

  3. 验证服务:
     curl http://<你的服务器IP>/health

  4. 将签名密钥复制到客户端:
     复制 keys/.license_verify_key 的内容到客户端项目的 .license_verify_key 文件
""")


if __name__ == "__main__":
    asyncio.run(init())
