"""通过真实应用验证 Health 和 OpenAPI 契约。"""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.bootstrap.application import create_app
from app.core.config import Environment, Settings


@pytest.mark.asyncio
async def test_health(settings: Settings) -> None:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_openapi_generation(settings: Settings) -> None:
    app = create_app(settings)
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "FastAPI Plus"
    assert set(schema["paths"]) == {
        "/health",
        "/api/v1/users",
        "/api/v1/users/{id}",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/files",
        "/api/v1/files/{id}",
        "/api/v1/files/{id}/download",
    }
    response_schema = schema["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert response_schema == {"$ref": "#/components/schemas/HealthResponse"}
    health_schema = schema["components"]["schemas"]["HealthResponse"]
    assert health_schema["required"] == ["status"]
    assert health_schema["properties"]["status"]["const"] == "ok"
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200
            assert response.json() == schema


@pytest.mark.parametrize("environment", list(Environment))
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.asyncio
async def test_openapi_visibility_is_independent(environment: Environment, enabled: bool) -> None:
    app = create_app(
        Settings(
            environment=environment,
            openapi_enabled=enabled,
            jwt_secret=SecretStr("test-only-secret-" * 3),
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for path in ("/openapi.json", "/docs", "/redoc"):
                assert (await client.get(path)).status_code == (200 if enabled else 404)
            assert (await client.get("/health")).json() == {"status": "ok"}
