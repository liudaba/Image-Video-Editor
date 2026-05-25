"""UI event handlers mixin - model selection, config, dependencies, etc."""
import os
import re
import sys
import json
import time
import threading
import subprocess
import tkinter as tk
from video_generator.mixins.logging import safe_print_exc
from tkinter import ttk, messagebox

from video_generator.config import (
    Config, get_http_session, validate_image_size, sanitize_url,
    RE_BOLD, RE_ITALIC, RE_NEWLINES, RE_WHITESPACE,
    RE_COLON_SPLIT, RE_LEADING_PUNCT, RE_TRAILING_PUNCT,
)
from video_generator.ollama_client import (
    is_ollama_available,
    set_ollama_available,
    check_ollama_available,
    LLMConfig,
    get_available_models,
    try_start_ollama_service,
    is_cloud_llm_active,
    is_cloud_image_active,
)
from video_generator.multi_model import llm_optimizer
from video_generator.app_state import (
    psutil,
    GPUtil,
)

class UIHandlersMixin:
    def _check_api_heartbeat(self):
        """周期性检测API连接状态，发现恢复时自动连接，发现断开时通知用户"""
        try:
            if not is_cloud_image_active():
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
                else:
                    try:
                        resp = get_http_session().get(f"{sd_api_url}/sdapi/v1/sd-models", timeout=3)
                        if resp.status_code != 200:
                            self._sd_api_connected = False
                            if hasattr(self, 'sd_api_status_var') and hasattr(self, 'root') and self.root:
                                self.root.after(0, lambda: self.sd_api_status_var.set("❌ 已断开"))
                            if hasattr(self, 'sd_api_status_label') and hasattr(self, 'root') and self.root:
                                self.root.after(0, lambda: self.sd_api_status_label.config(foreground="red"))
                            self.log("⚠️ SD API 连接已断开")
                    except Exception:
                        self._sd_api_connected = False
                        if hasattr(self, 'sd_api_status_var') and hasattr(self, 'root') and self.root:
                            self.root.after(0, lambda: self.sd_api_status_var.set("❌ 已断开"))
                        if hasattr(self, 'sd_api_status_label') and hasattr(self, 'root') and self.root:
                            self.root.after(0, lambda: self.sd_api_status_label.config(foreground="red"))
                        self.log("⚠️ SD API 连接已断开")

            ollama_connected = is_ollama_available()
            if not ollama_connected:
                if not is_cloud_llm_active():
                    if check_ollama_available():
                        set_ollama_available(True)
                        self.log("✅ Ollama服务已自动连接")
            else:
                if not is_cloud_llm_active():
                    if not check_ollama_available():
                        set_ollama_available(False)
                        self.log("⚠️ Ollama服务已断开")
        except Exception:
            pass
    

    def auto_connect_ollama(self, silent=False):
        try:
            try:
                from video_generator.cloud_llm_client import is_cloud_llm_active
                if is_cloud_llm_active():
                    if not silent:
                        self.log("☁️ 云端大模型已启用，无需连接本地Ollama")
                    return
            except ImportError:
                pass

            if check_ollama_available():
                set_ollama_available(True)
                if not silent:
                    self.log("✅ Ollama服务已连接")
                self.update_model_list()
                return

            if not silent:
                self.log("⚠️ Ollama服务未运行，正在自动启动...")
            if try_start_ollama_service():
                set_ollama_available(True)
                if not silent:
                    self.log("✅ Ollama服务已自动启动并连接")
                self.update_model_list()
                return

            set_ollama_available(False)
            if not silent:
                self.log("❌ Ollama服务自动启动失败")
            self.update_model_list()
            if not silent:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Ollama服务未连接",
                    "Ollama大模型服务未运行，且自动启动失败！\n\n"
                    "分镜生成和提示词生成需要Ollama服务支持。\n\n"
                    "请手动启动Ollama后重试，或在高级设置中启用云端大模型。"
                ))
        except Exception as e:
            set_ollama_available(False)
            if not silent:
                self.log("❌ Ollama连接失败，请检查Ollama是否已安装并运行")
                safe_print_exc()
            self.update_model_list()
            if not silent:
                self.root.after(0, lambda: messagebox.showwarning(
                    "Ollama服务异常",
                    "Ollama服务连接异常，无法与Ollama通信。\n\n"
                    "分镜生成和提示词生成需要Ollama服务支持。\n\n"
                    "请在高级设置中启用云端大模型，或检查Ollama是否已安装并正常运行。"
                ))

    def _detect_gpu_info_async(self):
        def _detect():
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=gpu_name,memory.total", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    line = result.stdout.strip().split("\n")[0]
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        gpu_name = parts[0]
                        gpu_mem = float(parts[1]) / 1024
                        self._gpu_info = f"{gpu_name} ({gpu_mem:.1f}GB, CUDA)"
                        return
            except Exception:
                pass
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_name = result.stdout.strip().split("\n")[0].strip()
                    self._gpu_info = f"{gpu_name} (CUDA)"
            except Exception:
                pass
        threading.Thread(target=_detect, daemon=True).start()
    

    def update_model_list(self):
        """更新模型列表，自动检测本地已安装的Ollama模型"""
        
        _FALLBACK_MODEL_SIZES = {
            "qwen3.5:4b": "3.2GB",
            "qwen3:8b": "4.9GB",
            "qwen3:4b": "2.3GB",
            "qwen2.5:7b": "4.4GB",
            "qwen2.5:3b": "2.0GB",
            "gemma4:latest": "8.9GB",
            "gemma4:e4b": "8.9GB",
            "gemma4:e2b": "6.7GB",
            "gemma3:4b": "3.1GB",
            "deepseek-r1:8b": "5.2GB",
            "llama3.2:3b": "2.0GB",
            "mistral": "4.1GB",
            "llama3": "4.7GB",
        }
        
        _api_model_sizes = {}
        try:
            from video_generator.ollama_client import is_ollama_available
            if is_ollama_available():
                resp = get_http_session().get(
                    f"{Config.OLLAMA_BASE_URL}/api/tags",
                    timeout=Config.API_TIMEOUT_SHORT
                )
                if resp.status_code == 200:
                    for m in resp.json().get("models", []):
                        name = m.get("name", "")
                        size_bytes = m.get("size", 0)
                        if name and size_bytes:
                            gb = size_bytes / (1024 ** 3)
                            _api_model_sizes[name] = f"{gb:.1f}GB"
        except Exception:
            pass
        
        def get_model_label(model_name):
            if model_name in _api_model_sizes:
                return f"{model_name}  {_api_model_sizes[model_name]}"
            for key, size in _FALLBACK_MODEL_SIZES.items():
                if key in model_name:
                    return f"{model_name}  {size}"
            return model_name
        
        ollama_connected = False
        if is_ollama_available():
            ollama_connected = True
        elif check_ollama_available():
            set_ollama_available(True)
            ollama_connected = True
        else:
            if try_start_ollama_service():
                set_ollama_available(True)
                ollama_connected = True
        
        model_labels = []
        model_ids = []
        try:
            if is_ollama_available() or ollama_connected:
                available_models = get_available_models(force_refresh=True)
                if available_models:
                    for model in available_models:
                        model_labels.append(get_model_label(model))
                        model_ids.append(model)
                else:
                    for model in ["qwen3.5:4b", "qwen3:4b", "gemma3:4b", "deepseek-r1:8b"]:
                        model_labels.append(get_model_label(model))
                        model_ids.append(model)
            else:
                for model in ["qwen3.5:4b", "qwen3:4b", "gemma3:4b", "deepseek-r1:8b"]:
                    model_labels.append(get_model_label(model))
                    model_ids.append(model)
        except Exception as e:
            error_msg = str(e)
            self.log(f"获取Ollama模型列表失败: {error_msg}")
            for model in ["qwen3.5:4b", "qwen3:4b", "gemma3:4b", "deepseek-r1:8b"]:
                model_labels.append(get_model_label(model))
                model_ids.append(model)
        
        self._ollama_model_ids = model_ids
        
        if hasattr(self, '_ollama_listbox') and self._ollama_listbox.winfo_exists():
            self._ollama_listbox.delete(0, tk.END)
            for label in model_labels:
                self._ollama_listbox.insert(tk.END, label)
            self._ollama_listbox.config(height=min(len(model_labels), 15))
            current = self.ollama_model_var.get()
            if current:
                for i, mid in enumerate(model_ids):
                    if mid == current:
                        self._ollama_listbox.selection_set(i)
                        self._ollama_listbox.see(i)
                        break

    def _toggle_ollama_listbox(self):
        """切换Ollama模型列表的展开/收起"""
        if self._ollama_listbox_visible:
            self._ollama_listbox_frame.pack_forget()
            self._ollama_listbox_visible = False
        else:
            self.update_model_list()
            count = self._ollama_listbox.size()
            self._ollama_listbox.config(height=min(count, 15))
            self._ollama_listbox_frame.pack(fill=tk.X, after=self._ollama_btn, pady=1)
            self._ollama_listbox_visible = True

    def _on_ollama_listbox_select(self, event=None):
        """Listbox选择模型后的回调"""
        selection = self._ollama_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if 0 <= idx < len(self._ollama_model_ids):
            model = self._ollama_model_ids[idx]
            self.ollama_model_var.set(model)
            self.log(f"✅ 已选择Ollama模型: {model}")
        self._ollama_listbox_frame.pack_forget()
        self._ollama_listbox_visible = False


    def toggle_advanced_settings(self):
        """打开/关闭高级设置窗口"""
        if self.advanced_window and self.advanced_window.winfo_exists():
            try:
                self._sync_all_settings()
                self.save_config()
                self._print_current_settings()
            except Exception:
                pass
            self.advanced_window.destroy()
            self.advanced_window = None
        else:
            self.advanced_window = tk.Toplevel(self.root)
            self.advanced_window.title("⚙️ 高级设置")
            self.advanced_window.geometry("1050x640")
            self.advanced_window.minsize(900, 560)
            self.advanced_window.resizable(True, True)
            self.advanced_window.configure(bg="#2a2d35")
            
            self.advanced_window.protocol("WM_DELETE_WINDOW", self._on_advanced_window_close)
            
            main_frame = ttk.Frame(self.advanced_window, padding=4, style="Adv.TFrame")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            main_frame.columnconfigure(0, weight=1, uniform="col")
            main_frame.columnconfigure(1, weight=1, uniform="col")
            main_frame.columnconfigure(2, weight=1, uniform="col")
            for i in range(4):
                main_frame.rowconfigure(i, weight=1, uniform="row")
            main_frame.rowconfigure(4, weight=0, minsize=10)
            
            self._adv_panels = {}
            
            self._adv_panels["draw"] = ttk.Frame(main_frame)
            self._adv_panels["draw"].grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["video"] = ttk.Frame(main_frame)
            self._adv_panels["video"].grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["cloud_llm"] = ttk.Frame(main_frame)
            self._adv_panels["cloud_llm"].grid(row=0, column=2, rowspan=2, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["style"] = ttk.Frame(main_frame)
            self._adv_panels["style"].grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["thread"] = ttk.Frame(main_frame)
            self._adv_panels["thread"].grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["sd_api"] = ttk.Frame(main_frame)
            self._adv_panels["sd_api"].grid(row=2, column=0, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["prompt"] = ttk.Frame(main_frame)
            self._adv_panels["prompt"].grid(row=2, column=1, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["cloud_asr"] = ttk.Frame(main_frame)
            self._adv_panels["cloud_asr"].grid(row=2, column=2, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["optimize"] = ttk.Frame(main_frame)
            self._adv_panels["optimize"].grid(row=3, column=0, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["theme"] = ttk.Frame(main_frame)
            self._adv_panels["theme"].grid(row=3, column=1, sticky="nsew", padx=2, pady=2)
            
            self._adv_panels["cloud_img"] = ttk.Frame(main_frame)
            self._adv_panels["cloud_img"].grid(row=3, column=2, sticky="nsew", padx=2, pady=2)
            
            btn_frame = ttk.Frame(main_frame)
            btn_frame.grid(row=4, column=0, columnspan=3, sticky="ew", padx=4, pady=(2, 2))
            style = ttk.Style()
            style.configure("LargeGreen.TButton", font=('Microsoft YaHei', 13, 'bold'), padding=(10, 10))
            btn_apply = ttk.Button(btn_frame, text="✅ 应用设置", command=self.apply_advanced_settings, style="LargeGreen.TButton")
            btn_apply.pack(fill=tk.X, padx=5)
            
            self.setup_advanced_panel_content(self._adv_panels)
    

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
            thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 8
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
            print(f"  SD API地址:   {sanitize_url(api_url)}")
            print(f"  Ollama模型:   {ollama_model}")
            print(f"  LLM配置:      {llm_preset}")
            print(f"  Whisper模型:  {whisper_model}")
            print(f"  提示词类型:   {prompt_type}")
            print(f"  动画效果:     {animation}")
            print(f"  过渡效果:     {transition}")
            print(f"  分镜创建线程: {thread_count}")
            batch_size = self.batch_size_var.get() if hasattr(self, 'batch_size_var') else 2
            print(f"  分镜批处理:   {batch_size}")
            min_shot_dur = self.min_shot_duration_var.get() if hasattr(self, 'min_shot_duration_var') else 4.0
            print(f"  最短分镜时长: {min_shot_dur:.1f}秒")
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
            self._sync_all_settings()
            self.save_config()
            self._print_current_settings()
        except Exception:
            pass
        if self.advanced_window and self.advanced_window.winfo_exists():
            self.advanced_window.destroy()
        self.advanced_window = None
    

    def toggle_model_dropdown(self):
        """刷新Ollama模型列表"""
        self.update_model_list()


    def select_ollama_model(self, model):
        """选择Ollama模型（兼容旧调用）"""
        self.ollama_model_var.set(model)
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
        
        if prompt_type != "SD提示词" and hasattr(self, 'style_dropdown_frame') and self.style_dropdown_visible:
            self.style_dropdown_frame.pack_forget()
            self.style_dropdown_visible = False

    def _update_min_shot_label(self):
        """更新最短分镜时长显示标签"""
        try:
            if hasattr(self, 'min_shot_duration_var') and hasattr(self, '_min_shot_label'):
                val = self.min_shot_duration_var.get()
                self._min_shot_label.config(text=f"{val:.1f}s")
        except Exception:
            pass
    

    _PROGRESS_THROTTLE_SEC = 0.3

    def update_task_progress(self, message, progress=None):
        """更新任务进度（带节流，避免UI事件洪水）"""
        now = time.time()
        if not hasattr(self, '_last_progress_time'):
            self._last_progress_time = 0

        def _update():
            try:
                if hasattr(self, 'lbl_progress'):
                    self.lbl_progress.config(text=message)
                if hasattr(self, 'progress_var') and progress is not None:
                    self.progress_var.set(progress)
                self._last_progress_time = time.time()
            except Exception:
                pass

        if hasattr(self, 'root') and self.root:
            _is_critical = any(kw in message for kw in ['取消', '失败', '错误', '完成', '就绪'])
            if _is_critical:
                self.root.after(0, _update)
            else:
                elapsed = now - self._last_progress_time
                delay = max(0, int((self._PROGRESS_THROTTLE_SEC - elapsed) * 1000))
                self.root.after(delay, _update)
    
    
    

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
        confirm_msg += f"SD API地址: {sanitize_url(self.sd_api_url_var.get() if hasattr(self, 'sd_api_url_var') else Config.SD_API_BASE_URL)}\n"
        confirm_msg += f"Ollama模型: {self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else 'gemma3:4b'}\n"
        confirm_msg += f"语音模型: {self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else 'medium'}\n"
        confirm_msg += f"配置模式: {self.llm_config_preset_var.get() if hasattr(self, 'llm_config_preset_var') else '质量优先'}\n"
        confirm_msg += f"动画效果: {self.animation_var.get() if hasattr(self, 'animation_var') else '无'}\n"
        confirm_msg += f"过渡效果: {self.transition_var.get() if hasattr(self, 'transition_var') else '硬切'}\n"
        confirm_msg += f"分镜线程: {self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 8}\n"
        confirm_msg += f"分镜批处理: {self.batch_size_var.get() if hasattr(self, 'batch_size_var') else 2}\n"
        min_shot_dur = self.min_shot_duration_var.get() if hasattr(self, 'min_shot_duration_var') else 4.0
        confirm_msg += f"最短分镜时长: {min_shot_dur:.1f}秒\n"

        # 显示确认对话框
        confirmed = messagebox.askyesno("确认设置", confirm_msg)

        if confirmed:
            msg = f"设置已应用:\n模型: {model}\n提示词类型: {prompt_type}\n尺寸: {width}x{height}"
            if custom_theme:
                msg += f"\n核心主题: {custom_theme}"
            if custom_tone:
                msg += f"\n视觉基调: {custom_tone}"
            if hasattr(self, 'min_shot_duration_var'):
                msg += f"\n最短分镜时长: {self.min_shot_duration_var.get():.1f}秒"
            self._sync_all_settings()
            self.log(msg)
            self.save_config()
            self._print_current_settings()
            messagebox.showinfo("成功", "设置已成功应用！\n系统将按照您的选择执行相应功能。")
            self.toggle_advanced_settings()
        else:
            # 取消应用
            self.log("⚠️ 设置应用已取消")
    

    def _sync_all_settings(self):
        """同步所有高级设置面板变量到运行时状态（无需点击应用按钮）"""
        try:
            if hasattr(self, 'min_shot_duration_var'):
                self.MIN_SHOT_DURATION = self.min_shot_duration_var.get()
        except Exception:
            pass
        try:
            if hasattr(self, '_apply_cloud_llm_config'):
                self._apply_cloud_llm_config()
        except Exception:
            pass

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
                if hasattr(self, 'model_combo'):
                    def update_ui():
                        try:
                            if sd_models:
                                labeled_models = self._add_model_type_labels(sd_models)
                                models = ["使用当前模型"] + labeled_models
                            else:
                                models = list(self._default_models)
                                current = self.model_var.get()
                                if current and current not in models:
                                    models.append(current)
                            self.model_combo['values'] = models
                        except Exception:
                            pass
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, update_ui)
            except Exception:
                pass
        
        thread = threading.Thread(target=_fetch_and_update, daemon=True)
        thread.start()
    
    def _refresh_model_list(self):
        """手动刷新模型列表（用户点击刷新按钮时调用）"""
        if hasattr(self, '_model_refresh_btn'):
            self._model_refresh_btn.config(state='disabled')
        
        self.log("🔄 正在刷新模型列表...")
        
        def _do_refresh():
            try:
                sd_models = self._get_sd_models_from_api()
                def update_ui():
                    try:
                        if sd_models:
                            labeled_models = self._add_model_type_labels(sd_models)
                            models = ["使用当前模型"] + labeled_models
                            self.model_combo['values'] = models
                            self.log(f"✅ 模型列表已刷新，共 {len(sd_models)} 个模型")
                        else:
                            models = list(self._default_models)
                            current = self.model_var.get()
                            if current and current not in models:
                                models.append(current)
                            self.model_combo['values'] = models
                            self.log("⚠️ 未获取到模型列表，请检查SD API连接")
                    except Exception as e:
                        self.log(f"⚠️ 刷新模型列表失败: {str(e)[:60]}")
                    finally:
                        if hasattr(self, '_model_refresh_btn'):
                            self._model_refresh_btn.config(state='normal')
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            except Exception as e:
                self.log(f"⚠️ 刷新模型列表失败: {str(e)[:60]}")
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, lambda: self._model_refresh_btn.config(state='normal') if hasattr(self, '_model_refresh_btn') else None)
        
        thread = threading.Thread(target=_do_refresh, daemon=True)
        thread.start()

    def _add_model_type_labels(self, model_names):
        """为模型名称添加类型标签
        
        例如: "Flux Dev" → "[Flux] Flux Dev"
              "dreamshaperXL" → "[SDXL] dreamshaperXL"
              "realisticVisionV51" → "[SD1.5] realisticVisionV51"
        """
        from video_generator.model_profiles import get_model_type_label
        labeled = []
        for name in model_names:
            label = get_model_type_label(name)
            labeled.append(f"{label} {name}")
        return labeled


    def _update_model_dropdown(self):
        """更新模型下拉菜单（在 SD API 连接成功后调用）- 异步执行避免阻塞UI"""
        if not hasattr(self, 'model_combo'):
            return

        def _do_update():
            try:
                sd_models = self._get_sd_models_from_api()
                def update_ui():
                    try:
                        if sd_models:
                            labeled_models = self._add_model_type_labels(sd_models)
                            models = ["使用当前模型"] + labeled_models
                            self.model_combo['values'] = models
                            if self.model_var.get() in ["Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3", "DALL·E 3"]:
                                self.model_var.set("使用当前模型")
                        else:
                            models = list(self._default_models)
                            current = self.model_var.get()
                            if current and current not in models:
                                models.append(current)
                            self.model_combo['values'] = models
                    except Exception:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            except Exception:
                pass

        threading.Thread(target=_do_update, daemon=True).start()
    

    def close_sd_api_connection(self):
        """关闭 SD API 连接"""
        self.log("正在关闭 SD API 连接...")

        self._sd_api_connected = False

        if hasattr(self, 'sd_api_status_var'):
            self.sd_api_status_var.set("❌ 未连接")
        if hasattr(self, 'sd_api_status_label'):
            self.sd_api_status_label.config(foreground="red")

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
        lightweight_deps = [
            ("requests", "pip install requests", None, True),
            ("PIL", "pip install Pillow", None, True),
            ("numpy", "pip install numpy", None, True),
            ("moviepy", "pip install moviepy", None, True),
        ]
        heavy_deps = [
            ("whisper", "pip install openai-whisper", "load_model", False),
        ]

        results = {}
        def _check_one(dep, install_cmd, required_attr, is_core):
            try:
                module = __import__(dep)
                if required_attr and not hasattr(module, required_attr):
                    results[dep] = ("incomplete", is_core, install_cmd)
                else:
                    results[dep] = ("ok", is_core, install_cmd)
            except (ImportError, TypeError, OSError) as e:
                self.log(f"     ⚠️ {dep} 导入失败: {type(e).__name__}: {e}")
                results[dep] = ("missing", is_core, install_cmd)
            except Exception as e:
                self.log(f"     ⚠️ {dep} 导入异常: {type(e).__name__}: {e}")
                results[dep] = ("missing", is_core, install_cmd)

        def _check_lightweight(dep, install_cmd, is_core):
            import importlib.util
            spec = importlib.util.find_spec(dep)
            if spec is not None:
                results[dep] = ("ok", is_core, install_cmd)
            else:
                results[dep] = ("missing", is_core, install_cmd)

        threads = []
        for dep, install_cmd, required_attr, is_core in lightweight_deps:
            t = threading.Thread(target=_check_one, args=(dep, install_cmd, required_attr, is_core))
            t.start()
            threads.append(t)
        for dep, install_cmd, required_attr, is_core in heavy_deps:
            t = threading.Thread(target=_check_lightweight, args=(dep, install_cmd, is_core))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=10)

        missing_core = []
        all_deps = lightweight_deps + heavy_deps
        for dep, install_cmd, required_attr, is_core in all_deps:
            if dep not in results:
                if is_core:
                    missing_core.append((dep, install_cmd))
                continue
            status, _, _ = results[dep]
            if status == "incomplete":
                if is_core:
                    self.log(f"     ⚠️ {dep} 已安装但功能不完整（缺少 {required_attr}）")
                    missing_core.append((dep, install_cmd))
                else:
                    self.log(f"     ⚠️ {dep} 已安装但功能不完整，可使用云端语音识别替代")
            elif status == "missing":
                if is_core:
                    self.log(f"     ❌ {dep} 未安装，请执行: {install_cmd}")
                    missing_core.append((dep, install_cmd))
                else:
                    self.log(f"     ⚠️ {dep} 未安装，可使用云端语音识别替代")
        
        if missing_core:
            self.log("❌ 缺少核心依赖项")
            msg = "缺少以下核心依赖项:\n"
            for dep, install_cmd in missing_core:
                msg += f"- {dep}: {install_cmd}\n"
            if hasattr(self, 'root') and self.root:
                self.root.after(0, lambda: messagebox.showwarning("警告", msg))
            return False
        else:
            return True




    def monitor_performance(self):
        """监控系统性能 - 优化版（非阻塞）"""
        try:
            # 首次调用cpu_percent需要间隔，之后可以非阻塞
            if psutil:
                psutil.cpu_percent(interval=None)  # 初始化
            
            update_interval = 0
            gpu_memory_percent = 0  # 更新计数器
            
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
                        except Exception:
                            gpu_memory_percent = 0
                    
                    try:
                        if update_interval % 2 == 0:
                            _cpu = cpu_usage
                            _mem = memory_usage
                            _gpu = gpu_memory_percent
                            _mem_d = f"{memory_used} MB / {memory_total} MB"
                            def _update_perf_ui():
                                try:
                                    if hasattr(self, 'cpu_label') and self.cpu_label.winfo_exists():
                                        self.cpu_label.config(text=f"{_cpu:.1f}%")
                                    if hasattr(self, 'memory_label') and self.memory_label.winfo_exists():
                                        self.memory_label.config(text=f"{_mem:.1f}%")
                                    if hasattr(self, 'gpu_label') and self.gpu_label.winfo_exists():
                                        self.gpu_label.config(text=f"{_gpu:.1f}%")
                                    if hasattr(self, 'memory_detail_label') and self.memory_detail_label.winfo_exists():
                                        self.memory_detail_label.config(text=_mem_d)
                                except tk.TclError:
                                    pass
                            if hasattr(self, 'root') and self.root:
                                self.root.after(0, _update_perf_ui)
                    except tk.TclError:
                        break
                    
                    update_interval += 1
                    # 智能调整监控间隔
                    self._perf_monitor_interval = 2.0 if getattr(self, "task_running", False) else 5.0
                
                time.sleep(self._perf_monitor_interval)  # 智能间隔：空闲5s，任务中2s
        except Exception:
            pass


    def system_check(self):
        self.check_dependencies()
    

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
        output_folder = os.path.join(self.base_dir, "output_project")
        os.makedirs(output_folder, exist_ok=True)
        self._open_folder(output_folder)

    def open_trash_browser(self):
        if hasattr(self, '_trash_window') and self._trash_window is not None:
            try:
                self._trash_window.focus_force()
                return
            except tk.TclError:
                self._trash_window = None

        self._trash_window = tk.Toplevel(self.root)
        self._trash_window.title("垃圾桶 - 已删除文件")
        self._trash_window.geometry("960x640")
        self._trash_window.configure(bg="#1e1e1e")
        self._trash_window.transient(self.root)

        header = tk.Frame(self._trash_window, bg="#252526", height=44)
        header.pack(fill=tk.X, padx=0, pady=0)
        header.pack_propagate(False)

        tk.Label(header, text="  🗑️ 垃圾桶 - 已删除的文件", font=("Microsoft YaHei", 14, "bold"),
                 bg="#252526", fg="#d4d4d4").pack(side=tk.LEFT, padx=8, pady=6)

        btn_empty = ttk.Button(header, text="清空垃圾桶", command=self._empty_trash_and_refresh, style="Small.TButton")
        btn_empty.pack(side=tk.RIGHT, padx=8, pady=6)

        btn_refresh = ttk.Button(header, text="刷新", command=self._refresh_trash_list, style="Small.TButton")
        btn_refresh.pack(side=tk.RIGHT, padx=4, pady=6)

        # 主区域：左侧列表 + 右侧预览
        main_pane = tk.PanedWindow(self._trash_window, orient=tk.HORIZONTAL, bg="#1e1e1e",
                                    sashwidth=4, sashrelief=tk.FLAT)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：会话列表
        left_frame = tk.Frame(main_pane, bg="#1e1e1e")
        main_pane.add(left_frame, width=520)

        columns = ("session", "files", "size", "contents")
        self._trash_tree = ttk.Treeview(left_frame, columns=columns, show="headings", selectmode="browse")
        self._trash_tree.heading("session", text="会话")
        self._trash_tree.heading("files", text="文件数")
        self._trash_tree.heading("size", text="大小")
        self._trash_tree.heading("contents", text="内容")
        self._trash_tree.column("session", width=200, minwidth=150)
        self._trash_tree.column("files", width=55, minwidth=40, anchor="center")
        self._trash_tree.column("size", width=80, minwidth=60, anchor="center")
        self._trash_tree.column("contents", width=160, minwidth=100)

        tree_font = ("Microsoft YaHei", 11)
        self._trash_tree.tag_configure("normal", font=tree_font)
        self._trash_tree.configure(font=tree_font, rowheight=32)

        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self._trash_tree.yview)
        self._trash_tree.configure(yscrollcommand=scrollbar.set)
        self._trash_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._trash_tree.bind("<<TreeviewSelect>>", self._on_trash_select)

        # 右侧：预览区
        right_frame = tk.Frame(main_pane, bg="#2d2d2d")
        main_pane.add(right_frame, width=400)

        preview_label = tk.Label(right_frame, text="📁 文件预览", font=("Microsoft YaHei", 12, "bold"),
                                  bg="#2d2d2d", fg="#cccccc")
        preview_label.pack(fill=tk.X, padx=8, pady=(8, 4))

        # 文件列表
        self._trash_file_list = tk.Listbox(right_frame, bg="#1e1e1e", fg="#d4d4d4",
                                            font=("Microsoft YaHei", 11), selectbackground="#094771",
                                            selectforeground="#ffffff", activestyle="none",
                                            relief=tk.FLAT, highlightthickness=0)
        self._trash_file_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self._trash_file_list.bind("<Double-Button-1>", self._on_trash_file_double_click)

        # 缩略图预览区
        self._trash_preview_frame = tk.Frame(right_frame, bg="#2d2d2d", height=120)
        self._trash_preview_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
        self._trash_preview_frame.pack_propagate(False)
        self._trash_preview_label = tk.Label(self._trash_preview_frame, text="双击图片文件可预览",
                                              bg="#2d2d2d", fg="#888888", font=("Microsoft YaHei", 10))
        self._trash_preview_label.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        btn_frame = tk.Frame(self._trash_window, bg="#1e1e1e")
        btn_frame.pack(fill=tk.X, padx=10, pady=8)

        btn_restore = ttk.Button(btn_frame, text="📂 恢复选中项", command=self._restore_selected_trash, style="Medium.TButton")
        btn_restore.pack(side=tk.LEFT, padx=5)

        btn_delete = ttk.Button(btn_frame, text="❌ 永久删除", command=self._delete_selected_trash, style="Medium.TButton")
        btn_delete.pack(side=tk.LEFT, padx=5)

        btn_open_dir = ttk.Button(btn_frame, text="📁 打开文件夹", command=self._open_trash_folder, style="Medium.TButton")
        btn_open_dir.pack(side=tk.LEFT, padx=5)

        self._trash_session_map = {}
        self._trash_current_session_path = None
        self._refresh_trash_list()

        self._trash_window.protocol("WM_DELETE_WINDOW", self._on_trash_window_close)

    def _on_trash_window_close(self):
        if hasattr(self, '_trash_window') and self._trash_window:
            try:
                self._trash_window.destroy()
            except Exception:
                pass
            self._trash_window = None

    def _on_trash_select(self, event=None):
        """选中会话时，右侧显示该会话内的文件列表"""
        sel = self._trash_tree.selection()
        if not sel:
            return
        session_path = self._trash_session_map.get(sel[0])
        if not session_path or not os.path.isdir(session_path):
            return
        self._trash_current_session_path = session_path
        self._trash_file_list.delete(0, tk.END)
        self._trash_preview_label.config(image="", text="双击图片文件可预览")

        for root, dirs, files in os.walk(session_path):
            for f in sorted(files):
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, session_path)
                lf = f.lower()
                if lf.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                    icon = "🖼️"
                elif lf.endswith((".mp4", ".avi", ".mkv", ".mov", ".webm")):
                    icon = "🎬"
                elif lf == "shots_data.json":
                    icon = "📝"
                else:
                    icon = "📄"
                self._trash_file_list.insert(tk.END, f"{icon} {rel}")

    def _on_trash_file_double_click(self, event=None):
        """双击文件：图片则预览，视频/其他则用系统打开"""
        sel = self._trash_file_list.curselection()
        if not sel:
            return
        display_text = self._trash_file_list.get(sel[0])
        # 去掉图标前缀
        filename = display_text.split(" ", 1)[1] if " " in display_text else display_text
        if not self._trash_current_session_path:
            return
        file_path = os.path.join(self._trash_current_session_path, filename)
        if not os.path.isfile(file_path):
            return

        lf = file_path.lower()
        if lf.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            self._preview_trash_image(file_path)
        else:
            os.startfile(file_path)

    def _preview_trash_image(self, file_path):
        """在预览区显示图片缩略图"""
        try:
            from PIL import Image, ImageTk
            img = Image.open(file_path)
            # 适配预览区大小
            max_w, max_h = 380, 110
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._trash_preview_label.config(image=photo, text="")
            self._trash_preview_label._photo = photo  # 防止GC
        except ImportError:
            self._trash_preview_label.config(text="需要Pillow库才能预览图片", image="")
        except Exception:
            self._trash_preview_label.config(text="图片预览失败", image="")

    def _refresh_trash_list(self):
        if not hasattr(self, '_trash_tree') or not self._trash_tree:
            return
        self._trash_tree.delete(*self._trash_tree.get_children())
        self._trash_session_map.clear()
        sessions = self._list_trash_sessions()
        for s in sessions:
            content_parts = []
            if s["has_shots"]:
                content_parts.append("📝 分镜脚本")
            if s["has_images"]:
                content_parts.append("🖼️ 图片")
            if s["has_video"]:
                content_parts.append("🎬 视频")
            if not content_parts:
                content_parts.append("📄 其他")
            size_str = self._format_size(s["total_size"])
            item_id = self._trash_tree.insert("", tk.END, values=(
                s["name"], s["file_count"], size_str, " | ".join(content_parts)
            ))
            self._trash_session_map[item_id] = s["path"]

    def _restore_selected_trash(self):
        if not hasattr(self, '_trash_tree') or not self._trash_tree:
            return
        sel = self._trash_tree.selection()
        if not sel:
            messagebox.showinfo("垃圾桶", "请先选择要恢复的会话", parent=self._trash_window)
            return
        item_id = sel[0]
        session_path = self._trash_session_map.get(item_id)
        if not session_path:
            return
        if not messagebox.askyesno("恢复确认", "将此会话的文件恢复到 output_project？\n同名文件将保留不被覆盖。",
                                    parent=self._trash_window):
            return
        if self._restore_trash_session(session_path):
            self.log("✅ 文件已从垃圾桶恢复到 output_project")
            self._refresh_trash_list()
        else:
            messagebox.showerror("错误", "恢复文件失败", parent=self._trash_window)

    def _delete_selected_trash(self):
        if not hasattr(self, '_trash_tree') or not self._trash_tree:
            return
        sel = self._trash_tree.selection()
        if not sel:
            messagebox.showinfo("垃圾桶", "请先选择要永久删除的会话", parent=self._trash_window)
            return
        item_id = sel[0]
        session_path = self._trash_session_map.get(item_id)
        if not session_path:
            return
        if not messagebox.askyesno("永久删除", "确定要永久删除此会话？此操作不可撤销！",
                                    parent=self._trash_window):
            return
        if self._delete_trash_session(session_path):
            self.log("🗑️ 垃圾桶会话已永久删除")
            self._refresh_trash_list()
        else:
            messagebox.showerror("错误", "删除失败", parent=self._trash_window)

    def _empty_trash_and_refresh(self):
        if not messagebox.askyesno("清空垃圾桶", "确定要永久删除垃圾桶中的所有文件？此操作不可撤销！",
                                    parent=self._trash_window):
            return
        count = self._empty_trash()
        self.log(f"🗑️ 垃圾桶已清空：共删除 {count} 个会话")
        self._refresh_trash_list()

    def _open_trash_folder(self):
        trash_dir = self._get_trash_dir()
        os.makedirs(trash_dir, exist_ok=True)
        self._open_folder(trash_dir)

    @staticmethod
    def _format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    

    def clear_log(self):
        try:
            if hasattr(self, 'txt_log') and self.txt_log:
                def update_ui():
                    try:
                        self.txt_log.delete(1.0, tk.END)
                        if hasattr(self, '_log_line_count'):
                            self._log_line_count = 0
                    except Exception:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
        except Exception:
            safe_print_exc()


    # =======================================================================
    # 云端大模型相关处理
    # =======================================================================

    def _on_cloud_provider_changed(self, event=None):
        """云端大模型服务商切换时更新模型列表"""
        from video_generator.cloud_llm_client import PROVIDER_CONFIG, get_provider_models
        
        provider_name = self.cloud_llm_provider_var.get()
        provider_id = None
        for pid, pcfg in PROVIDER_CONFIG.items():
            if pcfg["name"] == provider_name:
                provider_id = pid
                break
        
        if not provider_id:
            return
        
        models = get_provider_models(provider_id)
        model_names = [f"{m['name']} - {m['desc']}" for m in models]
        self._cloud_model_ids = [m['id'] for m in models]
        
        if hasattr(self, '_cloud_model_combo'):
            self._cloud_model_combo['values'] = model_names
        
        default_model = PROVIDER_CONFIG[provider_id]["default_model"]
        self.cloud_llm_model_var.set(default_model)
        self._cloud_selected_model_id = default_model
        
        self.log(f"☁️ 已切换云端服务商: {provider_name}")


    def _on_cloud_model_changed(self, event=None):
        """云端大模型选择变更"""
        selected_display = self.cloud_llm_model_var.get()
        if hasattr(self, '_cloud_model_combo') and hasattr(self, '_cloud_model_ids'):
            values = self._cloud_model_combo['values']
            for i, val in enumerate(values):
                if val == selected_display and i < len(self._cloud_model_ids):
                    actual_id = self._cloud_model_ids[i]
                    self._cloud_selected_model_id = actual_id
                    self.log(f"☁️ 已选择云端模型: {selected_display} ({actual_id})")
                    return
        self.log(f"☁️ 已选择云端模型: {selected_display}")



    def _test_cloud_asr_connection(self):
        """测试云端语音识别连接"""
        try:
            from video_generator.cloud_llm_client import test_cloud_asr_connection
        except ImportError:
            self.log("⚠️ 云端语音识别模块不可用")
            return

        api_key = self.cloud_asr_api_key_var.get().strip()
        if not api_key:
            self.log("⚠️ 请先输入API Key")
            messagebox.showwarning("提示", "请先输入API Key再测试连接！")
            return

        self.log("☁️ 正在测试云端语音识别连接...")
        self.cloud_asr_status_var.set("⏳ 测试中...")
        if hasattr(self, 'cloud_asr_status_label'):
            self.cloud_asr_status_label.config(foreground="orange")

        if hasattr(self, 'btn_test_cloud_asr'):
            self.btn_test_cloud_asr.config(state='disabled')

        def _do_test():
            success, message = test_cloud_asr_connection(api_key)

            def _update_ui():
                if success:
                    self.cloud_asr_status_var.set(f"✅ {message}")
                    if hasattr(self, 'cloud_asr_status_label'):
                        self.cloud_asr_status_label.config(foreground="green")
                    self.log("=" * 50)
                    self.log("✅ 云端语音识别连接成功！")
                    self.log(f"   {message}")
                    self.log("=" * 50)
                else:
                    self.cloud_asr_status_var.set(f"❌ {message}")
                    if hasattr(self, 'cloud_asr_status_label'):
                        self.cloud_asr_status_label.config(foreground="red")
                    self.log("=" * 50)
                    self.log("❌ 云端语音识别连接失败！")
                    self.log(f"   {message}")
                    self.log("=" * 50)

                if hasattr(self, 'btn_test_cloud_asr'):
                    self.btn_test_cloud_asr.config(state='normal')

            if hasattr(self, 'root') and self.root:
                self.root.after(0, _update_ui)

        threading.Thread(target=_do_test, daemon=True).start()


    def _test_cloud_llm_connection(self):
        """测试云端大模型连接"""
        from video_generator.cloud_llm_client import test_cloud_connection, PROVIDER_CONFIG
        
        provider_name = self.cloud_llm_provider_var.get()
        provider_id = None
        for pid, pcfg in PROVIDER_CONFIG.items():
            if pcfg["name"] == provider_name:
                provider_id = pid
                break
        
        if not provider_id:
            self.log("⚠️ 未选择云端服务商")
            return
        
        api_key = self.cloud_llm_api_key_var.get().strip()
        if not api_key:
            self.log("⚠️ 请先输入API Key")
            messagebox.showwarning("提示", "请先输入API Key再测试连接！")
            return
        
        model = getattr(self, '_cloud_selected_model_id', '') or self.cloud_llm_model_var.get()
        custom_url = self.cloud_llm_custom_url_var.get().strip()
        
        self.log(f"☁️ 正在测试云端模型连接: {provider_name} / {model}...")
        self.cloud_llm_status_var.set("⏳ 测试中...")
        if hasattr(self, 'cloud_llm_status_label'):
            self.cloud_llm_status_label.config(foreground="orange")
        
        if hasattr(self, 'btn_test_cloud'):
            self.btn_test_cloud.config(state='disabled')
        
        def _do_test():
            success, message = test_cloud_connection(api_key, provider_id, model, custom_url)
            
            def _update_ui():
                if success:
                    self.cloud_llm_status_var.set(f"✅ {message}")
                    if hasattr(self, 'cloud_llm_status_label'):
                        self.cloud_llm_status_label.config(foreground="green")
                    self.log("=" * 50)
                    self.log(f"✅ 云端模型连接成功！")
                    self.log(f"   {message}")
                    self.log("=" * 50)
                else:
                    self.cloud_llm_status_var.set(f"❌ {message}")
                    if hasattr(self, 'cloud_llm_status_label'):
                        self.cloud_llm_status_label.config(foreground="red")
                    self.log("=" * 50)
                    self.log(f"❌ 云端模型连接失败！")
                    self.log(f"   {message}")
                    self.log("=" * 50)
                
                if hasattr(self, 'btn_test_cloud'):
                    self.btn_test_cloud.config(state='normal')
            
            if hasattr(self, 'root') and self.root:
                self.root.after(0, _update_ui)
        
        threading.Thread(target=_do_test, daemon=True).start()


    def _on_cloud_image_provider_changed(self, event=None):
        """云端生图服务商变更"""
        try:
            from video_generator.cloud_image_client import IMAGE_PROVIDER_CONFIG, get_image_provider_models
            provider_name = self.cloud_image_provider_var.get()
            provider_id = None
            for pid, pcfg in IMAGE_PROVIDER_CONFIG.items():
                if pcfg["name"] == provider_name:
                    provider_id = pid
                    break
            if not provider_id:
                return
            models = get_image_provider_models(provider_id)
            model_names = [f"{m['name']} - {m['desc']}" for m in models]
            self._cloud_img_model_ids = [m['id'] for m in models]
            if hasattr(self, '_cloud_img_model_combo'):
                self._cloud_img_model_combo['values'] = model_names
            default_model = IMAGE_PROVIDER_CONFIG[provider_id].get("default_model", "")
            self.cloud_image_model_var.set(default_model)
            self._cloud_selected_image_model_id = default_model
        except ImportError:
            pass


    def _on_cloud_image_model_changed(self, event=None):
        """云端生图模型变更"""
        idx = getattr(self, '_cloud_img_model_combo', None)
        if idx is not None:
            current = self._cloud_img_model_combo.current()
            if 0 <= current < len(self._cloud_img_model_ids):
                self._cloud_selected_image_model_id = self._cloud_img_model_ids[current]
            else:
                self._cloud_selected_image_model_id = self.cloud_image_model_var.get()


    def _toggle_entry_visibility(self, entry_widget):
        """切换输入框的密码显示/隐藏"""
        if entry_widget.cget('show') == '*':
            entry_widget.config(show='')
        else:
            entry_widget.config(show='*')


    def _test_cloud_image_connection(self):
        """测试云端生图连接"""
        try:
            from video_generator.cloud_image_client import test_cloud_image_connection, IMAGE_PROVIDER_CONFIG
        except ImportError:
            self.log("⚠️ 云端生图模块未安装")
            return

        provider_name = self.cloud_image_provider_var.get()
        provider_id = None
        for pid, pcfg in IMAGE_PROVIDER_CONFIG.items():
            if pcfg["name"] == provider_name:
                provider_id = pid
                break

        if not provider_id:
            self.log("⚠️ 未选择云端生图服务商")
            return

        api_key = self.cloud_image_api_key_var.get().strip()
        if not api_key:
            self.log("⚠️ 请先输入云端生图API Key")
            messagebox.showwarning("提示", "请先输入API Key再测试连接！")
            return

        model = getattr(self, '_cloud_selected_image_model_id', '') or self.cloud_image_model_var.get()
        custom_url = self.cloud_image_custom_url_var.get().strip()

        self.log(f"☁️ 正在测试云端生图连接: {provider_name} / {model}...")
        self.cloud_image_status_var.set("⏳ 测试中...")
        if hasattr(self, 'cloud_image_status_label'):
            self.cloud_image_status_label.config(foreground="orange")

        if hasattr(self, 'btn_test_cloud_image'):
            self.btn_test_cloud_image.config(state='disabled')

        def _do_test():
            success, message = test_cloud_image_connection(api_key, provider_id, model, custom_url)

            def _update_ui():
                if success:
                    self.cloud_image_status_var.set(f"✅ {message}")
                    if hasattr(self, 'cloud_image_status_label'):
                        self.cloud_image_status_label.config(foreground="green")
                    self.log("=" * 50)
                    self.log(f"✅ 云端生图连接成功！")
                    self.log(f"   {message}")
                    self.log("=" * 50)
                else:
                    self.cloud_image_status_var.set(f"❌ {message}")
                    if hasattr(self, 'cloud_image_status_label'):
                        self.cloud_image_status_label.config(foreground="red")
                    self.log("=" * 50)
                    self.log(f"❌ 云端生图连接失败！")
                    self.log(f"   {message}")
                    self.log("=" * 50)

                if hasattr(self, 'btn_test_cloud_image'):
                    self.btn_test_cloud_image.config(state='normal')

            if hasattr(self, 'root') and self.root:
                self.root.after(0, _update_ui)

        threading.Thread(target=_do_test, daemon=True).start()


    def _apply_cloud_llm_config(self):
        """应用云端大模型配置到全局状态"""
        from video_generator.cloud_llm_client import set_cloud_llm_config, PROVIDER_CONFIG
        
        provider_name = self.cloud_llm_provider_var.get()
        provider_id = None
        for pid, pcfg in PROVIDER_CONFIG.items():
            if pcfg["name"] == provider_name:
                provider_id = pid
                break
        
        if not provider_id:
            provider_id = "deepseek"
        
        enabled = self.cloud_llm_enabled_var.get() if hasattr(self, 'cloud_llm_enabled_var') else False
        api_key = self.cloud_llm_api_key_var.get().strip() if hasattr(self, 'cloud_llm_api_key_var') else ""
        model = getattr(self, '_cloud_selected_model_id', '') or (self.cloud_llm_model_var.get() if hasattr(self, 'cloud_llm_model_var') else "")
        custom_url = self.cloud_llm_custom_url_var.get().strip() if hasattr(self, 'cloud_llm_custom_url_var') else ""
        
        if enabled and not api_key:
            self.log("⚠️ 启用云端模型需要提供API Key")
            enabled = False
            if hasattr(self, 'cloud_llm_enabled_var'):
                self.cloud_llm_enabled_var.set(False)
        
        set_cloud_llm_config({
            "enabled": enabled,
            "provider": provider_id,
            "api_key": api_key,
            "model": model,
            "custom_base_url": custom_url,
        })
        
        try:
            from video_generator.cloud_llm_client import set_cloud_asr_config
            asr_enabled = self.cloud_asr_enabled_var.get() if hasattr(self, 'cloud_asr_enabled_var') else False
            asr_api_key = self.cloud_asr_api_key_var.get().strip() if hasattr(self, 'cloud_asr_api_key_var') else ""
            set_cloud_asr_config({
                "enabled": asr_enabled,
                "provider": "openai",
                "api_key": asr_api_key,
            })
        except ImportError:
            pass

        try:
            from video_generator.cloud_image_client import set_cloud_image_config, IMAGE_PROVIDER_CONFIG
            img_enabled = self.cloud_image_enabled_var.get() if hasattr(self, 'cloud_image_enabled_var') else False
            img_api_key = self.cloud_image_api_key_var.get().strip() if hasattr(self, 'cloud_image_api_key_var') else ""
            img_provider_name = self.cloud_image_provider_var.get() if hasattr(self, 'cloud_image_provider_var') else ""
            img_provider_id = None
            for pid, pcfg in IMAGE_PROVIDER_CONFIG.items():
                if pcfg["name"] == img_provider_name:
                    img_provider_id = pid
                    break
            if not img_provider_id:
                img_provider_id = "siliconflow"
            img_model = getattr(self, '_cloud_selected_image_model_id', '') or (self.cloud_image_model_var.get() if hasattr(self, 'cloud_image_model_var') else "")
            img_custom_url = self.cloud_image_custom_url_var.get().strip() if hasattr(self, 'cloud_image_custom_url_var') else ""

            if img_enabled and not img_api_key:
                self.log("⚠️ 启用云端生图需要提供API Key")
                img_enabled = False
                if hasattr(self, 'cloud_image_enabled_var'):
                    self.cloud_image_enabled_var.set(False)

            set_cloud_image_config({
                "enabled": img_enabled,
                "provider": img_provider_id,
                "api_key": img_api_key,
                "model": img_model,
                "custom_base_url": img_custom_url,
            })

            if img_enabled:
                img_provider_display = IMAGE_PROVIDER_CONFIG.get(img_provider_id, {}).get("name", img_provider_id)
                self._cloud_img_enabled = True
                self._cloud_img_provider = img_provider_display
                self._cloud_img_model = img_model
            else:
                self._cloud_img_enabled = False
        except ImportError:
            self._cloud_img_enabled = False

        provider_display = PROVIDER_CONFIG.get(provider_id, {}).get("name", provider_id)
        if enabled:
            self._cloud_llm_enabled = True
            self._cloud_llm_provider = provider_display
            self._cloud_llm_model = model
            if not getattr(self, 'task_running', False) and is_ollama_available():
                try:
                    self._unload_ollama_models(log_prefix="")
                    set_ollama_available(False)
                except Exception:
                    pass
        else:
            self._cloud_llm_enabled = False


    def _on_cloud_llm_toggle_ui(self, *args):
        """云端LLM启用状态变化时，更新本地模型面板的可用性"""
        if hasattr(self, 'root') and self.root:
            self.root.after(0, self._update_local_model_panel_state)

    def _on_cloud_asr_toggle_ui(self, *args):
        """云端ASR启用状态变化时，更新Whisper模型选择器的可用性"""
        if hasattr(self, 'root') and self.root:
            self.root.after(0, self._update_local_model_panel_state)

    def _update_local_model_panel_state(self):
        """根据云端模式状态，启用/禁用本地模型预选面板中的各项"""
        cloud_llm = self.cloud_llm_enabled_var.get() if hasattr(self, 'cloud_llm_enabled_var') else False
        cloud_asr = self.cloud_asr_enabled_var.get() if hasattr(self, 'cloud_asr_enabled_var') else False
        cloud_img = self.cloud_image_enabled_var.get() if hasattr(self, 'cloud_image_enabled_var') else False

        if hasattr(self, '_ollama_button'):
            state = 'disabled' if cloud_llm else 'normal'
            self._ollama_button.config(state=state)

        if hasattr(self, '_ollama_label'):
            self._ollama_label.config(foreground="#888888" if cloud_llm else "")

        if hasattr(self, '_whisper_combo'):
            state = 'disabled' if cloud_asr else 'readonly'
            self._whisper_combo.config(state=state)

        if hasattr(self, '_whisper_label'):
            self._whisper_label.config(foreground="#888888" if cloud_asr else "")

        if hasattr(self, '_sd_model_combo'):
            state = 'disabled' if cloud_img else 'readonly'
            self._sd_model_combo.config(state=state)
        if hasattr(self, '_sd_model_label'):
            self._sd_model_label.config(foreground="#888888" if cloud_img else "")

        if hasattr(self, '_width_entry'):
            state = 'disabled' if cloud_img else 'normal'
            self._width_entry.config(state=state)
        if hasattr(self, '_height_entry'):
            state = 'disabled' if cloud_img else 'normal'
            self._height_entry.config(state=state)

        if hasattr(self, '_btn_connect_api'):
            state = 'disabled' if cloud_img else 'normal'
            self._btn_connect_api.config(state=state)
        if hasattr(self, '_btn_disconnect_api'):
            state = 'disabled' if cloud_img else 'normal'
            self._btn_disconnect_api.config(state=state)
        if hasattr(self, '_sd_api_url_entry'):
            state = 'disabled' if cloud_img else 'normal'
            self._sd_api_url_entry.config(state=state)

        if hasattr(self, '_cloud_mode_note'):
            notes = []
            if cloud_llm:
                notes.append("☁️ Ollama模型已禁用（云端LLM替代）")
                notes.append("   配置模式仅temperature生效")
            if cloud_asr:
                notes.append("☁️ 语音模型已禁用（云端ASR替代）")
            if cloud_img:
                notes.append("🎨 本地SD设置已禁用（云端生图替代）")
            self._cloud_mode_note.config(text="\n".join(notes))

    def clear_script(self):
        """清除脚本"""
        self.log("🗑️ 清除脚本")
        try:
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
            safe_print_exc()
    

    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                try:
                    from video_generator.crypto_utils import decrypt_config
                    decrypt_config(config, self.base_dir)
                except ImportError:
                    pass
                
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
                
                # 加载分镜批处理大小设置
                if 'batch_size' in config and hasattr(self, 'batch_size_var'):
                    self.batch_size_var.set(config['batch_size'])
                
                # 加载Whisper模型设置
                if 'whisper_model' in config and hasattr(self, 'whisper_model_var'):
                    self.whisper_model_var.set(config['whisper_model'])
                
                if 'cloud_llm_enabled' in config and hasattr(self, 'cloud_llm_enabled_var'):
                    self.cloud_llm_enabled_var.set(config['cloud_llm_enabled'])
                if 'cloud_llm_provider' in config and hasattr(self, 'cloud_llm_provider_var'):
                    self.cloud_llm_provider_var.set(config['cloud_llm_provider'])
                if 'cloud_llm_api_key' in config and hasattr(self, 'cloud_llm_api_key_var'):
                    self.cloud_llm_api_key_var.set(config['cloud_llm_api_key'])
                if 'cloud_llm_model' in config and hasattr(self, 'cloud_llm_model_var'):
                    self.cloud_llm_model_var.set(config['cloud_llm_model'])
                    self._cloud_selected_model_id = config.get('cloud_llm_model_id', config['cloud_llm_model'])
                if 'cloud_llm_custom_url' in config and hasattr(self, 'cloud_llm_custom_url_var'):
                    self.cloud_llm_custom_url_var.set(config['cloud_llm_custom_url'])
                if 'cloud_asr_enabled' in config and hasattr(self, 'cloud_asr_enabled_var'):
                    self.cloud_asr_enabled_var.set(config['cloud_asr_enabled'])
                if 'cloud_asr_api_key' in config and hasattr(self, 'cloud_asr_api_key_var'):
                    self.cloud_asr_api_key_var.set(config['cloud_asr_api_key'])

                if 'cloud_image_enabled' in config and hasattr(self, 'cloud_image_enabled_var'):
                    self.cloud_image_enabled_var.set(config['cloud_image_enabled'])
                if 'cloud_image_provider' in config and hasattr(self, 'cloud_image_provider_var'):
                    self.cloud_image_provider_var.set(config['cloud_image_provider'])
                if 'cloud_image_api_key' in config and hasattr(self, 'cloud_image_api_key_var'):
                    self.cloud_image_api_key_var.set(config['cloud_image_api_key'])
                if 'cloud_image_model' in config and hasattr(self, 'cloud_image_model_var'):
                    self.cloud_image_model_var.set(config['cloud_image_model'])
                    self._cloud_selected_image_model_id = config.get('cloud_image_model_id', config['cloud_image_model'])
                if 'cloud_image_custom_url' in config and hasattr(self, 'cloud_image_custom_url_var'):
                    self.cloud_image_custom_url_var.set(config['cloud_image_custom_url'])

                if 'min_shot_duration' in config and hasattr(self, 'min_shot_duration_var'):
                    self.min_shot_duration_var.set(float(config['min_shot_duration']))
                    self.MIN_SHOT_DURATION = float(config['min_shot_duration'])

                if hasattr(self, '_apply_cloud_llm_config'):
                    try:
                        self._apply_cloud_llm_config()
                    except Exception:
                        pass
                
                self.log(f"✅ 配置加载完成")
                self._print_current_settings()
        except Exception as e:
            self.log(f"⚠️ 配置加载失败: {e}")
    

    def save_config(self):
        """保存配置"""
        try:
            if hasattr(self, '_apply_cloud_llm_config'):
                self._apply_cloud_llm_config()
            
            selected_styles = self.get_selected_styles()
            
            existing_config = {}
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    existing_config = json.load(f)
            except Exception:
                pass
            
            _w, _h = validate_image_size(self.width_var.get(), self.height_var.get())
            config = {
                'api_base_url': existing_config.get('api_base_url', 'https://api.wangzha178.com'),
                'model': self.model_var.get(),
                'width': _w,
                'height': _h,
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
                'thread_count': self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 8,
                'batch_size': self.batch_size_var.get() if hasattr(self, 'batch_size_var') else 2,
                'cloud_llm_enabled': self.cloud_llm_enabled_var.get() if hasattr(self, 'cloud_llm_enabled_var') else False,
                'cloud_llm_provider': self.cloud_llm_provider_var.get() if hasattr(self, 'cloud_llm_provider_var') else 'DeepSeek 深度求索',
                'cloud_llm_api_key': self.cloud_llm_api_key_var.get() if hasattr(self, 'cloud_llm_api_key_var') else '',
                'cloud_llm_model': self.cloud_llm_model_var.get() if hasattr(self, 'cloud_llm_model_var') else 'deepseek-chat',
                'cloud_llm_model_id': getattr(self, '_cloud_selected_model_id', '') or 'deepseek-chat',
                'cloud_llm_custom_url': self.cloud_llm_custom_url_var.get() if hasattr(self, 'cloud_llm_custom_url_var') else '',
                'cloud_asr_enabled': self.cloud_asr_enabled_var.get() if hasattr(self, 'cloud_asr_enabled_var') else False,
                'cloud_asr_api_key': self.cloud_asr_api_key_var.get() if hasattr(self, 'cloud_asr_api_key_var') else '',
                'cloud_image_enabled': self.cloud_image_enabled_var.get() if hasattr(self, 'cloud_image_enabled_var') else False,
                'cloud_image_provider': self.cloud_image_provider_var.get() if hasattr(self, 'cloud_image_provider_var') else 'siliconflow',
                'cloud_image_api_key': self.cloud_image_api_key_var.get() if hasattr(self, 'cloud_image_api_key_var') else '',
                'cloud_image_model': self.cloud_image_model_var.get() if hasattr(self, 'cloud_image_model_var') else '',
                'cloud_image_model_id': getattr(self, '_cloud_selected_image_model_id', '') or '',
                'cloud_image_custom_url': self.cloud_image_custom_url_var.get() if hasattr(self, 'cloud_image_custom_url_var') else '',
                'min_shot_duration': self.min_shot_duration_var.get() if hasattr(self, 'min_shot_duration_var') else 4.0,
            }
            
            try:
                from video_generator.crypto_utils import encrypt_config
                encrypt_config(config, self.base_dir)
            except ImportError:
                pass
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.log("✅ 配置保存完成")
        except Exception as e:
            self.log(f"⚠️ 配置保存失败: {e}")

    def _check_api_heartbeat(self):
        try:
            from video_generator.config import get_api_base_url, get_http_session
            api_url = get_api_base_url()
            if not api_url:
                return
            resp = get_http_session().get(
                f"{api_url}/health",
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                db_ok = data.get("database") == "ok"
                if not db_ok:
                    if not getattr(self, '_api_db_warned', False):
                        self._api_db_warned = True
                        self.log("⚠️ Backend API database degraded")
            else:
                if not getattr(self, '_api_warned', False):
                    self._api_warned = True
                    self.log(f"⚠️ Backend API returned status {resp.status_code}")
        except Exception:
            if not getattr(self, '_api_warned', False):
                self._api_warned = True
                self.log("⚠️ Backend API unreachable")

