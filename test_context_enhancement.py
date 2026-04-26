#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试上下文增强的提示词生成功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# 模拟必要的导入和类
class MockVideoGenerator:
    def __init__(self):
        self._shot_texts_for_context = [
            "今天天气真好",
            "我们去公园玩",
            "看到很多花朵",
            "孩子们在欢笑",
            "夕阳西下时分"
        ]

    def _generate_prompt_with_llm(self, dubbing, content_type="general", prompt_type="SD提示词",
                                  core_theme="", visual_tone="", theme_elements=None,
                                  visual_style="", original_dubbing="", full_text="今天天气真好，我们去公园玩，看到很多花朵，孩子们在欢笑，夕阳西下时分"):
        """测试上下文增强的提示词生成"""
        if theme_elements is None:
            theme_elements = []

        # 模拟上下文生成
        context_hint = ""
        if hasattr(self, '_shot_texts_for_context') and isinstance(dubbing, str):
            shot_texts = self._shot_texts_for_context
            try:
                idx = shot_texts.index(dubbing) if dubbing in shot_texts else -1
                if idx >= 0:
                    # 添加全局内容摘要
                    if full_text and len(full_text) > 50:
                        content_summary = full_text[:200] + "..." if len(full_text) > 200 else full_text
                        context_hint += f"整体内容摘要: {content_summary}\n"

                    # 添加前文上下文
                    prev_texts = [shot_texts[j] for j in range(max(0, idx-3), idx)]
                    if prev_texts:
                        context_hint += f"前文上下文: {' | '.join(prev_texts)}\n"

                    # 添加后文上下文
                    next_texts = [shot_texts[j] for j in range(idx+1, min(len(shot_texts), idx+4))]
                    if next_texts:
                        context_hint += f"后文上下文: {' | '.join(next_texts)}\n"

                    # 添加位置信息
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
            except Exception as e:
                print(f"上下文生成错误: {e}")

        # 模拟生成提示词
        if context_hint:
            print("=== 上下文信息 ===")
            print(context_hint)
            print("=== 当前配音 ===")
            print(f"当前配音：{dubbing}")
            print("=== 生成的提示词 ===")
            # 这里应该调用实际的LLM，但我们只是模拟
            mock_prompt = f"masterpiece, best quality, ultra detailed, 8k, photorealistic, {dubbing.replace(' ', ', ')}, scenic landscape, cinematic lighting, documentary style, film grain texture"
            print(mock_prompt)
            return mock_prompt
        else:
            return f"masterpiece, best quality, ultra detailed, 8k, photorealistic, {dubbing}, cinematic lighting, documentary style, film grain texture"

# 测试函数
def test_context_enhancement():
    print("测试上下文增强的提示词生成功能")
    print("=" * 50)

    generator = MockVideoGenerator()

    # 测试中间片段（应该有前文和后文上下文）
    print("\n1. 测试中间片段 '看到很多花朵':")
    result1 = generator._generate_prompt_with_llm("看到很多花朵", full_text="今天天气真好，我们去公园玩，看到很多花朵，孩子们在欢笑，夕阳西下时分")
    print(f"结果: {result1}")

    # 测试开头片段（只有后文上下文）
    print("\n2. 测试开头片段 '今天天气真好':")
    result2 = generator._generate_prompt_with_llm("今天天气真好", full_text="今天天气真好，我们去公园玩，看到很多花朵，孩子们在欢笑，夕阳西下时分")
    print(f"结果: {result2}")

    # 测试结尾片段（只有前文上下文）
    print("\n3. 测试结尾片段 '夕阳西下时分':")
    result3 = generator._generate_prompt_with_llm("夕阳西下时分", full_text="今天天气真好，我们去公园玩，看到很多花朵，孩子们在欢笑，夕阳西下时分")
    print(f"结果: {result3}")

    print("\n测试完成！")

if __name__ == "__main__":
    test_context_enhancement()