"""验证三种异步方言配置、可选驱动与跨库字段映射。"""

from importlib.util import find_spec
from typing import Literal

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.dialects import mysql, postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.core.config import Settings
from app.database.engine import create_engine
from tests.database_models import Record


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backend", "driver", "url"),
    [
        ("sqlite", "aiosqlite", "sqlite+aiosqlite:///:memory:"),
        ("postgresql", "asyncpg", "postgresql+asyncpg://localhost/test"),
        ("mysql", "asyncmy", "mysql+asyncmy://localhost/test"),
    ],
)
async def test_engine_creation(
    backend: Literal["sqlite", "postgresql", "mysql"], driver: str, url: str
) -> None:
    settings = Settings(database=backend, database_url=SecretStr(url))
    if find_spec(driver) is None:
        # 默认安装无需外部驱动，但选择未安装的后端必须给出明确错误。
        with pytest.raises(RuntimeError, match=f"请安装 {backend} 可选依赖"):
            create_engine(settings)
        return
    engine = create_engine(settings)
    try:
        assert engine.dialect.name == backend
        assert engine.dialect.driver == driver
        assert engine.dialect.is_async
        assert engine.echo is False
        assert engine.sync_engine.hide_parameters is True
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "invalid-secret",
        "sqlite:///test.db",
        "postgresql+asyncpg://localhost/test",
        "sqlite+aiosqlite://example:secret@localhost/test",
    ],
)
def test_invalid_database_urls_are_safe(url: str) -> None:
    with pytest.raises(ValidationError) as error:
        Settings(database_url=SecretStr(url))
    assert url not in str(error.value)


@pytest.mark.parametrize("url", ["postgresql+asyncpg:///test", "postgresql+asyncpg://localhost"])
def test_remote_database_requires_host_and_name(url: str) -> None:
    with pytest.raises(ValidationError, match="主机与数据库名"):
        Settings(database="postgresql", database_url=SecretStr(url))


def test_database_url_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE", "postgresql")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example:secret%25@localhost/test")
    settings = Settings()
    assert settings.sqlalchemy_url.password == "secret%"
    assert "secret" not in repr(settings)
    assert "secret" not in settings.model_dump_json()


def test_primary_key_dialect_mapping() -> None:
    table = Record.metadata.tables["test_records"]
    sqlite_ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    postgres_ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    mysql_ddl = str(CreateTable(table).compile(dialect=mysql.dialect()))
    assert "id INTEGER NOT NULL" in sqlite_ddl
    assert "id BIGSERIAL NOT NULL" in postgres_ddl
    assert "id BIGINT NOT NULL AUTO_INCREMENT" in mysql_ddl
    for ddl in (sqlite_ddl, postgres_ddl, mysql_ddl):
        assert "pk_test_records" in ddl
        assert "uq_test_records_name" in ddl
