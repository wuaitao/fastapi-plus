"""撤销契约及无外部依赖的默认空实现，只接收 jti 和到期时间"""

from typing import Protocol


class TokenStore(Protocol):
    async def is_revoked(self, jti: str) -> bool: ...

    async def revoke(self, jti: str, expires_at: int) -> None: ...


class NullTokenStore:
    """默认无状态实现：退出不撤销令牌，也不提供刷新防重放"""

    async def is_revoked(self, jti: str) -> bool:
        return False

    async def revoke(self, jti: str, expires_at: int) -> None:
        return None
