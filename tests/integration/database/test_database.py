"""真实 SQLAlchemy CRUD、分页、UTC 和事务回滚。"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.logging.config import configure_logging
from app.database.repository import BaseRepository
from app.database.session import create_session_factory, session_scope
from tests.database_models import Child, Record


@pytest.mark.asyncio
async def test_debug_logging_does_not_expose_sql(
    database_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(Settings(log_level="DEBUG", log_format="json"))
    async with session_scope(create_session_factory(database_engine)) as session:
        await BaseRepository(session, Record).create(Record(name="sensitive-database-value"))
    output = capsys.readouterr().err
    assert "sensitive-database-value" not in output
    assert "INSERT INTO" not in output


@pytest.mark.asyncio
async def test_repository_crud(database_engine: AsyncEngine) -> None:
    factory = create_session_factory(database_engine)
    async with session_scope(factory) as session:
        repository = BaseRepository(session, Record)
        record = await repository.create(Record(name="initial"))
        identifier = record.id
        created_at = record.created_at
        assert identifier > 0
        assert created_at.tzinfo is UTC
        assert record.updated_at.tzinfo is UTC
        assert await repository.get(identifier) is record
        assert await repository.get(identifier + 1) is None
        await session.commit()
        assert record.name == "initial"

    async with session_scope(factory) as session:
        repository = BaseRepository(session, Record)
        loaded = await repository.get(identifier)
        assert loaded is not None
        loaded.name = "updated"
        assert await repository.update(loaded) is loaded
        assert loaded.created_at == created_at
        assert loaded.updated_at >= created_at
        await session.commit()

    async with session_scope(factory) as session:
        repository = BaseRepository(session, Record)
        loaded = await repository.get(identifier)
        assert loaded is not None
        assert loaded.name == "updated"
        await repository.delete(loaded)
        assert await repository.get(identifier) is None
        await session.commit()

    async with session_scope(factory) as session:
        assert await BaseRepository(session, Record).list() == []


@pytest.mark.asyncio
async def test_pagination(database_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(database_engine)) as session:
        repository = BaseRepository(session, Record)
        empty = await repository.paginate()
        assert (empty.items, empty.total, empty.page, empty.size) == ([], 0, 1, 20)
        records = [await repository.create(Record(name=f"item-{i}")) for i in range(5)]
        page = await repository.paginate(page=2, size=2)
        assert page.items == records[2:4]
        assert (page.total, page.page, page.size) == (5, 2, 2)
        assert (await repository.paginate(page=3, size=2)).items == records[4:]
        outside = await repository.paginate(page=4, size=2)
        assert outside.items == []
        assert outside.total == 5
        assert await repository.list(offset=1, limit=2) == records[1:3]
        assert (await repository.paginate(size=100)).items == records


@pytest.mark.asyncio
@pytest.mark.parametrize(("page", "size"), [(0, 20), (-1, 20), (1, 0), (1, 101)])
async def test_invalid_pagination(database_engine: AsyncEngine, page: int, size: int) -> None:
    async with session_scope(create_session_factory(database_engine)) as session:
        with pytest.raises(ValueError, match="page"):
            await BaseRepository(session, Record).paginate(page=page, size=size)


@pytest.mark.asyncio
@pytest.mark.parametrize(("offset", "limit"), [(-1, 20), (0, 0), (0, 101)])
async def test_invalid_list(database_engine: AsyncEngine, offset: int, limit: int) -> None:
    async with session_scope(create_session_factory(database_engine)) as session:
        with pytest.raises(ValueError, match="offset"):
            await BaseRepository(session, Record).list(offset=offset, limit=limit)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_session_close_rolls_back(database_engine: AsyncEngine, fail: bool) -> None:
    factory = create_session_factory(database_engine)

    async def write() -> None:
        async with session_scope(factory) as session:
            record = await BaseRepository(session, Record).create(Record(name="uncommitted"))
            if fail:
                raise RuntimeError("业务失败")
        assert inspect(record).detached
        assert not session.in_transaction()

    if fail:
        with pytest.raises(RuntimeError, match="业务失败"):
            await write()
    else:
        await write()
    async with session_scope(factory) as session:
        assert await BaseRepository(session, Record).list() == []


@pytest.mark.asyncio
async def test_explicit_rollback_of_all_mutations(database_engine: AsyncEngine) -> None:
    factory = create_session_factory(database_engine)
    async with session_scope(factory) as session:
        repository = BaseRepository(session, Record)
        first = await repository.create(Record(name="first"))
        second = await repository.create(Record(name="second"))
        await session.commit()
        first.name = "changed"
        await repository.update(first)
        await repository.delete(second)
        await repository.create(Record(name="third"))
        await session.rollback()
    async with session_scope(factory) as session:
        assert [record.name for record in await BaseRepository(session, Record).list()] == [
            "first",
            "second",
        ]


@pytest.mark.asyncio
async def test_unique_failure_requires_caller_rollback(database_engine: AsyncEngine) -> None:
    factory = create_session_factory(database_engine)
    async with session_scope(factory) as session:
        repository = BaseRepository(session, Record)
        await repository.create(Record(name="duplicate"))
        with pytest.raises(IntegrityError):
            await repository.create(Record(name="duplicate"))
        assert not session.is_active
        await session.rollback()
        assert await repository.list() == []
        await repository.create(Record(name="recovered"))
        await session.commit()
    async with session_scope(factory) as session:
        assert [record.name for record in await BaseRepository(session, Record).list()] == [
            "recovered"
        ]


@pytest.mark.asyncio
async def test_foreign_keys_are_enforced(database_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(database_engine)) as session:
        with pytest.raises(IntegrityError):
            await BaseRepository(session, Child).create(Child(record_id=999))
        await session.rollback()


@pytest.mark.asyncio
async def test_sqlite_ddl_and_savepoint_rollback(database_engine: AsyncEngine) -> None:
    async with database_engine.connect() as connection:
        await connection.execute(text("CREATE TABLE rollback_probe (id INTEGER PRIMARY KEY)"))
        await connection.rollback()
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        assert "rollback_probe" not in tables
    factory = create_session_factory(database_engine)
    async with session_scope(factory) as session:
        async with session.begin_nested():
            await BaseRepository(session, Record).create(Record(name="nested"))
        await session.rollback()
    async with session_scope(factory) as session:
        assert await BaseRepository(session, Record).list() == []


@pytest.mark.asyncio
async def test_timestamp_normalization_and_update(database_engine: AsyncEngine) -> None:
    original = datetime(2020, 1, 1, 8, tzinfo=timezone(timedelta(hours=8)))
    async with session_scope(create_session_factory(database_engine)) as session:
        repository = BaseRepository(session, Record)
        record = await repository.create(
            Record(name="utc", created_at=original, updated_at=original)
        )
        assert record.created_at == datetime(2020, 1, 1, tzinfo=UTC)
        assert record.updated_at.tzinfo is UTC
        record.name = "utc-updated"
        await repository.update(record)
        assert record.updated_at > original
        assert record.created_at == original
        with pytest.raises(StatementError, match="时间必须包含时区"):
            await repository.create(Record(name="naive", created_at=datetime(2020, 1, 1)))
        await session.rollback()
