# -*- coding: utf-8 -*-
"""硬件加速视频渲染器 - 从 My-Video Generator.py 提取"""

import subprocess
import os
import tempfile
import shutil
import json


# === 从 My-Video Generator.py 提取 ===

class HardwareAcceleratedRenderer:
    """硬件加速视频渲染器 - 延迟检测"""
    
    def __init__(self):
        self._has_cuda = None
        self._has_quicksync = None
        self._preferred_encoder = None
    
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
    def preferred_encoder(self):
        if self._preferred_encoder is None:
            self._preferred_encoder = self._select_encoder()
        return self._preferred_encoder
    
    def _check_cuda(self):
        """检查CUDA可用性"""
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def _check_quicksync(self):
        """检查Intel Quick Sync可用性 - 带超时"""
        try:
            import subprocess
            # 设置3秒超时，避免ffmpeg卡住
            result = subprocess.run(
                ['ffmpeg', '-hwaccels'], 
                capture_output=True, text=True,
                timeout=3
            )
            return 'qsv' in result.stdout.lower()
        except:
            return False
    
    def _select_encoder(self):
        """选择最佳编码器"""
        if self.has_cuda:
            return {
                'vcodec': 'h264_nvenc',
                'preset': 'p4',  # 性能与质量平衡
                'rc': 'vbr',
                'cq': 23
            }
        elif self.has_quicksync:
            return {
                'vcodec': 'h264_qsv',
                'preset': 'medium',
                'global_quality': 23
            }
        else:
            # CPU编码，使用快速预设
            return {
                'vcodec': 'libx264',
                'preset': 'veryfast',
                'crf': 23
            }
    
    def render(self, image_files, audio_file, output_file, fps=30, 
               transition_type="hard_cut", progress_callback=None):
        """渲染视频
        
        Args:
            image_files: 图像文件路径列表
            audio_file: 音频文件路径
            output_file: 输出视频路径
            fps: 帧率
            transition_type: 转场类型 (hard_cut/crossfade)
            progress_callback: 进度回调
        """
        import subprocess
        import tempfile
        import shutil
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 生成ffmpeg命令
            encoder_config = self.preferred_encoder
            
            # 构建输入参数
            if transition_type == "hard_cut":
                # 硬切：简单高效
                cmd = self._build_hardcut_cmd(
                    image_files, audio_file, output_file, 
                    fps, encoder_config, temp_dir
                )
            else:
                # 交叉淡化
                cmd = self._build_crossfade_cmd(
                    image_files, audio_file, output_file,
                    fps, encoder_config, temp_dir
                )
            
            # 执行渲染
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 监控进度
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                raise Exception(f"FFmpeg渲染失败: {stderr}")
            
            return True
            
        finally:
            # 清理临时文件
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _build_hardcut_cmd(self, image_files, audio_file, output_file, 
                          fps, encoder_config, temp_dir):
        """构建硬切视频命令"""
        import os
        
        # 计算每张图片的持续时间
        import subprocess
        
        # 获取音频时长
        audio_duration = self._get_audio_duration(audio_file)
        duration_per_image = audio_duration / len(image_files)
        
        # 创建concat文件列表
        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for img_file in image_files:
                # 使用loop滤镜循环每张图片
                f.write(f"file '{img_file}'\n")
                f.write(f"duration {duration_per_image}\n")
            # 最后一张图片也需要duration
            if image_files:
                f.write(f"file '{image_files[-1]}'\n")
        
        # 构建ffmpeg命令
        cmd = [
            'ffmpeg',
            '-y',  # 覆盖输出
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-i', audio_file,
            '-c:v', encoder_config['vcodec'],
            '-c:a', 'aac',
            '-b:a', '192k',
            '-r', str(fps),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # 快速启动
        ]
        
        # 添加编码器特定参数
        if 'preset' in encoder_config:
            cmd.extend(['-preset', encoder_config['preset']])
        if 'cq' in encoder_config:
            cmd.extend(['-cq', str(encoder_config['cq'])])
        if 'crf' in encoder_config:
            cmd.extend(['-crf', str(encoder_config['crf'])])
        if 'rc' in encoder_config:
            cmd.extend(['-rc', encoder_config['rc']])
        
        cmd.append(output_file)
        
        return cmd
    
    def _build_crossfade_cmd(self, image_files, audio_file, output_file,
                            fps, encoder_config, temp_dir):
        """构建交叉淡化视频命令（简化版）"""
        # 对于交叉淡化，使用较慢但效果更好的方法
        return self._build_hardcut_cmd(
            image_files, audio_file, output_file,
            fps, encoder_config, temp_dir
        )
    
    def _get_audio_duration(self, audio_file):
        """获取音频时长"""
        import subprocess
        import json
        
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            audio_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])

