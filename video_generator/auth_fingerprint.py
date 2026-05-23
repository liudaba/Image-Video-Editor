# -*- coding: utf-8 -*-
"""机器指纹生成模块

生成唯一的机器指纹，用于设备绑定和防多设备滥用。
此模块为客户端核心安全模块，由 PyArmor 混淆保护。
"""

import hashlib
import platform
import os
import sys
import subprocess
import logging

logger = logging.getLogger("auth_fingerprint")


def _safe_run_cmd(cmd: str) -> str:
    """安全执行命令行并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _get_disk_serial() -> str:
    """获取Windows系统盘序列号"""
    if sys.platform != "win32":
        return ""
    output = _safe_run_cmd(
        'wmic diskdrive where "Index=0" get SerialNumber /value'
    )
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SerialNumber="):
            return line.split("=", 1)[1].strip()
    return ""


def _get_bios_serial() -> str:
    """获取BIOS序列号"""
    if sys.platform != "win32":
        return ""
    output = _safe_run_cmd("wmic bios get SerialNumber /value")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SerialNumber="):
            return line.split("=", 1)[1].strip()
    return ""


def _get_motherboard_serial() -> str:
    """获取主板序列号"""
    if sys.platform != "win32":
        return ""
    output = _safe_run_cmd("wmic baseboard get SerialNumber /value")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SerialNumber="):
            return line.split("=", 1)[1].strip()
    return ""


def _get_cpu_id() -> str:
    """获取CPU标识"""
    if sys.platform != "win32":
        return ""
    output = _safe_run_cmd("wmic cpu get ProcessorId /value")
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("ProcessorId="):
            return line.split("=", 1)[1].strip()
    return ""


def generate_fingerprint() -> str:
    """生成机器指纹

    组合多个硬件标识生成唯一指纹，用于设备绑定。
    指纹格式：sha256哈希的十六进制字符串（前32位）

    Returns:
        32字符的机器指纹字符串
    """
    components = []

    # CPU ID
    cpu_id = _get_cpu_id()
    if cpu_id:
        components.append(f"cpu:{cpu_id}")

    # 系统盘序列号
    disk_serial = _get_disk_serial()
    if disk_serial:
        components.append(f"disk:{disk_serial}")

    # 主板序列号
    mb_serial = _get_motherboard_serial()
    if mb_serial:
        components.append(f"mb:{mb_serial}")

    # BIOS序列号
    bios_serial = _get_bios_serial()
    if bios_serial:
        components.append(f"bios:{bios_serial}")

    # 平台信息作为兜底
    components.append(f"platform:{platform.node()}-{platform.machine()}")

    # 组合所有组件并哈希
    combined = "|".join(components)
    fingerprint = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]

    return fingerprint
