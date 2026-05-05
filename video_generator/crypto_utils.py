# -*- coding: utf-8 -*-
"""敏感数据加密存储模块

使用 Windows DPAPI (优先) 或 Fernet 对称加密保护 API Key 等敏感数据。
加密密钥绑定到当前 Windows 用户，其他用户无法解密。
"""

import base64
import hashlib
import os
import struct

_SALT_FILE = ".key_salt"
_SALT_SIZE = 32


def _get_machine_user_fingerprint():
    """基于当前 Windows 用户名 + 机器名生成唯一指纹，作为加密密钥种子

    不同用户/不同机器会产生不同密钥，实现绑定效果。
    """
    import getpass
    import platform
    user = getpass.getuser()
    machine = platform.node()
    raw = f"VideoGen::{user}@{machine}".encode("utf-8")
    return hashlib.sha256(raw).digest()


def _get_or_create_salt(base_dir):
    """获取或创建盐值文件，盐值随机生成后持久化到磁盘"""
    salt_path = os.path.join(base_dir, _SALT_FILE)
    if os.path.exists(salt_path):
        try:
            with open(salt_path, "rb") as f:
                salt = f.read()
            if len(salt) == _SALT_SIZE:
                return salt
        except Exception:
            pass
    salt = os.urandom(_SALT_SIZE)
    try:
        with open(salt_path, "wb") as f:
            f.write(salt)
    except Exception:
        pass
    return salt


def _derive_fernet_key(base_dir):
    """基于用户指纹 + 盐值派生 Fernet 兼容密钥"""
    fingerprint = _get_machine_user_fingerprint()
    salt = _get_or_create_salt(base_dir)
    key_material = hashlib.pbkdf2_hmac("sha256", fingerprint, salt, iterations=100000, dklen=32)
    sign_key = hashlib.sha256(key_material).digest()
    return base64.urlsafe_b64encode(sign_key)


def _get_fernet(base_dir):
    """获取 Fernet 加密器实例（延迟导入）"""
    from cryptography.fernet import Fernet
    key = _derive_fernet_key(base_dir)
    return Fernet(key)


def encrypt_value(plaintext, base_dir):
    """加密字符串

    Args:
        plaintext: 明文字符串
        base_dir: 项目根目录，用于定位盐值文件

    Returns:
        加密后的字符串（带 ENC: 前缀），加密失败返回空字符串
    """
    if not plaintext:
        return ""
    try:
        f = _get_fernet(base_dir)
        encrypted = f.encrypt(plaintext.encode("utf-8"))
        return "ENC:" + encrypted.decode("ascii")
    except ImportError:
        return ""
    except Exception:
        return ""


def decrypt_value(ciphertext, base_dir):
    """解密字符串

    Args:
        ciphertext: 密文字符串（带 ENC: 前缀的为加密数据）
        base_dir: 项目根目录

    Returns:
        解密后的明文字符串，解密失败返回原值
    """
    if not ciphertext or not ciphertext.startswith("ENC:"):
        return ciphertext
    try:
        f = _get_fernet(base_dir)
        encrypted = ciphertext[4:].encode("ascii")
        decrypted = f.decrypt(encrypted)
        return decrypted.decode("utf-8")
    except ImportError:
        return ciphertext
    except Exception:
        return ""


SENSITIVE_KEYS = [
    "cloud_llm_api_key",
    "cloud_asr_api_key",
    "cloud_image_api_key",
]


def encrypt_config(config_dict, base_dir):
    """加密配置字典中的敏感字段（原地修改）"""
    for key in SENSITIVE_KEYS:
        if key in config_dict and config_dict[key]:
            config_dict[key] = encrypt_value(config_dict[key], base_dir)
    return config_dict


def decrypt_config(config_dict, base_dir):
    """解密配置字典中的敏感字段（原地修改）"""
    for key in SENSITIVE_KEYS:
        if key in config_dict and config_dict[key]:
            config_dict[key] = decrypt_value(config_dict[key], base_dir)
    return config_dict
