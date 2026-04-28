# -*- coding: utf-8 -*-
"""video_generator 子包 - 统一导出接口"""

from .config import Config, get_http_session
from .cache import SmartCache, prompt_cache, image_cache
from .parallel import ParallelPromptGenerator
from .sd_generator import BatchSDGenerator
from .hardware import HardwareAcceleratedRenderer
from .ollama_client import (
    LLMConfig,
    call_ollama_model,
    call_ollama_single,
    warmup_model,
    is_ollama_available,
    set_ollama_available,
    check_ollama_available,
    get_available_models,
    try_start_ollama_service,
)
from .multi_model import LLMPerformanceOptimizer, llm_optimizer, MultiModelFusion
from .templates import PromptTemplates
from .enhanced_content_recognition import (
    get_enhanced_recognizer, EnhancedContentRecognizer,
    COUNTRY_MAPPING, REGION_MAPPING, CITY_MAPPING,
    ORGANIZATION_MAPPING, MILITARY_MAPPING, CONTENT_TYPE_KEYWORDS
)

try:
    from .arv_optimization import SceneContinuityManager, AbsoluteRealisticPrompts, ARVPromptTemplates
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False
    ARVPromptTemplates = None

try:
    from .prompts_arv import PRESET_PROMPTS
    ARV_PROMPTS_AVAILABLE = True
except ImportError:
    ARV_PROMPTS_AVAILABLE = False
    PRESET_PROMPTS = None


def init_ollama():
    """初始化时检测 Ollama 可用性（替代 __init__.py 中的顶层检测）"""
    check_ollama_available()
