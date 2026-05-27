"""上传1.0.2补丁到服务器并注册版本（累加式更新）"""
import requests
import paramiko
import os

base = 'https://api.wangzha178.com'
patch_file = r'F:\shipinshengcheng\Image-Video-Editor\patches\update_1.0.0_to_1.0.2.zip'
patch_hash = '56ae4faf4f027da677bd08eb9fbfd6db7ed09f1da5b8ba426077e8173b9046e2'
patch_size = 10371

# 1. 通过SSH上传补丁文件到服务器
print("1. 上传补丁文件到服务器...")
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"

with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
    password = f.read().strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

SERVER_PATCHES_DIR = "/root/videogen/app/static/patches"
ssh.exec_command(f"mkdir -p {SERVER_PATCHES_DIR} && chmod 777 {SERVER_PATCHES_DIR}")

sftp = ssh.open_sftp()
remote_path = f"{SERVER_PATCHES_DIR}/update_1.0.0_to_1.0.2.zip"
sftp.put(patch_file, remote_path)
ssh.exec_command(f"chmod 644 {remote_path}")
print(f"  补丁文件已上传: {remote_path}")

# 验证容器内可见
stdin, stdout, stderr = ssh.exec_command("docker exec videogen-api-1 ls -la /app/app/static/patches/update_1.0.0_to_1.0.2.zip 2>&1")
print(f"  容器内验证: {stdout.read().decode().strip()}")

sftp.close()
ssh.close()

# 2. 管理员登录
print("\n2. 管理员登录...")
login_resp = requests.post(f'{base}/api/auth/login', json={
    'username': 'admin',
    'password': 'Admin123456'
}, timeout=10)
if login_resp.status_code != 200:
    print(f'  登录失败: {login_resp.text}')
    exit(1)
token = login_resp.json().get('access_token', '')
print(f'  登录成功')

# 3. 检查版本是否已存在
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
list_resp = requests.get(f'{base}/api/admin/versions', headers=headers, timeout=10)
if list_resp.status_code == 200:
    versions = list_resp.json().get('versions', [])
    for v in versions:
        if v['version'] == '1.0.2':
            print(f'  版本 1.0.2 已存在，跳过创建')
            exit(0)

# 4. 创建版本 1.0.2（累加式，不删除老版本）
print("\n3. 注册版本 1.0.2...")
version_data = {
    'version': '1.0.2',
    'update_type': 'patch',
    'from_version': '1.0.0',
    'patch_url': f'{base}/static/patches/update_1.0.0_to_1.0.2.zip',
    'patch_hash': patch_hash,
    'patch_size': patch_size,
    'changelog': ['修复GPU显存显示误报，区分本进程显存和总显存', '修复桌面快捷方式创建失败，改用ps1脚本替代EncodedCommand'],
    'priority': 'normal',
    'force_update': False
}

create_resp = requests.post(f'{base}/api/admin/versions', json=version_data, headers=headers, timeout=10)
print(f'  创建状态: {create_resp.status_code}')
print(f'  响应: {create_resp.text}')

if create_resp.status_code == 200:
    print('\n补丁1.0.2推送成功！客户端启动后将自动检测到更新。')
elif create_resp.status_code == 409:
    print('\n版本已存在，无需重复创建。')
