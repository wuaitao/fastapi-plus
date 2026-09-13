"""redis 配置字段；由 Settings 统一加载配置来源"""

from typing import Self
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings


class RedisSettings(BaseSettings):
    redis_enabled: bool = False
    redis_url: SecretStr | None = None

    @model_validator(mode="after")
    def validate_redis(self) -> Self:
        """仅在启用 Redis 时要求有效的连接配置。"""
        if self.redis_enabled:
            if self.redis_url is None:
                raise ValueError("启用 Redis 必须配置 REDIS_URL")
            try:
                url = urlsplit(self.redis_url.get_secret_value())
                valid = url.scheme in {"redis", "rediss"} and bool(url.hostname)
                _ = url.port
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("REDIS_URL 必须是有效的 redis/rediss 连接串")
        return self
