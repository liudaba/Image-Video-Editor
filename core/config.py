"""配置和常量模块"""

# ==================== Ollama配置 ====================
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_API_TAGS = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_API_CHAT = f"{OLLAMA_BASE_URL}/api/chat"

# Ollama并发配置
DEFAULT_NUM_PARALLEL = 8
DEFAULT_MAX_LOADED_MODELS = 2

# ==================== 模型优先级列表 ====================
# 按大小排序，优先使用最小最快的模型
MODEL_PRIORITY_LIST = [
    ("gemma3:1b", 0.8, "超轻量级模型-首选(815MB)"),
    ("gemma3:4b", 3.3, "通用模型(3.3GB)"),
    ("qwen3:4b", 2.5, "通用模型(2.5GB)"),
    ("qwen2.5:7b", 4.7, "阿里模型(4.7GB)"),
    ("deepseek-r1:8b", 5.2, "推理模型(5.2GB)"),
    ("qwen3:8b", 5.2, "阿里大模型(5.2GB)"),
    ("llama3.2:3b", 2.0, "Meta轻量模型(2.0GB)"),
]

# 轻量级模型列表（用于快速模式）
LIGHTWEIGHT_MODELS = ["gemma3:1b", "qwen2.5:0.5b", "phi3:mini"]

# ==================== LLM配置 ====================
class LLMConfig:
    """LLM配置类"""
    
    CONFIGS = {
        "极速模式": {
            "temperature": 0.3,
            "num_predict": 150,
            "top_p": 0.9,
            "top_k": 40,
        },
        "平衡模式": {
            "temperature": 0.4,
            "num_predict": 200,
            "top_p": 0.9,
            "top_k": 40,
        },
        "质量优先": {
            "temperature": 0.7,
            "num_predict": 400,
            "num_ctx": 8192,
            "top_p": 0.95,
            "top_k": 50,
        }
    }
    
    def __init__(self, mode="平衡模式"):
        self.mode = mode
        self.config = self.CONFIGS.get(mode, self.CONFIGS["平衡模式"])
    
    def get_options(self, num_predict=None):
        """获取Ollama选项"""
        options = dict(self.config)
        if num_predict:
            options["num_predict"] = num_predict
        return options

# ==================== 线程配置 ====================
MAX_THREADS = 16
MIN_THREADS = 4
OLLAMA_MAX_CONCURRENT = 3  # Ollama并发限制

# ==================== 缓存配置 ====================
CACHE_EXPIRY_HOURS = 24

# ==================== 提示词模板 ====================
# System Prompt - 有全文上下文时
SYSTEM_PROMPT_WITH_CONTEXT = """你是一个纪录片视频画面提示词专家。

任务：理解整篇文档的核心思想，分析每个分镜与主题的关系，生成精准的英文画面提示词。

分析要求：
1. 先理解全文核心主题思想
2. 分析当前配音与核心主题的关系
3. 用正确的视觉元素表达配音内容

输出格式：
documentary photography, cinematic still, [具体场景], [视觉元素], 8k uhd, high detail, film grain

禁止：
- 不要有"here's"、"set of tags"等解释
- 不要输出千篇一律的固定格式
- 场景描述要精准匹配配音内容

直接输出英文提示词："""

# System Prompt - 无全文上下文时
SYSTEM_PROMPT_WITHOUT_CONTEXT = """将以下中文翻译成英文图片提示词。

要求：
1. 只输出英文关键词，用逗号分隔
2. 不要有"here's"、"set of tags"等解释
3. 必须包含：documentary photography, cinematic still
4. 场景要具体描述配音内容
5. 结尾加：8k uhd, high detail, film grain

直接输出英文："""

# 轻量级System Prompt
SYSTEM_PROMPT_LIGHTWEIGHT = """将中文配音直接翻译成英文图片提示词。

要求：
1. 只输出英文关键词，用逗号分隔
2. 禁止"here's"、"set of tags"等解释
3. 必须包含风格标签

格式：documentary photography, [场景描述], 8k uhd, high detail"""

# ==================== 需要过滤的坏模式 ====================
BAD_PROMPT_PATTERNS = [
    r"here'?s a set of tags.*",
    r"here'?s.*?prompt.*?(for|about|of)?.*?documentary",
    r"^set of tags.*",
    r"^prompt:.*",
    r"^tags:.*",
    r"following your guidelines.*",
    r"focusing on the provided context.*",
    r"aiming for.*?(documentary|detailed|evocative).*",
    r"according to.*?(your|the).*",
    r"based on.*?(your|the).*",
    r"okay,? here'?s.*",
    r"here'?s.*?(based|formatted|incorporating).*",
    r"a set of tags.*?(for|about).*",
    r"^documentary photography, cinematic still, war journalism, raw photo,",
]

# ==================== 质量标签 ====================
QUALITY_TAGS = [
    "8k uhd", "high detail", "film grain", "natural lighting", 
    "shot on 35mm", "masterpiece", "best quality", 
    "ultra detailed", "photorealistic"
]

# ==================== 负面提示词 ====================
DEFAULT_NEGATIVE_PROMPT = "worst quality, low quality, cartoon, anime, painting, illustration, ugly, deformed, blurry, disfigured, bad anatomy, extra limbs, mutated hands"

# ==================== 内容类型映射 ====================
CONTENT_TYPE_TAGS = {
    "military": "military, warfare, soldiers, combat",
    "political": "politics, government, speech, ceremony",
    "economic": "economy, finance, business, trade",
    "social": "society, crowd, people, daily life",
    "disaster": "disaster, emergency, rescue, damage",
    "general": "general, documentary, news"
}
