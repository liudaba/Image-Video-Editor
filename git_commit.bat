@echo off
title Git Auto Commit Tool
color 0A

echo ============================================
echo    Git Auto Commit Tool
echo ============================================
echo.

cd /d "%~dp0"

if not exist ".git" (
    if exist "..\.git" (
        cd ..
        echo [Info] Switched to parent directory: %cd%
    ) else (
        echo [Error] Not a git repository!
        pause
        exit /b 1
    )
)

echo [Step 1/4] Checking for changes...
echo.

git status --short

echo.
echo [Step 2/4] Adding all files...
git add -A

echo.
echo [Step 3/4] Committing...
git commit -m "feat: 更新代码 - %date% %time%"

echo.
echo [Step 4/4] Pushing to remote...
git push

echo.
echo ============================================
echo    Completed!
echo ============================================
echo.
pause
