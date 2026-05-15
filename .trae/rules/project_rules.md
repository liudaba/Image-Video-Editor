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

- SSH: `ssh root@8.141.101.155`，密码: `1t&zdDYk979tZYksBtfZ`
- 管理后台: `http://8.141.101.155/admin/login`
- 管理员账号: `admin` / `Admin123456!`
- 后端运行在 Docker 容器中（`videogen-api-1`），项目目录 `/home/backend/`
- 代码同步方式：SFTP 上传到宿主机 + `docker cp` 到容器 + `docker restart`

## 本地测试

- 本地测试后端使用端口 **9000**（避免与 8000 端口冲突）
- 本地数据库使用 SQLite（`videogen.db`），与远程 PostgreSQL 独立
- 测试完毕后关停本地 uvicorn 进程
- 客户端 `config.json` 中 `api_base_url` 测试时临时改为 `http://localhost:9000`，测试完恢复为 `http://8.141.101.155`

## 文件保护（绝对禁止删除/修改）

以下文件和目录是用户专用工具，**任何情况下都不得删除、移动或覆盖**：

- `f:\shipinshengcheng\ssh_manager\` — SSH密码管理工具目录，包含：
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
   - 对比本地代码与远程服务器 `/home/backend/` 的代码版本
   - 如本地有新变更尚未同步到云端，向用户汇报并询问是否需要同步
   - 同步方式：SFTP 上传到宿主机 → `docker cp` 到容器 → `docker restart`（需用户同意后才执行）

4. **检查工作区是否干净**
   - 确认无残留的临时文件（如 `ssh_check*.py`、`ssh_reset*.py` 等临时脚本）
   - 确认无残留的测试文件（如 `test_*.py`、`*.db` 等不应存在于项目中的文件）
   - 确认 `config.json` 的 `api_base_url` 为 `http://8.141.101.155`（非测试用的 localhost）

5. **汇报格式**
   ```
   📋 项目状态检查
   - Git工作区: 干净 / 有N个未提交变更
   - 远程推送: 已同步 / 有N个未推送提交
   - 云端服务器: 已同步 / 需要同步（列出变更文件）
   - 工作区: 干净 / 发现临时文件（列出）
   ```
