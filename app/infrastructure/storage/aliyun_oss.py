"""阿里云 OSS v2 同步 SDK 适配器，全部调用隔离到工作线程"""

from datetime import timedelta
from importlib import import_module
from typing import Any, BinaryIO

from app.core.config.storage import CloudStorageSettings
from app.infrastructure.storage.common import attachment, object_key, storage_io
from app.providers.storage import RemoteAccess, StoredObject, Visibility


class AliyunOSSStorage:
    def __init__(self, settings: CloudStorageSettings) -> None:
        try:
            self._sdk = import_module("alibabacloud_oss_v2")
        except ImportError:
            raise RuntimeError("OSS 已启用，请安装 uv sync --extra oss") from None
        self.bucket = settings.bucket
        config = self._sdk.config.load_default()
        config.region = settings.region
        config.endpoint = f"https://oss-{settings.region}.aliyuncs.com"
        config.credentials_provider = self._sdk.credentials.StaticCredentialsProvider(
            settings.access_key_id.get_secret_value(),
            settings.access_key_secret.get_secret_value(),
        )
        # SDK 无完整静态类型且为可选依赖，动态类型仅保留在厂商边界内。
        self._client: Any = self._sdk.Client(config)

    async def put(
        self, key: str, content: BinaryIO, *, size: int, content_type: str, visibility: Visibility
    ) -> StoredObject:
        """将流上传到 OSS，按可见性设置对象前缀和 ACL"""
        remote_key = object_key(key, visibility)
        await storage_io(
            self._client.put_object,
            self._sdk.PutObjectRequest(
                bucket=self.bucket,
                key=remote_key,
                body=content,
                content_length=size,
                content_type=content_type,
                acl="private" if visibility == "private" else "public-read",
            ),
        )
        return StoredObject(key, size)

    async def exists(self, key: str, *, visibility: Visibility) -> bool:
        """查询 OSS 对象存在性，调用异常交给存储边界转换"""
        return bool(
            await storage_io(self._client.is_object_exist, self.bucket, object_key(key, visibility))
        )

    async def delete(self, key: str, *, visibility: Visibility) -> None:
        """幂等删除 OSS 对象，保留存储失败语义"""
        await storage_io(
            self._client.delete_object,
            self._sdk.DeleteObjectRequest(bucket=self.bucket, key=object_key(key, visibility)),
        )

    async def access(self, key: str, *, visibility: Visibility, filename: str) -> RemoteAccess:
        """签发五分钟有效的下载 URL，并附带原始下载文件名"""
        result = await storage_io(
            self._client.presign,
            self._sdk.GetObjectRequest(
                bucket=self.bucket,
                key=object_key(key, visibility),
                response_content_disposition=attachment(filename),
            ),
            expires=timedelta(seconds=300),
        )
        return RemoteAccess(str(result.url))
