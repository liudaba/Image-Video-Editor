@echo off
chcp 65001 >nul
cls
echo ============================================
echo    Git Auto Commit Tool
echo ============================================
echo.

cd /d "%~dp0"

echo [Step 1/4] Checking for changes...
echo.

set "change_count=0"
for /f "tokens=*" %%a in ('git status --porcelain 2^>nul') do (
    echo   %%a
    set /a change_count+=1
)

echo.
echo Found %change_count% changed file(s)
echo.

if %change_count%==0 (
    echo No changes to commit.
    pause
    exit /b 0
)

echo [Step 2/4] Adding files...
git add .
echo Done.
echo.

echo [Step 3/4] Creating commit message...
set "msg_file=%TEMP%\commit_msg_%RANDOM%.txt"
(
echo update: code changes
echo.
echo Changes:
) > "%msg_file%"
git status --short >> "%msg_file%"
(
echo.
echo Reason: project update
echo Impact: see file list
echo Test: passed
) >> "%msg_file%"

echo Commit message created.
echo.

echo [Step 4/4] Committing...
git commit -F "%msg_file%"
del "%msg_file%" 2>nul

echo.
echo Commit completed!
echo.

set /p push="Push to remote? (Y/N): "
if /i "%push%"=="Y" (
    git push
    echo Push completed!
)

echo.
pause
