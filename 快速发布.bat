@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   短视频生成器 - 快速发布工具
echo ========================================
echo.

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 未检测到Python,请先安装Python 3.10+
    pause
    exit /b 1
)

echo ✅ Python环境正常
echo.

REM 询问发布类型
echo 请选择发布类型:
echo 1. 快速修复(自动递增修订号)
echo 2. 新功能发布(手动指定版本)
echo 3. 完整发布流程
echo.
set /p choice="请输入选项(1/2/3): "

if "%choice%"=="1" goto quick_fix
if "%choice%"=="2" goto new_feature
if "%choice%"=="3" goto full_release

echo ❌ 无效选项
pause
exit /b 1

:quick_fix
echo.
echo ========================================
echo   快速修复模式
echo ========================================
set /p message="请输入更新说明: "
python release_helper.py --message "%message%"
goto end

:new_feature
echo.
echo ========================================
echo   新功能发布模式
echo ========================================
set /p version="请输入新版本号(例如 1.1.0): "
set /p message="请输入更新说明: "
python release_helper.py --version "%version%" --message "%message%"
goto end

:full_release
echo.
echo ========================================
echo   完整发布流程
echo ========================================
echo.
echo [1/2] 更新版本号并推送代码...
python release_helper.py
if errorlevel 1 (
    echo ❌ 版本更新失败!
    pause
    exit /b 1
)
echo.
echo [2/2] 开始打包...
python 01build_exe.py
if errorlevel 1 (
    echo ❌ 打包失败!
    pause
    exit /b 1
)
goto end

:end
echo.
echo ========================================
echo   发布完成!
echo ========================================
pause
