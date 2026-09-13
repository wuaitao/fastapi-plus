"""统一配置 structlog 和标准 logging"""

import logging
import logging.config

import structlog
from structlog.typing import Processor

from app.core.config import Environment, Settings
from app.core.logging.redaction import redact_sensitive_fields


def configure_logging(settings: Settings) -> None:
    """由 Bootstrap 显式配置进程级日志；重复调用不会增加 Handler"""
    # 输出流故障时，标准 logging 的调试回退会打印原始记录和当前异常。
    logging.raiseExceptions = False
    log_format = settings.log_format or (
        "json" if settings.environment is Environment.PRODUCTION else "console"
    )
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "foreign_pre_chain": [structlog.stdlib.ExtraAdder(), *shared],
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        redact_sensitive_fields,
                        renderer,
                    ],
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": settings.log_level,
                    "stream": "ext://sys.stderr",
                    "formatter": "structured",
                }
            },
            "root": {"handlers": ["console"], "level": settings.log_level},
            "loggers": {
                "uvicorn": {"handlers": [], "propagate": True},
                "uvicorn.error": {"handlers": [], "propagate": True},
                # 应用统一记录完成事件，禁用带原始 query 的重复访问日志。
                "uvicorn.access": {"handlers": [], "propagate": False},
                # SQL echo=False 不限制驱动日志；应用 DEBUG 也不能输出 SQL 和参数。
                "sqlalchemy.engine": {"handlers": [], "level": "WARNING", "propagate": True},
                "sqlalchemy.pool": {"handlers": [], "level": "WARNING", "propagate": True},
                "aiosqlite": {"handlers": [], "level": "WARNING", "propagate": True},
            },
        }
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
