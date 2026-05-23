"""
短视频生成器 - 后台管理系统启动器
直接打开远程管理后台
"""
import sys
import webbrowser


ADMIN_URL = "https://api.wangzha178.com/admin/login"


def main():
    print("=" * 60)
    print("短视频生成器 - 后台管理系统启动器")
    print("=" * 60)
    print(f"🌐 正在打开管理后台: {ADMIN_URL}")
    webbrowser.open(ADMIN_URL)
    print("✅ 浏览器已打开，如未自动跳转请手动访问上述地址")
    return 0


if __name__ == "__main__":
    sys.exit(main())
