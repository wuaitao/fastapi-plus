"""工厂只构造任务应用，不连接 Broker 或启动 Worker"""

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.infrastructure.celery.config import celery_configuration

if TYPE_CHECKING:
    from celery import Celery


def create_celery_app(settings: Settings) -> "Celery | None":
    """按需创建 Celery 应用及发送信号，不连接 Broker 或启动 Worker。"""
    if not settings.celery_enabled:
        return None
    try:
        from celery import Celery
    except ImportError:
        raise RuntimeError("Celery 依赖未安装，请安装 celery extra") from None
    from celery.signals import before_task_publish

    from app.infrastructure.celery.signals import propagate_context

    app = Celery("fastapi_plus", set_as_current=False)
    app.conf.update(celery_configuration(settings))
    before_task_publish.connect(propagate_context)
    return app
