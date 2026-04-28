# -*- coding: utf-8 -*-
"""并行提示词生成器 - 线程池自动回收、任务取消、错误隔离"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from .cache import prompt_cache
from .config import Config


class ParallelPromptGenerator:
    """并行提示词生成器 - 延迟初始化线程池，自动回收，支持取消"""

    _IDLE_TIMEOUT = 120
    _CHECK_INTERVAL = 30

    def __init__(self, max_workers=Config.DEFAULT_MAX_WORKERS):
        self.max_workers = max_workers
        self.executor = None
        self._lock = threading.Lock()
        self._last_use_time = 0
        self._active_tasks = 0
        self._cancelled = False
        self._watcher_thread = None

    def _get_executor(self):
        with self._lock:
            if self.executor is None:
                self.executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="prompt_"
                )
                self._start_watcher()
            self._last_use_time = time.time()
            self._active_tasks += 1
            return self.executor

    def _release_executor(self):
        with self._lock:
            self._active_tasks = max(0, self._active_tasks - 1)
            self._last_use_time = time.time()

    def _start_watcher(self):
        if self._watcher_thread is None or not self._watcher_thread.is_alive():
            self._watcher_thread = threading.Thread(
                target=self._idle_watcher,
                daemon=True,
                name="prompt_pool_watcher"
            )
            self._watcher_thread.start()

    def _idle_watcher(self):
        while True:
            time.sleep(self._CHECK_INTERVAL)
            with self._lock:
                if (self._active_tasks <= 0
                        and self.executor is not None
                        and self._last_use_time > 0):
                    idle_time = time.time() - self._last_use_time
                    if idle_time > self._IDLE_TIMEOUT:
                        try:
                            self.executor.shutdown(wait=False)
                        except Exception:
                            pass
                        self.executor = None
                        return

    def cancel(self):
        """取消当前所有任务"""
        self._cancelled = True

    def generate_batch(self, shots_data, generate_func, progress_callback=None):
        """批量并行生成提示词

        Args:
            shots_data: 分镜数据列表
            generate_func: 生成单个提示词的函数
            progress_callback: 进度回调函数 (completed, total, from_cache)

        Returns:
            按原始顺序排列的提示词列表
        """
        self._cancelled = False
        results = [None] * len(shots_data)
        completed = 0

        def generate_with_index(idx_shot):
            idx, shot = idx_shot
            try:
                if self._cancelled:
                    return idx, None, False

                cache_key = f"{shot.get('description', '')}_{shot.get('content_type', '')}"
                cached = prompt_cache.get(cache_key)
                if cached:
                    return idx, cached, True

                result = generate_func(shot)
                prompt_cache.set(cache_key, result)
                return idx, result, False
            except Exception as e:
                return idx, f"ERROR: {str(e)}", False

        executor = self._get_executor()
        try:
            future_to_idx = {
                executor.submit(generate_with_index, (i, shot)): i
                for i, shot in enumerate(shots_data)
            }

            for future in as_completed(future_to_idx):
                if self._cancelled:
                    break
                try:
                    idx, result, from_cache = future.result(timeout=300)
                    results[idx] = result
                except Exception:
                    pass

                completed += 1
                if progress_callback:
                    try:
                        progress_callback(completed, len(shots_data), False)
                    except Exception:
                        pass
        finally:
            self._release_executor()

        return results

    def shutdown(self):
        """关闭线程池"""
        with self._lock:
            if self.executor:
                try:
                    self.executor.shutdown(wait=False)
                except Exception:
                    pass
                self.executor = None
