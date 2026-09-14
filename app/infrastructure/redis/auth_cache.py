"""Redis 认证快照缓存，故障时回源数据库，不缓存密码或验证结果"""

import asyncio
from typing import Protocol

import structlog

from app.providers.auth_cache import AuthUserSnapshot

logger = structlog.get_logger(__name__)


class RedisAuthCommands(Protocol):
    """收窄 redis-py 同步/异步共用注解，仅描述此适配器使用的异步命令"""

    async def get(self, name: str) -> str | bytes | None: ...

    async def set(self, name: str, value: str, *, ex: int) -> object: ...


class RedisAuthUserCache:
    def __init__(self, client: RedisAuthCommands, *, ttl: int, prefix: str) -> None:
        self.client = client
        self.ttl = ttl
        # 版本号隔离后续快照格式变化；不同应用/环境须配置独立前缀。
        self.prefix = f"{prefix}:v1:"

    async def get(self, user_id: int, auth_id: str) -> AuthUserSnapshot | None:
        """读取并校验快照；限时失败回源，命中不延长有效期"""
        try:
            async with asyncio.timeout(0.2):
                value = await self.client.get(f"{self.prefix}{user_id}:{auth_id}")
            if value is None:
                return None
            user = AuthUserSnapshot.model_validate_json(value)
            if user.id != user_id or user.auth_id != auth_id:
                raise ValueError("缓存认证身份不匹配")
            return user
        except Exception:
            # 不记录缓存正文、连接信息或异常文本；取消信号仍向上传播。
            logger.warning("auth.cache_read_failed")
            return None

    async def put(self, user: AuthUserSnapshot) -> None:
        """写入固定 TTL；写入失败不撤销已完成的数据库身份校验"""
        try:
            async with asyncio.timeout(0.2):
                await self.client.set(
                    f"{self.prefix}{user.id}:{user.auth_id}", user.model_dump_json(), ex=self.ttl
                )
        except Exception:
            logger.warning("auth.cache_write_failed")
