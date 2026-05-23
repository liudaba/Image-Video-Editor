# -*- coding: utf-8 -*-
"""客户端本地存储模块 - SQLite 替代 JSON 文件

将 .license_credentials 和 .license_cache 从 JSON 明文存储
迁移到 SQLite 数据库，提供原子写入、防篡改校验、断电安全等保障。

此模块为客户端核心安全模块，由 PyArmor 混淆保护。
"""

import json
import os
import sys
import sqlite3
import hashlib
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger("client_store")

# 线程安全的数据库连接锁
_db_lock = threading.Lock()


def _get_db_path() -> str:
    """获取数据库文件路径"""
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(app_dir, ".client_store.db")


def _get_connection() -> sqlite3.Connection:
    """获取数据库连接（启用WAL模式提升并发性能）"""
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def _init_db():
    """初始化数据库表结构"""
    with _db_lock:
        conn = _get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    username TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    save_user INTEGER NOT NULL DEFAULT 0,
                    save_pass INTEGER NOT NULL DEFAULT 0,
                    saved_at TEXT NOT NULL DEFAULT '',
                    integrity_hash TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS license_cache (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    license_data TEXT NOT NULL DEFAULT '{}',
                    cached_at TEXT NOT NULL DEFAULT '',
                    integrity_hash TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                );
            """)
            conn.commit()
        finally:
            conn.close()


def _compute_integrity_hash(*fields: str) -> str:
    """计算字段值的完整性哈希，用于防篡改校验

    使用 SHA-256 对字段值拼接后计算哈希。
    密钥为硬编码的内部盐值，增加篡改难度。
    """
    _SALT = "VGenStore2026 IntegrityGuard"
    payload = _SALT + "|".join(fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _verify_integrity(*fields: str, expected_hash: str) -> bool:
    """校验字段值的完整性"""
    return _compute_integrity_hash(*fields) == expected_hash


# ============ 凭证管理 ============

def save_credentials(username: str, password: str, save_user: bool, save_pass: bool):
    """保存登录凭证到数据库

    Args:
        username: 用户名
        password: 已混淆的密码
        save_user: 是否保存用户名
        save_pass: 是否保存密码
    """
    _init_db()
    saved_at = datetime.now(timezone.utc).isoformat()
    integrity_hash = _compute_integrity_hash(
        username, password, str(int(save_user)), str(int(save_pass)), saved_at
    )

    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO credentials
                    (id, username, password, save_user, save_pass, saved_at, integrity_hash)
                VALUES (1, ?, ?, ?, ?, ?, ?)
            """, (username, password, int(save_user), int(save_pass), saved_at, integrity_hash))
            conn.commit()
        except Exception as e:
            logger.debug("保存凭证到数据库失败: %s", e)
        finally:
            conn.close()


def load_credentials() -> Tuple[str, str, bool, bool]:
    """加载保存的登录凭证

    Returns:
        (username, password, save_user, save_pass) 元组
    """
    _init_db()
    with _db_lock:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT username, password, save_user, save_pass, saved_at, integrity_hash FROM credentials WHERE id = 1"
            ).fetchone()
            if row is None:
                return "", "", False, False

            username, password, save_user, save_pass, saved_at, integrity_hash = row
            save_user = bool(save_user)
            save_pass = bool(save_pass)

            # 完整性校验
            if not _verify_integrity(
                username, password, str(int(save_user)), str(int(save_pass)), saved_at,
                expected_hash=integrity_hash
            ):
                logger.warning("凭证完整性校验失败，可能被篡改，已清除")
                clear_credentials()
                return "", "", False, False

            return username, password, save_user, save_pass
        except Exception as e:
            logger.debug("从数据库加载凭证失败: %s", e)
            return "", "", False, False
        finally:
            conn.close()


def clear_credentials():
    """清除保存的登录凭证"""
    _init_db()
    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM credentials WHERE id = 1")
            conn.commit()
        except Exception as e:
            logger.debug("清除凭证失败: %s", e)
        finally:
            conn.close()


# ============ 许可证缓存管理 ============

def save_license_cache(license_data: dict):
    """保存许可证数据到本地缓存

    Args:
        license_data: 许可证数据字典
    """
    _init_db()
    cached_at = datetime.now(timezone.utc).isoformat()
    data_str = json.dumps(license_data, ensure_ascii=False, sort_keys=True)
    integrity_hash = _compute_integrity_hash(data_str, cached_at)

    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO license_cache
                    (id, license_data, cached_at, integrity_hash)
                VALUES (1, ?, ?, ?)
            """, (data_str, cached_at, integrity_hash))
            conn.commit()
        except Exception as e:
            logger.debug("保存许可证缓存到数据库失败: %s", e)
        finally:
            conn.close()


def load_license_cache() -> Optional[dict]:
    """从本地缓存加载许可证数据

    Returns:
        许可证数据字典，如果缓存不存在或校验失败则返回 None
    """
    _init_db()
    with _db_lock:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT license_data, cached_at, integrity_hash FROM license_cache WHERE id = 1"
            ).fetchone()
            if row is None:
                return None

            data_str, cached_at, integrity_hash = row

            # 完整性校验
            if not _verify_integrity(data_str, cached_at, expected_hash=integrity_hash):
                logger.warning("许可证缓存完整性校验失败，可能被篡改，已清除")
                clear_license_cache()
                return None

            return json.loads(data_str)
        except Exception as e:
            logger.debug("从数据库加载许可证缓存失败: %s", e)
            return None
        finally:
            conn.close()


def clear_license_cache():
    """清除许可证缓存"""
    _init_db()
    with _db_lock:
        conn = _get_connection()
        try:
            conn.execute("DELETE FROM license_cache WHERE id = 1")
            conn.commit()
        except Exception as e:
            logger.debug("清除许可证缓存失败: %s", e)
        finally:
            conn.close()


# ============ JSON 迁移 ============

def migrate_from_json():
    """从旧版 JSON 文件迁移数据到 SQLite

    迁移完成后自动删除旧 JSON 文件。
    此函数只需执行一次，重复调用是安全的（幂等）。
    """
    if getattr(sys, "frozen", False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    _init_db()

    # 迁移凭证
    cred_path = os.path.join(app_dir, ".license_credentials")
    if os.path.exists(cred_path):
        try:
            with open(cred_path, "r", encoding="utf-8") as f:
                cred = json.load(f)
            username = cred.get("username", "")
            password = cred.get("password", "")
            save_user = cred.get("save_user", False)
            save_pass = cred.get("save_pass", False)
            # 只有当数据库中还没有凭证时才迁移
            existing = load_credentials()
            if not existing[0] and not existing[1]:
                save_credentials(username, password, save_user, save_pass)
            # 迁移成功后删除旧文件
            os.remove(cred_path)
            logger.info("凭证从JSON迁移到SQLite完成")
        except Exception as e:
            logger.debug("凭证迁移失败: %s", e)

    # 迁移许可证缓存
    cache_path = os.path.join(app_dir, ".license_cache")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                license_data = json.load(f)
            # 只有当数据库中还没有缓存时才迁移
            existing_cache = load_license_cache()
            if existing_cache is None:
                save_license_cache(license_data)
            # 迁移成功后删除旧文件
            os.remove(cache_path)
            logger.info("许可证缓存从JSON迁移到SQLite完成")
        except Exception as e:
            logger.debug("许可证缓存迁移失败: %s", e)
