"""Redis 客户端只在启用时导入和连接"""

from asyncio import CancelledError
from typing import TYPE_CHECKING, Protocol, cast

from app.core.config import Settings

if TYPE_CHECKING:
    from redis.asyncio import Redis


class _RedisFactory(Protocol):
    def from_url(self, url: str, **kwargs: object) -> "Redis": ...


class RedisPing(Protocol):
    async def ping(self) -> bool: ...


async def create_redis_client(settings: Settings, *, required: bool = True) -> "Redis | None":
    """创建 Redis 客户端；强依赖立即探测，可降级缓存按首个命令连接"""
    if not settings.redis_enabled:
        return None
    try:
        from redis.asyncio import Redis
    except ImportError:
        raise RuntimeError("Redis 依赖未安装，请安装 redis extra") from None
    assert settings.redis_url is not None
    # redis-py 这些入口的可变参数未完整标注，在 SDK 边界收窄已核实的调用签名。
    client = cast(_RedisFactory, Redis).from_url( # noqa
        settings.redis_url.get_secret_value(),
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    if not required:
        # 保留客户端以便后续请求重连；缓存适配器负责限时回源，关闭仍归生命周期管理。
        return client
    try:
        await cast(RedisPing, client).ping()
    except CancelledError:
        await client.aclose()
        raise
    except Exception:
        # 初始化失败也关闭自有连接池，错误信息不包含服务端或连接凭据。
        await client.aclose()
        raise RuntimeError("Redis 连接失败，请检查配置与服务状态") from None
    return client
