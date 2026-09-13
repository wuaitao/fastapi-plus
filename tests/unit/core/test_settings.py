"""验证配置来源、默认值、缓存与非法输入。"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.core.config import Environment, Settings, get_settings


def test_default_settings() -> None:
    settings = Settings()
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.database == "sqlite"
    assert settings.redis_enabled is False
    assert settings.celery_enabled is False
    assert settings.debug is False
    assert settings.openapi_enabled is True


@pytest.mark.parametrize("environment", list(Environment))
def test_environment_loading(monkeypatch: pytest.MonkeyPatch, environment: Environment) -> None:
    monkeypatch.setenv("ENVIRONMENT", environment.value)
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-" * 3)
    assert Settings().environment is environment


def test_configuration_precedence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# 本地配置\nENVIRONMENT=testing\nDEBUG=true\n", encoding="utf-8"
    )
    assert Settings().environment is Environment.TESTING
    assert Settings().debug is True

    monkeypatch.setenv("ENVIRONMENT", "development")
    assert Settings().environment is Environment.DEVELOPMENT
    assert Settings(environment=Environment.TESTING).environment is Environment.TESTING

    class WithoutDotenv(Settings):
        model_config = SettingsConfigDict(env_file=None)

    assert WithoutDotenv().debug is False


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ENVIRONMENT", "staging"),
        ("ENVIRONMENT", ""),
        ("DATABASE", "mysql"),
        ("DEBUG", "invalid"),
        ("OPENAPI_ENABLED", "invalid"),
        ("LOG_FORMAT", "xml"),
        ("LOG_LEVEL", "verbose"),
        ("REDIS_ENABLED", "invalid"),
        ("CELERY_ENABLED", "invalid"),
        ("REDIS_ENABLED", "true"),
        ("CELERY_ENABLED", "true"),
    ],
)
def test_invalid_environment_configuration(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        get_settings()


def test_production_debug_rejected() -> None:
    with pytest.raises(ValidationError, match="生产环境禁止启用 DEBUG"):
        Settings(environment=Environment.PRODUCTION, debug=True)


def test_unknown_dotenv_key_rejected(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ENVIRONMNET=testing\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Settings()


def test_settings_are_frozen(settings: Settings) -> None:
    with pytest.raises(ValidationError, match="frozen"):
        settings.debug = True


def test_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    first = get_settings()
    monkeypatch.setenv("ENVIRONMENT", "testing")
    assert get_settings() is first
    assert get_settings().environment is Environment.DEVELOPMENT

    get_settings.cache_clear()
    assert get_settings().environment is Environment.TESTING
    assert get_settings() is not first


def test_grouped_settings_preserve_sources_and_cloud_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 跨配置分组验证同一次加载仍遵循构造参数 > 环境变量 > .env 的优先级。
    (tmp_path / ".env").write_text(
        "LOG_LEVEL=WARNING\nACCESS_TOKEN_EXPIRE_MINUTES=15\n"
        "STORAGE_BACKEND=oss\nSTORAGE_OSS__BUCKET=test-bucket\n"
        "STORAGE_OSS__REGION=test-region\nSTORAGE_OSS__ACCESS_KEY_ID=test-id\n"
        "STORAGE_OSS__ACCESS_KEY_SECRET=test-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    settings = Settings(access_token_expire_minutes=60)
    assert settings.log_level == "ERROR"
    assert settings.access_token_expire_minutes == 60
    assert settings.storage_backend == "oss"
    assert settings.storage_oss is not None
    assert settings.storage_oss.bucket == "test-bucket"
    assert "test-secret" not in repr(settings)
    assert "test-secret" not in settings.model_dump_json()
    with pytest.raises(ValidationError, match="frozen"):
        settings.storage_oss.bucket = "changed"
