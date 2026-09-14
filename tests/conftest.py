"""隔离测试配置、日志和运行目录，禁止读取开发者资源"""

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core.config import Environment, Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """移除 Settings 环境来源，并让相对路径落在测试临时目录"""
    fields = {name.upper() for name in Settings.model_fields}
    for name in os.environ:
        if name.upper().split("__")[0] in fields:
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    # 应用工厂和迁移不应重配 pytest 所在进程的日志 Handler。
    def keep_logging(settings: Settings) -> None:
        """保留测试运行器的日志配置"""

    monkeypatch.setattr("app.bootstrap.application.configure_logging", keep_logging)
    monkeypatch.setattr("app.core.logging.config.configure_logging", keep_logging)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """提供每个用例独占的 SQLite 文件和 Local 目录"""
    root = tmp_path / "storage"
    root.mkdir()
    return Settings(
        environment=Environment.TESTING,
        debug=False,
        storage_local_root=root,
        database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"),
    )
