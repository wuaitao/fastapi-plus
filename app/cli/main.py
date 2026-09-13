"""显式注册项目命令；帮助和版本查询无需加载运行配置"""

from importlib.metadata import version as package_version
from platform import python_version

import typer

from app.bootstrap.cli import command_errors
from app.cli.db import app as db_app
from app.cli.doctor import doctor
from app.cli.user import create_superuser

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
app.add_typer(db_app, name="db")
app.command()(doctor)
app.command()(create_superuser)


@app.command()
def version() -> None:
    """显示项目、Python 和主要运行时版本"""
    with command_errors():
        typer.echo(f"Python {python_version()}")
        for package in ("fastapi-plus", "fastapi", "sqlalchemy", "alembic", "typer"):
            typer.echo(f"{package} {package_version(package)}")
