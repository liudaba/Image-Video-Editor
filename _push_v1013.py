import requests
import paramiko
import os
import hashlib
import json
import zipfile
import shutil

BASE = 'https://api.wangzha178.com'
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_PATCHES_DIR = "/root/videogen/app/static/patches"
PATCHES_LOCAL_DIR = r"F:\shipinshengcheng\Image-Video-Editor\patches"
PROJECT_DIR = r"F:\shipinshengcheng\Image-Video-Editor"

NEW_VERSION = "1.0.13"
FROM_VERSIONS = ["1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6", "1.0.7", "1.0.8", "1.0.9", "1.0.10", "1.0.11", "1.0.12"]

CHANGELOG = [
    "全面修复所有时间与本地时间不同步问题",
    "修复垃圾桶目录名时间显示错误(差8小时)",
    "修复视频输出文件名时间显示错误(差8小时)",
    "修复自动更新时间戳显示错误",
    "统一使用time.localtime()替代datetime.now()",
    "清理不再需要的datetime模块导入",
]

CHANGED_FILES = [
    "video_generator/mixins/logging.py",
    "video_generator/mixins/resource.py",
    "video_generator/mixins/video.py",
    "video_generator/app.py",
    "video_generator/auto_updater.py",
    "video_generator/version.py",
]


def compute_file_info(filepath):
    full_path = os.path.join(PROJECT_DIR, filepath)
    data = open(full_path, "rb").read()
    sha256 = hashlib.sha256(data).hexdigest()
    size = os.path.getsize(full_path)
    return {"path": filepath, "sha256": sha256, "size": size}


def create_patch_zip(from_ver):
    patch_dir = os.path.join(PATCHES_LOCAL_DIR, f"patch_{from_ver}_to_{NEW_VERSION}")
    os.makedirs(patch_dir, exist_ok=True)

    for filepath in CHANGED_FILES:
        src = os.path.join(PROJECT_DIR, filepath)
        dst = os.path.join(patch_dir, filepath)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    manifest = {
        "version": NEW_VERSION,
        "from_version": from_ver,
        "files": [compute_file_info(f) for f in CHANGED_FILES],
        "release_notes": "\n".join(CHANGELOG),
        "force_update": False,
    }

    manifest_path = os.path.join(patch_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    zip_path = os.path.join(PATCHES_LOCAL_DIR, f"update_{from_ver}_to_{NEW_VERSION}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(patch_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, patch_dir)
                zf.write(file_path, arcname)

    shutil.rmtree(patch_dir)

    size = os.path.getsize(zip_path)
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    sha256 = h.hexdigest()

    with open(zip_path, "rb") as f:
        zip_content = f.read()
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest_data = json.loads(zf.read("manifest.json"))
    manifest_obj = manifest_data
    assert isinstance(manifest_obj["files"], list), "files must be list"
    for item in manifest_obj["files"]:
        assert "path" in item and "sha256" in item and "size" in item, f"missing field: {item}"

    print(f"  补丁: {os.path.basename(zip_path)} ({size/1024:.1f} KB, sha256={sha256[:16]}...) manifest验证通过")

    return {
        "path": zip_path,
        "size": size,
        "sha256": sha256,
        "filename": os.path.basename(zip_path),
    }


print("=" * 60)
print(f"  v{NEW_VERSION} 补丁生成与上传")
print("=" * 60)

print("\n[1/5] 生成补丁文件...")
patch_infos = {}
for from_ver in FROM_VERSIONS:
    info = create_patch_zip(from_ver)
    patch_infos[from_ver] = info

print("\n[2/5] 上传补丁文件到服务器...")
with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
    password = f.read().strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {SERVER_PATCHES_DIR} && chmod 777 {SERVER_PATCHES_DIR}", timeout=10)
stdout.channel.recv_exit_status()

sftp = ssh.open_sftp()

for from_ver in FROM_VERSIONS:
    info = patch_infos[from_ver]
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

print("\n[3/5] 管理员登录...")
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

print("\n[4/5] 清理旧版本记录并注册新版本...")
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

print("\n[5/5] 验证：模拟客户端检查更新")
for from_ver in ["1.0.12", "1.0.11", "1.0.5", "1.0.0"]:
    check_resp = requests.get(f'{BASE}/api/version/latest', params={
        'current_version': from_ver,
        'platform': 'windows'
    }, timeout=10)
    if check_resp.status_code == 200:
        data = check_resp.json()
        update = data.get('update_available', False) or data.get('has_update', False)
        new_ver = data.get('version', 'N/A')
        update_type = data.get('update_type', 'N/A')
        patch_size = data.get('patch_size', 'N/A')
        print(f"  {from_ver}: update={update}, version={new_ver}, type={update_type}, size={patch_size}")
    else:
        print(f"  {from_ver}: ERROR {check_resp.status_code} - {check_resp.text[:100]}")

print("\n" + "=" * 60)
print(f"  v{NEW_VERSION} 部署完成！")
print("=" * 60)
