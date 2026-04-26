# 视频生成优化 - 快速参考

## 🚀 快速开始

### 导入模块
```python
from video_generator.optimization import (
    ProgressManager,      # 进度管理 + ETA预测
    ResourceManager,      # GPU/内存管理
    BatchImageLoader,     # 批量图片加载
    VideoRendererOptimizer # 渲染优化
)
```

---

## 📊 ProgressManager - 进度管理

```python
# 创建(100个项目)
progress = ProgressManager(total_items=100)

# 更新进度
progress.update(increment=1)        # 增量方式
progress.update(completed=50)       # 直接设置

# 获取统计
stats = progress.get_stats()
print(f"进度: {stats['progress']:.1f}%")
print(f"速度: {stats['throughput']:.2f}项/秒")
print(f"剩余: {stats['eta_formatted']}")

# 重置
progress.reset(total_items=200)
```

---

## 💾 ResourceManager - 资源管理

```python
resource_mgr = ResourceManager()

# 检查GPU
gpu_info = resource_mgr.check_gpu_memory()
print(gpu_info['message'])  # "GPU显存: 4096MB / 8192MB (50.0%)"

# 清理GPU
if resource_mgr.should_cleanup_gpu():
    resource_mgr.cleanup_gpu_memory(log_callback=print)

# 卸载Whisper
whisper_model = resource_mgr.unload_whisper_model(model, log_callback=print)

# 智能GC(每50个项目)
for i in range(100):
    resource_mgr.smart_gc(processed_count=i+1, interval=50)
```

---

## 🖼️ BatchImageLoader - 批量加载

```python
loader = BatchImageLoader(batch_size=20)

# 预加载
paths = ["img1.png", "img2.png", ...]
loaded = loader.preload_batch(paths)

# 从缓存获取
img = loader.get_image("img1.png")

# 清空缓存
loader.clear_cache()
```

---

## 🎬 VideoRendererOptimizer - 渲染优化

```python
renderer_opt = VideoRendererOptimizer()

# 检测编码器
encoder = renderer_opt.check_gpu_encoder()
print(f"编码器: {encoder['encoder']}")  # h264_nvenc
print(f"预设: {encoder['preset']}")      # p4

# 使用GPU渲染
clip.write_videofile(
    output,
    codec=encoder['encoder'],
    preset=encoder['preset']
)
```

---

## 🔧 配置参数

在 `video_generator/config.py` 中调整:

```python
class Config:
    IMAGE_PREFETCH_QUEUE_SIZE = 16   # 预取队列大小
    IMAGE_SAVE_POOL_SIZE = 4         # 图片保存线程池
    VIDEO_CLIP_BATCH_SIZE = 20       # 批量加载大小
    GPU_MEMORY_THRESHOLD = 0.85      # GPU阈值
    PROGRESS_ETA_WINDOW = 10         # ETA窗口大小
```

---

## 📈 典型应用场景

### 图像生成流水线
```python
progress = ProgressManager(total_items=len(shots))
resource_mgr = ResourceManager()

for idx, shot in enumerate(shots):
    # 生成图片...
    
    progress.update(increment=1)
    
    if (idx + 1) % 10 == 0:
        stats = progress.get_stats()
        log(f"进度: {stats['progress']:.1f}% | "
            f"速度: {stats['throughput']:.2f}张/秒 | "
            f"剩余: {stats['eta_formatted']}")
    
    resource_mgr.smart_gc(idx+1, 10)

resource_mgr.cleanup_gpu_memory(log_callback=log)
```

### 视频渲染流程
```python
progress = ProgressManager(total_items=len(shots))
resource_mgr = ResourceManager()
loader = BatchImageLoader(batch_size=20)
renderer_opt = VideoRendererOptimizer()

# 检测编码器
encoder = renderer_opt.check_gpu_encoder()
log(f"编码器: {encoder['description']}")

# 批量加载图片
paths = [os.path.join(dir, s['file']) for s in shots]
loader.preload_batch(paths)

# 创建片段
for idx, shot in enumerate(shots):
    img = loader.get_image(path)
    # 创建clip...
    progress.update(increment=1)

# 检查GPU
if resource_mgr.should_cleanup_gpu():
    resource_mgr.cleanup_gpu_memory(log_callback=log)

# 渲染
clip.write_videofile(output, codec=encoder['encoder'], preset=encoder['preset'])

# 清理
loader.clear_cache()
resource_mgr.cleanup_gpu_memory(log_callback=log)
```

---

## ⚠️ 注意事项

1. **线程安全**: 所有类都支持多线程
2. **定期清理**: 任务完成后调用 `clear_cache()` 和 `cleanup_gpu_memory()`
3. **ETA精度**: 需要至少2个样本才开始计算
4. **GPU阈值**: 默认85%,可根据显存大小调整

---

## 📚 完整文档

- [OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md) - 详细报告
- [OPTIMIZATION_GUIDE.md](OPTIMIZATION_GUIDE.md) - 使用指南
- [test_optimization.py](test_optimization.py) - 测试脚本

---

**最后更新**: 2026-04-25
