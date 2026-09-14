"""组合各能力的配置字段，集中加载来源并校验跨配置约束"""

from functools import lru_cache
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.app import AppSettings, Environment
from app.core.config.celery import CelerySettings
from app.core.config.database import DatabaseSettings
from app.core.config.logging import LoggingSettings
from app.core.config.redis import RedisSettings
from app.core.config.security import SecuritySettings
from app.core.config.storage import StorageSettings


class Settings(
    AppSettings,
    DatabaseSettings,
    SecuritySettings,
    LoggingSettings,
    RedisSettings,
    CelerySettings,
    StorageSettings,
    BaseSettings,
):
    # 字段组合保持既有平铺环境变量，仅云配置使用嵌套名称；来源只加载一次。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """检查生产环境的跨配置约束：关闭调试并提供固定密钥"""
        if self.environment == Environment.PRODUCTION and self.debug:
            raise ValueError("生产环境禁止启用 DEBUG")
        if self.environment == Environment.PRODUCTION and self.jwt_secret is None:
            raise ValueError("生产环境必须配置 JWT_SECRET")
        if self.login_rate_limit_enabled and not self.redis_enabled:
            raise ValueError("启用登录限流必须同时启用 REDIS_ENABLED")
        if self.request_max_body_size <= self.file_max_size:
            raise ValueError(
                "REQUEST_MAX_BODY_SIZE 必须大于 FILE_MAX_SIZE，为 multipart 编码留余量"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """每个进程复用不可变配置；测试修改来源后须显式清理缓存"""
    return Settings()
