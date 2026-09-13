"""唯一示例任务：只读查询用户状态，重复执行无业务副作用"""

from typing import TYPE_CHECKING

from sqlalchemy.exc import DBAPIError, TimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security.password import get_password_hasher
from app.infrastructure.celery.bridge import run_async_handler
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService

if TYPE_CHECKING:
    from celery import Celery


async def user_status_handler(session: AsyncSession, user_id: int) -> dict[str, int | bool]:
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("user_id 必须是正整数")
    service = UserService(UserRepository(session), get_password_hasher())
    user = await service.get_user(user_id)
    return {"user_id": user.id, "is_active": user.is_active}


def register_user_tasks(app: "Celery", settings: Settings) -> None:
    from app.infrastructure.celery.base import BaseTask, TransientTaskError

    @app.task(name="user.status", base=BaseTask, shared=False)
    def user_status(user_id: int) -> dict[str, int | bool]:
        async def handle(session: AsyncSession) -> dict[str, int | bool]:
            return await user_status_handler(session, user_id)

        try:
            return run_async_handler(settings, handle)
        except TimeoutError:
            raise TransientTaskError("任务数据库暂时不可用") from None
        except DBAPIError as exc:
            # 只重试已失效连接；表不存在、约束错误等永久故障保留失败语义。
            if exc.connection_invalidated:
                raise TransientTaskError("任务数据库暂时不可用") from None
            raise
