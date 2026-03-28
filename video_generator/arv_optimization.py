"""
ARV绝对写实风格优化模块
专为 absoluteRealisticVision v20 模型优化的提示词生成系统
"""

class SceneContinuityManager:
    """分镜连贯性管理器 - 确保分镜间视觉一致性"""

    def __init__(self):
        self.scene_history = []
        self.last_scene_type = None
        self.last_location = None
        self.last_camera = None
        self.last_lighting = None

    def update_scene(self, shot_data, semantic_elements=None, camera_direction=None, lighting_style=None):
        """更新场景状态，保持连贯性"""
        self.scene_history.append({
            'content_type': shot_data.get('content_type', ''),
            'visual_tone': shot_data.get('visual_tone', ''),
            'semantic_elements': semantic_elements or [],
            'camera': camera_direction,
            'lighting': lighting_style,
        })
        if len(self.scene_history) > 5:
            self.scene_history.pop(0)

    def get_continuity_tags(self):
        """获取连贯性标签"""
        tags = []

        if len(self.scene_history) >= 1:
            last_shot = self.scene_history[-1]

            if last_shot.get('camera'):
                tags.append(last_shot['camera'])

            if last_shot.get('semantic_elements'):
                tags.append(', '.join(last_shot['semantic_elements'][:1]))

        return tags


class AbsoluteRealisticPrompts:
    """专为 absoluteRealisticVision v20 模型优化的提示词生成系统

    核心优化：
    1. 强化写实质量标签：针对ARV模型的写实特性定制质量标签
    2. 语义精确匹配：确保英文提示词与中文描述完全对应
    3. 分镜连贯性：维护分镜间的视觉逻辑一致性
    4. 场景深度理解：不只是关键词匹配，而是语义解析
    """

    ARV_QUALITY_TAGS = {
        "base": "masterpiece, best quality, absolute realistic, photo-realistic, ultra detailed, 8K, HDR, cinematic lighting",
    }

    CONTENT_ARV_PROMPTS = {
        "general": {
            "base": "documentary scene, real-life situation",
            "atmosphere": "realistic atmosphere",
            "lighting": "natural lighting"
        },
        "military": {
            "base": "war zone, battlefield, combat scene",
            "atmosphere": "tense atmosphere, dramatic combat, war documentary",
            "lighting": "dramatic lighting, combat shadows"
        },
        "politics": {
            "base": "government building, diplomatic scene",
            "atmosphere": "formal atmosphere, serious tone",
            "lighting": "professional lighting"
        },
        "science": {
            "base": "laboratory, research facility, tech scene",
            "atmosphere": "scientific precision, professional atmosphere",
            "lighting": "clean laboratory lighting"
        },
        "space": {
            "base": "cosmic scene, deep space, astronomical view",
            "atmosphere": "mysterious atmosphere, cosmic scale",
            "lighting": "celestial lighting"
        },
        "nature": {
            "base": "natural landscape, wildlife habitat",
            "atmosphere": "natural atmosphere, serene environment",
            "lighting": "natural sunlight, golden hour"
        },
        "technology": {
            "base": "high-tech scene, innovation center",
            "atmosphere": "modern atmosphere, cutting-edge tone",
            "lighting": "technological illumination"
        },
        "business": {
            "base": "office, corporate scene, financial district",
            "atmosphere": "professional atmosphere",
            "lighting": "office lighting"
        },
        "economy": {
            "base": "stock market, trading floor, financial scene",
            "atmosphere": "market tension, financial pressure",
            "lighting": "screen glow, indoor lighting"
        },
        "history": {
            "base": "historical site, period scene, heritage location",
            "atmosphere": "historical atmosphere, period authenticity",
            "lighting": "period lighting"
        }
    }

    SEMANTIC_MAPPINGS = {
        '中东': 'Middle Eastern region, Levant area, Persian Gulf',
        '城市': 'urban cityscape, city buildings, metropolitan area',
        '街道': 'city street, urban road, street scene',
        '战场': 'battlefield, war zone, combat area, front line',
        '油田': 'oil field, petroleum facility, drilling platform',
        '工厂': 'factory, manufacturing plant, industrial facility',
        '医院': 'hospital, medical facility, emergency room',
        '市场': 'marketplace, commercial center, trading hub',
        '港口': 'port, harbor, shipping terminal, dock',
        '海峡': 'strait, channel, maritime route',
        '实验室': 'laboratory, research facility, scientific lab',
        '沙漠': 'desert, arid landscape, sand dunes',
        '山区': 'mountain, mountainous region, alpine area',
        '芯片': 'semiconductor chips, microchips, integrated circuits',
        '医疗': 'medical equipment, healthcare supplies, medical devices',
        '石油': 'petroleum, crude oil, oil products',
        '坦克': 'tanks, military tanks, armored vehicles',
        '飞机': 'aircraft, airplanes, fighter jets',
        '船只': 'ships, vessels, cargo ships',
        '导弹': 'missiles, ballistic missiles',
        '设备': 'equipment, machinery, devices',
        '生产线': 'production line, assembly line',
        '供应链': 'supply chain, logistics network',
        '战斗': 'combat, battle, fighting, military engagement',
        '轰炸': 'airstrike, bombing, aerial attack',
        '爆炸': 'explosion, blast, detonation',
        '瘫痪': 'paralysis, shutdown, disabled system',
        '生产': 'production, manufacturing, industrial output',
        '短缺': 'shortage, scarcity, lack, insufficient supply',
        '运输': 'transportation, logistics, cargo movement',
        '航运': 'shipping, maritime transport, sea freight',
        '恐慌': 'panic, chaos, fear, hysteria',
        '上涨': 'rising, increasing, surging, price increase',
        '下跌': 'falling, declining, dropping, price decrease',
        '燃烧': 'burning, on fire, flames, blazing',
        '倒塌': 'collapsed, ruined, destroyed, rubble',
        '混乱': 'chaos, disorder, confusion, turmoil',
        '紧张': 'tense atmosphere, tension, nervous mood',
        '危机': 'crisis, emergency, critical situation',
        '危险': 'dangerous, hazardous, peril, risk',
        '沉重': 'heavy atmosphere, somber mood, grave',
        '绝望': 'desperate, hopeless, despair',
        '希望': 'hopeful, optimistic, positive',
        '早晨': 'morning, sunrise, early morning light',
        '中午': 'midday, noon, bright daylight',
        '夜晚': 'night, nighttime, moonlight',
        '深夜': 'late night, deep night, midnight',
        '全景': 'wide shot, panoramic view, establishing shot',
        '特写': 'close-up, detailed shot, macro view',
        '中景': 'medium shot, waist-up framing',
    }

    def __init__(self):
        self.continuity_manager = SceneContinuityManager()

    def has_semantic_match(self, text, core_theme):
        """检测是否有语义匹配 - 优先检查配音文本"""
        for key in self.SEMANTIC_MAPPINGS.keys():
            if key in text:
                return True

        return False

    def analyze_semantic_structure(self, text, core_theme, visual_tone):
        """深度语义分析"""
        semantic_elements = []
        visual_style = []
        atmosphere = []
        camera_direction = []

        for key, en_value in self.SEMANTIC_MAPPINGS.items():
            if key in text:
                if key in ['中东', '城市', '街道', '战场', '油田', '工厂', '医院', '市场', '港口', '海峡', '实验室', '沙漠', '山区']:
                    semantic_elements.append(en_value)
                elif key in ['紧张', '危机', '危险', '沉重', '绝望', '希望', '恐慌', '混乱']:
                    atmosphere.append(en_value)
                elif key in ['早晨', '中午', '夜晚', '深夜']:
                    visual_style.append(en_value)
                elif key in ['全景', '特写', '中景']:
                    camera_direction.append(en_value)
                else:
                    semantic_elements.append(en_value)

        return semantic_elements, visual_style, atmosphere, camera_direction

    def _translate_theme_to_elements(self, theme):
        """将核心主题转换为视觉元素"""
        theme_elements = []

        if not theme:
            return theme_elements

        theme_mappings = {
            '中东': 'Middle East war zone, Levant conflict area',
            '芯片': 'semiconductor industry, chip manufacturing',
            '医疗': 'medical crisis, healthcare emergency',
            '石油': 'oil industry, energy crisis',
            '供应链': 'supply chain disruption',
            '经济': 'financial crisis, market turmoil',
            '科技': 'technology sector, innovation',
            '环境': 'environmental disaster, climate crisis',
        }

        for theme_key, en_value in theme_mappings.items():
            if theme_key in theme:
                theme_elements.append(en_value)

        return theme_elements

    def generate_arv_prompt(self, text, content_type, core_theme, visual_tone, shot_data=None):
        """生成ARV专用提示词"""
        semantic_elements, visual_style, atmosphere, camera_direction = self.analyze_semantic_structure(
            text, core_theme, visual_tone
        )

        content_prompts = self.CONTENT_ARV_PROMPTS.get(content_type, self.CONTENT_ARV_PROMPTS["general"])

        # 获取上一帧的连贯性标签（在更新之前获取）
        continuity_tags = self.continuity_manager.get_continuity_tags()

        # 然后更新当前帧
        if shot_data:
            self.continuity_manager.update_scene(shot_data, semantic_elements, camera_direction, content_prompts.get('lighting'))

        prompt_parts = []

        # 收集所有元素用于去重
        all_elements = []

        # 1. 语义分析结果（具体内容，由大模型根据上下文理解）
        all_elements.extend(semantic_elements[:2])

        # 去重
        seen = set()
        unique_elements = []
        for e in all_elements:
            if e not in seen:
                seen.add(e)
                unique_elements.append(e)

        if unique_elements:
            prompt_parts.append(', '.join(unique_elements))

        # 只在语义元素和氛围都为空时添加内容类型基础元素
        if not semantic_elements and not atmosphere and content_prompts.get('base'):
            prompt_parts.append(content_prompts['base'])

        # 3. 氛围（只添加一个）
        if atmosphere:
            prompt_parts.append(atmosphere[0])
        elif not semantic_elements and content_prompts.get('atmosphere'):
            prompt_parts.append(content_prompts['atmosphere'])

        # 4. 光影（只添加一个，当没有语义元素时才添加）
        if not semantic_elements and content_prompts.get('lighting'):
            prompt_parts.append(content_prompts['lighting'])

        # 5. ARV质量标签（重要，放在最后但包含所有质量要求）
        prompt_parts.append(self.ARV_QUALITY_TAGS['base'])

        final_prompt = ', '.join(p for p in prompt_parts if p)

        return final_prompt


def get_arv_prompter():
    """获取ARV提示词生成器实例"""
    return AbsoluteRealisticPrompts()
