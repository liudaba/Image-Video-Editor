# -*- coding: utf-8 -*-
"""
短视频生成器 - 版本管理模块
统一管理版本号，供自动更新、关于对话框、后端API等使用
支持 version.json 运行时版本覆盖（补丁更新后无需重新打包exe）
"""

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("version")

__version__ = "1.0.0"
__app_name__ = "短视频生成器"
__app_name_en__ = "VideoGen"
__build_number__ = 2026052301

VERSION_TUPLE = tuple(int(x) for x in __version__.split("."))

# 运行时版本文件路径（补丁更新写入此文件）
if getattr(sys, "frozen", False):
    _VERSION_JSON_PATH = Path(sys.executable).resolve().parent / "version.json"
else:
    _VERSION_JSON_PATH = Path(__file__).resolve().parent.parent / "version.json"


def _is_valid_version(v: str) -> bool:
    try:
        parts = v.split(".")
        return len(parts) >= 2 and all(p.isdigit() for p in parts)
    except Exception:
        return False


def get_version() -> str:
    """获取运行时版本号，优先读取 version.json（补丁更新后版本号可能已变更）"""
    try:
        if _VERSION_JSON_PATH.exists():
            data = json.loads(_VERSION_JSON_PATH.read_text(encoding="utf-8"))
            runtime_ver = data.get("version", "")
            if runtime_ver and _is_valid_version(runtime_ver):
                return runtime_ver
    except Exception as e:
        logger.debug(f"Failed to read version.json: {e}")
    return __version__


def get_version_info() -> dict:
    return {
        "version": get_version(),
        "app_name": __app_name__,
        "app_name_en": __app_name_en__,
        "build_number": __build_number__,
    }


def compare_versions(v1: str, v2: str) -> int:
    """比较两个版本号，返回 1(v1>v2) / 0(相等) / -1(v1<v2)"""
    try:
        t1 = tuple(int(x) for x in v1.split("."))
    except (ValueError, AttributeError):
        t1 = (0, 0, 0)
    try:
        t2 = tuple(int(x) for x in v2.split("."))
    except (ValueError, AttributeError):
        t2 = (0, 0, 0)
    if t1 > t2:
        return 1
    elif t1 < t2:
        return -1
    return 0
