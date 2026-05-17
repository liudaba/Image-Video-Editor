# -*- coding: utf-8 -*-
"""授权核心逻辑模块（零UI依赖）

从 license_manager.py 拆分出的纯业务逻辑层：
- 授权验证、心跳、签名
- 弹性心跳（指数退避 + 分级离线容忍）
- 弹性机器指纹（评分制）
- 本地授权令牌（HMAC签名离线令牌）

所有UI相关代码已移至 auth_dialogs.py
"""

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import get_http_session, get_api_base_url
from .auth_fingerprint import (
    get_machine_fingerprint,
    get_fingerprint_components,
    verify_fingerprint,
)

_HMAC_KEY = "_sig"
_TRIAL_DAYS = 15
_GRACE_HOURS = 2

_HEARTBEAT_INTERVAL = 180
_HEARTBEAT_JITTER = 30
_HEARTBEAT_MAX_CONSECUTIVE_FAILURES = 5
_HEARTBEAT_BACKOFF_MAX_INTERVAL = 86400

_OFFLINE_TOLERANCE = {
    "trial": 4,
    "monthly": 24,
    "quarterly": 48,
    "annual": 72,
    "yearly": 72,
    "lifetime": 168,
    "pro": 72,
    "default": 4,
}

_HMAC_VERIFY_SECRET = None
_ECDSA_PUBLIC_KEY = None
_SIG_VERSION_KEY = "_sig_ver"
_last_known_time = time.time()

_CREDENTIALS_FILE = ".login_creds"


def _get_verify_secret():
    global _HMAC_VERIFY_SECRET
    if _HMAC_VERIFY_SECRET is not None:
        return _HMAC_VERIFY_SECRET
    try:
        base_dir = _get_data_dir()
        key_file = os.path.join(base_dir, ".license_verify_key")
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                _HMAC_VERIFY_SECRET = f.read().strip().encode("utf-8")
    except Exception:
        pass
    return _HMAC_VERIFY_SECRET


def _get_ecdsa_public_key():
    global _ECDSA_PUBLIC_KEY
    if _ECDSA_PUBLIC_KEY is not None:
        return _ECDSA_PUBLIC_KEY
    try:
        from cryptography.hazmat.primitives import serialization
        search_dirs = [_get_data_dir()]
        parent_dir = os.path.dirname(_get_data_dir())
        if parent_dir and parent_dir not in search_dirs:
            search_dirs.append(parent_dir)
        for search_dir in search_dirs:
            pubkey_file = os.path.join(search_dir, ".license_verify_pubkey.pem")
            if os.path.exists(pubkey_file):
                with open(pubkey_file, "rb") as f:
                    _ECDSA_PUBLIC_KEY = serialization.load_pem_public_key(f.read())
                break
    except Exception:
        pass
    return _ECDSA_PUBLIC_KEY


def _verify_signature(data: dict) -> bool:
    if _HMAC_KEY not in data:
        return False
    sig_ver = data.get(_SIG_VERSION_KEY, 1)
    check = {k: v for k, v in data.items() if k != _HMAC_KEY and k != _SIG_VERSION_KEY and v is not None}
    payload = json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if sig_ver == 2:
        pubkey = _get_ecdsa_public_key()
        if pubkey is None:
            return False
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives import hashes
            signature = bytes.fromhex(data[_HMAC_KEY])
            pubkey.verify(signature, payload.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
            return True
        except Exception:
            return False
    else:
        secret = _get_verify_secret()
        if not secret:
            return False
        computed = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(data[_HMAC_KEY], computed)


def _check_clock_rollback():
    global _last_known_time
    now = time.time()
    if now < _last_known_time - 300:
        return True
    _last_known_time = now
    return False


def _parse_iso_to_naive(iso_str):
    try:
        if isinstance(iso_str, str) and iso_str.endswith("Z"):
            iso_str = iso_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_data_dir():
    if getattr(sys, "frozen", False):
        internal_dir = os.path.join(os.path.dirname(sys.executable), "_internal")
        if os.path.isdir(internal_dir):
            return internal_dir
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _get_offline_tolerance_hours(license_type):
    return _OFFLINE_TOLERANCE.get(license_type, _OFFLINE_TOLERANCE["default"])


class LicenseManager:
    _instance = None
    _init_lock = threading.Lock()

    @property
    def API_BASE(self):
        return get_api_base_url()

    def __new__(cls):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.license_data = None
                cls._instance._heartbeat_thread = None
                cls._instance._heartbeat_stop = threading.Event()
                cls._instance._consecutive_failures = 0
                cls._instance._stopping = False
                cls._instance._current_heartbeat_interval = _HEARTBEAT_INTERVAL
                cls._instance._registered_components = None
                cls._instance._auth_revoked_callback = None
                cls._instance._auth_recovered_callback = None
                cls._instance._revoked_notified = False
                cls._instance.load_license()
        return cls._instance

    @staticmethod
    def get_machine_fingerprint():
        return get_machine_fingerprint()

    def _get_registered_components(self):
        if self._registered_components is not None:
            return self._registered_components
        if not self.license_data:
            return None
        stored = self.license_data.get("fingerprint_components")
        if stored and isinstance(stored, dict):
            self._registered_components = stored
            return stored
        return None

    def _save_registered_components(self, components):
        self._registered_components = components
        if self.license_data:
            self.license_data["fingerprint_components"] = components

    def _check_fingerprint_elastic(self):
        """弹性指纹检查：当指纹哈希变化时，用评分制判断是否同一台机器

        Returns:
            True 表示通过（同一台机器），False 表示需要重新绑定
        """
        registered = self._get_registered_components()
        if not registered:
            self._save_registered_components(get_fingerprint_components())
            return True

        current = get_fingerprint_components()
        result = verify_fingerprint(current, registered)

        if result["action"] == "pass":
            return True
        elif result["action"] == "auto_update":
            self._save_registered_components(current)
            return True
        elif result["action"] == "rebind":
            return False
        else:
            return False

    def verify_with_server(self):
        try:
            token = self._get_token()
            if not token:
                return False
            fingerprint = get_machine_fingerprint()
            response = get_http_session().post(
                f"{self.API_BASE}/api/user/heartbeat",
                json={
                    "fingerprint": fingerprint,
                    "app_version": self._get_app_version(),
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                if not data.get("is_valid", False):
                    signed_data = self.license_data.get("signed", self.license_data)
                    signed_data["is_valid"] = False
                    self._save_signed_license(
                        signed_data,
                        token=self._get_token(),
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                    )
                    return False
                remote_license = data.get("license")
                if remote_license and _verify_signature(remote_license):
                    self._save_signed_license(
                        remote_license,
                        token=self._get_token(),
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                    )
                if self._revoked_notified:
                    self._revoked_notified = False
                    if self._auth_recovered_callback:
                        try:
                            self._auth_recovered_callback()
                        except Exception:
                            pass
                return True
            elif response.status_code == 403:
                signed_data = self.license_data.get("signed", self.license_data)
                signed_data["is_valid"] = False
                self._save_signed_license(
                    signed_data,
                    token=self._get_token(),
                    last_heartbeat=datetime.now(timezone.utc).isoformat(),
                )
                if not self._revoked_notified:
                    self._revoked_notified = True
                return False
            elif response.status_code == 401:
                result = self._try_silent_relogin()
                if result and self._revoked_notified:
                    self._revoked_notified = False
                    if self._auth_recovered_callback:
                        try:
                            self._auth_recovered_callback()
                        except Exception:
                            pass
                return result
            if self.license_data:
                signed_data = self.license_data.get("signed", self.license_data)
                if not signed_data.get("is_valid", False):
                    return False
            return True
        except Exception:
            if self.license_data:
                signed_data = self.license_data.get("signed", self.license_data)
                if not signed_data.get("is_valid", False):
                    return False
                last_hb_str = self.license_data.get("last_heartbeat")
                if last_hb_str:
                    last_hb = _parse_iso_to_naive(last_hb_str)
                    if last_hb:
                        from datetime import timezone as _tz
                        now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                        offline_hours = (now_utc - last_hb).total_seconds() / 3600
                        license_type = signed_data.get("license_type", "trial")
                        tolerance = _get_offline_tolerance_hours(license_type)
                        if offline_hours > tolerance:
                            return False
            return True

    def start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._consecutive_failures = 0
        self._current_heartbeat_interval = _HEARTBEAT_INTERVAL
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        if not self._stopping:
            return
        self._heartbeat_stop.set()

    def set_auth_revoked_callback(self, callback):
        self._auth_revoked_callback = callback

    def set_auth_recovered_callback(self, callback):
        self._auth_recovered_callback = callback

    def _heartbeat_loop(self):
        import random

        first_check = True
        while not self._heartbeat_stop.is_set():
            if first_check:
                interval = 5
                first_check = False
            else:
                jitter = random.randint(-_HEARTBEAT_JITTER, _HEARTBEAT_JITTER)
                interval = self._current_heartbeat_interval + jitter
            if self._heartbeat_stop.wait(timeout=interval):
                break
            try:
                self._do_heartbeat()
            except Exception:
                pass

    def _do_heartbeat(self):
        if not self.license_data:
            return
        token = self._get_token()
        if not token:
            return
        try:
            fingerprint = get_machine_fingerprint()
            response = get_http_session().post(
                f"{self.API_BASE}/api/user/heartbeat",
                json={
                    "fingerprint": fingerprint,
                    "app_version": self._get_app_version(),
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                server_ts = data.get("timestamp")
                if server_ts and abs(time.time() - server_ts) > 300:
                    self._on_heartbeat_failure()
                    return
                self._consecutive_failures = 0
                self._current_heartbeat_interval = _HEARTBEAT_INTERVAL

                if not data.get("is_valid", False):
                    self.license_data["signed"]["is_valid"] = False
                    self._save_signed_license(
                        self.license_data["signed"],
                        token=self._get_token(),
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                    )
                    if not self._revoked_notified:
                        self._revoked_notified = True
                        if self._auth_revoked_callback:
                            try:
                                self._auth_revoked_callback()
                            except Exception:
                                pass
                else:
                    remote_license = data.get("license")
                    if remote_license:
                        if _verify_signature(remote_license):
                            self._save_signed_license(
                                remote_license,
                                token=self._get_token(),
                                last_heartbeat=datetime.now(timezone.utc).isoformat(),
                            )
                        else:
                            self._on_heartbeat_failure()
                    else:
                        self._save_signed_license(
                            self.license_data.get("signed", self.license_data),
                            token=self._get_token(),
                            last_heartbeat=datetime.now(timezone.utc).isoformat(),
                        )
                    if self._revoked_notified:
                        self._revoked_notified = False
                        if self._auth_recovered_callback:
                            try:
                                self._auth_recovered_callback()
                            except Exception:
                                pass
            elif response.status_code == 401:
                refreshed = self._try_silent_relogin()
                if refreshed:
                    if self._revoked_notified:
                        self._revoked_notified = False
                        if self._auth_recovered_callback:
                            try:
                                self._auth_recovered_callback()
                            except Exception:
                                pass
                else:
                    self._on_heartbeat_failure()
                    if not self._revoked_notified:
                        self._revoked_notified = True
                        if self._auth_revoked_callback:
                            try:
                                self._auth_revoked_callback()
                            except Exception:
                                pass
            elif response.status_code == 403:
                signed_data = self.license_data.get("signed", self.license_data)
                signed_data["is_valid"] = False
                self._save_signed_license(
                    signed_data,
                    token=self._get_token(),
                    last_heartbeat=datetime.now(timezone.utc).isoformat(),
                )
                if not self._revoked_notified:
                    self._revoked_notified = True
                    if self._auth_revoked_callback:
                        try:
                            self._auth_revoked_callback()
                        except Exception:
                            pass
        except (ConnectionError, TimeoutError, OSError):
            self._on_heartbeat_failure()
        except Exception:
            self._consecutive_failures += 1

    def _on_heartbeat_failure(self):
        self._consecutive_failures += 1
        backoff_factor = 2 ** min(self._consecutive_failures, 6)
        self._current_heartbeat_interval = min(
            _HEARTBEAT_INTERVAL * backoff_factor, _HEARTBEAT_BACKOFF_MAX_INTERVAL
        )

        if self._consecutive_failures >= _HEARTBEAT_MAX_CONSECUTIVE_FAILURES:
            if not self._check_fingerprint_elastic():
                signed_data = self.license_data.get("signed", self.license_data)
                signed_data["is_valid"] = False
                self._save_signed_license(
                    signed_data,
                    token=self._get_token(),
                )
                if not self._revoked_notified:
                    self._revoked_notified = True
                    if self._auth_revoked_callback:
                        try:
                            self._auth_revoked_callback()
                        except Exception:
                            pass
            else:
                self._consecutive_failures = max(0, self._consecutive_failures - 2)
                self._current_heartbeat_interval = _HEARTBEAT_INTERVAL

    def _try_silent_relogin(self):
        try:
            current_token = self._get_token()
            if current_token:
                response = get_http_session().post(
                    f"{self.API_BASE}/api/auth/token-renew",
                    headers={"Authorization": f"Bearer {current_token}"},
                    timeout=10,
                )
                if response.status_code == 403:
                    if self.license_data:
                        signed_data = self.license_data.get("signed", self.license_data)
                        signed_data["is_valid"] = False
                        self._save_signed_license(
                            signed_data,
                            token=self._get_token(),
                            last_heartbeat=datetime.now(timezone.utc).isoformat(),
                        )
                    if not self._revoked_notified:
                        self._revoked_notified = True
                    return False
                if response.status_code == 200:
                    data = response.json()
                    signed_license = data.get("license", {})
                    new_token = data.get("access_token", "")
                    if signed_license and _verify_signature(signed_license) and new_token:
                        self._save_signed_license(
                            signed_license,
                            token=new_token,
                            last_heartbeat=datetime.now(timezone.utc).isoformat(),
                        )
                        self._consecutive_failures = 0
                        self._current_heartbeat_interval = _HEARTBEAT_INTERVAL
                        return True
            username, password, save_user, save_pass = self.load_login_credentials()
            if not save_pass or not username or not password:
                return False
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                signed_license = data.get("license", {})
                new_token = data.get("access_token", "")
                if signed_license and _verify_signature(signed_license) and new_token:
                    self._save_signed_license(
                        signed_license,
                        token=new_token,
                        last_heartbeat=datetime.now(timezone.utc).isoformat(),
                    )
                    self._consecutive_failures = 0
                    self._current_heartbeat_interval = _HEARTBEAT_INTERVAL
                    return True
            return False
        except Exception:
            return False

    def _get_app_version(self):
        try:
            from .version import __version__
            return __version__
        except Exception:
            return "unknown"

    def load_license(self):
        try:
            license_file = self.get_license_path()
            if os.path.exists(license_file):
                with open(license_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                signed_part = data.get("signed", data)
                if not _verify_signature(signed_part):
                    self.license_data = None
                    return
                self.license_data = data
                if "fingerprint_components" in data:
                    self._registered_components = data["fingerprint_components"]
            else:
                self.license_data = None
        except Exception:
            self.license_data = None

    def save_license(self, license_data):
        try:
            license_file = self.get_license_path()
            os.makedirs(os.path.dirname(license_file), exist_ok=True)
            with open(license_file, "w", encoding="utf-8") as f:
                json.dump(license_data, f, indent=2, ensure_ascii=False)
            self.license_data = license_data
            return True
        except Exception:
            return False

    def _get_token(self):
        raw = self.license_data.get("token", "") if self.license_data else ""
        if not raw:
            return ""
        if raw.startswith("ENC:"):
            try:
                from .crypto_utils import decrypt_value

                base_dir = os.path.dirname(self.get_license_path())
                decrypted = decrypt_value(raw, base_dir)
                return decrypted if decrypted else raw
            except Exception:
                return raw
        return raw

    def _save_signed_license(self, signed_license, token=None, last_heartbeat=None, username=None):
        save_data = {"signed": signed_license}
        if last_heartbeat:
            save_data["last_heartbeat"] = last_heartbeat
        if token:
            try:
                from .crypto_utils import encrypt_value

                base_dir = os.path.dirname(self.get_license_path())
                encrypted_token = encrypt_value(token, base_dir)
                save_data["token"] = encrypted_token if encrypted_token else token
            except Exception:
                save_data["token"] = token
        if self._registered_components is not None:
            save_data["fingerprint_components"] = self._registered_components
        if username:
            save_data["username"] = username
        elif self.license_data and self.license_data.get("username"):
            save_data["username"] = self.license_data["username"]
        self.save_license(save_data)

    def get_license_path(self):
        base_dir = _get_base_dir()
        return os.path.join(base_dir, "license.json")

    def save_login_credentials(self, username, password, save_user, save_pass):
        try:
            base_dir = _get_base_dir()
            creds_path = os.path.join(base_dir, _CREDENTIALS_FILE)
            from .crypto_utils import encrypt_value

            data = {"save_user": save_user, "save_pass": save_pass}
            if save_user:
                data["username"] = username
            if save_pass and password:
                data["password"] = encrypt_value(password, base_dir)
            with open(creds_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def load_login_credentials(self):
        try:
            base_dir = _get_base_dir()
            creds_path = os.path.join(base_dir, _CREDENTIALS_FILE)
            if not os.path.exists(creds_path):
                return None, None, False, False
            with open(creds_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            save_user = data.get("save_user", False)
            save_pass = data.get("save_pass", False)
            username = data.get("username", "")
            password = ""
            if save_pass and data.get("password"):
                from .crypto_utils import decrypt_value

                password = decrypt_value(data["password"], base_dir) or ""
            return username, password, save_user, save_pass
        except Exception:
            return None, None, False, False

    def clear_login_credentials(self):
        try:
            base_dir = _get_base_dir()
            creds_path = os.path.join(base_dir, _CREDENTIALS_FILE)
            if os.path.exists(creds_path):
                os.remove(creds_path)
        except Exception:
            pass

    def register_user(self, username, email, password):
        try:
            api_url = self.API_BASE
            fingerprint = get_machine_fingerprint()
            components = get_fingerprint_components()
            payload = {
                "username": username,
                "email": email,
                "password": password,
            }
            if fingerprint:
                payload["fingerprint"] = fingerprint
            response = get_http_session().post(
                f"{api_url}/api/auth/register",
                json=payload,
                timeout=10,
            )
            if response.status_code == 200:
                self._save_registered_components(components)
                return self.login_user(username, password)
            else:
                error_msg = response.json().get("detail", "注册失败")
                return False, error_msg
        except Exception as e:
            return (
                False,
                f"无法连接服务器({type(e).__name__}: {e}), API:{self.API_BASE}",
            )

    def login_user(self, username, password):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/login",
                json={"username": username, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                signed_license = data.get("license", {})
                if signed_license and _verify_signature(signed_license):
                    components = get_fingerprint_components()
                    self._save_registered_components(components)
                    self._save_signed_license(
                        signed_license, token=data["access_token"],
                        username=username
                    )
                    self._revoked_notified = False
                else:
                    return False, "服务器返回的授权数据无效,请联系客服"
                self.start_heartbeat()
                license_type = signed_license.get("license_type", "trial")
                days_left = signed_license.get("days_left", 0)
                if license_type == "trial":
                    if days_left <= 0:
                        return (
                            True,
                            "登录成功!试用期已结束,请购买专业版继续使用",
                        )
                    elif days_left >= _TRIAL_DAYS:
                        return True, f"登录成功!您有{_TRIAL_DAYS}天免费试用期"
                    else:
                        return True, f"登录成功!试用期剩余{days_left}天"
                elif license_type == "pro":
                    if days_left < 0 or days_left >= 9999:
                        return True, "登录成功!专业版终身会员"
                    else:
                        return True, f"登录成功!专业版剩余{days_left}天"
                else:
                    return True, "登录成功!"
            else:
                error_msg = response.json().get("detail", "登录失败")
                return False, error_msg
        except Exception as e:
            return (
                False,
                f"无法连接服务器({type(e).__name__}: {e}), API:{self.API_BASE}",
            )

    def check_license(self):
        if not self.license_data:
            return {"valid": False, "message": "未登录,请先注册或登录"}

        signed_data = self.license_data.get("signed", self.license_data)

        is_valid = signed_data.get("is_valid", False)
        if not is_valid:
            return {"valid": False, "message": "授权已失效,请重新登录"}

        has_signature = _HMAC_KEY in signed_data
        if has_signature and not _verify_signature(signed_data):
            return {"valid": False, "message": "授权数据已被篡改,请重新登录"}
        if not has_signature:
            return {"valid": False, "message": "授权数据缺少签名,请重新登录"}

        if _check_clock_rollback():
            return {"valid": False, "message": "检测到系统时钟异常,请校正后重试"}

        if (
            not self._stopping
            and self.license_data
            and not (
                self._heartbeat_thread and self._heartbeat_thread.is_alive()
            )
        ):
            if not self._heartbeat_stop.is_set():
                self.start_heartbeat()

        last_heartbeat_str = (
            self.license_data.get("last_heartbeat") if self.license_data else None
        )
        if last_heartbeat_str:
            try:
                last_hb = _parse_iso_to_naive(last_heartbeat_str)
                if last_hb:
                    from datetime import timezone as _tz

                    now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                    if (
                        last_hb.tzinfo is None
                        and "+" not in last_heartbeat_str
                        and last_heartbeat_str.endswith("Z") is False
                    ):
                        now_for_compare = datetime.now().replace(tzinfo=None)
                    else:
                        now_for_compare = now_utc
                    offline_hours = (
                        now_for_compare - last_hb
                    ).total_seconds() / 3600

                    license_type = signed_data.get("license_type", "trial")
                    tolerance = _get_offline_tolerance_hours(license_type)

                    offline_until_str = signed_data.get("offline_until")
                    if offline_until_str:
                        offline_until = _parse_iso_to_naive(offline_until_str)
                        if offline_until:
                            from datetime import timezone as _tz

                            check_time = datetime.now(_tz.utc).replace(
                                tzinfo=None
                            )
                            if check_time > offline_until:
                                return {
                                    "valid": False,
                                    "message": f"离线授权已过期,请连接网络验证授权",
                                }
                        else:
                            if offline_hours > tolerance:
                                return {
                                    "valid": False,
                                    "message": f"已离线超过{tolerance}小时,请连接网络验证授权",
                                }
                    else:
                        if offline_hours > tolerance:
                            return {
                                "valid": False,
                                "message": f"已离线超过{tolerance}小时,请连接网络验证授权",
                            }
            except (ValueError, TypeError):
                pass

        license_type = signed_data.get("license_type", "none")
        days_left = signed_data.get("days_left", 0)
        from datetime import timezone as _tz
        now_utc = datetime.now(_tz.utc).replace(tzinfo=None)

        if license_type == "trial":
            trial_end_str = signed_data.get("trial_end")
            if trial_end_str:
                trial_end = _parse_iso_to_naive(trial_end_str)
                if trial_end:
                    if now_utc <= trial_end + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (trial_end - now_utc).days)
                        return {
                            "valid": True,
                            "type": "trial",
                            "days_left": days_left,
                            "message": f"试用期剩余 {days_left} 天",
                        }
                    else:
                        return {
                            "valid": False,
                            "message": "试用期已结束,请购买专业版继续使用",
                        }
            return {
                "valid": False,
                "message": "试用期已结束,请购买专业版继续使用",
            }

        if license_type == "pro":
            expiry_str = signed_data.get("expiry_date")
            if expiry_str:
                expiry_date = _parse_iso_to_naive(expiry_str)
                if expiry_date:
                    if now_utc <= expiry_date + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (expiry_date - now_utc).days)
                        return {
                            "valid": True,
                            "type": "pro",
                            "days_left": days_left,
                            "message": f"专业版剩余 {days_left} 天",
                        }
                    else:
                        return {"valid": False, "message": "专业版已过期,请续费继续使用"}
            if not expiry_str:
                return {
                    "valid": True,
                    "type": "pro",
                    "days_left": 9999,
                    "message": "终身会员",
                }
            return {"valid": False, "message": "授权已过期,请购买专业版继续使用"}

        return {"valid": False, "message": "未知的授权类型,请重新登录"}

    def activate_pro_license(self, license_key):
        try:
            token = self._get_token()
            response = get_http_session().post(
                f"{self.API_BASE}/api/license/activate",
                json={"license_key": license_key},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                signed_license = data.get("license", {})
                if signed_license and _verify_signature(signed_license):
                    self._save_signed_license(signed_license, token=token)
                    if not (self._heartbeat_thread and self._heartbeat_thread.is_alive()):
                        self.start_heartbeat()
                else:
                    return False, "激活响应数据无效,请联系客服"
                lic_type = signed_license.get("license_type", "pro")
                if lic_type == "trial":
                    return True, "试用版激活成功!"
                return True, "专业版激活成功!"
            else:
                error_msg = response.json().get("detail", "激活失败")
                return False, error_msg
        except Exception:
            return False, "激活失败，请稍后重试"

    def purchase_subscription(self, plan_type, payment_method):
        try:
            token = self._get_token()
            response = get_http_session().post(
                f"{self.API_BASE}/api/payment/create-order",
                json={"plan_type": plan_type, "payment_method": payment_method},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                return True, data
            else:
                return False, response.json().get("detail", "创建订单失败")
        except Exception:
            return False, "创建订单失败，请稍后重试"

    def check_payment_availability(self):
        try:
            response = get_http_session().get(
                f"{self.API_BASE}/api/payment/methods",
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                return data
            return {"methods": [], "any_online_available": False}
        except Exception:
            return {"methods": [], "any_online_available": False}

    def request_password_reset(self, email):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/request-reset",
                json={"email": email},
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                return True, data.get("message", "验证码已发送")
            else:
                error_msg = response.json().get("detail", "请求失败")
                return False, error_msg
        except Exception as e:
            return False, f"无法连接服务器({type(e).__name__})"

    def confirm_password_reset(self, email, code, new_password):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/confirm-reset",
                json={
                    "email": email,
                    "code": code,
                    "new_password": new_password,
                },
                timeout=15,
            )
            if response.status_code == 200:
                return True, "密码重置成功,请使用新密码登录"
            else:
                error_msg = response.json().get("detail", "重置失败")
                return False, error_msg
        except Exception as e:
            return False, f"无法连接服务器({type(e).__name__})"

    def refresh_license(self):
        try:
            token = self._get_token()
            if not token:
                return False
            response = get_http_session().get(
                f"{self.API_BASE}/api/user/license_status",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                signed_license = data.get("license", {})
                if signed_license and _verify_signature(signed_license):
                    self._save_signed_license(signed_license, token=token)
                    return True
            return False
        except Exception:
            return False

    def get_membership_display(self):
        if not self.license_data:
            return ""
        signed_data = self.license_data.get("signed", self.license_data)
        license_type = signed_data.get("license_type", "")
        if license_type == "pro" and not signed_data.get("expiry_date"):
            return "终身会员"
        from datetime import timezone as _tz

        now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
        if license_type == "trial":
            trial_end_str = signed_data.get("trial_end")
            if trial_end_str:
                trial_end = _parse_iso_to_naive(trial_end_str)
                if trial_end:
                    days_left = max(0, (trial_end - now_utc).days)
                    if days_left > 0:
                        return f"试用剩余{days_left}天"
                    return "试用已到期"
        expiry_str = signed_data.get("expiry_date")
        if expiry_str:
            expiry_date = _parse_iso_to_naive(expiry_str)
            if expiry_date:
                days_left = max(0, (expiry_date - now_utc).days)
                if license_type == "pro" and days_left > 3650:
                    return "终身会员"
                if days_left > 0:
                    return f"会员还剩{days_left}天到期"
                return "会员已到期"
        days_left = signed_data.get("days_left", 0)
        if license_type == "pro" and days_left > 3650:
            return "终身会员"
        if days_left > 0:
            return f"会员还剩{days_left}天到期"
        return ""

    def get_account_info(self):
        info = {
            "username": "",
            "membership_type_name": "",
            "days_left": 0,
            "is_lifetime": False,
            "is_trial": False,
            "is_valid": False,
        }
        if not self.license_data:
            return info
        signed_data = self.license_data.get("signed", self.license_data)
        info["is_valid"] = signed_data.get("is_valid", False)
        username = self.license_data.get("username", "")
        if not username:
            username = signed_data.get("username", "")
        if not username:
            try:
                saved_user, _, save_user, _ = self.load_login_credentials()
                if save_user and saved_user:
                    username = saved_user
            except Exception:
                pass
        info["username"] = username
        license_type = signed_data.get("license_type", "")
        if license_type == "trial":
            info["is_trial"] = True
            info["membership_type_name"] = "试用期"
            trial_end_str = signed_data.get("trial_end")
            if trial_end_str:
                trial_end = _parse_iso_to_naive(trial_end_str)
                if trial_end:
                    from datetime import timezone as _tz
                    now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                    info["days_left"] = max(0, (trial_end - now_utc).days)
            else:
                info["days_left"] = signed_data.get("days_left", 0)
            return info
        if signed_data.get("activation_code") or signed_data.get("license_key"):
            info["membership_type_name"] = "激活码会员"
            info["days_left"] = signed_data.get("days_left", 0)
            if info["days_left"] > 3650 or not signed_data.get("expiry_date"):
                info["is_lifetime"] = True
                info["membership_type_name"] = "终身会员"
            return info
        if license_type == "pro":
            plan_type = signed_data.get("plan_type", "")
            if plan_type:
                plan_map = {
                    "monthly": "月卡会员",
                    "quarterly": "季卡会员",
                    "yearly": "年卡会员",
                    "annual": "年卡会员",
                    "lifetime": "终身会员",
                }
                info["membership_type_name"] = plan_map.get(plan_type, "会员")
                if plan_type == "lifetime":
                    info["is_lifetime"] = True
            else:
                if not signed_data.get("expiry_date"):
                    info["is_lifetime"] = True
                    info["membership_type_name"] = "终身会员"
                else:
                    days_left = 0
                    expiry_str = signed_data.get("expiry_date")
                    if expiry_str:
                        expiry_date = _parse_iso_to_naive(expiry_str)
                        if expiry_date:
                            from datetime import timezone as _tz
                            now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                            days_left = max(0, (expiry_date - now_utc).days)
                    else:
                        days_left = signed_data.get("days_left", 0)
                    info["days_left"] = days_left
                    if days_left > 3650:
                        info["is_lifetime"] = True
                        info["membership_type_name"] = "终身会员"
                    else:
                        info["membership_type_name"] = "会员"
            if info["is_lifetime"]:
                info["days_left"] = 9999
            elif info["days_left"] == 0:
                info["days_left"] = signed_data.get("days_left", 0)
            return info
        return info

    def logout(self):
        self._stopping = True
        self.stop_heartbeat()
        self.license_data = None
        self._registered_components = None
        self.clear_login_credentials()
        license_file = self.get_license_path()
        if os.path.exists(license_file):
            try:
                os.remove(license_file)
            except Exception:
                pass
