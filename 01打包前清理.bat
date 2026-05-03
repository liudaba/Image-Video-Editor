@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   短视频生成器 - 打包前清理工具
echo ========================================
echo.

echo 🧹 正在清理所有不必要的文件...
echo.

REM ========== 删除Python缓存 ==========
if exist __pycache__ (
    echo ✅ 删除 __pycache__/
    rmdir /s /q __pycache__
)

REM ========== 删除构建目录 ==========
if exist build (
    echo ✅ 删除 build/
    rmdir /s /q build
)

if exist dist (
    echo ✅ 删除 dist/
    rmdir /s /q dist
)

REM ========== 删除输出项目文件夹 ==========
if exist output_project (
    echo ✅ 删除 output_project/
    rmdir /s /q output_project
)

REM ========== 删除垃圾桶文件夹 ==========
if exist "垃圾桶" (
    echo ✅ 删除 垃圾桶/
    rmdir /s /q "垃圾桶"
)

REM ========== 删除备份文件 ==========
for %%f in (*.bak) do (
    if exist "%%f" (
        echo ✅ 删除 %%f
        del /q "%%f"
    )
)

REM ========== 删除临时视频文件 ==========
for %%f in (*TEMP*.mp4) do (
    if exist "%%f" (
        echo ✅ 删除 %%f
        del /q "%%f"
    )
)

REM ========== 删除快捷方式 ==========
if exist "回收站.lnk" (
    echo ✅ 删除 回收站.lnk
    del /q "回收站.lnk"
)

REM ========== 删除其他临时文件 ==========
if exist "*.tmp" (
    echo ✅ 删除 *.tmp 文件
    del /q *.tmp
)

if exist "*.log" (
    echo ✅ 删除 *.log 文件
    del /q *.log
)

echo.
echo ========================================
echo   ⚠️  以下文件需要手动确认是否删除
echo ========================================
echo.

REM IDE配置(可选删除)
if exist .idea (
    echo ⚠️  发现 .idea/ (PyCharm配置)
    set /p confirm_idea="是否删除? (y/n, 默认n): "
    if "%confirm_idea%"=="y" (
        echo ✅ 删除 .idea/
        rmdir /s /q .idea
    )
)

REM 虚拟环境(谨慎删除!)
if exist .venv (
    echo ⚠️  发现 .venv/ (Python虚拟环境,约2-5GB)
    echo ⚠️  删除后需要重新安装依赖: pip install -r requirements.txt
    set /p confirm_venv="是否删除? (y/n, 默认n): "
    if "%confirm_venv%"=="y" (
        echo ✅ 删除 .venv/
        rmdir /s /q .venv
    )
)

echo.
echo ========================================
echo   ✅ 清理完成!
echo ========================================
echo.
echo 📋 保留的核心文件:
echo   ✅ video_generator/      - 核心程序模块
echo   ✅ config.json           - 配置文件
echo   ✅ start.bat             - 启动脚本
echo   ✅ README.md             - 用户手册
echo   ✅ LICENSE               - 许可证
echo   ✅ assets/icon.ico       - 图标文件
echo.
echo 📋 保留的开发文件(不打包但需要保留):
echo   ℹ️  backend/             - 后端服务器(开发用)
echo   ℹ️  models/              - AI模型(用户自动下载)
echo   ℹ️  docs/                - 技术文档
echo   ℹ️  build_exe.py         - 打包脚本
echo   ℹ️  release_helper.py    - 发布助手
echo   ℹ️  installer_setup.iss  - Inno Setup脚本
echo.
echo 💡 下一步操作:
echo   1. 运行 python build_exe.py 进行打包
echo   2. 或双击: python build_exe.py
echo.
pause
