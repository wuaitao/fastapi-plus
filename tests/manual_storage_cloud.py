"""显式运行的真实云契约，不被默认 test_*.py 规则收集。"""

import io
import os
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.bootstrap.providers import create_storage_registry
from app.core.config import Settings
from app.core.config.storage import CloudStorageSettings
from app.providers.storage import RemoteAccess, Visibility


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["oss", "cos"])
@pytest.mark.parametrize("visibility", ["private", "public"])
async def test_live_storage(backend: str, visibility: Visibility) -> None:
    # 独立命名的测试凭据不读取开发者应用配置，缺失时直接失败而非跳过。
    prefix = f"LIVE_STORAGE_{backend.upper()}_"
    cloud = CloudStorageSettings(
        bucket=os.environ[prefix + "BUCKET"],
        region=os.environ[prefix + "REGION"],
        access_key_id=SecretStr(os.environ[prefix + "ACCESS_KEY_ID"]),
        access_key_secret=SecretStr(os.environ[prefix + "ACCESS_KEY_SECRET"]),
    )
    settings = Settings.model_validate({"storage_backend": backend, f"storage_{backend}": cloud})
    provider = create_storage_registry(settings).get()
    key = f"contract-check/{uuid4().hex}"
    content = b"FastAPI Plus storage contract"
    try:
        assert not await provider.exists(key, visibility=visibility)
        stored = await provider.put(
            key,
            io.BytesIO(content),
            size=len(content),
            content_type="text/plain",
            visibility=visibility,
        )
        assert stored.size == len(content)
        assert await provider.exists(key, visibility=visibility)
        access = await provider.access(key, visibility=visibility, filename="云端测试.txt")
        assert isinstance(access, RemoteAccess)
        async with AsyncClient() as client:
            response = await client.get(access.url)
            assert response.status_code == 200
            assert response.content == content
            # 同一地址移除签名后验证实际对象 ACL，避免仅验证 SDK 调用参数。
            unsigned = await client.get(access.url.split("?", 1)[0])
            assert unsigned.status_code == (200 if visibility == "public" else 403)
        await provider.delete(key, visibility=visibility)
        await provider.delete(key, visibility=visibility)
        assert not await provider.exists(key, visibility=visibility)
    finally:
        await provider.delete(key, visibility=visibility)
