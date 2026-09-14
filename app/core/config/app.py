"""app 配置字段；由 Settings 统一加载配置来源"""

from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    app_title: str = Field(default="FastAPI Plus", min_length=1)
    app_summary: str = ""
    app_description: str = ""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    openapi_enabled: bool = True
    cors_allow_origins: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    readiness_timeout: float = Field(default=3, gt=0, allow_inf_nan=False)
    metrics_enabled: bool = False

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, hosts: tuple[str, ...]) -> tuple[str, ...]:
        """只接受主机名或子域通配符，空列表表示不启用 Host 校验"""
        for host in hosts:
            name = host.removeprefix("*.")
            if not name or any(c in name for c in "*/:@?#") or any(c.isspace() for c in name):
                raise ValueError("ALLOWED_HOSTS 必须为主机名，可使用 *.example.com，不含端口")
        return hosts

    @field_validator("cors_allow_origins")
    @classmethod
    def validate_cors_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        """校验浏览器来源白名单，拒绝通配符和无法精确匹配的 URL"""
        for origin in origins:
            # 浏览器 Origin 只有协议、主机和可选端口；拒绝会导致匹配失效的路径等内容。
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or origin != f"{parsed.scheme}://{parsed.netloc}"
                or "*" in origin
                or any(character.isspace() for character in origin)
            ):
                raise ValueError("CORS_ALLOW_ORIGINS 必须是无路径的明确 HTTP/HTTPS 来源")
            # 访问 port 属性会校验非法端口和越界值，不让错误配置推迟到浏览器接入时暴露。
            _ = parsed.port
        return origins
