"""数据库集成测试使用独立文件和真实事务，不用外层事务吞掉 commit。"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.database.engine import create_engine
from tests.database_models import Record


@pytest_asyncio.fixture
async def database_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"))
    )
    try:
        # 仅为 Repository 测试建表；Alembic 流程由独立迁移测试验收。
        async with engine.begin() as connection:
            await connection.run_sync(Record.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()
