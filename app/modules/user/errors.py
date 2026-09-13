"""用户错误及已知唯一约束的识别，不对外暴露数据库诊断"""

import re
import sqlite3

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ErrorDescriptor

USER_ALREADY_EXISTS = ErrorDescriptor(30001, "USER_ALREADY_EXISTS", "User already exists", 409)
USER_NOT_FOUND = ErrorDescriptor(30002, "USER_NOT_FOUND", "User not found", 404)
USER_DISABLED = ErrorDescriptor(30003, "USER_DISABLED", "User disabled", 403)
USER_SELF_DELETE = ErrorDescriptor(30004, "USER_SELF_DELETE", "Cannot delete yourself", 403)


def is_user_unique_violation(error: IntegrityError) -> bool:
    original = error.orig
    if original is None:
        return False
    constraints = {"uq_users_username", "uq_users_email"}
    if isinstance(original, sqlite3.IntegrityError):
        # SQLite 不报告约束名，因此同时核对错误码和完整列名。
        return original.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_UNIQUE and str(original) in {
            "UNIQUE constraint failed: users.username",
            "UNIQUE constraint failed: users.email",
        }
    if getattr(original, "sqlstate", None) == "23505":
        # asyncpg 原始异常保存在 SQLAlchemy 适配异常的 cause 中。
        return getattr(original.__cause__, "constraint_name", None) in constraints
    if len(original.args) >= 2 and original.args[0] == 1062:
        # MySQL 1062 还可能是其他唯一键；只接受消息末尾的已知键名。
        match = re.search(r"for key '(?:users\.)?([^']+)'$", str(original.args[1]))
        return match is not None and match.group(1) in constraints
    return False
