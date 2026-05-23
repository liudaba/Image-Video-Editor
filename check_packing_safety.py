#!/usr/bin/env python3
"""
打包安全检查脚本
检查打包前是否存在不应该包含的文件或目录

使用方式:
    python check_packing_safety.py

返回码:
    0 - 检查通过
    1 - 检查失败（存在敏感文件）
"""

import os
import sys
from pathlib import Path


def print_section(title):
    """打印分节标题"""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}")


def print_result(icon, message):
    """打印结果"""
    print(f"  {icon} {message}")


class SafetyChecker:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passed = []

    def add_error(self, message):
        """添加错误"""
        self.errors.append(message)
        print_result("❌", message)

    def add_warning(self, message):
        """添加警告"""
        self.warnings.append(message)
        print_result("⚠️ ", message)

    def add_pass(self, message):
        """添加通过项"""
        self.passed.append(message)
        print_result("✅", message)

    def check_sensitive_files(self):
        """检查敏感文件"""
        print_section("检查敏感文件")

        sensitive_files_will_clean = [
            '.key_salt',
            '配置信息.txt',
            'create_config.py',
            'generate_config.py',
            'setup_config.py',
            '设置配置.bat',
        ]

        found = False
        for file in sensitive_files_will_clean:
            if os.path.exists(file):
                self.add_warning(f"发现敏感文件: {file} (打包时会自动清理)")
                found = True

        sensitive_files_must_fix = [
            '.env',
            '.env.local',
            '.env.production',
            '.secret_key',
            '.license_sign_key',
            'current_ssh_password.txt',
            'ssh_password_history.txt',
            'ssh_password_manager.py',
            'generate_signing_keys.py',
            '_audit_server.py',
            '_check.py',
            '_cleanup_server.py',
        ]

        for file in sensitive_files_must_fix:
            if os.path.exists(file):
                self.add_error(f"发现高危敏感文件: {file}")
                found = True

        if not found:
            self.add_pass("未发现敏感文件")

    def check_develop_files(self):
        """检查开发文件"""
        print_section("检查开发文件")

        develop_files = [
            'requirements.txt',
            'pyproject.toml',
            'setup.py',
            'setup.cfg',
            'MANIFEST.in',
            '.gitignore',
            '.editorconfig',
            '.flake8',
            'pytest.ini',
            'tox.ini',
        ]

        for file in develop_files:
            if os.path.exists(file):
                self.add_warning(f"发现开发文件: {file} (打包时会自动排除)")

        if not self.warnings:
            self.add_pass("未发现开发文件")

    def check_develop_dirs(self):
        """检查开发目录"""
        print_section("检查开发目录")

        develop_dirs = [
            '.git',
            '.vscode',
            '.idea',
            '.venv',
            'backend',
            'keys',
            'models',
            'output_project',
            'trash',
            'docs',
            'logs',
            '__pycache__',
            '.trae',
            'tests',
            '.pytest_cache',
            'htmlcov',
            '.coverage',
        ]

        found = False
        for dir_name in develop_dirs:
            if os.path.isdir(dir_name):
                self.add_warning(f"发现开发目录: {dir_name}/ (打包时会自动排除)")
                found = True

        if not found:
            self.add_pass("未发现开发目录")

    def check_backend_system(self):
        """检查后台管理系统相关文件"""
        print_section("检查后台管理系统文件")

        backend_files = [
            '后台管理系统启动器.py',
            '停止后台管理系统.bat',
            'videogen/',
            'server/',
            'app/',
        ]

        found = False
        for file in backend_files:
            if os.path.exists(file):
                self.add_warning(f"发现后台系统文件: {file} (可能不应打包)")
                found = True

        if not found:
            self.add_pass("未发现后台管理系统文件")

    def check_required_files(self):
        """检查必需文件"""
        print_section("检查必需文件")

        required_files = [
            ('video_generator/', '核心程序目录'),
            ('run.py', '启动入口'),
            ('config.json', '配置文件'),
            ('assets/icon.ico', '程序图标'),
        ]

        all_found = True
        for file, desc in required_files:
            if os.path.isdir(file) or os.path.exists(file):
                self.add_pass(f"{file} ({desc})")
            else:
                self.add_error(f"缺少必需文件: {file} ({desc})")
                all_found = False

        return all_found

    def check_optional_files(self):
        """检查可选文件"""
        print_section("检查可选文件")

        optional_files = [
            ('README.md', '项目说明'),
            ('LICENSE', '软件许可证'),
            ('USER_GUIDE.md', '使用指南'),
            ('QuickStart.md', '快速入门'),
            ('TERMS_OF_SERVICE.md', '服务条款'),
            ('PRIVACY_POLICY.md', '隐私政策'),
            ('.license_verify_pubkey.pem', 'ECDSA签名验证公钥'),
        ]

        for file, desc in optional_files:
            if os.path.isdir(file) or os.path.exists(file):
                self.add_pass(f"{file} ({desc})")
            else:
                self.add_warning(f"{file} 缺失 ({desc})")

    def check_security_keys(self):
        """检查安全密钥"""
        print_section("检查安全密钥")

        key_patterns = ['*.pem', '*.key', '*.crt', '*.cert']
        whitelist = ['.license_verify_pubkey.pem']

        found_sensitive = False
        for pattern in key_patterns:
            import glob
            matches = glob.glob(pattern)
            if matches:
                for match in matches:
                    basename = os.path.basename(match)
                    if basename in whitelist:
                        self.add_pass(f"授权验证公钥(允许): {match}")
                    else:
                        self.add_error(f"发现密钥文件: {match}")
                        found_sensitive = True

        if not found_sensitive and not any(glob.glob(p) for p in key_patterns):
            self.add_pass("未发现密钥文件")

    def check_database_files(self):
        """检查数据库文件"""
        print_section("检查数据库文件")

        import glob
        db_files = glob.glob('*.db') + glob.glob('*.sqlite') + glob.glob('*.sqlite3')

        if db_files:
            for db in db_files:
                self.add_error(f"发现数据库文件: {db}")
        else:
            self.add_pass("未发现数据库文件")

    def generate_report(self):
        """生成检查报告"""
        print_section("检查报告")

        print(f"\n📊 检查统计:")
        print(f"  ✅ 通过: {len(self.passed)} 项")
        print(f"  ⚠️  警告: {len(self.warnings)} 项")
        print(f"  ❌ 错误: {len(self.errors)} 项")

        if self.errors:
            print(f"\n🔴 发现 {len(self.errors)} 个错误:")
            for error in self.errors:
                print(f"   - {error}")
            return False

        if self.warnings:
            print(f"\n🟡 发现 {len(self.warnings)} 个警告:")
            for warning in self.warnings:
                print(f"   - {warning}")

        print(f"\n🟢 检查通过! 可以开始打包。")
        return True


def main():
    print("\n" + "=" * 60)
    print(" 打包安全检查工具")
    print(" 检查时间: " + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    checker = SafetyChecker()

    # 执行所有检查
    checker.check_sensitive_files()
    checker.check_security_keys()
    checker.check_database_files()
    checker.check_develop_files()
    checker.check_develop_dirs()
    checker.check_backend_system()

    required_ok = checker.check_required_files()
    checker.check_optional_files()

    # 生成报告
    success = checker.generate_report()

    # 返回结果
    if success and required_ok:
        print("\n✅ 安全检查通过! 可以开始打包。\n")
        return 0
    elif required_ok:
        print("\n⚠️  有警告但可以继续打包。\n")
        return 0
    else:
        print("\n❌ 安全检查失败! 请修复错误后重新打包。\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
