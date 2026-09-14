"""认证业务复用用户查询与安全能力，不依赖 HTTP 入口"""

from argon2 import PasswordHasher

from app.core.exceptions import AuthenticationException, AuthorizationException
from app.core.security.password import verify_password
from app.core.security.token import TokenClaims, TokenPair, TokenProvider, TokenType
from app.modules.user.errors import USER_DISABLED
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.providers.auth_cache import AuthUserCache, AuthUserSnapshot
from app.providers.token_store import TokenStore


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        password_hasher: PasswordHasher,
        token_provider: TokenProvider,
        token_store: TokenStore,
        dummy_password_hash: str,
        user_cache: AuthUserCache | None = None,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_provider = token_provider
        self.token_store = token_store
        self.dummy_password_hash = dummy_password_hash
        self.user_cache = user_cache

    async def login(self, username: str, password: str) -> TokenPair:
        """验证用户名和密码，通过后签发访问与刷新令牌"""
        user = await self.repository.get_by_username(username)
        valid = await verify_password(
            password,
            user.password_hash if user is not None else self.dummy_password_hash,
            self.password_hasher,
        )
        if not valid or user is None or not user.is_active:
            raise AuthenticationException()
        return self.token_provider.create_pair(str(user.id))

    async def _authenticate(
        self, token: str, token_type: TokenType, *, use_cache: bool = False
    ) -> tuple[User, TokenClaims]:
        """验证令牌用途、撤销状态和用户状态，返回用户与声明"""
        claims = self.token_provider.decode_token(token, token_type)
        if await self.token_store.is_revoked(claims.jti):
            raise AuthenticationException()
        # sub 是字符串，但用户主键必须是数据库可接受的正整数，避免溢出导致 500。
        if not claims.sub.isascii() or not claims.sub.isdecimal() or len(claims.sub) > 19:
            raise AuthenticationException()
        user_id = int(claims.sub)
        if not 0 < user_id <= 9223372036854775807:
            raise AuthenticationException()
        # 每次先验签并检查撤销状态；缓存只替代用户查询，不能替代令牌校验。
        cache = self.user_cache if use_cache else None
        snapshot = await cache.get(user_id) if cache is not None else None
        if snapshot is not None:
            # 保持现有身份依赖的 User 接口；该对象不含密码，也不得用于持久化。
            user = User(**snapshot.model_dump())
        else:
            user = await self.repository.get(user_id)
        if user is None:
            raise AuthenticationException()
        if not user.is_active:
            raise AuthorizationException(USER_DISABLED)
        if cache is not None and snapshot is None:
            await cache.put(AuthUserSnapshot.model_validate(user))
        return user, claims

    async def refresh(self, refresh_token: str) -> TokenPair:
        """重新验证刷新令牌及用户状态，签发新令牌对"""
        user, _ = await self._authenticate(refresh_token, "refresh")
        # 默认不消费旧 refresh token；轮换与防重放需要有状态存储。
        return self.token_provider.create_pair(str(user.id))

    async def logout(self, access_token: str) -> None:
        """验证访问令牌并调用撤销契约，默认空实现不撤销服务器令牌"""
        _, claims = await self._authenticate(access_token, "access")
        await self.token_store.revoke(claims.jti, claims.exp)

    async def get_current_user(self, access_token: str) -> User:
        """验证访问令牌并返回当前启用用户"""
        user, _ = await self._authenticate(access_token, "access", use_cache=True)
        return user
