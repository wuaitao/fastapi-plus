"""腾讯云 COS 同步 SDK 适配器，未启用时不加载 SDK"""

from importlib import import_module
from typing import Any, BinaryIO

from app.core.config.storage import CloudStorageSettings
from app.infrastructure.storage.common import attachment, object_key, storage_io
from app.providers.storage import RemoteAccess, StoredObject, Visibility


class TencentCOSStorage:
    def __init__(self, settings: CloudStorageSettings) -> None:
        try:
            sdk = import_module("qcloud_cos")
        except ImportError:
            raise RuntimeError("COS 已启用，请安装 uv sync --extra cos") from None
        self.bucket = settings.bucket
        config = sdk.CosConfig(
            Region=settings.region,
            SecretId=settings.access_key_id.get_secret_value(),
            SecretKey=settings.access_key_secret.get_secret_value(),
            Scheme="https",
        )
        self._client: Any = sdk.CosS3Client(config)
        self._service_error: type[Exception] = sdk.CosServiceError

    async def put(
        self, key: str, content: BinaryIO, *, size: int, content_type: str, visibility: Visibility
    ) -> StoredObject:
        await storage_io(
            self._client.put_object,
            Bucket=self.bucket,
            Key=object_key(key, visibility),
            Body=content,
            ContentLength=size,
            ContentType=content_type,
            ACL="private" if visibility == "private" else "public-read",
        )
        return StoredObject(key, size)

    async def exists(self, key: str, *, visibility: Visibility) -> bool:
        remote_key = object_key(key, visibility)

        def head() -> bool:
            try:
                self._client.head_object(Bucket=self.bucket, Key=remote_key)
            except self._service_error as error:
                # HEAD 404 可能没有响应体；明确的桶错误、鉴权和网络错误仍须失败。
                sdk_error: Any = error
                if sdk_error.get_status_code() == 404 and sdk_error.get_error_code() in (
                    "NoSuchKey",
                    "",
                    "Unknown",
                ):
                    return False
                raise
            return True

        return await storage_io(head)

    async def delete(self, key: str, *, visibility: Visibility) -> None:
        await storage_io(
            self._client.delete_object, Bucket=self.bucket, Key=object_key(key, visibility)
        )

    async def access(self, key: str, *, visibility: Visibility, filename: str) -> RemoteAccess:
        url = await storage_io(
            self._client.get_presigned_url,
            Bucket=self.bucket,
            Key=object_key(key, visibility),
            Method="GET",
            Expired=300,
            Params={"response-content-disposition": attachment(filename)},
        )
        return RemoteAccess(str(url))
