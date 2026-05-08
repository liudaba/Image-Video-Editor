@echo off
setlocal EnableDelayedExpansion

echo.
echo ===============================================
echo    Short Video Generator - Stop Backend Service
echo ===============================================
echo.

set "PORT_FOUND=0"

echo [1/3] Stopping service by port...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 "') do (
    echo       Found process ID %%a on port 8001
    echo       Terminating process...
    taskkill /f /pid %%a >nul 2>&1
    if !errorlevel! equ 0 (
        echo       Process terminated successfully
        set "PORT_FOUND=1"
    ) else (
        echo       Failed to terminate process
    )
)

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8002 "') do (
    echo       Found process ID %%a on port 8002
    echo       Terminating process...
    taskkill /f /pid %%a >nul 2>&1
    if !errorlevel! equ 0 (
        echo       Process terminated successfully
        set "PORT_FOUND=1"
    ) else (
        echo       Failed to terminate process
    )
)

if !PORT_FOUND! equ 0 (
    echo       No process found on port 8001 or 8002
)

echo.
echo [2/3] Stopping Python uvicorn processes...

set "UVICORN_FOUND=0"
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV ^| findstr python.exe') do (
    set "PID=%%a"
    set "PID=!PID:"=!"
    for /f "tokens=*" %%c in ('wmic process where "ProcessID=!PID!" get Commandline ^| findstr /C:"uvicorn" 2^>nul') do (
        echo       Found uvicorn process ID: !PID!
        echo       Terminating process...
        taskkill /f /pid !PID! >nul 2>&1
        if !errorlevel! equ 0 (
            echo       Uvicorn process terminated
            set "UVICORN_FOUND=1"
        ) else (
            echo       Failed to terminate process
        )
    )
)

if !UVICORN_FOUND! equ 0 (
    echo       No uvicorn process found
)

echo.
echo [3/3] Verifying service stopped...

timeout /t 1 /nobreak >nul

set "STOPPED=1"
netstat -an | findstr ":8001 " >nul
if !errorlevel! equ 0 (
    echo       WARNING: Port 8001 still in use
    set "STOPPED=0"
)

netstat -an | findstr ":8002 " >nul
if !errorlevel! equ 0 (
    echo       WARNING: Port 8002 still in use
    set "STOPPED=0"
)

echo.
if !STOPPED! equ 1 (
    echo Service stopped successfully
) else (
    echo Some services may still be running, please check manually
)

echo.
echo Press any key to exit...
pause >nul