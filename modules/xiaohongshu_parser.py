"""小红书链接解析模块 - 小红书笔记链接解析功能"""

import json
import os
import re
import sys
from urllib.parse import unquote, urlparse, parse_qs
import requests

# 全局调试模式
DEBUG_MODE = os.environ.get('XHS_DEBUG', 'False').lower() in ('true', '1', 'yes')


class _XiaohongshuParserCore:
    """小红书解析器核心类

    使用HTTP请求直接获取页面HTML，从SSR渲染的 __INITIAL_STATE__ 中提取数据。
    无需浏览器自动化，避免了反爬检测问题。
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.xiaohongshu.com',
    }

    def __init__(self):
        # 定义字段分类映射
        self.field_categories = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'images', 'final_url'],
            'content': ['title', 'desc', 'tag', 'note_type'],
            'author_info': ['author', 'author_id'],
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],
            'video_detail': ['duration', 'video_id', 'create_time'],
            'music_info': ['music'],
        }

        self.category_order = ['status', 'urls', 'content', 'author_info', 'statistics', 'video_detail', 'music_info', 'debug']

        self.field_order = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'images', 'final_url'],
            'content': ['title', 'desc', 'tag', 'note_type'],
            'author_info': ['author', 'author_id'],
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],
            'video_detail': ['duration', 'video_id', 'create_time'],
            'music_info': ['music'],
            'debug': ['debug'],
        }

    def _organize_result(self, data: dict) -> dict:
        """将扁平的数据组织为层级结构"""
        organized = {}

        field_to_category = {}
        for category, fields in self.field_categories.items():
            for field in fields:
                field_to_category[field] = category

        for category in self.category_order:
            category_data = {}
            if category in self.field_order:
                for field in self.field_order[category]:
                    if field in data:
                        category_data[field] = data[field]
            if category_data:
                organized[category] = category_data

        for key, value in data.items():
            if key not in field_to_category:
                if 'other' not in organized:
                    organized['other'] = {}
                organized['other'][key] = value

        return organized

    def extract_url(self, text: str) -> str:
        """从分享文本中提取小红书链接

        Args:
            text: 分享文本，可能包含链接

        Returns:
            str: 提取到的链接，如果没有找到则返回原文本
        """
        patterns = [
            r'https?://xhslink\.com/[a-zA-Z0-9/]+',
            r'https?://www\.xiaohongshu\.com/explore/[a-zA-Z0-9]+',
            r'https?://www\.xiaohongshu\.com/discovery/item/[a-zA-Z0-9]+',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return text.strip()

    def _resolve_short_url(self, url: str) -> str:
        """通过HTTP重定向解析短链接，获取最终URL（含xsec_token等参数）"""
        if 'xhslink.com' not in url:
            return url

        try:
            response = requests.get(url, headers=self.HEADERS, allow_redirects=True, timeout=15)
            if response.url != url:
                if DEBUG_MODE:
                    print(f"[DEBUG] 短链接重定向: {response.url}", file=sys.stderr)
                return response.url
        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 解析短链接失败: {e}", file=sys.stderr)

        return url

    def parse(self, url: str) -> dict:
        """解析小红书链接，获取笔记信息

        Args:
            url: 小红书链接（短链接或完整链接）

        Returns:
            dict: 层级化的笔记信息
        """
        try:
            # 1. 解析短链接
            resolved_url = self._resolve_short_url(url)
            note_id = self._extract_note_id(resolved_url)

            if not note_id:
                return self._organize_result({
                    'success': False,
                    'error': '无法从URL中提取笔记ID'
                })

            # 2. 构造explore URL（保留query参数，特别是xsec_token）
            parsed = urlparse(resolved_url)
            explore_url = f'https://www.xiaohongshu.com/explore/{note_id}'
            if parsed.query:
                explore_url += f'?{parsed.query}'

            if DEBUG_MODE:
                print(f"[DEBUG] 请求URL: {explore_url[:120]}", file=sys.stderr)

            # 3. HTTP请求获取页面HTML
            response = requests.get(explore_url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            html = response.text

            if DEBUG_MODE:
                try:
                    with open('debug_xhs_page.html', 'w', encoding='utf-8') as f:
                        f.write(html[:200000])
                    print("[DEBUG] 已保存页面HTML到 debug_xhs_page.html", file=sys.stderr)
                except Exception:
                    pass

            # 4. 从 __INITIAL_STATE__ 提取数据
            page_data = self._extract_initial_state(html)
            # 同时提取meta标签数据作为补充
            meta_data = self._extract_from_html(html, note_id)

            if page_data:
                if DEBUG_MODE:
                    try:
                        with open('debug_xhs_data.json', 'w', encoding='utf-8') as f:
                            json.dump(page_data, f, ensure_ascii=False, indent=2)
                        print("[DEBUG] 已保存INITIAL_STATE", file=sys.stderr)
                    except Exception:
                        pass

                result = self._extract_from_page_data(page_data, note_id)
                if result.get('success'):
                    # 用meta标签数据补充SSR中缺失的字段（如封面URL）
                    if not result.get('cover_url') and meta_data.get('cover_url'):
                        result['cover_url'] = meta_data['cover_url']
                    if not result.get('video_url') and meta_data.get('video_url'):
                        result['video_url'] = meta_data['video_url']
                        result['audio_url'] = meta_data['video_url']
                    result['final_url'] = explore_url.split('?')[0]
                    return self._organize_result(result)

            # 5. 回退到HTML meta标签提取
            meta_data['final_url'] = explore_url.split('?')[0]
            return self._organize_result(meta_data)

        except requests.RequestException as e:
            return self._organize_result({
                'success': False,
                'error': f'请求失败: {str(e)}'
            })
        except Exception as e:
            return self._organize_result({
                'success': False,
                'error': f'解析异常: {str(e)}'
            })

    def _extract_note_id(self, url: str) -> str:
        """从URL中提取笔记ID"""
        patterns = [
            r'/explore/([a-zA-Z0-9]+)',
            r'/discovery/item/([a-zA-Z0-9]+)',
            r'/note/([a-zA-Z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _extract_initial_state(self, html: str) -> dict:
        """从页面script标签中提取 __INITIAL_STATE__ 数据"""
        patterns = [
            r'<script>window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>',
            r'<script>window\.__INITIAL_SSR_STATE__\s*=\s*(\{.+?\})\s*</script>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                json_str = match.group(1)
                # 小红书的 __INITIAL_STATE__ 中 undefined 需要替换为 null
                json_str = re.sub(r'\bundefined\b', 'null', json_str)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    if DEBUG_MODE:
                        print("[DEBUG] JSON解析失败，尝试清理后重试", file=sys.stderr)
                    try:
                        json_str = re.sub(r',\s*}', '}', json_str)
                        json_str = re.sub(r',\s*]', ']', json_str)
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue

        return None

    def _extract_from_page_data(self, data: dict, note_id: str = None) -> dict:
        """从页面 __INITIAL_STATE__ 数据中提取笔记信息"""
        note_detail_map = data.get('note', {}).get('noteDetailMap', {})

        note_data = None
        if note_id and note_id in note_detail_map:
            note_data = note_detail_map[note_id].get('note')
        else:
            for key, value in note_detail_map.items():
                if key == 'null':
                    continue
                if isinstance(value, dict) and 'note' in value:
                    note_data = value['note']
                    break

        if not note_data:
            note_data = data.get('noteData') or data.get('note', {}).get('note')

        if not note_data:
            return {'success': False}

        return self._extract_from_note_card(note_data, note_id)

    def _extract_from_note_card(self, note_card: dict, note_id: str = None) -> dict:
        """从笔记数据中提取信息

        Args:
            note_card: 笔记数据字典
            note_id: 笔记ID

        Returns:
            dict: 扁平化的笔记信息
        """
        result = {'success': True}

        # 笔记类型
        note_type_str = note_card.get('type', '')
        if note_type_str == 'video':
            result['note_type'] = 'video'
        else:
            result['note_type'] = 'image'

        # 标题和描述
        result['title'] = note_card.get('title') or ''
        result['desc'] = note_card.get('desc') or ''

        if not result['title'] and result['desc']:
            first_line = result['desc'].split('\n')[0]
            result['title'] = first_line[:50] if len(first_line) > 50 else first_line

        # 作者信息
        user = note_card.get('user', {})
        if user:
            result['author'] = user.get('nickname') or user.get('name')
            result['author_id'] = user.get('userId') or user.get('uid') or user.get('user_id')

        # 统计数据
        interact_info = note_card.get('interactInfo') or note_card.get('interact_info') or {}
        if interact_info:
            result['like_count'] = self._parse_count(interact_info.get('likedCount') or interact_info.get('liked_count'))
            result['comment_count'] = self._parse_count(interact_info.get('commentCount') or interact_info.get('comment_count'))
            result['share_count'] = self._parse_count(interact_info.get('shareCount') or interact_info.get('share_count'))
            result['collect_count'] = self._parse_count(interact_info.get('collectedCount') or interact_info.get('collected_count'))

        # 笔记ID
        result['video_id'] = note_card.get('noteId') or note_card.get('note_id') or note_id

        # 创建时间
        result['create_time'] = note_card.get('time') or note_card.get('create_time')

        # 标签
        tag_list = note_card.get('tagList') or note_card.get('tag_list') or []
        if tag_list:
            tags = [t.get('name', '') for t in tag_list if isinstance(t, dict) and t.get('name')]
            if tags:
                result['tag'] = ' 、'.join(tags)

        # 视频笔记：提取视频URL和封面
        if result['note_type'] == 'video':
            video = note_card.get('video', {})
            if video:
                # 视频URL - 从stream中提取
                media = video.get('media', {})
                if media:
                    stream = media.get('stream', {})
                    for quality in ['h264', 'h265', 'av1']:
                        streams = stream.get(quality, [])
                        if streams and isinstance(streams, list):
                            for s in streams:
                                master_url = s.get('masterUrl') or s.get('master_url')
                                if master_url:
                                    result['video_url'] = master_url
                                    break
                            if result.get('video_url'):
                                break

                # 备用：从consumer获取
                if not result.get('video_url'):
                    consumer = video.get('consumer', {})
                    if consumer:
                        origin = consumer.get('originVideoKey')
                        if origin:
                            result['video_url'] = f'https://sns-video-bd.xhscdn.com/{origin}'

                if not result.get('video_url'):
                    result['video_url'] = video.get('url')

                # 小红书视频音视频合一
                if result.get('video_url'):
                    result['audio_url'] = result['video_url']

                # 视频时长（毫秒）
                duration = video.get('duration')
                if duration:
                    result['duration'] = duration

                # 封面
                cover = video.get('image', {})
                if isinstance(cover, dict):
                    info_list = cover.get('infoList') or cover.get('info_list') or []
                    if info_list:
                        result['cover_url'] = info_list[-1].get('url')
                    elif cover.get('url'):
                        result['cover_url'] = cover['url']

        # 图文笔记：提取图片列表和封面
        if result['note_type'] == 'image':
            image_list = note_card.get('imageList') or note_card.get('image_list') or []
            if image_list:
                images = []
                for img in image_list:
                    info_list = img.get('infoList') or img.get('info_list') or []
                    if info_list:
                        images.append(info_list[-1].get('url'))
                    elif img.get('url'):
                        images.append(img['url'])
                    elif img.get('urlDefault') or img.get('url_default'):
                        images.append(img.get('urlDefault') or img.get('url_default'))

                if images:
                    result['images'] = images
                    result['cover_url'] = images[0]

        # 封面回退：从顶层 cover 字段提取
        if not result.get('cover_url'):
            cover = note_card.get('cover', {})
            if isinstance(cover, dict):
                info_list = cover.get('infoList') or cover.get('info_list') or []
                if info_list:
                    result['cover_url'] = info_list[-1].get('url')
                elif cover.get('url'):
                    result['cover_url'] = cover['url']

        # 音乐信息
        music = note_card.get('music', {})
        if music and isinstance(music, dict):
            result['music'] = music.get('name') or music.get('title')

        return result

    def _parse_count(self, value) -> int:
        """解析统计数字，小红书可能返回字符串如 '1.2万'"""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                match = re.match(r'([\d.]+)\s*万', value)
                if match:
                    return int(float(match.group(1)) * 10000)
                return None
        return None

    def _extract_from_html(self, html: str, note_id: str = None) -> dict:
        """从HTML meta标签中提取笔记信息（回退方案）"""
        result = {'success': False}

        title_match = re.search(r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"', html)
        if not title_match:
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
        if title_match:
            result['title'] = title_match.group(1).strip()
            result['title'] = re.sub(r'\s*[-|]\s*小红书.*$', '', result['title'])

        desc_match = re.search(r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"', html)
        if desc_match:
            result['desc'] = desc_match.group(1).strip()

        image_match = re.search(r'<meta\s+(?:property|name)="og:image"\s+content="([^"]*)"', html)
        if image_match:
            result['cover_url'] = image_match.group(1)

        video_match = re.search(r'<meta\s+(?:property|name)="og:video"\s+content="([^"]*)"', html)
        if video_match:
            result['video_url'] = video_match.group(1)
            result['audio_url'] = result['video_url']
            result['note_type'] = 'video'
        else:
            result['note_type'] = 'image'
            img_urls = re.findall(r'<meta\s+(?:property|name)="og:image"\s+content="([^"]*)"', html)
            if img_urls:
                result['images'] = img_urls

        if note_id:
            result['video_id'] = note_id

        if result.get('title'):
            result['success'] = True

        return result

    def _parse_title_and_tag(self, title_text: str) -> tuple:
        """解析标题和标签

        小红书标题中常见 #标签 和 [话题] 格式
        """
        tags = []

        hash_tags = re.findall(r'#(\S+?)(?:\s|#|$)', title_text)
        tags.extend(hash_tags)

        bracket_tags = re.findall(r'\[([^\]]+)\]', title_text)
        tags.extend(bracket_tags)

        if tags:
            title = re.sub(r'#\S+', '', title_text)
            title = re.sub(r'\[[^\]]+\]', '', title)
            title = title.strip()
            title = re.sub(r'\s*[，、。,]*$', '', title)
            tag = ' 、'.join(tags)
            return title, tag
        else:
            return title_text, None


class XiaohongshuLinkParser:
    """小红书链接解析器 - 对外接口"""

    def __init__(self):
        self._parser = _XiaohongshuParserCore()

    def extract_url(self, text: str) -> str:
        """从分享文本中提取小红书链接"""
        return self._parser.extract_url(text)

    def parse(self, url: str) -> dict:
        """解析小红书链接，获取笔记信息"""
        return self._parser.parse(url)

    def parse_title_and_tag(self, title_text: str) -> tuple:
        """解析标题和标签，返回 (title, tag)"""
        return self._parser._parse_title_and_tag(title_text)
