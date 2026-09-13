"""在临时目录真实执行 Alembic，避免更改仓库迁移和开发数据库。"""

import asyncio
import io
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command
from app.core.config import get_settings
from app.database import metadata
from app.database.engine import create_engine
from app.database.repository import BaseRepository
from app.database.session import create_session_factory, session_scope
from tests.database_models import Record


@pytest.fixture
def migration_config(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Config:
    scripts = tmp_path / "alembic"
    shutil.copytree(repository_root / "alembic", scripts)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}")
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(scripts))
    return config


def test_users_migration_roundtrip(migration_config: Config, tmp_path: Path) -> None:
    assert set(metadata.target_metadata.tables) == {"users", "files"}
    command.upgrade(migration_config, "head")
    command.check(migration_config)
    with sqlite3.connect(tmp_path / "migration.db") as connection:
        names = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert set(names) == {("alembic_version",), ("users",), ("files",)}
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == [
            ("0002_create_files",)
        ]
        assert connection.execute("SELECT * FROM users").fetchall() == []
        assert connection.execute("SELECT * FROM files").fetchall() == []
    command.downgrade(migration_config, "base")
    with sqlite3.connect(tmp_path / "migration.db") as connection:
        names = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert names == [("alembic_version",)]
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == []
    command.upgrade(migration_config, "head")
    command.check(migration_config)


def test_autogenerate_upgrade_and_downgrade(
    migration_config: Config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 将测试 metadata 接入同一个显式入口，验证模型加载、自定义类型和模板可执行性。
    command.upgrade(migration_config, "head")
    monkeypatch.setattr(metadata, "target_metadata", Record.metadata)
    command.revision(migration_config, message="测试数据库基础", autogenerate=True)
    command.upgrade(migration_config, "head")
    command.check(migration_config)

    async def insert_record() -> int:
        engine = create_engine(get_settings())
        try:
            async with session_scope(create_session_factory(engine)) as session:
                record = await BaseRepository(session, Record).create(Record(name="migrated"))
                await session.commit()
                return record.id
        finally:
            await engine.dispose()

    assert asyncio.run(insert_record()) == 1
    with sqlite3.connect(tmp_path / "migration.db") as connection:
        assert connection.execute("SELECT name FROM test_records").fetchall() == [("migrated",)]
        assert len(connection.execute("SELECT * FROM alembic_version").fetchall()) == 1

    command.downgrade(migration_config, "base")
    with sqlite3.connect(tmp_path / "migration.db") as connection:
        names = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        assert names == [("alembic_version",)]
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == []
    command.upgrade(migration_config, "head")
    command.check(migration_config)


@pytest.mark.parametrize(
    ("backend", "url"),
    [
        ("sqlite", "sqlite+aiosqlite:///:memory:"),
        ("postgresql", "postgresql+asyncpg://localhost/test"),
        ("mysql", "mysql+asyncmy://localhost/test"),
    ],
)
def test_offline_migrations(
    migration_config: Config, monkeypatch: pytest.MonkeyPatch, backend: str, url: str
) -> None:
    monkeypatch.setenv("DATABASE", backend)
    monkeypatch.setenv("DATABASE_URL", url)
    output = io.StringIO()
    migration_config.output_buffer = output
    command.revision(migration_config, message="离线环境测试")
    command.upgrade(migration_config, "head", sql=True)
    assert "CREATE TABLE alembic_version" in output.getvalue()
    assert "INSERT INTO alembic_version" in output.getvalue()
    assert "CREATE TABLE users" in output.getvalue()
    assert "CREATE TABLE files" in output.getvalue()
    assert "uq_users_username" in output.getvalue()
    assert "uq_users_email" in output.getvalue()
