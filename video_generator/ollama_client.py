# -*- coding: utf-8 -*-
"""Ollama 统一调用入口 + LLMConfig + 全局状态管理

所有 Ollama 调用必须通过本模块的函数进行，禁止在其他模块直接调用 ollama.chat()
使用 HTTP API 直接调用，避免 ollama 库版本兼容性问题
"""

import re
import subprocess
import threading
import time
from .config import Config, get_http_session


def _strip_think_tags(text):
    if not text:
        return text
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'</?think>', '', text)
    return text.strip()


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


def is_llm_available():
    """检查大模型是否可用（云端或本地Ollama，任一可用即返回True）"""
    try:
        from video_generator.cloud_llm_client import is_cloud_llm_enabled
        if is_cloud_llm_enabled():
            return True
    except ImportError:
        pass
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


def restart_ollama_service(log_callback=None):
    """重启Ollama服务，强制重新检测GPU

    当Ollama在模型卸载/重载后GPU检测缓存失效时使用。
    先关闭现有Ollama进程，再重新启动。

    Args:
        log_callback: 日志回调

    Returns:
        bool: 是否成功重启
    """
    import os

    if log_callback:
        log_callback("🔄 重启Ollama服务（强制重新检测GPU）...")

    try:
        if os.name == 'nt':
            subprocess.run(
                ["taskkill", "/f", "/im", "ollama.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(2)
        else:
            subprocess.run(["pkill", "-f", "ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)
    except Exception:
        pass

    set_ollama_available(False)
    time.sleep(1)

    if try_start_ollama_service():
        if log_callback:
            log_callback("✅ Ollama服务已重启")
        return True
    else:
        if log_callback:
            log_callback("⚠️ Ollama服务重启失败")
        return False


def try_start_ollama_service():
    """尝试自动启动 Ollama 服务

    Returns:
        bool: 是否成功启动
    """
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


# ============ 思考模型专属参数（基于官方推荐） ============
_THINKING_MODEL_PROFILES = {
    "qwen3.5": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    },
    "qwen3": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "presence_penalty": 1.5,
        "repeat_penalty": 1.0,
    },
    "deepseek-r1": {
        "temperature": 0.6,
        "top_p": 0.95,
        "min_p": 0.01,
        "repeat_penalty": 1.0,
    },
    "deepscaler": {
        "temperature": 0.6,
        "top_p": 0.95,
        "min_p": 0.01,
        "repeat_penalty": 1.0,
    },
    "kimi": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "repeat_penalty": 1.0,
    },
    "glm-5": {
        "temperature": 0.6,
        "top_p": 0.95,
        "top_k": 20,
        "repeat_penalty": 1.0,
    },
}

_THINKING_MODEL_PREFIXES = tuple(_THINKING_MODEL_PROFILES.keys())


def _get_thinking_model_profile(model_name):
    model_lower = model_name.lower()
    for prefix, profile in _THINKING_MODEL_PROFILES.items():
        if model_lower.startswith(prefix):
            return profile
    return None


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

    _SAMPLING_KEYS = {"temperature", "top_p", "top_k", "min_p", "repeat_penalty",
                      "frequency_penalty", "presence_penalty"}

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
_ollama_call_semaphore = threading.Semaphore(2)


def call_ollama_model(model_list, system_prompt, user_prompt,
                      log_callback=None, num_predict=512, num_ctx=4096,
                      llm_config=None, timeout=120):
    """统一的大模型调用函数

    调度逻辑：
    - 云端大模型已启用 → 全部由云端模型完成，不使用本地Ollama
    - 云端大模型未启用 → 全部由本地Ollama完成

    Args:
        model_list: 模型名称列表，按优先级排列
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调函数
        num_predict: 预测token数
        num_ctx: 上下文长度
        llm_config: LLMConfig 实例，如果提供则使用其参数
        timeout: 请求超时时间（秒），默认120秒

    Returns:
        tuple: (result_text, model_name) 或 (None, None)
    """
    try:
        from video_generator.cloud_llm_client import is_cloud_llm_enabled, call_cloud_llm
        if is_cloud_llm_enabled():
            temperature = None
            if llm_config:
                temperature = llm_config.config.get("temperature")
            result, model = call_cloud_llm(
                system_prompt, user_prompt,
                log_callback=log_callback,
                num_predict=num_predict,
                temperature=temperature,
            )
            return result, model
    except ImportError:
        pass

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

    options["num_gpu"] = -1

    for model in candidate_models:
        try:
            if log_callback:
                log_callback(f"   尝试模型: {model}")

            model_options = dict(options)
            thinking_profile = _get_thinking_model_profile(model)
            is_thinking = thinking_profile is not None
            if is_thinking and model_options.get("num_predict", 0) < 8192:
                model_options["num_predict"] = max(model_options.get("num_predict", 512) * 3, 8192)
                if model_options.get("num_ctx", 0) < model_options["num_predict"] + 2048:
                    model_options["num_ctx"] = model_options["num_predict"] + 2048

            if thinking_profile:
                for key in LLMConfig._SAMPLING_KEYS:
                    if key in thinking_profile:
                        model_options.pop(key, None)
                        model_options[key] = thinking_profile[key]

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
                        "options": model_options
                    },
                    timeout=(10, timeout)
                )

            if response.status_code != 200:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} HTTP错误: {response.status_code}")
                continue

            result_data = response.json()
            message = result_data.get("message", {})
            content = _strip_think_tags(message.get("content", ""))
            thinking = _strip_think_tags(message.get("thinking", ""))

            if content and thinking:
                result = thinking + "\n" + content
            elif content:
                result = content
            elif thinking:
                result = thinking
            else:
                result = ""

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
                       llm_config=None, extra_options=None, timeout=120):
    """调用单个大模型（不自动切换）

    调度逻辑：
    - 云端大模型已启用 → 全部由云端模型完成，不使用本地Ollama
    - 云端大模型未启用 → 全部由本地Ollama完成

    Args:
        model: 模型名称
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调
        num_predict: 预测token数
        num_ctx: 上下文长度
        llm_config: LLMConfig 实例
        extra_options: 额外的采样参数，会覆盖默认值（如 repeat_penalty, temperature）
        timeout: 请求超时时间（秒），默认120秒

    Returns:
        tuple: (result_text, model_name) 或 (None, None)
    """
    try:
        from video_generator.cloud_llm_client import is_cloud_llm_enabled, call_cloud_llm
        if is_cloud_llm_enabled():
            temperature = None
            if llm_config:
                temperature = llm_config.config.get("temperature")
            if extra_options and "temperature" in extra_options:
                temperature = extra_options["temperature"]
            result, used_model = call_cloud_llm(
                system_prompt, user_prompt,
                log_callback=log_callback,
                num_predict=num_predict,
                temperature=temperature,
            )
            return result, used_model
    except ImportError:
        pass

    if not is_ollama_available():
        if not check_ollama_available():
            if log_callback:
                log_callback("⚠️ Ollama 服务不可用")
            return None, None

    thinking_profile = _get_thinking_model_profile(model)
    is_thinking_model = thinking_profile is not None

    if is_thinking_model and num_predict < 8192:
        num_predict = max(num_predict * 3, 8192)
        if num_ctx < num_predict + 2048:
            num_ctx = num_predict + 2048

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

    if thinking_profile:
        for key in LLMConfig._SAMPLING_KEYS:
            if key in thinking_profile:
                options.pop(key, None)
                options[key] = thinking_profile[key]

    if extra_options:
        options.update(extra_options)

    options["num_gpu"] = -1

    try:
        with _ollama_call_semaphore:
            request_body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "keep_alive": 60,
                "options": options
            }
            response = get_http_session().post(
                f"{Config.OLLAMA_BASE_URL}/api/chat",
                json=request_body,
                timeout=(10, timeout)
            )

        if response.status_code != 200:
            if log_callback:
                log_callback(f"⚠️ 模型 {model} HTTP错误: {response.status_code}")
            return None, None

        result_data = response.json()
        message = result_data.get("message", {})
        content = _strip_think_tags(message.get("content", ""))
        thinking = _strip_think_tags(message.get("thinking", ""))

        if content and thinking:
            result = thinking + "\n" + content
        elif content:
            result = content
        elif thinking:
            result = thinking
            if log_callback:
                log_callback(f"💡 模型 {model} content为空，已回退使用thinking字段")
        else:
            result = ""

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

    云端模式下自动跳过，不需要预热本地模型。

    Args:
        model: 模型名称
        log_callback: 日志回调

    Returns:
        bool: 是否成功
    """
    try:
        from video_generator.cloud_llm_client import is_cloud_llm_enabled
        if is_cloud_llm_enabled():
            if log_callback:
                log_callback("☁️ 云端模式已启用，跳过本地模型预热")
            return True
    except ImportError:
        pass
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
                    "keep_alive": 60,
                    "options": {
                        "num_predict": 1,
                        "temperature": 0.1,
                        "num_gpu": -1
                    },
                    "think": False
                },
                timeout=(10, 60)
            )
        if response.status_code == 200:
            try:
                ps_resp = get_http_session().get(
                    f"{Config.OLLAMA_BASE_URL}/api/ps",
                    timeout=5
                )
                if ps_resp.status_code == 200:
                    models = ps_resp.json().get('models', [])
                    for m in models:
                        if model in m.get('name', ''):
                            size_vram = m.get('size_vram', 0)
                            size_total = m.get('size', 0)
                            if log_callback:
                                if size_vram > 0:
                                    log_callback(f"   🖥️ 模型已加载到GPU (VRAM: {size_vram/1024**3:.1f}GB)")
                                elif size_total > 0:
                                    log_callback(f"   ⚠️ 模型运行在CPU上 (内存: {size_total/1024**3:.1f}GB，GPU未使用)")
                            break
            except Exception:
                pass
        return response.status_code == 200
    except Exception:
        return False

