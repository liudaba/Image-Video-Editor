@echo off
title Git Auto Commit Tool
color 0A

echo ============================================
echo    Git Auto Commit Tool
echo ============================================
echo.

REM 切换到项目根目录（Git仓库所在目录）
cd /d "%~dp0"

REM 检查当前目录是否有.git，如果没有则切换到父目录
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
echo feat: 优化分镜生成功能，提升性能和用户体验
echo.
echo 【功能优化】
echo 1. 新增全文上下文支持：大模型能够理解整篇转录文本内容，生成更精准的专业纪录片风格画面描述
echo 2. 新增Ollama并行处理：设置OLLAMA_NUM_PARALLEL=8环境变量，支持多线程并行请求
echo 3. 优化线程数配置：根据Ollama单线程特性，将分镜创建线程数从32减少到8
echo 4. 简化prompt长度：优化system prompt和user prompt，减少输入长度加快生成速度
echo.
echo 【体验优化】
echo 1. 启动速度优化：移除启动时的Ollama连接尝试，加快程序启动
echo 2. 模型菜单响应优化：先显示默认模型列表，后台异步获取真实模型
echo 3. 配置保存/加载修复：恢复用户设置的优化方式和模型选择延续功能
echo 4. 添加线程ID日志：方便调试多线程并行执行情况
echo.
echo 【问题修复】
echo 1. 修复配置不能延续问题：load_config函数不再强制覆盖用户保存的设置
echo 2. 修复启动时Ollama错误：移除discover_available_models调用
echo.
echo 【生成的Prompt格式示例】
echo 原来：chaotic, intense, ruthless, no boundaries, masterpiece, best quality
echo 现在：documentary photography, cinematic still, war journalism, raw photo, chaotic urban warfare scene, destroyed buildings, smoke and debris, emergency vehicles, civilians running, dramatic lighting, 8k uhd, high detail, film grain, natural lighting, shot on 35mm, masterpiece, best quality
) > "%msg_file%"

git status --short >> "%msg_file%"

(
echo.
echo Test: 功能测试通过
echo Impact: 提升分镜生成质量和速度，优化用户体验
) >> "%msg_file%"

echo Commit message:
type "%msg_file%"
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
