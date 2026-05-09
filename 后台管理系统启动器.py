"""
短视频生成器 - 后台管理系统启动器
用于启动和管理后台管理系统的运行
"""
import os
import sys
import subprocess
import threading
import time
import argparse
import webbrowser

VENV_DIR = ".venv"

def find_virtual_env_python():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, VENV_DIR, "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python
    return None

def restart_with_venv():
    venv_python = find_virtual_env_python()
    if venv_python and sys.executable != venv_python:
        print(f"🚀 正在使用虚拟环境启动...")
        print(f"   虚拟环境: {venv_python}")
        try:
            args = [venv_python] + sys.argv
            subprocess.Popen(args)
            sys.exit(0)
        except Exception as e:
            print(f"⚠️  虚拟环境启动失败: {e}")
            print("   将使用当前Python环境继续")

def check_python_version():
    if sys.version_info < (3, 10):
        print("❌ 错误: Python版本过低，需要Python 3.10或更高版本")
        return False
    return True

def check_virtual_env():
    in_venv = (
        hasattr(sys, 'real_prefix') or 
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )
    if in_venv:
        print("✅ 已在虚拟环境中运行")
        return True
    
    venv_python = find_virtual_env_python()
    if venv_python:
        print("⚠️  检测到虚拟环境，但当前未激活")
        print(f"   虚拟环境路径: {venv_python}")
        return False
    
    print("⚠️  未检测到虚拟环境，建议在虚拟环境中运行")
    return False

def check_dependencies_in_venv(python_executable):
    try:
        result = subprocess.run(
            [python_executable, "-c",
             "import fastapi, uvicorn, jinja2, sqlalchemy, jose, bcrypt; print('OK')"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and "OK" in result.stdout:
            return True
        return False
    except Exception:
        return False

def check_dependencies():
    try:
        import fastapi
        import uvicorn
        import jinja2
        import sqlalchemy
        import jose
        import bcrypt
        print("✅ 依赖检查通过")
        return True
    except ImportError as e:
        print(f"❌ 依赖缺失: {e}")
        return False

def start_backend_admin(host="127.0.0.1", port=8001, reload=False, auto_open_browser=True, python_executable=None):
    print(f"🚀 启动后台管理系统，地址: http://{host}:{port}/admin/login")
    
    def open_browser():
        time.sleep(3)
        url = f"http://{host}:{port}/admin/login"
        print(f"🌐 正在打开浏览器访问: {url}")
        webbrowser.open(url)
    
    if auto_open_browser:
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
    
    python = python_executable if python_executable else sys.executable
    
    cmd = [
        python, "-m", "uvicorn", 
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if reload:
        cmd.append("--reload")
    
    original_cwd = os.getcwd()
    backend_dir = os.path.join(original_cwd, 'backend')
    
    if not os.path.isdir(backend_dir):
        print(f"❌ 错误: 未找到backend目录: {backend_dir}")
        return
    
    os.chdir(backend_dir)
    
    process = None
    try:
        process = subprocess.Popen(cmd)
        
        print(f"✅ 后台管理系统已在 http://{host}:{port}/admin/login 启动")
        print("💡 提示: 使用 Ctrl+C 停止服务，或运行 '停止后台管理系统.bat'")
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 正在停止后台管理系统...")
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            print("✅ 后台管理系统已停止")
    except FileNotFoundError:
        print(f"❌ 错误: 找不到Python解释器: {python}")
        print("   请确保Python已正确安装或虚拟环境路径正确")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
    finally:
        os.chdir(original_cwd)

def main():
    restart_with_venv()
    
    parser = argparse.ArgumentParser(description='短视频生成器 - 后台管理系统启动器')
    parser.add_argument('--host', default='127.0.0.1', help='绑定的主机地址 (默认: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8001, help='绑定的端口号 (默认: 8001)')
    parser.add_argument('--reload', action='store_true', help='启用热重载模式')
    parser.add_argument('--skip-browser', action='store_true', help='跳过自动打开浏览器')
    parser.add_argument('--skip-checks', action='store_true', help='跳过环境检查')
    
    args = parser.parse_args()
    
    print("="*60)
    print("短视频生成器 - 后台管理系统启动器")
    print("="*60)
    
    venv_python = find_virtual_env_python()
    use_venv = False
    python_to_use = sys.executable
    
    if not args.skip_checks:
        print("🔍 检查运行环境...")
        
        if not check_python_version():
            return 1
            
        in_venv = check_virtual_env()
        
        if not in_venv and venv_python:
            print("💡 检测到虚拟环境，正在验证虚拟环境中的依赖...")
            if check_dependencies_in_venv(venv_python):
                print("✅ 虚拟环境中依赖完整")
                use_venv = True
                python_to_use = venv_python
            else:
                print("⚠️  虚拟环境中依赖不完整")
        
        if not use_venv and not check_dependencies():
            if venv_python:
                print("💡 提示: 依赖可能已安装在虚拟环境中")
                print("🔄 正在尝试安装依赖到虚拟环境...")
                try:
                    subprocess.check_call([
                        venv_python, "-m", "pip", "install", 
                        "-r", "backend/requirements.txt"
                    ])
                    print("✅ 依赖安装完成")
                    use_venv = True
                    python_to_use = venv_python
                except subprocess.CalledProcessError:
                    print("❌ 依赖安装失败")
                    return 1
            else:
                print("❓ 是否尝试安装依赖？(y/N): ", end="")
                response = input().strip().lower()
                if response in ['y', 'yes']:
                    print("📦 正在安装依赖...")
                    try:
                        subprocess.check_call([
                            sys.executable, "-m", "pip", "install", 
                            "-r", "backend/requirements.txt"
                        ])
                        print("✅ 依赖安装完成")
                    except subprocess.CalledProcessError:
                        print("❌ 依赖安装失败")
                        return 1
                else:
                    print("❌ 依赖检查未通过，无法启动")
                    return 1
    
    print(f"🎯 启动参数: {args.host}:{args.port}")
    if args.reload:
        print("🔄 热重载模式: 已启用")
    if use_venv:
        print(f"🐍 使用虚拟环境: {python_to_use}")
    
    print("-"*60)
    
    start_backend_admin(args.host, args.port, args.reload, not args.skip_browser, python_to_use if use_venv else None)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
