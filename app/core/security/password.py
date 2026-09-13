"""复用 Argon2id，在工作线程计算，避免阻塞异步入口"""

import asyncio
from functools import lru_cache
from secrets import token_urlsafe

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError


@lru_cache(maxsize=1)
def get_password_hasher() -> PasswordHasher:
    """按进程复用 Argon2id 密码哈希器"""
    return PasswordHasher(type=Type.ID)


@lru_cache(maxsize=1)
def get_dummy_password_hash() -> str:
    """生成供未知账号验证使用的随机哈希，减少账号枚举的耗时差异"""
    # 不存在的账号也执行同等哈希验证，减少通过耗时枚举账号的差异。
    return get_password_hasher().hash(token_urlsafe(32))


async def hash_password(password: str, hasher: PasswordHasher | None = None) -> str:
    """在线程中计算密码哈希，避免阻塞异步请求"""
    return await asyncio.to_thread((hasher or get_password_hasher()).hash, password)


async def verify_password(
    password: str, password_hash: str, hasher: PasswordHasher | None = None
) -> bool:
    """在线程中验证密码，不匹配或哈希无效时返回假值"""
    try:
        return await asyncio.to_thread(
            (hasher or get_password_hasher()).verify, password_hash, password
        )
    except (VerificationError, InvalidHashError):
        return False
