"""存储只管理内容和访问能力；授权由文件业务完成"""

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal, Protocol

from app.core.exceptions import InfrastructureException

Visibility = Literal["private", "public"]


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int


@dataclass(frozen=True)
class LocalAccess:
    path: Path


@dataclass(frozen=True)
class RemoteAccess:
    url: str


StorageAccess = LocalAccess | RemoteAccess


class StorageProvider(Protocol):
    async def put(
        self, key: str, content: BinaryIO, *, size: int, content_type: str, visibility: Visibility
    ) -> StoredObject: ...

    async def exists(self, key: str, *, visibility: Visibility) -> bool: ...

    async def delete(self, key: str, *, visibility: Visibility) -> None:
        """删除不存在对象成功；存储故障必须抛出基础设施异常"""
        ...

    async def access(self, key: str, *, visibility: Visibility, filename: str) -> StorageAccess:
        """调用者必须先授权；云地址短期有效，本地结果不包含 HTTP 响应"""
        ...


class StorageRegistry:
    def __init__(self, default_backend: str) -> None:
        self.default_backend = default_backend
        self._providers: dict[str, StorageProvider] = {}

    def register(self, backend: str, provider: StorageProvider) -> None:
        if not backend or backend in self._providers:
            raise ValueError("存储后端名称不能为空或重复")
        self._providers[backend] = provider

    def get(self, backend: str | None = None) -> StorageProvider:
        try:
            return self._providers[backend if backend is not None else self.default_backend]
        except KeyError:
            # 历史后端未装配时明确失败，禁止回退到当前默认后端。
            raise InfrastructureException() from None
