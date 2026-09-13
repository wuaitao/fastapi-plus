"""使用 Celery 原生配置，限制消息格式并默认忽略结果"""

from app.core.config import Settings


def celery_configuration(settings: Settings) -> dict[str, object]:
    """生成原生 Celery 配置，限制 JSON 序列化、重试和任务超时。"""
    assert settings.celery_broker_url is not None
    return {
        "broker_url": settings.celery_broker_url.get_secret_value(),
        "result_backend": (
            settings.celery_result_backend.get_secret_value()
            if settings.celery_result_backend is not None
            else None
        ),
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "result_accept_content": ["json"],
        "task_ignore_result": settings.celery_result_backend is None,
        "task_default_queue": "default",
        "timezone": "UTC",
        "enable_utc": True,
        "worker_hijack_root_logger": False,
        "worker_redirect_stdouts": False,
        "broker_connection_timeout": 5,
        "broker_connection_max_retries": 3,
        "task_soft_time_limit": 30,
        "task_time_limit": 60,
    }
