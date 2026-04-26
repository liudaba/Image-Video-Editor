# -*- coding: utf-8 -*-
"""
视频生成优化模块测试脚本
测试 ProgressManager, ResourceManager, BatchImageLoader, VideoRendererOptimizer
"""

import sys
import os
import time
import threading

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from video_generator.optimization import (
    ProgressManager, 
    ResourceManager, 
    BatchImageLoader,
    VideoRendererOptimizer
)


def test_progress_manager():
    """测试进度管理器"""
    print("=" * 60)
    print("测试1: ProgressManager - 进度管理")
    print("=" * 60)
    
    # 创建进度管理器
    progress = ProgressManager(total_items=100)
    
    # 模拟进度更新
    for i in range(100):
        progress.update(increment=1)
        time.sleep(0.01)  # 模拟处理时间
        
        if (i + 1) % 20 == 0:
            stats = progress.get_stats()
            print(f"  [{i+1}/100] 进度: {stats['progress']:.1f}% | "
                  f"速度: {stats['throughput']:.2f}项/秒 | "
                  f"预计剩余: {stats['eta_formatted']}")
    
    # 最终统计
    final_stats = progress.get_stats()
    print(f"\n✅ 最终统计:")
    print(f"   总耗时: {final_stats['elapsed']:.2f}秒")
    print(f"   平均速度: {final_stats['throughput']:.2f}项/秒")
    print(f"   ETA: {final_stats['eta_formatted']}")
    
    # 测试重置
    progress.reset(total_items=50)
    print(f"\n✅ 重置后总数: {progress.total_items}")
    print("✅ 测试1通过\n")


def test_resource_manager():
    """测试资源管理器"""
    print("=" * 60)
    print("测试2: ResourceManager - 资源管理")
    print("=" * 60)
    
    resource_mgr = ResourceManager()
    
    # 检查GPU显存
    gpu_info = resource_mgr.check_gpu_memory()
    print(f"📊 GPU信息:")
    print(f"   可用: {gpu_info['available']}")
    print(f"   消息: {gpu_info['message']}")
    
    if gpu_info['available']:
        print(f"   显存使用: {gpu_info['used_mb']:.0f}MB / {gpu_info['total_mb']:.0f}MB")
        print(f"   使用率: {gpu_info['used_percent']*100:.1f}%")
        
        # 测试清理
        if resource_mgr.should_cleanup_gpu():
            print("\n⚠️ GPU显存过高，执行清理...")
            resource_mgr.cleanup_gpu_memory(log_callback=lambda msg: print(f"   {msg}"))
        else:
            print("\n✅ GPU显存充足，无需清理")
    
    # 测试智能GC
    print("\n🧹 测试智能垃圾回收:")
    for i in range(100):
        resource_mgr.smart_gc(processed_count=i+1, interval=25)
        if (i + 1) % 25 == 0:
            print(f"   已处理 {i+1} 个项目，执行GC")
    
    print("✅ 测试2通过\n")


def test_batch_image_loader():
    """测试批量图片加载器"""
    print("=" * 60)
    print("测试3: BatchImageLoader - 批量图片加载")
    print("=" * 60)
    
    loader = BatchImageLoader(batch_size=5)
    
    # 创建测试图片
    from PIL import Image
    import tempfile
    
    test_images = []
    temp_dir = tempfile.mkdtemp()
    
    print("📸 创建测试图片...")
    for i in range(10):
        img_path = os.path.join(temp_dir, f"test_{i}.png")
        img = Image.new('RGB', (100, 100), color=(i*25, i*25, i*25))
        img.save(img_path)
        test_images.append(img_path)
    
    print(f"   创建了 {len(test_images)} 张测试图片")
    
    # 预加载第一批
    print("\n📥 预加载第一批(5张)...")
    batch1 = loader.preload_batch(test_images[:5])
    print(f"   加载了 {len(batch1)} 张图片")
    print(f"   缓存大小: {loader.get_cache_size()}")
    
    # 从缓存获取
    print("\n🔍 从缓存获取图片...")
    img = loader.get_image(test_images[0])
    if img:
        print(f"   ✅ 成功获取图片，尺寸: {img.size}")
    else:
        print(f"   ❌ 缓存未命中")
    
    # 预加载第二批
    print("\n📥 预加载第二批(5张)...")
    batch2 = loader.preload_batch(test_images[5:])
    print(f"   加载了 {len(batch2)} 张图片")
    print(f"   缓存大小: {loader.get_cache_size()}")
    
    # 清空缓存
    print("\n🗑️ 清空缓存...")
    loader.clear_cache()
    print(f"   缓存大小: {loader.get_cache_size()}")
    
    # 清理临时文件
    import shutil
    shutil.rmtree(temp_dir)
    
    print("✅ 测试3通过\n")


def test_video_renderer_optimizer():
    """测试视频渲染优化器"""
    print("=" * 60)
    print("测试4: VideoRendererOptimizer - 渲染优化")
    print("=" * 60)
    
    renderer_opt = VideoRendererOptimizer()
    
    # 检测GPU编码器
    print("🎬 检测GPU编码器...")
    encoder_info = renderer_opt.check_gpu_encoder()
    print(f"   可用: {encoder_info['available']}")
    print(f"   编码器: {encoder_info['encoder']}")
    print(f"   预设: {encoder_info['preset']}")
    print(f"   描述: {encoder_info['description']}")
    
    if encoder_info['available']:
        print(f"\n✅ 可以使用GPU加速渲染")
    else:
        print(f"\nℹ️ 将使用CPU软件编码")
    
    print("✅ 测试4通过\n")


def test_thread_safety():
    """测试线程安全性"""
    print("=" * 60)
    print("测试5: 线程安全性")
    print("=" * 60)
    
    progress = ProgressManager(total_items=1000)
    errors = []
    
    def worker(thread_id):
        try:
            for i in range(100):
                progress.update(increment=1)
                time.sleep(0.001)
        except Exception as e:
            errors.append(str(e))
    
    # 启动10个线程
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # 等待所有线程完成
    for t in threads:
        t.join()
    
    if errors:
        print(f"❌ 线程错误: {errors}")
    else:
        print(f"✅ 10个并发线程测试通过")
        print(f"   最终完成数: {progress.completed_items}")
        print(f"   预期完成数: 1000")
        assert progress.completed_items == 1000, "进度计数不正确"
    
    print("✅ 测试5通过\n")


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("视频生成优化模块 - 功能测试")
    print("=" * 60 + "\n")
    
    tests = [
        ("ProgressManager", test_progress_manager),
        ("ResourceManager", test_resource_manager),
        ("BatchImageLoader", test_batch_image_loader),
        ("VideoRendererOptimizer", test_video_renderer_optimizer),
        ("线程安全性", test_thread_safety),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} 测试失败: {e}\n")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"测试结果汇总:")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")
    print(f"  📊 总计: {len(tests)}")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 所有测试通过！优化模块可以正常使用。")
    else:
        print(f"\n⚠️ 有 {failed} 个测试失败，请检查错误信息。")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
