"""
VideoGenerator - 简化打包脚本

流程：清理 → 安全检查 → PyInstaller打包(spec为唯一配置源) → 后处理 → 验证 → 压缩
不再通过命令行参数覆盖 spec 配置，避免配置冲突。
"""

import os
import sys
import shutil
import glob
import subprocess
import json
import hashlib
import re


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(BASE_DIR, 'VideoGenerator.spec')
OUTPUT_DIR = os.path.join(BASE_DIR, 'dist', 'VideoGenerator')


# ═══════════════════════════════════════════════════════════════
# 第1步：清理
# ═══════════════════════════════════════════════════════════════

def clean_build_dirs():
    """清理构建和输出目录"""
    dirs = ['build', 'dist', '__pycache__']
    for d in dirs:
        p = os.path.join(BASE_DIR, d)
        if os.path.exists(p):
            print(f"  清理 {d}/")
            shutil.rmtree(p, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# 第2步：安全检查
# ═══════════════════════════════════════════════════════════════

def check_packing_safety():
    """运行安全检查脚本"""
    print("\n🔒 安全检查...")
    script = os.path.join(BASE_DIR, 'check_packing_safety.py')
    if not os.path.exists(script):
        print("  ⚠️ check_packing_safety.py 不存在，跳过")
        return
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True, cwd=BASE_DIR
    )
    print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr)
        print("❌ 安全检查失败！打包终止。")
        sys.exit(1)
    print("✅ 安全检查通过")


# ═══════════════════════════════════════════════════════════════
# 第3步：PyInstaller 打包（使用 spec 文件，不传额外参数）
# ═══════════════════════════════════════════════════════════════

def run_pyinstaller():
    """执行 PyInstaller 打包，spec 文件是唯一配置源"""
    print("\n🚀 PyInstaller 打包中...")
    print(f"  spec 文件: {SPEC_FILE}")

    if not os.path.exists(SPEC_FILE):
        print(f"❌ {SPEC_FILE} 不存在！")
        sys.exit(1)

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        SPEC_FILE,
        '--clean',
        '--noconfirm',
    ]

    print(f"  命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=BASE_DIR)

    if result.returncode != 0:
        print("❌ PyInstaller 打包失败！")
        sys.exit(1)

    if not os.path.exists(OUTPUT_DIR):
        print(f"❌ 输出目录不存在: {OUTPUT_DIR}")
        sys.exit(1)

    exe_path = os.path.join(OUTPUT_DIR, 'VideoGenerator.exe')
    if not os.path.exists(exe_path):
        print(f"❌ VideoGenerator.exe 未生成！")
        sys.exit(1)

    print(f"✅ PyInstaller 打包成功: {exe_path}")


# ═══════════════════════════════════════════════════════════════
# 第4步：后处理
# ═══════════════════════════════════════════════════════════════

def post_build():
    """打包后处理：复制辅助文件、生成启动脚本等"""
    print("\n📋 后处理...")

    # 4.1 复制 config.json 到 exe 同级目录
    config_src = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(config_src):
        shutil.copy2(config_src, os.path.join(OUTPUT_DIR, 'config.json'))
        # _internal 里也放一份（PyInstaller 已自动放入，确保一致）
        internal_dir = os.path.join(OUTPUT_DIR, '_internal')
        if os.path.isdir(internal_dir):
            shutil.copy2(config_src, os.path.join(internal_dir, 'config.json'))
        # 生成签名（使用 HMAC-SHA256，与 crypto_utils.py verify_config_signature 一致）
        try:
            import hmac as _hmac
            with open(config_src, 'r', encoding='utf-8') as f:
                content = f.read()
            sig_key = "VideoGen2025ConfigSignatureKey_v1"
            sig = _hmac.new(
                sig_key.encode("utf-8"),
                content.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            for d in [OUTPUT_DIR, internal_dir]:
                if os.path.isdir(d):
                    with open(os.path.join(d, 'config.json.sig'), 'w') as sf:
                        sf.write(sig)
        except Exception:
            pass
        print("  ✅ config.json (含签名)")
    else:
        print("  ❌ config.json 缺失！")
        sys.exit(1)

    # 4.2 复制公钥到 exe 同级
    pubkey_src = os.path.join(BASE_DIR, '.license_verify_pubkey.pem')
    if os.path.exists(pubkey_src):
        shutil.copy2(pubkey_src, os.path.join(OUTPUT_DIR, '.license_verify_pubkey.pem'))
        print("  ✅ .license_verify_pubkey.pem")
    else:
        print("  ❌ .license_verify_pubkey.pem 缺失！")
        sys.exit(1)

    # 4.3 复制 FFmpeg
    _copy_ffmpeg()

    # 4.4 复制 Whisper 模型
    _copy_whisper_models()

    # 4.5 复制辅助文件
    for f, desc in [
        ('LICENSE', '许可证'),
        ('QuickStart.md', '快速入门'),
        ('UserGuide.md', '用户指南'),
    ]:
        src = os.path.join(BASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUTPUT_DIR, f))
            print(f"  ✅ {f} ({desc})")

    # 复制图标
    icon_src = os.path.join(BASE_DIR, 'assets', 'icon.ico')
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(OUTPUT_DIR, 'icon.ico'))
        print("  ✅ icon.ico")

    # 复制快捷方式脚本
    for f in ['CreateShortcut.bat']:
        src = os.path.join(BASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUTPUT_DIR, f))
            print(f"  ✅ {f}")

    # 4.6 生成启动脚本
    _generate_start_scripts()

    # 4.7 生成 version.json
    _generate_version_json()

    # 4.8 生成校验文件
    _generate_checksums()

    # 4.9 清理输出目录中的敏感/多余文件
    _clean_output()

    print("  ✅ 后处理完成")


def _copy_ffmpeg():
    """复制 FFmpeg"""
    print("  📦 复制 FFmpeg...")
    ffmpeg_dest = os.path.join(OUTPUT_DIR, 'ffmpeg')
    os.makedirs(ffmpeg_dest, exist_ok=True)

    # 优先从项目目录的 ffmpeg/ 复制
    local_ffmpeg = os.path.join(BASE_DIR, 'ffmpeg')
    if os.path.isdir(local_ffmpeg):
        for exe in ['ffmpeg.exe', 'ffprobe.exe']:
            src = os.path.join(local_ffmpeg, exe)
            if os.path.exists(src) and os.path.getsize(src) > 1000000:
                shutil.copy2(src, os.path.join(ffmpeg_dest, exe))
                print(f"    ✅ {exe}")
                return

    # 从系统 PATH 查找
    try:
        result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True)
        if result.returncode == 0:
            ffmpeg_exe = os.path.realpath(result.stdout.strip().split('\n')[0].strip())
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            found = False
            for exe in ['ffmpeg.exe', 'ffprobe.exe']:
                src = os.path.join(ffmpeg_dir, exe)
                real = os.path.realpath(src)
                if os.path.exists(real) and os.path.getsize(real) > 1000000:
                    shutil.copy2(real, os.path.join(ffmpeg_dest, exe))
                    print(f"    ✅ {exe}")
                    found = True
            if found:
                return
    except Exception:
        pass

    print("    ⚠️ 未找到 FFmpeg，跳过")


def _copy_whisper_models():
    """复制 Whisper 模型"""
    print("  📦 复制 Whisper 模型...")
    whisper_cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    whisper_dest = os.path.join(OUTPUT_DIR, 'whisper_models')

    if not os.path.exists(whisper_cache):
        print("    ⚠️ Whisper 模型缓存不存在，跳过")
        return

    os.makedirs(whisper_dest, exist_ok=True)
    count = 0
    for f in os.listdir(whisper_cache):
        if f.endswith('.pt'):
            src = os.path.join(whisper_cache, f)
            size_mb = os.path.getsize(src) / (1024 * 1024)
            shutil.copy2(src, os.path.join(whisper_dest, f))
            print(f"    ✅ {f} ({size_mb:.0f}MB)")
            count += 1

    if count == 0:
        print("    ⚠️ 无 .pt 模型文件")
    else:
        print(f"    ✅ 共 {count} 个模型")


def _generate_start_scripts():
    """生成 start.vbs 和 start.bat"""
    # start.vbs - 无控制台启动
    vbs = (
        'On Error Resume Next\n'
        'Set fso = CreateObject("Scripting.FileSystemObject")\n'
        'Set shell = CreateObject("WScript.Shell")\n'
        'appDir = fso.GetParentFolderName(WScript.ScriptFullName)\n'
        'exePath = appDir & "\\VideoGenerator.exe"\n'
        'If Not fso.FileExists(exePath) Then\n'
        '    MsgBox "VideoGenerator.exe 未找到" & vbCrLf & "请确认解压完整，或运行 CheckEnv.bat", vbCritical, "启动失败"\n'
        '    WScript.Quit 1\n'
        'End If\n'
        'shell.CurrentDirectory = appDir\n'
        'If fso.FileExists(appDir & "\\ffmpeg\\ffmpeg.exe") Then\n'
        '    shell.Environment("Process").Item("FFMPEG_BINARY") = appDir & "\\ffmpeg\\ffmpeg.exe"\n'
        'End If\n'
        'shell.Run "VideoGenerator.exe", 1, False\n'
    )
    with open(os.path.join(OUTPUT_DIR, 'start.vbs'), 'w', encoding='gbk') as f:
        f.write(vbs)
    print("  ✅ start.vbs")

    # start.bat - 命令行启动（带检查）
    bat = (
        '@echo off\n'
        'chcp 65001 >nul 2>&1\n'
        'cd /d "%~dp0"\n'
        'if not exist "VideoGenerator.exe" (\n'
        '    echo [ERROR] VideoGenerator.exe not found\n'
        '    pause\n'
        '    exit /b 1\n'
        ')\n'
        'if exist "%~dp0ffmpeg\\ffmpeg.exe" set "FFMPEG_BINARY=%~dp0ffmpeg\\ffmpeg.exe"\n'
        'start "" "VideoGenerator.exe"\n'
    )
    with open(os.path.join(OUTPUT_DIR, 'start.bat'), 'w', encoding='utf-8') as f:
        f.write(bat)
    print("  ✅ start.bat")


def _generate_version_json():
    """生成 version.json"""
    try:
        sys.path.insert(0, BASE_DIR)
        from video_generator.version import __version__, __build_number__
        data = {
            "version": __version__,
            "build_number": __build_number__,
            "updated_at": "",
        }
        with open(os.path.join(OUTPUT_DIR, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✅ version.json (v{__version__})")
    except ImportError:
        print("  ⚠️ 无法生成 version.json")


def _generate_checksums():
    """生成 SHA256 校验文件"""
    print("  🔐 生成校验文件...")
    checksum_path = os.path.join(OUTPUT_DIR, 'file_checksums.txt')
    skip_dirs = {'whisper_models', 'ffmpeg', 'logs', 'output_project', '__pycache__', '.git'}
    skip_exts = {'.log', '.tmp', '.bak'}
    count = 0
    with open(checksum_path, 'w', encoding='utf-8') as f:
        f.write("# VideoGenerator - File Integrity Checksums\n")
        f.write("# 由打包脚本自动生成\n\n")
        for root, dirs, files in os.walk(OUTPUT_DIR):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in sorted(files):
                if any(filename.endswith(ext) for ext in skip_exts):
                    continue
                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, OUTPUT_DIR).replace(os.sep, '/')
                if rel_path == 'file_checksums.txt':
                    continue
                try:
                    h = hashlib.sha256()
                    with open(abs_path, 'rb') as fh:
                        for chunk in iter(lambda: fh.read(8192), b''):
                            h.update(chunk)
                    f.write(f"{h.hexdigest()}  {rel_path}\n")
                    count += 1
                except (OSError, PermissionError):
                    f.write(f"ERROR  {rel_path}\n")
                    count += 1
    print(f"    ✅ {count} 个文件校验")


def _clean_output():
    """清理输出目录中的敏感和多余文件"""
    print("  🧹 清理敏感文件...")

    # 不应出现在输出中的文件
    unwanted_files = [
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt', '.login_creds', '.license_verify_key',
        '.license_cache', '.license_credentials', '.unlocked',
        'generate_signing_keys.py', 'check_packing_safety.py',
        'VideoGenerator.spec', '01build_exe.py', 'pyarmor_config.json',
        'run.py', 'run.pyw', 'requirements.txt',
        'sync_to_server.py', 'pack_patch.py',
    ]

    removed = 0
    for f in unwanted_files:
        for base in [OUTPUT_DIR, os.path.join(OUTPUT_DIR, '_internal')]:
            fp = os.path.join(base, f)
            if os.path.exists(fp):
                os.remove(fp)
                removed += 1

    # 清理非公钥的 .pem 文件
    for base in [OUTPUT_DIR, os.path.join(OUTPUT_DIR, '_internal')]:
        if not os.path.isdir(base):
            continue
        for pem in glob.glob(os.path.join(base, '*.pem')):
            if os.path.basename(pem) != '.license_verify_pubkey.pem':
                os.remove(pem)
                removed += 1

    if removed:
        print(f"    清理 {removed} 个文件")


# ═══════════════════════════════════════════════════════════════
# 第5步：验证
# ═══════════════════════════════════════════════════════════════

def verify_output():
    """验证打包输出"""
    print("\n🔍 验证打包结果...")

    # 5.1 关键文件检查
    required = {
        'VideoGenerator.exe': '主程序',
        '_internal': '运行时目录',
        'config.json': '配置文件',
        '.license_verify_pubkey.pem': 'ECDSA公钥',
    }
    for rel, desc in required.items():
        p = os.path.join(OUTPUT_DIR, rel)
        if os.path.exists(p):
            print(f"  ✅ {desc}({rel})")
        else:
            print(f"  ❌ {desc}({rel}) 缺失！")
            sys.exit(1)

    # 5.2 验证 config.json 内容
    config_path = os.path.join(OUTPUT_DIR, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        api_url = config.get('api_base_url', '')
        if not api_url or any(p in api_url for p in ['localhost', '127.0.0.1', '0.0.0.0']):
            print(f"  ❌ api_base_url = {api_url}，客户无法连接！")
            sys.exit(1)
        print(f"  ✅ api_base_url = {api_url}")

        # API Key 不应为空
        for key in ['cloud_llm_api_key', 'cloud_asr_api_key', 'cloud_image_api_key']:
            if config.get(key, '') != '':
                print(f"  ❌ {key} 不为空！密钥将泄露给客户！")
                sys.exit(1)
        print("  ✅ API Key 字段均为空")
    except json.JSONDecodeError:
        print("  ❌ config.json 格式错误！")
        sys.exit(1)

    # 5.3 敏感文件检查
    sensitive = [
        '.env', 'license.json', '.secret_key', '.license_verify_key',
        'generate_signing_keys.py',
    ]
    found_leak = False
    for f in sensitive:
        for base in [OUTPUT_DIR, os.path.join(OUTPUT_DIR, '_internal')]:
            if os.path.exists(os.path.join(base, f)):
                print(f"  ❌ 发现敏感文件: {f}")
                found_leak = True
    if not found_leak:
        print("  ✅ 无敏感文件泄露")

    # 5.4 输出大小
    total_size = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    print(f"  📦 打包总大小: {total_size / (1024*1024):.0f}MB")
    print("✅ 验证通过")


# ═══════════════════════════════════════════════════════════════
# 第6步：压缩
# ═══════════════════════════════════════════════════════════════

def create_archive():
    """创建 7z 压缩包（非固实压缩，兼容性更好）"""
    print("\n📦 创建压缩包...")

    # 查找 7z
    zip_cmd = None
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "7-Zip", "7z.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "7-Zip", "7z.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            zip_cmd = c
            break
    if not zip_cmd:
        try:
            r = subprocess.run(['7z', '--help'], capture_output=True, timeout=5)
            if r.returncode == 0:
                zip_cmd = '7z'
        except Exception:
            pass

    if not zip_cmd:
        print("  ⚠️ 未找到 7-Zip，跳过压缩")
        print(f"  请手动压缩: {OUTPUT_DIR}")
        return

    from datetime import datetime
    date_stamp = datetime.now().strftime("%Y%m%d")
    archive_name = f"VideoGenerator_{date_stamp}"
    archive_7z = os.path.join(BASE_DIR, 'dist', f"{archive_name}.7z")

    # 非固实压缩 -mx=7，兼容性好，单文件损坏不影响其他文件
    cmd = [zip_cmd, "a", "-t7z", "-mx=7", "-ms=off", archive_7z, "VideoGenerator"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.join(BASE_DIR, 'dist'))

    if result.returncode == 0:
        size_mb = os.path.getsize(archive_7z) / (1024 * 1024)
        print(f"  ✅ 压缩完成: {archive_7z} ({size_mb:.0f}MB)")
        print(f"  💡 非固实压缩，单文件损坏不影响其他文件解压")
    else:
        print(f"  ❌ 压缩失败: {result.stderr[:200]}")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  VideoGenerator 打包脚本 v2")
    print("  spec 文件为唯一配置源，无命令行参数覆盖")
    print("=" * 60)

    # 版本信息
    try:
        sys.path.insert(0, BASE_DIR)
        from video_generator.version import __version__, __build_number__
        print(f"  版本: v{__version__} (build {__build_number__})")
    except ImportError:
        print("  ⚠️ 无法读取版本信息")

    print()

    # 1. 清理
    print("【1/6】清理构建目录...")
    clean_build_dirs()

    # 2. 安全检查
    print("\n【2/6】安全检查...")
    check_packing_safety()

    # 3. 打包
    print("\n【3/6】PyInstaller 打包...")
    run_pyinstaller()

    # 4. 后处理
    print("\n【4/6】后处理...")
    post_build()

    # 5. 验证
    print("\n【5/6】验证...")
    verify_output()

    # 6. 压缩
    print("\n【6/6】压缩...")
    create_archive()

    print("\n" + "=" * 60)
    print("  ✅ 打包完成！")
    print(f"  输出目录: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
