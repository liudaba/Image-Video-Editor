# -*- coding: utf-8 -*-
"""全局配置、预编译正则、HTTP Session - 唯一配置源"""

import re
import sys
import requests
import threading


class Config:
    OLLAMA_BASE_URL = "http://localhost:11434"
    SD_API_BASE_URL = "http://127.0.0.1:8080"
    API_BASE_URL = "http://8.141.101.155"
    API_TIMEOUT_SHORT = 3
    API_TIMEOUT_MEDIUM = 5
    API_TIMEOUT_LONG = 180
    API_TIMEOUT_LLM_WARMUP = 30
    API_TIMEOUT_LLM_PROMPT = 180
    API_TIMEOUT_LLM_ANALYSIS = 180

    DEFAULT_MAX_WORKERS = 4
    SD_MAX_WORKERS = 4

    PROMPT_CACHE_SIZE = 500
    PROMPT_CACHE_TTL = 7200
    IMAGE_CACHE_SIZE = 50
    IMAGE_CACHE_TTL = 3600

    MAX_RETRY_COUNT = 3
    RETRY_DELAY = 2

    RESIZE_DEBOUNCE_MS = 300
    PROGRESS_UPDATE_INTERVAL_MS = 100

    DEFAULT_MIN_SHOT_DURATION = 4.0

    IMAGE_WIDTH_MIN = 256
    IMAGE_WIDTH_MAX = 4096
    IMAGE_HEIGHT_MIN = 256
    IMAGE_HEIGHT_MAX = 4096
    IMAGE_SIZE_STEP = 8


def validate_image_size(width_str, height_str, default_w=1024, default_h=576):
    """验证并修正图片尺寸，确保在合法范围内且为8的倍数"""
    try:
        w = int(width_str)
    except (ValueError, TypeError):
        w = default_w
    try:
        h = int(height_str)
    except (ValueError, TypeError):
        h = default_h
    w = max(Config.IMAGE_WIDTH_MIN, min(Config.IMAGE_WIDTH_MAX, w))
    h = max(Config.IMAGE_HEIGHT_MIN, min(Config.IMAGE_HEIGHT_MAX, h))
    w = (w // Config.IMAGE_SIZE_STEP) * Config.IMAGE_SIZE_STEP
    h = (h // Config.IMAGE_SIZE_STEP) * Config.IMAGE_SIZE_STEP
    w = max(Config.IMAGE_SIZE_STEP, w)
    h = max(Config.IMAGE_SIZE_STEP, h)
    return w, h


RE_BOLD = re.compile(r'\*\*([^*]+)\*\*')
RE_ITALIC = re.compile(r'\*([^*]+)\*')
RE_NEWLINES = re.compile(r'\n+')
RE_WHITESPACE = re.compile(r'\s+')
RE_LEADING_PUNCT = re.compile(r'^[，,。、：:；;\s]+')
RE_TRAILING_PUNCT = re.compile(r'[，,。、：:；;\s]+$')
RE_COLON_SPLIT = re.compile(r'[：:]\s*([^\n]+)')

_http_session = None
_http_session_lock = threading.Lock()


def get_http_session():
    """获取全局 HTTP Session，复用连接提升性能（线程安全）"""
    global _http_session
    if _http_session is None:
        with _http_session_lock:
            if _http_session is None:
                _http_session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=10,
                    pool_maxsize=20,
                    max_retries=2
                )
                _http_session.mount('http://', adapter)
                _http_session.mount('https://', adapter)
    return _http_session


_RE_URL_SENSITIVE = re.compile(r'([?&](?:token|key|api_key|secret|password|auth)=)[^&\s]+', re.IGNORECASE)


def sanitize_url(url):
    """脱敏URL中的敏感参数，用于日志输出
    
    sanitize_url("http://host:8080?token=abc123&mode=json")
    → "http://host:8080?token=***&mode=json"
    """
    if not url:
        return url
    return _RE_URL_SENSITIVE.sub(r'\1***', url)


def get_api_base_url():
    """从config.json读取API基础地址，失败则使用默认值。强制HTTPS，拒绝HTTP非本地地址"""
    try:
        import os
        import json
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            url = data.get("api_base_url", "").strip()
            if url:
                url = url.rstrip("/")
                return url
    except Exception:
        pass
    return Config.API_BASE_URL
