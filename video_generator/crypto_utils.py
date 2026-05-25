# -*- coding: utf-8 -*-
"""加密工具模块 - 提供字符串混淆和签名验证功能

用于客户端凭证持久化（密码混淆存储）和配置文件签名验证。
"""

import base64
import hashlib
import hmac as _hmac
import os
import logging

logger = logging.getLogger("crypto_utils")

# 混淆盐值（与 client_store.py 中的完整性哈希盐值配合使用）
_OBFUSCATION_KEY = "VGenCrypto2026_ObfuscationKey"


def obfuscate_string(text: str) -> str:
    """混淆字符串用于安全存储

    使用 XOR 加密 + Base64 编码，防止密码明文存储。

    Args:
        text: 原始字符串

    Returns:
        混淆后的字符串
    """
    if not text:
        return ""

    key_bytes = _OBFUSCATION_KEY.encode("utf-8")
    text_bytes = text.encode("utf-8")

    # XOR 加密：循环使用密钥字节
    encrypted = bytearray(len(text_bytes))
    for i, b in enumerate(text_bytes):
        encrypted[i] = b ^ key_bytes[i % len(key_bytes)]

    # Base64 编码
    return base64.b64encode(bytes(encrypted)).decode("ascii")


def deobfuscate_string(obfuscated: str) -> str:
    """反混淆字符串

    将 obfuscate_string 的输出还原为原始字符串。

    Args:
        obfuscated: 混淆后的字符串

    Returns:
        原始字符串

    Raises:
        ValueError: 如果输入不是有效的混淆字符串
    """
    if not obfuscated:
        return ""

    try:
        key_bytes = _OBFUSCATION_KEY.encode("utf-8")
        encrypted = base64.b64decode(obfuscated)

        # XOR 解密（与加密相同操作）
        decrypted = bytearray(len(encrypted))
        for i, b in enumerate(encrypted):
            decrypted[i] = b ^ key_bytes[i % len(key_bytes)]

        return decrypted.decode("utf-8")
    except Exception as e:
        logger.warning("反混淆失败: %s", e)
        raise ValueError(f"无效的混淆字符串: {e}")


def verify_config_signature(config_content: str, signature: str) -> bool:
    """验证配置文件的HMAC签名

    使用与打包脚本相同的密钥验证 config.json 的完整性，
    防止API地址等关键配置被篡改。

    Args:
        config_content: 配置文件的原始内容
        signature: 存储的签名值

    Returns:
        签名是否有效
    """
    if not config_content or not signature:
        return False

    try:
        _CONFIG_SIGN_KEY = "VideoGen2025ConfigSignatureKey_v1"
        expected = _hmac.new(
            _CONFIG_SIGN_KEY.encode("utf-8"),
            config_content.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return _hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.warning("配置签名验证异常: %s", e)
        return False
