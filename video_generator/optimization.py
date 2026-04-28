# -*- coding: utf-8 -*-
"""
视频生成优化模块 - 提供性能优化的工具类
包含:
- ProgressManager: 统一进度管理和ETA预测
- ResourceManager: 智能资源管理(GPU显存、内存、线程池)
- GPUScheduler: GPU显存调度器(Whisper/SD/Ollama协调)
- BatchImageLoader: 批量图片加载器(带LRU淘汰和内存上限)
- VideoRendererOptimizer: 视频渲染优化器
- ResourceGuard: 资源上下文管理器(用完即释放)
"""

import time
import threading
import gc
import os
import subprocess
from typing import Dict, List, Optional, Tuple, Any
from contextlib import contextmanager


class ProgressManager:
    """统一的进度管理器 - 提供ETA预测和实时统计"""

    def __init__(self, total_items: int = 0):
        self.total_items = total_items
        self.completed_items = 0
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.eta_window: List[Tuple[float, int]] = []
        self.lock = threading.Lock()

    def update(self, completed: Optional[int] = None, increment: int = 1):
        with self.lock:
            if completed is not None:
                self.completed_items = completed
            else:
                self.completed_items += increment
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            if elapsed > 0:
                self.eta_window.append((current_time, self.completed_items))
                if len(self.eta_window) > 10:
                    self.eta_window.pop(0)
            self.last_update_time = current_time

    def get_progress(self) -> float:
        if self.total_items == 0:
            return 0.0
        return min(100.0, (self.completed_items / self.total_items) * 100)

    def get_eta(self) -> float:
        with self.lock:
            if len(self.eta_window) < 2 or self.total_items == 0:
                return -1
            window_start = self.eta_window[0]
            window_end = self.eta_window[-1]
            time_diff = window_end[0] - window_start[0]
            items_diff = window_end[1] - window_start[1]
            if time_diff <= 0 or items_diff <= 0:
                return -1
            items_per_second = items_diff / time_diff
            remaining_items = self.total_items - self.completed_items
            if items_per_second <= 0:
                return -1
            return remaining_items / items_per_second

    def get_throughput(self) -> float:
        with self.lock:
            elapsed = time.time() - self.start_time
            if elapsed <= 0:
                return 0.0
            return self.completed_items / elapsed

    def get_stats(self) -> Dict:
        eta = self.get_eta()
        throughput = self.get_throughput()
        elapsed = time.time() - self.start_time
        return {
            'progress': self.get_progress(),
            'completed': self.completed_items,
            'total': self.total_items,
            'elapsed': elapsed,
            'throughput': throughput,
            'eta': eta,
            'eta_formatted': self._format_eta(eta)
        }

    def _format_eta(self, eta_seconds: float) -> str:
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
        with self.lock:
            self.total_items = total_items
            self.completed_items = 0
            self.start_time = time.time()
            self.last_update_time = time.time()
            self.eta_window.clear()


class ResourceManager:
    """智能资源管理器 - GPU显存、内存、线程池统一管理"""

    def __init__(self):
        self.gpu_memory_threshold = 0.85
        self.ollama_keep_alive_minutes = 5
        self.whisper_unload_after_use = True
        self._cleanup_lock = threading.Lock()
        self._registered_pools: List[Any] = []

    def register_thread_pool(self, pool):
        """注册线程池，退出时统一关闭"""
        self._registered_pools.append(pool)

    def unregister_thread_pool(self, pool):
        """取消注册线程池"""
        if pool in self._registered_pools:
            self._registered_pools.remove(pool)

    def shutdown_all_pools(self, wait=False):
        """关闭所有已注册的线程池"""
        for pool in self._registered_pools:
            try:
                pool.shutdown(wait=wait, cancel_futures=True)
            except TypeError:
                try:
                    pool.shutdown(wait=wait)
                except Exception:
                    pass
            except Exception:
                pass
        self._registered_pools.clear()

    def check_gpu_memory(self) -> Dict:
        try:
            import torch
            if not torch.cuda.is_available():
                return {
                    'available': False,
                    'used_percent': 0.0,
                    'total_mb': 0.0,
                    'used_mb': 0.0,
                    'free_mb': 0.0,
                    'message': 'CUDA不可用'
                }
            total_memory = torch.cuda.get_device_properties(0).total_memory / (1024**2)
            allocated_memory = torch.cuda.memory_allocated(0) / (1024**2)
            reserved_memory = torch.cuda.memory_reserved(0) / (1024**2)
            used_percent = reserved_memory / total_memory if total_memory > 0 else 0
            free_mb = total_memory - reserved_memory
            return {
                'available': True,
                'used_percent': used_percent,
                'total_mb': total_memory,
                'used_mb': allocated_memory,
                'reserved_mb': reserved_memory,
                'free_mb': free_mb,
                'message': f'GPU显存: {reserved_memory:.0f}MB / {total_memory:.0f}MB ({used_percent*100:.1f}%)'
            }
        except Exception as e:
            return {
                'available': False,
                'used_percent': 0.0,
                'total_mb': 0.0,
                'used_mb': 0.0,
                'free_mb': 0.0,
                'message': f'检测失败: {str(e)}'
            }

    def check_system_memory(self) -> Dict:
        """检查系统内存使用情况"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                'available': True,
                'total_gb': mem.total / (1024**3),
                'used_gb': mem.used / (1024**3),
                'free_gb': mem.available / (1024**3),
                'used_percent': mem.percent / 100.0,
                'message': f'内存: {mem.used/(1024**3):.1f}GB / {mem.total/(1024**3):.1f}GB ({mem.percent}%)'
            }
        except ImportError:
            return {
                'available': False,
                'total_gb': 0.0,
                'used_gb': 0.0,
                'free_gb': 0.0,
                'used_percent': 0.0,
                'message': 'psutil未安装'
            }

    def should_cleanup_gpu(self) -> bool:
        gpu_info = self.check_gpu_memory()
        if not gpu_info['available']:
            return False
        return gpu_info['used_percent'] > self.gpu_memory_threshold

    def cleanup_gpu_memory(self, log_callback=None):
        with self._cleanup_lock:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    gc.collect()
                    if log_callback:
                        gpu_info = self.check_gpu_memory()
                        log_callback(f"🧹 GPU显存已清理: {gpu_info['message']}")
            except Exception as e:
                if log_callback:
                    log_callback(f"⚠️ GPU显存清理失败: {e}")

    def unload_whisper_model(self, whisper_model_ref, log_callback=None, full_unload=False):
        """卸载Whisper模型释放GPU

        Args:
            whisper_model_ref: Whisper模型引用
            log_callback: 日志回调
            full_unload: True=完全卸载(删除模型), False=仅移回CPU

        Returns:
            更新后的模型引用(full_unload=True时返回None)
        """
        try:
            import torch
            if whisper_model_ref is not None:
                if torch.cuda.is_available():
                    whisper_model_ref = whisper_model_ref.to("cpu")
                    torch.cuda.empty_cache()
                    if log_callback:
                        log_callback("   🧹 Whisper GPU显存已释放")

                if full_unload:
                    del whisper_model_ref
                    whisper_model_ref = None
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    if log_callback:
                        log_callback("   🧹 Whisper模型已完全卸载，内存已释放")

            return whisper_model_ref
        except Exception as e:
            if log_callback:
                log_callback(f"   ⚠️ Whisper卸载失败: {e}")
            return whisper_model_ref

    def kill_ollama_process(self, log_callback=None):
        """终止Ollama进程释放GPU显存"""
        try:
            if os.name == 'nt':
                subprocess.run(
                    ['taskkill', '/F', '/IM', 'ollama.exe'],
                    capture_output=True, timeout=5
                )
            else:
                subprocess.run(
                    ['pkill', '-f', 'ollama'],
                    capture_output=True, timeout=5
                )
            if log_callback:
                log_callback("🧹 Ollama进程已终止，GPU资源已释放")
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ 终止Ollama失败: {e}")

    def full_cleanup(self, log_callback=None):
        """全面清理：GC + GPU显存 + 系统内存"""
        with self._cleanup_lock:
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
            except ImportError:
                pass
            if log_callback:
                gpu_info = self.check_gpu_memory()
                mem_info = self.check_system_memory()
                log_callback(f"🧹 资源清理完成: {gpu_info['message']} | {mem_info['message']}")

    def smart_gc(self, processed_count: int, interval: int = 50):
        if processed_count > 0 and processed_count % interval == 0:
            gc.collect()

    def get_resource_report(self) -> Dict:
        """获取完整资源报告"""
        gpu = self.check_gpu_memory()
        mem = self.check_system_memory()
        return {
            'gpu': gpu,
            'memory': mem,
            'registered_pools': len(self._registered_pools),
            'needs_gpu_cleanup': self.should_cleanup_gpu()
        }


class GPUScheduler:
    """GPU显存调度器 - 协调 Whisper/SD/Ollama 之间的GPU显存使用

    核心策略：
    1. Whisper 使用时独占GPU，用完立即释放
    2. SD 生成前确保 Whisper 和 Ollama 已释放GPU
    3. Ollama 在分镜任务完成后可终止释放GPU
    4. 所有GPU操作通过调度器协调，避免冲突
    """

    WHISPER = "whisper"
    SD = "stable_diffusion"
    OLLAMA = "ollama"

    def __init__(self, resource_manager: ResourceManager):
        self.rm = resource_manager
        self._lock = threading.Lock()
        self._current_holder = None
        self._holder_since = None

    def acquire(self, task_name: str, log_callback=None):
        """申请GPU资源

        Args:
            task_name: 任务名称 (WHISPER/SD/OLLAMA)
            log_callback: 日志回调

        Returns:
            bool: 是否成功获取
        """
        with self._lock:
            if self._current_holder is not None and self._current_holder != task_name:
                if log_callback:
                    log_callback(f"⏳ GPU被 {self._current_holder} 占用，等待释放...")
                return False

            self._current_holder = task_name
            self._holder_since = time.time()
            if log_callback:
                log_callback(f"🔒 GPU已分配给 {task_name}")
            return True

    def release(self, task_name: str, log_callback=None):
        """释放GPU资源

        Args:
            task_name: 释放资源的任务名称
            log_callback: 日志回调
        """
        with self._lock:
            if self._current_holder == task_name:
                self._current_holder = None
                self._holder_since = None
                self.rm.cleanup_gpu_memory(log_callback=log_callback)
                if log_callback:
                    log_callback(f"🔓 {task_name} 已释放GPU资源")

    @contextmanager
    def gpu_context(self, task_name: str, log_callback=None):
        """GPU资源上下文管理器 - 用完自动释放

        Usage:
            with gpu_scheduler.gpu_context(GPUScheduler.WHISPER, log):
                # 使用GPU的操作
                model.to("cuda")
                ...
            # 离开上下文后自动释放GPU
        """
        self.acquire(task_name, log_callback)
        try:
            yield
        finally:
            self.release(task_name, log_callback)

    def force_release_all(self, log_callback=None):
        """强制释放所有GPU资源"""
        with self._lock:
            self._current_holder = None
            self._holder_since = None
        self.rm.cleanup_gpu_memory(log_callback=log_callback)
        self.rm.kill_ollama_process(log_callback=log_callback)

    def get_status(self) -> Dict:
        """获取GPU调度状态"""
        with self._lock:
            holder = self._current_holder
            since = self._holder_since
        duration = time.time() - since if since else 0
        gpu_info = self.rm.check_gpu_memory()
        return {
            'current_holder': holder,
            'hold_duration': duration,
            'gpu_info': gpu_info
        }


class ResourceGuard:
    """资源守卫 - 上下文管理器，确保资源用完即释放

    Usage:
        # Whisper GPU资源守卫
        with ResourceGuard(whisper_model, log_callback=self.log) as guard:
            guard.model = guard.model.to("cuda")
            result = guard.model.transcribe(audio)
        # 离开上下文后自动将模型移回CPU并清理GPU
    """

    def __init__(self, model_ref, log_callback=None, full_unload=False):
        self.model = model_ref
        self.log_callback = log_callback
        self.full_unload = full_unload
        self._rm = ResourceManager()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.model = self._rm.unload_whisper_model(
            self.model,
            log_callback=self.log_callback,
            full_unload=self.full_unload
        )
        return False


class BatchImageLoader:
    """批量图片加载器 - 带LRU淘汰和内存上限"""

    def __init__(self, batch_size: int = 20, max_memory_mb: int = 512):
        self.batch_size = batch_size
        self.max_memory_mb = max_memory_mb
        self.cache: Dict[str, Any] = {}
        self._access_order: List[str] = []
        self._cache_sizes: Dict[str, int] = {}
        self._total_size = 0
        self.lock = threading.Lock()

    def preload_batch(self, image_paths: List[str]) -> Dict[str, Any]:
        from PIL import Image
        loaded = {}

        for path in image_paths:
            try:
                if path not in self.cache:
                    with Image.open(path) as img:
                        loaded[path] = img.copy()
                    img_size = loaded[path].size[0] * loaded[path].size[1] * 4
                    self._add_to_cache(path, loaded[path], img_size)
                else:
                    loaded[path] = self.cache[path]
                    self._touch(path)
            except Exception as e:
                print(f"⚠️ 图片加载失败 {path}: {e}")

        return loaded

    def _add_to_cache(self, path: str, image: Any, size_bytes: int):
        with self.lock:
            while (self._total_size + size_bytes > self.max_memory_mb * 1024 * 1024
                   and self._access_order):
                evict_path = self._access_order.pop(0)
                evict_size = self._cache_sizes.pop(evict_path, 0)
                self.cache.pop(evict_path, None)
                self._total_size -= evict_size
            self.cache[path] = image
            self._cache_sizes[path] = size_bytes
            self._total_size += size_bytes
            self._touch(path)

    def _touch(self, path: str):
        if path in self._access_order:
            self._access_order.remove(path)
        self._access_order.append(path)

    def get_image(self, path: str):
        with self.lock:
            img = self.cache.get(path)
            if img is not None:
                self._touch(path)
            return img

    def clear_cache(self):
        with self.lock:
            self.cache.clear()
            self._access_order.clear()
            self._cache_sizes.clear()
            self._total_size = 0
            gc.collect()

    def get_cache_size(self) -> int:
        with self.lock:
            return len(self.cache)

    def get_memory_usage_mb(self) -> float:
        with self.lock:
            return self._total_size / (1024 * 1024)


class VideoRendererOptimizer:
    """视频渲染优化器 - 提供渲染相关的优化功能"""

    def __init__(self):
        self.animation_cache: Dict[str, Any] = {}
        self.resource_manager = ResourceManager()

    def check_gpu_encoder(self) -> Dict:
        try:
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
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
        self.animation_cache.clear()
        gc.collect()
