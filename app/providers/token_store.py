"""撤销契约及无外部依赖的默认空实现，只接收 jti 和到期时间"""

from typing import Protocol


class TokenStore(Protocol):
    async def is_revoked(self, jti: str) -> bool:
        """根据 jti 查询令牌是否已撤销。"""
        ...

    async def revoke(self, jti: str, expires_at: int) -> None:
        """记录 jti 撤销状态至 expires_at，时间为 Unix 秒。"""
        ...


class NullTokenStore:
    """默认无状态实现：退出不撤销令牌，也不提供刷新防重放"""

    async def is_revoked(self, jti: str) -> bool:
        """无状态模式始终视为未撤销。"""
        return False

    async def revoke(self, jti: str, expires_at: int) -> None:
        """无状态模式不保存撤销记录，客户端负责清理令牌。"""
        return None
