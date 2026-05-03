# -*- coding: utf-8 -*-
"""全局配置、预编译正则、HTTP Session - 唯一配置源"""

import re
import requests
import threading


class Config:
    OLLAMA_BASE_URL = "http://localhost:11434"
    SD_API_BASE_URL = "http://127.0.0.1:8080"
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
    IMAGE_CACHE_SIZE = 200
    IMAGE_CACHE_TTL = 3600

    MAX_RETRY_COUNT = 3
    RETRY_DELAY = 2

    RESIZE_DEBOUNCE_MS = 300
    PROGRESS_UPDATE_INTERVAL_MS = 100

    DEFAULT_MIN_SHOT_DURATION = 4.0


RE_BOLD = re.compile(r'\*\*([^*]+)\*\*')
RE_ITALIC = re.compile(r'\*([^*]+)\*')
RE_NEWLINES = re.compile(r'\n+')
RE_WHITESPACE = re.compile(r'\s+')
RE_LEADING_PUNCT = re.compile(r'^[，,。、：:；;\s]+')
RE_TRAILING_PUNCT = re.compile(r'[，,。、：:；;\s]+$')
RE_THINK_TAGS = re.compile(r'</?think>')
RE_THOUGHT_TAG = re.compile(r'<\|thought\|>.*?</\|thought\|>', re.DOTALL)
RE_THOUGHT_TAG_SIMPLE = re.compile(r'</?\|thought\|>')
RE_COLON_SPLIT = re.compile(r'[：:]\s*([^\n]+)')
RE_CORE_THEME = re.compile(r'\*\*核心主题[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_CORE_THEME_ALT = re.compile(r'核心主题[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_VISUAL_TONE = re.compile(r'\*\*视觉基调[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_VISUAL_TONE_ALT = re.compile(r'视觉基调[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_THEME_ELEMENTS = re.compile(r'\*\*主题元素[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_THEME_ELEMENTS_ALT = re.compile(r'主题元素[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_JSON_BRACKETS = re.compile(r'(\[[\s\S]*\]|\{[\s\S]*\})')
RE_JSON_BRACES = re.compile(r'\{[\s\S]*\}')
RE_JSON_LINE = re.compile(r'["\']?(\d+)["\']?\s*:\s*["\'](.+?)["\']')

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
