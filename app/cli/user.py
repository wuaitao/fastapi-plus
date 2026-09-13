"""交互输入经现有 Schema 校验，再交给用户 Service"""

import asyncio

import typer
from pydantic import SecretStr

from app.bootstrap.cli import command_errors, load_settings, user_service
from app.core.config import Settings
from app.modules.user.schema import UserCreate


async def _create(settings: Settings, data: UserCreate) -> int:
    """通过独立用户服务创建管理员并返回数据库生成的 ID。"""
    async with user_service(settings) as service:
        return (await service.create_superuser(data)).id


def create_superuser() -> None:
    """交互创建管理员；密码为 8–128 字符，不回显且需确认"""
    with command_errors():
        settings = load_settings()
        username = typer.prompt("Username")
        email = typer.prompt("Email (optional)", default="", show_default=False)
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        data = UserCreate.model_validate(
            {"username": username, "email": email or None, "password": SecretStr(password)}
        )
        user_id = asyncio.run(_create(settings, data))
        typer.echo(f"超级用户创建成功，ID: {user_id}")
