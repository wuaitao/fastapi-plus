"""验证 SQLite URI 和文件消失竞争下的只读保证。"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.database import diagnostics


@pytest.mark.asyncio
async def test_sqlite_file_uri_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "space # percent %.db"
    with closing(sqlite3.connect(path)):
        pass
    url = URL.create(
        "sqlite+aiosqlite", database=path.as_uri(), query={"uri": "true", "mode": "rw"}
    )
    settings = Settings(database_url=SecretStr(url.render_as_string(hide_password=False)))
    before = path.read_bytes()
    assert await diagnostics.current_heads(settings) == ()
    assert path.read_bytes() == before


@pytest.mark.asyncio
async def test_disappearing_database_is_not_recreated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "removed.db"
    with closing(sqlite3.connect(path)):
        pass
    original = diagnostics.create_engine

    def remove_before_connect(settings: Settings, *, null_pool: bool = False) -> AsyncEngine:
        # 在存在性检查后移除专用临时文件，真实连接必须失败且不能重新建库。
        path.unlink()
        return original(settings, null_pool=null_pool)

    monkeypatch.setattr(diagnostics, "create_engine", remove_before_connect)
    with pytest.raises(OperationalError):
        await diagnostics.current_heads(
            Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{path}"))
        )
    assert not path.exists()
