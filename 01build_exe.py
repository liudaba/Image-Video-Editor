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
import re


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

def _load_spec_config():
    spec_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VideoGenerator.spec')
    if not os.path.exists(spec_path):
        print("  ⚠️  VideoGenerator.spec 不存在，使用内置默认配置")
        return (
            ['whisper', 'moviepy', 'torch', 'torchaudio', 'numpy', 'PIL', 'requests',
             'tkinter', 'cryptography', 'cryptography.fernet', 'psutil', 'GPUtil',
             'moviepy.video.io.ffmpeg_tools', 'moviepy.video.VideoClip',
             'moviepy.video.compositing.CompositeVideoClip', 'moviepy.audio.AudioClip',
             'moviepy.audio.io.AudioFileClip', 'moviepy.video.io.VideoFileClip',
             'moviepy.editor', 'tiktoken', 'numba', 'llvmlite', 'regex', 'pydub',
             'imageio', 'imageio_ffmpeg', 'proglog', 'tqdm'],
            ['test', 'tests', 'unittest', 'setuptools', 'pip', 'easy_install',
             'pkg_resources', 'PyQt5', 'PyQt6', 'matplotlib', 'scipy', 'notebook',
             'IPython', 'jupyter', 'tornado', 'fastapi', 'uvicorn', 'sqlalchemy',
             'alembic', 'redis', 'asyncpg', 'aiosqlite', 'paramiko', 'bcrypt',
             'passlib', 'python_jose', 'python_multipart', 'jose', 'httpx',
             'websockets', 'starlette', 'anyio', 'httptools', 'pydantic', 'uvloop',
             'sympy', 'networkx']
        )
    import re
    with open(spec_path, 'r', encoding='utf-8') as f:
        content = f.read()
    hiddenimports = []
    excludes = []
    hi_match = re.search(r"hiddenimports\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if hi_match:
        hiddenimports = re.findall(r"'([^']+)'", hi_match.group(1))
    ex_match = re.search(r"excludes\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if ex_match:
        excludes = re.findall(r"'([^']+)'", ex_match.group(1))
    if hiddenimports:
        print(f"  ✅ 从 spec 文件加载 {len(hiddenimports)} 个 hiddenimports")
    if excludes:
        print(f"  ✅ 从 spec 文件加载 {len(excludes)} 个 excludes")
    return hiddenimports, excludes

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


def _cython_compile_modules():
    import subprocess
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cython_modules = [
        "video_generator/auth_core.py",
        "video_generator/license_manager.py",
        "video_generator/crypto_utils.py",
        "video_generator/auth_fingerprint.py",
    ]
    try:
        import Cython
        print(f"  📦 检测到 Cython {Cython.__version__}")
    except ImportError:
        print("  ⚠️  Cython 未安装，跳过 Cython 编译（将使用 PyArmor 混淆替代）")
        return False

    backup_dir = os.path.join(base_dir, "_cython_backup")
    if os.path.exists(backup_dir):
        shutil.rmtree(backup_dir)
    os.makedirs(backup_dir)

    success_count = 0
    for mod_path in cython_modules:
        src = os.path.join(base_dir, mod_path)
        if not os.path.exists(src):
            print(f"  ⚠️  {mod_path} 不存在，跳过")
            continue
        shutil.copy2(src, os.path.join(backup_dir, os.path.basename(mod_path)))
        pyx_path = src.replace(".py", ".pyx")
        try:
            shutil.copy2(src, pyx_path)
            result = subprocess.run(
                [sys.executable, "-m", "cython", "-3", pyx_path],
                capture_output=True, text=True, cwd=base_dir, timeout=60,
            )
            c_path = pyx_path.replace(".pyx", ".c")
            if result.returncode == 0 and os.path.exists(c_path):
                ext_suffix = ".cp{}{}-win_amd64.pyd".format(sys.version_info.major, sys.version_info.minor)
                build_cmd = [
                    sys.executable, "-m", "pip", "install", "cython",
                    "--quiet", "--no-deps",
                ]
                mod_path_posix = mod_path.replace(os.sep, "/")
                setup_content = (
                    "from setuptools import setup\n"
                    "from Cython.Build import cythonize\n"
                    "import sys\n"
                    f'ext_modules = cythonize("{mod_path_posix}", compiler_directives={{"language_level": "3"}})\n'
                    "setup(ext_modules=ext_modules)\n"
                )
                setup_path = os.path.join(base_dir, "_cython_setup.py")
                with open(setup_path, "w", encoding="utf-8") as f:
                    f.write(setup_content)
                build_result = subprocess.run(
                    [sys.executable, setup_path, "build_ext", "--inplace"],
                    capture_output=True, text=True, cwd=base_dir, timeout=120,
                )
                if os.path.exists(setup_path):
                    os.remove(setup_path)
                mod_dir = os.path.dirname(src)
                mod_name = os.path.basename(src).replace(".py", "")
                pyd_found = None
                for f in os.listdir(mod_dir):
                    if f.startswith(mod_name) and f.endswith(".pyd"):
                        pyd_found = os.path.join(mod_dir, f)
                        break
                if pyd_found:
                    target_pyd = os.path.join(mod_dir, f"{mod_name}.pyd")
                    if pyd_found != target_pyd:
                        if os.path.exists(target_pyd):
                            os.remove(target_pyd)
                        os.rename(pyd_found, target_pyd)
                    if os.path.exists(src):
                        os.remove(src)
                    success_count += 1
                    print(f"  ✅ Cython 编译成功: {mod_path} → {mod_name}.pyd")
                else:
                    print(f"  ⚠️  Cython 编译 {mod_path} 未生成 .pyd，回退到源码")
            else:
                print(f"  ⚠️  Cython 转换 {mod_path} 失败: {result.stderr[:100]}")
        except Exception as e:
            print(f"  ⚠️  Cython 编译 {mod_path} 异常: {e}")
        finally:
            if os.path.exists(pyx_path):
                os.remove(pyx_path)
            c_path = pyx_path.replace(".pyx", ".c")
            if os.path.exists(c_path):
                os.remove(c_path)

    if success_count > 0:
        print(f"  ✅ Cython 编译完成: {success_count}/{len(cython_modules)} 个模块")
        return True
    else:
        print("  ⚠️  Cython 编译全部失败，将使用 PyArmor 混淆替代")
        if os.path.exists(backup_dir):
            for f in os.listdir(backup_dir):
                src_backup = os.path.join(backup_dir, f)
                dst = os.path.join(base_dir, "video_generator", f)
                shutil.copy2(src_backup, dst)
            shutil.rmtree(backup_dir)
        return False


def _restore_cython_modules():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backup_dir = os.path.join(base_dir, "_cython_backup")
    if not os.path.exists(backup_dir):
        return
    cython_modules = [
        "video_generator/auth_core.py",
        "video_generator/license_manager.py",
        "video_generator/crypto_utils.py",
        "video_generator/auth_fingerprint.py",
    ]
    for mod_path in cython_modules:
        mod_name = os.path.basename(mod_path).replace(".py", "")
        mod_dir = os.path.join(base_dir, os.path.dirname(mod_path))
        pyd_path = os.path.join(mod_dir, f"{mod_name}.pyd")
        if os.path.exists(pyd_path):
            os.remove(pyd_path)
        src_backup = os.path.join(backup_dir, os.path.basename(mod_path))
        if os.path.exists(src_backup):
            shutil.copy2(src_backup, os.path.join(base_dir, mod_path))
    shutil.rmtree(backup_dir)
    print("  ✅ Cython 编译模块已恢复为源码")


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
        "video_generator/cloud_image_client.py",
        "video_generator/cloud_llm_client.py",
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
        "video_generator/cloud_image_client.py",
        "video_generator/cloud_llm_client.py",
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

    spec_hiddenimports, spec_excludes = _load_spec_config()

    try:
        from video_generator.version import __version__, __build_number__
        print(f"  📋 当前版本: v{__version__} (build {__build_number__})")
        iss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "installer_setup.iss")
        if os.path.exists(iss_path):
            with open(iss_path, "r", encoding="utf-8") as f:
                iss_content = f.read()
            iss_version_match = re.search(r'#define MyAppVersion "([^"]+)"', iss_content)
            if iss_version_match and iss_version_match.group(1) != __version__:
                iss_content = re.sub(
                    r'#define MyAppVersion "[^"]+"',
                    f'#define MyAppVersion "{__version__}"',
                    iss_content,
                )
                with open(iss_path, "w", encoding="utf-8") as f:
                    f.write(iss_content)
                print(f"  ✅ installer_setup.iss 版本号已同步为 {__version__}")
            elif iss_version_match:
                print(f"  ✅ installer_setup.iss 版本号已是最新 ({__version__})")
    except ImportError:
        print("  ⚠️  无法读取版本信息")

    cythonized = _cython_compile_modules()
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

    hidden_import_args = [f'--hidden-import={m}' for m in spec_hiddenimports]

    collect_args = [
        '--collect-all=whisper',
        '--collect-submodules=moviepy',
        '--collect-submodules=torchaudio',
        '--collect-submodules=tiktoken',
        '--collect-submodules=numba',
    ]

    exclude_module_args = [f'--exclude-module={m}' for m in spec_excludes]

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
            if cythonized:
                _restore_cython_modules()

            print(f"\n💡 分发说明:")
            print(f"  1. 压缩包将自动生成在 dist/ 目录下")
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

            _create_release_archive(output_dir)
        else:
            print(f"\n❌ 错误: 输出目录不存在: {output_dir}")
            sys.exit(1)

    except Exception as e:
        if obfuscated:
            _restore_original_modules()
        if cythonized:
            _restore_cython_modules()
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
            if filename in ('.license_verify_key', '.license_verify_pubkey.pem'):
                continue
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
                if filename in ('.license_verify_key', '.license_verify_pubkey.pem'):
                    continue
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
                if f in ('.license_verify_key', '.license_verify_pubkey.pem'):
                    continue
                if f in sensitive_patterns or any(f.endswith(ext) for ext in sensitive_extensions):
                    rel = os.path.relpath(os.path.join(root, f), output_dir)
                    print(f"  ❌ 错误: 发现敏感文件 {rel}")
                    has_error = True
                if fl.endswith('.py') and not fl.endswith('.pyd'):
                    rel = os.path.relpath(os.path.join(root, f), output_dir)
                    rel_norm = rel.replace(os.sep, '/')
                    if 'video_generator/' in rel_norm:
                        print(f"  ❌ 错误: 发现源代码文件 {rel}")
                        has_error = True
                    obf_modules = ['auth_core', 'auth_dialogs', 'auth_fingerprint',
                                   'license_manager', 'crypto_utils', 'auto_updater',
                                   'cloud_image_client', 'cloud_llm_client']
                    for mod in obf_modules:
                        if fl == f'{mod}.py' or fl == f'{mod}.pyc':
                            print(f"  ❌ 错误: 安全模块未混淆 {rel}（应为 .pyd）")
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
        'shell.Run "短视频生成器.exe", 1, False\n'
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
        print("  ✅ 复制 .license_verify_key (HMAC, 向后兼容)")

    pubkey_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_verify_pubkey.pem")
    if os.path.exists(pubkey_src):
        internal_dir = os.path.join(output_dir, "_internal")
        os.makedirs(internal_dir, exist_ok=True)
        shutil.copy2(pubkey_src, os.path.join(output_dir, ".license_verify_pubkey.pem"))
        shutil.copy2(pubkey_src, os.path.join(internal_dir, ".license_verify_pubkey.pem"))
        print("  ✅ 复制 .license_verify_pubkey.pem (ECDSA 公钥)")
    else:
        print("  ⚠️  .license_verify_pubkey.pem 缺失，ECDSA 签名验证将不可用")
        print("     请运行 python generate_signing_keys.py 生成密钥对")

    if not os.path.exists(verify_key_src) and not os.path.exists(pubkey_src):
        print("  ❌ 错误: .license_verify_key 和 .license_verify_pubkey.pem 都缺失！")
        print("     授权验证将无法工作")
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

    license_file = os.path.join(base_dir, "LICENSE")
    if os.path.exists(license_file):
        shutil.copy2(license_file, os.path.join(output_dir, "LICENSE"))
        print("  ✅ 复制 LICENSE")
    terms_file = os.path.join(base_dir, "TERMS_OF_SERVICE.md")
    if os.path.exists(terms_file):
        shutil.copy2(terms_file, os.path.join(output_dir, "服务条款.md"))
        print("  ✅ 复制 服务条款.md")
    privacy_file = os.path.join(base_dir, "PRIVACY_POLICY.md")
    if os.path.exists(privacy_file):
        shutil.copy2(privacy_file, os.path.join(output_dir, "隐私政策.md"))
        print("  ✅ 复制 隐私政策.md")

    icon_src = os.path.join(base_dir, "assets", "icon.ico")
    if os.path.exists(icon_src):
        shutil.copy2(icon_src, os.path.join(output_dir, "icon.ico"))
        print("  ✅ 复制 icon.ico（桌面快捷方式图标）")
    else:
        print("  ⚠️  assets/icon.ico 缺失，桌面快捷方式将使用默认图标")

    shortcut_bat = os.path.join(base_dir, "创建桌面快捷方式.bat")
    if os.path.exists(shortcut_bat):
        shutil.copy2(shortcut_bat, os.path.join(output_dir, "创建桌面快捷方式.bat"))
        print("  ✅ 复制 创建桌面快捷方式.bat")
    else:
        print("  ⚠️  创建桌面快捷方式.bat 缺失")

    _generate_checksums(output_dir)

    _generate_diagnostic_bat(output_dir)
    _generate_first_run_bat(output_dir)

    print("  ✅ 后处理完成\n")


def _generate_checksums(output_dir):
    print("\n🔐 生成完整性校验文件（全文件SHA256）...")
    import hashlib
    checksum_path = os.path.join(output_dir, "file_checksums.txt")
    skip_dirs = {
        'whisper_models', 'ffmpeg', 'logs', 'output_project',
        '垃圾桶', '__pycache__', '.git', '.idea', '.vscode',
    }
    skip_extensions = {'.log', '.tmp', '.bak'}
    count = 0
    total_size = 0
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write("# 短视频生成器 - 文件完整性校验\n")
        f.write("# 由打包脚本自动生成，请勿修改\n")
        f.write("# 运行「环境自检修复.bat」可验证文件完整性\n")
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
                    file_size = os.path.getsize(abs_path)
                    total_size += file_size
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
    print(f"  ✅ 已生成校验文件 ({count} 个文件, 总计 {total_size / (1024*1024):.0f}MB)")
    print(f"  💡 排除了大体积目录: whisper_models/, ffmpeg/ (这些目录由环境自检单独检查大小)")
    print(f"  💡 用户运行「环境自检修复.bat」时会自动比对SHA256")


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

echo [1/10] 检查安装路径...
echo [1/10] 检查安装路径... >> "%LOG_FILE%"
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

echo [2/10] 检查主程序...
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

echo [3/10] 检查运行时依赖...
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

echo [4/10] 检查FFmpeg...
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

echo [5/10] 检查Whisper语音模型...
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

echo [6/10] 检查配置文件...
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

echo [7/10] 检查授权验证文件...
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

echo [8/10] 检查VC++运行时...
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

echo [9/10] 文件完整性SHA256校验...
set "CHK_FILE=%APP_DIR%file_checksums.txt"
if not exist "%CHK_FILE%" (
    echo   [!] 校验文件缺失，跳过SHA256校验
    echo   [!] 校验文件缺失 >> "%LOG_FILE%"
    set /a WARN+=1
    goto :checksum_done
)

set "CHK_PASS=0"
set "CHK_FAIL=0"
set "CHK_TOTAL=0"

for /f "usebackq tokens=1,*" %%A in ("%CHK_FILE%") do (
    set "HASH=%%A"
    set "FNAME=%%B"
    call :check_one_line
)

goto :checksum_done

:check_one_line
if "!HASH:~0,1!"=="#" goto :eof
if "!HASH!"=="ERROR" goto :eof
if "!HASH!"=="" goto :eof

set /a CHK_TOTAL+=1
set "FULL_PATH=%APP_DIR%!FNAME:/=\!"

if not exist "!FULL_PATH!" (
    echo   [!!] 文件缺失: !FNAME!
    echo   [!!] 文件缺失: !FNAME! >> "%LOG_FILE%"
    set /a CHK_FAIL+=1
    goto :eof
)

certutil -hashfile "!FULL_PATH!" SHA256 >nul 2>&1
if errorlevel 1 (
    set /a CHK_PASS+=1
    goto :eof
)

set "ACTUAL_HASH="
for /f "tokens=1,* skip=1" %%H in ('certutil -hashfile "!FULL_PATH!" SHA256 2^>nul ^| findstr /v ":" ^| findstr /v "CertUtil"') do (
    set "ACTUAL_HASH=!ACTUAL_HASH!%%H"
)

if "!ACTUAL_HASH!"=="" (
    set /a CHK_PASS+=1
    goto :eof
)

set "ACTUAL_HASH_LC=!ACTUAL_HASH: =!"
set "EXPECTED_LC=!HASH: =!"

if /i "!ACTUAL_HASH_LC!"=="!EXPECTED_LC!" (
    set /a CHK_PASS+=1
) else (
    echo   [!!] 文件已损坏: !FNAME!
    echo   [!!] 文件已损坏: !FNAME! >> "%LOG_FILE%"
    set /a CHK_FAIL+=1
)
goto :eof

if !CHK_TOTAL! GTR 0 (
    if !CHK_FAIL! EQU 0 (
        echo   [OK] !CHK_TOTAL! 个文件SHA256校验全部通过
        echo   [OK] SHA256校验全部通过 >> "%LOG_FILE%"
        set /a PASS+=1
    ) else (
        echo   [!!] !CHK_FAIL!/!CHK_TOTAL! 个文件校验失败（文件已损坏或被篡改）
        echo   [!!] !CHK_FAIL!个文件校验失败 >> "%LOG_FILE%"
        set /a FAIL+=1
    )
) else (
    echo   [!] 校验文件为空，无法校验
    set /a WARN+=1
)

:checksum_done
echo.

echo [10/10] 解压验证提示...
set "NEED_REEXTRACT=0"
if !FAIL! GTR 0 (
    set "NEED_REEXTRACT=1"
)
if !CHK_FAIL! GTR 0 (
    set "NEED_REEXTRACT=1"
)

if "!NEED_REEXTRACT!"=="1" (
    echo   [!!] 检测到文件缺失或损坏，可能原因:
    echo.
    echo        1. 解压时杀毒软件删除了部分文件（请关闭杀毒后重新解压）
    echo        2. 解压不完整（请使用7-Zip或WinRAR重新解压）
    echo        3. 下载文件损坏（请重新下载）
    echo.
    echo        建议操作:
    echo        - 关闭杀毒软件（特别是Windows Defender实时保护）
    echo        - 使用7-Zip或WinRAR重新解压压缩包
    echo        - 解压完成后再次运行本工具验证
    echo   [!!] 需要重新解压 >> "%LOG_FILE%"
    set /a FAIL+=1
) else (
    echo   [OK] 所有文件完整，解压验证通过
    echo   [OK] 解压验证通过 >> "%LOG_FILE%"
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
    echo   存在严重问题，建议:
    echo   1. 关闭杀毒软件，使用7-Zip或WinRAR重新解压
    echo   2. 重新下载完整安装包
    echo   3. 联系我们获取帮助
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
    print("  ✅ 生成 环境自检修复.bat（10项诊断，含SHA256校验）")


def _generate_first_run_bat(output_dir):
    print("  🔧 生成 首次运行引导.bat ...")
    bat_content = r'''@echo off
chcp 65001 >nul 2>&1
title 短视频生成器 - 首次运行引导
color 0B
cd /d "%~dp0"

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
echo  第2步: 确认解压方式
echo ============================================================
echo.
echo  重要：请确认您使用了正确的解压工具！
echo.
echo  推荐解压工具（解压时自动校验文件完整性）：
echo    - 7-Zip（免费，推荐！下载: https://7-zip.org）
echo    - WinRAR
echo.
echo  不推荐的解压方式：
echo    - 某些国产压缩软件的"快速解压"（会跳过CRC校验）
echo    - 直接双击压缩包内文件运行（文件不完整）
echo.
echo  如果解压时出现错误提示，说明下载文件损坏，请重新下载。
echo.
echo  按任意键继续...
pause >nul
echo.

echo ============================================================
echo  第3步: 解除文件锁定
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
echo  第4步: 添加杀毒软件信任
echo ============================================================
echo.
echo  重要：杀毒软件可能在解压时删除关键文件！
echo.
echo  如果之前解压时未关闭杀毒，部分文件可能已被删除。
echo  请将本文件夹添加为信任目录后再继续：
echo.
echo  - Windows Defender: 设置 -^> 病毒防护 -^> 排除项 -^> 添加文件夹
echo  - 其他杀软: 请在对应设置中添加排除
echo.
echo  添加完成后按任意键继续...
pause >nul
echo.

echo ============================================================
echo  第5步: 检查VC++运行时
echo ============================================================
echo.

where vcruntime140.dll >nul 2>&1
if errorlevel 1 (
    echo  [!] 未检测到 VC++ 运行时
    echo  [!] 这可能导致软件无法启动
    echo.
    echo  请下载并安装 Microsoft Visual C++ Redistributable:
    echo  https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    echo  安装完成后按任意键继续...
    pause >nul
) else (
    echo  [OK] VC++ 运行时已安装
)
echo.

echo ============================================================
echo  第6步: 验证文件完整性
echo ============================================================
echo.
echo  正在快速检查关键文件...
echo.

set "VERIFY_OK=1"

if exist "%APP_DIR%短视频生成器.exe" (
    echo  [OK] 主程序: 存在
) else (
    echo  [!!] 主程序: 缺失！可能被杀毒软件删除
    set "VERIFY_OK=0"
)

if exist "%APP_DIR%_internal\python310.dll" (
    echo  [OK] 运行时: 正常
) else (
    echo  [!!] 运行时: 缺失！解压可能不完整
    set "VERIFY_OK=0"
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

if exist "%APP_DIR%file_checksums.txt" (
    echo  [OK] 校验文件: 存在（可运行环境自检修复.bat进行完整校验）
) else (
    echo  [!] 校验文件: 缺失
)

if "!VERIFY_OK!"=="0" (
    echo.
    echo  [!!] 检测到关键文件缺失！
    echo.
    echo  最可能的原因:
    echo    1. 杀毒软件在解压时删除了文件
    echo    2. 解压不完整
    echo.
    echo  建议操作:
    echo    1. 关闭杀毒软件的实时保护
    echo    2. 使用7-Zip或WinRAR重新解压
    echo    3. 解压完成后再次运行本引导
    echo.
    echo  按任意键退出...
    pause >nul
    exit /b 1
)

echo.
echo  如需完整文件校验，请运行「环境自检修复.bat」
echo.

echo ============================================================
echo  第7步: 启动软件
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
    print("  ✅ 生成 首次运行引导.bat（7步引导，含解压验证）")


def _verify_required_files(output_dir):
    print("\n🔍 验证关键文件完整性...")
    required = [
        ("短视频生成器.exe", "主程序"),
        ("_internal/python310.dll", "Python运行时"),
        ("config.json", "配置文件(exe同级)"),
        ("_internal/config.json", "配置文件(_internal)"),
        (".license_verify_pubkey.pem", "ECDSA公钥(exe同级)"),
        ("_internal/.license_verify_pubkey.pem", "ECDSA公钥(_internal)"),
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

    # HMAC 密钥为向后兼容保留，缺失仅警告
    hmac_key = os.path.join(output_dir, ".license_verify_key")
    hmac_key_internal = os.path.join(output_dir, "_internal", ".license_verify_key")
    if not os.path.exists(hmac_key) and not os.path.exists(hmac_key_internal):
        print("  ⚠️  .license_verify_key 缺失 (HMAC 验证不可用)")

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
        private_patterns = ['localhost', '127.0.0.1', '0.0.0.0', '192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.2', '172.3']
        if not api_url or any(p in api_url for p in private_patterns):
            print(f"  ❌ api_base_url 为 {api_url}，用户无法连接服务器!")
            print("     请确保 config.json 中 api_base_url 指向生产服务器")
            sys.exit(1)
        if api_url.startswith('http://'):
            print(f"  ⚠️  api_base_url 使用 HTTP，建议升级为 HTTPS")
        print(f"  ✅ api_base_url = {api_url}")
    except json.JSONDecodeError:
        print("  ❌ config.json 格式错误!")
        sys.exit(1)


def _create_release_archive(output_dir):
    print("\n📦 创建发布压缩包...")

    zip_cmd = None
    for candidate in ["7z", os.path.join(os.environ.get("ProgramFiles", ""), "7-Zip", "7z.exe"),
                      os.path.join(os.environ.get("ProgramFiles(x86)", ""), "7-Zip", "7z.exe")]:
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
        print("  ⚠️  未找到 7-Zip，跳过自动压缩")
        print("     请安装 7-Zip: https://7-zip.org/download.html")
        print("     或手动将以下目录压缩成ZIP:")
        print(f"     {output_dir}")
        print()
        print("  💡 建议使用7z固实压缩以获得更小体积和更好的完整性保护:")
        print(f"     7z a -t7z -mx=7 -ms=on VideoGenerator.7z {output_dir}")
        return

    from datetime import datetime
    date_stamp = datetime.now().strftime("%Y%m%d")
    archive_name = f"VideoGenerator_{date_stamp}"

    archive_7z = os.path.join("dist", f"{archive_name}.7z")

    print(f"  📦 使用7z固实压缩（Solid Archive）...")
    print(f"     输出: {archive_7z}")

    cmd = [zip_cmd, "a", "-t7z", "-mx=7", "-ms=on", "-m0=lzma2",
           archive_7z, os.path.basename(output_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd="dist")
    if result.returncode == 0:
        archive_size = os.path.getsize(archive_7z) / (1024 * 1024)
        print(f"  ✅ 7z固实压缩完成: {archive_7z} ({archive_size:.0f}MB)")
        print(f"  💡 固实压缩优势:")
        print(f"     - 体积更小（小文件联合压缩）")
        print(f"     - 任何文件损坏都会导致解压失败（不会悄悄损坏）")
        print(f"     - 7-Zip解压时自动校验CRC")
    else:
        print(f"  ❌ 7z压缩失败: {result.stderr[:200]}")
        print(f"     请手动压缩 {output_dir}")

    print()
    print(f"  📋 分发说明:")
    print(f"  1. 将 {archive_7z} 上传到网盘或CDN")
    print(f"  2. 提醒用户使用 7-Zip 或 WinRAR 解压（不要用其他压缩软件的快速解压）")
    print(f"  3. 解压后双击「首次运行引导.bat」或「启动.vbs」")
    print(f"  4. 建议用户解压后运行「环境自检修复.bat」验证文件完整性")


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
