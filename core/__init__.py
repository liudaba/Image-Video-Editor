"""核心模块"""

from .config import (
    LLMConfig,
    MODEL_PRIORITY_LIST,
    LIGHTWEIGHT_MODELS,
    OLLAMA_MAX_CONCURRENT,
    SYSTEM_PROMPT_WITH_CONTEXT,
    SYSTEM_PROMPT_WITHOUT_CONTEXT,
    SYSTEM_PROMPT_LIGHTWEIGHT,
    BAD_PROMPT_PATTERNS,
    QUALITY_TAGS,
    DEFAULT_NEGATIVE_PROMPT,
    CONTENT_TYPE_TAGS,
)
from .ollama_client import OllamaClient, get_ollama_client
from .prompt_engine import PromptEngine, get_prompt_engine

__all__ = [
    # 配置
    'LLMConfig',
    'MODEL_PRIORITY_LIST',
    'LIGHTWEIGHT_MODELS',
    'OLLAMA_MAX_CONCURRENT',
    'SYSTEM_PROMPT_WITH_CONTEXT',
    'SYSTEM_PROMPT_WITHOUT_CONTEXT',
    'SYSTEM_PROMPT_LIGHTWEIGHT',
    'BAD_PROMPT_PATTERNS',
    'QUALITY_TAGS',
    'DEFAULT_NEGATIVE_PROMPT',
    'CONTENT_TYPE_TAGS',
    # 客户端
    'OllamaClient',
    'get_ollama_client',
    # 提示词引擎
    'PromptEngine',
    'get_prompt_engine',
]
