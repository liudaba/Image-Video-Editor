# -*- coding: utf-8 -*-
"""
短视频生成器 - 授权和试用管理系统
功能:
1. 用户注册/登录
2. 7天免费试用
3. 付费订阅验证
4. 离线授权支持
5. HMAC签名防篡改（签名由服务端生成，客户端只验证）
6. 心跳验证（30分钟间隔，3次连续失败吊销）
7. 时钟回拨检测
8. 记住登录凭据（加密存储）
9. 密码邮箱找回
10. 会员购买与激活
"""

import hashlib
import hmac
import json
import os
import re
import sys
import tkinter as tk
import threading
import time
from datetime import datetime, timedelta, timezone
from tkinter import ttk, messagebox

from .config import get_http_session, get_api_base_url

_HMAC_KEY = "_sig"
_TRIAL_DAYS = 7
_GRACE_HOURS = 2
_HEARTBEAT_INTERVAL = 1800
_HEARTBEAT_JITTER = 300
_HEARTBEAT_MAX_CONSECUTIVE_FAILURES = 3
_OFFLINE_TOLERANCE_HOURS = 48

_HMAC_VERIFY_SECRET = None
_last_known_time = time.time()

_CREDENTIALS_FILE = ".login_creds"


def _get_verify_secret():
    global _HMAC_VERIFY_SECRET
    if _HMAC_VERIFY_SECRET is not None:
        return _HMAC_VERIFY_SECRET
    try:
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        key_file = os.path.join(base_dir, ".license_verify_key")
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                _HMAC_VERIFY_SECRET = f.read().strip().encode("utf-8")
    except Exception:
        pass
    return _HMAC_VERIFY_SECRET


def _verify_signature(data: dict) -> bool:
    if _HMAC_KEY not in data:
        return False
    secret = _get_verify_secret()
    if not secret:
        return False
    expected = data[_HMAC_KEY]
    check = {k: v for k, v in data.items() if k != _HMAC_KEY and v is not None}
    payload = json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    computed = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, computed)


def _check_clock_rollback():
    global _last_known_time
    now = time.time()
    if now < _last_known_time - 300:
        return True
    _last_known_time = now
    return False


def _parse_iso_to_naive(iso_str):
    try:
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
                cls._instance.load_license()
        return cls._instance

    @staticmethod
    def get_machine_fingerprint():
        try:
            import getpass
            import platform
            user = getpass.getuser()
            machine = platform.node()
            raw = f"VideoGen::{user}@{machine}".encode("utf-8")
            base_hash = hashlib.sha256(raw).hexdigest()

            extra_parts = []
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                    guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                    extra_parts.append(guid)
            except Exception:
                pass

            try:
                import subprocess
                result = subprocess.run(
                    ["wmic", "diskdrive", "get", "serialnumber"],
                    capture_output=True, text=True, timeout=5
                )
                lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip() and "SerialNumber" not in l]
                if lines:
                    extra_parts.append(lines[0])
            except Exception:
                pass

            if extra_parts:
                combined = f"{base_hash}::{'::'.join(extra_parts)}".encode("utf-8")
                return hashlib.sha256(combined).hexdigest()
            return base_hash
        except Exception:
            return "unknown"

    def start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        if not self._stopping:
            return
        self._heartbeat_stop.set()

    def _heartbeat_loop(self):
        import random
        while not self._heartbeat_stop.is_set():
            interval = _HEARTBEAT_INTERVAL + random.randint(-_HEARTBEAT_JITTER, _HEARTBEAT_JITTER)
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
            fingerprint = self.get_machine_fingerprint()
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
                    self._consecutive_failures += 1
                    return
                self._consecutive_failures = 0
                if not data.get("is_valid", False):
                    self.license_data["signed"]["is_valid"] = False
                    self._save_signed_license(
                        self.license_data["signed"],
                        token=self._get_token(),
                        last_heartbeat=datetime.now().isoformat(),
                    )
                else:
                    remote_license = data.get("license")
                    if remote_license:
                        if _verify_signature(remote_license):
                            self._save_signed_license(
                                remote_license,
                                token=self._get_token(),
                                last_heartbeat=datetime.now().isoformat(),
                            )
                        else:
                            self._consecutive_failures += 1
                    else:
                        self._save_signed_license(
                            self.license_data.get("signed", self.license_data),
                            token=self._get_token(),
                            last_heartbeat=datetime.now().isoformat(),
                        )
            elif response.status_code == 401:
                self._consecutive_failures += 1
                if self._consecutive_failures >= _HEARTBEAT_MAX_CONSECUTIVE_FAILURES:
                    signed_data = self.license_data.get("signed", self.license_data)
                    signed_data["is_valid"] = False
                    self._save_signed_license(
                        signed_data,
                        token=self._get_token(),
                    )
        except (ConnectionError, TimeoutError, OSError):
            self._consecutive_failures += 1
            if self._consecutive_failures >= _HEARTBEAT_MAX_CONSECUTIVE_FAILURES:
                signed_data = self.license_data.get("signed", self.license_data)
                signed_data["is_valid"] = False
                self._save_signed_license(
                    signed_data,
                    token=self._get_token(),
                )
        except Exception:
            self._consecutive_failures += 1

    @staticmethod
    def _get_app_version():
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

    def _save_signed_license(self, signed_license, token=None, last_heartbeat=None):
        if last_heartbeat:
            signed_license["last_heartbeat"] = last_heartbeat
        save_data = {"signed": signed_license}
        if token:
            try:
                from .crypto_utils import encrypt_value
                base_dir = os.path.dirname(self.get_license_path())
                encrypted_token = encrypt_value(token, base_dir)
                save_data["token"] = encrypted_token if encrypted_token else token
            except Exception:
                save_data["token"] = token
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
            response = get_http_session().post(
                f"{api_url}/api/auth/register",
                json={"username": username, "email": email, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                return self.login_user(username, password)
            else:
                error_msg = response.json().get("detail", "注册失败")
                return False, error_msg
        except Exception as e:
            return False, f"无法连接服务器({type(e).__name__}: {e}), API:{self.API_BASE}"

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
                    self._save_signed_license(signed_license, token=data["access_token"])
                else:
                    return False, "服务器返回的授权数据无效,请联系客服"
                self.start_heartbeat()
                return True, f"登录成功!您有{_TRIAL_DAYS}天免费试用期"
            else:
                error_msg = response.json().get("detail", "登录失败")
                return False, error_msg
        except Exception as e:
            return False, f"无法连接服务器({type(e).__name__}: {e}), API:{self.API_BASE}"

    def check_license(self):
        if not self.license_data:
            return {"valid": False, "message": "未登录,请先注册或登录"}

        signed_data = self.license_data.get("signed", self.license_data)
        has_signature = _HMAC_KEY in signed_data
        if has_signature and not _verify_signature(signed_data):
            return {"valid": False, "message": "授权数据已被篡改,请重新登录"}
        if not has_signature:
            return {"valid": False, "message": "授权数据缺少签名,请重新登录"}

        if _check_clock_rollback():
            return {"valid": False, "message": "检测到系统时钟异常,请校正后重试"}

        if not self._stopping and self.license_data and not (self._heartbeat_thread and self._heartbeat_thread.is_alive()):
            if not self._heartbeat_stop.is_set():
                self.start_heartbeat()

        last_heartbeat_str = signed_data.get("last_heartbeat")
        if last_heartbeat_str:
            try:
                last_hb = _parse_iso_to_naive(last_heartbeat_str)
                if last_hb:
                    from datetime import timezone as _tz
                    now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                    offline_hours = (now_utc - last_hb).total_seconds() / 3600
                    if offline_hours > _OFFLINE_TOLERANCE_HOURS:
                        return {"valid": False, "message": f"已离线超过{_OFFLINE_TOLERANCE_HOURS}小时,请连接网络验证授权"}
            except (ValueError, TypeError):
                pass

        is_valid = signed_data.get("is_valid", False)
        if not is_valid:
            return {"valid": False, "message": "授权已过期,请购买专业版继续使用"}

        license_type = signed_data.get("license_type", "none")
        days_left = signed_data.get("days_left", 0)

        if license_type == "trial":
            trial_end_str = signed_data.get("trial_end")
            if trial_end_str:
                trial_end = _parse_iso_to_naive(trial_end_str)
                if trial_end:
                    from datetime import timezone as _tz
                    now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                    if now_utc <= trial_end + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (trial_end - now_utc).days)
                        return {
                            "valid": True,
                            "type": "trial",
                            "days_left": days_left,
                            "message": f"试用期剩余 {days_left} 天",
                        }
            return {"valid": False, "message": "试用期已结束,请购买专业版继续使用"}

        if license_type == "pro":
            expiry_str = signed_data.get("expiry_date")
            if expiry_str:
                expiry_date = _parse_iso_to_naive(expiry_str)
                if expiry_date:
                    from datetime import timezone as _tz
                    now_utc = datetime.now(_tz.utc).replace(tzinfo=None)
                    if now_utc <= expiry_date + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (expiry_date - now_utc).days)
                        return {
                            "valid": True,
                            "type": "pro",
                            "days_left": days_left,
                            "message": f"专业版剩余 {days_left} 天",
                        }
            return {"valid": True, "type": "pro", "days_left": 9999, "message": "终身会员"}

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
                else:
                    return False, "激活响应数据无效,请联系客服"
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

    def request_password_reset(self, email):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/request-reset",
                json={"email": email},
                timeout=15,
            )
            if response.status_code == 200:
                return True, "验证码已发送到您的邮箱"
            else:
                error_msg = response.json().get("detail", "请求失败")
                return False, error_msg
        except Exception as e:
            return False, f"无法连接服务器({type(e).__name__})"

    def confirm_password_reset(self, email, code, new_password):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/confirm-reset",
                json={"email": email, "code": code, "new_password": new_password},
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
        days_left = signed_data.get("days_left", 0)
        expiry_str = signed_data.get("expiry_date")
        if license_type == "pro" and not expiry_str:
            return "终身会员"
        if license_type == "pro" and days_left > 3650:
            return "终身会员"
        if days_left > 0:
            return f"会员还剩{days_left}天到期"
        return ""

    def logout(self):
        self._stopping = True
        self.stop_heartbeat()
        self.license_data = None
        self.clear_login_credentials()
        license_file = self.get_license_path()
        if os.path.exists(license_file):
            try:
                os.remove(license_file)
            except Exception:
                pass


class LoginDialog(tk.Toplevel):
    _BG = "#1e1e1e"
    _PANEL_BG = "#252526"
    _TEXT_FG = "#d4d4d4"
    _ACCENT = "#2196f3"
    _ACCENT_HOVER = "#1976d2"
    _INPUT_BG = "#3a3a3a"
    _INPUT_FG = "#ffffff"
    _INPUT_BORDER = "#5a5a5a"
    _INPUT_FOCUS = "#2196f3"
    _HINT_FG = "#888888"
    _WARN_FG = "#ff9800"
    _SUCCESS_FG = "#4caf50"
    _ERROR_FG = "#f44336"
    _BTN_SECONDARY = "#3c3f41"
    _BTN_PURCHASE = "#ff9800"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "login"
        self.result = None
        self.title("用户登录")
        self.geometry("520x720")
        self.minsize(480, 680)
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._setup_styles()
        self._build_ui()
        self._load_saved_credentials()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Destroy>", self._on_destroy)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        style.configure("Login.TFrame", background=self._BG)
        style.configure("Login.Card.TFrame", background=self._PANEL_BG)
        style.configure("Login.TLabel", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 13))
        style.configure("Login.Title.TLabel", background=self._BG, foreground=self._ACCENT, font=("Microsoft YaHei", 24, "bold"))
        style.configure("Login.Sub.TLabel", background=self._BG, foreground=self._HINT_FG, font=("Microsoft YaHei", 11))
        style.configure("Login.Hint.TLabel", background=self._BG, foreground=self._WARN_FG, font=("Microsoft YaHei", 11))
        style.configure("Login.Trial.TLabel", background=self._BG, foreground=self._WARN_FG, font=("Microsoft YaHei", 12, "bold"))
        style.configure("Login.Error.TLabel", background=self._BG, foreground=self._ERROR_FG, font=("Microsoft YaHei", 10))
        style.configure("Login.TCheckbutton", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 11))
        style.configure("Login.Card.TCheckbutton", background=self._PANEL_BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 11))
        style.configure("Login.TButton", font=("Microsoft YaHei", 12), padding=(10, 8))
        style.configure("Login.Primary.TButton", background=self._ACCENT, foreground="#ffffff", font=("Microsoft YaHei", 13, "bold"), padding=(14, 10))
        style.map("Login.Primary.TButton", background=[('active', self._ACCENT_HOVER), ('pressed', '#1565c0')])
        style.configure("Login.Link.TButton", background=self._BG, foreground=self._ACCENT, font=("Microsoft YaHei", 11), padding=(5, 5))
        style.map("Login.Link.TButton", foreground=[('active', '#64b5f6')])
        style.configure("Login.Purchase.TButton", background=self._BTN_PURCHASE, foreground="#ffffff", font=("Microsoft YaHei", 12, "bold"), padding=(10, 8))
        style.map("Login.Purchase.TButton", background=[('active', '#f57c00')])
        style.configure("Login.Secondary.TButton", background=self._BTN_SECONDARY, foreground="#ffffff", font=("Microsoft YaHei", 11), padding=(8, 7))
        style.map("Login.Secondary.TButton", background=[('active', '#505050')])

    def _make_entry(self, parent, variable, show=None, placeholder=""):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            font=("Microsoft YaHei", 14),
            bg=self._INPUT_BG,
            fg=self._INPUT_FG,
            insertbackground=self._INPUT_FG,
            insertwidth=2,
            relief=tk.SOLID,
            bd=1,
            show=show if show else "",
            highlightthickness=2,
            highlightcolor=self._INPUT_FOCUS,
            highlightbackground=self._INPUT_BORDER,
        )
        if placeholder:
            entry.insert(0, placeholder)
            entry.configure(fg=self._HINT_FG)
            entry.bind("<FocusIn>", self._clear_placeholder(entry, placeholder))
            entry.bind("<FocusOut>", self._restore_placeholder(entry, placeholder))
        return entry

    def _clear_placeholder(self, entry, placeholder):
        def handler(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.configure(fg=self._INPUT_FG)
        return handler

    def _restore_placeholder(self, entry, placeholder):
        def handler(event):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.configure(fg=self._HINT_FG)
        return handler

    def _build_ui(self):
        main = ttk.Frame(self, style="Login.TFrame", padding=(36, 18, 36, 12))
        main.pack(fill=tk.BOTH, expand=True)

        title_lbl = ttk.Label(main, text="🎬 短视频生成器", style="Login.Title.TLabel")
        title_lbl.pack(pady=(0, 2))
        sub_lbl = ttk.Label(main, text="AI驱动的音频转视频工具", style="Login.Sub.TLabel")
        sub_lbl.pack(pady=(0, 12))

        card = ttk.Frame(main, style="Login.Card.TFrame", padding=20)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.username_var = tk.StringVar()
        ttk.Label(card, text="用户名", style="Login.TLabel", background=self._PANEL_BG).pack(anchor=tk.W, pady=(0, 6))
        self.username_entry = self._make_entry(card, self.username_var)
        self.username_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self.email_var = tk.StringVar()
        self._email_label = ttk.Label(card, text="邮箱地址", style="Login.TLabel", background=self._PANEL_BG)
        self.email_entry = self._make_entry(card, self.email_var)
        self._email_widgets = [self._email_label, self.email_entry]

        self.password_var = tk.StringVar()
        ttk.Label(card, text="密码", style="Login.TLabel", background=self._PANEL_BG).pack(anchor=tk.W, pady=(0, 6))
        self.password_entry = self._make_entry(card, self.password_var, show="●")
        self.password_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self.confirm_var = tk.StringVar()
        self._confirm_label = ttk.Label(card, text="确认密码", style="Login.TLabel", background=self._PANEL_BG)
        self.confirm_entry = self._make_entry(card, self.confirm_var, show="●")
        self._confirm_widgets = [self._confirm_label, self.confirm_entry]

        self._save_user_var = tk.BooleanVar(value=False)
        self._save_pass_var = tk.BooleanVar(value=False)
        save_frame = ttk.Frame(card, style="Login.Card.TFrame")
        save_frame.pack(fill=tk.X, pady=(0, 8))
        self._save_user_check = ttk.Checkbutton(
            save_frame, text="保存登录名", variable=self._save_user_var,
            style="Login.Card.TCheckbutton",
        )
        self._save_user_check.configure(command=lambda: self._on_save_toggle())
        self._save_user_check.pack(side=tk.LEFT, padx=(0, 20))
        self._save_pass_check = ttk.Checkbutton(
            save_frame, text="保存密码", variable=self._save_pass_var,
            style="Login.Card.TCheckbutton",
        )
        self._save_pass_check.pack(side=tk.LEFT)
        self._save_frame = save_frame

        self._agree_var = tk.BooleanVar(value=False)
        self._agree_check = ttk.Checkbutton(
            card, text="我同意《隐私政策》和《服务条款》",
            variable=self._agree_var, style="Login.Card.TCheckbutton",
        )
        self._agree_widgets = [self._agree_check]

        self.action_btn = ttk.Button(card, text="登 录", command=self._handle_action, style="Login.Primary.TButton")
        self.action_btn.pack(fill=tk.X, pady=(6, 4))

        self.switch_btn = ttk.Button(card, text="还没有账号? 立即注册", command=self._toggle_mode, style="Login.Link.TButton")
        self.switch_btn.pack(fill=tk.X, pady=(0, 4))

        self.purchase_btn = ttk.Button(card, text="💎 购买会员", command=self._show_purchase_dialog, style="Login.Purchase.TButton")
        self.purchase_btn.pack(fill=tk.X, pady=(4, 4))

        self.reset_btn = ttk.Button(card, text="🔑 密码邮箱找回", command=self._show_reset_dialog, style="Login.Secondary.TButton")
        self.reset_btn.pack(fill=tk.X, pady=(0, 6))

        trial_lbl = ttk.Label(main, text="✨ 注册登录7天免费试用!", style="Login.Trial.TLabel")
        trial_lbl.pack(pady=(6, 0))

    def _on_save_toggle(self):
        if not self._save_user_var.get():
            self._save_pass_var.set(False)

    def _load_saved_credentials(self):
        try:
            mgr = LicenseManager()
            username, password, save_user, save_pass = mgr.load_login_credentials()
            if username:
                self.username_var.set(username)
            if save_user:
                self._save_user_var.set(True)
            if save_pass and password:
                self._save_pass_var.set(True)
                self.password_var.set(password)
        except Exception:
            pass

    def _toggle_mode(self):
        self.mode = "register" if self.mode == "login" else "login"
        if self.mode == "register":
            self._email_label.pack(after=self.username_entry, anchor=tk.W, pady=(0, 6))
            self.email_entry.pack(after=self._email_label, fill=tk.X, ipady=8, pady=(0, 14))
            self._confirm_label.pack(after=self.password_entry, anchor=tk.W, pady=(0, 6))
            self.confirm_entry.pack(after=self._confirm_label, fill=tk.X, ipady=8, pady=(0, 14))
            self._save_frame.pack_forget()
            self._agree_check.pack(after=self.confirm_entry, fill=tk.X, pady=(8, 4))
            self.action_btn.config(text="注 册")
            self.switch_btn.config(text="已有账号? 立即登录")
            self.purchase_btn.pack_forget()
            self.reset_btn.pack_forget()
            self.title("用户注册")
        else:
            for w in self._email_widgets:
                w.pack_forget()
            for w in self._confirm_widgets:
                w.pack_forget()
            for w in self._agree_widgets:
                w.pack_forget()
            self._save_frame.pack(fill=tk.X, pady=(0, 8))
            self.action_btn.config(text="登 录")
            self.switch_btn.config(text="还没有账号? 立即注册")
            self.purchase_btn.pack(fill=tk.X, pady=(4, 4))
            self.reset_btn.pack(fill=tk.X, pady=(0, 6))
            self.title("用户登录")

    def _handle_action(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请填写用户名和密码", parent=self)
            return
        if self.mode == "login":
            success, message = LicenseManager().login_user(username, password)
            if success:
                mgr = LicenseManager()
                mgr.save_login_credentials(
                    username, password,
                    self._save_user_var.get(),
                    self._save_pass_var.get(),
                )
        else:
            if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fa5]{3,50}$', username):
                messagebox.showwarning("提示", "用户名需3-50位，支持字母数字下划线和中文", parent=self)
                return
            email = self.email_var.get().strip()
            if not email:
                messagebox.showwarning("提示", "请填写邮箱", parent=self)
                return
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                messagebox.showwarning("提示", "请输入有效的邮箱地址", parent=self)
                return
            if len(password) < 8:
                messagebox.showwarning("提示", "密码至少8位", parent=self)
                return
            if not re.search(r'[A-Z]', password):
                messagebox.showwarning("提示", "密码必须包含至少一个大写字母", parent=self)
                return
            if not re.search(r'[a-z]', password):
                messagebox.showwarning("提示", "密码必须包含至少一个小写字母", parent=self)
                return
            if not re.search(r'\d', password):
                messagebox.showwarning("提示", "密码必须包含至少一个数字", parent=self)
                return
            confirm = self.confirm_var.get().strip()
            if password != confirm:
                messagebox.showwarning("提示", "两次密码不一致", parent=self)
                return
            if not self._agree_var.get():
                messagebox.showwarning("提示", "请先同意隐私政策和服务条款", parent=self)
                return
            success, message = LicenseManager().register_user(username, email, password)
        if success:
            messagebox.showinfo("成功", message, parent=self)
            self.result = True
            self.destroy()
        else:
            messagebox.showerror("错误", message, parent=self)

    def _show_reset_dialog(self):
        dialog = PasswordResetDialog(self)
        self.wait_window(dialog)

    def _show_purchase_dialog(self):
        dialog = PurchaseDialog(self)
        self.wait_window(dialog)

    def _on_cancel(self):
        self.result = False
        self.destroy()

    def _on_destroy(self, event):
        if event.widget is self and self.result is None:
            self.result = False


class PasswordResetDialog(tk.Toplevel):
    _BG = "#1e1e1e"
    _PANEL_BG = "#252526"
    _TEXT_FG = "#d4d4d4"
    _ACCENT = "#2196f3"
    _INPUT_BG = "#3a3a3a"
    _INPUT_FG = "#ffffff"
    _INPUT_BORDER = "#5a5a5a"
    _HINT_FG = "#888888"

    def __init__(self, parent):
        super().__init__(parent)
        self.title("密码邮箱找回")
        self.geometry("480x520")
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._setup_styles()
        self._build_ui()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Reset.TFrame", background=self._BG)
        style.configure("Reset.TLabel", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 12))
        style.configure("Reset.Title.TLabel", background=self._BG, foreground=self._ACCENT, font=("Microsoft YaHei", 16, "bold"))
        style.configure("Reset.Hint.TLabel", background=self._BG, foreground=self._HINT_FG, font=("Microsoft YaHei", 10))
        style.configure("Reset.TButton", font=("Microsoft YaHei", 11), padding=(8, 6))
        style.configure("Reset.Primary.TButton", background=self._ACCENT, foreground="#ffffff", font=("Microsoft YaHei", 12, "bold"), padding=(12, 8))
        style.configure("Reset.TCheckbutton", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 11))

    def _make_entry(self, parent, variable, show=None):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            font=("Microsoft YaHei", 14),
            bg=self._INPUT_BG,
            fg=self._INPUT_FG,
            insertbackground=self._INPUT_FG,
            insertwidth=2,
            relief=tk.SOLID,
            bd=1,
            show=show if show else "",
            highlightthickness=2,
            highlightcolor=self._ACCENT,
            highlightbackground=self._INPUT_BORDER,
        )
        return entry

    def _build_ui(self):
        main = ttk.Frame(self, style="Reset.TFrame", padding=(30, 20, 30, 15))
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="🔑 密码找回", style="Reset.Title.TLabel").pack(pady=(0, 4))
        ttk.Label(main, text="通过注册邮箱验证身份后重置密码", style="Reset.Hint.TLabel").pack(pady=(0, 14))

        self.email_var = tk.StringVar()
        ttk.Label(main, text="注册邮箱", style="Reset.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.email_entry = self._make_entry(main, self.email_var)
        self.email_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        btn_row = ttk.Frame(main, style="Reset.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 14))
        self.code_var = tk.StringVar()
        ttk.Label(btn_row, text="验证码", style="Reset.TLabel").pack(side=tk.LEFT)
        self.code_entry = self._make_entry(btn_row, self.code_var)
        self.code_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8), ipady=6)
        self.send_btn = ttk.Button(btn_row, text="发送验证码", command=self._send_code, style="Reset.TButton")
        self.send_btn.pack(side=tk.RIGHT)

        self.new_pass_var = tk.StringVar()
        ttk.Label(main, text="新密码", style="Reset.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.new_pass_entry = self._make_entry(main, self.new_pass_var, show="●")
        self.new_pass_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self.confirm_pass_var = tk.StringVar()
        ttk.Label(main, text="确认新密码", style="Reset.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.confirm_pass_entry = self._make_entry(main, self.confirm_pass_var, show="●")
        self.confirm_pass_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        ttk.Button(main, text="重置密码", command=self._do_reset, style="Reset.Primary.TButton").pack(fill=tk.X, pady=(0, 6))
        ttk.Button(main, text="取消", command=self.destroy, style="Reset.TButton").pack(fill=tk.X)

        self._code_sent = False
        self._countdown_id = None

    def _send_code(self):
        email = self.email_var.get().strip()
        if not email:
            messagebox.showwarning("提示", "请输入注册邮箱", parent=self)
            return
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            messagebox.showwarning("提示", "请输入有效的邮箱地址", parent=self)
            return
        success, message = LicenseManager().request_password_reset(email)
        if success:
            self._code_sent = True
            messagebox.showinfo("成功", message, parent=self)
            self._start_countdown(60)
        else:
            messagebox.showerror("错误", message, parent=self)

    def _start_countdown(self, seconds):
        if seconds <= 0:
            self.send_btn.config(text="发送验证码", state=tk.NORMAL)
            return
        self.send_btn.config(text=f"{seconds}s", state=tk.DISABLED)
        self._countdown_id = self.after(1000, lambda: self._start_countdown(seconds - 1))

    def _do_reset(self):
        email = self.email_var.get().strip()
        code = self.code_var.get().strip()
        new_pass = self.new_pass_var.get().strip()
        confirm_pass = self.confirm_pass_var.get().strip()

        if not email:
            messagebox.showwarning("提示", "请输入注册邮箱", parent=self)
            return
        if not code:
            messagebox.showwarning("提示", "请输入验证码", parent=self)
            return
        if len(new_pass) < 8:
            messagebox.showwarning("提示", "新密码至少8位", parent=self)
            return
        if not re.search(r'[A-Z]', new_pass):
            messagebox.showwarning("提示", "新密码必须包含至少一个大写字母", parent=self)
            return
        if not re.search(r'[a-z]', new_pass):
            messagebox.showwarning("提示", "新密码必须包含至少一个小写字母", parent=self)
            return
        if not re.search(r'\d', new_pass):
            messagebox.showwarning("提示", "新密码必须包含至少一个数字", parent=self)
            return
        if new_pass != confirm_pass:
            messagebox.showwarning("提示", "两次密码不一致", parent=self)
            return

        success, message = LicenseManager().confirm_password_reset(email, code, new_pass)
        if success:
            messagebox.showinfo("成功", message, parent=self)
            self.destroy()
        else:
            messagebox.showerror("错误", message, parent=self)

    def destroy(self):
        if self._countdown_id:
            self.after_cancel(self._countdown_id)
        super().destroy()


class PurchaseDialog(tk.Toplevel):
    _BG = "#1e1e1e"
    _PANEL_BG = "#252526"
    _TEXT_FG = "#d4d4d4"
    _ACCENT = "#2196f3"
    _INPUT_BG = "#3a3a3a"
    _INPUT_FG = "#ffffff"
    _INPUT_BORDER = "#5a5a5a"
    _HINT_FG = "#888888"
    _GOLD = "#ffc107"
    _SELECTED_BG = "#1a3a5c"

    PLANS = [
        {"key": "monthly", "name": "月卡", "price": "¥14.9/月", "desc": "30天专业版"},
        {"key": "quarterly", "name": "季卡", "price": "¥39.9/季", "desc": "90天专业版"},
        {"key": "yearly", "name": "年卡", "price": "¥129.9/年", "desc": "365天专业版"},
        {"key": "lifetime", "name": "终身会员", "price": "¥219.9", "desc": "永久专业版"},
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("购买会员")
        self.geometry("560x560")
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._selected_plan = None
        self._plan_cards = {}

        self._setup_styles()
        self._build_ui()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Purchase.TFrame", background=self._BG)
        style.configure("Purchase.TLabel", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 12))
        style.configure("Purchase.Title.TLabel", background=self._BG, foreground=self._GOLD, font=("Microsoft YaHei", 18, "bold"))
        style.configure("Purchase.TButton", font=("Microsoft YaHei", 11), padding=(8, 6))
        style.configure("Purchase.Primary.TButton", background=self._GOLD, foreground="#1e1e1e", font=("Microsoft YaHei", 12, "bold"), padding=(12, 8))
        style.configure("Purchase.TCheckbutton", background=self._BG, foreground=self._TEXT_FG, font=("Microsoft YaHei", 11))

    def _make_entry(self, parent, variable, show=None):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            font=("Microsoft YaHei", 14),
            bg=self._INPUT_BG,
            fg=self._INPUT_FG,
            insertbackground=self._INPUT_FG,
            insertwidth=2,
            relief=tk.SOLID,
            bd=1,
            show=show if show else "",
            highlightthickness=2,
            highlightcolor=self._ACCENT,
            highlightbackground=self._INPUT_BORDER,
        )
        return entry

    def _build_ui(self):
        main = ttk.Frame(self, style="Purchase.TFrame", padding=(30, 18, 30, 15))
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="💎 购买会员", style="Purchase.Title.TLabel").pack(pady=(0, 12))

        plans_frame = ttk.Frame(main, style="Purchase.TFrame")
        plans_frame.pack(fill=tk.X, pady=(0, 10))

        for i, plan in enumerate(self.PLANS):
            card = tk.Frame(
                plans_frame, bg=self._PANEL_BG, bd=1, relief=tk.RAISED,
                cursor="hand2", padx=8, pady=6,
            )
            card.grid(row=0, column=i, padx=4, pady=0, sticky="nsew")
            plans_frame.columnconfigure(i, weight=1)

            name_lbl = tk.Label(card, text=plan["name"], font=("Microsoft YaHei", 12, "bold"),
                                bg=self._PANEL_BG, fg=self._TEXT_FG)
            name_lbl.pack()
            price_lbl = tk.Label(card, text=plan["price"], font=("Microsoft YaHei", 14, "bold"),
                                 bg=self._PANEL_BG, fg=self._GOLD)
            price_lbl.pack(pady=(2, 0))
            desc_lbl = tk.Label(card, text=plan["desc"], font=("Microsoft YaHei", 10),
                                bg=self._PANEL_BG, fg=self._HINT_FG)
            desc_lbl.pack(pady=(0, 2))

            for widget in [card, name_lbl, price_lbl, desc_lbl]:
                widget.bind("<Button-1>", lambda e, k=plan["key"]: self._select_plan(k))

            self._plan_cards[plan["key"]] = card

        sep = ttk.Separator(main, orient="horizontal")
        sep.pack(fill=tk.X, pady=(10, 14))

        ttk.Label(main, text="激活码激活", style="Purchase.TLabel").pack(anchor=tk.W, pady=(0, 6))
        activate_frame = ttk.Frame(main, style="Purchase.TFrame")
        activate_frame.pack(fill=tk.X, pady=(0, 14))

        self.activate_var = tk.StringVar()
        self.activate_entry = self._make_entry(activate_frame, self.activate_var)
        self.activate_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(activate_frame, text="激活", command=self._do_activate, style="Purchase.TButton").pack(side=tk.RIGHT)

        sep2 = ttk.Separator(main, orient="horizontal")
        sep2.pack(fill=tk.X, pady=(6, 14))

        pay_label_frame = ttk.Frame(main, style="Purchase.TFrame")
        pay_label_frame.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(pay_label_frame, text="在线购买", style="Purchase.TLabel").pack(side=tk.LEFT)
        ttk.Label(pay_label_frame, text="请先选择套餐", style="Purchase.TLabel",
                  foreground=self._HINT_FG).pack(side=tk.RIGHT)
        self._pay_hint = pay_label_frame.winfo_children()[-1]

        pay_btn_frame = ttk.Frame(main, style="Purchase.TFrame")
        pay_btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(pay_btn_frame, text="支付宝支付", command=lambda: self._do_purchase("alipay"),
                    style="Purchase.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(pay_btn_frame, text="微信支付", command=lambda: self._do_purchase("wechat"),
                    style="Purchase.TButton").pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        ttk.Button(main, text="关闭", command=self.destroy, style="Purchase.TButton").pack(fill=tk.X, pady=(10, 0))

    def _select_plan(self, plan_key):
        self._selected_plan = plan_key
        for key, card in self._plan_cards.items():
            if key == plan_key:
                card.configure(bg=self._SELECTED_BG)
                for w in card.winfo_children():
                    w.configure(bg=self._SELECTED_BG)
            else:
                card.configure(bg=self._PANEL_BG)
                for w in card.winfo_children():
                    w.configure(bg=self._PANEL_BG)
        plan_name = next((p["name"] for p in self.PLANS if p["key"] == plan_key), "")
        self._pay_hint.configure(text=f"已选择: {plan_name}")

    def _do_activate(self):
        code = self.activate_var.get().strip()
        if not code:
            messagebox.showwarning("提示", "请输入正确的激活码", parent=self)
            return
        mgr = LicenseManager()
        success, message = mgr.activate_pro_license(code)
        if success:
            messagebox.showinfo("提示", "程序已激活", parent=self)
            self.destroy()
        else:
            messagebox.showerror("提示", "请输入正确的激活码", parent=self)

    def _do_purchase(self, payment_method):
        if not self._selected_plan:
            messagebox.showwarning("提示", "请先选择套餐", parent=self)
            return
        mgr = LicenseManager()
        success, result = mgr.purchase_subscription(self._selected_plan, payment_method)
        if success:
            order_id = result.get("order_id", "")
            qr_code = result.get("qr_code", "")
            msg = result.get("message", "")
            info = f"订单号: {order_id}\n"
            if msg:
                info += f"提示: {msg}\n"
            if qr_code:
                info += f"\n请使用{'支付宝' if payment_method == 'alipay' else '微信'}扫描以下二维码支付:\n{qr_code}"
            messagebox.showinfo("订单创建成功", info, parent=self)
        else:
            messagebox.showerror("错误", result if isinstance(result, str) else "创建订单失败", parent=self)


def check_and_show_login(parent=None):
    license_mgr = LicenseManager()
    license_status = license_mgr.check_license()
    if not license_status["valid"]:
        dialog = LoginDialog(parent)
        dialog.wait_window()
        if dialog.result:
            license_status = license_mgr.check_license()
            if license_status["valid"]:
                license_mgr.start_heartbeat()
            else:
                verify_secret = _get_verify_secret()
                if not verify_secret:
                    return {"valid": False, "message": "授权验证组件缺失(.license_verify_key)，请联系客服"}
            return license_status
        else:
            return {"valid": False, "message": "用户取消登录"}
    license_mgr.start_heartbeat()
    return license_status
