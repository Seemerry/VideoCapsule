"""文本格式化模块 - 使用 DeepSeek API 对转录文本进行排版优化和摘要生成"""

import json
import os
import requests
from typing import Optional, Dict


class TextFormatter:
    """使用 DeepSeek API 格式化转录文本并生成摘要"""

    def __init__(self, config_path: Optional[str] = None):
        """初始化格式化器

        Args:
            config_path: 配置文件路径，默认为 ./config.json
        """
        self.api_key = None
        self.api_base = "https://api.deepseek.com"
        self.model = "deepseek-reasoner"

        # 加载配置
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')

        self._load_config(config_path)

    def _load_config(self, config_path: str):
        """从配置文件加载 DeepSeek API 配置"""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    deepseek_config = config.get('deepseek', {})
                    self.api_key = deepseek_config.get('api_key')
                    if deepseek_config.get('api_base'):
                        self.api_base = deepseek_config.get('api_base')
                    if deepseek_config.get('model'):
                        self.model = deepseek_config.get('model')
            except (json.JSONDecodeError, IOError):
                pass

    def _call_api(self, system_prompt: str, user_prompt: str) -> Optional[str]:
        """调用 DeepSeek API

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词

        Returns:
            str: API 返回的内容，失败返回 None
        """
        try:
            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False
                },
                timeout=120  # 2分钟超时
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get('choices', [{}])[0].get('message', {}).get('content')
                return content
            else:
                print(f"DeepSeek API 错误: {response.status_code} - {response.text}", file=__import__('sys').stderr)
                return None

        except requests.exceptions.Timeout:
            print("DeepSeek API 请求超时", file=__import__('sys').stderr)
            return None
        except requests.exceptions.RequestException as e:
            print(f"DeepSeek API 请求失败: {e}", file=__import__('sys').stderr)
            return None
        except Exception as e:
            print(f"API 调用失败: {e}", file=__import__('sys').stderr)
            return None

    def generate_summary(self, raw_text: str, title: Optional[str] = None) -> Optional[str]:
        """使用 DeepSeek API 生成文本摘要

        Args:
            raw_text: 原始转录文本
            title: 视频标题（可选，用于提供上下文）

        Returns:
            str: 生成的摘要，失败返回 None
        """
        if not self.api_key:
            print("警告: 未配置 DeepSeek API Key，跳过摘要生成", file=__import__('sys').stderr)
            return None

        if not raw_text or raw_text == '无转录内容':
            return None

        system_prompt = """你是一个专业的内容摘要助手。你的任务是对视频转录文本进行摘要提炼，帮助读者快速了解视频核心内容。

请严格遵守以下规则：
1. 提炼视频的**核心主题**和**关键观点**
2. 摘要应简洁明了，控制在200-400字之间
3. 使用条理清晰的段落或要点形式呈现
4. 对**关键人物、重要数据、核心概念**使用加粗格式（**文字**）
5. 输出格式为 Markdown
6. 不要添加任何标题（如"摘要"等），直接输出摘要内容"""

        user_prompt = f"请为以下视频内容生成摘要：\n\n{raw_text}"
        if title:
            user_prompt = f"视频标题：{title}\n\n" + user_prompt

        return self._call_api(system_prompt, user_prompt)

    def format_text(self, raw_text: str, title: Optional[str] = None) -> Optional[str]:
        """使用 DeepSeek API 格式化转录文本

        Args:
            raw_text: 原始转录文本
            title: 视频标题（可选，用于提供上下文）

        Returns:
            str: 格式化后的 Markdown 文本，失败返回 None
        """
        if not self.api_key:
            print("警告: 未配置 DeepSeek API Key，跳过文本格式化", file=__import__('sys').stderr)
            return None

        if not raw_text or raw_text == '无转录内容':
            return raw_text

        # 构建提示词
        system_prompt = """你是一个专业的文字排版助手。你的任务是对语音转文字的内容进行排版优化，使其更适合阅读。

请严格遵守以下规则：
1. **绝对不能修改、删减或添加任何原文内容**，必须保留每一个字句
2. 对文本进行合理的段落划分，根据语义和话题进行换行
3. 对**重点语句、核心观点、关键信息**使用加粗格式（**文字**）
4. 可以适当添加空行来分隔不同的段落或话题
5. 如果有明显的对话或问答，可以用空行分隔
6. 输出格式必须为 Markdown
7. 不要添加任何标题、解释性文字或前言后语，只输出排版后的内容"""

        user_prompt = f"请对以下语音转文字内容进行排版优化：\n\n{raw_text}"
        if title:
            user_prompt = f"视频标题：{title}\n\n" + user_prompt

        return self._call_api(system_prompt, user_prompt)

    def process_text(self, raw_text: str, title: Optional[str] = None) -> Dict[str, Optional[str]]:
        """处理文本：生成摘要并格式化原文

        Args:
            raw_text: 原始转录文本
            title: 视频标题（可选，用于提供上下文）

        Returns:
            dict: 包含 'summary' 和 'formatted_text' 的字典
        """
        result = {
            'summary': None,
            'formatted_text': None
        }

        if not self.api_key:
            print("警告: 未配置 DeepSeek API Key，跳过文本处理", file=__import__('sys').stderr)
            return result

        if not raw_text or raw_text == '无转录内容':
            return result

        print("正在生成摘要...", file=__import__('sys').stderr)
        result['summary'] = self.generate_summary(raw_text, title)

        print("正在格式化原文...", file=__import__('sys').stderr)
        result['formatted_text'] = self.format_text(raw_text, title)

        return result
