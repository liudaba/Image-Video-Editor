# -*- coding: utf-8 -*-
"""Cloud LLM Client - 云端大模型统一调用客户端

支持的云端大模型服务商：
1. DeepSeek - 深度求索 (deepseek-chat, deepseek-reasoner)
2. 智谱AI / ChatGLM (glm-4, glm-4-flash, glm-4-plus)
3. 月之暗面 / Moonshot (moonshot-v1-8k, moonshot-v1-32k)
4. 通义千问 / Qwen (qwen-turbo, qwen-plus, qwen-max)
5. SiliconFlow - 硅基流动 (多种开源模型统一API)
6. OpenAI (gpt-4o, gpt-4o-mini, o1-mini)
7. Google Gemini (gemini-2.0-flash, gemini-1.5-pro)

所有云端API均兼容 OpenAI Chat Completions 格式，
通过统一的适配层实现一套代码调用多家服务商。
"""

import threading
import time
import json
import requests
from .config import get_http_session


PROVIDER_CONFIG = {
    "deepseek": {
        "name": "DeepSeek 深度求索",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            {"id": "deepseek-chat", "name": "DeepSeek-V3", "desc": "通用对话，性价比极高", "ctx": 65536},
            {"id": "deepseek-reasoner", "name": "DeepSeek-R1", "desc": "深度推理，逻辑分析", "ctx": 65536},
        ],
        "default_model": "deepseek-chat",
    },
    "zhipu": {
        "name": "智谱AI ChatGLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": [
            {"id": "glm-4-flash", "name": "GLM-4-Flash", "desc": "极速响应，免费额度", "ctx": 128000},
            {"id": "glm-4-plus", "name": "GLM-4-Plus", "desc": "高性能，复杂任务", "ctx": 128000},
            {"id": "glm-4", "name": "GLM-4", "desc": "旗舰模型，全面能力", "ctx": 128000},
        ],
        "default_model": "glm-4-flash",
    },
    "moonshot": {
        "name": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": [
            {"id": "moonshot-v1-8k", "name": "Moonshot-v1-8k", "desc": "标准模型，日常任务", "ctx": 8192},
            {"id": "moonshot-v1-32k", "name": "Moonshot-v1-32k", "desc": "长文本处理", "ctx": 32768},
            {"id": "moonshot-v1-128k", "name": "Moonshot-v1-128k", "desc": "超长文本处理", "ctx": 131072},
        ],
        "default_model": "moonshot-v1-8k",
    },
    "qwen": {
        "name": "通义千问 Qwen",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            {"id": "qwen-turbo", "name": "Qwen-Turbo", "desc": "极速响应，性价比高", "ctx": 131072},
            {"id": "qwen-plus", "name": "Qwen-Plus", "desc": "能力均衡，推荐使用", "ctx": 131072},
            {"id": "qwen-max", "name": "Qwen-Max", "desc": "旗舰模型，最强能力", "ctx": 32768},
        ],
        "default_model": "qwen-plus",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek-V3(SF)", "desc": "DeepSeek-V3 硅基流动版", "ctx": 65536},
            {"id": "Qwen/Qwen2.5-72B-Instruct", "name": "Qwen2.5-72B", "desc": "通义千问72B", "ctx": 32768},
            {"id": "Qwen/Qwen2.5-32B-Instruct", "name": "Qwen2.5-32B", "desc": "通义千问32B", "ctx": 32768},
            {"id": "deepseek-ai/DeepSeek-R1", "name": "DeepSeek-R1(SF)", "desc": "DeepSeek-R1 硅基流动版", "ctx": 65536},
        ],
        "default_model": "deepseek-ai/DeepSeek-V3",
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "gpt-4o-mini", "name": "GPT-4o-mini", "desc": "轻量快速，性价比高", "ctx": 128000},
            {"id": "gpt-4o", "name": "GPT-4o", "desc": "旗舰模型，全能型", "ctx": 128000},
            {"id": "o1-mini", "name": "o1-mini", "desc": "推理模型，逻辑分析", "ctx": 128000},
        ],
        "default_model": "gpt-4o-mini",
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini-2.0-Flash", "desc": "极速响应，免费额度", "ctx": 1048576},
            {"id": "gemini-1.5-pro", "name": "Gemini-1.5-Pro", "desc": "高性能，长上下文", "ctx": 2097152},
        ],
        "default_model": "gemini-2.0-flash",
    },
}


_cloud_llm_lock = threading.Lock()
_cloud_llm_config = {
    "enabled": False,
    "provider": "deepseek",
    "api_key": "",
    "model": "deepseek-chat",
    "custom_base_url": "",
}


def get_cloud_llm_config():
    with _cloud_llm_lock:
        return _cloud_llm_config.copy()


def set_cloud_llm_config(config_dict):
    with _cloud_llm_lock:
        for k, v in config_dict.items():
            _cloud_llm_config[k] = v


def is_cloud_llm_enabled():
    with _cloud_llm_lock:
        return _cloud_llm_config.get("enabled", False) and bool(_cloud_llm_config.get("api_key", ""))


def get_provider_models(provider_id):
    provider = PROVIDER_CONFIG.get(provider_id)
    if not provider:
        return []
    return provider["models"]


def get_all_providers():
    result = []
    for pid, pcfg in PROVIDER_CONFIG.items():
        result.append({
            "id": pid,
            "name": pcfg["name"],
            "default_model": pcfg["default_model"],
            "model_count": len(pcfg["models"]),
        })
    return result


def get_effective_base_url():
    with _cloud_llm_lock:
        custom = _cloud_llm_config.get("custom_base_url", "").strip()
        if custom:
            return custom.rstrip("/")
        provider_id = _cloud_llm_config.get("provider", "deepseek")
        provider = PROVIDER_CONFIG.get(provider_id, {})
        return provider.get("base_url", "").rstrip("/")


def call_cloud_llm(system_prompt, user_prompt, log_callback=None,
                   num_predict=512, temperature=None, llm_config=None):
    """统一的云端大模型调用函数

    所有云端API均兼容 OpenAI Chat Completions 格式。

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调函数
        num_predict: 最大生成token数
        temperature: 采样温度，None则使用默认值

    Returns:
        tuple: (result_text, model_name) 或 (None, None)
    """
    with _cloud_llm_lock:
        config = _cloud_llm_config.copy()

    api_key = config.get("api_key", "")
    if not api_key:
        if log_callback:
            log_callback("⚠️ 云端大模型API Key未设置")
        return None, None

    provider_id = config.get("provider", "deepseek")
    model = config.get("model", "")
    if not model:
        provider = PROVIDER_CONFIG.get(provider_id, {})
        model = provider.get("default_model", "")

    custom = config.get("custom_base_url", "").strip()
    if custom:
        base_url = custom.rstrip("/")
    else:
        base_url = PROVIDER_CONFIG.get(provider_id, {}).get("base_url", "").rstrip("/")
    url = f"{base_url}/chat/completions"

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    request_body = {
        "model": model,
        "messages": messages,
    }

    effective_num_predict = num_predict
    if llm_config:
        config_num_predict = llm_config.config.get("num_predict")
        if config_num_predict and config_num_predict > num_predict:
            effective_num_predict = config_num_predict
    request_body["max_tokens"] = effective_num_predict

    if llm_config:
        sampling = llm_config.get_options()
        if "temperature" in sampling:
            request_body["temperature"] = sampling["temperature"]
        if "top_p" in sampling:
            request_body["top_p"] = sampling["top_p"]
        if "frequency_penalty" in sampling:
            request_body["frequency_penalty"] = sampling["frequency_penalty"]
        if "presence_penalty" in sampling:
            request_body["presence_penalty"] = sampling["presence_penalty"]
    elif temperature is not None:
        request_body["temperature"] = temperature
    else:
        request_body["temperature"] = 0.3

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if log_callback:
        provider_name = PROVIDER_CONFIG.get(provider_id, {}).get("name", provider_id)
        log_callback(f"☁️ 正在调用云端模型: {provider_name} / {model}")

    _MAX_RETRIES = 3
    _RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            session = get_http_session()
            response = session.post(
                url,
                headers=headers,
                json=request_body,
                timeout=(10, 120),
            )

            if response.status_code == 401:
                if log_callback:
                    log_callback("=" * 50)
                    log_callback("❌ 云端模型调用失败！API Key无效或已过期")
                    log_callback("   请在高级设置中检查API Key配置")
                    log_callback("=" * 50)
                return None, None

            if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                if log_callback:
                    reason = "频率限制" if response.status_code == 429 else f"服务器错误({response.status_code})"
                    log_callback(f"⚠️ 云端模型{reason}，第{attempt}次重试（等待{wait}秒）...")
                time.sleep(wait)
                continue

            if response.status_code == 429:
                if log_callback:
                    log_callback("=" * 50)
                    log_callback("⚠️ 云端模型请求频率超限！")
                    log_callback("   请稍后重试，或切换到其他服务商")
                    log_callback("=" * 50)
                return None, None

            if response.status_code != 200:
                error_detail = ""
                try:
                    err_json = response.json()
                    error_detail = err_json.get("error", {}).get("message", "")
                    if not error_detail:
                        error_detail = str(err_json)[:200]
                except Exception:
                    error_detail = response.text[:200]
                if log_callback:
                    log_callback("=" * 50)
                    log_callback(f"❌ 云端模型调用失败！HTTP {response.status_code}")
                    log_callback(f"   错误详情: {error_detail[:150]}")
                    log_callback("=" * 50)
                return None, None

            result_data = response.json()

            choices = result_data.get("choices", [])
            if not choices:
                if log_callback:
                    log_callback("⚠️ 云端模型返回空结果")
                return None, None

            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                if log_callback:
                    log_callback("⚠️ 云端模型返回空内容")
                return None, None

            usage = result_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            if log_callback:
                log_callback(f"✅ 云端模型调用成功: {model} (tokens: {prompt_tokens}+{completion_tokens})")

            return content, model

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < _MAX_RETRIES:
                wait = min(2 ** attempt, 30)
                if log_callback:
                    log_callback(f"⚠️ 云端模型网络异常({type(e).__name__})，第{attempt}次重试（等待{wait}秒）...")
                time.sleep(wait)
                continue
            if log_callback:
                log_callback("=" * 50)
                log_callback(f"❌ 云端模型调用异常！重试{_MAX_RETRIES}次后仍失败")
                log_callback(f"   {type(e).__name__}: {str(e)[:150]}")
                log_callback("=" * 50)
            return None, None

        except Exception as e:
            if log_callback:
                log_callback("=" * 50)
                log_callback(f"❌ 云端模型调用异常！")
                log_callback(f"   {type(e).__name__}: {str(e)[:150]}")
                log_callback("=" * 50)
            return None, None

    if log_callback:
        log_callback(f"❌ 云端模型调用失败：已达最大重试次数({_MAX_RETRIES})")
    return None, None


def test_cloud_connection(api_key, provider_id, model=None, custom_base_url=""):
    """测试云端大模型连接

    Args:
        api_key: API密钥
        provider_id: 服务商ID
        model: 模型ID，None则使用默认
        custom_base_url: 自定义API地址

    Returns:
        tuple: (success, message)
    """
    provider = PROVIDER_CONFIG.get(provider_id)
    if not provider:
        return False, f"未知服务商: {provider_id}"

    if not model:
        model = provider["default_model"]

    base_url = custom_base_url.strip().rstrip("/") if custom_base_url.strip() else provider["base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    request_body = {
        "model": model,
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 10,
        "temperature": 0.1,
    }

    try:
        session = get_http_session()
        response = session.post(url, headers=headers, json=request_body, timeout=30)

        if response.status_code == 401:
            return False, "API Key无效或已过期"
        if response.status_code == 429:
            return True, "连接成功（但请求频率受限，请稍后使用）"
        if response.status_code != 200:
            try:
                err = response.json().get("error", {}).get("message", "")[:100]
            except Exception:
                err = response.text[:100]
            return False, f"API错误 ({response.status_code}): {err}"

        result_data = response.json()
        content = result_data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content:
            return True, f"连接成功！模型 {model} 响应正常"
        return True, "连接成功（模型返回空响应，但API可用）"

    except Exception as e:
        return False, f"连接失败: {type(e).__name__} - {str(e)[:80]}"


# ============ 云端语音识别（ASR） ============

_cloud_asr_lock = threading.Lock()
_cloud_asr_config = {
    "enabled": False,
    "provider": "openai",
    "api_key": "",
}


def get_cloud_asr_config():
    with _cloud_asr_lock:
        return _cloud_asr_config.copy()


def set_cloud_asr_config(config_dict):
    with _cloud_asr_lock:
        for k, v in config_dict.items():
            _cloud_asr_config[k] = v


def is_cloud_asr_enabled():
    with _cloud_asr_lock:
        return _cloud_asr_config.get("enabled", False) and bool(_cloud_asr_config.get("api_key", ""))


def call_cloud_asr(audio_path, language="zh", log_callback=None):
    """调用云端语音识别API

    目前支持 OpenAI Whisper API，返回与本地Whisper兼容的segments格式。

    Args:
        audio_path: 音频文件路径
        language: 语言代码，默认"zh"
        log_callback: 日志回调

    Returns:
        tuple: (segments_list, full_text) 或 (None, None)
        segments格式: [{"start": 0.0, "end": 3.5, "text": "..."}, ...]
    """
    with _cloud_asr_lock:
        config = _cloud_asr_config.copy()
    
    api_key = config.get("api_key", "")
    if not api_key:
        if log_callback:
            log_callback("⚠️ 云端ASR API Key未设置")
        return None, None

    provider = config.get("provider", "openai")

    if provider == "openai":
        return _call_openai_whisper_api(audio_path, api_key, language, log_callback)

    if log_callback:
        log_callback(f"⚠️ 不支持的云端ASR服务商: {provider}")
    return None, None


def _call_openai_whisper_api(audio_path, api_key, language, log_callback=None):
    """调用 OpenAI Whisper API 进行语音识别

    返回与本地Whisper兼容的segments格式。
    """
    import os

    url = "https://api.openai.com/v1/audio/transcriptions"

    if log_callback:
        log_callback("☁️ 正在调用云端Whisper API进行语音识别...")

    try:
        with open(audio_path, "rb") as audio_file:
            filename = os.path.basename(audio_path)

            response = get_http_session().post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_file)},
                data={
                    "model": "whisper-1",
                    "language": language,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=300,
            )

        if response.status_code == 401:
            if log_callback:
                log_callback("=" * 50)
                log_callback("❌ 云端ASR调用失败！API Key无效或已过期")
                log_callback("=" * 50)
            return None, None

        if response.status_code == 429:
            if log_callback:
                log_callback("=" * 50)
                log_callback("⚠️ 云端ASR请求频率超限！")
                log_callback("=" * 50)
            return None, None

        if response.status_code != 200:
            error_detail = ""
            try:
                error_detail = response.json().get("error", {}).get("message", "")[:150]
            except Exception:
                error_detail = response.text[:150]
            if log_callback:
                log_callback("=" * 50)
                log_callback(f"❌ 云端ASR调用失败！HTTP {response.status_code}")
                log_callback(f"   {error_detail}")
                log_callback("=" * 50)
            return None, None

        result_data = response.json()
        segments = result_data.get("segments", [])

        compatible_segments = []
        for seg in segments:
            compatible_segments.append({
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", "").strip(),
            })

        full_text = result_data.get("text", "")
        if not full_text:
            full_text = "".join(s["text"] for s in compatible_segments)

        if log_callback:
            duration = result_data.get("duration", 0)
            log_callback(f"✅ 云端Whisper识别完成: {len(compatible_segments)}个片段, 时长{duration:.1f}秒")

        return compatible_segments, full_text

    except Exception as e:
        if log_callback:
            log_callback("=" * 50)
            log_callback(f"❌ 云端ASR调用异常！")
            log_callback(f"   {type(e).__name__}: {str(e)[:150]}")
            log_callback("=" * 50)
        return None, None
