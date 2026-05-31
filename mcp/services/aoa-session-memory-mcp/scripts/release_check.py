#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> None:
    subprocess.run(argv, cwd=ROOT.parents[2], check=True)


def main() -> None:
    run([sys.executable, "mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py"])
    run([sys.executable, "-m", "pytest", "mcp/services/aoa-session-memory-mcp/tests", "-q"])


if __name__ == "__main__":
    main()
