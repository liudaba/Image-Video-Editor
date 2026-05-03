"""
短视频生成器 - 授权和试用管理系统
功能:
1. 用户注册/登录
2. 7天免费试用
3. 付费订阅验证
4. 离线授权支持
"""

import json
import os
import sys
from datetime import datetime, timedelta
import requests
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt5.QtCore import Qt


class LicenseManager:
    """授权管理器 - 单例模式"""
    
    _instance = None
    API_BASE = "https://api.videogen.com"  # 授权服务器地址
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.license_data = None
            cls._instance.load_license()
        return cls._instance
    
    def load_license(self):
        """加载本地授权信息"""
        try:
            license_file = self.get_license_path()
            if os.path.exists(license_file):
                with open(license_file, 'r', encoding='utf-8') as f:
                    self.license_data = json.load(f)
            else:
                self.license_data = None
        except:
            self.license_data = None
    
    def save_license(self, license_data):
        """保存授权信息到本地"""
        try:
            license_file = self.get_license_path()
            os.makedirs(os.path.dirname(license_file), exist_ok=True)
            
            with open(license_file, 'w', encoding='utf-8') as f:
                json.dump(license_data, f, indent=2, ensure_ascii=False)
            
            self.license_data = license_data
            return True
        except Exception as e:
            print(f"保存授权失败: {e}")
            return False
    
    def get_license_path(self):
        """获取授权文件路径"""
        if getattr(sys, 'frozen', False):
            # 打包后的路径
            base_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境路径
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(base_dir, 'license.json')
    
    def register_user(self, username, email, password):
        """用户注册"""
        try:
            response = requests.post(
                f"{self.API_BASE}/api/auth/register",
                json={
                    "username": username,
                    "email": email,
                    "password": password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                # 自动登录并获取试用授权
                return self.login_user(username, password)
            else:
                error_msg = response.json().get('detail', '注册失败')
                return False, error_msg
        
        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器,请检查网络连接"
        except Exception as e:
            return False, f"注册失败: {str(e)}"
    
    def login_user(self, username, password):
        """用户登录"""
        try:
            response = requests.post(
                f"{self.API_BASE}/api/auth/login",
                json={
                    "username": username,
                    "password": password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                license_data = {
                    "username": username,
                    "token": data['access_token'],
                    "trial_start": datetime.now().isoformat(),
                    "trial_end": (datetime.now() + timedelta(days=7)).isoformat(),
                    "license_type": "trial",
                    "is_active": True
                }
                
                self.save_license(license_data)
                return True, "登录成功!您有7天免费试用期"
            else:
                error_msg = response.json().get('detail', '登录失败')
                return False, error_msg
        
        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器,请检查网络连接"
        except Exception as e:
            return False, f"登录失败: {str(e)}"
    
    def check_license(self):
        """检查授权状态"""
        if not self.license_data:
            return {
                "valid": False,
                "message": "未登录,请先注册或登录"
            }
        
        # 检查是否在试用期内
        trial_end = datetime.fromisoformat(self.license_data.get('trial_end'))
        now = datetime.now()
        
        if now <= trial_end:
            days_left = (trial_end - now).days
            return {
                "valid": True,
                "type": "trial",
                "days_left": days_left,
                "message": f"试用期剩余 {days_left} 天"
            }
        
        # 试用期结束,检查是否有正式授权
        if self.license_data.get('license_type') == 'pro':
            expiry_date = datetime.fromisoformat(self.license_data.get('expiry_date'))
            if now <= expiry_date:
                days_left = (expiry_date - now).days
                return {
                    "valid": True,
                    "type": "pro",
                    "days_left": days_left,
                    "message": f"专业版剩余 {days_left} 天"
                }
        
        return {
            "valid": False,
            "message": "试用期已结束,请购买专业版继续使用"
        }
    
    def activate_pro_license(self, license_key):
        """激活专业版授权"""
        try:
            response = requests.post(
                f"{self.API_BASE}/api/license/activate",
                json={"license_key": license_key},
                headers={"Authorization": f"Bearer {self.license_data['token']}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.license_data.update({
                    "license_type": "pro",
                    "expiry_date": data['expiry_date'],
                    "license_key": license_key
                })
                self.save_license(self.license_data)
                return True, "专业版激活成功!"
            else:
                error_msg = response.json().get('detail', '激活失败')
                return False, error_msg
        
        except Exception as e:
            return False, f"激活失败: {str(e)}"
    
    def purchase_subscription(self, plan_type, payment_method):
        """购买订阅"""
        try:
            response = requests.post(
                f"{self.API_BASE}/api/payment/create_order",
                json={
                    "plan_type": plan_type,  # 'monthly' or 'yearly'
                    "payment_method": payment_method  # 'alipay' or 'wechat'
                },
                headers={"Authorization": f"Bearer {self.license_data['token']}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                return True, data  # 返回支付链接或二维码
            else:
                return False, response.json().get('detail', '创建订单失败')
        
        except Exception as e:
            return False, f"创建订单失败: {str(e)}"
    
    def logout(self):
        """登出"""
        self.license_data = None
        license_file = self.get_license_path()
        if os.path.exists(license_file):
            os.remove(license_file)


class LoginDialog(QDialog):
    """登录/注册对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = 'login'  # 'login' or 'register'
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("用户登录" if self.mode == 'login' else "用户注册")
        self.setFixedSize(450, 350)
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QLabel {
                color: #333;
            }
            QLineEdit {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }
            QPushButton {
                padding: 12px 24px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Logo和标题
        title_layout = QVBoxLayout()
        logo_label = QLabel("🎬 短视频生成器")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #2196F3; margin-bottom: 10px;")
        title_layout.addWidget(logo_label)
        
        subtitle = QLabel("AI驱动的音频转视频工具")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666; font-size: 12px;")
        title_layout.addWidget(subtitle)
        layout.addLayout(title_layout)
        
        # 用户名输入
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("用户名")
        layout.addWidget(self.username_input)
        
        # 邮箱输入(仅注册时显示)
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("邮箱地址")
        self.email_input.setVisible(False)
        layout.addWidget(self.email_input)
        
        # 密码输入
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)
        
        # 确认密码(仅注册时显示)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("确认密码")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input.setVisible(False)
        layout.addWidget(self.confirm_password_input)
        
        # 操作按钮
        action_btn = QPushButton("登录" if self.mode == 'login' else "注册")
        action_btn.clicked.connect(self.handle_action)
        layout.addWidget(action_btn)
        
        # 切换模式按钮
        switch_text = "还没有账号?立即注册" if self.mode == 'login' else "已有账号?立即登录"
        switch_btn = QPushButton(switch_text)
        switch_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #2196F3;
                border: none;
                text-decoration: underline;
            }
        """)
        switch_btn.clicked.connect(self.toggle_mode)
        layout.addWidget(switch_btn)
        
        # 试用提示
        trial_hint = QLabel("✨ 注册即享7天免费试用!")
        trial_hint.setAlignment(Qt.AlignCenter)
        trial_hint.setStyleSheet("color: #FF5722; font-size: 12px; margin-top: 10px;")
        layout.addWidget(trial_hint)
        
        self.setLayout(layout)
    
    def toggle_mode(self):
        """切换登录/注册模式"""
        self.mode = 'register' if self.mode == 'login' else 'login'
        
        # 更新UI
        self.email_input.setVisible(self.mode == 'register')
        self.confirm_password_input.setVisible(self.mode == 'register')
        
        action_btn = self.findChild(QPushButton, text="登录" if self.mode == 'register' else "注册")
        if action_btn:
            action_btn.setText("注册" if self.mode == 'register' else "登录")
        
        switch_text = "还没有账号?立即注册" if self.mode == 'login' else "已有账号?立即登录"
        switch_btn = self.findChild(QPushButton, text="已有账号?立即登录" if self.mode == 'register' else "还没有账号?立即注册")
        if switch_btn:
            switch_btn.setText(switch_text)
        
        self.setWindowTitle("用户登录" if self.mode == 'login' else "用户注册")
    
    def handle_action(self):
        """处理登录或注册"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, "提示", "请填写用户名和密码")
            return
        
        if self.mode == 'login':
            success, message = LicenseManager().login_user(username, password)
        else:
            email = self.email_input.text().strip()
            confirm_pwd = self.confirm_password_input.text().strip()
            
            if not email:
                QMessageBox.warning(self, "提示", "请填写邮箱")
                return
            
            if password != confirm_pwd:
                QMessageBox.warning(self, "提示", "两次密码不一致")
                return
            
            success, message = LicenseManager().register_user(username, email, password)
        
        if success:
            QMessageBox.information(self, "成功", message)
            self.accept()
        else:
            QMessageBox.critical(self, "错误", message)


def check_and_show_login():
    """检查授权并显示登录对话框"""
    license_mgr = LicenseManager()
    
    # 检查是否有有效授权
    license_status = license_mgr.check_license()
    
    if not license_status['valid']:
        # 需要登录
        dialog = LoginDialog()
        if dialog.exec_():
            # 登录成功,重新检查
            license_status = license_mgr.check_license()
            return license_status
        else:
            # 用户取消登录
            return {"valid": False, "message": "用户取消登录"}
    
    return license_status
