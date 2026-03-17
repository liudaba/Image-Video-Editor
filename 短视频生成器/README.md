# 短视频生成器

一个基于 Python 的短视频生成工具，支持图片转视频、音频合成等功能。

## 项目结构

```
短视频生成器/
├── My-Video Generator.py  # 主程序
├── config.json           # 配置文件
├── 启动.bat             # Windows启动脚本
├── 启动.vbs             # Windows无窗口启动脚本
├── models/              # 模型文件目录（需单独下载）
└── src/                 # 源代码目录
```

## 环境要求

- Python 3.11+
- 依赖包：见 requirements.txt

## 模型文件下载

由于模型文件较大，未包含在Git仓库中，请从以下地址下载：

| 模型文件 | 说明 | 下载地址 |
|---------|------|---------|
| `latentsync_unet.pt` | LatentSync 口型同步模型 | [下载链接] |
| `tiny.pt` | Whisper 语音识别模型 | [下载链接] |

下载后将模型文件放入 `models/` 目录即可。

## 使用方法

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 下载模型文件并放入 `models/` 目录

3. 运行程序：
   - 方式一：双击 `启动.bat`
   - 方式二：双击 `启动.vbs`（无控制台窗口）
   - 方式三：命令行运行 `python "My-Video Generator.py"`

## 功能特性

- 图片转视频
- 音频合成
- 口型同步
- 字幕生成

## 许可证

MIT License
