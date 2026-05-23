# -*- coding: utf-8 -*-
"""加密工具模块

提供字符串混淆/反混淆等安全工具函数，用于保护敏感配置信息。
此模块为客户端核心安全模块，由 PyArmor 混淆保护。
"""

import base64
import hashlib


# 混淆种子表：用于简单的字符串混淆，防止明文暴露
_OBFUSCATION_SEED = "VideoGen2025SecureObfuscationSeed"


def obfuscate_string(plain: str) -> str:
    """混淆字符串，生成可逆的混淆表示

    Args:
        plain: 明文字符串

    Returns:
        混淆后的十六进制字符串
    """
    if not plain:
        return ""
    key_bytes = _OBFUSCATION_SEED.encode("utf-8")
    plain_bytes = plain.encode("utf-8")
    result = bytearray(len(plain_bytes))
    for i, b in enumerate(plain_bytes):
        result[i] = b ^ key_bytes[i % len(key_bytes)]
    return base64.b16encode(bytes(result)).decode("ascii").lower()


def deobfuscate_string(obfuscated: str) -> str:
    """反混淆字符串，还原原始明文

    Args:
        obfuscated: 混淆后的十六进制字符串

    Returns:
        原始明文字符串
    """
    if not obfuscated:
        return ""
    try:
        key_bytes = _OBFUSCATION_SEED.encode("utf-8")
        obf_bytes = base64.b16decode(obfuscated.upper())
        result = bytearray(len(obf_bytes))
        for i, b in enumerate(obf_bytes):
            result[i] = b ^ key_bytes[i % len(key_bytes)]
        return result.decode("utf-8")
    except Exception:
        return ""


# ============ 配置文件签名校验 ============

# 签名密钥（与构建脚本中的密钥保持一致）
_CONFIG_SIGN_KEY = "VideoGen2025ConfigSignatureKey_v1"


def compute_config_signature(config_content: str) -> str:
    """计算配置文件内容的HMAC-SHA256签名

    Args:
        config_content: 配置文件的原始文本内容

    Returns:
        十六进制签名字符串
    """
    import hmac as _hmac
    return _hmac.new(
        _CONFIG_SIGN_KEY.encode("utf-8"),
        config_content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_config_signature(config_content: str, signature: str) -> bool:
    """验证配置文件签名

    Args:
        config_content: 配置文件的原始文本内容
        signature: 待验证的签名

    Returns:
        True 如果签名验证通过
    """
    import hmac as _hmac
    expected = compute_config_signature(config_content)
    return _hmac.compare_digest(expected, signature)


# ============ 配置文件敏感字段加密/解密 ============

# 需要加密的配置键名（API Key等敏感信息）
_SENSITIVE_KEYS = frozenset([
    "cloud_llm_api_key",
    "cloud_asr_api_key",
    "cloud_image_api_key",
])

# 加密标记前缀
_ENCRYPTED_PREFIX = "ENC:"


def encrypt_config(config: dict, base_dir: str = "") -> dict:
    """加密配置中的敏感字段（原地修改并返回）

    对 API Key 等敏感字段使用 XOR 混淆，防止明文存储在 config.json 中。

    Args:
        config: 配置字典
        base_dir: 应用根目录（用于签名文件路径）

    Returns:
        修改后的配置字典
    """
    for key in _SENSITIVE_KEYS:
        value = config.get(key, "")
        if value and not value.startswith(_ENCRYPTED_PREFIX):
            encrypted = obfuscate_string(value)
            config[key] = _ENCRYPTED_PREFIX + encrypted
    return config


def decrypt_config(config: dict, base_dir: str = "") -> dict:
    """解密配置中的敏感字段（原地修改并返回）

    将加密的 API Key 等字段还原为明文，供运行时使用。

    Args:
        config: 配置字典
        base_dir: 应用根目录（用于签名文件路径）

    Returns:
        修改后的配置字典
    """
    for key in _SENSITIVE_KEYS:
        value = config.get(key, "")
        if value and value.startswith(_ENCRYPTED_PREFIX):
            encrypted_part = value[len(_ENCRYPTED_PREFIX):]
            decrypted = deobfuscate_string(encrypted_part)
            config[key] = decrypted
    return config
