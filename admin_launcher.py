"""
短视频生成器 - 后台管理系统启动器
用于启动和管理后台管理系统的运行
"""
import os
import sys
import subprocess
import threading
import time
import signal
import argparse
import webbrowser
from pathlib import Path

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
    if not in_venv:
        print("⚠️  警告: 未检测到虚拟环境，建议在虚拟环境中运行")
        return False
    return True

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

def start_backend_admin(host="127.0.0.1", port=8001, reload=False, auto_open_browser=True):
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
    
    cmd = [
        sys.executable, "-m", "uvicorn", 
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if reload:
        cmd.append("--reload")
    
    original_cwd = os.getcwd()
    backend_dir = os.path.join(original_cwd, 'backend')
    os.chdir(backend_dir)
    
    try:
        process = subprocess.Popen(cmd)
        
        print(f"✅ 后台管理系统已在 http://{host}:{port}/admin/login 启动")
        print("💡 提示: 使用 Ctrl+C 停止服务，或运行 '停止后台管理系统.bat'")
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 正在停止后台管理系统...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        print("✅ 后台管理系统已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
    finally:
        os.chdir(original_cwd)

def main():
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
    
    if not args.skip_checks:
        print("🔍 检查运行环境...")
        
        if not check_python_version():
            return 1
            
        check_virtual_env()
                
        if not check_dependencies():
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
    
    print("-"*60)
    
    start_backend_admin(args.host, args.port, args.reload, not args.skip_browser)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())