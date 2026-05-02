"""UI initialization mixin - window setup, variables, system services."""
import os
import time
import threading
import warnings
import tkinter as tk
from tkinter import ttk, messagebox

from video_generator.config import Config
from video_generator.cache import prompt_cache, image_cache
from video_generator.ollama_client import (
    LLMConfig,
)
from video_generator.app_state import lazy_import, DEFAULT_MIN_SHOT_DURATION

try:
    from video_generator.arv_optimization import get_arv_prompter
    ARV_OPTIMIZATION_AVAILABLE = True
except ImportError:
    ARV_OPTIMIZATION_AVAILABLE = False

DEFAULT_MIN_SHOT_DURATION = Config.DEFAULT_MIN_SHOT_DURATION

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
        
        # 显示优化状态（不立即检测硬件）
        prompt_threads = self.prompt_thread_count_var.get() if hasattr(self, 'prompt_thread_count_var') else Config.DEFAULT_MAX_WORKERS
        thread_count = self.thread_count_var.get() if hasattr(self, 'thread_count_var') else 16
        print(f"🚀 性能优化已启用:")
        print(f"   - 并行提示词生成: {prompt_threads}线程（按需加载）")
        print(f"   - 图像生成线程: {thread_count}")
        print(f"   - 批量图像生成: 就绪")
        print(f"   - 视频编码器: 延迟检测（首次使用时）")
    

    def _initialize_ui(self):
        """初始化用户界面"""
        self.root.title("DocuMaker Pro Lite V7 | 智能分镜工作流 (SD API 连通版)")
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
        
        # 设置样式（只执行一次）
        self._setup_styles()
        self.root.configure(bg=self.bg_color)
        
        # 监听窗口大小变化事件
        self.root.bind("<Configure>", self.on_window_resize)
        
        # 标记UI初始化完成
        self._ui_initialized = True
    

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
            
            # LabelFrame 样式 - 板块标题字体加大加粗
            self.style.configure("TLabelframe", background=self.panel_bg, foreground="#e0e0e0",
                               font=("Microsoft YaHei", self.font_size + 4, "bold"),
                               relief="groove", borderwidth=2)
            self.style.configure("TLabelframe.Label", background=self.panel_bg, foreground="#90caf9",
                               font=("Microsoft YaHei", self.font_size + 4, "bold"))
            
            # 高级设置面板专用 LabelFrame 样式
            self.style.configure("Adv.TLabelframe", background="#2a2d35", foreground="#e0e0e0",
                               font=("Microsoft YaHei", self.font_size + 5, "bold"),
                               relief="groove", borderwidth=2)
            self.style.configure("Adv.TLabelframe.Label", background="#2a2d35", foreground="#90caf9",
                               font=("Microsoft YaHei", self.font_size + 5, "bold"))
            
            # 高级设置面板内部控件样式
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
        try:
            self._setup_styles()
            
            # 更新文本框字体大小
            if hasattr(self, 'txt_script') and self.txt_script:
                self.txt_script.configure(font=("Microsoft YaHei", self.font_size + 4))
            if hasattr(self, 'txt_log') and self.txt_log:
                self.txt_log.configure(font=("Microsoft YaHei", self.font_size + 4))
        except Exception:
            pass
    

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

        # 日志区域（独占右侧，分镜脚本窗口已移除）
        self.log_frame_container = ttk.Frame(self.right_paned)
        self.right_paned.add(self.log_frame_container, weight=1)
    

    def _initialize_variables(self):
        """初始化变量"""
        # 基本路径
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        self.thread_count_var = tk.IntVar(value=16)
        self.prompt_thread_count_var = tk.IntVar(value=Config.DEFAULT_MAX_WORKERS)
        
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
        self.resource_lock = threading.RLock()  # 用于保护共享资源的可重入锁
        self.task_executor = None
        self.max_workers = min((os.cpu_count() or 4) // 2, 4)
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
        # ========== 启动时清空所有全局缓存（确保全新开始）==========
        try:
            prompt_cache.clear()
            image_cache.clear()
            self.log("🗑️ 已清空全局缓存（prompt_cache + image_cache）")
        except Exception as e:
            self.log(f"⚠️ 清空全局缓存失败: {e}")
        
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

        # ARV提示词生成器（保持单例，确保分镜连贯性）
        self.arv_prompter = None
        if ARV_OPTIMIZATION_AVAILABLE:
            try:
                self.arv_prompter = get_arv_prompter()
            except Exception:
                pass

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
            time.sleep(1)  # 等待Ollama模块加载完成
            
            try:
                self._cleanup_residual_files()
            except Exception:
                pass
            
            self.system_check()
            time.sleep(1)
            cloud_img = False
            try:
                from video_generator.cloud_image_client import is_cloud_image_enabled
                cloud_img = is_cloud_image_enabled()
            except ImportError:
                pass
            if not cloud_img:
                self.check_sd_api_connection(silent=True)
            
            # 【修改】启动时自动检测并连接Ollama服务
            self.auto_connect_ollama()
        threading.Thread(target=delayed_system_check, daemon=True).start()
        
        # 预加载Whisper模型（延迟执行，让UI先加载）
        def preload_whisper():
            time.sleep(2)  # 等待UI完全加载后再预加载
            self.preload_whisper_model()
            
            # 所有预加载完成后，显示就绪提示
            time.sleep(0.5)  # 稍微延迟，确保日志输出顺序正确
            self.log("")
            self.log("=" * 60)
            self.log("✅ 程序启动完成，工具已就绪！")
            self.log("📂 请导入音频文件开始创作")
            self.log("=" * 60)
            self.log("")
        threading.Thread(target=preload_whisper, daemon=True).start()
        
        self._api_heartbeat_running = True
        def api_heartbeat():
            while self._api_heartbeat_running:
                time.sleep(30)
                if not self._api_heartbeat_running:
                    break
                self._check_api_heartbeat()
        threading.Thread(target=api_heartbeat, daemon=True).start()
    

