@echo off
chcp 65001 >nul
title Git变更监控
color 0E

echo ============================================
echo     Git变更监控工具
echo ============================================
echo.
echo 此工具会每30秒检查一次文件变更
echo 发现变更时会弹出提示
echo.
echo 按 Ctrl+C 停止监控
echo.

REM 切换到项目目录
cd /d "%~dp0"

REM 检查是否有Git仓库
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库！
    pause
    exit /b 1
)

:loop
cls
echo ============================================
echo     Git变更监控运行中... [%time%]
echo ============================================
echo.

REM 检查是否有变更
set "has_changes=0"

for /f "tokens=*" %%a in ('git status --porcelain') do (
    if "!has_changes!"=="0" (
        echo [发现变更！]
        echo.
    )
    set "has_changes=1"
    echo %%a
)

if "!has_changes!"=="1" (
    echo.
    echo ============================================
    echo ⚠️  发现文件变更！建议提交到Git仓库
    echo ============================================
    echo.
    echo 按任意键打开自动提交工具...
    pause >nul
    start "" "git_auto_commit.bat"
) else (
    echo [状态] 暂无变更 - 上次检查: %time%
)

echo.
echo 30秒后再次检查...
timeout /t 30 /nobreak >nul
goto loop
