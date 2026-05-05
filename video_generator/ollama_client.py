# -*- coding: utf-8 -*-
"""Ollama 统一调用入口 + LLMConfig + 全局状态管理

所有 Ollama 调用必须通过本模块的函数进行，禁止在其他模块直接调用 ollama.chat()
使用 HTTP API 直接调用，避免 ollama 库版本兼容性问题
"""

import re
import subprocess
import threading
import time

import requests

from .config import Config, get_http_session


_RE_THINK_BLOCK = re.compile(r'<think>.*?</think>', re.DOTALL)
_RE_THINK_TAG = re.compile(r'</?think>')


def _strip_think_tags(text):
    if not text:
        return text
    text = _RE_THINK_BLOCK.sub('', text)
    text = _RE_THINK_TAG.sub('', text)
    return text.strip()


_ollama_state_lock = threading.Lock()
_ollama_available = False
_ollama_models_cache = None
_ollama_models_cache_time = 0
_OLLAMA_MODELS_CACHE_TTL = 30


def is_cloud_llm_active():
    """统一云端LLM检测，消除各处分散的 try/except ImportError 模式"""
    try:
        from video_generator.cloud_llm_client import is_cloud_llm_enabled
        return is_cloud_llm_enabled()
    except ImportError:
        return False


def is_cloud_image_active():
    """统一云端生图检测"""
    try:
        from video_generator.cloud_image_client import is_cloud_image_enabled
        return is_cloud_image_enabled()
    except ImportError:
        return False


def is_ollama_available():
    with _ollama_state_lock:
        return _ollama_available


def is_llm_available():
    if is_cloud_llm_active():
        return True
    with _ollama_state_lock:
        return _ollama_available


def set_ollama_available(value):
    global _ollama_available
    with _ollama_state_lock:
        _ollama_available = value


def check_ollama_available():
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


_ollama_serve_process = None


def get_ollama_process():
    """获取当前 Ollama 服务进程引用"""
    return _ollama_serve_process


def stop_ollama_serve():
    """终止由本程序启动的 Ollama 服务进程"""
    global _ollama_serve_process
    if _ollama_serve_process is not None:
        try:
            _ollama_serve_process.terminate()
            _ollama_serve_process.wait(timeout=5)
        except Exception:
            try:
                _ollama_serve_process.kill()
            except Exception:
                pass
        _ollama_serve_process = None


_ollama_models_lock = threading.Lock()


def get_available_models(force_refresh=False):
    global _ollama_models_cache, _ollama_models_cache_time

    with _ollama_models_lock:
        now = time.time()
        if not force_refresh and _ollama_models_cache is not None:
            if now - _ollama_models_cache_time < _OLLAMA_MODELS_CACHE_TTL:
                return list(_ollama_models_cache)

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
                return list(available_models)
        except Exception:
            pass

        return list(_ollama_models_cache) if _ollama_models_cache else []


def restart_ollama_service(log_callback=None):
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
    import os

    ollama_path = None
    for path in [
        r"D:\Ollama\ollama.exe",
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
            global _ollama_serve_process
            _ollama_serve_process = subprocess.Popen(
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


class LLMConfig:
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


_ollama_call_semaphore = threading.Semaphore(2)


def call_ollama_model(model_list, system_prompt, user_prompt,
                      log_callback=None, num_predict=512, num_ctx=4096,
                      llm_config=None, extra_options=None, timeout=120):
    if is_cloud_llm_active():
        try:
            from video_generator.cloud_llm_client import call_cloud_llm
            result, model = call_cloud_llm(
                system_prompt, user_prompt,
                log_callback=log_callback,
                num_predict=num_predict,
                llm_config=llm_config,
            )
            return result, model
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ 云端模型调用失败: {e}")
            if not is_ollama_available():
                if log_callback:
                    log_callback("⚠️ 本地 Ollama 也不可用（云端模式下已释放），请检查云端配置")
                return None, None

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

    if isinstance(model_list, str):
        model_list = [model_list]

    candidate_models = [m for m in model_list if m in available_models]

    if not candidate_models:
        if log_callback:
            log_callback(f"⚠️ 模型列表 {model_list} 中没有可用的模型")
        return None, None

    options = {}
    if llm_config:
        config_overrides = {}
        if num_ctx:
            config_overrides["num_ctx"] = num_ctx
        if "num_predict" not in llm_config.config:
            config_overrides["num_predict"] = num_predict
        options = llm_config.get_options(**config_overrides)
    else:
        options = LLMConfig().get_options(
            num_predict=num_predict,
            num_ctx=num_ctx
        )

    if extra_options:
        options.update(extra_options)

    options["num_gpu"] = -1

    for model in candidate_models:
        try:
            if log_callback and len(candidate_models) > 1:
                log_callback(f"   尝试模型: {model}")

            model_options = dict(options)

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
                        "options": model_options,
                        "think": False
                    },
                    timeout=(10, timeout)
                )

            if response.status_code != 200:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} HTTP错误: {response.status_code}")
                continue

            result_data = response.json()
            message = result_data.get("message", {})
            raw_content = message.get("content", "")

            content = _strip_think_tags(raw_content)

            if not content:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} 返回空结果")
                continue

            if log_callback and len(candidate_models) > 1:
                log_callback(f"   ✅ 使用模型: {model}")

            return content, model

        except requests.exceptions.ConnectionError:
            if log_callback:
                log_callback(f"   ⚠️ 无法连接 Ollama 服务，尝试自动重连...")
            if try_start_ollama_service():
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
                                "options": model_options,
                                "think": False
                            },
                            timeout=(10, timeout)
                        )
                    if response.status_code == 200:
                        result_data = response.json()
                        message = result_data.get("message", {})
                        raw_content = message.get("content", "")
                        content = _strip_think_tags(raw_content)
                        if content:
                            if log_callback:
                                log_callback(f"   ✅ 重连成功，使用模型: {model}")
                            return content, model
                except Exception:
                    pass
            continue
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
    return call_ollama_model(
        [model], system_prompt, user_prompt,
        log_callback=log_callback,
        num_predict=num_predict,
        num_ctx=num_ctx,
        llm_config=llm_config,
        extra_options=extra_options,
        timeout=timeout,
    )


def warmup_model(model, log_callback=None):
    if is_cloud_llm_active():
        if log_callback:
            log_callback("☁️ 云端模式已启用，跳过本地模型预热")
        return True
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
