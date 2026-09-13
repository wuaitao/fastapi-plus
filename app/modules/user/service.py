"""用户业务及事务边界，可由 HTTP、CLI 或任务独立调用"""

from argon2 import PasswordHasher
from sqlalchemy.exc import IntegrityError

from app.common.pagination import PageResult
from app.core.exceptions import BusinessException
from app.core.security.password import hash_password
from app.modules.user.errors import (
    USER_ALREADY_EXISTS,
    USER_NOT_FOUND,
    USER_SELF_DELETE,
    is_user_unique_violation,
)
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.modules.user.schema import UserCreate, UserQuery, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository, password_hasher: PasswordHasher) -> None:
        self.repository = repository
        self.password_hasher = password_hasher

    async def _check_unique(
        self, username: str, email: str | None, *, exclude_id: int | None = None
    ) -> None:
        """更新前检查用户名和邮箱冲突，可排除当前用户"""
        by_username = await self.repository.get_by_username(username)
        if by_username is not None and by_username.id != exclude_id:
            raise BusinessException(USER_ALREADY_EXISTS)
        if email is not None:
            by_email = await self.repository.get_by_email(email)
            if by_email is not None and by_email.id != exclude_id:
                raise BusinessException(USER_ALREADY_EXISTS)

    async def create_user(self, data: UserCreate) -> User:
        """创建普通用户并完成事务，不接受输入指定管理员身份"""
        return await self._create_user(data, is_superuser=False)

    async def create_superuser(self, data: UserCreate) -> User:
        """在单次事务中创建已激活的超级管理员"""
        # 权限与激活状态在首次提交前设置，避免分两次事务创建半成品管理员。
        return await self._create_user(
            data.model_copy(update={"is_active": True}), is_superuser=True
        )

    async def _create_user(self, data: UserCreate, *, is_superuser: bool) -> User:
        """计算密码哈希后创建用户，以数据库唯一约束处理并发冲突"""
        # Argon2 是阻塞计算；在线程中完成后再开启数据库事务。
        password_hash = await hash_password(data.password.get_secret_value(), self.password_hasher)
        try:
            # 创建直接依赖唯一约束，避免 SQLite 先读后写时的事务锁升级竞争。
            user = await self.repository.create(
                User(
                    username=data.username,
                    email=data.email,
                    password_hash=password_hash,
                    is_active=data.is_active,
                    is_superuser=is_superuser,
                )
            )
            await self.repository.session.commit()
            return user
        except IntegrityError as error:
            await self.repository.session.rollback()
            # 仅将已知唯一约束转换成业务冲突，保留其他数据库故障。
            if is_user_unique_violation(error):
                raise BusinessException(USER_ALREADY_EXISTS) from None
            raise
        except Exception:
            await self.repository.session.rollback()
            raise

    async def get_user(self, user_id: int) -> User:
        """按 ID 查询用户，不存在时抛用户业务异常"""
        user = await self.repository.get(user_id)
        if user is None:
            raise BusinessException(USER_NOT_FOUND)
        return user

    async def list_users(self, query: UserQuery) -> PageResult[User]:
        """按已验证的分页参数返回用户模型和总数"""
        return await self.repository.paginate(page=query.page, size=query.size)

    async def update_user(self, user_id: int, data: UserUpdate) -> User:
        """仅更新显式允许的字段，处理唯一冲突并提交或回滚事务"""
        try:
            user = await self.get_user(user_id)
            username = data.username if data.username is not None else user.username
            email = data.email if "email" in data.model_fields_set else user.email
            await self._check_unique(username, email, exclude_id=user.id)
            user.username = username
            user.email = email
            if data.is_active is not None:
                user.is_active = data.is_active
            await self.repository.update(user)
            await self.repository.session.commit()
            return user
        except IntegrityError as error:
            await self.repository.session.rollback()
            if is_user_unique_violation(error):
                raise BusinessException(USER_ALREADY_EXISTS) from None
            raise
        except Exception:
            await self.repository.session.rollback()
            raise

    async def delete_user(self, user_id: int, *, actor_id: int) -> None:
        """禁止操作者自删，删除目标用户并完成事务"""
        try:
            # 自删规则属于业务层，CLI/Worker 调用也必须显式传入操作者。
            if user_id == actor_id:
                raise BusinessException(USER_SELF_DELETE)
            user = await self.get_user(user_id)
            await self.repository.delete(user)
            await self.repository.session.commit()
        except Exception:
            await self.repository.session.rollback()
            raise
