"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import app.database.mixins
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """升级数据库结构；提交前人工审查自动生成的操作。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回退本版本的数据库结构。"""
    ${downgrades if downgrades else "pass"}
