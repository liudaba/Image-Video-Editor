# -*- coding: utf-8 -*-
"""敏感数据加密存储模块

使用 Fernet 对称加密保护 API Key 等敏感数据。
加密密钥绑定到当前 Windows 用户+机器，其他用户无法解密。
"""

import base64
import hashlib
import os

_SALT_FILE = ".key_salt"
_SALT_SIZE = 32


def _get_machine_user_fingerprint():
    import getpass
    import platform
    user = getpass.getuser()
    machine = platform.node()
    raw = f"VideoGen::{user}@{machine}".encode("utf-8")
    base_hash = hashlib.sha256(raw).digest()

    extra_parts = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            extra_parts.append(guid)
    except Exception:
        pass

    if not extra_parts:
        try:
            from .auth_fingerprint import _get_disk_serial, _get_cpu_id
            disk = _get_disk_serial()
            cpu = _get_cpu_id()
            if disk:
                extra_parts.append(f"disk:{disk}")
            if cpu:
                extra_parts.append(f"cpu:{cpu}")
        except Exception:
            pass

    if extra_parts:
        combined = f"{base_hash.hex()}::{'::'.join(extra_parts)}".encode("utf-8")
        return hashlib.sha256(combined).digest()
    return base_hash


def _get_or_create_salt(base_dir):
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
    fingerprint = _get_machine_user_fingerprint()
    salt = _get_or_create_salt(base_dir)
    key_material = hashlib.pbkdf2_hmac("sha256", fingerprint, salt, iterations=100000, dklen=32)
    return base64.urlsafe_b64encode(key_material)


def _get_fernet(base_dir):
    from cryptography.fernet import Fernet
    key = _derive_fernet_key(base_dir)
    return Fernet(key)


def encrypt_value(plaintext, base_dir):
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
    if not ciphertext or not ciphertext.startswith("ENC:"):
        return ciphertext
    try:
        f = _get_fernet(base_dir)
        encrypted = ciphertext[4:].encode("ascii")
        decrypted = f.decrypt(encrypted)
        return decrypted.decode("utf-8")
    except ImportError:
        return ""
    except Exception:
        return ""


SENSITIVE_KEYS = [
    "cloud_llm_api_key",
    "cloud_asr_api_key",
    "cloud_image_api_key",
]


def encrypt_config(config_dict, base_dir):
    for key in SENSITIVE_KEYS:
        if key in config_dict and config_dict[key]:
            config_dict[key] = encrypt_value(config_dict[key], base_dir)
    return config_dict


def decrypt_config(config_dict, base_dir):
    for key in SENSITIVE_KEYS:
        if key in config_dict and config_dict[key]:
            config_dict[key] = decrypt_value(config_dict[key], base_dir)
    return config_dict


_OBFUSCATION_SEED = b"VideoGen2026ObfSeed"


def _get_obfuscation_key():
    try:
        import getpass
        import platform
        user = getpass.getuser()
        machine = platform.node()
        raw = f"ObfKey::{user}@{machine}".encode("utf-8")
        import hashlib
        derived = hashlib.sha256(_OBFUSCATION_SEED + raw).digest()
        return derived
    except Exception:
        return _OBFUSCATION_SEED * 2


def _obfuscate_string(plaintext):
    key = _get_obfuscation_key()
    data = plaintext.encode("utf-8")
    result = bytearray()
    for i, b in enumerate(data):
        result.append(b ^ key[i % len(key)])
    return result.hex()


def deobfuscate_string(hex_str):
    try:
        key = _get_obfuscation_key()
        data = bytes.fromhex(hex_str)
        result = bytearray()
        for i, b in enumerate(data):
            result.append(b ^ key[i % len(key)])
        return result.decode("utf-8")
    except Exception:
        return ""


def verify_core_integrity():
    """运行时自校验：检测核心模块是否被篡改"""
    try:
        import sys
        if getattr(sys, "frozen", False):
            base_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
            if not os.path.isdir(base_dir):
                base_dir = os.path.dirname(sys.executable)
            core_files = [
                os.path.join(base_dir, "video_generator", "auth_core.py"),
                os.path.join(base_dir, "video_generator", "auth_fingerprint.py"),
            ]
            for filepath in core_files:
                if not os.path.exists(filepath):
                    continue
                with open(filepath, "rb") as f:
                    content = f.read()
                if b"os._exit" in content or b"import antidebug" in content:
                    return False
            return True
        core_files = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_core.py"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth_fingerprint.py"),
        ]
        for filepath in core_files:
            if not os.path.exists(filepath):
                continue
            with open(filepath, "rb") as f:
                content = f.read()
            if b"os._exit" in content or b"import antidebug" in content:
                return False
        return True
    except Exception:
        return True
