"""在临时项目执行真实命令、迁移及用户 Service，不接触开发数据。"""

import asyncio
import shutil
import sqlite3
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from kombu import Connection
from redis.asyncio import Redis
from sqlalchemy import event
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from app.cli.main import app
from app.core.config import get_settings
from app.core.security.password import verify_password
from app.database.engine import create_engine
from app.database.session import create_session_factory, session_scope
from app.modules.user.errors import USER_ALREADY_EXISTS
from app.modules.user.model import User
from app.modules.user.repository import UserRepository
from app.modules.user.schema import UserCreate
from app.modules.user.service import UserService
from tests.storage_fakes import CloudClient

runner = CliRunner()
PASSWORD = "cli-test-password"


@pytest.fixture
def cli_project(repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repository_root / "alembic", tmp_path / "alembic")
    shutil.copyfile(repository_root / "alembic.ini", tmp_path / "alembic.ini")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("STORAGE_LOCAL_ROOT", str(tmp_path / "storage"))
    return tmp_path


def test_version_and_help_ignore_invalid_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "invalid-secret-url")
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output
    assert f"fastapi-plus {version('fastapi-plus')}" in result.output
    assert "Python " in result.output
    assert "typer " in result.output
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["db", "--help"]).exit_code == 0


def test_installed_console_entry_point() -> None:
    executable = Path(sys.executable).parent / (
        "fastplus.exe" if sys.platform == "win32" else "fastplus"
    )
    result = subprocess.run(
        [str(executable), "version"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert f"fastapi-plus {version('fastapi-plus')}" in result.stdout


def test_db_roundtrip_and_autogenerate(cli_project: Path) -> None:
    for args in (["db", "upgrade"], ["db", "current"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    assert "0002_create_files" in result.output
    result = runner.invoke(app, ["db", "revision", "-m", "cli migration", "--autogenerate"])
    assert result.exit_code == 0, result.output
    assert len(list((cli_project / "alembic" / "versions").glob("*cli_migration.py"))) == 1
    assert runner.invoke(app, ["db", "upgrade", "head"]).exit_code == 0
    assert runner.invoke(app, ["db", "downgrade", "--", "-1"]).exit_code == 0
    assert "0002_create_files" in runner.invoke(app, ["db", "current"]).output
    assert runner.invoke(app, ["db", "downgrade", "base"]).exit_code == 0
    with sqlite3.connect(cli_project / "cli.db") as connection:
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == []
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("alembic_version",)]
    assert runner.invoke(app, ["db", "upgrade", "0001_create_users"]).exit_code == 0
    assert "0001_create_users" in runner.invoke(app, ["db", "current"]).output


def test_blank_revision_needs_no_database(cli_project: Path) -> None:
    result = runner.invoke(app, ["db", "revision", "--message", "blank"])
    assert result.exit_code == 0, result.output
    assert not (cli_project / "cli.db").exists()
    assert len(list((cli_project / "alembic" / "versions").glob("*blank.py"))) == 1


@pytest.mark.parametrize("args", [["db", "downgrade"], ["db", "revision"], ["unknown"]])
def test_invalid_usage(args: list[str]) -> None:
    assert runner.invoke(app, args).exit_code == 2


def test_missing_project_config() -> None:
    result = runner.invoke(app, ["db", "current"])
    assert result.exit_code == 2
    assert "alembic.ini" in result.output
    assert "Traceback" not in result.output


def test_configuration_error_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "secret-invalid-url")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 2
    assert "配置或输入无效" in result.output
    assert "secret-invalid-url" not in result.output
    assert "Traceback" not in result.output


def test_migration_error_is_safe(cli_project: Path) -> None:
    result = runner.invoke(app, ["db", "upgrade", "unknown-secret-revision"])
    assert result.exit_code == 1
    assert "操作失败" in result.output
    assert "unknown-secret-revision" not in result.output
    assert "Traceback" not in result.output


def test_doctor_missing_resources_is_read_only(cli_project: Path) -> None:
    (cli_project / ".env").write_text("DEBUG=false\n", encoding="utf-8")
    before = {path.relative_to(cli_project) for path in cli_project.rglob("*")}
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1, result.output
    assert "database: FAIL" in result.output
    assert "storage local: FAIL" in result.output
    assert "redis: disabled" in result.output
    assert "celery broker: disabled" in result.output
    assert "storage oss: disabled" in result.output
    assert "storage cos: disabled" in result.output
    assert {path.relative_to(cli_project) for path in cli_project.rglob("*")} == before
    assert (cli_project / ".env").read_text(encoding="utf-8") == "DEBUG=false\n"


def test_doctor_healthy_and_pending_migrations(cli_project: Path) -> None:
    (cli_project / "storage").mkdir()
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    before = (cli_project / "cli.db").read_bytes()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "database: OK" in result.output
    assert "migrations: OK" in result.output
    assert "storage local: OK" in result.output
    assert (cli_project / "cli.db").read_bytes() == before
    assert list((cli_project / "storage").iterdir()) == []
    assert runner.invoke(app, ["db", "downgrade", "base"]).exit_code == 0
    before = (cli_project / "cli.db").read_bytes()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "migrations: FAIL" in result.output
    assert (cli_project / "cli.db").read_bytes() == before


def test_doctor_does_not_create_version_table(cli_project: Path) -> None:
    with sqlite3.connect(cli_project / "cli.db"):
        pass
    before = (cli_project / "cli.db").read_bytes()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "migrations: FAIL" in result.output
    assert (cli_project / "cli.db").read_bytes() == before


def test_create_superuser_reuses_service_and_handles_conflict(
    cli_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    original = UserService.create_superuser
    calls: list[str] = []

    async def record_call(self: UserService, data: UserCreate) -> User:
        # 只记录入口调用；Schema、密码哈希、Repository 和提交均真实执行。
        calls.append(data.username)
        return await original(self, data)

    monkeypatch.setattr(UserService, "create_superuser", record_call)
    inputs = f"operator\noperator@example.com\n{PASSWORD}\n{PASSWORD}\n"
    result = runner.invoke(app, ["create-superuser"], input=inputs)
    assert result.exit_code == 0, result.output
    assert "超级用户创建成功" in result.output
    assert PASSWORD not in result.output
    assert calls == ["operator"]

    async def check_user() -> None:
        engine = create_engine(get_settings())
        try:
            async with session_scope(create_session_factory(engine)) as session:
                users = await UserRepository(session).list()
                assert len(users) == 1
                user = users[0]
                assert (user.username, user.email) == ("operator", "operator@example.com")
                assert user.is_active and user.is_superuser
                assert await verify_password(PASSWORD, user.password_hash)
        finally:
            await engine.dispose()

    asyncio.run(check_user())
    result = runner.invoke(app, ["create-superuser"], input=inputs)
    assert result.exit_code == 1
    assert USER_ALREADY_EXISTS.message in result.output
    assert PASSWORD not in result.output
    assert "Traceback" not in result.output
    asyncio.run(check_user())


@pytest.mark.parametrize(
    "inputs", ["invalid name\n\nabcdefgh\nabcdefgh\n", "operator\n\nshort\nshort\n"]
)
def test_invalid_user_input_creates_no_database(cli_project: Path, inputs: str) -> None:
    result = runner.invoke(app, ["create-superuser"], input=inputs)
    assert result.exit_code == 2
    assert "配置或输入无效" in result.output
    assert "short" not in result.output
    assert not (cli_project / "cli.db").exists()


def test_password_confirmation_and_abort(cli_project: Path) -> None:
    inputs = f"operator\n\n{PASSWORD}\nmismatch-secret\n"
    result = runner.invoke(app, ["create-superuser"], input=inputs)
    assert result.exit_code == 1
    assert "do not match" in result.output
    assert PASSWORD not in result.output
    assert "mismatch-secret" not in result.output
    assert not (cli_project / "cli.db").exists()


def test_superuser_commit_failure_rolls_back(cli_project: Path) -> None:
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0

    def fail_commit(session: Session) -> None:
        raise RuntimeError("internal-secret-detail")

    event.listen(Session, "before_commit", fail_commit)
    try:
        result = runner.invoke(
            app, ["create-superuser"], input=f"operator\n\n{PASSWORD}\n{PASSWORD}\n"
        )
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert result.exit_code == 1
    assert "internal-secret-detail" not in result.output
    assert PASSWORD not in result.output
    with sqlite3.connect(cli_project / "cli.db") as connection:
        assert connection.execute("SELECT * FROM users").fetchall() == []


@pytest.mark.parametrize("failed", [False, True])
def test_doctor_cloud_probes_are_read_only(
    cli_project: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    from app.infrastructure.storage import aliyun_oss, tencent_cos

    client = CloudClient()
    if failed:
        client.error = RuntimeError("cloud-secret-detail")
    monkeypatch.setattr(aliyun_oss, "import_module", client.sdk)
    monkeypatch.setattr(tencent_cos, "import_module", client.sdk)
    for backend in ("OSS", "COS"):
        for field, value in {
            "BUCKET": "test-bucket",
            "REGION": "test-region",
            "ACCESS_KEY_ID": "test-key",
            "ACCESS_KEY_SECRET": "cloud-secret-detail",
        }.items():
            monkeypatch.setenv(f"STORAGE_{backend}__{field}", value)
    (cli_project / "storage").mkdir()
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == (1 if failed else 0), result.output
    for backend in ("oss", "cos"):
        assert f"storage {backend}: {'FAIL' if failed else 'OK'}" in result.output
    assert "cloud-secret-detail" not in result.output
    assert len(client.calls) == 2
    assert client.objects == {}


@pytest.mark.parametrize("failed", [False, True])
def test_doctor_redis_closes_client_and_reports_safe_error(
    cli_project: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    closed: list[Redis] = []
    original_close = Redis.aclose

    async def ping(client: Redis) -> bool:
        if failed:
            raise ConnectionError("redis-secret-detail")
        return True

    async def close(client: Redis, close_connection_pool: bool | None = None) -> None:
        closed.append(client)
        await original_close(client, close_connection_pool)

    monkeypatch.setattr(Redis, "ping", ping)
    monkeypatch.setattr(Redis, "aclose", close)
    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://:redis-secret-detail@localhost/0")
    (cli_project / "storage").mkdir()
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == (1 if failed else 0), result.output
    assert f"redis: {'FAIL' if failed else 'OK'}" in result.output
    assert len(closed) == 1
    assert "redis-secret-detail" not in result.output


@pytest.mark.parametrize("failed", [False, True])
def test_doctor_celery_broker_connection(
    cli_project: Path, monkeypatch: pytest.MonkeyPatch, failed: bool
) -> None:
    if failed:

        def fail_connection(self: Connection, **kwargs: object) -> Connection:
            raise ConnectionError("broker-secret-detail")

        monkeypatch.setattr(Connection, "ensure_connection", fail_connection)
    monkeypatch.setenv("CELERY_ENABLED", "true")
    monkeypatch.setenv("CELERY_BROKER_URL", "memory://")
    (cli_project / "storage").mkdir()
    assert runner.invoke(app, ["db", "upgrade"]).exit_code == 0
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == (1 if failed else 0), result.output
    assert f"celery broker: {'FAIL' if failed else 'OK'}" in result.output
    assert "broker-secret-detail" not in result.output
