"""JSON 业务响应契约，保留具体数据类型"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: Literal[0] = 0
    message: str = "success"
    data: T


class ValidationIssue(BaseModel):
    field: str
    message: str
    type: str


class ValidationData(BaseModel):
    errors: list[ValidationIssue]


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: ValidationData | None = None
    request_id: str | None = None
