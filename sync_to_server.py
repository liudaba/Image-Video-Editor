#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键部署脚本：本地代码 -> 云端服务器
流程：上传文件 -> 重启容器 -> 健康检查

服务器目录结构：
  /root/videogen/              ← docker compose 项目目录
  ├── docker-compose.yml
  ├── Dockerfile
  ├── requirements.txt         ← Python 依赖（同步）
  ├── alembic.ini              ← 数据库迁移配置（同步）
  ├── alembic/                 ← 数据库迁移脚本（同步）
  │   ├── env.py
  │   ├── script.py.mako
  │   └── versions/
  ├── .env                     ← 服务器专属配置（不同步）
  ├── keys/                    ← 密钥目录（挂载到容器 /app/keys）
  ├── logs/                    ← 日志目录（挂载到容器 /app/logs）
  └── app/                     ← 代码目录（挂载到容器 /app/app）
      ├── __init__.py
      ├── main.py, config.py, ...
      ├── routers/
      ├── services/
      └── templates/

容器挂载关系：
  /root/videogen/keys -> /app/keys
  /root/videogen/logs -> /app/logs
  /root/videogen/app  -> /app/app

重启策略（由快到慢）：
  1. docker restart（普通代码变更，~10秒）
  2. docker compose up -d（docker-compose.yml 变更，~15秒）
  3. docker compose up -d --build（Dockerfile/依赖变更，~数分钟）

用法：
  python sync_to_server.py              # 默认：同步所有代码+模板
  python sync_to_server.py --build      # 强制重建镜像
  python sync_to_server.py --templates  # 只同步模板文件
  python sync_to_server.py --code       # 只同步代码文件（不含模板）
"""
import paramiko
import sys
import os
import posixpath
import time
import json

sys.stdout.reconfigure(line_buffering=True)

# ─── 配置 ───────────────────────────────────────────────────
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_PROJECT_DIR = "/root/videogen"
SERVER_APP_DIR = "/root/videogen/app"
CONTAINER = "videogen-api-1"
HEALTH_URL = "http://127.0.0.1:8000/health"

# 本地路径 -> 服务器路径映射（{app_dir} 和 {project_dir} 会被替换）
SYNC_FILES = [
    # Python 代码
    ("backend/app/__init__.py",              "{app_dir}/__init__.py"),
    ("backend/app/main.py",                  "{app_dir}/main.py"),
    ("backend/app/config.py",                "{app_dir}/config.py"),
    ("backend/app/database.py",              "{app_dir}/database.py"),
    ("backend/app/models.py",                "{app_dir}/models.py"),
    ("backend/app/schemas.py",               "{app_dir}/schemas.py"),
    ("backend/app/auth.py",                  "{app_dir}/auth.py"),
    # 路由
    ("backend/app/routers/__init__.py",      "{app_dir}/routers/__init__.py"),
    ("backend/app/routers/admin.py",         "{app_dir}/routers/admin.py"),
    ("backend/app/routers/auth.py",          "{app_dir}/routers/auth.py"),
    ("backend/app/routers/license.py",       "{app_dir}/routers/license.py"),
    ("backend/app/routers/payment.py",       "{app_dir}/routers/payment.py"),
    ("backend/app/routers/user.py",          "{app_dir}/routers/user.py"),
    ("backend/app/routers/version.py",       "{app_dir}/routers/version.py"),
    # 服务
    ("backend/app/services/__init__.py",     "{app_dir}/services/__init__.py"),
    ("backend/app/services/cleanup_service.py",    "{app_dir}/services/cleanup_service.py"),
    ("backend/app/services/heartbeat_service.py",  "{app_dir}/services/heartbeat_service.py"),
    ("backend/app/services/license_service.py",    "{app_dir}/services/license_service.py"),
    ("backend/app/services/payment_service.py",    "{app_dir}/services/payment_service.py"),
    # Python 依赖（重建镜像时需要）
    ("backend/requirements.txt",             "{project_dir}/requirements.txt"),
    # 数据库初始化脚本
    ("backend/init_db.py",                   "{project_dir}/init_db.py"),
    # 数据库迁移
    ("backend/alembic.ini",                  "{project_dir}/alembic.ini"),
    ("backend/alembic/env.py",               "{project_dir}/alembic/env.py"),
    ("backend/alembic/script.py.mako",       "{project_dir}/alembic/script.py.mako"),
    ("backend/alembic/versions/001_initial.py",            "{project_dir}/alembic/versions/001_initial.py"),
    ("backend/alembic/versions/002_payment_notify.py",     "{project_dir}/alembic/versions/002_payment_notify.py"),
    ("backend/alembic/versions/003_order_fields.py",       "{project_dir}/alembic/versions/003_order_fields.py"),
    ("backend/alembic/versions/004_cleanup_indexes.py",    "{project_dir}/alembic/versions/004_cleanup_indexes.py"),
    ("backend/alembic/versions/005_license_key_expiry.py", "{project_dir}/alembic/versions/005_license_key_expiry.py"),
    ("backend/alembic/versions/006_license_plan_type.py",  "{project_dir}/alembic/versions/006_license_plan_type.py"),
    ("backend/alembic/versions/007_version_patch_fields.py", "{project_dir}/alembic/versions/007_version_patch_fields.py"),
    # Docker 配置（同步到项目根目录）
    ("backend/Dockerfile",                   "{project_dir}/Dockerfile"),
    ("backend/docker-compose.yml",           "{project_dir}/docker-compose.yml"),
    # 密钥文件（同步到 keys/ 目录）
    ("backend/keys/.license_sign_private.pem", "{project_dir}/keys/.license_sign_private.pem"),
    ("backend/keys/.license_verify_pubkey.pem", "{project_dir}/keys/.license_verify_pubkey.pem"),
    # 注意：.env 不同步！服务器有自己的配置（含 DB_PASSWORD 等）
]

# 模板文件（自动映射到 {app_dir}/templates/）
TEMPLATE_FILES = [
    "backend/app/templates/admin_base.html",
    "backend/app/templates/analytics_content.html",
    "backend/app/templates/audit_logs_content.html",
    "backend/app/templates/dashboard_content.html",
    "backend/app/templates/licenses_content.html",
    "backend/app/templates/login.html",
    "backend/app/templates/orders_content.html",
    "backend/app/templates/trial_codes_content.html",
    "backend/app/templates/users_content.html",
    "backend/app/templates/versions_content.html",
]


def get_ssh_password():
    if os.path.exists(SSH_PASSWORD_FILE):
        with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def exec_cmd(ssh, cmd, timeout=60):
    """执行远程命令，返回 (exit_code, stdout, stderr)"""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    return rc, stdout.read().decode().strip(), stderr.read().decode().strip()


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    force_build = "--build" in sys.argv
    only_templates = "--templates" in sys.argv
    only_code = "--code" in sys.argv

    print("=" * 60)
    print("  VideoGenerator 一键部署")
    print("=" * 60)

    # ─── [1/3] 收集文件并上传 ──────────────────────────────
    files_to_sync = []

    # 代码文件
    if not only_templates:
        for local_rel, remote_rel in SYNC_FILES:
            local_path = os.path.join(project_dir, local_rel)
            if not os.path.exists(local_path):
                print(f"  [SKIP] {local_rel} (本地不存在)")
                continue
            remote_path = remote_rel.format(
                app_dir=SERVER_APP_DIR,
                project_dir=SERVER_PROJECT_DIR,
            )
            files_to_sync.append((local_path, remote_path, local_rel))

    # 模板文件
    if not only_code:
        for local_rel in TEMPLATE_FILES:
            local_path = os.path.join(project_dir, local_rel)
            if not os.path.exists(local_path):
                print(f"  [SKIP] {local_rel} (本地不存在)")
                continue
            basename = os.path.basename(local_rel)
            remote_path = f"{SERVER_APP_DIR}/templates/{basename}"
            files_to_sync.append((local_path, remote_path, local_rel))

    if not files_to_sync:
        print("  没有需要同步的文件")
        return

    password = get_ssh_password()
    if not password:
        print("  ERROR: SSH密码文件不存在或为空")
        sys.exit(1)

    print(f"\n  [1/3] 连接服务器并上传 {len(files_to_sync)} 个文件...")
    t_start = time.time()

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)
    except Exception as e:
        print(f"  FAIL: SSH连接失败: {e}")
        sys.exit(1)

    t_connected = time.time()
    print(f"  SSH连接成功 ({t_connected - t_start:.1f}s)")

    sftp = ssh.open_sftp()

    success_count = 0
    fail_count = 0
    # 预先收集所有需要创建的远程目录
    remote_dirs_needed = set()
    for local_path, remote_path, rel in files_to_sync:
        remote_dir = posixpath.dirname(remote_path)
        if remote_dir:
            remote_dirs_needed.add(remote_dir)

    # 批量创建远程目录
    for remote_dir in sorted(remote_dirs_needed):
        rc, _, _ = exec_cmd(ssh, f"mkdir -p {remote_dir}", timeout=10)
        if rc != 0:
            print(f"  [WARN] 创建目录 {remote_dir} 失败")

    for local_path, remote_path, rel in files_to_sync:
        try:
            sftp.put(local_path, remote_path)
            success_count += 1
            print(f"  [OK] {rel}")
        except Exception as e:
            print(f"  [FAIL] {rel} - {e}")
            fail_count += 1

    sftp.close()
    t_uploaded = time.time()
    print(f"  上传完成: {success_count} 成功, {fail_count} 失败 ({t_uploaded - t_connected:.1f}s)")

    if fail_count > 0:
        print(f"\n  {fail_count} 个文件上传失败，中止部署")
        ssh.close()
        sys.exit(1)

    # ─── [2/3] 重启容器 ────────────────────────────────────
    # 判断重启策略
    compose_changed = any(
        rel == "backend/docker-compose.yml" for _, _, rel in files_to_sync
    )
    dockerfile_changed = any(
        rel == "backend/Dockerfile" for _, _, rel in files_to_sync
    )
    requirements_changed = any(
        rel == "backend/requirements.txt" for _, _, rel in files_to_sync
    )

    if force_build or dockerfile_changed or requirements_changed:
        # 策略3：重建镜像（最慢，Dockerfile 或依赖变更时才需要）
        reasons = []
        if force_build:
            reasons.append("强制")
        if dockerfile_changed:
            reasons.append("Dockerfile 变更")
        if requirements_changed:
            reasons.append("requirements.txt 变更")
        reason = " + ".join(reasons)
        print(f"\n  [2/3] {reason}，重建镜像并重启容器...")
        # 先停止并移除旧容器，避免容器名冲突
        exec_cmd(ssh, f"cd {SERVER_PROJECT_DIR} && docker compose down api", timeout=30)
        cmd = f"cd {SERVER_PROJECT_DIR} && docker compose up -d --build api"
        rc, out, err = exec_cmd(ssh, cmd, timeout=300)
        if rc != 0:
            print(f"  FAIL: 重建失败: {err}")
            ssh.close()
            sys.exit(1)
        print(f"  镜像重建完成")
    elif compose_changed:
        # 策略2：重新应用 compose 配置（不重建镜像）
        print(f"\n  [2/3] 检测到 docker-compose.yml 变更，重新应用配置...")
        cmd = f"cd {SERVER_PROJECT_DIR} && docker compose up -d api"
        rc, out, err = exec_cmd(ssh, cmd, timeout=60)
        if rc != 0:
            print(f"  FAIL: 配置更新失败: {err}")
            ssh.close()
            sys.exit(1)
        print(f"  配置已应用")
    else:
        # 策略1：直接重启容器（最快，普通代码变更）
        print(f"\n  [2/3] 重启容器 {CONTAINER}...")
        rc, out, err = exec_cmd(ssh, f"docker restart {CONTAINER}", timeout=60)
        if rc != 0:
            print(f"  FAIL: 重启失败: {err}")
            ssh.close()
            sys.exit(1)
        print(f"  容器已重启")

    # 等待容器启动
    print(f"  等待服务就绪...")
    time.sleep(10)

    # ─── [3/3] 健康检查 ────────────────────────────────────
    print(f"\n  [3/3] 健康检查...")
    healthy = False
    for attempt in range(1, 7):
        rc, health_raw, _ = exec_cmd(ssh, f"curl -sf {HEALTH_URL}", timeout=10)
        if rc == 0 and health_raw:
            try:
                health = json.loads(health_raw)
                if health.get("status") == "ok":
                    print(f"  [OK] 健康: db={health.get('database')}, redis={health.get('redis')}")
                    healthy = True
                    break
                else:
                    print(f"  [RETRY {attempt}/6] 状态: {health_raw}")
            except json.JSONDecodeError:
                print(f"  [RETRY {attempt}/6] 返回非JSON: {health_raw}")
        else:
            print(f"  [RETRY {attempt}/6] 服务未就绪，5秒后重试...")
        if attempt < 6:
            time.sleep(5)

    if not healthy:
        print(f"\n  FAIL: 健康检查未通过")
        _, logs, _ = exec_cmd(ssh, f"docker logs --tail 20 {CONTAINER} 2>&1")
        print(f"  最近日志:\n{logs}")
        ssh.close()
        sys.exit(1)

    # 显示容器启动时间
    _, started_at, _ = exec_cmd(
        ssh,
        f'docker inspect --format "{{{{.State.StartedAt}}}}" {CONTAINER} 2>/dev/null'
    )
    print(f"  容器启动时间: {started_at}")

    ssh.close()
    t_total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  部署完成！{success_count} 个文件已上传，服务运行正常")
    print(f"  总耗时: {t_total:.1f}秒")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
