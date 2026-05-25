from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aoa_evals_mcp.core import AoAEvalsMCPState  # noqa: E402
from aoa_evals_mcp.server import build_server  # noqa: E402


def main() -> None:
    required = [
        "AGENTS.md",
        "README.md",
        "DESIGN.md",
        "docs/BOUNDARIES.md",
        "docs/THREAT_MODEL.md",
        "src/aoa_evals_mcp/core.py",
        "src/aoa_evals_mcp/server.py",
        "scripts/aoa_evals_mcp_server.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    if missing:
        raise SystemExit(f"missing required files: {missing}")

    state = AoAEvalsMCPState.discover()
    catalog = state.build_catalog()
    if catalog["count"] <= 0:
        raise SystemExit("aoa-evals catalog is empty or unavailable")
    first_name = catalog["evals"][0]["name"]
    inspection = state.inspect_bundle(first_name)
    if inspection["authority_boundary"]["stronger_owner"] != "bundle-local EVAL.md and eval.yaml":
        raise SystemExit("authority boundary drifted")
    if state.report_skeleton(first_name, [])["sections"]["verdict"] != "UNSET: MCP must not compute verdicts":
        raise SystemExit("report skeleton must leave verdict unset")
    server = build_server()
    if server is None:
        raise SystemExit("MCP server did not build")

    print(
        json.dumps(
            {
                "ok": True,
                "schema": catalog["schema"],
                "evals_root": catalog["evals_root"],
                "catalog_count": catalog["count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
