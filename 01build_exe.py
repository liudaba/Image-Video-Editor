"""
短视频生成器 - PyInstaller打包配置
生成独立的.exe可执行文件
"""

import PyInstaller.__main__
import os
import sys
import shutil
import glob


def clean_build_dirs():
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"🗑️  清理 {dir_name}/")
            shutil.rmtree(dir_name)


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


def build_executable():

    print("\n" + "=" * 60)
    print("🔧 准备打包环境")
    print("=" * 60)
    clean_build_dirs()
    clean_temp_files()

    print("\n📋 检查必要文件...")
    required_files = [
        'video_generator/__init__.py',
        'config.json',
        'README.md',
        'LICENSE',
        'USER_GUIDE.md',
        '快速上手指南.md',
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
        '--add-data=video_generator;video_generator',
        '--add-data=config.json;.',
        '--add-data=README.md;.',
        '--add-data=USER_GUIDE.md;.',
        '--add-data=快速上手指南.md;.',
        '--add-data=LICENSE;.',
    ]

    if os.path.exists('TERMS_OF_SERVICE.md'):
        add_data_args.append('--add-data=TERMS_OF_SERVICE.md;.')
    if os.path.exists('PRIVACY_POLICY.md'):
        add_data_args.append('--add-data=PRIVACY_POLICY.md;.')

    hidden_import_args = [
        '--hidden-import=whisper',
        '--hidden-import=moviepy',
        '--hidden-import=torch',
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
    ]

    collect_args = [
        '--collect-all=whisper',
        '--collect-submodules=moviepy',
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
        '--exclude-module=sympy',
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
    print("  ✅ USER_GUIDE.md        - 使用说明书")
    print("  ✅ 快速上手指南.md       - 快速入门指南")
    print("  ✅ LICENSE              - 商业软件许可证")
    if os.path.exists('TERMS_OF_SERVICE.md'):
        print("  ✅ TERMS_OF_SERVICE.md  - 服务条款")
    if os.path.exists('PRIVACY_POLICY.md'):
        print("  ✅ PRIVACY_POLICY.md    - 隐私政策")
    print("  ✅ _internal/           - PyInstaller依赖库")
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
    print("📊 预期大小: 800MB - 1.5GB (不含AI模型)\n")

    try:
        PyInstaller.__main__.run(args)

        print("\n" + "=" * 60)
        print("✅ 打包完成!")
        print("=" * 60)

        output_dir = os.path.join('dist', '短视频生成器')
        if os.path.exists(output_dir):
            _post_build(output_dir)
            _clean_output(output_dir)
            size = get_directory_size(output_dir)
            print(f"\n📁 输出目录: {output_dir}/")
            print(f"📊 总大小: {size:.2f} MB")

            print(f"\n🔍 验证打包结果...")
            _verify_output(output_dir)

            print(f"\n💡 分发说明:")
            print(f"  1. 将整个 '{output_dir}' 文件夹压缩成ZIP")
            print(f"  2. 上传到网盘或CDN")
            print(f"  3. 用户解压后双击 启动.vbs 即可运行")
            print(f"  4. 首次运行会自动下载AI模型(约2-5GB)")

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
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt',
        'run.py', 'run.pyw',
        '01build_exe.py', '02build_exe.py', 'obfuscate_build.py',
        'release_helper.py', 'installer_setup.iss',
        'requirements.txt',
        '后台管理系统启动器.py', '停止后台管理系统.bat',
        '02验证打包结果.bat', '推送代码.bat', '快速发布.bat',
        '检查环境.bat', '生成Demo素材.bat', 'check_and_install_deps.bat',
        'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
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

    print("  ✅ 清理完成\n")


def _verify_output(output_dir):
    should_not_exist = [
        '.git', '.idea', '.venv', 'backend', 'models',
        'output_project', '垃圾桶', 'docs', 'logs',
        'run.py', 'run.pyw',
        '01build_exe.py', '02build_exe.py', 'obfuscate_build.py',
        'release_helper.py', 'installer_setup.iss',
        'requirements.txt', 'check_and_install_deps.bat',
        '后台管理系统启动器.py', '停止后台管理系统.bat',
        '02验证打包结果.bat', '推送代码.bat', '快速发布.bat',
        '检查环境.bat', '生成Demo素材.bat',
        'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
        '.env', 'license.json', '.secret_key', '.license_sign_key',
        '.key_salt',
    ]

    has_error = False
    for item in should_not_exist:
        item_path = os.path.join(output_dir, item)
        if os.path.exists(item_path):
            print(f"  ❌ 错误: 发现了不应该存在的 {item}")
            has_error = True

    if not has_error:
        print(f"  ✅ 验证通过: 没有发现不该存在的文件")


def _post_build(output_dir):
    print("\n📋 打包后处理...")

    vbs_content = (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        'WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)\n'
        'WshShell.Run "短视频生成器.exe", 0, False\n'
    )
    vbs_path = os.path.join(output_dir, "启动.vbs")
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)
    print("  ✅ 生成 启动.vbs（启动exe，无黑框）")

    bat_content = (
        '@echo off\n'
        'cd /d "%~dp0"\n'
        'start "" "短视频生成器.exe"\n'
    )
    bat_path = os.path.join(output_dir, "start.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  ✅ 生成 start.bat（启动exe，备选）")

    verify_key_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_verify_key")
    if os.path.exists(verify_key_src):
        shutil.copy2(verify_key_src, os.path.join(output_dir, ".license_verify_key"))
        print("  ✅ 复制 .license_verify_key（授权验证密钥）")
    else:
        print("  ⚠️  .license_verify_key 缺失！部署后端后需复制此文件到打包目录")

    print("  ✅ 后处理完成\n")


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
