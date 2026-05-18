# -*- coding: utf-8 -*-
"""
针对 absoluteRealisticVision v20 模型的提示词工具
仅保留质量标签和基础映射，让大模型自主生成
"""


class ARVPromptTemplates:
    """absoluteRealisticVision v20 专用质量标签和基础工具"""

    QUALITY_PREFIX = "(masterpiece, best quality, ultra detailed, 8k:1.2), RAW photo, (photorealistic:1.3), DSLR, high resolution"

    STYLE_TAGS = {
        "documentary": "documentary photography, (film grain:1.1), photojournalism style",
        "cinematic": "(cinematic shot:1.2), dramatic lighting, high contrast, (film grain:1.1), anamorphic lens",
        "news": "breaking news broadcast, (professional broadcast quality:1.1), live report style",
        "war": "(war photojournalism:1.3), battlefield documentary, combat zone, press photography",
    }

    COMPOSITION_TAGS = {
        "close_up": "(close-up shot:1.2), detailed focus, (shallow depth of field:1.1), bokeh background",
        "medium": "medium shot, eye level perspective, balanced composition, 50mm lens",
        "wide": "(wide angle shot:1.1), establishing view, panoramic vista, 24mm lens",
        "aerial": "(aerial drone footage:1.2), overhead view, bird's eye perspective",
    }

    LIGHTING_TAGS = {
        "dramatic": "(dramatic chiaroscuro lighting:1.2), strong shadows, high contrast, Rembrandt lighting",
        "natural": "natural lighting, soft ambient light, balanced exposure, diffused daylight",
        "golden": "(golden hour lighting:1.2), warm tones, cinematic glow, sunset rim light",
        "harsh": "harsh lighting, strong directional light, deep shadows, hard edge shadows",
        "moody": "(moody atmosphere:1.1), dim lighting, mysterious ambiance, low key lighting",
    }

    @classmethod
    def generate_prompt(cls, dubbing_text: str, content_type: str = "general",
                        core_theme: str = "", visual_tone: str = "",
                        model_type: str = "sd15") -> str:
        style = cls._select_style(content_type)
        composition = cls._select_composition(content_type)
        lighting = cls._select_lighting(visual_tone)

        if model_type in ('flux', 'sd3'):
            import re as _re
            def _strip_weights(text):
                text = _re.sub(r'\(([^)]+):[\d.]+\)', r'\1', text)
                text = _re.sub(r'\[([^]]+):[\d.]+\]', r'\1', text)
                text = _re.sub(r'\(\(([^)]+)\)\)', r'\1', text)
                return text
            parts = []
            style_tag = _strip_weights(cls.STYLE_TAGS.get(style, ""))
            comp_tag = _strip_weights(cls.COMPOSITION_TAGS.get(composition, ""))
            light_tag = _strip_weights(cls.LIGHTING_TAGS.get(lighting, ""))
            if style_tag:
                parts.append(style_tag)
            if comp_tag:
                parts.append(comp_tag)
            if light_tag:
                parts.append(light_tag)
            if core_theme:
                parts.append(core_theme)
            if model_type == 'flux':
                sentence = 'A scene with ' + ', and '.join(p.strip() for p in parts if p.strip())
                sentence = sentence.rstrip(', and ')
            else:
                sentence = '. '.join(p.strip().capitalize() for p in parts if p.strip())
            if sentence and not sentence[0].isupper():
                sentence = sentence[0].upper() + sentence[1:]
            return sentence if sentence else "A cinematic scene"

        if model_type == 'sdxl':
            quality_prefix = "RAW photo, photorealistic, ultra detailed, 8k"
        else:
            quality_prefix = cls.QUALITY_PREFIX

        parts = [quality_prefix]
        parts.append(cls.STYLE_TAGS.get(style, ""))
        parts.append(cls.COMPOSITION_TAGS.get(composition, ""))
        parts.append(cls.LIGHTING_TAGS.get(lighting, ""))

        if core_theme:
            parts.append(core_theme)
        
        return ", ".join(p for p in parts if p)

    @classmethod
    def _select_composition(cls, content_type: str) -> str:
        if content_type in ["military", "war", "space"]:
            return "wide"
        elif content_type in ["politics", "news"]:
            return "medium"
        return "medium"

    @classmethod
    def _select_lighting(cls, visual_tone: str) -> str:
        if visual_tone:
            if any(w in visual_tone for w in ["紧张", "危机", "冲突", "tense", "crisis"]):
                return "dramatic"
            elif any(w in visual_tone for w in ["希望", "胜利", "hope", "victory", "温暖"]):
                return "golden"
        return "natural"

    @classmethod
    def _select_style(cls, content_type: str) -> str:
        if content_type in ["military", "war"]:
            return "war"
        elif content_type in ["news"]:
            return "news"
        return "documentary"


def quick_generate_arv_prompt(dubbing_text: str, content_type: str = "general") -> str:
    return ARVPromptTemplates.generate_prompt(dubbing_text, content_type)
