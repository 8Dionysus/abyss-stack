from __future__ import annotations

import ast
from pathlib import Path


LAUNCHER = Path(__file__).resolve().parents[1] / "external_codex_mount_launcher.py"


def test_python311_namespace_setup_uses_libc_syscall_not_os_unshare() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "os.unshare" not in source
    assert source.count("_syscall(libc, SYS_UNSHARE") == 2
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
        and node.func.attr == "unshare"
    ]
    assert calls == []

