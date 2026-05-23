#!/usr/bin/env python3
import paramiko
import os
import sys

SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"

def get_ssh_password():
    if os.path.exists(SSH_PASSWORD_FILE):
        with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

def main():
    password = get_ssh_password()
    if not password:
        print("ERROR: SSH密码文件不存在")
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

    # 检查admin用户状态
    cmd = """cd /root/videogen && docker compose exec -T api python3 -c "
from app.database import SessionLocal
from app.models import User
from sqlalchemy import select
db = SessionLocal()
user = db.execute(select(User).where(User.username=='admin')).scalar_one()
print(f'is_active={user.is_active}')
print(f'is_admin={user.is_admin}')
print(f'password_changed_at={user.password_changed_at}')
print(f'created_at={user.created_at}')
db.close()
"
"""
    print("=== 检查admin用户状态 ===")
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print("ERR:", err)

    # 测试登录
    print("\n=== 测试admin登录 ===")
    cmd2 = """cd /root/videogen && docker compose exec -T api python3 -c "
import os
from app.config import settings
print(f'ADMIN_PASSWORD is set: {bool(settings.ADMIN_PASSWORD)}')
" """
    stdin, stdout, stderr = ssh.exec_command(cmd2)
    out2 = stdout.read().decode().strip()
    print(out2)

    ssh.close()

if __name__ == "__main__":
    main()
