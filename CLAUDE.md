# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-platform video information extractor that combines link parsing and audio transcription. Given a Douyin URL, Bilibili URL, or local video file, it extracts comprehensive video metadata, transcribes the audio content using speech-to-text APIs, and generates Markdown notes with AI-powered summaries.

**Note**: This project is fully self-contained with no external project dependencies.

## Architecture

### Data Flow

```
Input URL/File → Platform Detection → Parser (Douyin/Bilibili/Local) → Video Info → TextExtractor → Transcription
                                                                                    ↓
                                                                            Complete JSON Output
                                                                                    ↓
                                                                    TextFormatter (optional, --format-text)
                                                                        ↓ process_text() → summary + formatted_text
                                                                        ↓ identify_key_moments() → FrameExtractor.extract_frames()
                                                                        ↓ generate_mindmap_markdown() → MindMapGenerator.generate()
                                                                                    ↓
                                                                            MarkdownGenerator → MD Note File + assets/
```

### Core Components

**main.py** - Entry point and orchestrator
- `detect_platform(url)` - Detects platform from URL or local file path (douyin/bilibili/local/unknown)
- `VideoExtractor.extract()` - Main extraction pipeline
  1. Detects platform and selects appropriate parser
  2. Parses URL via `DouyinLinkParser`, `BilibiliLinkParser`, or `LocalVideoParser`
  3. Extracts audio URL from video info
  4. Transcribes audio via `TextExtractor`
  5. Post-processes title/tags
  6. Generates Markdown note via `MarkdownGenerator` (when `-o` flag is used)
     - If `--format-text` is enabled, calls `TextFormatter.process_text()` for summary + formatting
     - If `--format-text` is enabled and segments exist, calls `TextFormatter.identify_key_moments()` + `FrameExtractor.extract_frames()` to insert keyframe images into the transcript
     - If `--format-text` is enabled, calls `TextFormatter.generate_mindmap_markdown()` + `MindMapGenerator.generate()` to create mindmap PNG and embed in note
- Tag extraction happens AFTER video parsing to separate `#hashtags` from title
- MD note generation only happens when output file is specified (`-o` flag)

**modules/douyin_parser.py** - Douyin video metadata extraction
- Self-contained Playwright-based Douyin parser
- Uses `_DouyinParserCore` class for all parsing logic
- `DouyinLinkParser` class - Public interface
- Key methods:
  - `extract_url()` - Extracts clean URL from share text
  - `parse()` - Returns hierarchical JSON with video info
  - `parse_title_and_tag()` - Separates hashtags from title using regex
- Captures API responses via Playwright route handling
- Extracts: video URL, audio URL, cover, title, author, statistics, etc.

**modules/bilibili_parser.py** - Bilibili video metadata extraction
- HTTP API-based parser (no browser automation needed)
- `BilibiliLinkParser` class - Same interface as DouyinLinkParser
- Key methods:
  - `extract_url()` - Extracts clean URL from share text
  - `parse()` - Returns hierarchical JSON with video info
  - `parse_title_and_tag()` - Handles title parsing
- API endpoints:
  - Video info: `api.bilibili.com/x/web-interface/view?bvid={bvid}`
  - Play URL: `api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}`
- Supports: BV links, b23.tv short links, plain BV numbers
- Note: Bilibili uses DASH format (.m4s files) with separate video/audio streams

**modules/local_parser.py** - Local video file metadata extraction
- Self-contained local file parser using ffprobe
- `LocalVideoParser` class - Same interface as other parsers
- Supported formats: mp4, avi, mov, mkv, flv, wmv, webm, m4v
- Key methods:
  - `extract_url()` - Returns the file path if valid
  - `parse()` - Returns hierarchical JSON with video info
  - `parse_title_and_tag()` - Handles title parsing
  - `is_local_file()` - Checks if path is a local video file
- Extracts: title (from filename), duration (via ffprobe), file path
- Statistics fields (like_count, etc.) are set to `null`

**modules/oss_uploader.py** - OSS file upload for local video transcription
- `OSSUploader` class - Handles file upload to Alibaba Cloud OSS
- Key methods:
  - `upload_file()` - Uploads local file and returns signed URL
  - `delete_file()` - Deletes file from OSS
  - `is_local_file()` - Checks if path is a local file
- Generates temporary signed URLs (default 1 hour expiry)
- Auto-cleanup after transcription completes

**modules/text_extractor.py** - Audio transcription
- Self-contained audio-to-text functionality
- Supports two models: `doubao` (default) and `paraformer`
- Supports both URLs and local files (local files are uploaded to OSS first)
- Key architecture:
  - `_get_oss_uploader()` - Lazy-loads OSS uploader for local files
  - `_transcribe_audio_doubao()` - Two-phase: submit → poll (60 retries, 2s interval)
  - `_transcribe_audio_paraformer()` - Uses DashScope SDK
  - `_format_result()` - Delegates to model-specific formatters
  - `_add_speaker_label()` - Auto-merges consecutive segments from same speaker
- Local file workflow: upload to OSS → transcribe → delete from OSS

**modules/md_generator.py** - Markdown note generation
- Self-contained Markdown generator based on template file
- `MarkdownGenerator` class - Reads template and fills in video info
- Key methods:
  - `_load_template()` - Loads `视频笔记模板.md` and converts Unicode quotes to ASCII
  - `generate()` - Generates MD file from video info dict
    - Parameters: `video_info`, `output_dir`, `format_text`, `config_path`
    - If `format_text=True`, calls `TextFormatter.process_text()` before generating
    - If `format_text=True` and segments exist, calls `_insert_frames()` for keyframe images
    - If `format_text=True`, calls `TextFormatter.generate_mindmap_markdown()` + `MindMapGenerator.generate()` for mindmap
  - `_format_duration()` - Converts milliseconds to `mm:ss` or `hh:mm:ss`
  - `_format_timestamp()` - Converts Unix timestamp to `YYYY-MM-DD HH:mm`
  - `_sanitize_filename()` - Removes illegal characters from title for filename
  - `_insert_frames(formatter, formatted_text, segments, video_url, title, output_dir)` - Orchestrates keyframe insertion:
    1. Calls `formatter.identify_key_moments()` to select key segments
    2. Creates `FrameExtractor` and extracts frame images
    3. Locates insertion points via `_find_insertion_point()`
    4. Inserts frame Markdown in reverse order to avoid position drift
    5. Entire flow is try/except wrapped — failures return original text
  - `_find_insertion_point(text, segment_text)` - Locates segment text in formatted output, backtracks to nearest paragraph boundary (`\n\n`)
- Template placeholders: `"title"`, `"cover_url"`, `"video_url"`, `"audio_url"`, `"tag"`, `"author"`, `"author_id"`, `"duration"`, `"video_id"`, `"create_time"`, `"like_count"`, `"comment_count"`, `"share_count"`, `"collect_count"`, `"summary"`, `"text"`, `"mindmap"`, `time` (current time)
- Output filename: `{title}_笔记.md`
- Handles null values gracefully (shows "无数据", "未知", or "无摘要")

**modules/text_formatter.py** - Text formatting and summary generation
- Self-contained text processor using DeepSeek API
- `TextFormatter` class - Handles API calls for text optimization
- Configuration: Reads from `config.json` → `deepseek` section
- Key methods:
  - `_call_api()` - Generic API call handler with error handling
  - `generate_summary()` - Generates 200-400 char summary with key points bolded
  - `format_text()` - Formats raw transcription with paragraphs and emphasis
  - `process_text()` - Combined: returns `{'summary': str, 'formatted_text': str}`
  - `generate_mindmap_markdown(raw_text, title=None)` - Generates hierarchical Markdown structure for mindmap
    - Calls DeepSeek API to extract core topics and key branches from transcription
    - Output format: `#` headings (up to 4 levels) mixed with `-` list items
    - Each node text kept concise (≤15 chars)
    - Returns Markdown string, or None on failure
  - `identify_key_moments(formatted_text, segments, max_moments=8)` - Identifies key moments in transcript
    - Sends numbered segment list to DeepSeek API
    - Asks API to select up to N key moments (turning points, core arguments, key events)
    - Returns `[{'text': str, 'timestamp_ms': int, 'segment_index': int}]`
  - `_parse_key_moments_response(response, segments)` - Robust JSON parsing with markdown fence removal and regex fallback
- API details:
  - Endpoint: `https://api.deepseek.com/chat/completions`
  - Model: `deepseek-reasoner` (configurable)
  - Timeout: 120 seconds
- Summary rules: Extract core themes, bold key entities, no title prefix
- Format rules: Never modify content, add paragraphs, bold key statements

**modules/frame_extractor.py** - Video keyframe extraction
- Self-contained frame extractor using ffmpeg
- `FrameExtractor` class - Downloads video (if remote) and extracts frames at given timestamps
- Key methods:
  - `extract_frames(video_source, timestamps_ms, output_dir, title)` - Main entry point
    1. Detects video source type (local file or remote URL)
    2. Downloads remote video to temp file if needed (platform-aware headers)
    3. Calls ffmpeg for each timestamp to extract a single frame
    4. Saves frames to `{sanitized_title}_assets/` subfolder
    5. Returns `[{'timestamp_ms': int, 'image_path': str, 'relative_path': str, 'label': str}]`
    6. Cleans up temp download files
  - `_download_video(url, platform)` - Downloads remote video
    - Bilibili: includes Referer header, saves as `.m4s`
    - Douyin/other: standard HTTP GET, saves as `.mp4`
  - `_extract_single_frame(video_path, timestamp_ms, output_path)` - ffmpeg call
    - Command: `ffmpeg -ss {seconds} -i {video_path} -vframes 1 -q:v 2 -y {output_path}`
    - `-ss` before `-i` for fast seek
  - `_detect_platform(url)` - Detects platform from URL patterns
  - `_format_timestamp_label(timestamp_ms)` - Generates `mm:ss` label
  - `_frame_filename(index, timestamp_ms)` - Generates `frame_01_00m29s.jpg` filename
  - `_sanitize_dirname(title)` - Cleans illegal characters for folder name
- Requirements: ffmpeg must be installed and available in PATH
- Graceful degradation: all failures return empty list, never raises

**modules/mindmap_generator.py** - Mindmap rendering (Markmap.js + Playwright)
- Self-contained mindmap generator that converts Markdown to PNG
- `MindMapGenerator` class - Renders hierarchical Markdown into a visual mindmap image
- Key methods:
  - `generate(mindmap_md, output_dir, title)` - Main entry point
    1. Creates `{sanitized_title}_assets/` subfolder
    2. Saves Markdown source to `mindmap.md` (for user editing)
    3. Calls `_render_to_png()` to produce `mindmap.png`
    4. Returns `{'image_path', 'image_relative_path', 'source_path', 'source_relative_path'}`
  - `regenerate(source_path)` - Static method for re-rendering from edited source file
    - Reads `.md` file, renders PNG to same directory, returns PNG path
    - Used by `regenerate_mindmap.py` standalone script
  - `_render_to_png(mindmap_md, output_path)` - Core rendering logic
    1. Escapes Markdown as JSON string for JS embedding
    2. Generates temp HTML with inline Markmap.js (CDN: d3@7, markmap-view, markmap-lib)
    3. Opens HTML with Playwright sync API (Chromium, viewport 1600x900)
    4. Waits for `[data-ready="true"]` attribute (set after 2s setTimeout)
    5. Screenshots the SVG element (`#markmap`)
    6. Cleans up temp HTML
  - `_escape_for_js(text)` - Uses `json.dumps()` for safe JS string literal
  - `_sanitize_dirname(title)` - Same pattern as FrameExtractor
- HTML template uses `__MINDMAP_CONTENT__` placeholder (not `{}` braces, to avoid conflict with JS syntax)
- Uses Playwright **sync** API (unlike douyin_parser which uses async)
- Graceful degradation: all failures return None, never raises

**regenerate_mindmap.py** - Standalone mindmap regeneration script
- Usage: `python regenerate_mindmap.py <mindmap.md path>`
- Calls `MindMapGenerator.regenerate()` to re-render PNG from edited source
- PNG is written to same directory as source file, overwriting previous version
- Since note MD references relative path, no note file edits needed after regeneration

## Common Commands

### Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### Configuration
- Copy `config.example.json` to `config.json`
- Add API keys for DashScope and Doubao (required for transcription)
- Add OSS configuration (required for local video transcription)
- Add DeepSeek configuration (required for `--format-text` feature)

### Running
```bash
# Douyin links (auto-detected)
python main.py "https://v.douyin.com/xxxxx/" -o result.json

# Bilibili links (auto-detected)
python main.py "https://www.bilibili.com/video/BVxxxxx/" -o result.json

# Bilibili short links
python main.py "https://b23.tv/xxxxx" -o result.json

# Local video files (auto-detected)
python main.py "D:\path\to\video.mp4" -o result.json

# Parse only (no transcription)
python main.py "URL_OR_FILE" --no-transcribe -o result.json

# With AI-powered text formatting (summary + formatted transcript + mindmap)
python main.py "URL_OR_FILE" --format-text -o result.json

# With speaker detection
python main.py "URL_OR_FILE" --speaker-info -o result.json

# Use Paraformer model instead of Doubao
python main.py "URL_OR_FILE" --model paraformer -o result.json
```

### Testing Changes
```bash
# Quick test with Douyin URL
python main.py "https://v.douyin.com/OQsck5Woryw/" -o test.json

# Quick test with Bilibili URL
python main.py "https://www.bilibili.com/video/BV1MbFXz5Esa/" -o test.json

# Quick test with text formatting (summary + formatted transcript + mindmap)
python main.py "https://www.bilibili.com/video/BV1MbFXz5Esa/" --format-text -o test.json

# Quick test with local video (parse only)
python main.py "D:\path\to\video.mp4" --no-transcribe -o test.json

# Quick test with local video (with transcription, requires OSS)
python main.py "D:\path\to\video.mp4" -o test.json

# Verify output
cat test.json | python -c "import sys, json; d=json.load(sys.stdin); print('Success:', d['status']['success']); print('Platform:', 'Bilibili' if 'BV' in d.get('video_detail', {}).get('video_id', '') else ('Local' if 'http' not in d.get('urls', {}).get('video_url', '') else 'Douyin'))"
```

## Key Implementation Details

### Platform Detection (main.py)
```python
def detect_platform(url: str) -> str:
    # First check if it's a local file
    if os.path.isfile(url):
        return 'local'

    url_lower = url.lower()
    if any(domain in url_lower for domain in ['douyin.com', 'iesdouyin.com']):
        return 'douyin'
    elif any(domain in url_lower for domain in ['bilibili.com', 'b23.tv']) or re.search(r'BV[a-zA-Z0-9]{10,}', url):
        return 'bilibili'
    return 'unknown'
```

### Tag Extraction Logic
Tags are extracted AFTER video parsing:
1. Get `title` from `content.title` (contains hashtags)
2. Call `parse_title_and_tag()` which uses regex to find `#(\S+)` pattern
3. Returns `(cleaned_title, tags_string)` where tags are joined by ` 、`
4. Updates `result['content']['title']` and adds `result['content']['tag']`

### Audio URL Fallback
```python
audio_url = video_info['urls'].get('audio_url') or video_info['urls'].get('video_url')
```
Tries `audio_url` first, falls back to `video_url` if missing.

### Parser Architecture

**Douyin Parser:**
- Uses Playwright async API for browser automation
- Captures API responses from `/aweme/v1/web/aweme/detail` endpoints
- Debug mode available via `DOUYIN_DEBUG=1` environment variable

**Bilibili Parser:**
- Uses HTTP requests with proper headers (User-Agent, Referer)
- Resolves b23.tv short links via redirect
- Extracts audio from DASH format (`data.dash.audio[0].baseUrl`)

### Unified Output Structure
Both parsers output the same hierarchical JSON structure with categories:
`status`, `urls`, `content`, `author_info`, `statistics`, `video_detail`, `music_info`

All fields are optional - check existence before accessing.

### Transcription Error Handling
- If transcription fails, `video_info['transcription']` is set to `None`
- Error stored in `video_info['status']['transcription_error']`
- Video info is still returned even if transcription fails

### Windows Console Encoding Issue
Direct console output shows Chinese as garbled text (GBK encoding issue).
**Always use `-o` flag to save results to file for proper UTF-8 display.**

## Output Structure

When using `-o` flag, two files are generated:
1. **JSON file** - Complete video info with transcription segments
2. **MD file** - Human-readable note with formatted tables and content
3. **Assets folder** (when `--format-text` is used) - `{title}_assets/` containing:
   - Keyframe images (`frame_01_00m29s.jpg`, etc.)
   - Mindmap source (`mindmap.md`) — editable Markdown, can be regenerated
   - Mindmap image (`mindmap.png`) — rendered by Markmap.js + Playwright

### JSON Structure
```json
{
  "status": {"success": bool, "error": str, "transcription_error": str},
  "urls": {"video_url": str, "audio_url": str, "cover_url": str, "final_url": str},
  "content": {"title": str, "desc": str, "tag": str},
  "author_info": {"author": str, "author_id": str},
  "statistics": {"like_count": int, "comment_count": int, "share_count": int, "collect_count": int},
  "video_detail": {"duration": int, "video_id": str, "create_time": int},
  "music_info": {"music": str},
  "transcription": {"url": str, "text": str, "segments": [{"text": str, "start": int, "end": int}]}
}
```

### MD Note Structure
Based on `视频笔记模板.md`, contains:
- Title heading with video title
- Cover image
- Resource links table (video/audio/cover URLs)
- Basic info table (title, tags, author, duration, video ID, create time)
- Statistics table (likes, comments, shares, collects) with timestamp
- Transcription section with:
  - **摘要** (Summary): AI-generated summary with bolded key points (when `--format-text` enabled)
  - **原文** (Original text): Formatted transcript with paragraphs and emphasis (when `--format-text` enabled)
  - **关键帧** (Keyframes): Frame images inserted at key moments in the transcript (when `--format-text` enabled)
    - Format: `![mm:ss](title_assets/frame_01_00m29s.jpg)` followed by `*mm:ss*`
    - Up to 8 keyframes, evenly distributed across the transcript
- 思维导图 (Mindmap) section with:
  - Mindmap PNG image: `![思维导图](title_assets/mindmap.png)` (when `--format-text` enabled)
  - Source file link: `> 源文件: [title_assets/mindmap.md](title_assets/mindmap.md)（可编辑后重新生成）`
  - When `--format-text` is not used or generation fails, the section is empty

Note: `transcription` is `null` if extraction fails or no audio URL is found.
When `--format-text` is not used, summary shows "无摘要" and text shows raw transcription.

## Bilibili-Specific Notes

### DASH Format
Bilibili uses DASH streaming format:
- Video and audio are separate `.m4s` files
- `video_url` and `audio_url` point to different streams
- To merge: use FFmpeg to combine `video.m4s` + `audio.m4s`

### API Headers
```python
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.bilibili.com',
}
```
Required for successful API calls.

## Local Video Notes

### OSS Configuration
Local video transcription requires Alibaba Cloud OSS:
- Bucket must allow PutObject, GetObject, DeleteObject operations
- Configuration in `config.json`:
```json
{
  "oss": {
    "access_key_id": "your_key",
    "access_key_secret": "your_secret",
    "bucket_name": "your_bucket",
    "endpoint": "oss-cn-shenzhen.aliyuncs.com"
  }
}
```

### ffprobe Requirement
- Required for extracting video duration from local files
- Install ffmpeg (includes ffprobe): `winget install ffmpeg` or download from https://ffmpeg.org
- If ffprobe is not available, duration will be `null`

### Local Video Output
- Statistics fields (like_count, comment_count, etc.) are always `null`
- Title is extracted from filename (cleaned of common patterns like "(Av123,P1)")
- `video_url` and `audio_url` both point to the local file path
- Transcription URL is the temporary OSS URL (valid for 2 hours, auto-deleted after use)

## DeepSeek Configuration

### Text Formatting Feature
The `--format-text` flag enables AI-powered text processing:
1. **Summary Generation** - Extracts core themes and key points
2. **Text Formatting** - Adds paragraphs and bold emphasis without modifying content
3. **Mindmap Generation** - Structures transcription into hierarchical Markdown, rendered as PNG

### Configuration
Add to `config.json`:
```json
{
  "deepseek": {
    "api_key": "your_deepseek_api_key",
    "api_base": "https://api.deepseek.com",
    "model": "deepseek-reasoner"
  }
}
```

### API Usage Notes
- Each `--format-text` call makes 4 API requests (summary + formatting + key moment identification + mindmap structure)
- Uses `deepseek-reasoner` model by default
- 120 second timeout per request
- If formatting fails, falls back to raw transcription text
- If key moment identification or frame extraction fails, falls back to formatted text without images
- If mindmap generation fails (API or Playwright), note is still generated without mindmap
