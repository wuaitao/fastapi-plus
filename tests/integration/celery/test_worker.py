"""真实 SQLite、Celery tracer 与非 eager Worker 的任务契约。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import structlog
from celery import Celery
from celery.contrib.testing.worker import start_worker
from celery.signals import before_task_publish
from kombu.exceptions import EncodeError
from pydantic import SecretStr
from sqlalchemy import Engine, event, select
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.application import create_app
from app.core.config import Environment, Settings
from app.core.exceptions import BusinessException
from app.core.logging.config import configure_logging
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.celery.base import TransientTaskError
from app.infrastructure.celery.bridge import run_async_handler
from app.modules.user.model import User
from app.modules.user.tasks import user_status_handler


@pytest.fixture
def task_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment=Environment.TESTING,
        log_format="json",
        celery_enabled=True,
        celery_broker_url=SecretStr("memory://"),
        celery_result_backend=SecretStr("cache+memory://"),
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}"),
    )


@pytest.fixture
def task_app(task_settings: Settings) -> Iterator[Celery]:
    from app.bootstrap.worker import create_worker

    app = create_worker(task_settings)
    assert app is not None
    # 内存 Broker 是进程全局传输，队列名独立以免失败用例残留消息影响其他 Worker。
    app.conf.task_default_queue = f"test-{uuid4().hex}"

    async def seed(session: AsyncSession) -> None:
        connection = await session.connection()
        await connection.run_sync(User.metadata.create_all)
        session.add(User(username="task-user", password_hash="unused-test-hash", is_active=True))
        await session.commit()

    run_async_handler(task_settings, seed)
    try:
        yield app
    finally:
        app.close()


def test_celery_json_configuration_and_optional_backend(task_app: Celery) -> None:
    assert task_app.conf.task_serializer == task_app.conf.result_serializer == "json"
    assert task_app.conf.accept_content == task_app.conf.result_accept_content == ["json"]
    assert not task_app.conf.task_always_eager
    app = create_celery_app(Settings(celery_enabled=True, celery_broker_url=SecretStr("memory://")))
    assert app is not None
    try:
        assert app.conf.task_ignore_result
        assert app.conf.result_backend is None
    finally:
        app.close()


def test_handler_and_permanent_failure(task_app: Celery, task_settings: Settings) -> None:
    async def handler(session: AsyncSession) -> dict[str, int | bool]:
        return await user_status_handler(session, 1)

    assert run_async_handler(task_settings, handler) == {"user_id": 1, "is_active": True}
    task = task_app.tasks["user.status"]
    # throw=True 保留应用异常类型；结果后端会使用 Celery 原生异常序列化包装。
    with pytest.raises(BusinessException, match="User not found"):
        task.apply(args=(999,), throw=True)
    for value in (0, -1, True, "1"):
        invalid = task.apply(args=(value,))
        assert invalid.failed()
        assert isinstance(invalid.result, ValueError)


def test_no_orm_arguments(task_app: Celery) -> None:
    user = User(username="must-not-serialize", password_hash="sensitive-hash")
    with pytest.raises(EncodeError):
        task_app.tasks["user.status"].apply_async(args=(user,))
    eager = task_app.tasks["user.status"].apply(args=(user,))
    assert eager.failed() and isinstance(eager.result, TypeError)


@pytest.mark.parametrize("failures", [0, 2, 5])
def test_retry_limits_and_context(
    task_app: Celery, task_settings: Settings, capsys: pytest.CaptureFixture[str], failures: int
) -> None:
    attempts: list[dict[str, Any]] = []
    disposed: list[Engine] = []

    def disconnect(
        connection: Connection,
        cursor: DBAPICursor,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("SELECT"):
            attempts.append(structlog.contextvars.get_contextvars())
            if len(attempts) <= failures:
                # 在驱动边界注入失效连接；Wrapper/Handler/Service/Repository 真实执行。
                raise DBAPIError(
                    statement,
                    None,
                    ConnectionError("private-driver-error"),
                    connection_invalidated=True,
                )

    configure_logging(task_settings)
    event.listen(Engine, "before_cursor_execute", disconnect)
    on_dispose = disposed.append
    event.listen(Engine, "engine_disposed", on_dispose)
    previous = {"request_id": "caller-context"}
    structlog.contextvars.bind_contextvars(**previous)
    try:
        task = task_app.tasks["user.status"]
        result = task.apply(args=(1,), headers={"correlation_id": "trace-123", "actor_id": "7"})
        assert len(attempts) == min(failures + 1, 4)
        assert len(disposed) == len(attempts)
        assert [context["retry_count"] for context in attempts] == list(range(len(attempts)))
        assert all(context["correlation_id"] == "trace-123" for context in attempts)
        assert all(context["actor_id"] == "7" for context in attempts)
        assert all(context["task_name"] == "user.status" for context in attempts)
        assert structlog.contextvars.get_contextvars() == previous
        if failures <= 3:
            assert result.successful()
            assert result.result == {"user_id": 1, "is_active": True}
        else:
            assert result.failed() and isinstance(result.result, TransientTaskError)
        logs = capsys.readouterr().err
        assert "private-driver-error" not in logs
        finished = [json.loads(line) for line in logs.splitlines() if '"task.finished"' in line]
        assert len(finished) == len(attempts)
        assert all(record["duration_ms"] >= 0 for record in finished)
    finally:
        event.remove(Engine, "before_cursor_execute", disconnect)
        event.remove(Engine, "engine_disposed", on_dispose)


def test_bridge_rolls_back_and_uses_independent_resources(task_settings: Settings) -> None:
    sessions: list[AsyncSession] = []
    loops: list[asyncio.AbstractEventLoop] = []
    engines: list[Engine] = []

    async def uncommitted(session: AsyncSession) -> None:
        sessions.append(session)
        loops.append(asyncio.get_running_loop())
        connection = await session.connection()
        await connection.run_sync(User.metadata.create_all)
        await session.commit()
        session.add(User(username="rolled-back", password_hash="unused-test-hash"))
        await session.flush()
        raise ValueError("handler failed")

    async def inspect(session: AsyncSession) -> None:
        sessions.append(session)
        loops.append(asyncio.get_running_loop())
        assert list(await session.scalars(select(User))) == []

    on_dispose = engines.append
    event.listen(Engine, "engine_disposed", on_dispose)
    try:
        with pytest.raises(ValueError, match="handler failed"):
            run_async_handler(task_settings, uncommitted)
        run_async_handler(task_settings, inspect)
        assert sessions[0] is not sessions[1]
        assert all(not session.in_transaction() for session in sessions)
        assert loops[0] is not loops[1] and all(loop.is_closed() for loop in loops)
        assert len(engines) == 2 and engines[0] is not engines[1]
    finally:
        event.remove(Engine, "engine_disposed", on_dispose)


def test_non_eager_worker_and_publish_context(
    task_app: Celery, task_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    published: list[dict[str, Any]] = []

    def capture(headers: dict[str, Any], **kwargs: Any) -> None:
        published.append(dict(headers))

    before_task_publish.connect(capture)
    configure_logging(task_settings)
    try:
        with start_worker(task_app, pool="solo", concurrency=1, perform_ping_check=False):
            structlog.contextvars.bind_contextvars(request_id="web-request", actor_id="42")
            first = task_app.tasks["user.status"].apply_async(args=(1,))
            assert first.get(timeout=10) == {"user_id": 1, "is_active": True}
            structlog.contextvars.clear_contextvars()
            second = task_app.tasks["user.status"].apply_async(args=(1,))
            assert second.get(timeout=10) == {"user_id": 1, "is_active": True}
        assert published[0]["correlation_id"] == "web-request"
        assert published[0]["actor_id"] == "42"
        assert published[0]["argsrepr"] == published[0]["kwargsrepr"] == "[REDACTED]"
        assert "actor_id" not in published[1] and "correlation_id" not in published[1]
        finished = [
            json.loads(line)
            for line in capsys.readouterr().err.splitlines()
            if '"task.finished"' in line
        ]
        assert finished[0]["correlation_id"] == "web-request"
        assert finished[0]["actor_id"] == "42"
        assert finished[1]["correlation_id"] == second.id
        assert "actor_id" not in finished[1]
    finally:
        before_task_publish.disconnect(capture)


@pytest.mark.asyncio
async def test_enabled_web_broker_lifecycle(task_settings: Settings) -> None:
    app = create_app(task_settings)
    async with app.router.lifespan_context(app):
        assert app.state.redis is None
        assert isinstance(app.state.celery, Celery)
    assert not hasattr(app.state, "celery")
    assert not hasattr(app.state, "engine")
