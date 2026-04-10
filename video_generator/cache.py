# -*- coding: utf-8 -*-
"""智能缓存系统 - 从 My-Video Generator.py 提取"""

import threading
import time
import hashlib
import json
from .config import Config


# === 从 My-Video Generator.py 提取 ===

class SmartCache:
    """智能缓存系统 - 带TTL和LRU的混合缓存（优化版）"""

    __slots__ = ('max_size', 'default_ttl', '_cache', '_lock', '_hits', '_misses', '_expire_times')

    def __init__(self, max_size=1000, default_ttl=3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = {}
        self._expire_times = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _generate_key(self, *args, **kwargs):
        """生成缓存键"""
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key):
        """获取缓存值"""
        with self._lock:
            expire_time = self._expire_times.get(key)
            if expire_time is not None:
                if expire_time > time.time():
                    self._hits += 1
                    return self._cache.get(key)
                else:
                    self._cache.pop(key, None)
                    self._expire_times.pop(key, None)
            self._misses += 1
            return None

    def set(self, key, value, ttl=None):
        """设置缓存值"""
        with self._lock:
            if len(self._cache) >= self.max_size:
                min_expire = min(self._expire_times.values()) if self._expire_times else 0
                expired_keys = [k for k, v in self._expire_times.items() if v <= min_expire]
                if expired_keys:
                    for k in expired_keys[:max(1, len(expired_keys) // 4)]:
                        self._cache.pop(k, None)
                        self._expire_times.pop(k, None)

            ttl = ttl or self.default_ttl
            self._cache[key] = value
            self._expire_times[key] = time.time() + ttl

    def cleanup_expired(self):
        """清理过期项"""
        with self._lock:
            current_time = time.time()
            expired_keys = [k for k, v in self._expire_times.items() if v <= current_time]
            for k in expired_keys:
                self._cache.pop(k, None)
                self._expire_times.pop(k, None)
            return len(expired_keys)

    def get_stats(self):
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate*100:.1f}%",
                'size': len(self._cache)
            }

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._expire_times.clear()

# 全局缓存实例
prompt_cache = SmartCache(max_size=Config.PROMPT_CACHE_SIZE, default_ttl=Config.PROMPT_CACHE_TTL)
image_cache = SmartCache(max_size=Config.IMAGE_CACHE_SIZE, default_ttl=Config.IMAGE_CACHE_TTL)

