# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a multi-platform video information extractor that combines link parsing and audio transcription. Given a Douyin or Bilibili URL, it extracts comprehensive video metadata and transcribes the audio content using speech-to-text APIs.

**Note**: This project is fully self-contained with no external project dependencies.

## Architecture

### Data Flow

```
Input URL → Platform Detection → Parser (Douyin/Bilibili) → Video Info → TextExtractor → Transcription
                                                                              ↓
                                                                      Complete JSON Output
```

### Core Components

**main.py** - Entry point and orchestrator
- `detect_platform(url)` - Detects platform from URL (douyin/bilibili/unknown)
- `VideoExtractor.extract()` - Main extraction pipeline
  1. Detects platform and selects appropriate parser
  2. Parses URL via `DouyinLinkParser` or `BilibiliLinkParser`
  3. Extracts audio URL from video info
  4. Transcribes audio via `TextExtractor`
  5. Post-processes title/tags
- Tag extraction happens AFTER video parsing to separate `#hashtags` from title

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

**modules/text_extractor.py** - Audio transcription
- Self-contained audio-to-text functionality
- Supports two models: `doubao` (default) and `paraformer`
- Key architecture:
  - `_transcribe_audio_doubao()` - Two-phase: submit → poll (60 retries, 2s interval)
  - `_transcribe_audio_paraformer()` - Uses DashScope SDK
  - `_format_result()` - Delegates to model-specific formatters
  - `_add_speaker_label()` - Auto-merges consecutive segments from same speaker

## Common Commands

### Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

### Configuration
- Copy `config.example.json` to `config.json`
- Add API keys for DashScope and Doubao (required for transcription)

### Running
```bash
# Douyin links (auto-detected)
python main.py "https://v.douyin.com/xxxxx/" -o result.json

# Bilibili links (auto-detected)
python main.py "https://www.bilibili.com/video/BVxxxxx/" -o result.json

# Bilibili short links
python main.py "https://b23.tv/xxxxx" -o result.json

# Parse only (no transcription)
python main.py "URL" --no-transcribe -o result.json

# With speaker detection
python main.py "URL" --speaker-info -o result.json

# Use Paraformer model instead of Doubao
python main.py "URL" --model paraformer -o result.json
```

### Testing Changes
```bash
# Quick test with Douyin URL
python main.py "https://v.douyin.com/OQsck5Woryw/" -o test.json

# Quick test with Bilibili URL
python main.py "https://www.bilibili.com/video/BV1MbFXz5Esa/" -o test.json

# Verify output
cat test.json | python -c "import sys, json; d=json.load(sys.stdin); print('Success:', d['status']['success']); print('Platform:', 'Bilibili' if 'BV' in d.get('video_detail', {}).get('video_id', '') else 'Douyin')"
```

## Key Implementation Details

### Platform Detection (main.py)
```python
def detect_platform(url: str) -> str:
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

Note: `transcription` is `null` if extraction fails or no audio URL is found.

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
