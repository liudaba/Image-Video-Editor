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
        
        btn_generate = ttk.Button(section2, text="🎬 生成分镜脚本", command=self.generate_shots_threaded, style="LargeBlue.TButton")
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
        
        btn_render = ttk.Button(section5, text="🎞️ 生成视频", command=self.render_video_threaded, style="LargeRed.TButton")
        btn_render.pack(fill=tk.BOTH, expand=True, pady=5)
        


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
        
        # 性能统计按钮
        btn_stats = ttk.Button(status_frame, text="📊 性能统计", command=self.show_performance_stats, style="Medium.TButton")
        btn_stats.pack(fill=tk.X, pady=5)

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
        
        if not hasattr(self, 'model_var') or self.model_var.get() == "":
            self.model_var = tk.StringVar(value="使用当前模型")
        
        self._default_models = ["使用当前模型", "Stable Diffusion 1.5", "SDXL 1.0", "Flux Dev", "Stable Diffusion 3"]
        
        models = self._default_models
        
        model_combo = ttk.Combobox(model_frame, textvariable=self.model_var, values=models, state="readonly", font=("Microsoft YaHei", large_font_size))
        model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=2)
        
        self.model_combo = model_combo
        
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
        self.style_control_frame = ttk.Frame(style_section)
        self.style_control_frame.pack(fill=tk.X, pady=3)
        
        # 风格设置按钮
        self.style_dropdown_visible = False
        self.style_dropdown_frame = ttk.Frame(style_section)
        
        style_button = ttk.Button(self.style_control_frame, text="展开风格选项", command=self.toggle_style_dropdown, style="Medium.TButton")
        style_button.pack(fill=tk.X, padx=5, pady=2)
        
        # 风格预设网格布局（初始隐藏）
        self.style_grid = ttk.Frame(self.style_dropdown_frame)
        self.style_grid.pack(fill=tk.X, pady=3)
        
        # 创建风格预设复选框网格
        style_options = ["电影感", "纪录片风", "赛博朋克", "写实摄影", "皮克斯", "达芬奇", "油画", "多巴胺", "黑白线条", "吉卜力", "梵高", "日式动漫", "水彩"]
        
        # 复用__init__中已创建的dlr_vars（保留load_config恢复的值）
        existing_vars = {name: var for name, var in self.dlr_vars}
        
        # 3列网格布局
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
        
        # 加载保存的风格设置
        try:
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
        
        # 过渡效果设置
        transition_frame = ttk.Frame(video_section)
        transition_frame.pack(fill=tk.X, pady=3)
        ttk.Label(transition_frame, text="过渡效果:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        if not hasattr(self, 'transition_var'):
            self.transition_var = tk.StringVar(value="硬切")
        
        transition_options = ["硬切", "交叉淡化"]
        transition_combo = ttk.Combobox(transition_frame, textvariable=self.transition_var, values=transition_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        transition_combo.pack(fill=tk.X, padx=5, pady=2)
        
        # 5. 优化方法部分
        model_section = ttk.LabelFrame(adv_frame, text="🔧 优化方法", padding=15)
        model_section.pack(fill=tk.X, pady=5)
        
        # Whisper模型设置
        whisper_frame = ttk.Frame(model_section)
        whisper_frame.pack(fill=tk.X, pady=3)
        ttk.Label(whisper_frame, text="语音模型:", width=12, font=('Microsoft YaHei', large_font_size)).pack(side=tk.LEFT, padx=5)
        
        whisper_options = ["tiny", "base", "small", "medium", "large"]
        whisper_combo = ttk.Combobox(whisper_frame, textvariable=self.whisper_model_var, values=whisper_options, state="readonly", font=('Microsoft YaHei', large_font_size))
        whisper_combo.pack(fill=tk.X, padx=5, pady=2)
        
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
        
        # 并发线程数设置
        thread_section = ttk.LabelFrame(adv_frame, text="⚡ 并发设置", padding=15)
        thread_section.pack(fill=tk.X, pady=5)
        
        # 分镜创建线程数
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
        
        # 提示词生成线程数（新增）
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
        sd_prompt_btn = ttk.Button(prompt_options, text="SD提示词", command=lambda: self._on_prompt_type_changed("SD提示词"), style="Medium.TButton")
        sd_prompt_btn.pack(side=tk.LEFT, padx=5, pady=2, fill=tk.X, expand=True)

        # ARV绝对写实提示词按钮
        arv_prompt_btn = ttk.Button(prompt_options, text="ARV写实提示词", command=lambda: self._on_prompt_type_changed("ARV写实提示词"), style="Medium.TButton")
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
        
        # 应用按钮
        apply_frame = ttk.Frame(adv_frame)
        apply_frame.pack(fill=tk.X, pady=10)
        # 增大应用设置按钮的字体
        style = ttk.Style()
        style.configure("LargeGreen.TButton", font=('Microsoft YaHei', 14, 'bold'))
        btn_apply = ttk.Button(apply_frame, text="✅ 应用设置", command=self.apply_advanced_settings, style="LargeGreen.TButton")
        btn_apply.pack(fill=tk.X, padx=5, pady=8)


    def setup_script_area(self):
        """设置脚本区域 - 已移除分镜脚本窗口，仅保留内部变量兼容性"""
        # 不再创建脚本区域UI，仅保留 txt_script 变量以兼容其他代码
        self.txt_script = None
    

    def setup_log_area(self):
        """设置日志区域 - 独占右侧面板"""
        # 创建日志区域
        log_frame = ttk.LabelFrame(self.log_frame_container, text="运行日志", padding=15)
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
        
        self._log_scrollbar = ttk.Scrollbar(self.txt_log, command=self._smart_yview if hasattr(self, '_smart_yview') else self.txt_log.yview)
        self._log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.txt_log.config(yscrollcommand=self._log_scrollbar.set)
        
        if hasattr(self, '_setup_smart_scroll'):
            self._setup_smart_scroll()
        
        self.log("📋 日志区域初始化完成")
    

