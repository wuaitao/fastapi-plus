"""通过 FastAPI 原生路由显式注册入口"""

import asyncio
from typing import Literal, cast

from fastapi import APIRouter, FastAPI, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.database.diagnostics import check_connection
from app.infrastructure.redis.client import RedisPing
from app.modules.auth.router import router as auth_router
from app.modules.file.router import router as file_router
from app.modules.user.router import router as user_router

health_router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]


@health_router.get("/health", tags=["health"])
async def health() -> HealthResponse:
    """仅检查应用存活，不探测数据库或可选外部资源"""
    return HealthResponse(status="ok")


class ReadinessResponse(BaseModel):
    status: Literal["ok", "unavailable"]


@health_router.get(
    "/health/ready",
    tags=["health"],
    responses={503: {"model": ReadinessResponse, "description": "Dependencies unavailable"}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    """限时检查现有数据库池与已启用 Redis，不运行迁移或写入业务数据"""
    settings = cast(Settings, request.app.state.settings)
    response.headers["Cache-Control"] = "no-store"
    try:
        # 复用进程资源，避免每次探测另建连接池；超时也退出连接上下文。
        async with asyncio.timeout(settings.readiness_timeout):
            engine = cast(AsyncEngine, request.app.state.engine)
            await check_connection(engine)
            if settings.redis_enabled:
                await cast(RedisPing, request.app.state.redis).ping()
    except Exception:
        # 探针只返回健康状态，连接串、驱动异常和凭据不对外公开。
        response.status_code = 503
        return ReadinessResponse(status="unavailable")
    return ReadinessResponse(status="ok")


def register_routers(app: FastAPI) -> None:
    """显式挂载健康检查和业务路由，新增模块在此注册"""
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(file_router, prefix="/api/v1")
