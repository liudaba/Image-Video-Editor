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
    """清理构建目录"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"🗑️  清理 {dir_name}/")
            shutil.rmtree(dir_name)


def clean_temp_files():
    """清理临时文件(打包前必须执行)"""
    print("\n🧹 清理临时文件...")
    
    # 删除备份文件
    bak_files = glob.glob('*.bak')
    for f in bak_files:
        print(f"  🗑️  删除 {f}")
        os.remove(f)
    
    # 删除临时视频文件
    temp_videos = glob.glob('*TEMP*.mp4')
    for f in temp_videos:
        print(f"  🗑️  删除 {f}")
        os.remove(f)
    
    # 删除快捷方式
    if os.path.exists('回收站.lnk'):
        print(f"  🗑️  删除 回收站.lnk")
        os.remove('回收站.lnk')
    
    print("✅ 临时文件清理完成\n")


def build_executable():
    """构建可执行文件"""
    
    # 步骤1: 清理旧的构建文件
    print("\n" + "="*60)
    print("🔧 准备打包环境")
    print("="*60)
    clean_build_dirs()
    clean_temp_files()
    
    # 步骤2: 验证必要文件存在
    print("\n📋 检查必要文件...")
    required_files = [
        'video_generator/__init__.py',
        'config.json',
        'start.bat',
        'README.md',
        'LICENSE'
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ 错误: 缺少必要文件 {file_path}")
            sys.exit(1)
        else:
            print(f"  ✅ {file_path}")
    
    print("✅ 所有必要文件就绪\n")
    
    # 步骤3: 构建PyInstaller参数
    args = [
        'run.py',
        
        '--name=短视频生成器',
        '--onedir',
        '--windowed',
        '--icon=assets/icon.ico',
        
        '--add-data=video_generator;video_generator',
        '--add-data=config.json;.',
        '--add-data=README.md;.',
        '--add-data=快速上手指南.md;.',
        '--add-data=LICENSE;.',
    ]
    
    args += [
        '--hidden-import=whisper',
        '--collect-all=whisper',
        
        '--hidden-import=moviepy',
        '--hidden-import=torch',
        '--hidden-import=numpy',
        '--hidden-import=PIL',
        '--hidden-import=requests',
        '--hidden-import=json',
        '--hidden-import=threading',
        '--hidden-import=subprocess',
        '--hidden-import=datetime',
        '--hidden-import=queue',
        '--hidden-import=logging',
        '--hidden-import=tkinter',
        '--hidden-import=cryptography',
        
        '--collect-submodules=moviepy',
        
        '--exclude-module=test',
        '--exclude-module=tests',
        '--exclude-module=unittest',
        '--exclude-module=setuptools',
        '--exclude-module=pip',
        '--exclude-module=easy_install',
        '--exclude-module=pkg_resources',
        '--exclude-module=PyQt5',
        
        '--exclude=.git',
        '--exclude=.idea',
        '--exclude=.vscode',
        '--exclude=.venv',
        '--exclude=__pycache__',
        
        '--exclude=.env',
        '--exclude=license.json',
        '--exclude=.secret_key',
        '--exclude=.license_sign_key',
        '--exclude=.license_verify_key',
        '--exclude=.key_salt',
        '--exclude=*.pem',
        '--exclude=*.db',
        
        '--exclude=backend',
        '--exclude=models',
        '--exclude=model_aware_patch',
        
        '--exclude=output_project',
        '--exclude=垃圾桶',
        '--exclude=build',
        '--exclude=dist',
        
        '--exclude=docs',
        
        '--clean',
        '--noconfirm',
        '--noupx',
    ]
    
    # 步骤4: 显示打包信息
    print("\n" + "="*60)
    print("🚀 开始打包短视频生成器...")
    print("="*60)
    
    print("\n📦 打包内容清单:")
    print("  ✅ video_generator/     - 核心程序模块")
    print("  ✅ config.json          - 配置文件")
    print("  ✅ README.md            - 用户使用手册")
    print("  ✅ 快速上手指南.md       - 快速入门指南")
    print("  ✅ LICENSE              - 开源许可证")
    print("  ✅ _internal/           - PyInstaller依赖库")
    print("  🔄 启动.vbs             - 打包后自动生成（指向exe）")
    print("  🔄 start.bat            - 打包后自动生成（指向exe）")
    if os.path.exists('.license_verify_key'):
        print("  ✅ .license_verify_key  - 授权签名验证密钥")
    else:
        print("  ⚠️  .license_verify_key  - 缺失！部署服务端后需复制此文件")
    
    print("\n🚫 排除内容清单:")
    print("  ❌ .git/ .idea/ .venv/  - 开发环境文件")
    print("  ❌ backend/             - FastAPI后端服务器(桌面版不需要)")
    print("  ❌ models/              - AI模型文件(2-5GB,用户自动下载)")
    print("  ❌ model_aware_patch/   - 模型补丁")
    print("  ❌ output_project/      - 用户输出文件")
    print("  ❌ 垃圾桶/              - 清理的临时文件")
    print("  ❌ docs/                - 开发者技术文档")
    print("  ❌ logs/                - 日志文件夹(隐私保护)")
    print("  ❌ run.py / run.pyw     - Python调试入口(exe模式由exe替代)")
    print("  ❌ *.bat (除start.bat)  - 开发工具脚本")
    print("  ❌ *.py (除run.py)      - 开发脚本")
    print("  ❌ PyQt5                - 已移除的旧依赖")
    print("  ❌ requirements.txt     - Python依赖列表(exe不需要)")
    print("  ❌ installer_setup.iss  - Inno Setup脚本")
    print("  ❌ release_helper.py    - 发布助手")
    print("  ❌ 01build_exe.py       - 打包脚本本身")
    print("  ❌ GITHUB_IMPROVEMENT_GUIDE.md - 开发者文档")
    print("  ❌ .gitignore           - Git配置")
    print("  ❌ 回收站.lnk           - 开发调试快捷方式")
    
    print("\n⏳ 预计耗时: 5-10分钟")
    print("📊 预期大小: 800MB - 1.5GB (不含AI模型)\n")
    
    # 步骤5: 执行打包
    try:
        PyInstaller.__main__.run(args)
        
        # 步骤6: 验证结果
        print("\n" + "="*60)
        print("✅ 打包完成!")
        print("="*60)
        
        output_dir = os.path.join('dist', '短视频生成器')
        if os.path.exists(output_dir):
            _post_build(output_dir)
            size = get_directory_size(output_dir)
            print(f"\n📁 输出目录: {output_dir}/")
            print(f"📊 总大小: {size:.2f} MB")
            
            # 验证不应该存在的文件
            print(f"\n🔍 验证打包结果...")
            should_not_exist = [
                '.git', '.idea', '.venv', 'backend', 'models',
                'output_project', '垃圾桶', 'docs', 'logs',
                '02build_exe.py', 'release_helper.py', 'installer_setup.iss',
                'requirements.txt', 'check_and_install_deps.bat',
                'run.py', 'run.pyw', 'generate_placeholders.py',
                'GITHUB_IMPROVEMENT_GUIDE.md', '.gitignore',
                '01打包前清理.bat', '03验证打包结果.bat', '快速发布.bat',
                '推送代码.bat', '检查环境.bat', '生成Demo素材.bat',
                '.env', 'license.json', '.secret_key', '.license_sign_key',
                '.key_salt',
            ]
            
            has_error = False
            for item in should_not_exist:
                item_path = os.path.join(output_dir, item)
                if os.path.exists(item_path):
                    print(f"  ❌ 错误: 发现了不应该存在的 {item}/")
                    has_error = True
            
            if not has_error:
                print(f"  ✅ 验证通过: 没有发现不该存在的文件")
            
            print(f"\n💡 分发说明:")
            print(f"  1. 将整个 '{output_dir}' 文件夹压缩成ZIP")
            print(f"  2. 上传到网盘或CDN")
            print(f"  3. 用户解压后双击 启动.vbs 即可运行")
            print(f"  4. 首次运行会自动下载AI模型(约2-5GB)")
            
            if size > 2000:  # 超过2GB
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


def _post_build(output_dir):
    """打包后处理：生成启动脚本、复制密钥文件"""
    print("\n📋 打包后处理...")

    vbs_content = 'Set WshShell = CreateObject("WScript.Shell")\n'
    vbs_content += 'WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)\n'
    vbs_content += 'WshShell.Run "短视频生成器.exe", 0, False\n'
    vbs_path = os.path.join(output_dir, "启动.vbs")
    with open(vbs_path, "w", encoding="utf-8") as f:
        f.write(vbs_content)
    print("  ✅ 生成 启动.vbs（启动exe，无黑框）")

    bat_content = '@echo off\n'
    bat_content += 'cd /d "%~dp0"\n'
    bat_content += 'start "" "短视频生成器.exe"\n'
    bat_path = os.path.join(output_dir, "start.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    print("  ✅ 生成 start.bat（启动exe，备选）")

    verify_key_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".license_verify_key")
    if os.path.exists(verify_key_src):
        import shutil as _shutil
        _shutil.copy2(verify_key_src, os.path.join(output_dir, ".license_verify_key"))
        print("  ✅ 复制 .license_verify_key（授权验证密钥）")
    else:
        print("  ⚠️  .license_verify_key 缺失！部署后端后需复制此文件到打包目录")

    print("  ✅ 后处理完成\n")


def get_directory_size(path):
    """计算文件夹大小(MB)"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)


if __name__ == '__main__':
    build_executable()
