@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   短视频生成器 - 打包结果验证工具
echo ========================================
echo.

set OUTPUT_DIR=dist\短视频生成器

REM 检查输出目录是否存在
if not exist "%OUTPUT_DIR%" (
    echo ❌ 错误: 输出目录不存在
    echo 请先运行: python build_exe.py
    pause
    exit /b 1
)

echo 📁 检查目录: %OUTPUT_DIR%
echo.

REM ========== 检查文件大小 ==========
echo 📊 检查文件大小...
for /f "tokens=*" %%i in ('powershell -command "(Get-ChildItem '%OUTPUT_DIR%' -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB"') do set SIZE=%%i
echo   当前大小: %SIZE% MB

if %SIZE% GTR 2000 (
    echo   ❌ 警告: 文件过大(超过2GB),可能包含了不必要的文件
    echo   请检查是否包含了:
    echo   - .venv/ (虚拟环境,2-5GB)
    echo   - models/ (AI模型,2-5GB)
    echo   - backend/ (后端服务器)
) else if %SIZE% LSS 500 (
    echo   ❌ 警告: 文件过小(小于500MB),可能缺少依赖
) else (
    echo   ✅ 文件大小正常(800MB-1.5GB)
)
echo.

REM ========== 检查不应该存在的文件夹 ==========
echo 🔍 检查不应该存在的文件夹...
set HAS_ERROR=0

for %%F in (.git .idea .vscode .venv __pycache__ backend models model_aware_patch output_project 垃圾桶 build dist docs) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F/
        set HAS_ERROR=1
    )
)

if %HAS_ERROR%==0 (
    echo   ✅ 验证通过: 没有发现不该存在的文件夹
)
echo.

REM ========== 检查不应该存在的文件 ==========
echo 🔍 检查不应该存在的文件...
set HAS_ERROR=0

for %%F in (02build_exe.py release_helper.py installer_setup.iss requirements.txt check_and_install_deps.bat generate_placeholders.py run.py run.pyw GITHUB_IMPROVEMENT_GUIDE.md) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set HAS_ERROR=1
    )
)

REM 检查其他.bat文件(除了start.bat)
for %%F in (01打包前清理.bat 03验证打包结果.bat 快速发布.bat 推送代码.bat 检查环境.bat 生成Demo素材.bat check_and_install_deps.bat) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set HAS_ERROR=1
    )
)

REM 检查其他.md文件(除了README.md和快速上手指南.md)
for %%F in (GITHUB_IMPROVEMENT_GUIDE.md) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set HAS_ERROR=1
    )
)

if %HAS_ERROR%==0 (
    echo   ✅ 验证通过: 没有发现不该存在的文件
)
echo.

REM ========== 检查应该存在的文件 ==========
echo 🔍 检查应该存在的文件...
set HAS_ERROR=0

for %%F in (短视频生成器.exe 启动.vbs start.bat README.md 快速上手指南.md LICENSE config.json video_generator) do (
    if not exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 缺少必要文件 %%F
        set HAS_ERROR=1
    )
)

REM 检查_internal目录(PyInstaller依赖)
if not exist "%OUTPUT_DIR%\_internal" (
    echo   ❌ 错误: 缺少 _internal/ 目录(PyInstaller依赖库)
    set HAS_ERROR=1
)

if %HAS_ERROR%==0 (
    echo   ✅ 验证通过: 所有必要文件都存在
)
echo.

REM ========== 检查临时文件 ==========
echo 🔍 检查临时文件...
set HAS_TEMP=0

for %%F in (*.bak *.tmp *.log *TEMP*.mp4) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ⚠️  发现临时文件: %%F
        set HAS_TEMP=1
    )
)

if %HAS_TEMP%==0 (
    echo   ✅ 没有发现临时文件
)
echo.

REM ========== 最终结论 ==========
echo ========================================
if %HAS_ERROR%==0 (
    echo   ✅✅✅ 打包验证完全通过!
    echo.
    echo   可以将 %OUTPUT_DIR% 分发给用户
    echo.
    echo   💡 建议操作:
    echo   1. 将整个文件夹压缩成ZIP
    echo   2. 上传到网盘或CDN
    echo   3. 提供下载链接给用户
) else (
    echo   ❌❌❌ 打包验证失败!
    echo.
    echo   请修复上述问题后重新打包
    echo.
    echo   💡 解决步骤:
    echo   1. 运行 打包前清理.bat
    echo   2. 检查 build_exe.py 的排除规则
    echo   3. 重新运行: python build_exe.py
    echo   4. 再次运行本验证脚本
)
echo ========================================
echo.

pause
