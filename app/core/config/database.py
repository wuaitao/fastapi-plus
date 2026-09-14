"""database 配置字段；由 Settings 统一加载配置来源"""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class DatabaseSettings(BaseSettings):
    database: Literal["sqlite", "postgresql", "mysql"] = "sqlite"
    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./data/app.db")
    # 每个进程独立持有连接池；禁止无限池和无限溢出，便于计算连接预算。
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout: float = Field(default=30, gt=0, allow_inf_nan=False)
    database_pool_recycle: int = Field(default=1800, ge=-1)

    @property
    def sqlalchemy_url(self) -> URL:
        """只在数据库装配边界解开连接串，避免配置 repr 暴露凭据"""
        try:
            url = make_url(self.database_url.get_secret_value())
        except (ArgumentError, ValueError):
            raise ValueError("DATABASE_URL 格式无效") from None
        drivers = {
            "sqlite": "sqlite+aiosqlite",
            "postgresql": "postgresql+asyncpg",
            "mysql": "mysql+asyncmy",
        }
        if url.drivername != drivers[self.database]:
            raise ValueError("DATABASE_URL 必须使用与 DATABASE 匹配的异步驱动")
        if self.database == "sqlite" and any(
            value is not None for value in (url.username, url.password, url.host, url.port)
        ):
            raise ValueError("SQLite DATABASE_URL 仅接受文件路径或内存数据库")
        if self.database != "sqlite" and (not url.host or not url.database):
            raise ValueError("DATABASE_URL 必须包含主机与数据库名")
        return url

    @model_validator(mode="after")
    def validate_database(self) -> Self:
        """在加载配置时验证数据库类型和异步连接串的一致性"""
        _ = self.sqlalchemy_url
        return self
