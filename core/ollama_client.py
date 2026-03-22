"""Ollama客户端模块 - 统一管理Ollama API调用"""

import os
import re
import threading
import requests
from typing import Optional, List, Dict, Any

from .config import (
    OLLAMA_BASE_URL,
    OLLAMA_API_TAGS,
    OLLAMA_API_CHAT,
    DEFAULT_NUM_PARALLEL,
    DEFAULT_MAX_LOADED_MODELS,
    MODEL_PRIORITY_LIST,
    LIGHTWEIGHT_MODELS,
    LLMConfig,
)


class OllamaClient:
    """Ollama客户端 - 统一管理API调用"""
    
    _instance = None
    _lock = threading.Lock()
    _semaphore = None
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._available = False
        self._models_cache = None
        self._requests_session = None
        
        # 初始化信号量
        from .config import OLLAMA_MAX_CONCURRENT
        if OllamaClient._semaphore is None:
            OllamaClient._semaphore = threading.Semaphore(OLLAMA_MAX_CONCURRENT)
    
    @property
    def is_available(self) -> bool:
        """检查Ollama是否可用"""
        return self._available
    
    def check_connection(self) -> bool:
        """检查Ollama连接"""
        try:
            response = requests.get(OLLAMA_API_TAGS, timeout=5)
            if response.status_code == 200:
                self._available = True
                return True
        except:
            pass
        self._available = False
        return False
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        if self._models_cache is not None:
            return self._models_cache
        
        try:
            response = requests.get(OLLAMA_API_TAGS, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = []
                if "models" in data:
                    for m in data["models"]:
                        name = m.get("name", m.get("model", ""))
                        if name:
                            models.append(name)
                self._models_cache = models
                return models
        except:
            pass
        return []
    
    def restart_with_settings(self, num_parallel: int = DEFAULT_NUM_PARALLEL, 
                             max_models: int = DEFAULT_MAX_LOADED_MODELS) -> bool:
        """重启Ollama并应用设置"""
        import subprocess
        import time
        
        try:
            # 停止现有进程
            subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], 
                         capture_output=True, timeout=5)
            time.sleep(1)
        except:
            pass
        
        # 设置环境变量
        env = os.environ.copy()
        env['OLLAMA_NUM_PARALLEL'] = str(num_parallel)
        env['OLLAMA_MAX_LOADED_MODELS'] = str(max_models)
        
        # 查找Ollama路径
        ollama_path = None
        for path in [r"C:\Ollama\ollama.exe", r"C:\Program Files\Ollama\ollama.exe", 
                    os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                    "ollama"]:
            if os.path.exists(path) or path == "ollama":
                ollama_path = path
                break
        
        if ollama_path:
            try:
                subprocess.Popen([ollama_path, "serve"], 
                               env=env,
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                time.sleep(5)
                self._models_cache = None  # 清除模型缓存
                return self.check_connection()
            except:
                pass
        return False
    
    def chat(self, model: str, messages: List[Dict], options: Optional[Dict] = None) -> Optional[Dict]:
        """调用Ollama chat API"""
        import ollama
        
        try:
            # 使用信号量限制并发
            with self._semaphore:
                response = ollama.chat(
                    model=model,
                    messages=messages,
                    options=options or {}
                )
                return response
        except Exception as e:
            return None
    
    def select_model(self, preferred_model: Optional[str] = None, 
                    lightweight: bool = False) -> Optional[str]:
        """选择最佳模型"""
        available = self.get_available_models()
        if not available:
            return None
        
        # 如果指定了首选模型，且可用
        if preferred_model and preferred_model in available:
            return preferred_model
        
        # 选择模型列表
        model_list = LIGHTWEIGHT_MODELS if lightweight else [m[0] for m in MODEL_PRIORITY_LIST]
        
        for model in model_list:
            if model in available:
                return model
        
        return available[0] if available else None
    
    def cleanup(self):
        """清理资源"""
        self._models_cache = None


# 全局实例
ollama_client = OllamaClient()


def get_ollama_client() -> OllamaClient:
    """获取Ollama客户端实例"""
    return ollama_client
