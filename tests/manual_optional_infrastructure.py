"""显式启动隔离 Redis 与独立 Worker 进程，不连接已有服务。"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest
from celery import Celery
from pydantic import SecretStr
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Environment, Settings
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.celery.bridge import run_async_handler
from app.infrastructure.redis.client import create_redis_client
from app.modules.user.model import User


class SyncPing(Protocol):
    def ping(self) -> bool: ...


@pytest.fixture
def isolated_redis(tmp_path: Path) -> Iterator[str]:
    executable = os.environ.get("REDIS_SERVER_EXECUTABLE") or shutil.which("redis-server")
    assert executable, "请配置 REDIS_SERVER_EXECUTABLE，指向测试用 redis-server"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    # 无持久化、仅监听回环、使用临时目录，不读取开发者 redis.conf。
    with (tmp_path / "redis.log").open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [
                executable,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        client = Redis(host="127.0.0.1", port=port, socket_timeout=0.2, socket_connect_timeout=0.2)
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, (tmp_path / "redis.log").read_text(encoding="utf-8")
                try:
                    if cast(SyncPing, client).ping():
                        break
                except RedisConnectionError:
                    pass
                assert time.monotonic() < deadline, "测试 Redis 启动超时"
                time.sleep(0.1)
            yield f"redis://127.0.0.1:{port}/0"
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=10)


def test_real_redis_and_independent_worker(isolated_redis: str, tmp_path: Path) -> None:
    settings = Settings(
        environment=Environment.TESTING,
        redis_enabled=True,
        redis_url=SecretStr(isolated_redis),
        celery_enabled=True,
        celery_broker_url=SecretStr(isolated_redis),
        celery_result_backend=SecretStr(isolated_redis),
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'worker.db'}"),
    )

    async def ping() -> None:
        client = await create_redis_client(settings)
        assert client is not None
        await client.aclose()

    with asyncio.Runner() as runner:
        runner.run(ping())

    async def seed(session: AsyncSession) -> None:
        connection = await session.connection()
        await connection.run_sync(User.metadata.create_all)
        session.add(User(username="worker-user", password_hash="unused-test-hash"))
        await session.commit()

    run_async_handler(settings, seed)
    app = create_celery_app(settings)
    assert isinstance(app, Celery)
    environment = dict(os.environ)
    environment.update(
        ENVIRONMENT="testing",
        CELERY_ENABLED="true",
        CELERY_BROKER_URL=isolated_redis,
        CELERY_RESULT_BACKEND=isolated_redis,
        DATABASE_URL=settings.database_url.get_secret_value(),
        LOG_FORMAT="json",
        PYTHONIOENCODING="utf-8",
    )
    worker_log = tmp_path / "worker.log"
    with worker_log.open("w", encoding="utf-8") as output:
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.bootstrap.worker:celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--loglevel=INFO",
            ],
            cwd=tmp_path,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            # 真正经 Redis 入队，由另一个进程读取 SQLite 并写入 JSON 结果后端。
            first = app.send_task(
                "user.status", args=(1,), headers={"correlation_id": "real-trace"}
            )
            assert first.get(timeout=20) == {"user_id": 1, "is_active": True}
            missing = app.send_task("user.status", args=(999,))
            missing.get(timeout=20, propagate=False)
            assert missing.failed()
            second = app.send_task("user.status", args=(1,))
            assert second.get(timeout=20) == {"user_id": 1, "is_active": True}
            assert worker.poll() is None
            missing_id, second_id = missing.id, second.id
            # 在 Redis 仍存活时释放结果订阅，避免析构阶段向已关闭的服务重连。
            first.forget()
            missing.forget()
            second.forget()
            del first, missing, second
        finally:
            worker.terminate()
            worker.wait(timeout=10)
            app.close()
            # AsyncResult 的回调可能形成循环引用，须在临时 Redis 关闭前完成析构。
            gc.collect()
    records = [
        json.loads(line)
        for line in worker_log.read_text(encoding="utf-8").splitlines()
        if line.startswith("{")
    ]
    finished = [record for record in records if record.get("event") == "task.finished"]
    assert len(finished) == 3
    assert finished[0]["correlation_id"] == "real-trace"
    assert finished[1]["correlation_id"] == missing_id
    assert finished[2]["correlation_id"] == second_id
    assert all(record["retry_count"] == 0 for record in finished)
