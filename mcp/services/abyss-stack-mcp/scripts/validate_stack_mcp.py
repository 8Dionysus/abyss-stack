#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from abyss_stack_mcp.contracts import RuntimeObservation  # noqa: E402


def main() -> int:
    generator = SERVICE_ROOT / "scripts" / "generate_stack_mcp_contracts.py"
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=SERVICE_ROOT,
        check=False,
    )
    if result.returncode:
        return result.returncode

    example = SERVICE_ROOT / "examples" / "runtime-observation.public.example.json"
    RuntimeObservation.model_validate(json.loads(example.read_text(encoding="utf-8")))

    required = {
        "README.md": (
            "not a gateway",
            "read process",
            "candidate process",
            "execution_authorized=false",
        ),
        "DESIGN.md": (
            "source",
            "package",
            "deploy",
            "process",
            "endpoint",
            "consumer",
        ),
        "docs/BOUNDARIES.md": (
            "does not own",
            "aoa-evals",
            "owner acceptance",
        ),
        "docs/THREAT_MODEL.md": (
            "confused deputy",
            "separate credential",
            "symlink",
        ),
    }
    for relative, needles in required.items():
        text = (SERVICE_ROOT / relative).read_text(encoding="utf-8").lower()
        for needle in needles:
            if needle.lower() not in text:
                raise SystemExit(f"{relative} is missing required boundary: {needle}")

    print("[ok] abyss-stack MCP source contracts and public example")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
