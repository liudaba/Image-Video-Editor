"""
生成README演示用的占位图片
运行此脚本可以快速生成临时截图,用于GitHub README展示
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_placeholder_image(width, height, text, output_path, bg_color=(40, 44, 52), text_color=(255, 255, 255)):
    """
    创建占位图片
    
    参数:
        width: 图片宽度
        height: 图片高度
        text: 显示的文字
        output_path: 输出路径
        bg_color: 背景颜色 (R, G, B)
        text_color: 文字颜色 (R, G, B)
    """
    # 创建图片
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 尝试使用系统字体
    try:
        # Windows系统字体
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 48)
    except:
        try:
            # macOS系统字体
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 48)
        except:
            # 使用默认字体
            font = ImageFont.load_default()
    
    # 计算文字位置(居中)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    
    # 绘制文字
    draw.text((x, y), text, fill=text_color, font=font)
    
    # 添加边框效果
    draw.rectangle([10, 10, width-10, height-10], outline=(100, 100, 100), width=3)
    
    # 保存图片
    img.save(output_path, 'PNG', optimize=True, quality=95)
    print(f"✅ 已生成: {output_path}")


def main():
    """生成所有占位图片"""
    
    # 确保目录存在
    os.makedirs("docs/screenshots", exist_ok=True)
    os.makedirs("docs/demo", exist_ok=True)
    
    print("🎨 开始生成占位图片...\n")
    
    # 主界面截图
    create_placeholder_image(
        width=1200,
        height=800,
        text="主界面截图\nMain Interface",
        output_path="docs/screenshots/main_interface.png",
        bg_color=(40, 44, 52)
    )
    
    # 高级设置面板截图
    create_placeholder_image(
        width=1200,
        height=900,
        text="高级设置面板\nAdvanced Settings",
        output_path="docs/screenshots/advanced_settings.png",
        bg_color=(50, 54, 62)
    )
    
    # 生成过程截图
    create_placeholder_image(
        width=1200,
        height=800,
        text="生成过程截图\nGeneration Process\n进度: 65%",
        output_path="docs/screenshots/generation_process.png",
        bg_color=(45, 49, 57)
    )
    
    print("\n✨ 所有占位图片生成完成!")
    print("\n📝 下一步:")
    print("1. 查看生成的图片: docs/screenshots/")
    print("2. 替换为真实的程序截图")
    print("3. 制作演示视频放入 docs/demo/")
    print("4. 更新 README.md 中的图片链接")


if __name__ == "__main__":
    main()
