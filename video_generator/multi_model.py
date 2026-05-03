# -*- coding: utf-8 -*-
"""LLMPerformanceOptimizer + MultiModelFusion - 性能优化与多模型融合"""

import threading
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from .ollama_client import (
    LLMConfig, is_ollama_available, is_llm_available, get_available_models,
    call_ollama_single
)


class LLMPerformanceOptimizer:
    """大模型性能优化器 - 自适应调整参数"""

    def __init__(self):
        self.call_history = []
        self.max_history = 10
        self.avg_response_time = 0
        self.success_rate = 1.0
        self._lock = threading.Lock()

    def record_call(self, duration, success, token_count=0):
        with self._lock:
            self.call_history.append({
                "duration": duration,
                "success": success,
                "token_count": token_count,
                "timestamp": datetime.datetime.now()
            })
            if len(self.call_history) > self.max_history:
                self.call_history.pop(0)
            self._update_stats()

    def _update_stats(self):
        if not self.call_history:
            return
        durations = [h["duration"] for h in self.call_history]
        self.avg_response_time = sum(durations) / len(durations)
        successes = sum(1 for h in self.call_history if h["success"])
        self.success_rate = successes / len(self.call_history)

    def get_optimal_config(self, task_complexity="medium"):
        base_config = LLMConfig("质量优先")
        if self.success_rate < 0.7:
            base_config.apply_preset("平衡模式")
            base_config.set_custom_param("num_predict", 1500)
        elif self.avg_response_time > 20:
            base_config.apply_preset("极速模式")

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
        suggestions = []
        if self.avg_response_time > 15:
            suggestions.append(f"平均响应时间 {self.avg_response_time:.1f}s 较长，建议使用极速模式或减少num_predict")
        if self.success_rate < 0.8:
            suggestions.append(f"成功率 {self.success_rate*100:.1f}% 较低，建议检查模型状态或降低temperature")
        if not suggestions:
            suggestions.append(f"性能良好：平均响应 {self.avg_response_time:.1f}s，成功率 {self.success_rate*100:.1f}%")
        return suggestions


llm_optimizer = LLMPerformanceOptimizer()


class MultiModelFusion:
    """多模型融合系统 - 整合多个模型的优势"""

    def __init__(self):
        self.available_models = []
        self.model_weights = {}
        self.fusion_strategy = "weighted_vote"

    def discover_models(self):
        if not is_ollama_available():
            return []
        try:
            models = get_available_models(force_refresh=True)
            self.available_models = []
            for model_name in models:
                self.available_models.append(model_name)
                self.model_weights[model_name] = self._calculate_model_weight(model_name)
            return self.available_models
        except Exception as e:
            print(f"发现模型失败: {e}")
        return []

    def _calculate_model_weight(self, model_name):
        weights = {
            "gemma3:4b": 0.9, "gemma3:1b": 0.7,
            "deepseek-r1:8b": 0.85, "deepseek-r1:14b": 0.95,
            "mistral": 0.8, "mistral:7b": 0.85,
            "llama3": 0.85, "llama3:8b": 0.9,
            "qwen3:8b": 0.9, "qwen3:4b": 0.8
        }
        if model_name in weights:
            return weights[model_name]
        for key, weight in weights.items():
            if key in model_name:
                return weight
        return 0.75

    def parallel_generate(self, prompt_template, models=None, timeout=60):
        if not is_llm_available():
            return None
        if models is None:
            models = self.available_models[:3]
        if not models:
            return None

        results = {}

        def call_single_model(model_name):
            try:
                start_time = time.time()

                result_text, used_model = call_ollama_single(
                    model_name,
                    prompt_template["system"],
                    prompt_template["user"],
                    llm_config=LLMConfig()
                )
                duration = time.time() - start_time

                if result_text:
                    return {
                        "model": model_name,
                        "result": result_text,
                        "duration": duration,
                        "weight": self.model_weights.get(model_name, 0.75)
                    }
                else:
                    return {
                        "model": model_name,
                        "result": "",
                        "duration": duration,
                        "weight": 0,
                        "error": "调用返回空"
                    }
            except Exception as e:
                return {
                    "model": model_name,
                    "result": "",
                    "duration": 0,
                    "weight": 0,
                    "error": str(e)
                }

        with ThreadPoolExecutor(max_workers=len(models)) as executor:
            future_to_model = {
                executor.submit(call_single_model, model): model
                for model in models
            }
            for future in as_completed(future_to_model, timeout=timeout):
                model = future_to_model[future]
                try:
                    results[model] = future.result()
                except Exception as e:
                    results[model] = {
                        "model": model, "result": "", "duration": 0,
                        "weight": 0, "error": str(e)
                    }
        return results

    def fuse_results(self, results, strategy=None):
        if not results:
            return None
        if strategy is None:
            strategy = self.fusion_strategy

        valid_results = {k: v for k, v in results.items() if v.get("result") and not v.get("error")}
        if not valid_results:
            return None

        if strategy == "best_single":
            best = max(valid_results.values(), key=lambda x: x["weight"])
            return best["result"]
        elif strategy == "weighted_vote":
            scored_results = []
            for r in valid_results.values():
                length_score = min(len(r["result"]) / 500, 1.0)
                quality_score = r["weight"]
                final_score = quality_score * 0.7 + length_score * 0.3
                scored_results.append((r, final_score))
            best = max(scored_results, key=lambda x: x[1])
            return best[0]["result"]
        elif strategy == "cascade":
            sorted_by_size = sorted(
                valid_results.values(),
                key=lambda x: ("1b" in x["model"], "4b" in x["model"], "7b" in x["model"], "8b" in x["model"], "14b" in x["model"]),
                reverse=True
            )
            if sorted_by_size:
                return sorted_by_size[0]["result"]

        return list(valid_results.values())[0]["result"]

    def get_fusion_report(self, results):
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


multi_model_fusion = MultiModelFusion()
