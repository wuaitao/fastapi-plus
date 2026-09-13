"""只读诊断逐项报告，失败不阻止其余独立检查"""

import asyncio
from collections.abc import Awaitable, Callable

import typer
from alembic.script import ScriptDirectory

from app.bootstrap.cli import command_errors, load_settings, migration_config
from app.core.config import Settings
from app.database.diagnostics import current_heads
from app.infrastructure.diagnostics import (
    check_celery,
    check_cos,
    check_local,
    check_oss,
    check_redis,
)


async def _diagnose(settings: Settings, heads: set[str]) -> bool:
    """逐项只读检查资源和迁移，汇总结果且不因单项失败提前退出"""
    healthy = True
    try:
        current = set(await current_heads(settings))
        typer.echo("database: OK")
        if current != heads:
            healthy = False
            typer.echo("migrations: FAIL，请检查版本并显式运行 fastplus db upgrade")
        else:
            typer.echo("migrations: OK")
    except Exception:
        healthy = False
        typer.echo("database: FAIL，请检查数据库是否存在、驱动、连接与权限")
        typer.echo("migrations: 未检查（数据库不可用）")

    checks: list[tuple[str, bool, Callable[[], Awaitable[object]], str]] = [
        (
            "storage local",
            True,
            lambda: asyncio.to_thread(check_local, settings.storage_local_root),
            "请显式创建 STORAGE_LOCAL_ROOT 并检查目录权限",
        ),
        (
            "storage oss",
            settings.storage_oss is not None,
            lambda: check_oss(settings),
            "请检查 oss extra、桶配置、凭据和网络",
        ),
        (
            "storage cos",
            settings.storage_cos is not None,
            lambda: check_cos(settings),
            "请检查 cos extra、桶配置、凭据和网络",
        ),
        (
            "redis",
            settings.redis_enabled,
            lambda: check_redis(settings),
            "请检查 redis extra、REDIS_URL 和服务状态",
        ),
        (
            "celery broker",
            settings.celery_enabled,
            lambda: asyncio.to_thread(check_celery, settings),
            "请检查 celery extra、CELERY_BROKER_URL 和服务状态",
        ),
    ]
    for name, enabled, check, hint in checks:
        if not enabled:
            typer.echo(f"{name}: disabled")
            continue
        try:
            await check()
        except Exception:
            healthy = False
            typer.echo(f"{name}: FAIL，{hint}")
        else:
            typer.echo(f"{name}: OK")
    return healthy


def doctor() -> None:
    """只读检查配置、数据库迁移、存储和已启用的连接"""
    with command_errors():
        settings = load_settings()
        typer.echo("configuration: OK")
        heads = set(ScriptDirectory.from_config(migration_config()).get_heads())
        if not asyncio.run(_diagnose(settings, heads)):
            raise typer.Exit(1)
