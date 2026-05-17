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
import tkinter as tk
from tkinter import ttk, messagebox

from .auth_core import LicenseManager, _get_verify_secret


class LoginDialog(tk.Toplevel):
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
        super().__init__(parent)
        self.result = None
        self.title("用户登录")
        self.geometry("460x660")
        self.minsize(440, 620)
        self.resizable(True, True)
        self.configure(bg=self._BG)
        self.transient(parent)

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

    def _make_entry(self, parent, variable, show=None, placeholder=""):
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
            highlightcolor=self._INPUT_FOCUS,
            highlightbackground=self._INPUT_BORDER,
        )
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
            text="\u25c6 \u77ed\u89c6\u9891\u751f\u6210\u5668",
            font=("Microsoft YaHei", 22, "bold"),
            bg=self._BG,
            fg=self._ACCENT_LIGHT,
        )
        title_lbl.pack()

        sub_lbl = tk.Label(
            title_frame,
            text="AI\u9a71\u52a8\u7684\u97f3\u9891\u8f6c\u89c6\u9891\u5de5\u5177",
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
        self._tab_control.add(login_tab, text="  \u767b\u5f55  ")

        register_tab = ttk.Frame(self._tab_control, style="Login.Card.TFrame", padding=16)
        self._tab_control.add(register_tab, text="  \u6ce8\u518c  ")

        activate_tab = ttk.Frame(self._tab_control, style="Login.Card.TFrame", padding=16)
        self._tab_control.add(activate_tab, text="  \u6fc0\u6d3b\u7801  ")

        self._build_login_tab(login_tab)
        self._build_register_tab(register_tab)
        self._build_activate_tab(activate_tab)

        sep2 = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep2.pack(fill=tk.X, pady=(4, 8))

        bottom_frame = ttk.Frame(main, style="Login.TFrame")
        bottom_frame.pack(fill=tk.X, pady=(0, 0))

        trial_lbl = tk.Label(
            bottom_frame,
            text="\u2728 \u6ce8\u518c\u767b\u5f557\u5929\u514d\u8d39\u8bd5\u7528!",
            font=("Microsoft YaHei", 11, "bold"),
            bg=self._BG,
            fg=self._WARN_FG,
        )
        trial_lbl.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(
            bottom_frame,
            text="\u2726 \u8d2d\u4e70\u4f1a\u5458",
            command=self._show_purchase_dialog,
            style="Login.Purchase.TButton",
        ).pack(side=tk.RIGHT)

    def _build_login_tab(self, card):
        self._login_username_var = tk.StringVar()
        self._make_label(card, "\u7528\u6237\u540d").pack(anchor=tk.W, pady=(0, 4))
        self._login_username_entry = self._make_entry(card, self._login_username_var)
        self._login_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._login_password_var = tk.StringVar()
        self._make_label(card, "\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self._login_password_entry = self._make_entry(
            card, self._login_password_var, show="\u25cf"
        )
        self._login_password_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._save_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            card,
            text="\u4fdd\u5b58\u5bc6\u7801",
            variable=self._save_pass_var,
            style="Login.Card.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(
            card,
            text="\u767b  \u5f55",
            command=self._handle_login,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X, pady=(0, 8))

        ttk.Button(
            card,
            text="\u5fd8\u8bb0\u5bc6\u7801?",
            command=self._show_reset_dialog,
            style="Login.Link.TButton",
        ).pack(anchor=tk.E)

    def _build_register_tab(self, card):
        self._reg_username_var = tk.StringVar()
        self._make_label(card, "\u7528\u6237\u540d").pack(anchor=tk.W, pady=(0, 4))
        self._reg_username_entry = self._make_entry(card, self._reg_username_var)
        self._reg_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._reg_email_var = tk.StringVar()
        self._make_label(card, "\u90ae\u7bb1\u5730\u5740").pack(anchor=tk.W, pady=(0, 4))
        self._reg_email_entry = self._make_entry(card, self._reg_email_var)
        self._reg_email_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._reg_password_var = tk.StringVar()
        self._make_label(card, "\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self._reg_password_entry = self._make_entry(
            card, self._reg_password_var, show="\u25cf"
        )
        self._reg_password_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._reg_confirm_var = tk.StringVar()
        self._make_label(card, "\u786e\u8ba4\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self._reg_confirm_entry = self._make_entry(
            card, self._reg_confirm_var, show="\u25cf"
        )
        self._reg_confirm_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._agree_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            card,
            text="\u6211\u540c\u610f\u300a\u9690\u79c1\u653f\u7b56\u300b\u548c\u300a\u670d\u52a1\u6761\u6b3e\u300b",
            variable=self._agree_var,
            style="Login.Card.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Button(
            card,
            text="\u6ce8  \u518c",
            command=self._handle_register,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X)

    def _build_activate_tab(self, card):
        self._activate_username_var = tk.StringVar()
        self._make_label(card, "\u7528\u6237\u540d").pack(anchor=tk.W, pady=(0, 4))
        self._activate_username_entry = self._make_entry(card, self._activate_username_var)
        self._activate_username_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._activate_password_var = tk.StringVar()
        self._make_label(card, "\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self._activate_password_entry = self._make_entry(
            card, self._activate_password_var, show="\u25cf"
        )
        self._activate_password_entry.pack(fill=tk.X, ipady=6, pady=(0, 10))

        self._activate_code_var = tk.StringVar()
        self._make_label(card, "\u6fc0\u6d3b\u7801").pack(anchor=tk.W, pady=(0, 4))
        self._activate_code_entry = self._make_entry(card, self._activate_code_var)
        self._activate_code_entry.pack(fill=tk.X, ipady=6, pady=(0, 14))

        ttk.Button(
            card,
            text="\u767b\u5f55\u5e76\u6fc0\u6d3b",
            command=self._handle_activate,
            style="Login.Primary.TButton",
        ).pack(fill=tk.X)

    def _handle_login(self):
        username = self._login_username_var.get().strip()
        password = self._login_password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u586b\u5199\u7528\u6237\u540d\u548c\u5bc6\u7801", parent=self)
            return

        login_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[0]).winfo_children():
            if isinstance(child, ttk.Button) and child.cget("text") == "\u767b  \u5f55":
                login_btn = child
                break
        if login_btn:
            login_btn.configure(state=tk.DISABLED, text="\u767b\u5f55\u4e2d...")

        def do_login():
            mgr = LicenseManager()
            success, message = mgr.login_user(username, password)
            if success:
                mgr.save_login_credentials(username, password, True, self._save_pass_var.get())
                self.after(0, lambda: self._on_login_success(message))
            else:
                self.after(0, lambda: self._on_login_failure(message, login_btn))

        threading.Thread(target=do_login, daemon=True).start()

    def _on_login_success(self, message):
        messagebox.showinfo("\u6210\u529f", message, parent=self)
        self.result = True
        self.destroy()

    def _on_login_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="\u767b  \u5f55")
        messagebox.showerror("\u9519\u8bef", message, parent=self)

    def _handle_register(self):
        username = self._reg_username_var.get().strip()
        if not username:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u586b\u5199\u7528\u6237\u540d", parent=self)
            return
        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]{3,50}$", username):
            messagebox.showwarning(
                "\u63d0\u793a",
                "\u7528\u6237\u540d\u97003-50\u4f4d\uff0c\u652f\u6301\u5b57\u6bcd\u6570\u5b57\u4e0b\u5212\u7ebf\u548c\u4e2d\u6587",
                parent=self,
            )
            return
        email = self._reg_email_var.get().strip()
        if not email:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u586b\u5199\u90ae\u7bb1", parent=self)
            return
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            messagebox.showwarning(
                "\u63d0\u793a", "\u8bf7\u8f93\u5165\u6709\u6548\u7684\u90ae\u7bb1\u5730\u5740", parent=self
            )
            return
        password = self._reg_password_var.get().strip()
        if not password:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u586b\u5199\u5bc6\u7801", parent=self)
            return
        if len(password) < 8:
            messagebox.showwarning("\u63d0\u793a", "\u5bc6\u7801\u81f3\u5c118\u4f4d", parent=self)
            return
        if not re.search(r"[A-Z]", password):
            messagebox.showwarning(
                "\u63d0\u793a", "\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u5927\u5199\u5b57\u6bcd", parent=self
            )
            return
        if not re.search(r"[a-z]", password):
            messagebox.showwarning(
                "\u63d0\u793a", "\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u5c0f\u5199\u5b57\u6bcd", parent=self
            )
            return
        if not re.search(r"\d", password):
            messagebox.showwarning(
                "\u63d0\u793a", "\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u6570\u5b57", parent=self
            )
            return
        confirm = self._reg_confirm_var.get().strip()
        if password != confirm:
            messagebox.showwarning(
                "\u63d0\u793a", "\u4e24\u6b21\u5bc6\u7801\u4e0d\u4e00\u81f4", parent=self
            )
            return
        if not self._agree_var.get():
            messagebox.showwarning(
                "\u63d0\u793a", "\u8bf7\u5148\u540c\u610f\u9690\u79c1\u653f\u7b56\u548c\u670d\u52a1\u6761\u6b3e", parent=self
            )
            return

        reg_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[1]).winfo_children():
            if isinstance(child, ttk.Button):
                reg_btn = child
                break
        if reg_btn:
            reg_btn.configure(state=tk.DISABLED, text="\u6ce8\u518c\u4e2d...")

        def do_register():
            success, message = LicenseManager().register_user(username, email, password)
            if success:
                self.after(0, lambda: self._on_register_success(message))
            else:
                self.after(0, lambda: self._on_register_failure(message, reg_btn))

        threading.Thread(target=do_register, daemon=True).start()

    def _on_register_success(self, message):
        messagebox.showinfo("\u6210\u529f", message, parent=self)
        self.result = True
        self.destroy()

    def _on_register_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="\u6ce8  \u518c")
        messagebox.showerror("\u9519\u8bef", message, parent=self)

    def _handle_activate(self):
        username = self._activate_username_var.get().strip()
        password = self._activate_password_var.get().strip()
        code = self._activate_code_var.get().strip()

        if not username or not password:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u586b\u5199\u7528\u6237\u540d\u548c\u5bc6\u7801", parent=self)
            return
        if not code:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u8f93\u5165\u6fc0\u6d3b\u7801", parent=self)
            return

        activate_btn = None
        for child in self._tab_control.nametowidget(self._tab_control.tabs()[2]).winfo_children():
            if isinstance(child, ttk.Button):
                activate_btn = child
                break
        if activate_btn:
            activate_btn.configure(state=tk.DISABLED, text="\u6fc0\u6d3b\u4e2d...")

        def do_activate():
            mgr = LicenseManager()
            success, message = mgr.login_user(username, password)
            if not success:
                self.after(0, lambda: self._on_activate_failure(f"\u767b\u5f55\u5931\u8d25: {message}", activate_btn))
                return
            success2, message2 = mgr.activate_pro_license(code)
            if success2:
                mgr.save_login_credentials(username, password, True, False)
                self.after(0, lambda: self._on_activate_success())
            else:
                self.after(0, lambda: self._on_activate_partial(message2, activate_btn))

        threading.Thread(target=do_activate, daemon=True).start()

    def _on_activate_success(self):
        messagebox.showinfo("\u6210\u529f", "\u6fc0\u6d3b\u6210\u529f\uff01\u4e13\u4e1a\u7248\u5df2\u5f00\u901a", parent=self)
        self.result = True
        self.destroy()

    def _on_activate_partial(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="\u767b\u5f55\u5e76\u6fc0\u6d3b")
        messagebox.showerror("\u9519\u8bef", f"\u6fc0\u6d3b\u5931\u8d25: {message}", parent=self)
        self.result = True
        self.destroy()

    def _on_activate_failure(self, message, btn):
        if btn and btn.winfo_exists():
            btn.configure(state=tk.NORMAL, text="\u767b\u5f55\u5e76\u6fc0\u6d3b")
        messagebox.showerror("\u9519\u8bef", message, parent=self)

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


class PasswordResetDialog(tk.Toplevel):
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
        super().__init__(parent)
        self.title("\u5bc6\u7801\u627e\u56de")
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
            main, text="\u25c6 \u5bc6\u7801\u627e\u56de", font=("Microsoft YaHei", 18, "bold"),
            bg=self._BG, fg=self._ACCENT_LIGHT,
        ).pack(pady=(0, 4))
        tk.Label(
            main,
            text="\u901a\u8fc7\u6ce8\u518c\u90ae\u7bb1\u9a8c\u8bc1\u8eab\u4efd\u540e\u91cd\u7f6e\u5bc6\u7801",
            font=("Microsoft YaHei", 10),
            bg=self._BG, fg=self._HINT_FG,
        ).pack(pady=(0, 14))

        self._make_label(main, "\u6ce8\u518c\u90ae\u7bb1").pack(anchor=tk.W, pady=(0, 4))
        self.email_entry = self._make_entry(main, tk.StringVar() if not hasattr(self, 'email_var') else self.email_var)
        self.email_var = tk.StringVar()
        self.email_entry = self._make_entry(main, self.email_var)
        self.email_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self._make_label(main, "\u9a8c\u8bc1\u7801").pack(anchor=tk.W, pady=(0, 4))
        btn_row = ttk.Frame(main, style="Reset.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 14))
        self.code_var = tk.StringVar()
        self.code_entry = self._make_entry(btn_row, self.code_var)
        self.code_entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=8
        )
        self.send_btn = ttk.Button(
            btn_row,
            text="\u53d1\u9001\u9a8c\u8bc1\u7801",
            command=self._send_code,
            style="Reset.TButton",
        )
        self.send_btn.pack(side=tk.RIGHT)

        self._make_label(main, "\u65b0\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self.new_pass_var = tk.StringVar()
        self.new_pass_entry = self._make_entry(
            main, self.new_pass_var, show="\u25cf"
        )
        self.new_pass_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        self._make_label(main, "\u786e\u8ba4\u65b0\u5bc6\u7801").pack(anchor=tk.W, pady=(0, 4))
        self.confirm_pass_var = tk.StringVar()
        self.confirm_pass_entry = self._make_entry(
            main, self.confirm_pass_var, show="\u25cf"
        )
        self.confirm_pass_entry.pack(fill=tk.X, ipady=8, pady=(0, 14))

        ttk.Button(
            main,
            text="\u91cd\u7f6e\u5bc6\u7801",
            command=self._do_reset,
            style="Reset.Primary.TButton",
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            main, text="\u53d6\u6d88", command=self.destroy, style="Reset.TButton"
        ).pack(fill=tk.X)

        self._code_sent = False
        self._countdown_id = None

    def _send_code(self):
        email = self.email_var.get().strip()
        if not email:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u8f93\u5165\u6ce8\u518c\u90ae\u7bb1", parent=self)
            return
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            messagebox.showwarning(
                "\u63d0\u793a", "\u8bf7\u8f93\u5165\u6709\u6548\u7684\u90ae\u7bb1\u5730\u5740", parent=self
            )
            return
        success, message = LicenseManager().request_password_reset(email)
        if success:
            self._code_sent = True
            messagebox.showinfo("\u6210\u529f", message, parent=self)
            self._start_countdown(60)
        else:
            messagebox.showerror("\u9519\u8bef", message, parent=self)

    def _start_countdown(self, seconds):
        if seconds <= 0:
            self.send_btn.config(text="\u53d1\u9001\u9a8c\u8bc1\u7801", state=tk.NORMAL)
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
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u8f93\u5165\u6ce8\u518c\u90ae\u7bb1", parent=self)
            return
        if not code:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u8f93\u5165\u9a8c\u8bc1\u7801", parent=self)
            return
        if len(new_pass) < 8:
            messagebox.showwarning("\u63d0\u793a", "\u65b0\u5bc6\u7801\u81f3\u5c118\u4f4d", parent=self)
            return
        if not re.search(r"[A-Z]", new_pass):
            messagebox.showwarning(
                "\u63d0\u793a", "\u65b0\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u5927\u5199\u5b57\u6bcd", parent=self
            )
            return
        if not re.search(r"[a-z]", new_pass):
            messagebox.showwarning(
                "\u63d0\u793a", "\u65b0\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u5c0f\u5199\u5b57\u6bcd", parent=self
            )
            return
        if not re.search(r"\d", new_pass):
            messagebox.showwarning(
                "\u63d0\u793a", "\u65b0\u5bc6\u7801\u5fc5\u987b\u5305\u542b\u81f3\u5c11\u4e00\u4e2a\u6570\u5b57", parent=self
            )
            return
        if new_pass != confirm_pass:
            messagebox.showwarning(
                "\u63d0\u793a", "\u4e24\u6b21\u5bc6\u7801\u4e0d\u4e00\u81f4", parent=self
            )
            return

        success, message = LicenseManager().confirm_password_reset(
            email, code, new_pass
        )
        if success:
            messagebox.showinfo("\u6210\u529f", message, parent=self)
            self.destroy()
        else:
            messagebox.showerror("\u9519\u8bef", message, parent=self)

    def destroy(self):
        if self._countdown_id:
            self.after_cancel(self._countdown_id)
        super().destroy()


class PurchaseDialog(tk.Toplevel):
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
            "name": "\u6708\u5361",
            "price": "\u00a514.9/\u6708",
            "desc": "30\u5929\u4e13\u4e1a\u7248",
        },
        {
            "key": "quarterly",
            "name": "\u5b63\u5361",
            "price": "\u00a539.9/\u5b63",
            "desc": "90\u5929\u4e13\u4e1a\u7248",
        },
        {
            "key": "yearly",
            "name": "\u5e74\u5361",
            "price": "\u00a5129.9/\u5e74",
            "desc": "365\u5929\u4e13\u4e1a\u7248",
        },
        {
            "key": "lifetime",
            "name": "\u7ec8\u8eab\u4f1a\u5458",
            "price": "\u00a5219.9",
            "desc": "\u6c38\u4e45\u4e13\u4e1a\u7248",
        },
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("\u8d2d\u4e70\u4f1a\u5458")
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
        return entry

    def _build_ui(self):
        main = ttk.Frame(
            self, style="Purchase.TFrame", padding=(30, 18, 30, 15)
        )
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            main, text="\u25c6 \u8d2d\u4e70\u4f1a\u5458", font=("Microsoft YaHei", 18, "bold"),
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
            main, text="\u6fc0\u6d3b\u7801\u6fc0\u6d3b",
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
        ttk.Button(
            activate_frame,
            text="\u6fc0\u6d3b",
            command=self._do_activate,
            style="Purchase.TButton",
        ).pack(side=tk.RIGHT)

        sep2 = tk.Frame(main, bg=self._DIVIDER, height=1)
        sep2.pack(fill=tk.X, pady=(6, 14))

        pay_label_frame = ttk.Frame(main, style="Purchase.TFrame")
        pay_label_frame.pack(fill=tk.X, pady=(0, 6))
        tk.Label(
            pay_label_frame, text="\u5728\u7ebf\u8d2d\u4e70",
            font=("Microsoft YaHei", 12, "bold"),
            bg=self._BG, fg=self._TEXT_FG,
        ).pack(side=tk.LEFT)
        self._pay_hint = tk.Label(
            pay_label_frame,
            text="\u8bf7\u5148\u9009\u62e9\u5957\u9910",
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
            text="\u652f\u4ed8\u5b9d\u652f\u4ed8",
            command=lambda: self._do_purchase("alipay"),
            style="Purchase.TButton",
        )
        self._alipay_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self._wechat_btn = ttk.Button(
            pay_btn_frame,
            text="\u5fae\u4fe1\u652f\u4ed8",
            command=lambda: self._do_purchase("wechat"),
            style="Purchase.TButton",
        )
        self._wechat_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0))

        ttk.Button(
            main,
            text="\u5173\u95ed",
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
                text="\u26a0 \u5728\u7ebf\u652f\u4ed8\u6682\u672a\u5f00\u901a\uff0c\u8bf7\u8054\u7cfb\u5ba2\u670d\u8d2d\u4e70\u6fc0\u6d3b\u7801\n"
                     "\u60a8\u53ef\u4ee5\u5728\u4e0a\u65b9\"\u6fc0\u6d3b\u7801\u6fc0\u6d3b\"\u533a\u57df\u8f93\u5165\u5ba2\u670d\u63d0\u4f9b\u7684\u6fc0\u6d3b\u7801"
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
                    text="\u26a0 \u90e8\u5206\u652f\u4ed8\u65b9\u5f0f\u6682\u672a\u5f00\u901a\uff0c\u8bf7\u8054\u7cfb\u5ba2\u670d\u8d2d\u4e70\u6fc0\u6d3b\u7801"
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
        self._pay_hint.configure(text=f"\u5df2\u9009\u62e9: {plan_name}")

    def _do_activate(self):
        code = self.activate_var.get().strip()
        if not code:
            messagebox.showwarning(
                "\u63d0\u793a", "\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u6fc0\u6d3b\u7801", parent=self
            )
            return
        mgr = LicenseManager()
        success, message = mgr.activate_pro_license(code)
        if success:
            messagebox.showinfo("\u63d0\u793a", "\u7a0b\u5e8f\u5df2\u6fc0\u6d3b", parent=self)
            self.destroy()
        else:
            messagebox.showerror(
                "\u63d0\u793a", "\u8bf7\u8f93\u5165\u6b63\u786e\u7684\u6fc0\u6d3b\u7801", parent=self
            )

    def _do_purchase(self, payment_method):
        if not self._selected_plan:
            messagebox.showwarning("\u63d0\u793a", "\u8bf7\u5148\u9009\u62e9\u5957\u9910", parent=self)
            return
        mgr = LicenseManager()
        success, result = mgr.purchase_subscription(
            self._selected_plan, payment_method
        )
        if success:
            order_id = result.get("order_id", "")
            qr_code = result.get("qr_code", "")
            msg = result.get("message", "")
            info = f"\u8ba2\u5355\u53f7: {order_id}\n"
            if msg:
                info += f"\u63d0\u793a: {msg}\n"
            if qr_code:
                pay_name = "\u652f\u4ed8\u5b9d" if payment_method == "alipay" else "\u5fae\u4fe1"
                info += f"\n\u8bf7\u4f7f\u7528{pay_name}\u626b\u63cf\u4ee5\u4e0b\u4e8c\u7ef4\u7801\u652f\u4ed8:\n{qr_code}"
            messagebox.showinfo("\u8ba2\u5355\u521b\u5efa\u6210\u529f", info, parent=self)
        else:
            messagebox.showerror(
                "\u9519\u8bef",
                result if isinstance(result, str) else "\u521b\u5efa\u8ba2\u5355\u5931\u8d25",
                parent=self,
            )


def check_and_show_login(parent=None):
    license_mgr = LicenseManager()
    license_status = license_mgr.check_license()
    if not license_status["valid"]:
        if license_mgr._try_silent_relogin():
            license_status = license_mgr.check_license()
            if license_status["valid"]:
                if not license_mgr.verify_with_server():
                    license_status = license_mgr.check_license()
                    if not license_status["valid"]:
                        dialog = LoginDialog(parent)
                        dialog.wait_window()
                        if dialog.result:
                            license_status = license_mgr.check_license()
                            if license_status["valid"]:
                                license_mgr.start_heartbeat()
                                return license_status
                            return license_status
                        return {"valid": False, "message": "用户取消登录"}
                license_mgr.start_heartbeat()
                return license_status
        dialog = LoginDialog(parent)
        dialog.wait_window()
        if dialog.result:
            license_status = license_mgr.check_license()
            if license_status["valid"]:
                if not license_mgr.verify_with_server():
                    license_status = license_mgr.check_license()
                    if not license_status["valid"]:
                        return license_status
                license_mgr.start_heartbeat()
                return license_status
            verify_secret = _get_verify_secret()
            if not verify_secret:
                return {
                    "valid": False,
                    "message": "授权验证组件缺失(.license_verify_key)，请联系客服",
                }
            return license_status
        else:
            return {"valid": False, "message": "用户取消登录"}
    if not license_mgr.verify_with_server():
        license_status = license_mgr.check_license()
        if not license_status["valid"]:
            dialog = LoginDialog(parent)
            dialog.wait_window()
            if dialog.result:
                license_status = license_mgr.check_license()
                if license_status["valid"]:
                    license_mgr.start_heartbeat()
                    return license_status
                return license_status
            return {"valid": False, "message": "用户取消登录"}
    license_mgr.start_heartbeat()
    return license_status
