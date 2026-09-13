"""只读诊断必须拒绝 Local Adapter 无法使用的可见性目录链接。"""

import os
import subprocess
from pathlib import Path

import pytest

from app.infrastructure.diagnostics import check_local


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_local_diagnostics_rejects_directory_links(tmp_path: Path, visibility: str) -> None:
    root = tmp_path / "storage"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "untouched.txt"
    marker.write_text("unchanged", encoding="utf-8")
    link = root / visibility
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        # Windows 未授权符号链接时使用真实 junction，仍验证相同的目录逃逸。
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            check=True,
            capture_output=True,
        )
    with pytest.raises(RuntimeError):
        check_local(root)
    assert marker.read_text(encoding="utf-8") == "unchanged"
