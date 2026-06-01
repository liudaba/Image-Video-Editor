import requests
import paramiko
import os
import hashlib

BASE = 'https://api.wangzha178.com'
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_PATCHES_DIR = "/root/videogen/app/static/patches"
PATCHES_LOCAL_DIR = r"F:\shipinshengcheng\Image-Video-Editor\patches"

NEW_VERSION = "1.0.10"
FROM_VERSIONS = ["1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8", "1.0.9"]
CHANGELOG = [
    "修复图片生成GPU过热问题：模型参数动态适配",
    "修复sd_generator硬编码SD1.5参数导致Flux/SDXL/SD3生成异常",
    "修复强制VAE覆盖导致非SD1.5模型显存浪费",
    "优化关键帧增强参数：Flux/SD3温和增强，SD1.5/SDXL适度增强",
    "修复重试间隔过短导致GPU持续满载，改为递增等待(5->10->20秒)",
    "修复缓存key缺少模型名导致切换模型后返回旧图片",
    "降低并发上限从6到4，减少GPU压力",
]

def get_patch_info(from_ver):
    patch_file = os.path.join(PATCHES_LOCAL_DIR, f"update_{from_ver}_to_{NEW_VERSION}.zip")
    if not os.path.exists(patch_file):
        print(f"  ERROR: 补丁文件不存在: {patch_file}")
        return None
    size = os.path.getsize(patch_file)
    h = hashlib.sha256()
    with open(patch_file, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    sha256 = h.hexdigest()
    return {
        'path': patch_file,
        'size': size,
        'sha256': sha256,
        'filename': os.path.basename(patch_file),
    }

print("=" * 60)
print(f"  v{NEW_VERSION} 补丁上传与版本注册")
print("=" * 60)

print("\n[1/4] 上传补丁文件到服务器...")
with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
    password = f.read().strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {SERVER_PATCHES_DIR} && chmod 777 {SERVER_PATCHES_DIR}", timeout=10)
stdout.channel.recv_exit_status()

sftp = ssh.open_sftp()

for from_ver in FROM_VERSIONS:
    info = get_patch_info(from_ver)
    if not info:
        continue
    remote_path = f"{SERVER_PATCHES_DIR}/{info['filename']}"
    print(f"  上传: {info['filename']} ({info['size']/1024:.1f} KB)")
    sftp.put(info['path'], remote_path)
    remote_size = sftp.stat(remote_path).st_size
    if remote_size == info['size']:
        print(f"    OK: 大小匹配 ({remote_size} bytes)")
    else:
        print(f"    ERROR: 大小不匹配! 本地={info['size']}, 远程={remote_size}")

sftp.close()
ssh.close()

print("\n[2/4] 管理员登录...")
login_resp = requests.post(f'{BASE}/api/auth/login', json={
    'username': 'admin',
    'password': 'Admin123456'
}, timeout=10)
if login_resp.status_code != 200:
    print(f'  登录失败: {login_resp.text}')
    exit(1)
token = login_resp.json().get('access_token', '')
print(f'  登录成功')

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

print("\n[3/4] 清理旧版本记录...")
list_resp = requests.get(f'{BASE}/api/admin/versions', headers=headers, timeout=10)
versions = list_resp.json().get('versions', [])
deleted = 0
for v in versions:
    if v.get('version') == NEW_VERSION:
        vid = v.get('id')
        del_resp = requests.delete(f'{BASE}/api/admin/versions/{vid}', headers=headers, timeout=10)
        if del_resp.status_code == 200:
            deleted += 1
            print(f"  删除旧记录: id={vid}, from={v.get('from_version')}")
        else:
            print(f"  删除失败: id={vid}, {del_resp.text[:100]}")
print(f"  已删除 {deleted} 条旧v{NEW_VERSION}记录")

print("\n[4/4] 注册版本和补丁...")
for from_ver in FROM_VERSIONS:
    info = get_patch_info(from_ver)
    if not info:
        continue

    version_data = {
        'version': NEW_VERSION,
        'update_type': 'patch',
        'from_version': from_ver,
        'patch_url': f'{BASE}/static/patches/{info["filename"]}',
        'patch_hash': info['sha256'],
        'patch_size': info['size'],
        'changelog': CHANGELOG,
        'priority': 'normal',
        'force_update': False,
    }

    print(f"  注册: {from_ver} -> {NEW_VERSION}")
    create_resp = requests.post(f'{BASE}/api/admin/versions', json=version_data, headers=headers, timeout=10)
    if create_resp.status_code == 200:
        print(f"    OK: 注册成功")
    elif create_resp.status_code == 409:
        print(f"    SKIP: 已存在")
    else:
        print(f"    ERROR: {create_resp.status_code} - {create_resp.text[:200]}")

print("\n" + "=" * 60)
print("  验证：模拟客户端检查更新")
print("=" * 60)
for from_ver in FROM_VERSIONS:
    check_resp = requests.get(f'{BASE}/api/version/latest', params={
        'current_version': from_ver,
        'platform': 'windows'
    }, timeout=10)
    if check_resp.status_code == 200:
        data = check_resp.json()
        update = data.get('update_available', False) or data.get('has_update', False)
        patch_url = data.get('patch_url', 'N/A')
        update_type = data.get('update_type', 'N/A')
        patch_size = data.get('patch_size', 'N/A')
        print(f"  {from_ver}: update={update}, type={update_type}, size={patch_size}")
    else:
        print(f"  {from_ver}: ERROR {check_resp.status_code} - {check_resp.text[:100]}")

print("\n" + "=" * 60)
print(f"  v{NEW_VERSION} 部署完成！")
print("=" * 60)
