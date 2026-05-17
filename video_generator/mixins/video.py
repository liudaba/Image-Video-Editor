"""Video rendering mixin - moviepy composition, animation effects."""
import os
import sys
import json
import time
import gc
import datetime
import traceback
import threading
from video_generator.mixins.logging import safe_print_exc
from video_generator.config import validate_image_size, Config
from video_generator.config import get_http_session
from video_generator.cache import prompt_cache, image_cache
import subprocess
import tempfile
import shutil
import numpy as np
import tkinter as tk
from tkinter import messagebox
from concurrent.futures import ThreadPoolExecutor

class VideoMixin:
    def generate_video(self, skip_clear=False, use_original_resolution=False, skip_image_check=False):
        """生成视频
        
        Args:
            skip_clear: 是否跳过清除旧文件（跑图模式设为True）
            use_original_resolution: 是否使用原始图片分辨率
            skip_image_check: 是否跳过图片检查（直接渲染模式设为True）
        """
        self.log("=" * 60)
        self.log("🎞️ 开始生成视频...")
        self.log("=" * 60)
        
        _video_start_time = time.time()
        
        audio = None
        final_clip = None
        background = None
        clips = []
        intermediate_clips = []
        
        def check_cancelled():
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return True
            if not self.pause_event.is_set():
                self.log("⏸️ 任务已暂停")
                self.pause_event.wait(timeout=5)
                if not self.pause_event.is_set() and not self.task_running:
                    return True
            return False
        
        try:
            from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip, ColorClip, vfx
            
            # 步骤1: 准备阶段
            self.update_task_progress("正在准备...", 10)
            self.log("\n📍 步骤 1/10: 准备工作")
            
            if check_cancelled():
                return
            
            # 步骤2: 清理旧文件（可选）
            if not skip_clear:
                self.update_task_progress("正在清理旧文件...", 15)
                self.log("\n📍 步骤 2/10: 清理旧文件")
                self.clear_images_and_videos()
                self.log("   ✅ 旧文件清理完成")
            
            if check_cancelled():
                return
            
            # 步骤3: 加载分镜数据
            self.update_task_progress("正在加载分镜数据...", 20)
            self.log("\n📍 步骤 3/10: 加载分镜数据")
            if not self.shots_data:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            loaded = json.load(f)
                        with self.resource_lock:
                            self.shots_data = loaded
                        self.log(f"   📂 从文件加载分镜数据: {len(self.shots_data)} 个")
                    except (json.JSONDecodeError, Exception) as e:
                        self.log(f"   ⚠️ 分镜数据文件损坏，请重新生成分镜")
                        self.shots_data = []
                else:
                    self.log("❌ 没有分镜数据，请先生成分镜")
                    self.update_task_progress("就绪")
                    return
            else:
                self.log(f"   ✅ 使用内存中的分镜数据: {len(self.shots_data)} 个")
            
            # 步骤4: 检查音频文件
            self.update_task_progress("正在检查音频文件...", 25)
            self.log("\n📍 步骤 4/10: 检查音频文件")
            if not self.audio_path:
                self.log("❌ 没有音频文件，请先导入音频")
                self.update_task_progress("就绪")
                return
            
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   请重新导入音频文件")
                self.update_task_progress("就绪")
                return
            self.log(f"   ✅ 音频文件存在: {os.path.basename(self.audio_path)}")
            
            # 步骤5: 检查并补充图片
            if skip_image_check:
                self.update_task_progress("跳过图片检查", 30)
                self.log("\n📍 步骤 5/10: 跳过图片检查（直接使用现有图片）")
            else:
                self.update_task_progress("正在检查图片...", 30)
                self.log("\n📍 步骤 5/10: 检查并补充图片")
                missing_count = sum(1 for shot in self.shots_data 
                                   if not os.path.exists(os.path.join(self.images_dir, shot['image_file'])))
                
                if missing_count > 0:
                    self.log(f"   ⚠️ 检测到 {missing_count} 张图片缺失，开始生成...")
                    self.log("   🔄 正在调用图像生成模块...")
                    
                    # 记录开始时间
                    img_start_time = time.time()
                    
                    self.generate_images()
                    
                    # 记录耗时
                    img_elapsed = time.time() - img_start_time
                    self.log(f"   ✅ 图像生成流程完成 (耗时: {img_elapsed:.1f}s)")
                    
                    # 再次检查
                    missing_count = sum(1 for shot in self.shots_data 
                                       if not os.path.exists(os.path.join(self.images_dir, shot['image_file'])))
                    if missing_count > 0:
                        missing_files = [shot['image_file'] for shot in self.shots_data 
                                        if not os.path.exists(os.path.join(self.images_dir, shot['image_file']))]
                        self.log(f"   ❌ 仍有 {missing_count} 张图片缺失，无法生成视频")
                        self.log(f"      缺失的图片: {missing_files[:5]}")
                        if len(missing_files) > 5:
                            self.log(f"      ... 还有 {len(missing_files) - 5} 张")
                        self.update_task_progress("就绪")
                        return
                    else:
                        self.log("   ✅ 所有图片已补全")
                else:
                    self.log("   ✅ 所有图片已存在，跳过生成步骤")

            if check_cancelled():
                return
            
            # 步骤6: 加载音频
            self.update_task_progress("正在加载音频...", 35)
            self.log("\n📍 步骤 6/10: 加载音频文件")
            
            audio = AudioFileClip(self.audio_path)
            audio_duration = audio.duration
            self._active_audio = audio
            self.log(f"   ✅ 音频加载成功，时长: {audio_duration:.2f}s")
            
            # 验证时间轴（只显示信息，不修改原始时间戳）
            self.update_task_progress("正在验证时间轴...", 40)
            self.log("\n📍 步骤 7/10: 验证时间轴")
            total_shots_duration = 0
            has_gaps = False
            has_overlap = False
            total_gaps = 0
            total_overlap = 0
            for i, shot in enumerate(self.shots_data):
                expected_duration = shot['end'] - shot['start']
                shot['duration'] = expected_duration
                total_shots_duration += expected_duration
                if i > 0:
                    gap = shot['start'] - self.shots_data[i-1]['end']
                    if gap > 0.05:
                        has_gaps = True
                        total_gaps += gap
                    elif gap < 0:
                        has_overlap = True
                        total_overlap += abs(gap)
            
            self.log(f"   📊 音频时长: {audio_duration:.2f}s, 分镜总时长: {total_shots_duration:.2f}s")
            
            if total_gaps > 0:
                self.log(f"      ⏱️ 时间间隔: {total_gaps:.2f}s")
            if total_overlap > 0:
                self.log(f"      ⚠️ 时间重叠: {total_overlap:.2f}s")
            
            if has_gaps:
                self.log("      ⚠️ 检测到时间间隔，使用精确定位模式")
            elif has_overlap:
                self.log("      ⚠️ 检测到时间重叠，使用精确定位模式")
            else:
                self.log("      ✅ 时间戳连续，使用精确定位模式")
            
            self.log("      📍 保持原始语音时间戳，确保音画同步")
            
            if check_cancelled():
                return
            
            # 步骤8: 准备视频片段
            self.update_task_progress("正在准备视频片段...", 45)
            self.log("\n📍 步骤 8/10: 准备视频片段")
            
            # 获取用户选择的动画效果
            animation_type = self.animation_var.get() if hasattr(self, 'animation_var') else "无"
            transition_type = self.transition_var.get() if hasattr(self, 'transition_var') else "硬切"
            self.log(f"   🎬 动画效果: {animation_type}")
            self.log(f"   🎬 过渡效果: {transition_type}")
            
            # 获取视频分辨率
            width, height = validate_image_size(
                self.width_var.get() if hasattr(self, 'width_var') else '1920',
                self.height_var.get() if hasattr(self, 'height_var') else '1080',
                default_w=1920, default_h=1080
            )
            self.log(f"   📐 视频分辨率: {width}x{height}")
            
            self.log("      📍 保持原始语音时间戳，确保音画同步")
            
            if check_cancelled():
                return
            
            # ========== 快速路径: 无动画+硬切 → FFmpeg直接渲染 ==========
            if self.video_renderer is None:
                try:
                    from video_generator.hardware import HardwareAcceleratedRenderer
                    self.video_renderer = HardwareAcceleratedRenderer()
                except Exception:
                    self.video_renderer = None
            
            use_ffmpeg_direct = (
                animation_type == "无" and
                transition_type == "硬切" and
                not has_overlap and
                self.video_renderer is not None
            )
            
            if use_ffmpeg_direct:
                self.log("")
                self.log("⚡ 检测到简单场景（无动画/硬切），启用FFmpeg直接渲染模式")
                self.log("   🚀 跳过moviepy，由FFmpeg原生处理，速度大幅提升")
                
                try:
                    from PIL import Image as PILImageForResize
                    
                    temp_render_dir = tempfile.mkdtemp(prefix="vg_render_")
                    try:
                        resized_images = []
                        shot_durations = []
                        
                        prev_end = 0.0
                        for shot in self.shots_data:
                            image_path = os.path.join(self.images_dir, shot['image_file'])
                            if not os.path.exists(image_path):
                                self.log(f"   ⚠️ 图片缺失: {shot['image_file']}")
                                continue
                            
                            shot_dur = shot['end'] - shot['start']
                            gap = shot['start'] - prev_end
                            if gap > 0.05:
                                shot_dur += gap
                            
                            resized_name = f"resized_{len(resized_images):04d}.jpg"
                            resized_path = os.path.join(temp_render_dir, resized_name)
                            
                            with PILImageForResize.open(image_path) as orig_img:
                                fitted = self._resize_image_to_fit(orig_img, width, height)
                                fitted.save(resized_path, 'JPEG', quality=95)
                            
                            resized_images.append(resized_path)
                            shot_durations.append(shot_dur)
                            prev_end = shot['end']
                        
                        if not resized_images:
                            self.log("❌ 没有可用的图片文件")
                            self.update_task_progress("就绪")
                            return
                        
                        self.update_task_progress("正在渲染视频...", 60)
                        self.log(f"\n🎥 开始FFmpeg直接渲染...")
                        self.log(f"   📊 {len(resized_images)} 张图片, 总时长 {sum(shot_durations):.1f}s")
                        
                        output_path = os.path.join(self.output_dir, f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
                        
                        _ffmpeg_render_start = time.time()
                        
                        _ffmpeg_last_log_pct = [-1]
                        def _ffmpeg_progress(pct, info=None):
                            progress = 60 + int(pct * 0.35)
                            _log_pct = int(pct // 10) * 10
                            if _log_pct > _ffmpeg_last_log_pct[0] and _log_pct > 0:
                                _ffmpeg_last_log_pct[0] = _log_pct
                                self.log(f"   📊 渲染进度: {_log_pct}%")
                            if info:
                                time_str = f"{int(info.get('current_time', 0)//60):02d}:{int(info.get('current_time', 0)%60):02d}"
                                total_str = f"{int(info.get('total_time', 0)//60):02d}:{int(info.get('total_time', 0)%60):02d}"
                                desc = f"FFmpeg渲染 {pct:.0f}% ({time_str}/{total_str})"
                                eta = info.get('eta')
                                if eta and eta > 0:
                                    eta_min = int(eta // 60)
                                    eta_sec = int(eta % 60)
                                    desc += f" 剩余{eta_min}:{eta_sec:02d}"
                                self.update_task_progress(desc, progress)
                            else:
                                self.update_task_progress(f"FFmpeg渲染中 {pct:.0f}%", progress)
                        
                        def _ffmpeg_log(msg):
                            pass
                        
                        success = self.video_renderer.render(
                            resized_images, self.audio_path, output_path,
                            fps=30, shot_durations=shot_durations,
                            progress_callback=_ffmpeg_progress,
                            log_callback=_ffmpeg_log
                        )
                        
                        if success:
                            _video_elapsed = time.time() - _video_start_time
                            _video_min = int(_video_elapsed // 60)
                            _video_sec = int(_video_elapsed % 60)
                            self.update_task_progress("视频生成完成", 100)
                            self.log(f"✅ 视频生成完成！耗时{_video_min}分{_video_sec}秒")
                            self.log(f"   📁 {output_path}")
                            
                            self.state_manager['video']['generated'] = True
                            self.state_manager['video']['path'] = output_path
                            
                            self.task_running = False
                            self.log("\n📂 打开输出文件夹...")
                            self._open_folder(os.path.dirname(output_path))
                            return
                        else:
                            self.log("⚠️ FFmpeg直接渲染失败，回退到moviepy渲染...")
                    finally:
                        shutil.rmtree(temp_render_dir, ignore_errors=True)
                
                except Exception as e:
                    self._log_exception(f"⚠️ FFmpeg直接渲染异常: {type(e).__name__}", e)
                    self.log("   🔄 回退到moviepy渲染...")
            
            # 步骤9: 创建视频片段（多线程批量加载图片）
            self.update_task_progress("正在创建视频片段...", 50)
            self.log("\n📍 步骤 9/10: 创建视频片段")
            clips = []
            total_shots = len(self.shots_data)
            
            self.log(f"   📊 共 {total_shots} 个分镜需要处理...")
            
            from PIL import Image as PILImage
            
            def _load_and_resize_single(shot_item):
                shot, w, h = shot_item
                image_path = os.path.join(self.images_dir, shot['image_file'])
                if not os.path.exists(image_path):
                    return (shot, None)
                try:
                    with PILImage.open(image_path) as orig_img:
                        img = self._resize_image_to_fit(orig_img, w, h)
                    return (shot, img)
                except Exception:
                    return (shot, None)
            
            load_batch_size = min(16, total_shots)
            self.log(f"   ⚡ 多线程加载: {load_batch_size}线程并行预加载图片")
            
            shot_img_map = {}
            load_start = time.time()
            with ThreadPoolExecutor(max_workers=load_batch_size) as loader_pool:
                load_tasks = [(shot, width, height) for shot in self.shots_data]
                for shot, img in loader_pool.map(_load_and_resize_single, load_tasks):
                    if img is not None:
                        shot_img_map[shot['image_file']] = img
                    else:
                        self.log(f"      ⚠️ 图片缺失: {shot['image_file']}")
            
            load_elapsed = time.time() - load_start
            self.log(f"   ✅ 图片预加载完成: {len(shot_img_map)}/{total_shots} 张 (耗时 {load_elapsed:.1f}s)")
            
            processed_shots = 0
            intermediate_clips = []
            clips = []
            for shot in self.shots_data:
                if check_cancelled():
                    # 修复：同时清理 clips 和 intermediate_clips
                    for img in shot_img_map.values():
                        try: img.close()
                        except Exception: pass
                    shot_img_map.clear()
                    for ic in intermediate_clips:
                        try: ic.close()
                        except Exception: pass
                    for c in clips:
                        try: c.close()
                        except Exception: pass
                    return
                
                processed_shots += 1
                progress = 50 + int((processed_shots / total_shots) * 10)
                if processed_shots % 5 == 0 or processed_shots == total_shots:
                    self.update_task_progress(f"正在创建视频片段 ({processed_shots}/{total_shots})...", progress)
                
                img = shot_img_map.get(shot['image_file'])
                if img is None:
                    continue
                
                shot_duration = shot['end'] - shot['start']
                if shot_duration <= 0:
                    self.log(f"      ⚠️ 分镜时间戳无效，跳过: {shot.get('image_file', '未知')}")
                    try: img.close()
                    except Exception: pass
                    continue
                
                clip = ImageClip(np.array(img)).with_duration(shot_duration)
                
                try:
                    img.close()
                except Exception:
                    pass
                
                if animation_type != "无":
                    old_clip = clip
                    clip = self.apply_animation_effect_prerender(clip, animation_type)
                    if clip is not old_clip:
                        intermediate_clips.append(old_clip)
                
                if transition_type == "交叉淡化" and shot_duration > 0.6:
                    crossfade_dur = min(0.3, shot_duration * 0.15)
                    old_clip = clip
                    clip = clip.with_effects([vfx.FadeIn(crossfade_dur), vfx.FadeOut(crossfade_dur)])
                    if clip is not old_clip:
                        intermediate_clips.append(old_clip)
                
                clip = clip.with_start(shot['start'])
                clips.append(clip)
            
            if not clips:
                self.log("❌ 没有有效的图片文件")
                self.update_task_progress("就绪")
                return
            
            self.log(f"   ✅ 视频片段创建完成: {len(clips)} 个片段")
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 步骤10: 合成视频片段
            self.update_task_progress("正在合成视频...", 60)
            self.log("\n📍 步骤 10/10: 合成视频片段")
            
            first_start = self.shots_data[0]['start'] if self.shots_data else 0
            has_start_gap = first_start > 0.05
            
            if has_gaps or has_start_gap:
                if has_start_gap:
                    self.log(f"      ⚠️ 视频开头有 {first_start:.2f}s 间隔，用第一张图片填充")
                if has_gaps:
                    self.log("      ⚠️ 检测到片段间时间间隔，使用延续图片方式填充")
                
                if has_start_gap and clips:
                    first_clip = clips[0]
                    new_duration = first_clip.duration + first_clip.start
                    clips[0] = first_clip.with_duration(new_duration).with_start(0)
                
                fixed_clips = []
                prev_clip = None
                
                for i, clip in enumerate(clips):
                    if prev_clip is not None:
                        prev_end = prev_clip.start + prev_clip.duration
                        curr_start = clip.start
                        gap = curr_start - prev_end
                        
                        if gap > 0.05:
                            new_duration = prev_clip.duration + gap
                            prev_clip = prev_clip.with_duration(new_duration)
                            fixed_clips[-1] = prev_clip
                    
                    fixed_clips.append(clip)
                    prev_clip = clip
                
                clips = fixed_clips
                self.log(f"      ✅ 已修复时间间隔: {len(clips)} 个片段")
            
            try:
                background = ColorClip(size=(width, height), color=(0, 0, 0)).with_duration(audio_duration)
                final_clip = CompositeVideoClip([background] + clips, size=(width, height))
                self._active_background = background
                self._active_final_clip = final_clip
                self._active_clips = clips
                self.log(f"   ✅ 视频片段合成完成: {len(clips)} 个片段")
            except Exception as e:
                self._log_exception(f"   ❌ 视频片段合成失败: {type(e).__name__}", e)
                self.update_task_progress("就绪")
                return

            if check_cancelled():
                return
            
            # 步骤11: 添加音频
            self.update_task_progress("正在添加音频...", 65)
            self.log("\n🔊 添加音频轨道...")
            old_final_clip = final_clip
            final_clip = final_clip.with_audio(audio)
            if old_final_clip is not final_clip:
                try:
                    old_final_clip.close()
                except Exception:
                    pass
            self.log("   ✅ 音频轨道添加成功")
            
            # 步骤12: 渲染视频
            self.update_task_progress("正在渲染视频...", 70)
            self.log("\n🎥 开始渲染视频...")
            output_path = os.path.join(self.output_dir, f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            
            if not hasattr(self, '_gpu_encoder_cache'):
                self._gpu_encoder_cache = None
            
            use_gpu = False
            gpu_encoder = 'h264_nvenc'
            gpu_preset = "p4"
            
            if self._gpu_encoder_cache is not None:
                use_gpu, gpu_encoder, gpu_preset = self._gpu_encoder_cache
                if use_gpu:
                    self.log(f"   ⚡ GPU加速渲染 ({gpu_encoder})")
                else:
                    self.log(f"   🖥️ CPU渲染")
            else:
                try:
                    if self.video_renderer is None:
                        from video_generator.hardware import HardwareAcceleratedRenderer
                        self.video_renderer = HardwareAcceleratedRenderer()
                    enc_info = self.video_renderer.get_encoder_info()
                    enc_name = enc_info['encoder']
                    if enc_name != 'libx264':
                        use_gpu = True
                        gpu_encoder = enc_name
                        gpu_preset = enc_info.get('preset', 'medium')
                        hw_desc = {"h264_nvenc": "NVIDIA GPU", "h264_qsv": "Intel QuickSync", "h264_amf": "AMD AMF"}.get(enc_name, "GPU")
                        self.log(f"   ⚡ 检测到{hw_desc}加速")
                    else:
                        self.log("   🖥️ 将使用CPU渲染")
                except Exception as e:
                    self._log_exception(f"      ⚠️ 编码器检测失败: {type(e).__name__}", e)
                
                self._gpu_encoder_cache = (use_gpu, gpu_encoder, gpu_preset)
            
            if not use_gpu:
                self.log("   🖥️ CPU渲染 (libx264)")
            
            try:
                from proglog import ProgressBarLogger
                
                _moviepy_render_start = time.time()
                _moviepy_total_frames = int(audio_duration * 30)
                _moviepy_last_log_time = 0.0
                
                class _MoviePyProgressLogger(ProgressBarLogger):
                    def __init__(self, app_ref, expected_total_frames):
                        super().__init__(min_time_interval=0.5)
                        self.app = app_ref
                        self._last_progress_pct = 0.0
                        self._expected_total = expected_total_frames
                        self._video_bar = None
                        self._audio_bar = None
                    
                    def bars_callback(self, bar, attr, value, old_value=None):
                        try:
                            bar_data = self.bars.get(bar, {})
                            index = bar_data.get('index', 0)
                            total = bar_data.get('total', 0)
                            
                            if total <= 0 or attr != 'index':
                                return
                            
                            pct = (index / total) * 100
                            
                            is_video = (total >= self._expected_total * 0.5)
                            
                            if is_video:
                                if self._video_bar is None:
                                    self._video_bar = bar
                                progress_val = 70 + int((index / total) * 25)
                                phase_label = "视频编码"
                            else:
                                if self._audio_bar is None:
                                    self._audio_bar = bar
                                progress_val = 95 + int((index / total) * 5)
                                phase_label = "音频编码"
                            
                            desc = f"{phase_label} {pct:.0f}%"
                            
                            elapsed = time.time() - _moviepy_render_start
                            if pct > 5 and elapsed > 0:
                                remaining_pct = 100.0 - pct
                                eta = (remaining_pct / pct) * elapsed
                                if eta > 0:
                                    eta_min = int(eta // 60)
                                    eta_sec = int(eta % 60)
                                    desc += f" 剩余{eta_min}:{eta_sec:02d}"
                            
                            self.app.update_task_progress(desc, progress_val)
                            
                            now = time.time()
                            nonlocal _moviepy_last_log_time
                            _log_pct = int(pct // 10) * 10
                            _last_log_pct = int(getattr(self, '_last_logged_pct', -1))
                            if _log_pct > _last_log_pct and _log_pct > 0:
                                self._last_logged_pct = _log_pct
                                _moviepy_last_log_time = now
                                self.app.log(f"   📊 {phase_label}: {_log_pct}%")
                            
                            self._last_progress_pct = pct
                        except Exception:
                            pass
                    
                    def callback(self, **kw):
                        pass
                
                _moviepy_logger = _MoviePyProgressLogger(self, _moviepy_total_frames)
                
                encoder_desc = gpu_encoder if use_gpu else 'libx264'
                total_frames_desc = _moviepy_total_frames
                self.log(f"   🔄 正在渲染视频... ({encoder_desc})")
                
                if use_gpu:
                    hw_params = ['-movflags', '+faststart', '-threads', '0']
                    if gpu_encoder == 'h264_nvenc':
                        hw_params.extend(['-cq', '20', '-rc', 'vbr'])
                        try:
                            if self.video_renderer is None:
                                from video_generator.hardware import HardwareAcceleratedRenderer
                                self.video_renderer = HardwareAcceleratedRenderer()
                            nvenc_extra = self.video_renderer._build_nvenc_extra_params()
                            hw_params.extend(nvenc_extra)
                        except Exception:
                            pass
                    final_clip.write_videofile(output_path, fps=30, codec=gpu_encoder, audio_codec='aac', preset=gpu_preset, ffmpeg_params=hw_params, logger=_moviepy_logger)
                else:
                    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac', preset='medium', ffmpeg_params=['-movflags', '+faststart', '-threads', '0', '-crf', '20'], logger=_moviepy_logger)
            except Exception as e:
                if use_gpu:
                    self._log_exception(f"      ⚠️ GPU渲染失败，切换CPU", e)
                    self.log("      🖥️ 切换为CPU渲染 (libx264, preset='medium')")
                    self._gpu_encoder_cache = (False, 'libx264', 'medium')
                    try:
                        from proglog import ProgressBarLogger as _PBL2
                        _fallback_logger = _MoviePyProgressLogger(self, _moviepy_total_frames)
                    except Exception:
                        _fallback_logger = None
                    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac', preset='medium', ffmpeg_params=['-movflags', '+faststart', '-threads', '0', '-crf', '20'], logger=_fallback_logger)
                else:
                    raise
            
            # 完成
            _video_elapsed = time.time() - _video_start_time
            _video_min = int(_video_elapsed // 60)
            _video_sec = int(_video_elapsed % 60)
            _render_elapsed = time.time() - _moviepy_render_start
            file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            size_mb = file_size / (1024 * 1024)
            self.update_task_progress("视频生成完成", 100)
            self.log(f"✅ 视频生成完成！耗时{_video_min}分{_video_sec}秒, 文件{size_mb:.1f}MB")
            self.log(f"   📁 {output_path}")
            
            self.state_manager['video']['generated'] = True
            self.state_manager['video']['path'] = output_path
            
            self.log("🧹 资源已释放")
            
            self.log("\n📂 打开输出文件夹...")
            self._open_folder(os.path.dirname(output_path))
            
        except Exception as e:
            _video_elapsed = time.time() - _video_start_time
            _video_min = int(_video_elapsed // 60)
            _video_sec = int(_video_elapsed % 60)
            self.log("\n❌ 视频生成失败，请检查文件和配置是否正确")
            self.log(f"   ⏱️ 已耗时: {_video_min}分{_video_sec}秒 ({_video_elapsed:.1f}s)")
            safe_print_exc()
        finally:
            for clip in clips:
                try: clip.close()
                except Exception: pass
            for ic in intermediate_clips:
                try: ic.close()
                except Exception: pass
            if background:
                try: background.close()
                except Exception: pass
            if final_clip:
                try: final_clip.close()
                except Exception: pass
            if audio:
                try: audio.close()
                except Exception: pass
            if 'shot_img_map' in locals():
                for img in shot_img_map.values():
                    try: img.close()
                    except Exception: pass
            self._active_audio = None
            self._active_clips = None
            self._active_background = None
            self._active_final_clip = None
            with self.task_lock:
                self.task_running = False
            self._set_action_buttons_state("normal")
            try:
                gc.collect()
            except Exception:
                pass
    

    def apply_animation_effect_prerender(self, clip, animation_type="缩放"):
        """预渲染动画效果 - 使用PIL仿射变换实现亚像素级平滑插值

        支持动画类型:
        - "缩放": 缓慢放大 (Ken Burns效果, 1.0x→1.10x)

        核心优化:
        1. 预渲染放大帧，后续每帧仅做仿射变换
        2. 使用PIL Image.transform()实现亚像素级插值，消除整数截断导致的抖动
        3. 使用smoothstep缓动曲线，起止更自然
        4. BICUBIC重采样保证画面清晰

        注意：此函数返回新片段，会丢失原片段的 start 属性
              调用方必须在调用此函数后重新设置 with_start()
        """
        try:
            from moviepy import VideoClip
            from PIL import Image

            original_duration = clip.duration

            if not original_duration or original_duration <= 0:
                self.log("⚠️ 动画片段时长无效，跳过动画效果")
                return clip

            w, h = clip.size
            base_frame = clip.get_frame(0)
            base_img = Image.fromarray(base_frame)

            if animation_type == "缩放":
                max_scale = 1.10
                max_w = int(w * max_scale)
                max_h = int(h * max_scale)
                source_img = base_img.resize((max_w, max_h), Image.LANCZOS)
                source_arr = np.array(source_img)
                cached_source = Image.fromarray(source_arr)
                source_img.close()
                base_img.close()

                def make_frame(t):
                    try:
                        progress = min(t / original_duration, 1.0)
                        progress = progress * progress * (3 - 2 * progress)
                        scale = 1.0 + (max_scale - 1.0) * progress
                        crop_w = w * max_scale / scale
                        crop_h = h * max_scale / scale
                        left = (max_w - crop_w) / 2.0
                        top = (max_h - crop_h) / 2.0
                        sx = crop_w / w
                        sy = crop_h / h
                        result = cached_source.transform(
                            (w, h), Image.AFFINE,
                            (sx, 0, left, 0, sy, top),
                            Image.BICUBIC
                        )
                        arr = np.array(result)
                        result.close()
                        return arr
                    except Exception:
                        return base_frame
            else:
                base_img.close()
                return clip

            animated_clip = VideoClip(make_frame, duration=original_duration)
            _cached_ref = [cached_source]
            def _on_clip_close():
                try:
                    if _cached_ref[0] is not None:
                        _cached_ref[0].close()
                        _cached_ref[0] = None
                except Exception:
                    pass
            animated_clip.on_close = _on_clip_close
            return animated_clip
        except Exception as e:
            self._log_exception("⚠️ 预渲染动画效果失败", e)
            return clip


    def _resize_image_to_fit(self, img, target_width, target_height):
        """将图片缩放到目标尺寸，保持比例，不足部分填充黑边"""
        from PIL import Image, ImageFilter

        orig_width, orig_height = img.size
        scale_w = target_width / orig_width
        scale_h = target_height / orig_height
        scale = min(scale_w, scale_h)
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
        resized = img.resize((new_width, new_height), Image.LANCZOS)
        if new_width > orig_width or new_height > orig_height:
            resized = resized.filter(ImageFilter.UnsharpMask(radius=1.5, percent=100, threshold=3))
        new_img = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2
        new_img.paste(resized, (paste_x, paste_y))
        resized.close()
        return new_img


    def render_video_threaded(self):
        """跑图生成视频（完整流程：生成分镜 + 生成图片 + 合成视频）
        
        工作流程（三种情况）：
        1. 有分镜脚本 + 有图片（数量匹配）→ 直接使用，合成视频
        2. 有分镜脚本 + 无图片/图片不匹配 → 使用分镜脚本，生成图片，合成视频
        3. 无分镜脚本 → 从头生成分镜，生成图片，合成视频
        
        每次执行前会自动清除上一次任务的缓存
        """
        if not getattr(self, '_auth_valid', False):
            self.log("\u26a0\ufe0f \u8bf7\u5148\u767b\u5f55\u540e\u518d\u64cd\u4f5c")
            self._show_login_dialog()
            return
        # ===== 任务互斥检查 =====
        with self.task_lock:
            if self.task_running:
                self.log("⚠️ 已有任务正在运行，请稍后再试")
                return
            self.task_running = True

        self._set_action_buttons_state("disabled")

        try:
            self.log("🎞️ 开始跑图生成视频...")
            self.log("🎬 开始执行生成视频任务")

            # ===== 前置检查 =====
            # 检查1: 必须导入音频文件
            if not self.audio_path:
                self.log("❌ 没有导入音频文件，无法执行任务")
                messagebox.showwarning("缺少音频", "请先导入音频文件，再执行跑图生成视频任务！")
                with self.task_lock:
                    self.task_running = False
                self._set_action_buttons_state("normal")
                return
            
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                messagebox.showwarning("音频文件丢失", "音频文件不存在，请重新导入音频文件！")
                with self.task_lock:
                    self.task_running = False
                self._set_action_buttons_state("normal")
                return
            
            # 检查2: 检查是否存在分镜脚本文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            has_shots_file = os.path.exists(shots_file)
            
            # 检查3: 图片文件夹内是否存在图片文件
            has_images = False
            image_count = 0
            if os.path.exists(self.images_dir):
                image_files = [f for f in os.listdir(self.images_dir) 
                              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
                has_images = len(image_files) > 0
                image_count = len(image_files)
            
            # 加载分镜数据以获取分镜数量（用于后续验证）
            shots_count = 0
            if has_shots_file:
                try:
                    with open(shots_file, 'r', encoding='utf-8') as f:
                        temp_shots = json.load(f)
                    shots_count = len(temp_shots)
                except Exception as e:
                    self._log_exception("⚠️ 读取分镜脚本失败", e)
                    has_shots_file = False
            
            # ========== 情况1: 有分镜脚本 + 有图片（数量匹配）→ 直接合成视频 ==========
            if has_shots_file and has_images and image_count == shots_count:
                self.log("")
                self.log("=" * 60)
                self.log("✅ 检测到完整的分镜脚本和图片文件")
                self.log("=" * 60)
                self.log(f"   📋 分镜数量: {shots_count} 个")
                self.log(f"   🖼️ 图片数量: {image_count} 张")
                self.log(f"   ✅ 数量匹配，可以直接合成视频")
                self.log("")
                self.log("💡 提示: 将直接使用现有文件，跳过生成分镜和生成图片步骤")
                
                # 修复：使用后台线程执行，避免冻结GUI
                self._start_render_thread(mode="use_existing_shots_only")
                return
            
            # ========== 情况2: 有分镜脚本 + 无图片/图片不匹配 → 使用分镜，生成图片 ==========
            if has_shots_file and (not has_images or image_count != shots_count):
                if not has_images:
                    self.log("")
                    self.log("=" * 60)
                    self.log("✅ 检测到分镜脚本文件，但图片文件夹为空")
                    self.log("=" * 60)
                    self.log(f"   📋 分镜数量: {shots_count} 个")
                    self.log(f"   🖼️ 图片数量: 0 张")
                    self.log("")
                    self.log("💡 提示: 将使用现有分镜脚本，自动生成图片")
                else:
                    self.log("")
                    self.log("=" * 60)
                    self.log("⚠️ 检测到分镜脚本文件，但图片数量不匹配")
                    self.log("=" * 60)
                    self.log(f"   📋 分镜数量: {shots_count} 个")
                    self.log(f"   🖼️ 图片数量: {image_count} 张")
                    self.log(f"   ❌ 数量不匹配（需要 {shots_count} 张）")
                    self.log("")
                    self.log("💡 提示: 将使用现有分镜脚本，重新生成所有图片")
                
                # 启动渲染线程
                self._start_render_thread(mode="use_existing_shots")
                return
            
            # ========== 情况3: 无分镜脚本 → 从头生成 ==========
            if not has_shots_file:
                self.log("")
                self.log("=" * 60)
                self.log("📝 未检测到分镜脚本文件")
                self.log("=" * 60)
                self.log("")
                self.log("💡 提示: 将从头开始生成分镜脚本、图片和视频")
                
                # 启动渲染线程
                self._start_render_thread(mode="full_generation")
                return
            
        except Exception as e:
            self.log(f"❌ 渲染视频线程启动失败: {e}")
            safe_print_exc()
            with self.task_lock:
                self.task_running = False
            self._set_action_buttons_state("normal")
    

    def _check_sd_available(self):
        """检查SD API是否可用（本地或云端）"""
        try:
            from video_generator.cloud_image_client import is_cloud_image_enabled
            if is_cloud_image_enabled():
                return True
        except ImportError:
            pass

        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL
        try:
            resp = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=5)
            if resp.status_code == 200:
                self._sd_api_connected = True
                return True
        except Exception:
            pass
        return False

    def _start_render_thread(self, mode="full_generation"):
        """启动渲染线程
        
        Args:
            mode: "full_generation" - 从头生成, "use_existing_shots" - 使用现有分镜和图片, "use_existing_shots_only" - 仅使用现有分镜和图片直接合成视频
        """
        def render_video_worker():
            self.pause_event.set()
            try:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                
                # ========== 阶段1: 准备分镜数据 ==========
                self.log("")
                self.log("=" * 60)
                self.log("📋 阶段1/3: 准备分镜数据")
                self.log("=" * 60)
                
                if mode == "use_existing_shots_only":
                    self.log("✅ 分镜脚本和图片已就绪，直接加载分镜数据")
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            loaded = json.load(f)
                        with self.resource_lock:
                            self.shots_data = loaded
                        self.log(f"📂 已加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self._log_exception("❌ 加载分镜数据失败", e)
                        safe_print_exc()
                        return
                elif mode == "use_existing_shots" and os.path.exists(shots_file):
                    self.log("✅ 检测到已存在的分镜脚本文件")
                    self.log("ℹ️ 将直接使用文件夹内分镜脚本生成图片")
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            loaded = json.load(f)
                        with self.resource_lock:
                            self.shots_data = loaded
                        self.log(f"📂 已加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        self.log("🔄 将重新生成分镜脚本")
                        self.generate_shots(auto_mode=True)
                else:
                    self.log("📝 未检测到分镜脚本，开始从头生成...")
                    self.log("🔄 正在清除上一次任务的缓存...")
                    
                    self.shots_data = []
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    if hasattr(self, '_shot_texts_for_context'):
                        delattr(self, '_shot_texts_for_context')
                    
                    self._move_output_to_trash(reason="一键生成视频")
                    
                    self.cache_clear()
                    try:
                        prompt_cache.clear()
                    except Exception:
                        pass
                    try:
                        image_cache.clear()
                    except Exception:
                        pass
                    
                    try:
                        if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                            self.state_manager['shots'] = {
                                'generated': False,
                                'count': 0,
                                'data': []
                            }
                    except Exception:
                        pass
                    
                    self.log("✅ 旧数据已清除，开始生成分镜...")
                    self.generate_shots(auto_mode=True)
                    
                    self.log("🔍 检查分镜生成结果...")
                
                # 验证分镜是否生成成功
                self.log(f"🔍 验证分镜数据: hasattr={hasattr(self, 'shots_data')}, data={'存在' if hasattr(self, 'shots_data') else '不存在'}, 长度={len(self.shots_data) if hasattr(self, 'shots_data') and self.shots_data else 0}")
                
                if not hasattr(self, 'shots_data') or not self.shots_data:
                    self.log("⚠️ 内存中无分镜数据，尝试从文件加载...")
                    if os.path.exists(shots_file):
                        try:
                            with open(shots_file, 'r', encoding='utf-8') as f:
                                loaded = json.load(f)
                            with self.resource_lock:
                                self.shots_data = loaded
                            self.log(f"📂 从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                        except Exception as e:
                            self.log(f"❌ 加载分镜数据失败: {e}")
                            safe_print_exc()
                    
                    if not self.shots_data:
                        self.log("❌ 分镜生成失败，无法继续")
                        self.update_task_progress("就绪")
                        return
                
                self.log(f"✅ 阶段1完成: {len(self.shots_data)} 个分镜已就绪")
                
                # ========== 阶段2: 生成图像（仅当需要时） ==========
                if mode != "use_existing_shots_only":
                    self.log("🚀 即将进入阶段2: 生成图像...")
                    self.log("")
                    self.log("=" * 60)
                    self.log("🖼️ 阶段2/3: 生成图像")
                    self.log("=" * 60)
                    
                    sd_available = self._check_sd_available()
                    
                    if not sd_available:
                        self.log("")
                        self.log("⚠️ SD API 当前未连接，先跳过生图步骤")
                        self.log("   💡 分镜数据已保存，等待 SD API 连接后自动恢复生图...")
                        self.log("   💡 请确保 Stable Diffusion Web UI 已启动")
                        self.log("   💡 系统将每15秒自动检测SD连接状态")
                        self.log("")
                        self.update_task_progress("⏳ 等待SD API连接...", 35)
                        
                        self._waiting_for_sd = True
                        sd_connected = False
                        
                        while self.task_running and self._waiting_for_sd:
                            time.sleep(15)
                            if not self.task_running:
                                self.log("❌ 任务已被取消")
                                return
                            
                            sd_available_now = self._check_sd_available()
                            if sd_available_now:
                                self.log("")
                                self.log("✅ SD API 已自动连接！继续执行生图任务...")
                                self._waiting_for_sd = False
                                sd_connected = True
                                break
                            else:
                                self.log("⏳ SD API 仍未连接，继续等待...（可点击「停止任务」取消）")
                        
                        if not sd_connected:
                            self.log("")
                            self.log("❌ SD API 始终未连接，任务已停止")
                            self.log("   💡 分镜数据已保存，待SD连接后可重新执行任务")
                            self.log("   💡 也可单独点击「生成图片」按钮手动生图")
                            self.update_task_progress("就绪 - 等待SD API连接")
                            return
                    
                    self.generate_images()
                    
                    if not self.task_running:
                        self.log("❌ 任务已被取消")
                        return

                    # 检查图片是否实际生成成功
                    images_ok = False
                    if os.path.exists(self.images_dir):
                        img_files = [f for f in os.listdir(self.images_dir)
                                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
                        images_ok = len(img_files) > 0
                    
                    if not images_ok:
                        self.log("⚠️ 图像生成未成功，无法合成视频")
                        self.log("   💡 分镜数据已保存，可稍后重试")
                        self.update_task_progress("就绪")
                        return

                    self.log("✅ 阶段2完成: 图像生成结束")
                else:
                    self.log("✅ 跳过阶段2: 使用现有图片")

                # ========== 阶段3: 合成视频 ==========
                self.log("")
                self.log("=" * 60)
                self.log("🎞️ 阶段3/3: 合成视频")
                self.log("=" * 60)
                
                self.generate_video(skip_clear=True, skip_image_check=True)
                
                self.log("✅ 所有阶段完成")
                
            except Exception as e:
                self.log("❌ 渲染视频出错，请检查分镜数据和图片文件是否完整")
                safe_print_exc()
            finally:
                self._waiting_for_sd = False
                try:
                    self._unload_ollama_models(log_prefix="🔄 任务结束: ")
                except Exception:
                    pass
                try:
                    if hasattr(self, 'whisper_model') and self.whisper_model:
                        self._safe_release_whisper_gpu()
                        del self.whisper_model
                        self.whisper_model = None
                        self._whisper_on_gpu = False
                except Exception:
                    pass
                try:
                    if hasattr(self, 'shots_data') and self.shots_data:
                        self.shots_data = []
                except Exception:
                    pass
                try:
                    prompt_cache.clear()
                    image_cache.clear()
                except Exception:
                    pass
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                try:
                    gc.collect()
                except Exception:
                    pass
                with self.task_lock:
                    self.task_running = False
                self._set_action_buttons_state("normal")
                if hasattr(self, '_pregenerated_prompts'):
                    delattr(self, '_pregenerated_prompts')
        
        thread = threading.Thread(target=render_video_worker, daemon=True)
        thread.start()
        with self.task_lock:
            self.current_task_thread = thread
        self.log("✅ 渲染线程已启动")
    

