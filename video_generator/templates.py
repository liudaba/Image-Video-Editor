# -*- coding: utf-8 -*-
"""PromptTemplates - 精简提示词系统 - 只给规则，不给案例，让大模型自主创作"""

import re
from .config import Config


class PromptTemplates:
    """精简提示词系统 - 只给规则不给案例，让大模型自主创作
    
    核心原则：
    1. 只给大模型格式规则和质量要求，不给具体案例
    2. 大模型负责：分析内容、纠正错别字、确定主题基调、生成提示词
    3. 不用案例约束大模型，让它根据内容自主发挥
    4. 输出必须是纯粹的提示词，不含任何解释性文字
    """
    
    THEME_ANALYSIS = {
        "system": """你是视频内容分析师。分析语音文本并输出结构化结果。

【核心任务】分析语音文本，提取内容类型、主题和视觉风格
- 如果文本中存在明显的语音识别错误（如同音字错字、形近字错字、人名错字），请进行纠正
- 特别注意人名纠错：如"王建林"→"王健林"、"李延宏"→"李彦宏"、"夏海军"→"夏海钧"等常见商界人物
- 注意成语纠错：如"赤诈风云"→"叱咤风云"、"食物规划"→"低空规划"等同音字错误
- 如果文本中没有识别错误，则无需列出纠错

【内容类型】新闻播报/军事分析/科普教育/历史纪录/社会民生/财经商业/文化艺术/自然地理/体育竞技

【输出要求】严格按此格式，不要输出其他内容：

【内容类型】：(选一个)
【核心主题】：(一句话，简洁明了)
【情感基调】：(严肃/紧张/轻松/温馨/激昂)
【视觉风格】：(推荐风格)
【核心元素】：(5-8个关键词)
【纠错说明】：(仅当存在实际错别字纠正时列出，格式：错字1→正确1,错字2→正确2，如无纠正则写"无")

重要：
1. 仔细阅读文本，判断是否存在需要纠正的错别字，特别是人名和专有名词
2. 如果文本准确无误，【纠错说明】必须写"无"
3. 不要凭空捏造纠错内容
4. 直接输出格式内容，不要有开场白或解释""",
        
        "user_template": """语音文本：
{text}

请先仔细检查整个文本，找出所有可能的语音识别错误，然后按格式输出："""
    }
    
    DUBBING_SEMANTIC_MAPPING = {
        "en": """
【核心规则】提示词必须准确反映当前配音内容的具体场景和语义，每个分镜的配音不同，提示词必须独特，禁止千篇一律
【反重复】禁止每个分镜都用office/boardroom/mahogany desk/cityscape，必须根据配音内容变换场景、构图、主体"""
    }
    
    SHOT_PROMPT_SD = {
        "system": """你是AI图像提示词工程师，为absoluteRealisticVision v20写实模型生成英文提示词。

【格式规则】
- 必须以质量前缀开头：(masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), ultra detailed, 8k
- 只输出英文关键词，逗号分隔，禁止使用完整句子，禁止输出中文
- 描述可拍摄的画面内容，不要描述抽象概念或叙事
- 重要主体用权重语法强调：(subject:1.3)表示主要主体，(subject:1.2)表示次要主体
- 不要输出解释、标题、标注、括号说明
- 结尾必须添加：cinematic lighting, documentary style, (film grain:1.1)

【反重复规则】
- 禁止每个分镜都用相同的场景（如office/boardroom/mahogany desk/cityscape）
- 必须根据配音内容变换：地点、构图、主体、光线、角度
- 配音提到人物→展示该人物的具体情境（不是站在办公室）
- 配音提到危机/债务→展示戏剧性视觉隐喻（下跌图表、破碎建筑）
- 配音提到法律问题→展示法庭、警察、法槌
- 配音提到特定行业→展示该行业的视觉元素（工地、实验室、农田）

{semantic_mapping}

{style_instruction}
{theme_instruction}

【必加标签】(masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), cinematic lighting, documentary style, (film grain:1.1)""",
        
        "user_template": """配音：{dubbing}

输出英文提示词："""
    }
    
    @classmethod
    def get_template(cls, template_type, **kwargs):
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
                style_instruction = f"【必须使用用户预设的风格】{visual_style}"
            else:
                style_instruction = "【风格选择】根据内容自主选择合适的视觉风格"
            
            core_theme = kwargs.get("core_theme", "")
            visual_tone = kwargs.get("visual_tone", "")
            
            theme_parts = []
            if core_theme and core_theme != "未指定":
                theme_parts.append(f"核心主题：{core_theme}")
            if visual_tone and visual_tone.strip():
                theme_parts.append(f"视觉基调：{visual_tone}")
            
            theme_instruction = f"【必须融入】{', '.join(theme_parts)}，将其转化为具体视觉元素" if theme_parts else ""
            
            semantic_mapping = cls.DUBBING_SEMANTIC_MAPPING["en"]
            
            system_content = template["system"].format(
                style_instruction=style_instruction,
                theme_instruction=theme_instruction,
                semantic_mapping=semantic_mapping
            )
            system_content = system_content.replace("\n\n\n", "\n\n")
            
            dubbing = kwargs.get("dubbing", "")
            user_content = f"配音：{dubbing}\n\n输出提示词："
        else:
            system_content = template["system"]
            user_content = template["user_template"].format(**kwargs)
        
        return {
            "system": system_content,
            "user": user_content
        }
