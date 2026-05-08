@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

echo.
echo ===============================================
echo    短视频生成器 - 停止后台管理系统
echo ===============================================
echo.

set "PORT_FOUND=0"

echo [1/3] 尝试通过端口停止服务...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 "') do (
    echo       找到进程ID %%a 占用端口 8001
    echo       正在终止进程...
    taskkill /f /pid %%a >nul 2>&1
    if !errorlevel! equ 0 (
        echo       ✅ 进程已终止
        set "PORT_FOUND=1"
    ) else (
        echo       ❌ 无法终止进程
    )
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8002 "') do (
    echo       找到进程ID %%a 占用端口 8002
    echo       正在终止进程...
    taskkill /f /pid %%a >nul 2>&1
    if !errorlevel! equ 0 (
        echo       ✅ 进程已终止
        set "PORT_FOUND=1"
    ) else (
        echo       ❌ 无法终止进程
    )
)

if !PORT_FOUND! equ 0 (
    echo       未找到占用端口 8001 或 8002 的进程
)

echo.
echo [2/3] 尝试终止 Python uvicorn 进程...

set "UVICORN_FOUND=0"
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr python.exe') do (
    set "PID=%%a"
    set "PID=!PID:"=!"
    for /f "tokens=*" %%c in ('wmic process where "ProcessID=!PID!" get Commandline ^| findstr /C:"uvicorn" 2^>nul') do (
        echo       找到 uvicorn 进程ID: !PID!
        echo       正在终止进程...
        taskkill /f /pid !PID! >nul 2>&1
        if !errorlevel! equ 0 (
            echo       ✅ uvicorn 进程已终止
            set "UVICORN_FOUND=1"
        ) else (
            echo       ❌ 无法终止进程
        )
    )
)

if !UVICORN_FOUND! equ 0 (
    echo       未找到 uvicorn 进程
)

echo.
echo [3/3] 验证服务是否已停止...

timeout /t 1 /nobreak >nul

set "STOPPED=1"
netstat -an | findstr ":8001 " >nul
if !errorlevel! equ 0 (
    echo       ⚠️  端口 8001 仍被占用
    set "STOPPED=0"
)

netstat -an | findstr ":8002 " >nul
if !errorlevel! equ 0 (
    echo       ⚠️  端口 8002 仍被占用
    set "STOPPED=0"
)

echo.
if !STOPPED! equ 1 (
    echo ✅ 后台管理系统已成功停止
) else (
    echo ⚠️  部分服务可能仍在运行，请手动检查
)

echo.
echo 按任意键退出...
pause >nul