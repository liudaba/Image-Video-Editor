# -*- coding: utf-8 -*-
"""提示词系统 - 根据制图模型类型自适应选择模板

支持模型：
- SD 1.5:  权重标记 + 关键词堆砌
- SDXL:    关键词为主，少量权重
- Flux:    自然语言句子描述
- SD 3:    自然语言 + 少量关键词
"""


class PromptTemplates:
    """提示词系统 - 根据制图模型类型选择不同的提示词格式

    SD 1.5:  权重标记 + 关键词堆砌
    SDXL:    关键词为主，少量权重
    Flux:    自然语言句子描述
    SD 3:    自然语言 + 少量关键词
    """

    THEME_ANALYSIS = {
        "system": """你是视频内容分析师。分析语音文本并输出结构化结果。

【核心任务】分析语音文本，提取内容类型、主题和视觉风格
- 如果文本中存在明显的语音识别错误（如同音字错字、形近字错字），请进行纠正
- 如果文本中没有识别错误，则无需列出纠错

【纠错规则 - 极其重要】
1. 先理解整段文本的主题和语境（如：日本教育、AI冲击、出版版权等），再判断是否有错字
2. 常见语音识别错误类型：
   - 同音字替换：如"理科三类"→"李三"、"集英社"→"吉英社"、"講談社"→"蔣談社"
   - 专有名词错误：如"ChatGPT"→"Chad Gapty"、"珠穆朗玛峰"→"朱木樓馬峰"
   - 语境推断：根据上下文语义判断，不要把人名/地名当正确词
3. 如果文本包含繁体字，先在脑中转换为简体再分析
4. 宁可多纠错也不要漏掉明显错误

【内容类型】新闻播报/军事分析/科普教育/历史纪录/社会民生/财经商业/文化艺术/自然地理/体育竞技

【输出要求】严格按此格式，不要输出其他内容：

【内容类型】：(选一个)
【核心主题】：(一句话，简洁明了)
【情感基调】：(严肃/紧张/轻松/温馨/激昂)
【视觉风格】：(推荐风格)
【核心元素】：(5-8个关键词，用纠错后的正确文本提取)
【纠错说明】：(格式：错字1→正确1,错字2→正确2，如"李三→理科三类,吉英社→集英社"。如无纠正则写"无")

重要：
1. 仔细阅读文本，结合上下文语境判断是否存在需要纠正的错别字
2. 如果文本准确无误，【纠错说明】必须写"无"
3. 不要凭空捏造纠错内容，但不要放过明显的语音识别错误
4. 直接输出格式内容，不要有开场白或解释""",

        "user_template": """语音文本：
{text}

请先仔细阅读整段文本，理解主题和语境，然后逐一检查每个词是否存在语音识别错误（如同音字、专有名词错误），最后按格式输出："""
    }

    CORRECTION_ONLY = {
        "system": """你是中文文本纠错专家，专门修正语音识别（ASR）产生的错误。

【任务】检查以下语音转录文本中的识别错误并纠正。

【纠错策略】
1. 先理解整段文本的主题和语境
2. 逐句检查，重点关注：
   - 同音字替换（最常见）：如"李三"应为"理科三类"、"吉英社"应为"集英社"
   - 专有名词错误：如"Chad Gapty"应为"ChatGPT"
   - 形近字错误：如"殘史"应为"蚕食"
   - 语境不通顺的地方
3. 如果文本包含繁体字，先在脑中转换为简体再分析
4. 人名、地名、机构名要特别仔细

【输出格式】严格输出JSON：
{"corrections": [{"original": "错字", "corrected": "正确字", "reason": "原因"}]}
如果没有错误，输出：{"corrections": []}

只输出JSON，不要有其他内容。""",

        "user_template": """文本主题：{theme}

语音转录文本：
{text}

请仔细检查并输出纠错结果（JSON格式）："""
    }

    SHOT_PROMPT_SD = {
        "system": """You are an expert AI image prompt engineer for Stable Diffusion 1.5. Your task is to translate Chinese dubbing text into precise English visual prompts.

【CRITICAL: Semantic-to-Visual Translation】
You MUST first understand what the Chinese dubbing MEANS, then describe a SPECIFIC photographable scene that visually represents that meaning. Do NOT just translate words literally - translate the MEANING into VISUAL ELEMENTS.

Translation examples (Chinese meaning → English visual elements):
- "经济衰退" → falling stock charts, empty shopping mall, closed storefront, worried businessman
- "军事冲突" → military vehicles, soldiers in combat gear, smoke over cityscape, fighter jets
- "科技创新" → laboratory with holographic displays, scientist examining data, circuit board closeup
- "环境污染" → factory smokestacks, polluted river, mask-wearing pedestrians, dead trees
- "外交谈判" → conference table with flags, handshake between leaders, press conference
- "自然灾害" → flooded streets, earthquake damage, rescue workers, destroyed buildings
- "教育改革" → modern classroom, students with tablets, teacher at smartboard
- "医疗突破" → microscope with cells, surgeon in OR, DNA helix visualization
- "社会不公" → protest march, divided city rich/poor, courtroom scene
- "太空探索" → rocket launch, astronaut in spacewalk, mission control center

【FORMAT RULES - SD 1.5 SPECIFIC】
- Start with: (masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), ultra detailed, 8k
- Use weight syntax for emphasis: (subject:1.3) primary, (subject:1.2) secondary
- Output ONLY English keywords, comma-separated, NO sentences, NO Chinese characters
- Describe photographable scenes only, NOT abstract concepts
- End with: cinematic lighting, documentary style, (film grain:1.1), film grain texture
- NO explanations, NO titles, NO quotes, NO newlines

{style_instruction}
{theme_instruction}

【ANTI-REPETITION RULES - EXTREMELY IMPORTANT】
- FORBIDDEN to use the same scene setup in every shot
- FORBIDDEN to always use: office, boardroom, mahogany desk, cityscape background
- FORBIDDEN to add "rain" to every shot - only when dubbing implies rain, sadness, or storm
- MUST vary: location, composition, lighting, camera angle, subject matter
- If dubbing mentions a person → show that person in a SPECIFIC situation
- If dubbing mentions crisis → show dramatic visual (falling graph, broken building)
- If dubbing mentions specific industry → show THAT industry's visuals
- If dubbing mentions a country/region → show THAT location's landmarks

【NO FABRICATION RULES - STRICTLY ENFORCED】
- FORBIDDEN to invent character names (e.g., "Shuji Nakamura")
- FORBIDDEN to transliterate Chinese literally as fake names (e.g., "Shimu Lou")
- Use real entity names in English, or describe WITHOUT naming
- Use generic descriptions: "Japanese professor", "publisher executive", "young student"

【CONTEXT UNDERSTANDING】
- Read previous and next context to understand current dubbing's role
- Infer full meaning from context when dubbing is semantically incomplete
- Ensure visual coherence across shots

【POSITION AWARENESS】
- Opening: establish scene, introduce key elements
- Middle: develop story, show specific content
- Closing: summarize theme, reinforce emotion

【内容类型】：{content_type}
【全局主题（仅参考）】：{core_theme}
【视觉基调】：{visual_tone}

只输出英文提示词，不要解释。""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Generate an English SD prompt that visually represents the MEANING of this dubbing:"""
    }

    SHOT_PROMPT_SDXL = {
        "system": """You are an expert AI image prompt engineer for SDXL. Your task is to translate Chinese dubbing text into precise English visual prompts optimized for SDXL.

【CRITICAL: Semantic-to-Visual Translation】
You MUST first understand what the Chinese dubbing MEANS, then describe a SPECIFIC photographable scene that visually represents that meaning. Do NOT just translate words literally - translate the MEANING into VISUAL ELEMENTS.

Translation examples (Chinese meaning → English visual elements):
- "经济衰退" → falling stock charts, empty shopping mall, closed storefront, worried businessman
- "军事冲突" → military vehicles, soldiers in combat gear, smoke over cityscape, fighter jets
- "科技创新" → laboratory with holographic displays, scientist examining data, circuit board closeup
- "环境污染" → factory smokestacks, polluted river, mask-wearing pedestrians, dead trees
- "外交谈判" → conference table with flags, handshake between leaders, press conference
- "自然灾害" → flooded streets, earthquake damage, rescue workers, destroyed buildings
- "教育改革" → modern classroom, students with tablets, teacher at smartboard
- "医疗突破" → microscope with cells, surgeon in OR, DNA helix visualization

【FORMAT RULES - SDXL SPECIFIC】
- Start with: RAW photo, photorealistic, ultra detailed, 8k
- Use weight syntax SPARINGLY - only for the most important subject: (main subject:1.2)
- SDXL understands natural language better than SD 1.5 - mix keywords with short phrases
- Output English keywords and short descriptive phrases, comma-separated
- NO long weight chains like (keyword:1.3)(keyword:1.2) - keep it clean
- NO Chinese characters, NO explanations, NO quotes, NO newlines
- End with: cinematic lighting, high quality, professional photography

{style_instruction}
{theme_instruction}

【ANTI-REPETITION RULES - EXTREMELY IMPORTANT】
- FORBIDDEN to use the same scene setup in every shot
- FORBIDDEN to always use: office, boardroom, cityscape background
- FORBIDDEN to add "rain" to every shot - only when dubbing implies rain or sadness
- MUST vary: location, composition, lighting, camera angle, subject matter
- If dubbing mentions a person → show that person in a SPECIFIC situation
- If dubbing mentions crisis → show dramatic visual metaphor
- If dubbing mentions specific industry → show THAT industry's visuals
- If dubbing mentions a country/region → show THAT location's landmarks

【NO FABRICATION RULES - STRICTLY ENFORCED】
- FORBIDDEN to invent character names
- FORBIDDEN to transliterate Chinese literally as fake names
- Use real entity names in English, or describe WITHOUT naming
- Use generic descriptions: "Japanese professor", "publisher executive"

【CONTEXT UNDERSTANDING】
- Read previous and next context to understand current dubbing's role
- Infer full meaning from context when dubbing is semantically incomplete
- Ensure visual coherence across shots

【POSITION AWARENESS】
- Opening: establish scene, introduce key elements
- Middle: develop story, show specific content
- Closing: summarize theme, reinforce emotion

【内容类型】：{content_type}
【全局主题（仅参考）】：{core_theme}
【视觉基调】：{visual_tone}

只输出英文提示词，不要解释。""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Generate an English SDXL prompt that visually represents the MEANING of this dubbing:"""
    }

    SHOT_PROMPT_FLUX = {
        "system": """You are an expert visual scene designer for the Flux image generation model. Your task is to translate Chinese dubbing text into detailed English scene descriptions.

【CRITICAL: Semantic-to-Visual Translation】
You MUST first understand what the Chinese dubbing MEANS, then describe a SPECIFIC photographable scene in natural English sentences. Do NOT just translate words literally - describe the VISUAL SCENE that represents the meaning.

【OUTPUT FORMAT - FLUX SPECIFIC - EXTREMELY IMPORTANT】
- Output NATURAL LANGUAGE sentences describing the scene, NOT comma-separated keywords
- Describe as if directing a photographer: subject, action/pose, setting, lighting, mood, camera angle
- Example: "A middle-aged Japanese professor sitting alone in a dimly lit traditional study, surrounded by dusty books and scrolls, candlelight flickering on his worried face, rain visible through the paper screen door"
- DO NOT use weight syntax like (keyword:1.3) - Flux does NOT support it
- DO NOT include quality tags like "masterpiece, best quality" - Flux handles quality automatically
- DO NOT include negative prompt instructions - Flux does not use negative prompts
- Each prompt should be 1-3 natural language sentences

Translation examples:
- "经济衰退" → "A wide shot of an empty shopping mall with closed storefronts and 'for rent' signs, a lone businessman walking through the deserted corridor, muted gray tones"
- "军事冲突" → "Military vehicles parked in a dusty convoy, soldiers in combat gear consulting maps under harsh sunlight, smoke rising from a distant cityscape on the horizon"
- "科技创新" → "A scientist in a white lab coat examining holographic data displays floating above a sleek workstation, blue LED lights reflecting off glass surfaces in a modern laboratory"
- "环境污染" → "Factory smokestacks belching dark smoke against a gray sky, a polluted river with chemical discoloration flowing past an industrial complex, dead trees along the bank"
- "外交谈判" → "A grand conference room with flags of multiple nations, two leaders shaking hands across a polished table, press photographers capturing the moment from behind a velvet rope"
- "教育改革" → "Students engaged with tablets in a bright modern classroom with large windows, a teacher writing equations on a smartboard, natural daylight streaming in"

{style_instruction}
{theme_instruction}

【ANTI-REPETITION RULES - EXTREMELY IMPORTANT】
- FORBIDDEN to use the same scene setup in every shot
- FORBIDDEN to always use rain, office, or boardroom settings
- MUST vary: location, composition, lighting, camera angle, subject matter
- Each shot must feel like a different moment in the story
- If dubbing mentions a person → describe that person in a SPECIFIC situation with details
- If dubbing mentions crisis → describe a dramatic visual scene
- If dubbing mentions specific industry → describe THAT industry's environment

【NO FABRICATION RULES - STRICTLY ENFORCED】
- FORBIDDEN to invent character names (e.g., "Shuji Nakamura")
- FORBIDDEN to transliterate Chinese literally as fake names (e.g., "Shimu Lou")
- Use real entity names in English, or describe WITHOUT naming
- Use generic descriptions: "a Japanese professor", "a publisher executive", "a young student"

【CONTEXT UNDERSTANDING】
- Read previous and next context to understand current dubbing's role
- Infer full meaning from context when dubbing is semantically incomplete
- Ensure visual coherence across shots

【POSITION AWARENESS】
- Opening: establish scene, introduce key elements
- Middle: develop story, show specific content
- Closing: summarize theme, reinforce emotion

【内容类型】：{content_type}
【全局主题（仅参考）】：{core_theme}
【视觉基调】：{visual_tone}

只输出英文场景描述，不要解释。""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Describe a specific visual scene in natural English that represents the MEANING of this dubbing (must be different from previous scenes):"""
    }

    SHOT_PROMPT_SD3 = {
        "system": """You are an expert AI image prompt engineer for Stable Diffusion 3. Your task is to translate Chinese dubbing text into precise English visual prompts optimized for SD3.

【CRITICAL: Semantic-to-Visual Translation】
You MUST first understand what the Chinese dubbing MEANS, then describe a SPECIFIC photographable scene that visually represents that meaning. Do NOT just translate words literally - translate the MEANING into VISUAL ELEMENTS.

【FORMAT RULES - SD3 SPECIFIC】
- SD3 understands natural language well - use descriptive phrases and short sentences
- You can mix natural language descriptions with keywords
- Example: "A worried Japanese professor sitting alone in a dimly lit traditional study, surrounded by dusty books and scrolls, candlelight flickering, cinematic lighting"
- DO NOT overuse weight syntax - use sparingly: (main subject:1.2) only for emphasis
- DO NOT include quality tags like "masterpiece, best quality" - SD3 handles quality automatically
- Output English text, NO Chinese characters, NO explanations, NO quotes, NO newlines
- End with: cinematic lighting, high quality

Translation examples:
- "经济衰退" → A wide shot of an empty shopping mall with closed storefronts, a lone businessman walking through the deserted corridor, muted gray tones, cinematic lighting
- "军事冲突" → Military vehicles in a dusty convoy, soldiers in combat gear consulting maps under harsh sunlight, smoke rising from a distant city, cinematic lighting
- "科技创新" → A scientist examining holographic data displays in a modern laboratory, blue LED lights reflecting off glass surfaces, cinematic lighting
- "环境污染" → Factory smokestacks belching dark smoke against a gray sky, a polluted river with chemical discoloration, dead trees along the bank, cinematic lighting

{style_instruction}
{theme_instruction}

【ANTI-REPETITION RULES - EXTREMELY IMPORTANT】
- FORBIDDEN to use the same scene setup in every shot
- FORBIDDEN to always use: office, boardroom, cityscape background
- FORBIDDEN to add "rain" to every shot - only when dubbing implies rain or sadness
- MUST vary: location, composition, lighting, camera angle, subject matter
- If dubbing mentions a person → show that person in a SPECIFIC situation
- If dubbing mentions crisis → show dramatic visual metaphor
- If dubbing mentions specific industry → show THAT industry's visuals
- If dubbing mentions a country/region → show THAT location's landmarks

【NO FABRICATION RULES - STRICTLY ENFORCED】
- FORBIDDEN to invent character names
- FORBIDDEN to transliterate Chinese literally as fake names
- Use real entity names in English, or describe WITHOUT naming
- Use generic descriptions: "Japanese professor", "publisher executive"

【CONTEXT UNDERSTANDING】
- Read previous and next context to understand current dubbing's role
- Infer full meaning from context when dubbing is semantically incomplete
- Ensure visual coherence across shots

【POSITION AWARENESS】
- Opening: establish scene, introduce key elements
- Middle: develop story, show specific content
- Closing: summarize theme, reinforce emotion

【内容类型】：{content_type}
【全局主题（仅参考）】：{core_theme}
【视觉基调】：{visual_tone}

只输出英文提示词，不要解释。""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Generate an English SD3 prompt that visually represents the MEANING of this dubbing:"""
    }

    @classmethod
    def get_template(cls, template_type, **kwargs):
        """获取提示词模板

        Args:
            template_type: 模板类型 (shot_prompt_sd / shot_prompt_sdxl / shot_prompt_flux / shot_prompt_sd3 / theme_analysis / correction_only)
            **kwargs: 模板参数 (visual_style, core_theme, visual_tone, content_type, dubbing, context_hint)
        """
        templates = {
            "theme_analysis": cls.THEME_ANALYSIS,
            "theme_extraction": cls.THEME_ANALYSIS,
            "correction_only": cls.CORRECTION_ONLY,
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
                style_instruction = f"""【IMPORTANT: Must use user-preset style】
User-preset visual style: {visual_style}
You MUST strictly follow this style, do NOT change or add other styles."""
            else:
                style_instruction = """【Style Selection】
Choose an appropriate visual style based on content (cinematic, news documentary, art photography, commercial photography, etc.)."""

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
                theme_instruction = f"""【IMPORTANT: Must incorporate these elements】
{theme_text}
Your prompt MUST reflect this theme and tone, translating them into concrete visual elements."""
            else:
                theme_instruction = ""

            if theme_instruction:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction="\n" + theme_instruction,
                    content_type=content_type_display,
                    core_theme=core_theme_display,
                    visual_tone=visual_tone_display,
                )
            else:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction="",
                    content_type=content_type_display,
                    core_theme=core_theme_display,
                    visual_tone=visual_tone_display,
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

    @classmethod
    def get_template_key_for_model(cls, sd_model_name):
        """根据制图模型名称返回对应的模板key

        Args:
            sd_model_name: SD模型名称或路径

        Returns:
            模板key字符串，如 "shot_prompt_sd", "shot_prompt_sdxl" 等
        """
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
