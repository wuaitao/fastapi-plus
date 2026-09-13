"""适配器共享的安全 key 和阻塞调用边界"""

import asyncio
import re
from collections.abc import Callable
from typing import ParamSpec, TypeVar
from urllib.parse import quote

from app.core.exceptions import InfrastructureException
from app.providers.storage import Visibility

P = ParamSpec("P")
T = TypeVar("T")


def object_key(key: str, visibility: Visibility) -> str:
    # 同时拒绝 POSIX/Windows 跳转、盘符、设备名和 URL 二次解码歧义。
    parts = key.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    if (
        visibility not in ("private", "public")
        or len(key) > 255
        or any(
            not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", part)
            or part.endswith(".")
            or part.split(".")[0].upper() in reserved
            for part in parts
        )
    ):
        raise ValueError("无效的存储 key 或可见性")
    return f"{visibility}/{key}"


def attachment(filename: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(filename, safe='')}"


async def storage_io(call: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        # 等待线程退出后再传播取消，避免调用者关闭仍被 SDK 使用的上传流。
        task = asyncio.create_task(asyncio.to_thread(call, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass
            raise
    except Exception:
        # 不携带厂商消息、签名 URL 或本地路径穿过应用边界。
        raise InfrastructureException() from None
