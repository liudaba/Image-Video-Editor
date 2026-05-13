@echo off
title Video Generator - Main Program

echo ================================================================
echo.
echo   Video Generator - Main Program Launcher
echo.
echo ================================================================
echo.

cd /d "%~dp0"

REM Check Python
echo [1/4] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed!
    echo.
    echo Please install Python 3.10 or higher:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: During installation, make sure to check:
    echo   [x] Add Python to PATH
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo    OK: Python %PYTHON_VER%

REM Check or create virtual environment
echo.
echo [2/4] Checking virtual environment...
if not exist "venv" (
    echo    Creating virtual environment...
    python -m venv venv
    echo    OK: Virtual environment created
) else (
    echo    OK: Virtual environment exists
)

REM Install dependencies if needed
echo.
echo [3/4] Installing dependencies...
call venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import moviepy" >nul 2>&1
if errorlevel 1 (
    echo    Installing dependencies, please wait...
    pip install -r requirements.txt -q
    if errorlevel 1 (
        echo.
        echo ERROR: Failed to install dependencies!
        echo.
        echo Please try:
        echo   1. Right-click this file and select "Run as administrator"
        echo   2. Check your internet connection
        echo.
        pause
        exit /b 1
    )
    echo    OK: Dependencies installed
) else (
    echo    OK: Dependencies installed
)

REM Start main program
echo.
echo [4/4] Starting main program...
echo.
echo ================================================================
echo.
echo   Main Program Starting...
echo.
echo ================================================================
echo.
echo   If this is your first time, please:
echo   1. Register an account
echo   2. Activate your license
echo   3. Configure API keys in Settings
echo.
echo   For help, see README.md
echo.
echo ================================================================
echo.

REM Start in windowed mode (no console)
start "" venv\Scripts\pythonw.exe run.pyw

echo    OK: Program started!
echo.
echo    The program should open automatically.
echo    If not, check the window that just appeared.
echo.
timeout /t 3 >nul
