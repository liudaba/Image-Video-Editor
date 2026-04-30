# -*- coding: utf-8 -*-
"""Ollama 统一调用入口 + LLMConfig + 全局状态管理

所有 Ollama 调用必须通过本模块的函数进行，禁止在其他模块直接调用 ollama.chat()
使用 HTTP API 直接调用，避免 ollama 库版本兼容性问题
"""

import threading
import time
from .config import Config, get_http_session


# ============ Ollama 全局状态（线程安全管理） ============
_ollama_state_lock = threading.Lock()
_ollama_available = False
_ollama_models_cache = None
_ollama_models_cache_time = 0
_OLLAMA_MODELS_CACHE_TTL = 30


def is_ollama_available():
    """线程安全地获取 Ollama 可用状态"""
    with _ollama_state_lock:
        return _ollama_available


def set_ollama_available(value):
    """线程安全地设置 Ollama 可用状态"""
    global _ollama_available
    with _ollama_state_lock:
        _ollama_available = value


def check_ollama_available():
    """检测 Ollama 服务是否可用，更新全局状态并返回"""
    try:
        response = get_http_session().get(
            f"{Config.OLLAMA_BASE_URL}/api/tags",
            timeout=Config.API_TIMEOUT_SHORT
        )
        available = response.status_code == 200
        set_ollama_available(available)
        return available
    except Exception:
        set_ollama_available(False)
        return False


def get_available_models(force_refresh=False):
    """获取可用模型列表（带缓存）

    Args:
        force_refresh: 强制刷新缓存

    Returns:
        list: 模型名称列表，失败返回空列表
    """
    global _ollama_models_cache, _ollama_models_cache_time

    now = time.time()
    if not force_refresh and _ollama_models_cache is not None:
        if now - _ollama_models_cache_time < _OLLAMA_MODELS_CACHE_TTL:
            return _ollama_models_cache

    try:
        response = get_http_session().get(
            f"{Config.OLLAMA_BASE_URL}/api/tags",
            timeout=Config.API_TIMEOUT_MEDIUM
        )
        if response.status_code == 200:
            models_info = response.json()
            available_models = []
            if "models" in models_info:
                for m in models_info["models"]:
                    model_name = m.get("name", m.get("model", ""))
                    if model_name:
                        available_models.append(model_name)
            _ollama_models_cache = available_models
            _ollama_models_cache_time = now
            set_ollama_available(True)
            return available_models
    except Exception:
        pass

    return _ollama_models_cache or []


def try_start_ollama_service():
    """尝试自动启动 Ollama 服务

    Returns:
        bool: 是否成功启动
    """
    import subprocess
    import os

    ollama_path = None
    for path in [
        r"C:\Ollama\ollama.exe",
        r"C:\Program Files\Ollama\ollama.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
        "ollama"
    ]:
        if os.path.exists(path) or path == "ollama":
            ollama_path = path
            break

    if ollama_path:
        try:
            subprocess.Popen(
                [ollama_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            for _ in range(6):
                time.sleep(1)
                if check_ollama_available():
                    return True
        except Exception:
            pass

    return False


# ============ LLMConfig ============
class LLMConfig:
    """大模型高级配置类"""

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
        options.pop("description", None)
        return options

    def set_custom_param(self, key, value):
        self.custom_params[key] = value

    def apply_preset(self, preset_name):
        if preset_name in self.PRESETS:
            self.preset = preset_name
            self.config = self.PRESETS[preset_name].copy()
            self.custom_params = {}
            return True
        return False


# ============ 统一 Ollama 调用函数 ============
_ollama_call_semaphore = threading.Semaphore(3)


def call_ollama_model(model_list, system_prompt, user_prompt,
                      log_callback=None, num_predict=512, num_ctx=4096,
                      llm_config=None):
    """统一的 Ollama 模型调用函数

    使用 HTTP API 直接调用，避免 ollama 库版本兼容性问题。
    自动尝试多个模型，直到成功。

    Args:
        model_list: 模型名称列表，按优先级排列
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调函数
        num_predict: 预测token数
        num_ctx: 上下文长度
        llm_config: LLMConfig 实例，如果提供则使用其参数

    Returns:
        tuple: (result_text, model_name) 或 (None, None)
    """
    if not is_ollama_available():
        if not check_ollama_available():
            if log_callback:
                log_callback("⚠️ Ollama 服务不可用")
            return None, None

    available_models = get_available_models()
    if not available_models:
        if log_callback:
            log_callback("⚠️ 获取模型列表失败")
        return None, None

    candidate_models = [m for m in model_list if m in available_models]

    if not candidate_models:
        if log_callback:
            log_callback(f"⚠️ 模型列表 {model_list} 中没有可用的模型")
        return None, None

    options = {}
    if llm_config:
        options = llm_config.get_options(
            num_predict=num_predict,
            num_ctx=num_ctx
        )
    else:
        options = {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": num_predict,
            "num_ctx": num_ctx
        }

    for model in candidate_models:
        try:
            if log_callback:
                log_callback(f"   尝试模型: {model}")

            with _ollama_call_semaphore:
                response = get_http_session().post(
                    f"{Config.OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": options
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
            if log_callback:
                log_callback(f"   ⚠️ 模型 {model} 调用失败: {str(e)[:80]}")
            continue

    if log_callback:
        log_callback("❌ 所有模型调用失败")
    return None, None


def call_ollama_single(model, system_prompt, user_prompt,
                       log_callback=None, num_predict=512, num_ctx=4096,
                       llm_config=None):
    """调用单个 Ollama 模型（不自动切换）

    Args:
        model: 模型名称
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调
        num_predict: 预测token数
        num_ctx: 上下文长度
        llm_config: LLMConfig 实例

    Returns:
        tuple: (result_text, model_name) 或 (None, None)
    """
    if not is_ollama_available():
        if not check_ollama_available():
            if log_callback:
                log_callback("⚠️ Ollama 服务不可用")
            return None, None

    options = {}
    if llm_config:
        options = llm_config.get_options(
            num_predict=num_predict,
            num_ctx=num_ctx
        )
    else:
        options = {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": num_predict,
            "num_ctx": num_ctx
        }

    try:
        with _ollama_call_semaphore:
            response = get_http_session().post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "keep_alive": 60,
                    "options": options
                },
                timeout=120
            )

        if response.status_code != 200:
            if log_callback:
                log_callback(f"⚠️ 模型 {model} HTTP错误: {response.status_code}")
            return None, None

        result_data = response.json()
        result = result_data.get("message", {}).get("content", "").strip()

        if not result:
            if log_callback:
                log_callback(f"⚠️ 模型 {model} 返回空结果")
            return None, None

        return result, model

    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 模型 {model} 调用失败: {str(e)[:80]}")
        return None, None


def warmup_model(model, log_callback=None):
    """预热模型（发送简单请求让模型加载到内存）

    Args:
        model: 模型名称
        log_callback: 日志回调

    Returns:
        bool: 是否成功
    """
    try:
        with _ollama_call_semaphore:
            response = get_http_session().post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "ok"}
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": 1,
                        "temperature": 0.1
                    }
                },
                timeout=60
            )
        return response.status_code == 200
    except Exception:
        return False

