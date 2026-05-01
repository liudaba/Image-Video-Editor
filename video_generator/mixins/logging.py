"""Logging mixin - smart auto-scroll with user scroll detection."""
import datetime
import tkinter as tk

_CONSOLE_ONLY_KEYS = ['✅', '❌', '🎉', '📍', '⚠️', '🗑️', '🔧', '💡', '🎬', '🎞️', '📊', '🔍', '步骤', '完成', '失败', '错误', '启动', '就绪']


class LoggingMixin:
    def log(self, message):
        """记录日志 - GUI智能滚动 + 控制台精简输出
        
        GUI日志：完整输出所有日志，智能滚动
        控制台：只输出关键节点信息，减少滚动干扰
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"

        is_important = any(key in message for key in _CONSOLE_ONLY_KEYS)
        if is_important:
            print(log_message)

        if not hasattr(self, '_user_scrolling'):
            self._user_scrolling = False

        def update_ui():
            if hasattr(self, 'txt_log') and self.txt_log:
                try:
                    self.txt_log.configure(state=tk.NORMAL)
                    self.txt_log.insert(tk.END, log_message + '\n')

                    if not self._user_scrolling:
                        self.txt_log.see(tk.END)
                except Exception:
                    pass

        if hasattr(self, 'root') and self.root:
            self.root.after(0, update_ui)

    def _on_log_scroll(self, event):
        """监听滚动事件：用户上滚时暂停自动跟随，滚回底部时恢复"""
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        try:
            yview = self.txt_log.yview()
            at_bottom = yview[1] >= 0.998

            if event.delta:
                if event.delta < 0:
                    pass
                else:
                    if at_bottom:
                        self._user_scrolling = False
                    else:
                        self._user_scrolling = True
            elif event.num == 4:
                self._user_scrolling = True
            elif event.num == 5:
                if at_bottom:
                    self._user_scrolling = False

            if at_bottom:
                self._user_scrolling = False
        except Exception:
            pass

    def _on_log_scrollbar(self, *args):
        """监听滚动条拖动：用户拖动滚动条时判断是否在底部"""
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        try:
            yview = self.txt_log.yview()
            at_bottom = yview[1] >= 0.998
            if at_bottom:
                self._user_scrolling = False
            elif len(args) >= 2 and args[0] == 'moveto':
                self._user_scrolling = True
        except Exception:
            pass

    def _setup_smart_scroll(self):
        """初始化智能滚动监听（在日志文本框创建后调用）"""
        if not hasattr(self, 'txt_log') or not self.txt_log:
            return

        self._user_scrolling = False

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
