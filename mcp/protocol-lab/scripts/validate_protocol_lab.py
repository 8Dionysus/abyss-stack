#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


LAB_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = LAB_ROOT.parents[1]
BUILDER_PATH = LAB_ROOT / "scripts" / "build_protocol_lab_status.py"
EXPECTED_GATE_IDS = tuple(f"P1-{index:02d}" for index in range(1, 15))


def _load_builder() -> Any:
    spec = importlib.util.spec_from_file_location("protocol_lab_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load protocol lab builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> list[str]:
    errors: list[str] = []
    builder = _load_builder()
    matrix = _load(builder.MATRIX_PATH)
    observation = _load(builder.OBSERVATION_PATH)
    try:
        status = builder.build_status(matrix, observation)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    expected_render = json.dumps(
        status,
        indent=2,
        ensure_ascii=True,
        sort_keys=True,
    ) + "\n"
    if (
        not builder.OUTPUT_PATH.is_file()
        or builder.OUTPUT_PATH.read_text(encoding="utf-8") != expected_render
    ):
        errors.append("generated protocol-lab status is missing or stale")

    gate_ids = tuple(gate["gate_id"] for gate in matrix["migration_gates"])
    if gate_ids != EXPECTED_GATE_IDS:
        errors.append("P1 gates must be exactly ordered P1-01 through P1-14")
    if matrix["next_spec"]["final_published"]:
        errors.append("pre-final matrix cannot claim next spec final publication")
    if matrix["next_spec"]["production_allowed"]:
        errors.append("release candidate cannot be production allowed")
    if status["migration_allowed"] or status["read_only_pilot_allowed"]:
        errors.append("pre-final source posture must block next-protocol migration")
    if status["effectful_migration_allowed"]:
        errors.append("P1 must never migrate effectful organs in the first pilot")
    if not status["stable_registration_retained"]:
        errors.append("dual support must retain the stable registration")
    if status["authority_move_combined"]:
        errors.append("protocol migration cannot combine an authority move")

    pilot = matrix["pilot"]
    if (
        pilot["policy_family"] != "read"
        or pilot["effectful"]
        or pilot["stable_registration"] == pilot["next_lab_registration"]
        or pilot["next_lab_registration_enabled"]
    ):
        errors.append("pilot must be read-only, separate, and disabled pre-final")

    next_sdks = [
        sdk
        for sdk in matrix["sdk_lines"]
        if matrix["next_spec"]["wire_version"] in sdk["protocol_versions"]
    ]
    if not next_sdks or any(
        sdk["release_status"] == "stable" or sdk["production_allowed"]
        for sdk in next_sdks
    ):
        errors.append("all current next-protocol SDK lines must remain prerelease-only")
    python_stable = next(
        sdk for sdk in matrix["sdk_lines"] if sdk["sdk_id"] == "python-stable"
    )
    if (
        python_stable["version"] != "1.28.1"
        or python_stable["stack_pin"] != "1.27.2"
        or python_stable["stack_pin_status"] != "compatible_maintenance_drift"
    ):
        errors.append("Python stable and exact stack-pin drift are not recorded")

    service_pyprojects = sorted(
        (REPO_ROOT / "mcp" / "services").glob("*/pyproject.toml")
    )
    mcp_constraints: list[str] = []
    for path in service_pyprojects:
        text = path.read_text(encoding="utf-8")
        match = re.search(r'"mcp>=([^"]+)"', text)
        if match is not None:
            mcp_constraints.append(match.group(1))
    if not mcp_constraints or any(value != "1.27.2,<2" for value in mcp_constraints):
        errors.append("all stack MCP service constraints must retain mcp>=1.27.2,<2")
    lock = (
        REPO_ROOT
        / "mcp"
        / "services"
        / "abyss-stack-mcp"
        / "requirements.lock"
    ).read_text(encoding="utf-8")
    if "mcp==1.27.2 \\" not in lock:
        errors.append("abyss-stack-mcp lock must retain exact mcp 1.27.2")

    consumer = matrix["consumer_pairs"][0]
    if (
        consumer["next_wire_pair_observed"]
        or consumer["server_discover_observed"]
        or consumer["tasks_wire_pair_observed"]
        or consumer["capability_posture"] != "unknown"
    ):
        errors.append("Codex next-era capability must remain unknown before pair proof")
    if not consumer["next_protocol_literal_present"]:
        errors.append("matrix must retain the observed Codex next-version literal")

    if observation["verdict"] != "blocked" or not observation["reason_codes"]:
        errors.append("current pre-final pair observation must be explicitly blocked")
    if observation["receipt_refs"] == []:
        errors.append("current observation must cite local version evidence")
    for check_name in (
        "official_conformance",
        "abyss_pair_conformance",
        "read_only_canary",
        "dual_support",
        "rollback",
    ):
        if observation[check_name]["status"] == "passed":
            errors.append(f"{check_name} cannot pass without runtime receipts")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("MCP protocol lab validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("MCP protocol lab validation passed: pre-final migration is blocked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
