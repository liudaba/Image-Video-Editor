# 项目操作规则

---

## 一、项目架构概览

| 端 | 技术栈 | 说明 |
|---|--------|------|
| 客户端 | Python + tkinter | `video_generator/` 目录，打包为 exe 分发 |
| 后端 | FastAPI + PostgreSQL + Redis | `backend/` 目录，Docker 容器部署 |
| 管理后台 | Jinja2 模板 | `backend/app/templates/`，与后端同服务 |

**三端核心数据流**：客户端登录/激活/心跳 → 后端 API 验证+签名 → 管理后台展示状态

---

## 二、端口与服务管理

1. **8000 端口是用户专用的**（语音克隆项目后端），本地测试使用 **9000** 端口
2. **不得随意终止任何运行中的服务**（本地或云端）
3. **需要重启服务时，必须先征求用户同意**
4. **端口冲突时优先换端口，不 kill 进程**

---

## 三、本地测试环境

### 3.1 前置依赖（必须安装）

本地测试后端前，必须确保以下服务已安装并运行：

| 依赖 | 用途 | 安装验证命令 |
|------|------|-------------|
| PostgreSQL 16 | 主数据库 | `& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "SELECT version();"` |
| Redis | 缓存/会话 | `redis-cli ping`（应返回 PONG） |
| Python 3.11+ | 运行后端 | `python --version` |
| asyncpg | PostgreSQL 异步驱动 | `python -c "import asyncpg; print('OK')"` |
| psycopg2-binary | PostgreSQL 同步驱动 | `python -c "import psycopg2; print('OK')"` |
| email-validator | 邮箱验证 | `python -c "import email_validator; print('OK')"` |

**安装命令参考**（Windows）：
```powershell
# PostgreSQL（winget 安装）
winget install PostgreSQL.PostgreSQL.16

# Redis（推荐用 Memurai 或 WSL）
# 安装后确保 redis-server 在默认端口 6379 运行

# Python 依赖（在 backend 目录下）
pip install -r requirements.txt
```

### 3.2 本地数据库初始化

```powershell
# 1. 创建数据库和用户（用 psql，需输入 postgres 密码）
$env:PGPASSWORD = "postgres"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -w -c "CREATE USER videogen WITH PASSWORD 'videogen';"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -w -c "CREATE DATABASE videogen OWNER videogen;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -w -c "GRANT ALL PRIVILEGES ON DATABASE videogen TO videogen;"

# 2. 创建表（在 backend 目录下）
python init_db.py
```

### 3.3 本地测试流程

```powershell
# 1. 确认 PostgreSQL 和 Redis 服务正在运行
# 2. 进入 backend 目录
cd f:\shipinshengcheng\Image-Video-Editor\backend

# 3. 启动后端（端口 9000，避免与 8000 冲突）
uvicorn app.main:app --host 0.0.0.0 --port 9000

# 4. 客户端 config.json 中 api_base_url 临时改为 http://localhost:9000
# 5. 测试完毕后：
#    - 关停 uvicorn 进程（Ctrl+C）
#    - config.json 的 api_base_url 恢复为 http://8.141.101.155
```

### 3.4 本地环境配置文件

本地测试使用 `backend/.env` 文件，关键配置：
```
DATABASE_URL=postgresql+asyncpg://videogen:videogen@localhost:5432/videogen
REDIS_URL=redis://localhost:6379/0
VIDEOGEN_ENV=development
LOG_LEVEL=DEBUG
```

> **注意**：本地和云端共用 PostgreSQL，但本地连接 `localhost:5432`，云端连接 Docker 内部网络。本地 `.env` 不会影响云端。

### 3.5 常见测试问题排查

| 问题 | 原因 | 解决方法 |
|------|------|---------|
| 测试卡住无响应 | PostgreSQL 或 Redis 未启动 | 启动对应服务 |
| `ModuleNotFoundError: No module named 'asyncpg'` | 依赖未安装 | `pip install asyncpg` |
| `ImportError: email-validator is not installed` | 依赖未安装 | `pip install email-validator` |
| psql 需要手动输入密码导致脚本卡住 | 交互式密码提示 | 使用 `$env:PGPASSWORD = "密码"` 环境变量 |
| 连接被拒绝 | PostgreSQL 服务未启动或端口不对 | 检查服务状态和端口 |
| `asyncpg.exceptions.InvalidCatalogNameError` | 数据库 `videogen` 不存在 | 执行 3.2 节的初始化步骤 |

---

## 四、远程服务器与部署

### 4.1 服务器信息

- **SSH**: `ssh root@8.141.101.155`（密码见 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt`）
- **管理后台**: `http://8.141.101.155/admin/login`（账号 `admin` / `Admin123456!`）
- **后端容器**: `videogen-api-1`，项目目录 `/root/videogen/`
- **绑定挂载**: `./app:/app/app`，修改宿主机文件后重启容器即生效

### 4.2 代码同步（一键同步，禁止手动分步）

**必须使用 `sync_to_server.py`**，自动完成：上传文件 → 重启容器 → 健康检查。

```bash
python sync_to_server.py          # 全量同步
python sync_to_server.py --code   # 仅代码文件
python sync_to_server.py --templates  # 仅模板文件
```

**同步前必须先提交推送**：`git add -A && git commit -m "xxx" && git push origin master`

> **绝对禁止**手动 scp 上传后忘记重启容器。始终使用 `sync_to_server.py`。

**同步脚本技术要点**：
- 使用 paramiko 复用 SSH 连接（3秒 vs scp 逐文件12秒）
- 禁止依赖 sshpass（Windows 通常未安装）
- SSH 密码从 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt` 自动读取

### 4.3 Docker 容器操作

| 场景 | 命令 | 说明 |
|------|------|------|
| 代码变更（app/ 下文件） | `docker compose restart api` | 只重启，不重新读取 .env |
| .env 变更 | `docker compose up -d api` | 重建容器，加载新环境变量 |
| docker-compose.yml 变更 | `docker compose up -d api` | 重建容器 |
| requirements.txt/Dockerfile 变更 | `docker compose up -d --build api` | 重新构建镜像 |
| 数据库模型变更 | `docker compose exec api alembic upgrade head` | 运行迁移 |

**Docker 挂载路径**：宿主机是 `/root/videogen/app/`，不是 `/root/videogen/backend/app/`

### 4.4 注意事项

- **不要用 `api.videogen.com` 做 SSH**：域名解析到 CDN 代理 IP，SSH 流量被拒绝，必须用 `8.141.101.155`
- **不要在服务器 `git pull`**：服务器不是 git 仓库，使用 `sync_to_server.py` 上传
- **SSH 密码定期更新**：同步前先读取 `current_ssh_password.txt` 获取最新密码
- **.env 变更后**：`sync_to_server.py` 默认执行 `restart`，需手动执行 `docker compose up -d api`

### 4.5 首次部署 ECDSA 密钥

1. 运行 `python generate_signing_keys.py` 生成密钥对
2. 用 `sync_to_server.py` 上传密钥文件
3. 更新服务器 `.env`：添加 `ECDSA_PRIVATE_KEY_PATH=keys/.license_sign_private.pem`
4. 重建容器：`docker compose up -d api`（必须用 up -d）
5. 验证：`curl -s http://127.0.0.1:8000/health`

---

## 五、密钥管理

### 5.1 密钥类型

| 密钥 | 用途 | 分发范围 |
|------|------|---------|
| ECDSA 私钥（`.license_sign_private.pem`） | 服务端签名授权数据 | 仅服务端，绝不随客户端分发 |
| ECDSA 公钥（`.license_verify_pubkey.pem`） | 客户端验证签名 | 随客户端打包 |
| HMAC 密钥（`.license_verify_key`） | 旧版兼容签名 | 随客户端打包 |

- **密钥轮换**：运行 `python generate_signing_keys.py`，然后同步到服务端和客户端
- **密钥文件安全**：私钥不得提交到公开仓库（已在 .gitignore 中排除）

### 5.2 密钥文件位置

| 文件 | 本地 | 服务端 | 客户端 |
|------|------|--------|--------|
| 私钥 | `keys/.license_sign_private.pem` | `/root/videogen/keys/` | 不分发 |
| 公钥 | `.license_verify_pubkey.pem` | `/root/videogen/keys/` | exe同级 + `_internal/` |
| HMAC | `.license_verify_key` | `/root/videogen/keys/` | exe同级 + `_internal/` |

---

## 六、打包规范

- **每次打包前必须先征得用户同意**，说明原因和预计耗时
- 打包完成后向用户汇报结果（输出目录、大小、验证结果）
- **打包前必须彻底删除所有旧构建产物**：
  - `build/`、`dist/`、`dist_obfuscated/`、`_obf_backup/`、`dependencies_package/`、`installer_output/`
  - `*.zip`、`*.7z`、`*.tar.gz`、`__pycache__/`
  - 旧构建产物毫无价值，必须彻底清除

---

## 七、项目整洁规范

- **项目根目录必须保持干净**，不得残留临时文件或废弃产物
- 禁止遗留：构建产物、临时文件（`*.tmp`/`*.bak`/`*.log`）、缓存目录、调试脚本（用完即删）
- 每次会话结束前检查并清理根目录
- 新建临时脚本必须在用途完成后立即删除

---

## 八、文件保护（绝对禁止删除/修改）

- `f:\shipinshengcheng\ssh_manager\` — SSH密码管理工具目录，**任何情况下都不得删除、移动或覆盖**
  - 包含：`生成SSH密码.bat`、`ssh_password_manager.py`、`current_ssh_password.txt`、`ssh_password_history.txt`、`.key_salt`
- 清理临时文件时，**只允许删除以 `ssh_check`/`ssh_reset`/`ssh_upload`/`ssh_rebuild`/`ssh_sync`/`ssh_copy`/`ssh_fix`/`ssh_logs` 开头的 `.py` 文件**
- **绝不使用通配符 `ssh_*.py` 删除文件**，会误删 `ssh_password_manager.py`

---

## 九、新会话启动检查

每次新对话开始时，必须按以下顺序检查项目状态并向用户汇报：

1. **Git 工作区**：`git status` + `git diff --stat`，有未提交变更则汇报
2. **远程推送**：`git log origin/master..HEAD`，有未推送提交则汇报
3. **云端同步**：本地有新变更未同步到云端则汇报，同步方式 `python sync_to_server.py`
4. **工作区整洁**：确认无临时文件、无测试残留、`config.json` 的 `api_base_url` 为 `http://8.141.101.155`、无构建产物

**汇报格式**：
```
项目状态检查
- Git工作区: 干净 / 有N个未提交变更
- 远程推送: 已同步 / 有N个未推送提交
- 云端服务器: 已同步 / 需要同步（列出变更文件）
- 工作区: 干净 / 发现临时文件（列出）
```
