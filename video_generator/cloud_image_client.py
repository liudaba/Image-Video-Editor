# -*- coding: utf-8 -*-
"""Cloud Image Client - 云端生图统一调用客户端

支持的云端生图服务商：
1. SiliconFlow - 硅基流动 (Stable Diffusion XL, FLUX等开源模型云端推理)
2. Stability AI - 官方Stable Diffusion API
3. OpenAI DALL-E 3 - GPT画图模型
4. 通义万相 - 阿里云AI生图

所有服务商通过统一适配层实现一套代码调用多家服务。
"""

import threading
import time
import base64
import os
from .config import get_http_session


IMAGE_PROVIDER_CONFIG = {
    "siliconflow": {
        "name": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": [
            {"id": "stabilityai/stable-diffusion-xl-base-1.0", "name": "SDXL 1.0", "desc": "Stable Diffusion XL，高质量", "max_size": 1024},
            {"id": "stabilityai/stable-diffusion-3-medium", "name": "SD3 Medium", "desc": "Stable Diffusion 3，更精细", "max_size": 1024},
            {"id": "black-forest-labs/FLUX.1-schnell", "name": "FLUX.1-schnell", "desc": "FLUX快速版，极速生成", "max_size": 1024},
            {"id": "black-forest-labs/FLUX.1-dev", "name": "FLUX.1-dev", "desc": "FLUX开发版，高质量", "max_size": 1024},
        ],
        "default_model": "stabilityai/stable-diffusion-xl-base-1.0",
        "api_format": "openai_image",
    },
    "stability": {
        "name": "Stability AI",
        "base_url": "https://api.stability.ai/v2beta",
        "models": [
            {"id": "stable-diffusion-xl", "name": "SDXL 1.0", "desc": "Stable Diffusion XL", "max_size": 1024},
            {"id": "stable-diffusion-3", "name": "SD3", "desc": "Stable Diffusion 3", "max_size": 1024},
            {"id": "stable-image-core", "name": "Core", "desc": "Stability Core，高质量", "max_size": 1024},
        ],
        "default_model": "stable-diffusion-xl",
        "api_format": "stability_v2",
    },
    "openai_dalle": {
        "name": "OpenAI DALL-E",
        "base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "dall-e-3", "name": "DALL-E 3", "desc": "最新版，理解力强，高质量", "max_size": 1024},
            {"id": "gpt-image-1", "name": "GPT-Image-1", "desc": "最新GPT图像模型", "max_size": 1024},
        ],
        "default_model": "dall-e-3",
        "api_format": "openai_image",
    },
    "tongyi_wanxiang": {
        "name": "通义万相",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": [
            {"id": "wanx-v1", "name": "万相V1", "desc": "通义万相基础版", "max_size": 1024},
            {"id": "wanx2.1-t2i-turbo", "name": "万相2.1极速版", "desc": "快速生成，性价比高", "max_size": 1024},
            {"id": "wanx2.1-t2i-plus", "name": "万相2.1增强版", "desc": "高质量，细节丰富", "max_size": 1024},
        ],
        "default_model": "wanx2.1-t2i-turbo",
        "api_format": "openai_image",
    },
}


_cloud_image_lock = threading.Lock()
_cloud_image_config = {
    "enabled": False,
    "provider": "siliconflow",
    "api_key": "",
    "model": "stabilityai/stable-diffusion-xl-base-1.0",
    "custom_base_url": "",
}


def get_cloud_image_config():
    with _cloud_image_lock:
        return _cloud_image_config.copy()


def set_cloud_image_config(config_dict):
    with _cloud_image_lock:
        for k, v in config_dict.items():
            _cloud_image_config[k] = v


def is_cloud_image_enabled():
    with _cloud_image_lock:
        return _cloud_image_config.get("enabled", False) and bool(_cloud_image_config.get("api_key", ""))


def get_image_provider_models(provider_id):
    provider = IMAGE_PROVIDER_CONFIG.get(provider_id)
    if not provider:
        return []
    return provider["models"]


def get_all_image_providers():
    result = []
    for pid, pcfg in IMAGE_PROVIDER_CONFIG.items():
        result.append({
            "id": pid,
            "name": pcfg["name"],
            "default_model": pcfg["default_model"],
            "model_count": len(pcfg["models"]),
        })
    return result


def get_effective_image_base_url():
    with _cloud_image_lock:
        custom = _cloud_image_config.get("custom_base_url", "").strip()
        if custom:
            return custom.rstrip("/")
        provider_id = _cloud_image_config.get("provider", "siliconflow")
        provider = IMAGE_PROVIDER_CONFIG.get(provider_id, {})
        return provider.get("base_url", "").rstrip("/")


def call_cloud_image(prompt, negative_prompt="", width=1024, height=576,
                     log_callback=None):
    """统一的云端生图调用函数

    Args:
        prompt: 正向提示词
        negative_prompt: 负向提示词
        width: 图片宽度
        height: 图片高度
        log_callback: 日志回调

    Returns:
        tuple: (image_base64, model_name) 或 (None, None)
    """
    with _cloud_image_lock:
        config = _cloud_image_config.copy()

    api_key = config.get("api_key", "")
    if not api_key:
        if log_callback:
            log_callback("⚠️ 云端生图API Key未设置")
        return None, None

    provider_id = config.get("provider", "siliconflow")
    if provider_id not in IMAGE_PROVIDER_CONFIG:
        if log_callback:
            log_callback(f"⚠️ 未知的云端生图服务商: {provider_id}，请检查配置")
        return None, None
    model = config.get("model", "")
    if not model:
        provider = IMAGE_PROVIDER_CONFIG.get(provider_id, {})
        model = provider.get("default_model", "")
    if not model:
        # 从模型列表中取第一个
        models = IMAGE_PROVIDER_CONFIG.get(provider_id, {}).get("models", [])
        if models:
            model = models[0]["id"]
    if not model:
        if log_callback:
            log_callback("⚠️ 云端生图模型未指定，请选择模型")
        return None, None

    provider = IMAGE_PROVIDER_CONFIG[provider_id]
    api_format = provider.get("api_format", "openai_image")

    if api_format == "openai_image":
        return _call_openai_image_format(prompt, negative_prompt, width, height,
                                          api_key, provider_id, model, log_callback)
    elif api_format == "stability_v2":
        return _call_stability_v2(prompt, negative_prompt, width, height,
                                   api_key, provider_id, model, log_callback)

    if log_callback:
        log_callback(f"⚠️ 不支持的云端生图API格式: {api_format}")
    return None, None


def _call_openai_image_format(prompt, negative_prompt, width, height,
                               api_key, provider_id, model, log_callback=None):
    """调用 OpenAI Images API 兼容格式的云端生图

    适用于: SiliconFlow, OpenAI DALL-E, 通义万相
    """
    base_url = get_effective_image_base_url()
    url = f"{base_url}/images/generations"

    provider = IMAGE_PROVIDER_CONFIG.get(provider_id, {})
    max_size = 1024
    for m in provider.get("models", []):
        if m["id"] == model:
            max_size = m.get("max_size", 1024)
            break

    adj_w = min(width, max_size)
    adj_h = min(height, max_size)
    if adj_w % 8 != 0:
        adj_w = (adj_w // 8) * 8
    if adj_h % 8 != 0:
        adj_h = (adj_h // 8) * 8

    if (adj_w != width or adj_h != height) and log_callback:
        log_callback(f"⚠️ 云端模型最大尺寸{max_size}px，已将 {width}x{height} 调整为 {adj_w}x{adj_h}")

    request_body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": f"{adj_w}x{adj_h}",
        "response_format": "b64_json",
    }

    if provider_id == "siliconflow" and negative_prompt:
        request_body["negative_prompt"] = negative_prompt

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    if log_callback:
        provider_name = provider.get("name", provider_id)
        log_callback(f"☁️ 正在调用云端生图: {provider_name} / {model}")

    try:
        session = get_http_session()
        response = session.post(
            url,
            headers=headers,
            json=request_body,
            timeout=180,
        )

        if response.status_code == 401:
            if log_callback:
                log_callback("❌ 云端生图API Key无效或已过期")
            return None, None

        if response.status_code == 429:
            if log_callback:
                log_callback("⚠️ 云端生图请求频率超限，请稍后重试")
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
                log_callback(f"❌ 云端生图失败！HTTP {response.status_code}: {error_detail[:120]}")
            return None, None

        result_data = response.json()

        images = result_data.get("data", [])
        if not images:
            if log_callback:
                log_callback("⚠️ 云端生图返回空结果")
            return None, None

        image_item = images[0]

        b64_data = image_item.get("b64_json", "")
        if not b64_data:
            image_url = image_item.get("url", "")
            if image_url:
                if log_callback:
                    log_callback("☁️ 正在下载云端生成的图片...")
                try:
                    img_response = session.get(image_url, timeout=60)
                    if img_response.status_code == 200:
                        b64_data = base64.b64encode(img_response.content).decode("utf-8")
                    else:
                        if log_callback:
                            log_callback(f"❌ 图片下载失败: HTTP {img_response.status_code}")
                        return None, None
                except Exception as e:
                    if log_callback:
                        log_callback(f"❌ 图片下载异常: {e}")
                    return None, None
            else:
                if log_callback:
                    log_callback("⚠️ 云端生图返回结果中无图片数据")
                return None, None

        if log_callback:
            log_callback(f"✅ 云端生图成功: {model} ({adj_w}x{adj_h})")

        return b64_data, model

    except Exception as e:
        if log_callback:
            log_callback(f"❌ 云端生图调用异常: {type(e).__name__}: {str(e)[:120]}")
        return None, None


def _call_stability_v2(prompt, negative_prompt, width, height,
                        api_key, provider_id, model, log_callback=None):
    """调用 Stability AI v2beta API 格式的云端生图"""
    base_url = get_effective_image_base_url()

    # 根据模型选择正确的endpoint
    endpoint_map = {
        "stable-diffusion-xl": "sdxl",
        "stable-diffusion-3": "sd3",
        "stable-image-core": "core",
    }
    endpoint = endpoint_map.get(model, "sd3")
    url = f"{base_url}/stable-image/generate/{endpoint}"

    max_size = 1024
    adj_w = min(width, max_size)
    adj_h = min(height, max_size)

    if (adj_w != width or adj_h != height) and log_callback:
        log_callback(f"⚠️ 云端模型最大尺寸{max_size}px，已将 {width}x{height} 调整为 {adj_w}x{adj_h}")

    form_data = {
        "prompt": prompt,
        "output_format": "png",
        "aspect_ratio": _get_aspect_ratio(adj_w, adj_h),
    }
    # core endpoint 不支持 negative_prompt，sdxl 和 sd3 支持
    if negative_prompt and endpoint in ("sdxl", "sd3"):
        form_data["negative_prompt"] = negative_prompt

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*",
    }

    if log_callback:
        log_callback(f"☁️ 正在调用Stability AI生图: {model}")

    try:
        session = get_http_session()
        response = session.post(
            url,
            headers=headers,
            files={"none": ""},
            data=form_data,
            timeout=180,
        )

        if response.status_code == 401:
            if log_callback:
                log_callback("❌ Stability AI API Key无效")
            return None, None

        if response.status_code == 429:
            if log_callback:
                log_callback("⚠️ Stability AI请求频率超限")
            return None, None

        if response.status_code != 200:
            if log_callback:
                log_callback(f"❌ Stability AI生图失败: HTTP {response.status_code}")
            return None, None

        b64_data = base64.b64encode(response.content).decode("utf-8")

        if log_callback:
            log_callback(f"✅ Stability AI生图成功")

        return b64_data, model

    except Exception as e:
        if log_callback:
            log_callback(f"❌ Stability AI调用异常: {type(e).__name__}: {str(e)[:120]}")
        return None, None


def _get_aspect_ratio(w, h):
    """根据宽高返回最接近的标准宽高比字符串"""
    ratio = w / h
    ratios = {
        "1:1": 1.0,
        "16:9": 16/9,
        "21:9": 21/9,
        "2:3": 2/3,
        "3:2": 3/2,
        "4:5": 4/5,
        "5:4": 5/4,
        "9:16": 9/16,
        "9:21": 9/21,
    }
    closest = min(ratios.items(), key=lambda x: abs(x[1] - ratio))
    return closest[0]


def test_cloud_image_connection(api_key, provider_id, model=None, custom_base_url=""):
    """测试云端生图连接

    Returns:
        tuple: (success, message)
    """
    provider = IMAGE_PROVIDER_CONFIG.get(provider_id)
    if not provider:
        return False, f"未知服务商: {provider_id}"

    if not model:
        model = provider["default_model"]

    api_format = provider.get("api_format", "openai_image")

    if api_format == "openai_image":
        base_url = custom_base_url.strip().rstrip("/") if custom_base_url.strip() else provider["base_url"].rstrip("/")
        url = f"{base_url}/images/generations"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        request_body = {
            "model": model,
            "prompt": "a beautiful sunset",
            "n": 1,
            "size": "512x512",
            "response_format": "b64_json",
        }

        try:
            session = get_http_session()
            response = session.post(url, headers=headers, json=request_body, timeout=60)

            if response.status_code == 401:
                return False, "API Key无效或已过期"
            if response.status_code == 429:
                return True, "连接成功（请求频率受限，请稍后使用）"
            if response.status_code != 200:
                try:
                    err = response.json().get("error", {}).get("message", "")[:100]
                except Exception:
                    err = response.text[:100]
                return False, f"API错误 ({response.status_code}): {err}"

            result_data = response.json()
            images = result_data.get("data", [])
            if images:
                return True, f"连接成功！模型 {model} 生图正常"
            return True, "连接成功（但返回空结果，请检查模型名称）"

        except Exception as e:
            return False, f"连接失败: {type(e).__name__} - {str(e)[:80]}"

    elif api_format == "stability_v2":
        base_url = custom_base_url.strip().rstrip("/") if custom_base_url.strip() else provider["base_url"].rstrip("/")

        try:
            session = get_http_session()
            response = session.get(
                f"{base_url}/user/account",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            if response.status_code == 200:
                return True, f"连接成功！Stability AI 账号验证通过"
            elif response.status_code == 401:
                return False, "API Key无效"
            else:
                return True, f"连接可能成功（HTTP {response.status_code}）"
        except Exception as e:
            return False, f"连接失败: {type(e).__name__} - {str(e)[:80]}"

    return False, f"不支持的API格式: {api_format}"
