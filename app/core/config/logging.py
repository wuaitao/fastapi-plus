"""logging 配置字段；由 Settings 统一加载配置来源"""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class LoggingSettings(BaseSettings):
    log_format: Literal["console", "json"] | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file_path: Path | None = None
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    log_file_backup_count: int = Field(default=5, ge=1)
