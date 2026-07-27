#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from aoa_xda_connector_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
