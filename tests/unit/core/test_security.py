"""密码、JWT 声明及安全配置的边界测试。"""

from datetime import UTC, datetime
from typing import cast

import jwt
import pytest
from pydantic import SecretStr, ValidationError

from app.bootstrap.application import create_app
from app.core.config import Environment, Settings
from app.core.exceptions import AuthenticationException
from app.core.security import hash_password, verify_password
from app.core.security.token import TokenProvider
from app.providers.token_store import NullTokenStore


@pytest.mark.asyncio
async def test_argon2id_hash_and_verify() -> None:
    password = "测试-password-123"
    first = await hash_password(password)
    second = await hash_password(password)
    assert first.startswith("$argon2id$")
    assert first != second
    assert password not in first
    assert await verify_password(password, first)
    assert not await verify_password("wrong-password", first)
    assert not await verify_password(password, "corrupt-hash")


@pytest.fixture
def provider() -> TokenProvider:
    return TokenProvider(SecretStr("unit-test-secret-" * 4), 1800, 604800)


def test_token_claims_and_unique_ids(provider: TokenProvider) -> None:
    pair = provider.create_pair("123")
    access = provider.decode_token(pair.access_token, "access")
    refresh = provider.decode_token(pair.refresh_token, "refresh")
    assert set(access.model_dump()) == {"sub", "type", "iat", "exp", "jti"}
    assert access.sub == refresh.sub == "123"
    assert access.jti != refresh.jti
    assert access.exp - access.iat == pair.expires_in == 1800
    assert refresh.exp - refresh.iat == 604800
    assert pair.access_token not in repr(pair)
    assert provider.secret.get_secret_value() not in repr(provider)


@pytest.mark.parametrize("claim", ["sub", "type", "iat", "exp", "jti"])
def test_all_claims_required(provider: TokenProvider, claim: str) -> None:
    payload = provider.decode_token(provider.create_token("1", "access"), "access").model_dump()
    del payload[claim]
    token = jwt.encode(payload, provider.secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(AuthenticationException):
        provider.decode_token(token, "access")


@pytest.mark.parametrize(
    "claim,value",
    [
        ("sub", 1),
        ("sub", ""),
        ("jti", 1),
        ("jti", ""),
        ("type", "other"),
        ("iat", True),
        ("iat", "123"),
        ("iat", 1.5),
        ("iat", -1),
        ("iat", float("inf")),
        ("exp", True),
        ("exp", "9999999999"),
        ("exp", 9999999999.5),
        ("exp", float("inf")),
    ],
)
def test_claim_types(provider: TokenProvider, claim: str, value: object) -> None:
    now = int(datetime.now(UTC).timestamp())
    payload: dict[str, object] = {
        "sub": "1",
        "type": "access",
        "iat": now,
        "exp": now + 60,
        "jti": "test-id",
    }
    payload[claim] = value
    token = jwt.encode(payload, provider.secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(AuthenticationException):
        provider.decode_token(token, "access")


def test_future_issued_at_and_unsigned_token(provider: TokenProvider) -> None:
    now = int(datetime.now(UTC).timestamp())
    payload = {"sub": "1", "type": "access", "iat": now + 60, "exp": now + 120, "jti": "test-id"}
    future = jwt.encode(payload, provider.secret.get_secret_value(), algorithm="HS256")
    unsigned = jwt.encode(payload, key="", algorithm="none")
    for token in (future, unsigned):
        with pytest.raises(AuthenticationException):
            provider.decode_token(token, "access")


def test_production_requires_secret() -> None:
    with pytest.raises(ValidationError, match="生产环境必须配置 JWT_SECRET"):
        Settings(environment=Environment.PRODUCTION)
    secret = "production-config-test-only-" * 3
    settings = Settings(environment=Environment.PRODUCTION, jwt_secret=SecretStr(secret))
    assert secret not in repr(settings)
    assert "jwt_secret" not in settings.model_dump()
    assert secret not in settings.model_dump_json()


@pytest.mark.parametrize(
    "values",
    [
        {"jwt_secret": ""},
        {"jwt_secret": "too-short"},
        {"access_token_expire_minutes": 0},
        {"refresh_token_expire_days": -1},
    ],
)
def test_invalid_security_configuration(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_development_keys_are_isolated() -> None:
    first = cast(TokenProvider, create_app(Settings()).state.token_provider)
    second = cast(TokenProvider, create_app(Settings()).state.token_provider)
    token = first.create_token("1", "access")
    with pytest.raises(AuthenticationException):
        second.decode_token(token, "access")


@pytest.mark.asyncio
async def test_null_store_is_stateless() -> None:
    store = NullTokenStore()
    await store.revoke("test-id", 123)
    assert not await store.is_revoked("test-id")
