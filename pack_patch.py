#!/usr/bin/env python
"""增量补丁打包工具 - 供 PackPatch.bat 或命令行调用

用法:
    python pack_patch.py <新版本号> [更新说明] [--force]
    
示例:
    python pack_patch.py 2.0.1 "修复登录异常，优化视频生成速度"
    python pack_patch.py 2.1.0 "新增批量导出功能" --force
"""
import sys
import os
import subprocess
import json

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from video_generator.auto_updater import create_patch_zip
from video_generator.version import get_version


def get_changed_files():
    """从git获取变更文件列表（已提交 + 未提交）"""
    files = set()

    # 1. 最近一次提交的变更（首次提交时 HEAD~1 不存在，需要用 --diff-filter）
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1'],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line:
                    files.add(line)
        else:
            # 首次提交，尝试用 git diff --cached HEAD（无父提交）
            result2 = subprocess.run(
                ['git', 'diff', '--name-only', '--cached'],
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            for line in result2.stdout.strip().split('\n'):
                line = line.strip()
                if line:
                    files.add(line)
    except Exception:
        pass

    # 2. 工作区未提交的变更
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only'],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line:
                files.add(line)
    except Exception:
        pass

    # 3. 暂存区变更
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', '--cached'],
            capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line:
                files.add(line)
    except Exception:
        pass

    return sorted(files)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    new_version = sys.argv[1]

    # 验证版本号格式
    import re
    if not re.match(r'^\d+\.\d+\.\d+$', new_version):
        print(f"错误: 版本号格式不正确 '{new_version}'，应为 X.Y.Z 格式（如 2.0.1）")
        sys.exit(1)

    release_notes = ''
    force_update = False

    # 解析参数
    for arg in sys.argv[2:]:
        if arg == '--force':
            force_update = True
        elif not release_notes:
            release_notes = arg

    old_version = get_version()

    print(f"新版本号: {new_version}")
    print(f"当前版本: {old_version}")
    print(f"更新说明: {release_notes or '(无)'}")
    print(f"强制更新: {'是' if force_update else '否'}")
    print()

    # 获取变更文件
    all_changed = get_changed_files()
    if not all_changed:
        print("未检测到任何变更文件。请确认已修改文件并提交。")
        sys.exit(1)

    print(f"所有变更文件 ({len(all_changed)}):")
    for f in all_changed:
        print(f"  {f}")
    print()

    # 过滤：打包 video_generator/ 下的文件 + run.py/run.pyw + 根目录脚本文件(.bat/.ps1)
    root_scripts = {f for f in all_changed if '/' not in f and os.path.splitext(f)[1].lower() in ('.bat', '.ps1')}
    client_files = [f for f in all_changed if f.startswith('video_generator/') or f in ('run.py', 'run.pyw') or f in root_scripts]
    if not client_files:
        print("变更文件中没有 video_generator/ 下的文件，无需生成补丁。")
        print("如果是后端或文档变更，不需要客户端补丁更新。")
        sys.exit(0)

    print(f"需要打包的文件 ({len(client_files)}):")
    for f in client_files:
        print(f"  {f}")
    print()

    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'patches')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'update_{old_version}_to_{new_version}.zip')

    # 生成补丁包
    print("正在生成补丁包...")
    result = create_patch_zip(
        version=new_version,
        from_version=old_version,
        changed_files=client_files,
        output_path=output_path,
        release_notes=release_notes,
        force_update=force_update,
    )

    print()
    print("=" * 50)
    print("  补丁包生成成功！")
    print("=" * 50)
    print(f"  路径:   {result['path']}")
    print(f"  SHA256: {result['sha256']}")
    print(f"  大小:   {result['size']} bytes ({result['size']/1024:.1f} KB)")
    print(f"  文件数: {result['file_count']}")
    print()
    print("后续步骤:")
    print("  1. 在管理后台创建版本，填写补丁信息")
    print("  2. 上传补丁文件到CDN/对象存储")
    print("  3. 将下载地址和SHA256填入版本记录")
    print("  4. 客户端将自动检测并提示增量更新")


if __name__ == '__main__':
    main()
