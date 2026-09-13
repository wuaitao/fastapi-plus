"""文件校验、所有权、对象存储与数据库事务协调"""

import asyncio
import unicodedata
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO
from uuid import uuid4

import structlog

from app.core.exceptions import AuthenticationException, AuthorizationException, BusinessException
from app.modules.file.errors import (
    FILE_INVALID_NAME,
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    FILE_TYPE_NOT_ALLOWED,
)
from app.modules.file.model import FileRecord
from app.modules.file.repository import FileRepository
from app.modules.user.model import User
from app.providers.storage import StorageAccess, StorageRegistry, Visibility

logger = structlog.get_logger(__name__)

# 最小上传允许列表；扩展名和 MIME 仅作输入约束，不代表已扫描内容。
ALLOWED_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bin": "application/octet-stream",
}


@dataclass(frozen=True)
class FileDownload:
    record: FileRecord
    access: StorageAccess


class FileService:
    def __init__(self, repository: FileRepository, storage: StorageRegistry, max_size: int) -> None:
        self.repository = repository
        self.storage = storage
        self.max_size = max_size

    def _validate(self, content: BinaryIO, filename: str, content_type: str) -> int:
        if (
            not filename
            or len(filename) > 255
            or filename.strip() != filename
            or any(char in filename for char in "/\\:")
            or any(unicodedata.category(char).startswith("C") for char in filename)
        ):
            raise BusinessException(FILE_INVALID_NAME)
        if ALLOWED_TYPES.get(PurePath(filename).suffix.lower()) != content_type:
            raise BusinessException(FILE_TYPE_NOT_ALLOWED)
        # 不信任 HTTP 长度；分块统计实际流并复位，内存占用不随文件增长。
        content.seek(0)
        size = 0
        while chunk := content.read(64 * 1024):
            size += len(chunk)
            if size > self.max_size:
                raise BusinessException(FILE_TOO_LARGE)
        content.seek(0)
        return size

    async def upload(
        self,
        content: BinaryIO,
        *,
        filename: str,
        content_type: str,
        visibility: Visibility,
        actor: User,
    ) -> FileRecord:
        if visibility not in ("private", "public"):
            raise ValueError("无效的文件可见性")
        validation = asyncio.create_task(
            asyncio.to_thread(self._validate, content, filename, content_type)
        )
        try:
            size = await asyncio.shield(validation)
        except asyncio.CancelledError:
            # 线程不会随请求取消而停止；退出前等待校验结束，避免入口提前关闭上传流。
            try:
                await validation
            except Exception:
                pass
            raise
        backend = self.storage.default_backend
        provider = self.storage.get(backend)
        key = uuid4().hex
        try:
            stored = await provider.put(
                key,
                content,
                size=size,
                content_type=content_type,
                visibility=visibility,
            )
            record = await self.repository.create(
                FileRecord(
                    backend=backend,
                    key=stored.key,
                    original_name=filename,
                    content_type=content_type,
                    size=stored.size,
                    visibility=visibility,
                    created_by=actor.id,
                )
            )
            await self.repository.session.commit()
            return record
        except BaseException:
            # 对象写入的网络错误也可能已在云端生效；新 key 可安全补偿删除。
            # 回滚或补偿失败均不覆盖原异常，也不能宣称跨系统一致性已恢复。
            try:
                await self.repository.session.rollback()
            except Exception:
                logger.error("file_upload_rollback_failed", backend=backend, key=key)
            try:
                await provider.delete(key, visibility=visibility)
            except Exception:
                logger.error("file_upload_compensation_failed", backend=backend, key=key)
            raise

    @staticmethod
    def _authorize(record: FileRecord, actor: User | None, *, write: bool = False) -> None:
        if not write and record.visibility == "public":
            return
        if actor is None:
            raise AuthenticationException()
        if actor.id != record.created_by and not actor.is_superuser:
            raise AuthorizationException()

    async def get_file(self, file_id: int, actor: User | None) -> FileRecord:
        record = await self.repository.get(file_id)
        if record is None:
            raise BusinessException(FILE_NOT_FOUND)
        self._authorize(record, actor)
        return record

    async def download(self, file_id: int, actor: User | None) -> FileDownload:
        record = await self.get_file(file_id, actor)
        provider = self.storage.get(record.backend)
        if not await provider.exists(record.key, visibility=record.visibility):
            raise BusinessException(FILE_NOT_FOUND)
        access = await provider.access(
            record.key,
            visibility=record.visibility,
            filename=record.original_name,
        )
        return FileDownload(record, access)

    async def delete_file(self, file_id: int, actor: User) -> None:
        record = await self.get_file(file_id, actor)
        self._authorize(record, actor, write=True)
        provider = self.storage.get(record.backend)
        backend, key, visibility = record.backend, record.key, record.visibility
        object_deleted = False
        try:
            await provider.delete(key, visibility=visibility)
            object_deleted = True
            await self.repository.delete(record)
            await self.repository.session.commit()
        except BaseException:
            # 数据库回滚不能恢复已删除的内容；保留元数据可重试清理，日志明确不一致。
            if object_deleted:
                logger.error("file_delete_metadata_failed", backend=backend, key=key)
            try:
                await self.repository.session.rollback()
            except Exception:
                logger.error("file_delete_rollback_failed", backend=backend, key=key)
            raise
