"""请求级认证服务、当前用户查询与权限依赖装配"""

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security.dependencies import AccessTokenDep
from app.core.security.password import get_password_hasher
from app.core.security.permissions import check_permission
from app.core.security.token import TokenProvider
from app.database.session import get_session, session_scope
from app.modules.auth.service import AuthService
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.providers.token_store import TokenStore


def get_auth_service(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AuthService:
    """组合请求 Session 与应用级令牌能力，构造认证服务。"""
    return AuthService(
        UserRepository(session),
        get_password_hasher(),
        cast(TokenProvider, request.app.state.token_provider),
        cast(TokenStore, request.app.state.token_store),
        cast(str, request.app.state.dummy_password_hash),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def resolve_current_user(request: Request, token: str) -> User:
    """用独立短 Session 完成认证，返回已加载的用户快照。"""
    # 身份查询在业务执行前关闭读事务，避免 SQLite 并发写入时升级认证读锁。
    # 返回已加载的脱管用户快照；入口只读取身份字段，不借此 Session 修改用户。
    factory = cast(async_sessionmaker[AsyncSession], request.app.state.session_factory)
    async with session_scope(factory) as session:
        return await get_auth_service(request, session).get_current_user(token)


async def get_current_user(token: AccessTokenDep, request: Request) -> User:
    """验证访问令牌并返回当前启用用户。"""
    return await resolve_current_user(request, token)


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str) -> Callable[..., User]:
    """创建指定权限的 FastAPI 依赖，业务策略交给通用权限入口。"""

    def permitted_user(user: CurrentUserDep) -> User:
        """检查已认证用户权限，通过后返回用户快照。"""
        # 模块提供当前用户状态，通用策略不反向导入用户模型。
        check_permission(permission, is_superuser=user.is_superuser)
        return user

    return permitted_user
