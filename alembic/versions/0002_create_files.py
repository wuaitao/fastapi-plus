"""创建文件元数据表；不保存访问 URL"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_files"
down_revision: str | None = "0001_create_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True),
        sa.Column("backend", sa.String(32), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(127), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("visibility", sa.String(7), nullable=False),
        sa.Column(
            "created_by", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.UniqueConstraint("backend", "key", name="uq_files_backend_key"),
        sa.CheckConstraint("visibility IN ('private', 'public')", name=op.f("ck_files_visibility")),
        sa.CheckConstraint("size >= 0", name=op.f("ck_files_size")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_files_created_by_users", ondelete="SET NULL"
        ),
    )


def downgrade() -> None:
    op.drop_table("files")
