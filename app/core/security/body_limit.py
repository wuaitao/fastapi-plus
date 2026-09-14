"""复用 Starlette 流式限额，统一早期拒绝与解析阶段的 413 响应"""

from starlette.datastructures import Headers
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.requests import Request
from starlette.types import Message, Receive, Scope, Send

from app.core.exceptions.common import BODY_TOO_LARGE
from app.core.exceptions.handlers import error_response


class BodyLimitMiddleware(RequestBodyLimitMiddleware):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """按原始字节限额；只替换错误格式，不缓冲请求体或成功响应"""
        replaced = False

        async def send_response(message: Message) -> None:
            """框架早期拒绝默认是纯文本，在边界转换成项目错误契约"""
            nonlocal replaced
            if (
                message["type"] == "http.response.start"
                and message["status"] == 413
                and Headers(raw=message["headers"]).get("content-type", "").startswith("text/plain")
            ):
                replaced = True
                response = error_response(Request(scope), BODY_TOO_LARGE)
                await response(scope, receive, send)
            elif not replaced:
                await send(message)

        await super().__call__(scope, receive, send_response)
