#!/usr/bin/env python3
"""VideoGenerator 启动入口（控制台模式）"""
import sys
import os

# 确保项目根目录在 sys.path 中
app_dir = os.path.dirname(os.path.abspath(__file__))
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

from video_generator.app import main

if __name__ == "__main__":
    main()
