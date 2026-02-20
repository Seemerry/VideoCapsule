"""OSS上传模块 - 将本地文件上传到阿里云OSS并生成临时访问URL"""

import os
import uuid
from datetime import datetime
from typing import Optional


class OSSUploader:
    """阿里云OSS文件上传器"""

    def __init__(self, config: dict):
        """
        初始化OSS上传器

        Args:
            config: OSS配置字典，包含 access_key_id, access_key_secret, bucket_name, endpoint
        """
        self.config = config
        self._bucket = None
        self._setup_oss()

    def _setup_oss(self):
        """设置OSS连接"""
        try:
            import oss2

            # 创建认证对象
            auth = oss2.Auth(
                self.config['access_key_id'],
                self.config['access_key_secret']
            )

            # 创建Bucket对象
            self._bucket = oss2.Bucket(
                auth,
                self.config['endpoint'],
                self.config['bucket_name']
            )
        except ImportError:
            raise ImportError("请安装 oss2 库: pip install oss2")
        except Exception as e:
            raise RuntimeError(f"OSS初始化失败: {str(e)}")

    def upload_file(self, local_path: str, expires_hours: int = 1,
                    delete_after: bool = True) -> dict:
        """
        上传本地文件到OSS并生成临时访问URL

        Args:
            local_path: 本地文件路径
            expires_hours: URL过期时间（小时）
            delete_after: 转录完成后是否删除文件

        Returns:
            dict: 包含 url 和 object_key 的字典
        """
        if not os.path.isfile(local_path):
            raise FileNotFoundError(f"文件不存在: {local_path}")

        # 生成唯一的对象键
        file_ext = os.path.splitext(local_path)[1]
        timestamp = datetime.now().strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex[:8]
        object_key = f"temp/{timestamp}/{unique_id}{file_ext}"

        # 上传文件
        try:
            with open(local_path, 'rb') as f:
                self._bucket.put_object(object_key, f)

            # 生成带签名的临时URL
            url = self._bucket.sign_url(
                'GET',
                object_key,
                expires_hours * 3600  # 转换为秒
            )

            return {
                'url': url,
                'object_key': object_key,
                'delete_after': delete_after
            }
        except Exception as e:
            raise RuntimeError(f"文件上传失败: {str(e)}")

    def delete_file(self, object_key: str) -> bool:
        """
        删除OSS上的文件

        Args:
            object_key: OSS对象键

        Returns:
            bool: 是否删除成功
        """
        try:
            self._bucket.delete_object(object_key)
            return True
        except Exception:
            return False

    @staticmethod
    def is_local_file(path: str) -> bool:
        """
        判断是否是本地文件路径

        Args:
            path: 路径字符串

        Returns:
            bool: 是否是本地文件
        """
        if path.startswith(('http://', 'https://')):
            return False
        return os.path.isfile(path)
