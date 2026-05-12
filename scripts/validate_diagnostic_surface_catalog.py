#!/usr/bin/env python3
"""Validate the abyss-stack diagnostic capsule surface catalog."""

from __future__ import annotations

import json

from diagnostic_surface_catalog_common import (
    DIAGNOSTIC_SURFACE_CATALOG_PATH,
    SURFACE_PAYLOAD,
    SURFACE_SPECS,
    VALIDATION_REFS,
    build_payload,
    resolve_ref,
)


def main() -> int:
    expected_payload = build_payload()
    current_payload = json.loads(DIAGNOSTIC_SURFACE_CATALOG_PATH.read_text(encoding="utf-8"))
    if current_payload != expected_payload:
        raise SystemExit("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json does not match the canonical rebuild")

    for key, expected in SURFACE_PAYLOAD.items():
        if current_payload.get(key) != expected:
            raise SystemExit(
                f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must keep {key}={expected!r}"
            )
        if key == "authority_ref":
            resolve_ref(expected)

    surfaces = current_payload.get("surfaces")
    if not isinstance(surfaces, list) or len(surfaces) != len(SURFACE_SPECS):
        raise SystemExit("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json must publish exactly five diagnostic surfaces")
    for surface, spec in zip(surfaces, SURFACE_SPECS, strict=True):
        if not isinstance(surface, dict):
            raise SystemExit("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json surfaces must be objects")
        for key in ("name", "schema_ref", "example_ref", "primary_question"):
            if surface.get(key) != spec[key]:
                raise SystemExit(
                    f"mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json surface '{spec['name']}' must keep {key}"
                )
        resolve_ref(surface["schema_ref"])
        resolve_ref(surface["example_ref"])

    validation_refs = current_payload.get("validation_refs")
    if validation_refs != VALIDATION_REFS:
        raise SystemExit("mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json validation_refs drifted")
    for ref in VALIDATION_REFS:
        resolve_ref(ref)

    print("[ok] validated mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
