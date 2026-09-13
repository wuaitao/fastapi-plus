"""复用 Argon2id，在工作线程计算，避免阻塞异步入口"""

import asyncio
from functools import lru_cache
from secrets import token_urlsafe

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasher:
    return PasswordHasher(type=Type.ID)


@lru_cache(maxsize=1)
def get_dummy_password_hash() -> str:
    # 不存在的账号也执行同等哈希验证，减少通过耗时枚举账号的差异。
    return get_password_hasher().hash(token_urlsafe(32))


async def hash_password(password: str, hasher: PasswordHasher | None = None) -> str:
    return await asyncio.to_thread((hasher or get_password_hasher()).hash, password)


async def verify_password(
    password: str, password_hash: str, hasher: PasswordHasher | None = None
) -> bool:
    try:
        return await asyncio.to_thread(
            (hasher or get_password_hasher()).verify, password_hash, password
        )
    except (VerificationError, InvalidHashError):
        return False
