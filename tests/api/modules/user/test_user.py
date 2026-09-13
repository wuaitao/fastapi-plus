"""用户 API 的持久化行为、输入边界及公开契约。"""

import logging

import pytest
from argon2 import PasswordHasher
from httpx import AsyncClient

from app.core.config import Settings
from app.database.engine import create_engine
from app.database.session import create_session_factory, session_scope
from app.modules.user.repository import UserRepository

URL = "/api/v1/users"
PASSWORD = "test-password-123"


@pytest.mark.asyncio
async def test_crud(
    client: AsyncClient, user_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    response = await client.post(
        URL, json={"username": "alice", "email": "alice@example.com", "password": PASSWORD}
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["code"], body["message"]) == (0, "success")
    user = body["data"]
    assert set(user) == {
        "id",
        "username",
        "email",
        "is_active",
        "is_superuser",
        "created_at",
        "updated_at",
    }
    assert isinstance(user["id"], str)
    assert user["is_active"] is True
    assert user["is_superuser"] is False
    assert user["created_at"].endswith("Z")
    assert user["updated_at"].endswith("Z")
    resource = f"{URL}/{user['id']}"
    assert (await client.get(resource)).json()["data"] == user

    engine = create_engine(user_settings)
    try:
        async with session_scope(create_session_factory(engine)) as session:
            stored = await UserRepository(session).get(int(user["id"]))
            assert stored is not None
            assert stored.password_hash.startswith("$argon2id$")
            assert PasswordHasher().verify(stored.password_hash, PASSWORD)
            password_hash = stored.password_hash
    finally:
        await engine.dispose()

    changed = await client.patch(resource, json={"username": "alice-new", "is_active": False})
    assert changed.status_code == 200
    updated = changed.json()["data"]
    assert updated["username"] == "alice-new"
    assert updated["is_active"] is False
    assert updated["email"] == "alice@example.com"
    assert updated["created_at"] == user["created_at"]
    assert updated["updated_at"] >= user["updated_at"]
    assert (await client.get(resource)).json()["data"] == updated
    assert (await client.patch(resource, json={})).json()["data"] == updated
    cleared = await client.patch(resource, json={"email": None})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["email"] is None
    deleted = await client.delete(resource)
    assert deleted.status_code == 200
    assert deleted.json() == {"code": 0, "message": "success", "data": None}
    assert (await client.get(resource)).status_code == 404
    assert (await client.get(URL)).json()["data"]["total"] == 0
    assert PASSWORD not in caplog.text
    assert password_hash not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["username", "email"])
async def test_duplicate_create_and_update(client: AsyncClient, field: str) -> None:
    first = {"username": "alice", "email": "alice@example.com", "password": PASSWORD}
    second = {"username": "bob", "email": "bob@example.com", "password": PASSWORD}
    assert (await client.post(URL, json=first)).status_code == 201
    response = await client.post(URL, json=second | {field: first[field]})
    assert response.status_code == 409
    assert response.json()["code"] == 30001
    assert response.json()["message"] == "User already exists"
    created = await client.post(URL, json=second)
    assert created.status_code == 201
    resource = f"{URL}/{created.json()['data']['id']}"
    conflict = await client.patch(resource, json={field: first[field]})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 30001
    assert (await client.get(resource)).json()["data"][field] == second[field]
    assert (await client.patch(resource, json={field: second[field]})).status_code == 200
    assert (await client.get(URL)).json()["data"]["total"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_not_found(client: AsyncClient, method: str) -> None:
    response = await client.request(method, f"{URL}/999", json={} if method == "patch" else None)
    assert response.status_code == 404
    assert response.json()["code"] == 30002
    assert response.json()["message"] == "User not found"


@pytest.mark.asyncio
async def test_pagination_and_nullable_email(client: AsyncClient) -> None:
    empty = await client.get(URL)
    assert empty.json()["data"] == {"items": [], "total": 0, "page": 1, "size": 20}
    ids: list[str] = []
    for index in range(5):
        response = await client.post(URL, json={"username": f"user-{index}", "password": PASSWORD})
        assert response.status_code == 201
        ids.append(response.json()["data"]["id"])
    for page, expected in [(1, ids[:2]), (2, ids[2:4]), (3, ids[4:]), (4, [])]:
        response = await client.get(URL, params={"page": page, "size": 2})
        assert response.status_code == 200
        data = response.json()["data"]
        assert [item["id"] for item in data["items"]] == expected
        assert (data["total"], data["page"], data["size"]) == (5, page, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"username": ""},
        {"username": "x" * 65},
        {"username": "white space"},
        {"email": "invalid"},
        {"password": "short"},
        {"password": "x" * 129},
        {"password": None},
        {"is_active": None},
        {"is_superuser": True},
        {"password_hash": "forged"},
    ],
)
async def test_create_validation(client: AsyncClient, payload: dict[str, object]) -> None:
    data = {"username": "alice", "password": PASSWORD} | payload if payload else {}
    response = await client.post(URL, json=data)
    assert response.status_code == 422
    assert response.json()["code"] == 40001
    assert "detail" not in response.json()
    assert PASSWORD not in response.text
    assert (await client.get(URL)).json()["data"]["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"username": None},
        {"is_active": None},
        {"email": "invalid"},
        {"password": PASSWORD},
        {"password_hash": "forged"},
        {"is_superuser": True},
        {"id": 2},
        {"created_at": "2026-01-01T00:00:00Z"},
    ],
)
async def test_patch_validation(client: AsyncClient, payload: dict[str, object]) -> None:
    created = await client.post(URL, json={"username": "alice", "password": PASSWORD})
    user = created.json()["data"]
    resource = f"{URL}/{user['id']}"
    response = await client.patch(resource, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == 40001
    assert PASSWORD not in response.text
    assert (await client.get(resource)).json()["data"] == user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query", ["page=0", "size=0", "size=101", "page=no", "sort_by=password_hash"]
)
async def test_query_validation(client: AsyncClient, query: str) -> None:
    response = await client.get(f"{URL}?{query}")
    assert response.status_code == 422
    assert response.json()["code"] == 40001


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["0", "-1", "abc", "9223372036854775808"])
async def test_id_validation(client: AsyncClient, identifier: str) -> None:
    response = await client.get(f"{URL}/{identifier}")
    assert response.status_code == 422
    assert response.json()["code"] == 40001


@pytest.mark.asyncio
async def test_openapi(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    models = schema["components"]["schemas"]
    user = models["UserResponse"]
    assert user["properties"]["id"]["type"] == "string"
    assert "password" not in user["properties"]
    assert "password_hash" not in user["properties"]
    assert "password" not in models["UserUpdate"]["properties"]
    assert "is_superuser" not in models["UserUpdate"]["properties"]
    assert models["UserUpdate"]["additionalProperties"] is False
    for path in (URL, f"{URL}/{{id}}"):
        for operation in schema["paths"][path].values():
            assert operation["summary"] and operation["description"]
            assert operation["tags"] == ["users"]
            for status in ("404", "422", "500"):
                response = operation["responses"][status]["content"]["application/json"]["schema"]
                assert response == {"$ref": "#/components/schemas/ErrorResponse"}
    for path, method in [(URL, "post"), (f"{URL}/{{id}}", "patch")]:
        assert "409" in schema["paths"][path][method]["responses"]
    response = schema["paths"][URL]["get"]["responses"]["200"]["content"]["application/json"]
    envelope = models[response["schema"]["$ref"].split("/")[-1]]
    page = models[envelope["properties"]["data"]["$ref"].split("/")[-1]]
    assert set(page["properties"]) == {"items", "total", "page", "size"}
    assert page["properties"]["items"]["items"] == {"$ref": "#/components/schemas/UserResponse"}
