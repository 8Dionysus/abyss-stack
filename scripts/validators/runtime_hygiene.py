from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RUNTIME_LIFECYCLE_SURFACE_ROOT = (
    Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts"
)
RUNTIME_LIFECYCLE_SCHEMA_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "schemas"
RUNTIME_LIFECYCLE_EXAMPLE_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "examples"
RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH = (
    RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json"
)
RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH = (
    RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-usage-snapshot.schema.json"
)
RUNTIME_GATEWAY_CACHE_STATUS_EXAMPLE_PATH = (
    RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_gateway_cache_status.gateway-local.example.json"
)
RUNTIME_USAGE_SNAPSHOT_EXAMPLE_PATH = (
    RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_usage_snapshot.workhorse-local.example.json"
)


def read_required_text(errors: list[str], *, root: Path, relative_path: Path) -> str:
    try:
        return (root / relative_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing required file: {relative_path.as_posix()}")
        return ""


def read_required_json(
    errors: list[str],
    *,
    root: Path,
    relative_path: Path,
) -> dict[str, Any] | None:
    try:
        payload = json.loads((root / relative_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing required file: {relative_path.as_posix()}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{relative_path.as_posix()} must contain valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{relative_path.as_posix()} must contain a top-level JSON object")
        return None
    return payload


def require_snippets(
    errors: list[str],
    *,
    text: str,
    path_label: str,
    snippets: tuple[str, ...],
) -> None:
    for snippet in snippets:
        if snippet not in text:
            errors.append(f"{path_label} must mention `{snippet}`")


def validate_runtime_hygiene_contracts(errors: list[str], *, root: Path) -> None:
    cache_doc = read_required_text(
        errors,
        root=root,
        relative_path=RUNTIME_LIFECYCLE_SURFACE_ROOT / "docs" / "GATEWAY_CACHE_POLICY.md",
    )
    require_snippets(
        errors,
        text=cache_doc,
        path_label="mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md",
        snippets=(
            "request deduplication",
            "inflight replay",
            "completed TTL",
            "cache key normalization",
            "no-cache bypass",
            "eviction",
            "hit rate",
            "It does not own truth.",
            "It does not grant routing authority.",
            "It does not lock the stack to one vendor.",
            "This surface documents the contract only. It does not activate live cache behavior.",
            "`runtime_gateway_cache_status_v1`",
        ),
    )

    usage_doc = read_required_text(
        errors,
        root=root,
        relative_path=RUNTIME_LIFECYCLE_SURFACE_ROOT / "docs" / "USAGE_BUDGET_POLICY.md",
    )
    require_snippets(
        errors,
        text=usage_doc,
        path_label="mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md",
        snippets=(
            "per-request",
            "session",
            "hourly",
            "daily",
            "graceful degrade",
            "strict stop",
            "reset window",
            "baseline cost",
            "savings",
            "It must not turn runtime budget posture into proof semantics.",
            "It does not create wallet, payment, or vendor-analysis obligations.",
            "This surface documents status readouts only.",
            "`runtime_usage_snapshot_v1`",
        ),
    )

    doctor_split_doc = read_required_text(
        errors,
        root=root,
        relative_path=Path("mechanics")
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "docs"
        / "LOCAL_OPS_DOCTOR_SPLIT.md",
    )
    require_snippets(
        errors,
        text=doctor_split_doc,
        path_label="mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
        snippets=(
            "`aoa-doctor` remains readiness-only.",
            "gateway reachability",
            "log presence",
            "basic config health",
            "local floor availability",
            "It does not become a usage monitor.",
            "bounded local ops status surface",
            "This contract does not add new `aoa-doctor` exit semantics.",
        ),
    )

    service_catalog_doc = read_required_text(
        errors,
        root=root,
        relative_path=Path("docs") / "runtime" / "SERVICE_CATALOG.md",
    )
    require_snippets(
        errors,
        text=service_catalog_doc,
        path_label="docs/runtime/SERVICE_CATALOG.md",
        snippets=(
            "mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md",
            "mechanics/runtime-lifecycle/parts/status-readouts/docs/USAGE_BUDGET_POLICY.md",
            "mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
            "does not add new HTTP endpoints in this contract surface",
            "bounded runtime artifact",
        ),
    )

    runbook_doc = read_required_text(
        errors,
        root=root,
        relative_path=Path("docs") / "operations" / "RUNBOOK.md",
    )
    require_snippets(
        errors,
        text=runbook_doc,
        path_label="docs/operations/RUNBOOK.md",
        snippets=(
            "runtime_gateway_cache_status",
            "runtime_usage_snapshot",
            "Logs/runtime-gateway/cache-status/latest/",
            "Logs/runtime-usage/latest/",
            "absence is not a failure",
        ),
    )

    doctor_doc = read_required_text(
        errors,
        root=root,
        relative_path=Path("mechanics")
        / "diagnostic-spine"
        / "parts"
        / "doctor-readiness"
        / "docs"
        / "DOCTOR.md",
    )
    require_snippets(
        errors,
        text=doctor_doc,
        path_label="mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md",
        snippets=(
            "mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
            "readiness-only",
            "usage monitor",
        ),
    )

    validate_gateway_cache_schema(errors, root=root)
    validate_usage_snapshot_schema(errors, root=root)
    validate_gateway_cache_example(errors, root=root)
    validate_usage_snapshot_example(errors, root=root)


def validate_gateway_cache_schema(errors: list[str], *, root: Path) -> None:
    cache_schema = read_required_json(
        errors,
        root=root,
        relative_path=RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH,
    )
    if cache_schema and cache_schema.get("title") != "abyss-stack runtime gateway cache status":
        errors.append(
            f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must describe abyss-stack runtime gateway cache status"
        )
    if not cache_schema:
        return
    cache_required = cache_schema.get("required")
    if not isinstance(cache_required, list):
        errors.append(f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must declare a required field list")
    else:
        for field in (
            "cache_key_strategy",
            "normalization_rules",
            "inflight_state",
            "ttl_window",
            "bypass_reason",
            "hit_state",
            "generated_at",
        ):
            if field not in cache_required:
                errors.append(f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must require `{field}`")
    cache_properties = cache_schema.get("properties")
    cache_surface_type = (
        cache_properties.get("surface_type", {})
        if isinstance(cache_properties, dict)
        else {}
    )
    if not isinstance(cache_surface_type, dict) or cache_surface_type.get("const") != "runtime_gateway_cache_status":
        errors.append(
            f"{RUNTIME_GATEWAY_CACHE_STATUS_SCHEMA_PATH.as_posix()} must pin surface_type.const to runtime_gateway_cache_status"
        )


def validate_usage_snapshot_schema(errors: list[str], *, root: Path) -> None:
    usage_schema = read_required_json(
        errors,
        root=root,
        relative_path=RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH,
    )
    if usage_schema and usage_schema.get("title") != "abyss-stack runtime usage snapshot":
        errors.append(
            f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must describe abyss-stack runtime usage snapshot"
        )
    if not usage_schema:
        return
    usage_required = usage_schema.get("required")
    if not isinstance(usage_required, list):
        errors.append(f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must declare a required field list")
    else:
        for field in (
            "request_window",
            "session_window",
            "hourly_window",
            "daily_window",
            "policy_mode",
            "degrade_state",
            "strict_stop",
            "baseline_cost_estimate",
            "savings_estimate",
            "reset_at",
        ):
            if field not in usage_required:
                errors.append(f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must require `{field}`")
    usage_properties = usage_schema.get("properties")
    usage_surface_type = (
        usage_properties.get("surface_type", {})
        if isinstance(usage_properties, dict)
        else {}
    )
    if not isinstance(usage_surface_type, dict) or usage_surface_type.get("const") != "runtime_usage_snapshot":
        errors.append(
            f"{RUNTIME_USAGE_SNAPSHOT_SCHEMA_PATH.as_posix()} must pin surface_type.const to runtime_usage_snapshot"
        )


def validate_gateway_cache_example(errors: list[str], *, root: Path) -> None:
    cache_example = read_required_json(
        errors,
        root=root,
        relative_path=RUNTIME_GATEWAY_CACHE_STATUS_EXAMPLE_PATH,
    )
    if not cache_example:
        return
    if cache_example.get("surface_type") != "runtime_gateway_cache_status":
        errors.append("runtime gateway cache status example must use surface_type runtime_gateway_cache_status")
    if cache_example.get("schema_version") != "v1":
        errors.append("runtime gateway cache status example must use schema_version v1")
    boundary = cache_example.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("supports_runtime_claims_only") is not True:
        errors.append("runtime gateway cache status example must stay runtime-claims-only")
    recent_decisions = cache_example.get("recent_decisions")
    if not isinstance(recent_decisions, list):
        errors.append("runtime gateway cache status example must include recent_decisions")
        return
    decision_kinds = {
        item.get("decision")
        for item in recent_decisions
        if isinstance(item, dict)
    }
    for expected in ("hit", "inflight_replay", "bypass"):
        if expected not in decision_kinds:
            errors.append(f"runtime gateway cache status example must include a `{expected}` decision")
    if not any(
        isinstance(item, dict)
        and item.get("decision") == "bypass"
        and item.get("cache_control") == "no-cache"
        and item.get("bypass_reason") == "no_cache_header"
        for item in recent_decisions
    ):
        errors.append("runtime gateway cache status example must show Cache-Control: no-cache bypass")


def validate_usage_snapshot_example(errors: list[str], *, root: Path) -> None:
    usage_example_text = read_required_text(
        errors,
        root=root,
        relative_path=RUNTIME_USAGE_SNAPSHOT_EXAMPLE_PATH,
    )
    usage_example = read_required_json(
        errors,
        root=root,
        relative_path=RUNTIME_USAGE_SNAPSHOT_EXAMPLE_PATH,
    )
    if not usage_example:
        return
    if usage_example.get("surface_type") != "runtime_usage_snapshot":
        errors.append("runtime usage snapshot example must use surface_type runtime_usage_snapshot")
    if usage_example.get("schema_version") != "v1":
        errors.append("runtime usage snapshot example must use schema_version v1")
    if usage_example.get("policy_mode") not in {
        "observe_only",
        "soft_cap",
        "graceful_degrade",
        "strict_stop",
    }:
        errors.append("runtime usage snapshot example must use a supported policy_mode")
    baseline_estimate = usage_example.get("baseline_cost_estimate")
    if not isinstance(baseline_estimate, dict) or baseline_estimate.get("unit") != "normalized_cost_units":
        errors.append("runtime usage snapshot example must express baseline_cost_estimate in normalized_cost_units")
    savings_estimate = usage_example.get("savings_estimate")
    if not isinstance(savings_estimate, dict) or savings_estimate.get("unit") != "normalized_cost_units":
        errors.append("runtime usage snapshot example must express savings_estimate in normalized_cost_units")
    boundary = usage_example.get("boundary")
    if not isinstance(boundary, dict) or boundary.get("supports_runtime_claims_only") is not True:
        errors.append("runtime usage snapshot example must stay runtime-claims-only")
    lowered_usage_example = usage_example_text.lower()
    for forbidden in ("wallet", "payment", "billing", "invoice"):
        if forbidden in lowered_usage_example:
            errors.append(f"runtime usage snapshot example must stay free of {forbidden} semantics")
