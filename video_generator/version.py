# -*- coding: utf-8 -*-
"""
短视频生成器 - 版本管理模块
统一管理版本号，供自动更新、关于对话框、后端API等使用
"""

__version__ = "2.0.0"
__app_name__ = "短视频生成器"
__app_name_en__ = "VideoGen"
__build_number__ = 2026051601

VERSION_TUPLE = tuple(int(x) for x in __version__.split("."))


def get_version():
    return __version__


def get_version_info():
    return {
        "version": __version__,
        "app_name": __app_name__,
        "app_name_en": __app_name_en__,
        "build_number": __build_number__,
    }


def compare_versions(v1, v2):
    """比较两个版本号，返回 1(v1>v2) / 0(相等) / -1(v1<v2)"""
    t1 = tuple(int(x) for x in v1.split("."))
    t2 = tuple(int(x) for x in v2.split("."))
    if t1 > t2:
        return 1
    elif t1 < t2:
        return -1
    return 0
