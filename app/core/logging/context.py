"""纯 ASGI 请求上下文，覆盖错误响应且不缓冲流式数据"""

import re
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """为 HTTP 请求绑定隔离上下文，记录耗时并在结束后恢复调用方上下文。"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ids = Headers(scope=scope).getlist("x-request-id")
        request_id = ids[0] if len(ids) == 1 and _REQUEST_ID.fullmatch(ids[0]) else uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        previous_context = structlog.contextvars.get_contextvars()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        started = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            """向响应头写入请求 ID，并记录实际发送的状态码。"""
            nonlocal status_code
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            try:
                logger.info(
                    "request.completed",
                    status_code=status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                )
            finally:
                # 恢复调用者上下文，同时丢弃本次请求中业务代码额外绑定的字段。
                structlog.contextvars.clear_contextvars()
                structlog.contextvars.bind_contextvars(**previous_context)
