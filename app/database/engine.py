"""按配置创建异步引擎，显式处理 SQLite 的事务与外键差异"""

from typing import Protocol

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPICursor
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import ConnectionPoolEntry, NullPool

from app.core.config import Settings


def create_engine(settings: Settings, *, null_pool: bool = False) -> AsyncEngine:
    """按配置创建异步引擎，可为短期 CLI 或任务资源禁用连接池"""
    pool_options: dict[str, object] = {}
    if null_pool:
        pool_options["poolclass"] = NullPool
    elif settings.database != "sqlite":
        # SQLite 保留驱动的文件池/内存 StaticPool 选择；NullPool 不接受队列池参数。
        pool_options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
        )
    try:
        engine = create_async_engine(
            settings.sqlalchemy_url,
            echo=False,
            hide_parameters=True,
            pool_pre_ping=True,
            pool_recycle=settings.database_pool_recycle,
            **pool_options,
        )
    except ImportError:
        raise RuntimeError(f"数据库驱动未安装，请安装 {settings.database} 可选依赖") from None
    if settings.database == "sqlite":
        event.listen(engine.sync_engine, "connect", _configure_sqlite)
        event.listen(engine.sync_engine, "begin", _begin_sqlite)
    return engine


class _SQLiteConnection(Protocol):
    """事件接收 SQLAlchemy 适配后的 DBAPI 连接，仅声明这里需要的接口"""

    isolation_level: str | None

    def cursor(self) -> DBAPICursor: ...


def _configure_sqlite(connection: _SQLiteConnection, record: ConnectionPoolEntry) -> None:
    """开启 SQLite 外键约束，并将事务起点交给 SQLAlchemy"""
    # 关闭驱动的旧式事务控制，让 SELECT、DDL、SAVEPOINT 也受真实事务保护。
    connection.isolation_level = None
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _begin_sqlite(connection: Connection) -> None:
    """显式发出 BEGIN，使读取和 DDL 也遵守事务边界"""
    connection.exec_driver_sql("BEGIN")
