"""Logging mixin - immediate UI log updates with scroll preservation."""
import datetime
import tkinter as tk


class LoggingMixin:
    def log(self, message):
        """记录日志 - 每条立即刷新，保留用户滚动位置"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)

        def update_ui():
            if hasattr(self, 'txt_log') and self.txt_log:
                try:
                    # 记录插入前的滚动位置
                    yview = self.txt_log.yview()
                    scroll_pos = yview[0]
                    at_bottom = yview[1] >= 0.95

                    self.txt_log.configure(state=tk.NORMAL)
                    self.txt_log.insert(tk.END, log_message + '\n')

                    if at_bottom:
                        self.txt_log.see(tk.END)
                    else:
                        self.txt_log.yview_moveto(scroll_pos)
                except Exception:
                    pass

        if hasattr(self, 'root') and self.root:
            self.root.after(0, update_ui)
