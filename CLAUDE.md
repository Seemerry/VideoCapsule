# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a standalone Douyin (TikTok China) video information extractor that combines link parsing and audio transcription. Given a Douyin URL, it extracts comprehensive video metadata and transcribes the audio content using speech-to-text APIs.

**Note**: This project is fully self-contained with no external project dependencies.

## Architecture

### Data Flow

```
Input (Douyin URL) → LinkParser → Video Info → TextExtractor → Transcription
                                                      ↓
                                              Complete JSON Output
```

### Core Components

**main.py** - Entry point and orchestrator
- `DouyinVideoExtractor.extract()` - Main extraction pipeline
  1. Parses Douyin URL via `LinkParser`
  2. Extracts audio URL from video info
  3. Transcribes audio via `TextExtractor`
  4. Post-processes title/tags (lines 100-106)
- Tag extraction happens AFTER video parsing to separate `#hashtags` from title

**modules/link_parser.py** - Video metadata extraction
- Self-contained Playwright-based Douyin parser
- Uses `_DouyinParserCore` class for all parsing logic
- Key methods:
  - `extract_url()` - Extracts clean URL from share text
  - `parse()` - Returns hierarchical JSON with video info
  - `parse_title_and_tag()` - Separates hashtags from title using regex
- Captures API responses via Playwright route handling
- Extracts: video URL, audio URL, cover, title, author, statistics, etc.

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
# Basic usage
python main.py "https://v.douyin.com/xxxxx/"

# Save to file (recommended - avoids console encoding issues)
python main.py "https://v.douyin.com/xxxxx/" -o result.json

# With speaker detection
python main.py "URL" --speaker-info -o result.json

# Use Paraformer model instead of Doubao
python main.py "URL" --model paraformer -o result.json
```

### Testing Changes
```bash
# Quick test with known working URL
python main.py "https://v.douyin.com/OQsck5Woryw/" -o test.json

# Verify output
cat test.json | python -c "import sys, json; d=json.load(sys.stdin); print('Success:', d['status']['success']); print('Has tag:', 'tag' in d.get('content', {}))"
```

## Key Implementation Details

### Tag Extraction Logic (main.py:100-106)
Tags are extracted AFTER video parsing:
1. Get `title` from `content.title` (contains hashtags)
2. Call `parse_title_and_tag()` which uses regex to find `#(\S+)` pattern
3. Returns `(cleaned_title, tags_string)` where tags are joined by ` 、`
4. Updates `result['content']['title']` and adds `result['content']['tag']`

### Audio URL Fallback (main.py:29-30)
```python
audio_url = video_info['urls'].get('audio_url') or video_info['urls'].get('video_url')
```
Tries `audio_url` first, falls back to `video_url` if missing.

### Link Parser Architecture
- Uses Playwright async API for browser automation
- Captures API responses from `/aweme/v1/web/aweme/detail` endpoints
- Hierarchical JSON output with categories: `status`, `urls`, `content`, `author_info`, `statistics`, `video_detail`, `music_info`
- All fields are optional - check existence before accessing
- Debug mode available via `DOUYIN_DEBUG=1` environment variable

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
