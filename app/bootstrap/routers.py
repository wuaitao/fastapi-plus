"""通过 FastAPI 原生路由显式注册入口"""

from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

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


def register_routers(app: FastAPI) -> None:
    """显式挂载健康检查和业务路由，新增模块在此注册。"""
    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(user_router, prefix="/api/v1")
    app.include_router(file_router, prefix="/api/v1")
