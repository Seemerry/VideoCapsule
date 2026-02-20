"""本地视频解析模块 - 本地视频文件信息提取功能"""

import os
import re
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple


class _LocalParserCore:
    """本地视频解析器核心类"""

    # 支持的视频格式
    SUPPORTED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}

    def __init__(self):
        # 定义字段分类映射（与其他解析器保持一致）
        self.field_categories = {
            # 状态和错误信息
            'status': ['success', 'error'],

            # URL链接
            'urls': ['video_url', 'audio_url', 'cover_url', 'final_url'],

            # 内容信息
            'content': ['title', 'desc', 'tag'],

            # 作者信息
            'author_info': ['author', 'author_id'],

            # 统计数据
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],

            # 视频详情
            'video_detail': ['duration', 'video_id', 'create_time'],

            # 音乐信息
            'music_info': ['music'],
        }

        # 定义分类的显示顺序
        self.category_order = ['status', 'urls', 'content', 'author_info', 'statistics', 'video_detail', 'music_info']

        # 定义每个分类内字段的顺序
        self.field_order = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'final_url'],
            'content': ['title', 'desc', 'tag'],
            'author_info': ['author', 'author_id'],
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],
            'video_detail': ['duration', 'video_id', 'create_time'],
            'music_info': ['music'],
        }

    def _organize_result(self, data: dict) -> dict:
        """
        将扁平的数据组织为层级结构

        Args:
            data: 原始扁平数据字典

        Returns:
            dict: 层级化的数据字典
        """
        organized = {}

        # 创建反向映射：字段 -> 分类
        field_to_category = {}
        for category, fields in self.field_categories.items():
            for field in fields:
                field_to_category[field] = category

        # 按分类顺序组织数据
        for category in self.category_order:
            category_data = {}

            # 获取该分类下的所有字段
            if category in self.field_order:
                for field in self.field_order[category]:
                    if field in data:
                        category_data[field] = data[field]

            # 添加该分类到结果中（如果有数据）
            if category_data:
                organized[category] = category_data

        # 添加未定义分类的字段
        for key, value in data.items():
            if key not in field_to_category:
                if 'other' not in organized:
                    organized['other'] = {}
                organized['other'][key] = value

        return organized

    def extract_url(self, text: str) -> str:
        """
        从输入文本中提取本地文件路径

        Args:
            text: 输入文本，可能是文件路径

        Returns:
            str: 文件路径
        """
        # 去除首尾空白和可能的引号
        path = text.strip().strip('"').strip("'")

        # 检查是否是本地文件路径
        if self._is_local_file(path):
            return path

        return text.strip()

    def _is_local_file(self, path: str) -> bool:
        """
        检查路径是否是本地视频文件

        Args:
            path: 文件路径

        Returns:
            bool: 是否是本地视频文件
        """
        # 检查是否是URL
        if path.startswith(('http://', 'https://')):
            return False

        # 检查文件是否存在
        if not os.path.isfile(path):
            return False

        # 检查文件扩展名
        ext = os.path.splitext(path)[1].lower()
        return ext in self.SUPPORTED_EXTENSIONS

    def _get_video_info_ffprobe(self, file_path: str) -> dict:
        """
        使用 ffprobe 获取视频信息

        Args:
            file_path: 视频文件路径

        Returns:
            dict: 视频信息
        """
        try:
            # 使用 ffprobe 获取视频信息
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0:
                return json.loads(result.stdout.decode('utf-8', errors='ignore'))
        except FileNotFoundError:
            # ffprobe 不存在
            pass
        except subprocess.TimeoutExpired:
            pass
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

        return {}

    def _extract_title_from_filename(self, file_path: str) -> str:
        """
        从文件名提取标题

        Args:
            file_path: 视频文件路径

        Returns:
            str: 提取的标题
        """
        # 获取文件名（不含扩展名）
        filename = os.path.splitext(os.path.basename(file_path))[0]

        # 尝试清理文件名中的一些常见模式
        patterns_to_remove = [
            r'\s*-\s*\d+\.\s*',  # "- 1." 模式
            r'\s*\(Av\d+,P\d+\)\s*$',  # "(Av123,P1)" 模式
            r'\s*\(av\d+,P\d+\)\s*$',  # "(av123,P1)" 模式（小写）
            r'\s*\[.*?\]\s*$',  # 结尾的方括号内容
        ]

        cleaned = filename
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned)

        # 移除重复的标题部分（例如 "【漫士】xxx【漫士】xxx" 变成 "【漫士】xxx"）
        # 检测是否有重复的前缀+内容模式
        bracket_match = re.match(r'^([【\[「『].*?[】\]」』])(.+)$', cleaned)
        if bracket_match:
            prefix = bracket_match.group(1)
            content = bracket_match.group(2).strip()
            # 如果内容以相同的prefix开头，说明有重复
            if content.startswith(prefix):
                cleaned = prefix + content[len(prefix):].strip()

        # 尝试检测并移除重复的内容（无空格分隔的情况）
        # 例如 "【漫士】看完这个视频【漫士】看完这个视频" -> "【漫士】看完这个视频"
        # 找到最短的非重复前缀
        for length in range(len(cleaned) // 2, 0, -1):
            if len(cleaned) >= length * 2:
                first_half = cleaned[:length]
                second_half = cleaned[length:].lstrip()  # 移除左边可能的空格
                if second_half.startswith(first_half):
                    cleaned = first_half
                    break

        # 清理多余空格
        cleaned = ' '.join(cleaned.split())

        return cleaned.strip() if cleaned.strip() else filename

    def _get_file_create_time(self, file_path: str) -> int:
        """
        获取文件创建时间

        Args:
            file_path: 文件路径

        Returns:
            int: Unix 时间戳
        """
        try:
            # Windows 使用 st_ctime (创建时间)
            # Unix 使用 st_mtime (修改时间) 作为备选
            stat = os.stat(file_path)
            return int(stat.st_ctime)
        except Exception:
            return 0

    def parse(self, file_path: str) -> dict:
        """
        解析本地视频文件

        Args:
            file_path: 视频文件路径

        Returns:
            dict: 解析结果
        """
        try:
            # 检查文件是否存在
            if not os.path.isfile(file_path):
                return self._organize_result({
                    'success': False,
                    'error': f'文件不存在: {file_path}'
                })

            # 检查文件扩展名
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in self.SUPPORTED_EXTENSIONS:
                return self._organize_result({
                    'success': False,
                    'error': f'不支持的视频格式: {ext}'
                })

            # 获取视频信息
            ffprobe_info = self._get_video_info_ffprobe(file_path)

            # 提取基本信息
            result = {
                'success': True,
                'video_url': file_path,
                'audio_url': file_path,  # 本地文件同时作为视频和音频源
                'cover_url': None,
                'final_url': file_path,
            }

            # 从文件名提取标题
            title = self._extract_title_from_filename(file_path)
            result['title'] = title
            result['desc'] = None
            result['tag'] = None

            # 作者信息（本地文件无作者信息）
            result['author'] = None
            result['author_id'] = None

            # 统计数据（本地文件无统计数据，设为 None）
            result['like_count'] = None
            result['comment_count'] = None
            result['share_count'] = None
            result['collect_count'] = None

            # 视频详情
            result['video_id'] = os.path.basename(file_path)
            result['create_time'] = self._get_file_create_time(file_path)

            # 从 ffprobe 信息中提取时长
            duration = None
            if ffprobe_info:
                format_info = ffprobe_info.get('format', {})
                # 尝试从 format 获取时长（秒）
                if 'duration' in format_info:
                    try:
                        duration = float(format_info['duration']) * 1000  # 转换为毫秒
                    except (ValueError, TypeError):
                        pass

                # 如果没有从 format 获取到，尝试从视频流获取
                if duration is None:
                    for stream in ffprobe_info.get('streams', []):
                        if stream.get('codec_type') == 'video':
                            if 'duration' in stream:
                                try:
                                    duration = float(stream['duration']) * 1000
                                except (ValueError, TypeError):
                                    pass
                            break

            result['duration'] = int(duration) if duration else None

            # 音乐信息（本地视频无独立音乐信息）
            result['music'] = None

            return self._organize_result(result)

        except Exception as e:
            return self._organize_result({
                'success': False,
                'error': f'解析异常: {str(e)}'
            })

    def parse_title_and_tag(self, title_text: str) -> Tuple[str, Optional[str]]:
        """
        解析标题和标签

        Args:
            title_text: 原始标题文本

        Returns:
            tuple: (title, tag)
        """
        # 查找所有 # 标签（# 后跟非空白字符）
        tag_pattern = r'#(\S+)'
        tags = re.findall(tag_pattern, title_text)

        if tags:
            # 去掉标签后的标题
            title = re.sub(tag_pattern, '', title_text).strip()
            # 清理标题末尾可能的空格和标点
            title = re.sub(r'\s*[，、。,]*$', '', title)
            # 用顿号连接多个标签
            tag = ' 、'.join(tags)
            return title, tag
        else:
            # 没有找到标签
            return title_text, None


class LocalVideoParser:
    """本地视频解析器 - 对外接口"""

    def __init__(self):
        self._parser = _LocalParserCore()

    def extract_url(self, text: str) -> str:
        """从输入文本中提取本地文件路径"""
        return self._parser.extract_url(text)

    def parse(self, file_path: str) -> dict:
        """解析本地视频文件，获取视频信息"""
        return self._parser.parse(file_path)

    def parse_title_and_tag(self, title_text: str) -> Tuple[str, Optional[str]]:
        """解析标题和标签，返回 (title, tag)"""
        return self._parser.parse_title_and_tag(title_text)

    def is_local_file(self, path: str) -> bool:
        """检查路径是否是本地视频文件"""
        return self._parser._is_local_file(path)
