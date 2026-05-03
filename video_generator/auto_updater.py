"""
短视频生成器 - 自动更新系统 (Tkinter版本)
功能:
1. 检查最新版本
2. 显示更新通知
3. 下载更新包
4. 引导安装
"""

import json
import os
import sys
import requests
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime


class UpdateManager:
    """更新管理器 - 单例模式"""
    
    _instance = None
    UPDATE_API_URL = "https://api.videogen.com/api/version/latest"
    CURRENT_VERSION = "1.0.0"  # 从配置文件读取
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.version_info = None
            cls._instance.load_config()
        return cls._instance
    
    def load_config(self):
        """加载配置获取当前版本"""
        try:
            config_file = os.path.join(os.path.dirname(__file__), '..', 'config.json')
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.CURRENT_VERSION = config.get('version', '1.0.0')
        except:
            pass
    
    def check_for_updates(self, callback=None):
        """检查更新(异步)
        
        Args:
            callback: 回调函数,接收(has_update, version_info)参数
        """
        def check_thread():
            try:
                response = requests.get(
                    self.UPDATE_API_URL,
                    params={"current_version": self.CURRENT_VERSION},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('has_update'):
                        self.version_info = data
                        
                        # 判断更新优先级
                        priority = data.get('priority', 'normal')  # low/normal/high/critical
                        force_update = data.get('force_update', False)
                        
                        # 根据优先级决定通知方式
                        if priority == 'critical' or force_update:
                            # 强制更新或严重安全漏洞 - 必须立即通知
                            data['notification_type'] = 'forced_popup'
                        elif priority == 'high':
                            # 重要功能更新 - 弹窗提示
                            data['notification_type'] = 'popup'
                        elif priority == 'normal':
                            # 常规更新 - 日志提示
                            data['notification_type'] = 'log_only'
                        else:
                            # 小修复 - 静默记录
                            data['notification_type'] = 'silent'
                        
                        if callback:
                            callback(True, data)
                    else:
                        if callback:
                            callback(False, None)
                else:
                    if callback:
                        callback(None, f"服务器错误: {response.status_code}")
            
            except requests.exceptions.Timeout:
                if callback:
                    callback(None, "检查超时,请检查网络连接")
            except requests.exceptions.ConnectionError:
                if callback:
                    callback(None, "无法连接到更新服务器")
            except Exception as e:
                if callback:
                    callback(None, f"检查失败: {str(e)}")
        
        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
    
    def download_update(self, download_url, save_path, progress_callback=None, complete_callback=None, error_callback=None):
        """下载更新包
        
        Args:
            download_url: 下载地址
            save_path: 保存路径
            progress_callback: 进度回调(downloaded, total, percentage)
            complete_callback: 完成回调(file_path)
            error_callback: 错误回调(error_msg)
        """
        def download_thread():
            try:
                response = requests.get(download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if total_size > 0 and progress_callback:
                                percentage = int((downloaded / total_size) * 100)
                                progress_callback(downloaded, total_size, percentage)
                
                if complete_callback:
                    complete_callback(save_path)
            
            except Exception as e:
                if error_callback:
                    error_callback(f"下载失败: {str(e)}")
        
        thread = threading.Thread(target=download_thread, daemon=True)
        thread.start()
    
    @staticmethod
    def format_size(size_bytes):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"


class UpdateDialog(tk.Toplevel):
    """更新对话框窗口"""
    
    def __init__(self, parent, auto_check=False):
        super().__init__(parent)
        self.parent = parent
        self.auto_check = auto_check
        self.update_manager = UpdateManager()
        self.is_downloading = False
        
        self.title("检查更新")
        self.geometry("600x450")
        self.resizable(False, False)
        
        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (450 // 2)
        self.geometry(f"+{x}+{y}")
        
        self.init_ui()
        
        if auto_check:
            self.check_updates()
    
    def init_ui(self):
        """初始化UI"""
        # 主框架
        main_frame = ttk.Frame(self, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(
            main_frame, 
            text="🔄 版本更新",
            font=("Microsoft YaHei", 16, "bold")
        )
        title_label.pack(pady=(0, 15))
        
        # 状态标签
        self.status_var = tk.StringVar(value="正在检查更新...")
        status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei", 11),
            foreground="#666"
        )
        status_label.pack(pady=(0, 10))
        
        # 更新内容框架
        changelog_frame = ttk.LabelFrame(main_frame, text="更新内容:", padding="10")
        changelog_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 更新日志文本框
        self.changelog_text = tk.Text(
            changelog_frame,
            height=8,
            wrap=tk.WORD,
            font=("Microsoft YaHei", 10),
            state=tk.DISABLED
        )
        scrollbar = ttk.Scrollbar(changelog_frame, orient=tk.VERTICAL, command=self.changelog_text.yview)
        self.changelog_text.configure(yscrollcommand=scrollbar.set)
        
        self.changelog_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 进度条框架
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        
        self.progress_var = tk.StringVar(value="")
        progress_label = ttk.Label(
            progress_frame,
            textvariable=self.progress_var,
            font=("Microsoft YaHei", 9),
            foreground="#666"
        )
        progress_label.pack()
        
        # 隐藏进度条
        self.progress_bar.pack_forget()
        progress_label.pack_forget()
        
        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        # 检查更新按钮
        self.check_btn = ttk.Button(btn_frame, text="检查更新", command=self.check_updates)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 下载按钮
        self.download_btn = ttk.Button(btn_frame, text="立即下载", command=self.start_download)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.download_btn.pack_forget()  # 初始隐藏
        
        # 取消按钮
        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.cancel_download)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn.pack_forget()  # 初始隐藏
        
        # 关闭按钮
        close_btn = ttk.Button(btn_frame, text="关闭", command=self.destroy)
        close_btn.pack(side=tk.RIGHT)
    
    def check_updates(self):
        """检查更新"""
        self.status_var.set("正在检查更新...")
        self.update_changelog("")
        self.download_btn.pack_forget()
        self.check_btn.config(state=tk.DISABLED)
        
        def on_check_complete(has_update, result):
            if has_update is None:
                # 检查失败
                self.status_var.set(f"❌ {result}")
                self.check_btn.config(state=tk.NORMAL)
            elif has_update:
                # 有新版本
                self.show_update_available(result)
            else:
                # 已是最新
                self.status_var.set("✅ 您使用的是最新版本!")
                self.update_changelog("暂无更新内容")
                self.check_btn.config(state=tk.NORMAL)
        
        self.update_manager.check_for_updates(on_check_complete)
    
    def show_update_available(self, version_info):
        """显示可用更新"""
        self.version_info = version_info
        
        self.status_var.set(
            f"✨ 发现新版本 v{version_info['version']}!\n"
            f"发布日期: {version_info['release_date']}"
        )
        
        # 显示更新日志
        changelog = "\n".join([f"• {item}" for item in version_info.get('changelog', [])])
        self.update_changelog(changelog)
        
        # 显示下载按钮
        file_size = UpdateManager.format_size(version_info.get('file_size', 0))
        self.download_btn.config(text=f"下载更新 ({file_size})")
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.NORMAL)
        
        # 强制更新提示
        if version_info.get('force_update'):
            messagebox.showwarning(
                "重要更新",
                "此版本包含重要修复,建议您立即更新!"
            )
    
    def update_changelog(self, text):
        """更新日志显示"""
        self.changelog_text.config(state=tk.NORMAL)
        self.changelog_text.delete(1.0, tk.END)
        self.changelog_text.insert(tk.END, text)
        self.changelog_text.config(state=tk.DISABLED)
    
    def start_download(self):
        """开始下载"""
        if not hasattr(self, 'version_info'):
            return
        
        # 设置保存路径
        save_dir = os.path.join(os.getenv('TEMP', ''), 'VideoGen_Update')
        filename = f"VideoGen_v{self.version_info['version']}_Setup.exe"
        save_path = os.path.join(save_dir, filename)
        
        # 显示进度条
        self.download_btn.pack_forget()
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        self.check_btn.config(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.progress_bar['value'] = 0
        
        # 找到progress_label并显示
        for widget in self.progress_bar.master.winfo_children():
            if isinstance(widget, ttk.Label):
                widget.pack()
                break
        
        self.is_downloading = True
        
        def on_progress(downloaded, total, percentage):
            self.progress_bar['value'] = percentage
            self.progress_var.set(
                f"下载中... {UpdateManager.format_size(downloaded)} / "
                f"{UpdateManager.format_size(total)} ({percentage}%)"
            )
        
        def on_complete(file_path):
            self.is_downloading = False
            self.progress_var.set("✅ 下载完成!")
            self.cancel_btn.pack_forget()
            
            if messagebox.askyesno(
                "下载完成",
                f"更新包已下载到:\n{file_path}\n\n是否立即安装?"
            ):
                # 启动安装程序
                os.startfile(file_path)
                self.destroy()
            else:
                self.download_btn.pack(side=tk.LEFT, padx=5)
        
        def on_error(error_msg):
            self.is_downloading = False
            self.progress_var.set(f"❌ {error_msg}")
            self.cancel_btn.pack_forget()
            self.download_btn.pack(side=tk.LEFT, padx=5)
            self.check_btn.config(state=tk.NORMAL)
            messagebox.showerror("下载失败", error_msg)
        
        self.update_manager.download_update(
            self.version_info['download_url'],
            save_path,
            progress_callback=on_progress,
            complete_callback=on_complete,
            error_callback=on_error
        )
    
    def cancel_download(self):
        """取消下载"""
        if self.is_downloading:
            self.is_downloading = False
            self.progress_var.set("已取消下载")
            self.cancel_btn.pack_forget()
            self.download_btn.pack(side=tk.LEFT, padx=5)
            self.check_btn.config(state=tk.NORMAL)


def check_and_notify_update(parent_window, auto_check=False, silent=False):
    """检查并通知更新
    
    Args:
        parent_window: 父窗口
        auto_check: 是否自动检查(只在有新版本时显示)
        silent: 是否静默检查(仅日志提示,不弹窗)
    """
    if silent:
        # 静默模式 - 只检查,不显示对话框
        from video_generator.auto_updater import UpdateManager
        update_mgr = UpdateManager()
        
        def on_check_complete(has_update, result):
            if has_update is True:
                # 通过parent_window的log方法输出(如果可用)
                if hasattr(parent_window, 'log'):
                    version = result.get('version', '未知')
                    parent_window.log(f"🔔 发现新版本 v{version}(后台检查)")
        
        update_mgr.check_for_updates(on_check_complete)
    else:
        # 正常模式 - 显示对话框
        dialog = UpdateDialog(parent_window, auto_check=auto_check)
        
        if not auto_check:
            # 手动检查,等待用户操作
            dialog.wait_window()
