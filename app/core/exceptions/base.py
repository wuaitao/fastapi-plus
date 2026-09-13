"""应用异常分类，业务层仅依赖稳定描述符"""

from app.core.exceptions.common import (
    INFRASTRUCTURE_UNAVAILABLE,
    INVALID_CREDENTIALS,
    PERMISSION_DENIED,
)
from app.core.exceptions.descriptors import ErrorDescriptor


class AppException(Exception):
    def __init__(self, descriptor: ErrorDescriptor) -> None:
        self.descriptor = descriptor
        super().__init__(descriptor.message)


class BusinessException(AppException):
    """由模块自己的描述符定义业务失败"""


class AuthenticationException(AppException):
    def __init__(self, descriptor: ErrorDescriptor = INVALID_CREDENTIALS) -> None:
        super().__init__(descriptor)


class AuthorizationException(AppException):
    def __init__(self, descriptor: ErrorDescriptor = PERMISSION_DENIED) -> None:
        super().__init__(descriptor)


class InfrastructureException(AppException):
    def __init__(self, descriptor: ErrorDescriptor = INFRASTRUCTURE_UNAVAILABLE) -> None:
        super().__init__(descriptor)
