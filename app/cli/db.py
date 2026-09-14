"""直接映射 Alembic 原生命令，不引入迁移引擎"""

from typing import Annotated

import typer

from alembic import command
from app.bootstrap.cli import command_errors, load_settings, migration_config

app = typer.Typer(no_args_is_help=True)


@app.command()
def revision(
    message: Annotated[str, typer.Option("--message", "-m", help="迁移说明")],
    autogenerate: Annotated[bool, typer.Option(help="根据模型生成差异")] = False,
) -> None:
    """创建迁移文件；仅显式指定时自动生成模型差异"""
    with command_errors():
        if autogenerate:
            load_settings()
        command.revision(migration_config(), message=message, autogenerate=autogenerate)


@app.command()
def upgrade(revision: Annotated[str, typer.Argument(help="目标 revision")] = "head") -> None:
    """升级到指定 revision，默认 head"""
    with command_errors():
        load_settings()
        command.upgrade(migration_config(), revision)


@app.command()
def downgrade(revision: Annotated[str, typer.Argument(help="目标 revision，例如 base 或 -1")]) -> None:
    """显式回退到指定 revision"""
    with command_errors():
        load_settings()
        command.downgrade(migration_config(), revision)


@app.command()
def current() -> None:
    """查看数据库当前迁移版本"""
    with command_errors():
        load_settings()
        command.current(migration_config())
