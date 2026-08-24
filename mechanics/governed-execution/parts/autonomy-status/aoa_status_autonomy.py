#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from itertools import islice
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
CONFIGS_ROOT = Path(os.environ.get("AOA_CONFIGS_ROOT", str(STACK_ROOT / "Configs")))
SOURCE_ROOT_ENV = "AOA_SOURCE_ROOT"
SOURCE_README_TITLE = "# abyss-stack"
SOURCE_AGENTS_OWNER_LINE = "Root route card for `abyss-stack`."
SOURCE_AGENTS_SCAN_LINES = 8
# Keep the active owner-shape path visible to the source validator
# (`"docs" / "install" / "DEPLOYMENT.md"`); identity verification remains
# centralized in scripts/abyss_stack_source_identity.py.
SOURCE_DEPLOYMENT_SURFACE = Path("docs") / "install" / "DEPLOYMENT.md"
ROUTE_API_BASE_URL = os.environ.get("AOA_ROUTE_API_BASE_URL", "http://127.0.0.1:5402")
SCRIPT_PATH = Path(__file__).resolve()


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


SCRIPT_ROOT = find_repo_root(SCRIPT_PATH.parent)


def _load_source_identity_module() -> Any:
    helper_path = SCRIPT_ROOT / "scripts" / "abyss_stack_source_identity.py"
    spec = importlib.util.spec_from_file_location("abyss_stack_source_identity_autonomy", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load source identity helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SOURCE_IDENTITY = _load_source_identity_module()

PRESERVED_LONG_HORIZON_PROGRAM_ID = "w5-langgraph-llamacpp-v1"
PRESERVED_LONG_HORIZON_INDEX_NAME = "W5-long-horizon-index.json"
PRESERVED_BOUNDED_AUTONOMY_PROGRAM_ID = "w6-bounded-autonomy-llamacpp-v1"
PRESERVED_BOUNDED_AUTONOMY_INDEX_NAME = "W6-autonomy-index.json"
LONG_HORIZON_INDEX_PATH = (
    STACK_ROOT
    / "Logs"
    / "local-ai-trials"
    / PRESERVED_LONG_HORIZON_PROGRAM_ID
    / PRESERVED_LONG_HORIZON_INDEX_NAME
)
BOUNDED_AUTONOMY_INDEX_PATH = (
    STACK_ROOT
    / "Logs"
    / "local-ai-trials"
    / PRESERVED_BOUNDED_AUTONOMY_PROGRAM_ID
    / PRESERVED_BOUNDED_AUTONOMY_INDEX_NAME
)
FEDERATION_LAYERS = [
    "aoa-agents",
    "aoa-routing",
    "aoa-memo",
    "aoa-evals",
    "aoa-playbooks",
    "aoa-kag",
    "tos-source",
]
SDK_CANONICAL_AUTHORITY = {
    "archive_authorized": False,
    "canonical_producer_switch_authorized": True,
    "compatibility_window_started": True,
    "live_runtime_mutation_authorized": True,
    "predecessor_maintenance_only": True,
    "sdk_canonical": True,
}
PODMAN_INSPECT_MISSING_MARKERS = (
    "no such object",
    "no such container",
    "no container with name or id",
    "does not exist",
)


def is_source_checkout(
    path: Path,
    *,
    expected_identity: dict[str, Any] | None = None,
) -> bool:
    if is_runtime_projection(path) or not SOURCE_IDENTITY.source_shape(path):
        return False
    try:
        SOURCE_IDENTITY.bind_source_root(
            path,
            consumer="autonomy-status",
            expected_identity=expected_identity,
            current_root=SCRIPT_ROOT,
            allow_source_local=expected_identity is None,
        )
    except SOURCE_IDENTITY.SourceIdentityError:
        return False
    return True


def is_runtime_projection(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for runtime_root in (STACK_ROOT, CONFIGS_ROOT):
        try:
            resolved_runtime_root = runtime_root.resolve()
        except OSError:
            continue
        if resolved == resolved_runtime_root or resolved_runtime_root in resolved.parents:
            return True
    return False


def source_root_candidates() -> list[tuple[str, Path]]:
    explicit_root = os.environ.get(SOURCE_ROOT_ENV)
    if explicit_root:
        # An explicit operator binding is authoritative and must not silently
        # fall through to another candidate when it is invalid.
        return [("explicit_override", Path(explicit_root).expanduser())]
    if not is_runtime_projection(SCRIPT_ROOT) and is_source_checkout(SCRIPT_ROOT):
        return [("script_root", SCRIPT_ROOT)]
    return []


def resolve_source_root_binding() -> Any | None:
    for method, candidate in source_root_candidates():
        try:
            expected_identity = (
                SOURCE_IDENTITY.load_environment_identity()
                if method == "explicit_override"
                else None
            )
            return SOURCE_IDENTITY.bind_source_root(
                candidate,
                consumer="autonomy-status",
                expected_identity=expected_identity,
                current_root=SCRIPT_ROOT,
                allow_source_local=method != "explicit_override",
            )
        except SOURCE_IDENTITY.SourceIdentityError:
            continue
    return None


def resolve_source_root() -> Path | None:
    binding = resolve_source_root_binding()
    return binding.root if binding is not None else None


def run_command(
    parts: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            parts,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "command": parts,
            "cwd": str(cwd) if cwd else None,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": parts,
            "cwd": str(cwd) if cwd else None,
            "exit_code": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }


def inspect_result_is_missing(result: dict[str, Any]) -> bool:
    output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    return any(marker in output for marker in PODMAN_INSPECT_MISSING_MARKERS)


def container_state(name: str) -> str:
    result = run_command(
        ["podman", "inspect", "--format", "{{.State.Status}}", name],
        timeout_s=15.0,
    )
    if result["exit_code"] != 0:
        if inspect_result_is_missing(result):
            return "missing"
        return "inspect_error"
    status = str(result["stdout"]).strip()
    if not status:
        return "unknown"
    return status


def container_env_flag(name: str, env_name: str) -> bool:
    if container_state(name) != "running":
        return False
    result = run_command(
        ["podman", "exec", name, "/bin/sh", "-c", f'printf %s "${{{env_name}:-}}"'],
        timeout_s=15.0,
    )
    if result["exit_code"] != 0:
        return False
    return str(result["stdout"]).strip().lower() in {"1", "true", "yes", "on"}


def route_api_requirement() -> dict[str, Any]:
    route_api_state = container_state("route-api")
    federated_consumer_enabled = container_env_flag("langchain-api", "AOA_FEDERATED_RUN_ENABLED")
    required = route_api_state != "missing" or federated_consumer_enabled
    if route_api_state != "missing":
        reason = f"route-api container state is {route_api_state}"
    elif federated_consumer_enabled:
        reason = "langchain-api has AOA_FEDERATED_RUN_ENABLED=true"
    else:
        reason = "federation profile is not active and federated advisory consumption is disabled"
    return {
        "required": required,
        "route_api_container_state": route_api_state,
        "federated_consumer_enabled": federated_consumer_enabled,
        "reason": reason,
    }


def load_json_text(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def is_git_object_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def is_sha256_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def http_get_json(url: str, *, timeout_s: float = 10.0) -> dict[str, Any]:
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        body = response.read().decode("utf-8", errors="strict")
    return load_json_text(body)


def normalize_truth_status(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "source_authored": False,
            "deployed": False,
            "trial_proven": False,
            "live_available": False,
            "notes": ["truth_status unavailable"],
        }
    return {
        "source_authored": bool(payload.get("source_authored")),
        "deployed": bool(payload.get("deployed")),
        "trial_proven": bool(payload.get("trial_proven")),
        "live_available": bool(payload.get("live_available")),
        "notes": [str(item) for item in payload.get("notes") or []],
    }


def bool_word(value: bool) -> str:
    return "true" if value else "false"


def make_check(
    *,
    status: str,
    summary: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"status": status, "summary": summary}
    if detail is not None:
        payload["detail"] = detail
    return payload


def run_parity_check(
    source_root: Path | None,
    *,
    binding: Any | None = None,
) -> dict[str, Any]:
    if source_root is None:
        return make_check(
            status="fail",
            summary="source root unresolved for parity check",
            detail={"reason": "source_root_unresolved"},
        )

    try:
        if binding is None:
            expected_identity = (
                SOURCE_IDENTITY.load_environment_identity()
                if os.environ.get(SOURCE_ROOT_ENV)
                else None
            )
            binding = SOURCE_IDENTITY.bind_source_root(
                source_root,
                consumer="autonomy-status",
                expected_identity=expected_identity,
                current_root=SCRIPT_ROOT,
                allow_source_local=expected_identity is None,
            )
        resolved_source_root = SOURCE_IDENTITY.revalidate_source_binding(binding)
    except SOURCE_IDENTITY.SourceIdentityError as exc:
        return make_check(
            status="fail",
            summary="source root unresolved for parity check",
            detail={"reason": "source_root_unresolved", "identity_error": str(exc)},
        )

    result = run_command(
        [
            sys.executable,
            str(resolved_source_root / "scripts" / "validate_stack.py"),
            "--parity-check",
        ],
        cwd=resolved_source_root,
        timeout_s=120.0,
    )
    detail = {
        "source_root": str(resolved_source_root),
        "deployed_configs_root": str(CONFIGS_ROOT),
        "exit_code": result["exit_code"],
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
    }
    if result["exit_code"] == 0:
        return make_check(status="pass", summary="source/deployed parity is green", detail=detail)
    return make_check(status="fail", summary="source/deployed parity failed", detail=detail)


def run_llamacpp_verify() -> dict[str, Any]:
    result = run_command(
        [
            sys.executable,
            str(CONFIGS_ROOT / "scripts" / "aoa-llamacpp-pilot"),
            "verify",
            "--timeout",
            "60",
        ],
        cwd=CONFIGS_ROOT,
        timeout_s=180.0,
    )
    detail: dict[str, Any] = {
        "exit_code": result["exit_code"],
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
    }
    if result["exit_code"] == 0:
        try:
            payload = load_json_text(result["stdout"])
        except (json.JSONDecodeError, ValueError):
            payload = {"ok": False}
        detail["payload"] = payload
        if payload.get("ok") is True:
            return make_check(
                status="pass",
                summary="llama.cpp promoted runtime verify passed",
                detail=detail,
            )
    return make_check(
        status="fail",
        summary="llama.cpp promoted runtime verify failed",
        detail=detail,
    )


def fetch_route_api_health(requirement: dict[str, Any]) -> dict[str, Any]:
    if not requirement["required"]:
        return make_check(
            status="not_enabled",
            summary="route-api health is not required in the current runtime shape",
            detail=requirement,
        )
    url = f"{ROUTE_API_BASE_URL.rstrip('/')}/health"
    try:
        payload = http_get_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return make_check(
            status="fail",
            summary="route-api health request failed",
            detail={"url": url, "error": str(exc)},
        )

    closure_summary = payload.get("closure_summary")
    detail = {
        "url": url,
        "ok": payload.get("ok"),
        "mirror_ready": payload.get("mirror_ready"),
        "closure_summary": closure_summary,
    }
    if payload.get("ok") is True and payload.get("mirror_ready") is True:
        return make_check(status="pass", summary="route-api health is green", detail=detail)
    return make_check(status="fail", summary="route-api health is not green", detail=detail)


def valid_closure_summary(payload: Any) -> bool:
    return isinstance(payload, dict) and all(
        key in payload
        for key in (
            "closure_ready",
            "ready_layer_count",
            "layer_count",
            "ready_layers",
            "degraded_layers",
            "failing_layers",
        )
    )


def fetch_route_api_surface_status(requirement: dict[str, Any]) -> dict[str, Any]:
    if not requirement["required"]:
        return make_check(
            status="not_enabled",
            summary="route-api closure reporting is not required in the current runtime shape",
            detail=requirement,
        )
    url = f"{ROUTE_API_BASE_URL.rstrip('/')}/surface-status"
    try:
        payload = http_get_json(url)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        return make_check(
            status="fail",
            summary="route-api surface-status request failed",
            detail={"url": url, "error": str(exc)},
        )

    closure_summary = payload.get("closure_summary")
    detail = {
        "url": url,
        "ok": payload.get("ok"),
        "closure_summary": closure_summary,
    }
    if payload.get("ok") is True and valid_closure_summary(closure_summary):
        return make_check(
            status="pass",
            summary="route-api surface-status closure summary is valid",
            detail=detail,
        )
    return make_check(
        status="fail",
        summary="route-api surface-status did not return a valid closure summary",
        detail=detail,
    )


def routing_sdk_canonical_layer_check(
    predecessor_sync_check: dict[str, Any],
) -> dict[str, Any]:
    url = f"{ROUTE_API_BASE_URL.rstrip('/')}/surface-status"
    detail: dict[str, Any] = {
        "accepted_via": "route_api_sdk_canonical_closure",
        "predecessor_sync_check": predecessor_sync_check,
        "route_api_url": url,
    }
    try:
        payload = http_get_json(url)
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        detail["reasons"] = ["route_api_surface_status_unavailable"]
        detail["error"] = str(exc)
        return make_check(
            status="degraded",
            summary=(
                "aoa-routing predecessor mirror check failed and "
                "SDK-canonical closure was unavailable"
            ),
            detail=detail,
        )

    switch = payload.get("routing_switch")
    layers_status = payload.get("layers_status")
    routing_status = (
        layers_status.get("aoa-routing")
        if isinstance(layers_status, dict)
        else None
    )
    closure = (
        routing_status.get("closure_status")
        if isinstance(routing_status, dict)
        else None
    )
    metadata = (
        routing_status.get("surface_metadata")
        if isinstance(routing_status, dict)
        else None
    )
    provenance = (
        metadata.get("mirror_provenance")
        if isinstance(metadata, dict)
        else None
    )
    receipt = (
        switch.get("owner_switch_receipt")
        if isinstance(switch, dict)
        else None
    )

    detail["routing_switch"] = switch
    detail["routing_closure"] = closure
    detail["routing_provenance"] = (
        {
            key: provenance.get(key)
            for key in (
                "routing_producer_posture",
                "cutover_activation_mode",
                "operator_change_ref_present",
                "source_git_commit",
                "artifact_subject_digest",
                "canonical_producer",
                "predecessor_rollback",
                "g5_authority",
                "trust_verdict_available",
            )
        }
        if isinstance(provenance, dict)
        else provenance
    )
    reasons: list[str] = []
    if not isinstance(switch, dict):
        reasons.append("routing_switch_missing")
    else:
        expected_switch = {
            "posture": "sdk_canonical",
            "activation_mode": "authorized_live_cutover",
            "canonical_posture": True,
            "canonical_ready": True,
            "closure_ready": True,
            "live_cutover_active": True,
            "compatibility_rollback_active": False,
            "canonical_switch_authorized": True,
        }
        for key, expected in expected_switch.items():
            if switch.get(key) != expected:
                reasons.append(f"routing_switch_{key}_invalid")
        if switch.get("canonical_reasons") != []:
            reasons.append("routing_switch_canonical_reasons_present")
    if not isinstance(receipt, dict):
        reasons.append("routing_owner_switch_receipt_missing")
    else:
        receipt_digest = receipt.get("digest")
        if (
            receipt.get("schema")
            != "aoa_sdk_routing_g5_owner_switch_receipt_v1"
            or receipt.get("status") != "g5_switch_authorized"
            or not is_sha256_digest(receipt_digest)
        ):
            reasons.append("routing_owner_switch_receipt_invalid")
        compatibility = receipt.get("compatibility_window")
        if (
            not isinstance(compatibility, dict)
            or compatibility.get("state") != "started"
            or not isinstance(
                compatibility.get("started_by_sdk_version"),
                str,
            )
            or not isinstance(compatibility.get("started_on"), str)
        ):
            reasons.append(
                "routing_owner_switch_compatibility_window_invalid"
            )
    if not isinstance(closure, dict):
        reasons.append("routing_closure_missing")
    else:
        for key in (
            "mirror_ready",
            "consumer_ready",
            "provenance_ready",
            "closure_ready",
            "canonical_posture",
            "canonical_ready",
        ):
            if closure.get(key) is not True:
                reasons.append(f"routing_closure_{key}_invalid")
        if closure.get("canonical_reasons") != []:
            reasons.append("routing_closure_canonical_reasons_present")
        if closure.get("reasons") != []:
            reasons.append("routing_closure_reasons_present")
    if not isinstance(provenance, dict):
        reasons.append("routing_provenance_missing")
    else:
        if provenance.get("routing_producer_posture") != "sdk_canonical":
            reasons.append("routing_provenance_posture_invalid")
        if (
            provenance.get("cutover_activation_mode")
            != "authorized_live_cutover"
        ):
            reasons.append("routing_provenance_activation_mode_invalid")
        if provenance.get("operator_change_ref_present") is not True:
            reasons.append("routing_provenance_operator_change_ref_missing")
        if provenance.get("trust_verdict_available") is not True:
            reasons.append("routing_provenance_trust_verdict_missing")
        if provenance.get("g5_authority") != SDK_CANONICAL_AUTHORITY:
            reasons.append("routing_provenance_g5_authority_invalid")
        producer = provenance.get("canonical_producer")
        source_ref = provenance.get("source_git_commit")
        if (
            not isinstance(producer, dict)
            or producer.get("owner_repo") != "aoa-sdk"
            or producer.get("source_ref") != source_ref
            or not is_git_object_id(source_ref)
        ):
            reasons.append("routing_provenance_canonical_producer_invalid")
        predecessor = provenance.get("predecessor_rollback")
        if (
            not isinstance(predecessor, dict)
            or predecessor.get("owner_repo") != "aoa-routing"
            or not is_git_object_id(predecessor.get("source_ref"))
        ):
            reasons.append("routing_provenance_predecessor_invalid")
        subject_digest = provenance.get("artifact_subject_digest")
        if not is_sha256_digest(subject_digest):
            reasons.append("routing_provenance_subject_digest_invalid")

    detail["reasons"] = reasons
    if not reasons:
        return make_check(
            status="pass",
            summary=(
                "aoa-routing SDK-canonical live cutover closure passed; "
                "predecessor sync mismatch is compatibility evidence"
            ),
            detail=detail,
        )
    return make_check(
        status="degraded",
        summary=(
            "aoa-routing predecessor mirror check failed and "
            "SDK-canonical live cutover closure did not pass"
        ),
        detail=detail,
    )


def run_federation_layer_check(layer: str) -> dict[str, Any]:
    result = run_command(
        [
            "bash",
            str(CONFIGS_ROOT / "scripts" / "aoa-sync-federation-surfaces"),
            "--check",
            "--json",
            "--layer",
            layer,
        ],
        cwd=CONFIGS_ROOT,
        timeout_s=60.0,
    )
    detail: dict[str, Any] = {
        "exit_code": result["exit_code"],
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
    }
    payload: dict[str, Any] | None = None
    try:
        payload = load_json_text(result["stdout"])
    except (json.JSONDecodeError, ValueError):
        payload = None
    if payload is not None:
        detail["payload"] = payload
    if result["exit_code"] == 0 and payload is not None and payload.get("status") == "ok":
        return make_check(
            status="pass",
            summary=f"{layer} federation mirror check passed",
            detail=detail,
        )
    if layer == "aoa-routing":
        return routing_sdk_canonical_layer_check(detail)
    return make_check(
        status="degraded",
        summary=f"{layer} federation mirror check failed",
        detail=detail,
    )


def run_federation_layer_checks(requirement: dict[str, Any]) -> dict[str, Any]:
    if not requirement["required"]:
        return {
            "status": "not_enabled",
            "summary": "federation seam checks are not required in the current runtime shape",
            "layers": {},
            "detail": requirement,
        }
    layer_checks = {layer: run_federation_layer_check(layer) for layer in FEDERATION_LAYERS}
    failing_layers = sorted(
        layer for layer, check in layer_checks.items() if check["status"] != "pass"
    )
    status = "pass" if not failing_layers else "degraded"
    summary = (
        "all federation mirror checks passed"
        if not failing_layers
        else f"federation mirror checks degraded for: {', '.join(failing_layers)}"
    )
    return {
        "status": status,
        "summary": summary,
        "layers": layer_checks,
    }


def load_trial_index(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json_text(path.read_text(encoding="utf-8"))


def summarize_trial_index(name: str, index_path: Path) -> dict[str, Any]:
    payload = load_trial_index(index_path)
    if payload is None:
        return make_check(
            status="degraded",
            summary=f"{name} trial index is missing",
            detail={"path": str(index_path), "truth_status": normalize_truth_status(None)},
        )

    truth_status = normalize_truth_status(payload.get("truth_status"))
    detail = {
        "path": str(index_path),
        "gate_result": payload.get("gate_result"),
        "truth_status": truth_status,
    }
    if truth_status["trial_proven"] and truth_status["live_available"]:
        return make_check(
            status="pass",
            summary=f"{name} is trial-proven and live-available",
            detail=detail,
        )
    if truth_status["trial_proven"] and not truth_status["live_available"]:
        return make_check(
            status="degraded",
            summary=f"{name} is trial-proven but not live-available",
            detail=detail,
        )
    return make_check(
        status="degraded",
        summary=f"{name} is not yet a live-available promoted trial",
        detail=detail,
    )


def control_truth_status(
    *,
    source_root: Path | None,
    parity_check: dict[str, Any],
    llamacpp_verify: dict[str, Any],
    route_api_requirement: dict[str, Any],
    route_api_health: dict[str, Any],
    route_api_surface_status: dict[str, Any],
    federation_layers: dict[str, Any],
    long_horizon: dict[str, Any],
    bounded_autonomy: dict[str, Any],
) -> dict[str, Any]:
    source_authored = source_root is not None
    deployed = (
        (CONFIGS_ROOT / "scripts" / "aoa-status").exists()
        and (CONFIGS_ROOT / "scripts" / "aoa-llamacpp-pilot").exists()
        and (CONFIGS_ROOT / "scripts" / "aoa-sync-federation-surfaces").exists()
    )
    trial_proven = bool(
        long_horizon["detail"]["truth_status"]["trial_proven"]
        and bounded_autonomy["detail"]["truth_status"]["trial_proven"]
    )
    route_api_required = bool(route_api_requirement["required"])
    surface_closure = route_api_surface_status.get("detail", {}).get("closure_summary") or {}
    route_api_ready = (
        route_api_health["status"] == "pass"
        and route_api_surface_status["status"] == "pass"
        and surface_closure.get("closure_ready") is True
    )
    federation_ready = federation_layers["status"] == "pass"
    live_available = bool(
        parity_check["status"] == "pass"
        and llamacpp_verify["status"] == "pass"
        and (not route_api_required or route_api_ready)
        and (not route_api_required or federation_ready)
        and long_horizon["detail"]["truth_status"]["live_available"]
        and bounded_autonomy["detail"]["truth_status"]["live_available"]
    )
    notes = [
        "control_plane source_authored tracks whether the canonical source checkout is discoverable for parity checks.",
        "control_plane deployed tracks whether the deployed operator scripts are present under /srv/AbyssOS/abyss-stack/Configs/scripts.",
        "control_plane trial_proven requires the preserved autonomy pilot summaries to remain trial_proven.",
        "control_plane live_available requires parity, promoted runtime verify, and preserved pilot live availability.",
    ]
    if route_api_required:
        notes.append(
            "Because the federation seam is active, live_available also requires route-api health, route-api closure, and federation layer checks."
        )
    else:
        notes.append(
            "Because the federation seam is not active in the current runtime shape, route-api and federation checks are reported as not_enabled and do not gate live_available."
        )
    return {
        "control_plane": {
            "source_authored": source_authored,
            "deployed": deployed,
            "trial_proven": trial_proven,
            "live_available": live_available,
            "notes": notes,
        },
        "long_horizon": long_horizon["detail"]["truth_status"],
        "bounded_autonomy": bounded_autonomy["detail"]["truth_status"],
    }


def recommended_action(
    *,
    overall_status: str,
    degradation_reasons: list[str],
) -> str:
    if overall_status == "pass":
        return "Control loop is coherent on the deployed path. Keep using `aoa-status --autonomy --json` as the operator verdict."
    if "source_runtime_drift" in degradation_reasons or "source_root_unresolved" in degradation_reasons:
        return "Resolve the canonical source checkout, then rerun `python scripts/validate_stack.py --parity-check` and resync the deployed Configs mirror."
    if "llamacpp_verify_failed" in degradation_reasons:
        return "Repair the promoted llama.cpp lane first. Rerun `python /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60` before trusting autonomy readiness."
    if "route_api_health_failed" in degradation_reasons or "route_api_surface_status_invalid" in degradation_reasons:
        return "Restore route-api health and closure reporting, then rerun `aoa-status --autonomy --json`."
    return "Inspect the degraded layers and pilot truth gaps, then rerun the deployed federation checks and preserved pilot summary refresh."


def collect_autonomy_status(
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    try:
        source_binding = (
            resolve_source_root_binding()
            if source_root is None
            else SOURCE_IDENTITY.bind_source_root(
                source_root,
                consumer="autonomy-status",
                expected_identity=(
                    SOURCE_IDENTITY.load_environment_identity()
                    if os.environ.get(SOURCE_ROOT_ENV)
                    else None
                ),
                current_root=SCRIPT_ROOT,
                allow_source_local=not bool(os.environ.get(SOURCE_ROOT_ENV)),
            )
        )
    except SOURCE_IDENTITY.SourceIdentityError:
        source_binding = None
    resolved_source_root = source_binding.root if source_binding is not None else None
    parity = run_parity_check(resolved_source_root, binding=source_binding)
    verify = run_llamacpp_verify()
    route_requirement = route_api_requirement()
    route_health = fetch_route_api_health(route_requirement)
    route_surface = fetch_route_api_surface_status(route_requirement)
    federation = run_federation_layer_checks(route_requirement)
    long_horizon = summarize_trial_index("long-horizon pilot", LONG_HORIZON_INDEX_PATH)
    bounded_autonomy = summarize_trial_index(
        "bounded-autonomy pilot",
        BOUNDED_AUTONOMY_INDEX_PATH,
    )

    degradation_reasons: list[str] = []
    if parity["status"] != "pass":
        if parity.get("detail", {}).get("reason") == "source_root_unresolved":
            degradation_reasons.append("source_root_unresolved")
        else:
            degradation_reasons.append("source_runtime_drift")
    if verify["status"] != "pass":
        degradation_reasons.append("llamacpp_verify_failed")
    if route_health["status"] not in {"pass", "not_enabled"}:
        degradation_reasons.append("route_api_health_failed")
    if route_surface["status"] not in {"pass", "not_enabled"}:
        degradation_reasons.append("route_api_surface_status_invalid")

    surface_closure = route_surface.get("detail", {}).get("closure_summary") or {}
    if route_surface["status"] == "pass":
        for layer in surface_closure.get("degraded_layers", []):
            degradation_reasons.append(f"closure_gap:{layer}")
        for layer in surface_closure.get("failing_layers", []):
            degradation_reasons.append(f"closure_gap:{layer}")
    if federation["status"] != "not_enabled":
        for layer, check in federation["layers"].items():
            if check["status"] != "pass":
                degradation_reasons.append(f"federation_layer_failed:{layer}")
    if (
        long_horizon["detail"]["truth_status"]["trial_proven"]
        and not long_horizon["detail"]["truth_status"]["live_available"]
    ):
        degradation_reasons.append("trial_live_gap:long_horizon")
    elif long_horizon["status"] != "pass":
        degradation_reasons.append("trial_status_unavailable:long_horizon")
    if (
        bounded_autonomy["detail"]["truth_status"]["trial_proven"]
        and not bounded_autonomy["detail"]["truth_status"]["live_available"]
    ):
        degradation_reasons.append("trial_live_gap:bounded_autonomy")
    elif bounded_autonomy["status"] != "pass":
        degradation_reasons.append("trial_status_unavailable:bounded_autonomy")

    unique_reasons = sorted(set(degradation_reasons))
    if any(
        reason in unique_reasons
        for reason in (
            "source_root_unresolved",
            "source_runtime_drift",
            "llamacpp_verify_failed",
            "route_api_health_failed",
            "route_api_surface_status_invalid",
        )
    ):
        overall_status = "fail"
    elif unique_reasons:
        overall_status = "degraded"
    else:
        overall_status = "pass"

    truth_status = control_truth_status(
        source_root=resolved_source_root,
        parity_check=parity,
        llamacpp_verify=verify,
        route_api_requirement=route_requirement,
        route_api_health=route_health,
        route_api_surface_status=route_surface,
        federation_layers=federation,
        long_horizon=long_horizon,
        bounded_autonomy=bounded_autonomy,
    )

    return {
        "overall_status": overall_status,
        "truth_status": truth_status,
        "checks": {
            "parity_check": parity,
            "llamacpp_verify": verify,
            "route_api_requirement": route_requirement,
            "route_api_health": route_health,
            "route_api_surface_status": route_surface,
            "federation_layers": federation,
            "long_horizon": long_horizon,
            "bounded_autonomy": bounded_autonomy,
        },
        "degradation_reasons": unique_reasons,
        "recommended_action": recommended_action(
            overall_status=overall_status,
            degradation_reasons=unique_reasons,
        ),
    }


def render_text(payload: dict[str, Any]) -> str:
    truth = payload["truth_status"]["control_plane"]
    federation = payload["checks"]["federation_layers"]
    lines = [
        "AoA Autonomy Status",
        "",
        f"- Overall status: `{payload['overall_status']}`",
        "- Control-plane truth: "
        + ", ".join(
            [
                f"source_authored={bool_word(truth['source_authored'])}",
                f"deployed={bool_word(truth['deployed'])}",
                f"trial_proven={bool_word(truth['trial_proven'])}",
                f"live_available={bool_word(truth['live_available'])}",
            ]
        ),
        f"- Parity check: `{payload['checks']['parity_check']['status']}`",
        f"- llama.cpp verify: `{payload['checks']['llamacpp_verify']['status']}`",
        f"- route-api health: `{payload['checks']['route_api_health']['status']}`",
        f"- route-api closure: `{payload['checks']['route_api_surface_status']['status']}`",
        f"- Federation layers: `{federation['status']}`",
        f"- Long-horizon pilot: `{payload['checks']['long_horizon']['status']}`",
        f"- Bounded-autonomy pilot: `{payload['checks']['bounded_autonomy']['status']}`",
    ]
    if payload["degradation_reasons"]:
        lines.extend(
            [
                "",
                "Degradation reasons:",
                *[f"- {reason}" for reason in payload["degradation_reasons"]],
            ]
        )
    lines.extend(["", "Recommended action:", payload["recommended_action"]])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect the promoted autonomy control-loop verdict for abyss-stack."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = collect_autonomy_status()
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
    else:
        print(render_text(payload))

    if payload["overall_status"] == "pass":
        return 0
    if payload["overall_status"] == "degraded":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
