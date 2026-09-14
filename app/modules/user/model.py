"""用户持久化模型，密码仅存储哈希"""

from uuid import uuid4

from sqlalchemy import Boolean, String, UniqueConstraint, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("auth_id", name="uq_users_auth_id"),
        # SQLite 不复用已删除 ID，避免短 TTL 身份快照关联到新用户的业务资源。
        {"comment": "用户账号与身份状态", "sqlite_autoincrement": True},
    )

    # 认证身份与可复用的整数主键分离；创建后不通过用户更新接口修改。
    auth_id: Mapped[str] = mapped_column(
        String(32), default=lambda: uuid4().hex, nullable=False, comment="随机认证标识"
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="登录用户名")
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, comment="邮箱，可为空")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="Argon2 密码哈希")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False, comment="账号是否启用"
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, comment="是否为超级管理员"
    )
