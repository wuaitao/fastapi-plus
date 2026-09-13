"""CLI 独立装配资源并集中转换错误，不导入 Web 应用"""

import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import typer
from alembic.config import Config
from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.core.logging.config import configure_logging
from app.core.security.password import get_password_hasher
from app.database.engine import create_engine
from app.database.session import create_session_factory, session_scope
from app.modules.user.repository import UserRepository
from app.modules.user.service import UserService


@contextmanager
def command_errors() -> Generator[None]:
    """将应用、输入与运行错误转换为安全提示和 CLI 退出码。"""
    try:
        yield
    except (typer.Exit, typer.Abort):
        raise
    except AppException as error:
        typer.echo(f"错误：{error.descriptor.message}", err=True)
        raise typer.Exit(1) from None
    except (ValidationError, SettingsError):
        # 不输出校验异常正文；其中可能包含密码、连接串或整个配置输入。
        typer.echo("配置或输入无效，请检查环境配置及命令字段约束", err=True)
        raise typer.Exit(2) from None
    except Exception:
        typer.echo("操作失败，请检查配置、依赖、资源权限及迁移状态", err=True)
        raise typer.Exit(1) from None


def load_settings() -> Settings:
    """读取进程配置并初始化 CLI 日志。"""
    settings = get_settings()
    configure_logging(settings)
    return settings


def migration_config() -> Config:
    """从当前项目根目录加载 Alembic 配置。"""
    # Template-first 命令使用当前项目，不能静默迁移安装包所在仓库。
    path = Path("alembic.ini")
    if not path.is_file():
        typer.echo("未找到 alembic.ini，请在项目根目录执行", err=True)
        raise typer.Exit(2)
    return Config(str(path.resolve()), stdout=sys.stdout)


@asynccontextmanager
async def user_service(settings: Settings) -> AsyncGenerator[UserService]:
    """为单次 CLI 操作装配用户服务，退出时关闭 Session 和引擎。"""
    engine = create_engine(settings, null_pool=True)
    try:
        async with session_scope(create_session_factory(engine)) as session:
            yield UserService(UserRepository(session), get_password_hasher())
    finally:
        await engine.dispose()
