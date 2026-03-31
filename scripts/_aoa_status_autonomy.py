#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/abyss-stack"))
CONFIGS_ROOT = Path(os.environ.get("AOA_CONFIGS_ROOT", str(STACK_ROOT / "Configs")))
HOME_SOURCE_ROOT = Path.home() / "src" / "abyss-stack"
ROUTE_API_BASE_URL = os.environ.get("AOA_ROUTE_API_BASE_URL", "http://127.0.0.1:5402")
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_ROOT = SCRIPT_PATH.parents[1]

W5_INDEX_PATH = (
    STACK_ROOT
    / "Logs"
    / "local-ai-trials"
    / "w5-langgraph-llamacpp-v1"
    / "W5-long-horizon-index.json"
)
W6_INDEX_PATH = (
    STACK_ROOT
    / "Logs"
    / "local-ai-trials"
    / "w6-bounded-autonomy-llamacpp-v1"
    / "W6-autonomy-index.json"
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


def is_source_checkout(path: Path) -> bool:
    return (
        (path / "CONTRIBUTING.md").exists()
        and (path / "scripts" / "validate_stack.py").exists()
        and (path / "docs" / "DEPLOYMENT.md").exists()
    )


def resolve_source_root() -> Path | None:
    candidates: list[Path] = []
    env_root = os.environ.get("AOA_SOURCE_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    if is_source_checkout(SCRIPT_ROOT):
        candidates.append(SCRIPT_ROOT)
    candidates.append(HOME_SOURCE_ROOT)

    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if is_source_checkout(resolved):
            return resolved
    return None


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


def load_json_text(text: str) -> dict[str, Any]:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


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


def run_parity_check(source_root: Path | None) -> dict[str, Any]:
    if source_root is None:
        return make_check(
            status="fail",
            summary="source root unresolved for parity check",
            detail={"reason": "source_root_unresolved"},
        )

    result = run_command(
        [sys.executable, str(source_root / "scripts" / "validate_stack.py"), "--parity-check"],
        cwd=source_root,
        timeout_s=120.0,
    )
    detail = {
        "source_root": str(source_root),
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


def fetch_route_api_health() -> dict[str, Any]:
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


def fetch_route_api_surface_status() -> dict[str, Any]:
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
    return make_check(
        status="degraded",
        summary=f"{layer} federation mirror check failed",
        detail=detail,
    )


def run_federation_layer_checks() -> dict[str, Any]:
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


def load_wave_index(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return load_json_text(path.read_text(encoding="utf-8"))


def summarize_wave(name: str, index_path: Path) -> dict[str, Any]:
    payload = load_wave_index(index_path)
    if payload is None:
        return make_check(
            status="degraded",
            summary=f"{name} wave index is missing",
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
        summary=f"{name} is not yet a live-available promoted wave",
        detail=detail,
    )


def control_truth_status(
    *,
    source_root: Path | None,
    parity_check: dict[str, Any],
    llamacpp_verify: dict[str, Any],
    route_api_health: dict[str, Any],
    route_api_surface_status: dict[str, Any],
    federation_layers: dict[str, Any],
    w5: dict[str, Any],
    w6: dict[str, Any],
) -> dict[str, Any]:
    source_authored = source_root is not None
    deployed = (
        (CONFIGS_ROOT / "scripts" / "aoa-status").exists()
        and (CONFIGS_ROOT / "scripts" / "aoa-llamacpp-pilot").exists()
        and (CONFIGS_ROOT / "scripts" / "aoa-sync-federation-surfaces").exists()
    )
    trial_proven = bool(
        w5["detail"]["truth_status"]["trial_proven"]
        and w6["detail"]["truth_status"]["trial_proven"]
    )
    surface_closure = route_api_surface_status.get("detail", {}).get("closure_summary") or {}
    live_available = bool(
        parity_check["status"] == "pass"
        and llamacpp_verify["status"] == "pass"
        and route_api_health["status"] == "pass"
        and route_api_surface_status["status"] == "pass"
        and surface_closure.get("closure_ready") is True
        and federation_layers["status"] == "pass"
        and w5["detail"]["truth_status"]["live_available"]
        and w6["detail"]["truth_status"]["live_available"]
    )
    notes = [
        "control_plane source_authored tracks whether the canonical source checkout is discoverable for parity checks.",
        "control_plane deployed tracks whether the deployed operator scripts are present under /srv/abyss-stack/Configs/scripts.",
        "control_plane trial_proven requires both W5 and W6 to remain trial_proven.",
        "control_plane live_available requires parity, promoted runtime verify, route-api health, route-api closure, federation layer checks, and W5/W6 live availability.",
    ]
    return {
        "control_plane": {
            "source_authored": source_authored,
            "deployed": deployed,
            "trial_proven": trial_proven,
            "live_available": live_available,
            "notes": notes,
        },
        "w5": w5["detail"]["truth_status"],
        "w6": w6["detail"]["truth_status"],
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
        return "Repair the promoted llama.cpp lane first. Rerun `python /srv/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60` before trusting autonomy readiness."
    if "route_api_health_failed" in degradation_reasons or "route_api_surface_status_invalid" in degradation_reasons:
        return "Restore route-api health and closure reporting, then rerun `aoa-status --autonomy --json`."
    return "Inspect the degraded layers and wave truth gaps, then rerun the deployed federation checks and W5/W6 summary refresh."


def collect_autonomy_status(
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    resolved_source_root = source_root or resolve_source_root()
    parity = run_parity_check(resolved_source_root)
    verify = run_llamacpp_verify()
    route_health = fetch_route_api_health()
    route_surface = fetch_route_api_surface_status()
    federation = run_federation_layer_checks()
    w5 = summarize_wave("W5", W5_INDEX_PATH)
    w6 = summarize_wave("W6", W6_INDEX_PATH)

    degradation_reasons: list[str] = []
    if parity["status"] != "pass":
        if parity.get("detail", {}).get("reason") == "source_root_unresolved":
            degradation_reasons.append("source_root_unresolved")
        else:
            degradation_reasons.append("source_runtime_drift")
    if verify["status"] != "pass":
        degradation_reasons.append("llamacpp_verify_failed")
    if route_health["status"] != "pass":
        degradation_reasons.append("route_api_health_failed")
    if route_surface["status"] != "pass":
        degradation_reasons.append("route_api_surface_status_invalid")

    surface_closure = route_surface.get("detail", {}).get("closure_summary") or {}
    for layer in surface_closure.get("degraded_layers", []):
        degradation_reasons.append(f"closure_gap:{layer}")
    for layer in surface_closure.get("failing_layers", []):
        degradation_reasons.append(f"closure_gap:{layer}")
    for layer, check in federation["layers"].items():
        if check["status"] != "pass":
            degradation_reasons.append(f"federation_layer_failed:{layer}")
    if w5["detail"]["truth_status"]["trial_proven"] and not w5["detail"]["truth_status"]["live_available"]:
        degradation_reasons.append("trial_live_gap:W5")
    elif w5["status"] != "pass":
        degradation_reasons.append("wave_status_unavailable:W5")
    if w6["detail"]["truth_status"]["trial_proven"] and not w6["detail"]["truth_status"]["live_available"]:
        degradation_reasons.append("trial_live_gap:W6")
    elif w6["status"] != "pass":
        degradation_reasons.append("wave_status_unavailable:W6")

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
        route_api_health=route_health,
        route_api_surface_status=route_surface,
        federation_layers=federation,
        w5=w5,
        w6=w6,
    )

    return {
        "overall_status": overall_status,
        "truth_status": truth_status,
        "checks": {
            "parity_check": parity,
            "llamacpp_verify": verify,
            "route_api_health": route_health,
            "route_api_surface_status": route_surface,
            "federation_layers": federation,
            "w5": w5,
            "w6": w6,
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
        f"- W5: `{payload['checks']['w5']['status']}`",
        f"- W6: `{payload['checks']['w6']['status']}`",
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
