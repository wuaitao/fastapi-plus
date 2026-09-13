"""最小数据访问方法，不包含提交、权限或 HTTP 语义"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.pagination import PageResult
from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get(self, identifier: int) -> ModelT | None:
        """按主键返回模型，记录不存在时返回空值"""
        return await self.session.get(self.model, identifier)

    async def create(self, instance: ModelT) -> ModelT:
        """写入并刷新模型以获取数据库默认值，不提交事务"""
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelT) -> ModelT:
        """调用方先修改当前 Session 中的对象，模块显式选择允许更新的字段"""
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        """删除并 flush，事务最终由调用方 Service 提交"""
        await self.session.delete(instance)
        await self.session.flush()

    async def list(self, *, offset: int = 0, limit: int = 20) -> list[ModelT]:
        """按主键稳定排序读取受限数量的记录"""
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset 必须非负，limit 必须在 1 到 100 之间")
        # 固定主键排序保证翻页顺序；业务筛选使用模块自身的 SQLAlchemy 查询。
        statement = select(self.model).order_by(self.model.id).offset(offset).limit(limit)
        return list((await self.session.scalars(statement)).all())

    async def paginate(self, *, page: int = 1, size: int = 20) -> PageResult[ModelT]:
        """查询总数和当前页模型，返回与 HTTP 无关的分页结果"""
        if page < 1 or not 1 <= size <= 100:
            raise ValueError("page 必须至少为 1，size 必须在 1 到 100 之间")
        total = await self.session.scalar(select(func.count()).select_from(self.model))
        items = await self.list(offset=(page - 1) * size, limit=size)
        return PageResult(items=items, total=total or 0, page=page, size=size)
