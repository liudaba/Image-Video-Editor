"""Logging mixin - thread-safe logging with smart auto-scroll and file persistence."""
import datetime
import logging
import os
import threading
import traceback
import tkinter as tk
import sys

_MAX_LOG_LINES = 5000
_TRIM_LOG_LINES = 4000

_print_lock = threading.Lock()

_file_logger = None
_file_logger_lock = threading.Lock()


def _get_file_logger(base_dir):
    global _file_logger
    if _file_logger is not None:
        return _file_logger
    with _file_logger_lock:
        if _file_logger is not None:
            return _file_logger
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        logger = logging.getLogger("videogen")
        logger.setLevel(logging.DEBUG)
        if logger.handlers:
            _file_logger = logger
            return _file_logger
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        fh = logging.FileHandler(
            os.path.join(log_dir, f"app_{today}.log"),
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
        _file_logger = logger
        return _file_logger


def safe_print(*args, **kwargs):
    """线程安全的 print 替代函数"""
    with _print_lock:
        try:
            kwargs.setdefault('flush', True)
            print(*args, **kwargs)
        except Exception:
            pass


def safe_print_exc():
    """线程安全的 traceback.print_exc 替代函数"""
    with _print_lock:
        try:
            traceback.print_exc()
            sys.stderr.flush()
        except Exception:
            pass


class LoggingMixin:
    def log(self, message):
        """线程安全日志 - GUI智能滚动 + 控制台同步输出

        GUI日志：完整输出所有日志，智能滚动，行数上限保护
        控制台：完整输出所有日志，线程安全，顺序与GUI一致
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"

        with _print_lock:
            try:
                print(log_message, flush=True)
            except Exception:
                pass

        try:
            if hasattr(self, 'base_dir') and self.base_dir:
                fl = _get_file_logger(self.base_dir)
                if fl:
                    fl.info(message)
        except Exception:
            pass

        if not hasattr(self, '_user_scrolling'):
            self._user_scrolling = False

        if not hasattr(self, '_log_line_count'):
            self._log_line_count = 0

        def update_ui():
            if hasattr(self, 'txt_log') and self.txt_log:
                try:
                    self.txt_log.configure(state=tk.NORMAL)
                    self.txt_log.insert(tk.END, log_message + '\n')
                    self._log_line_count += 1

                    if self._log_line_count > _MAX_LOG_LINES:
                        delete_count = self._log_line_count - _TRIM_LOG_LINES
                        self.txt_log.delete('1.0', f'{delete_count}.0')
                        self._log_line_count = _TRIM_LOG_LINES

                    if not self._user_scrolling:
                        self.txt_log.see(tk.END)
                except Exception:
                    pass

        if hasattr(self, 'root') and self.root:
            self.root.after(0, update_ui)

    def _log_exception(self, prefix, exc=None):
        """线程安全异常日志 - GUI显示摘要，控制台显示完整堆栈

        Args:
            prefix: 日志前缀
            exc: 异常对象，默认使用当前异常上下文
        """
        if exc is None:
            exc_info = traceback.format_exc()
            msg = prefix
        else:
            exc_info = traceback.format_exception(type(exc), exc, exc.__traceback__)
            exc_info = ''.join(exc_info)
            msg = f"{prefix}: {exc}"
        self.log(msg)
        with _print_lock:
            try:
                print(exc_info, flush=True)
            except Exception:
                pass

    def _toggle_auto_scroll(self):
        if hasattr(self, '_auto_scroll_var'):
            auto = self._auto_scroll_var.get()
            self._user_scrolling = not auto
            if auto:
                if hasattr(self, 'txt_log') and self.txt_log:
                    self.txt_log.see(tk.END)

    def _on_log_scroll(self, event):
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        try:
            yview = self.txt_log.yview()
            at_bottom = yview[1] >= 0.998

            if event.delta:
                if event.delta > 0:
                    if not at_bottom:
                        self._user_scrolling = True
                        if hasattr(self, '_auto_scroll_var'):
                            self._auto_scroll_var.set(False)
            elif event.num == 4:
                self._user_scrolling = True
                if hasattr(self, '_auto_scroll_var'):
                    self._auto_scroll_var.set(False)
            elif event.num == 5:
                pass

            if at_bottom:
                self._user_scrolling = False
                if hasattr(self, '_auto_scroll_var'):
                    self._auto_scroll_var.set(True)
        except Exception:
            pass

    def _on_log_scrollbar(self, *args):
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        try:
            yview = self.txt_log.yview()
            at_bottom = yview[1] >= 0.998
            if at_bottom:
                self._user_scrolling = False
                if hasattr(self, '_auto_scroll_var'):
                    self._auto_scroll_var.set(True)
            elif len(args) >= 2 and args[0] == 'moveto':
                self._user_scrolling = True
                if hasattr(self, '_auto_scroll_var'):
                    self._auto_scroll_var.set(False)
        except Exception:
            pass

    def _setup_smart_scroll(self):
        """初始化智能滚动监听（在日志文本框创建后调用）"""
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        self._user_scrolling = False
        self._log_line_count = 0

        self.txt_log.bind('<MouseWheel>', self._on_log_scroll)
        self.txt_log.bind('<Button-4>', self._on_log_scroll)
        self.txt_log.bind('<Button-5>', self._on_log_scroll)

        if hasattr(self, '_log_scrollbar') and self._log_scrollbar:
            self._log_scrollbar.config(command=self._smart_yview)

    def _smart_yview(self, *args):
        """智能滚动条命令：拖动时检测用户是否在底部"""
        if hasattr(self, 'txt_log') and self.txt_log:
            self.txt_log.yview(*args)
            self._on_log_scrollbar(*args)
