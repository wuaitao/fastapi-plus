"""测试专属模型，独立 metadata 避免污染应用的迁移目标。"""

from sqlalchemy import ForeignKey, MetaData, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.mixins import TimestampMixin


class Record(TimestampMixin, Base):
    __tablename__ = "test_records"
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)


class Child(Base):
    __tablename__ = "test_children"
    metadata = Record.metadata

    record_id: Mapped[int] = mapped_column(ForeignKey("test_records.id"), nullable=False)
