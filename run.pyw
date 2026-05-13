# -*- coding: utf-8 -*-
"""短视频生成器 - 无控制台窗口启动入口

使用 pythonw.exe 运行此文件，不会显示命令提示符黑框。
双击"启动.vbs"即可无黑框启动。
"""
import sys
import os
import traceback

_err_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_pythonw_error.log")

try:
    from video_generator.app import main

    if __name__ == "__main__":
        main()
except SystemExit:
    pass
except BaseException:
    try:
        with open(_err_log, "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    except Exception:
        pass
