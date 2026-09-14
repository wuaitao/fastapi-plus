"""创建用户表及具名唯一约束"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_create_users"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建带独立认证标识的用户表，SQLite 用户主键禁止自动复用"""
    op.create_table(
        "users",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, comment="主键"
        ),
        # 随机认证标识由应用创建用户时生成，原始 SQL 写入也须提供独立标识。
        sa.Column("auth_id", sa.String(32), nullable=False, comment="随机认证标识"),
        sa.Column("username", sa.String(64), nullable=False, comment="登录用户名"),
        sa.Column("email", sa.String(254), nullable=True, comment="邮箱，可为空"),
        sa.Column("password_hash", sa.String(255), nullable=False, comment="Argon2 密码哈希"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False, comment="账号是否启用"),
        sa.Column("is_superuser", sa.Boolean(), server_default=sa.false(), nullable=False, comment="是否为超级管理员"),
        # 与 TimestampMixin 一致，存储无时区 UTC，由 ORM 维护时间值。
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("auth_id", name="uq_users_auth_id"),
        sqlite_autoincrement=True,
        comment="用户账号与身份状态",
    )


def downgrade() -> None:
    op.drop_table("users")
