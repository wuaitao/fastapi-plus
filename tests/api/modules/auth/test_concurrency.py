"""真实认证与并发写入不能因共享读事务触发 SQLite 锁升级失败。"""

import asyncio

import pytest
from argon2 import PasswordHasher
from httpx import AsyncClient

from app.modules.user import service as user_service
from app.modules.user.model import User
from app.modules.user.repository import UserRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("duplicate", [False, True])
async def test_authenticated_concurrent_creates(
    client: AsyncClient, users: dict[str, User], monkeypatch: pytest.MonkeyPatch, duplicate: bool
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "auth-test-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    original = user_service.hash_password
    ready = asyncio.Event()
    arrived = 0

    async def synchronized_hash(password: str, hasher: PasswordHasher) -> str:
        nonlocal arrived
        result = await original(password, hasher)
        arrived += 1
        if arrived == 2:
            ready.set()
        # 两个请求都完成真实认证和哈希后再写库，确定性覆盖读锁升级竞争。
        await asyncio.wait_for(ready.wait(), timeout=10)
        return result

    monkeypatch.setattr(user_service, "hash_password", synchronized_hash)
    responses = await asyncio.gather(
        *(
            client.post(
                "/api/v1/users",
                json={
                    "username": f"concurrent-{0 if duplicate else index}",
                    "password": "test-only-password",
                },
                headers=headers,
            )
            for index in range(2)
        )
    )
    assert sorted(response.status_code for response in responses) == (
        [201, 409] if duplicate else [201, 201]
    )
    listed = await client.get("/api/v1/users", headers=headers)
    assert listed.status_code == 200
    names = {item["username"] for item in listed.json()["data"]["items"]}
    assert "concurrent-0" in names
    assert ("concurrent-1" in names) is not duplicate


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["patch", "delete"])
async def test_concurrent_writes_report_contention_and_recover(
    client: AsyncClient, users: dict[str, User], monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "operator", "password": "auth-test-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    targets = [users[name].id for name in ("alice", "disabled")]
    ready = asyncio.Event()
    arrived = 0
    original = UserRepository.get

    async def synchronized_get(repository: UserRepository, identifier: int) -> User | None:
        nonlocal arrived
        user = await original(repository, identifier)
        if identifier in targets:
            arrived += 1
            if arrived == 2:
                ready.set()
            # 两个业务事务都读取记录后再写，覆盖 SQLite 单写者的真实锁竞争。
            await asyncio.wait_for(ready.wait(), timeout=10)
        return user

    monkeypatch.setattr(UserRepository, "get", synchronized_get)

    async def write(identifier: int) -> int:
        response = await client.request(
            method,
            f"/api/v1/users/{identifier}",
            headers=headers,
            json={"username": f"changed-{identifier}"} if method == "patch" else None,
        )
        if response.status_code == 503:
            assert response.json()["code"] == 11001
            assert "locked" not in response.text
        return response.status_code

    statuses = await asyncio.gather(*(write(identifier) for identifier in targets))
    assert sorted(statuses) == [200, 503]
    # 锁已释放后显式重试失败请求，验证回滚不会污染后续 Session 或记录。
    assert await write(targets[statuses.index(503)]) == 200
    for identifier in targets:
        response = await client.get(f"/api/v1/users/{identifier}", headers=headers)
        assert response.status_code == (200 if method == "patch" else 404)
        if method == "patch":
            assert response.json()["data"]["username"] == f"changed-{identifier}"
