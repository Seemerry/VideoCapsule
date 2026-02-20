"""Markdown笔记生成模块 - 从视频信息JSON生成笔记文件"""

import os
import re
from datetime import datetime
from typing import Optional


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

    def generate(self, video_info: dict, output_dir: Optional[str] = None) -> Optional[str]:
        """从视频信息生成Markdown笔记

        Args:
            video_info: 视频信息JSON字典
            output_dir: 输出目录，默认与JSON文件同目录

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

        title = content.get('title', '未知标题')
        tag = content.get('tag', '无')
        cover_url = urls.get('cover_url', '无')
        video_url = urls.get('video_url', '无')
        audio_url = urls.get('audio_url', '无')
        author = author_info.get('author', '未知')
        author_id = author_info.get('author_id', '未知')
        duration = video_detail.get('duration')
        video_id = video_detail.get('video_id', '未知')
        create_time = video_detail.get('create_time')

        # 统计数据
        like_count = statistics.get('like_count')
        comment_count = statistics.get('comment_count')
        share_count = statistics.get('share_count')
        collect_count = statistics.get('collect_count')

        # 转录文本
        text = transcription.get('text', '无转录内容') if transcription else '无转录内容'

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
        md_content = md_content.replace('"text"', text)

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
