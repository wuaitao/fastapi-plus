"""驱动诊断只识别用户已知唯一键；不依赖外部数据库服务。"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import COMMON_ERRORS
from app.modules.user.errors import (
    USER_ALREADY_EXISTS,
    USER_DISABLED,
    USER_NOT_FOUND,
    USER_SELF_DELETE,
    is_user_unique_violation,
)


def test_error_descriptors_are_unique() -> None:
    descriptors = (
        *COMMON_ERRORS,
        USER_ALREADY_EXISTS,
        USER_NOT_FOUND,
        USER_DISABLED,
        USER_SELF_DELETE,
    )
    assert len({item.code for item in descriptors}) == len(descriptors)
    assert len({item.key for item in descriptors}) == len(descriptors)


@pytest.mark.parametrize("constraint", ["uq_users_username", "uq_users_email", "pk_users", "other"])
def test_postgresql_unique_constraints(constraint: str) -> None:
    class DriverError(Exception):
        constraint_name = constraint

    class AdaptedError(Exception):
        sqlstate = "23505"

    original = AdaptedError()
    original.__cause__ = DriverError()
    error = IntegrityError("", {}, original)
    assert is_user_unique_violation(error) == (
        constraint in {"uq_users_username", "uq_users_email"}
    )
    original.sqlstate = "23502"
    assert not is_user_unique_violation(error)


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        (1062, "Duplicate entry 'alice' for key 'uq_users_username'", True),
        (1062, "Duplicate entry 'alice@example.com' for key 'users.uq_users_email'", True),
        (1062, "Duplicate entry 'uq_users_username' for key 'PRIMARY'", False),
        (1048, "Column 'username' cannot be null", False),
    ],
)
def test_mysql_unique_constraints(code: int, message: str, expected: bool) -> None:
    assert is_user_unique_violation(IntegrityError("", {}, Exception(code, message))) is expected
