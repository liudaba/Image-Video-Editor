#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动发布助手 - 一键发布新版本
用法: python release_helper.py --version "1.1.0" --message "修复音频导入bug"
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path


class ReleaseHelper:
    """自动发布助手"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.config_file = self.project_root / "config.json"
        self.versions_file = self.project_root / "backend" / "versions.json"
        self.version_api_url = "http://localhost:5001/api/version/publish"  # 本地测试用
        
    def step1_generate_version(self, version_input=None):
        """步骤1: 生成或确认版本号"""
        print("\n" + "="*60)
        print("📋 步骤 1/7: 生成版本号")
        print("="*60)
        
        if version_input:
            version = version_input
            print(f"✅ 使用指定版本号: v{version}")
        else:
            # 读取当前版本
            current_version = self._get_current_version()
            print(f"📌 当前版本: v{current_version}")
            
            # 自动递增修订号
            parts = current_version.split('.')
            parts[-1] = str(int(parts[-1]) + 1)
            auto_version = '.'.join(parts)
            
            user_input = input(f"\n建议新版本号: v{auto_version}\n是否使用? (Y/n): ")
            version = auto_version if user_input.lower() != 'n' else input("请输入新版本号: ")
        
        return version
    
    def step2_update_config(self, version):
        """步骤2: 更新config.json中的版本号"""
        print("\n" + "="*60)
        print("📝 步骤 2/7: 更新配置文件")
        print("="*60)
        
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            old_version = config.get('version', '1.0.0')
            config['version'] = version
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"✅ 版本号已更新: {old_version} → {version}")
        else:
            print("⚠️  config.json不存在,跳过")
    
    def step3_build_exe(self):
        """步骤3: 打包EXE"""
        print("\n" + "="*60)
        print("🔨 步骤 3/7: 打包程序")
        print("="*60)
        
        build_script = self.project_root / "build_exe.py"
        if not build_script.exists():
            print("❌ build_exe.py不存在")
            return False
        
        print("🚀 开始打包...")
        try:
            result = subprocess.run(
                [sys.executable, str(build_script)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10分钟超时
            )
            
            if result.returncode == 0:
                print("✅ 打包成功!")
                print(result.stdout[-500:])  # 显示最后500字符
                return True
            else:
                print("❌ 打包失败:")
                print(result.stderr)
                return False
        except Exception as e:
            print(f"❌ 打包异常: {e}")
            return False
    
    def step4_compile_installer(self):
        """步骤4: 编译安装器"""
        print("\n" + "="*60)
        print("📦 步骤 4/7: 编译安装器")
        print("="*60)
        
        installer_script = self.project_root / "installer_setup.iss"
        if not installer_script.exists():
            print("⚠️  installer_setup.iss不存在,跳过")
            return True
        
        print("🔧 请使用Inno Setup手动编译:")
        print(f"   脚本位置: {installer_script}")
        print("   编译后生成的安装包请放在: releases/vX.X.X/")
        
        user_confirm = input("\n是否已完成编译? (y/n): ")
        return user_confirm.lower() == 'y'
    
    def step5_upload_to_cdn(self, version):
        """步骤5: 上传到CDN(可选)"""
        print("\n" + "="*60)
        print("☁️  步骤 5/7: 上传到CDN")
        print("="*60)
        
        use_cdn = input("是否上传到CDN? (y/n, 默认n): ").lower()
        if use_cdn != 'y':
            print("⏭️  跳过CDN上传")
            return None
        
        # TODO: 实现CDN上传逻辑
        cdn_url = input("请输入CDN地址: ")
        print(f"⚠️  请手动上传安装包到: {cdn_url}/releases/v{version}/")
        
        file_url = input("上传完成后,请输入文件URL: ")
        return file_url
    
    def step6_publish_version(self, version, changelog, download_url=None):
        """步骤6: 发布版本到服务器"""
        print("\n" + "="*60)
        print("🚀 步骤 6/7: 发布版本")
        print("="*60)
        
        # 构建发布数据
        publish_data = {
            "version": version,
            "release_date": datetime.now().strftime("%Y-%m-%d"),
            "download_url": download_url or f"./releases/v{version}/installer.exe",
            "file_size": self._get_file_size(download_url),
            "changelog": changelog,
            "force_update": False,
            "priority": "normal"
        }
        
        print("\n📋 发布信息预览:")
        print(json.dumps(publish_data, indent=2, ensure_ascii=False))
        
        confirm = input("\n确认发布? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ 取消发布")
            return False
        
        # 调用API发布
        try:
            import requests
            response = requests.post(
                self.version_api_url,
                json=publish_data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 发布成功: {result.get('message')}")
                return True
            else:
                print(f"❌ 发布失败: {response.status_code}")
                print(response.text)
                return False
        except ImportError:
            print("⚠️  requests库未安装,无法调用API")
            print("💡 请手动调用以下curl命令:")
            print(f"curl -X POST {self.version_api_url} \\")
            print(f"  -H 'Content-Type: application/json' \\")
            print(f"  -d '{json.dumps(publish_data, ensure_ascii=False)}'")
            return True
        except Exception as e:
            print(f"❌ 发布异常: {e}")
            return False
    
    def step7_notify_users(self, version):
        """步骤7: 通知用户(可选)"""
        print("\n" + "="*60)
        print("📢 步骤 7/7: 通知用户")
        print("="*60)
        
        notify_channels = []
        
        if input("是否在B站发布更新公告? (y/n): ").lower() == 'y':
            notify_channels.append("bilibili")
        
        if input("是否在知乎发布更新文章? (y/n): ").lower() == 'y':
            notify_channels.append("zhihu")
        
        if input("是否在用户群发布公告? (y/n): ").lower() == 'y':
            notify_channels.append("qq_group")
        
        if notify_channels:
            print(f"\n✅ 将在以下渠道发布通知: {', '.join(notify_channels)}")
            print("💡 提示: 可以使用预设的更新公告模板")
        else:
            print("⏭️  跳过用户通知")
    
    def run(self, version=None, message=None):
        """执行完整发布流程"""
        print("\n" + "🎉"*30)
        print("  短视频生成器 - 自动发布助手")
        print("🎉"*30)
        
        try:
            # 步骤1: 生成版本号
            version = self.step1_generate_version(version)
            
            # 步骤2: 更新配置
            self.step2_update_config(version)
            
            # 步骤3: 打包程序
            if not self.step3_build_exe():
                print("\n❌ 打包失败,发布中止")
                return False
            
            # 步骤4: 编译安装器
            if not self.step4_compile_installer():
                print("\n❌ 安装器编译未完成,发布中止")
                return False
            
            # 收集更新日志
            changelog = self._collect_changelog(message)
            
            # 步骤5: 上传CDN
            download_url = self.step5_upload_to_cdn(version)
            
            # 步骤6: 发布版本
            if not self.step6_publish_version(version, changelog, download_url):
                print("\n❌ 版本发布失败")
                return False
            
            # 步骤7: 通知用户
            self.step7_notify_users(version)
            
            # 完成
            print("\n" + "🎊"*30)
            print(f"  ✅ 版本 v{version} 发布成功!")
            print("🎊"*30)
            print("\n📝 后续操作:")
            print("1. 检查更新服务器是否正常响应")
            print("2. 在社交媒体发布更新公告")
            print("3. 监控用户反馈和下载统计")
            
            return True
            
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断发布流程")
            return False
        except Exception as e:
            print(f"\n❌ 发布过程出错: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _get_current_version(self):
        """获取当前版本号"""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('version', '1.0.0')
        return '1.0.0'
    
    def _collect_changelog(self, initial_message=None):
        """收集更新日志"""
        print("\n" + "="*60)
        print("📝 收集更新日志")
        print("="*60)
        
        changelog = []
        
        if initial_message:
            changelog.append(initial_message)
            print(f"✅ 已添加: {initial_message}")
        
        while True:
            item = input("\n添加更新项(直接回车结束): ")
            if not item:
                break
            changelog.append(item)
            print(f"✅ 已添加: {item}")
        
        if not changelog:
            changelog.append("常规更新和优化")
        
        return changelog
    
    def _get_file_size(self, file_path):
        """获取文件大小"""
        if file_path and os.path.exists(file_path):
            size = os.path.getsize(file_path)
            return size
        return 0


def main():
    parser = argparse.ArgumentParser(description='自动发布助手')
    parser.add_argument('--version', type=str, help='指定版本号')
    parser.add_argument('--message', type=str, help='更新说明')
    
    args = parser.parse_args()
    
    helper = ReleaseHelper()
    success = helper.run(version=args.version, message=args.message)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
