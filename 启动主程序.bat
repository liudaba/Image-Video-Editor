@echo off
title 短视频生成器 - 主程序启动器
chcp 65001 >nul 2>&1

echo ================================================================
echo.
echo   短视频生成器 - 主程序启动器
echo.
echo ================================================================
echo.

cd /d "%~dp0"

REM 检查Python
echo [1/4] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo 错误: 未检测到Python!
    echo.
    echo 请安装 Python 3.10 或更高版本:
    echo   https://www.python.org/downloads/
    echo.
    echo 重要: 安装时请务必勾选:
    echo   [x] Add Python to PATH
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo    正常: Python %PYTHON_VER%

REM 检查或创建虚拟环境
echo.
echo [2/4] 检查虚拟环境...
if not exist "venv" if not exist ".venv" (
    echo    正在创建虚拟环境...
    python -m venv venv
    echo    完成: 虚拟环境已创建
) else (
    echo    正常: 虚拟环境已存在
)

REM 安装依赖
echo.
echo [3/4] 安装依赖...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -c "import moviepy" >nul 2>&1
if errorlevel 1 (
    echo    正在安装依赖，请稍候...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo.
        echo 错误: 依赖安装失败!
        echo.
        echo 请尝试:
        echo   1. 右键此文件，选择"以管理员身份运行"
        echo   2. 检查网络连接
        echo.
        pause
        exit /b 1
    )
    echo    完成: 依赖已安装
) else (
    echo    正常: 依赖已安装
)

REM 启动主程序
echo.
echo [4/4] 启动主程序...
echo.
echo ================================================================
echo.
echo   正在启动主程序...
echo.
echo ================================================================
echo.
echo   首次使用请:
echo   1. 注册账号
echo   2. 激活授权码
echo   3. 在设置中配置API密钥
echo.
echo   帮助文档请查看 README.md
echo.
echo ================================================================
echo.

REM 无控制台窗口模式启动
if exist "venv\Scripts\pythonw.exe" (
    start "" venv\Scripts\pythonw.exe run.pyw
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" .venv\Scripts\pythonw.exe run.pyw
)

echo    完成: 程序已启动!
echo.
echo    程序应自动打开窗口。
echo    如未打开，请检查刚出现的窗口。
echo.
timeout /t 3 >nul
