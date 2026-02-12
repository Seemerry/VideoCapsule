"""文本提取模块 - 音频转文本功能"""

import json
import uuid
import time
import requests
from pathlib import Path
from http import HTTPStatus
from typing import List, Optional


class TextExtractor:
    """文本提取器"""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)
        self._setup_dashscope()

    def _load_config(self, config_path: Optional[str] = None) -> dict:
        """加载配置文件"""
        if config_path is None:
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config.json"

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _setup_dashscope(self):
        """设置DashScope API密钥"""
        try:
            import dashscope
            dashscope.api_key = self.config["dashscope"]["api_key"]
        except ImportError:
            pass

    def extract(self, audio_url: str, model: str = 'doubao',
                language_hints: Optional[List[str]] = None,
                enable_speaker_info: bool = False) -> dict:
        """从音频URL提取文本"""
        if language_hints is None:
            language_hints = ['zh', 'en']

        if model == 'doubao':
            result = self._transcribe_audio_doubao([audio_url], language_hints, enable_speaker_info)
        else:
            result = self._transcribe_audio_paraformer([audio_url], language_hints, enable_speaker_info)

        if result:
            return self._format_result(model, [audio_url], result)
        return None

    def _transcribe_audio_doubao(self, file_urls: List[str],
                                  language_hints: Optional[List[str]] = None,
                                  enable_speaker_info: bool = False) -> Optional[dict]:
        """使用豆包模型将音频转换为文本"""
        file_urls = [file_urls] if isinstance(file_urls, str) else file_urls
        request_id = str(uuid.uuid4())
        headers = self._build_doubao_headers(request_id)

        request_params = {"model_name": "bigmodel", "enable_itn": True}
        if enable_speaker_info:
            request_params["enable_speaker_info"] = True

        submit_data = {
            "user": {"uid": "doubao_user"},
            "audio": {"url": file_urls[0], "format": "mp3"},
            "request": request_params
        }

        try:
            response = requests.post(
                self.config["doubao"]["submit_endpoint"],
                json=submit_data,
                headers=headers
            )
            response.raise_for_status()

            if response.headers.get('X-Api-Status-Code') != '20000000':
                return None

            # 轮询查询结果
            for _ in range(60):
                time.sleep(2)
                query_response = requests.post(
                    self.config["doubao"]["query_endpoint"],
                    json={},
                    headers=self._build_doubao_headers(request_id)
                )

                query_status_code = query_response.headers.get('X-Api-Status-Code')
                if query_status_code == '20000000':
                    return query_response.json()
                elif query_status_code not in ['20000001', '20000002']:
                    return None

            return None
        except Exception:
            return None

    def _transcribe_audio_paraformer(self, file_urls: List[str],
                                      language_hints: Optional[List[str]] = None,
                                      enable_speaker_info: bool = False) -> Optional[dict]:
        """使用Paraformer模型将音频转换为文本"""
        try:
            from dashscope.audio.asr import Transcription
        except ImportError:
            return None

        file_urls = [file_urls] if isinstance(file_urls, str) else file_urls

        params = {
            'model': 'paraformer-v2',
            'file_urls': file_urls,
            'language_hints': language_hints
        }

        if enable_speaker_info:
            params['speaker_detection_enabled'] = True

        try:
            task_response = Transcription.async_call(**params)
            transcribe_response = Transcription.wait(task=task_response.output.task_id)

            if transcribe_response.status_code == HTTPStatus.OK:
                return transcribe_response.output
            return None
        except Exception:
            return None

    def _build_doubao_headers(self, request_id: str) -> dict:
        """构建豆包API请求头"""
        return {
            "Content-Type": "application/json",
            "X-Api-App-Key": self.config["doubao"]["app_id"],
            "X-Api-Access-Key": self.config["doubao"]["access_token"],
            "X-Api-Resource-Id": self.config["doubao"]["resource_id"],
            "X-Api-Request-Id": request_id,
            "X-Api-Sequence": "-1"
        }

    def _add_speaker_label(self, text_parts: list, speaker: str,
                           segment_text: str, last_speaker: str) -> str:
        """添加说话人标签，自动合并同一说话人"""
        if speaker != last_speaker:
            label = f"\n发言人{speaker}： {segment_text}" if last_speaker is not None else f"发言人{speaker}： {segment_text}"
            text_parts.append(label)
        else:
            text_parts.append(segment_text)
        return speaker

    def _format_result(self, model: str, urls: List[str], result: dict) -> dict:
        """格式化转录结果"""
        if model == 'doubao':
            if 'result' in result and isinstance(result['result'], dict):
                return self._format_doubao_result(urls, result['result'])
        else:
            if 'results' in result:
                return self._format_paraformer_result(urls, result)
        return None

    def _format_doubao_result(self, urls: List[str], result_data: dict) -> dict:
        """格式化豆包模型结果"""
        segments = []
        utterances = result_data.get('utterances', [])
        text_parts = []
        last_speaker = None

        for utterance in utterances:
            segment_text = utterance.get('text', '')
            segment = {
                "text": segment_text,
                "start": utterance.get('start_time', 0),
                "end": utterance.get('end_time', 0)
            }

            additions = utterance.get('additions', {})
            if isinstance(additions, dict) and 'speaker' in additions:
                speaker = additions['speaker']
                segment["speaker"] = speaker
                last_speaker = self._add_speaker_label(text_parts, speaker, segment_text, last_speaker)
            else:
                text_parts.append(segment_text)
                last_speaker = None

            segments.append(segment)

        return {
            "url": urls[0],
            "text": ' '.join(text_parts),
            "segments": segments
        }

    def _format_paraformer_result(self, urls: List[str], result: dict) -> dict:
        """格式化Paraformer模型结果"""
        for idx, res in enumerate(result.results):
            url = res.get('file_url', urls[idx] if idx < len(urls) else 'Unknown')
            transcription_url = res.get('transcription_url')

            if not transcription_url:
                continue

            try:
                response = requests.get(transcription_url)
                if response.status_code != 200:
                    continue

                data = response.json()
                if 'transcripts' not in data:
                    continue

                for transcript in data['transcripts']:
                    if 'sentences' not in transcript:
                        continue

                    sentences = transcript['sentences']
                    segments = []
                    text_parts = []
                    last_speaker = None

                    for sentence in sentences:
                        segment_text = sentence.get('text', '')
                        segment = {
                            "text": segment_text,
                            "start": sentence.get('begin_time', 0),
                            "end": sentence.get('end_time', 0)
                        }

                        if 'speaker' in sentence:
                            speaker = sentence['speaker']
                            segment["speaker"] = speaker
                            last_speaker = self._add_speaker_label(text_parts, speaker, segment_text, last_speaker)
                        else:
                            text_parts.append(segment_text)
                            last_speaker = None

                        segments.append(segment)

                    return {
                        "url": url,
                        "text": ' '.join(text_parts),
                        "segments": segments
                    }
            except Exception:
                continue

        return None
