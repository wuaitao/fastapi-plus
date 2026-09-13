"""仅探测外部能力，不写对象、发送任务或创建目录"""

import os
from pathlib import Path

from app.core.config import Settings
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.redis.client import create_redis_client


def check_local(root: Path) -> None:
    """只读检查本地存储目录和可见性子目录的路径及权限。"""
    # 不通过试写验证权限；已有 public/private 子目录也必须可访问。
    root = root.resolve()
    for path in (root, root / "public", root / "private"):
        # 与 Local Adapter 的路径规则一致，不能把可见性目录链接误报为健康。
        if path != root and (path.is_symlink() or path.resolve() != path):
            raise RuntimeError("存储可见性目录不能包含链接")
        if path != root and not path.exists() and not path.is_symlink():
            continue
        if not path.is_dir() or not os.access(path, os.R_OK | os.W_OK | os.X_OK):
            raise RuntimeError("请显式创建存储目录并检查读写权限")


async def check_redis(settings: Settings) -> None:
    """连接并 PING 已启用的 Redis，随后关闭诊断连接。"""
    client = await create_redis_client(settings)
    if client is not None:
        await client.aclose()


def check_celery(settings: Settings) -> None:
    """只检查 Broker 连通性，不投递任务或探测 Worker。"""
    app = create_celery_app(settings)
    if app is not None:
        try:
            # 只打开 Broker 连接，不声明队列、发布消息或探测 Worker。
            with app.connection_for_read(connect_timeout=5) as connection:
                connection.ensure_connection(max_retries=0)
        finally:
            app.close()


async def check_oss(settings: Settings) -> None:
    """以对象存在性查询检查 OSS 读取连接，不创建探测对象。"""
    from app.infrastructure.storage.aliyun_oss import AliyunOSSStorage

    assert settings.storage_oss is not None
    await AliyunOSSStorage(settings.storage_oss).exists("fastplus-doctor", visibility="private")


async def check_cos(settings: Settings) -> None:
    """以对象存在性查询检查 COS 读取连接，不创建探测对象。"""
    from app.infrastructure.storage.tencent_cos import TencentCOSStorage

    assert settings.storage_cos is not None
    await TencentCOSStorage(settings.storage_cos).exists("fastplus-doctor", visibility="private")
