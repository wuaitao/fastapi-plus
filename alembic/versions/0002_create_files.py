"""创建文件元数据表；不保存访问 URL"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_files"
down_revision: str | None = "0001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建文件元数据及所有者外键，默认私有，删除用户时保留文件"""
    op.create_table(
        "files",
        sa.Column(
            "id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, comment="主键"
        ),
        sa.Column("backend", sa.String(32), nullable=False, comment="存储后端标识"),
        sa.Column("key", sa.String(255), nullable=False, comment="唯一对象键"),
        sa.Column("original_name", sa.String(255), nullable=False, comment="原始文件名，仅供展示"),
        sa.Column("content_type", sa.String(127), nullable=False, comment="文件 MIME 类型"),
        sa.Column("size", sa.BigInteger(), nullable=False, comment="文件大小（字节）"),
        sa.Column("visibility", sa.String(7), nullable=False, comment="可见性：private 或 public"),
        sa.Column(
            "created_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True, comment="上传用户 ID，用户删除后置空",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False, comment="创建时间（UTC）"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, comment="更新时间（UTC）"),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.UniqueConstraint("backend", "key", name="uq_files_backend_key"),
        sa.CheckConstraint("visibility IN ('private', 'public')", name=op.f("ck_files_visibility")),
        sa.CheckConstraint("size >= 0", name=op.f("ck_files_size")),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_files_created_by_users", ondelete="SET NULL"),
        comment="文件元数据与存储位置",
    )


def downgrade() -> None:
    op.drop_table("files")
