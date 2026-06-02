"""Resource management mixin - cache, thread pool, cleanup, file management."""
import os
import sys
import gc
import json
import time
import ctypes
import threading
import shutil
from concurrent.futures import ThreadPoolExecutor

from video_generator.config import Config, get_http_session
from video_generator.cache import prompt_cache, image_cache, SmartCache
from video_generator.ollama_client import is_ollama_available, stop_ollama_serve

class ResourceMixin:
    def _add_to_translation_cache(self, chinese, english):
        """将新翻译加入动态缓存"""
        if not hasattr(self, '_translation_cache'):
            self._translation_cache = {}
        if len(self._translation_cache) >= 500:
            keys = list(self._translation_cache.keys())
            for k in keys[:100]:
                del self._translation_cache[k]
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
        """初始化缓存系统 - 统一使用 SmartCache"""
        self._general_cache = SmartCache(max_size=1000, default_ttl=3600)
        self.log("✅ 缓存系统初始化完成")

    def cache_get(self, category, key):
        """获取缓存"""
        composite_key = f"{category}:{key}"
        return self._general_cache.get(composite_key)

    def cache_set(self, category, key, value):
        """设置缓存"""
        composite_key = f"{category}:{key}"
        self._general_cache.set(composite_key, value)

    def cache_clear(self, category=None):
        """清除缓存"""
        if category:
            self._general_cache.remove_by_prefix(f"{category}:")
        else:
            self._general_cache.clear()

    def get_cache_stats(self):
        """获取缓存统计信息"""
        return self._general_cache.get_stats()
    

    _last_unload_time = 0
    _UNLOAD_COOLDOWN = 5

    def _unload_ollama_models(self, log_prefix="", exit_mode=False):
        """卸载所有Ollama模型释放GPU显存（统一方法，替代4处重复代码）

        注意：此方法包含网络请求和等待，不应在主线程中调用。
        通过Ollama API确认模型已卸载，而非依赖PyTorch显存检测
        （Ollama是独立进程，PyTorch无法看到其显存占用）。
        
        Args:
            exit_mode: 退出模式，使用极短超时避免阻塞UI关闭
        """
        if not exit_mode:
            now = time.time()
            if now - self._last_unload_time < self._UNLOAD_COOLDOWN:
                return
            self._last_unload_time = now
        api_timeout = 1 if exit_mode else 5
        unload_timeout = 2 if exit_mode else 15
        poll_max = 2 if exit_mode else 10

        try:
            if is_ollama_available():
                status_resp = get_http_session().get(
                    f"{Config.OLLAMA_BASE_URL}/api/ps",
                    timeout=api_timeout
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
                                    timeout=unload_timeout
                                )
                            except Exception:
                                pass
                    if loaded_models:
                        released = False
                        for attempt in range(poll_max):
                            time.sleep(1)
                            try:
                                check_resp = get_http_session().get(
                                    f"{Config.OLLAMA_BASE_URL}/api/ps",
                                    timeout=api_timeout
                                )
                                if check_resp.status_code == 200:
                                    remaining = check_resp.json().get('models', [])
                                    if not remaining:
                                        released = True
                                        break
                            except Exception:
                                break
                        try:
                            import torch
                            if torch.cuda.is_available():
                                torch.cuda.empty_cache()
                        except Exception:
                            pass
                        if released:
                            self.log(f"{log_prefix}🧹 Ollama 模型已卸载，GPU 显存已释放")
                        else:
                            self.log(f"{log_prefix}🧹 Ollama 模型卸载指令已发送（显存释放中）")
        except Exception:
            pass


    def init_thread_pool(self):
        """初始化线程池"""
        if hasattr(self, 'executor') and self.executor is not None:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                self.executor.shutdown(wait=False)
            except Exception:
                pass

        try:
            import psutil
            cpu_count = os.cpu_count() or 4
            available_memory = psutil.virtual_memory().available / (1024 ** 3)
            self.max_workers = max(1, min(cpu_count, int(available_memory / 2), 8))
        except ImportError:
            self.max_workers = max(1, min(os.cpu_count() or 4, 4))
        
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
                self._log_exception(f"❌ 任务失败: {task['type']}", e)
            finally:
                self.thread_pool_stats['active_threads'] -= 1
                try:
                    self.thread_pool['tasks'].pop(task_id, None)
                except Exception:
                    pass
                with self.task_lock:
                    self.task_running = False
                    self.current_task = None
                # 处理下一个任务
                self.process_task_queue()
        
        # 在子线程中执行任务
        threading.Thread(target=run_task, daemon=True, name=f"Task-{task_id}").start()
    

    def _clear_internal_state(self, reset_audio=False, reset_cache_stats=False):
        """公共内部状态清理方法，被 _thorough_cleanup / _release_memory_resources / _reset_project_state 共用"""
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
            if hasattr(self, '_pregenerated_understandings_for_context'):
                delattr(self, '_pregenerated_understandings_for_context')
        except Exception:
            pass

        try:
            if hasattr(self, '_pregenerated_prompts_for_context'):
                delattr(self, '_pregenerated_prompts_for_context')
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
                if reset_audio and 'audio' in self.state_manager:
                    self.state_manager['audio'] = {
                        'loaded': False,
                        'path': None,
                        'duration': 0
                    }
                if 'images' in self.state_manager:
                    self.state_manager['images']['generated'] = False
                    self.state_manager['images']['count'] = 0
                if 'video' in self.state_manager:
                    self.state_manager['video']['generated'] = False
                    self.state_manager['video']['path'] = None
        except Exception:
            pass

        if reset_audio:
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
            if hasattr(self, '_general_cache'):
                self._general_cache.clear()
        except Exception:
            pass

        try:
            if hasattr(self, '_translation_cache'):
                self._translation_cache.clear()
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

        try:
            from video_generator.enhanced_content_recognition import get_enhanced_recognizer
            recognizer = get_enhanced_recognizer()
            if recognizer and hasattr(recognizer, 'reset_context'):
                recognizer.reset_context()
        except Exception:
            pass

    def _thorough_cleanup(self):
        """彻底清理所有分镜脚本数据和缓存 - 确保无残留（含磁盘文件+内存数据）"""
        self._move_output_to_trash(reason="thorough_cleanup")
        self._clear_internal_state(reset_audio=True, reset_cache_stats=True)

    # save_config / load_config 由 UIHandlersMixin 提供（完整版，含云端配置应用）
    # 此处不再重复定义，避免 MRO 覆盖导致云端配置丢失

    # _safe_release_whisper_gpu 由 AudioMixin 提供（更完善的版本，含 _whisper_on_gpu 标志管理）
    # 此处不再重复定义，避免 MRO 覆盖导致 GPU 状态不一致

    def _release_memory_resources(self):
        """只释放内存资源，不删除磁盘文件（用于程序退出时）"""
        self._safe_release_whisper_gpu()
        self._clear_internal_state(reset_audio=True, reset_cache_stats=True)


    def _get_trash_dir(self):
        if getattr(sys, 'frozen', False):
            return os.path.join(os.path.dirname(sys.executable), "trash")
        return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "trash")

    def _move_to_trash(self, file_path, trash_session_dir=None):
        try:
            if not os.path.exists(file_path):
                return False
            
            trash_dir = self._get_trash_dir()
            os.makedirs(trash_dir, exist_ok=True)

            if trash_session_dir is None:
                timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
                trash_session_dir = os.path.join(trash_dir, f"cleanup_{timestamp}")
            os.makedirs(trash_session_dir, exist_ok=True)
            
            filename = os.path.basename(file_path)
            dest = os.path.join(trash_session_dir, filename)
            if os.path.exists(dest):
                name, ext = os.path.splitext(filename)
                dest = os.path.join(trash_session_dir, f"{name}_{int(time.time()*1000)}{ext}")
            
            shutil.move(file_path, dest)
            return True
        except Exception as e:
            if hasattr(self, 'log'):
                self._log_exception(f"⚠️ move to trash failed: {os.path.basename(file_path)}", e)
            return False


    def _move_output_to_trash(self, reason="cleanup"):
        moved_count = 0
        try:
            trash_dir = self._get_trash_dir()
            os.makedirs(trash_dir, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
            trash_session_dir = os.path.join(trash_dir, f"output_project_{timestamp}")

            if not hasattr(self, 'output_dir'):
                self.log("⚠️ output_dir 未设置，跳过垃圾桶操作")
                return 0

            if not os.path.exists(self.output_dir):
                self.log(f"⚠️ output_dir 不存在: {self.output_dir}")
                return 0

            has_content = any(os.listdir(self.output_dir))
            if not has_content:
                return 0

            self.log(f"🗑️ 正在将输出目录移至垃圾桶({reason})...")

            # 方法1: 尝试整目录移动（最快，原子操作）
            try:
                shutil.move(self.output_dir, trash_session_dir)
                # 重新创建空的 output_dir 和 images_dir
                os.makedirs(self.output_dir, exist_ok=True)
                if hasattr(self, 'images_dir'):
                    os.makedirs(self.images_dir, exist_ok=True)
                self.log(f"✅ 已将输出目录移至垃圾桶: {trash_session_dir}")
                return 1
            except Exception as move_err:
                self.log(f"⚠️ 整目录移动失败，改用逐文件移动: {move_err}")

            # 方法2: 逐文件/子目录移动到垃圾桶（fallback）
            os.makedirs(trash_session_dir, exist_ok=True)

            for item in os.listdir(self.output_dir):
                src = os.path.join(self.output_dir, item)
                dst = os.path.join(trash_session_dir, item)

                if os.path.isfile(src):
                    try:
                        if os.path.exists(dst):
                            name, ext = os.path.splitext(item)
                            dst = os.path.join(trash_session_dir, f"{name}_{int(time.time()*1000)}{ext}")
                        shutil.move(src, dst)
                        moved_count += 1
                    except Exception as e:
                        self._log_exception(f"⚠️ 移动文件到垃圾桶失败: {item}", e)
                elif os.path.isdir(src):
                    try:
                        if os.path.exists(dst):
                            # 目标已存在，合并目录内容
                            for root, dirs, files in os.walk(src):
                                rel = os.path.relpath(root, src)
                                target_dir = os.path.join(dst, rel)
                                os.makedirs(target_dir, exist_ok=True)
                                for f in files:
                                    src_file = os.path.join(root, f)
                                    dst_file = os.path.join(target_dir, f)
                                    if not os.path.exists(dst_file):
                                        shutil.move(src_file, dst_file)
                                        moved_count += 1
                            # 尝试删除空的源目录
                            try:
                                shutil.rmtree(src, ignore_errors=True)
                            except Exception:
                                pass
                        else:
                            shutil.move(src, dst)
                            moved_count += 1
                    except Exception as e:
                        self._log_exception(f"⚠️ 移动目录到垃圾桶失败: {item}", e)

            # 确保 output_dir 和 images_dir 始终存在
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir, exist_ok=True)
            if hasattr(self, 'images_dir') and not os.path.exists(self.images_dir):
                os.makedirs(self.images_dir, exist_ok=True)

            if moved_count > 0:
                self.log(f"✅ 已将 {moved_count} 个文件/目录移至垃圾桶: {trash_session_dir}")
            else:
                self.log("⚠️ 垃圾桶操作完成，但未移动任何文件")

        except Exception as e:
            self._log_exception("⚠️ 移动文件到垃圾桶失败", e)
            # 确保 output_dir 始终存在
            try:
                if hasattr(self, 'output_dir') and not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir, exist_ok=True)
                if hasattr(self, 'images_dir') and not os.path.exists(self.images_dir):
                    os.makedirs(self.images_dir, exist_ok=True)
            except Exception:
                pass

        return moved_count


    def _cleanup_residual_files(self):
        self._move_output_to_trash(reason="auto_cleanup")

    def _list_trash_sessions(self):
        trash_dir = self._get_trash_dir()
        if not os.path.isdir(trash_dir):
            return []
        sessions = []
        for name in sorted(os.listdir(trash_dir), reverse=True):
            session_path = os.path.join(trash_dir, name)
            if not os.path.isdir(session_path):
                continue
            file_count = 0
            total_size = 0
            has_shots = False
            has_images = False
            has_video = False
            for root, dirs, files in os.walk(session_path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except OSError:
                        pass
                    file_count += 1
                    lf = f.lower()
                    if lf == "shots_data.json":
                        has_shots = True
                    elif lf.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                        has_images = True
                    elif lf.endswith((".mp4", ".avi", ".mkv", ".mov", ".webm")):
                        has_video = True
            sessions.append({
                "name": name,
                "path": session_path,
                "file_count": file_count,
                "total_size": total_size,
                "has_shots": has_shots,
                "has_images": has_images,
                "has_video": has_video,
            })
        return sessions

    def _restore_trash_session(self, session_path):
        if not os.path.isdir(session_path):
            return False
        try:
            output_dir = getattr(self, 'output_dir', None)
            if not output_dir:
                return False
            os.makedirs(output_dir, exist_ok=True)
            for item in os.listdir(session_path):
                src = os.path.join(session_path, item)
                dst = os.path.join(output_dir, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        for sub_root, sub_dirs, sub_files in os.walk(src):
                            rel = os.path.relpath(sub_root, src)
                            target_dir = os.path.join(dst, rel)
                            os.makedirs(target_dir, exist_ok=True)
                            for sf in sub_files:
                                sfp = os.path.join(sub_root, sf)
                                dfp = os.path.join(target_dir, sf)
                                if not os.path.exists(dfp):
                                    shutil.copy2(sfp, dfp)
                    else:
                        shutil.copytree(src, dst)
                else:
                    if not os.path.exists(dst):
                        shutil.copy2(src, dst)
            shutil.rmtree(session_path)
            return True
        except Exception as e:
            if hasattr(self, 'log'):
                self._log_exception("⚠️ restore from trash failed", e)
            return False

    def _delete_trash_session(self, session_path):
        if not os.path.isdir(session_path):
            return False
        try:
            shutil.rmtree(session_path)
            return True
        except Exception as e:
            if hasattr(self, 'log'):
                self._log_exception("⚠️ delete trash session failed", e)
            return False

    def _empty_trash(self):
        trash_dir = self._get_trash_dir()
        if not os.path.isdir(trash_dir):
            return 0
        count = 0
        for name in os.listdir(trash_dir):
            session_path = os.path.join(trash_dir, name)
            if os.path.isdir(session_path):
                try:
                    shutil.rmtree(session_path)
                    count += 1
                except Exception:
                    pass
        return count


    def on_close(self):
        """关闭窗口时的处理 - 确保快速退出"""
        # 防止重复调用
        if getattr(self, '_closing', False):
            return
        self._closing = True

        # 启动超时守护线程：3秒后强制退出，防止任何清理步骤卡死
        def _force_exit_watchdog():
            time.sleep(3)
            os._exit(0)
        import threading as _th
        _th.Thread(target=_force_exit_watchdog, daemon=False).start()

        try:
            self.log("🔄 正在关闭程序...")
        except Exception:
            pass

        # 1. 停止所有运行标志
        try:
            self.perf_monitor_running = False
            self.task_running = False
            self._api_heartbeat_running = False
            self._sd_api_connected = False
            if hasattr(self, '_api_heartbeat_event'):
                self._api_heartbeat_event.set()
        except Exception:
            pass

        # 2. 停止心跳（直接用已有实例，避免 LicenseManager() 阻塞）
        try:
            from video_generator.license_manager import LicenseManager
            if LicenseManager._instance is not None:
                LicenseManager._instance.stop_heartbeat()
        except Exception:
            pass

        # 3. 取消定时器
        try:
            if hasattr(self, 'resize_timer') and self.resize_timer:
                self.root.after_cancel(self.resize_timer)
                self.resize_timer = None
        except Exception:
            pass

        # 4. 保存配置
        try:
            self.save_config()
        except Exception:
            pass

        # 5. 释放任务锁
        try:
            with self.task_lock:
                self.task_paused = False
                self.pause_event.set()
                self.task_queue.clear()
                self.current_task = None
        except Exception:
            pass

        # 6. 关闭线程池
        try:
            if hasattr(self, 'executor') and self.executor is not None:
                try:
                    self.executor.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    self.executor.shutdown(wait=False)
                self.executor = None
        except Exception:
            pass

        try:
            if hasattr(self, 'parallel_prompt_generator') and self.parallel_prompt_generator is not None:
                self.parallel_prompt_generator.shutdown()
                self.parallel_prompt_generator = None
        except Exception:
            pass

        # 7. 终止视频渲染
        try:
            if hasattr(self, 'video_renderer') and self.video_renderer is not None:
                self.video_renderer.cancel_render()
                self.video_renderer = None
        except Exception:
            pass

        # 8. 关闭HTTP Session
        try:
            session = get_http_session()
            if session is not None:
                session.close()
        except Exception:
            pass

        # 9. 销毁窗口
        try:
            self.root.destroy()
        except Exception:
            pass

        # 10. 强制退出
        os._exit(0)
    
    # =======================================================================
    # 第十部分：主任务执行 - 生成分镜/图片/视频 (行 7995-8940)
    # =======================================================================

