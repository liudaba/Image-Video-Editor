# Git Auto Commit and Push Script
# 保存为 git_push.ps1

$ErrorActionPreference = "Continue"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   Git Auto Commit Tool" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 切换到脚本目录
Set-Location $PSScriptRoot

# 检查git仓库
if (-not (Test-Path ".git")) {
    Write-Host "[Error] Not a git repository!" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# 检查变更
Write-Host "[Step 1/4] Checking for changes..." -ForegroundColor Yellow
$status = git status --short
if ($status) {
    Write-Host "Found changes:" -ForegroundColor Green
    $status | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "No changes to commit." -ForegroundColor Gray
    Read-Host "Press Enter to exit"
    exit 0
}

Write-Host ""
Write-Host "[Step 2/4] Adding files..." -ForegroundColor Yellow
git add -A

Write-Host ""
Write-Host "[Step 3/4] Committing..." -ForegroundColor Yellow
git commit -m "feat: Auto update - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

Write-Host ""
Write-Host "[Step 4/4] Pushing to remote..." -ForegroundColor Yellow
git push

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "   Completed!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

Read-Host "Press Enter to exit"
