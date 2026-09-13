"""共享测试资源与配置来源隔离。"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from app.core.config import Environment, Settings, get_settings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--release-database",
        choices=("sqlite", "postgresql", "mysql"),
        default="sqlite",
        help="发布流程数据库；外部数据库使用 FASTPLUS_TEST_DATABASE_URL 指定独立空库",
    )


@pytest.fixture(autouse=True)
def isolated_logging() -> Iterator[None]:
    # 应用配置属于进程级状态；测试结束恢复日志输出，避免指向已关闭的捕获流。
    configuration = structlog.get_config()
    raise_exceptions = logging.raiseExceptions
    names = (
        "",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "aiosqlite",
    )
    states = [
        (logger, logger.handlers[:], logger.level, logger.propagate, logger.disabled)
        for logger in (logging.getLogger(name) for name in names)
    ]
    context = structlog.contextvars.get_contextvars()
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(**context)
    structlog.configure(**configuration)
    logging.raiseExceptions = raise_exceptions
    for logger, handlers, level, propagate, disabled in states:
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.disabled = disabled


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    # 在临时目录加载 .env，并移除已声明的环境变量，避免读取开发者配置。
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(environment=Environment.TESTING)


@pytest.fixture(scope="session")
def repository_root() -> Path:
    """基于测试文件位置定位仓库，避免依赖调用者的工作目录。"""
    return Path(__file__).resolve().parents[1]
