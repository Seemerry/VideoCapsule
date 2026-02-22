"""视频关键帧提取模块 - 从视频中截取指定时间点的帧图片"""

import os
import re
import subprocess
import sys
import tempfile
from typing import List, Optional

import requests


class FrameExtractor:
    """视频关键帧提取器"""

    # 平台下载请求头
    BILIBILI_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
    }

    DOUYIN_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.douyin.com/',
    }

    XIAOHONGSHU_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.xiaohongshu.com',
    }

    KUAISHOU_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.kuaishou.com',
    }

    def extract_frames(self, video_source: str, timestamps_ms: List[int],
                       output_dir: str, title: str) -> List[dict]:
        """从视频中提取指定时间点的帧图片

        Args:
            video_source: 视频路径或URL
            timestamps_ms: 时间戳列表（毫秒）
            output_dir: 输出目录
            title: 视频标题（用于生成assets子文件夹名）

        Returns:
            list: [{'timestamp_ms': int, 'image_path': str, 'relative_path': str, 'label': str}]
        """
        if not timestamps_ms:
            return []

        # 创建 assets 子文件夹
        safe_title = self._sanitize_dirname(title)
        assets_dir = os.path.join(output_dir, f"{safe_title}_assets")
        os.makedirs(assets_dir, exist_ok=True)

        # 检测是否为本地文件
        is_local = os.path.isfile(video_source)
        temp_file = None
        video_path = video_source

        try:
            if not is_local:
                # 远程视频需要先下载
                platform = self._detect_platform(video_source)
                temp_file = self._download_video(video_source, platform)
                if temp_file is None:
                    return []
                video_path = temp_file

            # 对每个时间戳提取帧
            results = []
            for idx, ts_ms in enumerate(timestamps_ms):
                filename = self._frame_filename(idx, ts_ms)
                output_path = os.path.join(assets_dir, filename)
                relative_path = f"{safe_title}_assets/{filename}"

                success = self._extract_single_frame(video_path, ts_ms, output_path)
                if success:
                    results.append({
                        'timestamp_ms': ts_ms,
                        'image_path': os.path.abspath(output_path),
                        'relative_path': relative_path,
                        'label': self._format_timestamp_label(ts_ms),
                    })

            return results

        finally:
            # 清理临时下载文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass

    def _download_video(self, url: str, platform: str) -> Optional[str]:
        """下载远程视频到临时文件

        Args:
            url: 视频URL
            platform: 平台标识 ('bilibili', 'douyin', 'other')

        Returns:
            str: 临时文件路径，失败返回 None
        """
        try:
            headers = {}
            if platform == 'bilibili':
                headers = self.BILIBILI_HEADERS
            elif platform == 'douyin':
                headers = self.DOUYIN_HEADERS
            elif platform == 'xiaohongshu':
                headers = self.XIAOHONGSHU_HEADERS
            elif platform == 'kuaishou':
                headers = self.KUAISHOU_HEADERS

            response = requests.get(url, headers=headers, stream=True, timeout=120)
            response.raise_for_status()

            # 创建临时文件
            suffix = '.m4s' if platform == 'bilibili' else '.mp4'
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
            tmp.close()
            return tmp.name

        except Exception as e:
            print(f"视频下载失败: {e}", file=sys.stderr)
            return None

    def _extract_single_frame(self, video_path: str, timestamp_ms: int,
                              output_path: str) -> bool:
        """使用 ffmpeg 从视频中提取单帧

        Args:
            video_path: 视频文件路径
            timestamp_ms: 时间戳（毫秒）
            output_path: 输出图片路径

        Returns:
            bool: 是否成功
        """
        seconds = timestamp_ms / 1000.0
        try:
            result = subprocess.run(
                [
                    'ffmpeg', '-ss', f'{seconds:.3f}',
                    '-i', video_path,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    output_path,
                ],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0 and os.path.exists(output_path)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"ffmpeg 帧提取失败 ({self._format_timestamp_label(timestamp_ms)}): {e}", file=sys.stderr)
            return False

    def _detect_platform(self, url: str) -> str:
        """根据 URL 特征判断平台"""
        url_lower = url.lower()
        if any(d in url_lower for d in ['bilibili.com', 'bilivideo', 'b23.tv']):
            return 'bilibili'
        if any(d in url_lower for d in ['douyin.com', 'iesdouyin.com', 'douyinvod']):
            return 'douyin'
        if any(d in url_lower for d in ['xiaohongshu.com', 'xhscdn.com']):
            return 'xiaohongshu'
        if any(d in url_lower for d in ['kuaishou.com', 'ksvideo']):
            return 'kuaishou'
        return 'other'

    @staticmethod
    def _format_timestamp_label(timestamp_ms: int) -> str:
        """将毫秒时间戳格式化为 mm:ss 标签"""
        total_seconds = timestamp_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    @staticmethod
    def _frame_filename(index: int, timestamp_ms: int) -> str:
        """生成帧图片文件名: frame_01_00m29s.jpg"""
        total_seconds = timestamp_ms // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"frame_{index + 1:02d}_{minutes:02d}m{seconds:02d}s.jpg"

    @staticmethod
    def _sanitize_dirname(title: str) -> str:
        """清理文件夹名称，移除非法字符"""
        illegal_chars = r'[<>:"/\\|?*]'
        sanitized = re.sub(illegal_chars, '_', title)
        sanitized = sanitized.strip(' .')
        return sanitized[:100] if len(sanitized) > 100 else sanitized
