"""Redis 原子令牌桶限制登录 IP；共享 Redis 的进程和实例共用额度"""

import asyncio
from hashlib import sha256
from typing import Protocol, cast

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings
from app.core.exceptions import INFRASTRUCTURE_UNAVAILABLE, ErrorDescriptor
from app.core.exceptions.handlers import error_response

LOGIN_RATE_LIMITED = ErrorDescriptor(20002, "LOGIN_RATE_LIMITED", "Too many login attempts", 429)

# 使用 Redis 时间消除应用实例时钟差异；扣减、补充和过期在一个脚本内原子执行。
_TOKEN_BUCKET = """
local capacity = tonumber(ARGV[1])
local period = tonumber(ARGV[2])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local state = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(state[1]) or capacity
local updated = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) * capacity / period)
local retry = 0
if tokens >= 1 then
    tokens = tokens - 1
else
    retry = math.ceil((1 - tokens) * period / capacity)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('EXPIRE', KEYS[1], period)
return retry
"""


class _RedisEval(Protocol):
    async def eval(self, script: str, numkeys: int, *args: str | int) -> int: ...


class LoginRateLimitMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """在解析密码和执行 Argon2 前限流，Redis 故障时拒绝登录并返回 503"""
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        # 代理或挂载应用可带 root_path，匹配应用内路径，防止前缀绕过限流。
        path = scope["path"]
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(f"{root_path}/"):
            path = path[len(root_path) :]
        if path.rstrip("/") != "/api/v1/auth/login":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        # 只使用 ASGI 客户端地址，不直接信任请求携带的 X-Forwarded-For。
        address = request.client.host if request.client is not None else "unknown"
        key = f"{self.settings.login_rate_limit_prefix}:{sha256(address.encode()).hexdigest()}"
        client = cast(_RedisEval, request.app.state.redis)
        try:
            async with asyncio.timeout(2):
                retry = await client.eval(
                    _TOKEN_BUCKET,
                    1,
                    key,
                    self.settings.login_rate_limit_capacity,
                    self.settings.login_rate_limit_period,
                )
        except Exception:
            response = error_response(request, INFRASTRUCTURE_UNAVAILABLE)
            await response(scope, receive, send)
            return
        if retry:
            response = error_response(
                request, LOGIN_RATE_LIMITED, headers={"Retry-After": str(retry)}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
