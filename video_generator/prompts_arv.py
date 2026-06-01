# -*- coding: utf-8 -*-
"""
针对 absoluteRealisticVision v20 模型的提示词工具
仅保留质量标签和基础映射，让大模型自主生成
"""
import re as _re


# 中文关键词→英文场景描述映射表（用于ARV回退时将配音文本转为视觉场景）
_DUBBING_SCENE_MAP = {
    # 政治/权力
    '政治': 'political scene, government building',
    '总统': 'president at podium, national leader',
    '总理': 'prime minister in office, government leader',
    '政府': 'government building interior, official hall',
    '权力': 'power symbol, leader in command',
    '选举': 'election rally, voting scene, ballot boxes',
    '反对派': 'opposition gathering, protest crowd',
    '执政': 'ruling party headquarters, political power',
    # 军事/战争
    '军事': 'military base, soldiers in formation',
    '军方': 'military headquarters, armed forces',
    '战争': 'war zone, battlefield, combat',
    '士兵': 'armed soldiers, military personnel',
    '导弹': 'missile launch, military weapons',
    '坦克': 'tanks on battlefield, armored vehicles',
    '武装': 'armed forces, military equipment',
    # 经济/能源
    '经济': 'financial district, stock exchange',
    '石油': 'oil refinery, petroleum industry',
    '制裁': 'economic sanctions, restricted trade',
    '金融': 'banking, financial center',
    '通胀': 'economic hardship, rising prices',
    '股票': 'stock market trading floor, falling charts',
    '投资': 'investment analysis, financial charts',
    '杠杆': 'financial risk, leveraged trading',
    '资金': 'capital flow, money transaction',
    '现金流': 'cash flow crisis, empty wallet',
    '崩盘': 'market crash, financial panic',
    '裁员': 'layoff scene, office boxes, unemployment',
    '就业': 'job market, employment office, resume',
    '失业': 'unemployment, empty office desks',
    '工资': 'paycheck, salary, wage slip',
    '存款': 'bank savings, ATM, deposit',
    '房贷': 'mortgage, housing loan documents',
    '消费': 'shopping, consumer spending, retail',
    '收入': 'income, earnings report',
    '退休': 'retirement, pension, elderly living',
    # AI/科技/就业
    'AI': 'AI neural network visualization, artificial intelligence interface',
    '人工智能': 'AI technology, digital innovation, futuristic lab',
    '自动化': 'automated factory, robotic assembly line',
    '岗位': 'job position, workplace scene',
    '替代': 'AI replacing workers, automation displacement',
    '算法': 'algorithm visualization, code on screens',
    '数字化': 'digital transformation, screens and data',
    '编程': 'programming, code on monitors, developer workspace',
    '翻译': 'translation work, language processing',
    '设计': 'design workspace, creative studio',
    # 生活/民生
    '柴米油盐': 'daily necessities, grocery shopping, household items',
    '保险': 'insurance policy, safety net documents',
    '储蓄': 'savings, piggy bank, bank book',
    '养老': 'elderly care, retirement planning',
    '教育': 'classroom, education, students studying',
    '医疗': 'hospital, medical care, health insurance',
    '房价': 'real estate, housing prices, apartment buildings',
    '物价': 'price tags, inflation, market goods',
    # 社会/民生
    '难民': 'refugees at border, displaced people',
    '民生': 'civilian daily life, community scene',
    '民众': 'crowd of people, public gathering',
    '食品': 'food distribution, market scene',
    '腐败': 'corruption scene, wealth disparity',
    # 司法
    '审判': 'courtroom, judicial proceedings',
    '法院': 'courtroom interior, judge bench',
    '逮捕': 'arrest scene, law enforcement',
    # 人物
    '将军': 'military general in uniform',
    '外交官': 'diplomat at negotiation table',
    '夫妇': 'couple in formal setting',
    '妻子': 'spouse in formal setting',
    # 地点
    '委内瑞拉': 'Venezuela, Caracas cityscape',
    '俄罗斯': 'Russia, Moscow skyline',
    '中国': 'China, Beijing landmarks',
    '美国': 'United States, Washington DC',
    # 自然/科学
    '宇宙': 'deep space, cosmic scene',
    '黑洞': 'black hole, space phenomenon',
    '森林': 'dense forest, woodland',
    '海洋': 'ocean view, sea landscape',
    '进化': 'evolution concept, life progression',
    '科学': 'laboratory, scientific research',
    # 情感/氛围
    '危机': 'crisis atmosphere, tense situation',
    '希望': 'hopeful scene, warm light',
    '紧张': 'tense atmosphere, dramatic moment',
    '胜利': 'victory celebration, triumph',
    # ===== 新增：日常场景 =====
    # 天气/自然
    '阳光': 'bright sunlight, sunlit scene, warm daylight',
    '晴天': 'clear blue sky, sunny day',
    '雨天': 'rainy scene, wet streets, rain drops',
    '雪': 'snowfall, snowy landscape, winter scene',
    '风': 'windy scene, blowing wind, dynamic atmosphere',
    '雷': 'thunderstorm, lightning strike, dramatic sky',
    '雾': 'foggy atmosphere, misty scene, low visibility',
    '彩虹': 'rainbow in sky, colorful arc, after rain',
    '暴风雨': 'storm scene, heavy rain, dark clouds',
    '洪水': 'flood disaster, rising water, submerged area',
    '地震': 'earthquake destruction, collapsed buildings',
    '火山': 'volcanic eruption, lava flow, ash cloud',
    # 时间
    '早晨': 'early morning, dawn light, sunrise',
    '清晨': 'dawn, first light of day, morning mist',
    '黄昏': 'golden twilight, sunset glow, dusk',
    '夜晚': 'night scene, dark sky, moonlight',
    '深夜': 'late night, dark atmosphere, dim lights',
    '白天': 'daytime, bright daylight, midday sun',
    # 城市/建筑
    '城市': 'cityscape, urban skyline, metropolitan area',
    '街道': 'city street, urban road, pedestrian area',
    '大楼': 'skyscraper, tall building, modern architecture',
    '办公室': 'office interior, workplace, desk and computer',
    '学校': 'school campus, classroom, educational building',
    '医院': 'hospital interior, medical facility',
    '教堂': 'church interior, cathedral, religious building',
    '公园': 'public park, green space, garden',
    '桥': 'bridge structure, crossing over water',
    '港口': 'harbor, port, ships at dock',
    '机场': 'airport terminal, airplanes, runway',
    '车站': 'train station, railway platform',
    '夜景': 'city night view, illuminated skyline, neon lights',
    # 交通
    '汽车': 'automobile, car on road, vehicle',
    '火车': 'train, railway, locomotive',
    '飞机': 'airplane in sky, aircraft, aviation',
    '船': 'ship on water, vessel, boat',
    '地铁': 'subway train, underground station',
    # 人物/职业
    '工人': 'industrial worker, laborer, construction worker',
    '农民': 'farmer in field, agricultural worker',
    '医生': 'doctor in hospital, medical professional',
    '护士': 'nurse in medical setting',
    '教师': 'teacher in classroom, educator',
    '学生': 'student studying, young person learning',
    '商人': 'businessman, corporate professional',
    '警察': 'police officer, law enforcement',
    '消防': 'firefighter, fire engine, emergency rescue',
    '孩子': 'children playing, kids in scene',
    '老人': 'elderly person, senior citizen',
    '家庭': 'family together, family scene',
    # 自然景观
    '大海': 'vast ocean, sea waves, coastal view',
    '河流': 'river flowing, waterway, stream',
    '山': 'mountain landscape, mountain range, peaks',
    '沙漠': 'desert landscape, sand dunes, arid terrain',
    '草原': 'grassland, prairie, open meadow',
    '瀑布': 'waterfall, cascading water, natural wonder',
    '岛屿': 'island, tropical island, surrounded by water',
    '湖': 'lake view, calm water, lakeside',
    '花': 'flowers blooming, floral scene, garden',
    '树': 'trees, woodland, forest canopy',
    # 动物
    '狗': 'dog, canine companion',
    '猫': 'cat, feline',
    '鸟': 'birds flying, avian wildlife',
    '鱼': 'fish underwater, aquatic life',
    '马': 'horse, equestrian scene',
    # 食物/餐饮
    '餐厅': 'restaurant interior, dining room',
    '厨房': 'kitchen interior, cooking scene',
    '市场': 'market scene, marketplace, vendors',
    # 科技
    '电脑': 'computer screen, digital technology',
    '手机': 'smartphone, mobile device',
    '网络': 'digital network, internet concept',
    '机器人': 'robot, artificial intelligence, machine',
    '卫星': 'satellite in orbit, space technology',
    # 文化/艺术
    '音乐': 'musical performance, concert, instruments',
    '舞蹈': 'dance performance, dancer in motion',
    '绘画': 'painting, artist at work, canvas',
    '电影': 'cinema, movie scene, film production',
    '书': 'books, library, reading',
    # 运动
    '运动': 'sports scene, athletic activity',
    '足球': 'soccer match, football game',
    '篮球': 'basketball game, court scene',
    '游泳': 'swimming, pool scene, aquatic sport',
    '跑步': 'running, jogging, track and field',
}


def _extract_scene_from_dubbing(dubbing_text: str) -> str:
    """从配音文本中提取关键视觉场景描述

    通过关键词匹配将中文配音文本转换为英文场景描述，
    确保ARV回退生成的提示词与配音内容语义相关。
    """
    if not dubbing_text:
        return ""

    scene_parts = []
    seen = set()

    for cn_key, en_scene in _DUBBING_SCENE_MAP.items():
        if cn_key in dubbing_text and en_scene not in seen:
            scene_parts.append(en_scene)
            seen.add(en_scene)
            if len(scene_parts) >= 5:
                break

    return ", ".join(scene_parts)


class ARVPromptTemplates:
    """absoluteRealisticVision v20 专用质量标签和基础工具"""

    QUALITY_PREFIX = "(masterpiece, best quality, ultra detailed, 8k:1.2), RAW photo, (photorealistic:1.3), DSLR, high resolution"

    STYLE_TAGS = {
        "documentary": "documentary photography, (film grain:1.1), photojournalism style",
        "cinematic": "(cinematic shot:1.2), dramatic lighting, high contrast, (film grain:1.1), anamorphic lens",
        "news": "breaking news broadcast, (professional broadcast quality:1.1), live report style",
        "war": "(war photojournalism:1.3), battlefield documentary, combat zone, press photography",
    }

    COMPOSITION_TAGS = {
        "close_up": "(close-up shot:1.2), detailed focus, (shallow depth of field:1.1), bokeh background",
        "medium": "medium shot, eye level perspective, balanced composition, 50mm lens",
        "wide": "(wide angle shot:1.1), establishing view, panoramic vista, 24mm lens",
        "aerial": "(aerial drone footage:1.2), overhead view, bird's eye perspective",
        "over_shoulder": "over-the-shoulder shot, looking past subject, depth and context, 85mm lens",
        "dutch_angle": "(dutch angle:1.1), tilted composition, tension and unease, dynamic framing",
        "low_angle": "(low angle shot:1.1), looking upward, power and dominance, dramatic perspective",
        "silhouette": "(silhouette shot:1.2), backlit figure, rim lighting, stark contrast outline",
    }

    LIGHTING_TAGS = {
        "dramatic": "(dramatic chiaroscuro lighting:1.2), strong shadows, high contrast, Rembrandt lighting",
        "natural": "natural lighting, soft ambient light, balanced exposure, diffused daylight",
        "golden": "(golden hour lighting:1.2), warm tones, cinematic glow, sunset rim light",
        "harsh": "harsh lighting, strong directional light, deep shadows, hard edge shadows",
        "moody": "(moody atmosphere:1.1), dim lighting, mysterious ambiance, low key lighting",
    }

    # 非写实风格的替代质量标签
    NON_REALISTIC_PREFIX = "masterpiece, best quality, ultra detailed, vibrant colors, artistic style"
    NON_REALISTIC_STYLES = {
        "pixar": "Pixar style, 3D animation, soft lighting, smooth textures, cute characters",
        "ghibli": "Studio Ghibli style, hand-drawn animation, watercolor backgrounds, dreamy atmosphere",
        "anime": "anime style, cel shading, vibrant colors, manga aesthetic",
        "oil_painting": "oil painting, brush strokes, classical art, textured canvas, rich colors",
        "watercolor": "watercolor painting, soft edges, flowing colors, pastel tones, paper texture",
        "sketch": "line art, ink drawing, monochrome, clean lines, high contrast",
        "cyberpunk": "cyberpunk, neon lights, futuristic, holographic displays, dark atmosphere",
        "van_gogh": "Van Gogh style, impressionism, swirling brushstrokes, vivid colors",
        "da_vinci": "Leonardo da Vinci style, Renaissance painting, sfumato technique, warm earth tones",
    }

    @classmethod
    def generate_prompt(cls, dubbing_text: str, content_type: str = "general",
                        core_theme: str = "", visual_tone: str = "",
                        model_type: str = "sd15", user_styles: list = None,
                        shot_index: int = -1) -> str:
        style = cls._select_style(content_type)
        composition = cls._select_composition(content_type, visual_tone, shot_index)
        lighting = cls._select_lighting(visual_tone)

        # 从配音文本中提取视觉场景描述
        scene_from_dubbing = _extract_scene_from_dubbing(dubbing_text)

        # 检测用户是否选择了非写实风格
        is_non_realistic = False
        non_realistic_style_tag = ""
        if user_styles:
            style_text_lower = " ".join(user_styles).lower()
            nr_keywords = {
                'pixar': 'pixar', '皮克斯': 'pixar',
                'ghibli': 'ghibli', '吉卜力': 'ghibli',
                'anime': 'anime', '动漫': 'anime', '日式动漫': 'anime',
                'oil painting': 'oil_painting', '油画': 'oil_painting',
                'watercolor': 'watercolor', '水彩': 'watercolor',
                'line art': 'sketch', '黑白线条': 'sketch',
                'cyberpunk': 'cyberpunk', '赛博朋克': 'cyberpunk',
                'van gogh': 'van_gogh', '梵高': 'van_gogh',
                'da vinci': 'da_vinci', '达芬奇': 'da_vinci',
            }
            for kw, style_key in nr_keywords.items():
                if kw in style_text_lower:
                    is_non_realistic = True
                    non_realistic_style_tag = cls.NON_REALISTIC_STYLES.get(style_key, "")
                    break

        def _strip_weights(text):
            text = _re.sub(r'\(([^)]+):[\d.]+\)', r'\1', text)
            text = _re.sub(r'\[([^]]+):[\d.]+\]', r'\1', text)
            text = _re.sub(r'\(\(([^)]+)\)\)', r'\1', text)
            return text

        if model_type in ('flux', 'sd3'):
            parts = []
            if is_non_realistic and non_realistic_style_tag:
                parts.append(_strip_weights(non_realistic_style_tag))
            else:
                style_tag = _strip_weights(cls.STYLE_TAGS.get(style, ""))
                if style_tag:
                    parts.append(style_tag)
            comp_tag = _strip_weights(cls.COMPOSITION_TAGS.get(composition, ""))
            light_tag = _strip_weights(cls.LIGHTING_TAGS.get(lighting, ""))
            if comp_tag:
                parts.append(comp_tag)
            if not is_non_realistic and light_tag:
                parts.append(light_tag)
            if scene_from_dubbing:
                parts.append(scene_from_dubbing)
            if core_theme:
                parts.append(core_theme)
            if model_type == 'flux':
                sentence = 'A scene with ' + ', and '.join(p.strip() for p in parts if p.strip())
                sentence = sentence.rstrip(', and ')
            else:
                sentence = '. '.join(p.strip().capitalize() for p in parts if p.strip())
            if sentence and not sentence[0].isupper():
                sentence = sentence[0].upper() + sentence[1:]
            return sentence if sentence else "A cinematic scene"

        # SD15 / SDXL 路径
        if is_non_realistic:
            quality_prefix = cls.NON_REALISTIC_PREFIX
            if model_type == 'sdxl':
                quality_prefix = "masterpiece, best quality, ultra detailed, vibrant colors, artistic style"
        elif model_type == 'sdxl':
            quality_prefix = "RAW photo, photorealistic, ultra detailed, 8k"
        else:
            quality_prefix = cls.QUALITY_PREFIX

        parts = [quality_prefix]

        if is_non_realistic and non_realistic_style_tag:
            parts.append(non_realistic_style_tag)
        else:
            parts.append(cls.STYLE_TAGS.get(style, ""))

        parts.append(cls.COMPOSITION_TAGS.get(composition, ""))

        if not is_non_realistic:
            parts.append(cls.LIGHTING_TAGS.get(lighting, ""))

        # 将配音文本场景描述插入提示词（核心修复：确保语义相关）
        if scene_from_dubbing:
            parts.append(scene_from_dubbing)

        if core_theme:
            parts.append(core_theme)

        return ", ".join(p for p in parts if p)

    @classmethod
    def _select_composition(cls, content_type: str, visual_tone: str = "", shot_index: int = -1) -> str:
        """根据内容类型、视觉基调和分镜序号选择构图
        
        策略：
        - 首分镜(0)：广角建立镜头
        - 尾分镜：中景收束
        - 中间分镜：按序号轮换构图，避免视觉单调
        - 紧张/危机场景：倾斜构图增加张力
        """
        # 首分镜强制广角
        if shot_index == 0:
            return "wide"
        
        # 紧张/危机场景优先倾斜构图
        if visual_tone and any(w in visual_tone for w in ["紧张", "危机", "冲突", "危急", "动荡", "tense", "crisis"]):
            if shot_index >= 0 and shot_index % 3 == 0:
                return "dutch_angle"
        
        # 中间分镜轮换构图
        _COMPOSITION_ROTATION = ["medium", "close_up", "over_shoulder", "silhouette", "low_angle", "medium", "wide", "close_up"]
        if shot_index >= 0:
            return _COMPOSITION_ROTATION[shot_index % len(_COMPOSITION_ROTATION)]
        
        # 兜底：按内容类型
        if content_type in ["military", "war", "space"]:
            return "wide"
        elif content_type in ["politics", "news"]:
            return "medium"
        return "medium"

    @classmethod
    def _select_lighting(cls, visual_tone: str) -> str:
        if visual_tone:
            if any(w in visual_tone for w in ["紧张", "危机", "冲突", "tense", "crisis"]):
                return "dramatic"
            elif any(w in visual_tone for w in ["希望", "胜利", "hope", "victory", "温暖"]):
                return "golden"
        return "natural"

    @classmethod
    def _select_style(cls, content_type: str) -> str:
        if content_type in ["military", "war"]:
            return "war"
        elif content_type in ["news"]:
            return "news"
        return "documentary"


def quick_generate_arv_prompt(dubbing_text: str, content_type: str = "general",
                             core_theme: str = "", visual_tone: str = "",
                             model_type: str = "sd15", user_styles: list = None) -> str:
    return ARVPromptTemplates.generate_prompt(dubbing_text, content_type, core_theme,
                                              visual_tone, model_type, user_styles)
