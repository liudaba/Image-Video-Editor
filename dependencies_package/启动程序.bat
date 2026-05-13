@echo off
title 短视频生成器 - 离线版

echo ================================================================
echo.
echo   短视频生成器 - 离线版启动程序
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
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
echo    OK: Python %PYTHON_VER%

REM Check virtual environment
echo.
echo [2/4] Checking virtual environment...
if not exist "venv" (
    echo.
    echo ERROR: Virtual environment not found!
    echo.
    echo The dependencies_package folder seems incomplete.
    echo Please re-download the complete package.
    echo.
    pause
    exit /b 1
) else (
    echo    OK: Virtual environment found
)

REM Activate virtual environment
echo.
echo [3/4] Activating virtual environment...
call venv\Scripts\activate.bat
echo    OK: Virtual environment activated

REM Verify dependencies
echo.
echo [4/4] Verifying dependencies...
python -c "import moviepy; import whisper; import torch" >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Some dependencies are missing!
    echo Please re-download the complete offline package.
    echo.
    pause
    exit /b 1
) else (
    echo    OK: All dependencies verified
)

REM Start main program
echo.
echo ================================================================
echo.
echo   Main Program Starting...
echo.
echo ================================================================
echo.

REM Start in windowed mode
start "" venv\Scripts\pythonw.exe run.pyw

echo    OK: Program started!
echo.
echo    The program should open automatically.
echo    If not, check the window that just appeared.
echo.
timeout /t 3 >nul
