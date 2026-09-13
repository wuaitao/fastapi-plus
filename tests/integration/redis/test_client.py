"""Redis 外部服务边界及 Web 部分启动失败的资源清理。"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy import event

from app.bootstrap.application import create_app
from app.core.config import Settings


@pytest_asyncio.fixture
async def redis_server() -> AsyncIterator[str]:
    # 仅模拟外部 Redis 的 PING 协议；被测客户端仍是真实 redis-py 连接池。
    import asyncio

    async def respond(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                count = int(line[1:])
                parts: list[bytes] = []
                for _ in range(count):
                    size = int((await reader.readline())[1:])
                    parts.append(await reader.readexactly(size))
                    await reader.readexactly(2)
                writer.write(b"+PONG\r\n" if parts[0].upper() == b"PING" else b"+OK\r\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(respond, "127.0.0.1", 0)
    try:
        yield f"redis://127.0.0.1:{server.sockets[0].getsockname()[1]}/0"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_redis_lifecycle(redis_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[Redis] = []
    original = Redis.aclose

    async def close(client: Redis, close_connection_pool: bool | None = None) -> None:
        closed.append(client)
        await original(client, close_connection_pool)

    monkeypatch.setattr(Redis, "aclose", close)
    app = create_app(Settings(redis_enabled=True, redis_url=SecretStr(redis_server)))
    async with app.router.lifespan_context(app):
        client = app.state.redis
        assert isinstance(client, Redis)
    assert closed == [client]
    assert not hasattr(app.state, "redis")
    assert not hasattr(app.state, "engine")


@pytest.mark.asyncio
async def test_redis_failure_closes_pool_and_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[Redis] = []
    disposed: list[object] = []
    original = Redis.aclose

    async def ping(client: Redis) -> bool:
        raise ConnectionError("redis://:private-password@host")

    async def close(client: Redis, close_connection_pool: bool | None = None) -> None:
        closed.append(client)
        await original(client, close_connection_pool)

    monkeypatch.setattr(Redis, "ping", ping)
    monkeypatch.setattr(Redis, "aclose", close)
    app: FastAPI = create_app(
        Settings(redis_enabled=True, redis_url=SecretStr("redis://localhost"))
    )
    from sqlalchemy import Engine

    on_dispose = disposed.append
    event.listen(Engine, "engine_disposed", on_dispose)
    try:
        with pytest.raises(RuntimeError, match="Redis 连接失败") as caught:
            async with app.router.lifespan_context(app):
                pytest.fail("启动必须失败")
        assert "private-password" not in str(caught.value)
        assert len(closed) == len(disposed) == 1
        assert not hasattr(app.state, "engine")
    finally:
        event.remove(Engine, "engine_disposed", on_dispose)
