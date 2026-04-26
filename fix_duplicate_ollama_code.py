# -*- coding: utf-8 -*-
"""
自动修复Bug 5和7的脚本 - 清理重复的Ollama启动代码
"""

import re

def fix_duplicate_code():
    """修复My-Video Generator.py中的重复代码"""
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找并删除重复的代码块（L8271-8283）
    # 模式：从 "except ImportError:" 到下一个 "# 只有连接成功后才使用大模型分析"
    pattern = r'(                except ImportError:\s+self\.log\("⚠️ Ollama未安装.*?)(                    # 只有连接成功后才使用大模型分析)'
    
    replacement = r'\2'
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("✅ 成功删除重复代码")
    else:
        print("⚠️ 未找到需要删除的重复代码")
    
    # 修复L1740的孤立try语句
    pattern2 = r'(        except Exception as e:\s+self\.log\(f"⚠️ Ollama连接失败: \{type\(e\)\.__name__\}"\))\s+try:\s+self\.log\("⚠️ 尝试启动Ollama服务"\).*?(?=        def |\n\n\n|\Z)'
    
    replacement2 = r'\1'
    
    new_content2 = re.sub(pattern2, replacement2, new_content, flags=re.DOTALL)
    
    if new_content2 != new_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content2)
        print("✅ 成功删除孤立的try-except块")
    else:
        print("⚠️ 未找到孤立的try-except块")

if __name__ == "__main__":
    fix_duplicate_code()
    print("\n修复完成！请运行 get_problems 验证")
