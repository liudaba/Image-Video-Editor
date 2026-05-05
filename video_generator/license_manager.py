# -*- coding: utf-8 -*-
"""
短视频生成器 - 授权和试用管理系统
功能:
1. 用户注册/登录
2. 7天免费试用
3. 付费订阅验证
4. 离线授权支持
5. HMAC签名防篡改（签名由服务端生成，客户端只验证）
"""

import hashlib
import hmac
import json
import os
import sys
import tkinter as tk
import threading
import time
from datetime import datetime, timedelta
from tkinter import ttk, messagebox

from .config import get_http_session

_HMAC_KEY = "_sig"
_TRIAL_DAYS = 7
_GRACE_HOURS = 2
_HEARTBEAT_INTERVAL = 1800
_HEARTBEAT_JITTER = 300
_HEARTBEAT_MAX_CONSECUTIVE_FAILURES = 3

_HMAC_VERIFY_SECRET = None


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
    check = {k: v for k, v in data.items() if k != _HMAC_KEY}
    payload = json.dumps(check, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    computed = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, computed)


class LicenseManager:
    _instance = None
    API_BASE = "https://api.videogen.com"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.license_data = None
            cls._instance._heartbeat_thread = None
            cls._instance._heartbeat_stop = threading.Event()
            cls._instance._consecutive_failures = 0
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
            return hashlib.sha256(raw).hexdigest()
        except Exception:
            return "unknown"

    def start_heartbeat(self):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
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
        token = self.license_data.get("token", "")
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
                self._consecutive_failures = 0
                if not data.get("is_valid", False):
                    self.license_data["is_valid"] = False
                    self.save_license(self.license_data)
                else:
                    remote_license = data.get("license")
                    if remote_license:
                        remote_license["token"] = token
                        self.save_license(remote_license)
            elif response.status_code == 401:
                self._consecutive_failures += 1
                if self._consecutive_failures >= _HEARTBEAT_MAX_CONSECUTIVE_FAILURES:
                    self.license_data["is_valid"] = False
                    self.save_license(self.license_data)
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= _HEARTBEAT_MAX_CONSECUTIVE_FAILURES:
                self.license_data["is_valid"] = False
                self.save_license(self.license_data)

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
                if not _verify_signature(data):
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

    def get_license_path(self):
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, "license.json")

    def register_user(self, username, email, password):
        try:
            response = get_http_session().post(
                f"{self.API_BASE}/api/auth/register",
                json={"username": username, "email": email, "password": password},
                timeout=10,
            )
            if response.status_code == 200:
                return self.login_user(username, password)
            else:
                error_msg = response.json().get("detail", "注册失败")
                return False, error_msg
        except Exception:
            return False, "无法连接到服务器,请检查网络连接"

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
                if signed_license:
                    self.save_license(signed_license)
                else:
                    license_data = {
                        "username": username,
                        "token": data["access_token"],
                        "trial_start": datetime.now().isoformat(),
                        "trial_end": (datetime.now() + timedelta(days=_TRIAL_DAYS)).isoformat(),
                        "license_type": "trial",
                        "is_valid": True,
                        "days_left": _TRIAL_DAYS,
                    }
                    self.save_license(license_data)
                self.start_heartbeat()
                return True, f"登录成功!您有{_TRIAL_DAYS}天免费试用期"
            else:
                error_msg = response.json().get("detail", "登录失败")
                return False, error_msg
        except Exception:
            return False, "无法连接到服务器,请检查网络连接"

    def check_license(self):
        if not self.license_data:
            return {"valid": False, "message": "未登录,请先注册或登录"}

        has_signature = _HMAC_KEY in self.license_data
        if has_signature and not _verify_signature(self.license_data):
            return {"valid": False, "message": "授权数据已被篡改,请重新登录"}
        if not has_signature:
            return {"valid": False, "message": "授权数据缺少签名,请重新登录"}

        is_valid = self.license_data.get("is_valid", False)
        if not is_valid:
            return {"valid": False, "message": "授权已过期,请购买专业版继续使用"}

        license_type = self.license_data.get("license_type", "none")
        days_left = self.license_data.get("days_left", 0)

        if license_type == "trial":
            trial_end_str = self.license_data.get("trial_end")
            if trial_end_str:
                try:
                    trial_end = datetime.fromisoformat(trial_end_str)
                    now = datetime.now()
                    if now <= trial_end + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (trial_end - now).days)
                        return {
                            "valid": True,
                            "type": "trial",
                            "days_left": days_left,
                            "message": f"试用期剩余 {days_left} 天",
                        }
                except (ValueError, TypeError):
                    pass
            if days_left > 0:
                return {
                    "valid": True,
                    "type": "trial",
                    "days_left": days_left,
                    "message": f"试用期剩余 {days_left} 天",
                }
            return {"valid": False, "message": "试用期已结束,请购买专业版继续使用"}

        if license_type == "pro":
            expiry_str = self.license_data.get("expiry_date")
            if expiry_str:
                try:
                    expiry_date = datetime.fromisoformat(expiry_str)
                    now = datetime.now()
                    if now <= expiry_date + timedelta(hours=_GRACE_HOURS):
                        days_left = max(0, (expiry_date - now).days)
                        return {
                            "valid": True,
                            "type": "pro",
                            "days_left": days_left,
                            "message": f"专业版剩余 {days_left} 天",
                        }
                except (ValueError, TypeError):
                    pass
            if days_left > 0:
                return {
                    "valid": True,
                    "type": "pro",
                    "days_left": days_left,
                    "message": f"专业版剩余 {days_left} 天",
                }
            return {"valid": False, "message": "专业版已过期,请续费继续使用"}

        return {"valid": False, "message": "未知的授权类型,请重新登录"}

    def activate_pro_license(self, license_key):
        try:
            token = self.license_data.get("token", "") if self.license_data else ""
            response = get_http_session().post(
                f"{self.API_BASE}/api/license/activate",
                json={"license_key": license_key},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                signed_license = data.get("license", {})
                if signed_license:
                    signed_license["token"] = token
                    self.save_license(signed_license)
                else:
                    self.license_data.update({
                        "license_type": "pro",
                        "expiry_date": data["expiry_date"],
                        "license_key": license_key,
                        "is_valid": True,
                    })
                    self.save_license(self.license_data)
                return True, "专业版激活成功!"
            else:
                error_msg = response.json().get("detail", "激活失败")
                return False, error_msg
        except Exception:
            return False, "激活失败，请稍后重试"

    def purchase_subscription(self, plan_type, payment_method):
        try:
            token = self.license_data.get("token", "") if self.license_data else ""
            response = get_http_session().post(
                f"{self.API_BASE}/api/payment/create_order",
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

    def refresh_license(self):
        try:
            token = self.license_data.get("token", "") if self.license_data else ""
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
                if signed_license:
                    signed_license["token"] = token
                    self.save_license(signed_license)
                    return True
            return False
        except Exception:
            return False

    def logout(self):
        self.license_data = None
        license_file = self.get_license_path()
        if os.path.exists(license_file):
            try:
                os.remove(license_file)
            except Exception:
                pass


class LoginDialog(tk.Toplevel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "login"
        self.result = None
        self.title("用户登录")
        self.geometry("420x400")
        self.resizable(False, False)
        self.configure(bg="#f5f5f5")
        self.transient(parent)
        self.grab_set()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (420 // 2)
        y = (self.winfo_screenheight() // 2) - (400 // 2)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        main = ttk.Frame(self, padding=25)
        main.pack(fill=tk.BOTH, expand=True)

        title_lbl = ttk.Label(main, text="🎬 短视频生成器", font=("Microsoft YaHei", 18, "bold"), foreground="#2196F3")
        title_lbl.pack(pady=(0, 5))
        sub_lbl = ttk.Label(main, text="AI驱动的音频转视频工具", font=("Microsoft YaHei", 10), foreground="#666")
        sub_lbl.pack(pady=(0, 15))

        self.username_var = tk.StringVar()
        ttk.Label(main, text="用户名", font=("Microsoft YaHei", 10)).pack(anchor=tk.W)
        self.username_entry = ttk.Entry(main, textvariable=self.username_var, font=("Microsoft YaHei", 11))
        self.username_entry.pack(fill=tk.X, pady=(0, 8))

        self.email_var = tk.StringVar()
        ttk.Label(main, text="邮箱地址", font=("Microsoft YaHei", 10)).pack(anchor=tk.W)
        self.email_entry = ttk.Entry(main, textvariable=self.email_var, font=("Microsoft YaHei", 11))
        self.email_entry.pack(fill=tk.X, pady=(0, 8))
        self.email_entry.pack_forget()
        self._email_label = main.winfo_children()[-2]
        self._email_label.pack_forget()

        self.password_var = tk.StringVar()
        ttk.Label(main, text="密码", font=("Microsoft YaHei", 10)).pack(anchor=tk.W)
        self.password_entry = ttk.Entry(main, textvariable=self.password_var, font=("Microsoft YaHei", 11), show="*")
        self.password_entry.pack(fill=tk.X, pady=(0, 8))

        self.confirm_var = tk.StringVar()
        ttk.Label(main, text="确认密码", font=("Microsoft YaHei", 10)).pack(anchor=tk.W)
        self.confirm_entry = ttk.Entry(main, textvariable=self.confirm_var, font=("Microsoft YaHei", 11), show="*")
        self.confirm_entry.pack(fill=tk.X, pady=(0, 8))
        self.confirm_entry.pack_forget()
        self._confirm_label = main.winfo_children()[-2]
        self._confirm_label.pack_forget()

        self.action_btn = ttk.Button(main, text="登录", command=self._handle_action)
        self.action_btn.pack(fill=tk.X, pady=(5, 5))

        self.switch_btn = ttk.Button(main, text="还没有账号?立即注册", command=self._toggle_mode)
        self.switch_btn.pack(fill=tk.X, pady=(0, 5))

        trial_lbl = ttk.Label(main, text="✨ 注册即享7天免费试用!", font=("Microsoft YaHei", 9), foreground="#FF5722")
        trial_lbl.pack(pady=(5, 0))

    def _toggle_mode(self):
        self.mode = "register" if self.mode == "login" else "login"
        if self.mode == "register":
            self._email_label.pack(after=self.username_entry, anchor=tk.W)
            self.email_entry.pack(after=self._email_label, fill=tk.X, pady=(0, 8))
            self._confirm_label.pack(after=self.password_entry, anchor=tk.W)
            self.confirm_entry.pack(after=self._confirm_label, fill=tk.X, pady=(0, 8))
            self.action_btn.config(text="注册")
            self.switch_btn.config(text="已有账号?立即登录")
            self.title("用户注册")
        else:
            self.email_entry.pack_forget()
            self._email_label.pack_forget()
            self.confirm_entry.pack_forget()
            self._confirm_label.pack_forget()
            self.action_btn.config(text="登录")
            self.switch_btn.config(text="还没有账号?立即注册")
            self.title("用户登录")

    def _handle_action(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请填写用户名和密码", parent=self)
            return
        if self.mode == "login":
            success, message = LicenseManager().login_user(username, password)
        else:
            email = self.email_var.get().strip()
            confirm = self.confirm_var.get().strip()
            if not email:
                messagebox.showwarning("提示", "请填写邮箱", parent=self)
                return
            if password != confirm:
                messagebox.showwarning("提示", "两次密码不一致", parent=self)
                return
            success, message = LicenseManager().register_user(username, email, password)
        if success:
            messagebox.showinfo("成功", message, parent=self)
            self.result = True
            self.destroy()
        else:
            messagebox.showerror("错误", message)

    def _on_cancel(self):
        self.result = False
        self.destroy()


def check_and_show_login():
    license_mgr = LicenseManager()
    license_status = license_mgr.check_license()
    if not license_status["valid"]:
        dialog = LoginDialog()
        dialog.wait_window()
        if dialog.result:
            license_status = license_mgr.check_license()
            if license_status["valid"]:
                license_mgr.start_heartbeat()
            return license_status
        else:
            return {"valid": False, "message": "用户取消登录"}
    license_mgr.start_heartbeat()
    return license_status
