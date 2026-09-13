"""认证测试使用真实迁移、真实数据库和完整依赖链。"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from app.bootstrap.application import create_app
from app.core.config import get_settings
from app.core.security.password import get_password_hasher
from app.database.session import session_scope
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.modules.user.schema import UserCreate
from app.modules.user.service import UserService

PASSWORD = "auth-test-password"


@pytest_asyncio.fixture
async def auth_app(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[FastAPI]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-" * 3)
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "alembic"))
    # Alembic 使用独立事件循环，在工作线程执行迁移。
    await asyncio.to_thread(command.upgrade, config, "head")
    app = create_app(get_settings())
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture
async def client(auth_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=auth_app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def users(auth_app: FastAPI) -> dict[str, User]:
    factory = cast(async_sessionmaker[AsyncSession], auth_app.state.session_factory)
    async with session_scope(factory) as session:
        service = UserService(UserRepository(session), get_password_hasher())
        result: dict[str, User] = {}
        for username in ("alice", "operator", "disabled"):
            user = await service.create_user(
                UserCreate(
                    username=username,
                    password=SecretStr(PASSWORD),
                    is_active=username != "disabled",
                )
            )
            if username == "operator":
                # 仅测试显式赋予管理权限，应用启动不创建任何账号。
                user.is_superuser = True
                await session.commit()
            result[username] = user
        return result
