"""Bilibili链接解析模块 - Bilibili视频链接解析功能"""

import re
import requests
from typing import Optional, Tuple


class _BilibiliParserCore:
    """Bilibili解析器核心类"""

    # API endpoints
    VIDEO_INFO_API = "https://api.bilibili.com/x/web-interface/view"
    PLAY_URL_API = "https://api.bilibili.com/x/player/playurl"

    # 请求头
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com',
    }

    def __init__(self):
        # 定义字段分类映射（与Douyin保持完全一致）
        self.field_categories = {
            # 状态和错误信息
            'status': ['success', 'error'],

            # URL链接
            'urls': ['video_url', 'audio_url', 'cover_url', 'final_url'],

            # 内容信息
            'content': ['title', 'desc', 'tag'],

            # 作者信息
            'author_info': ['author', 'author_id'],

            # 统计数据（与Douyin保持一致，只有4个字段）
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
        从分享文本中提取Bilibili URL

        Args:
            text: 分享文本，可能包含链接

        Returns:
            str: 提取到的URL，如果没有找到则返回原文本
        """
        # 匹配Bilibili链接的各种格式
        patterns = [
            r'https?://www\.bilibili\.com/video/(BV[a-zA-Z0-9]+)/?',  # 标准BV链接
            r'https?://bilibili\.com/video/(BV[a-zA-Z0-9]+)/?',  # 无www的BV链接
            r'https?://b23\.tv/([a-zA-Z0-9]+)',  # 短链接
            r'(BV[a-zA-Z0-9]{10,})',  # 纯BV号
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                url = match.group(0)
                # 如果匹配到的是BV号，构造完整URL
                if url.startswith('BV'):
                    return f'https://www.bilibili.com/video/{url}/'
                return url

        # 如果没有匹配到，返回原文本（假设它已经是URL）
        return text.strip()

    def _extract_bvid(self, url: str) -> Optional[str]:
        """
        从URL中提取BV号

        Args:
            url: Bilibili视频URL

        Returns:
            str: BV号，如果提取失败返回None
        """
        # 处理短链接
        if 'b23.tv' in url:
            try:
                response = requests.head(url, headers=self.HEADERS, allow_redirects=True, timeout=10)
                url = response.url
            except Exception:
                return None

        # 从URL中提取BV号
        match = re.search(r'(BV[a-zA-Z0-9]+)', url)
        if match:
            return match.group(1)

        return None

    def _fetch_video_info(self, bvid: str) -> dict:
        """
        调用Bilibili API获取视频信息

        Args:
            bvid: 视频BV号

        Returns:
            dict: API响应数据
        """
        params = {'bvid': bvid}
        response = requests.get(
            self.VIDEO_INFO_API,
            params=params,
            headers=self.HEADERS,
            timeout=15
        )
        response.raise_for_status()
        return response.json()

    def _fetch_play_url(self, bvid: str, cid: int) -> dict:
        """
        调用Bilibili API获取播放地址

        Args:
            bvid: 视频BV号
            cid: 视频cid

        Returns:
            dict: API响应数据
        """
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': 16,  # 画质（16=高清1080P）
            'fnver': 0,
            'fnval': 16,  # 启用DASH格式
            'fourk': 0
        }
        response = requests.get(
            self.PLAY_URL_API,
            params=params,
            headers=self.HEADERS,
            timeout=15
        )
        response.raise_for_status()
        return response.json()

    def _extract_audio_url(self, play_data: dict) -> Optional[str]:
        """
        从播放地址API响应中提取音频URL

        Args:
            play_data: 播放地址API响应

        Returns:
            str: 音频URL，如果提取失败返回None
        """
        data = play_data.get('data', {})

        # 优先尝试DASH格式
        dash = data.get('dash', {})
        if dash:
            audio_list = dash.get('audio', [])
            if audio_list:
                # 选择最高质量的音频
                audio_info = audio_list[0]
                return audio_info.get('baseUrl') or audio_info.get('base_url')

        # 备选：DURL格式（旧版）
        durl = data.get('durl', [])
        if durl:
            return durl[0].get('url')

        return None

    def _extract_video_url(self, play_data: dict) -> Optional[str]:
        """
        从播放地址API响应中提取视频URL

        Args:
            play_data: 播放地址API响应

        Returns:
            str: 视频URL，如果提取失败返回None
        """
        data = play_data.get('data', {})

        # 优先尝试DASH格式
        dash = data.get('dash', {})
        if dash:
            video_list = dash.get('video', [])
            if video_list:
                # 选择最高质量的视频
                video_info = video_list[0]
                return video_info.get('baseUrl') or video_info.get('base_url')

        # 备选：DURL格式（旧版）
        durl = data.get('durl', [])
        if durl:
            return durl[0].get('url')

        return None

    def _map_video_info(self, api_data: dict) -> dict:
        """
        将API响应映射到输出格式

        Args:
            api_data: Bilibili API响应数据

        Returns:
            dict: 映射后的视频信息
        """
        data = api_data.get('data', {})
        if not data:
            return {'success': False, 'error': 'API返回数据为空'}

        # 提取背景音乐信息
        music_info = data.get('music', {})
        music_name = ''
        if music_info:
            # 优先使用音乐标题
            music_name = music_info.get('title', '') or music_info.get('name', '')
            # 如果有作者信息，拼接
            music_author = music_info.get('author', '') or music_info.get('up_name', '')
            if music_author:
                music_name = f"{music_name} - {music_author}" if music_name else music_author

        result = {
            'success': True,
            # 内容信息
            'title': data.get('title', ''),
            'desc': data.get('desc', ''),

            # 作者信息
            'author': data.get('owner', {}).get('name', ''),
            'author_id': str(data.get('owner', {}).get('mid', '')),

            # 统计数据（与Douyin字段保持一致）
            'like_count': data.get('stat', {}).get('like', 0),
            'comment_count': data.get('stat', {}).get('reply', 0),
            'share_count': data.get('stat', {}).get('share', 0),
            'collect_count': data.get('stat', {}).get('favorite', 0),  # 收藏数

            # 视频详情
            'duration': (data.get('duration', 0) or 0) * 1000,  # 转换为毫秒
            'video_id': data.get('bvid', ''),
            'create_time': data.get('pubdate', 0),

            # 音乐信息
            'music': music_name if music_name else None,

            # URL
            'cover_url': data.get('pic', ''),
            'final_url': f"https://www.bilibili.com/video/{data.get('bvid', '')}/",

            # 保存cid用于获取播放地址
            '_cid': data.get('cid'),
            '_bvid': data.get('bvid'),
        }

        return result

    def parse(self, url: str) -> dict:
        """
        解析Bilibili链接，获取视频信息

        Args:
            url: Bilibili视频链接

        Returns:
            dict: 解析结果
        """
        try:
            # 提取BV号
            bvid = self._extract_bvid(url)
            if not bvid:
                return self._organize_result({
                    'success': False,
                    'error': '无法从链接中提取BV号'
                })

            # 获取视频信息
            api_data = self._fetch_video_info(bvid)
            if api_data.get('code', 0) != 0:
                return self._organize_result({
                    'success': False,
                    'error': f"API错误: {api_data.get('message', '未知错误')}"
                })

            # 映射视频信息
            result = self._map_video_info(api_data)

            # 获取音频和视频URL
            cid = result.pop('_cid', None)
            bvid = result.pop('_bvid', None)

            if cid and bvid:
                try:
                    play_data = self._fetch_play_url(bvid, cid)
                    if play_data.get('code', 0) == 0:
                        # 提取视频URL
                        video_url = self._extract_video_url(play_data)
                        if video_url:
                            result['video_url'] = video_url

                        # 提取音频URL
                        audio_url = self._extract_audio_url(play_data)
                        if audio_url:
                            result['audio_url'] = audio_url
                except Exception as e:
                    # URL获取失败不影响基本信息
                    pass

            return self._organize_result(result)

        except requests.RequestException as e:
            return self._organize_result({
                'success': False,
                'error': f'网络请求失败: {str(e)}'
            })
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
        # Bilibili标题通常不包含#标签，但保留接口一致性
        return title_text, None


class BilibiliLinkParser:
    """Bilibili链接解析器 - 对外接口"""

    def __init__(self):
        self._parser = _BilibiliParserCore()

    def extract_url(self, text: str) -> str:
        """从分享文本中提取Bilibili链接"""
        return self._parser.extract_url(text)

    def parse(self, url: str) -> dict:
        """解析Bilibili链接，获取视频信息"""
        return self._parser.parse(url)

    def parse_title_and_tag(self, title_text: str) -> Tuple[str, Optional[str]]:
        """解析标题和标签，返回 (title, tag)"""
        return self._parser.parse_title_and_tag(title_text)
