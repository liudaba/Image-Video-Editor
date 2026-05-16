#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import paramiko
import sys
import os
import time
import json

SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_APP_DIR = "/root/videogen/app"
SERVER_BACKEND_DIR = "/root/videogen/backend"
HEALTH_URL = "http://127.0.0.1:8000/health"

SYNC_FILES = [
    ("backend/app/__init__.py", "{app_dir}/__init__.py"),
    ("backend/app/main.py", "{app_dir}/main.py"),
    ("backend/app/config.py", "{app_dir}/config.py"),
    ("backend/app/database.py", "{app_dir}/database.py"),
    ("backend/app/models.py", "{app_dir}/models.py"),
    ("backend/app/schemas.py", "{app_dir}/schemas.py"),
    ("backend/app/auth.py", "{app_dir}/auth.py"),
    ("backend/app/routers/__init__.py", "{app_dir}/routers/__init__.py"),
    ("backend/app/routers/admin.py", "{app_dir}/routers/admin.py"),
    ("backend/app/routers/auth.py", "{app_dir}/routers/auth.py"),
    ("backend/app/routers/license.py", "{app_dir}/routers/license.py"),
    ("backend/app/routers/payment.py", "{app_dir}/routers/payment.py"),
    ("backend/app/routers/user.py", "{app_dir}/routers/user.py"),
    ("backend/app/routers/version.py", "{app_dir}/routers/version.py"),
    ("backend/app/services/__init__.py", "{app_dir}/services/__init__.py"),
    ("backend/app/services/cleanup_service.py", "{app_dir}/services/cleanup_service.py"),
    ("backend/app/services/heartbeat_service.py", "{app_dir}/services/heartbeat_service.py"),
    ("backend/app/services/license_service.py", "{app_dir}/services/license_service.py"),
    ("backend/app/services/payment_service.py", "{app_dir}/services/payment_service.py"),
    ("backend/.env", "{backend_dir}/.env"),
]

TEMPLATE_FILES = [
    "backend/app/templates/admin_base.html",
    "backend/app/templates/analytics_content.html",
    "backend/app/templates/audit_logs_content.html",
    "backend/app/templates/dashboard.html",
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


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    print("=" * 60)
    print("  一键同步：本地 -> 云端服务器（上传+重启+验证）")
    print("=" * 60)

    only_templates = "--templates" in sys.argv
    only_code = "--code" in sys.argv

    files_to_sync = []
    for local_rel, remote_rel in SYNC_FILES:
        if only_templates:
            continue
        local_path = os.path.join(project_dir, local_rel)
        if not os.path.exists(local_path):
            print(f"  [SKIP] {local_rel}")
            continue
        remote_path = remote_rel.format(app_dir=SERVER_APP_DIR, backend_dir=SERVER_BACKEND_DIR)
        files_to_sync.append((local_path, remote_path))

    if not only_code:
        for local_rel in TEMPLATE_FILES:
            local_path = os.path.join(project_dir, local_rel)
            if not os.path.exists(local_path):
                print(f"  [SKIP] {local_rel}")
                continue
            basename = os.path.basename(local_rel)
            remote_path = f"{SERVER_APP_DIR}/templates/{basename}"
            files_to_sync.append((local_path, remote_path))

    if not files_to_sync:
        print("  没有需要同步的文件")
        return

    password = get_ssh_password()
    if not password:
        print("  ERROR: SSH密码文件不存在或为空")
        sys.exit(1)

    # [1/3] 建立连接 + 上传文件（复用同一SSH连接）
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
    print(f"  连接建立: {t_connected - t_start:.2f}秒")

    sftp = ssh.open_sftp()

    success_count = 0
    fail_count = 0
    for local_path, remote_path in files_to_sync:
        rel = os.path.relpath(local_path, project_dir)
        try:
            remote_dir = os.path.dirname(remote_path)
            try:
                sftp.stat(remote_dir)
            except FileNotFoundError:
                stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_dir}")
                stdout.read()
            sftp.put(local_path, remote_path)
            success_count += 1
        except Exception as e:
            print(f"  FAIL: {rel} - {e}")
            fail_count += 1

    sftp.close()

    t_uploaded = time.time()
    print(f"  上传完成: {success_count} 个文件成功, 耗时 {t_uploaded - t_connected:.2f}秒")

    if fail_count > 0:
        print(f"\n  {fail_count} 个文件上传失败，中止同步")
        ssh.close()
        sys.exit(1)

    # [2/3] 重启 API 容器
    print(f"\n  [2/3] 重启 API 容器...")
    stdin, stdout, stderr = ssh.exec_command("cd /root/videogen && docker compose restart api")
    output = stdout.read().decode().strip()
    errors = stderr.read().decode().strip()
    if errors and "error" in errors.lower():
        print(f"  FAIL: 容器重启失败: {errors}")
        ssh.close()
        sys.exit(1)
    print(f"  OK: 容器重启成功")

    print(f"\n  等待服务就绪...")
    time.sleep(8)

    # [3/3] 健康检查
    print(f"\n  [3/3] 健康检查...")
    stdin, stdout, stderr = ssh.exec_command(f"curl -s {HEALTH_URL}")
    health_raw = stdout.read().decode().strip()
    try:
        health = json.loads(health_raw)
        if health.get("status") == "ok":
            print(f"  OK: status={health.get('status')}, db={health.get('database')}, redis={health.get('redis')}")
        else:
            print(f"  FAIL: 健康检查异常: {health_raw}")
            ssh.close()
            sys.exit(1)
    except json.JSONDecodeError:
        print(f"  FAIL: 健康检查返回非JSON: {health_raw}")
        ssh.close()
        sys.exit(1)

    ssh.close()

    t_total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  同步完成！{success_count} 个文件已上传，服务运行正常")
    print(f"  总耗时: {t_total:.1f}秒")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
