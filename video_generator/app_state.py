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

DEFAULT_MIN_SHOT_DURATION = Config.DEFAULT_MIN_SHOT_DURATION


def get_ollama_available():
    """Get Ollama availability (thread-safe)."""
    return is_ollama_available()


def get_llm_available():
    """Get LLM availability (cloud or local, thread-safe)."""
    return is_llm_available()


def set_ollama_available_global(value):
    """Set Ollama availability (thread-safe)."""
    set_ollama_available(value)


PERFORMANCE_MONITOR_AVAILABLE = False
psutil = None
GPUtil = None


def lazy_import():
    """Lazy import non-essential modules (psutil, GPUtil)."""
    global PERFORMANCE_MONITOR_AVAILABLE, psutil, GPUtil
    try:
        try:
            import psutil as _psutil
            psutil = _psutil
        except ImportError:
            pass
        try:
            import GPUtil as _GPUtil
            GPUtil = _GPUtil
        except ImportError:
            pass
        PERFORMANCE_MONITOR_AVAILABLE = psutil is not None and GPUtil is not None
        check_ollama_available()
    except Exception:
        pass
