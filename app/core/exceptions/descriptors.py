"""稳定错误描述符，不依赖 HTTP 框架"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDescriptor:
    code: int
    key: str
    message: str
    status_code: int
