"""UI event handlers mixin - model selection, config, dependencies, etc."""
import os
import re
import sys
import json
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

from video_generator.config import Config, get_http_session
from video_generator.ollama_client import (
    is_ollama_available,
    set_ollama_available,
    check_ollama_available,
    get_available_models,
    try_start_ollama_service,
)
from video_generator.app_state import (
    PERFORMANCE_MONITOR_AVAILABLE,
    psutil,
    GPUtil,
)

class UIHandlersMixin:
    def _check_api_heartbeat(self):
        """周期性检测API连接状态，发现恢复时自动连接并提示"""
        try:
            sd_api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL
            sd_connected = getattr(self, '_sd_api_connected', False)
            
            if not sd_connected:
                try:
                    resp = get_http_session().get(f"{sd_api_url}/sdapi/v1/sd-models", timeout=5)
                    if resp.status_code == 200:
                        self._sd_api_connected = True
                        if hasattr(self, 'sd_api_status_var') and hasattr(self, 'root') and self.root:
                            self.root.after(0, lambda: self.sd_api_status_var.set("✅ 已连接"))
                        if hasattr(self, 'sd_api_status_label') and hasattr(self, 'root') and self.root:
                            self.root.after(0, lambda: self.sd_api_status_label.config(foreground="green"))
                        self.log("✅ SD API 已自动连接")
                        if hasattr(self, 'root') and self.root:
                            self.root.after(0, self._update_model_dropdown)
                except Exception:
                    pass
            
            ollama_connected = is_ollama_available()
            if not ollama_connected:
                if check_ollama_available():
                    set_ollama_available(True)
                    self.log("✅ Ollama服务已自动连接")
        except Exception:
            pass
    

    def auto_connect_ollama(self):
        """启动时自动检测并连接Ollama服务 - 失败时弹窗提醒"""
        try:
            if check_ollama_available():
                set_ollama_available(True)
                self.log("✅ Ollama服务已连接")
                return

            if try_start_ollama_service():
                set_ollama_available(True)
                self.log("✅ Ollama服务已启动并连接")
                return

            set_ollama_available(False)
            self.log("❌ Ollama服务连接失败")
            self.root.after(0, lambda: messagebox.showwarning(
                "Ollama服务未连接",
                "Ollama大模型服务未运行，且自动启动失败！\n\n"
                "分镜生成和提示词生成需要Ollama服务支持。\n\n"
                "请手动启动Ollama后重试，或在高级设置中检查Ollama模型配置。"
            ))
        except Exception as e:
            set_ollama_available(False)
            self.log(f"❌ Ollama连接失败: {e}")
            self.root.after(0, lambda: messagebox.showwarning(
                "Ollama服务异常",
                f"Ollama服务连接异常：{e}\n\n"
                "分镜生成和提示词生成需要Ollama服务支持。"
            ))
    

    def update_model_list(self):
        """更新模型列表，自动检测本地已安装的Ollama模型"""
        
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
        
        # 自动检测并启动Ollama服务
        ollama_connected = False
        if check_ollama_available():
            set_ollama_available(True)
            ollama_connected = True
        else:
            if try_start_ollama_service():
                set_ollama_available(True)
                ollama_connected = True
        
        # 尝试获取本地已安装的Ollama模型
        try:
            if is_ollama_available() or ollama_connected:
                available_models = get_available_models()
                model_names = available_models
                    
                if model_names:
                    recommended_models = []
                    for model in model_names:
                        if any(keyword in model.lower() for keyword in ["qwen", "gemma", "deepseek", "llama", "mistral"]):
                            recommended_models.append((model, True))
                        else:
                            recommended_models.append((model, False))
                    
                    for model, is_recommended in recommended_models:
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
                    default_models = ["qwen2.5:7b", "gemma3:4b", "deepseek-r1:8b", "qwen2.5:3b", "gemma3:1b", "mistral", "llama3"]
                    for model in default_models:
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
            api_url = self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL
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
    

    def _clean_style_output(self, raw_output):
        """清洗风格描述输出，只保留关键词"""
        
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
        confirm_msg += f"SD API地址: {self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL}\n"
        confirm_msg += f"Ollama模型: {self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b'}\n"
        confirm_msg += f"语音模型: {self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else 'medium'}\n"
        confirm_msg += f"配置模式: {self.llm_config_preset_var.get() if hasattr(self, 'llm_config_preset_var') else '质量优先'}\n"
        confirm_msg += f"动画效果: {self.animation_var.get() if hasattr(self, 'animation_var') else '无'}\n"
        confirm_msg += f"过渡效果: {self.transition_var.get() if hasattr(self, 'transition_var') else '硬切'}\n"
        confirm_msg += f"分镜线程: {self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16}\n"
        confirm_msg += f"提示词线程: {self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else 4}\n"

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
        
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    

    def _get_translation_from_dict(self, word):
        """从字典获取翻译（支持动态扩展）"""
        # 核心常用词汇（高频词，优先加载）
        core_translations = {
            # === 城市/地点 ===
            '东京': 'Tokyo', '北京': 'Beijing', '上海': 'Shanghai', '纽约': 'New York',
            '伦敦': 'London', '巴黎': 'Paris', '首尔': 'Seoul', '大阪': 'Osaka',
            
            # === 人物/性别 ===
            '女性': 'woman', '男性': 'man', '年轻人': 'young people', '老人': 'elderly',
            '儿童': 'children', '学生': 'student', '工人': 'worker',
            
            # === 经济/社会 ===
            '零工经济': 'gig economy', '社会问题': 'social issues', '房租': 'rent',
            '物价': 'price', '低薪': 'low salary', '失业': 'unemployment',
            '经济': 'economy', '市场': 'market',
            
            # === 科技/互联网 ===
            '社交软件': 'social media', '互联网': 'internet', '智能手机': 'smartphone',
            '人工智能': 'AI',
            
            # === 生活/文化 ===
            '饮食': 'food', '时尚': 'fashion', '娱乐': 'entertainment', '旅游': 'travel',
            '教育': 'education', '医疗': 'medical', '健康': 'health',
            
            # === 政治/国际 ===
            '政府': 'government', '政策': 'policy', '战争': 'war', '和平': 'peace', '冲突': 'conflict',
        }
        
        # 先查核心字典
        if word in core_translations:
            return core_translations[word]
        
        # 再查动态缓存（运行时学习的词汇）
        if hasattr(self, '_translation_cache'):
            return self._translation_cache.get(word)
        
        return None
    

    def _split_by_words_with_punctuation(self, words, sentence_endings):
        """使用词级时间戳精确切分句子，确保音画同步
        
        Args:
            words: 词列表，每个词包含 'word', 'start', 'end'
            sentence_endings: 句子结束标点的正则表达式
        
        Returns:
            切分后的片段列表
        """
        
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
            except (ImportError, TypeError, OSError) as e:
                # TypeError/OSError: Python 3.14+ 与 whisper 包不兼容 (ctypes.CDLL(None) 失败)
                self.log(f"⚠️ {dep} 加载失败: {type(e).__name__}: {str(e)[:60]}")
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
        """检查并更新依赖项（子线程执行，避免阻塞GUI）"""
        def _worker():
            self._check_and_update_dependencies_impl()
        threading.Thread(target=_worker, daemon=True).start()
    

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


    def system_check(self):
        """系统检查"""
        self.log("正在进行系统检查...")
        # 检查依赖项
        self.check_dependencies()
        # 检查SD API连接
        # self.check_sd_api_connection()
        self.log("✅ 系统检查完成")
    

    @staticmethod
    def _open_folder(path):
        """跨平台打开文件夹"""
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
        except Exception:
            pass


    def open_output_folder(self):
        """打开输出文件夹"""
        output_folder = os.path.join(self.base_dir, "output_project")
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        self._open_folder(output_folder)
    

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
            traceback.print_exc()
    

    def load_config(self):
        """加载配置"""
        try:
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
                
                # 加载Whisper模型设置
                if 'whisper_model' in config and hasattr(self, 'whisper_model_var'):
                    self.whisper_model_var.set(config['whisper_model'])
                
                # 集中显示已加载的配置
                ollama_model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b'
                whisper_model = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else 'medium'
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
                'animation': self.animation_var.get() if hasattr(self, 'animation_var') else '无',
                'thread_count': self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16,
                'prompt_thread_count': self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log("✅ 配置保存完成")
        except Exception as e:
            self.log(f"⚠️ 配置保存失败: {e}")

