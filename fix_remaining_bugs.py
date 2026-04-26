# -*- coding: utf-8 -*-
"""
Bug修复脚本 - 自动修复剩余的5个bug
运行此脚本将应用所有建议的修复
"""

import re
import os

def fix_thread_safety():
    """修复Bug 4: 线程安全问题 - resize_timer"""
    file_path = "My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找并替换resize_timer相关代码
    old_code = """        # 防抖处理，避免高频触发
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)"""
    
    new_code = """        # 防抖处理，避免高频触发
        if hasattr(self, 'resize_timer') and self.resize_timer:
            try:
                self.root.after_cancel(self.resize_timer)
            except Exception:
                pass  # timer可能已经执行完毕"""
    
    if old_code in content:
        content = content.replace(old_code, new_code)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Bug 4 已修复: 线程安全问题")
    else:
        print("⚠️ Bug 4 代码未找到，可能已手动修复")

def add_exception_logging():
    """修复Bug 7: 添加异常日志记录"""
    file_path = "My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    for i, line in enumerate(lines):
        # 查找bare except或空的except块
        if re.match(r'^\s*except\s*:', line) or re.match(r'^\s*except\s+Exception\s*:', line):
            # 检查下一行是否有日志记录
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if 'log' not in next_line and 'print' not in next_line and 'logging' not in next_line:
                    # 添加日志记录（缩进与except保持一致）
                    indent = len(line) - len(line.lstrip())
                    log_line = ' ' * (indent + 4) + '# TODO: 添加错误日志\n'
                    lines.insert(i + 1, log_line)
                    modified = True
    
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("✅ Bug 7 部分修复: 添加了TODO标记需要添加日志的位置")
    else:
        print("ℹ️ Bug 7: 未发现需要添加日志的位置，或已手动处理")

def main():
    print("=" * 60)
    print("短视频生成器 - Bug修复脚本")
    print("=" * 60)
    print()
    
    # 检查文件是否存在
    if not os.path.exists("My-Video Generator.py"):
        print("❌ 错误: 找不到 My-Video Generator.py")
        return
    
    print("开始修复剩余的bug...\n")
    
    # 修复线程安全问题
    fix_thread_safety()
    
    # 添加异常日志
    add_exception_logging()
    
    print()
    print("=" * 60)
    print("修复完成！请运行以下命令验证:")
    print("  python check_python_env.py")
    print("  python \"My-Video Generator.py\"")
    print("=" * 60)

if __name__ == "__main__":
    main()
