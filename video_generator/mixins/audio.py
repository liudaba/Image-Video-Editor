"""Audio management mixin - Whisper model, audio import/clear."""
import os
import gc
import traceback
import tkinter as tk
from video_generator.mixins.logging import safe_print_exc
from tkinter import ttk, filedialog, messagebox

from video_generator.cache import prompt_cache, image_cache

class AudioMixin:
    def preload_whisper_model(self):
        """预加载Whisper模型 - 仅加载到CPU，使用时再按需移至GPU，节省显存"""
        try:
            import whisper
            
            whisper_model_size = self.whisper_model_var.get() if hasattr(self, 'whisper_model_var') else "medium"
            
            self.log(f"🔄 预加载 Whisper {whisper_model_size} 模型到内存...")
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

    def _safe_release_whisper_gpu(self):
        """安全释放Whisper GPU显存 - 仅在Whisper确实在GPU上时才调用torch.cuda
        
        避免在Whisper不在GPU上时调用torch.cuda.is_available()，
        因为该调用会触发CUDA Context创建，导致显存被永久占用。
        """
        if not self._whisper_on_gpu or self.whisper_model is None:
            return
        
        try:
            import torch
            if torch.cuda.is_available():
                device = next(self.whisper_model.parameters()).device
                if device.type == "cuda":
                    self.whisper_model = self.whisper_model.to("cpu")
                    torch.cuda.synchronize()
                    torch.cuda.empty_cache()
                    self._whisper_on_gpu = False
        except (StopIteration, Exception):
            try:
                import torch
                self.whisper_model = self.whisper_model.to("cpu")
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                self._whisper_on_gpu = False
            except Exception:
                pass
    

    def import_audio(self):
        """导入音频"""
        self.log("📂 开始导入音频...")
        try:
            with self.task_lock:
                if self.task_running:
                    self.log("⚠️ 有任务正在运行，请等待任务完成后再导入音频")
                    messagebox.showwarning("任务运行中", "有任务正在运行，请等待任务完成后再导入音频！")
                    return
            
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                title="选择音频文件",
                filetypes=[("音频文件", "*.mp3 *.wav *.m4a *.flac"), ("所有文件", "*.*")]
            )
            
            if not file_path:
                self.log("⚠️ 用户取消了音频选择")
                return
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                self.log("❌ 音频文件不存在")
                messagebox.showerror("错误", "音频文件不存在")
                return
            
            # 检查文件大小（限制为500MB）
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            if file_size > 500:
                self.log(f"❌ 音频文件过大: {file_size:.2f}MB")
                messagebox.showerror("错误", f"音频文件过大，请选择小于500MB的文件")
                return
            
            # 保存音频路径
            self.audio_path = file_path
            self.state_manager['audio']['loaded'] = True
            self.state_manager['audio']['path'] = file_path
            
            # 清除旧的分镜数据和缓存，防止新音频混入旧音频的转录内容
            if self.state_manager.get('audio', {}).get('loaded', False):
                if not messagebox.askyesno("确认", "导入新音频将清除当前所有分镜数据和图片，是否继续？"):
                    self.log("ℹ️ 已取消导入新音频")
                    return
            self.log("🗑️ 清除旧分镜数据，防止混入旧音频内容...")
            
            # 释放Whisper GPU资源（如果上次任务异常退出未释放）
            self._safe_release_whisper_gpu()
            if not self._whisper_on_gpu:
                self.log("   🧹 Whisper GPU资源已释放")
            
            self._move_output_to_trash(reason="导入新音频")
            self._reset_project_state(reset_audio_path=False)
            
            if hasattr(self, 'txt_script') and self.txt_script:
                def clear_script():
                    try:
                        self.txt_script.delete(1.0, tk.END)
                        self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, clear_script)
            
            gc.collect()
            
            self.log("✅ 旧数据已清除，新音频将使用全新转录结果")
            
            # 更新UI
            if hasattr(self, 'lbl_audio_status'):
                def update_ui():
                    try:
                        self.lbl_audio_status.config(text=f"已加载: {os.path.basename(file_path)}")
                    except Exception as e:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            self.log(f"✅ 音频导入完成: {os.path.basename(file_path)}")
            
        except Exception as e:
            self.log(f"❌ 音频导入失败: {e}")
            messagebox.showerror("错误", f"音频导入失败: {str(e)}")
            safe_print_exc()
    

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
        """清除音频"""
        if not messagebox.askyesno("确认清除", "清除音频将删除所有分镜数据和已生成的图片，此操作不可恢复！\n\n确定要清除吗？"):
            return
        self.log("🗑️ 清除音频")
        try:
            if self.whisper_model is not None:
                self.log("🔄 释放Whisper模型内存...")
                self._safe_release_whisper_gpu()
                del self.whisper_model
                self.whisper_model = None
                self._whisper_model_size = None
                self._whisper_on_gpu = False
                gc.collect()
                self.log("✅ Whisper模型内存已释放")
            
            self.audio_path = None
            self._reset_project_state(reset_audio_path=True)
            self._move_output_to_trash(reason="清除音频")
            
            # 更新UI
            if hasattr(self, 'lbl_audio_status'):
                def update_ui():
                    try:
                        self.lbl_audio_status.config(text="未加载音频")
                        if hasattr(self, 'txt_script') and self.txt_script:
                            self.txt_script.delete(1.0, tk.END)
                            self.txt_script.insert(tk.END, "# 分镜脚本将在此显示\n")
                    except Exception:
                        pass
                if hasattr(self, 'root') and self.root:
                    self.root.after(0, update_ui)
            
            gc.collect()
            self.log("✅ 音频清除完成")
        except Exception as e:
            self.log(f"❌ 音频清除失败: {e}")
            safe_print_exc()
    

