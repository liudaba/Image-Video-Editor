# 🚀 自动发布助手使用指南

## 📋 目录
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [发布流程详解](#发布流程详解)
- [常见问题](#常见问题)

---

## 快速开始

### 方式1: 交互式发布(推荐)

```bash
python release_helper.py
```

程序会逐步引导你完成所有步骤。

---

### 方式2: 命令行参数

```bash
# 指定版本号和更新说明
python release_helper.py --version "1.1.0" --message "修复音频导入bug"

# 仅指定版本号
python release_helper.py --version "1.1.0"

# 仅指定更新说明(自动递增版本号)
python release_helper.py --message "新增13种艺术风格"
```

---

## 使用方式

### 场景1: 小修复(修订版更新)

```bash
# 例如: v1.0.0 → v1.0.1
python release_helper.py --message "修复音频导入失败的问题"
```

**自动处理**:
- ✅ 版本号从 1.0.0 → 1.0.1
- ✅ 更新config.json
- ✅ 打包程序
- ✅ 发布到服务器

---

### 场景2: 新功能(次版本更新)

```bash
# 例如: v1.0.0 → v1.1.0
python release_helper.py --version "1.1.0" --message "新增云端AI服务支持"
```

**需要手动添加的更新项**:
- 新增云端LLM支持
- 新增云端ASR支持
- 新增云端图片生成
- 优化性能提升50%

---

### 场景3: 重大更新(主版本更新)

```bash
# 例如: v1.x.x → v2.0.0
python release_helper.py --version "2.0.0" --message "架构重构,全面升级"
```

**建议设置**:
- priority: `high` 或 `critical`
- force_update: `true`(如果需要强制更新)

---

## 发布流程详解

### 步骤1: 生成版本号 📋

```
📌 当前版本: v1.0.0
建议新版本号: v1.0.1
是否使用? (Y/n): Y
✅ 使用版本号: v1.0.1
```

**智能提示**:
- 自动读取当前版本
- 建议递增修订号
- 可手动输入任意版本

---

### 步骤2: 更新配置文件 📝

```
✅ 版本号已更新: 1.0.0 → 1.0.1
```

**修改文件**:
- `config.json` - version字段

---

### 步骤3: 打包程序 🔨

```
🚀 开始打包...
[PyInstaller输出...]
✅ 打包成功!
```

**执行脚本**:
- `build_exe.py`

**耗时**: 约5-10分钟(取决于项目大小)

---

### 步骤4: 编译安装器 📦

```
🔧 请使用Inno Setup手动编译:
   脚本位置: installer_setup.iss
   编译后生成的安装包请放在: releases/vX.X.X/

是否已完成编译? (y/n): y
```

**手动操作**:
1. 打开Inno Setup Compiler
2. 加载`installer_setup.iss`
3. 点击"编译"
4. 将生成的`.exe`文件放到指定目录

---

### 步骤5: 上传CDN ☁️

```
是否上传到CDN? (y/n, 默认n): n
⏭️  跳过CDN上传
```

**可选步骤**:
- 如果使用CDN,选择`y`
- 手动上传到阿里云OSS/腾讯云COS
- 输入CDN URL

---

### 步骤6: 发布版本 🚀

```
📋 发布信息预览:
{
  "version": "1.0.1",
  "release_date": "2026-05-03",
  "download_url": "./releases/v1.0.1/installer.exe",
  "file_size": 52428800,
  "changelog": ["修复音频导入bug"],
  "force_update": false,
  "priority": "normal"
}

确认发布? (y/n): y
✅ 发布成功: 版本 v1.0.1 发布成功
```

**调用API**:
- POST `/api/version/publish`
- 更新`versions.json`

---

### 步骤7: 通知用户 📢

```
是否在B站发布更新公告? (y/n): y
是否在知乎发布更新文章? (y/n): n
是否在用户群发布公告? (y/n): y

✅ 将在以下渠道发布通知: bilibili, qq_group
💡 提示: 可以使用预设的更新公告模板
```

**可选渠道**:
- B站动态/视频
- 知乎文章
- QQ/微信群
- 微信公众号

---

## 完整示例

### 示例1: 快速修复Bug

```bash
$ python release_helper.py --message "修复音频导入失败的问题"

🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
  短视频生成器 - 自动发布助手
🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉

============================================================
📋 步骤 1/7: 生成版本号
============================================================
📌 当前版本: v1.0.0

建议新版本号: v1.0.1
是否使用? (Y/n): Y
✅ 使用指定版本号: v1.0.1

============================================================
📝 步骤 2/7: 更新配置文件
============================================================
✅ 版本号已更新: 1.0.0 → 1.0.1

============================================================
🔨 步骤 3/7: 打包程序
============================================================
🚀 开始打包...
✅ 打包成功!

============================================================
📦 步骤 4/7: 编译安装器
============================================================
🔧 请使用Inno Setup手动编译:
   脚本位置: C:\...\installer_setup.iss
   
是否已完成编译? (y/n): y

============================================================
📝 收集更新日志
============================================================
✅ 已添加: 修复音频导入失败的问题

添加更新项(直接回车结束): 

============================================================
☁️  步骤 5/7: 上传到CDN
============================================================
是否上传到CDN? (y/n, 默认n): n
⏭️  跳过CDN上传

============================================================
🚀 步骤 6/7: 发布版本
============================================================
📋 发布信息预览:
{
  "version": "1.0.1",
  "release_date": "2026-05-03",
  "download_url": "./releases/v1.0.1/installer.exe",
  "file_size": 52428800,
  "changelog": ["修复音频导入失败的问题"],
  "force_update": false,
  "priority": "normal"
}

确认发布? (y/n): y
✅ 发布成功: 版本 v1.0.1 发布成功

============================================================
📢 步骤 7/7: 通知用户
============================================================
是否在B站发布更新公告? (y/n): n
是否在知乎发布更新文章? (y/n): n
是否在用户群发布公告? (y/n): n
⏭️  跳过用户通知

🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊
  ✅ 版本 v1.0.1 发布成功!
🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊🎊

📝 后续操作:
1. 检查更新服务器是否正常响应
2. 在社交媒体发布更新公告
3. 监控用户反馈和下载统计
```

---

## 高级用法

### 自定义优先级

编辑`release_helper.py`第6步的`publish_data`:

```python
publish_data = {
    "version": version,
    # ... 其他字段
    "priority": "high",  # 改为 high/critical
    "force_update": True  # 改为 True 强制更新
}
```

---

### 集成CDN上传

修改`step5_upload_to_cdn`方法:

```python
def step5_upload_to_cdn(self, version):
    """自动上传到阿里云OSS"""
    import oss2
    
    auth = oss2.Auth('AccessKey', 'SecretKey')
    bucket = oss2.Bucket(auth, 'oss-cn-hangzhou.aliyuncs.com', 'your-bucket')
    
    file_path = f"./dist/VideoGenerator_v{version}.exe"
    object_name = f"releases/v{version}/installer.exe"
    
    bucket.put_object_from_file(object_name, file_path)
    
    return f"https://your-bucket.oss-cn-hangzhou.aliyuncs.com/{object_name}"
```

---

### 自动生成更新公告

添加模板功能:

```python
def generate_announcement(self, version, changelog):
    """生成B站/知乎更新公告"""
    template = f"""
# 🎉 短视频生成器 v{version} 发布!

## ✨ 更新内容
"""
    for item in changelog:
        template += f"- {item}\n"
    
    template += """
## 📥 下载地址
[点击下载最新版本](你的下载链接)

## 💬 反馈渠道
- QQ群: xxxxxxxx
- GitHub Issues
"""
    return template
```

---

## 常见问题

### Q1: 打包失败怎么办?

**A**: 检查以下几点:
1. Python环境是否正确激活
2. 依赖是否完整(`pip install -r requirements.txt`)
3. 查看`build_exe.py`输出的错误信息
4. 清理缓存后重试(`rmdir /s /q build dist`)

---

### Q2: 如何回滚版本?

**A**: 
1. 修改`versions.json`,将`latest`指向上一个版本
2. 或者调用API重新发布旧版本:
```python
requests.post(url, json={
    "version": "1.0.0",  # 回滚到这个版本
    "rollback": True
})
```

---

### Q3: 可以跳过某些步骤吗?

**A**: 可以,修改`run`方法:
```python
def run(self, version=None, message=None):
    version = self.step1_generate_version(version)
    self.step2_update_config(version)
    # 注释掉不需要的步骤
    # if not self.step3_build_exe():
    #     return False
    changelog = self._collect_changelog(message)
    self.step6_publish_version(version, changelog)
```

---

### Q4: 如何测试发布流程?

**A**: 
1. 修改`version_api_url`为本地地址
2. 启动本地版本服务器:`python backend/version_server.py`
3. 运行发布助手测试完整流程

---

### Q5: 版本号规则是什么?

**A**: 语义化版本 `X.Y.Z`:
- **X**(主版本): 重大更新,可能不兼容
- **Y**(次版本): 新功能,向下兼容
- **Z**(修订版): Bug修复和小改进

**示例**:
- `1.0.0` → `1.0.1`: 修复bug
- `1.0.0` → `1.1.0`: 新增功能
- `1.0.0` → `2.0.0`: 架构重构

---

## 最佳实践

### ✅ 推荐做法

1. **频繁小更新** - 每周发布修订版
2. **详细更新日志** - 让用户清楚知道改了什么
3. **分级推送** - 紧急bug用critical,常规用normal
4. **多渠道通知** - B站+知乎+用户群同步
5. **备份旧版本** - 保留最近3个版本的安装包

---

### ❌ 避免做法

1. **不要跳版本号** - 保持连续性(1.0.0 → 1.0.1,不是1.0.0 → 1.2.0)
2. **不要频繁大更新** - 给用户适应时间
3. **不要忘记测试** - 发布前充分测试
4. **不要忽略反馈** - 及时响应用户问题

---

## 自动化扩展

### Git自动提交

在发布成功后自动提交代码:

```python
def auto_git_commit(self, version):
    """自动Git提交"""
    subprocess.run(['git', 'add', '.'])
    subprocess.run(['git', 'commit', '-m', f'Release v{version}'])
    subprocess.run(['git', 'tag', f'v{version}'])
    subprocess.run(['git', 'push', 'origin', 'main', '--tags'])
```

---

### CI/CD集成

在GitHub Actions中自动发布:

```yaml
name: Auto Release
on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run Release Helper
        run: python release_helper.py --version ${{ github.ref_name }}
```

---

## 技术支持

如遇到问题:
1. 检查Python版本(>=3.10)
2. 确认依赖已安装(`pip install requests`)
3. 查看控制台错误输出
4. 联系开发者获取帮助

---

**最后更新**: 2026-05-03  
**版本**: v1.0.0
