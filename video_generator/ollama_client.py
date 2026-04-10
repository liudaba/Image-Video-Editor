# -*- coding: utf-8 -*-
"""Ollama客户端、全局变量、LLMConfig - 从 My-Video Generator.py 提取"""

import threading
import datetime
import time
import json
import re
import requests
from .config import Config
from .cache import prompt_cache
from .multi_model import LLMPerformanceOptimizer

# === 从 My-Video Generator.py 提取 ===

# 全局变量
PERFORMANCE_MONITOR_AVAILABLE = False
psutil = None
GPUtil = None
OLLAMA_AVAILABLE = False
ollama = None
ollama_lock = threading.Lock()  # 全局锁，保护Ollama API调用
requests = None

# ==================== 统一的 Ollama 模型调用函数 ====================
def call_ollama_model(model_list, system_prompt, user_prompt, log_callback=None, num_predict=512, num_ctx=4096):
    """
    统一的 Ollama 模型调用函数 - 自动尝试多个模型，直到成功
    
    使用HTTP API直接调用，避免ollama库版本兼容性问题
    """
    global requests
    
    if requests is None:
        try:
            import requests
        except ImportError:
            if log_callback:
                log_callback("⚠️ requests库未安装")
            return None, None
    
    # 获取可用模型列表
    try:
        response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
        if response.status_code == 200:
            models_info = response.json()
            available_models = []
            if "models" in models_info:
                for m in models_info["models"]:
                    model_name = m.get("name", m.get("model", ""))
                    if model_name:
                        available_models.append(model_name)
        else:
            if log_callback:
                log_callback(f"⚠️ 获取模型列表失败: HTTP {response.status_code}")
            return None, None
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 获取模型列表失败: {e}")
        return None, None
    
    # 过滤出实际可用的模型
    candidate_models = []
    for model in model_list:
        if model in available_models:
            candidate_models.append(model)
    
    if not candidate_models:
        if log_callback:
            log_callback(f"⚠️ 模型列表 {model_list} 中没有可用的模型")
        return None, None
    
    # 依次尝试每个模型
    for model in candidate_models:
        try:
            if log_callback:
                log_callback(f"   尝试模型: {model}")
            
            # 使用HTTP API直接调用
            response = get_http_session().post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": num_predict,
                        "num_ctx": num_ctx
                    }
                },
                timeout=120
            )
            
            if response.status_code != 200:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} HTTP错误: {response.status_code}")
                continue
            
            result_data = response.json()
            result = result_data.get("message", {}).get("content", "").strip()
            
            if not result:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} 返回空结果")
                continue
            
            if log_callback:
                log_callback(f"   ✅ 使用模型: {model}")
            
            return result, model
            
        except Exception as e:
            error_msg = str(e)
            if log_callback:
                log_callback(f"   ⚠️ 模型 {model} 调用失败: {error_msg[:50]}")
            continue
    
    if log_callback:
        log_callback(f"❌ 所有模型调用失败")
    return None, None

# ==================== 提示词优化器 ====================

# 配置常量
DEFAULT_MIN_SHOT_DURATION = 4.0 
SD_API_URL = "http://127.0.0.1:7860"  # 秋叶 SD 默认地址
MAX_RETRY_COUNT = 3  # API 调用最大重试次数
RETRY_DELAY = 2  # 重试延迟（秒）

# ==================== 大模型高级配置 ====================
class LLMConfig:
    """大模型高级配置类 - 释放模型最大潜力"""
    
    # 预设配置模式
    PRESETS = {
        "创意模式": {
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 100,
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.3,
            "description": "高创造性，适合头脑风暴和创意生成"
        },
        "平衡模式": {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 80,
            "repeat_penalty": 1.15,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.2,
            "description": "平衡创造性和准确性"
        },
        "精确模式": {
            "temperature": 0.3,
            "top_p": 0.7,
            "top_k": 40,
            "repeat_penalty": 1.2,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.1,
            "description": "高准确性，适合分析和结构化任务"
        },
        "极速模式": {
            "temperature": 0.2,
            "top_p": 0.5,
            "top_k": 20,
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "num_predict": 500,
            "description": "最快响应，适合简单任务"
        },
        "质量优先": {
            "temperature": 0.6,
            "top_p": 0.92,
            "top_k": 60,
            "repeat_penalty": 1.18,
            "frequency_penalty": 0.25,
            "presence_penalty": 0.25,
            "num_predict": 4000,
            "num_ctx": 8192,
            "description": "最高输出质量，适合复杂任务"
        }
    }
    
    def __init__(self, preset="质量优先"):
        self.preset = preset
        self.config = self.PRESETS.get(preset, self.PRESETS["质量优先"]).copy()
        self.custom_params = {}
    
    def get_options(self, **overrides):
        """获取Ollama调用参数"""
        options = self.config.copy()
        options.update(self.custom_params)
        options.update(overrides)
        # 移除描述字段
        options.pop("description", None)
        return options
    
    def set_custom_param(self, key, value):
        """设置自定义参数"""
        self.custom_params[key] = value
    
    def apply_preset(self, preset_name):
        """应用预设配置"""
        if preset_name in self.PRESETS:
            self.preset = preset_name
            self.config = self.PRESETS[preset_name].copy()
            self.custom_params = {}
            return True
        return False



# 全局优化器实例 (从 multi_model 导入)
