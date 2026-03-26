# -*- coding: utf-8 -*-
"""
针对 absoluteRealisticVision v20 模型优化的提示词模板系统

这个模块提供专门针对 absoluteRealisticVision 写实模型的提示词优化，
确保生成的提示词既快速又高质量。

关键特点：
1. 固定的质量标签前缀，确保一致性
2. 电影纪实风格的视觉元素库
3. 针对不同内容类型的专用模板
4. 高效的提示词生成逻辑
"""

class ARVPromptTemplates:
    """absoluteRealisticVision v20 专用提示词模板"""
    
    # ========== 固定质量标签前缀 ==========
    # 这些标签确保每张图片都有稳定的质量基线
    QUALITY_PREFIX = "masterpiece, best quality, ultra detailed, 8k, photorealistic"
    
    # ========== 风格标签 ==========
    STYLE_TAGS = {
        "documentary": "documentary style, war photojournalism, film grain texture",
        "cinematic": "cinematic shot, dramatic lighting, high contrast, film grain",
        "news": "breaking news broadcast style, professional broadcast quality",
        "war": "war photojournalism, battlefield documentary, combat zone",
    }
    
    # ========== 构图标签 ==========
    COMPOSITION_TAGS = {
        "close_up": "close-up shot, detailed focus, shallow depth of field",
        "medium": "medium shot, eye level perspective, balanced composition",
        "wide": "wide angle shot, establishing view, panoramic vista",
        "aerial": "aerial drone footage, overhead view, bird's eye perspective",
    }
    
    # ========== 光线标签 ==========
    LIGHTING_TAGS = {
        "dramatic": "dramatic chiaroscuro lighting, strong shadows, high contrast",
        "natural": "natural lighting, soft ambient light, balanced exposure",
        "golden": "golden hour lighting, warm tones, cinematic glow",
        "harsh": "harsh lighting, strong directional light, deep shadows",
        "moody": "moody atmosphere, dim lighting, mysterious ambiance",
    }
    
    # ========== 内容类型专用视觉元素库 ==========
    # 每种内容类型都有预先设计好的视觉元素组合
    CONTENT_VISUAL_ELEMENTS = {
        "military": {
            "primary": ["military equipment", "soldiers", "tanks", "weapons", "battlefield"],
            "secondary": ["smoke", "fire", "explosions", "debris", "ruins"],
            "environment": ["destroyed buildings", "trenches", "military base", "war zone"],
            "atmosphere": ["tense", "chaotic", "intense", "dangerous"],
        },
        "politics": {
            "primary": ["government officials", "diplomats", "politicians", "leaders"],
            "secondary": ["documents", "flags", "podiums", "meeting rooms"],
            "environment": ["government building", "parliament", "conference room", "embassy"],
            "atmosphere": ["formal", "serious", "authoritative", "professional"],
        },
        "space": {
            "primary": ["celestial bodies", "stars", "planets", "galaxies", "nebulae"],
            "secondary": ["spacecraft", "satellites", "astronauts", "telescopes"],
            "environment": ["deep space", "cosmic void", "stellar backdrop", "orbit"],
            "atmosphere": ["mysterious", "vast", "awe-inspiring", "otherworldly"],
        },
        "science": {
            "primary": ["scientists", "researchers", "laboratory equipment", "experiments"],
            "secondary": ["data visualization", "microscopes", "test tubes", "computers"],
            "environment": ["laboratory", "research facility", "university", "clinic"],
            "atmosphere": ["analytical", "precise", "innovative", "focused"],
        },
        "technology": {
            "primary": ["engineers", "technicians", "computers", "electronics"],
            "secondary": ["circuit boards", "screens", "robots", "machinery"],
            "environment": ["tech lab", "factory", "data center", "workshop"],
            "atmosphere": ["modern", "innovative", "sleek", "advanced"],
        },
        "news": {
            "primary": ["news anchor", "journalists", "reporters", "camera crew"],
            "secondary": ["microphones", "cameras", "teleprompters", "screens"],
            "environment": ["news studio", "broadcast room", "press conference", "field location"],
            "atmosphere": ["urgent", "professional", "authoritative", "informative"],
        },
        "economy": {
            "primary": ["business people", "traders", "analysts", "executives"],
            "secondary": ["charts", "graphs", "financial data", "stock tickers"],
            "environment": ["stock exchange", "office", "bank", "corporate building"],
            "atmosphere": ["professional", "dynamic", "competitive", "global"],
        },
        "general": {
            "primary": ["people", "crowds", "individuals", "groups"],
            "secondary": ["everyday objects", "urban elements", "nature elements"],
            "environment": ["urban setting", "rural setting", "indoor", "outdoor"],
            "atmosphere": ["neutral", "balanced", "realistic", "authentic"],
        },
    }
    
    # ========== 中文到英文的关键词映射 ==========
    # 用于快速将中文配音内容转换为英文提示词
    KEYWORD_MAPPINGS = {
        # 国家/地区
        "伊朗": "Iran, Iranian, Middle East",
        "美国": "USA, American, United States",
        "中国": "China, Chinese",
        "俄罗斯": "Russia, Russian",
        "以色列": "Israel, Israeli",
        "欧洲": "Europe, European",
        "中东": "Middle East",
        
        # 军事/战争
        "战争": "war, warfare, conflict, battle",
        "战斗": "combat, fighting, battle",
        "军队": "military, armed forces, troops",
        "士兵": "soldiers, troops, military personnel",
        "坦克": "tanks, armored vehicles",
        "导弹": "missile, rocket, projectile",
        "无人机": "drone, UAV, unmanned aerial vehicle",
        "战斗机": "fighter jet, military aircraft",
        "爆炸": "explosion, blast, detonation",
        "轰炸": "bombing, airstrike, bombardment",
        
        # 政治/政府
        "政府": "government, administration, officials",
        "总统": "president, head of state, leader",
        "部长": "minister, cabinet member",
        "会议": "meeting, conference, summit",
        "谈判": "negotiation, talks, diplomacy",
        "制裁": "sanctions, economic restrictions",
        
        # 媒体/新闻
        "新闻": "news, breaking news, news broadcast",
        "报道": "report, coverage, journalism",
        "记者": "journalist, reporter, correspondent",
        "主持人": "anchor, presenter, broadcaster",
        "直播": "live broadcast, livestream",
        
        # 时间/状态
        "今天": "today, current events, breaking",
        "最新": "latest, recent, breaking",
        "紧急": "urgent, emergency, breaking",
        "刚刚": "just happened, breaking, latest",
        
        # 情感/氛围
        "紧张": "tense, tense atmosphere, crisis",
        "危机": "crisis, emergency, critical situation",
        "冲突": "conflict, confrontation, clash",
        "希望": "hope, hopeful, optimistic",
        "胜利": "victory, triumphant, success",
        "失败": "failure, defeat, loss",
    }
    
    # ========== 预设场景模板 ==========
    # 这些是预先设计好的完整场景描述，可以直接使用
    SCENE_TEMPLATES = {
        "war_overview": {
            "prompt": "battlefield overview, destroyed tanks and vehicles, smoke rising from ruins, military helicopters overhead, war documentary footage, gray overcast sky",
            "composition": "wide",
            "lighting": "dramatic",
            "style": "war",
        },
        "news_studio": {
            "prompt": "news broadcast studio, anchor at desk, multiple screens showing world map with conflict zones, professional lighting, breaking news graphics",
            "composition": "medium",
            "lighting": "natural",
            "style": "news",
        },
        "military_base": {
            "prompt": "military installation, soldiers in formation, armored vehicles, command center with satellite dishes, strategic operations",
            "composition": "wide",
            "lighting": "natural",
            "style": "documentary",
        },
        "government_meeting": {
            "prompt": "government officials in formal meeting, conference table with documents, flags, serious discussion, official setting",
            "composition": "medium",
            "lighting": "natural",
            "style": "documentary",
        },
        "crisis_scene": {
            "prompt": "crisis situation, emergency response, damaged infrastructure, humanitarian concerns, tense atmosphere",
            "composition": "wide",
            "lighting": "dramatic",
            "style": "documentary",
        },
    }
    
    @classmethod
    def generate_prompt(cls, dubbing_text: str, content_type: str = "general", 
                        core_theme: str = "", visual_tone: str = "") -> str:
        """
        生成针对 absoluteRealisticVision 模型的优化提示词
        
        Args:
            dubbing_text: 配音文本内容
            content_type: 内容类型 (military, politics, news, etc.)
            visual_tone: 视觉基调
            
        Returns:
            优化后的英文提示词
        """
        # 1. 从配音文本中提取关键视觉元素
        visual_elements = cls._extract_visual_elements(dubbing_text, content_type)
        
        # 2. 获取内容类型专用的视觉元素
        content_elements = cls.CONTENT_VISUAL_ELEMENTS.get(content_type, cls.CONTENT_VISUAL_ELEMENTS["general"])
        
        # 3. 选择合适的构图和光线
        composition = cls._select_composition(dubbing_text, content_type)
        lighting = cls._select_lighting(dubbing_text, visual_tone)
        
        # 4. 构建最终提示词
        parts = [
            cls.QUALITY_PREFIX,
            visual_elements,
            content_elements["primary"][0] if content_elements["primary"] else "",
            content_elements["environment"][0] if content_elements["environment"] else "",
            cls.COMPOSITION_TAGS.get(composition, ""),
            cls.LIGHTING_TAGS.get(lighting, ""),
            cls.STYLE_TAGS.get("documentary", ""),
        ]
        
        # 过滤空字符串并组合
        prompt = ", ".join(p for p in parts if p)
        
        return prompt
    
    @classmethod
    def _extract_visual_elements(cls, text: str, content_type: str) -> str:
        """从文本中提取视觉元素"""
        elements = []
        text_lower = text.lower()
        
        for cn_key, en_value in cls.KEYWORD_MAPPINGS.items():
            if cn_key in text:
                elements.append(en_value)
        
        return ", ".join(elements[:5]) if elements else ""
    
    @classmethod
    def _select_composition(cls, text: str, content_type: str) -> str:
        """选择合适的构图"""
        # 根据内容类型选择默认构图
        if content_type in ["military", "war"]:
            return "wide"
        elif content_type in ["politics", "news"]:
            return "medium"
        elif content_type in ["space"]:
            return "wide"
        return "medium"
    
    @classmethod
    def _select_lighting(cls, text: str, visual_tone: str) -> str:
        """选择合适的光线"""
        # 根据视觉基调选择
        if visual_tone:
            if any(w in visual_tone for w in ["紧张", "危机", "冲突", "tense", "crisis"]):
                return "dramatic"
            elif any(w in visual_tone for w in ["希望", "胜利", "hope", "victory"]):
                return "golden"
        
        # 根据文本内容选择
        if any(w in text for w in ["战争", "战斗", "冲突", "爆炸", "war", "battle"]):
            return "dramatic"
        elif any(w in text for w in ["新闻", "报道", "会议", "news", "meeting"]):
            return "natural"
        
        return "natural"


# ========== 快速提示词生成函数 ==========
def quick_generate_arv_prompt(dubbing_text: str, content_type: str = "general") -> str:
    """
    快速生成针对 absoluteRealisticVision 的提示词
    这是最高效的生成方式，适合大批量处理
    
    Args:
        dubbing_text: 配音文本
        content_type: 内容类型
        
    Returns:
        优化后的提示词
    """
    return ARVPromptTemplates.generate_prompt(dubbing_text, content_type)


# ========== 预设的高质量提示词模板 ==========
# 这些模板可以直接用于常见场景，无需调用大模型
PRESET_PROMPTS = {
    # 战争/军事主题
    "war_scene": "masterpiece, best quality, ultra detailed, 8k, photorealistic, battlefield scene, destroyed tanks, smoke billowing, soldiers in combat, dramatic lighting, wide angle shot, war photojournalism, film grain texture",
    
    "military_base": "masterpiece, best quality, ultra detailed, 8k, photorealistic, military installation, armored vehicles, soldiers, command center, natural lighting, wide angle shot, documentary style",
    
    "missile_launch": "masterpiece, best quality, ultra detailed, 8k, photorealistic, missile launch, rocket ascending, exhaust plume, dramatic sky, wide angle shot, military documentary",
    
    # 新闻/政治主题
    "news_broadcast": "masterpiece, best quality, ultra detailed, 8k, photorealistic, news studio, anchor at desk, breaking news graphics, world map display, professional lighting, medium shot",
    
    "government_meeting": "masterpiece, best quality, ultra detailed, 8k, photorealistic, government officials in meeting, conference table, formal setting, natural lighting, medium shot, documentary style",
    
    "diplomatic_scene": "masterpiece, best quality, ultra detailed, 8k, photorealistic, diplomatic meeting, flags, formal atmosphere, professional setting, natural lighting, medium shot",
    
    # 科技/太空主题
    "space_scene": "masterpiece, best quality, ultra detailed, 8k, photorealistic, deep space, stars, cosmic background, nebula, dramatic lighting, wide angle shot, space documentary",
    
    "technology_lab": "masterpiece, best quality, ultra detailed, 8k, photorealistic, modern laboratory, scientists, high-tech equipment, screens and monitors, natural lighting, medium shot",
    
    # 经济/商业主题
    "economic_scene": "masterpiece, best quality, ultra detailed, 8k, photorealistic, financial district, business professionals, stock charts, modern office, natural lighting, medium shot",
    
    # 通用场景
    "general_scene": "masterpiece, best quality, ultra detailed, 8k, photorealistic, realistic scene, documentary style, natural lighting, medium shot, professional photography",
}


# ========== 针对大模型的轻量级提示词优化指令 ==========
# 这个指令用于让大模型快速生成适配 ARV 的提示词
ARV_OPTIMIZATION_PROMPT = """You are a prompt engineer for absoluteRealisticVision v20 SD model.

STRICT OUTPUT RULES:
1. Output ONLY English keywords, comma-separated
2. Start with: masterpiece, best quality, ultra detailed, 8k, photorealistic
3. End with: cinematic lighting, documentary style, film grain texture
4. Include visual elements: subject, environment, lighting, composition
5. Total length: 30-50 words
6. NO explanations, NO quotes, NO newlines

Convert this Chinese text to SD prompt:"""
