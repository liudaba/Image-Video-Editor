@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo.
echo ========================================
echo   短视频生成器 - 打包结果验证工具
echo ========================================
echo.

set OUTPUT_DIR=dist\VideoGenerator_Release

if not exist "%OUTPUT_DIR%" (
    if exist "dist\VideoGenerator" (
        set OUTPUT_DIR=dist\VideoGenerator
    ) else (
        echo ❌ 错误: 输出目录不存在
        echo 请先运行: python 01build_exe.py
        pause
        exit /b 1
    )
)

echo 📁 检查目录: %OUTPUT_DIR%
echo.

set ERROR_COUNT=0
set WARNING_COUNT=0

REM ========== 检查文件大小 ==========
echo 📊 检查文件大小...
for /f "tokens=*" %%i in ('powershell -NoProfile -command "[math]::Round((Get-ChildItem '%OUTPUT_DIR%' -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 2)"') do set SIZE=%%i
echo   当前大小: %SIZE% MB

powershell -NoProfile -command "$s=%SIZE%; if ($s -gt 2000) { exit 1 } elseif ($s -lt 500) { exit 2 } else { exit 0 }"
if !errorlevel! equ 1 (
    echo   ❌ 警告: 文件过大(超过2GB^),可能包含了不必要的文件
    echo   请检查是否包含了:
    echo   - .venv/ (虚拟环境,2-5GB^)
    echo   - models/ (AI模型,2-5GB^)
    echo   - backend/ (后端服务器^)
    set /a ERROR_COUNT+=1
) else if !errorlevel! equ 2 (
    echo   ❌ 警告: 文件过小(小于500MB^),可能缺少依赖
    set /a ERROR_COUNT+=1
) else (
    echo   ✅ 文件大小正常(800MB-1.5GB^)
)
echo.

REM ========== 检查不应该存在的文件夹 ==========
echo 🔍 检查不应该存在的文件夹...
set DIR_ERROR=0
for %%F in (.git .idea .vscode .venv __pycache__ backend models model_aware_patch output_project trash build dist docs logs) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F/
        set DIR_ERROR=1
        set /a ERROR_COUNT+=1
    )
)
if !DIR_ERROR! equ 0 (
    echo   ✅ 验证通过: 没有发现不该存在的文件夹
)
echo.

REM ========== 检查不应该存在的文件 ==========
echo 🔍 检查不应该存在的文件...
set FILE_ERROR=0

for %%F in (01build_exe.py 02build_exe.py obfuscate_build.py release_helper.py installer_setup.iss requirements.txt check_and_install_deps.bat generate_placeholders.py run.py run.pyw) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set FILE_ERROR=1
        set /a ERROR_COUNT+=1
    )
)

for %%F in (02验证打包结果.bat 推送代码.bat 快速发布.bat 检查环境.bat 生成Demo素材.bat check_and_install_deps.bat 停止后台管理系统.bat !!!FirstRun.bat 启动.vbs 启动主程序.bat) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set FILE_ERROR=1
        set /a ERROR_COUNT+=1
    )
)

for %%F in (GITHUB_IMPROVEMENT_GUIDE.md IMPROVEMENT_SUMMARY.md FINAL_REPORT.md) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 发现了不应该存在的 %%F
        set FILE_ERROR=1
        set /a ERROR_COUNT+=1
    )
)

for %%F in (.env license.json .secret_key .license_sign_key .key_salt) do (
    if exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 严重: 发现敏感文件 %%F - 绝不能分发!
        set FILE_ERROR=1
        set /a ERROR_COUNT+=1
    )
)

if exist "%OUTPUT_DIR%\后台管理系统启动器.py" (
    echo   ❌ 错误: 发现了不应该存在的 后台管理系统启动器.py
    set FILE_ERROR=1
    set /a ERROR_COUNT+=1
)

if !FILE_ERROR! equ 0 (
    echo   ✅ 验证通过: 没有发现不该存在的文件
)
echo.

REM ========== 检查应该存在的文件 ==========
echo 🔍 检查应该存在的文件...
set MISSING_ERROR=0

for %%F in (VideoGenerator.exe start.vbs start.bat QuickStart.md UserGuide.md config.json) do (
    if not exist "%OUTPUT_DIR%\%%F" (
        echo   ❌ 错误: 缺少必要文件 %%F
        set MISSING_ERROR=1
        set /a ERROR_COUNT+=1
    )
)

if not exist "%OUTPUT_DIR%\_internal" (
    echo   ❌ 错误: 缺少 _internal/ 目录(PyInstaller依赖库^)
    set MISSING_ERROR=1
    set /a ERROR_COUNT+=1
)

if exist "%OUTPUT_DIR%\.license_verify_key" (
    echo   ❌ 严重: 发现 HMAC 密钥 .license_verify_key - 绝不能分发!
    set /a ERROR_COUNT+=1
) else (
    echo   ✅ .license_verify_key 未包含（正确，HMAC密钥不应分发）
)

if exist "%OUTPUT_DIR%\LICENSE" (
    echo   ✅ LICENSE 已包含
) else (
    echo   ⚠️  LICENSE 缺失（建议包含许可证文件）
    set /a WARNING_COUNT+=1
)

if exist "%OUTPUT_DIR%\FirstRunSetup.bat" (
    echo   ✅ FirstRunSetup.bat 已包含
) else (
    echo   ⚠️  FirstRunSetup.bat 缺失（首次运行引导）
    set /a WARNING_COUNT+=1
)

if exist "%OUTPUT_DIR%\CheckEnv.bat" (
    echo   ✅ CheckEnv.bat 已包含
) else (
    echo   ⚠️  CheckEnv.bat 缺失（环境检查工具）
    set /a WARNING_COUNT+=1
)

if !MISSING_ERROR! equ 0 (
    echo   ✅ 验证通过: 所有必要文件都存在
)
echo.

REM ========== 检查启动脚本内容 ==========
echo 🔍 检查启动脚本内容...

findstr /C:"pythonw" "%OUTPUT_DIR%\start.vbs" >nul 2>&1
if not errorlevel 1 (
    echo   ❌ 错误: start.vbs 仍引用 pythonw（打包版应启动exe）
    set /a ERROR_COUNT+=1
) else (
    echo   ✅ start.vbs 内容正确（启动exe）
)

findstr /C:"pythonw" "%OUTPUT_DIR%\start.bat" >nul 2>&1
if not errorlevel 1 (
    echo   ❌ 错误: start.bat 仍引用 pythonw（打包版应启动exe）
    set /a ERROR_COUNT+=1
) else (
    echo   ✅ start.bat 内容正确（启动exe）
)
echo.

REM ========== 检查临时文件 ==========
echo 🔍 检查打包目录中的临时文件...
set TEMP_ERROR=0
for %%E in (bak tmp log) do (
    for /f "delims=" %%F in ('dir /b /s "%OUTPUT_DIR%\*.%%E" 2^>nul') do (
        echo   ⚠️  发现临时文件: %%F
        set TEMP_ERROR=1
        set /a ERROR_COUNT+=1
    )
)
for /f "delims=" %%F in ('dir /b /s "%OUTPUT_DIR%\*TEMP*.mp4" 2^>nul') do (
    echo   ⚠️  发现临时文件: %%F
    set TEMP_ERROR=1
    set /a ERROR_COUNT+=1
)
if !TEMP_ERROR! equ 0 (
    echo   ✅ 没有发现临时文件
)
echo.

REM ========== 最终结论 ==========
echo ========================================
echo   错误数: !ERROR_COUNT!   警告数: !WARNING_COUNT!
echo ----------------------------------------
if !ERROR_COUNT! gtr 0 (
    echo   ❌❌❌ 打包验证失败!
    echo.
    echo   请修复上述问题后重新打包
    echo.
    echo   💡 解决步骤:
    echo   1. 运行 python 01build_exe.py 重新打包
    echo   2. 再次运行本验证脚本
) else if !WARNING_COUNT! gtr 0 (
    echo   ⚠️⚠️⚠️ 打包验证基本通过，但有警告!
    echo.
    echo   部分功能可能需要额外配置才能正常使用
    echo   请查看上方 ⚠️ 标记的条目
) else (
    echo   ✅✅✅ 打包验证完全通过!
    echo.
    echo   可以将 %OUTPUT_DIR% 分发给用户
    echo.
    echo   💡 建议操作:
    echo   1. 将整个文件夹压缩成ZIP
    echo   2. 上传到网盘或CDN
    echo   3. 提供下载链接给用户
)
echo ========================================
echo.

pause
