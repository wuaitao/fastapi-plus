"""文件数据访问复用基础 Repository，事务归 Service"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.modules.file.model import FileRecord


class FileRepository(BaseRepository[FileRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, FileRecord)
