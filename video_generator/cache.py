# -*- coding: utf-8 -*-
"""智能缓存系统 - 唯一版本，带TTL和LRU的混合缓存"""

import threading
import time
import hashlib
import json
import gc
from .config import Config


class SmartCache:
    """智能缓存系统 - 带TTL和LRU的混合缓存（优化版）"""

    __slots__ = ('max_size', 'default_ttl', '_cache', '_lock', '_hits', '_misses',
                 '_expire_times', '_access_times')

    def __init__(self, max_size=1000, default_ttl=3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = {}
        self._expire_times = {}
        self._access_times = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def _generate_key(self, *args, **kwargs):
        key_data = json.dumps({'args': args, 'kwargs': kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, key):
        with self._lock:
            expire_time = self._expire_times.get(key)
            if expire_time is not None:
                if expire_time > time.time():
                    self._hits += 1
                    self._access_times[key] = time.time()
                    return self._cache.get(key)
                else:
                    self._cache.pop(key, None)
                    self._expire_times.pop(key, None)
                    self._access_times.pop(key, None)
            self._misses += 1
            return None

    def set(self, key, value, ttl=None):
        with self._lock:
            if len(self._cache) >= self.max_size:
                self._evict()

            ttl = ttl or self.default_ttl
            now = time.time()
            self._cache[key] = value
            self._expire_times[key] = now + ttl
            self._access_times[key] = now

    def _evict(self):
        """先淘汰过期项，再按LRU淘汰最久未访问的项"""
        current_time = time.time()
        expired_keys = [k for k, v in self._expire_times.items() if v <= current_time]
        for k in expired_keys:
            self._cache.pop(k, None)
            self._expire_times.pop(k, None)
            self._access_times.pop(k, None)

        if len(self._cache) >= self.max_size and self._access_times:
            sorted_keys = sorted(self._access_times.items(), key=lambda x: x[1])
            evict_count = max(1, len(sorted_keys) // 4)
            for k, _ in sorted_keys[:evict_count]:
                self._cache.pop(k, None)
                self._expire_times.pop(k, None)
                self._access_times.pop(k, None)

    def cleanup_expired(self):
        with self._lock:
            current_time = time.time()
            expired_keys = [k for k, v in self._expire_times.items() if v <= current_time]
            for k in expired_keys:
                self._cache.pop(k, None)
                self._expire_times.pop(k, None)
                self._access_times.pop(k, None)
            return len(expired_keys)

    def get_stats(self):
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
        with self._lock:
            self._cache.clear()
            self._expire_times.clear()
            self._access_times.clear()

    def clear_and_gc(self):
        """清空缓存并触发垃圾回收，释放内存"""
        with self._lock:
            self._cache.clear()
            self._expire_times.clear()
            self._access_times.clear()
        gc.collect()

    def remove_by_prefix(self, prefix):
        """按前缀批量删除缓存项"""
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                self._cache.pop(k, None)
                self._expire_times.pop(k, None)
                self._access_times.pop(k, None)
            return len(keys_to_remove)


prompt_cache = SmartCache(max_size=Config.PROMPT_CACHE_SIZE, default_ttl=Config.PROMPT_CACHE_TTL)
image_cache = SmartCache(max_size=Config.IMAGE_CACHE_SIZE, default_ttl=Config.IMAGE_CACHE_TTL)
