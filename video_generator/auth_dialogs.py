# -*- coding: utf-8 -*-
"""授权UI对话框模块

从 license_manager.py 拆分出的纯UI层：
- LoginDialog: 登录/注册对话框
- PasswordResetDialog: 密码找回对话框
- PurchaseDialog: 购买会员对话框
- check_and_show_login: 登录流程入口

UI层只负责显示和用户交互，业务逻辑通过 auth_core.LicenseManager 处理。
"""

import re
import threading

from .auth_core import LicenseManager, _get_verify_secret

# tkinter 延迟导入：无GUI环境（如Docker容器）中tkinter不可用
# 仅在实际需要创建对话框时才导入
tk = None
ttk = None
messagebox = None

def _ensure_tkinter():
    """确保tkinter可用，不可用时抛出ImportError"""
    global tk, ttk, messagebox
    if tk is None:
        try:
            import tkinter as _tk
            from tkinter import ttk as _ttk, messagebox as _mb
            tk = _tk
            ttk = _ttk
            messagebox = _mb
        except ImportError:
            raise ImportError("tkinter不可用，当前环境不支持GUI操作。请在有图形界面的环境中运行。")
    return tk, ttk, messagebox

def _bind_entry_context_menu(entry):
    _ensure_tkinter()
    menu = tk.Menu(entry, tearoff=0)
    def _paste():
        try:
            entry.delete("sel.first", "sel.last")
        except Exception:
            pass
        try:
            entry.insert("insert", entry.clipboard_get())
        except Exception:
            pass
    def _copy():
        try:
            entry.clipboard_clear()
            entry.clipboard_append(entry.get("sel.first", "sel.last"))
        except Exception:
            pass
    def _cut():
        try:
            entry.clipboard_clear()
            entry.clipboard_append(entry.get("sel.first", "sel.last"))
            entry.delete("sel.first", "sel.last")
        except Exception:
            pass
    def _select_all():
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
    menu.add_command(label="粘贴 Ctrl+V", command=_paste)
    menu.add_command(label="复制 Ctrl+C", command=_copy)
    menu.add_command(label="剪切 Ctrl+X", command=_cut)
    menu.add_separator()
    menu.add_command(label="全选 Ctrl+A", command=_select_all)
    menu.add_command(label="清空", command=lambda: entry.delete(0, tk.END))
    def _show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    entry.bind("<Button-3>", _show_menu)
    def _ctrl_a(event):
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        return "break"
    entry.bind("<Control-a>", _ctrl_a)
    return entry

# 延迟基类：tkinter不可用时使用占位基类，实际使用时通过_ensure_tkinter()确保可用
# 占位基类的__init__接受任意参数，避免object.__init__()参数错误
class _PlaceholderBase:
    """tkinter不可用时的占位基类，确保super().__init__()不会因参数报错"""
    def __init__(self, *args, **kwargs):
        pass

_ToplevelBase = None

def _get_toplevel_base():
    global _ToplevelBase
    if _ToplevelBase is None:
        try:
            import tkinter as _tk
            _ToplevelBase = _tk.Toplevel
        except ImportError:
            _ToplevelBase = _PlaceholderBase
    return _ToplevelBase

class LoginDialog(_get_toplevel_base()):
    _BG = "#0f1923"
    _PANEL_BG = "#162231"
    _CARD_BG = "#1b2d3e"
    _TEXT_FG = "#e8edf2"
    _TEXT_SECONDARY = "#8fa3b8"
    _ACCENT = "#3b82f6"
    _ACCENT_HOVER = "#2563eb"
    _ACCENT_LIGHT = "#60a5fa"
    _INPUT_BG = "#1e3448"
    _INPUT_FG = "#f0f4f8"
    _INPUT_BORDER = "#2d4a5f"
    _INPUT_FOCUS = "#3b82f6"
    _HINT_FG = "#6b8299"
    _WARN_FG = "#f59e0b"
    _SUCCESS_FG = "#10b981"
    _ERROR_FG = "#ef4444"
    _BTN_SECONDARY = "#253b4f"
    _BTN_PURCHASE = "#f59e0b"
    _BTN_PURCHASE_HOVER = "#d97706"
    _DIVIDER = "#2d4a5f"
    _TAB_ACTIVE_BG = "#1b2d3e"
    _TAB_INACTIVE_BG = "#0f1923"
    _SHADOW = "#0a1018"

    def __init__(self, parent=None):
        _ensure_tkinter()
        super().__init__(parent)
        self.result = None
        self.title("用户登录")
        self.geometry("460x660")
        self.minsize(440, 620)
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._setup_styles()
        self._build_ui()
        self._load_saved_credentials()

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.bind("<Destroy>", self._on_destroy)
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("Login.TFrame", background=self._BG)
        style.configure("Login.Card.TFrame", background=self._CARD_BG)
        style.configure(
            "Login.TLabel",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 11),
        )
        style.configure(
            "Login.Title.TLabel",
            background=self._BG,
            foreground=self._ACCENT_LIGHT,
            font=("Microsoft YaHei", 22, "bold"),
        )
        style.configure(
            "Login.Sub.TLabel",
            background=self._BG,
            foreground=self._TEXT_SECONDARY,
            font=("Microsoft YaHei", 10),
        )
        style.configure(
            "Login.Hint.TLabel",
            background=self._BG,
            foreground=self._WARN_FG,
            font=("Microsoft YaHei", 10),
        )
        style.configure(
            "Login.Trial.TLabel",
            background=self._BG,
            foreground=self._WARN_FG,
            font=("Microsoft YaHei", 11, "bold"),
        )
        style.configure(
            "Login.Error.TLabel",
            background=self._BG,
            foreground=self._ERROR_FG,
            font=("Microsoft YaHei", 9),
        )
        style.configure(
            "Login.TCheckbutton",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 10),
        )
        style.configure(
            "Login.Card.TCheckbutton",
            background=self._CARD_BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 10),
        )
        style.configure(
            "Login.TButton", font=("Microsoft YaHei", 11), padding=(8, 6)
        )
        style.configure(
            "Login.Primary.TButton",
            background=self._ACCENT,
            foreground="#ffffff",
            font=("Microsoft YaHei", 12, "bold"),
            padding=(12, 10),
        )
        style.map(
            "Login.Primary.TButton",
            background=[("active", self._ACCENT_HOVER), ("pressed", "#1d4ed8")],
        )
        style.configure(
            "Login.Link.TButton",
            background=self._BG,
            foreground=self._ACCENT_LIGHT,
            font=("Microsoft YaHei", 10),
            padding=(4, 3),
        )
        style.map(
            "Login.Link.TButton", foreground=[("active", "#93c5fd")]
        )
        style.configure(
            "Login.Purchase.TButton",
            background=self._BTN_PURCHASE,
            foreground="#ffffff",
            font=("Microsoft YaHei", 11, "bold"),
            padding=(10, 7),
        )
        style.map(
            "Login.Purchase.TButton", background=[("active", self._BTN_PURCHASE_HOVER)]
        )
        style.configure(
            "Login.Secondary.TButton",
            background=self._BTN_SECONDARY,
            foreground="#ffffff",
            font=("Microsoft YaHei", 10),
            padding=(6, 5),
        )
        style.map(
            "Login.Secondary.TButton", background=[("active", "#354f66")]
        )

        style.configure(
            "Login.TNotebook",
            background=self._BG,
            borderwidth=0,
            relief=tk.FLAT,
        )
        style.configure(
            "Login.TNotebook.Tab",
            background=self._TAB_INACTIVE_BG,
            foreground=self._TEXT_SECONDARY,
            font=("Microsoft YaHei", 11, "bold"),
            padding=(18, 10),
        )
        style.map(
            "Login.TNotebook.Tab",
            background=[("selected", self._TAB_ACTIVE_BG)],
            foreground=[("selected", self._ACCENT_LIGHT)],
            expand=[("selected", [0, 0, 0, 2])],
        )
        style.configure(
            "Login.TNotebook.Panel",
            background=self._CARD_BG,
            borderwidth=0,
        )

    def _safe_call(self, func):
        """安全调用UI函数，窗口已销毁时忽略"""
        try:
            if self.winfo_exists():
                func()
        except Exception:
            pass

    def _make_entry(self, parent, variable, show=None, placeholder=""):
        if show:
            frame = tk.Frame(parent, bg=self._INPUT_BORDER, bd=0,
                             highlightthickness=2,
                             highlightcolor=self._INPUT_FOCUS,
                             highlightbackground=self._INPUT_BORDER)
            frame.pack_configure = None
            entry = tk.Entry(
                frame,
                textvariable=variable,
                font=("Microsoft YaHei", 13),
                bg=self._INPUT_BG,
                fg=self._INPUT_FG,
                insertbackground=self._INPUT_FG,
                insertwidth=2,
                relief=tk.FLAT,
                bd=0,
                show=show,
                highlightthickness=0,
            )
            entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=6, padx=(2, 0))

            eye_btn = tk.Label(
                frame,
                text="\u25d0",
                font=("Segoe UI", 14),
                bg=self._INPUT_BG,
                fg=self._HINT_FG,
                cursor="hand2",
                bd=0,
                padx=8,
            )
            eye_btn.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=2)

            _show_char = show
            _visible = [False]

            def _toggle_visibility(event=None):
                if _visible[0]:
                    entry.configure(show=_show_char)
                    eye_btn.configure(text="\u25d0", fg=self._HINT_FG)
                    _visible[0] = False
                else:
                    entry.configure(show="")
                    eye_btn.configure(text="\u25c9", fg=self._ACCENT_LIGHT)
                    _visible[0] = True

            eye_btn.bind("<Button-1>", _toggle_visibility)
            _bind_entry_context_menu(entry)

            frame._inner_entry = entry
            frame._is_password_frame = True
            return frame
        else:
            entry = tk.Entry(
                parent,
                textvariable=variable,
                font=("Microsoft YaHei", 13),
                bg=self._INPUT_BG,
                fg=self._INPUT_FG,
                insertbackground=self._INPUT_FG,
                insertwidth=2,
                relief=tk.FLAT,
                bd=0,
                show="",
                highlightthickness=2,
                highlightcolor=self._INPUT_FOCUS,
                highlightbackground=self._INPUT_BORDER,
            )
            _bind_entry_context_menu(entry)
            if placeholder:
                entry.insert(0, placeholder)
                entry.configure(fg=self._HINT_FG)
                entry.bind("<FocusIn>", self._clear_placeholder(entry, placeholder))
                entry.bind("<FocusOut>", self._restore_placeholder(entry, placeholder))
            return entry

    def _clear_placeholder(self, entry, placeholder):
        def handler(event):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.configure(fg=self._INPUT_FG)

        return handler

    def _restore_placeholder(self, entry, placeholder):
        def handler(event):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.configure(fg=self._HINT_FG)

        return handler

    def _make_label(self, parent, text, **kw):
        return tk.Label(
            parent,
            text=text,
            font=("Microsoft YaHei", 11, "bold"),
            bg=self._CARD_BG,
            fg=self._TEXT_SECONDARY,
            anchor=tk.W,
            **kw,
        )

    def _build_ui(self):
        main = ttk.Frame(self, style="Login.TFrame", padding=(28, 16, 28, 12))
        main.pack(fill=tk.BOTH, expand=True)

        title_frame = tk.Frame(main, bg=self._BG)
        title_frame.pack(fill=tk.X, pady=(0, 2))

        title_lbl = tk.Label(
            title_frame,
            text="\u25c6 短视频生成器",
            font=("Microsoft YaHei", 22, "bold"),
            bg=self._BG,
            fg=self._ACCENT_LIGHT,
        )
        title_lbl.pack()

        sub_lbl = tk.Label(
            title_frame,
            text="AI驱动的音频转视频工具",
            font=("Microsoft YaHei", 10),
            bg=self._BG,
            fg=self._TEXT_SECONDARY,
        )
        sub_lbl.pack(pady=(2, 0))

        sep = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep.pack(fill=tk.X, pady=(10, 6))

        self._tab_control = ttk.Notebook(main, style="Login.TNotebook")
        self._tab_control.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        login_tab = ttk.Frame(self._tab_control, style="Login.Card.TFrame", padding=16)
        self._tab_control.add(login_tab, text="  登录  ")

        register_tab = ttk.Frame(self._tab_control, style="Login.Card.TFrame", padding=16)
        self._tab_control.add(register_tab, text="  注册  ")

        activate_tab = ttk.Frame(self._tab_control, style="Login.Card.TFrame", padding=16)
        self._tab_control.add(activate_tab, text="  激活码  ")

        self._build_login_tab(login_tab)
        self._build_register_tab(register_tab)
        self._build_activate_tab(activate_tab)

        sep2 = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep2.pack(fill=tk.X, pady=(4, 8))

        bottom_frame = ttk.Frame(main, style="Login.TFrame")
        bottom_frame.pack(fill=tk.X, pady=(0, 0))

        trial_lbl = tk.Label(
            bottom_frame,
            text="\u2728 注册登录7天免费试用!",
            font=("Microsoft YaHei", 11, "bold"),
            bg=self._BG,
            fg=self._WARN_FG,
        )
        trial_lbl.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            bottom_frame,
            text="\u2726 购买会员",
            command=self._show_purchase_dialog,
            style="Login.Purchase.TButton",
        ).pack(side=tk.RIGHT)

    def _build_login_tab(self, card):
        self._login_username_var = tk.StringVar()
        self._make_label(card, "用户名").pack(anchor=tk.W, pady=(0, 4))
        self._login_username_entry = self._make_entry(card, self._login_username_var)
        self._login_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._login_password_var = tk.StringVar()
        self._make_label(card, "密码").pack(anchor=tk.W, pady=(0, 4))
        self._login_password_entry = self._make_entry(
            card, self._login_password_var, show="\u25cf"
        )
        self._login_password_entry.pack(fill=tk.X, pady=(0, 10))

        self._save_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            card,
            text="保存密码",
            variable=self._save_pass_var,
            style="Login.Card.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(
            card,
            text="登  录",
            command=self._handle_login,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X, pady=(0, 8))

        ttk.Button(
            card,
            text="忘记密码?",
            command=self._show_reset_dialog,
            style="Login.Link.TButton",
        ).pack(anchor=tk.E)

    def _build_register_tab(self, card):
        self._reg_username_var = tk.StringVar()
        self._make_label(card, "用户名").pack(anchor=tk.W, pady=(0, 4))
        self._reg_username_entry = self._make_entry(card, self._reg_username_var)
        self._reg_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._reg_email_var = tk.StringVar()
        self._make_label(card, "邮箱地址").pack(anchor=tk.W, pady=(0, 4))
        self._reg_email_entry = self._make_entry(card, self._reg_email_var)
        self._reg_email_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._reg_password_var = tk.StringVar()
        self._make_label(card, "密码").pack(anchor=tk.W, pady=(0, 4))
        self._reg_password_entry = self._make_entry(
            card, self._reg_password_var, show="\u25cf"
        )
        self._reg_password_entry.pack(fill=tk.X, pady=(0, 10))

        self._reg_confirm_var = tk.StringVar()
        self._make_label(card, "确认密码").pack(anchor=tk.W, pady=(0, 4))
        self._reg_confirm_entry = self._make_entry(
            card, self._reg_confirm_var, show="\u25cf"
        )
        self._reg_confirm_entry.pack(fill=tk.X, pady=(0, 10))

        self._agree_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            card,
            text="我同意《隐私政策》和《服务条款》",
            variable=self._agree_var,
            style="Login.Card.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(
            card,
            text="注  册",
            command=self._handle_register,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X)

    def _build_activate_tab(self, card):
        # 检查是否已登录，如果已登录则自动填充用户名
        mgr = LicenseManager()
        existing_username = mgr.license_data.get("username", "") if mgr.license_data else ""

        self._activate_username_var = tk.StringVar(value=existing_username)
        self._make_label(card, "用户名").pack(anchor=tk.W, pady=(0, 4))
        self._activate_username_entry = self._make_entry(card, self._activate_username_var)
        self._activate_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))
        if existing_username:
            self._activate_username_entry.configure(state=tk.DISABLED)

        self._activate_password_var = tk.StringVar()
        self._make_label(card, "密码").pack(anchor=tk.W, pady=(0, 4))
        self._activate_password_entry = self._make_entry(
            card, self._activate_password_var, show="\u25cf"
        )
        self._activate_password_entry.pack(fill=tk.X, pady=(0, 10))
        if existing_username:
            self._activate_password_entry.configure(state=tk.DISABLED)
            hint = tk.Label(
                card,
                text="已登录，直接输入激活码即可",
                font=("Microsoft YaHei", 8),
                bg=self._BG,
                fg=self._TEXT_SECONDARY,
            )
            hint.pack(anchor=tk.W, pady=(0, 4))

        self._activate_code_var = tk.StringVar()
        self._make_label(card, "激活码").pack(anchor=tk.W, pady=(0, 4))
        self._activate_code_entry = self._make_entry(card, self._activate_code_var)
        self._activate_code_entry.pack(fill=tk.X, ipady=6, pady=(0, 14))

        btn_text = "激  活" if existing_username else "登录并激活"
        ttk.Button(
            card,
            text=btn_text,
            command=self._handle_activate,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X)

    def _handle_login(self):
        username = self._login_username_var.get().strip()
        password = self._login_password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请填写用户名和密码", parent=self)
            return

        login_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[0]).winfo_children():
            if isinstance(child, ttk.Button) and child.cget("text") == "登  录":
                login_btn = child
                break
        if login_btn:
            login_btn.configure(state=tk.DISABLED, text="登录中...")

        def do_login():
            mgr = LicenseManager()
            success, message = mgr.login_user(username, password)
            if success:
                mgr.save_login_credentials(username, password, True, self._save_pass_var.get())
                self.after(0, lambda: self._safe_call(lambda: self._on_login_success(message)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_login_failure(message, login_btn)))

        threading.Thread(target=do_login, daemon=True).start()

    def _on_login_success(self, message):
        messagebox.showinfo("成功", message, parent=self)
        self.result = True
        self.destroy()

    def _on_login_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="登  录")
        messagebox.showerror("错误", message, parent=self)

    def _handle_register(self):
        username = self._reg_username_var.get().strip()
        if not username:
            messagebox.showwarning("提示", "请填写用户名", parent=self)
            return
        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]{3,50}$", username):
            messagebox.showwarning(
                "提示",
                "用户名需3-50位，支持字母数字下划线和中文",
                parent=self,
            )
            return
        email = self._reg_email_var.get().strip()
        if not email:
            messagebox.showwarning("提示", "请填写邮箱", parent=self)
            return
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            messagebox.showwarning(
                "提示", "请输入有效的邮箱地址", parent=self
            )
            return
        password = self._reg_password_var.get().strip()
        if not password:
            messagebox.showwarning("提示", "请填写密码", parent=self)
            return
        if len(password) < 8:
            messagebox.showwarning("提示", "密码至少8位", parent=self)
            return
        if len(password) > 72:
            messagebox.showwarning("提示", "密码不能超过72位", parent=self)
            return
        if not re.search(r"[A-Z]", password):
            messagebox.showwarning(
                "提示", "密码必须包含至少一个大写字母", parent=self
            )
            return
        if not re.search(r"[a-z]", password):
            messagebox.showwarning(
                "提示", "密码必须包含至少一个小写字母", parent=self
            )
            return
        if not re.search(r"\d", password):
            messagebox.showwarning(
                "提示", "密码必须包含至少一个数字", parent=self
            )
            return
        confirm = self._reg_confirm_var.get().strip()
        if password != confirm:
            messagebox.showwarning(
                "提示", "两次密码不一致", parent=self
            )
            return
        if not self._agree_var.get():
            messagebox.showwarning(
                "提示", "请先同意隐私政策和服务条款", parent=self
            )
            return

        reg_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[1]).winfo_children():
            if isinstance(child, ttk.Button):
                reg_btn = child
                break
        if reg_btn:
            reg_btn.configure(state=tk.DISABLED, text="注册中...")

        def do_register():
            success, message = LicenseManager().register_user(username, email, password)
            if success:
                self.after(0, lambda: self._safe_call(lambda: self._on_register_success(message)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_register_failure(message, reg_btn)))

        threading.Thread(target=do_register, daemon=True).start()

    def _on_register_success(self, message):
        messagebox.showinfo("成功", message, parent=self)
        self.result = True
        self.destroy()

    def _on_register_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="注  册")
        messagebox.showerror("错误", message, parent=self)

    def _handle_activate(self):
        username = self._activate_username_var.get().strip()
        password = self._activate_password_var.get().strip()
        code = self._activate_code_var.get().strip()

        mgr = LicenseManager()
        already_logged_in = bool(mgr.license_data and mgr.license_data.get("username"))

        if not already_logged_in:
            if not username or not password:
                messagebox.showwarning("提示", "请填写用户名和密码", parent=self)
                return
        if not code:
            messagebox.showwarning("提示", "请输入激活码", parent=self)
            return

        activate_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[2]).winfo_children():
            if isinstance(child, ttk.Button):
                activate_btn = child
                break
        if activate_btn:
            activate_btn.configure(state=tk.DISABLED, text="激活中...")

        def do_activate():
            if not already_logged_in:
                success, message = mgr.login_user(username, password)
                if not success:
                    self.after(0, lambda: self._safe_call(lambda: self._on_activate_failure(f"登录失败: {message}", activate_btn)))
                    return
            success2, message2 = mgr.activate_pro_license(code)
            if success2:
                mgr.save_login_credentials(username or mgr.license_data.get("username", ""), password, True, False)
                self.after(0, lambda: self._safe_call(lambda: self._on_activate_success()))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_activate_partial(message2, activate_btn)))

        threading.Thread(target=do_activate, daemon=True).start()

    def _on_activate_success(self):
        messagebox.showinfo("成功", "激活成功！专业版已开通", parent=self)
        self.result = True
        self.destroy()

    def _on_activate_partial(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="登录并激活")
        # 登录已成功但激活失败，用户已处于登录状态，关闭对话框让用户重试
        messagebox.showerror("错误", f"激活失败: {message}\n您已登录成功，可稍后点击「购买会员」→「激活码」重新激活。", parent=self)
        self.result = True
        self.destroy()

    def _on_activate_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="登录并激活")
        messagebox.showerror("错误", message, parent=self)

    def _load_saved_credentials(self):
        try:
            mgr = LicenseManager()
            username, password, save_user, save_pass = (
                mgr.load_login_credentials()
            )
            if username:
                self._login_username_var.set(username)
            if save_pass and password:
                self._save_pass_var.set(True)
                self._login_password_var.set(password)
        except Exception:
            pass

    def _show_reset_dialog(self):
        dialog = PasswordResetDialog(self)
        self.wait_window(dialog)

    def _show_purchase_dialog(self):
        dialog = PurchaseDialog(self)
        self.wait_window(dialog)

    def _on_cancel(self):
        self.result = False
        self.destroy()

    def _on_destroy(self, event):
        if event.widget is self and self.result is None:
            self.result = False

class PasswordResetDialog(_get_toplevel_base()):
    _BG = "#0f1923"
    _CARD_BG = "#1b2d3e"
    _TEXT_FG = "#e8edf2"
    _TEXT_SECONDARY = "#8fa3b8"
    _ACCENT = "#3b82f6"
    _ACCENT_LIGHT = "#60a5fa"
    _INPUT_BG = "#1e3448"
    _INPUT_FG = "#f0f4f8"
    _INPUT_BORDER = "#2d4a5f"
    _HINT_FG = "#6b8299"
    _DIVIDER = "#2d4a5f"

    def __init__(self, parent):
        _ensure_tkinter()
        super().__init__(parent)
        self.title("密码找回")
        self.geometry("480x540")
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._setup_styles()
        self._build_ui()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Reset.TFrame", background=self._BG)
        style.configure(
            "Reset.TLabel",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 12),
        )
        style.configure(
            "Reset.Title.TLabel",
            background=self._BG,
            foreground=self._ACCENT_LIGHT,
            font=("Microsoft YaHei", 18, "bold"),
        )
        style.configure(
            "Reset.Hint.TLabel",
            background=self._BG,
            foreground=self._HINT_FG,
            font=("Microsoft YaHei", 10),
        )
        style.configure(
            "Reset.TButton",
            font=("Microsoft YaHei", 11),
            padding=(8, 6),
        )
        style.configure(
            "Reset.Primary.TButton",
            background=self._ACCENT,
            foreground="#ffffff",
            font=("Microsoft YaHei", 12, "bold"),
            padding=(12, 8),
        )
        style.configure(
            "Reset.TCheckbutton",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 11),
        )

    def _safe_call(self, func):
        """安全调用UI函数，窗口已销毁时忽略"""
        try:
            if self.winfo_exists():
                func()
        except Exception:
            pass

    def _make_entry(self, parent, variable, show=None):
        if show:
            frame = tk.Frame(parent, bg=self._INPUT_BORDER, bd=0,
                             highlightthickness=2,
                             highlightcolor=self._ACCENT,
                             highlightbackground=self._INPUT_BORDER)
            entry = tk.Entry(
                frame,
                textvariable=variable,
                font=("Microsoft YaHei", 13),
                bg=self._INPUT_BG,
                fg=self._INPUT_FG,
                insertbackground=self._INPUT_FG,
                insertwidth=2,
                relief=tk.FLAT,
                bd=0,
                show=show,
                highlightthickness=0,
            )
            entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, ipady=8, padx=(2, 0))

            eye_btn = tk.Label(
                frame,
                text="\u25d0",
                font=("Segoe UI", 14),
                bg=self._INPUT_BG,
                fg=self._HINT_FG,
                cursor="hand2",
                bd=0,
                padx=8,
            )
            eye_btn.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=2)

            _show_char = show
            _visible = [False]

            def _toggle_visibility(event=None):
                if _visible[0]:
                    entry.configure(show=_show_char)
                    eye_btn.configure(text="\u25d0", fg=self._HINT_FG)
                    _visible[0] = False
                else:
                    entry.configure(show="")
                    eye_btn.configure(text="\u25c9", fg=self._ACCENT_LIGHT)
                    _visible[0] = True

            eye_btn.bind("<Button-1>", _toggle_visibility)
            _bind_entry_context_menu(entry)

            frame._inner_entry = entry
            frame._is_password_frame = True
            return frame
        else:
            entry = tk.Entry(
                parent,
                textvariable=variable,
                font=("Microsoft YaHei", 13),
                bg=self._INPUT_BG,
                fg=self._INPUT_FG,
                insertbackground=self._INPUT_FG,
                insertwidth=2,
                relief=tk.FLAT,
                bd=0,
                show="",
                highlightthickness=2,
                highlightcolor=self._ACCENT,
                highlightbackground=self._INPUT_BORDER,
            )
            _bind_entry_context_menu(entry)
            return entry

    def _make_label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            font=("Microsoft YaHei", 11, "bold"),
            bg=self._BG,
            fg=self._TEXT_SECONDARY,
            anchor=tk.W,
        )

    def _build_ui(self):
        main = ttk.Frame(self, style="Reset.TFrame", padding=(30, 20, 30, 15))
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="\u25c6 密码找回", font=("Microsoft YaHei", 18, "bold"),
            bg=self._BG, fg=self._ACCENT_LIGHT,
        ).pack(pady=(0, 4))
        tk.Label(
            main,
            text="通过注册邮箱验证身份后重置密码",
            font=("Microsoft YaHei", 10),
            bg=self._BG, fg=self._HINT_FG,
        ).pack(pady=(0, 14))

        self._make_label(main, "注册邮箱").pack(anchor=tk.W, pady=(0, 4))
        self.email_var = tk.StringVar()
        self.email_entry = self._make_entry(main, self.email_var)
        self.email_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self._make_label(main, "验证码").pack(anchor=tk.W, pady=(0, 4))
        btn_row = ttk.Frame(main, style="Reset.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 14))
        self.code_var = tk.StringVar()
        self.code_entry = self._make_entry(btn_row, self.code_var)
        self.code_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=8
        )
        self.send_btn = ttk.Button(
            btn_row,
            text="发送验证码",
            command=self._send_code,
            style="Reset.TButton",
        )
        self.send_btn.pack(side=tk.RIGHT)

        self._make_label(main, "新密码").pack(anchor=tk.W, pady=(0, 4))
        self.new_pass_var = tk.StringVar()
        self.new_pass_entry = self._make_entry(
            main, self.new_pass_var, show="\u25cf"
        )
        self.new_pass_entry.pack(fill=tk.X, pady=(0, 14))

        self._make_label(main, "确认新密码").pack(anchor=tk.W, pady=(0, 4))
        self.confirm_pass_var = tk.StringVar()
        self.confirm_pass_entry = self._make_entry(
            main, self.confirm_pass_var, show="\u25cf"
        )
        self.confirm_pass_entry.pack(fill=tk.X, pady=(0, 14))

        self._reset_btn = ttk.Button(
            main,
            text="重置密码",
            command=self._do_reset,
            style="Reset.Primary.TButton",
        )
        self._reset_btn.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            main, text="取消", command=self.destroy, style="Reset.TButton"
        ).pack(fill=tk.X)

        self._code_sent = False
        self._countdown_id = None

    def _send_code(self):
        email = self.email_var.get().strip()
        if not email:
            messagebox.showwarning("提示", "请输入注册邮箱", parent=self)
            return
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            messagebox.showwarning(
                "提示", "请输入有效的邮箱地址", parent=self
            )
            return
        self.send_btn.configure(state=tk.DISABLED, text="发送中...")

        def do_send():
            success, message = LicenseManager().request_password_reset(email)
            if success:
                self._code_sent = True
                self.after(0, lambda: self._safe_call(lambda: self._on_send_code_success(message)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_send_code_failure(message)))

        threading.Thread(target=do_send, daemon=True).start()

    def _on_send_code_success(self, message):
        messagebox.showinfo("成功", message, parent=self)
        self._start_countdown(60)

    def _on_send_code_failure(self, message):
        self.send_btn.configure(state=tk.NORMAL, text="发送验证码")
        messagebox.showerror("错误", message, parent=self)

    def _start_countdown(self, seconds):
        if seconds <= 0:
            self.send_btn.config(text="发送验证码", state=tk.NORMAL)
            return
        self.send_btn.config(text=f"{seconds}s", state=tk.DISABLED)
        self._countdown_id = self.after(
            1000, lambda: self._start_countdown(seconds - 1)
        )

    def _do_reset(self):
        email = self.email_var.get().strip()
        code = self.code_var.get().strip()
        new_pass = self.new_pass_var.get().strip()
        confirm_pass = self.confirm_pass_var.get().strip()

        if not email:
            messagebox.showwarning("提示", "请输入注册邮箱", parent=self)
            return
        if not self._code_sent:
            messagebox.showwarning("提示", "请先发送验证码", parent=self)
            return
        if not code:
            messagebox.showwarning("提示", "请输入验证码", parent=self)
            return
        if len(new_pass) < 8:
            messagebox.showwarning("提示", "新密码至少8位", parent=self)
            return
        if len(new_pass) > 72:
            messagebox.showwarning("提示", "新密码不能超过72位", parent=self)
            return
        if not re.search(r"[A-Z]", new_pass):
            messagebox.showwarning(
                "提示", "新密码必须包含至少一个大写字母", parent=self
            )
            return
        if not re.search(r"[a-z]", new_pass):
            messagebox.showwarning(
                "提示", "新密码必须包含至少一个小写字母", parent=self
            )
            return
        if not re.search(r"\d", new_pass):
            messagebox.showwarning(
                "提示", "新密码必须包含至少一个数字", parent=self
            )
            return
        if new_pass != confirm_pass:
            messagebox.showwarning(
                "提示", "两次密码不一致", parent=self
            )
            return

        self._reset_btn.configure(state=tk.DISABLED, text="重置中...")

        def do_reset():
            success, message = LicenseManager().confirm_password_reset(
                email, code, new_pass
            )
            if success:
                self.after(0, lambda: self._safe_call(lambda: self._on_reset_success(message)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_reset_failure(message)))

        threading.Thread(target=do_reset, daemon=True).start()

    def _on_reset_success(self, message):
        LicenseManager().clear_login_credentials()
        messagebox.showinfo("成功", message, parent=self)
        self.destroy()

    def _on_reset_failure(self, message):
        if hasattr(self, '_reset_btn') and self._reset_btn.winfo_exists():
            self._reset_btn.configure(state=tk.NORMAL, text="重置密码")
        messagebox.showerror("错误", message, parent=self)

    def destroy(self):
        if self._countdown_id:
            self.after_cancel(self._countdown_id)
        super().destroy()

class PurchaseDialog(_get_toplevel_base()):
    _BG = "#0f1923"
    _CARD_BG = "#1b2d3e"
    _TEXT_FG = "#e8edf2"
    _TEXT_SECONDARY = "#8fa3b8"
    _ACCENT = "#3b82f6"
    _ACCENT_LIGHT = "#60a5fa"
    _INPUT_BG = "#1e3448"
    _INPUT_FG = "#f0f4f8"
    _INPUT_BORDER = "#2d4a5f"
    _HINT_FG = "#6b8299"
    _GOLD = "#f59e0b"
    _GOLD_HOVER = "#d97706"
    _SELECTED_BG = "#1a3a5c"
    _DIVIDER = "#2d4a5f"
    _WARN_FG = "#f59e0b"

    PLANS = [
        {
            "key": "monthly",
            "name": "月卡",
            "price": "\u00a514.9/月",
            "desc": "30天专业版",
        },
        {
            "key": "quarterly",
            "name": "季卡",
            "price": "\u00a539.9/季",
            "desc": "90天专业版",
        },
        {
            "key": "yearly",
            "name": "年卡",
            "price": "\u00a5129.9/年",
            "desc": "365天专业版",
        },
        {
            "key": "lifetime",
            "name": "终身会员",
            "price": "\u00a5219.9",
            "desc": "永久专业版",
        },
    ]

    def __init__(self, parent):
        _ensure_tkinter()
        super().__init__(parent)
        self.title("购买会员")
        self.geometry("560x640")
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)
        self.grab_set()

        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self._selected_plan = None
        self._plan_cards = {}
        self._online_available = True
        self._payment_methods_info = {}

        self._setup_styles()
        self._build_ui()
        self._check_payment_availability()

        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Purchase.TFrame", background=self._BG)
        style.configure(
            "Purchase.TLabel",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 12),
        )
        style.configure(
            "Purchase.Title.TLabel",
            background=self._BG,
            foreground=self._GOLD,
            font=("Microsoft YaHei", 18, "bold"),
        )
        style.configure(
            "Purchase.TButton",
            font=("Microsoft YaHei", 11),
            padding=(8, 6),
        )
        style.configure(
            "Purchase.Primary.TButton",
            background=self._GOLD,
            foreground="#0f1923",
            font=("Microsoft YaHei", 12, "bold"),
            padding=(12, 8),
        )
        style.configure(
            "Purchase.TCheckbutton",
            background=self._BG,
            foreground=self._TEXT_FG,
            font=("Microsoft YaHei", 11),
        )

    def _safe_call(self, func):
        """安全调用UI函数，窗口已销毁时忽略"""
        try:
            if self.winfo_exists():
                func()
        except Exception:
            pass

    def _make_entry(self, parent, variable, show=None):
        entry = tk.Entry(
            parent,
            textvariable=variable,
            font=("Microsoft YaHei", 13),
            bg=self._INPUT_BG,
            fg=self._INPUT_FG,
            insertbackground=self._INPUT_FG,
            insertwidth=2,
            relief=tk.FLAT,
            bd=0,
            show=show if show else "",
            highlightthickness=2,
            highlightcolor=self._ACCENT,
            highlightbackground=self._INPUT_BORDER,
        )
        _bind_entry_context_menu(entry)
        return entry

    def _build_ui(self):
        main = ttk.Frame(
            self, style="Purchase.TFrame", padding=(30, 18, 30, 15)
        )
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="\u25c6 购买会员", font=("Microsoft YaHei", 18, "bold"),
            bg=self._BG, fg=self._GOLD,
        ).pack(pady=(0, 14))

        plans_frame = ttk.Frame(main, style="Purchase.TFrame")
        plans_frame.pack(fill=tk.X, pady=(0, 10))

        for i, plan in enumerate(self.PLANS):
            card = tk.Frame(
                plans_frame,
                bg=self._CARD_BG,
                bd=1,
                relief=tk.RAISED,
                cursor="hand2",
                padx=10,
                pady=8,
            )
            card.grid(row=0, column=i, padx=4, pady=0, sticky="nsew")
            plans_frame.columnconfigure(i, weight=1)

            name_lbl = tk.Label(
                card,
                text=plan["name"],
                font=("Microsoft YaHei", 12, "bold"),
                bg=self._CARD_BG,
                fg=self._TEXT_FG,
            )
            name_lbl.pack()
            price_lbl = tk.Label(
                card,
                text=plan["price"],
                font=("Microsoft YaHei", 14, "bold"),
                bg=self._CARD_BG,
                fg=self._GOLD,
            )
            price_lbl.pack(pady=(2, 0))
            desc_lbl = tk.Label(
                card,
                text=plan["desc"],
                font=("Microsoft YaHei", 10),
                bg=self._CARD_BG,
                fg=self._HINT_FG,
            )
            desc_lbl.pack(pady=(0, 2))

            for widget in [card, name_lbl, price_lbl, desc_lbl]:
                widget.bind(
                    "<Button-1>",
                    lambda e, k=plan["key"]: self._select_plan(k),
                )

            self._plan_cards[plan["key"]] = card

        sep = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep.pack(fill=tk.X, pady=(10, 14))

        tk.Label(
            main, text="激活码激活",
            font=("Microsoft YaHei", 12, "bold"),
            bg=self._BG, fg=self._TEXT_FG,
        ).pack(anchor=tk.W, pady=(0, 6))
        activate_frame = ttk.Frame(main, style="Purchase.TFrame")
        activate_frame.pack(fill=tk.X, pady=(0, 14))

        self.activate_var = tk.StringVar()
        self.activate_entry = self._make_entry(activate_frame, self.activate_var)
        self.activate_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10)
        )
        self._activate_btn = ttk.Button(
            activate_frame,
            text="激活",
            command=self._do_activate,
            style="Purchase.TButton",
        )
        self._activate_btn.pack(side=tk.RIGHT)

        sep2 = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep2.pack(fill=tk.X, pady=(6, 14))

        pay_label_frame = ttk.Frame(main, style="Purchase.TFrame")
        pay_label_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            pay_label_frame, text="在线购买",
            font=("Microsoft YaHei", 12, "bold"),
            bg=self._BG, fg=self._TEXT_FG,
        ).pack(side=tk.LEFT)
        self._pay_hint = tk.Label(
            pay_label_frame,
            text="请先选择套餐",
            font=("Microsoft YaHei", 10),
            bg=self._BG,
            fg=self._HINT_FG,
        )
        self._pay_hint.pack(side=tk.RIGHT)

        self._online_hint_lbl = tk.Label(
            main,
            text="",
            font=("Microsoft YaHei", 10),
            bg=self._BG,
            fg=self._WARN_FG,
            wraplength=480,
            justify=tk.LEFT,
        )
        self._online_hint_lbl.pack(fill=tk.X, pady=(0, 6))

        pay_btn_frame = ttk.Frame(main, style="Purchase.TFrame")
        pay_btn_frame.pack(fill=tk.X, pady=(0, 10))
        self._alipay_btn = ttk.Button(
            pay_btn_frame,
            text="支付宝支付",
            command=lambda: self._do_purchase("alipay"),
            style="Purchase.TButton",
        )
        self._alipay_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._wechat_btn = ttk.Button(
            pay_btn_frame,
            text="微信支付",
            command=lambda: self._do_purchase("wechat"),
            style="Purchase.TButton",
        )
        self._wechat_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        ttk.Button(
            main,
            text="关闭",
            command=self.destroy,
            style="Purchase.TButton",
        ).pack(fill=tk.X, pady=(10, 0))

    def _check_payment_availability(self):
        def _check():
            try:
                from .config import get_api_base_url, get_http_session
                response = get_http_session().get(
                    f"{get_api_base_url()}/api/payment/methods",
                    timeout=5,
                )
                if response.status_code == 200:
                    data = response.json()
                    self._online_available = data.get("any_online_available", True)
                    self._payment_methods_info = {
                        m["id"]: m for m in data.get("methods", [])
                    }
            except Exception:
                self._online_available = False

            self.after(0, self._update_payment_ui)

        threading.Thread(target=_check, daemon=True).start()

    def _update_payment_ui(self):
        if not self._online_available:
            self._alipay_btn.configure(state=tk.DISABLED)
            self._wechat_btn.configure(state=tk.DISABLED)
            self._online_hint_lbl.configure(
                text="\u26a0 在线支付暂未开通，请联系客服购买激活码\n"
                     "您可以在上方\"激活码激活\"区域输入客服提供的激活码"
            )
        else:
            alipay_info = self._payment_methods_info.get("alipay", {})
            wechat_info = self._payment_methods_info.get("wechat", {})
            if not alipay_info.get("available", True):
                self._alipay_btn.configure(state=tk.DISABLED)
            if not wechat_info.get("available", True):
                self._wechat_btn.configure(state=tk.DISABLED)
            if not alipay_info.get("available", True) or not wechat_info.get("available", True):
                self._online_hint_lbl.configure(
                    text="\u26a0 部分支付方式暂未开通，请联系客服购买激活码"
                )

    def _select_plan(self, plan_key):
        self._selected_plan = plan_key
        for key, card in self._plan_cards.items():
            if key == plan_key:
                card.configure(bg=self._SELECTED_BG)
                for w in card.winfo_children():
                    w.configure(bg=self._SELECTED_BG)
            else:
                card.configure(bg=self._CARD_BG)
                for w in card.winfo_children():
                    w.configure(bg=self._CARD_BG)
        plan_name = next(
            (p["name"] for p in self.PLANS if p["key"] == plan_key), ""
        )
        self._pay_hint.configure(text=f"已选择: {plan_name}")

    def _do_activate(self):
        code = self.activate_var.get().strip()
        if not code:
            messagebox.showwarning(
                "提示", "请输入正确的激活码", parent=self
            )
            return
        mgr = LicenseManager()
        if not mgr._get_token():
            messagebox.showwarning(
                "提示", "请先登录后再激活", parent=self
            )
            return
        self._activate_btn.configure(state=tk.DISABLED, text="激活中...")

        def do_activate():
            mgr = LicenseManager()
            success, message = mgr.activate_pro_license(code)
            if success:
                self.after(0, lambda: self._safe_call(lambda: self._on_purchase_activate_success(message)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_purchase_activate_failure(message)))

        threading.Thread(target=do_activate, daemon=True).start()

    def _on_purchase_activate_success(self, message):
        messagebox.showinfo("提示", "程序已激活", parent=self)
        self.destroy()

    def _on_purchase_activate_failure(self, message):
        if hasattr(self, '_activate_btn') and self._activate_btn.winfo_exists():
            self._activate_btn.configure(state=tk.NORMAL, text="激活")
        messagebox.showerror(
            "提示", f"激活失败: {message}", parent=self
        )

    def _do_purchase(self, payment_method):
        if not self._selected_plan:
            messagebox.showwarning("提示", "请先选择套餐", parent=self)
            return
        mgr = LicenseManager()
        if not mgr._get_token():
            messagebox.showwarning("提示", "请先登录后再购买", parent=self)
            return
        pay_btn = self._alipay_btn if payment_method == "alipay" else self._wechat_btn
        pay_btn.configure(state=tk.DISABLED, text="请求中...")

        def do_purchase():
            mgr = LicenseManager()
            success, result = mgr.purchase_subscription(
                self._selected_plan, payment_method
            )
            if success:
                self.after(0, lambda: self._safe_call(lambda: self._on_purchase_success(result, payment_method)))
            else:
                self.after(0, lambda: self._safe_call(lambda: self._on_purchase_failure(result, payment_method)))

        threading.Thread(target=do_purchase, daemon=True).start()

    def _on_purchase_success(self, result, payment_method):
        self._alipay_btn.configure(state=tk.NORMAL, text="支付宝支付")
        self._wechat_btn.configure(state=tk.NORMAL, text="微信支付")
        order_id = result.get("order_id", "")
        qr_code = result.get("qr_code", "")
        msg = result.get("message", "")
        info = f"订单号: {order_id}\n"
        if msg:
            info += f"提示: {msg}\n"
        if qr_code:
            pay_name = "支付宝" if payment_method == "alipay" else "微信"
            info += f"\n请使用{pay_name}扫描以下二维码支付:\n{qr_code}"
        info += "\n\n支付完成后将自动检测..."
        messagebox.showinfo("订单创建成功", info, parent=self)
        # 启动订单状态轮询
        if order_id:
            self._poll_order_status(order_id)

    def _poll_order_status(self, order_id, attempt=0, max_attempts=60):
        """轮询订单状态，支付成功后自动刷新授权"""
        if attempt >= max_attempts:
            return
        if not self.winfo_exists():
            return

        def _check():
            try:
                mgr = LicenseManager()
                token = mgr._get_token()
                if not token:
                    return
                from .config import get_api_base_url, get_http_session
                response = get_http_session().get(
                    f"{get_api_base_url()}/api/payment/order-status/{order_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "paid":
                        # 支付成功，刷新授权
                        mgr.refresh_license()
                        self.after(0, lambda: self._safe_call(lambda: self._on_payment_confirmed()))
                        return
            except Exception:
                pass
            # 继续轮询，间隔3秒
            self.after(3000, lambda: self._poll_order_status(order_id, attempt + 1, max_attempts))

        if attempt == 0:
            # 首次等待5秒再开始轮询
            self.after(5000, lambda: threading.Thread(target=_check, daemon=True).start())
        else:
            threading.Thread(target=_check, daemon=True).start()

    def _on_payment_confirmed(self):
        messagebox.showinfo("支付成功", "支付已确认，专业版已开通！", parent=self)
        self.destroy()

    def _on_purchase_failure(self, result, payment_method):
        self._alipay_btn.configure(state=tk.NORMAL, text="支付宝支付")
        self._wechat_btn.configure(state=tk.NORMAL, text="微信支付")
        messagebox.showerror(
            "错误",
            result if isinstance(result, str) else "创建订单失败",
            parent=self,
        )

def check_and_show_login(parent=None):
    _ensure_tkinter()
    license_mgr = LicenseManager()
    license_status = license_mgr.check_license()

    # 辅助函数：尝试登录对话框并返回结果
    def _try_login_dialog():
        dialog = LoginDialog(parent)
        dialog.wait_window()
        if dialog.result:
            status = license_mgr.check_license()
            if status["valid"]:
                license_mgr.start_heartbeat()
                return status
            verify_secret = _get_verify_secret()
            if not verify_secret:
                return {
                    "valid": False,
                    "message": "授权验证组件缺失(.license_verify_key)，请联系客服",
                }
            return status
        return {"valid": False, "message": "用户取消登录"}

    # 主流程
    if not license_status["valid"]:
        # 本地授权无效，尝试静默重登录
        if license_mgr._try_silent_relogin():
            license_status = license_mgr.check_license()
            if license_status["valid"]:
                # 重登录成功，验证服务器
                if not license_mgr.verify_with_server():
                    license_status = license_mgr.check_license()
                    if not license_status["valid"]:
                        return _try_login_dialog()
                license_mgr.start_heartbeat()
                return license_status
        # 静默重登录失败或授权仍无效，弹出登录框
        return _try_login_dialog()

    # 本地授权有效，验证服务器
    if not license_mgr.verify_with_server():
        license_status = license_mgr.check_license()
        if not license_status["valid"]:
            return _try_login_dialog()

    license_mgr.start_heartbeat()
    return license_status
