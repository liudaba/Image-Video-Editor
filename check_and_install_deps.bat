@echo off
chcp 65001 >nul
echo ========================================
echo   短视频生成器 - 环境检测与安装
echo ========================================
echo.

REM 检查Python是否安装
echo [1/3] 检查Python环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python未安装,正在下载安装...
    
    REM 下载Python安装器
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe' -OutFile '%TEMP%\python-installer.exe'}"
    
    if exist "%TEMP%\python-installer.exe" (
        echo ✅ Python安装包下载完成
        echo ⏳ 正在安装Python,请稍候...
        
        REM 静默安装Python
        start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1
        
        echo ✅ Python安装完成
    ) else (
        echo ❌ Python下载失败,请手动安装Python 3.10+
        echo 下载地址: https://www.python.org/downloads/
        pause
        exit /b 1
    )
) else (
    echo ✅ Python已安装
    python --version
)
echo.

REM 检查pip
echo [2/3] 检查pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip未安装,请重新安装Python
    pause
    exit /b 1
) else (
    echo ✅ pip已安装
)
echo.

REM 安装依赖包
echo [3/3] 安装程序依赖...
echo ⏳ 这可能需要几分钟时间,请耐心等待...
echo.

cd /d "%~dp0"

REM 使用国内镜像加速下载
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if errorlevel 1 (
    echo.
    echo ⚠️ 部分依赖安装失败,尝试逐个安装...
    
    echo 安装 moviepy...
    pip install moviepy>=2.0.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
    
    echo 安装 requests...
    pip install requests>=2.31.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
    
    echo 安装 Pillow...
    pip install Pillow>=10.0.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
    
    echo 安装 numpy...
    pip install numpy>=1.24.0 -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo.
echo ========================================
echo   ✅ 环境配置完成!
echo ========================================
echo.
echo 🎉 短视频生成器已成功安装!
echo.
echo 📝 下一步:
echo    1. 双击桌面上的"短视频生成器"图标启动程序
echo    2. 首次运行需要注册账号(享15天免费试用)
echo    3. 确保Stable Diffusion WebUI正在运行
echo.
echo 💡 提示:
echo    - 如遇到问题,请查看 快速上手指南.md
echo    - 加入QQ群获取技术支持
echo.

pause
