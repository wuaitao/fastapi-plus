"""通过测试专用路由验收核心契约，不引入业务模块。"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from io import StringIO
from typing import Annotated, cast
from uuid import UUID

import pytest
import pytest_asyncio
import structlog
from fastapi import FastAPI, Query, Request
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse, StreamingResponse
from starlette.types import Message, Scope

from app.bootstrap.application import create_app
from app.common.pagination import Page
from app.common.response import ApiResponse
from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationException,
    AuthorizationException,
    BusinessException,
    ErrorDescriptor,
    InfrastructureException,
)


class Input(BaseModel):
    count: int
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value == "sensitive-input":
            raise ValueError(f"private validation text {value}")
        return value


@pytest.fixture
def log_output() -> StringIO:
    return StringIO()


@pytest.fixture
def app(log_output: StringIO) -> FastAPI:
    application = create_app(Settings(log_format="json"))
    # 保留真实 Handler/Formatter，只把输出流设为跨测试阶段稳定的内存流。
    for handler in logging.getLogger().handlers:
        assert isinstance(handler, logging.StreamHandler)
        cast("logging.StreamHandler[StringIO]", handler).setStream(log_output)

    @application.post("/probe")
    async def probe(value: Input) -> ApiResponse[int]:
        return ApiResponse(data=value.count)

    @application.get("/page")
    async def page(size: Annotated[int, Query(ge=1, le=100)] = 20) -> ApiResponse[Page[int]]:
        return ApiResponse(data=Page(items=[1], total=1, size=size))

    @application.get("/failure/{kind}")
    async def failure(kind: str) -> None:
        if kind == "auth":
            raise AuthenticationException()
        if kind == "permission":
            raise AuthorizationException()
        if kind == "infrastructure":
            raise InfrastructureException()
        if kind == "business":
            raise BusinessException(ErrorDescriptor(10005, "CONFLICT", "Conflict", 409))
        if kind == "http":
            raise HTTPException(429, "private detail", headers={"Retry-After": "10"})
        if kind == "challenge":
            raise HTTPException(401, "private detail", headers={"WWW-Authenticate": "Bearer"})
        raise RuntimeError("sensitive-input SELECT * FROM private /private/file.py")

    @application.get("/context")
    async def context(request: Request) -> ApiResponse[str]:
        structlog.contextvars.bind_contextvars(actor_id="request-actor")
        await asyncio.sleep(0)
        structlog.get_logger().info("context.observed")
        return ApiResponse(data=request.state.request_id)

    @application.get("/sync-context")
    def sync_context(request: Request) -> ApiResponse[str]:
        structlog.get_logger().info("context.observed")
        return ApiResponse(data=request.state.request_id)

    @application.get("/stream")
    async def stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"first"
            yield b"second"

        return StreamingResponse(chunks(), media_type="application/octet-stream")

    @application.get("/redirect")
    async def redirect() -> RedirectResponse:
        return RedirectResponse("/health")

    @application.get("/broken-stream")
    async def broken_stream() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"first"
            raise RuntimeError("stream-secret")

        return StreamingResponse(chunks())

    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as current:
            yield current


@pytest.mark.asyncio
async def test_validation_format_and_safe_messages(client: AsyncClient) -> None:
    response = await client.post(
        "/probe", json={"count": "sensitive-input", "password": "sensitive-input"}
    )
    assert response.status_code == 422
    assert response.json() == {
        "code": 40001,
        "message": "Validation error",
        "data": {
            "errors": [
                {"field": "count", "message": "Invalid value", "type": "int_parsing"},
                {"field": "password", "message": "Invalid value", "type": "value_error"},
            ]
        },
        "request_id": response.headers["X-Request-ID"],
    }
    assert "sensitive-input" not in response.text
    missing = await client.post("/probe", json={})
    assert missing.json()["data"]["errors"][0] == {
        "field": "count",
        "message": "Field required",
        "type": "missing",
    }
    malformed = await client.post("/probe", content='{"password":"sensitive-input",')
    assert malformed.status_code == 422
    assert "sensitive-input" not in malformed.text


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("GET", "/missing", 404, 10003),
        ("POST", "/health", 405, 10004),
        ("GET", "/failure/auth", 401, 20001),
        ("GET", "/failure/permission", 403, 21001),
        ("GET", "/failure/infrastructure", 503, 11001),
        ("GET", "/failure/business", 409, 10005),
        ("GET", "/failure/http", 429, 10002),
        ("GET", "/failure/challenge", 401, 20001),
    ],
)
@pytest.mark.asyncio
async def test_error_mapping(
    client: AsyncClient, method: str, path: str, status: int, code: int
) -> None:
    response = await client.request(method, path, headers={"X-Request-ID": "error-request"})
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"code", "message", "data", "request_id"}
    assert body["code"] == code
    assert body["data"] is None
    assert body["request_id"] == response.headers["X-Request-ID"] == "error-request"
    assert "private detail" not in response.text
    if status == 405:
        assert "GET" in response.headers["Allow"]
    if path.endswith("/http"):
        assert response.headers["Retry-After"] == "10"
    if path.endswith("/challenge"):
        assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("debug", [False, True])
@pytest.mark.asyncio
async def test_safe_500_with_context(
    app: FastAPI, client: AsyncClient, debug: bool, log_output: StringIO
) -> None:
    app.debug = debug
    response = await client.get(
        "/failure/unexpected?token=query-secret",
        headers={"X-Request-ID": "failed-request", "Accept": "text/html"},
    )
    assert response.status_code == 500
    assert response.json() == {
        "code": 10001,
        "message": "Internal server error",
        "data": None,
        "request_id": "failed-request",
    }
    assert response.headers["X-Request-ID"] == "failed-request"
    output = log_output.getvalue()
    for secret in ("sensitive-input", "SELECT", "/private/file.py", "Traceback", "query-secret"):
        assert secret not in output + response.text
    events = [json.loads(line) for line in output.splitlines()]
    failures = [event for event in events if event["event"] == "request.failed"]
    assert len(failures) == 1
    assert failures[0]["request_id"] == "failed-request"
    assert failures[0]["error_type"] == "RuntimeError"
    assert failures[0]["frames"][-1]["function"] == "failure"
    completed = [event for event in events if event["event"] == "request.completed"]
    assert len(completed) == 1
    assert completed[0]["status_code"] == 500
    assert completed[0]["duration_ms"] >= 0
    assert structlog.contextvars.get_contextvars() == {}


@pytest.mark.parametrize("incoming", [None, "", "bad id", "line\nbreak", "x" * 65, "valid_ID-123"])
@pytest.mark.asyncio
async def test_request_id(client: AsyncClient, incoming: str | None) -> None:
    response = await client.get(
        "/health", headers={} if incoming is None else {"X-Request-ID": incoming}
    )
    request_id = response.headers["X-Request-ID"]
    if incoming == "valid_ID-123":
        assert request_id == incoming
    else:
        assert UUID(request_id).version == 4
        assert request_id != incoming
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_duplicate_request_id_headers(client: AsyncClient) -> None:
    response = await client.get(
        "/health", headers=[("X-Request-ID", "first"), ("X-Request-ID", "second")]
    )
    assert UUID(response.headers["X-Request-ID"]).version == 4


@pytest.mark.asyncio
async def test_concurrent_context_and_cleanup(client: AsyncClient, log_output: StringIO) -> None:
    structlog.contextvars.bind_contextvars(correlation_id="outer")
    responses = await asyncio.gather(
        *[
            client.get("/context", headers={"X-Request-ID": request_id})
            for request_id in ("first", "second")
        ]
    )
    assert [response.json()["data"] for response in responses] == ["first", "second"]
    await client.get("/sync-context", headers={"X-Request-ID": "third"})
    events = [json.loads(line) for line in log_output.getvalue().splitlines()]
    observed = [event for event in events if event["event"] == "context.observed"]
    assert {event["request_id"] for event in observed} == {"first", "second", "third"}
    assert all("correlation_id" not in event for event in observed)
    assert "actor_id" not in observed[-1]
    completed = [event for event in events if event["event"] == "request.completed"]
    assert len(completed) == 3
    assert all(event["method"] == "GET" and event["status_code"] == 200 for event in completed)
    assert structlog.contextvars.get_contextvars() == {"correlation_id": "outer"}


@pytest.mark.asyncio
async def test_stream_and_redirect_are_not_wrapped(client: AsyncClient) -> None:
    stream = await client.get("/stream")
    assert stream.content == b"firstsecond"
    assert stream.headers["content-type"] == "application/octet-stream"
    assert stream.headers["X-Request-ID"]
    redirect = await client.get("/redirect")
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/health"
    assert redirect.content == b""
    assert redirect.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_stream_failure_preserves_started_response(
    app: FastAPI, log_output: StringIO
) -> None:
    messages: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET",
        "path": "/broken-stream",
        "query_string": b"",
        "headers": [(b"x-request-id", b"stream-request")],
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    async with app.router.lifespan_context(app):
        with pytest.raises(RuntimeError, match="stream-secret"):
            await app(scope, receive, send)
    starts = [message for message in messages if message["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 200
    assert (b"x-request-id", b"stream-request") in starts[0]["headers"]
    assert "stream-secret" not in str(messages) + log_output.getvalue()
    events = [json.loads(line) for line in log_output.getvalue().splitlines()]
    failures = [event for event in events if event["event"] == "request.failed"]
    assert len(failures) == 1
    assert failures[0]["request_id"] == "stream-request"
    assert len([event for event in events if event["event"] == "request.completed"]) == 1
    assert structlog.contextvars.get_contextvars() == {}


@pytest.mark.asyncio
async def test_generic_responses_and_openapi(app: FastAPI, client: AsyncClient) -> None:
    response = await client.get("/page")
    assert response.json() == {
        "code": 0,
        "message": "success",
        "data": {"items": [1], "total": 1, "page": 1, "size": 20},
    }
    invalid = await client.get("/page?size=101")
    assert invalid.status_code == 422
    assert invalid.json()["data"]["errors"][0]["field"] == "size"
    schema = app.openapi()
    responses = schema["paths"]["/page"]["get"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    assert responses["500"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
    schemas = schema["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    reference = responses["200"]["content"]["application/json"]["schema"]["$ref"]
    envelope = schemas[reference.rsplit("/", 1)[1]]
    page = schemas[envelope["properties"]["data"]["$ref"].rsplit("/", 1)[1]]
    assert page["properties"]["items"]["items"]["type"] == "integer"
