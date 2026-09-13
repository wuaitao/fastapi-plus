"""分页 Schema 与应用结果；不依赖 ORM 或具体业务模块"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=100)


@dataclass(frozen=True)
class PageResult(Generic[T]):
    """包含 ORM 对象的应用结果，由 Router 转换为公开分页 Schema"""

    items: list[T]
    total: int
    page: int
    size: int
