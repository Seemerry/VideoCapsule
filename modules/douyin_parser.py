"""链接解析模块 - 抖音视频链接解析功能"""

import asyncio
import json
import os
import re
import sys
from urllib.parse import unquote
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# 全局调试模式
DEBUG_MODE = os.environ.get('DOUYIN_DEBUG', 'False').lower() in ('true', '1', 'yes')


class _DouyinParserCore:
    """抖音解析器核心类"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        # 定义字段分类映射
        self.field_categories = {
            # 状态和错误信息
            'status': ['success', 'error'],

            # URL链接
            'urls': ['video_url', 'audio_url', 'cover_url', 'short_url', 'final_url'],

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
        self.category_order = ['status', 'urls', 'content', 'author_info', 'statistics', 'video_detail', 'music_info', 'debug']

        # 定义每个分类内字段的顺序
        self.field_order = {
            'status': ['success', 'error'],
            'urls': ['video_url', 'audio_url', 'cover_url', 'short_url', 'final_url'],
            'content': ['title', 'desc', 'tag'],
            'author_info': ['author', 'author_id'],
            'statistics': ['like_count', 'comment_count', 'share_count', 'collect_count'],
            'video_detail': ['duration', 'video_id', 'create_time'],
            'music_info': ['music'],
            'debug': ['debug'],
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
                # 如果还没有other分类，创建一个
                if 'other' not in organized:
                    organized['other'] = {}
                organized['other'][key] = value

        return organized

    def extract_url(self, text: str) -> str:
        """
        从分享文本中提取抖音短链接

        Args:
            text: 分享文本，可能包含链接

        Returns:
            str: 提取到的短链接，如果没有找到则返回原文本
        """
        # 匹配抖音短链接的各种格式
        patterns = [
            r'https?://v\.douyin\.com/[a-zA-Z0-9_\-]+/?',  # 标准短链接（包含下划线和连字符）
            r'https?://www\.douyin\.com/video/\d+',  # 完整视频链接
            r'https?://www\.iesdouyin\.com/share/video/\d+',  # 旧版分享链接
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                url = match.group(0)
                # 确保URL以/结尾（短链接标准格式）
                if url.startswith('https://v.douyin.com/') and not url.endswith('/'):
                    url += '/'
                return url

        # 如果没有匹配到，检查是否是纯短链接代码
        if re.match(r'^[a-zA-Z0-9_\-]+$', text.strip()):
            return f'https://v.douyin.com/{text.strip()}/'

        # 如果都没有，返回原文本（假设它已经是URL）
        return text.strip()

    async def parse_async(self, short_url: str) -> dict:
        """
        异步解析抖音短链接

        Args:
            short_url: 抖音短链接

        Returns:
            dict: 解析结果
        """
        async with async_playwright() as p:
            # 使用chromium浏览器
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.headers['User-Agent'],
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            try:
                # 监听网络请求
                video_url_from_network = []
                api_responses = []

                async def handle_route(route, request):
                    # 捕获API请求
                    url = request.url
                    if '/aweme/v1/web/aweme/detail' in url or '/aweme/v1/web/aweme/detailinfo' in url:
                        try:
                            # 继续请求并获取响应
                            response = await route.fetch()
                            if response.ok:
                                body = await response.body()
                                api_responses.append({
                                    'url': url,
                                    'body': body.decode('utf-8')
                                })
                                if DEBUG_MODE:
                                    print(f"[DEBUG] 捕获API响应: {url}", file=sys.stderr)
                        except Exception as e:
                            if DEBUG_MODE:
                                print(f"[DEBUG] 捕获API失败: {e}", file=sys.stderr)

                    # 继续原始请求
                    await route.continue_()

                # 只监听API请求 - 使用更通用的模式
                await page.route('**/aweme/v1/web/aweme/detail/**', handle_route)
                await page.route('**/aweme/v1/web/aweme/detailinfo/**', handle_route)

                # 监听所有请求以捕获视频URL
                def handle_request(request):
                    url = request.url
                    # 捕获包含视频特征的URL
                    if any(keyword in url for keyword in ['.mp4', 'video', 'douyinvod']):
                        if ('.mp4' in url or 'douyinvod' in url) and 'temp=' in url:
                            video_url_from_network.append(url)

                page.on('request', handle_request)

                # 访问短链接，增加超时时间到60秒
                await page.goto(short_url, wait_until='domcontentloaded', timeout=60000)

                # 等待页面加载完成，等待API响应
                await asyncio.sleep(10)

                # 获取页面内容
                content = await page.content()
                final_url = page.url

                # 尝试从API响应中提取视频信息
                api_video_info = {}
                if api_responses:
                    if DEBUG_MODE:
                        print(f"[DEBUG] 捕获到 {len(api_responses)} 个API响应", file=sys.stderr)
                    for resp in api_responses:
                        try:
                            api_data = json.loads(resp['body'])  # body已经是字符串
                            if DEBUG_MODE:
                                with open('debug_api_response.json', 'w', encoding='utf-8') as f:
                                    json.dump(api_data, f, ensure_ascii=False, indent=2)
                                print("[DEBUG] 已保存API响应到 debug_api_response.json", file=sys.stderr)

                            # 从API响应中提取信息
                            api_video_info = self._extract_from_api_response(api_data)
                            if api_video_info:
                                if DEBUG_MODE:
                                    print(f"[DEBUG] 从API提取到信息: {api_video_info}", file=sys.stderr)
                                break
                        except Exception as e:
                            if DEBUG_MODE:
                                print(f"[DEBUG] 解析API响应失败: {e}", file=sys.stderr)
                                import traceback
                                traceback.print_exc(file=sys.stderr)
                            continue

                # 优先使用从网络请求捕获的视频URL
                if video_url_from_network:
                    # 使用第一个捕获到的视频URL
                    video_url = video_url_from_network[0]
                    title = self._extract_title(content)
                    video_info = self._extract_video_info(content)

                    # 合并API数据和HTML提取的数据
                    video_info.update(api_video_info)

                    result = {
                        'success': True,
                        'video_url': video_url,
                        'title': title,
                        'final_url': final_url,
                        **video_info  # 展开所有提取的视频信息
                    }

                    # 组织为层级结构
                    return self._organize_result(result)

                # 如果网络请求没有捕获到，尝试从页面内容中提取
                video_url = self._extract_video_url(content)

                if video_url:
                    title = self._extract_title(content)
                    video_info = self._extract_video_info(content)
                    result = {
                        'success': True,
                        'video_url': video_url,
                        'title': title,
                        'final_url': final_url,
                        **video_info  # 展开所有提取的视频信息
                    }
                    return self._organize_result(result)

                # 无法提取视频URL，返回错误
                result = {
                    'success': False,
                    'error': '无法从页面中提取视频URL',
                    'debug': {
                        'final_url': final_url,
                        'content_length': len(content)
                    }
                }
                return self._organize_result(result)

            except PlaywrightTimeoutError:
                result = {
                    'success': False,
                    'error': '页面加载超时'
                }
                return self._organize_result(result)
            except Exception as e:
                result = {
                    'success': False,
                    'error': f'解析异常: {str(e)}'
                }
                return self._organize_result(result)
            finally:
                await browser.close()

    def parse(self, short_url: str) -> dict:
        """
        同步解析抖音短链接

        Args:
            short_url: 抖音短链接

        Returns:
            dict: 解析结果
        """
        return asyncio.run(self.parse_async(short_url))

    def _extract_video_url(self, html: str) -> str:
        """从HTML中提取视频URL"""
        # 方法1: 尝试匹配 "playAddr" 字段
        patterns = [
            r'"playAddr":"([^"]+)"',
            r'playAddr["\s:]+(https?://[^"]+?video[^"]+?)["\s,}]',
            r'"video_url":"([^"]+)"',
            r'video_url["\s:]+(https?://[^"]+?video[^"]+?)["\s,}]',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                url = match.group(1).replace('\\u002F', '/').replace('\\', '')
                return unquote(url)

        # 方法2: 查找所有HTTP URL，过滤包含video的
        pattern = r'https?://[^\s"\'<>]+video[^\s"\'<>]*'
        matches = re.findall(pattern, html)
        for match in matches:
            url = match.replace('\\u002F', '/').replace('\\', '')
            if 'douyinvod.com' in url or 'douyin.com' in url:
                return unquote(url)

        return None

    def _extract_title(self, html: str) -> str:
        """从HTML中提取视频标题"""
        patterns = [
            r'<title[^>]*>([^<]+)</title>',
            r'"desc":"([^"]+)"',
            r'"title":"([^"]+)"'
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                title = match.group(1)
                title = re.sub(r'\s*-\s*抖音.*$', '', title)
                return title.strip()

        return "未知标题"

    def _extract_video_info(self, html: str) -> dict:
        """
        从HTML中提取视频信息（简化版，作为API的后备）

        Args:
            html: 页面HTML内容

        Returns:
            dict: 包含视频信息的字典
        """
        info = {}

        # 调试模式：保存HTML内容
        if DEBUG_MODE:
            try:
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(html[:100000])
                print("[DEBUG] 已保存页面HTML到 debug_page.html", file=sys.stderr)
            except Exception as e:
                print(f"[DEBUG] 保存HTML失败: {e}", file=sys.stderr)

        # 尝试从script标签中的JSON数据提取（作为后备）
        script_data = self._extract_script_data(html)
        if script_data:
            if DEBUG_MODE:
                print(f"[DEBUG] 从script提取到数据", file=sys.stderr)
            info.update(self._extract_from_json(script_data))

        # 使用正则表达式作为最后的后备方案
        if not info.get('author'):
            info['author'] = self._extract_field(html, [
                r'"author"\s*:\s*\{[^}]*"nickname"\s*:\s*"([^"]+)"',
                r'"nickname"\s*:\s*"([^"]+)"'
            ])

        if not info.get('author_id'):
            info['author_id'] = self._extract_field(html, [
                r'"author"\s*:\s*\{[^}]*"uid"\s*:\s*"(\d+)"',
                r'"sec_uid"\s*:\s*"([^"]+)"'
            ])

        if not info.get('duration'):
            info['duration'] = self._extract_numeric_field(html, [r'"duration"\s*:\s*(\d+)'])

        if not info.get('video_id'):
            info['video_id'] = self._extract_field(html, [
                r'"aweme_id"\s*:\s*"([^"]+)"',
                r'/video/(\d+)'
            ])

        # 过滤掉None值
        return {k: v for k, v in info.items() if v is not None}

    def _extract_from_api_response(self, api_data: dict) -> dict:
        """
        从API响应中提取视频信息

        Args:
            api_data: API响应数据

        Returns:
            dict: 提取到的视频信息
        """
        info = {}

        # 递归查找aweme详情
        def find_aweme_data(obj, depth=0):
            if depth > 10:  # 限制递归深度
                return None

            if isinstance(obj, dict):
                # 检查是否包含aweme关键字
                if 'aweme' in obj and 'detail' in str(obj):
                    return obj

                # 检查常见的视频数据结构
                if any(key in obj for key in ['desc', 'author', 'statistics', 'video']):
                    # 验证这是视频数据
                    if 'desc' in obj and ('author' in obj or 'statistics' in obj):
                        return obj

                # 递归搜索
                for value in obj.values():
                    result = find_aweme_data(value, depth+1)
                    if result:
                        return result

            elif isinstance(obj, list) and len(obj) > 0:
                for item in obj:
                    result = find_aweme_data(item, depth+1)
                    if result:
                        return result

            return None

        # 查找视频数据
        aweme_data = find_aweme_data(api_data)

        if aweme_data:
            if DEBUG_MODE:
                print(f"[DEBUG] 找到视频数据! 键: {list(aweme_data.keys())[:20]}", file=sys.stderr)

            # 提取作者信息
            if 'author' in aweme_data:
                author = aweme_data['author']
                if isinstance(author, dict):
                    info['author'] = author.get('nickname') or author.get('unique_id') or author.get('signature')
                    info['author_id'] = author.get('uid') or author.get('sec_uid') or author.get('id')

            # 提取统计信息
            if 'statistics' in aweme_data:
                stats = aweme_data['statistics']
                if isinstance(stats, dict):
                    info['like_count'] = stats.get('digg_count') or stats.get('like_count')
                    info['comment_count'] = stats.get('comment_count')
                    info['share_count'] = stats.get('share_count')
                    info['collect_count'] = stats.get('collect_count') or stats.get('favorite_count')

            # 提取视频时长、音频和封面
            if 'video' in aweme_data:
                video = aweme_data['video']
                if isinstance(video, dict):
                    info['duration'] = video.get('duration')

                    # 提取音频URL
                    # 优先从music字段获取音频
                    if 'music' in aweme_data:
                        music = aweme_data['music']
                        if isinstance(music, dict):
                            audio_url = None

                            # 尝试多个可能的音频URL字段
                            possible_audio_fields = ['play_url', 'audio_url', 'play_url_web', 'stream_url']
                            for field in possible_audio_fields:
                                value = music.get(field)
                                if value:
                                    # 如果是字符串直接使用
                                    if isinstance(value, str):
                                        audio_url = value
                                        break
                                    # 如果是对象且有url_list，提取第一个URL
                                    elif isinstance(value, dict) and 'url_list' in value:
                                        url_list = value['url_list']
                                        if url_list and len(url_list) > 0:
                                            audio_url = url_list[0]
                                            break

                            # 如果上述字段都没有，检查play_addr
                            if not audio_url and isinstance(music.get('play_addr'), dict):
                                url_list = music['play_addr'].get('url_list', [])
                                if url_list:
                                    audio_url = url_list[0]

                            if audio_url:
                                info['audio_url'] = audio_url

                    # 如果music中没有音频URL，尝试从video字段提取
                    if 'audio_url' not in info:
                        # 从video的download_addr或play_addr获取（这些通常包含音轨）
                        video_addr = video.get('download_addr') or video.get('play_addr')
                        if isinstance(video_addr, dict) and 'url_list' in video_addr:
                            url_list = video_addr['url_list']
                            if url_list:
                                info['audio_url'] = url_list[0]

                    # 提取封面URL
                    # 优先使用 origin_cover（原始封面），其次是 cover，然后是 dynamic_cover
                    cover_url = video.get('origin_cover') or video.get('cover') or video.get('dynamic_cover')
                    # 如果是URL列表，取第一个
                    if isinstance(cover_url, dict) and 'url_list' in cover_url:
                        cover_url = cover_url['url_list'][0] if cover_url['url_list'] else None
                    elif isinstance(cover_url, list) and len(cover_url) > 0:
                        cover_url = cover_url[0]

                    if cover_url:
                        info['cover_url'] = cover_url

            # 提取其他信息
            if 'desc' in aweme_data:
                info['desc'] = aweme_data['desc']

            if 'aweme_id' in aweme_data:
                info['video_id'] = aweme_data['aweme_id']

            if 'create_time' in aweme_data:
                info['create_time'] = aweme_data['create_time']

            if 'music' in aweme_data:
                music = aweme_data['music']
                if isinstance(music, dict):
                    info['music'] = music.get('title') or music.get('author')

        return info

    def _extract_script_data(self, html: str) -> dict:
        """
        从script标签中提取JSON数据（简化版）

        Args:
            html: 页面HTML内容

        Returns:
            dict: 解析后的JSON数据，如果失败返回None
        """
        import html as html_module

        # 主要的script标签模式
        patterns = [
            r'<script id="RENDER_DATA" type="application/json">(.+?)</script>',
            r'<script>window\.__INITIAL_STATE__\s*=\s*(\{.+?\});?</script>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                json_str = match.group(1).strip()

                # 尝试多种解码方式
                for decode_func in [lambda s: s, unquote, html_module.unescape]:
                    try:
                        decoded_str = decode_func(json_str)
                        data = json.loads(decoded_str)
                        if isinstance(data, dict) and data:
                            return data
                    except:
                        continue

        return None

    def _extract_from_json(self, data: dict, prefix: str = '') -> dict:
        """
        从JSON数据中递归提取视频信息

        Args:
            data: JSON数据字典
            prefix: 当前递归路径前缀

        Returns:
            dict: 提取到的视频信息
        """
        info = {}
        if not isinstance(data, dict):
            return info

        # 定义要查找的字段映射（更多可能的字段名）
        field_mappings = {
            'author': ['author', 'authorNickname', 'nickname', 'author_name', 'userName'],
            'author_id': ['authorUid', 'authorId', 'uid', 'secUid', 'user_id', 'userId'],
            'like_count': ['diggCount', 'likeCount', 'digg_count', 'like_count', 'statistics', 'digg_count'],
            'comment_count': ['commentCount', 'comment_count', 'commentCount'],
            'share_count': ['shareCount', 'share_count'],
            'collect_count': ['collectCount', 'collect_count', 'favoriteCount'],
            'duration': ['duration', 'videoDuration', 'video_duration'],
            'video_id': ['awemeId', 'aweme_id', 'videoId', 'video_id', 'aweme_id'],
            'create_time': ['createTime', 'create_time', 'timestamp'],
            'music': ['musicTitle', 'musicName', 'music', 'music_title', 'bgMusic'],
            'desc': ['desc', 'description', 'videoDesc', 'content'],
        }

        # 在当前层级查找字段
        for target_field, possible_keys in field_mappings.items():
            if not info.get(target_field):
                for key in possible_keys:
                    if key in data:
                        value = data[key]
                        # 过滤None和空值
                        if value is not None and value != '':
                            # 特殊处理statistics字段
                            if key == 'statistics' and isinstance(value, dict):
                                if 'digg_count' in value:
                                    info['like_count'] = value.get('digg_count')
                                if 'comment_count' in value:
                                    info['comment_count'] = value.get('comment_count')
                                if 'share_count' in value:
                                    info['share_count'] = value.get('share_count')
                                if 'collect_count' in value:
                                    info['collect_count'] = value.get('collect_count')
                            elif key == 'music' and isinstance(value, dict):
                                # 从music对象中提取标题
                                if 'title' in value:
                                    info['music'] = value['title']
                                elif 'music_name' in value:
                                    info['music'] = value['music_name']
                            else:
                                info[target_field] = value
                            break

        # 递归查找嵌套对象 - 增加递归深度检查
        for key, value in data.items():
            # 跳过一些不需要深度遍历的键
            if key in ['__wxConfig', 'router', 'location']:
                continue

            if isinstance(value, dict):
                # 递归处理嵌套字典
                nested_info = self._extract_from_json(value, f"{prefix}.{key}" if prefix else key)
                # 合并结果，只保留尚未找到的字段
                for k, v in nested_info.items():
                    if k not in info or info[k] is None:
                        info[k] = v
            elif isinstance(value, list) and len(value) > 0:
                # 检查列表元素
                for item in value[:10]:  # 限制检查前10个元素，避免过度遍历
                    if isinstance(item, dict):
                        nested_info = self._extract_from_json(item, f"{prefix}.{key}" if prefix else key)
                        for k, v in nested_info.items():
                            if k not in info or info[k] is None:
                                info[k] = v

        return info

    def _extract_field(self, html: str, patterns: list) -> str:
        """
        使用多个模式提取字段

        Args:
            html: HTML内容
            patterns: 正则表达式模式列表

        Returns:
            str: 提取到的值，如果没有找到则返回None
        """
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None

    def _extract_numeric_field(self, html: str, patterns: list) -> int:
        """
        使用多个模式提取数字字段

        Args:
            html: HTML内容
            patterns: 正则表达式模式列表

        Returns:
            int: 提取到的数值，如果没有找到则返回None
        """
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None

    def _parse_title_and_tag(self, title_text: str) -> tuple:
        """
        解析标题和标签

        Args:
            title_text: 原始标题文本，可能包含 #标签

        Returns:
            tuple: (title, tag)
                - title: 去掉标签后的标题
                - tag: 标签字符串，多个标签用顿号连接，如果没有标签则为 None
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


class DouyinLinkParser:
    """抖音链接解析器 - 对外接口"""

    def __init__(self):
        self._parser = _DouyinParserCore()

    def extract_url(self, text: str) -> str:
        """从分享文本中提取抖音链接"""
        return self._parser.extract_url(text)

    def parse(self, url: str) -> dict:
        """解析抖音链接，获取视频信息"""
        return self._parser.parse(url)

    def parse_title_and_tag(self, title_text: str) -> tuple:
        """解析标题和标签，返回 (title, tag)"""
        return self._parser._parse_title_and_tag(title_text)
