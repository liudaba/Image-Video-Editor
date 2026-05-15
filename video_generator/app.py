"""My-Video Generator - Main Entry Point

This file contains module-level setup (console, imports) and the entry point.
All business logic lives in video_generator/mixins/ modules.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import sys
import datetime
import warnings
import ctypes
from ctypes import wintypes

# ============ Sub-module imports ============

if __name__ == "__main__":
    print("✅ 优化模块已加载: 智能缓存 + 并行生成 + 批量SD + 硬件加速（延迟检测）")

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

# ============ Windows console setup ============
_is_pythonw = sys.executable.lower().endswith('pythonw.exe')
_has_no_console = sys.stdout is None or sys.stderr is None
_console_allocated = False

# 仅在非打包的开发模式下才显示控制台，打包后完全无控制台
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
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8')

    ctypes.windll.kernel32.SetConsoleTitleW("短视频生成器 - 日志控制台")


def _print_console_banner():
    if not _should_show_console:
        return
    try:
        print("=" * 60)
        print("🎬 短视频生成器 - 日志控制台")
        print("=" * 60)
        print(f"启动时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    pass


def _check_critical_files(app_dir):
    import logging
    logger = logging.getLogger("startup_check")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(app_dir, "startup_check.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
        logger.addHandler(handler)

    internal_dir = os.path.join(app_dir, "_internal")
    critical = {
        "config.json": os.path.join(app_dir, "config.json"),
        ".license_verify_key": os.path.join(app_dir, ".license_verify_key"),
    }
    missing = []
    for name, path in critical.items():
        if not os.path.exists(path):
            alt_path = os.path.join(internal_dir, name)
            if os.path.exists(alt_path):
                logger.info(f"FOUND in _internal/: {name}")
            else:
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
        print("[OK] VideoGenApp created successfully")
    except Exception as e:
        print(f"[ERROR] VideoGenApp init failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    root.after(800, app._deferred_auth_check)
    root.mainloop()


if __name__ == "__main__":
    main()
