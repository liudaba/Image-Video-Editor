"""My-Video Generator - Main Entry Point

This file contains module-level setup (console, imports) and the entry point.
All business logic lives in video_generator/mixins/ modules.
"""
import tkinter as tk
import os
import sys
import io
import datetime
import time
import warnings
import ctypes

# ============ Windows console setup (MUST be before any imports that may use stdout) ============
_is_pythonw = sys.executable.lower().endswith('pythonw.exe')
_has_no_console = sys.stdout is None or sys.stderr is None
_console_allocated = False

# PyInstaller 打包的 Windows GUI 程序中 sys.stdout/stderr 为 None，
# 导致 tqdm、whisper 等库调用 .write() 时崩溃。提前替换为安全对象。
class _NullWriter:
    """Dummy writer that silently discards all output."""
    def write(self, *args, **kwargs):
        return 0
    def flush(self):
        pass
    def isatty(self):
        return False
    def fileno(self):
        raise io.UnsupportedOperation("fileno")

if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()

# ============ Sub-module imports ============

sys.path.append(os.path.dirname(__file__))

# ============ Mixin imports ============
from video_generator.mixins.ui_init import UIInitMixin
from video_generator.mixins.ui_panels import UIPanelsMixin
from video_generator.mixins.ui_handlers import UIHandlersMixin
from video_generator.mixins.audio import AudioMixin
from video_generator.mixins.shots import ShotsMixin
from video_generator.mixins.images import ImagesMixin
from video_generator.mixins.video import VideoMixin
from video_generator.mixins.resource import ResourceMixin
from video_generator.mixins.logging import LoggingMixin

# 检测是否为便携版（内嵌Python模式）
_is_portable = False
if not getattr(sys, 'frozen', False):
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _embedded_python = os.path.join(_project_root, 'python', 'python.exe')
    _is_portable = os.path.exists(_embedded_python)

# 仅在开发模式下显示控制台；便携版和PyInstaller打包版不显示
# 便携版通过start.bat(python.exe)启动时已有控制台，不需要额外分配
# 便携版通过start.vbs(pythonw.exe)启动时不应该分配控制台
if _is_portable:
    _should_show_console = False  # 便携版：依赖启动方式决定是否有控制台
else:
    _should_show_console = not getattr(sys, 'frozen', False)

if sys.platform == "win32" and _should_show_console:
    if _is_pythonw or _has_no_console:
        ctypes.windll.kernel32.AllocConsole()
        _console_allocated = True
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    else:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()

    if hwnd:
        user32 = ctypes.windll.user32
        hMenu = user32.GetSystemMenu(hwnd, False)
        if hMenu:
            SC_CLOSE = 0xF060
            MF_BYCOMMAND = 0x00000000
            user32.DeleteMenu(hMenu, SC_CLOSE, MF_BYCOMMAND)
            user32.DrawMenuBar(hwnd)
        GWL_STYLE = -16
        WS_SYSMENU = 0x00080000
        WS_MINIMIZEBOX = 0x00020000
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        style = style | WS_MINIMIZEBOX
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.DrawMenuBar(hwnd)

    def _console_ctrl_handler(ctrl_type):
        if ctrl_type in (2, 5, 6):
            return True
        return False

    try:
        HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        _handler = HANDLER_ROUTINE(_console_ctrl_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)
    except Exception:
        pass

    if _is_pythonw or _has_no_console:
        try:
            sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
            sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
        except OSError:
            # AllocConsole 可能失败（权限不足等），保持 _NullWriter
            pass

    ctypes.windll.kernel32.SetConsoleTitleW("短视频生成器 - 日志控制台")


def _print_console_banner():
    if not _should_show_console:
        return
    try:
        print("=" * 60)
        print("🎬 短视频生成器 - 日志控制台")
        print("=" * 60)
        print(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
        print(f"运行模式: {'pythonw.exe (GUI模式)' if _is_pythonw else 'python.exe (控制台模式)'}")
        print("=" * 60)
        print()
        print("💡 提示: 此窗口显示程序运行日志")
        print("   • 可以最小化到任务栏")
        print("   • 关闭按钮已锁定，请通过主程序退出")
        print("   • 关闭主程序时此窗口会自动关闭")
        print("=" * 60)
        print()
    except UnicodeEncodeError:
        pass


warnings.filterwarnings("ignore", message="urllib3.*doesn't match a supported version", module="requests")


class VideoGenApp(
    LoggingMixin,
    UIInitMixin,
    UIPanelsMixin,
    UIHandlersMixin,
    AudioMixin,
    ShotsMixin,
    ImagesMixin,
    VideoMixin,
    ResourceMixin,
):
    """短视频生成器 - 主应用类（Mixin 组合，业务逻辑在各 Mixin 模块中）"""

    def start_periodic_update_check(self, interval_hours=24):
        """启动周期性更新检查"""
        from .auto_updater import check_and_notify_update

        def _do_check():
            try:
                check_and_notify_update(self.root, auto_check=True, silent=True)
            except Exception as e:
                import logging
                logging.getLogger("auto_updater").debug(f"Periodic update check failed: {e}")

        _do_check()
        self.root.after(int(interval_hours * 3600 * 1000),
                        lambda: self.start_periodic_update_check(interval_hours))


def _check_critical_files(app_dir):
    import logging
    logger = logging.getLogger("startup_check")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(app_dir, "startup_check.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
        handler.formatter.converter = time.localtime
        logger.addHandler(handler)

    internal_dir = os.path.join(app_dir, "_internal")
    critical = {
        "config.json": [
            os.path.join(app_dir, "config.json"),
            os.path.join(internal_dir, "config.json"),
        ],
        ".license_verify_pubkey.pem": [
            os.path.join(app_dir, ".license_verify_pubkey.pem"),
            os.path.join(internal_dir, ".license_verify_pubkey.pem"),
        ],
    }
    missing = []
    for name, paths in critical.items():
        found = False
        for path in paths:
            if os.path.exists(path):
                found = True
                break
        if not found:
            missing.append(name)
            logger.warning(f"MISSING: {name}")

    if missing:
        logger.error(f"Critical files missing: {', '.join(missing)}")

    try:
        app_dir.encode("ascii")
    except UnicodeEncodeError:
        logger.warning(f"Non-ASCII path detected: {app_dir}")

    ffmpeg_dir = os.path.join(app_dir, "ffmpeg")
    if os.path.isdir(ffmpeg_dir) and not os.path.isfile(os.path.join(ffmpeg_dir, "ffmpeg.exe")):
        logger.warning("FFmpeg directory exists but ffmpeg.exe is missing")

    whisper_dir = os.path.join(app_dir, "whisper_models")
    if os.path.isdir(whisper_dir):
        has_model = any(f.endswith(".pt") for f in os.listdir(whisper_dir))
        if not has_model:
            logger.warning("Whisper models directory exists but no .pt model files found")



def main():
    from video_generator.config import get_ffmpeg_dir, get_app_dir
    _app_dir = get_app_dir()

    _check_critical_files(_app_dir)

    ffmpeg_dir = get_ffmpeg_dir()
    if ffmpeg_dir:
        os.environ["FFMPEG_BINARY"] = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        os.environ["ImageIO_FFMPEG_EXE"] = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        existing_path = os.environ.get("PATH", "")
        if ffmpeg_dir not in existing_path:
            os.environ["PATH"] = ffmpeg_dir + ";" + existing_path

    _print_console_banner()
    root = tk.Tk()
    root.withdraw()

    try:
        app = VideoGenApp(root)
        root.deiconify()
    except Exception as e:
        print(f"[ERROR] VideoGenApp init failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    root.after(800, app._deferred_auth_check)
    root.after(3000, lambda: app.start_periodic_update_check(interval_hours=24))
    root.mainloop()


if __name__ == "__main__":
    main()

