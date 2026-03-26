#!/usr/bin/env python3
"""
增强版内容识别模块
修复问题：
1. 国家/地点识别错误（如"厄立特里亚"被误识别为"俄罗斯"）
2. 上下文理解问题（如"那裡的普通老百姓"应关联到前面提到的朝鲜）
3. 内容类型分类优化
"""

import re
from typing import Dict, List, Tuple, Optional

# ==================== 国家/地区实体映射（完整版）====================
# 包含常见的中文别名、繁体字、误识别纠正

COUNTRY_MAPPING = {
    # 亚洲
    '中国': 'China, Chinese', '中華': 'China, Chinese', '中國': 'China, Chinese',
    '美国': 'United States, USA, American', '美國': 'United States, USA, American', '美': 'USA, American',
    '日本': 'Japan, Japanese', '日': 'Japan, Japanese',
    '韩国': 'South Korea, Korean', '韓國': 'South Korea, Korean', '南韩': 'South Korea, Korean', '南韓': 'South Korea, Korean',
    '朝鲜': 'North Korea, Korean', '北韩': 'North Korea, Korean', '北韓': 'North Korea, Korean', '朝鮮': 'North Korea, Korean',
    '伊朗': 'Iran, Iranian', '伊': 'Iran, Iranian',
    '以色列': 'Israel, Israeli', '以': 'Israel, Israeli',
    '俄罗斯': 'Russia, Russian', '俄羅斯': 'Russia, Russian', '俄': 'Russia, Russian',
    '沙特': 'Saudi Arabia, Saudi', '沙特阿拉伯': 'Saudi Arabia, Saudi',
    '阿联酋': 'UAE, United Arab Emirates', '阿聯酋': 'UAE, United Arab Emirates',
    '土耳其': 'Turkey, Turkish', '土': 'Turkey, Turkish',
    '印度': 'India, Indian', '印': 'India, Indian',
    '巴基斯坦': 'Pakistan, Pakistani', '巴': 'Pakistan, Pakistani',
    '阿富汗': 'Afghanistan, Afghan', '阿富汗': 'Afghanistan, Afghan',
    '伊拉克': 'Iraq, Iraqi', '伊': 'Iraq, Iraqi',  # 注意：伊朗和伊拉克都有"伊"，需要上下文区分
    '叙利亚': 'Syria, Syrian', '敘利亞': 'Syria, Syrian',
    '黎巴嫩': 'Lebanon, Lebanese',
    '约旦': 'Jordan, Jordanian', '約旦': 'Jordan, Jordanian',
    '埃及': 'Egypt, Egyptian', '埃': 'Egypt, Egyptian',
    '越南': 'Vietnam, Vietnamese', '越': 'Vietnam, Vietnamese',
    '泰国': 'Thailand, Thai', '泰': 'Thailand, Thai',
    '印尼': 'Indonesia, Indonesian', '印度尼西亚': 'Indonesia, Indonesian', '印度尼西亞': 'Indonesia, Indonesian',
    '马来西亚': 'Malaysia, Malaysian', '馬來西亞': 'Malaysia, Malaysian',
    '新加坡': 'Singapore, Singaporean',
    '菲律宾': 'Philippines, Filipino', '菲': 'Philippines, Filipino',
    '缅甸': 'Myanmar, Burmese', '緬甸': 'Myanmar, Burmese',
    '孟加拉': 'Bangladesh, Bangladeshi',
    
    # 欧洲
    '英国': 'UK, United Kingdom, British', '英國': 'UK, United Kingdom, British', '英': 'UK, British',
    '法国': 'France, French', '法國': 'France, French', '法': 'France, French',
    '德国': 'Germany, German', '德國': 'Germany, German', '德': 'Germany, German',
    '意大利': 'Italy, Italian', '義大利': 'Italy, Italian',
    '西班牙': 'Spain, Spanish', '西': 'Spain, Spanish',
    '荷兰': 'Netherlands, Dutch', '荷蘭': 'Netherlands, Dutch',
    '波兰': 'Poland, Polish', '波蘭': 'Poland, Polish',
    '乌克兰': 'Ukraine, Ukrainian', '烏克蘭': 'Ukraine, Ukrainian',
    '瑞典': 'Sweden, Swedish', '瑞士': 'Switzerland, Swiss',
    
    # 非洲 - 重点添加之前遗漏的国家
    '厄立特里亚': 'Eritrea, Eritrean', '厄利垂亞': 'Eritrea, Eritrean', '俄利特里亞': 'Eritrea, Eritrean',
    '厄立特': 'Eritrea, Eritrean',  # 常见简写/误写
    '埃塞俄比亚': 'Ethiopia, Ethiopian', '埃塞俄比亞': 'Ethiopia, Ethiopian', '衣索比亞': 'Ethiopia, Ethiopian',
    '索马里': 'Somalia, Somali', '索馬里': 'Somalia, Somali',
    '苏丹': 'Sudan, Sudanese', '蘇丹': 'Sudan, Sudanese',
    '南非': 'South Africa, South African',
    '尼日利亚': 'Nigeria, Nigerian', '奈及利亞': 'Nigeria, Nigerian',
    '肯尼亚': 'Kenya, Kenyan', '肯亞': 'Kenya, Kenyan',
    '摩洛哥': 'Morocco, Moroccan',
    '阿尔及利亚': 'Algeria, Algerian', '阿爾及利亞': 'Algeria, Algerian',
    '突尼斯': 'Tunisia, Tunisian',
    '利比亚': 'Libya, Libyan', '利比亞': 'Libya, Libyan',
    '刚果': 'Congo, Congolese', '剛果': 'Congo, Congolese',
    
    # 美洲
    '加拿大': 'Canada, Canadian',
    '墨西哥': 'Mexico, Mexican',
    '巴西': 'Brazil, Brazilian',
    '阿根廷': 'Argentina, Argentine',
    '委内瑞拉': 'Venezuela, Venezuelan', '委內瑞拉': 'Venezuela, Venezuelan',
    
    # 大洋洲
    '澳大利亚': 'Australia, Australian', '澳': 'Australia, Australian', '澳洲': 'Australia, Australian',
    '新西兰': 'New Zealand, NZ', '新西蘭': 'New Zealand, NZ',
}

# ==================== 地区/区域映射 ====================
REGION_MAPPING = {
    '中东': 'Middle East', '中東': 'Middle East',
    '欧洲': 'Europe, European', '歐洲': 'Europe, European',
    '亚洲': 'Asia, Asian', '亞洲': 'Asia, Asian',
    '非洲': 'Africa, African', '非': 'Africa, African',
    '美洲': 'Americas, American',
    '北美': 'North America',
    '南美': 'South America',
    '拉丁美洲': 'Latin America',
    '东南亚': 'Southeast Asia', '東南亞': 'Southeast Asia',
    '东亚': 'East Asia', '東亞': 'East Asia',
    '西亚': 'West Asia', '西亞': 'West Asia',
    '北非': 'North Africa',
    '撒哈拉以南': 'Sub-Saharan Africa',
    '波斯湾': 'Persian Gulf', '波斯灣': 'Persian Gulf',
    '红海': 'Red Sea', '紅海': 'Red Sea',
    '地中海': 'Mediterranean',
    '霍尔木兹海峡': 'Strait of Hormuz', '霍爾木茲海峽': 'Strait of Hormuz',
}

# ==================== 城市/地点映射 ====================
CITY_MAPPING = {
    # 伊朗城市
    '德黑兰': 'Tehran, Iran capital', '德黑蘭': 'Tehran, Iran capital',
    '伊斯法罕': 'Isfahan, Iran',
    '设拉子': 'Shiraz, Iran', '設拉子': 'Shiraz, Iran',
    
    # 朝鲜城市
    '平壤': 'Pyongyang, North Korea capital',
    
    # 中东城市
    '耶路撒冷': 'Jerusalem',
    '特拉维夫': 'Tel Aviv, Israel', '特拉維夫': 'Tel Aviv, Israel',
    '贝鲁特': 'Beirut, Lebanon', '貝魯特': 'Beirut, Lebanon',
    '大马士革': 'Damascus, Syria', '大馬士革': 'Damascus, Syria',
    '巴格达': 'Baghdad, Iraq', '巴格達': 'Baghdad, Iraq',
    '利雅得': 'Riyadh, Saudi Arabia',
    '迪拜': 'Dubai, UAE', '杜拜': 'Dubai, UAE',
    '多哈': 'Doha, Qatar',
    
    # 俄罗斯城市
    '莫斯科': 'Moscow, Russia capital',
    '圣彼得堡': 'Saint Petersburg, Russia', '聖彼得堡': 'Saint Petersburg, Russia',
    
    # 乌克兰城市
    '基辅': 'Kyiv, Ukraine capital', '基輔': 'Kyiv, Ukraine capital',
    
    # 美国城市
    '华盛顿': 'Washington DC, US capital', '華盛頓': 'Washington DC, US capital',
    '纽约': 'New York City, USA', '紐約': 'New York City, USA',
    '洛杉矶': 'Los Angeles, USA', '洛杉磯': 'Los Angeles, USA',
    '旧金山': 'San Francisco, USA', '舊金山': 'San Francisco, USA',
    '五角大楼': 'Pentagon, US Defense Department', '五角大樓': 'Pentagon, US Defense Department',
    
    # 中国城市
    '北京': 'Beijing, China capital',
    '上海': 'Shanghai, China',
    '香港': 'Hong Kong',
    '台北': 'Taipei, Taiwan', '臺北': 'Taipei, Taiwan',
}

# ==================== 组织/机构映射 ====================
ORGANIZATION_MAPPING = {
    # 军事组织
    '革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '伊朗革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '伊革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '美军': 'US military, American forces', '美軍': 'US military, American forces',
    '俄军': 'Russian military, Russian forces', '俄軍': 'Russian military, Russian forces',
    '以军': 'Israeli military, IDF', '以軍': 'Israeli military, IDF',
    '伊军': 'Iranian military', '伊軍': 'Iranian military',
    '朝军': 'North Korean military', '朝軍': 'North Korean military',
    
    # 国际组织
    '联合国': 'United Nations, UN', '聯合國': 'United Nations, UN',
    '安理会': 'UN Security Council', '安理會': 'UN Security Council',
    '北约': 'NATO, North Atlantic Treaty Organization', '北約': 'NATO',
    '欧盟': 'European Union, EU', '歐盟': 'European Union, EU',
    '欧佩克': 'OPEC', '歐佩克': 'OPEC',
    
    # 政府机构
    '国防部': 'Ministry of Defense, Pentagon', '國防部': 'Ministry of Defense, Pentagon',
    '外交部': 'Foreign Ministry', '外交部': 'Foreign Ministry',
    '白宫': 'White House, US President', '白宮': 'White House, US President',
    '克里姆林宫': 'Kremlin, Russian government', '克里姆林宮': 'Kremlin, Russian government',
}

# ==================== 军事/武器映射 ====================
MILITARY_MAPPING = {
    '导弹': 'missile, rocket', '導彈': 'missile, rocket',
    '弹道导弹': 'ballistic missile', '彈道導彈': 'ballistic missile',
    '巡航导弹': 'cruise missile', '巡航導彈': 'cruise missile',
    '无人机': 'drone, UAV', '無人機': 'drone, UAV',
    '战斗机': 'fighter jet, military aircraft', '戰鬥機': 'fighter jet, military aircraft',
    '轰炸机': 'bomber aircraft', '轟炸機': 'bomber aircraft',
    '航母': 'aircraft carrier', '航空母舰': 'aircraft carrier', '航空母艦': 'aircraft carrier',
    '军舰': 'warship, naval vessel', '軍艦': 'warship, naval vessel',
    '潜艇': 'submarine', '潛艇': 'submarine',
    '坦克': 'tank, armored vehicle',
    '防空': 'air defense, anti-aircraft', '防空': 'air defense, anti-aircraft',
    '雷达': 'radar', '雷達': 'radar',
    '核设施': 'nuclear facility', '核設施': 'nuclear facility',
    '核武器': 'nuclear weapon', '核武器': 'nuclear weapon',
}

# ==================== 上下文关联映射 ====================
# 用于处理"那裡的普通老百姓"这类需要上下文理解的文本
CONTEXT_ASSOCIATIONS = {
    # 当前面提到某个国家/地点，后面的"那里"应该关联到它
    '朝鲜': ['那里', '那裡', '当地', '當地', '本地', '这个国家', '這個國家', '老百姓', '人民', '民众', '民眾'],
    '伊朗': ['那里', '那裡', '当地', '當地', '本地', '这个国家', '這個國家', '老百姓', '人民', '民众', '民眾'],
    '俄罗斯': ['那里', '那裡', '当地', '當地', '本地', '这个国家', '這個國家', '老百姓', '人民', '民众', '民眾'],
    '以色列': ['那里', '那裡', '当地', '當地', '本地', '这个国家', '這個國家', '老百姓', '人民', '民众', '民眾'],
}

# ==================== 内容类型关键词映射 ====================
CONTENT_TYPE_KEYWORDS = {
    'military': {
        'keywords': ['战争', '戰爭', '军事', '軍事', '军队', '軍隊', '士兵', '武器', '导弹', '導彈', 
                    '飞机', '飛機', '战斗机', '戰鬥機', '轰炸', '轟炸', '打击', '打擊', '防空', '警报', '警報',
                    '冲突', '衝突', '战斗', '戰鬥', '作战', '作戰', '袭击', '襲擊', '攻击', '攻擊', '防御', '防禦',
                    '伤亡', '傷亡', '尸体', '屍體', '战略', '戰略', '战术', '戰術', '军事基地', '軍事基地',
                    '战区', '戰區', '前线', '前線', '后勤', '後勤', '装备', '裝備', '无人机', '無人機',
                    '伊朗', '美国', '以色列', '中东', '波斯湾', '霍尔木兹', '德黑兰', '美军', '以军', '伊军',
                    'IRGC', '核设施', '航母', '舰队', '水雷', '快艇', '指挥中心'],
        'visual_style': 'military documentary, war zone, combat environment, tactical setting',
    },
    'politics': {
        'keywords': ['政治', '政府', '国家', '國家', '总统', '總統', '领导人', '領導人', '外交', '国际', '國際',
                    '政策', '政权', '政權', '议会', '議會', '选举', '選舉', '党派', '黨派', '官员', '官員',
                    '制裁', '谈判', '談判', '协议', '協議', '条约', '條約', '声明', '聲明', '抗议', '抗議',
                    '游行', '遊行', '白宫', '白宮', '华盛顿', '華盛頓', '反战', '反戰', '纳税人', '納稅人',
                    '国际社会', '國際社會', '盟友', '中俄', '国际秩序', '國際秩序', '共识', '共識', '和解', '发展'],
        'visual_style': 'political scene, government building, diplomatic venue, official setting',
    },
    'space': {
        'keywords': ['太空', '宇宙', '星球', '行星', '恒星', '恆星', '卫星', '衛星', '轨道', '軌道', '引力',
                    '黑洞', '星云', '星雲', '水星', '金星', '地球', '火星', '木星', '土星', '天王星', '海王星',
                    '太阳系', '太陽系', '银河系', '銀河系', '天文单位', '公转', '公轉', '自转', '自轉',
                    '日心', '地心', '陨石', '隕石', '彗星', '小行星', '空间站', '宇航员', '宇航員'],
        'visual_style': 'cosmic scene, deep space, astronomical visualization, celestial bodies',
    },
    'science': {
        'keywords': ['科学', '科學', '研究', '实验', '實驗', '理论', '理論', '数据', '數據', '分析',
                    '发现', '發現', '技术', '技術', '原理', '规律', '規律', '科学家', '科學家', '实验室', '實驗室'],
        'visual_style': 'scientific environment, laboratory, research setting, technology',
    },
    'nature': {
        'keywords': ['自然', '环境', '環境', '生态', '生態', '气候', '氣候', '动物', '動物', '植物',
                    '地形', '地貌', '水文', '地质', '地質', '森林', '海洋', '河流', '山脉', '山脈'],
        'visual_style': 'natural landscape, outdoor scene, environment, wildlife',
    },
    'history': {
        'keywords': ['历史', '歷史', '古代', '文明', '文化', '传统', '傳統', '遗迹', '遺跡', '考古',
                    '文物', '朝代', '事件', '古代', '古典', '历史性', '歷史性'],
        'visual_style': 'historical setting, period scene, cultural heritage, classical',
    },
    'technology': {
        'keywords': ['科技', '技术', '技術', '发明', '發明', '创新', '創新', '人工智能', '计算机', '計算機',
                    '网络', '網絡', '数码', '數碼', '自动化', '自動化', '机器人', '機器人', 'AI', '互联网', '互聯網'],
        'visual_style': 'high-tech, futuristic, digital, innovation, technology',
    },
    'economy': {
        'keywords': ['经济', '經濟', '商业', '商業', '市场', '市場', '企业', '企業', '金融', '贸易', '貿易',
                    '管理', '营销', '營銷', '创业', '創業', '投资', '投資', '股票', '油价', '油價', '航运', '航運'],
        'visual_style': 'business environment, corporate setting, financial district, office scene',
    },
}


class EnhancedContentRecognizer:
    """增强版内容识别器"""
    
    def __init__(self):
        self.country_mapping = COUNTRY_MAPPING
        self.region_mapping = REGION_MAPPING
        self.city_mapping = CITY_MAPPING
        self.organization_mapping = ORGANIZATION_MAPPING
        self.military_mapping = MILITARY_MAPPING
        self.content_type_keywords = CONTENT_TYPE_KEYWORDS
        self.context_associations = CONTEXT_ASSOCIATIONS
        
        # 上下文历史记录（用于处理"那里"等代词）
        self.context_history = []
        self.last_country = None
        self.last_region = None
        self.last_city = None
    
    def update_context(self, text: str):
        """更新上下文，记录最近提到的国家/地区"""
        # 检测国家
        for cn_name, en_value in self.country_mapping.items():
            if cn_name in text:
                self.last_country = (cn_name, en_value)
                break
        
        # 检测地区
        for cn_name, en_value in self.region_mapping.items():
            if cn_name in text:
                self.last_region = (cn_name, en_value)
                break
        
        # 检测城市
        for cn_name, en_value in self.city_mapping.items():
            if cn_name in text:
                self.last_city = (cn_name, en_value)
                break
    
    def resolve_context_reference(self, text: str) -> Optional[Tuple[str, str]]:
        """解析上下文引用，如"那里"、"当地"等
        
        返回: (中文名称, 英文翻译) 或 None
        """
        # 检查是否包含引用词
        reference_words = ['那里', '那裡', '当地', '當地', '本地', '这个国家', '這個國家']
        
        has_reference = any(word in text for word in reference_words)
        
        if has_reference:
            # 返回最近的国家/地区
            if self.last_country:
                return self.last_country
            if self.last_region:
                return self.last_region
        
        return None
    
    def identify_entities(self, text: str) -> Dict[str, List[str]]:
        """识别文本中的实体
        
        Returns:
            {
                'countries': [...],
                'regions': [...],
                'cities': [...],
                'organizations': [...],
                'military': [...],
                'context_references': [...],  # 上下文引用
            }
        """
        entities = {
            'countries': [],
            'regions': [],
            'cities': [],
            'organizations': [],
            'military': [],
            'context_references': [],
        }
        
        # 先更新上下文
        self.update_context(text)
        
        # 解析上下文引用
        context_ref = self.resolve_context_reference(text)
        if context_ref:
            entities['context_references'].append(context_ref)
        
        # 识别国家（优先匹配长的名称）
        for cn_name, en_value in sorted(self.country_mapping.items(), key=lambda x: -len(x[0])):
            if cn_name in text:
                # 避免重复添加
                en_simple = en_value.split(',')[0]
                if en_simple not in [e.split(',')[0] for e in entities['countries']]:
                    entities['countries'].append(en_value)
        
        # 识别地区
        for cn_name, en_value in sorted(self.region_mapping.items(), key=lambda x: -len(x[0])):
            if cn_name in text:
                if en_value not in entities['regions']:
                    entities['regions'].append(en_value)
        
        # 识别城市
        for cn_name, en_value in sorted(self.city_mapping.items(), key=lambda x: -len(x[0])):
            if cn_name in text:
                if en_value not in entities['cities']:
                    entities['cities'].append(en_value)
        
        # 识别组织
        for cn_name, en_value in sorted(self.organization_mapping.items(), key=lambda x: -len(x[0])):
            if cn_name in text:
                if en_value not in entities['organizations']:
                    entities['organizations'].append(en_value)
        
        # 识别军事相关
        for cn_name, en_value in sorted(self.military_mapping.items(), key=lambda x: -len(x[0])):
            if cn_name in text:
                if en_value not in entities['military']:
                    entities['military'].append(en_value)
        
        return entities
    
    def detect_content_type(self, text: str) -> Tuple[str, str]:
        """检测内容类型
        
        Returns:
            (content_type, visual_style)
        """
        scores = {}
        
        for content_type, data in self.content_type_keywords.items():
            score = 0
            for keyword in data['keywords']:
                if keyword in text:
                    # 长关键词权重更高
                    score += len(keyword)
            scores[content_type] = score
        
        if scores:
            best_type = max(scores, key=scores.get)
            if scores[best_type] > 0:
                return best_type, self.content_type_keywords[best_type]['visual_style']
        
        return 'general', 'documentary photography, news footage style, realistic'
    
    def generate_prompt_entities(self, text: str) -> str:
        """生成提示词中的实体部分
        
        将识别到的实体转换为英文提示词
        """
        entities = self.identify_entities(text)
        
        prompt_parts = []
        
        # 添加上下文引用（最重要）
        if entities['context_references']:
            for cn_name, en_value in entities['context_references']:
                prompt_parts.append(f"in {en_value.split(',')[0]}")
        
        # 添加国家
        if entities['countries']:
            prompt_parts.extend(entities['countries'][:2])  # 最多2个国家
        
        # 添加组织
        if entities['organizations']:
            prompt_parts.extend(entities['organizations'][:2])
        
        # 添加军事相关
        if entities['military']:
            prompt_parts.extend(entities['military'][:3])
        
        # 添加城市
        if entities['cities']:
            prompt_parts.extend(entities['cities'][:2])
        
        # 添加地区
        if entities['regions']:
            prompt_parts.extend(entities['regions'][:1])
        
        return ', '.join(prompt_parts) if prompt_parts else ''
    
    def reset_context(self):
        """重置上下文（用于新的分镜任务）"""
        self.context_history = []
        self.last_country = None
        self.last_region = None
        self.last_city = None


# 创建全局实例
enhanced_recognizer = EnhancedContentRecognizer()


def get_enhanced_recognizer() -> EnhancedContentRecognizer:
    """获取全局内容识别器实例"""
    return enhanced_recognizer
