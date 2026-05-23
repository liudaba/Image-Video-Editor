import paramiko
import os

SSH_PASSWORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ssh_manager', 'current_ssh_password.txt')

def get_ssh_password():
    if os.path.exists(SSH_PASSWORD_FILE):
        with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None

pwd = get_ssh_password()
if not pwd:
    print("ERROR: SSH密码文件不存在")
    exit(1)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('8.141.101.155', username='root', password=pwd, timeout=10)

# 上传测试脚本
sftp = ssh.open_sftp()
sftp.put(r'f:\shipinshengcheng\Image-Video-Editor\backend\admin_deep_check.py', '/root/videogen/admin_deep_check.py')
sftp.close()

# 复制到容器并执行
stdin, stdout, stderr = ssh.exec_command(
    'cd /root/videogen && docker compose cp admin_deep_check.py api:/app/admin_deep_check.py && docker compose exec -T api python /app/admin_deep_check.py',
    timeout=60
)
print(stdout.read().decode())
err = stderr.read().decode()
if err.strip():
    print(f"[stderr]: {err[:500]}")

ssh.close()
