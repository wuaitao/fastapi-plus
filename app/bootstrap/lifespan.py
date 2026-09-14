"""集中管理应用的启动与关闭"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.database.engine import create_engine
from app.database.session import create_session_factory
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.redis.client import create_redis_client

if TYPE_CHECKING:
    from celery import Celery
    from redis.asyncio import Redis


async def startup(app: FastAPI) -> None:
    """创建应用独立的引擎与工厂；连接按需打开，不建表或迁移"""
    settings = cast(Settings, app.state.settings)
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = await create_redis_client(settings)
    app.state.celery = create_celery_app(settings)
    if app.state.celery is not None:
        # 已启用的 Broker 在启动时检查；阻塞客户端不得占用 Web 事件循环。
        from asyncio import to_thread

        celery = app.state.celery

        def check_broker() -> None:
            """检查已启用的 Broker 连接，失败时仅返回安全提示"""
            try:
                with celery.connection_for_write() as connection:
                    connection.ensure_connection(max_retries=0)
            except Exception:
                raise RuntimeError("Celery Broker 连接失败，请检查配置与服务状态") from None

        await to_thread(check_broker)


async def shutdown(app: FastAPI) -> None:
    """启动部分失败时也释放已经创建的引擎"""
    celery = cast("Celery | None", getattr(app.state, "celery", None))
    redis = cast("Redis | None", getattr(app.state, "redis", None))
    try:
        if celery is not None:
            celery.close()
    finally:
        try:
            if redis is not None:
                await redis.aclose()
        finally:
            engine = cast(AsyncEngine | None, getattr(app.state, "engine", None))
            if engine is not None:
                await engine.dispose()
            for name in ("engine", "session_factory", "redis", "celery"):
                if hasattr(app.state, name):
                    delattr(app.state, name)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """统一管理启动与关闭，启动中途失败也释放已创建资源"""
    # 即使启动或运行阶段抛错，也执行集中关闭钩子。
    try:
        await startup(app)
        yield
    finally:
        await shutdown(app)
