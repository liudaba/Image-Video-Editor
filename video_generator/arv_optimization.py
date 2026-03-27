"""
ARV绝对写实风格优化模块
专为 absoluteRealisticVision v20 模型优化的提示词生成系统
"""

class SceneContinuityManager:
    """分镜连贯性管理器 - 确保分镜间视觉一致性"""

    def __init__(self):
        self.scene_history = []
        self.current_scene = None
        self.visual_tone = None
        self.color_palette = None
        self.camera_distance = None
        self.lighting_style = None

    def update_scene(self, shot_data):
        """更新场景状态，保持连贯性"""
        self.scene_history.append(shot_data)
        if len(self.scene_history) > 5:
            self.scene_history.pop(0)

        self.current_scene = shot_data.get('content_type', '')
        self.visual_tone = shot_data.get('visual_tone', '')

    def get_continuity_tags(self, shot_data):
        """获取连贯性标签"""
        tags = []

        if len(self.scene_history) > 1:
            last_shot = self.scene_history[-2]

            if last_shot.get('camera_distance'):
                tags.append(last_shot['camera_distance'])

            if last_shot.get('lighting_style'):
                tags.append(last_shot['lighting_style'])

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
        "base": "masterpiece, best quality, absolute realistic, photo-realistic, ultra detailed, sharp focus, 8K resolution, professional photography, documentary style",
        "lighting": "cinematic lighting, natural lighting, volumetric light, realistic shadows, high contrast, HDR photography, studio lighting",
        "photography": "35mm lens, shallow depth of field, bokeh, professional camera, telephoto lens, wide angle, macro photography, time-lapse",
        "texture": "skin texture, fabric texture, metal texture, surface details, material rendering, realistic materials, fine details",
        "color": "accurate colors, natural color grading, cinematic color grading, color correction, realistic tones"
    }

    CONTENT_ARV_PROMPTS = {
        "military": {
            "base": "military documentary, war zone, combat scene, tactical operation, battlefield realism",
            "elements": "military equipment, soldiers, tanks, military vehicles, combat gear, tactical uniforms",
            "atmosphere": "tense atmosphere, dramatic combat, war photography style, battlefield documentary",
            "lighting": "dramatic lighting, battlefield shadows, combat illumination, war zone lighting"
        },
        "politics": {
            "base": "political documentary, government building, diplomatic scene, political setting",
            "elements": "official venues, government architecture, diplomatic environment, political figures",
            "atmosphere": "formal atmosphere, serious tone, political documentary style, official photography",
            "lighting": "professional lighting, government venue lighting, documentary illumination"
        },
        "science": {
            "base": "scientific documentary, laboratory scene, research environment, technology visualization",
            "elements": "scientific equipment, lab instruments, research facilities, technological devices",
            "atmosphere": "professional atmosphere, scientific precision, research documentary style",
            "lighting": "laboratory lighting, clean lighting, technical illumination, scientific photography"
        },
        "space": {
            "base": "space documentary, cosmic scene, astronomical visualization, deep space photography",
            "elements": "planets, stars, nebulae, galaxies, spacecraft, satellites, telescopes",
            "atmosphere": "mysterious atmosphere, cosmic scale, space documentary style, astronomical photography",
            "lighting": "celestial lighting, cosmic illumination, space lighting, astronomical rendering"
        },
        "nature": {
            "base": "nature documentary, landscape photography, wildlife documentary, environmental scene",
            "elements": "natural landscapes, wildlife, forests, mountains, rivers, oceans, wildlife habitats",
            "atmosphere": "natural atmosphere, serene environment, nature documentary style, wildlife photography",
            "lighting": "natural sunlight, golden hour lighting, environmental lighting, nature photography"
        },
        "technology": {
            "base": "technology documentary, high-tech scene, innovation visualization, future technology",
            "elements": "digital devices, futuristic equipment, innovation centers, tech facilities",
            "atmosphere": "modern atmosphere, cutting-edge tone, technology documentary style, tech photography",
            "lighting": "modern lighting, technological illumination, innovation lighting, tech documentary"
        },
        "business": {
            "base": "business documentary, corporate scene, financial district, business environment",
            "elements": "office buildings, corporate interiors, financial venues, business facilities",
            "atmosphere": "professional atmosphere, business tone, corporate documentary style, business photography",
            "lighting": "professional lighting, office lighting, corporate illumination, business photography"
        },
        "history": {
            "base": "historical documentary, period scene, historical setting, cultural heritage",
            "elements": "historical architecture, period costumes, ancient sites, cultural artifacts",
            "atmosphere": "historical atmosphere, period authenticity, historical documentary style, heritage photography",
            "lighting": "period-accurate lighting, historical illumination, documentary lighting, heritage photography"
        }
    }

    def __init__(self):
        self.continuity_manager = SceneContinuityManager()

    def analyze_semantic_structure(self, text, core_theme, visual_tone):
        """深度语义分析"""
        semantic_elements = []
        visual_style = []
        atmosphere = []
        camera_direction = []

        text_lower = text.lower()

        time_elements = {
            '早晨': 'morning light, sunrise, early morning atmosphere',
            '中午': 'midday sun, bright daylight, noon lighting',
            '下午': 'afternoon light, daytime setting, post-meridiem',
            '傍晚': 'golden hour, sunset lighting, evening atmosphere',
            '夜晚': 'nighttime, dark atmosphere, moonlight, artificial lighting',
            '深夜': 'late night, darkness, urban night lighting'
        }

        for time_key, time_desc in time_elements.items():
            if time_key in text:
                visual_style.append(time_desc)
                atmosphere.append(f"{time_key} atmosphere")
                break

        location_semantics = {
            '城市': 'urban cityscape, city environment, metropolitan area, urban setting',
            '街道': 'street scene, urban street, city road, pedestrian area',
            '建筑': 'architecture, building exterior, architectural photography, urban structures',
            '办公室': 'office interior, corporate workspace, business environment, office setting',
            '山脉': 'mountain range, mountain landscape, mountain terrain, alpine environment',
            '河流': 'river scene, waterway, flowing water, river landscape',
            '海洋': 'ocean view, sea landscape, marine environment, coastal scene',
            '森林': 'forest environment, woodland, tree-covered area, natural forest',
            '室内': 'interior scene, indoor setting, indoor environment, room interior',
            '会议室': 'conference room, meeting space, boardroom, business meeting environment',
            '实验室': 'laboratory interior, research facility, scientific workspace, lab setting',
            '战场': 'battlefield, war zone, combat area, military engagement scene',
            '灾区': 'disaster area, affected region, disaster zone, crisis location',
            '边境': 'border area, border zone, frontier region, boundary line'
        }

        for loc_key, loc_desc in location_semantics.items():
            if loc_key in text:
                semantic_elements.append(loc_desc)
                break

        emotion_semantics = {
            '紧张': 'tense atmosphere, dramatic tension, suspenseful mood, intensity',
            '危机': 'crisis atmosphere, emergency situation, urgent tone, critical mood',
            '危险': 'dangerous environment, hazardous situation, risk atmosphere, peril',
            '沉重': 'heavy atmosphere, serious tone, grave mood, solemn feeling',
            '严肃': 'serious atmosphere, formal tone, grave mood, solemn setting',
            '和平': 'peaceful atmosphere, tranquil mood, calm setting, harmonious environment',
            '宁静': 'serene atmosphere, calm mood, peaceful setting, tranquil environment',
            '希望': 'hopeful atmosphere, optimistic mood, positive tone, inspiring feeling',
            '温暖': 'warm atmosphere, comfortable mood, inviting feeling, cozy setting'
        }

        for emo_key, emo_desc in emotion_semantics.items():
            if emo_key in text or emo_key in visual_tone:
                atmosphere.append(emo_desc)

        action_semantics = {
            '战斗': 'combat action, battle scene, fighting, military engagement',
            '谈判': 'negotiation scene, diplomatic talk, meeting discussion, conversation',
            '工作': 'working scene, professional activity, business operation, task execution',
            '研究': 'research activity, scientific investigation, analytical work, study process'
        }

        for action_key, action_desc in action_semantics.items():
            if action_key in text:
                semantic_elements.append(action_desc)

        if '全景' in text or '整体' in text:
            camera_direction.append('wide shot, panoramic view, establishing shot')
        elif '特写' in text or '细节' in text:
            camera_direction.append('close-up, detailed shot, macro view')
        elif '中景' in text or '人物' in text:
            camera_direction.append('medium shot, waist-up framing')

        if core_theme:
            theme_keywords = self._translate_theme_to_elements(core_theme)
            if theme_keywords:
                semantic_elements.extend(theme_keywords)

        return semantic_elements, visual_style, atmosphere, camera_direction

    def _translate_theme_to_elements(self, theme):
        """将核心主题转换为视觉元素"""
        theme_elements = []

        theme_mappings = {
            '战争反思': ['war aftermath', 'destroyed landscape', 'war memorial', 'post-war reconstruction'],
            '供应链危机': ['supply chain disruption', 'logistics problems', 'distribution issues', 'transportation breakdown'],
            '科技发展': ['technological advancement', 'innovation scene', 'future technology', 'digital transformation'],
            '环境问题': ['environmental degradation', 'pollution scene', 'climate change effects', 'ecological damage'],
            '国际合作': ['international cooperation', 'diplomatic meeting', 'collaboration scene', 'global partnership']
        }

        for theme_key, elements in theme_mappings.items():
            if theme_key in theme:
                theme_elements.extend(elements)
                break

        return theme_elements

    def generate_arv_prompt(self, text, content_type, core_theme, visual_tone, shot_data=None):
        """生成ARV专用提示词"""
        if shot_data:
            self.continuity_manager.update_scene(shot_data)

        semantic_elements, visual_style, atmosphere, camera_direction = self.analyze_semantic_structure(
            text, core_theme, visual_tone
        )

        content_prompts = self.CONTENT_ARV_PROMPTS.get(content_type, {})

        prompt_parts = []

        main_subject = []
        if semantic_elements:
            main_subject.extend(semantic_elements)
        if 'base' in content_prompts:
            main_subject.append(content_prompts['base'])
        prompt_parts.append(', '.join(main_subject))

        if 'elements' in content_prompts:
            prompt_parts.append(content_prompts['elements'])

        if atmosphere:
            prompt_parts.append(', '.join(atmosphere))
        if 'atmosphere' in content_prompts:
            prompt_parts.append(content_prompts['atmosphere'])

        lighting_tags = []
        if visual_style:
            lighting_tags.extend(visual_style)
        if 'lighting' in content_prompts:
            lighting_tags.append(content_prompts['lighting'])
        if lighting_tags:
            prompt_parts.append(', '.join(lighting_tags))

        if camera_direction:
            prompt_parts.append(', '.join(camera_direction))

        if shot_data:
            continuity_tags = self.continuity_manager.get_continuity_tags(shot_data)
            if continuity_tags:
                prompt_parts.append(', '.join(continuity_tags))

        arv_quality = []
        arv_quality.append(self.ARV_QUALITY_TAGS['base'])
        arv_quality.append(self.ARV_QUALITY_TAGS['lighting'])
        arv_quality.append(self.ARV_QUALITY_TAGS['photography'])
        arv_quality.append(self.ARV_QUALITY_TAGS['texture'])
        arv_quality.append(self.ARV_QUALITY_TAGS['color'])
        prompt_parts.append(', '.join(arv_quality))

        final_prompt = ', '.join(prompt_parts)

        return final_prompt


def get_arv_prompter():
    """获取ARV提示词生成器实例"""
    return AbsoluteRealisticPrompts()
