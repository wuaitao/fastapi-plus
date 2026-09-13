"""Registry、可选依赖和安全配置的独立契约。"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.providers import create_storage_registry
from app.core.config import Settings
from app.core.config.storage import CloudStorageSettings
from app.core.exceptions import InfrastructureException
from app.infrastructure.storage import aliyun_oss as oss
from app.infrastructure.storage import tencent_cos as cos
from app.infrastructure.storage.local import LocalStorage
from app.providers.storage import StorageRegistry


def test_registry(tmp_path: Path) -> None:
    registry = StorageRegistry("local")
    provider = LocalStorage(tmp_path)
    registry.register("local", provider)
    assert registry.get() is provider
    with pytest.raises(ValueError):
        registry.register("local", provider)
    with pytest.raises(InfrastructureException):
        registry.get("removed")


@pytest.mark.parametrize("backend", ["oss", "cos"])
def test_cloud_configuration_and_missing_sdk(backend: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"storage_backend": backend})
    config = CloudStorageSettings(
        bucket="test-bucket",
        region="test-region",
        access_key_id=SecretStr("sensitive-id"),
        access_key_secret=SecretStr("sensitive-secret"),
    )
    assert "sensitive" not in repr(config)
    assert "access_key_secret" not in config.model_dump()

    def missing_sdk(name: str) -> None:
        raise ImportError("internal dependency detail")

    monkeypatch.setattr(oss if backend == "oss" else cos, "import_module", missing_sdk)
    settings = Settings.model_validate({"storage_backend": backend, f"storage_{backend}": config})
    with pytest.raises(RuntimeError, match=f"uv sync --extra {backend}") as error:
        create_storage_registry(settings)
    assert "internal dependency" not in str(error.value)


def test_default_app_never_imports_cloud_sdk(repository_root: Path) -> None:
    code = """
import sys
from importlib.abc import MetaPathFinder
class BlockCloud(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'alibabacloud_oss_v2', 'qcloud_cos'}:
            raise AssertionError('Local mode tried to import a cloud SDK')
sys.meta_path.insert(0, BlockCloud())
from app.bootstrap.application import create_app
from app.core.config import Settings
create_app(Settings())
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
