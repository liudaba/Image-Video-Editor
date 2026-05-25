"""
VideoGenerator - Portable Build Script (Embedded Python + Source Code)
内嵌Python环境 + 源码外置模式，支持补丁更新直接替换.py文件

打包后目录结构:
  VideoGenerator/
  ├── python/                    内嵌Python环境
  │   ├── python.exe
  │   ├── Lib/
  │   └── Scripts/
  ├── video_generator/           源码（补丁更新可直接替换）
  │   ├── __init__.py
  │   ├── app.py
  │   ├── auto_updater.py
  │   ├── license_manager.py
  │   └── ...
  ├── run.py                     入口脚本
  ├── config.json                配置文件
  ├── version.json               版本信息
  ├── .license_verify_pubkey.pem ECDSA公钥
  ├── assets/                    资源文件
  │   └── icon.ico
  ├── ffmpeg/                    FFmpeg
  ├── whisper_models/            Whisper模型
  ├── VideoGenerator.exe         启动器（可选，也可用start.bat）
  ├── start.bat                  启动脚本
  ├── start.vbs                  无窗口启动
  ├── CheckEnv.bat               环境检查
  └── FirstRunSetup.bat          首次运行引导
"""

import os
import sys
import shutil
import glob
import subprocess
import json
import re
import hashlib
import hmac as _hmac
from pathlib import Path


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_NAME = "VideoGenerator"


def _load_core_modules_config():
    """从 pyarmor_config.json 加载核心模块列表"""
    config_path = os.path.join(BASE_DIR, "pyarmor_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("core_modules", [])
    return []


def clean_build_dirs():
    """清理旧的构建目录"""
    dirs_to_clean = ['dist', 'dependencies_package', 'installer_output']
    for dir_name in dirs_to_clean:
        path = os.path.join(BASE_DIR, dir_name)
        if os.path.exists(path):
            print(f"  清理 {dir_name}/")
            try:
                shutil.rmtree(path)
            except PermissionError:
                # Windows下目录被占用时，尝试强制删除
                import subprocess
                print(f"    常规删除失败，尝试强制删除...")
                try:
                    subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', path],
                                   capture_output=True, timeout=60)
                except Exception as e:
                    print(f"    强制删除也失败: {e}")
                    print(f"    请手动关闭占用 {dir_name} 的程序后重试")
                    raise
    for zip_pattern in ['dist/*.zip', 'dist/*.7z']:
        for zf in glob.glob(os.path.join(BASE_DIR, zip_pattern)):
            print(f"  删除 {os.path.basename(zf)}")
            os.remove(zf)


def clean_temp_files():
    """清理临时文件"""
    print("\n清理临时文件...")
    patterns = ['**/*.bak', '**/*.tmp', '**/*TEMP*.mp4']
    for pattern in patterns:
        for f in glob.glob(os.path.join(BASE_DIR, pattern), recursive=True):
            try:
                os.remove(f)
            except OSError:
                pass
    for lnk in ['回收站.lnk']:
        path = os.path.join(BASE_DIR, lnk)
        if os.path.exists(path):
            os.remove(path)
    print("  临时文件清理完成\n")


def check_packing_safety():
    """执行打包安全检查"""
    print("\n执行打包安全检查...")
    safety_script = os.path.join(BASE_DIR, 'check_packing_safety.py')
    if os.path.exists(safety_script):
        result = subprocess.run([sys.executable, safety_script], capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
            print("\n安全检查失败! 打包终止。")
            sys.exit(1)
        else:
            print(result.stdout)
            print("  安全检查通过!")
    else:
        print("  安全检查脚本不存在，跳过检查。")


def _obfuscate_core_modules():
    """混淆核心安全模块（PyArmor）"""
    print("\n混淆核心安全模块（PyArmor）...")

    pyarmor_cmd = None
    for candidate in ["pyarmor", os.path.join(os.path.dirname(sys.executable), "pyarmor.exe")]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pyarmor_cmd = candidate
                break
        except Exception:
            continue

    if not pyarmor_cmd:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pyarmor", "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pyarmor_cmd = [sys.executable, "-m", "pyarmor"]
        except Exception:
            pass

    if not pyarmor_cmd:
        print("  PyArmor 未安装，跳过混淆")
        return False

    obf_output = os.path.join(BASE_DIR, "dist_obfuscated")
    if os.path.exists(obf_output):
        shutil.rmtree(obf_output)
    os.makedirs(obf_output, exist_ok=True)

    core_modules = _load_core_modules_config()
    if not core_modules:
        print("  无核心模块配置，跳过混淆")
        return False

    backup_dir = os.path.join(BASE_DIR, "_obf_backup")
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)

    success_count = 0
    obfuscated_modules = []  # 只记录成功混淆的模块
    for module_path in core_modules:
        src = os.path.join(BASE_DIR, module_path)
        if not os.path.exists(src):
            print(f"  跳过不存在的模块: {module_path}")
            continue

        module_output = os.path.join(obf_output, os.path.dirname(module_path))
        os.makedirs(module_output, exist_ok=True)

        backup_path = os.path.join(backup_dir, module_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(src, backup_path)

        print(f"  混淆: {module_path}")
        if isinstance(pyarmor_cmd, list):
            cmd_base = pyarmor_cmd
        else:
            cmd_base = [pyarmor_cmd]
        cmd = cmd_base + [
            "gen",
            "--output", module_output,
            "--assert-call",
            "--assert-import",
            src
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
        if result.returncode != 0:
            print(f"  混淆失败: {module_path}")
            print(f"     {result.stderr[:200]}")
            continue
        success_count += 1
        obfuscated_modules.append(module_path)

    if success_count == 0:
        print("  所有模块混淆失败，将使用原始文件继续打包")
        shutil.rmtree(backup_dir)
        return False

    # 只替换成功混淆的模块
    for module_path in obfuscated_modules:
        obf_src = os.path.join(obf_output, module_path)
        orig_dst = os.path.join(BASE_DIR, module_path)
        if os.path.exists(obf_src):
            shutil.copy2(obf_src, orig_dst)
            print(f"  替换: {module_path}")

    print(f"  混淆完成: {success_count}/{len(core_modules)} 个模块")
    print(f"  原始文件备份在: _obf_backup/")
    return True


def _restore_original_modules():
    """恢复原始源码文件"""
    backup_dir = os.path.join(BASE_DIR, "_obf_backup")
    if not os.path.isdir(backup_dir):
        return

    print("\n恢复原始源码文件...")
    core_modules = _load_core_modules_config()

    for module_path in core_modules:
        backup_path = os.path.join(backup_dir, module_path)
        orig_path = os.path.join(BASE_DIR, module_path)
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, orig_path)
            print(f"  恢复: {module_path}")

    shutil.rmtree(backup_dir)
    obf_output = os.path.join(BASE_DIR, "dist_obfuscated")
    if os.path.exists(obf_output):
        shutil.rmtree(obf_output)
    print("  原始文件已恢复\n")


def _prepare_embedded_python(output_dir):
    """准备内嵌Python环境"""
    print("\n准备内嵌Python环境...")

    python_dest = os.path.join(output_dir, "python")
    if os.path.exists(python_dest):
        shutil.rmtree(python_dest)

    # 策略1: 使用当前运行的Python环境
    current_python = os.path.dirname(sys.executable)
    python_exe = os.path.join(current_python, "python.exe")

    if not os.path.exists(python_exe):
        print("  错误: 找不到当前Python环境!")
        sys.exit(1)

    # 复制Python环境（精简版）
    print(f"  从 {current_python} 复制Python环境...")

    # 必须复制的核心文件
    core_files = [
        "python.exe",
        "pythonw.exe",   # 无控制台窗口启动（start.vbs使用）
        "python3.dll",
        "python310.dll",
        "python311.dll",
        "python312.dll",
        "vcruntime140.dll",     # VC++运行时（Python必需）
        "vcruntime140_1.dll",   # VC++运行时（Python必需）
    ]
    os.makedirs(python_dest, exist_ok=True)

    for f in core_files:
        src = os.path.join(current_python, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(python_dest, f))
            print(f"  复制 {f}")

    # 复制Lib目录
    lib_src = os.path.join(current_python, "Lib")
    lib_dest = os.path.join(python_dest, "Lib")
    if os.path.exists(lib_src):
        print(f"  复制 Lib/ 目录...")
        # 注意：不要排除unittest/distutils等，很多第三方包依赖它们
        # 只排除纯开发/文档相关的目录
        shutil.copytree(lib_src, lib_dest, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.pyo',
            'test', 'tests',           # Python标准库测试目录
            'idlelib',                  # IDLE编辑器
            'turtledemo',              # 海龟绘图演示
            'site-packages',           # site-packages单独处理
        ))
        # tkinter需要保留（GUI程序依赖）- 已在上面复制中保留

    # 复制site-packages（只复制项目依赖的包）
    sp_src = os.path.join(lib_src, "site-packages")
    sp_dest = os.path.join(lib_dest, "site-packages")
    if os.path.exists(sp_src):
        print(f"  复制 site-packages/ (项目依赖)...")
        os.makedirs(sp_dest, exist_ok=True)

        # 排除的包（开发工具、后端专用、大型无关包）
        # 使用黑名单策略：复制所有，只排除明确不需要的
        # 注意：packaging 保留！很多包的元数据读取依赖它
        exclude_packages = {
            # 开发/构建工具
            'pip', 'pip-_internal', 'setuptools', 'wheel', 'build',
            'distlib', 'installer',
            # 后端专用（注意：httpx/anyio/pydantic 被openai等包依赖，不可排除）
            'fastapi', 'uvicorn', 'sqlalchemy', 'redis',
            'asyncpg', 'aiosqlite', 'paramiko', 'bcrypt',
            'passlib', 'python_jose', 'python_multipart',
            'websockets', 'starlette',
            'httptools', 'uvloop',
            'databases', 'alembic', 'async_timeout',
            # 大型无关包
            'PyQt5', 'PyQt6', 'matplotlib', 'notebook',
            'IPython', 'jupyter', 'tornado', 'sphinx',
            'pytest', 'nose', 'mock', 'coverage',
        }

        # 对应的dist-info前缀（排除包的元数据）
        exclude_dist_info_prefixes = set()
        for pkg in exclude_packages:
            exclude_dist_info_prefixes.add(pkg.lower().replace('-', '_'))

        copied_count = 0
        for item in os.listdir(sp_src):
            src_item = os.path.join(sp_src, item)
            item_lower = item.lower().replace('-', '_')

            # 检查是否在排除列表中
            should_skip = False

            # 检查包目录
            for exc in exclude_packages:
                if item_lower.startswith(exc.lower().replace('-', '_')):
                    should_skip = True
                    break

            # 检查dist-info：只排除黑名单包的dist-info
            if item.endswith('.dist-info') or item.endswith('.egg-info'):
                for prefix in exclude_dist_info_prefixes:
                    if item_lower.startswith(prefix):
                        should_skip = True
                        break
                # 其他dist-info保留（包元数据，moviepy等需要）

            if should_skip:
                continue

            dst_item = os.path.join(sp_dest, item)
            try:
                if os.path.isdir(src_item):
                    shutil.copytree(src_item, dst_item,
                                   ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
                else:
                    shutil.copy2(src_item, dst_item)
                copied_count += 1
            except Exception as e:
                print(f"  警告: 复制 {item} 失败: {e}")

        print(f"  复制了 {copied_count} 个包/文件")

        # 验证dist-info完整性：确保所有非排除包的dist-info都被复制
        missing_dist_info = []
        for item in os.listdir(sp_src):
            if not (item.endswith('.dist-info') or item.endswith('.egg-info')):
                continue
            item_lower = item.lower().replace('-', '_')
            # 检查是否在排除列表中
            is_excluded = False
            for prefix in exclude_dist_info_prefixes:
                if item_lower.startswith(prefix):
                    is_excluded = True
                    break
            if is_excluded:
                continue
            # 检查目标是否存在
            if not os.path.exists(os.path.join(sp_dest, item)):
                missing_dist_info.append(item)

        if missing_dist_info:
            print(f"  ⚠️ 发现 {len(missing_dist_info)} 个缺失的dist-info，正在补充复制...")
            for item in missing_dist_info:
                src_item = os.path.join(sp_src, item)
                dst_item = os.path.join(sp_dest, item)
                try:
                    if os.path.isdir(src_item):
                        shutil.copytree(src_item, dst_item,
                                       ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
                    else:
                        shutil.copy2(src_item, dst_item)
                    print(f"    + 补充: {item}")
                except Exception as e2:
                    print(f"    ✗ 补充失败: {item}: {e2}")
            print(f"  dist-info补充完成")

    # 复制DLLs目录
    dlls_src = os.path.join(current_python, "DLLs")
    dlls_dest = os.path.join(python_dest, "DLLs")
    if os.path.exists(dlls_src):
        print(f"  复制 DLLs/ 目录...")
        shutil.copytree(dlls_src, dlls_dest, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.pyo', 'test', 'tests'
        ))

    # 复制Scripts目录（pip等工具，可选）
    scripts_src = os.path.join(current_python, "Scripts")
    if os.path.exists(scripts_src):
        # 不复制Scripts，客户端不需要pip
        pass

    # 复制Tcl/Tk运行时（Tkinter GUI依赖，缺少则无法启动）
    tcl_src = os.path.join(current_python, "tcl")
    tcl_dest = os.path.join(python_dest, "tcl")
    if os.path.exists(tcl_src):
        print(f"  复制 tcl/ 目录（Tkinter运行时）...")
        shutil.copytree(tcl_src, tcl_dest, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', '*.pyo', 'demos', 'msgs',
        ))

    # 验证Python环境
    test_python = os.path.join(python_dest, "python.exe")
    if os.path.exists(test_python):
        print(f"  Python环境准备完成: {python_dest}")
    else:
        print(f"  错误: Python环境不完整!")
        sys.exit(1)


def _copy_source_code(output_dir):
    """复制源码到输出目录（补丁更新可直接替换）"""
    print("\n复制源码文件...")

    # 复制 video_generator/ 目录
    src_dir = os.path.join(BASE_DIR, "video_generator")
    dst_dir = os.path.join(output_dir, "video_generator")
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)

    shutil.copytree(src_dir, dst_dir, ignore=shutil.ignore_patterns(
        '__pycache__', '*.pyc', '*.pyo', '*.bak', '*.tmp',
    ))
    print(f"  复制 video_generator/ ({len(os.listdir(dst_dir))} 个文件)")

    # 复制入口脚本
    for entry_name in ['run.py', 'run.pyw']:
        entry_src = os.path.join(BASE_DIR, entry_name)
        if os.path.exists(entry_src):
            shutil.copy2(entry_src, os.path.join(output_dir, entry_name))
            print(f"  复制 {entry_name}")


def _copy_config_files(output_dir):
    """复制配置文件"""
    print("\n复制配置文件...")

    # config.json
    config_src = os.path.join(BASE_DIR, "config.json")
    if os.path.exists(config_src):
        shutil.copy2(config_src, os.path.join(output_dir, "config.json"))
        # 生成签名
        try:
            with open(config_src, "r", encoding="utf-8") as f:
                config_content = f.read()
            _CONFIG_SIGN_KEY = "VideoGen2025ConfigSignatureKey_v1"
            sig = _hmac.new(_CONFIG_SIGN_KEY.encode("utf-8"), config_content.encode("utf-8"), hashlib.sha256).hexdigest()
            with open(os.path.join(output_dir, "config.json.sig"), "w", encoding="utf-8") as sf:
                sf.write(sig)
            print("  复制 config.json (含签名)")
        except Exception as e:
            shutil.copy2(config_src, os.path.join(output_dir, "config.json"))
            print(f"  复制 config.json (签名生成失败: {e})")
    else:
        print("  错误: config.json 缺失!")
        sys.exit(1)

    # .license_verify_pubkey.pem
    pubkey_src = os.path.join(BASE_DIR, ".license_verify_pubkey.pem")
    if os.path.exists(pubkey_src):
        shutil.copy2(pubkey_src, os.path.join(output_dir, ".license_verify_pubkey.pem"))
        print("  复制 .license_verify_pubkey.pem")
    else:
        print("  错误: .license_verify_pubkey.pem 缺失!")
        sys.exit(1)

    # version.json
    try:
        from video_generator.version import __version__, __build_number__
        version_data = {
            "version": __version__,
            "build_number": __build_number__,
            "updated_at": "",
        }
        with open(os.path.join(output_dir, "version.json"), "w", encoding="utf-8") as f:
            json.dump(version_data, f, ensure_ascii=False, indent=2)
        print(f"  生成 version.json (v{__version__})")
    except ImportError:
        print("  警告: 无法生成 version.json")


def _copy_assets(output_dir):
    """复制资源文件"""
    print("\n复制资源文件...")

    assets_src = os.path.join(BASE_DIR, "assets")
    assets_dst = os.path.join(output_dir, "assets")
    if os.path.exists(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst, ignore=shutil.ignore_patterns('__pycache__'))
        print(f"  复制 assets/ ({len(os.listdir(assets_dst))} 个文件)")
    else:
        print("  警告: assets/ 目录缺失")


def _copy_whisper_models(output_dir):
    """复制Whisper语音识别模型"""
    print("\n复制Whisper语音识别模型...")
    whisper_cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    whisper_dest = os.path.join(output_dir, "whisper_models")

    if not os.path.exists(whisper_cache):
        print("  未找到Whisper模型缓存目录，跳过")
        return

    os.makedirs(whisper_dest, exist_ok=True)

    model_files = {
        "tiny.pt": "tiny (39MB)",
        "base.pt": "base (74MB)",
        "small.pt": "small (244MB)",
        "medium.pt": "medium (769MB)",
        "large-v2.pt": "large-v2 (1.5GB)",
        "large-v3.pt": "large-v3 (1.5GB)",
        "large-v3-turbo.pt": "turbo (809MB)",
    }

    copied_count = 0
    for filename, desc in model_files.items():
        src = os.path.join(whisper_cache, filename)
        if os.path.exists(src):
            dst = os.path.join(whisper_dest, filename)
            size_mb = os.path.getsize(src) / (1024 * 1024)
            print(f"  复制 {filename} ({desc}) - {size_mb:.0f}MB")
            shutil.copy2(src, dst)
            copied_count += 1

    if copied_count > 0:
        print(f"  共复制 {copied_count} 个Whisper模型")
    else:
        print("  未复制任何Whisper模型")


def _copy_ffmpeg(output_dir):
    """复制FFmpeg"""
    print("\n复制FFmpeg...")
    ffmpeg_dest = os.path.join(output_dir, "ffmpeg")
    os.makedirs(ffmpeg_dest, exist_ok=True)

    found = False
    try:
        result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True)
        if result.returncode == 0:
            ffmpeg_exe = result.stdout.strip().split('\n')[0].strip()
            ffmpeg_exe = os.path.realpath(ffmpeg_exe)
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            for exe_name in ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"]:
                exe_path = os.path.join(ffmpeg_dir, exe_name)
                real_path = os.path.realpath(exe_path)
                if os.path.exists(real_path) and os.path.getsize(real_path) > 1000000:
                    shutil.copy2(real_path, os.path.join(ffmpeg_dest, exe_name))
                    print(f"  复制 {exe_name} ({os.path.getsize(real_path) // 1048576} MB)")
                    found = True
    except Exception:
        pass

    if not found:
        print("  未找到FFmpeg，跳过")


def _generate_start_bat(output_dir):
    """生成启动脚本 start.bat"""
    print("\n生成启动脚本...")

    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title VideoGenerator
cd /d "%~dp0"

set "APP_DIR=%~dp0"
set "PYTHON_EXE=%APP_DIR%python\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [错误] 未找到Python环境: %PYTHON_EXE%
    echo 请重新下载完整安装包，或运行 CheckEnv.bat 检查
    echo.
    pause
    exit /b 1
)

if exist "%APP_DIR%ffmpeg\ffmpeg.exe" set "FFMPEG_BINARY=%APP_DIR%ffmpeg\ffmpeg.exe"

echo 正在启动 VideoGenerator...
echo.

"%PYTHON_EXE%" "%APP_DIR%run.py"

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出
    echo 请运行 "CheckEnv.bat" 检查环境
    echo.
    pause
)
'''
    with open(os.path.join(output_dir, "start.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  生成 start.bat")


def _generate_start_vbs(output_dir):
    """生成无窗口启动脚本 start.vbs（使用 ChrW 避免编码问题）"""
    vbs_content = (
        'On Error Resume Next\n'
        'Set fso = CreateObject("Scripting.FileSystemObject")\n'
        'Set shell = CreateObject("WScript.Shell")\n'
        'appDir = fso.GetParentFolderName(WScript.ScriptFullName)\n'
        'pythonwExe = appDir & "\\python\\pythonw.exe"\n'
        'runPyw = appDir & "\\run.pyw"\n'
        'If Not fso.FileExists(pythonwExe) Then\n'
        '    MsgBox ChrW(26410)&ChrW(25214)&ChrW(21040)&ChrW(80)&ChrW(121)&ChrW(116)&ChrW(104)&ChrW(111)&ChrW(110)&ChrW(29615)&ChrW(22659) & vbCrLf & vbCrLf & ChrW(35831)&ChrW(37325)&ChrW(26032)&ChrW(19979)&ChrW(36733)&ChrW(23436)&ChrW(25972)&ChrW(23433)&ChrW(35013)&ChrW(21253)&ChrW(65292)&ChrW(25110)&ChrW(36816)&ChrW(34892)&ChrW(32)&"CheckEnv.bat"&ChrW(26816)&ChrW(26597), vbCritical, ChrW(21551)&ChrW(21160)&ChrW(22833)&ChrW(36133)\n'
        '    WScript.Quit 1\n'
        'End If\n'
        'If Not fso.FileExists(runPyw) Then\n'
        '    MsgBox ChrW(26410)&ChrW(25214)&ChrW(21040)&ChrW(32)&"run.pyw" & vbCrLf & vbCrLf & ChrW(35831)&ChrW(37325)&ChrW(26032)&ChrW(19979)&ChrW(36733)&ChrW(23436)&ChrW(25972)&ChrW(23433)&ChrW(35013)&ChrW(21253)&ChrW(65292)&ChrW(25110)&ChrW(36816)&ChrW(34892)&ChrW(32)&"CheckEnv.bat"&ChrW(26816)&ChrW(26597), vbCritical, ChrW(21551)&ChrW(21160)&ChrW(22833)&ChrW(36133)\n'
        '    WScript.Quit 1\n'
        'End If\n'
        'hasChinese = False\n'
        'For i = 1 To Len(appDir)\n'
        '    charCode = AscW(Mid(appDir, i, 1))\n'
        '    If charCode > 127 Then\n'
        '        hasChinese = True\n'
        '        Exit For\n'
        '    End If\n'
        'Next\n'
        'If hasChinese Then\n'
        '    result = MsgBox(ChrW(24403)&ChrW(21069)&ChrW(36335)&ChrW(24452)&ChrW(21253)&ChrW(21547)&ChrW(38750)&ChrW(33521)&ChrW(25991)&ChrW(23383)&ChrW(31526)&ChrW(65292)&ChrW(21487)&ChrW(33021)&ChrW(23548)&ChrW(33268)&ChrW(36816)&ChrW(34892)&ChrW(24322)&ChrW(24120) & vbCrLf & vbCrLf & ChrW(24314)&ChrW(35758)&ChrW(31227)&ChrW(21160)&ChrW(21040)&ChrW(32431)&ChrW(33521)&ChrW(25991)&ChrW(36335)&ChrW(24452)&ChrW(65292)&ChrW(22914)&ChrW(32)&"D:\\VideoGenerator\\" & vbCrLf & vbCrLf & ChrW(26159)&ChrW(21542)&ChrW(32487)&ChrW(32493)&ChrW(21551)&ChrW(21160)&ChrW(65311), vbExclamation + vbYesNo, ChrW(36335)&ChrW(24452)&ChrW(35686)&ChrW(21578))\n'
        '    If result = vbNo Then WScript.Quit 0\n'
        'End If\n'
        'shell.CurrentDirectory = appDir\n'
        'If fso.FileExists(appDir & "\\ffmpeg\\ffmpeg.exe") Then\n'
        '    shell.Environment("Process").Item("FFMPEG_BINARY") = appDir & "\\ffmpeg\\ffmpeg.exe"\n'
        'End If\n'
        'shell.Run """" & pythonwExe & """" & " " & """" & runPyw & """", 0, False\n'
    )
    with open(os.path.join(output_dir, "start.vbs"), "w", encoding="ascii") as f:
        f.write(vbs_content)
    print("  生成 start.vbs")


def _generate_checkenv_bat(output_dir):
    """生成环境检查脚本 CheckEnv.bat"""
    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title VideoGenerator - Environment Check
color 0A
setlocal enabledelayedexpansion

set "APP_DIR=%~dp0"

echo ============================================================
echo          VideoGenerator - Environment Check
echo ============================================================
echo.

set PASS=0
set FAIL=0
set WARN=0

echo [1/7] 检查安装路径...
set "HAS_NON_ASCII=0"
> "%TEMP%\vg_path_check.tmp" echo %APP_DIR%
findstr /R /C:"[^\x20-\x7E]" "%TEMP%\vg_path_check.tmp" >nul 2>&1 && set "HAS_NON_ASCII=1"
del "%TEMP%\vg_path_check.tmp" >nul 2>&1
if "!HAS_NON_ASCII!"=="1" (
    echo   [WARN] 警告: 路径含非英文字符
    set /a WARN+=1
) else (
    echo   [OK] 路径正常
    set /a PASS+=1
)
echo.

echo [2/7] 检查Python环境...
if exist "%APP_DIR%python\python.exe" (
    echo   [OK] Python环境正常
    set /a PASS+=1
) else (
    echo   [FAIL] Python环境缺失
    set /a FAIL+=1
)
echo.

echo [3/7] 检查主程序...
if exist "%APP_DIR%run.py" (
    echo   [OK] run.py 正常
    set /a PASS+=1
) else (
    echo   [FAIL] run.py 缺失
    set /a FAIL+=1
)

if exist "%APP_DIR%video_generator\app.py" (
    echo   [OK] video_generator/app.py 正常
    set /a PASS+=1
) else (
    echo   [FAIL] video_generator/app.py 缺失
    set /a FAIL+=1
)
echo.

echo [4/7] 检查FFmpeg...
if exist "%APP_DIR%ffmpeg\ffmpeg.exe" (
    echo   [OK] FFmpeg正常
    set /a PASS+=1
) else (
    echo   [WARN] FFmpeg缺失（软件会自动下载）
    set /a WARN+=1
)
echo.

echo [5/7] 检查Whisper模型...
if exist "%APP_DIR%whisper_models\medium.pt" (
    echo   [OK] Whisper模型正常
    set /a PASS+=1
) else (
    echo   [WARN] Whisper模型缺失（软件会自动下载）
    set /a WARN+=1
)
echo.

echo [6/7] 检查配置文件...
if exist "%APP_DIR%config.json" (
    echo   [OK] 配置文件正常
    set /a PASS+=1
) else (
    echo   [FAIL] 配置文件缺失
    set /a FAIL+=1
)
echo.

echo [7/7] 检查授权文件...
if exist "%APP_DIR%.license_verify_pubkey.pem" (
    echo   [OK] 授权文件正常
    set /a PASS+=1
) else (
    echo   [FAIL] 授权文件缺失
    set /a FAIL+=1
)
echo.

echo ============================================================
echo   通过: !PASS! 项  警告: !WARN! 项  失败: !FAIL! 项
echo ============================================================
echo.
if !FAIL! GTR 0 (
    echo   存在严重问题，建议重新下载完整安装包
) else if !WARN! GTR 0 (
    echo   存在警告项，软件可运行但部分功能可能受限
) else (
    echo   所有检查项均通过!
)
echo.
pause
'''
    with open(os.path.join(output_dir, "CheckEnv.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  生成 CheckEnv.bat")


def _generate_firstrun_bat(output_dir):
    """生成首次运行引导脚本"""
    bat_content = r'''@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title VideoGenerator - First Run Setup
color 0B
cd /d "%~dp0"

set "APP_DIR=%~dp0"

echo ============================================================
echo        VideoGenerator - First Run Setup
echo ============================================================
echo.
echo  Welcome to VideoGenerator
echo.

echo [1/4] 检查安装路径...
set "HAS_NON_ASCII=0"
> "%TEMP%\vg_path_check.tmp" echo %APP_DIR%
findstr /R /C:"[^\x20-\x7E]" "%TEMP%\vg_path_check.tmp" >nul 2>&1 && set "HAS_NON_ASCII=1"
del "%TEMP%\vg_path_check.tmp" >nul 2>&1
if "!HAS_NON_ASCII!"=="1" (
    echo   [WARN] 路径含非英文字符，建议迁移到纯英文路径
    echo   [WARN] 如 D:\VideoGenerator\
)
echo.

echo [2/4] 解除文件锁定...
powershell -Command "Get-ChildItem '%APP_DIR%' -Recurse | Unblock-File -ErrorAction SilentlyContinue" 2>nul
echo   文件锁定已解除
echo.

echo [3/4] 验证关键文件...
set "VERIFY_OK=1"
if exist "%APP_DIR%python\python.exe" (
    echo   [OK] Python环境
) else (
    echo   [FAIL] Python环境缺失
    set "VERIFY_OK=0"
)
if exist "%APP_DIR%run.py" (
    echo   [OK] 主程序
) else (
    echo   [FAIL] 主程序缺失
    set "VERIFY_OK=0"
)
if exist "%APP_DIR%config.json" (
    echo   [OK] 配置文件
) else (
    echo   [FAIL] 配置文件缺失
    set "VERIFY_OK=0"
)

if "!VERIFY_OK!"=="0" (
    echo.
    echo   关键文件缺失，请重新下载完整安装包
    pause
    exit /b 1
)
echo.

echo [4/4] 启动软件...
echo   3秒后自动启动...
timeout /t 3 /nobreak >nul
start "" "%APP_DIR%python\pythonw.exe" "%APP_DIR%run.pyw"
'''
    with open(os.path.join(output_dir, "FirstRunSetup.bat"), "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  生成 FirstRunSetup.bat")


def _copy_misc_files(output_dir):
    """复制其他文件"""
    print("\n复制其他文件...")

    misc_files = {
        "LICENSE": "LICENSE",
        "QuickStart.md": "QuickStart.md",
        "UserGuide.md": "UserGuide.md",
    }
    for src_name, dst_name in misc_files.items():
        src = os.path.join(BASE_DIR, src_name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(output_dir, dst_name))
            print(f"  复制 {src_name}")

    # icon.ico
    icon_src = os.path.join(BASE_DIR, "assets", "icon.ico")
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(output_dir, "icon.ico"))
        print("  复制 icon.ico")

    # CreateShortcut.bat
    shortcut_bat = os.path.join(BASE_DIR, "CreateShortcut.bat")
    if os.path.exists(shortcut_bat):
        shutil.copy2(shortcut_bat, os.path.join(output_dir, "CreateShortcut.bat"))
        print("  复制 CreateShortcut.bat")


def _clean_output(output_dir):
    """清理输出目录中不应存在的文件（递归扫描所有子目录）"""
    print("\n清理输出目录...")

    # 1. 递归删除 __pycache__ 目录
    for root, dirs, files in os.walk(output_dir, topdown=True):
        if '__pycache__' in dirs:
            cache_dir = os.path.join(root, '__pycache__')
            shutil.rmtree(cache_dir, ignore_errors=True)
            dirs.remove('__pycache__')

    # 2. 递归删除 .pyc/.pyo 文件
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith(('.pyc', '.pyo', '.bak', '.tmp')):
                os.remove(os.path.join(root, f))

    # 3. 删除不需要的顶层目录
    unwanted_dirs = [
        '.git', '.idea', '.vscode', '.venv',
        '.trae', 'keys', 'backend', 'models', 'model_aware_patch',
        'output_project', '垃圾桶', 'docs', 'logs', 'trash',
    ]
    for d in unwanted_dirs:
        dp = os.path.join(output_dir, d)
        if os.path.exists(dp):
            shutil.rmtree(dp, ignore_errors=True)
            print(f"  删除 {d}/")

    # 4. 递归删除敏感文件（在任何子目录中）
    # 这些文件绝对不能出现在客户分发包中
    sensitive_filenames = [
        '.env', '.secret_key', '.license_sign_key',
        '.key_salt', '.login_creds', '.license_verify_key',
        'license.json', '.license_credentials', '.license_cache',
        '.unlocked', '_pythonw_error.log',
        'generate_signing_keys.py',
        'current_ssh_password.txt', 'ssh_password_history.txt',
        'ssh_password_manager.py',
    ]
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f in sensitive_filenames:
                fp = os.path.join(root, f)
                os.remove(fp)
                print(f"  删除敏感文件: {os.path.relpath(fp, output_dir)}")

    # 5. 递归删除敏感.pem文件（只保留 .license_verify_pubkey.pem 和 certifi/cacert.pem）
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith('.pem') and f not in ('.license_verify_pubkey.pem', 'cacert.pem'):
                fp = os.path.join(root, f)
                os.remove(fp)
                print(f"  删除敏感PEM: {os.path.relpath(fp, output_dir)}")

    # 6. 递归删除.db文件
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f.endswith('.db'):
                os.remove(os.path.join(root, f))

    # 7. 删除不需要的顶层文件
    unwanted_files = [
        '配置信息.txt', 'create_config.py', 'generate_config.py',
        'setup_config.py', '设置配置.bat',
        '生成SSH密码.bat',
        '01build_exe.py', '02build_exe.py', 'obfuscate_build.py',
        'release_helper.py', 'installer_setup.iss',
        'requirements.txt',
        '后台管理系统启动器.py', '停止后台管理系统.bat',
        '!!!FirstRun.bat', '启动.vbs', '启动主程序.bat',
        '02验证打包结果.bat', '推送代码.bat', '快速发布.bat',
        '生成Demo素材.bat', 'check_and_install_deps.bat', '检查环境.bat',
        'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
        'sync_to_server.py', 'config.json.example',
        'VideoGenerator.spec', 'check_packing_safety.py',
        'pyarmor_config.json', 'pack_patch.py', 'PackPatch.bat',
        '02build_portable.py', 'file_checksums.txt',
        '_full_test.py', 'pack_patch.py', '.unlocked',
    ]
    for f in unwanted_files:
        fp = os.path.join(output_dir, f)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    # 8. 删除不需要的文档（只保留快速上手+使用说明）
    unwanted_docs = [
        'README.md', 'TERMS_OF_SERVICE.md', 'PRIVACY_POLICY.md',
        'USER_GUIDE.md', 'GITHUB_IMPROVEMENT_GUIDE.md',
        'CHANGELOG.md', 'CONTRIBUTING.md',
    ]
    for f in unwanted_docs:
        fp = os.path.join(output_dir, f)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    print("  清理完成")

    # 9. 删除后端专用包（客户端不需要）
    backend_packages = [
        'alipay', 'alipay_sdk_python', 'alibabacloud_core',
        'alibabacloud_ecs20140526', 'alibabacloud_endpoint_util',
        'alibabacloud_openapi_util', 'alibabacloud_tea_openapi',
        'alibabacloud_tea_util', 'alibabacloud_credentials',
        'alibabacloud_gateway_spi', 'Cython', 'pyarmor',
    ]
    site_packages = os.path.join(output_dir, "python", "Lib", "site-packages")
    if os.path.isdir(site_packages):
        for entry in os.listdir(site_packages):
            entry_lower = entry.lower()
            for pkg in backend_packages:
                if entry_lower.startswith(pkg.lower()):
                    fp = os.path.join(site_packages, entry)
                    try:
                        if os.path.isdir(fp):
                            shutil.rmtree(fp, ignore_errors=True)
                    except OSError:
                        pass
                    break
            # 删除 .dist-info 目录（安装元数据，运行时不需要）
            if entry.endswith('.dist-info'):
                fp = os.path.join(site_packages, entry)
                try:
                    if os.path.isdir(fp):
                        shutil.rmtree(fp, ignore_errors=True)
                except OSError:
                    pass

    print("  后端专用包清理完成")


def _verify_output(output_dir):
    """验证打包输出"""
    print("\n验证打包结果...")

    required = [
        ("python/python.exe", "Python环境"),
        ("python/pythonw.exe", "Python无窗口环境"),
        ("python/tcl/tcl8.6/init.tcl", "Tcl运行时"),
        ("python/tcl/tk8.6/tk.tcl", "Tk运行时"),
        ("run.py", "入口脚本"),
        ("run.pyw", "无窗口入口脚本"),
        ("video_generator/app.py", "核心程序"),
        ("video_generator/__init__.py", "包初始化"),
        ("config.json", "配置文件"),
        (".license_verify_pubkey.pem", "ECDSA公钥"),
        ("version.json", "版本信息"),
        ("start.bat", "启动脚本"),
        ("start.vbs", "无窗口启动脚本"),
    ]

    missing = []
    for rel_path, desc in required:
        abs_path = os.path.join(output_dir, rel_path.replace("/", os.sep))
        if os.path.exists(abs_path):
            print(f"  [OK] {desc}({rel_path})")
        else:
            print(f"  [FAIL] {desc}({rel_path}) 缺失!")
            missing.append(rel_path)

    if missing:
        print(f"\n  关键文件缺失，打包终止!")
        sys.exit(1)

    # 验证配置文件内容
    config_path = os.path.join(output_dir, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        api_url = config.get("api_base_url", "")
        private_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.']
        if any(p in api_url for p in private_patterns):
            print(f"  [FAIL] api_base_url 为 {api_url}，用户无法连接服务器!")
            sys.exit(1)
        print(f"  [OK] api_base_url = {api_url}")

        sensitive_keys = ['cloud_llm_api_key', 'cloud_asr_api_key', 'cloud_image_api_key']
        for key in sensitive_keys:
            if config.get(key, '') != '':
                print(f"  [FAIL] config.json 中 {key} 不为空!")
                sys.exit(1)
        print("  [OK] API Key 字段均为空（安全）")
    except json.JSONDecodeError:
        print("  [FAIL] config.json 格式错误!")
        sys.exit(1)

    # 递归检查敏感文件（任何子目录中都不能存在）
    sensitive_files = [
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.license_verify_key', '.key_salt', '.login_creds',
        '.license_credentials', '.license_cache', '.unlocked',
        '_pythonw_error.log', 'generate_signing_keys.py',
    ]
    found_sensitive = []
    for root, dirs, files in os.walk(output_dir):
        for f in files:
            if f in sensitive_files:
                fp = os.path.join(root, f)
                found_sensitive.append(os.path.relpath(fp, output_dir))
            if f.endswith('.pem') and f not in ('.license_verify_pubkey.pem', 'cacert.pem'):
                fp = os.path.join(root, f)
                found_sensitive.append(os.path.relpath(fp, output_dir))

    if found_sensitive:
        print(f"  [FAIL] 发现敏感文件:")
        for s in found_sensitive:
            print(f"       {s}")
        print("  打包终止! 请检查清理逻辑!")
        sys.exit(1)

    # 检查 __pycache__ 残留
    for root, dirs, files in os.walk(output_dir):
        if '__pycache__' in dirs:
            print(f"  [FAIL] 发现 __pycache__ 残留: {os.path.relpath(root, output_dir)}")
            sys.exit(1)

    print("  验证通过!")


def _generate_checksums(output_dir):
    """生成完整性校验文件"""
    print("\n生成完整性校验文件...")
    checksum_path = os.path.join(output_dir, "file_checksums.txt")
    skip_dirs = {
        'whisper_models', 'ffmpeg', 'logs', 'output_project',
        '垃圾桶', '__pycache__', '.git', 'python',
    }
    skip_extensions = {'.log', '.tmp', '.bak', '.pyc', '.pyo'}
    count = 0

    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("# VideoGenerator - File Integrity Checksums\n")
        f.write("# 由打包脚本自动生成，请勿修改\n")
        f.write("# 格式: SHA256  相对路径\n\n")

        for root, dirs, files in os.walk(output_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for filename in sorted(files):
                if any(filename.endswith(ext) for ext in skip_extensions):
                    continue
                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, output_dir).replace(os.sep, "/")
                if rel_path == "file_checksums.txt":
                    continue
                try:
                    sha256_hash = hashlib.sha256()
                    with open(abs_path, "rb") as fh:
                        for chunk in iter(lambda: fh.read(8192), b''):
                            sha256_hash.update(chunk)
                    sha256 = sha256_hash.hexdigest()
                    f.write(f"{sha256}  {rel_path}\n")
                    count += 1
                except (OSError, PermissionError):
                    f.write(f"ERROR  {rel_path}\n")
                    count += 1

    print(f"  已生成校验文件 ({count} 个文件)")


def _create_release_archive(output_dir):
    """创建发布压缩包"""
    print("\n创建发布压缩包...")

    zip_cmd = None
    for candidate in ["7z",
                      os.path.join(os.environ.get("ProgramFiles", ""), "7-Zip", "7z.exe"),
                      os.path.join(os.environ.get("ProgramFiles(x86)"), "7-Zip", "7z.exe")]:
        try:
            if os.path.isfile(candidate):
                zip_cmd = candidate
                break
            result = subprocess.run([candidate, "--help"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                zip_cmd = candidate
                break
        except Exception:
            continue

    if not zip_cmd:
        # 后备方案：使用Python内置zipfile
        print("  未找到7-Zip，使用Python内置压缩...")
        from datetime import datetime
        date_stamp = datetime.now().strftime("%Y%m%d")
        archive_zip = os.path.join(BASE_DIR, "dist", f"VideoGenerator_{date_stamp}.zip")

        import zipfile
        print(f"  创建ZIP压缩包（这可能需要较长时间）...")
        with zipfile.ZipFile(archive_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(output_dir))
                    try:
                        zf.write(file_path, arcname)
                    except Exception:
                        pass
        archive_size = os.path.getsize(archive_zip) / (1024 * 1024)
        print(f"  ZIP压缩完成: {archive_zip} ({archive_size:.0f}MB)")
        return

    from datetime import datetime
    date_stamp = datetime.now().strftime("%Y%m%d")
    archive_name = f"VideoGenerator_{date_stamp}"
    archive_7z = os.path.join(BASE_DIR, "dist", f"{archive_name}.7z")

    print(f"  使用7z固实压缩...")
    cmd = [zip_cmd, "a", "-t7z", "-mx=7", "-ms=on", "-m0=lzma2",
           archive_7z, os.path.basename(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="dist")
    if result.returncode == 0:
        archive_size = os.path.getsize(archive_7z) / (1024 * 1024)
        print(f"  7z固实压缩完成: {archive_7z} ({archive_size:.0f}MB)")
    else:
        print(f"  7z压缩失败: {result.stderr[:200]}")


def get_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)


def build_portable():
    """主构建函数：内嵌Python + 源码外置模式"""
    print("=" * 60)
    print("  VideoGenerator - Portable Build")
    print("  内嵌Python + 源码外置模式（支持补丁更新）")
    print("=" * 60)

    # 1. 清理
    clean_build_dirs()
    clean_temp_files()

    # 2. 安全检查
    check_packing_safety()

    # 3. 版本信息
    try:
        from video_generator.version import __version__, __build_number__
        print(f"\n当前版本: v{__version__} (build {__build_number__})")
    except ImportError:
        print("  警告: 无法读取版本信息")

    # 4. 混淆核心模块
    # 便携版（源码外置模式）默认不混淆，保留原始.py文件以便补丁更新
    # 安全性由服务端验证保证，而非客户端混淆
    obfuscated = False
    print("\n跳过代码混淆（便携版模式保留原始源码，支持补丁更新）")

    try:
        # 5. 创建输出目录
        output_dir = os.path.join(BASE_DIR, "dist", OUTPUT_NAME)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        print(f"\n输出目录: {output_dir}")

        # 6. 准备内嵌Python环境
        _prepare_embedded_python(output_dir)

        # 7. 复制源码
        _copy_source_code(output_dir)

        # 8. 复制配置文件
        _copy_config_files(output_dir)

        # 9. 复制资源文件
        _copy_assets(output_dir)

        # 10. 复制Whisper模型
        _copy_whisper_models(output_dir)

        # 11. 复制FFmpeg
        _copy_ffmpeg(output_dir)

        # 12. 复制其他文件
        _copy_misc_files(output_dir)

        # 13. 生成启动脚本
        _generate_start_bat(output_dir)
        _generate_start_vbs(output_dir)
        _generate_checkenv_bat(output_dir)
        _generate_firstrun_bat(output_dir)

        # 14. 清理
        _clean_output(output_dir)

        # 15. 验证
        _verify_output(output_dir)

        # 16. 重命名为Release
        final_dir = os.path.join(BASE_DIR, "dist", f"{OUTPUT_NAME}_Release")
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        os.rename(output_dir, final_dir)
        output_dir = final_dir

        size = get_directory_size(output_dir)
        print(f"\n{'=' * 60}")
        print(f"  打包完成!")
        print(f"  输出目录: {output_dir}/")
        print(f"  总大小: {size:.2f} MB")
        print(f"{'=' * 60}")

        print(f"\n分发说明:")
        print(f"  1. 压缩包将自动生成在 dist/ 目录下")
        print(f"  2. 用户解压后双击 start.vbs 或 start.bat 即可运行")
        print(f"  3. 补丁更新可直接替换 .py 文件，无需重新下载完整包")
        print(f"  4. 管理后台注册新版本号 + 上传补丁包即可推送更新")

        # 18. 创建压缩包
        _create_release_archive(output_dir)

    except Exception as e:
        if obfuscated:
            _restore_original_modules()
        print(f"\n打包失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 恢复原始文件
    if obfuscated:
        _restore_original_modules()


if __name__ == '__main__':
    build_portable()
