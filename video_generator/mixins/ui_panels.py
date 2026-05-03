"""UI panels mixin - left panel, advanced settings, script/log areas."""
import os
import json
import tkinter as tk
from tkinter import ttk

from video_generator.config import Config
# 修复：导入模块而非值，运行时读取实际状态
import video_generator.app_state as app_state

class UIPanelsMixin:
    def setup_left_panel(self):
        """设置左侧控制面板"""
        # 主框架，使用grid布局实现均匀分布
        frame = ttk.Frame(self.left_frame, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置grid布局，使行和列能够自适应
        frame.columnconfigure(0, weight=1)
        
        # 为每个功能组设置权重，实现均匀分布
        for i in range(9):  # 增加一行用于更新按钮
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

        # ========== 新增: 版本更新按钮 ==========
        update_frame = ttk.Frame(frame)
        update_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        update_frame.columnconfigure(0, weight=1)
        update_frame.rowconfigure(0, weight=1)
        
        btn_check_update = ttk.Button(update_frame, text="🔄 检查更新", command=self.check_for_updates, style="Medium.TButton")
        btn_check_update.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 分隔线
        sep_update = ttk.Separator(frame, orient='horizontal')
        sep_update.grid(row=2, column=0, sticky="ew", pady=5)

        # 第一组：音频导入
        section1 = ttk.Frame(frame)
        section1.grid(row=3, column=0, sticky="nsew", pady=(0, 5))
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
        sep1.grid(row=4, column=0, sticky="ew", pady=5)

        # 第二组：生成分镜
        section2 = ttk.Frame(frame)
        section2.grid(row=5, column=0, sticky="nsew", pady=(0, 5))
        section2.columnconfigure(0, weight=1)
        section2.rowconfigure(0, weight=1)
        
        btn_generate = ttk.Button(section2, text="🎬 生成分镜脚本", command=self.generate_shots_threaded, style="LargeBlue.TButton")
        btn_generate.pack(fill=tk.BOTH, expand=True, pady=5)

        # 分隔线
        sep2 = ttk.Separator(frame, orient='horizontal')
        sep2.grid(row=6, column=0, sticky="ew", pady=5)

        # 第三组：视频生成
        section5 = ttk.Frame(frame)
        section5.grid(row=7, column=0, sticky="nsew", pady=(0, 5))
        section5.columnconfigure(0, weight=1)
        section5.rowconfigure(0, weight=1)
        section5.rowconfigure(1, weight=1)
        
        btn_render = ttk.Button(section5, text="🎞️ 生成视频", command=self.render_video_threaded, style="LargeRed.TButton")
        btn_render.pack(fill=tk.BOTH, expand=True, pady=5)
        


        # 分隔线
        sep3 = ttk.Separator(frame, orient='horizontal')
        sep3.grid(row=8, column=0, sticky="ew", pady=5)

        # 第四组：进度条和依赖检查
        status_frame = ttk.Frame(frame)
        status_frame.grid(row=9, column=0, sticky="nsew", pady=(0, 5))
        status_frame.columnconfigure(0, weight=1)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(status_frame, variable=self.progress_var, maximum=100, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 进度标签
        self.lbl_progress = tk.Label(status_frame, text="就绪", background="#2b2b2b", foreground="#FFFFFF", font=("Microsoft YaHei", 16, "bold"))
        self.lbl_progress.pack(anchor=tk.W, pady=2)
        
        # 高级设置按钮
        btn_advanced = ttk.Button(status_frame, text="⚙️ 高级设置", command=self.toggle_advanced_settings, style="Medium.TButton")
        btn_advanced.pack(fill=tk.X, pady=5)

        # 性能监控面板（运行时检查，确保 lazy_import 后的状态正确）
        if app_state.PERFORMANCE_MONITOR_AVAILABLE:
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


    def setup_advanced_panel_content(self, panels):
        """创建高级设置面板内容 - 网格均匀分布布局
        
        panels: dict，key为板块名，value为对应的Frame容器
        """
        large_font_size = self.font_size + 4
        small_font_size = self.font_size + 2
        enable_font_size = self.font_size + 3

        style = ttk.Style()
        style.configure("Cloud.TCheckbutton", font=('Microsoft YaHei', enable_font_size, 'bold'), foreground="#e0e0e0")
        
        # ==================== 绘图设置 ====================
        section_frame = ttk.LabelFrame(panels["draw"], text="🎨 绘图设置", padding=6, style="Adv.TLabelframe")
        section_frame.pack(fill=tk.X)
        
        # 绘图模型
        model_frame = ttk.Frame(section_frame)
        model_frame.pack(fill=tk.X, pady=3)
        ttk.Label(model_frame, text="模型:", width=12, font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'model_var') or self.model_var.get() == "":
            self.model_var = tk.StringVar(value="使用当前模型")
        
        self._default_models = ["使用当前模型", "Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3"]
        
        models = self._default_models
        
        model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, values=models, state="readonly", font=("Microsoft YaHei", large_font_size))
        model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        self.model_combo = model_combo
        self._sd_model_combo = model_combo
        
        refresh_btn = ttk.Button(model_frame, text="🔄", width=3,
            command=self._refresh_model_list, style="Accent.TButton")
        refresh_btn.pack(side=tk.LEFT, padx=2, pady=2)
        self._model_refresh_btn = refresh_btn
        
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
        
        self._width_entry = ttk.Entry(width_frame, textvariable=self.width_var, width=10, font=("Microsoft YaHei", large_font_size))
        self._width_entry.pack(side=tk.LEFT, padx=5, pady=2)
        
        height_frame = ttk.Frame(pixel_frame)
        height_frame.pack(side=tk.LEFT, padx=5)
        ttk.Label(height_frame, text="高:", font=("Microsoft YaHei", large_font_size)).pack(side=tk.LEFT)
        
        # 如果变量不存在，则初始化
        if not hasattr(self, 'height_var') or self.height_var.get() == "":
            self.height_var = tk.StringVar(value="1080")
        
        self._height_entry = ttk.Entry(height_frame, textvariable=self.height_var, width=10, font=("Microsoft YaHei", large_font_size))
        self._height_entry.pack(side=tk.LEFT, padx=5, pady=2)

        # ==================== 风格设置 ====================
        style_section = ttk.LabelFrame(panels["style"], text="🎨 风格设置", padding=6, style="Adv.TLabelframe")
        style_section.pack(fill=tk.X)
        
        self.style_control_frame = ttk.Frame(style_section)
        self.style_control_frame.pack(fill=tk.X, pady=3)
        
        self.style_dropdown_visible = False
        self.style_dropdown_frame = ttk.Frame(style_section)
        
        style_button = ttk.Button(self.style_control_frame, text="展开风格选项", command=self.toggle_style_dropdown, style="Medium.TButton")
        style_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.style_grid = ttk.Frame(self.style_dropdown_frame)
        self.style_grid.pack(fill=tk.X, pady=3)
        
        style_options = ["电影感", "纪录片风", "赛博朋克", "写实摄影", "皮克斯", "达芬奇", "油画", "多巴胺", "黑白线条", "吉卜力", "梵高", "日式动漫", "水彩"]
        
        existing_vars = {name: var for name, var in self.dlr_vars}
        
        for i, opt in enumerate(style_options):
            if opt in existing_vars:
                var = existing_vars[opt]
            else:
                var = tk.BooleanVar()
                self.dlr_vars.append((opt, var))
            row = i // 3
            col = i % 3
            chk = ttk.Checkbutton(self.style_grid, text=opt, variable=var)
            chk.grid(row=row, column=col, sticky=tk.W, padx=10, pady=8)
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if 'selected_styles' in config:
                    selected_styles = config['selected_styles']
                    for style_name, var in self.dlr_vars:
                        if style_name in selected_styles:
                            var.set(True)
                        else:
                            var.set(False)
        except Exception as e:
            pass
        
        # ==================== SD API设置 ====================
        api_section = ttk.LabelFrame(panels["sd_api"], text="🔌 SD API 设置", padding=6, style="Adv.TLabelframe")
        api_section.pack(fill=tk.X)
        
        api_url_frame = ttk.Frame(api_section)
        api_url_frame.pack(fill=tk.X, pady=3)
        ttk.Label(api_url_frame, text="API URL:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        self._sd_api_url_entry = ttk.Entry(api_url_frame, textvariable=self.sd_api_url_var, font=('Microsoft YaHei', large_font_size))
        self._sd_api_url_entry.pack(fill=tk.X, padx=5, pady=2)
        
        api_control_frame = ttk.Frame(api_section)
        api_control_frame.pack(fill=tk.X, pady=3)
        
        if not hasattr(self, 'sd_api_status_var'):
            self.sd_api_status_var = tk.StringVar(value="❌ 未连接")
        self.sd_api_status_label = ttk.Label(api_control_frame, textvariable=self.sd_api_status_var, font=('Microsoft YaHei', large_font_size), foreground="red")
        if "已连接" in self.sd_api_status_var.get():
            self.sd_api_status_label.config(foreground="green")
        else:
            self.sd_api_status_label.config(foreground="red")
        self.sd_api_status_label.pack(side=tk.LEFT, padx=5)
        
        btn_frame = ttk.Frame(api_control_frame)
        btn_frame.pack(side=tk.RIGHT)
        
        self._btn_connect_api = ttk.Button(btn_frame, text="🔗 连接 API", command=self.check_sd_api_connection, style="Medium.TButton")
        self._btn_connect_api.pack(side=tk.LEFT, padx=5, pady=2)
        
        self._btn_disconnect_api = ttk.Button(btn_frame, text="🔌 断开连接", command=self.close_sd_api_connection, style="Medium.TButton")
        self._btn_disconnect_api.pack(side=tk.LEFT, padx=5, pady=2)
        
        # ==================== 视频设置 ====================
        video_section = ttk.LabelFrame(panels["video"], text="🎬 视频设置", padding=6, style="Adv.TLabelframe")
        video_section.pack(fill=tk.X)
        
        animation_frame = ttk.Frame(video_section)
        animation_frame.pack(fill=tk.X, pady=3)
        ttk.Label(animation_frame, text="单张画面动画:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'animation_var'):
            self.animation_var = tk.StringVar(value="无")
        
        animation_options = ["无", "缩放", "左移", "右移", "上移", "下移"]
        animation_combo = ttk.Combobox(animation_frame, textvariable=self.animation_var, values=animation_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        animation_combo.pack(fill=tk.X, padx=5, pady=2)
        
        transition_frame = ttk.Frame(video_section)
        transition_frame.pack(fill=tk.X, pady=3)
        ttk.Label(transition_frame, text="过渡效果:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'transition_var'):
            self.transition_var = tk.StringVar(value="硬切")
        
        transition_options = ["硬切", "交叉淡化"]
        transition_combo = ttk.Combobox(transition_frame, textvariable=self.transition_var, values=transition_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        transition_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # ==================== 提示词设置 ====================
        prompt_section = ttk.LabelFrame(panels["prompt"], text="💬 提示词设置", padding=4, style="Adv.TLabelframe")
        prompt_section.pack(fill=tk.X)
        
        prompt_frame = ttk.Frame(prompt_section)
        prompt_frame.pack(fill=tk.X, pady=3)
        ttk.Label(prompt_frame, text="提示词类型:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'prompt_type_var'):
            self.prompt_type_var = tk.StringVar(value="SD提示词")
        
        prompt_options = ttk.Frame(prompt_frame)
        prompt_options.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        sd_prompt_btn = ttk.Button(prompt_options, text="SD提示词", command=lambda: self._on_prompt_type_changed("SD提示词"), style="Medium.TButton")
        sd_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        arv_prompt_btn = ttk.Button(prompt_options, text="ARV写实提示词", command=lambda: self._on_prompt_type_changed("ARV写实提示词"), style="Medium.TButton")
        arv_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)
        
        prompt_status_frame = ttk.Frame(prompt_section)
        prompt_status_frame.pack(fill=tk.X, pady=3)
        ttk.Label(prompt_status_frame, text="当前选择:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        prompt_status_label = ttk.Label(prompt_status_frame, textvariable=self.prompt_type_var, font=('Microsoft YaHei', large_font_size, 'bold'))
        prompt_status_label.pack(side=tk.LEFT, padx=5)
        
        # ==================== 云端大模型 ====================
        cloud_section = ttk.LabelFrame(panels["cloud_llm"], text="☁️ 云端大模型 · AI思考大脑", padding=4, style="Adv.TLabelframe")
        cloud_section.pack(fill=tk.X)
        
        from video_generator.cloud_llm_client import PROVIDER_CONFIG, get_cloud_llm_config, get_provider_models
        
        cloud_config = get_cloud_llm_config()
        
        if not hasattr(self, 'cloud_llm_enabled_var'):
            self.cloud_llm_enabled_var = tk.BooleanVar(value=cloud_config.get("enabled", False))
        if not hasattr(self, 'cloud_llm_provider_var'):
            self.cloud_llm_provider_var = tk.StringVar(value=cloud_config.get("provider", "deepseek"))
        if not hasattr(self, 'cloud_llm_api_key_var'):
            self.cloud_llm_api_key_var = tk.StringVar(value=cloud_config.get("api_key", ""))
        if not hasattr(self, 'cloud_llm_model_var'):
            self.cloud_llm_model_var = tk.StringVar(value=cloud_config.get("model", "deepseek-chat"))
        if not hasattr(self, 'cloud_llm_custom_url_var'):
            self.cloud_llm_custom_url_var = tk.StringVar(value=cloud_config.get("custom_base_url", ""))
        
        enable_frame = ttk.Frame(cloud_section)
        enable_frame.pack(fill=tk.X, pady=3)
        cloud_enable_chk = ttk.Checkbutton(enable_frame, text="启用云端大模型（替代本地Ollama）", variable=self.cloud_llm_enabled_var, style="Cloud.TCheckbutton")
        cloud_enable_chk.pack(anchor=tk.W, padx=5)
        cloud_enable_label = tk.Label(enable_frame, text="⚡ 启用后所有AI思考任务由云端完成，不使用本地Ollama", font=('Microsoft YaHei', small_font_size), foreground="white", bg=self.panel_bg)
        cloud_enable_label.pack(anchor=tk.W, padx=20)
        
        provider_frame = ttk.Frame(cloud_section)
        provider_frame.pack(fill=tk.X, pady=3)
        ttk.Label(provider_frame, text="服务商:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        provider_names = [f"{PROVIDER_CONFIG[pid]['name']}" for pid in PROVIDER_CONFIG]
        provider_ids = list(PROVIDER_CONFIG.keys())
        self._cloud_provider_ids = provider_ids
        
        provider_combo = ttk.Combobox(provider_frame, textvariable=self.cloud_llm_provider_var, values=provider_names, state="readonly", font=('Microsoft YaHei', large_font_size))
        provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        provider_combo.bind('<<ComboboxSelected>>', self._on_cloud_provider_changed)
        
        api_key_frame = ttk.Frame(cloud_section)
        api_key_frame.pack(fill=tk.X, pady=3)
        ttk.Label(api_key_frame, text="API Key:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        api_key_entry = ttk.Entry(api_key_frame, textvariable=self.cloud_llm_api_key_var, font=('Microsoft YaHei', large_font_size), show="*")
        api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        toggle_key_btn = ttk.Button(api_key_frame, text="👁", width=3, command=self._toggle_api_key_visibility, style="Small.TButton")
        toggle_key_btn.pack(side=tk.LEFT, padx=2)
        
        cloud_model_frame = ttk.Frame(cloud_section)
        cloud_model_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cloud_model_frame, text="模型:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        current_provider = cloud_config.get("provider", "deepseek")
        current_models = get_provider_models(current_provider)
        model_names = [f"{m['name']} - {m['desc']}" for m in current_models]
        self._cloud_model_ids = [m['id'] for m in current_models]
        
        cloud_model_combo = ttk.Combobox(cloud_model_frame, textvariable=self.cloud_llm_model_var, values=model_names, state="readonly", font=('Microsoft YaHei', large_font_size))
        cloud_model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        cloud_model_combo.bind('<<ComboboxSelected>>', self._on_cloud_model_changed)
        self._cloud_model_combo = cloud_model_combo
        
        custom_url_frame = ttk.Frame(cloud_section)
        custom_url_frame.pack(fill=tk.X, pady=3)
        ttk.Label(custom_url_frame, text="自定义URL:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        custom_url_entry = ttk.Entry(custom_url_frame, textvariable=self.cloud_llm_custom_url_var, font=('Microsoft YaHei', large_font_size))
        custom_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        cloud_btn_frame = ttk.Frame(cloud_section)
        cloud_btn_frame.pack(fill=tk.X, pady=3)
        
        self.btn_test_cloud = ttk.Button(cloud_btn_frame, text="🔗 测试连接", command=self._test_cloud_llm_connection, style="Medium.TButton")
        self.btn_test_cloud.pack(side=tk.LEFT, padx=5, pady=2)
        
        if not hasattr(self, 'cloud_llm_status_var'):
            self.cloud_llm_status_var = tk.StringVar(value="❌ 未连接")
        self.cloud_llm_status_label = ttk.Label(cloud_btn_frame, textvariable=self.cloud_llm_status_var, font=('Microsoft YaHei', large_font_size), foreground="red")
        self.cloud_llm_status_label.pack(side=tk.LEFT, padx=10)
        
        # ==================== 云端语音识别 ====================
        asr_section = ttk.LabelFrame(panels["cloud_asr"], text="🎙️ 云端语音识别 · 替代Whisper", padding=4, style="Adv.TLabelframe")
        asr_section.pack(fill=tk.X)
        
        try:
            from video_generator.cloud_llm_client import get_cloud_asr_config
            asr_config = get_cloud_asr_config()
            asr_available = True
        except ImportError:
            asr_available = False
            asr_config = {}
        
        if not hasattr(self, 'cloud_asr_enabled_var'):
            self.cloud_asr_enabled_var = tk.BooleanVar(value=asr_config.get("enabled", False))
        if not hasattr(self, 'cloud_asr_api_key_var'):
            self.cloud_asr_api_key_var = tk.StringVar(value=asr_config.get("api_key", ""))
        
        asr_enable_frame = ttk.Frame(asr_section)
        asr_enable_frame.pack(fill=tk.X, pady=3)
        asr_enable_chk = ttk.Checkbutton(asr_enable_frame, text="启用云端语音识别（替代本地Whisper，无需GPU）", variable=self.cloud_asr_enabled_var, style="Cloud.TCheckbutton")
        asr_enable_chk.pack(anchor=tk.W, padx=5)
        asr_enable_label = tk.Label(asr_enable_frame, text="⚡ 启用后语音识别由OpenAI Whisper API完成，不使用本地Whisper", font=('Microsoft YaHei', small_font_size), foreground="white", bg=self.panel_bg)
        asr_enable_label.pack(anchor=tk.W, padx=20)
        
        asr_key_frame = ttk.Frame(asr_section)
        asr_key_frame.pack(fill=tk.X, pady=3)
        ttk.Label(asr_key_frame, text="API Key:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        asr_key_entry = ttk.Entry(asr_key_frame, textvariable=self.cloud_asr_api_key_var, font=('Microsoft YaHei', large_font_size), show="*")
        asr_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        asr_note = ttk.Label(asr_section, text="💡 使用OpenAI Whisper API，识别精度相当于本地large模型", font=('Microsoft YaHei', small_font_size), foreground="white")
        asr_note.pack(anchor=tk.W, padx=5)
        
        # ==================== 云端生图 ====================
        cloud_img_section = ttk.LabelFrame(panels["cloud_img"], text="🎨 云端生图 · 替代本地SD", padding=4, style="Adv.TLabelframe")
        cloud_img_section.pack(fill=tk.X)
        
        try:
            from video_generator.cloud_image_client import IMAGE_PROVIDER_CONFIG, get_cloud_image_config, get_image_provider_models
            img_config = get_cloud_image_config()
            img_available = True
        except ImportError:
            img_available = False
            img_config = {}
            IMAGE_PROVIDER_CONFIG = {}
        
        if not hasattr(self, 'cloud_image_enabled_var'):
            self.cloud_image_enabled_var = tk.BooleanVar(value=img_config.get("enabled", False))
        if not hasattr(self, 'cloud_image_provider_var'):
            self.cloud_image_provider_var = tk.StringVar(value=img_config.get("provider", "siliconflow"))
        if not hasattr(self, 'cloud_image_api_key_var'):
            self.cloud_image_api_key_var = tk.StringVar(value=img_config.get("api_key", ""))
        if not hasattr(self, 'cloud_image_model_var'):
            self.cloud_image_model_var = tk.StringVar(value=img_config.get("model", "stabilityai/stable-diffusion-xl-base-1.0"))
        if not hasattr(self, 'cloud_image_custom_url_var'):
            self.cloud_image_custom_url_var = tk.StringVar(value=img_config.get("custom_base_url", ""))
        
        cimg_enable_frame = ttk.Frame(cloud_img_section)
        cimg_enable_frame.pack(fill=tk.X, pady=3)
        cimg_enable_chk = ttk.Checkbutton(cimg_enable_frame, text="启用云端生图（替代本地SD，无需本地GPU画图）", variable=self.cloud_image_enabled_var, style="Cloud.TCheckbutton")
        cimg_enable_chk.pack(anchor=tk.W, padx=5)
        cimg_enable_label = tk.Label(cimg_enable_frame, text="⚡ 启用后所有图片由云端生成，风格预设将作为指令传递给云端模型", font=('Microsoft YaHei', small_font_size), foreground="white", bg=self.panel_bg)
        cimg_enable_label.pack(anchor=tk.W, padx=20)
        
        if img_available:
            cimg_provider_frame = ttk.Frame(cloud_img_section)
            cimg_provider_frame.pack(fill=tk.X, pady=3)
            ttk.Label(cimg_provider_frame, text="服务商:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
            
            img_provider_names = [f"{IMAGE_PROVIDER_CONFIG[pid]['name']}" for pid in IMAGE_PROVIDER_CONFIG]
            img_provider_ids = list(IMAGE_PROVIDER_CONFIG.keys())
            self._cloud_img_provider_ids = img_provider_ids
            
            cimg_provider_combo = ttk.Combobox(cimg_provider_frame, textvariable=self.cloud_image_provider_var, values=img_provider_names, state="readonly", font=('Microsoft YaHei', large_font_size))
            cimg_provider_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
            cimg_provider_combo.bind('<<ComboboxSelected>>', self._on_cloud_image_provider_changed)
        
        cimg_key_frame = ttk.Frame(cloud_img_section)
        cimg_key_frame.pack(fill=tk.X, pady=3)
        ttk.Label(cimg_key_frame, text="API Key:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        cimg_key_entry = ttk.Entry(cimg_key_frame, textvariable=self.cloud_image_api_key_var, font=('Microsoft YaHei', large_font_size), show="*")
        cimg_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        cimg_toggle_btn = ttk.Button(cimg_key_frame, text="👁", width=3, command=lambda: self._toggle_entry_visibility(cimg_key_entry), style="Small.TButton")
        cimg_toggle_btn.pack(side=tk.LEFT, padx=2)
        
        if img_available:
            cimg_model_frame = ttk.Frame(cloud_img_section)
            cimg_model_frame.pack(fill=tk.X, pady=3)
            ttk.Label(cimg_model_frame, text="模型:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
            
            current_img_provider = img_config.get("provider", "siliconflow")
            current_img_models = get_image_provider_models(current_img_provider)
            img_model_names = [f"{m['name']} - {m['desc']}" for m in current_img_models]
            self._cloud_img_model_ids = [m['id'] for m in current_img_models]
            
            cimg_model_combo = ttk.Combobox(cimg_model_frame, textvariable=self.cloud_image_model_var, values=img_model_names, state="readonly", font=('Microsoft YaHei', large_font_size))
            cimg_model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
            cimg_model_combo.bind('<<ComboboxSelected>>', self._on_cloud_image_model_changed)
            self._cloud_img_model_combo = cimg_model_combo
        
        cimg_btn_frame = ttk.Frame(cloud_img_section)
        cimg_btn_frame.pack(fill=tk.X, pady=3)
        
        self.btn_test_cloud_image = ttk.Button(cimg_btn_frame, text="🔗 测试连接", command=self._test_cloud_image_connection, style="Medium.TButton")
        self.btn_test_cloud_image.pack(side=tk.LEFT, padx=5, pady=2)
        
        if not hasattr(self, 'cloud_image_status_var'):
            self.cloud_image_status_var = tk.StringVar(value="❌ 未连接")
        self.cloud_image_status_label = ttk.Label(cimg_btn_frame, textvariable=self.cloud_image_status_var, font=('Microsoft YaHei', large_font_size), foreground="red")
        self.cloud_image_status_label.pack(side=tk.LEFT, padx=10)
        
        cimg_note = ttk.Label(cloud_img_section, text="💡 启用后，所有图片由云端生成，无需本地SD WebUI", font=('Microsoft YaHei', small_font_size), foreground="white")
        cimg_note.pack(anchor=tk.W, padx=5)
        
        # ==================== 本地模型预选 ====================
        model_section = ttk.LabelFrame(panels["optimize"], text="🔧 本地模型预选", padding=4, style="Adv.TLabelframe")
        model_section.pack(fill=tk.X)
        
        whisper_frame = ttk.Frame(model_section)
        whisper_frame.pack(fill=tk.X, pady=3)
        self._whisper_label = ttk.Label(whisper_frame, text="语音模型:", width=12, font=('Microsoft YaHei', large_font_size))
        self._whisper_label.pack(side=tk.LEFT, padx=5)
        
        whisper_options = ["tiny", "base", "small", "medium", "large"]
        self._whisper_combo = ttk.Combobox(whisper_frame, textvariable=self.whisper_model_var, values=whisper_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        self._whisper_combo.pack(fill=tk.X, padx=5, pady=2)
        
        ollama_frame = ttk.Frame(model_section)
        ollama_frame.pack(fill=tk.X, pady=3)
        self._ollama_label = ttk.Label(ollama_frame, text="Ollama模型:", width=12, font=('Microsoft YaHei', large_font_size))
        self._ollama_label.pack(side=tk.LEFT, padx=5)
        
        ollama_frame_right = ttk.Frame(ollama_frame)
        ollama_frame_right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self._ollama_button = ttk.Button(ollama_frame_right, textvariable=self.ollama_model_var, command=self.toggle_model_dropdown, style="Medium.TButton")
        self._ollama_button.pack(fill=tk.X, padx=5, pady=2)
        
        self.model_dropdown_frame = ttk.Frame(ollama_frame_right)
        self.model_dropdown_inner_frame = ttk.Frame(self.model_dropdown_frame)
        
        config_frame = ttk.Frame(model_section)
        config_frame.pack(fill=tk.X, pady=3)
        self._config_label = ttk.Label(config_frame, text="配置模式:", width=12, font=('Microsoft YaHei', large_font_size, 'bold'))
        self._config_label.pack(side=tk.LEFT, padx=5)
        
        self._config_combo = ttk.Combobox(
            config_frame, 
            textvariable=self.llm_config_preset_var, 
            values=self.llm_config_presets, 
            state="readonly",
            style="Config.TCombobox",
            height=10
        )
        self._config_combo.pack(fill=tk.X, padx=5, pady=2, ipady=3)
        self._config_combo.bind('<<ComboboxSelected>>', self.on_llm_config_changed)
        
        self._cloud_mode_note = ttk.Label(model_section, text="", font=('Microsoft YaHei', small_font_size), foreground="#ff9800")
        self._cloud_mode_note.pack(anchor=tk.W, padx=5, pady=(2, 0))
        
        self.cloud_llm_enabled_var.trace_add('write', self._on_cloud_llm_toggle_ui)
        self.cloud_asr_enabled_var.trace_add('write', self._on_cloud_asr_toggle_ui)
        self._update_local_model_panel_state()
        
        # ==================== 并发设置 ====================
        thread_section = ttk.LabelFrame(panels["thread"], text="⚡ 并发设置", padding=4, style="Adv.TLabelframe")
        thread_section.pack(fill=tk.X)
        
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
        
        # ==================== 主题自定义 ====================
        theme_section = ttk.LabelFrame(panels["theme"], text="🎯 主题自定义", padding=4, style="Adv.TLabelframe")
        theme_section.pack(fill=tk.X)
        
        theme_frame = ttk.Frame(theme_section)
        theme_frame.pack(fill=tk.X, pady=3)
        ttk.Label(theme_frame, text="核心主题:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        theme_entry = ttk.Entry(theme_frame, textvariable=self.custom_theme_var, font=('Microsoft YaHei', large_font_size))
        theme_entry.pack(fill=tk.X, padx=5, pady=2)
        
        tone_frame = ttk.Frame(theme_section)
        tone_frame.pack(fill=tk.X, pady=3)
        ttk.Label(tone_frame, text="视觉基调:", width=10, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        tone_entry = ttk.Entry(tone_frame, textvariable=self.custom_visual_tone_var, font=('Microsoft YaHei', large_font_size))
        tone_entry.pack(fill=tk.X, padx=5, pady=2)


    def setup_script_area(self):
        """设置脚本区域 - 已移除分镜脚本窗口，仅保留内部变量兼容性"""
        # 不再创建脚本区域UI，仅保留 txt_script 变量以兼容其他代码
        self.txt_script = None
    

    def setup_log_area(self):
        """设置日志区域 - 独占右侧面板"""
        log_frame = ttk.LabelFrame(self.log_frame_container, text="运行日志", padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill=tk.X, pady=(0, 5))
        
        self._auto_scroll_var = tk.BooleanVar(value=True)
        btn_toggle_scroll = ttk.Checkbutton(
            log_control_frame, text="📌 自动跟随",
            variable=self._auto_scroll_var,
            command=self._toggle_auto_scroll,
            style="Small.TCheckbutton"
        )
        btn_toggle_scroll.pack(side=tk.LEFT, padx=5)
        
        btn_clear_log = ttk.Button(log_control_frame, text="🗑️ 清除日志", command=self.clear_log, style="Small.TButton")
        btn_clear_log.pack(side=tk.RIGHT, padx=5)
        
        self.txt_log = tk.Text(log_frame, wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4", font=('Microsoft YaHei', self.font_size + 4))
        self.txt_log.pack(fill=tk.BOTH, expand=True)
        
        self._log_scrollbar = ttk.Scrollbar(self.txt_log, command=self._smart_yview if hasattr(self, '_smart_yview') else self.txt_log.yview)
        self._log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.txt_log.config(yscrollcommand=self._log_scrollbar.set)
        
        if hasattr(self, '_setup_smart_scroll'):
            self._setup_smart_scroll()
        
        self.log("📋 日志区域初始化完成")

    def check_for_updates(self):
        """检查更新"""
        try:
            from video_generator.auto_updater import check_and_notify_update
            check_and_notify_update(self.root, auto_check=False)
        except ImportError as e:
            self.log(f"⚠️ 更新模块未找到: {e}")
            messagebox.showwarning("提示", "自动更新功能尚未启用")
        except Exception as e:
            self.log(f"❌ 检查更新失败: {e}")
            messagebox.showerror("错误", f"检查更新失败:\n{str(e)}")
    
    def start_periodic_update_check(self, interval_hours=24):
        """启动定时更新检查
        
        Args:
            interval_hours: 检查间隔(小时),默认24小时
        """
        import threading
        import time
        
        def periodic_check():
            """后台定期检查更新"""
            while True:
                time.sleep(interval_hours * 3600)  # 转换为秒
                try:
                    self.log("🔄 正在后台检查更新...")
                    from video_generator.auto_updater import check_and_notify_update
                    # 静默检查,不打扰用户
                    check_and_notify_update(self.root, auto_check=True, silent=True)
                except Exception as e:
                    # 静默失败,不影响主程序
                    pass
        
        # 启动后台线程
        check_thread = threading.Thread(target=periodic_check, daemon=True)
        check_thread.start()
        self.log(f"✅ 已启动定时更新检查(每{interval_hours}小时)")
    
    def show_windows_notification(self, title, message, icon="info"):
        """显示Windows桌面通知
        
        Args:
            title: 通知标题
            message: 通知内容
            icon: 图标类型 (info/warning/error/success)
        """
        try:
            # 尝试使用Windows原生通知
            from winrt.windows.ui.notifications import ToastNotificationManager, ToastNotification
            from winrt.windows.data.xml.dom import XmlDocument
            
            # 获取模板
            notifier = ToastNotificationManager.create_toast_notifier()
            template_type = 0  # ToastText02
            
            if icon == "warning":
                template_type = 1  # ToastWarning
            elif icon == "error":
                template_type = 2  # ToastError
            
            xml = ToastNotificationManager.get_template_content(template_type)
            
            # 设置文本
            text_elements = xml.get_elements_by_tag_name("text")
            text_elements[0].append_child(xml.create_text_node(title))
            text_elements[1].append_child(xml.create_text_node(message))
            
            # 创建并显示通知
            toast = ToastNotification(xml)
            notifier.show(toast)
            
        except ImportError:
            # 如果winrt不可用,使用简单的tkinter弹窗
            import tkinter as tk
            from tkinter import messagebox
            
            if icon == "warning":
                messagebox.showwarning(title, message)
            elif icon == "error":
                messagebox.showerror(title, message)
            else:
                messagebox.showinfo(title, message)
        except Exception as e:
            # 降级到日志提示
            self.log(f"🔔 {title}: {message}")
