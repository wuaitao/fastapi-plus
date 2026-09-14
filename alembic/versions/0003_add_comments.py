"""补充表和字段注释；保留已应用的建表迁移"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_add_comments"
down_revision: str | None = "0002_create_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 迁移保留独立的历史快照，不从业务模型读取未来可能变化的注释或类型。
_TABLES = (
    sa.Table(
        "users",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), nullable=False, comment="数据库生成的整数主键"),
        sa.Column("username", sa.String(64), nullable=False, comment="唯一登录用户名"),
        sa.Column("email", sa.String(254), nullable=True, comment="邮箱，可为空"),
        sa.Column("password_hash", sa.String(255), nullable=False, comment="Argon2 密码哈希"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment="账号是否启用",
        ),
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否为超级管理员",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        comment="用户账号与身份状态",
    ),
    sa.Table(
        "files",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), nullable=False, comment="数据库生成的整数主键"),
        sa.Column("backend", sa.String(32), nullable=False, comment="存储后端标识"),
        sa.Column("key", sa.String(255), nullable=False, comment="后端内唯一对象键"),
        sa.Column("original_name", sa.String(255), nullable=False, comment="原始文件名，仅供展示"),
        sa.Column("content_type", sa.String(127), nullable=False, comment="文件 MIME 类型"),
        sa.Column("size", sa.BigInteger(), nullable=False, comment="文件大小（字节）"),
        sa.Column("visibility", sa.String(7), nullable=False, comment="可见性：private 或 public"),
        sa.Column(
            "created_by", sa.BigInteger(), nullable=True, comment="上传用户 ID，用户删除后置空"
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        comment="文件元数据与存储位置",
    ),
)


def _comments(*, remove: bool) -> None:
    """只变更支持注释的数据库；MySQL 显式保留类型、空值、默认值和自增属性"""
    if op.get_context().dialect.name == "sqlite":
        # SQLite 不持久化表/字段注释，不为注释重建表或搬迁业务数据。
        return
    for table in _TABLES:
        if remove:
            op.drop_table_comment(table.name, existing_comment=table.comment)
        else:
            op.create_table_comment(table.name, table.comment, existing_comment=None)
        for column in table.columns:
            op.alter_column(
                table.name,
                column.name,
                comment=None if remove else column.comment,
                existing_comment=column.comment if remove else None,
                existing_type=column.type,
                existing_nullable=column.nullable,
                existing_server_default=column.server_default,
                existing_autoincrement=(
                    column.name == "id" if op.get_context().dialect.name == "mysql" else None
                ),
            )


def upgrade() -> None:
    """为已有数据库添加注释，不修改业务数据"""
    _comments(remove=False)


def downgrade() -> None:
    """移除本版本注释，保留全部字段和记录"""
    _comments(remove=True)
