# -*- coding: utf-8 -*-
"""硬件加速视频渲染器 - 统一FFmpeg渲染与GPU编码器检测"""

import subprocess
import os
import tempfile
import shutil
import json
import re
import time
import threading
from typing import Dict, Optional, Callable


class HardwareAcceleratedRenderer:
    """硬件加速视频渲染器 - 延迟检测 + 实时进度监控"""

    def __init__(self):
        self._has_cuda = None
        self._has_quicksync = None
        self._has_amf = None
        self._preferred_encoder = None
        self._render_process = None
        self._cancel_requested = False

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

    def _check_cuda(self):
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _check_quicksync(self):
        try:
            result = subprocess.run(
                ['ffmpeg', '-hwaccels'],
                capture_output=True, text=True, timeout=3
            )
            return 'qsv' in result.stdout.lower()
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

    def _select_encoder(self):
        if self.has_cuda:
            return {
                'vcodec': 'h264_nvenc',
                'preset': 'p4',
                'rc': 'vbr',
                'cq': 23
            }
        elif self.has_quicksync:
            return {
                'vcodec': 'h264_qsv',
                'preset': 'medium',
                'global_quality': 23
            }
        elif self.has_amf:
            return {
                'vcodec': 'h264_amf',
                'preset': 'quality',
                'rc': 'vbr',
                'quality': 23
            }
        else:
            return {
                'vcodec': 'libx264',
                'preset': 'veryfast',
                'crf': 23
            }

    def cancel_render(self):
        """取消正在进行的渲染"""
        self._cancel_requested = True
        if self._render_process and self._render_process.poll() is None:
            try:
                self._render_process.terminate()
            except Exception:
                pass

    def render(self, image_files, audio_file, output_file, fps=30,
               transition_type="hard_cut", progress_callback=None,
               log_callback=None):
        """渲染视频（带实时进度监控和取消支持）

        Args:
            image_files: 图像文件路径列表
            audio_file: 音频文件路径
            output_file: 输出视频路径
            fps: 帧率
            transition_type: 转场类型 (hard_cut/crossfade)
            progress_callback: 进度回调 (percent: float)
            log_callback: 日志回调 (message: str)

        Returns:
            bool: 是否成功
        """
        self._cancel_requested = False
        temp_dir = tempfile.mkdtemp()

        try:
            encoder_config = self.preferred_encoder
            if log_callback:
                log_callback(f"🎬 使用编码器: {encoder_config['vcodec']}")

            audio_duration = self._get_audio_duration(audio_file)
            if audio_duration <= 0:
                raise Exception("无法获取音频时长")

            cmd = self._build_hardcut_cmd(
                image_files, audio_file, output_file,
                fps, encoder_config, temp_dir, audio_duration
            )

            if log_callback:
                log_callback(f"🎬 开始渲染: {len(image_files)}张图片, {audio_duration:.1f}秒音频")

            self._render_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            total_frames = int(audio_duration * fps)
            duration_pattern = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
            last_progress = 0.0

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

                    if progress - last_progress >= 1.0:
                        last_progress = progress
                        if progress_callback:
                            try:
                                progress_callback(progress)
                            except Exception:
                                pass

            self._render_process.wait()
            self._render_process = None

            if self._cancel_requested:
                return False

            if self._render_process is None and os.path.exists(output_file):
                if progress_callback:
                    progress_callback(100.0)
                if log_callback:
                    log_callback("✅ 视频渲染完成")
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

    def _build_hardcut_cmd(self, image_files, audio_file, output_file,
                           fps, encoder_config, temp_dir, audio_duration=None):
        if audio_duration is None:
            audio_duration = self._get_audio_duration(audio_file)
        duration_per_image = audio_duration / len(image_files) if image_files else 5.0

        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            for img_file in image_files:
                f.write(f"file '{img_file}'\n")
                f.write(f"duration {duration_per_image}\n")
            if image_files:
                f.write(f"file '{image_files[-1]}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', concat_file,
            '-i', audio_file,
            '-c:v', encoder_config['vcodec'],
            '-c:a', 'aac', '-b:a', '192k',
            '-r', str(fps),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-stats_period', '1',
        ]

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
