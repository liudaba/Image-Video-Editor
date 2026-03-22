import re

with open(r'c:\Users\Administrator\Desktop\短视频生成器\video_generator_merged.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all module headers and fix them
# Pattern: # ===...# 模块: xxx# ===...\n中文\n"""
def fix_modules(text):
    # Pattern 1: # =...# 模块: xxx# =...\n中文\n"""
    pattern1 = r'(# ={30,})# 模块: (\w+)# =\1\n([^\n#]+)\n"""'
    text = re.sub(pattern1, r'\1\n# Module: \2\n\1\n"""Module: \2"""', text)
    
    # Pattern 2: # =...# 模块: xxx\n中文\n"""
    pattern2 = r'(# ={30,})# 模块: (\w+)\n([^\n#]+)\n"""'
    text = re.sub(pattern2, r'\1\n# Module: \2\n\1\n"""Module: \2"""', text)
    
    return text

content = fix_modules(content)

with open(r'c:\Users\Administrator\Desktop\短视频生成器\video_generator_merged.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
