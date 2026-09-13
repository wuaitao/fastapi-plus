"""集中转换 HTTP 错误，输出只使用已定义的安全信息"""

import sqlite3
from collections.abc import Mapping
from http import HTTPStatus

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as DatabaseTimeoutError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.common.response import ErrorResponse, ValidationData, ValidationIssue
from app.core.exceptions import (
    COMMON_ERRORS,
    HTTP_ERROR,
    INFRASTRUCTURE_UNAVAILABLE,
    INTERNAL_ERROR,
    VALIDATION_ERROR,
    AppException,
    ErrorDescriptor,
)
from app.core.logging.redaction import exception_diagnostics, redact_text

logger = structlog.get_logger(__name__)
_HTTP_ERRORS = {error.status_code: error for error in COMMON_ERRORS}


def error_response(
    request: Request,
    descriptor: ErrorDescriptor,
    *,
    data: ValidationData | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id: str | None = getattr(request.state, "request_id", None)
    body = ErrorResponse(
        code=descriptor.code, message=descriptor.message, data=data, request_id=request_id
    )
    response_headers = dict(headers or {})
    if descriptor.status_code == 401:
        response_headers.setdefault("WWW-Authenticate", "Bearer")
    if request_id is not None:
        response_headers["X-Request-ID"] = request_id
    return JSONResponse(
        status_code=descriptor.status_code,
        content=body.model_dump(mode="json"),
        headers=response_headers,
    )


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppException)
    return error_response(request, exc.descriptor)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    issues: list[ValidationIssue] = []
    for error in exc.errors():
        location = error["loc"]
        if location and location[0] in {"body", "query", "path", "header", "cookie"}:
            location = location[1:]
        # msg/ctx 可能含自定义校验器拼接的输入或异常文本，不能直接回显。
        error_type = error["type"]
        issues.append(
            ValidationIssue(
                field=redact_text(".".join(str(part) for part in location)),
                message="Field required" if error_type == "missing" else "Invalid value",
                type=redact_text(error_type),
            )
        )
    return error_response(request, VALIDATION_ERROR, data=ValidationData(errors=issues))


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    descriptor = _HTTP_ERRORS.get(exc.status_code)
    if descriptor is None:
        try:
            message = HTTPStatus(exc.status_code).phrase
        except ValueError:
            message = HTTP_ERROR.message
        descriptor = ErrorDescriptor(HTTP_ERROR.code, HTTP_ERROR.key, message, exc.status_code)
    # 保留 Allow、WWW-Authenticate、Retry-After 等 HTTP 语义，不回显 detail。
    return error_response(request, descriptor, headers=exc.headers)


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 流式响应开始后异常会继续传播到框架兜底，避免再次记录同一诊断。
    if not getattr(request.state, "exception_logged", False):
        logger.error("request.failed", **exception_diagnostics(exc))
        request.state.exception_logged = True
    # 仅识别连接池超时、已失效连接和 SQLite BUSY；SQL/约束错误仍保留 500。
    # 扩展错误码低 8 位是主错误码，例如 SQLITE_BUSY_SNAPSHOT 也属于锁竞争。
    unavailable = isinstance(exc, DatabaseTimeoutError)
    if isinstance(exc, DBAPIError):
        unavailable = exc.connection_invalidated or (
            isinstance(exc.orig, sqlite3.OperationalError)
            and getattr(exc.orig, "sqlite_errorcode", 0) & 0xFF == sqlite3.SQLITE_BUSY
        )
    return error_response(request, INFRASTRUCTURE_UNAVAILABLE if unavailable else INTERNAL_ERROR)
