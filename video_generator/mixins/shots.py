"""Shot generation mixin - Whisper transcription, prompt generation, theme analysis."""
import os
import json
import time
import threading
import hashlib
import re
import gc
import warnings
from video_generator.mixins.logging import safe_print_exc
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox

from video_generator.config import Config, get_whisper_model_path
from video_generator.cache import prompt_cache, image_cache
from video_generator.ollama_client import (
    call_ollama_model,
    call_ollama_single,
    get_available_models,
    warmup_model,
    is_llm_available,
    check_ollama_available,
    try_start_ollama_service,
    check_model_gpu_status,
)
from video_generator.templates import PromptTemplates
from video_generator.app_state import set_ollama_available_global

try:
    from video_generator.enhanced_content_recognition import (
        get_enhanced_recognizer,
        EnhancedContentRecognizer,
        COUNTRY_MAPPING,
        REGION_MAPPING,
        CITY_MAPPING,
        ORGANIZATION_MAPPING,
        MILITARY_MAPPING,
        CONTENT_TYPE_KEYWORDS,
    )
    ENHANCED_RECOGNITION_AVAILABLE = True
except ImportError:
    ENHANCED_RECOGNITION_AVAILABLE = False

try:
    from video_generator.arv_optimization import get_arv_prompter
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False

try:
    from video_generator.prompts_arv import ARVPromptTemplates, quick_generate_arv_prompt
    ARV_PROMPTS_AVAILABLE = True
except ImportError:
    ARV_PROMPTS_AVAILABLE = False

_SIMPLIFIED_TO_TRADITIONAL = {
    '达': '達', '尔': '爾', '灵': '靈', '长': '長', '类': '類', '论': '論',
    '进': '進', '劳': '勞', '动': '動', '职': '職', '场': '場', '数': '數',
    '万': '萬', '亿': '億', '审': '審', '与': '與', '专': '專', '业': '業',
    '丛': '叢', '东': '東', '丝': '絲', '两': '兩', '严': '嚴', '丧': '喪',
    '争': '爭', '丰': '豐', '临': '臨', '为': '為', '丽': '麗', '举': '舉',
    '么': '麼', '义': '義', '乌': '烏', '乐': '樂', '乔': '喬', '习': '習',
    '乡': '鄉', '书': '書', '买': '買', '乱': '亂', '于': '於', '产': '產',
    '亲': '親', '仅': '僅', '从': '從', '众': '眾', '仑': '侖', '仓': '倉',
    '仪': '儀', '们': '們', '价': '價', '优': '優', '伙': '夥', '会': '會',
    '伟': '偉', '传': '傳', '伤': '傷', '伦': '倫', '伪': '偽', '余': '餘',
    '侠': '俠', '侦': '偵', '侧': '側', '侨': '僑', '俭': '儉', '侣': '侶',
    '储': '儲', '党': '黨', '兰': '蘭', '关': '關', '兴': '興', '养': '養',
    '兽': '獸', '内': '內', '册': '冊', '写': '寫', '军': '軍', '农': '農',
    '决': '決', '况': '況', '冲': '衝', '净': '淨', '凉': '涼', '减': '減',
    '几': '幾', '凭': '憑', '凯': '凱', '划': '劃', '刘': '劉', '则': '則',
    '刚': '剛', '创': '創', '删': '刪', '别': '別', '剑': '劍', '剧': '劇',
    '办': '辦', '务': '務', '劲': '勁', '势': '勢', '勋': '勳', '胜': '勝',
    '励': '勵', '劝': '勸', '汇': '匯', '区': '區', '协': '協', '却': '卻',
    '厅': '廳', '历': '歷', '厉': '厲', '压': '壓', '厌': '厭', '参': '參',
    '变': '變', '叠': '疊', '号': '號', '国': '國', '图': '圖', '圆': '圓',
    '圣': '聖', '坚': '堅', '坛': '壇', '墙': '牆', '奖': '獎', '妇': '婦',
    '妈': '媽', '婴': '嬰', '孙': '孫', '学': '學', '宁': '寧', '宝': '寶',
    '实': '實', '宽': '寬', '宾': '賓', '导': '導', '将': '將', '层': '層',
    '属': '屬', '岛': '島', '岁': '歲', '师': '師', '带': '帶', '帮': '幫',
    '广': '廣', '庆': '慶', '废': '廢', '库': '庫', '应': '應', '开': '開',
    '异': '異', '弃': '棄', '张': '張', '弹': '彈', '强': '強', '归': '歸',
    '当': '當', '忆': '憶', '态': '態', '愤': '憤', '戏': '戲', '战': '戰',
    '户': '戶', '执': '執', '扩': '擴', '扫': '掃', '扬': '揚', '扰': '擾',
    '担': '擔', '据': '據', '拥': '擁', '击': '擊', '挡': '擋', '挤': '擠',
    '挥': '揮', '摄': '攝', '摆': '擺', '摇': '搖', '摊': '攤', '敌': '敵',
    '斗': '鬥', '无': '無', '旧': '舊', '时': '時', '显': '顯', '暂': '暫',
    '术': '術', '机': '機', '杀': '殺', '权': '權', '条': '條', '来': '來',
    '杨': '楊', '极': '極', '枪': '槍', '柜': '櫃', '栋': '棟', '标': '標',
    '检': '檢', '楼': '樓', '横': '橫', '桥': '橋', '欢': '歡', '残': '殘',
    '气': '氣', '汉': '漢', '汤': '湯', '泽': '澤', '洁': '潔', '测': '測',
    '浓': '濃', '涛': '濤', '润': '潤', '涨': '漲', '温': '溫', '滨': '濱',
    '滩': '灘', '潜': '潛', '灭': '滅', '灯': '燈', '灾': '災', '炉': '爐',
    '点': '點', '烂': '爛', '炼': '煉', '热': '熱', '烧': '燒', '营': '營',
    '蓝': '藍', '质': '質', '赞': '贊', '跃': '躍', '践': '踐', '车': '車',
    '轨': '軌', '转': '轉', '轮': '輪', '软': '軟', '轰': '轟', '载': '載',
    '辅': '輔', '辆': '輛', '辉': '輝', '输': '輸', '辞': '辭', '边': '邊',
    '迁': '遷', '过': '過', '迈': '邁', '运': '運', '还': '還', '这': '這',
    '远': '遠', '违': '違', '连': '連', '迟': '遲', '选': '選', '递': '遞',
    '遗': '遺', '遥': '遙', '酿': '釀', '释': '釋', '针': '針', '钟': '鐘',
    '钢': '鋼', '铁': '鐵', '银': '銀', '链': '鏈', '销': '銷', '锁': '鎖',
    '锋': '鋒', '错': '錯', '录': '錄', '锦': '錦', '键': '鍵', '镇': '鎮',
    '门': '門', '闭': '閉', '间': '間', '闹': '鬧', '闻': '聞', '阔': '闊',
    '阳': '陽', '阴': '陰', '阵': '陣', '阶': '階', '际': '際', '陆': '陸',
    '陈': '陳', '险': '險', '隐': '隱', '难': '難', '双': '雙', '离': '離',
    '云': '雲', '电': '電', '雾': '霧', '静': '靜', '韦': '韋', '韧': '韌',
    '韩': '韓', '韵': '韻', '响': '響', '页': '頁', '顺': '順', '须': '須',
    '预': '預', '领': '領', '头': '頭', '频': '頻', '题': '題', '颜': '顏',
    '额': '額', '风': '風', '飘': '飄', '飞': '飛', '饭': '飯', '饮': '飲',
    '饰': '飾', '饱': '飽', '马': '馬', '驱': '驅', '驴': '驢', '驶': '駛',
    '驻': '駐', '驾': '駕', '骂': '罵', '骄': '驕', '验': '驗', '骑': '騎',
    '骗': '騙', '腾': '騰', '鱼': '魚', '鲜': '鮮', '鲸': '鯨', '鸟': '鳥',
    '鸡': '雞', '鸣': '鳴', '鸥': '鷗', '鸭': '鴨', '鹅': '鵝', '鹤': '鶴',
    '齐': '齊', '齿': '齒', '龙': '龍', '龟': '龜', '罗': '羅', '里': '裡',
    '纸': '紙', '杆': '桿', '稳': '穩', '矿': '礦', '脑': '腦', '给': '給',
    '装': '裝', '亚': '亞', '个': '個', '织': '織', '样': '樣', '觉': '覺',
    '维': '維', '现': '現', '状': '狀', '贵': '貴', '线': '線', '轻': '輕',
    '说': '說', '卖': '賣', '顾': '顧', '简': '簡', '华': '華', '顿': '頓',
    '债': '債', '邻': '鄰', '虽': '雖', '总': '總', '让': '讓', '处': '處',
    '种': '種', '御': '禦', '后': '後', '经': '經', '顶': '頂', '济': '濟',
    '盘': '盤', '许': '許', '赎': '贖', '赌': '賭', '筹': '籌', '码': '碼',
    '纽': '紐', '彻': '徹', '损': '損', '衬': '襯', '贴': '貼', '购': '購',
    '贷': '貸', '贸': '貿', '费': '費', '贺': '賀', '贼': '賊', '赔': '賠',
    '赚': '賺', '赛': '賽', '赶': '趕', '趋': '趨', '踪': '蹤', '轧': '軋',
    '轴': '軸', '较': '較', '辈': '輩', '辊': '輥', '辍': '輟', '辑': '輯',
    '辔': '轡', '辕': '轅', '辖': '轄', '邓': '鄧', '邮': '郵', '郑': '鄭',
    '钓': '釣', '铃': '鈴', '铅': '鉛', '铢': '銖', '铭': '銘', '铺': '鋪',
    '锏': '鐧', '闲': '閒', '闷': '悶', '闸': '閘', '阁': '閣', '阀': '閥',
    '阕': '闋', '阑': '闌', '阒': '闃', '阖': '闔', '阙': '闕', '陕': '陝',
    '隶': '隸', '雇': '僱', '雏': '雛', '麦': '麥', '麸': '麩', '麹': '麴',
    '黄': '黃', '龄': '齡', '龀': '齔', '龁': '齕', '龃': '齟', '龅': '齙',
    '龆': '齠', '龇': '齜', '龈': '齦', '龉': '齬', '龊': '齪', '龋': '齲',
    '龌': '齷', '龚': '龔', '龛': '龕', '游': '遊', '干': '幹', '系': '係',
    '发': '發', '复': '復', '制': '製', '板': '闆', '表': '錶', '困': '睏',
    '厂': '廠', '范': '範', '台': '臺', '准': '準', '确': '確', '朴': '樸',
    '筑': '築', '蜡': '蠟', '松': '鬆', '舍': '捨', '咸': '鹹', '岩': '巖',
    '谷': '穀', '征': '徵', '致': '緻', '出': '齣', '沈': '瀋', '拓': '搨',
    '挽': '輓', '搓': '撚', '拟': '擬', '毁': '毀', '涂': '塗', '泼': '潑',
}

def _is_traditional_conversion(old, new):
    if old == new:
        return True
    converted = ''.join(_SIMPLIFIED_TO_TRADITIONAL.get(c, c) for c in old)
    if converted == new:
        return True
    return False

# 补充 _SIMPLIFIED_TO_TRADITIONAL 中遗漏的常见繁简映射
_SIMPLIFIED_TO_TRADITIONAL.update({
    '对': '對', '单': '單', '忧': '憂', '舱': '艙', '钉': '釘',
    '冲': '沖', '择': '擇', '问': '問',
    '适': '適', '续': '續',
    '绕': '繞', '纲': '綱', '网': '網',
    '罚': '罰', '罢': '罷',
    '趋': '趨', '赶': '趕',
    '辩': '辯',
    '凑': '湊',
})

_TRADITIONAL_TO_SIMPLIFIED = {v: k for k, v in _SIMPLIFIED_TO_TRADITIONAL.items() if k != v}

# 尝试使用opencc进行更完整的繁简转换
_opencc_converter = None
_opencc_available = False
try:
    import opencc
    _opencc_converter = opencc.OpenCC('t2s')
    _opencc_available = True
except (ImportError, Exception):
    _opencc_available = False

def _ensure_simplified_chinese(text):
    """将繁体中文转换为简体中文
    
    优先使用opencc库（覆盖完整、准确），回退到手动映射字典。
    """
    if not text:
        return text
    if _opencc_available and _opencc_converter:
        try:
            return _opencc_converter.convert(text)
        except Exception:
            pass
    return ''.join(_TRADITIONAL_TO_SIMPLIFIED.get(c, c) for c in text)

_ENTITY_COUNTRY_MAPPING = {
    '伊朗': 'Iran, Iranian', '美国': 'USA, American', '美國': 'USA, American', '中国': 'China, Chinese', '中國': 'China, Chinese',
    '俄罗斯': 'Russia, Russian', '俄羅斯': 'Russia, Russian', '以色列': 'Israel, Israeli', '日本': 'Japan, Japanese',
    '英国': 'UK, British', '英國': 'UK, British', '法国': 'France, French', '法國': 'France, French', '德国': 'Germany, German', '德國': 'Germany, German',
    '朝鲜': 'North Korea, Korean', '朝鮮': 'North Korea, Korean', '北韩': 'North Korea, Korean', '北韓': 'North Korea, Korean',
    '韩国': 'South Korea, Korean', '韓國': 'South Korea, Korean', '南韩': 'South Korea, Korean', '南韓': 'South Korea, Korean',
    '乌克兰': 'Ukraine, Ukrainian', '烏克蘭': 'Ukraine, Ukrainian', '欧洲': 'Europe, European', '歐洲': 'Europe, European',
    '中东': 'Middle East', '中東': 'Middle East', '亚洲': 'Asia, Asian', '亞洲': 'Asia, Asian',
    '厄立特里亚': 'Eritrea, Eritrean', '厄利垂亞': 'Eritrea, Eritrean', '俄利特里亞': 'Eritrea, Eritrean',
    '埃塞俄比亚': 'Ethiopia, Ethiopian', '埃塞俄比亞': 'Ethiopia, Ethiopian', '衣索比亞': 'Ethiopia, Ethiopian',
    '索马里': 'Somalia, Somali', '索馬里': 'Somalia, Somali',
    '苏丹': 'Sudan, Sudanese', '蘇丹': 'Sudan, Sudanese',
    '南非': 'South Africa, South African',
    '埃及': 'Egypt, Egyptian',
}

_ENTITY_MILITARY_MAPPING = {
    '革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '革命衛隊': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '伊朗革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
    '美军': 'US military, American forces', '美軍': 'US military, American forces', '美军方': 'US military, Pentagon',
    '军队': 'military, armed forces, troops', '軍隊': 'military, armed forces, troops', '部队': 'troops, military unit', '部隊': 'troops, military unit',
    '海军': 'navy, naval forces', '海軍': 'navy, naval forces', '空军': 'air force, aviation', '空軍': 'air force, aviation',
    '陆军': 'army, ground forces', '陸軍': 'army, ground forces', '导弹': 'missile, rocket', '導彈': 'missile, rocket',
    '无人机': 'drone, UAV', '無人機': 'drone, UAV', '战斗机': 'fighter jet, aircraft', '戰鬥機': 'fighter jet, aircraft',
    '航母': 'aircraft carrier', '军舰': 'warship, naval vessel', '軍艦': 'warship, naval vessel',
    '武器': 'weapons, armaments', '军事': 'military, armed', '軍事': 'military, armed',
    '国防部': 'Ministry of Defense, Pentagon', '國防部': 'Ministry of Defense, Pentagon', '五角大楼': 'Pentagon, US Defense Department', '五角大樓': 'Pentagon, US Defense Department',
}

_ENTITY_POLITICAL_MAPPING = {
    '政府': 'government, officials', '总统': 'president, head of state', '總統': 'president, head of state',
    '总理': 'prime minister', '總理': 'prime minister', '首相': 'prime minister',
    '外交部': 'foreign ministry, diplomatic', '联合国': 'United Nations, UN', '聯合國': 'United Nations, UN',
    '安理会': 'UN Security Council', '安理會': 'UN Security Council', '北约': 'NATO, NATO alliance', '北約': 'NATO, NATO alliance',
    '欧盟': 'European Union, EU', '歐盟': 'European Union, EU', '国会': 'congress, parliament', '國會': 'congress, parliament',
    '议会': 'parliament, legislative', '議會': 'parliament, legislative', '政党': 'political party', '政黨': 'political party',
    '官员': 'officials, authorities', '官員': 'officials, authorities', '发言人': 'spokesperson, official spokesperson', '發言人': 'spokesperson, official spokesperson',
}

_ENTITY_EVENT_MAPPING = {
    '战争': 'war, warfare, conflict', '戰爭': 'war, warfare, conflict', '冲突': 'conflict, clash', '衝突': 'conflict, clash',
    '战斗': 'battle, combat, fighting', '戰鬥': 'battle, combat, fighting', '袭击': 'attack, strike, assault', '襲擊': 'attack, strike, assault',
    '爆炸': 'explosion, blast', '发射': 'launch', '發射': 'launch',
    '试射': 'test, missile test', '試射': 'test, missile test', '军演': 'military exercise, drill', '軍演': 'military exercise, drill',
    '谈判': 'negotiation, talks', '談判': 'negotiation, talks', '会议': 'meeting, conference', '會議': 'meeting, conference',
    '声明': 'statement, announcement', '聲明': 'statement, announcement', '宣布': 'announcement, declare',
    '签署': 'signing, agreement', '簽署': 'signing, agreement', '协议': 'agreement, deal, pact', '協議': 'agreement, deal, pact',
    '制裁': 'sanctions, embargo', '援助': 'aid, assistance',
}

_ENTITY_LOCATION_MAPPING = {
    '基地': 'base, military base', '机场': 'airport, air base', '機場': 'airport, air base',
    '港口': 'port, harbor, naval base', '城市': 'city, urban',
    '农村': 'rural, countryside', '農村': 'rural, countryside', '山区': 'mountain, mountainous', '山區': 'mountain, mountainous',
    '沙漠': 'desert', '海边': 'coastal, seaside', '海邊': 'coastal, seaside',
    '海峡': 'strait, waterway', '海峽': 'strait, waterway', '油田': 'oil field, oil facility',
    '核设施': 'nuclear facility', '核設施': 'nuclear facility', '工厂': 'factory, facility', '工廠': 'factory, facility',
    '大使馆': 'embassy', '大使館': 'embassy', '领事馆': 'consulate', '領事館': 'consulate',
}

_ENTITY_MEDIA_MAPPING = {
    '新闻': 'news, news report, breaking news', '新聞': 'news, news report, breaking news', '记者': 'journalist, reporter', '記者': 'journalist, reporter',
    '主持人': 'anchor, presenter', '直播': 'live broadcast, livestream',
    '报道': 'report, coverage', '報道': 'report, coverage', '采访': 'interview', '採訪': 'interview',
    '发布会': 'press conference', '發布會': 'press conference', '声明': 'official statement', '聲明': 'official statement',
}

_ENTITY_GENERIC_KEYWORDS = {
    '今天': 'today, current events, breaking news',
    '消息': 'news, information, report',
    '全球': 'global, worldwide, international',
    '牵动': 'impact, concern, attention', '牽動': 'impact, concern, attention',
    '最新': 'latest, recent, breaking',
    '关注': 'attention, focus, interest', '關注': 'attention, focus, interest',
    '热点': 'hot topic, trending, viral', '熱點': 'hot topic, trending, viral',
    '重大': 'major, significant, important',
    '紧急': 'urgent, emergency, breaking', '緊急': 'urgent, emergency, breaking',
    '刚刚': 'just happened, breaking, latest', '剛剛': 'just happened, breaking, latest',
    '最新消息': 'breaking news, latest update, recent development',
    '据报道': 'according to reports, sources say', '據報道': 'according to reports, sources say',
    '业内人士': 'industry sources, experts, insiders', '業內人士': 'industry sources, experts, insiders',
}

_ENTITY_ALL_MAPPINGS = [
    (_ENTITY_MILITARY_MAPPING, 'military'),
    (_ENTITY_POLITICAL_MAPPING, 'political'),
    (_ENTITY_EVENT_MAPPING, 'event'),
    (_ENTITY_LOCATION_MAPPING, 'location'),
    (_ENTITY_COUNTRY_MAPPING, 'country'),
    (_ENTITY_MEDIA_MAPPING, 'media'),
    (_ENTITY_GENERIC_KEYWORDS, 'generic'),
]

_TRANSLATION_MAPPING = {
    '人': 'person', '男人': 'man', '女人': 'woman', '老人': 'elderly person',
    '小孩': 'child', '年轻人': 'young person', '学生': 'student', '医生': 'doctor',
    '护士': 'nurse', '警察': 'police officer', '军人': 'soldier', '教师': 'teacher',
    '记者': 'journalist', '商人': 'businessman', '科学家': 'scientist',
    '工程师': 'engineer', '运动员': 'athlete', '演员': 'actor', '歌手': 'singer',
    '总统': 'president', '总理': 'prime minister', '部长': 'minister',
    '司令': 'commander', '长官': 'officer', '領導人': 'leader',
    '人群': 'crowd', '群众': 'people', '群眾': 'people',
    '總統': 'president', '總理': 'prime minister', '部長': 'minister',
    '長官': 'officer',
    '年輕人': 'young person', '學生': 'student', '醫生': 'doctor',
    '護士': 'nurse', '軍人': 'soldier', '教師': 'teacher',
    '科學家': 'scientist', '工程師': 'engineer', '運動員': 'athlete',
    '演員': 'actor', '歌手': 'singer',
    '城市': 'city', '城镇': 'town', '农村': 'countryside', '乡村': 'village',
    '街道': 'street', '道路': 'road', '商场': 'shopping mall', '餐厅': 'restaurant',
    '医院': 'hospital', '学校': 'school', '工厂': 'factory', '办公室': 'office',
    '图书馆': 'library', '公园': 'park', '海滩': 'beach', '山': 'mountain',
    '河': 'river', '湖': 'lake', '海': 'sea', '森林': 'forest',
    '草原': 'grassland', '沙漠': 'desert', '房间': 'room', '楼': 'building',
    '机场': 'airport', '车站': 'station', '码头': 'dock',
    '城鎮': 'town', '農村': 'countryside', '鄉村': 'village',
    '商場': 'shopping mall', '餐廳': 'restaurant',
    '醫院': 'hospital', '學校': 'school', '工廠': 'factory', '辦公室': 'office',
    '圖書館': 'library', '公園': 'park', '海灘': 'beach',
    '房間': 'room', '樓': 'building',
    '機場': 'airport', '車站': 'station', '碼頭': 'dock',
    '伊朗': 'Iran', '美国': 'United States', '中国': 'China', '俄罗斯': 'Russia',
    '欧洲': 'Europe', '亚洲': 'Asia', '中东': 'Middle East',
    '美國': 'United States', '中國': 'China', '俄羅斯': 'Russia',
    '歐洲': 'Europe', '亞洲': 'Asia', '中東': 'Middle East',
    '车': 'car', '汽车': 'car', '火车': 'train', '飞机': 'airplane', '船': 'ship',
    '車': 'car', '汽車': 'car', '火車': 'train', '飛機': 'airplane',
    '手机': 'mobile phone', '电脑': 'computer', '电视': 'television',
    '书': 'book', '文件': 'document', '照片': 'photo', '图片': 'image',
    '手機': 'mobile phone', '電腦': 'computer', '電視': 'television',
    '書': 'book', '圖片': 'image',
    '走': 'walking', '跑': 'running', '跳': 'jumping', '飞': 'flying',
    '坐': 'sitting', '躺': 'lying', '站': 'standing', '看': 'looking',
    '听': 'listening', '说': 'speaking', '笑': 'smiling', '哭': 'crying',
    '唱': 'singing', '跳舞': 'dancing', '吃': 'eating', '喝': 'drinking',
    '工作': 'working', '学习': 'studying', '开车': 'driving',
    '打电话': 'making phone call', '拍照': 'taking photo',
    '采访': 'interviewing', '演讲': 'giving speech', '表演': 'performing',
    '比赛': 'competing', '战斗': 'fighting', '战争': 'war',
    '飛': 'flying',
    '聽': 'listening', '說': 'speaking',
    '學習': 'studying', '開車': 'driving',
    '打電話': 'making phone call',
    '採訪': 'interviewing', '演講': 'giving speech',
    '比賽': 'competing', '戰鬥': 'fighting', '戰爭': 'war',
    '白天': 'daytime', '夜晚': 'night', '早晨': 'morning', '黄昏': 'dusk',
    '黃昏': 'dusk',
    '晴天': 'sunny', '雨天': 'rainy', '雪天': 'snowy', '阴天': 'cloudy',
    '陰天': 'cloudy',
    '紧张': 'tense', '危机': 'crisis', '危险': 'dangerous',
    '平静': 'peaceful', '安静': 'quiet', '宁静': 'serene',
    '高兴': 'happy', '快乐': 'joyful', '开心': 'cheerful',
    '悲伤': 'sad', '难过': 'sad', '伤心': 'heartbreaking',
    '愤怒': 'angry', '生气': 'furious', '害怕': 'scared', '恐惧': 'fearful',
    '緊張': 'tense', '危機': 'crisis', '危險': 'dangerous',
    '平靜': 'peaceful', '安靜': 'quiet', '寧靜': 'serene',
    '高興': 'happy', '快樂': 'joyful', '開心': 'cheerful',
    '悲傷': 'sad', '難過': 'sad', '傷心': 'heartbreaking',
    '憤怒': 'angry', '生氣': 'furious', '害怕': 'scared', '恐懼': 'fearful',
    '导弹': 'missile',
    '武器': 'weapon', '坦克': 'tank', '军舰': 'warship',
    '導彈': 'missile', '軍艦': 'warship',
    '火': 'fire', '炸弹': 'bomb', '定时炸弹': 'time bomb',
    '地缘': 'geopolitical', '棋盘': 'chessboard',
    '投降': 'surrender', '谈判': 'negotiation',
    '炸彈': 'bomb', '定時炸彈': 'time bomb',
    '地緣': 'geopolitical', '棋盤': 'chessboard',
    '談判': 'negotiation',
    '马杜罗': 'President Maduro', '普京': 'President Putin',
    '拜登': 'President Biden', '特朗普': 'Donald Trump',
    '习近平': 'President Xi', '泽连斯基': 'President Zelensky',
    '内塔尼亚胡': 'Prime Minister Netanyahu',
    '金正恩': 'Supreme Leader Kim Jong-un',
    '委内瑞拉': 'Venezuela', '委国': 'Venezuela',
    '加拉加斯': 'Caracas', '乌克兰': 'Ukraine',
    '以色列': 'Israel', '巴勒斯坦': 'Palestine',
    '朝鲜': 'North Korea', '韩国': 'South Korea',
    '日本': 'Japan', '印度': 'India',
    '巴西': 'Brazil', '哥伦比亚': 'Colombia',
    '古巴': 'Cuba', '阿根廷': 'Argentina',
    '沙特': 'Saudi Arabia', '伊朗': 'Iran',
    '伊拉克': 'Iraq', '叙利亚': 'Syria',
    '安理会': 'UN Security Council', '海牙': 'The Hague',
    '否决权': 'veto power', '制裁': 'sanctions',
    '石油': 'oil, petroleum', '矿产': 'mineral resources',
    '油价': 'oil price', '能源': 'energy',
    '军方': 'military', '军心': 'military morale',
    '武装': 'armed forces', '枪杆': 'military power',
    '权力': 'power, authority', '政权': 'regime',
    '反对派': 'opposition', '选票': 'ballot, voting',
    '合法性': 'legitimacy', '崩盘': 'collapse',
    '难民': 'refugee', '流亡': 'exile',
    '审判': 'trial', '司法': 'judiciary',
    # 经济/金融/就业
    '经济': 'economy', '金融': 'finance', '股票': 'stock market',
    '投资': 'investment', '杠杆': 'leverage', '资金': 'capital, funds',
    '资金链': 'capital chain', '现金流': 'cash flow',
    '崩盘': 'market crash', '通胀': 'inflation',
    '裁员': 'layoff, job cuts', '就业': 'employment', '失业': 'unemployment',
    '工资': 'wage, salary', '存款': 'savings, deposit',
    '房贷': 'mortgage', '消费': 'consumption', '收入': 'income',
    '退休': 'retirement', '养老': 'elderly care, pension',
    '储蓄': 'savings', '保险': 'insurance',
    '柴米油盐': 'daily necessities', '物价': 'commodity prices',
    '岗位': 'job position', '替代': 'replacement, displacement',
    '自动化': 'automation', '算法': 'algorithm',
    # AI/科技
    '人工智能': 'artificial intelligence', '芯片': 'microchip',
    '数字化': 'digitalization', '编程': 'programming',
    '翻译': 'translation', '设计': 'design',
    '机器人': 'robot', '互联网': 'internet',
    # 情绪/基调补充
    '冷静': 'calm, composed', '坚定': 'firm, resolute',
    '审慎': 'prudent, cautious', '务实': 'pragmatic',
    '理性': 'rational', '思辨': 'contemplative',
    '贪婪': 'greedy', '算计': 'calculating',
    '危急': 'critical, dire', '动荡': 'turbulent',
    '阴沉': 'gloomy', '沉闷': 'dull, oppressive',
    '严肃': 'serious, solemn', '紧张': 'tense, intense', '危急': 'critical, urgent', '贪婪': 'greedy, avaricious', '压抑': 'oppressive, stifling', '绝望': 'desperate, hopeless', '阴沉': 'gloomy, sinister', '动荡': 'turbulent, volatile', '悲凉': 'desolate, sorrowful', '算计': 'calculating, scheming', '沉闷': 'dull, stifling', '思辨': 'contemplative, thoughtful', '激昂': 'passionate, stirring',
    '紧张, 危急': 'critical, urgent', '紧张, 贪婪': 'greedy, intense', '紧张, 压抑': 'oppressive, stifling', '紧张, 绝望': 'desperate, hopeless', '紧张, 阴沉': 'gloomy, sinister', '紧张, 动荡': 'turbulent, volatile', '紧张, 悲凉': 'desolate, sorrowful', '紧张, 算计': 'calculating, scheming', '紧张, 沉闷': 'dull, stifling', '紧张, 思辨': 'contemplative, thoughtful',
    '严肃, 冷峻': 'stern, austere', '严肃, 庄重': 'solemn, dignified', '严肃, 审慎': 'prudent, measured', '严肃, 沉思': 'pensive, reflective', '严肃, 凛然': 'grave, formidable',
    '悲壮, 崇高': 'tragic, heroic', '悲壮, 无助': 'helpless, devastated', '悲壮, 凄凉': 'bleak, desolate', '悲壮, 壮烈': 'heroic, valiant',
    '激昂, 自豪': 'proud, triumphant', '激昂, 热血': 'fervent, passionate', '激昂, 振奋': 'inspiring, uplifting', '激昂, 雄壮': 'majestic, grand',
    '温馨, 柔和': 'warm, tender', '温馨, 感动': 'touching, heartfelt', '温馨, 喜悦': 'joyful, blissful', '温馨, 宁静': 'serene, peaceful',
    '沉重, 悲痛': 'grief-stricken, mournful', '沉重, 压抑': 'heavy, oppressive', '沉重, 无奈': 'helpless, resigned', '沉重, 愧疚': 'remorseful, guilty',
    '温馨': 'warm, tender', '轻松': 'relaxed, lighthearted', '悲壮': 'tragic, heroic',
    '沉重': 'heavy, somber', '振奋': 'inspiring, uplifting', '冷静': 'calm, composed',
    '焦虑': 'anxious, worried', '绝望': 'desperate, hopeless', '坚定': 'resolute, determined',
    '讽刺': 'ironic, satirical', '震撼': 'shocking, impactful', '忧郁': 'melancholic, gloomy',
    '激愤': 'indignant, outraged', '沉稳': 'steady, composed', '压抑': 'oppressive, stifling',
    '肃穆': 'solemn, reverent', '凝重': 'grave, dignified', '犀利': 'sharp, incisive',
    '嚴肅': 'serious, solemn', '緊張': 'tense, intense', '危急': 'critical, urgent', '貪婪': 'greedy, avaricious', '壓抑': 'oppressive, stifling', '絕望': 'desperate, hopeless', '陰沉': 'gloomy, sinister', '動蕩': 'turbulent, volatile', '悲涼': 'desolate, sorrowful', '算計': 'calculating, scheming', '沉悶': 'dull, stifling', '思辨': 'contemplative, thoughtful', '激昂': 'passionate, stirring',
    '緊張, 危急': 'critical, urgent', '緊張, 貪婪': 'greedy, intense', '緊張, 壓抑': 'oppressive, stifling', '緊張, 絕望': 'desperate, hopeless', '緊張, 陰沉': 'gloomy, sinister', '緊張, 動蕩': 'turbulent, volatile', '緊張, 悲涼': 'desolate, sorrowful', '緊張, 算計': 'calculating, scheming', '緊張, 沉悶': 'dull, stifling', '緊張, 思辨': 'contemplative, thoughtful',
    '溫馨': 'warm, tender', '輕鬆': 'relaxed, lighthearted', '冷靜': 'calm, composed',
    '肅穆': 'solemn, reverent', '凝重': 'grave, dignified',
    '赌': 'gambling', '筹码': 'bargaining chip',
    '防线': 'defense line', '压舱石': 'ballast',
    '后路': 'retreat route', '退路': 'way out',
    '金山': 'gold mountain, wealth', '肥差': 'lucrative post',
    '食品': 'food supplies', '底层': 'grassroots, bottom class',
    # 通用生活/日常领域（确保任何主题都有基础翻译覆盖）
    '厨房': 'kitchen', '食材': 'ingredients', '烹饪': 'cooking',
    '菜': 'dish, cuisine', '肉': 'meat', '蔬菜': 'vegetables',
    '水果': 'fruit', '米饭': 'rice', '面条': 'noodles',
    '汤': 'soup', '调料': 'seasoning', '刀': 'knife',
    '锅': 'pot, pan', '碗': 'bowl', '盘子': 'plate',
    '烤箱': 'oven', '冰箱': 'refrigerator',
    # 旅游/风光
    '湖泊': 'lake', '瀑布': 'waterfall', '秋色': 'autumn colors',
    '山峰': 'mountain peak', '峡谷': 'canyon, gorge',
    '海滩': 'beach', '岛屿': 'island', '日出': 'sunrise',
    '日落': 'sunset', '云海': 'sea of clouds', '雪景': 'snowscape',
    '花海': 'flower field', '草原': 'grassland, prairie',
    '古镇': 'ancient town', '寺庙': 'temple', '教堂': 'church',
    '城堡': 'castle', '宫殿': 'palace',
    # 情感/生活
    '温馨': 'warm, cozy', '轻松': 'relaxed, lighthearted',
    '浪漫': 'romantic', '幸福': 'happy, blissful',
    '孤独': 'lonely, solitary', '思念': 'missing, longing',
    '回忆': 'memory, reminiscence', '成长': 'growth, coming of age',
    '奋斗': 'struggle, striving', '梦想': 'dream, aspiration',
    '家庭': 'family', '朋友': 'friend', '爱情': 'love',
    '孩子': 'child', '母亲': 'mother', '父亲': 'father',
    # 教育/知识
    '课堂': 'classroom', '考试': 'examination', '毕业': 'graduation',
    '书籍': 'books', '知识': 'knowledge', '智慧': 'wisdom',
    # 健康/运动
    '跑步': 'running', '游泳': 'swimming', '瑜伽': 'yoga',
    '健身': 'fitness', '健康': 'health',
    # 自然/环境
    '雨': 'rain', '雪': 'snow', '风': 'wind',
    '雷': 'thunder', '彩虹': 'rainbow', '雾': 'fog, mist',
    '星空': 'starry sky', '月亮': 'moon', '阳光': 'sunlight',
    '树': 'tree', '花': 'flower', '草': 'grass',
    '河': 'river', '溪': 'stream', '泉': 'spring',
}

_COMMON_ASR_ERROR_DICT = {
    '委内日拉': '委内瑞拉', '委内日瑞拉': '委内瑞拉', '委内瑞士': '委内瑞拉', '委内瑞典': '委内瑞拉',
    '送动': '松动', '宋动': '松动',
    '高枕无优': '高枕无忧',
    '战车尚': '战车上',
    '否决劝': '否决权', '否决全': '否决权',
    '压仓石': '压舱石',
    '走刚丝': '走钢丝', '走港丝': '走钢丝',
    '串息': '喘息',
    '干遇': '干预',
    '前少': '前哨',
    '博一牌': '博弈牌',
    '松洞': '松动',
    '憲責': '宪责',
    '護著': '护着', '攥著': '攥着', '握著': '握着',
    '趁著': '趁着', '等著': '等着', '看著': '看着', '走著': '走着', '拿著': '拿着', '站著': '站着',
    '震盪': '震荡',
    '默認': '默认',
    '巴叙利亚': '西莉亚', '西利亚': '西莉亚',
    '俄军斯': '俄罗斯',
    '哥利比亚': '哥伦比亚',
    '孟加拉加斯': '加拉加斯',
    '海法': '海牙',
    '約旦': '一旦',
    '左歐盟': '左翼盟友', '左欧盟友': '左翼盟友',
    '防空性': '防守性',
    '司法国': '司法方面', '司方面': '司法方面', '合法国': '合法性',
    '底瑞': '底层',
    '以军舰': '军队', '塞以军': '塞给军队',
    '朝军舰': '军队', '塞朝军舰': '塞给军队', '压朝军舰': '压在军队',
    '朝军舰高层': '军队高层', '朝军舰动摇': '军队动摇',
    '朝军舰觉得': '军队觉得', '朝军舰的': '军队的',
    '只朝军舰': '只要军队',
    '乡里': '想来',
    '退倒': '退',
    '好赌': '而赌',
    '南非常': '就非常',
    '防空间': '的空间',
    '核武器派': '核武和派',
    '外号第一战斗机': '外号第一夫人',
    '支立': '织起',
    '压以军': '压在军',
    '塞以': '塞给',
    '压以': '压在',
    '海泰国际': '海牙国际', '泰国际': '在国际', '好泰': '好在',
    '海泰': '海牙',
    '法国的审判': '法庭的审判',
    '法国石油': '设法让石油',
    '想办法国': '想办法让',
    '去巴西方': '去换西方',
    '拉美军国': '拉美军事大国', '拉美军一根': '拉美军事一根',
    '华好的': '最好的',
    '只以军': '只要军队',
    '塞以军舰': '塞给军队',
    '压以军舰': '压在军队',
    '以军舰的': '军队的',
    '以军舰觉得': '军队觉得',
    '以军舰高层': '军队高层',
    '以军舰动摇': '军队动摇',
    '法国政党': '方面政党',
    '熬日本': '熬日子',
    '的日本也': '的日子也',
    '变成了异常': '变成了一种病',
    '海中国际': '海牙国际',
    '好中国际': '好在国际',
    '眼中国好': '眼中最好',
    '约旦失去': '一旦失去',
    '北韩有着': '北约有着',
    '两个泰国': '两个大国',
    # 日常/经济/就业常见ASR错误
    '柴米油眼': '柴米油盐',
    '资金炼': '资金链',
    '存购': '存够',
    '行一行': '心一横',
    '报复梦': '暴富梦',
    '内联储': '美联储',
    '联储': '联储',
    '加杠': '加杠杆',
    '去杠': '去杠杆',
    '现壮': '现状',
    '保住现': '保持现',
    '稳住现': '稳住现状',
    '就也': '就业',
    '岗位被': '岗位被',
    '替代岗': '替代岗位',
    '裁圆': '裁员',
    '失也': '失业',
    '工姿': '工资',
    '存坎': '存款',
    '房贷压': '房贷压力',
    '消费降': '消费降级',
    '收入减': '收入减少',
    '退修': '退休',
    '养劳': '养老',
    '储需': '储蓄',
    '保险杠': '保险杠',
    '保显': '保险',
    '柴米油': '柴米油盐',
    '油盐酱': '油盐酱醋',
    '暴复梦': '暴富梦',
    '报富梦': '暴富梦',
    '金炼断了': '资金链断了',
    '资金炼断了': '资金链断了',
}

def _levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]

def _auto_correct_asr(text, known_entities):
    """基于已知实体的编辑距离ASR纠错
    
    改进：支持2字实体纠错（如"经济"、"就业"），
    但对2字实体要求更严格的匹配（编辑距离必须为1且首字相同），
    避免误纠错。
    """
    if not text or not known_entities:
        return text
    
    # 分离2字实体和3字以上实体
    short_entities = {e for e in known_entities if len(e) == 2}
    long_entities = {e for e in known_entities if len(e) >= 3}
    
    corrected = text
    
    # 先处理长实体（3字以上），逻辑不变
    if long_entities:
        entity_lens = set(len(e) for e in long_entities)
        for elen in sorted(entity_lens, reverse=True):
            for i in range(len(text) - elen + 1):
                word = text[i:i+elen]
                if not re.match(r'^[\u4e00-\u9fff]+$', word):
                    continue
                if word in long_entities:
                    continue
                for entity in long_entities:
                    if len(entity) != elen:
                        continue
                    dist = _levenshtein_distance(word, entity)
                    if len(entity) <= 3:
                        max_dist = 1
                    elif len(entity) <= 5:
                        max_dist = 1
                    else:
                        max_dist = 2
                    if 0 < dist <= max_dist:
                        corrected = corrected.replace(word, entity)
                        break
    
    # 处理2字实体：要求首字相同且编辑距离为1（同音/近音替换）
    if short_entities:
        for i in range(len(corrected) - 1):
            word = corrected[i:i+2]
            if not re.match(r'^[\u4e00-\u9fff]{2}$', word):
                continue
            if word in short_entities:
                continue
            for entity in short_entities:
                if word[0] != entity[0]:
                    continue  # 首字必须相同
                dist = _levenshtein_distance(word, entity)
                if dist == 1:
                    corrected = corrected[:i] + entity + corrected[i+2:]
                    break
    
    return corrected

def _fix_whisper_repeated_chars(text):
    """修复Whisper语音识别产生的重复字错误
    
    常见模式：最后一个字被重复2-3次
    例如："關係係係" → "關係", "的的了" → "的"
    """
    if not text:
        return text
    text = re.sub(r'(.)\1{2,}', r'\1', text)
    text = re.sub(r'(.{2})\1{1,}', r'\1', text)
    return text

class ShotsMixin:
    def _get_current_model(self):
        return (self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else None) or "gemma3:4b"

    def generate_style_description(self, style):
        """使用Ollama模型生成详细的风格描述"""
        model = self._get_current_model()
        cache_key = f"style_{style}_{model}"
        cached_description = self.cache_get('prompts', cache_key)
        if cached_description:
            return cached_description
        
        # 预定义的风格关键词（直接返回，不调用大模型）
        predefined_styles = {
            "电影感": "cinematic lighting, film grain, dramatic shadows, movie scene, 4K film quality, anamorphic lens flare, depth of field",
            "纪录片风": "documentary photography, natural lighting, candid shot, photojournalism, raw and authentic, unposed",
            "赛博朋克": "cyberpunk, neon lights, futuristic city, holographic displays, dark atmosphere, blue and pink lighting, high tech",
            "写实摄影": "photorealistic, real photography, natural lighting, high detail, sharp focus, 8K resolution, professional camera",
            "皮克斯": "Pixar style, 3D animation, vibrant colors, soft lighting, cartoon render, cute characters, smooth textures",
            "达芬奇": "Leonardo da Vinci style, Renaissance painting, classical art, sfumato technique, warm earth tones, portrait masterpiece",
            "油画": "oil painting, brush strokes, classical art, textured canvas, rich colors, artistic masterpiece",
            "多巴胺": "dopamine style, bright vibrant colors, joyful, energetic, saturated colors, happy atmosphere, colorful",
            "黑白线条": "black and white line art, ink drawing, minimal, monochrome, sketch style, clean lines, high contrast",
            "吉卜力": "Studio Ghibli style, anime, hand-drawn animation, soft watercolor backgrounds, Miyazaki aesthetic, dreamy atmosphere",
            "梵高": "Van Gogh style, impressionism, swirling brushstrokes, vivid colors, Starry Night inspired, post-impressionist",
            "日式动漫": "Japanese anime style, manga art, cel shading, big eyes, vibrant colors, anime aesthetic",
            "水彩": "watercolor painting, soft edges, flowing colors, artistic, delicate brushstrokes, pastel tones, paper texture"
        }
        
        # 如果是预定义风格，直接返回
        if style in predefined_styles:
            self.cache_set('prompts', cache_key, predefined_styles[style])
            return predefined_styles[style]
        
        # 非预定义风格，调用大模型生成
        try:
            # 精确的提示词，要求只输出关键词
            user_message = f"""为AI绘图风格'{style}'生成英文提示词关键词。

规则：
- 只输出英文关键词，逗号分隔
- 5-15个关键词
- 不要解释、不要开场白、不要格式

输出："""
            
            result_text, _ = call_ollama_single(
                model=model,
                system_prompt="You are an AI art style keyword generator. Output only English keywords separated by commas.",
                user_prompt=user_message,
                log_callback=self.log,
                llm_config=getattr(self, 'current_llm_config', None),
                timeout=Config.API_TIMEOUT_LLM_PROMPT,
                cancel_check=lambda: not self.task_running
            )
            
            if result_text:
                raw_output = result_text.strip()
            else:
                raise Exception("Ollama调用失败")
            
            # 清洗输出，移除开场白和解释
            cleaned = self._clean_style_output(raw_output)
            
            # 缓存结果
            self.cache_set('prompts', cache_key, cleaned)
            
            return cleaned
        except Exception as e:
            self._log_exception("⚠️ 风格描述生成失败", e)
            # 返回一个默认风格
            return "professional photography, high quality, detailed"
    

    def analyze_content_type(self, sentence):
        """分析内容类型 - 增强版，使用增强版内容识别模块"""
        # 优先使用增强版识别器
        if ENHANCED_RECOGNITION_AVAILABLE:
            try:
                recognizer = get_enhanced_recognizer()
                content_type, visual_style = recognizer.detect_content_type(sentence)
                return content_type
            except Exception as e:
                self._log_exception("⚠️ 增强版识别失败，使用内置识别", e)
        
        # 回退到内置识别逻辑
        # 内容类型关键词及其权重
        content_types = {
            "military": {
                "keywords": ["战争", "戰爭", "军事", "軍事", "军队", "軍隊", "士兵", "武器", "导弹", "導彈",
                            "飞机", "飛機", "战斗机", "戰鬥機", "轰炸", "轟炸", "打击", "打擊", "防空", "警报", "警報",
                            "冲突", "衝突", "战斗", "戰鬥", "作战", "作戰", "袭击", "襲擊", "攻击", "攻擊", "防御", "防禦",
                            "伤亡", "傷亡", "尸体", "屍體", "战略", "戰略", "战术", "戰術", "军事基地", "軍事基地",
                            "战区", "戰區", "前线", "前線", "后勤", "後勤", "装备", "裝備", "无人机", "無人機",
                            # 添加国家和地缘政治相关词汇
                            "伊朗", "美国", "美國", "以色列", "中东", "中東", "波斯湾", "波斯灣", "霍尔木兹", "霍爾木茲", "德黑兰", "德黑蘭",
                            "美军", "美軍", "以军", "以軍", "伊军", "伊軍", "伊斯兰", "伊斯蘭", "革命卫队", "革命衛隊", "IRGC", "核设施", "核設施",
                            # 添加作战相关词汇
                            "无人机", "無人機", "空袭", "空襲", "地面战", "地面戰", "海军", "海軍", "空军", "空軍", "陆军", "陸軍", "航母", "舰队", "艦隊",
                            "水雷", "快艇", "雷达", "雷達", "指挥中心", "指揮中心", "核研发", "核研發", "加固建筑", "加固建築",
                            # 添加战争影响词汇
                            "油价", "油價", "航运", "航運", "保险", "保險", "保费", "保費", "断网", "斷網", "断电", "斷電", "废墟", "廢墟", "烟尘", "煙塵",
                            # 添加局势相关词汇（用于上下文理解）
                            "局势", "局勢", "战局", "戰局", "形势", "形勢", "格局", "态势", "態勢", "局面",
                            # 添加抵抗、战斗相关词汇
                            "抵抗", "反抗", "抗战", "抗戰", "战事", "戰事", "战况", "戰況",
                            # 添加力量、实力相关词汇
                            "实力", "實力", "力量", "战力", "戰力", "战斗力", "戰鬥力", "武装", "武裝", "部队", "部隊",
                            # 添加时间、变化相关词汇
                            "期间", "時期", "时期", "階段", "阶段", "过程", "過程", "变化", "變化", "转变", "轉變", "发展", "發展"],
                "weight": 1.0
            },
            "politics": {
                "keywords": ["政治", "政府", "国家", "國家", "总统", "總統", "领导人", "領導人", "外交", "国际", "國際", "政策", "政权", "政權", "议会", "議會",
                            "选举", "選舉", "党派", "黨派", "官员", "官員", "制裁", "谈判", "談判", "协议", "協議", "条约", "條約", "声明", "聲明", "抗议", "抗議", "游行", "遊行",
                            # 添加更多政治相关词汇
                            "白宫", "白宮", "华盛顿", "華盛頓", "反战", "反戰", "纳税人", "納稅人", "国际社会", "國際社會", "盟友", "中俄", "谈判", "談判",
                            "国际秩序", "國際秩序", "共识", "共識", "和解", "发展", "發展", "历史", "歷史",
                            # 添加局势相关词汇
                            "局势", "局勢", "形势", "形勢", "格局", "态势", "態勢", "局面", "变动", "變動", "更迭", "变化", "變化"],
                "weight": 0.95
            },
            "space": {
                "keywords": ["太空", "宇宙", "星球", "行星", "恒星", "恆星", "卫星", "衛星", "轨道", "軌道", "引力",
                            "黑洞", "星云", "星雲", "水星", "金星", "地球", "火星", "木星", "土星", "天王星", "海王星", 
                            "太阳系", "太陽系", "银河系", "銀河系", "天文单位", "公转", "公轉", "自转", "自轉", 
                            "日心", "地心", "陨石", "隕石", "彗星", "小行星", "空间站", "空間站", "宇航员", "宇航員"],
                "weight": 1.0
            },
            "science": {
                "keywords": ["科学", "科學", "研究", "实验", "實驗", "理论", "理論", "数据", "數據", "分析", "发现", "發現", "技术", "技術", "原理", "规律", "規律"],
                "weight": 0.9
            },
            "nature": {
                "keywords": ["自然", "环境", "環境", "生态", "生態", "气候", "氣候", "动物", "動物", "植物",
                            "地形", "地貌", "水文", "地质", "地質"],
                "weight": 0.8
            },
            "history": {
                "keywords": ["历史", "歷史", "古代", "文明", "文化", "传统", "傳統", "遗迹", "遺跡", "考古", "文物", "朝代", "事件"],
                "weight": 0.8
            },
            "technology": {
                "keywords": ["科技", "技术", "技術", "发明", "發明", "创新", "創新", "人工智能", "计算机", "計算機",
                            "网络", "網絡", "数码", "數碼", "自动化", "自動化", "机器人", "機器人"],
                "weight": 0.9
            },
            "art": {
                "keywords": ["艺术", "藝術", "绘画", "繪畫", "音乐", "音樂", "文学", "文學", "电影", "電影", "戏剧", "戲劇", "雕塑", "建筑", "建築", "设计", "設計", "创意", "創意"],
                "weight": 0.7
            },
            "education": {
                "keywords": ["教育", "学习", "學習", "知识", "知識", "培训", "培訓", "课程", "課程", "学校", "學校", "教师", "教師", "学生", "學生", "教材", "考试", "考試"],
                "weight": 0.7
            },
            "business": {
                "keywords": ["商业", "商業", "经济", "經濟", "市场", "市場", "企业", "企業", "金融", "贸易", "貿易", "管理", "营销", "營銷", "创业", "創業", "投资", "投資"],
                "weight": 0.7
            },
            "health": {
                "keywords": ["健康", "医疗", "醫療", "疾病", "治疗", "治療", "预防", "預防", "营养", "營養", "运动", "運動", "心理", "生理", "医药", "醫藥"],
                "weight": 0.8
            },
            "travel": {
                "keywords": ["旅行", "旅游", "旅遊", "景点", "景點", "风景", "風景", "城市", "乡村", "鄉村", "文化", "体验", "體驗", "探索", "冒险", "冒險"],
                "weight": 0.7
            }
        }
        
        # 计算每个内容类型的得分
        scores = {}
        for content_type, data in content_types.items():
            score = 0
            for keyword in data["keywords"]:
                if keyword in sentence:
                    score += data["weight"]
            if score > 0:
                scores[content_type] = score
        
        # 返回得分最高的内容类型
        if scores:
            return max(scores, key=scores.get)
        
        return "general"


    def calculate_semantic_weight(self, sentence):
        """计算语义权重 - 增强版，提供更好的区分度
        
        评分维度：
        1. 关键词权重（核心论点/转折/强调）
        2. 句子长度
        3. 标点符号（疑问/感叹/转折）
        4. 内容类型
        5. 语义角色（开场/结论/转折/核心论据）
        """
        keyword_weights = {
            "重要": 1.5, "关键": 1.5, "核心": 1.5, "本质": 1.5,
            "新": 1.0, "创新": 1.0, "发现": 1.0, "突破": 1.2,
            "首先": 0.8, "首次": 1.0, "唯一": 1.0,
            "因为": 0.8, "所以": 0.8, "但是": 1.0, "然而": 1.0,
            "如果": 0.6, "假设": 0.6, "可能": 0.5,
            "必须": 1.0, "应该": 0.6, "需要": 0.5,
            "建议": 0.4, "推荐": 0.4, "注意": 0.6,
            "共同": 1.2, "祖先": 1.2, "起源": 1.2, "根本": 1.2,
            "为什么": 1.2, "为何": 1.2, "到底": 1.0,
            "恰恰": 1.0, "偏偏": 1.0, "正是": 1.0,
            "意味着": 1.0, "说明": 0.8, "表明": 0.8,
            "最终": 0.8, "结果": 0.6, "其实": 0.8,
        }
        
        weight = 0.7
        
        for keyword, keyword_weight in keyword_weights.items():
            if keyword in sentence:
                weight += keyword_weight
        
        sentence_length = len(sentence)
        if sentence_length > 50:
            weight += 0.5
        elif sentence_length > 30:
            weight += 0.3
        elif sentence_length < 10:
            weight -= 0.3
        
        if "？" in sentence or "?" in sentence:
            weight += 0.8
        if "！" in sentence or "!" in sentence:
            weight += 0.6
        if "。" in sentence:
            weight += 0.2
        if "，" in sentence:
            weight += 0.1
        if "但是" in sentence or "然而" in sentence or "不过" in sentence:
            weight += 0.5
        
        content_type = self.analyze_content_type(sentence)
        content_weight = {
            "space": 1.1, "science": 1.05, "technology": 1.05,
            "history": 1.0, "nature": 1.0, "health": 1.0,
            "business": 0.95, "education": 0.95, "art": 0.9,
            "travel": 0.9, "general": 0.85
        }
        weight *= content_weight.get(content_type, 0.85)
        
        return round(min(weight, 5.0), 2)


    def _semantic_similarity(self, text_a, text_b):
        """计算两段中文文本的语义相似度（0.0-1.0）
        
        基于共享字符比例和关键词重叠度，用于智能分镜合并决策。
        不依赖外部库，使用字符级n-gram匹配 + 单字符重叠 + 主题关键词。
        """
        if not text_a or not text_b:
            return 0.0
        a_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text_a.lower())
        b_clean = re.sub(r'[^\u4e00-\u9fff\w]', '', text_b.lower())
        if not a_clean or not b_clean:
            return 0.0
        
        a_chars = set(a_clean)
        b_chars = set(b_clean)
        char_intersection = a_chars & b_chars
        char_union = a_chars | b_chars
        char_jaccard = len(char_intersection) / len(char_union) if char_union else 0.0
        
        def _char_ngrams(s, n=2):
            return set(s[i:i+n] for i in range(max(1, len(s)-n+1)))
        a_ngrams = _char_ngrams(a_clean)
        b_ngrams = _char_ngrams(b_clean)
        if a_ngrams and b_ngrams:
            ngram_intersection = a_ngrams & b_ngrams
            ngram_union = a_ngrams | b_ngrams
            ngram_jaccard = len(ngram_intersection) / len(ngram_union) if ngram_union else 0.0
        else:
            ngram_jaccard = 0.0
        
        _TOPIC_KEYWORDS = [
            "政治", "经济", "军事", "科技", "文化", "历史", "自然", "社会",
            "教育", "健康", "环境", "能源", "外交", "法律", "金融",
        ]
        _TOPIC_SINGLE = {
            "军": "军事", "政": "政治", "经": "经济", "科": "科技",
            "文": "文化", "史": "历史", "法": "法律", "外": "外交",
        }
        a_topics = set(kw for kw in _TOPIC_KEYWORDS if kw in text_a)
        b_topics = set(kw for kw in _TOPIC_KEYWORDS if kw in text_b)
        for char, topic in _TOPIC_SINGLE.items():
            if char in text_a:
                a_topics.add(topic)
            if char in text_b:
                b_topics.add(topic)
        topic_overlap = 1.0 if a_topics & b_topics else (0.5 if not a_topics and not b_topics else 0.0)
        
        similarity = char_jaccard * 0.3 + ngram_jaccard * 0.3 + topic_overlap * 0.4
        return min(similarity, 1.0)

    def _split_description_semantic(self, desc, num_parts):
        if not desc:
            return [''] * num_parts
        sentences = re.split(r'([。.！!？?；;])', desc)
        merged = []
        buf = ''
        for seg in sentences:
            buf += seg
            if seg in '\u3002.\uff01\uff1f\uff1b' and buf.strip():
                merged.append(buf.strip())
                buf = ''
        if buf.strip():
            merged.append(buf.strip())
        if not merged:
            sub = re.split(r'[，,、]', desc)
            merged = [s.strip() for s in sub if s.strip()]
        if not merged:
            merged = [desc]
        if len(merged) >= num_parts:
            sent_lens = [len(s) for s in merged]
            total_len = sum(sent_lens)
            target = total_len / num_parts
            parts = []
            current_part = []
            current_len = 0
            for s in merged:
                current_part.append(s)
                current_len += len(s)
                if current_len >= target and len(parts) < num_parts - 1:
                    parts.append(''.join(current_part))
                    current_part = []
                    current_len = 0
            if current_part:
                if parts:
                    parts.append(''.join(current_part))
                else:
                    parts.append(''.join(current_part))
            while len(parts) < num_parts:
                parts.append(parts[-1] if parts else desc)
            return parts[:num_parts]
        if len(merged) == 1:
            result = []
            chunk = max(1, len(merged[0]) // num_parts)
            for p in range(num_parts):
                start_c = p * chunk
                end_c = start_c + chunk if p < num_parts - 1 else len(merged[0])
                part = merged[0][start_c:end_c].strip()
                if not part:
                    part = merged[0]
                result.append(part)
            return result
        while len(merged) < num_parts:
            longest_idx = max(range(len(merged)), key=lambda i: len(merged[i]))
            s = merged[longest_idx]
            mid = len(s) // 2
            split_pos = mid
            for ch in '，,、 ':
                pos = s.find(ch, max(1, mid - 3))
                if pos != -1 and pos < mid + 3:
                    split_pos = pos + 1
                    break
            merged[longest_idx:longest_idx+1] = [s[:split_pos].strip(), s[split_pos:].strip()]
        return merged[:num_parts]

    _CAMERA_ANGLES = [
        'wide establishing shot', 'medium shot', 'close-up shot',
        'over-the-shoulder shot', 'low angle shot', 'high angle shot',
        'dutch angle shot', 'extreme close-up', 'full body shot',
        "bird's eye view shot", 'tracking shot', 'panoramic shot',
    ]
    _LIGHTING_STYLES = [
        'dramatic lighting', 'soft natural lighting',
        'backlit silhouette', 'golden hour lighting',
        'harsh shadow lighting', 'diffused overcast lighting',
        'neon-lit atmosphere', 'candlelight glow', 'spotlight focus',
        'ambient lighting',
    ]
    _COMPOSITION_TYPES = [
        'rule of thirds composition', 'centered composition',
        'leading lines', 'symmetrical framing',
        'negative space', 'layered foreground',
        'diagonal composition', 'frame within frame',
    ]

    def _regenerate_prompt_for_split_shot(self, description, orig_shot, part_index, total_parts):
        orig_prompt = orig_shot.get('prompt_en', '')
        core_theme = orig_shot.get('core_theme', '')
        visual_tone = orig_shot.get('visual_tone', '')

        model_type = "sd15"
        if hasattr(self, 'model_var'):
            mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            try:
                from video_generator.model_profiles import detect_model_type
                model_type = detect_model_type(mn)
            except Exception:
                pass

        angle = self._CAMERA_ANGLES[part_index % len(self._CAMERA_ANGLES)]
        lighting = self._LIGHTING_STYLES[(part_index + 1) % len(self._LIGHTING_STYLES)]
        composition = self._COMPOSITION_TYPES[(part_index + 2) % len(self._COMPOSITION_TYPES)]

        translated_tone = self._translate_to_english(visual_tone) if visual_tone else ''
        if translated_tone and re.search(r'[\u4e00-\u9fff]', translated_tone):
            translated_tone = ''

        orig_desc = orig_shot.get('description', '')
        is_desc_different = description != orig_desc and description.strip()

        if model_type == 'flux':
            desc_en = self._extract_visual_keywords_from_description(description) if is_desc_different else ''
            tone_str = translated_tone if translated_tone else ''
            result_parts = [f"A {angle.lower()} scene"]
            if desc_en:
                desc_words = [w.strip() for w in desc_en.replace(',', ' and').split(' and') if w.strip()]
                if desc_words:
                    result_parts.append(f"showing {' and '.join(desc_words[:5])}")
            if tone_str:
                result_parts.append(f"with a {tone_str.lower()} atmosphere")
            result_parts.append(f"{lighting.lower()} lighting")
            result = '. '.join(p.strip() for p in result_parts if p.strip())
            result = re.sub(r'[\u4e00-\u9fff]+', '', result)
            result = re.sub(r'\([^)]*:[\d.]+\)', lambda m: m.group(0).split(':')[0].strip('()'), result)
            result = re.sub(r'\[([^]]*):[\d.]+\]', r'\1', result)
            result = re.sub(r'\(\(([^)]+)\)\)', r'\1', result)
            return result if result else orig_prompt

        existing_lower = set(k.strip().lower() for k in orig_prompt.split(',') if len(k.strip()) > 2)
        camera_lower = {'wide', 'medium', 'close-up', 'close up', 'shot', 'angle', 'view',
                        'establishing', 'over-the-shoulder', 'dutch', 'extreme', 'body',
                        'bird', 'tracking', 'panoramic', 'low', 'high'}
        core_parts = [p.strip() for p in orig_prompt.split(',') if p.strip()
                      and not any(kw in p.lower() for kw in camera_lower)]

        parts = []
        parts.append(angle)
        parts.append(lighting)
        parts.append(composition)

        if is_desc_different:
            new_keywords = self._extract_visual_keywords_from_description(description)
            if new_keywords:
                for kw in new_keywords.split(','):
                    kw = kw.strip()
                    if kw and kw.lower() not in existing_lower:
                        parts.append(kw)

            theme_translated = self._translate_to_english(core_theme) if core_theme else ''
            if theme_translated and not re.search(r'[\u4e00-\u9fff]', theme_translated) and theme_translated.lower() not in orig_prompt.lower():
                parts.append(theme_translated)
        else:
            if core_parts:
                parts.extend(core_parts[:8])

        if translated_tone and translated_tone.lower() not in ' '.join(parts).lower():
            parts.append(translated_tone)

        result = ', '.join(parts)
        result = re.sub(r'[\u4e00-\u9fff]+', '', result)
        result = re.sub(r',\s*,', ',', result)
        result = re.sub(r'^\s*,|,\s*$', '', result)
        seen = set()
        deduped = []
        for p in result.split(','):
            p = p.strip()
            if p and p.lower() not in seen:
                seen.add(p.lower())
                deduped.append(p)
        result = ', '.join(deduped)
        return result if result else orig_prompt

    def _extract_visual_keywords_from_description(self, description):
        """从描述文本中提取可用于SD提示词的英文关键词"""
        if not description:
            return ''

        _desc_keyword_map = {
            '总统': 'president', '领袖': 'leader', '将军': 'general',
            '士兵': 'soldier', '军官': 'military officer', '外交官': 'diplomat',
            '民众': 'crowd', '难民': 'refugee', '反对派': 'opposition',
            '战争': 'war zone', '战斗': 'battlefield', '冲突': 'conflict',
            '制裁': 'sanctions', '选举': 'election', '谈判': 'negotiation',
            '石油': 'oil industry', '经济': 'economy', '金融': 'finance',
            '城市': 'city', '街道': 'street', '建筑': 'building',
            '宫殿': 'palace', '办公室': 'office', '会议室': 'conference room',
            '边境': 'border', '港口': 'harbor', '工厂': 'factory',
            '广场': 'square', '监狱': 'prison', '法庭': 'courtroom',
            '直升机': 'helicopter', '坦克': 'tank', '军舰': 'warship',
            '旗帜': 'flag', '地图': 'map', '文件': 'document',
            '演讲': 'speech', '抗议': 'protest', '游行': 'rally',
            '会议': 'meeting', '握手': 'handshake', '签字': 'signing',
            '行走': 'walking', '站立': 'standing', '交谈': 'conversation',
            '夜晚': 'night scene', '白天': 'daylight', '室内': 'indoor',
            '室外': 'outdoor', '黎明': 'dawn', '黄昏': 'dusk',
        }

        keywords = []
        for cn, en in _desc_keyword_map.items():
            if cn in description and en not in keywords:
                keywords.append(en)

        return ', '.join(keywords[:3]) if keywords else ''

    def _regenerate_prompt_for_merged_shot(self, merged_description, keeper_shot):
        """为合并后的分镜生成提示词（轻量方式，不调用LLM）

        策略：合并两个prompt的关键词 + 从合并描述中提取新关键词
        """
        keeper_prompt = keeper_shot.get('prompt_en', '')
        visual_tone = keeper_shot.get('visual_tone', '')
        translated_tone = self._translate_to_english(visual_tone) if visual_tone else ''
        if translated_tone and re.search(r'[\u4e00-\u9fff]', translated_tone):
            translated_tone = ''

        model_type = "sd15"
        if hasattr(self, 'model_var'):
            mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            try:
                from video_generator.model_profiles import detect_model_type
                model_type = detect_model_type(mn)
            except Exception:
                pass

        desc_keywords = self._extract_visual_keywords_from_description(merged_description)

        if model_type == 'flux':
            result_parts = []
            if desc_keywords:
                desc_words = [w.strip() for w in desc_keywords.replace(',', ' and').split(' and') if w.strip()]
                if desc_words:
                    result_parts.append(f"A scene showing {' and '.join(desc_words[:5])}")
            if keeper_prompt:
                cleaned_keeper = re.sub(r'\([^)]*:[\d.]+\)', lambda m: m.group(0).split(':')[0].strip('()'), keeper_prompt)
                cleaned_keeper = re.sub(r'\[([^]]*):[\d.]+\]', r'\1', cleaned_keeper)
                cleaned_keeper = re.sub(r'\(\(([^)]+)\)\)', r'\1', cleaned_keeper)
                keeper_words = [w.strip() for w in cleaned_keeper.replace(',', ' and').split(' and') if w.strip()]
                if keeper_words:
                    result_parts.append(f"featuring {' and '.join(keeper_words[:6])}")
            if translated_tone:
                result_parts.append(f"with a {translated_tone.lower()} atmosphere")
            result = '. '.join(p.strip() for p in result_parts if p.strip())
            result = re.sub(r'[\u4e00-\u9fff]+', '', result)
            return result if result else keeper_prompt

        parts = []
        if desc_keywords:
            parts.append(desc_keywords)
        if keeper_prompt:
            parts.append(keeper_prompt)
        if translated_tone and translated_tone.lower() not in keeper_prompt.lower():
            parts.append(translated_tone)

        result = ', '.join(parts)
        result = re.sub(r'[\u4e00-\u9fff]+', '', result)
        result = re.sub(r',\s*,', ',', result)
        result = re.sub(r'^\s*,|,\s*$', '', result)
        return result if result else keeper_prompt

    def _merge_shots(self, shots, keep_idx, remove_idx):
        """智能合并两个分镜，保留语义更丰富的一方的时间范围
        
        合并规则：
        - 时间范围：合并后覆盖两个分镜的完整时间跨度
        - 描述文本：用空格连接，保留两段语义
        - prompt_en：保留语义权重更高的一方（避免SD提示词拼接混乱）
        - 音画同步：确保start/end时间戳连续无间隙
        """
        if keep_idx >= len(shots) or remove_idx >= len(shots):
            return
        keeper = shots[keep_idx]
        removed = shots[remove_idx]
        new_start = min(keeper['start'], removed['start'])
        new_end = max(keeper['end'], removed['end'])
        keeper['start'] = new_start
        keeper['end'] = new_end
        keeper['duration'] = new_end - new_start
        keeper['description'] = keeper.get('description', '') + ' ' + removed.get('description', '')
        keeper_weight = keeper.get('semantic_weight', 0.5)
        removed_weight = removed.get('semantic_weight', 0.5)
        if removed_weight > keeper_weight and removed.get('prompt_en', ''):
            keeper['prompt_en'] = removed['prompt_en']
        if removed.get('negative_prompt', '') and not keeper.get('negative_prompt', ''):
            keeper['negative_prompt'] = removed['negative_prompt']
        keeper['semantic_weight'] = max(keeper_weight, removed_weight)
        merged_desc = keeper.get('description', '')
        if merged_desc:
            keeper['prompt_en'] = self._regenerate_prompt_for_merged_shot(merged_desc, keeper)
            sd_model_name = ""
            if hasattr(self, 'model_var'):
                sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            keeper['prompt_en'] = self._build_final_prompt(keeper['prompt_en'], sd_model_name)
            keeper['prompt_quality'] = self._calculate_prompt_quality(
                keeper['prompt_en'], merged_desc
            )
        shots.pop(remove_idx)


    # =======================================================================
    # 第四部分：分镜创建与管理 (行 3422-3840)
    # =======================================================================



    def _merge_semantic_segments(self, segments):
        """基于大模型语义理解划分分镜
        
        策略：
        1. 将Whisper片段拼接为完整文本
        2. 大模型添加标点符号，并按标点/语义划分分镜
        3. 将划分结果映射回时间戳
        4. 如果大模型不可用，回退到规则合并
        """
        if not segments or len(segments) <= 1:
            return segments
        
        try:
            if not is_llm_available():
                return segments
            model = self._get_current_model()
            
            indexed_lines = []
            for i, seg in enumerate(segments):
                text = seg['text'].strip()
                start = seg['start']
                end = seg['end']
                duration = end - start
                indexed_lines.append(f"[{i}] ({start:.1f}s-{end:.1f}s, {duration:.1f}s) {text}")
            
            segments_text = "\n".join(indexed_lines)
            
            system_prompt = """你是视频分镜编辑。你的任务是将语音识别产生的无标点碎片文本，添加标点符号后按语义划分分镜。

【规则】
1. 先为整个文本添加正确的标点符号（逗号、句号、问号等）
2. 然后按标点符号和语义完整性划分分镜
3. 每个分镜必须是一句或几句话构成的完整语义段落
4. 每个分镜时长建议3-10秒，最短不少于2.5秒
5. 只能合并相邻片段，不能拆分或重排
6. 同时纠正明显的语音识别错误（如同音字、人名错字）
7. 过短的片段（<2.5秒）必须与相邻片段合并，确保每个分镜都有足够的展示时间

【输出格式】严格输出JSON数组，每个元素包含：
- "range": [起始片段索引, 结束片段索引]（包含两端）
- "text": 添加标点后的分镜文本

示例输出：
[{"range":[0,2],"text":"回看这些年，商界的风云变幻，地产大佬们的境遇真可谓是同行不同命。"},{"range":[3,5],"text":"如果我们把这些曾经叱咤风云的人物放在一张坐标图上，你会发现，虽然大家都曾站在财富的巅峰，但现在的处境却天差地别。"}]

重要：
- range必须覆盖所有片段索引，不遗漏不重复
- text必须包含正确的标点符号
- 纠正明显的语音识别错误"""

            user_prompt = f"以下是{len(segments)}个语音片段，请添加标点并按语义划分分镜：\n\n{segments_text}"
            
            result_text, _ = call_ollama_single(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                log_callback=self.log,
                num_predict=4000,
                num_ctx=8192,
                llm_config=getattr(self, 'current_llm_config', None),
                timeout=Config.API_TIMEOUT_LLM_ANALYSIS,
                cancel_check=lambda: not self.task_running
            )
            
            if not result_text:
                raise ValueError("大模型调用失败")
            
            raw_output = result_text.strip()
            
            
            json_match = re.search(r'\[.*\]', raw_output, re.DOTALL)
            if not json_match:
                raise ValueError("大模型未返回有效JSON")
            
            merge_plan = json.loads(json_match.group())
            
            if not isinstance(merge_plan, list) or not merge_plan:
                raise ValueError("合并计划格式无效")
            
            merged = []
            covered = set()
            for item in merge_plan:
                if not isinstance(item, dict):
                    continue
                range_info = item.get('range', item.get('index', []))
                punctuated_text = item.get('text', '')
                
                if not isinstance(range_info, list) or len(range_info) != 2:
                    continue
                
                start_idx, end_idx = int(range_info[0]), int(range_info[1])
                start_idx = max(0, min(start_idx, len(segments) - 1))
                end_idx = max(start_idx, min(end_idx, len(segments) - 1))
                
                if not punctuated_text:
                    punctuated_text = ""
                    for j in range(start_idx, end_idx + 1):
                        punctuated_text += segments[j]['text'].strip()
                
                merged_start = segments[start_idx]['start']
                merged_end = segments[end_idx]['end']
                
                for j in range(start_idx, end_idx + 1):
                    covered.add(j)
                
                merged.append({
                    'text': punctuated_text,
                    'start': merged_start,
                    'end': merged_end,
                })
            
            for j in range(len(segments)):
                if j not in covered:
                    merged.append({
                        'text': segments[j]['text'].strip(),
                        'start': segments[j]['start'],
                        'end': segments[j]['end'],
                    })
            
            merged.sort(key=lambda x: x['start'])
            
            deduped = []
            for item in merged:
                if deduped:
                    prev = deduped[-1]
                    if item['start'] < prev['end']:
                        if item['end'] > prev['end']:
                            item['start'] = prev['end']
                        else:
                            continue
                if item['end'] > item['start']:
                    deduped.append(item)
            
            merged = deduped
            
            self.log(f"   ✅ 大模型语义划分: {len(segments)} → {len(merged)} 个分镜")
            return merged
            
        except Exception as e:
            self._log_exception(f"   ⚠️ 大模型语义划分失败，回退到规则合并", e)
            return self._rule_based_merge(segments)
    

    def _rule_based_merge(self, segments):
        """规则合并：大模型不可用时的回退方案
        
        策略：
        1. 过短的片段（< 2.5秒）与相邻片段合并
        2. 语义不完整的片段（只有连词/过渡词）与下一个片段合并
        3. 二次合并：合并后仍过短的片段继续合并
        """
        if not segments or len(segments) <= 1:
            return segments
        
        incomplete_words = {
            '然而', '但是', '不过', '而且', '因此', '所以', '于是',
            '同时', '另外', '此外', '并且', '接着', '然后',
            '其实', '实际上', '当然', '总之', '说到底', '归根结底',
            '相比之下', '换句话说', '也就是说', '不仅如此',
            '更重要的是', '值得注意的是', '事实上',
            '先聊聊', '再看看', '还有', '比如', '例如',
            '而', '但', '又', '且', '则',
        }
        
        merged = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            text = seg['text'].strip()
            duration = seg['end'] - seg['start']
            
            should_merge = False
            
            if duration < 2.5:
                should_merge = True
            
            if text in incomplete_words:
                should_merge = True
            
            if len(text) <= 3 and text not in {'是的', '没错', '对', '好'}:
                should_merge = True
            
            if should_merge and merged:
                last = merged[-1]
                last['text'] = last['text'] + text
                last['end'] = seg['end']
                i += 1
                continue
            
            if should_merge and not merged and i + 1 < len(segments):
                next_seg = segments[i + 1]
                merged.append({
                    'text': text + next_seg['text'].strip(),
                    'start': seg['start'],
                    'end': next_seg['end'],
                })
                i += 2
                continue
            
            merged.append({
                'text': text,
                'start': seg['start'],
                'end': seg['end'],
            })
            i += 1
        
        if len(merged) > 1:
            final = [merged[0]]
            for j in range(1, len(merged)):
                prev = final[-1]
                curr = merged[j]
                prev_duration = prev['end'] - prev['start']
                if prev_duration < 3.0:
                    prev['text'] = prev['text'] + curr['text'].strip()
                    prev['end'] = curr['end']
                else:
                    final.append(curr)
            if len(final) > 1:
                last = final[-1]
                prev = final[-2]
                if (last['end'] - last['start']) < 3.0:
                    prev['text'] = prev['text'] + last['text'].strip()
                    prev['end'] = last['end']
                    final.pop()
            merged = final
        
        return merged


    def _review_narrative_coherence(self, pregenerated_prompts, final_tasks):
        """全局叙事连贯性审查 - 确保视觉叙事弧线完整
        
        审查维度：
        1. 首尾呼应：opening和closing分镜的视觉元素应有主题关联
        2. 叙事弧线：确保opening→development→climax→resolution的视觉强度递进
        3. 视觉基调一致性：检测并修正突兀的风格跳变
        """
        if not pregenerated_prompts or len(pregenerated_prompts) < 3:
            return
        
        indices = sorted(pregenerated_prompts.keys())
        total = len(indices)
        if total < 3:
            return
        
        first_prompt = pregenerated_prompts.get(indices[0], "")
        last_prompt = pregenerated_prompts.get(indices[-1], "")
        
        if first_prompt and last_prompt:
            _CLOSING_THEMES = {
                'palace': 'empty courtyard, no allies',
                'balcony': 'distant horizon, solitude',
                'office': 'dimly lit, papers scattered',
                'military': 'silent battlefield, aftermath',
                'courtroom': 'empty chamber, gavel at rest',
                'protest': 'quiet street, aftermath',
                'portrait': 'reflective gaze, contemplation',
                'handshake': 'sealed document, finality',
                'flag': 'sunset over landmark, closure',
            }
            
            first_lower = first_prompt.lower()
            closing_theme_found = False
            for key, closing_visual in _CLOSING_THEMES.items():
                if key in first_lower and key not in last_prompt.lower():
                    last_prompt = last_prompt.rstrip() + f", {closing_visual}"
                    pregenerated_prompts[indices[-1]] = last_prompt
                    closing_theme_found = True
                    break
            
            if closing_theme_found:
                self.log("   🎬 尾分镜已添加首尾呼应视觉元素")
        
        _SHOT_TYPE_KEYWORDS = {
            'wide': ['wide angle', 'wide shot', 'establishing shot', 'panoramic', 'aerial'],
            'medium': ['medium shot', 'medium close-up', 'mid shot', 'waist up'],
            'close': ['close-up', 'close up', 'tight', 'detail shot', 'macro'],
        }
        
        _has_opening_wide = any(kw in first_prompt.lower() for kw in _SHOT_TYPE_KEYWORDS['wide']) if first_prompt else False
        if not _has_opening_wide and total >= 4:
            first_prompt = re.sub(
                r'(medium shot|close-up|close up|tight shot)',
                'wide establishing shot',
                first_prompt,
                count=1,
                flags=re.IGNORECASE
            )
            if first_prompt != pregenerated_prompts.get(indices[0], ""):
                pregenerated_prompts[indices[0]] = first_prompt
                self.log("   🎬 首分镜已调整为广角建立镜头")
        
        _has_closing_wide = any(kw in last_prompt.lower() for kw in _SHOT_TYPE_KEYWORDS['wide'] + _SHOT_TYPE_KEYWORDS['medium']) if last_prompt else False
        if not _has_closing_wide and total >= 4:
            last_prompt = re.sub(
                r'(close-up|close up|tight shot|macro)',
                'medium shot, reflective',
                last_prompt,
                count=1,
                flags=re.IGNORECASE
            )
            if last_prompt != pregenerated_prompts.get(indices[-1], ""):
                pregenerated_prompts[indices[-1]] = last_prompt
                self.log("   🎬 尾分镜已调整为收束镜头")


    def _check_and_deduplicate_prompts(self, pregenerated_prompts, final_tasks):
        """检测并修正重复的提示词 - 轻量级本地处理版
        
        策略：
        1. 计算提示词的词汇重叠率（相邻）
        2. 重叠率超过50%的标记为重复，使用本地规则替换
        3. 检测高频视觉元素重复，使用预定义替代方案替换
        4. 不调用LLM，纯本地处理，零额外延迟
        
        Returns:
            修正的重复提示词数量
        """
        if not pregenerated_prompts or len(pregenerated_prompts) <= 1:
            return 0
        
        def _token_overlap_ratio(p1, p2):
            if not p1 or not p2:
                return 0.0
            tokens1 = set(p1.lower().split(','))
            tokens1 = {t.strip() for t in tokens1 if len(t.strip()) > 2}
            tokens2 = set(p2.lower().split(','))
            tokens2 = {t.strip() for t in tokens2 if len(t.strip()) > 2}
            if not tokens1 or not tokens2:
                return 0.0
            intersection = tokens1 & tokens2
            union = tokens1 | tokens2
            return len(intersection) / len(union) if union else 0.0
        
        def _select_semantic_alternative(alternatives, description):
            if not alternatives:
                return None
            if not description:
                import random
                return random.choice(alternatives)
            desc_lower = description.lower()
            scored = []
            for alt in alternatives:
                s = 0
                for kw in alt.lower().split():
                    if kw in desc_lower:
                        s += 1
                scored.append((alt, s))
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored and scored[0][1] > 0:
                return scored[0][0]
            import random
            return random.choice(alternatives)
        
        def _get_visual_elements(prompt):
            if not prompt:
                return set()
            visual_keywords = {
                'palace', 'office', 'military', 'soldier', 'general',
                'casino', 'poker', 'card', 'gold', 'oil', 'contract',
                'courtroom', 'prison', 'border', 'refugee',
                'helicopter', 'warship', 'tank', 'rifle', 'missile',
                'protest', 'crowd', 'rally', 'speech', 'podium',
                'map', 'globe', 'flag', 'document', 'desk',
                'professor', 'scientist', 'researcher',
                'laboratory', 'museum', 'hospital',
                'forest', 'jungle', 'mountain', 'ocean', 'desert',
                'factory', 'port', 'harbor', 'airport', 'train station',
            }
            prompt_lower = prompt.lower()
            found = set()
            for kw in visual_keywords:
                if kw in prompt_lower:
                    found.add(kw)
            return found
        
        VISUAL_ALTERNATIVES = {
            'palace': ['government building corridor', 'presidential residence exterior', 'official chamber'],
            'office': ['war room', 'command center', 'briefing room', 'diplomatic chamber'],
            'military': ['armed patrol', 'security detail', 'paramilitary unit'],
            'soldier': ['armed guard', 'security personnel', 'military officer'],
            'general': ['admiral', 'field marshal', 'commander in uniform'],
            'courtroom': ['tribunal chamber', 'international court', 'judicial hearing room'],
            'prison': ['detention facility', 'holding cell', 'interrogation room'],
            'border': ['checkpoint crossing', 'frontier outpost', 'coastal patrol'],
            'protest': ['demonstration march', 'public gathering', 'strike rally'],
            'oil': ['petroleum refinery', 'oil pipeline', 'energy infrastructure'],
            'forest': ['open savanna', 'coastal wetland', 'mountain meadow'],
            'casino': ['high-stakes negotiation table', 'backroom deal', 'luxury hotel suite'],
            'poker': ['strategic negotiation', 'backroom dealing', 'diplomatic bargaining'],
            'card': ['negotiation document', 'treaty paper', 'strategic dossier'],
            'gold': ['oil contract', 'mineral rights document', 'treasury vault'],
            'contract': ['treaty document', 'trade agreement', 'memorandum'],
            'refugee': ['displaced family', 'evacuee convoy', 'humanitarian camp'],
            'helicopter': ['military transport plane', 'surveillance drone', 'naval vessel'],
            'warship': ['patrol boat', 'submarine', 'aircraft carrier deck'],
            'tank': ['armored vehicle', 'military jeep', 'patrol truck'],
            'rifle': ['sidearm', 'military baton', 'security radio'],
            'missile': ['rocket launcher', 'military installation', 'defense system'],
            'crowd': ['assembled officials', 'parliament members', 'delegation'],
            'rally': ['political convention', 'campaign event', 'press conference'],
            'speech': ['address from podium', 'televised announcement', 'press statement'],
            'podium': ['negotiation table', 'cabinet desk', 'parliament lectern'],
            'map': ['satellite view', 'strategic diagram', 'terrain model'],
            'globe': ['world atlas page', 'regional map', 'strategic chart'],
            'flag': ['national emblem', 'official seal', 'coat of arms'],
            'document': ['classified folder', 'official decree', 'sealed envelope'],
            'desk': ['conference table', 'negotiation table', 'war room table'],
            'museum': ['archive room', 'library study', 'display cabinet'],
            'laboratory': ['field station', 'research vessel', 'outdoor experiment'],
            'hospital': ['medical ward', 'clinic corridor', 'treatment room'],
        }
        
        duplicate_count = 0
        indices = sorted(pregenerated_prompts.keys())
        
        def _remove_duplicate_keywords(prompt):
            if not prompt:
                return prompt
            parts = [p.strip() for p in prompt.split(',') if p.strip()]
            seen = set()
            result = []
            for part in parts:
                key = part.lower().strip()
                if key not in seen:
                    seen.add(key)
                    result.append(part)
            return ', '.join(result)

        # Pass 1: 相邻去重（阈值50%）- 本地替换
        for i in range(1, len(indices)):
            curr_idx = indices[i]
            prev_idx = indices[i - 1]
            curr_prompt = pregenerated_prompts.get(curr_idx, "")
            prev_prompt = pregenerated_prompts.get(prev_idx, "")
            
            if not curr_prompt or not prev_prompt:
                continue
            
            overlap = _token_overlap_ratio(curr_prompt, prev_prompt)
            if overlap > 0.35:
                duplicate_count += 1
                prev_elements = _get_visual_elements(prev_prompt)
                new_prompt = curr_prompt
                for elem in prev_elements:
                    if elem in VISUAL_ALTERNATIVES and elem in new_prompt.lower():
                        alternatives = VISUAL_ALTERNATIVES[elem]
                        curr_desc = final_tasks[curr_idx].get('text', '') if curr_idx < len(final_tasks) else ''
                        replacement = _select_semantic_alternative(alternatives, curr_desc)
                        if replacement.lower() in new_prompt.lower():
                            continue
                        pattern = r'\b' + re.escape(elem) + r'\b'
                        new_prompt = re.sub(pattern, replacement, new_prompt, count=1, flags=re.IGNORECASE)
                if new_prompt != curr_prompt:
                    new_prompt = re.sub(r'(\w+ized)', lambda m: m.group(0).replace('ized', ''), new_prompt)
                    new_prompt = re.sub(r'(\w+ized)\s+(\w+)', r'\2', new_prompt)
                    new_prompt = re.sub(r'\b\w+ized\b', '', new_prompt)
                    new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                    new_prompt = re.sub(r',\s*,', ',', new_prompt)
                    new_prompt = _remove_duplicate_keywords(new_prompt)
                    new_prompt = new_prompt.strip(' ,')
                    pregenerated_prompts[curr_idx] = new_prompt
                    self._pregenerated_prompts_for_context[curr_idx] = new_prompt
        
        # Pass 2: 高频视觉元素去重（同一视觉元素在连续3+个分镜中出现）- 本地替换
        element_history = {}
        for i in range(len(indices)):
            idx = indices[i]
            prompt = pregenerated_prompts.get(idx, "")
            if not prompt:
                continue
            current_elements = _get_visual_elements(prompt)
            for elem in current_elements:
                if elem not in element_history:
                    element_history[elem] = []
                element_history[elem].append(i)
        
        for elem, occurrences in element_history.items():
            consecutive_runs = []
            run_start = 0
            for j in range(1, len(occurrences)):
                if occurrences[j] - occurrences[j-1] <= 2:
                    continue
                else:
                    if j - run_start >= 3:
                        consecutive_runs.append(occurrences[run_start:j])
                    run_start = j
            if len(occurrences) - run_start >= 3:
                consecutive_runs.append(occurrences[run_start:])
            
            for run in consecutive_runs:
                for k in range(2, len(run)):
                    dup_idx = indices[run[k]]
                    dup_prompt = pregenerated_prompts.get(dup_idx, "")
                    if dup_prompt and elem in VISUAL_ALTERNATIVES:
                        alternatives = VISUAL_ALTERNATIVES[elem]
                        dup_desc = final_tasks[dup_idx].get('text', '') if dup_idx < len(final_tasks) else ''
                        replacement = _select_semantic_alternative(alternatives, dup_desc)
                        if replacement.lower() in dup_prompt.lower():
                            continue
                        pattern = r'\b' + re.escape(elem) + r'\b'
                        new_prompt = re.sub(pattern, replacement, dup_prompt, count=1, flags=re.IGNORECASE)
                        if new_prompt != dup_prompt:
                            new_prompt = re.sub(r'(\w+ized)', lambda m: m.group(0).replace('ized', ''), new_prompt)
                            new_prompt = re.sub(r'(\w+ized)\s+(\w+)', r'\2', new_prompt)
                            new_prompt = re.sub(r'\b\w+ized\b', '', new_prompt)
                            new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                            new_prompt = re.sub(r',\s*,', ',', new_prompt)
                            new_prompt = _remove_duplicate_keywords(new_prompt)
                            new_prompt = new_prompt.strip(' ,')
                            pregenerated_prompts[dup_idx] = new_prompt
                            self._pregenerated_prompts_for_context[dup_idx] = new_prompt
                            duplicate_count += 1

        # Pass 3: 窗口3内的非相邻相似检测
        # 检测距离2-3的分镜之间的相似度，防止跳过一个分镜后重复
        for i in range(2, len(indices)):
            curr_idx = indices[i]
            curr_prompt = pregenerated_prompts.get(curr_idx, "")
            if not curr_prompt:
                continue
            for gap in (2, 3):
                if i - gap < 0:
                    continue
                prev_idx = indices[i - gap]
                prev_prompt = pregenerated_prompts.get(prev_idx, "")
                if not prev_prompt:
                    continue
                overlap = _token_overlap_ratio(curr_prompt, prev_prompt)
                if overlap > 0.45:
                    prev_elements = _get_visual_elements(prev_prompt)
                    new_prompt = curr_prompt
                    for elem in prev_elements:
                        if elem in VISUAL_ALTERNATIVES and elem in new_prompt.lower():
                            alternatives = VISUAL_ALTERNATIVES[elem]
                            curr_desc = final_tasks[curr_idx].get('text', '') if curr_idx < len(final_tasks) else ''
                            replacement = _select_semantic_alternative(alternatives, curr_desc)
                            if replacement.lower() in new_prompt.lower():
                                continue
                            pattern = r'\b' + re.escape(elem) + r'\b'
                            new_prompt = re.sub(pattern, replacement, new_prompt, count=1, flags=re.IGNORECASE)
                    if new_prompt != curr_prompt:
                        new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                        new_prompt = re.sub(r',\s*,', ',', new_prompt)
                        new_prompt = _remove_duplicate_keywords(new_prompt)
                        new_prompt = new_prompt.strip(' ,')
                        pregenerated_prompts[curr_idx] = new_prompt
                        self._pregenerated_prompts_for_context[curr_idx] = new_prompt
                        duplicate_count += 1
                    break

        # Pass 4: 中文语义骨架级别去重 - 利用两步法提取的语义骨架
        if hasattr(self, '_chinese_semantic_skeletons') and self._chinese_semantic_skeletons:
            skeleton_indices = sorted(self._chinese_semantic_skeletons.keys())
            for i in range(1, len(skeleton_indices)):
                curr_sk_idx = skeleton_indices[i]
                prev_sk_idx = skeleton_indices[i - 1]
                if abs(curr_sk_idx - prev_sk_idx) > 3:
                    continue
                curr_skeleton = self._chinese_semantic_skeletons.get(curr_sk_idx, "")
                prev_skeleton = self._chinese_semantic_skeletons.get(prev_sk_idx, "")
                if not curr_skeleton or not prev_skeleton:
                    continue
                sk_sim = self._semantic_similarity(curr_skeleton, prev_skeleton)
                if sk_sim > 0.6:
                    curr_prompt = pregenerated_prompts.get(curr_sk_idx, "")
                    if curr_prompt:
                        prev_elements = _get_visual_elements(curr_prompt)
                        new_prompt = curr_prompt
                        for elem in prev_elements:
                            if elem in VISUAL_ALTERNATIVES and elem in new_prompt.lower():
                                alternatives = VISUAL_ALTERNATIVES[elem]
                                sk_desc = final_tasks[curr_sk_idx].get('text', '') if curr_sk_idx < len(final_tasks) else ''
                                replacement = _select_semantic_alternative(alternatives, sk_desc)
                                pattern = r'\b' + re.escape(elem) + r'\b'
                                new_prompt = re.sub(pattern, replacement, new_prompt, count=1, flags=re.IGNORECASE)
                        if new_prompt != curr_prompt:
                            new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                            new_prompt = re.sub(r',\s*,', ',', new_prompt)
                            new_prompt = new_prompt.strip(' ,')
                            pregenerated_prompts[curr_sk_idx] = new_prompt
                            self._pregenerated_prompts_for_context[curr_sk_idx] = new_prompt
                            duplicate_count += 1

        return duplicate_count


    def _extract_entities_for_prompt(self, text):
        """从配音文本中提取关键实体（国家、军事、组织等），返回英文提示"""
        if not text:
            return ""
        
        entities = []
        
        if ENHANCED_RECOGNITION_AVAILABLE:
            try:
                from video_generator.enhanced_content_recognition import (
                    COUNTRY_MAPPING, CITY_MAPPING, ORGANIZATION_MAPPING, MILITARY_MAPPING
                )
                for cn, en in COUNTRY_MAPPING.items():
                    if cn in text:
                        entities.append(en)
                for cn, en in CITY_MAPPING.items():
                    if cn in text:
                        entities.append(en)
                for cn, en in ORGANIZATION_MAPPING.items():
                    if cn in text:
                        entities.append(en)
                for cn, en in MILITARY_MAPPING.items():
                    if cn in text:
                        entities.append(en)
            except ImportError:
                pass
        
        tech_terms = {
            'ChatGPT': 'ChatGPT', 'AI': 'AI', '人工智能': 'AI artificial intelligence',
            '算法': 'algorithm', '数据': 'data', '互联网': 'internet',
            '手机': 'smartphone', '电脑': 'computer', '软件': 'software',
            '机器人': 'robot', '无人机': 'drone', '导弹': 'missile',
            '核武器': 'nuclear weapon', '航母': 'aircraft carrier',
            'GDP': 'GDP', '股市': 'stock market', '经济': 'economy',
        }
        for cn, en in tech_terms.items():
            if cn in text:
                entities.append(en)
        
        seen = set()
        unique = []
        for e in entities:
            e_lower = e.lower()
            if e_lower not in seen:
                seen.add(e_lower)
                unique.append(e)
        
        return ', '.join(unique[:8]) if unique else ""

    _HALLUCINATION_STOPWORDS = {
        'The', 'This', 'These', 'Those', 'With', 'From', 'Into',
        'Over', 'Under', 'Between', 'Through', 'During', 'Before',
        'After', 'Above', 'Below', 'Around', 'Against', 'Within',
        'And', 'But', 'Not', 'For', 'Are', 'Was', 'Were', 'Has',
        'Have', 'Had', 'Will', 'Would', 'Could', 'Should', 'May',
        'Can', 'Its', 'His', 'Her', 'Their', 'Our', 'Your', 'She',
        'Some', 'More', 'Also', 'Very', 'Just', 'Only', 'Than',
        'Then', 'When', 'Where', 'What', 'How', 'Why', 'Who',
        'Which', 'There', 'Here', 'About', 'Like', 'Into', 'Upon',
    }

    def _detect_hallucinated_names(self, prompt_en, description):
        if not prompt_en or not description:
            return set()
        prompt_names = set(re.findall(r'\b[A-Z][a-z]{2,}\b', prompt_en))
        prompt_names -= self._HALLUCINATION_STOPWORDS
        if not prompt_names:
            return set()
        known_en_names = set()
        for length in range(2, 5):
            for i in range(len(description) - length + 1):
                substr = description[i:i+length]
                if not re.match(r'^[\u4e00-\u9fff]+$', substr):
                    continue
                en_trans = self._translate_to_english(substr)
                if en_trans and en_trans != substr:
                    for part in en_trans.replace(',', ' ').split():
                        if len(part) > 2 and part[0].isupper():
                            known_en_names.add(part)
        potential = prompt_names - known_en_names
        sd_common = {
            'Shot', 'Angle', 'View', 'Light', 'Lighting', 'Close',
            'Wide', 'Medium', 'High', 'Low', 'Full', 'Body', 'Dutch',
            'Bird', 'Eye', 'Over', 'Golden', 'Hour', 'Night', 'Day',
            'Film', 'Photo', 'Real', 'Ultra', 'Cinematic', 'Dramatic',
            'Vivid', 'Detailed', 'Texture', 'Modern', 'Ancient',
            'Color', 'Black', 'White', 'Digital', 'Art', 'Style',
            'Quality', 'Resolution', 'Render', 'Scene', 'Image',
            'Depth', 'Field', 'Rule', 'Thirds', 'Negative', 'Space',
            'Leading', 'Lines', 'Centered', 'Symmetrical', 'Frame',
            'Soft', 'Hard', 'Natural', 'Ambient', 'Backlit',
        }
        potential -= sd_common
        return potential

    def _calculate_prompt_quality(self, prompt_en, dubbing_text):
        if not prompt_en:
            return 0.0
        
        score = 0.0
        
        _model_type = "sd15"
        if hasattr(self, 'model_var'):
            _mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            try:
                from video_generator.model_profiles import detect_model_type
                _model_type = detect_model_type(_mn)
            except Exception:
                pass
        
        prompt_len = len(prompt_en)
        if _model_type in ('flux', 'sd3'):
            if 80 <= prompt_len <= 400:
                score += 0.15
            elif 50 <= prompt_len < 80:
                score += 0.10
            elif 400 < prompt_len <= 600:
                score += 0.08
            elif 30 <= prompt_len < 50:
                score += 0.05
            elif prompt_len > 10:
                score += 0.02
        else:
            if 50 <= prompt_len <= 180:
                score += 0.15
            elif 30 <= prompt_len < 50:
                score += 0.10
            elif 180 < prompt_len <= 300:
                score += 0.08
            elif 15 <= prompt_len < 30:
                score += 0.05
            elif prompt_len > 10:
                score += 0.02
        
        keywords = [k.strip() for k in prompt_en.split(',') if k.strip()]
        if _model_type in ('flux', 'sd3'):
            words = prompt_en.split()
            if 20 <= len(words) <= 80:
                score += 0.15
            elif 10 <= len(words) < 20:
                score += 0.10
            elif 80 < len(words) <= 120:
                score += 0.08
            elif 5 <= len(words) < 10:
                score += 0.05
            elif len(words) >= 3:
                score += 0.02
        else:
            if 10 <= len(keywords) <= 22:
                score += 0.15
            elif 7 <= len(keywords) < 10:
                score += 0.10
            elif 22 < len(keywords) <= 30:
                score += 0.08
            elif 4 <= len(keywords) < 7:
                score += 0.05
            elif len(keywords) >= 3:
                score += 0.02
        
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', prompt_en))
        if not has_chinese:
            score += 0.15
        else:
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', prompt_en))
            if chinese_chars <= 2:
                score += 0.06
            elif chinese_chars <= 5:
                score += 0.02
        
        if dubbing_text and ENHANCED_RECOGNITION_AVAILABLE:
            try:
                from video_generator.enhanced_content_recognition import COUNTRY_MAPPING, MILITARY_MAPPING
                entity_hits = 0
                prompt_lower = prompt_en.lower()
                for cn_name, en_value in {**COUNTRY_MAPPING, **MILITARY_MAPPING}.items():
                    if cn_name in dubbing_text:
                        for en_part in en_value.split(','):
                            en_part = en_part.strip().lower()
                            if en_part and en_part in prompt_lower:
                                entity_hits += 1
                                break
                if entity_hits >= 2:
                    score += 0.15
                elif entity_hits == 1:
                    score += 0.08
            except ImportError:
                pass
        
        if dubbing_text:
            desc_keywords = set(re.findall(r'[\u4e00-\u9fff]{2,}', dubbing_text))
            translated = set()
            for kw in desc_keywords:
                en = self._translate_to_english(kw)
                if en and en != kw:
                    translated.update(en.lower().split())
            prompt_lower = prompt_en.lower()
            if translated:
                covered = sum(1 for t in translated if t in prompt_lower)
                coverage = covered / len(translated)
                score += 0.10 * coverage
        
        visual_specificity_words = [
            'close-up', 'wide shot', 'medium shot', 'establishing shot', 'aerial',
            'silhouette', 'reflection', 'shadow', 'backlit', 'golden hour',
            'dramatic', 'vivid', 'intricate', 'detailed', 'textured',
            'glowing', 'illuminated', 'weathered', 'ancient', 'modern',
            'lighting', 'composition', 'atmosphere', 'mood', 'depth', 'contrast',
        ]
        prompt_lower = prompt_en.lower()
        visual_hits = sum(1 for w in visual_specificity_words if w in prompt_lower)
        if visual_hits >= 4:
            score += 0.15
        elif visual_hits >= 3:
            score += 0.12
        elif visual_hits >= 2:
            score += 0.08
        elif visual_hits >= 1:
            score += 0.04
        
        composition_words = [
            'close-up', 'wide', 'medium', 'establishing', 'overhead',
            'low angle', 'high angle', 'bird\'s eye', 'panoramic', 'portrait',
            'landscape', 'split', 'symmetrical', 'depth of field',
            'rule of thirds', 'centered', 'leading lines', 'negative space',
        ]
        comp_hits = sum(1 for w in composition_words if w in prompt_lower)
        if comp_hits >= 2:
            score += 0.10
        elif comp_hits >= 1:
            score += 0.08
        else:
            score += 0.02
        
        _generic_words = {
            'person', 'thing', 'object', 'item', 'stuff', 'someone', 'something',
            'area', 'place', 'part', 'aspect', 'element', 'factor', 'point',
            'people', 'group', 'scene', 'image', 'picture', 'photo',
        }
        keyword_set = set(k.strip().lower() for k in keywords if k.strip())
        generic_count = len(keyword_set & _generic_words)
        if generic_count >= 3:
            score -= 0.15
        elif generic_count >= 2:
            score -= 0.10
        elif generic_count >= 1:
            score -= 0.05

        _meaningful_keywords = [k.strip().lower() for k in keywords if k.strip() and k.strip().lower() not in _generic_words]
        if len(_meaningful_keywords) < 4:
            score -= 0.10
        elif len(_meaningful_keywords) < 6:
            score -= 0.05

        seen_kw = set()
        dup_count = 0
        for kw in keyword_set:
            if kw in seen_kw:
                dup_count += 1
            seen_kw.add(kw)
        if dup_count >= 2:
            score -= 0.08
        elif dup_count >= 1:
            score -= 0.04
        
        # 惩罚纯模板化prompt：如果prompt只包含通用模板词而无具体场景描述
        _template_only_words = {
            'geopolitical', 'cinematic lighting', 'film grain', 'documentary',
            'photorealistic', 'raw photo', 'dslr', 'masterpiece', 'best quality',
            'ultra detailed', '8k', 'high resolution', 'dramatic lighting',
            'natural lighting', 'soft ambient', 'balanced composition',
        }
        _concrete_scene_words = {
            'office', 'building', 'street', 'room', 'courtroom', 'military base',
            'border', 'refugee', 'protest', 'election', 'stock exchange',
            'bank', 'factory', 'hospital', 'school', 'market', 'port',
            'harbor', 'airport', 'prison', 'palace', 'parliament', 'war zone',
            'battlefield', 'oil refinery', 'desert', 'forest', 'ocean',
            'leader', 'soldier', 'diplomat', 'crowd', 'refugees', 'workers',
            'ai', 'algorithm', 'computer', 'screen', 'code', 'data',
            'chart', 'money', 'cash', 'wallet', 'document', 'contract',
        }
        prompt_lower_for_template = prompt_en.lower()
        template_hits = sum(1 for w in _template_only_words if w in prompt_lower_for_template)
        concrete_hits = sum(1 for w in _concrete_scene_words if w in prompt_lower_for_template)
        if template_hits >= 4 and concrete_hits == 0:
            score -= 0.15  # 纯模板无具体场景，大幅扣分
        elif template_hits >= 3 and concrete_hits == 0:
            score -= 0.10
        elif concrete_hits >= 2:
            score += 0.08  # 有具体场景描述，加分

        return round(max(0.0, min(1.0, score)), 2)

    _TONE_VARIANTS = {
        '紧张': {
            '战争|战斗|导弹|坦克|武装|枪杆|军心|倒戈': '紧张, 危急',
            '石油|矿产|能源|油价|金山|肥差|利益': '紧张, 贪婪',
            '制裁|安理会|否决权|国际|外交|谈判': '紧张, 压抑',
            '审判|海牙|逮捕|流亡|后路|崩盘': '紧张, 绝望',
            '妻子|夫人|厉害|铁桶|关系网': '紧张, 阴沉',
            '反对派|选票|选举|透明|过渡': '紧张, 动荡',
            '难民|边境|冲垮|底层|食品': '紧张, 悲凉',
            '博弈|棋局|筹码|赌|牌': '紧张, 算计',
            '平衡|稳定|喘息|拉锯|维持': '紧张, 沉闷',
            '救|救赎|深思|问题': '紧张, 思辨',
            '希望|出路|机遇|转机|曙光|突破': '冷静, 坚定',
            '建议|应该|保持|稳住|理性|冷静': '冷静, 审慎',
        },
        '緊張': {
            '戰爭|戰鬥|導彈|坦克|武裝|軍心|倒戈': '緊張, 危急',
            '石油|礦產|能源|油價|金山|肥差|利益': '緊張, 貪婪',
            '制裁|安理會|否決權|國際|外交|談判': '緊張, 壓抑',
            '審判|海牙|逮捕|流亡|後路|崩盤': '緊張, 絕望',
            '難民|邊境|底層': '緊張, 悲涼',
            '博弈|棋局|籌碼': '緊張, 算計',
            '希望|出路|機遇|轉機': '冷靜, 堅定',
        },
        '严肃': {
            '经济|金融|股市|崩盘|危机': '严肃, 冷峻',
            '法律|审判|法庭|判决|司法': '严肃, 庄重',
            '调查|报告|数据|研究|分析': '严肃, 审慎',
            '历史|纪念|回顾|反思|教训': '严肃, 沉思',
            '责任|追责|问责|监管|合规': '严肃, 凛然',
            '建议|应该|保持|理性': '严肃, 理性',
        },
        '嚴肅': {
            '經濟|金融|股市|崩盤|危機': '嚴肅, 冷峻',
            '法律|審判|法庭|判決|司法': '嚴肅, 莊重',
            '調查|報告|數據|研究|分析': '嚴肅, 審慎',
        },
        '悲壮': {
            '牺牲|殉难|英雄|烈士|捐躯': '悲壮, 崇高',
            '灾难|地震|洪水|疫情|伤亡': '悲壮, 无助',
            '流离|难民|逃亡|流亡|背井': '悲壮, 凄凉',
            '抵抗|抗争|坚守|不屈|奋战': '悲壮, 壮烈',
        },
        '激昂': {
            '胜利|突破|成就|夺冠|成功': '激昂, 自豪',
            '革命|起义|反抗|推翻|变革': '激昂, 热血',
            '科技|创新|发现|发明|进步': '激昂, 振奋',
            '崛起|复兴|腾飞|跨越|腾跃': '激昂, 雄壮',
        },
        '温馨': {
            '家庭|团聚|亲情|温暖|关怀': '温馨, 柔和',
            '救援|互助|善举|慈善|捐助': '温馨, 感动',
            '丰收|庆祝|节日|欢聚|喜悦': '温馨, 喜悦',
            '成长|教育|陪伴|守护|呵护': '温馨, 宁静',
        },
        '沉重': {
            '死亡|逝去|告别|哀悼|悼念': '沉重, 悲痛',
            '失败|挫折|困境|低谷|崩溃': '沉重, 压抑',
            '损失|代价|牺牲|付出|承受': '沉重, 无奈',
            '反思|忏悔|自责|悔恨|遗憾': '沉重, 愧疚',
        },
        '冷静': {
            '分析|理性|数据|研究|客观': '冷静, 理性',
            '建议|策略|方案|规划|应对': '冷静, 务实',
            '希望|机遇|转机|出路|曙光': '冷静, 坚定',
        },
    }

    def _diversify_visual_tone(self, description, base_tone, shot_index=-1, total_shots=0):
        """根据描述文本和叙事位置差异化视觉基调
        
        改进：
        1. 匹配描述文本中的关键词选择变体
        2. 尾部分镜允许正向情绪转折（冷静/坚定）
        3. 避免所有分镜都以同一基调前缀开头
        """
        if not base_tone:
            return '严肃'
        variants = self._TONE_VARIANTS.get(base_tone)
        if not variants:
            return base_tone
        
        # 优先按描述文本关键词匹配
        for pattern, variant in variants.items():
            if re.search(pattern, description):
                return variant
        
        # 尾部分镜（最后20%）允许情绪转折
        if total_shots > 3 and shot_index >= 0:
            tail_threshold = int(total_shots * 0.8)
            if shot_index >= tail_threshold:
                # 检查描述中是否有建议/理性/出路等正向信号
                positive_signals = ['建议', '应该', '保持', '理性', '冷静', '稳住', 
                                   '出路', '希望', '机遇', '转机', '曙光', '准备',
                                   '保险', '储蓄', '存款', '后路', '退路']
                if any(s in description for s in positive_signals):
                    return '冷静, 坚定'
        
        # 兜底：按hash轮换
        tones = list(variants.values())
        return tones[hash(description) % len(tones)]

    def _extract_shot_theme_elements(self, shot_text, global_elements):
        if not shot_text:
            return []

        semantic_map = {
            '地产': ['房', '楼', '建筑', '楼盘', '物业', '土地'],
            '财富': ['钱', '资产', '富豪', '身价', '亿万', '财富', '资本'],
            '债务': ['债', '欠', '贷款', '负债', '资金链', '违约'],
            '风险': ['危险', '危机', '崩塌', '断裂', '凶险'],
            '法律': ['法', '刑', '逮捕', '调查', '审判', '违规', '追责'],
            '科技': ['技术', 'AI', '人工智能', '数字化', '芯片'],
            '农业': ['农', '养殖', '种植'],
            '商业': ['商', '市场', '竞争', '投资', '并购'],
            '权力': ['权', '控制', '掌控', '政权'],
            '军事': ['军', '武', '战', '士兵', '将领', '武装'],
            '政治': ['政治', '总统', '政府', '选举', '反对派'],
            '经济': ['经济', '金融', '股票', '石油', '制裁', '投资', '杠杆', '资金', '崩盘', '裁员', '就业', '失业', '工资', '存款', '消费'],
            '外交': ['外交', '谈判', '国际', '盟友', '否决权'],
            '社会': ['社会', '民生', '民众', '底层', '柴米油盐', '保险', '养老'],
            '能源': ['石油', '矿产', '油价', '能源'],
            '就业': ['就业', '岗位', '裁员', '失业', '工资', '替代', '自动化'],
        }

        matched_elements = []
        if global_elements:
            for elem in global_elements:
                if elem in shot_text:
                    matched_elements.append(elem)
                    continue
                keywords = semantic_map.get(elem, [])
                if any(kw in shot_text for kw in keywords):
                    matched_elements.append(elem)

        # 如果全局元素匹配不足2个，且全局元素总数<=3，直接继承所有全局元素
        # 这确保了像"经济"、"AI"这样的全局性主题不会因为不在某句配音中而丢失
        if global_elements and len(matched_elements) < 2 and len(global_elements) <= 3:
            for elem in global_elements:
                if elem not in matched_elements:
                    matched_elements.append(elem)

        if not matched_elements:
            dynamic_keywords = []
            concept_patterns = [
                ('战争', ['战争', '戰爭', '战斗', '軍事', '军事', '导弹', '坦克']),
                ('政治', ['政治', '总统', '總統', '政府', '选举', '選舉', '权力', '政权']),
                ('经济', ['经济', '經濟', '金融', '股票', '投资', '投資', '制裁', '杠杆', '资金', '裁员', '就业']),
                ('外交', ['外交', '谈判', '談判', '制裁', '国际', '國際', '否决权']),
                ('军事', ['军队', '軍隊', '武装', '武裝', '军官', '軍官', '士兵', '军方']),
                ('社会', ['社会', '社會', '民生', '抗议', '抗議', '示威', '底层']),
                ('科技', ['科技', '技术', '技術', '人工智能', 'AI', '芯片', '算法', '数字化']),
                ('能源', ['石油', '天然气', '能源', '矿产', '礦產']),
                ('司法', ['审判', '法院', '海牙', '司法', '逮捕']),
                ('生存', ['生存', '保险', '防线', '后路', '退路', '柴米油盐', '储蓄']),
                ('就业', ['就业', '岗位', '裁员', '失业', '替代', '自动化']),
            ]
            for concept, patterns in concept_patterns:
                if any(p in shot_text for p in patterns):
                    dynamic_keywords.append(concept)
            matched_elements = dynamic_keywords[:5]

        return matched_elements[:3]


    def _infer_shot_content_type(self, shot_text, global_content_type):
        """根据分镜文本推断更精准的内容类型
        
        当全局content_type过于宽泛（如"社会民生"）时，
        根据分镜文本中的关键词推断更具体的子类型，
        使prompt生成能匹配更准确的视觉场景。
        """
        if not shot_text:
            return global_content_type
        
        _SHOT_TYPE_PATTERNS = [
            ('财经商业', ['股票', '投资', '杠杆', '资金', '崩盘', '金融', '经济', '通胀', '制裁',
                         '现金流', '存款', '房贷', '消费', '收入', '工资', '储蓄', '退休']),
            ('科技科普', ['AI', '人工智能', '算法', '芯片', '数字化', '自动化', '编程', '翻译',
                         '设计', '机器人', '互联网', '数据', '替代', '岗位']),
            ('军事分析', ['战争', '导弹', '坦克', '武装', '军方', '军队', '士兵', '军官',
                         '军事', '核武', '防空']),
            ('政治分析', ['总统', '政府', '选举', '反对派', '政权', '权力', '执政',
                         '政治', '否决权', '宪政']),
            ('外交分析', ['外交', '谈判', '国际', '盟友', '安理会', '制裁',
                         '邻国', '博弈', '地缘']),
        ]
        
        for subtype, keywords in _SHOT_TYPE_PATTERNS:
            if any(kw in shot_text for kw in keywords):
                return subtype
        
        return global_content_type

    def create_new_shot(self, shot_id, start_time, end_time, sentence, content_type, core_theme='', visual_tone='', theme_elements=None):
        """创建新分镜"""
        if theme_elements is None:
            theme_elements = []
        shot_duration = end_time - start_time
        
        # 确保时长不小于最小分镜时长
        if shot_duration < 1.0:
            shot_duration = 1.0
            end_time = start_time + shot_duration
        
        # 清理句子，确保语义清晰
        cleaned_sentence = re.sub(r'[\s\n\r]+', ' ', sentence).strip()
        
        # 确保繁体字转为简体
        cleaned_sentence = _ensure_simplified_chinese(cleaned_sentence)
        
        # 根据分镜文本推断更精准的内容类型（覆盖全局content_type）
        shot_content_type = self._infer_shot_content_type(cleaned_sentence, content_type)
        if shot_content_type != content_type:
            self.log(f"   📂 分镜{shot_id+1} 内容类型细化: 「{content_type}」→「{shot_content_type}」")
            content_type = shot_content_type
        
        # ASR纠错安全网：确保_COMMON_ASR_ERROR_DICT纠错一定生效
        for wrong, correct in sorted(_COMMON_ASR_ERROR_DICT.items(), key=lambda x: len(x[0]), reverse=True):
            if wrong in cleaned_sentence:
                cleaned_sentence = cleaned_sentence.replace(wrong, correct)
        
        # ASR动态纠错：基于LLM主题元素的编辑距离纠错
        if theme_elements:
            dynamic_entities = set()
            for elem in theme_elements:
                if elem and len(elem) >= 2:
                    dynamic_entities.add(elem)
            if core_theme and len(core_theme) >= 2:
                for part in re.split(r'[，、,的与和及]', core_theme):
                    p = part.strip()
                    if p and len(p) >= 2:
                        dynamic_entities.add(p)
            if dynamic_entities:
                cleaned_sentence = _auto_correct_asr(cleaned_sentence, dynamic_entities)
        
        # 清洗和修正文本，修正错别字和语句不通顺的地方
        cleaned_sentence = self.clean_text(cleaned_sentence)
        
        # 从description中提取画面构思（如果包含）
        # description格式：配音内容 + 画面构思 + 视觉元素
        has_pregenerated = (hasattr(self, '_pregenerated_prompts') 
                           and shot_id in self._pregenerated_prompts 
                           and self._pregenerated_prompts.get(shot_id))
        description_parts = self._parse_description(cleaned_sentence, skip_llm_inference=has_pregenerated)
        
        # 添加核心主题和视觉基调到描述中
        # 优先级：传入的参数 > 用户在高级设置中输入的
        user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
        user_custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
        
        # 使用大模型分析得到的主题/基调（如果有），否则使用用户输入的
        effective_theme = core_theme if core_theme else user_custom_theme
        effective_visual_tone = visual_tone if visual_tone else user_custom_visual_tone
        
        if effective_theme:
            description_parts['custom_theme'] = effective_theme
        if effective_visual_tone:
            description_parts['custom_visual_tone'] = effective_visual_tone
        if theme_elements:
            validated_elements = []
            for elem in theme_elements:
                if not elem or len(elem) < 2:
                    continue
                if elem in cleaned_sentence or elem in (effective_theme or ''):
                    validated_elements.append(elem)
                elif len(elem) >= 2:
                    _has_substring_match = False
                    for i in range(len(elem) - 1):
                        if elem[i:i+2] in cleaned_sentence:
                            _has_substring_match = True
                            break
                    if _has_substring_match:
                        validated_elements.append(elem)
            if validated_elements != theme_elements:
                removed = [e for e in theme_elements if e not in validated_elements]
                if removed:
                    self.log(f"   🔍 分镜{shot_id+1} 过滤无关主题元素: {removed}")
            theme_elements = validated_elements if validated_elements else theme_elements
            description_parts['theme_elements'] = theme_elements
        
        # 视觉基调差异化：根据每个分镜的配音内容，将全局基调细分为更精准的子基调
        # 这是唯一调用_diversify_visual_tone的地方，确保差异化逻辑只执行一次
        original_visual_tone = effective_visual_tone
        if hasattr(self, '_diversify_visual_tone') and effective_visual_tone:
            _total_shots = getattr(self, '_total_shot_count', 0)
            diversified = self._diversify_visual_tone(cleaned_sentence, effective_visual_tone, shot_index=shot_id, total_shots=_total_shots)
            if diversified != effective_visual_tone:
                self.log(f"   🎨 分镜{shot_id+1} 基调差异化: 「{original_visual_tone}」→「{diversified}」")
                effective_visual_tone = diversified
                description_parts['custom_visual_tone'] = effective_visual_tone
        
        # 检查用户选择的提示词类型
        prompt_type = "SD提示词"
        if hasattr(self, 'prompt_type_var'):
            prompt_type = self.prompt_type_var.get()
        
        if hasattr(self, '_pregenerated_prompts') and shot_id in self._pregenerated_prompts and self._pregenerated_prompts.get(shot_id):
            prompt_en = self._pregenerated_prompts[shot_id]
        else:
            if prompt_type == "ARV写实提示词":
                prompt_en = self._generate_arv_prompt(description_parts, content_type, shot_id)
            else:
                prompt_en = self._generate_sd_prompt(description_parts, content_type, shot_id)
        
        if not prompt_en or len(prompt_en.strip()) < 10:
            self.log(f"⚠️ 分镜{shot_id+1} 提示词为空或过短，尝试重新生成")
            dubbing_text = description_parts.get('dubbing', '')
            if dubbing_text:
                prompt_en = self._generate_prompt_with_llm(
                    dubbing_text, content_type,
                    prompt_type=prompt_type,
                    core_theme=effective_theme,
                    visual_tone=effective_visual_tone,
                    theme_elements=theme_elements,
                    visual_style=description_parts.get('visual_style', ''),
                    shot_index=shot_id
                )
            if not prompt_en or len(prompt_en.strip()) < 10:
                prompt_en = self._fallback_generate_prompt(
                    description_parts.get('dubbing', ''), content_type, prompt_type,
                    effective_theme, effective_visual_tone, theme_elements
                )
        
        prompt_quality = self._calculate_prompt_quality(prompt_en, description_parts.get('dubbing', ''))
        optimized_prompt = prompt_en

        # 安全网：如果清洗后prompt_en仍含中文，先尝试翻译移除，再使用回退生成
        if re.search(r'[\u4e00-\u9fff]', optimized_prompt):
            chinese_matches = re.findall(r'[\u4e00-\u9fff]+', optimized_prompt)
            for cm in chinese_matches:
                en_trans = self._translate_to_english(cm)
                if en_trans:
                    optimized_prompt = optimized_prompt.replace(cm, en_trans)
                else:
                    optimized_prompt = optimized_prompt.replace(cm, '')
            optimized_prompt = re.sub(r',\s*,', ',', optimized_prompt)
            optimized_prompt = re.sub(r'^\s*,|,\s*$', '', optimized_prompt)
        if re.search(r'[\u4e00-\u9fff]', optimized_prompt):
            dubbing_text = description_parts.get('dubbing', '')
            if dubbing_text:
                fallback = self._analyze_and_generate_sd_prompt(dubbing_text, content_type,
                    theme_elements=theme_elements, shot_index=shot_id)
                if fallback and not re.search(r'[\u4e00-\u9fff]', fallback):
                    optimized_prompt = fallback
                    prompt_quality = self._calculate_prompt_quality(optimized_prompt, dubbing_text)

        prompt_quality = self._calculate_prompt_quality(optimized_prompt, description_parts.get('dubbing', ''))
        quality_retries = 0
        max_quality_retries = 2
        min_prompt_words = 5
        while (prompt_quality < 0.4 or len(optimized_prompt.split(',')) < min_prompt_words) and quality_retries < max_quality_retries:
            dubbing_text = description_parts.get('dubbing', '')
            if dubbing_text and quality_retries == 0 and is_llm_available():
                retry_prompt = self._generate_prompt_with_llm(
                    dubbing_text, content_type,
                    prompt_type=prompt_type,
                    core_theme=effective_theme,
                    visual_tone=effective_visual_tone,
                    theme_elements=theme_elements,
                    visual_style=description_parts.get('visual_style', ''),
                    shot_index=shot_id
                )
                if retry_prompt and len(retry_prompt.strip()) > 10:
                    retry_quality = self._calculate_prompt_quality(retry_prompt, dubbing_text)
                    if retry_quality > prompt_quality:
                        optimized_prompt = retry_prompt
                        prompt_quality = retry_quality
                        self.log(f"   📈 分镜{shot_id+1} 质量提升: {prompt_quality:.2f} → {retry_quality:.2f}")
                        quality_retries += 1
                        continue
            if dubbing_text:
                fallback = self._analyze_and_generate_sd_prompt(dubbing_text, content_type,
                    custom_theme=effective_theme, custom_visual_tone=effective_visual_tone,
                    theme_elements=theme_elements, shot_index=shot_id)
                if fallback and not re.search(r'[\u4e00-\u9fff]', fallback):
                    fb_quality = self._calculate_prompt_quality(fallback, dubbing_text)
                    if fb_quality > prompt_quality:
                        optimized_prompt = fallback
                        prompt_quality = fb_quality
            quality_retries += 1

        hallucinated_names = self._detect_hallucinated_names(optimized_prompt, cleaned_sentence)
        if hallucinated_names:
            for name in hallucinated_names:
                optimized_prompt = re.sub(r'\b' + re.escape(name) + r'\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bbetween\s+and\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bof\s+on\b', 'on', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bwith\s+and\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bfrom\s+to\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\band\s*,', ',', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r',\s*\band\s+', ', ', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'(^|[\s,(])-\w{2,}', r'\1', optimized_prompt)
            optimized_prompt = re.sub(r'\b\w*ousne\b', '', optimized_prompt)
            optimized_prompt = re.sub(r'\b\w*icne\b', '', optimized_prompt)
            optimized_prompt = re.sub(r'\b\w*fulne\b', '', optimized_prompt)
            optimized_prompt = re.sub(r'\b\w*lessne\b', '', optimized_prompt)
            optimized_prompt = re.sub(r'\bemphas\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\b\w*ominou\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\b\w*debri\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bof\s+and\b', '', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\bof\s+(\w+ing)\b', r'\1', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'\b(?:of|in|at|on|for|to|from|by|with)\s*,', ',', optimized_prompt, flags=re.IGNORECASE)
            optimized_prompt = re.sub(r'  +', ' ', optimized_prompt)
            optimized_prompt = re.sub(r'\s+,', ',', optimized_prompt)
            optimized_prompt = re.sub(r',\s*,', ',', optimized_prompt)
            optimized_prompt = re.sub(r'^\s*,|,\s*$', '', optimized_prompt)
            prompt_quality = self._calculate_prompt_quality(optimized_prompt, description_parts.get('dubbing', ''))
        
        optimized_prompt = re.sub(r'\(\s*:\s*[\d.]+\s*\)', '', optimized_prompt)
        optimized_prompt = re.sub(r'\(\s*\)', '', optimized_prompt)
        def _fix_semi_empty_final(t):
            def _repl(m):
                kw = m.group(1).strip()
                wt = m.group(2)
                if len(kw) <= 1:
                    return ''
                return f'({kw}:{wt})'
            return re.sub(r'\(\s+([a-zA-Z][a-zA-Z\s]*?)\s*:\s*([\d.]+)\s*\)', _repl, t)
        optimized_prompt = _fix_semi_empty_final(optimized_prompt)
        optimized_prompt = re.sub(r'[。！？、；：]', ',', optimized_prompt)
        optimized_prompt = re.sub(r'[，]', ',', optimized_prompt)
        optimized_prompt = re.sub(r'  +', ' ', optimized_prompt)
        optimized_prompt = re.sub(r'\s+,', ',', optimized_prompt)
        optimized_prompt = re.sub(r',\s*,', ',', optimized_prompt)
        optimized_prompt = re.sub(r'^\s*,|,\s*$', '', optimized_prompt)
        optimized_prompt = optimized_prompt.strip()
        
        def _strip_quality_tags_for_compare(p):
            _q = ['masterpiece', 'best quality', 'RAW photo', 'raw photo', 'photorealistic',
                  'ultra detailed', '8k', '8K', 'HDR', 'DSLR', 'high resolution',
                  'cinematic lighting', 'film grain', 'professional photography',
                  'documentary photography', 'photojournalism', 'high quality']
            t = p.lower()
            for q in _q:
                t = re.sub(r',?\s*\(' + re.escape(q.lower()) + r'(?::[\d.]+)?\)\s*,?', ',', t)
                t = re.sub(r',?\s*' + re.escape(q.lower()) + r'\s*,?', ',', t)
            t = re.sub(r',\s*,+', ',', t).strip(', ')
            return t
        
        if hasattr(self, '_recent_scene_keywords'):
            _scene_only = _strip_quality_tags_for_compare(optimized_prompt)
            _current_kws = set(k.strip().lower() for k in _scene_only.split(',') if len(k.strip()) > 2)
            for _prev_id, _prev_kws in self._recent_scene_keywords:
                _overlap = _current_kws & _prev_kws
                _union = _current_kws | _prev_kws
                _jaccard = len(_overlap) / max(1, len(_union))
                if _jaccard > 0.7 and len(_current_kws) >= 3:
                    self.log(f"⚠️ 分镜{shot_id+1} 与分镜{_prev_id+1} 提示词重复度 {_jaccard:.0%}，尝试差异化重新生成")
                    dubbing_text = description_parts.get('dubbing', '')
                    if dubbing_text:
                        _diverse_hint = f"CRITICAL: The previous shot used a very similar scene. You MUST create a COMPLETELY DIFFERENT scene with different camera angle, different location, different focal point. Previous similar keywords to AVOID: {', '.join(list(_overlap)[:8])}\n"
                        _retry_prompt = self._generate_prompt_with_llm(
                            dubbing_text, content_type,
                            prompt_type=prompt_type,
                            core_theme=effective_theme,
                            visual_tone=effective_visual_tone,
                            theme_elements=theme_elements,
                            visual_style=description_parts.get('visual_style', ''),
                            shot_index=shot_id
                        )
                        if _retry_prompt and len(_retry_prompt.strip()) > 10:
                            _retry_scene = _strip_quality_tags_for_compare(_retry_prompt)
                            _retry_kws = set(k.strip().lower() for k in _retry_scene.split(',') if len(k.strip()) > 2)
                            _retry_overlap = _retry_kws & _prev_kws
                            _retry_union = _retry_kws | _prev_kws
                            _retry_jaccard = len(_retry_overlap) / max(1, len(_retry_union))
                            if _retry_jaccard < _jaccard:
                                optimized_prompt = _retry_prompt
                                prompt_quality = self._calculate_prompt_quality(optimized_prompt, dubbing_text)
                                self.log(f"   ✅ 差异化成功，重复度 {_jaccard:.0%} → {_retry_jaccard:.0%}")
                            else:
                                self.log(f"   ⚠️ 重试仍相似 ({_retry_jaccard:.0%})，保留原提示词")
                    break
        
        if not hasattr(self, '_recent_scene_keywords'):
            self._recent_scene_keywords = []
        _scene_for_compare = _strip_quality_tags_for_compare(optimized_prompt)
        _kws_for_compare = set(k.strip().lower() for k in _scene_for_compare.split(',') if len(k.strip()) > 2)
        self._recent_scene_keywords.append((shot_id, _kws_for_compare))
        if len(self._recent_scene_keywords) > 6:
            self._recent_scene_keywords.pop(0)
        
        from decimal import Decimal, ROUND_HALF_UP
        
        start_dec = Decimal(str(start_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        end_dec = Decimal(str(end_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        duration_dec = end_dec - start_dec
        
        # 禁用短分镜强制扩展 - 保持原始语音时长，确保音画同步
        # if duration_dec < Decimal('1.0'):
        #     duration_dec = Decimal('1.0')
        #     end_dec = start_dec + duration_dec
        
        diversified_visual_tone = description_parts.get('custom_visual_tone', effective_visual_tone)

        shot_data = {
            "id": shot_id,
            "start": float(start_dec),
            "end": float(end_dec),
            "duration": float(duration_dec),
            "description": cleaned_sentence,
            "prompt_en": optimized_prompt,
            "image_file": f"shot_{shot_id+1:02d}.png",
            "content_type": content_type,
            "semantic_weight": self.calculate_semantic_weight(description_parts['dubbing']),
            "prompt_quality": prompt_quality,
            "core_theme": effective_theme if effective_theme else "",
            "visual_tone": diversified_visual_tone if diversified_visual_tone else "",
            "theme_elements": theme_elements if theme_elements else []
        }

        sd_model_name = ""
        if hasattr(self, 'model_var'):
            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
        shot_data["negative_prompt"] = self._get_custom_negative_prompt(content_type, description_parts['dubbing'], sd_model_name, shot_id)
        
        return shot_data
    

    def _parse_description(self, description, skip_llm_inference=False):
        """解析description，提取各个部分 - 增强版支持多种格式"""
        
        result = {
            'dubbing': '',
            'semantic': '',
            'visual_concept': '',
            'visual_elements': '',
            'style': ''
        }
        
        cleaned = re.sub(r'\*+', '', description)
        cleaned = re.sub(r'^\s*-\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'[""""]', '', cleaned)
        cleaned = cleaned.strip()
        
        lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
        
        if lines:
            first_line = lines[0]
            if '：' in first_line or ':' in first_line:
                result['dubbing'] = re.sub(r'.*?[:：]\s*', '', first_line)
            else:
                result['dubbing'] = first_line
        
        for line in lines:
            if any(keyword in line for keyword in ['画面构思', '镜头', '展示', '场景', '画面']):
                result['visual_concept'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        for line in lines:
            if any(keyword in line for keyword in ['视觉元素', '元素', '物体', '主体']):
                result['visual_elements'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        for line in lines:
            if any(keyword in line for keyword in ['风格', '纪实', '摄影', '色调']):
                result['style'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        if not skip_llm_inference:
            if not result['visual_concept'] and result['dubbing']:
                result['visual_concept'] = self._infer_visual_concept_from_dubbing(result['dubbing'])
            if not result['visual_elements'] and result['dubbing']:
                result['visual_elements'] = self._infer_visual_elements_from_dubbing(result['dubbing'])
        
        if not result['dubbing']:
            result['dubbing'] = cleaned[:100] if len(cleaned) > 100 else cleaned
        
        return result
    
    # =======================================================================
    # 第五部分：提示词生成 (行 3809-4397)
    # 包含：ARV提示词、SD提示词、LLM提示词
    # =======================================================================

    def _infer_from_dubbing_with_llm(self, dubbing, user_prompt_template, system_prompt):
        """使用大模型从配音内容推断视觉信息（统一方法，消除重复代码）
        
        Args:
            dubbing: 配音文本
            user_prompt_template: 用户提示词模板，包含 {dubbing} 占位符
            system_prompt: 系统提示词
        """
        if not dubbing or len(dubbing.strip()) < 2:
            return ""
        if not is_llm_available():
            return ""
        try:
            model = self._get_current_model()
            if not model:
                model = "gemma3:4b"
            user_prompt = user_prompt_template.format(dubbing=dubbing)
            result_text, _ = call_ollama_single(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                log_callback=self.log,
                num_predict=256,
                num_ctx=1532,
                llm_config=getattr(self, 'current_llm_config', None),
                timeout=Config.API_TIMEOUT_LLM_PROMPT,
                cancel_check=lambda: not self.task_running
            )
            if result_text:
                return result_text.strip()
            return ""
        except Exception:
            return ""
    

    def _infer_visual_concept_from_dubbing(self, dubbing):
        """使用大模型从配音内容智能推断画面构思"""
        return self._infer_from_dubbing_with_llm(
            dubbing,
            user_prompt_template="""根据以下配音文本，构思一个适合的图像画面场景。
要求：
1. 描述一个具体的画面场景，包含主要视觉元素
2. 用英文描述
3. 只返回画面描述，不要其他解释

配音文本：{dubbing}

返回格式：a detailed visual scene description""",
            system_prompt="You are a visual scene designer. Describe a specific visual scene based on the given text."
        )
    

    def _infer_visual_elements_from_dubbing(self, dubbing):
        """使用大模型从配音内容智能推断视觉元素"""
        return self._infer_from_dubbing_with_llm(
            dubbing,
            user_prompt_template="""从以下配音文本中提取所有能够用于图像生成的视觉元素关键词。
要求：
1. 提取具体的人、物、场景、动作等视觉元素
2. 用英文逗号分隔每个关键词
3. 只返回关键词列表，不要其他解释

配音文本：{dubbing}

返回格式：keyword1, keyword2, keyword3""",
            system_prompt="You are a visual element extractor. Extract visual keywords from text."
        )
    

    def _generate_arv_prompt(self, description_parts, content_type, shot_id):
        """生成ARV绝对写实风格提示词 - 使用ARV优化模块，必要时切换大模型"""

        if not ARV_OPTIMIZATION_AVAILABLE:
            self.log("⚠️ ARV优化模块不可用，切换到SD提示词")
            return self._generate_sd_prompt(description_parts, content_type, shot_id)

        dubbing = description_parts.get('dubbing', '')
        core_theme = description_parts.get('custom_theme', '')
        visual_tone = description_parts.get('custom_visual_tone', '')
        theme_elements = description_parts.get('theme_elements', [])

        try:
            self.log(f"🎨 使用ARV绝对写实风格生成提示词")
            return self._generate_arv_format_prompt(description_parts, content_type, shot_id)

        except Exception as e:
            self._log_exception("⚠️ ARV提示词生成失败，切换到SD提示词", e)
            return self._generate_sd_prompt(description_parts, content_type, shot_id)


    def _generate_arv_format_prompt(self, description_parts, content_type, shot_id):
        """生成ARV格式提示词 - 统一走_generate_prompt_with_llm"""
        dubbing = description_parts.get('dubbing', '')
        core_theme = description_parts.get('custom_theme', '')
        visual_tone = description_parts.get('custom_visual_tone', '')
        theme_elements = description_parts.get('theme_elements', [])
        content_type = description_parts.get('content_type', content_type)
        visual_style = description_parts.get('visual_style', '')

        try:
            return self._generate_prompt_with_llm(
                dubbing, content_type,
                prompt_type="ARV写实提示词",
                core_theme=core_theme,
                visual_tone=visual_tone,
                theme_elements=theme_elements,
                visual_style=visual_style
            )
        except Exception as e:
            self._log_exception("⚠️ ARV格式生成失败", e)
            return self._generate_sd_prompt(description_parts, content_type, shot_id)


    def _generate_sd_prompt(self, description_parts, content_type, shot_id):
        """生成SD提示词 - 统一走大模型"""
        dubbing = description_parts['dubbing']
        core_theme = description_parts.get('custom_theme', '')
        visual_tone = description_parts.get('custom_visual_tone', '')
        theme_elements = description_parts.get('theme_elements', [])
        content_type = description_parts.get('content_type', content_type)
        visual_style = description_parts.get('visual_style', '')
        
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            if ARV_PROMPTS_AVAILABLE:
                _mt = "sd15"
                if hasattr(self, 'model_var'):
                    _mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                    try:
                        from video_generator.model_profiles import detect_model_type
                        _mt = detect_model_type(_mn)
                    except Exception:
                        pass
                _user_styles = self.get_selected_styles() if hasattr(self, 'get_selected_styles') else []
                return ARVPromptTemplates.generate_prompt(dubbing, content_type, core_theme, visual_tone, model_type=_mt, user_styles=_user_styles, shot_index=shot_id if isinstance(shot_id, int) else -1)
            return self._analyze_and_generate_sd_prompt(dubbing, content_type,
                custom_theme=core_theme, custom_visual_tone=visual_tone,
                theme_elements=theme_elements, shot_index=shot_id if isinstance(shot_id, int) else -1)

        return self._generate_prompt_with_llm(
            dubbing, content_type,
            prompt_type="SD提示词",
            core_theme=core_theme,
            visual_tone=visual_tone,
            theme_elements=theme_elements,
            visual_style=visual_style
        )
    

    def _clean_prompt_output(self, raw_output, model_type=None):
        """清洗大模型输出的提示词，移除解释性文字和格式污染
        
        支持输出格式:
        - 三阶段格式: 中文语义骨架 || English understanding || SD prompt (优先)
        - 两阶段格式: [understanding] | [prompt] (向后兼容)
        如果检测到对应格式，只提取 SD prompt 部分
        
        Args:
            raw_output: 大模型返回的原始输出
            model_type: 模型类型(sd15/sdxl/flux/sd3)，Flux/SD3保留自然语言描述
            
        Returns:
            清洗后的纯净提示词
        """
        if not raw_output:
            return ""
        
        text = str(raw_output).strip()

        text = re.sub(r'<unused\d+>', '', text)
        text = re.sub(r'[\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0E00-\u0E7F\u0E80-\u0EFF\u1000-\u109F\u10A0-\u10FF\u1100-\u11FF\u3040-\u309F\u30A0-\u30FF\uAC00-\uD7AF]', '', text)
        text = re.sub(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FE0F\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', '', text)
        text = re.sub(r'[\u2300-\u23FF\u27C0-\u27EF\u2980-\u29FF]', '', text)
        text = re.sub(r'[\u0370-\u03FF\u1F00-\u1FFF][\uFE00-\uFE0F]?', '', text)
        text = re.sub(r'\[prompt\s+', '[', text, flags=re.IGNORECASE)
        
        _three_part_format = False
        if '||' in text:
            parts = text.split('||')
            if len(parts) >= 3:
                best_part = ''
                best_score = -1
                for part in parts:
                    p = part.strip().strip(',').strip()
                    if not p:
                        continue
                    score = 0
                    score += len(p)
                    sd_weight_count = len(re.findall(r'\([^)]*:\s*1\.\d+\)', p))
                    score += sd_weight_count * 50
                    comma_keywords = [k.strip() for k in p.split(',') if len(k.strip()) > 2]
                    score += len(comma_keywords) * 5
                    if p.lower() in ('sd prompt', 'prompt', 'english prompt', 'stable diffusion prompt'):
                        score -= 200
                    if score > best_score:
                        best_score = score
                        best_part = p
                if best_part:
                    text = best_part
                else:
                    last_part = parts[-1].strip()
                    if last_part and last_part.lower() not in ('sd prompt', 'prompt', 'english prompt', 'stable diffusion prompt'):
                        text = last_part
                    else:
                        mid_part = parts[-2].strip() if len(parts) >= 3 else ''
                        if mid_part and len(mid_part) > 10:
                            text = mid_part
                        else:
                            first_part = parts[0].strip()
                            text = first_part if first_part and len(first_part) > 10 else ''
                _three_part_format = True
            elif len(parts) == 2:
                last_part = parts[-1].strip()
                if last_part and last_part.lower() not in ('sd prompt', 'prompt', 'english prompt'):
                    text = last_part
                else:
                    text = parts[0].strip()
                _three_part_format = True
        
        # 解析两阶段输出格式: [understanding] | [prompt]
        # 格式1: [some understanding text] | [some prompt text]
        # 格式2: [Understanding]: some text | [Prompt]: some text
        # 格式3: Understanding: some text | Prompt: some text
        # 格式4: bare understanding text | (prompt keywords)  <-- 最常见，LLM经常不写方括号
        
        if not _three_part_format:
            label_pipe_match = re.search(
                r'\[(?:Understanding|understanding|Prompt|prompt)\]\s*:\s*.*?\s*\|\s*\[(?:Understanding|understanding|Prompt|prompt)\]\s*:\s*',
                text, re.IGNORECASE | re.DOTALL
            )
            if label_pipe_match:
                after_match = text[label_pipe_match.end():].strip()
                if after_match and len(after_match) > 10:
                    text = after_match
            else:
                no_bracket_match = re.search(
                    r'(?:Understanding|understanding)\s*:\s*.*?\s*\|\s*(?:Prompt|prompt)\s*:\s*',
                    text, re.IGNORECASE | re.DOTALL
                )
                if no_bracket_match:
                    after_match = text[no_bracket_match.end():].strip()
                    if after_match and len(after_match) > 10:
                        text = after_match
                else:
                    pipe_match = re.search(r'\]\s*\|\s*', text)
                    if pipe_match:
                        after_pipe = text[pipe_match.end():].strip()
                        if after_pipe and len(after_pipe) > 10:
                            text = after_pipe
            
            if '|' in text and not re.search(r'\]\s*\|\s*', text):
                pipe_positions = [m.start() for m in re.finditer(r'\|', text)]
                for pipe_pos in pipe_positions:
                    after_pipe = text[pipe_pos + 1:].strip()
                    has_sd_weight = bool(re.search(r'\([^)]*:\s*1\.\d+\)', after_pipe))
                    has_comma_keywords = len([p for p in after_pipe.split(',') if len(p.strip()) > 2]) >= 3
                    if (has_sd_weight or has_comma_keywords) and len(after_pipe) > 10:
                        text = after_pipe
                        break
        
        # 清除残留的 [Understanding]: 或 [Prompt]: 标签
        text = re.sub(r'\[(?:Understanding|understanding|Prompt|prompt)\]\s*:\s*', '', text, flags=re.IGNORECASE)
        
        # gemma3 推理文本剥离：找到第一个 SD 关键词模式，删除之前的所有推理文本
        # SD 关键词模式: (keyword:1.x) 或 (keyword:1.x), 或纯关键词逗号列表
        sd_pattern = re.search(r'\(\w[^)]*:\s*1\.\d+\)', text)
        if sd_pattern:
            start_pos = sd_pattern.start()
            if start_pos > 0:
                prefix = text[:start_pos]
                if any(kw in prefix.lower() for kw in ['break down', 'craft', 'prompt', 'scene', 'translates',
                    'narration', 'dubbing', 'phrase', 'implies', 'suggests', 'highlights',
                    'describes', 'indicates', 'references', 'depict', 'represent', 'convey',
                    'reasoning', 'step', 'okay', 'let\'s', 'here are', 'what scene',
                    'the audio', 'the line', 'this chinese', 'given the']):
                    text = text[start_pos:]
        
        # 【关键】处理 DeepSeek-R1 等推理模型的思考标签
        # 必须在最前面处理，否则会影响后续清洗逻辑
        # DeepSeek-R1 会输出 <think>...</think> 包裹的思考过程
        if '<think>' in text or '</think>' in text:
            # 移除完整的思考块
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
            # 移除未闭合的思考标签
            text = re.sub(r'</?think>', '', text)
            text = text.strip()
        
        # 处理其他推理模型的思考标签（如 Qwen3 的思考模式）
        if '<|thought|>' in text or '</|thought|>' in text:
            text = re.sub(r'<\|thought\|>.*?</\|thought\|>', '', text, flags=re.DOTALL)
            text = re.sub(r'</?\|thought\|>', '', text)
            text = text.strip()
        
        # 定义需要移除的模式列表
        remove_patterns = [
            r'^Here[\'\'\']?s a prompt[^.]*\.\s*',
            r'^Here is a prompt[^.]*\.\s*',
            r'^Based on[^.]*[,，]\s*',
            r'^The following is[^.]*\.\s*',
            r'^I[\'\'\']?ll generate[^.]*\.\s*',
            r'^Let me[^.]*\.\s*',
            r'^Sure[，,.]?\s*',
            r'^Of course[，,.]?\s*',
            r'^Certainly[，,.]?\s*',
            r'^Okay[,.]?\s*',
            r'^Step\s+\d+\s*[:：]\s*.*?(?=Step\s+\d+|---|\[prompt\]|\(Maduro|\(Silvia|\(Military|\(China|\(Russia|\(UN|\(Latin|\(Venezuela|\(Maduro|\()[\s]*',
            r'Step\s+\d+\s*[:：]\s*[^,()\[\]]+?(?:\.\s*)',
            r'Step\s+\d+\s*[:：]\s*',
            r"Okay,? let'?s (?:break down|analyze|craft|generate)[^.]*\.\s*",
            r"The (?:Chinese |English )?phrase [\"\"「」][^\"\"「」]+[\"\"「」][^.]*\.\s*",
            r'It (?:implies|suggests|signifies|highlights|emphasizes|conveys|lends itself)[^.]*\.\s*',
            r'This (?:dubbing|narration|line|phrase|scene|translates)[^.]*\.\s*',
            r'The narration (?:describes|emphasizes|highlights|indicates|references|suggests)[^.]*\.\s*',
            r'The scene (?:should |needs to |must )?(?:depict|represent|convey|show|visualize)[^.]*\.\s*',
            r'(?:Consider|We need to show|Visual elements should|Here\'s a potential)[^.]*\.\s*',
            r'---\s*\*{0,4}\s*',
            r'\[prompt\]\s*[-–—]?\s*',
            r'\[Prompt\]\s*[-–—]?\s*',
            r'\[A [^]]*\]\s*',
            
            r'^以下[是为][^。！？]*[。！？]?\s*',
            r'^好的[，,。！？]?\s*[^。！？]*[。！？]?\s*',
            r'^请看[^。！？]*[。！？]?\s*',
            r'^根据[^。！？]*[。！？]?\s*',
            r'^基于[^。！？]*[。！？]?\s*',
            
            r'\*{0,2}提示词\*{0,2}[：:]\s*',
            r'【提示词】[：:]?\s*',
            r'提示词[：:]\s*',
            
            r'\n?\*{0,2}补充说明\*{0,2}[：:].*',
            r'\n?【补充说明】[：:].*',
            r'\n?补充说明[：:].*',
            
            r'\n?\*{0,2}解释说明\*{0,2}[：:].*',
            r'\n?【解释说明】[：:].*',
            r'\n?解释说明[：:].*',
            
            r'\n?\*{0,2}更[详细进]*[^。！？]*[。！？]\*{0,2}[：:].*',
            
            r'\n?\*{0,2}备选提示词\*{0,2}[：:].*',
            
            r'\n?\*{0,2}附加说明\*{0,2}[：:].*',
            r'\n?【附加说明】[：:].*',
            
            r'\n?希望[^\n]*[！！。]',
            r'\n?以上[^\n]*[！！。]',
            r'\n?请[^\n]*[！！。]',
            r'\n?感谢[^\n]*[！！。]',
            r'\n?如果[您你][^\n]*[！！。]',
            
            r'\*{2}([^*]+)\*{2}',
            r'\*([^*]+)\*',
            r'#{1,6}\s*',
            
            r'\n?【?场景】?[：:][^。\n]*[。\n]?',
            r'\n?【?元素】?[：:][^。\n]*[。\n]?',
            r'\n?【?風格】?[：:][^。\n]*[。\n]?',
            r'\n?【?氛围】?[：:][^。\n]*[。\n]?',
            r'\n?【?主体】?[：:][^。\n]*[。\n]?',
            r'\n?【?细节】?[：:][^。\n]*[。\n]?',
            
            r'\n?为什么[^\n]*',
            r'\n?進一步[^\n]*',
        ]
        
        # 拦截完整英文句子泄漏（最严重问题）
        # SD提示词应为逗号分隔关键词，完整英文句子是LLM推理文本泄漏
        # 策略：检测含主谓结构的完整句子并移除
        # 但 Flux/SD3 需要自然语言描述，只移除明显的推理/解释性句子
        _is_natural_language_model = model_type in ('flux', 'sd3')
        full_sentence_patterns = [
            r'It\'?s about\s+[^,]*\.\s*',
            r'This (?:is|means|shows|depicts|represents|conveys|illustrates)\s+[^,]*\.\s*',
            r'(?:The|A|An)\s+(?:key|main|primary|important|central|core)\s+(?:message|point|idea|concept|theme|meaning)\s+[^,]*\.\s*',
            r'The line (?:means|suggests|implies|indicates|highlights|emphasizes|conveys)\s+[^,]*\.\s*',
            r'A visual representation of this would be[^,]*\.\s*',
            r'(?:This |The )?(?:line |phrase |idiom )?(?:means|suggests|implies|indicates|highlights|conveys|signifies|emphasizes) that\s+[^,]*\.\s*',
        ]
        if not _is_natural_language_model:
            full_sentence_patterns.extend([
                r'[A-Z][a-z]+(?:,\s*(?:as|but|and|or|not)\s+[a-z]+)*\s+(?:is|are|was|were|has|have|had|will|would|can|could|should|must|does|did)\s+[^,]*\.\s*',
                r'(?:China|Russia|Beijing|Moscow|Venezuela|Maduro),?\s+as\s+a\s+[^,]*\.\s*',
                r'(?:Maduro|Cilia|He|She|They|It) is (?:actively |currently )?(?:building|engaging|offering|standing|examining|distributing|holding|maintaining|attempting|controlling|using|trying|engaging|offering|sitting|negotiating|reinforcing)[^,]*\.\s*',
                r'Maduro\'?s?\s+(?:defenses|control|power|survival|approach|strategy)\s+[^,]*\.\s*',
                r'(?:External |The )?(?:sanctions|pressure|situation|problem|issue)\s+(?:are|is)\s+(?:a\s+)?(?:Liabilities?|chronic|slow|persistent)[^,]*\.\s*',
            ])
        for pat in full_sentence_patterns:
            text = re.sub(pat, '', text, flags=re.IGNORECASE)

        # 移除抽象风格标签（LLM自作主张添加的非视觉关键词）
        abstract_style_tags = [
            'investigative journalism', 'geopolitical analysis', 'news broadcast style',
            'news broadcast', 'political analysis', 'geopolitical tension',
            'strategic importance', 'political commentary', 'documentary style',
            'photojournalism', 'editorial photography',
        ]
        for tag in abstract_style_tags:
            text = re.sub(r',?\s*\(' + re.escape(tag) + r'(?::[\d.]+)?\)\s*,?', ',', text, flags=re.IGNORECASE)
            text = re.sub(r',?\s*\b' + re.escape(tag) + r'\b\s*,?', ',', text, flags=re.IGNORECASE)

        # 修复SD语法错误
        # 修复多余句号: "medium shot,." → "medium shot"
        text = re.sub(r',\s*\.\s*', ', ', text)
        # 修复连续句号: "photography." → 移除句号
        text = re.sub(r'\.\s*(?=,|$)', '', text)
        # 修复缺少括号的权重语法: "Cilia Flores:1.2" → "(Cilia Flores:1.2)"
        text = re.sub(r'(?<!\()\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*:\s*(1\.[\d]+)\b(?!\))', r'(\1:\2)', text)
        # 修复无效SD语法: "opposition figures (3):" → 移除
        text = re.sub(r'\b\w+\s+\(\d+\)\s*:\s*', '', text)

        # gemma3 推理文本后置剥离：删除残留的英文完整句子
        # SD提示词是逗号分隔的关键词，不应包含完整英文句子
        # 策略：匹配以大写字母开头、以句号结尾、且不包含SD权重语法的片段
        # Flux/SD3使用自然语言描述，只移除明显的推理标记
        if _is_natural_language_model:
            text = re.sub(r'(?:^|,\s*)[A-Z][a-z][^.]*?(?:reasoning|step \d|let\'s analyze|here are the)[^.]*\.\s*', '', text, flags=re.IGNORECASE)
        else:
            sentence_pattern = re.compile(
                r'(?:^|,\s*)([A-Z][a-z][^.]*?(?:translates|implies|suggests|highlights|describes|indicates|'
                r'references|depicts|represents|conveys|signifies|emphasizes|discusses|mentions|'
                r'refers to|lends itself|breaks down|craft|analyze|reasoning|step \d|'
                r'what scene|the audio|the narration|the line|the phrase|this chinese|given the|'
                r'here are|let\'s|okay|so the)[^.]*\.\s*)',
                re.IGNORECASE
            )
            text = sentence_pattern.sub('', text)
        
        # 清除 "What scene shows this?" 等疑问句
        text = re.sub(r'[^,]*[Ww]hat (?:scene|image|visual|shot) (?:shows|depicts|represents|conveys)[^,]*\?\s*', '', text)
        # 清除 "Reasoning:" 标记后的内容直到下一个逗号
        text = re.sub(r'Reasoning:\s*[^,]*', '', text, flags=re.IGNORECASE)
        # 清除 "directly relates to" 等解释性短语
        text = re.sub(r'[^,]*directly relates to[^,]*', '', text, flags=re.IGNORECASE)
        # 清除 "This highlights" 等解释
        text = re.sub(r'[^,]*This highlights[^,]*', '', text, flags=re.IGNORECASE)
        if not _is_natural_language_model:
            # 清除 "He is distributing" 等描述性句子（Flux/SD3需要这类描述）
            text = re.sub(r'[^,]*(?:He|She|They|It|Maduro|The regime) is (?:distributing|holding|maintaining|attempting|controlling|using|trying)[^,]*\.\s*', '', text)
            # 清除 "Once they lose power" 等叙述性句子
            text = re.sub(r'[^,]*Once (?:they|he|she)[^,]*\.\s*', '', text)
            # 清除 "China, as a creditor" 等解释
            text = re.sub(r'[^,]*as a (?:creditor|leader|result|consequence)[^,]*\.\s*', '', text, flags=re.IGNORECASE)
            # 清除 "A low-ranking soldier" 等描述
            text = re.sub(r'A\s+(?:low-ranking|high-ranking|senior|junior)[^,]*\.\s*', '', text)
        # 清除 "The narrator is questioning" 等
        text = re.sub(r'The narrator is[^,]*\.\s*', '', text, flags=re.IGNORECASE)
        # 清除 "It's describing" 等
        text = re.sub(r'It\'?s (?:describing|saying|posing|referring)[^,]*\.\s*', '', text, flags=re.IGNORECASE)
        # 清除残留的 ** 标记
        text = re.sub(r'\*{2,}', '', text)
        # 清除 " - " 分隔符

        # 【关键】清除所有中文字符 - SD/SDXL模型无法理解中文提示词
        # 如果清洗后仍含中文，说明LLM直接输出了中文配音文本，必须移除
        chinese_chars = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text)
        if chinese_chars:
            # 移除所有中文字符及紧邻的中文标点
            text = re.sub(r'[\u4e00-\u9fff]+[\u3000-\u303f\uff00-\uffef]?', '', text)
            # 清理因移除中文产生的多余逗号和空格
            text = re.sub(r'\s*,\s*,\s*', ', ', text)
            text = re.sub(r'^\s*,\s*', '', text)
            text = re.sub(r'\s*,\s*$', '', text)
            text = text.strip()
        text = re.sub(r'\s*[-–—]\s*$', '', text)
        text = re.sub(r'^\s*[-–—]\s*', '', text)
        
        # 应用所有移除模式
        for pattern in remove_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 处理"关键词补充"、"更精细的提示词"等格式
        # 提取其中的关键词部分
        if '【关键词】' in text:
            match = re.search(r'【关键词】[：:]?\s*([^【\n]+)', text)
            if match:
                text = match.group(1).strip()
        
        # 处理中英文混合的场景描述
        # 如果存在"场景："、"元素："等格式，提取内容
        if re.search(r'[场情元素風格氛围][:：]', text):
            # 尝试提取关键词组合
            parts = []
            for label in ['场景', '元素', '風格', '氛围', '主体', '细节']:
                match = re.search(f'{label}[：:]\\s*([^場元素風格氛圍主体細節\\n]+)', text)
                if match:
                    parts.append(match.group(1).strip().rstrip('。，'))
            if parts:
                text = '，'.join(parts)
        
        # 清理多余的空白和换行
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'^[，,。、：:；;\\s]+', '', text)
        text = re.sub(r'[，,。、：:；;\\s]+$', '', text)
        
        # 主动过滤中文字符（提示词应为纯英文）
        # 先检测是否为中文提示词模式（如果超过50%是中文则保留）
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text.replace(' ', '').replace(',', ''))
        if total_chars > 0 and chinese_chars / total_chars < 0.5:
            # 英文提示词模式：移除残留的中文字符及紧邻的中文标点
            text = re.sub(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', '', text)
            text = re.sub(r'\s*,\s*,\s*', ', ', text)
            text = re.sub(r'^[，,。、：:；;\\s]+', '', text)
            text = re.sub(r'[，,。、：:；;\\s]+$', '', text)
        
        # 处理重复词语（如 "warning – severe – critical – warning – dark – warning..."）
        # 如果同一个词重复出现超过3次，可能是模型输出异常
        words = re.split(r'[，,、\\s–—-]+', text)
        if len(words) > 10:
            # 检测是否有词重复超过3次
            word_count = {}
            for w in words:
                w_lower = w.lower().strip()
                if len(w_lower) > 2:  # 忽略短词
                    word_count[w_lower] = word_count.get(w_lower, 0) + 1
            
            # 如果有词重复超过3次，去重
            if any(c > 3 for c in word_count.values()):
                seen = set()
                unique_words = []
                for w in words:
                    w_lower = w.lower().strip()
                    if w_lower not in seen or len(w_lower) <= 2:
                        unique_words.append(w)
                        if len(w_lower) > 2:
                            seen.add(w_lower)
                text = ', '.join(unique_words)
        
        meaningless_words = ['texture', 'textures', 'textured', 'detailed texture', 'visual texture']
        for w in meaningless_words:
            text = re.sub(r',?\s*\(' + re.escape(w) + r'(?::[\d.]+)?\)\s*,?', ',', text, flags=re.IGNORECASE)
            text = re.sub(r',?\s*\b' + re.escape(w) + r'\b\s*,?', ',', text, flags=re.IGNORECASE)
        text = re.sub(r',\s*,+', ',', text).strip(', ')

        # 修复非法权重值: (keyword:1𒁩) → (keyword:1.3), (keyword:1 dwRes) → (keyword:1.3)
        # SD权重语法中冒号后必须是 1.X 格式的数字，否则替换为默认1.3
        def _fix_corrupted_weights(t):
            def _replace_bad_weight(m):
                keyword = m.group(1).strip()
                weight_str = m.group(2)
                if not keyword or not re.search(r'[a-zA-Z]', keyword):
                    return ''
                try:
                    weight = float(weight_str)
                    if 0.5 <= weight <= 2.0:
                        normalized = f'{weight:.1f}'
                        return f'({keyword}:{normalized})'
                    else:
                        return f'({keyword}:1.3)'
                except (ValueError, TypeError):
                    return f'({keyword}:1.3)'
            return re.sub(r'\(([^)]*?):\s*([^,)]*?)\)', _replace_bad_weight, t)
        text = _fix_corrupted_weights(text)

        _MEANINGLESS_WEIGHT_WORDS = {
            'and', 'or', 'but', 'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'has', 'have', 'had', 'do', 'does', 'did', 'not', 'no', 'nor',
            'this', 'that', 'these', 'those', 'it', 'its', 'as', 'if', 'so',
            'than', 'then', 'very', 'too', 'also', 'just', 'only', 'even',
            'still', 'already', 'yet', 'now', 'here', 'there', 'where', 'when',
            'how', 'what', 'which', 'who', 'whom', 'whose', 'why',
            'can', 'could', 'will', 'would', 'shall', 'should', 'may', 'might',
            'must', 'need', 'into', 'about', 'over', 'under', 'between',
            'through', 'during', 'before', 'after', 'above', 'below',
            'up', 'down', 'out', 'off', 'more', 'most', 'some', 'any',
            'all', 'each', 'every', 'both', 'few', 'many', 'much', 'own',
            'other', 'such', 'same', 'being', 'having', 'doing',
            'however', 'therefore', 'although', 'because', 'since', 'while',
            'unless', 'until', 'whether', 'though', 'else', 'instead',
        }
        def _remove_meaningless_weights(t):
            def _check_weight(m):
                keyword = m.group(1).strip()
                if keyword.lower().strip() in _MEANINGLESS_WEIGHT_WORDS:
                    return ''
                if len(keyword) <= 1:
                    return ''
                if not re.search(r'[a-zA-Z]{2,}', keyword):
                    return ''
                return m.group(0)
            return re.sub(r'\(([^)]*?):\s*([\d.]+)\)', _check_weight, t)
        text = _remove_meaningless_weights(text)

        # 清理截断残留: "Maduro's 3," 或 "3, a general examining" 中的孤立数字3
        # 这是LLM输出被截断后的残留token，常见模式: "xxx 3, yyy" 或 "xxx's 3, yyy"
        text = re.sub(r"\b3\s*,\s*(?=[a-z])", '', text)
        text = re.sub(r"(?:'s\s+)?\b3\b\s*,", ',', text)

        # Fix SD syntax: [text:weight] → (text:weight) - square brackets are NOT weight syntax in SD
        text = re.sub(r'\[([^,\]]+?):([\d.]+)\]', r'(\1:\2)', text)

        # Fix SD syntax: [text | text] alternating syntax → just use first text
        text = re.sub(r'\[([^|\]]+?)\s*\|\s*([^\]]+?)\]', r'\1', text)
        
        # Fix mismatched brackets: (4K] → (4K), [text) → [text]
        # Fix closing ] without opening [
        text = re.sub(r'\(([^)]*?)\]', r'(\1)', text)
        # Fix closing ) without opening (
        text = re.sub(r'\[([^\]]*?)\)', r'[\1]', text)
        
        # Fix unbalanced parentheses in SD weight syntax
        # Remove orphaned opening parentheses: "(keyword" without closing ")"
        # Strategy: find ( that has content but no matching )
        def _fix_unbalanced_parens(t):
            result = []
            paren_stack = []
            i = 0
            while i < len(t):
                if t[i] == '(':
                    paren_stack.append(len(result))
                    result.append('(')
                elif t[i] == ')':
                    if paren_stack:
                        paren_stack.pop()
                        result.append(')')
                    else:
                        pass
                else:
                    result.append(t[i])
                i += 1
            while paren_stack:
                idx = paren_stack.pop()
                result.insert(idx + 1, ')') if idx + 1 <= len(result) else result.append(')')
            return ''.join(result)
        
        text = _fix_unbalanced_parens(text)
        
        # Remove empty parentheses: () or ( :1.2) or (,)
        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'\(\s*:\s*[\d.]+\s*\)', '', text)
        text = re.sub(r'\(\s*,\s*\)', '', text)
        text = re.sub(r'\(\s*:\s*1\.\d+\)', '', text)
        # Fix semi-empty weights: "( diplomat:1.3)" → "(diplomat:1.3)"
        # Remove leading spaces inside weight parens, then drop if keyword too short
        def _fix_semi_empty_weights(t):
            def _replacer(m):
                kw = m.group(1).strip()
                wt = m.group(2)
                if len(kw) <= 1:
                    return ''
                return f'({kw}:{wt})'
            return re.sub(r'\(\s+([a-zA-Z][a-zA-Z\s]*?)\s*:\s*([\d.]+)\s*\)', _replacer, t)
        text = _fix_semi_empty_weights(text)
        
        # Clean LLM leak phrases within prompt text
        text = re.sub(r'\bSD prompt\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bEnglish prompt[:\s]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bStable Diffusion prompt\b', '', text, flags=re.IGNORECASE)
        
        # Clean Chinese punctuation in English prompt
        text = re.sub(r'[、；：。！？]', ',', text)
        text = re.sub(r'[（]', '(', text)
        text = re.sub(r'[）]', ')', text)
        text = re.sub(r'[，]', ',', text)
        
        text = re.sub(r",?\s*'s\s+", ', ', text)
        text = re.sub(r"\b's\b", '', text)
        
        text = re.sub(r'\bbetween\s+and\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bof\s+on\b', 'on', text, flags=re.IGNORECASE)
        text = re.sub(r'\bwith\s+and\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bfrom\s+to\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\band\s*,', ',', text, flags=re.IGNORECASE)
        text = re.sub(r',\s*\band\s+', ', ', text, flags=re.IGNORECASE)
        text = re.sub(r'(^|[\s,(])-\w{2,}', r'\1', text)
        text = re.sub(r'\b\w*ousne\b', '', text)
        text = re.sub(r'\b\w*icne\b', '', text)
        text = re.sub(r'\b\w*fulne\b', '', text)
        text = re.sub(r'\b\w*lessne\b', '', text)
        text = re.sub(r'\bemphas\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\w*ominou\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\w*debri\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bof\s+and\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bof\s+(\w+ing)\b', r'\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(?:of|in|at|on|for|to|from|by|with)\s*,', ',', text, flags=re.IGNORECASE)
        
        # Clean double spaces (LLM output with deleted/missing words)
        text = re.sub(r'  +', ' ', text)
        # Clean orphaned commas after word deletion: "word , word" → "word, word"
        text = re.sub(r'\s+,', ',', text)
        text = re.sub(r',\s*,', ',', text)
        text = re.sub(r'^\s*,|,\s*$', '', text)
        
        if len(text.strip()) < 10:
            fallback = self._generate_fallback_prompt(raw_output)
            if fallback:
                return fallback
            return raw_output.strip()

        _placeholder_patterns = [
            'sd prompt', 'english prompt', 'stable diffusion prompt',
            'english understanding', 'prompt here', 'your prompt',
            'insert prompt', 'prompt goes here',
        ]
        text_lower = text.strip().lower()
        if text_lower in _placeholder_patterns or len(text_lower) < 5:
            fallback = self._generate_fallback_prompt(raw_output)
            if fallback and len(fallback) > 10:
                return fallback
            return raw_output.strip()

        _name_corrections = {
            'Westley': 'Cilia Flores', 'Westylia': 'Cilia Flores',
            'Xaviera': 'Cilia Flores', 'Wesley': 'Cilia Flores',
        }
        for wrong, correct in _name_corrections.items():
            if wrong in text:
                text = text.replace(wrong, correct)

        sd_model_name = ""
        if hasattr(self, 'model_var'):
            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
        text = self._build_final_prompt(text, sd_model_name)

        return text.strip()

    def _extract_understanding(self, raw_output):
        """从LLM原始输出中提取understanding部分，用于场景去重
        
        支持格式:
        - 三阶段: 中文语义骨架 || English understanding || SD prompt
        - 两阶段: [understanding] | [prompt] (向后兼容)
        """
        if not raw_output:
            return ""
        text = str(raw_output).strip()
        understanding = ""
        if '||' in text:
            parts = text.split('||')
            if len(parts) >= 3:
                understanding = parts[1].strip()
            elif len(parts) == 2:
                understanding = parts[0].strip()
        if not understanding:
            pipe_match = re.search(r'\]\s*\|\s*', text)
            if pipe_match:
                before_pipe = text[:pipe_match.start()].strip()
                label_match = re.search(r'\[(?:Understanding|understanding)\]\s*:\s*(.+)', before_pipe, re.DOTALL)
                if label_match:
                    understanding = label_match.group(1).strip()
                else:
                    no_bracket_match = re.search(r'(?:Understanding|understanding)\s*:\s*(.+)', before_pipe, re.IGNORECASE | re.DOTALL)
                    if no_bracket_match:
                        understanding = no_bracket_match.group(1).strip()
                if not understanding and before_pipe.startswith('[') and before_pipe.endswith(']'):
                    understanding = before_pipe[1:-1].strip()
        if understanding:
            understanding = re.sub(r'^(Understanding|understanding)\s*:\s*', '', understanding, flags=re.IGNORECASE).strip()
            understanding = re.sub(r'\[|\]', '', understanding).strip()
        return understanding[:200] if understanding else ""

    def _extract_chinese_skeleton(self, raw_output):
        """从LLM原始输出中提取中文语义骨架部分
        
        格式: 中文语义骨架 || English understanding || SD prompt
        """
        if not raw_output:
            return ""
        text = str(raw_output).strip()
        if '||' in text:
            parts = text.split('||')
            if len(parts) >= 3:
                skeleton = parts[0].strip()
                skeleton = re.sub(r'^\[\d+\]\s*', '', skeleton).strip()
                skeleton = re.sub(r'\[|\]', '', skeleton).strip()
                return skeleton[:150] if skeleton else ""
        return ""

    def _generate_fallback_prompt(self, raw_output):
        """当清洗后提示词为空时，从原始输出中提取最小可用提示词"""
        if not raw_output:
            return ""
        text = str(raw_output).strip()
        pipe_match = re.search(r'\]\s*\|\s*', text)
        if pipe_match:
            after_pipe = text[pipe_match.end():].strip()
        else:
            after_pipe = text
        after_pipe = re.sub(r'<unused\d+>', '', after_pipe)
        after_pipe = re.sub(r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF]', '', after_pipe)
        after_pipe = re.sub(r'^[^,()]*?\.\s*', '', after_pipe)
        sd_keywords = re.findall(r'\([^)]+(?::\s*1\.\d+)\)', after_pipe)
        comma_phrases = [p.strip() for p in after_pipe.split(',') if p.strip() and len(p.strip()) > 2 and not p.strip().startswith(('[', 'The ', 'This ', 'A ', 'An ', 'It '))]
        if sd_keywords or comma_phrases:
            parts = sd_keywords[:3] + comma_phrases[:5]
            return ', '.join(dict.fromkeys(parts))
        return ""
    

    def _build_final_prompt(self, scene_description, sd_model_name=""):
        """拼接最终提示词：质量前缀 + 模型场景描述 + 风格后缀

        根据制图模型类型自动选择对应的质量前缀/后缀格式：
        - SD 1.5: 带权重标记 (masterpiece, best quality:1.2)
        - SDXL:   无权重标记 RAW photo, photorealistic
        - Flux:   无前缀后缀（自然语言）
        - SD3:    无前缀，轻量后缀

        非写实风格（皮克斯、吉卜力、动漫等）自动移除写实关键词。
        动态增强：根据场景语义调整质量前缀强度。
        """
        from video_generator.model_profiles import get_model_profile, detect_model_type

        model_type = detect_model_type(sd_model_name)
        profile = get_model_profile(model_type)
        prefix = profile.get("quality_prefix", "")
        suffix = profile.get("quality_suffix", "")

        user_selected_styles = self.get_selected_styles()
        is_non_realistic = False
        from video_generator.model_profiles import NON_REALISTIC_KEYWORDS
        if user_selected_styles:
            style_text_lower = " ".join(user_selected_styles).lower()
            is_non_realistic = any(kw in style_text_lower for kw in NON_REALISTIC_KEYWORDS)

        if is_non_realistic:
            prefix = re.sub(r',?\s*\(?\s*RAW photo\s*\)?\s*,?', ',', prefix, flags=re.IGNORECASE)
            prefix = re.sub(r',?\s*\(?\s*raw photo\s*\)?\s*,?', ',', prefix, flags=re.IGNORECASE)
            prefix = re.sub(r',?\s*\(?\s*photorealistic(?::[\d.]+)?\)?\s*,?', ',', prefix, flags=re.IGNORECASE)
            prefix = re.sub(r',?\s*\(?\s*documentary style\s*\)?\s*,?', ',', prefix, flags=re.IGNORECASE)
            suffix = re.sub(r',?\s*\(?\s*film grain(?::[\d.]+)?\)?\s*,?', ',', suffix, flags=re.IGNORECASE)
            suffix = re.sub(r',?\s*\(?\s*film grain texture\s*\)?\s*,?', ',', suffix, flags=re.IGNORECASE)
            suffix = re.sub(r',?\s*\(?\s*documentary style\s*\)?\s*,?', ',', suffix, flags=re.IGNORECASE)
            prefix = re.sub(r',\s*,+', ',', prefix).strip(', ')
            suffix = re.sub(r',\s*,+', ',', suffix).strip(', ')

        scene_lower = scene_description.lower()
        if model_type == "sd15":
            _has_person = bool(re.search(r'\(?(?:person|man|woman|girl|boy|portrait|figure|soldier|officer|president|leader|general|doctor|scientist|woman in|man in)[^)]*\)?:\s*1\.\d', scene_lower))
            _has_landscape = bool(re.search(r'(?:landscape|panoramic|aerial|wide angle|establishing shot|skyline|horizon|mountain|ocean|forest)', scene_lower))
            _has_closeup = bool(re.search(r'(?:close-up|close up|detail|macro|tight)', scene_lower))
            
            if _has_person and not _has_landscape:
                if 'best quality' not in prefix.lower():
                    prefix = "(best quality:1.2), " + prefix if prefix else "(best quality:1.2)"
                if 'anatomy' not in prefix.lower():
                    prefix += ", (detailed face:1.1)"
            elif _has_landscape:
                if 'scenic' not in prefix.lower():
                    suffix = (suffix + ", scenic, dramatic atmosphere") if suffix else "scenic, dramatic atmosphere"
            if _has_closeup and _has_person:
                if 'skin detail' not in prefix.lower():
                    prefix += ", (skin detail:1.1), (eye detail:1.1)"

        redundant = [
            "masterpiece", "best quality", "ultra detailed", "8k",
            "photorealistic", "cinematic lighting", "documentary style",
            "film grain", "high quality", "professional photography",
            "RAW photo", "raw photo", "film grain texture",
            "documentary photography", "photojournalism",
            "raw and authentic", "unposed", "candid shot",
            "detailed face", "skin detail", "eye detail",
            "scenic", "dramatic atmosphere",
        ]
        cleaned = scene_description
        cleaned = re.sub(r'\(\s*masterpiece\s*,\s*best\s+quality\s*:\s*[\d.]+\s*\)', '', cleaned, flags=re.IGNORECASE)
        for tag in redundant:
            cleaned = re.sub(r',?\s*\(' + re.escape(tag) + r'(?::[\d.]+)?\)\s*,?', ',', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r',?\s*' + re.escape(tag) + r'\s*,?', ',', cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r'\(\s*,\s*:\s*[\d.]+\s*\)', '', cleaned)
        cleaned = re.sub(r'\(\s*:\s*[\d.]+\s*\)', '', cleaned)
        cleaned = re.sub(r'\(\s*,\s*\)', '', cleaned)
        cleaned = re.sub(r'\(\s*\)', '', cleaned)

        cleaned = re.sub(r',\s*,+', ',', cleaned).strip(', ')

        if model_type in ('flux', 'sd3'):
            if len(cleaned) > 400:
                cleaned = cleaned[:400]
        else:
            if len(cleaned) > 250:
                keywords = [k.strip() for k in cleaned.split(',') if k.strip()]
                if len(keywords) > 20:
                    keywords = keywords[:20]
                    cleaned = ', '.join(keywords)

        parts = []
        if prefix:
            parts.append(prefix)
        if cleaned:
            parts.append(cleaned)
        if suffix:
            parts.append(suffix)

        if model_type in ('flux', 'sd3') and len(parts) > 1:
            # Flux/SD3使用自然语言：如果有质量前缀/后缀，用逗号融入场景描述
            # 避免用句号生硬拼接导致不自然的文本
            if prefix and suffix:
                result = f"{prefix}, {cleaned}, {suffix}"
            elif prefix:
                result = f"{prefix}, {cleaned}"
            elif suffix:
                result = f"{cleaned}, {suffix}"
            else:
                result = cleaned
        else:
            result = ', '.join(parts)
        result = self._validate_sd_syntax(result, model_type)
        return result

    def _validate_sd_syntax(self, prompt, model_type=None):
        """SD语法后处理验证：修复常见语法问题"""
        if not prompt:
            return prompt
        if model_type is None:
            model_type = "sd15"
            if hasattr(self, 'model_var'):
                mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                from video_generator.model_profiles import detect_model_type
                model_type = detect_model_type(mn)

        text = prompt

        text = re.sub(r',\s*\.\s*', ', ', text)
        text = re.sub(r'\.\s*(?=,|$)', '', text)
        text = re.sub(r',\s*,+', ',', text)
        text = re.sub(r'^\s*,\s*', '', text)
        text = re.sub(r'\s*,\s*$', '', text)

        text = re.sub(r'(?<!\()\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*:\s*(1\.[\d]+)\b(?!\))', r'(\1:\2)', text)

        text = re.sub(r'\(\s*\)', '', text)
        text = re.sub(r'\(\s*,\s*\)', '', text)
        text = re.sub(r'\(\s*:\s*[\d.]+\s*\)', '', text)

        text = re.sub(r'\s{2,}', ' ', text)

        text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text, flags=re.IGNORECASE)

        if model_type == 'flux':
            text = re.sub(r'\([^)]*:[\d.]+\)', lambda m: m.group(0).split(':')[0].strip('()'), text)
            text = re.sub(r'\[([^]]*):[\d.]+\]', r'\1', text)
            text = re.sub(r'\(\(([^)]+)\)\)', r'\1', text)
            _flux_generic = {'person', 'thing', 'object', 'item', 'stuff', 'someone', 'something'}
            flux_kws = [k.strip() for k in text.split(',')]
            flux_kws = [k for k in flux_kws if k.lower().strip() not in _flux_generic and len(k.strip()) > 1]
            if flux_kws:
                # 检测是否已包含自然语言句子（句号或长词组）
                has_sentence = any('.' in k or len(k.split()) > 4 for k in flux_kws)
                if has_sentence:
                    # 已有自然语言描述，保持原样，仅用逗号连接
                    text = ', '.join(flux_kws)
                elif len(flux_kws) >= 3:
                    # 纯关键词列表，转为自然语言
                    main_subject = flux_kws[0]
                    details = ', '.join(flux_kws[1:])
                    text = f"A {main_subject}, with {details}"
                else:
                    text = ', '.join(flux_kws)
            if text and not re.match(r'^[A-Z]', text):
                text = text[0].upper() + text[1:] if text else text
            return text.strip(', ')

        _generic_words = {'person', 'thing', 'object', 'item', 'stuff', 'someone', 'something'}
        keywords = [k.strip() for k in text.split(',')]
        seen_bases = set()
        deduped = []
        for kw in keywords:
            kw_stripped = kw.strip()
            if not kw_stripped:
                continue
            base = re.match(r'\(?\s*([^:()]+?)\s*(?::[\d.]+)?\s*\)?$', kw_stripped)
            base_text = base.group(1).strip().lower() if base else kw_stripped.lower()
            if base_text in _generic_words:
                continue
            if base_text not in seen_bases:
                seen_bases.add(base_text)
                deduped.append(kw_stripped)
        text = ', '.join(deduped)

        return text.strip(', ')


    def _fallback_generate_prompt(self, dubbing, content_type, prompt_type="SD提示词", core_theme="", visual_tone="", theme_elements=None):
        if theme_elements is None:
            theme_elements = []
        fallback_parts = {
            'dubbing': dubbing,
            'content_type': content_type,
            'custom_theme': core_theme,
            'custom_visual_tone': visual_tone,
            'theme_elements': theme_elements,
        }
        if prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
            return self._generate_arv_format_prompt(fallback_parts, content_type, 0)
        elif prompt_type == "SD提示词" and ARV_PROMPTS_AVAILABLE:
            _mt = "sd15"
            if hasattr(self, 'model_var'):
                _mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                try:
                    from video_generator.model_profiles import detect_model_type
                    _mt = detect_model_type(_mn)
                except Exception:
                    pass
            _user_styles = self.get_selected_styles() if hasattr(self, 'get_selected_styles') else []
            return ARVPromptTemplates.generate_prompt(dubbing, content_type, core_theme, visual_tone, model_type=_mt, user_styles=_user_styles, shot_index=-1)
        else:
            return self._analyze_and_generate_sd_prompt(dubbing, content_type,
                custom_theme=core_theme, custom_visual_tone=visual_tone,
                theme_elements=theme_elements, shot_index=-1)


    def _generate_prompt_with_llm(self, dubbing, content_type, prompt_type="SD提示词", core_theme="", visual_tone="", theme_elements=None, visual_style="", original_dubbing="", full_text="", shot_index=-1):
        """使用大模型生成提示词 - 只给规则不给案例，让大模型自主创作"""
        if theme_elements is None:
            theme_elements = []
        
        if not is_llm_available():
            self.log("⚠️ 大模型不可用，尝试重启Ollama服务...")
            try:
                from video_generator.ollama_client import restart_ollama_service
                if restart_ollama_service(log_callback=self.log):
                    set_ollama_available_global(True)
                    self.log("✅ Ollama服务已重启，继续生成提示词")
                    time.sleep(2)
                else:
                    self.log("❌ Ollama服务重启失败，使用内置逻辑生成提示词")
                    return self._fallback_generate_prompt(dubbing, content_type, prompt_type, core_theme, visual_tone, theme_elements)
            except Exception:
                self.log("❌ 重启Ollama异常，使用内置逻辑生成提示词")
                return self._fallback_generate_prompt(dubbing, content_type, prompt_type, core_theme, visual_tone, theme_elements)
            
        model = self._get_current_model()
        if not model:
            model = "gemma3:4b"
        
        template_params = {
            "content_type": content_type or "未指定类型",
            "core_theme": core_theme or "未指定",
            "visual_style": visual_style,
            "visual_tone": visual_tone or "",
            "theme_elements": ", ".join(theme_elements) if theme_elements else "根据配音内容确定",
            "dubbing": dubbing,
            "visual_narrative_strategy": getattr(self, '_visual_narrative_strategy', ''),
            "sd_model_name": "",
        }
        
        context_hint = ""
        if full_text and isinstance(full_text, str) and len(full_text) > 50:
            summary = full_text[:300] if len(full_text) > 300 else full_text
            context_hint += f"FULL AUDIO CONTEXT (use this to understand the overall narrative):\n{summary}\n\n"
        if hasattr(self, '_shot_texts_for_context') and isinstance(dubbing, str):
            shot_texts = self._shot_texts_for_context
            try:
                idx = shot_index if shot_index >= 0 else (shot_texts.index(dubbing) if dubbing in shot_texts else -1)
                if idx >= 0:
                    if hasattr(self, '_pregenerated_prompts_for_context'):
                        prev_prompts = [self._pregenerated_prompts_for_context[j] for j in range(max(0, idx-2), idx) if j in self._pregenerated_prompts_for_context and self._pregenerated_prompts_for_context[j]]
                        if prev_prompts:
                            context_hint += f"AVOID: {', '.join(prev_prompts[-2:])}\n"
                        
                        # 提取已用背景关键词，防止背景同质化
                        _BACKGROUND_KEYWORDS = [
                            'palace interior', 'dimly lit office', 'mahogany table', 'overcast sky',
                            'palace', 'office', 'courtroom', 'military base', 'border crossing',
                            'rural landscape', 'port', 'harbor', 'diplomatic venue', 'refugee camp',
                            'oil facility', 'parliament hall', 'prison corridor', 'airport tarmac',
                            'hotel lobby', 'city street', 'war room', 'bunker', 'balcony',
                        ]
                        used_backgrounds = []
                        for j in range(max(0, idx - 6), idx):
                            if j in self._pregenerated_prompts_for_context and self._pregenerated_prompts_for_context[j]:
                                prev_p_lower = self._pregenerated_prompts_for_context[j].lower()
                                for bg in _BACKGROUND_KEYWORDS:
                                    if bg in prev_p_lower and bg not in used_backgrounds:
                                        used_backgrounds.append(bg)
                        if used_backgrounds:
                            context_hint += f"USED BACKGROUNDS (do NOT reuse): {', '.join(used_backgrounds[-5:])}\n"
                    
                    if hasattr(self, '_pregenerated_understandings_for_context'):
                        prev_understandings = [self._pregenerated_understandings_for_context[j] for j in range(max(0, idx-3), idx) if j in self._pregenerated_understandings_for_context and self._pregenerated_understandings_for_context[j]]
                        if prev_understandings:
                            context_hint += f"PREVIOUS SCENES (do NOT repeat similar scenes):\n"
                            for i, u in enumerate(prev_understandings[-3:]):
                                context_hint += f"  - {u}\n"
                    
                    total_shots = len(shot_texts)
                    if idx == 0:
                        context_hint += "Position: OPENING - Establish the scene, set the visual tone for the entire video. Use a WIDE establishing shot.\n"
                    elif idx == total_shots - 1:
                        context_hint += "Position: CLOSING - Provide visual closure. Use a resonant final image that echoes the core theme.\n"
                    else:
                        progress = idx / max(1, total_shots - 1)
                        if progress <= 0.25:
                            context_hint += "Position: INTRODUCTION (first quarter) - Introduce key subjects and settings. Prefer medium shots that clearly show who/what.\n"
                        elif progress <= 0.5:
                            context_hint += "Position: DEVELOPMENT (second quarter) - Show actions, interactions, and details. Prefer close-ups and dynamic angles.\n"
                        elif progress <= 0.75:
                            context_hint += "Position: CLIMAX (third quarter) - Heighten visual intensity. Use dramatic lighting, tight close-ups, or symbolic imagery.\n"
                        else:
                            context_hint += "Position: RESOLUTION (final quarter) - Show consequences, outcomes, or reflection. Prefer medium/wide shots with emotional weight.\n"
            except Exception:
                pass
        
        entity_hint = self._extract_entities_for_prompt(dubbing)
        if entity_hint:
            context_hint += f"Entities: {entity_hint}\n"
        
        if hasattr(self, '_chinese_semantic_skeletons') and isinstance(dubbing, str):
            shot_texts = getattr(self, '_shot_texts_for_context', [])
            try:
                idx = shot_index if shot_index >= 0 else (shot_texts.index(dubbing) if dubbing in shot_texts else -1)
                if idx >= 0:
                    prev_skeletons = [self._chinese_semantic_skeletons[j] for j in range(max(0, idx-2), idx) if j in self._chinese_semantic_skeletons and self._chinese_semantic_skeletons[j]]
                    if prev_skeletons:
                        context_hint += f"前序语义骨架 (确保语义递进，不重复):\n"
                        for sk in prev_skeletons[-2:]:
                            context_hint += f"  - {sk}\n"
            except Exception:
                pass
        
        template_params["context_hint"] = context_hint
        
        sd_model_name = ""
        if hasattr(self, 'model_var'):
            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
        template_key = PromptTemplates.get_template_key_for_model(sd_model_name)
        template_params["sd_model_name"] = sd_model_name
        
        template = PromptTemplates.get_template(template_key, **template_params)
        
        if prompt_type == "ARV写实提示词":
            arv_instruction = (
                "\n\n【ARV REALISTIC STYLE OVERRIDE】"
                "\nThis prompt MUST produce a photorealistic, documentary-style image."
                "\n- ALWAYS include: RAW photo, photorealistic, DSLR quality"
                "\n- ALWAYS use: documentary photography, film grain, natural lighting"
                "\n- NEVER produce: cartoon, anime, painting, illustration, 3D render"
                "\n- Emphasize: real textures, authentic atmosphere, unposed candid moments"
            )
            try:
                from video_generator.model_profiles import detect_model_type, MODEL_TYPE_FLUX, MODEL_TYPE_SD3
                _arv_model_type = detect_model_type(sd_model_name)
                if _arv_model_type in (MODEL_TYPE_FLUX, MODEL_TYPE_SD3):
                    arv_instruction += (
                        "\n- OUTPUT FORMAT: Write natural language scene descriptions, NOT comma-separated keywords"
                        "\n- Describe the scene as if writing a photo caption: who, what, where, lighting, mood"
                    )
            except Exception:
                pass
            template["system"] += arv_instruction
        
        try:
            _prompt_hb_stop = threading.Event()
            def _prompt_heartbeat():
                wait_sec = 0
                while not _prompt_hb_stop.is_set() and self.task_running:
                    _prompt_hb_stop.wait(8)
                    wait_sec += 8
                    if not _prompt_hb_stop.is_set() and self.task_running:
                        self.log(f"   ⏳ 提示词生成中... 已等待 {wait_sec}秒")
            
            hb_t = threading.Thread(target=_prompt_heartbeat, daemon=True)
            hb_t.start()
            
            try:
                llm_config = getattr(self, 'current_llm_config', None)
                result_text, _ = call_ollama_single(
                    model=model,
                    system_prompt=template["system"],
                    user_prompt=template["user"],
                    log_callback=self.log,
                    num_predict=512,
                    num_ctx=2560,
                    llm_config=llm_config,
                    timeout=Config.API_TIMEOUT_LLM_PROMPT,
                    cancel_check=lambda: not self.task_running
                )
            finally:
                _prompt_hb_stop.set()
                hb_t.join(timeout=2)
            
            if result_text:
                raw_output = result_text.strip()
                _sd_model_name = ""
                if hasattr(self, 'model_var'):
                    _sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                from video_generator.model_profiles import detect_model_type as _dt
                _current_model_type = _dt(_sd_model_name)
                cleaned_prompt = self._clean_prompt_output(raw_output, model_type=_current_model_type)
                if cleaned_prompt:
                    understanding = self._extract_understanding(raw_output)
                    if understanding and hasattr(self, '_pregenerated_understandings_for_context') and shot_index >= 0:
                        self._pregenerated_understandings_for_context[shot_index] = understanding
                    chinese_skeleton = self._extract_chinese_skeleton(raw_output)
                    if chinese_skeleton and hasattr(self, '_chinese_semantic_skeletons') and shot_index >= 0:
                        self._chinese_semantic_skeletons[shot_index] = chinese_skeleton
                    return cleaned_prompt
                self.log(f"⚠️ 模型 {model} 输出被清洗后为空，原始输出: {raw_output[:100]}")
            
            raise Exception(f"大模型 {model} 返回为空 (配音: {dubbing[:30]}...)")
        except Exception as e:
            self._log_exception(f"⚠️ 大模型调用失败，回退到内置逻辑生成基础提示词", e)
            self.log(f"   💡 提示: 回退生成的提示词质量较低，建议检查Ollama服务状态")
            return self._fallback_generate_prompt(dubbing, content_type, prompt_type, core_theme, visual_tone, theme_elements)

    def _generate_prompts_batch(self, batch_items, theme_info, user_prompt_type,
                                 user_style_override, full_text):
        """批量生成提示词 - 将多个分镜合并为一次LLM调用以减少开销

        Args:
            batch_items: 列表，每个元素为 (original_idx, task_dict)
            theme_info: 主题信息字典
            user_prompt_type: 提示词类型
            user_style_override: 用户风格覆盖
            full_text: 全文
        Returns:
            dict: {original_idx: prompt_string}，失败的项目值为空字符串
        """
        if not batch_items:
            return {}

        if not is_llm_available():
            self.log(f"   ⚠️ 大模型不可用，尝试重启Ollama服务...")
            try:
                from video_generator.ollama_client import restart_ollama_service
                if restart_ollama_service(log_callback=self.log):
                    set_ollama_available_global(True)
                    self.log("✅ Ollama服务已重启，继续批量生成")
                    time.sleep(2)
                else:
                    self.log("❌ Ollama服务重启失败，批次将使用回退生成")
                    return {idx: "" for idx, _ in batch_items}
            except Exception as e:
                self.log(f"❌ 重启Ollama异常: {e}，批次将使用回退生成")
                return {idx: "" for idx, _ in batch_items}

        model = self._get_current_model()
        if not model:
            model = "gemma3:4b"

        effective_visual_style = user_style_override if user_style_override else theme_info.get('visual_style', '')
        effective_visual_tone = theme_info.get('visual_tone', '')

        template_params = {
            "content_type": theme_info.get('content_type', '') or "未指定类型",
            "core_theme": theme_info.get('core_theme', '') or "未指定",
            "visual_style": effective_visual_style,
            "visual_tone": effective_visual_tone,
            "theme_elements": ", ".join(theme_info.get('theme_elements', [])) if theme_info.get('theme_elements') else "根据配音内容确定",
            "dubbing": "",
            "visual_narrative_strategy": theme_info.get('visual_narrative_strategy', ''),
            "sd_model_name": "",
        }

        if user_prompt_type == "ARV写实提示词":
            sd_model_name = ""
            if hasattr(self, 'model_var'):
                sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            template_key = PromptTemplates.get_template_key_for_model(sd_model_name)
        else:
            sd_model_name = ""
            if hasattr(self, 'model_var'):
                sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            template_key = PromptTemplates.get_template_key_for_model(sd_model_name)
        template_params["sd_model_name"] = sd_model_name

        dubbings = []
        for original_idx, task in batch_items:
            dubbing = task.get('text', '')
            context_hint = ""
            if full_text and isinstance(full_text, str) and len(full_text) > 50:
                summary = full_text[:300] if len(full_text) > 300 else full_text
                context_hint += f"FULL AUDIO CONTEXT (use this to understand the overall narrative):\n{summary}\n\n"
            if hasattr(self, '_shot_texts_for_context') and dubbing:
                shot_texts = self._shot_texts_for_context
                try:
                    idx = original_idx
                    if idx >= 0:
                        if hasattr(self, '_pregenerated_prompts_for_context'):
                            prev_prompts = [self._pregenerated_prompts_for_context[j] for j in range(max(0, idx - 2), idx) if j in self._pregenerated_prompts_for_context and self._pregenerated_prompts_for_context[j]]
                            if prev_prompts:
                                context_hint += f"AVOID: {', '.join(prev_prompts[-2:])}\n"
                            _BACKGROUND_KEYWORDS = [
                                'palace interior', 'dimly lit office', 'mahogany table', 'overcast sky',
                                'palace', 'office', 'courtroom', 'military base', 'border crossing',
                                'rural landscape', 'port', 'harbor', 'diplomatic venue', 'refugee camp',
                                'oil facility', 'parliament hall', 'prison corridor', 'airport tarmac',
                                'hotel lobby', 'city street', 'war room', 'bunker', 'balcony',
                            ]
                            used_backgrounds = []
                            for j in range(max(0, idx - 6), idx):
                                if j in self._pregenerated_prompts_for_context and self._pregenerated_prompts_for_context[j]:
                                    prev_p_lower = self._pregenerated_prompts_for_context[j].lower()
                                    for bg in _BACKGROUND_KEYWORDS:
                                        if bg in prev_p_lower and bg not in used_backgrounds:
                                            used_backgrounds.append(bg)
                            if used_backgrounds:
                                context_hint += f"USED BACKGROUNDS (do NOT reuse): {', '.join(used_backgrounds[-5:])}\n"
                        if hasattr(self, '_pregenerated_understandings_for_context'):
                            prev_understandings = [self._pregenerated_understandings_for_context[j] for j in range(max(0, idx - 3), idx) if j in self._pregenerated_understandings_for_context and self._pregenerated_understandings_for_context[j]]
                            if prev_understandings:
                                context_hint += "PREVIOUS SCENES (do NOT repeat similar scenes):\n"
                                for u in prev_understandings[-3:]:
                                    context_hint += f"  - {u}\n"
                        total_shots = len(shot_texts)
                        if idx == 0:
                            context_hint += "Position: OPENING\n"
                        elif idx == total_shots - 1:
                            context_hint += "Position: CLOSING\n"
                except Exception:
                    pass

            entity_hint = self._extract_entities_for_prompt(dubbing)
            if entity_hint:
                context_hint += f"Entities: {entity_hint}\n"

            if hasattr(self, '_chinese_semantic_skeletons') and dubbing:
                shot_texts = getattr(self, '_shot_texts_for_context', [])
                try:
                    idx = original_idx
                    if idx >= 0:
                        prev_skeletons = [self._chinese_semantic_skeletons[j] for j in range(max(0, idx-2), idx) if j in self._chinese_semantic_skeletons and self._chinese_semantic_skeletons[j]]
                        if prev_skeletons:
                            context_hint += f"前序语义骨架 (确保语义递进，不重复):\n"
                            for sk in prev_skeletons[-2:]:
                                context_hint += f"  - {sk}\n"
                except Exception:
                    pass

            shot_visual_tone = effective_visual_tone
            if hasattr(self, '_diversify_visual_tone') and shot_visual_tone and dubbing:
                _total_shots = getattr(self, '_total_shot_count', 0)
                _shot_idx = getattr(self, '_current_shot_index', -1)
                diversified = self._diversify_visual_tone(dubbing, shot_visual_tone, shot_index=_shot_idx, total_shots=_total_shots)
                if diversified != shot_visual_tone:
                    shot_visual_tone = diversified
                    tone_en = self._translate_to_english(shot_visual_tone)
                    if tone_en:
                        context_hint += f"Visual tone for THIS shot: {tone_en} (different from global tone)\n"

            dubbings.append({
                "idx": original_idx + 1,
                "text": dubbing,
                "context_hint": context_hint.strip()
            })

        batch_template = PromptTemplates.get_batch_template(template_key, dubbings, **template_params)

        batch_size = len(batch_items)
        num_predict = min(512 * batch_size, 4096)
        num_ctx = min(2560 + 256 * batch_size, 8192)

        try:
            _batch_hb_stop = threading.Event()
            def _batch_heartbeat():
                wait_sec = 0
                while not _batch_hb_stop.is_set() and self.task_running:
                    _batch_hb_stop.wait(8)
                    wait_sec += 8
                    if not _batch_hb_stop.is_set() and self.task_running:
                        self.log(f"   ⏳ 批量提示词生成中（{batch_size}个分镜）... 已等待 {wait_sec}秒")
            
            _batch_hb_t = threading.Thread(target=_batch_heartbeat, daemon=True)
            _batch_hb_t.start()
            
            try:
                result_text, _ = call_ollama_single(
                    model=model,
                    system_prompt=batch_template["system"],
                    user_prompt=batch_template["user"],
                    log_callback=self.log,
                    num_predict=num_predict,
                    num_ctx=num_ctx,
                    llm_config=getattr(self, 'current_llm_config', None),
                    timeout=Config.API_TIMEOUT_LLM_PROMPT * max(1, batch_size),
                    fallback_to_available=True,
                    cancel_check=lambda: not self.task_running
                )
            finally:
                _batch_hb_stop.set()
                _batch_hb_t.join(timeout=2)

            if not result_text:
                self.log(f"   ⚠️ 批量生成返回为空（批次大小: {batch_size}）")
                return {idx: "" for idx, _ in batch_items}

            results = {}
            raw_output = result_text.strip()
            lines = raw_output.split('\n')

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[(\d+)\]\s*(.+)', line)
                if not match:
                    match = re.match(r'(\d+)[.\)]\s*(.+)', line)
                if match:
                    shot_num = int(match.group(1))
                    content = match.group(2).strip()
                    original_idx = shot_num - 1
                    idx_keys = [idx for idx, _ in batch_items]
                    if original_idx in idx_keys:
                        _batch_sd_model_name = ""
                        if hasattr(self, 'model_var'):
                            _batch_sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                        from video_generator.model_profiles import detect_model_type as _bdt
                        _batch_model_type = _bdt(_batch_sd_model_name)
                        cleaned = self._clean_prompt_output(content, model_type=_batch_model_type)
                        if cleaned:
                            results[original_idx] = cleaned
                            understanding = self._extract_understanding(content)
                            if understanding and hasattr(self, '_pregenerated_understandings_for_context'):
                                self._pregenerated_understandings_for_context[original_idx] = understanding
                            chinese_skeleton = self._extract_chinese_skeleton(content)
                            if chinese_skeleton and hasattr(self, '_chinese_semantic_skeletons'):
                                self._chinese_semantic_skeletons[original_idx] = chinese_skeleton
                            if hasattr(self, '_pregenerated_prompts_for_context'):
                                self._pregenerated_prompts_for_context[original_idx] = cleaned

            for original_idx, _ in batch_items:
                if original_idx not in results:
                    results[original_idx] = ""

            return results

        except Exception as e:
            self._log_exception(f"⚠️ 批量生成提示词失败（批次大小: {batch_size}）", e)
            return {idx: "" for idx, _ in batch_items}
    

    def _get_custom_negative_prompt(self, content_type, dubbing, sd_model_name="", shot_index=-1):
        """根据制图模型类型和内容生成定制化负面提示词 - 增强版
        
        使用 model_profiles 统一管理基础负面提示词，
        然后根据配音文本内容和中文语义骨架动态添加针对性的负面提示词
        """
        from video_generator.model_profiles import get_model_profile, detect_model_type

        model_type = detect_model_type(sd_model_name)
        profile = get_model_profile(model_type)

        if not profile.get("needs_negative", True):
            return ""

        user_selected_styles = self.get_selected_styles()
        is_non_realistic = False
        from video_generator.model_profiles import NON_REALISTIC_KEYWORDS as _NRK2
        if user_selected_styles:
            style_text_lower = " ".join(user_selected_styles).lower()
            is_non_realistic = any(kw in style_text_lower for kw in _NRK2)

        if is_non_realistic and profile.get("non_realistic_negative"):
            base_negative = profile.get("non_realistic_negative", "").split(", ")
        else:
            base_negative = profile.get("default_negative", "").split(", ")
        base_negative = [n.strip() for n in base_negative if n.strip()]

        content_specific_negative = {
            "space": ["human", "person", "face", "building", "tree", "landscape", "daytime", "sun"],
            "science": ["cartoon character", "fictional creature", "fantasy", "magic"],
            "nature": ["urban", "building", "structure", "artificial", "concrete"],
            "history": ["modern", "contemporary", "anachronism", "smartphone", "computer"],
        }

        additional_negative = []
        
        _skeleton = ""
        if hasattr(self, '_chinese_semantic_skeletons') and shot_index >= 0:
            _skeleton = self._chinese_semantic_skeletons.get(shot_index, "")
        _combined = dubbing + " " + _skeleton

        if any(kw in _combined for kw in ["黑洞", "宇宙", "银河", "恒星", "星云"]):
            additional_negative.extend(["star", "sun", "planet", "moon", "satellite", "human", "person", "face", "building", "tree"])
        if any(kw in _combined for kw in ["政治", "历史", "古代", "战争"]):
            additional_negative.extend(["modern", "contemporary", "anachronism"])
        
        person_keywords = ["人", "他", "她", "我", "你", "我们", "他们", "教授", "学生", "科学家",
                          "学者", "研究", "教授", "老師", "博士", "人類", "人类"]
        if any(kw in _combined for kw in person_keywords):
            additional_negative.extend(["(extra faces:1.2)", "(multiple people:1.1)", "(crowded:1.1)"])
        
        animal_keywords = ["猴子", "猴", "猿", "猩猩", "黑猩猩", "动物", "動物", "灵长", "靈長",
                          "恐龙", "恐龍", "鸟", "魚", "鱼", "虎", "狮", "象"]
        if any(kw in _combined for kw in animal_keywords):
            additional_negative.extend(["(deformed animal:1.3)", "(wrong animal anatomy:1.2)", "(extra legs:1.2)"])
        
        abstract_keywords = ["进化", "進化", "演化", "自然选择", "自然選擇", "基因", "DNA",
                            "文明", "文化", "历史", "歷史", "时间", "時間", "千萬年", "百万年",
                            "链條", "鏈條", "接力", "转折", "轉折"]
        has_abstract = any(kw in _combined for kw in abstract_keywords)
        has_person = any(kw in _combined for kw in person_keywords)
        if has_abstract and not has_person:
            additional_negative.extend(["realistic person", "portrait", "face close-up", "selfie"])
        
        face_closeup_keywords = ["特写", "面部", "表情", "脸", "肖像", "面容",
                                  "close-up", "portrait", "face detail", "facial expression"]
        needs_face = any(kw in _combined for kw in face_closeup_keywords)
        if not needs_face and not has_person:
            additional_negative.extend(["(face close-up:1.1)", "(portrait:1.1)", "selfie", "(unwanted face:1.1)"])
        elif has_person and not needs_face:
            additional_negative.extend(["(face close-up:1.1)", "selfie"])
        
        data_keywords = ["98%", "百分比", "数据", "數據", "统计", "統計", "比例", "相似度"]
        if any(kw in _combined for kw in data_keywords):
            additional_negative.extend(["(text:1.3)", "(numbers:1.2)", "(watermark with text:1.2)", "chart with text"])
        
        nature_scene_keywords = ["森林", "树", "丛林", "草原", "山脉", "河流", "海洋", "沙漠"]
        if any(kw in _combined for kw in nature_scene_keywords):
            additional_negative.extend(["indoor", "room", "wall", "ceiling", "furniture"])

        # 经济/金融场景：排除不相关的自然/人物元素
        economy_keywords = ["股票", "投资", "杠杆", "资金", "崩盘", "金融", "经济", "通胀",
                           "现金流", "存款", "房贷", "消费", "收入", "工资", "储蓄", "制裁"]
        if any(kw in _combined for kw in economy_keywords):
            additional_negative.extend(["(forest:1.2)", "(ocean:1.2)", "(mountain:1.2)", "wildlife", "rural landscape"])
        
        # AI/科技场景：排除不相关的传统元素
        ai_keywords = ["AI", "人工智能", "算法", "芯片", "数字化", "自动化", "编程", "机器人"]
        if any(kw in _combined for kw in ai_keywords):
            additional_negative.extend(["(handwriting:1.2)", "(paper document:1.1)", "(typewriter:1.1)"])
        
        # 日常生活场景：排除不相关的宏大场景
        daily_keywords = ["柴米油盐", "保险", "养老", "房贷", "存款", "工资", "消费"]
        if any(kw in _combined for kw in daily_keywords):
            additional_negative.extend(["(war zone:1.2)", "(military:1.2)", "(battlefield:1.2)", "(palace:1.1)"])

        all_negative = base_negative.copy()
        content_type_lower = content_type.lower() if content_type else ""
        for ct, negatives in content_specific_negative.items():
            if ct in content_type_lower:
                all_negative.extend(negatives)
        all_negative.extend(additional_negative)
        all_negative = list(dict.fromkeys(all_negative))

        return ", ".join(all_negative)
    

    def _extract_core_entities(self, dubbing, content_type):
        """从配音文本中提取核心实体，直接作为视觉主体
        
        这是最关键的步骤：确保配音文本说的什么，SD生成的图片就是什么
        例如："伊朗革命卫队正式宣布" → "Iranian Revolutionary Guard, military announcement, official statement"
        
        增强版：使用增强版内容识别模块，支持：
        1. 更准确的国家/地点识别（如"厄立特里亚"不再是"俄罗斯"）
        2. 上下文引用解析（如"那里"能关联到前面提到的国家）
        3. 更完整的实体映射
        """
        if not dubbing:
            return ""
        
        dubbing_clean = dubbing.strip()
        entities = []
        
        # 优先使用增强版识别器
        if ENHANCED_RECOGNITION_AVAILABLE:
            try:
                recognizer = get_enhanced_recognizer()
                # 更新上下文（用于处理"那里"等引用）
                recognizer.update_context(dubbing_clean)
                
                # 识别实体
                recognized = recognizer.identify_entities(dubbing_clean)
                
                # 添加上下文引用（最重要，如"那里"→朝鲜）
                if recognized['context_references']:
                    for cn_name, en_value in recognized['context_references']:
                        entities.append(f"in {en_value.split(',')[0]}")
                
                # 添加国家
                if recognized['countries']:
                    entities.extend(recognized['countries'][:2])
                
                # 添加组织
                if recognized['organizations']:
                    entities.extend(recognized['organizations'][:2])
                
                # 添加军事相关
                if recognized['military']:
                    entities.extend(recognized['military'][:3])
                
                # 添加城市
                if recognized['cities']:
                    entities.extend(recognized['cities'][:2])
                
                # 添加地区
                if recognized['regions']:
                    entities.extend(recognized['regions'][:1])
                
                if entities:
                    return ", ".join(entities)
                
            except Exception as e:
                self._log_exception("⚠️ 增强版实体识别失败，使用内置识别", e)
        
        # 回退到内置识别逻辑（使用模块级常量，避免重复实例化）
        for mapping, mtype in _ENTITY_ALL_MAPPINGS:
            for cn_key, en_value in mapping.items():
                if cn_key in dubbing_clean:
                    entities.append(en_value)
                    break

        if content_type:
            content_lower = content_type.lower()
            if 'military' in content_lower:
                entities.append('military scene, combat zone')
            elif 'politics' in content_lower:
                entities.append('political scene, government setting')
            elif 'science' in content_lower:
                entities.append('scientific scene, laboratory')

        if entities:
            return ", ".join(entities)

        return ""

    def _analyze_and_generate_sd_prompt(self, text, content_type, custom_theme='', custom_visual_tone='',
                                         theme_elements=None, shot_index=-1):
        """分析文本语义并生成SD提示词 - 自适应回退方案

        核心策略：优先利用主题分析阶段LLM已提取的结构化信息（content_type、core_theme、
        visual_tone、theme_elements），而非依赖硬编码关键词匹配。这确保了无论音频内容
        是什么主题，回退路径都能生成与主题紧密相关的prompt。

        三层信息源（优先级递减）：
        1. LLM主题分析结果 → core_theme/visual_tone/theme_elements（最可靠，对任何主题有效）
        2. 文本语义提取 → 从配音文本中提取实体/场景/人物（补充细节）
        3. 硬编码关键词映射 → 仅作为兜底（覆盖面有限）

        根据模型类型输出不同格式：Flux/SD3用自然语言，SD15/SDXL用关键词
        """
        if theme_elements is None:
            theme_elements = []

        model_type = "sd15"
        if hasattr(self, 'model_var'):
            mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            try:
                from video_generator.model_profiles import detect_model_type
                model_type = detect_model_type(mn)
            except Exception:
                pass

        user_selected_styles = self.get_selected_styles() if hasattr(self, 'get_selected_styles') else []
        is_non_realistic = False
        from video_generator.model_profiles import NON_REALISTIC_KEYWORDS as _NRK3
        if user_selected_styles:
            style_text_lower = " ".join(user_selected_styles).lower()
            is_non_realistic = any(kw in style_text_lower for kw in _NRK3)

        # ========== 第一层：LLM主题分析结果（最可靠） ==========
        # core_theme、visual_tone、theme_elements 是LLM分析全文本后提取的，
        # 对任何主题都有效（经济、科技、体育、美食、旅游……）
        theme_keywords = []
        if custom_theme:
            theme_translated = self._smart_translate(custom_theme)
            if theme_translated:
                theme_keywords.append(theme_translated)
        if custom_visual_tone:
            tone_translated = self._smart_translate(custom_visual_tone)
            if tone_translated:
                theme_keywords.append(tone_translated)
        if theme_elements:
            for elem in theme_elements:
                elem_translated = self._smart_translate(elem)
                if elem_translated and elem_translated not in theme_keywords:
                    theme_keywords.append(elem_translated)

        # ========== 第二层：从配音文本中提取实体/场景/人物（补充细节） ==========
        entity_keywords = []
        scene_keyword = ''

        # 实体提取（人名/地名/组织名）
        entity_hint = self._extract_entities_for_prompt(text)
        if entity_hint:
            # entity_hint 格式如 "Entities: Maduro, Venezuela"
            for part in entity_hint.replace('Entities:', '').split(','):
                part = part.strip()
                if part and part not in theme_keywords:
                    entity_keywords.append(part)

        # 场景提取：基于content_type推断场景类型
        content_type_scene = self._content_type_to_scene(content_type, text)
        if content_type_scene:
            scene_keyword = content_type_scene

        # 人物角色提取
        person_keyword = self._extract_person_role(text)

        # 构图/镜头：基于shot_index
        camera_keyword = self._get_camera_for_shot(shot_index)

        # ========== 第三层：硬编码关键词映射（兜底） ==========
        fallback_keywords = []
        for cn_key, en_val in _TRANSLATION_MAPPING.items():
            if cn_key in text and en_val not in theme_keywords and en_val not in entity_keywords:
                fallback_keywords.append(en_val)

        # 如果前两层信息充足，不需要硬编码兜底
        if len(theme_keywords) + len(entity_keywords) >= 3:
            fallback_keywords = fallback_keywords[:2]  # 最多补充2个

        # ========== 组装prompt ==========
        all_parts = []
        if camera_keyword:
            all_parts.append(camera_keyword)
        if scene_keyword:
            all_parts.append(scene_keyword)
        if person_keyword:
            all_parts.append(person_keyword)
        all_parts.extend(entity_keywords[:3])
        all_parts.extend(theme_keywords[:5])
        all_parts.extend(fallback_keywords[:3])

        # 去重
        unique_parts = list(dict.fromkeys(all_parts))
        if len(unique_parts) <= 1:
            unique_parts = ['realistic scene', 'detailed environment']

        # 根据模型类型输出不同格式
        return self._format_prompt_for_model(unique_parts, model_type, is_non_realistic,
                                              camera_keyword, scene_keyword)


    def _smart_translate(self, chinese_text):
        """智能中文到英文翻译 - 三层策略确保任何中文都能翻译

        1. 精确匹配 _TRANSLATION_MAPPING
        2. 子串匹配 + 拼装
        3. 通用翻译策略（基于content_type推断场景类别词）

        返回纯英文，不含中文。如果无法翻译则返回空字符串。
        """
        if not chinese_text:
            return ""

        # 先用 _translate_to_english 做精确/子串匹配
        result = self._translate_to_english(chinese_text)
        if result and not re.search(r'[\u4e00-\u9fff]', result):
            return result

        # 策略2：拆分后逐段翻译再拼装
        # 按中文标点、顿号、空格拆分
        parts = re.split(r'[，。、；：！？\s,;:!?]+', chinese_text)
        translated_parts = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            tr = self._translate_to_english(part)
            if tr and not re.search(r'[\u4e00-\u9fff]', tr):
                translated_parts.append(tr)
            else:
                # 尝试逐字/逐词匹配
                sub_parts = []
                i = 0
                while i < len(part):
                    # 尝试4字→3字→2字→1字匹配
                    matched = False
                    for length in range(min(4, len(part) - i), 0, -1):
                        sub = part[i:i+length]
                        sub_tr = _TRANSLATION_MAPPING.get(sub, '')
                        if sub_tr and not re.search(r'[\u4e00-\u9fff]', sub_tr):
                            sub_parts.append(sub_tr)
                            i += length
                            matched = True
                            break
                    if not matched:
                        i += 1  # 跳过无法翻译的字
                if sub_parts:
                    translated_parts.append(', '.join(sub_parts))

        if translated_parts:
            return ', '.join(translated_parts)

        # 策略3：无法翻译时返回空，让调用方使用兜底逻辑
        return ""

    def _content_type_to_scene(self, content_type, text=''):
        """根据content_type推断视觉场景关键词

        不依赖硬编码中文关键词匹配，而是直接将content_type映射到
        对应的英文场景描述。这样无论音频是什么主题，只要LLM
        正确识别了content_type，就能生成合适的场景。
        """
        _CONTENT_TYPE_SCENES = {
            '军事分析': 'military scene, strategic command',
            '政治分析': 'political scene, government building',
            '外交分析': 'diplomatic venue, international summit',
            '财经商业': 'financial district, business environment',
            '科技科普': 'technology lab, digital innovation',
            '科普教育': 'educational setting, knowledge sharing',
            '新闻播报': 'news broadcast, press conference',
            '历史纪录': 'historical scene, archival footage',
            '社会民生': 'everyday life, social conditions',
            '文化艺术': 'cultural scene, artistic environment',
            '自然地理': 'natural landscape, geographic feature',
            '体育竞技': 'sports event, athletic competition',
            '医疗健康': 'medical setting, healthcare',
            '美食烹饪': 'kitchen, cooking scene, food preparation',
            '旅游风光': 'scenic destination, travel landscape',
            '情感生活': 'emotional scene, personal moment',
            '教育学习': 'classroom, learning environment',
            '娱乐综艺': 'entertainment, performance stage',
        }
        # 精确匹配
        if content_type in _CONTENT_TYPE_SCENES:
            return _CONTENT_TYPE_SCENES[content_type]

        # 模糊匹配：content_type中的关键词
        _PARTIAL_MAP = {
            '军事': 'military scene', '战争': 'war zone',
            '政治': 'political scene', '政府': 'government building',
            '外交': 'diplomatic venue', '国际': 'international setting',
            '财经': 'financial district', '经济': 'economic scene',
            '商业': 'business environment', '金融': 'financial district',
            '科技': 'technology lab', '科普': 'science, educational',
            '教育': 'educational setting', '新闻': 'news broadcast',
            '历史': 'historical scene', '社会': 'social conditions',
            '文化': 'cultural scene', '艺术': 'artistic environment',
            '自然': 'natural landscape', '体育': 'sports event',
            '医疗': 'medical setting', '健康': 'healthcare',
            '美食': 'kitchen, cooking', '旅游': 'travel, scenic view',
            '情感': 'emotional scene', '娱乐': 'entertainment',
        }
        for key, scene in _PARTIAL_MAP.items():
            if key in content_type:
                return scene

        return 'realistic scene'

    def _extract_person_role(self, text):
        """从文本中提取人物角色关键词"""
        _PERSON_PATTERNS = [
            (r'总统|主席|首相|总理|领导人', 'national leader'),
            (r'将军|军官|司令|将领', 'military general'),
            (r'士兵|军人|武装人员', 'armed soldier'),
            (r'外交官|大使|代表', 'diplomat'),
            (r'科学家|研究员|学者', 'scientist'),
            (r'医生|护士|医护人员', 'medical professional'),
            (r'教师|老师|教授', 'teacher'),
            (r'运动员|选手|冠军', 'athlete'),
            (r'商人|企业家|CEO', 'business leader'),
            (r'工人|劳动者|职工', 'worker'),
            (r'农民|渔民|牧民', 'rural worker'),
            (r'学生|青年|少年', 'young person, student'),
            (r'老人|长者|老者', 'elderly person'),
            (r'女性|妇女|妻子|母亲', 'woman'),
            (r'儿童|小孩|孩子', 'child'),
            (r'夫妇|夫妻|伴侣', 'couple'),
        ]
        for pattern, role in _PERSON_PATTERNS:
            if re.search(pattern, text):
                return role
        return ''

    def _get_camera_for_shot(self, shot_index):
        """根据分镜位置返回镜头类型，确保视觉多样性"""
        if shot_index < 0:
            # 无shot_index时，使用随机但确定性的选择
            return 'medium shot'

        _CAMERA_SEQUENCE = [
            'wide establishing shot',      # 0: 开场广角
            'medium shot',                  # 1: 中景
            'close-up shot',                # 2: 特写
            'over-the-shoulder shot',        # 3: 过肩
            'low angle shot',               # 4: 仰角
            'medium shot',                  # 5: 中景
            'close-up shot, detailed',      # 6: 细节特写
            'wide shot, reflective',        # 7: 结尾广角
        ]
        if shot_index == 0:
            return _CAMERA_SEQUENCE[0]
        idx = shot_index % len(_CAMERA_SEQUENCE)
        return _CAMERA_SEQUENCE[idx]

    def _format_prompt_for_model(self, unique_parts, model_type, is_non_realistic,
                                  camera_keyword='', scene_keyword=''):
        """根据模型类型格式化prompt输出

        SD 1.5: 关键词 + 权重标记
        SDXL:   关键词 + 短描述
        Flux:   自然语言句子
        SD3:    自然语言 + 少量关键词
        """
        # 移除可能残留的中文
        clean_parts = [re.sub(r'[\u4e00-\u9fff]+', '', p).strip() for p in unique_parts]
        clean_parts = [p for p in clean_parts if p]

        if model_type in ('flux', 'sd3'):
            # Flux/SD3: 自然语言描述
            sentence_parts = []
            if camera_keyword:
                sentence_parts.append(f"A {camera_keyword}")
            else:
                sentence_parts.append('A scene')

            if scene_keyword:
                sentence_parts.append(f"depicting {scene_keyword}")

            # 将关键词转为描述性短语（跳过camera和scene，避免重复）
            skip_parts = {camera_keyword, scene_keyword}
            desc_parts = [p for p in clean_parts if p not in skip_parts][:5]
            if desc_parts:
                desc_text = ', '.join(desc_parts)
                sentence_parts.append(f"featuring {desc_text}")

            if not is_non_realistic:
                sentence_parts.append("cinematic lighting, high quality")

            result = '. '.join(p for p in sentence_parts if p)
            if result and not result[0].isupper():
                result = result[0].upper() + result[1:]
            return result if result else 'A cinematic scene with dramatic lighting'

        # SD 1.5 / SDXL: 关键词格式
        if is_non_realistic:
            quality_tags = 'highly detailed, vibrant colors, artistic style'
        elif model_type == 'sdxl':
            quality_tags = 'ultra detailed, photorealistic, cinematic lighting, high quality'
        else:
            quality_tags = 'ultra detailed, hyper realistic, photorealistic, cinematic lighting, professional photography'

        return f"{', '.join(clean_parts)}, {quality_tags}"

    def _translate_to_english(self, chinese_text):
        """中文到英文翻译，支持多词组合（逗号/顿号分隔）"""
        if chinese_text in _TRANSLATION_MAPPING:
            return _TRANSLATION_MAPPING[chinese_text]
        if ',' in chinese_text or '，' in chinese_text or '、' in chinese_text:
            parts = re.split(r'[,，、]', chinese_text)
            translated_parts = []
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if part in _TRANSLATION_MAPPING:
                    translated_parts.append(_TRANSLATION_MAPPING[part])
                else:
                    for key, value in _TRANSLATION_MAPPING.items():
                        if key in part:
                            translated_parts.append(value)
                            break
            if translated_parts:
                return ', '.join(translated_parts)
        for key, value in _TRANSLATION_MAPPING.items():
            if key in chinese_text:
                return value
        return ""
    
    
    # =======================================================================
    # 第六部分：关键词与视觉概念提取 (行 5599-6015)
    # =======================================================================





    
    # =======================================================================
    # 第七部分：分镜优化与情感分析 (行 6367-6797)
    # =======================================================================

    

    def _robust_json_parse(self, result, shots_count):
        """健壮的JSON解析函数，处理各种格式
        
        返回: (applied_count, log_message)
        """
        
        applied_count = 0
        log_message = ""
        
        # 方法1: 直接尝试 json.loads
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str) and len(value) > 10:
                        idx = int(key) if key.isdigit() else None
                        if idx is not None and 0 <= idx < shots_count:
                            applied_count += 1
                if applied_count > 0:
                    return applied_count, f"直接解析成功: {applied_count}个"
        except Exception:
            pass
        
        # 方法2: 尝试提取JSON数组或对象
        patterns = [
            (r'\[[\s\S]*\]', '数组'),
            (r'\{[\s\S]*\}', '对象'),
        ]
        
        for pattern, pattern_name in patterns:
            match = re.search(pattern, result)
            if match:
                try:
                    data = json.loads(match.group())
                    
                    # 格式A: {"0": "xxx", "1": "yyy"}
                    if isinstance(data, dict) and all(k.isdigit() for k in data.keys()):
                        for i in range(shots_count):
                            if str(i) in data and len(data[str(i)]) > 10:
                                applied_count += 1
                        if applied_count > 0:
                            return applied_count, f"字典格式解析成功: {applied_count}个"
                    
                    # 格式B: ["xxx", "yyy"]
                    elif isinstance(data, list) and len(data) > 0:
                        if isinstance(data[0], str):
                            applied_count = sum(1 for x in data if isinstance(x, str) and len(x) > 10)
                            if applied_count > 0:
                                return applied_count, f"数组格式解析成功: {applied_count}个"
                        
                        # 格式C: [{"scene_id": 1, "prompt": "xxx"}]
                        elif isinstance(data[0], dict):
                            for item in data:
                                sid = item.get('scene_id')
                                p = item.get('prompt')
                                if sid and p and len(p) > 10:
                                    if 1 <= sid <= shots_count:
                                        applied_count += 1
                            if applied_count > 0:
                                return applied_count, f"scene_id格式解析成功: {applied_count}个"
                    
                    # 格式D: {"prompts": ["xxx", "yyy"]}
                    elif isinstance(data, dict) and 'prompts' in data:
                        prompts = data.get('prompts', [])
                        if isinstance(prompts, list):
                            applied_count = sum(1 for x in prompts if isinstance(x, str) and len(x) > 10)
                            if applied_count > 0:
                                return applied_count, f"prompts格式解析成功: {applied_count}个"
                    
                    # 格式E: {"scenes": [{"scene_id": 1, "prompt": "xxx"}]}
                    elif isinstance(data, dict) and 'scenes' in data:
                        scenes = data.get('scenes', [])
                        if isinstance(scenes, list):
                            for item in scenes:
                                sid = item.get('scene_id')
                                p = item.get('prompt')
                                if sid and p and len(p) > 10:
                                    if 1 <= sid <= shots_count:
                                        applied_count += 1
                            if applied_count > 0:
                                return applied_count, f"scenes格式解析成功: {applied_count}个"
                except json.JSONDecodeError:
                    continue
        
        # 方法3: 逐行解析 key: value 格式
        lines = result.split('\n')
        parsed = {}
        for line in lines:
            line = line.strip()
            if not line or ':' not in line:
                continue
            # 尝试提取数字key
            for num in re.findall(r'^\s*["\']?(\d+)["\']?\s*:', line):
                # 尝试提取引号中的内容
                match = re.search(r':\s*["\'](.+?)["\']', line)
                if match:
                    parsed[num] = match.group(1)
        
        if parsed:
            applied_count = sum(1 for v in parsed.values() if len(v) > 10)
            if applied_count > 0:
                return applied_count, f"逐行解析成功: {applied_count}个"
        
        return 0, "无法解析"
        

    def _translate_theme_elements_to_english(self, theme_elements):
        """将主题元素翻译成英文（双层策略 + 自动学习）
        
        策略：
        1. 字典匹配（快速，覆盖常用词）
        2. LLM批量翻译（智能，处理生僻词，结果自动加入字典）
        """
        if not theme_elements:
            return []
        
        result = []
        untranslated = []
        
        # === 第一层：字典快速匹配 ===
        for elem in theme_elements:
            translation = self._get_translation_from_dict(elem)
            if translation:
                result.append(translation)
            else:
                untranslated.append(elem)
                result.append(elem)  # 暂时保留中文
        
        # === 第二层：LLM批量翻译未命中的词汇 ===
        if untranslated and is_llm_available():
            try:
                translated_map = self._batch_translate_with_llm(untranslated)
                if translated_map:
                    # 更新结果列表并自动学习新词汇
                    for i, elem in enumerate(theme_elements):
                        if elem in translated_map:
                            result[i] = translated_map[elem]
                            # 自动加入字典（下次直接使用）
                            self._add_to_translation_cache(elem, translated_map[elem])
                            self.log(f"🌐 LLM翻译: '{elem}' → '{translated_map[elem]}' (已缓存)")
            except Exception as e:
                self._log_exception("⚠️ LLM翻译失败，使用原文", e)
        
        return result
    

    def _batch_translate_with_llm(self, words_list):
        """使用Ollama批量翻译中文词汇为英文
        
        Args:
            words_list: 需要翻译的中文词汇列表
            
        Returns:
            dict: {中文: 英文} 的映射字典，失败返回空字典
        """
        if not words_list:
            return {}
        
        try:
            # 构造翻译提示词
            words_str = ', '.join(words_list)
            prompt = f"""请将以下中文词汇翻译成英文，以JSON格式返回结果。

中文词汇：{words_str}

要求：
1. 只返回JSON格式，不要其他解释
2. 格式示例：{{"东京": "Tokyo", "女性": "woman"}}
3. 保持简洁，每个词用最常用的英文翻译

返回："""
            
            model = self._get_current_model()
            if not model:
                model = "gemma3:4b"
            model_list = [model, "gemma3:4b", "qwen3:8b", "mistral"]
            
            result_text, _ = call_ollama_model(
                model_list=model_list,
                system_prompt="You are a translator. Translate Chinese words to English. Output only JSON format like {\"中文\": \"English\"}.",
                user_prompt=prompt,
                log_callback=self.log,
                num_predict=500,
                num_ctx=1532,
                llm_config=getattr(self, 'current_llm_config', None),
                timeout=Config.API_TIMEOUT_LLM_PROMPT
            )
            
            if result_text:
                json_match = re.search(r'\{[^}]+\}', result_text)
                if json_match:
                    translated_dict = json.loads(json_match.group())
                    return translated_dict
            
            return {}
        except Exception as e:
            self._log_exception("⚠️ LLM批量翻译异常", e)
            return {}

    # =======================================================================
    # 第八部分：文本翻译与主题分析 (行 6819-7221)
    # =======================================================================
    

    def _simplify_theme(self, theme_text):
        """简化核心主题：保留完整语义，仅去除描述性前缀
        
        截断时按中文标点/逗号边界截断，避免在字中间切断导致语义残缺。
        """
        if not theme_text:
            return theme_text
        
        
        prefixes_to_remove = [
            '这是一段关于', '本文讨论的是', '主要讲述', '主要内容是',
            '文章讲述', '本文介绍', '视频讲述', '这段音频讲述',
        ]
        
        cleaned = theme_text
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        if len(cleaned) > 30:
            # 优先在标点/逗号处截断，保留完整语义片段
            _BREAK_CHARS = '，。、；：！？,;:!?'
            cut_pos = -1
            for i in range(30, max(15, 30 - 10) - 1, -1):
                if i < len(cleaned) and cleaned[i] in _BREAK_CHARS:
                    cut_pos = i
                    break
            if cut_pos > 10:
                cleaned = cleaned[:cut_pos]
            else:
                # 没有合适的标点，尝试在最后一个完整词边界截断
                # 中文每个字都是独立词，直接截到30即可，但确保不切断
                cleaned = cleaned[:30]
        
        return cleaned
    

    def extract_theme_info(self, analysis_result):
        """从大模型分析结果中提取主题信息 - 支持新增的内容类型、视觉风格、场景建议"""
        theme_info = {
            'content_type': '',
            'core_theme': '',
            'visual_tone': '',
            'visual_tone_en': '',
            'visual_style': '',
            'visual_style_en': '',
            'theme_elements': [],
            'emotional_tone': '',
            'visual_narrative_strategy': '',
            'correction_dict': {}
        }

        if not analysis_result:
            return theme_info

        try:
            # 清理各种格式标记
            cleaned_result = analysis_result.replace('**', '').replace('【', '').replace('】', '')
            cleaned_result = cleaned_result.replace('*', '')

            # 内容类型标准化映射
            content_type_mapping = {
                '新闻播报': '新闻播报',
                '新闻': '新闻播报',
                '军事分析': '军事分析',
                '军事': '军事分析',
                '科普教育': '科普教育',
                '科普': '科普教育',
                '科学': '科普教育',
                '历史纪录': '历史纪录',
                '历史': '历史纪录',
                '社会民生': '社会民生',
                '社会': '社会民生',
                '民生': '社会民生',
                '财经商业': '财经商业',
                '财经': '财经商业',
                '经济': '财经商业',
                '文化艺术': '文化艺术',
                '文化': '文化艺术',
                '艺术': '文化艺术',
                '自然地理': '自然地理',
                '自然': '自然地理',
                '地理': '自然地理',
                '体育竞技': '体育竞技',
                '体育': '体育竞技',
            }

            # 提取内容类型（新增）
            if '内容类型' in cleaned_result:
                try:
                    type_match = cleaned_result.split('内容类型')[1].split('\n')[0]
                    type_match = type_match.replace('：', '').replace(':', '').strip()
                    
                    # 标准化内容类型
                    for key, value in content_type_mapping.items():
                        if key in type_match:
                            theme_info['content_type'] = value
                            break
                    else:
                        # 如果没有匹配到，使用原始值
                        theme_info['content_type'] = type_match.replace('类', '').replace('型', '')
                except Exception:
                    theme_info['content_type'] = ''

            # 提取核心主题（支持有冒号和无冒号的情况）
            if '核心主题' in cleaned_result:
                try:
                    core_match = cleaned_result.split('核心主题')[1].split('\n')[0]
                    core_match = core_match.replace('：', '').replace(':', '').strip()
                except Exception:
                    core_match = ""
            elif '中心思想' in cleaned_result:
                core_match = cleaned_result.split('中心思想')[1].split('\n')[0].strip()
            elif 'Core Theme:' in cleaned_result:
                core_match = cleaned_result.split('Core Theme:')[1].split('\n')[0].strip()
            else:
                core_match = ""
            
            if core_match:
                core_match = self._simplify_theme(core_match)
                theme_info['core_theme'] = core_match

            # 提取情感基调（新增）
            if '情感基调' in cleaned_result:
                try:
                    emotion_match = cleaned_result.split('情感基调')[1].split('\n')[0]
                    emotion_match = emotion_match.replace('：', '').replace(':', '').strip()
                    theme_info['emotional_tone'] = emotion_match
                    if not theme_info.get('visual_tone'):
                        theme_info['visual_tone'] = emotion_match
                except Exception:
                    pass

            if '视觉基调' in cleaned_result:
                tone_match = cleaned_result.split('视觉基调')[1].split('\n')[0].replace('：', '').replace(':', '').strip()
                theme_info['visual_tone'] = tone_match
                if tone_match in _TRANSLATION_MAPPING:
                    theme_info['visual_tone_en'] = _TRANSLATION_MAPPING[tone_match]
                else:
                    translated = self._translate_to_english(tone_match)
                    theme_info['visual_tone_en'] = translated if translated else tone_match

            if '英文视觉风格' in cleaned_result:
                try:
                    en_style_match = cleaned_result.split('英文视觉风格')[1].split('\n')[0]
                    en_style_match = en_style_match.replace('：', '').replace(':', '').strip()
                    if en_style_match and en_style_match != '无':
                        theme_info['visual_style_en'] = en_style_match
                        theme_info['visual_style'] = en_style_match
                except Exception:
                    pass

            cn_style_text = cleaned_result
            if '英文视觉风格' in cn_style_text:
                cn_style_text = cn_style_text.split('英文视觉风格')[0]
            if '视觉风格' in cn_style_text:
                try:
                    style_match = cn_style_text.split('视觉风格')[1].split('\n')[0]
                    style_match = style_match.replace('：', '').replace(':', '').strip()
                    if not theme_info.get('visual_style'):
                        theme_info['visual_style'] = style_match
                    if not theme_info.get('visual_tone'):
                        theme_info['visual_tone'] = style_match
                except Exception:
                    if not theme_info.get('visual_style'):
                        theme_info['visual_style'] = theme_info.get('visual_tone', '')

            # 提取主题元素
            if '主题元素' in cleaned_result or '核心元素' in cleaned_result:
                try:
                    elements_key = '核心元素' if '核心元素' in cleaned_result else '主题元素'
                    elements_text = cleaned_result.split(elements_key)[1].split('\n')[0]
                    elements_text = elements_text.replace('：', '').replace(':', '').strip()
                    elements = re.split(r'[，、,\n]', elements_text)
                    cleaned_elements = []
                    for e in elements:
                        e = e.strip()
                        if not e:
                            continue
                        if '→' in e:
                            e = e.split('→')[-1].strip()
                        elif '->' in e:
                            e = e.split('->')[-1].strip()
                        if e:
                            cleaned_elements.append(e)
                    theme_info['theme_elements'] = cleaned_elements[:8]
                except Exception:
                    theme_info['theme_elements'] = []
            elif 'Theme Elements:' in cleaned_result:
                elements_text = cleaned_result.split('Theme Elements:')[1].split('\n')[0].strip()
                elements = re.split(r'[,;]', elements_text)
                theme_info['theme_elements'] = [e.strip() for e in elements if e.strip()]

            # 提取视觉叙事策略
            if '视觉叙事策略' in cleaned_result:
                try:
                    strategy_match = cleaned_result.split('视觉叙事策略')[1].split('\n')[0]
                    strategy_match = strategy_match.replace('：', '').replace(':', '').strip()
                    if strategy_match and strategy_match != '无':
                        strategy_map = {
                            'A': '时间线叙事', 'B': '空间探索', 'C': '主题递进',
                            'D': '对比叙事', 'E': '隐喻主线',
                            '时间线': '时间线叙事', '空间': '空间探索',
                            '主题': '主题递进', '对比': '对比叙事', '隐喻': '隐喻主线',
                        }
                        matched_strategy = None
                        for key, value in strategy_map.items():
                            if key in strategy_match:
                                matched_strategy = value
                                break
                        theme_info['visual_narrative_strategy'] = matched_strategy or strategy_match
                except Exception:
                    pass

            # 提取纠错说明并应用纠正
            correction_dict = {}
            skipped_noop = 0
            self.log(f"   🔍 检查是否存在'纠错说明'...")
            if '纠错说明' in cleaned_result:
                self.log(f"   🔍 找到纠错说明，正在解析...")
                try:
                    after_correction = cleaned_result.split('纠错说明')[1]
                    
                    next_section_markers = ['解析', '总结', '备注', '说明', '内容类型', '核心主题', '情感基调', '视觉风格', '英文视觉', '核心元素', '主题元素', '视觉叙事策略']
                    correction_text = after_correction
                    for marker in next_section_markers:
                        if marker in correction_text:
                            correction_text = correction_text.split(marker)[0]
                            break
                    correction_text = correction_text.replace('：', '').replace(':', '').strip()
                    
                    if not correction_text:
                        lines = after_correction.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line and line != '：' and line != ':':
                                correction_text = line.replace('：', '').replace(':', '').strip()
                                if correction_text:
                                    break
                    
                    self.log(f"   🔍 纠错内容原始: {correction_text}")
                    
                    if correction_text and correction_text != '无' and correction_text != '无纠正' and not correction_text.startswith('无'):
                        # 支持多种分隔符：逗号、顿号、分号
                        separators = [',', '，', '、', ';', '；']
                        parts = [correction_text]
                        for sep in separators:
                            new_parts = []
                            for part in parts:
                                new_parts.extend(part.split(sep))
                            parts = new_parts
                        
                        for part in parts:
                            part = part.strip()
                            if not part:
                                continue
                            if '→' not in part and '->' not in part and '=>' not in part:
                                continue
                            try:
                                if '→' in part:
                                    old, new = part.split('→', 1)
                                elif '->' in part:
                                    old, new = part.split('->', 1)
                                elif '=>' in part:
                                    old, new = part.split('=>', 1)
                                else:
                                    continue
                                old = old.strip()
                                new = new.strip()
                                if not old or not new:
                                    continue
                                old_simplified = _ensure_simplified_chinese(old)
                                new_simplified = _ensure_simplified_chinese(new)
                                # 繁→简转换检查应基于simplified版本
                                # 如果simplified后old==new，说明只是繁简差异，不是真正的纠错
                                if old_simplified == new_simplified:
                                    skipped_noop += 1
                                    continue
                                if old_simplified != new_simplified:
                                    if new_simplified.startswith(old_simplified) and len(new_simplified) > len(old_simplified):
                                        skipped_noop += 1
                                        continue
                                    if old_simplified.startswith(new_simplified) and len(old_simplified) > len(new_simplified):
                                        skipped_noop += 1
                                        continue
                                    if new_simplified in old_simplified and len(new_simplified) < len(old_simplified):
                                        skipped_noop += 1
                                        continue
                                    if len(old_simplified) == 2 and len(new_simplified) == 2 and old_simplified[0] == new_simplified[0] and old_simplified[1] != new_simplified[1]:
                                        # 同音/近音替换是合法的ASR纠错（如"油眼→油盐"、"金炼→金链"），不应跳过
                                        # 仅跳过明显非纠错的替换：形近但音不同，且不在常见ASR错误模式中
                                        try:
                                            import pypinyin
                                            old_pinyin = ''.join([p[0] for p in pypinyin.lazy_pinyin(old_simplified)])
                                            new_pinyin = ''.join([p[0] for p in pypinyin.lazy_pinyin(new_simplified)])
                                            if old_pinyin == new_pinyin or old_pinyin[-1] == new_pinyin[-1]:
                                                # 同音或末字同音，是合法ASR纠错，保留
                                                pass
                                            else:
                                                # 非同音替换，可能是LLM幻觉，跳过
                                                skipped_noop += 1
                                                continue
                                        except ImportError:
                                            # pypinyin不可用时，保守策略：保留纠错（宁可误纠也不漏纠）
                                            pass
                                    correction_dict[old_simplified] = new_simplified
                                    if old_simplified != old or new_simplified != new:
                                        self.log(f"   🔄 纠错项繁→简: {old}→{new} ⇒ {old_simplified}→{new_simplified}")
                                else:
                                    skipped_noop += 1
                            except Exception as e:
                                self.log(f"   ⚠️ 解析单项纠错失败: {part}, 错误: {e}")
                                continue
                        
                        if skipped_noop > 0:
                            self.log(f"   ℹ️ 跳过 {skipped_noop} 项无效纠错（前后内容相同，如繁体字→繁体字）")

                        if correction_dict:
                            self.log(f"   🔍 有效纠错字典: {correction_dict}")
                            
                            if theme_info.get('core_theme'):
                                corrected_theme = theme_info['core_theme']
                                for old, new in correction_dict.items():
                                    corrected_theme = corrected_theme.replace(old, new)
                                if corrected_theme != theme_info['core_theme']:
                                    self.log(f"   🔄 主题纠错: {theme_info['core_theme']} → {corrected_theme}")
                                    theme_info['core_theme'] = corrected_theme
                            
                            if theme_info.get('theme_elements'):
                                corrected_elements = []
                                for elem in theme_info['theme_elements']:
                                    corrected_elem = elem
                                    for old, new in correction_dict.items():
                                        corrected_elem = corrected_elem.replace(old, new)
                                    corrected_elements.append(corrected_elem)
                                if corrected_elements != theme_info['theme_elements']:
                                    self.log(f"   🔄 元素纠错: {theme_info['theme_elements']} → {corrected_elements}")
                                theme_info['theme_elements'] = corrected_elements
                            
                            theme_info['correction_dict'] = correction_dict
                            self.log(f"   ✅ 纠错已应用到主题信息")
                        else:
                            self.log(f"   ✅ 无有效纠错项（所有纠错前后内容相同），文本无需纠错")
                            theme_info['correction_dict'] = {}
                    else:
                        self.log(f"   ℹ️ 纠错说明为'无'，无需纠错")
                        theme_info['correction_dict'] = {}
                except Exception as e:
                    self.log(f"   ⚠️ 解析纠错说明失败: {e}")
                    theme_info['correction_dict'] = {}
            else:
                theme_info['correction_dict'] = {}

        except Exception as e:
            self._log_exception("⚠️ 提取主题信息时出错", e)

        if theme_info:
            try:
                import unicodedata
                _t2s_map = str.maketrans({
                    '亞': '亚', '羅': '罗', '權': '权', '軍': '军', '戰': '战',
                    '國': '国', '際': '际', '濟': '济', '製': '制', '歷': '历',
                    '運': '运', '動': '动', '黨': '党', '選': '选', '舉': '举',
                    '議': '议', '題': '题', '驗': '验', '經': '经', '營': '营',
                    '業': '业', '農': '农', '產': '产', '點': '点', '從': '从',
                    '過': '过', '還': '还', '進': '进', '開': '开', '關': '关',
                    '無': '无', '與': '与', '區': '区', '時': '时', '說': '说',
                    '長': '长', '門': '门', '問': '问', '馬': '马', '車': '车',
                    '將': '将', '對': '对', '學': '学', '樣': '样', '現': '现',
                    '來': '来', '發': '发', '書': '书', '見': '见', '話': '话',
                    '會': '会', '機': '机', '壓': '压', '總': '总', '體': '体',
                    '條': '条', '達': '达', '讓': '让', '著': '着', '裡': '里',
                    '準': '准', '強': '强', '團': '团', '處': '处', '據': '据',
                    '認': '认', '為': '为', '個': '个', '層': '层', '級': '级',
                    '導': '导', '實': '实', '記': '记', '計': '计', '劃': '划',
                    '設': '设', '備': '备', '務': '务', '職': '职', '費': '费',
                    '質': '质', '網': '网',
                })
                _simplified_fields = {}
                for key in ['core_theme', 'visual_tone', 'content_type']:
                    val = theme_info.get(key, '')
                    if val and re.search(r'[\u4e00-\u9fff]', val):
                        new_val = val.translate(_t2s_map)
                        if new_val != val:
                            _simplified_fields[key] = (val, new_val)
                            theme_info[key] = new_val
                elems = theme_info.get('theme_elements', [])
                if elems:
                    new_elems = []
                    changed = False
                    for e in elems:
                        ne = e.translate(_t2s_map)
                        if ne != e:
                            changed = True
                        new_elems.append(ne)
                    if changed:
                        _simplified_fields['theme_elements'] = (elems, new_elems)
                        theme_info['theme_elements'] = new_elems
                if _simplified_fields:
                    self.log(f"   🔄 主题元素繁体→简体: {_simplified_fields}")
                elems = theme_info.get('theme_elements', [])
                if elems:
                    asr_fixed = []
                    asr_changed = False
                    for e in elems:
                        fe = e
                        for wrong, correct in sorted(_COMMON_ASR_ERROR_DICT.items(), key=lambda x: len(x[0]), reverse=True):
                            if wrong in fe:
                                fe = fe.replace(wrong, correct)
                        if fe != e:
                            asr_changed = True
                        asr_fixed.append(fe)
                    if asr_changed:
                        self.log(f"   🔄 主题元素ASR纠错: {elems} → {asr_fixed}")
                        theme_info['theme_elements'] = asr_fixed
            except Exception:
                pass

        return theme_info


    def quick_theme_consistency_check(self, shots, theme_info):
        """快速主题一致性预检查（轻量级，不调用LLM）
        
        检查策略：
        1. 中文主题关键词在description中匹配
        2. 英文主题关键词在prompt中匹配（仅使用翻译字典，不调用LLM）
        3. 内容类型关键词匹配
        4. 只要命中任一即视为一致
        
        返回: (是否一致, 偏离数量, 总检查数, 偏离索引列表)
        """
        if not theme_info.get('core_theme'):
            return True, 0, len(shots), []
        
        core_theme = theme_info['core_theme']
        theme_elements = theme_info.get('theme_elements', [])
        content_type = theme_info.get('content_type', '')
        
        check_keywords_cn = []
        for elem in theme_elements:
            for word in elem.split():
                if len(word) >= 2:
                    check_keywords_cn.append(word)
        for word in core_theme.split():
            if len(word) >= 2:
                check_keywords_cn.append(word)
        check_keywords_cn = list(set(check_keywords_cn))
        
        check_keywords_en = []
        for elem in theme_elements:
            trans = self._get_translation_from_dict(elem)
            if trans:
                for word in trans.lower().split():
                    if len(word) > 3:
                        check_keywords_en.append(word)
        trans = self._get_translation_from_dict(core_theme)
        if trans:
            for word in trans.lower().split():
                if len(word) > 3:
                    check_keywords_en.append(word)
        check_keywords_en = list(set(check_keywords_en))
        
        content_type_keywords = {
            '军事': ['military', 'soldier', 'war', 'weapon', 'combat', 'tank', 'missile', 'navy', 'army'],
            '新闻': ['news', 'press', 'journalist', 'reporter', 'broadcast', 'media'],
            '科普': ['science', 'laboratory', 'research', 'experiment', 'technology', 'data'],
            '历史': ['historical', 'ancient', 'heritage', 'classical', 'period', 'dynasty'],
            '财经': ['business', 'economy', 'finance', 'stock', 'market', 'corporate'],
            '文化': ['culture', 'art', 'museum', 'tradition', 'heritage', 'literature'],
            '自然': ['nature', 'landscape', 'wildlife', 'environment', 'mountain', 'ocean'],
            '体育': ['sport', 'athlete', 'competition', 'stadium', 'game', 'race'],
        }
        content_en = []
        for ct_key, ct_words in content_type_keywords.items():
            if ct_key in content_type:
                content_en.extend(ct_words)
        content_en = list(set(content_en))
        
        self.log(f"\n🔍 快速预检查:")
        self.log(f"   core_theme: '{core_theme}'")
        self.log(f"   中文关键词({len(check_keywords_cn)}个): {check_keywords_cn[:10]}")
        self.log(f"   英文关键词({len(check_keywords_en)}个): {check_keywords_en[:10]}")
        self.log(f"   内容类型关键词({len(content_en)}个): {content_en[:8]}")
        
        deviation_count = 0
        deviation_indices = []
        
        for i, shot in enumerate(shots):
            prompt = shot.get('prompt_en', '').lower()
            description = shot.get('description', '').lower()
            combined = prompt + ' ' + description
            
            has_theme_element = False
            
            if any(kw in description for kw in check_keywords_cn):
                has_theme_element = True
            
            if not has_theme_element and any(kw in combined for kw in check_keywords_en):
                has_theme_element = True
            
            if not has_theme_element and any(kw in prompt for kw in content_en):
                has_theme_element = True
            
            if not has_theme_element:
                deviation_count += 1
                deviation_indices.append(i)
        
        total_checked = len(shots)
        is_consistent = deviation_count == 0
        
        self.log(f"📊 检查结果: {deviation_count}/{total_checked} 偏离")
        
        return is_consistent, deviation_count, total_checked, deviation_indices
    

    def validate_theme_consistency(self, shots, theme_info, deviation_indices=None):
        """验证分镜的主题一致性，偏离时自动修正提示词
        
        限制：最多修正10个分镜，避免无限循环
        """
        if not theme_info.get('core_theme'):
            return True, "未提取到主题信息，跳过一致性检查"

        core_theme = theme_info['core_theme']
        theme_elements = theme_info.get('theme_elements', [])
        visual_tone = theme_info.get('visual_tone', '')

        consistency_issues = []
        fixed_count = 0

        if deviation_indices is not None:
            indices_to_fix = list(deviation_indices)
        else:
            indices_to_fix = []

        MAX_FIX_COUNT = 10
        indices_to_fix = indices_to_fix[:MAX_FIX_COUNT]

        if len(deviation_indices or []) > MAX_FIX_COUNT:
            self.log(f"   ⚠️ 偏离数量过多({len(deviation_indices)}个)，仅修正前{MAX_FIX_COUNT}个以避免耗时过长")

        for i in indices_to_fix:
            if i >= len(shots):
                continue
            shot = shots[i]
            consistency_issues.append(f"分镜{i+1}")
            
            if is_llm_available() and shot.get('description'):
                try:
                    dubbing = shot['description']
                    content_type = shot.get('content_type', 'general')
                    corrected = self._generate_prompt_with_llm(
                        dubbing, content_type,
                        prompt_type=self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词",
                        core_theme=core_theme,
                        visual_tone=visual_tone,
                        theme_elements=theme_elements
                    )
                    if corrected and len(corrected) > 20:
                        shot['prompt_en'] = corrected
                        fixed_count += 1
                        self.log(f"   ✅ 分镜{i+1}已修正")
                except Exception:
                    pass

        if consistency_issues:
            total_deviant = len(deviation_indices) if deviation_indices else len(indices_to_fix)
            msg = f"发现{total_deviant}个偏离主题的分镜"
            if fixed_count > 0:
                msg += f"，已自动修正{fixed_count}个"
            if total_deviant > MAX_FIX_COUNT:
                msg += f"（仅修正前{MAX_FIX_COUNT}个）"
            return False, msg

        return True, "主题一致性检查通过"
    


    def generate_shots(self, auto_mode=False):
        """生成分镜 - 修复异常处理和状态管理
        
        Args:
            auto_mode: 自动模式，为True时不显示完成弹窗（用于自动化流程）
        """
        # 确保在函数开始时就导入必要的模块
        
        # 初始化变量，防止 NameError
        analysis_result = ""
        theme_info = {}
        
        whisper_model_loaded = False
        whisper_used_gpu = False
        
        _shots_start_time = time.time()
        
        try:
            # 检查是否有音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，无法生成分镜")
                self.update_task_progress("就绪")
                return
            
            # 检查大模型服务是否可用（云端或本地Ollama）
            llm_ready = is_llm_available()
            
            if not llm_ready:
                if check_ollama_available():
                    set_ollama_available_global(True)
                    llm_ready = True
                    self.log("✅ Ollama服务已连接")
                else:
                    self.log("⚠️ Ollama服务未运行，尝试自动启动...")
                    if try_start_ollama_service():
                        set_ollama_available_global(True)
                        llm_ready = True
                        self.log("✅ Ollama服务已自动启动并连接")
                    else:
                        set_ollama_available_global(False)
                        self.log("❌ 大模型服务不可用")
                        if not auto_mode:
                            self.root.after(0, lambda: messagebox.showwarning(
                                "大模型服务不可用",
                                "本地Ollama未运行，且未启用云端大模型！\n\n"
                                "分镜生成需要大模型进行：\n"
                                "• 语音文本纠错和标点添加\n"
                                "• 主题分析和内容分类\n"
                                "• 提示词生成\n\n"
                                "请选择以下方式之一：\n"
                                "方案A：启动本地Ollama服务后重试\n"
                                "方案B：在高级设置中启用云端大模型"
                            ))
                        self.update_task_progress("就绪")
                        return
            
            self.log("=" * 50)
            self.log("🎬 开始一键生成分镜")
            self.log("=" * 50)
            
            if hasattr(self, '_sync_all_settings'):
                self._sync_all_settings()
            
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
            
            self.cache_clear('analysis')
            self.cache_clear('prompts')

            try:
                prompt_cache.clear()
            except Exception:
                pass

            try:
                if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                    if 'shots' in self.state_manager:
                        self.state_manager['shots'] = {
                            'generated': False,
                            'count': 0,
                            'data': []
                        }
                    if 'images' in self.state_manager:
                        self.state_manager['images'] = {
                            'generated': False,
                            'count': 0,
                            'path': self.images_dir if hasattr(self, 'images_dir') else ''
                        }
                    if 'video' in self.state_manager:
                        self.state_manager['video'] = {
                            'generated': False,
                            'path': None
                        }
            except Exception:
                pass

            try:
                if hasattr(self, 'data_bus') and isinstance(self.data_bus, dict):
                    self.data_bus.clear()
            except Exception:
                pass

            try:
                if hasattr(self, 'event_system') and isinstance(self.event_system, dict):
                    self.event_system.clear()
            except Exception:
                pass

            self.log("🗑️ 已清除历史缓存（保留音频转录缓存以加速重复生成）")
            
            self.shots_data = []
            
            self._move_output_to_trash(reason="regenerate_shots")
            
            # 步骤1: 音频分析
            self.log("\n📍 步骤 1/4: 音频语音识别")
            self.update_task_progress("正在识别音频语音...", 10)
            
            # 生成音频文件的缓存键（添加文件大小防止冲突）
            try:
                audio_stat = os.stat(self.audio_path)
                audio_key = f"audio_{hashlib.md5(self.audio_path.encode()).hexdigest()}_{audio_stat.st_mtime}_{audio_stat.st_size}"
            except Exception as e:
                self._log_exception("❌ 无法读取音频文件", e)
                self.update_task_progress("就绪")
                return
            
            # 检查缓存中是否有分析结果
            cached_result = self.cache_get('audio_analysis', audio_key)
            if cached_result:
                self.log("✅ 从缓存加载音频分析结果")
                segments = cached_result.get('segments', [])
                full_text = cached_result.get('full_text', "")
                self.log(f"   识别片段数: {len(segments)}")

                if self.whisper_model is not None:
                    was_on_gpu = self._whisper_on_gpu
                    self._safe_release_whisper_gpu()
                    if was_on_gpu:
                        self.log("   ✅ Whisper GPU 资源已释放（缓存命中）")
                whisper_used_gpu = False
            else:
                # 检查是否启用云端语音识别
                cloud_asr_enabled = False
                try:
                    from video_generator.cloud_llm_client import is_cloud_asr_enabled, call_cloud_asr
                    cloud_asr_enabled = is_cloud_asr_enabled()
                except ImportError:
                    pass
                
                if cloud_asr_enabled:
                    self.update_task_progress("正在使用云端Whisper识别...", 20)
                    self.log("☁️ 使用云端Whisper API进行语音识别（无需本地GPU）")
                    
                    cloud_segments, cloud_text = call_cloud_asr(
                        self.audio_path, language="zh", log_callback=self.log
                    )
                    
                    if cloud_segments is not None and len(cloud_segments) > 0:
                        segments = cloud_segments
                        full_text = cloud_text
                        whisper_used_gpu = False
                        
                        self.log(f"✅ 云端语音识别完成，共 {len(segments)} 个片段")
                        
                        cache_data = {'segments': segments, 'full_text': full_text}
                        self.cache_set('audio_analysis', audio_key, cache_data)
                        self.log("✅ 音频分析结果已缓存")
                    else:
                        if cloud_segments is not None:
                            self.log("⚠️ 云端ASR返回空结果，回退到本地Whisper")
                        else:
                            self.log("⚠️ 云端ASR失败，回退到本地Whisper")
                        cloud_asr_enabled = False
                
                # 本地Whisper语音识别（云端ASR成功时跳过）
                if not cloud_asr_enabled:
                    self.update_task_progress("正在加载Whisper模型...", 20)
                    # 仅在云端LLM也启用时才卸载Ollama，避免混合模式（LLM=本地, ASR=云端→回退本地）下误卸本地模型
                    try:
                        from video_generator.ollama_client import is_cloud_llm_active
                        if is_cloud_llm_active():
                            self._unload_ollama_models(log_prefix="   ")
                        else:
                            self.log("   💡 本地LLM模式，保留Ollama模型")
                    except ImportError:
                        self._unload_ollama_models(log_prefix="   ")
                    warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")
                    
                    whisper_model_size = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "large-v3-turbo"
                    current_model_size = getattr(self, '_whisper_model_size', None)
                    
                    if self.whisper_model and current_model_size and current_model_size != whisper_model_size:
                        self.log(f"🔄 模型大小已变更 ({current_model_size} → {whisper_model_size})，重新加载...")
                        self._safe_release_whisper_gpu()
                        del self.whisper_model
                        self.whisper_model = None
                        gc.collect()
                    
                    if self.whisper_model is not None and current_model_size == whisper_model_size:
                        try:
                            import torch
                            if torch.cuda.is_available():
                                self.whisper_model = self.whisper_model.to("cuda")
                                self._whisper_on_gpu = True
                                whisper_used_gpu = True
                                self.log(f"✅ Whisper {whisper_model_size} 已迁移到GPU")
                            else:
                                self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                        except Exception as e:
                            self._log_exception("⚠️ Whisper迁移GPU失败，使用CPU", e)
                    else:
                        try:
                            import whisper
                            import torch
                            if torch.cuda.is_available():
                                gpu_name = torch.cuda.get_device_name(0)
                                gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
                                self.log(f"🖥️ 加载Whisper到GPU: {gpu_name} ({gpu_mem:.1f}GB, CUDA)")
                                self.log(f"   使用模型: Whisper {whisper_model_size}")
                                self.update_task_progress(f"正在加载Whisper {whisper_model_size}模型...", 22)
                                local_model = get_whisper_model_path(whisper_model_size)
                                model_arg = local_model if local_model else whisper_model_size
                                if local_model:
                                    self.log(f"   使用本地模型: {local_model}")
                                
                                _whisper_load_hb_stop = threading.Event()
                                def _whisper_load_heartbeat():
                                    wait_sec = 0
                                    while not _whisper_load_hb_stop.is_set() and self.task_running:
                                        _whisper_load_hb_stop.wait(3)
                                        wait_sec += 3
                                        if not _whisper_load_hb_stop.is_set() and self.task_running:
                                            self.log(f"   ⏳ 模型加载中... 已等待 {wait_sec}秒")
                                
                                _whisper_load_hb_t = threading.Thread(target=_whisper_load_heartbeat, daemon=True)
                                _whisper_load_hb_t.start()
                                
                                try:
                                    self.whisper_model = whisper.load_model(model_arg, device="cuda")
                                finally:
                                    _whisper_load_hb_stop.set()
                                    _whisper_load_hb_t.join(timeout=2)
                                
                                self._whisper_model_size = whisper_model_size
                                whisper_model_loaded = True
                                self._whisper_on_gpu = True
                                whisper_used_gpu = True
                                self.log(f"✅ Whisper {whisper_model_size} 加载成功 (GPU加速)")
                            else:
                                self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                                self.log(f"   使用模型: Whisper {whisper_model_size}")
                                self.update_task_progress(f"正在加载Whisper {whisper_model_size}模型...", 22)
                                local_model = get_whisper_model_path(whisper_model_size)
                                model_arg = local_model if local_model else whisper_model_size
                                if local_model:
                                    self.log(f"   使用本地模型: {local_model}")
                                self.whisper_model = whisper.load_model(model_arg, device="cpu")
                                self._whisper_model_size = whisper_model_size
                                whisper_model_loaded = True
                                self._whisper_on_gpu = False
                                whisper_used_gpu = False
                                self.log(f"✅ Whisper {whisper_model_size} 加载成功 (CPU模式)")
                        except Exception as e:
                            self._log_exception("⚠️ GPU加载失败，回退到CPU", e)
                            try:
                                import whisper as _whisper_fallback
                                local_model = get_whisper_model_path(whisper_model_size)
                                model_arg = local_model if local_model else whisper_model_size
                                if local_model:
                                    self.log(f"   使用本地模型: {local_model}")
                                self.whisper_model = _whisper_fallback.load_model(model_arg, device="cpu")
                                whisper_model_loaded = True
                                self._whisper_on_gpu = False
                                self.log(f"✅ Whisper {whisper_model_size} 加载成功 (CPU模式)")
                            except Exception as e2:
                                self._log_exception("❌ 模型加载完全失败", e2)
                                self.update_task_progress("就绪")
                                return
                    
                    self.update_task_progress("正在进行语音识别...", 30)
                    try:
                        if not self.task_running:
                            self.log("❌ 任务已被取消")
                            return
                        
                        _whisper_hb_stop = threading.Event()
                        _whisper_start_time = time.time()
                        def _whisper_heartbeat():
                            wait_sec = 0
                            while not _whisper_hb_stop.is_set() and self.task_running:
                                _whisper_hb_stop.wait(5)
                                wait_sec += 5
                                if not _whisper_hb_stop.is_set() and self.task_running:
                                    self.log(f"   ⏳ 语音识别进行中... 已等待 {wait_sec}秒")
                        
                        _whisper_hb_thread = threading.Thread(target=_whisper_heartbeat, daemon=True)
                        _whisper_hb_thread.start()
                        
                        try:
                            result = self.whisper_model.transcribe(
                                self.audio_path,
                                language="zh",
                                word_timestamps=True,
                                fp16=False,
                                verbose=False,
                                condition_on_previous_text=False,
                                no_speech_threshold=0.3
                            )
                        finally:
                            _whisper_hb_stop.set()
                            _whisper_hb_thread.join(timeout=2)
                        
                        whisper_elapsed = time.time() - _whisper_start_time
                        segments = result.get("segments", [])
                        self.log(f"✅ 语音识别完成，共 {len(segments)} 个片段（耗时 {whisper_elapsed:.1f}秒）")
                        if len(segments) < 50:
                            avg_duration = sum(s.get('end', 0) - s.get('start', 0) for s in segments) / len(segments) if segments else 0
                            self.log(f"   ℹ️ 平均片段时长: {avg_duration:.1f}秒，如需要更细分镜可减小停顿检测阈值")
                    except Exception as e:
                        self._log_exception("❌ 语音识别失败", e)
                        self.update_task_progress("就绪")
                        return
                    
                    if not segments:
                        self.log("❌ 音频识别失败，无法生成分镜")
                        self.update_task_progress("就绪")
                        return
                    
                    full_text = "".join([segment.get("text", "").strip() for segment in segments])
                    cache_data = {'segments': segments, 'full_text': full_text}
                    self.cache_set('audio_analysis', audio_key, cache_data)
                    self.log("✅ 音频分析结果已缓存")
                    was_on_gpu = self._whisper_on_gpu
                    self._safe_release_whisper_gpu()
                    if was_on_gpu:
                        self.log("   ✅ Whisper 模型 GPU 资源已释放")
            
            # 步骤2: 大模型分析文章内容（用于统一分镜基调）
            self.log("\n📍 步骤 2/4: 主题分析与纠错")
            self.log("   流程: 发送全文 → 大模型提取主题/基调/元素/纠错 → 供后续分镜使用")
            self.update_task_progress("正在分析文章内容...", 40)
            
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 初始化变量（确保变量在所有代码路径中都有定义）
            content_type = "general"
            prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
            correction_dict = {}
            
            # 显示当前使用的提示词类型
            self.log(f"💬 提示词类型: {prompt_type}")
            self.log(f"🤖 大模型: {self._get_current_model()}")
            
            audio_file_hash = hashlib.md5(self.audio_path.encode()).hexdigest()[:8]
            cache_key_string = f"{audio_file_hash}_{full_text}_{prompt_type}"
            analysis_key = f"analysis_{hashlib.md5(cache_key_string.encode()).hexdigest()}"

            # 直接从原始segments创建分镜列表（每个片段一个分镜）
            # 不再计算推荐数量，完全由大模型决定
            original_shot_tasks = []
            for seg in segments:
                text = seg.get('text', '').strip()
                seg_start = seg.get('start', 0)
                seg_end = seg.get('end', 0)
                if text and seg_end > seg_start:
                    original_shot_tasks.append({
                        'text': text,
                        'start': seg_start,
                        'end': seg_end,
                    })
            
            self.log(f"   原始语音片段数: {len(original_shot_tasks)}个")

            # 初始化theme_info（包含全局内容类型）
            theme_info = {
                'core_theme': '', 
                'visual_tone': '', 
                'visual_tone_en': '',
                'visual_style': '',
                'visual_style_en': '',
                'theme_elements': [],
                'content_type': content_type,
                'correction_dict': {}
            }
            user_custom_theme = ""
            user_custom_tone = ""
            _ollama_model_already_loaded = False
            
            # 检查缓存中是否有大模型分析结果
            cached_analysis = self.cache_get('analysis', analysis_key)
            if cached_analysis:
                self.log("✅ 从缓存加载大模型分析结果")
                self.log(f"   缓存键包含: 文本内容 + 内容类型({content_type}) + 提示词类型({prompt_type})")
                analysis_result = cached_analysis
                
                # 从缓存中提取主题信息
                theme_info = self.extract_theme_info(analysis_result)
                
                # 同步 content_type 变量
                if theme_info.get('content_type'):
                    content_type = theme_info['content_type']
                
                # 确保visual_tone有值
                if not theme_info.get('visual_tone'):
                    theme_info['visual_tone'] = '紧张'
                
                # 重要：对缓存中的主题再次进行简化处理（确保使用最新逻辑）
                if theme_info.get('core_theme'):
                    simplified_theme = self._simplify_theme(theme_info['core_theme'])
                    if simplified_theme != theme_info['core_theme']:
                        theme_info['core_theme'] = simplified_theme
                
                user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                
                if user_custom_theme:
                    theme_info['core_theme'] = user_custom_theme
                if user_custom_tone:
                    theme_info['visual_tone'] = user_custom_tone
                
                self.log(f"🎯 核心主题: {theme_info.get('core_theme', '未指定')}")
                if theme_info.get('visual_tone'):
                    tone_cn = theme_info['visual_tone']
                    tone_en = theme_info.get('visual_tone_en', '')
                    tone_display = f"{tone_cn} ({tone_en})" if tone_en else tone_cn
                    self.log(f"🎨 视觉基调: {tone_display}")
                if theme_info.get('theme_elements'):
                    self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:8])}")
                
                self.log("✅ 主题提取完成，将应用纠错结果到分镜文本")
                _ollama_model_already_loaded = False
            else:
                if len(full_text) > 20:
                    llm_ready = is_llm_available()
                    ollama_connected = False
                    
                    if not llm_ready:
                        if check_ollama_available():
                            set_ollama_available_global(True)
                            ollama_connected = True
                            llm_ready = True
                            self.log("✅ 已连接到Ollama服务")
                        else:
                            self.log("⚠️ Ollama服务未响应")
                            self.log("   尝试自动启动Ollama服务...")
                            if try_start_ollama_service():
                                set_ollama_available_global(True)
                                ollama_connected = True
                                llm_ready = True
                                self.log("✅ Ollama服务已启动并连接成功")
                            else:
                                self.log("❌ 本地Ollama不可用")
                    
                    if llm_ready:
                        try:
                            self.update_task_progress("正在等待模型分析...", 50)
                            
                            _cloud_llm_active = False
                            try:
                                from video_generator.cloud_llm_client import is_cloud_llm_active
                                _cloud_llm_active = is_cloud_llm_active()
                            except ImportError:
                                pass
                            
                            user_model = self._get_current_model()
                            if _cloud_llm_active:
                                candidate_models = ["cloud"]
                                self.log("🤖 启动云端大模型分析...")
                            else:
                                available_models = get_available_models()
                                if user_model in available_models:
                                    candidate_models = [user_model]
                                else:
                                    candidate_models = [user_model]
                                    self.log(f"⚠️ 用户指定的模型 {user_model} 不在可用列表中，仍将尝试使用")
                                self.log(f"🤖 启动本地大模型分析...")
                                self.log(f"   使用模型: {user_model}")
                                self.log(f"   可用模型数: {len(available_models)}个")
                            
                            self.log(f"   文本长度: {len(full_text)} 字符")
                            self.log(f"   提示词类型: {prompt_type}")
                            self.log(f"   内容类型: {content_type}")
                            
                            # 检查并显示自定义主题设置
                            custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                            custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                            if custom_theme:
                                self.log(f"   🎯 自定义核心主题: {custom_theme}")
                            if custom_visual_tone:
                                self.log(f"   🎨 自定义视觉基调: {custom_visual_tone}")
                            if not custom_theme and not custom_visual_tone:
                                self.log(f"   💡 提示: 可在高级设置中自定义主题和基调")
                            
                            # 使用线程池执行大模型调用
                            
                            def call_ollama_with_model(model_name):
                                """使用指定模型调用Ollama - 通篇分析提取主题"""
                                _heartbeat_stop = threading.Event()
                                
                                def _heartbeat():
                                    wait_sec = 0
                                    while not _heartbeat_stop.is_set() and self.task_running:
                                        _heartbeat_stop.wait(5)
                                        wait_sec += 5
                                        if not _heartbeat_stop.is_set() and self.task_running:
                                            self.log(f"   ⏳ 模型思考中... 已等待 {wait_sec}秒")
                                
                                try:
                                    custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                                    custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                                    
                                    template = PromptTemplates.get_template("theme_analysis", text=full_text)
                                    
                                    if custom_theme or custom_visual_tone:
                                        user_addition = f"\n\n【用户指定的核心主题】: {custom_theme}" if custom_theme else ""
                                        user_addition += f"\n【用户指定的视觉基调】: {custom_visual_tone}" if custom_visual_tone else ""
                                        system_content = template["system"]
                                        user_content = template["user"] + user_addition
                                    else:
                                        system_content = template["system"]
                                        user_content = template["user"]
                                    
                                    hb_thread = threading.Thread(target=_heartbeat, daemon=True)
                                    hb_thread.start()
                                    
                                    try:
                                        result_content, _ = call_ollama_single(
                                            model=model_name,
                                            system_prompt=system_content,
                                            user_prompt=user_content,
                                            log_callback=self.log,
                                            num_predict=2000,
                                            num_ctx=8192,
                                            llm_config=getattr(self, 'current_llm_config', None),
                                            timeout=Config.API_TIMEOUT_LLM_ANALYSIS,
                                            cancel_check=lambda: not self.task_running
                                        )
                                    finally:
                                        _heartbeat_stop.set()
                                        hb_thread.join(timeout=2)
                                    
                                    if not result_content:
                                        raise Exception(f"大模型 {model_name} 主题分析返回为空")
                                    
                                    result_content = result_content.strip()
                                    
                                    self.log(f"   📝 模型响应长度: {len(result_content)} 字符")
                                    
                                    return result_content
                                except Exception as e:
                                    _heartbeat_stop.set()
                                    raise e
                            
                            analysis_result = ""
                            selected_model = candidate_models[0] if candidate_models else user_model
                            _retry_count = 0
                            _max_retries = 1 if _cloud_llm_active else 2
                            
                            while _retry_count < _max_retries and not analysis_result:
                                _retry_count += 1
                                is_retry = _retry_count > 1
                                
                                try:
                                    if is_retry:
                                        self.log(f"\n   🔄 第 {_retry_count} 次尝试（重启Ollama后重试）...")
                                        try:
                                            from video_generator.ollama_client import restart_ollama_service, is_ollama_available
                                            if restart_ollama_service(log_callback=self.log):
                                                set_ollama_available_global(True)
                                                self.log("✅ Ollama服务已重启，重新尝试调用模型")
                                                time.sleep(2)
                                            else:
                                                self.log("❌ Ollama服务重启失败")
                                                break
                                        except Exception as restart_err:
                                            self.log(f"❌ 重启Ollama异常: {restart_err}")
                                            break
                                    else:
                                        self.log(f"   等待模型分析中...")
                                    
                                    start_time = time.time()
                                    analysis_result = call_ollama_with_model(selected_model)
                                    elapsed_time = time.time() - start_time
                                    
                                    if analysis_result:
                                        self.log(f"✅ 模型 {selected_model} 分析完毕！")
                                        self.log(f"   响应时间: {elapsed_time:.1f}秒")
                                        self.log(f"   响应长度: {len(analysis_result)} 字符")
                                        self.log(f"   响应内容预览: {analysis_result[:100]}...")
                                    else:
                                        self.log(f"⚠️ 模型 {selected_model} 返回空结果")
                                        if _retry_count < _max_retries:
                                            self.log(f"   将重启Ollama后重试...")
                                        
                                except Exception as e:
                                    error_msg = str(e).lower()
                                    self._log_exception(f"⚠️ 模型 {selected_model} 调用失败", e)
                                    
                                    if "timeout" in error_msg or "timed out" in error_msg:
                                        self.log(f"   ❌ 模型响应超时（当前超时设置: {Config.API_TIMEOUT_LLM_ANALYSIS}秒）")
                                        if _retry_count < _max_retries:
                                            self.log(f"   将重启Ollama后重试...")
                                        else:
                                            self.log(f"   💡 建议: 1) 在设置中切换更小的模型  2) 检查GPU显存是否充足  3) 关闭其他占用GPU的程序")
                                    elif "connection" in error_msg or "refused" in error_msg:
                                        self.log(f"   ❌ Ollama服务连接失败")
                                        if _retry_count < _max_retries:
                                            self.log(f"   将重启Ollama后重试...")
                                        else:
                                            self.log(f"   💡 请检查Ollama是否正常运行")
                                    else:
                                        if _retry_count < _max_retries:
                                            self.log(f"   将重启Ollama后重试...")
                                        else:
                                            self.log(f"   💡 请检查Ollama服务是否正常运行，或更换模型重试")
                            
                            if not analysis_result:
                                self.log(f"\n❌ 模型 {selected_model} 调用失败（已重试 {_max_retries} 次）")
                                self.log(f"   💡 请在设置中切换其他模型后重试")
                                set_ollama_available_global(False)
                                self.log("🧹 Ollama标记为不可用，GPU显存将在空闲时自动释放")
                                _ollama_model_already_loaded = False
                            
                            # 缓存分析结果（即使是空结果也缓存，避免重复失败）
                            if analysis_result:
                                self.cache_set('analysis', analysis_key, analysis_result)
                                self.log("✅ 大模型分析结果已缓存")
                            
                            # 解析分析结果 - 只提取主题信息，不生成分镜
                            self.update_task_progress("正在提取分析结果...", 55)
                            
                            if analysis_result:
                                self.log(f"📝 大模型返回内容预览: {analysis_result[:500]}...")
                            
                            theme_info = self.extract_theme_info(analysis_result)
                            
                            if theme_info.get('content_type'):
                                content_type = theme_info['content_type']
                            
                            # 简化核心主题：提取关键词，去除描述性内容
                            if theme_info.get('core_theme'):
                                simplified_theme = self._simplify_theme(theme_info['core_theme'])
                                if simplified_theme != theme_info['core_theme']:
                                    self.log(f"   🔄 主题已简化: {theme_info['core_theme']} → {simplified_theme}")
                                    theme_info['core_theme'] = simplified_theme
                            
                            # 如果用户没有设置自定义主题/基调，使用大模型提取的
                            user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                            user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                            
                            # 显示主题分析结果（包含新增字段）
                            if theme_info.get('content_type'):
                                self.log(f"📺 内容类型: {theme_info['content_type']}")
                            
                            if user_custom_theme:
                                theme_info['core_theme'] = user_custom_theme
                            if user_custom_tone:
                                theme_info['visual_tone'] = user_custom_tone
                            
                            self.log(f"🎯 核心主题: {theme_info.get('core_theme', '未指定')}")
                            
                            if theme_info.get('emotional_tone'):
                                self.log(f"💭 情感基调: {theme_info['emotional_tone']}")
                            
                            if theme_info.get('visual_tone'):
                                tone_cn = theme_info['visual_tone']
                                tone_en = theme_info.get('visual_tone_en', '')
                                tone_display = f"{tone_cn} ({tone_en})" if tone_en else tone_cn
                                self.log(f"🎨 视觉基调: {tone_display}")
                            
                            if theme_info.get('visual_style'):
                                self.log(f"🎬 视觉风格: {theme_info['visual_style']}")
                            
                            if theme_info.get('theme_elements'):
                                self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:8])}")
                            
                            if theme_info.get('correction_dict'):
                                self.log(f"🔧 纠错结果: {len(theme_info['correction_dict'])} 处修正")
                                self.log("✅ 主题分析完成，纠错结果将应用到分镜文本")
                            elif analysis_result:
                                self.log("✅ 主题分析完成，文本无需纠错")
                            
                            if analysis_result:
                                _ollama_model_already_loaded = True
                        
                        except Exception as e:
                            self._log_exception(f"   ⚠️ 大模型分析过程出错", e)
                            self.log("   将使用原始语音片段创建分镜")
                            theme_info = {
                                'content_type': '', 
                                'core_theme': '', 
                                'visual_tone': '', 
                                'visual_tone_en': '',
                                'theme_elements': [],
                                'visual_style': '',
                                'visual_style_en': '',
                                'emotional_tone': '',
                                'correction_dict': {}
                            }
                            # 即使大模型分析失败，也要保留用户设置的主题和基调
                            user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                            user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                            # 将用户设置应用到 theme_info
                            if user_custom_theme:
                                theme_info['core_theme'] = user_custom_theme
                                self.log(f"🎯 使用用户指定的核心主题: {user_custom_theme}")
                            if user_custom_tone:
                                theme_info['visual_tone'] = user_custom_tone
                                self.log(f"🎨 使用用户指定的视觉基调: {user_custom_tone}")
                else:
                    self.log(f"⚠️ 文本内容过短({len(full_text)}字符)，跳过大模型主题分析")
                    self.log(f"   💡 提示: 主题分析需要至少20字符的文本内容")
            
            # 步骤3: 生成提示词
            self.log("\n📍 步骤 3/4: 生成分镜提示词")
            self.log("   流程: 语音片段 → 批量生成提示词(含差异化基调)")
            self.update_task_progress("正在准备分镜任务...", 60)
            
            correction_dict = theme_info.get('correction_dict', {})
            
            final_tasks = []
            for seg in original_shot_tasks:
                text = seg.get('text', '').strip()
                if text:
                    text = _ensure_simplified_chinese(text)
                    if correction_dict:
                        for old, new in correction_dict.items():
                            text = text.replace(old, new)
                    for wrong, correct in sorted(_COMMON_ASR_ERROR_DICT.items(), key=lambda x: len(x[0]), reverse=True):
                        if wrong in text:
                            text = text.replace(wrong, correct)
                    known_entities = set()
                    if ENHANCED_RECOGNITION_AVAILABLE:
                        try:
                            from video_generator.enhanced_content_recognition import COUNTRY_MAPPING, ORGANIZATION_MAPPING, MILITARY_MAPPING
                            for mapping in [COUNTRY_MAPPING, ORGANIZATION_MAPPING, MILITARY_MAPPING]:
                                for cn_name in mapping:
                                    known_entities.add(cn_name)
                        except ImportError:
                            pass
                    if theme_info and theme_info.get('theme_elements'):
                        for elem in theme_info['theme_elements']:
                            if elem and len(elem) >= 2:
                                known_entities.add(elem)
                    if theme_info and theme_info.get('core_theme') and len(theme_info['core_theme']) >= 2:
                        for part in re.split(r'[，、,的与和及]', theme_info['core_theme']):
                            p = part.strip()
                            if p and len(p) >= 2:
                                known_entities.add(p)
                    if known_entities:
                        text = _auto_correct_asr(text, known_entities)
                    text = _fix_whisper_repeated_chars(text)
                    text = _ensure_simplified_chinese(text)
                    final_tasks.append({
                        'text': text,
                        'start': seg.get('start', 0),
                        'end': seg.get('end', 0),
                    })
            self.log(f"📝 共 {len(final_tasks)} 个语音片段分镜（已应用纠错）")
            
            # 记录总分镜数，供visual_tone差异化使用
            self._total_shot_count = len(final_tasks)
            
            # 预先为原始分镜生成提示词
            pregenerated_prompts = {}
            
            self.log("\n🎨 预先为原始分镜生成提示词...")
            self.log(f"   📋 流程说明: 先批量生成提示词 → 再创建分镜时直接使用")
            self.log(f"   🎨 视觉基调策略: 全局基调「{theme_info.get('visual_tone', '未指定')}」→ 按分镜内容自动差异化")
            self.update_task_progress(f"正在生成分镜提示词 (0/{len(final_tasks)})...", 62)
            
            if not final_tasks:
                self.log("   ⚠️ 没有分镜数据")
            
            # 获取用户选择的提示词类型
            user_prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
            
            self.log(f"💬 提示词类型: {user_prompt_type}")
            
            if _ollama_model_already_loaded:
                self.log("✅ 模型已在GPU中（主题分析阶段已加载），跳过预热")
            else:
                try:
                    from video_generator.cloud_llm_client import is_cloud_llm_enabled
                    _need_restart = not is_cloud_llm_enabled()
                except ImportError:
                    _need_restart = True
                
                if _need_restart:
                    from video_generator.ollama_client import is_ollama_available
                    if not is_ollama_available():
                        from video_generator.ollama_client import restart_ollama_service
                        self.log("⚠️ Ollama 服务不可用，尝试重启...")
                        restart_ollama_service(log_callback=self.log)
                    else:
                        self.log("✅ Ollama 服务可用")
                
                try:
                    from video_generator.cloud_llm_client import is_cloud_llm_active as _is_cloud_active
                    if _is_cloud_active():
                        self.log("☁️ 云端模式已启用，跳过本地模型预热")
                    else:
                        self.log("🔥 预热模型中...")
                        model = self._get_current_model()
                        if not model:
                            model = "gemma3:4b"
                        warmup_start = time.time()
                        warmup_model(model, log_callback=self.log)
                        warmup_time = time.time() - warmup_start
                        self.log(f"✅ 模型预热完成 ({warmup_time:.1f}秒)")
                except ImportError:
                    self.log("🔥 预热模型中...")
                    try:
                        model = self._get_current_model()
                        if not model:
                            model = "gemma3:4b"
                        warmup_start = time.time()
                        warmup_model(model, log_callback=self.log)
                        warmup_time = time.time() - warmup_start
                        self.log(f"✅ 模型预热完成 ({warmup_time:.1f}秒)")
                    except Exception as e:
                        self._log_exception(f"⚠️ 模型预热失败", e)
                except Exception as e:
                    self._log_exception(f"⚠️ 模型预热失败", e)
            
            # 获取用户预设的风格（高级设置面板）
            user_selected_styles = self.get_selected_styles()
            user_style_override = ""
            if user_selected_styles:
                self.log(f"🎨 用户预设风格: {', '.join(user_selected_styles)}")
                style_descriptions = []
                for style in user_selected_styles:
                    style_desc = self.generate_style_description(style)
                    if style_desc:
                        style_descriptions.append(style_desc)
                if style_descriptions:
                    user_style_override = ", ".join(style_descriptions)
                    display_style = user_style_override[:80] + "..." if len(user_style_override) > 80 else user_style_override
                    self.log(f"   风格关键词: {display_style}")
            
            self.log(f"   开始为 {len(final_tasks)} 个分镜生成提示词...")
            
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            start_time = time.time()
            
            failed_count = 0
            
            try:
                from video_generator.cloud_llm_client import is_cloud_llm_enabled
                _cloud_llm = is_cloud_llm_enabled()
            except ImportError:
                _cloud_llm = False
            
            total_tasks = len(final_tasks)

            self._shot_texts_for_context = [task.get('text', '') for task in final_tasks]
            self._pregenerated_prompts_for_context = {}
            self._pregenerated_understandings_for_context = {}
            self._chinese_semantic_skeletons = {}
            self._visual_narrative_strategy = theme_info.get('visual_narrative_strategy', '')

            BATCH_SIZE = self.batch_size_var.get() if hasattr(self, 'batch_size_var') else 2

            if _cloud_llm:
                prompt_max_workers = 4
                self.log(f"   ☁️ 云端LLM模式，{prompt_max_workers}线程并行生成")
                current_model = self._get_current_model()
                if current_model:
                    check_model_gpu_status(current_model, self.log)

                completed_count = 0
                per_prompt_timeout = max(30, Config.API_TIMEOUT_LLM_PROMPT // max(1, total_tasks))
                total_timeout = Config.API_TIMEOUT_LLM_PROMPT + total_tasks * per_prompt_timeout

                def generate_single_prompt(idx_task):
                    idx, task = idx_task
                    try:
                        dubbing = task.get('text', '')
                        if dubbing:
                            effective_visual_style = user_style_override if user_style_override else theme_info.get('visual_style', '')
                            shot_visual_tone = theme_info.get('visual_tone', '')
                            if hasattr(self, '_diversify_visual_tone') and shot_visual_tone:
                                shot_visual_tone = self._diversify_visual_tone(dubbing, shot_visual_tone, shot_index=idx, total_shots=len(pregenerated_prompts))
                            prompt = self._generate_prompt_with_llm(
                                dubbing,
                                content_type=theme_info.get('content_type', ''),
                                prompt_type=user_prompt_type,
                                core_theme=theme_info.get('core_theme', ''),
                                visual_tone=shot_visual_tone,
                                theme_elements=theme_info.get('theme_elements', []),
                                visual_style=effective_visual_style,
                                original_dubbing=dubbing,
                                full_text=full_text,
                                shot_index=idx
                            )
                            return (idx, prompt, None)
                        return (idx, "", None)
                    except Exception as e:
                        return (idx, "", str(e))

                executor = ThreadPoolExecutor(max_workers=prompt_max_workers)
                future_to_idx = {executor.submit(generate_single_prompt, (idx, task)): idx for idx, task in enumerate(final_tasks)}
                try:
                    for future in as_completed(future_to_idx, timeout=total_timeout):
                        try:
                            idx, prompt, error = future.result(timeout=per_prompt_timeout)
                            if error:
                                failed_count += 1
                                error_display = error[:200] if len(error) > 200 else error
                                self.log(f"   ⚠️ 第{idx+1}个生成失败: {error_display}")
                                pregenerated_prompts[idx] = ""
                            else:
                                pregenerated_prompts[idx] = prompt
                                self._pregenerated_prompts_for_context[idx] = prompt
                        except Exception as e:
                            idx = future_to_idx[future]
                            failed_count += 1
                            pregenerated_prompts[idx] = ""
                            self._log_exception(f"   ⚠️ 第{idx+1}个生成异常", e)
                        completed_count += 1
                        progress_pct = 62 + int((completed_count / total_tasks) * 18)
                        self.update_task_progress(f"正在生成分镜提示词 ({completed_count}/{total_tasks})...", progress_pct)
                except TimeoutError:
                    unfinished = [idx for idx in range(total_tasks) if idx not in pregenerated_prompts or not pregenerated_prompts[idx]]
                    self.log(f"   ⚠️ 提示词生成超时，{len(unfinished)}个未完成（将使用回退生成）")
                    for idx in unfinished:
                        pregenerated_prompts[idx] = ""
                        failed_count += 1
                finally:
                    for f in future_to_idx:
                        f.cancel()
                    executor.shutdown(wait=False)
            else:
                self.log(f"   🚀 本地Ollama模式，批处理生成（每批{BATCH_SIZE}个，共享系统提示词减少开销）")
                current_model = self._get_current_model()
                if current_model:
                    check_model_gpu_status(current_model, self.log)

                num_batches = (total_tasks + BATCH_SIZE - 1) // BATCH_SIZE
                self.log(f"   开始生成 {total_tasks} 个提示词（{num_batches}批，每批最多{BATCH_SIZE}个）...")

                completed_count = 0
                for batch_idx in range(num_batches):
                    if not self.task_running:
                        self.log("❌ 任务已被取消")
                        break

                    start = batch_idx * BATCH_SIZE
                    end = min(start + BATCH_SIZE, total_tasks)
                    batch_items = [(idx, final_tasks[idx]) for idx in range(start, end)]

                    self.log(f"   📦 批次 {batch_idx + 1}/{num_batches}（第{start+1}-{end}个分镜）")

                    batch_results = self._generate_prompts_batch(
                        batch_items, theme_info, user_prompt_type,
                        user_style_override, full_text
                    )

                    batch_failed = 0
                    for original_idx, prompt in batch_results.items():
                        if prompt:
                            pregenerated_prompts[original_idx] = prompt
                            self._pregenerated_prompts_for_context[original_idx] = prompt
                        else:
                            pregenerated_prompts[original_idx] = ""
                            batch_failed += 1
                            failed_count += 1

                    if batch_failed > 0:
                        self.log(f"   ⚠️ 批次 {batch_idx + 1} 中 {batch_failed} 个生成失败，将使用回退生成")

                    completed_count += len(batch_items)
                    progress_pct = 62 + int((completed_count / total_tasks) * 18)
                    self.update_task_progress(f"正在生成分镜提示词 ({completed_count}/{total_tasks})...", progress_pct)
            
            elapsed = time.time() - start_time
            speed = len(pregenerated_prompts) / elapsed if elapsed > 0 else 0
            self.log(f"   完成 {len(pregenerated_prompts)} 个 (速度: {speed:.2f}个/秒)")
            
            duplicate_count = self._check_and_deduplicate_prompts(pregenerated_prompts, final_tasks)
            if duplicate_count > 0:
                self.log(f"   🔄 已去重修正 {duplicate_count} 个重复提示词")
            
            if failed_count > 0:
                self.log(f"⚠️ {failed_count} 个提示词生成失败，使用内置逻辑回退生成")
                for idx, task in enumerate(final_tasks):
                    if idx in pregenerated_prompts and not pregenerated_prompts[idx]:
                        dubbing = task.get('text', '')
                        if dubbing:
                            fallback_parts = {
                                'dubbing': dubbing,
                                'content_type': theme_info.get('content_type', ''),
                                'custom_theme': theme_info.get('core_theme', ''),
                                'custom_visual_tone': theme_info.get('visual_tone', ''),
                                'theme_elements': theme_info.get('theme_elements', []),
                            }
                            if user_prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
                                pregenerated_prompts[idx] = self._generate_arv_format_prompt(fallback_parts, theme_info.get('content_type', ''), 0)
                            elif user_prompt_type == "SD提示词" and ARV_PROMPTS_AVAILABLE:
                                _mt = "sd15"
                                if hasattr(self, 'model_var'):
                                    _mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                                    try:
                                        from video_generator.model_profiles import detect_model_type
                                        _mt = detect_model_type(_mn)
                                    except Exception:
                                        pass
                                _user_styles = self.get_selected_styles() if hasattr(self, 'get_selected_styles') else []
                                pregenerated_prompts[idx] = ARVPromptTemplates.generate_prompt(dubbing, theme_info.get('content_type', ''), theme_info.get('core_theme', ''), theme_info.get('visual_tone', ''), model_type=_mt, user_styles=_user_styles, shot_index=idx)
                            else:
                                pregenerated_prompts[idx] = self._analyze_and_generate_sd_prompt(dubbing, theme_info.get('content_type', ''),
                                    custom_theme=theme_info.get('core_theme', ''),
                                    custom_visual_tone=theme_info.get('visual_tone', ''),
                                    theme_elements=theme_info.get('theme_elements', []),
                                    shot_index=idx)
                            if pregenerated_prompts[idx]:
                                self.log(f"   🔄 第{idx+1}个提示词已通过内置逻辑回退生成")
                                failed_count -= 1
            
            self.log(f"✅ 提示词预生成完成 ({len(pregenerated_prompts)} 个)")
            
            self._review_narrative_coherence(pregenerated_prompts, final_tasks)
            
            self._pregenerated_prompts = pregenerated_prompts
            
            # 步骤4: 创建分镜并后处理
            self.log("\n📍 步骤 4/4: 创建分镜与后处理")
            self.update_task_progress("正在创建分镜...", 80)
            self.log(f"📝 基于语音片段创建分镜（提示词已预生成，将应用差异化基调）")
            
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            global_content_type = theme_info.get('content_type', 'general')
            shot_tasks = []
            for i, task in enumerate(final_tasks):
                shot_text = task['text']
                shot_content_type = global_content_type
                shot_start = task['start']
                shot_end = task['end']
                
                shot_tasks.append((
                    len(shot_tasks),
                    shot_start,
                    shot_end,
                    shot_text,
                    shot_content_type
                ))
            
            # 使用线程池并行创建分镜
            
            # 获取用户设置的线程数（默认8）
            if hasattr(self, 'thread_count_var'):
                thread_count = self.thread_count_var.get()
            else:
                thread_count = 8

            has_unpregenerated = any(
                not pregenerated_prompts.get(i) for i in range(len(final_tasks))
            )
            if has_unpregenerated:
                effective_thread_count = min(thread_count, 2)
                self.log(f"🚀 启动分镜创建: {effective_thread_count}个线程（部分提示词未预生成，限制并发避免LLM过载）")
            else:
                effective_thread_count = min(thread_count, 8)
                self.log(f"🚀 启动多线程分镜创建: {effective_thread_count}个线程并行处理")
            
            completed_count = 0
            shots_dict = {}
            lock = threading.Lock()
            create_start_time = time.time()
            
            # 获取主题信息（优先使用用户自定义的）
            core_theme = user_custom_theme if user_custom_theme else theme_info.get('core_theme', '')
            visual_tone = user_custom_tone if user_custom_tone else theme_info.get('visual_tone', '')
            theme_elements = theme_info.get('theme_elements', [])
            
            def create_shot_task(task_data):
                idx, shot_start, shot_end, shot_text, shot_type = task_data
                
                shot_theme_elements = self._extract_shot_theme_elements(
                    shot_text, theme_elements
                )
                shot = self.create_new_shot(
                    idx, shot_start, shot_end, shot_text, shot_type,
                    core_theme=core_theme,
                    visual_tone=visual_tone,
                    theme_elements=shot_theme_elements
                )
                return idx, shot
            
            with ThreadPoolExecutor(max_workers=effective_thread_count) as executor:
                futures = {executor.submit(create_shot_task, task): task[0] for task in shot_tasks}
                _last_progress_time = time.time()
                
                for future in as_completed(futures):
                    try:
                        idx, shot = future.result(timeout=60)
                        with lock:
                            if shot:
                                shots_dict[idx] = shot
                            completed_count += 1
                            now = time.time()
                            if (now - _last_progress_time >= 0.5) or completed_count == len(shot_tasks):
                                _last_progress_time = now
                                elapsed = time.time() - create_start_time
                                speed = completed_count / elapsed if elapsed > 0 else 0
                                self.log(f"   📊 正在创建分镜: {completed_count}/{len(shot_tasks)} (速度: {speed:.1f}个/秒)")
                                progress = 80 + int(completed_count / len(shot_tasks) * 10) if len(shot_tasks) > 0 else 80
                                self.update_task_progress(f"正在创建分镜: {completed_count}/{len(shot_tasks)}", progress)
                    except Exception as e:
                        task_idx = futures[future]
                        self._log_exception(f"   ⚠️ 创建分镜{task_idx+1}失败", e)
                        try:
                            task_data = shot_tasks[task_idx] if task_idx < len(shot_tasks) else None
                            if task_data:
                                idx, shot = create_shot_task(task_data)
                                if shot:
                                    with lock:
                                        shots_dict[idx] = shot
                                    self.log(f"   🔄 分镜{task_idx+1}重试成功")
                        except Exception as retry_e:
                            self.log(f"   ❌ 分镜{task_idx+1}重试也失败: {str(retry_e)[:60]}")
            
            elapsed_time = time.time() - create_start_time
            
            # 按索引排序
            shots = [shots_dict[i] for i in sorted(shots_dict.keys())]
            self.log(f"✅ 成功创建 {len(shots)} 个分镜（{effective_thread_count}线程并行，耗时 {elapsed_time:.1f}秒，速度 {len(shots)/elapsed_time:.1f}个/秒）")

            self.log("   ✅ 保持原始时间戳，确保音画同步")

            shots_file = os.path.join(self.output_dir, "shots_data.json")

            # 检查分镜是否为空
            if not shots:
                self.log("❌ 未能生成分镜，请检查音频文件是否正确")
                self.update_task_progress("就绪")
                self.root.after(0, lambda: messagebox.showwarning("警告", "未能生成分镜，请检查音频文件是否正确"))
                return
            
            # 后处理：时间戳修复 + 合并过短 + 拆分超长
            self.log("\n🔧 后处理（时间戳修复、合并、拆分）")
            self.update_task_progress("正在后处理分镜数据...", 85)
            
            audio_total_duration = segments[-1].get("end", 0) if segments else 0
            
            self.log("🔍 验证时间戳完整性...")
            total_shots_duration = sum(s['duration'] for s in shots)
            
            # 检测并修复重叠
            overlap_fixed = 0
            for i in range(1, len(shots)):
                prev_end = shots[i-1]['end']
                curr_start = shots[i]['start']
                if curr_start < prev_end:
                    overlap = prev_end - curr_start
                    mid_point = (curr_start + prev_end) / 2.0
                    shots[i-1]['end'] = mid_point
                    shots[i-1]['duration'] = mid_point - shots[i-1]['start']
                    shots[i]['start'] = mid_point
                    shots[i]['duration'] = shots[i]['end'] - mid_point
                    overlap_fixed += 1
            if overlap_fixed > 0:
                self.log(f"   🔧 已修复 {overlap_fixed} 个时间戳重叠")
            
            # 填充间隔：将前一个分镜的end延伸到后一个分镜的start
            gaps_filled = 0
            for i in range(1, len(shots)):
                prev_end = shots[i-1]['end']
                curr_start = shots[i]['start']
                gap = curr_start - prev_end
                if gap > 0.1:
                    shots[i-1]['end'] = curr_start
                    shots[i-1]['duration'] = curr_start - shots[i-1]['start']
                    gaps_filled += 1
            if gaps_filled > 0:
                self.log(f"   🔧 已填充 {gaps_filled} 个时间间隔（延伸前一分镜end）")
            
            # 合并过短分镜与相邻分镜
            min_shot_dur = getattr(self, 'MIN_SHOT_DURATION', 2.0)
            if min_shot_dur < 1.5:
                min_shot_dur = 1.5
            short_merged = 0
            i = 0
            while i < len(shots):
                if shots[i]['duration'] < min_shot_dur:
                    _merged = False
                    _prev_semantic_sim = 0.0
                    _next_semantic_sim = 0.0
                    
                    if i > 0:
                        _prev_semantic_sim = self._semantic_similarity(
                            shots[i-1].get('description', ''), 
                            shots[i].get('description', '')
                        )
                    if i < len(shots) - 1:
                        _next_semantic_sim = self._semantic_similarity(
                            shots[i].get('description', ''), 
                            shots[i+1].get('description', '')
                        )
                    
                    if i > 0 and i < len(shots) - 1:
                        if _prev_semantic_sim >= _next_semantic_sim:
                            self._merge_shots(shots, i-1, i)
                            short_merged += 1
                            _merged = True
                        else:
                            self._merge_shots(shots, i, i+1)
                            short_merged += 1
                            _merged = True
                    elif i > 0:
                        self._merge_shots(shots, i-1, i)
                        short_merged += 1
                        _merged = True
                    elif i < len(shots) - 1:
                        self._merge_shots(shots, i, i+1)
                        short_merged += 1
                        _merged = True
                    
                    if not _merged:
                        i += 1
                    continue
                i += 1
            if short_merged > 0:
                self.log(f"   🔧 已合并 {short_merged} 个过短分镜（< {min_shot_dur}秒）")

            # 拆分超长分镜（单帧超过10秒会导致画面呆板）
            max_shot_dur = 10.0
            split_count = 0
            i = 0
            while i < len(shots):
                if shots[i]['duration'] > max_shot_dur:
                    orig_dur = shots[i]['duration']
                    num_parts = int(orig_dur // max_shot_dur) + (1 if orig_dur % max_shot_dur > 1.0 else 0)
                    if num_parts < 2:
                        num_parts = 2
                    part_dur = orig_dur / num_parts
                    orig_shot = shots[i].copy()
                    desc = orig_shot.get('description', '')
                    desc_parts = self._split_description_semantic(desc, num_parts)

                    new_shots = []
                    for p in range(num_parts):
                        new_shot = orig_shot.copy()
                        new_shot['start'] = round(orig_shot['start'] + p * part_dur, 3)
                        new_shot['end'] = round(orig_shot['start'] + (p + 1) * part_dur, 3)
                        new_shot['duration'] = round(part_dur, 3)
                        new_shot['description'] = desc_parts[p] if p < len(desc_parts) else desc_parts[-1]
                        new_shot['prompt_en'] = self._regenerate_prompt_for_split_shot(
                            new_shot['description'], orig_shot, p, num_parts
                        )
                        sd_model_name = ""
                        if hasattr(self, 'model_var'):
                            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                        new_shot['prompt_en'] = self._build_final_prompt(new_shot['prompt_en'], sd_model_name)
                        new_shot['prompt_quality'] = self._calculate_prompt_quality(
                            new_shot['prompt_en'], new_shot['description']
                        )
                        new_shots.append(new_shot)

                    shots[i:i+1] = new_shots
                    split_count += 1
                    i += num_parts
                    continue
                i += 1

            if split_count > 0:
                self.log(f"   🔧 已拆分 {split_count} 个超长分镜（> {max_shot_dur}秒）")
            
            _prefix_fixed = 0
            _sd_model_name = ""
            if hasattr(self, 'model_var'):
                _sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            for s in shots:
                p = s.get('prompt_en', '')
                if p and 'masterpiece' not in p.lower() and 'best quality' not in p.lower():
                    s['prompt_en'] = self._build_final_prompt(p, _sd_model_name)
                    _prefix_fixed += 1
            if _prefix_fixed > 0:
                self.log(f"   🔧 已补全 {_prefix_fixed} 个分镜的质量前缀")

            _broken_possessive = 0
            for s in shots:
                p = s.get('prompt_en', '')
                if p:
                    p = re.sub(r",?\s*'s\s+", ', ', p)
                    p = re.sub(r",?\s*\b's\b", '', p)
                    p = re.sub(r',\s*,', ',', p)
                    p = re.sub(r'^\s*,|,\s*$', '', p)
                    if p != s.get('prompt_en', ''):
                        s['prompt_en'] = p
                        _broken_possessive += 1
            if _broken_possessive > 0:
                self.log(f"   🔧 已修复 {_broken_possessive} 个破损所有格模式")

            _grammar_broken = 0
            for s in shots:
                p = s.get('prompt_en', '')
                if p:
                    orig_p = p
                    p = re.sub(r'\bbetween\s+and\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\bof\s+on\b', 'on', p, flags=re.IGNORECASE)
                    p = re.sub(r'\bwith\s+and\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\bfrom\s+to\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\band\s*,', ',', p, flags=re.IGNORECASE)
                    p = re.sub(r',\s*\band\s+', ', ', p, flags=re.IGNORECASE)
                    p = re.sub(r'(^|[\s,(])-\w{2,}', r'\1', p)
                    p = re.sub(r'\b\w*ousne\b', '', p)
                    p = re.sub(r'\b\w*icne\b', '', p)
                    p = re.sub(r'\b\w*fulne\b', '', p)
                    p = re.sub(r'\b\w*lessne\b', '', p)
                    p = re.sub(r'\bemphas\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\b\w*ominou\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\b\w*debri\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\bof\s+and\b', '', p, flags=re.IGNORECASE)
                    p = re.sub(r'\bof\s+(\w+ing)\b', r'\1', p, flags=re.IGNORECASE)
                    p = re.sub(r'\b(?:of|in|at|on|for|to|from|by|with)\s*,', ',', p, flags=re.IGNORECASE)
                    p = re.sub(r'  +', ' ', p)
                    p = re.sub(r'\s+,', ',', p)
                    p = re.sub(r',\s*,', ',', p)
                    p = re.sub(r'^\s*,|,\s*$', '', p)
                    if p != orig_p:
                        s['prompt_en'] = p
                        _grammar_broken += 1
            if _grammar_broken > 0:
                self.log(f"   🔧 已修复 {_grammar_broken} 个语法破损短语")

            _syntax_fixed = 0
            _sd_mt = "sd15"
            if hasattr(self, 'model_var'):
                _mn = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
                try:
                    from video_generator.model_profiles import detect_model_type as _dmt
                    _sd_mt = _dmt(_mn)
                except Exception:
                    pass
            for s in shots:
                p = s.get('prompt_en', '')
                if p:
                    fixed = self._validate_sd_syntax(p, _sd_mt)
                    if fixed != p:
                        s['prompt_en'] = fixed
                        _syntax_fixed += 1
            if _syntax_fixed > 0:
                self.log(f"   🔧 已修复 {_syntax_fixed} 个分镜的语法问题")

            _exact_dedup = 0
            _prompt_to_indices = {}
            for _di, s in enumerate(shots):
                p = s.get('prompt_en', '')
                if p:
                    key = p.strip().lower()
                    if key not in _prompt_to_indices:
                        _prompt_to_indices[key] = []
                    _prompt_to_indices[key].append(_di)
            for key, indices in _prompt_to_indices.items():
                if len(indices) > 1:
                    for dup_i, shot_idx in enumerate(indices[1:], 1):
                        s = shots[shot_idx]
                        new_prompt = self._regenerate_prompt_for_split_shot(
                            s.get('description', ''), s, dup_i, len(indices)
                        )
                        if new_prompt and new_prompt.strip().lower() != key:
                            s['prompt_en'] = self._build_final_prompt(new_prompt, _sd_model_name)
                            _exact_dedup += 1
            if _exact_dedup > 0:
                self.log(f"   🔧 已去重 {_exact_dedup} 个跨分镜重复提示词")

            _quality_recalculated = 0
            for s in shots:
                old_q = s.get('prompt_quality', 0)
                new_q = self._calculate_prompt_quality(s.get('prompt_en', ''), s.get('description', ''))
                if abs(new_q - old_q) > 0.01:
                    s['prompt_quality'] = new_q
                    _quality_recalculated += 1
            if _quality_recalculated > 0:
                self.log(f"   🔧 已重算 {_quality_recalculated} 个分镜的质量评分")

            # 确保首尾覆盖整个音频时长
            if shots and audio_total_duration > 0:
                if shots[0]['start'] > 0.1:
                    shots[0]['start'] = 0.0
                    shots[0]['duration'] = shots[0]['end'] - shots[0]['start']
                    self.log(f"   🔧 首分镜起始时间已校准为0.0s")
                if shots[-1]['end'] < audio_total_duration - 0.1:
                    shots[-1]['end'] = audio_total_duration
                    shots[-1]['duration'] = shots[-1]['end'] - shots[-1]['start']
                    self.log(f"   🔧 尾分镜结束时间已校准为{audio_total_duration:.2f}s")
            
            # 重新计算总时长
            total_shots_duration = sum(s['duration'] for s in shots)
            
            if abs(total_shots_duration - audio_total_duration) > 0.1:
                self.log(f"   ⚠️ 时长差异: 分镜{total_shots_duration:.2f}s vs 音频{audio_total_duration:.2f}s")
            else:
                self.log(f"   ✅ 时间戳验证通过")
            
            # 一次性完成：重新编号 + 浮点修复 + 保存
            for j in range(len(shots)):
                shots[j]['id'] = j
                shots[j]['image_file'] = f"shot_{j+1:02d}.png"
                shots[j]['start'] = round(shots[j]['start'], 3)
                shots[j]['end'] = round(shots[j]['end'], 3)
                shots[j]['duration'] = round(shots[j]['duration'], 3)

            with self.resource_lock:
                self.shots_data = shots
            self.state_manager['shots']['generated'] = True
            self.state_manager['shots']['count'] = len(shots)
            self.state_manager['shots']['data'] = None

            self.update_task_progress("正在保存分镜数据...", 95)
            tmp_file = shots_file + ".tmp"
            try:
                with open(tmp_file, 'w', encoding='utf-8') as f:
                    json.dump(shots, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, shots_file)
            except Exception:
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
                with open(shots_file, 'w', encoding='utf-8') as f:
                    json.dump(shots, f, ensure_ascii=False, indent=2)
            self.log(f"   ✅ 分镜数据已保存: {shots_file}")
            
            gaps = []
            for i in range(1, len(shots)):
                prev_end = shots[i-1]['end']
                curr_start = shots[i]['start']
                if curr_start - prev_end > 0.1:
                    gaps.append(i)
            
            if gaps:
                self.log(f"   📊 检测到 {len(gaps)} 个时间间隔，视频合成时将自动填充")
            else:
                self.log(f"   ✅ 时间戳连续无间隔")
            
            # 显示完成信息
            _shots_elapsed = time.time() - _shots_start_time
            _shots_min = int(_shots_elapsed // 60)
            _shots_sec = int(_shots_elapsed % 60)
            
            _diversified_count = sum(1 for s in shots if s.get('visual_tone', '') != theme_info.get('visual_tone', '') and s.get('visual_tone', ''))
            _tone_variants = list(dict.fromkeys(s.get('visual_tone', '') for s in shots if s.get('visual_tone', '')))
            
            self.log("=" * 50)
            self.log("✅ 分镜脚本生成完成！")
            self.log(f"   📊 共 {len(shots)} 个分镜")
            self.log(f"   🎨 基调差异化: {_diversified_count}个分镜应用了差异化基调（共{len(_tone_variants)}种变体）")
            if _tone_variants:
                self.log(f"   🎨 基调变体: {', '.join(_tone_variants[:8])}")
            self.log(f"   ⏱️ 总耗时: {_shots_min}分{_shots_sec}秒 ({_shots_elapsed:.1f}s)")
            self.log(f"   📁 保存位置: {shots_file}")
            self.log("=" * 50)
            
            # 显示分镜内容到脚本区域（已移除脚本窗口，仅记录到日志）
            if hasattr(self, 'txt_script') and self.txt_script:
                def update_script():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本\n\n")
                        for i, shot in enumerate(shots):
                            corrected_description = shot.get('description', '')
                            if corrected_description and hasattr(self, 'clean_text'):
                                corrected_description = self.clean_text(corrected_description)
                            self.txt_script.insert(tk.END, f"## 分镜 {i+1}\n")
                            self.txt_script.insert(tk.END, f"时间: {shot['start']:.2f}s - {shot['end']:.2f}s (时长: {shot['duration']:.2f}s)\n")
                            self.txt_script.insert(tk.END, f"内容: {corrected_description}\n")
                            self.txt_script.insert(tk.END, f"提示词: {shot['prompt_en'][:100]}...\n\n")
                        # 自动模式下不显示弹窗
                        if not auto_mode:
                            messagebox.showinfo("完成", f"分镜脚本生成完成！\n\n共 {len(shots)} 个分镜\n\n下一步：点击「生成视频」自动生成图片并合成视频")
                    except Exception as e:
                        self.log(f"❌ 更新脚本区域失败: {e}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_script)
            
            # 清理预生成的提示词缓存
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            
            gc.collect()
            
            self._unload_ollama_models()

            try:
                from video_generator.cloud_llm_client import is_cloud_llm_active as _is_cloud
                if not _is_cloud():
                    if not check_ollama_available():
                        set_ollama_available_global(False)
                    else:
                        set_ollama_available_global(True)
            except ImportError:
                if not check_ollama_available():
                    set_ollama_available_global(False)
                else:
                    set_ollama_available_global(True)
            
            # 更新进度为完成
            self.update_task_progress("分镜生成完成", 100)
        
        except Exception as e:
            _shots_elapsed = time.time() - _shots_start_time
            _shots_min = int(_shots_elapsed // 60)
            _shots_sec = int(_shots_elapsed % 60)
            self.log(f"❌ 生成分镜失败: {e}")
            self.log(f"   ⏱️ 已耗时: {_shots_min}分{_shots_sec}秒 ({_shots_elapsed:.1f}s)")
            safe_print_exc()
            self.update_task_progress("生成失败", 0)
            return []
        finally:
            try:
                self._unload_ollama_models(log_prefix="🧹 ")
            except Exception:
                pass
            if hasattr(self, 'whisper_model') and self.whisper_model:
                self._safe_release_whisper_gpu()
                del self.whisper_model
                self.whisper_model = None
                self._whisper_on_gpu = False
                self.log("🧹 Whisper模型已完全卸载，内存已释放")
            try:
                gc.collect()
            except Exception:
                pass
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def generate_shots_threaded(self):
        """生成分镜脚本（线程化版本）"""
        if not getattr(self, '_auth_valid', False):
            self.log("⚠️ 请先登录后再操作")
            self._show_login_dialog()
            return
        if not self.audio_path:
            self.log("❌ 没有导入音频文件，无法生成分镜")
            messagebox.showwarning("缺少音频", "请先导入音频文件，再生成分镜脚本！")
            return
        try:
            with self.task_lock:
                if self.task_running:
                    self.log("⚠️ 已有任务正在运行，请稍后再试")
                    return
                self.task_running = True
            
            self._set_action_buttons_state("disabled")
            
            self.log("🎬 开始执行生成分镜脚本任务")
            # 检查2: 输出文件夹中不允许存在分镜脚本文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            if os.path.exists(shots_file):
                self.log("⚠️ 输出文件夹中已存在分镜脚本文件")
                messagebox.showwarning(
                    "分镜脚本已存在",
                    "输出文件夹中已存在分镜脚本文件（shots_data.json）！\n\n"
                    "请先清理输出文件夹中的旧分镜脚本，再执行生成分镜任务。\n\n"
                    "提示：可以在左侧面板点击「清除」按钮清理旧文件。"
                )
                with self.task_lock:
                    self.task_running = False
                self._set_action_buttons_state("normal")
                return
            
            self.log("🎬 开始线程化生成分镜...")
            
            if hasattr(self, 'txt_script') and self.txt_script:
                def clear_script():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception as e:
                        self.log(f"⚠️ 清除脚本失败: {e}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, clear_script)
            
            def generate_shots_worker():
                self.pause_event.set()
                self.log("🎬 开始生成分镜...")
                try:
                    self.generate_shots()
                except Exception as e:
                    self.log(f"❌ 生成分镜过程中出错: {e}")
                    safe_print_exc()
                finally:
                    try:
                        self._unload_ollama_models(log_prefix="🔄 分镜任务结束: ")
                    except Exception:
                        pass
                    try:
                        if hasattr(self, 'whisper_model') and self.whisper_model:
                            self._safe_release_whisper_gpu()
                            del self.whisper_model
                            self.whisper_model = None
                            self._whisper_on_gpu = False
                    except Exception:
                        pass
                    # 注意：不在 finally 中无条件清空 shots_data
                    # 分镜数据已保存到 shots_data.json 文件，内存中保留供后续"生成视频"使用
                    # 仅在任务被取消时才清空内存中的分镜数据
                    with self.task_lock:
                        _was_cancelled = not self.task_running
                    if _was_cancelled:
                        try:
                            if hasattr(self, 'shots_data') and self.shots_data:
                                self.shots_data = []
                        except Exception:
                            pass
                    try:
                        prompt_cache.clear()
                        image_cache.clear()
                    except Exception:
                        pass
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:
                        pass
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    with self.task_lock:
                        was_cancelled = not self.task_running
                        self.task_running = False
                        self.current_task_thread = None
                    self._set_action_buttons_state("normal")
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    if was_cancelled:
                        self.log("⏹️ 分镜生成任务已取消")
                        self.update_task_progress("任务已取消")
                    else:
                        self.log("✅ 分镜生成任务结束")
                        if not getattr(self, '_auto_mode', False):
                            self.log("请点击「🎞️ 生成视频」自动生成图片并合成最终视频")
            
            thread = threading.Thread(target=generate_shots_worker, daemon=True, name="GenerateShotsThread")
            thread.start()
            
            with self.task_lock:
                self.current_task_thread = thread
                
        except Exception as e:
            self.log(f"❌ 生成分镜线程启动失败: {e}")
            safe_print_exc()
            with self.task_lock:
                self.task_running = False


