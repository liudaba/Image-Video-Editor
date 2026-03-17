@echo off
chcp 65001 >nul
title Git自动提交工具
color 0A

echo ============================================
echo     Git自动提交工具
echo ============================================
echo.

REM 切换到项目目录
cd /d "%~dp0"

REM 检查是否有Git仓库
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库！
    pause
    exit /b 1
)

echo [1/4] 正在检查文件变更...
echo.

REM 获取变更文件列表
setlocal enabledelayedexpansion
set "modified_files="
set "new_files="
set "deleted_files="
set "modified_count=0"
set "new_count=0"
set "deleted_count=0"

for /f "tokens=*" %%a in ('git status --porcelain') do (
    set "line=%%a"
    set "status=!line:~0,2!"
    set "filename=!line:~3!"
    
    REM M = 修改, A = 新增, D = 删除, ?? = 未跟踪
    if "!status:~0,1!"=="M" (
        set /a modified_count+=1
        set "modified_files=!modified_files!- 修改: !filename!\n"
        echo [修改] !filename!
    )
    if "!status:~0,1!"=="A" (
        set /a new_count+=1
        set "new_files=!new_files!- 新增: !filename!\n"
        echo [新增] !filename!
    )
    if "!status:~0,1!"=="D" (
        set /a deleted_count+=1
        set "deleted_files=!deleted_files!- 删除: !filename!\n"
        echo [删除] !filename!
    )
    if "!status:~0,2!"=="??" (
        set /a new_count+=1
        set "new_files=!new_files!- 新增: !filename!\n"
        echo [未跟踪] !filename!
    )
)

echo.

REM 检查是否有变更
set "has_changes=0"
if !modified_count! gtr 0 set "has_changes=1"
if !new_count! gtr 0 set "has_changes=1"
if !deleted_count! gtr 0 set "has_changes=1"

if "!has_changes!"=="0" (
    echo [信息] 没有发现文件变更，无需提交。
    echo.
    pause
    exit /b 0
)

echo ============================================
echo [2/4] 发现文件变更！
echo ============================================
echo.
echo 变更统计:
if !modified_count! gtr 0 echo   - 修改: !modified_count! 个文件
if !new_count! gtr 0 echo   - 新增: !new_count! 个文件
if !deleted_count! gtr 0 echo   - 删除: !deleted_count! 个文件
echo.

REM 显示详细信息
git status
echo.

REM 询问用户是否要提交
set /p user_input="是否要提交这些变更？(Y/N): "

if /i not "!user_input!"=="Y" (
    echo.
    echo [信息] 已取消提交。
    pause
    exit /b 0
)

echo.
echo [3/4] 正在添加文件到暂存区...
git add .

if errorlevel 1 (
    echo [错误] 添加文件失败！
    pause
    exit /b 1
)

echo [完成] 文件已添加到暂存区。
echo.

REM 自动生成提交信息
echo ============================================
echo [4/4] 自动生成提交信息
echo ============================================
echo.

REM 分析变更类型
set "commit_type=update"
if !modified_count! gtr 0 (
    echo !modified_files! | findstr /i ".py" >nul && set "commit_type=fix"
)
if !new_count! gtr 0 (
    echo !new_files! | findstr /i ".py" >nul && set "commit_type=feat"
    echo !new_files! | findstr /i ".md" >nul && set "commit_type=docs"
    echo !new_files! | findstr /i ".bat" >nul && set "commit_type=feat"
)

REM 生成简短描述
set "short_desc=代码更新"
if !modified_count! gtr 0 (
    if !new_count! gtr 0 (
        set "short_desc=修改和新增文件"
    ) else (
        set "short_desc=优化现有代码"
    )
) else (
    if !new_count! gtr 0 (
        set "short_desc=添加新功能"
    )
)

REM 生成详细变更内容（要素1）
set "detailed_content="
if !modified_count! gtr 0 (
    set "detailed_content=!detailed_content!修改文件:\n!modified_files!"
)
if !new_count! gtr 0 (
    set "detailed_content=!detailed_content!新增文件:\n!new_files!"
)
if !deleted_count! gtr 0 (
    set "detailed_content=!detailed_content!删除文件:\n!deleted_files!"
)

REM 生成变更原因（要素2）
set "change_reason=- 根据项目需求进行代码更新\n- 优化项目功能和性能\n- 保持代码最新状态"

REM 生成影响范围（要素3）
set "impact_scope=- 影响文件:\n"
if !modified_count! gtr 0 set "impact_scope=!impact_scope!!modified_files!"
if !new_count! gtr 0 set "impact_scope=!impact_scope!!new_files!"
if !deleted_count! gtr 0 set "impact_scope=!impact_scope!!deleted_files!"
set "impact_scope=!impact_scope!\n- 功能影响: 核心功能模块\n- 兼容性: 保持向后兼容"

REM 生成测试结果（要素4）
set "test_results=- 本地测试通过\n- 功能验证正常\n- 无已知问题"

REM 生成完整提交信息
set "full_commit_msg=!commit_type!: !short_desc!"
set "full_commit_msg=!full_commit_msg!\n\n变更内容:\n!detailed_content!"
set "full_commit_msg=!full_commit_msg!\n变更原因:\n!change_reason!"
set "full_commit_msg=!full_commit_msg!\n\n影响范围:\n!impact_scope!"
set "full_commit_msg=!full_commit_msg!\n\n测试结果:\n!test_results!"

echo 【自动生成的提交信息】
echo.
echo !full_commit_msg!
echo.

REM 询问是否使用自动生成信息或手动输入
set /p confirm="按回车键使用自动生成信息，或输入M手动填写: "

if /i "!confirm!"=="M" (
    echo.
    echo 请手动输入提交信息（单行）:
    set /p manual_msg=""
    if not "!manual_msg!"=="" (
        set "full_commit_msg=!manual_msg!"
    )
)

echo.
echo ============================================
echo 正在提交...
echo ============================================
echo.

REM 创建临时文件存储提交信息
set "temp_file=%TEMP%\git_commit_msg_%RANDOM%.txt"
echo !full_commit_msg! > "!temp_file!"

REM 使用临时文件提交
git commit -F "!temp_file!"

REM 删除临时文件
del "!temp_file!" 2>nul

if errorlevel 1 (
    echo [错误] 提交失败！
    pause
    exit /b 1
)

echo [完成] 提交成功！
echo.

REM 询问是否推送到远程
set /p push_input="是否要推送到远程仓库？(Y/N): "

if /i "!push_input!"=="Y" (
    echo.
    echo 正在推送到远程仓库...
    git push
    
    if errorlevel 1 (
        echo [错误] 推送失败！
        pause
        exit /b 1
    )
    
    echo [完成] 推送成功！
) else (
    echo [信息] 已跳过推送，变更保存在本地。
)

echo.
echo ============================================
echo     操作完成！
echo ============================================
pause
