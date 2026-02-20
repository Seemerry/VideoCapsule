#!/usr/bin/env python3
"""视频信息提取器 - 支持抖音、Bilibili链接和本地视频，输出视频信息和文本"""

import argparse
import json
import os
import re
import sys

from modules import DouyinLinkParser, BilibiliLinkParser, LocalVideoParser, TextExtractor


def detect_platform(url: str) -> str:
    """
    检测URL所属平台或是否为本地文件

    Args:
        url: 视频链接或本地文件路径

    Returns:
        str: 平台名称 ('douyin', 'bilibili', 'local', 'unknown')
    """
    # 首先检查是否是本地文件
    if os.path.isfile(url):
        return 'local'

    url_lower = url.lower()
    if any(domain in url_lower for domain in ['douyin.com', 'iesdouyin.com']):
        return 'douyin'
    elif any(domain in url_lower for domain in ['bilibili.com', 'b23.tv']) or re.search(r'BV[a-zA-Z0-9]{10,}', url):
        return 'bilibili'
    return 'unknown'


class VideoExtractor:
    """视频信息提取器 - 支持多平台"""

    def __init__(self, config_path: str = None):
        self.douyin_parser = DouyinLinkParser()
        self.bilibili_parser = BilibiliLinkParser()
        self.local_parser = LocalVideoParser()
        self.text_extractor = TextExtractor(config_path)

    def _get_parser(self, platform: str):
        """根据平台获取对应的解析器"""
        if platform == 'bilibili':
            return self.bilibili_parser
        elif platform == 'local':
            return self.local_parser
        return self.douyin_parser

    def extract(self, url: str,
                transcribe_model: str = 'doubao',
                enable_speaker_info: bool = False,
                platform: str = None) -> dict:
        """从视频链接提取视频信息和文本

        Args:
            url: 视频链接（支持抖音和Bilibili）
            transcribe_model: 转录模型
            enable_speaker_info: 是否启用说话人识别
            platform: 指定平台（可选，默认自动检测）

        Returns:
            dict: 视频信息字典
        """
        # 自动检测平台
        if not platform:
            platform = detect_platform(url)

        parser = self._get_parser(platform)
        video_info = parser.parse(url)

        if not video_info.get('status', {}).get('success'):
            return video_info

        # 提取音频URL
        audio_url = None
        if 'urls' in video_info:
            audio_url = video_info['urls'].get('audio_url') or video_info['urls'].get('video_url')

        if not audio_url:
            video_info['status']['success'] = False
            video_info['status']['error'] = '未能获取到音频URL'
            return video_info

        # 提取文本
        try:
            transcription_result = self.text_extractor.extract(
                audio_url,
                model=transcribe_model,
                enable_speaker_info=enable_speaker_info
            )

            if transcription_result:
                video_info['transcription'] = transcription_result
            else:
                video_info['transcription'] = None
                video_info['status']['transcription_error'] = '文本提取失败'
        except Exception as e:
            video_info['transcription'] = None
            video_info['status']['transcription_error'] = str(e)

        return video_info


def main():
    """主函数"""
    arg_parser = argparse.ArgumentParser(
        description='视频信息提取器 - 支持抖音、Bilibili和本地视频，输出完整的视频信息和文本'
    )
    arg_parser.add_argument('url', nargs='?', help='视频链接、分享文本或本地视频文件路径（支持抖音/Bilibili/本地文件）')
    arg_parser.add_argument('-m', '--model', choices=['paraformer', 'doubao'],
                        default='doubao', help='转录模型（默认: doubao）')
    arg_parser.add_argument('-s', '--speaker-info', action='store_true',
                        help='启用说话人识别')
    arg_parser.add_argument('-c', '--config', default=None,
                        help='配置文件路径（默认: ./config.json）')
    arg_parser.add_argument('-o', '--output', default=None,
                        help='输出文件路径（默认: 标准输出）')
    arg_parser.add_argument('--no-transcribe', action='store_true',
                        help='仅解析链接，不进行音频转录')

    args = arg_parser.parse_args()

    # 获取输入
    input_text = args.url if args.url else sys.stdin.read().strip()
    if not input_text:
        print("错误: 未提供视频链接", file=sys.stderr)
        sys.exit(1)

    extractor = VideoExtractor(config_path=args.config)

    # 检测平台并提取URL
    platform = detect_platform(input_text)
    link_parser = extractor._get_parser(platform)
    video_url = link_parser.extract_url(input_text)

    # 验证输入（本地文件或URL）
    if platform == 'local':
        # 本地文件验证
        if not video_url or not os.path.isfile(video_url):
            error_result = {
                'status': {'success': False, 'error': '本地视频文件不存在'},
                'input': input_text[:100] + '...' if len(input_text) > 100 else input_text
            }
            output_json = json.dumps(error_result, ensure_ascii=False, indent=2)
            _write_output(output_json, args.output)
            sys.exit(1)
    else:
        # URL验证
        if not video_url or not video_url.startswith('http'):
            error_result = {
                'status': {'success': False, 'error': '未能从输入中提取出有效的视频链接'},
                'input': input_text[:100] + '...' if len(input_text) > 100 else input_text
            }
            output_json = json.dumps(error_result, ensure_ascii=False, indent=2)
            _write_output(output_json, args.output)
            sys.exit(1)

    # 仅解析链接模式
    if args.no_transcribe:
        result = link_parser.parse(video_url)
    else:
        # 执行完整提取（包含转录）
        result = extractor.extract(
            video_url,
            transcribe_model=args.model,
            enable_speaker_info=args.speaker_info,
            platform=platform
        )

    # 解析标题和标签
    if result.get('status', {}).get('success') and 'content' in result:
        title_text = result['content'].get('title', '')
        if title_text:
            title, tag = link_parser.parse_title_and_tag(title_text)
            result['content']['title'] = title
            if tag:
                result['content']['tag'] = tag

    # 输出结果
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    _write_output(output_json, args.output)

    success = result.get('status', {}).get('success', False)
    sys.exit(0 if success else 1)


def _write_output(content: str, filepath: str = None):
    """写入输出到文件或标准输出"""
    if filepath:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"结果已保存到: {filepath}", file=sys.stderr)
    else:
        print(content)


if __name__ == '__main__':
    main()
