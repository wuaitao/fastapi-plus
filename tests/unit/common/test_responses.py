"""验证泛型序列化与分页边界。"""

import pytest
from pydantic import BaseModel, ValidationError

from app.common.pagination import Page
from app.common.response import ApiResponse, ErrorResponse


class Item(BaseModel):
    name: str


def test_typed_page_response() -> None:
    response = ApiResponse[Page[Item]](data=Page(items=[Item(name="sample")], total=1))
    assert response.model_dump() == {
        "code": 0,
        "message": "success",
        "data": {"items": [{"name": "sample"}], "total": 1, "page": 1, "size": 20},
    }
    with pytest.raises(ValidationError):
        ApiResponse[Page[Item]].model_validate({"data": {"items": [123], "total": 1}})


def test_empty_and_null_responses() -> None:
    assert Page[Item](items=[], total=0).model_dump()["items"] == []
    assert ApiResponse[None](data=None).model_dump() == {
        "code": 0,
        "message": "success",
        "data": None,
    }
    assert ErrorResponse(code=10001, message="Internal server error").data is None


@pytest.mark.parametrize("values", [{"page": 0}, {"size": 0}, {"size": 101}, {"total": -1}])
def test_invalid_page(values: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Page[Item].model_validate({"items": [], "total": 0, **values})
