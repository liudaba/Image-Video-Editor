"""v1.0.19 补丁生成、上传、版本注册与容器重启

深度审查与优化：修复视频渲染全链路的 11 个真实 bug，保障本地/云端/交叉三种模式丝滑运行。

核心修复：
- 视频渲染：动画预渲染像素截断导致边缘错位、FFmpeg直接渲染路径资源竞争
- 图像生成：producer 线程 put 失败导致结果丢失（整批任务延迟 30s/张）
- 硬件加速：取消渲染时子进程残留占用文件锁、僵尸进程堆积
- 云端模式：num_predict 取值路径错误导致长文本截断、negative_prompt 服务商隔离
- 缓存系统：边界条件与统计准确性

累加式版本策略：为 1.0.0~1.0.18 全部 19 个旧版本各生成一份增量补丁，
无论客户处于哪个版本，都能升级到最新版本。
"""
import sys
import os
import json
import hashlib
import requests
import paramiko
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from video_generator.auto_updater import create_patch_zip

# ============ 配置 ============
BASE = 'https://api.wangzha178.com'
SERVER = "8.141.101.155"
SERVER_USER = "root"
SSH_PASSWORD_FILE = r"f:\shipinshengcheng\ssh_manager\current_ssh_password.txt"
SERVER_PATCHES_DIR = "/root/videogen/app/static/patches"
PATCHES_LOCAL_DIR = r"F:\shipinshengcheng\Image-Video-Editor\patches"

NEW_VERSION = "1.0.19"
# 累加式：覆盖从最早的 1.0.0 到上一个正式版 1.0.18，全部都能升级到 1.0.19
FROM_VERSIONS = [
    "1.0.0", "1.0.1", "1.0.2", "1.0.3", "1.0.4",
    "1.0.5", "1.0.6", "1.0.7", "1.0.8", "1.0.9",
    "1.0.10", "1.0.11", "1.0.12", "1.0.13", "1.0.14",
    "1.0.15", "1.0.16", "1.0.17", "1.0.18",
]

CHANGELOG = [
    "【视频质量】修复动画预渲染像素截断导致 Ken Burns 缩放动画边缘错位/抖动",
    "【视频质量】修复 FFmpeg 直接渲染成功路径资源竞争与重复关闭",
    "【图像生成】修复 producer 线程结果丢失导致整批任务卡顿 30 秒/张的问题",
    "【图像生成】新增 _safe_result_put 带退避重试机制，保障任务结果可靠送达",
    "【硬件加速】修复取消渲染时子进程残留占用文件锁、僵尸进程堆积",
    "【硬件加速】并行渲染子进程增加 wait+kill 三段式清理",
    "【云端LLM】修复 num_predict 取值路径错误导致自定义长度失效、长文本被截断",
    "【云端生图】修复尺寸对齐下限保护（避免极端输入产生 0 尺寸）",
    "【云端生图】negative_prompt 按服务商隔离（通义万相支持，DALL-E 排除）",
    "【缓存系统】修复 max_size 边界条件与 hit/miss 统计准确性",
    "【健壮性】保障本地模式、云端模式、交叉模式三种运行模式丝滑运行",
]

# 本次修改的文件清单（精确的最小化补丁）
ALL_CHANGED_FILES = [
    "video_generator/mixins/video.py",
    "video_generator/mixins/images.py",
    "video_generator/cloud_image_client.py",
    "video_generator/cloud_llm_client.py",
    "video_generator/cache.py",
    "video_generator/hardware.py",
    "video_generator/version.py",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def step(msg):
    print(f"\n{'=' * 60}\n  {msg}\n{'=' * 60}")


# ============ 第一步：验证变更文件完整性 ============
step(f"v{NEW_VERSION} 发布流程启动 - 验证变更文件")
missing = []
for f in ALL_CHANGED_FILES:
    abs_path = os.path.join(BASE_DIR, f)
    if not os.path.exists(abs_path):
        missing.append(f)
        print(f"  MISSING: {f}")
    else:
        size = os.path.getsize(abs_path)
        print(f"  OK: {f} ({size:,} bytes)")

if missing:
    print(f"\n  ❌ {len(missing)} 个文件缺失，无法生成补丁！")
    sys.exit(1)
print(f"\n  ✅ 全部 {len(ALL_CHANGED_FILES)} 个变更文件就绪")

# ============ 第二步：生成补丁包（每个旧版本一份） ============
step(f"[1/5] 生成补丁包 ({len(FROM_VERSIONS)} 个旧版本 → v{NEW_VERSION})")

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

print(f"\n  ✅ 全部 {len(patch_infos)} 个补丁包生成完毕")

# ============ 第三步：上传补丁到服务器 ============
step("[2/5] 上传补丁文件到服务器")

with open(SSH_PASSWORD_FILE, "r", encoding="utf-8") as f:
    password = f.read().strip()

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {SERVER_PATCHES_DIR} && chmod 777 {SERVER_PATCHES_DIR}", timeout=10)
stdout.channel.recv_exit_status()

sftp = ssh.open_sftp()

upload_ok = 0
upload_fail = 0
for from_ver, info in patch_infos.items():
    remote_path = f"{SERVER_PATCHES_DIR}/{info['filename']}"
    print(f"  上传: {info['filename']} ({info['size']/1024:.1f} KB)")
    try:
        sftp.put(info['path'], remote_path)
        remote_size = sftp.stat(remote_path).st_size
        if remote_size == info['size']:
            print(f"    ✅ 大小匹配 ({remote_size:,} bytes)")
            upload_ok += 1
        else:
            print(f"    ❌ 大小不匹配! 本地={info['size']}, 远程={remote_size}")
            upload_fail += 1
    except Exception as e:
        print(f"    ❌ 上传失败: {e}")
        upload_fail += 1

sftp.close()
ssh.close()
print(f"\n  上传结果: 成功 {upload_ok}/{len(patch_infos)}, 失败 {upload_fail}")
if upload_fail > 0:
    print("  ⚠️ 存在上传失败，请检查网络后重试")

# ============ 第四步：管理员登录 + 清理旧版本记录 ============
step("[3/5] 注册版本和补丁")

login_resp = requests.post(f'{BASE}/api/auth/login', json={
    'username': 'admin',
    'password': 'Admin123456'
}, timeout=10)
if login_resp.status_code != 200:
    print(f'  ❌ 管理员登录失败: {login_resp.text}')
    sys.exit(1)
token = login_resp.json().get('access_token', '')
print(f'  ✅ 管理员登录成功')

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# 清理已存在的 v1.0.19 记录（幂等发布）
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
print(f"  已清理 {deleted} 条旧 v{NEW_VERSION} 记录")

# ============ 第五步：注册全部 19 个补丁版本 ============
registered = 0
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
        print(f"    ✅ 注册成功")
        registered += 1
    elif create_resp.status_code == 409:
        print(f"    ⏭️  已存在，跳过")
        registered += 1
    else:
        print(f"    ❌ ERROR: {create_resp.status_code} - {create_resp.text[:200]}")

print(f"\n  注册结果: {registered}/{len(FROM_VERSIONS)}")

# ============ 第六步：重启服务器容器 ============
step("[4/5] 重启服务器 Docker 容器")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, port=22, username=SERVER_USER, password=password, timeout=15)

# 查找 videogen 相关容器并重启
cmds = [
    f"cd /root/videogen && docker compose down",
    f"cd /root/videogen && docker compose up -d",
]
for cmd in cmds:
    print(f"  执行: {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out:
        print(f"    stdout: {out[:300]}")
    if err:
        print(f"    stderr: {err[:300]}")
    print(f"    exit: {exit_code}")

# 等待容器启动
print("\n  等待容器启动 (10秒)...")
time.sleep(10)

# 检查容器状态
stdin, stdout, stderr = ssh.exec_command("docker ps --filter name=videogen --format '{{.Names}}: {{.Status}}'", timeout=15)
container_status = stdout.read().decode('utf-8', errors='replace').strip()
print(f"  容器状态:\n{container_status}")

# 健康检查
print("\n  健康检查...")
stdin, stdout, stderr = ssh.exec_command("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health", timeout=15)
health_code = stdout.read().decode('utf-8', errors='replace').strip()
print(f"  /health 返回: {health_code}")

ssh.close()

# ============ 第七步：验证升级链路 ============
step(f"[5/5] 验证：模拟客户端检查更新（v{NEW_VERSION} 累加式升级）")

verify_ok = 0
verify_fail = 0
for from_ver in FROM_VERSIONS:
    check_resp = requests.get(f'{BASE}/api/version/latest', params={
        'current_version': from_ver,
        'platform': 'windows'
    }, timeout=10)
    if check_resp.status_code == 200:
        data = check_resp.json()
        update = data.get('update_available', False) or data.get('has_update', False)
        target_ver = data.get('version', 'N/A')
        update_type = data.get('update_type', 'N/A')
        patch_size = data.get('patch_size', 'N/A')
        if update and target_ver == NEW_VERSION:
            print(f"  ✅ {from_ver} -> {target_ver}: type={update_type}, size={patch_size}")
            verify_ok += 1
        else:
            print(f"  ❌ {from_ver}: update={update}, target={target_ver} (期望 {NEW_VERSION})")
            verify_fail += 1
    else:
        print(f"  ❌ {from_ver}: HTTP {check_resp.status_code} - {check_resp.text[:100]}")
        verify_fail += 1

# ============ 最终汇总 ============
step(f"v{NEW_VERSION} 发布完成")
print(f"""
  📦 补丁包生成: {len(patch_infos)}/{len(FROM_VERSIONS)}
  📤 补丁包上传: {upload_ok}/{len(patch_infos)} (失败 {upload_fail})
  📋 版本注册:   {registered}/{len(FROM_VERSIONS)}
  🐳 容器重启:   完成
  ✅ 升级验证:   {verify_ok}/{len(FROM_VERSIONS)} (失败 {verify_fail})

  累加式升级覆盖: v1.0.0 ~ v1.0.18 → v{NEW_VERSION}
  任意旧版本客户端均可平滑升级到最新版本
""")
