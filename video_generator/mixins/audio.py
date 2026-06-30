"""Audio management mixin - Whisper model, audio import/clear."""
import os
import gc
import traceback
import threading
import tkinter as tk
from video_generator.mixins.logging import safe_print_exc
from tkinter import ttk, filedialog, messagebox

from video_generator.cache import prompt_cache, image_cache
from video_generator.config import get_whisper_model_path

class AudioMixin:
    def preload_whisper_model(self):
        """预加载Whisper模型 - 仅加载到CPU，使用时再按需移至GPU，节省显存"""
        try:
            import whisper
            
            whisper_model_size = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
            
            self.log(f"🔄 预加载 Whisper {whisper_model_size} 模型到内存...")
            local_model = get_whisper_model_path(whisper_model_size)
            if local_model:
                self.log(f"   使用本地模型: {local_model}")
                self.whisper_model = whisper.load_model(local_model, device="cpu")
            else:
                self.whisper_model = whisper.load_model(whisper_model_size, device="cpu")
            self._whisper_model_size = whisper_model_size
            self.log(f"✅ Whisper {whisper_model_size} 模型预加载完成 (CPU，使用时自动加载到GPU)")
                
        except TypeError as e:
            # Python 3.14+ 与 whisper 包不兼容 (ctypes.CDLL(None) 失败)
            if "NoneType" in str(e):
                self.log(f"⚠️ Whisper模型预加载失败: Python 3.14 与当前 whisper 版本不兼容")
                self.log(f"   解决方案: pip install --upgrade openai-whisper 或降级到 Python 3.12/3.13")
            else:
                self.log(f"⚠️ Whisper模型预加载失败: {e}")
        except Exception as e:
            self.log(f"⚠️ Whisper模型预加载失败: {e}")
    
    # =======================================================================
    # 第二部分：设置面板与UI组件 (行 1949-2827)
    # =======================================================================

    def _safe_release_whisper_gpu(self, skip_gc=False):
        """安全释放Whisper模型占用的GPU显存和CPU内存（AudioMixin版本）

        注意：由于 MRO 顺序，AudioMixin 排在 ShotsMixin 之前，
        因此此版本是实际被 VideoGenApp 使用的版本。
        不要先 model.to("cpu") 再 del，这会在CPU上额外分配一份
        模型权重副本，反而增加内存峰值。直接 del 即可。
        无论模型在GPU还是CPU上，都会被删除释放内存。

        Args:
            skip_gc: 是否跳过gc.collect()。在后台线程中调用时可以跳过，
                     由调用方统一在适当时机执行gc.collect()以减少阻塞。
        """
        _cuda_available = False
        try:
            import torch
            _cuda_available = torch.cuda.is_available()
            if _cuda_available:
                torch.cuda.synchronize()
        except Exception:
            pass

        if not hasattr(self, 'whisper_model') or self.whisper_model is None:
            return

        try:
            del self.whisper_model
            self.whisper_model = None
            self._whisper_on_gpu = False
            self._whisper_model_size = None
        except Exception:
            pass

        if not skip_gc:
            try:
                gc.collect()
            except Exception:
                pass

        if _cuda_available:
            try:
                import torch
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except Exception:
                pass
    

    def import_audio(self):
        """导入音频 - 非阻塞版本，耗时操作移至后台线程"""
        self.log("📂 开始导入音频...")
        try:
            with self.task_lock:
                if self.task_running:
                    self.log("⚠️ 有任务正在运行，请等待任务完成后再导入音频")
                    messagebox.showwarning("任务运行中", "有任务正在运行，请等待任务完成后再导入音频！")
                    return
                self.task_running = True
            
            file_path = filedialog.askopenfilename(
                title="选择音频文件",
                filetypes=[("音频文件", "*.mp3 *.wav *.m4a *.flac"), ("所有文件", "*.*")]
            )
            
            if not file_path:
                self.log("⚠️ 用户取消了音频选择")
                with self.task_lock:
                    self.task_running = False
                return
            
            if not os.path.exists(file_path):
                self.log("❌ 音频文件不存在")
                messagebox.showerror("错误", "音频文件不存在")
                with self.task_lock:
                    self.task_running = False
                return
            
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            if file_size > 500:
                self.log(f"❌ 音频文件过大: {file_size:.2f}MB")
                messagebox.showerror("错误", f"音频文件过大，请选择小于500MB的文件")
                with self.task_lock:
                    self.task_running = False
                return
            
            has_existing_audio = self.state_manager.get('audio', {}).get('loaded', False)
            output_dir = getattr(self, 'output_dir', None)
            has_existing_output = False
            if output_dir and os.path.isdir(output_dir):
                has_existing_output = any(os.listdir(output_dir))
            
            if has_existing_audio or has_existing_output:
                if not messagebox.askyesno("确认", "导入新音频将清除当前所有分镜数据、图片和视频文件（移入垃圾桶保存），是否继续？"):
                    self.log("ℹ️ 已取消导入新音频")
                    with self.task_lock:
                        self.task_running = False
                    return
            
            self.audio_path = file_path
            self.state_manager['audio']['loaded'] = True
            self.state_manager['audio']['path'] = file_path
            
            self.log("🗑️ 后台清除旧分镜数据...")
            
            if hasattr(self, 'lbl_audio_status'):
                def update_ui_loading():
                    try:
                        self.lbl_audio_status.config(text=f"加载中: {os.path.basename(file_path)}...")
                    except Exception:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui_loading)
            
            def _import_audio_worker():
                try:
                    _was_on_gpu = getattr(self, '_whisper_on_gpu', False)
                    self._safe_release_whisper_gpu()
                    if _was_on_gpu:
                        self.log("   🧹 Whisper GPU资源已释放")
                    
                    self._move_output_to_trash(reason="new_audio")
                    self._reset_project_state(reset_audio_path=False)
                    
                    gc.collect()
                    
                    self.log("✅ 旧数据已清除，新音频将使用全新转录结果")
                    
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, self._finish_import_audio, file_path)
                except Exception as e:
                    self.log(f"❌ 音频导入后台处理失败: {e}")
                    safe_print_exc()
                finally:
                    with self.task_lock:
                        self.task_running = False
            
            threading.Thread(target=_import_audio_worker, daemon=True, name="ImportAudio").start()
            
        except Exception as e:
            self.log("❌ 音频导入失败，请检查文件格式是否支持")
            messagebox.showerror("错误", "音频导入失败，请检查文件格式是否支持。\n\n支持的格式：MP3、WAV、FLAC、OGG等")
            safe_print_exc()
            with self.task_lock:
                self.task_running = False
    
    def _finish_import_audio(self, file_path):
        """完成音频导入的UI更新（在主线程中执行）"""
        try:
            if hasattr(self, 'txt_script') and self.txt_script:
                self.txt_script.delete(1.0, tk.END)
                self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
            
            if hasattr(self, 'lbl_audio_status'):
                self.lbl_audio_status.config(text=f"已加载: {os.path.basename(file_path)}")
            
            self.log(f"✅ 音频导入完成: {os.path.basename(file_path)}")
        except Exception as e:
            self.log(f"⚠️ 音频导入UI更新失败: {e}")
    

    def _reset_project_state(self, reset_audio_path=False):
        """重置项目状态（公共方法，被 import_audio 和 clear_audio 共用）
        
        Args:
            reset_audio_path: 是否同时重置音频路径（clear_audio=True, import_audio=False）
        """
        self._clear_internal_state(reset_audio=reset_audio_path, reset_cache_stats=True)
        if not reset_audio_path:
            try:
                if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
                    if 'audio' in self.state_manager:
                        self.state_manager['audio']['duration'] = 0
            except Exception:
                pass


    def clear_audio(self):
        """清除音频 - 非阻塞版本，耗时操作移至后台线程"""
        if not messagebox.askyesno("确认清除", "清除音频将删除所有分镜数据和已生成的图片，此操作不可恢复！\n\n确定要清除吗？"):
            return
        
        try:
            with self.task_lock:
                if self.task_running:
                    self.log("⚠️ 有任务正在运行，请等待任务完成后再清除音频")
                    messagebox.showwarning("任务运行中", "有任务正在运行，请等待任务完成后再清除音频！")
                    return
                self.task_running = True
            
            self.log("🗑️ 清除音频")
            
            def _clear_audio_worker():
                try:
                    if hasattr(self, 'whisper_model') and self.whisper_model is not None:
                        self.log("🔄 释放Whisper模型内存...")
                        self._safe_release_whisper_gpu()
                        self._whisper_model_size = None
                        self.log("✅ Whisper模型内存已释放")
                    
                    self.audio_path = None
                    self._reset_project_state(reset_audio_path=True)
                    self._move_output_to_trash(reason="clear_audio")
                    
                    gc.collect()
                    
                    if hasattr(self, 'root') and self.root:
                        self.root.after(0, self._finish_clear_audio)
                except Exception as e:
                    self.log(f"❌ 音频清除失败: {e}")
                    safe_print_exc()
                finally:
                    with self.task_lock:
                        self.task_running = False
            
            threading.Thread(target=_clear_audio_worker, daemon=True, name="ClearAudio").start()
            
        except Exception as e:
            self.log(f"❌ 音频清除失败: {e}")
            safe_print_exc()
            with self.task_lock:
                self.task_running = False
    
    def _finish_clear_audio(self):
        """完成音频清除的UI更新（在主线程中执行）"""
        try:
            if hasattr(self, 'lbl_audio_status'):
                self.lbl_audio_status.config(text="未加载音频")
            
            if hasattr(self, 'txt_script') and self.txt_script:
                self.txt_script.delete(1.0, tk.END)
                self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
            
            self.log("✅ 音频清除完成")
        except Exception as e:
            self.log(f"⚠️ 音频清除UI更新失败: {e}")
    

