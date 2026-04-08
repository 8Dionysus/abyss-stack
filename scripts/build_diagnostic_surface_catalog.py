#!/usr/bin/env python3
"""Build the abyss-stack diagnostic capsule surface catalog."""

from __future__ import annotations

import argparse

from diagnostic_surface_catalog_common import (
    DIAGNOSTIC_SURFACE_CATALOG_PATH,
    build_payload,
    render_payload,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build abyss-stack generated/diagnostic_surface_catalog.min.json."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the generated file matches the canonical rebuild instead of rewriting it.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rendered = render_payload(build_payload())
    DIAGNOSTIC_SURFACE_CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if args.check:
        current = DIAGNOSTIC_SURFACE_CATALOG_PATH.read_text(encoding="utf-8")
        if current != rendered:
            raise SystemExit("generated/diagnostic_surface_catalog.min.json is out of date")
        print("[ok] verified generated/diagnostic_surface_catalog.min.json")
        return 0
    DIAGNOSTIC_SURFACE_CATALOG_PATH.write_text(rendered, encoding="utf-8")
    print("[ok] wrote generated/diagnostic_surface_catalog.min.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
