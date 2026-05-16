# 项目操作规则

## 端口与服务管理

1. **8000 端口是用户专用的**（语音克隆项目后端），本地测试时使用其他端口（如 9000），启动命令示例：
   ```
   uvicorn app.main:app --host 0.0.0.0 --port 9000
   ```
2. **不得随意终止任何运行中的服务**（本地或云端），包括但不限于：
   - 本地 8000 端口上的语音克隆项目服务
   - 远程服务器 8.141.101.155 上的 Docker 容器
   - 任何其他用户正在使用的进程
3. **需要重启服务时，必须先征求用户同意**，说明原因和影响范围
4. **端口冲突时优先换端口，不 kill 进程**

## 远程服务器

- SSH: `ssh root@8.141.101.155`（密码定期更新，当前密码见 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt`）
- 管理后台: `http://8.141.101.155/admin/login`
- 管理员账号: `admin` / `Admin123456!`
- 后端运行在 Docker 容器中（`videogen-api-1`），项目目录 `/root/videogen/`
- docker-compose 中 `./app:/app/app` 为绑定挂载，修改宿主机文件后重启容器即生效，无需重新构建镜像

### Docker 容器操作关键规则

- **`docker compose restart api`**：只重启现有容器，**不会重新读取 .env 文件**。适用于代码文件变更（通过绑定挂载自动生效）
- **`docker compose up -d api`**：检测配置变化并**重新创建容器**，会加载新的 .env 环境变量。适用于 .env 变更、新增环境变量等场景
- **何时用 `up -d` 而非 `restart`**：
  - 修改了 `.env` 文件 → `docker compose up -d api`
  - 修改了 `docker-compose.yml` → `docker compose up -d api`
  - 只修改了 `app/` 下的代码文件 → `docker compose restart api`
- **Docker 挂载路径**：`./app:/app/app`，所以宿主机路径是 `/root/videogen/app/`，而非 `/root/videogen/backend/app/`
  - 正确: `scp auth.py root@8.141.101.155:/root/videogen/app/routers/auth.py`
  - 错误: `scp auth.py root@8.141.101.155:/root/videogen/backend/app/routers/auth.py`

### 云端代码同步流程（一键同步，禁止手动分步操作）

**必须使用 `sync_to_server.py` 一键同步脚本**，该脚本基于 **paramiko 复用 SSH 连接**，自动完成：上传所有后端文件 → 重启API容器 → 健康检查验证。禁止手动 scp + 手动重启的分步操作，避免遗漏重启步骤。

```bash
# 一键同步（上传所有后端文件 + 自动重启 + 自动验证）
python sync_to_server.py

# 仅同步代码文件（不同步模板）
python sync_to_server.py --code

# 仅同步模板文件
python sync_to_server.py --templates
```

**同步前必须先提交推送**：`git add -A && git commit -m "xxx" && git push origin master`

> ⚠️ **绝对禁止**：手动 scp 上传后忘记重启容器。这会导致服务器运行旧代码，项目运行不畅。始终使用 `sync_to_server.py`。

#### 同步脚本技术要点（禁止回退到 scp 方式）

- **使用 paramiko 复用连接**：建立1次SSH连接，通过SFTP通道上传所有文件，同一连接执行docker命令和健康检查
- **禁止使用 scp 逐文件上传**：scp 每个文件都建立独立SSH连接+密钥交换，31个文件需31次握手约12秒；paramiko复用连接仅需3秒，提速4倍
- **禁止依赖 sshpass**：Windows 环境下 sshpass 通常未安装，导致 scp 方式全部失败；paramiko 纯 Python 实现，无外部依赖
- **SSH 密码来源**：从 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt` 读取

### 注意事项

- **不要用 `api.videogen.com` 做 SSH**：该域名解析到 CDN 代理 IP（198.18.x.x），SSH 流量被拒绝，必须用真实 IP `8.141.101.155`
- **不要 `git pull`**：服务器 `/root/videogen/` 不是 git 仓库，使用 `sync_to_server.py` 直接上传文件
- **修改了 requirements.txt 或 Dockerfile**：需要重新构建镜像 `docker compose up -d --build api`
- **修改了数据库模型**：需要运行迁移 `docker compose exec api alembic upgrade head`
- **SSH 密码定期更新**：用户会定期更换 SSH 密码，新密码保存在 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt`，同步前先读取该文件获取最新密码

## ECDSA 密钥管理与安全

- **ECDSA 密钥对**用于授权数据签名验证，替代旧的 HMAC 对称签名
- **私钥**（`keys/.license_sign_private.pem`）：仅服务端使用，**绝不随客户端分发**
- **公钥**（`.license_verify_pubkey.pem`）：随客户端打包分发，用于验证签名
- **旧 HMAC 密钥**（`.license_verify_key`）：保留用于向后兼容，新授权数据自动使用 ECDSA 签名（sig_ver=2）
- **密钥轮换**：如需更换密钥对，运行 `python generate_signing_keys.py`，然后同步到服务端和客户端
- **密钥文件安全**：私钥文件不得提交到公开仓库（已在 .gitignore 中排除）

### 密钥文件位置

| 文件 | 本地位置 | 服务端位置 | 客户端位置 |
|------|---------|-----------|-----------|
| 私钥 | `keys/.license_sign_private.pem` | `/root/videogen/keys/.license_sign_private.pem` | 不分发 |
| 公钥 | `.license_verify_pubkey.pem` | `/root/videogen/keys/.license_verify_pubkey.pem` | exe同级 + `_internal/` |
| HMAC密钥 | `.license_verify_key` | `/root/videogen/keys/.license_verify_key` | exe同级 + `_internal/` |

## 部署与自动重启

- **必须使用 `sync_to_server.py` 一键同步**：上传 + 重启 + 验证一步到位，杜绝遗漏重启（基于 paramiko 复用连接，速度快、无外部依赖）
- **.env 变更后需额外操作**：`sync_to_server.py` 默认执行 `docker compose restart api`；如果修改了 `.env` 文件，需手动执行 `docker compose up -d api`（重建容器以加载新环境变量）
- **密钥文件同步**：新密钥文件上传到服务器后，同样使用 `sync_to_server.py` 自动重启
- **无需用户确认重启**：代码已同步到服务器意味着用户已同意部署，自动重启是部署流程的一部分

### 首次部署 ECDSA 密钥的步骤

1. 运行 `python generate_signing_keys.py` 生成密钥对
2. 使用 `sync_to_server.py` 上传密钥文件到服务器（或通过 paramiko SFTP 手动上传 `keys/.license_sign_private.pem` 和 `keys/.license_verify_pubkey.pem` 到 `/root/videogen/keys/`）
3. 更新服务器 `.env`：添加 `ECDSA_PRIVATE_KEY_PATH=keys/.license_sign_private.pem`
4. 重建 API 容器：`docker compose up -d api`（必须用 up -d，因为 .env 变更）
5. 验证：`curl -s http://127.0.0.1:8000/health`

## 打包工程文件

- **每次执行打包（运行 01build_exe.py）前，必须先征得用户同意**，说明打包原因和预计耗时
- 未经用户明确同意，不得自行启动打包流程
- 打包完成后，向用户汇报结果（输出目录、大小、验证结果）
- **打包前必须彻底删除所有旧构建产物**，包括但不限于：
  - `build/`、`dist/`、`dist_obfuscated/`、`_obf_backup/`、`dependencies_package/`、`installer_output/` 目录
  - `*.zip`、`*.7z`、`*.tar.gz` 压缩包
  - `__pycache__/` 目录
  - 旧构建产物一旦被新打包替代就毫无价值，必须彻底清除，不得占用磁盘空间

## 项目根目录整洁规范

- **项目根目录必须始终保持清清朗朗、工工整整**，不得残留任何临时文件或废弃产物
- 禁止在根目录遗留以下类型的文件：
  - 构建产物：`dist/`、`build/`、`*.zip`、`*.7z`、`*.tar.gz`、`*.spec.bak`
  - 临时文件：`*.tmp`、`*.bak`、`*.log`、`*.db`（项目自用的除外）
  - 缓存目录：`__pycache__/`、`.pytest_cache/`、`.mypy_cache/`
  - 调试脚本：一次性使用的 `test_*.py`、`debug_*.py`、`check_*.py`（用完即删）
  - IDE 产物：`.idea/`、`.vscode/`（已在 .gitignore 中排除）
- 每次会话结束前，检查并清理根目录中不应存在的文件
- 新建临时脚本时，必须在用途完成后立即删除

## 本地测试

- 本地测试后端使用端口 **9000**（避免与 8000 端口冲突）
- 本地数据库使用 SQLite（`videogen.db`），与远程 PostgreSQL 独立
- 测试完毕后关停本地 uvicorn 进程
- 客户端 `config.json` 中 `api_base_url` 测试时临时改为 `http://localhost:9000`，测试完恢复为 `http://8.141.101.155`

## 文件保护（绝对禁止删除/修改）

以下文件和目录是用户专用工具，**任何情况下都不得删除、移动或覆盖**：

- `f:\\shipinshengcheng\\ssh_manager\\` — SSH密码管理工具目录，包含：
  - `生成SSH密码.bat` — 启动入口
  - `ssh_password_manager.py` — 主程序
  - `current_ssh_password.txt` — 当前密码
  - `ssh_password_history.txt` — 密码变更历史
  - `.key_salt` — 加密盐值
- 清理临时文件时，**只允许删除以 `ssh_check`、`ssh_reset`、`ssh_upload`、`ssh_rebuild`、`ssh_sync`、`ssh_copy`、`ssh_fix`、`ssh_logs` 开头的 `.py` 文件**（这些是我自己创建的临时脚本）
- **绝不使用通配符 `ssh_*.py` 删除文件**，因为会误删 `ssh_password_manager.py`

## 新会话启动检查（每次新对话开始时必须执行）

每次新会话开始时，必须按以下顺序检查项目状态，并向用户汇报：

1. **检查Git工作区状态**
   - 执行 `git status` 查看是否有未提交的代码变更
   - 执行 `git diff --stat` 查看变更文件概览
   - 如有未提交变更，向用户汇报并询问是否需要提交

2. **检查是否需要推送到远程仓库**
   - 执行 `git log origin/master..HEAD` 查看是否有本地未推送的提交
   - 如有未推送的提交，向用户汇报并询问是否需要推送

3. **检查是否需要同步到云端服务器**
   - 对比本地代码与远程服务器 `/root/videogen/app/` 的代码版本
   - 如本地有新变更尚未同步到云端，向用户汇报并询问是否需要同步
   - 同步方式：`python sync_to_server.py` 一键同步（上传 + 重启 + 验证）
   - SSH 密码从 `f:\shipinshengcheng\ssh_manager\current_ssh_password.txt` 读取（脚本自动读取）

4. **检查工作区是否干净**
   - 确认无残留的临时文件（如 `ssh_check*.py`、`ssh_reset*.py` 等临时脚本）
   - 确认无残留的测试文件（如 `test_*.py`、`*.db` 等不应存在于项目中的文件）
   - 确认 `config.json` 的 `api_base_url` 为 `http://8.141.101.155`（非测试用的 localhost）
   - 确认根目录无构建产物残留（`dist/`、`build/`、`*.zip` 等）

5. **汇报格式**
   ```
   📋 项目状态检查
   - Git工作区: 干净 / 有N个未提交变更
   - 远程推送: 已同步 / 有N个未推送提交
   - 云端服务器: 已同步 / 需要同步（列出变更文件）
   - 工作区: 干净 / 发现临时文件（列出）
   ```
