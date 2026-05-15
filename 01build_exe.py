"""
短视频生成器 - PyInstaller打包配置
生成独立的.exe可执行文件
集成PyArmor代码混淆，一键构建发布版本
"""

import PyInstaller.__main__
import os
import sys
import shutil
import glob
import subprocess
import json


def clean_build_dirs():
    dirs_to_clean = ['build', 'dist', '__pycache__', 'dist_obfuscated', '_obf_backup',
                     'dependencies_package', 'installer_output']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"🗑️  清理 {dir_name}/")
            shutil.rmtree(dir_name)
    for zip_pattern in ['*.zip', '*.7z', '*.tar.gz']:
        for zf in glob.glob(zip_pattern):
            print(f"🗑️  删除 {zf}")
            os.remove(zf)


def clean_temp_files():
    print("\n🧹 清理临时文件...")

    patterns = ['**/*.bak', '**/*.tmp', '**/*TEMP*.mp4']
    for pattern in patterns:
        for f in glob.glob(pattern, recursive=True):
            print(f"  🗑️  删除 {f}")
            try:
                os.remove(f)
            except OSError:
                pass

    for lnk in ['回收站.lnk']:
        if os.path.exists(lnk):
            print(f"  🗑️  删除 {lnk}")
            os.remove(lnk)

    print("✅ 临时文件清理完成\n")


def check_packing_safety():
    print("\n🔒 执行打包安全检查...")
    safety_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check_packing_safety.py')
    if os.path.exists(safety_script):
        import subprocess
        result = subprocess.run([sys.executable, safety_script], capture_output=True, text=True)
        if result.returncode != 0:
            print("\n" + result.stdout)
            if result.stderr:
                print(result.stderr)
            print("\n❌ 安全检查失败! 打包终止。")
            sys.exit(1)
        else:
            print("\n" + result.stdout)
            print("✅ 安全检查通过!")
    else:
        print("⚠️  安全检查脚本不存在，跳过检查。")
        print("💡 建议: 创建 check_packing_safety.py 以增强安全性")


def _obfuscate_core_modules():
    print("\n🔒 混淆核心安全模块（PyArmor）...")

    pyarmor_cmd = None
    for candidate in ["pyarmor", os.path.join(os.path.dirname(sys.executable), "pyarmor.exe")]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                pyarmor_cmd = candidate
                print(f"  ✅ PyArmor: {result.stdout.strip().split(chr(10))[0]}")
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
            else:
                raise Exception("not found")
        except Exception:
            print("  ⚠️  PyArmor 未安装，正在安装...")
            subprocess.run([sys.executable, "-m", "pip", "install", "pyarmor"], check=True)
            pyarmor_cmd = "pyarmor"

    base_dir = os.path.dirname(os.path.abspath(__file__))
    obf_output = os.path.join(base_dir, "dist_obfuscated")
    if os.path.exists(obf_output):
        shutil.rmtree(obf_output)
    os.makedirs(obf_output, exist_ok=True)

    core_modules = [
        "video_generator/auth_core.py",
        "video_generator/auth_dialogs.py",
        "video_generator/auth_fingerprint.py",
        "video_generator/license_manager.py",
        "video_generator/crypto_utils.py",
        "video_generator/auto_updater.py",
    ]

    backup_dir = os.path.join(base_dir, "_obf_backup")
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    os.makedirs(backup_dir, exist_ok=True)

    success_count = 0
    for module_path in core_modules:
        src = os.path.join(base_dir, module_path)
        if not os.path.exists(src):
            print(f"  ⚠️  跳过不存在的模块: {module_path}")
            continue

        module_name = os.path.splitext(os.path.basename(module_path))[0]
        module_output = os.path.join(obf_output, os.path.dirname(module_path))
        os.makedirs(module_output, exist_ok=True)

        backup_path = os.path.join(backup_dir, module_path)
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(src, backup_path)

        print(f"  🔒 混淆: {module_path}")
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

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=base_dir)
        if result.returncode != 0:
            print(f"  ❌ 混淆失败: {module_path}")
            print(f"     {result.stderr[:200]}")
            continue
        success_count += 1

    if success_count == 0:
        print("  ⚠️  所有模块混淆失败，将使用原始文件继续打包")
        shutil.rmtree(backup_dir)
        return False

    for module_path in core_modules:
        obf_src = os.path.join(obf_output, module_path)
        orig_dst = os.path.join(base_dir, module_path)
        if os.path.exists(obf_src):
            shutil.copy2(obf_src, orig_dst)
            print(f"  ✅ 替换: {module_path}")

    print(f"  ✅ 混淆完成: {success_count}/{len(core_modules)} 个模块")
    print(f"  💾 原始文件备份在: _obf_backup/")
    return True


def _restore_original_modules():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backup_dir = os.path.join(base_dir, "_obf_backup")
    if not os.path.isdir(backup_dir):
        return

    print("\n🔄 恢复原始源码文件（从 _obf_backup/）...")
    core_modules = [
        "video_generator/auth_core.py",
        "video_generator/auth_dialogs.py",
        "video_generator/auth_fingerprint.py",
        "video_generator/license_manager.py",
        "video_generator/crypto_utils.py",
        "video_generator/auto_updater.py",
    ]

    for module_path in core_modules:
        backup_path = os.path.join(backup_dir, module_path)
        orig_path = os.path.join(base_dir, module_path)
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, orig_path)
            print(f"  ✅ 恢复: {module_path}")

    shutil.rmtree(backup_dir)
    obf_output = os.path.join(base_dir, "dist_obfuscated")
    if os.path.exists(obf_output):
        shutil.rmtree(obf_output)
    print("  ✅ 原始文件已恢复，临时目录已清理\n")


def build_executable():
    print("\n" + "=" * 60)
    print("🔧 准备打包环境")
    print("=" * 60)
    clean_build_dirs()
    clean_temp_files()

    check_packing_safety()

    obfuscated = _obfuscate_core_modules()

    print("\n📋 检查必要文件...")
    required_files = [
        'video_generator/__init__.py',
        'config.json',
        'README.md',
        'LICENSE',
        '用户快速开始.md',
        'assets/icon.ico',
    ]

    optional_files = {
        'TERMS_OF_SERVICE.md': '服务条款(建议包含)',
        'PRIVACY_POLICY.md': '隐私政策(建议包含)',
    }

    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ 错误: 缺少必要文件 {file_path}")
            sys.exit(1)
        else:
            print(f"  ✅ {file_path}")

    for file_path, desc in optional_files.items():
        if os.path.exists(file_path):
            print(f"  ✅ {file_path} ({desc})")
        else:
            print(f"  ⚠️  {file_path} 缺失 ({desc})")

    print("✅ 所有必要文件就绪\n")

    add_data_args = [
        '--add-data=config.json;.',
        '--add-data=LICENSE;.',
    ]

    hidden_import_args = [
        '--hidden-import=whisper',
        '--hidden-import=moviepy',
        '--hidden-import=torch',
        '--hidden-import=torchaudio',
        '--hidden-import=numpy',
        '--hidden-import=PIL',
        '--hidden-import=requests',
        '--hidden-import=tkinter',
        '--hidden-import=cryptography',
        '--hidden-import=cryptography.fernet',
        '--hidden-import=psutil',
        '--hidden-import=GPUtil',
        '--hidden-import=moviepy.video.io.ffmpeg_tools',
        '--hidden-import=moviepy.video.VideoClip',
        '--hidden-import=moviepy.video.compositing.CompositeVideoClip',
        '--hidden-import=moviepy.audio.AudioClip',
        '--hidden-import=moviepy.audio.io.AudioFileClip',
        '--hidden-import=moviepy.video.io.VideoFileClip',
        '--hidden-import=moviepy.video.VideoClip',
        '--hidden-import=moviepy.editor',
        '--hidden-import=tiktoken',
        '--hidden-import=numba',
        '--hidden-import=llvmlite',
        '--hidden-import=regex',
        '--hidden-import=pydub',
        '--hidden-import=imageio',
        '--hidden-import=imageio_ffmpeg',
        '--hidden-import=proglog',
        '--hidden-import=tqdm',
    ]

    collect_args = [
        '--collect-all=whisper',
        '--collect-submodules=moviepy',
        '--collect-submodules=torchaudio',
        '--collect-submodules=tiktoken',
        '--collect-submodules=numba',
    ]

    exclude_module_args = [
        '--exclude-module=test',
        '--exclude-module=tests',
        '--exclude-module=unittest',
        '--exclude-module=setuptools',
        '--exclude-module=pip',
        '--exclude-module=easy_install',
        '--exclude-module=pkg_resources',
        '--exclude-module=PyQt5',
        '--exclude-module=PyQt6',
        '--exclude-module=matplotlib',
        '--exclude-module=scipy',
        '--exclude-module=notebook',
        '--exclude-module=IPython',
        '--exclude-module=jupyter',
        '--exclude-module=tornado',
        '--exclude-module=fastapi',
        '--exclude-module=uvicorn',
        '--exclude-module=sqlalchemy',
        '--exclude-module=alembic',
        '--exclude-module=redis',
        '--exclude-module=asyncpg',
        '--exclude-module=aiosqlite',
    ]

    args = [
        'run.py',
        '--name=短视频生成器',
        '--onedir',
        '--windowed',
        '--icon=assets/icon.ico',
    ]

    args += add_data_args
    args += hidden_import_args
    args += collect_args
    args += exclude_module_args
    args += [
        '--clean',
        '--noconfirm',
        '--noupx',
    ]

    print("\n" + "=" * 60)
    print("🚀 开始打包短视频生成器...")
    print("=" * 60)

    print("\n📦 打包内容清单:")
    print("  ✅ video_generator/     - 核心程序模块")
    print("  ✅ config.json          - 配置文件")
    print("  ✅ README.md            - 项目介绍")
    print("  ✅ 用户快速开始.md      - 使用说明书")
    print("  ✅ LICENSE              - 商业软件许可证")
    if os.path.exists('TERMS_OF_SERVICE.md'):
        print("  ✅ TERMS_OF_SERVICE.md  - 服务条款")
    if os.path.exists('PRIVACY_POLICY.md'):
        print("  ✅ PRIVACY_POLICY.md    - 隐私政策")
    print("  ✅ _internal/           - PyInstaller依赖库")
    print("  ✅ whisper_models/      - Whisper语音识别模型(打包后复制)")
    print("  ✅ ffmpeg/              - FFmpeg音视频工具(打包后复制)")
    print("  🔄 启动.vbs             - 打包后自动生成（指向exe）")
    print("  🔄 start.bat            - 打包后自动生成（指向exe）")
    if os.path.exists('.license_verify_key'):
        print("  ✅ .license_verify_key  - 授权签名验证密钥")
    else:
        print("  ⚠️  .license_verify_key  - 缺失！部署服务端后需复制此文件")

    print("\n🚫 排除模块清单 (通过 --exclude-module):")
    for m in ['PyQt5', 'PyQt6', 'matplotlib', 'scipy', 'fastapi', 'uvicorn',
              'sqlalchemy', 'redis', 'notebook', 'IPython', 'jupyter']:
        print(f"  ❌ {m}")

    print("\n⏳ 预计耗时: 5-10分钟")
    print("📊 预期大小: 1.5GB - 3GB (含AI模型和FFmpeg)\n")

    try:
        PyInstaller.__main__.run(args)

        print("\n" + "=" * 60)
        print("✅ 打包完成!")
        print("=" * 60)

        output_dir = os.path.join('dist', '短视频生成器')
        final_dir = os.path.join('dist', 'VideoGenerator')
        if os.path.exists(output_dir):
            _post_build(output_dir)
            _clean_output(output_dir)
            if os.path.exists(final_dir):
                shutil.rmtree(final_dir)
            os.rename(output_dir, final_dir)
            output_dir = final_dir
            size = get_directory_size(output_dir)
            print(f"\n📁 输出目录: {output_dir}/")
            print(f"📊 总大小: {size:.2f} MB")

            print(f"\n🔍 验证打包结果...")
            _verify_output(output_dir)
            _verify_required_files(output_dir)
            _verify_config_content(output_dir)

            if obfuscated:
                _restore_original_modules()

            print(f"\n💡 分发说明:")
            print(f"  1. 将整个 '{output_dir}' 文件夹压缩成ZIP")
            print(f"  2. 上传到网盘或CDN")
            print(f"  3. 用户解压后双击 启动.vbs 即可运行")
            print(f"  4. Whisper模型和FFmpeg已预装，无需额外下载")
            print(f"  5. 用户需自行安装: SD WebUI + 模型, Ollama + 推理模型")

            if size > 2000:
                print(f"\n⚠️  警告: 打包体积过大({size:.0f}MB)!")
                print(f"  请检查是否错误包含了:")
                print(f"  - .venv/ (虚拟环境)")
                print(f"  - models/ (AI模型)")
                print(f"  - backend/ (后端服务器)")
        else:
            print(f"\n❌ 错误: 输出目录不存在: {output_dir}")
            sys.exit(1)

    except Exception as e:
        if obfuscated:
            _restore_original_modules()
        print(f"\n❌ 打包失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _clean_output(output_dir):
    print("\n🧹 清理打包输出中的多余文件...")

    unwanted_dirs = [
        '.git', '.idea', '.vscode', '.venv', '__pycache__',
        'backend', 'models', 'model_aware_patch',
        'output_project', '垃圾桶', 'docs', 'logs',
    ]
    for d in unwanted_dirs:
        dp = os.path.join(output_dir, d)
        if os.path.exists(dp):
            print(f"  🗑️  删除 {d}/")
            shutil.rmtree(dp, ignore_errors=True)

    unwanted_files = [
        # 安全相关 - 机密文件
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt', '.login_creds',
        '配置信息.txt', 'create_config.py', 'generate_config.py',
        'setup_config.py', '设置配置.bat',
        # SSH密码管理 - 绝对不能打包
        'current_ssh_password.txt', 'ssh_password_history.txt',
        'ssh_password_manager.py', '生成SSH密码.bat',
        # 源代码和构建脚本
        'run.py', 'run.pyw',
        '01build_exe.py', '02build_exe.py', 'obfuscate_build.py',
        'release_helper.py', 'installer_setup.iss',
        'requirements.txt',
        # 后台管理系统相关
        '后台管理系统启动器.py', '停止后台管理系统.bat',
        # 开发和部署脚本
        '02验证打包结果.bat', '推送代码.bat', '快速发布.bat',
        '检查环境.bat', '生成Demo素材.bat', 'check_and_install_deps.bat',
        # 其他
        'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
        'README.md', 'TERMS_OF_SERVICE.md', 'PRIVACY_POLICY.md',
        '用户快速开始.md', '开发人员快速参考.md',
    ]
    for f in unwanted_files:
        fp = os.path.join(output_dir, f)
        if os.path.exists(fp):
            print(f"  🗑️  删除 {f}")
            try:
                os.remove(fp)
            except OSError:
                pass

    for pem in glob.glob(os.path.join(output_dir, '*.pem')):
        print(f"  🗑️  删除 {os.path.basename(pem)}")
        os.remove(pem)
    for db in glob.glob(os.path.join(output_dir, '*.db')):
        print(f"  🗑️  删除 {os.path.basename(db)}")
        os.remove(db)

    internal_dir = os.path.join(output_dir, '_internal')
    if os.path.isdir(internal_dir):
        internal_unwanted = [
            '.env', 'license.json', '.secret_key', '.license_sign_key',
            '.key_salt', '.login_creds',
            'current_ssh_password.txt', 'ssh_password_history.txt',
            # .license_verify_key is REQUIRED, do not remove
            'README.md', 'TERMS_OF_SERVICE.md', 'PRIVACY_POLICY.md',
            '用户快速开始.md', '开发人员快速参考.md',
        ]
        for f in internal_unwanted:
            fp = os.path.join(internal_dir, f)
            if os.path.exists(fp):
                print(f"  🗑️  删除 _internal/{f}")
                try:
                    os.remove(fp)
                except OSError:
                    pass
        for pem in glob.glob(os.path.join(internal_dir, '*.pem')):
            print(f"  🗑️  删除 _internal/{os.path.basename(pem)}")
            os.remove(pem)
        for db in glob.glob(os.path.join(internal_dir, '*.db')):
            print(f"  🗑️  删除 _internal/{os.path.basename(db)}")
            os.remove(db)

    print("  ✅ 清理完成\n")


def _verify_output(output_dir):
    should_not_exist = [
        # 目录 - 绝对不能给客户的
        '.git', '.idea', '.venv', 'backend', 'models', 'keys',
        'output_project', '垃圾桶', 'docs', 'logs',
        # 源代码和构建脚本
        'run.py', 'run.pyw',
        '01build_exe.py', '02build_exe.py', 'obfuscate_build.py',
        'release_helper.py', 'installer_setup.iss',
        'requirements.txt', 'check_and_install_deps.bat',
        # 后台管理系统
        '后台管理系统启动器.py', '停止后台管理系统.bat',
        # 其他开发脚本
        '02验证打包结果.bat', '推送代码.bat', '快速发布.bat',
        '检查环境.bat', '生成Demo素材.bat',
        'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
        # ⚠️ 机密文件 - 绝对不能打包
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt', '.login_creds',
        '配置信息.txt', 'create_config.py', 'generate_config.py',
        'setup_config.py', '设置配置.bat',
        # ⚠️ SSH密码管理 - 绝对不能打包
        'current_ssh_password.txt', 'ssh_password_history.txt',
        'ssh_password_manager.py', '生成SSH密码.bat',
    ]

    has_error = False

    # 检查普通文件和目录
    for item in should_not_exist:
        item_path = os.path.join(output_dir, item)
        if os.path.exists(item_path):
            print(f"  ❌ 错误: 发现了不应该存在的 {item}")
            has_error = True

    # 检查通配符文件 (证书和密钥)
    for pattern in ['*.pem', '*.db', '*.key']:
        matches = glob.glob(os.path.join(output_dir, pattern))
        for match in matches:
            filename = os.path.basename(match)
            print(f"  ❌ 错误: 发现了不应该存在的 {filename}")
            has_error = True

    # 检查 _internal 目录中的敏感文件
    internal_dir = os.path.join(output_dir, '_internal')
    internal_sensitive = [
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt', '.login_creds',
        'current_ssh_password.txt', 'ssh_password_history.txt',
    ]
    # .license_verify_key is a REQUIRED file, not a sensitive leak
    if os.path.isdir(internal_dir):
        for item in internal_sensitive:
            item_path = os.path.join(internal_dir, item)
            if os.path.exists(item_path):
                print(f"  ❌ 错误: 发现了不应该存在的 _internal/{item}")
                has_error = True
        for pattern in ['*.pem', '*.db', '*.key']:
            matches = glob.glob(os.path.join(internal_dir, pattern))
            for match in matches:
                filename = os.path.basename(match)
                print(f"  ❌ 错误: 发现了不应该存在的 _internal/{filename}")
                has_error = True
        # 深度扫描: 递归检查所有子目录中的敏感文件
        sensitive_patterns = ['.env', 'license.json', '.secret_key', '.license_sign_key',
                              '.key_salt', '.login_creds', 'current_ssh_password.txt']
        # .license_verify_key is REQUIRED, excluded from sensitive scan
        sensitive_extensions = ['.pem', '.db', '.key']
        for root, dirs, files in os.walk(internal_dir):
            for f in files:
                fl = f.lower()
                if f in sensitive_patterns or any(f.endswith(ext) for ext in sensitive_extensions):
                    rel = os.path.relpath(os.path.join(root, f), output_dir)
                    print(f"  ❌ 错误: 发现敏感文件 {rel}")
                    has_error = True
                if fl.endswith('.py') and not fl.endswith('.pyd'):
                    rel = os.path.relpath(os.path.join(root, f), output_dir)
                    print(f"  ❌ 错误: 发现源代码文件 {rel}")
                    has_error = True

    if not has_error:
        print(f"  ✅ 安全验证通过: 没有发现不该存在的文件")
    else:
        print(f"  ❌ 安全验证失败! 发现敏感文件泄露，打包终止!")
        sys.exit(1)


def _copy_whisper_models(output_dir):
    print("\n📦 复制 Whisper 语音识别模型...")
    whisper_cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    whisper_dest = os.path.join(output_dir, "whisper_models")

    if not os.path.exists(whisper_cache):
        print("  ⚠️  未找到 Whisper 模型缓存目录，跳过")
        print(f"     路径: {whisper_cache}")
        print("     请先运行程序下载模型后再打包")
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
            print(f"  ✅ 复制 {filename} ({desc}) - {size_mb:.0f}MB")
            shutil.copy2(src, dst)
            copied_count += 1
        else:
            print(f"  ⏭️  跳过 {filename} ({desc}) - 本地不存在")

    if copied_count > 0:
        print(f"  ✅ 共复制 {copied_count} 个 Whisper 模型")
    else:
        print("  ⚠️  未复制任何 Whisper 模型！客户首次运行将需要联网下载")


def _copy_ffmpeg(output_dir):
    print("\n📦 复制 FFmpeg...")
    ffmpeg_dest = os.path.join(output_dir, "ffmpeg")
    os.makedirs(ffmpeg_dest, exist_ok=True)

    ffmpeg_paths = [
        os.path.join(os.environ.get("ProgramFiles", ""), "FFmpeg", "bin"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "FFmpeg", "bin"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages"),
    ]

    found = False
    for search_dir in ffmpeg_paths:
        if not os.path.exists(search_dir):
            continue
        for exe_name in ["ffmpeg.exe", "ffprobe.exe", "ffplay.exe"]:
            for root, dirs, files in os.walk(search_dir):
                if exe_name in files:
                    exe_path = os.path.join(root, exe_name)
                    real_path = os.path.realpath(exe_path)
                    if os.path.getsize(real_path) > 1000000:
                        shutil.copy2(real_path, os.path.join(ffmpeg_dest, exe_name))
                        print(f"  ✅ 复制 {exe_name} ({os.path.getsize(real_path) // 1048576} MB)")
                        found = True
                    break

    import subprocess
    if not found:
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
                        print(f"  ✅ 复制 {exe_name} ({os.path.getsize(real_path) // 1048576} MB)")
                        found = True
        except Exception:
            pass

    if not found:
        print("  ⚠️  未找到 FFmpeg，跳过")
        print("     请确保已安装 FFmpeg (winget install Gyan.FFmpeg)")
    else:
        print("  ✅ FFmpeg 复制完成")


def _post_build(output_dir):
    print("\n📋 打包后处理...")

    vbs_content = (
        'On Error Resume Next\n'
        'Set fso = CreateObject("Scripting.FileSystemObject")\n'
        'Set shell = CreateObject("WScript.Shell")\n'
        'appDir = fso.GetParentFolderName(WScript.ScriptFullName)\n'
        'exePath = appDir & "\\短视频生成器.exe"\n'
        'If Not fso.FileExists(exePath) Then\n'
        '    MsgBox "未找到 短视频生成器.exe" & vbCrLf & vbCrLf & "请确认文件解压完整，或运行「环境自检修复.bat」", vbCritical, "启动失败"\n'
        '    WScript.Quit 1\n'
        'End If\n'
        'internalDll = appDir & "\\_internal\\python310.dll"\n'
        'If Not fso.FileExists(internalDll) Then\n'
        '    MsgBox "运行时文件缺失，软件无法启动。" & vbCrLf & vbCrLf & "请重新下载完整安装包，或运行「环境自检修复.bat」", vbCritical, "启动失败"\n'
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
        '    result = MsgBox("当前安装路径包含中文字符，可能导致软件运行异常。" & vbCrLf & vbCrLf & "建议迁移到纯英文路径，如 D:\\VideoGenerator\\" & vbCrLf & vbCrLf & "是否仍然继续启动？", vbExclamation + vbYesNo, "路径警告")\n'
        '    If result = vbNo Then WScript.Quit 0\n'
        'End If\n'
        'shell.CurrentDirectory = appDir\n'
        'shell.Run "短视频生成器.exe", 0, False\n'
    )
    vbs_path = os.path.join(output_dir, "启动.vbs")
    with open(vbs_path, "w", encoding="gbk") as f:
        f.write(vbs_content)
    print("  ✅ 生成 启动.vbs（含路径检查+缺失提示）")

    bat_content = (
        '@echo off\n'
        'chcp 65001 >nul 2>&1\n'
        'cd /d "%~dp0"\n'
        'if not exist "短视频生成器.exe" (\n'
        '    echo [错误] 未找到 短视频生成器.exe\n'
        '    echo 请确认文件解压完整，或运行「环境自检修复.bat」\n'
        '    echo.\n'
        '    pause\n'
        '    exit /b 1\n'
        ')\n'
        'if not exist "_internal\\python310.dll" (\n'
        '    echo [错误] 运行时文件缺失\n'
        '    echo 请重新下载完整安装包，或运行「环境自检修复.bat」\n'
        '    echo.\n'
        '    pause\n'
        '    exit /b 1\n'
        ')\n'
        'start "" "短视频生成器.exe"\n'
    )
    bat_path = os.path.join(output_dir, "start.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  ✅ 生成 start.bat（含环境检查）")

    # config.json: 双位置复制（exe同级 + _internal/）
    config_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_src):
        internal_dir = os.path.join(output_dir, "_internal")
        os.makedirs(internal_dir, exist_ok=True)
        shutil.copy2(config_src, os.path.join(output_dir, "config.json"))
        shutil.copy2(config_src, os.path.join(internal_dir, "config.json"))
        print("  ✅ config.json → exe同级 + _internal/")
    else:
        print("  ❌ 错误: config.json 缺失！")
        sys.exit(1)

    # .license_verify_key: 双位置复制（exe同级 + _internal/）
    verify_key_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_verify_key")
    if os.path.exists(verify_key_src):
        internal_dir = os.path.join(output_dir, "_internal")
        os.makedirs(internal_dir, exist_ok=True)
        shutil.copy2(verify_key_src, os.path.join(output_dir, ".license_verify_key"))
        shutil.copy2(verify_key_src, os.path.join(internal_dir, ".license_verify_key"))
        print("  ✅ .license_verify_key → exe同级 + _internal/")
    else:
        print("  ❌ 错误: .license_verify_key 缺失！授权验证将无法工作")
        print("     请先运行 backend/init_db.py 生成密钥文件")
        sys.exit(1)

    _copy_whisper_models(output_dir)
    _copy_ffmpeg(output_dir)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    quick_start = os.path.join(base_dir, "用户快速开始.md")
    if os.path.exists(quick_start):
        shutil.copy2(quick_start, os.path.join(output_dir, "使用说明.md"))
        print("  ✅ 复制 使用说明.md（快速上手）")
    detailed_guide = os.path.join(base_dir, "使用指南.md")
    if os.path.exists(detailed_guide):
        shutil.copy2(detailed_guide, os.path.join(output_dir, "使用指南.md"))
        print("  ✅ 复制 使用指南.md（详细说明）")

    _generate_checksums(output_dir)

    _generate_diagnostic_bat(output_dir)
    _generate_first_run_bat(output_dir)

    print("  ✅ 后处理完成\n")


def _generate_checksums(output_dir):
    print("\n🔐 生成完整性校验文件...")
    import hashlib
    checksum_path = os.path.join(output_dir, "file_checksums.txt")
    critical_files = [
        "短视频生成器.exe",
        "_internal/python310.dll",
        "_internal/config.json",
        "_internal/.license_verify_key",
        "ffmpeg/ffmpeg.exe",
        "ffmpeg/ffprobe.exe",
    ]
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("# 短视频生成器 - 文件完整性校验\n")
        f.write("# 由打包脚本自动生成，请勿修改\n")
        f.write("# 运行「环境自检修复.bat」可验证文件完整性\n\n")
        count = 0
        for rel_path in critical_files:
            abs_path = os.path.join(output_dir, rel_path.replace("/", os.sep))
            if os.path.exists(abs_path):
                with open(abs_path, "rb") as fh:
                    sha256 = hashlib.sha256(fh.read()).hexdigest()
                f.write(f"{sha256}  {rel_path}\n")
                count += 1
    print(f"  ✅ 已生成校验文件 ({count} 个关键文件)")


def _generate_diagnostic_bat(output_dir):
    print("  🔧 生成 环境自检修复.bat ...")
    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title 短视频生成器 - 环境自检修复
color 0A
setlocal enabledelayedexpansion

set "APP_DIR=%~dp0"
set "LOG_FILE=%APP_DIR%diagnostic_log.txt"

echo ============================================================
echo          短视频生成器 - 环境自检修复工具
echo ============================================================
echo.

echo [%date% %time%] 开始环境自检... > "%LOG_FILE%"

set PASS=0
set FAIL=0
set WARN=0

echo [1/8] 检查安装路径...
echo [1/8] 检查安装路径... >> "%LOG_FILE%"
set "PATH_SAFE=1"
echo %APP_DIR%| findstr /R /C:"[^\x20-\x7E]" >nul 2>&1
if not errorlevel 1 (
    echo   [!] 警告: 路径含非英文字符，可能导致部分功能异常
    echo   [!] 警告: 路径含非英文字符 >> "%LOG_FILE%"
    echo   [!] 建议迁移到纯英文路径，如 D:\VideoGenerator\
    set "PATH_SAFE=0"
    set /a WARN+=1
) else (
    echo   [OK] 路径正常: %APP_DIR%
    echo   [OK] 路径正常 >> "%LOG_FILE%"
    set /a PASS+=1
)
echo.

echo [2/8] 检查主程序...
if exist "%APP_DIR%短视频生成器.exe" (
    for %%F in ("%APP_DIR%短视频生成器.exe") do set EXE_SIZE=%%~zF
    if !EXE_SIZE! LSS 1000000 (
        echo   [!!] 主程序文件不完整，大小异常
        echo   [!!] 主程序文件不完整 >> "%LOG_FILE%"
        set /a FAIL+=1
    ) else (
        echo   [OK] 主程序正常
        echo   [OK] 主程序正常 >> "%LOG_FILE%"
        set /a PASS+=1
    )
) else (
    echo   [!!] 未找到 短视频生成器.exe
    echo   [!!] 未找到主程序 >> "%LOG_FILE%"
    set /a FAIL+=1
)
echo.

echo [3/8] 检查运行时依赖...
if exist "%APP_DIR%_internal\python310.dll" (
    echo   [OK] Python运行时正常
    echo   [OK] Python运行时正常 >> "%LOG_FILE%"
    set /a PASS+=1
) else (
    echo   [!!] Python运行时缺失，请重新下载完整包
    echo   [!!] Python运行时缺失 >> "%LOG_FILE%"
    set /a FAIL+=1
)
echo.

echo [4/8] 检查FFmpeg...
if exist "%APP_DIR%ffmpeg\ffmpeg.exe" (
    for %%F in ("%APP_DIR%ffmpeg\ffmpeg.exe") do set FF_SIZE=%%~zF
    if !FF_SIZE! LSS 1000000 (
        echo   [!!] FFmpeg文件不完整，大小异常
        echo   [!!] FFmpeg文件不完整 >> "%LOG_FILE%"
        set /a FAIL+=1
    ) else (
        echo   [OK] FFmpeg正常
        echo   [OK] FFmpeg正常 >> "%LOG_FILE%"
        set /a PASS+=1
    )
) else (
    echo   [!] FFmpeg缺失，视频合成功能将不可用
    echo   [!] FFmpeg缺失 >> "%LOG_FILE%"
    echo   [!] 软件启动后会自动下载，或手动安装 FFmpeg
    set /a WARN+=1
)
echo.

echo [5/8] 检查Whisper语音模型...
if exist "%APP_DIR%whisper_models\medium.pt" (
    for %%F in ("%APP_DIR%whisper_models\medium.pt") do set WH_SIZE=%%~zF
    if !WH_SIZE! LSS 500000000 (
        echo   [!!] Whisper模型不完整，大小异常
        echo   [!!] Whisper模型不完整 >> "%LOG_FILE%"
        set /a FAIL+=1
    ) else (
        echo   [OK] Whisper模型正常
        echo   [OK] Whisper模型正常 >> "%LOG_FILE%"
        set /a PASS+=1
    )
) else (
    echo   [!] Whisper模型缺失，语音识别功能将不可用
    echo   [!] Whisper模型缺失 >> "%LOG_FILE%"
    echo   [!] 软件启动后会自动下载，或联系我们获取
    set /a WARN+=1
)
echo.

echo [6/8] 检查配置文件...
if exist "%APP_DIR%_internal\config.json" (
    echo   [OK] 配置文件正常
    echo   [OK] 配置文件正常 >> "%LOG_FILE%"
    set /a PASS+=1
) else (
    echo   [!!] 配置文件缺失
    echo   [!!] 配置文件缺失 >> "%LOG_FILE%"
    set /a FAIL+=1
)
echo.

echo [7/8] 检查授权验证文件...
if exist "%APP_DIR%_internal\.license_verify_key" (
    echo   [OK] 授权文件正常
    echo   [OK] 授权文件正常 >> "%LOG_FILE%"
    set /a PASS+=1
) else (
    echo   [!!] 授权文件缺失，激活功能将不可用
    echo   [!!] 授权文件缺失 >> "%LOG_FILE%"
    set /a FAIL+=1
)
echo.

echo [8/8] 检查VC++运行时...
where vcruntime140.dll >nul 2>&1
if errorlevel 1 (
    echo   [!] VC++运行时缺失，尝试安装...
    echo   [!] VC++运行时缺失 >> "%LOG_FILE%"
    if exist "%APP_DIR%_internal\vcruntime140.dll" (
        echo   [OK] 内置VC++运行时可用
        echo   [OK] 内置VC++运行时可用 >> "%LOG_FILE%"
        set /a PASS+=1
    ) else (
        echo   [!!] VC++运行时完全缺失，软件可能无法启动
        echo   [!!] VC++运行时完全缺失 >> "%LOG_FILE%"
        set /a FAIL+=1
    )
) else (
    echo   [OK] VC++运行时正常
    echo   [OK] VC++运行时正常 >> "%LOG_FILE%"
    set /a PASS+=1
)
echo.

echo ============================================================
echo          自检结果
echo ============================================================
echo   通过: %PASS% 项
echo   警告: %WARN% 项
echo   失败: %FAIL% 项
echo.
echo   诊断日志已保存到: diagnostic_log.txt
echo   如有问题，请将此文件发送给我们排查
echo ============================================================
echo.

if %FAIL% GTR 0 (
    echo   存在严重问题，建议重新下载完整安装包
    echo   或联系我们获取帮助
) else if %WARN% GTR 0 (
    echo   存在警告项，软件可运行但部分功能可能受限
    echo   软件启动后会尝试自动修复
) else (
    echo   所有检查项均通过，环境正常！
)

echo.
echo 按任意键退出...
pause >nul
'''
    bat_path = os.path.join(output_dir, "环境自检修复.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  ✅ 生成 环境自检修复.bat（8项诊断）")


def _generate_first_run_bat(output_dir):
    print("  🔧 生成 首次运行引导.bat ...")
    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title 短视频生成器 - 首次运行引导
color 0B

set "APP_DIR=%~dp0"

echo ============================================================
echo        短视频生成器 - 首次运行引导
echo ============================================================
echo.
echo  欢迎使用短视频生成器！
echo  请按以下步骤操作，确保软件正常运行。
echo.
echo ============================================================
echo  第1步: 检查安装路径
echo ============================================================
echo.
echo  当前路径: %APP_DIR%
echo.

setlocal enabledelayedexpansion
set "PATH_SAFE=1"
for /f "delims=" %%C in ('cmd /c "echo %APP_DIR%" 2^>nul ^| findstr /R /C:"[^\x20-\x7E]"') do set "PATH_SAFE=0"

if "!PATH_SAFE!"=="0" (
    echo  [!] 警告: 当前路径包含中文或特殊字符
    echo  [!] 这可能导致软件运行异常
    echo  [!] 建议将整个文件夹移动到纯英文路径，如 D:\VideoGenerator\
    echo.
    echo  是否继续？(Y/N^)
    set /p CONT=
    if /i "!CONT!"=="N" exit /b 0
) else (
    echo  [OK] 路径正常
)
echo.

echo ============================================================
echo  第2步: 解除文件锁定
echo ============================================================
echo.
echo  从网盘下载的文件可能被Windows锁定，需要解除。
echo.

powershell -Command "Get-ChildItem '%APP_DIR%' -Recurse | Unblock-File -ErrorAction SilentlyContinue" 2>nul
if errorlevel 1 (
    echo  [!] 自动解除失败，请手动操作:
    echo  右键 短视频生成器.exe -^> 属性 -^> 勾选「解除锁定」-^> 确定
) else (
    echo  [OK] 文件锁定已解除
)
echo.

echo ============================================================
echo  第3步: 添加杀毒软件信任
echo ============================================================
echo.
echo  部分杀毒软件可能误报，请将本文件夹添加为信任目录:
echo.
echo  - Windows Defender: 设置 -^> 病毒防护 -^> 排除项 -^> 添加文件夹
echo  - 其他杀软: 请在对应设置中添加排除
echo.
echo  添加完成后按任意键继续...
pause >nul
echo.

echo ============================================================
echo  第4步: 环境快速检查
echo ============================================================
echo.

if exist "%APP_DIR%短视频生成器.exe" (
    echo  [OK] 主程序: 存在
) else (
    echo  [!!] 主程序: 缺失！请确认解压完整
)

if exist "%APP_DIR%_internal\python310.dll" (
    echo  [OK] 运行时: 正常
) else (
    echo  [!!] 运行时: 缺失！请重新下载
)

if exist "%APP_DIR%ffmpeg\ffmpeg.exe" (
    echo  [OK] FFmpeg: 正常
) else (
    echo  [!] FFmpeg: 缺失（软件会自动下载）
)

if exist "%APP_DIR%whisper_models\medium.pt" (
    echo  [OK] 语音模型: 正常
) else (
    echo  [!] 语音模型: 缺失（软件会自动下载，约770MB）
)

echo.

echo ============================================================
echo  第5步: 启动软件
echo ============================================================
echo.
echo  环境检查完成！即将启动软件...
echo.
echo  首次使用需要:
echo    1. 注册账号
echo    2. 输入激活码
echo.
echo  3秒后自动启动...
echo.

timeout /t 3 /nobreak >nul
start "" "%APP_DIR%短视频生成器.exe"
'''
    bat_path = os.path.join(output_dir, "首次运行引导.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  ✅ 生成 首次运行引导.bat（5步引导）")


def _verify_required_files(output_dir):
    print("\n🔍 验证关键文件完整性...")
    required = [
        ("短视频生成器.exe", "主程序"),
        ("_internal/python310.dll", "Python运行时"),
        ("config.json", "配置文件(exe同级)"),
        ("_internal/config.json", "配置文件(_internal)"),
        (".license_verify_key", "授权密钥(exe同级)"),
        ("_internal/.license_verify_key", "授权密钥(_internal)"),
    ]
    recommended = [
        ("whisper_models", "Whisper语音模型目录"),
        ("ffmpeg/ffmpeg.exe", "FFmpeg视频工具"),
    ]
    missing = []
    for rel_path, desc in required:
        abs_path = os.path.join(output_dir, rel_path.replace("/", os.sep))
        if os.path.exists(abs_path):
            size = os.path.getsize(abs_path)
            if size < 100:
                print(f"  ❌ {desc}({rel_path}) 文件异常小({size}字节)")
                missing.append(rel_path)
            else:
                print(f"  ✅ {desc}({rel_path}) - {size//1024}KB")
        else:
            print(f"  ❌ {desc}({rel_path}) 缺失!")
            missing.append(rel_path)
    if missing:
        print(f"\n  ❌ 关键文件缺失，打包终止!")
        sys.exit(1)
    print("  ✅ 所有关键文件完整")

    print("\n🔍 检查推荐文件（缺失不中止打包，但影响用户体验）...")
    for rel_path, desc in recommended:
        abs_path = os.path.join(output_dir, rel_path.replace("/", os.sep))
        if os.path.exists(abs_path):
            if os.path.isdir(abs_path):
                pt_files = [f for f in os.listdir(abs_path) if f.endswith('.pt')]
                if pt_files:
                    print(f"  ✅ {desc}({rel_path}/) - {len(pt_files)}个模型")
                else:
                    print(f"  ⚠️  {desc}({rel_path}/) 目录存在但无模型文件")
            else:
                size = os.path.getsize(abs_path)
                print(f"  ✅ {desc}({rel_path}) - {size//1024}KB")
        else:
            print(f"  ⚠️  {desc}({rel_path}) 缺失！用户将无法使用此功能")
    print()


def _verify_config_content(output_dir):
    print("🔍 验证配置文件内容...")
    config_path = os.path.join(output_dir, "_internal", "config.json")
    if not os.path.exists(config_path):
        print("  ❌ config.json 不存在!")
        sys.exit(1)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        api_url = config.get("api_base_url", "")
        if not api_url or "localhost" in api_url or "127.0.0.1" in api_url:
            print(f"  ❌ api_base_url 为 {api_url}，用户无法连接服务器!")
            print("     请确保 config.json 中 api_base_url 指向生产服务器")
            sys.exit(1)
        print(f"  ✅ api_base_url = {api_url}")
    except json.JSONDecodeError:
        print("  ❌ config.json 格式错误!")
        sys.exit(1)


def get_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)


if __name__ == '__main__':
    build_executable()
