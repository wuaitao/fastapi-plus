"""API 使用真实迁移创建的临时数据库，每次请求独立提交事务。"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from alembic import command
from app.bootstrap.application import create_app
from app.core.config import Settings, get_settings
from app.modules.auth.dependencies import get_current_user
from app.modules.user.model import User


@pytest.fixture
def user_settings(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "alembic"))
    command.upgrade(config, "head")
    return get_settings()


@pytest_asyncio.fixture
async def client(user_settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(user_settings)
    # CRUD 用例保留空库断言；真实认证与权限链由 auth API 用例独立覆盖。
    app.dependency_overrides[get_current_user] = lambda: User(
        id=9223372036854775807, username="test-operator", is_active=True, is_superuser=True
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
