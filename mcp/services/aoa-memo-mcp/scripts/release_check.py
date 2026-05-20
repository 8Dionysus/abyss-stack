from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    print("[ok]", " ".join(cmd))


def main() -> None:
    py = sys.executable
    run([py, "scripts/validate_memo_mcp.py"])
    run([py, "-m", "pytest", "-q"])


if __name__ == "__main__":
    main()
