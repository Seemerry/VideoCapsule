"""快手链接解析模块 - 快手视频链接解析功能"""

import asyncio
import json
import os
import re
import sys
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# 全局调试模式
DEBUG_MODE = os.environ.get('KUAISHOU_DEBUG', 'False').lower() in ('true', '1', 'yes')


class _KuaishouParserCore:
    """快手解析器核心类

    使用 Playwright 浏览器自动化获取cookies，
    然后通过 GraphQL API 获取视频元数据。
    快手页面是纯 SPA，无 SSR 数据，所有视频数据通过 GraphQL 获取。
    """

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.kuaishou.com',
    }

    # GraphQL query matching Kuaishou's actual schema
    # Note: VisionVideoDetailPhoto does NOT have commentCount field;
    # comment count comes from the separate commentListQuery
    GRAPHQL_QUERY = """query visionVideoDetail($photoId: String, $type: String, $page: String, $webPageArea: String) {
  visionVideoDetail(photoId: $photoId, type: $type, page: $page, webPageArea: $webPageArea) {
    status
    type
    author {
      id
      name
      headerUrl
      __typename
    }
    photo {
      id
      duration
      caption
      likeCount
      viewCount
      realLikeCount
      coverUrl
      photoUrl
      photoH265Url
      manifest {
        adaptationSet {
          id
          duration
          representation {
            id
            url
            width
            height
            qualityLabel
            __typename
          }
          __typename
        }
        __typename
      }
      videoResource
      timestamp
      __typename
    }
    tags {
      type
      name
      __typename
    }
    __typename
  }
}"""

    def __init__(self):
        # 定义字段分类映射
        self.field_categories = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'final_url'],
            'content': ['title', 'desc', 'tag'],
            'author_info': ['author', 'author_id'],
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],
            'video_detail': ['duration', 'video_id', 'create_time'],
            'music_info': ['music'],
        }

        self.category_order = ['status', 'urls', 'content', 'author_info', 'statistics', 'video_detail', 'music_info', 'debug']

        self.field_order = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'final_url'],
            'content': ['title', 'desc', 'tag'],
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
        """从分享文本中提取快手链接

        Args:
            text: 分享文本，可能包含链接

        Returns:
            str: 提取到的链接，如果没有找到则返回原文本
        """
        patterns = [
            r'https?://v\.kuaishou\.com/[a-zA-Z0-9_\-]+',
            r'https?://www\.kuaishou\.com/short-video/[a-zA-Z0-9_\-]+',
            r'https?://www\.kuaishou\.com/f/[a-zA-Z0-9_\-]+',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)

        return text.strip()

    def _extract_photo_id(self, url: str) -> str:
        """从URL中提取视频ID（photoId）"""
        patterns = [
            r'/short-video/([a-zA-Z0-9_\-]+)',
            r'/f/([a-zA-Z0-9_\-]+)',
            r'/photo/([a-zA-Z0-9_\-]+)',
            r'/video/([a-zA-Z0-9_\-]+)',
        ]
        # 也支持从query参数中提取
        parsed = urlparse(url)
        if parsed.query:
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            if 'photoId' in params:
                return params['photoId'][0]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def parse_async(self, url: str) -> dict:
        """异步解析快手链接，获取视频信息

        Args:
            url: 快手链接（短链接或完整链接）

        Returns:
            dict: 层级化的视频信息
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.HEADERS['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            try:
                if DEBUG_MODE:
                    print(f"[DEBUG] 访问URL: {url}", file=sys.stderr)

                # 收集页面自动发起的GraphQL请求和响应
                captured_exchanges = []

                async def handle_route(route, request):
                    """捕获GraphQL请求体和响应"""
                    try:
                        post_data = request.post_data
                        response = await route.fetch()
                        if response.ok:
                            body = await response.body()
                            captured_exchanges.append({
                                'request': post_data,
                                'response': body.decode('utf-8')
                            })
                            if DEBUG_MODE:
                                op_name = 'unknown'
                                if post_data:
                                    try:
                                        op_name = json.loads(post_data).get('operationName', 'unknown')
                                    except Exception:
                                        pass
                                print(f"[DEBUG] 捕获GraphQL: {op_name}", file=sys.stderr)
                    except Exception as e:
                        if DEBUG_MODE:
                            print(f"[DEBUG] 捕获GraphQL失败: {e}", file=sys.stderr)
                    await route.continue_()

                await page.route('**/graphql**', handle_route)

                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except PlaywrightTimeoutError:
                    if DEBUG_MODE:
                        print("[DEBUG] 页面加载超时，继续处理", file=sys.stderr)

                # 等待页面加载和API请求完成
                await asyncio.sleep(5)

                final_url = page.url
                if DEBUG_MODE:
                    html = await page.content()
                    try:
                        with open('debug_kuaishou_page.html', 'w', encoding='utf-8') as f:
                            f.write(html[:200000])
                        print("[DEBUG] 已保存页面HTML到 debug_kuaishou_page.html", file=sys.stderr)
                    except Exception:
                        pass

                # 提取 photoId
                photo_id = self._extract_photo_id(final_url)
                if not photo_id:
                    photo_id = self._extract_photo_id(url)

                if DEBUG_MODE:
                    print(f"[DEBUG] photoId: {photo_id}, finalUrl: {final_url[:120]}", file=sys.stderr)

                if not photo_id:
                    return self._organize_result({
                        'success': False,
                        'error': '无法从URL中提取视频ID'
                    })

                # 从捕获的响应中提取评论数
                comment_count = None
                for exchange in captured_exchanges:
                    try:
                        req_data = json.loads(exchange['request']) if exchange['request'] else {}
                        if req_data.get('operationName') == 'commentListQuery':
                            resp_data = json.loads(exchange['response'])
                            comment_list = resp_data.get('data', {}).get('visionCommentList', {})
                            comment_count = comment_list.get('commentCountV2') or comment_list.get('commentCount')
                            if DEBUG_MODE:
                                print(f"[DEBUG] 从commentListQuery获取评论数: {comment_count}", file=sys.stderr)
                    except Exception:
                        pass

                # 主动调用 visionVideoDetail GraphQL API
                result = await self._fetch_via_graphql(page, photo_id)
                if result and result.get('success'):
                    result['final_url'] = final_url
                    # 补充评论数（visionVideoDetail不返回commentCount）
                    if comment_count is not None and not result.get('comment_count'):
                        result['comment_count'] = self._parse_count(comment_count)
                    return self._organize_result(result)

                # 回退：从捕获的 visionShortVideoReco 响应中查找目标视频
                for exchange in captured_exchanges:
                    try:
                        req_data = json.loads(exchange['request']) if exchange['request'] else {}
                        if req_data.get('operationName') == 'visionShortVideoReco':
                            resp_data = json.loads(exchange['response'])
                            feeds = resp_data.get('data', {}).get('visionShortVideoReco', {}).get('feeds', [])
                            for feed in feeds:
                                photo = feed.get('photo', {})
                                if photo.get('id') == photo_id:
                                    if DEBUG_MODE:
                                        print(f"[DEBUG] 从visionShortVideoReco中找到目标视频", file=sys.stderr)
                                    result = self._extract_from_feed(feed)
                                    if result and result.get('success'):
                                        result['final_url'] = final_url
                                        if comment_count is not None and not result.get('comment_count'):
                                            result['comment_count'] = self._parse_count(comment_count)
                                        return self._organize_result(result)
                    except Exception:
                        pass

                # 最终回退：返回只有基本信息的结果
                return self._organize_result({
                    'success': False,
                    'error': 'GraphQL API 未返回视频数据',
                    'final_url': final_url,
                    'video_id': photo_id,
                })

            except Exception as e:
                return self._organize_result({
                    'success': False,
                    'error': f'解析异常: {str(e)}'
                })
            finally:
                await browser.close()

    async def _fetch_via_graphql(self, page, photo_id: str) -> dict:
        """通过 GraphQL API 获取视频详情

        使用 Playwright 的 page.evaluate 发起请求，自动携带浏览器cookies。
        """
        try:
            response_text = await page.evaluate("""
                async (params) => {
                    const response = await fetch('https://www.kuaishou.com/graphql', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            operationName: 'visionVideoDetail',
                            variables: {
                                photoId: params.photoId,
                                type: '1',
                                page: 'detail',
                            },
                            query: params.query,
                        }),
                        credentials: 'include',
                    });
                    return await response.text();
                }
            """, {'photoId': photo_id, 'query': self.GRAPHQL_QUERY})

            if DEBUG_MODE:
                try:
                    with open('debug_kuaishou_graphql.json', 'w', encoding='utf-8') as f:
                        f.write(response_text)
                    print("[DEBUG] 已保存GraphQL响应到 debug_kuaishou_graphql.json", file=sys.stderr)
                except Exception:
                    pass

            data = json.loads(response_text)
            return self._extract_from_graphql_response(data)

        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] GraphQL API 调用失败: {e}", file=sys.stderr)
            return None

    def _extract_from_graphql_response(self, data: dict) -> dict:
        """从 visionVideoDetail GraphQL 响应中提取视频信息"""
        try:
            video_detail = data.get('data', {}).get('visionVideoDetail', {})
            if not video_detail:
                if DEBUG_MODE and data.get('errors'):
                    print(f"[DEBUG] GraphQL错误: {data['errors']}", file=sys.stderr)
                return None

            photo = video_detail.get('photo')
            author = video_detail.get('author')

            if not photo:
                return None

            result = {'success': True}

            # 标题
            result['title'] = photo.get('caption') or ''

            # 视频URL - 快手音视频合一
            video_url = photo.get('photoUrl')
            if video_url:
                result['video_url'] = video_url
                result['audio_url'] = video_url

            # 封面
            cover_url = photo.get('coverUrl')
            if cover_url:
                result['cover_url'] = cover_url

            # 作者信息
            if author:
                result['author'] = author.get('name')
                result['author_id'] = author.get('id')

            # 统计数据
            result['like_count'] = self._parse_count(photo.get('realLikeCount') or photo.get('likeCount'))
            # commentCount 不在 visionVideoDetail 中，由调用方从 commentListQuery 补充
            result['comment_count'] = None
            # 快手无分享数，用播放数替代
            result['share_count'] = self._parse_count(photo.get('viewCount'))
            result['collect_count'] = None

            # 视频ID
            result['video_id'] = photo.get('id')

            # 创建时间（毫秒转秒）
            timestamp = photo.get('timestamp')
            if timestamp:
                result['create_time'] = timestamp // 1000 if timestamp > 9999999999 else timestamp

            # 时长（毫秒）
            duration = photo.get('duration')
            if duration:
                result['duration'] = duration

            # 标签
            tags_data = video_detail.get('tags', [])
            if tags_data:
                tag_names = [t.get('name', '') for t in tags_data if isinstance(t, dict) and t.get('name')]
                if tag_names:
                    result['tag'] = ' 、'.join(tag_names)

            # 从manifest中尝试获取更高质量的视频URL
            manifest = photo.get('manifest')
            if manifest and isinstance(manifest, dict):
                adaptation_set = manifest.get('adaptationSet', [])
                if adaptation_set:
                    best_url = None
                    best_width = 0
                    for adapt in adaptation_set:
                        representations = adapt.get('representation', [])
                        for rep in representations:
                            width = rep.get('width', 0)
                            if width > best_width and rep.get('url'):
                                best_width = width
                                best_url = rep['url']
                    if best_url:
                        result['video_url'] = best_url
                        result['audio_url'] = best_url

            return result

        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 解析GraphQL响应失败: {e}", file=sys.stderr)
            return None

    def _extract_from_feed(self, feed: dict) -> dict:
        """从 visionShortVideoReco 的单个 feed 中提取视频信息"""
        try:
            photo = feed.get('photo', {})
            author = feed.get('author', {})

            if not photo:
                return None

            result = {'success': True}

            result['title'] = photo.get('caption') or ''

            video_url = photo.get('photoUrl')
            if video_url:
                result['video_url'] = video_url
                result['audio_url'] = video_url

            cover_url = photo.get('coverUrl')
            if cover_url:
                result['cover_url'] = cover_url

            if author:
                result['author'] = author.get('name')
                result['author_id'] = author.get('id')

            result['like_count'] = self._parse_count(photo.get('realLikeCount') or photo.get('likeCount'))
            result['comment_count'] = None
            result['share_count'] = self._parse_count(photo.get('viewCount'))
            result['collect_count'] = None

            result['video_id'] = photo.get('id')

            timestamp = photo.get('timestamp')
            if timestamp:
                result['create_time'] = timestamp // 1000 if timestamp > 9999999999 else timestamp

            duration = photo.get('duration')
            if duration:
                result['duration'] = duration

            # 标签
            tags_data = feed.get('tags', [])
            if tags_data:
                tag_names = [t.get('name', '') for t in tags_data if isinstance(t, dict) and t.get('name')]
                if tag_names:
                    result['tag'] = ' 、'.join(tag_names)

            return result

        except Exception as e:
            if DEBUG_MODE:
                print(f"[DEBUG] 解析feed失败: {e}", file=sys.stderr)
            return None

    def _extract_from_html(self, html: str, photo_id: str = None) -> dict:
        """从HTML meta标签中提取视频信息（回退方案）"""
        result = {'success': False}

        title_match = re.search(r'<meta\s+(?:property|name)="og:title"\s+content="([^"]*)"', html)
        if not title_match:
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
        if title_match:
            result['title'] = title_match.group(1).strip()
            result['title'] = re.sub(r'\s*[-|]\s*快手.*$', '', result['title'])

        desc_match = re.search(r'<meta\s+(?:property|name)="og:description"\s+content="([^"]*)"', html)
        if desc_match:
            result['desc'] = desc_match.group(1).strip()

        image_match = re.search(r'<meta\s+(?:property|name)="og:image"\s+content="([^"]*)"', html)
        if image_match:
            result['cover_url'] = image_match.group(1)

        video_match = re.search(r'<meta\s+(?:property|name)="og:video"\s+content="([^"]*)"', html)
        if not video_match:
            video_match = re.search(r'<meta\s+(?:property|name)="og:video:url"\s+content="([^"]*)"', html)
        if video_match:
            result['video_url'] = video_match.group(1)
            result['audio_url'] = result['video_url']

        if photo_id:
            result['video_id'] = photo_id

        if result.get('title') or result.get('video_url'):
            result['success'] = True

        return result

    def _parse_title_and_tag(self, title_text: str) -> tuple:
        """解析标题和标签

        快手标题中常见 #标签 格式

        Args:
            title_text: 原始标题文本

        Returns:
            tuple: (title, tag)
        """
        tag_pattern = r'#(\S+)'
        tags = re.findall(tag_pattern, title_text)

        if tags:
            title = re.sub(tag_pattern, '', title_text).strip()
            title = re.sub(r'\s*[，、。,]*$', '', title)
            tag = ' 、'.join(tags)
            return title, tag
        else:
            return title_text, None

    def _parse_count(self, value) -> int:
        """解析统计数字，处理 '1.2万' 格式"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
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

    def parse(self, url: str) -> dict:
        """同步解析快手链接"""
        return asyncio.run(self.parse_async(url))


class KuaishouLinkParser:
    """快手链接解析器 - 对外接口"""

    def __init__(self):
        self._parser = _KuaishouParserCore()

    def extract_url(self, text: str) -> str:
        """从分享文本中提取快手链接"""
        return self._parser.extract_url(text)

    def parse(self, url: str) -> dict:
        """解析快手链接，获取视频信息"""
        return self._parser.parse(url)

    def parse_title_and_tag(self, title_text: str) -> tuple:
        """解析标题和标签，返回 (title, tag)"""
        return self._parser._parse_title_and_tag(title_text)
