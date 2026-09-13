"""真实本地文件系统；public/private 使用独立目录且不做静态挂载"""

from pathlib import Path
from typing import BinaryIO

from app.infrastructure.storage.common import object_key, storage_io
from app.providers.storage import LocalAccess, StoredObject, Visibility


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str, visibility: Visibility) -> Path:
        """解析可见性目录内的安全路径，拒绝符号链接和目录逃逸"""
        relative = object_key(key, visibility)
        path = self.root / relative
        # 逐级拒绝符号链接和 Windows junction，防止跨可见性目录或根目录逃逸。
        for candidate in (path, *path.parents):
            if candidate == self.root:
                break
            if candidate.is_symlink() or candidate.resolve() != candidate:
                raise ValueError("存储路径不能包含链接")
        if not path.resolve().is_relative_to(self.root / visibility):
            raise ValueError("存储路径越界")
        return path

    async def put(
        self, key: str, content: BinaryIO, *, size: int, content_type: str, visibility: Visibility
    ) -> StoredObject:
        """分块写入新文件并核对大小，失败时清理本次不完整内容"""
        object_key(key, visibility)

        def write() -> StoredObject:
            """执行排他创建及分块写入，不覆盖已有对象"""
            path = self._path(key, visibility)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._path(key, visibility)
            # 排他创建避免覆盖历史对象；失败只清理本次新建的文件。
            with path.open("xb") as target:
                try:
                    actual = 0
                    while chunk := content.read(64 * 1024):
                        actual += len(chunk)
                        if actual > size:
                            raise ValueError("实际流大小与声明不一致")
                        target.write(chunk)
                    if actual != size:
                        raise ValueError("实际流大小与声明不一致")
                except BaseException:
                    target.close()
                    path.unlink(missing_ok=True)
                    raise
            return StoredObject(key, actual)

        return await storage_io(write)

    async def exists(self, key: str, *, visibility: Visibility) -> bool:
        """检查安全路径上的文件是否存在，存储故障继续报错"""
        object_key(key, visibility)
        return await storage_io(lambda: self._path(key, visibility).is_file())

    async def delete(self, key: str, *, visibility: Visibility) -> None:
        """幂等删除指定文件，拒绝不安全路径"""
        object_key(key, visibility)
        await storage_io(lambda: self._path(key, visibility).unlink(missing_ok=True))

    async def access(self, key: str, *, visibility: Visibility, filename: str) -> LocalAccess:
        """返回已验证的本地路径，HTTP 下载与授权仍由上层处理"""
        object_key(key, visibility)
        return LocalAccess(await storage_io(self._path, key, visibility))
