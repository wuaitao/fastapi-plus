"""完整文件 HTTP 流程、权限隔离、输入错误与 OpenAPI。"""

from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr

from app.core.config.storage import CloudStorageSettings
from app.core.security.token import TokenProvider
from app.infrastructure.storage import aliyun_oss as oss
from app.infrastructure.storage import tencent_cos as cos
from app.modules.user.model import User
from app.providers.storage import StorageRegistry
from tests.storage_fakes import CloudClient


def headers(app: FastAPI, user: User) -> dict[str, str]:
    provider = cast(TokenProvider, app.state.token_provider)
    return {"Authorization": f"Bearer {provider.create_pair(str(user.id)).access_token}"}


@pytest.mark.asyncio
async def test_private_upload_download_delete(
    client: AsyncClient, auth_app: FastAPI, users: dict[str, User], tmp_path: Path
) -> None:
    owner = headers(auth_app, users["alice"])
    filename = "中文 文档.txt"
    response = await client.post(
        "/api/v1/files", files={"file": (filename, b"content", "text/plain")}, headers=owner
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["visibility"] == "private"
    assert data["url"] is None
    assert data["original_name"] == filename
    assert data["size"] == 7
    assert isinstance(data["id"], str)
    assert data["created_by"] == str(users["alice"].id)
    assert filename not in data["key"]
    path = tmp_path / "data/storage/private" / data["key"]
    assert path.read_bytes() == b"content"
    resource = f"/api/v1/files/{data['id']}"
    assert (await client.get(resource)).status_code == 401
    assert (await client.get(resource + "/download")).status_code == 401
    download = await client.get(resource + "/download", headers=owner)
    assert download.content == b"content"
    assert quote(filename) in download.headers["content-disposition"]
    assert download.headers["cache-control"] == "no-store"
    assert (await client.get(resource, headers=owner)).json()["data"]["url"] is None
    duplicate = await client.post(
        "/api/v1/files", files={"file": (filename, b"second", "text/plain")}, headers=owner
    )
    assert duplicate.json()["data"]["key"] != data["key"]
    assert path.read_bytes() == b"content"
    assert (await client.delete(resource, headers=owner)).json()["data"] is None
    assert not path.exists()
    assert (await client.get(resource, headers=owner)).status_code == 404
    assert (await client.delete(resource, headers=owner)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["public", "private"])
async def test_access_rules(
    client: AsyncClient, auth_app: FastAPI, users: dict[str, User], visibility: str
) -> None:
    # operator 是超级管理员；disabled 不能通过认证。
    creator = headers(auth_app, users["operator"])
    stranger = headers(auth_app, users["alice"])
    result = await client.post(
        "/api/v1/files",
        files={"file": ("a.txt", b"a", "text/plain")},
        data={"visibility": visibility},
        headers=creator,
    )
    data = result.json()["data"]
    resource = f"/api/v1/files/{data['id']}"
    for suffix in ("", "/download"):
        assert (await client.get(resource + suffix)).status_code == (
            200 if visibility == "public" else 401
        )
        assert (await client.get(resource + suffix, headers=stranger)).status_code == (
            200 if visibility == "public" else 403
        )
    assert (await client.delete(resource, headers=stranger)).status_code == 403
    assert (await client.delete(resource)).status_code == 401
    assert (
        await client.get(resource, headers=headers(auth_app, users["disabled"]))
    ).status_code == 403
    assert (
        await client.get(resource, headers={"Authorization": "Bearer invalid"})
    ).status_code == 401
    if visibility == "public":
        assert (await client.get(data["url"])).content == b"a"
    else:
        assert data["url"] is None
    assert (await client.get(f"/storage/{visibility}/{data['key']}")).status_code == 404
    assert (await client.delete(resource, headers=creator)).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "content_type", "status"),
    [("../bad.txt", "text/plain", 422), ("a.html", "text/html", 415), ("a.png", "text/plain", 415)],
)
async def test_invalid_upload(
    client: AsyncClient,
    auth_app: FastAPI,
    users: dict[str, User],
    filename: str,
    content_type: str,
    status: int,
) -> None:
    result = await client.post(
        "/api/v1/files",
        files={"file": (filename, b"x", content_type)},
        headers=headers(auth_app, users["alice"]),
    )
    assert result.status_code == status
    assert result.json()["data"] is None


@pytest.mark.asyncio
async def test_large_upload_and_missing_file(
    client: AsyncClient, auth_app: FastAPI, users: dict[str, User]
) -> None:
    owner = headers(auth_app, users["alice"])
    response = await client.post(
        "/api/v1/files",
        files={"file": ("a.bin", b"x" * (10 * 1024 * 1024 + 1), "application/octet-stream")},
        headers=owner,
    )
    assert response.status_code == 413
    assert response.json()["code"] == 31002
    assert (
        await client.post("/api/v1/files", files={"file": ("a.txt", b"x", "text/plain")})
    ).status_code == 401
    assert (await client.get("/api/v1/files/9223372036854775808")).status_code == 422
    assert (await client.get("/api/v1/files/999/download", headers=owner)).status_code == 404


def test_file_openapi(auth_app: FastAPI) -> None:
    schema: dict[str, Any] = auth_app.openapi()
    paths = schema["paths"]
    upload = paths["/api/v1/files"]["post"]
    assert "multipart/form-data" in upload["requestBody"]["content"]
    assert {"201", "401", "403", "413", "415", "422", "503"} <= upload["responses"].keys()
    assert upload["security"] == [{"HTTPBearer": []}]
    download = paths["/api/v1/files/{id}/download"]["get"]
    assert {} in download["security"]
    assert "307" in download["responses"]
    assert "application/json" not in download["responses"]["200"]["content"]
    output = schema["components"]["schemas"]["FileResponse"]["properties"]
    assert output["id"].get("type") == "string"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["oss", "cos"])
async def test_cloud_authorization_redirect_and_errors(
    client: AsyncClient,
    auth_app: FastAPI,
    users: dict[str, User],
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    cloud = CloudClient()
    config = CloudStorageSettings(
        bucket="test-bucket",
        region="test-region",
        access_key_id=SecretStr("id"),
        access_key_secret=SecretStr("secret"),
    )
    registry = cast(StorageRegistry, auth_app.state.storage_registry)
    if backend == "oss":
        monkeypatch.setattr(oss, "import_module", cloud.sdk)
        registry.register(backend, oss.AliyunOSSStorage(config))
    else:
        monkeypatch.setattr(cos, "import_module", cloud.sdk)
        registry.register(backend, cos.TencentCOSStorage(config))
    registry.default_backend = backend
    result = await client.post(
        "/api/v1/files",
        files={"file": ("cloud.txt", b"cloud", "text/plain")},
        headers=headers(auth_app, users["alice"]),
    )
    assert result.status_code == 201
    data = result.json()["data"]
    assert data["url"] is None
    resource = f"/api/v1/files/{data['id']}"
    assert (await client.get(resource + "/download")).status_code == 401
    assert cloud.signed is None
    admin = headers(auth_app, users["operator"])
    response = await client.get(resource + "/download", headers=admin)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://cloud.example/")
    assert response.headers["cache-control"] == "no-store"
    cloud.error = OSError("secret-sdk-detail")
    response = await client.get(resource + "/download", headers=admin)
    assert response.status_code == 503
    assert response.json()["code"] == 11001
    assert "secret-sdk-detail" not in response.text
    cloud.error = None
    assert (await client.delete(resource, headers=admin)).status_code == 200
