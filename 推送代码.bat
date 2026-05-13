@echo off
chcp 65001
cls
echo ============================================
echo  自动推送代码到远程仓库
echo ============================================
echo.
cd /d "%~dp0"

echo [1/5] 检查 Git 状态...
git status --short
echo.

echo [2/5] 检测更改的文件...
set "changes="

:: 检查是否有新的模块文件
if exist "video_generator\config.py" set "changes=%changes%新增config模块, "
if exist "video_generator\cache.py" set "changes=%changes%新增cache模块, "
if exist "video_generator\parallel.py" set "changes=%changes%新增parallel模块, "
if exist "video_generator\sd_generator.py" set "changes=%changes%新增sd_generator模块, "
if exist "video_generator\hardware.py" set "changes=%changes%新增hardware模块, "
if exist "video_generator\ollama_client.py" set "changes=%changes%新增ollama_client模块, "
if exist "video_generator\multi_model.py" set "changes=%changes%新增multi_model模块, "
if exist "video_generator\templates.py" set "changes=%changes%新增templates模块, "

:: 检查 __init__.py 是否有修改
git diff --name-only video_generator\__init__.py >nul 2>&1
if %errorlevel%==0 set "changes=%changes%更新__init__.py, "

:: 检查主文件是否有修改
git diff --name-only "My-Video Generator.py" >nul 2>&1
if %errorlevel%==0 set "changes=%changes%更新主文件, "

:: 清理末尾的逗号和空格
if not "%changes%"=="" set "changes=%changes:~0,-2%"

:: 如果没有检测到具体变化，使用默认信息
if "%changes%"=="" set "changes=更新代码"

echo 检测到的更改: %changes%
echo.

echo [3/5] 添加更改文件...
git add video_generator/ config.json.example 01build_exe.py obfuscate_build.py pyarmor_config.json .gitignore

echo.
echo [4/5] 提交代码...
git commit -m "%changes%"

echo.
echo [5/5] 推送到远程仓库...
git push

echo.
echo ============================================
if %errorlevel%==0 (
    echo ✅ 推送成功！
) else (
    echo ❌ 推送失败，请检查网络连接
)
echo ============================================

echo.
pause
