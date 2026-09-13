"""集中注册 Web 中间件，运行时上下文由 Core 管理"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.exceptions.middleware import SafeExceptionMiddleware
from app.core.logging.context import RequestContextMiddleware


def register_middleware(app: FastAPI, settings: Settings) -> None:
    # 后注册的层先接收请求：上下文 → CORS → 安全异常兜底 → 路由。
    # 预检也有请求 ID/日志，未知异常先转响应再附加跨域头。
    app.add_middleware(SafeExceptionMiddleware)
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=False,
            allow_methods=("GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"),
            allow_headers=("Authorization", "Content-Type", "X-Request-ID"),
            expose_headers=("X-Request-ID", "Content-Disposition"),
        )
    app.add_middleware(RequestContextMiddleware)
