"""验证应用资源隔离、惰性连接与异常路径释放。"""

from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import ConnectionPoolEntry

from app.bootstrap.application import create_app
from app.core.config import Settings


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_lifespan_disposes_connections(tmp_path: Path, fail: bool) -> None:
    database = tmp_path / "lifecycle.db"
    app = create_app(Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{database}")))
    closed: list[object] = []

    def on_close(connection: object, record: ConnectionPoolEntry) -> None:
        closed.append(connection)

    async def run() -> None:
        assert not hasattr(app.state, "engine")
        async with app.router.lifespan_context(app):
            assert not database.exists()
            engine = cast(AsyncEngine, app.state.engine)
            event.listen(engine.sync_engine, "close", on_close)
            async with engine.connect() as connection:
                assert await connection.scalar(text("SELECT 1")) == 1
                tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
                assert tables == []
            if fail:
                raise RuntimeError("生命周期异常")

    if fail:
        with pytest.raises(RuntimeError, match="生命周期异常"):
            await run()
    else:
        await run()
    assert len(closed) == 1
    assert not hasattr(app.state, "engine")
    assert not hasattr(app.state, "session_factory")


@pytest.mark.asyncio
async def test_apps_have_independent_database_resources(settings: Settings) -> None:
    first = create_app(settings)
    second = create_app(settings)
    async with first.router.lifespan_context(first), second.router.lifespan_context(second):
        assert first.state.engine is not second.state.engine
        assert first.state.session_factory is not second.state.session_factory
