"""在模块边界显式装配请求级 Service"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.password import get_password_hasher
from app.database.session import get_session
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    return UserService(UserRepository(session), get_password_hasher())
