# -*- coding: utf-8 -*-
"""
针对 absoluteRealisticVision v20 模型的提示词工具
仅保留质量标签和基础映射，让大模型自主生成
"""
import re as _re


# 中文关键词→英文场景描述映射表（用于ARV回退时将配音文本转为视觉场景）
_DUBBING_SCENE_MAP = {
    # 政治/权力
    '政治': 'political scene, government building',
    '总统': 'president at podium, national leader',
    '总理': 'prime minister in office, government leader',
    '政府': 'government building interior, official hall',
    '权力': 'power symbol, leader in command',
    '选举': 'election rally, voting scene, ballot boxes',
    '反对派': 'opposition gathering, protest crowd',
    '执政': 'ruling party headquarters, political power',
    # 军事/战争
    '军事': 'military base, soldiers in formation',
    '军方': 'military headquarters, armed forces',
    '战争': 'war zone, battlefield, combat',
    '士兵': 'armed soldiers, military personnel',
    '导弹': 'missile launch, military weapons',
    '坦克': 'tanks on battlefield, armored vehicles',
    '武装': 'armed forces, military equipment',
    # 经济/能源
    '经济': 'financial district, stock exchange',
    '石油': 'oil refinery, petroleum industry',
    '制裁': 'economic sanctions, restricted trade',
    '金融': 'banking, financial center',
    '通胀': 'economic hardship, rising prices',
    # 社会/民生
    '难民': 'refugees at border, displaced people',
    '民生': 'civilian daily life, community scene',
    '民众': 'crowd of people, public gathering',
    '食品': 'food distribution, market scene',
    '腐败': 'corruption scene, wealth disparity',
    # 司法
    '审判': 'courtroom, judicial proceedings',
    '法院': 'courtroom interior, judge bench',
    '逮捕': 'arrest scene, law enforcement',
    # 人物
    '将军': 'military general in uniform',
    '外交官': 'diplomat at negotiation table',
    '夫妇': 'couple in formal setting',
    '妻子': 'woman in formal attire',
    # 地点
    '委内瑞拉': 'Venezuela, Caracas cityscape',
    '俄罗斯': 'Russia, Moscow skyline',
    '中国': 'China, Beijing landmarks',
    '美国': 'United States, Washington DC',
    # 自然/科学
    '宇宙': 'deep space, cosmic scene',
    '黑洞': 'black hole, space phenomenon',
    '森林': 'dense forest, woodland',
    '海洋': 'ocean view, sea landscape',
    '进化': 'evolution concept, life progression',
    '科学': 'laboratory, scientific research',
    # 情感/氛围
    '危机': 'crisis atmosphere, tense situation',
    '希望': 'hopeful scene, warm light',
    '紧张': 'tense atmosphere, dramatic moment',
    '胜利': 'victory celebration, triumph',
}


def _extract_scene_from_dubbing(dubbing_text: str) -> str:
    """从配音文本中提取关键视觉场景描述

    通过关键词匹配将中文配音文本转换为英文场景描述，
    确保ARV回退生成的提示词与配音内容语义相关。
    """
    if not dubbing_text:
        return ""

    scene_parts = []
    seen = set()

    for cn_key, en_scene in _DUBBING_SCENE_MAP.items():
        if cn_key in dubbing_text and en_scene not in seen:
            scene_parts.append(en_scene)
            seen.add(en_scene)
            if len(scene_parts) >= 3:
                break

    return ", ".join(scene_parts)


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

    # 非写实风格的替代质量标签
    NON_REALISTIC_PREFIX = "masterpiece, best quality, ultra detailed, vibrant colors, artistic style"
    NON_REALISTIC_STYLES = {
        "pixar": "Pixar style, 3D animation, soft lighting, smooth textures, cute characters",
        "ghibli": "Studio Ghibli style, hand-drawn animation, watercolor backgrounds, dreamy atmosphere",
        "anime": "anime style, cel shading, vibrant colors, manga aesthetic",
        "oil_painting": "oil painting, brush strokes, classical art, textured canvas, rich colors",
        "watercolor": "watercolor painting, soft edges, flowing colors, pastel tones, paper texture",
        "sketch": "line art, ink drawing, monochrome, clean lines, high contrast",
        "cyberpunk": "cyberpunk, neon lights, futuristic, holographic displays, dark atmosphere",
        "van_gogh": "Van Gogh style, impressionism, swirling brushstrokes, vivid colors",
        "da_vinci": "Leonardo da Vinci style, Renaissance painting, sfumato technique, warm earth tones",
    }

    @classmethod
    def generate_prompt(cls, dubbing_text: str, content_type: str = "general",
                        core_theme: str = "", visual_tone: str = "",
                        model_type: str = "sd15", user_styles: list = None) -> str:
        style = cls._select_style(content_type)
        composition = cls._select_composition(content_type)
        lighting = cls._select_lighting(visual_tone)

        # 从配音文本中提取视觉场景描述
        scene_from_dubbing = _extract_scene_from_dubbing(dubbing_text)

        # 检测用户是否选择了非写实风格
        is_non_realistic = False
        non_realistic_style_tag = ""
        if user_styles:
            style_text_lower = " ".join(user_styles).lower()
            nr_keywords = {
                'pixar': 'pixar', '皮克斯': 'pixar',
                'ghibli': 'ghibli', '吉卜力': 'ghibli',
                'anime': 'anime', '动漫': 'anime', '日式动漫': 'anime',
                'oil painting': 'oil_painting', '油画': 'oil_painting',
                'watercolor': 'watercolor', '水彩': 'watercolor',
                'line art': 'sketch', '黑白线条': 'sketch',
                'cyberpunk': 'cyberpunk', '赛博朋克': 'cyberpunk',
                'van gogh': 'van_gogh', '梵高': 'van_gogh',
                'da vinci': 'da_vinci', '达芬奇': 'da_vinci',
            }
            for kw, style_key in nr_keywords.items():
                if kw in style_text_lower:
                    is_non_realistic = True
                    non_realistic_style_tag = cls.NON_REALISTIC_STYLES.get(style_key, "")
                    break

        def _strip_weights(text):
            text = _re.sub(r'\(([^)]+):[\d.]+\)', r'\1', text)
            text = _re.sub(r'\[([^]]+):[\d.]+\]', r'\1', text)
            text = _re.sub(r'\(\(([^)]+)\)\)', r'\1', text)
            return text

        if model_type in ('flux', 'sd3'):
            parts = []
            if is_non_realistic and non_realistic_style_tag:
                parts.append(_strip_weights(non_realistic_style_tag))
            else:
                style_tag = _strip_weights(cls.STYLE_TAGS.get(style, ""))
                if style_tag:
                    parts.append(style_tag)
            comp_tag = _strip_weights(cls.COMPOSITION_TAGS.get(composition, ""))
            light_tag = _strip_weights(cls.LIGHTING_TAGS.get(lighting, ""))
            if comp_tag:
                parts.append(comp_tag)
            if not is_non_realistic and light_tag:
                parts.append(light_tag)
            if scene_from_dubbing:
                parts.append(scene_from_dubbing)
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

        # SD15 / SDXL 路径
        if is_non_realistic:
            quality_prefix = cls.NON_REALISTIC_PREFIX
            if model_type == 'sdxl':
                quality_prefix = "masterpiece, best quality, ultra detailed, vibrant colors, artistic style"
        elif model_type == 'sdxl':
            quality_prefix = "RAW photo, photorealistic, ultra detailed, 8k"
        else:
            quality_prefix = cls.QUALITY_PREFIX

        parts = [quality_prefix]

        if is_non_realistic and non_realistic_style_tag:
            parts.append(non_realistic_style_tag)
        else:
            parts.append(cls.STYLE_TAGS.get(style, ""))

        parts.append(cls.COMPOSITION_TAGS.get(composition, ""))

        if not is_non_realistic:
            parts.append(cls.LIGHTING_TAGS.get(lighting, ""))

        # 将配音文本场景描述插入提示词（核心修复：确保语义相关）
        if scene_from_dubbing:
            parts.append(scene_from_dubbing)

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


def quick_generate_arv_prompt(dubbing_text: str, content_type: str = "general",
                             core_theme: str = "", visual_tone: str = "",
                             model_type: str = "sd15", user_styles: list = None) -> str:
    return ARVPromptTemplates.generate_prompt(dubbing_text, content_type, core_theme,
                                              visual_tone, model_type, user_styles)
