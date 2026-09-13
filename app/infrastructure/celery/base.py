"""任务执行上下文、JSON 边界及有限重试的公共基类"""

from __future__ import annotations

import json
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from celery import Task
from celery.exceptions import Retry

if TYPE_CHECKING:
    TaskBase = Task[..., object]
else:
    # Celery 运行时 Task 不支持泛型下标；类型参数仅供静态检查。
    TaskBase = Task

logger = structlog.get_logger(__name__)


class TransientTaskError(Exception):
    """仅在任务明确识别出暂时性故障后使用，不携带底层异常文本"""


class BaseTask(TaskBase):
    abstract = True
    autoretry_for = (TransientTaskError,)
    max_retries = 3
    retry_backoff = 1
    retry_backoff_max = 60
    retry_jitter = True

    def __call__(self, *args: Any, **kwargs: Any) -> object:
        """隔离任务上下文，验证 JSON 边界并记录完成或失败事件。"""
        previous = structlog.contextvars.get_contextvars()
        structlog.contextvars.clear_contextvars()
        headers = self.request.headers or {}
        structlog.contextvars.bind_contextvars(
            task_id=self.request.id,
            task_name=self.name,
            retry_count=self.request.retries,
            correlation_id=(
                headers.get("x_correlation_id")
                or headers.get("correlation_id")
                or self.request.id
                or uuid4().hex
            ),
        )
        if isinstance(headers.get("actor_id"), (str, int)):
            structlog.contextvars.bind_contextvars(actor_id=headers["actor_id"])
        started = perf_counter()
        outcome = "success"
        try:
            # 同时保护直接调用/eager 路径；不允许自定义 encoder 把 ORM 混入消息。
            json.dumps([args, kwargs], allow_nan=False)
            # Celery tracer 已压入当前 request，super().__call__ 会覆盖其 headers/retries。
            result = self.run(*args, **kwargs)
            json.dumps(result, allow_nan=False)
            return result
        except Retry:
            outcome = "retry"
            raise
        except Exception as exc:
            outcome = "failure"
            logger.error("task.failed", error_type=type(exc).__name__)
            raise
        finally:
            logger.info(
                "task.finished",
                outcome=outcome,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(**previous)
