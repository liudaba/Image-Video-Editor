# -*- coding: utf-8 -*-
"""性能配置、正则表达式、HTTP Session - 从 My-Video Generator.py 提取"""

import re
import requests

# ============ 性能优化配置常量 ============
class Config:
    # API 配置
    OLLAMA_BASE_URL = "http://localhost:11434"
    SD_API_BASE_URL = "http://127.0.0.1:7860"
    API_TIMEOUT_SHORT = 3
    API_TIMEOUT_MEDIUM = 5
    API_TIMEOUT_LONG = 180

    # 线程池配置
    DEFAULT_MAX_WORKERS = 4
    SD_MAX_WORKERS = 4

    # 缓存配置
    PROMPT_CACHE_SIZE = 500
    PROMPT_CACHE_TTL = 7200
    IMAGE_CACHE_SIZE = 200
    IMAGE_CACHE_TTL = 3600

    # 重试配置
    DEFAULT_MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1

    # UI 配置
    RESIZE_DEBOUNCE_MS = 300
    PROGRESS_UPDATE_INTERVAL_MS = 100

# ============ 预编译正则表达式 ============
# 文本清理
RE_BOLD = re.compile(r'\*\*([^*]+)\*\*')
RE_ITALIC = re.compile(r'\*([^*]+)\*')
RE_NEWLINES = re.compile(r'\n+')
RE_WHITESPACE = re.compile(r'\s+')
RE_LEADING_PUNCT = re.compile(r'^[，,。、：:；;\s]+')
RE_TRAILING_PUNCT = re.compile(r'[，,。、：:；;\s]+$')
RE_THINK_TAGS = re.compile(r'</?think>')
RE_THOUGHT_TAG = re.compile(r'<\|thought\|>.*?</\|thought\|>', re.DOTALL)
RE_THOUGHT_TAG_SIMPLE = re.compile(r'</?\|thought\|>')

# 提取模式
RE_COLON_SPLIT = re.compile(r'[：:]\s*([^\n]+)')
RE_KEYWORDS = re.compile(r'【关键词】[：:]?\s*([^【\n]+)')
RE_CHINESE_ELEMENT = re.compile(r'[场情元素风格氛围][:：]')
RE_ELEMENT_LABEL = re.compile(r'{label}[：:]\\s*([^场元素风格氛围主体细节\\n]+)')
RE_SENTENCE_END = re.compile(r'[.!?。！？]+')

# 主题提取（用于分镜解析）
RE_CORE_THEME = re.compile(r'\*\*核心主题[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_CORE_THEME_ALT = re.compile(r'核心主题[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_VISUAL_TONE = re.compile(r'\*\*视觉基调[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_VISUAL_TONE_ALT = re.compile(r'视觉基调[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_THEME_ELEMENTS = re.compile(r'\*\*主题元素[：:]\s*(.+?)(?:\n|$)', re.DOTALL)
RE_THEME_ELEMENTS_ALT = re.compile(r'主题元素[：:]\s*(.+?)(?:\n|$)', re.DOTALL)

# JSON 提取
RE_JSON_BRACKETS = re.compile(r'(\[[\s\S]*\]|\{[\s\S]*\})')
RE_JSON_BRACES = re.compile(r'\{[\s\S]*\}')
RE_JSON_LINE = re.compile(r'["\']?(\d+)["\']?\s*:\s*["\'](.+?)["\']')

# 主题提取

# 文件匹配
RE_NUMBER = re.compile(r'\d+')

# ============ 全局 HTTP Session (连接复用) ============
_http_session = None

def get_http_session():
    """获取全局 HTTP Session，复用连接提升性能"""
    global _http_session
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

