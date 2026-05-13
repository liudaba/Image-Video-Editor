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


def main():
    from video_generator.config import get_ffmpeg_dir
    ffmpeg_dir = get_ffmpeg_dir()
    if ffmpeg_dir:
        os.environ["FFMPEG_BINARY"] = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        os.environ["ImageIO_FFMPEG_EXE"] = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        existing_path = os.environ.get("PATH", "")
        if ffmpeg_dir not in existing_path:
            os.environ["PATH"] = ffmpeg_dir + ";" + existing_path

    _print_console_banner()
    root = tk.Tk()
    root.title("短视频生成器")
    root.geometry("400x200")
    root.resizable(False, False)
    root.configure(bg="#1e1e1e")
    _sw = root.winfo_screenwidth()
    _sh = root.winfo_screenheight()
    _x = (_sw - 400) // 2
    _y = (_sh - 200) // 2
    root.geometry(f"400x200+{_x}+{_y}")
    _loading_label = tk.Label(root, text="正在验证授权，请稍候...", font=("Microsoft YaHei", 13), bg="#1e1e1e", fg="#d4d4d4")
    _loading_label.pack(expand=True)

    _login_ok = [False]

    def _do_login_check():
        from video_generator.license_manager import check_and_show_login
        try:
            license_status = check_and_show_login(root)
        except Exception as e:
            print(f"[ERROR] check_and_show_login failed: {e}")
            import traceback
            traceback.print_exc()
            root.quit()
            return

        if not license_status.get("valid", False):
            print(f"[WARN] license invalid: {license_status}")
            root.quit()
            return

        try:
            _loading_label.destroy()
        except Exception:
            pass

        _login_ok[0] = True
        try:
            app = VideoGenApp(root)
            print("[OK] VideoGenApp created successfully")
        except Exception as e:
            print(f"[ERROR] VideoGenApp init failed: {e}")
            import traceback
            traceback.print_exc()
            root.quit()

    root.after(100, _do_login_check)
    root.mainloop()

    if not _login_ok[0]:
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    main()
