"""使用真实 SQLite 验证用户查询、哈希、失败回滚和竞争写入。"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from argon2 import PasswordHasher
from pydantic import SecretStr
from sqlalchemy import event, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import BusinessException
from app.database.engine import create_engine
from app.database.session import create_session_factory, session_scope
from app.modules.user.errors import USER_ALREADY_EXISTS, is_user_unique_violation
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.modules.user.schema import UserCreate, UserUpdate
from app.modules.user.service import UserService


@pytest_asyncio.fixture
async def user_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(
        Settings(database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}"))
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(User.metadata.create_all)
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repository_does_not_commit(user_engine: AsyncEngine) -> None:
    factory = create_session_factory(user_engine)
    async with session_scope(factory) as session:
        repository = UserRepository(session)
        user = await repository.create(
            User(username="alice", email="alice@example.com", password_hash="test-hash")
        )
        assert isinstance(user.id, int)
        assert await repository.get_by_username("alice") is user
        assert await repository.get_by_email("alice@example.com") is user
        assert await repository.get_by_username("missing") is None
        assert await repository.get_by_email("missing@example.com") is None
    async with session_scope(factory) as session:
        assert (await UserRepository(session).paginate()).total == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["username", "email"])
async def test_concurrent_create_conflict(
    user_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    barrier = asyncio.Barrier(2)
    original_create = UserRepository.create

    async def simultaneous_create(self: UserRepository, instance: User) -> User:
        # 仅同步写入时机，所有查询、INSERT 和事务仍使用真实数据库。
        await barrier.wait()
        return await original_create(self, instance)

    monkeypatch.setattr(UserRepository, "create", simultaneous_create)
    factory = create_session_factory(user_engine)

    async def create(index: int) -> int | BusinessException:
        async with session_scope(factory) as session:
            service = UserService(UserRepository(session), PasswordHasher())
            try:
                return (
                    await service.create_user(
                        UserCreate(
                            username="alice" if field == "username" else f"user-{index}",
                            email="alice@example.com" if field == "email" else None,
                            password=SecretStr("test-password"),
                        )
                    )
                ).id
            except BusinessException as error:
                assert not session.in_transaction()
                assert (await service.repository.paginate()).total == 1
                return error

    results = await asyncio.gather(create(1), create(2))
    assert sum(isinstance(result, int) for result in results) == 1
    errors = [result for result in results if isinstance(result, BusinessException)]
    assert len(errors) == 1
    assert errors[0].descriptor == USER_ALREADY_EXISTS


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["username", "email"])
async def test_update_constraint_fallback(
    user_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    factory = create_session_factory(user_engine)
    async with session_scope(factory) as session:
        service = UserService(UserRepository(session), PasswordHasher())
        first = await service.create_user(
            UserCreate(
                username="alice", email="alice@example.com", password=SecretStr("test-password")
            )
        )
        second = await service.create_user(
            UserCreate(username="bob", email="bob@example.com", password=SecretStr("test-password"))
        )
        second_id = second.id
        conflict_value = getattr(first, field)

        async def stale_lookup(self: UserRepository, value: str) -> User | None:
            # 模拟预检查与写入之间的变化，保留真实 UPDATE 和数据库错误。
            return None

        monkeypatch.setattr(UserRepository, f"get_by_{field}", stale_lookup)
        with pytest.raises(BusinessException) as error:
            await service.update_user(second_id, UserUpdate.model_validate({field: conflict_value}))
        assert error.value.descriptor == USER_ALREADY_EXISTS
        assert not session.in_transaction()
        restored = await service.get_user(second_id)
        assert (restored.username, restored.email) == ("bob", "bob@example.com")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
async def test_failed_commit_rolls_back(user_engine: AsyncEngine, operation: str) -> None:
    factory = create_session_factory(user_engine)
    async with session_scope(factory) as session:
        service = UserService(UserRepository(session), PasswordHasher())
        user = await service.create_user(
            UserCreate(username="alice", password=SecretStr("test-password"))
        )
        user_id = user.id

        def fail_commit(sync_session: Session) -> None:
            # Repository 已执行真实 flush；在提交边界失败才能验证 Service 的回滚责任。
            raise RuntimeError("提交失败测试")

        event.listen(session.sync_session, "before_commit", fail_commit)
        try:
            with pytest.raises(RuntimeError, match="提交失败测试"):
                if operation == "create":
                    await service.create_user(
                        UserCreate(username="bob", password=SecretStr("test-password"))
                    )
                elif operation == "update":
                    await service.update_user(user_id, UserUpdate(username="bob"))
                else:
                    await service.delete_user(user_id, actor_id=user_id + 1)
            assert not session.in_transaction()
        finally:
            event.remove(session.sync_session, "before_commit", fail_commit)
    async with session_scope(factory) as session:
        users = await UserRepository(session).list()
        assert len(users) == 1
        assert (users[0].id, users[0].username) == (user_id, "alice")


@pytest.mark.asyncio
async def test_unrelated_integrity_error_is_not_duplicate(user_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(user_engine)) as session:
        service = UserService(UserRepository(session), PasswordHasher())

        def before_flush(sync_session: Session, context: object, instances: object) -> None:
            # 制造真实 NOT NULL 失败，验证其不会被笼统转换为“用户已存在”。
            sync_session.execute(insert(User).values(username="invalid", password_hash=None))

        event.listen(session.sync_session, "before_flush", before_flush)
        try:
            with pytest.raises(IntegrityError) as error:
                await service.create_user(
                    UserCreate(username="alice", password=SecretStr("test-password"))
                )
            assert not is_user_unique_violation(error.value)
            assert not session.in_transaction()
            assert (await service.repository.paginate()).total == 0
        finally:
            event.remove(session.sync_session, "before_flush", before_flush)


@pytest.mark.asyncio
async def test_service_rejects_self_delete(user_engine: AsyncEngine) -> None:
    async with session_scope(create_session_factory(user_engine)) as session:
        service = UserService(UserRepository(session), PasswordHasher())
        user = await service.create_user(
            UserCreate(username="operator", password=SecretStr("test-password"))
        )
        user_id = user.id
        with pytest.raises(BusinessException) as error:
            await service.delete_user(user_id, actor_id=user_id)
        assert error.value.descriptor.key == "USER_SELF_DELETE"
        assert not session.in_transaction()
        assert (await service.get_user(user_id)).username == "operator"
