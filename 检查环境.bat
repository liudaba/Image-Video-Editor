@echo off
chcp 65001
cls
echo ============================================
echo  Python 环境检查工具
echo ============================================
echo.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo [✓] 使用项目虚拟环境的 Python
    .venv\Scripts\python.exe check_python_env.py
) else (
    echo [!] 未找到虚拟环境，使用系统 Python
    python check_python_env.py
)

echo.
echo ============================================
echo 检查完成！窗口将在 10 秒后关闭...
echo ============================================
timeout /t 10 >nul
