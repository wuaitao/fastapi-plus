"""集中同步到异步桥接，每次调用独占循环、引擎和 Session"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.database.engine import create_engine

T = TypeVar("T")


def run_async_handler(
    settings: Settings, handler: Callable[[AsyncSession], Coroutine[Any, Any, T]]
) -> T:
    async def invoke() -> T:
        engine = create_engine(settings, null_pool=True)
        try:
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
            # Session 关闭会回滚未提交事务；桥接不替 Service 提交。
            async with factory() as session:
                return await handler(session)
        finally:
            await engine.dispose()

    # 在 Worker 执行时才创建资源，避免 prefork 继承连接或跨循环复用。
    # Runner 同时等待异步生成器和线程池退出；任务文件不自行创建事件循环。
    with asyncio.Runner() as runner:
        return runner.run(invoke())
