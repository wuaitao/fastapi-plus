"""同一套迁移、事务与 HTTP 流程在三种真实数据库上执行。"""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from app.bootstrap.application import create_app
from app.core.config import get_settings
from app.core.exceptions import BusinessException
from app.core.security.password import get_password_hasher
from app.database.engine import create_engine
from app.database.session import session_scope
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.modules.user.schema import UserCreate
from app.modules.user.service import UserService


@pytest_asyncio.fixture
async def release_app(
    request: pytest.FixtureRequest,
    repository_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[FastAPI]:
    backend = cast(str, request.config.getoption("--release-database"))
    if backend == "sqlite":
        database_url = SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'release.db'}")
    else:
        raw_url = os.environ.get("FASTPLUS_TEST_DATABASE_URL")
        if not raw_url:
            pytest.fail("外部数据库验收必须设置 FASTPLUS_TEST_DATABASE_URL", pytrace=False)
        database_url = SecretStr(raw_url)
        url = make_url(database_url.get_secret_value())
        # 名称和空库双重检查：迁移往返会删除表，绝不能指向开发或生产业务库。
        if url.get_backend_name() != backend or not (url.database or "").startswith(
            "fastplus_test_"
        ):
            pytest.fail("要求后端匹配且数据库名以 fastplus_test_ 开头的专用空库", pytrace=False)
    monkeypatch.setenv("DATABASE", backend)
    monkeypatch.setenv("DATABASE_URL", database_url.get_secret_value())
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    settings = get_settings()
    engine = create_engine(settings, null_pool=True)
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "alembic"))
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            views = await connection.run_sync(lambda conn: inspect(conn).get_view_names())
        if tables or views:
            pytest.fail("发布测试拒绝操作非空数据库", pytrace=False)
        # Alembic 自建事件循环，在线程中运行；测试不使用 create_all 代替迁移。
        try:
            await asyncio.to_thread(command.upgrade, config, "head")
            await asyncio.to_thread(command.check, config)
            async with engine.connect() as connection:
                assert set(
                    await connection.run_sync(lambda conn: inspect(conn).get_table_names())
                ) == {"users", "files", "alembic_version"}
            app = create_app(settings)
            async with app.router.lifespan_context(app):
                yield app
        finally:
            await asyncio.to_thread(command.downgrade, config, "base")
            async with engine.begin() as connection:
                assert await connection.run_sync(lambda conn: inspect(conn).get_table_names()) == [
                    "alembic_version"
                ]
            await asyncio.to_thread(command.upgrade, config, "head")
            await asyncio.to_thread(command.check, config)
            await asyncio.to_thread(command.downgrade, config, "base")
            async with engine.begin() as connection:
                await connection.run_sync(
                    lambda conn: Table("alembic_version", MetaData()).drop(conn)
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_release_repository_transactions(release_app: FastAPI) -> None:
    factory = cast(async_sessionmaker[AsyncSession], release_app.state.session_factory)
    async with session_scope(factory) as session:
        repository = UserRepository(session)
        assert (await repository.paginate()).total == 0
        # Repository 的 flush 不能隐式提交；关闭入口后新 Session 不应看到该记录。
        await repository.create(User(username="uncommitted", password_hash="test-only-hash"))
    async with session_scope(factory) as session:
        assert await UserRepository(session).get_by_username("uncommitted") is None
        service = UserService(UserRepository(session), get_password_hasher())
        first = await service.create_user(
            UserCreate(username="first", password=SecretStr("test-only-password"))
        )
        first_id = first.id
        assert first_id > 0
        assert first.created_at.utcoffset() == timedelta(0)
        assert first.password_hash.startswith("$argon2id$")
        with pytest.raises(BusinessException) as conflict:
            await service.create_user(
                UserCreate(username="first", password=SecretStr("test-only-password"))
            )
        assert conflict.value.descriptor.code == 30001
        # 唯一冲突回滚后同一 Session 必须仍可提交新用户；两条空邮箱不应冲突。
        second = await service.create_user(
            UserCreate(username="second", password=SecretStr("test-only-password"))
        )
        assert second.id > first_id
        page = await service.repository.paginate(page=2, size=1)
        assert page.total == 2
        assert [item.id for item in page.items] == [second.id]
    async with session_scope(factory) as session:
        assert (await UserRepository(session).paginate()).total == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["username", "email"])
async def test_release_concurrent_unique_conflict(release_app: FastAPI, field: str) -> None:
    factory = cast(async_sessionmaker[AsyncSession], release_app.state.session_factory)

    async def create(index: int) -> int:
        async with session_scope(factory) as session:
            service = UserService(UserRepository(session), get_password_hasher())
            try:
                await service.create_user(
                    UserCreate(
                        username="same" if field == "username" else f"user-{index}",
                        email="same@example.com" if field == "email" else None,
                        password=SecretStr("test-only-password"),
                    )
                )
            except BusinessException as error:
                assert error.descriptor.code == 30001
                assert not session.in_transaction()
                return 409
            return 201

    # 独立 Session 竞争同一唯一键，必须由数据库裁决且由 Service 恢复失败事务。
    assert sorted(await asyncio.gather(create(1), create(2))) == [201, 409]
    async with session_scope(factory) as session:
        assert (await UserRepository(session).paginate()).total == 1


@pytest.mark.asyncio
async def test_release_auth_user_file_flow(release_app: FastAPI, tmp_path: Path) -> None:
    factory = cast(async_sessionmaker[AsyncSession], release_app.state.session_factory)
    password = "release-test-password"
    async with session_scope(factory) as session:
        service = UserService(UserRepository(session), get_password_hasher())
        assert (await service.repository.paginate()).total == 0
        await service.create_superuser(
            UserCreate(username="operator", password=SecretStr(password))
        )
    async with AsyncClient(
        transport=ASGITransport(app=release_app), base_url="http://test"
    ) as client:
        login = await client.post(
            "/api/v1/auth/login", json={"username": "operator", "password": password}
        )
        assert login.status_code == 200
        assert login.headers["cache-control"] == "no-store"
        pair = login.json()["data"]
        admin = {"Authorization": f"Bearer {pair['access_token']}"}
        created = await client.post(
            "/api/v1/users", json={"username": "owner", "password": password}, headers=admin
        )
        assert created.status_code == 201
        user = created.json()["data"]
        assert isinstance(user["id"], str)
        assert "password" not in user and "password_hash" not in user
        owner_login = await client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": password}
        )
        assert owner_login.status_code == 200
        owner_pair = owner_login.json()["data"]
        owner = {"Authorization": f"Bearer {owner_pair['access_token']}"}
        assert (await client.get("/api/v1/auth/me", headers=owner)).json()["data"] == user
        assert (await client.get("/api/v1/users", headers=owner)).status_code == 403
        assert (await client.get("/api/v1/users")).status_code == 401
        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": owner_pair["refresh_token"]}
        )
        assert refresh.status_code == 200
        assert refresh.json()["data"]["access_token"] != owner_pair["access_token"]
        assert (await client.post("/api/v1/auth/logout", headers=owner)).status_code == 200
        # 默认退出是无状态语义，旧令牌仍有效；不能把它误报为服务端撤销。
        assert (await client.get("/api/v1/auth/me", headers=owner)).status_code == 200
        for visibility in ("private", "public"):
            uploaded = await client.post(
                "/api/v1/files",
                headers=owner,
                data={"visibility": visibility},
                files={"file": ("发布验证.txt", "内容".encode(), "text/plain")},
            )
            assert uploaded.status_code == 201
            file = uploaded.json()["data"]
            path = f"/api/v1/files/{file['id']}"
            anonymous = await client.get(path + "/download")
            assert anonymous.status_code == (401 if visibility == "private" else 200)
            downloaded = await client.get(path + "/download", headers=owner)
            assert downloaded.content == "内容".encode()
            assert downloaded.headers["cache-control"] == "no-store"
            assert "attachment" in downloaded.headers["content-disposition"]
            assert (await client.delete(path, headers=owner)).status_code == 200
            assert (await client.get(path, headers=admin)).status_code == 404
        assert not [path for path in (tmp_path / "storage").rglob("*") if path.is_file()]
        # 保留文件后删除所有者，验证真实数据库的 ON DELETE SET NULL 及管理员接管。
        uploaded = await client.post(
            "/api/v1/files", headers=owner, files={"file": ("orphan.txt", b"orphan", "text/plain")}
        )
        assert uploaded.status_code == 201
        path = f"/api/v1/files/{uploaded.json()['data']['id']}"
        assert (
            await client.delete(f"/api/v1/users/{user['id']}", headers=admin)
        ).status_code == 200
        assert (await client.get(path, headers=admin)).json()["data"]["created_by"] is None
        assert (await client.get("/api/v1/auth/me", headers=owner)).status_code == 401
        assert (await client.get(path + "/download", headers=admin)).content == b"orphan"
        assert (await client.delete(path, headers=admin)).status_code == 200
