"""集中注册 Web 中间件，运行时上下文由 Core 管理"""

from fastapi import FastAPI

from app.core.logging.context import RequestContextMiddleware


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
