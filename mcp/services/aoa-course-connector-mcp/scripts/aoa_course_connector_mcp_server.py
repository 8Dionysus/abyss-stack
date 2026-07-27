#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aoa_course_connector_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
