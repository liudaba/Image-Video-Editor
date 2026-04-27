# 启动时完全清空缓存功能 - 实现说明

**实施日期**: 2026-04-27  
**用户需求**: 每次启动程序时完全清空所有缓存，确保全新开始  
**状态**: ✅ **已实现**

---

## 🎯 用户需求背景

用户属于以下场景：
- ❌ 不需要快速迭代调试
- ❌ 不需要复用历史缓存
- ✅ **每次都是全新任务**
- ✅ **对数据新鲜度要求极高**
- ✅ **期望"重新启动 = 全新开始"**

---

## ✅ 实现方案

### 修改位置
`My-Video Generator.py` L1057 - [_initialize_systems](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L1057-L1090) 方法

### 添加的代码
```python
def _initialize_systems(self):
    """初始化各个系统"""
    # ========== 启动时清空所有全局缓存（确保全新开始）==========
    try:
        prompt_cache.clear()
        image_cache.clear()
        self.log("🗑️ 已清空全局缓存（prompt_cache + image_cache）")
    except Exception as e:
        self.log(f"⚠️ 清空全局缓存失败: {e}")
    
    # 通信系统
    self.event_system = {}
    self.state_manager = {}
    self.data_bus = {}
    
    # ... 其他初始化代码 ...
```

---

## 📊 清理范围详解

### ✅ 现在会清理的内容

#### 1. **全局提示词缓存** ([prompt_cache](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L121-L121))
```python
prompt_cache = SmartCache(max_size=Config.PROMPT_CACHE_SIZE, default_ttl=Config.PROMPT_CACHE_TTL)
# 存储内容: Ollama生成的提示词
# 清空效果: 下次生成分镜时会重新调用Ollama
```

#### 2. **全局图像缓存** ([image_cache](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L122-L122))
```python
image_cache = SmartCache(max_size=Config.IMAGE_CACHE_SIZE, default_ttl=Config.IMAGE_CACHE_TTL)
# 存储内容: SD生成的图像元数据
# 清空效果: 下次生成图片时会重新请求SD API
```

#### 3. **磁盘文件** (已有功能，保持不变)
```python
_cleanup_residual_files()
# 删除内容:
# - shots_data.json
# - images/*.png, *.jpg
# - *.mp4, *.avi
```

#### 4. **状态管理器** (已有功能，在任务开始时清理)
```python
_thorough_cleanup()
# 重置内容:
# - self.shots_data = []
# - state_manager['shots'] = {...}
# - 其他状态标志
```

---

### ❌ 不会清理的内容（设计决定）

#### 1. **Whisper模型**
```python
self.whisper_model  # 预加载的音频识别模型
```
**原因**: 
- 模型加载耗时较长（约5-10秒）
- 模型本身是静态的，不存在"过时"问题
- 保留模型可以加速首次音频转录

#### 2. **Ollama连接状态**
```python
OLLAMA_AVAILABLE  # 全局标志
```
**原因**:
- 这是服务可用性标志，不是缓存数据
- 重新检测需要额外时间

#### 3. **SD API连接状态**
```python
self.sd_api_status_var  # UI变量
```
**原因**:
- 这是UI状态，不影响数据处理
- 重新检测需要调用API

---

## 🎬 启动流程对比

### 修改前
```
程序启动
  ├─ _initialize_variables()
  │   └─ _cleanup_residual_files()  ← 只清理磁盘文件
  │
  ├─ _initialize_systems()
  │   ├─ 初始化event_system
  │   ├─ 初始化state_manager
  │   └─ 初始化cache_system
  │       └─ 启动缓存清理线程（TTL管理）
  │
  └─ 全局缓存保持原样 ❌
      ├─ prompt_cache: 可能包含旧提示词
      └─ image_cache: 可能包含旧图像元数据
```

### 修改后
```
程序启动
  ├─ _initialize_variables()
  │   └─ _cleanup_residual_files()  ← 清理磁盘文件
  │
  ├─ _initialize_systems()
  │   ├─ 清空全局缓存 ✅ 新增
  │   │   ├─ prompt_cache.clear()
  │   │   ├─ image_cache.clear()
  │   │   └─ 日志: "🗑️ 已清空全局缓存"
  │   │
  │   ├─ 初始化event_system
  │   ├─ 初始化state_manager
  │   └─ 初始化cache_system
  │
  └─ 所有缓存都是空的 ✅
      ├─ prompt_cache: 空
      └─ image_cache: 空
```

---

## 📝 预期日志输出

### 程序启动时的日志
```log
[2026-04-27 XX:XX:XX] ✅ 状态管理器初始化完成
[2026-04-27 XX:XX:XX] ✅ 事件系统初始化完成
[2026-04-27 XX:XX:XX] ✅ 缓存系统初始化完成
[2026-04-27 XX:XX:XX] 🗑️ 已清空全局缓存（prompt_cache + image_cache）  ← 新增
[2026-04-27 XX:XX:XX] ✅ 线程池初始化完成，最大工作线程数: 8
[2026-04-27 XX:XX:XX] 📋 日志区域初始化完成
[2026-04-27 XX:XX:XX] ✅ 已加载Ollama模型: gemma3:4b
[2026-04-27 XX:XX:XX] ✅ 已加载音频模型: medium
...
```

### 运行任务时的影响
```log
[2026-04-27 XX:XX:XX] 🎞️ 开始跑图生成视频...
[2026-04-27 XX:XX:XX] 📝 未检测到分镜脚本文件
[2026-04-27 XX:XX:XX] 💡 提示: 将从头开始生成分镜脚本、图片和视频
[2026-04-27 XX:XX:XX] 
[2026-04-27 XX:XX:XX] ============================================================
[2026-04-27 XX:XX:XX] 📋 阶段1/3: 准备分镜数据
[2026-04-27 XX:XX:XX] ============================================================
[2026-04-27 XX:XX:XX] 📝 未检测到分镜脚本，开始从头生成...
[2026-04-27 XX:XX:XX] 🔥 预热模型中...
[2026-04-27 XX:XX:XX]    开始为 59 个分镜生成提示词...  ← 一定会重新生成
[2026-04-27 XX:XX:XX]    开始生成 59 个提示词（4线程并行）...
```

**关键变化**:
- ✅ 每次都会重新生成提示词（不会复用缓存）
- ✅ 每次都会重新请求SD API（不会复用缓存）
- ✅ 确保使用最新的数据和参数

---

## ⚖️ 性能影响分析

### 首次任务耗时对比

#### 场景: 生成59个分镜的图片

**修改前（有缓存）**:
```
假设之前生成过相同内容的提示词：
- 提示词生成: 0秒（从缓存读取）
- SD图片生成: 8分钟（59张 × 8秒/张）
总耗时: 8分钟
```

**修改后（无缓存）**:
```
每次都重新生成：
- 提示词生成: 2分钟（59个 × 2秒/个）
- SD图片生成: 8分钟（59张 × 8秒/张）
总耗时: 10分钟

增加耗时: 2分钟
```

### 权衡分析

| 维度 | 修改前（保留缓存） | 修改后（清空缓存） |
|------|------------------|------------------|
| **首次任务速度** | ⭐⭐⭐⭐⭐ (快) | ⭐⭐⭐ (慢2分钟) |
| **数据新鲜度** | ⭐⭐⭐ (可能过期) | ⭐⭐⭐⭐⭐ (最新) |
| **调试灵活性** | ⭐⭐⭐⭐⭐ (高) | ⭐⭐ (低) |
| **可预测性** | ⭐⭐⭐ (不确定) | ⭐⭐⭐⭐⭐ (确定) |
| **符合预期** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**结论**: 
- 对于您的需求（每次都是全新任务），**修改后的方案更合适** ✅
- 虽然首次任务慢2分钟，但确保了数据的绝对新鲜度
- 符合"重新启动 = 全新开始"的预期

---

## 🔍 验证方法

### 测试步骤

#### 测试1: 验证启动时清空缓存
```bash
1. 运行程序
2. 观察日志，应该看到:
   "🗑️ 已清空全局缓存（prompt_cache + image_cache）"
3. 关闭程序
4. 再次运行程序
5. 再次看到相同的日志
```

#### 测试2: 验证不会复用缓存
```bash
1. 运行"跑图生成视频"任务
2. 记录提示词生成耗时（应该约2分钟）
3. 关闭程序
4. 重新启动程序
5. 再次运行相同任务
6. 提示词生成耗时应该仍然是约2分钟（不会更快）
   → 证明没有复用缓存 ✅
```

#### 测试3: 验证磁盘文件清理
```bash
1. 运行任务，生成shots_data.json和图片
2. 关闭程序
3. 检查output_project文件夹，应该是空的
4. 重新启动程序
5. output_project文件夹仍然应该是空的
```

---

## 💡 高级选项（可选）

如果您希望在某些情况下**临时保留缓存**，可以考虑以下扩展：

### 方案1: 命令行参数
```bash
# 默认行为：清空缓存
python "My-Video Generator.py"

# 保留缓存模式
python "My-Video Generator.py" --keep-cache
```

### 方案2: 配置文件选项
```json
{
  "startup_clear_cache": true  // 改为false则不清空
}
```

### 方案3: GUI设置
```
高级设置 → 启动时清空缓存 ☑️
```

**如需实现这些选项，请告诉我！**

---

## 📋 总结

### 实现的功能
✅ 程序启动时自动清空全局缓存  
✅ 包括 [prompt_cache](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L121-L121) 和 [image_cache](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L122-L122)  
✅ 添加明确的日志提示  
✅ 异常处理完善  

### 清理范围
- ✅ 全局提示词缓存
- ✅ 全局图像缓存
- ✅ 磁盘文件（已有功能）
- ❌ Whisper模型（保留以加速）
- ❌ 服务连接状态（保留以避免重复检测）

### 性能影响
- ⏱️ 首次任务增加约2分钟（提示词重新生成）
- ✅ 确保数据绝对新鲜
- ✅ 符合"全新开始"的预期

### 适用场景
- ✅ 每次都是全新任务
- ✅ 对数据新鲜度要求高
- ✅ 不频繁调试迭代
- ✅ 期望可预测的行为

---

**实施日期**: 2026-04-27  
**实施者**: AI Assistant  
**验证状态**: ✅ 语法检查通过  
**文档状态**: ✅ 完整详细

🎉 **功能已实现！现在每次启动程序都会完全清空所有缓存，确保全新开始！**

