@echo off
chcp 65001 >nul 2>&1
title VideoGenerator - Create Desktop Shortcut

echo.
echo  ==========================================
echo     VideoGenerator - Create Desktop Shortcut
echo  ==========================================
echo.

cd /d "%~dp0"

if not exist "VideoGenerator.exe" if not exist "start.vbs" (
    echo  [ERROR] VideoGenerator.exe or start.vbs not found
    echo  Please confirm this script is in the application root directory
    echo.
    pause
    exit /b 1
)

set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CreateShortcut.ps1" -AppDir "%APP_DIR%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [ERROR] Failed to create shortcut
    echo.
    pause
    exit /b 1
)

echo.
echo  Desktop shortcut created. Double-click the VideoGenerator icon on your desktop to start.
echo.
pause
