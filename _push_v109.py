"""v1.0.9 补丁生成、上传与版本注册

优化分镜提示词系统：
- 修复女人头像问题（替换模板示例、增加性别中性规则、修改妻子映射、放宽面部抑制）
- Flux/SD3适配（独立清洗逻辑、宽松版规则、保留自然语言描述）
- 丰富场景多样性背景列表（按内容类型）
- 统一非写实风格检测关键词列表
"""
import sys
import os
import json
import zipfile
import requests
import paramiko
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_generator.auto_updater import create_patch_zip

BASE = 'https://api.wangzha178.com'
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_PATCHES_DIR = "/root/videogen/app/static/patches"
PATCHES_LOCAL_DIR = r"F:\shipinshengcheng\Image-Video-Editor\patches"

NEW_VERSION = "1.0.9"
FROM_VERSIONS = ["1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8"]
CHANGELOG = [
    "优化分镜脚本提示词系统，修复图片莫名出现女人头像的问题",
    "LLM提示词模板增加性别中性规则，避免默认生成女性形象",
    "修复'妻子'关键词映射为'woman'导致强制生成女性形象",
    "增强负面提示词面部抑制，减少不相关的面部特写",
    "Flux/SD3模型适配：保留自然语言描述，不再被清洗逻辑破坏",
    "Flux/SD3模型使用宽松版核心规则，允许氛围词提升出图质量",
    "丰富场景多样性背景列表，支持科普/自然/经济/历史/生活等多种内容类型",
    "统一非写实风格检测关键词列表，消除3个文件间的不一致",
    "修复model_type未定义导致分镜生成崩溃的严重Bug",
]

ALL_CHANGED_FILES = [
    "video_generator/templates.py",
    "video_generator/mixins/shots.py",
    "video_generator/prompts_arv.py",
    "video_generator/model_profiles.py",
    "video_generator/version.py",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("=" * 60)
print(f"  v{NEW_VERSION} 补丁生成、上传与版本注册")
print("=" * 60)

# ========== 第一步：生成补丁包 ==========
print(f"\n[1/4] 生成补丁包 ({len(FROM_VERSIONS)} 个旧版本)...")

patch_infos = {}
for from_ver in FROM_VERSIONS:
    output_path = os.path.join(PATCHES_LOCAL_DIR, f"update_{from_ver}_to_{NEW_VERSION}.zip")
    if os.path.exists(output_path):
        os.remove(output_path)
    print(f"  生成: {from_ver} -> {NEW_VERSION}")
    result = create_patch_zip(
        version=NEW_VERSION,
        from_version=from_ver,
        changed_files=ALL_CHANGED_FILES,
        output_path=output_path,
        release_notes="\n".join(CHANGELOG),
        force_update=False,
        base_dir=BASE_DIR,
    )
    print(f"    SHA256: {result['sha256'][:16]}..., 大小: {result['size']/1024:.1f} KB, 文件数: {result['file_count']}")
    patch_infos[from_ver] = {
        'path': result['path'],
        'size': result['size'],
        'sha256': result['sha256'],
        'filename': os.path.basename(result['path']),
    }

# ========== 第二步：上传补丁到服务器 ==========
print(f"\n[2/4] 上传补丁文件到服务器...")

with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
    password = f.read().strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {SERVER_PATCHES_DIR} && chmod 777 {SERVER_PATCHES_DIR}", timeout=10)
stdout.channel.recv_exit_status()

sftp = ssh.open_sftp()

for from_ver, info in patch_infos.items():
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

# ========== 第三步：管理员登录 + 清理旧版本记录 ==========
print("\n[3/4] 注册版本和补丁...")

login_resp = requests.post(f'{BASE}/api/auth/login', json={
    'username': 'admin',
    'password': 'Admin123456'
}, timeout=10)
if login_resp.status_code != 200:
    print(f'  登录失败: {login_resp.text}')
    sys.exit(1)
token = login_resp.json().get('access_token', '')
print(f'  管理员登录成功')

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

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
print(f"  已删除 {deleted} 条旧v{NEW_VERSION}记录")

# ========== 第四步：注册版本和补丁 ==========
for from_ver in FROM_VERSIONS:
    info = patch_infos[from_ver]

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

# ========== 验证 ==========
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
        patch_hash = data.get('patch_hash', 'N/A')
        print(f"  {from_ver}: update={update}, type={update_type}, size={patch_size}, hash={str(patch_hash)[:16]}...")
    else:
        print(f"  {from_ver}: ERROR {check_resp.status_code} - {check_resp.text[:100]}")

print("\n" + "=" * 60)
print(f"  v{NEW_VERSION} 部署完成！")
print("=" * 60)
