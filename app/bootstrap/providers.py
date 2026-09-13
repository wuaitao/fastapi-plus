"""显式装配所有已配置后端，保留历史记录的 backend 定位能力"""

from secrets import token_urlsafe

from fastapi import FastAPI
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security.password import get_dummy_password_hash
from app.core.security.token import TokenProvider
from app.infrastructure.storage.local import LocalStorage
from app.providers.storage import StorageRegistry
from app.providers.token_store import NullTokenStore


def create_storage_registry(settings: Settings) -> StorageRegistry:
    registry = StorageRegistry(settings.storage_backend)
    registry.register("local", LocalStorage(settings.storage_local_root))
    if settings.storage_oss is not None:
        from app.infrastructure.storage.aliyun_oss import AliyunOSSStorage

        registry.register("oss", AliyunOSSStorage(settings.storage_oss))
    if settings.storage_cos is not None:
        from app.infrastructure.storage.tencent_cos import TencentCOSStorage

        registry.register("cos", TencentCOSStorage(settings.storage_cos))
    registry.get()
    return registry


def register_providers(app: FastAPI, settings: Settings) -> None:
    """实例级能力显式装配；CLI/Worker 可复用相应工厂"""
    app.state.storage_registry = create_storage_registry(settings)
    # 未配置秘密时仅开发/测试允许使用实例级随机密钥，重启后旧令牌自然失效。
    app.state.token_provider = TokenProvider(
        settings.jwt_secret or SecretStr(token_urlsafe(48)),
        settings.access_token_expire_minutes * 60,
        settings.refresh_token_expire_days * 86400,
    )
    app.state.token_store = NullTokenStore()
    app.state.dummy_password_hash = get_dummy_password_hash()
