@echo off
chcp 65001
cls
echo ============================================
echo  Python 环境检查工具
echo ============================================
echo.
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    echo [OK] 使用项目虚拟环境的 Python
    .venv\Scripts\python.exe -c "import sys; print(f'Python {sys.version}'); import moviepy; print('[OK] moviepy'); import requests; print('[OK] requests'); import PIL; print('[OK] Pillow'); import numpy; print('[OK] numpy'); import tiktoken; print('[OK] tiktoken'); import whisper; print('[OK] whisper')"
) else (
    echo [!] 未找到虚拟环境，使用系统 Python
    python -c "import sys; print(f'Python {sys.version}'); import moviepy; print('[OK] moviepy'); import requests; print('[OK] requests'); import PIL; print('[OK] Pillow'); import numpy; print('[OK] numpy'); import tiktoken; print('[OK] tiktoken'); import whisper; print('[OK] whisper')"
)

echo.
echo ============================================
echo 检查完成！窗口将在 10 秒后关闭...
echo ============================================
timeout /t 10 >nul
