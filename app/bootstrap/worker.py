"""独立 Worker 入口；不导入 Web 应用或复用其资源"""

from typing import TYPE_CHECKING

from app.core.config import Settings, get_settings
from app.infrastructure.celery.app import create_celery_app

if TYPE_CHECKING:
    from celery import Celery


def create_worker(settings: Settings | None = None) -> "Celery | None":
    """独立装配 Worker 日志与任务，未启用 Celery 时返回空值"""
    settings = settings if settings is not None else get_settings()
    app = create_celery_app(settings)
    if app is None:
        return None
    from app.infrastructure.celery.signals import WorkerLogging
    from app.modules.user.tasks import register_user_tasks

    # 使用弱引用信号；由应用持有配置器，关闭/回收应用后不残留全局配置接收者。
    logging = WorkerLogging(settings)
    app.__dict__["worker_logging"] = logging
    logging.connect()
    register_user_tasks(app, settings)
    return app


celery_app = create_worker()
