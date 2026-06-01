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

## 九、PowerShell 环境下执行 Python 代码规范

### 9.1 核心原则

**禁止使用 `python -c "..."` 执行复杂 Python 代码**。PowerShell 5 对嵌套引号、f-string、特殊字符的转义处理极差，会导致不可预期的语法错误。

### 9.2 标准执行模式：here-string + 临时文件

```powershell
$code = @'
# 任意 Python 代码，无需任何转义
print(f"单引号'双引号\"反斜杠\\都OK")
result = "RAW" not in "Ghibli style"
print(f"逻辑判断 = {result}")
'@
[System.IO.File]::WriteAllText("$env:TEMP\_py_test.py", $code, [System.Text.UTF8Encoding]::new($false))
python "$env:TEMP\_py_test.py"
```

### 9.3 关键技术要点

| 要点 | 说明 |
|------|------|
| `@' ... '@` | PowerShell here-string，内部**不做任何转义解析**，原样输出 |
| `[System.Text.UTF8Encoding]::new($false)` | 写入**无BOM的UTF-8**，避免 Python 报 `U+FEFF` 错误 |
| `$env:TEMP\_py_test.py` | 使用系统临时目录，不污染项目 |
| `sys.path.insert(0, r'项目路径')` | 临时文件不在项目目录时，需手动添加项目路径到 `sys.path` |

### 9.4 简单命令例外

仅以下场景允许使用 `python -c`：
- 单行、无引号嵌套的简单检查：`python -c "import ast; print('OK')"`
- 版本检查：`python -c "import torch; print(torch.__version__)"`

**判断标准**：如果代码包含 f-string、嵌套引号、中文、或超过1个逻辑行，必须使用临时文件模式。

---

## 十、新会话启动检查

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

---

## 十一、补丁发布流程规范（强制执行）

> **背景**：v1.0.10 补丁因 manifest.json 格式错误，导致客户端更新后程序无法启动。此规范为避免重蹈覆辙。

### 11.1 补丁 manifest.json 格式（强制标准）

manifest.json 中的 `files` **必须是对象数组**，每个对象包含 `path`、`sha256`、`size` 三个字段：

```json
{
  "version": "1.0.11",
  "from_version": "1.0.10",
  "files": [
    {
      "path": "video_generator/xxx.py",
      "sha256": "abc123...",
      "size": 12345
    }
  ],
  "release_notes": "更新说明",
  "force_update": false
}
```

**绝对禁止**使用字符串数组：`"files": ["video_generator/xxx.py"]` — 这会导致 `_load_manifest` 解析失败，触发"全目录替换"逻辑，删除所有未包含在补丁中的文件。

### 11.2 补丁发布三步流程（不可跳过任何一步）

**第一步：生成补丁**
- 使用 `_push_vXXX.py` 脚本生成补丁，确保 manifest.json 格式正确
- 补丁中只包含**变更的文件**，不包含未修改的文件

**第二步：本地端到端验证（强制）**
- 创建完整 dist 副本到临时目录
- 模拟 `_load_manifest` → `_verify_manifest` → `_apply_patch` 全流程
- 验证项：
  1. manifest 解析成功（不为 None）
  2. SHA256 校验通过
  3. 补丁前后文件总数不变
  4. 无文件丢失（对比补丁前后的 .py 文件列表）
  5. version.json 和 version.py 版本号正确
- **任何一项验证失败，禁止上传到服务器**

**第三步：上传到服务器**
- 只有第二步全部通过后，才执行 `_push_vXXX.py` 上传补丁
- 上传后验证：模拟客户端检查更新，确认返回正确的 patch_url 和 patch_size

### 11.3 dist 目录操作禁令

- **未经用户明确授权，禁止修改、同步、覆盖 dist 目录下的任何文件**
- dist 目录是用户管理的发布包，不是开发目录
- 代码修改只在 `video_generator/` 源代码目录进行
- 补丁通过服务器分发给客户，不通过直接修改 dist 目录

### 11.4 版本发布检查清单

每次发布新版本前，逐项确认：

- [ ] 代码修改在源代码目录完成，语法检查通过
- [ ] 本地功能测试通过（import 测试、关键函数调用测试）
- [ ] 版本号已更新（version.py + version.json）
- [ ] 补丁已生成，manifest.json 格式正确
- [ ] 本地端到端补丁应用测试通过
- [ ] git commit + push 完成
- [ ] 补丁上传到服务器，版本注册成功
- [ ] 模拟客户端验证更新可用
- [ ] 临时脚本已清理
