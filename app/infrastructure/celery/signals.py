"""将 Worker 日志接入 structlog，并通过消息头传播关联上下文"""

import logging
from typing import Any

import structlog
from celery.signals import setup_logging

from app.core.config import Settings
from app.core.logging.config import configure_logging


def propagate_context(headers: dict[str, Any] | None = None, **kwargs: Any) -> None:
    if headers is None:
        return
    context = structlog.contextvars.get_contextvars()
    correlation_id = context.get("correlation_id") or context.get("request_id")
    if correlation_id is not None:
        headers.setdefault("correlation_id", correlation_id)
    if headers.get("correlation_id") is not None:
        # Celery Worker 用消息属性覆盖同名保留字段，另存自定义头以保留业务关联 ID。
        headers["x_correlation_id"] = headers["correlation_id"]
    if context.get("actor_id") is not None:
        headers.setdefault("actor_id", context["actor_id"])
    # 隐藏事件与原生日志中的参数展示，消息体仍由 JSON serializer 正常处理。
    headers["argsrepr"] = "[REDACTED]"
    headers["kwargsrepr"] = "[REDACTED]"


class WorkerLogging:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def setup(self, **kwargs: Any) -> None:
        configure_logging(self.settings)
        # 原生任务日志会拼接结果、异常与任意参数，统一由 BaseTask 输出安全事件。
        # Broker 诊断仍可由 Celery 命令退出状态及应用启动错误定位。
        for name in ("celery", "kombu"):
            logger = logging.getLogger(name)
            logger.handlers = [logging.NullHandler()]
            logger.propagate = False

    def connect(self) -> None:
        setup_logging.connect(self.setup)
