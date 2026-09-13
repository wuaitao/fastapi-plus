"""每个入口创建独立 Session，业务事务由 Service 显式完成"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建异步 Session 工厂，保留提交后的已加载字段并关闭自动 flush。"""
    # 提交后保留已加载字段，避免异步序列化触发隐式 I/O。
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[AsyncSession]:
    """提供独立 Session，退出时关闭并回滚未提交事务。"""
    # close 会回滚未完成事务；正常退出也不隐式提交。
    async with factory() as session:
        yield session


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """从应用工厂取得请求独占的 Session，并在请求结束后释放。"""
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with session_scope(factory) as session:
        yield session
