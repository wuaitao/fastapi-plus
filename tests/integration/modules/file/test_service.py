"""真实数据库事务、对象补偿、删除失败与历史后端选择。"""

import asyncio
import io
import threading
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import event, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from structlog.testing import capture_logs

from app.core.config import Settings
from app.core.exceptions import InfrastructureException
from app.database.engine import create_engine
from app.database.metadata import target_metadata
from app.database.session import create_session_factory, session_scope
from app.infrastructure.storage.local import LocalStorage
from app.modules.file.model import FileRecord
from app.modules.file.repository import FileRepository
from app.modules.file.service import FileService
from app.modules.user.model import User
from app.providers.storage import LocalAccess, StorageRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize("read_fails", [False, True])
async def test_cancelled_validation_finishes_before_stream_closes(
    service: tuple[FileService, User], tmp_path: Path, read_fails: bool
) -> None:
    files, actor = service
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    class SlowStream(io.BytesIO):
        def read(self, size: int | None = -1, /) -> bytes:
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=10):
                raise TimeoutError("测试未释放上传流")
            if read_fails:
                raise OSError("测试读取失败")
            return super().read(size)

    stream = SlowStream(b"data")

    async def upload() -> None:
        try:
            await files.upload(
                stream,
                filename="a.txt",
                content_type="text/plain",
                visibility="private",
                actor=actor,
            )
        finally:
            # 模拟 Router 的 finally：Service 返回后入口立即关闭上传流。
            stream.close()

    task = asyncio.create_task(upload())
    try:
        await asyncio.wait_for(started.wait(), timeout=10)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=0.1)
        assert not done
        assert not stream.closed
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stream.closed
    assert not (tmp_path / "storage").exists()
    assert await files.repository.session.scalar(select(func.count()).select_from(FileRecord)) == 0


@pytest_asyncio.fixture
async def service(tmp_path: Path) -> AsyncIterator[tuple[FileService, User]]:
    engine = create_engine(
        Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'files.db'}"))
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(target_metadata.create_all)
        async with session_scope(create_session_factory(engine)) as session:
            actor = User(username="owner", password_hash="test-hash", is_superuser=False)
            session.add(actor)
            await session.commit()
            registry = StorageRegistry("local")
            registry.register("local", LocalStorage(tmp_path / "storage"))
            yield FileService(FileRepository(session), registry, 1024), actor
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["flush", "commit"])
@pytest.mark.parametrize("compensation_fails", [False, True])
async def test_upload_compensation(
    service: tuple[FileService, User],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    compensation_fails: bool,
) -> None:
    files, actor = service
    session = files.repository.session

    def fail_commit(sync_session: Session) -> None:
        raise RuntimeError("original database failure")

    def fail_flush(sync_session: Session, context: object, instances: object) -> None:
        # 制造真实 NOT NULL 约束错误，不替换被测 Repository 或 Service。
        sync_session.execute(insert(FileRecord).values(backend="invalid"))

    original_unlink = Path.unlink

    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.parent == tmp_path / "storage/private":
            raise OSError("private filesystem detail")
        original_unlink(path, missing_ok=missing_ok)

    if compensation_fails:
        monkeypatch.setattr(Path, "unlink", fail_unlink)
    if stage == "commit":
        event.listen(session.sync_session, "before_commit", fail_commit)
    else:
        event.listen(session.sync_session, "before_flush", fail_flush)
    with capture_logs() as logs:
        with pytest.raises(RuntimeError if stage == "commit" else IntegrityError):
            await files.upload(
                io.BytesIO(b"data"),
                filename="a.txt",
                content_type="text/plain",
                visibility="private",
                actor=actor,
            )
    if stage == "commit":
        event.remove(session.sync_session, "before_commit", fail_commit)
    else:
        event.remove(session.sync_session, "before_flush", fail_flush)
    assert not session.in_transaction()
    assert await session.scalar(select(func.count()).select_from(FileRecord)) == 0
    assert len(list((tmp_path / "storage/private").iterdir())) == int(compensation_fails)
    assert (
        any(log["event"] == "file_upload_compensation_failed" for log in logs) == compensation_fails
    )
    assert "private filesystem detail" not in str(logs)


@pytest.mark.asyncio
async def test_delete_database_failure_is_reported(
    service: tuple[FileService, User], tmp_path: Path
) -> None:
    files, actor = service
    record = await files.upload(
        io.BytesIO(b"data"),
        filename="a.txt",
        content_type="text/plain",
        visibility="private",
        actor=actor,
    )
    file_id, key = record.id, record.key
    session = files.repository.session

    def fail_commit(sync_session: Session) -> None:
        raise RuntimeError("database failure")

    event.listen(session.sync_session, "before_commit", fail_commit)
    with capture_logs() as logs, pytest.raises(RuntimeError, match="database failure"):
        await files.delete_file(file_id, actor)
    event.remove(session.sync_session, "before_commit", fail_commit)
    assert not session.in_transaction()
    assert await files.repository.get(file_id) is not None
    assert not (tmp_path / "storage/private" / key).exists()
    assert any(log["event"] == "file_delete_metadata_failed" for log in logs)
    # 对象已不存在时允许重试完成元数据删除。
    await session.refresh(actor)
    await files.delete_file(file_id, actor)
    assert await files.repository.get(file_id) is None


@pytest.mark.asyncio
async def test_delete_storage_failure_keeps_metadata(
    service: tuple[FileService, User], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files, actor = service
    record = await files.upload(
        io.BytesIO(b"data"),
        filename="a.txt",
        content_type="text/plain",
        visibility="private",
        actor=actor,
    )
    file_id, key = record.id, record.key
    original_unlink = Path.unlink

    def fail_unlink(path: Path, missing_ok: bool = False) -> None:
        if path.name == key:
            raise OSError("storage unavailable")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_unlink)
    with pytest.raises(InfrastructureException):
        await files.delete_file(file_id, actor)
    assert await files.repository.get(file_id) is not None
    assert (tmp_path / "storage/private" / key).read_bytes() == b"data"


@pytest.mark.asyncio
async def test_historical_backend_and_orphan_owner(
    service: tuple[FileService, User], tmp_path: Path
) -> None:
    files, actor = service
    files.storage.register("archive", LocalStorage(tmp_path / "archive"))
    files.storage.default_backend = "archive"
    record = await files.upload(
        io.BytesIO(b"old"),
        filename="a.txt",
        content_type="text/plain",
        visibility="private",
        actor=actor,
    )
    file_id = record.id
    files.storage.default_backend = "local"
    download = await files.download(file_id, actor)
    assert isinstance(download.access, LocalAccess)
    assert download.access.path == tmp_path / "archive/private" / record.key
    assert download.access.path.read_bytes() == b"old"
    await files.repository.session.delete(actor)
    await files.repository.session.commit()
    await files.repository.session.refresh(record)
    assert record.created_by is None
