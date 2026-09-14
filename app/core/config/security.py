"""security 配置字段；由 Settings 统一加载配置来源"""

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    jwt_secret: SecretStr | None = Field(default=None, repr=False, exclude=True)
    access_token_expire_minutes: int = Field(default=30, gt=0, le=1440)
    refresh_token_expire_days: int = Field(default=7, gt=0, le=365)
    # 仅与 Redis 同时启用时缓存认证用户；固定短 TTL 限制身份状态的滞后窗口。
    auth_cache_enabled: bool = False
    auth_cache_ttl: int = Field(default=30, ge=1, le=300)
    auth_cache_prefix: str = Field(default="fastplus:auth", min_length=1)
    # 包含 multipart 编码开销，默认比单文件 10 MiB 上限多留 1 MiB。
    request_max_body_size: int = Field(default=11534336, gt=0)
    login_rate_limit_enabled: bool = False
    login_rate_limit_capacity: int = Field(default=5, ge=1)
    login_rate_limit_period: int = Field(default=60, ge=1)
    login_rate_limit_prefix: str = Field(default="fastplus:login", min_length=1)

    @model_validator(mode="after")
    def validate_secret(self) -> Self:
        """检查显式 JWT 密钥的字节长度，避免使用过短密钥"""
        if self.jwt_secret is not None and len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET 至少需要 32 字节的随机秘密")
        return self
