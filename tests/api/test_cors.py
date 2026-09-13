"""验证浏览器跨域预检、错误可读性及请求上下文。"""

import json
from collections.abc import AsyncIterator

import pytest
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Headers
from starlette.types import Message, Scope

from app.bootstrap.application import create_app
from app.core.config import Settings
from app.core.exceptions import AuthorizationException, InfrastructureException

ORIGIN = "https://frontend.example.com"


@pytest.mark.asyncio
async def test_cors_disabled_by_default() -> None:
    app = create_app(Settings())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": ORIGIN})
        preflight = await client.options(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
    assert preflight.status_code == 405
    assert "access-control-allow-origin" not in preflight.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE", "HEAD"])
async def test_cors_preflight(method: str, capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app(Settings(cors_allow_origins=(ORIGIN,), log_format="json"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/users",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "authorization,content-type,x-request-id",
                "X-Request-ID": "preflight-request",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert method in response.headers["access-control-allow-methods"].split(", ")
    assert "access-control-allow-credentials" not in response.headers
    assert response.headers["x-request-id"] == "preflight-request"
    events = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    completed = [event for event in events if event["event"] == "request.completed"]
    assert len(completed) == 1
    assert completed[0]["status_code"] == 200
    assert completed[0]["request_id"] == "preflight-request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("origin", "method", "header"),
    [
        ("https://untrusted.example.com", "POST", "authorization"),
        (ORIGIN, "TRACE", "authorization"),
        (ORIGIN, "POST", "x-unapproved"),
    ],
)
async def test_cors_rejects_unapproved_preflight(origin: str, method: str, header: str) -> None:
    app = create_app(Settings(cors_allow_origins=(ORIGIN,)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/users",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": header,
            },
        )
        simple = await client.get("/health", headers={"Origin": "https://untrusted.example.com"})
    assert response.status_code == 400
    assert response.headers["x-request-id"]
    if origin != ORIGIN:
        assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in simple.headers


@pytest.mark.asyncio
@pytest.mark.parametrize("debug", [False, True])
async def test_cors_preserves_success_errors_and_request_ids(
    debug: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(Settings(cors_allow_origins=(ORIGIN,), debug=debug, log_format="json"))

    @app.get("/failure")
    async def failure() -> None:
        raise RuntimeError("private-error-detail")

    @app.get("/unavailable")
    async def unavailable() -> None:
        raise InfrastructureException()

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise AuthorizationException()

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        for method, path, status in [
            ("GET", "/health", 200),
            ("GET", "/api/v1/auth/me", 401),
            ("GET", "/forbidden", 403),
            ("GET", "/missing", 404),
            ("POST", "/health", 405),
            ("POST", "/api/v1/auth/login", 422),
            ("GET", "/failure", 500),
            ("GET", "/unavailable", 503),
        ]:
            response = await client.request(
                method, path, headers={"Origin": ORIGIN, "X-Request-ID": "cors-request"}
            )
            assert response.status_code == status
            assert response.headers["access-control-allow-origin"] == ORIGIN
            assert "Origin" in response.headers["vary"]
            assert "X-Request-ID" in response.headers["access-control-expose-headers"]
            assert "Content-Disposition" in response.headers["access-control-expose-headers"]
            assert response.headers["x-request-id"] == "cors-request"
            assert "access-control-allow-credentials" not in response.headers
            assert "private-error-detail" not in response.text
            if status >= 400:
                assert response.json()["request_id"] == "cors-request"
    output = capsys.readouterr().err
    assert "private-error-detail" not in output
    events = [json.loads(line) for line in output.splitlines()]
    assert len([event for event in events if event["event"] == "request.completed"]) == 8
    assert len([event for event in events if event["event"] == "request.failed"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [False, True])
async def test_cors_stream_preserves_chunks_and_single_response(broken: bool) -> None:
    app = create_app(Settings(cors_allow_origins=(ORIGIN,)))

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"first"
            if broken:
                raise RuntimeError("stream-interrupted")
            yield b"second"

        return StreamingResponse(chunks(), media_type="application/octet-stream")

    messages: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET",
        "path": "/stream",
        "query_string": b"",
        "scheme": "http",
        "headers": [(b"origin", ORIGIN.encode()), (b"x-request-id", b"stream-request")],
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    if broken:
        with pytest.raises(RuntimeError, match="stream-interrupted"):
            await app(scope, receive, send)
    else:
        await app(scope, receive, send)
    starts = [message for message in messages if message["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 200
    headers = Headers(scope=starts[0])
    assert headers["access-control-allow-origin"] == ORIGIN
    assert headers["x-request-id"] == "stream-request"
    chunks_sent = [
        message["body"] for message in messages if message["type"] == "http.response.body"
    ]
    assert chunks_sent == ([b"first"] if broken else [b"first", b"second", b""])
