@echo off
chcp 65001 >nul
echo ========================================
echo   短视频生成器 - Demo素材检查工具
echo ========================================
echo.

echo [1/2] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python,请先安装Python 3.10+
    pause
    exit /b 1
)
echo 正常: Python环境就绪
echo.

echo [2/2] 检查目录结构...
set DIR_OK=1
if not exist "docs\screenshots" (
    echo 警告: docs\screenshots 目录不存在，正在创建...
    mkdir "docs\screenshots"
    set DIR_OK=0
)
if not exist "docs\demo" (
    echo 警告: docs\demo 目录不存在，正在创建...
    mkdir "docs\demo"
    set DIR_OK=0
)

if "!DIR_OK!"=="1" (
    echo 正常: 目录结构完整
)

echo.
echo ========================================
echo   检查完成!
echo ========================================
echo.
echo 目录结构:
echo    - docs\screenshots\  (放置程序截图)
echo    - docs\demo\         (放置演示视频)
echo.
echo 截图规范: 1920x1080, PNG格式, 小于2MB
echo 视频规范: 1080p, MP4格式, 30-60秒
echo.

pause
