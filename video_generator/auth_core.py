# -*- coding: utf-8 -*-
"""授权核心模块 - 统一导出层

从 license_manager 导出核心类和函数，供 auth_dialogs.py 使用。
此模块为客户端核心安全模块，由 PyArmor 混淆保护。

模块职责：
- 作为 auth_dialogs.py 的唯一业务逻辑入口
- 导出 LicenseManager 类和验证密钥获取函数
- 隔离 UI 层与底层实现
"""

from .license_manager import LicenseManager


def _get_verify_secret() -> str:
    """获取本地签名验证密钥/公钥内容

    用于客户端验证许可证数据的签名是否由服务端签发。
    如果密钥文件不存在，返回空字符串。

    Returns:
        验证密钥内容字符串，或空字符串
    """
    import os
    import sys

    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 优先检查 ECDSA 公钥
    pubkey_path = os.path.join(app_dir, ".license_verify_pubkey.pem")
    if os.path.exists(pubkey_path):
        try:
            with open(pubkey_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    # 其次检查 HMAC 验证密钥
    verify_key_path = os.path.join(app_dir, ".license_verify_key")
    if os.path.exists(verify_key_path):
        try:
            with open(verify_key_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    return ""


__all__ = ["LicenseManager", "_get_verify_secret"]
