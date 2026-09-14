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
        {"comment": "文件元数据与存储位置"},
    )

    backend: Mapped[str] = mapped_column(String(32), nullable=False, comment="存储后端标识")
    key: Mapped[str] = mapped_column(String(255), nullable=False, comment="后端内唯一对象键")
    original_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名，仅供展示"
    )
    content_type: Mapped[str] = mapped_column(String(127), nullable=False, comment="文件 MIME 类型")
    size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    visibility: Mapped[Visibility] = mapped_column(
        String(7), default="private", nullable=False, comment="可见性：private 或 public"
    )
    # 删除用户保留文件；失去所有者的私有文件仅超级管理员可管理。
    created_by: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="上传用户 ID，用户删除后置空",
    )
