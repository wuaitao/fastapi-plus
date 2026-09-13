"""在 CORS 内层转换未知 HTTP 异常，保留流式响应的中止语义"""

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions.handlers import unexpected_exception_handler


class SafeExceptionMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """兜底 HTTP 异常，响应已开始时继续抛出，由服务器中止连接"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_response(message: Message) -> None:
            """跟踪响应头是否已发送，防止异常路径产生第二组响应"""
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as exc:
            # 在 Starlette 的 DEBUG traceback 响应之前兜底；错误响应也经过外层 CORS。
            response = await unexpected_exception_handler(Request(scope), exc)
            if response_started:
                # 已发送的流不能替换为 JSON；交给服务器中止连接，不发送第二组响应头。
                raise
            await response(scope, receive, send_response)
