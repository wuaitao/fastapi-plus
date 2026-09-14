"""应用工厂负责配置、生命周期和路由装配"""

from importlib.metadata import version

from fastapi import FastAPI

from app.bootstrap.exceptions import register_exception_handlers
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware import register_middleware
from app.bootstrap.providers import register_providers
from app.bootstrap.routers import register_routers
from app.common.response import ErrorResponse
from app.core.config import Settings, get_settings
from app.core.logging.config import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """根据配置装配独立 Web 应用，资源启停由 lifespan 管理"""
    settings = settings if settings is not None else get_settings()
    configure_logging(settings)
    app = FastAPI(
        title=settings.app_title,
        summary=settings.app_summary,
        description=settings.app_description,
        version=version("fastapi-plus"),
        debug=settings.debug,
        openapi_url="/openapi.json" if settings.openapi_enabled else None,
        lifespan=lifespan,
        responses={
            status: {
                "model": ErrorResponse,
                "description": description,
                "headers": {"X-Request-ID": {"schema": {"type": "string"}}},
            }
            for status, description in (
                (404, "Not found"),
                (405, "Method not allowed"),
                (413, "Request body too large"),
                (422, "Validation error"),
                (429, "Too many requests"),
                (500, "Internal server error"),
                (503, "Service unavailable"),
            )
        },
    )
    app.state.settings = settings
    register_providers(app, settings)
    register_exception_handlers(app)
    if settings.metrics_enabled:
        try:
            from app.infrastructure.metrics import register_metrics
        except ImportError:
            raise RuntimeError("指标依赖未安装，请安装 metrics extra") from None

        register_metrics(app)
    register_middleware(app, settings)
    register_routers(app)
    return app
