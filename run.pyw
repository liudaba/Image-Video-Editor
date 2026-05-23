#!/usr/bin/env python3
"""VideoGenerator 启动入口（无控制台模式，由 pythonw.exe 调用）"""
import sys
import os

# 确保项目根目录在 sys.path 中
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# pythonw.exe 模式下重定向 stdout/stderr 到日志文件，避免写 None 报错
_log_path = os.path.join(app_dir, "_pythonw_error.log")

class _Logger:
    def __init__(self, log_path):
        self._log_path = log_path
        self._file = None
    def write(self, msg):
        if not msg:
            return
        try:
            if self._file is None:
                self._file = open(self._log_path, "a", encoding="utf-8")
            self._file.write(msg)
            self._file.flush()
        except Exception:
            pass
    def flush(self):
        try:
            if self._file:
                self._file.flush()
        except Exception:
            pass

if sys.stdout is None:
    sys.stdout = _Logger(_log_path)
if sys.stderr is None:
    sys.stderr = _Logger(_log_path)

try:
    from video_generator.app import main
    main()
except Exception as e:
    try:
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[FATAL] {e}\n")
            import traceback
            traceback.print_exc(file=f)
    except Exception:
        pass
