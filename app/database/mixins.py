"""跨数据库保持一致的 UTC 时间字段"""

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    # SQLite/MySQL 不保留时区；统一存无时区 UTC，读取时恢复 UTC 标识。
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """将带时区时间转换为无时区 UTC 后入库，拒绝含糊的本地时间"""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """为读取的数据库时间恢复 UTC 时区标识"""
        return value.replace(tzinfo=UTC) if value is not None else None


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间，供模型默认值和更新使用"""
    return datetime.now(UTC)


class TimestampMixin:
    # 时间由 SQLAlchemy 写入；原始 SQL 写入者也必须显式维护这两个字段。
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False
    )
