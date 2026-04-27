import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import warnings
import sys
import time
import hashlib
import re
import gc
import subprocess
import traceback
import requests

# ============ 性能优化配置常量 ============
class Config:
    OLLAMA_BASE_URL = "http://localhost:11434"
    SD_API_BASE_URL = "http://127.0.0.1:7860"
    API_TIMEOUT_SHORT = 3
    API_TIMEOUT_MEDIUM = 5
    API_TIMEOUT_LONG = 90

    DEFAULT_MAX_WORKERS = 4

    PROMPT_CACHE_SIZE = 500
    PROMPT_CACHE_TTL = 7200
    IMAGE_CACHE_SIZE = 200
    IMAGE_CACHE_TTL = 3600

# ============ 性能优化模块导入 ============
from video_generator.optimization import (
    ProgressManager,
    ResourceManager,
    BatchImageLoader,
    VideoRendererOptimizer
)

# ============ 预编译正则表达式 ============
RE_BOLD = re.compile(r'\*\*([^*]+)\*\*')
RE_ITALIC = re.compile(r'\*([^*]+)\*')
RE_NEWLINES = re.compile(r'\n+')
RE_WHITESPACE = re.compile(r'\s+')
RE_LEADING_PUNCT = re.compile(r'^[，,。、：:；;\s]+')
RE_TRAILING_PUNCT = re.compile(r'[，,。、：:；;\s]+$')
RE_COLON_SPLIT = re.compile(r'[：:]\s*([^\n]+)')

# ============ 全局 HTTP Session (连接复用) ============
_http_session = None

def get_http_session():
    """获取全局 HTTP Session，复用连接提升性能"""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=2
        )
        _http_session.mount('http://', adapter)
        _http_session.mount('https://', adapter)
    return _http_session

# ============ 优化1: 智能缓存系统 ============
class SmartCache:
    """智能缓存系统 - 带TTL和LRU的混合缓存（优化版）"""

    __slots__ = ('max_size', 'default_ttl', '_cache', '_lock', '_hits', '_misses', '_expire_times')

    def __init__(self, max_size=1000, default_ttl=3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache = {}
        self._expire_times = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key):
        """获取缓存值"""
        with self._lock:
            expire_time = self._expire_times.get(key)
            if expire_time is not None:
                if expire_time > time.time():
                    self._hits += 1
                    return self._cache.get(key)
                else:
                    self._cache.pop(key, None)
                    self._expire_times.pop(key, None)
            self._misses += 1
            return None

    def set(self, key, value, ttl=None):
        """设置缓存值"""
        with self._lock:
            if len(self._cache) >= self.max_size:
                min_expire = min(self._expire_times.values()) if self._expire_times else 0
                expired_keys = [k for k, v in self._expire_times.items() if v <= min_expire]
                if expired_keys:
                    for k in expired_keys[:max(1, len(expired_keys) // 4)]:
                        self._cache.pop(k, None)
                        self._expire_times.pop(k, None)

            ttl = ttl or self.default_ttl
            self._cache[key] = value
            self._expire_times[key] = time.time() + ttl

    def get_stats(self):
        """获取缓存统计"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': f"{hit_rate*100:.1f}%",
                'size': len(self._cache)
            }

    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._expire_times.clear()

# 全局缓存实例
prompt_cache = SmartCache(max_size=Config.PROMPT_CACHE_SIZE, default_ttl=Config.PROMPT_CACHE_TTL)
image_cache = SmartCache(max_size=Config.IMAGE_CACHE_SIZE, default_ttl=Config.IMAGE_CACHE_TTL)

# ============ 优化2: 并行提示词生成器 ============

# ============ 优化3: 批量SD图像生成器 ============

# ============ 优化4: 硬件加速视频渲染 ============
class HardwareAcceleratedRenderer:
    """硬件加速视频渲染器 - 延迟检测"""
    
    def __init__(self):
        self._has_cuda = None
        self._has_quicksync = None
        self._preferred_encoder = None
    
    @property
    def has_cuda(self):
        if self._has_cuda is None:
            self._has_cuda = self._check_cuda()
        return self._has_cuda
    
    @property
    def has_quicksync(self):
        if self._has_quicksync is None:
            self._has_quicksync = self._check_quicksync()
        return self._has_quicksync
    
    @property
    def preferred_encoder(self):
        if self._preferred_encoder is None:
            self._preferred_encoder = self._select_encoder()
        return self._preferred_encoder
    
    def _check_cuda(self):
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def _check_quicksync(self):
        try:
            import subprocess
            result = subprocess.run(
                ['ffmpeg', '-hwaccels'], 
                capture_output=True, text=True,
                timeout=3
            )
            return 'qsv' in result.stdout.lower()
        except:
            return False
    
    def _select_encoder(self):
        if self.has_cuda:
            return {'vcodec': 'h264_nvenc', 'preset': 'p4', 'rc': 'vbr', 'cq': 23}
        elif self.has_quicksync:
            return {'vcodec': 'h264_qsv', 'preset': 'medium', 'global_quality': 23}
        else:
            return {'vcodec': 'libx264', 'preset': 'veryfast', 'crf': 23}

print("✅ 优化模块已加载: 智能缓存 + 并行生成 + 批量SD + 硬件加速（延迟检测）")

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 导入增强版内容识别模块
try:
    from video_generator.enhanced_content_recognition import (
        get_enhanced_recognizer, 
        EnhancedContentRecognizer,
        COUNTRY_MAPPING,
        REGION_MAPPING,
        CITY_MAPPING,
        ORGANIZATION_MAPPING,
        MILITARY_MAPPING,
        CONTENT_TYPE_KEYWORDS
    )
    ENHANCED_RECOGNITION_AVAILABLE = True
except ImportError:
    ENHANCED_RECOGNITION_AVAILABLE = False
    print("⚠️ 增强版内容识别模块未找到，使用内置识别")

# 导入 ARV 提示词模板模块（混合模式）
try:
    from video_generator.prompts_arv import (
        ARVPromptTemplates,
        quick_generate_arv_prompt
    )
    ARV_PROMPTS_AVAILABLE = True
except ImportError:
    ARV_PROMPTS_AVAILABLE = False
    print("⚠️ ARV提示词模板模块未找到，使用大模型生成所有提示词")

# 导入ARV绝对写实风格优化模块
try:
    from video_generator.arv_optimization import (
        AbsoluteRealisticPrompts,
        get_arv_prompter
    )
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False
    print("⚠️ ARV优化模块未找到")

# 检测是否在 pythonw 环境下运行（无控制台窗口）
_is_pythonw = sys.executable.lower().endswith('pythonw.exe')
_has_no_console = sys.stdout is None or sys.stderr is None
_console_allocated = False

import ctypes
from ctypes import wintypes

if _is_pythonw or _has_no_console:
    ctypes.windll.kernel32.AllocConsole()
    _console_allocated = True
    
    # 获取控制台窗口句柄
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()

    # 隐藏控制台窗口
    if hwnd:
        SW_HIDE = 0
        ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
else:
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()

if hwnd:
    user32 = ctypes.windll.user32
    
    hMenu = user32.GetSystemMenu(hwnd, False)
    if hMenu:
        SC_CLOSE = 0xF060
        MF_BYCOMMAND = 0x00000000
        user32.DeleteMenu(hMenu, SC_CLOSE, MF_BYCOMMAND)
        user32.DrawMenuBar(hwnd)
    
    GWL_STYLE = -16
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    style = style & ~WS_SYSMENU  
    style = style | WS_MINIMIZEBOX  
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    user32.DrawMenuBar(hwnd)

def _console_ctrl_handler(ctrl_type):
    CTRL_CLOSE_EVENT = 2
    CTRL_LOGOFF_EVENT = 5
    CTRL_SHUTDOWN_EVENT = 6
    if ctrl_type in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
        return True
    return False

try:
    HANDLER_ROUTINE = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
    _handler = HANDLER_ROUTINE(_console_ctrl_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler, True)
except Exception:
    pass

if _is_pythonw or _has_no_console:
    sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
    sys.stderr = open('CONOUT$', 'w', encoding='utf-8')

ctypes.windll.kernel32.SetConsoleTitleW("短视频生成器 - 日志控制台")

print("=" * 60)
print("🎬 短视频生成器 - 日志控制台")
print("=" * 60)
print(f"启动时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"运行模式: {'pythonw.exe (GUI模式)' if _is_pythonw else 'python.exe (控制台模式)'}")
print("=" * 60)
print()
print("💡 提示: 此窗口显示程序运行日志")
print("   • 可以最小化到任务栏")
print("   • 关闭按钮已锁定，请通过主程序退出")
print("   • 关闭主程序时此窗口会自动关闭")
print("=" * 60)
print()

# 忽略requests库的依赖版本警告
warnings.filterwarnings("ignore", message="urllib3.*doesn't match a supported version", module="requests")

# 全局变量
PERFORMANCE_MONITOR_AVAILABLE = False
psutil = None
GPUtil = None
OLLAMA_AVAILABLE = False
ollama = None
ollama_lock = threading.Lock()  # 全局锁，保护Ollama API调用
requests = None

# ==================== 统一的 Ollama 模型调用函数 ====================

# ==================== 提示词优化器 ====================

# 配置常量
DEFAULT_MIN_SHOT_DURATION = 4.0 
SD_API_URL = "http://127.0.0.1:7860"  # 秋叶 SD 默认地址
MAX_RETRY_COUNT = 3  # API 调用最大重试次数
RETRY_DELAY = 2  # 重试延迟（秒）

# ==================== 大模型高级配置 ====================
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
    
    def __init__(self, preset="质量优先"):
        self.preset = preset
        self.config = self.PRESETS.get(preset, self.PRESETS["质量优先"]).copy()
        self.custom_params = {}
    
    def get_options(self, **overrides):
        """获取Ollama调用参数"""
        options = self.config.copy()
        options.update(self.custom_params)
        options.update(overrides)
        # 移除描述字段
        options.pop("description", None)
        return options
    
    def set_custom_param(self, key, value):
        """设置自定义参数"""
        self.custom_params[key] = value
    
    def apply_preset(self, preset_name):
        """应用预设配置"""
        if preset_name in self.PRESETS:
            self.preset = preset_name
            self.config = self.PRESETS[preset_name].copy()
            self.custom_params = {}
            return True
        return False


class LLMPerformanceOptimizer:
    """大模型性能优化器 - 自适应调整参数"""
    
    def __init__(self):
        self.call_history = []
        self.max_history = 10
        self.avg_response_time = 0
        self.success_rate = 1.0
        self._lock = threading.Lock()  # 线程安全锁
        
    def record_call(self, duration, success, token_count=0):
        """记录调用性能"""
        with self._lock:
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
    
    def _update_stats(self):
        """更新性能统计"""
        if not self.call_history:
            return
        
        durations = [h["duration"] for h in self.call_history]
        self.avg_response_time = sum(durations) / len(durations)
        
        successes = sum(1 for h in self.call_history if h["success"])
        self.success_rate = successes / len(self.call_history)
    
    def get_optimal_config(self, task_complexity="medium"):
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
    
    def suggest_optimization(self):
        """提供优化建议"""
        suggestions = []
        
        if self.avg_response_time > 15:
            suggestions.append(f"平均响应时间 {self.avg_response_time:.1f}s 较长，建议使用极速模式或减少num_predict")
        
        if self.success_rate < 0.8:
            suggestions.append(f"成功率 {self.success_rate*100:.1f}% 较低，建议检查模型状态或降低temperature")
        
        if not suggestions:
            suggestions.append(f"性能良好：平均响应 {self.avg_response_time:.1f}s，成功率 {self.success_rate*100:.1f}%")
        
        return suggestions


# 全局优化器实例
llm_optimizer = LLMPerformanceOptimizer()


# ==================== 多模型融合系统 ====================


# 全局多模型融合实例


# ==================== 精简提示词系统 - 大模型自主创作 ====================
class PromptTemplates:
    """精简提示词系统 - 删除过度约束，保留必要指导，让大模型自主创作
    
    核心原则：
    1. 分镜数量由语音片段数量决定（每个segment一个分镜）
    2. 大模型负责：通篇分析、纠正错别字、捋清语义、确定主题基调、生成优化的提示词
    3. 不限制大模型的创作方式，让它根据内容自主发挥
    4. 输出必须是纯粹的提示词，不含任何解释性文字
    5. 统一视觉风格：电影纪实风格，4K画质，真实感
    """
    
    # 主题分析模板 - 智能识别内容类型，针对性分析
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
    
    # 共享的配音语义映射规则 - 用于生成符合配音内容的独特提示词
    # 避免在多个模板中重复维护
    DUBBING_SEMANTIC_MAPPING = {
        "en": """
【重要】每个分镜的配音内容不同，生成的提示词必须体现该配音的独特语义：
- 配音提到"台海和平" → 提示词必须包含Taiwan Strait, peace相关元素
- 配音提到"宪法" → 提示词必须包含constitution, legal document相关元素
- 配音提到"两岸关系" → 提示词必须包含cross-strait, relations相关元素""",
        "zh": """
【重要】每个分镜的配音内容不同，生成的提示词必须体现该配音的独特语义：
- 配音提到"台海和平" → 提示词必须包含台海、和平相关元素
- 配音提到"宪法" → 提示词必须包含宪法、法律文件相关元素
- 配音提到"两岸关系" → 提示词必须包含两岸、关系相关元素"""
    }
    
    # 分镜提示词模板 - SD版本（英文）- 精简版
    SHOT_PROMPT_SD = {
        "system": """你是AI图像提示词工程师，为Stable Diffusion生成英文提示词。

【严格格式要求】
- 必须以质量前缀开头：masterpiece, best quality, ultra detailed, 8k, photorealistic
- 只输出英文关键词，逗号分隔，禁止使用完整句子
- 描述可拍摄的画面内容，不要描述抽象概念或叙事
- 不要输出解释、标题、标注、括号说明
- 结尾必须添加：cinematic lighting, documentary style, film grain texture
- 【核心】提示词必须准确反映当前配音内容的具体场景，禁止千篇一律

{semantic_mapping}

{style_instruction}
{theme_instruction}

【上下文理解规则 - 极其重要】
- 仔细阅读前文上下文和后文上下文，理解当前配音在整体故事中的位置
- 当前配音可能语义不完整，结合上下文推断完整含义
- 避免生成与上下文矛盾的场景，确保视觉连贯性
- 如果当前配音是过渡词或连接词，从上下文推断具体场景
- 考虑故事的叙事流，确保视觉风格在整个视频中保持一致

【位置感知规则】
- 开头分镜：建立场景，介绍主要元素
- 中段分镜：发展故事，展示具体内容
- 结尾分镜：总结主题，强化情感
- 避免前后分镜使用完全相同的场景设置

【示例】
配音："中东战事升级"
核心主题：战争反思
视觉基调：冷色调，沉重深刻
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, Middle Eastern war zone, destroyed buildings, smoke rising, military tanks, desert road, fighter jets overhead, cold blue tones, tense atmosphere, war documentary, news photography, cinematic lighting, documentary style, film grain texture

配音："科学家发现新黑洞"
核心主题：宇宙探索
视觉基调：神秘，科技感
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, space telescope control room, scientists, data screens, monitors, cosmic imagery, deep space background, mysterious atmosphere, high-tech setting, professional lighting, cinematic lighting, documentary style, film grain texture

配音："幸福的一家人"
核心主题：家庭温情
视觉基调：温暖，明亮
输出：masterpiece, best quality, ultra detailed, 8k, photorealistic, Asian family, warm home interior, living room, soft golden light, candid moment, happy expressions, warm atmosphere, lifestyle photography, cinematic lighting, documentary style, film grain texture

【必加标签】masterpiece, best quality, ultra detailed, 8k, photorealistic, cinematic lighting, documentary style, film grain texture""",
        
        "user_template": """配音：{dubbing}

输出英文提示词："""
    }
    
    @classmethod
    def get_template(cls, template_type, **kwargs):
        """获取提示词模板
        
        Args:
            template_type: 模板类型
            **kwargs: 模板参数，包括：
                - visual_style: 用户预设的视觉风格（如有）
                - dubbing: 配音文本
                - 其他参数...
        """
        templates = {
            "theme_analysis": cls.THEME_ANALYSIS,
            "shot_prompt_sd": cls.SHOT_PROMPT_SD,
            "theme_extraction": cls.THEME_ANALYSIS,
        }
        
        if template_type not in templates:
            # 默认返回空模板，让大模型完全自主
            return {
                "system": "",
                "user": kwargs.get("text", kwargs.get("description", ""))
            }
        
        template = templates[template_type]
        
        # 只有 shot_prompt 模板需要处理 style_instruction 和 theme_instruction
        is_shot_prompt = template_type == "shot_prompt_sd"
        
        if is_shot_prompt:
            # 处理风格指令
            visual_style = kwargs.get("visual_style", "")
            is_sd = template_type == "shot_prompt_sd"
            
            if visual_style and visual_style.strip():
                # 用户预设了风格，强制使用该风格
                style_instruction = f"""【重要：必须使用用户预设的风格】
用户预设的视觉风格：{visual_style}
你必须严格按照此风格生成提示词，禁止自行更改或添加其他风格。"""
            else:
                # 用户未预设风格，让模型自主选择
                style_instruction = """【风格选择】
根据内容自主选择合适的视觉风格（如电影感、新闻纪实、艺术摄影、商业摄影等）。"""
            
            # 处理主题指令（核心主题 + 视觉基调）
            core_theme = kwargs.get("core_theme", "")
            visual_tone = kwargs.get("visual_tone", "")
            
            if (core_theme and core_theme != "未指定") or (visual_tone and visual_tone.strip()):
                # 用户设置了主题或基调，生成指令
                theme_parts = []
                if core_theme and core_theme != "未指定":
                    theme_parts.append(f"核心主题：{core_theme}")
                if visual_tone and visual_tone.strip():
                    theme_parts.append(f"视觉基调：{visual_tone}")
                
                theme_text = "，".join(theme_parts)
                theme_instruction = f"""【重要：必须融入以下元素】
{theme_text}
你生成的提示词必须体现以上主题和基调，将其转化为具体的视觉元素。"""
            else:
                # 用户未设置，不需要额外指令
                theme_instruction = ""
            
            # 格式化 system prompt（同时处理两个占位符）
            # 如果 theme_instruction 为空，移除多余的空行
            # 获取对应的语义映射
            semantic_mapping = cls.DUBBING_SEMANTIC_MAPPING["en"] if is_sd else cls.DUBBING_SEMANTIC_MAPPING["zh"]
            
            if theme_instruction:
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction=theme_instruction,
                    semantic_mapping=semantic_mapping
                )
            else:
                # theme_instruction 为空时，移除对应的那一行避免空行
                system_content = template["system"].format(
                    style_instruction=style_instruction,
                    theme_instruction="",
                    semantic_mapping=semantic_mapping
                )
                # 清理多余空行
                system_content = system_content.replace("\n\n\n", "\n\n")
            
            # 构建 user prompt
            dubbing = kwargs.get("dubbing", "")
            context_hint = kwargs.get("context_hint", "")
            
            if context_hint:
                user_content = f"""{context_hint}
当前配音：{dubbing}

根据上下文和当前配音生成英文提示词："""
            else:
                user_content = f"""配音：{dubbing}

输出英文提示词："""
        else:
            # theme_analysis 模板，直接使用原模板
            system_content = template["system"]
            user_content = template["user_template"].format(**kwargs)
        
        return {
            "system": system_content,
            "user": user_content
        }



# 延迟导入函数
def lazy_import():
    """延迟导入非必要模块"""
    global PERFORMANCE_MONITOR_AVAILABLE, psutil, GPUtil
    global OLLAMA_AVAILABLE, ollama
    global requests
    
    try:
        # 尝试导入性能监控库
        try:
            import psutil as _psutil
            import GPUtil as _GPUtil
            psutil = _psutil
            GPUtil = _GPUtil
            PERFORMANCE_MONITOR_AVAILABLE = True
        except ImportError:
            pass
        
        # 尝试导入Ollama客户端
        try:
            import ollama as _ollama
            ollama = _ollama
            OLLAMA_AVAILABLE = True
        except ImportError:
            pass
        
        # 导入 requests
        import requests as _requests
        requests = _requests
        
    except Exception as e:
        print(f"延迟导入模块失败: {e}")

class DocuMakerLiteV7:
    # =======================================================================
    # 第一部分：UI 初始化 (行 1504-1900)
    # =======================================================================
    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        
        self.video_renderer = None
        
        self._initialize_ui()
        self._initialize_variables()
        self._initialize_systems()
        self._setup_ui_components()
        self._initialize_event_handlers()
        self._start_system_services()
        
        # 显示优化状态（不立即检测硬件）
        prompt_threads = self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
        thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16
        print(f"🚀 性能优化已启用:")
        print(f"   - 并行提示词生成: {prompt_threads}线程（按需加载）")
        print(f"   - 图像生成线程: {thread_count}")
        print(f"   - 批量图像生成: 就绪")
        print(f"   - 视频编码器: 延迟检测（首次使用时）")
    
    def _initialize_ui(self):
        """初始化用户界面"""
        self.root.title("DocuMaker Pro Lite V7 | 智能分镜工作流 (SD API 连通版)")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # 初始化完成标志 - 防止启动时resize事件触发样式重设
        self._ui_initialized = False
        
        # 启用高DPI支持
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        
        # 配色方案
        self.bg_color = "#1e1e1e"
        self.panel_bg = "#252526"
        self.text_fg = "#d4d4d4"
        self.accent_blue = "#2196f3"
        self.accent_red = "#f44336"
        self.btn_mid_bg = "#3c3f41"
        
        # 基础字体大小
        self.base_font_size = 12
        self.font_size = self.base_font_size
        
        # 防抖相关
        self.resize_timer = None
        self.resize_delay = 500  # 增加防抖延迟到500毫秒
        
        # 窗口大小跟踪
        self.current_width = 1000
        self.current_height = 700
        
        # 先创建布局
        self._create_layout()
        
        # 设置样式（只执行一次）
        self._setup_styles()
        self.root.configure(bg=self.bg_color)
        
        # 监听窗口大小变化事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 标记UI初始化完成
        self._ui_initialized = True
    
    def _setup_styles(self):
        """设置UI样式"""
        try:
            self.style = ttk.Style()
            if 'clam' in self.style.theme_names():
                self.style.theme_use('clam')
            
            # 基础样式
            self.style.configure("TFrame", background=self.bg_color)
            self.style.configure("TLabel", background=self.bg_color, foreground=self.text_fg, font=("Microsoft YaHei", self.font_size + 2))
            self.style.configure("Header.TLabel", background=self.bg_color, foreground="#00bcd4", font=("Microsoft YaHei", self.font_size + 4, "bold"))
            
            # 按钮样式
            self.style.configure("LargeBlue.TButton", background=self.accent_blue, foreground="#ffffff", 
                               font=("Microsoft YaHei", self.font_size + 6, "bold"), padding=(15, 15), relief="flat")
            self.style.map("LargeBlue.TButton", background=[('active', '#1976d2')])
            
            self.style.configure("LargeRed.TButton", background=self.accent_red, foreground="#ffffff", 
                               font=("Microsoft YaHei", self.font_size + 6, "bold"), padding=(15, 15), relief="flat")
            self.style.map("LargeRed.TButton", background=[('active', '#d32f2f')])

            self.style.configure("Medium.TButton", background=self.btn_mid_bg, foreground="#ffffff", 
                               font=("Microsoft YaHei", self.font_size + 4), padding=(10, 12), relief="flat")
            self.style.map("Medium.TButton", background=[('active', '#505050')])
            
            self.style.configure("Small.TButton", background=self.btn_mid_bg, foreground="#ffffff", 
                               font=("Microsoft YaHei", self.font_size + 2), padding=(5, 5), relief="flat")
            self.style.map("Small.TButton", background=[('active', '#505050')])
            
            # 复选框样式
            self.style.configure("TCheckbutton", background=self.bg_color, foreground=self.text_fg, 
                               font=("Microsoft YaHei", self.font_size))
            
            # 进度条样式 - 使用亮绿色进度条，与深色背景形成鲜明对比
            self.style.configure("TProgressbar", 
                               thickness=20,
                               background="#00FF00",  # 亮绿色进度条
                               troughcolor="#1a1a1a",  # 深色背景
                               borderwidth=0)
            
            # 配置模式下拉框样式 - 使用亮白色字体和更大的高度
            self.style.configure("Config.TCombobox", 
                               font=("Microsoft YaHei", self.font_size + 4),
                               padding=(10, 8))
            self.style.map("Config.TCombobox", 
                          selectbackground=[('readonly', self.bg_color)],
                          selectforeground=[('readonly', '#ffffff')],
                          fieldbackground=[('readonly', self.panel_bg)],
                          foreground=[('readonly', '#ffffff')])
        except Exception as e:
            self.log(f"样式设置失败: {e}")
    
    def on_window_resize(self, event):
        """窗口大小变化时的处理"""
        # UI未完成初始化时不处理
        if not getattr(self, '_ui_initialized', False):
            return
        
        # 只处理窗口大小变化，忽略其他Configure事件
        if event.widget != self.root:
            return
        
        # 检查窗口大小是否真的发生了变化
        if event.width == self.current_width and event.height == self.current_height:
            return
        
        # 更新当前窗口大小
        self.current_width = event.width
        self.current_height = event.height
        
        # 防抖处理，避免高频触发
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)
        
        # 延迟执行调整逻辑
        self.resize_timer = self.root.after(self.resize_delay, lambda: self._handle_resize(event))
    
    def _handle_resize(self, event):
        """处理窗口大小变化的实际逻辑 - 优化版"""
        # 计算缩放比例
        width = event.width
        height = event.height
        
        # 基于窗口宽度计算字体大小
        scale_factor = min(width / 1000, height / 700)
        new_font_size = max(8, int(self.base_font_size * scale_factor))
        
        # 只有字体大小变化超过2个像素才更新，避免频繁重设样式
        if abs(new_font_size - self.font_size) >= 2:
            self.font_size = new_font_size
            # 使用after延迟执行样式更新，避免阻塞UI
            self.root.after(100, self._update_fonts_async)
    
    def _update_fonts_async(self):
        """异步更新字体，避免阻塞UI"""
        try:
            self._setup_styles()
            
            # 更新文本框字体大小
            if hasattr(self, 'txt_script') and self.txt_script:
                self.txt_script.configure(font=("Microsoft YaHei", self.font_size + 4))
            if hasattr(self, 'txt_log') and self.txt_log:
                self.txt_log.configure(font=("Microsoft YaHei", self.font_size + 4))
        except Exception:
            pass
    
    def _create_layout(self):
        """创建UI布局"""
        # 主分割窗口
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # 左侧面板
        self.left_frame = ttk.Frame(self.main_paned, width=280)
        self.main_paned.add(self.left_frame, weight=0)
        
        # 右侧分割窗口
        self.right_paned = ttk.PanedWindow(self.main_paned, orient=tk.VERTICAL)
        self.main_paned.add(self.right_paned, weight=1)

        # 日志区域（独占右侧，分镜脚本窗口已移除）
        self.log_frame_container = ttk.Frame(self.right_paned)
        self.right_paned.add(self.log_frame_container, weight=1)
    
    def _initialize_variables(self):
        """初始化变量"""
        # 基本路径
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = os.path.join(self.base_dir, "output_project")
        self.images_dir = os.path.join(self.output_dir, "images")
        self.config_file = os.path.join(self.base_dir, "config.json")
        
        # 创建必要的目录
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
        
        # 启动时清理上次可能残留的磁盘文件（防止异常退出后数据残留）
        self._cleanup_residual_files()
        
        # 核心变量
        self.audio_path = None
        self.shots_data = [] 
        self.total_audio_duration = 0
        self.MIN_SHOT_DURATION = DEFAULT_MIN_SHOT_DURATION
        self.whisper_model = None  # 缓存 Whisper 模型
        
        # API设置
        self.api_var = tk.StringVar(value="Stable Diffusion API")
        self.sd_api_url_var = tk.StringVar(value="http://localhost:7860")
        self.sd_api_status_var = tk.StringVar(value="❌ 未连接")  # SD API 连接状态（提前初始化）
        
        # 大模型设置
        self.ollama_model_var = tk.StringVar(value="")
        self.model_dropdown_visible = False
        
        # 大模型高级配置 - 初始值为质量优先，由load_config加载
        self.llm_config_preset_var = tk.StringVar(value="质量优先")
        self.llm_config_presets = list(LLMConfig.PRESETS.keys())
        self.current_llm_config = LLMConfig("质量优先")
        
        # 视频设置 - 初始值为硬切（无过渡效果，速度最快），由load_config加载
        self.transition_var = tk.StringVar(value="硬切")
        self.transition_dropdown_visible = False
        
        # 绘图设置
        self.model_var = tk.StringVar(value="使用当前模型")
        self.width_var = tk.StringVar(value="1920")
        self.height_var = tk.StringVar(value="1080")
        
        # 主题自定义设置
        self.custom_theme_var = tk.StringVar(value="")
        self.custom_visual_tone_var = tk.StringVar(value="")
        
        # 提示词类型设置 - 初始值为SD提示词
        self.prompt_type_var = tk.StringVar(value="SD提示词")
        
        # 动画类型设置 - 初始值为无
        self.animation_var = tk.StringVar(value="无")
        
        # 并发线程数设置 - 初始默认值，由高级设置面板和load_config覆盖
        self.thread_count_var = tk.IntVar(value=16)
        self.prompt_thread_count_var = tk.IntVar(value=Config.DEFAULT_MAX_WORKERS)
        
        # 音频模型设置 - 初始默认值，由load_config覆盖
        self.whisper_model_var = tk.StringVar(value="medium")
        
        # 风格预设 - 初始空列表，由高级设置面板填充
        self.dlr_vars = []
        
        # 模型下拉菜单（分镜脚本窗口已移除，这些frame暂不挂载到UI）
        self.model_dropdown_frame = ttk.Frame(self.log_frame_container)
        self.transition_dropdown_frame = ttk.Frame(self.log_frame_container)
        
        # 任务管理
        self.task_queue = []
        self.current_task = None
        self.task_running = False
        self.task_paused = False
        self.task_lock = threading.Lock()
        self.resource_lock = threading.RLock()  # 用于保护共享资源的可重入锁
        self.task_executor = None
        self.max_workers = min((os.cpu_count() or 4) // 2, 4)
        self.pause_event = threading.Event()
        self.pause_event.set()
        
        # 任务优先级和状态
        self.TASK_PRIORITY = {
            'generate_shots': 3,      # 最高优先级
            'generate_images': 2,     # 中优先级
            'generate_video': 1        # 低优先级
        }
        
        self.TASK_STATUS = {
            'queued': '排队中',
            'running': '执行中',
            'paused': '已暂停',
            'completed': '已完成',
            'failed': '失败',
            'cancelled': '已取消'
        }
    
    def _initialize_systems(self):
        """初始化各个系统"""
        # ========== 启动时清空所有全局缓存（确保全新开始）==========
        try:
            prompt_cache.clear()
            image_cache.clear()
            self.log("🗑️ 已清空全局缓存（prompt_cache + image_cache）")
        except Exception as e:
            self.log(f"⚠️ 清空全局缓存失败: {e}")
        
        # 通信系统
        self.event_system = {}
        self.state_manager = {}
        self.data_bus = {}

        # 缓存系统
        self.cache_system = {
            'models': {},
            'prompts': {},
            'images': {},
            'audio': {}
        }

        # 线程池管理
        self.thread_pool = {}
        self.thread_pool_stats = {
            'active_threads': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_tasks': 0
        }

        # ARV提示词生成器（保持单例，确保分镜连贯性）
        self.arv_prompter = None
        if ARV_OPTIMIZATION_AVAILABLE:
            try:
                self.arv_prompter = get_arv_prompter()
            except Exception:
                pass

        # 初始化各个系统
        self.init_state_manager()
        self.init_event_system()
        self.init_cache_system()
        self.init_thread_pool()
    
    def _setup_ui_components(self):
        """设置UI组件"""
        self.setup_script_area()
        self.setup_log_area()
        self.setup_left_panel()
        
        # 初始化高级设置窗口
        self.advanced_window = None
    
    def _initialize_event_handlers(self):
        """初始化事件处理器"""
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 加载配置
        self.load_config()
    
    def _start_system_services(self):
        """启动系统服务"""
        # 延迟导入非必要模块
        threading.Thread(target=lazy_import, daemon=True).start()
        
        # 启动时运行系统检查（延迟执行，让UI先加载）
        def delayed_system_check():
            # 等待延迟导入完成
            time.sleep(1)  # 等待Ollama模块加载完成
            
            self.system_check()
            # 系统检查完成后，尝试连接SD API（静默模式，不弹窗）
            time.sleep(1)
            self.check_sd_api_connection(silent=True)
            
            # 【修改】启动时自动检测并连接Ollama服务
            self.auto_connect_ollama()
        threading.Thread(target=delayed_system_check, daemon=True).start()
        
        # 预加载Whisper模型（延迟执行，让UI先加载）
        def preload_whisper():
            time.sleep(2)  # 等待UI完全加载后再预加载
            self.preload_whisper_model()
            
            # 所有预加载完成后，显示就绪提示
            time.sleep(0.5)  # 稍微延迟，确保日志输出顺序正确
            self.log("")
            self.log("=" * 60)
            self.log("✅ 程序启动完成，工具已就绪！")
            self.log("📂 请导入音频文件开始创作")
            self.log("=" * 60)
            self.log("")
        threading.Thread(target=preload_whisper, daemon=True).start()
    
    def auto_connect_ollama(self):
        """启动时自动检测并连接Ollama服务 - 失败时弹窗提醒"""
        global OLLAMA_AVAILABLE
        
        try:
            import requests
            import subprocess
            import os
            
            try:
                response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_SHORT)
                if response.status_code == 200:
                    OLLAMA_AVAILABLE = True
                    self.log("✅ Ollama服务已连接")
                    return
            except Exception:
                pass
            
            ollama_path = None
            for path in [r"C:\Ollama\ollama.exe", r"C:\Program Files\Ollama\ollama.exe", 
                       os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                       "ollama"]:
                if os.path.exists(path) or path == "ollama":
                    ollama_path = path
                    break
            
            if ollama_path:
                subprocess.Popen([ollama_path, "serve"], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                time.sleep(3)
                try:
                    response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
                    if response.status_code == 200:
                        OLLAMA_AVAILABLE = True
                        self.log("✅ Ollama服务已启动并连接")
                        return
                except Exception:
                    pass
            
            # 连接失败 - 弹窗提醒用户
            OLLAMA_AVAILABLE = False
            self.log("❌ Ollama服务连接失败")
            self.root.after(0, lambda: messagebox.showwarning(
                "Ollama服务未连接",
                "Ollama大模型服务未运行，且自动启动失败！\n\n"
                "分镜生成和提示词生成需要Ollama服务支持。\n\n"
                "请手动启动Ollama后重试，或在高级设置中检查Ollama模型配置。"
            ))
        except Exception as e:
            OLLAMA_AVAILABLE = False
            self.log(f"❌ Ollama连接失败: {e}")
            self.root.after(0, lambda: messagebox.showwarning(
                "Ollama服务异常",
                f"Ollama服务连接异常：{e}\n\n"
                "分镜生成和提示词生成需要Ollama服务支持。"
            ))
    
    def preload_whisper_model(self):
        """预加载Whisper模型 - 仅加载到CPU，使用时再按需移至GPU，节省显存"""
        try:
            import whisper
            
            whisper_model_size = "medium"
            
            self.log(f"🔄 预加载 Whisper {whisper_model_size} 模型到内存...")
            self.whisper_model = whisper.load_model(whisper_model_size, device="cpu")
            self.log(f"✅ Whisper {whisper_model_size} 模型预加载完成 (CPU，使用时自动加载到GPU)")
                
        except Exception as e:
            self.log(f"⚠️ Whisper模型预加载失败: {e}")
    
    # =======================================================================
    # 第二部分：设置面板与UI组件 (行 1949-2827)
    # =======================================================================
    def setup_left_panel(self):
        """设置左侧控制面板"""
        # 主框架，使用grid布局实现均匀分布
        frame = ttk.Frame(self.left_frame, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置grid布局，使行和列能够自适应
        frame.columnconfigure(0, weight=1)
        
        # 为每个功能组设置权重，实现均匀分布
        for i in range(8):
            frame.rowconfigure(i, weight=1)
        
        # 顶部标题和文件夹按钮
        title_frame = ttk.Frame(frame)
        title_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        title_frame.columnconfigure(0, weight=1)
        title_frame.columnconfigure(1, weight=0)
        
        title_label = ttk.Label(title_frame, text="🎛️ 控制台", style="Header.TLabel")
        title_label.grid(row=0, column=0, sticky="w")
        
        # 添加文件夹按钮，点击打开output_project文件夹
        btn_open_folder = ttk.Button(title_frame, text="📁 打开文件夹", command=self.open_output_folder, style="Medium.TButton")
        btn_open_folder.grid(row=0, column=1, padx=(10, 0), sticky="e")

        # 第一组：音频导入
        section1 = ttk.Frame(frame)
        section1.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        section1.columnconfigure(0, weight=1)
        section1.rowconfigure(0, weight=1)
        section1.rowconfigure(1, weight=1)
        
        btn_import = ttk.Button(section1, text="📂 导入音频", command=self.import_audio, style="LargeBlue.TButton")
        btn_import.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 音频状态和清理按钮
        audio_status_frame = ttk.Frame(section1)
        audio_status_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.lbl_audio_status = tk.Label(audio_status_frame, text="未加载音频", wraplength=200, justify="left", font=("Microsoft YaHei", 14, "bold"), foreground="#FFFFFF", bg="#2b2b2b")
        self.lbl_audio_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 添加垃圾筐按钮
        btn_clear_audio = ttk.Button(audio_status_frame, text="🗑️", command=self.clear_audio, style="Small.TButton")
        btn_clear_audio.pack(side=tk.RIGHT, padx=5)

        # 分隔线
        sep1 = ttk.Separator(frame, orient='horizontal')
        sep1.grid(row=2, column=0, sticky="ew", pady=5)

        # 第二组：生成分镜
        section2 = ttk.Frame(frame)
        section2.grid(row=3, column=0, sticky="nsew", pady=(0, 5))
        section2.columnconfigure(0, weight=1)
        section2.rowconfigure(0, weight=1)
        
        btn_generate = ttk.Button(section2, text="🎬 生成分镜脚本", command=self.generate_shots_threaded, style="LargeBlue.TButton")
        btn_generate.pack(fill=tk.BOTH, expand=True, pady=5)

        # 分隔线
        sep2 = ttk.Separator(frame, orient='horizontal')
        sep2.grid(row=4, column=0, sticky="ew", pady=5)

        # 第三组：视频生成
        section5 = ttk.Frame(frame)
        section5.grid(row=5, column=0, sticky="nsew", pady=(0, 5))
        section5.columnconfigure(0, weight=1)
        section5.rowconfigure(0, weight=1)
        section5.rowconfigure(1, weight=1)
        
        btn_render = ttk.Button(section5, text="🎞️ 生成视频", command=self.render_video_threaded, style="LargeRed.TButton")
        btn_render.pack(fill=tk.BOTH, expand=True, pady=5)
        


        # 分隔线
        sep3 = ttk.Separator(frame, orient='horizontal')
        sep3.grid(row=6, column=0, sticky="ew", pady=5)

        # 第四组：进度条和依赖检查
        status_frame = ttk.Frame(frame)
        status_frame.grid(row=7, column=0, sticky="nsew", pady=(0, 5))
        status_frame.columnconfigure(0, weight=1)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 进度标签
        self.lbl_progress = tk.Label(status_frame, text="就绪", background="#2b2b2b", foreground="#FFFFFF", font=("Microsoft YaHei", 16, "bold"))
        self.lbl_progress.pack(anchor=tk.W, pady=2)
        
        # 依赖检查更新按钮
        btn_check_deps = ttk.Button(status_frame, text="🔧 检查更新依赖", command=self.check_and_update_dependencies, style="Medium.TButton")
        btn_check_deps.pack(fill=tk.X, pady=5)
        
        # 高级设置按钮
        btn_advanced = ttk.Button(status_frame, text="⚙️ 高级设置", command=self.toggle_advanced_settings, style="Medium.TButton")
        btn_advanced.pack(fill=tk.X, pady=5)
        
        # 性能统计按钮
        btn_stats = ttk.Button(status_frame, text="📊 性能统计", command=self.show_performance_stats, style="Medium.TButton")
        btn_stats.pack(fill=tk.X, pady=5)

        # 性能监控面板
        if PERFORMANCE_MONITOR_AVAILABLE:
            perf_frame = ttk.LabelFrame(frame, text="📊 系统资源监控", padding=10)
            perf_frame.grid(row=8, column=0, sticky="nsew", pady=(5, 0))
            perf_frame.columnconfigure(0, weight=1)
            
            # CPU监控
            cpu_frame = ttk.Frame(perf_frame)
            cpu_frame.pack(fill=tk.X, pady=2)
            ttk.Label(cpu_frame, text="CPU:", width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
            self.cpu_label = ttk.Label(cpu_frame, text="--%", font=("Microsoft YaHei", 9))
            self.cpu_label.pack(side=tk.LEFT)
            
            # 内存监控
            memory_frame = ttk.Frame(perf_frame)
            memory_frame.pack(fill=tk.X, pady=2)
            ttk.Label(memory_frame, text="内存:", width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
            self.memory_label = ttk.Label(memory_frame, text="--%", font=("Microsoft YaHei", 9))
            self.memory_label.pack(side=tk.LEFT)
            
            # GPU监控
            gpu_frame = ttk.Frame(perf_frame)
            gpu_frame.pack(fill=tk.X, pady=2)
            ttk.Label(gpu_frame, text="GPU:", width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
            self.gpu_label = ttk.Label(gpu_frame, text="--%", font=("Microsoft YaHei", 9))
            self.gpu_label.pack(side=tk.LEFT)
            
            # 内存使用详情
            memory_detail_frame = ttk.Frame(perf_frame)
            memory_detail_frame.pack(fill=tk.X, pady=2)
            ttk.Label(memory_detail_frame, text="内存详情:", width=8, font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
            self.memory_detail_label = ttk.Label(memory_detail_frame, text="-- MB / -- MB", font=("Microsoft YaHei", 9))
            self.memory_detail_label.pack(side=tk.LEFT)
            
            # 启动性能监控线程
            self.perf_monitor_running = True
            self._perf_monitor_interval = 5.0  # 性能监控间隔（秒），任务中自动切换为2s
            self.perf_monitor_thread = threading.Thread(target=self.monitor_performance, daemon=True)
            self.perf_monitor_thread.start()

    def setup_advanced_panel_content(self, adv_frame):
        """创建风格设置的内容"""
        # 增加字体大小
        large_font_size = self.font_size + 4
        
        # 1. 绘图设置部分
        section_frame = ttk.LabelFrame(adv_frame, text="🎨 绘图设置", padding=15)
        section_frame.pack(fill=tk.X, pady=5)
        
        # 绘图模型
        model_frame = ttk.Frame(section_frame)
        model_frame.pack(fill=tk.X, pady=3)
        ttk.Label(model_frame, text="模型:", width=12, font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT, padx=5)
        
        # 如果变量不存在，则初始化（保持与已加载配置的一致性）
        if not hasattr(self, 'model_var') or self.model_var.get() == "":
            self.model_var = tk.StringVar(value="使用当前模型")
        
        # 默认模型列表（当 SD API 未连接时使用）
        self._default_models = ["使用当前模型", "Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3"]
        
        # 先使用默认列表快速显示窗口，避免阻塞
        models = self._default_models
        
        model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, values=models, state="readonly", font=("Microsoft YaHei", large_font_size))
        model_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # 保存下拉菜单引用，以便后续更新
        self.model_combo = model_combo
        
        # 异步获取 SD 模型列表（不阻塞 UI）
        self._async_update_sd_models()
        
        # 图片像素设置
        pixel_frame = ttk.Frame(section_frame)
        pixel_frame.pack(fill=tk.X, pady=3)
        ttk.Label(pixel_frame, text="像素尺寸:", width=12, font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT, padx=5)
        
        width_frame = ttk.Frame(pixel_frame)
        width_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(width_frame, text="宽:", font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT)
        
        # 如果变量不存在，则初始化
        if not hasattr(self, 'width_var') or self.width_var.get() == "":
            self.width_var = tk.StringVar(value="1920")
        
        width_entry = ttk.Entry(width_frame, textvariable=self.width_var, width=10, font=("Microsoft YaHei", large_font_size))
        width_entry.pack(side=tk.LEFT, padx=5, pady=2)
        
        height_frame = ttk.Frame(pixel_frame)
        height_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(height_frame, text="高:", font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT)
        
        # 如果变量不存在，则初始化
        if not hasattr(self, 'height_var') or self.height_var.get() == "":
            self.height_var = tk.StringVar(value="1080")
        
        height_entry = ttk.Entry(height_frame, textvariable=self.height_var, width=10, font=("Microsoft YaHei", large_font_size))
        height_entry.pack(side=tk.LEFT, padx=5, pady=2)

        # 2. 风格设置部分
        style_section = ttk.LabelFrame(adv_frame, text="🎨 风格设置", padding=15)
        style_section.pack(fill=tk.X, pady=5)
        
        # 风格设置控制栏
        self.style_control_frame = ttk.Frame(style_section)
        self.style_control_frame.pack(fill=tk.X, pady=3)
        
        # 风格设置按钮
        self.style_dropdown_visible = False
        self.style_dropdown_frame = ttk.Frame(style_section)
        
        style_button = ttk.Button(self.style_control_frame, text="展开风格选项", command=self.toggle_style_dropdown, style="Medium.TButton")
        style_button.pack(fill=tk.X, padx=5, pady=2)
        
        # 风格预设网格布局（初始隐藏）
        self.style_grid = ttk.Frame(self.style_dropdown_frame)
        self.style_grid.pack(fill=tk.X, pady=3)
        
        # 创建风格预设复选框网格
        style_options = ["电影感", "纪录片风", "赛博朋克", "写实摄影", "皮克斯", "达芬奇", "油画", "多巴胺", "黑白线条", "吉卜力", "梵高", "日式动漫", "水彩"]
        
        # 检查是否需要重新创建dlr_vars
        if not hasattr(self, 'dlr_vars'):
            self.dlr_vars = []
        else:
            # 清空现有列表
            self.dlr_vars.clear()
        
        # 3列网格布局
        for i, opt in enumerate(style_options):
            var = tk.BooleanVar()
            row = i // 3
            col = i % 3
            chk = ttk.Checkbutton(self.style_grid, text=opt, variable=var)
            # ttk.Checkbutton不支持font参数，需要通过style设置
            chk.grid(row=row, column=col, sticky=tk.W, padx=10, pady=8)
            self.dlr_vars.append((opt, var))
        
        # 加载保存的风格设置
        try:
            import os
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 加载风格设置
                if 'selected_styles' in config:
                    selected_styles = config['selected_styles']
                    for style_name, var in self.dlr_vars:
                        if style_name in selected_styles:
                            var.set(True)
                        else:
                            var.set(False)
        except Exception as e:
            pass
        
        # 3. SD API设置部分
        api_section = ttk.LabelFrame(adv_frame, text="🔌 SD API 设置", padding=15)
        api_section.pack(fill=tk.X, pady=5)
        
        # API URL设置
        api_url_frame = ttk.Frame(api_section)
        api_url_frame.pack(fill=tk.X, pady=3)
        ttk.Label(api_url_frame, text="API URL:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        api_url_entry = ttk.Entry(api_url_frame, textvariable=self.sd_api_url_var, font=('Microsoft YaHei', large_font_size))
        api_url_entry.pack(fill=tk.X, padx=5, pady=2)
        
        # API控制按钮
        api_control_frame = ttk.Frame(api_section)
        api_control_frame.pack(fill=tk.X, pady=3)
        
        # SD API状态显示灯
        if not hasattr(self, 'sd_api_status_var'):
            self.sd_api_status_var = tk.StringVar(value="❌ 未连接")
        self.sd_api_status_label = ttk.Label(api_control_frame, textvariable=self.sd_api_status_var, font=('Microsoft YaHei', large_font_size), foreground="red")
        # 根据当前状态设置标签颜色
        if "已连接" in self.sd_api_status_var.get():
            self.sd_api_status_label.config(foreground="green")
        else:
            self.sd_api_status_label.config(foreground="red")
        self.sd_api_status_label.pack(side=tk.LEFT, padx=5)
        
        # 连接/断开按钮
        btn_frame = ttk.Frame(api_control_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        self.btn_connect_api = ttk.Button(btn_frame, text="🔗 连接 API", command=self.check_sd_api_connection, style="Medium.TButton")
        self.btn_connect_api.pack(side=tk.LEFT, padx=5, pady=2)
        
        self.btn_disconnect_api = ttk.Button(btn_frame, text="🔌 断开连接", command=self.close_sd_api_connection, style="Medium.TButton")
        self.btn_disconnect_api.pack(side=tk.LEFT, padx=5, pady=2)
        
        # 4. 视频设置部分
        video_section = ttk.LabelFrame(adv_frame, text="🎬 视频设置", padding=15)
        video_section.pack(fill=tk.X, pady=5)
        
        # 单张画面动画效果设置
        animation_frame = ttk.Frame(video_section)
        animation_frame.pack(fill=tk.X, pady=3)
        ttk.Label(animation_frame, text="单张画面动画:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        # 初始化动画效果变量
        if not hasattr(self, 'animation_var'):
            self.animation_var = tk.StringVar(value="无")
        
        # 动画效果选项（精简版，只保留缩放）
        animation_options = ["无", "缩放"]
        animation_combo = ttk.Combobox(animation_frame, textvariable=self.animation_var, values=animation_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        animation_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # 5. 优化方法部分
        model_section = ttk.LabelFrame(adv_frame, text="🔧 优化方法", padding=15)
        model_section.pack(fill=tk.X, pady=5)
        
        # Ollama模型设置
        ollama_frame = ttk.Frame(model_section)
        ollama_frame.pack(fill=tk.X, pady=3)
        ttk.Label(ollama_frame, text="Ollama模型:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        # 大模型下拉菜单
        ollama_frame_right = ttk.Frame(ollama_frame)
        ollama_frame_right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ollama_button = ttk.Button(ollama_frame_right, textvariable=self.ollama_model_var, command=self.toggle_model_dropdown, style="Medium.TButton")
        ollama_button.pack(fill=tk.X, padx=5, pady=2)
        
        # 大模型下拉菜单框架 - 添加滚动条支持
        self.model_dropdown_frame = ttk.Frame(ollama_frame_right)
        self.model_dropdown_canvas = tk.Canvas(self.model_dropdown_frame, height=200, highlightthickness=0, bg=self.panel_bg)
        self.model_dropdown_scrollbar = ttk.Scrollbar(self.model_dropdown_frame, orient="vertical", command=self.model_dropdown_canvas.yview)
        self.model_dropdown_inner_frame = ttk.Frame(self.model_dropdown_canvas)
        
        self.model_dropdown_canvas.configure(yscrollcommand=self.model_dropdown_scrollbar.set)
        self.model_dropdown_inner_frame.bind("<Configure>", lambda e: self.model_dropdown_canvas.configure(scrollregion=self.model_dropdown_canvas.bbox("all")))
        
        # 大模型配置模式选择
        config_frame = ttk.Frame(model_section)
        config_frame.pack(fill=tk.X, pady=3)
        ttk.Label(config_frame, text="配置模式:", width=12, font=('Microsoft YaHei', large_font_size, 'bold')).pack(side=tk.LEFT, padx=5)
        
        # 配置模式下拉菜单 - 使用自定义样式和更大的尺寸
        config_combo = ttk.Combobox(
            config_frame, 
            textvariable=self.llm_config_preset_var, 
            values=self.llm_config_presets, 
            state="readonly",
            style="Config.TCombobox",
            height=10
        )
        config_combo.pack(fill=tk.X, padx=5, pady=2, ipady=3)
        config_combo.bind('<<ComboboxSelected>>', self.on_llm_config_changed)
        
        # 并发线程数设置
        thread_section = ttk.LabelFrame(adv_frame, text="⚡ 并发设置", padding=15)
        thread_section.pack(fill=tk.X, pady=5)
        
        # 分镜创建线程数
        thread_frame = ttk.Frame(thread_section)
        thread_frame.pack(fill=tk.X, pady=3)
        ttk.Label(thread_frame, text="分镜创建线程:", width=14, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'thread_count_var'):
            self.thread_count_var = tk.IntVar(value=16)
        
        thread_options = [4, 8, 12, 16, 24, 32]
        thread_combo = ttk.Combobox(
            thread_frame,
            textvariable=self.thread_count_var,
            values=thread_options,
            state="readonly",
            font=('Microsoft YaHei', large_font_size),
            width=8
        )
        thread_combo.pack(side=tk.LEFT, padx=5, pady=2)
        
        # 提示词生成线程数（新增）
        prompt_thread_frame = ttk.Frame(thread_section)
        prompt_thread_frame.pack(fill=tk.X, pady=3)
        ttk.Label(prompt_thread_frame, text="提示词生成线程:", width=14, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'prompt_thread_count_var'):
            self.prompt_thread_count_var = tk.IntVar(value=4)
        
        prompt_thread_options = [1, 2, 3, 4, 6, 8]
        prompt_thread_combo = ttk.Combobox(
            prompt_thread_frame,
            textvariable=self.prompt_thread_count_var,
            values=prompt_thread_options,
            state="readonly",
            font=('Microsoft YaHei', large_font_size),
            width=8
        )
        prompt_thread_combo.pack(side=tk.LEFT, padx=5, pady=2)
        
        # 6. 提示词设置部分
        prompt_section = ttk.LabelFrame(adv_frame, text="💬 提示词设置", padding=15)
        prompt_section.pack(fill=tk.X, pady=5)
        
        # 提示词类型选择
        prompt_frame = ttk.Frame(prompt_section)
        prompt_frame.pack(fill=tk.X, pady=3)
        ttk.Label(prompt_frame, text="提示词类型:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        # 初始化提示词类型变量 - 如果已存在则不再创建
        if not hasattr(self, 'prompt_type_var'):
            self.prompt_type_var = tk.StringVar(value="SD提示词")
        
        # 提示词类型选项
        prompt_options = ttk.Frame(prompt_frame)
        prompt_options.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # SD提示词按钮
        sd_prompt_btn = ttk.Button(prompt_options, text="SD提示词", command=lambda: self._on_prompt_type_changed("SD提示词"), style="Medium.TButton")
        sd_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        # ARV绝对写实提示词按钮
        arv_prompt_btn = ttk.Button(prompt_options, text="ARV写实提示词", command=lambda: self._on_prompt_type_changed("ARV写实提示词"), style="Medium.TButton")
        arv_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)
        
        # 提示词类型状态显示
        prompt_status_frame = ttk.Frame(prompt_section)
        prompt_status_frame.pack(fill=tk.X, pady=3)
        ttk.Label(prompt_status_frame, text="当前选择:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        prompt_status_label = ttk.Label(prompt_status_frame, textvariable=self.prompt_type_var, font=('Microsoft YaHei', large_font_size, 'bold'))
        prompt_status_label.pack(side=tk.LEFT, padx=5)

        # 7. 主题自定义设置部分
        theme_section = ttk.LabelFrame(adv_frame, text="🎯 主题自定义", padding=15)
        theme_section.pack(fill=tk.X, pady=5)
        
        # 核心主题输入
        theme_frame = ttk.Frame(theme_section)
        theme_frame.pack(fill=tk.X, pady=3)
        ttk.Label(theme_frame, text="核心主题:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        theme_entry = ttk.Entry(theme_frame, textvariable=self.custom_theme_var, font=('Microsoft YaHei', large_font_size))
        theme_entry.pack(fill=tk.X, padx=5, pady=2)
        
        # 视觉基调输入
        tone_frame = ttk.Frame(theme_section)
        tone_frame.pack(fill=tk.X, pady=3)
        ttk.Label(tone_frame, text="视觉基调:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        tone_entry = ttk.Entry(tone_frame, textvariable=self.custom_visual_tone_var, font=('Microsoft YaHei', large_font_size))
        tone_entry.pack(fill=tk.X, padx=5, pady=2)
        
        # 应用按钮
        apply_frame = ttk.Frame(adv_frame)
        apply_frame.pack(fill=tk.X, pady=10)
        # 增大应用设置按钮的字体
        style = ttk.Style()
        style.configure("LargeGreen.TButton", font=('Microsoft YaHei', 14, 'bold'))
        btn_apply = ttk.Button(apply_frame, text="✅ 应用设置", command=self.apply_advanced_settings, style="LargeGreen.TButton")
        btn_apply.pack(fill=tk.X, padx=5, pady=8)

    def update_model_list(self):
        """更新模型列表，自动检测本地已安装的Ollama模型"""
        global OLLAMA_AVAILABLE
        
        # 模型信息字典：名称 -> (大小, 用途)
        model_info = {
            "qwen3:8b": ("5.2GB", "阿里通用模型，推荐首选"),
            "qwen2.5:7b": ("4.7GB", "阿里通用模型，性能优秀"),
            "gemma3:4b": ("3.3GB", "Google通用模型，推荐"),
            "qwen3:4b": ("2.5GB", "阿里通用模型"),
            "llama3.2:3b": ("2.0GB", "Meta轻量级模型"),
            "deepseek-r1:8b": ("5.2GB", "推理模型，不推荐提示词"),
            "gemma3:1b": ("815MB", "轻量级模型，速度快"),
        }
        
        def get_model_label(model_name):
            """获取模型显示标签（名称+大小+用途）"""
            for key, (size, desc) in model_info.items():
                if key in model_name:
                    return f"{model_name} | {size} | {desc}"
            return f"{model_name}"
        
        # 清空现有模型按钮
        for widget in self.model_dropdown_inner_frame.winfo_children():
            widget.destroy()
        
        # 已移除"本地大模型"选项，因为该功能已不再使用
        
        # 【修改】自动检测并启动Ollama服务
        ollama_connected = False
        try:
            response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_SHORT)
            if response.status_code == 200:
                OLLAMA_AVAILABLE = True
                ollama_connected = True
        except Exception:
            # Ollama未运行，尝试自动启动
            try:
                import subprocess
                import os
                ollama_path = None
                for path in [r"C:\Ollama\ollama.exe", r"C:\Program Files\Ollama\ollama.exe", 
                           os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                           "ollama"]:
                    if os.path.exists(path) or path == "ollama":
                        ollama_path = path
                        break
                if ollama_path:
                    subprocess.Popen([ollama_path, "serve"], 
                                   stdout=subprocess.DEVNULL, 
                                   stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    time.sleep(3)
                    # 再次尝试连接
                    try:
                        response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
                        if response.status_code == 200:
                            OLLAMA_AVAILABLE = True
                            ollama_connected = True
                    except Exception:
                        pass
            except Exception:
                pass
        
        # 尝试获取本地已安装的Ollama模型
        try:
            if OLLAMA_AVAILABLE or ollama_connected:
                models = ollama.list()
                # 尝试不同的键名来获取模型列表
                if "models" in models:
                    model_list = models["models"]
                    model_names = []
                    for model in model_list:
                        # 尝试不同的键名来获取模型名称
                        if "name" in model:
                            model_names.append(model["name"])
                        elif "model" in model:
                            model_names.append(model["model"])
                    
                    if model_names:
                        # 智能推荐模型
                        recommended_models = []
                        for model in model_names:
                            if any(keyword in model.lower() for keyword in ["qwen", "gemma", "deepseek", "llama", "mistral"]):
                                recommended_models.append((model, True))
                            else:
                                recommended_models.append((model, False))
                        
                        # 先显示推荐模型
                        for model, is_recommended in recommended_models:
                            # 添加模型任务标注
                            model_label = model
                            if "qwen2.5:7b" in model:
                                model_label = f"{model} (通用任务，推荐)"
                            elif "qwen2.5:3b" in model:
                                model_label = f"{model} (轻量级任务，速度优先)"
                            elif "qwen3:8b" in model:
                                model_label = f"{model} (通用任务，内容分析)"
                            elif "qwen3:4b" in model:
                                model_label = f"{model} (轻量级通用任务)"
                            elif "deepseek-r1:8b" in model:
                                model_label = f"{model} (推理任务，逻辑分析)"
                            elif "gemma3:4b" in model:
                                model_label = f"{model} (通用任务，提示词优化)"
                            elif "gemma3:1b" in model:
                                model_label = f"{model} (超轻量任务，极速响应)"
                            elif "mistral" in model:
                                model_label = f"{model} (通用任务，创意生成)"
                            elif "llama3" in model:
                                model_label = f"{model} (通用任务，长文本分析)"
                            
                            if is_recommended:
                                btn = ttk.Button(self.model_dropdown_inner_frame, text=f"{model_label} (推荐)", command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                            else:
                                btn = ttk.Button(self.model_dropdown_inner_frame, text=model_label, command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                            btn.pack(fill=tk.X, pady=1, padx=5)
                    else:
                        # 如果没有模型，显示默认模型
                        default_models = ["qwen2.5:7b", "gemma3:4b", "deepseek-r1:8b", "qwen2.5:3b", "gemma3:1b", "mistral", "llama3"]
                        for model in default_models:
                            # 添加模型任务标注
                            model_label = model
                            if "qwen2.5:7b" in model:
                                model_label = f"{model} (通用任务，推荐)"
                            elif "qwen2.5:3b" in model:
                                model_label = f"{model} (轻量级任务，速度优先)"
                            elif "gemma3:4b" in model:
                                model_label = f"{model} (通用任务，提示词优化)"
                            elif "gemma3:1b" in model:
                                model_label = f"{model} (超轻量任务，极速响应)"
                            elif "deepseek-r1:8b" in model:
                                model_label = f"{model} (推理任务，逻辑分析)"
                            elif "mistral" in model:
                                model_label = f"{model} (通用任务，创意生成)"
                            elif "llama3" in model:
                                model_label = f"{model} (通用任务，长文本分析)"
                            
                            if is_recommended:
                                btn = ttk.Button(self.model_dropdown_inner_frame, text=f"{model_label} (推荐)", command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                            else:
                                btn = ttk.Button(self.model_dropdown_inner_frame, text=model_label, command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                            btn.pack(fill=tk.X, pady=1, padx=5)
                else:
                    # 如果没有models键，显示默认模型
                    default_models = ["qwen2.5:7b", "gemma3:4b", "deepseek-r1:8b", "qwen2.5:3b", "gemma3:1b", "mistral", "llama3"]
                    for model in default_models:
                        # 添加模型任务标注
                        model_label = model
                        if "qwen2.5:7b" in model:
                            model_label = f"{model} (通用任务，推荐)"
                        elif "qwen2.5:3b" in model:
                            model_label = f"{model} (轻量级任务，速度优先)"
                        elif "gemma3:4b" in model:
                            model_label = f"{model} (通用任务，提示词优化)"
                        elif "gemma3:1b" in model:
                            model_label = f"{model} (超轻量任务，极速响应)"
                        elif "deepseek-r1:8b" in model:
                            model_label = f"{model} (推理任务，逻辑分析)"
                        elif "mistral" in model:
                            model_label = f"{model} (通用任务，创意生成)"
                        elif "llama3" in model:
                            model_label = f"{model} (通用任务，长文本分析)"
                        
                        btn = ttk.Button(self.model_dropdown_inner_frame, text=f"{model_label} (推荐)", command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                        btn.pack(fill=tk.X, pady=1, padx=5)
            else:
                # 如果Ollama不可用，显示默认模型
                default_models = ["qwen2.5:7b", "gemma3:4b", "deepseek-r1:8b", "qwen2.5:3b", "gemma3:1b", "mistral", "llama3"]
                for model in default_models:
                    # 添加模型任务标注
                    model_label = model
                    if "qwen2.5:7b" in model:
                        model_label = f"{model} (通用任务，推荐)"
                    elif "qwen2.5:3b" in model:
                        model_label = f"{model} (轻量级任务，速度优先)"
                    elif "gemma3:4b" in model:
                        model_label = f"{model} (通用任务，提示词优化)"
                    elif "gemma3:1b" in model:
                        model_label = f"{model} (超轻量任务，极速响应)"
                    elif "deepseek-r1:8b" in model:
                        model_label = f"{model} (推理任务，逻辑分析)"
                    elif "mistral" in model:
                        model_label = f"{model} (通用任务，创意生成)"
                    elif "llama3" in model:
                        model_label = f"{model} (通用任务，长文本分析)"
                    
                    btn = ttk.Button(self.model_dropdown_inner_frame, text=f"{model_label} (推荐)", command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                    btn.pack(fill=tk.X, pady=1, padx=5)
        except Exception as e:
            error_msg = str(e)
            status_code = getattr(e, 'code', None) or getattr(e, 'status', None) or '未知'
            self.log(f"获取Ollama模型列表失败: {error_msg} (status code: {status_code})")
            # 出错时显示默认模型
            default_models = ["qwen2.5:7b", "gemma3:4b", "deepseek-r1:8b", "qwen2.5:3b", "gemma3:1b", "mistral", "llama3"]
            for model in default_models:
                # 添加模型任务标注
                model_label = model
                if "qwen2.5:7b" in model:
                    model_label = f"{model} (通用任务，推荐)"
                elif "qwen2.5:3b" in model:
                    model_label = f"{model} (轻量级任务，速度优先)"
                elif "gemma3:4b" in model:
                    model_label = f"{model} (通用任务，提示词优化)"
                elif "gemma3:1b" in model:
                    model_label = f"{model} (超轻量任务，极速响应)"
                elif "deepseek-r1:8b" in model:
                    model_label = f"{model} (推理任务，逻辑分析)"
                elif "mistral" in model:
                    model_label = f"{model} (通用任务，创意生成)"
                elif "llama3" in model:
                    model_label = f"{model} (通用任务，长文本分析)"
                
                btn = ttk.Button(self.model_dropdown_inner_frame, text=f"{model_label} (推荐)", command=lambda m=model: self.select_ollama_model(m), style="Medium.TButton")
                btn.pack(fill=tk.X, pady=1, padx=5)

    def toggle_advanced_settings(self):
        """打开/关闭高级设置窗口"""
        if self.advanced_window and self.advanced_window.winfo_exists():
            try:
                self.save_config()
                self._print_current_settings()
            except Exception:
                pass
            self.advanced_window.destroy()
            self.advanced_window = None
        else:
            # 创建新的高级设置窗口
            self.advanced_window = tk.Toplevel(self.root)
            self.advanced_window.title("⚙️ 高级设置")
            self.advanced_window.geometry("700x650")
            self.advanced_window.resizable(True, True)
            
            # 绑定窗口关闭按钮（X）事件，关闭前自动保存
            self.advanced_window.protocol("WM_DELETE_WINDOW", self._on_advanced_window_close)
            
            # 创建高级设置面板
            adv_frame = ttk.Frame(self.advanced_window, padding=15)
            adv_frame.pack(fill=tk.BOTH, expand=True)
            
            # 调用设置内容的方法
            self.setup_advanced_panel_content(adv_frame)
    
    def _print_current_settings(self):
        """在命令提示框打印当前所有设置参数"""
        try:
            model = self.model_var.get() if hasattr(self, 'model_var') else '使用当前模型'
            width = self.width_var.get() if hasattr(self, 'width_var') else '768'
            height = self.height_var.get() if hasattr(self, 'height_var') else '512'
            api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else 'http://localhost:7860'
            ollama_model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b'
            llm_preset = self.llm_config_preset_var.get() if hasattr(self, 'llm_config_preset_var') else '质量优先'
            whisper_model = 'medium'
            animation = self.animation_var.get() if hasattr(self, 'animation_var') else '无'
            transition = self.transition_var.get() if hasattr(self, 'transition_var') else '硬切'
            thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16
            prompt_thread = self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
            prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else 'SD提示词'
            core_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ''
            visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ''
            
            styles = []
            if hasattr(self, 'dlr_vars'):
                for style_name, var in self.dlr_vars:
                    if var.get():
                        styles.append(style_name)
            
            print("")
            print("━" * 50)
            print("📋 当前高级设置参数确认")
            print("━" * 50)
            print(f"  SD模型:       {model}")
            print(f"  图片尺寸:     {width} x {height}")
            print(f"  SD API地址:   {api_url}")
            print(f"  Ollama模型:   {ollama_model}")
            print(f"  LLM配置:      {llm_preset}")
            print(f"  Whisper模型:  {whisper_model}")
            print(f"  提示词类型:   {prompt_type}")
            print(f"  动画效果:     {animation}")
            print(f"  过渡效果:     {transition}")
            print(f"  图像生成线程: {thread_count}")
            print(f"  提示词生成线程: {prompt_thread}")
            if core_theme:
                print(f"  核心主题:     {core_theme}")
            if visual_tone:
                print(f"  视觉基调:     {visual_tone}")
            if styles:
                print(f"  风格预设:     {', '.join(styles)}")
            print("━" * 50)
            print("")
        except Exception:
            pass

    def _on_advanced_window_close(self):
        """高级设置窗口关闭事件 - 自动保存配置并显示参数"""
        try:
            self.save_config()
            self._print_current_settings()
        except Exception:
            pass
        if self.advanced_window and self.advanced_window.winfo_exists():
            self.advanced_window.destroy()
        self.advanced_window = None
    
    def toggle_model_dropdown(self):
        """切换模型选择下拉菜单的显示/隐藏"""
        if self.model_dropdown_visible:
            self.model_dropdown_frame.pack_forget()
            self.model_dropdown_visible = False
        else:
            # 每次打开下拉菜单前，先更新模型列表
            self.update_model_list()
            # 重新创建Canvas内的窗口
            self.model_dropdown_canvas.create_window((0, 0), window=self.model_dropdown_inner_frame, anchor="nw")
            # 设置Canvas窗口宽度与Canvas一致
            self.model_dropdown_inner_frame.update_idletasks()
            self.model_dropdown_canvas.itemconfig(self.model_dropdown_canvas.find_withtag("all")[0] if self.model_dropdown_canvas.find_withtag("all") else None, width=self.model_dropdown_canvas.winfo_width())
            # 显示下拉框和滚动条
            self.model_dropdown_frame.pack(fill=tk.X, pady=2)
            self.model_dropdown_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.model_dropdown_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.model_dropdown_visible = True
    
    def select_ollama_model(self, model):
        """选择Ollama模型"""
        self.ollama_model_var.set(model)
        self.model_dropdown_canvas.pack_forget()
        self.model_dropdown_scrollbar.pack_forget()
        self.model_dropdown_frame.pack_forget()
        self.model_dropdown_visible = False
        self.log(f"✅ 已选择Ollama模型: {model}")
    
    def on_llm_config_changed(self, event=None):
        """大模型配置模式改变时的处理"""
        preset = self.llm_config_preset_var.get()
        if self.current_llm_config.apply_preset(preset):
            self.log(f"🎯 大模型配置已切换: {preset}")
            self.log(f"   参数: temperature={LLMConfig.PRESETS[preset].get('temperature')}, top_p={LLMConfig.PRESETS[preset].get('top_p')}")
            
            # 显示优化建议
            suggestions = llm_optimizer.suggest_optimization()
            for suggestion in suggestions:
                self.log(f"   💡 {suggestion}")
        else:
            self.log(f"⚠️ 未知配置模式: {preset}")
    
    
    def select_transition(self, transition):
        """选择视频过渡模式"""
        self.transition_var.set(transition)
        self.transition_dropdown_frame.pack_forget()
        self.transition_dropdown_visible = False
        self.log(f"✅ 已选择过渡模式: {transition}")
    
    def toggle_style_dropdown(self):
        """切换风格设置下拉菜单的显示/隐藏"""
        if self.style_dropdown_visible:
            self.style_dropdown_frame.pack_forget()
            self.style_dropdown_visible = False
        else:
            self.style_dropdown_frame.pack(fill=tk.X, pady=5)
            self.style_dropdown_visible = True
    
    def _on_prompt_type_changed(self, prompt_type):
        """提示词类型切换时联动控制风格设置"""
        self.prompt_type_var.set(prompt_type)
        
        is_sd = prompt_type == "SD提示词"
        
        if hasattr(self, 'style_grid') and self.style_grid:
            for child in self.style_grid.winfo_children():
                if isinstance(child, ttk.Checkbutton):
                    state = 'normal' if is_sd else 'disabled'
                    child.configure(state=state)
        
        if hasattr(self, 'style_control_frame') and self.style_control_frame:
            for child in self.style_control_frame.winfo_children():
                if isinstance(child, ttk.Button):
                    state = 'normal' if is_sd else 'disabled'
                    child.configure(state=state)
        
        if not is_sd and hasattr(self, 'style_dropdown_frame') and self.style_dropdown_visible:
            self.style_dropdown_frame.pack_forget()
            self.style_dropdown_visible = False
    
    def update_task_progress(self, message, progress=None):
        """更新任务进度"""
        def _update():
            try:
                if hasattr(self, 'lbl_progress'):
                    self.lbl_progress.config(text=message)
                if hasattr(self, 'progress_var') and progress is not None:
                    self.progress_var.set(progress)
            except Exception:
                pass
        
        if hasattr(self, 'root') and self.root:
            self.root.after(0, _update)
    
    
    
    def get_selected_styles(self):
        """获取用户选择的风格预设"""
        selected_styles = []
        if hasattr(self, 'dlr_vars'):
            for style, var in self.dlr_vars:
                if var.get():
                    selected_styles.append(style)
        return selected_styles
    
    def generate_style_description(self, style):
        """使用Ollama模型生成详细的风格描述"""
        # 检查Ollama模型设置
        model = self.ollama_model_var.get()
        
        # 检查缓存
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
            
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "user", "content": user_message}
                ]
            )
            
            raw_output = response["message"]["content"].strip()
            
            # 清洗输出，移除开场白和解释
            cleaned = self._clean_style_output(raw_output)
            
            # 缓存结果
            self.cache_set('prompts', cache_key, cleaned)
            
            return cleaned
        except Exception as e:
            self.log(f"⚠️ 风格描述生成失败: {e}")
            # 返回一个默认风格
            return "professional photography, high quality, detailed"
    
    def _clean_style_output(self, raw_output):
        """清洗风格描述输出，只保留关键词"""
        import re
        
        text = raw_output.strip()
        
        # 移除常见的开场白
        patterns_to_remove = [
            r'^好的[，,。:：]\s*',
            r'^Here\s*(is|are)\s*(a\s*)?(style\s*)?(description\s*)?[，,：:]*\s*',
            r'^Sure[，,。:：]?\s*',
            r'^Of course[，,。:：]?\s*',
            r'^风格描述[：:]\s*',
            r'^Style description[：:]\s*',
            r'^\*\*[^*]+\*\*[：:]\s*',  # **标题**：
            r'^【[^】]+】[：:]\s*',  # 【标题】：
        ]
        
        for pattern in patterns_to_remove:
            compiled = re.compile(pattern, re.IGNORECASE)
            text = compiled.sub('', text)

        # 移除Markdown格式
        text = RE_BOLD.sub(r'\1', text)
        text = RE_ITALIC.sub(r'\1', text)

        # 移除换行和多余空格
        text = RE_NEWLINES.sub(', ', text)
        text = RE_WHITESPACE.sub(' ', text)

        # 如果包含"核心概念"、"关键要素"等，提取冒号后的内容
        if '核心概念' in text or '关键要素' in text or 'Core concept' in text.lower():
            # 尝试提取描述部分
            match = RE_COLON_SPLIT.search(text)
            if match:
                text = match.group(1)

        # 截取前200字符，防止太长
        if len(text) > 200:
            # 在逗号处截断
            last_comma = text[:200].rfind(',')
            if last_comma > 50:
                text = text[:last_comma]

        # 清理首尾标点
        text = RE_LEADING_PUNCT.sub('', text)
        text = RE_TRAILING_PUNCT.sub('', text)
        
        return text.strip()

    def apply_advanced_settings(self):
        """应用高级设置"""
        # 收集所有设置内容
        model = self.model_var.get() if hasattr(self, 'model_var') else "使用当前模型"
        width = self.width_var.get() if hasattr(self, 'width_var') else "1920"
        height = self.height_var.get() if hasattr(self, 'height_var') else "1080"
        prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
        custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
        custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
        
        # 收集风格设置
        selected_styles = []
        if hasattr(self, 'dlr_vars'):
            for style, var in self.dlr_vars:
                if var.get():
                    selected_styles.append(style)

        # 构建确认信息
        confirm_msg = f"请确认以下设置:\n\n"
        confirm_msg += f"模型: {model}\n"
        confirm_msg += f"提示词类型: {prompt_type}\n"
        confirm_msg += f"图片尺寸: {width}x{height}\n"
        if custom_theme:
            confirm_msg += f"核心主题: {custom_theme}\n"
        if custom_tone:
            confirm_msg += f"视觉基调: {custom_tone}\n"
        if selected_styles:
            confirm_msg += f"风格预设: {', '.join(selected_styles)}\n"
        else:
            confirm_msg += "风格预设: 无\n"
        confirm_msg += f"SD API地址: {self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else 'http://127.0.0.1:7860'}\n"

        # 显示确认对话框
        confirmed = messagebox.askyesno("确认设置", confirm_msg)

        if confirmed:
            msg = f"设置已应用:\n模型: {model}\n提示词类型: {prompt_type}\n尺寸: {width}x{height}"
            if custom_theme:
                msg += f"\n核心主题: {custom_theme}"
            if custom_tone:
                msg += f"\n视觉基调: {custom_tone}"
            self.log(msg)
            self.save_config()
            self._print_current_settings()
            messagebox.showinfo("成功", "设置已成功应用！\n系统将按照您的选择执行相应功能。")
            self.toggle_advanced_settings()
        else:
            # 取消应用
            self.log("⚠️ 设置应用已取消")
    
    def check_sd_api_connection(self, silent=False):
        """连接 SD API - 在子线程中执行，避免阻塞UI
        
        Args:
            silent: True表示静默模式，不弹出错误对话框
        """
        # 如果是静默模式（启动时自动检查），在子线程中执行
        if silent:
            def check_in_thread():
                self._check_sd_api_impl(silent=True)
            threading.Thread(target=check_in_thread, daemon=True).start()
            return
        
        # 用户手动点击连接按钮，也在子线程中执行
        self.log("正在连接 SD API...")
        
        def check_in_thread():
            result = self._check_sd_api_impl(silent=False)
            # 在主线程中显示结果
            if hasattr(self, 'root') and self.root:
                self.root.after(0, lambda: self._show_sd_api_result(result))
        
        threading.Thread(target=check_in_thread, daemon=True).start()
    
    def _check_sd_api_impl(self, silent=False):
        """实际执行SD API连接检查（内部方法）"""
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL

        try:
            response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_MEDIUM)
            if response.status_code == 200:
                self.log("✅ SD API 连接成功！")
                
                # 更新状态变量（即使 label 还不存在也要更新，这样面板打开时能显示正确状态）
                if hasattr(self, 'sd_api_status_var'):
                    self.sd_api_status_var.set("✅ 已连接")
                
                # 更新 UI 显示（如果 label 已存在）
                if hasattr(self, 'sd_api_status_label'):
                    def update_ui():
                        if hasattr(self, 'sd_api_status_label'):
                            self.sd_api_status_label.config(foreground="green")
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
                
                # 更新模型下拉菜单
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, self._update_model_dropdown)
                
                return True
            else:
                self.log(f"❌ SD API 连接失败: 状态码 {response.status_code}")
                
                # 更新状态变量
                if hasattr(self, 'sd_api_status_var'):
                    self.sd_api_status_var.set("❌ 未连接")
                
                # 更新 UI 显示
                if hasattr(self, 'sd_api_status_label'):
                    def update_ui():
                        if hasattr(self, 'sd_api_status_label'):
                            self.sd_api_status_label.config(foreground="red")
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
                return False
        except Exception as e:
            self.log(f"❌ SD API 连接异常: {str(e)}")
            
            # 更新状态变量
            if hasattr(self, 'sd_api_status_var'):
                self.sd_api_status_var.set("❌ 未连接")
            
            # 更新 UI 显示
            if hasattr(self, 'sd_api_status_label'):
                def update_ui():
                    if hasattr(self, 'sd_api_status_label'):
                        self.sd_api_status_label.config(foreground="red")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            return False
    
    def _get_sd_models_from_api(self):
        """从 SD API 获取可用模型列表"""
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL

        try:
            response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_SHORT)
            if response.status_code == 200:
                models_data = response.json()
                # 提取模型名称（使用 title 或 model_name）
                model_names = []
                for model in models_data:
                    title = model.get('title', '')
                    model_name = model.get('model_name', '')
                    # 优先使用 title，因为更易读
                    if title:
                        # 去掉文件扩展名，使显示更简洁
                        display_name = title.replace('.safetensors', '').replace('.ckpt', '')
                        model_names.append(display_name)
                    elif model_name:
                        model_names.append(model_name)
                return model_names
        except Exception as e:
            pass  # 静默失败，使用默认列表
        return []
    
    def _async_update_sd_models(self):
        """异步获取并更新 SD 模型列表（不阻塞 UI）"""
        def _fetch_and_update():
            try:
                sd_models = self._get_sd_models_from_api()
                if sd_models and hasattr(self, 'model_combo'):
                    # 在主线程中更新 UI
                    def update_ui():
                        try:
                            models = ["使用当前模型"] + sd_models
                            self.model_combo['values'] = models
                        except Exception:
                            pass
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
            except Exception:
                pass  # 静默失败
        
        # 在后台线程中执行
        import threading
        thread = threading.Thread(target=_fetch_and_update, daemon=True)
        thread.start()
    
    def _update_model_dropdown(self):
        """更新模型下拉菜单（在 SD API 连接成功后调用）"""
        if not hasattr(self, 'model_combo'):
            return
        
        sd_models = self._get_sd_models_from_api()
        if sd_models:
            models = ["使用当前模型"] + sd_models
            self.model_combo['values'] = models
            # 如果当前选择的是旧的默认模型，重置为"使用当前模型"
            if self.model_var.get() in ["Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3", "DALL·E 3"]:
                self.model_var.set("使用当前模型")
    
    def _show_sd_api_result(self, result):
        """显示SD API连接结果（在主线程中调用）"""
        if not result:
            messagebox.showerror("错误", "SD API 连接失败，请检查Stable Diffusion是否已启动")
    
    def close_sd_api_connection(self):
        """关闭 SD API 连接"""
        self.log("正在关闭 SD API 连接...")
        
        # 更新连接状态
        if hasattr(self, 'sd_api_status_var') and hasattr(self, 'sd_api_status_label'):
            self.sd_api_status_var.set("❌ 未连接")
            self.sd_api_status_label.config(foreground="red")  # 断开态呈现红色
        
        # 清理可能的连接资源
        self.log("✅ SD API 连接已关闭")
    
    # =======================================================================
    # 第三部分：文本处理与内容分析 (行 3212-3413)
    # =======================================================================
    def clean_text(self, text):
        """简单清洗文本 - 去除多余空白字符"""
        if not text:
            return ""
        
        import re
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    
    def analyze_content_type(self, sentence):
        """分析内容类型 - 增强版，使用增强版内容识别模块"""
        # 优先使用增强版识别器
        if ENHANCED_RECOGNITION_AVAILABLE:
            try:
                recognizer = get_enhanced_recognizer()
                content_type, visual_style = recognizer.detect_content_type(sentence)
                return content_type
            except Exception as e:
                self.log(f"⚠️ 增强版识别失败，使用内置识别: {e}")
        
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
        """计算语义权重"""
        # 基于关键词、句子长度、内容类型等因素计算语义权重
        import re
        
        # 关键词权重
        keyword_weights = {
            "重要": 3.0, "关键": 3.0, "核心": 3.0,
            "新": 2.5, "创新": 2.5, "发现": 2.5,
            "首先": 2.0, "首次": 2.0, "唯一": 2.0,
            "因为": 1.5, "所以": 1.5, "但是": 1.5,
            "如果": 1.2, "假设": 1.2, "可能": 1.2,
            "必须": 2.0, "应该": 1.5, "需要": 1.5,
            "建议": 1.2, "推荐": 1.2, "注意": 1.5
        }
        
        weight = 1.0
        
        # 基于关键词计算权重
        for keyword, keyword_weight in keyword_weights.items():
            if keyword in sentence:
                weight += keyword_weight
        
        # 基于句子长度调整权重
        sentence_length = len(sentence)
        if sentence_length > 50:
            weight += 1.0
        elif sentence_length > 30:
            weight += 0.5
        elif sentence_length < 10:
            weight -= 0.5
        
        # 基于标点符号调整权重
        if "。" in sentence or "！" in sentence or "？" in sentence:
            weight += 0.5
        if "，" in sentence:
            weight += 0.2
        
        # 基于内容类型调整权重
        content_type = self.analyze_content_type(sentence)
        content_weight = {
            "space": 1.2,
            "science": 1.1,
            "technology": 1.1,
            "history": 1.0,
            "nature": 1.0,
            "health": 1.0,
            "business": 0.9,
            "education": 0.9,
            "art": 0.8,
            "travel": 0.8,
            "general": 0.7
        }
        weight *= content_weight.get(content_type, 0.7)
        
        return min(weight, 5.0)  # 权重上限为5.0


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
            import ollama
            model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else "gemma3:4b"
            
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
4. 每个分镜时长建议3-10秒
5. 只能合并相邻片段，不能拆分或重排
6. 同时纠正明显的语音识别错误（如同音字、人名错字）

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
            
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            raw_output = response["message"]["content"].strip()
            
            import re
            import json
            
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
            
            self.log(f"   ✅ 大模型语义划分: {len(segments)} → {len(merged)} 个分镜")
            return merged
            
        except Exception as e:
            self.log(f"   ⚠️ 大模型语义划分失败({str(e)[:60]})，回退到规则合并")
            return self._rule_based_merge(segments)
    
    def _rule_based_merge(self, segments):
        """规则合并：大模型不可用时的回退方案
        
        策略：
        1. 过短的片段（< 3秒）与相邻片段合并
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
            
            if duration < 3.0:
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

    def _extract_shot_theme_elements(self, shot_text, global_elements):
        """从分镜文案中提取相关的主题元素
        
        策略：
        1. 精确匹配：元素直接出现在分镜文案中
        2. 关键词关联匹配：通过语义关联词映射
        3. 兜底：如果无匹配，返回全局元素（作为LLM参考）
        """
        if not global_elements or not shot_text:
            return global_elements[:6] if global_elements else []

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
            return global_elements[:6]

        return matched_elements[:6]

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
        import re
        cleaned_sentence = re.sub(r'[\s\n\r]+', ' ', sentence).strip()
        
        # 清洗和修正文本，修正错别字和语句不通顺的地方
        cleaned_sentence = self.clean_text(cleaned_sentence)
        
        # 从description中提取画面构思（如果包含）
        # description格式：配音内容 + 画面构思 + 视觉元素
        description_parts = self._parse_description(cleaned_sentence)
        
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
        
        # 简化处理：直接使用生成的提示词，跳过额外的优化和质量评估
        # 已由大模型生成
        prompt_quality = 0.0
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

        shot_data["negative_prompt"] = self._get_custom_negative_prompt(content_type, description_parts['dubbing'])
        
        return shot_data
    
    def _parse_description(self, description):
        """解析description，提取各个部分 - 增强版支持多种格式"""
        import re
        
        result = {
            'dubbing': '',
            'semantic': '',
            'visual_concept': '',
            'visual_elements': '',
            'style': ''
        }
        
        # 清理元数据标记
        cleaned = re.sub(r'\*+', '', description)
        cleaned = re.sub(r'^\s*-\s*', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'[""""]', '', cleaned)  # 移除引号
        cleaned = cleaned.strip()
        
        # 尝试提取各个部分
        lines = [l.strip() for l in cleaned.split('\n') if l.strip()]
        
        if lines:
            # 第一行通常是配音内容
            first_line = lines[0]
            # 如果包含冒号或特定标记，提取后面的内容
            if '：' in first_line or ':' in first_line:
                result['dubbing'] = re.sub(r'.*?[:：]\s*', '', first_line)
            else:
                result['dubbing'] = first_line
        
        # 查找画面构思（支持多种关键词）
        for line in lines:
            if any(keyword in line for keyword in ['画面构思', '镜头', '展示', '场景', '画面']):
                result['visual_concept'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        # 查找视觉元素
        for line in lines:
            if any(keyword in line for keyword in ['视觉元素', '元素', '物体', '主体']):
                result['visual_elements'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        # 查找风格
        for line in lines:
            if any(keyword in line for keyword in ['风格', '纪实', '摄影', '色调']):
                result['style'] = re.sub(r'.*?[:：]\s*', '', line)
                break
        
        # 如果没有提取到visual_concept，尝试从dubbing智能推断
        if not result['visual_concept'] and result['dubbing']:
            result['visual_concept'] = self._infer_visual_concept_from_dubbing(result['dubbing'])
        
        # 如果没有提取到visual_elements，尝试从dubbing智能推断
        if not result['visual_elements'] and result['dubbing']:
            result['visual_elements'] = self._infer_visual_elements_from_dubbing(result['dubbing'])
        
        # 如果没有提取到，使用整个description作为dubbing
        if not result['dubbing']:
            result['dubbing'] = cleaned[:200]
        
        return result
    
    # =======================================================================
    # 第五部分：提示词生成 (行 3809-4397)
    # 包含：ARV提示词、SD提示词、LLM提示词
    # =======================================================================
    def _infer_visual_concept_from_dubbing(self, dubbing):
        """使用大模型从配音内容智能推断画面构思"""
        if not dubbing or len(dubbing.strip()) < 2:
            return ""
        
        # 检查是否配置了 Ollama
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            return ""
        
        try:
            model = self.ollama_model_var.get()
            ollama_url = "http://localhost:11434"
            
            prompt = f"""根据以下配音文本，构思一个适合的图像画面场景。
要求：
1. 描述一个具体的画面场景，包含主要视觉元素
2. 用英文描述
3. 只返回画面描述，不要其他解释

配音文本：{dubbing}

返回格式：a detailed visual scene description"""
            
            config_options = self.current_llm_config.get_options() if hasattr(self, 'current_llm_config') else {"temperature": 0.3}
            response = get_http_session().post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": config_options
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                visual_concept = result.get('response', '').strip()
                if visual_concept:
                    return visual_concept
            
            return ""
        except Exception as e:
            return ""
    
    def _infer_visual_elements_from_dubbing(self, dubbing):
        """使用大模型从配音内容智能推断视觉元素"""
        if not dubbing or len(dubbing.strip()) < 2:
            return ""
        
        # 检查是否配置了 Ollama
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            return ""
        
        try:
            model = self.ollama_model_var.get()
            ollama_url = "http://localhost:11434"
            
            prompt = f"""从以下配音文本中提取所有能够用于图像生成的视觉元素关键词。
要求：
1. 提取具体的人、物、场景、动作等视觉元素
2. 用英文逗号分隔每个关键词
3. 只返回关键词列表，不要其他解释

配音文本：{dubbing}

返回格式：keyword1, keyword2, keyword3"""
            
            config_options = self.current_llm_config.get_options() if hasattr(self, 'current_llm_config') else {"temperature": 0.3}
            response = get_http_session().post(
                f"{ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": config_options
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                visual_elements = result.get('response', '').strip()
                if visual_elements:
                    return visual_elements
            
            return ""
        except Exception as e:
            return ""
    
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
            self.log(f"⚠️ ARV提示词生成失败: {e}，切换到SD提示词")
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
            self.log(f"⚠️ ARV格式生成失败: {e}")
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
        
        Args:
            raw_output: 大模型返回的原始输出
            
        Returns:
            清洗后的纯净提示词
        """
        if not raw_output:
            return ""
        
        import re
        
        # 转为字符串
        text = str(raw_output).strip()
        
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
            # 英文开场白和解释性文字
            r'^Here[\'\'\']?s a prompt[^.]*\.\s*',
            r'^Here is a prompt[^.]*\.\s*',
            r'^Based on[^.]*[,，]\s*',
            r'^The following is[^.]*\.\s*',
            r'^I[\'\'\']?ll generate[^.]*\.\s*',
            r'^Let me[^.]*\.\s*',
            r'^Sure[，,.]?\s*',
            r'^Of course[，,.]?\s*',
            r'^Certainly[，,.]?\s*',
            
            # 中文开场白和解释性文字
            r'^以下[是为][^。！？]*[。！？]?\s*',
            r'^好的[，,。！？]?\s*[^。！？]*[。！？]?\s*',
            r'^请看[^。！？]*[。！？]?\s*',
            r'^根据[^。！？]*[。！？]?\s*',
            r'^基于[^。！？]*[。！？]?\s*',
            
            # 提示词标记
            r'\*{0,2}提示词\*{0,2}[：:]\s*',
            r'【提示词】[：:]?\s*',
            r'提示词[：:]\s*',
            
            # 补充说明
            r'\n?\*{0,2}补充说明\*{0,2}[：:].*',
            r'\n?【补充说明】[：:].*',
            r'\n?补充说明[：:].*',
            
            # 解释说明
            r'\n?\*{0,2}解释说明\*{0,2}[：:].*',
            r'\n?【解释说明】[：:].*',
            r'\n?解释说明[：:].*',
            
            # 更详细的补充
            r'\n?\*{0,2}更[详细进]*[^。！？]*[。！？]\*{0,2}[：:].*',
            
            # 备选提示词
            r'\n?\*{0,2}备选提示词\*{0,2}[：:].*',
            
            # 附加说明
            r'\n?\*{0,2}附加说明\*{0,2}[：:].*',
            r'\n?【附加说明】[：:].*',
            
            # 结束语和问候
            r'\n?希望[^\n]*[！！。]',
            r'\n?以上[^\n]*[！！。]',
            r'\n?请[^\n]*[！！。]',
            r'\n?感谢[^\n]*[！！。]',
            r'\n?如果[您你][^\n]*[！！。]',
            
            # Markdown格式
            r'\*{2}([^*]+)\*{2}',  # 加粗
            r'\*([^*]+)\*',        # 斜体
            r'#{1,6}\s*',          # 标题
            
            # 场景/元素/风格标签（中文格式）
            r'\n?【?场景】?[：:][^。\n]*[。\n]?',
            r'\n?【?元素】?[：:][^。\n]*[。\n]?',
            r'\n?【?风格】?[：:][^。\n]*[。\n]?',
            r'\n?【?氛围】?[：:][^。\n]*[。\n]?',
            r'\n?【?主体】?[：:][^。\n]*[。\n]?',
            r'\n?【?细节】?[：:][^。\n]*[。\n]?',
            
            # 为什么选择这些提示词等解释
            r'\n?为什么[^\n]*',
            r'\n?进一步[^\n]*',
        ]
        
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
        if re.search(r'[场情元素风格氛围][:：]', text):
            # 尝试提取关键词组合
            parts = []
            for label in ['场景', '元素', '风格', '氛围', '主体', '细节']:
                match = re.search(f'{label}[：:]\\s*([^场元素风格氛围主体细节\\n]+)', text)
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
        
        # 如果结果太短（可能是清洗过度），返回原始输出
        if len(text.strip()) < 10:
            return raw_output.strip()
        
        # 确保提示词包含必需的结尾标签
        text = self._ensure_required_tags(text)
        
        return text.strip()
    
    def _ensure_required_tags(self, prompt_text):
        """确保提示词包含必需的结尾标签 - SD/ARV提示词统一使用英文标签"""
        required_tags = ["cinematic lighting", "documentary style", "film grain texture"]
        
        prompt_lower = prompt_text.lower()
        
        missing_tags = [tag for tag in required_tags if tag.lower() not in prompt_lower]
        
        if missing_tags:
            prompt_text = prompt_text.rstrip(',; ') + ", " + ", ".join(missing_tags)
        
        return prompt_text

    def _generate_prompt_with_llm(self, dubbing, content_type, prompt_type="SD提示词", core_theme="", visual_tone="", theme_elements=None, visual_style="", original_dubbing="", full_text=""):
        """使用大模型生成提示词 - 只给规则不给案例，让大模型自主创作"""
        if theme_elements is None:
            theme_elements = []
        
        if not OLLAMA_AVAILABLE:
            self.log("⚠️ Ollama不可用，使用内置逻辑生成提示词")
            if prompt_type == "ARV写实提示词" and ARV_OPTIMIZATION_AVAILABLE:
                return self._generate_arv_format_prompt(dubbing, content_type, 0)
            elif prompt_type == "SD提示词" and ARV_PROMPTS_AVAILABLE:
                return ARVPromptTemplates.generate_prompt(dubbing, content_type, core_theme, visual_tone)
            else:
                return self._analyze_and_generate_sd_prompt(dubbing, content_type)
            
        model = self.ollama_model_var.get()
        
        template_params = {
            "content_type": content_type or "未指定类型",
            "core_theme": core_theme or "未指定",
            "visual_style": visual_style,
            "visual_tone": visual_tone or "",
            "theme_elements": ", ".join(theme_elements) if theme_elements else "根据配音内容确定",
            "dubbing": dubbing
        }
        
        if prompt_type == "SD提示词":
            # 为SD提示词添加上下文信息
            context_hint = ""
            if hasattr(self, '_shot_texts_for_context') and isinstance(dubbing, str):
                shot_texts = self._shot_texts_for_context
                try:
                    idx = shot_texts.index(dubbing) if dubbing in shot_texts else -1
                    if idx >= 0:
                        # 添加全局内容摘要（帮助理解整体主题）
                        if full_text and len(full_text) > 50:
                            # 截取前200字符作为内容摘要
                            content_summary = full_text[:200] + "..." if len(full_text) > 200 else full_text
                            context_hint += f"整体内容摘要: {content_summary}\n"
                        
                        # 添加前文上下文（最近的2-3个片段）
                        prev_texts = [shot_texts[j] for j in range(max(0, idx-3), idx)]
                        if prev_texts:
                            context_hint += f"前文上下文: {' | '.join(prev_texts)}\n"
                        
                        # 添加后文上下文（接下来的2-3个片段）
                        next_texts = [shot_texts[j] for j in range(idx+1, min(len(shot_texts), idx+4))]
                        if next_texts:
                            context_hint += f"后文上下文: {' | '.join(next_texts)}\n"
                        
                        # 添加全局位置信息
                        total_shots = len(shot_texts)
                        position_info = f"这是第{idx+1}个分镜，共{total_shots}个分镜"
                        if idx == 0:
                            position_info += "（开头）"
                        elif idx == total_shots - 1:
                            position_info += "（结尾）"
                        elif idx < total_shots // 3:
                            position_info += "（前段）"
                        elif idx > (total_shots * 2) // 3:
                            position_info += "（后段）"
                        else:
                            position_info += "（中段）"
                        context_hint += f"位置信息: {position_info}\n"
                except Exception:
                    pass
            
            # 更新模板参数，包含上下文
            template_params["context_hint"] = context_hint
            template = PromptTemplates.get_template("shot_prompt_sd", **template_params)
        elif prompt_type == "ARV写实提示词":
            context_hint = ""
            if hasattr(self, '_shot_texts_for_context') and isinstance(dubbing, str):
                shot_texts = self._shot_texts_for_context
                try:
                    idx = shot_texts.index(dubbing) if dubbing in shot_texts else -1
                    if idx >= 0:
                        prev_texts = [shot_texts[j] for j in range(max(0, idx-2), idx)]
                        next_texts = [shot_texts[j] for j in range(idx+1, min(len(shot_texts), idx+3))]
                        if prev_texts:
                            context_hint += f"前文: {' | '.join(prev_texts)}\n"
                        if next_texts:
                            context_hint += f"后文: {' | '.join(next_texts)}\n"
                except Exception:
                    pass

            template = {
                "system": f"""You are a prompt engineer for absoluteRealisticVision v20 SD model.

【格式规则】
- Start with: (masterpiece, best quality:1.2), RAW photo, (photorealistic:1.3), ultra detailed, 8k
- Output ONLY English keywords, comma-separated, NO sentences, NO Chinese characters
- Describe photographable scenes, NOT abstract concepts
- Use weight syntax for key subjects: (subject:1.3) primary, (subject:1.2) secondary
- End with: cinematic lighting, documentary style, (film grain:1.1)
- NO explanations, NO quotes, NO newlines

【核心规则】
- Prompt MUST accurately reflect the specific content of the dubbing text
- Each shot has different dubbing, each prompt MUST be unique and visually distinct
- Global theme is background reference only, do NOT stuff it into every shot
- Describe the specific scene that matches the current dubbing

【反重复规则 - 极其重要】
- FORBIDDEN to use the same scene setup in every shot
- FORBIDDEN to always use: office, boardroom, mahogany desk, cityscape background
- MUST vary: location, composition, lighting, camera angle, subject matter
- If dubbing mentions a person → show that person in a SPECIFIC situation (not just standing in office)
- If dubbing mentions debt/crisis → show dramatic visual metaphor (falling graph, broken building, not just office)
- If dubbing mentions success/safety → show achievement scene (handshake, celebration, not just office)
- If dubbing mentions legal issues → show courtroom, police, handcuffs, gavel (not just office)
- If dubbing mentions specific industry → show THAT industry's visuals (construction site, tech lab, farmland)

【内容类型】：{content_type}
【全局主题（仅参考）】：{core_theme or '根据配音内容确定'}
【视觉基调】：{visual_tone or '根据内容确定'}

只输出英文提示词，不要解释。""",
                "user": f"""{context_hint}当前配音: {dubbing}

根据当前配音的具体内容生成英文提示词（必须与之前的场景不同）："""
            }
        else:
            template = PromptTemplates.get_template("shot_prompt_sd", **template_params)
        
        try:
            import ollama
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": template["system"]},
                    {"role": "user", "content": template["user"]}
                ]
            )
            
            raw_output = response["message"]["content"].strip()
            if raw_output:
                cleaned_prompt = self._clean_prompt_output(raw_output)
                return cleaned_prompt
            
            raise Exception("大模型返回为空")
        except ImportError:
            self.log("⚠️ ollama模块导入失败，回退到内置逻辑")
            return self._analyze_and_generate_sd_prompt(dubbing, content_type)
        except Exception as e:
            self.log(f"⚠️ 大模型调用失败: {str(e)[:80]}，回退到内置逻辑")
            return self._analyze_and_generate_sd_prompt(dubbing, content_type)
    
    def _get_custom_negative_prompt(self, content_type, dubbing):
        """根据内容类型和配音内容生成定制化负面提示词 - 适配ARV写实模型"""
        base_negative = [
            "(worst quality:1.2)", "(low quality:1.2)", "cartoon", "anime", "painting",
            "illustration", "3d render", "sketch", "(ugly:1.3)", "(deformed:1.3)",
            "blurry", "disfigured", "(bad anatomy:1.2)", "extra limbs", "mutated hands",
            "(bad hands:1.2)", "missing fingers", "extra digits", "cropped", "watermark",
            "text", "signature", "username", "jpeg artifacts", "duplicate", "morbid"
        ]

        content_specific_negative = {
            "space": [
                "human", "person", "face", "building", "tree",
                "landscape", "daytime", "sun"
            ],
            "science": [
                "cartoon character", "fictional creature", "fantasy", "magic"
            ],
            "nature": [
                "urban", "building", "structure", "artificial", "concrete"
            ],
            "history": [
                "modern", "contemporary", "anachronism", "smartphone", "computer"
            ]
        }

        additional_negative = []

        if any(kw in dubbing for kw in ["黑洞", "宇宙", "银河", "恒星", "星云"]):
            additional_negative.extend([
                "star", "sun", "planet", "moon", "satellite",
                "human", "person", "face", "building", "tree"
            ])

        if any(kw in dubbing for kw in ["政治", "历史", "古代", "战争"]):
            additional_negative.extend([
                "modern", "contemporary", "anachronism"
            ])

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
                self.log(f"⚠️ 增强版实体识别失败，使用内置识别: {e}")
        
        # 回退到内置识别逻辑
        # 国家/地区实体 - 扩展版本，包含更多国家和常见误识别纠正
        country_mapping = {
            '伊朗': 'Iran, Iranian', '美国': 'USA, American', '美國': 'USA, American', '中国': 'China, Chinese', '中國': 'China, Chinese',
            '俄罗斯': 'Russia, Russian', '俄羅斯': 'Russia, Russian', '以色列': 'Israel, Israeli', '日本': 'Japan, Japanese',
            '英国': 'UK, British', '英國': 'UK, British', '法国': 'France, French', '法國': 'France, French', '德国': 'Germany, German', '德國': 'Germany, German',
            '朝鲜': 'North Korea, Korean', '朝鮮': 'North Korea, Korean', '北韩': 'North Korea, Korean', '北韓': 'North Korea, Korean',
            '韩国': 'South Korea, Korean', '韓國': 'South Korea, Korean', '南韩': 'South Korea, Korean', '南韓': 'South Korea, Korean',
            '乌克兰': 'Ukraine, Ukrainian', '烏克蘭': 'Ukraine, Ukrainian', '欧洲': 'Europe, European', '歐洲': 'Europe, European',
            '中东': 'Middle East', '中東': 'Middle East', '亚洲': 'Asia, Asian', '亞洲': 'Asia, Asian',
            # 新增：非洲国家（修复"厄立特里亚"被误识别的问题）
            '厄立特里亚': 'Eritrea, Eritrean', '厄利垂亞': 'Eritrea, Eritrean', '俄利特里亞': 'Eritrea, Eritrean',
            '埃塞俄比亚': 'Ethiopia, Ethiopian', '埃塞俄比亞': 'Ethiopia, Ethiopian', '衣索比亞': 'Ethiopia, Ethiopian',
            '索马里': 'Somalia, Somali', '索馬里': 'Somalia, Somali',
            '苏丹': 'Sudan, Sudanese', '蘇丹': 'Sudan, Sudanese',
            '南非': 'South Africa, South African',
            '埃及': 'Egypt, Egyptian',
        }
        
        # 军事/安全机构实体
        military_mapping = {
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
        
        # 政治/组织实体
        political_mapping = {
            '政府': 'government, officials', '总统': 'president, head of state', '總統': 'president, head of state',
            '总理': 'prime minister', '總理': 'prime minister', '首相': 'prime minister',
            '外交部': 'foreign ministry, diplomatic', '联合国': 'United Nations, UN', '聯合國': 'United Nations, UN',
            '安理会': 'UN Security Council', '安理會': 'UN Security Council', '北约': 'NATO, NATO alliance', '北約': 'NATO, NATO alliance',
            '欧盟': 'European Union, EU', '歐盟': 'European Union, EU', '国会': 'congress, parliament', '國會': 'congress, parliament',
            '议会': 'parliament, legislative', '議會': 'parliament, legislative', '政党': 'political party', '政黨': 'political party',
            '官员': 'officials, authorities', '官員': 'officials, authorities', '发言人': 'spokesperson, official spokesperson', '發言人': 'spokesperson, official spokesperson',
        }
        
        # 事件/行动实体
        event_mapping = {
            '战争': 'war, warfare, conflict', '戰爭': 'war, warfare, conflict', '冲突': 'conflict, clash', '衝突': 'conflict, clash',
            '战斗': 'battle, combat, fighting', '戰鬥': 'battle, combat, fighting', '袭击': 'attack, strike, assault', '襲擊': 'attack, strike, assault',
            '爆炸': 'explosion, blast', '发射': 'launch', '發射': 'launch',
            '试射': 'test, missile test', '試射': 'test, missile test', '军演': 'military exercise, drill', '軍演': 'military exercise, drill',
            '谈判': 'negotiation, talks', '談判': 'negotiation, talks', '会议': 'meeting, conference', '會議': 'meeting, conference',
            '声明': 'statement, announcement', '聲明': 'statement, announcement', '宣布': 'announcement, declare',
            '签署': 'signing, agreement', '簽署': 'signing, agreement', '协议': 'agreement, deal, pact', '協議': 'agreement, deal, pact',
            '制裁': 'sanctions, embargo', '援助': 'aid, assistance',
        }
        
        # 地点/场景实体
        location_mapping = {
            '基地': 'base, military base', '机场': 'airport, air base', '機場': 'airport, air base',
            '港口': 'port, harbor, naval base', '城市': 'city, urban',
            '农村': 'rural, countryside', '農村': 'rural, countryside', '山区': 'mountain, mountainous', '山區': 'mountain, mountainous',
            '沙漠': 'desert', '海边': 'coastal, seaside', '海邊': 'coastal, seaside',
            '海峡': 'strait, waterway', '海峽': 'strait, waterway', '油田': 'oil field, oil facility',
            '核设施': 'nuclear facility', '核設施': 'nuclear facility', '工厂': 'factory, facility', '工廠': 'factory, facility',
            '大使馆': 'embassy', '大使館': 'embassy', '领事馆': 'consulate', '領事館': 'consulate',
        }
        
        # 新闻/媒体相关
        media_mapping = {
            '新闻': 'news, news report, breaking news', '新聞': 'news, news report, breaking news', '记者': 'journalist, reporter', '記者': 'journalist, reporter',
            '主持人': 'anchor, presenter', '直播': 'live broadcast, livestream',
            '报道': 'report, coverage', '報道': 'report, coverage', '采访': 'interview', '採訪': 'interview',
            '发布会': 'press conference', '發布會': 'press conference', '声明': 'official statement', '聲明': 'official statement',
        }
        
        # 通用开场/过渡词（需要结合主题）
        generic_keywords = {
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
        
        # 按优先级匹配：军事 > 政治 > 事件 > 地点 > 国家 > 通用开场
        all_mappings = [
            (military_mapping, 'military'),
            (political_mapping, 'political'),
            (event_mapping, 'event'),
            (location_mapping, 'location'),
            (country_mapping, 'country'),
            (media_mapping, 'media'),
            (generic_keywords, 'generic'),
        ]
        
        for mapping, mtype in all_mappings:
            for cn_key, en_value in mapping.items():
                if cn_key in dubbing_clean:
                    entities.append(en_value)
                    break
        
        # 内容类型补充
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
        """简单的中文到英文翻译"""
        import re
        
        # 常见词汇映射 - 扩展版本
        mapping = {
            # 人物（简体+繁体）
            '人': 'person', '男人': 'man', '女人': 'woman', '老人': 'elderly person',
            '小孩': 'child', '年轻人': 'young person', '学生': 'student', '医生': 'doctor',
            '护士': 'nurse', '警察': 'police officer', '军人': 'soldier', '教师': 'teacher',
            '记者': 'journalist', '商人': 'businessman', '科学家': 'scientist',
            '工程师': 'engineer', '运动员': 'athlete', '演员': 'actor', '歌手': 'singer',
            '总统': 'president', '总理': 'prime minister', '部长': 'minister',
            '司令': 'commander', '长官': 'officer', '領導人': 'leader',
            '人': 'people', '人群': 'crowd', '群众': 'people',
            # 繁体人物
            '總統': 'president', '總理': 'prime minister', '部長': 'minister',
            '司令': 'commander', '長官': 'officer', '領導人': 'leader', '人': 'people',
            '人群': 'crowd', '群眾': 'people', '男人': 'man', '女人': 'woman',
            '老人': 'elderly person', '小孩': 'child', '年輕人': 'young person',
            '學生': 'student', '醫生': 'doctor', '護士': 'nurse', '警察': 'police officer',
            '軍人': 'soldier', '教師': 'teacher', '記者': 'journalist', '商人': 'businessman',
            '科學家': 'scientist', '工程師': 'engineer', '運動員': 'athlete',
            '演員': 'actor', '歌手': 'singer',
            # 地点（简体+繁体）
            '城市': 'city', '城镇': 'town', '农村': 'countryside', '乡村': 'village',
            '街道': 'street', '道路': 'road', '商场': 'shopping mall', '餐厅': 'restaurant',
            '医院': 'hospital', '学校': 'school', '工厂': 'factory', '办公室': 'office',
            '图书馆': 'library', '公园': 'park', '海滩': 'beach', '山': 'mountain',
            '河': 'river', '湖': 'lake', '海': 'sea', '森林': 'forest',
            '草原': 'grassland', '沙漠': 'desert', '房间': 'room', '楼': 'building',
            '机场': 'airport', '车站': 'station', '码头': 'dock',
            # 繁体地点
            '城市': 'city', '城鎮': 'town', '農村': 'countryside', '鄉村': 'village',
            '街道': 'street', '道路': 'road', '商場': 'shopping mall', '餐廳': 'restaurant',
            '醫院': 'hospital', '學校': 'school', '工廠': 'factory', '辦公室': 'office',
            '圖書館': 'library', '公園': 'park', '海灘': 'beach', '山': 'mountain',
            '河': 'river', '湖': 'lake', '海': 'sea', '森林': 'forest',
            '草原': 'grassland', '沙漠': 'desert', '房間': 'room', '樓': 'building',
            '機場': 'airport', '車站': 'station', '碼頭': 'dock',
            # 国家/地区
            '伊朗': 'Iran', '美国': 'United States', '中国': 'China', '俄罗斯': 'Russia',
            '欧洲': 'Europe', '亚洲': 'Asia', '中东': 'Middle East',
            '伊朗': 'Iran', '美國': 'United States', '中國': 'China', '俄羅斯': 'Russia',
            '歐洲': 'Europe', '亞洲': 'Asia', '中東': 'Middle East',
            # 交通工具
            '车': 'car', '汽车': 'car', '火车': 'train', '飞机': 'airplane', '船': 'ship',
            '車': 'car', '汽車': 'car', '火車': 'train', '飛機': 'airplane', '船': 'ship',
            # 物品
            '手机': 'mobile phone', '电脑': 'computer', '电视': 'television',
            '书': 'book', '文件': 'document', '照片': 'photo', '图片': 'image',
            '手機': 'mobile phone', '電腦': 'computer', '電視': 'television',
            '書': 'book', '文件': 'document', '照片': 'photo', '圖片': 'image',
            # 动作
            '走': 'walking', '跑': 'running', '跳': 'jumping', '飞': 'flying',
            '坐': 'sitting', '躺': 'lying', '站': 'standing', '看': 'looking',
            '听': 'listening', '说': 'speaking', '笑': 'smiling', '哭': 'crying',
            '唱': 'singing', '跳舞': 'dancing', '吃': 'eating', '喝': 'drinking',
            '工作': 'working', '学习': 'studying', '开车': 'driving',
            '打电话': 'making phone call', '拍照': 'taking photo',
            '采访': 'interviewing', '演讲': 'giving speech', '表演': 'performing',
            '比赛': 'competing', '战斗': 'fighting', '战争': 'war',
            # 繁体动作
            '走': 'walking', '跑': 'running', '跳': 'jumping', '飛': 'flying',
            '坐': 'sitting', '躺': 'lying', '站': 'standing', '看': 'looking',
            '聽': 'listening', '說': 'speaking', '笑': 'smiling', '哭': 'crying',
            '唱': 'singing', '跳舞': 'dancing', '吃': 'eating', '喝': 'drinking',
            '工作': 'working', '學習': 'studying', '開車': 'driving',
            '打電話': 'making phone call', '拍照': 'taking photo',
            '採訪': 'interviewing', '演講': 'giving speech', '表演': 'performing',
            '比賽': 'competing', '戰鬥': 'fighting', '戰爭': 'war',
            # 时间
            '白天': 'daytime', '夜晚': 'night', '早晨': 'morning', '黄昏': 'dusk',
            '白天': 'daytime', '夜晚': 'night', '早晨': 'morning', '黃昏': 'dusk',
            # 天气
            '晴天': 'sunny', '雨天': 'rainy', '雪天': 'snowy', '阴天': 'cloudy',
            '晴天': 'sunny', '雨天': 'rainy', '雪天': 'snowy', '陰天': 'cloudy',
            # 氛围/情感
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
            # 战争/军事相关
            '战争': 'war', '战斗': 'battle', '军队': 'army', '导弹': 'missile',
            '武器': 'weapon', '坦克': 'tank', '飞机': 'aircraft', '军舰': 'warship',
            '戰爭': 'war', '戰鬥': 'battle', '軍隊': 'army', '導彈': 'missile',
            '武器': 'weapon', '坦克': 'tank', '飛機': 'aircraft', '軍艦': 'warship',
            # 其他常见词
            '火': 'fire', '炸弹': 'bomb', '定时炸弹': 'time bomb',
            '地缘': 'geopolitical', '棋盘': 'chessboard',
            '投降': 'surrender', '谈判': 'negotiation',
            '火': 'fire', '炸彈': 'bomb', '定時炸彈': 'time bomb',
            '地緣': 'geopolitical', '棋盤': 'chessboard',
            '投降': 'surrender', '談判': 'negotiation',
        }
        
        # 精确匹配
        if chinese_text in mapping:
            return mapping[chinese_text]
        
        # 尝试部分匹配
        for key, value in mapping.items():
            if key in chinese_text:
                return value
        
        # 如果没有匹配，返回空字符串而不是原始文本
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
        import json
        import re
        
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
        except:
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
        
    def _translate_theme_elements_to_english(self, theme_elements):
        """将主题元素翻译成英文"""
        if not theme_elements:
            return []
        
        # 常见主题元素的中英对照
        translations = {
            '氦气': 'helium', '芯片': 'chip', '半导体': 'semiconductor',
            '医疗': 'medical', '供应链': 'supply chain', '全球市场': 'global market',
            '中东战火': 'Middle East war', '地缘政治': 'geopolitics',
            '价格波动': 'price fluctuation', '生产基地': 'production base',
            '天然气': 'natural gas', '危机': 'crisis', '恐慌': 'panic',
            '战争': 'war', '冲突': 'conflict', '紧张': 'tension',
            '科技': 'technology', '工业': 'industrial', '经济': 'economy',
            '支援舰艇': 'support ship', '补给舰': 'supply ship', '驱逐舰': 'destroyer',
            '护卫舰': 'frigate', '航母': 'aircraft carrier', '舰队': 'fleet',
            '无人机': 'drone', '侦察机': 'reconnaissance aircraft', '战斗机': 'fighter jet',
            '海峡': 'strait', '霍尔木兹海峡': 'Strait of Hormuz', '港口': 'port',
            '油价': 'oil price', '石油': 'oil', '天然气': 'natural gas',
            '中东': 'Middle East', '冲突': 'conflict', '战争': 'war',
            '军事行动': 'military operation', '战略': 'strategy', '紧张': 'tense',
            '危机': 'crisis', '局势': 'situation', '打击': 'strike',
            '伊朗': 'Iran', '美国': 'USA', '中国': 'China', '俄罗斯': 'Russia',
            '塞拉来港': 'Bandar-e Jask', '塞拉杰': 'Bandar-e Jask', '阿巴斯港': 'Bandar Abbas',
            '霍尔木兹海峡': 'Strait of Hormuz', '波斯湾': 'Persian Gulf',
            '支援舰艇': 'support ship', '补给舰': 'supply ship', '驱逐舰': 'destroyer',
            '护卫舰': 'frigate', '航母': 'aircraft carrier', '舰队': 'fleet', '舰艇': 'warship',
            '无人机': 'drone', '侦察机': 'reconnaissance aircraft', '战斗机': 'fighter jet',
            '海峡': 'strait', '港口': 'port', '海军': 'navy', '海军舰艇': 'naval vessel',
            '油价': 'oil price', '石油': 'oil', '天然气': 'natural gas',
            '中东': 'Middle East', '冲突': 'conflict', '战争': 'war',
            '军事行动': 'military operation', '战略': 'strategy', '紧张': 'tense',
            '危机': 'crisis', '局势': 'situation', '打击': 'strike',
            '雷达': 'radar', '导弹': 'missile', '舰载机': 'carrier-based aircraft'
        }
        
        result = []
        for elem in theme_elements:
            if elem in translations:
                result.append(translations[elem])
            else:
                result.append(elem)
        return result
    
    # =======================================================================
    # 第八部分：文本翻译与主题分析 (行 6819-7221)
    # =======================================================================
    
    def _split_by_words_with_punctuation(self, words, sentence_endings):
        """使用词级时间戳精确切分句子，确保音画同步
        
        Args:
            words: 词列表，每个词包含 'word', 'start', 'end'
            sentence_endings: 句子结束标点的正则表达式
        
        Returns:
            切分后的片段列表
        """
        import re
        
        if not words:
            return []
        
        sentences = []
        current_sentence_words = []
        
        for word_info in words:
            word = word_info.get('word', '').strip()
            if not word:
                continue
            
            current_sentence_words.append(word_info)
            
            # 检查是否句子结束
            if re.search(sentence_endings, word):
                if current_sentence_words:
                    # 构建新片段，使用精确的词时间戳
                    sentence_text = ''.join([w.get('word', '') for w in current_sentence_words])
                    sentence_start = current_sentence_words[0].get('start', 0)
                    sentence_end = current_sentence_words[-1].get('end', 0)
                    
                    sentences.append({
                        'text': sentence_text.strip(),
                        'start': sentence_start,
                        'end': sentence_end,
                        'words': current_sentence_words
                    })
                    current_sentence_words = []
        
        # 处理剩余的词
        if current_sentence_words:
            sentence_text = ''.join([w.get('word', '') for w in current_sentence_words])
            sentence_start = current_sentence_words[0].get('start', 0)
            sentence_end = current_sentence_words[-1].get('end', 0)
            
            sentences.append({
                'text': sentence_text.strip(),
                'start': sentence_start,
                'end': sentence_end,
                'words': current_sentence_words
            })
        
        return sentences
    
    
    def _simplify_theme(self, theme_text):
        """简化核心主题：保留完整语义，仅去除描述性前缀"""
        if not theme_text:
            return theme_text
        
        import re
        
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
            'visual_style': '',
            'theme_elements': [],
            'emotional_tone': '',
            'correction_dict': {}
        }

        if not analysis_result:
            return theme_info

        try:
            import re
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
                except:
                    theme_info['content_type'] = ''

            # 提取核心主题（支持有冒号和无冒号的情况）
            if '核心主题' in cleaned_result:
                try:
                    core_match = cleaned_result.split('核心主题')[1].split('\n')[0]
                    core_match = core_match.replace('：', '').replace(':', '').strip()
                except:
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
                except:
                    pass

            if '视觉基调' in cleaned_result:
                tone_match = cleaned_result.split('视觉基调')[1].split('\n')[0].replace('：', '').replace(':', '').strip()
                theme_info['visual_tone'] = tone_match

            if '视觉风格' in cleaned_result:
                try:
                    style_match = cleaned_result.split('视觉风格')[1].split('\n')[0]
                    style_match = style_match.replace('：', '').replace(':', '').strip()
                    theme_info['visual_style'] = style_match
                    if not theme_info.get('visual_tone'):
                        theme_info['visual_tone'] = style_match
                except:
                    theme_info['visual_style'] = theme_info.get('visual_tone', '')

            # 提取主题元素
            if '主题元素' in cleaned_result or '核心元素' in cleaned_result:
                try:
                    elements_key = '核心元素' if '核心元素' in cleaned_result else '主题元素'
                    elements_text = cleaned_result.split(elements_key)[1].split('\n')[0]
                    elements_text = elements_text.replace('：', '').replace(':', '').strip()
                    elements = re.split(r'[，、,\n]', elements_text)
                    theme_info['theme_elements'] = [e.strip() for e in elements if e.strip()][:8]
                except:
                    theme_info['theme_elements'] = []
            elif 'Theme Elements:' in cleaned_result:
                elements_text = cleaned_result.split('Theme Elements:')[1].split('\n')[0].strip()
                elements = re.split(r'[,;]', elements_text)
                theme_info['theme_elements'] = [e.strip() for e in elements if e.strip()]

            # 提取纠错说明并应用纠正
            correction_dict = {}
            self.log(f"   🔍 检查是否存在'纠错说明'...")
            if '纠错说明' in cleaned_result:
                self.log(f"   🔍 找到纠错说明，正在解析...")
                try:
                    correction_match = cleaned_result.split('纠错说明')[1].split('\n')[0]
                    correction_match = correction_match.replace('：', '').replace(':', '').strip()
                    self.log(f"   🔍 纠错内容原始: {correction_match}")
                    
                    if correction_match and correction_match != '无' and correction_match != '无纠正':
                        # 支持多种分隔符：逗号、顿号、分号
                        separators = [',', '，', '、', ';', '；']
                        parts = [correction_match]
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
                                # 支持多种箭头格式：→ -> =>
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
                                if old and new and old != new:
                                    correction_dict[old] = new
                            except Exception as e:
                                self.log(f"   ⚠️ 解析单项纠错失败: {part}, 错误: {e}")
                                continue
                        
                        if correction_dict:
                            self.log(f"   🔍 解析到纠错字典: {correction_dict}")
                            
                            # 应用纠错到核心主题
                            if theme_info.get('core_theme'):
                                self.log(f"   🔍 原始core_theme: {theme_info['core_theme']}")
                                corrected_theme = theme_info['core_theme']
                                for old, new in correction_dict.items():
                                    corrected_theme = corrected_theme.replace(old, new)
                                theme_info['core_theme'] = corrected_theme
                                self.log(f"   🔄 纠错后core_theme: {theme_info['core_theme']}")
                            
                            # 应用纠错到核心元素
                            if theme_info.get('theme_elements'):
                                self.log(f"   🔍 原始theme_elements: {theme_info['theme_elements']}")
                                corrected_elements = []
                                for elem in theme_info['theme_elements']:
                                    corrected_elem = elem
                                    for old, new in correction_dict.items():
                                        corrected_elem = corrected_elem.replace(old, new)
                                    corrected_elements.append(corrected_elem)
                                theme_info['theme_elements'] = corrected_elements
                                self.log(f"   🔄 纠错后theme_elements: {theme_info['theme_elements']}")
                            
                            # 保存纠错字典供后续使用
                            theme_info['correction_dict'] = correction_dict
                            self.log(f"   ✅ 纠错已应用到主题信息")
                    else:
                        self.log(f"   ℹ️ 纠错说明为'无'，无需纠错")
                        theme_info['correction_dict'] = {}
                except Exception as e:
                    self.log(f"   ⚠️ 解析纠错说明失败: {e}")
                    theme_info['correction_dict'] = {}
            else:
                theme_info['correction_dict'] = {}

        except Exception as e:
            self.log(f"⚠️ 提取主题信息时出错: {e}")

        return theme_info

    def validate_theme_consistency(self, shots, theme_info):
        """验证分镜的主题一致性，偏离时自动修正提示词"""
        if not theme_info.get('core_theme'):
            return True, "未提取到主题信息，跳过一致性检查"

        core_theme = theme_info['core_theme']
        theme_elements = theme_info.get('theme_elements', [])
        visual_tone = theme_info.get('visual_tone', '')
        theme_elements_en = self._translate_theme_elements_to_english(theme_elements) if theme_elements else []

        consistency_issues = []
        fixed_count = 0

        for i, shot in enumerate(shots):
            prompt = shot.get('prompt_en', '').lower()
            
            if theme_elements_en:
                has_theme_element = any(
                    elem.lower() in prompt for elem in theme_elements_en
                )
                if not has_theme_element and i > 0:
                    consistency_issues.append(f"分镜{i+1}")
                    
                    if OLLAMA_AVAILABLE and shot.get('description'):
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
                            if corrected and len(corrected) > 30:
                                shot['prompt_en'] = corrected
                                fixed_count += 1
                        except Exception:
                            pass

        if consistency_issues:
            msg = f"发现{len(consistency_issues)}个偏离主题的分镜"
            if fixed_count > 0:
                msg += f"，已自动修正{fixed_count}个"
            return False, msg

        return True, "主题一致性检查通过"
    

    def check_dependencies(self):
        """检查系统依赖项（优化版）"""
        self.log("正在检查系统依赖项...")
        
        # 检查所有必要的依赖项
        core_dependencies = [
            ("requests", "pip install requests", None),
            ("PIL", "pip install Pillow", None),
            ("numpy", "pip install numpy", None),
            ("moviepy", "pip install moviepy", None),
            ("whisper", "pip install openai-whisper", "load_model"),  # 特殊检查：需要验证load_model函数
        ]
        
        missing_deps = []
        for dep, install_cmd, required_attr in core_dependencies:
            try:
                module = __import__(dep)
                # 如果指定了必需属性，检查该属性是否存在
                if required_attr and not hasattr(module, required_attr):
                    self.log(f"⚠️ {dep} 已安装但功能不完整 (缺少 {required_attr})")
                    missing_deps.append((dep, install_cmd))
                else:
                    self.log(f"✅ {dep} 已安装")
            except ImportError:
                self.log(f"⚠️ {dep} 未安装")
                missing_deps.append((dep, install_cmd))
        
        if missing_deps:
            self.log("❌ 缺少核心依赖项")
            msg = "缺少以下核心依赖项:\n"
            for dep, install_cmd in missing_deps:
                msg += f"- {dep}: {install_cmd}\n"
            messagebox.showwarning("警告", msg)
            return False
        else:
            self.log("✅ 核心依赖项已安装")
            return True

    def check_and_update_dependencies(self):
        """检查并更新依赖项"""
        self.log("====================================")
        self.log("🔧 开始检查并更新依赖项")
        self.log("====================================")
        
        # 定义需要的依赖项及其子依赖（用于解决版本兼容性问题）
        dependencies = [
            ("requests", ["urllib3", "chardet", "charset_normalizer", "idna", "certifi"]),
            ("Pillow", []),
            ("whisper", []),
            ("moviepy", []),
            ("ollama", []),
            ("psutil", []),
            ("GPUtil", []),
        ]
        
        import subprocess
        import sys
        import re
        
        # 统计信息
        total_deps = len(dependencies)
        updated_count = 0
        already_latest_count = 0
        installed_count = 0
        failed_count = 0
        
        self.log(f"📋 待检查依赖项: {total_deps} 个主包")
        self.log("")
        
        # 检查并更新每个依赖项
        for index, (dep, sub_deps) in enumerate(dependencies, 1):
            self.log(f"[{index}/{total_deps}] 🔍 检查 {dep}...")
            
            # 获取当前版本信息
            try:
                module = __import__(dep.replace("Pillow", "PIL"))
                current_version = getattr(module, "__version__", "未知版本")
                self.log(f"   📌 当前版本: {current_version}")
            except Exception:
                current_version = "未安装"
                self.log(f"   📌 当前状态: {current_version}")
            
            try:
                # 尝试导入依赖项
                __import__(dep.replace("Pillow", "PIL"))
                
                # 构建更新命令：主依赖 + 子依赖
                packages_to_update = [dep] + sub_deps
                
                if sub_deps:
                    self.log(f"   📦 关联子依赖: {', '.join(sub_deps)}")
                
                self.log(f"   ⬆️  正在检查更新...")
                
                # 尝试更新依赖项及其子依赖
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade"] + packages_to_update,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    # 解析pip输出，提取版本信息
                    stdout = result.stdout
                    
                    # 检查是否有实际更新
                    if "already up-to-date" in stdout or "already satisfied" in stdout:
                        self.log(f"   ✅ {dep} 已是最新版本")
                        already_latest_count += 1
                    elif "Successfully installed" in stdout:
                        # 提取安装的版本信息
                        installed_packages = []
                        # 匹配 "Successfully installed package-1.0.0"
                        match = re.search(r'Successfully installed (.+)', stdout)
                        if match:
                            packages_str = match.group(1)
                            # 提取每个包的名称和版本
                            for pkg in packages_str.split():
                                # 移除末尾的换行符等
                                pkg = pkg.strip()
                                if pkg:
                                    installed_packages.append(pkg)
                        
                        if installed_packages:
                            self.log(f"   ✅ 成功更新:")
                            for pkg in installed_packages:
                                self.log(f"      📦 {pkg}")
                        else:
                            self.log(f"   ✅ {dep} 已更新")
                        
                        updated_count += 1
                    else:
                        # 可能有部分更新或其他情况
                        self.log(f"   ✅ {dep} 检查完成")
                        
                        # 尝试从输出中提取版本信息
                        version_matches = re.findall(r'([a-zA-Z0-9_-]+)-(\d+\.\d+[^\s]*)', stdout)
                        if version_matches:
                            self.log(f"   📋 涉及包版本:")
                            for pkg_name, version in version_matches[:5]:  # 最多显示5个
                                self.log(f"      • {pkg_name} {version}")
                        
                        already_latest_count += 1
                    
                    # 如果有警告信息，显示出来
                    if "WARNING" in stdout:
                        warnings = [line for line in stdout.split('\n') if 'WARNING' in line]
                        for warning in warnings[:2]:  # 最多显示2条警告
                            self.log(f"   ⚠️  {warning.strip()}")
                else:
                    self.log(f"   ❌ 更新 {dep} 时出现错误")
                    error_msg = result.stderr.strip()
                    if error_msg:
                        # 只显示错误的前100个字符
                        self.log(f"      错误: {error_msg[:100]}")
                    failed_count += 1
                    
            except ImportError:
                # 依赖项未安装，进行安装
                self.log(f"   ⚠️  {dep} 未安装，开始安装...")
                packages_to_install = [dep] + sub_deps
                
                if sub_deps:
                    self.log(f"   📦 将同时安装子依赖: {', '.join(sub_deps)}")
                
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install"] + packages_to_install,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    self.log(f"   ✅ {dep} 安装成功")
                    
                    # 尝试显示安装的版本
                    match = re.search(r'Successfully installed ([^\n]+)', result.stdout)
                    if match:
                        installed = match.group(1).strip()
                        self.log(f"      📦 安装详情: {installed}")
                    
                    installed_count += 1
                else:
                    self.log(f"   ❌ 安装 {dep} 失败")
                    error_msg = result.stderr.strip()
                    if error_msg:
                        self.log(f"      错误: {error_msg[:100]}")
                    failed_count += 1
            
            self.log("")  # 空行分隔
        
        # 显示统计总结
        self.log("====================================")
        self.log("📊 依赖项检查和更新统计")
        self.log("====================================")
        self.log(f"   ✅ 已更新: {updated_count} 个")
        self.log(f"   ✓  已是最新: {already_latest_count} 个")
        self.log(f"   📥 新安装: {installed_count} 个")
        if failed_count > 0:
            self.log(f"   ❌ 失败: {failed_count} 个")
        self.log("====================================")
        self.log("🔧 依赖项检查和更新完成")
        self.log("   💡 提示：已自动同步更新子依赖包")
        self.log("====================================")
        
        # 构建提示消息
        msg = f"依赖项检查和更新完成！\n\n"
        msg += f"✅ 已更新: {updated_count} 个\n"
        msg += f"✓  已是最新: {already_latest_count} 个\n"
        msg += f"📥 新安装: {installed_count} 个\n"
        if failed_count > 0:
            msg += f"❌ 失败: {failed_count} 个\n"
        msg += f"\n已自动处理子依赖版本兼容性。"
        
        messagebox.showinfo("成功", msg)
    
    def monitor_performance(self):
        """监控系统性能 - 优化版（非阻塞）"""
        try:
            # 首次调用cpu_percent需要间隔，之后可以非阻塞
            if psutil:
                psutil.cpu_percent(interval=None)  # 初始化
            
            update_interval = 0  # 更新计数器
            
            while getattr(self, 'perf_monitor_running', True):
                if psutil and GPUtil:
                    # 获取CPU使用率（非阻塞，interval=None）
                    cpu_usage = psutil.cpu_percent(interval=None)
                    # 获取内存使用率
                    memory = psutil.virtual_memory()
                    memory_usage = memory.percent
                    memory_used = memory.used // (1024 * 1024)
                    memory_total = memory.total // (1024 * 1024)
                    
                    # 降低GPU检测频率（每5次更新一次）
                    if update_interval % 5 == 0:
                        try:
                            gpus = GPUtil.getGPUs()
                            if gpus:
                                gpu_memory_percent = gpus[0].memoryUtil * 100
                            else:
                                gpu_memory_percent = 0
                        except:
                            gpu_memory_percent = 0
                    
                    # 更新UI（捕获 tkinter 组件已销毁的异常）
                    try:
                        if update_interval % 2 == 0:  # 每2次循环更新一次UI
                            if hasattr(self, 'cpu_label') and self.cpu_label.winfo_exists():
                                self.cpu_label.config(text=f"{cpu_usage:.1f}%")
                            if hasattr(self, 'memory_label') and self.memory_label.winfo_exists():
                                self.memory_label.config(text=f"{memory_usage:.1f}%")
                            if hasattr(self, 'gpu_label') and self.gpu_label.winfo_exists():
                                self.gpu_label.config(text=f"{gpu_memory_percent:.1f}%")
                            if hasattr(self, 'memory_detail_label') and self.memory_detail_label.winfo_exists():
                                self.memory_detail_label.config(text=f"{memory_used} MB / {memory_total} MB")
                    except tk.TclError:
                        break
                    
                    update_interval += 1
                    # 智能调整监控间隔
                    self._perf_monitor_interval = 2.0 if getattr(self, "task_running", False) else 5.0
                
                time.sleep(self._perf_monitor_interval)  # 智能间隔：空闲5s，任务中2s
        except Exception:
            pass

    def init_state_manager(self):
        """初始化状态管理器"""
        self.state_manager = {
            'app': {
                'status': 'ready',
                'current_workflow': None,
                'last_error': None
            },
            'audio': {
                'loaded': False,
                'path': None,
                'duration': 0
            },
            'shots': {
                'generated': False,
                'count': 0,
                'data': []
            },
            'images': {
                'generated': False,
                'count': 0,
                'path': self.images_dir
            },
            'video': {
                'generated': False,
                'path': None
            },
            'system': {
                'cpu_usage': 0,
                'memory_usage': 0,
                'gpu_usage': 0,
                'gpu_memory': 0
            }
        }
        self.log("✅ 状态管理器初始化完成")
    
    def init_event_system(self):
        """初始化事件系统"""
        self.event_system = {}
        self.log("✅ 事件系统初始化完成")
    
    # =======================================================================
    # 第九部分：系统初始化与缓存线程池 (行 7560-7900)
    # =======================================================================
    def init_cache_system(self):
        """初始化缓存系统"""
        self.cache_system = {
            'models': {},
            'prompts': {},
            'images': {},
            'audio': {}
        }
        # 缓存配置
        self.cache_config = {
            'max_size': 1000,  # 最大缓存项数
            'expiry_time': 3600,  # 缓存过期时间（秒）
            'cleanup_interval': 600  # 清理间隔（秒）
        }
        # 缓存统计信息
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'size': 0
        }
        # 缓存清理线程控制标志
        self.cache_cleanup_running = True
        # 启动缓存清理线程
        threading.Thread(target=self.cache_cleanup, daemon=True).start()
        self.log("✅ 缓存系统初始化完成")
    
    def cache_cleanup(self):
        """定期清理过期缓存"""
        while getattr(self, 'cache_cleanup_running', True):
            try:
                time.sleep(self.cache_config['cleanup_interval'])
                
                # 检查是否应该退出
                if not getattr(self, 'cache_cleanup_running', True):
                    break
                    
                current_time = time.time()
                evicted = 0
                
                for category in self.cache_system:
                    items_to_remove = []
                    for key, value in self.cache_system[category].items():
                        # 检查是否有过期时间
                        if isinstance(value, dict) and 'timestamp' in value:
                            if current_time - value['timestamp'] > self.cache_config['expiry_time']:
                                items_to_remove.append(key)
                    
                    # 移除过期项
                    for key in items_to_remove:
                        del self.cache_system[category][key]
                        evicted += 1
                
                if evicted > 0:
                    self.cache_stats['evictions'] += evicted
                    self.cache_stats['size'] = sum(len(items) for items in self.cache_system.values())
                    self.log(f"🔄 缓存清理完成，移除了 {evicted} 个过期项")
            except Exception as e:
                # 检查是否因为关闭导致的异常
                if not getattr(self, 'cache_cleanup_running', True):
                    break
                self.log(f"⚠️ 缓存清理失败: {e}")
    
    def cache_get(self, category, key):
        """获取缓存"""
        if category not in self.cache_system:
            self.cache_stats['misses'] += 1
            return None
        
        item = self.cache_system[category].get(key)
        if item is None:
            self.cache_stats['misses'] += 1
            return None
        
        # 检查是否过期
        if isinstance(item, dict) and 'timestamp' in item and 'value' in item:
            if time.time() - item['timestamp'] > self.cache_config['expiry_time']:
                del self.cache_system[category][key]
                self.cache_stats['misses'] += 1
                self.cache_stats['evictions'] += 1
                return None
            self.cache_stats['hits'] += 1
            return item['value']
        
        self.cache_stats['hits'] += 1
        return item
    
    def cache_set(self, category, key, value):
        """设置缓存"""
        if category not in self.cache_system:
            self.cache_system[category] = {}
        
        # 检查缓存大小
        current_size = sum(len(items) for items in self.cache_system.values())
        if current_size >= self.cache_config['max_size']:
            # 清理最旧的缓存项
            self._cleanup_oldest_cache()
        
        # 添加时间戳
        self.cache_system[category][key] = {
            'value': value,
            'timestamp': time.time()
        }
        
        self.cache_stats['size'] = sum(len(items) for items in self.cache_system.values())
    
    def _cleanup_oldest_cache(self):
        """清理最旧的缓存项"""
        oldest_item = None
        oldest_category = None
        oldest_key = None
        oldest_time = float('inf')
        
        for category in self.cache_system:
            for key, item in self.cache_system[category].items():
                if isinstance(item, dict) and 'timestamp' in item:
                    if item['timestamp'] < oldest_time:
                        oldest_time = item['timestamp']
                        oldest_item = item
                        oldest_category = category
                        oldest_key = key
        
        if oldest_key:
            del self.cache_system[oldest_category][oldest_key]
            self.cache_stats['evictions'] += 1
    
    def cache_clear(self, category=None):
        """清除缓存"""
        if category:
            if category in self.cache_system:
                self.cache_stats['evictions'] += len(self.cache_system[category])
                self.cache_system[category].clear()
        else:
            for cat in self.cache_system:
                self.cache_stats['evictions'] += len(self.cache_system[cat])
                self.cache_system[cat].clear()
        self.cache_stats['size'] = 0
    
    def get_cache_stats(self):
        """获取缓存统计信息"""
        return self.cache_stats
    
    def init_thread_pool(self):
        """初始化线程池"""
        # 基于CPU核心数和系统内存动态调整线程池大小
        import os
        try:
            import psutil
            # 获取CPU核心数
            cpu_count = os.cpu_count() or 4
            # 获取可用内存（GB）
            available_memory = psutil.virtual_memory().available / (1024 ** 3)
            
            # 根据系统资源动态调整线程数
            # RTX 4000 + 8GB显存，优先使用GPU，线程数可以更多
            self.max_workers = min(cpu_count, int(available_memory / 2), 8)  # 最多8个线程
        except ImportError:
            # 如果psutil不可用，使用默认值
            self.max_workers = min(os.cpu_count() or 4, 4)
        
        # 初始化线程池
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.thread_pool = {
            'executor': self.executor,
            'tasks': {},
            'task_counter': 0
        }
        self.thread_pool_stats = {
            'active_threads': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_tasks': 0
        }
        self.log(f"✅ 线程池初始化完成，最大工作线程数: {self.max_workers}")
    
    def process_task_queue(self):
        """处理任务队列"""
        with self.task_lock:
            if self.task_running or not self.task_queue:
                return
            
            # 按优先级排序任务队列
            self.task_queue.sort(key=lambda task_id: self.thread_pool['tasks'][task_id]['priority'], reverse=True)
            
            # 获取下一个任务
            task_id = self.task_queue.pop(0)
            self.current_task = task_id
            self.task_running = True
        
        # 执行任务
        self.execute_task(task_id)
    
    def execute_task(self, task_id):
        """执行任务 - 在子线程中执行，避免阻塞UI"""
        task = self.thread_pool['tasks'].get(task_id)
        if not task:
            with self.task_lock:
                self.task_running = False
                self.current_task = None
            self.process_task_queue()
            return
        
        task['status'] = 'running'
        self.thread_pool_stats['active_threads'] += 1
        
        def run_task():
            """在子线程中执行任务"""
            try:
                if task['type'] == 'generate_shots':
                    self.generate_shots()
                elif task['type'] == 'generate_images':
                    self.generate_images()
                elif task['type'] == 'generate_video':
                    self.generate_video()
                
                task['status'] = 'completed'
                self.thread_pool_stats['completed_tasks'] += 1
                self.log(f"✅ 任务完成: {task['type']}")
            except Exception as e:
                task['status'] = 'failed'
                task['error'] = str(e)
                self.thread_pool_stats['failed_tasks'] += 1
                self.log(f"❌ 任务失败: {task['type']} - {e}")
            finally:
                self.thread_pool_stats['active_threads'] -= 1
                with self.task_lock:
                    self.task_running = False
                    self.current_task = None
                # 处理下一个任务
                self.process_task_queue()
        
        # 在子线程中执行任务
        threading.Thread(target=run_task, daemon=True, name=f"Task-{task_id}").start()
    
    def _cleanup_residual_files(self):
        """启动时清理上次可能残留的磁盘文件"""
        try:
            if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    os.remove(shots_file)

                if hasattr(self, 'images_dir') and os.path.exists(self.images_dir):
                    for f in os.listdir(self.images_dir):
                        fp = os.path.join(self.images_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass

                for f in os.listdir(self.output_dir):
                    fp = os.path.join(self.output_dir, f)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
        except Exception:
            pass

    def _thorough_cleanup(self):
        """彻底清理所有分镜脚本数据和缓存 - 确保无残留"""
        try:
            self.shots_data = []
        except Exception:
            pass

        try:
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
        except Exception:
            pass

        try:
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
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
                if 'audio' in self.state_manager:
                    self.state_manager['audio'] = {
                        'loaded': False,
                        'path': None,
                        'duration': 0
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
            if hasattr(self, 'total_audio_duration'):
                self.total_audio_duration = 0
        except Exception:
            pass

        try:
            if hasattr(self, 'audio_path'):
                self.audio_path = None
        except Exception:
            pass

        try:
            if hasattr(self, 'cache_system') and isinstance(self.cache_system, dict):
                for cat in list(self.cache_system.keys()):
                    self.cache_system[cat] = {}
        except Exception:
            pass

        try:
            if hasattr(self, 'cache_stats') and isinstance(self.cache_stats, dict):
                self.cache_stats = {
                    'hits': 0,
                    'misses': 0,
                    'evictions': 0,
                    'size': 0
                }
        except Exception:
            pass

        try:
            prompt_cache.clear()
        except Exception:
            pass

        try:
            image_cache.clear()
        except Exception:
            pass

        try:
            if hasattr(self, 'arv_prompter') and self.arv_prompter is not None:
                del self.arv_prompter
                self.arv_prompter = None
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

        try:
            if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    os.remove(shots_file)

                if hasattr(self, 'images_dir') and os.path.exists(self.images_dir):
                    for f in os.listdir(self.images_dir):
                        fp = os.path.join(self.images_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass

                for f in os.listdir(self.output_dir):
                    fp = os.path.join(self.output_dir, f)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass
        except Exception:
            pass

    def on_close(self):
        """关闭窗口时的处理 - 增强版，确保快速退出并彻底清除所有残留数据"""
        try:
            self.log("🔄 正在关闭程序，清理资源...")
        except Exception:
            pass

        try:
            self.perf_monitor_running = False
            self.cache_cleanup_running = False
            self.task_running = False
        except Exception:
            pass

        try:
            if hasattr(self, 'resize_timer') and self.resize_timer:
                self.root.after_cancel(self.resize_timer)
                self.resize_timer = None
        except Exception:
            pass

        try:
            self.save_config()
        except Exception:
            pass

        try:
            with self.task_lock:
                self.task_paused = False
                self.pause_event.set()
                self.task_queue.clear()
                self.current_task = None
        except Exception:
            pass

        try:
            if hasattr(self, 'executor'):
                try:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self.executor.shutdown(wait=False)
        except Exception:
            pass

        try:
            import torch
            import gc

            if self.whisper_model is not None:
                try:
                    self.whisper_model = self.whisper_model.to("cpu")
                except Exception:
                    pass
                del self.whisper_model
                self.whisper_model = None

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            gc.collect()
        except ImportError:
            pass
        except Exception:
            pass

        try:
            self._thorough_cleanup()
        except Exception:
            pass

        try:
            import gc
            gc.collect()
        except Exception:
            pass

        try:
            self.log("✅ 资源清理完成，正在退出...")
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass

        try:
            if sys.stdout and hasattr(sys.stdout, 'close'):
                try:
                    sys.stdout.close()
                except Exception:
                    pass
            if sys.stderr and hasattr(sys.stderr, 'close'):
                try:
                    sys.stderr.close()
                except Exception:
                    pass
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        import os
        os._exit(0)
    
    # =======================================================================
    # 第十部分：主任务执行 - 生成分镜/图片/视频 (行 7995-8940)
    # =======================================================================
    def system_check(self):
        """系统检查"""
        self.log("正在进行系统检查...")
        # 检查依赖项
        self.check_dependencies()
        # 检查SD API连接
        # self.check_sd_api_connection()
        self.log("✅ 系统检查完成")
    
    def generate_shots(self, auto_mode=False):
        """生成分镜 - 修复异常处理和状态管理
        
        Args:
            auto_mode: 自动模式，为True时不显示完成弹窗（用于自动化流程）
        """
        # 确保在函数开始时就导入必要的模块
        import os
        import hashlib
        import gc
        
        global OLLAMA_AVAILABLE
        
        # 初始化变量，防止 NameError
        analysis_result = ""
        theme_info = {}
        
        # 用于跟踪资源，确保清理
        resources_to_cleanup = []
        whisper_model_loaded = False
        whisper_used_gpu = False
        
        try:
            # 检查是否有音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，无法生成分镜")
                self.update_task_progress("就绪")
                return
            
            # 检查Ollama服务是否可用
            if not OLLAMA_AVAILABLE:
                self.log("🔄 正在检测Ollama服务...")
                try:
                    response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_SHORT)
                    if response.status_code == 200:
                        OLLAMA_AVAILABLE = True
                        self.log("✅ Ollama服务已连接")
                    else:
                        raise Exception("服务响应异常")
                except Exception:
                    # 尝试自动启动
                    self.log("⚠️ Ollama服务未运行，尝试自动启动...")
                    import subprocess
                    ollama_path = None
                    for path in [r"C:\Ollama\ollama.exe", r"C:\Program Files\Ollama\ollama.exe",
                               os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                               "ollama"]:
                        if os.path.exists(path) or path == "ollama":
                            ollama_path = path
                            break
                    if ollama_path:
                        subprocess.Popen([ollama_path, "serve"],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                        time.sleep(3)
                        try:
                            response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
                            if response.status_code == 200:
                                OLLAMA_AVAILABLE = True
                                self.log("✅ Ollama服务已自动启动并连接")
                        except Exception:
                            pass
                    
                    if not OLLAMA_AVAILABLE:
                        self.log("❌ Ollama服务不可用")
                        if not auto_mode:
                            self.root.after(0, lambda: messagebox.showwarning(
                                "Ollama服务不可用",
                                "Ollama大模型服务未运行，无法生成分镜！\n\n"
                                "分镜生成需要Ollama进行：\n"
                                "• 语音文本纠错和标点添加\n"
                                "• 主题分析和内容分类\n"
                                "• 提示词生成\n\n"
                                "请先启动Ollama服务后重试。"
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
                    if 'audio' in self.state_manager:
                        self.state_manager['audio'] = {
                            'loaded': False,
                            'path': None,
                            'duration': 0
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
            
            try:
                old_shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(old_shots_file):
                    os.remove(old_shots_file)
                    self.log("🗑️ 已删除旧的分镜脚本文件")
                if os.path.exists(self.images_dir):
                    for f in os.listdir(self.images_dir):
                        fp = os.path.join(self.images_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
                if os.path.exists(self.output_dir):
                    for f in os.listdir(self.output_dir):
                        fp = os.path.join(self.output_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
            except Exception:
                pass
            
            # 步骤1: 音频分析
            self.log("\n📍 步骤 1/4: 音频语音识别")
            self.update_task_progress("正在分析音频...", 10)
            
            # 生成音频文件的缓存键（添加文件大小防止冲突）
            try:
                audio_stat = os.stat(self.audio_path)
                audio_key = f"audio_{hashlib.md5(self.audio_path.encode()).hexdigest()}_{audio_stat.st_mtime}_{audio_stat.st_size}"
            except Exception as e:
                self.log(f"❌ 无法读取音频文件: {e}")
                self.update_task_progress("就绪")
                return
            
            # 检查缓存中是否有分析结果
            cached_result = self.cache_get('audio_analysis', audio_key)
            if cached_result:
                self.log("✅ 从缓存加载音频分析结果")
                segments = cached_result.get('segments', [])
                full_text = cached_result.get('full_text', "")
                self.log(f"   识别片段数: {len(segments)}")

                # 缓存命中，释放 Whisper 占用的 GPU
                try:
                    import torch
                    if self.whisper_model is not None and torch.cuda.is_available():
                        try:
                            self.whisper_model = self.whisper_model.to("cpu")
                            torch.cuda.empty_cache()
                            self.log("   ✅ Whisper GPU 资源已释放（缓存命中）")
                        except Exception:
                            pass
                except ImportError:
                    pass
            else:
                # 加载Whisper模型进行语音识别
                self.update_task_progress("正在加载Whisper模型...", 20)
                
                import warnings
                warnings.filterwarnings("ignore", message="Failed to launch Triton kernels")
                
                if self.whisper_model:
                    # 模型已预加载（在CPU上），按需移至GPU
                    try:
                        import torch
                        whisper_model_size = "medium"
                        if torch.cuda.is_available():
                            gpu_name = torch.cuda.get_device_name(0)
                            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                            self.log(f"🖥️ 加载Whisper到GPU: {gpu_name} ({gpu_memory:.1f}GB)")
                            self.whisper_model = self.whisper_model.to("cuda")
                            whisper_used_gpu = True
                            self.log(f"✅ Whisper {whisper_model_size} 已加载到GPU")
                        else:
                            self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                    except Exception as e:
                        self.log(f"⚠️ Whisper移至GPU失败，使用CPU: {e}")
                else:
                    # 模型未预加载，全新加载
                    self.log("📦 正在加载Whisper模型...")
                    try:
                        import torch
                        
                        whisper_model_size = "medium"
                        
                        if torch.cuda.is_available():
                            device = "cuda"
                            gpu_name = torch.cuda.get_device_name(0)
                            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                            cuda_version = torch.version.cuda
                            self.log(f"🖥️ 使用GPU加速: {gpu_name}")
                            self.log(f"   CUDA版本: {cuda_version}")
                            self.log(f"   GPU显存: {gpu_memory:.1f} GB")
                            self.log(f"   使用模型: Whisper {whisper_model_size}")
                        else:
                            device = "cpu"
                            self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                            self.log(f"   使用模型: Whisper {whisper_model_size}")
                        
                        self.whisper_model = whisper.load_model(whisper_model_size, device=device)
                        whisper_model_loaded = True
                        
                        if torch.cuda.is_available():
                            whisper_used_gpu = True
                            self.log(f"✅ Whisper {whisper_model_size}模型加载成功 (GPU加速)")
                        else:
                            self.log(f"✅ Whisper {whisper_model_size}模型加载成功 (CPU模式)")
                    except Exception as e:
                        self.log(f"⚠️ GPU加载失败，回退到CPU: {e}")
                        whisper_model_size = "medium"
                        try:
                            self.whisper_model = whisper.load_model(whisper_model_size, device="cpu")
                            whisper_model_loaded = True
                            self.log(f"✅ Whisper {whisper_model_size}模型加载成功 (CPU模式)")
                        except Exception as e2:
                            self.log(f"❌ 模型加载完全失败: {e2}")
                            self.update_task_progress("就绪")
                            return
                
                # 语音识别，启用标点符号（添加超时机制）
                self.update_task_progress("正在进行语音识别...", 30)
                try:
                    # 使用线程池添加超时控制
                    import concurrent.futures
                    
                    # 语音识别（优化参数，更敏感检测停顿）
                    result = self.whisper_model.transcribe(
                        self.audio_path,
                        language="zh",
                        word_timestamps=True,
                        fp16=False,
                        verbose=False,
                        condition_on_previous_text=False,  # 减少对前文依赖，提高切分精度
                        no_speech_threshold=0.3            # 降低无语音阈值，更敏感检测停顿
                    )
                    
                    segments = result.get("segments", [])
                    self.log(f"✅ 语音识别完成，共 {len(segments)} 个片段")
                    
                    # 提示：如果片段过少，说明语音停顿不明显
                    if len(segments) < 50:
                        avg_duration = sum(s.get('end', 0) - s.get('start', 0) for s in segments) / len(segments) if segments else 0
                        self.log(f"   ℹ️ 平均片段时长: {avg_duration:.1f}秒，如需要更细分镜可减小停顿检测阈值")
                except Exception as e:
                    self.log(f"❌ 语音识别失败: {e}")
                    self.update_task_progress("就绪")
                    return
                
                if not segments:
                    self.log("❌ 音频识别失败，无法生成分镜")
                    self.update_task_progress("就绪")
                    return
                
                # 收集完整文本用于大模型分析
                full_text = "".join([segment.get("text", "").strip() for segment in segments])
                
                # 缓存分析结果
                cache_data = {
                    'segments': segments,
                    'full_text': full_text
                }
                self.cache_set('audio_analysis', audio_key, cache_data)
                self.log("✅ 音频分析结果已缓存")

                # Whisper 转录完成，主动释放 GPU 资源（关键优化）
                try:
                    import torch
                    if self.whisper_model is not None and torch.cuda.is_available():
                        self.whisper_model = self.whisper_model.to("cpu")
                        torch.cuda.empty_cache()
                        self.log("   ✅ Whisper 模型 GPU 资源已释放")
                except Exception as e:
                    self.log(f"   ⚠️ Whisper GPU 释放失败: {e}")
            
            # 步骤2: 大模型分析文章内容（用于统一分镜基调）
            self.log("\n📍 步骤 2/4: 分析文章内容（用于统一分镜基调）")
            self.update_task_progress("正在分析文章内容...", 40)
            
            # 初始化变量（修复：确保变量在所有代码路径中都有定义）
            content_type = "general"
            prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
            
            # 显示当前使用的提示词类型
            self.log(f"💬 提示词类型: {prompt_type}")
            self.log(f"🤖 大模型: {self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else '未选择'}")
            
            audio_file_hash = hashlib.md5(self.audio_path.encode()).hexdigest()[:8]
            cache_key_string = f"{audio_file_hash}_{full_text}_{content_type}_{prompt_type}"
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
                'theme_elements': [],
                'content_type': content_type,
                'correction_dict': {}
            }
            user_custom_theme = ""
            user_custom_tone = ""
            
            # 检查缓存中是否有大模型分析结果
            cached_analysis = self.cache_get('analysis', analysis_key)
            if cached_analysis:
                self.log("✅ 从缓存加载大模型分析结果")
                self.log(f"   缓存键包含: 文本内容 + 内容类型({content_type}) + 提示词类型({prompt_type})")
                analysis_result = cached_analysis
                
                # 从缓存中提取主题信息
                theme_info = self.extract_theme_info(analysis_result)
                
                # 重要：使用全局内容类型覆盖（用户选择的优先级最高）
                if content_type:
                    theme_info['content_type'] = content_type
                
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
            else:
                # 动态检测Ollama服务是否可用
                if len(full_text) > 100:
                    # 尝试动态导入和检测Ollama服务
                    ollama_connected = False
                    try:
                        import ollama
                        # 尝试调用API检测服务是否响应
                        try:
                            response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
                            if response.status_code == 200:
                                OLLAMA_AVAILABLE = True
                                ollama_connected = True
                                self.log("✅ 已连接到Ollama服务")
                        except Exception as e:
                            self.log(f"⚠️ Ollama服务未响应: {e}")
                            # 尝试自动启动Ollama服务
                            self.log("   尝试自动启动Ollama服务...")
                            try:
                                import subprocess
                                import os
                                # 查找ollama可执行文件并启动
                                ollama_path = None
                                for path in [r"C:\Ollama\ollama.exe", r"C:\Program Files\Ollama\ollama.exe", 
                                           os.path.expanduser(r"~\AppData\Local\Programs\Ollama\ollama.exe"),
                                           "ollama"]:
                                    if os.path.exists(path) or path == "ollama":
                                        ollama_path = path
                                        break
                                if ollama_path:
                                    subprocess.Popen([ollama_path, "serve"], 
                                                   stdout=subprocess.DEVNULL, 
                                                   stderr=subprocess.DEVNULL,
                                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                                    time.sleep(3)  # 等待服务启动
                                    # 再次尝试连接
                                    try:
                                        response = get_http_session().get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=Config.API_TIMEOUT_MEDIUM)
                                        if response.status_code == 200:
                                            OLLAMA_AVAILABLE = True
                                            ollama_connected = True
                                            self.log("✅ Ollama服务已启动并连接成功")
                                    except Exception:
                                        self.log("❌ 无法启动Ollama服务")
                                else:
                                    self.log("❌ 未找到Ollama安装路径")
                            except Exception as start_err:
                                self.log(f"❌ 启动Ollama失败: {start_err}")
                    except ImportError:
                        self.log("❌ Ollama模块未安装，请运行: pip install ollama")
                    
                    # 只有连接成功后才使用大模型分析
                    if ollama_connected and OLLAMA_AVAILABLE:
                        try:
                            self.update_task_progress("正在使用大模型分析文章内容...", 50)
                            
                            # 获取用户指定的模型
                            user_model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else "gemma3:4b"
                            
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
                            
                            # 获取可用的模型列表
                            def get_available_models():
                                """获取本地可用的Ollama模型列表"""
                                try:
                                    models_info = ollama.list()
                                    available = []
                                    if "models" in models_info:
                                        for m in models_info["models"]:
                                            model_name = m.get("name", m.get("model", ""))
                                            if model_name:
                                                available.append(model_name)
                                    return available
                                except Exception as e:
                                    self.log(f"⚠️ 获取可用模型列表失败: {e}")
                                    return []
                            
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
                            import concurrent.futures
                            
                            def call_ollama_with_model(model_name):
                                """使用指定模型调用Ollama - 通篇分析提取主题"""
                                global ollama_lock
                                try:
                                    custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                                    custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                                    
                                    # 使用新的主题分析模板
                                    template = PromptTemplates.get_template("theme_analysis", text=full_text)
                                    
                                    # 如果用户指定了主题/基调，在系统提示中补充说明
                                    if custom_theme or custom_visual_tone:
                                        user_addition = f"\n\n【用户指定的核心主题】: {custom_theme}" if custom_theme else ""
                                        user_addition += f"\n【用户指定的视觉基调】: {custom_visual_tone}" if custom_visual_tone else ""
                                        system_content = template["system"]
                                        user_content = f"语音转录文本：\n{full_text}{user_addition}"
                                    else:
                                        system_content = template["system"]
                                        user_content = f"语音转录文本：\n{full_text}"
                                    
                                    response = ollama.chat(
                                        model=model_name,
                                        messages=[
                                            {"role": "system", "content": system_content},
                                            {"role": "user", "content": user_content}
                                        ]
                                    )
                                    
                                    # 添加详细调试日志
                                    raw_response = response
                                    result_content = raw_response["message"]["content"].strip()
                                    
                                    # 调试：打印原始响应结构（ChatResponse是对象不是字典）
                                    self.log(f"   🔍 调试: 响应类型: {type(raw_response)}")
                                    
                                    # 调试：打印模型返回的原始内容（截取前200字符）
                                    self.log(f"   🔍 调试: 原始响应内容: {repr(result_content[:200])}")
                                    
                                    return result_content
                                except Exception as e:
                                    raise e
                            
                            # 尝试调用模型，失败时自动切换
                            analysis_result = ""
                            current_model_index = 0
                            max_retries = len(candidate_models)
                            
                            while current_model_index < max_retries and not analysis_result:
                                current_model = candidate_models[current_model_index]
                                
                                self.log(f"\n   [{current_model_index + 1}/{max_retries}] 尝试使用模型: {current_model}")
                                
                                try:
                                    with concurrent.futures.ThreadPoolExecutor() as executor:
                                        future = executor.submit(call_ollama_with_model, current_model)
                                        self.log(f"   等待模型响应中...")
                                        
                                        start_time = time.time()
                                        analysis_result = future.result()
                                        elapsed_time = time.time() - start_time
                                        
                                        if analysis_result:
                                            self.log(f"✅ 模型 {current_model} 响应成功！")
                                            self.log(f"   响应时间: {elapsed_time:.1f}秒")
                                            self.log(f"   响应长度: {len(analysis_result)} 字符")
                                            self.log(f"   响应内容预览: {analysis_result[:100]}...")
                                            
                                            # 如果成功使用的不是用户指定的模型，显示提醒
                                            if current_model != user_model:
                                                self.log(f"⚠️ 提醒: 已自动切换到备用模型 {current_model}")
                                                self.log(f"   原因: 用户指定的模型 {user_model} 无响应或调用失败")
                                            break
                                        else:
                                            self.log(f"⚠️ 模型 {current_model} 返回空结果")
                                            self.log(f"   🔍 请检查上方的调试日志以了解详情")
                                            current_model_index += 1
                                            
                                except concurrent.futures.TimeoutError:
                                    self.log(f"⚠️ 模型 {current_model} 响应超时（超过120秒）")
                                    self.log(f"   可能原因: 模型计算量大或GPU资源不足")
                                    current_model_index += 1
                                    
                                    if current_model_index < max_retries:
                                        next_model = candidate_models[current_model_index]
                                        self.log(f"   自动切换到下一个模型: {next_model}")
                                        time.sleep(1)  # 超时后等待稍长时间再重试
                                except Exception as e:
                                    error_msg = str(e).lower()
                                    self.log(f"⚠️ 模型 {current_model} 调用失败: {str(e)[:100]}")
                                    
                                    # 如果是连接错误，直接退出
                                    if "connection" in error_msg or "refused" in error_msg:
                                        self.log(f"   ❌ Ollama服务连接失败，停止尝试")
                                        break
                                    
                                    current_model_index += 1
                                    
                                    if current_model_index < max_retries:
                                        next_model = candidate_models[current_model_index]
                                        self.log(f"   自动切换到下一个模型: {next_model}")
                                        time.sleep(0.5)  # 短暂延迟后重试
                            
                            # 如果所有模型都失败
                            if not analysis_result:
                                self.log(f"\n❌ 所有候选模型均调用失败（共尝试 {max_retries} 个模型）")
                                self.log(f"   候选模型列表: {', '.join(candidate_models)}")
                                self.log(f"   建议: 请检查Ollama服务是否正常运行，或安装上述模型")
                                # 关闭Ollama释放GPU资源（跨平台）
                                try:
                                    import subprocess
                                    if os.name == 'nt':  # Windows
                                        subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True)
                                    else:  # Linux/macOS
                                        subprocess.run(['pkill', '-f', 'ollama'], capture_output=True)
                                    time.sleep(1)
                                    self.log("🧹 Ollama已关闭，GPU资源已释放")
                                except Exception:
                                    pass
                                analysis_result = ""
                            
                            # 缓存分析结果（即使是空结果也缓存，避免重复失败）
                            if analysis_result:
                                self.cache_set('analysis', analysis_key, analysis_result)
                                self.log("✅ 大模型分析结果已缓存")
                            
                            # 解析分析结果 - 只提取主题信息，不生成分镜
                            self.update_task_progress("正在提取主题信息...", 60)
                            
                            # 首先记录大模型返回的内容
                            self.log(f"📝 大模型返回内容预览: {analysis_result[:500]}...")
                            
                            # 直接从分析结果中提取主题信息
                            theme_info = self.extract_theme_info(analysis_result)
                            
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
                            
                            correction_dict = theme_info.get('correction_dict', {})
                            if correction_dict:
                                self.log(f"🔧 大模型纠错结果: {correction_dict}")
                                self.log("✅ 主题分析完成，纠错结果将应用到分镜文本")
                            else:
                                self.log("✅ 主题分析完成，文本无需纠错")
                        
                        except Exception as e:
                            self.log(f"   ⚠️ 大模型分析过程出错: {str(e)[:100]}")
                            self.log("   将使用原始语音片段创建分镜")
                            theme_info = {
                                'content_type': '', 
                                'core_theme': '', 
                                'visual_tone': '', 
                                'theme_elements': [],
                                'visual_style': '',
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
            
            # 步骤2.5: 使用原始语音片段（确保时间戳准确性，实现100%语音同步）
            self.log("\n📍 步骤 2.5/4: 使用原始语音片段")
            self.update_task_progress("正在处理原始语音片段...", 65)
            
            # 直接使用原始语音片段，不进行语义合并以保持时间戳准确性
            final_tasks = original_shot_tasks
            self.log(f"📝 使用原始语音片段: {len(final_tasks)} 个分镜")
            
            # 预先为原始分镜生成提示词
            pregenerated_prompts = {}
            
            self.log("\n🎨 预先为原始分镜生成提示词...")
            
            if not final_tasks:
                self.log("   ⚠️ 没有分镜数据")
            
            # 获取用户选择的提示词类型
            user_prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
            
            self.log(f"💬 提示词类型: {user_prompt_type}")
            
            # 预热模型 - 发送简单请求加载模型到GPU
            self.log("🔥 预热模型中...")
            try:
                import ollama
                model = self.ollama_model_var.get()
                warmup_start = time.time()
                ollama.chat(
                    model=model,
                    messages=[{"role": "user", "content": "ok"}]
                )
                warmup_time = time.time() - warmup_start
                self.log(f"✅ 模型预热完成 ({warmup_time:.1f}秒)")
            except Exception as e:
                self.log(f"⚠️ 模型预热失败: {str(e)[:50]}")
            
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
            
            start_time = time.time()
            
            failed_count = 0
            
            def generate_single_prompt(idx_task):
                """单个提示词生成任务"""
                idx, task = idx_task
                try:
                    dubbing = task.get('text', '')
                    if dubbing:
                        effective_visual_style = user_style_override if user_style_override else theme_info.get('visual_style', '')
                        
                        prompt = self._generate_prompt_with_llm(
                            dubbing, 
                            content_type=theme_info.get('content_type', ''), 
                            prompt_type=user_prompt_type,
                            core_theme=theme_info.get('core_theme', ''),
                            visual_tone=theme_info.get('visual_tone', ''),
                            theme_elements=theme_info.get('theme_elements', []),
                            visual_style=effective_visual_style,
                            original_dubbing=dubbing,
                            full_text=full_text
                        )
                        return (idx, prompt, None)
                    return (idx, "", None)
                except Exception as e:
                    import traceback
                    full_error = f"{str(e)}\n{traceback.format_exc()}"
                    return (idx, "", full_error)
            
            if hasattr(self, 'prompt_thread_count_var'):
                prompt_max_workers = self.prompt_thread_count_var.get()
            else:
                prompt_max_workers = 4
            
            total_tasks = len(final_tasks)
            self.log(f"   开始生成 {total_tasks} 个提示词（{prompt_max_workers}线程并行）...")
            
            self._shot_texts_for_context = [task.get('text', '') for task in final_tasks]

            with concurrent.futures.ThreadPoolExecutor(max_workers=prompt_max_workers) as executor:
                results = list(executor.map(generate_single_prompt, enumerate(final_tasks)))
                
                for idx, prompt, error in results:
                    if error:
                        failed_count += 1
                        error_display = error[:200] if len(error) > 200 else error
                        self.log(f"   ⚠️ 第{idx+1}个生成失败: {error_display}")
                        pregenerated_prompts[idx] = ""
                    else:
                        pregenerated_prompts[idx] = prompt
            
            elapsed = time.time() - start_time
            speed = len(pregenerated_prompts) / elapsed if elapsed > 0 else 0
            self.log(f"   完成 {len(pregenerated_prompts)} 个 (速度: {speed:.2f}个/秒)")
            
            if failed_count > 0:
                self.log(f"❌ 错误: {failed_count} 个提示词生成失败，任务终止")
                return
            
            self.log(f"✅ 提示词预生成完成 ({len(pregenerated_prompts)} 个)")
            
            self._pregenerated_prompts = pregenerated_prompts
            
            # 步骤3: 解析和校准分镜
            self.log("\n📍 步骤 3/4: 解析和校准分镜")

            if not theme_info.get('core_theme') and not theme_info.get('visual_tone'):
                theme_info = self.extract_theme_info(analysis_result) if analysis_result else theme_info
            
            if theme_info.get('core_theme'):
                final_theme = self._simplify_theme(theme_info['core_theme'])
                if final_theme != theme_info['core_theme']:
                    theme_info['core_theme'] = final_theme
            
            user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
            user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
            
            display_theme = user_custom_theme if user_custom_theme else theme_info.get('core_theme', '')
            display_tone = user_custom_tone if user_custom_tone else theme_info.get('visual_tone', '')
            
            if display_theme:
                self.log(f"🎯 核心主题: {display_theme}")
            if display_tone:
                self.log(f"🎨 视觉基调: {display_tone}")
            if theme_info.get('theme_elements'):
                self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:8])}")

            self.update_task_progress("正在创建分镜...", 80)
            self.log(f"📝 基于语义片段创建分镜（大模型已预生成提示词）")
            
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
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import os
            
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
            correction_dict = theme_info.get('correction_dict', {})
            
            if correction_dict:
                self.log(f"   🔧 大模型纠错字典: {correction_dict}")
            
            def create_shot_task(task_data):
                idx, shot_start, shot_end, shot_text, shot_type = task_data
                
                if correction_dict and shot_text:
                    original_text = shot_text
                    for old, new in correction_dict.items():
                        shot_text = shot_text.replace(old, new)
                    if shot_text != original_text:
                        self.log(f"   🔄 分镜{idx+1}大模型纠错: {original_text[:20]}... → {shot_text[:20]}...")
                
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
                
                for future in as_completed(futures):
                    try:
                        idx, shot = future.result()
                        with lock:
                            if shot:
                                shots_dict[idx] = shot
                            completed_count += 1
                            if completed_count % 5 == 0 or completed_count == len(shot_tasks):
                                elapsed = time.time() - create_start_time
                                speed = completed_count / elapsed if elapsed > 0 else 0
                                self.log(f"   📊 正在创建分镜: {completed_count}/{len(shot_tasks)} (速度: {speed:.1f}个/秒)")
                                progress = 50 + int(completed_count / len(shot_tasks) * 30) if len(shot_tasks) > 0 else 50
                                self.update_task_progress(f"正在创建分镜: {completed_count}/{len(shot_tasks)}", progress)
                    except Exception as e:
                        self.log(f"   ⚠️ 创建分镜失败: {str(e)}")
            
            elapsed_time = time.time() - create_start_time
            
            # 按索引排序
            shots = [shots_dict[i] for i in sorted(shots_dict.keys())]
            self.log(f"✅ 成功创建 {len(shots)} 个分镜（{thread_count}线程并行，耗时 {elapsed_time:.1f}秒，速度 {len(shots)/elapsed_time:.1f}个/秒）")

            self.log("   ✅ 保持原始时间戳，确保音画同步")

            # 立即保存分镜数据（先保存再验证，确保文件不延迟）
            self.shots_data = shots
            self.state_manager['shots']['generated'] = True
            self.state_manager['shots']['count'] = len(shots)
            self.state_manager['shots']['data'] = None
            
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump(shots, f, ensure_ascii=False, indent=2)
            self.log(f"   ✅ 分镜数据已保存: {shots_file}")

            # 验证分镜主题一致性（如果大模型分析成功）
            if theme_info.get('core_theme'):
                # 在自动模式下，跳过耗时的主题一致性检查和修正
                if auto_mode:
                    self.log("ℹ️ 自动模式：跳过主题一致性检查以加速流程")
                else:
                    is_consistent, consistency_msg = self.validate_theme_consistency(shots, theme_info)
                    if is_consistent:
                        self.log(f"✅ {consistency_msg}")
                    else:
                        self.log(f"⚠️ {consistency_msg}")
                        self.log(f"💡 建议: 检查分镜提示词是否围绕主题'{theme_info['core_theme']}'展开")
                        if not is_consistent:
                            with open(shots_file, 'w', encoding='utf-8') as f:
                                json.dump(shots, f, ensure_ascii=False, indent=2)
                            self.log(f"   ✅ 修正后的分镜数据已重新保存")

            # 检查分镜是否为空
            if not shots:
                self.log("❌ 未能生成分镜，请检查音频文件是否正确")
                self.update_task_progress("就绪")
                messagebox.showwarning("警告", "未能生成分镜，请检查音频文件是否正确")
                return
            
            # 步骤4: 验证和完成
            self.log("\n📍 步骤 4/4: 验证分镜数据")
            self.update_task_progress("正在验证分镜数据...", 90)
            
            audio_total_duration = segments[-1].get("end", 0) if segments else 0
            
            self.log("🔍 验证时间戳完整性...")
            total_shots_duration = sum(s['duration'] for s in shots)
            
            if abs(total_shots_duration - audio_total_duration) > 0.1:
                self.log(f"   ⚠️ 时长差异: 分镜{total_shots_duration:.2f}s vs 音频{audio_total_duration:.2f}s")
                self.log(f"   ✅ 保持原始时间戳，确保音画同步")
            else:
                self.log(f"   ✅ 时间戳验证通过")
            
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
            self.log("=" * 50)
            self.log("✅ 分镜脚本生成完成！")
            self.log(f"   📊 共 {len(shots)} 个分镜")
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
            
            # 清理内存
            import gc
            gc.collect()
            
            # 分镜任务完成后立即释放显存
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    self.log("🧹 分镜任务完成，GPU显存已释放")
            except Exception:
                pass
            
            # 关闭Ollama释放GPU显存（分镜任务不再需要大模型）
            try:
                import subprocess
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True)
                else:
                    subprocess.run(['pkill', '-f', 'ollama'], capture_output=True)
                self.log("🧹 Ollama已关闭，GPU显存已释放")
            except Exception:
                pass
            
            # 更新进度为完成
            self.update_task_progress("分镜生成完成", 100)
        
        except Exception as e:
            self.log(f"❌ 生成分镜失败: {e}")
            import traceback
            traceback.print_exc()
            self.update_task_progress("生成失败", 0)
            return []
        finally:
            # 释放Whisper占用的GPU显存
            if whisper_used_gpu and hasattr(self, 'whisper_model') and self.whisper_model:
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.whisper_model = self.whisper_model.to("cpu")
                        torch.cuda.empty_cache()
                        self.log("🧹 Whisper GPU显存已释放，模型保留在CPU内存中")
                except Exception as e:
                    self.log(f"⚠️ 释放Whisper GPU显存失败: {e}")
            
            # 如果模型是本次加载的（非预加载），完全卸载释放内存
            if whisper_model_loaded and hasattr(self, 'whisper_model') and self.whisper_model:
                try:
                    import torch
                    del self.whisper_model
                    self.whisper_model = None
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    self.log("🧹 Whisper模型已完全卸载，内存已释放")
                except Exception as e:
                    self.log(f"⚠️ 卸载Whisper模型失败: {e}")
    
    def generate_images(self):
        """生成图像"""
        self.log("🖼️ 开始生成图像...")
        try:
            import os
            import requests
            from PIL import Image
            from io import BytesIO
            
            # 检查是否有分镜数据，如果没有则尝试从文件加载
            if not self.shots_data:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        for shot in self.shots_data:
                            if 'description' in shot and shot['description']:
                                shot['description'] = self.clean_text(shot['description'])
                        self.log(f"📂 已从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        self.log("❌ 没有分镜数据，无法生成图像")
                        self.update_task_progress("就绪")
                        return
                else:
                    self.log("❌ 没有分镜数据，无法生成图像")
                    self.update_task_progress("就绪")
                    return
            
            # 更新进度
            self.update_task_progress("正在连接SD服务...", 10)
            
            # 检查SD API连接状态
            api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else "http://127.0.0.1:7860"
            current_sd_model = "未知"  # 当前实际使用的SD模型
            
            # 获取用户设置的像素尺寸
            width = int(self.width_var.get()) if hasattr(self, 'width_var') else 1920
            height = int(self.height_var.get()) if hasattr(self, 'height_var') else 1080
            
            # 调试：显示原始设置值
            raw_width = self.width_var.get() if hasattr(self, 'width_var') else "未设置"
            raw_height = self.height_var.get() if hasattr(self, 'height_var') else "未设置"
            self.log(f"   原始设置: 宽={raw_width}, 高={raw_height}")
            
            # 获取用户选择的模型
            selected_model = self.model_var.get() if hasattr(self, 'model_var') else "使用当前模型"
            
            # 获取用户选择的风格预设
            selected_styles = self.get_selected_styles()
            
            # ========== 步骤1: 连接SD服务 ==========
            self.log("")
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log("🖼️ 图像生成任务开始")
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            try:
                # 获取当前SD配置
                options_response = get_http_session().get(f"{api_url}/sdapi/v1/options", timeout=Config.API_TIMEOUT_MEDIUM)
                if options_response.status_code != 200:
                    self.log(f"❌ SD服务连接失败 (状态码: {options_response.status_code})")
                    self.log("💡 请确认 Stable Diffusion Web UI 已启动")
                    self.update_task_progress("就绪")
                    return
                
                options = options_response.json()
                current_sd_model = options.get('sd_model_checkpoint', '未知')
                self.log(f"✅ SD服务连接成功")
                self.log(f"   服务地址: {api_url}")
                self.log(f"   当前模型: {current_sd_model}")
                
                # 获取可用模型列表
                models_response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_MEDIUM)
                if models_response.status_code == 200:
                    available_models = models_response.json()
                    self.log(f"   可用模型: {len(available_models)} 个")
                else:
                    available_models = []
                    self.log(f"   可用模型: 无法获取")
                    
            except Exception as e:
                self.log(f"❌ SD服务连接异常: {str(e)}")
                self.log("💡 请确认 Stable Diffusion Web UI 已启动且API地址正确")
                self.update_task_progress("就绪")
                return
            
            # ========== 步骤2: 准备生成参数 ==========
            self.update_task_progress("正在准备生成参数...", 20)
            self.log("")
            self.log("📋 生成参数配置:")
            self.log(f"   图像尺寸: {width} × {height} 像素")
            self.log(f"   用户选择模型: {selected_model}")
            if selected_styles:
                self.log(f"   风格预设: {', '.join(selected_styles)}")
            self.log(f"   采样参数: steps=25, cfg=7.0, sampler=DPM++ 2M Karras")
            
            # 确保图像目录存在
            if not os.path.exists(self.images_dir):
                os.makedirs(self.images_dir)
            
            # 准备风格描述
            style_descriptions = []
            for style in selected_styles:
                style_desc = self.generate_style_description(style)
                if style_desc:
                    style_descriptions.append(style_desc)
            
            # 按分镜ID排序
            sorted_shots = sorted(self.shots_data, key=lambda x: x['id'])
            
            # 统计需要生成的图像
            tasks = []
            skipped_count = 0
            for shot in sorted_shots:
                shot_id = shot['id']
                prompt = shot['prompt_en']
                image_file = shot['image_file']
                image_path = os.path.join(self.images_dir, image_file)
                description = shot.get('description', 'No content')
                negative_prompt = shot.get('negative_prompt', '')
                
                if os.path.exists(image_path):
                    skipped_count += 1
                    continue
                
                enhanced_prompt = prompt
                if style_descriptions:
                    style_text = ", ".join(style_descriptions)
                    enhanced_prompt = f"{prompt}, {style_text}"
                
                tasks.append((shot_id, enhanced_prompt, image_file, image_path, description, negative_prompt))
            
            self.log("")
            self.log(f"📊 任务统计:")
            self.log(f"   总分镜数: {len(self.shots_data)} 个")
            if skipped_count > 0:
                self.log(f"   已存在跳过: {skipped_count} 个")
            self.log(f"   需要生成: {len(tasks)} 个")
            
            # ========== 步骤3: 模型切换（如需要）==========
            if selected_model and selected_model != "使用当前模型":
                self.log("")
                self.log("🔄 模型切换:")
                self.log(f"   目标模型: {selected_model}")
                self.log(f"   当前模型: {current_sd_model}")
                
                try:
                    # 直接使用用户选择的模型名称（已从 SD API 获取）
                    sd_model_name = selected_model
                    
                    if len(available_models) == 0:
                        models_response = get_http_session().get(f"{api_url}/sdapi/v1/sd-models", timeout=Config.API_TIMEOUT_LONG)
                        if models_response.status_code == 200:
                            available_models = models_response.json()
                    
                    target_model = None
                    for model_info in available_models:
                        # 精确匹配或部分匹配
                        model_title = model_info.get('title', '')
                        model_name = model_info.get('model_name', '')
                        
                        # 去掉扩展名后比较
                        clean_title = model_title.replace('.safetensors', '').replace('.ckpt', '')
                        
                        if sd_model_name == clean_title or sd_model_name == model_title or sd_model_name == model_name:
                            target_model = model_title  # 使用完整的 title 来切换
                            break
                        # 也支持部分匹配
                        elif sd_model_name.lower() in model_title.lower() or sd_model_name.lower() in model_name.lower():
                            target_model = model_title
                            break
                    
                    if target_model:
                        switch_response = get_http_session().post(
                            f"{api_url}/sdapi/v1/options",
                            json={"sd_model_checkpoint": target_model},
                            timeout=30
                        )
                        if switch_response.status_code == 200:
                            # 确认切换成功
                            confirm_response = get_http_session().get(f"{api_url}/sdapi/v1/options", timeout=Config.API_TIMEOUT_MEDIUM)
                            if confirm_response.status_code == 200:
                                new_options = confirm_response.json()
                                current_sd_model = new_options.get('sd_model_checkpoint', '未知')
                                self.log(f"   ✅ 切换成功")
                                self.log(f"   实际使用: {current_sd_model}")
                            else:
                                self.log(f"   ⚠️ 切换命令已发送，但无法确认结果")
                        else:
                            self.log(f"   ❌ 切换失败 (HTTP {switch_response.status_code})")
                            self.log(f"   继续使用: {current_sd_model}")
                    else:
                        self.log(f"   ❌ 未找到目标模型")
                        self.log(f"   继续使用: {current_sd_model}")
                        
                except Exception as e:
                    self.log(f"   ❌ 切换异常: {e}")
                    self.log(f"   继续使用: {current_sd_model}")
            
            # ========== 最终配置确认 ==========
            self.log("")
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log(f"🎯 实际使用模型: {current_sd_model}")
            self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.log("")
            
            # 定义图像生成函数
            def generate_single_image(task):
                shot_id, enhanced_prompt, image_file, image_path, description, neg_prompt = task
                
                # 检查是否被暂停
                if not self.pause_event.is_set():
                    self.log("⏸️ 任务已暂停，等待恢复...")
                    self.pause_event.wait()
                
                # 检查是否被取消
                if not self.task_running:
                    self.log("❌ 任务已被取消")
                    return False
                
                self.log(f"📷 [{shot_id+1}/{len(self.shots_data)}] {image_file}")
                
                # 检查提示词长度，过长可能导致处理变慢
                if len(enhanced_prompt) > 500:
                    self.log(f"   ⚠️ 提示词较长 ({len(enhanced_prompt)}字符)，可能影响生成速度")
                
                # 尝试使用本地Stable Diffusion API生成图像，增加重试机制
                max_retries = 3
                retry_delay = 5
                
                for retry in range(max_retries):
                    try:
                        gen_width = width
                        gen_height = height
                        
                        # 记录请求开始时间
                        request_start_time = time.time()
                        
                        # 发送完整参数
                        payload = {
                            "prompt": enhanced_prompt,
                            "negative_prompt": neg_prompt or "",
                            "width": gen_width,
                            "height": gen_height,
                            "steps": 28,
                            "cfg_scale": 7.5,
                            "sampler_name": "DPM++ 2M Karras",
                            "seed": -1,
                            "batch_size": 1
                        }
                        
                        # 发送请求（超时90秒）
                        response = get_http_session().post(f"{api_url}/sdapi/v1/txt2img", json=payload, timeout=Config.API_TIMEOUT_LONG)
                        
                        request_time = time.time() - request_start_time
                        
                        if response.status_code == 200:
                            result = response.json()
                            if "images" in result and len(result["images"]) > 0:
                                import base64
                                image_data = base64.b64decode(result["images"][0])
                                image = Image.open(BytesIO(image_data))
                                image.save(image_path)
                                self.log(f"   ✅ 完成 (耗时 {request_time:.1f}s)")
                                return True
                            else:
                                self.log(f"   ❌ 失败: 无图像数据")
                                if retry < max_retries - 1:
                                    self.log(f"   🔄 重试 {retry+1}/{max_retries}...")
                                    time.sleep(retry_delay)
                                    continue
                        else:
                            self.log(f"   ❌ 失败: HTTP {response.status_code}")
                            if retry < max_retries - 1:
                                self.log(f"   🔄 重试 {retry+1}/{max_retries}...")
                                time.sleep(retry_delay)
                                continue
                            
                    except requests.exceptions.Timeout:
                        self.log(f"   ❌ 请求超时 (90秒)")
                        if retry < max_retries - 1:
                            self.log(f"   🔄 重试 {retry+1}/{max_retries}...")
                            time.sleep(retry_delay)
                            continue
                    except requests.exceptions.ConnectionError:
                        self.log(f"   ❌ 连接失败: SD服务未响应")
                        self.log(f"   💡 请检查 SD WebUI 是否正常运行")
                        return False
                    except Exception as e:
                        error_msg = str(e)[:50]
                        self.log(f"   ❌ 错误: {error_msg}")
                        if retry < max_retries - 1:
                            self.log(f"   🔄 重试 {retry+1}/{max_retries}...")
                            time.sleep(retry_delay)
                            continue
                
                return False
            
            # ========== 步骤4: 预取流水线生成图像 ==========
            if tasks:
                self.log("")
                # SD 生成前释放 Whisper 占用的 GPU
                try:
                    import torch
                    if self.whisper_model is not None and torch.cuda.is_available():
                        self.whisper_model = self.whisper_model.to("cpu")
                        torch.cuda.empty_cache()
                        self.log("   🧹 Whisper GPU 显存已释放，准备 SD 生成")
                except Exception as e:
                    self.log(f"   ⚠️ GPU 显存释放失败: {e}")
                self.log(f"🚀 开始生成 {len(tasks)} 张图像...")
                self.log(f"   模式: 预取流水线（SD生成与图片保存并行）")
                self.log("")

                import queue
                import base64
                from PIL import Image
                from io import BytesIO

                # --- 图片保存队列: 解码+保存在独立线程中执行 ---
                save_queue = queue.Queue(maxsize=8)

                def image_saver():
                    """独立IO线程: 解码base64并保存图片到磁盘"""
                    while True:
                        item = save_queue.get()
                        if item is None:
                            save_queue.task_done()
                            break
                        try:
                            _, save_path, b64_data = item
                            img_bytes = base64.b64decode(b64_data)
                            image = Image.open(BytesIO(img_bytes))
                            image.save(save_path)
                        except Exception:
                            pass
                        finally:
                            save_queue.task_done()

                saver_thread = threading.Thread(target=image_saver, daemon=True)
                saver_thread.start()

                # --- 结果队列: producer线程把SD响应放入，主线程消费 ---
                result_queue = queue.Queue(maxsize=16)

                def sd_producer():
                    """独立请求线程: 连续发送SD生成请求，实现预取"""
                    for idx, (sid, prompt, img_file, img_path, desc, neg) in enumerate(tasks):
                        # 检查取消
                        if not self.task_running:
                            result_queue.put((idx, None, None, "cancelled"))
                            break
                        # 检查暂停
                        if not self.pause_event.is_set():
                            self.pause_event.wait()

                        # 检查缓存
                        ck = hashlib.md5(f"{prompt}_{width}_{height}".encode()).hexdigest()
                        cached = image_cache.get(ck)
                        if cached:
                            result_queue.put((idx, ck, cached, "cached", img_path))
                            continue

                        # 发送SD请求（含重试）
                        max_retries = 3
                        retry_delay = 5
                        for retry in range(max_retries):
                            if not self.task_running:
                                result_queue.put((idx, None, None, "cancelled"))
                                break
                            try:
                                req_start = time.time()
                                resp = get_http_session().post(
                                    f"{api_url}/sdapi/v1/txt2img",
                                    json={
                                        "prompt": prompt,
                                        "negative_prompt": neg or "",
                                        "width": width, "height": height,
                                        "steps": 28, "cfg_scale": 7.5,
                                        "sampler_name": "DPM++ 2M Karras",
                                        "seed": -1, "batch_size": 1
                                    },
                                    timeout=45
                                )
                                req_time = time.time() - req_start

                                if resp.status_code == 200:
                                    rj = resp.json()
                                    if "images" in rj and rj["images"]:
                                        img_data = rj["images"][0]
                                        image_cache.set(ck, img_data)
                                        result_queue.put((idx, ck, img_data, "generated", req_time, img_path))
                                        break
                                    else:
                                        if retry < max_retries - 1:
                                            time.sleep(retry_delay)
                                else:
                                    if retry < max_retries - 1:
                                        time.sleep(retry_delay)
                            except requests.exceptions.ConnectionError:
                                result_queue.put((idx, None, None, "connection_error"))
                                break
                            except requests.exceptions.Timeout:
                                if retry < max_retries - 1:
                                    time.sleep(retry_delay)
                            except Exception as e:
                                if retry < max_retries - 1:
                                    time.sleep(retry_delay)
                        else:
                            result_queue.put((idx, None, None, "failed"))
                    # 发送结束信号
                    result_queue.put(None)

                producer_thread = threading.Thread(target=sd_producer, daemon=True, name="SD-Producer")
                producer_thread.start()

                # --- 主线程（消费者）: 从队列取结果，更新UI ---
                results = []
                generated_count = 0
                failed_count = 0
                cached_count = 0
                batch_start_time = time.time()
                total_tasks = len(tasks)
                received = 0

                while received < total_tasks:
                    item = result_queue.get()
                    if item is None:
                        break

                    result_type = item[3] if len(item) > 3 else "unknown"

                    if result_type == "cancelled":
                        self.log("❌ 任务已被取消")
                        break

                    idx = item[0]

                    # 更新进度
                    progress = 40 + (received / total_tasks) * 50
                    self.update_task_progress(f"生成图像 {received+1}/{total_tasks}...", progress)

                    # 每5张输出一次日志
                    if received % 5 == 0 or received == total_tasks - 1:
                        elapsed = time.time() - batch_start_time
                        avg_time = elapsed / (received + 1)
                        remaining = (total_tasks - received - 1) * avg_time
                        _, _, _, shot_id = tasks[idx][:4]
                        self.log(f"📷 [{received+1}/{total_tasks}] (已用{elapsed:.0f}s, 预计剩余{remaining:.0f}s)")

                    if result_type == "cached":
                        cached_count += 1
                        img_path = item[4]
                        save_queue.put((idx, img_path, item[2]), timeout=30)
                        self.log(f"   ✅ 缓存命中")

                    elif result_type == "generated":
                        generated_count += 1
                        req_time = item[4]
                        img_path = item[5]
                        save_queue.put((idx, img_path, item[2]), timeout=30)
                        self.log(f"   ✅ 完成 (耗时 {req_time:.1f}s)")

                    elif result_type == "connection_error":
                        failed_count += 1
                        self.log(f"   ❌ 连接失败: SD服务未响应")
                        self.log(f"   💡 请检查 SD WebUI 是否正常运行")
                        break

                    else:
                        failed_count += 1
                        self.log(f"   ❌ 生成失败")

                    received += 1
                    result_queue.task_done()

                # 等待保存线程完成
                save_queue.put(None)
                saver_thread.join(timeout=120)

                # 等待producer结束
                producer_thread.join(timeout=5)

            self.state_manager['images']['generated'] = True
            self.state_manager['images']['count'] = generated_count
            
        except Exception as e:
            self.log(f"❌ 图像生成失败: {e}")
            import traceback
            traceback.print_exc()
    
    # =======================================================================
    # 第十一部分：音视频导入与渲染 (行 9398-10278)
    # 包含：清除图片视频、导入音频、视频渲染、输出文件夹
    # =======================================================================
    def clear_images_and_videos(self):
        """清除图片和视频文件"""
        self.log("🗑️ 开始清除图片和视频文件...")
        try:
            import os
            
            if os.path.exists(self.images_dir):
                for file in os.listdir(self.images_dir):
                    file_path = os.path.join(self.images_dir, file)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                            self.log(f"✅ 已删除图片: {file}")
                        except Exception:
                            pass
            
            if os.path.exists(self.output_dir):
                for file in os.listdir(self.output_dir):
                    file_path = os.path.join(self.output_dir, file)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                            self.log(f"✅ 已删除文件: {file}")
                        except Exception:
                            pass
            
            self.log("✅ 图片和视频文件清除完成")
        except Exception as e:
            self.log(f"❌ 清除图片和视频文件失败: {e}")
    
    def generate_video(self, skip_clear=False, use_original_resolution=False, skip_image_check=False):
        """生成视频
        
        Args:
            skip_clear: 是否跳过清除旧文件（跑图模式设为True）
            use_original_resolution: 是否使用原始图片分辨率
            skip_image_check: 是否跳过图片检查（直接渲染模式设为True）
        """
        self.log("🎞️ 开始生成视频...")
        
        # 定义简化的取消检查函数
        def check_cancelled():
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return True
            if not self.pause_event.is_set():
                self.log("⏸️ 任务已暂停")
                self.pause_event.wait()
            return False
        
        try:
            import os
            from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip, ColorClip
            import numpy as np
            
            self.update_task_progress("正在准备...", 10)
            
            if check_cancelled():
                return
            
            # 步骤1: 清理旧文件（可选）
            if not skip_clear:
                self.update_task_progress("正在清理旧文件...", 15)
                self.clear_images_and_videos()
            
            if check_cancelled():
                return
            
            # 步骤2: 加载分镜数据
            if not self.shots_data:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    with open(shots_file, 'r', encoding='utf-8') as f:
                        self.shots_data = json.load(f)
                    self.log(f"📂 加载分镜数据: {len(self.shots_data)} 个")
                else:
                    self.log("❌ 没有分镜数据，请先生成分镜")
                    self.update_task_progress("就绪")
                    return
            
            # 步骤3: 检查音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，请先导入音频")
                self.update_task_progress("就绪")
                return
            
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   请重新导入音频文件")
                self.update_task_progress("就绪")
                return
            
            # 步骤4: 检查并补充图片
            if skip_image_check:
                self.log("ℹ️ 跳过图片检查")
            else:
                self.update_task_progress("正在检查图片...", 20)
                missing_count = sum(1 for shot in self.shots_data 
                                   if not os.path.exists(os.path.join(self.images_dir, shot['image_file'])))
                
                if missing_count > 0:
                    self.log(f"⚠️ 缺少 {missing_count} 张图片，开始生成...")
                    self.log("🔄 正在调用图像生成模块...")
                    
                    # 记录开始时间
                    img_start_time = time.time()
                    
                    self.generate_images()
                    
                    # 记录耗时
                    img_elapsed = time.time() - img_start_time
                    self.log(f"✅ 图像生成完成 (耗时: {img_elapsed:.1f}s)")
                    self.log("🎬 所有图片已就绪，开始视频合成...")
                    
                    # 再次检查
                    missing_count = sum(1 for shot in self.shots_data 
                                       if not os.path.exists(os.path.join(self.images_dir, shot['image_file'])))
                    if missing_count > 0:
                        missing_files = [shot['image_file'] for shot in self.shots_data 
                                        if not os.path.exists(os.path.join(self.images_dir, shot['image_file']))]
                        self.log(f"❌ 仍有 {missing_count} 张图片缺失，无法生成视频")
                        self.log(f"   缺失的图片: {missing_files[:5]}")
                        if len(missing_files) > 5:
                            self.log(f"   ... 还有 {len(missing_files) - 5} 张")
                        self.update_task_progress("就绪")
                        return
                else:
                    self.log("✅ 所有图片已存在，跳过生成步骤")

            if check_cancelled():
                return
            
            # 步骤5: 加载音频
            self.update_task_progress("正在加载音频...", 30)
            
            # 再次检查音频文件（可能在图片生成期间被删除或移动）
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   音频文件可能在图片生成期间被移动或删除")
                self.log("   请重新导入音频文件")
                self.update_task_progress("就绪")
                return
            
            audio = AudioFileClip(self.audio_path)
            audio_duration = audio.duration
            
            # 验证时间轴（只显示信息，不修改原始时间戳）
            self.update_task_progress("正在验证时间轴...", 35)
            total_shots_duration = 0
            for shot in self.shots_data:
                expected_duration = shot['end'] - shot['start']
                shot['duration'] = expected_duration
                total_shots_duration += expected_duration
            
            self.log(f"📊 音频时长: {audio_duration:.2f}s, 分镜总时长: {total_shots_duration:.2f}s")
            
            # 计算时间间隔和重叠
            total_gaps = 0
            total_overlap = 0
            for i in range(1, len(self.shots_data)):
                gap = self.shots_data[i]['start'] - self.shots_data[i-1]['end']
                if gap > 0.05:
                    total_gaps += gap
                elif gap < 0:
                    total_overlap += abs(gap)
            
            if total_gaps > 0:
                self.log(f"   ⏱️ 时间间隔: {total_gaps:.2f}s")
            if total_overlap > 0:
                self.log(f"   ⚠️ 时间重叠: {total_overlap:.2f}s")
            
            self.log("   📍 保持原始语音时间戳，确保音画同步")
            
            if check_cancelled():
                return
            
            # 步骤6: 准备视频片段
            self.update_task_progress("正在准备视频片段...", 40)
            
            # 获取用户选择的动画效果
            animation_type = self.animation_var.get() if hasattr(self, 'animation_var') else "无"
            transition_type = self.transition_var.get() if hasattr(self, 'transition_var') else "硬切"
            self.log(f"🎬 动画效果: {animation_type}")
            self.log(f"🎬 过渡效果: {transition_type}")
            
            # 获取视频分辨率
            width = int(self.width_var.get()) if hasattr(self, 'width_var') else 1920
            height = int(self.height_var.get()) if hasattr(self, 'height_var') else 1080
            
            # 检测是否有时间间隔或重叠
            # 始终使用精确定位模式，保持语音时间戳不变
            # 这样可以确保图片显示时间与语音片段精确对应
            has_gaps = any(self.shots_data[i]['start'] > self.shots_data[i-1]['end'] + 0.05 
                          for i in range(1, len(self.shots_data)))
            has_overlap = any(self.shots_data[i]['start'] < self.shots_data[i-1]['end'] 
                             for i in range(1, len(self.shots_data)))
            
            if has_gaps:
                self.log("   ⚠️ 检测到时间间隔，使用精确定位模式")
            elif has_overlap:
                self.log("   ⚠️ 检测到时间重叠，使用精确定位模式")
            else:
                self.log("   ✅ 时间戳连续，使用精确定位模式")
            
            self.log("   📍 保持原始语音时间戳，确保音画同步")
            
            if check_cancelled():
                return
            
            # 步骤7: 创建视频片段
            self.update_task_progress("正在创建视频片段...", 45)
            clips = []
            total_shots = len(self.shots_data)
            processed_shots = 0
            
            for shot in self.shots_data:
                if check_cancelled():
                    return
                
                processed_shots += 1
                
                # 更新进度（45% - 55% 范围）
                progress = 45 + int((processed_shots / total_shots) * 10)
                if processed_shots % 10 == 0 or processed_shots == total_shots:  # 每10个分镜更新一次，避免频繁更新
                    self.update_task_progress(f"正在创建视频片段 ({processed_shots}/{total_shots})...", progress)
                
                image_path = os.path.join(self.images_dir, shot['image_file'])
                if os.path.exists(image_path):
                    from PIL import Image
                    with Image.open(image_path) as orig_img:
                        # 调整图片尺寸
                        img = self._resize_image_to_fit(orig_img.copy(), width, height)
                    
                    # 计算图片显示时长（基于原始语音片段时间戳）
                    shot_duration = shot['end'] - shot['start']


                    
                    # 边界检查：时长无效时跳过此片段
                    if shot_duration <= 0:
                        self.log(f"⚠️ 分镜时间戳无效，跳过: {shot.get('image_file', '未知')}")
                        continue
                    
                    # 创建视频片段
                    clip = ImageClip(np.array(img)).with_duration(shot_duration)
                    
                    # 应用动画效果（注意：必须在设置起始时间之前调用）
                    if animation_type != "无":
                        clip = self.apply_animation_effect_prerender(clip)
                    
                    # 应用过渡效果
                    if transition_type == "交叉淡化" and shot_duration > 0.6:
                        crossfade_dur = min(0.3, shot_duration * 0.15)
                        clip = clip.crossfadein(crossfade_dur).crossfadeout(crossfade_dur)
                    
                    # 精确定位到时间轴位置
                    # 使用 with_start 方法（兼容 ImageClip 和 ImageSequenceClip）
                    clip = clip.with_start(shot['start'])
                    
                    clips.append(clip)
                else:
                    self.log(f"⚠️ 图片缺失: {shot['image_file']}")
            
            if not clips:
                self.log("❌ 没有有效的图片文件")
                self.update_task_progress("就绪")
                return
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 步骤8: 合成视频片段
            self.update_task_progress("正在合成视频...", 50)
            
            # 检查是否有时间间隔
            has_gaps = any(self.shots_data[i]['start'] > self.shots_data[i-1]['end'] + 0.05 
                          for i in range(1, len(self.shots_data)))
            
            # 检查第一个片段之前是否有间隔
            first_start = self.shots_data[0]['start'] if self.shots_data else 0
            has_start_gap = first_start > 0.05
            
            if has_gaps or has_start_gap:
                if has_start_gap:
                    self.log(f"   ⚠️ 视频开头有 {first_start:.2f}s 间隔，用第一张图片填充")
                if has_gaps:
                    self.log("   ⚠️ 检测到片段间时间间隔，使用延续图片方式填充")
                
                fixed_clips = []
                prev_clip = None
                
                for i, clip in enumerate(clips):
                    if prev_clip is not None:
                        # 计算前一个片段的实际结束时间
                        prev_end = prev_clip.start + prev_clip.duration
                        curr_start = clip.start
                        gap = curr_start - prev_end
                        
                        if gap > 0.05:
                            # 扩展前一个片段填补间隔
                            new_duration = prev_clip.duration + gap
                            prev_clip = prev_clip.with_duration(new_duration)
                            # 更新列表中前一个元素
                            fixed_clips[-1] = prev_clip
                    
                    fixed_clips.append(clip)
                    prev_clip = clip
                
                clips = fixed_clips
                self.log(f"   ✅ 已修复时间间隔: {len(clips)} 个片段")
            
            try:
                background = ColorClip(size=(width, height), color=(0, 0, 0), duration=audio_duration)
                final_clip = CompositeVideoClip([background] + clips, size=(width, height))
                self.log(f"✅ 视频片段合成完成: {len(clips)} 个")
            except Exception as e:
                self.log(f"❌ 视频片段合成失败: {type(e).__name__} - {str(e)[:200]}")
                self.update_task_progress("就绪")
                return

            if check_cancelled():
                return
            
            # 步骤9: 添加音频
            self.update_task_progress("正在添加音频...", 60)
            final_clip = final_clip.with_audio(audio)
            
            # 步骤10: 渲染视频
            self.update_task_progress("正在渲染视频...", 70)
            output_path = os.path.join(self.output_dir, f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            
            # 检测GPU加速
            use_gpu = False
            gpu_preset = "p4"  # GPU 编码器预设（质量优先）
            try:
                import torch
                import subprocess
                if torch.cuda.is_available():
                    result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True)
                    if 'h264_nvenc' in result.stdout:
                        use_gpu = True
                        self.log(f"⚡ 使用GPU加速渲染 (h264_nvenc)")
                        self.log(f"   📊 编码器预设: preset='{gpu_preset}' (质量优先)")
            except Exception as e:
                self.log(f"⚠️ GPU检测失败: {type(e).__name__} - {str(e)[:100]}")
                use_gpu = False
            
            if not use_gpu:
                self.log("🖥️ 使用CPU渲染 (libx264, preset='veryfast')")
            
            # 渲染视频
            try:
                if use_gpu:
                    # 使用 p4 预设（质量优先），适合高质量输出
                    final_clip.write_videofile(output_path, fps=30, codec='h264_nvenc', audio_codec='aac', preset=gpu_preset, logger=None)
                else:
                    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac', preset='veryfast', logger=None)
            except Exception as e:
                if use_gpu:
                    self.log(f"⚠️ GPU渲染失败，切换CPU: {str(e)[:50]}")
                    self.log("🖥️ 切换为CPU渲染 (libx264, preset='veryfast')")
                    final_clip.write_videofile(output_path, fps=30, codec='libx264', audio_codec='aac', preset='veryfast', logger=None)
                else:
                    raise
            
            # 完成
            self.update_task_progress("视频生成完成", 100)
            self.log("=" * 50)
            self.log("✅ 视频生成完成！")
            self.log(f"   📁 保存位置: {output_path}")
            self.log("=" * 50)
            
            self.state_manager['video']['generated'] = True
            self.state_manager['video']['path'] = output_path
            
            # 释放资源
            for clip in clips:
                try: clip.close()
                except: pass
            try: final_clip.close()
            except: pass
            try: audio.close()
            except: pass
            
            import gc
            gc.collect()
            
            # 打开输出文件夹
            import subprocess
            subprocess.Popen(f'explorer "{os.path.dirname(output_path)}"')
            
        except Exception as e:
            self.log(f"❌ 视频生成失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 确保资源释放
            try:
                import gc
                gc.collect()
            except Exception:
                pass
    
    def import_audio(self):
        """导入音频"""
        self.log("📂 开始导入音频...")
        try:
            import os
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择音频文件",
                filetypes=[("音频文件", "*.mp3 *.wav *.m4a *.flac"), ("所有文件", "*.*")]
            )
            
            if not file_path:
                self.log("⚠️ 用户取消了音频选择")
                return
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                self.log("❌ 音频文件不存在")
                messagebox.showerror("错误", "音频文件不存在")
                return
            
            # 检查文件大小（限制为500MB）
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            if file_size > 500:
                self.log(f"❌ 音频文件过大: {file_size:.2f}MB")
                messagebox.showerror("错误", f"音频文件过大，请选择小于500MB的文件")
                return
            
            # 保存音频路径
            self.audio_path = file_path
            self.state_manager['audio']['loaded'] = True
            self.state_manager['audio']['path'] = file_path
            
            # 清除旧的分镜数据和缓存，防止新音频混入旧音频的转录内容
            self.log("🗑️ 清除旧分镜数据，防止混入旧音频内容...")
            self.shots_data = []
            self.total_audio_duration = 0
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
            
            # 删除旧的分镜脚本文件
            try:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    os.remove(shots_file)
                    self.log("   🗑️ 已删除旧的shots_data.json")
            except Exception:
                pass
            
            # 清除所有缓存（音频分析、提示词等），强制重新转录
            self.cache_clear()
            try:
                prompt_cache.clear()
            except Exception:
                pass
            try:
                image_cache.clear()
            except Exception:
                pass
            
            # 重置状态管理器
            try:
                if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                    self.state_manager['shots'] = {
                        'generated': False,
                        'count': 0,
                        'data': []
                    }
                    self.state_manager['audio']['duration'] = 0
                    if 'images' in self.state_manager:
                        self.state_manager['images']['generated'] = False
                        self.state_manager['images']['count'] = 0
                    if 'video' in self.state_manager:
                        self.state_manager['video']['generated'] = False
                        self.state_manager['video']['path'] = None
            except Exception:
                pass
            
            self.log("✅ 旧数据已清除，新音频将使用全新转录结果")
            
            # 更新UI
            if hasattr(self, 'lbl_audio_status'):
                def update_ui():
                    try:
                        self.lbl_audio_status.config(text=f"已加载: {os.path.basename(file_path)}")
                    except Exception as e:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            self.log(f"✅ 音频导入完成: {os.path.basename(file_path)}")
            
        except Exception as e:
            self.log(f"❌ 音频导入失败: {e}")
            messagebox.showerror("错误", f"音频导入失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def apply_animation_effect_prerender(self, clip):
        """预渲染缩放动画效果 - 使用更高效的帧生成方式
        
        注意：此函数返回新片段，会丢失原片段的 start 属性
              调用方必须在调用此函数后重新设置 with_start()
        """
        try:
            import numpy as np
            from moviepy import VideoClip
            
            original_duration = clip.duration
            
            if not original_duration or original_duration <= 0:
                self.log("⚠️ 动画片段时长无效，跳过动画效果")
                return clip
            
            w, h = clip.size
            
            def make_frame(t):
                try:
                    original_frame = clip.get_frame(t)
                    
                    if isinstance(original_frame, np.ndarray):
                        from PIL import Image
                        img = Image.fromarray(original_frame)
                        
                        scale = 1.0 + 0.05 * (t / original_duration)
                        new_w = int(w * scale)
                        new_h = int(h * scale)
                        resized = img.resize((new_w, new_h), Image.LANCZOS)
                        
                        if new_w > w:
                            left = (new_w - w) // 2
                            top = (new_h - h) // 2
                            resized = resized.crop((left, top, left + w, top + h))
                        
                        return np.array(resized)
                    return original_frame
                except Exception:
                    return clip.get_frame(0) if t > 0 else clip.get_frame(0)
            
            animated_clip = VideoClip(make_frame, duration=original_duration)
            
            return animated_clip
        except Exception as e:
            self.log(f"⚠️ 预渲染动画效果失败: {e}")
            return clip

    def _resize_image_to_fit(self, img, target_width, target_height):
        """将图片缩放到目标尺寸，保持比例，不足部分填充黑边"""
        from PIL import Image
        import numpy as np

        # 获取原始尺寸
        orig_width, orig_height = img.size

        # 计算缩放比例（保持宽高比）
        scale_w = target_width / orig_width
        scale_h = target_height / orig_height
        scale = min(scale_w, scale_h)

        # 计算缩放后的尺寸
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)

        # 缩放图片
        resized = img.resize((new_width, new_height), Image.LANCZOS)

        # 创建目标尺寸的画布（黑色背景）
        new_img = Image.new('RGB', (target_width, target_height), (0, 0, 0))

        # 计算居中粘贴位置
        paste_x = (target_width - new_width) // 2
        paste_y = (target_height - new_height) // 2

        # 粘贴缩放后的图片
        new_img.paste(resized, (paste_x, paste_y))

        return new_img

    def clear_audio(self):
        """清除音频"""
        self.log("🗑️ 清除音频")
        try:
            if self.whisper_model is not None:
                self.log("🔄 释放Whisper模型内存...")
                import gc
                import torch
                del self.whisper_model
                self.whisper_model = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                self.log("✅ Whisper模型内存已释放")
            
            self.audio_path = None
            self.total_audio_duration = 0
            self.shots_data = []

            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
            
            try:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    os.remove(shots_file)
                if os.path.exists(self.images_dir):
                    for f in os.listdir(self.images_dir):
                        fp = os.path.join(self.images_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
                if os.path.exists(self.output_dir):
                    for f in os.listdir(self.output_dir):
                        fp = os.path.join(self.output_dir, f)
                        if os.path.isfile(fp):
                            try:
                                os.remove(fp)
                            except Exception:
                                pass
            except Exception:
                pass
            
            self.cache_clear()

            try:
                prompt_cache.clear()
            except Exception:
                pass

            try:
                image_cache.clear()
            except Exception:
                pass
            
            self.state_manager['audio']['loaded'] = False
            self.state_manager['audio']['path'] = None
            self.state_manager['audio']['duration'] = 0
            self.state_manager['shots']['generated'] = False
            self.state_manager['shots']['count'] = 0
            self.state_manager['shots']['data'] = []

            try:
                if 'images' in self.state_manager:
                    self.state_manager['images']['generated'] = False
                    self.state_manager['images']['count'] = 0
                if 'video' in self.state_manager:
                    self.state_manager['video']['generated'] = False
                    self.state_manager['video']['path'] = None
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
            
            # 更新UI
            if hasattr(self, 'lbl_audio_status'):
                def update_ui():
                    try:
                        self.lbl_audio_status.config(text="未加载音频")
                        # 清空脚本区域（已移除脚本窗口）
                        if hasattr(self, 'txt_script') and self.txt_script:
                            self.txt_script.delete(1.0, tk.END)
                            self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception as e:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            # 清理内存
            import gc
            gc.collect()
            
            self.log("✅ 音频清除完成")
        except Exception as e:
            self.log(f"❌ 音频清除失败: {e}")
            import traceback
            traceback.print_exc()
    
    def render_video_threaded(self):
        """跑图生成视频（完整流程：生成分镜 + 生成图片 + 合成视频）
        
        工作流程（三种情况）：
        1. 有分镜脚本 + 有图片（数量匹配）→ 直接使用，合成视频
        2. 有分镜脚本 + 无图片/图片不匹配 → 使用分镜脚本，生成图片，合成视频
        3. 无分镜脚本 → 从头生成分镜，生成图片，合成视频
        
        每次执行前会自动清除上一次任务的缓存
        """
        try:
            self.log("🎞️ 开始跑图生成视频...")
            self.log("🎬 开始执行生成视频任务")

            # ===== 前置检查 =====
            # 检查1: 必须导入音频文件
            if not self.audio_path:
                self.log("❌ 没有导入音频文件，无法执行任务")
                messagebox.showwarning("缺少音频", "请先导入音频文件，再执行跑图生成视频任务！")
                return
            
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                messagebox.showwarning("音频文件丢失", "音频文件不存在，请重新导入音频文件！")
                return
            
            # 检查2: 检查是否存在分镜脚本文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            has_shots_file = os.path.exists(shots_file)
            
            # 检查3: 图片文件夹内是否存在图片文件
            has_images = False
            image_count = 0
            if os.path.exists(self.images_dir):
                image_files = [f for f in os.listdir(self.images_dir) 
                              if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp'))]
                has_images = len(image_files) > 0
                image_count = len(image_files)
            
            # 加载分镜数据以获取分镜数量（用于后续验证）
            shots_count = 0
            if has_shots_file:
                try:
                    with open(shots_file, 'r', encoding='utf-8') as f:
                        temp_shots = json.load(f)
                    shots_count = len(temp_shots)
                except Exception as e:
                    self.log(f"⚠️ 读取分镜脚本失败: {e}")
                    has_shots_file = False
            
            # ========== 情况1: 有分镜脚本 + 有图片（数量匹配）→ 直接合成视频 ==========
            if has_shots_file and has_images and image_count == shots_count:
                self.log("")
                self.log("=" * 60)
                self.log("✅ 检测到完整的分镜脚本和图片文件")
                self.log("=" * 60)
                self.log(f"   📋 分镜数量: {shots_count} 个")
                self.log(f"   🖼️ 图片数量: {image_count} 张")
                self.log(f"   ✅ 数量匹配，可以直接合成视频")
                self.log("")
                self.log("💡 提示: 将直接使用现有文件，跳过生成分镜和生成图片步骤")
                
                # 直接生成视频
                self.generate_video(skip_clear=True, skip_image_check=True)
                return
            
            # ========== 情况2: 有分镜脚本 + 无图片/图片不匹配 → 使用分镜，生成图片 ==========
            if has_shots_file and (not has_images or image_count != shots_count):
                if not has_images:
                    self.log("")
                    self.log("=" * 60)
                    self.log("✅ 检测到分镜脚本文件，但图片文件夹为空")
                    self.log("=" * 60)
                    self.log(f"   📋 分镜数量: {shots_count} 个")
                    self.log(f"   🖼️ 图片数量: 0 张")
                    self.log("")
                    self.log("💡 提示: 将使用现有分镜脚本，自动生成图片")
                else:
                    self.log("")
                    self.log("=" * 60)
                    self.log("⚠️ 检测到分镜脚本文件，但图片数量不匹配")
                    self.log("=" * 60)
                    self.log(f"   📋 分镜数量: {shots_count} 个")
                    self.log(f"   🖼️ 图片数量: {image_count} 张")
                    self.log(f"   ❌ 数量不匹配（需要 {shots_count} 张）")
                    self.log("")
                    self.log("💡 提示: 将使用现有分镜脚本，重新生成所有图片")
                
                # 启动渲染线程
                self._start_render_thread(mode="use_existing_shots")
                return
            
            # ========== 情况3: 无分镜脚本 → 从头生成 ==========
            if not has_shots_file:
                self.log("")
                self.log("=" * 60)
                self.log("📝 未检测到分镜脚本文件")
                self.log("=" * 60)
                self.log("")
                self.log("💡 提示: 将从头开始生成分镜脚本、图片和视频")
                
                # 启动渲染线程
                self._start_render_thread(mode="full_generation")
                return
            
        except Exception as e:
            self.log(f"❌ 渲染视频线程启动失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_render_thread(self, mode="full_generation"):
        """启动渲染线程
        
        Args:
            mode: "full_generation" - 从头生成, "use_existing_shots" - 使用现有分镜
        """
        def render_video_worker():
            self.task_running = True
            self.pause_event.set()
            try:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                
                # ========== 阶段1: 准备分镜数据 ==========
                self.log("")
                self.log("=" * 60)
                self.log("📋 阶段1/3: 准备分镜数据")
                self.log("=" * 60)
                
                if mode == "use_existing_shots" and os.path.exists(shots_file):
                    # 使用现有分镜脚本
                    self.log("✅ 检测到已存在的分镜脚本文件")
                    self.log("ℹ️ 将直接使用文件夹内分镜脚本生成图片")
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        self.log(f"📂 已加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        self.log("🔄 将重新生成分镜脚本")
                        self.generate_shots(auto_mode=True)
                else:
                    # 从头生成分镜
                    self.log("📝 未检测到分镜脚本，开始从头生成...")
                    self.log("🔄 正在清除上一次任务的缓存...")
                    
                    # 清除旧的分镜数据
                    self.shots_data = []
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    if hasattr(self, '_shot_texts_for_context'):
                        delattr(self, '_shot_texts_for_context')
                    
                    # 删除旧的分镜脚本文件
                    if os.path.exists(shots_file):
                        os.remove(shots_file)
                        self.log("   🗑️ 已删除旧的shots_data.json")
                    
                    # 清除音频分析缓存，强制重新转录
                    self.cache_clear()
                    try:
                        prompt_cache.clear()
                    except Exception:
                        pass
                    try:
                        image_cache.clear()
                    except Exception:
                        pass
                    
                    # 重置状态管理器
                    try:
                        if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                            self.state_manager['shots'] = {
                                'generated': False,
                                'count': 0,
                                'data': []
                            }
                    except Exception:
                        pass
                    
                    self.log("✅ 旧数据已清除，开始生成分镜...")
                    self.generate_shots(auto_mode=True)
                    
                    # 分镜生成完成后，立即记录日志确认
                    self.log("🔍 检查分镜生成结果...")
                
                # 验证分镜是否生成成功
                self.log(f"🔍 验证分镜数据: hasattr={hasattr(self, 'shots_data')}, data={'存在' if hasattr(self, 'shots_data') else '不存在'}, 长度={len(self.shots_data) if hasattr(self, 'shots_data') and self.shots_data else 0}")
                
                if not hasattr(self, 'shots_data') or not self.shots_data:
                    self.log("⚠️ 内存中无分镜数据，尝试从文件加载...")
                    # 尝试从文件加载
                    if os.path.exists(shots_file):
                        try:
                            with open(shots_file, 'r', encoding='utf-8') as f:
                                self.shots_data = json.load(f)
                            self.log(f"📂 从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                        except Exception as e:
                            self.log(f"❌ 加载分镜数据失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    if not self.shots_data:
                        self.log("❌ 分镜生成失败，无法继续")
                        self.update_task_progress("就绪")
                        return
                
                self.log(f"✅ 阶段1完成: {len(self.shots_data)} 个分镜已就绪")
                self.log("🚀 即将进入阶段2: 生成图像...")

                # ========== 阶段2: 生成图像 ==========
                self.log("")
                self.log("=" * 60)
                self.log("🖼️ 阶段2/3: 生成图像")
                self.log("=" * 60)
                
                # 注意: skip_clear=True 避免删除已有图片
                self.generate_video(skip_clear=True, skip_image_check=False)
                
                self.log("✅ 所有阶段完成")
                
            except Exception as e:
                self.log(f"❌ 渲染视频出错: {type(e).__name__}: {str(e)[:200]}")
                import traceback
                traceback.print_exc()
            finally:
                self.task_running = False
                if hasattr(self, '_pregenerated_prompts'):
                    delattr(self, '_pregenerated_prompts')
        
        thread = threading.Thread(target=render_video_worker, daemon=True)
        thread.start()
        self.log("✅ 渲染线程已启动")
    
    def generate_shots_threaded(self):
        """生成分镜脚本（线程化版本）"""
        try:
            with self._task_lock:
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
                with self._task_lock:
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
                    import traceback
                    traceback.print_exc()
                finally:
                    with self._task_lock:
                        self.task_running = False
                        self.current_task_thread = None
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    self.log("✅ 分镜生成任务结束")
            
            thread = threading.Thread(target=generate_shots_worker, daemon=True, name="GenerateShotsThread")
            thread.start()
            
            with self._task_lock:
                self.current_task_thread = thread
                
        except Exception as e:
            self.log(f"❌ 生成分镜线程启动失败: {e}")
            import traceback
            traceback.print_exc()
            with getattr(self, '_task_lock', threading.Lock()):
                self.task_running = False
    
    def open_output_folder(self):
        """打开输出文件夹"""
        import os
        import subprocess
        output_folder = os.path.join(self.base_dir, "output_project")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        subprocess.Popen(f'explorer "{output_folder}"')
    
    def setup_script_area(self):
        """设置脚本区域 - 已移除分镜脚本窗口，仅保留内部变量兼容性"""
        # 不再创建脚本区域UI，仅保留 txt_script 变量以兼容其他代码
        self.txt_script = None
    
    def setup_log_area(self):
        """设置日志区域 - 独占右侧面板"""
        # 创建日志区域
        log_frame = ttk.LabelFrame(self.log_frame_container, text="运行日志", padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建日志控制栏
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 添加清除日志按钮
        btn_clear_log = ttk.Button(log_control_frame, text="🗑️ 清除日志", command=self.clear_log, style="Small.TButton")
        btn_clear_log.pack(side=tk.RIGHT, padx=5)
        
        # 创建日志文本框
        self.txt_log = tk.Text(log_frame, wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4", font=('Microsoft YaHei', self.font_size + 4))
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.txt_log, command=self.txt_log.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_log.config(yscrollcommand=scrollbar.set)
        
        # 添加初始日志
        self.log("📋 日志区域初始化完成")
    
    def log(self, message):
        """记录日志 - 优化版（批量更新）"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        
        # 初始化日志缓冲区和计数器
        if not hasattr(self, '_log_buffer'):
            self._log_buffer = []
            self._log_counter = 0
        
        self._log_buffer.append(log_message)
        self._log_counter += 1
        
        is_important = any(key in message for key in ['✅', '❌', '🎉', '📍', '完成', '失败', '错误', '步骤', '⚠️', '🗑️'])
        
        def update_ui():
            if hasattr(self, 'txt_log') and self.txt_log:
                try:
                    if self._log_buffer:
                        text = '\n'.join(self._log_buffer) + '\n'
                        self._log_buffer.clear()
                        self.txt_log.insert(tk.END, text)
                        self.txt_log.see(tk.END)
                except Exception:
                    pass
        
        if hasattr(self, 'root') and self.root:
            if is_important or self._log_counter % 5 == 0:
                self.root.after(0, update_ui)
            elif self._log_counter > 50:
                self.root.after(0, update_ui)
                self._log_counter = 0
    
    def clear_log(self):
        """清除日志"""
        self.log("🗑️ 清除日志")
        try:
            # 清空日志文本框
            if hasattr(self, 'txt_log') and self.txt_log:
                def update_ui():
                    try:
                        self.txt_log.delete(1.0, tk.END)
                        self.txt_log.insert(tk.END, "📋 日志区域初始化完成\n")
                    except Exception as e:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            self.log("✅ 日志清除完成")
        except Exception as e:
            self.log(f"❌ 日志清除失败: {e}")
            import traceback
            traceback.print_exc()
    
    def show_performance_stats(self):
        """显示性能优化统计信息"""
        self.log("=" * 60)
        self.log("📊 性能优化统计报告")
        self.log("=" * 60)
        
        # 提示词缓存统计
        prompt_stats = prompt_cache.get_stats()
        self.log(f"\n💬 提示词缓存:")
        self.log(f"   命中次数: {prompt_stats['hits']}")
        self.log(f"   未命中次数: {prompt_stats['misses']}")
        self.log(f"   命中率: {prompt_stats['hit_rate']}")
        self.log(f"   缓存条目: {prompt_stats['size']}")
        
        # 图像缓存统计
        image_stats = image_cache.get_stats()
        self.log(f"\n🖼️ 图像缓存:")
        self.log(f"   命中次数: {image_stats['hits']}")
        self.log(f"   未命中次数: {image_stats['misses']}")
        self.log(f"   命中率: {image_stats['hit_rate']}")
        self.log(f"   缓存条目: {image_stats['size']}")
        
        # 硬件加速状态 - 延迟初始化
        self.log(f"\n⚡ 硬件加速:")
        if self.video_renderer is None:
            self.log("   正在检测硬件...")
            self.video_renderer = HardwareAcceleratedRenderer()
        if self.video_renderer:
            encoder = self.video_renderer.preferred_encoder
            self.log(f"   视频编码器: {encoder.get('vcodec', '未知')}")
            self.log(f"   CUDA可用: {'是' if self.video_renderer.has_cuda else '否'}")
            self.log(f"   Quick Sync可用: {'是' if self.video_renderer.has_quicksync else '否'}")
        
        # 线程配置
        self.log(f"\n🔧 并发配置:")
        thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16
        self.log(f"   图像生成线程数: {thread_count}")
        prompt_thread_count = self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
        self.log(f"   提示词生成线程数: {prompt_thread_count}")
        
        # 计算节省时间估计
        total_hits = prompt_stats['hits'] + image_stats['hits']
        if total_hits > 0:
            avg_time_saved_per_hit = 3.0  # 估计每次缓存命中节省3秒
            estimated_time_saved = total_hits * avg_time_saved_per_hit
            self.log(f"\n💰 优化收益估算:")
            self.log(f"   预计节省时间: {estimated_time_saved:.0f} 秒 ({estimated_time_saved/60:.1f} 分钟)")
        
        self.log("=" * 60)
    
    def clear_script(self):
        """清除脚本"""
        self.log("🗑️ 清除脚本")
        try:
            # 清空脚本文本框
            if hasattr(self, 'txt_script') and self.txt_script:
                def update_ui():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception as e:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            self.log("✅ 脚本清除完成")
        except Exception as e:
            self.log(f"❌ 脚本清除失败: {e}")
            import traceback
            traceback.print_exc()
    
    def load_config(self):
        """加载配置"""
        try:
            import os
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 加载绘图设置
                if 'model' in config:
                    self.model_var.set(config['model'])
                if 'width' in config:
                    self.width_var.set(str(config['width']))
                if 'height' in config:
                    self.height_var.set(str(config['height']))
                
                # 加载API设置
                if 'api_type' in config:
                    self.api_var.set(config['api_type'])
                if 'api_url' in config:
                    self.sd_api_url_var.set(config['api_url'])
                    
                # 加载Ollama模型设置
                if hasattr(self, 'ollama_model_var'):
                    if 'ollama_model' in config and config['ollama_model']:
                        self.ollama_model_var.set(config['ollama_model'])
                    else:
                        self.ollama_model_var.set("gemma3:4b")
                    
                if 'llm_config_preset' in config and config['llm_config_preset']:
                    preset = config['llm_config_preset']
                    self.llm_config_preset_var.set(preset)
                    self.current_llm_config.apply_preset(preset)
                else:
                    self.llm_config_preset_var.set("质量优先")
                    self.current_llm_config.apply_preset("质量优先")
                
                # 加载视频设置
                if 'transition' in config and config['transition']:
                    self.transition_var.set(config['transition'])
                else:
                    self.transition_var.set("硬切")
                
                # 加载风格设置
                if 'selected_styles' in config and hasattr(self, 'dlr_vars'):
                    selected_styles = config['selected_styles']
                    for style_name, var in self.dlr_vars:
                        if style_name in selected_styles:
                            var.set(True)
                        else:
                            var.set(False)
                
                # 加载主题自定义设置
                if 'custom_theme' in config:
                    if hasattr(self, 'custom_theme_var'):
                        self.custom_theme_var.set(config['custom_theme'])
                if 'custom_visual_tone' in config:
                    if hasattr(self, 'custom_visual_tone_var'):
                        self.custom_visual_tone_var.set(config['custom_visual_tone'])
                
                # 加载提示词类型设置
                if 'prompt_type' in config and hasattr(self, 'prompt_type_var'):
                    self.prompt_type_var.set(config['prompt_type'])
                
                # 加载动画类型设置
                if 'animation' in config and hasattr(self, 'animation_var'):
                    self.animation_var.set(config['animation'])
                
                # 加载并发线程数设置
                if 'thread_count' in config and hasattr(self, 'thread_count_var'):
                    self.thread_count_var.set(config['thread_count'])
                if 'prompt_thread_count' in config and hasattr(self, 'prompt_thread_count_var'):
                    self.prompt_thread_count_var.set(config['prompt_thread_count'])
                
                # 集中显示已加载的配置
                ollama_model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b'
                whisper_model = 'medium'
                core_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ''
                visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ''
                prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else 'SD提示词'
                animation = self.animation_var.get() if hasattr(self, 'animation_var') else '无'
                thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16
                prompt_thread_count = self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
                
                self.log(f"✅ 已加载Ollama模型: {ollama_model}")
                self.log(f"✅ 已加载音频模型: {whisper_model}")
                self.log(f"✅ 已加载核心主题: {core_theme}")
                self.log(f"✅ 已加载视觉基调: {visual_tone}")
                self.log(f"✅ 已加载提示词类型: {prompt_type}")
                self.log(f"✅ 配置加载完成")
                self._print_current_settings()
        except Exception as e:
            self.log(f"⚠️ 配置加载失败: {e}")
    
    def save_config(self):
        """保存配置"""
        try:
            import os
            # 获取用户选择的风格预设
            selected_styles = self.get_selected_styles()
            
            config = {
                'model': self.model_var.get(),
                'width': int(self.width_var.get()),
                'height': int(self.height_var.get()),
                'api_type': self.api_var.get(),
                'api_url': self.sd_api_url_var.get(),
                'ollama_model': self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b',
                'llm_config_preset': self.llm_config_preset_var.get() if hasattr(self, 'llm_config_preset_var') else '质量优先',
                'whisper_model': 'medium',
                'transition': self.transition_var.get(),
                'selected_styles': selected_styles,
                'custom_theme': self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else '',
                'custom_visual_tone': self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else '',
                'prompt_type': self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else 'SD提示词',
                'animation': self.animation_var.get() if hasattr(self, 'animation_var') else '无',
                'thread_count': self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16,
                'prompt_thread_count': self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log("✅ 配置保存完成")
        except Exception as e:
            self.log(f"⚠️ 配置保存失败: {e}")

# 创建根窗口
root = tk.Tk()

# 初始化应用程序
app = DocuMakerLiteV7(root)

# 启动主循环
root.mainloop()