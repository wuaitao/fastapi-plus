"""独立执行异步迁移，复用配置和数据库方言设置。"""

import asyncio

from sqlalchemy.engine import Connection

from alembic import context
from app.core.config import get_settings
from app.core.logging.config import configure_logging
from app.database.engine import create_engine
from app.database.metadata import target_metadata

settings = get_settings()
configure_logging(settings)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=settings.database == "sqlite",
        user_module_prefix="app.database.mixins.",
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
        user_module_prefix="app.database.mixins.",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(settings, null_pool=True)
    try:
        # 外层事务也覆盖 SQLite 的显式 BEGIN，确保版本号和 DDL 一起持久化。
        async with engine.begin() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
