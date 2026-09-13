"""公共错误编号唯一，分类不改变描述符的 HTTP 语义。"""

from dataclasses import FrozenInstanceError

import pytest

from app.core.exceptions import (
    COMMON_ERRORS,
    INTERNAL_ERROR,
    AppException,
    AuthenticationException,
    AuthorizationException,
    BusinessException,
    ErrorDescriptor,
    InfrastructureException,
)


def test_common_errors_are_unique_and_immutable() -> None:
    assert len({error.code for error in COMMON_ERRORS}) == len(COMMON_ERRORS)
    assert len({error.key for error in COMMON_ERRORS}) == len(COMMON_ERRORS)
    with pytest.raises(FrozenInstanceError):
        INTERNAL_ERROR.__setattr__("message", "changed")


@pytest.mark.parametrize(
    ("exception", "code", "status"),
    [
        (AppException(INTERNAL_ERROR), 10001, 500),
        (AuthenticationException(), 20001, 401),
        (AuthorizationException(), 21001, 403),
        (InfrastructureException(), 11001, 503),
        (BusinessException(ErrorDescriptor(10005, "CONFLICT", "Conflict", 409)), 10005, 409),
    ],
)
def test_exception_descriptor(exception: AppException, code: int, status: int) -> None:
    assert exception.descriptor.code == code
    assert exception.descriptor.status_code == status
    assert str(exception) == exception.descriptor.message
