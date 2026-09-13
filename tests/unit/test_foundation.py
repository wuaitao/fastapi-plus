"""验证安装元数据、应用导入与异步测试工具链。"""

import asyncio
from importlib.metadata import distribution
from pathlib import Path

import pytest

import app


def test_installed_distribution_matches_repository(repository_root: Path) -> None:
    package = distribution("fastapi-plus")
    assert package.metadata["Requires-Python"] == ">=3.11"
    assert app.__file__ is not None
    # 同时校验可编辑安装指向当前模板，避免误导入环境中的同名包。
    assert Path(app.__file__).resolve() == repository_root / "app" / "__init__.py"


@pytest.mark.asyncio
async def test_asyncio_plugin_executes_coroutines() -> None:
    assert await asyncio.sleep(0, result="ready") == "ready"
