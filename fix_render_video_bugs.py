# -*- coding: utf-8 -*-
"""
跑图生成视频任务 - Bug修复脚本
自动修复render_video_threaded、generate_video、generate_images函数中的bug
"""

import re

def fix_render_video_bugs():
    """修复跑图生成视频相关的所有bug"""
    
    file_path = r"c:\Users\Administrator\Desktop\短视频生成器\My-Video Generator.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Bug 1: GPU检测异常处理缺少日志
    old_gpu_check = """            except Exception:
                # TODO: 添加错误日志
                pass"""
    
    new_gpu_check = """            except Exception as e:
                self.log(f"⚠️ GPU检测失败: {type(e).__name__} - {str(e)[:100]}")
                use_gpu = False"""
    
    if old_gpu_check in content:
        content = content.replace(old_gpu_check, new_gpu_check)
        print("✅ Bug 1 已修复: GPU检测异常日志")
    else:
        print("⚠️ Bug 1 代码未找到，可能已修复")
    
    # Bug 2: Image.open资源泄漏
    old_image_open = """                image_path = os.path.join(self.images_dir, shot['image_file'])
                if os.path.exists(image_path):
                    from PIL import Image
                    orig_img = Image.open(image_path)
                    
                    # 调整图片尺寸
                    img = self._resize_image_to_fit(orig_img, width, height)"""
    
    new_image_open = """                image_path = os.path.join(self.images_dir, shot['image_file'])
                if os.path.exists(image_path):
                    from PIL import Image
                    with Image.open(image_path) as orig_img:
                        # 调整图片尺寸（使用copy避免原始图像被修改）
                        img = self._resize_image_to_fit(orig_img.copy(), width, height)"""
    
    if old_image_open in content:
        content = content.replace(old_image_open, new_image_open)
        print("✅ Bug 2 已修复: Image.open资源泄漏")
    else:
        print("⚠️ Bug 2 代码未找到，可能已修复")
    
    # Bug 6: CompositeVideoClip异常处理
    old_composite = """            background = ColorClip(size=(width, height), color=(0, 0, 0), duration=audio_duration)
            final_clip = CompositeVideoClip([background] + clips, size=(width, height))
            
            self.log(f"✅ 视频片段合成完成: {len(clips)} 个")"""
    
    new_composite = """            try:
                background = ColorClip(size=(width, height), color=(0, 0, 0), duration=audio_duration)
                final_clip = CompositeVideoClip([background] + clips, size=(width, height))
                self.log(f"✅ 视频片段合成完成: {len(clips)} 个")
            except Exception as e:
                self.log(f"❌ 视频片段合成失败: {type(e).__name__} - {str(e)[:200]}")
                self.update_task_progress("就绪")
                return"""
    
    if old_composite in content:
        content = content.replace(old_composite, new_composite)
        print("✅ Bug 6 已修复: CompositeVideoClip异常处理")
    else:
        print("⚠️ Bug 6 代码未找到，可能已修复")
    
    # Bug 4: 音频文件检查改进
    old_audio_check = """            # 再次检查音频文件（可能在图片生成期间被删除或移动）
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   音频文件可能在图片生成期间被移动或删除")
                self.log("   请重新导入音频文件")
                self.update_task_progress("就绪")
                return"""
    
    new_audio_check = """            # 再次检查音频文件（可能在图片生成期间被删除或移动）
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   音频文件可能在图片生成期间被移动或删除")
                self.log("   请重新导入音频文件")
                self.update_task_progress("就绪")
                # 在主线程显示错误提示
                if hasattr(self, 'root') and self.root:
                    def show_error():
                        from tkinter import messagebox
                        messagebox.showerror("音频文件缺失", 
                                           f"音频文件已丢失，请重新导入：\\n{self.audio_path}")
                    self.root.after(0, show_error)
                return"""
    
    if old_audio_check in content:
        content = content.replace(old_audio_check, new_audio_check)
        print("✅ Bug 4 已修复: 音频文件检查改进")
    else:
        print("⚠️ Bug 4 代码未找到，可能已修复")
    
    # Bug 5: 视频片段边界检查改进
    old_boundary_check = """                    # 边界检查：时长无效时跳过此片段
                    if shot_duration <= 0:
                        self.log(f"⚠️ 分镜时间戳无效，跳过: {shot.get('image_file', '未知')}")
                        continue"""
    
    new_boundary_check = """                    # 边界检查：时长无效时跳过此片段
                    if shot_duration <= 0:
                        self.log(f"⚠️ 分镜时间戳无效，跳过: {shot.get('image_file', '未知')} (start={shot['start']:.2f}s, end={shot['end']:.2f}s)")
                        continue"""
    
    if old_boundary_check in content:
        content = content.replace(old_boundary_check, new_boundary_check)
        print("✅ Bug 5 已修复: 视频片段边界检查改进")
    else:
        print("⚠️ Bug 5 代码未找到，可能已修复")
    
    # 保存修复后的内容
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("\n" + "="*60)
    print("修复完成！请运行以下命令验证:")
    print('  python -m py_compile "My-Video Generator.py"')
    print("="*60)

if __name__ == "__main__":
    fix_render_video_bugs()
