"""验证工厂隔离、入口与集中生命周期。"""

from importlib import import_module

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.bootstrap import lifespan as lifecycle
from app.bootstrap.application import create_app
from app.core.config import Settings, get_settings


def test_create_app_with_cached_settings() -> None:
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.state.settings is get_settings()
    assert app.debug is False


def test_explicit_settings_isolate_apps(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "invalid")
    first = create_app(settings)
    second = create_app(settings)
    assert first is not second
    assert first.state is not second.state
    assert first.router is not second.router
    assert first.state.settings is settings
    assert get_settings.cache_info().currsize == 0


def test_invalid_configuration_prevents_app_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        create_app()


def test_debug_setting() -> None:
    assert create_app(Settings(debug=True)).debug is True


@pytest.mark.asyncio
async def test_main_entry() -> None:
    entry = import_module("app.main")
    async with entry.app.router.lifespan_context(entry.app):
        async with AsyncClient(
            transport=ASGITransport(app=entry.app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "startup", "running"])
async def test_lifespan_hooks(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    app = create_app(settings)
    events: list[str] = []

    async def startup(current: FastAPI) -> None:
        assert current is app
        events.append("startup")
        if failure == "startup":
            raise RuntimeError("startup")

    async def shutdown(current: FastAPI) -> None:
        assert current is app
        events.append("shutdown")

    # 仅验证钩子调用顺序；真实数据库资源释放由数据库生命周期测试覆盖。
    monkeypatch.setattr(lifecycle, "startup", startup)
    monkeypatch.setattr(lifecycle, "shutdown", shutdown)

    async def run() -> None:
        async with app.router.lifespan_context(app):
            assert events == ["startup"]
            events.append("running")
            if failure == "running":
                raise RuntimeError("running")

    if failure is None:
        await run()
    else:
        with pytest.raises(RuntimeError, match=failure):
            await run()
    expected = (
        ["startup", "shutdown"] if failure == "startup" else ["startup", "running", "shutdown"]
    )
    assert events == expected
