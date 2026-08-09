"""Launch one managed MCP executable from a process-retained source inode."""

from __future__ import annotations

import argparse
import os
import runpy
import stat
from pathlib import Path


PROCESS_EXECUTABLE_FD = 198


class ProcessLauncherError(ValueError):
    """The managed executable cannot be retained and launched safely."""


def _open_process_executable(path: Path) -> int:
    absolute = path.expanduser().absolute()
    for component in tuple(reversed(absolute.parents)) + (absolute,):
        if (component.exists() or component.is_symlink()) and component.is_symlink():
            raise ProcessLauncherError("managed executable cannot traverse a symlink")
    try:
        descriptor = os.open(
            absolute,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise ProcessLauncherError("managed executable is unavailable") from exc
    retained = False
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not metadata.st_mode & 0o111:
            raise ProcessLauncherError(
                "managed executable must be an executable regular file"
            )
        if descriptor == PROCESS_EXECUTABLE_FD:
            os.set_inheritable(descriptor, False)
            retained = True
        else:
            os.dup2(descriptor, PROCESS_EXECUTABLE_FD, inheritable=False)
    finally:
        if not retained:
            os.close(descriptor)
    return PROCESS_EXECUTABLE_FD


def launch(path: Path) -> None:
    descriptor = _open_process_executable(path)
    runpy.run_path(f"/proc/self/fd/{descriptor}", run_name="__main__")


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-process-launcher")
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args()
    try:
        launch(args.executable)
    except ProcessLauncherError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
