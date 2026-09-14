"""认证用户快照缓存契约，不包含密码哈希或令牌"""

from typing import Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AuthUserSnapshot(BaseModel):
    """独立于 ORM 和 HTTP 响应的身份快照，仅保存认证及展示所需字段"""

    model_config = ConfigDict(from_attributes=True, extra="forbid", strict=True)

    id: int = Field(gt=0, le=9223372036854775807)
    auth_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    username: str
    email: str | None
    is_active: bool
    is_superuser: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AuthUserCache(Protocol):
    async def get(self, user_id: int, auth_id: str) -> AuthUserSnapshot | None:
        """读取快照；不存在、损坏或缓存不可用时返回空值以回源数据库"""
        ...

    async def put(self, user: AuthUserSnapshot) -> None:
        """尽力写入带固定有效期的快照，不影响数据库认证结果"""
        ...
