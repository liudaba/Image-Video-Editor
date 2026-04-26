# 视频生成优化模块使用指南

## 📦 模块概述

`video_generator/optimization.py` 提供了4个核心优化类:

1. **ProgressManager** - 统一进度管理和ETA预测
2. **ResourceManager** - 智能GPU显存和内存管理
3. **BatchImageLoader** - 批量图片预加载器
4. **VideoRendererOptimizer** - 视频渲染优化器

---

## 🚀 快速开始

### 1. ProgressManager - 进度管理

```python
from video_generator.optimization import ProgressManager

# 创建进度管理器(总共100个项目)
progress = ProgressManager(total_items=100)

# 更新进度(增量方式)
progress.update(increment=1)

# 或直接设置完成数
progress.update(completed=50)

# 获取统计信息
stats = progress.get_stats()
print(f"进度: {stats['progress']:.1f}%")
print(f"已完成: {stats['completed']}/{stats['total']}")
print(f"吞吐量: {stats['throughput']:.2f} 项/秒")
print(f"预计剩余: {stats['eta_formatted']}")

# 重置进度管理器
progress.reset(total_items=200)
```

**输出示例:**
```
进度: 50.0%
已完成: 50/100
吞吐量: 2.35 项/秒
预计剩余: 21秒
```

---

### 2. ResourceManager - 资源管理

```python
from video_generator.optimization import ResourceManager

# 创建资源管理器
resource_mgr = ResourceManager()

# 检查GPU显存
gpu_info = resource_mgr.check_gpu_memory()
print(gpu_info['message'])
# 输出: GPU显存: 4096MB / 8192MB (50.0%)

# 判断是否需要清理
if resource_mgr.should_cleanup_gpu():
    print("⚠️ GPU显存使用过高，需要清理")
    resource_mgr.cleanup_gpu_memory(log_callback=print)

# 卸载Whisper模型释放GPU
whisper_model = resource_mgr.unload_whisper_model(
    whisper_model_ref=whisper_model,
    log_callback=print
)

# 智能垃圾回收(每处理50个项目执行一次GC)
for i in range(100):
    # ... 处理项目 ...
    resource_mgr.smart_gc(processed_count=i+1, interval=50)
```

---

### 3. BatchImageLoader - 批量图片加载

```python
from video_generator.optimization import BatchImageLoader

# 创建批量加载器(每批20张)
loader = BatchImageLoader(batch_size=20)

# 预加载一批图片
image_paths = [
    "images/shot_001.png",
    "images/shot_002.png",
    # ... 更多图片
]
loaded_images = loader.preload_batch(image_paths)

# 从缓存获取图片
img = loader.get_image("images/shot_001.png")

# 查看缓存大小
print(f"缓存中有 {loader.get_cache_size()} 张图片")

# 清空缓存释放内存
loader.clear_cache()
```

---

### 4. VideoRendererOptimizer - 渲染优化

```python
from video_generator.optimization import VideoRendererOptimizer

# 创建渲染优化器
renderer_opt = VideoRendererOptimizer()

# 检测GPU编码器
encoder_info = renderer_opt.check_gpu_encoder()
if encoder_info['available']:
    print(f"✅ 使用GPU编码: {encoder_info['description']}")
    print(f"   编码器: {encoder_info['encoder']}")
    print(f"   预设: {encoder_info['preset']}")
else:
    print(f"🖥️ 使用CPU编码: {encoder_info['description']}")

# 预渲染动画帧到缓存
frames = renderer_opt.cache_animation_frame(
    clip=my_clip,
    duration=3.0,
    frame_count=30
)

# 清空动画缓存
renderer_opt.clear_animation_cache()
```

---

## 🎯 实际应用场景

### 场景1: 图像生成流水线优化

```python
from video_generator.optimization import ProgressManager, ResourceManager

# 初始化
progress = ProgressManager(total_items=len(shots_data))
resource_mgr = ResourceManager()

# 生成图像
for idx, shot in enumerate(shots_data):
    # 生成单张图片...
    
    # 更新进度
    progress.update(increment=1)
    
    # 每10张图片显示一次详细进度
    if (idx + 1) % 10 == 0:
        stats = progress.get_stats()
        log(f"📊 进度: {stats['progress']:.1f}% | "
            f"速度: {stats['throughput']:.2f}张/秒 | "
            f"预计剩余: {stats['eta_formatted']}")
    
    # 智能GC
    resource_mgr.smart_gc(processed_count=idx+1, interval=10)

# 完成后清理GPU
resource_mgr.cleanup_gpu_memory(log_callback=log)
```

### 场景2: 视频渲染优化

```python
from video_generator.optimization import (
    ProgressManager, ResourceManager, 
    BatchImageLoader, VideoRendererOptimizer
)

# 初始化优化器
progress = ProgressManager(total_items=len(shots_data))
resource_mgr = ResourceManager()
image_loader = BatchImageLoader(batch_size=20)
renderer_opt = VideoRendererOptimizer()

# 步骤1: 检测GPU编码器
encoder_info = renderer_opt.check_gpu_encoder()
log(f"🎬 编码器: {encoder_info['description']}")

# 步骤2: 批量预加载图片
all_image_paths = [
    os.path.join(images_dir, shot['image_file'])
    for shot in shots_data
]
loaded_images = image_loader.preload_batch(all_image_paths)

# 步骤3: 创建视频片段
clips = []
for idx, shot in enumerate(shots_data):
    img_path = os.path.join(images_dir, shot['image_file'])
    
    # 从缓存获取图片(避免重复IO)
    img = image_loader.get_image(img_path)
    if img is None:
        # 如果缓存未命中,直接加载
        from PIL import Image
        with Image.open(img_path) as orig_img:
            img = orig_img.copy()
    
    # 创建clip...
    
    # 更新进度
    progress.update(increment=1)
    
    # 定期清理不需要的缓存
    if idx % 20 == 0:
        # 保留最近20张图片在缓存中
        pass

# 步骤4: 渲染前检查GPU显存
gpu_info = resource_mgr.check_gpu_memory()
if gpu_info['used_percent'] > 0.85:
    log("⚠️ GPU显存不足，清理缓存")
    resource_mgr.cleanup_gpu_memory(log_callback=log)
    image_loader.clear_cache()

# 步骤5: 渲染视频
if encoder_info['available']:
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec=encoder_info['encoder'],
        preset=encoder_info['preset'],
        logger=None
    )
else:
    final_clip.write_videofile(
        output_path,
        fps=30,
        codec='libx264',
        preset='veryfast',
        logger=None
    )

# 清理资源
image_loader.clear_cache()
renderer_opt.clear_animation_cache()
resource_mgr.cleanup_gpu_memory(log_callback=log)
```

---

## ⚙️ 配置参数

所有优化参数可在 `Config` 类中调整:

```python
# video_generator/config.py
class Config:
    # 图像生成优化
    IMAGE_PREFETCH_QUEUE_SIZE = 16  # 预取队列大小
    IMAGE_SAVE_POOL_SIZE = 4        # 图片保存线程池
    
    # 视频渲染优化
    VIDEO_CLIP_BATCH_SIZE = 20      # 视频片段批量加载大小
    GPU_MEMORY_THRESHOLD = 0.85     # GPU显存阈值
    
    # 进度管理
    PROGRESS_ETA_WINDOW = 10        # ETA滑动窗口大小
```

---

## 📊 性能提升预期

| 优化项 | 优化前 | 优化后 | 提升 |
|--------|--------|--------|------|
| 进度反馈 | 无ETA | 实时ETA预测 | 用户体验↑ |
| GPU管理 | 手动清理 | 自动监控清理 | 稳定性↑ |
| 图片加载 | 逐个读取 | 批量预加载 | IO减少50% |
| 渲染检测 | 失败才fallback | 提前检测编码器 | 可靠性↑ |
| 内存管理 | 频繁GC | 智能间隔GC | CPU占用↓ |

---

## 🔧 故障排查

### Q1: ETA显示"计算中..."
**原因**: 样本不足或速度为0  
**解决**: 等待至少2个进度更新样本

### Q2: GPU显存清理无效
**原因**: 其他进程占用GPU  
**解决**: 关闭其他GPU应用或重启程序

### Q3: 图片缓存占用过多内存
**原因**: 缓存未清理  
**解决**: 调用 `loader.clear_cache()`

### Q4: 进度更新卡顿UI
**原因**: 更新频率过高  
**解决**: 每10-20个项目更新一次UI

---

## 📝 注意事项

1. **线程安全**: 所有类都使用了锁保护,可安全用于多线程
2. **内存管理**: 定期清理缓存避免内存泄漏
3. **GPU资源**: 任务完成后务必清理GPU显存
4. **进度精度**: ETA基于滑动窗口,初期可能不准确

---

**最后更新**: 2026-04-25
