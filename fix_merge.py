import re

# Read the file
with open(r'c:\Users\Administrator\Desktop\短视频生成器\video_generator_merged.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken module headers
# Pattern: # =====...# 模块: xxx# ======\nxxx
content = re.sub(
    r'(# =+\{10,12\})# 模块: (\w+)# =\1\n+(\w+)',
    r'\1\n"""Module: \2"""\n',
    content
)

# Also fix the ones that have Chinese after # ===== 
content = re.sub(
    r'(# =+\{10,12\})([^\n#]+)(# =+\{10,12\})\n+([^\n#]+)',
    r'\1\n"""Module: \2"""\n',
    content
)

# Write back
with open(r'c:\Users\Administrator\Desktop\短视频生成器\video_generator_merged.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
