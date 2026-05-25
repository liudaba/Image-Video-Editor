# -*- coding: utf-8 -*-
"""机器指纹生成模块

生成唯一的机器指纹用于许可证绑定验证。
综合多种硬件特征生成稳定的指纹标识。
"""

import hashlib
import logging
import platform
import os
import struct
import subprocess

# Windows 下隐藏子进程的控制台窗口，防止蓝色命令框闪烁
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

logger = logging.getLogger("auth_fingerprint")


def _run_wmic(command: str, field: str) -> str:
    """运行WMIC或PowerShell命令获取硬件信息

    优先使用wmic，在Windows 11 23H2+（wmic已弃用）上回退到PowerShell。
    """
    try:
        if platform.system() == "Windows":
            # 优先尝试 wmic（更快）
            try:
                result = subprocess.run(
                    ["wmic", command],
                    capture_output=True, text=True, timeout=5,
                    creationflags=_SUBPROCESS_FLAGS
                )
                if result.returncode == 0:
                    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
                    if len(lines) > 1:
                        return lines[1].strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            # wmic 不可用时，回退到 PowerShell（兼容 Windows 11 23H2+）
            try:
                ps_cmd = f"(Get-CimInstance -ClassName {field} | Select-Object -First 1).{command.split()[-1]}"
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=10,
                    creationflags=_SUBPROCESS_FLAGS
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    except Exception:
        pass
    return ""


def _get_disk_serial() -> str:
    """获取系统磁盘序列号"""
    return _run_wmic("diskdrive get serialnumber", "Win32_DiskDrive")


def _get_mac_address() -> str:
    """获取第一个非回环网络接口的MAC地址"""
    try:
        import uuid
        mac = uuid.getnode()
        # uuid.getnode() 失败时返回随机值（多播地址，最低位为1）
        # 正确的检测方式：检查最低字节的最低位是否为1（多播/随机标志）
        if mac & 0x010000000000:
            return ""
        return f"{mac:012x}"
    except Exception:
        pass
    return ""


def _get_cpu_info() -> str:
    """获取CPU标识信息"""
    result = _run_wmic("cpu get ProcessorId", "Win32_Processor")
    if result:
        return result
    return platform.processor() or ""


def _get_motherboard_serial() -> str:
    """获取主板序列号"""
    return _run_wmic("baseboard get serialnumber", "Win32_BaseBoard")


def generate_fingerprint() -> str:
    """生成机器指纹

    综合多种硬件特征生成唯一的32字符指纹标识。
    指纹在同一台机器上应保持稳定。

    Returns:
        32字符的十六进制指纹字符串
    """
    components = []

    # 主机名
    components.append(platform.node())

    # CPU信息
    cpu_info = _get_cpu_info()
    if cpu_info:
        components.append(cpu_info)

    # 磁盘序列号
    disk_serial = _get_disk_serial()
    if disk_serial:
        components.append(disk_serial)

    # MAC地址
    mac = _get_mac_address()
    if mac:
        components.append(mac)

    # 主板序列号
    mb_serial = _get_motherboard_serial()
    if mb_serial:
        components.append(mb_serial)

    # 机器架构
    components.append(platform.machine())

    # 组合所有组件并生成哈希
    combined = "|".join(components)
    fingerprint = hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]

    logger.debug("机器指纹: %s (组件数: %d)", fingerprint, len(components))
    return fingerprint
