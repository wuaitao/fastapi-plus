"""文件请求级装配，以及公开资源的可选身份解析"""

from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security.dependencies import bearer
from app.database.session import get_session
from app.modules.auth.dependencies import resolve_current_user
from app.modules.file.repository import FileRepository
from app.modules.file.service import FileService
from app.modules.user.model import User
from app.providers.storage import StorageRegistry


def get_file_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> FileService:
    settings = cast(Settings, request.app.state.settings)
    return FileService(
        FileRepository(session),
        cast(StorageRegistry, request.app.state.storage_registry),
        settings.file_max_size,
    )


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    request: Request,
) -> User | None:
    # 提交了 Bearer 就必须验证，不能把无效令牌降级为匿名身份。
    if credentials is None:
        return None
    return await resolve_current_user(request, credentials.credentials)


FileServiceDep = Annotated[FileService, Depends(get_file_service)]
OptionalUserDep = Annotated[User | None, Depends(get_optional_user)]
