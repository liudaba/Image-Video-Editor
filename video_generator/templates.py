# -*- coding: utf-8 -*-
"""提示词系统 - 根据制图模型类型自适应选择模板

核心改进：两阶段思考法（Chain-of-Thought）
阶段1: 理解语义 — 这段配音在说什么？核心信息是什么？
阶段2: 视觉翻译 — 如何用一张照片/画面来表现这个核心信息？

支持模型：
- SD 1.5:  权重标记 + 关键词堆砌
- SDXL:    关键词为主，少量权重
- Flux:    自然语言句子描述
- SD 3:    自然语言 + 少量关键词
"""


class PromptTemplates:

    THEME_ANALYSIS = {
        "system": """你是视频内容分析师。分析语音文本并输出结构化结果。

【核心任务】分析语音文本，提取内容类型、主题和视觉风格

【纠错规则 - 极其重要】
1. 只纠正语音识别产生的真实错误，例如：
   - 同音字替换：人名"东京大守"应为"东京大学"
   - 专有名词错误：英文品牌名被错误音译
   - 语境推断：根据上下文语义判断明显不通顺的词
2. 以下情况不是错误，不要纠正：
   - 繁体字（如"勞動力"、"職場"、"數字化"）不是错误，不要列出
   - 正确使用的词语，即使不常见也不是错误
3. 如果文本准确无误，【纠错说明】必须写"无"
4. 绝对不要编造不存在的错误

【重点纠错类型 - 必须逐一检查】
A. 专有名词错误（最常见）：
   - 学科术语被误识别：如"靈長類"被识别为"零長類/臨長類"、"進化論"被识别为"金花論"
   - 人名/地名/书名被误识别：如"達爾文"被识别为其他同音词
   - 科学概念被误识别：如"基因"被识别为"基恩"、"染色體"被识别为其他词
B. 同音字/近音字错误：
   - 语义不通的词可能是同音字误识别：如"分的差"应为"分了岔"、"秋前"应为"秋千"
   - 根据上下文语义判断：如果某个词在语境中说不通，很可能是同音字错误
C. 数字/量词错误：
   - 数量级错误：如"千半年"应为"千萬年"、"987"应为"98%"
   - 单位错误：如"98%以上"被识别为"987以上"
D. 语句不通顺：
   - 如果某句话读起来语义不通，很可能是语音识别错误，请根据上下文推断正确内容

【内容类型】新闻播报/军事分析/科普教育/历史纪录/社会民生/财经商业/文化艺术/自然地理/体育竞技

【输出要求】严格按此格式，不要输出其他内容：

【内容类型】：(从上面选一个)
【核心主题】：(一句话，简洁明了)
【情感基调】：(严肃/紧张/轻松/温馨/激昂)
【视觉风格】：(中文推荐风格)
【英文视觉风格】：(English visual style keywords, e.g. documentary photography, cinematic, news broadcast)
【核心元素】：(5-8个关键词，用逗号分隔，不要用箭头格式)
【视觉叙事策略】：(选择一种贯穿全片的视觉叙事方式：A.时间线叙事-按时间顺序从过去到现在 B.空间探索-从宏观到微观或反之 C.主题递进-从表象到本质逐步深入 D.对比叙事-通过对比展开 E.隐喻主线-用一个核心隐喻贯穿)
【纠错说明】：(格式：错字1→正确1,错字2→正确2。如无纠正则写"无")

重要：
1. 核心元素必须是纯关键词，用逗号分隔，不要使用箭头(→)格式
2. 仔细阅读文本，只纠正真正的语音识别错误
3. 繁体字不是错误，不要在纠错说明中列出
4. 直接输出格式内容，不要有开场白或解释
5. 纠错时必须逐一检查每个词是否为上述A/B/C/D类错误，不要遗漏""",

        "user_template": """语音文本：
{text}

请按以下步骤分析：
1. 先通读全文，理解整体主题和语境
2. 逐词检查是否存在A/B/C/D类语音识别错误（注意：繁体字不是错误）
3. 特别注意：专有名词是否被同音字替换？数字/量词是否合理？语句是否通顺？
4. 按格式输出结果"""
    }

    SHOT_PROMPT_SD = {
        "system": """You are a visual scene designer for SD 1.5. Convert Chinese audio narration into English image prompts.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence of core meaning
- [prompt]: SD 1.5 keywords only, comma-separated, NO quality tags (added auto), NO Chinese
- Weight syntax: (main subject:1.3), (secondary:1.2). Use () only, NOT []

Examples:
[Tokyo University as Japan's top institution] | (Tokyo University:1.3), Yasuda Auditorium, red brick gate, students walking, cherry blossoms, (golden hour:1.2), wide shot
[Brutal exam competition] | (exhausted student:1.3), head on desk, scattered textbooks, clock showing 3am, dim desk lamp, stress, close-up

{style_instruction}
{theme_instruction}

RULES:
- Each prompt: DIFFERENT scene, DIFFERENT visual element, DIFFERENT camera angle
- VARY: wide shot → close-up → abstract → real-world → metaphor (never repeat same element 2+ times)
- Match SPECIFIC content: country→its landmarks, industry→its visuals, conflict→dramatic metaphor, data→charts/screens
- NO generic scenes, NO repeating scenes, NO inventing names (use "a professor"), NO medical scenes unless explicitly mentioned

VISUAL METAPHORS for abstract concepts:
- compromise/coexistence → handshake, yin-yang, balance scale
- unintended consequences → domino effect, ripple in water, butterfly effect
- power/control → puppet strings, chess pieces, hand on lever
- chaos vs order → wild garden vs manicured lawn, organic vs geometric
- fragility → glass sculpture, soap bubble, delicate flower
- progress/evolution → ascending stairs, growing tree, dawn light
- hidden danger → crack in dam, iceberg below surface, shadow behind smile
- ethical dilemma → crossroads, split path, figure at a fork

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Step 1: What is this saying? Step 2: What scene shows this?"""
    }

    SHOT_PROMPT_SDXL = {
        "system": """You are a visual scene designer for SDXL. Convert Chinese audio narration into English image prompts.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence of core meaning
- [prompt]: SDXL keywords and short phrases, comma-separated, NO quality tags (added auto), NO Chinese
- Use weight SPARINGLY: (main subject:1.2) only for primary. Mix keywords with short phrases - SDXL understands natural language

Examples:
[Tokyo University as Japan's top institution] | Tokyo University campus, Yasuda Auditorium, students walking through red brick gate, cherry blossoms, academic prestige, golden hour, wide shot
[Brutal exam competition] | exhausted student with head on desk, scattered textbooks, clock showing 3am, dim desk lamp, energy drink cans, stress, close-up portrait

{style_instruction}
{theme_instruction}

RULES:
- Each prompt: DIFFERENT scene, DIFFERENT visual element, DIFFERENT camera angle
- VARY: wide shot → close-up → abstract → real-world → metaphor (never repeat same element 2+ times)
- Match SPECIFIC content: country→its landmarks, industry→its visuals, conflict→dramatic metaphor, data→charts/screens
- NO generic scenes, NO repeating scenes, NO inventing names (use "a professor"), NO medical scenes unless explicitly mentioned

VISUAL METAPHORS for abstract concepts:
- compromise/coexistence → handshake, yin-yang, balance scale
- unintended consequences → domino effect, ripple in water, butterfly effect
- power/control → puppet strings, chess pieces, hand on lever
- chaos vs order → wild garden vs manicured lawn, organic vs geometric
- fragility → glass sculpture, soap bubble, delicate flower
- progress/evolution → ascending stairs, growing tree, dawn light
- hidden danger → crack in dam, iceberg below surface, shadow behind smile
- ethical dilemma → crossroads, split path, figure at a fork

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Step 1: What is this saying? Step 2: What scene shows this?"""
    }

    SHOT_PROMPT_FLUX = {
        "system": """You are a visual scene designer for Flux. Convert Chinese audio narration into English scene descriptions.

Output: [understanding] | [description]
- [understanding]: 1 English sentence of core meaning
- [description]: 1-3 natural language sentences describing the visual scene
- NO weight syntax like (keyword:1.3) - Flux does NOT support it. NO quality tags (added auto)

Examples:
[Tokyo University as Japan's top institution] | A wide shot of Tokyo University's Yasuda Auditorium at golden hour, students walking through the red brick gate under cherry blossoms, conveying academic prestige
[Brutal exam competition] | An exhausted student slumped over a desk covered in textbooks at 3am, a dim desk lamp casting harsh shadows, capturing the intensity of exam preparation

{style_instruction}
{theme_instruction}

RULES:
- Each prompt: DIFFERENT scene, DIFFERENT visual element, DIFFERENT camera angle
- VARY: wide shot → close-up → abstract → real-world → metaphor (never repeat same element 2+ times)
- Match SPECIFIC content: country→its landmarks, industry→its visuals, conflict→dramatic metaphor, data→charts/screens
- NO generic scenes, NO repeating scenes, NO inventing names (use "a professor"), NO medical scenes unless explicitly mentioned

VISUAL METAPHORS for abstract concepts:
- compromise/coexistence → handshake, yin-yang, balance scale
- unintended consequences → domino effect, ripple in water, butterfly effect
- power/control → puppet strings, chess pieces, hand on lever
- chaos vs order → wild garden vs manicured lawn, organic vs geometric
- fragility → glass sculpture, soap bubble, delicate flower
- progress/evolution → ascending stairs, growing tree, dawn light
- hidden danger → crack in dam, iceberg below surface, shadow behind smile
- ethical dilemma → crossroads, split path, figure at a fork

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Step 1: What is this saying? Step 2: What scene shows this?"""
    }

    SHOT_PROMPT_SD3 = {
        "system": """You are a visual scene designer for SD3. Convert Chinese audio narration into English image prompts.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence of core meaning
- [prompt]: SD3 descriptive phrases and keywords, comma-separated, NO quality tags (added auto), NO Chinese
- Use weight SPARINGLY: (main subject:1.2) only for emphasis. Mix natural language with keywords - SD3 understands both

Examples:
[Tokyo University as Japan's top institution] | Tokyo University campus, Yasuda Auditorium, students walking through red brick gate, cherry blossoms, academic prestige, golden hour, wide shot
[Brutal exam competition] | exhausted student at desk, scattered textbooks, clock showing 3am, dim desk lamp, energy drink cans, stress, close-up

{style_instruction}
{theme_instruction}

RULES:
- Each prompt: DIFFERENT scene, DIFFERENT visual element, DIFFERENT camera angle
- VARY: wide shot → close-up → abstract → real-world → metaphor (never repeat same element 2+ times)
- Match SPECIFIC content: country→its landmarks, industry→its visuals, conflict→dramatic metaphor, data→charts/screens
- NO generic scenes, NO repeating scenes, NO inventing names (use "a professor"), NO medical scenes unless explicitly mentioned

VISUAL METAPHORS for abstract concepts:
- compromise/coexistence → handshake, yin-yang, balance scale
- unintended consequences → domino effect, ripple in water, butterfly effect
- power/control → puppet strings, chess pieces, hand on lever
- chaos vs order → wild garden vs manicured lawn, organic vs geometric
- fragility → glass sculpture, soap bubble, delicate flower
- progress/evolution → ascending stairs, growing tree, dawn light
- hidden danger → crack in dam, iceberg below surface, shadow behind smile
- ethical dilemma → crossroads, split path, figure at a fork

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Step 1: What is this saying? Step 2: What scene shows this?"""
    }

    @classmethod
    def get_template(cls, template_type, **kwargs):
        templates = {
            "theme_analysis": cls.THEME_ANALYSIS,
            "theme_extraction": cls.THEME_ANALYSIS,
            "shot_prompt_sd": cls.SHOT_PROMPT_SD,
            "shot_prompt_sdxl": cls.SHOT_PROMPT_SDXL,
            "shot_prompt_flux": cls.SHOT_PROMPT_FLUX,
            "shot_prompt_sd3": cls.SHOT_PROMPT_SD3,
        }

        if template_type not in templates:
            return {
                "system": "",
                "user": kwargs.get("text", kwargs.get("description", ""))
            }

        template = templates[template_type]
        is_shot_prompt = template_type.startswith("shot_prompt_")

        if is_shot_prompt:
            visual_style = kwargs.get("visual_style", "")
            if visual_style and visual_style.strip():
                non_realistic_keywords = ['pixar', 'ghibli', 'anime', 'manga', 'cartoon', 
                    'oil painting', 'watercolor', 'line art', 'van gogh', 'da vinci',
                    'sketch', 'illustration', '3d animation', 'cel shading',
                    '皮克斯', '吉卜力', '动漫', '油画', '水彩', '梵高', '达芬奇', '黑白线条', '多巴胺']
                is_non_realistic = any(kw.lower() in visual_style.lower() for kw in non_realistic_keywords)
                if is_non_realistic:
                    style_instruction = f"【Style】Must use: {visual_style}\n【Style Override】This is a NON-REALISTIC style. Do NOT use photorealistic, RAW photo, or documentary keywords. Embrace the artistic/stylized aesthetic."
                else:
                    style_instruction = f"【Style】Must use: {visual_style}"
            else:
                style_instruction = "【Style】Choose appropriate style based on content."

            core_theme = kwargs.get("core_theme", "")
            visual_tone = kwargs.get("visual_tone", "")
            core_theme_display = core_theme if core_theme and core_theme != "未指定" else "根据配音内容确定"
            visual_tone_display = visual_tone if visual_tone and visual_tone.strip() else "根据内容确定"
            content_type_display = kwargs.get("content_type", "") or "未指定类型"

            if (core_theme and core_theme != "未指定") or (visual_tone and visual_tone.strip()):
                theme_parts = []
                if core_theme and core_theme != "未指定":
                    theme_parts.append(f"Core theme: {core_theme}")
                if visual_tone and visual_tone.strip():
                    theme_parts.append(f"Visual tone: {visual_tone}")
                theme_text = ", ".join(theme_parts)
                theme_instruction = f"【Theme】{theme_text} - MUST reflect in visual elements."
            else:
                theme_instruction = ""

            theme_elements = kwargs.get("theme_elements", "")
            if theme_elements and theme_elements != "根据配音内容确定":
                theme_instruction += f"\n【Key Visual Elements】MUST include these elements in the scene: {theme_elements}"

            visual_narrative_strategy = kwargs.get("visual_narrative_strategy", "")
            if visual_narrative_strategy:
                strategy_short = {
                    '时间线叙事': 'TIMELINE: chronological visual progression (ancient→modern)',
                    '空间探索': 'SPATIAL: wide shots→close-up details, macro/micro alternation',
                    '主题递进': 'THEMATIC DEEPENING: surface→abstract, each shot adds new layer',
                    '对比叙事': 'CONTRAST: alternate opposing elements (light/dark, old/new)',
                    '隐喻主线': 'METAPHOR: ONE consistent metaphor throughout (tree/river/building)',
                }
                strategy_text = strategy_short.get(visual_narrative_strategy, visual_narrative_strategy)
                theme_instruction += f"\n【Narrative Strategy】{strategy_text}"

            system_content = template["system"].format(
                style_instruction=style_instruction,
                theme_instruction=theme_instruction,
                content_type=content_type_display,
                core_theme=core_theme_display,
                visual_tone=visual_tone_display,
            )
            system_content = system_content.replace("\n\n\n", "\n\n")

            dubbing = kwargs.get("dubbing", "")
            context_hint = kwargs.get("context_hint", "")
            context_section = f"{context_hint}\n\n" if context_hint else ""

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

    @classmethod
    def get_template_key_for_model(cls, sd_model_name):
        if not sd_model_name:
            return "shot_prompt_sd"

        model_lower = sd_model_name.lower()

        if any(kw in model_lower for kw in ['sdxl', 'xl']):
            return "shot_prompt_sdxl"
        elif any(kw in model_lower for kw in ['flux', 'flx']):
            return "shot_prompt_flux"
        elif any(kw in model_lower for kw in ['sd3', 'sd 3', 'stable diffusion 3']):
            return "shot_prompt_sd3"
        else:
            return "shot_prompt_sd"
