"""Shot generation mixin - Whisper transcription, prompt generation, theme analysis."""
import os
import json
import time
import threading
import hashlib
import re
import gc
import traceback
import warnings
from video_generator.mixins.logging import safe_print_exc
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import messagebox

from video_generator.config import Config, get_http_session
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
from video_generator.multi_model import LLMPerformanceOptimizer, llm_optimizer
from video_generator.templates import PromptTemplates
from video_generator.parallel import ParallelPromptGenerator
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
    '齐': '齊', '齿': '齒', '龙': '龍', '龟': '龜',
    '罗': '羅', '里': '裡', '纸': '紙', '杆': '桿', '稳': '穩', '矿': '礦',
    '脑': '腦', '给': '給', '装': '裝', '亚': '亞', '个': '個', '织': '織',
    '样': '樣', '觉': '覺', '维': '維', '现': '現', '状': '狀', '贵': '貴',
    '线': '線', '轻': '輕', '说': '說', '卖': '賣', '顾': '顧', '简': '簡',
    '华': '華', '顿': '頓', '债': '債', '邻': '鄰', '虽': '雖', '总': '總',
    '让': '讓', '处': '處', '种': '種', '御': '禦', '后': '後', '经': '經',
    '顶': '頂', '济': '濟', '盘': '盤', '许': '許', '赎': '贖', '赌': '賭',
    '筹': '籌', '码': '碼', '纽': '紐', '彻': '徹', '损': '損', '衬': '襯',
    '贴': '貼', '购': '購', '贷': '貸', '贸': '貿', '费': '費', '贺': '賀',
    '贼': '賊', '赔': '賠', '赚': '賺', '赛': '賽', '赞': '贊', '走': '走',
    '赶': '趕', '起': '起', '超': '超', '越': '越', '趋': '趨', '跌': '跌',
    '跑': '跑', '跟': '跟', '跨': '跨', '跪': '跪', '路': '路', '踪': '蹤',
    '身': '身', '车': '車', '轧': '軋', '轴': '軸', '较': '較', '辈': '輩',
    '辊': '輥', '辍': '輟', '辑': '輯', '辔': '轡', '辕': '轅', '辖': '轄',
    '邓': '鄧', '邮': '郵', '郑': '鄭', '钓': '釣', '铃': '鈴', '铅': '鉛',
    '铢': '銖', '铭': '銘', '铺': '鋪', '锏': '鐧', '门': '門', '闲': '閒',
    '闷': '悶', '闸': '閘', '阁': '閣', '阀': '閥', '阕': '闋', '阑': '闌',
    '阒': '闃', '阖': '闔', '阙': '闕', '陕': '陝', '陪': '陪', '隶': '隸',
    '雇': '僱', '雏': '雛', '麦': '麥', '麸': '麩', '麹': '麴', '麻': '麻',
    '黄': '黃', '黔': '黔', '默': '默', '黛': '黛', '黜': '黜', '黝': '黝',
    '点': '點', '齐': '齊', '龄': '齡', '龀': '齔', '龁': '齕', '龃': '齟',
    '龅': '齙', '龆': '齠', '龇': '齜', '龈': '齦', '龉': '齬', '龊': '齪',
    '龋': '齲', '龌': '齷', '龚': '龔', '龛': '龕',
    '著': '著', '游': '遊', '干': '幹', '系': '係', '面': '面', '后': '後',
    '里': '裡', '发': '發', '复': '復', '制': '製', '板': '闆', '表': '錶',
    '困': '睏', '厂': '廠', '广': '廣', '范': '範', '汇': '匯', '台': '臺',
    '准': '準', '确': '確', '朴': '樸', '筑': '築', '蜡': '蠟', '术': '術',
    '松': '鬆', '舍': '捨', '咸': '鹹', '岩': '巖', '谷': '穀', '征': '徵',
    '致': '緻', '制': '製', '钟': '鐘', '板': '闆', '出': '齣', '沈': '瀋',
    '拓': '搨', '括': '括', '挽': '輓', '搓': '撚', '摸': '摸', '摆': '擺',
    '据': '據', '拟': '擬', '撞': '撞', '操': '操', '支': '支', '收': '收',
    '改': '改', '攻': '攻', '放': '放', '政': '政', '效': '效', '敏': '敏',
    '救': '救', '教': '教', '敬': '敬', '整': '整', '斗': '鬥', '料': '料',
    '斧': '斧', '斯': '斯', '新': '新', '方': '方', '施': '施', '旁': '旁',
    '旅': '旅', '旋': '旋', '族': '族', '既': '既', '日': '日', '明': '明',
    '易': '易', '映': '映', '昨': '昨', '是': '是', '晚': '晚', '晨': '晨',
    '普': '普', '景': '景', '晴': '晴', '智': '智', '暗': '暗', '暴': '暴',
    '更': '更', '替': '替', '最': '最', '月': '月', '有': '有', '朋': '朋',
    '服': '服', '朝': '朝', '期': '期', '未': '未', '末': '末', '本': '本',
    '林': '林', '果': '果', '枝': '枝', '棋': '棋', '森': '森', '植': '植',
    '椅': '椅', '椒': '椒', '概': '概', '榜': '榜', '模': '模', '橙': '橙',
    '橡': '橡', '檀': '檀', '次': '次', '欣': '欣', '正': '正', '此': '此',
    '步': '步', '武': '武', '歧': '歧', '殃': '殃', '段': '段', '毁': '毀',
    '每': '每', '毒': '毒', '比': '比', '民': '民', '水': '水', '永': '永',
    '浦': '浦', '海': '海', '浸': '浸', '涂': '塗', '消': '消', '涉': '涉',
    '深': '深', '混': '混', '添': '添', '清': '清', '渡': '渡', '源': '源',
    '溢': '溢', '溯': '溯', '溶': '溶', '滴': '滴', '漂': '漂', '漏': '漏',
    '演': '演', '漫': '漫', '澄': '澄', '激': '激', '灌': '灌', '泼': '潑',
    '黑': '黑', '鼎': '鼎', '鼓': '鼓', '鼠': '鼠', '鼻': '鼻', '龄': '齡',
}

def _is_traditional_conversion(old, new):
    if old == new:
        return True
    converted = ''.join(_SIMPLIFIED_TO_TRADITIONAL.get(c, c) for c in old)
    if converted == new:
        return True
    return False

_TRADITIONAL_TO_SIMPLIFIED = {v: k for k, v in _SIMPLIFIED_TO_TRADITIONAL.items() if k != v}

def _ensure_simplified_chinese(text):
    if not text:
        return text
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
}

_COMMON_ASR_ERROR_DICT = {
    '零長類': '靈長類', '臨長類': '靈長類', '零长类': '灵长类', '临长类': '灵长类',
    '金花論': '進化論', '金花论': '进化论', '精化论': '进化论', '近化论': '进化论',
    '秋前': '秋千', '秋钱': '秋千',
    '千半年': '千萬年', '千半年': '千万年',
    '分的差': '分了岔', '分的叉': '分了岔',
    '達爾聞': '達爾文', '达尔闻': '达尔文',
    '黑腥腥': '黑猩猩', '黑星星': '黑猩猩',
    '染色提': '染色體', '染色蹄': '染色體',
    '進話論': '進化論', '进话论': '进化论',
    '原長類': '靈長類', '原长类': '灵长类',
    '基恩': '基因',
    '物理學裡': '生物學裡', '物理学里': '生物学里',
    '父子關': '父子關係', '堂兄弟關': '堂兄弟關係',
}

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
                timeout=Config.API_TIMEOUT_LLM_PROMPT
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
                timeout=Config.API_TIMEOUT_LLM_ANALYSIS
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
        
        def _get_visual_elements(prompt):
            if not prompt:
                return set()
            visual_keywords = {
                'dna', 'helix', 'double helix', 'gene', 'genetic', 'chromosome',
                'tree', 'branching', 'evolutionary tree', 'family tree', 'phylogenetic',
                'fossil', 'fossilized', 'skull', 'skeleton', 'bone', 'remains',
                'sediment', 'strata', 'stratified', 'geological', 'layered',
                'paleontologist', 'excavation', 'dig site',
                'forest', 'jungle', 'canopy', 'prehistoric', 'primordial',
                'professor', 'scientist', 'researcher', 'student',
                'laboratory', 'museum',
                'ancient primate', 'hominid', 'early hominid', 'primitive hominid',
                'cave painting', 'stone tool', 'timeline mural', 'comparative anatomy',
                'cell division', 'protein folding',
            }
            prompt_lower = prompt.lower()
            found = set()
            for kw in visual_keywords:
                if kw in prompt_lower:
                    found.add(kw)
            return found
        
        VISUAL_ALTERNATIVES = {
            'dna': ['microscopic cell structure', 'chromosome diagram', 'RNA strand'],
            'helix': ['protein folding', 'gene expression pattern', 'cellular machinery'],
            'double helix': ['twisted ladder metaphor', 'genetic code visualization', 'molecular structure'],
            'gene': ['allele comparison', 'genotype diagram', 'heredity chart'],
            'genetic': ['molecular biology', 'hereditary trait', 'biochemical pathway'],
            'chromosome': ['karyotype display', 'chromatid pair', 'cell nucleus detail'],
            'tree': ['river delta', 'branching coral', 'neural network'],
            'branching': ['diverging path', 'splitting stream', 'forked lightning'],
            'evolutionary tree': ['phylogenetic chart', 'cladogram diagram', 'lineage map'],
            'fossil': ['living habitat reconstruction', 'footprint trackway', 'ancient egg'],
            'fossilized': ['petrified wood', 'amber specimen', 'mineralized imprint'],
            'skull': ['brain cavity cast', 'jaw structure', 'cranial capacity diagram'],
            'skeleton': ['muscular reconstruction', 'body silhouette', 'joint mechanism'],
            'bone': ['cartilage model', 'tissue cross-section', 'growth ring'],
            'sediment': ['erosion pattern', 'riverbed cross-section', 'depositional layer'],
            'strata': ['geological column', 'rock formation', 'cliff face exposure'],
            'stratified': ['banded iron formation', 'layered canyon wall', 'sedimentary fold'],
            'geological': ['tectonic plate boundary', 'volcanic formation', 'mineral vein'],
            'layered': ['laminated rock', 'sedimentary stack', 'depositional sequence'],
            'paleontologist': ['field researcher', 'laboratory analyst', 'science student'],
            'forest': ['open savanna', 'coastal wetland', 'mountain meadow'],
            'prehistoric': ['ancient civilization', 'primordial landscape', 'dawn of time'],
            'primordial': ['volcanic landscape', 'early earth', 'hazy dawn'],
            'ancient primate': ['primate hand grasping tool', 'footprint in volcanic ash', 'nesting site'],
            'hominid': ['bipedal trackway', 'stone tool workshop', 'fire-lit shelter'],
            'cave painting': ['rock art close-up', 'ochre hand stencil', 'animal engraving'],
            'timeline mural': ['chronological scroll', 'era comparison chart', 'epoch diagram'],
            'comparative anatomy': ['hand skeleton comparison', 'skull side-by-side', 'limb bone overlay'],
            'cell division': ['mitosis illustration', 'chromosome separation', 'spindle fiber'],
            'protein folding': ['enzyme active site', 'molecular docking', 'amino acid chain'],
            'museum': ['archive room', 'library study', 'display cabinet'],
            'laboratory': ['field station', 'research vessel', 'outdoor experiment'],
        }
        
        duplicate_count = 0
        indices = sorted(pregenerated_prompts.keys())
        
        # Pass 1: 相邻去重（阈值50%）- 本地替换
        for i in range(1, len(indices)):
            curr_idx = indices[i]
            prev_idx = indices[i - 1]
            curr_prompt = pregenerated_prompts.get(curr_idx, "")
            prev_prompt = pregenerated_prompts.get(prev_idx, "")
            
            if not curr_prompt or not prev_prompt:
                continue
            
            overlap = _token_overlap_ratio(curr_prompt, prev_prompt)
            if overlap > 0.5:
                duplicate_count += 1
                prev_elements = _get_visual_elements(prev_prompt)
                new_prompt = curr_prompt
                for elem in prev_elements:
                    if elem in VISUAL_ALTERNATIVES and elem in new_prompt.lower():
                        alternatives = VISUAL_ALTERNATIVES[elem]
                        import random
                        replacement = random.choice(alternatives)
                        pattern = r'\b' + re.escape(elem) + r'\b'
                        new_prompt = re.sub(pattern, replacement, new_prompt, count=1, flags=re.IGNORECASE)
                if new_prompt != curr_prompt:
                    new_prompt = re.sub(r'(\w+ized)', lambda m: m.group(0).replace('ized', ''), new_prompt)
                    new_prompt = re.sub(r'(\w+ized)\s+(\w+)', r'\2', new_prompt)
                    new_prompt = re.sub(r'\b\w+ized\b', '', new_prompt)
                    new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                    new_prompt = re.sub(r',\s*,', ',', new_prompt)
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
                        import random
                        replacement = random.choice(alternatives)
                        pattern = r'\b' + re.escape(elem) + r'\b'
                        new_prompt = re.sub(pattern, replacement, dup_prompt, count=1, flags=re.IGNORECASE)
                        if new_prompt != dup_prompt:
                            new_prompt = re.sub(r'(\w+ized)', lambda m: m.group(0).replace('ized', ''), new_prompt)
                            new_prompt = re.sub(r'(\w+ized)\s+(\w+)', r'\2', new_prompt)
                            new_prompt = re.sub(r'\b\w+ized\b', '', new_prompt)
                            new_prompt = re.sub(r'\s{2,}', ' ', new_prompt)
                            new_prompt = re.sub(r',\s*,', ',', new_prompt)
                            new_prompt = new_prompt.strip(' ,')
                            pregenerated_prompts[dup_idx] = new_prompt
                            self._pregenerated_prompts_for_context[dup_idx] = new_prompt
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

    def _calculate_prompt_quality(self, prompt_en, dubbing_text):
        """计算提示词质量评分（0.0-1.0）- 增强版，更细粒度
        
        评分维度：
        1. 长度适当性（0.20分）：30-200字符为最佳
        2. 关键词丰富度（0.20分）：逗号分隔的关键词数量
        3. 无中文污染（0.15分）：不含中文字符
        4. 语义相关性（0.20分）：提示词与配音文本的实体重叠
        5. 视觉具体性（0.15分）：包含具体视觉描述词
        6. 构图多样性（0.10分）：包含镜头/构图关键词
        """
        if not prompt_en:
            return 0.0
        
        score = 0.0
        
        prompt_len = len(prompt_en)
        if 50 <= prompt_len <= 180:
            score += 0.20
        elif 30 <= prompt_len < 50:
            score += 0.15
        elif 180 < prompt_len <= 300:
            score += 0.12
        elif 15 <= prompt_len < 30:
            score += 0.08
        elif prompt_len > 10:
            score += 0.03
        
        keywords = [k.strip() for k in prompt_en.split(',') if k.strip()]
        if 10 <= len(keywords) <= 22:
            score += 0.20
        elif 7 <= len(keywords) < 10:
            score += 0.15
        elif 22 < len(keywords) <= 30:
            score += 0.12
        elif 4 <= len(keywords) < 7:
            score += 0.08
        elif len(keywords) >= 3:
            score += 0.04
        
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', prompt_en))
        if not has_chinese:
            score += 0.15
        else:
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', prompt_en))
            if chinese_chars <= 2:
                score += 0.08
            elif chinese_chars <= 5:
                score += 0.03
        
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
                    score += 0.20
                elif entity_hits == 1:
                    score += 0.12
            except ImportError:
                pass
        
        visual_specificity_words = [
            'close-up', 'wide shot', 'medium shot', 'establishing shot', 'aerial',
            'silhouette', 'reflection', 'shadow', 'backlit', 'golden hour',
            'dramatic', 'vivid', 'intricate', 'detailed', 'textured',
            'glowing', 'illuminated', 'weathered', 'ancient', 'modern',
        ]
        prompt_lower = prompt_en.lower()
        visual_hits = sum(1 for w in visual_specificity_words if w in prompt_lower)
        if visual_hits >= 3:
            score += 0.15
        elif visual_hits >= 2:
            score += 0.10
        elif visual_hits >= 1:
            score += 0.05
        
        composition_words = [
            'close-up', 'wide', 'medium', 'establishing', 'overhead',
            'low angle', 'high angle', 'bird\'s eye', 'panoramic', 'portrait',
            'landscape', 'split', 'symmetrical', 'depth of field',
        ]
        comp_hits = sum(1 for w in composition_words if w in prompt_lower)
        if comp_hits >= 1:
            score += 0.10
        elif comp_hits == 0:
            score += 0.02
        
        return round(min(1.0, score), 2)

    def _extract_shot_theme_elements(self, shot_text, global_elements):
        """从分镜文案中提取相关的主题元素 - 增强版
        
        策略：
        1. 精确匹配：元素直接出现在分镜文案中
        2. 关键词关联匹配：通过语义关联词映射
        3. 动态提取：从分镜文本中提取关键名词/概念
        4. 兜底：如果无匹配，返回空列表（不注入无关元素）
        """
        if not global_elements or not shot_text:
            return []

        semantic_map = {
            '地产': ['房', '楼', '万达', '恒大', 'SOHO', '建筑', '楼盘', '物业', '土地'],
            '财富': ['钱', '资产', '富豪', '身价', '亿万', '财富', '资本', '收益'],
            '债务': ['债', '欠', '贷款', '负债', '还债', '资金链', '违约', '杠杆'],
            '风险': ['危险', '危机', '暴雷', '崩塌', '断裂', '凶险', '暴风'],
            '法律': ['法', '刑', '逮捕', '调查', '审判', '违规', '诈骗', '洗钱', '追责', '强制措施'],
            '科技': ['技术', 'AI', '人工智能', '百度', '互联网', '数字化', '芯片'],
            '农业': ['农', '养殖', '饲料', '新希望', '种植'],
            '转型': ['转', '升级', '布局', '多元化', '调整', '改革'],
            '商业': ['商', '市场', '竞争', '资本', '投资', '并购'],
            '权力': ['权', '控制', '掌控', '帝国', '教父', '大佬'],
            '病毒': ['病毒', '感染', '传染', '疫情', '新冠', '德尔塔', '变异'],
            '疫苗': ['疫苗', '接种', '免疫', '抗体', '防感染'],
            '变异': ['变异', '突变', '变异株', '德尔塔', '毒株'],
            '致死率': ['致死', '死亡', '重症', '死亡率', '病死'],
            'ICU': ['ICU', '重症', '呼吸机', '监护', '急救'],
            '基因编辑': ['基因', '编辑', 'DNA', 'CRISPR', '遗传', '基因组'],
            '城市': ['城市', '建筑', '街道', '巷弄', '社区', '胡同', '弄堂'],
            '生命': ['生命', '生存', '活着', '呼吸', '生活'],
            '进化': ['进化', '演化', '進化', '演變', '自然選擇', '自然筛选', '适者生存', '达尔文', '達爾文'],
            '灵长类': ['灵长', '靈長', '猿', '猴', '猩猩', '古人類', '古人猿'],
            '共同祖先': ['祖先', '共同', '起源', '起源地', '根'],
            '基因': ['基因', 'DNA', '遗传', '遺傳', '染色體', '染色体', '双螺旋'],
            '气候变化': ['气候', '氣候', '森林', '环境', '環境', '变暖', '冰川'],
            '文明': ['文明', '文化', '工具', '思考', '智慧', '哲学'],
            '生存': ['生存', '活下去', '适应', '適應', '妥协', '妥協'],
        }

        matched_elements = []
        for elem in global_elements:
            if elem in shot_text:
                matched_elements.append(elem)
                continue
            keywords = semantic_map.get(elem, [])
            if any(kw in shot_text for kw in keywords):
                matched_elements.append(elem)

        if not matched_elements:
            dynamic_keywords = []
            concept_patterns = [
                ('进化', ['进化', '演化', '進化', '演變']),
                ('灵长类', ['灵长', '靈長', '猿', '猴', '猩猩']),
                ('基因', ['基因', 'DNA', '遗传', '遺傳']),
                ('共同祖先', ['祖先', '共同', '起源']),
                ('气候变化', ['气候', '氣候', '森林减少']),
                ('文明', ['文明', '工具', '思考']),
                ('自然选择', ['自然選擇', '自然筛选', '适者生存']),
            ]
            for concept, patterns in concept_patterns:
                if any(p in shot_text for p in patterns):
                    dynamic_keywords.append(concept)
            matched_elements = dynamic_keywords[:3]

        return matched_elements[:3]


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
        # 添加主题元素列表
        if theme_elements:
            description_parts['theme_elements'] = theme_elements
        
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
        
        prompt_quality = self._calculate_prompt_quality(prompt_en, description_parts.get('dubbing', ''))
        optimized_prompt = prompt_en
        
        # 修复：使用Decimal进行高精度时间戳计算，确保duration = end - start
        from decimal import Decimal, ROUND_HALF_UP
        
        start_dec = Decimal(str(start_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        end_dec = Decimal(str(end_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        duration_dec = end_dec - start_dec
        
        # 禁用短分镜强制扩展 - 保持原始语音时长，确保音画同步
        # if duration_dec < Decimal('1.0'):
        #     duration_dec = Decimal('1.0')
        #     end_dec = start_dec + duration_dec
        
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
            # 新增：核心主题和视觉基调字段
            "core_theme": effective_theme if effective_theme else "",
            "visual_tone": effective_visual_tone if effective_visual_tone else "",
            "theme_elements": theme_elements if theme_elements else []
        }

        sd_model_name = ""
        if hasattr(self, 'model_var'):
            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
        shot_data["negative_prompt"] = self._get_custom_negative_prompt(content_type, description_parts['dubbing'], sd_model_name)
        
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
                timeout=Config.API_TIMEOUT_LLM_PROMPT
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
        
        try:
            return self._generate_prompt_with_llm(
                dubbing, content_type,
                prompt_type="ARV写实提示词",
                core_theme=core_theme,
                visual_tone=visual_tone,
                theme_elements=theme_elements
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
                return ARVPromptTemplates.generate_prompt(dubbing, content_type, core_theme, visual_tone)
            return self._analyze_and_generate_sd_prompt(dubbing, content_type)
        
        return self._generate_prompt_with_llm(
            dubbing, content_type, 
            prompt_type="SD提示词", 
            core_theme=core_theme, 
            visual_tone=visual_tone, 
            theme_elements=theme_elements,
            visual_style=visual_style
        )
    

    def _clean_prompt_output(self, raw_output):
        """清洗大模型输出的提示词，移除解释性文字和格式污染
        
        支持两阶段输出格式: [understanding] | [prompt]
        如果检测到此格式，只提取 [prompt] 部分
        
        Args:
            raw_output: 大模型返回的原始输出
            
        Returns:
            清洗后的纯净提示词
        """
        if not raw_output:
            return ""
        
        text = str(raw_output).strip()
        
        # 解析两阶段输出格式: [understanding] | [prompt]
        # 格式1: [some understanding text] | [some prompt text]
        # 格式2: [Understanding]: some text | [Prompt]: some text
        # 格式3: Understanding: some text | Prompt: some text
        
        # 优先尝试格式2/3: [Label]: text | [Label]: text
        label_pipe_match = re.search(
            r'\[(?:Understanding|understanding|Prompt|prompt)\]\s*:\s*.*?\s*\|\s*\[(?:Understanding|understanding|Prompt|prompt)\]\s*:\s*',
            text, re.IGNORECASE | re.DOTALL
        )
        if label_pipe_match:
            after_match = text[label_pipe_match.end():].strip()
            if after_match and len(after_match) > 10:
                text = after_match
        else:
            # 尝试无括号的标签格式: Understanding: text | Prompt: text
            no_bracket_match = re.search(
                r'(?:Understanding|understanding)\s*:\s*.*?\s*\|\s*(?:Prompt|prompt)\s*:\s*',
                text, re.IGNORECASE | re.DOTALL
            )
            if no_bracket_match:
                after_match = text[no_bracket_match.end():].strip()
                if after_match and len(after_match) > 10:
                    text = after_match
            else:
                # 格式1: [text] | [text] - 原始逻辑
                pipe_match = re.search(r'\]\s*\|\s*', text)
                if pipe_match:
                    after_pipe = text[pipe_match.end():].strip()
                    if after_pipe and len(after_pipe) > 10:
                        text = after_pipe
        
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
        full_sentence_patterns = [
            r'[A-Z][a-z]+(?:,\s*(?:as|but|and|or|not)\s+[a-z]+)*\s+(?:is|are|was|were|has|have|had|will|would|can|could|should|must|does|did)\s+[^,]*\.\s*',
            r'It\'?s about\s+[^,]*\.\s*',
            r'This (?:is|means|shows|depicts|represents|conveys|illustrates)\s+[^,]*\.\s*',
            r'(?:China|Russia|Beijing|Moscow|Venezuela|Maduro),?\s+as\s+a\s+[^,]*\.\s*',
            r'(?:The|A|An)\s+(?:key|main|primary|important|central|core)\s+(?:message|point|idea|concept|theme|meaning)\s+[^,]*\.\s*',
        ]
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
        # 清除 "He is distributing" 等描述性句子
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
        text = re.sub(r'\(\s*:[\d.]+\s*\)', '', text)
        text = re.sub(r'\(\s*,\s*\)', '', text)
        
        if len(text.strip()) < 10:
            return raw_output.strip()
        
        sd_model_name = ""
        if hasattr(self, 'model_var'):
            sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
        text = self._build_final_prompt(text, sd_model_name)

        return text.strip()

    def _extract_understanding(self, raw_output):
        """从LLM原始输出中提取understanding部分，用于场景去重"""
        if not raw_output:
            return ""
        text = str(raw_output).strip()
        understanding = ""
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
    

    def _build_final_prompt(self, scene_description, sd_model_name=""):
        """拼接最终提示词：质量前缀 + 模型场景描述 + 风格后缀

        根据制图模型类型自动选择对应的质量前缀/后缀格式：
        - SD 1.5: 带权重标记 (masterpiece, best quality:1.2)
        - SDXL:   无权重标记 RAW photo, photorealistic
        - Flux:   无前缀后缀（自然语言）
        - SD3:    无前缀，轻量后缀

        非写实风格（皮克斯、吉卜力、动漫等）自动移除写实关键词。
        """
        from video_generator.model_profiles import get_model_profile, detect_model_type

        model_type = detect_model_type(sd_model_name)
        profile = get_model_profile(model_type)
        prefix = profile.get("quality_prefix", "")
        suffix = profile.get("quality_suffix", "")

        user_selected_styles = self.get_selected_styles()
        is_non_realistic = False
        non_realistic_keywords = ['pixar', 'ghibli', 'anime', 'cartoon', '3d animation',
                                   'oil painting', 'watercolor', 'van gogh', 'da vinci',
                                   'sketch', 'line art', 'dopamine', 'cyberpunk']
        if user_selected_styles:
            style_text_lower = " ".join(user_selected_styles).lower()
            is_non_realistic = any(kw in style_text_lower for kw in non_realistic_keywords)

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

        redundant = [
            "masterpiece", "best quality", "ultra detailed", "8k",
            "photorealistic", "cinematic lighting", "documentary style",
            "film grain", "high quality", "professional photography",
            "RAW photo", "raw photo", "film grain texture",
            "documentary photography", "photojournalism",
            "raw and authentic", "unposed", "candid shot",
        ]
        cleaned = scene_description
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

        result = ', '.join(parts)
        result = self._validate_sd_syntax(result)
        return result

    def _validate_sd_syntax(self, prompt):
        """SD语法后处理验证：修复常见语法问题"""
        if not prompt:
            return prompt

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

        return text.strip(', ')


    def _generate_prompt_with_llm(self, dubbing, content_type, prompt_type="SD提示词", core_theme="", visual_tone="", theme_elements=None, visual_style="", original_dubbing="", full_text="", shot_index=-1):
        """使用大模型生成提示词 - 只给规则不给案例，让大模型自主创作"""
        if theme_elements is None:
            theme_elements = []
        
        if not is_llm_available():
            self.log("⚠️ 大模型不可用，使用内置逻辑生成提示词")
            if prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
                return self._generate_arv_format_prompt(dubbing, content_type, 0)
            elif prompt_type == "SD提示词" and ARV_PROMPTS_AVAILABLE:
                return ARVPromptTemplates.generate_prompt(dubbing, content_type, core_theme, visual_tone)
            else:
                return self._analyze_and_generate_sd_prompt(dubbing, content_type)
            
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
            "visual_narrative_strategy": getattr(self, '_visual_narrative_strategy', '')
        }
        
        context_hint = ""
        if hasattr(self, '_shot_texts_for_context') and isinstance(dubbing, str):
            shot_texts = self._shot_texts_for_context
            try:
                idx = shot_index if shot_index >= 0 else (shot_texts.index(dubbing) if dubbing in shot_texts else -1)
                if idx >= 0:
                    if hasattr(self, '_pregenerated_prompts_for_context'):
                        prev_prompts = [self._pregenerated_prompts_for_context[j] for j in range(max(0, idx-2), idx) if j in self._pregenerated_prompts_for_context and self._pregenerated_prompts_for_context[j]]
                        if prev_prompts:
                            context_hint += f"AVOID: {', '.join(prev_prompts[-2:])}\n"
                    
                    if hasattr(self, '_pregenerated_understandings_for_context'):
                        prev_understandings = [self._pregenerated_understandings_for_context[j] for j in range(max(0, idx-3), idx) if j in self._pregenerated_understandings_for_context and self._pregenerated_understandings_for_context[j]]
                        if prev_understandings:
                            context_hint += f"PREVIOUS SCENES (do NOT repeat similar scenes):\n"
                            for i, u in enumerate(prev_understandings[-3:]):
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
        
        template_params["context_hint"] = context_hint
        
        if prompt_type == "ARV写实提示词":
            template_key = "shot_prompt_sd"
        else:
            sd_model_name = ""
            if hasattr(self, 'model_var'):
                sd_model_name = self.model_var.get() if hasattr(self.model_var, 'get') else str(self.model_var)
            template_key = PromptTemplates.get_template_key_for_model(sd_model_name)
        
        template = PromptTemplates.get_template(template_key, **template_params)
        
        try:
            llm_config = getattr(self, 'current_llm_config', None)
            result_text, _ = call_ollama_single(
                model=model,
                system_prompt=template["system"],
                user_prompt=template["user"],
                log_callback=self.log,
                num_predict=384,
                num_ctx=1532,
                llm_config=llm_config,
                timeout=Config.API_TIMEOUT_LLM_PROMPT
            )
            
            if result_text:
                raw_output = result_text.strip()
                cleaned_prompt = self._clean_prompt_output(raw_output)
                if cleaned_prompt:
                    understanding = self._extract_understanding(raw_output)
                    if understanding and hasattr(self, '_pregenerated_understandings_for_context') and shot_index >= 0:
                        self._pregenerated_understandings_for_context[shot_index] = understanding
                    return cleaned_prompt
                self.log(f"⚠️ 模型 {model} 输出被清洗后为空，原始输出: {raw_output[:100]}")
            
            raise Exception(f"大模型 {model} 返回为空 (配音: {dubbing[:30]}...)")
        except Exception as e:
            self._log_exception(f"⚠️ 大模型调用失败，回退到内置逻辑生成基础提示词", e)
            self.log(f"   💡 提示: 回退生成的提示词质量较低，建议检查Ollama服务状态")
            if prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
                return ARVPromptTemplates.generate_prompt(dubbing, content_type,
                    core_theme=core_theme, visual_tone=visual_tone)
            return self._analyze_and_generate_sd_prompt(dubbing, content_type,
                custom_theme=core_theme, custom_visual_tone=visual_tone)
    

    def _get_custom_negative_prompt(self, content_type, dubbing, sd_model_name=""):
        """根据制图模型类型和内容生成定制化负面提示词 - 增强版
        
        使用 model_profiles 统一管理基础负面提示词，
        然后根据配音文本内容动态添加针对性的负面提示词
        """
        from video_generator.model_profiles import get_model_profile, detect_model_type

        model_type = detect_model_type(sd_model_name)
        profile = get_model_profile(model_type)

        if not profile.get("needs_negative", True):
            return ""

        user_selected_styles = self.get_selected_styles()
        is_non_realistic = False
        non_realistic_keywords = ['pixar', 'ghibli', 'anime', 'cartoon', '3d animation',
                                   'oil painting', 'watercolor', 'van gogh', 'da vinci',
                                   'sketch', 'line art', 'dopamine', 'cyberpunk']
        if user_selected_styles:
            style_text_lower = " ".join(user_selected_styles).lower()
            is_non_realistic = any(kw in style_text_lower for kw in non_realistic_keywords)

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
        if any(kw in dubbing for kw in ["黑洞", "宇宙", "银河", "恒星", "星云"]):
            additional_negative.extend(["star", "sun", "planet", "moon", "satellite", "human", "person", "face", "building", "tree"])
        if any(kw in dubbing for kw in ["政治", "历史", "古代", "战争"]):
            additional_negative.extend(["modern", "contemporary", "anachronism"])
        
        # 动态检测：含人物的分镜
        person_keywords = ["人", "他", "她", "我", "你", "我们", "他们", "教授", "学生", "科学家",
                          "学者", "研究", "教授", "老師", "博士", "人類", "人类"]
        if any(kw in dubbing for kw in person_keywords):
            additional_negative.extend(["(extra faces:1.2)", "(multiple people:1.1)", "(crowded:1.1)"])
        
        # 动态检测：含动物的分镜
        animal_keywords = ["猴子", "猴", "猿", "猩猩", "黑猩猩", "动物", "動物", "灵长", "靈長",
                          "恐龙", "恐龍", "鸟", "魚", "鱼", "虎", "狮", "象"]
        if any(kw in dubbing for kw in animal_keywords):
            additional_negative.extend(["(deformed animal:1.3)", "(wrong animal anatomy:1.2)", "(extra legs:1.2)"])
        
        # 动态检测：含抽象概念的分镜（避免生成不必要的人物）
        abstract_keywords = ["进化", "進化", "演化", "自然选择", "自然選擇", "基因", "DNA",
                            "文明", "文化", "历史", "歷史", "时间", "時間", "千萬年", "百万年",
                            "链條", "鏈條", "接力", "转折", "轉折"]
        has_abstract = any(kw in dubbing for kw in abstract_keywords)
        has_person = any(kw in dubbing for kw in person_keywords)
        if has_abstract and not has_person:
            additional_negative.extend(["realistic person", "portrait", "face close-up", "selfie"])
        
        # 动态检测：含数字/数据的分镜（避免生成乱码文字）
        data_keywords = ["98%", "百分比", "数据", "數據", "统计", "統計", "比例", "相似度"]
        if any(kw in dubbing for kw in data_keywords):
            additional_negative.extend(["(text:1.3)", "(numbers:1.2)", "(watermark with text:1.2)", "chart with text"])
        
        # 动态检测：含自然景观的分镜
        nature_scene_keywords = ["森林", "树", "丛林", "草原", "山脉", "河流", "海洋", "沙漠"]
        if any(kw in dubbing for kw in nature_scene_keywords):
            additional_negative.extend(["indoor", "room", "wall", "ceiling", "furniture"])

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

    def _analyze_and_generate_sd_prompt(self, text, content_type, custom_theme='', custom_visual_tone=''):
        """分析文本语义并生成SD提示词 - 精简版回退方案（Ollama不可用时使用）"""
        keywords = []
        
        if custom_theme:
            theme_translated = self._translate_to_english(custom_theme)
            keywords.append(theme_translated if theme_translated else custom_theme)
        if custom_visual_tone:
            tone_translated = self._translate_to_english(custom_visual_tone)
            keywords.append(tone_translated if tone_translated else custom_visual_tone)
        
        theme_map = {
            'war': (['戰爭', '战争', '戰鬥', '战斗', '軍事', '军事', '導彈', '导弹', '坦克'], ['war zone', 'military conflict', 'battlefield']),
            'politics': (['政治', '總統', '总统', '總理', '总理', '政府', '部長', '部长'], ['political scene', 'government', 'diplomatic']),
            'economy': (['經濟', '经济', '金融', '股票', '投資', '投资', '商'], ['financial district', 'business', 'economy']),
            'tech': (['科技', '技術', '技术', '科學', '科学', '創新', '创新'], ['technology', 'laboratory', 'innovation']),
            'medical': (['醫生', '医生', '醫院', '医院', '健康', '治療', '治疗'], ['hospital', 'medical', 'healthcare']),
        }
        for key, (triggers, tags) in theme_map.items():
            if any(w in text for w in triggers):
                keywords.extend(tags)
        
        if not keywords:
            keywords.append('realistic scene')
        
        unique_keywords = list(dict.fromkeys(keywords))
        if len(unique_keywords) <= 1:
            unique_keywords = ['realistic scene', 'detailed environment']
        
        quality_tags = 'ultra detailed, hyper realistic, photorealistic, cinematic lighting, professional photography'
        return f"{', '.join(unique_keywords)}, {quality_tags}"
    
    

    def _translate_to_english(self, chinese_text):
        """简单的中文到英文翻译（使用模块级常量，避免重复实例化）"""
        if chinese_text in _TRANSLATION_MAPPING:
            return _TRANSLATION_MAPPING[chinese_text]
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
        """简化核心主题：保留完整语义，仅去除描述性前缀"""
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
                tone_en_map = {
                    '严肃': 'serious, solemn',
                    '紧张': 'tense, suspenseful',
                    '轻松': 'light, relaxed',
                    '温馨': 'warm, cozy',
                    '激昂': 'passionate, stirring',
                    '悲伤': 'sad, melancholic',
                    '欢快': 'cheerful, joyful',
                    '平静': 'calm, peaceful',
                    '震撼': 'shocking, impactful',
                    '忧郁': 'melancholic, gloomy',
                }
                theme_info['visual_tone'] = tone_match
                if tone_match in tone_en_map:
                    theme_info['visual_tone_en'] = tone_en_map[tone_match]
                else:
                    theme_info['visual_tone_en'] = tone_match

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
                            if not part or '→' not in part:
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
                                if _is_traditional_conversion(old, new):
                                    skipped_noop += 1
                                    continue
                                if old != new:
                                    correction_dict[old] = new
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
            
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
            
            self.cache_clear()

            try:
                prompt_cache.clear()
            except Exception:
                pass

            try:
                image_cache.clear()
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

            self.log("🗑️ 已清除所有历史缓存和状态数据，确保使用最新数据")
            
            self.shots_data = []
            
            self._move_output_to_trash(reason="一键生成分镜")
            
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
                    self._safe_release_whisper_gpu()
                    if not self._whisper_on_gpu:
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
                    
                    if cloud_segments is not None:
                        segments = cloud_segments
                        full_text = cloud_text
                        whisper_used_gpu = False
                        
                        self.log(f"✅ 云端语音识别完成，共 {len(segments)} 个片段")
                        
                        cache_data = {'segments': segments, 'full_text': full_text}
                        self.cache_set('audio_analysis', audio_key, cache_data)
                        self.log("✅ 音频分析结果已缓存")
                    else:
                        self.log("⚠️ 云端ASR失败，回退到本地Whisper")
                        cloud_asr_enabled = False
                
                # 本地Whisper语音识别（云端ASR成功时跳过）
                if not cloud_asr_enabled:
                    self.update_task_progress("正在加载Whisper模型...", 20)
                    self._unload_ollama_models(log_prefix="   ")
                    warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")
                    
                    whisper_model_size = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
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
                            import torch
                            import whisper
                            device = "cuda" if torch.cuda.is_available() else "cpu"
                            if device == "cuda":
                                gpu_name = torch.cuda.get_device_name(0)
                                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                                self.log(f"🖥️ 加载Whisper到GPU: {gpu_name} ({gpu_memory:.1f}GB)")
                            else:
                                self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                            self.log(f"   使用模型: Whisper {whisper_model_size}")
                            self.whisper_model = whisper.load_model(whisper_model_size, device=device)
                            self._whisper_model_size = whisper_model_size
                            whisper_model_loaded = True
                            self._whisper_on_gpu = (device == "cuda")
                            whisper_used_gpu = (device == "cuda")
                            self.log(f"✅ Whisper {whisper_model_size} 加载成功 ({'GPU加速' if device == 'cuda' else 'CPU模式'})")
                        except Exception as e:
                            self._log_exception("⚠️ GPU加载失败，回退到CPU", e)
                            try:
                                self.whisper_model = whisper.load_model(whisper_model_size, device="cpu")
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
                        result = self.whisper_model.transcribe(
                            self.audio_path,
                            language="zh",
                            word_timestamps=True,
                            fp16=False,
                            verbose=False,
                            condition_on_previous_text=False,
                            no_speech_threshold=0.3
                        )
                        segments = result.get("segments", [])
                        self.log(f"✅ 语音识别完成，共 {len(segments)} 个片段")
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
                    self._safe_release_whisper_gpu()
                    if not self._whisper_on_gpu:
                        self.log("   ✅ Whisper 模型 GPU 资源已释放")
            
            # 步骤2: 大模型分析文章内容（用于统一分镜基调）
            self.log("\n📍 步骤 2/4: 分析文章内容（用于统一分镜基调）")
            self.log("   流程: 发送文本 → 等待模型分析 → 提取分析结果")
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
                    seg_content_type = self.analyze_content_type(text)
                    original_shot_tasks.append({
                        'text': text,
                        'start': seg_start,
                        'end': seg_end,
                        'content_type': seg_content_type
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
                        self.log(f"   🔄 主题已简化: {theme_info['core_theme']} → {simplified_theme}")
                        theme_info['core_theme'] = simplified_theme
                
                user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                
                if not user_custom_theme and theme_info.get('core_theme'):
                    self.log(f"🎯 核心主题: {theme_info['core_theme']}")
                elif user_custom_theme:
                    theme_info['core_theme'] = user_custom_theme
                    self.log(f"🎯 使用用户指定的核心主题: {user_custom_theme}")
                
                if not user_custom_tone and theme_info.get('visual_tone'):
                    self.log(f"🎨 视觉基调: {theme_info['visual_tone']}")
                elif user_custom_tone:
                    theme_info['visual_tone'] = user_custom_tone
                    self.log(f"🎨 使用用户指定的视觉基调: {user_custom_tone}")
                
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
                            
                            # 获取用户指定的模型
                            user_model = self._get_current_model()
                            
                            # 定义模型优先级列表（包含本地所有已安装的Ollama模型）
                            # 按能力和稳定性排序，推理模型(deepseek-r1)不适合提示词生成
                            model_priority_list = [
                                ("qwen3:8b", 5, "阿里通用模型，推荐首选"),
                                ("qwen2.5:7b", 5, "阿里通用模型，性能优秀"),
                                ("gemma3:4b", 4, "Google通用模型，推荐"),
                                ("qwen3:4b", 4, "阿里通用模型"),
                                ("llama3.2:3b", 3, "Meta轻量级模型"),
                                ("deepseek-r1:8b", 2, "推理模型，不推荐用于提示词生成"),
                                ("gemma3:1b", 1, "轻量级模型，速度快但能力有限"),
                            ]
                            
                            available_models = get_available_models()
                            
                            # 构建候选模型列表（优先使用用户指定的模型，然后按大小排序）
                            candidate_models = []
                            
                            # 首先添加用户指定的模型
                            if user_model in available_models:
                                candidate_models.append(user_model)
                            
                            # 然后按优先级添加其他可用模型（从小到大）
                            for model_name, size, desc in model_priority_list:
                                if model_name in available_models and model_name not in candidate_models:
                                    candidate_models.append(model_name)
                            
                            # 如果没有可用模型，使用默认列表
                            if not candidate_models:
                                candidate_models = ["gemma3:4b", "gemma3:1b", "deepseek-r1:8b", "mistral", "llama3"]
                                self.log("⚠️ 未检测到本地模型，使用默认候选列表")
                            
                            self.log(f"🤖 启动大模型分析...")
                            self.log(f"   用户指定模型: {user_model}")
                            self.log(f"   可用模型数: {len(available_models)}个")
                            self.log(f"   候选模型数: {len(candidate_models)}个")
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
                                try:
                                    custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                                    custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                                    
                                    # 使用新的主题分析模板
                                    template = PromptTemplates.get_template("theme_analysis", text=full_text)
                                    
                                    if custom_theme or custom_visual_tone:
                                        user_addition = f"\n\n【用户指定的核心主题】: {custom_theme}" if custom_theme else ""
                                        user_addition += f"\n【用户指定的视觉基调】: {custom_visual_tone}" if custom_visual_tone else ""
                                        system_content = template["system"]
                                        user_content = template["user"] + user_addition
                                    else:
                                        system_content = template["system"]
                                        user_content = template["user"]
                                    
                                    result_content, _ = call_ollama_single(
                                        model=model_name,
                                        system_prompt=system_content,
                                        user_prompt=user_content,
                                        log_callback=self.log,
                                        num_predict=2000,
                                        num_ctx=8192,
                                        llm_config=getattr(self, 'current_llm_config', None),
                                        timeout=Config.API_TIMEOUT_LLM_ANALYSIS
                                    )
                                    
                                    if not result_content:
                                        raise Exception(f"大模型 {model_name} 主题分析返回为空")
                                    
                                    result_content = result_content.strip()
                                    
                                    self.log(f"   🔍 调试: 原始响应内容: {repr(result_content[:200])}")
                                    
                                    return result_content
                                except Exception as e:
                                    raise e
                            
                            # 尝试调用模型，失败时自动切换
                            analysis_result = ""
                            current_model_index = 0
                            max_retries = len(candidate_models)
                            
                            try:
                                with ThreadPoolExecutor(max_workers=1) as analysis_executor:
                                    while current_model_index < max_retries and not analysis_result:
                                        current_model = candidate_models[current_model_index]
                                        
                                        self.log(f"\n   [{current_model_index + 1}/{max_retries}] 尝试使用模型: {current_model}")
                                        
                                        try:
                                            future = analysis_executor.submit(call_ollama_with_model, current_model)
                                            self.log(f"   等待模型分析中...")
                                            
                                            start_time = time.time()
                                            analysis_result = future.result(timeout=180)
                                            elapsed_time = time.time() - start_time
                                            
                                            if analysis_result:
                                                self.log(f"✅ 模型 {current_model} 分析完毕！")
                                                self.log(f"   响应时间: {elapsed_time:.1f}秒")
                                                self.log(f"   响应长度: {len(analysis_result)} 字符")
                                                self.log(f"   响应内容预览: {analysis_result[:100]}...")
                                                
                                                if current_model != user_model:
                                                    self.log(f"⚠️ 提醒: 已自动切换到备用模型 {current_model}")
                                                    self.log(f"   原因: 用户指定的模型 {user_model} 无响应或调用失败")
                                                break
                                            else:
                                                self.log(f"⚠️ 模型 {current_model} 返回空结果")
                                                self.log(f"   🔍 请检查上方的调试日志以了解详情")
                                                current_model_index += 1
                                                
                                        except TimeoutError:
                                            self.log(f"⚠️ 模型 {current_model} 响应超时（超过180秒）")
                                            self.log(f"   可能原因: 模型计算量大或GPU资源不足")
                                            current_model_index += 1
                                            
                                            if current_model_index < max_retries:
                                                next_model = candidate_models[current_model_index]
                                                self.log(f"   自动切换到下一个模型: {next_model}")
                                                time.sleep(1)
                                        except Exception as e:
                                            error_msg = str(e).lower()
                                            self._log_exception(f"⚠️ 模型 {current_model} 调用失败", e)
                                            
                                            if "connection" in error_msg or "refused" in error_msg:
                                                self.log(f"   ❌ Ollama服务连接失败，停止尝试")
                                                break
                                            
                                            current_model_index += 1
                                            
                                            if current_model_index < max_retries:
                                                next_model = candidate_models[current_model_index]
                                                self.log(f"   自动切换到下一个模型: {next_model}")
                                                time.sleep(0.5)
                            except Exception as e:
                                self._log_exception("⚠️ 分析步骤异常", e)
                            
                            # 如果所有模型都失败
                            if not analysis_result:
                                self.log(f"\n❌ 所有候选模型均调用失败（共尝试 {max_retries} 个模型）")
                                self.log(f"   候选模型列表: {', '.join(candidate_models)}")
                                self.log(f"   建议: 请检查Ollama服务是否正常运行，或安装上述模型")
                                set_ollama_available_global(False)
                                self.log("🧹 Ollama标记为不可用，GPU显存将在空闲时自动释放")
                                analysis_result = ""
                            
                            # 缓存分析结果（即使是空结果也缓存，避免重复失败）
                            if analysis_result:
                                self.cache_set('analysis', analysis_key, analysis_result)
                                self.log("✅ 大模型分析结果已缓存")
                            
                            # 解析分析结果 - 只提取主题信息，不生成分镜
                            self.update_task_progress("正在提取分析结果...", 55)
                            
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
                            
                            if not user_custom_theme and theme_info.get('core_theme'):
                                self.log(f"🎯 核心主题: {theme_info['core_theme']}")
                            elif user_custom_theme:
                                theme_info['core_theme'] = user_custom_theme
                                self.log(f"🎯 使用用户指定的核心主题: {user_custom_theme}")
                            
                            if theme_info.get('emotional_tone'):
                                self.log(f"💭 情感基调: {theme_info['emotional_tone']}")
                            
                            if not user_custom_tone and theme_info.get('visual_tone'):
                                self.log(f"🎨 视觉基调: {theme_info['visual_tone']}")
                            elif user_custom_tone:
                                theme_info['visual_tone'] = user_custom_tone
                                self.log(f"🎨 使用用户指定的视觉基调: {user_custom_tone}")
                            
                            if theme_info.get('visual_style'):
                                self.log(f"🎬 视觉风格: {theme_info['visual_style']}")
                            
                            if theme_info.get('theme_elements'):
                                self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:8])}")
                            
                            if theme_info.get('correction_dict'):
                                self.log(f"🔧 大模型纠错结果: {theme_info['correction_dict']}")
                                self.log("✅ 主题分析完成，纠错结果将应用到分镜文本")
                            else:
                                self.log("✅ 主题分析完成，文本无需纠错")
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
            
            # 步骤2.5: 使用原始语音片段（每个语音片段对应一个分镜）
            self.log("\n📍 步骤 2.5/4: 准备分镜任务")
            self.update_task_progress("正在准备分镜任务...", 60)
            
            correction_dict = theme_info.get('correction_dict', {})
            
            final_tasks = []
            for seg in original_shot_tasks:
                text = seg.get('text', '').strip()
                if text:
                    if correction_dict:
                        for old, new in correction_dict.items():
                            text = text.replace(old, new)
                    for wrong, correct in _COMMON_ASR_ERROR_DICT.items():
                        if wrong in text:
                            text = text.replace(wrong, correct)
                    text = _fix_whisper_repeated_chars(text)
                    text = _ensure_simplified_chinese(text)
                    seg_content_type = self.analyze_content_type(text)
                    final_tasks.append({
                        'text': text,
                        'start': seg.get('start', 0),
                        'end': seg.get('end', 0),
                        'content_type': seg_content_type
                    })
            self.log(f"📝 共 {len(final_tasks)} 个语音片段分镜（已应用纠错）")
            
            # 预先为原始分镜生成提示词
            pregenerated_prompts = {}
            
            self.log("\n🎨 预先为原始分镜生成提示词...")
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
            
            def generate_single_prompt(idx_task):
                """单个提示词生成任务"""
                idx, task = idx_task
                try:
                    dubbing = task.get('text', '')
                    if dubbing:
                        effective_visual_style = user_style_override if user_style_override else theme_info.get('visual_style', '')
                        effective_visual_tone = theme_info.get('visual_tone_en', '') or theme_info.get('visual_tone', '')
                        
                        prompt = self._generate_prompt_with_llm(
                            dubbing, 
                            content_type=theme_info.get('content_type', ''), 
                            prompt_type=user_prompt_type,
                            core_theme=theme_info.get('core_theme', ''),
                            visual_tone=effective_visual_tone,
                            theme_elements=theme_info.get('theme_elements', []),
                            visual_style=effective_visual_style,
                            original_dubbing=dubbing,
                            full_text=full_text,
                            shot_index=idx
                        )
                        return (idx, prompt, None)
                    return (idx, "", None)
                except Exception as e:
                    full_error = str(e)
                    return (idx, "", full_error)
            
            try:
                from video_generator.cloud_llm_client import is_cloud_llm_enabled
                _cloud_llm = is_cloud_llm_enabled()
            except ImportError:
                _cloud_llm = False
            
            if _cloud_llm:
                prompt_max_workers = 4
                self.log(f"   ☁️ 云端LLM模式，{prompt_max_workers}线程并行生成")
            else:
                prompt_max_workers = 1
                self.log(f"   💡 本地Ollama模式，串行生成（Ollama内部串行处理，多线程仅增加排队开销）")
                current_model = self._get_current_model()
                if current_model:
                    check_model_gpu_status(current_model, self.log)
            
            total_tasks = len(final_tasks)
            mode_desc = "串行" if prompt_max_workers == 1 else f"{prompt_max_workers}线程并行"
            self.log(f"   开始生成 {total_tasks} 个提示词（{mode_desc}）...")
            
            self._shot_texts_for_context = [task.get('text', '') for task in final_tasks]
            self._pregenerated_prompts_for_context = {}
            self._pregenerated_understandings_for_context = {}
            self._visual_narrative_strategy = theme_info.get('visual_narrative_strategy', '')

            completed_count = 0
            per_prompt_timeout = max(30, Config.API_TIMEOUT_LLM_PROMPT // max(1, total_tasks))
            total_timeout = Config.API_TIMEOUT_LLM_PROMPT + total_tasks * per_prompt_timeout
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
                            if user_prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
                                pregenerated_prompts[idx] = self._generate_arv_format_prompt(dubbing, theme_info.get('content_type', ''), 0)
                            elif user_prompt_type == "SD提示词" and ARV_PROMPTS_AVAILABLE:
                                pregenerated_prompts[idx] = ARVPromptTemplates.generate_prompt(dubbing, theme_info.get('content_type', ''), theme_info.get('core_theme', ''), theme_info.get('visual_tone', ''))
                            else:
                                pregenerated_prompts[idx] = self._analyze_and_generate_sd_prompt(dubbing, theme_info.get('content_type', ''))
                            if pregenerated_prompts[idx]:
                                self.log(f"   🔄 第{idx+1}个提示词已通过内置逻辑回退生成")
                                failed_count -= 1
            
            self.log(f"✅ 提示词预生成完成 ({len(pregenerated_prompts)} 个)")
            
            self._pregenerated_prompts = pregenerated_prompts
            
            # 步骤3: 创建分镜
            self.log("\n📍 步骤 3/4: 创建分镜")
            self.update_task_progress("正在创建分镜...", 80)
            self.log(f"📝 基于语音片段创建分镜（提示词已预生成）")
            
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
            
            # 获取用户设置的线程数（默认16）
            if hasattr(self, 'thread_count_var'):
                thread_count = self.thread_count_var.get()
            else:
                thread_count = 16
            
            self.log(f"🚀 启动多线程分镜创建: {thread_count}个线程并行处理")
            
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
            
            with ThreadPoolExecutor(max_workers=thread_count) as executor:
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
            self.log(f"✅ 成功创建 {len(shots)} 个分镜（{thread_count}线程并行，耗时 {elapsed_time:.1f}秒，速度 {len(shots)/elapsed_time:.1f}个/秒）")

            self.log("   ✅ 保持原始时间戳，确保音画同步")

            # 立即保存分镜数据（先保存再验证，确保文件不延迟）
            with self.resource_lock:
                self.shots_data = shots
            self.state_manager['shots']['generated'] = True
            self.state_manager['shots']['count'] = len(shots)
            self.state_manager['shots']['data'] = None
            
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump(shots, f, ensure_ascii=False, indent=2)
            self.log(f"   ✅ 分镜数据已保存: {shots_file}")

            self._unload_ollama_models()

            # 云端生图启用时，额外释放Whisper GPU（后续图像生成不需要本地GPU）
            cloud_img = False
            try:
                from video_generator.cloud_image_client import is_cloud_image_enabled
                cloud_img = is_cloud_image_enabled()
            except ImportError:
                pass
            if cloud_img:
                self._safe_release_whisper_gpu()
                if not self._whisper_on_gpu:
                    self.log("   🧹 Whisper GPU 显存已释放（云端生图模式）")

            # 检查分镜是否为空
            if not shots:
                self.log("❌ 未能生成分镜，请检查音频文件是否正确")
                self.update_task_progress("就绪")
                self.root.after(0, lambda: messagebox.showwarning("警告", "未能生成分镜，请检查音频文件是否正确"))
                return
            
            # 步骤4: 验证和完成
            self.log("\n📍 步骤 4/4: 验证分镜数据")
            self.update_task_progress("正在验证分镜数据...", 91)
            
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
            
            # 合并过短分镜（< 2.0秒）与相邻分镜
            MIN_SHOT_DURATION = 2.0
            short_merged = 0
            i = 0
            while i < len(shots):
                if shots[i]['duration'] < MIN_SHOT_DURATION:
                    if i > 0 and i < len(shots) - 1:
                        prev_dur = shots[i-1]['duration']
                        next_dur = shots[i+1]['duration']
                        if prev_dur <= next_dur:
                            shots[i-1]['description'] = shots[i-1]['description'] + shots[i]['description']
                            shots[i-1]['end'] = shots[i]['end']
                            shots[i-1]['duration'] = shots[i-1]['end'] - shots[i-1]['start']
                            shots.pop(i)
                            short_merged += 1
                            continue
                        else:
                            shots[i+1]['description'] = shots[i]['description'] + shots[i+1]['description']
                            shots[i+1]['start'] = shots[i]['start']
                            shots[i+1]['duration'] = shots[i+1]['end'] - shots[i+1]['start']
                            shots.pop(i)
                            short_merged += 1
                            continue
                    elif i > 0:
                        shots[i-1]['description'] = shots[i-1]['description'] + shots[i]['description']
                        shots[i-1]['end'] = shots[i]['end']
                        shots[i-1]['duration'] = shots[i-1]['end'] - shots[i-1]['start']
                        shots.pop(i)
                        short_merged += 1
                        continue
                    elif i < len(shots) - 1:
                        shots[i+1]['description'] = shots[i]['description'] + shots[i+1]['description']
                        shots[i+1]['start'] = shots[i]['start']
                        shots[i+1]['duration'] = shots[i+1]['end'] - shots[i+1]['start']
                        shots.pop(i)
                        short_merged += 1
                        continue
                i += 1
            if short_merged > 0:
                self.log(f"   🔧 已合并 {short_merged} 个过短分镜（< {MIN_SHOT_DURATION}秒）")
                self.update_task_progress("正在合并过短分镜...", 93)
                for j in range(len(shots)):
                    shots[j]['id'] = j
                with open(shots_file, 'w', encoding='utf-8') as f:
                    json.dump(shots, f, ensure_ascii=False, indent=2)
                self.log(f"   ✅ 合并后分镜数据已重新保存: {shots_file}")
            
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
            
            self.update_task_progress("正在保存分镜数据...", 95)
            
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump(shots, f, ensure_ascii=False, indent=2)
            self.log(f"   ✅ 验证后分镜数据已保存: {shots_file}")
            
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
            self.log("=" * 50)
            self.log("✅ 分镜脚本生成完成！")
            self.log(f"   📊 共 {len(shots)} 个分镜")
            self.log(f"   ⏱️ 总耗时: {_shots_min}分{_shots_sec}秒 ({_shots_elapsed:.1f}s)")
            self.log(f"   📁 保存位置: {shots_file}")
            self.log("")
            self.log("📋 下一步操作：")
            self.log("   1. 点击「🎨 生成图片」生成分镜画面")
            self.log("   2. 点击「🎞️ 生成视频」合成最终视频")
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
                            messagebox.showinfo("完成", f"分镜脚本生成完成！\n\n共 {len(shots)} 个分镜\n\n下一步：点击「生成图片」生成分镜画面")
                    except Exception as e:
                        self.log(f"❌ 更新脚本区域失败: {e}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_script)
            
            # 清理预生成的提示词缓存
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            
            gc.collect()
            
            self._unload_ollama_models()
            
            from video_generator.ollama_client import check_ollama_available
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
            if hasattr(self, 'whisper_model') and self.whisper_model:
                self._safe_release_whisper_gpu()
                if not self._whisper_on_gpu:
                    self.log("🧹 Whisper GPU显存已释放")
                if whisper_model_loaded:
                    del self.whisper_model
                    self.whisper_model = None
                    self._whisper_on_gpu = False
                    gc.collect()
                    self.log("🧹 Whisper模型已完全卸载，内存已释放")
    

    def generate_shots_threaded(self):
        """生成分镜脚本（线程化版本）"""
        try:
            with self.task_lock:
                if self.task_running:
                    self.log("⚠️ 已有任务正在运行，请稍后再试")
                    return
                self.task_running = True
            
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
                    with self.task_lock:
                        self.task_running = False
                        self.current_task_thread = None
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    self.log("✅ 分镜生成任务结束")
            
            thread = threading.Thread(target=generate_shots_worker, daemon=True, name="GenerateShotsThread")
            thread.start()
            
            with self.task_lock:
                self.current_task_thread = thread
                
        except Exception as e:
            self.log(f"❌ 生成分镜线程启动失败: {e}")
            safe_print_exc()
            with self.task_lock:
                self.task_running = False


