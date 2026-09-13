"""Alembic 的显式模型导入入口，不扫描目录或导入 Web app"""

from app.database.base import Base
from app.modules.file.model import FileRecord as FileRecord
from app.modules.user.model import User as User

# 显式导入模型以注册 metadata，不依赖 Web app 或目录扫描。
target_metadata = Base.metadata
