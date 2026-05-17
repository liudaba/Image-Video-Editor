"""UI initialization mixin - window setup, variables, system services."""
import os
import sys
import time
import threading
import warnings
import tkinter as tk
from tkinter import ttk, messagebox

from video_generator.config import Config
from video_generator.cache import prompt_cache, image_cache
from video_generator.version import get_version
from video_generator.ollama_client import (
    LLMConfig,
)
from video_generator.app_state import lazy_import, DEFAULT_MIN_SHOT_DURATION

try:
    from video_generator.arv_optimization import get_arv_prompter
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False

class UIInitMixin:
    def __init__(self, root):
        """初始化应用程序"""
        self.root = root
        
        self.video_renderer = None
        
        self._initialize_ui()
        self._initialize_variables()
        self._initialize_systems()
        self._setup_ui_components()
        self._initialize_event_handlers()
        self._start_system_services()
        
        thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 8
    

    def _update_membership_title(self):
        try:
            from video_generator.license_manager import LicenseManager
            mgr = LicenseManager()
            account_info = mgr.get_account_info()
            version_str = f"短视频生成器 v{get_version()}"
            base_title = f"{version_str} | 智能分镜工作流"

            parts = [base_title]
            username = account_info.get("username", "")
            if username:
                parts.append(username)
            membership_name = account_info.get("membership_type_name", "")
            if membership_name:
                parts.append(membership_name)

            title_text = " | ".join(parts)

            self.root.title(title_text)
        except Exception:
            self.root.title(f"短视频生成器 v{get_version()} | 智能分镜工作流")

    def _initialize_ui(self):
        """初始化用户界面"""
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # 初始化完成标志 - 防止启动时resize事件触发样式重设
        self._ui_initialized = False
        
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
        self.resize_delay = 500  # 增加防抖延迟到500毫秒
        
        # 窗口大小跟踪
        self.current_width = 1000
        self.current_height = 700
        
        # 先创建布局
        self._create_layout()
        self._update_membership_title()
        
        # 设置样式（只执行一次）
        self._setup_styles()
        self.root.configure(bg=self.bg_color)
        
        # 监听窗口大小变化事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 标记UI初始化完成
        self._ui_initialized = True
    

    def _setup_styles(self):
        """设置UI样式（只在初始化时调用一次）"""
        try:
            self.style = ttk.Style()
            if 'clam' in self.style.theme_names():
                self.style.theme_use('clam')
            
            self.style.configure("TFrame", background=self.bg_color)
            self.style.configure("TLabel", background=self.bg_color, foreground=self.text_fg, font=("Microsoft YaHei", self.font_size + 2))
            self.style.configure("Header.TLabel", background=self.bg_color, foreground="#00bcd4", font=("Microsoft YaHei", self.font_size + 4, "bold"))
            
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
            
            self.style.configure("TCheckbutton", background=self.bg_color, foreground=self.text_fg, 
                               font=("Microsoft YaHei", self.font_size))
            
            self.style.configure("TLabelframe", background=self.panel_bg, foreground="#e0e0e0",
                               font=("Microsoft YaHei", self.font_size + 4, "bold"),
                               relief="groove", borderwidth=2)
            self.style.configure("TLabelframe.Label", background=self.panel_bg, foreground="#90caf9",
                               font=("Microsoft YaHei", self.font_size + 4, "bold"))
            
            self.style.configure("Adv.TLabelframe", background="#2a2d35", foreground="#e0e0e0",
                               font=("Microsoft YaHei", self.font_size + 5, "bold"),
                               relief="groove", borderwidth=2)
            self.style.configure("Adv.TLabelframe.Label", background="#2a2d35", foreground="#90caf9",
                               font=("Microsoft YaHei", self.font_size + 5, "bold"))
            
            self.style.configure("Adv.TFrame", background="#2a2d35")
            self.style.configure("Adv.TLabel", background="#2a2d35", foreground="#cccccc",
                               font=("Microsoft YaHei", self.font_size + 2))
            self.style.configure("Adv.TCheckbutton", background="#2a2d35", foreground="#cccccc",
                               font=("Microsoft YaHei", self.font_size + 2))
            self.style.configure("Adv.TButton", background="#3c4f6e", foreground="#ffffff",
                               font=("Microsoft YaHei", self.font_size + 3), padding=(8, 6), relief="flat")
            self.style.map("Adv.TButton", background=[('active', '#4a6a9a')])
            self.style.configure("Adv.TCombobox",
                               font=("Microsoft YaHei", self.font_size + 2),
                               padding=(6, 4))
            self.style.configure("Adv.TEntry",
                               font=("Microsoft YaHei", self.font_size + 2),
                               padding=(4, 4))
            
            self.style.configure("TProgressbar", 
                               thickness=20,
                               background="#00FF00",
                               troughcolor="#1a1a1a",
                               borderwidth=0)
            
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

    _FONT_STYLES = {
        "TLabel": 2, "Header.TLabel": 4,
        "LargeBlue.TButton": 6, "LargeRed.TButton": 6, "LargeGreen.TButton": 6,
        "Medium.TButton": 4, "Small.TButton": 2,
        "TCheckbutton": 0,
        "TLabelframe": 4, "TLabelframe.Label": 4,
        "Adv.TLabelframe": 5, "Adv.TLabelframe.Label": 5,
        "Adv.TLabel": 2, "Adv.TCheckbutton": 2,
        "Adv.TButton": 3, "Adv.TCombobox": 2, "Adv.TEntry": 2,
        "Config.TCombobox": 4,
    }

    def _update_fonts_only(self):
        """仅更新字体属性，不重建样式表（窗口缩放时调用）"""
        try:
            for style_name, offset in self._FONT_STYLES.items():
                bold = "bold" if style_name in (
                    "Header.TLabel", "LargeBlue.TButton", "LargeRed.TButton",
                    "LargeGreen.TButton",
                    "TLabelframe", "TLabelframe.Label",
                    "Adv.TLabelframe", "Adv.TLabelframe.Label", "Adv.TButton",
                ) else ""
                font = ("Microsoft YaHei", self.font_size + offset, bold) if bold else ("Microsoft YaHei", self.font_size + offset)
                self.style.configure(style_name, font=font)
            
            if hasattr(self, 'txt_script') and self.txt_script:
                self.txt_script.configure(font=("Microsoft YaHei", self.font_size + 4))
            if hasattr(self, 'txt_log') and self.txt_log:
                self.txt_log.configure(font=("Microsoft YaHei", self.font_size + 4))
        except Exception:
            pass
    

    def on_window_resize(self, event):
        """窗口大小变化时的处理"""
        # UI未完成初始化时不处理
        if not getattr(self, '_ui_initialized', False):
            return
        
        # 只处理窗口大小变化，忽略其他Configure事件
        if event.widget != self.root:
            return
        
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
        """处理窗口大小变化的实际逻辑 - 优化版"""
        # 计算缩放比例
        width = event.width
        height = event.height
        
        # 基于窗口宽度计算字体大小
        scale_factor = min(width / 1000, height / 700)
        new_font_size = max(8, int(self.base_font_size * scale_factor))
        
        # 只有字体大小变化超过2个像素才更新，避免频繁重设样式
        if abs(new_font_size - self.font_size) >= 2:
            self.font_size = new_font_size
            # 使用after延迟执行样式更新，避免阻塞UI
            self.root.after(100, self._update_fonts_async)
    

    def _update_fonts_async(self):
        """异步更新字体，避免阻塞UI"""
        self.root.after_idle(self._update_fonts_only)
    

    def _create_layout(self):
        self.top_bar = tk.Frame(self.root, bg="#0d2137", height=36)
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)

        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.main_paned, width=280)
        self.main_paned.add(self.left_frame, weight=0)

        self.right_paned = ttk.PanedWindow(self.main_paned, orient=tk.VERTICAL)
        self.main_paned.add(self.right_paned, weight=1)

        self.log_frame_container = ttk.Frame(self.right_paned)
        self.right_paned.add(self.log_frame_container, weight=1)

        self._create_top_bar()

    def _create_top_bar(self):
        self.auth_status_label = tk.Label(
            self.top_bar,
            text="",
            font=("Microsoft YaHei", 10),
            bg="#0d2137",
            fg="#9ca3af",
            cursor="hand2",
            padx=10,
            pady=2,
        )
        self.auth_status_label.pack(side=tk.RIGHT, padx=(0, 8), pady=2)
        self.auth_status_label.bind("<Button-1>", lambda e: self._show_login_dialog())
        self.auth_status_label.bind("<Enter>", lambda e: self.auth_status_label.configure(fg="#ffffff"))
        self.auth_status_label.bind("<Leave>", self._on_auth_label_leave)

    def _on_auth_label_leave(self, event):
        if hasattr(self, '_auth_label_color') and self._auth_label_color:
            self.auth_status_label.configure(fg=self._auth_label_color)
        else:
            self.auth_status_label.configure(fg="#9ca3af")

    def _update_auth_status_label(self, text, color="#9ca3af", bg="#0d2137"):
        self._auth_label_color = color
        self.auth_status_label.configure(text=text, fg=color, bg=bg)

    def _set_action_buttons_state(self, state):
        if state == "normal":
            authed = getattr(self, '_auth_valid', False)
            if not authed:
                state = "disabled"
                self._update_auth_status_label("⚠️ 授权已中断 - 点击登录", "#ef4444", "#2d1215")
        for btn_attr in ("btn_generate", "btn_render"):
            btn = getattr(self, btn_attr, None)
            if btn:
                try:
                    btn.configure(state=state)
                except Exception:
                    pass
        if state == "disabled":
            self._show_cancel_button(True)
        else:
            self._show_cancel_button(False)

    def _show_cancel_button(self, show):
        btn = getattr(self, 'btn_cancel', None)
        if btn:
            try:
                if show:
                    btn.pack(fill=tk.X, pady=(0, 5))
                else:
                    btn.pack_forget()
            except Exception:
                pass

    def _cancel_current_task(self):
        with self.task_lock:
            if self.task_running:
                self.task_running = False
                self.task_paused = False
                self.pause_event.set()
                self.log("⏹ 用户已请求停止任务...")
                self._show_cancel_button(False)
                renderer = getattr(self, 'video_renderer', None)
                if renderer:
                    try:
                        renderer.cancel_render()
                    except Exception:
                        pass

    def _deferred_auth_check(self):
        self._auth_valid = False
        self._set_action_buttons_state("disabled")
        self._update_auth_status_label("验证授权中...", "#9ca3af", "#0d2137")

        def _check():
            try:
                from video_generator.license_manager import LicenseManager
                mgr = LicenseManager()
                license_status = mgr.check_license()
                if license_status["valid"]:
                    mgr.start_heartbeat()
                    mgr.set_auth_revoked_callback(lambda: self.root.after(0, self._on_auth_revoked))
                    mgr.set_auth_recovered_callback(lambda: self.root.after(0, self._on_auth_recovered))
                    display = mgr.get_membership_display()
                    self.root.after(0, lambda: self._on_auth_valid(display))
                elif mgr._try_silent_relogin():
                    license_status = mgr.check_license()
                    if license_status["valid"]:
                        mgr.start_heartbeat()
                        mgr.set_auth_revoked_callback(lambda: self.root.after(0, self._on_auth_revoked))
                        mgr.set_auth_recovered_callback(lambda: self.root.after(0, self._on_auth_recovered))
                        display = mgr.get_membership_display()
                        self.root.after(0, lambda: self._on_auth_valid(display))
                    else:
                        self.root.after(0, self._on_auth_invalid)
                else:
                    self.root.after(0, self._on_auth_invalid)
            except Exception as e:
                print(f"[AUTH] Deferred auth check error: {e}")
                self.root.after(0, self._on_auth_invalid)

        threading.Thread(target=_check, daemon=True).start()

    def _on_auth_valid(self, display_text):
        self._auth_valid = True
        self._set_action_buttons_state("normal")
        try:
            from video_generator.license_manager import LicenseManager
            mgr = LicenseManager()
            account_info = mgr.get_account_info()
        except Exception:
            account_info = {}

        is_lifetime = account_info.get("is_lifetime", False)
        is_trial = account_info.get("is_trial", False)
        days_left = account_info.get("days_left", 0)

        if is_lifetime:
            self._update_auth_status_label("✅ 终身", "#FFD700", "#0d2137")
        elif is_trial:
            self._update_auth_status_label(f"⏳ 试用期剩余{days_left}天", "#f59e0b", "#1a2744")
        elif days_left > 0:
            self._update_auth_status_label(f"⏳ 剩余{days_left}天", "#f59e0b", "#1a2744")
        else:
            self._update_auth_status_label("✅ 已授权", "#10b981", "#0d3325")

        self._update_membership_title()

    def _on_auth_invalid(self):
        self._auth_valid = False
        self._set_action_buttons_state("normal")
        self._update_auth_status_label("未登录 - 点击登录", "#f59e0b", "#1a2744")
        self._update_membership_title()

    def _on_auth_revoked(self):
        try:
            from video_generator.license_manager import LicenseManager
            mgr = LicenseManager()
            server_ok = mgr.verify_with_server()
            if server_ok:
                license_status = mgr.check_license()
                if license_status["valid"]:
                    self._on_auth_recovered()
                    return
            else:
                license_status = mgr.check_license()
                if license_status["valid"]:
                    self._on_auth_recovered()
                    return
        except Exception:
            pass
        self._auth_valid = False
        self._set_action_buttons_state("disabled")
        self._update_auth_status_label("授权已失效 - 点击重新登录", "#ef4444", "#2d1215")
        self._update_membership_title()
        try:
            from tkinter import messagebox
            messagebox.showwarning("授权失效", "您的账号已被禁用或授权已失效，请重新登录。")
        except Exception:
            pass
        self._show_login_dialog()

    def _on_auth_recovered(self):
        try:
            from video_generator.license_manager import LicenseManager
            mgr = LicenseManager()
            display = mgr.get_membership_display()
            self._on_auth_valid(display)
        except Exception:
            self._deferred_auth_check()

    def _show_login_dialog(self):
        try:
            from video_generator.auth_dialogs import LoginDialog
            dialog = LoginDialog(self.root)
            self.root.wait_window(dialog)
            if dialog.result:
                self._deferred_auth_check()
        except Exception as e:
            print(f"[AUTH] Show login dialog error: {e}")

    def _initialize_variables(self):
        """初始化变量"""
        # 基本路径
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.output_dir = os.path.join(self.base_dir, "output_project")
        self.images_dir = os.path.join(self.output_dir, "images")
        self.config_file = os.path.join(self.base_dir, "config.json")
        
        # 创建必要的目录
        os.makedirs(self.images_dir, exist_ok=True)
        
        # 核心变量
        self.audio_path = None
        self.shots_data = []
        self.total_audio_duration = 0
        self.MIN_SHOT_DURATION = DEFAULT_MIN_SHOT_DURATION
        self.whisper_model = None
        self._whisper_on_gpu = False
        self._whisper_model_size = None
        self._log_buffer = []
        self._log_counter = 0
        self.executor = None
        
        # API设置
        self.api_var = tk.StringVar(value="Stable Diffusion API")
        self.sd_api_url_var = tk.StringVar(value="http://127.0.0.1:8080")
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
        
        # 并发线程数设置 - 初始默认值，由高级设置面板和load_config覆盖
        self.thread_count_var = tk.IntVar(value=8)
        
        # 分镜批处理大小设置 - 初始默认值，由高级设置面板和load_config覆盖
        self.batch_size_var = tk.IntVar(value=2)
        
        # 最短分镜时长设置 - 初始默认值，由load_config覆盖
        self.min_shot_duration_var = tk.DoubleVar(value=DEFAULT_MIN_SHOT_DURATION)
        
        # 音频模型设置 - 初始默认值，由load_config覆盖
        self.whisper_model_var = tk.StringVar(value="medium")
        
        # 云端大模型设置 - 初始默认值，由load_config覆盖
        self.cloud_llm_enabled_var = tk.BooleanVar(value=False)
        self.cloud_llm_provider_var = tk.StringVar(value="DeepSeek 深度求索")
        self.cloud_llm_api_key_var = tk.StringVar(value="")
        self.cloud_llm_model_var = tk.StringVar(value="deepseek-chat")
        self.cloud_llm_custom_url_var = tk.StringVar(value="")
        self.cloud_llm_status_var = tk.StringVar(value="❌ 未连接")
        self._cloud_selected_model_id = "deepseek-chat"
        self.cloud_asr_enabled_var = tk.BooleanVar(value=False)
        self.cloud_asr_api_key_var = tk.StringVar(value="")
        
        self.cloud_image_enabled_var = tk.BooleanVar(value=False)
        self.cloud_image_provider_var = tk.StringVar(value="硅基流动 SiliconFlow")
        self.cloud_image_api_key_var = tk.StringVar(value="")
        self.cloud_image_model_var = tk.StringVar(value="")
        self.cloud_image_custom_url_var = tk.StringVar(value="")
        
        # 风格预设 - 预创建变量，确保load_config能恢复风格设置
        style_options = ["电影感", "纪录片风", "赛博朋克", "写实摄影", "皮克斯", "达芬奇", "油画", "多巴胺", "黑白线条", "吉卜力", "梵高", "日式动漫", "水彩"]
        self.dlr_vars = [(opt, tk.BooleanVar()) for opt in style_options]
        
        # 模型下拉菜单（分镜脚本窗口已移除，这些frame暂不挂载到UI）
        self.model_dropdown_frame = ttk.Frame(self.log_frame_container)
        self.transition_dropdown_frame = ttk.Frame(self.log_frame_container)
        
        # 任务管理
        self.task_queue = []
        self.current_task = None
        self.task_running = False
        self.task_paused = False
        self.task_lock = threading.Lock()
        self.resource_lock = threading.RLock()
        self.task_executor = None
        self.max_workers = min((os.cpu_count() or 4) // 2, 4)
        self.pause_event = threading.Event()
        self._sd_api_connected = False
        self._waiting_for_sd = False
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
        self.event_system = {}
        self.state_manager = {}
        self.data_bus = {}

        self.cache_system = {
            'models': {},
            'prompts': {},
            'images': {},
            'audio': {}
        }

        self.thread_pool = {}
        self.thread_pool_stats = {
            'active_threads': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_tasks': 0
        }

        try:
            prompt_cache.clear()
            image_cache.clear()
        except Exception:
            pass

        self.arv_prompter = None
        if ARV_OPTIMIZATION_AVAILABLE:
            try:
                self.arv_prompter = get_arv_prompter()
            except Exception:
                pass

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
        threading.Thread(target=lazy_import, daemon=True).start()

        self._readiness = {
            'config': False,
            'auth': False,
            'dependencies': False,
            'ollama': False,
            'sd_api': False,
            'whisper_model': False,
            'ffmpeg': False,
        }
        self._gpu_info = ""

        def delayed_system_check():
            time.sleep(0.5)

            self._detect_gpu_info_async()

            self.root.after(0, lambda: self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))
            self.root.after(0, lambda: self.log("  系统自检开始"))
            self.root.after(0, lambda: self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"))

            try:
                self._cleanup_residual_files()
            except Exception:
                pass

            self._readiness['config'] = True
            self.root.after(0, lambda: self.log("  [1/7] ✅ 配置文件加载完成"))

            auth_ok = False
            try:
                from video_generator.license_manager import LicenseManager
                mgr = LicenseManager()
                result = mgr.check_license()
                auth_ok = result.get('valid', False)
            except Exception:
                pass
            self._readiness['auth'] = auth_ok
            if auth_ok:
                self.root.after(0, lambda: self.log("  [2/7] ✅ 授权认证通过"))
            else:
                self.root.after(0, lambda: self.log("  [2/7] ❌ 授权认证未通过（请先登录或激活软件）"))

            self.system_check()
            self._readiness['dependencies'] = True
            self.root.after(0, lambda: self.log("  [3/7] ✅ 系统依赖项检查完成"))

            cloud_img = getattr(self, '_cloud_img_enabled', False)
            cloud_llm = getattr(self, '_cloud_llm_enabled', False)

            if cloud_img:
                self._readiness['sd_api'] = True
                provider = getattr(self, '_cloud_img_provider', '')
                model = getattr(self, '_cloud_img_model', '')
                self.root.after(0, lambda: self.log(f"  [4/7] ✅ 云端图片服务已启用（{provider} / {model}）"))
            else:
                self._check_sd_api_impl(silent=True)
                sd_ok = getattr(self, '_sd_api_connected', False)
                if sd_ok:
                    self._readiness['sd_api'] = True
                    self.root.after(0, lambda: self.log("  [4/7] ✅ Stable Diffusion API 已连接"))
                else:
                    self.root.after(0, lambda: self.log("  [4/7] ⚠️ Stable Diffusion API 未连接（图片生成不可用）"))

            self.auto_connect_ollama(silent=True)
            from video_generator.ollama_client import is_ollama_available
            ollama_ok = is_ollama_available()
            if cloud_llm:
                self._readiness['ollama'] = True
                provider = getattr(self, '_cloud_llm_provider', '')
                model = getattr(self, '_cloud_llm_model', '')
                self.root.after(0, lambda: self.log(f"  [5/7] ✅ 云端大模型已启用（{provider} / {model}）"))
            elif ollama_ok:
                self._readiness['ollama'] = True
                ollama_model = self.ollama_model_var.get() if hasattr(self, 'ollama_model_var') else ''
                self.root.after(0, lambda: self.log(f"  [5/7] ✅ Ollama 大模型已连接（{ollama_model}）"))
            else:
                self.root.after(0, lambda: self.log("  [5/7] ⚠️ 大模型服务未连接（分镜生成不可用）"))

            import shutil
            ffmpeg_found = False
            if shutil.which('ffmpeg'):
                ffmpeg_found = True
            elif os.path.exists(os.path.join(getattr(self, 'base_dir', ''), 'ffmpeg', 'ffmpeg.exe')):
                ffmpeg_found = True
            self._readiness['ffmpeg'] = ffmpeg_found
            if ffmpeg_found:
                self.root.after(0, lambda: self.log("  [6/7] ✅ FFmpeg 音视频工具已就绪"))
            else:
                self.root.after(0, lambda: self.log("  [6/7] ⚠️ FFmpeg 未找到（视频合成不可用）"))

            whisper_model_dir = os.path.join(getattr(self, 'base_dir', ''), 'whisper_models')
            has_whisper = False
            if os.path.isdir(whisper_model_dir):
                has_whisper = any(f.endswith('.pt') for f in os.listdir(whisper_model_dir))
            if not has_whisper:
                whisper_cache = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
                if os.path.isdir(whisper_cache):
                    has_whisper = any(f.endswith('.pt') for f in os.listdir(whisper_cache))
            self._readiness['whisper_model'] = has_whisper
            if has_whisper:
                whisper_name = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else 'medium'
                self.root.after(0, lambda: self.log(f"  [7/7] ✅ Whisper 语音识别模型已就绪（{whisper_name}）"))
            else:
                self.root.after(0, lambda: self.log("  [7/7] ⚠️ Whisper 模型未下载（首次使用时将自动下载）"))

            self.root.after(0, self._show_readiness_summary)

        threading.Thread(target=delayed_system_check, daemon=True).start()

        self._api_heartbeat_running = True
        self._api_heartbeat_event = threading.Event()
        def api_heartbeat():
            while self._api_heartbeat_running:
                self._api_heartbeat_event.wait(timeout=30)
                self._api_heartbeat_event.clear()
                if not self._api_heartbeat_running:
                    break
                self._check_api_heartbeat()
                self.root.after(0, self._update_membership_title)
        threading.Thread(target=api_heartbeat, daemon=True).start()

    def _show_readiness_summary(self):
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("  系统就绪状态汇总")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        core_labels = {
            'config': '配置文件',
            'auth': '授权认证',
            'dependencies': '系统依赖',
        }
        feature_labels = {
            'ollama': 'AI 大模型',
            'sd_api': '图片生成',
            'whisper_model': '语音识别',
            'ffmpeg': '音视频处理',
        }
        feature_hints = {
            'ollama': '未连接',
            'sd_api': 'SD API未连接',
            'whisper_model': '模型未下载',
            'ffmpeg': '未安装',
        }

        self.log("  【核心条件】")
        core_all_ok = True
        for key, label in core_labels.items():
            ok = self._readiness.get(key, False)
            if not ok:
                core_all_ok = False
            self.log(f"    {'✅' if ok else '❌'} {label} — {'已就绪' if ok else '未就绪'}")

        self.log("  【功能条件】")
        feature_missing = []
        for key, label in feature_labels.items():
            ok = self._readiness.get(key, False)
            if not ok:
                feature_missing.append(label)
            hint = '已就绪' if ok else feature_hints.get(key, '未就绪')
            self.log(f"    {'✅' if ok else '⚠️ '} {label} — {hint}")

        thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 8
        self.log("  【性能配置】")
        gpu_info = getattr(self, '_gpu_info', '')
        if gpu_info:
            self.log(f"    🖥️ GPU: {gpu_info}")
        else:
            self.log(f"    🖥️ GPU: 未检测到NVIDIA显卡")
        self.log(f"    🔧 分镜创建线程: {thread_count}")
        self.log(f"    🔧 提示词生成: 本地单线程 / 云端4线程（自动切换）")
        self.log(f"    🔧 批量图像生成: 就绪")
        self.log(f"    🔧 视频编码器: 延迟检测（首次使用时）")

        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if core_all_ok:
            if feature_missing:
                missing_str = "、".join(feature_missing)
                self.log(f"  ⚠️ 以下功能暂不可用: {missing_str}")
                self.log(f"     不影响基础操作，对应功能需条件满足后方可使用")
            self.log("  🎬 核心条件已全部具备，可以导入音频开始创作！")
        else:
            self.log(f"  ❌ 核心条件未全部具备，当前无法正常使用")
            if not self._readiness.get('auth'):
                self.log(f"     → 授权认证未通过：请先登录或激活软件")
            if not self._readiness.get('dependencies'):
                self.log(f"     → 系统依赖缺失：请检查安装是否完整")
            if not self._readiness.get('config'):
                self.log(f"     → 配置文件异常：请检查 config.json")

        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    

