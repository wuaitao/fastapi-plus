"""独立进程验证公共契约及业务逻辑可以脱离 Web 装配导入。"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("modules", "blocked"),
    [
        (
            ("app.cli.main",),
            (
                "app.main",
                "app.bootstrap.application",
                "app.bootstrap.worker",
                "redis",
                "celery",
                "alibabacloud_oss_v2",
                "qcloud_cos",
            ),
        ),
        (
            (
                "app.providers.storage",
                "app.providers.token_store",
                "app.core.exceptions",
                "app.core.security.token",
                "app.core.security.permissions",
                "app.common.pagination",
            ),
            ("app.modules", "app.infrastructure", "app.bootstrap", "fastapi", "sqlalchemy"),
        ),
        (
            (
                "app.modules.auth.service",
                "app.modules.user.service",
                "app.modules.file.service",
            ),
            ("app.bootstrap", "app.infrastructure", "fastapi"),
        ),
    ],
)
def test_imports_respect_layer_boundaries(
    modules: tuple[str, ...], blocked: tuple[str, ...]
) -> None:
    # 主测试进程已加载配置和框架，用全新解释器才能发现包初始化带来的隐式依赖。
    code = f"""
from importlib import import_module
from importlib.abc import MetaPathFinder
import sys

class BlockDependencies(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in {blocked!r}):
            raise AssertionError('Unexpected dependency: ' + fullname)

sys.meta_path.insert(0, BlockDependencies())
for name in {modules!r}:
    import_module(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_repository_and_router_boundaries(repository_root: Path) -> None:
    modules = repository_root / "app" / "modules"
    repositories = [repository_root / "app" / "database" / "repository.py"]
    repositories.extend(modules.glob("*/repository.py"))
    # 导入测试不能发现方法中的提交和 SQL；检查 AST 以锁定这些明确的层次约束。
    for path in repositories:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"commit", "rollback"}, path
    for path in modules.glob("*/router.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imports: list[str] = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            for name in imports:
                assert not name.startswith(("sqlalchemy", "app.infrastructure")), path
                assert not name.endswith(".repository"), path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {
                    "commit",
                    "rollback",
                    "execute",
                    "scalar",
                    "scalars",
                }, path
