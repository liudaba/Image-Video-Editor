@echo off
chcp 65001 >nul
echo ========================================
echo   GitHub项目完善 - 一键生成工具
echo ========================================
echo.

echo [1/3] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python,请先安装Python 3.10+
    pause
    exit /b 1
)
echo ✅ Python环境正常
echo.

echo [2/3] 生成占位图片...
python generate_placeholders.py
if errorlevel 1 (
    echo ❌ 错误: 生成占位图片失败
    pause
    exit /b 1
)
echo.

echo [3/3] 检查目录结构...
if not exist "docs\screenshots" (
    echo ❌ 错误: docs\screenshots 目录不存在
    pause
    exit /b 1
)
if not exist "docs\demo" (
    echo ❌ 错误: docs\demo 目录不存在
    pause
    exit /b 1
)
echo ✅ 目录结构正常
echo.

echo ========================================
echo   ✨ 生成完成!
echo ========================================
echo.
echo 📁 生成的文件:
echo    - docs\screenshots\main_interface.png
echo    - docs\screenshots\advanced_settings.png
echo    - docs\screenshots\generation_process.png
echo.
echo 📝 下一步操作:
echo    1. 查看生成的占位图片
echo    2. 替换为真实的程序截图
echo    3. 制作演示视频放入 docs\demo\
echo    4. 查看详细指南: docs\QUICK_START.md
echo.
echo 💡 提示:
echo    - 截图规范: 1920x1080, PNG格式, ^<2MB
echo    - 视频规范: 1080p, MP4格式, 30-60秒
echo    - 详细教程: docs\README_IMAGES.md
echo.

pause
