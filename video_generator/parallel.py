# -*- coding: utf-8 -*-
"""并行提示词生成器 - 从 My-Video Generator.py 提取"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from .cache import prompt_cache
from .config import Config


# === 从 My-Video Generator.py 提取 ===

class ParallelPromptGenerator:
    """并行提示词生成器 - 延迟初始化线程池"""
    
    def __init__(self, max_workers=Config.DEFAULT_MAX_WORKERS):
        self.max_workers = max_workers
        self.executor = None  # 延迟初始化
    
    def _get_executor(self):
        """获取或创建线程池"""
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="prompt_")
        return self.executor
    
    def generate_batch(self, shots_data, generate_func, progress_callback=None):
        """批量并行生成提示词
        
        Args:
            shots_data: 分镜数据列表
            generate_func: 生成单个提示词的函数
            progress_callback: 进度回调函数
        
        Returns:
            按原始顺序排列的提示词列表
        """
        results = [None] * len(shots_data)
        completed = 0
        
        def generate_with_index(idx_shot):
            idx, shot = idx_shot
            try:
                # 检查缓存
                cache_key = f"{shot.get('description', '')}_{shot.get('content_type', '')}"
                cached = prompt_cache.get(cache_key)
                if cached:
                    return idx, cached, True  # 返回索引、值、是否来自缓存
                
                # 生成提示词
                result = generate_func(shot)
                
                # 存入缓存
                prompt_cache.set(cache_key, result)
                
                return idx, result, False
            except Exception as e:
                return idx, f"ERROR: {str(e)}", False
        
        # 提交所有任务
        executor = self._get_executor()
        future_to_idx = {
            executor.submit(generate_with_index, (i, shot)): i 
            for i, shot in enumerate(shots_data)
        }
        
        # 处理完成的任务
        for future in as_completed(future_to_idx):
            idx, result, from_cache = future.result()
            results[idx] = result
            completed += 1
            
            if progress_callback:
                progress_callback(completed, len(shots_data), from_cache)
        
        return results
    
    def shutdown(self):
        """关闭线程池"""
        if self.executor:
            self.executor.shutdown(wait=False)

