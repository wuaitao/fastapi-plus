"""文件定位依赖 backend + key，URL 不持久化"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin
from app.providers.storage import Visibility


class FileRecord(TimestampMixin, Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("backend", "key", name="uq_files_backend_key"),
        CheckConstraint("visibility IN ('private', 'public')", name="visibility"),
        CheckConstraint("size >= 0", name="size"),
    )

    backend: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    visibility: Mapped[Visibility] = mapped_column(String(7), default="private", nullable=False)
    # 删除用户保留文件；失去所有者的私有文件仅超级管理员可管理。
    created_by: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
