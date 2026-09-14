"""集中注册 Web 中间件，运行时上下文由 Core 管理"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings
from app.core.exceptions.middleware import SafeExceptionMiddleware
from app.core.logging.context import RequestContextMiddleware
from app.core.security.body_limit import BodyLimitMiddleware


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """集中装配请求上下文、可选跨域和安全异常边界"""
    # 请求方向：上下文 → 指标 → CORS → Host → 安全兜底 → 限额/限流 → 路由。
    # 预检也有请求 ID/日志，未知异常先转响应再附加跨域头。
    if settings.login_rate_limit_enabled:
        from app.infrastructure.redis.rate_limit import LoginRateLimitMiddleware

        app.add_middleware(LoginRateLimitMiddleware, settings=settings)
    app.add_middleware(BodyLimitMiddleware, max_body_size=settings.request_max_body_size)
    app.add_middleware(SafeExceptionMiddleware)
    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False
        )
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=False,
            allow_methods=("GET", "HEAD", "POST", "PATCH", "DELETE", "OPTIONS"),
            allow_headers=("Authorization", "Content-Type", "X-Request-ID"),
            expose_headers=("X-Request-ID", "Content-Disposition"),
        )
    if settings.metrics_enabled:
        from app.infrastructure.metrics import MetricsMiddleware

        app.add_middleware(MetricsMiddleware, metrics=app.state.metrics)
    app.add_middleware(RequestContextMiddleware)
