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
import base64
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
            {"id": "o1-mini", "name": "O1-Mini", "desc": "推理模型，逻辑分析", "ctx": 128000},
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
    if provider_id not in PROVIDER_CONFIG:
        if log_callback:
            log_callback(f"⚠️ 未知的云端LLM服务商: {provider_id}，请检查配置")
        return None, None
    model = config.get("model", "")
    if not model:
        provider = PROVIDER_CONFIG.get(provider_id, {})
        model = provider.get("default_model", "")
    if not model:
        # 从模型列表中取第一个
        models = PROVIDER_CONFIG.get(provider_id, {}).get("models", [])
        if models:
            model = models[0]["id"]
    if not model:
        if log_callback:
            log_callback("⚠️ 云端LLM模型未指定，请选择模型")
        return None, None

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

ASR_PROVIDER_CONFIG = {
    "openai": {
        "name": "OpenAI Whisper",
        "base_url": "https://api.openai.com",
        "models": [
            {"id": "whisper-1", "name": "Whisper-1", "desc": "OpenAI官方语音识别，多语言支持"},
        ],
        "default_model": "whisper-1",
        "api_format": "openai_whisper",
    },
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn",
        "models": [
            {"id": "FunAudioLLM/SenseVoiceSmall", "name": "SenseVoiceSmall", "desc": "阿里SenseVoice，中文优化", "max_size": 25},
            {"id": "deepseek-ai/DeepSeek-Whisper", "name": "DeepSeek-Whisper", "desc": "DeepSeek语音模型"},
        ],
        "default_model": "FunAudioLLM/SenseVoiceSmall",
        "api_format": "openai_whisper",
    },
    "aliyun": {
        "name": "阿里云语音识别",
        "base_url": "https://dashscope.aliyuncs.com",
        "models": [
            {"id": "sensevoice-v1", "name": "SenseVoice V1", "desc": "阿里SenseVoice，中文最优"},
            {"id": "paraformer-v2", "name": "Paraformer V2", "desc": "Paraformer语音识别"},
        ],
        "default_model": "sensevoice-v1",
        "api_format": "dashscope_asr",
    },
    "tencent": {
        "name": "腾讯云语音识别",
        "base_url": "https://asr.tencentcloudapi.com",
        "models": [
            {"id": "16k_zh", "name": "中文普通话", "desc": "16k采样率，中文通用"},
            {"id": "16k_en", "name": "英文", "desc": "16k采样率，英文通用"},
        ],
        "default_model": "16k_zh",
        "api_format": "tencent_asr",
    },
}


def get_asr_provider_models(provider_id):
    provider = ASR_PROVIDER_CONFIG.get(provider_id)
    if not provider:
        return []
    return provider["models"]


def get_all_asr_providers():
    result = []
    for pid, pcfg in ASR_PROVIDER_CONFIG.items():
        result.append({
            "id": pid,
            "name": pcfg["name"],
            "default_model": pcfg["default_model"],
            "model_count": len(pcfg["models"]),
        })
    return result


_cloud_asr_lock = threading.Lock()
_cloud_asr_config = {
    "enabled": False,
    "provider": "openai",
    "api_key": "",
    "model": "whisper-1",
    "custom_base_url": "",
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


def test_cloud_asr_connection(api_key, provider="openai", model=None, custom_base_url=""):
    """测试云端语音识别API连接

    Args:
        api_key: API密钥
        provider: 服务商ID
        model: 模型ID
        custom_base_url: 自定义API地址

    Returns:
        tuple: (success, message)
    """
    if not api_key:
        return False, "API Key不能为空"

    provider_cfg = ASR_PROVIDER_CONFIG.get(provider)
    if not provider_cfg:
        return False, f"不支持的服务商: {provider}"

    try:
        base_url = custom_base_url.strip() if custom_base_url.strip() else provider_cfg["base_url"]
        api_format = provider_cfg.get("api_format", "openai_whisper")

        if api_format in ("openai_whisper",):
            # OpenAI 兼容格式：通过列出模型验证 Key
            url = f"{base_url.rstrip('/')}/v1/models"
            response = get_http_session().get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                target_model = model or provider_cfg["default_model"]
                target_available = any(
                    m.get("id", "") == target_model or m.get("id", "").startswith("whisper")
                    for m in data.get("data", [])
                )
                if target_available:
                    return True, f"连接成功，{target_model} 可用"
                else:
                    return True, f"连接成功（共{model_count}个模型）"
            elif response.status_code == 401:
                return False, "API Key无效或已过期"
            elif response.status_code == 429:
                return True, "连接成功（请求频率受限，但Key有效）"
            else:
                return False, f"HTTP {response.status_code}: {response.text[:100]}"

        elif api_format == "dashscope_asr":
            # 阿里云 DashScope：通过列出模型验证 Key
            url = f"{base_url.rstrip('/')}/compatible-mode/v1/models"
            response = get_http_session().get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                return True, "连接成功，阿里云语音服务可用"
            elif response.status_code == 401:
                return False, "API Key无效或已过期"
            elif response.status_code == 429:
                return True, "连接成功（请求频率受限，但Key有效）"
            else:
                return False, f"HTTP {response.status_code}: {response.text[:100]}"

        elif api_format == "tencent_asr":
            # 腾讯云：简单验证 Key 格式（SecretId）
            if len(api_key) < 10:
                return False, "API Key格式不正确"
            return True, "连接配置已保存（腾讯云需实际调用时验证）"

        else:
            return False, f"不支持的API格式: {api_format}"
    except Exception as e:
        return False, f"连接失败: {str(e)[:100]}"


def call_cloud_asr(audio_path, language="zh", log_callback=None):
    """调用云端语音识别API

    支持多家服务商，返回与本地Whisper兼容的segments格式。

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

    provider_id = config.get("provider", "openai")
    if provider_id not in ASR_PROVIDER_CONFIG:
        if log_callback:
            log_callback(f"⚠️ 未知的云端ASR服务商: {provider_id}，请检查配置")
        return None, None
    model = config.get("model", "")
    custom_base_url = config.get("custom_base_url", "").strip()
    provider_cfg = ASR_PROVIDER_CONFIG[provider_id]
    if not model:
        model = provider_cfg.get("default_model", "whisper-1")
    api_format = provider_cfg.get("api_format", "openai_whisper")

    if api_format == "openai_whisper":
        return _call_openai_whisper_api(audio_path, api_key, language, model, custom_base_url, provider_cfg, log_callback)
    elif api_format == "dashscope_asr":
        return _call_dashscope_asr(audio_path, api_key, language, model, custom_base_url, log_callback)
    elif api_format == "tencent_asr":
        return _call_tencent_asr(audio_path, api_key, language, model, log_callback)

    if log_callback:
        log_callback(f"⚠️ 不支持的云端ASR服务商: {provider_id}")
    return None, None


def _call_openai_whisper_api(audio_path, api_key, language, model="whisper-1",
                              custom_base_url="", provider_cfg=None, log_callback=None):
    """调用 OpenAI Whisper API 兼容格式进行语音识别

    适用于: OpenAI, 硅基流动 等 OpenAI 兼容接口
    返回与本地Whisper兼容的segments格式。
    """
    import os

    base_url = custom_base_url if custom_base_url else (provider_cfg or {}).get("base_url", "https://api.openai.com")
    url = f"{base_url.rstrip('/')}/v1/audio/transcriptions"

    provider_name = (provider_cfg or {}).get("name", "OpenAI Whisper")
    if log_callback:
        log_callback(f"☁️ 正在调用云端语音识别: {provider_name} / {model}")

    try:
        with open(audio_path, "rb") as audio_file:
            filename = os.path.basename(audio_path)

            response = get_http_session().post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_file)},
                data={
                    "model": model,
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
            text = seg.get("text", "").strip()
            if text:
                compatible_segments.append({
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": text,
                })

        full_text = result_data.get("text", "")
        if not full_text:
            full_text = "".join(s["text"] for s in compatible_segments)

        if not compatible_segments and not full_text:
            if log_callback:
                log_callback("⚠️ 云端ASR返回空结果")
            return None, None

        if log_callback:
            duration = result_data.get("duration", 0)
            log_callback(f"✅ 云端语音识别完成: {len(compatible_segments)}个片段, 时长{duration:.1f}秒")

        return compatible_segments, full_text

    except Exception as e:
        if log_callback:
            log_callback("=" * 50)
            log_callback(f"❌ 云端ASR调用异常！")
            log_callback(f"   {type(e).__name__}: {str(e)[:150]}")
            log_callback("=" * 50)
        return None, None


def _call_dashscope_asr(audio_path, api_key, language, model="sensevoice-v1",
                         custom_base_url="", log_callback=None):
    """调用阿里云 DashScope 语音识别API

    使用 OpenAI 兼容接口格式
    """
    import os

    base_url = custom_base_url if custom_base_url else "https://dashscope.aliyuncs.com"
    url = f"{base_url.rstrip('/')}/compatible-mode/v1/audio/transcriptions"

    if log_callback:
        log_callback(f"☁️ 正在调用阿里云语音识别: {model}")

    try:
        with open(audio_path, "rb") as audio_file:
            filename = os.path.basename(audio_path)

            response = get_http_session().post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (filename, audio_file)},
                data={
                    "model": model,
                    "language": language,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "segment",
                },
                timeout=300,
            )

        if response.status_code == 401:
            if log_callback:
                log_callback("❌ 阿里云ASR调用失败！API Key无效")
            return None, None

        if response.status_code == 429:
            if log_callback:
                log_callback("⚠️ 阿里云ASR请求频率超限")
            return None, None

        if response.status_code != 200:
            error_detail = ""
            try:
                err = response.json()
                error_detail = err.get("error", {}).get("message", "")[:150] or err.get("message", "")[:150]
            except Exception:
                error_detail = response.text[:150]
            if log_callback:
                log_callback(f"❌ 阿里云ASR调用失败！HTTP {response.status_code}: {error_detail}")
            return None, None

        result_data = response.json()
        segments = result_data.get("segments", [])

        compatible_segments = []
        for seg in segments:
            text = seg.get("text", "").strip()
            if text:
                compatible_segments.append({
                    "start": seg.get("start", 0.0),
                    "end": seg.get("end", 0.0),
                    "text": text,
                })

        full_text = result_data.get("text", "")
        if not full_text:
            full_text = "".join(s["text"] for s in compatible_segments)

        if not compatible_segments and not full_text:
            if log_callback:
                log_callback("⚠️ 阿里云ASR返回空结果")
            return None, None

        if log_callback:
            duration = result_data.get("duration", 0)
            log_callback(f"✅ 阿里云语音识别完成: {len(compatible_segments)}个片段, 时长{duration:.1f}秒")

        return compatible_segments, full_text

    except Exception as e:
        if log_callback:
            log_callback(f"❌ 阿里云ASR调用异常: {type(e).__name__}: {str(e)[:150]}")
        return None, None


def _call_tencent_asr(audio_path, api_key, language, model="16k_zh", log_callback=None):
    """调用腾讯云语音识别API

    注意：腾讯云ASR需要 SecretId + SecretKey，此处 api_key 格式为 "SecretId:SecretKey"
    """
    import os
    import hashlib
    import hmac
    import time
    import json as _json

    if ":" not in api_key:
        if log_callback:
            log_callback("❌ 腾讯云ASR Key格式错误，需要 SecretId:SecretKey")
        return None, None

    secret_id, secret_key = api_key.split(":", 1)

    if log_callback:
        log_callback(f"☁️ 正在调用腾讯云语音识别: {model}")

    try:
        # 读取音频文件并转为base64
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        audio_len = len(audio_data)

        # 腾讯云ASR本地音频上传限制5MB
        if audio_len > 5 * 1024 * 1024:
            if log_callback:
                log_callback(f"❌ 腾讯云ASR音频文件过大: {audio_len / 1024 / 1024:.1f}MB（限制5MB）")
            return None, None

        audio_base64 = base64.b64encode(audio_data).decode("utf-8")

        # 腾讯云ASR 录音文件识别请求
        url = "https://asr.tencentcloudapi.com"

        payload = {
            "EngineModelType": model,
            "ChannelNum": 1,
            "ResTextFormat": 3,  # 含时间戳
            "SourceType": 1,     # 音频URL方式，此处用base64
            "Data": audio_base64,
            "DataLen": audio_len,
        }

        # 构建腾讯云API签名
        service = "asr"
        host = "asr.tencentcloudapi.com"
        action = "CreateRecTask"
        version = "2019-06-14"
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

        # 步骤1：拼接规范请求串
        http_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        payload_str = _json.dumps(payload)
        hashed_payload = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{action.lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        canonical_request = f"{http_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"

        # 步骤2：拼接待签名字符串
        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical}"

        # 步骤3：计算签名
        def _hmac_sha256(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = _hmac_sha256(f"TC3{secret_key}".encode("utf-8"), date)
        secret_service = _hmac_sha256(secret_date, service)
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        # 步骤4：构建Authorization
        authorization = f"{algorithm} Credential={secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        headers = {
            "Authorization": authorization,
            "Content-Type": ct,
            "Host": host,
            "X-TC-Action": action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": version,
        }

        response = get_http_session().post(url, headers=headers, data=payload_str, timeout=30)

        if response.status_code != 200:
            if log_callback:
                log_callback(f"❌ 腾讯云ASR请求失败: HTTP {response.status_code}")
            return None, None

        result = response.json()
        resp_data = result.get("Response", {})
        error_code = resp_data.get("Error", {}).get("Code", "")
        if error_code:
            error_msg = resp_data.get("Error", {}).get("Message", "")
            if log_callback:
                log_callback(f"❌ 腾讯云ASR错误: {error_code} - {error_msg}")
            return None, None

        task_id = resp_data.get("Data", {}).get("TaskId")
        if task_id is None:
            if log_callback:
                log_callback("❌ 腾讯云ASR未返回任务ID")
            return None, None

        # 轮询获取结果
        if log_callback:
            log_callback(f"   任务ID: {task_id}，等待识别完成...")

        for _ in range(60):  # 最多等60秒
            time.sleep(1)

            desc_payload = {"TaskId": task_id}
            desc_str = _json.dumps(desc_payload)
            desc_action = "DescribeTaskStatus"

            # 重新签名
            timestamp2 = int(time.time())
            date2 = time.strftime("%Y-%m-%d", time.gmtime(timestamp2))
            hashed_payload2 = hashlib.sha256(desc_str.encode("utf-8")).hexdigest()
            canonical_headers2 = f"content-type:{ct}\nhost:{host}\nx-tc-action:{desc_action.lower()}\n"
            canonical_request2 = f"{http_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers2}\n{signed_headers}\n{hashed_payload2}"
            credential_scope2 = f"{date2}/{service}/tc3_request"
            hashed_canonical2 = hashlib.sha256(canonical_request2.encode("utf-8")).hexdigest()
            string_to_sign2 = f"{algorithm}\n{timestamp2}\n{credential_scope2}\n{hashed_canonical2}"
            secret_date2 = _hmac_sha256(f"TC3{secret_key}".encode("utf-8"), date2)
            secret_service2 = _hmac_sha256(secret_date2, service)
            secret_signing2 = _hmac_sha256(secret_service2, "tc3_request")
            signature2 = hmac.new(secret_signing2, string_to_sign2.encode("utf-8"), hashlib.sha256).hexdigest()
            authorization2 = f"{algorithm} Credential={secret_id}/{credential_scope2}, SignedHeaders={signed_headers}, Signature={signature2}"

            headers2 = {
                "Authorization": authorization2,
                "Content-Type": ct,
                "Host": host,
                "X-TC-Action": desc_action,
                "X-TC-Timestamp": str(timestamp2),
                "X-TC-Version": version,
            }

            poll_resp = get_http_session().post(url, headers=headers2, data=desc_str, timeout=30)
            if poll_resp.status_code != 200:
                continue

            poll_result = poll_resp.json()
            poll_data = poll_result.get("Response", {})
            status = poll_data.get("Data", {}).get("StatusStr", "")

            if status == "success":
                result_text = poll_data.get("Data", {}).get("Result", "")
                # 解析腾讯云返回的时间戳格式
                compatible_segments = []
                full_text = result_text

                # 尝试解析带时间戳的结果
                try:
                    prd_list = poll_data.get("Data", {}).get("ResultDetail", [])
                    if prd_list:
                        for sentence in prd_list:
                            # SentenceDetail: 句子级别，StartMs/EndMs为毫秒
                            start_ms = sentence.get("StartMs", 0)
                            end_ms = sentence.get("EndMs", 0)
                            text = sentence.get("FinalSentence", sentence.get("Text", "")).strip()
                            if text:
                                compatible_segments.append({
                                    "start": start_ms / 1000.0,  # 毫秒转秒
                                    "end": end_ms / 1000.0,
                                    "text": text,
                                })
                        full_text = "".join(s["text"] for s in compatible_segments) or result_text
                    else:
                        if result_text.strip():
                            compatible_segments = [{"start": 0.0, "end": 0.0, "text": result_text.strip()}]
                        else:
                            compatible_segments = []
                except Exception:
                    if result_text.strip():
                        compatible_segments = [{"start": 0.0, "end": 0.0, "text": result_text.strip()}]
                    else:
                        compatible_segments = []

                if not compatible_segments and not full_text.strip():
                    if log_callback:
                        log_callback("⚠️ 腾讯云ASR返回空结果")
                    return None, None

                if log_callback:
                    log_callback(f"✅ 腾讯云语音识别完成: {len(compatible_segments)}个片段")

                return compatible_segments, full_text

            elif status in ("failed", "error"):
                if log_callback:
                    log_callback(f"❌ 腾讯云ASR识别失败: {poll_data.get('Data', {}).get('ErrorMsg', '未知错误')}")
                return None, None

        if log_callback:
            log_callback("❌ 腾讯云ASR识别超时")
        return None, None

    except Exception as e:
        if log_callback:
            log_callback(f"❌ 腾讯云ASR调用异常: {type(e).__name__}: {str(e)[:150]}")
        return None, None
