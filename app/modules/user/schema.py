"""创建、局部更新、查询和公开响应各自声明允许的字段"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_serializer,
    model_validator,
)

Username = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]
Email = Annotated[EmailStr, Field(max_length=254)]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username
    email: Email | None = None
    password: SecretStr = Field(min_length=8, max_length=128)
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: Username | None = None
    email: Email | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> Self:
        """区分 PATCH 省略与显式空值，仅允许清空邮箱"""
        # PATCH 省略字段表示保持原值；只有 email 允许通过显式 null 清空。
        for name in ("username", "is_active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} 不能为 null")
        return self


class UserQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        """统一将用户 ID 输出为字符串，避免 JavaScript 整数精度丢失"""
        # 由 Schema 统一保证 JSON 和 OpenAPI 的 ID 类型，避免 JavaScript 精度丢失。
        return str(value)
