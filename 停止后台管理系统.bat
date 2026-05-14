@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

echo.
echo ===============================================
echo    短视频生成器 - 停止后台管理系统
echo ===============================================
echo.

set "PORT_FOUND=0"
set "KILLED_PIDS="

echo [1/3] 尝试通过端口停止服务...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:"  *8001 "' 2^>nul') do (
    set "ALREADY_KILLED=0"
    for %%k in (!KILLED_PIDS!) do (
        if "%%a"=="%%k" set "ALREADY_KILLED=1"
    )
    if !ALREADY_KILLED! equ 0 (
        echo       找到进程ID %%a 占用端口 8001
        echo       正在终止进程...
        taskkill /f /pid %%a >nul 2>&1
        if !errorlevel! equ 0 (
            echo       ✅ 进程已终止
            set "PORT_FOUND=1"
            set "KILLED_PIDS=!KILLED_PIDS! %%a"
        ) else (
            echo       ❌ 无法终止进程
        )
    )
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr /R /C:"  *8000 "' 2^>nul') do (
    set "ALREADY_KILLED=0"
    for %%k in (!KILLED_PIDS!) do (
        if "%%a"=="%%k" set "ALREADY_KILLED=1"
    )
    if !ALREADY_KILLED! equ 0 (
        echo       找到进程ID %%a 占用端口 8000
        echo       正在终止进程...
        taskkill /f /pid %%a >nul 2>&1
        if !errorlevel! equ 0 (
            echo       ✅ 进程已终止
            set "PORT_FOUND=1"
            set "KILLED_PIDS=!KILLED_PIDS! %%a"
        ) else (
            echo       ❌ 无法终止进程
        )
    )
)

if !PORT_FOUND! equ 0 (
    echo       未找到占用端口 8000 或 8001 的进程
)

echo.
echo [2/3] 尝试终止 Python uvicorn 进程...

set "UVICORN_FOUND=0"
for /f %%a in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*uvicorn*' } | Select-Object -ExpandProperty ProcessId" 2^>nul') do (
    set "PID=%%a"
    set "ALREADY_KILLED=0"
    for %%k in (!KILLED_PIDS!) do (
        if "!PID!"=="%%k" set "ALREADY_KILLED=1"
    )
    if !ALREADY_KILLED! equ 0 (
        echo       找到 uvicorn 进程ID: !PID!
        echo       正在终止进程...
        taskkill /f /pid !PID! >nul 2>&1
        if !errorlevel! equ 0 (
            echo       ✅ uvicorn 进程已终止
            set "UVICORN_FOUND=1"
            set "KILLED_PIDS=!KILLED_PIDS! !PID!"
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

timeout /t 2 /nobreak >nul

set "STOPPED=1"
netstat -an | findstr /R /C:"  *8001 .*LISTEN" >nul 2>&1
if !errorlevel! equ 0 (
    echo       ⚠️  端口 8001 仍被占用
    set "STOPPED=0"
)

netstat -an | findstr /R /C:"  *8000 .*LISTEN" >nul 2>&1
if !errorlevel! equ 0 (
    echo       ⚠️  端口 8000 仍被占用
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
