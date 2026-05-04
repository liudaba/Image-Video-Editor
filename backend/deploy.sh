#!/bin/bash
# ============================================================
# 短视频生成器 - 一键部署脚本
# 适用于: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
# 使用方法: sudo bash deploy.sh
# ============================================================

set -e

APP_DIR="/opt/videogen"
BACKEND_DIR="$APP_DIR/backend"
LOG_DIR="/var/log/videogen"
PYTHON_VERSION="3.11"

echo "============================================"
echo "  短视频生成器 - 后端部署脚本"
echo "============================================"
echo ""

# 检查root权限
if [ "$EUID" -ne 0 ]; then
    echo "❌ 请使用 sudo 运行此脚本"
    exit 1
fi

# 1. 安装系统依赖
echo "📦 [1/7] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx curl > /dev/null 2>&1
echo "  ✅ 系统依赖安装完成"

# 2. 创建目录
echo "📁 [2/7] 创建目录结构..."
mkdir -p $APP_DIR
mkdir -p $BACKEND_DIR
mkdir -p $LOG_DIR
chown -R www-data:www-data $LOG_DIR
echo "  ✅ 目录创建完成"

# 3. 复制后端代码
echo "📋 [3/7] 复制后端代码..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp -f "$SCRIPT_DIR/server.py" "$BACKEND_DIR/"
cp -f "$SCRIPT_DIR/requirements.txt" "$BACKEND_DIR/"
cp -f "$SCRIPT_DIR/nginx_videogen.conf" "$BACKEND_DIR/"
cp -f "$SCRIPT_DIR/videogen.service" "$BACKEND_DIR/"
cp -f "$SCRIPT_DIR/.env.example" "$BACKEND_DIR/.env.example"

if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo "  ⚠️  已创建 .env 文件，请编辑填入真实配置！"
fi
echo "  ✅ 代码复制完成"

# 4. 创建Python虚拟环境并安装依赖
echo "🐍 [4/7] 安装Python依赖..."
if [ ! -d "$BACKEND_DIR/venv" ]; then
    python3 -m venv "$BACKEND_DIR/venv"
fi
$BACKEND_DIR/venv/bin/pip install -q --upgrade pip
$BACKEND_DIR/venv/bin/pip install -q -r "$BACKEND_DIR/requirements.txt"
echo "  ✅ Python依赖安装完成"

# 5. 初始化密钥
echo "🔑 [5/7] 生成密钥..."
cd $BACKEND_DIR

# 生成JWT密钥
if ! grep -q "VIDEOGEN_SECRET_KEY=." .env; then
    JWT_KEY=$($BACKEND_DIR/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))")
    sed -i "s|^VIDEOGEN_SECRET_KEY=.*|VIDEOGEN_SECRET_KEY=$JWT_KEY|" .env
    echo "  ✅ JWT密钥已生成"
else
    echo "  ⏭️  JWT密钥已存在，跳过"
fi

# 生成授权签名密钥
if ! grep -q "VIDEOGEN_LICENSE_SIGN_KEY=." .env; then
    SIGN_KEY=$($BACKEND_DIR/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))")
    sed -i "s|^VIDEOGEN_LICENSE_SIGN_KEY=.*|VIDEOGEN_LICENSE_SIGN_KEY=$SIGN_KEY|" .env
    echo "  ✅ 授权签名密钥已生成"
else
    echo "  ⏭️  授权签名密钥已存在，跳过"
fi

# 生成管理员Token
if ! grep -q "VIDEOGEN_ADMIN_TOKEN=." .env; then
    ADMIN_KEY=$($BACKEND_DIR/venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s|^VIDEOGEN_ADMIN_TOKEN=.*|VIDEOGEN_ADMIN_TOKEN=$ADMIN_KEY|" .env
    echo "  ✅ 管理员Token已生成"
else
    echo "  ⏭️  管理员Token已存在，跳过"
fi

# 生成客户端验证密钥文件
SIGN_KEY_VALUE=$(grep "^VIDEOGEN_LICENSE_SIGN_KEY=" .env | cut -d= -f2)
echo "$SIGN_KEY_VALUE" > "$BACKEND_DIR/.license_verify_key"
echo "  ✅ 客户端验证密钥文件已生成"

# 设置文件权限
chown -R www-data:www-data $BACKEND_DIR
chmod 600 $BACKEND_DIR/.env
chmod 600 $BACKEND_DIR/.secret_key 2>/dev/null || true
chmod 600 $BACKEND_DIR/.license_sign_key 2>/dev/null || true
chmod 600 $BACKEND_DIR/.license_verify_key

# 6. 配置systemd服务
echo "⚙️  [6/7] 配置系统服务..."
cp "$BACKEND_DIR/videogen.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable videogen
systemctl restart videogen
sleep 2
if systemctl is-active --quiet videogen; then
    echo "  ✅ 服务启动成功"
else
    echo "  ❌ 服务启动失败，请检查日志: journalctl -u videogen"
    exit 1
fi

# 7. 配置Nginx
echo "🌐 [7/7] 配置Nginx反向代理..."
cp "$BACKEND_DIR/nginx_videogen.conf" /etc/nginx/sites-available/videogen
ln -sf /etc/nginx/sites-available/videogen /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t 2>/dev/null
if [ $? -eq 0 ]; then
    systemctl reload nginx
    echo "  ✅ Nginx配置完成"
else
    echo "  ⚠️  Nginx配置有误，请手动检查"
fi

echo ""
echo "============================================"
echo "  ✅ 部署完成！"
echo "============================================"
echo ""
echo "📋 重要信息:"
echo ""

ADMIN_TOKEN=$(grep "^VIDEOGEN_ADMIN_TOKEN=" .env | cut -d= -f2)
echo "  🔑 管理员Token: $ADMIN_TOKEN"
echo ""

SIGN_KEY=$(grep "^VIDEOGEN_LICENSE_SIGN_KEY=" .env | cut -d= -f2)
echo "  🔐 授权签名密钥: $SIGN_KEY"
echo ""
echo "  📋 客户端打包所需文件:"
echo "     将以下文件从服务器复制到你的开发电脑项目根目录:"
echo "     scp root@$(hostname -I | awk '{print $1}'):$BACKEND_DIR/.license_verify_key  ."
echo ""

echo "  📡 API地址: https://api.videogen.com"
echo "  🏥 健康检查: https://api.videogen.com/health"
echo ""

echo "📝 下一步操作:"
echo "  1. 配置DNS: 将 api.videogen.com 指向本服务器IP"
echo "  2. 申请HTTPS证书: certbot --nginx -d api.videogen.com"
echo "  3. 编辑 .env 填入虎皮椒支付配置: nano $BACKEND_DIR/.env"
echo "  4. 重启服务: systemctl restart videogen"
echo "  5. 将 .license_verify_key 文件复制到客户端打包目录"
echo ""
echo "🔧 常用命令:"
echo "  查看日志: journalctl -u videogen -f"
echo "  重启服务: systemctl restart videogen"
echo "  查看状态: systemctl status videogen"
echo ""
