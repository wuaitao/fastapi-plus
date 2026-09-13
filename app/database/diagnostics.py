"""只读数据库连接及 Alembic 版本检查"""

import os
from pathlib import Path
from urllib.parse import unquote

from alembic.runtime.migration import MigrationContext
from pydantic import SecretStr

from app.core.config import Settings
from app.database.engine import create_engine


async def current_heads(settings: Settings) -> tuple[str, ...]:
    """只读查询数据库迁移版本，SQLite 文件缺失时不隐式创建数据库。"""
    if settings.database == "sqlite":
        url = settings.sqlalchemy_url
        database = url.database or ""
        if not database or database == ":memory:" or url.query.get("mode") == "memory":
            raise RuntimeError("内存数据库无法检查持久迁移状态")
        if url.query.get("uri") == "true" and database.startswith("file:"):
            database = unquote(database[5:])
            # Windows file:///C:/ URI 的盘符前导斜线不能作为 UNC 路径解析。
            if os.name == "nt" and database.lstrip("/")[1:2] == ":":
                database = database.lstrip("/")
        path = Path(database).resolve()
        if not path.is_file():
            raise RuntimeError("SQLite 数据库不存在")
        # 使用 SQLite 自身的只读模式，避免检查与连接之间文件消失时重新建库。
        url = url.set(database=path.as_uri(), query={"mode": "ro", "uri": "true"})
        settings = settings.model_copy(
            update={"database_url": SecretStr(url.render_as_string(hide_password=False))}
        )
    engine = create_engine(settings, null_pool=True)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda connection: MigrationContext.configure(connection).get_current_heads()
            )
    finally:
        await engine.dispose()
