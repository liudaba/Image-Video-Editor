# -*- coding: utf-8 -*-
"""video_generator 子包 - 统一导出接口"""

from .config import Config, get_http_session
from .cache import SmartCache, prompt_cache, image_cache
from .parallel import ParallelPromptGenerator
from .sd_generator import BatchSDGenerator
from .hardware import HardwareAcceleratedRenderer
from .optimization import (
    ProgressManager,
    ResourceManager,
    GPUScheduler,
    ResourceGuard,
    BatchImageLoader,
    VideoRendererOptimizer
)
from .ollama_client import (
    LLMConfig,
    call_ollama_model,
    call_ollama_single,
    warmup_model,
    is_ollama_available,
    is_llm_available,
    set_ollama_available,
    check_ollama_available,
    get_available_models,
    try_start_ollama_service,
)
from .multi_model import LLMPerformanceOptimizer, llm_optimizer
from .templates import PromptTemplates
from .enhanced_content_recognition import (
    get_enhanced_recognizer, EnhancedContentRecognizer,
    COUNTRY_MAPPING, REGION_MAPPING, CITY_MAPPING,
    ORGANIZATION_MAPPING, MILITARY_MAPPING, CONTENT_TYPE_KEYWORDS
)

try:
    from .arv_optimization import SceneContinuityManager, AbsoluteRealisticPrompts, get_arv_prompter
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False
    SceneContinuityManager = None
    AbsoluteRealisticPrompts = None
    get_arv_prompter = None

try:
    from .prompts_arv import ARVPromptTemplates, quick_generate_arv_prompt
    ARV_PROMPTS_AVAILABLE = True
except ImportError:
    ARV_PROMPTS_AVAILABLE = False
    ARVPromptTemplates = None
    quick_generate_arv_prompt = None


def init_ollama():
    """初始化时检测 Ollama 可用性"""
    check_ollama_available()
