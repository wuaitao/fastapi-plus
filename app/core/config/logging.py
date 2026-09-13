"""logging 配置字段；由 Settings 统一加载配置来源"""

from typing import Literal

from pydantic_settings import BaseSettings


class LoggingSettings(BaseSettings):
    log_format: Literal["console", "json"] | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
