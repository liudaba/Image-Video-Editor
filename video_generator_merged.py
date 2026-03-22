# -*- coding: utf-8 -*-
"""
短视频生成器 - 模块化合并版

将多模块代码合并为单文件，便于分发和使用。

功能：
1. 语音转录 -> 分镜脚本生成
2. AI 绘图提示词优化 -> 批量图片生成
3. 图片序列 -> 视频渲染

使用方法：
    python video_generator_merged.py
"

import sys
import os
import warnings
import datetime
import threading
import time
import json
import re
import base64
import hashlib
from datetime import datetime
from typing import Optional, Tuple, Callable, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future, as_completed

# 忽略 requests 库的依赖版本警告
warnings.filterwarnings(
    "ignore",
    message="urllib3.*doesn't match a supported version",
    module="requests"
)


# ======================================================================# 模块: config# ======================================================================
配置模块 - 集中管理所有配置项
"""

import os

# ==================== 路径配置 ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output_project")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ==================== API 配置 ====================
SD_API_URL = "http://127.0.0.1:7860"  # 秋叶 SD 默认地址
MAX_RETRY_COUNT = 3  # API 调用最大重试次数
RETRY_DELAY = 2  # 重试延迟（秒）

# ==================== 视频配置 ====================
DEFAULT_MIN_SHOT_DURATION = 4.0  # 默认最小分镜时长（秒）
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30

# ==================== UI 配置 ====================
UI_CONFIG = {
    "window_title": "DocuMaker Pro Lite V7 | 智能分镜工作流",
    "default_width": 1000,
    "default_height": 700,
    "min_width": 800,
    "min_height": 600,
    "resize_delay": 200,  # 防抖延迟（毫秒）
}

# ==================== 颜色配置 ====================
COLORS = {
    "bg_color": "#1e1e1e",
    "panel_bg": "#252526",
    "text_fg": "#d4d4d4",
    "accent_blue": "#2196f3",
    "accent_red": "#f44336",
    "btn_mid_bg": "#3c3f41",
    "progress_bar": "#00FF00",
    "progress_trough": "#1a1a1a",
}

# ==================== 字体配置 ====================
FONT_CONFIG = {
    "family": "Microsoft YaHei",
    "base_size": 12,
    "header_size": 16,
    "title_size": 20,
}

# ==================== 任务配置 ====================
TASK_PRIORITY = {
    'generate_shots': 3,      # 最高优先级
    'generate_images': 2,     # 中优先级
    'generate_video': 1       # 低优先级
}

TASK_STATUS = {
    'queued': '排队中',
    'running': '执行中',
    'paused': '已暂停',
    'completed': '已完成',
    'failed': '失败',
    'cancelled': '已取消'
}

# ==================== 过渡效果配置 ====================
TRANSITIONS = {
    "硬切": None,
    "淡入淡出": "fade",
    "滑动": "slide",
    "缩放": "zoom",
    "旋转": "rotate"
}

# ==================== 动画效果配置 ====================
ANIMATIONS = {
    "无": None,
    "缓慢缩放": "slow_zoom",
    "左右平移": "pan_horizontal",
    "上下平移": "pan_vertical",
    "组合动画": "combined"
}

# ==================== 默认配置 ====================
DEFAULT_CONFIG = {
    "api_type": "Stable Diffusion API",
    "sd_api_url": SD_API_URL,
    "optimization_method": "脚本自带",
    "ollama_model": "",
    "llm_config_preset": "质量优先",
    "transition": "硬切",
    "width": DEFAULT_WIDTH,
    "height": DEFAULT_HEIGHT,
    "model": "不选择",
    "prompt_type": "SD提示词",
    "animation": "无",
    "custom_theme": "",
    "custom_visual_tone": "",
}

# ==================== 辅助函数 ====================
def ensure_directories():
    """确保必要的目录存在"""
    for dir_path in [OUTPUT_DIR, IMAGES_DIR]:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
    return OUTPUT_DIR, IMAGES_DIR


def get_font_config(scaled_size=None):
    """获取字体配置"""
    config = FONT_CONFIG.copy()
    if scaled_size:
        config["base_size"] = scaled_size
    return config

# ======================================================================#
# 模块: utils.text
# ======================================================================#
"""文本处理工具"""

import re
import string
from typing import List, Optional


def clean_text(text: str) -> str:
    """
    清理文本，移除多余空白和特殊字符
    
    Args:
        text: 原始文本
    
    Returns:
        清理后的文本
    """
    if not text:
        return ""
    
    # 移除多余空白
    text = re.sub(r'\s+', ' ', text)
    
    # 移除首尾空白
    text = text.strip()
    
    return text


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """
    从文本中提取关键词
    
    Args:
        text: 输入文本
        max_keywords: 最大关键词数量
    
    Returns:
        关键词列表
    """
    if not text:
        return []
    
    # 简单的关键词提取（实际应用中可以使用更复杂的算法）
    # 移除标点符号
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # 分词（简单按空格分割，中文需要分词库）
    words = text.split()
    
    # 过滤短词和常见停用词
    stopwords = {'的', '是', '在', '了', '和', '与', '或', '等', '也', '都',
                 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'shall'}
    
    keywords = [
        word for word in words
        if len(word) >= 2 and word.lower() not in stopwords
    ]
    
    # 去重并限制数量
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)
            if len(unique_keywords) >= max_keywords:
                break
    
    return unique_keywords


def extract_number(text: str) -> Optional[float]:
    """
    从文本中提取数字
    
    Args:
        text: 包含数字的文本
    
    Returns:
        提取的数字或 None
    """
    if not text:
        return None
    
    # 匹配整数和小数
    match = re.search(r'[-+]?\d*\.?\d+', text)
    
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    
    return None


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本到指定长度
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
    
    Returns:
        截断后的文本
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def count_words(text: str) -> int:
    """
    统计文本字数（中英文混合）
    
    Args:
        text: 输入文本
    
    Returns:
        字数
    """
    if not text:
        return 0
    
    # 统计中文字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    
    # 统计英文单词
    english_words = len(re.findall(r'[a-zA-Z]+', text))
    
    return chinese_chars + english_words


def split_sentences(text: str) -> List[str]:
    """
    将文本分割成句子
    
    Args:
        text: 输入文本
    
    Returns:
        句子列表
    """
    if not text:
        return []
    
    # 按中英文句号、问号、感叹号分割
    sentences = re.split(r'[。！？.!?]+', text)
    
    # 过滤空句子并去除首尾空白
    return [s.strip() for s in sentences if s.strip()]

# ======================================================================# 模块: utils.audio# ======================================================================
音频处理工具
"""

import os
import threading
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class AudioSegment:
    """音频片段数据类"""
    start: float      # 开始时间（秒）
    end: float        # 结束时间（秒）
    text: str         # 文本内容
    confidence: float # 置信度


class AudioProcessor:
    """音频处理器"""
    
    def __init__(self):
        self._whisper_model = None
        self._model_lock = threading.Lock()
    
    def load_whisper_model(self, model_size: str = "base"):
        """
        加载 Whisper 模型
        
        Args:
            model_size: 模型大小 (tiny, base, small, medium, large)
        """
        with self._model_lock:
            if self._whisper_model is None:
                try:
                    import whisper
                    self._whisper_model = whisper.load_model(model_size)
                except ImportError:
                    raise RuntimeError("Whisper 未安装，请运行: pip install openai-whisper")
            return self._whisper_model
    
    def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
        model_size: str = "base"
    ) -> Tuple[str, List[AudioSegment]]:
        """
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            language: 语言代码
            model_size: 模型大小
        
        Returns:
            (完整文本, 音频片段列表)
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")
        
        model = self.load_whisper_model(model_size)
        
        # 转录音频
        result = model.transcribe(audio_path, language=language)
        
        # 提取完整文本
        full_text = result.get("text", "")
        
        # 提取片段
        segments = []
        for seg in result.get("segments", []):
            segments.append(AudioSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"].strip(),
                confidence=seg.get("confidence", 1.0)
            ))
        
        return full_text, segments
    
    def get_duration(self, audio_path: str) -> float:
        """
        获取音频时长
        
        Args:
            audio_path: 音频文件路径
        
        Returns:
            时长（秒）
        """
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except ImportError:
            # 如果没有 pydub，使用 whisper 获取
            _, segments = self.transcribe(audio_path)
            if segments:
                return segments[-1].end
            return 0.0
    
    @staticmethod
    def is_audio_file(filepath: str) -> bool:
        """检查是否为音频文件"""
        audio_extensions = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac', '.wma'}
        return os.path.splitext(filepath)[1].lower() in audio_extensions


def format_timestamp(seconds: float) -> str:
    """
    将秒数格式化为时间戳字符串
    
    Args:
        seconds: 秒数
    
    Returns:
        格式化的时间戳 (HH:MM:SS.mmm)
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def parse_timestamp(timestamp: str) -> float:
    """
    将时间戳字符串解析为秒数
    
    Args:
        timestamp: 时间戳字符串 (HH:MM:SS.mmm 或 MM:SS.mmm)
    
    Returns:
        秒数
    """
    parts = timestamp.split(':')
    
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)
    else:
        return float(timestamp)

# ======================================================================# 模块: utils.helpers# ======================================================================
通用辅助函数
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, Optional


def ensure_dir(path: str) -> str:
    """
    确保目录存在，不存在则创建
    
    Args:
        path: 目录路径
    
    Returns:
        目录路径
    """
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def format_duration(seconds: float) -> str:
    """
    格式化时长为可读字符串
    
    Args:
        seconds: 秒数
    
    Returns:
        格式化的字符串 (如 "1:30:45" 或 "5:30")
    """
    if seconds < 0:
        return "0:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def get_timestamp(fmt: str = "%Y%m%d_%H%M%S") -> str:
    """
    获取当前时间戳字符串
    
    Args:
        fmt: 时间格式
    
    Returns:
        格式化的时间戳
    """
    return datetime.now().strftime(fmt)


def load_json(filepath: str) -> Optional[Dict[str, Any]]:
    """
    加载 JSON 文件
    
    Args:
        filepath: 文件路径
    
    Returns:
        解析后的字典或 None
    """
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_json(filepath: str, data: Dict[str, Any], indent: int = 2) -> bool:
    """
    保存数据到 JSON 文件
    
    Args:
        filepath: 文件路径
        data: 要保存的数据
        indent: 缩进空格数
    
    Returns:
        是否成功
    """
    try:
        ensure_dir(os.path.dirname(filepath))
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        return True
    except IOError:
        return False


def safe_filename(name: str, max_length: int = 255) -> str:
    """
    生成安全的文件名
    
    Args:
        name: 原始名称
        max_length: 最大长度
    
    Returns:
        安全的文件名
    """
    # 替换非法字符
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        name = name.replace(char, '_')
    
    # 移除首尾空格和点
    name = name.strip(' .')
    
    # 限制长度
    if len(name) > max_length:
        name = name[:max_length]
    
    # 如果为空，使用默认名称
    if not name:
        name = "untitled"
    
    return name


def get_file_size(filepath: str) -> int:
    """
    获取文件大小（字节）
    
    Args:
        filepath: 文件路径
    
    Returns:
        文件大小
    """
    if not os.path.exists(filepath):
        return 0
    return os.path.getsize(filepath)


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为可读字符串
    
    Args:
        size_bytes: 字节数
    
    Returns:
        格式化的字符串 (如 "1.5 MB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def chunk_list(lst: list, chunk_size: int):
    """
    将列表分割成指定大小的块
    
    Args:
        lst: 原始列表
        chunk_size: 每块大小
    
    Yields:
        列表块
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    将值限制在指定范围内
    
    Args:
        value: 原始值
        min_val: 最小值
        max_val: 最大值
    
    Returns:
        限制后的值
    """
    return max(min_val, min(max_val, value))

# ======================================================================# 模块: utils# ======================================================================
工具模块 - 通用工具函数
"""

from .text import clean_text, extract_keywords, extract_number
from .audio import AudioProcessor
from .helpers import ensure_dir, format_duration, get_timestamp

__all__ = [
    'clean_text',
    'extract_keywords',
    'extract_number',
    'AudioProcessor',
    'ensure_dir',
    'format_duration',
    'get_timestamp',
]

# ======================================================================# 模块: cache# ======================================================================
缓存模块 - 统一的缓存管理系统
"""

import os
import json
import time
import threading
import hashlib
from typing import Any, Optional, Dict
from datetime import datetime


class CacheManager:
    """缓存管理器 - 内存缓存 + 可选文件持久化"""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600, cache_dir: str = None):
        """
        初始化缓存管理器
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存生存时间（秒）
            cache_dir: 缓存文件目录（可选）
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._ttl = ttl
        self._cache_dir = cache_dir
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _generate_key(self, data: Any) -> str:
        """生成缓存键"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif not isinstance(data, bytes):
            data = str(data).encode('utf-8')
        return hashlib.md5(data).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值或 None
        """
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            entry = self._cache[key]
            
            # 检查是否过期
            if time.time() - entry['timestamp'] > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            
            self._hits += 1
            return entry['value']
    
    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 生存时间（可选，默认使用全局 TTL）
        """
        with self._lock:
            # 如果缓存已满，清理最旧的条目
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            
            self._cache[key] = {
                'value': value,
                'timestamp': time.time(),
                'ttl': ttl or self._ttl
            }
    
    def delete(self, key: str) -> bool:
        """删除缓存条目"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
    
    def _evict_oldest(self) -> None:
        """清理最旧的缓存条目"""
        if not self._cache:
            return
        
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k]['timestamp']
        )
        del self._cache[oldest_key]
    
    def cleanup_expired(self) -> int:
        """清理所有过期缓存，返回清理数量"""
        count = 0
        current_time = time.time()
        
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if current_time - v['timestamp'] > v['ttl']
            ]
            
            for key in expired_keys:
                del self._cache[key]
                count += 1
        
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0
        
        return {
            'size': len(self._cache),
            'max_size': self._max_size,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': f"{hit_rate:.2%}",
            'ttl': self._ttl
        }
    
    def save_to_file(self, filename: str = "cache.json") -> bool:
        """保存缓存到文件"""
        if not self._cache_dir:
            return False
        
        filepath = os.path.join(self._cache_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'cache': self._cache,
                    'timestamp': datetime.now().isoformat()
                }, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def load_from_file(self, filename: str = "cache.json") -> bool:
        """从文件加载缓存"""
        if not self._cache_dir:
            return False
        
        filepath = os.path.join(self._cache_dir, filename)
        
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 只加载未过期的条目
            current_time = time.time()
            for key, entry in data.get('cache', {}).items():
                if current_time - entry['timestamp'] <= entry['ttl']:
                    self._cache[key] = entry
            
            return True
        except Exception:
            return False


# 全局缓存实例
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


def cache_get(key: str) -> Optional[Any]:
    """快捷函数：获取缓存"""
    return get_cache_manager().get(key)


def cache_set(key: str, value: Any, ttl: int = None) -> None:
    """快捷函数：设置缓存"""
    get_cache_manager().set(key, value, ttl)


def cache_clear() -> None:
    """快捷函数：清空缓存"""
    get_cache_manager().clear()


def get_cache_stats() -> Dict[str, Any]:
    """快捷函数：获取缓存统计"""
    return get_cache_manager().get_stats()

# ======================================================================# 模块: prompts# ======================================================================
提示词模板模块 - 集中管理所有提示词模板
"""

from typing import Dict, Optional


class PromptTemplates:
    """高级提示词模板系统 - 释放大模型最大潜力"""
    
    # ==================== 提示词优化模板 ====================
    PROMPT_OPTIMIZATION = {
        "system": """你是世界级的AI图像生成提示词工程师，拥有深厚的艺术、摄影、电影和视觉设计背景。

【核心能力】
1. 语义理解：精准捕捉文本的深层含义、情感基调和视觉意象
2. 视觉转化：将抽象概念转化为具体的视觉元素和构图
3. 技术精通：掌握Stable Diffusion、Midjourney、DALL-E等平台的提示词语法
4. 艺术审美：具备专业级的美术、摄影和电影构图知识

【视觉联想引导 - 关键】
请从以下维度进行丰富的视觉联想：
1. 主体元素联想：
   - 识别文本中的核心主体（人物、物体、场景等）
   - 联想主体的细节特征（外观、材质、状态、动作等）
   - 考虑主体在画面中的位置和比例

2. 环境场景联想：
   - 为主体匹配合适的环境和背景
   - 联想环境的细节（建筑风格、天气、时间、地点等）
   - 考虑环境与主体的互动关系

3. 光线氛围联想：
   - 选择合适的光线类型（自然光、人造光、混合光）
   - 联想光线的方向、强度、色温
   - 考虑光影对比和阴影效果

4. 色彩色调联想：
   - 根据文本情感选择主色调（暖色调/冷色调/中性色调）
   - 联想辅助色和点缀色
   - 考虑色彩饱和度和对比度

5. 构图视角联想：
   - 选择合适的视角（平视/俯视/仰视/特写/全景）
   - 考虑构图法则（三分法则、对称构图、引导线等）
   - 决定画面的景别（近景/中景/远景）

6. 艺术风格联想：
   - 选择合适的艺术风格（写实/插画/油画/水彩/赛博朋克等）
   - 考虑画面的质感和纹理
   - 添加风格化的艺术元素

【优化原则】
- 准确性：严格忠于原文语义，不添加无关元素
- 丰富性：添加合理的细节使画面生动（光线、材质、氛围、色彩）
- 结构性：主体→环境→风格→技术参数的逻辑顺序
- 专业性：使用行业标准术语（如"bokeh"、"golden hour"、"rule of thirds"）
- 兼容性：确保提示词适用于所有主流AI绘图平台
- 联想性：从多个维度进行丰富的视觉联想，使画面生动具体

【输出要求】
- 只返回优化后的英文提示词
- 使用逗号分隔不同元素
- 长度控制在50-150词之间
- 包含质量增强词（masterpiece, best quality等）
- 体现丰富的视觉联想（主体、环境、光线、色彩、构图、风格）""",
        
        "user_template": """【原始描述】
{description}

【上下文信息】
- 场景类型: {scene_type}
- 情感基调: {mood}
- 视觉风格: {style}

请生成专业级AI绘图提示词："""
    }
    
    # ==================== 分镜分析模板 - SD提示词版本（英文）====================
    SHOT_ANALYSIS_SD = {
        "system": """你是资深影视导演和视觉叙事专家，擅长将文本转化为电影级分镜脚本。

【核心要求 - 必须遵守】
1. 【强制】每个分镜的"配音"字段必须使用原始转录文本，禁止做任何总结或概括！
2. 【强制】分镜数量必须充足，确保每个分镜时长在8-12秒之间，不宜过长
3. 整篇深度阅读：必须完整阅读并深入理解整段转录文本，把握核心主题思想
4. 主题提炼：准确提炼出文本的中心思想、情感基调和视觉主题
5. 统一基调：所有分镜的画面提示词必须围绕同一主题思想、定准同一基调
6. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
7. 综合表达：所有分镜画面综合起来必须突出表达那个核心主题思想

【关键：分镜数量由你根据语义完整性自主决定】
- 不要限制分镜数量，根据语义断句自由创建
- 每一句完整的话或语义连贯的多个句子应该作为一个分镜
- 分镜数量由大模型根据语义完整性自行判断
- 不要合并语义完整的句子！

【输出格式 - 必须严格遵守】
核心主题：[一句话概括文本的核心主题思想]
视觉基调：[整体视觉风格+统一色调+情感氛围]
主题元素：[贯穿全篇的视觉元素列表，用逗号分隔]

分镜脚本：
1. **配音**：[原始转录文本，不要总结或概括]
2. **画面提示词**：[英文关键词，用逗号分隔，权重使用(数字)格式]
3. **反向提示词**：[英文，避免的问题]""",

        "user_template": """【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

【转录文本】
{text}

【重要要求】
1. 请先完整阅读整篇文本，深入理解其核心主题思想
2. 根据语义合理拆分文本，每句完整的话或语义连贯的多个句子作为一个分镜
3. 分镜数量不限制，由你根据语义完整性自主判断
4. 所有分镜的画面提示词必须围绕同一主题、定准同一基调

请设计电影级分镜脚本，画面提示词必须使用英文："""
    }
    
    # 为了保持兼容性，保留旧的SHOT_ANALYSIS引用（默认使用SD版本)
    SHOT_ANALYSIS = SHOT_ANALYSIS_SD
    
    # ==================== 分镜分析模板 - 豆包提示词版本（中文）====================
    SHOT_ANALYSIS_DOUBAO = {
        "system": """你是资深影视导演和视觉叙事专家，擅长将文本转化为电影级分镜脚本。

【核心要求 - 必须遵守】
1. 【强制】每个分镜的"配音"字段必须使用原始转录文本，禁止做任何总结或概括！
2. 【强制】分镜数量必须充足，确保每个分镜时长在8-12秒之间，不宜过长
3. 整篇深度阅读：必须完整阅读并深入理解整段转录文本，把握核心主题思想

【输出格式 - 必须严格遵守】
核心主题：[一句话概括文本的核心主题思想]
视觉基调：[整体视觉风格+统一色调+情感氛围]
主题元素：[贯穿全篇的视觉元素列表，用逗号分隔]

分镜脚本：
1. **配音**：[原始转录文本，不要总结或概括]
2. **画面提示词**：[中文画面描述]
3. **反向提示词**：[中文，避免的问题]""",

        "user_template": """【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

【转录文本】
{text}

请设计电影级分镜脚本，画面提示词使用中文："""
    }
    
    # ==================== 主题提取模板 ====================
    THEME_EXTRACTION = {
        "system": """你是专业的视频内容分析专家。请从以下语音转录文本中提取关键词，用于后续分镜生成。

【重要】你必须直接返回关键词，不需要任何解释或描述。

请用以下严格格式输出（只输出这些内容，不要有任何其他文字）：
【核心主题】：关键词1, 关键词2, 关键词3（最多5个关键词，用逗号分隔）
【视觉基调】：关键词1, 关键词2（最多3个关键词）
【主题元素】：关键词1, 关键词2, 关键词3, 关键词4, 关键词5（最多5个关键词）""",
        
        "user_template": "语音转录文本：\n{text}"
    }
    
    # ==================== 语音新闻播报分镜分析模板 ====================
    VOICE_SHOT_ANALYSIS_SD = {
        "system": """你是专业的语音新闻播报视频分镜脚本专家。

【主题统一性要求 - 最重要】
1. 整篇深度阅读：必须完整阅读整段转录文本，深入理解文章的核心主题思想
2. 主题提炼：准确提炼出贯穿全文的中心思想、情感基调和视觉主题
3. 统一基调：所有分镜的画面提示词必须围绕同一主题思想、定准同一基调

【分镜脚本生成规则】
1. 每个语音片段必须对应一个独立的分镜
2. 绝对不要将多个句子合并成一个分镜
3. 分镜数量不限制，由大模型根据语义完整性自主判断

输出格式：
- 核心主题：[文章的核心主题思想]
- 视觉基调：[整体视觉风格+统一色调+情感氛围]
- 主题元素：[贯穿全篇的视觉元素列表]

分镜脚本：
  1. **配音**：[润色后的配音文本内容]
     **画面提示词**：[英文提示词]
     **负面提示词**：[英文负面提示词]""",

        "user_template": """【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

原始语音转录文本：
{text}

提示词类型：SD提示词（必须使用英文画面提示词）
风格预设：{style_preset}

请生成专业的分镜脚本。"""
    }
    
    # ==================== 风格描述模板 ====================
    STYLE_DESCRIPTION = {
        "system": """你是艺术史专家和视觉风格顾问，精通各种艺术流派和视觉风格。

【分析维度】
1. 历史渊源：风格的起源、发展和代表人物
2. 视觉特征：独特的色彩、线条、构图和技法
3. 情感表达：风格传达的情绪和氛围
4. 应用场景：适合表现的主题和内容
5. AI适配：转化为AI绘图提示词的最佳方式

【输出要求】
- 提供详细、专业的风格描述
- 包含具体的视觉元素关键词
- 说明色彩搭配建议
- 给出构图和技法提示""",
        
        "user_template": """请详细分析以下艺术风格，并提供专业的AI绘图描述：

风格名称：{style_name}"""
    }
    
    # ==================== 质量评估模板 ====================
    QUALITY_ASSESSMENT = {
        "system": """你是AI生成内容质量评估专家，擅长评估文本输出的质量和适用性。

【评估维度】
1. 语义准确性：是否准确反映原始意图
2. 完整性：是否包含所有必要元素
3. 专业性：术语使用是否准确专业
4. 创造性：是否有独特的创意和视角
5. 可用性：是否可以直接投入使用

【评分标准】
- 0.9-1.0：优秀，无需修改
- 0.8-0.9：良好，轻微优化
- 0.7-0.8：合格，需要改进
- 0.6-0.7：较差，建议重写
- <0.6：不合格，必须重新生成""",
        
        "user_template": """【原始输入】
{original_input}

【模型输出】
{model_output}

【预期用途】
{intended_use}

请评估输出质量："""
    }
    
    @classmethod
    def get_template(cls, template_type: str, **kwargs) -> Optional[Dict[str, str]]:
        """
        获取格式化的提示词模板
        
        Args:
            template_type: 模板类型名称
            **kwargs: 模板参数
        
        Returns:
            包含 system 和 user 键的字典，或 None
        """
        templates = {
            "prompt_optimization": cls.PROMPT_OPTIMIZATION,
            "shot_analysis": cls.SHOT_ANALYSIS,
            "shot_analysis_sd": cls.SHOT_ANALYSIS_SD,
            "shot_analysis_doubao": cls.SHOT_ANALYSIS_DOUBAO,
            "voice_shot_analysis_sd": cls.VOICE_SHOT_ANALYSIS_SD,
            "theme_extraction": cls.THEME_EXTRACTION,
            "style_description": cls.STYLE_DESCRIPTION,
            "quality_assessment": cls.QUALITY_ASSESSMENT,
        }
        
        if template_type not in templates:
            return None
        
        template = templates[template_type]
        
        return {
            "system": template["system"],
            "user": template["user_template"].format(**kwargs) if kwargs else template["user_template"]
        }
    
    @classmethod
    def list_templates(cls) -> list:
        """列出所有可用的模板类型"""
        return [
            "prompt_optimization",
            "shot_analysis",
            "shot_analysis_sd",
            "shot_analysis_doubao",
            "voice_shot_analysis_sd",
            "theme_extraction",
            "style_description",
            "quality_assessment",
        ]

# ======================================================================# 模块: task_queue# ======================================================================
任务队列模块 - 异步任务管理和调度
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, Future


class TaskStatus(Enum):
    """任务状态枚举"""
    QUEUED = "queued"      # 排队中
    RUNNING = "running"    # 执行中
    PAUSED = "paused"      # 已暂停
    COMPLETED = "completed" # 已完成
    FAILED = "failed"      # 失败
    CANCELLED = "cancelled" # 已取消


class TaskPriority(Enum):
    """任务优先级枚举"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """任务数据类"""
    id: str
    name: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.QUEUED
    result: Any = None
    error: Optional[str] = None
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    def __lt__(self, other):
        """比较运算符，用于优先级队列排序"""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at


class TaskQueue:
    """任务队列管理器"""
    
    def __init__(self, max_workers: int = 4):
        """
        初始化任务队列
        
        Args:
            max_workers: 最大工作线程数
        """
        self._queue: List[Task] = []
        self._tasks: Dict[str, Task] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._max_workers = max_workers
        self._lock = threading.RLock()
        self._running = False
        self._current_task: Optional[Task] = None
        self._pause_event = threading.Event()
        self._pause_event.set()  # 默认不暂停
        
        # 回调函数
        self._on_task_start: Optional[Callable] = None
        self._on_task_complete: Optional[Callable] = None
        self._on_task_error: Optional[Callable] = None
        self._on_progress: Optional[Callable] = None
    
    def start(self) -> None:
        """启动任务队列"""
        if self._running:
            return
        
        self._running = True
        self._executor = ThreadPoolExecutor(max_workers=self._max_workers)
    
    def shutdown(self, wait: bool = True) -> None:
        """关闭任务队列"""
        self._running = False
        
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None
    
    def add_task(
        self,
        task_id: str,
        task_name: str,
        func: Callable,
        args: tuple = None,
        kwargs: dict = None,
        priority: TaskPriority = TaskPriority.NORMAL
    ) -> str:
        """
        添加任务到队列
        
        Args:
            task_id: 任务唯一ID
            task_name: 任务名称
            func: 任务执行函数
            args: 位置参数
            kwargs: 关键字参数
            priority: 任务优先级
        
        Returns:
            任务ID
        """
        task = Task(
            id=task_id,
            name=task_name,
            func=func,
            args=args or (),
            kwargs=kwargs or {},
            priority=priority
        )
        
        with self._lock:
            self._tasks[task_id] = task
            self._queue.append(task)
            # 按优先级排序
            self._queue.sort()
        
        return task_id
    
    def get_next_task(self) -> Optional[Task]:
        """获取下一个待执行的任务"""
        with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.QUEUED:
                    return task
        return None
    
    def execute_next(self) -> Optional[Future]:
        """执行下一个任务"""
        if not self._running or not self._executor:
            return None
        
        task = self.get_next_task()
        if not task:
            return None
        
        def run_task():
            # 等待暂停解除
            self._pause_event.wait()
            
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            self._current_task = task
            
            if self._on_task_start:
                self._on_task_start(task)
            
            try:
                task.result = task.func(*task.args, **task.kwargs)
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                
                if self._on_task_complete:
                    self._on_task_complete(task)
                    
            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = time.time()
                
                if self._on_task_error:
                    self._on_task_error(task, e)
            
            finally:
                self._current_task = None
        
        return self._executor.submit(run_task)
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.status == TaskStatus.QUEUED:
                    task.status = TaskStatus.CANCELLED
                    self._queue.remove(task)
                    return True
        return False
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PAUSED
                    self._pause_event.clear()
                    return True
        return False
    
    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        with self._lock:
            if task_id in self._tasks:
                task = self._tasks[task_id]
                if task.status == TaskStatus.PAUSED:
                    task.status = TaskStatus.RUNNING
                    self._pause_event.set()
                    return True
        return False
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务信息"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self._tasks.values())
    
    def get_queue_length(self) -> int:
        """获取队列长度"""
        with self._lock:
            return len([t for t in self._queue if t.status == TaskStatus.QUEUED])
    
    def clear_completed(self) -> int:
        """清理已完成的任务"""
        count = 0
        with self._lock:
            completed_ids = [
                tid for tid, task in self._tasks.items()
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
            ]
            for tid in completed_ids:
                del self._tasks[tid]
                count += 1
        return count
    
    def set_callbacks(
        self,
        on_start: Callable = None,
        on_complete: Callable = None,
        on_error: Callable = None,
        on_progress: Callable = None
    ) -> None:
        """设置回调函数"""
        self._on_task_start = on_start
        self._on_task_complete = on_complete
        self._on_task_error = on_error
        self._on_progress = on_progress
    
    def get_status_text(self, status: TaskStatus) -> str:
        """获取状态的中文文本"""
        status_map = {
            TaskStatus.QUEUED: "排队中",
            TaskStatus.RUNNING: "执行中",
            TaskStatus.PAUSED: "已暂停",
            TaskStatus.COMPLETED: "已完成",
            TaskStatus.FAILED: "失败",
            TaskStatus.CANCELLED: "已取消"
        }
        return status_map.get(status, "未知")


# 全局任务队列实例
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """获取全局任务队列实例"""
    global _task_queue
    if _task_queue is None:
        _task_queue = TaskQueue()
    return _task_queue

# ======================================================================# 模块: llm.performance# ======================================================================
LLM 性能优化模块 - 大模型配置和性能优化
"""

import datetime
from typing import Dict, List, Any, Optional


class LLMConfig:
    """大模型高级配置类 - 释放模型最大潜力"""
    
    # 预设配置模式
    PRESETS = {
        "创意模式": {
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 100,
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.3,
            "presence_penalty": 0.3,
            "description": "高创造性，适合头脑风暴和创意生成"
        },
        "平衡模式": {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 80,
            "repeat_penalty": 1.15,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.2,
            "description": "平衡创造性和准确性"
        },
        "精确模式": {
            "temperature": 0.3,
            "top_p": 0.7,
            "top_k": 40,
            "repeat_penalty": 1.2,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.1,
            "description": "高准确性，适合分析和结构化任务"
        },
        "极速模式": {
            "temperature": 0.2,
            "top_p": 0.5,
            "top_k": 20,
            "repeat_penalty": 1.1,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
            "num_predict": 500,
            "description": "最快响应，适合简单任务"
        },
        "质量优先": {
            "temperature": 0.6,
            "top_p": 0.92,
            "top_k": 60,
            "repeat_penalty": 1.18,
            "frequency_penalty": 0.25,
            "presence_penalty": 0.25,
            "num_predict": 4000,
            "num_ctx": 8192,
            "description": "最高输出质量，适合复杂任务"
        }
    }
    
    def __init__(self, preset: str = "质量优先"):
        self.preset = preset
        self.config = self.PRESETS.get(preset, self.PRESETS["质量优先"]).copy()
        self.custom_params: Dict[str, Any] = {}
    
    def get_options(self, **overrides) -> Dict[str, Any]:
        """获取 Ollama 调用参数"""
        options = self.config.copy()
        options.update(self.custom_params)
        options.update(overrides)
        # 移除描述字段
        options.pop("description", None)
        return options
    
    def set_custom_param(self, key: str, value: Any) -> None:
        """设置自定义参数"""
        self.custom_params[key] = value
    
    def apply_preset(self, preset_name: str) -> bool:
        """应用预设配置"""
        if preset_name in self.PRESETS:
            self.preset = preset_name
            self.config = self.PRESETS[preset_name].copy()
            self.custom_params = {}
            return True
        return False
    
    @classmethod
    def get_preset_names(cls) -> List[str]:
        """获取所有预设名称"""
        return list(cls.PRESETS.keys())
    
    @classmethod
    def get_preset_description(cls, preset_name: str) -> str:
        """获取预设描述"""
        preset = cls.PRESETS.get(preset_name, {})
        return preset.get("description", "")


class LLMPerformanceOptimizer:
    """大模型性能优化器 - 自适应调整参数"""
    
    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []
        self.max_history = 10
        self.avg_response_time = 0.0
        self.success_rate = 1.0
    
    def record_call(self, duration: float, success: bool, token_count: int = 0) -> None:
        """记录调用性能"""
        self.call_history.append({
            "duration": duration,
            "success": success,
            "token_count": token_count,
            "timestamp": datetime.datetime.now()
        })
        
        # 保持历史记录在限制范围内
        if len(self.call_history) > self.max_history:
            self.call_history.pop(0)
        
        # 更新统计
        self._update_stats()
    
    def _update_stats(self) -> None:
        """更新性能统计"""
        if not self.call_history:
            return
        
        durations = [h["duration"] for h in self.call_history]
        self.avg_response_time = sum(durations) / len(durations)
        
        successes = sum(1 for h in self.call_history if h["success"])
        self.success_rate = successes / len(self.call_history)
    
    def get_optimal_config(self, task_complexity: str = "medium") -> LLMConfig:
        """根据历史性能获取最优配置"""
        base_config = LLMConfig("质量优先")
        
        # 根据成功率调整
        if self.success_rate < 0.7:
            # 成功率低，降低复杂度
            base_config.apply_preset("平衡模式")
            base_config.set_custom_param("num_predict", 1500)
        elif self.avg_response_time > 20:
            # 响应慢，使用极速模式
            base_config.apply_preset("极速模式")
        
        # 根据任务复杂度调整
        complexity_adjustments = {
            "low": {"temperature": 0.3, "num_predict": 500},
            "medium": {"temperature": 0.6, "num_predict": 2000},
            "high": {"temperature": 0.7, "num_predict": 4000, "num_ctx": 8192}
        }
        
        if task_complexity in complexity_adjustments:
            for key, value in complexity_adjustments[task_complexity].items():
                base_config.set_custom_param(key, value)
        
        return base_config
    
    def suggest_optimization(self) -> List[str]:
        """提供优化建议"""
        suggestions = []
        
        if self.avg_response_time > 15:
            suggestions.append(
                f"平均响应时间 {self.avg_response_time:.1f}s 较长，"
                f"建议使用极速模式或减少 num_predict"
            )
        
        if self.success_rate < 0.8:
            suggestions.append(
                f"成功率 {self.success_rate*100:.1f}% 较低，"
                f"建议检查模型状态或降低 temperature"
            )
        
        if not suggestions:
            suggestions.append(
                f"性能良好：平均响应 {self.avg_response_time:.1f}s，"
                f"成功率 {self.success_rate*100:.1f}%"
            )
        
        return suggestions
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        return {
            "avg_response_time": self.avg_response_time,
            "success_rate": self.success_rate,
            "total_calls": len(self.call_history),
            "recent_calls": self.call_history[-5:] if self.call_history else []
        }


# 全局优化器实例
llm_optimizer = LLMPerformanceOptimizer()

# ======================================================================# 模块: llm.ollama_client# ======================================================================
Ollama 客户端模块 - 统一的 Ollama 模型调用接口
"""

import threading
from typing import Optional, Tuple, Callable, List

# 全局锁，保护 Ollama API 调用
ollama_lock = threading.Lock()

# 模块级别的 requests 引用
_requests = None


def _get_requests():
    """延迟导入 requests"""
    global _requests
    if _requests is None:
        import requests
        _requests = requests
    return _requests


class OllamaClient:
    """Ollama 客户端类"""
    
    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_TIMEOUT = 120
    
    def __init__(self, host: str = None, timeout: int = None):
        self.host = host or self.DEFAULT_HOST
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self._requests = _get_requests()
    
    def list_models(self) -> List[str]:
        """获取可用模型列表"""
        try:
            response = self._requests.get(
                f"{self.host}/api/tags",
                timeout=5
            )
            if response.status_code == 200:
                models_info = response.json()
                available_models = []
                if "models" in models_info:
                    for m in models_info["models"]:
                        model_name = m.get("name", m.get("model", ""))
                        if model_name:
                            available_models.append(model_name)
                return available_models
        except Exception:
            pass
        return []
    
    def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        options: dict = None,
        log_callback: Callable = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        调用单个模型进行对话
        
        Args:
            model: 模型名称
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            options: 模型参数
            log_callback: 日志回调函数
        
        Returns:
            (结果文本, 模型名称) 或 (None, None)
        """
        default_options = {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 512,
            "num_ctx": 4096
        }
        if options:
            default_options.update(options)
        
        try:
            response = self._requests.post(
                f"{self.host}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "options": default_options
                },
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                if log_callback:
                    log_callback(f"⚠️ 模型 {model} HTTP错误: {response.status_code}")
                return None, None
            
            result_data = response.json()
            result = result_data.get("message", {}).get("content", "").strip()
            
            if not result:
                if log_callback:
                    log_callback(f"⚠️ 模型 {model} 返回空结果")
                return None, None
            
            return result, model
            
        except Exception as e:
            if log_callback:
                log_callback(f"⚠️ 模型 {model} 调用失败: {str(e)[:50]}")
            return None, None


def call_ollama_model(
    model_list: List[str],
    system_prompt: str,
    user_prompt: str,
    log_callback: Callable = None,
    num_predict: int = 512,
    num_ctx: int = 4096,
    host: str = None,
    timeout: int = 120
) -> Tuple[Optional[str], Optional[str]]:
    """
    统一的 Ollama 模型调用函数 - 自动尝试多个模型，直到成功
    
    使用 HTTP API 直接调用，避免 ollama 库版本兼容性问题
    
    Args:
        model_list: 要尝试的模型列表（按优先级排序）
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        log_callback: 日志回调函数
        num_predict: 生成的最大 token 数
        num_ctx: 上下文窗口大小
        host: Ollama 服务地址
        timeout: 请求超时时间
    
    Returns:
        (结果文本, 使用的模型名称) 或 (None, None)
    """
    requests = _get_requests()
    
    if requests is None:
        if log_callback:
            log_callback("⚠️ requests 库未安装")
        return None, None
    
    client = OllamaClient(host, timeout)
    
    # 获取可用模型列表
    available_models = client.list_models()
    
    if not available_models:
        if log_callback:
            log_callback("⚠️ 无法获取 Ollama 模型列表，请确保 Ollama 服务正在运行")
        return None, None
    
    # 过滤出实际可用的模型
    candidate_models = [m for m in model_list if m in available_models]
    
    if not candidate_models:
        if log_callback:
            log_callback(f"⚠️ 模型列表 {model_list} 中没有可用的模型")
            log_callback(f"   可用模型: {available_models}")
        return None, None
    
    # 依次尝试每个模型
    for model in candidate_models:
        if log_callback:
            log_callback(f"   尝试模型: {model}")
        
        result, used_model = client.chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            options={
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": num_predict,
                "num_ctx": num_ctx
            },
            log_callback=log_callback
        )
        
        if result:
            if log_callback:
                log_callback(f"   ✅ 使用模型: {used_model}")
            return result, used_model
    
    if log_callback:
        log_callback("❌ 所有模型调用失败")
    return None, None

# ======================================================================# 模块: llm.model_fusion# ======================================================================
多模型融合模块 - 整合多个模型的优势
"""

import threading
from typing import Dict, List, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from .ollama_client import OllamaClient


class MultiModelFusion:
    """多模型融合系统 - 整合多个模型的优势"""
    
    def __init__(self, host: str = None):
        self.client = OllamaClient(host)
        self.available_models: List[str] = []
        self.model_weights: Dict[str, float] = {}
        self.fusion_strategy = "weighted_vote"  # weighted_vote, cascade, ensemble
        self._lock = threading.Lock()
    
    def discover_models(self, log_callback: Callable = None) -> List[str]:
        """发现可用的 Ollama 模型"""
        self.available_models = self.client.list_models()
        
        if not self.available_models:
            if log_callback:
                log_callback("⚠️ 未发现可用的 Ollama 模型")
            return []
        
        # 计算每个模型的权重
        for model in self.available_models:
            self.model_weights[model] = self._calculate_model_weight(model)
        
        if log_callback:
            log_callback(f"✅ 发现 {len(self.available_models)} 个可用模型")
        
        return self.available_models
    
    def _calculate_model_weight(self, model_name: str) -> float:
        """计算模型权重（基于模型名称启发式判断）"""
        weight = 1.0
        
        # 根据模型大小/类型调整权重
        model_lower = model_name.lower()
        
        # 大模型优先
        if any(x in model_lower for x in ['70b', '72b', '8x7b', 'mixtral']):
            weight = 1.5
        elif any(x in model_lower for x in ['34b', '35b', '40b']):
            weight = 1.3
        elif any(x in model_lower for x in ['13b', '14b', '20b']):
            weight = 1.2
        elif any(x in model_lower for x in ['7b', '8b', '9b']):
            weight = 1.0
        elif any(x in model_lower for x in ['3b', '4b', '5b']):
            weight = 0.8
        elif any(x in model_lower for x in ['1b', '2b', 'tiny', 'mini']):
            weight = 0.5
        
        # 特定模型加成
        if 'llama3' in model_lower or 'qwen2' in model_lower:
            weight *= 1.1
        elif 'gemma' in model_lower or 'mistral' in model_lower:
            weight *= 1.05
        
        return weight
    
    def call_single_model(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        options: dict = None,
        log_callback: Callable = None
    ) -> Optional[str]:
        """调用单个模型"""
        result, _ = self.client.chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            options=options,
            log_callback=log_callback
        )
        return result
    
    def parallel_generate(
        self,
        models: List[str],
        system_prompt: str,
        user_prompt: str,
        options: dict = None,
        max_workers: int = 3,
        log_callback: Callable = None
    ) -> Dict[str, str]:
        """并行调用多个模型"""
        results = {}
        
        def call_model(model: str) -> tuple:
            result = self.call_single_model(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                options=options,
                log_callback=log_callback
            )
            return model, result
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(call_model, m): m for m in models}
            
            for future in as_completed(futures):
                try:
                    model, result = future.result()
                    if result:
                        results[model] = result
                except Exception as e:
                    if log_callback:
                        log_callback(f"⚠️ 模型调用异常: {e}")
        
        return results
    
    def fuse_results(
        self,
        results: Dict[str, str],
        strategy: str = None
    ) -> str:
        """
        融合多个模型的结果
        
        Args:
            results: {模型名: 结果} 字典
            strategy: 融合策略 (weighted_vote, cascade, ensemble)
        
        Returns:
            融合后的结果
        """
        if not results:
            return ""
        
        if len(results) == 1:
            return list(results.values())[0]
        
        strategy = strategy or self.fusion_strategy
        
        if strategy == "weighted_vote":
            # 加权投票：选择权重最高的模型结果
            best_model = max(
                results.keys(),
                key=lambda m: self.model_weights.get(m, 1.0)
            )
            return results[best_model]
        
        elif strategy == "cascade":
            # 级联：返回第一个非空结果
            for model in sorted(results.keys(), key=lambda m: -self.model_weights.get(m, 1.0)):
                if results[model]:
                    return results[model]
        
        elif strategy == "ensemble":
            # 集成：简单拼接（可根据需要改进）
            combined = []
            for model, result in sorted(results.items(), key=lambda x: -self.model_weights.get(x[0], 1.0)):
                if result:
                    combined.append(f"[{model}] {result}")
            return "\n\n".join(combined)
        
        # 默认返回第一个结果
        return list(results.values())[0]
    
    def get_fusion_report(self, results: Dict[str, str]) -> Dict[str, Any]:
        """生成融合报告"""
        report = {
            "total_models": len(self.available_models),
            "used_models": list(results.keys()),
            "model_weights": {
                m: self.model_weights.get(m, 1.0) 
                for m in results.keys()
            },
            "result_lengths": {
                m: len(r) for m, r in results.items()
            }
        }
        
        # 找出最佳模型
        if results:
            best_model = max(
                results.keys(),
                key=lambda m: self.model_weights.get(m, 1.0)
            )
            report["best_model"] = best_model
            report["best_weight"] = self.model_weights.get(best_model, 1.0)
        
        return report
    
    def get_top_models(self, n: int = 3) -> List[str]:
        """获取权重最高的 N 个模型"""
        sorted_models = sorted(
            self.available_models,
            key=lambda m: -self.model_weights.get(m, 1.0)
        )
        return sorted_models[:n]

# ======================================================================# 模块: llm# ======================================================================
LLM 模块 - 大模型相关功能
"""

from .ollama_client import call_ollama_model, OllamaClient
from .performance import LLMPerformanceOptimizer, LLMConfig, llm_optimizer
from .model_fusion import MultiModelFusion

__all__ = [
    'call_ollama_model',
    'OllamaClient',
    'LLMPerformanceOptimizer',
    'LLMConfig',
    'llm_optimizer',
    'MultiModelFusion',
]

# ======================================================================# 模块: generators.shot_creator# ======================================================================
分镜创建模块 - 分镜脚本生成和管理
"""

import json
import re
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict


@dataclass
class Shot:
    """分镜数据类"""
    id: int
    start: float              # 开始时间（秒）
    end: float                # 结束时间（秒）
    duration: float           # 时长（秒）
    description: str          # 描述/配音文本
    prompt_en: str            # 英文提示词
    negative_prompt: str = "" # 负向提示词
    image_file: str = ""      # 图片文件名
    content_type: str = "general"  # 内容类型
    semantic_weight: float = 0.7   # 语义权重
    prompt_quality: float = 0.5    # 提示词质量评分
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Shot':
        """从字典创建"""
        return cls(**data)


class ShotCreator:
    """分镜创建器"""
    
    # 默认负向提示词
    DEFAULT_NEGATIVE_PROMPT = (
        "worst quality, low quality, cartoon, anime, painting, illustration, "
        "ugly, deformed, blurry, disfigured, bad anatomy, extra limbs, mutated hands"
    )
    
    def __init__(
        self,
        min_shot_duration: float = 4.0,
        max_shot_duration: float = 15.0
    ):
        """
        初始化分镜创建器
        
        Args:
            min_shot_duration: 最小分镜时长
            max_shot_duration: 最大分镜时长
        """
        self.min_shot_duration = min_shot_duration
        self.max_shot_duration = max_shot_duration
        self.shots: List[Shot] = []
    
    def create_shot(
        self,
        id: int,
        start: float,
        end: float,
        description: str,
        prompt_en: str,
        negative_prompt: str = None,
        **kwargs
    ) -> Shot:
        """
        创建单个分镜
        
        Args:
            id: 分镜ID
            start: 开始时间
            end: 结束时间
            description: 描述
            prompt_en: 英文提示词
            negative_prompt: 负向提示词
            **kwargs: 其他参数
        
        Returns:
            Shot 对象
        """
        shot = Shot(
            id=id,
            start=start,
            end=end,
            duration=end - start,
            description=description,
            prompt_en=prompt_en,
            negative_prompt=negative_prompt or self.DEFAULT_NEGATIVE_PROMPT,
            **kwargs
        )
        return shot
    
    def add_shot(self, shot: Shot) -> None:
        """添加分镜"""
        self.shots.append(shot)
    
    def clear_shots(self) -> None:
        """清空分镜"""
        self.shots = []
    
    def get_total_duration(self) -> float:
        """获取总时长"""
        if not self.shots:
            return 0.0
        return self.shots[-1].end
    
    def adjust_durations(self, target_duration: float = None) -> None:
        """
        调整分镜时长
        
        Args:
            target_duration: 目标总时长（可选）
        """
        if not self.shots:
            return
        
        # 计算当前总时长
        current_duration = self.get_total_duration()
        
        if target_duration and current_duration > 0:
            # 按比例调整
            scale = target_duration / current_duration
            
            for shot in self.shots:
                shot.start *= scale
                shot.end *= scale
                shot.duration = shot.end - shot.start
    
    def validate(self) -> List[str]:
        """
        验证分镜数据
        
        Returns:
            错误信息列表
        """
        errors = []
        
        for i, shot in enumerate(self.shots):
            # 检查时长
            if shot.duration < self.min_shot_duration:
                errors.append(
                    f"分镜 {i+1}: 时长 {shot.duration:.1f}s 小于最小值 {self.min_shot_duration}s"
                )
            
            # 检查时间连续性
            if i > 0 and shot.start != self.shots[i-1].end:
                errors.append(
                    f"分镜 {i+1}: 时间不连续，上一分镜结束于 {self.shots[i-1].end:.2f}s"
                )
            
            # 检查提示词
            if not shot.prompt_en.strip():
                errors.append(f"分镜 {i+1}: 提示词为空")
        
        return errors
    
    def to_json(self, filepath: str) -> bool:
        """
        保存到 JSON 文件
        
        Args:
            filepath: 文件路径
        
        Returns:
            是否成功
        """
        try:
            data = [shot.to_dict() for shot in self.shots]
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def from_json(self, filepath: str) -> bool:
        """
        从 JSON 文件加载
        
        Args:
            filepath: 文件路径
        
        Returns:
            是否成功
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.shots = [Shot.from_dict(item) for item in data]
            return True
        except Exception:
            return False
    
    def parse_llm_output(self, output: str, audio_duration: float = None) -> int:
        """
        解析大模型输出的分镜脚本
        
        Args:
            output: 大模型输出的文本
            audio_duration: 音频时长（可选）
        
        Returns:
            解析的分镜数量
        """
        self.clear_shots()
        
        # 提取核心主题、视觉基调等元信息
        # ...（具体解析逻辑可根据输出格式实现）
        
        # 提取分镜脚本部分
        # 这里提供基本的解析框架，实际需要根据具体输出格式调整
        
        lines = output.split('\n')
        current_shot = None
        shot_id = 0
        
        for line in lines:
            line = line.strip()
            
            # 检测分镜开始
            if re.match(r'^\d+\.', line) or '**配音**' in line:
                if current_shot:
                    self.shots.append(current_shot)
                
                shot_id += 1
                current_shot = Shot(
                    id=shot_id - 1,
                    start=0,
                    end=0,
                    duration=0,
                    description="",
                    prompt_en="",
                    negative_prompt=self.DEFAULT_NEGATIVE_PROMPT
                )
            
            # 提取配音
            if current_shot and '**配音**' in line:
                match = re.search(r'\*\*配音\*\*[：:]\s*(.+)', line)
                if match:
                    current_shot.description = match.group(1).strip()
            
            # 提取画面提示词
            if current_shot and '**画面提示词**' in line:
                match = re.search(r'\*\*画面提示词\*\*[：:]\s*(.+)', line)
                if match:
                    current_shot.prompt_en = match.group(1).strip()
        
        # 添加最后一个分镜
        if current_shot:
            self.shots.append(current_shot)
        
        # 根据音频时长调整时间
        if audio_duration and self.shots:
            self._distribute_time(audio_duration)
        
        return len(self.shots)
    
    def _distribute_time(self, total_duration: float) -> None:
        """根据总时长分配各分镜时间"""
        if not self.shots:
            return
        
        # 平均分配时间
        avg_duration = total_duration / len(self.shots)
        
        current_time = 0
        for shot in self.shots:
            shot.start = current_time
            shot.end = current_time + avg_duration
            shot.duration = avg_duration
            current_time = shot.end

# ======================================================================# 模块: generators.image_generator# ======================================================================
图片生成模块 - Stable Diffusion API 客户端
"""

import os
import time
import base64
import threading
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

# 延迟导入
_requests = None


def _get_requests():
    """延迟导入 requests"""
    global _requests
    if _requests is None:
        import requests
        _requests = requests
    return _requests


@dataclass
class GenerationResult:
    """生成结果数据类"""
    success: bool
    image_path: Optional[str] = None
    image_data: Optional[bytes] = None
    seed: Optional[int] = None
    error: Optional[str] = None
    generation_time: float = 0.0


class SDAPIClient:
    """Stable Diffusion API 客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:7860", timeout: int = 120):
        """
        初始化 SD API 客户端
        
        Args:
            base_url: SD WebUI API 地址
            timeout: 请求超时时间
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._requests = _get_requests()
        self._connected = False
    
    def check_connection(self) -> bool:
        """检查与 SD API 的连接"""
        try:
            response = self._requests.get(
                f"{self.base_url}/sdapi/v1/sd-models",
                timeout=5
            )
            self._connected = response.status_code == 200
            return self._connected
        except Exception:
            self._connected = False
            return False
    
    def get_models(self) -> List[Dict[str, Any]]:
        """获取可用模型列表"""
        try:
            response = self._requests.get(
                f"{self.base_url}/sdapi/v1/sd-models",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []
    
    def get_samplers(self) -> List[Dict[str, Any]]:
        """获取可用采样器列表"""
        try:
            response = self._requests.get(
                f"{self.base_url}/sdapi/v1/samplers",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return []
    
    def txt2img(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1920,
        height: int = 1080,
        steps: int = 20,
        cfg_scale: float = 7.0,
        sampler_name: str = "DPM++ 2M Karras",
        seed: int = -1,
        model: str = None,
        **kwargs
    ) -> GenerationResult:
        """
        文生图
        
        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            width: 图片宽度
            height: 图片高度
            steps: 采样步数
            cfg_scale: CFG 缩放
            sampler_name: 采样器名称
            seed: 随机种子
            model: 模型名称
            **kwargs: 其他参数
        
        Returns:
            GenerationResult
        """
        start_time = time.time()
        
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "sampler_name": sampler_name,
            "seed": seed,
            **kwargs
        }
        
        # 如果指定了模型，尝试切换
        if model:
            self._switch_model(model)
        
        try:
            response = self._requests.post(
                f"{self.base_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                return GenerationResult(
                    success=False,
                    error=f"API 返回错误: {response.status_code}"
                )
            
            data = response.json()
            
            if not data.get("images"):
                return GenerationResult(
                    success=False,
                    error="未返回图片数据"
                )
            
            # 解码图片
            image_data = base64.b64decode(data["images"][0])
            
            # 获取种子
            info = data.get("info", {})
            if isinstance(info, str):
                import json
                try:
                    info = json.loads(info)
                except:
                    info = {}
            
            return GenerationResult(
                success=True,
                image_data=image_data,
                seed=info.get("seed"),
                generation_time=time.time() - start_time
            )
            
        except Exception as e:
            return GenerationResult(
                success=False,
                error=str(e),
                generation_time=time.time() - start_time
            )
    
    def _switch_model(self, model_name: str) -> bool:
        """切换模型"""
        try:
            response = self._requests.post(
                f"{self.base_url}/sdapi/v1/options",
                json={"sd_model_checkpoint": model_name},
                timeout=30
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def save_image(
        self,
        result: GenerationResult,
        output_path: str
    ) -> bool:
        """
        保存生成结果到文件
        
        Args:
            result: 生成结果
            output_path: 输出路径
        
        Returns:
            是否成功
        """
        if not result.success or not result.image_data:
            return False
        
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(result.image_data)
            result.image_path = output_path
            return True
        except Exception:
            return False


class ImageGenerator:
    """图片生成器 - 批量生成管理"""
    
    def __init__(
        self,
        api_client: SDAPIClient = None,
        output_dir: str = "output/images",
        max_workers: int = 2
    ):
        """
        初始化图片生成器
        
        Args:
            api_client: SD API 客户端
            output_dir: 输出目录
            max_workers: 最大并发数
        """
        self.api_client = api_client or SDAPIClient()
        self.output_dir = output_dir
        self.max_workers = max_workers
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 回调函数
        self._on_progress: Optional[Callable] = None
        self._on_complete: Optional[Callable] = None
    
    def generate_single(
        self,
        prompt: str,
        negative_prompt: str = "",
        filename: str = None,
        **kwargs
    ) -> GenerationResult:
        """
        生成单张图片
        
        Args:
            prompt: 提示词
            negative_prompt: 负向提示词
            filename: 文件名
            **kwargs: 其他参数
        
        Returns:
            GenerationResult
        """
        result = self.api_client.txt2img(
            prompt=prompt,
            negative_prompt=negative_prompt,
            **kwargs
        )
        
        if result.success and filename:
            output_path = os.path.join(self.output_dir, filename)
            self.api_client.save_image(result, output_path)
        
        return result
    
    def generate_batch(
        self,
        prompts: List[Dict[str, Any]],
        log_callback: Callable = None
    ) -> List[GenerationResult]:
        """
        批量生成图片
        
        Args:
            prompts: 提示词列表，每个元素包含 prompt, negative_prompt, filename 等
            log_callback: 日志回调
        
        Returns:
            结果列表
        """
        results = []
        total = len(prompts)
        
        for i, p in enumerate(prompts):
            if log_callback:
                log_callback(f"正在生成第 {i+1}/{total} 张图片...")
            
            result = self.generate_single(
                prompt=p.get("prompt", ""),
                negative_prompt=p.get("negative_prompt", ""),
                filename=p.get("filename"),
                **{k: v for k, v in p.items() if k not in ["prompt", "negative_prompt", "filename"]}
            )
            
            results.append(result)
            
            if self._on_progress:
                self._on_progress(i + 1, total, result)
        
        if self._on_complete:
            self._on_complete(results)
        
        return results
    
    def generate_parallel(
        self,
        prompts: List[Dict[str, Any]],
        log_callback: Callable = None
    ) -> List[GenerationResult]:
        """
        并行批量生成图片
        
        Args:
            prompts: 提示词列表
            log_callback: 日志回调
        
        Returns:
            结果列表
        """
        results = [None] * len(prompts)
        total = len(prompts)
        completed = 0
        lock = threading.Lock()
        
        def generate_one(index: int, p: Dict[str, Any]) -> tuple:
            nonlocal completed
            result = self.generate_single(
                prompt=p.get("prompt", ""),
                negative_prompt=p.get("negative_prompt", ""),
                filename=p.get("filename"),
                **{k: v for k, v in p.items() if k not in ["prompt", "negative_prompt", "filename"]}
            )
            
            with lock:
                completed += 1
                if log_callback:
                    log_callback(f"已完成 {completed}/{total} 张图片")
            
            return index, result
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(generate_one, i, p)
                for i, p in enumerate(prompts)
            ]
            
            for future in as_completed(futures):
                try:
                    idx, result = future.result()
                    results[idx] = result
                except Exception as e:
                    if log_callback:
                        log_callback(f"生成失败: {e}")
        
        return results
    
    def set_callbacks(
        self,
        on_progress: Callable = None,
        on_complete: Callable = None
    ) -> None:
        """设置回调函数"""
        self._on_progress = on_progress
        self._on_complete = on_complete

# ======================================================================# 模块: generators# ======================================================================
生成器模块 - 图片和视频生成
"""

from .image_generator import ImageGenerator, SDAPIClient
from .shot_creator import ShotCreator

__all__ = [
    'ImageGenerator',
    'SDAPIClient',
    'ShotCreator',
]

# ======================================================================# 模块: ui.styles# ======================================================================
样式管理模块 - UI 样式配置
"""

from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class ColorScheme:
    """配色方案"""
    bg_color: str = "#1e1e1e"
    panel_bg: str = "#252526"
    text_fg: str = "#d4d4d4"
    accent_blue: str = "#2196f3"
    accent_red: str = "#f44336"
    btn_mid_bg: str = "#3c3f41"
    progress_bar: str = "#00FF00"
    progress_trough: str = "#1a1a1a"
    highlight: str = "#00bcd4"
    warning: str = "#ff9800"
    error: str = "#f44336"
    success: str = "#4caf50"


@dataclass
class FontConfig:
    """字体配置"""
    family: str = "Microsoft YaHei"
    base_size: int = 12
    header_size: int = 16
    title_size: int = 20
    small_size: int = 10


# 默认配色和字体
COLORS = ColorScheme()
FONTS = FontConfig()


class StyleManager:
    """样式管理器"""
    
    def __init__(self, style=None, colors: ColorScheme = None, fonts: FontConfig = None):
        """
        初始化样式管理器
        
        Args:
            style: ttk.Style 对象
            colors: 配色方案
            fonts: 字体配置
        """
        self.style = style
        self.colors = colors or COLORS
        self.fonts = fonts or FONTS
        self._base_font_size = self.fonts.base_size
        self._current_font_size = self._base_font_size
    
    def setup(self, style) -> None:
        """
        设置 ttk 样式
        
        Args:
            style: ttk.Style 对象
        """
        self.style = style
        
        # 尝试使用 clam 主题
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')
        
        self._configure_styles()
    
    def _configure_styles(self) -> None:
        """配置所有样式"""
        if not self.style:
            return
        
        fs = self._current_font_size
        
        # 基础样式
        self.style.configure("TFrame", background=self.colors.bg_color)
        self.style.configure(
            "TLabel",
            background=self.colors.bg_color,
            foreground=self.colors.text_fg,
            font=(self.fonts.family, fs + 2)
        )
        self.style.configure(
            "Header.TLabel",
            background=self.colors.bg_color,
            foreground=self.colors.highlight,
            font=(self.fonts.family, fs + 4, "bold")
        )
        
        # 按钮样式
        self.style.configure(
            "LargeBlue.TButton",
            background=self.colors.accent_blue,
            foreground="#ffffff",
            font=(self.fonts.family, fs + 6, "bold"),
            padding=(15, 15)
        )
        self.style.map(
            "LargeBlue.TButton",
            background=[('active', '#1976d2')]
        )
        
        self.style.configure(
            "LargeRed.TButton",
            background=self.colors.accent_red,
            foreground="#ffffff",
            font=(self.fonts.family, fs + 6, "bold"),
            padding=(15, 15)
        )
        self.style.map(
            "LargeRed.TButton",
            background=[('active', '#d32f2f')]
        )
        
        self.style.configure(
            "Medium.TButton",
            background=self.colors.btn_mid_bg,
            foreground="#ffffff",
            font=(self.fonts.family, fs + 4),
            padding=(10, 12)
        )
        self.style.map(
            "Medium.TButton",
            background=[('active', '#505050')]
        )
        
        self.style.configure(
            "Small.TButton",
            background=self.colors.btn_mid_bg,
            foreground="#ffffff",
            font=(self.fonts.family, fs + 2),
            padding=(5, 5)
        )
        self.style.map(
            "Small.TButton",
            background=[('active', '#505050')]
        )
        
        # 复选框样式
        self.style.configure(
            "TCheckbutton",
            background=self.colors.bg_color,
            foreground=self.colors.text_fg,
            font=(self.fonts.family, fs)
        )
        
        # 进度条样式
        self.style.configure(
            "TProgressbar",
            thickness=20,
            background=self.colors.progress_bar,
            troughcolor=self.colors.progress_trough,
            borderwidth=0
        )
        
        # 下拉框样式
        self.style.configure(
            "Config.TCombobox",
            font=(self.fonts.family, fs + 4),
            padding=(10, 8)
        )
        self.style.map(
            "Config.TCombobox",
            selectbackground=[('readonly', self.colors.bg_color)],
            selectforeground=[('readonly', '#ffffff')],
            fieldbackground=[('readonly', self.colors.panel_bg)],
            foreground=[('readonly', '#ffffff')]
        )
    
    def update_font_size(self, scale_factor: float) -> None:
        """
        更新字体大小
        
        Args:
            scale_factor: 缩放因子
        """
        new_size = max(8, int(self._base_font_size * scale_factor))
        
        if new_size != self._current_font_size:
            self._current_font_size = new_size
            self._configure_styles()
    
    def get_font(self, size_offset: int = 0, bold: bool = False) -> tuple:
        """
        获取字体配置
        
        Args:
            size_offset: 大小偏移
            bold: 是否加粗
        
        Returns:
            字体元组
        """
        weight = "bold" if bold else "normal"
        return (self.fonts.family, self._current_font_size + size_offset, weight)
    
    def get_button_style(self, size: str = "medium", color: str = "blue") -> str:
        """
        获取按钮样式名称
        
        Args:
            size: 尺寸 (small, medium, large)
            color: 颜色 (blue, red)
        
        Returns:
            样式名称
        """
        size_map = {
            "small": "Small",
            "medium": "Medium",
            "large": "Large"
        }
        
        color_map = {
            "blue": "Blue",
            "red": "Red"
        }
        
        size_prefix = size_map.get(size, "Medium")
        color_suffix = color_map.get(color, "Blue")
        
        return f"{size_prefix}{color_suffix}.TButton"

# ======================================================================# 模块: ui.main_window# ======================================================================
主窗口模块 - GUI 主窗口类
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional

from .styles import StyleManager, COLORS, FONTS


class MainWindow:
    """主窗口类"""
    
    def __init__(self, root: tk.Tk = None):
        """
        初始化主窗口
        
        Args:
            root: Tkinter 根窗口（可选）
        """
        # 创建或使用现有根窗口
        self.root = root or tk.Tk()
        
        # 初始化样式管理器
        self.style_manager = StyleManager()
        
        # 窗口配置
        self._setup_window()
        
        # 初始化 UI
        self._setup_ui()
        
        # 确保必要的目录存在
        self.output_dir, self.images_dir = ensure_directories()
        
        # 变量
        self._init_variables()
        
        # 绑定事件
        self._bind_events()
    
    def _setup_window(self) -> None:
        """设置窗口基本属性"""
        self.root.title(UI_CONFIG["window_title"])
        self.root.geometry(f"{UI_CONFIG['default_width']}x{UI_CONFIG['default_height']}")
        self.root.minsize(UI_CONFIG["min_width"], UI_CONFIG["min_height"])
        
        # 启用高 DPI 支持
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        
        # 设置背景色
        self.root.configure(bg=COLORS.bg_color)
    
    def _setup_ui(self) -> None:
        """设置 UI 组件"""
        # 设置 ttk 样式
        self.style = ttk.Style()
        self.style_manager.setup(self.style)
        
        # 创建主布局
        self._create_layout()
        
        # 创建左侧面板
        self._create_left_panel()
        
        # 创建右侧面板
        self._create_right_panel()
    
    def _create_layout(self) -> None:
        """创建主布局"""
        # 主分割窗口
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        
        # 左侧面板
        self.left_frame = ttk.Frame(self.main_paned, width=280)
        self.main_paned.add(self.left_frame, weight=0)
        
        # 右侧分割窗口
        self.right_paned = ttk.PanedWindow(self.main_paned, orient=tk.VERTICAL)
        self.main_paned.add(self.right_paned, weight=1)
        
        # 上部面板（脚本区域）
        self.top_frame = ttk.Frame(self.right_paned)
        self.right_paned.add(self.top_frame, weight=2)
        
        # 下部面板（日志区域）
        self.bottom_frame = ttk.Frame(self.right_paned)
        self.right_paned.add(self.bottom_frame, weight=1)
    
    def _create_left_panel(self) -> None:
        """创建左侧控制面板"""
        # 标题
        title_label = ttk.Label(
            self.left_frame,
            text="控制面板",
            style="Header.TLabel"
        )
        title_label.pack(pady=10)
        
        # 这里可以添加更多控制组件
        # 实际应用中根据需要添加按钮、下拉框等
    
    def _create_right_panel(self) -> None:
        """创建右侧内容区域"""
        # 脚本显示区
        script_label = ttk.Label(
            self.top_frame,
            text="分镜脚本",
            style="Header.TLabel"
        )
        script_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # 脚本文本框
        self.txt_script = tk.Text(
            self.top_frame,
            wrap=tk.WORD,
            font=(FONTS.family, FONTS.base_size + 4),
            bg=COLORS.panel_bg,
            fg=COLORS.text_fg
        )
        self.txt_script.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 日志区
        log_label = ttk.Label(
            self.bottom_frame,
            text="运行日志",
            style="Header.TLabel"
        )
        log_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # 日志文本框
        self.txt_log = tk.Text(
            self.bottom_frame,
            wrap=tk.WORD,
            font=(FONTS.family, FONTS.base_size),
            bg=COLORS.panel_bg,
            fg=COLORS.text_fg,
            state=tk.DISABLED
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    
    def _init_variables(self) -> None:
        """初始化变量"""
        # 基本变量
        self.audio_path: Optional[str] = None
        self.shots_data = []
        self.total_audio_duration = 0.0
        
        # Tkinter 变量
        self.model_var = tk.StringVar(value="不选择")
        self.width_var = tk.StringVar(value="1920")
        self.height_var = tk.StringVar(value="1080")
        self.transition_var = tk.StringVar(value="硬切")
        self.prompt_type_var = tk.StringVar(value="SD提示词")
        
        # 窗口大小跟踪
        self.current_width = UI_CONFIG["default_width"]
        self.current_height = UI_CONFIG["default_height"]
        self.resize_timer = None
    
    def _bind_events(self) -> None:
        """绑定事件"""
        # 窗口大小变化
        self.root.bind("<Configure>", self._on_window_resize)
        
        # 窗口关闭
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _on_window_resize(self, event) -> None:
        """窗口大小变化处理"""
        # 检查窗口大小是否真的发生了变化
        if event.width == self.current_width and event.height == self.current_height:
            return
        
        self.current_width = event.width
        self.current_height = event.height
        
        # 防抖处理
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)
        
        self.resize_timer = self.root.after(
            UI_CONFIG["resize_delay"],
            self._handle_resize
        )
    
    def _handle_resize(self) -> None:
        """处理窗口大小变化的实际逻辑"""
        scale_factor = min(
            self.current_width / UI_CONFIG["default_width"],
            self.current_height / UI_CONFIG["default_height"]
        )
        
        self.style_manager.update_font_size(scale_factor)
    
    def _on_close(self) -> None:
        """窗口关闭处理"""
        # 执行清理操作
        # ...
        
        # 关闭窗口
        self.root.destroy()
    
    def log(self, message: str) -> None:
        """
        输出日志
        
        Args:
            message: 日志消息
        """
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, message + "\n")
        self.txt_log.see(tk.END)
        self.txt_log.configure(state=tk.DISABLED)
    
    def run(self) -> None:
        """运行主窗口"""
        self.root.mainloop()


# 便捷函数
def create_main_window() -> MainWindow:
    """创建主窗口实例"""
    return MainWindow()

# ======================================================================# 模块: ui# ======================================================================
UI 模块 - 用户界面组件
"""

from .styles import StyleManager, COLORS, FONTS
from .main_window import MainWindow

__all__ = [
    'StyleManager',
    'COLORS',
    'FONTS',
    'MainWindow',
]

# ======================================================================# 模块: main# ======================================================================
短视频生成器 - 主入口文件

这是一个模块化的短视频生成器应用，用于：
1. 语音转录 -> 分镜脚本生成
2. AI 绘图提示词优化 -> 批量图片生成
3. 图片序列 -> 视频渲染

使用方法：
    python main.py

目录结构：
    video_generator/
    ├── main.py              # 主入口
    ├── config.py            # 配置管理
    ├── cache.py             # 缓存系统
    ├── prompts.py           # 提示词模板
    ├── task_queue.py        # 任务队列
    ├── llm/                 # LLM 模块
    │   ├── __init__.py
    │   ├── ollama_client.py
    │   ├── performance.py
    │   └── model_fusion.py
    ├── generators/          # 生成器模块
    │   ├── __init__.py
    │   ├── image_generator.py
    │   └── shot_creator.py
    ├── ui/                  # UI 模块
    │   ├── __init__.py
    │   ├── styles.py
    │   └── main_window.py
    └── utils/               # 工具模块
        ├── __init__.py
        ├── text.py
        ├── audio.py
        └── helpers.py
"""

import sys
import os
import warnings
import datetime

# 忽略 requests 库的依赖版本警告
warnings.filterwarnings(
    "ignore",
    message="urllib3.*doesn't match a supported version",
    module="requests"
)

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 处理 pythonw 环境（无控制台窗口）
_is_pythonw = sys.executable.lower().endswith('pythonw.exe')
_has_no_console = sys.stdout is None or sys.stderr is None

if _is_pythonw or _has_no_console:
    # 在 Windows 上创建独立的控制台窗口用于显示日志
    try:
        import ctypes
        from ctypes import wintypes
        
        # 创建一个新的控制台窗口
        ctypes.windll.kernel32.AllocConsole()
        
        # 获取控制台窗口句柄
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        
        if hwnd:
            user32 = ctypes.windll.user32
            hMenu = user32.GetSystemMenu(hwnd, False)
            if hMenu:
                MF_GRAYED = 0x00000001
                MF_BYCOMMAND = 0x00000000
                SC_CLOSE = 0xF060
                user32.EnableMenuItem(hMenu, SC_CLOSE, MF_GRAYED | MF_BYCOMMAND)
            
            user32.DrawMenuBar(hwnd)
        
        # 重新打开标准输出和标准错误
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
        
        # 设置控制台标题
        ctypes.windll.kernel32.SetConsoleTitleW(
            "短视频生成器 - 日志控制台（最小化到任务栏查看）"
        )
        
        # 打印启动信息
        print("=" * 60)
        print("🎬 短视频生成器 - 日志控制台")
        print("=" * 60)
        print(f"启动时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
    except Exception as e:
        print(f"控制台初始化失败: {e}")


def main():
    """主函数"""
    # 延迟导入 UI 模块
    
    # 创建并运行主窗口
    app = MainWindow()
    
    print("\n✅ 应用程序启动成功")
    print("   提示: 查看 GUI 窗口进行操作\n")
    
    app.run()


if __name__ == "__main__":
    main()
