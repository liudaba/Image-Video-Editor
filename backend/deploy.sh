#!/bin/bash
set -e

echo "=========================================="
echo "  短视频生成器 - 一键部署脚本"
echo "=========================================="
echo ""

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEPLOY_DIR"

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

echo "0️⃣ 创建必要目录..."
mkdir -p keys logs backups
echo "   ✅ 目录创建完成"

if [ ! -f "keys/.license_sign_private.pem" ]; then
    echo "   ⚠️  ECDSA 私钥不存在，请从开发机上传 keys/.license_sign_private.pem"
fi
if [ ! -f "keys/.license_verify_pubkey.pem" ]; then
    echo "   ⚠️  ECDSA 公钥不存在，请从开发机上传 keys/.license_verify_pubkey.pem"
fi

echo ""
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
sleep 10

echo ""
echo "3️⃣ 构建并启动 API 服务..."
docker compose up -d --build api
sleep 5

echo ""
echo "4️⃣ 运行数据库初始化..."
docker compose exec api python init_db.py 2>/dev/null || {
    echo "   ⚠️  初始化脚本失败，尝试 Alembic 迁移..."
    docker compose exec api alembic upgrade head 2>/dev/null || {
        echo "   ❌ 数据库迁移失败，请检查日志"
    }
}

echo ""
echo "5️⃣ 配置 Nginx..."
if [ ! -d "/etc/nginx/sites-available" ]; then
    mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled
fi
if [ ! -f "/etc/nginx/sites-available/videogen" ]; then
    cp nginx.conf /etc/nginx/sites-available/videogen
    ln -sf /etc/nginx/sites-available/videogen /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    echo "   ✅ Nginx 配置已安装"
else
    echo "   ⏭️ Nginx 配置已存在"
fi

echo ""
echo "6️⃣ 配置 SSL 证书..."
if command -v certbot &> /dev/null; then
    echo "   🔐 使用 Let's Encrypt 申请证书..."
    certbot --nginx -d api.videogen.com --non-interactive --agree-tos --email admin@videogen.com || {
        echo "   ⚠️  SSL 证书申请失败，请确认域名已解析到此服务器"
    }
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
    echo "   ✅ 自动续期已配置（每天凌晨3点检查）"
else
    echo "   📦 安装 Certbot..."
    apt install -y certbot python3-certbot-nginx
    certbot --nginx -d api.videogen.com --non-interactive --agree-tos --email admin@videogen.com || {
        echo "   ⚠️  SSL 证书申请失败，请确认域名已解析到此服务器"
    }
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'") | crontab -
    echo "   ✅ 自动续期已配置"
fi

nginx -t && systemctl reload nginx || echo "   ⚠️  Nginx 重载失败，请检查配置"

echo ""
echo "7️⃣ 配置 fail2ban..."
if ! command -v fail2ban-client &> /dev/null; then
    apt install -y fail2ban
fi
cat > /etc/fail2ban/jail.local << 'F2BEOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
logpath = /var/log/nginx/videogen_error.log
maxretry = 5
bantime = 1800
F2BEOF
systemctl enable fail2ban
systemctl start fail2ban
echo "   ✅ fail2ban 已配置"

echo ""
echo "8️⃣ 加固 SSH..."
if [ -f /etc/ssh/sshd_config ]; then
    cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
    mkdir -p /etc/ssh/sshd_config.d
    cat > /etc/ssh/sshd_config.d/hardening.conf << 'SSHEOF'
PermitRootLogin no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
SSHEOF
    systemctl restart sshd 2>/dev/null || true
    echo "   ✅ SSH 已加固（已禁用root登录，限制认证尝试）"
else
    echo "   ⏭️ SSH 配置未找到，跳过"
fi

echo ""
echo "9️⃣ 配置防火墙..."
if command -v ufw &> /dev/null; then
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
    echo "   ✅ UFW 防火墙已配置"
elif command -v iptables &> /dev/null; then
    iptables -A INPUT -p tcp --dport 22 -j ACCEPT
    iptables -A INPUT -p tcp --dport 80 -j ACCEPT
    iptables -A INPUT -p tcp --dport 443 -j ACCEPT
    iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
    iptables -P INPUT DROP
    iptables-save > /etc/iptables.rules 2>/dev/null || true
    echo "   ✅ iptables 防火墙已配置"
else
    echo "   ⚠️ 未找到防火墙工具，请手动配置"
fi

echo ""
echo "🔟 安装 systemd 服务..."
if [ -f "videogen-api.service" ]; then
    cp videogen-api.service /etc/systemd/system/videogen-api.service
    systemctl daemon-reload
    systemctl enable videogen-api
    echo "   ✅ systemd 服务已安装（开机自启）"
else
    echo "   ⏭️ systemd 服务文件未找到，跳过"
fi

echo ""
echo "🔍 验证服务..."
sleep 3
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
echo "  1. 确保 keys/.license_sign_private.pem（私钥）和 .license_verify_pubkey.pem（公钥）已就位"
echo "     公钥文件需复制到客户端项目根目录，打包时自动包含"
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
