"""Shared module-level state accessible across all mixins.

This module centralizes global variables and functions that are needed
by multiple mixin modules, avoiding circular imports.
"""
from video_generator.ollama_client import (
    is_ollama_available,
    is_llm_available,
    set_ollama_available,
    check_ollama_available,
)
from video_generator.config import Config

# 修复：统一引用 Config 中的值，避免多处定义不同步
DEFAULT_MIN_SHOT_DURATION = Config.DEFAULT_MIN_SHOT_DURATION

# Ollama availability state (mirrors ollama_client internal state)
OLLAMA_AVAILABLE = False


def get_ollama_available():
    """Get Ollama availability (thread-safe)."""
    return is_ollama_available()


def get_llm_available():
    """Get LLM availability (cloud or local, thread-safe)."""
    return is_llm_available()


def set_ollama_available_global(value):
    """Set Ollama availability (thread-safe), also updates local cache."""
    global OLLAMA_AVAILABLE
    OLLAMA_AVAILABLE = value
    set_ollama_available(value)


# Performance monitoring state
PERFORMANCE_MONITOR_AVAILABLE = False
psutil = None
GPUtil = None


def lazy_import():
    """Lazy import non-essential modules (psutil, GPUtil)."""
    global PERFORMANCE_MONITOR_AVAILABLE, psutil, GPUtil
    try:
        try:
            import psutil as _psutil
            import GPUtil as _GPUtil
            psutil = _psutil
            GPUtil = _GPUtil
            PERFORMANCE_MONITOR_AVAILABLE = True
        except ImportError:
            pass
        check_ollama_available()
    except Exception as e:
        print(f"延迟导入模块失败: {e}")
