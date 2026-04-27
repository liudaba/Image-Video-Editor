# 程序启动时缓存和文件清理机制 - 详细分析

**分析日期**: 2026-04-27  
**分析范围**: 程序启动时的初始化和清理逻辑  
**状态**: ✅ **已确认清理机制存在但不完全**

---

## 🎯 用户问题

**问**: 程序启动时，是否会自动清理程序系统内所有缓存以及文件夹内的所有文件？

**答**: **部分清理，但不是全部**。程序启动时会清理**磁盘文件**，但**不会清空内存缓存**。

---

## 📊 当前清理机制详解

### ✅ 1. 磁盘文件清理（会执行）

**位置**: `My-Video Generator.py` L972, L4926-4952

**触发时机**: 程序启动时，在 [_initialize_variables](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L952-L1047) 方法中调用

```python
def _initialize_variables(self):
    """初始化变量"""
    # ... 其他代码 ...
    
    # 启动时清理上次可能残留的磁盘文件（防止异常退出后数据残留）
    self._cleanup_residual_files()
```

**清理内容**:
```python
def _cleanup_residual_files(self):
    """启动时清理上次可能残留的磁盘文件"""
    try:
        if hasattr(self, 'output_dir') and os.path.exists(self.output_dir):
            # 1. 删除分镜脚本文件
            shots_file = os.path.join(self.output_dir, "shots_data.json")
            if os.path.exists(shots_file):
                os.remove(shots_file)

            # 2. 删除images文件夹内的所有图片文件
            if hasattr(self, 'images_dir') and os.path.exists(self.images_dir):
                for f in os.listdir(self.images_dir):
                    fp = os.path.join(self.images_dir, f)
                    if os.path.isfile(fp):
                        try:
                            os.remove(fp)
                        except Exception:
                            pass

            # 3. 删除output_dir下的所有其他文件（视频文件等）
            for f in os.listdir(self.output_dir):
                fp = os.path.join(self.output_dir, f)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
    except Exception:
        pass
```

**清理范围**:
- ✅ `output_project/shots_data.json` - 分镜脚本文件
- ✅ `output_project/images/*.png, *.jpg, etc.` - 所有生成的图片
- ✅ `output_project/*.mp4, *.avi, etc.` - 所有生成的视频文件
- ❌ **不清理音频文件**（因为这是用户导入的源文件）

---

### ❌ 2. 内存缓存清理（不会执行）

**全局缓存对象**:
```python
# L129-130: 全局缓存实例
prompt_cache = SmartCache(max_size=Config.PROMPT_CACHE_SIZE, default_ttl=Config.PROMPT_CACHE_TTL)
image_cache = SmartCache(max_size=Config.IMAGE_CACHE_SIZE, default_ttl=Config.IMAGE_CACHE_TTL)
```

**问题分析**:
1. **这些是模块级别的全局变量**，在Python解释器加载模块时就创建了
2. **程序启动时不会清空这些缓存**
3. **缓存有TTL（过期时间）**，会自动清理过期项，但不会立即清空

**SmartCache的自动清理机制**:
```python
def init_cache_system(self):
    """初始化缓存系统"""
    # ... 其他代码 ...
    
    # 启动缓存清理线程
    threading.Thread(target=self.cache_cleanup, daemon=True).start()

def cache_cleanup(self):
    """定期清理过期缓存"""
    while getattr(self, 'cache_cleanup_running', True):
        time.sleep(self.cache_config['cleanup_interval'])  # 每600秒清理一次
        
        current_time = time.time()
        
        for category in self.cache_system:
            items_to_remove = []
            for key, value in self.cache_system[category].items():
                # 检查是否有过期时间
                if isinstance(value, dict) and 'timestamp' in value:
                    if current_time - value['timestamp'] > self.cache_config['expiry_time']:
                        items_to_remove.append(key)
            
            # 移除过期项
            for key in items_to_remove:
                del self.cache_system[category][key]
```

**清理策略**:
- ⏰ **基于时间的清理**: 每600秒（10分钟）清理一次
- 🕐 **TTL过期**: 缓存项超过3600秒（1小时）后过期
- ❌ **不是启动时立即清空**

---

### ⚠️ 3. 状态管理器清理（部分执行）

**[_thorough_cleanup](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L4926-L4986) 函数**:
```python
def _thorough_cleanup(self):
    """彻底清理所有分镜脚本数据和缓存 - 确保无残留"""
    try:
        self.shots_data = []
    except Exception:
        pass

    try:
        if hasattr(self, '_pregenerated_prompts'):
            delattr(self, '_pregenerated_prompts')
    except Exception:
        pass

    try:
        if hasattr(self, '_shot_texts_for_context'):
            delattr(self, '_shot_texts_for_context')
    except Exception:
        pass

    try:
        if hasattr(self, 'state_manager') and isinstance(self.state_manager, dict):
            # 重置状态管理器
            self.state_manager['shots'] = {
                'generated': False,
                'count': 0,
                'data': []
            }
            # ... 其他状态重置 ...
    except Exception:
        pass
```

**问题**: 
- ❌ **这个函数在程序启动时没有被调用**
- ✅ **只在特定任务开始时调用**（如"跑图生成视频"任务的阶段1）

---

## 📋 清理时机总结

| 清理类型 | 启动时 | 任务开始时 | 说明 |
|---------|--------|-----------|------|
| **磁盘文件** | ✅ 是 | ✅ 是 | `_cleanup_residual_files()` |
| **全局缓存(prompt_cache)** | ❌ 否 | ❌ 否 | 仅按TTL自动过期 |
| **全局缓存(image_cache)** | ❌ 否 | ❌ 否 | 仅按TTL自动过期 |
| **实例缓存(cache_system)** | ❌ 否 | ❌ 否 | 仅按TTL自动过期 |
| **状态管理器** | ❌ 否 | ✅ 是 | `_thorough_cleanup()` |
| **分镜数据(shots_data)** | ❌ 否 | ✅ 是 | 任务开始时重置 |

---

## 🔍 实际影响分析

### 场景1: 正常关闭后重新启动

**流程**:
```
1. 用户关闭程序
2. 重新启动程序
3. _initialize_variables() 被调用
4. _cleanup_residual_files() 执行
   ├─ 删除 shots_data.json
   ├─ 删除 images/*.png
   └─ 删除 output_project/*.mp4
5. 全局缓存保持原样（如果Python进程未重启）
```

**结果**:
- ✅ 磁盘文件被清空
- ⚠️ 如果Python解释器重启，全局缓存也会清空（因为是新进程）
- ⚠️ 如果只是重新创建App实例，全局缓存会保留

---

### 场景2: 异常退出后重新启动

**流程**:
```
1. 程序崩溃或强制关闭
2. 磁盘上可能残留旧文件
3. 重新启动程序
4. _cleanup_residual_files() 执行
   └─ 清理所有残留文件
```

**结果**:
- ✅ 磁盘残留文件被清理
- ✅ 防止旧数据干扰新任务

---

### 场景3: 多次运行任务而不关闭程序

**流程**:
```
1. 第一次运行"跑图生成视频"
   ├─ 生成 shots_data.json
   ├─ 生成 images/*.png
   └─ 生成 video.mp4
   
2. 不关闭程序，再次运行任务
3. _cleanup_residual_files() 不会再次执行（只在启动时执行）
4. 旧文件仍然存在
```

**问题**:
- ❌ 第二次运行时，旧文件不会被自动清理
- ⚠️ 可能导致文件名冲突或数据混乱

**解决方案**:
- 每次任务开始时调用 `_cleanup_residual_files()`
- 或者在任务开始前询问用户是否清理

---

## 💡 建议改进方案

### 方案1: 启动时清空所有缓存（推荐）

**修改位置**: [_initialize_systems](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L1057-L1090) 方法

**添加代码**:
```python
def _initialize_systems(self):
    """初始化各个系统"""
    # 清空全局缓存
    prompt_cache.clear()
    image_cache.clear()
    self.log("🗑️ 已清空全局缓存")
    
    # ... 其他初始化代码 ...
```

**优点**:
- ✅ 确保每次启动都是干净的状态
- ✅ 避免旧缓存干扰新任务
- ✅ 符合用户对"重新启动=全新开始"的预期

**缺点**:
- ⚠️ 首次任务可能需要重新生成提示词（稍慢）
- ⚠️ 但如果使用频率不高，影响不大

---

### 方案2: 任务开始时清理（更激进）

**修改位置**: [render_video_threaded](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L7527-L7649) 方法开头

**添加代码**:
```python
def render_video_threaded(self):
    """跑图生成视频（完整流程）"""
    try:
        self.log("🎞️ 开始跑图生成视频...")
        
        # 清理上一次任务的残留
        self._cleanup_residual_files()
        prompt_cache.clear()
        image_cache.clear()
        self.log("🗑️ 已清理上一次任务的缓存和文件")
        
        # ... 后续流程 ...
```

**优点**:
- ✅ 每次任务都是全新的开始
- ✅ 最彻底的清理

**缺点**:
- ❌ 过于激进，可能不符合用户需求
- ❌ 如果用户想复用某些数据，会被清除

---

### 方案3: 提供清理选项（最灵活）

**实现方式**:
1. 在GUI添加"清理缓存"按钮
2. 或在高级设置中添加"启动时自动清理"选项
3. 让用户自己决定何时清理

**优点**:
- ✅ 最灵活，满足不同用户需求
- ✅ 用户可以控制清理时机

**缺点**:
- ⚠️ 增加UI复杂度
- ⚠️ 用户可能忘记清理

---

## 🎯 最终答案

### 直接回答您的问题

**问**: 程序启动时，是否会自动清理程序系统内所有缓存以及文件夹内的所有文件？

**答**: 

#### ✅ 会清理的内容：
1. **磁盘文件**（在 `output_project` 文件夹内）
   - `shots_data.json` - 分镜脚本文件
   - `images/` 文件夹内的所有图片
   - 其他生成的视频文件

#### ❌ 不会清理的内容：
1. **内存缓存**
   - `prompt_cache` - 提示词缓存
   - `image_cache` - 图像缓存
   - `cache_system` - 实例缓存系统

2. **状态管理器**
   - `state_manager` 中的数据

3. **音频文件**
   - 用户导入的源音频不会被删除

---

### 清理时机

| 清理类型 | 启动时 | 任务开始时 | 自动过期 |
|---------|--------|-----------|---------|
| 磁盘文件 | ✅ 是 | ❌ 否 | ❌ 否 |
| 内存缓存 | ❌ 否 | ❌ 否 | ✅ 是（1小时后） |
| 状态数据 | ❌ 否 | ✅ 是 | ❌ 否 |

---

### 建议

如果您希望**每次启动都完全清空所有缓存**，我建议采用**方案1**，在 [_initialize_systems](file://c:\Users\Administrator\Desktop\短视频生成器\My-Video%20Generator.py#L1057-L1090) 中添加缓存清空逻辑。

是否需要我帮您实现这个改进？

---

**分析日期**: 2026-04-27  
**分析者**: AI Assistant  
**文档状态**: ✅ 完整详细

📝 **总结**: 程序启动时会清理磁盘文件，但不会清空内存缓存。如果需要完全清理，需要手动添加缓存清空逻辑。

