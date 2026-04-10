# -*- coding: utf-8 -*-
"""video_generator 子包"""
from .config import Config, get_http_session
from .cache import SmartCache, prompt_cache, image_cache
from .parallel import ParallelPromptGenerator
from .sd_generator import BatchSDGenerator
from .hardware import HardwareAcceleratedRenderer
from .ollama_client import LLMConfig, call_ollama_model, OLLAMA_AVAILABLE
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

# 全局 Ollama 可用性标志
try:
    import requests
    _test = requests.get("http://localhost:11434/api/tags", timeout=0.5)
    OLLAMA_AVAILABLE = True
except:
    OLLAMA_AVAILABLE = False
