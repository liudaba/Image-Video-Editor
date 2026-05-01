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

    Args:
        model_name: SD WebUI 中的模型名称，如 "Flux Dev", "SDXL 1.0" 等

    Returns:
        模型类型常量 (MODEL_TYPE_SD15 / SDXL / FLUX / SD3)
    """
    if not model_name or model_name == "使用当前模型":
        return MODEL_TYPE_SD15

    name_lower = model_name.lower()

    # Flux 系列（优先检测，因为名称最独特）
    if "flux" in name_lower:
        return MODEL_TYPE_FLUX

    # SDXL 系列
    if "sdxl" in name_lower or "xl" in name_lower:
        return MODEL_TYPE_SDXL

    # SD3 系列
    if "sd3" in name_lower or "stable diffusion 3" in name_lower or "sd_3" in name_lower:
        return MODEL_TYPE_SD3

    # 默认 SD 1.5
    return MODEL_TYPE_SD15


def get_model_profile(model_name):
    """获取模型配置

    Args:
        model_name: SD WebUI 中的模型名称

    Returns:
        模型配置字典
    """
    model_type = detect_model_type(model_name)
    return MODEL_PROFILES[model_type]
