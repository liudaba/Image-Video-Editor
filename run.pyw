# -*- coding: utf-8 -*-
"""短视频生成器 - 无控制台窗口启动入口

使用 pythonw.exe 运行此文件，不会显示命令提示符黑框。
双击"启动.vbs"即可无黑框启动。
"""
import sys
import os

sys.stdout = open(os.devnull, 'w', encoding='utf-8', errors='replace')
sys.stderr = open(os.devnull, 'w', encoding='utf-8', errors='replace')

from video_generator.app import main

if __name__ == "__main__":
    main()
