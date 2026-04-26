# -*- coding: utf-8 -*-
"""
ARV绝对写实风格优化模块
仅保留质量标签和连贯性管理，让大模型自主生成
"""


class SceneContinuityManager:
    """分镜连贯性管理器"""

    def __init__(self):
        self.scene_history = []
        self.last_scene_type = None
        self.last_location = None
        self.last_camera = None
        self.last_lighting = None

    def update_scene(self, shot_data, semantic_elements=None, camera_direction=None, lighting_style=None):
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
        tags = []
        if len(self.scene_history) >= 1:
            last_shot = self.scene_history[-1]
            if last_shot.get('camera'):
                tags.append(last_shot['camera'])
            if last_shot.get('semantic_elements'):
                tags.append(', '.join(last_shot['semantic_elements'][:1]))
        return tags


class AbsoluteRealisticPrompts:
    """absoluteRealisticVision v20 质量标签工具"""

    ARV_QUALITY_TAGS = {
        "base": "(masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), ultra detailed, 8K, HDR, DSLR, high resolution",
    }

    CONTENT_ARV_PROMPTS = {
        "general": {
            "base": "documentary scene, real-life situation, authentic moment",
            "atmosphere": "realistic atmosphere, natural mood",
            "lighting": "natural lighting, balanced exposure"
        },
        "military": {
            "base": "(war zone:1.2), battlefield, combat scene, military operation",
            "atmosphere": "(tense atmosphere:1.2), dramatic combat, war documentary",
            "lighting": "dramatic lighting, combat shadows, harsh contrast"
        },
        "politics": {
            "base": "(government building:1.2), diplomatic scene, official setting",
            "atmosphere": "formal atmosphere, serious tone, authoritative presence",
            "lighting": "professional lighting, studio quality"
        },
        "science": {
            "base": "(laboratory:1.2), research facility, tech scene, scientific discovery",
            "atmosphere": "scientific precision, professional atmosphere, focused concentration",
            "lighting": "clean laboratory lighting, fluorescent illumination"
        },
        "space": {
            "base": "(cosmic scene:1.3), deep space, astronomical view, stellar panorama",
            "atmosphere": "mysterious atmosphere, cosmic scale, awe-inspiring vastness",
            "lighting": "celestial lighting, nebula glow, star illumination"
        },
        "nature": {
            "base": "(natural landscape:1.2), wildlife habitat, pristine environment",
            "atmosphere": "natural atmosphere, serene environment, peaceful mood",
            "lighting": "natural sunlight, golden hour, soft ambient"
        },
        "technology": {
            "base": "(high-tech scene:1.2), innovation center, advanced facility",
            "atmosphere": "modern atmosphere, cutting-edge tone, innovative spirit",
            "lighting": "technological illumination, LED lighting, cool tones"
        },
        "business": {
            "base": "(corporate office:1.2), business scene, professional environment",
            "atmosphere": "professional atmosphere, corporate culture",
            "lighting": "office lighting, professional illumination"
        },
        "economy": {
            "base": "(stock market:1.2), trading floor, financial scene, market activity",
            "atmosphere": "(market tension:1.1), financial pressure, competitive energy",
            "lighting": "screen glow, indoor lighting, monitor illumination"
        },
        "history": {
            "base": "(historical site:1.2), period scene, heritage location, archival footage",
            "atmosphere": "historical atmosphere, period authenticity, nostalgic mood",
            "lighting": "period lighting, vintage tone, sepia undertone"
        }
    }

    def __init__(self):
        self.continuity_manager = SceneContinuityManager()

    def has_semantic_match(self, text, core_theme):
        return False

    def analyze_semantic_structure(self, text, core_theme, visual_tone):
        return [], [], [], []

    def generate_arv_prompt(self, text, content_type, core_theme, visual_tone, shot_data=None):
        content_prompts = self.CONTENT_ARV_PROMPTS.get(content_type, self.CONTENT_ARV_PROMPTS["general"])
        continuity_tags = self.continuity_manager.get_continuity_tags()

        if shot_data:
            self.continuity_manager.update_scene(shot_data, [], [], content_prompts.get('lighting'))

        prompt_parts = [self.ARV_QUALITY_TAGS['base']]

        if content_prompts.get('base'):
            prompt_parts.append(content_prompts['base'])
        if content_prompts.get('atmosphere'):
            prompt_parts.append(content_prompts['atmosphere'])
        if content_prompts.get('lighting'):
            prompt_parts.append(content_prompts['lighting'])
        if continuity_tags:
            prompt_parts.append(', '.join(continuity_tags[:1]))

        return ', '.join(p for p in prompt_parts if p)


def get_arv_prompter():
    return AbsoluteRealisticPrompts()
