#!/usr/bin/env python3
"""短视频生成器 - 发布助手"""

import subprocess
import sys
import os
import re
from datetime import datetime


def get_current_version():
    version_file = os.path.join(os.path.dirname(__file__), "video_generator", "version.py")
    with open(version_file, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        return match.group(1)
    return "0.0.0"


def bump_version(version, bump_type="patch"):
    parts = version.split(".")
    if len(parts) != 3:
        return version
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}"


def update_version_file(new_version):
    version_file = os.path.join(os.path.dirname(__file__), "video_generator", "version.py")
    with open(version_file, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
        content,
    )
    build_date = datetime.now().strftime("%Y%m%d")
    build_num = int(datetime.now().strftime("%H")) + 1
    content = re.sub(
        r'__build_number__\s*=\s*\d+',
        f'__build_number__ = {build_date}{build_num:02d}',
        content,
    )
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ 版本已更新为 {new_version}")


def git_commit_push(message):
    cmds = [
        ["git", "add", "-A"],
        ["git", "commit", "-m", message],
        ["git", "push"],
    ]
    for cmd in cmds:
        print(f"  执行: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            print(f"  ⚠️ {result.stderr.strip()}")


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    args = sys.argv[1:]
    current = get_current_version()
    print(f"当前版本: {current}")

    version = None
    message = None

    i = 0
    while i < len(args):
        if args[i] == "--version" and i + 1 < len(args):
            version = args[i + 1]
            i += 2
        elif args[i] == "--message" and i + 1 < len(args):
            message = args[i + 1]
            i += 2
        else:
            i += 1

    if not version:
        version = bump_version(current, "patch")

    if not message:
        message = f"v{version} 发布"

    print(f"\n发布版本: {version}")
    print(f"提交信息: {message}")
    print()

    update_version_file(version)
    git_commit_push(message)

    print(f"\n🎉 发布完成! 版本 {version} 已推送到远程仓库")


if __name__ == "__main__":
    main()
