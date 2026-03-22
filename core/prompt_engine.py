"""提示词引擎模块 - 统一管理提示词生成和优化"""

import re
from typing import Optional

from .config import (
    LLMConfig,
    SYSTEM_PROMPT_WITH_CONTEXT,
    SYSTEM_PROMPT_WITHOUT_CONTEXT,
    SYSTEM_PROMPT_LIGHTWEIGHT,
    BAD_PROMPT_PATTERNS,
    QUALITY_TAGS,
    DEFAULT_NEGATIVE_PROMPT,
    CONTENT_TYPE_TAGS,
)
from .ollama_client import get_ollama_client


class PromptEngine:
    """提示词引擎 - 统一管理提示词生成和优化"""
    
    def __init__(self):
        self.client = get_ollama_client()
    
    def optimize_full(self, prompt: str, sentence: str, 
                     full_context: Optional[str] = None,
                     user_model: Optional[str] = None) -> str:
        """完整优化 - 使用完整上下文
        
        Args:
            prompt: 原始提示词
            sentence: 配音文本
            full_context: 全文上下文
            user_model: 用户指定的模型
        Returns:
            优化后的提示词
        """
        if not self.client.is_available:
            return prompt
        
        # 构建system prompt
        if full_context and len(full_context) > 50:
            system_prompt = SYSTEM_PROMPT_WITH_CONTEXT
            user_prompt = f"【全文核心主题参考】\n{full_context[:800]}...\n\n【当前分镜配音】\n{sentence}\n\n请根据全文核心思想，为当前分镜生成精准的英文画面提示词："
        else:
            system_prompt = SYSTEM_PROMPT_WITHOUT_CONTEXT
            user_prompt = f"配音：{sentence}"
        
        # 选择模型
        model = self.client.select_model(user_model, lightweight=False)
        if not model:
            return prompt
        
        # 调用API
        config = LLMConfig("质量优先")
        response = self.client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options=config.get_options(num_predict=500)
        )
        
        if not response:
            return prompt
        
        result = response["message"]["content"].strip()
        return self._clean_result(result) or prompt
    
    def optimize_lightweight(self, prompt: str, sentence: str,
                           user_model: Optional[str] = None) -> str:
        """轻量级优化 - 速度快
        
        Args:
            prompt: 原始提示词
            sentence: 配音文本
            user_model: 用户指定的模型
        Returns:
            优化后的提示词
        """
        if not self.client.is_available:
            return prompt
        
        # 轻量级prompt
        system_prompt = SYSTEM_PROMPT_LIGHTWEIGHT
        user_prompt = f"配音：{sentence}"
        
        # 选择最小的模型
        model = self.client.select_model(user_model, lightweight=True)
        if not model:
            return prompt
        
        # 轻量级配置
        config = LLMConfig("极速模式")
        response = self.client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options=config.get_options(num_predict=150)
        )
        
        if not response:
            return prompt
        
        result = response["message"]["content"].strip()
        return self._clean_result(result) or prompt
    
    def _clean_result(self, result: str) -> Optional[str]:
        """清理结果 - 移除坏模式"""
        for pattern in BAD_PROMPT_PATTERNS:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # 清理多余字符
        result = re.sub(r'^[\,\s]+', '', result)
        result = re.sub(r'[\,\s]+$', '', result)
        result = re.sub(r',+', ',', result)
        
        if result and len(result) > 10:
            return result.strip()
        return None
    
    def generate_sd_prompt(self, sentence: str, content_type: str = "general",
                          core_theme: str = "", visual_tone: str = "") -> str:
        """生成SD提示词 - 脚本模式
        
        Args:
            sentence: 配音文本
            content_type: 内容类型
            core_theme: 核心主题
            visual_tone: 视觉基调
        Returns:
            SD提示词
        """
        # 基础风格标签
        base_tags = ["documentary photography", "cinematic still"]
        
        # 添加内容类型标签
        content_tags = CONTENT_TYPE_TAGS.get(content_type, CONTENT_TYPE_TAGS["general"])
        
        # 构建场景描述
        scene_desc = sentence
        if core_theme:
            scene_desc = f"{core_theme}: {scene_desc}"
        
        # 添加视觉基调
        if visual_tone:
            scene_desc = f"{visual_tone}, {scene_desc}"
        
        # 组装提示词
        parts = base_tags + [scene_desc] + QUALITY_TAGS[:4]
        return ", ".join(parts)
    
    def evaluate_quality(self, prompt: str, sentence: str, content_type: str) -> float:
        """评估提示词质量
        
        Args:
            prompt: 提示词
            sentence: 配音文本
            content_type: 内容类型
        Returns:
            质量分数 0-1
        """
        score = 0.0
        
        # 长度评分
        if 50 <= len(prompt) <= 200:
            score += 0.2
        elif len(prompt) > 200:
            score += 0.1
        
        # 关键词评分
        keywords = ["documentary", "cinematic", "war", "military", "political"]
        if any(k in prompt.lower() for k in keywords):
            score += 0.2
        
        # 视觉元素评分
        visual_words = ["aerial", "close-up", "wide shot", "pan", "zoom"]
        if any(v in prompt.lower() for v in visual_words):
            score += 0.3
        
        # 质量标签评分
        quality_count = sum(1 for qt in QUALITY_TAGS if qt in prompt.lower())
        score += min(quality_count * 0.1, 0.2)
        
        # 多样性评分
        if len(set(prompt.split(','))) >= 5:
            score += 0.1
        
        return min(score, 1.0)


# 全局实例
prompt_engine = PromptEngine()


def get_prompt_engine() -> PromptEngine:
    """获取提示词引擎实例"""
    return prompt_engine
