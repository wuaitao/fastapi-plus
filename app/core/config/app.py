"""app 配置字段；由 Settings 统一加载配置来源"""

from enum import StrEnum

from pydantic_settings import BaseSettings


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    openapi_enabled: bool = True
