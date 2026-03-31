import sys
import os

print("="*60)
print("Python 环境检查工具")
print("="*60)

print(f"\n1. 当前 Python 可执行文件:")
print(f"   {sys.executable}")

print(f"\n2. Python 版本:")
print(f"   {sys.version}")

print(f"\n3. 检查 Whisper 安装位置:")
try:
    import whisper
    whisper_file = whisper.__file__
    print(f"   Whisper 位置: {whisper_file}")
    
    # 检查版本
    try:
        import pkg_resources
        version = pkg_resources.get_distribution("openai-whisper").version
        print(f"   Whisper 版本: {version}")
    except:
        print(f"   Whisper 版本: 无法确定")
        
except ImportError:
    print("   Whisper 未安装在此环境中！")

print(f"\n4. 虚拟环境状态:")
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    print(f"   ✅ 当前在虚拟环境中")
    print(f"   虚拟环境路径: {sys.prefix}")
else:
    print(f"   ⚠️ 当前不在虚拟环境中")
    print(f"   使用的是系统 Python")

print(f"\n5. 检查项目虚拟环境:")
project_venv = r"C:\Users\Administrator\Desktop\短视频生成器\.venv"
if os.path.exists(project_venv):
    print(f"   ✅ 项目虚拟环境存在: {project_venv}")
    
    # 检查虚拟环境中的 whisper
    venv_whisper = os.path.join(project_venv, "Lib", "site-packages", "whisper")
    if os.path.exists(venv_whisper):
        print(f"   ✅ 虚拟环境中有 Whisper")
    else:
        print(f"   ❌ 虚拟环境中没有 Whisper")
else:
    print(f"   ❌ 项目虚拟环境不存在")

print("\n" + "="*60)
print("结论:")
print("="*60)

if "短视频生成器" in sys.executable:
    print("✅ 程序使用的是项目虚拟环境的 Python")
    print("   Whisper 升级应该已经生效")
else:
    print("⚠️ 程序可能使用的是系统 Python")
    print("   需要在虚拟环境中运行程序才能使用新版本的 Whisper")

input("\n按回车键退出...")
