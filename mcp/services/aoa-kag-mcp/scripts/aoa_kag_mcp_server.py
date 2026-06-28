#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC = SERVICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_kag_mcp.server import main  # noqa: E402


if __name__ == "__main__":
    main()
