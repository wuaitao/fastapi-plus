"""真实请求的 Session 依赖关闭资源，不隐式提交。"""

from pathlib import Path
from typing import Annotated, cast

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.database.repository import BaseRepository
from app.database.session import create_session_factory, get_session, session_scope
from tests.database_models import Record


@pytest.mark.asyncio
async def test_request_sessions_close_and_rollback(tmp_path: Path) -> None:
    app = create_app(
        Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'requests.db'}"))
    )
    sessions: list[AsyncSession] = []

    @app.post("/database-probe")
    async def write(
        session: Annotated[AsyncSession, Depends(get_session)],
        reused: Annotated[AsyncSession, Depends(get_session)],
        fail: bool = False,
    ) -> dict[str, int]:
        assert session is reused
        sessions.append(session)
        record = await BaseRepository(session, Record).create(Record(name="uncommitted"))
        if fail:
            raise RuntimeError("请求失败")
        return {"id": record.id}

    async with app.router.lifespan_context(app):
        engine = cast(AsyncEngine, app.state.engine)
        async with engine.begin() as connection:
            await connection.run_sync(Record.metadata.create_all)
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            assert (await client.post("/database-probe")).status_code == 200
            assert (await client.post("/database-probe?fail=true")).status_code == 500
        assert len(sessions) == 2
        assert sessions[0] is not sessions[1]
        assert all(not session.in_transaction() for session in sessions)
        factory = cast(async_sessionmaker[AsyncSession], app.state.session_factory)
        async with session_scope(factory) as session:
            assert await BaseRepository(session, Record).list() == []


@pytest.mark.asyncio
async def test_pool_exhaustion_is_unavailable_and_recovers(tmp_path: Path) -> None:
    settings = Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'pool.db'}"))
    app = create_app(settings)

    @app.get("/database-pool-probe")
    async def read(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, int]:
        await session.execute(text("SELECT 1"))
        return {"value": 1}

    # 用真实的一连接池制造耗尽，不替换 Session 或异常处理器。
    engine = create_async_engine(
        settings.sqlalchemy_url, pool_size=1, max_overflow=0, pool_timeout=0.05
    )
    app.state.session_factory = create_session_factory(engine)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async with engine.connect():
                response = await client.get("/database-pool-probe")
                assert response.status_code == 503
                assert response.json()["code"] == 11001
                assert "QueuePool" not in response.text
                assert "pool.db" not in response.text
            assert (await client.get("/database-pool-probe")).status_code == 200
    finally:
        await engine.dispose()
