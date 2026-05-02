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

print("✅ 优化模块已加载: 智能缓存 + 并行生成 + 批量SD + 硬件加速（延迟检测）")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

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

if sys.platform == "win32":
    if _is_pythonw or _has_no_console:
        ctypes.windll.kernel32.AllocConsole()
        _console_allocated = True
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            SW_HIDE = 0
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
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

warnings.filterwarnings("ignore", message="urllib3.*doesn't match a supported version", module="requests")


class DocuMakerLiteV7(
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


# 创建根窗口
root = tk.Tk()

# 初始化应用程序
app = DocuMakerLiteV7(root)

# 启动主循环
root.mainloop()
