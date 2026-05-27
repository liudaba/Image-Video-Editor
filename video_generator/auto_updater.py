"""
短视频生成器 - 自动更新系统 (Tkinter版本)
功能:
1. 检查最新版本
2. 显示更新通知（支持强制更新/弹窗/静默三种模式）
3. 增量补丁更新：只下载变更文件，原子替换，无需安装程序
4. 全量更新：下载完整安装包（适用于大版本升级）
5. 下载更新包（含SHA256完整性校验 + 断点续传）
6. 更新完成后自动重启程序
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional
from urllib.parse import urlparse

from .config import get_http_session, get_api_base_url
from .crypto_utils import deobfuscate_string

logger = logging.getLogger("auto_updater")

# 应用根目录
if getattr(sys, "frozen", False):
    # PyInstaller打包模式：exe所在目录
    _ROOT_DIR = Path(sys.executable).resolve().parent
else:
    # 非打包模式：检测是否为便携版（内嵌Python）
    # 便携版特征：python/python.exe 在当前目录下，且 run.py 存在于上级目录
    _candidate = Path(__file__).resolve().parent.parent
    _exe_dir = Path(sys.executable).resolve().parent
    _exe_parent = _exe_dir.parent
    # 如果python.exe在"python/"子目录中，且上级目录有run.py，则是便携版
    if _exe_dir.name == "python" and (_exe_parent / "run.py").exists():
        _ROOT_DIR = _exe_parent
    else:
        _ROOT_DIR = _candidate

# 补丁下载缓存目录（不在temp中，避免断点续传文件被系统清理）
_temp_base = os.getenv('TEMP') or os.getenv('TMP') or os.path.join(os.path.expanduser('~'), '.cache')
_PATCH_CACHE_DIR = Path(_temp_base) / 'VideoGen_PatchCache'

_ALLOWED_DOWNLOAD_HOSTS = None


def _get_allowed_hosts():
    global _ALLOWED_DOWNLOAD_HOSTS
    if _ALLOWED_DOWNLOAD_HOSTS is not None:
        return _ALLOWED_DOWNLOAD_HOSTS
    _ALLOWED_DOWNLOAD_HOSTS = {
        deobfuscate_string("NzcMQDQTFxcOB1MBBQ5xLA0L"),  # api.wangzha178.com
        deobfuscate_string("ISYLCTkaGEFDVxxTXVs="),          # wangzha178.com
        deobfuscate_string("MS4RBjYQVxMbAg=="),                  # github.com
        deobfuscate_string("JCYSQCQbDRgBDUdDV0Q8IAwSEB0XTxcGAg=="),  # githubusercontent.com
    }
    _ALLOWED_DOWNLOAD_HOSTS.discard("")
    return _ALLOWED_DOWNLOAD_HOSTS


# ============================================================
#  数据类
# ============================================================

@dataclass
class PatchManifest:
    """增量补丁清单"""
    version: str = ''
    from_version: str = ''
    files: list = field(default_factory=list)
    release_notes: str = ''
    force_update: bool = False


@dataclass
class PatchFileEntry:
    """补丁中的单个文件条目"""
    path: str = ''
    sha256: str = ''
    size: int = 0


# ============================================================
#  工具函数
# ============================================================

def _show_windows_toast(parent_window, title, message):
    def _create_toast():
        try:
            toast = tk.Toplevel(parent_window)
            toast.overrideredirect(True)
            toast.attributes("-topmost", True)
            toast.geometry("320x80")
            toast.update_idletasks()
            x = toast.winfo_screenwidth() - 340
            y = toast.winfo_screenheight() - 120
            toast.geometry(f"+{x}+{y}")

            frame = tk.Frame(toast, bg="#333333", padx=12, pady=10,
                             highlightbackground="#555555", highlightthickness=1)
            frame.pack(fill=tk.BOTH, expand=True)

            tk.Label(frame, text=title, font=("Microsoft YaHei", 11, "bold"),
                     bg="#333333", fg="white", anchor=tk.W).pack(fill=tk.X)
            tk.Label(frame, text=message, font=("Microsoft YaHei", 9),
                     bg="#333333", fg="#cccccc", wraplength=290, anchor=tk.W).pack(fill=tk.X)

            toast.after(6000, toast.destroy)
        except Exception:
            logger.info(f"TOAST {title}: {message}")

    try:
        parent_window.after(0, _create_toast)
    except Exception:
        logger.info(f"TOAST {title}: {message}")


def hmac_compare_digest(a, b):
    import hmac as _hmac
    a = a.strip().lower()
    b = b.strip().lower()
    for prefix in ("sha256:", "sha1:"):
        if a.startswith(prefix):
            a = a[len(prefix):]
        if b.startswith(prefix):
            b = b[len(prefix):]
    if len(a) != len(b):
        return False
    return _hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ============================================================
#  UpdateManager - 核心更新管理器
# ============================================================

class UpdateManager:
    _instance = None
    _lock = threading.Lock()

    @property
    def UPDATE_API_URL(self):
        return f"{get_api_base_url()}/api/version/latest"

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance.version_info = None
                cls._instance.is_downloading = False
                cls._instance._cancel_requested = False
                cls._instance._state_lock = threading.Lock()
                from .version import get_version
                cls._instance.CURRENT_VERSION = get_version()
        return cls._instance

    @property
    def cancel_requested(self):
        with self._state_lock:
            return self._cancel_requested

    def _validate_download_url(self, url):
        try:
            parsed = urlparse(url)
            return parsed.hostname in _get_allowed_hosts()
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
                        else:
                            data['notification_type'] = 'log_only'

                        if callback:
                            callback(True, data)
                    else:
                        if callback:
                            callback(False, None)
                else:
                    if callback:
                        callback(None, f"服务器错误: {response.status_code}")

            except Exception as e:
                msg = "检查超时或无法连接到更新服务器" if isinstance(e, (ConnectionError, TimeoutError, OSError)) else f"检查失败: {str(e)}"
                if callback:
                    callback(None, msg)

        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()

    def download_update(self, download_url, save_path, expected_hash=None,
                        progress_callback=None, complete_callback=None, error_callback=None):
        if not self._validate_download_url(download_url):
            if error_callback:
                error_callback("下载地址不合法，拒绝下载")
            return

        with self._state_lock:
            if self.is_downloading:
                if error_callback:
                    error_callback("已有下载任务进行中")
                return
            self.is_downloading = True
            self._cancel_requested = False

        def download_thread():
            try:
                downloaded = 0
                hasher = hashlib.sha256()
                headers = {}
                resume_mode = False

                if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
                    existing_size = os.path.getsize(save_path)
                    headers["Range"] = f"bytes={existing_size}-"
                    with open(save_path, 'rb') as f:
                        while True:
                            chunk = f.read(8192)
                            if not chunk:
                                break
                            hasher.update(chunk)
                    downloaded = existing_size
                    logger.info(f"断点续传: 已有 {UpdateManager.format_size(downloaded)}，继续下载")

                response = get_http_session().get(download_url, stream=True, timeout=30, headers=headers)

                if response.status_code == 416:
                    response.close()
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    headers.pop("Range", None)
                    downloaded = 0
                    hasher = hashlib.sha256()
                    response = get_http_session().get(download_url, stream=True, timeout=30)

                if response.status_code == 206:
                    total_size = downloaded + int(response.headers.get('content-length', 0))
                    resume_mode = True
                elif response.status_code == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    hasher = hashlib.sha256()
                    resume_mode = False
                else:
                    response.raise_for_status()
                    total_size = 0

                os.makedirs(os.path.dirname(save_path), exist_ok=True)

                mode = 'ab' if resume_mode else 'wb'
                with open(save_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            if self.cancel_requested:
                                if error_callback:
                                    error_callback("下载已取消")
                                with self._state_lock:
                                    self.is_downloading = False
                                return

                            f.write(chunk)
                            hasher.update(chunk)
                            downloaded += len(chunk)

                            if total_size > 0 and progress_callback:
                                percentage = min(99, int((downloaded / total_size) * 100))
                                progress_callback(downloaded, total_size, percentage)

                if expected_hash:
                    actual_hash = hasher.hexdigest()
                    if not hmac_compare_digest(actual_hash, expected_hash):
                        if os.path.exists(save_path):
                            os.remove(save_path)
                        if error_callback:
                            error_callback("文件完整性校验失败，下载文件可能被篡改")
                        with self._state_lock:
                            self.is_downloading = False
                        return

                with self._state_lock:
                    self.is_downloading = False
                if complete_callback:
                    complete_callback(save_path)

            except Exception as e:
                with self._state_lock:
                    self.is_downloading = False
                if error_callback:
                    error_callback(f"下载失败: {str(e)}")

        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()

    def cancel_download(self):
        with self._state_lock:
            self._cancel_requested = True

    @staticmethod
    def format_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"


# ============================================================
#  PatchUpdater - 增量补丁更新器
# ============================================================

class PatchUpdater:
    """增量补丁更新：下载zip补丁包，按manifest逐文件原子替换"""

    def __init__(self):
        self._cancel_requested = False
        self._lock = threading.Lock()
        self._is_running = False

    @property
    def cancel_requested(self):
        with self._lock:
            return self._cancel_requested

    @property
    def is_running(self):
        with self._lock:
            return self._is_running

    def cancel(self):
        with self._lock:
            self._cancel_requested = True

    def download_and_apply(self, version_info: dict,
                           progress_callback=None,
                           complete_callback=None,
                           error_callback=None):
        """下载补丁包并应用更新"""
        download_url = version_info.get('patch_url') or version_info.get('download_url', '')
        if not download_url:
            if error_callback:
                error_callback("未提供补丁下载地址")
            return

        # 校验下载URL合法性
        updater = UpdateManager()
        if not updater._validate_download_url(download_url):
            if error_callback:
                error_callback("补丁下载地址不合法，拒绝下载")
            return

        with self._lock:
            self._cancel_requested = False
            if self._is_running:
                if error_callback:
                    error_callback("补丁更新正在进行中")
                return
            self._is_running = True
        temp_dir = None

        def _do_patch():
            nonlocal temp_dir
            try:
                # 1. 下载补丁zip
                if progress_callback:
                    progress_callback(0, 100, 0, "正在下载补丁包...")

                # 使用固定缓存目录，支持断点续传
                cache_dir = str(_PATCH_CACHE_DIR)
                os.makedirs(cache_dir, exist_ok=True)
                temp_dir = tempfile.mkdtemp(prefix='videogen_patch_', dir=cache_dir)
                zip_path = os.path.join(temp_dir, 'patch.zip')

                sha256_hash = hashlib.sha256()
                downloaded = 0
                resume_mode = False
                resp = None

                # 检查是否有未完成的下载（断点续传）
                if os.path.exists(zip_path) and os.path.getsize(zip_path) > 0:
                    existing_size = os.path.getsize(zip_path)
                    range_headers = {'Range': f'bytes={existing_size}-'}
                    try:
                        resume_resp = get_http_session().get(
                            download_url, stream=True, timeout=(10, 120), headers=range_headers
                        )
                        if resume_resp.status_code == 206:
                            resp = resume_resp
                            resume_mode = True
                            downloaded = existing_size
                            # 计算已有部分的hash
                            with open(zip_path, 'rb') as f:
                                while True:
                                    chunk = f.read(65536)
                                    if not chunk:
                                        break
                                    sha256_hash.update(chunk)
                            logger.info(f"补丁包断点续传: 已有 {UpdateManager.format_size(downloaded)}")
                        else:
                            # 服务器不支持续传，从头开始
                            downloaded = 0
                    except Exception:
                        downloaded = 0

                if not resume_mode:
                    resp = get_http_session().get(download_url, stream=True, timeout=(10, 120))

                if resp is None or resp.status_code not in (200, 206):
                    raise ValueError(f"下载失败: HTTP {resp.status_code}")

                total_size = int(resp.headers.get('content-length', 0))
                if resume_mode:
                    total_size = downloaded + total_size
                else:
                    total_size = total_size or version_info.get('patch_size', version_info.get('file_size', 0))

                mode = 'ab' if resume_mode else 'wb'
                with open(zip_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            if self.cancel_requested:
                                resp.close()
                                with self._lock:
                                    self._is_running = False
                                if error_callback:
                                    error_callback("下载已取消")
                                return
                            f.write(chunk)
                            sha256_hash.update(chunk)
                            downloaded += len(chunk)
                            if total_size > 0 and progress_callback:
                                pct = min(60, int((downloaded / total_size) * 60))
                                progress_callback(downloaded, total_size, pct, "正在下载补丁包...")

                # 下载完成，关闭response
                resp.close()

                # 2. SHA256校验（优先使用patch_hash）
                expected_hash = version_info.get('patch_hash') or version_info.get('file_hash') or version_info.get('sha256', '')
                if expected_hash:
                    actual_hash = sha256_hash.hexdigest()
                    if not hmac_compare_digest(actual_hash, expected_hash):
                        raise ValueError(f"补丁包SHA256校验失败")

                if progress_callback:
                    progress_callback(0, 0, 65, "正在解压补丁包...")

                # 3. 解压（带Zip Slip安全校验）
                if self.cancel_requested:
                    with self._lock:
                        self._is_running = False
                    if error_callback:
                        error_callback("更新已取消")
                    return

                extract_dir = os.path.join(temp_dir, 'extracted')
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # 安全校验：防止Zip Slip路径穿越攻击
                    for member in zf.namelist():
                        member_path = os.path.realpath(os.path.join(extract_dir, member))
                        if not member_path.startswith(os.path.realpath(extract_dir) + os.sep) and member_path != os.path.realpath(extract_dir):
                            raise ValueError(f"非法压缩包路径: {member}")
                    zf.extractall(extract_dir)

                # 4. 加载manifest
                if self.cancel_requested:
                    with self._lock:
                        self._is_running = False
                    if error_callback:
                        error_callback("更新已取消")
                    return

                manifest = self._load_manifest(extract_dir)

                if progress_callback:
                    progress_callback(0, 0, 70, "正在校验文件...")

                # 5. 校验manifest中的文件
                if manifest:
                    self._verify_manifest(manifest, extract_dir)

                # 6. 应用补丁
                if self.cancel_requested:
                    with self._lock:
                        self._is_running = False
                    if error_callback:
                        error_callback("更新已取消")
                    return
                if progress_callback:
                    progress_callback(0, 0, 75, "正在应用更新...")

                new_version = version_info.get('version', '')
                self._apply_patch(extract_dir, manifest, new_version, progress_callback)

                if progress_callback:
                    progress_callback(0, 0, 100, "更新完成！")

                logger.info(f"Patch applied successfully, new version: {new_version}")
                if complete_callback:
                    complete_callback(new_version)

            except Exception as e:
                logger.error(f"Patch update failed: {e}", exc_info=True)
                with self._lock:
                    self._is_running = False
                if error_callback:
                    error_callback(f"更新失败: {str(e)}")
                # 下载失败时保留zip文件以便断点续传，但清理解压目录
                if temp_dir:
                    try:
                        extract_dir = os.path.join(temp_dir, 'extracted')
                        if os.path.exists(extract_dir):
                            shutil.rmtree(extract_dir, ignore_errors=True)
                    except Exception:
                        pass
            else:
                # 成功后清理整个临时目录
                with self._lock:
                    self._is_running = False
                if temp_dir:
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    except Exception:
                        pass

        thread = threading.Thread(target=_do_patch, daemon=True)
        thread.start()

    def _load_manifest(self, extract_dir: str):
        manifest_path = os.path.join(extract_dir, 'manifest.json')
        if not os.path.exists(manifest_path):
            logger.info("No manifest.json found, treating as full directory replacement")
            return None

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            files = []
            for fdata in data.get('files', []):
                files.append(PatchFileEntry(
                    path=fdata.get('path', ''),
                    sha256=fdata.get('sha256', ''),
                    size=fdata.get('size', 0),
                ))

            return PatchManifest(
                version=data.get('version', ''),
                from_version=data.get('from_version', ''),
                files=files,
                release_notes=data.get('release_notes', ''),
                force_update=data.get('force_update', False),
            )
        except Exception as e:
            logger.warning(f"Failed to load manifest: {e}")
            return None

    def _verify_manifest(self, manifest: PatchManifest, extract_dir: str):
        for entry in manifest.files:
            # 路径安全校验
            dst = _ROOT_DIR / entry.path
            try:
                dst.resolve().relative_to(_ROOT_DIR.resolve())
            except ValueError:
                raise ValueError(f'非法路径: {entry.path}')

            src = os.path.join(extract_dir, entry.path)
            if not os.path.exists(src):
                raise ValueError(f'补丁文件缺失: {entry.path}')
            if entry.sha256:
                actual = _file_sha256(src)
                if actual != entry.sha256:
                    raise ValueError(f'文件校验失败: {entry.path}')

    def _apply_patch(self, extract_dir: str, manifest, new_version: str, progress_callback=None):
        total_files = len(manifest.files) if manifest and manifest.files else 0
        processed = 0

        # 收集已替换的文件，用于回滚
        replaced_files = []  # [(dst_path, backup_path), ...]

        try:
            if manifest and manifest.files:
                # 按manifest逐文件原子替换
                for entry in manifest.files:
                    src = os.path.join(extract_dir, entry.path)
                    dst = _ROOT_DIR / entry.path

                    # 路径安全校验：防止路径穿越攻击
                    try:
                        dst.resolve().relative_to(_ROOT_DIR.resolve())
                    except ValueError:
                        raise ValueError(f"非法路径: {entry.path}")

                    dst.parent.mkdir(parents=True, exist_ok=True)

                    # 备份原文件（用于回滚）
                    backup_path = None
                    if dst.exists():
                        backup_path = str(dst) + '.bak'
                        # 清理上次残留的备份
                        if os.path.exists(backup_path):
                            try:
                                if os.path.isdir(backup_path):
                                    shutil.rmtree(backup_path, ignore_errors=True)
                                else:
                                    os.remove(backup_path)
                            except Exception:
                                pass
                        shutil.copy2(str(dst), backup_path)

                    # 原子替换：先写.tmp，再os.replace()
                    # os.replace()跨驱动器会失败，回退到shutil.move()
                    tmp_dst = str(dst) + '.tmp'
                    if os.path.exists(tmp_dst):
                        try:
                            os.remove(tmp_dst)
                        except Exception:
                            pass
                    shutil.copy2(src, tmp_dst)
                    try:
                        os.replace(tmp_dst, str(dst))
                    except OSError:
                        # 跨驱动器时os.replace失败，使用shutil.move
                        shutil.move(tmp_dst, str(dst))

                    replaced_files.append((str(dst), backup_path))
                    logger.debug(f"Patched: {entry.path}")

                    processed += 1
                    if progress_callback and total_files > 0:
                        pct = 75 + int((processed / total_files) * 20)
                        progress_callback(0, 0, min(95, pct), f"正在更新: {entry.path}")
            else:
                # 无manifest，全目录替换
                for item in os.listdir(extract_dir):
                    if item == 'manifest.json':
                        continue
                    src = os.path.join(extract_dir, item)
                    dst = _ROOT_DIR / item

                    # 路径安全校验
                    try:
                        dst.resolve().relative_to(_ROOT_DIR.resolve())
                    except ValueError:
                        logger.warning(f"Skipping unsafe path: {item}")
                        continue

                    backup_path = None
                    if os.path.isdir(src):
                        if dst.exists():
                            backup_path = str(dst) + '.bak'
                            if os.path.exists(backup_path):
                                shutil.rmtree(backup_path, ignore_errors=True)
                            shutil.copytree(str(dst), backup_path)
                            shutil.rmtree(str(dst), ignore_errors=True)
                        shutil.copytree(src, str(dst))
                    else:
                        if dst.exists():
                            backup_path = str(dst) + '.bak'
                            shutil.copy2(str(dst), backup_path)
                        tmp_dst = str(dst) + '.tmp'
                        if os.path.exists(tmp_dst):
                            try:
                                os.remove(tmp_dst)
                            except Exception:
                                pass
                        shutil.copy2(src, tmp_dst)
                        try:
                            os.replace(tmp_dst, str(dst))
                        except OSError:
                            shutil.move(tmp_dst, str(dst))

                    replaced_files.append((str(dst), backup_path))
                    logger.debug(f"Patched: {item}")

            # 写入 version.json 更新版本号
            # 只有实际替换了文件才更新版本号
            if replaced_files:
                version_file = _ROOT_DIR / 'version.json'
                version_data = {
                    'version': new_version,
                    'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                }
                tmp_version = str(version_file) + '.tmp'
                if os.path.exists(tmp_version):
                    try:
                        os.remove(tmp_version)
                    except Exception:
                        pass
                Path(tmp_version).write_text(
                    json.dumps(version_data, ensure_ascii=False, indent=2), encoding='utf-8'
                )
                try:
                    os.replace(tmp_version, str(version_file))
                except OSError:
                    shutil.move(tmp_version, str(version_file))

                # 成功后清理备份文件
                for dst_path, backup_path in replaced_files:
                    if backup_path and os.path.exists(backup_path):
                        try:
                            if os.path.isdir(backup_path):
                                shutil.rmtree(backup_path, ignore_errors=True)
                            else:
                                os.remove(backup_path)
                        except Exception:
                            pass

        except Exception:
            # 回滚：恢复备份文件
            logger.error("Patch apply failed, rolling back...")
            for dst_path, backup_path in reversed(replaced_files):
                if backup_path and os.path.exists(backup_path):
                    try:
                        if os.path.isdir(backup_path):
                            # 目录型备份：先删除当前目录，再恢复备份
                            if os.path.isdir(dst_path):
                                shutil.rmtree(dst_path, ignore_errors=True)
                            shutil.copytree(backup_path, dst_path)
                            shutil.rmtree(backup_path, ignore_errors=True)
                        else:
                            try:
                                os.replace(backup_path, dst_path)
                            except OSError:
                                shutil.move(backup_path, dst_path)
                    except Exception as rollback_err:
                        logger.error(f"Rollback failed for {dst_path}: {rollback_err}")
            raise


# ============================================================
#  应用重启
# ============================================================

def restart_application():
    """重启应用程序（补丁更新后调用）

    支持三种运行模式：
    1. 内嵌Python模式（便携版）：python/pythonw.exe run.pyw
    2. PyInstaller打包模式：直接重启exe
    3. 开发模式：python run.py
    """
    logger.info("Restarting application for update...")
    try:
        env = os.environ.copy()

        # 检测是否为内嵌Python模式（便携版）
        # 便携版特征：_ROOT_DIR/python/python.exe 存在
        embedded_python = _ROOT_DIR / 'python' / 'python.exe'
        embedded_pythonw = _ROOT_DIR / 'python' / 'pythonw.exe'
        run_script = _ROOT_DIR / 'run.py'
        run_scriptw = _ROOT_DIR / 'run.pyw'

        if embedded_python.exists() and run_script.exists():
            # 内嵌Python模式（便携版）
            # 优先用pythonw.exe+run.pyw（无控制台窗口）
            logger.info("Restarting in embedded Python mode (portable)")
            if os.path.exists(os.path.join(str(_ROOT_DIR), 'ffmpeg', 'ffmpeg.exe')):
                env['FFMPEG_BINARY'] = str(_ROOT_DIR / 'ffmpeg' / 'ffmpeg.exe')

            if embedded_pythonw.exists() and run_scriptw.exists():
                # 无窗口模式（用户通常通过start.vbs启动）
                _portable_flags = subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == 'nt':
                    _portable_flags |= subprocess.CREATE_NO_WINDOW
                subprocess.Popen(
                    [str(embedded_pythonw), str(run_scriptw)] + sys.argv[1:],
                    cwd=str(_ROOT_DIR),
                    env=env,
                    creationflags=_portable_flags if os.name == 'nt' else 0,
                )
            else:
                # 回退到有窗口模式
                _portable_flags2 = subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == 'nt':
                    _portable_flags2 |= subprocess.CREATE_NO_WINDOW
                subprocess.Popen(
                    [str(embedded_python), str(run_script)] + sys.argv[1:],
                    cwd=str(_ROOT_DIR),
                    env=env,
                    creationflags=_portable_flags2 if os.name == 'nt' else 0,
                )
            os._exit(0)
        elif getattr(sys, 'frozen', False):
            # PyInstaller打包模式：直接重启exe
            logger.info("Restarting in PyInstaller mode")
            _restart_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == 'nt':
                _restart_flags |= subprocess.CREATE_NO_WINDOW
            subprocess.Popen(
                [sys.executable],
                cwd=os.path.dirname(sys.executable),
                env=env,
                creationflags=_restart_flags if os.name == 'nt' else 0,
            )
            os._exit(0)
        else:
            # 开发模式：重启python脚本
            logger.info("Restarting in development mode")
            main_script = str(run_script) if run_script.exists() else str(_ROOT_DIR / 'app.py')
            _dev_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            if os.name == 'nt':
                _dev_flags |= subprocess.CREATE_NO_WINDOW
            subprocess.Popen(
                [sys.executable, main_script] + sys.argv[1:],
                cwd=str(_ROOT_DIR),
                env=env,
                creationflags=_dev_flags if os.name == 'nt' else 0,
            )
            os._exit(0)
    except Exception as e:
        logger.error(f"Restart failed: {e}")
        os._exit(1)


# ============================================================
#  UpdateDialog - 更新对话框
# ============================================================

class UpdateDialog(tk.Toplevel):
    def __init__(self, parent, auto_check=False, notification_type='popup'):
        super().__init__(parent)
        self.parent = parent
        self.auto_check = auto_check
        self.notification_type = notification_type
        self.update_manager = UpdateManager()
        self.patch_updater = PatchUpdater()
        self.is_downloading = False
        self._forced = (notification_type == 'forced_popup')

        self.title("必须更新" if self._forced else "检查更新")
        self.geometry("600x480")
        self.resizable(False, False)

        if self._forced:
            self.protocol("WM_DELETE_WINDOW", self._on_force_close_attempt)
            # 禁用父窗口，防止用户绕过强制更新继续使用
            try:
                self.parent.attributes('-disabled', True)
            except Exception:
                pass
            self.grab_set()  # 模态窗口，防止切换到主窗口
        else:
            self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (480 // 2)
        self.geometry(f"+{x}+{y}")

        self.init_ui()

        if auto_check:
            self.check_updates()

    def _on_force_close_attempt(self):
        messagebox.showwarning(
            "必须更新",
            "此版本包含重要安全修复，必须更新后才能继续使用！\n请点击「立即更新」完成更新。"
        )

    def _release_parent(self):
        """恢复父窗口的可用状态"""
        try:
            self.parent.attributes('-disabled', False)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass

    def _on_close(self):
        """关闭窗口时取消正在进行的下载"""
        if self.is_downloading:
            self.update_manager.cancel_download()
            self.patch_updater.cancel()
            self.is_downloading = False
        self._release_parent()
        self.destroy()

    def destroy(self):
        """重写 destroy，确保父窗口始终被释放"""
        self._release_parent()
        super().destroy()

    def init_ui(self):
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        if self._forced:
            title_label = ttk.Label(
                main_frame,
                text="必须更新",
                font=("Microsoft YaHei", 16, "bold"),
                foreground="red"
            )
        else:
            title_label = ttk.Label(
                main_frame,
                text="版本更新",
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
        self.progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_var,
            font=("Microsoft YaHei", 9),
            foreground="#666"
        )

        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.check_btn = ttk.Button(btn_frame, text="检查更新", command=self.check_updates)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 5))

        if not self._forced:
            close_btn = ttk.Button(btn_frame, text="关闭", command=self.destroy)
            close_btn.pack(side=tk.LEFT, padx=5)

        self.download_btn = ttk.Button(btn_frame, text="立即更新", command=self.start_download)
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
            # 通过after回到主线程，确保线程安全
            try:
                self.after(0, lambda: self._on_check_complete(has_update, result))
            except Exception:
                pass

        self.update_manager.check_for_updates(on_check_complete)

    def _on_check_complete(self, has_update, result):
        """检查更新完成（在主线程中执行）"""
        if has_update is None:
            self.status_var.set(f"X {result}")
            self.check_btn.config(state=tk.NORMAL)
        elif has_update:
            self.show_update_available(result)
        else:
            self.status_var.set("您使用的是最新版本!")
            self.update_changelog("暂无更新内容")
            self.check_btn.config(state=tk.NORMAL)

    def show_update_available(self, version_info):
        self.version_info = version_info

        # 判断更新类型
        is_patch = bool(version_info.get('patch_url'))
        update_type_label = "增量补丁" if is_patch else "完整安装包"

        if self._forced:
            self.status_var.set(
                f"必须更新到 v{version_info['version']}! ({update_type_label})\n"
                f"发布日期: {version_info.get('release_date', '')}"
            )
        else:
            self.status_var.set(
                f"发现新版本 v{version_info['version']}! ({update_type_label})\n"
                f"发布日期: {version_info.get('release_date', '')}"
            )

        # changelog可能是字符串或列表
        changelog_raw = version_info.get('changelog', '')
        if isinstance(changelog_raw, list):
            changelog = "\n".join([f"- {item}" for item in changelog_raw])
        elif isinstance(changelog_raw, str) and changelog_raw:
            changelog = changelog_raw
        else:
            changelog = "暂无更新说明"
        self.update_changelog(changelog)

        if is_patch:
            display_size = UpdateManager.format_size(version_info.get('patch_size', 0))
            btn_text = f"增量更新 ({display_size})"
        else:
            display_size = UpdateManager.format_size(version_info.get('file_size', 0))
            btn_text = f"下载更新 ({display_size})"
        self.download_btn.config(text=btn_text)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.NORMAL)

        if self._forced:
            self.start_download()

    def update_changelog(self, text):
        self.changelog_text.config(state=tk.NORMAL)
        self.changelog_text.delete(1.0, tk.END)
        self.changelog_text.insert(tk.END, text)
        self.changelog_text.config(state=tk.DISABLED)

    def start_download(self):
        if not hasattr(self, 'version_info'):
            return

        # 防止重复点击：如果正在下载中，忽略
        if self.is_downloading:
            return

        version_info = self.version_info
        is_patch = bool(version_info.get('patch_url'))

        self.download_btn.pack_forget()
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.progress_label.pack()

        self.is_downloading = True

        if is_patch:
            # 增量补丁更新
            self._start_patch_update(version_info)
        else:
            # 全量安装包更新
            self._start_full_update(version_info)

    def _start_patch_update(self, version_info):
        def on_progress(downloaded, total, percentage, message=""):
            # Tkinter不是线程安全的，通过after回到主线程
            try:
                self.after(0, lambda: self._update_progress(percentage, message, downloaded, total))
            except Exception:
                pass

        def on_complete(new_version):
            try:
                self.after(0, lambda: self._on_patch_complete(new_version))
            except Exception:
                pass

        def on_error(error_msg):
            try:
                self.after(0, lambda: self._on_update_error(error_msg))
            except Exception:
                pass

        self.patch_updater.download_and_apply(
            version_info,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error,
        )

    def _update_progress(self, percentage, message, downloaded=0, total=0):
        """在主线程中更新进度条（线程安全）"""
        try:
            self.progress_bar['value'] = percentage
            if message:
                self.progress_var.set(message)
            elif total > 0:
                self.progress_var.set(
                    f"下载中... {UpdateManager.format_size(downloaded)} / "
                    f"{UpdateManager.format_size(total)} ({percentage}%)"
                )
        except Exception:
            pass

    def _on_patch_complete(self, new_version):
        """补丁更新完成（在主线程中执行）"""
        try:
            self.is_downloading = False
            self.progress_bar['value'] = 100
            self.progress_var.set("更新完成！正在重启程序...")
            self.cancel_btn.pack_forget()

            if self._forced:
                self._release_parent()
                self.after(1500, lambda: restart_application())
            else:
                self._release_parent()
                if messagebox.askyesno(
                    "更新完成",
                    f"已成功更新到 v{new_version}！\n需要重启程序才能生效，是否立即重启？"
                ):
                    restart_application()
                else:
                    self.download_btn.config(text="重启程序")
                    self.download_btn.pack(side=tk.LEFT, padx=5)
                    self.download_btn.config(command=lambda: restart_application())
        except Exception:
            pass

    def _on_update_error(self, error_msg):
        """更新失败（在主线程中执行）"""
        try:
            self.is_downloading = False
            is_cancelled = "取消" in error_msg
            if is_cancelled:
                self.progress_var.set("已取消")
            else:
                self.progress_var.set(f"X {error_msg}")
            self.cancel_btn.pack_forget()
            self.cancel_btn.config(state=tk.NORMAL)
            self.download_btn.pack(side=tk.LEFT, padx=5)
            self.check_btn.config(state=tk.NORMAL)
            if not is_cancelled:
                messagebox.showerror("更新失败", error_msg)
            # 强制更新失败时，恢复父窗口但保持弹窗不关闭，用户可重试
            # 不调用_release_parent，因为强制更新场景下用户不应回到主界面
        except Exception:
            pass

    def _start_full_update(self, version_info):
        download_url = version_info.get('download_url')
        if not download_url:
            messagebox.showerror("更新失败", "未提供全量安装包下载地址，请尝试增量更新或联系管理员")
            return

        save_dir = os.path.join(_temp_base, 'VideoGen_Update')
        filename = f"VideoGen_v{version_info['version']}_Setup.exe"
        save_path = os.path.join(save_dir, filename)

        def on_progress(downloaded, total, percentage):
            try:
                self.after(0, lambda: self._update_progress(percentage, "", downloaded, total))
            except Exception:
                pass

        def on_complete(file_path):
            try:
                self.after(0, lambda: self._on_full_download_complete(file_path))
            except Exception:
                pass

        def on_error(error_msg):
            try:
                self.after(0, lambda: self._on_update_error(error_msg))
            except Exception:
                pass

        expected_hash = version_info.get('file_hash')

        self.update_manager.download_update(
            download_url,
            save_path,
            expected_hash=expected_hash,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error
        )

    def _on_full_download_complete(self, file_path):
        """全量包下载完成（在主线程中执行）"""
        try:
            self.is_downloading = False
            self.progress_bar['value'] = 100
            self.progress_var.set("下载完成! 文件完整性校验通过!")
            self.cancel_btn.pack_forget()

            if self._forced:
                self._release_parent()
                self._launch_installer_and_exit(file_path)
            else:
                self._release_parent()
                if messagebox.askyesno(
                    "下载完成",
                    f"更新包已下载到:\n{file_path}\n\n是否立即安装?"
                ):
                    self._launch_installer_and_exit(file_path)
                else:
                    self.download_btn.pack(side=tk.LEFT, padx=5)
        except Exception:
            pass

    def _launch_installer_and_exit(self, file_path):
        self._spawn_restart_watcher(file_path)
        try:
            self.parent.quit()
        except Exception:
            pass
        os._exit(0)

    def _spawn_restart_watcher(self, installer_path):
        """生成一个独立的重启监视器进程：等待安装程序结束后自动重启程序"""
        watcher_code = r'''
import subprocess
import sys
import os
import time

def _try_launch(exe_path):
    if not os.path.isfile(exe_path):
        import glob
        candidates = glob.glob(os.path.join(os.environ.get('ProgramFiles', ''), 'VideoGen', 'VideoGen.exe'))
        candidates += glob.glob(os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'VideoGen', 'VideoGen.exe'))
        candidates += glob.glob(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'VideoGen', 'VideoGen.exe'))
        for c in candidates:
            if os.path.isfile(c):
                exe_path = c
                break
    try:
        subprocess.Popen([exe_path], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
    except Exception:
        try:
            os.startfile(exe_path)
        except Exception:
            pass

installer_path = sys.argv[1]
app_exe = sys.argv[2]
max_wait = int(sys.argv[3])

# 启动安装程序
proc = None
try:
    proc = subprocess.Popen(
        [installer_path],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    )
except Exception:
    try:
        os.startfile(installer_path)
    except Exception:
        pass

# 等待安装程序结束（最多max_wait秒）
if proc is not None:
    try:
        proc.wait(timeout=max_wait)
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
else:
    # 无法获取进程句柄，等待固定时间
    time.sleep(max_wait)

# 安装程序结束后，等待3秒再启动应用
time.sleep(3)
_try_launch(app_exe)
'''

        if getattr(sys, 'frozen', False):
            app_exe = sys.executable
        else:
            app_exe = sys.executable

        watcher_dir = os.path.join(_temp_base, 'VideoGen_Update')
        os.makedirs(watcher_dir, exist_ok=True)

        if getattr(sys, 'frozen', False):
            watcher_path = os.path.join(watcher_dir, '_restart_watcher.bat')
            bat_content = (
                '@echo off\n'
                'chcp 65001 >nul 2>&1\n'
                'start "" /wait """"%~1""""\n'
                'timeout /t 3 /nobreak >nul\n'
                'start "" """"%~2""""\n'
                'del "%~f0"\n'
            )
            watcher_tmp = watcher_path + '.tmp'
            with open(watcher_tmp, 'w', encoding='utf-8') as f:
                f.write(bat_content)
            try:
                os.replace(watcher_tmp, watcher_path)
            except OSError:
                shutil.move(watcher_tmp, watcher_path)

            subprocess.Popen(
                [watcher_path, installer_path, app_exe],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True
            )
        else:
            watcher_path = os.path.join(watcher_dir, '_restart_watcher.py')

            watcher_tmp = watcher_path + '.tmp'
            with open(watcher_tmp, 'w', encoding='utf-8') as f:
                f.write(watcher_code)
            try:
                os.replace(watcher_tmp, watcher_path)
            except OSError:
                shutil.move(watcher_tmp, watcher_path)

            subprocess.Popen(
                [sys.executable, watcher_path, installer_path, app_exe, '300'],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW,
                close_fds=True
            )

    def cancel_download(self):
        if self.is_downloading:
            # 只发送取消信号，不直接修改is_downloading
            # 子线程检测到取消后会自行设置is_downloading=False
            self.update_manager.cancel_download()
            self.patch_updater.cancel()
            self.progress_var.set("正在取消...")
            self.cancel_btn.config(state=tk.DISABLED)


# ============================================================
#  对外接口
# ============================================================

def check_and_notify_update(parent_window, auto_check=False, silent=False):
    if silent:
        update_mgr = UpdateManager()

        def _is_window_alive():
            """检查窗口是否仍然存在且可用"""
            try:
                parent_window.winfo_exists()
                return True
            except Exception:
                return False

        def on_check_complete(has_update, result):
            if has_update is True:
                notification_type = result.get('notification_type', 'log_only')
                version = result.get('version', '未知')

                if notification_type == 'forced_popup':
                    def _show_forced():
                        if _is_window_alive():
                            UpdateDialog(parent_window, auto_check=True, notification_type='forced_popup')
                    try:
                        if _is_window_alive():
                            parent_window.after(0, _show_forced)
                        else:
                            _show_forced()
                    except Exception:
                        _show_forced()

                elif notification_type == 'popup':
                    def _show_popup():
                        if _is_window_alive():
                            UpdateDialog(parent_window, auto_check=True, notification_type='popup')
                    try:
                        if _is_window_alive():
                            parent_window.after(0, _show_popup)
                        else:
                            _show_popup()
                    except Exception:
                        _show_popup()

                elif notification_type == 'log_only':
                    _show_windows_toast(
                        parent_window,
                        "发现新版本",
                        f"短视频生成器 v{version} 已发布，点击「检查更新」获取"
                    )
                    try:
                        if _is_window_alive() and hasattr(parent_window, 'log'):
                            parent_window.log(f"发现新版本 v{version}(后台检查)")
                    except Exception:
                        pass
                else:
                    try:
                        if _is_window_alive() and hasattr(parent_window, 'log'):
                            parent_window.log(f"发现新版本 v{version}(后台检查)")
                    except Exception:
                        pass

        update_mgr.check_for_updates(on_check_complete)
    else:
        dialog = UpdateDialog(parent_window, auto_check=auto_check, notification_type='popup')
        # 非自动检查时等待对话框关闭；自动检查时对话框自行管理生命周期
        if not auto_check:
            dialog.wait_window()


# ============================================================
#  开发者工具：创建补丁包
# ============================================================

def create_patch_zip(
    version: str,
    from_version: str,
    changed_files: list,
    output_path: str,
    release_notes: str = '',
    force_update: bool = False,
    base_dir: Optional[str] = None,
) -> dict:
    """创建增量补丁zip包（供开发者/PackPatch.bat调用）

    Args:
        version: 新版本号
        from_version: 从哪个版本升级
        changed_files: 变更文件的相对路径列表
        output_path: 输出zip路径
        release_notes: 更新说明
        force_update: 是否强制更新
        base_dir: 项目根目录，默认自动检测

    Returns:
        dict: 包含 path, sha256, size, file_count 的信息
    """
    if base_dir is None:
        base_dir = str(_ROOT_DIR)

    manifest_data = {
        'version': version,
        'from_version': from_version,
        'files': [],
        'release_notes': release_notes,
        'force_update': force_update,
    }

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path in changed_files:
            # 安全校验：防止路径穿越
            normalized = os.path.normpath(rel_path)
            if normalized.startswith('..') or os.path.isabs(normalized):
                logger.warning(f"Skipping unsafe path: {rel_path}")
                continue

            abs_path = os.path.join(base_dir, rel_path)
            if not os.path.exists(abs_path):
                logger.warning(f"File not found, skipping: {rel_path}")
                continue

            file_sha256 = _file_sha256(abs_path)
            file_size = os.path.getsize(abs_path)

            manifest_data['files'].append({
                'path': rel_path,
                'sha256': file_sha256,
                'size': file_size,
            })

            zf.write(abs_path, rel_path)

        zf.writestr('manifest.json', json.dumps(manifest_data, ensure_ascii=False, indent=2))

    zip_sha256 = _file_sha256(output_path)
    zip_size = os.path.getsize(output_path)

    return {
        'path': output_path,
        'sha256': zip_sha256,
        'size': zip_size,
        'file_count': len(manifest_data['files']),
    }
