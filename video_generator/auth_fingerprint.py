# -*- coding: utf-8 -*-
"""弹性机器指纹模块

评分制指纹验证，允许部分硬件变更而不锁死用户。
- 采集5类硬件组件，按权重计算匹配分数
- 分数 >= 60：自动通过（如有变更则自动更新注册信息）
- 分数 40-59：需要确认身份后重新绑定
- 分数 < 40：判定为不同电脑，拒绝通过

向后兼容：get_machine_fingerprint() 保持与原 license_manager.py 完全相同的算法，
确保现有用户的指纹哈希不会因本次重构而改变。
"""

import hashlib
import logging

logger = logging.getLogger(__name__)

COMPONENTS_CONFIG = {
    "machine_guid": {"weight": 30, "stable": True},
    "disk_serial": {"weight": 25, "stable": False},
    "cpu_id": {"weight": 20, "stable": True},
    "mac_address": {"weight": 15, "stable": False},
    "bios_uuid": {"weight": 10, "stable": True},
}

MATCH_THRESHOLD = 60
REBIND_THRESHOLD = 40


def _get_machine_guid():
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return guid
    except Exception:
        return ""


def _get_disk_serial():
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "diskdrive", "get", "serialnumber"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [
            l.strip()
            for l in result.stdout.strip().split("\n")
            if l.strip() and "SerialNumber" not in l
        ]
        if lines:
            return lines[0]
    except Exception:
        pass
    return ""


def _get_cpu_id():
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "cpu", "get", "ProcessorId"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [
            l.strip()
            for l in result.stdout.strip().split("\n")
            if l.strip() and "ProcessorId" not in l
        ]
        if lines:
            return lines[0]
    except Exception:
        pass
    return ""


def _get_mac_address():
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "nic", "get", "MACAddress"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [
            l.strip()
            for l in result.stdout.strip().split("\n")
            if l.strip() and "MACAddress" not in l and l.strip()
        ]
        if lines:
            return lines[0]
    except Exception:
        pass
    return ""


def _get_bios_uuid():
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [
            l.strip()
            for l in result.stdout.strip().split("\n")
            if l.strip() and "UUID" not in l
        ]
        if lines:
            return lines[0]
    except Exception:
        pass
    return ""


def get_fingerprint_components():
    """采集所有硬件组件信息，返回字典"""
    return {
        "machine_guid": _get_machine_guid(),
        "disk_serial": _get_disk_serial(),
        "cpu_id": _get_cpu_id(),
        "mac_address": _get_mac_address(),
        "bios_uuid": _get_bios_uuid(),
    }


def get_machine_fingerprint():
    """生成机器指纹哈希

    保持与原 license_manager.py 完全相同的算法：
    user@machine -> SHA256 -> 追加 MachineGuid + disk_serial -> 再次SHA256
    确保现有用户的指纹不会因重构而改变。
    """
    try:
        import getpass
        import platform

        user = getpass.getuser()
        machine = platform.node()
        raw = f"VideoGen::{user}@{machine}".encode("utf-8")
        base_hash = hashlib.sha256(raw).hexdigest()

        extra_parts = []
        guid = _get_machine_guid()
        if guid:
            extra_parts.append(guid)
        disk = _get_disk_serial()
        if disk:
            extra_parts.append(disk)

        if extra_parts:
            combined = f"{base_hash}::{'::'.join(extra_parts)}".encode("utf-8")
            return hashlib.sha256(combined).hexdigest()
        return base_hash
    except Exception:
        return "unknown"


def compute_fingerprint_score(current_components, registered_components):
    """计算指纹匹配分数

    Returns:
        (score, changed_components): 匹配分数和变更的组件列表
    """
    score = 0
    changed_components = []
    for comp, config in COMPONENTS_CONFIG.items():
        current_val = current_components.get(comp, "")
        registered_val = registered_components.get(comp, "")
        if current_val and registered_val and current_val == registered_val:
            score += config["weight"]
        elif current_val or registered_val:
            changed_components.append(comp)
    return score, changed_components


def verify_fingerprint(current_components, registered_components):
    """验证指纹，返回验证结果

    Returns:
        dict with keys:
            - match: bool
            - score: int
            - changed: list
            - action: "pass" / "auto_update" / "rebind" / "reject"
    """
    score, changed = compute_fingerprint_score(current_components, registered_components)

    if score >= MATCH_THRESHOLD:
        if changed:
            return {
                "match": True,
                "score": score,
                "changed": changed,
                "action": "auto_update",
            }
        return {"match": True, "score": score, "changed": [], "action": "pass"}

    if score >= REBIND_THRESHOLD:
        return {
            "match": False,
            "score": score,
            "changed": changed,
            "action": "rebind",
        }

    return {"match": False, "score": score, "changed": changed, "action": "reject"}
