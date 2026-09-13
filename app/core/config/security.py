"""security 配置字段；由 Settings 统一加载配置来源"""

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    jwt_secret: SecretStr | None = Field(default=None, repr=False, exclude=True)
    access_token_expire_minutes: int = Field(default=30, gt=0, le=1440)
    refresh_token_expire_days: int = Field(default=7, gt=0, le=365)

    @model_validator(mode="after")
    def validate_secret(self) -> Self:
        """检查显式 JWT 密钥的字节长度，避免使用过短密钥。"""
        if self.jwt_secret is not None and len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError("JWT_SECRET 至少需要 32 字节的随机秘密")
        return self
