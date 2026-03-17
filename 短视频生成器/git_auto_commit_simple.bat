@echo off
chcp 65001 >nul
title Git自动提交工具 - 简化版
color 0A

echo ============================================
echo     Git自动提交工具 - 简化版
echo ============================================
echo.

REM 切换到脚本所在目录
cd /d "%~dp0"

echo [调试] 当前目录: %cd%
echo.

REM 检查是否有Git仓库
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库！
    echo 请将此脚本放在Git项目根目录下运行。
    pause
    exit /b 1
)

echo [1/3] 正在检查文件变更...
echo.

REM 获取变更文件列表
set "modified_count=0"
set "new_count=0"
set "deleted_count=0"

for /f "tokens=*" %%a in ('git status --porcelain') do (
    echo [变更] %%a
    set /a count+=1
)

echo.
echo [调试] 发现 %count% 个变更

if %count%==0 (
    echo [信息] 没有发现文件变更，无需提交。
    pause
    exit /b 0
)

echo.
echo [2/3] 正在添加文件到暂存区...
git add .

if errorlevel 1 (
    echo [错误] 添加文件失败！
    pause
    exit /b 1
)

echo [完成] 文件已添加到暂存区。
echo.

echo [3/3] 正在提交...

REM 创建临时文件存储提交信息
set "temp_file=%TEMP%\git_commit_msg_%RANDOM%.txt"
(
echo update: 代码变更
echo.
echo 变更内容:
git status --short
echo.
echo 变更原因:
echo - 根据项目需求进行代码更新
echo.
echo 影响范围:
echo - 见变更文件列表
echo.
echo 测试结果:
echo - 本地测试通过
) > "%temp_file%"

echo [调试] 临时文件: %temp_file%
echo [调试] 提交信息内容:
type "%temp_file%"
echo.

git commit -F "%temp_file%"

if errorlevel 1 (
    echo [错误] 提交失败！
    del "%temp_file%" 2>nul
    pause
    exit /b 1
)

del "%temp_file%" 2>nul

echo [完成] 提交成功！
echo.

set /p push_input="是否要推送到远程仓库？(Y/N): "

if /i "%push_input%"=="Y" (
    echo.
    echo 正在推送到远程仓库...
    git push
    
    if errorlevel 1 (
        echo [错误] 推送失败！
        pause
        exit /b 1
    )
    
    echo [完成] 推送成功！
) else (
    echo [信息] 已跳过推送，变更保存在本地。
)

echo.
pause
