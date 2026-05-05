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
echo "4️⃣ 初始化数据库（创建表+管理员+版本记录）..."
docker compose exec api python init_db.py

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
echo "6️⃣ 检查 SSL 证书..."
SSL_DIR="/etc/nginx/ssl"
if [ ! -f "$SSL_DIR/videogen.com.pem" ]; then
    echo "   ⚠️  未找到 SSL 证书，请手动安装:"
    echo "   mkdir -p $SSL_DIR"
    echo "   cp 你的证书.pem $SSL_DIR/videogen.com.pem"
    echo "   cp 你的密钥.key $SSL_DIR/videogen.com.key"
    echo ""
    echo "   或使用 Let's Encrypt 免费证书:"
    echo "   apt install certbot python3-certbot-nginx"
    echo "   certbot --nginx -d api.videogen.com"
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
echo "  API 文档: https://api.videogen.com/docs"
echo ""
echo "  管理员登录: admin / (你在.env中设置的密码)"
echo ""
echo "  下一步:"
echo "  1. 将 keys/.license_verify_key 的内容复制到客户端的 .license_verify_key"
echo "  2. 打包客户端并分发"
echo "  3. 在管理后台创建版本记录"
echo ""
echo "  常用命令:"
echo "  - 查看日志: docker compose logs -f api"
echo "  - 重启服务: docker compose restart api"
echo "  - 停止服务: docker compose down"
