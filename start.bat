@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "APP_DIR=%~dp0"

REM 优先级1：便携版（内嵌Python环境）
if exist "%APP_DIR%python\python.exe" (
    if exist "%APP_DIR%run.py" (
        if exist "%APP_DIR%ffmpeg\ffmpeg.exe" set "FFMPEG_BINARY=%APP_DIR%ffmpeg\ffmpeg.exe"
        start "" "%APP_DIR%python\pythonw.exe" "%APP_DIR%run.pyw"
        exit /b 0
    )
)

REM 优先级2：PyInstaller打包版
if exist "%APP_DIR%VideoGenerator.exe" (
    if exist "%APP_DIR%_internal\python310.dll" (
        if exist "%APP_DIR%ffmpeg\ffmpeg.exe" set "FFMPEG_BINARY=%APP_DIR%ffmpeg\ffmpeg.exe"
        start "" "%APP_DIR%VideoGenerator.exe"
        exit /b 0
    )
)

REM 优先级3：开发模式（venv或系统Python）
if exist "venv\Scripts\pythonw.exe" (
    start "" venv\Scripts\pythonw.exe run.pyw
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" .venv\Scripts\pythonw.exe run.pyw
) else (
    start "" pythonw run.pyw
)
