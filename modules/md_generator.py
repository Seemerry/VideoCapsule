"""Markdown笔记生成模块 - 从视频信息JSON生成笔记文件"""

import os
import re
import sys
from datetime import datetime
from typing import Optional, List

from .text_formatter import TextFormatter
from .frame_extractor import FrameExtractor
from .mindmap_generator import MindMapGenerator


class MarkdownGenerator:
    """Markdown笔记生成器"""

    def __init__(self, template_path: Optional[str] = None):
        """初始化生成器

        Args:
            template_path: 模板文件路径，默认为同目录下的视频笔记模板.md
        """
        if template_path is None:
            template_path = os.path.join(os.path.dirname(__file__), '..', '视频笔记模板.md')
        self.template_path = template_path
        self.template = self._load_template()

    def _load_template(self) -> str:
        """加载模板文件"""
        with open(self.template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 将Unicode左右引号(U+201C, U+201D)转换为普通引号(U+0022)，方便替换
        content = content.replace('\u201c', '"').replace('\u201d', '"')
        return content

    def _format_duration(self, duration_ms: Optional[int]) -> str:
        """格式化时长（毫秒转 mm:ss 或 hh:mm:ss）"""
        if duration_ms is None:
            return '未知'

        total_seconds = duration_ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _format_timestamp(self, timestamp: Optional[int]) -> str:
        """格式化时间戳（秒级时间戳转 YYYY-MM-DD HH:mm）"""
        if timestamp is None:
            return '未知'

        try:
            # 处理毫秒级时间戳
            if timestamp > 10000000000:
                timestamp = timestamp // 1000
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, TypeError):
            return '未知'

    def _format_number(self, num: Optional[int]) -> str:
        """格式化数字（处理null和显示）"""
        if num is None:
            return '无数据'
        return str(num)

    def _sanitize_filename(self, title: str) -> str:
        """清理文件名，移除非法字符"""
        # 移除Windows文件名中的非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(illegal_chars, '_', title)
        # 移除首尾空格和点
        sanitized = sanitized.strip(' .')
        # 限制长度
        return sanitized[:100] if len(sanitized) > 100 else sanitized

    def _insert_frames(self, formatter: 'TextFormatter', formatted_text: str,
                       segments: List[dict], video_url: str, title: str,
                       output_dir: str) -> str:
        """识别关键节点、提取帧图片并插入到格式化文本中

        Args:
            formatter: TextFormatter 实例
            formatted_text: 格式化后的文本
            segments: 转录片段列表
            video_url: 视频URL或路径
            title: 视频标题
            output_dir: 输出目录

        Returns:
            str: 插入帧图片后的文本，失败返回原文
        """
        try:
            # 1. 识别关键节点
            key_moments = formatter.identify_key_moments(formatted_text, segments)
            if not key_moments:
                return formatted_text

            # 2. 提取帧图片
            timestamps = [m['timestamp_ms'] for m in key_moments]
            extractor = FrameExtractor()
            frames = extractor.extract_frames(video_url, timestamps, output_dir, title)
            if not frames:
                return formatted_text

            # 建立 timestamp -> frame 映射
            frame_map = {f['timestamp_ms']: f for f in frames}

            # 3. 收集需要插入的 (位置, markdown) 对
            insertions = []
            for moment in key_moments:
                ts = moment['timestamp_ms']
                frame = frame_map.get(ts)
                if not frame:
                    continue

                pos = self._find_insertion_point(formatted_text, moment['text'])
                if pos < 0:
                    continue

                label = frame['label']
                rel_path = frame['relative_path']
                frame_md = f"\n\n![{label}]({rel_path})\n*{label}*\n"
                insertions.append((pos, frame_md))

            if not insertions:
                return formatted_text

            # 4. 按位置逆序插入，避免偏移
            insertions.sort(key=lambda x: x[0], reverse=True)
            result = formatted_text
            for pos, md in insertions:
                result = result[:pos] + md + result[pos:]

            print(f"已插入 {len(insertions)} 个关键帧图片", file=sys.stderr)
            return result

        except Exception as e:
            print(f"关键帧插入失败，使用原文: {e}", file=sys.stderr)
            return formatted_text

    @staticmethod
    def _find_insertion_point(text: str, segment_text: str) -> int:
        """在格式化文本中定位片段对应的插入位置

        在找到的文本位置之前的段落边界处插入。

        Args:
            text: 格式化后的完整文本
            segment_text: 要定位的片段文本

        Returns:
            int: 插入位置索引，找不到返回 -1
        """
        segment_text = segment_text.strip()
        if not segment_text:
            return -1

        # 精确匹配
        pos = text.find(segment_text)

        # 失败则尝试匹配前20个字符
        if pos < 0 and len(segment_text) > 20:
            pos = text.find(segment_text[:20])

        if pos < 0:
            return -1

        # 回溯到段落起始位置（最近的 \n\n）
        para_start = text.rfind('\n\n', 0, pos)
        if para_start >= 0:
            return para_start
        return 0

    def generate(self, video_info: dict, output_dir: Optional[str] = None,
                 format_text: bool = False, config_path: Optional[str] = None) -> Optional[str]:
        """从视频信息生成Markdown笔记

        Args:
            video_info: 视频信息JSON字典
            output_dir: 输出目录，默认与JSON文件同目录
            format_text: 是否使用 DeepSeek API 格式化转录文本
            config_path: 配置文件路径

        Returns:
            str: 生成的Markdown文件路径，失败返回None
        """
        if not video_info.get('status', {}).get('success', False):
            return None

        # 提取各字段
        content = video_info.get('content', {})
        urls = video_info.get('urls', {})
        author_info = video_info.get('author_info', {})
        statistics = video_info.get('statistics') or {}
        video_detail = video_info.get('video_detail', {})
        transcription = video_info.get('transcription')

        title = content.get('title') or '未知标题'
        tag = content.get('tag') or '无'
        cover_url = urls.get('cover_url') or '无'
        video_url = urls.get('video_url') or '无'
        audio_url = urls.get('audio_url') or '无'
        author = author_info.get('author') or '未知'
        author_id = author_info.get('author_id') or '未知'
        duration = video_detail.get('duration')
        video_id = video_detail.get('video_id') or '未知'
        create_time = video_detail.get('create_time')

        # 统计数据
        like_count = statistics.get('like_count')
        comment_count = statistics.get('comment_count')
        share_count = statistics.get('share_count')
        collect_count = statistics.get('collect_count')

        # 转录文本
        raw_text = transcription.get('text', '无转录内容') if transcription else '无转录内容'

        # 初始化摘要和文本
        summary = '无摘要'
        text = raw_text
        mindmap_image_md = ''

        # 如果启用格式化，使用 DeepSeek API 处理文本（生成摘要 + 格式化原文）
        if format_text and raw_text != '无转录内容':
            formatter = TextFormatter(config_path)
            result = formatter.process_text(raw_text, title)
            if result.get('summary'):
                summary = result['summary']
            if result.get('formatted_text'):
                text = result['formatted_text']
            print("文本处理完成", file=sys.stderr)

            # 提取关键帧并插入到格式化后的文本中
            segments = transcription.get('segments', []) if transcription else []
            if segments:
                text = self._insert_frames(
                    formatter, text, segments,
                    urls.get('video_url', ''), title, output_dir or '.'
                )

            # 生成思维导图
            mindmap_md = formatter.generate_mindmap_markdown(raw_text, title)
            if mindmap_md:
                mg = MindMapGenerator()
                mindmap_result = mg.generate(mindmap_md, output_dir or '.', title)
                if mindmap_result:
                    img_rel = mindmap_result['image_relative_path']
                    src_rel = mindmap_result['source_relative_path']
                    mindmap_image_md = (
                        f'![思维导图]({img_rel})\n\n'
                        f'> 源文件: [{src_rel}]({src_rel})（可编辑后重新生成）'
                    )

        # 当前时间（精确到分）
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

        # 替换模板中的占位符
        md_content = self.template
        md_content = md_content.replace('"title"', title)
        md_content = md_content.replace('"cover_url"', cover_url)
        md_content = md_content.replace('"video_url"', video_url)
        md_content = md_content.replace('"audio_url"', audio_url)
        md_content = md_content.replace('"tag"', tag)
        md_content = md_content.replace('"author"', author)
        md_content = md_content.replace('"author_id"', author_id)
        md_content = md_content.replace('"duration"', self._format_duration(duration))
        md_content = md_content.replace('"video_id"', video_id)
        md_content = md_content.replace('"create_time"', self._format_timestamp(create_time))
        md_content = md_content.replace('time', current_time)
        md_content = md_content.replace('"like_count"', self._format_number(like_count))
        md_content = md_content.replace('"comment_count"', self._format_number(comment_count))
        md_content = md_content.replace('"share_count"', self._format_number(share_count))
        md_content = md_content.replace('"collect_count"', self._format_number(collect_count))
        md_content = md_content.replace('"summary"', summary)
        md_content = md_content.replace('"text"', text)
        md_content = md_content.replace('"mindmap"', mindmap_image_md)

        # 生成文件名
        safe_title = self._sanitize_filename(title)
        filename = f"{safe_title}_笔记.md"

        # 确定输出路径
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, filename)
        else:
            output_path = filename

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return os.path.abspath(output_path)
