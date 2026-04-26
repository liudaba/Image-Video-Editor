# -*- coding: utf-8 -*-
"""
视频生成优化模块 - 提供性能优化的工具类
包含:
- ProgressManager: 统一进度管理和ETA预测
- ResourceManager: 智能资源管理(GPU显存、内存)
- BatchImageLoader: 批量图片加载器
- VideoRendererOptimizer: 视频渲染优化器
"""

import time
import threading
import gc
from typing import Dict, List, Optional, Tuple


class ProgressManager:
    """统一的进度管理器 - 提供ETA预测和实时统计"""
    
    def __init__(self, total_items: int = 0):
        self.total_items = total_items
        self.completed_items = 0
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.eta_window: List[Tuple[float, int]] = []  # 滑动窗口记录完成时间
        self.lock = threading.Lock()
        
    def update(self, completed: Optional[int] = None, increment: int = 1):
        """更新进度
        
        Args:
            completed: 直接设置完成的数量（如果为None则使用increment）
            increment: 增量（默认1）
        """
        with self.lock:
            if completed is not None:
                self.completed_items = completed
            else:
                self.completed_items += increment
            
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            
            # 记录到滑动窗口
            if elapsed > 0:
                self.eta_window.append((current_time, self.completed_items))
                # 保持窗口大小(最近10个样本)
                if len(self.eta_window) > 10:
                    self.eta_window.pop(0)
            
            self.last_update_time = current_time
    
    def get_progress(self) -> float:
        """获取当前进度百分比"""
        if self.total_items == 0:
            return 0.0
        return min(100.0, (self.completed_items / self.total_items) * 100)
    
    def get_eta(self) -> float:
        """获取预计剩余时间（秒）
        
        Returns:
            float: 预计剩余秒数，如果无法计算返回-1
        """
        with self.lock:
            if len(self.eta_window) < 2 or self.total_items == 0:
                return -1
            
            # 使用滑动窗口计算平均速度
            window_start = self.eta_window[0]
            window_end = self.eta_window[-1]
            
            time_diff = window_end[0] - window_start[0]
            items_diff = window_end[1] - window_start[1]
            
            if time_diff <= 0 or items_diff <= 0:
                return -1
            
            # 计算每秒处理的项目数
            items_per_second = items_diff / time_diff
            remaining_items = self.total_items - self.completed_items
            
            if items_per_second <= 0:
                return -1
            
            return remaining_items / items_per_second
    
    def get_throughput(self) -> float:
        """获取吞吐量（项目/秒）"""
        with self.lock:
            elapsed = time.time() - self.start_time
            if elapsed <= 0:
                return 0.0
            return self.completed_items / elapsed
    
    def get_stats(self) -> Dict:
        """获取完整的统计信息"""
        eta = self.get_eta()
        throughput = self.get_throughput()
        elapsed = time.time() - self.start_time
        
        stats = {
            'progress': self.get_progress(),
            'completed': self.completed_items,
            'total': self.total_items,
            'elapsed': elapsed,
            'throughput': throughput,
            'eta': eta,
            'eta_formatted': self._format_eta(eta)
        }
        
        return stats
    
    def _format_eta(self, eta_seconds: float) -> str:
        """格式化ETA时间为可读字符串"""
        if eta_seconds < 0:
            return "计算中..."
        
        hours = int(eta_seconds // 3600)
        minutes = int((eta_seconds % 3600) // 60)
        seconds = int(eta_seconds % 60)
        
        if hours > 0:
            return f"{hours}小时{minutes}分{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"
    
    def reset(self, total_items: int = 0):
        """重置进度管理器"""
        with self.lock:
            self.total_items = total_items
            self.completed_items = 0
            self.start_time = time.time()
            self.last_update_time = time.time()
            self.eta_window.clear()


class ResourceManager:
    """智能资源管理器 - GPU显存和内存管理"""
    
    def __init__(self):
        self.gpu_memory_threshold = 0.85  # GPU显存使用阈值
        self.ollama_keep_alive_minutes = 5  # Ollama模型保持活跃时间
        self.whisper_unload_after_use = True  # Whisper使用后卸载
        
    def check_gpu_memory(self) -> Dict:
        """检查GPU显存使用情况
        
        Returns:
            dict: {'available': bool, 'used_percent': float, 'total_mb': float, 'used_mb': float}
        """
        try:
            import torch
            if not torch.cuda.is_available():
                return {
                    'available': False,
                    'used_percent': 0.0,
                    'total_mb': 0.0,
                    'used_mb': 0.0,
                    'message': 'CUDA不可用'
                }
            
            total_memory = torch.cuda.get_device_properties(0).total_memory / (1024**2)  # MB
            allocated_memory = torch.cuda.memory_allocated(0) / (1024**2)  # MB
            used_percent = allocated_memory / total_memory if total_memory > 0 else 0
            
            return {
                'available': True,
                'used_percent': used_percent,
                'total_mb': total_memory,
                'used_mb': allocated_memory,
                'message': f'GPU显存: {allocated_memory:.0f}MB / {total_memory:.0f}MB ({used_percent*100:.1f}%)'
            }
        except Exception as e:
            return {
                'available': False,
                'used_percent': 0.0,
                'total_mb': 0.0,
                'used_mb': 0.0,
                'message': f'检测失败: {str(e)}'
            }
    
    def should_cleanup_gpu(self) -> bool:
        """判断是否需要清理GPU显存"""
        gpu_info = self.check_gpu_memory()
        if not gpu_info['available']:
            return False
        return gpu_info['used_percent'] > self.gpu_memory_threshold
    
    def cleanup_gpu_memory(self, log_callback=None):
        """清理GPU显存"""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                if log_callback:
                    gpu_info = self.check_gpu_memory()
                    log_callback(f"🧹 GPU显存已清理: {gpu_info['message']}")
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ GPU显存清理失败: {e}")
    
    def unload_whisper_model(self, whisper_model_ref, log_callback=None):
        """卸载Whisper模型释放GPU"""
        try:
            import torch
            if whisper_model_ref is not None:
                del whisper_model_ref
                whisper_model_ref = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                if log_callback:
                    log_callback("   🧹 Whisper GPU显存已彻底释放")
                return whisper_model_ref
        except Exception as e:
            if log_callback:
                log_callback(f"   ⚠️ Whisper卸载失败: {e}")
        return whisper_model_ref
    
    def smart_gc(self, processed_count: int, interval: int = 50):
        """智能垃圾回收 - 每处理interval个项目执行一次GC
        
        Args:
            processed_count: 已处理的项目数
            interval: GC间隔
        """
        if processed_count > 0 and processed_count % interval == 0:
            gc.collect()


class BatchImageLoader:
    """批量图片加载器 - 预加载图片到内存减少IO"""
    
    def __init__(self, batch_size: int = 20):
        self.batch_size = batch_size
        self.cache: Dict[str, any] = {}  # 图片路径 -> PIL Image
        self.lock = threading.Lock()
    
    def preload_batch(self, image_paths: List[str]) -> Dict[str, any]:
        """预加载一批图片到缓存
        
        Args:
            image_paths: 图片路径列表
            
        Returns:
            dict: {path: PIL.Image}
        """
        from PIL import Image
        loaded = {}
        
        for path in image_paths:
            try:
                if path not in self.cache:
                    with Image.open(path) as img:
                        loaded[path] = img.copy()  # 复制避免原始图像被修改
                    self.cache[path] = loaded[path]
                else:
                    loaded[path] = self.cache[path]
            except Exception as e:
                print(f"⚠️ 图片加载失败 {path}: {e}")
        
        return loaded
    
    def get_image(self, path: str):
        """从缓存获取图片"""
        with self.lock:
            return self.cache.get(path)
    
    def clear_cache(self):
        """清空缓存释放内存"""
        with self.lock:
            self.cache.clear()
            gc.collect()
    
    def get_cache_size(self) -> int:
        """获取缓存大小"""
        with self.lock:
            return len(self.cache)


class VideoRendererOptimizer:
    """视频渲染优化器 - 提供渲染相关的优化功能"""
    
    def __init__(self):
        self.animation_cache: Dict[str, any] = {}  # 动画效果缓存
        self.resource_manager = ResourceManager()
    
    def check_gpu_encoder(self) -> Dict:
        """检测GPU编码器可用性
        
        Returns:
            dict: {'available': bool, 'encoder': str, 'preset': str}
        """
        try:
            import subprocess
            result = subprocess.run(['ffmpeg', '-encoders'], 
                                  capture_output=True, text=True, timeout=5)
            
            encoders = {
                'h264_nvenc': ('NVIDIA NVENC H.264', 'p4'),
                'hevc_nvenc': ('NVIDIA NVENC HEVC', 'p4'),
                'h264_amf': ('AMD AMF H.264', 'quality'),
                'h264_qsv': ('Intel QuickSync H.264', 'veryslow')
            }
            
            for encoder_name, (desc, preset) in encoders.items():
                if encoder_name in result.stdout:
                    return {
                        'available': True,
                        'encoder': encoder_name,
                        'preset': preset,
                        'description': desc
                    }
            
            return {
                'available': False,
                'encoder': 'libx264',
                'preset': 'veryfast',
                'description': 'CPU软件编码'
            }
        except Exception as e:
            return {
                'available': False,
                'encoder': 'libx264',
                'preset': 'veryfast',
                'description': f'检测失败: {str(e)[:50]}'
            }
    
    def cache_animation_frame(self, clip, duration: float, frame_count: int = 30):
        """预渲染动画帧到缓存
        
        Args:
            clip: MoviePy clip对象
            duration: 持续时间
            frame_count: 帧数
            
        Returns:
            list: 预渲染的帧数组
        """
        import numpy as np
        
        cache_key = f"{id(clip)}_{duration}_{frame_count}"
        if cache_key in self.animation_cache:
            return self.animation_cache[cache_key]
        
        frames = []
        try:
            for i in range(frame_count):
                t = (i / frame_count) * duration
                frame = clip.get_frame(t)
                frames.append(frame)
            
            self.animation_cache[cache_key] = frames
            return frames
        except Exception as e:
            print(f"⚠️ 动画预渲染失败: {e}")
            return None
    
    def clear_animation_cache(self):
        """清空动画缓存"""
        self.animation_cache.clear()
        gc.collect()
