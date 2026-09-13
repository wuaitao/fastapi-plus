"""只模拟厂商 SDK 边界；真实适配器和 Registry 保持原样执行。"""

import threading
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, BinaryIO


class CosError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code

    def get_status_code(self) -> int:
        return self.status

    def get_error_code(self) -> str:
        return self.code


class CloudClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.acls: dict[str, str] = {}
        self.calls: list[int] = []
        self.error: Exception | None = None
        self.signed: tuple[str, int, str] | None = None

    def check(self) -> None:
        self.calls.append(threading.get_ident())
        if self.error is not None:
            raise self.error

    def put_object(self, request: Any = None, **kwargs: Any) -> None:
        self.check()
        key: str = request.key if request else kwargs["Key"]
        content: BinaryIO = request.body if request else kwargs["Body"]
        size: int = request.content_length if request else kwargs["ContentLength"]
        data = bytearray()
        while chunk := content.read(64 * 1024):
            data.extend(chunk)
        assert len(data) == size
        self.objects[key] = bytes(data)
        self.acls[key] = request.acl if request else kwargs["ACL"]

    def delete_object(self, request: Any = None, **kwargs: Any) -> None:
        self.check()
        self.objects.pop(request.key if request else kwargs["Key"], None)

    def is_object_exist(self, bucket: str, key: str) -> bool:
        self.check()
        return key in self.objects

    def head_object(self, *, Bucket: str, Key: str) -> None:
        self.check()
        if Key not in self.objects:
            raise CosError(404, "NoSuchKey")

    def presign(self, request: Any, *, expires: timedelta) -> SimpleNamespace:
        self.check()
        self.signed = (
            request.key,
            int(expires.total_seconds()),
            request.response_content_disposition,
        )
        return SimpleNamespace(url="https://cloud.example/object?signature=test")

    def get_presigned_url(self, **kwargs: Any) -> str:
        self.check()
        self.signed = (
            kwargs["Key"],
            kwargs["Expired"],
            kwargs["Params"]["response-content-disposition"],
        )
        return "https://cloud.example/object?signature=test"

    def sdk(self, name: str = "") -> SimpleNamespace:
        def credentials(*args: str) -> None:
            return None

        def client(config: object) -> CloudClient:
            return self

        return SimpleNamespace(
            config=SimpleNamespace(load_default=SimpleNamespace),
            credentials=SimpleNamespace(StaticCredentialsProvider=credentials),
            Client=client,
            CosS3Client=client,
            CosConfig=SimpleNamespace,
            CosServiceError=CosError,
            PutObjectRequest=SimpleNamespace,
            DeleteObjectRequest=SimpleNamespace,
            GetObjectRequest=SimpleNamespace,
        )
