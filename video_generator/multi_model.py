# -*- coding: utf-8 -*-
"""LLMPerformanceOptimizer, MultiModelFusion - 从 My-Video Generator.py 提取"""

import threading
import time
import datetime
import concurrent.futures
from .config import Config


# === 从 My-Video Generator.py 提取 ===

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
