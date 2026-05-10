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

VENV_DIR = ".venv"

REQUIRED_PACKAGES = [
    "fastapi", "uvicorn", "jinja2", "sqlalchemy",
    "jose", "bcrypt", "pydantic", "pydantic_settings",
    "multipart", "email_validator", "redis",
    "dotenv", "asyncpg", "aiosqlite", "alembic",
    "packaging", "defusedxml",
]

LOCAL_ENV_TEMPLATE = """# 本地开发环境配置（由启动器自动生成）
DATABASE_URL=sqlite+aiosqlite:///./videogen.db
REDIS_URL=redis://localhost:6379/0

JWT_SECRET_KEY=local-dev-only-change-in-production-at-least-64-characters-long-random-string
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

HMAC_SIGN_KEY=local-dev-hmac-key-change-after-init-db

TRIAL_DAYS=7
GRACE_HOURS=2

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

CORS_ORIGINS=["http://localhost","http://localhost:8001"]

RATE_LIMIT_PER_MINUTE=120
LOG_LEVEL=DEBUG
VIDEOGEN_ENV=development
"""


def find_virtual_env_python():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, VENV_DIR, "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python
    return None


def check_python_version():
    if sys.version_info < (3, 10):
        print("❌ 错误: Python版本过低，需要Python 3.10或更高版本")
        print(f"   当前版本: {sys.version}")
        return False
    print(f"✅ Python版本: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
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


def check_dependencies(python_executable=None):
    python = python_executable or sys.executable
    import_statements = ",".join(REQUIRED_PACKAGES)
    try:
        result = subprocess.run(
            [python, "-c", f"import {import_statements}; print('OK')"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and "OK" in result.stdout:
            print("✅ 依赖检查通过")
            return True

        missing = []
        for pkg in REQUIRED_PACKAGES:
            check = subprocess.run(
                [python, "-c", f"import {pkg}"],
                capture_output=True, text=True, timeout=10
            )
            if check.returncode != 0:
                missing.append(pkg)

        if missing:
            print(f"❌ 缺失依赖: {', '.join(missing)}")
        return False
    except Exception as e:
        print(f"❌ 依赖检查失败: {e}")
        return False


def install_dependencies(python_executable=None):
    python = python_executable or sys.executable
    script_dir = os.path.dirname(os.path.abspath(__file__))
    req_file = os.path.join(script_dir, "backend", "requirements.txt")

    if not os.path.exists(req_file):
        print(f"❌ 未找到 requirements.txt: {req_file}")
        return False

    print("📦 正在安装依赖...")
    try:
        subprocess.check_call(
            [python, "-m", "pip", "install", "-r", req_file, "-i",
             "https://mirrors.aliyun.com/pypi/simple/",
             "--trusted-host", "mirrors.aliyun.com"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError:
        print("❌ 依赖安装失败")
        return False


def ensure_local_env():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_file = os.path.join(script_dir, "backend", ".env")

    if os.path.exists(env_file):
        return True

    print("⚠️  未找到 backend/.env 配置文件")
    print("💡 正在创建本地开发配置...")

    try:
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(LOCAL_ENV_TEMPLATE)
        print(f"✅ 已创建本地开发配置: {env_file}")
        print("   默认管理员: admin / admin123")
        print("   使用 SQLite 数据库（本地开发模式）")
        return True
    except Exception as e:
        print(f"❌ 创建配置文件失败: {e}")
        return False


def check_port_available(host, port):
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            if result == 0:
                print(f"⚠️  端口 {port} 已被占用")
                try:
                    connections = subprocess.run(
                        ["netstat", "-aon"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line in connections.stdout.split("\n"):
                        if f":{port} " in line and "LISTENING" in line:
                            parts = line.strip().split()
                            if len(parts) >= 5:
                                pid = parts[-1]
                                print(f"   占用进程PID: {pid}")
                                try:
                                    proc_info = subprocess.run(
                                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                                        capture_output=True, text=True, timeout=5
                                    )
                                    for pline in proc_info.stdout.split("\n"):
                                        if pid in pline:
                                            proc_name = pline.split(",")[0].strip('"')
                                            print(f"   进程名称: {proc_name}")
                                except Exception:
                                    pass
                except Exception:
                    pass
                return False
            return True
    except Exception:
        return True


def start_backend_admin(host="127.0.0.1", port=8001, reload=False,
                        auto_open_browser=True, python_executable=None):
    print(f"🚀 启动后台管理系统，地址: http://{host}:{port}/admin/login")

    if auto_open_browser:
        def open_browser():
            time.sleep(3)
            url = f"http://{host}:{port}/admin/login"
            print(f"🌐 正在打开浏览器访问: {url}")
            webbrowser.open(url)

        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()

    python = python_executable or sys.executable

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
        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

        print(f"✅ 后台管理系统已在 http://{host}:{port}/admin/login 启动")
        print("💡 提示: 使用 Ctrl+C 停止服务，或运行 '停止后台管理系统.bat'")

        def _signal_handler(sig, frame):
            print("\n🛑 正在停止后台管理系统...")
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                print("✅ 后台管理系统已停止")
            sys.exit(0)

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

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
    parser = argparse.ArgumentParser(description='短视频生成器 - 后台管理系统启动器')
    parser.add_argument('--host', default='127.0.0.1', help='绑定的主机地址 (默认: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=8001, help='绑定的端口号 (默认: 8001)')
    parser.add_argument('--reload', action='store_true', help='启用热重载模式')
    parser.add_argument('--skip-browser', action='store_true', help='跳过自动打开浏览器')
    parser.add_argument('--skip-checks', action='store_true', help='跳过环境检查')

    args = parser.parse_args()

    print("=" * 60)
    print("短视频生成器 - 后台管理系统启动器")
    print("=" * 60)

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
            if check_dependencies(venv_python):
                print("✅ 虚拟环境中依赖完整")
                use_venv = True
                python_to_use = venv_python
            else:
                print("⚠️  虚拟环境中依赖不完整")
                if install_dependencies(venv_python):
                    use_venv = True
                    python_to_use = venv_python
                else:
                    print("❌ 虚拟环境依赖安装失败，尝试使用系统Python")

        if not use_venv and not check_dependencies():
            if venv_python:
                print("💡 尝试安装依赖到虚拟环境...")
                if install_dependencies(venv_python):
                    use_venv = True
                    python_to_use = venv_python
                else:
                    return 1
            else:
                print("❓ 是否尝试安装依赖？(y/N): ", end="")
                response = input().strip().lower()
                if response in ['y', 'yes']:
                    if install_dependencies():
                        pass
                    else:
                        return 1
                else:
                    print("❌ 依赖检查未通过，无法启动")
                    return 1

        if not ensure_local_env():
            return 1

        if not check_port_available(args.host, args.port):
            print(f"❌ 端口 {args.port} 已被占用，请先停止占用进程或使用其他端口")
            print(f"   提示: 可使用 --port 参数指定其他端口，例如: --port 8002")
            return 1

    print(f"🎯 启动参数: {args.host}:{args.port}")
    if args.reload:
        print("🔄 热重载模式: 已启用")
    if use_venv:
        print(f"🐍 使用虚拟环境: {python_to_use}")

    print("-" * 60)

    start_backend_admin(
        args.host, args.port, args.reload,
        not args.skip_browser,
        python_to_use if use_venv else None,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
