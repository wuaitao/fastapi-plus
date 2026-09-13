"""用户专用查询；基础 CRUD 和分页复用 Repository，不提交事务"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import BaseRepository
from app.modules.user.model import User


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> User | None:
        """按唯一用户名查询用户，不存在时返回空值。"""
        return await self.session.scalar(select(User).where(User.username == username))

    async def get_by_email(self, email: str) -> User | None:
        """按唯一邮箱查询用户，不存在时返回空值。"""
        return await self.session.scalar(select(User).where(User.email == email))
