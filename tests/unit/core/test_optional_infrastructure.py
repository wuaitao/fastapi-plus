"""可选能力配置与独立解释器中的缺失依赖行为。"""

import subprocess
import sys

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.redis.client import create_redis_client


@pytest.mark.asyncio
async def test_disabled_factories(settings: Settings) -> None:
    assert await create_redis_client(settings) is None
    assert create_celery_app(settings) is None


def test_enabled_configuration_and_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://:redis-test-secret@localhost:6379/0")
    monkeypatch.setenv("CELERY_ENABLED", "true")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://:broker-test-secret@localhost:6379/1")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://:result-test-secret@localhost:6379/2")
    settings = Settings()
    assert settings.redis_enabled and settings.celery_enabled
    for secret in ("redis-test-secret", "broker-test-secret", "result-test-secret"):
        assert secret not in repr(settings)
        assert secret not in settings.model_dump_json()


@pytest.mark.parametrize(
    "url", ["", "https://localhost", "redis://", "redis://host:bad", "redis://["]
)
def test_invalid_redis_url(url: str) -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(redis_enabled=True, redis_url=SecretStr(url))


@pytest.mark.parametrize("url", ["", "not-a-url", "redis://", "redis://host:bad", "redis://["])
def test_invalid_broker_url(url: str) -> None:
    with pytest.raises(ValidationError, match="Celery"):
        Settings(celery_enabled=True, celery_broker_url=SecretStr(url))


def test_unused_urls_do_not_require_valid_connections() -> None:
    settings = Settings(redis_url=SecretStr("unused"), celery_broker_url=SecretStr("unused"))
    assert not settings.redis_enabled and not settings.celery_enabled


def test_web_and_worker_import_without_optional_packages() -> None:
    # 在全新解释器阻断可选包，避免已加载模块掩盖顶层强制导入。
    code = """
import asyncio
import sys
from importlib.abc import MetaPathFinder

class MissingOptional(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'redis', 'celery'}:
            raise ModuleNotFoundError(fullname)

sys.meta_path.insert(0, MissingOptional())
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from app.core.config import Settings
from app.bootstrap.application import create_app
from app.bootstrap.worker import celery_app
from app.infrastructure.celery.app import create_celery_app
from app.infrastructure.redis.client import create_redis_client

assert celery_app is None
async def check():
    app = create_app(Settings())
    async with app.router.lifespan_context(app):
        assert app.state.redis is None and app.state.celery is None
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/health')).json() == {'status': 'ok'}
    try:
        await create_redis_client(Settings(redis_enabled=True, redis_url=SecretStr('redis://localhost')))
    except RuntimeError as exc:
        assert 'redis extra' in str(exc)
    else:
        raise AssertionError('missing Redis must fail')
asyncio.run(check())
try:
    create_celery_app(Settings(celery_enabled=True, celery_broker_url=SecretStr('memory://')))
except RuntimeError as exc:
    assert 'celery extra' in str(exc)
else:
    raise AssertionError('missing Celery must fail')
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_enabled_worker_has_no_web_imports() -> None:
    code = """
import sys
from importlib.abc import MetaPathFinder
class NoWeb(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'fastapi' or fullname in {'app.main', 'app.bootstrap.application'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, NoWeb())
from pydantic import SecretStr
from app.core.config import Settings
from app.bootstrap.worker import create_worker
app = create_worker(Settings(celery_enabled=True, celery_broker_url=SecretStr('memory://')))
assert app is not None and 'user.status' in app.tasks
assert [name for name in app.tasks if not name.startswith('celery.')] == ['user.status']
app.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
