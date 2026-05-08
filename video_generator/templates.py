# -*- coding: utf-8 -*-
"""提示词系统 - 根据制图模型类型自适应选择模板

核心改进：三阶段思考法（Chain-of-Thought）
阶段1: 深度语义理解 — 这段配音的核心信息是什么？情感是什么？
阶段2: 视觉场景翻译 — 用什么具体的、可拍摄的画面来表现这个核心信息？
阶段3: 提示词构建 — 用SD能理解的关键词精确描述这个画面

支持模型：
- SD 1.5:  权重标记 + 关键词
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

    _COMMON_RULES = (
        "CRITICAL RULES - SEMANTIC ACCURACY:\n"
        "1. CONCRETE SCENE FIRST: Every prompt MUST describe a specific, photographable scene that directly illustrates the dubbing text's meaning. Think 'what would a photographer shoot?' NOT 'what abstract concept does this relate to?'\n"
        "2. SEMANTIC FIDELITY: The visual scene MUST directly reflect the SPECIFIC meaning of THIS dubbing line, not just the general topic. Each line has a unique message - your scene must capture THAT message.\n"
        "3. VISUALLY RENDERABLE ONLY: Every keyword must be something SD can draw. BANNED abstract terms: 'political intrigue', 'international relations', 'tension', 'power struggle', 'strategic control', 'political landscape', 'energy sector', 'decay', 'fragility', 'conflict'. Replace with concrete visuals: 'men in suits arguing at a table', 'soldiers standing guard outside a palace', 'hands shaking over a contract'.\n"
        "4. FOCUS: Use 3-5 key visual elements per prompt. Too many elements = SD produces noise. Prioritize the MOST important visual that captures the core meaning.\n"
        "5. CHARACTER CONSISTENCY: If the dubbing mentions a real person (e.g. Maduro, Cilia Flores), use their name consistently. Do NOT invent or swap names. If unsure of the exact name, use a generic descriptor like 'a president', 'a woman in power suit'.\n"
        "6. NO GENERIC BACKGROUNDS: Do NOT default to 'dimly lit office', 'crumbling building', 'shadows' for every shot. Match the background to the SPECIFIC content of each line.\n"
        "\n"
        "CHINESE IDIOM AND METAPHOR HANDLING - CRITICAL:\n"
        "Chinese idioms/metaphors must be translated by MEANING, NOT word-for-word. Depict the REAL-WORLD CONSEQUENCE or SITUATION the idiom describes:\n"
        "- \"天降神兵\" = unexpected rescue/savior -> show 'no help arriving, standing alone', NOT 'ancient cannon' or 'soldiers falling from sky'\n"
        "- \"捆在战车上\" = interests tied together -> show 'generals surrounded by wealth tied to leader', NOT 'ropes and restraints on people' or 'chariot'\n"
        "- \"压舱石\" = stabilizing force/foundation -> show 'military as unshakable foundation of power', NOT 'a person holding a stone' or 'ship ballast'\n"
        "- \"走钢丝\" = precarious balance -> show 'diplomat carefully navigating between opposing forces', NOT 'tightrope walker' or 'hand balancing globe on rope'\n"
        "- \"慢性病\" = slowly worsening problem -> show 'gradually deteriorating situation, cracks widening over time', NOT 'medical examination or stethoscope or syringe'\n"
        "- \"铁桶\" = airtight protection -> show 'impenetrable wall of guards around power center', NOT 'a metal barrel'\n"
        "- \"后路被堵死\" = no way out -> show 'all exits sealed, trapped with no escape route', NOT 'broken telegraph machine'\n"
        "- \"筹码\" / \"牌\" = leverage/bargaining power -> show 'using resources as leverage in negotiation', NOT 'a bronze key in stone chamber' or 'playing cards'\n"
        "- \"大棋局\" = geopolitical competition -> show 'diplomats negotiating in formal setting', NOT 'chessboard with miniature figures'\n"
        "- \"钉子\" (strategic nail) = strategic foothold -> show 'military base in foreign territory', NOT 'a literal nail on a map'\n"
        "- \"金山银山\" = vast wealth -> show 'generals surrounded by oil contracts and gold', NOT 'mountain of coins'\n"
        "- \"高枕无忧\" = carefree security -> show 'false sense of security, hidden threats', NOT 'pillow or sleeping'\n"
        "- \"垃圾站\" = miserable situation -> show 'deteriorating living conditions', NOT 'actual garbage dump'\n"
        "- RULE: When you encounter ANY Chinese metaphor in the dubbing, ask yourself: 'What REAL SCENE does this metaphor describe in the political/social context?' Then depict THAT real-world scene. NEVER depict the literal imagery of the metaphor.\n"
        "\n"
        "BAD vs GOOD examples:\n"
        "- BAD: (Maduro:1.3), Venezuela, military, energy, political, international relations, chessboard, shadow, crumbling building\n"
        "  WHY BAD: Abstract terms SD cannot render; no specific scene; generic background\n"
        "- GOOD: (Maduro:1.3), standing alone on a palace balcony, no allies in sight, empty courtyard below, storm clouds gathering, medium shot\n"
        "  WHY GOOD: Specific scene; directly illustrates 'no savior coming'; concrete visual elements\n"
        "\n"
        "- BAD: (military:1.3), cracked concrete, barbed wire, surveillance cameras, darkened cityscape, tension, strategic map\n"
        "  WHY BAD: 'tension' and 'strategic map' are abstract; random elements with no coherent scene\n"
        "- GOOD: (military general:1.3), weighing gold bars on one side and a rifle on the other, at a desk piled with oil contracts, close-up on the scale\n"
        "\n"
        "SCENE VARIETY:\n"
        "- Each prompt: DIFFERENT scene, DIFFERENT camera angle, DIFFERENT focal point\n"
        "- Rotate: wide establishing shot -> medium shot with action -> close-up on detail -> symbolic still life -> environmental shot\n"
        "- NEVER repeat the same visual element across consecutive shots\n"
        "\n"
        "BACKGROUND VARIETY - MANDATORY:\n"
        "- Do NOT use the same background setting more than twice in the entire video\n"
        "- Rotate backgrounds: palace interior -> city street -> military base -> courtroom -> border crossing -> rural landscape -> port/harbor -> diplomatic venue -> refugee camp -> oil facility -> parliament hall -> prison corridor -> airport tarmac -> hotel lobby\n"
        "- BANNED from overuse: 'dimly lit room', 'dimly lit office', 'mahogany table', 'overcast sky' - use these AT MOST once every 5 shots\n"
        "\n"
        "WHEN TO USE METAPHORS (sparingly):\n"
        "- ONLY when the dubbing text is itself metaphorical or too abstract for a literal scene\n"
        "- A metaphor MUST be a single, clear, concrete visual (e.g. 'a tightrope walker over a canyon' NOT 'precarious balance')\n"
        "- Prefer literal scenes over metaphors: 'generals counting money' > 'balance scale with gold and guns'\n"
        "\n"
        "OUTPUT FORMAT:\n"
        "- Output ONLY: [understanding] | [prompt]\n"
        "- NO explanatory sentences, NO reasoning text, NO style labels like 'news broadcast style' or 'investigative journalism'\n"
        "- The [prompt] section must contain ONLY comma-separated SD keywords/phrases"
    )

    SHOT_PROMPT_SD = {
        "system": """You are a visual scene designer for SD 1.5. Convert Chinese audio narration into English image prompts.

THINK IN 3 STAGES:
Stage 1 - UNDERSTAND: What is this specific dubbing line saying? What is its unique message?
Stage 2 - VISUALIZE: What concrete, photographable scene would best show this message? What would a photographer capture?
Stage 3 - DESCRIBE: Write SD 1.5 keywords for that specific scene.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence capturing the SPECIFIC meaning of THIS line (not the general topic)
- [prompt]: SD 1.5 keywords, comma-separated, NO quality tags (added auto), NO Chinese
- Weight syntax: (main subject:1.3), (secondary:1.2). Use () only, NOT []
- Keep prompt to 4-7 meaningful keywords/phrases. Less is more for SD 1.5.

Examples:
[A president's survival depends on military loyalty, not divine intervention] | (Maduro:1.3), standing alone on palace balcony, empty courtyard below, storm clouds, no allies visible, medium shot
[Power comes from military guns, not ballot boxes] | (soldier's hand:1.3) holding rifle, ballot papers scattered on ground, boot stepping on votes, close-up, low angle
[Oil wealth is traded for military allegiance] | (oil barrel:1.3), military general counting gold, handshake over contract, dim office, medium shot
[A woman weaving a network of political connections] | (woman in suit:1.3), connecting red threads on a wall of photos, judicial building in background, close-up on hands

{style_instruction}
{theme_instruction}

{_COMMON_RULES}

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Think step by step:
1. What is the SPECIFIC message of this line?
2. What ONE concrete scene best shows this message?
3. Write the prompt for that scene.

Output: [understanding] | [prompt]"""
    }

    SHOT_PROMPT_SDXL = {
        "system": """You are a visual scene designer for SDXL. Convert Chinese audio narration into English image prompts.

THINK IN 3 STAGES:
Stage 1 - UNDERSTAND: What is this specific dubbing line saying? What is its unique message?
Stage 2 - VISUALIZE: What concrete, photographable scene would best show this message? What would a photographer capture?
Stage 3 - DESCRIBE: Write SDXL keywords and short phrases for that specific scene.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence capturing the SPECIFIC meaning of THIS line (not the general topic)
- [prompt]: SDXL keywords and short descriptive phrases, comma-separated, NO quality tags (added auto), NO Chinese
- Use weight SPARINGLY: (main subject:1.2) only for the primary subject
- Mix keywords with short phrases - SDXL understands natural language
- Keep prompt focused: 4-8 meaningful elements. Avoid keyword soup.

Examples:
[A president's survival depends on military loyalty, not divine intervention] | (Maduro:1.2), standing alone on a palace balcony looking down at an empty courtyard, storm clouds gathering overhead, no allies in sight, medium shot, dramatic atmosphere
[Power comes from military guns, not ballot boxes] | a soldier's hand gripping a rifle, scattered ballot papers on the ground being stepped on, close-up shot from low angle, stark lighting
[Oil wealth is traded for military allegiance] | (oil barrel:1.2), a military general counting gold bars across a desk covered in contracts, handshake in progress, dimly lit office, medium shot
[A woman weaving a network of political connections] | (woman in power suit:1.2), connecting red threads between photos on a wall, judicial building visible through window, close-up on hands threading connections

{style_instruction}
{theme_instruction}

{_COMMON_RULES}

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Think step by step:
1. What is the SPECIFIC message of this line?
2. What ONE concrete scene best shows this message?
3. Write the prompt for that scene.

Output: [understanding] | [prompt]"""
    }

    SHOT_PROMPT_FLUX = {
        "system": """You are a visual scene designer for Flux. Convert Chinese audio narration into English scene descriptions.

THINK IN 3 STAGES:
Stage 1 - UNDERSTAND: What is this specific dubbing line saying? What is its unique message?
Stage 2 - VISUALIZE: What concrete, photographable scene would best show this message? What would a photographer capture?
Stage 3 - DESCRIBE: Write natural language describing that specific scene.

Output: [understanding] | [description]
- [understanding]: 1 English sentence capturing the SPECIFIC meaning of THIS line (not the general topic)
- [description]: 1-3 natural language sentences describing a CONCRETE visual scene
- NO weight syntax like (keyword:1.3) - Flux does NOT support it. NO quality tags (added auto)
- The description must paint a vivid, specific picture - not list abstract concepts

Examples:
[A president's survival depends on military loyalty, not divine intervention] | A man resembling Maduro stands alone on a grand palace balcony, gazing down at an empty courtyard with no allies in sight, storm clouds gathering overhead, conveying isolation and the absence of rescue
[Power comes from military guns, not ballot boxes] | A close-up of a soldier's boot stepping on scattered ballot papers, a rifle slung over the shoulder, stark overhead lighting casting sharp shadows on the discarded votes
[Oil wealth is traded for military allegiance] | A military general counting gold bars across a desk covered in oil contracts, a handshake frozen mid-motion, dim office lighting revealing the exchange of wealth for loyalty
[A woman weaving a network of political connections] | A woman in a power suit carefully connecting red threads between framed photos on a wall, a judicial building visible through the window behind her, close-up on her hands as she ties another connection

{style_instruction}
{theme_instruction}

{_COMMON_RULES}

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Think step by step:
1. What is the SPECIFIC message of this line?
2. What ONE concrete scene best shows this message?
3. Describe that scene vividly.

Output: [understanding] | [description]"""
    }

    SHOT_PROMPT_SD3 = {
        "system": """You are a visual scene designer for SD3. Convert Chinese audio narration into English image prompts.

THINK IN 3 STAGES:
Stage 1 - UNDERSTAND: What is this specific dubbing line saying? What is its unique message?
Stage 2 - VISUALIZE: What concrete, photographable scene would best show this message? What would a photographer capture?
Stage 3 - DESCRIBE: Write SD3 descriptive phrases and keywords for that specific scene.

Output: [understanding] | [prompt]
- [understanding]: 1 English sentence capturing the SPECIFIC meaning of THIS line (not the general topic)
- [prompt]: SD3 descriptive phrases and keywords, comma-separated, NO quality tags (added auto), NO Chinese
- Use weight SPARINGLY: (main subject:1.2) only for emphasis
- Mix natural language with keywords - SD3 understands both
- Keep prompt focused: 4-8 meaningful elements

Examples:
[A president's survival depends on military loyalty, not divine intervention] | (Maduro:1.2), standing alone on palace balcony, empty courtyard below, storm clouds gathering, no allies visible, medium shot, isolation
[Power comes from military guns, not ballot boxes] | soldier's hand gripping rifle, ballot papers scattered on ground, boot stepping on votes, close-up from low angle, stark lighting
[Oil wealth is traded for military allegiance] | (oil barrel:1.2), military general counting gold bars, handshake over contract, desk covered in documents, dim office, medium shot
[A woman weaving a network of political connections] | (woman in power suit:1.2), connecting red threads between photos on wall, judicial building through window, close-up on hands, political network

{style_instruction}
{theme_instruction}

{_COMMON_RULES}

【内容类型】：{content_type}
【全局主题】：{core_theme}
【视觉基调】：{visual_tone}""",

        "user_template": """{context_section}Current dubbing: {dubbing}

Think step by step:
1. What is the SPECIFIC message of this line?
2. What ONE concrete scene best shows this message?
3. Write the prompt for that scene.

Output: [understanding] | [prompt]"""
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
                if isinstance(theme_elements, list):
                    theme_elements = ", ".join(str(e) for e in theme_elements if e)
                if theme_elements and theme_elements.strip():
                    theme_instruction += f"\n【Key Visual Elements】MUST include these elements in the scene: {theme_elements}"

            visual_narrative_strategy = kwargs.get("visual_narrative_strategy", "")
            if visual_narrative_strategy:
                strategy_short = {
                    '时间线叙事': 'TIMELINE: chronological visual progression (ancient->modern)',
                    '空间探索': 'SPATIAL: wide shots->close-up details, macro/micro alternation',
                    '主题递进': 'THEMATIC DEEPENING: surface->abstract, each shot adds new layer',
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
                _COMMON_RULES=cls._COMMON_RULES,
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
