# -*- coding: utf-8 -*-
"""许可证管理器 - 客户端核心授权模块

负责客户端与服务端的认证交互、许可证状态管理、心跳检测、
凭证持久化等核心功能。

此模块为客户端核心安全模块，由 PyArmor 混淆保护。
"""

import json
import os
import sys
import time
import threading
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any

from .config import get_api_base_url, get_http_session
from .client_store import (
    save_credentials as _db_save_credentials,
    load_credentials as _db_load_credentials,
    clear_credentials as _db_clear_credentials,
    save_license_cache as _db_save_license_cache,
    load_license_cache as _db_load_license_cache,
    clear_license_cache as _db_clear_license_cache,
    migrate_from_json as _db_migrate_from_json,
)

logger = logging.getLogger("license_manager")

# ============ 离线容忍配置 ============
# 与服务端 license_service.py 的 offline_hours_map 保持一致
# 商业运营版：收紧离线容忍窗口，防止钻空子
_OFFLINE_TOLERANCE = {
    "trial": 2,        # 试用2小时（原4小时，收紧防止滥用）
    "trial_15d": 2,    # 试用2小时
    "monthly": 12,     # 月度12小时（原24小时，半天内必须联网验证）
    "quarterly": 24,   # 季度24小时（原48小时）
    "yearly": 48,      # 年度48小时（原72小时，2天内联网即可）
    "lifetime": 72,    # 终身72小时（原168小时/7天太长，3天足够）
    "pro": 48,         # PRO会员48小时（原72小时）
}

# 心跳间隔（秒）
_HEARTBEAT_INTERVAL = 180  # 3分钟
# 心跳失败后重试间隔
_HEARTBEAT_RETRY_INTERVAL = 30
# 最大连续心跳失败次数，超过后标记授权失效
_MAX_HEARTBEAT_FAILURES = 5


def _get_app_dir() -> str:
    """获取应用根目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_verify_key_path() -> str:
    """获取签名验证公钥路径"""
    return os.path.join(_get_app_dir(), ".license_verify_pubkey.pem")


class LicenseManager:
    """许可证管理器（单例模式）

    负责客户端授权的完整生命周期：
    - 登录/注册/激活
    - 许可证本地缓存与签名验证
    - 心跳检测与离线容忍
    - 凭证持久化（保存密码/自动登录）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._token = None
                instance.license_data = None
                instance._heartbeat_thread = None
                instance._heartbeat_running = False
                instance._heartbeat_failures = 0
                instance._auth_revoked_callback = None
                instance._auth_recovered_callback = None
                instance._last_heartbeat_time = 0
                instance._state_lock = threading.Lock()
                instance._server_invalid = False
                # 首次创建时，从旧版JSON文件迁移数据到SQLite
                try:
                    _db_migrate_from_json()
                except Exception:
                    pass
                cls._instance = instance
            return cls._instance

    # ============ Token 管理 ============

    def _get_token(self) -> Optional[str]:
        """获取当前JWT Token"""
        return self._token

    def _set_token(self, token: str):
        """设置JWT Token"""
        self._token = token

    # ============ 登录/注册/激活 ============

    def login_user(self, username: str, password: str) -> Tuple[bool, str]:
        """用户登录

        Args:
            username: 用户名
            password: 密码

        Returns:
            (success, message) 元组
        """
        try:
            api_url = get_api_base_url()
            if not api_url:
                return False, "未配置API服务器地址"

            fingerprint = self._get_machine_fingerprint()

            response = get_http_session().post(
                f"{api_url}/api/auth/login",
                json={
                    "username": username,
                    "password": password,
                    "fingerprint": fingerprint,
                },
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                license_info = data.get("license")

                if token and license_info:
                    self._set_token(token)
                    self._save_license_cache(license_info)
                    self.license_data = license_info
                    self._server_invalid = False
                    self._heartbeat_failures = 0
                    return True, "登录成功"
                elif token and not license_info:
                    # 有token但无许可证，清理token避免后续请求使用无效状态
                    self._set_token(None)
                    return False, "账号无有效授权，请联系管理员"
                else:
                    return False, "登录响应异常，请重试"
            elif response.status_code == 401:
                return False, "用户名或密码错误"
            elif response.status_code == 403:
                return False, "账户已被禁用"
            elif response.status_code == 429:
                return False, "请求过于频繁，请稍后再试"
            else:
                try:
                    detail = response.json().get("detail", f"服务器错误({response.status_code})")
                except Exception:
                    detail = f"服务器错误({response.status_code})"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"登录失败: {str(e)}"

    def register_user(self, username: str, email: str, password: str) -> Tuple[bool, str]:
        """用户注册

        Args:
            username: 用户名
            email: 邮箱
            password: 密码

        Returns:
            (success, message) 元组
        """
        try:
            api_url = get_api_base_url()
            if not api_url:
                return False, "未配置API服务器地址"

            fingerprint = self._get_machine_fingerprint()

            response = get_http_session().post(
                f"{api_url}/api/auth/register",
                json={
                    "username": username,
                    "email": email,
                    "password": password,
                    "fingerprint": fingerprint,
                },
                timeout=15,
            )

            if response.status_code == 200:
                # 注册成功后自动登录
                success, message = self.login_user(username, password)
                if success:
                    return True, "注册成功"
                else:
                    # 注册成功但自动登录失败，仍然返回成功但提示用户手动登录
                    return True, "注册成功，请手动登录"
            elif response.status_code == 409:
                return False, "用户名或邮箱已存在"
            elif response.status_code == 429:
                return False, "请求过于频繁，请稍后再试"
            else:
                try:
                    detail = response.json().get("detail", f"注册失败({response.status_code})")
                except Exception:
                    detail = f"注册失败({response.status_code})"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"注册失败: {str(e)}"

    def activate_pro_license(self, license_key: str) -> Tuple[bool, str]:
        """使用激活码激活专业版

        Args:
            license_key: 激活码

        Returns:
            (success, message) 元组
        """
        try:
            api_url = get_api_base_url()
            token = self._get_token()
            if not token:
                return False, "请先登录"

            response = get_http_session().post(
                f"{api_url}/api/license/activate",
                json={"license_key": license_key},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                license_info = data.get("license")
                if license_info:
                    is_valid = license_info.get("is_valid", False)
                    if is_valid:
                        self._save_license_cache(license_info)
                        self.license_data = license_info
                        self._server_invalid = False
                        return True, "激活成功"
                    else:
                        self.license_data = license_info
                        self._server_invalid = True
                        return False, "激活码已使用或已失效"
                else:
                    return False, "激活响应异常，请联系客服"
            else:
                try:
                    detail = response.json().get("detail", "激活失败")
                except Exception:
                    detail = "激活失败"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"激活失败: {str(e)}"

    def purchase_subscription(self, plan_type: str, payment_method: str) -> Tuple[bool, Any]:
        """创建支付订单

        Args:
            plan_type: 套餐类型 (monthly/quarterly/yearly/lifetime)
            payment_method: 支付方式 (alipay/wechat)

        Returns:
            (success, result) 元组，成功时result为订单信息dict
        """
        try:
            api_url = get_api_base_url()
            token = self._get_token()
            if not token:
                return False, "请先登录"

            response = get_http_session().post(
                f"{api_url}/api/payment/create-order",
                json={"plan_type": plan_type, "payment_method": payment_method},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                try:
                    detail = response.json().get("detail", "创建订单失败")
                except Exception:
                    detail = "创建订单失败"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"创建订单失败: {str(e)}"

    def request_password_reset(self, email: str) -> Tuple[bool, str]:
        """请求密码重置验证码

        Args:
            email: 注册邮箱

        Returns:
            (success, message) 元组
        """
        try:
            api_url = get_api_base_url()
            if not api_url:
                return False, "未配置API服务器地址"

            response = get_http_session().post(
                f"{api_url}/api/auth/request-reset",
                json={"email": email},
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "验证码已发送")
            else:
                try:
                    detail = response.json().get("detail", "请求失败")
                except Exception:
                    detail = "请求失败"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"请求失败: {str(e)}"

    def confirm_password_reset(self, email: str, code: str, new_password: str) -> Tuple[bool, str]:
        """确认密码重置

        Args:
            email: 注册邮箱
            code: 验证码
            new_password: 新密码

        Returns:
            (success, message) 元组
        """
        try:
            api_url = get_api_base_url()
            if not api_url:
                return False, "未配置API服务器地址"

            response = get_http_session().post(
                f"{api_url}/api/auth/confirm-reset",
                json={"email": email, "code": code, "new_password": new_password},
                timeout=15,
            )

            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "密码重置成功")
            else:
                try:
                    detail = response.json().get("detail", "重置失败")
                except Exception:
                    detail = "重置失败"
                return False, detail

        except Exception as e:
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                return False, "无法连接到服务器，请检查网络"
            return False, f"重置失败: {str(e)}"

    # ============ 许可证状态检查 ============

    def check_license(self) -> Dict[str, Any]:
        """检查本地许可证状态

        优先使用内存中的许可证数据，内存无数据时从缓存文件加载。
        验证签名和离线容忍时间。

        Returns:
            {"valid": bool, "message": str, ...} 字典
        """
        # 仅在内存中无许可证数据时才从缓存文件加载
        if not self.license_data:
            cached = self._load_license_cache()
            if cached:
                self.license_data = cached

        if not self.license_data:
            return {"valid": False, "message": "未登录"}

        # 服务端已明确标记无效（如管理员禁用），优先于本地缓存判断
        if self._server_invalid:
            return {"valid": False, "message": "授权已失效"}

        # 验证签名
        if not self._verify_license_signature(self.license_data):
            return {"valid": False, "message": "许可证签名验证失败"}

        # 检查 is_valid 字段
        if not self.license_data.get("is_valid", False):
            return {"valid": False, "message": "许可证已失效"}

        # 检查离线容忍时间
        offline_until = self.license_data.get("offline_until")
        if offline_until:
            try:
                offline_dt = datetime.fromisoformat(offline_until.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now > offline_dt:
                    return {"valid": False, "message": "离线时间超限，请联网验证"}
            except (ValueError, TypeError):
                pass

        # 检查过期时间
        expiry = self.license_data.get("expiry_date")
        if expiry:
            try:
                expiry_dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                if now > expiry_dt:
                    return {"valid": False, "message": "许可证已过期"}
            except (ValueError, TypeError):
                pass

        days_left = self.license_data.get("days_left", -1)
        return {
            "valid": True,
            "message": "许可证有效",
            "days_left": days_left,
            "license_type": self.license_data.get("license_type"),
            "plan_type": self.license_data.get("plan_type"),
            "is_lifetime": self.license_data.get("is_lifetime", False),
            "is_trial": self.license_data.get("is_trial", False),
            "username": self.license_data.get("username", ""),
            "membership_type_name": self.license_data.get("membership_type_name", ""),
        }

    def verify_with_server(self) -> bool:
        """向服务器验证许可证状态

        同时检查设备绑定限制，确保当前设备可以使用。

        Returns:
            True 如果服务器确认许可证有效且设备绑定正常
        """
        try:
            api_url = get_api_base_url()
            token = self._get_token()
            if not token or not api_url:
                return False

            # 先通过license_status获取最新许可证数据（含设备绑定检查）
            fingerprint = self._get_machine_fingerprint()
            url = f"{api_url}/api/user/license_status"
            if fingerprint:
                url += f"?fingerprint={fingerprint}"
            response = get_http_session().get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                license_info = data.get("license")
                if license_info:
                    is_valid = license_info.get("is_valid", False)
                    if is_valid:
                        # 仅缓存有效的许可证数据
                        self._save_license_cache(license_info)
                        self.license_data = license_info
                        self._server_invalid = False
                    else:
                        # 无效许可证：更新内存但不缓存到文件
                        self.license_data = license_info
                        self._server_invalid = True
                    return is_valid
                # 服务端返回200但无license数据，说明用户无有效授权
                self._server_invalid = True
                return False
            elif response.status_code == 401:
                # Token 过期，尝试续期
                renewed = self._renew_token()
                if renewed:
                    return self.verify_with_server()
                return False
            elif response.status_code == 403:
                # 账户被禁用
                self._server_invalid = True
                return False
            return False

        except Exception:
            # 网络异常时，依赖本地缓存和离线容忍
            return self.check_license()["valid"]

    def refresh_license(self) -> bool:
        """刷新许可证状态（支付成功后调用）

        Returns:
            True 如果刷新成功且许可证有效
        """
        ok = self.verify_with_server()
        if ok:
            self._server_invalid = False
        return ok

    # ============ 心跳检测 ============

    def start_heartbeat(self):
        """启动心跳检测线程"""
        with self._state_lock:
            if self._heartbeat_running:
                # 心跳线程已在运行，仅重置失败计数器
                self._heartbeat_failures = 0
                return
            self._heartbeat_running = True
            self._heartbeat_failures = 0

        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """停止心跳检测"""
        with self._state_lock:
            self._heartbeat_running = False

    def _heartbeat_loop(self):
        """心跳循环"""
        while self._heartbeat_running:
            try:
                interval = _HEARTBEAT_INTERVAL
                if self._heartbeat_failures > 0:
                    interval = _HEARTBEAT_RETRY_INTERVAL

                # 等待间隔
                waited = 0
                while waited < interval and self._heartbeat_running:
                    time.sleep(1)
                    waited += 1

                if not self._heartbeat_running:
                    break

                success = self._send_heartbeat()
                if success:
                    self._heartbeat_failures = 0
                    self._last_heartbeat_time = time.time()
                else:
                    self._heartbeat_failures += 1
                    if self._heartbeat_failures >= _MAX_HEARTBEAT_FAILURES:
                        logger.warning("心跳连续失败%d次，标记授权失效", self._heartbeat_failures)
                        if self._auth_revoked_callback:
                            try:
                                self._auth_revoked_callback()
                            except Exception:
                                pass
                        # 重置计数器，避免每次心跳都重复触发回调
                        self._heartbeat_failures = 0

            except Exception as e:
                logger.error("心跳循环异常: %s", e)
                self._heartbeat_failures += 1

    def _send_heartbeat(self) -> bool:
        """发送心跳请求

        Returns:
            True 如果心跳成功
        """
        try:
            api_url = get_api_base_url()
            token = self._get_token()
            if not token or not api_url:
                return False

            fingerprint = self._get_machine_fingerprint()
            from .version import get_version
            app_version = get_version()

            response = get_http_session().post(
                f"{api_url}/api/user/heartbeat",
                json={
                    "fingerprint": fingerprint,
                    "app_version": app_version,
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                is_valid = data.get("is_valid", False)
                license_info = data.get("license")

                if is_valid and license_info:
                    # 仅当授权有效时才缓存许可证数据，避免缓存签名不一致的无效数据
                    self._save_license_cache(license_info)
                    self.license_data = license_info
                    self._server_invalid = False
                elif not is_valid:
                    # 授权无效，标记服务端无效状态
                    self._server_invalid = True
                    if license_info:
                        # 仍然更新内存中的license_data用于显示信息，但不缓存到文件
                        self.license_data = license_info

                if is_valid:
                    # 如果之前是失效状态，现在恢复了
                    if self._heartbeat_failures > 0 and self._auth_recovered_callback:
                        try:
                            self._auth_recovered_callback()
                        except Exception:
                            pass
                    return True
                else:
                    reason = data.get("reason", "授权已失效")
                    logger.warning("心跳返回授权无效: %s", reason)
                    # 服务端明确返回无效（非网络问题），立即触发授权失效回调
                    # 避免管理员禁用用户后客户端长时间不感知
                    immediate_revoke_reasons = ("账户已被禁用", "许可证已过期", "设备绑定数量已达上限")
                    if reason.startswith(immediate_revoke_reasons) and self._auth_revoked_callback:
                        try:
                            self._auth_revoked_callback()
                        except Exception:
                            pass
                        # 重置计数器，避免回调被重复触发
                        self._heartbeat_failures = 0
                    return False
            elif response.status_code == 401:
                # Token 过期，尝试续期
                renewed = self._renew_token()
                if renewed:
                    return self._send_heartbeat()
                return False
            elif response.status_code == 403:
                # 账户被禁用，立即标记授权失效并触发回调
                self._server_invalid = True
                logger.warning("心跳返回403，账户已被禁用")
                if self._auth_revoked_callback:
                    try:
                        self._auth_revoked_callback()
                    except Exception:
                        pass
                    self._heartbeat_failures = 0
                return False
            else:
                return False

        except Exception as e:
            logger.debug("心跳请求异常: %s", e)
            return False

    def _renew_token(self) -> bool:
        """续期JWT Token

        Returns:
            True 如果续期成功
        """
        try:
            api_url = get_api_base_url()
            token = self._get_token()
            if not token or not api_url:
                return False

            response = get_http_session().post(
                f"{api_url}/api/auth/token-renew",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                new_token = data.get("access_token")
                license_info = data.get("license")
                if new_token:
                    self._set_token(new_token)
                if license_info:
                    is_valid = license_info.get("is_valid", False)
                    if is_valid:
                        self._save_license_cache(license_info)
                        self.license_data = license_info
                        self._server_invalid = False
                    else:
                        self.license_data = license_info
                        self._server_invalid = True
                return True
            return False

        except Exception:
            return False

    # ============ 静默重登录 ============

    def _try_silent_relogin(self) -> bool:
        """尝试使用保存的凭证静默重登录

        Returns:
            True 如果重登录成功
        """
        try:
            username, password, save_user, save_pass = self.load_login_credentials()
            if username and password:
                success, _ = self.login_user(username, password)
                return success
        except Exception:
            pass
        return False

    # ============ 凭证持久化 ============

    def save_login_credentials(self, username: str, password: str, save_user: bool, save_pass: bool):
        """保存登录凭证到本地（密码混淆存储，SQLite数据库）

        Args:
            username: 用户名
            password: 密码
            save_user: 是否保存用户名
            save_pass: 是否保存密码
        """
        try:
            from .crypto_utils import obfuscate_string
            _db_save_credentials(
                username=username if save_user else "",
                password=obfuscate_string(password) if (save_pass and password) else "",
                save_user=save_user,
                save_pass=save_pass,
            )
        except Exception as e:
            logger.debug("保存凭证失败: %s", e)

    def load_login_credentials(self) -> Tuple[str, str, bool, bool]:
        """加载保存的登录凭证（密码反混淆）

        Returns:
            (username, password, save_user, save_pass) 元组
        """
        try:
            from .crypto_utils import deobfuscate_string
            username, password, save_user, save_pass = _db_load_credentials()
            # 兼容旧版明文密码：尝试反混淆，如果失败则使用原始值
            if password:
                try:
                    decoded = deobfuscate_string(password)
                    if decoded:
                        password = decoded
                except Exception:
                    pass
            return username, password, save_user, save_pass
        except Exception:
            pass
        return "", "", False, False

    def clear_login_credentials(self):
        """清除保存的登录凭证"""
        try:
            _db_clear_credentials()
        except Exception:
            pass

    # ============ 许可证缓存 ============

    def _save_license_cache(self, license_data: dict):
        """保存许可证数据到本地缓存（SQLite数据库）"""
        try:
            _db_save_license_cache(license_data)
        except Exception as e:
            logger.debug("保存许可证缓存失败: %s", e)

    def _load_license_cache(self) -> Optional[dict]:
        """从本地缓存加载许可证数据"""
        try:
            return _db_load_license_cache()
        except Exception:
            pass
        return None

    # ============ 签名验证 ============

    def _verify_license_signature(self, data: dict) -> bool:
        """验证许可证数据的签名

        Args:
            data: 许可证数据字典，包含 _sig 和 _sig_ver 字段

        Returns:
            True 如果签名验证通过
        """
        sig = data.get("_sig") or data.get("sig")
        sig_ver = data.get("_sig_ver") or data.get("sig_ver", 1)

        if not sig:
            return False

        try:
            # 构建待验证的payload（排除签名字段）
            check = {
                k: v for k, v in data.items()
                if k not in ("_sig", "sig", "_sig_ver", "sig_ver") and v is not None
            }
            payload = json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

            if sig_ver == 2:
                # ECDSA 签名验证
                pubkey_path = _get_verify_key_path()
                if not os.path.exists(pubkey_path):
                    # 也检查打包目录下的公钥
                    pubkey_path = os.path.join(_get_app_dir(), ".license_verify_pubkey.pem")
                if os.path.exists(pubkey_path):
                    from cryptography.hazmat.primitives import serialization
                    from cryptography.hazmat.primitives.asymmetric import ec
                    from cryptography.hazmat.primitives import hashes
                    with open(pubkey_path, "rb") as f:
                        public_key = serialization.load_pem_public_key(f.read())
                    public_key.verify(bytes.fromhex(sig), payload, ec.ECDSA(hashes.SHA256()))
                    return True
                return False
            elif sig_ver == 1:
                # HMAC 签名验证
                verify_key_path = os.path.join(_get_app_dir(), ".license_verify_key")
                if os.path.exists(verify_key_path):
                    import hmac as _hmac
                    with open(verify_key_path, "rb") as f:
                        key = f.read().strip()
                    expected = _hmac.new(key, payload, hashlib.sha256).hexdigest()
                    return _hmac.compare_digest(expected, sig)
                return False
        except Exception as e:
            logger.debug("签名验证异常: %s", e)

        return False

    # ============ 机器指纹 ============

    def _get_machine_fingerprint(self) -> str:
        """获取机器指纹

        Returns:
            机器指纹字符串
        """
        try:
            from .auth_fingerprint import generate_fingerprint
            return generate_fingerprint()
        except ImportError:
            pass

        # 降级方案：使用基本硬件信息生成指纹
        try:
            import platform
            info = f"{platform.node()}-{platform.machine()}-{platform.processor()}"
            return hashlib.sha256(info.encode("utf-8")).hexdigest()[:32]
        except Exception:
            return "unknown"

    # ============ 回调设置 ============

    def set_auth_revoked_callback(self, callback):
        """设置授权失效回调"""
        self._auth_revoked_callback = callback

    def set_auth_recovered_callback(self, callback):
        """设置授权恢复回调"""
        self._auth_recovered_callback = callback

    # ============ 信息查询 ============

    def get_account_info(self) -> Dict[str, Any]:
        """获取当前账户信息

        Returns:
            包含账户信息的字典，包括 username, membership_type_name,
            is_lifetime, is_trial, days_left, expires_at 等
        """
        info = {
            "username": "",
            "membership_type_name": "",
            "is_lifetime": False,
            "is_trial": False,
            "days_left": 0,
            "expires_at": "",
        }

        if self.license_data:
            info["username"] = self.license_data.get("username", "")
            info["membership_type_name"] = self.license_data.get("membership_type_name", "")
            info["is_lifetime"] = self.license_data.get("is_lifetime", False)
            info["is_trial"] = self.license_data.get("is_trial", False)
            info["expires_at"] = self.license_data.get("expires_at", "")

            # 优先使用后端返回的days_left（向上取整），避免本地计算不一致
            backend_days_left = self.license_data.get("days_left")
            if backend_days_left is not None and backend_days_left >= 0:
                info["days_left"] = backend_days_left
            else:
                # 降级：本地计算剩余天数
                expires_at = self.license_data.get("expires_at", "")
                if expires_at:
                    try:
                        from datetime import datetime
                        if isinstance(expires_at, str):
                            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        else:
                            exp_dt = expires_at
                        now = datetime.now(exp_dt.tzinfo) if hasattr(exp_dt, 'tzinfo') else datetime.now()
                        delta = exp_dt - now
                        info["days_left"] = max(0, delta.days + (1 if delta.seconds > 0 else 0))
                    except Exception:
                        pass

        return info

    def get_membership_display(self) -> str:
        """获取会员类型的显示文本

        Returns:
            会员类型显示字符串，如 "终身会员", "专业版(剩余30天)", "试用版" 等
        """
        info = self.get_account_info()
        if info["is_lifetime"]:
            return "终身会员"
        if info["is_trial"]:
            days = info["days_left"]
            return f"试用版(剩余{days}天)" if days > 0 else "试用版(已过期)"
        days = info["days_left"]
        name = info["membership_type_name"] or "会员"
        if days > 0:
            return f"{name}(剩余{days}天)"
        return f"{name}(已过期)"
