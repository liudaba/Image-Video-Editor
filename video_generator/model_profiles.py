# -*- coding: utf-8 -*-
"""制图模型配置矩阵 - 根据不同制图模型调整提示词格式和生成参数"""


# 模型类型常量
MODEL_TYPE_SD15 = "sd15"
MODEL_TYPE_SDXL = "sdxl"
MODEL_TYPE_FLUX = "flux"
MODEL_TYPE_SD3 = "sd3"


# 各模型的完整配置
MODEL_PROFILES = {
    MODEL_TYPE_SD15: {
        "name": "Stable Diffusion 1.5",
        # 提示词格式：权重标记 + 关键词
        "prompt_format": "weighted_keywords",
        # 质量前缀（Ollama 生成提示词时拼在前面）
        "quality_prefix": "(masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), ultra detailed, 8k",
        # 质量后缀（Ollama 生成提示词时拼在后面）
        "quality_suffix": "cinematic lighting, documentary style, (film grain:1.1), film grain texture",
        # 是否需要负面提示词
        "needs_negative": True,
        # 默认负面提示词
        "default_negative": (
            "(worst quality:1.2), (low quality:1.2), cartoon, anime, painting, "
            "illustration, 3d render, sketch, (ugly:1.3), (deformed:1.3), "
            "blurry, disfigured, (bad anatomy:1.2), extra limbs, mutated hands, "
            "(bad hands:1.2), missing fingers, extra digits, cropped, watermark, "
            "text, signature, username, jpeg artifacts, duplicate, morbid"
        ),
        # SD WebUI 生成参数
        "params": {
            "steps": 28,
            "cfg_scale": 7.5,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
        },
        # 是否覆盖 VAE
        "use_vae_override": True,
        "vae_name": "vae-ft-mse-840000-ema-pruned.safetensors",
        # Ollama 生成提示词时使用的模板类型
        "template_key": "shot_prompt_sd",
    },
    MODEL_TYPE_SDXL: {
        "name": "SDXL 1.0",
        # 提示词格式：关键词为主，少量权重标记
        "prompt_format": "keywords_light",
        "quality_prefix": "RAW photo, photorealistic, ultra detailed, 8k",
        "quality_suffix": "cinematic lighting, high quality, professional photography",
        "needs_negative": True,
        "default_negative": (
            "(worst quality:1.2), (low quality:1.2), cartoon, anime, "
            "painting, illustration, 3d render, sketch, blurry, "
            "watermark, text, signature, deformed, ugly"
        ),
        "params": {
            "steps": 30,
            "cfg_scale": 6.0,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
        },
        "use_vae_override": False,
        "vae_name": "",
        "template_key": "shot_prompt_sdxl",
    },
    MODEL_TYPE_FLUX: {
        "name": "Flux Dev",
        # 提示词格式：自然语言句子
        "prompt_format": "natural_language",
        "quality_prefix": "",
        "quality_suffix": "",
        # Flux 不需要负面提示词
        "needs_negative": False,
        "default_negative": "",
        "params": {
            "steps": 25,
            "cfg_scale": 3.5,
            "sampler_name": "Euler",
            "scheduler": "Normal",
        },
        "use_vae_override": False,
        "vae_name": "",
        "template_key": "shot_prompt_flux",
    },
    MODEL_TYPE_SD3: {
        "name": "Stable Diffusion 3",
        # 提示词格式：自然语言 + 少量关键词
        "prompt_format": "natural_language_light",
        "quality_prefix": "",
        "quality_suffix": "cinematic lighting, high quality",
        "needs_negative": True,
        "default_negative": (
            "(worst quality:1.2), (low quality:1.2), blurry, "
            "watermark, text, deformed, ugly"
        ),
        "params": {
            "steps": 28,
            "cfg_scale": 5.0,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
        },
        "use_vae_override": False,
        "vae_name": "",
        "template_key": "shot_prompt_sd3",
    },
}


def detect_model_type(model_name):
    """根据模型名称检测模型类型

    支持的模型名称模式：
    - Flux系列: flux, flx, schnell, dev
    - SDXL系列: sdxl, xl, ssd-1, juggernaut xl, dreamshaper xl, realvis xl
    - SD3系列: sd3, sd 3, stable diffusion 3, sd_3
    - SD1.5系列: 其他所有（默认）

    Args:
        model_name: SD WebUI 中的模型名称，如 "Flux Dev", "SDXL 1.0" 等

    Returns:
        模型类型常量 (MODEL_TYPE_SD15 / SDXL / FLUX / SD3)
    """
    if not model_name or model_name == "使用当前模型":
        return MODEL_TYPE_SD15

    name_lower = model_name.lower()

    if name_lower.startswith('[sdxl]'):
        return MODEL_TYPE_SDXL
    if name_lower.startswith('[flux]'):
        return MODEL_TYPE_FLUX
    if name_lower.startswith('[sd3]'):
        return MODEL_TYPE_SD3
    if name_lower.startswith('[sd1.5]'):
        return MODEL_TYPE_SD15

    import re
    clean_name = re.sub(r'^\[SD1\.5\]\s*|\[SDXL\]\s*|\[Flux\]\s*|\[SD3\]\s*', '', name_lower).strip()
    if clean_name != name_lower:
        name_lower = clean_name

    if any(kw in name_lower for kw in ['flux', 'flx', 'schnell']):
        return MODEL_TYPE_FLUX

    if any(kw in name_lower for kw in ['sdxl', 'xl', 'ssd-1']):
        return MODEL_TYPE_SDXL

    if any(kw in name_lower for kw in ['sd3', 'sd 3', 'stable diffusion 3', 'sd_3']):
        return MODEL_TYPE_SD3

    sdxl_model_hints = [
        'juggernaut', 'dreamshaper', 'realvis', 'dynavision',
        'xlcast', 'xlmore', 'pony', 'animagine',
    ]
    for hint in sdxl_model_hints:
        if hint in name_lower:
            return MODEL_TYPE_SDXL

    return MODEL_TYPE_SD15


def get_model_type_label(model_name):
    """获取模型类型标签（用于UI显示）

    Args:
        model_name: SD WebUI 中的模型名称

    Returns:
        类型标签字符串，如 "[SD1.5]", "[SDXL]", "[Flux]", "[SD3]"
    """
    model_type = detect_model_type(model_name)
    labels = {
        MODEL_TYPE_SD15: "[SD1.5]",
        MODEL_TYPE_SDXL: "[SDXL]",
        MODEL_TYPE_FLUX: "[Flux]",
        MODEL_TYPE_SD3: "[SD3]",
    }
    return labels.get(model_type, "[SD1.5]")


def get_model_profile(model_name):
    """获取模型配置

    Args:
        model_name: SD WebUI 中的模型名称

    Returns:
        模型配置字典
    """
    model_type = detect_model_type(model_name)
    return MODEL_PROFILES[model_type]
