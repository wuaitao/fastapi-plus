"""在真实日志输出上验证格式、级别、标准库集成及脱敏。"""

import json
import logging
from datetime import datetime

import pytest
import structlog

from app.core.config import Environment, Settings
from app.core.logging.config import configure_logging
from app.core.logging.redaction import REDACTED, redact_sensitive_fields


@pytest.mark.parametrize("log_format", ["console", "json"])
def test_log_redaction(log_format: str, capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings.model_validate({"log_format": log_format}))
    values = {
        "PassWord": "password-value",
        "nested": [{"ACCESS_TOKEN": "token-value", "Cookie": "cookie-value"}],
        "password_hash": "hash-value",
        "client_secret": "secret-value",
        "Authorization": "Bearer bearer-value",
        "api-key": "key-value",
        "access_key_id": "cloud-id-value",
        "connection": "postgresql+asyncpg://user:db-value@host/db",
        "download": "https://storage.test/file?X-Amz-Signature=signed-value",
        "note": "password=inline-value Bearer inline-token AWS_ACCESS_KEY_ID=inline-cloud-id",
        "object": RuntimeError("object-value"),
        "safe": "visible",
    }
    structlog.get_logger().info("sample.created", **values)
    logging.getLogger("standard").info("standard.created", extra=values)
    try:
        raise RuntimeError("exception-value SELECT * FROM private")
    except RuntimeError:
        logging.getLogger("standard").exception("standard.failed")
        structlog.get_logger().exception("sample.failed")
    output = capsys.readouterr().err
    for secret in (
        "password-value",
        "token-value",
        "cookie-value",
        "hash-value",
        "secret-value",
        "bearer-value",
        "key-value",
        "cloud-id-value",
        "inline-cloud-id",
        "db-value",
        "signed-value",
        "inline-value",
        "inline-token",
        "object-value",
        "exception-value",
        "SELECT",
        "Traceback",
    ):
        assert secret not in output
    assert "visible" in output
    assert REDACTED in output
    assert values["PassWord"] == "password-value"
    if log_format == "json":
        events = [json.loads(line) for line in output.splitlines()]
        assert len(events) == 4
        assert events[0]["nested"][0]["ACCESS_TOKEN"] == REDACTED
        assert events[1]["safe"] == "visible"
        offset = datetime.fromisoformat(events[0]["timestamp"]).utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0


@pytest.mark.parametrize(
    ("environment", "is_json"), [(Environment.DEVELOPMENT, False), (Environment.PRODUCTION, True)]
)
def test_logging_defaults_and_repeat_configuration(
    environment: Environment, is_json: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = Settings.model_validate(
        {"environment": environment, "jwt_secret": "test-only-secret-" * 3}
    )
    configure_logging(settings)
    configure_logging(settings)
    structlog.get_logger().debug("hidden.debug")
    structlog.get_logger().info("application.ready")
    logging.getLogger("uvicorn.access").info("duplicate.access")
    output = capsys.readouterr().err
    assert output.count("application.ready") == 1
    assert "hidden.debug" not in output
    assert "duplicate.access" not in output
    assert output.startswith("{") == is_json


def test_log_level(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(Settings(log_format="json", log_level="WARNING"))
    # 第三方 logger 即使自行启用 DEBUG，也应遵守最终输出 Handler 的级别。
    server_logger = logging.getLogger("uvicorn.error")
    server_logger.setLevel(logging.DEBUG)
    server_logger.info("hidden.server_info")
    structlog.get_logger().info("hidden.info")
    structlog.get_logger().warning("visible.warning")
    assert [json.loads(line)["event"] for line in capsys.readouterr().err.splitlines()] == [
        "visible.warning"
    ]


def test_redaction_does_not_mutate_nested_fields() -> None:
    source = {"nested": [{"secret": "value", "count": 1}]}
    result = redact_sensitive_fields(None, "info", source)
    assert result == {"nested": [{"secret": REDACTED, "count": 1}]}
    assert source == {"nested": [{"secret": "value", "count": 1}]}
