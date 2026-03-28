import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import datetime
import warnings
import sys
import time

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
        PRESET_PROMPTS,
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
# pythonw.exe 不会创建控制台，sys.stdout/stderr 为 None
# 这会导致依赖控制台输出的库（如Whisper）抛出 'NoneType' object has no attribute 'write' 错误
_is_pythonw = sys.executable.lower().endswith('pythonw.exe')
_has_no_console = sys.stdout is None or sys.stderr is None

if _is_pythonw or _has_no_console:
    # 在Windows上创建一个独立的控制台窗口用于显示日志
    import ctypes
    from ctypes import wintypes
    
    # 创建一个新的控制台窗口
    ctypes.windll.kernel32.AllocConsole()
    
    # 获取控制台窗口句柄
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    
    if hwnd:
        # 禁用控制台窗口的关闭按钮（防止误关闭导致程序退出）
        # GetSystemMenu: 获取系统菜单句柄
        # EnableMenuItem: 禁用关闭菜单项（SC_CLOSE）
        user32 = ctypes.windll.user32
        
        # 获取系统菜单
        hMenu = user32.GetSystemMenu(hwnd, False)
        if hMenu:
            # 禁用关闭按钮 (SC_CLOSE = 0xF060)
            MF_GRAYED = 0x00000001
            MF_BYCOMMAND = 0x00000000
            SC_CLOSE = 0xF060
            user32.EnableMenuItem(hMenu, SC_CLOSE, MF_GRAYED | MF_BYCOMMAND)
        
        # 设置控制台窗口样式，移除关闭按钮
        # GetWindowLong 和 SetWindowLong 用于修改窗口样式
        GWL_STYLE = -16
        WS_SYSMENU = 0x00080000
        
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        # 保留系统菜单但确保关闭按钮被禁用
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        
        # 强制刷新窗口
        user32.DrawMenuBar(hwnd)
    
    # 重新打开标准输出和标准错误
    sys.stdout = open('CONOUT$', 'w', encoding='utf-8')
    sys.stderr = open('CONOUT$', 'w', encoding='utf-8')
    
    # 设置控制台标题
    ctypes.windll.kernel32.SetConsoleTitleW("短视频生成器 - 日志控制台（最小化到任务栏查看）")
    
    # 打印启动信息
    print("=" * 60)
    print("🎬 短视频生成器 - 日志控制台")
    print("=" * 60)
    print(f"启动时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"运行模式: {'pythonw.exe (GUI模式)' if _is_pythonw else '无控制台模式'}")
    print("=" * 60)
    print()
    print("💡 提示: 此窗口显示程序运行日志")
    print("   • 可以最小化到任务栏")
    print("   • 关闭按钮已被禁用，防止误操作")
    print("   • 程序退出时此窗口会自动关闭")
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
PIL = None

# ==================== 统一的 Ollama 模型调用函数 ====================
def call_ollama_model(model_list, system_prompt, user_prompt, log_callback=None, num_predict=512, num_ctx=4096):
    """
    统一的 Ollama 模型调用函数 - 自动尝试多个模型，直到成功
    
    使用HTTP API直接调用，避免ollama库版本兼容性问题
    """
    global requests
    
    if requests is None:
        try:
            import requests
        except ImportError:
            if log_callback:
                log_callback("⚠️ requests库未安装")
            return None, None
    
    # 获取可用模型列表
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models_info = response.json()
            available_models = []
            if "models" in models_info:
                for m in models_info["models"]:
                    model_name = m.get("name", m.get("model", ""))
                    if model_name:
                        available_models.append(model_name)
        else:
            if log_callback:
                log_callback(f"⚠️ 获取模型列表失败: HTTP {response.status_code}")
            return None, None
    except Exception as e:
        if log_callback:
            log_callback(f"⚠️ 获取模型列表失败: {e}")
        return None, None
    
    # 过滤出实际可用的模型
    candidate_models = []
    for model in model_list:
        if model in available_models:
            candidate_models.append(model)
    
    if not candidate_models:
        if log_callback:
            log_callback(f"⚠️ 模型列表 {model_list} 中没有可用的模型")
        return None, None
    
    # 依次尝试每个模型
    for model in candidate_models:
        try:
            if log_callback:
                log_callback(f"   尝试模型: {model}")
            
            # 使用HTTP API直接调用
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                        "num_predict": num_predict,
                        "num_ctx": num_ctx
                    }
                },
                timeout=120
            )
            
            if response.status_code != 200:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} HTTP错误: {response.status_code}")
                continue
            
            result_data = response.json()
            result = result_data.get("message", {}).get("content", "").strip()
            
            if not result:
                if log_callback:
                    log_callback(f"   ⚠️ 模型 {model} 返回空结果")
                continue
            
            if log_callback:
                log_callback(f"   ✅ 使用模型: {model}")
            
            return result, model
            
        except Exception as e:
            error_msg = str(e)
            if log_callback:
                log_callback(f"   ⚠️ 模型 {model} 调用失败: {error_msg[:50]}")
            continue
    
    if log_callback:
        log_callback(f"❌ 所有模型调用失败")
    return None, None

# ==================== 提示词优化器 ====================
Image = None
ImageDraw = None
ImageFont = None
BytesIO = None

# 全局实例
performance_monitor = None
cache_manager = None

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
class MultiModelFusion:
    """多模型融合系统 - 整合多个模型的优势"""
    
    def __init__(self):
        self.available_models = []
        self.model_weights = {}
        self.fusion_strategy = "weighted_vote"  # weighted_vote, cascade, ensemble
        
    def discover_models(self):
        """发现可用的Ollama模型"""
        if not OLLAMA_AVAILABLE:
            return []
        
        try:
            models = ollama.list()
            if "models" in models:
                self.available_models = []
                for model in models["models"]:
                    name = model.get("name") or model.get("model", "")
                    if name:
                        self.available_models.append(name)
                        self.model_weights[name] = self._calculate_model_weight(name)
                return self.available_models
        except Exception as e:
            error_msg = str(e)
            status_code = getattr(e, 'code', None) or getattr(e, 'status', None) or '未知'
            print(f"发现模型失败: {error_msg} (status code: {status_code})")
        return []
    
    def _calculate_model_weight(self, model_name):
        """根据模型名称计算权重"""
        weights = {
            "gemma3:4b": 0.9,
            "gemma3:1b": 0.7,
            "deepseek-r1:8b": 0.85,
            "deepseek-r1:14b": 0.95,
            "mistral": 0.8,
            "mistral:7b": 0.85,
            "llama3": 0.85,
            "llama3:8b": 0.9,
            "qwen3:8b": 0.9,
            "qwen3:4b": 0.8
        }
        
        # 精确匹配
        if model_name in weights:
            return weights[model_name]
        
        # 部分匹配
        for key, weight in weights.items():
            if key in model_name:
                return weight
        
        return 0.75  # 默认权重
    
    def parallel_generate(self, prompt_template, models=None, timeout=60):
        """并行调用多个模型生成结果"""
        global ollama_lock
        if not OLLAMA_AVAILABLE:
            return None
        
        if models is None:
            models = self.available_models[:3]  # 默认使用前3个模型
        
        if not models:
            return None
        
        results = {}
        
        def call_single_model(model_name):
            """调用单个模型"""
            try:
                start_time = time.time()
                
                # 根据模型特性选择配置
                if "1b" in model_name or "tiny" in model_name:
                    config = LLMConfig("极速模式")
                elif "8b" in model_name or "14b" in model_name:
                    config = LLMConfig("质量优先")
                else:
                    config = LLMConfig("平衡模式")
                
                # Ollama HTTP API 本身线程安全
                response = ollama.chat(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": prompt_template["system"]},
                        {"role": "user", "content": prompt_template["user"]}
                    ]
                )
                
                duration = time.time() - start_time
                result = response["message"]["content"].strip()
                
                return {
                    "model": model_name,
                    "result": result,
                    "duration": duration,
                    "weight": self.model_weights.get(model_name, 0.75)
                }
            except Exception as e:
                return {
                    "model": model_name,
                    "result": "",
                    "duration": 0,
                    "weight": 0,
                    "error": str(e)
                }
        
        # 使用线程池并行调用
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
            future_to_model = {
                executor.submit(call_single_model, model): model 
                for model in models
            }
            
            for future in concurrent.futures.as_completed(future_to_model, timeout=timeout):
                model = future_to_model[future]
                try:
                    result = future.result()
                    results[model] = result
                except Exception as e:
                    results[model] = {
                        "model": model,
                        "result": "",
                        "duration": 0,
                        "weight": 0,
                        "error": str(e)
                    }
        
        return results
    
    def fuse_results(self, results, strategy=None):
        """融合多个模型的结果"""
        if not results:
            return None
        
        if strategy is None:
            strategy = self.fusion_strategy
        
        # 过滤掉错误结果
        valid_results = {k: v for k, v in results.items() if v.get("result") and not v.get("error")}
        
        if not valid_results:
            return None
        
        if strategy == "best_single":
            # 选择权重最高的单个结果
            best = max(valid_results.values(), key=lambda x: x["weight"])
            return best["result"]
        
        elif strategy == "weighted_vote":
            # 加权投票（选择最长且权重较高的结果）
            total_weight = sum(r["weight"] for r in valid_results.values())
            
            # 根据质量和长度评分
            scored_results = []
            for r in valid_results.values():
                length_score = min(len(r["result"]) / 500, 1.0)  # 长度分数，最多500字符得满分
                quality_score = r["weight"]
                final_score = quality_score * 0.7 + length_score * 0.3
                scored_results.append((r, final_score))
            
            # 返回得分最高的结果
            best = max(scored_results, key=lambda x: x[1])
            return best[0]["result"]
        
        elif strategy == "cascade":
            # 级联策略：先用小模型快速生成，再用大模型优化
            sorted_by_size = sorted(
                valid_results.values(),
                key=lambda x: ("1b" in x["model"], "4b" in x["model"], "7b" in x["model"], "8b" in x["model"], "14b" in x["model"]),
                reverse=True
            )
            
            if sorted_by_size:
                return sorted_by_size[0]["result"]
        
        # 默认返回第一个有效结果
        return list(valid_results.values())[0]["result"]
    
    def get_fusion_report(self, results):
        """获取融合过程报告"""
        report = []
        report.append("=" * 50)
        report.append("多模型融合报告")
        report.append("=" * 50)
        
        for model, data in results.items():
            status = "✅ 成功" if data.get("result") else "❌ 失败"
            report.append(f"\n模型: {model}")
            report.append(f"状态: {status}")
            report.append(f"权重: {data.get('weight', 0):.2f}")
            report.append(f"耗时: {data.get('duration', 0):.2f}s")
            if data.get("error"):
                report.append(f"错误: {data['error']}")
            if data.get("result"):
                report.append(f"结果长度: {len(data['result'])} 字符")
        
        report.append("\n" + "=" * 50)
        return "\n".join(report)


# 全局多模型融合实例
multi_model_fusion = MultiModelFusion()


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
    
    # 统一的视觉风格基础标签
    UNIFIED_STYLE_BASE = {
        "sd": "documentary photography, news footage style, realistic, 4K, high detail, sharp focus, cinematic lighting",
        "doubao": "纪录片风格，新闻摄影，真实感，高清画质，细节丰富，电影级光影"
    }
    
    # 内容类型对应的视觉风格
    CONTENT_TYPE_STYLE = {
        "military": {
            "sd": "war zone, military environment, combat documentary, tactical scene",
            "doubao": "战区环境，军事场景，战争纪实，战术画面"
        },
        "politics": {
            "sd": "government building, political scene, diplomatic setting, official venue",
            "doubao": "政府建筑，政治场景，外交场合，官方场所"
        },
        "space": {
            "sd": "deep space, cosmic scene, astronomical visualization, celestial bodies",
            "doubao": "深空场景，宇宙画面，天文可视化，天体图像"
        },
        "science": {
            "sd": "scientific environment, laboratory, research setting, technology",
            "doubao": "科学环境，实验室，研究场所，科技感"
        },
        "nature": {
            "sd": "natural landscape, outdoor scene, environment, wildlife",
            "doubao": "自然风光，户外场景，环境画面，野生动物"
        },
        "history": {
            "sd": "historical setting, period scene, cultural heritage, classical",
            "doubao": "历史场景，时代画面，文化遗产，古典风格"
        },
        "technology": {
            "sd": "high-tech, futuristic, digital, innovation, technology",
            "doubao": "高科技，未来感，数字化，创新，科技感"
        },
        "business": {
            "sd": "business environment, corporate setting, financial district, office scene",
            "doubao": "商业环境，企业场景，金融区，办公画面"
        },
        "economy": {
            "sd": "economic scene, financial market, trading floor, business district",
            "doubao": "经济场景，金融市场，交易大厅，商业区"
        },
        "general": {
            "sd": "documentary style, news photography, realistic scene",
            "doubao": "纪录片风格，新闻摄影，真实场景"
        }
    }
    
    # 主题分析模板 - 智能识别内容类型，针对性分析
    THEME_ANALYSIS = {
        "system": """你是视频内容分析师。分析语音文本并输出结构化结果。

【核心任务】必须先进行彻底的错别字/错别词纠正！
1. 仔细阅读整个语音文本，找出所有可能的语音识别错误
2. 常见错误类型：
   - 同音字错误：如"害器"→"氦气"，"汽年"→"汽车"，"看不"→"看布"
   - 形近字错误：如"末来"→"未来"，"王作"→"工作"
   - 方言/口语误识别：根据上下文判断是否为错误
3. 必须列出所有纠正，格式：原词→纠正词

【重要示例】
- "害器" → "氦气" (惰性气体，用于芯片生产)
- "汽年" → "汽车" (交通工具)
- "错大发了" → "错大发了" (方言表达，保留原词)
- "看不" → "看不" (可能是"看不惯"，需根据上下文)
- "今天天气很好" → "今天天气很好" (无误，保留原词)

【内容类型】新闻播报/军事分析/科普教育/历史纪录/社会民生/财经商业/文化艺术/自然地理/体育竞技

【输出要求】严格按此格式，不要输出其他内容：

【内容类型】：(选一个)
【核心主题】：(一句话，简洁明了，必须使用纠正后的词语)
【情感基调】：(严肃/紧张/轻松/温馨/激昂)
【视觉风格】：(推荐风格)
【核心元素】：(5-8个关键词，使用纠正后的词语)
【场景建议】：(场景类型)
【纠错说明】：(必须列出所有纠正的词语，格式：原词→纠正词，多个用逗号分隔，如"害器→氦气,汽年→汽车"，如无纠正则写"无")

重要：
1. 必须先完成错别字纠正，再输出其他内容
2. 核心主题和核心元素必须使用纠正后的词语
3. 直接输出格式内容，不要有开场白或解释""",
        
        "user_template": """语音文本：
{text}

请先仔细检查整个文本，找出所有可能的语音识别错误，然后按格式输出："""
    }
    
    # 分镜提示词模板 - SD版本（英文）- 精简版
    SHOT_PROMPT_SD = {
        "system": """你是AI图像提示词工程师，为Stable Diffusion生成英文提示词。

【规则】
- 只输出英文关键词，逗号分隔
- 描述可拍摄的画面
- 不要输出解释、标题、标注
- 必须将用户提供的"核心主题"和"视觉基调"融入提示词
- 统一使用电影纪实风格，确保画面风格一致

{style_instruction}
{theme_instruction}

【示例】
配音："中东战事升级"
核心主题：战争反思
视觉基调：冷色调，沉重深刻
输出：Middle Eastern war zone, destroyed buildings with smoke, military tanks on desert road, fighter jets overhead, cold blue tones, somber atmosphere, war documentary style, news photography, realistic, 4K, high detail

配音："科学家发现新黑洞"
核心主题：宇宙探索
视觉基调：神秘，科技感
输出：Space telescope control room, scientists examining data screens, cosmic imagery on displays, mysterious deep space elements, high-tech atmosphere, professional photography, realistic, 4K, high detail, sharp focus

配音："幸福的一家人"
核心主题：家庭温情
视觉基调：温暖，明亮
输出：Happy Asian family, warm home interior, soft golden natural lighting, candid moment, warm and bright atmosphere, lifestyle photography, realistic, 4K, high detail

【必加标签】documentary photography, realistic, 4K, high detail""",
        
        "user_template": """配音：{dubbing}

输出英文提示词："""
    }
    
    # 分镜提示词模板 - 豆包版本（中文）- 精简版
    SHOT_PROMPT_DOUBAO = {
        "system": """你是AI图像提示词工程师，为Stable Diffusion生成中文提示词。

【规则】
- 只输出中文关键词，逗号分隔
- 描述可拍摄的画面
- 不要输出解释、标题、标注
- 必须将用户提供的"核心主题"和"视觉基调"融入提示词
- 统一使用电影纪实风格，确保画面风格一致

{style_instruction}
{theme_instruction}

【示例】
配音："中东战事升级"
核心主题：战争反思
视觉基调：冷色调，沉重深刻
输出：中东战区，冒着浓烟的废墟建筑，沙漠公路上的坦克，头顶的战斗机，冷色调画面，沉重深刻的氛围，战地纪录片风格，新闻摄影风格，真实感，高清画质，细节丰富

配音："科学家发现新黑洞"
核心主题：宇宙探索
视觉基调：神秘，科技感
输出：太空望远镜控制室，科学家查看数据屏幕，显示屏上的宇宙图像，神秘的深空元素，高科技氛围，专业摄影，真实感，高清画质，细节丰富

配音："幸福的一家人"
核心主题：家庭温情
视觉基调：温暖，明亮
输出：幸福的亚洲家庭，温馨的家居环境，温暖明亮的自然光，抓拍瞬间，生活摄影风格，真实感，高清画质，细节丰富

【必加标签】纪录片风格，真实感，高清画质，细节丰富""",
        
        "user_template": """配音：{dubbing}

输出中文提示词："""
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
            "shot_prompt_doubao": cls.SHOT_PROMPT_DOUBAO,
            # 兼容旧的调用名称
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
        is_shot_prompt = template_type in ["shot_prompt_sd", "shot_prompt_doubao"]
        
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
            system_content = template["system"].format(
                style_instruction=style_instruction,
                theme_instruction=theme_instruction
            )
            
            # 构建 user prompt
            dubbing = kwargs.get("dubbing", "")
            user_content = f"""配音：{dubbing}

输出提示词："""
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
    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        self._initialize_ui()
        self._initialize_variables()
        self._initialize_systems()
        self._setup_ui_components()
        self._initialize_event_handlers()
        self._start_system_services()
    
    def _initialize_ui(self):
        """初始化用户界面"""
        self.root.title("DocuMaker Pro Lite V7 | 智能分镜工作流 (SD API 连通版)")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
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
        self.resize_delay = 200  # 防抖延迟，单位毫秒
        
        # 窗口大小跟踪
        self.current_width = 1000
        self.current_height = 700
        
        # 设置样式
        self._setup_styles()
        self.root.configure(bg=self.bg_color)
        
        # 监听窗口大小变化事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 创建布局
        self._create_layout()
    
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
        """处理窗口大小变化的实际逻辑"""
        # 计算缩放比例
        width = event.width
        height = event.height
        
        # 基于窗口宽度计算字体大小
        scale_factor = min(width / 1000, height / 700)
        new_font_size = max(8, int(self.base_font_size * scale_factor))
        
        # 如果字体大小有变化，更新样式
        if new_font_size != self.font_size:
            self.font_size = new_font_size
            self._setup_styles()
            
            # 更新文本框字体大小
            if hasattr(self, 'txt_script'):
                self.txt_script.configure(font=("Microsoft YaHei", self.font_size + 4))
            if hasattr(self, 'txt_log'):
                self.txt_log.configure(font=("Microsoft YaHei", self.font_size + 4))
    
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

        # 上部面板（脚本区域）
        self.top_frame = ttk.Frame(self.right_paned)
        self.right_paned.add(self.top_frame, weight=2)
        
        # 下部面板（日志区域）
        self.bottom_frame = ttk.Frame(self.right_paned)
        self.right_paned.add(self.bottom_frame, weight=1)
    
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
        
        # 模型下拉菜单
        self.model_dropdown_frame = ttk.Frame(self.top_frame)
        self.transition_dropdown_frame = ttk.Frame(self.top_frame)
        
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
        threading.Thread(target=preload_whisper, daemon=True).start()
    
    def auto_connect_ollama(self):
        """启动时自动检测并连接Ollama服务"""
        global OLLAMA_AVAILABLE
        
        try:
            import requests
            import subprocess
            import os
            
            # 尝试直接连接
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=3)
                if response.status_code == 200:
                    OLLAMA_AVAILABLE = True
                    self.log("✅ Ollama服务已连接")
                    return
            except Exception:
                pass
            
            # Ollama未运行，尝试自动启动
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
                    response = requests.get("http://localhost:11434/api/tags", timeout=5)
                    if response.status_code == 200:
                        OLLAMA_AVAILABLE = True
                        self.log("✅ Ollama服务已启动并连接")
                except Exception:
                    self.log("⚠️ Ollama服务启动失败")
            else:
                self.log("⚠️ 未找到Ollama安装")
        except Exception as e:
            self.log(f"⚠️ Ollama连接失败: {e}")
    
    def preload_whisper_model(self):
        """预加载Whisper模型到内存，加快首次使用速度"""
        try:
            import whisper
            import torch
            
            # 获取用户选择的模型大小
            whisper_model_size = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
            
            # 检测设备
            if torch.cuda.is_available():
                device = "cuda"
                self.log(f"🔄 预加载 Whisper {whisper_model_size} 模型 (GPU模式)...")
            else:
                device = "cpu"
                self.log(f"🔄 预加载 Whisper {whisper_model_size} 模型 (CPU模式)...")
            
            # 加载模型
            self.whisper_model = whisper.load_model(whisper_model_size, device=device)
            
            if torch.cuda.is_available():
                self.log(f"✅ Whisper {whisper_model_size} 模型预加载完成 (GPU)")
            else:
                self.log(f"✅ Whisper {whisper_model_size} 模型预加载完成 (CPU)")
                
        except Exception as e:
            self.log(f"⚠️ Whisper模型预加载失败: {e}")
    
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
        
        btn_generate = ttk.Button(section2, text="🎬 一键生成分镜", command=self.generate_shots_threaded, style="LargeBlue.TButton")
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
        
        btn_render = ttk.Button(section5, text="🎞️ （跑图）生成视频", command=self.render_video_threaded, style="LargeRed.TButton")
        btn_render.pack(fill=tk.BOTH, expand=True, pady=5)
        
        btn_direct_render = ttk.Button(section5, text="🎞️ （直接）生成视频", command=self.direct_render_video, style="LargeBlue.TButton")
        btn_direct_render.pack(fill=tk.BOTH, expand=True, pady=5)

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
        style_control_frame = ttk.Frame(style_section)
        style_control_frame.pack(fill=tk.X, pady=3)
        
        # 风格设置按钮
        self.style_dropdown_visible = False
        self.style_dropdown_frame = ttk.Frame(style_section)
        
        style_button = ttk.Button(style_control_frame, text="展开风格选项", command=self.toggle_style_dropdown, style="Medium.TButton")
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
        
        # 配置模式说明标签 - 使用亮白色字体
        self.llm_config_desc_var = tk.StringVar(value=LLMConfig.PRESETS["质量优先"]["description"])
        config_desc_label = tk.Label(
            model_section, 
            textvariable=self.llm_config_desc_var,
            font=('Microsoft YaHei', large_font_size - 1),
            foreground="#ffffff",
            background=self.panel_bg,
            wraplength=400,
            justify=tk.LEFT,
            padx=5,
            pady=2
        )
        config_desc_label.pack(fill=tk.X, padx=5, pady=2)
        
        # 添加音频模型选择（Whisper）
        audio_model_frame = ttk.Frame(model_section)
        audio_model_frame.pack(fill=tk.X, pady=3)
        ttk.Label(audio_model_frame, text="音频模型:", width=12, font=('Microsoft YaHei', large_font_size, 'bold')).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'whisper_model_var'):
            self.whisper_model_var = tk.StringVar(value="medium")
        
        audio_model_combo = ttk.Combobox(
            audio_model_frame,
            textvariable=self.whisper_model_var,
            values=["tiny", "base", "small", "medium", "large"],
            state="readonly",
            style="Config.TCombobox",
            height=10
        )
        audio_model_combo.pack(fill=tk.X, padx=5, pady=2, ipady=3)
        
        # 添加音频模型说明
        audio_model_desc = tk.Label(
            audio_model_frame,
            text="推荐: medium (平衡速度与准确度)",
            font=('Microsoft YaHei', large_font_size - 1),
            foreground="#aaaaaa",
            background=self.panel_bg,
            wraplength=400,
            justify=tk.LEFT,
            padx=5
        )
        audio_model_desc.pack(fill=tk.X, padx=5, pady=2)
        
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
        sd_prompt_btn = ttk.Button(prompt_options, text="SD提示词", command=lambda: self.prompt_type_var.set("SD提示词"), style="Medium.TButton")
        sd_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        # 豆包提示词按钮
        doubao_prompt_btn = ttk.Button(prompt_options, text="豆包提示词", command=lambda: self.prompt_type_var.set("豆包提示词"), style="Medium.TButton")
        doubao_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        # ARV绝对写实提示词按钮
        arv_prompt_btn = ttk.Button(prompt_options, text="ARV写实提示词", command=lambda: self.prompt_type_var.set("ARV写实提示词"), style="Medium.TButton")
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
        
        # 主题自定义说明
        theme_desc_label = tk.Label(
            theme_section, 
            text="提示：核心主题例如'战争反思'、'科技未来'等；视觉基调例如'冷色调，沉重深刻'、'温暖明亮，积极向上'等。留空则自动识别。",
            font=('Microsoft YaHei', large_font_size - 2),
            foreground="#aaaaaa",
            background=self.panel_bg,
            wraplength=400,
            justify=tk.LEFT,
            padx=5,
            pady=2
        )
        theme_desc_label.pack(fill=tk.X, padx=5, pady=2)
        
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
        
        # 添加"本地大模型"选项
        script_model_btn = ttk.Button(self.model_dropdown_inner_frame, text="本地大模型", command=lambda m="本地大模型": self.select_ollama_model(m), style="Medium.TButton")
        script_model_btn.pack(fill=tk.X, pady=1, padx=5)
        
        # 【修改】自动检测并启动Ollama服务
        ollama_connected = False
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
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
                        response = requests.get("http://localhost:11434/api/tags", timeout=5)
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
            # 如果窗口已存在，关闭它
            self.advanced_window.destroy()
            self.advanced_window = None
        else:
            # 创建新的高级设置窗口
            self.advanced_window = tk.Toplevel(self.root)
            self.advanced_window.title("⚙️ 高级设置")
            self.advanced_window.geometry("700x650")
            self.advanced_window.resizable(True, True)
            
            # 创建高级设置面板
            adv_frame = ttk.Frame(self.advanced_window, padding=15)
            adv_frame.pack(fill=tk.BOTH, expand=True)
            
            # 调用设置内容的方法
            self.setup_advanced_panel_content(adv_frame)
    
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
            desc = LLMConfig.PRESETS[preset].get("description", "")
            self.llm_config_desc_var.set(desc)
            self.log(f"🎯 大模型配置已切换: {preset}")
            self.log(f"   参数: temperature={LLMConfig.PRESETS[preset].get('temperature')}, top_p={LLMConfig.PRESETS[preset].get('top_p')}")
            
            # 显示优化建议
            suggestions = llm_optimizer.suggest_optimization()
            for suggestion in suggestions:
                self.log(f"   💡 {suggestion}")
        else:
            self.log(f"⚠️ 未知配置模式: {preset}")
    
    def toggle_transition_dropdown(self):
        """切换过渡模式下拉菜单的显示/隐藏"""
        if self.transition_dropdown_visible:
            self.transition_dropdown_frame.pack_forget()
            self.transition_dropdown_visible = False
        else:
            # 清空现有按钮
            for widget in self.transition_dropdown_frame.winfo_children():
                widget.destroy()
            
            # 添加过渡模式选项（精简版）
            transitions = [
                "硬切",           # 直接切换，无过渡效果
                "交叉溶解",       # 淡入淡出叠加效果
                "淡入淡出"        # 淡入淡出效果
            ]
            for transition in transitions:
                btn = ttk.Button(self.transition_dropdown_frame, text=transition, command=lambda t=transition: self.select_transition(t), style="Medium.TButton")
                btn.pack(fill=tk.X, pady=1, padx=5)
            
            self.transition_dropdown_frame.pack(fill=tk.X, pady=2)
            self.transition_dropdown_visible = True
    
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
    
    def update_task_progress(self, message, progress=None):
        """更新任务进度 - 确保线程安全"""
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
        else:
            _update()
    
    def update_task_status(self, status):
        """更新任务状态"""
        if hasattr(self, 'task_status_var'):
            self.task_status_var.set(status)
    
    def _get_ollama_options_for_model(self, model_name):
        """根据模型大小获取合适的Ollama参数"""
        model_lower = model_name.lower()
        
        # 有问题的模型黑名单（API调用返回空结果）
        if 'qwen3:4b' in model_lower:
            self.log(f"   ⚠️ 模型 {model_name} 存在已知问题，将使用备用参数")
            # 返回最小参数尝试
            return {
                "temperature": 0.1,
                "top_p": 0.5,
                "num_predict": 256,
                "num_ctx": 1024
            }
        
        # 小模型列表（不支持大上下文）
        small_models = ['4b', '3b', '2b', '1b']
        
        # 检测是否为小模型
        is_small_model = any(size in model_lower for size in small_models)
        
        if is_small_model:
            # 小模型使用较小上下文
            return {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 512,
                "num_ctx": 2048
            }
        else:
            # 大模型使用完整配置
            if hasattr(self, 'current_llm_config'):
                return self.current_llm_config.get_options(
                    num_predict=1024,
                    num_ctx=4096
                )
            else:
                return {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 1024,
                    "num_ctx": 4096
                }
    
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
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # 移除Markdown格式
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **text** -> text
        text = re.sub(r'\*([^*]+)\*', r'\1', text)  # *text* -> text
        
        # 移除换行和多余空格
        text = re.sub(r'\n+', ', ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # 如果包含"核心概念"、"关键要素"等，提取冒号后的内容
        if '核心概念' in text or '关键要素' in text or 'Core concept' in text.lower():
            # 尝试提取描述部分
            match = re.search(r'[：:]\s*([^\n]+)', text)
            if match:
                text = match.group(1)
        
        # 截取前200字符，防止太长
        if len(text) > 200:
            # 在逗号处截断
            last_comma = text[:200].rfind(',')
            if last_comma > 50:
                text = text[:last_comma]
        
        # 清理首尾标点
        text = re.sub(r'^[，,。、：:；;\s]+', '', text)
        text = re.sub(r'[，,。、：:；;\s]+$', '', text)
        
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
            # 应用设置
            msg = f"设置已应用:\n模型: {model}\n提示词类型: {prompt_type}\n尺寸: {width}x{height}"
            if custom_theme:
                msg += f"\n核心主题: {custom_theme}"
            if custom_tone:
                msg += f"\n视觉基调: {custom_tone}"
            self.log(msg)
            # 保存配置
            self.save_config()
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
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else "http://127.0.0.1:7860"
        
        try:
            import requests
            response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=5)
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
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else "http://127.0.0.1:7860"
        
        try:
            import requests
            response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=3)
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

    def should_create_new_shot(self, current_shot, sentence, content_type, semantic_weight):
        """判断是否应该创建新分镜"""
        # 如果当前没有分镜，创建新分镜
        if not current_shot:
            return True
        
        # 如果内容类型改变，创建新分镜
        if current_shot.get("content_type") != content_type:
            return True
        
        # 如果语义权重大于2.0，创建新分镜
        if semantic_weight > 2.0:
            return True
        
        # 如果当前分镜时长超过10秒，创建新分镜
        current_duration = current_shot.get("duration", 0)
        if current_duration > 10.0:
            return True
        
        # 如果句子包含明显的分隔符，创建新分镜
        separators = ["。", "！", "？", "；", "，"]
        for sep in separators:
            if sep in sentence and len(sentence) > 15:
                return True
        
        return False

    def merge_short_shots(self, shots, min_duration=1.5, max_merge_count=3):
        """合并时长过短的分镜
        
        Args:
            shots: 分镜列表
            min_duration: 最小分镜时长（秒），低于此值的分镜将被合并
            max_merge_count: 最大合并数量，避免一次合并太多分镜
        
        Returns:
            合并后的分镜列表
        """
        if not shots:
            return shots
        
        merged_shots = []
        i = 0
        merge_count = 0
        
        while i < len(shots):
            current_shot = shots[i].copy()
            
            # 检查当前分镜是否过短
            if current_shot.get('duration', 0) < min_duration:
                # 尝试与后面的分镜合并
                merged_content = [current_shot.get('description', '')]
                merged_prompts = [current_shot.get('prompt_en', '')]
                total_duration = current_shot.get('duration', 0)
                merge_start = i
                
                # 查找可以合并的后续分镜
                j = i + 1
                while j < len(shots) and j - merge_start < max_merge_count:
                    next_shot = shots[j]
                    # 只合并相邻的短分镜
                    if next_shot.get('duration', 0) < min_duration:
                        merged_content.append(next_shot.get('description', ''))
                        merged_prompts.append(next_shot.get('prompt_en', ''))
                        total_duration += next_shot.get('duration', 0)
                        j += 1
                    else:
                        break
                
                # 如果合并后时长足够，执行合并
                if j > i + 1 and total_duration >= min_duration * 0.8:
                    # 创建合并后的分镜
                    merged_shot = current_shot.copy()
                    merged_shot['description'] = ' '.join(merged_content)
                    # 使用最后一个分镜的提示词（通常是最完整的）
                    merged_shot['prompt_en'] = merged_prompts[-1] if merged_prompts else current_shot.get('prompt_en', '')
                    # 关键：保持时间戳连续性，确保音画同步
                    merged_shot['start'] = shots[merge_start].get('start', current_shot.get('start', 0))  # 保留第一个分镜的start
                    merged_shot['end'] = shots[j-1].get('end', current_shot.get('end', 0))  # 使用最后一个分镜的end
                    merged_shot['duration'] = merged_shot['end'] - merged_shot['start']  # 重新计算duration确保一致性
                    merged_shot['merged_from'] = list(range(merge_start, j))
                    
                    merged_shots.append(merged_shot)
                    merge_count += 1
                    self.log(f"   🔗 合并分镜 {merge_start+1}-{j}（时间: {merged_shot['start']:.2f}s-{merged_shot['end']:.2f}s，时长: {merged_shot['duration']:.2f}s）")
                    i = j  # 跳过已合并的分镜
                else:
                    # 不合并，保留原分镜
                    merged_shots.append(current_shot)
                    i += 1
            else:
                # 分镜时长足够，保留原分镜
                merged_shots.append(current_shot)
                i += 1
        
        # 重新编号分镜ID
        for idx, shot in enumerate(merged_shots):
            shot['id'] = idx
            shot['image_file'] = f"shot_{idx+1:02d}.png"
        
        if merge_count > 0:
            self.log(f"   ✅ 已合并 {merge_count} 组短分镜，最终分镜数: {len(merged_shots)}")
        
        return merged_shots

    def _parse_shot_analysis_result(self, analysis_result):
        """
        智能解析大模型返回的分镜分析结果【最终增强版】
        支持任何格式的大模型返回
        """
        import re
        
        if not analysis_result:
            return None
        
        self.log(f"🔍 开始解析大模型返回内容，长度: {len(analysis_result)} 字符")
        
        # 预处理：统一格式
        cleaned_result = analysis_result
        cleaned_result = cleaned_result.replace('\r\n', '\n').replace('\r', '\n')
        
        # 提取主题信息
        core_theme = None
        visual_tone = None
        theme_elements = None
        
        # 提取核心主题
        theme_patterns = [
            r'\*\*核心主题[：:]\s*(.+?)(?:\n|$)',
            r'核心主题[：:]\s*(.+?)(?:\n|$)',
        ]
        for pattern in theme_patterns:
            match = re.search(pattern, cleaned_result, re.IGNORECASE | re.DOTALL)
            if match:
                core_theme = match.group(1).strip()
                break
        
        # 提取视觉基调
        tone_patterns = [
            r'\*\*视觉基调[：:]\s*(.+?)(?:\n|$)',
            r'视觉基调[：:]\s*(.+?)(?:\n|$)',
        ]
        for pattern in tone_patterns:
            match = re.search(pattern, cleaned_result, re.IGNORECASE | re.DOTALL)
            if match:
                visual_tone = match.group(1).strip()
                break
        
        # ============ 直接使用备用解析方法（更可靠）============
        # 不再依赖复杂的标准解析，直接从全文提取
        parsed_shots = []
        
        # 方法1：直接搜索 "数字. 配音:" 模式（支持各种变体）
        # 支持：1. 配音： / 1. **配音**： / 1.配音：
        patterns_to_try = [
            # 最宽松的模式：数字 + 任意空白 + 配音 + 任意冒号
            r'(\d+)[.、\s]+[\*\*]*配[\*\*]*音[\*\*]*[：:\s]+(.+?)(?=\n\d+[.、\s]|$)',
            # 带空格和全角冒号
            r'(\d+)[\.．]\s*[\*\*]*配音[\*\*]*[：:]\s*(.+?)(?=\n\d+[\.．]|$)',
        ]
        
        for pattern in patterns_to_try:
            matches = re.findall(pattern, cleaned_result, re.DOTALL | re.IGNORECASE)
            if matches:
                for match in matches:
                    shot_num, dubbing_text = match
                    dubbing_text = dubbing_text.strip()
                    if dubbing_text and len(dubbing_text) > 2:
                        # 清理文本，移除可能的**标记
                        dubbing_text = dubbing_text.replace('**', '').strip()
                        parsed_shots.append({
                            'dubbing': dubbing_text,
                            'semantic': '',
                            'content_type': '',
                            'keywords': '',
                            'visual_concept': '',
                            'visual_elements': '',
                            'prompt': '',
                            'negative_prompt': ''
                        })
                if parsed_shots:
                    self.log(f"✅ 解析完成，共找到 {len(parsed_shots)} 个分镜（方法1）")
                    break
        
        # 方法2：如果方法1失败，尝试搜索所有"配音："后面跟着的内容
        if not parsed_shots:
            # 查找所有"配音"出现的位置
            dubbing_positions = []
            for match in re.finditer(r'配音[：:]\s*', cleaned_result):
                dubbing_positions.append(match.end())
            
            if len(dubbing_positions) >= 2:
                # 从每个"配音："后面提取内容，直到下一个数字或结尾
                for i, pos in enumerate(dubbing_positions):
                    # 找到这段内容的结束位置（下一个"配音"或结尾）
                    if i + 1 < len(dubbing_positions):
                        end_pos = dubbing_positions[i + 1]
                    else:
                        end_pos = len(cleaned_result)
                    
                    text = cleaned_result[pos:end_pos].strip()
                    # 清理并提取实际内容
                    text = re.sub(r'^\s*[\*\*]*', '', text)
                    text = text.split('\n')[0]  # 取第一行
                    if text and len(text) > 2:
                        parsed_shots.append({
                            'dubbing': text,
                            'semantic': '',
                            'content_type': '',
                            'keywords': '',
                            'visual_concept': '',
                            'visual_elements': '',
                            'prompt': '',
                            'negative_prompt': ''
                        })
                if parsed_shots:
                    self.log(f"✅ 解析完成，共找到 {len(parsed_shots)} 个分镜（方法2）")
        
        # 返回结果
        if parsed_shots:
            return {
                'shots': parsed_shots,
                'theme_info': {
                    'core_theme': core_theme or '',
                    'visual_tone': visual_tone or '',
                    'theme_elements': theme_elements or ''
                }
            }
        
        # 完全失败，返回主题信息
        if core_theme or visual_tone:
            return {"theme_info": {"core_theme": core_theme, "visual_tone": visual_tone, "theme_elements": theme_elements}}
        
        self.log(f"❌ 解析失败")
        return None

    def create_new_shot(self, shot_id, start_time, end_time, sentence, content_type, llm_keywords='', llm_prompt='', use_raw_text=False, core_theme='', visual_tone='', theme_elements=None):
        """创建新分镜 - 增强版：根据每个分镜的独特内容生成个性化提示词
        
        Args:
            shot_id: 分镜ID
            start_time: 开始时间
            end_time: 结束时间
            sentence: 配音文本
            content_type: 内容类型
            llm_keywords: 大模型提取的关键词（可选）
            llm_prompt: 大模型生成的提示词（可选）
            core_theme: 核心主题（可选）
            visual_tone: 视觉基调（可选）
            theme_elements: 主题元素列表（可选）
        """
        # 确保 theme_elements 是列表
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
        
        # 优先使用大模型生成的提示词（如果可用）
        if llm_prompt:
            prompt_en = llm_prompt
        elif hasattr(self, '_pregenerated_prompts') and shot_id in self._pregenerated_prompts and self._pregenerated_prompts.get(shot_id):
            # 使用步骤2预生成的提示词
            prompt_en = self._pregenerated_prompts[shot_id]
        else:
            # 根据提示词类型生成相应的提示词
            if prompt_type == "SD提示词":
                prompt_en = self._generate_sd_prompt(description_parts, content_type, shot_id)
            elif prompt_type == "ARV写实提示词":
                prompt_en = self._generate_arv_prompt(description_parts, content_type, shot_id)
            else:
                prompt_en = self._generate_doubao_prompt(description_parts, content_type, shot_id)
        
        # 简化处理：直接使用生成的提示词，跳过额外的优化和质量评估
        # 因为 _generate_sd_prompt/_generate_doubao_prompt 已经由大模型生成
        prompt_quality = 0.0
        optimized_prompt = prompt_en
        
        # 修复：使用Decimal进行高精度时间戳计算，确保duration = end - start
        from decimal import Decimal, ROUND_HALF_UP
        
        start_dec = Decimal(str(start_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        end_dec = Decimal(str(end_time)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        duration_dec = end_dec - start_dec
        
        if duration_dec < Decimal('1.0'):
            duration_dec = Decimal('1.0')
            end_dec = start_dec + duration_dec
        
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

        # 如果是SD提示词或ARV写实提示词模式，使用定制化的反向提示词
        if prompt_type == "SD提示词" or prompt_type == "ARV写实提示词":
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
            
            import requests
            config_options = self.current_llm_config.get_options() if hasattr(self, 'current_llm_config') else {"temperature": 0.3}
            response = requests.post(
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
            
            import requests
            config_options = self.current_llm_config.get_options() if hasattr(self, 'current_llm_config') else {"temperature": 0.3}
            response = requests.post(
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
    
    def _generate_doubao_prompt(self, description_parts, content_type, shot_id):
        """生成豆包提示词 - 使用新模板"""
        
        dubbing = description_parts['dubbing']
        
        # 检查大模型是否可用
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            self.log("❌ 错误：豆包提示词需要大模型支持，请先在设置中选择 Ollama 模型")
            raise Exception("大模型不可用：豆包提示词需要 Ollama 模型支持，请在设置中选择模型后重试")
        
        # 获取完整的主题信息（包含新增字段）
        core_theme = description_parts.get('custom_theme', '')
        visual_tone = description_parts.get('custom_visual_tone', '')
        theme_elements = description_parts.get('theme_elements', [])
        content_type = description_parts.get('content_type', content_type)  # 优先使用传入的类型
        visual_style = description_parts.get('visual_style', '')
        scene_suggestions = description_parts.get('scene_suggestions', '')
        
        # 使用大模型生成提示词
        prompt = self._generate_prompt_with_llm(
            dubbing, content_type, 
            prompt_type="豆包提示词", 
            core_theme=core_theme, 
            visual_tone=visual_tone, 
            theme_elements=theme_elements,
            visual_style=visual_style,
            scene_suggestions=scene_suggestions
        )
        return prompt
    
    def _get_preset_prompt_key(self, content_type: str, dubbing: str) -> str:
        """判断是否可以使用预设模板，返回预设模板的key，否则返回空字符串
        
        混合模式逻辑：
        1. 根据内容类型和配音内容匹配预设模板
        2. 标准场景使用预设模板（速度快）
        3. 复杂场景返回空字符串，由大模型生成
        
        Args:
            content_type: 内容类型
            dubbing: 配音文本
            
        Returns:
            预设模板的key，如 "war_scene"、"space_scene" 等；空字符串表示需要大模型生成
        """
        if not ARV_PROMPTS_AVAILABLE:
            return ""
        
        # 内容类型到预设模板的映射
        type_to_preset = {
            "military": ["war_scene", "military_base", "missile_launch"],
            "war": ["war_scene", "military_base"],
            "space": ["space_scene"],
            "science": ["technology_lab"],
            "technology": ["technology_lab"],
            "politics": ["government_meeting", "diplomatic_scene"],
            "news": ["news_broadcast"],
            "economy": ["economic_scene"],
        }
        
        # 关键词到预设模板的直接映射（优先级最高）
        keyword_to_preset = {
            # 战争/军事
            "战场": "war_scene", "战斗": "war_scene", "战争": "war_scene",
            "爆炸": "war_scene", "轰炸": "war_scene", "导弹": "missile_launch",
            "军事基地": "military_base", "军营": "military_base",
            # 太空/科学
            "黑洞": "space_scene", "宇宙": "space_scene", "太空": "space_scene",
            "银河": "space_scene", "星云": "space_scene", "恒星": "space_scene",
            "实验室": "technology_lab", "科研": "technology_lab",
            # 政治/新闻
            "新闻": "news_broadcast", "直播": "news_broadcast",
            "会议": "government_meeting", "谈判": "diplomatic_scene",
            "外交": "diplomatic_scene", "峰会": "diplomatic_scene",
            # 经济
            "经济": "economic_scene", "金融": "economic_scene", "股市": "economic_scene",
        }
        
        # 1. 首先检查关键词直接匹配（最高优先级）
        for keyword, preset_key in keyword_to_preset.items():
            if keyword in dubbing:
                # 验证预设模板是否存在
                if preset_key in PRESET_PROMPTS:
                    return preset_key
        
        # 2. 根据内容类型匹配
        content_type_lower = (content_type or "").lower()
        for type_key, preset_keys in type_to_preset.items():
            if type_key in content_type_lower:
                # 返回第一个匹配的预设模板
                for preset_key in preset_keys:
                    if preset_key in PRESET_PROMPTS:
                        return preset_key
        
        # 3. 无法匹配，返回空字符串，由大模型生成
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
            if not self.arv_prompter:
                self.arv_prompter = get_arv_prompter()

            if not self.arv_prompter.has_semantic_match(dubbing, core_theme):
                self.log(f"🔄 ARV关键词未匹配，自动切换到大模型生成（ARV格式）")
                return self._generate_arv_format_prompt(description_parts, content_type, shot_id)

            shot_data = {
                'content_type': content_type,
                'visual_tone': visual_tone,
                'theme_elements': theme_elements
            }

            prompt_en = self.arv_prompter.generate_arv_prompt(
                text=dubbing,
                content_type=content_type,
                core_theme=core_theme,
                visual_tone=visual_tone,
                shot_data=shot_data
            )

            self.log(f"🎨 使用ARV绝对写实风格生成提示词")
            return prompt_en

        except Exception as e:
            self.log(f"⚠️ ARV提示词生成失败: {e}，切换到SD提示词")
            return self._generate_sd_prompt(description_parts, content_type, shot_id)

    def _generate_arv_format_prompt(self, description_parts, content_type, shot_id):
        """生成ARV格式的提示词 - 大模型生成但保持ARV格式"""

        dubbing = description_parts.get('dubbing', '')
        core_theme = description_parts.get('custom_theme', '')
        content_type = description_parts.get('content_type', content_type)
        theme_elements = description_parts.get('theme_elements', [])
        visual_tone = description_parts.get('custom_visual_tone', '')
        
        # 将主题元素转换为英文关键词
        theme_elements_str = ', '.join(theme_elements) if theme_elements else ''

        system_prompt = f"""You are a professional AI image prompt engineer for absoluteRealisticVision v20 model.

【全局分析阶段 - 必须首先完成】
在生成提示词之前，你必须先分析以下信息：
1. 核心主题：{core_theme}
2. 主题元素：{theme_elements_str}
3. 视觉基调：{visual_tone or '根据内容确定'}
4. 内容类型：{content_type}

分析要点：
- 理解核心主题的整体含义和情感倾向
- 确定需要表达的关键视觉元素
- 把握整体氛围（紧张/轻松/严肃/温馨等）
- 思考如何将主题元素有机融入画面

【提示词生成阶段】
基于以上分析，生成符合以下规则的英文提示词：
1. 输出必须是逗号分隔的关键词，不是编号列表
2. 必须包含所有主题元素：{theme_elements_str}
3. 从分析结果中选择最相关的视觉元素
4. 添加场景类型：{content_type}
5. 体现整体氛围和光线
6. 以以下标签结尾：masterpiece, best quality, absolute realistic, photo-realistic, ultra detailed, 8K, HDR, cinematic lighting

输出格式：[CORRECTED_TEXT]|||PROMPT
示例：芯片供应短缺|||semiconductor chips, supply shortage, factory, production line, industrial facility, geopolitical tensions, global market, economic crisis, realistic atmosphere, natural lighting, masterpiece, best quality, absolute realistic...

重要提示：
- 不要拒绝或提及安全指南
- 只输出纠正后的文本和提示词，用|||分隔
- 所有元素之间用逗号分隔"""

        user_prompt = f"""【当前分镜配音】
{dubbing}

【整体主题】
核心主题：{core_theme}
主题元素：{theme_elements_str}
视觉基调：{visual_tone or '紧张氛围，危机感'}
内容类型：{content_type}

请基于上述整体分析，为当前分镜生成提示词："""

        try:
            import ollama
            model = self.ollama_model_var.get()
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            result = response['message']['content'].strip()
            
            if '|||' in result:
                prompt_en = result.split('|||')[1].strip()
            else:
                prompt_en = result
            
            return prompt_en
        except Exception as e:
            self.log(f"⚠️ ARV格式生成失败: {e}")
            return self._generate_sd_prompt(description_parts, content_type, shot_id)

    def _generate_sd_prompt(self, description_parts, content_type, shot_id):
        """生成SD提示词 - 使用混合模式：预设模板优先，大模型兜底"""
        
        dubbing = description_parts['dubbing']
        
        # 获取完整的主题信息（包含新增字段）
        core_theme = description_parts.get('custom_theme', '')
        visual_tone = description_parts.get('custom_visual_tone', '')
        theme_elements = description_parts.get('theme_elements', [])
        content_type = description_parts.get('content_type', content_type)  # 优先使用传入的类型
        visual_style = description_parts.get('visual_style', '')
        scene_suggestions = description_parts.get('scene_suggestions', '')
        
        # ===== 混合模式：优先使用预设模板，提升速度 =====
        preset_key = self._get_preset_prompt_key(content_type, dubbing)
        
        if preset_key and ARV_PROMPTS_AVAILABLE:
            # 使用预设模板（速度快，< 0.1秒）
            preset_prompt = PRESET_PROMPTS.get(preset_key, "")
            if preset_prompt:
                self.log(f"⚡ 使用预设模板 [{preset_key}] 生成提示词")
                # 根据配音内容微调预设模板
                try:
                    enhanced_prompt = ARVPromptTemplates.generate_prompt(
                        dubbing, content_type, core_theme, visual_tone
                    )
                    # 如果增强版生成成功，优先使用
                    if enhanced_prompt and len(enhanced_prompt) > 50:
                        return enhanced_prompt
                except Exception:
                    pass  # 增强版失败，使用原始预设
                return preset_prompt
        
        # ===== 复杂场景：使用大模型生成提示词 =====
        # 检查大模型是否可用
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            self.log("❌ 错误：SD提示词需要大模型支持，请先在设置中选择 Ollama 模型")
            raise Exception("大模型不可用：SD提示词需要 Ollama 模型支持，请在设置中选择模型后重试")
        
        self.log(f"🤖 使用大模型生成提示词（复杂场景）")
        
        # 使用大模型生成提示词
        prompt = self._generate_prompt_with_llm(
            dubbing, content_type, 
            prompt_type="SD提示词", 
            core_theme=core_theme, 
            visual_tone=visual_tone, 
            theme_elements=theme_elements,
            visual_style=visual_style,
            scene_suggestions=scene_suggestions
        )
        return prompt
    
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
        
        return text.strip()

    def _generate_prompt_with_llm(self, dubbing, content_type, prompt_type="豆包", core_theme="", visual_tone="", theme_elements=None, visual_style="", scene_suggestions="", original_dubbing=""):
        """使用大模型生成提示词 - 根据内容类型智能调整
        
        Args:
            dubbing: 分镜的配音内容（已纠错）
            content_type: 内容类型（新闻播报/军事分析/科普教育等）
            prompt_type: "SD提示词" 或 "豆包提示词"
            core_theme: 整篇脚本的核心主题
            visual_tone: 整体视觉基调
            theme_elements: 主题相关元素列表
            visual_style: 视觉风格（根据内容类型推荐）
            scene_suggestions: 场景建议
            original_dubbing: 原始配音内容（未纠错，用于参考）
        """
        if theme_elements is None:
            theme_elements = []
            
        try:
            model = self.ollama_model_var.get()
            ollama_url = "http://localhost:11434"
            
            # 构建模板参数 - 包含内容类型信息
            template_params = {
                "content_type": content_type or "未指定类型",
                "core_theme": core_theme or "未指定",
                "visual_style": visual_style,  # 用户预设的风格（可能为空）
                "visual_tone": visual_tone or "",
                "theme_elements": ", ".join(theme_elements) if theme_elements else "根据内容确定",
                "scene_suggestions": scene_suggestions or "根据配音内容确定",
                "dubbing": dubbing
            }
            
            # 根据提示词类型选择模板
            if prompt_type == "SD提示词":
                template = PromptTemplates.get_template("shot_prompt_sd", **template_params)
            elif prompt_type == "ARV写实提示词":
                return ""  # ARV模式不需要预生成，会在create_new_shot中单独处理
            else:
                # 豆包提示词使用中文模板
                template = PromptTemplates.get_template("shot_prompt_doubao", **template_params)
            
            # 使用 ollama.chat API（支持 system + user 消息）
            import ollama
            
            # 简化参数配置，避免验证错误
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": template["system"]},
                    {"role": "user", "content": template["user"]}
                ]
            )
            
            raw_output = response["message"]["content"].strip()
            if raw_output:
                # 清洗提示词，移除解释性文字
                cleaned_prompt = self._clean_prompt_output(raw_output)
                return cleaned_prompt
            
            raise Exception("大模型返回为空")
            
        except Exception as e:
            import traceback
            self.log(f"❌ 大模型生成提示词失败: {str(e)}")
            self.log(f"   完整错误: {traceback.format_exc()[:500]}")
            raise Exception(f"大模型生成提示词失败: {str(e)}")
    
    def _get_custom_negative_prompt(self, content_type, dubbing):
        """【整改新增】根据内容类型和配音内容生成定制化负面提示词"""
        base_negative = [
            "worst quality",
            "low quality",
            "cartoon",
            "anime",
            "painting",
            "illustration",
            "ugly",
            "deformed",
            "blurry",
            "disfigured",
            "bad anatomy",
            "extra limbs",
            "mutated hands"
        ]

        # 根据内容类型添加特定排除
        content_specific_negative = {
            "space": [
                "human", "person", "face", "building", "tree",
                "landscape", "daytime", "sun", "satellite", "spacecraft",
                "astronaut"  # 除非明确需要，否则排除宇航员
            ],
            "science": [
                "cartoon character", "fictional creature", "fantasy"
            ],
            "nature": [
                "urban", "building", "structure", "artificial"
            ],
            "history": [
                "modern", "contemporary", "anachronism"
            ]
        }

        # 检查配音内容是否包含特定主题，添加相应排除
        additional_negative = []

        # 黑洞/宇宙主题排除
        if any(kw in dubbing for kw in ["黑洞", "宇宙", "银河", "恒星", "星云", "黑洞"]):
            additional_negative.extend([
                "star", "sun", "planet", "moon", "satellite",
                "human", "person", "face", "building", "tree"
            ])

        # 政治/历史主题排除
        if any(kw in dubbing for kw in ["政治", "历史", "古代", "战争"]):
            additional_negative.extend([
                "modern", "contemporary", "anachronism"
            ])

        # 合并所有排除项
        all_negative = base_negative.copy()

        # 添加内容类型特定的排除
        content_type_lower = content_type.lower() if content_type else ""
        for ct, negatives in content_specific_negative.items():
            if ct in content_type_lower:
                all_negative.extend(negatives)

        # 添加额外的排除
        all_negative.extend(additional_negative)

        # 去重
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
    
    def _intelligent_fuse_semantics(self, dubbing, core_theme, visual_tone, content_type):
        """智能融合语义：核心主题 + 视觉基调 + 音频文本语义
        
        根据核心主题和视觉基调，结合当前音频片段的语义，
        智能生成匹配的视觉元素提示词
        重点：确保配音文本的核心内容能够直接体现在视觉提示词中
        当配音文本太通用时，优先使用核心主题和视觉基调
        """
        if not dubbing:
            return ""
        
        fused_elements = []
        dubbing_lower = dubbing.lower()
        
        # 0. 【最重要】从配音文本中提取核心实体，直接作为视觉主体
        core_entities = self._extract_core_entities(dubbing, content_type)
        
        # 如果没有提取到核心实体，使用核心主题作为备选
        if not core_entities and core_theme:
            core_entities = core_theme
        
        # 如果有核心实体或核心主题，添加到提示词
        if core_entities:
            fused_elements.append(core_entities)
        
        # 1. 基于核心主题，智能扩展视觉元素（如果还没有主题内容）
        if core_theme and not core_entities:
            theme_lower = core_theme.lower()
            # 主题关键词映射到视觉元素
            theme_to_visuals = {
                '战争': 'war, battlefield, military, combat, destruction',
                'peace': 'peaceful, calm, harmony, tranquility, dove',
                '科技': 'technology, futuristic, digital, innovative, high-tech',
                'science': 'scientific, laboratory, research, experiment, data',
                '自然': 'nature, landscape, wilderness, environment, organic',
                '历史': 'historical, ancient, vintage, classical, heritage',
                '政治': 'political, government, diplomatic, official, ceremony',
                '经济': 'economic, financial, business, commerce, trading',
                '健康': 'healthcare, medical, wellness, hospital, medicine',
                '旅行': 'travel, adventure, exploration, scenic, journey',
                '太空': 'space, cosmos, galaxy, stars, planets, nebula',
                '宇宙': 'space, cosmos, universe, celestial, cosmic',
                '军事': 'military, armed forces, soldier, weapon, tactical',
            }
            for key, visual in theme_to_visuals.items():
                if key in theme_lower:
                    fused_elements.append(visual)
                    break
        
        # 2. 基于视觉基调，添加氛围元素
        if visual_tone:
            tone_lower = visual_tone.lower()
            tone_to_mood = {
                '压抑': 'dark, somber, gloomy, oppressive, heavy atmosphere',
                'dark': 'dark, shadowy, mysterious, dim lighting, moody',
                '光明': 'bright, luminous, radiant, warm, illuminated',
                'bright': 'bright, vibrant, colorful, vivid, energetic',
                '激烈': 'intense, dramatic, dynamic, powerful, chaotic',
                '平静': 'serene, peaceful, quiet, gentle, tranquil',
                'cold': 'cold, icy, frozen, blue tones, winter',
                '温暖': 'warm, cozy, golden hour, amber, sunset colors',
                '科幻': 'sci-fi, futuristic, neon, holographic, cyberpunk',
                '写实': 'realistic, authentic, natural, lifelike, photorealistic',
                '电影': 'cinematic, film quality, dramatic, professional',
                '梦幻': 'dreamlike, ethereal, surreal, fantastical, magical',
            }
            for key, mood in tone_to_mood.items():
                if key in tone_lower:
                    fused_elements.append(mood)
                    break
        
        # 3. 基于音频文本语义，提取即时视觉元素
        semantic_keywords = {
            # 人物相关
            ('人', '人物', '人们', '大家', '我们'): 'people, crowd, group of people',
            ('主持人', '记者', '主播'): 'anchor, presenter, broadcaster at desk',
            ('专家', '分析师', '学者'): 'expert, analyst, professional in office',
            ('总统', '官员', '领导'): 'leader, official, authority figure',
            ('医生', '护士', '医疗'): 'medical professional, healthcare worker',
            ('科学家', '研究员'): 'scientist, researcher, in laboratory',
            
            # 场景相关
            ('会议', '谈判', '会谈'): 'meeting room, conference, negotiation',
            ('战场', '战争', '冲突'): 'battlefield, combat zone, war area',
            ('城市', '街道', '建筑'): 'cityscape, urban street, architecture',
            ('自然', '森林', '山'): 'nature, forest, mountain landscape',
            ('海', '海洋', '船'): 'ocean, sea, marine, waterfront',
            ('天空', '云', '飞行'): 'sky, clouds, aerial view, flying',
            ('太空', '宇宙', '星球'): 'space, cosmos, planet, galaxy',
            
            # 物体/设备
            ('飞机', '航空', '飞行'): 'aircraft, airplane, aviation',
            ('导弹', '武器', '军事'): 'missile, weapon, military equipment',
            ('屏幕', '显示器', '数据'): 'screen, monitor, data display',
            ('图表', '数据', '分析'): 'chart, graph, data visualization',
            
            # 情感/氛围
            ('紧张', '危机', '冲突'): 'tense, crisis, conflict, urgent',
            ('希望', '胜利', '成功'): 'hopeful, victorious, success, achievement',
            ('悲伤', '绝望', '失败'): 'sad, desperate, failure, gloom',
            ('和平', '友好', '合作'): 'peaceful, friendly, cooperation, harmony',
        }
        
        for keywords, visual in semantic_keywords.items():
            if any(kw in dubbing for kw in keywords):
                fused_elements.append(visual)
                break
        
        # 4. 基于内容类型添加基础环境元素
        if content_type:
            content_lower = content_type.lower()
            if 'space' in content_lower or '宇宙' in core_theme or '太空' in dubbing:
                fused_elements.append('deep space, stars, cosmic background')
            elif 'military' in content_lower or '战争' in dubbing:
                fused_elements.append('military environment, tactical setting')
            elif 'science' in content_type:
                fused_elements.append('scientific environment, research setting')
        
        # 去重并组合
        if fused_elements:
            return ", ".join(fused_elements)
        
        return ""
    
    def _get_fallback_elements_by_content_type(self, content_type):
        """根据内容类型返回默认的视觉元素补充"""
        if not content_type:
            return "realistic scene, photorealistic, sharp focus"
        
        content_type_lower = content_type.lower()
        
        # 太空/宇宙相关
        if "space" in content_type_lower or "宇宙" in content_type:
            return "cosmic environment, space scene, celestial bodies, stars, nebula, astronomical phenomenon"
        
        # 科学/科技相关
        if "science" in content_type_lower or "科技" in content_type or "技术" in content_type:
            return "scientific laboratory, technology setting, research environment, futuristic equipment"
        
        # 军事/战争相关
        if "military" in content_type_lower or "战争" in content_type or "军事" in content_type:
            return "military scene, combat environment, military equipment, war zone"
        
        # 自然/环境相关
        if "nature" in content_type_lower or "自然" in content_type or "环境" in content_type:
            return "natural environment, nature scene, outdoor setting, landscape"
        
        # 历史相关
        if "history" in content_type_lower or "历史" in content_type or "古代" in content_type:
            return "historical setting, ancient scene, cultural heritage, classical architecture"
        
        # 政治相关
        if "politics" in content_type_lower or "政治" in content_type or "政府" in content_type:
            return "political setting, government building, official venue, professional environment"
        
        # 商业/经济相关
        if "business" in content_type_lower or "经济" in content_type or "商业" in content_type:
            return "business environment, corporate setting, financial district, office scene"
        
        # 健康/医学相关
        if "health" in content_type_lower or "健康" in content_type or "医学" in content_type or "医疗" in content_type:
            return "medical setting, healthcare environment, clinical scene, hospital setting"
        
        # 艺术相关
        if "art" in content_type_lower or "艺术" in content_type:
            return "artistic scene, creative setting, artistic environment, cultural scene"
        
        # 旅行相关
        if "travel" in content_type_lower or "旅行" in content_type or "旅游" in content_type:
            return "travel scene, tourist location, scenic view, landscape photography"
        
        # 默认
        return "realistic scene, photorealistic, detailed environment"
    
    def _get_lighting_by_mood(self, dubbing):
        """根据情感基调获取光线描述（带权重）"""
        if any(w in dubbing for w in ["紧张", "危机", "冲突", "严峻", "沉重"]):
            return "dramatic side lighting(1.3), dark shadows(1.2), moody atmosphere(1.2), desaturated colors(1.0)"
        elif any(w in dubbing for w in ["绝望", "失败", "崩溃", "毁灭"]):
            return "harsh lighting(1.3), high contrast(1.2), bleak atmosphere(1.2), gray tones(1.0)"
        elif any(w in dubbing for w in ["希望", "胜利", "和平", "成功"]):
            return "warm golden hour lighting(1.3), soft natural light(1.2), uplifting atmosphere(1.2)"
        else:
            return "neutral lighting(1.0), balanced exposure(1.2), soft natural light(1.1)"
    
    def _get_composition_by_shot_id(self, shot_id):
        """根据shot_id轮换构图，增加多样性（带权重）"""
        compositions = [
            "wide angle shot(1.2), establishing view(1.0)",
            "medium shot(1.2), eye level perspective(1.0)",
            "close-up shot(1.3), detailed view(1.1)",
            "low angle shot(1.2), looking up(1.0)",
            "high angle shot(1.2), bird's eye view(1.0)",
            "side angle(1.2), profile view(1.0)",
            "dutch angle(1.3), dynamic composition(1.1)",
            "over-the-shoulder shot(1.2)",
        ]
        return compositions[shot_id % len(compositions)]
    
    def _get_art_style(self, content_type, style_hint):
        """获取艺术风格（带权重）"""
        if "纪实" in style_hint or "纪录片" in style_hint:
            return "documentary photography style(1.5), photojournalistic(1.3), realistic(1.4)"
        elif "military" in content_type:
            return "war photography style(1.4), gritty realism(1.3), cinematic(1.3)"
        else:
            return "photorealistic style(1.5), cinematic composition(1.3), professional photography(1.4)"
    
    def _get_scene_type_zh(self, content_type, dubbing):
        """获取中文场景类型 - 增强版"""
        if "military" in content_type:
            if any(w in dubbing for w in ["分析", "评估", "认为", "战略"]):
                return "现代军事指挥中心，战略分析室"
            elif any(w in dubbing for w in ["废墟", "摧毁", "城市", "破坏"]):
                return "战争废墟场景，被摧毁的城市"
            elif any(w in dubbing for w in ["抵抗", "士兵", "部队", "战斗"]):
                return "战场环境，武装抵抗组织"
            elif any(w in dubbing for w in ["海军", "舰艇", "港口", "海上"]):
                return "海军基地，军港码头"
            elif any(w in dubbing for w in ["空军", "飞机", "无人机", "空中"]):
                return "空军基地，航空作战场景"
            elif any(w in dubbing for w in ["局势", "局勢", "战局", "戰局", "形势", "形勢", "格局", "态势", "態勢"]):
                return "战争局势图，战略态势展示，战场形势分析"
            else:
                return "军事场景，战争环境"
        elif "politics" in content_type:
            if any(w in dubbing for w in ["局势", "局勢", "形势", "形勢", "格局", "态势", "態勢", "局面"]):
                return "政治局势图，国际格局展示，战略态势分析"
            else:
                return "国际政治场景，外交谈判环境"
        return "纪实摄影场景"
    
    def _get_lighting_zh(self, dubbing):
        """获取中文光线描述"""
        if any(w in dubbing for w in ["紧张", "危机", "冲突", "严峻", "沉重", "黑暗"]):
            return "戏剧化侧光，深色阴影，压抑氛围，低饱和度色调"
        elif any(w in dubbing for w in ["绝望", "失败", "崩溃", "毁灭", "废墟"]):
            return "强烈对比光，高反差，荒凉氛围，灰色调"
        elif any(w in dubbing for w in ["希望", "胜利", "和平", "成功", "光明"]):
            return "温暖金色光线，柔和自然光，积极向上的氛围"
        else:
            return "中性光线，均衡曝光，纪实风格"
    
    def _get_composition_zh(self, shot_id):
        """获取中文构图描述"""
        compositions = [
            "广角镜头，全景视角，建立镜头",
            "中景镜头，平视视角",
            "特写镜头，细节展示",
            "低角度仰拍，仰视视角",
            "高角度俯拍，鸟瞰视角",
            "侧面角度，轮廓视角",
            "倾斜构图，动感视角",
            "过肩镜头，对话视角",
        ]
        return compositions[shot_id % len(compositions)]
    
    def _get_art_style_zh(self, content_type):
        """获取中文艺术风格"""
        if "military" in content_type:
            return "战争摄影风格，纪实主义，电影级画面"
        return "写实摄影风格，专业构图，高品质画面"
    
    def _enhance_prompt_with_details(self, base_prompt, description_parts, content_type):
        """使用脚本内置逻辑增强提示词 - 智能语义分析框架
        
        设计原则：
        1. 直接分析配音文本的整体语义
        2. 提取关键的视觉概念（而不是零散的词）
        3. 组合成完整的、语义连贯的提示词
        4. 融入用户自定义主题
        """
        import re
        
        # 调试日志
        self.log(f"   [_enhance_prompt_with_details] base_prompt: {base_prompt[:50] if base_prompt else 'None'}...")
        
        # 获取提示词类型
        prompt_type = "SD提示词"
        if hasattr(self, 'prompt_type_var'):
            prompt_type = self.prompt_type_var.get()
        
        self.log(f"   [_enhance_prompt_with_details] prompt_type: {prompt_type}")
        
        # 获取用户自定义主题
        custom_theme = description_parts.get('custom_theme', '')
        custom_visual_tone = description_parts.get('custom_visual_tone', '')
        self.log(f"   [_enhance_prompt_with_details] custom_theme: {custom_theme}, custom_visual_tone: {custom_visual_tone}")

        is_sd_prompt = prompt_type == "SD提示词" or prompt_type == "ARV写实提示词"
        
        dubbing = description_parts.get('dubbing', '')
        if not dubbing:
            self.log(f"   [_enhance_prompt_with_details] dubbing为空，使用base_prompt")
            return base_prompt
        
        self.log(f"   [_enhance_prompt_with_details] dubbing: {dubbing[:30]}...")
        
        # 清理和预处理文本
        text = dubbing.strip()
        
        # 分析语义并生成提示词
        if is_sd_prompt:
            # SD提示词
            prompt = self._analyze_and_generate_sd_prompt(text, content_type, custom_theme, custom_visual_tone)
            self.log(f"   [_enhance_prompt_with_details] SD prompt生成结果: {prompt[:50]}...")
            return prompt
        else:
            # 豆包提示词
            prompt = self._analyze_and_generate_doubao_prompt(text, content_type, custom_theme, custom_visual_tone)
            self.log(f"   [_enhance_prompt_with_details] 豆包 prompt生成结果: {prompt[:50]}...")
            return prompt
    
    def _analyze_and_generate_sd_prompt(self, text, content_type, custom_theme='', custom_visual_tone=''):
        """分析文本语义并生成SD提示词
        
        策略：
        1. 融入用户自定义主题
        2. 识别文本的核心主题
        3. 提取场景关键词
        4. 添加氛围描述
        5. 组合质量标签
        """
        text_lower = text.lower()
        keywords = []
        
        # ========== 0. 用户自定义主题（优先）==========
        if custom_theme:
            # 翻译用户自定义主题
            theme_translated = self._translate_to_english(custom_theme)
            if theme_translated:
                keywords.append(theme_translated)
            else:
                keywords.append(custom_theme)
            self.log(f"   [_analyze] 融入自定义主题: {custom_theme} -> {theme_translated or custom_theme}")
        
        # 如果有自定义视觉基调，也加入
        if custom_visual_tone:
            tone_translated = self._translate_to_english(custom_visual_tone)
            if tone_translated:
                keywords.append(tone_translated)
        
        # ========== 1. 主题识别（不阻断，可叠加）==========
        if any(word in text for word in ['戰爭', '战争', '戰鬥', '战斗', '軍事', '军事', '軍隊', '军队', '導彈', '导弹', '坦克', '炸彈', '炸弹', '定時炸彈', '定时炸弹']):
            keywords.extend(['war zone', 'military conflict', 'battlefield'])
        
        if any(word in text for word in ['政治', 'Politics', '總統', '总统', '總理', '总理', '政府', '部長', '部长', '官員', '官员', '領導', '领导', '領袖', '领袖']):
            keywords.extend(['political scene', 'government', 'diplomatic', 'leaders'])
        
        if any(word in text for word in ['經濟', '经济', '金融', '股票', '錢', '钱', '投資', '投资', '商', '生意']):
            keywords.extend(['financial district', 'business', 'economy'])
        
        if any(word in text for word in ['科技', '技術', '技术', '科學', '科学', '創新', '创新']):
            keywords.extend(['technology', 'laboratory', 'innovation'])
        
        if any(word in text for word in ['醫生', '医生', '醫院', '医院', '健康', '治療', '治疗']):
            keywords.extend(['hospital', 'medical', 'healthcare'])
        
        if any(word in text for word in ['學校', '学校', '教育', '学生', '教師', '教师', '教室']):
            keywords.extend(['school', 'education', 'classroom'])
        
        if any(word in text for word in ['投降', '談判', '谈判', '協商', '协商', '條約', '条约']):
            keywords.extend(['negotiation', 'surrender', 'diplomatic talk'])
        
        # 如果没有匹配任何主题，添加默认
        if not keywords:
            keywords.append('realistic scene')
        
        # ========== 2. 地点/场景 ==========
        if any(word in text for word in ['中東', '中东', '伊朗', '伊拉克', '敘利亞', '叙利亚', '以色列', '巴勒斯坦']):
            keywords.append('Middle East')
        if any(word in text for word in ['美國', '美国', 'USA', '美']):
            keywords.append('United States')
        if any(word in text for word in ['中國', '中国', '中']):
            keywords.append('China')
        if any(word in text for word in ['歐洲', '欧洲']):
            keywords.append('Europe')
        if any(word in text for word in ['亞洲', '亚洲', '亞洲']):
            keywords.append('Asia')
        if any(word in text for word in ['俄羅斯', '俄罗斯', '俄']):
            keywords.append('Russia')
        if any(word in text for word in ['烏克蘭', '乌克兰']):
            keywords.append('Ukraine')
        
        if any(word in text for word in ['城市', '城', '街', '街道', '都市']):
            keywords.append('urban city')
        if any(word in text for word in ['農村', '农村', '鄉村', '乡村']):
            keywords.append('countryside')
        
        # ========== 3. 氛围/情感 ==========
        if any(word in text for word in ['緊張', '紧张', '危機', '危机', '危險', '危险', '嚴峻', '严峻', '嚴重', '严重']):
            keywords.append('tense atmosphere')
        if any(word in text for word in ['戰爭', '战争', '戰鬥', '战斗', '衝突', '冲突']):
            keywords.append('dramatic battle')
        if any(word in text for word in ['和平', '平靜', '平静', '安靜', '安静']):
            keywords.append('peaceful')
        if any(word in text for word in ['快樂', '快乐', '高興', '高兴', '喜悅', '喜悦', '慶祝', '庆祝']):
            keywords.append('joyful')
        if any(word in text for word in ['悲傷', '悲伤', '難過', '难过', '傷心', '伤心', '絕望', '绝望']):
            keywords.append('sad')
        if any(word in text for word in ['壓抑', '压抑', '沈重', '沉重']):
            keywords.append('heavy atmosphere')
        
        # ========== 4. 时间/天气 ==========
        if any(word in text for word in ['白天', '日', '太陽', '太阳', '早晨', '早上']):
            keywords.append('daytime')
        if any(word in text for word in ['夜晚', '晚上', '黑', '夜']):
            keywords.append('night')
        
        if any(word in text for word in ['晴天', '晴', '陽光', '阳光']):
            keywords.append('sunny')
        if any(word in text for word in ['雨天', '雨', '下雨']):
            keywords.append('rainy')
        
        # ========== 5. 人物 ==========
        if any(word in text for word in ['總統', '总统', '國家領導人', '国家领导人']):
            keywords.append('president')
        if any(word in text for word in ['總理', '总理']):
            keywords.append('prime minister')
        if any(word in text for word in ['軍人', '军人', '士兵', '部隊', '部队']):
            keywords.append('soldier')
        if any(word in text for word in ['警察', '員警', '警']):
            keywords.append('police officer')
        
        # ========== 6. 组合提示词 ==========
        # 去重
        unique_keywords = list(dict.fromkeys(keywords))
        
        # 如果没有提取到关键词，使用通用场景
        if len(unique_keywords) <= 1:
            unique_keywords = ['realistic scene', 'detailed environment']
        
        # 添加质量标签
        quality_tags = 'ultra detailed, hyper realistic, photorealistic, cinematic lighting, professional photography'
        
        return f"{', '.join(unique_keywords)}, {quality_tags}"
    
    def _analyze_and_generate_doubao_prompt(self, text, content_type, custom_theme='', custom_visual_tone=''):
        """分析文本语义并生成豆包提示词
        
        策略：
        1. 融入用户自定义主题
        2. 识别文本的核心主题
        3. 提取场景关键词
        4. 添加氛围描述
        5. 组合质量标签
        """
        keywords = []
        
        # ========== 0. 用户自定义主题（优先）==========
        if custom_theme:
            keywords.append(custom_theme)
            self.log(f"   [_analyze] 融入自定义主题: {custom_theme}")
        
        # 如果有自定义视觉基调，也加入
        if custom_visual_tone:
            keywords.append(custom_visual_tone)
        
        # ========== 1. 主题识别 ==========
        if any(word in text for word in ['戰爭', '战争', '戰鬥', '战斗', '軍事', '军事']):
            keywords.extend(['战争场景', '军事冲突', '战场'])
        elif any(word in text for word in ['政治', '總統', '总统', '政府']):
            keywords.extend(['政治场景', '政府', '外交'])
        elif any(word in text for word in ['經濟', '经济', '金融']):
            keywords.extend(['金融', '商业', '经济'])
        elif any(word in text for word in ['科技', '技術', '科學', '科学']):
            keywords.extend(['科技', '实验室', '创新'])
        elif any(word in text for word in ['醫生', '医生', '醫院', '医院']):
            keywords.extend(['医院', '医疗', '健康'])
        elif any(word in text for word in ['學校', '学校', '教育']):
            keywords.extend(['学校', '教育', '教室'])
        
        # ========== 2. 地点 ==========
        if any(word in text for word in ['中東', '中东', '伊朗']):
            keywords.append('中东')
        elif any(word in text for word in ['美國', '美国']):
            keywords.append('美国')
        elif any(word in text for word in ['中國', '中国']):
            keywords.append('中国')
        
        if any(word in text for word in ['城市', '街']):
            keywords.append('城市')
        elif any(word in text for word in ['農村', '农村']):
            keywords.append('农村')
        
        # ========== 3. 氛围 ==========
        if any(word in text for word in ['緊張', '紧张', '危機', '危机']):
            keywords.append('紧张氛围')
        elif any(word in text for word in ['戰爭', '战争']):
            keywords.append('战争氛围')
        elif any(word in text for word in ['和平', '平靜', '平静']):
            keywords.append('平静氛围')
        elif any(word in text for word in ['快樂', '快乐', '高興', '高兴']):
            keywords.append('快乐氛围')
        
        # ========== 4. 组合提示词 ==========
        if len(keywords) <= 1:
            keywords = ['写实场景', '真实质感']
        
        quality_tags = '高清画质，细节丰富，专业摄影效果'
        
        return f"{'，'.join(keywords)}，{quality_tags}"
    
    def _extract_visual_info_from_dubbing(self, dubbing, is_sd_prompt=True):
        """从配音文本中提取关键视觉信息：主体、场景、动作、氛围
        
        Args:
            dubbing: 配音文本
            is_sd_prompt: True为SD提示词，False为豆包提示词
        """
        import re
        
        result = {
            'subject': '',      # 主体（谁/什么）
            'location': '',    # 场景（在哪里）
            'action': '',      # 动作/状态（做什么）
            'atmosphere': ''   # 氛围（什么样）
        }
        
        if not dubbing:
            return result
        
        text = dubbing.strip()
        
        # ========== 1. 提取主体 ==========
        # 首先尝试提取完整的人名/人物
        person_patterns = [
            (r'([^\s，,。.!！?？]{2,6}(?:人|者|员|师|生|工|兵|官|长|队))', 'person'),
            (r'([^\s，,。.!！?？]{2,4}(?:男人|女人|老人|小孩|年轻人|学生|医生|护士|警察|军人|教师))', 'person'),
            (r'([^\s，,。.!！?？]{2,4}(?:记者|主持|商人|科学家|工程师|运动员|演员|歌手|总统|总理|部长|司令|长官))', 'person'),
        ]
        
        # 提取主体
        for pattern, ptype in person_patterns:
            match = re.search(pattern, text)
            if match:
                subject = match.group(1)
                if is_sd_prompt:
                    result['subject'] = self._translate_to_english(subject)
                else:
                    result['subject'] = subject
                break
        
        # 如果没有匹配到人物，提取名词/物体
        if not result['subject']:
            # 提取第一个有意义的名词短语
            noun_pattern = r'[\u4e00-\u9fa5]{2,6}'
            nouns = re.findall(noun_pattern, text)
            
            # 常见无意义词列表（扩展）
            skip_words = [
                '這個', '那個', '一個', '什麼', '怎麼', '為什麼', '怎麼樣', '有多少', '有多',
                '這是', '那是', '因為', '所以', '但是', '而且', '如果', '雖然', '只是', '已經',
                '正在', '將要', '這場', '那場', '這裡', '那裡', '這時', '那時', '這次', '那次',
                '這個', '那個', '這裡', '那裡', '這裡', '那裡', '這兒', '那兒',
                '會', '能', '可以', '要', '去', '來', '到', '說', '想', '看', '聽', '做', '給',
                '把', '被', '讓', '跟', '和', '與', '及', '或', '但', '不', '沒', '有', '是',
                '在', '了', '著', '過', '的', '地', '得', '很', '都', '也', '還', '就', '而',
                '之', '於', '從', '到', '由', '向', '對', '以', '為', '當', '時', '後', '前',
                '裡', '中', '上', '下', '外', '內', '間', '旁', '邊', '處', '起',
                '除了', '除了', '只有', '除了', '關於', '對於', '由於', '根據',
                '通過', '經過', '隨著', '沿著', '朝著', '向著',
                '今天', '昨天', '明天', '現在', '過去', '未來', '將來',
                '這場', '那場', '這次', '那 次', '這點', '那點',
                '直接', '間接', '完全', '真正', '實際',
            ]
            
            for noun in nouns[:10]:  # 检查前10个
                # 跳过常见无意义词
                if noun in skip_words:
                    continue
                if noun[0] in ['這', '那', '哪'] and len(noun) <= 4:
                    # 跳过以"這/那/哪"开头的短词
                    continue
                if noun[0] in ['我', '你', '他', '她', '它', '我們', '你們', '他們', '她們'] and len(noun) <= 3:
                    # 跳过人称代词
                    continue
                    
                if is_sd_prompt:
                    translated = self._translate_to_english(noun)
                    # 只有翻译结果不为空才使用
                    if translated:
                        result['subject'] = translated
                        break
                    # 否则继续尝试下一个词
                else:
                    result['subject'] = noun
                    break
        
        # ========== 2. 提取场景 ==========
        location_patterns = [
            (r'在([^\s，,。.!！?？]{2,6}(?:城市|國家|地區|洲|鎮|村|鄉|區|街|道路|商場|餐廳|醫院|學校|工廠|辦公室|圖書館|公園|海灘|山|河|湖|海|森林|草原|沙漠|房間|樓|機場|車站|碼頭|廣場|大樓|大廈|宮殿|寺廟|教堂|學校|醫院|銀行|博物館|劇院|體育場|會議中心|實驗室))', 'location'),
            (r'([^\s，,。.!！?？]{2,4}(?:城市|城鎮|鄉村|街道|道路|商場|醫院|學校|工廠|辦公室|公園|機場|車站))', 'location'),
        ]
        
        for pattern, ltype in location_patterns:
            match = re.search(pattern, text)
            if match:
                location = match.group(1) if ltype == 'location' else match.group(0)
                if is_sd_prompt:
                    result['location'] = self._translate_to_english(location)
                else:
                    result['location'] = location
                break
        
        # ========== 3. 提取动作 ==========
        action_patterns = [
            (r'(?:在|正|著)在?([^\s，,。.!！?？]{1,4}(?:走|跑|跳|飛|坐|躺|站|看|聽|說|笑|哭|唱|跳舞|吃|喝|吸|抽|打|殺|砍|射|寫|畫|拍|攝|錄|工作|學習|開車|打電話|拍照|採訪|演講|表演|比賽|戰鬥|戰爭|談判|開會|討論|報告|演說|指揮|進攻|防守|撤退|占領|摧毀|建造|維修|治療|做飯|購物|旅行|睡覺|醒來|結婚|葬禮|慶祝|開會))', 'action'),
        ]
        
        for pattern, atype in action_patterns:
            match = re.search(pattern, text)
            if match:
                action = match.group(1)
                if is_sd_prompt:
                    result['action'] = self._translate_to_english(action)
                else:
                    result['action'] = action
                break
        
        # 如果没有匹配到具体动作，尝试其他方式
        if not result['action']:
            # 常见动作词列表（扩展）
            action_words = ['走', '跑', '跳', '飛', '坐', '站', '看', '聽', '說', '笑', '哭', '唱', '吃', '喝', '工作', '學習', '開車', '拍照', '戰鬥', '戰爭', '開會', '談判']
            for word in action_words:
                if word in text:
                    if is_sd_prompt:
                        result['action'] = self._translate_to_english(word)
                    else:
                        result['action'] = word
                    break
        
        # ========== 4. 提取氛围 ==========
        atmosphere_keywords = {
            '緊張': 'tense atmosphere', '危機': 'crisis mood', '危險': 'dangerous',
            '平靜': 'peaceful', '安靜': 'quiet', '寧靜': 'serene',
            '高興': 'happy', '快樂': 'joyful', '開心': 'cheerful',
            '悲傷': 'sad', '難過': 'sad', '傷心': 'heartbreaking',
            '憤怒': 'angry', '生氣': 'furious',
            '害怕': 'scared', '恐懼': 'fearful',
            '熱鬧': 'lively', '冷清': 'deserted',
            '白天': 'daytime', '夜晚': 'night', '早晨': 'morning', '黃昏': 'dusk',
            '晴天': 'sunny', '雨天': 'rainy', '雪天': 'snowy',
            '嚴峻': 'severe', '沉重': 'heavy', '壓抑': 'depressing',
            '絕望': 'desperate', '希望': 'hopeful', '勝利': 'victorious',
        }
        
        atmosphere_keywords_zh = {
            '緊張': '緊張氛圍', '危機': '危機感', '危險': '危險氛圍',
            '平靜': '平靜氛圍', '安靜': '安靜氛圍', '寧靜': '寧靜氛圍',
            '高興': '高興氛圍', '快樂': '快樂氛圍', '開心': '開心氛圍',
            '悲傷': '悲傷氛圍', '難過': '難過氛圍', '傷心': '傷心氛圍',
            '憤怒': '憤怒氛圍', '生氣': '生氣氛圍',
            '害怕': '害怕氛圍', '恐懼': '恐懼氛圍',
            '熱鬧': '熱鬧氛圍', '冷清': '冷清氛圍',
            '白天': '白天', '夜晚': '夜晚', '早晨': '早晨', '黃昏': '黃昏',
            '晴天': '晴天', '雨天': '雨天', '雪天': '雪天',
            '嚴峻': '嚴峻氛圍', '沉重': '沉重氛圍', '壓抑': '壓抑氛圍',
            '絕望': '絕望氛圍', '希望': '希望氛圍', '勝利': '勝利氛圍',
        }
        
        for keyword, en_value in atmosphere_keywords.items():
            if keyword in text:
                if is_sd_prompt:
                    result['atmosphere'] = en_value
                else:
                    result['atmosphere'] = atmosphere_keywords_zh.get(keyword, keyword)
                break
        
        # 如果没有匹配到氛围词，提取时间/天气
        if not result['atmosphere']:
            time_weather = ['白天', '夜晚', '早晨', '黃昏', '晴天', '雨天', '雪天', '陰天']
            for tw in time_weather:
                if tw in text:
                    if is_sd_prompt:
                        result['atmosphere'] = atmosphere_keywords.get(tw, tw)
                    else:
                        result['atmosphere'] = atmosphere_keywords_zh.get(tw, tw)
                    break
        
        return result
    
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
    
    def evaluate_prompt_quality(self, prompt, sentence, content_type):
        """评估提示词质量 - 高级版本"""
        score = 0.0
        details = {}
        
        # 1. 长度评估 (权重 15%)
        prompt_length = len(prompt.split(','))
        if 15 <= prompt_length <= 50:
            score += 0.15
            details['length'] = "优秀"
        elif prompt_length > 50:
            score += 0.1
            details['length'] = "良好"
        elif prompt_length >= 10:
            score += 0.05
            details['length'] = "一般"
        else:
            details['length'] = "过短"
        
        # 2. 关键词覆盖评估 (权重 20%)
        keywords = self.extract_keywords(sentence)
        keyword_matches = 0
        for keyword in keywords:
            if keyword.lower() in prompt.lower():
                keyword_matches += 1
        if keywords:
            keyword_ratio = keyword_matches / len(keywords)
            score += 0.2 * keyword_ratio
            if keyword_ratio >= 0.8:
                details['keywords'] = "优秀"
            elif keyword_ratio >= 0.5:
                details['keywords'] = "良好"
            else:
                details['keywords'] = "一般"
        
        # 3. 视觉元素丰富度评估 (权重 20%)
        visual_categories = {
            "subject": ["person", "object", "animal", "character", "figure"],
            "environment": ["background", "scene", "landscape", "setting", "environment"],
            "lighting": ["lighting", "light", "shadow", "sunlight", "moonlight", "golden hour"],
            "color": ["color", "red", "blue", "green", "warm", "cool", "vibrant"],
            "composition": ["composition", "perspective", "angle", "view", "close-up", "wide shot"],
            "style": ["style", "photorealistic", "cinematic", "artistic", "painting", "illustration"]
        }
        
        category_matches = 0
        for category, words in visual_categories.items():
            if any(word in prompt.lower() for word in words):
                category_matches += 1
        
        visual_ratio = category_matches / len(visual_categories)
        score += 0.2 * visual_ratio
        if visual_ratio >= 0.8:
            details['visual_elements'] = "优秀"
        elif visual_ratio >= 0.5:
            details['visual_elements'] = "良好"
        else:
            details['visual_elements'] = "一般"
        
        # 4. 内容类型匹配评估 (权重 15%)
        content_keywords = {
            "space": ["space", "cosmic", "planet", "star", "orbit", "galaxy", "astronaut"],
            "science": ["science", "research", "laboratory", "data", "experiment", "formula", "lab"],
            "nature": ["nature", "environment", "ecosystem", "wildlife", "landscape", "forest", "mountain"],
            "history": ["history", "ancient", "civilization", "heritage", "archaeological", "vintage", "old"],
            "technology": ["technology", "innovation", "digital", "high-tech", "future", "robot", "ai"],
            "art": ["art", "creative", "visualization", "gallery", "style", "painting", "sculpture"],
            "education": ["education", "learning", "classroom", "knowledge", "study", "book", "teacher"],
            "business": ["business", "corporate", "financial", "market", "strategy", "office", "meeting"],
            "health": ["health", "medical", "wellness", "healthcare", "treatment", "hospital", "doctor"],
            "travel": ["travel", "tourist", "destination", "scenic", "adventure", "journey", "trip"]
        }
        
        if content_type in content_keywords:
            content_matches = 0
            for keyword in content_keywords[content_type]:
                if keyword in prompt.lower():
                    content_matches += 1
            if content_keywords[content_type]:
                content_ratio = min(content_matches / len(content_keywords[content_type]), 1.0)
                score += 0.15 * content_ratio
                if content_ratio >= 0.6:
                    details['content_match'] = "优秀"
                elif content_ratio >= 0.3:
                    details['content_match'] = "良好"
                else:
                    details['content_match'] = "一般"
        
        # 5. 质量标签评估 (权重 15%)
        quality_tags = ["masterpiece", "best quality", "ultra-detailed", "sharp focus", "cinematic", "high quality", "8k", "hd"]
        quality_matches = 0
        for tag in quality_tags:
            if tag in prompt.lower():
                quality_matches += 1
        quality_ratio = min(quality_matches / len(quality_tags), 1.0)
        score += 0.15 * quality_ratio
        if quality_ratio >= 0.5:
            details['quality_tags'] = "优秀"
        elif quality_ratio >= 0.25:
            details['quality_tags'] = "良好"
        else:
            details['quality_tags'] = "一般"
        
        # 6. 词汇多样性评估 (权重 10%)
        unique_words = len(set(prompt.lower().split()))
        if unique_words > 40:
            score += 0.1
            details['diversity'] = "优秀"
        elif unique_words > 30:
            score += 0.07
            details['diversity'] = "良好"
        elif unique_words > 20:
            score += 0.04
            details['diversity'] = "一般"
        else:
            details['diversity'] = "较差"
        
        # 7. 避免负面词汇检查 (额外加分项)
        negative_indicators = ["low quality", "blurry", "distorted", "bad", "ugly", "worst"]
        has_negative = any(neg in prompt.lower() for neg in negative_indicators)
        if not has_negative:
            score = min(score + 0.05, 1.0)
            details['no_negative'] = "✅ 无负面词汇"
        
        final_score = min(score, 1.0)
        details['final_score'] = final_score
        
        # 记录详细评估结果
        self.log(f"📊 提示词质量评估: {final_score:.2f} | {details}")
        
        return final_score
    
    def extract_keywords(self, text):
        """提取关键词"""
        import re
        # 简单的关键词提取
        text = re.sub(r'[.,!?;:]', ' ', text)
        words = text.split()
        # 过滤停用词
        stop_words = set(['的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'])
        keywords = [word for word in words if word not in stop_words and len(word) > 1]
        return keywords[:10]  # 最多返回10个关键词

    def generate_english_keywords(self, sentence, content_type):
        """基于内容类型和句子语义生成英文关键词"""
        import re
        
        # 清理句子，去除标点和特殊字符
        cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', ' ', sentence).strip()
        
        # 中文到英文的实体映射（常见名词）
        entity_mappings = {
            # 地点
            '德黑兰': 'Tehran, Iran capital city',
            '伊朗': 'Iran, Middle East country',
            '美国': 'United States, America',
            '中国': 'China',
            '俄罗斯': 'Russia',
            '欧洲': 'Europe',
            '亚洲': 'Asia',
            '中东': 'Middle East',
            # 军事相关
            '防空警报': 'air raid siren, air defense alarm',
            '飞机': 'aircraft, airplane, military plane',
            '战斗机': 'fighter jet, military aircraft',
            '导弹': 'missile, rocket',
            '军队': 'military, army, troops',
            '战争': 'war, conflict, battle',
            '打击': 'strike, attack, bombing',
            '爆炸': 'explosion, blast',
            # 人物相关
            '总统': 'president, leader',
            '领导人': 'leader, politician',
            '士兵': 'soldier, military personnel',
            '尸体': 'corpse, body, casualty',
            # 场景
            '街道': 'street, city street',
            '城市': 'city, urban',
            '天空': 'sky, aerial',
            '地图': 'map, geographical map',
            '世界': 'world, global',
            # 时间/状态
            '清晨': 'early morning, dawn',
            '夜晚': 'night, nighttime',
            '持续': 'continuous, ongoing',
            '紧急': 'emergency, urgent',
        }
        
        # 提取句子中的关键实体
        extracted_keywords = []
        for chinese, english in entity_mappings.items():
            if chinese in cleaned:
                extracted_keywords.append(english)
        
        # 根据内容类型定义基础场景关键词
        keyword_mappings = {
            "space": ["cosmic scene", "space environment", "planetary", "celestial", "astronomical"],
            "science": ["scientific research", "laboratory", "experiment", "technology", "innovation"],
            "nature": ["natural landscape", "outdoor scene", "environment", "wildlife", "nature"],
            "history": ["historical scene", "period setting", "cultural heritage", "ancient", "traditional"],
            "technology": ["high-tech", "futuristic", "digital", "innovation", "technology"],
            "art": ["artistic", "creative", "artwork", "painting", "sculpture"],
            "education": ["learning", "education", "classroom", "academic", "knowledge"],
            "business": ["business", "corporate", "office", "professional", "workplace"],
            "health": ["medical", "healthcare", "hospital", "doctor", "wellness"],
            "travel": ["travel", "tourism", "destination", "scenic", "adventure"],
            "military": ["military scene", "war zone", "conflict area", "defense", "combat"],
            "politics": ["political scene", "government building", "diplomatic", "international"],
            "general": ["realistic scene", "photorealistic", "detailed", "cinematic"]
        }
        
        # 组合关键词：提取的实体 + 场景类型
        keywords = []
        
        # 首先添加提取的具体实体（最重要）
        keywords.extend(extracted_keywords[:3])
        
        # 然后添加场景类型关键词
        for key, values in keyword_mappings.items():
            if key in content_type:
                keywords.extend(values[:3])
                break
        else:
            # 如果没有匹配的类型，使用通用场景
            keywords.extend(["realistic scene", "photorealistic", "cinematic lighting"])
        
        return keywords[:6]  # 最多返回6个关键词

    def extract_visual_concepts(self, sentence, content_type):
        """提取英文视觉概念 - 用于SD提示词
        
        将句子语义转化为具体的英文视觉元素
        """
        import re
        
        concepts = []
        sentence_lower = sentence.lower()
        
        # 军事/战争相关视觉元素
        military_visuals = {
            '战争': ['battlefield scene', 'military conflict', 'war zone'],
            '冲突': ['conflict zone', 'tension scene', 'confrontation'],
            '军事': ['military installation', 'armed forces', 'defense facility'],
            '战斗': ['combat scene', 'battlefield', 'military engagement'],
            '导弹': ['missile launch', 'rocket trajectory', 'military strike'],
            '无人机': ['drone swarm', 'UAV formation', 'aerial surveillance'],
            '空军': ['air force base', 'fighter jets', 'military aircraft'],
            '海军': ['naval fleet', 'warships', 'maritime military'],
            '军队': ['military troops', 'soldier formation', 'armed forces'],
            '武器': ['military weapons', 'arsenal', 'armaments'],
            '防御': ['defense system', 'fortification', 'military defense'],
            '攻击': ['military assault', 'offensive operation', 'strike mission'],
            '战略': ['strategic command', 'war room', 'tactical planning'],
            '战术': ['tactical operation', 'battlefield strategy', 'combat tactics'],
            '指挥中心': ['command center', 'military headquarters', 'strategic planning room'],
            '地图': ['tactical map', 'strategic display', 'battlefield chart'],
        }
        
        # 政治/国际相关视觉元素
        political_visuals = {
            '伊朗': ['Iranian landscape', 'Middle East setting', 'Persian architecture'],
            '美国': ['American political scene', 'Washington DC', 'US government'],
            '以色列': ['Israeli defense forces', 'Middle East conflict zone', 'military installation'],
            '政府': ['government building', 'political institution', 'official venue'],
            '外交': ['diplomatic meeting', 'international summit', 'foreign affairs'],
            '国际': ['international scene', 'global politics', 'world affairs'],
            '政治': ['political scene', 'government setting', 'diplomatic venue'],
            '国家': ['national setting', 'country landscape', 'state institution'],
            '谈判': ['negotiation table', 'diplomatic talks', 'peace conference'],
            '协议': ['treaty signing', 'agreement ceremony', 'diplomatic accord'],
        }
        
        # 状态/情感视觉元素
        state_visuals = {
            '瘫痪': ['destroyed infrastructure', 'damaged facility', 'paralyzed system'],
            '损坏': ['damaged equipment', 'destruction scene', 'ruined structure'],
            '枯竭': ['depleted resources', 'exhausted state', 'drained capacity'],
            '紧张': ['tense atmosphere', 'stressful scene', 'high tension'],
            '危机': ['crisis situation', 'emergency state', 'critical moment'],
            '胜利': ['victory scene', 'triumphant moment', 'successful operation'],
            '失败': ['defeat scene', 'failed mission', 'collapse'],
            '抵抗': ['resistance movement', 'defensive stance', 'opposition'],
            '投降': ['surrender scene', 'capitulation', 'defeat'],
            '毁灭': ['destruction', 'devastation', 'annihilation'],
            '希望': ['hopeful atmosphere', 'bright future', 'positive vibe'],
            '和平': ['peaceful scene', 'harmony', 'tranquility'],
            '悲伤': ['sad atmosphere', 'melancholy', 'gloomy mood'],
            '愤怒': ['angry expression', 'furious scene', 'rage'],
            '恐惧': ['scary atmosphere', 'fearful expression', 'horror'],
            '喜悦': ['joyful scene', 'happy moment', 'celebration'],
            '惊讶': ['surprised expression', 'shocked scene', 'astonishment'],
        }
        
        # 科技/未来主题视觉元素
        tech_visuals = {
            '科技': ['futuristic laboratory', 'high-tech equipment', 'advanced technology'],
            '未来': ['futuristic cityscape', 'science fiction setting', 'advanced future'],
            '人工智能': ['AI interface', 'machine learning visualization', 'neural network'],
            '机器人': ['robot assistant', 'android', 'mechanical device'],
            '太空': ['space station', 'astronaut', 'cosmic exploration'],
            '宇宙': ['galaxy view', 'nebula scene', 'outer space'],
            '数据': ['data visualization', 'digital interface', 'information graphics'],
            '网络': ['cyberspace', 'network connection', 'digital world'],
            '创新': ['innovation lab', 'creative technology', 'breakthrough'],
            '实验室': ['scientific laboratory', 'research facility', 'experiment setup'],
        }
        
        # 自然/环境主题视觉元素
        nature_visuals = {
            '自然': ['natural landscape', 'wilderness scene', 'outdoor environment'],
            '森林': ['dense forest', 'woodland scene', 'trees and foliage'],
            '海洋': ['ocean view', 'seascape', 'marine environment'],
            '山脉': ['mountain range', 'alpine scene', 'peak view'],
            '河流': ['river landscape', 'stream scene', 'water flow'],
            '天空': ['cloudy sky', 'sunset scene', 'starry night'],
            '季节': ['autumn foliage', 'winter snow', 'spring bloom'],
            '天气': ['rainy day', 'stormy weather', 'sunny scene'],
            '生态': ['ecosystem', 'biodiversity', 'natural balance'],
            '环保': ['green environment', 'sustainable scene', 'eco-friendly'],
        }
        
        # 历史/文化主题视觉元素
        history_visuals = {
            '历史': ['historical scene', 'ancient setting', 'period costume'],
            '古代': ['ancient civilization', 'classical era', 'historical monument'],
            '文化': ['cultural heritage', 'traditional scene', 'folk culture'],
            '艺术': ['art gallery', 'painting exhibition', 'artistic creation'],
            '建筑': ['historic architecture', 'ancient building', 'monumental structure'],
            '传统': ['traditional ceremony', 'cultural ritual', 'heritage scene'],
            '考古': ['archaeological site', 'ancient ruins', 'artifact discovery'],
            '文明': ['civilization scene', 'cultural advancement', 'historical progress'],
            '复古': ['vintage style', 'retro scene', 'old-fashioned'],
            '经典': ['classic style', 'timeless scene', 'iconic moment'],
        }
        
        # 城市/人文主题视觉元素
        urban_visuals = {
            '城市': ['cityscape', 'urban scene', 'metropolitan view'],
            '街道': ['street scene', 'city road', 'urban traffic'],
            '建筑': ['modern building', 'skyscraper', 'architectural design'],
            '人群': ['crowd scene', 'people gathering', 'public space'],
            '交通': ['traffic jam', 'public transport', 'urban mobility'],
            '夜景': ['night cityscape', 'neon lights', 'evening scene'],
            '商业': ['shopping mall', 'storefront', 'commercial district'],
            '生活': ['daily life', 'urban living', 'city lifestyle'],
            '社区': ['neighborhood scene', 'community space', 'local area'],
            '市场': ['marketplace', 'bazaar scene', 'shopping area'],
        }
        
        # 教育/知识主题视觉元素
        education_visuals = {
            '教育': ['classroom scene', 'learning environment', 'academic setting'],
            '学校': ['school campus', 'university building', 'educational institution'],
            '知识': ['book collection', 'library scene', 'knowledge sharing'],
            '学习': ['study session', 'learning process', 'academic work'],
            '研究': ['research lab', 'scientific study', 'academic research'],
            '书籍': ['bookshelf', 'reading scene', 'literary work'],
            '教室': ['classroom interior', 'lecture hall', 'training room'],
            '学生': ['student group', 'young learners', 'academic community'],
            '老师': ['teacher figure', 'educator', 'instructor'],
            '智慧': ['wisdom scene', 'enlightened moment', 'intellectual depth'],
        }
        
        # 健康/医疗主题视觉元素
        health_visuals = {
            '健康': ['healthy lifestyle', 'wellness scene', 'vitality'],
            '医疗': ['hospital scene', 'medical setting', 'healthcare facility'],
            '医院': ['hospital interior', 'medical ward', 'clinic scene'],
            '医生': ['doctor figure', 'medical professional', 'physician'],
            '病人': ['patient care', 'medical treatment', 'health recovery'],
            '药物': ['medicine bottle', 'pharmaceutical scene', 'drug therapy'],
            '护理': ['nursing care', 'medical assistance', 'health support'],
            '体检': ['medical examination', 'health checkup', 'physical exam'],
            '锻炼': ['exercise scene', 'fitness activity', 'workout session'],
            '康复': ['recovery process', 'rehabilitation scene', 'healing process'],
        }
        
        # 商业/经济主题视觉元素
        business_visuals = {
            '商业': ['business setting', 'corporate scene', 'commercial environment'],
            '经济': ['economic scene', 'financial market', 'business activity'],
            '办公': ['office interior', 'workplace scene', 'business space'],
            '会议': ['meeting room', 'conference scene', 'business discussion'],
            '金融': ['financial scene', 'stock market', 'banking environment'],
            '交易': ['trade scene', 'business transaction', 'commercial exchange'],
            '成功': ['success scene', 'achievement moment', 'business victory'],
            '发展': ['growth scene', 'development progress', 'business expansion'],
            '创业': ['startup scene', 'entrepreneurship', 'new business'],
            '合作': ['partnership scene', 'collaboration', 'teamwork'],
        }
        
        # 艺术/创意主题视觉元素
        art_visuals = {
            '艺术': ['artistic scene', 'creative work', 'artistic expression'],
            '绘画': ['painting studio', 'art canvas', 'painting creation'],
            '音乐': ['music scene', 'musical performance', 'concert setting'],
            '舞蹈': ['dance performance', 'choreography scene', 'ballet stage'],
            '摄影': ['photography scene', 'camera setup', 'photo shoot'],
            '设计': ['design studio', 'creative design', 'graphic work'],
            '创意': ['creative process', 'idea generation', 'inspiration moment'],
            '画廊': ['art gallery', 'exhibition space', 'art display'],
            '演出': ['stage performance', 'theater scene', 'live show'],
            '美学': ['aesthetic scene', 'beauty appreciation', 'artistic taste'],
        }
        
        # 检查并提取相关概念
        for keyword, visuals in military_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in political_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in state_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in tech_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in nature_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in history_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in urban_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in education_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in health_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in business_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in art_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
        
        # 根据内容类型添加通用场景元素
        if "military" in content_type or any(k in sentence for k in military_visuals.keys()):
            concepts.extend([
                'military command center',
                'strategic planning room',
                'tactical display screens',
                'dramatic lighting',
                'tense atmosphere'
            ])
        elif "politics" in content_type or any(k in sentence for k in political_visuals.keys()):
            concepts.extend([
                'government building interior',
                'official press conference',
                'diplomatic venue',
                'world map display',
                'formal setting'
            ])
        
        # 去重并限制数量
        unique_concepts = list(dict.fromkeys(concepts))
        return unique_concepts[:8]

    def extract_visual_concepts_zh(self, sentence, content_type):
        """提取中文视觉概念 - 用于豆包提示词
        
        将句子语义转化为具体的中文视觉元素描述
        """
        concepts = []
        
        # 军事/战争相关视觉元素
        military_visuals = {
            '战争': ['战场场景', '军事冲突', '战区环境'],
            '冲突': ['冲突地区', '紧张对峙', '对抗场面'],
            '军事': ['军事设施', '武装力量', '国防基地'],
            '战斗': ['战斗场面', '战场环境', '军事交战'],
            '导弹': ['导弹发射', '火箭轨迹', '军事打击'],
            '无人机': ['无人机群', '无人飞行器', '空中侦察'],
            '空军': ['空军基地', '战斗机群', '军用飞机'],
            '海军': ['海军舰队', '军舰编队', '海上力量'],
            '军队': ['军队集结', '士兵方阵', '武装部队'],
            '武器': ['武器装备', '军火库', '武器系统'],
            '防御': ['防御系统', '防御工事', '军事防御'],
            '攻击': ['军事进攻', '作战行动', '打击任务'],
            '战略': ['战略指挥', '作战室', '战术规划'],
            '战术': ['战术行动', '战场策略', '作战战术'],
            '指挥中心': ['指挥中心', '军事总部', '战略会议室'],
            '地图': ['战术地图', '战略显示屏', '战场图表'],
        }
        
        # 政治/国际相关视觉元素
        political_visuals = {
            '伊朗': ['伊朗风光', '中东场景', '波斯建筑'],
            '美国': ['美国政治场景', '华盛顿', '美国政府'],
            '以色列': ['以色列国防军', '中东冲突区', '军事设施'],
            '政府': ['政府大楼', '政治机构', '官方场所'],
            '外交': ['外交会议', '国际峰会', '外事活动'],
            '国际': ['国际场景', '全球政治', '国际事务'],
            '政治': ['政治场景', '政府场所', '外交场地'],
            '国家': ['国家场景', '国土风光', '国家机构'],
            '谈判': ['谈判桌', '外交会谈', '和平会议'],
            '协议': ['条约签署', '协议仪式', '外交协定'],
        }
        
        # 状态/情感视觉元素
        state_visuals = {
            '瘫痪': ['瘫痪的基础设施', '损坏的设施', '失效的系统'],
            '损坏': ['损坏的设备', '破坏场景', '损毁的建筑'],
            '枯竭': ['枯竭的资源', '耗尽的状态', '衰竭的能力'],
            '紧张': ['紧张的氛围', '压力场景', '高度紧张'],
            '危机': ['危机局势', '紧急状态', '关键时刻'],
            '胜利': ['胜利场景', '凯旋时刻', '成功的行动'],
            '失败': ['失败场景', '任务失败', '崩溃'],
            '抵抗': ['抵抗运动', '防御姿态', '对抗'],
            '投降': ['投降场景', '屈服', '战败'],
            '毁灭': ['毁灭', ' devastation', '歼灭'],
        }
        
        # 检查并提取相关概念
        for keyword, visuals in military_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in political_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
                
        for keyword, visuals in state_visuals.items():
            if keyword in sentence:
                concepts.extend(visuals)
        
        # 根据内容类型添加通用场景元素
        if "military" in content_type or any(k in sentence for k in military_visuals.keys()):
            if not concepts:
                concepts.extend([
                    '军事指挥中心',
                    '战略会议室',
                    '战术显示屏',
                    '严肃的氛围',
                    '紧张的气氛'
                ])
        elif "politics" in content_type or any(k in sentence for k in political_visuals.keys()):
            if not concepts:
                concepts.extend([
                    '政府大楼内部',
                    '官方新闻发布会',
                    '外交场所',
                    '世界地图展示',
                    '正式场合'
                ])
        
        # 去重并限制数量
        unique_concepts = list(dict.fromkeys(concepts))
        return unique_concepts[:5]

    def adjust_shot_durations(self, shots, total_duration):
        """智能调整分镜时长 - 基于原始语音时间戳的精确调整
        
        关键原则：
        1. 不使用均匀分配策略
        2. 保持原始分镜的相对时长比例
        3. 确保时间戳连续且精确匹配音频总时长
        4. 每个分镜的duration严格等于end - start
        """
        if not shots:
            return shots
        
        # 修复：使用Decimal进行高精度计算，避免浮点数精度丢失
        from decimal import Decimal, ROUND_HALF_UP
        
        # 计算当前总分镜时长
        current_total = sum(shot.get("duration", 0) for shot in shots)
        
        # 计算需要调整的差值
        duration_diff = total_duration - current_total
        
        # 如果差异很小（小于1ms），直接确保时间戳连续性即可
        if abs(duration_diff) < 0.001:
            accumulated_time = Decimal('0')
            for shot in shots:
                duration_dec = Decimal(str(shot["duration"]))
                shot["start"] = float(accumulated_time)
                accumulated_time += duration_dec
                shot["end"] = float(accumulated_time)
                shot["duration"] = shot["end"] - shot["start"]
            # 确保最后一个分镜精确匹配总时长
            if shots:
                shots[-1]["end"] = float(total_duration)
                shots[-1]["duration"] = shots[-1]["end"] - shots[-1]["start"]
            return shots
        
        # 修复：使用基于原始比例的精确调整策略（非均匀分配）
        # 计算调整因子，保持原始相对比例
        adjustment_factor = Decimal(str(total_duration)) / Decimal(str(current_total))
        
        accumulated_time = Decimal('0')
        total_duration_dec = Decimal(str(total_duration))
        
        for i, shot in enumerate(shots):
            if i < len(shots) - 1:
                # 基于原始duration按比例调整，保持相对时长关系
                original_duration = Decimal(str(shot.get("duration", 0)))
                new_duration = original_duration * adjustment_factor
                new_duration = float(new_duration.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP))
                
                # 确保最小时长（至少0.5秒）
                if new_duration < 0.5:
                    new_duration = 0.5
                
                # 设置时间戳：start -> end，确保连续性
                shot["start"] = float(accumulated_time)
                accumulated_time += Decimal(str(new_duration))
                shot["end"] = float(accumulated_time)
                # duration严格等于end - start
                shot["duration"] = shot["end"] - shot["start"]
            else:
                # 最后一个分镜：精确匹配到音频结束时间
                shot["start"] = float(accumulated_time)
                shot["end"] = float(total_duration_dec)
                shot["duration"] = shot["end"] - shot["start"]
        
        # 最终验证：确保所有分镜的duration与end-start一致
        for i, shot in enumerate(shots):
            expected_duration = shot["end"] - shot["start"]
            if abs(shot["duration"] - expected_duration) > 0.0001:  # 0.1ms精度
                self.log(f"⚠️ 分镜{i+1} duration修正: {shot['duration']:.4f}s -> {expected_duration:.4f}s")
                shot["duration"] = expected_duration
        
        # 验证总分镜时长
        final_total = sum(s['duration'] for s in shots)
        if abs(final_total - total_duration) > 0.001:
            self.log(f"⚠️ 总分镜时长({final_total:.3f}s)与音频时长({total_duration:.3f}s)仍有差异")
        
        return shots

    def optimize_prompt_with_ollama(self, prompt, sentence):
        """使用Ollama大模型优化提示词"""
        import re
        
        prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
        
        cache_key = f"{sentence}_{prompt_type}"
        cached_prompt = self.cache_get('prompts', cache_key)
        if cached_prompt:
            return cached_prompt
        
        if not OLLAMA_AVAILABLE:
            return prompt
        
        # 定义模型优先级列表（按能力和稳定性排序）
        # 包含本地所有已安装的Ollama模型
        # 推理模型(deepseek-r1)不适合提示词生成，优先使用通用模型
        model_priority_list = [
            ("qwen3:8b", 5, "阿里通用模型，推荐首选"),
            ("qwen2.5:7b", 5, "阿里通用模型，性能优秀"),
            ("gemma3:4b", 4, "Google通用模型，推荐"),
            ("qwen3:4b", 4, "阿里通用模型"),
            ("llama3.2:3b", 3, "Meta轻量级模型"),
            ("deepseek-r1:8b", 2, "推理模型，不推荐用于提示词生成"),
            ("gemma3:1b", 1, "轻量级模型，速度快但能力有限"),
        ]
        
        def get_available_models():
            try:
                models_info = ollama.list()
                available = []
                if "models" in models_info:
                    for m in models_info["models"]:
                        model_name = m.get("name", m.get("model", ""))
                        if model_name:
                            available.append(model_name)
                return available
            except Exception:
                return []
        
        available_models = get_available_models()
        
        candidate_models = []
        if user_model in available_models:
            candidate_models.append(user_model)
        
        for model_name, size, desc in model_priority_list:
            if model_name in available_models and model_name not in candidate_models:
                candidate_models.append(model_name)
        
        if not candidate_models:
            return prompt

        start_time = time.time()

        try:
            is_sd = prompt_type == "SD提示词" or prompt_type == "ARV写实提示词"
            
            # 构建清晰简洁的指令
            if is_sd:
                system_prompt = """You are a professional SD prompt engineer. Your job is to convert Chinese text into high-quality English SD prompts.

STRICT RULES - MUST FOLLOW EXACTLY:
1. Output ONLY English words, comma-separated, NO Chinese characters
2. Must include quality tags: masterpiece, best quality, ultra detailed, 8k, photorealistic
3. Choose appropriate style based on content: cinematic, news photography, lifestyle, portrait, landscape, etc.
4. Must include lighting: natural lighting, cinematic lighting, or dramatic light as appropriate
5. Describe concrete visual elements: people, objects, environment, atmosphere
6. Include shot type when relevant: close-up, wide angle, aerial view
7. NO explanations, NO quotes, NO newlines, NO intro text
8. Exactly 30-60 English words
9. Output ONLY the prompt, NOTHING else

KEY: Convert abstract to concrete visual details!
- "时间" → calendar display, date, clock, news broadcast
- "战场" → battlefield, destroyed tanks, smoke, soldiers, ruins
- "冲突" → military equipment, explosions, fire, troops
- "多线" → multiple fronts, split screen, arrows
- "内战" → rebel fighters, civilians fleeing, destroyed village

EXCELLENT OUTPUT EXAMPLES:
INPUT: "2026年3月"
OUTPUT: "close-up of digital calendar showing March 2026, breaking news broadcast graphics, world map with glowing red conflict zones, news broadcast style"

INPUT: "全球战场"
OUTPUT: "world map projection with glowing red hotspots marking battlefields, strategic military briefing visualization, dark background, professional graphics"

INPUT: "俄乌战场"
OUTPUT: "Eastern front battlefield, destroyed Russian tanks in frozen muddy field, winter landscape, smoke rising from ruins, gray overcast sky, war photography"

INPUT: "多线混战"
OUTPUT: "multiple battlefronts burning simultaneously, urban warfare chaos, destroyed buildings with fire and thick smoke, military helicopters overhead, action photography"

Now convert this:
"""

                user_prompt = f"Text: {sentence}\n\nOutput ONLY the English SD prompt, nothing else."
                
            else:
                system_prompt = """你是专业的图像提示词工程师。

任务：将中文配音文本转换为简洁的图像提示词。

严格规则（必须遵守）：
1. 只输出中文描述，禁止英文
2. 必须保留核心主体和动作
3. 总长度控制在20-40个中文字符
4. 禁止添加解释、禁止添加引号、禁止换行
5. 直接输出提示词，不要有任何前缀文字"""

                user_prompt = f"配音文本：{sentence}\n\n直接输出中文提示词，严格遵守以上规则。"
            
            config = llm_optimizer.get_optimal_config(task_complexity="medium")
            
            if not hasattr(self, '_ollama_config_logged') or not self._ollama_config_logged:
                self.log(f"🎯 优化模式: 本地大模型 | {prompt_type}")
                self.log(f"   候选模型数: {len(candidate_models)}个")
                self._ollama_config_logged = True
            
            optimized_prompt = None
            last_error = None
            successfully_used_model = None
            
            refusal_patterns = [
                "cannot provide", "can't provide", "cannot help", "can't help",
                "sorry", "unable to", "not able to", "I cannot", "I can't",
                "拒绝", "无法", "抱歉", "对不起"
            ]
            
            global ollama_lock
            
            for model in candidate_models:
                try:
                    self.log(f"   尝试使用模型: {model}")
                    response = ollama.chat(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ]
                    )
                    optimized_prompt = response["message"]["content"].strip()
                    
                    is_refusal = any(pattern in optimized_prompt.lower() for pattern in refusal_patterns)
                    if is_refusal:
                        last_error = Exception(f"模型 {model} 拒绝生成内容")
                        optimized_prompt = None
                        self.log(f"   ⚠️ 模型 {model} 拒绝生成内容，尝试下一个...")
                        continue
                    
                    if not optimized_prompt:
                        last_error = Exception(f"模型 {model} 返回空结果")
                        self.log(f"   ⚠️ 模型 {model} 返回空结果，尝试下一个...")
                        continue
                    
                    successfully_used_model = model
                    self.log(f"   ✅ 使用模型: {model}")
                    break
                except Exception as e:
                    last_error = e
                    self.log(f"   ⚠️ 模型 {model} 调用失败: {str(e)[:50]}")
                    continue
            
            if not optimized_prompt:
                self.log(f"❌ Ollama调用失败: {last_error}")
                return prompt
            
            # 清理输出
            optimized_prompt = optimized_prompt.strip()
            
            if is_sd:
                # 过滤模板式回复
                template_patterns = [
                    r"^here'?s? the",
                    r"^okay,? here",
                    r"^here is",
                    r"^here'?s? your",
                    r"^sure,? here",
                    r"^of course",
                    r"^here we go",
                    r"^as requested",
                    r"^prompts?:",
                    r"^sd prompt:",
                ]
                for pattern in template_patterns:
                    if re.search(pattern, optimized_prompt, re.IGNORECASE):
                        self.log(f"⚠️ 模型返回了模板式回复，使用原始提示词")
                        return prompt
                
                if re.search(r'[\u4e00-\u9fff]', optimized_prompt):
                    self.log(f"⚠️ 模型返回了中文，使用原始提示词")
                    return prompt
                
                optimized_prompt = re.sub(r'^(Prompt|提示词|SD)[:\s]*', '', optimized_prompt, flags=re.IGNORECASE)
                optimized_prompt = re.sub(r'^[\*\#\-\=\s]+', '', optimized_prompt)
                optimized_prompt = re.sub(r'["\']', '', optimized_prompt)
                optimized_prompt = optimized_prompt.strip()
                
                has_colon = ':' in optimized_prompt
                if has_colon:
                    parts = optimized_prompt.split(':', 1)
                    content_part = parts[0].strip()
                else:
                    content_part = optimized_prompt
                
                prompt_lower = content_part.lower()
                has_masterpiece = 'masterpiece' in prompt_lower
                has_best_quality = 'best quality' in prompt_lower
                
                temp_prompt = content_part
                if has_masterpiece:
                    temp_prompt = re.sub(r',?\s*[Mm]asterpiece\s*,?', ', ', temp_prompt)
                if has_best_quality:
                    temp_prompt = re.sub(r',?\s*[Bb]est [Qq]uality\s*,?', ', ', temp_prompt)
                temp_prompt = re.sub(r'^[\,\s]+', '', temp_prompt)
                temp_prompt = re.sub(r'[\,\s]+$', '', temp_prompt)
                temp_prompt = temp_prompt.strip()
                
                if temp_prompt:
                    optimized_prompt = f"{temp_prompt}, masterpiece, best quality"
                else:
                    optimized_prompt = prompt
                
                optimized_prompt = re.sub(r',\s*,', ',', optimized_prompt)
                optimized_prompt = re.sub(r'^\s*,\s*', '', optimized_prompt)
                optimized_prompt = re.sub(r'\s*,\s*$', '', optimized_prompt)
                optimized_prompt = optimized_prompt.strip()
            else:
                if re.search(r'[a-zA-Z]', optimized_prompt):
                    self.log(f"⚠️ 模型返回了英文，使用原始提示词")
                    return prompt
                
                optimized_prompt = re.sub(r'^(Prompt|提示词)[:\s]*', '', optimized_prompt, flags=re.IGNORECASE)
                optimized_prompt = re.sub(r'^[\*\#\-\=\s]+', '', optimized_prompt)
                optimized_prompt = re.sub(r'["\']', '', optimized_prompt)
                optimized_prompt = optimized_prompt.strip()
                optimized_prompt = re.sub(r'\s+', '', optimized_prompt)
                optimized_prompt = optimized_prompt.strip()
            
            duration = time.time() - start_time
            llm_optimizer.record_call(duration, True)
            
            self.log(f"⚡ 优化完成 ({duration:.1f}s): {optimized_prompt[:50]}...")
            
            self.cache_set('prompts', cache_key, optimized_prompt)
            
            return optimized_prompt
            
        except Exception as e:
            llm_optimizer.record_call(time.time() - start_time, False)
            self.log(f"⚠️ 优化失败: {e}")
            return prompt
    
    def analyze_mood(self, sentence):
        """分析句子情感基调"""
        positive_words = ['美好', '幸福', '快乐', '成功', '希望', '美丽', '温暖', '喜悦']
        negative_words = ['悲伤', '痛苦', '失败', '绝望', '黑暗', '寒冷', '恐惧', '愤怒']
        neutral_words = ['平静', '普通', '日常', '简单', '客观', '理性']

        pos_count = sum(1 for word in positive_words if word in sentence)
        neg_count = sum(1 for word in negative_words if word in sentence)
        neu_count = sum(1 for word in neutral_words if word in sentence)

        if pos_count > neg_count and pos_count > neu_count:
            return "积极/温暖"
        elif neg_count > pos_count and neg_count > neu_count:
            return "消极/沉重"
        else:
            return "中性/客观"

    def _optimize_prompts_with_global_context(self, shots, core_theme, visual_tone, theme_elements, content_type):
        """【新增】基于整体主题和氛围，对所有分镜提示词进行系统性优化
        
        流程：
        1. 收集所有分镜的当前提示词
        2. 整体分析核心主题和氛围
        3. 对每个分镜进行优化，使其更符合整体风格
        4. 确保主题元素贯穿始终
        """
        if not shots:
            return shots
        
        # 将主题元素转换为英文
        theme_elements_en = self._translate_theme_elements_to_english(theme_elements)
        
        # 构建优化系统提示
        system_prompt = f"""You are a professional AI prompt optimizer SPECIALIZED for absoluteRealisticVision v20 (ARV) model.

【ARV v20 模型特性 - 必须遵循】
- 擅长生成超写实人像和风景
- 偏好自然真实的光照效果
- 喜欢电影感画面和高对比度
- 适合新闻纪实、战争场景、科技感画面
- 必须使用以下基础标签：masterpiece, best quality, absolute realistic, photo-realistic, ultra detailed, 8K, HDR, cinematic lighting

【任务】基于整体主题和氛围，优化多个分镜的英文提示词，使其更适合ARV v20模型生成高质量写实图片。

【整体信息】
- 核心主题：{core_theme}
- 视觉基调：{visual_tone or '紧张、危机氛围'}
- 内容类型：{content_type}
- 主题元素：{', '.join(theme_elements_en)}

【核心优化策略 - 必须全部实现】

1. 【从抽象→具体】
   - 禁止使用抽象词如：panic, chaos, fear, crisis, tension
   - 必须转化为具体可视化场景：如 red warning lights, trading floor chaos, anxious faces

2. 【从单一→组合】
   - 禁止单个关键词：如 marketplace, technology, supply chain
   - 必须组合为完整场景：如 Wall Street trading floor, Silicon Valley tech headquarters

3. 【添加专业摄影参数】（至少选择2-3项）
   - 相机型号：Nikon D850, Canon 5D Mark IV, Sony A7R IV
   - 镜头：85mm lens, 50mm lens, wide angle, telephoto, macro
   - 光圈：f/1.8, f/2.8, f/4, f/5.6
   - 构图：close-up, medium shot, wide angle shot, split screen, aerial view, drone perspective

4. 【场景具体化】
   - 每个提示词必须有明确主体：交易员、工程师、新闻主播、军人等
   - 必须有具体环境：交易大厅、医院、工厂、战场、新闻直播间等
   - 添加环境描述：golden hour, twilight, dramatic lighting, natural lighting, sunset

5. 【ARV风格强化】
   - 添加电影感描述：cinematic composition, film grain, cinematic color grading
   - 添加写实感描述：photorealistic, hyper realistic, true-to-life
   - 添加细节描述：sharp focus, high detail, intricate details, texture

6. 【主题元素贯穿】
   - 必须合理分布主题元素：helium, semiconductor, medical, supply chain, geopolitical等

【输出格式】
请按以下JSON格式输出：
{{"0": "优化后的提示词1", "1": "优化后的提示词2", ...}}

注意：只输出JSON，不要有其他内容。"""

        # 收集当前所有分镜信息
        prompts_info = []
        for i, shot in enumerate(shots):
            desc = shot.get('description', '')
            prompt = shot.get('prompt_en', '')
            prompts_info.append(f"分镜{i+1} - 配音: {desc} - 当前提示词: {prompt}")
        
        user_prompt = "【所有分镜信息】\n" + "\n".join(prompts_info) + "\n\n请优化以上所有分镜的提示词："
        
        try:
            import ollama
            model = self.ollama_model_var.get()
            
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            result = response['message']['content'].strip()
            self.log(f"   🔍 大模型返回优化结果（预览）: {result[:200]}...")
            
            # 解析JSON结果
            import json
            import re
            
            # 尝试提取JSON
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                optimized_prompts = json.loads(json_match.group())
                
                # 应用优化结果
                for i, shot in enumerate(shots):
                    if str(i) in optimized_prompts:
                        old_prompt = shot.get('prompt_en', '')
                        new_prompt = optimized_prompts[str(i)]
                        shot['prompt_en'] = new_prompt
                        self.log(f"   🔄 分镜{i+1}提示词已优化")
                        self.log(f"      旧: {old_prompt[:60]}...")
                        self.log(f"      新: {new_prompt[:60]}...")
                
                return shots
            else:
                self.log(f"   ⚠️ 无法解析优化结果，保持原提示词")
                return shots
                
        except Exception as e:
            self.log(f"   ⚠️ 优化过程出错: {e}")
            return shots
    
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
            '科技': 'technology', '工业': 'industrial', '经济': 'economy'
        }
        
        result = []
        for elem in theme_elements:
            if elem in translations:
                result.append(translations[elem])
            else:
                result.append(elem)
        return result
    
    def _simplify_theme(self, theme_text):
        """简化核心主题：提取关键词，去除描述性内容
        
        例如："美军对伊朗的军事行动已进入第20天" → "军事行动"
        """
        if not theme_text:
            return theme_text
        
        import re
        
        # 去除常见描述性前缀
        prefixes_to_remove = [
            '这是一段关于', '本文讨论的是', '主要讲述', '主要内容是',
            '文章讲述', '本文介绍', '视频讲述', '这段音频讲述',
            '报道了', '介绍了', '讲述了', '关于',
        ]
        
        cleaned = theme_text
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        # 提取关键名词短语（人、地点、组织、事件）
        # 按优先级排序：长匹配在前
        key_patterns = [
            # 优先级1：具体国家/军队（最具体）
            '美军', '俄军', '伊军', '以军', '朝军', '韩军', '英军', '法军', '德军', '日军',
            # 优先级2：多国组合
            '美以', '美俄', '美中', '俄乌', '美伊', '以伊', '俄以',
            # 优先级3：具体组织
            '革命卫队', '联合国', '北约',
            # 优先级4：具体国家
            '伊朗', '美国', '俄罗斯', '中国', '以色列', '乌克兰',
            '英国', '法国', '德国', '日本', '朝鲜', '韩国',
            # 优先级5：抽象行动类型（放最后）
            '军事行动', '军队', '部队',
            # 优先级6：战争相关
            '战争', '冲突', '战斗', '袭击', '爆炸', '发射',
            # 优先级7：事件
            '制裁', '谈判', '迈入新阶段', '新阶段',
            # 优先级8：地点
            '中东', '欧洲', '亚洲', '美洲', '非洲', '太平洋', '印度洋',
        ]
        
        # 简单字符串匹配
        found_keywords = []
        for pattern in key_patterns:
            if pattern in cleaned:
                found_keywords.append(pattern)
        
        # 如果找到关键词，只保留前2个
        if found_keywords:
            return ' '.join(found_keywords[:2])
        
        # 如果没有匹配到任何模式，截取前10个字符
        if len(cleaned) > 10:
            cleaned = cleaned[:10]
        
        return cleaned
    
    def extract_theme_info(self, analysis_result):
        """从大模型分析结果中提取主题信息 - 支持新增的内容类型、视觉风格、场景建议"""
        theme_info = {
            'content_type': '',        # 新增：内容类型
            'core_theme': '',
            'visual_tone': '',
            'visual_style': '',        # 新增：视觉风格
            'theme_elements': [],
            'scene_suggestions': '',   # 新增：场景建议
            'emotional_tone': ''       # 新增：情感基调
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
                except:
                    pass

            # 提取视觉基调
            if '视觉基调' in cleaned_result:
                tone_match = cleaned_result.split('视觉基调')[1].split('\n')[0].replace('：', '').replace(':', '').strip()
                theme_info['visual_tone'] = tone_match

            # 提取视觉风格（新增）
            if '视觉风格' in cleaned_result:
                try:
                    style_match = cleaned_result.split('视觉风格')[1].split('\n')[0]
                    style_match = style_match.replace('：', '').replace(':', '').strip()
                    theme_info['visual_style'] = style_match
                except:
                    theme_info['visual_style'] = theme_info['visual_tone']  # 兜底使用视觉基调

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

            # 提取场景建议（新增）
            if '场景建议' in cleaned_result:
                try:
                    scene_match = cleaned_result.split('场景建议')[1].split('\n')[0]
                    scene_match = scene_match.replace('：', '').replace(':', '').strip()
                    theme_info['scene_suggestions'] = scene_match
                except:
                    theme_info['scene_suggestions'] = ''

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
        """验证分镜的主题一致性"""
        if not theme_info['core_theme']:
            return True, "未提取到主题信息，跳过一致性检查"

        consistency_issues = []

        # 检查每个分镜的提示词是否包含主题元素
        core_theme = theme_info['core_theme']
        theme_elements = theme_info['theme_elements']

        for i, shot in enumerate(shots):
            prompt = shot.get('prompt_en', '').lower()

            # 检查是否偏离主题（简单启发式检查）
            # 这里可以添加更复杂的语义相似度检查
            if theme_elements:
                has_theme_element = any(
                    elem.lower() in prompt or elem.lower() in shot.get('description', '').lower()
                    for elem in theme_elements
                )
                if not has_theme_element and i > 0:  # 第一个分镜可能不需要包含所有元素
                    consistency_issues.append(f"分镜{i+1}可能偏离主题")

        if consistency_issues:
            return False, f"发现{len(consistency_issues)}个一致性问题: {', '.join(consistency_issues[:3])}"

        return True, "主题一致性检查通过"
    
    def get_current_style(self):
        """获取当前选中的风格"""
        if hasattr(self, 'dlr_vars'):
            for style, var in self.dlr_vars:
                if var.get():
                    return style
        return "写实风格"

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
        """监控系统性能"""
        try:
            while getattr(self, 'perf_monitor_running', True):
                if psutil and GPUtil:
                    # 获取CPU使用率
                    cpu_usage = psutil.cpu_percent(interval=1)
                    # 获取内存使用率
                    memory = psutil.virtual_memory()
                    memory_usage = memory.percent
                    memory_used = memory.used // (1024 * 1024)  # 转换为MB
                    memory_total = memory.total // (1024 * 1024)  # 转换为MB
                    # 获取GPU使用率和显存使用情况
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu_usage = gpus[0].load * 100
                        gpu_memory_used = gpus[0].memoryUsed  # 显存使用量（MB）
                        gpu_memory_total = gpus[0].memoryTotal  # 显存总量（MB）
                        gpu_memory_percent = (gpu_memory_used / gpu_memory_total) * 100 if gpu_memory_total > 0 else 0
                    else:
                        gpu_usage = 0
                        gpu_memory_used = 0
                        gpu_memory_total = 0
                        gpu_memory_percent = 0
                    
                    # 更新UI（捕获 tkinter 组件已销毁的异常）
                    try:
                        if hasattr(self, 'cpu_label') and self.cpu_label.winfo_exists():
                            self.cpu_label.config(text=f"{cpu_usage:.1f}%")
                        if hasattr(self, 'memory_label') and self.memory_label.winfo_exists():
                            self.memory_label.config(text=f"{memory_usage:.1f}%")
                        if hasattr(self, 'gpu_label') and self.gpu_label.winfo_exists():
                            self.gpu_label.config(text=f"{gpu_memory_percent:.1f}%")
                        if hasattr(self, 'memory_detail_label') and self.memory_detail_label.winfo_exists():
                            self.memory_detail_label.config(text=f"{memory_used} MB / {memory_total} MB")
                    except tk.TclError:
                        # 组件已被销毁，退出循环
                        break
                time.sleep(2)
        except Exception as e:
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
    
    def add_task_to_queue(self, task_type, task_data=None, priority=None):
        """添加任务到队列"""
        try:
            if priority is None:
                priority = self.TASK_PRIORITY.get(task_type, 1)
            
            with self.task_lock:
                # 确保thread_pool字典中有必要的键
                if 'task_counter' not in self.thread_pool:
                    self.thread_pool['task_counter'] = 0
                if 'tasks' not in self.thread_pool:
                    self.thread_pool['tasks'] = {}
                
                task_id = self.thread_pool['task_counter']
                self.thread_pool['task_counter'] += 1
                
                task = {
                    'id': task_id,
                    'type': task_type,
                    'data': task_data,
                    'priority': priority,
                    'status': 'queued',
                    'created_at': datetime.datetime.now()
                }
                
                self.thread_pool['tasks'][task_id] = task
                self.thread_pool_stats['total_tasks'] += 1
                
                # 将任务添加到队列
                self.task_queue.append(task_id)
                
                # 如果当前没有任务在运行，执行队列中的任务
                if not self.task_running:
                    self.process_task_queue()
                
                return task_id
        except Exception as e:
            self.log(f"❌ 添加任务到队列失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
    
    def shutdown_thread_pool(self):
        """关闭线程池"""
        if hasattr(self, 'executor'):
            try:
                # 等待当前任务完成，最多等待5秒
                self.executor.shutdown(wait=True, cancel_futures=False)
                self.log("✅ 线程池已关闭")
            except TypeError:
                # Python 3.8 及以下版本不支持 cancel_futures 参数
                self.executor.shutdown(wait=True)
                self.log("✅ 线程池已关闭")

    def pause_task(self):
        """暂停当前任务"""
        with self.task_lock:
            if self.task_running and not self.task_paused:
                self.task_paused = True
                self.pause_event.clear()
                if self.current_task:
                    task = self.thread_pool['tasks'].get(self.current_task)
                    if task:
                        task['status'] = 'paused'
                self.log("⏸️ 任务已暂停")

    def resume_task(self):
        """恢复当前任务"""
        with self.task_lock:
            if self.task_paused:
                self.task_paused = False
                self.pause_event.set()
                if self.current_task:
                    task = self.thread_pool['tasks'].get(self.current_task)
                    if task:
                        task['status'] = 'running'
                self.log("▶️ 任务已恢复")

    def cancel_task(self):
        """取消当前任务"""
        with self.task_lock:
            if self.task_running or self.task_paused:
                self.task_paused = False
                self.pause_event.set()
                self.task_running = False
                if self.current_task:
                    task = self.thread_pool['tasks'].get(self.current_task)
                    if task:
                        task['status'] = 'cancelled'
                    self.current_task = None
                self.log("❌ 任务已取消")
                # 处理下一个任务
                self.process_task_queue()

    def on_close(self):
        """关闭窗口时的处理 - 增强版，确保快速退出"""
        try:
            self.log("🔄 正在关闭程序，清理资源...")
            
            # 1. 立即停止所有后台线程标志
            self.perf_monitor_running = False
            self.cache_cleanup_running = False
            self.task_running = False
            
            # 2. 取消所有 tkinter after 定时器
            try:
                if hasattr(self, 'resize_timer') and self.resize_timer:
                    self.root.after_cancel(self.resize_timer)
                    self.resize_timer = None
            except Exception:
                pass
            
            # 3. 保存配置（快速保存，不阻塞）
            try:
                self.save_config()
            except Exception:
                pass
            
            # 4. 停止所有活动任务
            try:
                with self.task_lock:
                    self.task_paused = False
                    self.pause_event.set()  # 唤醒可能暂停的任务
                    self.task_queue.clear()
                    self.current_task = None
            except Exception:
                pass
            
            # 5. 快速关闭线程池（不等待）
            try:
                if hasattr(self, 'executor'):
                    # 使用 cancel_futures=True 取消未开始的任务
                    try:
                        self.executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        # Python 3.8 及以下版本
                        self.executor.shutdown(wait=False)
            except Exception:
                pass
            
            # 6. 释放 Whisper 模型内存（异步，不阻塞）
            if self.whisper_model is not None:
                try:
                    import torch
                    del self.whisper_model
                    self.whisper_model = None
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
            
            # 7. 清理缓存数据
            self.shots_data = []
            self.cache_system = {}
            
            # 8. 强制垃圾回收
            import gc
            gc.collect()
            
            self.log("✅ 资源清理完成，正在退出...")
            
            # 9. 销毁窗口
            self.root.destroy()
            
        except Exception as e:
            print(f"关闭窗口时出错: {e}")
            try:
                self.root.destroy()
            except Exception:
                pass
        
        # 10. 释放控制台窗口（如果在 pythonw 模式下创建）
        try:
            # 检查是否在 pythonw 模式下运行或创建了控制台
            if hasattr(sys, 'executable') and 'pythonw' in sys.executable.lower():
                # 关闭标准输出和错误输出
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
                # 释放控制台窗口
                import ctypes
                ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
        
        # 11. 强制退出进程（确保不残留）
        # 使用 os._exit 而不是 sys.exit，跳过剩余的清理代码
        import os
        os._exit(0)
    
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
        import whisper
        import numpy as np
        import hashlib
        import gc
        import concurrent.futures
        
        # 初始化变量，防止 NameError
        analysis_result = ""
        theme_info = {}
        
        # 用于跟踪资源，确保清理
        resources_to_cleanup = []
        whisper_model_loaded = False  # 标记是否在本次调用中加载了模型
        
        try:
            # 检查是否有音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，无法生成分镜")
                self.update_task_progress("就绪")
                return
            
            self.log("=" * 50)
            self.log("🎬 开始一键生成分镜")
            self.log("=" * 50)
            
            # 清除上次任务残留的提示词缓存
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
            self.cache_clear('prompts')  # 清除提示词缓存
            self.log("🗑️ 已清除上次任务的提示词缓存")
            
            # 只在用户强制要求时清除全部缓存，否则复用音频分析缓存加快速度
            force_clear = getattr(self, '_force_clear_cache', False)
            if force_clear:
                self.cache_clear()
                self.log("🗑️ 已强制清除全部历史缓存")
                self._force_clear_cache = False
            else:
                cache_stats = self.get_cache_stats()
                self.log(f"📦 缓存状态: {cache_stats['hits']}命中, {cache_stats['misses']}未命中")
            
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
            else:
                # 加载Whisper模型进行语音识别
                self.log("🔊 正在加载Whisper模型...")
                self.update_task_progress("正在加载Whisper模型...", 20)
                if not self.whisper_model:
                    self.log("📦 正在加载Whisper模型...")
                    try:
                        # 检测是否有GPU可用，选择合适的模型加载方式
                        import torch
                        
                        # 详细显示GPU信息
                        if torch.cuda.is_available():
                            device = "cuda"
                            gpu_name = torch.cuda.get_device_name(0)
                            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
                            cuda_version = torch.version.cuda
                            self.log(f"🖥️ 使用GPU加速: {gpu_name}")
                            self.log(f"   CUDA版本: {cuda_version}")
                            self.log(f"   GPU显存: {gpu_memory:.1f} GB")
                            whisper_model = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
                            self.log(f"   使用模型: Whisper {whisper_model}")
                        else:
                            device = "cpu"
                            self.log(f"🖥️ 使用CPU模式 (GPU不可用)")
                            whisper_model = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
                            self.log(f"   使用模型: Whisper {whisper_model}")
                        
                        # 使用用户选择的模型
                        whisper_model = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
                        self.whisper_model = whisper.load_model(whisper_model, device=device)
                        whisper_model_loaded = True  # 标记模型是在本次调用中加载的
                        
                        if torch.cuda.is_available():
                            self.log(f"✅ Whisper {whisper_model}模型加载成功 (GPU加速)")
                        else:
                            self.log(f"✅ Whisper {whisper_model}模型加载成功 (CPU模式)")
                    except Exception as e:
                        self.log(f"⚠️ GPU加载失败，回退到CPU: {e}")
                        whisper_model = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
                        self.log(f"   使用模型: Whisper {whisper_model}")
                        try:
                            self.whisper_model = whisper.load_model(whisper_model, device="cpu")
                            self.log(f"✅ Whisper {whisper_model}模型加载成功 (CPU模式)")
                        except Exception as e2:
                            self.log(f"❌ 模型加载完全失败: {e2}")
                            self.update_task_progress("就绪")
                            return
                
                # 语音识别，启用标点符号（添加超时机制）
                self.update_task_progress("正在进行语音识别...", 30)
                try:
                    # 使用线程池添加超时控制
                    import concurrent.futures
                    
                    def transcribe_with_timeout():
                        return self.whisper_model.transcribe(
                            self.audio_path, 
                            language="zh", 
                            word_timestamps=True, 
                            fp16=False,
                            verbose=False
                        )
                    
                    # 设置10分钟超时
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(transcribe_with_timeout)
                        try:
                            result = future.result(timeout=600)  # 10分钟超时
                        except concurrent.futures.TimeoutError:
                            self.log("❌ 语音识别超时（超过10分钟），请检查音频文件")
                            self.update_task_progress("就绪")
                            return
                    
                    segments = result.get("segments", [])
                    self.log(f"✅ 语音识别完成，共 {len(segments)} 个片段")
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

            # 初始化theme_info
            theme_info = {'core_theme': '', 'visual_tone': '', 'theme_elements': []}
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
                    self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:5])}")
                
                self.log("✅ 主题提取完成，将直接使用原始语音片段创建分镜")
            else:
                # 动态检测Ollama服务是否可用
                if len(full_text) > 100:
                    # 尝试动态导入和检测Ollama服务
                    ollama_connected = False
                    try:
                        import ollama
                        # 尝试调用API检测服务是否响应
                        import requests
                        try:
                            response = requests.get("http://localhost:11434/api/tags", timeout=5)
                            if response.status_code == 200:
                                global OLLAMA_AVAILABLE
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
                                        response = requests.get("http://localhost:11434/api/tags", timeout=5)
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
                            
                            if theme_info.get('scene_suggestions'):
                                self.log(f"📍 场景建议: {theme_info['scene_suggestions']}")
                            
                            # 不生成分镜列表，跳到步骤3直接使用原始语音片段
                            self.log("✅ 主题分析完成，将直接使用原始语音片段创建分镜")
                        
                        except Exception as e:
                            self.log(f"   ⚠️ 大模型分析过程出错: {str(e)[:100]}")
                            self.log("   将使用原始语音片段创建分镜")
                            theme_info = {
                                'content_type': '', 
                                'core_theme': '', 
                                'visual_tone': '', 
                                'theme_elements': [],
                                'visual_style': '',
                                'scene_suggestions': '',
                                'emotional_tone': ''
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
            
            # 预先为所有分镜生成提示词（无论是否有缓存都要执行）
            pregenerated_prompts = {}
            
            self.log("\n🎨 预先为所有分镜生成提示词...")
            
            if not original_shot_tasks:
                self.log("   ⚠️ 没有原始分镜数据")
            
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
                # 用户预设了风格，生成风格描述
                self.log(f"🎨 用户预设风格: {', '.join(user_selected_styles)}")
                style_descriptions = []
                for style in user_selected_styles:
                    style_desc = self.generate_style_description(style)
                    if style_desc:
                        style_descriptions.append(style_desc)
                if style_descriptions:
                    user_style_override = ", ".join(style_descriptions)
                    # 简洁显示风格关键词
                    display_style = user_style_override[:80] + "..." if len(user_style_override) > 80 else user_style_override
                    self.log(f"   风格关键词: {display_style}")
            
            self.log(f"   开始为 {len(original_shot_tasks)} 个分镜生成提示词...")
            
            start_time = time.time()
            
            # 4线程并发生成提示词
            max_workers = 4
            failed_count = 0
            
            def generate_single_prompt(idx_task):
                """单个提示词生成任务"""
                idx, task = idx_task
                try:
                    dubbing = task.get('text', '')
                    if dubbing:
                        # 获取纠错字典
                        correction_dict = theme_info.get('correction_dict', {})
                        
                        # 对分镜描述文本进行纠错
                        if correction_dict:
                            corrected_dubbing = dubbing
                            for old, new in correction_dict.items():
                                corrected_dubbing = corrected_dubbing.replace(old, new)
                            task['text'] = corrected_dubbing
                            task['original_text'] = dubbing
                        
                        # 如果用户预设了风格，使用用户预设的风格；否则使用主题分析推荐的风格
                        effective_visual_style = user_style_override if user_style_override else theme_info.get('visual_style', '')
                        
                        # 使用纠错后的文本生成提示词
                        prompt = self._generate_prompt_with_llm(
                            task.get('text', dubbing), 
                            content_type=theme_info.get('content_type', ''), 
                            prompt_type=user_prompt_type,
                            core_theme=theme_info.get('core_theme', ''),
                            visual_tone=theme_info.get('visual_tone', ''),
                            theme_elements=theme_info.get('theme_elements', []),
                            visual_style=effective_visual_style,
                            scene_suggestions=theme_info.get('scene_suggestions', ''),
                            original_dubbing=dubbing  # 传入原始文本用于参考
                        )
                        return (idx, prompt, None)
                    return (idx, "", None)
                except Exception as e:
                    import traceback
                    full_error = f"{str(e)}\n{traceback.format_exc()}"
                    return (idx, "", full_error)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                results = list(executor.map(generate_single_prompt, enumerate(original_shot_tasks)))
                
                for idx, prompt, error in results:
                    if error:
                        failed_count += 1
                        # 显示前500字符的错误信息
                        error_display = error[:500] if len(error) > 500 else error
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
            
            # 存储预生成的提示词供后续使用
            self._pregenerated_prompts = pregenerated_prompts
            
            # 步骤3: 解析和校准分镜
            self.log("\n📍 步骤 3/4: 解析和校准分镜")

            # 如果theme_info还没有从步骤2获取，则重新提取
            if not theme_info.get('core_theme') and not theme_info.get('visual_tone'):
                theme_info = self.extract_theme_info(analysis_result) if analysis_result else theme_info
            
            # 最终简化主题（兜底处理）
            if theme_info.get('core_theme'):
                final_theme = self._simplify_theme(theme_info['core_theme'])
                if final_theme != theme_info['core_theme']:
                    theme_info['core_theme'] = final_theme
            
            # 显示主题信息
            user_custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
            user_custom_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
            
            display_theme = user_custom_theme if user_custom_theme else theme_info.get('core_theme', '')
            display_tone = user_custom_tone if user_custom_tone else theme_info.get('visual_tone', '')
            
            if display_theme:
                self.log(f"🎯 核心主题: {display_theme}")
            if display_tone:
                self.log(f"🎨 视觉基调: {display_tone}")
            if theme_info.get('theme_elements'):
                self.log(f"✨ 主题元素: {', '.join(theme_info['theme_elements'][:5])}")

            # 直接使用原始语音片段创建分镜（跳过sentence列表）
            self.log(f"📊 共 {len(original_shot_tasks)} 个原始语音片段")
            
            # 使用原始语音片段创建分镜
            self.update_task_progress("正在创建分镜...", 80)
            self.log(f"📝 直接使用原始语音片段创建分镜")
            self.log(f"   共 {len(original_shot_tasks)} 个分镜")
            
            # 直接使用 original_shot_tasks（每个原始片段一个分镜）
            shot_tasks = []
            for i, task in enumerate(original_shot_tasks):
                shot_text = task['text']
                shot_content_type = task.get('content_type', 'general')
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
            
            # 优化：增加并发线程数以提高处理速度
            cpu_count = os.cpu_count() or 4
            thread_count = min(cpu_count * 4, 32)  # 增加并发上限以加速处理
            
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
                self.log(f"   🔧 获取到纠错字典: {correction_dict}")
            
            def create_shot_task(task_data):
                idx, shot_start, shot_end, shot_text, shot_type = task_data
                
                # 对分镜描述文本进行纠错
                if correction_dict and shot_text:
                    original_text = shot_text
                    for old, new in correction_dict.items():
                        shot_text = shot_text.replace(old, new)
                    if shot_text != original_text:
                        self.log(f"   🔄 分镜{idx+1}纠错: {original_text[:20]}... → {shot_text[:20]}...")
                
                shot = self.create_new_shot(
                    idx, shot_start, shot_end, shot_text, shot_type,
                    core_theme=core_theme,
                    visual_tone=visual_tone,
                    theme_elements=theme_elements
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

            # 合并时长过短的分镜（低于1.5秒）
            self.log("🔍 检查并合并短分镜...")
            shots = self.merge_short_shots(shots, min_duration=1.5)
            self.log(f"   📊 最终分镜数: {len(shots)} 个")

            # 验证分镜主题一致性（如果大模型分析成功）
            if theme_info.get('core_theme'):
                is_consistent, consistency_msg = self.validate_theme_consistency(shots, theme_info)
                if is_consistent:
                    self.log(f"✅ {consistency_msg}")
                else:
                    self.log(f"⚠️ {consistency_msg}")
                    self.log(f"💡 建议: 检查分镜提示词是否围绕主题'{theme_info['core_theme']}'展开")

            # 【新增】整体优化：基于核心主题和氛围，优化所有分镜的提示词
            if theme_info.get('core_theme') and shots and len(shots) > 0:
                self.log("\n🎨 基于整体主题和氛围优化分镜提示词...")
                self.update_task_progress("正在优化提示词...", 75)
                
                try:
                    optimized_shots = self._optimize_prompts_with_global_context(
                        shots, 
                        theme_info.get('core_theme', ''),
                        theme_info.get('visual_tone', ''),
                        theme_info.get('theme_elements', []),
                        theme_info.get('content_type', 'general')
                    )
                    if optimized_shots:
                        shots = optimized_shots
                        self.log(f"✅ 已完成 {len(shots)} 个分镜提示词的优化")
                except Exception as e:
                    self.log(f"⚠️ 提示词优化失败: {e}")
            
            # 检查分镜是否为空
            if not shots:
                self.log("❌ 未能生成分镜，请检查音频文件是否正确")
                self.update_task_progress("就绪")
                messagebox.showwarning("警告", "未能生成分镜，请检查音频文件是否正确")
                return
            
            # 步骤4: 保存和完成
            self.log("\n📍 步骤 4/4: 保存分镜数据")
            self.update_task_progress("正在保存分镜数据...", 90)
            
            # 获取音频总时长
            audio_total_duration = segments[-1].get("end", 0) if segments else 0
            
            # 验证时间戳完整性
            self.log("🔍 验证时间戳完整性...")
            total_shots_duration = sum(s['duration'] for s in shots)
            
            if abs(total_shots_duration - audio_total_duration) > 0.1:
                self.log(f"   ⚠️ 时长差异: 分镜{total_shots_duration:.2f}s vs 音频{audio_total_duration:.2f}s")
                shots = self.adjust_shot_durations(shots, audio_total_duration)
                self.log(f"   ✅ 已调整分镜时长以匹配音频")
            else:
                self.log(f"   ✅ 时间戳验证通过")
            
            # 检测时间间隔（用于视频合成）
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
            
            # 统一数据存储
            self.shots_data = shots
            self.state_manager['shots']['generated'] = True
            self.state_manager['shots']['count'] = len(shots)
            self.state_manager['shots']['data'] = None
            
            # 保存分镜数据到文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump(shots, f, ensure_ascii=False, indent=2)
            
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
            
            # 显示分镜内容到脚本区域
            if hasattr(self, 'txt_script'):
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
            
            # 更新进度为完成
            self.update_task_progress("分镜生成完成", 100)
        
        except Exception as e:
            self.log(f"❌ 生成分镜失败: {e}")
            import traceback
            traceback.print_exc()
            self.update_task_progress("生成失败", 0)
            return []
        finally:
            # 释放Whisper模型内存
            if whisper_model_loaded and hasattr(self, 'whisper_model') and self.whisper_model:
                try:
                    del self.whisper_model
                    self.whisper_model = None
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    self.log("🧹 Whisper模型已卸载，内存已释放")
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
                options_response = requests.get(f"{api_url}/sdapi/v1/options", timeout=5)
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
                models_response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=5)
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
                
                if os.path.exists(image_path):
                    skipped_count += 1
                    continue
                
                enhanced_prompt = prompt
                if style_descriptions:
                    style_text = ", ".join(style_descriptions)
                    enhanced_prompt = f"{prompt}, {style_text}"
                
                tasks.append((shot_id, enhanced_prompt, image_file, image_path, description))
            
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
                        models_response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=10)
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
                        switch_response = requests.post(
                            f"{api_url}/sdapi/v1/options", 
                            json={"sd_model_checkpoint": target_model}, 
                            timeout=30
                        )
                        if switch_response.status_code == 200:
                            # 确认切换成功
                            confirm_response = requests.get(f"{api_url}/sdapi/v1/options", timeout=5)
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
                shot_id, enhanced_prompt, image_file, image_path, description = task
                
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
                            "negative_prompt": "",
                            "width": gen_width,
                            "height": gen_height,
                            "steps": 25,
                            "cfg_scale": 7.0,
                            "sampler_name": "DPM++ 2M Karras",  # 使用带 Karras 的正确名称
                            "seed": -1,
                            "batch_size": 1
                        }
                        
                        # 发送请求（超时90秒）
                        response = requests.post(f"{api_url}/sdapi/v1/txt2img", json=payload, timeout=90)
                        
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
            
            # 串行生成图像
            if tasks:
                self.log("")
                self.log(f"🚀 开始生成 {len(tasks)} 张图像...")
                self.log("")
                results = []
                for i, task in enumerate(tasks):
                    if not self.pause_event.is_set():
                        self.log("⏸️ 任务已暂停，等待恢复...")
                        self.pause_event.wait()
                    
                    if not self.task_running:
                        self.log("❌ 任务已被取消")
                        break
                    
                    progress = 40 + (i / len(tasks)) * 50
                    self.update_task_progress(f"生成图像 {i+1}/{len(tasks)}...", progress)
                    
                    result = generate_single_image(task)
                    results.append(result)
                    time.sleep(0.3)
                
                generated_count = sum(results)
                failed_count = len(results) - generated_count
                
                self.log("")
                self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                self.log(f"📊 生成结果: 成功 {generated_count} 张, 失败 {failed_count} 张")
                self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            else:
                self.log("")
                self.log("⚠️ 所有图像已存在，无需重新生成")
                generated_count = 0
            
            self.update_task_progress("图像生成完成", 100)
            self.state_manager['images']['generated'] = True
            self.state_manager['images']['count'] = generated_count
            
        except Exception as e:
            self.log(f"❌ 图像生成失败: {e}")
            import traceback
            traceback.print_exc()
    
    def clear_images_and_videos(self):
        """清除图片和视频文件"""
        self.log("🗑️ 开始清除图片和视频文件...")
        try:
            import os
            
            # 清除图片文件夹内的所有图片
            if os.path.exists(self.images_dir):
                for file in os.listdir(self.images_dir):
                    file_path = os.path.join(self.images_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        self.log(f"✅ 已删除图片: {file}")
            
            # 清除输出文件夹内的所有视频
            if os.path.exists(self.output_dir):
                for file in os.listdir(self.output_dir):
                    file_path = os.path.join(self.output_dir, file)
                    if os.path.isfile(file_path) and file.endswith('.mp4'):
                        os.remove(file_path)
                        self.log(f"✅ 已删除视频: {file}")
            
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
                    self.generate_images()
                    
                    # 再次检查
                    missing_count = sum(1 for shot in self.shots_data 
                                       if not os.path.exists(os.path.join(self.images_dir, shot['image_file'])))
                    if missing_count > 0:
                        self.log(f"❌ 仍有 {missing_count} 张图片缺失，无法生成视频")
                        self.update_task_progress("就绪")
                        return
            
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
            self.log(f"🎬 动画效果: {animation_type if animation_type != '无' else '无'}")
            
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
                    orig_img = Image.open(image_path)
                    
                    # 调整图片尺寸
                    img = self._resize_image_to_fit(orig_img, width, height)
                    
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
            
            # 始终使用 CompositeVideoClip 精确定位，保持音画同步
            background = ColorClip(size=(width, height), color=(0, 0, 0), duration=audio_duration)
            final_clip = CompositeVideoClip([background] + clips, size=(width, height))
            
            self.log(f"✅ 视频片段合成完成: {len(clips)} 个")
            
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
            except Exception:
                pass
            
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
        """预渲染缩放动画效果 - 在生成时直接渲染帧序列
        
        注意：此函数返回新片段，会丢失原片段的 start 属性
              调用方必须在调用此函数后重新设置 with_start()
        """
        try:
            import numpy as np
            from PIL import Image
            from moviepy import ImageSequenceClip
            
            # 保存原始时长
            original_duration = clip.duration
            
            # 边界检查：时长无效时直接返回原片段
            if not original_duration or original_duration <= 0:
                self.log("⚠️ 动画片段时长无效，跳过动画效果")
                return clip
            
            frames = []
            fps = 30
            num_frames = max(1, int(original_duration * fps))  # 至少1帧
            w, h = clip.size
            
            for frame_idx in range(num_frames):
                t = frame_idx / fps
                frame = clip.get_frame(t)
                
                if isinstance(frame, np.ndarray):
                    img = Image.fromarray(frame)
                else:
                    img = frame
                
                # 缩放：从 1.0 到 1.05 的缓慢放大效果
                scale = 1.0 + 0.05 * (t / original_duration)
                new_w = int(w * scale)
                new_h = int(h * scale)
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                
                # 裁剪回原始尺寸（居中裁剪）
                if new_w > w:
                    left = (new_w - w) // 2
                    top = (new_h - h) // 2
                    resized = resized.crop((left, top, left + w, top + h))
                
                frames.append(np.array(resized))
            
            # 创建新片段，确保时长与原始一致
            animated_clip = ImageSequenceClip(frames, fps=fps)
            
            # 验证时长
            if abs(animated_clip.duration - original_duration) > 0.01:
                # 如果时长有偏差，强制设置为原始时长
                animated_clip = animated_clip.with_duration(original_duration)
            
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
            # 释放Whisper模型内存
            if self.whisper_model is not None:
                self.log("🔄 释放Whisper模型内存...")
                import gc
                import torch
                # 删除模型引用
                del self.whisper_model
                self.whisper_model = None
                # 强制垃圾回收
                gc.collect()
                # 清空CUDA缓存（如果可用）
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                self.log("✅ Whisper模型内存已释放")
            
            # 清除音频路径
            self.audio_path = None
            self.shots_data = []  # 清除分镜数据
            
            # 更新状态
            self.state_manager['audio']['loaded'] = False
            self.state_manager['audio']['path'] = None
            self.state_manager['audio']['duration'] = 0
            self.state_manager['shots']['generated'] = False
            self.state_manager['shots']['count'] = 0
            self.state_manager['shots']['data'] = []
            
            # 更新UI
            if hasattr(self, 'lbl_audio_status'):
                def update_ui():
                    try:
                        self.lbl_audio_status.config(text="未加载音频")
                        # 清空脚本区域
                        if hasattr(self, 'txt_script'):
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
        
        工作流程：
        1. 检查音频文件
        2. 检查分镜数据（如果没有则自动生成）
        3. 清除旧图片
        4. 调用SD生成所有图片
        5. 合成视频
        
        如果用户没有先生成分镜，此功能会自动完成全流程。
        """
        try:
            self.log("🎞️ 开始跑图生成视频...")
            
            # 检查音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，请先导入音频")
                return
            
            if not os.path.exists(self.audio_path):
                self.log(f"❌ 音频文件不存在: {self.audio_path}")
                self.log("   请重新导入音频文件")
                return
            
            # 检查是否有分镜数据（内存中或文件中）
            has_shots_data = False
            if hasattr(self, 'shots_data') and self.shots_data:
                has_shots_data = True
            else:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    has_shots_data = True
            
            # 启动渲染线程
            def render_video_worker():
                self.task_running = True
                self.pause_event.set()
                try:
                    # ========== 阶段1: 分镜准备 ==========
                    if not has_shots_data:
                        self.log("")
                        self.log("━" * 50)
                        self.log("📋 阶段1: 自动生成分镜脚本")
                        self.log("━" * 50)
                        self.log("⚠️ 未检测到分镜数据，正在自动生成...")
                        
                        # 调用生成分镜的核心函数（自动模式，不显示弹窗）
                        self.generate_shots(auto_mode=True)
                        
                        # 检查分镜是否生成成功
                        if not hasattr(self, 'shots_data') or not self.shots_data:
                            self.log("❌ 分镜生成失败，无法继续")
                            self.update_task_progress("就绪")
                            return
                        
                        self.log(f"✅ 分镜生成完成: {len(self.shots_data)} 个分镜")
                    else:
                        # 加载已有的分镜数据
                        if not hasattr(self, 'shots_data') or not self.shots_data:
                            shots_file = os.path.join(self.output_dir, "shots_data.json")
                            if os.path.exists(shots_file):
                                with open(shots_file, 'r', encoding='utf-8') as f:
                                    self.shots_data = json.load(f)
                                self.log(f"📂 已加载分镜数据: {len(self.shots_data)} 个分镜")
                        
                        self.log(f"✅ 已有分镜数据: {len(self.shots_data)} 个分镜")
                    
                    # ========== 阶段2: 生成图片 & 合成视频 ==========
                    self.log("")
                    self.log("━" * 50)
                    self.log("🖼️ 阶段2: 生成图片 & 合成视频")
                    self.log("━" * 50)
                    
                    # 跑图模式：skip_clear=False 清除旧图片，skip_image_check=False 检查并生成图片
                    self.generate_video(skip_clear=False, skip_image_check=False)
                    
                except Exception as e:
                    self.log(f"❌ 渲染视频出错: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    self.task_running = False
                    # 清除预生成提示词缓存
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
            
            thread = threading.Thread(target=render_video_worker, daemon=True)
            thread.start()
            self.log("✅ 渲染线程已启动")
        except Exception as e:
            self.log(f"❌ 渲染视频线程启动失败: {e}")
            import traceback
            traceback.print_exc()
    
    def direct_render_video(self):
        """直接渲染视频 - 所有检查和渲染都在后台线程执行，避免阻塞 UI"""
        
        # 快速预检查（仅检查关键变量是否存在，不进行 IO 操作）
        if not self.audio_path:
            self.log("❌ 错误: 请先导入音频文件")
            messagebox.showerror("缺少音频", "请先导入音频文件")
            return
        
        # 启动后台线程执行完整流程
        def direct_render_worker():
            try:
                self.log("🎞️ 开始直接渲染视频...")
                self.task_running = True
                self.pause_event.set()
                
                # === 所有检查都在后台线程执行 ===
                
                # 检查1: 音频文件是否存在
                if not self.audio_path or not os.path.exists(self.audio_path):
                    self.log("❌ 错误: 音频文件不存在")
                    self.root.after(0, lambda: messagebox.showerror("缺少音频", "请先导入音频文件"))
                    return
                
                # 检查2: 是否存在分镜脚本数据
                if not hasattr(self, 'shots_data') or not self.shots_data:
                    shots_file = os.path.join(self.output_dir, "shots_data.json")
                    if os.path.exists(shots_file):
                        try:
                            with open(shots_file, 'r', encoding='utf-8') as f:
                                self.shots_data = json.load(f)
                            for shot in self.shots_data:
                                if 'description' in shot and shot['description']:
                                    shot['description'] = self.clean_text(shot['description'])
                            self.log(f"📂 从文件加载了分镜数据: {len(self.shots_data)} 个分镜")
                        except Exception as e:
                            self.log(f"⚠️ 加载分镜数据失败: {e}")
                            self.shots_data = []
                
                if not hasattr(self, 'shots_data') or not self.shots_data:
                    self.log("❌ 错误: 没有分镜脚本数据")
                    self.root.after(0, lambda: messagebox.showerror("缺少分镜脚本", "请先生成分镜脚本"))
                    return
                
                # 检查3: 图片文件夹
                if not os.path.exists(self.images_dir):
                    self.log("❌ 错误: 图片文件夹不存在")
                    self.root.after(0, lambda: messagebox.showerror("错误", "图片文件夹不存在"))
                    return
                
                # 检查4: 获取图片文件并创建映射
                import re
                image_files = [f for f in os.listdir(self.images_dir) if f.endswith('.png') or f.endswith('.jpg')]
                if not image_files:
                    self.log("❌ 错误: 没有找到图片文件")
                    self.root.after(0, lambda: messagebox.showerror("错误", "没有找到图片文件"))
                    return
                
                self.log(f"📁 找到 {len(image_files)} 个图片文件")
                
                # 创建图片序号映射
                def extract_number(filename):
                    match = re.search(r'\d+', filename)
                    return int(match.group()) if match else None
                
                image_map = {}
                for img_file in image_files:
                    num = extract_number(img_file)
                    if num:
                        image_map[num] = img_file
                
                # 检查5: 图片数量是否与分镜脚本数量一致
                expected_shots = len(self.shots_data)
                if len(image_map) != expected_shots:
                    self.log(f"⚠️ 警告: 图片数量({len(image_map)})与分镜数量({expected_shots})不一致")
                
                # 检查6: 确保所有分镜都有对应的图片
                missing_shots = []
                for i, shot in enumerate(self.shots_data):
                    expected_num = i + 1
                    if expected_num not in image_map:
                        missing_shots.append(expected_num)
                
                if missing_shots:
                    error_msg = f"❌ 缺少图片序号: {', '.join(map(str, missing_shots[:10]))}"
                    if len(missing_shots) > 10:
                        error_msg += f" ... 共 {len(missing_shots)} 个"
                    self.log(error_msg)
                    self.root.after(0, lambda: messagebox.showerror("缺少图片", error_msg))
                    return
                
                # === 执行视频生成 ===
                self.generate_video(skip_clear=True, use_original_resolution=True, skip_image_check=True)
                
            except Exception as e:
                self.log(f"❌ 直接渲染视频失败: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self.task_running = False
                
                # 视频生成完成后显示通知
                def show_completion():
                    try:
                        messagebox.showinfo(
                            "🎉 任务完成",
                            "视频生成已完成！\n\n您可以在输出文件夹中查看生成的视频文件。",
                            icon='info'
                        )
                    except Exception:
                        pass
                
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, show_completion)
        
        # 启动后台线程
        thread = threading.Thread(target=direct_render_worker, daemon=True)
        thread.start()
        self.log("✅ 渲染任务已启动，请在后台查看进度...")
    
    def generate_shots_threaded(self):
        """线程化生成分镜 - 修复线程安全问题"""
        try:
            # 初始化任务锁（如果尚未初始化）
            if not hasattr(self, '_task_lock'):
                self._task_lock = threading.Lock()
            
            # 使用锁检查任务状态，防止重复启动
            with self._task_lock:
                if self.task_running:
                    self.log("⚠️ 任务正在运行中，请勿重复点击")
                    messagebox.showwarning("提示", "任务正在运行中，请等待当前任务完成")
                    return
                
                # 标记任务开始
                self.task_running = True
                self.current_task_thread = None
            
            # 立即更新UI，显示任务开始
            self.log("🎬 开始线程化生成分镜...")
            
            # 自动清除旧的分镜脚本内容
            if hasattr(self, 'txt_script') and self.txt_script:
                def clear_script():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception as e:
                        self.log(f"⚠️ 清除脚本失败: {e}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, clear_script)
            
            # 启动一个新线程来执行生成分镜的任务
            def generate_shots_worker():
                self.pause_event.set()  # 确保事件被设置
                self.log("🎬 开始生成分镜...")
                try:
                    self.generate_shots()
                except Exception as e:
                    self.log(f"❌ 生成分镜过程中出错: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 任务完成后重置状态（使用锁保护）
                    with self._task_lock:
                        self.task_running = False
                        self.current_task_thread = None
                    # 清除预生成提示词缓存
                    if hasattr(self, '_pregenerated_prompts'):
                        delattr(self, '_pregenerated_prompts')
                    self.log("✅ 分镜生成任务结束")
            
            # 使用更高优先级的线程
            thread = threading.Thread(target=generate_shots_worker, daemon=True, name="GenerateShotsThread")
            thread.start()
            
            # 保存线程引用
            with self._task_lock:
                self.current_task_thread = thread
                
        except Exception as e:
            self.log(f"❌ 生成分镜线程启动失败: {e}")
            import traceback
            traceback.print_exc()
            # 确保状态重置
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
        """设置脚本区域"""
        # 创建脚本区域
        script_frame = ttk.LabelFrame(self.top_frame, text="分镜脚本", padding=15)
        script_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建脚本控制栏
        script_control_frame = ttk.Frame(script_frame)
        script_control_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 添加清除脚本按钮
        btn_clear_script = ttk.Button(script_control_frame, text="🗑️ 清除脚本", command=self.clear_script, style="Small.TButton")
        btn_clear_script.pack(side=tk.RIGHT, padx=5)
        
        # 创建脚本文本框
        self.txt_script = tk.Text(script_frame, wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4", font=('Microsoft YaHei', self.font_size + 4))
        self.txt_script.pack(fill=tk.BOTH, expand=True)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.txt_script, command=self.txt_script.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_script.config(yscrollcommand=scrollbar.set)
        
        # 添加初始提示
        self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
    
    def setup_log_area(self):
        """设置日志区域"""
        # 创建日志区域
        log_frame = ttk.LabelFrame(self.bottom_frame, text="运行日志", padding=15)
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
        """记录日志"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        # 确保在主线程中更新UI
        def update_ui():
            if hasattr(self, 'txt_log') and self.txt_log:
                try:
                    self.txt_log.insert(tk.END, log_message + '\n')
                    self.txt_log.see(tk.END)
                except Exception as e:
                    pass
        
        # 使用after方法确保在主线程中执行
        if hasattr(self, 'root') and self.root:
            self.root.after(0, update_ui)
    
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
                    
                # 加载Ollama模型设置 - 使用配置文件中的值，而不是写死
                if hasattr(self, 'ollama_model_var'):
                    if 'ollama_model' in config and config['ollama_model']:
                        self.ollama_model_var.set(config['ollama_model'])
                        self.log(f"✅ 已加载Ollama模型: {config['ollama_model']}")
                    else:
                        # 配置文件中没有则使用默认值
                        self.ollama_model_var.set("gemma3:4b")
                    
                if 'llm_config_preset' in config and config['llm_config_preset']:
                    preset = config['llm_config_preset']
                    self.llm_config_preset_var.set(preset)
                    self.current_llm_config.apply_preset(preset)
                    if hasattr(self, 'llm_config_desc_var'):
                        self.llm_config_desc_var.set(LLMConfig.PRESETS.get(preset, {}).get('description', ''))
                else:
                    self.llm_config_preset_var.set("质量优先")
                    self.current_llm_config.apply_preset("质量优先")
                    if hasattr(self, 'llm_config_desc_var'):
                        self.llm_config_desc_var.set(LLMConfig.PRESETS.get("质量优先", {}).get('description', ''))
                
                # 加载音频模型（Whisper）设置
                if 'whisper_model' in config and config['whisper_model']:
                    # 确保变量存在
                    if not hasattr(self, 'whisper_model_var'):
                        self.whisper_model_var = tk.StringVar(value=config['whisper_model'])
                    else:
                        self.whisper_model_var.set(config['whisper_model'])
                    self.log(f"✅ 已加载音频模型: {config['whisper_model']}")
                elif hasattr(self, 'whisper_model_var'):
                    self.whisper_model_var.set("medium")
                else:
                    self.whisper_model_var = tk.StringVar(value="medium")
                
                # 加载视频设置 - 如果没有则使用默认值"硬切"
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
                        self.log(f"✅ 已加载核心主题: {config['custom_theme']}")
                if 'custom_visual_tone' in config:
                    if hasattr(self, 'custom_visual_tone_var'):
                        self.custom_visual_tone_var.set(config['custom_visual_tone'])
                        self.log(f"✅ 已加载视觉基调: {config['custom_visual_tone']}")
                
                # 加载提示词类型设置
                if 'prompt_type' in config and hasattr(self, 'prompt_type_var'):
                    self.prompt_type_var.set(config['prompt_type'])
                    self.log(f"✅ 已加载提示词类型: {config['prompt_type']}")
                
                # 加载动画类型设置
                if 'animation' in config and hasattr(self, 'animation_var'):
                    self.animation_var.set(config['animation'])
                
                self.log("✅ 配置加载完成")
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
                'whisper_model': self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else 'medium',
                'transition': self.transition_var.get(),
                'selected_styles': selected_styles,
                'custom_theme': self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else '',
                'custom_visual_tone': self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else '',
                'prompt_type': self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else 'SD提示词',
                'animation': self.animation_var.get() if hasattr(self, 'animation_var') else '无'
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