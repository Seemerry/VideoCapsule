# 视频信息提取器

综合了抖音、Bilibili 链接解析和本地视频处理的音频转文本工具。输入一个视频链接或本地视频文件，即可获取完整的视频信息和文本转录结果，并自动生成包含摘要的 Markdown 笔记。

## 功能特性

- **多平台支持**：自动识别抖音、Bilibili 链接和本地视频文件
  - 抖音：短链接、完整链接、分享文本
  - Bilibili：BV号链接、b23.tv 短链接、纯BV号
  - 本地视频：支持 mp4、avi、mov、mkv、flv、wmv、webm、m4v 格式

- **链接解析模块**：解析视频链接，提取视频信息
  - 视频下载链接
  - 音频下载链接
  - 视频封面图片链接
  - 视频标题、描述和标签（自动提取 #标签）
  - 作者信息（昵称、ID）
  - 统计数据（点赞、评论、分享、收藏）
  - 视频详情（时长、ID、发布时间）
  - 背景音乐信息

- **文本提取模块**：从音频URL提取文本
  - 支持豆包录音识别2.0模型（默认）
  - 支持阿里云Paraformer-v2模型
  - 可选说话人识别功能
  - 自动处理受限音频URL（Bilibili/抖音平台的音频链接需特殊请求头才能下载）
  - 输出完整文本和时间分段信息（毫秒级精度）

- **智能文稿处理**：使用 DeepSeek API 优化转录文本
  - 自动生成内容摘要，快速了解视频核心内容
  - 对原文进行排版优化，提升可读性
  - 重点语句和关键信息自动加粗
  - 保留原文完整性，不做任何删改

- **关键帧截取**：自动识别文稿重点，截取对应视频画面
  - 基于 AI 识别转录文本中的关键节点（转折点、核心论点、关键事件）
  - 使用 ffmpeg 从视频中截取对应时间点的帧图片
  - 图片自动插入到 Markdown 笔记的对应段落，实现图文并茂
  - 最多截取 8 个关键帧，均匀分布在整个视频时间线上
  - 支持远程视频（自动下载）和本地视频

- **思维导图生成**：自动将转录文本整理为思维导图
  - 使用 DeepSeek API 提取核心主题和关键分支，生成层级 Markdown 结构
  - 使用 Markmap.js + Playwright 渲染为 PNG 图片，嵌入笔记
  - 保留 Markdown 源文件（`mindmap.md`），可手动编辑后重新生成
  - 提供独立脚本 `regenerate_mindmap.py`，编辑后一键更新图片

- **Markdown笔记生成**：自动生成结构化的笔记文件
  - 基于 `视频笔记模板.md` 模板生成
  - 包含视频封面、资源链接、基础信息、统计数据
  - 智能摘要 + 格式化原文 + 关键帧图片 + 思维导图
  - 文件名格式：`{视频标题}_笔记.md`
  - 关键帧图片保存在 `{视频标题}_assets/` 文件夹中

## 项目结构

```
DouyinVideoExtractor/
├── modules/                    # 核心模块
│   ├── __init__.py
│   ├── douyin_parser.py        # 抖音链接解析（Playwright）
│   ├── bilibili_parser.py      # Bilibili链接解析（HTTP API）
│   ├── local_parser.py         # 本地视频解析（ffprobe）
│   ├── oss_uploader.py         # OSS文件上传模块
│   ├── text_extractor.py       # 文本提取模块（音频转文本）
│   ├── text_formatter.py       # 文本格式化模块（DeepSeek API）
│   ├── frame_extractor.py      # 关键帧提取模块（ffmpeg）
│   ├── mindmap_generator.py    # 思维导图生成模块（Markmap.js + Playwright）
│   └── md_generator.py         # Markdown笔记生成模块
├── config.json                 # 配置文件（需自行填写，已gitignore）
├── config.example.json         # 配置文件示例
├── 视频笔记模板.md              # Markdown笔记模板
├── main.py                     # 主入口
├── regenerate_mindmap.py       # 思维导图重新生成脚本
├── requirements.txt            # Python依赖
├── CLAUDE.md                   # 开发者指南
└── README.md                   # 本文档
```

**代码特点**：
- 独立项目：无外部依赖，所有功能自包含
- 模块化：链接解析和文本提取独立
- 容错性：文本提取失败不影响视频信息返回
- 灵活输出：支持控制台输出或保存到文件

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt
playwright install chromium

# 2. 配置 API 密钥
cp config.example.json config.json
# 编辑 config.json，填入你的 API 密钥

# 3. 运行测试（抖音）
python main.py "https://v.douyin.com/OQsck5Woryw/" -o test.json

# 4. 运行测试（Bilibili）
python main.py "https://www.bilibili.com/video/BV1MbFXz5Esa/" -o test.json

# 5. 查看结果
cat test.json | python -c "import sys, json; d=json.load(sys.stdin); print('标题:', d['content']['title']); print('标签:', d['content'].get('tag', '无'))"
```

## 配置

复制 `config.example.json` 为 `config.json`，并填入您的API密钥：

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "dashscope": {
    "api_key": "your_dashscope_api_key_here"
  },
  "doubao": {
    "app_id": "your_doubao_app_id_here",
    "access_token": "your_doubao_access_token_here",
    "resource_id": "volc.seedasr.auc",
    "submit_endpoint": "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit",
    "query_endpoint": "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
  },
  "deepseek": {
    "api_key": "your_deepseek_api_key_here",
    "api_base": "https://api.deepseek.com",
    "model": "deepseek-reasoner"
  },
  "oss": {
    "access_key_id": "your_oss_access_key_id_here",
    "access_key_secret": "your_oss_access_key_secret_here",
    "bucket_name": "your_bucket_name",
    "endpoint": "oss-cn-shenzhen.aliyuncs.com"
  }
}
```

**配置说明**：

| 配置项 | 用途 | 必需 |
|--------|------|------|
| `dashscope` | Paraformer 转录模型 | 使用 Paraformer 时需要 |
| `doubao` | 豆包转录模型（默认） | 是 |
| `deepseek` | 文本格式化和摘要生成 | 使用 `--format-text` 时需要 |
| `oss` | 本地视频转录及受限音频URL转录 | 处理本地视频或受限平台URL时需要 |

**OSS 配置说明**（本地视频转录及受限URL转录需要）：
- 需要阿里云 OSS Bucket
- AccessKey 需要有 `PutObject`、`GetObject`、`DeleteObject` 权限
- 转录完成后会自动删除临时文件

**注意**：`config.json` 包含敏感信息，已被 `.gitignore` 忽略，请勿提交到版本控制系统。

## 使用方法

### 基本用法

```bash
# 抖音链接（自动检测平台）
python main.py "https://v.douyin.com/xxxxx/" -o result.json

# Bilibili链接（自动检测平台）
python main.py "https://www.bilibili.com/video/BVxxxxx/" -o result.json

# Bilibili短链接
python main.py "https://b23.tv/xxxxx" -o result.json

# 本地视频文件（自动检测）
python main.py "D:\path\to\video.mp4" -o result.json

# 仅解析链接/文件，不进行转录
python main.py "URL" --no-transcribe -o result.json
```

**输出文件**：使用 `-o` 参数时，会同时生成两个文件：
- `result.json` - 完整的视频信息（JSON格式）
- `视频标题_笔记.md` - 可读性强的Markdown笔记
- `视频标题_assets/` - 资源文件夹（使用 `--format-text` 时生成）
  - `frame_01_00m29s.jpg` 等 - 关键帧图片
  - `mindmap.md` - 思维导图源文件（可编辑）
  - `mindmap.png` - 思维导图图片

**重要提示**：
- Windows 控制台中文会显示为乱码，**建议使用 `-o` 参数保存到文件**
- 程序会自动检测输入类型（抖音/Bilibili/本地文件）
- 本地视频转录需要配置 OSS（用于临时上传）
- 使用 `--no-transcribe` 可跳过转录，仅提取视频信息

### 高级选项

```bash
# 启用智能文稿处理（摘要 + 格式化 + 关键帧截取 + 思维导图）
python main.py "URL" --format-text -o result.json

# 使用Paraformer模型进行转录
python main.py "URL" --model paraformer -o result.json

# 启用说话人识别
python main.py "URL" --speaker-info -o result.json

# 指定配置文件路径
python main.py "URL" --config /path/to/config.json -o result.json
```

### 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `url` | 视频链接、分享文本或本地文件路径（可选） | `"https://v.douyin.com/xxxxx/"` 或 `"D:\video.mp4"` |
| `-m, --model` | 转录模型选择 | `paraformer` 或 `doubao`（默认） |
| `-s, --speaker-info` | 启用说话人识别 | 添加此标志即可 |
| `-c, --config` | 配置文件路径 | `./config.json`（默认） |
| `-o, --output` | 输出文件路径 | `result.json` |
| `--no-transcribe` | 仅解析链接/文件，不进行转录 | 添加此标志即可 |
| `--format-text` | 使用 DeepSeek API 优化文稿（摘要 + 格式化 + 关键帧 + 思维导图） | 添加此标志即可 |

## 输出格式

程序输出JSON格式的完整信息（抖音和Bilibili输出格式一致）：

```json
{
  "status": {
    "success": true
  },
  "urls": {
    "video_url": "https://...",
    "audio_url": "https://...",
    "cover_url": "https://...",
    "final_url": "https://..."
  },
  "content": {
    "title": "视频标题",
    "desc": "视频描述",
    "tag": "标签1 、标签2"
  },
  "author_info": {
    "author": "作者昵称",
    "author_id": "作者ID"
  },
  "statistics": {
    "like_count": 1000,
    "comment_count": 100,
    "share_count": 50,
    "collect_count": 20
  },
  "video_detail": {
    "duration": 60000,
    "video_id": "视频ID",
    "create_time": 1234567890
  },
  "music_info": {
    "music": "背景音乐标题"
  },
  "transcription": {
    "url": "https://...",
    "text": "完整的转录文本",
    "segments": [
      {
        "text": "第一句话",
        "start": 0,
        "end": 2000
      }
    ]
  }
}
```

### 字段说明

| 分类 | 字段 | 说明 |
|------|------|------|
| `status` | `success` | 是否成功 |
| `status` | `error` | 错误信息（如果失败） |
| `urls` | `video_url` | 视频下载链接 |
| `urls` | `audio_url` | 音频下载链接 |
| `urls` | `cover_url` | 封面图片链接 |
| `urls` | `final_url` | 最终页面链接 |
| `content` | `title` | 视频标题 |
| `content` | `desc` | 视频描述 |
| `content` | `tag` | 标签（多个用顿号分隔） |
| `author_info` | `author` | 作者昵称 |
| `author_info` | `author_id` | 作者ID |
| `statistics` | `like_count` | 点赞数 |
| `statistics` | `comment_count` | 评论数 |
| `statistics` | `share_count` | 分享数 |
| `statistics` | `collect_count` | 收藏数 |
| `video_detail` | `duration` | 时长（毫秒） |
| `video_detail` | `video_id` | 视频ID |
| `video_detail` | `create_time` | 发布时间戳 |
| `music_info` | `music` | 背景音乐信息 |
| `transcription` | `text` | 转录的完整文本 |
| `transcription` | `segments` | 分段信息（包含文本、开始时间、结束时间） |

## 模块说明

### 抖音解析模块 (modules/douyin_parser.py)

封装了抖音链接解析功能，使用 Playwright 浏览器自动化技术。

```python
from modules import DouyinLinkParser

parser = DouyinLinkParser()

# 从分享文本中提取URL
url = parser.extract_url("8.76 复制打开抖音... https://v.douyin.com/xxxxx/")

# 解析视频信息
result = parser.parse("https://v.douyin.com/xxxxx/")
# result 包含: status, urls, content, author_info, statistics, video_detail, music_info

# 提取标题和标签
title, tag = parser.parse_title_and_tag("视频标题 #标签1 #标签2")
# title: "视频标题"
# tag: "标签1 、标签2"
```

### Bilibili解析模块 (modules/bilibili_parser.py)

封装了 Bilibili 链接解析功能，使用 HTTP API 直接调用。

```python
from modules import BilibiliLinkParser

parser = BilibiliLinkParser()

# 从分享文本中提取URL
url = parser.extract_url("【视频标题】 https://www.bilibili.com/video/BVxxxxx/")

# 解析视频信息
result = parser.parse("https://www.bilibili.com/video/BVxxxxx/")
# result 包含: status, urls, content, author_info, statistics, video_detail, music_info

# 支持短链接
result = parser.parse("https://b23.tv/xxxxx")
```

### 本地视频解析模块 (modules/local_parser.py)

封装了本地视频文件解析功能，使用 ffprobe 获取视频信息。

```python
from modules import LocalVideoParser

parser = LocalVideoParser()

# 检查是否是本地视频文件
if parser.is_local_file("D:\\video.mp4"):
    # 解析视频信息
    result = parser.parse("D:\\video.mp4")
    # result 包含: status, urls, content, author_info, statistics, video_detail, music_info
    # 注意: statistics 字段为 null（本地文件无统计数据）
    # 注意: cover_url 等字段为 null（本地文件无封面等信息），笔记生成时自动显示为"无"
```

### 文本提取模块 (modules/text_extractor.py)

封装了音频转文本功能，支持 URL、本地文件和受限平台音频URL。

```python
from modules import TextExtractor

extractor = TextExtractor()  # 默认从 ./config.json 读取配置

# 从 URL 提取文本
result = extractor.extract(
    "https://example.com/audio.mp3",
    model='doubao',           # 或 'paraformer'
    enable_speaker_info=False # 启用说话人识别
)

# 从本地文件提取文本（需要配置 OSS）
result = extractor.extract(
    "D:\\video.mp4",
    model='doubao'
)

# 受限平台URL也能自动处理（需要配置 OSS）
# Bilibili/抖音的音频URL需要特殊请求头才能下载，
# 程序会自动检测并通过 下载→上传OSS→转录 的方式处理
result = extractor.extract(
    "https://upos-sz-mirrorali.bilivideo.com/...",
    model='doubao'
)

# result 包含:
# - url: 音频URL（本地文件/受限URL会先上传到OSS）
# - text: 完整文本
# - segments: 分段信息 [{"text": "...", "start": 0, "end": 2000}]
```

### Markdown笔记生成模块 (modules/md_generator.py)

封装了Markdown笔记生成功能，基于模板文件生成可读性强的笔记。

```python
from modules import MarkdownGenerator

generator = MarkdownGenerator()  # 默认使用 ./视频笔记模板.md

# 从视频信息生成Markdown笔记（不格式化）
md_path = generator.generate(video_info, output_dir='./output')

# 启用智能文稿处理（摘要 + 格式化原文 + 关键帧截取 + 思维导图）
md_path = generator.generate(
    video_info,
    output_dir='./output',
    format_text=True,      # 启用 DeepSeek API 处理
    config_path='./config.json'
)
# 返回生成的MD文件路径

# video_info 结构与 JSON 输出格式一致
# 生成的笔记包含:
# - 视频标题和封面图片
# - 音视频资源链接表格
# - 基础信息表格（标题、标签、作者、时长等）
# - 统计数据表格（点赞、评论、分享、收藏）
# - 智能摘要（format_text=True 时）
# - 格式化转录文稿（format_text=True 时）
# - 关键帧图片插入到文稿对应位置（format_text=True 时）
# - 思维导图（format_text=True 时）
```

### 文本格式化模块 (modules/text_formatter.py)

封装了使用 DeepSeek API 进行文本格式化和摘要生成的功能。

```python
from modules import TextFormatter

formatter = TextFormatter()  # 默认从 ./config.json 读取配置

# 仅生成摘要
summary = formatter.generate_summary(raw_text, title="视频标题")

# 仅格式化原文
formatted = formatter.format_text(raw_text, title="视频标题")

# 同时生成摘要和格式化原文
result = formatter.process_text(raw_text, title="视频标题")
# result = {
#     'summary': '生成的摘要内容...',
#     'formatted_text': '格式化后的原文...'
# }

# 生成思维导图 Markdown 结构
mindmap_md = formatter.generate_mindmap_markdown(raw_text, title="视频标题")
# mindmap_md: "# 主题\n## 观点一\n### 细节\n..."
```

### 思维导图生成模块 (modules/mindmap_generator.py)

封装了使用 Markmap.js + Playwright 将 Markdown 渲染为思维导图 PNG 的功能。

```python
from modules import MindMapGenerator

generator = MindMapGenerator()

# 生成思维导图图片和源文件
result = generator.generate(mindmap_md, output_dir='./output', title='视频标题')
# result = {
#     'image_path': '绝对路径/mindmap.png',
#     'image_relative_path': '视频标题_assets/mindmap.png',
#     'source_path': '绝对路径/mindmap.md',
#     'source_relative_path': '视频标题_assets/mindmap.md',
# }

# 从编辑后的源文件重新生成 PNG
png_path = MindMapGenerator.regenerate('./output/视频标题_assets/mindmap.md')
```

**独立重新生成脚本**：编辑 `mindmap.md` 后，可运行脚本更新图片：

```bash
python regenerate_mindmap.py ./output/视频标题_assets/mindmap.md
```

## 技术实现

| 功能 | 实现方式 | 说明 |
|------|---------|------|
| 抖音解析 | Playwright | 浏览器自动化，捕获 API 响应 |
| Bilibili 解析 | HTTP API | 直接调用公开 API，速度快 |
| 本地文件解析 | ffprobe | 获取视频时长等元数据，转录需上传 OSS |
| 音频转录 | 豆包 / Paraformer | 支持两种语音识别模型，自动处理受限平台URL |
| 文本格式化 | DeepSeek API | 摘要生成和原文排版优化 |
| 关键帧截取 | DeepSeek API + ffmpeg | AI 识别关键节点 + ffmpeg 截帧 |
| 思维导图 | DeepSeek API + Markmap.js + Playwright | AI 生成结构化 Markdown + 渲染为 PNG |

## 注意事项

1. **Windows 控制台乱码问题**
   - 直接输出到控制台时，中文会显示为乱码（GBK编码限制）
   - **解决方案**：使用 `-o` 参数保存到文件
   - 文件中的数据是正确的 UTF-8 编码

2. **抖音反爬虫检测**
   - 频繁访问或通过 stdin 输入可能被重定向到推荐页
   - **解决方案**：直接传递 URL 参数，避免频繁访问同一链接

3. **API 密钥安全**
   - `config.json` 包含敏感信息，已在 `.gitignore` 中
   - 请勿将 `config.json` 提交到版本控制系统

4. **转录费用和时间**
   - DashScope 和豆包 API 调用可能产生费用
   - 长音频（10分钟以上）可能需要较长的转录时间

5. **DeepSeek API 费用**
   - 使用 `--format-text` 参数会调用 DeepSeek API
   - 费用按 token 计费，摘要、格式化、关键节点识别和思维导图各调用一次 API（共 4 次）
   - 建议仅在需要时启用此功能

6. **关键帧截取**
   - 需要安装 ffmpeg 并加入 PATH
   - 远程视频会先下载到临时文件再截帧，截帧完成后自动清理
   - 帧图片保存在 `{视频标题}_assets/` 文件夹中
   - 如果截帧失败（ffmpeg 不可用、下载失败等），仍会正常生成笔记，只是没有图片

7. **思维导图**
   - 需要安装 Playwright Chromium 浏览器（`playwright install chromium`）
   - 渲染时需要联网加载 CDN 资源（Markmap.js、D3.js）
   - 生成的 `mindmap.md` 源文件可手动编辑，编辑后运行 `python regenerate_mindmap.py` 重新生成 PNG
   - 如果思维导图生成失败（Playwright 不可用、CDN 加载超时等），笔记仍会正常生成，只是没有思维导图

8. **Bilibili 音视频格式**
   - Bilibili 使用 DASH 格式，视频和音频分离（.m4s 文件）
   - `video_url` 和 `audio_url` 分别对应独立的流

9. **本地视频转录**
   - 需要配置阿里云 OSS（用于临时上传文件）
   - 需要安装 ffmpeg（包含 ffprobe）以获取视频时长
   - 转录完成后会自动删除 OSS 上的临时文件
   - 本地视频无封面、统计数据等信息，笔记中对应字段显示为"无"或"无数据"

10. **受限音频URL处理**
   - Bilibili 和抖音的音频URL需要特殊请求头（Referer 等）才能下载
   - 转录服务无法直接访问这些受限URL，程序会自动检测并处理
   - 处理流程：下载音频到本地临时文件 → 上传到 OSS → 转录 → 自动清理临时文件和 OSS 文件
   - 需要配置阿里云 OSS（同本地视频转录）

## 常见问题

### Q: 为什么输出显示乱码？
**A**: Windows 控制台编码问题。使用 `python main.py "URL" -o result.json` 保存到文件即可。

### Q: 为什么没有提取到 tag 字段？
**A**: tag 字段只在视频标题包含 `#标签` 时才会出现。如果视频没有标签，该字段不存在。Bilibili 视频通常没有标签。

### Q: 文本提取失败怎么办？
**A**: 检查：
1. `config.json` 中的 API 密钥是否正确
2. 网络连接是否正常
3. 音频 URL 是否有效
即使失败，视频信息仍会返回到 `transcription_error` 字段中。

### Q: 使用 --format-text 时提示"未配置 DeepSeek API Key"？
**A**: 需要在 `config.json` 中添加 DeepSeek 配置：
```json
{
  "deepseek": {
    "api_key": "your_deepseek_api_key_here",
    "api_base": "https://api.deepseek.com",
    "model": "deepseek-reasoner"
  }
}
```

### Q: Bilibili 视频的 video_url 是 m4s 格式？
**A**: Bilibili 使用 DASH 流媒体格式，视频和音频是分离的。如果需要合并格式，可以使用 FFmpeg 工具合并 video.m4s 和 audio.m4s。

### Q: 本地视频转录失败怎么办？
**A**: 检查：
1. `config.json` 中的 OSS 配置是否正确
2. OSS Bucket 权限是否允许 PutObject/GetObject/DeleteObject
3. 是否安装了 ffmpeg（包含 ffprobe）
4. 本地视频文件格式是否支持（mp4/avi/mov/mkv/flv/wmv/webm/m4v）

### Q: 如何修改思维导图内容？
**A**: 编辑 `{视频标题}_assets/mindmap.md` 文件（标准 Markdown 层级标题格式），然后运行：
```bash
python regenerate_mindmap.py {视频标题}_assets/mindmap.md
```
PNG 会原地覆盖更新，笔记中的引用自动生效。

## 许可证

[MIT License](LICENSE)
