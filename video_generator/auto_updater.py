"""
短视频生成器 - 自动更新系统 (Tkinter版本)
功能:
1. 检查最新版本
2. 显示更新通知
3. 下载更新包（含SHA256完整性校验）
4. 引导安装
"""

import hashlib
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .config import get_http_session, get_api_base_url

_ALLOWED_DOWNLOAD_HOSTS = {
    "api.videogen.com",
    "cdn.videogen.com",
    "releases.videogen.com",
}


class UpdateManager:
    _instance = None

    @property
    def UPDATE_API_URL(self):
        return f"{get_api_base_url()}/api/version/latest"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.version_info = None
            cls._instance.is_downloading = False
            from .version import get_version, compare_versions
            cls._instance.CURRENT_VERSION = get_version()
            cls._instance._compare_versions = compare_versions
        return cls._instance

    def _validate_download_url(self, url):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.hostname in _ALLOWED_DOWNLOAD_HOSTS
        except Exception:
            return False

    def check_for_updates(self, callback=None):
        def check_thread():
            try:
                headers = {}
                try:
                    from .license_manager import LicenseManager
                    token = LicenseManager()._get_token()
                    if token:
                        headers["Authorization"] = f"Bearer {token}"
                except Exception:
                    pass
                response = get_http_session().get(
                    self.UPDATE_API_URL,
                    params={"current_version": self.CURRENT_VERSION},
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()

                    if data.get('has_update'):
                        self.version_info = data

                        priority = data.get('priority', 'normal')
                        force_update = data.get('force_update', False)

                        if priority == 'critical' or force_update:
                            data['notification_type'] = 'forced_popup'
                        elif priority == 'high':
                            data['notification_type'] = 'popup'
                        elif priority == 'normal':
                            data['notification_type'] = 'log_only'
                        else:
                            data['notification_type'] = 'silent'

                        if callback:
                            callback(True, data)
                    else:
                        if callback:
                            callback(False, None)
                else:
                    if callback:
                        callback(None, f"服务器错误: {response.status_code}")

            except Exception as e:
                if callback:
                    callback(None, "检查超时或无法连接到更新服务器" if isinstance(e, (ConnectionError, TimeoutError, OSError)) else f"检查失败: {str(e)}")

        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()

    def download_update(self, download_url, save_path, expected_hash=None, progress_callback=None, complete_callback=None, error_callback=None):
        if not self._validate_download_url(download_url):
            if error_callback:
                error_callback("下载地址不合法，拒绝下载")
            return

        self.is_downloading = True
        self._cancel_requested = False

        def download_thread():
            try:
                response = get_http_session().get(download_url, stream=True, timeout=30)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0

                os.makedirs(os.path.dirname(save_path), exist_ok=True)

                hasher = hashlib.sha256()
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            if self._cancel_requested:
                                f.close()
                                if os.path.exists(save_path):
                                    os.remove(save_path)
                                if error_callback:
                                    error_callback("下载已取消")
                                self.is_downloading = False
                                return
                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)

                            if total_size > 0 and progress_callback:
                                percentage = int((downloaded / total_size) * 100)
                                progress_callback(downloaded, total_size, percentage)

                if expected_hash:
                    actual_hash = hasher.hexdigest()
                    if not hmac_compare_digest(actual_hash, expected_hash):
                        os.remove(save_path)
                        if error_callback:
                            error_callback("文件完整性校验失败，下载文件可能被篡改")
                        self.is_downloading = False
                        return

                self.is_downloading = False
                if complete_callback:
                    complete_callback(save_path)

            except Exception as e:
                self.is_downloading = False
                if os.path.exists(save_path):
                    try:
                        os.remove(save_path)
                    except Exception:
                        pass
                if error_callback:
                    error_callback(f"下载失败: {str(e)}")

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def cancel_download(self):
        self._cancel_requested = True

    @staticmethod
    def format_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"


def hmac_compare_digest(a, b):
    import hmac as _hmac
    if len(a) != len(b):
        return False
    return _hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


class UpdateDialog(tk.Toplevel):
    def __init__(self, parent, auto_check=False):
        super().__init__(parent)
        self.parent = parent
        self.auto_check = auto_check
        self.update_manager = UpdateManager()
        self.is_downloading = False

        self.title("检查更新")
        self.geometry("600x450")
        self.resizable(False, False)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (450 // 2)
        self.geometry(f"+{x}+{y}")

        self.init_ui()

        if auto_check:
            self.check_updates()

    def init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(
            main_frame,
            text="🔄 版本更新",
            font=("Microsoft YaHei", 16, "bold")
        )
        title_label.pack(pady=(0, 15))

        self.status_var = tk.StringVar(value="正在检查更新...")
        status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei", 11),
            foreground="#666"
        )
        status_label.pack(pady=(0, 10))

        changelog_frame = ttk.LabelFrame(main_frame, text="更新内容:", padding="10")
        changelog_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.changelog_text = tk.Text(
            changelog_frame,
            height=8,
            wrap=tk.WORD,
            font=("Microsoft YaHei", 10),
            state=tk.DISABLED
        )
        scrollbar = ttk.Scrollbar(changelog_frame, orient=tk.VERTICAL, command=self.changelog_text.yview)
        self.changelog_text.configure(yscrollcommand=scrollbar.set)

        self.changelog_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))

        self.progress_var = tk.StringVar(value="")
        progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_var,
            font=("Microsoft YaHei", 9),
            foreground="#666"
        )
        progress_label.pack()

        self.progress_bar.pack_forget()
        progress_label.pack_forget()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.check_btn = ttk.Button(btn_frame, text="检查更新", command=self.check_updates)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 5))

        close_btn = ttk.Button(btn_frame, text="关闭", command=self.destroy)
        close_btn.pack(side=tk.LEFT, padx=5)

        self.download_btn = ttk.Button(btn_frame, text="立即下载", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.download_btn.pack_forget()

        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.cancel_download)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn.pack_forget()

    def check_updates(self):
        self.status_var.set("正在检查更新...")
        self.update_changelog("")
        self.download_btn.pack_forget()
        self.check_btn.config(state=tk.DISABLED)

        def on_check_complete(has_update, result):
            if has_update is None:
                self.status_var.set(f"❌ {result}")
                self.check_btn.config(state=tk.NORMAL)
            elif has_update:
                self.show_update_available(result)
            else:
                self.status_var.set("✅ 您使用的是最新版本!")
                self.update_changelog("暂无更新内容")
                self.check_btn.config(state=tk.NORMAL)

        self.update_manager.check_for_updates(on_check_complete)

    def show_update_available(self, version_info):
        self.version_info = version_info

        self.status_var.set(
            f"✨ 发现新版本 v{version_info['version']}!\n"
            f"发布日期: {version_info['release_date']}"
        )

        changelog = "\n".join([f"• {item}" for item in version_info.get('changelog', [])])
        self.update_changelog(changelog)

        file_size = UpdateManager.format_size(version_info.get('file_size', 0))
        self.download_btn.config(text=f"下载更新 ({file_size})")
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.NORMAL)

        if version_info.get('force_update'):
            messagebox.showwarning(
                "重要更新",
                "此版本包含重要修复,建议您立即更新!"
            )

    def update_changelog(self, text):
        self.changelog_text.config(state=tk.NORMAL)
        self.changelog_text.delete(1.0, tk.END)
        self.changelog_text.insert(tk.END, text)
        self.changelog_text.config(state=tk.DISABLED)

    def start_download(self):
        if not hasattr(self, 'version_info'):
            return

        save_dir = os.path.join(os.getenv('TEMP', ''), 'VideoGen_Update')
        filename = f"VideoGen_v{self.version_info['version']}_Setup.exe"
        save_path = os.path.join(save_dir, filename)

        self.download_btn.pack_forget()
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.progress_bar['value'] = 0

        for widget in self.progress_bar.master.winfo_children():
            if isinstance(widget, ttk.Label):
                widget.pack()
                break

        self.is_downloading = True

        def on_progress(downloaded, total, percentage):
            self.progress_bar['value'] = percentage
            self.progress_var.set(
                f"下载中... {UpdateManager.format_size(downloaded)} / "
                f"{UpdateManager.format_size(total)} ({percentage}%)"
            )

        def on_complete(file_path):
            self.is_downloading = False
            self.progress_var.set("✅ 下载完成! 文件完整性校验通过!")
            self.cancel_btn.pack_forget()

            if messagebox.askyesno(
                "下载完成",
                f"更新包已下载到:\n{file_path}\n\n是否立即安装?"
            ):
                os.startfile(file_path)
                self.destroy()
            else:
                self.download_btn.pack(side=tk.LEFT, padx=5)

        def on_error(error_msg):
            self.is_downloading = False
            self.progress_var.set(f"❌ {error_msg}")
            self.cancel_btn.pack_forget()
            self.download_btn.pack(side=tk.LEFT, padx=5)
            self.check_btn.config(state=tk.NORMAL)
            messagebox.showerror("下载失败", error_msg)

        expected_hash = self.version_info.get('file_hash')

        self.update_manager.download_update(
            self.version_info['download_url'],
            save_path,
            expected_hash=expected_hash,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error
        )

    def cancel_download(self):
        if self.is_downloading:
            self.is_downloading = False
            self.update_manager.cancel_download()
            self.progress_var.set("已取消下载")
            self.cancel_btn.pack_forget()
            self.download_btn.pack(side=tk.LEFT, padx=5)
            self.check_btn.config(state=tk.NORMAL)


def check_and_notify_update(parent_window, auto_check=False, silent=False):
    if silent:
        update_mgr = UpdateManager()

        def on_check_complete(has_update, result):
            if has_update is True:
                if hasattr(parent_window, 'log'):
                    version = result.get('version', '未知')
                    parent_window.log(f"🔔 发现新版本 v{version}(后台检查)")

        update_mgr.check_for_updates(on_check_complete)
    else:
        dialog = UpdateDialog(parent_window, auto_check=auto_check)

        if not auto_check:
            dialog.wait_window()
