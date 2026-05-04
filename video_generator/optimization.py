# -*- coding: utf-8 -*-
"""
视频生成优化模块 - 提供性能优化的工具类
包含:
- ResourceManager: 智能资源管理(GPU显存、内存、线程池)
"""

import time
import threading
import gc
import os
import subprocess
from typing import Dict, List, Any


class ResourceManager:
    """智能资源管理器 - GPU显存、内存、线程池统一管理"""

    def __init__(self):
        self.gpu_memory_threshold = 0.85
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
