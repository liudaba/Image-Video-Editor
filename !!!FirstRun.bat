@echo off
chcp 65001 >nul 2>&1
title VideoGenerator - First Run Guide

echo.
echo  ================================================
echo    Welcome to VideoGenerator!
echo    This is your first time, please follow these steps:
echo  ================================================
echo.
echo    1. Double-click FirstRunSetup.bat to check environment
echo    2. Or double-click start.vbs to launch the software
echo    3. Register an account after startup to get 15-day free trial
echo.
echo  ================================================
echo    Having problems?
echo    Double-click CheckEnv.bat to auto-detect and fix
echo  ================================================
echo.
echo  Starting first run setup...
echo.

cd /d "%~dp0"

if exist "FirstRunSetup.bat" (
    call "FirstRunSetup.bat"
) else if exist "start.vbs" (
    start "" "start.vbs"
) else if exist "VideoGenerator.exe" (
    start "" "VideoGenerator.exe"
) else (
    echo  [ERROR] Startup file not found, please confirm complete extraction
    echo.
    pause
)
