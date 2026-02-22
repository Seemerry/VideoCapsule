# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-platform video information extractor that combines link parsing and audio transcription. Given a Douyin URL, Bilibili URL, Xiaohongshu URL, Kuaishou URL, or local video file, it extracts comprehensive video metadata, transcribes the audio content using speech-to-text APIs, and generates Markdown notes with AI-powered summaries.

**Note**: This project is fully self-contained with no external project dependencies.

## Architecture

### Data Flow

```
Input URL/File → Platform Detection → Parser (Douyin/Bilibili/Xiaohongshu/Kuaishou/Local) → Video Info → TextExtractor → Transcription
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
- `detect_platform(url)` - Detects platform from URL or local file path (douyin/bilibili/xiaohongshu/kuaishou/local/unknown)
- `VideoExtractor.extract()` - Main extraction pipeline
  1. Detects platform and selects appropriate parser
  2. Parses URL via `DouyinLinkParser`, `BilibiliLinkParser`, `XiaohongshuLinkParser`, or `LocalVideoParser`
  3. For image notes (`note_type == 'image'`), skips transcription and returns immediately
  4. Extracts audio URL from video info
  5. Transcribes audio via `TextExtractor`
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
- Captures API responses from `/aweme/v1/web/aweme/detail` and `/aweme/v1/web/aweme/detailinfo` endpoints via Playwright route handling
- Extracts: video URL, audio URL, cover, title, author, statistics, etc.

**modules/bilibili_parser.py** - Bilibili video metadata extraction
- HTTP API-based parser (no browser automation needed)
- Uses `_BilibiliParserCore` class for all parsing logic
- `BilibiliLinkParser` class - Public interface (same as DouyinLinkParser)
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
- Uses `_LocalParserCore` class for all parsing logic
- `LocalVideoParser` class - Public interface (same as other parsers)
- Supported formats: mp4, avi, mov, mkv, flv, wmv, webm, m4v
- Key methods:
  - `extract_url()` - Returns the file path if valid
  - `parse()` - Returns hierarchical JSON with video info
  - `parse_title_and_tag()` - Handles title parsing
  - `is_local_file()` - Checks if path is a local video file
- Extracts: title (from filename), duration (via ffprobe), file path
- Statistics fields (like_count, etc.) are set to `null`

**modules/xiaohongshu_parser.py** - Xiaohongshu (小红书) note metadata extraction
- HTTP-based parser (no browser automation needed — avoids Xiaohongshu's aggressive anti-bot detection)
- Uses `_XiaohongshuParserCore` class for all parsing logic
- `XiaohongshuLinkParser` class - Public interface (same as other parsers)
- Key methods:
  - `extract_url()` - Extracts clean URL from share text (supports `xhslink.com`, `xiaohongshu.com/explore/`, `xiaohongshu.com/discovery/item/`)
  - `_resolve_short_url()` - Resolves `xhslink.com` short links via HTTP redirect to get full URL with `xsec_token`
  - `parse()` - Fetches page HTML via HTTP, extracts `__INITIAL_STATE__` JSON, supplements with `og:*` meta tags
  - `_extract_initial_state()` - Parses SSR-rendered `window.__INITIAL_STATE__` from script tag (replaces JS `undefined` with JSON `null`)
  - `_extract_from_page_data()` - Extracts from `note.noteDetailMap[noteId].note` structure
  - `_extract_from_note_card()` - Shared extraction logic for note data (handles both camelCase and snake_case field names)
  - `_extract_from_html()` - Fallback extraction from `og:title`, `og:image`, `og:video` meta tags
  - `_parse_count()` - Handles string counts like `'1.2万'` → `12000`
  - `parse_title_and_tag()` - Handles `#标签[话题]#` format (Xiaohongshu-specific bracket+hash pattern)
- Supports two note types:
  - **Video notes** (`note_type: 'video'`): extracts video URL from `video.media.stream.h264[].masterUrl`, audio_url = video_url (Xiaohongshu videos have combined audio/video)
  - **Image notes** (`note_type: 'image'`): extracts image list from `imageList[].infoList[-1].url`, no video/audio URLs
- Cover URL: supplemented from `og:image` meta tag when SSR data lacks `infoList` for cover
- Debug mode available via `XHS_DEBUG=1` environment variable

**modules/kuaishou_parser.py** - Kuaishou (快手) video metadata extraction
- Playwright-based parser (browser automation needed for cookies)
- Uses `_KuaishouParserCore` class for all parsing logic
- `KuaishouLinkParser` class - Public interface (same as other parsers)
- Key methods:
  - `extract_url()` - Extracts clean URL from share text (supports `v.kuaishou.com`, `www.kuaishou.com/short-video/`, `www.kuaishou.com/f/`)
  - `_extract_photo_id(url)` - Extracts video ID (photoId) from URL path
  - `parse()` / `parse_async()` - Main parsing logic:
    1. Opens page with Playwright to get cookies and resolve short links
    2. Captures GraphQL API responses via route interception
    3. Falls back to active GraphQL API call via `page.evaluate(fetch(...))`
    4. Falls back to `__APOLLO_STATE__` extraction from page HTML
    5. Falls back to `og:*` meta tag extraction
  - `_fetch_via_graphql(page, photo_id, cookie_str)` - GraphQL API call using browser's fetch (auto-carries cookies)
  - `_extract_from_graphql_response(data)` - Extracts video info from GraphQL response
  - `_extract_apollo_state(html)` - Parses `window.__APOLLO_STATE__` from page HTML
  - `_extract_from_html(html, photo_id)` - Fallback extraction from `og:*` meta tags
  - `_parse_title_and_tag(title_text)` - Tag parsing (`#tag` format, same as Douyin)
  - `_parse_count(value)` - Handles string counts like `'1.2万'` → `12000`
- GraphQL endpoint: `POST https://www.kuaishou.com/graphql`, query: `visionVideoDetail`
- Video URL: combined MP4 stream (audio+video), `audio_url = video_url`
- Statistics: no dedicated share count, `share_count` uses `viewCount` (play count)
- Uses Playwright **async** API (same as douyin_parser)
- Debug mode available via `KUAISHOU_DEBUG=1` environment variable

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
- Supports URLs, local files, and restricted platform URLs (Bilibili/Douyin/Xiaohongshu)
- Key architecture:
  - `_get_oss_uploader()` - Lazy-loads OSS uploader for local files
  - `_RESTRICTED_PATTERNS` - Defines domain patterns and required HTTP headers for Bilibili/Douyin/Xiaohongshu audio URLs
  - `_detect_restricted_url(url)` - Checks if URL belongs to a restricted platform, returns required headers or None
  - `_download_to_temp(url, headers)` - Downloads restricted URL to local temp file using platform-specific headers
  - `_transcribe_audio_doubao()` - Two-phase: submit → poll (60 retries, 2s interval)
  - `_transcribe_audio_paraformer()` - Uses DashScope SDK
  - `_format_result()` - Delegates to model-specific formatters
  - `_add_speaker_label()` - Auto-merges consecutive segments from same speaker
- Three transcription paths in `extract()`:
  1. **Local file**: upload to OSS → transcribe → delete from OSS
  2. **Restricted remote URL** (Bilibili/Douyin/Xiaohongshu): download with platform headers → upload to OSS → transcribe → delete from OSS → delete temp file
  3. **Normal remote URL**: pass URL directly to transcription API

**modules/md_generator.py** - Markdown note generation
- Self-contained Markdown generator based on template file
- `MarkdownGenerator` class - Reads template and fills in video info
- Key methods:
  - `_load_template()` - Loads `视频笔记模板.md` and converts Unicode quotes to ASCII
  - `generate()` - Generates MD file from video info dict
    - Parameters: `video_info`, `output_dir`, `format_text`, `config_path`
    - Detects `note_type` from `content.note_type`: image notes insert image gallery in text section, skip keyframe extraction
    - If `format_text=True`, calls `TextFormatter.process_text()` before generating
    - If `format_text=True` and segments exist (video notes only), calls `_insert_frames()` for keyframe images
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
- Handles null values gracefully via `or` fallback pattern (e.g. `urls.get('cover_url') or '无'`), shows "无数据", "未知", "无", or "无摘要"
  - Note: must use `or` instead of `dict.get(key, default)` because fields may exist with `None` value (e.g. local videos have `cover_url: null`)

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
    - Douyin: includes Referer header (`https://www.douyin.com/`), saves as `.mp4`
    - Xiaohongshu: includes Referer header (`https://www.xiaohongshu.com`), saves as `.mp4`
    - Other: standard HTTP GET, saves as `.mp4`
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

# Xiaohongshu links (auto-detected, supports share text with URL)
python main.py "http://xhslink.com/o/xxxxx" -o result.json

# Xiaohongshu full links
python main.py "https://www.xiaohongshu.com/explore/xxxxx" -o result.json

# Kuaishou links (auto-detected, supports share text with URL)
python main.py "https://v.kuaishou.com/xxxxx" -o result.json

# Kuaishou full links
python main.py "https://www.kuaishou.com/short-video/xxxxx" -o result.json

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

# Quick test with Xiaohongshu URL (video note, parse only)
python main.py "http://xhslink.com/o/5uQW2gORRU1" --no-transcribe -o test.json

# Quick test with Xiaohongshu (full flow with transcription)
python main.py "http://xhslink.com/o/5uQW2gORRU1" --format-text -o test.json

# Quick test with Kuaishou URL (parse only)
python main.py "https://v.kuaishou.com/KH3UkHnt" --no-transcribe -o test.json

# Quick test with Kuaishou (full flow with transcription)
python main.py "https://v.kuaishou.com/KH3UkHnt" --format-text -o test.json

# Quick test with local video (parse only)
python main.py "D:\path\to\video.mp4" --no-transcribe -o test.json

# Quick test with local video (with transcription, requires OSS)
python main.py "D:\path\to\video.mp4" -o test.json

# Verify output
cat test.json | python -c "import sys, json; d=json.load(sys.stdin); print('Success:', d['status']['success']); print('Type:', d.get('content', {}).get('note_type', 'N/A'))"
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
    elif any(domain in url_lower for domain in ['xiaohongshu.com', 'xhslink.com', 'xhs.cn']):
        return 'xiaohongshu'
    elif any(domain in url_lower for domain in ['kuaishou.com', 'v.kuaishou.com']):
        return 'kuaishou'
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
- Captures API responses from `/aweme/v1/web/aweme/detail` and `/aweme/v1/web/aweme/detailinfo` endpoints
- Debug mode available via `DOUYIN_DEBUG=1` environment variable

**Bilibili Parser:**
- Uses HTTP requests with proper headers (User-Agent, Referer)
- Resolves b23.tv short links via redirect
- Extracts audio from DASH format (`data.dash.audio[0].baseUrl`)

**Xiaohongshu Parser:**
- Uses direct HTTP requests (not Playwright) to fetch page HTML — Xiaohongshu's anti-bot blocks headless browsers but serves full SSR data to HTTP requests
- Resolves `xhslink.com` short links via HTTP redirect (preserves `xsec_token` auth parameter)
- Converts `discovery/item/{id}` URLs to `explore/{id}` format with original query params
- Extracts structured data from `window.__INITIAL_STATE__` JSON in page HTML (replaces JS `undefined` → `null`)
- Supplements missing fields (cover URL, video URL) from `og:*` meta tags
- Two note types: video (`type: 'video'`) and image (`type: 'image'`)
- Image notes: no video/audio URLs, image list in `urls.images`, description in `content.desc`
- Video notes: audio_url = video_url (combined stream), video from `video.media.stream.h264[].masterUrl`
- Tag format: `#科技[话题]#` — bracket tags extracted alongside hash tags
- Debug mode available via `XHS_DEBUG=1` environment variable

**Kuaishou Parser:**
- Uses Playwright async API for browser automation (cookies required for GraphQL API)
- Resolves `v.kuaishou.com` short links via browser navigation (redirect)
- Extracts video ID (`photoId`) from final URL path
- Primary data source: GraphQL API (`POST https://www.kuaishou.com/graphql`) with `visionVideoDetail` query
- GraphQL call uses `page.evaluate(fetch(...))` to leverage browser's cookies
- Fallback 1: `window.__APOLLO_STATE__` JSON from page HTML
- Fallback 2: `og:*` meta tags
- Video URL: combined MP4 stream (audio+video), `audio_url = video_url`
- No dedicated share count; `share_count` uses `viewCount` (play count)
- `collect_count` is always `null` (not available via API)
- Debug mode available via `KUAISHOU_DEBUG=1` environment variable

### Unified Output Structure
All parsers output the same hierarchical JSON structure with categories:
`status`, `urls`, `content`, `author_info`, `statistics`, `video_detail`, `music_info`

All fields are optional - check existence before accessing.

### Transcription Error Handling
- If transcription fails, `video_info['transcription']` is set to `None`
- Error stored in `video_info['status']['transcription_error']`
- Video info is still returned even if transcription fails
- Image notes (`note_type == 'image'`) skip transcription entirely; `transcription` is `None`

### Share Text with Embedded Quotes
Platform share texts (especially Kuaishou) may contain ASCII double quotes `"` which break shell argument parsing. Three workarounds:

```bash
# 1. Pass URL only (recommended — extract_url handles the rest)
python main.py "https://v.kuaishou.com/KH3UkHnt" --format-text -o result.json

# 2. Use single quotes (bash only — single quotes preserve literal double quotes)
python main.py 'https://v.kuaishou.com/KH3UkHnt 你真的了解"卷积神经网络"吗？...' --format-text -o result.json

# 3. Pipe via stdin (works everywhere — no shell quoting issues)
echo '...share text with "quotes"...' | python main.py --format-text -o result.json
```

All parsers' `extract_url()` methods correctly extract URLs from messy share text containing quotes, hashtags, and other characters.

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
  "urls": {"video_url": str, "audio_url": str, "cover_url": str, "images": [str], "final_url": str},
  "content": {"title": str, "desc": str, "tag": str, "note_type": str},
  "author_info": {"author": str, "author_id": str},
  "statistics": {"like_count": int, "comment_count": int, "share_count": int, "collect_count": int},
  "video_detail": {"duration": int, "video_id": str, "create_time": int},
  "music_info": {"music": str},
  "transcription": {"url": str, "text": str, "segments": [{"text": str, "start": int, "end": int}]}
}
```

- `urls.images` — Only present for Xiaohongshu image notes; list of image URLs
- `content.note_type` — Only present for Xiaohongshu notes; `'video'` or `'image'`

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

Note: `transcription` is `null` if extraction fails, no audio URL is found, or for image notes.
When `--format-text` is not used, summary shows "无摘要" and text shows raw transcription.
For image notes, the text section contains image gallery (`![图片N](url)`) followed by description text. Keyframe extraction is skipped.

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

## Xiaohongshu-Specific Notes

### Two Note Types
Xiaohongshu has two content types:
- **Video notes** (`note_type: 'video'`): Contains a video with combined audio/video stream. `audio_url` equals `video_url`. Transcription and keyframe extraction work normally.
- **Image notes** (`note_type: 'image'`): Contains a list of images and text description. No video/audio. Transcription is skipped. Images are inserted as `![图片N](url)` in the Markdown note's text section.

### Short Link Resolution
- `xhslink.com` short links resolve via HTTP redirect to `xiaohongshu.com/discovery/item/{noteId}?...&xsec_token=...`
- The `xsec_token` parameter is essential for authorization — must be preserved in the explore URL
- Parser converts `discovery/item/` to `explore/` format while keeping query params

### SSR Data Extraction
- Xiaohongshu pages include full note data in `window.__INITIAL_STATE__` (server-side rendered)
- Direct HTTP requests receive this data; Playwright-based access is blocked by anti-bot
- Data path: `__INITIAL_STATE__.note.noteDetailMap[noteId].note`
- SSR data may lack some fields (e.g., cover image `infoList`), supplemented from `og:image` meta tag

### API Headers
```python
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.xiaohongshu.com',
}
```
Required for page requests and restricted audio/video URL downloads.

### Tag Format
Xiaohongshu uses a unique tag format: `#科技[话题]#`
- Both `#tag` and `[topic]` formats are extracted by `parse_title_and_tag()`
- Tags appear in `content.desc` (description), not in `content.title`

## Kuaishou-Specific Notes

### GraphQL API
- Endpoint: `POST https://www.kuaishou.com/graphql`
- Query: `visionVideoDetail` with `photoId` variable
- Requires cookies from a browser session — cannot be called with plain HTTP requests
- Returns: `data.visionVideoDetail.{photo, author}`

### Short Link Resolution
- `v.kuaishou.com` short links resolve via browser navigation (Playwright)
- Final URL format: `www.kuaishou.com/short-video/{photoId}` or `www.kuaishou.com/f/{photoId}`

### Video Format
- Kuaishou videos are combined MP4 streams (audio + video in one file)
- `audio_url = video_url` (same as Xiaohongshu)
- Higher quality URLs may be available in `photo.manifest.adaptationSet[].representation[]`

### API Headers
```python
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.kuaishou.com',
}
```
Required for restricted audio/video URL downloads.

### Statistics
- `like_count`: from `photo.likeCount`
- `comment_count`: from `photo.commentCount`
- `share_count`: uses `photo.viewCount` (play count, no dedicated share count)
- `collect_count`: always `null` (not available)

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
