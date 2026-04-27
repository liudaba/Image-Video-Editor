# -*- coding: utf-8 -*-
"""
视频生成任务 - 关键Bug修复脚本
自动修复以下问题：
1. render_video_threaded函数致命逻辑错误（清空已加载的分镜数据）
2. Image.open资源泄漏风险
3. GPU检测缺少详细日志
4. 图像生成队列大小过小
5. CompositeVideoClip缺少异常保护
"""

import re
import os

def fix_render_video_threaded_bug():
    """修复render_video_threaded中清空分镜数据的bug"""
    print("=" * 60)
    print("修复1: render_video_threaded空数据bug")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找需要删除的代码段
    # 从 "self.shots_data = []" 到 "self.log("✅ 旧数据已清除，开始生成分镜...")"
    pattern = r'(                    else:\s+# 没有分镜脚本文件，生成新的\s+self\._generate_shots_data\(\))\s+self\.shots_data = \[\]\s+if hasattr\(self, \'_pregenerated_prompts\'\):\s+delattr\(self, \'_pregenerated_prompts\'\)\s+if hasattr\(self, \'_shot_texts_for_context\'\):\s+delattr\(self, \'_shot_texts_for_context\'\)\s+# 删除旧的分镜脚本文件\s+shots_file = os\.path\.join\(self\.output_dir, "shots_data\.json"\)\s+if os\.path\.exists\(shots_file\):\s+os\.remove\(shots_file\)\s+self\.log\("   🗑️ 已删除旧的shots_data\.json"\)\s+# 清除音频分析缓存，强制重新转录\s+self\.cache_clear\(\)\s+try:\s+prompt_cache\.clear\(\)\s+except Exception:\s+pass\s+try:\s+image_cache\.clear\(\)\s+except Exception:\s+pass\s+# 重置状态管理器\s+try:\s+if hasattr\(self, \'state_manager\'\) and isinstance\(self\.state_manager, dict\):\s+self\.state_manager\[\'shots\'\] = \{\s+\'generated\': False,\s+\'count\': 0,\s+\'data\': \[\]\s+\}\s+except Exception:\s+pass\s+self\.log\("✅ 旧数据已清除，开始生成分镜\.\.\."\)'
    
    replacement = r'\1'
    
    if re.search(pattern, content):
        new_content = re.sub(pattern, replacement, content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ 已删除错误的清空数据代码")
        print("   说明: render_video_threaded现在会正确使用已有的分镜脚本")
        return True
    else:
        print("⚠️ 未找到需要修复的代码模式")
        print("   可能已经修复或代码结构不同")
        return False


def fix_image_open_resource_leak():
    """修复Image.open资源泄漏"""
    print("\n" + "=" * 60)
    print("修复2: Image.open资源泄漏")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed_count = 0
    
    # 查找所有Image.open但没有with语句的地方
    for i in range(len(lines)):
        line = lines[i]
        # 匹配 Image.open 但没有 with 的情况
        if 'Image.open(' in line and 'with ' not in line and 'orig_img = Image.open' in line:
            # 检查下一行是否使用了这个变量
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if '_resize_image_to_fit' in next_line or 'img =' in next_line:
                    # 找到需要修复的位置
                    indent = len(line) - len(line.lstrip())
                    
                    # 修改为with语句
                    lines[i] = ' ' * indent + 'with Image.open(image_path) as orig_img:\n'
                    lines[i + 1] = ' ' * (indent + 4) + next_line.lstrip()
                    
                    fixed_count += 1
                    print(f"✅ 修复第 {fixed_count} 处 Image.open 资源泄漏")
                    print(f"   位置: 第 {i + 1} 行")
    
    if fixed_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print(f"\n✅ 共修复 {fixed_count} 处 Image.open 资源泄漏")
        return True
    else:
        print("⚠️ 未找到需要修复的Image.open")
        return False


def fix_gpu_detection_logging():
    """修复GPU检测缺少日志的问题"""
    print("\n" + "=" * 60)
    print("修复3: GPU检测缺少详细日志")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 查找GPU检测的异常处理
    old_pattern = r'(            try:\s+import torch\s+import subprocess\s+if torch\.cuda\.is_available\(\):\s+result = subprocess\.run\(\[\'ffmpeg\', \'-encoders\'\], capture_output=True, text=True\)\s+if \'h264_nvenc\' in result\.stdout:\s+use_gpu = True\s+self\.log\(f"⚡ 使用GPU加速渲染 \(h264_nvenc\)"\)\s+self\.log\(f"   📊 编码器预设: preset=\'{gpu_preset}\' \(质量优先\)"\)\s+)except Exception:\s+pass'
    
    new_replacement = r'\1except Exception as e:\n                self.log(f"⚠️ GPU检测失败: {type(e).__name__} - {str(e)[:100]}")\n                use_gpu = False'
    
    if re.search(old_pattern, content):
        new_content = re.sub(old_pattern, new_replacement, content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print("✅ 已添加GPU检测详细日志")
        print("   说明: GPU检测失败时会记录具体错误信息")
        return True
    else:
        print("⚠️ 未找到需要修复的GPU检测代码")
        return False


def fix_queue_size():
    """增大图像生成队列大小"""
    print("\n" + "=" * 60)
    print("修复4: 增大图像生成队列大小")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 替换队列大小
    replacements = [
        ('result_queue = queue.Queue(maxsize=2)', 'result_queue = queue.Queue(maxsize=16)'),
        ('save_queue = queue.Queue(maxsize=4)', 'save_queue = queue.Queue(maxsize=8)'),
    ]
    
    fixed_count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            fixed_count += 1
            print(f"✅ {old} → {new}")
    
    if fixed_count > 0:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n✅ 共修改 {fixed_count} 处队列大小")
        print("   说明: 提高预取流水线并行度，减少IO等待")
        return True
    else:
        print("⚠️ 未找到需要修改的队列配置")
        return False


def fix_composite_clip_exception():
    """为CompositeVideoClip添加异常保护"""
    print("\n" + "=" * 60)
    print("修复5: CompositeVideoClip异常保护")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    fixed = False
    
    for i in range(len(lines)):
        line = lines[i]
        if 'background = ColorClip(size=(width, height)' in line:
            # 检查前一行是否有try
            has_try = False
            if i > 0 and 'try:' in lines[i-1]:
                has_try = True
            
            if not has_try:
                # 在ColorClip前添加try
                indent = len(line) - len(line.lstrip())
                lines.insert(i, ' ' * indent + 'try:\n')
                
                # 查找CompositeVideoClip行并添加异常处理
                for j in range(i, min(i + 10, len(lines))):
                    if 'final_clip = CompositeVideoClip' in lines[j]:
                        # 在这行后面添加except
                        clip_indent = len(lines[j]) - len(lines[j].lstrip())
                        except_block = [
                            ' ' * clip_indent + 'except Exception as e:\n',
                            ' ' * (clip_indent + 4) + 'self.log(f"❌ 视频片段合成失败: {type(e).__name__} - {str(e)[:200]}")\n',
                            ' ' * (clip_indent + 4) + 'self.update_task_progress("就绪")\n',
                            ' ' * (clip_indent + 4) + 'return\n',
                        ]
                        
                        # 找到下一个非缩进行
                        insert_pos = j + 1
                        while insert_pos < len(lines):
                            next_line = lines[insert_pos]
                            if next_line.strip() and not next_line.startswith(' ' * (clip_indent + 4)):
                                break
                            insert_pos += 1
                        
                        for k, exc_line in enumerate(except_block):
                            lines.insert(insert_pos + k, exc_line)
                        
                        fixed = True
                        print(f"✅ 已为CompositeVideoClip添加异常保护")
                        print(f"   位置: 第 {i + 1} 行附近")
                        break
                
                break
    
    if fixed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return True
    else:
        print("⚠️ 未找到需要添加保护的CompositeVideoClip")
        return False


def integrate_optimization_module():
    """集成优化模块到主程序"""
    print("\n" + "=" * 60)
    print("修复6: 集成优化模块到主程序")
    print("=" * 60)
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已经导入
    if 'from video_generator.optimization import' in content:
        print("✅ 优化模块已经导入")
        return True
    
    # 在Config类定义后添加导入
    insert_marker = "# ============ 预编译正则表达式 ============"
    
    if insert_marker in content:
        import_statement = """# ============ 性能优化模块导入 ============
from video_generator.optimization import (
    ProgressManager,
    ResourceManager,
    BatchImageLoader,
    VideoRendererOptimizer
)

"""
        content = content.replace(insert_marker, import_statement + insert_marker)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("✅ 已添加优化模块导入")
        print("   说明: 现在可以使用ProgressManager、ResourceManager等优化类")
        return True
    else:
        print("⚠️ 未找到合适的插入位置")
        return False


def main():
    """执行所有修复"""
    print("\n" + "=" * 60)
    print("视频生成任务 - Bug修复脚本")
    print("=" * 60)
    print("\n开始修复...\n")
    
    fixes = [
        ("render_video_threaded空数据bug", fix_render_video_threaded_bug),
        ("Image.open资源泄漏", fix_image_open_resource_leak),
        ("GPU检测缺少日志", fix_gpu_detection_logging),
        ("图像生成队列大小", fix_queue_size),
        ("CompositeVideoClip异常保护", fix_composite_clip_exception),
        ("集成优化模块", integrate_optimization_module),
    ]
    
    success_count = 0
    skip_count = 0
    
    for name, fix_func in fixes:
        try:
            result = fix_func()
            if result:
                success_count += 1
            else:
                skip_count += 1
        except Exception as e:
            print(f"❌ {name} 修复失败: {e}")
            import traceback
            traceback.print_exc()
            skip_count += 1
    
    print("\n" + "=" * 60)
    print("修复完成汇总")
    print("=" * 60)
    print(f"✅ 成功修复: {success_count} 项")
    print(f"⚠️ 跳过/未找到: {skip_count} 项")
    print(f"📊 总计: {len(fixes)} 项")
    print("=" * 60)
    
    if success_count > 0:
        print("\n💡 下一步:")
        print("1. 运行语法检查: python -m py_compile \"My-Video Generator.py\"")
        print("2. 如果没有错误，可以启动程序测试")
        print("3. 观察日志输出，确认修复生效")
    
    return success_count


if __name__ == "__main__":
    main()
