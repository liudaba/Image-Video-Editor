"""Resource management mixin - cache, thread pool, cleanup, file management."""
import os
import sys
import time
import gc
import datetime
import threading
import shutil
from concurrent.futures import ThreadPoolExecutor

from video_generator.config import Config, get_http_session
from video_generator.cache import prompt_cache, image_cache
from video_generator.ollama_client import is_ollama_available

class ResourceMixin:
    def _add_to_translation_cache(self, chinese, english):
        """将新翻译加入动态缓存"""
        if not hasattr(self, '_translation_cache'):
            self._translation_cache = {}
        self._translation_cache[chinese] = english
    

    def init_state_manager(self):
        """初始化状态管理器"""
        self.state_manager = {
            'app': {
                'status': 'ready',
                'current_workflow': None,
                'last_error': None
            },
            'audio': {
                'loaded': False,
                'path': None,
                'duration': 0
            },
            'shots': {
                'generated': False,
                'count': 0,
                'data': []
            },
            'images': {
                'generated': False,
                'count': 0,
                'path': self.images_dir
            },
            'video': {
                'generated': False,
                'path': None
            },
            'system': {
                'cpu_usage': 0,
                'memory_usage': 0,
                'gpu_usage': 0,
                'gpu_memory': 0
            }
        }
        self.log("✅ 状态管理器初始化完成")
    

    def init_event_system(self):
        """初始化事件系统"""
        self.event_system = {}
        self.log("✅ 事件系统初始化完成")
    
    # =======================================================================
    # 第九部分：系统初始化与缓存线程池 (行 7560-7900)
    # =======================================================================

    def init_cache_system(self):
        """初始化缓存系统"""
        self.cache_system = {
            'models': {},
            'prompts': {},
            'images': {},
            'audio': {}
        }
        # 缓存配置
        self.cache_config = {
            'max_size': 1000,  # 最大缓存项数
            'expiry_time': 3600,  # 缓存过期时间（秒）
            'cleanup_interval': 600  # 清理间隔（秒）
        }
        # 缓存统计信息
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'size': 0
        }
        # 缓存清理线程控制标志
        self.cache_cleanup_running = True
        # 启动缓存清理线程
        threading.Thread(target=self.cache_cleanup, daemon=True).start()
        self.log("✅ 缓存系统初始化完成")
    

    def cache_cleanup(self):
        """定期清理过期缓存"""
        while getattr(self, 'cache_cleanup_running', True):
            try:
                time.sleep(self.cache_config['cleanup_interval'])
                
                # 检查是否应该退出
                if not getattr(self, 'cache_cleanup_running', True):
                    break
                    
                current_time = time.time()
                evicted = 0
                
                for category in self.cache_system:
                    items_to_remove = []
                    for key, value in self.cache_system[category].items():
                        # 检查是否有过期时间
                        if isinstance(value, dict) and 'timestamp' in value:
                            if current_time - value['timestamp'] > self.cache_config['expiry_time']:
                                items_to_remove.append(key)
                    
                    # 移除过期项
                    for key in items_to_remove:
                        del self.cache_system[category][key]
                        evicted += 1
                
                if evicted > 0:
                    self.cache_stats['evictions'] += evicted
                    self.cache_stats['size'] = sum(len(items) for items in self.cache_system.values())
                    self.log(f"🔄 缓存清理完成，移除了 {evicted} 个过期项")
            except Exception as e:
                # 检查是否因为关闭导致的异常
                if not getattr(self, 'cache_cleanup_running', True):
                    break
                self.log(f"⚠️ 缓存清理失败: {e}")
    

    def cache_get(self, category, key):
        """获取缓存"""
        if category not in self.cache_system:
            self.cache_stats['misses'] += 1
            return None
        
        item = self.cache_system[category].get(key)
        if item is None:
            self.cache_stats['misses'] += 1
            return None
        
        # 检查是否过期
        if isinstance(item, dict) and 'timestamp' in item and 'value' in item:
            if time.time() - item['timestamp'] > self.cache_config['expiry_time']:
                del self.cache_system[category][key]
                self.cache_stats['misses'] += 1
                self.cache_stats['evictions'] += 1
                return None
            self.cache_stats['hits'] += 1
            return item['value']
        
        self.cache_stats['hits'] += 1
        return item
    

    def cache_set(self, category, key, value):
        """设置缓存"""
        if category not in self.cache_system:
            self.cache_system[category] = {}
        
        # 检查缓存大小
        current_size = sum(len(items) for items in self.cache_system.values())
        if current_size >= self.cache_config['max_size']:
            # 清理最旧的缓存项
            self._cleanup_oldest_cache()
        
        # 添加时间戳
        self.cache_system[category][key] = {
            'value': value,
            'timestamp': time.time()
        }
        
        self.cache_stats['size'] = sum(len(items) for items in self.cache_system.values())
    

    def _cleanup_oldest_cache(self):
        """清理最旧的缓存项"""
        oldest_item = None
        oldest_category = None
        oldest_key = None
        oldest_time = float('inf')
        
        for category in self.cache_system:
            for key, item in self.cache_system[category].items():
                if isinstance(item, dict) and 'timestamp' in item:
                    if item['timestamp'] < oldest_time:
                        oldest_time = item['timestamp']
                        oldest_item = item
                        oldest_category = category
                        oldest_key = key
        
        if oldest_key:
            del self.cache_system[oldest_category][oldest_key]
            self.cache_stats['evictions'] += 1
    

    def cache_clear(self, category=None):
        """清除缓存"""
        if category:
            if category in self.cache_system:
                self.cache_stats['evictions'] += len(self.cache_system[category])
                self.cache_system[category].clear()
        else:
            for cat in self.cache_system:
                self.cache_stats['evictions'] += len(self.cache_system[cat])
                self.cache_system[cat].clear()
        self.cache_stats['size'] = 0
    

    def get_cache_stats(self):
        """获取缓存统计信息"""
        return self.cache_stats
    

    def _unload_ollama_models(self, log_prefix=""):
        """卸载所有Ollama模型释放GPU显存（统一方法，替代4处重复代码）

        注意：此方法包含网络请求和等待，不应在主线程中调用。
        修复：轮询等待GPU显存真正释放，而非固定sleep。
        """
        try:
            if is_ollama_available():
                # 记录卸载前的GPU显存占用
                vram_before = 0
                try:
                    import torch
                    if torch.cuda.is_available():
                        vram_before = torch.cuda.memory_allocated() / 1024**3
                except Exception:
                    pass

                status_resp = get_http_session().get(
                    f"{Config.OLLAMA_BASE_URL}/api/ps",
                    timeout=5
                )
                if status_resp.status_code == 200:
                    loaded_models = status_resp.json().get('models', [])
                    for m in loaded_models:
                        model_name = m.get('name', '')
                        if model_name:
                            try:
                                get_http_session().post(
                                    f"{Config.OLLAMA_BASE_URL}/api/generate",
                                    json={"model": model_name, "keep_alive": 0, "stream": False},
                                    timeout=15
                                )
                            except Exception:
                                pass
                    if loaded_models:
                        # 轮询等待GPU显存真正释放（最多等15秒）
                        released = False
                        for attempt in range(15):
                            time.sleep(1)
                            try:
                                import torch
                                if torch.cuda.is_available():
                                    torch.cuda.empty_cache()
                                    vram_now = torch.cuda.memory_allocated() / 1024**3
                                    # 显存下降超过80%或低于1GB视为释放完成
                                    if vram_now < 1.0 or (vram_before > 0 and vram_now < vram_before * 0.2):
                                        released = True
                                        break
                            except Exception:
                                break
                        if released:
                            self.log(f"{log_prefix}🧹 Ollama 模型已卸载，GPU 显存已释放")
                        else:
                            self.log(f"{log_prefix}🧹 Ollama 模型卸载指令已发送（显存释放中）")
        except Exception:
            pass


    def init_thread_pool(self):
        """初始化线程池"""
        # 基于CPU核心数和系统内存动态调整线程池大小
        try:
            import psutil
            # 获取CPU核心数
            cpu_count = os.cpu_count() or 4
            # 获取可用内存（GB）
            available_memory = psutil.virtual_memory().available / (1024 ** 3)
            
            # 根据系统资源动态调整线程数
            # RTX 4000 + 8GB显存，优先使用GPU，线程数可以更多
            self.max_workers = min(cpu_count, int(available_memory / 2), 8)  # 最多8个线程
        except ImportError:
            # 如果psutil不可用，使用默认值
            self.max_workers = min(os.cpu_count() or 4, 4)
        
        # 初始化线程池
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.thread_pool = {
            'executor': self.executor,
            'tasks': {},
            'task_counter': 0
        }
        self.thread_pool_stats = {
            'active_threads': 0,
            'completed_tasks': 0,
            'failed_tasks': 0,
            'total_tasks': 0
        }
        self.log(f"✅ 线程池初始化完成，最大工作线程数: {self.max_workers}")
    

    def process_task_queue(self):
        """处理任务队列"""
        with self.task_lock:
            if self.task_running or not self.task_queue:
                return
            
            # 按优先级排序任务队列
            self.task_queue.sort(key=lambda task_id: self.thread_pool['tasks'][task_id]['priority'], reverse=True)
            
            # 获取下一个任务
            task_id = self.task_queue.pop(0)
            self.current_task = task_id
            self.task_running = True
        
        # 执行任务
        self.execute_task(task_id)
    

    def execute_task(self, task_id):
        """执行任务 - 在子线程中执行，避免阻塞UI"""
        task = self.thread_pool['tasks'].get(task_id)
        if not task:
            with self.task_lock:
                self.task_running = False
                self.current_task = None
            self.process_task_queue()
            return
        
        task['status'] = 'running'
        self.thread_pool_stats['active_threads'] += 1
        
        def run_task():
            """在子线程中执行任务"""
            try:
                if task['type'] == 'generate_shots':
                    self.generate_shots()
                elif task['type'] == 'generate_images':
                    self.generate_images()
                elif task['type'] == 'generate_video':
                    self.generate_video()
                
                task['status'] = 'completed'
                self.thread_pool_stats['completed_tasks'] += 1
                self.log(f"✅ 任务完成: {task['type']}")
            except Exception as e:
                task['status'] = 'failed'
                task['error'] = str(e)
                self.thread_pool_stats['failed_tasks'] += 1
                self.log(f"❌ 任务失败: {task['type']} - {e}")
            finally:
                self.thread_pool_stats['active_threads'] -= 1
                with self.task_lock:
                    self.task_running = False
                    self.current_task = None
                # 处理下一个任务
                self.process_task_queue()
        
        # 在子线程中执行任务
        threading.Thread(target=run_task, daemon=True, name=f"Task-{task_id}").start()
    

    def _thorough_cleanup(self):
        """彻底清理所有分镜脚本数据和缓存 - 确保无残留（含磁盘文件+内存数据）"""
        self._move_output_to_trash(reason="彻底清理")

        try:
            self.shots_data = []
        except Exception:
            pass

        try:
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
        except Exception:
            pass

        try:
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
        except Exception:
            pass

        try:
            if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                if 'shots' in self.state_manager:
                    self.state_manager['shots'] = {
                        'generated': False,
                        'count': 0,
                        'data': []
                    }
                if 'audio' in self.state_manager:
                    self.state_manager['audio'] = {
                        'loaded': False,
                        'path': None,
                        'duration': 0
                    }
                if 'images' in self.state_manager:
                    self.state_manager['images'] = {
                        'generated': False,
                        'count': 0,
                        'path': self.images_dir if hasattr(self, 'images_dir') else ''
                    }
                if 'video' in self.state_manager:
                    self.state_manager['video'] = {
                        'generated': False,
                        'path': None
                    }
        except Exception:
            pass

        try:
            if hasattr(self, 'total_audio_duration'):
                self.total_audio_duration = 0
        except Exception:
            pass

        try:
            if hasattr(self, 'audio_path'):
                self.audio_path = None
        except Exception:
            pass

        try:
            if hasattr(self, 'cache_system') and isinstance(self.cache_system, dict):
                for cat in list(self.cache_system.keys()):
                    self.cache_system[cat] = {}
        except Exception:
            pass

        try:
            if hasattr(self, 'cache_stats') and isinstance(self.cache_stats, dict):
                self.cache_stats = {
                    'hits': 0,
                    'misses': 0,
                    'evictions': 0,
                    'size': 0
                }
        except Exception:
            pass

        try:
            prompt_cache.clear()
        except Exception:
            pass

        try:
            image_cache.clear()
        except Exception:
            pass

        try:
            if hasattr(self, 'arv_prompter') and self.arv_prompter is not None:
                del self.arv_prompter
                self.arv_prompter = None
        except Exception:
            pass

        try:
            if hasattr(self, 'data_bus') and isinstance(self.data_bus, dict):
                self.data_bus.clear()
        except Exception:
            pass

        try:
            if hasattr(self, 'event_system') and isinstance(self.event_system, dict):
                self.event_system.clear()
        except Exception:
            pass


    def _release_memory_resources(self):
        """只释放内存资源，不删除磁盘文件（用于程序退出时）"""
        try:
            self.shots_data = []
        except Exception:
            pass

        try:
            if hasattr(self, '_pregenerated_prompts'):
                delattr(self, '_pregenerated_prompts')
        except Exception:
            pass

        try:
            if hasattr(self, '_shot_texts_for_context'):
                delattr(self, '_shot_texts_for_context')
        except Exception:
            pass

        try:
            if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                for key in self.state_manager:
                    if isinstance(self.state_manager[key], dict):
                        if 'data' in self.state_manager[key]:
                            self.state_manager[key]['data'] = []
                        if 'path' in self.state_manager[key]:
                            self.state_manager[key]['path'] = None
        except Exception:
            pass

        try:
            if hasattr(self, 'audio_path'):
                self.audio_path = None
        except Exception:
            pass

        try:
            if hasattr(self, 'cache_system') and isinstance(self.cache_system, dict):
                for cat in list(self.cache_system.keys()):
                    self.cache_system[cat] = {}
        except Exception:
            pass

        try:
            prompt_cache.clear()
        except Exception:
            pass

        try:
            image_cache.clear()
        except Exception:
            pass

        try:
            if hasattr(self, 'arv_prompter') and self.arv_prompter is not None:
                del self.arv_prompter
                self.arv_prompter = None
        except Exception:
            pass

        try:
            if hasattr(self, 'data_bus') and isinstance(self.data_bus, dict):
                self.data_bus.clear()
        except Exception:
            pass

        try:
            if hasattr(self, 'event_system') and isinstance(self.event_system, dict):
                self.event_system.clear()
        except Exception:
            pass


    def _move_to_trash(self, file_path, trash_session_dir=None):
        """将文件移动到垃圾桶而非直接删除
        
        Args:
            file_path: 要移动的文件路径
            trash_session_dir: 垃圾桶会话目录，如果为None则自动创建
        Returns:
            bool: 是否成功移动
        """
        try:
            if not os.path.exists(file_path):
                return False
            
            trash_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "垃圾桶")
            if not os.path.exists(trash_dir):
                os.makedirs(trash_dir)
            
            if trash_session_dir is None:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                trash_session_dir = os.path.join(trash_dir, f"清理_{timestamp}")
            if not os.path.exists(trash_session_dir):
                os.makedirs(trash_session_dir)
            
            filename = os.path.basename(file_path)
            dest = os.path.join(trash_session_dir, filename)
            if os.path.exists(dest):
                name, ext = os.path.splitext(filename)
                dest = os.path.join(trash_session_dir, f"{name}_{int(time.time()*1000)}{ext}")
            
            shutil.move(file_path, dest)
            return True
        except Exception as e:
            if hasattr(self, 'log'):
                self.log(f"⚠️ 移动文件到垃圾桶失败: {os.path.basename(file_path)} - {e}")
            return False


    def _move_output_to_trash(self, reason="清理"):
        """将output_project中的所有文件移动到垃圾桶
        
        Args:
            reason: 清理原因，用于日志和子文件夹命名
        Returns:
            int: 移动的文件数量
        """
        moved_count = 0
        try:
            trash_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "垃圾桶")
            if not os.path.exists(trash_dir):
                os.makedirs(trash_dir)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            trash_session_dir = os.path.join(trash_dir, f"{reason}_{timestamp}")
            os.makedirs(trash_session_dir)
            
            if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
                shots_file = os.path.join(self.output_dir, "shots_data.json")
                if os.path.exists(shots_file):
                    if self._move_to_trash(shots_file, trash_session_dir):
                        moved_count += 1

                if hasattr(self, 'images_dir') and os.path.exists(self.images_dir):
                    images_trash_dir = os.path.join(trash_session_dir, "images")
                    os.makedirs(images_trash_dir, exist_ok=True)
                    for f in os.listdir(self.images_dir):
                        fp = os.path.join(self.images_dir, f)
                        if os.path.isfile(fp):
                            if self._move_to_trash(fp, images_trash_dir):
                                moved_count += 1

                for f in os.listdir(self.output_dir):
                    fp = os.path.join(self.output_dir, f)
                    if os.path.isfile(fp):
                        if self._move_to_trash(fp, trash_session_dir):
                            moved_count += 1
            
            if moved_count > 0:
                self.log(f"🗑️ 已将 {moved_count} 个文件移至垃圾桶: {trash_session_dir}")
        except Exception as e:
            self.log(f"⚠️ 移动文件到垃圾桶失败: {e}")
        
        return moved_count


    def _cleanup_residual_files(self):
        """清理残留的磁盘文件，移动到垃圾桶而非直接删除"""
        self._move_output_to_trash(reason="自动清理")


    def on_close(self):
        """关闭窗口时的处理 - 增强版，确保快速退出并彻底清除所有残留数据"""
        try:
            self.log("🔄 正在关闭程序，清理资源...")
        except Exception:
            pass

        try:
            self.perf_monitor_running = False
            self.cache_cleanup_running = False
            self.task_running = False
            self._api_heartbeat_running = False
            self.sd_connected = False
        except Exception:
            pass

        try:
            if hasattr(self, 'resize_timer') and self.resize_timer:
                self.root.after_cancel(self.resize_timer)
                self.resize_timer = None
        except Exception:
            pass

        try:
            self.save_config()
        except Exception:
            pass

        try:
            with self.task_lock:
                self.task_paused = False
                self.pause_event.set()
                self.task_queue.clear()
                self.current_task = None
        except Exception:
            pass

        try:
            if hasattr(self, 'executor'):
                try:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self.executor.shutdown(wait=False)
        except Exception:
            pass

        try:
            for attr in ['_active_audio', '_active_background', '_active_final_clip']:
                clip = getattr(self, attr, None)
                if clip is not None:
                    try:
                        clip.close()
                    except Exception:
                        pass
                    setattr(self, attr, None)
            active_clips = getattr(self, '_active_clips', None)
            if active_clips is not None:
                for c in active_clips:
                    try: c.close()
                    except: pass
                self._active_clips = None
        except Exception:
            pass

        try:
            if self.whisper_model is not None:
                if self._whisper_on_gpu:
                    try:
                        import torch
                        self.whisper_model = self.whisper_model.to("cpu")
                        torch.cuda.synchronize()
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    self._whisper_on_gpu = False
                del self.whisper_model
                self.whisper_model = None

            gc.collect()
        except Exception:
            pass

        try:
            session = get_http_session()
            if session is not None:
                session.close()
        except Exception:
            pass

        try:
            self._release_memory_resources()
        except Exception:
            pass

        try:
            self._cleanup_residual_files()
        except Exception:
            pass

        try:
            gc.collect()
        except Exception:
            pass

        try:
            if self.executor is not None:
                self.executor.shutdown(wait=False)
                self.executor = None
        except Exception:
            pass

        try:
            self.log("✅ 资源清理完成，正在退出...")
        except Exception:
            pass

        try:
            self.root.destroy()
        except Exception:
            pass

        try:
            if sys.stdout and hasattr(sys.stdout, 'close'):
                try:
                    sys.stdout.close()
                except Exception:
                    pass
            if sys.stderr and hasattr(sys.stderr, 'close'):
                try:
                    sys.stderr.close()
                except Exception:
                    pass
            if sys.platform == "win32":
                ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

        sys.exit(0)
    
    # =======================================================================
    # 第十部分：主任务执行 - 生成分镜/图片/视频 (行 7995-8940)
    # =======================================================================

