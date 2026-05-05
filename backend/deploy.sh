#!/bin/bash
set -e

echo "=========================================="
echo "  短视频生成器 - 一键部署脚本"
echo "=========================================="
echo ""

if [ ! -f ".env" ]; then
    echo "❌ 未找到 .env 文件，正在从模板创建..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件，填入真实配置后再运行此脚本"
    echo "   必须修改的配置项:"
    echo "   - DATABASE_URL: 数据库连接"
    echo "   - JWT_SECRET_KEY: JWT密钥"
    echo "   - HMAC_SIGN_KEY: 签名密钥"
    echo "   - ADMIN_PASSWORD: 管理员密码"
    echo ""
    echo "   生成随机密钥: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
fi

echo "1️⃣ 安装 Docker（如果未安装）..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "   ✅ Docker 安装完成"
else
    echo "   ⏭️ Docker 已安装"
fi

echo ""
echo "2️⃣ 启动数据库和 Redis..."
docker compose up -d db redis
echo "   ⏳ 等待数据库就绪..."
sleep 5

echo ""
echo "3️⃣ 构建并启动 API 服务..."
docker compose up -d --build api
sleep 3

echo ""
echo "4️⃣ 运行数据库迁移（Alembic）..."
docker compose exec api alembic upgrade head 2>/dev/null || {
    echo "   ⚠️  Alembic 迁移失败，尝试直接初始化..."
    docker compose exec api python init_db.py
}

echo ""
echo "5️⃣ 配置 Nginx..."
if [ ! -f "/etc/nginx/sites-available/videogen" ]; then
    cp nginx.conf /etc/nginx/sites-available/videogen
    ln -sf /etc/nginx/sites-available/videogen /etc/nginx/sites-enabled/
    echo "   ✅ Nginx 配置已安装"
else
    echo "   ⏭️ Nginx 配置已存在"
fi

echo ""
echo "6️⃣ 配置 SSL 证书..."
SSL_DIR="/etc/nginx/ssl"
if [ ! -f "$SSL_DIR/videogen.com.pem" ]; then
    if command -v certbot &> /dev/null; then
        echo "   🔐 使用 Let's Encrypt 申请证书..."
        certbot --nginx -d api.videogen.com --non-interactive --agree-tos --email admin@videogen.com
        echo "   ✅ SSL 证书已安装"
        echo "   📋 设置自动续期..."
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
        echo "   ✅ 自动续期已配置（每天凌晨3点检查）"
    else
        echo "   📦 安装 Certbot..."
        apt install -y certbot python3-certbot-nginx
        certbot --nginx -d api.videogen.com --non-interactive --agree-tos --email admin@videogen.com
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
        echo "   ✅ SSL 证书已安装并配置自动续期"
    fi
else
    echo "   ✅ SSL 证书已就绪"
fi

nginx -t 2>/dev/null && systemctl reload nginx 2>/dev/null || true

echo ""
echo "7️⃣ 验证服务..."
sleep 2
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ API 服务运行正常"
else
    echo "   ❌ API 服务未响应，请检查日志:"
    echo "   docker compose logs api"
fi

echo ""
echo "=========================================="
echo "  🎉 部署完成!"
echo "=========================================="
echo ""
echo "  API 地址: https://api.videogen.com"
echo "  健康检查: https://api.videogen.com/health"
echo ""
echo "  管理员登录: admin / (你在.env中设置的密码)"
echo ""
echo "  下一步:"
echo "  1. 将 keys/.license_verify_key 的内容复制到客户端的 .license_verify_key"
echo "  2. 运行 python obfuscate_build.py 混淆核心模块"
echo "  3. 运行 python 01build_exe.py 打包客户端"
echo "  4. 在管理后台创建版本记录"
echo ""
echo "  常用命令:"
echo "  - 查看日志: docker compose logs -f api"
echo "  - 重启服务: docker compose restart api"
echo "  - 停止服务: docker compose down"
echo "  - 数据库迁移: docker compose exec api alembic upgrade head"
echo "  - 查看迁移历史: docker compose exec api alembic history"
