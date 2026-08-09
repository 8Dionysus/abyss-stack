from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

from abyss_stack_mcp.admission_revision import _process_backed_executable_digest
from abyss_stack_mcp.process_launcher import (
    PROCESS_EXECUTABLE_FD,
    _open_process_executable,
    launch,
)


def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def test_launcher_retains_the_exact_opened_executable_inode(tmp_path: Path) -> None:
    executable = tmp_path / "server.py"
    original = b"#!/usr/bin/env python3\nprint('original')\n"
    executable.write_bytes(original)
    executable.chmod(0o700)

    descriptor = _open_process_executable(executable)
    try:
        replacement = tmp_path / "replacement.py"
        replacement.write_bytes(b"#!/usr/bin/env python3\nprint('replacement')\n")
        replacement.chmod(0o700)
        os.replace(replacement, executable)
        os.lseek(descriptor, 0, os.SEEK_SET)

        assert descriptor == PROCESS_EXECUTABLE_FD
        assert os.read(descriptor, len(original) + 64) == original
    finally:
        os.close(descriptor)


def test_launcher_executes_the_retained_proc_inode(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    executable = tmp_path / "server.py"
    executable.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('launched', encoding='utf-8')\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)

    try:
        launch(executable)
        assert marker.read_text(encoding="utf-8") == "launched"
        assert Path(f"/proc/self/fd/{PROCESS_EXECUTABLE_FD}").is_file()
    finally:
        os.close(PROCESS_EXECUTABLE_FD)


def test_admission_hashes_the_process_retained_inode_not_mutable_path(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "server.py"
    original = b"#!/usr/bin/env python3\nprint('last-good')\n"
    executable.write_bytes(original)
    executable.chmod(0o700)
    descriptor = os.open(executable, os.O_RDONLY)
    process = subprocess.Popen(
        (sys.executable, "-c", "import time; time.sleep(30)"),
        pass_fds=(descriptor,),
    )
    try:
        os.close(descriptor)
        replacement = tmp_path / "replacement.py"
        replacement.write_bytes(b"#!/usr/bin/env python3\nprint('different')\n")
        replacement.chmod(0o700)
        os.replace(replacement, executable)
        identity = f"systemd-user:demo.service:pid:{process.pid}:start:654321"

        observed = _process_backed_executable_digest(
            identity,
            executable,
            "demo.service",
            launch_fd=descriptor,
            systemd_identity_reader=lambda unit_name: identity,
        )

        assert observed == _digest(original)
        assert observed != _digest(executable.read_bytes())
    finally:
        process.terminate()
        process.wait(timeout=5)
