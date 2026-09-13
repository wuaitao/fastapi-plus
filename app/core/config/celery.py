"""celery 配置字段；由 Settings 统一加载配置来源"""

from typing import Self
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings


class CelerySettings(BaseSettings):
    celery_enabled: bool = False
    celery_broker_url: SecretStr | None = None
    celery_result_backend: SecretStr | None = None

    @model_validator(mode="after")
    def validate_celery(self) -> Self:
        """仅在启用任务时校验 Broker 与可选结果后端的 URL。"""
        if self.celery_enabled:
            if self.celery_broker_url is None:
                raise ValueError("启用 Celery 必须配置 CELERY_BROKER_URL")
            # 传输由 Celery 原生选择；这里只校验 URL 结构，不输出含凭据的输入。
            for value in (self.celery_broker_url, self.celery_result_backend):
                if value is None:
                    continue
                try:
                    url = urlsplit(value.get_secret_value())
                    valid = bool(url.scheme) and "://" in value.get_secret_value()
                    if url.scheme in {"redis", "rediss", "amqp", "amqps"}:
                        valid = valid and bool(url.hostname)
                    _ = url.port
                except ValueError:
                    valid = False
                if not valid:
                    raise ValueError("Celery 连接配置必须是有效 URL")
        return self
