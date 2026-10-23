"""应用异常公共入口；导入异常不加载 HTTP Handler"""

from app.core.exceptions.base import (
    AppException,
    AuthenticationException,
    AuthorizationException,
    BusinessException,
    InfrastructureException,
)
from app.core.exceptions.common import (
    BODY_TOO_LARGE,
    COMMON_ERRORS,
    HTTP_ERROR,
    INFRASTRUCTURE_UNAVAILABLE,
    INTERNAL_ERROR,
    INVALID_CREDENTIALS,
    METHOD_NOT_ALLOWED,
    NOT_FOUND,
    PERMISSION_DENIED,
    VALIDATION_ERROR,
)
from app.core.exceptions.descriptors import ErrorDescriptor

__all__ = [
    "AppException",
    "AuthenticationException",
    "AuthorizationException",
    "BusinessException",
    "InfrastructureException",
    "ErrorDescriptor",
    "COMMON_ERRORS",
    "INTERNAL_ERROR",
    "HTTP_ERROR",
    "NOT_FOUND",
    "METHOD_NOT_ALLOWED",
    "BODY_TOO_LARGE",
    "INFRASTRUCTURE_UNAVAILABLE",
    "INVALID_CREDENTIALS",
    "PERMISSION_DENIED",
    "VALIDATION_ERROR",
]
