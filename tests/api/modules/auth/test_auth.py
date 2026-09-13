"""真实 HTTP 认证、授权、刷新、退出及公开契约。"""

import logging
from datetime import UTC, datetime
from typing import cast

import jwt
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security.token import TokenProvider
from app.database.session import session_scope
from app.modules.user.model import User
from app.modules.user.repository import UserRepository

URL = "/api/v1/auth"
PASSWORD = "auth-test-password"


async def login(client: AsyncClient, username: str = "alice") -> Response:
    return await client.post(f"{URL}/login", json={"username": username, "password": PASSWORD})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_login_me_refresh_logout(
    client: AsyncClient,
    users: dict[str, User],
    auth_app: FastAPI,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)
    response = await login(client)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    pair = response.json()["data"]
    assert set(pair) == {"access_token", "refresh_token", "token_type", "expires_in"}
    assert pair["token_type"] == "bearer"
    assert pair["expires_in"] == 1800
    provider = cast(TokenProvider, auth_app.state.token_provider)
    for kind in ("access", "refresh"):
        claims = provider.decode_token(pair[f"{kind}_token"], kind)
        assert claims.sub == str(users["alice"].id)
        assert claims.exp - claims.iat == (1800 if kind == "access" else 604800)
    headers = bearer(pair["access_token"])
    me = await client.get(f"{URL}/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["data"]["id"] == str(users["alice"].id)
    assert me.json()["data"]["username"] == "alice"
    assert "password" not in me.text
    refreshed = await client.post(f"{URL}/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.headers["Cache-Control"] == "no-store"
    new_pair = refreshed.json()["data"]
    assert new_pair["access_token"] != pair["access_token"]
    assert new_pair["refresh_token"] != pair["refresh_token"]
    assert (
        await client.get(f"{URL}/me", headers=bearer(new_pair["access_token"]))
    ).status_code == 200
    logout = await client.post(f"{URL}/logout", headers=headers)
    assert logout.status_code == 200
    assert logout.json() == {"code": 0, "message": "success", "data": None}
    # 无状态退出不会在服务器撤销 access 或 refresh，也不提供刷新防重放。
    assert (await client.get(f"{URL}/me", headers=headers)).status_code == 200
    assert (
        await client.post(f"{URL}/refresh", json={"refresh_token": pair["refresh_token"]})
    ).status_code == 200
    output = caplog.text + capsys.readouterr().err
    for secret in (
        PASSWORD,
        users["alice"].password_hash,
        *[pair[k] for k in ("access_token", "refresh_token")],
    ):
        assert secret not in output


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "username,password", [("alice", "wrong"), ("missing", PASSWORD), ("disabled", PASSWORD)]
)
async def test_invalid_credentials(
    client: AsyncClient, users: dict[str, User], username: str, password: str
) -> None:
    response = await client.post(f"{URL}/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["code"] == 20001
    assert response.json()["message"] == "Invalid credentials"
    assert response.json()["data"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["me", "logout"])
@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer", "Bearer broken"])
async def test_missing_or_malformed_bearer(
    client: AsyncClient, endpoint: str, authorization: str | None
) -> None:
    response = await client.request(
        "GET" if endpoint == "me" else "POST",
        f"{URL}/{endpoint}",
        headers={} if authorization is None else {"Authorization": authorization},
    )
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert "detail" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["access", "refresh"])
@pytest.mark.parametrize(
    "failure", ["signature", "expired", "type", "missing", "subject", "algorithm"]
)
async def test_invalid_tokens(
    client: AsyncClient, users: dict[str, User], auth_app: FastAPI, kind: str, failure: str
) -> None:
    provider = cast(TokenProvider, auth_app.state.token_provider)
    now = int(datetime.now(UTC).timestamp())
    claims: dict[str, object] = {
        "sub": str(users["alice"].id),
        "type": kind,
        "iat": now - 60,
        "exp": now + 60,
        "jti": "test-id",
    }
    if failure == "expired":
        claims["exp"] = now - 1
    elif failure == "type":
        claims["type"] = "refresh" if kind == "access" else "access"
    elif failure == "missing":
        del claims["jti"]
    elif failure == "subject":
        claims["sub"] = "9223372036854775808"
    secret = (
        "wrong-test-secret-" * 4 if failure == "signature" else provider.secret.get_secret_value()
    )
    token = jwt.encode(claims, secret, algorithm="HS384" if failure == "algorithm" else "HS256")
    response = (
        await client.get(f"{URL}/me", headers=bearer(token))
        if kind == "access"
        else await client.post(f"{URL}/refresh", json={"refresh_token": token})
    )
    assert response.status_code == 401
    assert token not in response.text
    assert response.json()["code"] == 20001


@pytest.mark.asyncio
@pytest.mark.parametrize("state,status", [("disabled", 403), ("deleted", 401)])
async def test_user_state_is_rechecked(
    client: AsyncClient, users: dict[str, User], auth_app: FastAPI, state: str, status: int
) -> None:
    pair = (await login(client)).json()["data"]
    factory = cast(async_sessionmaker[AsyncSession], auth_app.state.session_factory)
    async with session_scope(factory) as session:
        if state == "disabled":
            await session.execute(
                update(User).where(User.id == users["alice"].id).values(is_active=False)
            )
        else:
            await session.execute(delete(User).where(User.id == users["alice"].id))
        await session.commit()
    responses = [
        await client.get(f"{URL}/me", headers=bearer(pair["access_token"])),
        await client.post(f"{URL}/refresh", json={"refresh_token": pair["refresh_token"]}),
        await client.post(f"{URL}/logout", headers=bearer(pair["access_token"])),
    ]
    for response in responses:
        assert response.status_code == status
        assert response.json()["code"] == (30003 if state == "disabled" else 20001)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/users"),
        ("get", "/users"),
        ("get", "/users/1"),
        ("patch", "/users/1"),
        ("delete", "/users/1"),
    ],
)
async def test_401_vs_403(
    client: AsyncClient, users: dict[str, User], method: str, path: str
) -> None:
    token = (await login(client)).json()["data"]["access_token"]
    for headers, status in [({}, 401), (bearer(token), 403)]:
        response = await client.request(method, f"/api/v1{path}", headers=headers)
        assert response.status_code == status
        assert response.json()["code"] == (20001 if status == 401 else 21001)


@pytest.mark.asyncio
async def test_admin_management_and_self_delete(
    client: AsyncClient, users: dict[str, User]
) -> None:
    pair = (await login(client, "operator")).json()["data"]
    headers = bearer(pair["access_token"])
    assert (await client.get("/api/v1/users", headers=headers)).status_code == 200
    created = await client.post(
        "/api/v1/users", json={"username": "new-user", "password": PASSWORD}, headers=headers
    )
    assert created.status_code == 201
    resource = f"/api/v1/users/{created.json()['data']['id']}"
    assert (
        await client.patch(resource, json={"username": "renamed"}, headers=headers)
    ).status_code == 200
    assert (await client.delete(resource, headers=headers)).status_code == 200
    response = await client.delete(f"/api/v1/users/{users['operator'].id}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == 30004
    assert (await client.get(f"{URL}/me", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_startup_has_no_accounts(client: AsyncClient, auth_app: FastAPI) -> None:
    factory = cast(async_sessionmaker[AsyncSession], auth_app.state.session_factory)
    async with session_scope(factory) as session:
        assert (await UserRepository(session).paginate()).total == 0
    assert (await login(client, "admin")).status_code == 401


@pytest.mark.asyncio
async def test_openapi(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    for path, method in [("me", "get"), ("logout", "post"), ("login", "post"), ("refresh", "post")]:
        operation = schema["paths"][f"{URL}/{path}"][method]
        assert operation["summary"] and operation["description"]
        if path in {"me", "logout"}:
            assert operation["security"] == [{"HTTPBearer": []}]
        else:
            assert "security" not in operation
        for status in ("401", "403", "422"):
            assert operation["responses"][status]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }
    for path in ("/api/v1/users", "/api/v1/users/{id}"):
        for operation in schema["paths"][path].values():
            assert operation["security"] == [{"HTTPBearer": []}]
