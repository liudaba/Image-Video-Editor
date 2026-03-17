# 短视频生成器

一个基于 Python 的短视频生成工具，支持图片转视频、音频合成、音画同步等功能。

## 项目简介

本项目是一个自动化短视频生成工具，主要功能包括：
- 根据音频自动生成视频分镜
- 图片转视频合成
- 精准的音画同步
- 支持多种视频过渡效果

## 项目结构

```
短视频生成器/
├── My-Video Generator.py  # 主程序（GUI界面）
├── config.json           # 配置文件（默认设置）
├── 启动.bat             # Windows启动脚本（带控制台）
├── 启动.vbs             # Windows无窗口启动脚本
├── .gitignore           # Git忽略文件配置
├── models/              # 模型文件目录（需单独下载）
│   ├── latentsync_unet.pt  # LatentSync口型同步模型（大文件，需单独下载）
│   └── tiny.pt             # Whisper语音识别模型（大文件，需单独下载）
├── src/                 # 源代码目录（如有）
└── output_project/      # 输出项目目录（自动生成）
```

## 环境要求

- **操作系统**: Windows 10/11
- **Python**: 3.11+
- **GPU**: 推荐NVIDIA显卡（支持CUDA加速）
- **内存**: 建议8GB以上

## 依赖安装

```bash
pip install -r requirements.txt
```

主要依赖包：
- moviepy - 视频处理
- whisper - 语音识别
- torch - 深度学习框架
- Pillow - 图像处理
- tkinter - GUI界面

## 模型文件下载

由于模型文件较大（共约800MB+），未包含在Git仓库中，请从以下地址下载：

| 模型文件 | 大小 | 说明 | 下载地址 |
|---------|------|------|---------|
| `latentsync_unet.pt` | ~700MB | LatentSync 口型同步模型 | [需自行下载] |
| `tiny.pt` | ~100MB | Whisper 语音识别模型 | [需自行下载] |

**下载后请将模型文件放入 `models/` 目录**

## 使用方法

### 方式一：双击运行（推荐）
- **带控制台**: 双击 `启动.bat`（可查看运行日志）
- **无控制台**: 双击 `启动.vbs`（仅显示GUI界面）

### 方式二：命令行运行
```bash
python "My-Video Generator.py"
```

### 基本操作流程

1. **导入音频**：点击"导入音频"按钮选择音频文件（支持mp3、wav等格式）
2. **生成分镜**：点击"一键生成分镜"按钮，程序会自动分析音频并生成分镜脚本
3. **生成图片**：程序会自动根据分镜生成对应的图片（或手动放置图片到images目录）
4. **生成视频**：点击"生成视频"按钮，程序会将图片和音频合成为视频

## 功能特性

### 核心功能
- ✅ **音频分析**：使用Whisper进行语音识别，自动生成时间戳
- ✅ **智能分镜**：根据音频内容自动生成分镜脚本
- ✅ **图片生成**：支持AI绘图生成图片（需配置Stable Diffusion API）
- ✅ **音画同步**：精准的时间轴控制，确保音画完全同步
- ✅ **视频合成**：支持多种过渡效果（硬切/淡入淡出/交叉溶解）

### 视频过渡模式

| 模式 | 说明 | 速度 |
|------|------|------|
| **硬切** | 直接切换，无过渡效果 | ⚡ 最快（推荐） |
| 淡入淡出 | 画面渐隐渐现 | 🐌 较慢 |
| 交叉溶解 | 两个画面叠加过渡 | 🐌 较慢 |

**默认使用"硬切"模式**，可在配置文件或界面中修改。

## 配置文件说明

`config.json` 包含以下配置项：

```json
{
  "model": "Stable Diffusion 1.5",      // 默认AI绘图模型
  "width": 512,                          // 默认图片宽度
  "height": 512,                         // 默认图片高度
  "api_type": "Stable Diffusion API",    // API类型
  "api_url": "http://localhost:7860",    // Stable Diffusion API地址
  "optimization_method": "脚本优化",      // 优化方法
  "ollama_model": "qwen3:4b",            // 默认LLM模型
  "llm_config_preset": "极速模式",        // LLM配置预设
  "whisper_model": "medium",             // Whisper模型大小
  "transition": "硬切",                   // 默认过渡模式
  "selected_styles": [],                 // 选中的风格
  "custom_theme": "战争",                 // 自定义主题
  "custom_visual_tone": "战场，城市废墟", // 视觉基调
  "prompt_type": "SD提示词",              // 提示词类型
  "animation": "无"                       // 动画效果
}
```

## 最近更新

### 2024-03-17
- 🔧 **修复音画同步问题**：使用 `concatenate_videoclips` 替代 `CompositeVideoClip`
- 🔧 **优化时间戳处理**：移除 `with_start`，只使用 `duration`
- 🔧 **增强调试日志**：添加详细的时间戳验证日志
- 🔧 **默认过渡模式**：改为"硬切"，提升生成速度

## 注意事项

1. **模型文件**：首次使用需要下载模型文件并放入 `models/` 目录
2. **音频格式**：支持 mp3、wav、ogg 等常见音频格式
3. **图片格式**：支持 png、jpg 格式
4. **输出格式**：生成 mp4 格式视频
5. **大文件**：模型文件较大，请勿上传到Git仓库（已配置.gitignore）

## 常见问题

### Q: 音画不同步怎么办？
A: 请确保：
1. 使用最新版本代码（已修复音画同步问题）
2. 分镜生成时音频分析完整
3. 图片数量与分镜数量一致

### Q: 生成视频很慢怎么办？
A: 建议：
1. 使用"硬切"过渡模式（默认）
2. 关闭动画效果
3. 使用GPU加速（如有NVIDIA显卡）

### Q: 如何更新代码？
```bash
git pull origin master
```

## 许可证

MIT License

---

**GitHub仓库**: https://github.com/liudaba/tupian-shipin-bianjiqi
