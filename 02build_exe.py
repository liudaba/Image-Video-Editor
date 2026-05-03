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
        'run.py',  # 入口文件
        
        # ========== 基本配置 ==========
        '--name=短视频生成器',
        '--onedir',  # 单目录模式(便于更新)
        '--windowed',  # 无控制台窗口
        '--icon=assets/icon.ico',  # 图标(如果存在)
        
        # ========== 添加必要的文件和模块 ==========
        '--add-data=video_generator;video_generator',  # 核心程序模块
        '--add-data=config.json;.',  # 配置文件
        '--add-data=start.bat;.',  # 启动脚本
        '--add-data=README.md;.',  # 用户手册(完整版)
        '--add-data=docs/USER_GUIDE.md;.',  # 快速上手指南(简化版)
        '--add-data=docs/CUSTOMER_GUIDE.md;.',  # 客户使用完整指南
        '--add-data=LICENSE;.',  # 许可证
        
        # ========== 预打包Whisper语音识别模型(开箱即用!) ==========
        # Whisper是Python库,可以被PyInstaller打包
        # 默认打包medium模型(~1.5GB),平衡速度和准确度
        '--hidden-import=whisper',
        '--collect-all=whisper',
        
        # 注意: Ollama和SD WebUI无法打包,它们是独立的可执行程序
        # 本地模式需要用户手动安装这两个软件

        # ========== 隐藏导入(避免遗漏依赖) ==========
        '--hidden-import=PyQt5',
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
        '--hidden-import=tkinter',  # Tkinter用于GUI
        '--hidden-import=ttkbootstrap',  # 如果使用ttkbootstrap
        
        # ========== 收集所有依赖 ==========
        '--collect-all=PyQt5',
        '--collect-submodules=moviepy',
        
        # ========== 排除不必要的Python模块(减小体积) ==========
        '--exclude-module=test',
        '--exclude-module=tests',
        '--exclude-module=unittest',
        '--exclude-module=setuptools',
        '--exclude-module=pip',
        '--exclude-module=easy_install',
        '--exclude-module=pkg_resources',
        
        # ========== 排除开发文件夹(重要!) ==========
        '--exclude=.git',
        '--exclude=.idea',
        '--exclude=.vscode',
        '--exclude=.venv',
        '--exclude=__pycache__',
        
        # ========== 排除大型资源文件夹 ==========
        '--exclude=backend',  # Flask服务器(桌面版不需要)
        '--exclude=models',  # AI模型(用户首次运行自动下载,2-5GB)
        '--exclude=model_aware_patch',  # 模型补丁
        
        # ========== 排除输出和临时文件夹 ==========
        '--exclude=output_project',  # 用户生成的视频项目
        '--exclude=垃圾桶',  # 清理的旧文件
        '--exclude=build',  # 构建产物
        '--exclude=dist',  # 分发目录
        
        # ========== 排除技术文档文件夹 ==========
        '--exclude=docs',  # 技术文档(已单独添加README.md)
        
        # ========== 优化选项 ==========
        '--clean',  # 清理缓存
        '--noconfirm',  # 不确认直接覆盖
        '--noupx',  # 不使用UPX压缩(避免杀毒软件误报)
    ]
    
    # 步骤4: 显示打包信息
    print("\n" + "="*60)
    print("🚀 开始打包短视频生成器...")
    print("="*60)
    
    print("\n📦 打包内容清单:")
    print("  ✅ video_generator/     - 核心程序模块")
    print("  ✅ config.json          - 配置文件")
    print("  ✅ start.bat            - 启动脚本")
    print("  ✅ README.md            - 用户使用手册")
    print("  ✅ LICENSE              - 开源许可证")
    print("  ✅ _internal/           - PyInstaller依赖库")
    
    print("\n🚫 排除内容清单:")
    print("  ❌ .git/ .idea/ .venv/  - 开发环境文件")
    print("  ❌ backend/             - Flask后端服务器(桌面版不需要)")
    print("  ❌ models/              - AI模型文件(2-5GB,用户自动下载)")
    print("  ❌ model_aware_patch/   - 模型补丁")
    print("  ❌ output_project/      - 用户输出文件")
    print("  ❌ 垃圾桶/              - 清理的临时文件")
    print("  ❌ docs/                - 技术文档")
    print("  ❌ *.bat (除start.bat)  - 开发工具脚本")
    print("  ❌ *.py (除run.py)      - 开发脚本")
    print("  ❌ *.bak, *TEMP*.mp4    - 临时文件")
    print("  ❌ requirements.txt     - Python依赖列表")
    print("  ❌ installer_setup.iss  - Inno Setup脚本")
    print("  ❌ release_helper.py    - 发布助手")
    print("  ❌ build_exe.py         - 打包脚本")
    
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
            size = get_directory_size(output_dir)
            print(f"\n📁 输出目录: {output_dir}/")
            print(f"📊 总大小: {size:.2f} MB")
            
            # 验证不应该存在的文件
            print(f"\n🔍 验证打包结果...")
            should_not_exist = [
                '.git', '.idea', '.venv', 'backend', 'models',
                'output_project', '垃圾桶', 'docs',
                'build_exe.py', 'release_helper.py', 'installer_setup.iss',
                'requirements.txt', 'check_and_install_deps.bat'
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
            print(f"  3. 用户解压后双击 start.bat 即可运行")
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
