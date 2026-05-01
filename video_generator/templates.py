# -*- coding: utf-8 -*-
"""精简提示词系统 - 大模型自主创作（唯一版本）"""


class PromptTemplates:
    """精简提示词系统 - 语义驱动的视觉翻译

    核心原则：
    1. 每个分镜的配音内容不同，提示词必须体现该配音的独特语义
    2. 大模型必须先理解中文配音的含义，再翻译为英文视觉元素
    3. 提示词描述的是"可拍摄的画面"，不是抽象概念
    4. 输出必须是纯粹的英文关键词，不含任何解释性文字
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

    SHOT_PROMPT_SD = {
        "system": """You are a visual scene designer. Translate Chinese dubbing into a specific, photographable scene description.

【YOUR ONLY JOB】
Read the Chinese dubbing, understand its meaning, then describe ONE specific scene that a camera could capture. Output ONLY English keywords separated by commas. No sentences, no Chinese, no explanations.

【THREE RULES】
1. MEANING FIRST: Translate the Chinese meaning into visual elements, not literal word-by-word.
2. ONE SCENE PER PROMPT: Every dubbing is a different moment — your scene must be unique in location, angle, and subjects.
3. CONCRETE ONLY: Describe what a camera sees — people, objects, places, lighting. No abstract concepts, no emotions as words.

{style_instruction}
{theme_instruction}

Content type: {content_type}
Visual tone: {visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Describe one specific scene:"""
    }

    @classmethod
    def get_template(cls, template_type, **kwargs):
        """获取提示词模板

        Args:
            template_type: 模板类型
            **kwargs: 模板参数
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

            if visual_style and visual_style.strip():
                style_instruction = f"""【IMPORTANT: Must use user-preset style】
User-preset visual style: {visual_style}
You MUST strictly follow this style, do NOT change or add other styles."""
            else:
                style_instruction = """【Style Selection】
Choose an appropriate visual style based on content (cinematic, news documentary, art photography, commercial photography, etc.)."""

            core_theme = kwargs.get("core_theme", "")
            visual_tone = kwargs.get("visual_tone", "")

            if (core_theme and core_theme != "未指定") or (visual_tone and visual_tone.strip()):
                theme_parts = []
                if core_theme and core_theme != "未指定":
                    theme_parts.append(f"Core theme: {core_theme}")
                if visual_tone and visual_tone.strip():
                    theme_parts.append(f"Visual tone: {visual_tone}")

                theme_text = ", ".join(theme_parts)
                theme_instruction = f"""【IMPORTANT: Must incorporate these elements】
{theme_text}
Your prompt MUST reflect this theme and tone, translating them into concrete visual elements."""
            else:
                theme_instruction = ""

            if theme_instruction:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction="\n" + theme_instruction
                )
            else:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction=""
                )
                system_content = system_content.replace("\n\n\n", "\n\n")

            dubbing = kwargs.get("dubbing", "")
            context_hint = kwargs.get("context_hint", "")

            if context_hint:
                context_section = f"""{context_hint}

"""
            else:
                context_section = ""

            user_content = template["user_template"].format(
                context_section=context_section,
                dubbing=dubbing
            )
        else:
            system_content = template["system"]
            user_content = template["user_template"].format(**kwargs)

        return {
            "system": system_content,
            "user": user_content
        }
