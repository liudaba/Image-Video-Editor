import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
import datetime
import warnings
import multiprocessing
import sys

# 添加src目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

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
time = None
ThreadPoolExecutor = None

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
        
    def record_call(self, duration, success, token_count=0):
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
        
        # 导入time模块
        import time as _time
        
        results = {}
        
        def call_single_model(model_name):
            """调用单个模型"""
            try:
                start_time = _time.time()
                
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
                    ],
                    options=config.get_options(num_predict=1500)
                )
                
                duration = _time.time() - start_time
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


# ==================== 高级提示词模板系统 ====================
class PromptTemplates:
    """高级提示词模板系统 - 释放大模型最大潜力"""
    
    # 提示词优化模板
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
    
    # 分镜分析模板 - SD提示词版本（英文）
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

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其深层含义和情感色彩
2. 合理拆分：根据语义完整性和叙述逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合口语化表达
4. 语义-视觉映射：将抽象语义转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定核心主题后（如"战争类评论文章"），所有画面必须围绕该主题构图
2. 元素选择：根据文本语义，添加与主题相关的视觉元素
   - 战争主题：战场、军装、武器、旗帜、硝烟、废墟、和平鸽、纪念碑等
   - 历史主题：古籍、文物、历史人物、时代场景、文献资料等
   - 科技主题：实验室、设备、数据可视化、未来场景等
   - 自然主题：山川、河流、森林、季节变化、天气现象等
   - 城市主题：建筑、街道、交通、人群、夜景灯光等
   - 人文主题：人物表情、动作、互动、文化符号等
3. 视觉隐喻：使用象征性视觉元素表达抽象概念
4. 构图统一：保持镜头语言、视角、景深的一致性

【视觉联想深度引导 - 每张画都要思考】
请为每张分镜进行以下6个维度的深度视觉联想：

1. 主体元素联想：
   - 核心主体是什么？（人物、物体、场景等）
   - 主体的细节特征？（外观、材质、状态、动作、表情等）
   - 主体在画面中的位置和比例？（中心、前景、背景等）

2. 环境场景联想：
   - 主体需要什么环境背景？（室内/室外、城市/乡村、现代/古代等）
   - 环境的细节元素？（建筑风格、家具摆设、天气状况、时间季节等）
   - 环境与主体如何互动？（光影投射、物体遮挡、空间关系等）

3. 光线氛围联想：
   - 主光源类型？（自然光/人造光/混合光）
   - 光线的方向和强度？（顺光/侧光/逆光、强光/柔光）
   - 光线的色温和色调？（暖光/冷光/自然光）
   - 光影效果如何？（硬阴影/软阴影、高对比度/低对比度）

4. 色彩色调联想：
   - 主色调选择？（根据文本情感：暖色调/冷色调/中性色调）
   - 辅助色和点缀色？（与主色调和谐搭配）
   - 色彩饱和度？（鲜艳/淡雅/灰度）
   - 色彩对比度？（高对比/低对比/和谐对比）

5. 构图视角联想：
   - 拍摄视角？（平视/俯视/仰视/斜视）
   - 景别选择？（特写/近景/中景/远景/全景）
   - 构图法则？（三分法则/对称构图/引导线/框架构图）
   - 画面焦点？（主体清晰/背景虚化/全图清晰）

6. 艺术风格联想：
   - 艺术风格？（写实摄影/插画风格/油画风格/水彩风格/赛博朋克等）
   - 画面质感？（细腻/粗糙/光滑/颗粒感）
   - 艺术化元素？（电影感/故事板/概念艺术/插画风格）

【专业能力】
1. 叙事结构：理解故事节奏、情感曲线和信息层次
2. 视觉语言：掌握镜头语言、构图法则和视觉隐喻
3. 场景设计：创造连贯、有层次、有美感的视觉场景
4. 技术实现：了解AI图像生成的技术限制和优化方法

【分镜设计原则】
- 主题一致性：每个分镜都要服务于核心主题，不能偏离主线
- 视觉统一性：所有分镜在场景、色调、风格上保持高度统一
- 情感递进：分镜序列要有情感节奏和视觉张力
- 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的内容
- 提示词质量：每个画面提示词必须专业、详细、可执行

【输出格式 - 必须严格遵守】
【重要】你的输出必须严格按照以下格式返回，禁止使用其他格式！

核心主题：[一句话概括文本的核心主题思想]
视觉基调：[整体视觉风格+统一色调+情感氛围]
主题元素：[贯穿全篇的视觉元素列表，用逗号分隔]

分镜脚本：
1. **配音**：[原始转录文本，不要总结或概括]
2. **画面提示词**：[英文关键词，用逗号分隔，权重使用(数字)格式，如 black hole(1.5)]
3. **反向提示词**：[英文，避免的问题]

示例格式（请严格按照此格式输出）：
```
核心主题：黑洞的形成与宇宙命运
视觉基调：神秘、科幻、深邃的蓝色调
主题元素：黑洞、吸积盘、星云、星光

分镜脚本：
1. **配音**：在遥远的宇宙深处，隐藏着神秘的黑洞
2. **画面提示词**：black hole(1.5), event horizon(1.3), deep space(1.2), cosmic dust(1.1), nebula(1.2), neutral lighting(1.0), balanced exposure(1.2), documentary style(1.3), wide angle shot(1.1), photorealistic style(1.4), cinematic composition(1.3), professional astrophotography, masterpiece, best quality(1.6), ultra detailed(1.1)
3. **反向提示词**：worst quality, low quality, cartoon, anime, painting, illustration, ugly, deformed, blurry

1. **配音**：恒星逐渐被黑洞引力吞噬，形成壮观的吸积盘
2. **画面提示词**：dying star(1.6), black hole(1.5), accretion disk(1.8), gravitational pull(1.4), stellar collapse(1.5), space, hot plasma(1.4), orange glow(1.3), neutral lighting(1.0), balanced exposure(1.2), documentary style(1.3), medium shot(1.1), photorealistic style(1.4), cinematic composition(1.3), professional astrophotography, masterpiece, best quality(1.6), ultra detailed(1.1)
3. **反向提示词**：worst quality, low quality, cartoon, anime, painting, illustration, ugly, deformed, blurry
```

【注意】输出中必须包含"分镜脚本："这个关键词！
【关键】每个分镜的配音字段必须使用原始转录文本，绝对不能总结！""",

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
5. 根据文本语义添加与主题相关的视觉元素，进行主题化构图
6. 确保所有图片风格统一、色调协调、共同突出表达核心主题
7. 每个画面都要贴切诠释对应语义的内容

请设计电影级分镜脚本，画面提示词必须使用英文："""
    }
    
    # 分镜分析模板 - 豆包提示词版本（中文）
    SHOT_ANALYSIS_DOUBAO = {
        "system": """你是资深影视导演和视觉叙事专家，擅长将文本转化为电影级分镜脚本。

【核心要求 - 主题统一性】
1. 整篇深度阅读：必须完整阅读并深入理解整段转录文本，把握核心主题思想
2. 主题提炼：准确提炼出文本的中心思想、情感基调和视觉主题
3. 统一基调：所有分镜的画面提示词必须围绕同一主题思想、定准同一基调
4. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
5. 综合表达：所有分镜画面综合起来必须突出表达那个核心主题思想

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其深层含义和情感色彩
2. 合理拆分：根据语义完整性和叙述逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合口语化表达
4. 语义-视觉映射：将抽象语义转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定核心主题后（如"战争类评论文章"），所有画面必须围绕该主题构图
2. 元素选择：根据文本语义，添加与主题相关的视觉元素
   - 战争主题：战场、军装、武器、旗帜、硝烟、废墟、和平鸽、纪念碑等
   - 历史主题：古籍、文物、历史人物、时代场景、文献资料等
   - 科技主题：实验室、设备、数据可视化、未来场景等
   - 自然主题：山川、河流、森林、季节变化、天气现象等
   - 城市主题：建筑、街道、交通、人群、夜景灯光等
   - 人文主题：人物表情、动作、互动、文化符号等
3. 视觉隐喻：使用象征性视觉元素表达抽象概念
4. 构图统一：保持镜头语言、视角、景深的一致性

【视觉联想深度引导 - 每张画都要思考】
请为每张分镜进行以下6个维度的深度视觉联想：

1. 主体元素联想：
   - 核心主体是什么？（人物、物体、场景等）
   - 主体的细节特征？（外观、材质、状态、动作、表情等）
   - 主体在画面中的位置和比例？（中心、前景、背景等）

2. 环境场景联想：
   - 主体需要什么环境背景？（室内/室外、城市/乡村、现代/古代等）
   - 环境的细节元素？（建筑风格、家具摆设、天气状况、时间季节等）
   - 环境与主体如何互动？（光影投射、物体遮挡、空间关系等）

3. 光线氛围联想：
   - 主光源类型？（自然光/人造光/混合光）
   - 光线的方向和强度？（顺光/侧光/逆光、强光/柔光）
   - 光线的色温和色调？（暖光/冷光/自然光）
   - 光影效果如何？（硬阴影/软阴影、高对比度/低对比度）

4. 色彩色调联想：
   - 主色调选择？（根据文本情感：暖色调/冷色调/中性色调）
   - 辅助色和点缀色？（与主色调和谐搭配）
   - 色彩饱和度？（鲜艳/淡雅/灰度）
   - 色彩对比度？（高对比/低对比/和谐对比）

5. 构图视角联想：
   - 拍摄视角？（平视/俯视/仰视/斜视）
   - 景别选择？（特写/近景/中景/远景/全景）
   - 构图法则？（三分法则/对称构图/引导线/框架构图）
   - 画面焦点？（主体清晰/背景虚化/全图清晰）

6. 艺术风格联想：
   - 艺术风格？（写实摄影/插画风格/油画风格/水彩风格/赛博朋克等）
   - 画面质感？（细腻/粗糙/光滑/颗粒感）
   - 艺术化元素？（电影感/故事板/概念艺术/插画风格）

【专业能力】
1. 叙事结构：理解故事节奏、情感曲线和信息层次
2. 视觉语言：掌握镜头语言、构图法则和视觉隐喻
3. 场景设计：创造连贯、有层次、有美感的视觉场景
4. 技术实现：了解AI图像生成的技术限制和优化方法

【分镜设计原则】
- 主题一致性：每个分镜都要服务于核心主题，不能偏离主线
- 视觉统一性：所有分镜在场景、色调、风格上保持高度统一
- 情感递进：分镜序列要有情感节奏和视觉张力
- 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的内容
- 提示词质量：每个画面提示词必须专业、详细、可执行

【输出格式 - 必须严格遵守】
【重要】你的输出必须严格按照以下格式返回，否则程序无法解析！

核心主题：[一句话概括文本的核心主题思想]
视觉基调：[整体视觉风格+统一色调+情感氛围]
主题元素：[贯穿全篇的视觉元素列表]

分镜脚本：
1. **配音**：[润色后的口语化文本内容]
   - **语义解析**：[这句话的核心语义和情感]
   - **画面构思**：[围绕主题的具体构图思路]
   - **视觉元素**：[与主题和语义相关的具体元素]
   - **画面提示词**：[中文，必须围绕核心主题，包含主题相关元素]

【注意】输出中必须包含"分镜脚本："这个关键词！""",

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
5. 根据文本语义添加与主题相关的视觉元素，进行主题化构图
6. 确保所有图片风格统一、色调协调、共同突出表达核心主题
7. 每个画面都要贴切诠释对应语义的内容

请设计电影级分镜脚本，画面提示词必须使用中文："""
    }
    
    # 为了保持兼容性，保留旧的SHOT_ANALYSIS引用（默认使用SD版本)
    SHOT_ANALYSIS = SHOT_ANALYSIS_SD

    # 轻量级主题提取模板 - 仅提取核心主题和视觉基调，不生成分镜
    THEME_EXTRACTION = {
        "system": """你是专业的视频内容分析专家。请从以下语音转录文本中提取关键词，用于后续分镜生成。

【重要】你必须直接返回关键词，不需要任何解释或描述。

请用以下严格格式输出（只输出这些内容，不要有任何其他文字）：
【核心主题】：关键词1, 关键词2, 关键词3（最多5个关键词，用逗号分隔）
【视觉基调】：关键词1, 关键词2（最多3个关键词）
【主题元素】：关键词1, 关键词2, 关键词3, 关键词4, 关键词5（最多5个关键词）

示例：
【核心主题】：战争, 军事, 伊朗, 美国, 冲突
【视觉基调】：紧张, 纪实, 电影级
【主题元素】：战场, 军队, 导弹, 硝烟, 废墟""",
        "user_template": "语音转录文本：\n{text}"
    }
    
    # 语音新闻播报分镜分析模板 - SD提示词版本
    VOICE_SHOT_ANALYSIS_SD = {
        "system": """你是专业的语音新闻播报视频分镜脚本专家。请严格按照以下要求处理语音转录文本：

【主题统一性要求 - 最重要】
1. 整篇深度阅读：必须完整阅读整段转录文本，深入理解文章的核心主题思想
2. 主题提炼：准确提炼出贯穿全文的中心思想、情感基调和视觉主题
3. 统一基调：所有分镜的画面提示词必须围绕同一主题思想、定准同一基调
4. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
5. 综合表达：所有分镜画面综合起来必须突出表达那个核心主题思想
6. 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的内容

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其深层含义和情感色彩
2. 合理拆分：根据语义完整性和叙述逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合口语化表达
4. 语义-视觉映射：将抽象语义转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定核心主题后（如"战争类评论文章"），所有画面必须围绕该主题构图
2. 元素选择：根据文本语义，添加与主题相关的视觉元素
   - 战争主题：战场、军装、武器、旗帜、硝烟、废墟、和平鸽、纪念碑等
   - 历史主题：古籍、文物、历史人物、时代场景、文献资料等
   - 科技主题：实验室、设备、数据可视化、未来场景等
   - 自然主题：山川、河流、森林、季节变化、天气现象等
   - 城市主题：建筑、街道、交通、人群、夜景灯光等
   - 人文主题：人物表情、动作、互动、文化符号等
3. 视觉隐喻：使用象征性视觉元素表达抽象概念
4. 构图统一：保持镜头语言、视角、景深的一致性

核心要求：
1. 内容分析：首先通篇分析文章内容，确切了解掌握文章的中心思想和主要内容
2. 一字不差转录：严格按照原始语音内容进行转录，确保100%准确
3. 标点符号添加：根据GB/T 15834—2011规范，结合语音节奏准确添加标点符号
4. 错别字修正：仅修正明显的错别字
5. 分镜脚本生成规则 - 【强制要求】：
   - 【必须遵守】每个语音片段必须对应一个独立的分镜！
   - 【禁止合并】绝对不要将多个句子合并成一个分镜！
   - 【数量要求】分镜数量不限制，由大模型根据语义完整性自主判断
   - 【错别字修正】修正所有的错别字
   - 分镜之间要有连贯性，画面切换流畅自然
   - 所有分镜的画面提示词必须围绕同一主题、保持统一基调和风格
6. 语言要求：使用中文简体
7. 画面提示词必须使用英文撰写，符合Stable Diffusion标准格式
8. 提示词结构必须包含：主体描述、场景环境、光照条件、艺术风格、质量修饰词
9. 所有分镜的提示词必须体现主题统一性，使用一致的视觉元素和色调
10. 每个分镜必须提供英文负面提示词

输出格式 - 必须严格遵守：
【重要】你的输出必须严格按照以下格式返回，否则程序无法解析！

- 核心主题：[文章的核心主题思想]
- 视觉基调：[整体视觉风格+统一色调+情感氛围]
- 主题元素：[贯穿全篇的视觉元素列表]
- **内容类型**：[从以下类型中选择最匹配的：military军事/politics政治/space太空/science科学/nature自然/technology科技/history历史/art艺术/business商业/health健康/travel旅游/general通用]
- **关键词提取**：[提取文本中的核心关键词，用逗号分隔]
- 主要内容：[文章的主要内容概述]
- 转录文案：[带标点符号的完整文案]

分镜脚本：
  1. **[时间标记]**
     - **配音**：[润色后的配音文本内容]
     - **语义解析**：[这句话的核心语义和情感]
     - **画面构思**：[围绕主题的具体构图思路]
     - **视觉元素**：[与主题和语义相关的具体元素]
     - **画面提示词**：[英文提示词，必须围绕核心主题]
     - **负面提示词**：[英文负面提示词]""",

        "user_template": """请严格按照要求处理以下语音转录文本：

【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

原始语音转录文本：
{text}

提示词类型：SD提示词（必须使用英文画面提示词）
风格预设：{style_preset}
{custom_theme_section}
{custom_visual_tone_section}
{selected_styles_section}

【重要提醒 - 必须遵守】
1. 请一字不差地转录原始语音内容
2.【强制】错别字修正：修正所有的错别字
3. 请先完整阅读整篇文本，深入理解其核心主题思想
4. 根据文本语义添加与主题相关的视觉元素，进行主题化构图
5.【强制】根据语义进行断句，一个断句生成一个分镜。
6.【强制】分镜数量不限制，由大模型根据语义完整性自主判断
7. 【强制】所有分镜的画面提示词必须围绕断句的语义使用恰当贴切的名词或形容词，视觉元素用词不得少于三个！
8. 确保所有图片风格统一、色调协调、共同突出表达核心主题
9.每个画面的视觉元素都要贴切诠释对应语义的内容

请生成专业的分镜脚本。"""
    }

    # 语音新闻播报分镜分析模板 - 豆包提示词版本
    VOICE_SHOT_ANALYSIS_DOUBAO = {
        "system": """你是专业的语音新闻播报视频分镜脚本专家。请严格按照以下要求处理语音转录文本：

【主题统一性要求 - 最重要】
1. 整篇深度阅读：必须完整阅读整段转录文本，深入理解文章的核心主题思想
2. 主题提炼：准确提炼出贯穿全文的中心思想、情感基调和视觉主题
3. 统一基调：所有分镜的画面提示词必须围绕同一主题思想、定准同一基调
4. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
5. 综合表达：所有分镜画面综合起来必须突出表达那个核心主题思想
6. 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的内容

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其深层含义和情感色彩
2. 合理拆分：根据语义完整性和叙述逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合口语化表达
4. 语义-视觉映射：将抽象语义转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定核心主题后（如"战争类评论文章"），所有画面必须围绕该主题构图
2. 元素选择：根据文本语义，添加与主题相关的视觉元素
   - 战争主题：战场、军装、武器、旗帜、硝烟、废墟、和平鸽、纪念碑等
   - 历史主题：古籍、文物、历史人物、时代场景、文献资料等
   - 科技主题：实验室、设备、数据可视化、未来场景等
   - 自然主题：山川、河流、森林、季节变化、天气现象等
   - 城市主题：建筑、街道、交通、人群、夜景灯光等
   - 人文主题：人物表情、动作、互动、文化符号等
3. 视觉隐喻：使用象征性视觉元素表达抽象概念
4. 构图统一：保持镜头语言、视角、景深的一致性

核心要求：
1. 内容分析：首先通篇分析文章内容，确切了解掌握文章的中心思想和主要内容
2. 一字不差转录：严格按照原始语音内容进行转录，确保100%准确
3. 标点符号添加：根据GB/T 15834—2011规范，结合语音节奏准确添加标点符号
4. 错别字修正：仅修正明显的错别字
5. 分镜脚本生成规则：
   - 基于文章中心思想生成分镜脚本
   - 每个分镜只对应一句话，绝不合并多个句子
   - 每个独立的语义单元都必须是一个独立的分镜
   - 分镜数量越多越好，不要限制分镜数量
   - 分镜之间要有连贯性，画面切换流畅自然
   - 所有分镜的画面提示词必须围绕同一主题、保持统一基调和风格
6. 语言要求：使用中文简体
7. 画面提示词必须使用中文撰写，适合豆包生图平台
8. 提示词应包含：主体、场景、动作、氛围、风格等要素
9. 所有分镜的提示词必须体现主题统一性，使用一致的视觉元素和色调
10. 描述要生动具体，便于AI理解生成画面

输出格式 - 必须严格遵守：
【重要】你的输出必须严格按照以下格式返回，否则程序无法解析！

- 核心主题：[文章的核心主题思想]
- 视觉基调：[整体视觉风格+统一色调+情感氛围]
- 主题元素：[贯穿全篇的视觉元素列表]
- 主要内容：[文章的主要内容概述]
- 转录文案：[带标点符号的完整文案]

分镜脚本：
  1. **[时间标记]**
     - **配音**：[润色后的配音文本内容]
     - **语义解析**：[这句话的核心语义和情感]
     - **画面构思**：[围绕主题的具体构图思路]
     - **视觉元素**：[与主题和语义相关的具体元素]
     - **画面提示词**：[中文画面描述，必须围绕核心主题]

【注意】输出中必须包含"分镜脚本："这个关键词！""",

        "user_template": """请严格按照要求处理以下语音转录文本：

【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

原始语音转录文本：
{text}

提示词类型：豆包提示词（必须使用中文画面提示词）
风格预设：{style_preset}
{custom_theme_section}
{custom_visual_tone_section}
{selected_styles_section}

【重要提醒 - 必须遵守】
1. 请一字不差地转录原始语音内容
2.【强制】错别字修正：修正所有的错别字
3. 请先完整阅读整篇文本，深入理解其核心主题思想
4. 根据文本语义添加与主题相关的视觉元素，进行主题化构图
5.【强制】根据语义进行断句，一个断句生成一个分镜。
6.【强制】分镜数量不限制，由大模型根据语义完整性自主判断
7. 【强制】所有分镜的画面提示词必须围绕断句的语义使用恰当贴切的名词或形容词，视觉元素用词不得少于三个！
8. 确保所有图片风格统一、色调协调、共同突出表达核心主题
9.每个画面的视觉元素都要贴切诠释对应语义的内容

请生成专业的分镜脚本。"""
    }

    # 语音科普知识探讨讲解分镜分析模板 - SD提示词版本
    SCIENCE_SHOT_ANALYSIS_SD = {
        "system": """你是专业的科普知识视频分镜脚本专家。请严格按照以下要求处理语音转录文本：

【主题统一性要求 - 最重要】
1. 整篇深度阅读：必须完整阅读整段转录文本，深入理解科普主题和核心知识点
2. 主题提炼：准确提炼出贯穿全文的科普主题、知识脉络和视觉呈现方式
3. 统一基调：所有分镜的画面提示词必须围绕同一科普主题、定准同一知识传播基调
4. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
5. 综合表达：所有分镜画面综合起来必须突出表达那个核心科普主题
6. 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的科学内容

【转录要求 - 严格执行】
1. 一字不差转录：严格按照原始语音内容进行转录，确保100%准确
2. 语义断句：根据语义完整性和叙述逻辑进行断句，不要机械按时间切分
3. 国标标点：根据GB/T 15834—2011规范，结合语音节奏准确添加标点符号
4. 错别字修正：仅修正明显的错别字，保持原文专业性

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其科学知识内涵和讲解逻辑
2. 合理拆分：根据知识点的完整性和讲解逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合科普讲解的口语化表达
4. 知识-视觉映射：将抽象科学概念转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定科普主题后（如"量子力学探索"），所有画面必须围绕该主题构图
2. 元素选择：根据科学知识内容，添加与主题相关的视觉元素
   - 物理主题：公式、实验装置、粒子效果、能量可视化、空间维度等
   - 化学主题：分子结构、实验器皿、化学反应、元素周期表、微观世界等
   - 生物主题：细胞、DNA、生态系统、生物解剖、进化树等
   - 天文主题：星球、星系、望远镜、航天器、宇宙现象等
   - 地理主题：地图、地形、气候现象、地质结构、环境变化等
   - 数学主题：几何图形、公式推导、数据可视化、抽象结构等
   - 科技主题：芯片、电路、机器人、AI可视化、未来科技等
3. 视觉隐喻：使用象征性视觉元素表达抽象科学概念
4. 构图统一：保持镜头语言、视角、景深的一致性，营造科学严谨感

【分镜脚本生成规则】
1. 基于科普主题生成分镜脚本
2. 每个分镜对应一个完整的知识点或讲解单元
3. 每个独立的知识单元都必须是一个独立的分镜
4. 分镜数量根据知识密度确定，不要限制分镜数量
5. 分镜之间要有连贯性，知识传递流畅自然
6. 所有分镜的画面提示词必须围绕同一主题、保持统一基调和风格
7. 语言要求：使用中文简体
8. 画面提示词必须使用英文撰写，符合Stable Diffusion标准格式
9. 提示词结构必须包含：科学概念可视化、场景环境、光照条件、艺术风格、质量修饰词
10. 所有分镜的提示词必须体现主题统一性，使用一致的视觉元素和色调
11. 每个分镜必须提供英文负面提示词

输出格式 - 必须严格遵守：
【重要】你的输出必须严格按照以下格式返回，否则程序无法解析！

- 核心主题：[科普主题]
- 视觉基调：[整体视觉风格+统一色调+情感氛围]
- 主题元素：[贯穿全篇的视觉元素列表]
- 主要内容：[科普知识内容概述]
- 转录文案：[带标点符号的完整文案]

分镜脚本：
  1. **[时间标记]**
     - **配音**：[润色后的配音文本内容]
     - **语义解析**：[这句话的核心科学知识]
     - **画面构思**：[围绕科普主题的具体构图思路]
     - **视觉元素**：[与主题和语义相关的科学元素]
     - **画面提示词**：[英文提示词，必须围绕核心主题]

【注意】输出中必须包含"分镜脚本："这个关键词！""",

        "user_template": """请严格按照要求处理以下语音转录文本：

【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

原始语音转录文本：
{text}

提示词类型：SD提示词（必须使用英文画面提示词）
风格预设：{style_preset}

【重要提醒 - 必须遵守】
1. 请一字不差地转录原始语音内容
2.【强制】错别字修正：修正所有的错别字
3. 请先完整阅读整篇文本，深入理解其核心科普主题
4. 根据科学知识内容添加与主题相关的视觉元素，进行主题化构图
5.【强制】根据语义进行断句，一个断句生成一个分镜。
6.【强制】分镜数量不限制，由大模型根据语义完整性自主判断
7. 【强制】所有分镜的画面提示词必须围绕断句的语义使用恰当贴切的名词或形容词，视觉元素用词不得少于三个！
8. 确保所有图片风格统一、色调协调、共同突出表达核心科普主题
9.每个画面的视觉元素都要贴切诠释对应语义的内容

请生成专业的分镜脚本。"""
    }

    # 语音科普知识探讨讲解分镜分析模板 - 豆包提示词版本
    SCIENCE_SHOT_ANALYSIS_DOUBAO = {
        "system": """你是专业的科普知识视频分镜脚本专家。请严格按照以下要求处理语音转录文本：

【主题统一性要求 - 最重要】
1. 整篇深度阅读：必须完整阅读整段转录文本，深入理解科普主题和核心知识点
2. 主题提炼：准确提炼出贯穿全文的科普主题、知识脉络和视觉呈现方式
3. 统一基调：所有分镜的画面提示词必须围绕同一科普主题、定准同一知识传播基调
4. 视觉连贯：所有图片内容要风格统一、色调协调、构图有内在联系
5. 综合表达：所有分镜画面综合起来必须突出表达那个核心科普主题
6. 语义贴切：每张图片都要尽量贴切地诠释对应语义所要表达的科学内容

【转录要求 - 严格执行】
1. 一字不差转录：严格按照原始语音内容进行转录，确保100%准确
2. 语义断句：根据语义完整性和叙述逻辑进行断句，不要机械按时间切分
3. 国标标点：根据GB/T 15834—2011规范，结合语音节奏准确添加标点符号
4. 错别字修正：仅修正明显的错别字，保持原文专业性

【语义分析与拆分润色】
1. 语义理解：深入分析每句话的具体语义，理解其科学知识内涵和讲解逻辑
2. 合理拆分：根据知识点的完整性和讲解逻辑，将文本拆分为合适的分镜单元
3. 润色优化：对每句配音文本进行润色，使其更适合科普讲解的口语化表达
4. 知识-视觉映射：将抽象科学概念转化为具体的视觉元素和画面构图

【主题化构图设计 - 关键要求】
1. 主题先行：确定科普主题后（如"量子力学探索"），所有画面必须围绕该主题构图
2. 元素选择：根据科学知识内容，添加与主题相关的视觉元素
   - 物理主题：公式、实验装置、粒子效果、能量可视化、空间维度等
   - 化学主题：分子结构、实验器皿、化学反应、元素周期表、微观世界等
   - 生物主题：细胞、DNA、生态系统、生物解剖、进化树等
   - 天文主题：星球、星系、望远镜、航天器、宇宙现象等
   - 地理主题：地图、地形、气候现象、地质结构、环境变化等
   - 数学主题：几何图形、公式推导、数据可视化、抽象结构等
   - 科技主题：芯片、电路、机器人、AI可视化、未来科技等
3. 视觉隐喻：使用象征性视觉元素表达抽象科学概念
4. 构图统一：保持镜头语言、视角、景深的一致性，营造科学严谨感

【分镜脚本生成规则】
1. 基于科普主题生成分镜脚本
2. 每个分镜对应一个完整的知识点或讲解单元
3. 每个独立的知识单元都必须是一个独立的分镜
4. 分镜数量根据知识密度确定，不要限制分镜数量
5. 分镜之间要有连贯性，知识传递流畅自然
6. 所有分镜的画面提示词必须围绕同一主题、保持统一基调和风格
7. 语言要求：使用中文简体
8. 画面提示词必须使用中文撰写，适合豆包生图平台
9. 提示词应包含：科学概念可视化、场景、动作、氛围、风格等要素
10. 所有分镜的提示词必须体现主题统一性，使用一致的视觉元素和色调
11. 描述要生动具体，便于AI理解生成画面

输出格式 - 必须严格遵守：
【重要】你的输出必须严格按照以下格式返回，否则程序无法解析！

- 核心主题：[科普主题]
- 视觉基调：[整体视觉风格+统一色调+情感氛围]
- 主题元素：[贯穿全篇的视觉元素列表]
- 主要内容：[科普知识内容概述]
- 转录文案：[带标点符号的完整文案]

分镜脚本：
  1. **[时间标记]**
     - **配音**：[润色后的配音文本内容]
     - **语义解析**：[这句话的核心科学知识]
     - **画面构思**：[围绕科普主题的具体构图思路]
     - **视觉元素**：[与主题和语义相关的科学元素]
     - **画面提示词**：[中文画面描述，必须围绕核心主题]

【注意】输出中必须包含"分镜脚本："这个关键词！""",

        "user_template": """请严格按照要求处理以下语音转录文本：

【音频信息】
- 片段数：{segment_count}个
- 总时长：{duration:.1f}秒

原始语音转录文本：
{text}

提示词类型：豆包提示词（必须使用中文画面提示词）
风格预设：{style_preset}

【重要提醒 - 必须遵守】
1. 请一字不差地转录原始语音内容
2.【强制】错别字修正：修正所有的错别字
3. 请先完整阅读整篇文本，深入理解其核心科普主题
4. 根据科学知识内容添加与主题相关的视觉元素，进行主题化构图
5.【强制】根据语义进行断句，一个断句生成一个分镜。
6.【强制】分镜数量不限制，由大模型根据语义完整性自主判断
7. 【强制】所有分镜的画面提示词必须围绕断句的语义使用恰当贴切的名词或形容词，视觉元素用词不得少于三个！
8. 确保所有图片风格统一、色调协调、共同突出表达核心科普主题
9.每个画面的视觉元素都要贴切诠释对应语义的内容

请生成专业的分镜脚本。"""
    }

    # 风格描述模板
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
- 给出构图和技法提示
- 适合直接用于Stable Diffusion提示词""",
        
        "user_template": """请详细分析以下艺术风格，并提供专业的AI绘图描述：

风格名称：{style_name}"""
    }
    
    # 质量评估模板
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
- <0.6：不合格，必须重新生成

【输出格式】
评分：[0-1之间的数值]
评价：[简要评价]
建议：[改进建议，如有]""",
        
        "user_template": """【原始输入】
{original_input}

【模型输出】
{model_output}

【预期用途】
{intended_use}

请评估输出质量："""
    }
    
    @classmethod
    def get_template(cls, template_type, **kwargs):
        """获取格式化的提示词模板"""
        templates = {
            "prompt_optimization": cls.PROMPT_OPTIMIZATION,
            "shot_analysis": cls.SHOT_ANALYSIS,
            "shot_analysis_sd": cls.SHOT_ANALYSIS_SD,
            "shot_analysis_doubao": cls.SHOT_ANALYSIS_DOUBAO,
            "voice_shot_analysis_sd": cls.VOICE_SHOT_ANALYSIS_SD,
            "voice_shot_analysis_doubao": cls.VOICE_SHOT_ANALYSIS_DOUBAO,
            "science_shot_analysis_sd": cls.SCIENCE_SHOT_ANALYSIS_SD,
            "science_shot_analysis_doubao": cls.SCIENCE_SHOT_ANALYSIS_DOUBAO,
            "style_description": cls.STYLE_DESCRIPTION,
            "quality_assessment": cls.QUALITY_ASSESSMENT,
            "theme_extraction": cls.THEME_EXTRACTION
        }
        
        if template_type not in templates:
            return None
        
        # 不再强制限制分镜数量，让大模型自主判断
        # 保留这些键但设为 None，避免模板渲染错误
        if 'min_shots' not in kwargs:
            kwargs['min_shots'] = ""
        if 'max_shots' not in kwargs:
            kwargs['max_shots'] = ""
        
        template = templates[template_type]
        return {
            "system": template["system"],
            "user": template["user_template"].format(**kwargs) if kwargs else template["user_template"]
        }


# 延迟导入函数
def lazy_import():
    """延迟导入非必要模块"""
    global PERFORMANCE_MONITOR_AVAILABLE, psutil, GPUtil
    global OLLAMA_AVAILABLE, ollama
    global requests
    global PIL, Image, ImageDraw, ImageFont, BytesIO
    global time
    global ThreadPoolExecutor
    
    try:
        # 尝试导入性能监控库
        try:
            import psutil
            import GPUtil
            PERFORMANCE_MONITOR_AVAILABLE = True
        except ImportError:
            pass
        
        # 尝试导入Ollama客户端
        try:
            import ollama
            OLLAMA_AVAILABLE = True
        except ImportError:
            pass
        
        # 导入其他模块
        import requests
        from PIL import Image, ImageDraw, ImageFont
        from io import BytesIO
        import time
        from concurrent.futures import ThreadPoolExecutor
        
        # 更新全局变量
        globals().update(locals())
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
        except:
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
        
        # 大模型设置 - 初始值为脚本自带，由load_config加载
        self.optimization_method_var = tk.StringVar(value="脚本自带")
        self.ollama_model_var = tk.StringVar(value="脚本自带")
        self.model_dropdown_visible = False
        
        # 大模型高级配置 - 初始值为质量优先，由load_config加载
        self.llm_config_preset_var = tk.StringVar(value="质量优先")
        self.llm_config_presets = list(LLMConfig.PRESETS.keys())
        self.current_llm_config = LLMConfig("质量优先")
        
        # 视频设置 - 初始值为硬切（无过渡效果，速度最快），由load_config加载
        self.transition_var = tk.StringVar(value="硬切")
        self.transition_dropdown_visible = False
        
        # 绘图设置
        self.model_var = tk.StringVar(value="不选择")
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
        self.max_workers = min(multiprocessing.cpu_count() // 2, 4)
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
            import time
            time.sleep(1)  # 等待Ollama模块加载完成
            
            self.system_check()
            # 系统检查完成后，尝试连接SD API（静默模式，不弹窗）
            time.sleep(1)
            self.check_sd_api_connection(silent=True)
            
            # 发现可用的多模型
            time.sleep(0.5)
            self.discover_available_models()
        threading.Thread(target=delayed_system_check, daemon=True).start()
        
        # 预加载Whisper模型（延迟执行，让UI先加载）
        def preload_whisper():
            import time
            time.sleep(2)  # 等待UI完全加载后再预加载
            self.preload_whisper_model()
        threading.Thread(target=preload_whisper, daemon=True).start()
    
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
    
    def discover_available_models(self):
        """发现并记录可用的Ollama模型"""
        try:
            global OLLAMA_AVAILABLE
            if not OLLAMA_AVAILABLE:
                try:
                    import ollama
                    OLLAMA_AVAILABLE = True
                except ImportError:
                    pass
            
            if not OLLAMA_AVAILABLE:
                self.log("⚠️ Ollama模块未加载，跳过模型发现")
                return
            
            models = multi_model_fusion.discover_models()
            if models:
                self.log(f"🤖 发现 {len(models)} 个可用大模型:")
                for model in models[:10]:  # 显示前10个
                    weight = multi_model_fusion.model_weights.get(model, 0.75)
                    self.log(f"   • {model} (权重: {weight:.2f})")
                if len(models) > 10:
                    self.log(f"   ... 还有 {len(models) - 10} 个模型")
            else:
                self.log("⚠️ 未发现可用的Ollama模型")
        except Exception as e:
            self.log(f"⚠️ 模型发现失败: {e}")

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
            threading.Thread(target=self.monitor_performance, daemon=True).start()

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
            self.model_var = tk.StringVar(value="不选择")
        
        models = ["不选择", "Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3", "DALL·E 3"]
        model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, values=models, state="readonly", font=("Microsoft YaHei", large_font_size))
        model_combo.pack(fill=tk.X, padx=5, pady=2)
        
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
        
        # 过渡模式设置
        transition_frame = ttk.Frame(video_section)
        transition_frame.pack(fill=tk.X, pady=3)
        ttk.Label(transition_frame, text="过渡模式:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        # 过渡模式下拉菜单
        transition_frame_right = ttk.Frame(transition_frame)
        transition_frame_right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        transition_button = ttk.Button(transition_frame_right, textvariable=self.transition_var, command=self.toggle_transition_dropdown, style="Medium.TButton")
        transition_button.pack(fill=tk.X, padx=5, pady=2)
        
        # 过渡模式下拉菜单框架
        self.transition_dropdown_frame = ttk.Frame(transition_frame_right)
        
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
        
        # 添加优化方式选择
        opt_frame = ttk.Frame(model_section)
        opt_frame.pack(fill=tk.X, pady=3)
        ttk.Label(opt_frame, text="优化方式:", width=12, font=('Microsoft YaHei', large_font_size, 'bold')).pack(side=tk.LEFT, padx=5)
        
        opt_combo = ttk.Combobox(
            opt_frame,
            textvariable=self.optimization_method_var,
            values=["脚本自带", "本地大模型", "脚本优化"],
            state="readonly",
            style="Config.TCombobox",
            height=10
        )
        opt_combo.pack(fill=tk.X, padx=5, pady=2, ipady=3)
        
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
        # 清空现有模型按钮
        for widget in self.model_dropdown_inner_frame.winfo_children():
            widget.destroy()
        
        # 添加"脚本自带"选项
        script_model_btn = ttk.Button(self.model_dropdown_inner_frame, text="脚本自带", command=lambda m="脚本自带": self.select_ollama_model(m), style="Medium.TButton")
        script_model_btn.pack(fill=tk.X, pady=1, padx=5)
        
        # 尝试获取本地已安装的Ollama模型
        try:
            if OLLAMA_AVAILABLE:
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
                            elif "qwen3-vl:4b" in model:
                                model_label = f"{model} (视觉任务)"
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
        """更新任务进度"""
        if hasattr(self, 'lbl_progress'):
            self.lbl_progress.config(text=message)
        if hasattr(self, 'progress_var') and progress is not None:
            self.progress_var.set(progress)
    
    def update_task_status(self, status):
        """更新任务状态"""
        if hasattr(self, 'task_status_var'):
            self.task_status_var.set(status)
    
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
        # 检查优化方式
        optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
        
        # 如果优化方式是"脚本自带"或"脚本优化"，使用默认风格描述
        if optimization_method in ["脚本自带", "脚本优化"]:
            default_styles = {
                "电影感": "电影级别的视觉效果，高对比度，逼真的色彩，专业的灯光设置，清晰的画面细节",
                "纪录片风": "真实自然的拍摄风格，手持摄像效果，自然光线，真实的色彩还原，细节丰富",
                "赛博朋克": "霓虹灯效果，高楼大厦，未来感，科技感，暗色背景，鲜艳的色彩对比",
                "写实摄影": "真实的光影效果，自然的色彩，清晰的细节，专业的构图，逼真的质感",
                "皮克斯": "卡通风格，明亮的色彩，圆润的线条，温馨的氛围，细节丰富",
                "达芬奇": "文艺复兴风格，古典绘画效果，柔和的光线，丰富的细节，优雅的构图",
                "油画": "油画质感，丰富的色彩层次，细腻的笔触，古典的氛围，艺术感强烈",
                "多巴胺": "鲜艳的色彩，高饱和度，充满活力，对比强烈，视觉冲击力强",
                "黑白线条": "黑白对比，清晰的线条，简约的构图，艺术感强烈，表现力丰富",
                "吉卜力": "日本动画风格，温馨的氛围，细腻的画面，丰富的色彩，充满想象力",
                "梵高": "后印象派风格，强烈的色彩，独特的笔触，情感丰富，艺术感强烈",
                "日式动漫": "日本动漫风格，明亮的色彩，细腻的线条，生动的表情，充满活力",
                "水彩": "水彩画质感，透明的色彩，柔和的过渡，自然的笔触，清新的氛围"
            }
            return default_styles.get(style, "")
        
        # 检查Ollama模型设置
        model = self.ollama_model_var.get()
        if model == "脚本自带":
            # 对于"脚本自带"选项，使用默认风格描述
            default_styles = {
                "电影感": "电影级别的视觉效果，高对比度，逼真的色彩，专业的灯光设置，清晰的画面细节",
                "纪录片风": "真实自然的拍摄风格，手持摄像效果，自然光线，真实的色彩还原，细节丰富",
                "赛博朋克": "霓虹灯效果，高楼大厦，未来感，科技感，暗色背景，鲜艳的色彩对比",
                "写实摄影": "真实的光影效果，自然的色彩，清晰的细节，专业的构图，逼真的质感",
                "皮克斯": "卡通风格，明亮的色彩，圆润的线条，温馨的氛围，细节丰富",
                "达芬奇": "文艺复兴风格，古典绘画效果，柔和的光线，丰富的细节，优雅的构图",
                "油画": "油画质感，丰富的色彩层次，细腻的笔触，古典的氛围，艺术感强烈",
                "多巴胺": "鲜艳的色彩，高饱和度，充满活力，对比强烈，视觉冲击力强",
                "黑白线条": "黑白对比，清晰的线条，简约的构图，艺术感强烈，表现力丰富",
                "吉卜力": "日本动画风格，温馨的氛围，细腻的画面，丰富的色彩，充满想象力",
                "梵高": "后印象派风格，强烈的色彩，独特的笔触，情感丰富，艺术感强烈",
                "日式动漫": "日本动漫风格，明亮的色彩，细腻的线条，生动的表情，充满活力",
                "水彩": "水彩画质感，透明的色彩，柔和的过渡，自然的笔触，清新的氛围"
            }
            return default_styles.get(style, "")
        
        # 对于其他模型，检查Ollama是否可用
        if not OLLAMA_AVAILABLE:
            return None
        
        # 检查缓存
        cache_key = f"style_{style}_{model}"
        cached_description = self.cache_get('prompts', cache_key)
        if cached_description:
            return cached_description
        
        try:
            # 使用高级提示词模板
            template = PromptTemplates.get_template(
                "style_description",
                style_name=style
            )
            
            # 使用创意模式生成风格描述
            config = LLMConfig("创意模式")
            
            # Ollama HTTP API 本身线程安全
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system", "content": template["system"]},
                    {"role": "user", "content": template["user"]}
                ],
                options=config.get_options(
                    num_predict=800,
                    num_ctx=2048
                )
            )
            
            style_description = response["message"]["content"].strip()
            self.log(f"⚡ 风格描述生成完成: {style}: {style_description[:50]}...")
            
            # 缓存结果
            self.cache_set('prompts', cache_key, style_description)
            
            return style_description
        except Exception as e:
            self.log(f"⚠️ 风格描述生成失败，使用默认描述: {e}")
            return None

    def apply_advanced_settings(self):
        """应用高级设置"""
        # 收集所有设置内容
        model = self.model_var.get() if hasattr(self, 'model_var') else "不选择"
        width = self.width_var.get() if hasattr(self, 'width_var') else "1920"
        height = self.height_var.get() if hasattr(self, 'height_var') else "1080"
        prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
        optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
        
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
        confirm_msg += f"优化方式: {optimization_method}\n"
        confirm_msg += f"图片尺寸: {width}x{height}\n"
        if selected_styles:
            confirm_msg += f"风格预设: {', '.join(selected_styles)}\n"
        else:
            confirm_msg += "风格预设: 无\n"
        confirm_msg += f"SD API地址: {self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else 'http://127.0.0.1:7860'}\n"

        # 显示确认对话框
        confirmed = messagebox.askyesno("确认设置", confirm_msg)

        if confirmed:
            # 应用设置
            msg = f"设置已应用:\n模型:{model}\n提示词类型:{prompt_type}\n优化方式:{optimization_method}\n尺寸:{width}x{height}"
            self.log(msg)
            # 保存配置
            self.save_config()
            messagebox.showinfo("成功", "设置已成功应用！\n系统将按照您的选择执行相应功能。")
            self.toggle_advanced_settings()
        else:
            # 取消应用
            self.log("⚠️ 设置应用已取消")
    
    def check_sd_api_connection(self, silent=False):
        """连接 SD API
        
        Args:
            silent: True表示静默模式，不弹出错误对话框
        """
        self.log("正在连接 SD API...")
        
        # 获取 API 地址
        api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else "http://127.0.0.1:7860"
        
        # 尝试连接 SD API
        try:
            import requests
            response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=5)
            if response.status_code == 200:
                # 连接成功，无提示
                self.log("✅ SD API 连接成功！")
                if hasattr(self, 'sd_api_status_var') and hasattr(self, 'sd_api_status_label'):
                    self.sd_api_status_var.set("✅ 已连接")
                    self.sd_api_status_label.config(foreground="green")  # 连接态呈现绿色
                return True
            else:
                # 连接失败
                self.log(f"❌ SD API 连接失败: 状态码 {response.status_code}")
                if hasattr(self, 'sd_api_status_var') and hasattr(self, 'sd_api_status_label'):
                    self.sd_api_status_var.set("❌ 未连接")
                    self.sd_api_status_label.config(foreground="red")  # 断开态呈现红色
                if not silent:
                    messagebox.showerror("错误", f"SD API 连接失败: 状态码 {response.status_code}")
                return False
        except Exception as e:
            # 连接异常，静默处理
            self.log(f"❌ SD API 连接异常: {str(e)}")
            if hasattr(self, 'sd_api_status_var') and hasattr(self, 'sd_api_status_label'):
                self.sd_api_status_var.set("❌ 未连接")
                self.sd_api_status_label.config(foreground="red")  # 断开态呈现红色
            if not silent:
                messagebox.showerror("错误", f"SD API 连接异常: {str(e)}")
            return False
    
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
        """清洗和修正文本"""
        # 繁简转换映射 - 更完整的映射
        traditional_to_simplified = {
            # 常用繁体转简体
            "一個": "一个",
            "德黑蘭": "德黑兰",
            "防空警報": "防空警报",
            "已經": "已经",
            "消失": "消失",
            "整整": "整整",
            "一周": "一周",
            "聽起來": "听起来",
            "透著": "透着",
            "一種": "一种",
            "沙啞": "沙哑",
            "尸体": "尸体",
            "站在": "站在",
            "這個": "这个",
            "節點": "节点",
            "往回看": "往回看",
            "距離": "距离",
            "美國": "美国",
            "對": "对",
            "對著": "对着",
            "伊朗": "伊朗",
            "發動": "发动",
            "那場": "那场",
            "外科手術式": "外科手术式",
            "打擊": "打击",
            "過去": "过去",
            "七天": "七天",
            "禮拜": "星期",
            "世界": "世界",
            "像是": "像是",
            "被": "被",
            "應聲聲": "应声",
            "拽進": "拖入",
            "了": "了",
            "充滿": "充满",
            "不確定性": "不确定性",
            "的": "的",
            "新紀元": "新纪元",
            "這": "这",
            "這一周": "这一周",
            "這幾天": "这几天",
            "這也": "这也",
            "這裡": "这里",
            "可不": "可不",
            "只是": "只是",
            "簡單": "简单",
            "局部": "局部",
            "衝突": "冲突",
            "升級": "升级",
            "更": "更",
            "一場": "一场",
            "震動": "震动",
            "全球": "全球",
            "地緣政治": "地缘政治",
            "根基": "根基",
            "深層": "深层",
            "地震": "地震",
            "現代戰爭": "现代战争",
            "那種": "那种",
            "冷酷": "冷酷",
            "精準": "精准",
            "被展現的淋漓盡致": "展现得淋漓尽致",
            "美軍": "美军",
            "盟友": "盟友",
            "動用了": "动用了",
            "高超音速武器": "高超音速武器",
            "密集": "密集",
            "無人機群": "无人机群",
            "境內": "境内",
            "指揮中書": "指挥中心",
            "雷達陣地": "雷达阵地",
            "那些": "那些",
            "被盯著很久的": "被盯了很久的",
            "和研發設施": "核研发设施",
            "一輪又一輪的": "一轮又一轮的",
            "一輪": "一轮",
            "定點清除": "定点清除",
            "看著": "看着",
            "畫面裡": "画面里",
            "導彈": "导弹",
            "瞬間穿透": "瞬间穿透",
            "加固延體": "加固建筑",
            "不得不": "不得不",
            "感嘆": "感叹",
            "技術代差": "技术代差",
            "帶來的": "带来的",
            "壓迫感": "压迫感",
            "可預想中": "可预想中",
            "瞬間瓦解": "瞬间瓦解",
            "並沒有發生": "并没有发生",
            "權力核心": "权力核心",
            "迅速轉入地下": "迅速转入地下",
            "即便": "即便",
            "斷網斷電": "断网断电",
            "廢墟上": "废墟上",
            "強硬的聲音": "强硬的声音",
            "依然": "依然",
            "通過": "通过",
            "衛星信號": "卫星信号",
            "清晰的傳遍了": "清晰地传遍了",
            "波斯灣": "波斯湾",
            "每一個角落": "每一个角落",
            "其實": "其实",
            "證明了": "证明了",
            "一個挺殘酷的真理": "一个挺残酷的真理",
            "挺殘酷": "挺残酷",
            "炸毀": "炸毁",
            "一座橋": "一座桥",
            "只需要": "只需要",
            "幾秒鐘": "几秒钟",
            "幾天": "几天",
            "但要": "但要",
            "摧毀": "摧毁",
            "一個政權的意志": "一个政权的意志",
            "政權": "政权",
            "恐怕得": "恐怕得",
            "經歷": "经历",
            "一場通向深淵的漫長對峙": "一场通向深渊的漫长对峙",
            "漫長": "漫长",
            "戰火": "战火",
            "在前方燒著": "在前方燃烧",
            "全球經濟": "全球经济",
            "也跟著帶來了": "也随之引发了",
            "一場叫做": "一场叫做",
            "霍爾木茲恐懼": "霍尔木兹恐惧",
            "急性病": "急性病",
            "雖說": "虽说",
            "美軍第五艦隊": "美军第五舰队",
            "第五艦队": "第五舰队",
            "一直想清楚": "一直想开辟",
            "一條安全航道": "一条安全航道",
            "但海面下散布的水雷": "但海面下散布的水雷",
            "神出鬼沒的": "神出鬼没的",
            "自殺式快艇": "自杀式快艇",
            "還是": "还是",
            "讓": "让",
            "保險公司": "保险公司",
            "把這一代的保費": "把这一区域的保费",
            "這一代": "这一代",
            "保費": "保费",
            "提到了": "提到了",
            "天文數字": "天文数字",
            "數字": "数字",
            "短短一周": "短短一周",
            "國際油價": "国际油价",
            "就像拖江的野馬": "就像脱缰的野马",
            "在100美元大關": "在100美元大关",
            "大關": "大关",
            "來回橫衝直撞": "来回横冲直撞",
            "咱們普通人": "咱们普通人",
            "可能對": "可能对",
            "紅大的政治敘事": "宏大的政治叙事",
            "宏大": "宏大",
            "敘事": "叙事",
            "沒那麼敏感": "没那么敏感",
            "可當": "可当",
            "加油站的架目表": "加油站的价目表",
            "架目表": "价目表",
            "跳到": "跳到",
            "一個讓人心驚肉跳的數字": "一个让人心惊肉跳的数字",
            "心驚肉跳": "心惊肉跳",
            "當超市裡的進口貨": "当超市里的进口货",
            "進口貨": "进口货",
            "因為": "因为",
            "航運中斷": "航运中断",
            "航運": "航运",
            "而斷貨時": "而断货时",
            "斷貨": "断货",
            "戰爭的含義": "战争的含义",
            "就真的穿透了國境線": "就真的穿透了国境线",
            "國境線": "国境线",
            "直接爬上了每個家庭的餐桌": "直接影响到了每个家庭的生活",
            "同時": "同时",
            "華盛頓的日子": "华盛顿的日子",
            "華盛頓": "华盛顿",
            "也並不太平": "也并不太平",
            "白宮最初想把這次行動": "白宫最初想把这次行动",
            "白宮": "白宫",
            "這次行動": "这次行动",
            "包裝成": "包装成",
            "一次短促且必要的懲罰": "一次短促且必要的惩罚",
            "短促": "短促",
            "懲罰": "惩罚",
            "可結果呢": "可结果呢",
            "到了第七天": "到了第七天",
            "反戰浪潮": "反战浪潮",
            "開始在美國各大城市蔓延": "开始在美国各大城市蔓延",
            "開始": "开始",
            "美國": "美国",
            "納稅人們": "纳税人",
            "納稅人": "纳税人",
            "開始著想": "开始思考",
            "在全球經濟這麼不穩定的當下": "在全球经济这么不稳定的当下",
            "全球經濟": "全球经济",
            "這麼": "这么",
            "不穩定": "不稳定",
            "當下": "当下",
            "再往中東這個泥沼裡跳去": "再往中东这个泥潭里陷进去",
            "中東": "中东",
            "泥沼": "泥潭",
            "裡": "里",
            "國際社會被划分成了兩半": "国际社会被分成了两半",
            "國際社會": "国际社会",
            "兩半": "两半",
            "一邊是緊緊跟隨的盟友": "一边是紧紧跟随的盟友",
            "一邊": "一边",
            "緊緊跟隨": "紧紧跟随",
            "另一邊則是以中俄為代表": "另一边则是以中俄为代表",
            "另一邊": "另一边",
            "中俄": "中俄",
            "呼籲坐下來談的冷靜力量": "呼吁坐下来谈判的冷静力量",
            "呼籲": "呼吁",
            "坐下來": "坐下来",
            "冷靜": "冷静",
            "這種撕裂感": "这种撕裂感",
            "這種": "这种",
            "撕裂感": "撕裂感",
            "讓二戰以來建立的那套國際秩序": "让二战以来建立的那套国际秩序",
            "二戰": "二战",
            "以來": "以来",
            "國際秩序": "国际秩序",
            "顯得特別脆弱": "显得特别脆弱",
            "顯得": "显得",
            "特別": "特别",
            "脆弱": "脆弱",
            "就像一張隨時會崩斷的舊王": "就像一张随时会崩断的旧网",
            "一張": "一张",
            "隨時": "随时",
            "崩斷": "崩断",
            "舊王": "旧网",
            "現在這精心動魄的第一個七天": "现在这惊心动魄的第一个七天",
            "現在": "现在",
            "精心動魄": "惊心动魄",
            "第一個": "第一个",
            "總算要熬過去了": "总算要熬过去了",
            "總算": "总算",
            "熬過去": "熬过去",
            "可世界卻站在了": "可世界却站在了",
            "世界": "世界",
            "卻": "却",
            "最危險的十字路口": "最危险的十字路口",
            "最危險": "最危险",
            "十字路口": "十字路口",
            "誰也說不准": "谁也说不准",
            "誰也": "谁也",
            "說不准": "说不准",
            "下周等來的是河潭的曙光": "下周迎来的是和解的曙光",
            "下周": "下周",
            "等來": "迎来",
            "河潭": "和解",
            "曙光": "曙光",
            "還是衝突滑向大規模地面站的深淵": "还是冲突滑向大规模地面战的深渊",
            "還是": "还是",
            "大規模": "大规模",
            "地面站": "地面战",
            "深淵": "深渊",
            "廢墟上的煙塵": "废墟上的烟尘",
            "廢墟": "废墟",
            "煙塵": "烟尘",
            "還沒散盡": "还没散尽",
            "還沒": "还没",
            "散盡": "散尽",
            "但那些關於河潭與發展的舊共識": "但那些关于和解与发展的旧共识",
            "那些": "那些",
            "關於": "关于",
            "河潭與發展": "和解与发展",
            "舊共識": "旧共识",
            "早就在爆炸聲中變得面目全非了": "早就在爆炸声中变得面目全非了",
            "早在": "早在",
            "爆炸聲": "爆炸声",
            "變得": "变得",
            "面目全非": "面目全非",
            "歷史往往就在這種不經意間": "历史往往就在这种不经意间",
            "歷史": "历史",
            "往往": "往往",
            "不經意間": "不经意间",
            "轉了個大彎": "转了个大弯",
            "轉了": "转了",
            "大彎": "大弯",
            "而我們這一代人正秉持細致的": "而我们这一代人正屏息凝神地",
            "而": "而",
            "我們": "我们",
            "這一代人": "这一代人",
            "正": "正",
            "秉持細致的": "屏息凝神地",
            "坐在這輛失控的賽道上": "坐在这辆失控的列车上",
            "坐在": "坐在",
            "這輛": "这辆",
            "失控": "失控",
            "賽道": "列车",
            "看著窗外飛逝而過的未知": "看着窗外飞逝而过的未知",
            "窗外": "窗外",
            "飛逝而過": "飞逝而过",
            "未知": "未知",
            "還有": "还有",
            "行動": "行动",
            "著想": "思考",
            "這麼": "这么",
            "則是": "则是",
            "為": "为",
            "這種": "这种",
            "與發展": "与发展",
            "這輛": "这辆",
            "泥沼": "泥潭",
            "裡": "里",
            "這": "这",
            "麼": "么",
            "輛": "辆",
            "種": "种"
        }
        
        # 修正常见错别字
        corrections = {
            # 常见错别字
            "島煤彈": "小行星",
            "肥水星": "水星",
            "塔里太陽平均": "距离太阳平均",
            "踩": "约",
            "四轉": "自转",
            "射石度": "摄氏度",
            "內河": "内核",
            "鐵哥的": "铁球",
            "坑坑挖挖": "坑坑洼洼",
            "撕後": "结束",
            "皮胎": "基地",
            "拽進": "拖入",
            "脈斷貨": "断货",
            "泥潭": "局势",
            "賽車": "列车",
            "沙啞": "沙哑",
            "節點": "节点",
            "外科手術式": "外科手术式",
            "定點清除": "定点清除",
            "可預想": "可预想",
            "瞬間瓦解": "瞬间瓦解",
            "權力核心": "权力核心",
            "斷網斷電": "断网断电",
            "廢墟": "废墟",
            "強硬": "强硬",
            "衛星信號": "卫星信号",
            "波斯灣": "波斯湾",
            "霍爾木茲": "霍尔木兹",
            "急性病": "急性病",
            "艦隊": "舰队",
            "航道": "航道",
            "水雷": "水雷",
            "神出鬼沒": "神出鬼没",
            "自殺式快艇": "自杀式快艇",
            "保險公司": "保险公司",
            "保費": "保费",
            "天文數字": "天文数字",
            "油價": "油价",
            "拖江": "脱缰",
            "野馬": "野马",
            "大關": "大关",
            "橫衝直撞": "横冲直撞",
            "紅大": "宏大",
            "敘事": "叙事",
            "加油站": "加油站",
            "架目表": "价目表",
            "心驚肉跳": "心惊肉跳",
            "航運": "航运",
            "國境線": "国境线",
            "華盛頓": "华盛顿",
            "白宮": "白宫",
            "短促": "短促",
            "懲罰": "惩罚",
            "反戰浪潮": "反战浪潮",
            "納稅人": "纳税人",
            "中東": "中东",
            "國際社會": "国际社会",
            "裂成": "裂成",
            "盟友": "盟友",
            "中俄": "中俄",
            "呼籲": "呼吁",
            "撕裂感": "撕裂感",
            "二戰": "二战",
            "國際秩序": "国际秩序",
            "舊王": "旧网",
            "精心動魄": "惊心动魄",
            "熬過去": "熬过去",
            "河潭": "和解",
            "衝突": "冲突",
            "大規模地面戰": "大规模地面战",
            "深淵": "深渊",
            "煙塵": "烟尘",
            "散進": "散去",
            "河潭與發展": "和解与发展",
            "舊共識": "旧共识",
            "面目全非": "面目全非",
            "轉了個大彎": "转了个大弯",
            "秉持悉凝神": "屏息凝神",
            "失控": "失控",
            "列車": "列车",
            "飛遲而過": "飞驰而过",
            "未知": "未知",
            "應聲聲": "应声",
            "指揮中書": "指挥中心",
            "加固延體": "加固建筑",
            "泥沼": "泥潭",
            "地面站": "地面战",
            "賽道": "列车",
            "聽起來透著一種沙啞的尸体": "听起来透着一种沙哑的感觉",
            "應聲聲拽進": "瞬间拖入",
            "被展現的淋漓盡致": "展现得淋漓尽致",
            "被盯著很久的和研發設施": "被盯了很久的核研发设施",
            "加固延體": "加固建筑",
            "清晰的傳遍了": "清晰地传遍了",
            "戰火在前方燒著": "战火在前方燃烧",
            "也跟著帶來了": "也随之引发了",
            "一直想清楚": "一直想开辟",
            "神出鬼沒的": "神出鬼没的",
            "把這一代的保費": "把这一区域的保费",
            "拖江的野馬": "脱缰的野马",
            "紅大的政治敘事": "宏大的政治叙事",
            "加油站的架目表": "加油站的价目表",
            "直接爬上了每個家庭的餐桌": "直接影响到了每个家庭的生活",
            "白宮最初想把這次行動": "白宫最初想把这次行动",
            "納稅人們開始著想": "纳税人开始思考",
            "再往中東這個泥沼裡跳去": "再往中东这个泥潭里陷进去",
            "國際社會被划分成了兩半": "国际社会被分成了两半",
            "呼籲坐下來談的冷靜力量": "呼吁坐下来谈判的冷静力量",
            "讓二戰以來建立的那套國際秩序": "让二战以来建立的那套国际秩序",
            "就像一張隨時會崩斷的舊王": "就像一张随时会崩断的旧网",
            "現在這精心動魄的第一個七天": "现在这惊心动魄的第一个七天",
            "可世界卻站在了": "可世界却站在了",
            "誰也說不准下周等來的是河潭的曙光": "谁也说不准下周迎来的是和解的曙光",
            "還是衝突滑向大規模地面站的深淵": "还是冲突滑向大规模地面战的深渊",
            "但那些關於河潭與發展的舊共識": "但那些关于和解与发展的旧共识",
            "早就在爆炸聲中變得面目全非了": "早就在爆炸声中变得面目全非了",
            "歷史往往就在這種不經意間": "历史往往就在这种不经意间",
            "而我們這一代人正秉持細致的": "而我们这一代人正屏息凝神地",
            "坐在這輛失控的賽道上": "坐在这辆失控的列车上",
            "看著窗外飛逝而過的未知": "看着窗外飞逝而过的未知"
        }
        
        # 应用繁简转换
        for traditional, simplified in traditional_to_simplified.items():
            text = text.replace(traditional, simplified)
        
        # 应用错别字修正
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
        
        # 修正语句不通顺的地方
        text = text.replace("听起来透着一种沙哑的尸体", "听起来透着一种沙哑的感觉")
        text = text.replace("世界像是被应声拖入了一个充满不确定性的新纪元", "世界像是被瞬间拖入了一个充满不确定性的新纪元")
        text = text.replace("对著伊朗境内的指挥中心、雷达阵地", "对着伊朗境内的指挥中心、雷达阵地")
        text = text.replace("还有那些被盯了很久的核研发设施", "还有那些被盯了很久的核研发设施")
        text = text.replace("看着画面里那些被导弹瞬间穿透的加固建筑", "看着画面里那些被导弹瞬间穿透的加固建筑")
        text = text.replace("德黑兰的权力核心迅速转入地下。", "德黑兰的权力核心迅速转入地下。")
        text = text.replace("即便在断网断电的废墟上", "即便在断网断电的废墟上")
        text = text.replace("那些强硬的声音依然通过卫星信号清晰地传遍了波斯湾的每一个角落", "那些强硬的声音依然通过卫星信号清晰地传遍了波斯湾的每一个角落")
        text = text.replace("这几天其实证明了一个挺残酷的真理", "这几天其实证明了一个挺残酷的真理")
        text = text.replace("炸毁一座桥只需要几秒钟", "炸毁一座桥只需要几秒钟")
        text = text.replace("但要摧毁一个政权的意志恐怕得经历一场通向深渊的漫长对峙", "但要摧毁一个政权的意志恐怕得经历一场通向深渊的漫长对峙")
        text = text.replace("战火在前方燃烧", "战火在前方燃烧")
        text = text.replace("全球经济也随之引发了一场叫做霍尔木兹恐惧的急性病", "全球经济也随之引发了一场叫做霍尔木兹恐惧的急性病")
        text = text.replace("虽说美军第五舰队一直想开辟一条安全航道", "虽说美军第五舰队一直想开辟一条安全航道")
        text = text.replace("但海面下散布的水雷和那些神出鬼没的自杀式快艇", "但海面下散布的水雷和那些神出鬼没的自杀式快艇")
        text = text.replace("还是让保险公司把这一区域的保费提到了天文数字", "还是让保险公司把这一区域的保费提到了天文数字")
        text = text.replace("短短一周，国际油价就像脱缰的野马在100美元大关来回横冲直撞", "短短一周，国际油价就像脱缰的野马在100美元大关来回横冲直撞")
        text = text.replace("咱们普通人可能对宏大的政治叙事没那么敏感", "咱们普通人可能对宏大的政治叙事没那么敏感")
        text = text.replace("可当加油站的价目表跳到一个让人心惊肉跳的数字", "可当加油站的价目表跳到一个让人心惊肉跳的数字")
        text = text.replace("当超市里的进口货因为航运中断而断货时", "当超市里的进口货因为航运中断而断货时")
        text = text.replace("战争的含义就真的穿透了国境线，直接影响到了每个家庭的生活", "战争的含义就真的穿透了国境线，直接影响到了每个家庭的生活")
        text = text.replace("同时，华盛顿的日子也并不太平", "同时，华盛顿的日子也并不太平")
        text = text.replace("白宫最初想把这次行动包装成一次短促且必要的惩罚", "白宫最初想把这次行动包装成一次短促且必要的惩罚")
        text = text.replace("到了第七天，反战浪潮开始在美国各大城市蔓延", "到了第七天，反战浪潮开始在美国各大城市蔓延")
        text = text.replace("纳税人开始思考在全球经济这么不稳定的当下", "纳税人开始思考在全球经济这么不稳定的当下")
        text = text.replace("再往中东这个泥潭里陷进去", "再往中东这个泥潭里陷进去")
        text = text.replace("这也证明了国际社会被分成了两半", "这也证明了国际社会被分成了两半")
        text = text.replace("一边是紧紧跟随的盟友，另一边则是以中俄为代表", "一边是紧紧跟随的盟友，另一边则是以中俄为代表")
        text = text.replace("呼吁坐下来谈判的冷静力量", "呼吁坐下来谈判的冷静力量")
        text = text.replace("这种撕裂感让二战以来建立的那套国际秩序显得特别脆弱", "这种撕裂感让二战以来建立的那套国际秩序显得特别脆弱")
        text = text.replace("就像一张随时会崩断的旧网", "就像一张随时会崩断的旧网")
        text = text.replace("现在这惊心动魄的第一个七天总算要熬过去了", "现在这惊心动魄的第一个七天总算要熬过去了")
        text = text.replace("可世界却站在了最危险的十字路口", "可世界却站在了最危险的十字路口")
        text = text.replace("谁也说不准下周迎来的是和解的曙光", "谁也说不准下周迎来的是和解的曙光")
        text = text.replace("还是冲突滑向大规模地面战的深渊", "还是冲突滑向大规模地面战的深渊")
        text = text.replace("废墟上的烟尘还没散尽", "废墟上的烟尘还没散尽")
        text = text.replace("但那些关于和解与发展的旧共识早就在爆炸声中变得面目全非了", "但那些关于和解与发展的旧共识早就在爆炸声中变得面目全非了")
        text = text.replace("历史往往就在这种不经意间转了个大弯", "历史往往就在这种不经意间转了个大弯")
        text = text.replace("而我们这一代人正屏息凝神地坐在这辆失控的列车上看着窗外飞逝而过的未知", "而我们这一代人正屏息凝神地坐在这辆失控的列车上看着窗外飞逝而过的未知")
        
        # 修正科学数据
        # 水星温度修正
        text = text.replace("白天能飆到427射石度", "白天能达到427摄氏度")
        text = text.replace("晚上瞬間跌到1703射石度", "晚上会骤降至-173摄氏度")
        
        # 修正单位表述
        text = text.replace("天文單位", "天文单位")
        
        return text
    
    def analyze_content_type(self, sentence):
        """分析内容类型 - 增强版，包含更多军事和政治相关词汇"""
        # 内容类型关键词及其权重
        content_types = {
            "military": {
                "keywords": ["战争", "军事", "军队", "士兵", "武器", "导弹", "飞机", "战斗机", "轰炸", "打击",
                            "防空", "警报", "冲突", "战斗", "作战", "袭击", "攻击", "防御", "伤亡", "尸体",
                            "战略", "战术", "军事基地", "军营", "战区", "前线", "后勤", "装备",
                            # 添加国家和地缘政治相关词汇
                            "伊朗", "美国", "以色列", "中东", "波斯湾", "霍尔木兹", "德黑兰",
                            "美军", "以军", "伊斯兰", "革命卫队", "IRGC", "核设施",
                            # 添加作战相关词汇
                            "无人机", "空袭", "地面战", "海军", "空军", "陆军", "航母", "舰队",
                            "水雷", "快艇", "雷达", "指挥中心", "核研发", "加固建筑",
                            # 添加战争影响词汇
                            "油价", "航运", "保险", "保费", "断网", "断电", "废墟", "烟尘",
                            # 添加局势相关词汇（用于上下文理解）
                            "局势", "局勢", "战局", "戰局", "形势", "形勢", "格局", "态势", "態勢", "局面",
                            # 添加抵抗、战斗相关词汇
                            "抵抗", "反抗", "抗战", "战斗", "作战", "战争", "戰爭", "戰爭", "战事", "战况",
                            # 添加力量、实力相关词汇
                            "实力", "實力", "力量", "战力", "战斗力", "武装", "武器", "装备", "部队", "军队",
                            # 添加时间、变化相关词汇
                            "时间", "期间", "时期", "阶段", "过程", "变化", "變化", "转变", "轉變", "发展"],
                "weight": 1.0
            },
            "politics": {
                "keywords": ["政治", "政府", "国家", "总统", "领导人", "外交", "国际", "政策", "政权", "议会",
                            "选举", "党派", "官员", "制裁", "谈判", "协议", "条约", "声明", "抗议", "游行",
                            # 添加更多政治相关词汇
                            "白宫", "华盛顿", "反战", "纳税人", "国际社会", "盟友", "中俄", "谈判",
                            "国际秩序", "共识", "和解", "发展", "历史",
                            # 添加局势相关词汇
                            "局势", "局勢", "形势", "形勢", "格局", "态势", "態勢", "局面", "变动", "變動", "更迭", "变化", "變化"],
                "weight": 0.95
            },
            "space": {
                "keywords": ["太空", "宇宙", "星球", "行星", "恒星", "卫星", "轨道", "引力", "黑洞", "星云", 
                            "水星", "金星", "地球", "火星", "木星", "土星", "天王星", "海王星", 
                            "太阳系", "银河系", "天文单位", "公转", "自转", "日心", "地心", 
                            "陨石", "彗星", "小行星", "空间站", "宇航员"],
                "weight": 1.0
            },
            "science": {
                "keywords": ["科学", "研究", "实验", "理论", "数据", "分析", "发现", "技术", "原理", "规律"],
                "weight": 0.9
            },
            "nature": {
                "keywords": ["自然", "环境", "生态", "气候", "动物", "植物", "地形", "地貌", "水文", "地质"],
                "weight": 0.8
            },
            "history": {
                "keywords": ["历史", "古代", "文明", "文化", "传统", "遗迹", "考古", "文物", "朝代", "事件"],
                "weight": 0.8
            },
            "technology": {
                "keywords": ["科技", "技术", "发明", "创新", "人工智能", "计算机", "网络", "数码", "自动化", "机器人"],
                "weight": 0.9
            },
            "art": {
                "keywords": ["艺术", "绘画", "音乐", "文学", "电影", "戏剧", "雕塑", "建筑", "设计", "创意"],
                "weight": 0.7
            },
            "education": {
                "keywords": ["教育", "学习", "知识", "培训", "课程", "学校", "教师", "学生", "教材", "考试"],
                "weight": 0.7
            },
            "business": {
                "keywords": ["商业", "经济", "市场", "企业", "金融", "贸易", "管理", "营销", "创业", "投资"],
                "weight": 0.7
            },
            "health": {
                "keywords": ["健康", "医疗", "疾病", "治疗", "预防", "营养", "运动", "心理", "生理", "医药"],
                "weight": 0.8
            },
            "travel": {
                "keywords": ["旅行", "旅游", "景点", "风景", "城市", "乡村", "文化", "体验", "探索", "冒险"],
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
        else:
            # 根据提示词类型生成相应的提示词
            if prompt_type == "SD提示词":
                prompt_en = self._generate_sd_prompt(description_parts, content_type, shot_id)
            else:
                prompt_en = self._generate_doubao_prompt(description_parts, content_type, shot_id)
        
        # 根据优化方式选择不同的优化策略
        optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
        
        # 检查并规范化优化方式
        if not optimization_method or optimization_method not in ["脚本自带", "本地大模型", "脚本优化"]:
            optimization_method = "脚本自带"
        
        # 添加日志记录当前使用的优化方式
        if not hasattr(self, '_last_optimization_method') or self._last_optimization_method != optimization_method:
            self.log(f"🎯 当前优化方式: {optimization_method}")
            self._last_optimization_method = optimization_method
        
        # 仅在"本地大模型"模式下评估质量
        prompt_quality = 0.0
        if optimization_method == "本地大模型":
            # 使用Ollama大模型优化提示词
            optimized_prompt = self.optimize_prompt_with_ollama(prompt_en, description_parts['dubbing'])
            prompt_quality = self.evaluate_prompt_quality(optimized_prompt, description_parts['dubbing'], content_type)
        elif optimization_method == "脚本优化":
            # "脚本优化"模式：直接使用 _generate_sd_prompt 或 _generate_doubao_prompt 生成的结果
            # 不再调用 _enhance_prompt_with_details，避免重复生成
            # 因为 _generate_*_prompt 函数已经包含了完整的生成逻辑
            optimized_prompt = prompt_en
        else:
            # "脚本自带" - 直接使用原始提示词
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
            "description": sentence,
            "prompt_en": optimized_prompt,
            "image_file": f"shot_{shot_id+1:02d}.png",
            "content_type": content_type,
            "semantic_weight": self.calculate_semantic_weight(description_parts['dubbing']),
            "prompt_quality": prompt_quality
        }
        
        # 如果是SD提示词模式，使用定制化的反向提示词
        if prompt_type == "SD提示词":
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
        
        # 如果没有提取到visual_concept，尝试从dubbing智能推断（仅在大模型模式下）
        if not result['visual_concept'] and result['dubbing']:
            optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
            if optimization_method == "本地大模型":
                result['visual_concept'] = self._infer_visual_concept_from_dubbing(result['dubbing'])
        
        # 如果没有提取到visual_elements，尝试从dubbing智能推断（仅在大模型模式下）
        if not result['visual_elements'] and result['dubbing']:
            optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
            if optimization_method == "本地大模型":
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
    
    def _generate_sd_prompt(self, description_parts, content_type, shot_id):
        """生成SD提示词 - 根据分镜的独特内容"""
        import re
        
        prompt_parts = []
        
        # 1. 主体内容 - 基于画面构思和视觉元素
        if description_parts['visual_concept']:
            # 将中文画面构思翻译/转化为英文视觉描述
            visual_desc = self._translate_visual_concept(description_parts['visual_concept'])
            prompt_parts.append(visual_desc)
        elif description_parts.get('dubbing'):
            # 如果没有画面构思，从配音文本推断（仅在大模型模式下）
            optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
            # 无论哪种模式，都尝试从配音文本推断视觉概念
            if optimization_method == "本地大模型":
                inferred_concept = self._infer_visual_concept_from_dubbing(description_parts['dubbing'])
                if inferred_concept:
                    translated_concept = self._translate_visual_concept(inferred_concept)
                    if translated_concept:
                        prompt_parts.append(translated_concept)
            else:
                # 脚本自带/脚本优化模式也尝试提取
                inferred_concept = self._infer_visual_concept_from_dubbing(description_parts['dubbing'])
                if inferred_concept:
                    translated_concept = self._translate_visual_concept(inferred_concept)
                    if translated_concept:
                        prompt_parts.append(translated_concept)
        
        # 2. 基于内容类型的场景设定
        scene_keywords = self._get_scene_keywords_by_content(content_type, description_parts['dubbing'])
        if scene_keywords:
            prompt_parts.append(scene_keywords)
        
        # 3. 智能融合：核心主题 + 视觉基调 + 音频语义
        semantic_elements = self._intelligent_fuse_semantics(
            description_parts.get('dubbing', ''),
            description_parts.get('custom_theme', ''),
            description_parts.get('custom_visual_tone', ''),
            content_type
        )
        if semantic_elements:
            prompt_parts.append(semantic_elements)
        
        # 4. 视觉元素
        # 无论哪种模式，都尝试从配音文本提取视觉元素
        extracted_elements = self._extract_elements_from_dubbing(description_parts.get('dubbing', ''))
        if extracted_elements:
            translated_elements = self._translate_visual_concept(extracted_elements)
            if translated_elements:
                prompt_parts.append(translated_elements)
        elif description_parts.get('theme_elements'):
            # 使用大模型分析得到的主题元素
            elements_list = description_parts['theme_elements']
            if isinstance(elements_list, list):
                elements_str = ', '.join(elements_list[:5])  # 限制最多5个元素
            else:
                elements_str = str(elements_list)
            translated_elements = self._translate_visual_concept(elements_str)
            if translated_elements:
                prompt_parts.append(translated_elements)
        elif description_parts.get('visual_elements'):
            # 如果大模型没提取到，使用配置中的visual_elements
            elements = self._translate_visual_concept(description_parts['visual_elements'])
            if elements:
                prompt_parts.append(elements)
        else:
            # 如果都没有，根据内容类型添加fallback
            fallback_elements = self._get_fallback_elements_by_content_type(content_type)
            if fallback_elements:
                prompt_parts.append(fallback_elements)
        
        # 5. 自定义核心主题（如果有）
        if description_parts.get('custom_theme'):
            theme = description_parts['custom_theme']
            # 检查是否包含中文字符
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in theme)
            if has_chinese:
                theme_translation = self._translate_visual_concept(theme)
                if theme_translation:
                    prompt_parts.append(theme_translation)
            else:
                # 如果是英文，直接使用
                prompt_parts.append(theme)
        
        # 6. 自定义视觉基调（如果有）
        if description_parts.get('custom_visual_tone'):
            tone = description_parts['custom_visual_tone']
            # 检查是否包含中文字符
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in tone)
            if has_chinese:
                tone_translation = self._translate_visual_concept(tone)
                if tone_translation:
                    prompt_parts.append(tone_translation)
            else:
                # 如果是英文，直接使用
                prompt_parts.append(tone)
        
        # 7. 光线和氛围 - 根据情感基调
        lighting = self._get_lighting_by_mood(description_parts['dubbing'])
        prompt_parts.append(lighting)
        
        # 8. 构图和视角 - 根据shot_id轮换，增加多样性
        composition = self._get_composition_by_shot_id(shot_id)
        prompt_parts.append(composition)
        
        # 9. 艺术风格
        style = self._get_art_style(content_type, description_parts.get('style', ''))
        prompt_parts.append(style)
        
        # 10. 质量标签 - 包含正向提示词
        prompt_parts.extend([
            "masterpiece, best quality, ultra detailed, photorealistic, cinematic lighting, dramatic mood, high contrast, detailed, 8k, high resolution, professional photography"
        ])
        
        # 8. 合并并去重提示词
        # 人体相关词，仅在需要人物出镜时保留
        is_person_scene = any(word in description_parts.get('dubbing', '') for word in ['人', '人物', '人物', '主持人', '记者', '医生', '科学家', '总统', '官员', '人物'])
        
        all_prompt_parts = []
        seen = set()
        
        # 需要过滤的词（仅在非人物场景时过滤）
        person_only_tags = [
            'detailed skin texture', 'realistic pupils', 'soft skin', 
            'skin pores', 'eye detail', 'facial features', 'wrinkles',
            'beautiful face', 'pretty face', 'ugly face'
        ]
        
        for part in prompt_parts:
            if not part:
                continue
            # 按逗号分隔每个tag
            tags = [t.strip() for t in part.split(',')]
            for tag in tags:
                # 提取tag的基础词（去除权重）
                base_tag = tag.strip().lower()
                original_tag = tag.strip()
                for suffix in ['(1.0)', '(1.1)', '(1.2)', '(1.3)', '(1.4)', '(1.5)', '(1.6)', '(1.7)', '(1.8)', '(1.9)', '(2.0)']:
                    base_tag = base_tag.replace(suffix, '')
                    original_tag = original_tag.replace(suffix, '')
                base_tag = base_tag.strip()
                original_tag = original_tag.strip()
                
                # 过滤人体相关词（非人物场景）
                if not is_person_scene:
                    if any(pt in base_tag for pt in person_only_tags):
                        continue
                
                # 如果没出现过，添加
                if base_tag and base_tag not in seen:
                    seen.add(base_tag)
                    # 恢复原始权重格式
                    weight_match = tag.strip()
                    if '(' in weight_match and ')' in weight_match:
                        all_prompt_parts.append(tag.strip())
                    else:
                        all_prompt_parts.append(original_tag)
        
        return ", ".join(all_prompt_parts)
    
    def _generate_doubao_prompt(self, description_parts, content_type, shot_id):
        """生成豆包提示词 - 直接从配音文本生成，不依赖画面构思"""
        import re
        
        dubbing = description_parts['dubbing']
        prompt_parts = []
        
        # 1. 场景类型 - 基于内容类型和配音内容
        scene_type = self._get_scene_type_zh(content_type, dubbing)
        prompt_parts.append(scene_type)
        
        # 2. 主体描述 - 直接从配音文本智能生成（不再依赖visual_concept）
        subject_desc = self._generate_subject_from_dubbing(dubbing, content_type)
        if subject_desc:
            prompt_parts.append(f"画面主体：{subject_desc}")
        
        # 3. 视觉元素 - 直接从配音文本提取关键词
        visual_elements = self._extract_elements_from_dubbing(dubbing)
        if visual_elements:
            prompt_parts.append(f"视觉元素：{visual_elements}")
        
        # 4. 光线氛围
        lighting_zh = self._get_lighting_zh(dubbing)
        prompt_parts.append(lighting_zh)
        
        # 5. 构图视角
        composition_zh = self._get_composition_zh(shot_id)
        prompt_parts.append(composition_zh)
        
        # 6. 艺术风格
        style_zh = self._get_art_style_zh(content_type)
        prompt_parts.append(style_zh)
        
        # 7. 技术要求
        prompt_parts.extend([
            "高清画质，细节丰富",
            "专业摄影效果，电影级画面"
        ])
        
        return "，".join([p for p in prompt_parts if p])
    
    def _generate_subject_from_dubbing(self, dubbing, content_type):
        """从配音文本直接生成主体描述 - 智能语义分析版"""
        
        # 1. 军事冲突场景（最优先）
        if "military" in content_type or any(w in dubbing for w in ["战争", "冲突", "军事", "战斗", "战略", "战术", "武器", "军队", "部队"]):
            if any(w in dubbing for w in ["伊朗", "美国", "以色列", "敌方", "对手", "盟军", "联军"]):
                return "军事指挥中心，战略分析场景，军事地图与战术屏幕，严肃氛围"
            elif any(w in dubbing for w in ["硬碰硬", "对抗", "较量", "冲突", "交锋", "激战"]):
                return "军事对峙场景，双方力量对比，紧张氛围，对峙局面"
            elif any(w in dubbing for w in ["家底", "实力", "力量", "资源", "储备", "战力"]):
                return "军事力量展示，装备与人员，战争潜力，军事实力"
            elif any(w in dubbing for w in ["局势", "局勢", "战局", "戰局", "形势", "形勢", "格局", "态势", "態勢"]):
                return "战争局势图，战略态势展示，战场形势分析"
            elif any(w in dubbing for w in ["更迭", "变化", "變化", "转变", "轉變", "转折", "演变", "演變"]):
                return "战争进程演变，局势变化过程，历史转折时刻"
            else:
                return "现代战争场景，军事冲突环境，战场氛围"
        
        # 2. 政治外交场景
        if any(w in dubbing for w in ["政治", "外交", "国际", "政府", "国家", "政权", "议会", "选举", "谈判", "协议", "制裁", "局势", "格局"]):
            if any(w in dubbing for w in ["更迭", "变化", "转变", "转折", "演变", "动荡", "危机"]):
                return "政治局势演变，权力更迭过程，历史转折时刻"
            elif any(w in dubbing for w in ["几周", "时间", "短期", "即将", "很快", "马上"]):
                return "时间流逝象征，历史进程加速，紧迫时刻"
            else:
                return "国际政治场景，外交谈判环境，政治舞台"
        
        # 3. 时间/进程场景
        if any(w in dubbing for w in ["几周", "时间", "短期", "即将", "很快", "马上", "倒计时", "紧迫", "加速"]):
            return "时间流逝象征，历史进程，紧迫时刻，倒计时氛围"
        
        # 4. 抽象概念场景（用于"局势更迭"这类抽象描述）
        if any(w in dubbing for w in ["局势", "形势", "格局", "态势", "局面", "状况"]):
            if any(w in dubbing for w in ["更迭", "变化", "转变", "转折", "演变", "变革", "动荡"]):
                return "局势演变可视化，权力转移象征，历史转折点"
            else:
                return "复杂局势展示，多方力量博弈，战略格局"
        
        # 5. 默认场景（不再返回空洞的"纪实摄影场景"）
        # 根据语义推断一个合理的场景
        if len(dubbing) < 10:
            return "特写镜头，细节展示，微观视角"
        elif any(w in dubbing for w in ["大", "宏观", "整体", "全局", "全面"]):
            return "宏观视角，全景展示，大局观"
        elif any(w in dubbing for w in ["小", "细节", "局部", "具体", "个别"]):
            return "特写镜头，细节展示，微观视角"
        else:
            return "主题相关场景，与内容匹配的视觉画面，符合语境的环境"
    
    def _extract_elements_from_dubbing(self, dubbing):
        """从配音文本智能提取视觉元素 - 支持本地和大模型两种模式"""
        if not dubbing or len(dubbing.strip()) < 2:
            return ""
        
        # 优先尝试本地提取（不依赖大模型）
        local_result = self._extract_elements_locally(dubbing)
        if local_result:
            return local_result
        
        # 检查是否配置了 Ollama，如果配置了则尝试大模型提取
        if not hasattr(self, 'ollama_model_var') or not self.ollama_model_var.get():
            # 没有配置大模型，返回空（已通过本地提取处理）
            return ""
        
        try:
            model = self.ollama_model_var.get()
            ollama_url = "http://localhost:11434"
            
            prompt = f"""从以下配音文本中提取出能够用于图像生成的视觉元素关键词。
要求：
1. 提取具体的视觉对象、场景、人物、物品等（至少3-5个）
2. 用英文逗号分隔每个关键词
3. 只返回关键词，不要其他解释

配音文本：{dubbing}

返回格式：关键词1, 关键词2, 关键词3"""
            
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
                visual_keywords = result.get('response', '').strip()
                visual_keywords = visual_keywords.strip()
                if visual_keywords:
                    return visual_keywords
            
            return ""
        except Exception as e:
            return ""
    
    def _extract_elements_locally(self, dubbing):
        """本地模式：从配音文本提取视觉元素（不依赖大模型）"""
        import re
        
        if not dubbing:
            return ""
        
        visual_keywords = []
        
        # 军事/战争相关关键词
        military_mapping = {
            '美军': 'US military, American soldiers, US army',
            '伊朗': 'Iran, Iranian, Persia',
            '革命卫队': 'Revolutionary Guard, IRGC, Iranian military',
            '军队': 'military, armed forces, troops',
            '部队': 'troops, military unit',
            '战争': 'war, warfare, battlefield',
            '冲突': 'conflict, clash, confrontation',
            '战斗': 'battle, combat, fighting',
            '导弹': 'missile, rocket, projectile',
            '无人机': 'drone, UAV, unmanned aircraft',
            '战斗机': 'fighter jet, aircraft, warplane',
            '轰炸机': 'bomber, bombing aircraft',
            '航母': 'aircraft carrier, warship',
            '军舰': 'warship, naval vessel',
            '海军': 'navy, naval forces',
            '空军': 'air force, aviation',
            '陆军': 'army, ground forces',
            '武器': 'weapon, arms, armament',
            '军事': 'military, armed, warfare',
            '基地': 'military base, base',
            '战场': 'battlefield, war zone, front line',
            '进攻': 'attack, offensive, assault',
            '防御': 'defense, defensive',
            '轰炸': 'bombing, air strike, raid',
            '摧毁': 'destroyed, devastated, ruin',
            '爆炸': 'explosion, blast, detonation',
            '伤亡': 'casualties, deaths, injuries',
            '平民': 'civilians, civilians',
            '难民': 'refugees, displaced people',
            '国际': 'international, global',
            '中东': 'Middle East, MENA region',
        }
        
        # 合并所有关键词映射
        keyword_mapping = dict(military_mapping)
        keyword_mapping.update({
            '黑洞': 'black hole, event horizon, accretion disk',
            '宇宙': 'universe, cosmos, deep space',
            '太空': 'outer space, celestial',
            '星球': 'planet, celestial body',
            '银河': 'milky way, galaxy',
            '星系': 'galaxy, star system',
            '恒星': 'star, sun',
            '行星': 'planet',
            '星云': 'nebula, cosmic dust',
            'X射线': 'X-ray, radiation',
            '光': 'light, rays, glow',
            '热量': 'heat, thermal energy',
            '温度': 'temperature, heat',
            '攝氏度': 'Celsius degrees',
            '數千萬': 'tens of millions',
            '銀河系': 'Milky Way galaxy',
            '中心': 'center, core',
            '爆炸': 'explosion, blast',
            '能量': 'energy, power',
            '辐射': 'radiation',
            '天体': 'celestial body, heavenly body',
            '光年': 'light years',
            '距离': 'distance',
            '科学家': 'scientist, researcher',
            '实验室': 'laboratory, research lab',
            '仪器': 'instrument, device',
            '观测': 'observation, telescope',
            '研究': 'research, study',
            '数据': 'data, statistics',
            '屏幕': 'screen, monitor, display',
            '图表': 'chart, graph',
            '地图': 'map',
            '地球': 'Earth, planet Earth',
            '太阳': 'sun, solar',
            '月亮': 'moon, lunar',
            '火星': 'Mars',
            '木星': 'Jupiter',
            '土星': 'Saturn',
            '城市': 'city, urban, cityscape',
            '乡村': 'countryside, rural',
            '山脉': 'mountain, mountain range',
            '海洋': 'ocean, sea',
            '河流': 'river',
            '森林': 'forest, woods',
            '云': 'cloud',
            '天空': 'sky',
            '建筑': 'building, architecture',
            '房间': 'room, interior',
            '办公室': 'office',
            '教室': 'classroom',
            '医院': 'hospital',
            '餐厅': 'restaurant',
            '商店': 'store, shop',
            '街道': 'street, road',
            '车辆': 'vehicle, car',
            '飞机': 'aircraft, plane',
            '船': 'ship, boat',
            '人': 'person, people',
            '男人': 'man',
            '女人': 'woman',
            '孩子': 'child',
            '科学家': 'scientist',
            '医生': 'doctor',
            '老师': 'teacher',
            '学生': 'student',
            '工人': 'worker',
            '农民': 'farmer',
            '商人': 'businessman',
            '官员': 'official',
            '领袖': 'leader',
            '动物': 'animal',
            '鸟': 'bird',
            '鱼': 'fish',
            '狗': 'dog',
            '猫': 'cat',
            '马': 'horse',
            '花': 'flower',
            '树': 'tree',
            '草': 'grass',
            '石头': 'rock, stone',
            '水': 'water',
            '火': 'fire',
            '雨': 'rain',
            '雪': 'snow',
            '风': 'wind',
            '雷': 'thunder',
            '闪电': 'lightning',
            '山': 'mountain, hill',
            '谷': 'valley',
            '岛': 'island',
            '湖': 'lake',
            '海': 'sea, ocean',
        })
        
        for chinese, english in keyword_mapping.items():
            if chinese in dubbing:
                for eng in english.split(', '):
                    if eng.strip() not in visual_keywords:
                        visual_keywords.append(eng.strip())
        
        if visual_keywords:
            return ', '.join(visual_keywords[:5])
        
        return ""
    
    def _translate_visual_concept(self, chinese_concept):
        """将中文视觉概念转化为英文描述"""
        # 常见视觉元素映射
        translations = {
            '战场': 'battlefield scene, war zone',
            '军事分析师': 'military analyst, strategic advisor',
            '新闻主持人': 'news anchor, presenter',
            '废墟': 'ruins, destroyed buildings',
            '城市': 'cityscape, urban environment',
            '建筑': 'architecture, buildings',
            '摧毁': 'destroyed, devastated',
            '破败': 'dilapidated, ruined',
            '抵抗组织': 'resistance fighters',
            '士兵': 'soldiers, troops',
            '装备': 'military equipment',
            '武器': 'weapons, armaments',
            '无人机': 'drone, UAV',
            '导弹': 'missile, rocket',
            '天空': 'sky, aerial view',
            '记者': 'journalist, reporter',
            '采访': 'interview scene',
            '海军': 'naval forces, warships',
            '空军': 'air force, aircraft',
            '舰艇': 'warships, naval vessels',
            '飞机': 'aircraft, military planes',
            '基地': 'military base',
            '港口': 'harbor, port',
            'IRGC': 'Islamic Revolutionary Guard Corps',
            '革命卫队': 'Revolutionary Guard troops',
            '精锐': 'elite forces',
            '螃蟹': 'crab, symbolic imagery',
            '天平': 'balance scale, weighing scale',
            '指挥中心': 'command center',
            '屏幕': 'screens, monitors',
            '地图': 'maps, tactical charts',
            # 黑洞/宇宙相关
            '黑洞': 'black hole, event horizon, cosmic phenomenon',
            '宇宙': 'universe, cosmos, deep space',
            '太空': 'outer space, celestial',
            '星球': 'planet, celestial body',
            '星空': 'starry sky, night sky',
            '银河': 'milky way, galaxy',
            '星体': 'celestial body, stellar object',
            '天体': 'heavenly body, celestial object',
            '行星': 'planet, orbiting body',
            '恒星': 'star, sun',
            '星系': 'galaxy, star system',
            '引力': 'gravity, gravitational force',
            '明亮吸积盘': 'bright accretion disk, glowing ring',
            '天文照片': 'astronomical image, space photograph',
            '科学研究': 'scientific research, laboratory',
            '吸积盘': 'accretion disk, glowing disk',
        }
        
        result = []
        for cn, en in translations.items():
            if cn in chinese_concept:
                result.append(en)
        
        if result:
            return ", ".join(result)
        else:
            # 如果没有匹配，返回空字符串而不是默认描述
            return ""
    
    def _get_scene_keywords_by_content(self, content_type, dubbing):
        """根据配音内容智能获取场景关键词 - 无需调用大模型"""
        if not dubbing or len(dubbing.strip()) < 2:
            return ""

        # 【整改新增】专业元素映射表 - 根据具体内容生成精确的提示词
        professional_element_map = {
            # 黑洞/宇宙主题专业元素
            "黑洞": {
                "core": ["black hole", "event horizon", "singularity"],
                "effects": ["gravitational lensing", "accretion disk", "relativistic jets"],
                "weight": 1.8
            },
            "克尔黑洞": {
                "core": ["rotating Kerr black hole", "spinning black hole", "ergosphere"],
                "effects": ["accretion disk", "relativistic beaming", "doppler shift"],
                "weight": 2.0
            },
            "史瓦西": {
                "core": ["Schwarzschild black hole", "non-rotating black hole"],
                "effects": ["event horizon", "photon sphere", "schwarzschild radius"],
                "weight": 2.0
            },
            "吸积盘": {
                "core": ["accretion disk", "glowing disk", "circumstellar disk"],
                "effects": ["hot plasma", "relativistic beaming", "doppler shift", "orange-red emission"],
                "weight": 1.9
            },
            "人马座": {
                "core": ["Sagittarius A*", "supermassive black hole", "galactic center"],
                "effects": ["star cluster", "dense star field", "Milky Way core", "infrared emission"],
                "weight": 2.0
            },
            "银河系": {
                "core": ["Milky Way galaxy", "galactic spiral arm", "galactic disk"],
                "effects": ["star field", "nebula", "cosmic dust", "spiral structure"],
                "weight": 1.6
            },
            "恒星": {
                "core": ["star", "dying star", "stellar surface"],
                "effects": ["solar flare", "coronal mass ejection", "stellar wind", "nuclear fusion"],
                "weight": 1.5
            },
            "星云": {
                "core": ["nebula", "cosmic cloud", "emission nebula"],
                "effects": ["ionized gas", "star formation", "cosmic dust", "colorful emission"],
                "weight": 1.5
            },
            "宇宙": {
                "core": ["deep space", "cosmos", "interstellar space"],
                "effects": ["star field", "cosmic background", "dark matter visualization"],
                "weight": 1.3
            },
            "宇宙深处": {
                "core": ["deep space", "outer space", "cosmic void"],
                "effects": ["distant galaxies", "cosmic background radiation", "darkness"],
                "weight": 1.4
            }
        }

        # 检查配音内容是否匹配专业元素
        matched_elements = []
        for keyword, element_info in professional_element_map.items():
            if keyword in dubbing:
                # 添加核心元素带权重
                for elem in element_info["core"]:
                    weight = element_info["weight"]
                    matched_elements.append(f"{elem}({weight})")
                # 添加效果元素
                for elem in element_info["effects"][:2]:
                    matched_elements.append(elem)

        # 如果匹配到专业元素，返回它们
        if matched_elements:
            return ", ".join(matched_elements)

        # 脚本优化的场景关键词映射（无需调用大模型）
        scene_keywords_map = {
            '战争': 'war zone, battlefield, military conflict, ruins',
            '军事': 'military base, command center, tactical operation, soldier',
            '新闻': 'news studio, broadcast room, journalist, breaking news',
            '科技': 'technology lab, research facility, innovation, digital',
            '科学': 'laboratory, scientific research, experiment, data analysis',
            '历史': 'historical site, ancient civilization, heritage, vintage',
            '自然': 'nature landscape, wilderness, ecosystem, wildlife',
            '经济': 'financial district, stock market, business center, economy',
            '政治': 'government building, political summit, diplomatic, capital',
            '教育': 'classroom, university, education, learning, students',
            '健康': 'hospital, medical center, healthcare, wellness',
            '旅游': 'tourist destination, scenic spot, adventure, journey',
            '娱乐': 'entertainment venue, performance, show business, cinema',
            '体育': 'stadium, sports arena, athletic competition, player',
            '环境': 'environmental scene, pollution, conservation, nature',
            '社会': 'urban environment, city life, society, community',
            '文化': 'cultural heritage, museum, art gallery, tradition',
            '国际': 'international affairs, global event, diplomatic scene',
        }

        # 从配音文本中匹配场景关键词
        for key, keywords in scene_keywords_map.items():
            if key in dubbing:
                return keywords

        # 根据内容类型返回默认场景关键词
        if content_type:
            content_type_keywords = {
                'space': 'space station, astronaut, cosmic view, orbital',
                'science': 'laboratory, research, experiment, scientific data',
                'nature': 'nature landscape, wilderness, outdoor scene',
                'history': 'historical site, vintage scene, period setting',
                'technology': 'tech lab, innovation, digital interface, future',
                'art': 'art studio, creative space, gallery, artistic',
                'education': 'classroom, lecture hall, educational setting',
                'business': 'office, corporate setting, business environment',
                'health': 'hospital, medical facility, healthcare setting',
                'travel': 'travel destination, scenic location, adventure',
            }
            if content_type in content_type_keywords:
                return content_type_keywords[content_type]

        # 默认返回
        return "realistic scene, documentary style, photorealistic"

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
        """
        if not dubbing:
            return ""
        
        dubbing_clean = dubbing.strip()
        entities = []
        
        # 国家/地区实体
        country_mapping = {
            '伊朗': 'Iran, Iranian', '美国': 'USA, American', '中国': 'China, Chinese',
            '俄罗斯': 'Russia, Russian', '以色列': 'Israel, Israeli', '日本': 'Japan, Japanese',
            '英国': 'UK, British', '法国': 'France, French', '德国': 'Germany, German',
            '朝鲜': 'North Korea, Korean', '韩国': 'South Korea, Korean',
            '乌克兰': 'Ukraine, Ukrainian', '欧洲': 'Europe, European',
            '中东': 'Middle East', '亚洲': 'Asia, Asian',
        }
        
        # 军事/安全机构实体
        military_mapping = {
            '革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
            '伊朗革命卫队': 'Islamic Revolutionary Guard Corps, IRGC, Iranian military',
            '美军': 'US military, American forces', '美军方': 'US military, Pentagon',
            '军队': 'military, armed forces, troops', '部队': 'troops, military unit',
            '海军': 'navy, naval forces', '空军': 'air force, aviation',
            '陆军': 'army, ground forces', '导弹': 'missile, rocket',
            '无人机': 'drone, UAV', '战斗机': 'fighter jet, aircraft',
            '航母': 'aircraft carrier', '军舰': 'warship, naval vessel',
            '武器': 'weapons, armaments', '军事': 'military, armed',
            '国防部': 'Ministry of Defense, Pentagon', '五角大楼': 'Pentagon, US Defense Department',
        }
        
        # 政治/组织实体
        political_mapping = {
            '政府': 'government, officials', '总统': 'president, head of state',
            '总理': 'prime minister', '首相': 'prime minister',
            '外交部': 'foreign ministry, diplomatic', '联合国': 'United Nations, UN',
            '安理会': 'UN Security Council', '北约': 'NATO, NATO alliance',
            '欧盟': 'European Union, EU', '国会': 'congress, parliament',
            '议会': 'parliament, legislative', '政党': 'political party',
            '官员': 'officials, authorities', '发言人': 'spokesperson, official spokesperson',
        }
        
        # 事件/行动实体
        event_mapping = {
            '战争': 'war, warfare, conflict', '冲突': 'conflict, clash',
            '战斗': 'battle, combat, fighting', '袭击': 'attack, strike, assault',
            '爆炸': 'explosion, blast', '发射': 'launch, launch',
            '试射': 'test, missile test', '军演': 'military exercise, drill',
            '谈判': 'negotiation, talks', '会议': 'meeting, conference',
            '声明': 'statement, announcement', '宣布': 'announcement, declare',
            '签署': 'signing, agreement', '协议': 'agreement, deal, pact',
            '制裁': 'sanctions, embargo', '援助': 'aid, assistance',
        }
        
        # 地点/场景实体
        location_mapping = {
            '基地': 'base, military base', '机场': 'airport, air base',
            '港口': 'port, harbor, naval base', '城市': 'city, urban',
            '农村': 'rural, countryside', '山区': 'mountain, mountainous',
            '沙漠': 'desert', '海边': 'coastal, seaside',
            '海峡': 'strait, waterway', '油田': 'oil field, oil facility',
            '核设施': 'nuclear facility', '工厂': 'factory, facility',
            '大使馆': 'embassy', '领事馆': 'consulate',
        }
        
        # 新闻/媒体相关
        media_mapping = {
            '新闻': 'news, news report, breaking news', '记者': 'journalist, reporter',
            '主持人': 'anchor, presenter', '直播': 'live broadcast, livestream',
            '报道': 'report, coverage', '采访': 'interview',
            '发布会': 'press conference', '声明': 'official statement',
        }
        
        # 通用开场/过渡词（需要结合主题）
        generic_keywords = {
            '今天': 'today, current events, breaking news',
            '消息': 'news, information, report',
            '全球': 'global, worldwide, international',
            '牵动': 'impact, concern, attention',
            '最新': 'latest, recent, breaking',
            '关注': 'attention, focus, interest',
            '热点': 'hot topic, trending, viral',
            '重大': 'major, significant, important',
            '紧急': 'urgent, emergency, breaking',
            '刚刚': 'just happened, breaking, latest',
            '最新消息': 'breaking news, latest update, recent development',
            '据报道': 'according to reports, sources say',
            '业内人士': 'industry sources, experts, insiders',
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
                '写实': 'realistic, documentary, authentic, natural, lifelike',
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
            return "realistic scene, documentary style, photorealistic"
        
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
        return "realistic scene, documentary style, photorealistic environment"
    
    def _get_lighting_by_mood(self, dubbing):
        """根据情感基调获取光线描述（带权重）"""
        if any(w in dubbing for w in ["紧张", "危机", "冲突", "严峻", "沉重"]):
            return "dramatic side lighting(1.3), dark shadows(1.2), moody atmosphere(1.2), desaturated colors(1.0)"
        elif any(w in dubbing for w in ["绝望", "失败", "崩溃", "毁灭"]):
            return "harsh lighting(1.3), high contrast(1.2), bleak atmosphere(1.2), gray tones(1.0)"
        elif any(w in dubbing for w in ["希望", "胜利", "和平", "成功"]):
            return "warm golden hour lighting(1.3), soft natural light(1.2), uplifting atmosphere(1.2)"
        else:
            return "neutral lighting(1.0), balanced exposure(1.2), documentary style(1.3)"
    
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
        
        is_sd_prompt = prompt_type == "SD提示词"
        
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
            unique_keywords = ['realistic scene', 'documentary style']
        
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
            keywords = ['写实场景', '纪录片风格']
        
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
        import time
        import re
        
        user_model = self.ollama_model_var.get()
        if user_model == "脚本自带":
            return prompt
        
        prompt_type = self.prompt_type_var.get() if hasattr(self, 'prompt_type_var') else "SD提示词"
        
        cache_key = f"{sentence}_{prompt_type}"
        cached_prompt = self.cache_get('prompts', cache_key)
        if cached_prompt:
            return cached_prompt
        
        if not OLLAMA_AVAILABLE:
            return prompt
        
        model_priority_list = [
            ("gemma3:4b", 4, "通用模型"),
            ("gemma3:1b", 1, "轻量级模型"),
            ("qwen2.5:0.5b", 0.5, "超轻量级模型"),
            ("qwen2.5:1.5b", 1.5, "轻量级模型"),
            ("phi3:mini", 2, "微软轻量级模型"),
            ("qwen3:4b", 4, "通用模型"),
            ("qwen2.5:3b", 3, "阿里轻量级模型"),
            ("llama3.2:3b", 3, "Meta轻量级模型"),
            ("llama3.2:1b", 1, "Meta超轻量级模型"),
            ("llama3", 8, "Meta通用模型"),
            ("mistral", 7, "Mistral通用模型"),
            ("deepseek-r1:8b", 8, "DeepSeek推理模型"),
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
            except:
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
            is_sd = prompt_type == "SD提示词"
            
            # 构建清晰简洁的指令
            if is_sd:
                system_prompt = """你是专业的SD提示词工程师。

任务：将中文配音文本转换为简洁的英文SD提示词。

严格规则（必须遵守）：
1. 只输出英文tag，用英文逗号分隔，禁止任何中文
2. 必须保留核心主体和动作
3. 必须添加质量词：masterpiece, best quality
4. 禁止添加解释、禁止添加引号、禁止换行
5. 总长度控制在20-40个英文单词以内
6. 直接输出提示词，不要有任何前缀文字"""

                user_prompt = f"配音文本：{sentence}\n\n直接输出英文提示词，严格遵守以上规则。"
                
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
            
            optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "平衡模式"
            
            if optimization_method == "极速模式":
                task_complexity = "low"
            elif optimization_method == "质量优先":
                task_complexity = "high"
            else:
                task_complexity = "medium"
            
            config = llm_optimizer.get_optimal_config(task_complexity=task_complexity)
            
            if not hasattr(self, '_ollama_config_logged') or not self._ollama_config_logged:
                self.log(f"🎯 优化模式: {optimization_method} | {prompt_type}")
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
                        ],
                        options=config.get_options(num_predict=500)
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
        """从大模型分析结果中提取主题信息"""
        theme_info = {
            'core_theme': '',
            'visual_tone': '',
            'theme_elements': []
        }

        if not analysis_result:
            return theme_info

        try:
            # 清理analysis_result中的**标记，避免解析问题
            import re
            cleaned_result = analysis_result.replace('**', '')

            # 提取核心主题（支持中英文，包括**格式）
            if '核心主题：' in cleaned_result:
                core_match = cleaned_result.split('核心主题：')[1].split('\n')[0].strip()
            elif '中心思想：' in cleaned_result:
                core_match = cleaned_result.split('中心思想：')[1].split('\n')[0].strip()
            elif 'Core Theme:' in cleaned_result:
                core_match = cleaned_result.split('Core Theme:')[1].split('\n')[0].strip()
            elif 'core theme' in cleaned_result.lower():
                match = re.search(r'(?:core theme|主题)[:\s]+([^\n]+)', cleaned_result, re.IGNORECASE)
                if match:
                    core_match = match.group(1).strip()
                else:
                    core_match = ""
            else:
                core_match = ""
            
            # 简化核心主题：提取关键词，去除描述性内容
            if core_match:
                core_match = self._simplify_theme(core_match)
                theme_info['core_theme'] = core_match

            # 提取视觉基调（支持中英文，包括**格式）
            if '视觉基调：' in cleaned_result:
                tone_match = cleaned_result.split('视觉基调：')[1].split('\n')[0].strip()
                theme_info['visual_tone'] = tone_match
            elif '视觉主题：' in cleaned_result:
                tone_match = cleaned_result.split('视觉主题：')[1].split('\n')[0].strip()
                theme_info['visual_tone'] = tone_match
            elif 'Overall Tone:' in cleaned_result:
                tone_match = cleaned_result.split('Overall Tone:')[1].split('\n')[0].strip()
                theme_info['visual_tone'] = tone_match
            elif 'visual tone' in cleaned_result.lower():
                match = re.search(r'(?:visual tone|色调)[:\s]+([^\n]+)', cleaned_result, re.IGNORECASE)
                if match:
                    theme_info['visual_tone'] = match.group(1).strip()

            # 提取主题元素（支持中英文，包括**格式）
            if '主题元素：' in cleaned_result:
                elements_text = cleaned_result.split('主题元素：')[1].split('\n')[0].strip()
                elements = re.split(r'[，、,]', elements_text)
                theme_info['theme_elements'] = [e.strip() for e in elements if e.strip()]
            elif 'Theme Elements:' in cleaned_result:
                elements_text = cleaned_result.split('Theme Elements:')[1].split('\n')[0].strip()
                elements = re.split(r'[,;]', elements_text)
                theme_info['theme_elements'] = [e.strip() for e in elements if e.strip()]

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
            except:
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
                    
                    # 更新UI
                    if hasattr(self, 'cpu_label'):
                        self.cpu_label.config(text=f"{cpu_usage:.1f}%")
                    if hasattr(self, 'memory_label'):
                        self.memory_label.config(text=f"{memory_usage:.1f}%")
                    if hasattr(self, 'gpu_label'):
                        self.gpu_label.config(text=f"{gpu_memory_percent:.1f}%")
                    if hasattr(self, 'memory_detail_label'):
                        self.memory_detail_label.config(text=f"{memory_used} MB / {memory_total} MB")
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
        # 启动缓存清理线程
        threading.Thread(target=self.cache_cleanup, daemon=True).start()
        self.log("✅ 缓存系统初始化完成")
    
    def cache_cleanup(self):
        """定期清理过期缓存"""
        while True:
            try:
                import time
                time.sleep(self.cache_config['cleanup_interval'])
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
            import time
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
        import time
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
        """执行任务"""
        task = self.thread_pool['tasks'].get(task_id)
        if not task:
            with self.task_lock:
                self.task_running = False
                self.current_task = None
            self.process_task_queue()
            return
        
        task['status'] = 'running'
        self.thread_pool_stats['active_threads'] += 1
        
        try:
            # 使用资源锁保护共享资源
            with self.resource_lock:
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
    
    def shutdown_thread_pool(self):
        """关闭线程池"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
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
        """关闭窗口时的处理 - 增强版，确保内存完全释放"""
        try:
            self.log("🔄 正在关闭程序，清理资源...")
            
            # 停止性能监控线程
            if hasattr(self, 'perf_monitor_running'):
                self.perf_monitor_running = False
                self.log("🔄 性能监控已停止")
            
            # 取消待处理的resize定时器
            if hasattr(self, 'resize_timer') and self.resize_timer:
                self.root.after_cancel(self.resize_timer)
                self.resize_timer = None
            
            # 保存配置
            self.save_config()
            
            # 关闭线程池
            self.shutdown_thread_pool()
            
            # 停止所有活动任务
            with self.task_lock:
                self.task_running = False
                self.task_paused = False
                self.task_queue.clear()
                self.current_task = None
            
            # 释放Whisper模型内存
            if self.whisper_model is not None:
                self.log("🔄 释放Whisper模型内存...")
                try:
                    import torch
                    del self.whisper_model
                    self.whisper_model = None
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception as e:
                    print(f"释放Whisper模型失败: {e}")
            
            # 清理缓存数据
            if hasattr(self, 'shots_data'):
                self.shots_data = []
            if hasattr(self, 'cache_system'):
                self.cache_system = {}
            
            # 强制垃圾回收
            import gc
            gc.collect()
            
            # 再次清理CUDA缓存
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    self.log("✅ GPU内存已释放")
            except:
                pass
            
            self.log("✅ 资源清理完成")
            
            # 销毁窗口
            self.root.destroy()
        except Exception as e:
            print(f"关闭窗口时出错: {e}")
            # 即使出错也要尝试销毁窗口
            try:
                self.root.destroy()
            except:
                pass
    
    def system_check(self):
        """系统检查"""
        self.log("正在进行系统检查...")
        # 检查依赖项
        self.check_dependencies()
        # 检查SD API连接
        # self.check_sd_api_connection()
        self.log("✅ 系统检查完成")
    
    def generate_shots(self):
        """生成分镜 - 修复异常处理和状态管理"""
        # 确保在函数开始时就导入必要的模块
        import os
        import whisper
        import numpy as np
        import hashlib
        import gc  # 垃圾回收
        
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
            
            # 每次运行都清除缓存，确保使用最新逻辑
            self.cache_clear()
            self.log("🗑️ 已清除历史缓存")
            
            # 检查是否需要关闭Ollama以释放GPU资源给Whisper使用
            optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
            # 只有不使用大模型时才关闭Ollama
            if optimization_method not in ["本地大模型"]:
                self.log("🧹 检查GPU资源状态...")
                try:
                    import subprocess
                    result = subprocess.run(['tasklist'], capture_output=True, text=True)
                    if 'ollama.exe' in result.stdout:
                        self.log("⚠️ 检测到Ollama进程占用GPU，正在关闭以释放资源...")
                        subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True)
                        import time
                        time.sleep(2)
                        self.log("✅ Ollama已关闭，GPU资源已释放")
                except Exception as e:
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
            
            audio_file_hash = hashlib.md5(self.audio_path.encode()).hexdigest()[:8]
            cache_key_string = f"{audio_file_hash}_{full_text}_{content_type}_{prompt_type}"
            analysis_key = f"analysis_{hashlib.md5(cache_key_string.encode()).hexdigest()}"

            # 智能计算分镜数量（整改后 - 不做强制限制）
            # 让大模型根据语义断句自由创建分镜
            def calculate_optimal_shot_count():
                """根据语音片段计算最佳分镜数量 - 整改后版本

                关键改进：
                1. 不做强制数量限制
                2. 由大模型根据语义完整性自主判断
                3. 返回 None 表示不限制，由大模型自由决定
                """
                # 不再计算推荐数量，完全让大模型决定
                return None, 0, 0
            
            optimal_shot_count, segment_count, total_duration = calculate_optimal_shot_count()
            self.log(f"   音频已识别，等待大模型分析...")
            
            # 【关键修改】不再合并语音片段，直接使用原始segments
            # 这样可以确保：
            # 1. description 使用原始语音片段的完整句子
            # 2. 时间戳精确对应原始语音片段
            
            # 直接从原始segments创建分镜列表（每个片段一个分镜）
            original_shot_tasks = []
            for seg in segments:
                text = seg.get('text', '').strip()
                start_time = seg.get('start', 0)
                end_time = seg.get('end', 0)
                if text and end_time > start_time:
                    content_type = self.analyze_content_type(text)
                    original_shot_tasks.append({
                        'text': text,
                        'start': start_time,
                        'end': end_time,
                        'content_type': content_type
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
                # 检查用户是否选择了大模型优化方式
                optimization_method = self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else "脚本自带"
                
                # 【修复】动态检测Ollama服务是否可用，而不是仅依赖启动时的状态
                if optimization_method == "本地大模型" and len(full_text) > 100:
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
                                    import time
                                    time.sleep(3)  # 等待服务启动
                                    # 再次尝试连接
                                    try:
                                        response = requests.get("http://localhost:11434/api/tags", timeout=5)
                                        if response.status_code == 200:
                                            OLLAMA_AVAILABLE = True
                                            ollama_connected = True
                                            self.log("✅ Ollama服务已启动并连接成功")
                                    except:
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
                            if user_model == "脚本自带":
                                user_model = "gemma3:4b"
                            
                            # 定义模型优先级列表（按稳定性和速度排序）
                            model_priority_list = [
                                ("gemma3:4b", 4, "通用模型，推荐首选"),
                                ("gemma3:1b", 1, "轻量级模型，速度最快"),
                                ("qwen2.5:0.5b", 0.5, "超轻量级模型"),
                                ("qwen2.5:1.5b", 1.5, "轻量级模型"),
                                ("phi3:mini", 2, "微软轻量级模型"),
                                ("qwen3:4b", 4, "通用模型"),
                                ("qwen2.5:3b", 3, "阿里轻量级模型"),
                                ("llama3.2:3b", 3, "Meta轻量级模型"),
                                ("llama3.2:1b", 1, "Meta超轻量级模型"),
                                ("llama3", 8, "Meta通用模型"),
                                ("llama3.1", 8, "Meta通用模型"),
                                ("mistral", 7, "Mistral通用模型"),
                                ("deepseek-r1:8b", 8, "DeepSeek推理模型"),
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
                            import time
                            
                            def call_ollama_with_model(model_name):
                                """使用指定模型调用Ollama - 轻量级主题提取"""
                                global ollama_lock
                                try:
                                    custom_theme = self.custom_theme_var.get() if hasattr(self, 'custom_theme_var') else ""
                                    custom_visual_tone = self.custom_visual_tone_var.get() if hasattr(self, 'custom_visual_tone_var') else ""
                                    
                                    if custom_theme or custom_visual_tone:
                                        system_parts = [
                                            "你是专业的视频内容分析专家。请从以下语音转录文本中提取关键信息，用于后续分镜生成。",
                                            "",
                                            "【任务】",
                                            "只提取以下信息，不需要生成分镜脚本：",
                                            "1. 核心主题（一句话概括文章主要内容）",
                                            "2. 视觉基调（适合描述画面的关键词）",
                                            "3. 主题元素（3-5个与主题相关的视觉元素关键词）",
                                            "",
                                            "【用户指定的核心主题】: " + custom_theme if custom_theme else "无",
                                            "【用户指定的视觉基调】: " + custom_visual_tone if custom_visual_tone else "无",
                                            "",
                                            "请用以下格式输出：",
                                            "【核心主题】：xxx",
                                            "【视觉基调】：xxx",
                                            "【主题元素】：xxx, xxx, xxx"
                                        ]
                                        system_content = "\n".join(system_parts)
                                    else:
                                        template = PromptTemplates.get_template("theme_extraction", text=full_text)
                                        system_content = template["system"]
                                    
                                    response = ollama.chat(
                                        model=model_name,
                                        messages=[
                                            {"role": "system", "content": system_content},
                                            {"role": "user", "content": f"语音转录文本：\n{full_text}"}
                                        ],
                                        options=self.current_llm_config.get_options(
                                            num_predict=1024,
                                            num_ctx=4096
                                        ) if hasattr(self, 'current_llm_config') else {"temperature": 0.3, "top_p": 0.9, "num_predict": 1024, "num_ctx": 4096}
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
                                # 关闭Ollama释放GPU资源
                                try:
                                    import subprocess
                                    subprocess.run(['taskkill', '/F', '/IM', 'ollama.exe'], capture_output=True)
                                    import time
                                    time.sleep(1)
                                    self.log("🧹 Ollama已关闭，GPU资源已释放")
                                except:
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
                            
                            # 不生成分镜列表，跳到步骤3直接使用原始语音片段
                            self.log("✅ 主题提取完成，将直接使用原始语音片段创建分镜")
                        
                        except Exception as e:
                            self.log(f"   ⚠️ 大模型分析过程出错: {str(e)[:100]}")
                            self.log("   将使用原始语音片段创建分镜")
                            theme_info = {'core_theme': '', 'visual_tone': '', 'theme_elements': []}
                            user_custom_theme = ""
                            user_custom_tone = ""
                
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
                text = task['text']
                content_type = task['content_type']
                            
                # 直接使用原始片段的时间戳
                start_time = task['start']
                end_time = task['end']
                
                shot_tasks.append((
                    len(shot_tasks),
                    start_time,
                    end_time,
                    text,
                    content_type
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
            start_time = time.time()
            
            # 获取主题信息（优先使用用户自定义的）
            core_theme = user_custom_theme if user_custom_theme else theme_info.get('core_theme', '')
            visual_tone = user_custom_tone if user_custom_tone else theme_info.get('visual_tone', '')
            theme_elements = theme_info.get('theme_elements', [])
            
            def create_shot_task(task_data):
                idx, start_time, end_time, text, content_type = task_data
                shot = self.create_new_shot(
                    idx, start_time, end_time, text, content_type,
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
                                elapsed = time.time() - start_time
                                speed = completed_count / elapsed if elapsed > 0 else 0
                                self.log(f"   📊 正在创建分镜: {completed_count}/{len(shot_tasks)} (速度: {speed:.1f}个/秒)")
                                progress = 50 + int(completed_count / len(shot_tasks) * 30) if len(shot_tasks) > 0 else 50
                                self.update_task_progress(f"正在创建分镜: {completed_count}/{len(shot_tasks)}", progress)
                    except Exception as e:
                        self.log(f"   ⚠️ 创建分镜失败: {str(e)}")
            
            elapsed_time = time.time() - start_time
            
            # 按索引排序
            shots = [shots_dict[i] for i in sorted(shots_dict.keys())]
            self.log(f"✅ 成功创建 {len(shots)} 个分镜（{thread_count}线程并行，耗时 {elapsed_time:.1f}秒，速度 {len(shots)/elapsed_time:.1f}个/秒）")

            # 验证分镜主题一致性（如果大模型分析成功）
            if theme_info.get('core_theme'):
                is_consistent, consistency_msg = self.validate_theme_consistency(shots, theme_info)
                if is_consistent:
                    self.log(f"✅ {consistency_msg}")
                else:
                    self.log(f"⚠️ {consistency_msg}")
                    self.log(f"💡 建议: 检查分镜提示词是否围绕主题'{theme_info['core_theme']}'展开")
            
            # 检查分镜是否为空
            if not shots:
                self.log("❌ 未能生成分镜，请检查音频文件是否正确")
                self.update_task_progress("就绪")
                messagebox.showwarning("警告", "未能生成分镜，请检查音频文件是否正确")
                return
            
            # 步骤4: 保存和完成
            self.log("\n📍 步骤 4/4: 保存分镜数据")
            
            # 智能调整分镜时长
            self.update_task_progress("正在调整分镜时长...", 90)
            # 修复：使用音频实际时长作为总时长，确保与音频文件一致
            audio_total_duration = segments[-1].get("end", 0) if segments else 0
            shots = self.adjust_shot_durations(shots, audio_total_duration)
            
            # 修复：验证时间戳连续性，确保音画同步
            self.log("🔍 验证时间戳连续性...")
            for i, shot in enumerate(shots):
                expected_start = 0 if i == 0 else shots[i-1]['end']
                if abs(shot['start'] - expected_start) > 0.001:
                    self.log(f"⚠️ 分镜{i+1}时间戳不连续: 期望{expected_start:.3f}s, 实际{shot['start']:.3f}s")
                    # 自动修正
                    shot['start'] = expected_start
                    shot['duration'] = shot['end'] - shot['start']
            
            # 最终验证总分镜时长
            final_total = sum(s['duration'] for s in shots)
            if abs(final_total - audio_total_duration) > 0.01:
                self.log(f"⚠️ 总分镜时长({final_total:.3f}s)与音频时长({audio_total_duration:.3f}s)不匹配")
                # 修复：如果不匹配，重新调整以匹配音频时长
                self.log("🔄 重新调整分镜时长以匹配音频...")
                shots = self.adjust_shot_durations(shots, audio_total_duration)
                final_total = sum(s['duration'] for s in shots)
                self.log(f"✅ 调整后总分镜时长: {final_total:.3f}s")
            else:
                self.log(f"✅ 时间戳验证通过，总分镜时长: {final_total:.3f}s")
            
            self.log(f"✅ 分镜时长调整完成")
            
            # 保存分镜数据
            self.update_task_progress("正在保存分镜数据...", 95)
            # 修复：统一数据存储，只使用shots_data，避免数据冗余
            self.shots_data = shots
            self.state_manager['shots']['generated'] = True
            self.state_manager['shots']['count'] = len(shots)
            # 不再在state_manager中存储完整数据，只存储元数据
            self.state_manager['shots']['data'] = None  # 清除旧数据
            
            # 保存分镜数据到文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            with open(shots_file, 'w', encoding='utf-8') as f:
                json.dump(shots, f, ensure_ascii=False, indent=2)
            
            self.log(f"✅ 分镜生成完成！共 {len(shots)} 个分镜")
            self.log(f"📁 数据已保存到: {shots_file}")
            self.log("=" * 50)
            
            # 显示分镜内容到脚本区域
            if hasattr(self, 'txt_script'):
                def update_script():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本\n\n")
                        for i, shot in enumerate(shots):
                            self.txt_script.insert(tk.END, f"## 分镜 {i+1}\n")
                            self.txt_script.insert(tk.END, f"时间: {shot['start']:.2f}s - {shot['end']:.2f}s (时长: {shot['duration']:.2f}s)\n")
                            self.txt_script.insert(tk.END, f"内容: {shot['description']}\n")
                            self.txt_script.insert(tk.END, f"提示词: {shot['prompt_en'][:100]}...\n\n")
                        # 显示弹窗提示
                        messagebox.showinfo("成功", f"分镜脚本生成完成，共生成 {len(shots)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 更新脚本区域失败: {e}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_script)
            
            # 清理内存
            self.log("🔄 清理内存...")
            import gc
            gc.collect()
            
            # 更新进度为完成
            self.update_task_progress("分镜生成完成", 100)
            
        except Exception as e:
            self.log(f"❌ 分镜生成失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 修复：完善资源清理机制
            try:
                # 如果模型是在本次调用中加载的，释放模型内存
                if whisper_model_loaded and self.whisper_model is not None:
                    self.log("🔄 释放Whisper模型内存...")
                    import torch
                    del self.whisper_model
                    self.whisper_model = None
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    self.log("✅ Whisper模型内存已释放")
                
                # 强制垃圾回收
                import gc
                gc.collect()
                self.log("✅ 内存清理完成")
            except Exception as cleanup_error:
                self.log(f"⚠️ 资源清理时出错: {cleanup_error}")
    
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
            self.update_task_progress("正在检查SD API连接...", 10)
            
            # 检查SD API连接状态
            api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else "http://127.0.0.1:7860"
            try:
                response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=5)
                if response.status_code != 200:
                    self.log(f"❌ SD API 连接失败: 状态码 {response.status_code}")
                    self.log("❌ 系统拒绝生成图像，因为Stable Diffusion API不可用")
                    self.log("💡 解决方案建议: 请检查Stable Diffusion Web UI是否已启动，API地址是否正确")
                    self.update_task_progress("就绪")
                    return
            except Exception as e:
                self.log(f"❌ SD API 连接异常: {str(e)}")
                self.log("❌ 系统拒绝生成图像，因为Stable Diffusion API不可用")
                self.log("💡 解决方案建议: 1. 确保Stable Diffusion Web UI已启动 2. 检查API地址是否正确 3. 检查网络连接是否正常")
                self.update_task_progress("就绪")
                return
            
            # 确保图像目录存在
            self.update_task_progress("正在准备图像目录...", 20)
            if not os.path.exists(self.images_dir):
                os.makedirs(self.images_dir)
                self.log(f"✅ 创建图像目录: {self.images_dir}")
            
            # 获取用户选择的风格预设
            self.update_task_progress("正在准备风格预设...", 30)
            selected_styles = self.get_selected_styles()
            style_descriptions = []
            for style in selected_styles:
                style_desc = self.generate_style_description(style)
                if style_desc:
                    style_descriptions.append(style_desc)
            
            # 生成图像
            generated_count = 0
            self.log(f"📋 共有 {len(self.shots_data)} 个分镜需要生成图像")
            
            # 获取用户设置的像素尺寸（先定义变量）
            width = int(self.width_var.get()) if hasattr(self, 'width_var') else 1920
            height = int(self.height_var.get()) if hasattr(self, 'height_var') else 1080
            
            # 获取用户选择的模型
            selected_model = self.model_var.get() if hasattr(self, 'model_var') else "不选择"
            
            # 显示SD配置信息
            self.log(f"🖥️ Stable Diffusion 配置:")
            self.log(f"   API地址: {api_url}")
            self.log(f"   图像尺寸: {width}x{height}")
            if selected_model and selected_model != "不选择":
                self.log(f"   使用模型: {selected_model}")
            else:
                self.log(f"   使用模型: SD默认模型")
            if selected_styles:
                self.log(f"   风格预设: {', '.join(selected_styles)}")
            self.log(f"   生成参数: steps=20, cfg=7.0, sampler=DPM++ 2M")
            
            # 按分镜ID排序，确保顺序生成
            sorted_shots = sorted(self.shots_data, key=lambda x: x['id'])
            
            # 准备需要生成的图像任务
            tasks = []
            for shot in sorted_shots:
                shot_id = shot['id']
                prompt = shot['prompt_en']
                image_file = shot['image_file']
                image_path = os.path.join(self.images_dir, image_file)
                description = shot.get('description', 'No content')
                
                # 检查图像是否已经存在
                if os.path.exists(image_path):
                    self.log(f"⚠️ 图像已存在，跳过: {image_file}")
                    continue
                
                # 添加风格描述到提示词
                enhanced_prompt = prompt
                if style_descriptions:
                    style_text = ", ".join(style_descriptions)
                    enhanced_prompt = f"{prompt}, {style_text}"
                
                tasks.append((shot_id, enhanced_prompt, image_file, image_path, description))
            
            # 如果用户选择了模型，尝试切换SD模型
            if selected_model and selected_model != "不选择":
                self.log(f"🎨 正在切换绘图模型: {selected_model}")
                try:
                    # 模型名称映射（从显示名称到SD模型文件名）
                    model_mapping = {
                        "Stable Diffusion 1.5": "v1-5-pruned-emaonly",
                        "SDXL 1.0": "sd_xl_base_1.0",
                        "Flux Dev": "flux1-dev",
                        "Stable Diffusion 3": "sd3",
                        "DALL·E 3": "dall-e-3"
                    }
                    
                    # 获取SD模型名称（如果映射中不存在，使用原名称）
                    sd_model_name = model_mapping.get(selected_model, selected_model)
                    
                    # 先获取当前可用的模型列表
                    models_response = requests.get(f"{api_url}/sdapi/v1/sd-models", timeout=10)
                    if models_response.status_code == 200:
                        available_models = models_response.json()
                        model_titles = [m.get('title', '') for m in available_models]
                        model_names = [m.get('model_name', '') for m in available_models]
                        
                        # 查找匹配的模型
                        target_model = None
                        for model_info in available_models:
                            if sd_model_name.lower() in model_info.get('title', '').lower() or \
                               sd_model_name.lower() in model_info.get('model_name', '').lower():
                                target_model = model_info.get('title')
                                break
                        
                        if target_model:
                            # 切换模型
                            options_payload = {
                                "sd_model_checkpoint": target_model
                            }
                            switch_response = requests.post(
                                f"{api_url}/sdapi/v1/options", 
                                json=options_payload, 
                                timeout=30
                            )
                            if switch_response.status_code == 200:
                                self.log(f"✅ 已切换到模型: {selected_model} ({target_model})")
                            else:
                                self.log(f"⚠️ 模型切换失败: HTTP {switch_response.status_code}")
                        else:
                            self.log(f"⚠️ 未找到模型: {selected_model}，将使用当前模型")
                            self.log(f"   可用模型: {', '.join(model_titles[:5])}...")
                    else:
                        self.log(f"⚠️ 无法获取模型列表: HTTP {models_response.status_code}")
                        
                except Exception as e:
                    self.log(f"⚠️ 模型切换异常: {e}")
                    self.log(f"   将继续使用当前模型")
            
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
                
                self.log(f"📸 生成图像 {shot_id+1}/{len(self.shots_data)}: {image_file}")
                self.log(f"📝 分镜内容: {description[:50]}...")
                self.log(f"💡 提示词: {enhanced_prompt[:100]}...")
                
                # 尝试使用本地Stable Diffusion API生成图像，增加重试机制
                max_retries = 3
                retry_delay = 5
                
                for retry in range(max_retries):
                    try:
                        # 构建请求数据
                        # 使用用户设置的原始分辨率，不再强制限制
                        # 如果分辨率过大，记录警告但不强制修改
                        gen_width = width
                        gen_height = height
                        
                        # 检查分辨率是否过大，给出警告
                        if width > 1920 or height > 1080:
                            self.log(f"⚠️ 分辨率较大 ({width}x{height})，可能导致内存不足或生成缓慢")
                        
                        self.log(f"🖼️ 生图分辨率: {gen_width}x{gen_height}")
                        
                        payload = {
                            "prompt": enhanced_prompt,
                            "negative_prompt": "(worst quality, low quality:1.4), cartoon, anime, painting, illustration, ugly, deformed, blurry, disfigured, bad anatomy, extra limbs, watermark, text, signature, mutated hands",
                            "steps": 25,
                            "width": gen_width,
                            "height": gen_height,
                            "cfg_scale": 7.0,
                            "sampler_name": "DPM++ 2M",
                            "seed": -1,
                            "batch_size": 1
                        }
                        
                        # 发送请求，增加超时时间
                        response = requests.post(f"{api_url}/sdapi/v1/txt2img", json=payload, timeout=90)
                        
                        if response.status_code == 200:
                            # 处理响应
                            result = response.json()
                            if "images" in result and len(result["images"]) > 0:
                                # 解码Base64图像
                                import base64
                                image_data = base64.b64decode(result["images"][0])
                                image = Image.open(BytesIO(image_data))
                                
                                # 保存图像
                                image.save(image_path)
                                self.log(f"✅ 图像生成成功: {image_file}")
                                return True
                            else:
                                self.log(f"❌ 图像生成失败: 没有返回图像数据")
                        else:
                            self.log(f"❌ 图像生成失败: 状态码 {response.status_code}")
                            
                    except Exception as e:
                        self.log(f"⚠️ Stable Diffusion API调用失败 (尝试 {retry+1}/{max_retries}): {e}")
                        if retry < max_retries - 1:
                            self.log(f"⏳ 等待 {retry_delay} 秒后重试...")
                            import time
                            time.sleep(retry_delay)
                        else:
                            self.log("❌ 系统拒绝生成图像，因为Stable Diffusion API不可用")
                
                return False
            
            # 串行生成图像，避免API超时
            if tasks:
                self.log(f"⚡ 启动串行图像生成，共 {len(tasks)} 个任务")
                results = []
                for i, task in enumerate(tasks):
                    # 检查是否被暂停
                    if not self.pause_event.is_set():
                        self.log("⏸️ 任务已暂停，等待恢复...")
                        self.pause_event.wait()
                    
                    # 检查是否被取消
                    if not self.task_running:
                        self.log("❌ 任务已被取消")
                        break
                    
                    # 更新进度
                    progress = 40 + (i / len(tasks)) * 50
                    self.update_task_progress(f"正在生成图像 {i+1}/{len(tasks)}...", progress)
                    
                    shot_id, enhanced_prompt, image_file, image_path, description = task
                    self.log(f"🔄 处理任务 {i+1}/{len(tasks)}: {image_file}")
                    result = generate_single_image(task)
                    results.append(result)
                    if not result:
                        self.log(f"❌ 任务 {i+1} 失败: {image_file}")
                    # 生成一张图片后短暂休息
                    import time
                    time.sleep(0.3)
                generated_count = sum(results)
                failed_count = len(results) - generated_count
                self.log(f"📊 图像生成统计: 成功 {generated_count}, 失败 {failed_count}")
            else:
                self.log("⚠️ 没有需要生成的图像任务")
                generated_count = 0
            
            # 更新进度为完成
            self.update_task_progress("图像生成完成", 100)
            self.log(f"✅ 图像生成完成，共生成 {generated_count} 个图像")
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
        skip_clear: 是否跳过清除旧的视频文件（直接生成视频时设为True）
        use_original_resolution: 是否使用原始图片分辨率（直接生成视频时设为True）
        skip_image_check: 是否跳过图片存在性检查（直接生成视频时设为True）
        """
        self.log("🎞️ 开始生成视频...")
        try:
            import os
            from moviepy import VideoFileClip, AudioFileClip, ImageClip, concatenate_videoclips, CompositeVideoClip, ColorClip
            import numpy as np
            
            # 更新进度
            self.update_task_progress("正在准备视频生成...", 10)
            
            # 检查是否被暂停
            if not self.pause_event.is_set():
                self.log("⏸️ 任务已暂停，等待恢复...")
                self.pause_event.wait()
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 清除图片和视频文件（除非明确跳过）
            if not skip_clear:
                self.update_task_progress("正在清理旧文件...", 20)
                self.clear_images_and_videos()
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 检查是否有分镜数据，如果没有则尝试从文件加载
            if not self.shots_data:
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        self.log(f"📂 已从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        self.log("❌ 没有分镜数据，无法生成视频")
                        self.update_task_progress("就绪")
                        return
                else:
                    self.log("❌ 没有分镜数据，无法生成视频")
                    self.update_task_progress("就绪")
                    return
            
            # 检查是否有音频文件
            if not self.audio_path:
                self.log("❌ 没有音频文件，无法生成视频")
                self.update_task_progress("就绪")
                return
            
            # 检查图像是否存在，详细记录缺失的图像（除非明确跳过检查）
            if skip_image_check:
                self.log("ℹ️ 跳过图片检查（直接渲染模式）")
            else:
                self.update_task_progress("正在检查图像文件...", 30)
                missing_images = []
                for shot in self.shots_data:
                    # 检查是否被暂停
                    if not self.pause_event.is_set():
                        self.log("⏸️ 任务已暂停，等待恢复...")
                        self.pause_event.wait()
                    
                    # 检查是否被取消
                    if not self.task_running:
                        self.log("❌ 任务已被取消")
                        return
                    
                    image_path = os.path.join(self.images_dir, shot['image_file'])
                    if not os.path.exists(image_path):
                        missing_images.append(shot['image_file'])
                
                if missing_images:
                    self.log(f"⚠️ 发现 {len(missing_images)} 个缺失的图像文件")
                    for image_file in missing_images:
                        self.log(f"❌ 缺少图像: {image_file}")
                    self.log("⚠️ 开始生成缺失的图像...")
                    self.generate_images()
                    # 再次检查图像是否存在
                    missing_images = []
                    for shot in self.shots_data:
                        # 检查是否被暂停
                        if not self.pause_event.is_set():
                            self.log("⏸️ 任务已暂停，等待恢复...")
                            self.pause_event.wait()
                        
                        # 检查是否被取消
                        if not self.task_running:
                            self.log("❌ 任务已被取消")
                            return
                        
                        image_path = os.path.join(self.images_dir, shot['image_file'])
                        if not os.path.exists(image_path):
                            missing_images.append(shot['image_file'])
                    
                    if missing_images:
                        self.log(f"❌ 图像生成失败，仍然缺少 {len(missing_images)} 个图像文件")
                        for image_file in missing_images:
                            self.log(f"❌ 缺少图像: {image_file}")
                        self.log("❌ 拒绝生成视频，因为缺少必要的图像文件")
                        self.update_task_progress("就绪")
                        return
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 加载音频
            self.update_task_progress("正在加载音频...", 40)
            audio = AudioFileClip(self.audio_path)
            audio_duration = audio.duration
            
            # 修复：验证并调整分镜时长，确保与音频时长精确匹配（音画同步关键步骤）
            self.update_task_progress("正在校准时间轴...", 45)
            
            # 首先验证每个分镜的duration与end-start一致性
            for i, shot in enumerate(self.shots_data):
                expected_duration = shot['end'] - shot['start']
                if abs(shot.get('duration', 0) - expected_duration) > 0.001:
                    self.log(f"⚠️ 分镜{i+1} duration不一致: {shot.get('duration', 0):.3f}s -> {expected_duration:.3f}s")
                    shot['duration'] = expected_duration
            
            total_shots_duration = sum(shot.get('duration', 0) for shot in self.shots_data)
            
            # 添加详细的分镜时长日志
            self.log(f"📊 音频时长: {audio_duration:.3f}s, 分镜总时长: {total_shots_duration:.3f}s")
            for i, shot in enumerate(self.shots_data[:5]):
                self.log(f"   分镜{i+1}: start={shot['start']:.2f}s, end={shot['end']:.2f}s, duration={shot.get('duration', 0):.2f}s")
            if len(self.shots_data) > 5:
                self.log(f"   ... 共 {len(self.shots_data)} 个分镜")
            
            # 如果分镜总时长与音频时长差异超过10ms，需要调整
            # 注意：我们保持原始的 start 时间戳，只调整 duration
            duration_diff = abs(total_shots_duration - audio_duration)
            if duration_diff > 0.01:  # 10ms阈值
                self.log(f"⚠️ 分镜总时长({total_shots_duration:.3f}s)与音频时长({audio_duration:.3f}s)差异: {duration_diff:.3f}s")
                self.log("ℹ️ 保持原始时间戳，只调整duration来匹配音频总时长")
                
                # 只调整 duration，不改变 start
                # 保持原始的 start 时间戳用于视频定位
                for shot in self.shots_data:
                    original_start = shot.get('start', 0)
                    ratio = audio_duration / total_shots_duration
                    shot['duration'] = shot.get('duration', 0) * ratio
                    shot['end'] = original_start + shot['duration']
                
                total_shots_duration = sum(shot.get('duration', 0) for shot in self.shots_data)
                self.log(f"✅ 时间轴调整完成，总分镜时长: {total_shots_duration:.3f}s")
                
                for i, shot in enumerate(self.shots_data[:3]):
                    self.log(f"   分镜{i+1}: start={shot['start']:.2f}s, end={shot['end']:.2f}s, duration={shot.get('duration', 0):.2f}s")
            else:
                self.log(f"✅ 时间轴已精确匹配，总分镜时长: {total_shots_duration:.3f}s")
            
            # 准备视频片段 - 只设置时长，不设置起始时间，让concatenate自动计算
            self.update_task_progress("正在准备视频片段...", 50)
            clips = []
            # 获取用户选择的动画效果
            animation_type = self.animation_var.get() if hasattr(self, 'animation_var') else "无"
            
            # 显示动画效果设置
            if animation_type != "无":
                self.log(f"🎬 使用单张画面动画: {animation_type}")
            else:
                self.log(f"🎬 单张画面动画: 无")
            
            # 详细记录每个分镜的时间戳信息（用于调试音画同步）
            self.log("📊 分镜时间戳详情:")
            for i, shot in enumerate(self.shots_data):
                self.log(f"   分镜{i+1}: start={shot['start']:.3f}s, end={shot['end']:.3f}s, duration={shot['duration']:.3f}s")
            
            for i, shot in enumerate(self.shots_data):
                # 检查是否被取消
                if not self.task_running:
                    self.log("❌ 任务已被取消")
                    return
                
                # 修复：使用end-start计算实际duration，确保与时间戳一致
                actual_duration = shot['end'] - shot['start']
                if abs(actual_duration - shot['duration']) > 0.001:
                    self.log(f"⚠️ 分镜{i+1} duration修正: {shot['duration']:.3f}s -> {actual_duration:.3f}s")
                    shot['duration'] = actual_duration
                
                # 直接渲染时使用图片序号映射
                if hasattr(self, 'image_map') and use_original_resolution:
                    expected_num = i + 1
                    if expected_num in self.image_map:
                        image_file = self.image_map[expected_num]
                        image_path = os.path.join(self.images_dir, image_file)
                        if os.path.exists(image_path):
                            # 修复：加载图片并统一尺寸，避免不同尺寸图片导致闪动
                            from PIL import Image
                            img = Image.open(image_path)
                            # 统一转换为1920x1080（保持比例，填充黑边）
                            target_width, target_height = 1920, 1080
                            img = self._resize_image_to_fit(img, target_width, target_height)
                            clip = ImageClip(np.array(img)).with_duration(shot['duration'])
                            self.log(f"   分镜{i+1}: 图片={image_file}, duration={shot['duration']:.3f}s, 尺寸={img.size}")
                            # 应用动画效果
                            if animation_type != "无":
                                clip = self.apply_animation_effect(clip, animation_type, 1920, 1080)
                            clips.append(clip)
                        else:
                            self.log(f"⚠️ 图像文件不存在: {image_path}")
                    else:
                        self.log(f"⚠️ 找不到序号为 {expected_num} 的图片")
                else:
                    # 正常模式使用固定文件名
                    image_path = os.path.join(self.images_dir, shot['image_file'])
                    if os.path.exists(image_path):
                        # 修复：加载图片并统一尺寸，避免不同尺寸图片导致闪动
                        from PIL import Image
                        img = Image.open(image_path)
                        # 统一转换为1920x1080（保持比例，填充黑边）
                        target_width, target_height = 1920, 1080
                        img = self._resize_image_to_fit(img, target_width, target_height)
                        clip = ImageClip(np.array(img)).with_duration(shot['duration'])
                        self.log(f"   分镜{i+1}: 图片={shot['image_file']}, duration={shot['duration']:.3f}s, 尺寸={img.size}")
                        # 应用动画效果
                        if animation_type != "无":
                            clip = self.apply_animation_effect(clip, animation_type, 1920, 1080)
                        clips.append(clip)
                    else:
                        self.log(f"⚠️ 图像文件不存在: {image_path}")
            
            if not clips:
                self.log("❌ 没有找到有效的图像文件，无法生成视频")
                self.update_task_progress("就绪")
                return
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 应用过渡效果
            self.update_task_progress("正在应用过渡效果...", 60)
            self.log("🔄 正在应用过渡效果...")
            transition_type = self.transition_var.get() if hasattr(self, 'transition_var') else "硬切"
            self.log(f"🎬 使用过渡模式: {transition_type}")
            
            # 获取视频宽度和高度
            width, height = 1920, 1080  # 默认1080p分辨率
            if clips:
                # 从第一个片段获取分辨率
                try:
                    first_clip = clips[0]
                    width, height = first_clip.size
                except:
                    pass
            
            # 修复：使用concatenate_videoclips替代CompositeVideoClip，确保时间轴精准
            transition_duration = 0.5  # 过渡效果持续时间（秒）
            
            if transition_type == "硬切":
                # 硬切：直接拼接，无过渡效果，时间最精准
                self.log(f"🎬 应用硬切效果（时间最精准）")
                if len(clips) > 1:
                    final_clip = concatenate_videoclips(clips, method="chain")
                else:
                    final_clip = clips[0]
                    
            elif transition_type == "淡入淡出":
                # 淡入淡出效果
                self.log(f"🎬 应用淡入淡出效果")
                from moviepy.video.fx import FadeIn, FadeOut
                
                # 为每个片段添加淡入淡出效果
                clips_with_fade = []
                for i, clip in enumerate(clips):
                    if i == 0:
                        clips_with_fade.append(clip.with_effects([FadeIn(transition_duration)]))
                    elif i == len(clips) - 1:
                        clips_with_fade.append(clip.with_effects([FadeIn(transition_duration), FadeOut(transition_duration)]))
                    else:
                        clips_with_fade.append(clip.with_effects([FadeIn(transition_duration)]))
                
                if len(clips_with_fade) > 1:
                    final_clip = concatenate_videoclips(clips_with_fade, method="chain")
                else:
                    final_clip = clips_with_fade[0]
                    
            elif transition_type == "交叉溶解":
                # 交叉溶解效果
                self.log(f"🎬 应用交叉溶解效果")
                from moviepy.video.fx import CrossFadeIn
                
                # 应用交叉溶解
                clips_with_crossfade = []
                for i, clip in enumerate(clips):
                    if i == 0:
                        clips_with_crossfade.append(clip)
                    else:
                        # 应用交叉溶解效果
                        clip_with_transition = clip.with_effects([CrossFadeIn(transition_duration)])
                        clips_with_crossfade.append(clip_with_transition)
                
                if len(clips_with_crossfade) > 1:
                    final_clip = concatenate_videoclips(clips_with_crossfade, method="chain")
                else:
                    final_clip = clips_with_crossfade[0]
            else:
                # 默认使用硬切
                self.log(f"🎬 使用默认硬切效果")
                if len(clips) > 1:
                    final_clip = concatenate_videoclips(clips, method="chain")
                else:
                    final_clip = clips[0]
            
            # 计算实际视频时长
            actual_video_duration = sum(clip.duration for clip in clips)
            self.log(f"📊 片段总时长: {actual_video_duration:.3f}s, 音频时长: {audio_duration:.3f}s")
            
            # 修复：验证视频时长与音频时长是否匹配
            self.log(f"📊 视频时长: {actual_video_duration:.3f}s, 音频时长: {audio_duration:.3f}s")
            
            # 添加音频
            self.update_task_progress("正在添加音频...", 70)
            # 修复：确保视频时长与音频时长精确匹配，实现音画同步
            # 获取拼接后的实际视频时长
            final_video_duration = final_clip.duration
            self.log(f"📊 拼接后视频时长: {final_video_duration:.3f}s, 音频时长: {audio_duration:.3f}s")
            
            duration_diff = abs(final_video_duration - audio_duration)
            if duration_diff > 0.001:  # 更严格的阈值 1ms
                self.log(f"🔄 视频时长({final_video_duration:.3f}s)与音频时长({audio_duration:.3f}s)差异: {duration_diff:.3f}s")
                if final_video_duration > audio_duration:
                    self.log("   视频比音频长，将截断视频以匹配音频")
                else:
                    self.log("   视频比音频短，将延长最后一帧以匹配音频")
                # 使用音频时长作为最终时长，确保音画同步
                final_clip = final_clip.with_duration(audio_duration)
                final_video_duration = audio_duration
            else:
                self.log(f"✅ 视频时长与音频时长已精确匹配: {audio_duration:.3f}s")
            
            # 再次验证最终时长
            self.log(f"🔍 最终验证 - 视频时长: {final_video_duration:.3f}s, 音频时长: {audio_duration:.3f}s, 差异: {abs(final_video_duration - audio_duration):.6f}s")
            
            final_clip = final_clip.with_audio(audio)
            
            # 设置视频分辨率
            self.update_task_progress("正在设置视频分辨率...", 80)
            if use_original_resolution and clips:
                # 使用第一个图片的原始分辨率
                from PIL import Image
                if hasattr(self, 'image_map') and self.image_map:
                    # 直接渲染模式，使用图片映射
                    first_image_file = self.image_map[1]  # 第一个图片（序号1）
                    first_image_path = os.path.join(self.images_dir, first_image_file)
                else:
                    # 正常模式，使用分镜数据中的文件名
                    first_image_path = os.path.join(self.images_dir, self.shots_data[0]['image_file'])
                
                if os.path.exists(first_image_path):
                    img = Image.open(first_image_path)
                    width, height = img.size
                    self.log(f"📐 使用原始图片分辨率: {width}x{height}")
                else:
                    # 如果第一个图片不存在，使用默认分辨率
                    width = int(self.width_var.get()) if hasattr(self, 'width_var') else 1920
                    height = int(self.height_var.get()) if hasattr(self, 'height_var') else 1080
            else:
                # 使用用户设置的分辨率
                width = int(self.width_var.get()) if hasattr(self, 'width_var') else 1920
                height = int(self.height_var.get()) if hasattr(self, 'height_var') else 1080
                # moviepy 2.x 使用 scale 方法
                final_clip = final_clip.scale(width=width, height=height)
            
            # 输出路径
            output_path = os.path.join(self.output_dir, f"output_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
            
            # 检查是否被取消
            if not self.task_running:
                self.log("❌ 任务已被取消")
                return
            
            # 优化视频编码设置，利用GPU加速
            self.update_task_progress("正在渲染视频...", 90)
            
            # 检测最佳编码方式
            use_gpu = False
            try:
                import torch
                if torch.cuda.is_available():
                    # 检查FFmpeg是否支持NVENC编码器
                    import subprocess
                    result = subprocess.run(
                        ['ffmpeg', '-encoders'],
                        capture_output=True,
                        text=True
                    )
                    if 'h264_nvenc' in result.stdout:
                        use_gpu = True
                        self.log("✅ 检测到GPU加速支持，使用NVENC编码")
                    else:
                        self.log("⚠️ 未检测到NVENC编码器，使用CPU渲染")
                else:
                    self.log("⚠️ 未检测到CUDA支持，使用CPU渲染")
            except Exception as e:
                self.log(f"⚠️ GPU检测失败，使用CPU渲染: {e}")
            
            # 根据检测结果选择编码方式
            try:
                if use_gpu:
                    self.log("⚡ 正在使用GPU加速渲染视频...")
                    final_clip.write_videofile(
                        output_path,
                        fps=30,
                        codec='h264_nvenc',
                        bitrate='5000k',
                        audio_codec='aac',
                        preset='fast',
                        threads=self.max_workers,
                        logger=None  # 减少moviepy输出
                    )
                else:
                    self.log("⚡ 正在使用CPU渲染视频...")
                    final_clip.write_videofile(
                        output_path,
                        fps=30,
                        codec='libx264',
                        bitrate='5000k',
                        audio_codec='aac',
                        preset='fast',
                        threads=self.max_workers,
                        logger=None  # 减少moviepy输出
                    )
            except Exception as e:
                self.log(f"⚠️ 视频渲染失败: {e}")
                raise
            
            # 更新进度为完成
            self.update_task_progress("视频生成完成", 100)
            self.log(f"✅ 视频生成完成: {output_path}")
            self.state_manager['video']['generated'] = True
            self.state_manager['video']['path'] = output_path
            
            # 释放资源
            self.log("🔄 释放资源...")
            # 清理视频片段
            for clip in clips:
                clip.close()
            final_clip.close()
            audio.close()
            
            # 清理内存
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
            except:
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
    
    def apply_animation_effect(self, clip, animation_type, width, height):
        """应用单张画面的动画效果 - 修复MoviePy 2.x兼容性问题"""
        try:
            if animation_type == "缩放":
                # 缩放动画：MoviePy 2.x 使用 imagefx.resize 或修改 transform
                self.log(f"🎬 应用缩放动画效果")
                
                # 方法1：使用 with_effects 和 transforms
                # 从100%缓慢缩放到110%
                def scale_func(t, clip_duration):
                    return 1 + (t / clip_duration) * 0.1
                
                # 使用 lambda 来实现动态缩放
                return clip.transform(lambda get_frame, t: 
                    self._scale_frame(get_frame(t), scale_func(t, clip.duration)))
            else:
                # 无动画效果
                return clip
                
        except Exception as e:
            self.log(f"⚠️ 应用动画效果失败: {e}")
            import traceback
            traceback.print_exc()
            return clip
    
    def _scale_frame(self, frame, scale_factor):
        """缩放单个帧 - 修复居中计算错误"""
        try:
            from PIL import Image
            import numpy as np
            
            # 将 numpy array 转回 PIL Image
            if isinstance(frame, np.ndarray):
                img = Image.fromarray(frame)
            else:
                img = frame
            
            # 获取原始尺寸
            w, h = img.size
            
            # 计算新尺寸
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            
            # 缩放图片
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            
            # 如果放大，创建与原始尺寸相同的画布并居中粘贴缩放后的图片
            if scale_factor > 1:
                # 创建与原始尺寸相同的画布（保持输出尺寸一致）
                new_img = Image.new('RGB', (w, h), (0, 0, 0))
                # 计算居中粘贴位置（缩放后的图片比画布大，取中间部分）
                paste_x = (w - new_w) // 2
                paste_y = (h - new_h) // 2
                new_img.paste(resized, (paste_x, paste_y))
                return np.array(new_img)
            else:
                return np.array(resized)
        except Exception as e:
            self.log(f"⚠️ 缩放帧失败: {e}")
            return frame

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
        """线程化渲染视频（跑图生成视频）"""
        try:
            # 立即更新UI，显示任务开始
            self.log("🎞️ 开始线程化渲染视频...")
            
            # 检查是否有分镜数据
            if not hasattr(self, 'shots_data') or not self.shots_data:
                # 尝试从 shots_data.json 文件加载分镜数据
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        self.log(f"📂 已从文件加载分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"❌ 加载分镜数据失败: {e}")
                        self.log("❌ 没有分镜数据，请先生成分镜脚本")
                        return
                else:
                    self.log("❌ 没有分镜数据，请先生成分镜脚本")
                    # 注意：不要在后台线程中调用messagebox，会导致界面卡住！
                    return
            
            self.log(f"   📊 当前有 {len(self.shots_data)} 个分镜")
            
            # 启动一个新线程来执行渲染视频的任务
            def render_video_worker():
                # 设置任务状态为运行中
                self.task_running = True
                self.pause_event.set()  # 确保事件被设置
                self.log("🎞️ 开始渲染视频...")
                try:
                    self.generate_video()
                except Exception as e:
                    self.log(f"❌ 渲染视频出错: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # 任务完成后重置状态
                    self.task_running = False
                    # 检查是否可以执行直接生成视频
                    self.check_and_prompt_direct_render()
            
            # 使用更高优先级的线程
            thread = threading.Thread(target=render_video_worker, daemon=True)
            thread.start()
            self.log("✅ 渲染线程已启动")
        except Exception as e:
            self.log(f"❌ 渲染视频线程启动失败: {e}")
            import traceback
            traceback.print_exc()
    
    def check_and_prompt_direct_render(self):
        """检查是否满足直接生成视频的条件，并提示用户"""
        try:
            # 延迟一点执行，确保视频生成完全完成
            import time
            time.sleep(1)
            
            # 检查条件1: 音频已导入
            has_audio = self.audio_path and os.path.exists(self.audio_path)
            
            # 检查条件2: 有分镜脚本数据
            has_shots = hasattr(self, 'shots_data') and self.shots_data and len(self.shots_data) > 0
            
            # 检查条件3: 文件夹内有图片
            has_images = False
            image_count = 0
            if os.path.exists(self.images_dir):
                image_files = [f for f in os.listdir(self.images_dir) if f.endswith('.png') or f.endswith('.jpg')]
                image_count = len(image_files)
                has_images = image_count > 0
            
            # 检查条件4: 图片数量与分镜数量匹配
            shots_count = len(self.shots_data) if has_shots else 0
            images_match = has_images and image_count == shots_count
            
            # 记录检查结果
            self.log("\n" + "="*50)
            self.log("📋 检查直接生成视频条件:")
            self.log(f"   ✓ 音频已导入: {has_audio}")
            self.log(f"   ✓ 分镜脚本数据: {has_shots} ({shots_count}个分镜)")
            self.log(f"   ✓ 图片文件: {has_images} ({image_count}张图片)")
            self.log(f"   ✓ 数量匹配: {images_match}")
            self.log("="*50 + "\n")
            
            # 如果所有条件都满足，提示用户
            if has_audio and has_shots and has_images and images_match:
                self.log("✅ 所有条件满足，可以执行直接生成视频！")
                
                # 在主线程中显示对话框
                def show_prompt():
                    try:
                        from tkinter import messagebox
                        result = messagebox.askyesno(
                            "跑图完成",
                            f"🎉 跑图生成视频已完成！\n\n"
                            f"检测到以下条件已满足：\n"
                            f"✓ 音频已导入\n"
                            f"✓ 分镜脚本数据 ({shots_count}个)\n"
                            f"✓ 图片文件 ({image_count}张)\n"
                            f"✓ 数量匹配\n\n"
                            f"是否立即执行【直接生成视频】？\n\n"
                            f"提示：直接生成视频将使用现有图片快速渲染，\n"
                            f"不会重新生成图片，速度更快。",
                            icon='info'
                        )
                        if result:
                            self.log("🎬 用户选择执行直接生成视频...")
                            self.direct_render_video()
                        else:
                            self.log("⏸️ 用户选择暂不执行直接生成视频")
                            self.log("💡 提示：您可以随时点击【直接生成视频】按钮手动执行")
                    except Exception as e:
                        self.log(f"⚠️ 显示提示对话框失败: {e}")
                
                # 在主线程中执行对话框
                if hasattr(self, 'root') and self.root:
                    self.root.after(100, show_prompt)
            else:
                # 有条件不满足，记录日志
                if not has_audio:
                    self.log("⚠️ 缺少音频文件，无法执行直接生成视频")
                if not has_shots:
                    self.log("⚠️ 缺少分镜脚本数据，无法执行直接生成视频")
                if not has_images:
                    self.log("⚠️ 缺少图片文件，无法执行直接生成视频")
                if has_shots and has_images and not images_match:
                    self.log(f"⚠️ 图片数量({image_count})与分镜数量({shots_count})不匹配，无法执行直接生成视频")
                    
        except Exception as e:
            self.log(f"⚠️ 检查直接生成视频条件时出错: {e}")
    
    def direct_render_video(self):
        """直接渲染视频"""
        try:
            self.log("🎞️ 开始直接渲染视频...")
            
            # 检查1: 是否已导入音频
            if not self.audio_path or not os.path.exists(self.audio_path):
                self.log("❌ 错误: 请先导入音频文件")
                import tkinter as tk
                from tkinter import messagebox
                root = self.root if hasattr(self, 'root') else None
                if root:
                    root.after(0, lambda: messagebox.showerror("缺少音频", "请先导入音频文件"))
                return
            
            # 检查2: 是否存在分镜脚本数据，如果没有尝试从文件加载
            if not hasattr(self, 'shots_data') or not self.shots_data:
                # 尝试从文件加载分镜数据
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    try:
                        with open(shots_file, 'r', encoding='utf-8') as f:
                            self.shots_data = json.load(f)
                        self.log(f"📂 从文件加载了分镜数据: {len(self.shots_data)} 个分镜")
                    except Exception as e:
                        self.log(f"⚠️ 加载分镜数据失败: {e}")
                        self.shots_data = []
            
            # 再次检查分镜数据
            if not hasattr(self, 'shots_data') or not self.shots_data:
                self.log("❌ 错误: 没有分镜脚本数据，无法将图片与音频时间戳对应")
                import tkinter as tk
                from tkinter import messagebox
                root = self.root if hasattr(self, 'root') else None
                if root:
                    root.after(0, lambda: messagebox.showerror("缺少分镜脚本", "请先生成分镜脚本"))
                return
            
            # 检查3: 是否有图片文件夹
            if not os.path.exists(self.images_dir):
                self.log("❌ 错误: 图片文件夹不存在")
                return
            
            # 获取图片文件 (.png 或 .jpg)
            image_files = [f for f in os.listdir(self.images_dir) if f.endswith('.png') or f.endswith('.jpg')]
            if not image_files:
                self.log("❌ 错误: 没有找到图片文件")
                return
            
            self.log(f"📁 找到 {len(image_files)} 个图片文件")
            
            # 提取图片序号并创建映射
            import re
            def extract_number(filename):
                match = re.search(r'\d+', filename)
                return int(match.group()) if match else None
            
            # 创建图片序号映射
            image_map = {}
            for img_file in image_files:
                num = extract_number(img_file)
                if num:
                    image_map[num] = img_file
            
            # 检查4: 图片数量是否与分镜脚本数量一致
            expected_shots = len(self.shots_data)
            if len(image_map) != expected_shots:
                warning_msg = f"⚠️ 警告: 有效图片数量({len(image_map)})与分镜脚本数量({expected_shots})不一致！\n请确保每个分镜都有对应的图片，且图片文件名包含正确的序号。"
                self.log(warning_msg)
                import tkinter as tk
                from tkinter import messagebox
                root = self.root if hasattr(self, 'root') else None
                if root:
                    root.after(0, lambda: messagebox.showwarning("数量不匹配", warning_msg))
            
            # 检查5: 确保所有分镜都有对应的图片
            missing_shots = []
            for i, shot in enumerate(self.shots_data):
                expected_num = i + 1
                if expected_num not in image_map:
                    missing_shots.append(expected_num)
            
            if missing_shots:
                error_msg = f"❌ 错误: 缺少以下序号的图片: {', '.join(map(str, missing_shots))}\n请确保图片文件名包含正确的序号。"
                self.log(error_msg)
                import tkinter as tk
                from tkinter import messagebox
                root = self.root if hasattr(self, 'root') else None
                if root:
                    root.after(0, lambda: messagebox.showerror("缺少图片", error_msg))
                return
            
            # 保存图片映射到实例变量
            self.image_map = image_map
            
            # 直接调用视频生成（跳过清除步骤）
            def direct_render_worker():
                self.task_running = True
                self.pause_event.set()
                try:
                    self.generate_video(skip_clear=True, use_original_resolution=True, skip_image_check=True)
                finally:
                    self.task_running = False
            
            thread = threading.Thread(target=direct_render_worker, daemon=True)
            thread.start()
        except Exception as e:
            self.log(f"❌ 直接渲染视频失败: {e}")
            import traceback
            traceback.print_exc()
    
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
                
                # 加载大模型设置 - 默认使用脚本自带，避免大模型调用卡住
                # 强制设置为"脚本自带"，用户需要手动开启才使用大模型
                self.optimization_method_var.set("脚本自带")
                    
                # 加载Ollama模型设置 - 强制默认使用脚本自带
                if hasattr(self, 'ollama_model_var'):
                    self.ollama_model_var.set("脚本自带")
                    
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
                'optimization_method': self.optimization_method_var.get() if hasattr(self, 'optimization_method_var') else '脚本自带',
                'ollama_model': self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else '脚本自带',
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