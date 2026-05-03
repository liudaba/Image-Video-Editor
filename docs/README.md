# 📁 Demo素材目录说明

## 当前状态
本目录用于存放GitHub README中使用的演示素材。

---

## 📸 截图文件 (screenshots/)

### 需要准备的截图:

1. **main_interface.png** - 主界面截图
   - 拍摄时机: 程序启动完成,显示"工具已就绪"
   - 要求: 清晰显示左侧控制面板和右侧日志区域
   
2. **advanced_settings.png** - 高级设置面板截图
   - 拍摄时机: 点击"高级设置"按钮后
   - 要求: 显示完整的设置选项,特别是云端模型配置

3. **generation_process.png** - 生成过程截图
   - 拍摄时机: 视频生成进度50%-70%时
   - 要求: 显示进度条和实时日志

### 截图规范:
- ✅ 分辨率: 至少1280x720,推荐1920x1080
- ✅ 格式: PNG
- ✅ 文件大小: < 2MB/张
- ✅ 文字清晰可读

### 临时替代方案:
如果暂时没有截图,可以使用以下占位图服务:
```markdown
![主界面](https://via.placeholder.com/1200x800?text=Main+Interface)
```

---

## 🎬 演示视频 (demo/)

### 需要准备的视频:

1. **universe_demo.mp4** - 宇宙科普案例
   - 输入: 3分钟宇宙起源音频
   - 风格: 电影感 + 赛博朋克
   - 输出: 45个场景,1080p

2. **audiobook_demo.mp4** - 有声书可视化案例
   - 输入: 5分钟小说片段
   - 风格: 吉卜力动画风
   - 输出: 72个场景

3. **history_demo.mp4** - 历史纪录片案例
   - 输入: 4分钟中国古代史讲解
   - 风格: 纪录片风 + 油画质感
   - 输出: 58个场景

### 视频规范:
- ✅ 分辨率: 1920x1080 (1080p)
- ✅ 格式: MP4 (H.264编码)
- ✅ 时长: 30-60秒/个
- ✅ 文件大小: < 50MB/个
- ✅ 添加字幕说明关键步骤

### 临时替代方案:
如果暂时没有演示视频,可以:
1. 使用GIF动图代替
2. 上传到B站/YouTube,嵌入链接
3. 使用在线视频托管服务

---

## 🚀 快速上手

### 第一步: 截取界面图片

1. 启动程序 `start.bat`
2. 等待初始化完成
3. 调整窗口大小到合适尺寸
4. 使用截图工具(PrtScn或Snipping Tool)
5. 保存到对应位置

**详细指南**: 查看 [截图制作指南](../docs/README_IMAGES.md)

### 第二步: 生成演示视频

1. 准备测试音频(1-5分钟)
2. 选择合适的风格和参数
3. 点击"生成视频"
4. 录制整个生成过程
5. 剪辑成60秒以内的演示视频

### 第三步: 更新README

将生成的素材路径填入README.md:

```markdown
![主界面](docs/screenshots/main_interface.png)
[▶️ 观看演示视频](docs/demo/universe_demo.mp4)
```

### 第四步: 提交到GitHub

```bash
git add docs/
git commit -m "Add demo screenshots and videos"
git push
```

---

## 💡 常见问题

### Q: 我没有合适的音频做演示怎么办?
A: 
- 使用TTS工具生成(如微软Azure TTS、讯飞语音)
- 从免费音频网站下载(CC0协议)
- 自己朗读一段文字

### Q: 视频文件太大怎么办?
A:
- 使用HandBrake压缩: https://handbrake.fr/
- 降低码率到5-8Mbps
- 缩短时长到30秒以内

### Q: 截图文字太小看不清?
A:
- 提高Windows显示缩放比例(125%或150%)
- 或者截取后放大并锐化

### Q: GitHub限制大文件上传?
A:
- 单个文件不能超过100MB
- 建议视频控制在50MB以内
- 或使用Git LFS管理大文件

---

## 📞 获取帮助

- 📖 查看详细指南: [docs/README_IMAGES.md](README_IMAGES.md)
- 💬 用户交流群: [加入QQ群](#)
- 🐛 报告问题: [GitHub Issues](https://github.com/liudaba/Image-Video-Editor/issues)

---

**准备好你的演示素材,让项目更有吸引力!** 🎨✨
