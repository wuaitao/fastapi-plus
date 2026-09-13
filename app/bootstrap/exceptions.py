"""集中注册应用及框架异常处理器"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.core.exceptions import AppException
from app.core.exceptions.handlers import (
    app_exception_handler,
    http_exception_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)


def register_exception_handlers(app: FastAPI) -> None:
    """集中注册应用异常、参数校验及框架错误的响应转换"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)
