@echo off
chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   短视频生成器 - 增量补丁打包工具
echo ========================================
echo.

python "%~dp0pack_patch.py" %*
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)
echo.
pause
