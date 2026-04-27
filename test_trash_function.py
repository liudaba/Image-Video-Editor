"""
垃圾桶功能测试脚本
用于验证文件移动功能是否正常工作
"""
import os
import shutil
import datetime

def test_trash_function():
    """测试垃圾桶功能"""
    
    # 创建测试目录结构
    test_dir = "test_cleanup"
    images_dir = os.path.join(test_dir, "images")
    
    if not os.path.exists(test_dir):
        os.makedirs(test_dir)
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)
    
    # 创建测试文件
    test_files = [
        os.path.join(test_dir, "shots_data.json"),
        os.path.join(test_dir, "video.mp4"),
        os.path.join(images_dir, "image1.png"),
        os.path.join(images_dir, "image2.png"),
    ]
    
    for file_path in test_files:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("test content")
    
    print("✅ 测试文件创建完成")
    print(f"   - {len(test_files)} 个文件已创建")
    
    # 模拟清理操作
    trash_dir = "垃圾桶"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_session_dir = os.path.join(trash_dir, f"清理_{timestamp}")
    
    if not os.path.exists(trash_session_dir):
        os.makedirs(trash_session_dir)
    
    moved_count = 0
    
    # 移动分镜脚本
    shots_file = os.path.join(test_dir, "shots_data.json")
    if os.path.exists(shots_file):
        dest = os.path.join(trash_session_dir, "shots_data.json")
        shutil.move(shots_file, dest)
        moved_count += 1
        print(f"   ✅ 移动: shots_data.json")
    
    # 移动图片文件
    images_trash_dir = os.path.join(trash_session_dir, "images")
    os.makedirs(images_trash_dir)
    
    for f in os.listdir(images_dir):
        fp = os.path.join(images_dir, f)
        if os.path.isfile(fp):
            dest = os.path.join(images_trash_dir, f)
            shutil.move(fp, dest)
            moved_count += 1
            print(f"   ✅ 移动: images/{f}")
    
    # 移动其他文件
    for f in os.listdir(test_dir):
        fp = os.path.join(test_dir, f)
        if os.path.isfile(fp):
            dest = os.path.join(trash_session_dir, f)
            shutil.move(fp, dest)
            moved_count += 1
            print(f"   ✅ 移动: {f}")
    
    print(f"\n✅ 测试完成！")
    print(f"   - 共移动 {moved_count} 个文件")
    print(f"   - 垃圾桶位置: {trash_session_dir}")
    print(f"\n📂 请检查文件夹确认文件已正确移动")
    
    # 清理测试目录（如果为空）
    try:
        if os.path.exists(images_dir) and not os.listdir(images_dir):
            os.rmdir(images_dir)
        if os.path.exists(test_dir) and not os.listdir(test_dir):
            os.rmdir(test_dir)
    except:
        pass

if __name__ == "__main__":
    print("=" * 60)
    print("🗑️ 垃圾桶功能测试")
    print("=" * 60)
    test_trash_function()
    print("\n提示: 测试完成后可以手动删除'垃圾桶'文件夹中的测试数据")
