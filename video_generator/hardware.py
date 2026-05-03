# -*- coding: utf-8 -*-
"""硬件加速视频渲染器 - 统一FFmpeg渲染与GPU编码器检测"""

import subprocess
import os
import tempfile
import shutil
import json
import re
import time
from typing import Dict


class HardwareAcceleratedRenderer:
    """硬件加速视频渲染器 - 延迟检测 + 实时进度监控"""

    def __init__(self):
        self._has_cuda = None
        self._has_quicksync = None
        self._has_amf = None
        self._preferred_encoder = None
        self._render_process = None
        self._render_processes = []
        self._cancel_requested = False
        self._has_cuda_filters = None
        self._nvenc_sessions = None
        self._nvenc_options = None

    @property
    def has_cuda(self):
        if self._has_cuda is None:
            self._has_cuda = self._check_cuda()
        return self._has_cuda

    @property
    def has_quicksync(self):
        if self._has_quicksync is None:
            self._has_quicksync = self._check_quicksync()
        return self._has_quicksync

    @property
    def has_amf(self):
        if self._has_amf is None:
            self._has_amf = self._check_amf()
        return self._has_amf

    @property
    def preferred_encoder(self):
        if self._preferred_encoder is None:
            self._preferred_encoder = self._select_encoder()
        return self._preferred_encoder

    @property
    def has_cuda_filters(self):
        if self._has_cuda_filters is None:
            self._has_cuda_filters = self._check_cuda_filters()
        return self._has_cuda_filters

    @property
    def nvenc_sessions(self):
        if self._nvenc_sessions is None:
            self._nvenc_sessions = self._detect_nvenc_sessions()
        return self._nvenc_sessions

    @property
    def nvenc_options(self):
        if self._nvenc_options is None:
            self._nvenc_options = self._detect_nvenc_options()
        return self._nvenc_options

    def _check_cuda(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True, text=True, timeout=3
            )
            return 'h264_nvenc' in result.stdout
        except Exception:
            return False

    def _check_quicksync(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True, text=True, timeout=3
            )
            return 'h264_qsv' in result.stdout
        except Exception:
            return False

    def _check_amf(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True, text=True, timeout=3
            )
            return 'h264_amf' in result.stdout
        except Exception:
            return False

    def _check_cuda_filters(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-filters'],
                capture_output=True, text=True, timeout=3
            )
            return 'hwupload_cuda' in result.stdout
        except Exception:
            return False

    def _detect_nvenc_sessions(self):
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=gpu_name', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=5
            )
            gpu_name = result.stdout.strip().lower()
            if any(k in gpu_name for k in ['quadro', 'tesla', 'rtx a', 'a100', 'a10', 'a30', 'a40', 'l40']):
                return 5
            return 3
        except Exception:
            return 3

    def _detect_nvenc_options(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-h', 'encoder=h264_nvenc'],
                capture_output=True, text=True, timeout=5
            )
            help_text = result.stdout
            options = {}
            option_map = {
                'rc-lookahead': ['-rc-lookahead', '-lookahead'],
                '2pass': ['-2pass'],
                'spatial-aq': ['-spatial-aq', '-spatial_aq'],
                'temporal-aq': ['-temporal-aq', '-temporal_aq'],
                'b_ref_mode': ['-b_ref_mode'],
            }
            for opt_key, possible_names in option_map.items():
                for name in possible_names:
                    if name in help_text:
                        options[opt_key] = name
                        break
            return options
        except Exception:
            return {}

    def _select_encoder(self):
        if self.has_cuda:
            return {
                'vcodec': 'h264_nvenc',
                'preset': 'p4',
                'rc': 'vbr',
                'cq': 20,
                'gpu': '0',
            }
        elif self.has_quicksync:
            return {
                'vcodec': 'h264_qsv',
                'preset': 'medium',
                'global_quality': 20
            }
        elif self.has_amf:
            return {
                'vcodec': 'h264_amf',
                'preset': 'quality',
                'rc': 'vbr',
                'quality': 20
            }
        else:
            return {
                'vcodec': 'libx264',
                'preset': 'medium',
                'crf': 20
            }

    def _build_nvenc_extra_params(self):
        """根据FFmpeg实际支持的选项构建NVENC高级参数列表"""
        params = []
        opts = self.nvenc_options

        if '2pass' in opts:
            params.extend([opts['2pass'], '1'])
        if 'rc-lookahead' in opts:
            params.extend([opts['rc-lookahead'], '64'])
        if 'spatial-aq' in opts:
            params.extend([opts['spatial-aq'], '1'])
        if 'temporal-aq' in opts:
            params.extend([opts['temporal-aq'], '1'])
        if 'b_ref_mode' in opts:
            params.extend([opts['b_ref_mode'], '2'])

        return params

    def cancel_render(self):
        """取消正在进行的渲染"""
        self._cancel_requested = True
        if self._render_process and self._render_process.poll() is None:
            try:
                self._render_process.terminate()
            except Exception:
                pass
        for proc in self._render_processes:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

    def render(self, image_files, audio_file, output_file, fps=30,
               transition_type="hard_cut", progress_callback=None,
               log_callback=None, shot_durations=None):
        """渲染视频 - 自动选择最优渲染策略（并行/单进程）

        Args:
            image_files: 图像文件路径列表
            audio_file: 音频文件路径
            output_file: 输出视频路径
            fps: 帧率
            transition_type: 转场类型 (hard_cut/crossfade)
            progress_callback: 进度回调 (percent: float, info: dict)
            log_callback: 日志回调 (message: str)
            shot_durations: 每张图片的持续时间列表(秒)，None则等分音频时长

        Returns:
            bool: 是否成功
        """
        self._cancel_requested = False
        encoder_config = self.preferred_encoder

        if log_callback:
            log_callback(f"🎬 使用编码器: {encoder_config['vcodec']}")
            hw_desc = {"h264_nvenc": "NVIDIA GPU", "h264_qsv": "Intel QuickSync",
                       "h264_amf": "AMD AMF"}.get(encoder_config['vcodec'], "CPU")
            log_callback(f"   硬件加速: {hw_desc}")

        audio_duration = self._get_audio_duration(audio_file)
        if audio_duration <= 0:
            if log_callback:
                log_callback("❌ 无法获取音频时长")
            return False

        num_segments = 1
        if encoder_config['vcodec'] == 'h264_nvenc' and len(image_files) >= 6:
            max_sessions = self.nvenc_sessions
            num_segments = min(max_sessions, max(1, len(image_files) // 3))

        if num_segments >= 2:
            if log_callback:
                log_callback(f"🚀 启用并行编码: {num_segments} 个NVENC会话同时工作")
            success = self._render_parallel(
                image_files, audio_file, output_file, fps,
                encoder_config, audio_duration, shot_durations,
                num_segments, progress_callback, log_callback
            )
            if success:
                return True
            if log_callback:
                log_callback("⚠️ 并行编码失败，回退到单进程渲染...")
            self._cancel_requested = False

        return self._render_single(
            image_files, audio_file, output_file, fps,
            encoder_config, audio_duration, shot_durations,
            progress_callback, log_callback
        )

    def _render_single(self, image_files, audio_file, output_file, fps,
                       encoder_config, audio_duration, shot_durations,
                       progress_callback, log_callback):
        """单进程渲染（原始渲染逻辑）"""
        temp_dir = tempfile.mkdtemp()

        try:
            cmd = self._build_hardcut_cmd(
                image_files, audio_file, output_file,
                fps, encoder_config, temp_dir, audio_duration,
                shot_durations=shot_durations
            )

            total_frames = int(audio_duration * fps)
            if log_callback:
                log_callback(f"🎬 开始渲染: {len(image_files)}张图片, "
                             f"{audio_duration:.1f}秒音频, {total_frames}帧")

            self._render_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            duration_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
            frame_pattern = re.compile(r'frame=\s*(\d+)')
            speed_pattern = re.compile(r'speed=\s*([\d.]+)x')
            size_pattern = re.compile(r'size=\s*(\d+\w+)')
            bitrate_pattern = re.compile(r'bitrate=\s*([\d.]+\w+/s)')

            last_progress = 0.0
            last_log_time = 0.0
            render_start_time = time.time()
            last_update_time = render_start_time

            for line in self._render_process.stderr:
                if self._cancel_requested:
                    self._render_process.terminate()
                    if log_callback:
                        log_callback("⚠️ 渲染已取消")
                    return False

                match = duration_pattern.search(line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = float(match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds
                    progress = min(100.0, (current_time / audio_duration) * 100)

                    frame_match = frame_pattern.search(line)
                    speed_match = speed_pattern.search(line)
                    size_match = size_pattern.search(line)
                    bitrate_match = bitrate_pattern.search(line)

                    current_frame = int(frame_match.group(1)) if frame_match else None
                    speed = float(speed_match.group(1)) if speed_match else None
                    size = size_match.group(1) if size_match else None
                    bitrate = bitrate_match.group(1) if bitrate_match else None

                    elapsed = time.time() - render_start_time
                    eta = None
                    if progress > 0 and elapsed > 0:
                        remaining_pct = 100.0 - progress
                        eta = (remaining_pct / progress) * elapsed

                    info = {
                        'current_time': current_time,
                        'total_time': audio_duration,
                        'current_frame': current_frame,
                        'total_frames': total_frames,
                        'speed': speed,
                        'size': size,
                        'bitrate': bitrate,
                        'eta': eta,
                        'elapsed': elapsed,
                    }

                    now = time.time()
                    if progress - last_progress >= 0.5 or (now - last_update_time >= 2.0 and progress > last_progress):
                        last_progress = progress
                        last_update_time = now
                        if progress_callback:
                            try:
                                progress_callback(progress, info)
                            except TypeError:
                                try:
                                    progress_callback(progress)
                                except Exception:
                                    pass

                    if log_callback and (now - last_log_time >= 5.0) and progress > 1.0:
                        last_log_time = now
                        time_str = f"{int(current_time//60):02d}:{int(current_time%60):02d}"
                        total_str = f"{int(audio_duration//60):02d}:{int(audio_duration%60):02d}"
                        log_parts = [f"   📊 {progress:.1f}% ({time_str}/{total_str})"]
                        if current_frame is not None:
                            log_parts.append(f"帧:{current_frame}/{total_frames}")
                        if speed is not None:
                            log_parts.append(f"速度:{speed:.1f}x")
                        if eta is not None and eta > 0:
                            eta_min = int(eta // 60)
                            eta_sec = int(eta % 60)
                            log_parts.append(f"剩余:{eta_min}:{eta_sec:02d}")
                        if size is not None:
                            log_parts.append(f"大小:{size}")
                        log_callback(" ".join(log_parts))

            self._render_process.wait()
            self._render_process = None

            if self._cancel_requested:
                return False

            if self._render_process is None and os.path.exists(output_file):
                elapsed = time.time() - render_start_time
                file_size = os.path.getsize(output_file)
                size_mb = file_size / (1024 * 1024)
                if progress_callback:
                    try:
                        progress_callback(100.0, {'current_time': audio_duration,
                                                   'total_time': audio_duration,
                                                   'current_frame': total_frames,
                                                   'total_frames': total_frames,
                                                   'speed': None, 'size': None,
                                                   'bitrate': None, 'eta': 0,
                                                   'elapsed': elapsed})
                    except TypeError:
                        try:
                            progress_callback(100.0)
                        except Exception:
                            pass
                if log_callback:
                    log_callback(f"✅ 视频渲染完成 (耗时{elapsed:.1f}s, 文件{size_mb:.1f}MB)")
                return True
            else:
                if log_callback:
                    log_callback("❌ 视频渲染失败")
                return False

        except Exception as e:
            if log_callback:
                log_callback(f"❌ 渲染异常: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _render_parallel(self, image_files, audio_file, output_file, fps,
                         encoder_config, audio_duration, shot_durations,
                         num_segments, progress_callback, log_callback):
        """多进程并行渲染 - 将视频分成多段，使用多个NVENC会话同时编码"""
        temp_dir = tempfile.mkdtemp()

        try:
            if shot_durations and len(shot_durations) == len(image_files):
                durations = shot_durations
            else:
                duration_per_image = audio_duration / len(image_files) if image_files else 5.0
                durations = [duration_per_image] * len(image_files)

            segments = self._split_into_segments(image_files, durations, num_segments)
            if not segments:
                return False

            if log_callback:
                seg_info = ", ".join(f"{len(s['images'])}张/{s['duration']:.1f}s" for s in segments)
                log_callback(f"   📦 分段: [{seg_info}]")

            segment_outputs = []
            processes = []
            progress_data = []

            for i, segment in enumerate(segments):
                seg_output = os.path.join(temp_dir, f"segment_{i:04d}.mp4")
                segment_outputs.append(seg_output)
                progress_data.append({'current_time': 0.0, 'done': False, 'process': None})

                seg_concat = os.path.join(temp_dir, f"concat_{i:04d}.txt")
                with open(seg_concat, 'w', encoding='utf-8') as f:
                    for img_file, dur in zip(segment['images'], segment['durations']):
                        f.write(f"file '{img_file}'\n")
                        f.write(f"duration {dur}\n")
                    if segment['images']:
                        f.write(f"file '{segment['images'][-1]}'\n")

                use_cuda = (self.has_cuda_filters
                            and encoder_config.get('vcodec') == 'h264_nvenc')

                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat', '-safe', '0',
                    '-i', seg_concat,
                ]

                if use_cuda:
                    cmd.extend(['-vf', 'format=nv12,hwupload_cuda'])
                else:
                    cmd.extend(['-pix_fmt', 'yuv420p'])

                cmd.extend([
                    '-c:v', encoder_config['vcodec'],
                    '-an',
                    '-r', str(fps),
                    '-threads', '0',
                    '-thread_queue_size', '512',
                    '-stats_period', '1',
                ])

                for key, flag in [
                    ('preset', '-preset'), ('cq', '-cq'), ('crf', '-crf'),
                    ('rc', '-rc'), ('gpu', '-gpu'),
                ]:
                    if key in encoder_config:
                        cmd.extend([flag, str(encoder_config[key])])

                if encoder_config.get('vcodec') == 'h264_nvenc':
                    nvenc_params = self._build_nvenc_extra_params()
                    cmd.extend(nvenc_params)

                cmd.append(seg_output)

                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    universal_newlines=True
                )
                processes.append(proc)
                progress_data[i]['process'] = proc

            self._render_processes = processes

            if log_callback:
                log_callback(f"   🚀 {len(processes)} 个编码进程已启动")

            render_start_time = time.time()
            duration_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
            last_log_time = 0.0
            last_progress = 0.0
            last_update_time = render_start_time

            while True:
                if self._cancel_requested:
                    for proc in processes:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                    if log_callback:
                        log_callback("⚠️ 渲染已取消")
                    return False

                all_done = True
                for i, proc in enumerate(processes):
                    if progress_data[i]['done']:
                        continue

                    return_code = proc.poll()
                    if return_code is not None:
                        progress_data[i]['done'] = True
                        if return_code != 0:
                            if log_callback:
                                log_callback(f"❌ 分段{i}编码失败 (退出码:{return_code})")
                            for p in processes:
                                try:
                                    p.terminate()
                                except Exception:
                                    pass
                            return False
                        continue

                    all_done = False

                    try:
                        stderr_lines = []
                        while True:
                            line = proc.stderr.readline()
                            if not line:
                                break
                            stderr_lines.append(line)
                            match = duration_pattern.search(line)
                            if match:
                                hours = int(match.group(1))
                                minutes = int(match.group(2))
                                seconds = float(match.group(3))
                                progress_data[i]['current_time'] = hours * 3600 + minutes * 60 + seconds
                    except Exception:
                        pass

                total_progress_time = sum(pd['current_time'] for pd in progress_data)
                progress = min(100.0, (total_progress_time / audio_duration) * 100) if audio_duration > 0 else 0

                now = time.time()
                if progress - last_progress >= 0.5 or (now - last_update_time >= 2.0 and progress > last_progress):
                    last_progress = progress
                    last_update_time = now
                    elapsed = time.time() - render_start_time
                    eta = None
                    if progress > 0 and elapsed > 0:
                        remaining_pct = 100.0 - progress
                        eta = (remaining_pct / progress) * elapsed
                    info = {
                        'current_time': total_progress_time,
                        'total_time': audio_duration,
                        'current_frame': None,
                        'total_frames': int(audio_duration * fps),
                        'speed': None,
                        'size': None,
                        'bitrate': None,
                        'eta': eta,
                        'elapsed': elapsed,
                    }
                    if progress_callback:
                        try:
                            progress_callback(progress, info)
                        except TypeError:
                            try:
                                progress_callback(progress)
                            except Exception:
                                pass

                if log_callback and (now - last_log_time >= 5.0) and progress > 1.0:
                    last_log_time = now
                    done_count = sum(1 for pd in progress_data if pd['done'])
                    log_callback(f"   📊 并行编码 {progress:.1f}% (完成{done_count}/{len(processes)}段)")

                if all_done:
                    break

                time.sleep(0.2)

            for proc in processes:
                proc.wait()

            if self._cancel_requested:
                return False

            if log_callback:
                log_callback("   ✅ 所有分段编码完成，正在合并...")

            concat_file = os.path.join(temp_dir, "final_concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for seg_file in segment_outputs:
                    f.write(f"file '{seg_file}'\n")

            merge_cmd = [
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0',
                '-i', concat_file,
                '-i', audio_file,
                '-c:v', 'copy',
                '-c:a', 'aac', '-b:a', '192k',
                '-movflags', '+faststart',
                output_file
            ]

            merge_result = subprocess.run(
                merge_cmd, capture_output=True, text=True, timeout=300
            )

            if merge_result.returncode != 0:
                if log_callback:
                    log_callback(f"❌ 合并失败: {merge_result.stderr[-200:]}")
                return False

            if os.path.exists(output_file):
                elapsed = time.time() - render_start_time
                file_size = os.path.getsize(output_file)
                size_mb = file_size / (1024 * 1024)
                if progress_callback:
                    try:
                        progress_callback(100.0, {'current_time': audio_duration,
                                                   'total_time': audio_duration,
                                                   'current_frame': int(audio_duration * fps),
                                                   'total_frames': int(audio_duration * fps),
                                                   'speed': None, 'size': None,
                                                   'bitrate': None, 'eta': 0,
                                                   'elapsed': elapsed})
                    except TypeError:
                        try:
                            progress_callback(100.0)
                        except Exception:
                            pass
                if log_callback:
                    log_callback(f"✅ 并行渲染完成 (耗时{elapsed:.1f}s, 文件{size_mb:.1f}MB, {len(processes)}路并行)")
                return True
            else:
                if log_callback:
                    log_callback("❌ 合并后输出文件不存在")
                return False

        except Exception as e:
            if log_callback:
                log_callback(f"❌ 并行渲染异常: {e}")
            return False
        finally:
            self._render_processes = []
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _split_into_segments(self, image_files, durations, num_segments):
        """将图片和时长列表分成大致相等的段"""
        n = len(image_files)
        if n == 0 or num_segments <= 0:
            return []

        num_segments = min(num_segments, n)
        segment_size = n // num_segments
        remainder = n % num_segments

        segments = []
        start = 0
        for i in range(num_segments):
            size = segment_size + (1 if i < remainder else 0)
            end = start + size
            seg_images = image_files[start:end]
            seg_durations = durations[start:end]
            segments.append({
                'images': seg_images,
                'durations': seg_durations,
                'duration': sum(seg_durations),
            })
            start = end

        return segments

    def _build_hardcut_cmd(self, image_files, audio_file, output_file,
                           fps, encoder_config, temp_dir, audio_duration=None,
                           shot_durations=None, use_cuda_upload=True):
        if audio_duration is None:
            audio_duration = self._get_audio_duration(audio_file)

        if shot_durations and len(shot_durations) == len(image_files):
            durations = shot_durations
        else:
            duration_per_image = audio_duration / len(image_files) if image_files else 5.0
            durations = [duration_per_image] * len(image_files)

        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            for img_file, duration in zip(image_files, durations):
                f.write(f"file '{img_file}'\n")
                f.write(f"duration {duration}\n")
            if image_files:
                f.write(f"file '{image_files[-1]}'\n")

        use_cuda = (use_cuda_upload and self.has_cuda_filters
                    and encoder_config.get('vcodec') == 'h264_nvenc')

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', concat_file,
        ]

        if audio_file:
            cmd.extend(['-i', audio_file])

        if use_cuda:
            cmd.extend(['-vf', 'format=nv12,hwupload_cuda'])
        else:
            cmd.extend(['-pix_fmt', 'yuv420p'])

        cmd.extend([
            '-c:v', encoder_config['vcodec'],
            '-r', str(fps),
            '-threads', '0',
            '-thread_queue_size', '512',
            '-movflags', '+faststart',
            '-stats_period', '1',
        ])

        if audio_file:
            cmd.extend(['-c:a', 'aac', '-b:a', '192k'])

        if 'preset' in encoder_config:
            cmd.extend(['-preset', encoder_config['preset']])
        if 'cq' in encoder_config:
            cmd.extend(['-cq', str(encoder_config['cq'])])
        if 'crf' in encoder_config:
            cmd.extend(['-crf', str(encoder_config['crf'])])
        if 'rc' in encoder_config:
            cmd.extend(['-rc', encoder_config['rc']])
        if 'global_quality' in encoder_config:
            cmd.extend(['-global_quality', str(encoder_config['global_quality'])])
        if 'quality' in encoder_config and encoder_config.get('vcodec') == 'h264_amf':
            cmd.extend(['-quality', str(encoder_config['quality'])])
        if 'gpu' in encoder_config:
            cmd.extend(['-gpu', encoder_config['gpu']])

        if encoder_config.get('vcodec') == 'h264_nvenc':
            nvenc_params = self._build_nvenc_extra_params()
            cmd.extend(nvenc_params)

        cmd.append(output_file)
        return cmd

    def _get_audio_duration(self, audio_file):
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                audio_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except Exception:
            return 0.0

    def get_encoder_info(self) -> Dict:
        """获取编码器信息摘要"""
        enc = self.preferred_encoder
        return {
            'encoder': enc['vcodec'],
            'preset': enc.get('preset', 'N/A'),
            'cuda': self.has_cuda,
            'quicksync': self.has_quicksync,
            'amf': self.has_amf,
        }
