"""同一契约覆盖真实 Local 和仅模拟 SDK 边界的 OSS/COS。"""

import io
import threading
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config.storage import CloudStorageSettings
from app.core.exceptions import InfrastructureException
from app.infrastructure.storage import aliyun_oss as oss
from app.infrastructure.storage import tencent_cos as cos
from app.infrastructure.storage.local import LocalStorage
from app.providers.storage import LocalAccess, RemoteAccess, StorageProvider, Visibility
from tests.storage_fakes import CloudClient, CosError


class BoundedStream(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        assert size is not None and 0 < size <= 64 * 1024
        return super().read(size)


@pytest.fixture(params=["local", "oss", "cos"])
def storage(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[StorageProvider, CloudClient | None]:
    if request.param == "local":
        return LocalStorage(tmp_path / "storage"), None
    client = CloudClient()
    config = CloudStorageSettings(
        bucket="contract-bucket",
        region="test-region",
        access_key_id=SecretStr("test-id"),
        access_key_secret=SecretStr("test-secret"),
    )
    if request.param == "oss":
        monkeypatch.setattr(oss, "import_module", client.sdk)
        return oss.AliyunOSSStorage(config), client
    monkeypatch.setattr(cos, "import_module", client.sdk)
    return cos.TencentCOSStorage(config), client


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["private", "public"])
async def test_storage_contract(
    storage: tuple[StorageProvider, CloudClient | None], visibility: Visibility
) -> None:
    provider, client = storage
    content = b"streaming-content" * 131072
    stored = await provider.put(
        "2026/object",
        BoundedStream(content),
        size=len(content),
        content_type="application/octet-stream",
        visibility=visibility,
    )
    assert (stored.key, stored.size) == ("2026/object", len(content))
    assert await provider.exists(stored.key, visibility=visibility)
    other: Visibility = "public" if visibility == "private" else "private"
    assert not await provider.exists(stored.key, visibility=other)
    access = await provider.access(stored.key, visibility=visibility, filename="中文 文件.bin")
    if isinstance(access, LocalAccess):
        assert access.path.read_bytes() == content
        assert visibility in access.path.parts
    else:
        assert isinstance(access, RemoteAccess)
        assert client is not None
        assert client.objects[f"{visibility}/{stored.key}"] == content
        assert client.acls[f"{visibility}/{stored.key}"] == (
            "private" if visibility == "private" else "public-read"
        )
        assert client.signed == (
            f"{visibility}/{stored.key}",
            300,
            "attachment; filename*=UTF-8''%E4%B8%AD%E6%96%87%20%E6%96%87%E4%BB%B6.bin",
        )
        assert all(thread != threading.get_ident() for thread in client.calls)
    await provider.delete(stored.key, visibility=other)
    assert await provider.exists(stored.key, visibility=visibility)
    await provider.delete(stored.key, visibility=visibility)
    await provider.delete(stored.key, visibility=visibility)
    assert not await provider.exists(stored.key, visibility=visibility)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key",
    [
        "../escape",
        "/absolute",
        "a/../../b",
        "a//b",
        "a/./b",
        "C:/outside",
        r"a\b",
        "//host/share",
        "a%2fb",
        "a\x00b",
        "CON.txt",
        "a.",
        "",
        "a/..",
    ],
)
async def test_invalid_keys(storage: tuple[StorageProvider, CloudClient | None], key: str) -> None:
    provider, _ = storage
    with pytest.raises(ValueError):
        await provider.put(
            key, io.BytesIO(b"x"), size=1, content_type="text/plain", visibility="private"
        )
    with pytest.raises(ValueError):
        await provider.exists(key, visibility="private")
    with pytest.raises(ValueError):
        await provider.delete(key, visibility="private")
    with pytest.raises(ValueError):
        await provider.access(key, visibility="private", filename="a.txt")


@pytest.mark.asyncio
async def test_local_links_and_partial_write(tmp_path: Path) -> None:
    provider = LocalStorage(tmp_path / "storage")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"secret")
    private = provider.root / "private"
    private.mkdir(parents=True)
    # Windows 无符号链接权限时使用 junction，仍验证真实文件系统逃逸。
    link = private / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        import subprocess

        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    with pytest.raises(InfrastructureException):
        await provider.exists("linked/secret", visibility="private")
    with pytest.raises(InfrastructureException):
        await provider.delete("linked/secret", visibility="private")
    with pytest.raises(InfrastructureException):
        await provider.access("linked/secret", visibility="private", filename="x.txt")
    with pytest.raises(InfrastructureException):
        await provider.put(
            "linked/secret",
            io.BytesIO(b"bad"),
            size=3,
            content_type="text/plain",
            visibility="private",
        )
    assert (outside / "secret").read_bytes() == b"secret"
    with pytest.raises(InfrastructureException):
        await provider.put(
            "partial",
            io.BytesIO(b"too large"),
            size=1,
            content_type="text/plain",
            visibility="private",
        )
    assert not await provider.exists("partial", visibility="private")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [OSError("secret SDK failure"), CosError(403, "AccessDenied"), CosError(404, "NoSuchBucket")],
)
async def test_cloud_failure_is_not_absence(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    client = CloudClient()
    client.error = error
    monkeypatch.setattr(cos, "import_module", client.sdk)
    provider = cos.TencentCOSStorage(
        CloudStorageSettings(
            bucket="test-bucket",
            region="ap-test",
            access_key_id=SecretStr("id"),
            access_key_secret=SecretStr("secret"),
        )
    )
    with pytest.raises(InfrastructureException, match="^Service unavailable$"):
        await provider.exists("key", visibility="private")
    with pytest.raises(InfrastructureException):
        await provider.delete("key", visibility="private")


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["", "Unknown"])
async def test_cos_empty_head_404(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    client = CloudClient()
    client.error = CosError(404, code)
    monkeypatch.setattr(cos, "import_module", client.sdk)
    provider = cos.TencentCOSStorage(
        CloudStorageSettings(
            bucket="test-bucket",
            region="ap-test",
            access_key_id=SecretStr("id"),
            access_key_secret=SecretStr("secret"),
        )
    )
    # HEAD 的 404 可以没有 XML 响应体，SDK 此时没有 NoSuchKey 字段。
    assert not await provider.exists("key", visibility="private")
