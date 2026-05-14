# -*- coding: utf-8 -*-
"""
代码混淆构建脚本 - 使用PyArmor保护核心模块
用法: python obfuscate_build.py
"""

import os
import sys
import json
import shutil
import subprocess


def check_pyarmor():
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pyarmor", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print(f"✅ PyArmor 已安装: {result.stdout.strip()}")
            return True
    except Exception:
        pass
    print("❌ PyArmor 未安装，正在安装...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyarmor"], check=True)
    return True


def obfuscate_modules():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "pyarmor_config.json")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    output_dir = os.path.join(base_dir, config["build_output"])
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    core_modules = [
        "video_generator/auth_core.py",
        "video_generator/auth_dialogs.py",
        "video_generator/auth_fingerprint.py",
        "video_generator/license_manager.py",
        "video_generator/crypto_utils.py",
        "video_generator/auto_updater.py",
    ]

    for module_path in core_modules:
        src = os.path.join(base_dir, module_path)
        if not os.path.exists(src):
            print(f"⚠️  跳过不存在的模块: {module_path}")
            continue

        module_name = os.path.splitext(os.path.basename(module_path))[0]
        module_output = os.path.join(output_dir, os.path.dirname(module_path))
        os.makedirs(module_output, exist_ok=True)

        print(f"🔒 混淆模块: {module_path}")

        cmd = [
            sys.executable, "-m", "pyarmor",
            "gen",
            "--output", module_output,
            "--restrict",
            "--assert-call",
            "--assert-import",
            "--obf-code", "2",
            src
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=base_dir)
        if result.returncode != 0:
            print(f"❌ 混淆失败: {module_path}")
            print(f"   错误: {result.stderr}")
            continue
        print(f"   ✅ 混淆完成: {module_name}")

    print("\n📋 后续步骤:")
    print("   1. 检查 dist_obfuscated/ 目录中的混淆文件")
    print("   2. 将混淆后的文件替换到打包目录中")
    print("   3. 运行 01build_exe.py 打包发布版本")


if __name__ == "__main__":
    check_pyarmor()
    obfuscate_modules()
