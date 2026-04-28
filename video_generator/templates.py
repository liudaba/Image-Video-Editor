# -*- coding: utf-8 -*-
"""精简提示词系统 - 大模型自主创作（唯一版本）"""


class PromptTemplates:
    """精简提示词系统 - 删除过度约束，保留必要指导，让大模型自主创作

    核心原则：
    1. 分镜数量由语音片段数量决定（每个segment一个分镜）
    2. 大模型负责：通篇分析、纠正错别字、捋清语义、确定主题基调、生成优化的提示词
    3. 不限制大模型的创作方式，让它根据内容自主发挥
    4. 输出必须是纯粹的提示词，不含任何解释性文字
    5. 统一视觉风格：电影纪实风格，4K画质，真实感
    """

    THEME_ANALYSIS = {
        "system": """你是视频内容分析师。分析语音文本并输出结构化结果。

【核心任务】分析语音文本，提取内容类型、主题和视觉风格
- 如果文本中存在明显的语音识别错误（如同音字错字、形近字错字），请进行纠正
- 如果文本中没有识别错误，则无需列出纠错

【内容类型】新闻播报/军事分析/科普教育/历史纪录/社会民生/财经商业/文化艺术/自然地理/体育竞技

【输出要求】严格按此格式，不要输出其他内容：

【内容类型】：(选一个)
【核心主题】：(一句话，简洁明了)
【情感基调】：(严肃/紧张/轻松/温馨/激昂)
【视觉风格】：(推荐风格)
【核心元素】：(5-8个关键词)
【纠错说明】：(仅当存在实际错别字纠正时列出，格式：错字1→正确1,错字2→正确2，如"害器→氦气,汽年→汽车"，如无纠正则写"无")

重要：
1. 仔细阅读文本，判断是否存在需要纠正的错别字
2. 如果文本准确无误，【纠错说明】必须写"无"
3. 不要凭空捏造纠错内容
4. 直接输出格式内容，不要有开场白或解释""",

        "user_template": """语音文本：
{text}

请先仔细检查整个文本，找出所有可能的语音识别错误，然后按格式输出："""
    }

    DUBBING_SEMANTIC_MAPPING = {
        "en": """
【重要】每个分镜的配音内容不同，生成的提示词必须体现该配音的独特语义：
- 配音提到"台海和平" → 提示词必须包含Taiwan Strait, peace相关元素
- 配音提到"宪法" → 提示词必须包含constitution, legal document相关元素
- 配音提到"两岸关系" → 提示词必须包含cross-strait, relations相关元素""",
        "zh": """
【重要】每个分镜的配音内容不同，生成的提示词必须体现该配音的独特语义：
- 配音提到"台海和平" → 提示词必须包含台海、和平相关元素
- 配音提到"宪法" → 提示词必须包含宪法、法律文件相关元素
- 配音提到"两岸关系" → 提示词必须包含两岸、关系相关元素"""
    }

    SHOT_PROMPT_SD = {
        "system": """你是AI图像提示词工程师，为Stable Diffusion生成英文提示词。

【严格格式要求】
- 必须以质量前缀开头：masterpiece, best quality, ultra detailed, 8k, photorealistic
- 只输出英文关键词，逗号分隔，禁止使用完整句子
- 描述可拍摄的画面内容，不要描述抽象概念或叙事
- 不要输出解释、标题、标注、括号说明
- 结尾必须添加：cinematic lighting, documentary style, film grain texture
- 【核心】提示词必须准确反映当前配音内容的具体场景，禁止千篇一律

{semantic_mapping}

{style_instruction}
{theme_instruction}

【上下文理解规则 - 极其重要】
- 仔细阅读前文上下文和后文上下文，理解当前配音在整体故事中的位置
- 当前配音可能语义不完整，结合上下文推断完整含义
- 避免生成与上下文矛盾的场景，确保视觉连贯性
- 如果当前配音是过渡词或连接词，从上下文推断具体场景
- 考虑故事的叙事流，确保视觉风格在整个视频中保持一致

【位置感知规则】
- 开头分镜：建立场景，介绍主要元素
- 中段分镜：发展故事，展示具体内容
- 结尾分镜：总结主题，强化情感
- 避免前后分镜使用完全相同的场景设置

【示例】
配音："中东战事升级"
核心主题：战争反思
视觉基调：冷色调，沉重深刻
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, Middle Eastern war zone, destroyed buildings, smoke rising, military tanks, desert road, fighter jets overhead, cold blue tones, tense atmosphere, war documentary, news photography, cinematic lighting, documentary style, film grain texture

配音："科学家发现新黑洞"
核心主题：宇宙探索
视觉基调：神秘，科技感
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, space telescope control room, scientists, data screens, monitors, cosmic imagery, deep space background, mysterious atmosphere, high-tech setting, professional lighting, cinematic lighting, documentary style, film grain texture

配音："幸福的一家人"
核心主题：家庭温情
视觉基调：温暖，明亮
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, Asian family, warm home interior, living room, soft golden light, candid moment, happy expressions, warm atmosphere, lifestyle photography, cinematic lighting, documentary style, film grain texture

【必加标签】masterpiece, best quality, ultra detailed, 8k, photorealistic, cinematic lighting, documentary style, film grain texture""",

        "user_template": """配音：{dubbing}

输出英文提示词："""
    }

    @classmethod
    def get_template(cls, template_type, **kwargs):
        """获取提示词模板

        Args:
            template_type: 模板类型
            **kwargs: 模板参数，包括：
                - visual_style: 用户预设的视觉风格
                - dubbing: 配音文本
                - core_theme: 核心主题
                - visual_tone: 视觉基调
                - context_hint: 上下文提示
        """
        templates = {
            "theme_analysis": cls.THEME_ANALYSIS,
            "shot_prompt_sd": cls.SHOT_PROMPT_SD,
            "theme_extraction": cls.THEME_ANALYSIS,
        }

        if template_type not in templates:
            return {
                "system": "",
                "user": kwargs.get("text", kwargs.get("description", ""))
            }

        template = templates[template_type]
        is_shot_prompt = template_type == "shot_prompt_sd"

        if is_shot_prompt:
            visual_style = kwargs.get("visual_style", "")
            is_sd = template_type == "shot_prompt_sd"

            if visual_style and visual_style.strip():
                style_instruction = f"""【重要：必须使用用户预设的风格】
用户预设的视觉风格：{visual_style}
你必须严格按照此风格生成提示词，禁止自行更改或添加其他风格。"""
            else:
                style_instruction = """【风格选择】
根据内容自主选择合适的视觉风格（如电影感、新闻纪实、艺术摄影、商业摄影等）。"""

            core_theme = kwargs.get("core_theme", "")
            visual_tone = kwargs.get("visual_tone", "")

            if (core_theme and core_theme != "未指定") or (visual_tone and visual_tone.strip()):
                theme_parts = []
                if core_theme and core_theme != "未指定":
                    theme_parts.append(f"核心主题：{core_theme}")
                if visual_tone and visual_tone.strip():
                    theme_parts.append(f"视觉基调：{visual_tone}")

                theme_text = "，".join(theme_parts)
                theme_instruction = f"""【重要：必须融入以下元素】
{theme_text}
你生成的提示词必须体现以上主题和基调，将其转化为具体的视觉元素。"""
            else:
                theme_instruction = ""

            semantic_mapping = cls.DUBBING_SEMANTIC_MAPPING["en"] if is_sd else cls.DUBBING_SEMANTIC_MAPPING["zh"]

            if theme_instruction:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction=theme_instruction,
                    semantic_mapping=semantic_mapping
                )
            else:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction="",
                    semantic_mapping=semantic_mapping
                )
                system_content = system_content.replace("\n\n\n", "\n\n")

            dubbing = kwargs.get("dubbing", "")
            context_hint = kwargs.get("context_hint", "")

            if context_hint:
                user_content = f"""{context_hint}
当前配音：{dubbing}

根据上下文和当前配音生成英文提示词："""
            else:
                user_content = f"""配音：{dubbing}

输出英文提示词："""
        else:
            system_content = template["system"]
            user_content = template["user_template"].format(**kwargs)

        return {
            "system": system_content,
            "user": user_content
        }
