#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
CONFIGS_ROOT = Path(os.environ.get("AOA_CONFIGS_ROOT", str(STACK_ROOT / "Configs")))
SOURCE_ROOT_ENV = "AOA_SOURCE_ROOT"
SOURCE_README_TITLE = "# abyss-stack"
SOURCE_AGENTS_OWNER_LINE = "Root route card for `abyss-stack`."
SOURCE_AGENTS_SCAN_LINES = 8
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

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
DRIFT_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
AXIS_RANK = {"fail": 0, "unknown": 1, "skipped": 1, "warn": 2, "pass": 3}
CONTROL_PLANE_FIELDS = ("source_authored", "deployed", "trial_proven", "live_available")
TRUTH_GOAL_TO_FIELD = {
    "deployed": "deployed",
    "trial_proven": "trial_proven",
    "live_available": "live_available",
}
DOCTOR_ADVISORY_WARNINGS = (
    "vault mount /abyss not present",
    "internal-only services selected;",
)


def run_command(
    parts: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            parts,
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return {
            "command": parts,
            "cwd": str(cwd) if cwd else None,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "command": parts,
            "cwd": str(cwd) if cwd else None,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr,
        }


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    value = value.strip("-")
    return value or "unknown"


def relative_ref(path: Path) -> str:
    try:
        return path.relative_to(STACK_ROOT).as_posix()
    except ValueError:
        return str(path)


def command_ref(parts: list[str]) -> str:
    return "command:" + " ".join(parts)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_timestamp(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc_timestamp(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_source_checkout(path: Path) -> bool:
    if not (
        (path / "AGENTS.md").is_file()
        and (path / "README.md").is_file()
        and (path / "CONTRIBUTING.md").is_file()
        and (path / "mechanics").is_dir()
        and (path / "scripts" / "validate_stack.py").is_file()
        and (path / "docs" / "install" / "DEPLOYMENT.md").is_file()
    ):
        return False
    try:
        with (path / "README.md").open(encoding="utf-8") as readme_file:
            readme_title = next(
                (line.strip() for line in readme_file if line.strip()),
                None,
            )
        with (path / "AGENTS.md").open(encoding="utf-8") as agents_file:
            agents_owner_line = any(
                line.rstrip("\r\n") == SOURCE_AGENTS_OWNER_LINE
                for line in islice(agents_file, SOURCE_AGENTS_SCAN_LINES)
            )
    except OSError:
        return False
    return readme_title == SOURCE_README_TITLE and agents_owner_line


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


def resolve_source_root() -> Path | None:
    seen: set[str] = set()
    for _method, candidate in source_root_candidates():
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if not is_runtime_projection(resolved) and is_source_checkout(resolved):
            return resolved
    return None


def resolve_selector_context() -> dict[str, Any]:
    presets = split_csv(os.environ.get("AOA_DIAG_RESOLVED_PRESETS") or os.environ.get("AOA_STACK_PRESET"))
    profiles = split_csv(os.environ.get("AOA_DIAG_RESOLVED_PROFILES") or os.environ.get("AOA_STACK_PROFILE"))
    modules = split_csv(os.environ.get("AOA_DIAG_RESOLVED_MODULES"))
    if not profiles:
        profiles = ["core"]
    return {
        "presets": presets,
        "preset": ",".join(presets) if presets else "profile-only",
        "profiles": profiles,
        "modules": modules,
        "internal_selected": any(
            module in {"51-browser-tools.yml", "60-monitoring.yml"} for module in modules
        ),
    }


def selector_cli_args(selector_context: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if selector_context["presets"]:
        for preset in selector_context["presets"]:
            parts.extend(["--preset", preset])
        return parts
    for profile in selector_context["profiles"]:
        parts.extend(["--profile", profile])
    return parts


def self_command(selector_context: dict[str, Any], *, truth_goal: str) -> str:
    parts = [str(CONFIGS_ROOT / "scripts" / "aoa-diagnose"), *selector_cli_args(selector_context), "--truth-goal", truth_goal]
    return " ".join(parts)


def doctor_warning_is_advisory(warning: str) -> bool:
    lowered = warning.lower()
    return any(token in lowered for token in DOCTOR_ADVISORY_WARNINGS)


def collect_doctor_check() -> dict[str, Any]:
    command = ["bash", str(CONFIGS_ROOT / "scripts" / "aoa-doctor")]
    result = run_command(command, cwd=CONFIGS_ROOT, timeout_s=120.0)
    cleaned_lines = [strip_ansi(line).strip() for line in result["stdout"].splitlines()]
    warnings = [line.removeprefix("warn ").strip() for line in cleaned_lines if line.startswith("warn ")]
    failures = [line.removeprefix("fail ").strip() for line in cleaned_lines if line.startswith("fail ")]
    material_warnings = [warning for warning in warnings if not doctor_warning_is_advisory(warning)]
    advisory_warnings = [warning for warning in warnings if doctor_warning_is_advisory(warning)]
    if result["exit_code"] != 0 or failures:
        status = "fail"
        summary = "aoa-doctor reported readiness failures"
    elif material_warnings:
        status = "warn"
        summary = "aoa-doctor reported bounded readiness warnings"
    else:
        status = "pass"
        summary = "aoa-doctor is green for the selected runtime shape"
    return {
        "status": status,
        "summary": summary,
        "command": command,
        "exit_code": result["exit_code"],
        "warnings": warnings,
        "material_warnings": material_warnings,
        "advisory_warnings": advisory_warnings,
        "failures": failures,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def collect_render_services_check() -> dict[str, Any]:
    command = ["bash", str(CONFIGS_ROOT / "scripts" / "aoa-render-services")]
    result = run_command(command, cwd=CONFIGS_ROOT, timeout_s=120.0)
    services: list[str] = []
    for raw_line in result["stdout"].splitlines():
        line = strip_ansi(raw_line).strip()
        if not line:
            continue
        if line.startswith(">>>>") or line.startswith("<<<<"):
            continue
        if "podman-compose(1)" in line:
            continue
        services.append(line)
    if result["exit_code"] == 0 and services:
        status = "pass"
        summary = "rendered service shape resolved successfully"
    else:
        status = "fail"
        summary = "rendered service shape did not resolve cleanly"
    return {
        "status": status,
        "summary": summary,
        "command": command,
        "exit_code": result["exit_code"],
        "services": services,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def fallback_truth_status() -> dict[str, bool]:
    source_root = resolve_source_root()
    return {
        "source_authored": source_root is not None,
        "deployed": (CONFIGS_ROOT / "scripts" / "aoa-status").exists(),
        "trial_proven": False,
        "live_available": False,
    }


def collect_autonomy_check() -> dict[str, Any]:
    command = ["bash", str(CONFIGS_ROOT / "scripts" / "aoa-status"), "--autonomy", "--json"]
    result = run_command(command, cwd=CONFIGS_ROOT, timeout_s=300.0)
    payload: dict[str, Any] | None = None
    try:
        loaded = json.loads(result["stdout"])
        if isinstance(loaded, dict):
            payload = loaded
    except json.JSONDecodeError:
        payload = None
    if payload is not None:
        status = str(payload.get("overall_status", "fail"))
        truth_status = payload.get("truth_status", {}).get("control_plane") or fallback_truth_status()
        degradation_reasons = [str(item) for item in payload.get("degradation_reasons") or []]
    else:
        status = "fail"
        truth_status = fallback_truth_status()
        degradation_reasons = ["autonomy_payload_unavailable"]
    summary = (
        "autonomy control-plane verdict collected"
        if payload is not None
        else "autonomy control-plane verdict unavailable"
    )
    return {
        "status": status,
        "summary": summary,
        "command": command,
        "exit_code": result["exit_code"],
        "payload": payload,
        "truth_status": truth_status,
        "degradation_reasons": degradation_reasons,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }


def default_drift_watch(args: argparse.Namespace) -> list[str]:
    drifts = [
        "source_deploy_drift",
        "host_posture_drift",
        "adaptation_staleness",
        "render_truth_drift",
        "runtime_health_drift",
        "closure_drift",
        "evidence_gap",
    ]
    if args.truth_goal in {"trial_proven", "live_available"}:
        drifts.append("truth_gap")
    if args.against:
        drifts.append("selector_drift")
    if args.with_session_ref:
        drifts.append("boundary_confusion")
    if args.with_reviewed_diagnosis_ref:
        drifts.append("boundary_confusion")
    return sorted(dict.fromkeys(drifts))


def fallback_candidates(selector_context: dict[str, Any]) -> list[str]:
    presets = selector_context["presets"]
    candidates: list[str] = []
    if "intel-full" in presets:
        candidates.extend(["agent-full", "core"])
    elif "agent-full" in presets:
        candidates.append("core")
    elif selector_context["preset"] == "profile-only" and selector_context["profiles"] != ["core"]:
        candidates.append("core")
    return candidates


def build_target(
    args: argparse.Namespace,
    selector_context: dict[str, Any],
    render_check: dict[str, Any],
) -> dict[str, Any]:
    target: dict[str, Any] = {
        "schema_version": "diagnostic_target_v1",
        "id": f"{slugify(selector_context['preset'])}-{args.truth_goal}",
        "preset": selector_context["preset"],
        "profiles": selector_context["profiles"],
        "truth_goal": args.truth_goal,
        "required_checks": [
            "doctor",
            "render_services",
            "autonomy_status",
            "host_facts_record",
            "machine_fit_record",
        ],
        "drift_watch": default_drift_watch(args),
        "runtime_root": str(STACK_ROOT),
        "notes": "Generated by scripts/aoa-diagnose as a bounded read-only runtime diagnostic target.",
        "public_safe": True,
    }
    if render_check["services"]:
        target["expected_services"] = render_check["services"]
    if selector_context["internal_selected"]:
        target["expected_internal_probes"] = ["with_internal"]
    fallbacks = fallback_candidates(selector_context)
    if fallbacks:
        target["fallback_candidates"] = fallbacks
    if args.against:
        target["required_checks"].append("last_good_reference")
    if args.with_session_ref:
        target["required_checks"].append("reviewed_session_reference")
    if args.with_reviewed_diagnosis_ref:
        target["required_checks"].append("reviewed_diagnosis_reference")
    return target


def load_reference_artifacts(args: argparse.Namespace) -> dict[str, Any]:
    host_facts_path = STACK_ROOT / "Logs" / "host-facts" / "latest.private.json"
    machine_fit_path = STACK_ROOT / "Logs" / "machine-fit" / "latest" / "latest.private.json"
    platform_adaptation_path = STACK_ROOT / "Logs" / "platform-adaptations" / "latest" / "latest.private.json"

    session_refs: list[str] = []
    missing_session_refs: list[str] = []
    for raw_path in args.with_session_ref:
        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            session_refs.append(str(candidate))
        else:
            missing_session_refs.append(str(candidate))

    diagnosis_refs: list[str] = []
    missing_diagnosis_refs: list[str] = []
    diagnosis_ref_payloads: list[dict[str, Any]] = []
    for raw_path in args.with_reviewed_diagnosis_ref:
        candidate = Path(raw_path).expanduser()
        if candidate.exists():
            diagnosis_refs.append(str(candidate))
            payload = read_json(candidate)
            if payload is not None:
                diagnosis_ref_payloads.append(payload)
        else:
            missing_diagnosis_refs.append(str(candidate))

    against_label = None
    against_ref_path: Path | None = None
    against_session: dict[str, Any] | None = None
    against_missing = False
    if args.against:
        if args.against == "last-good":
            against_label = "last-good"
            against_ref_path = STACK_ROOT / "Logs" / "diagnostics" / "latest" / "last_good.ref.json"
        else:
            against_label = args.against
            against_ref_path = Path(args.against).expanduser()
        against_payload = read_json(against_ref_path) if against_ref_path.exists() else None
        if against_payload is None:
            against_missing = True
        elif against_payload.get("schema_version") == "diagnostic_session_v1":
            against_session = against_payload
        else:
            anchor_path_text = (
                against_payload.get("diagnostic_session_path")
                or against_payload.get("session_path")
                or against_payload.get("ref")
            )
            if isinstance(anchor_path_text, str) and anchor_path_text.strip():
                anchor_path = Path(anchor_path_text)
                if not anchor_path.is_absolute():
                    anchor_path = against_ref_path.parent / anchor_path
                against_session = read_json(anchor_path)
                if against_session is None:
                    against_missing = True
            else:
                against_missing = True

    return {
        "host_facts_path": host_facts_path if host_facts_path.exists() else None,
        "machine_fit_path": machine_fit_path if machine_fit_path.exists() else None,
        "platform_adaptation_path": platform_adaptation_path if platform_adaptation_path.exists() else None,
        "session_refs": session_refs,
        "missing_session_refs": missing_session_refs,
        "diagnosis_refs": diagnosis_refs,
        "missing_diagnosis_refs": missing_diagnosis_refs,
        "diagnosis_ref_payloads": diagnosis_ref_payloads,
        "against_label": against_label,
        "against_ref_path": against_ref_path,
        "against_missing": against_missing,
        "against_session": against_session,
    }


def add_drift(
    drifts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    kind: str,
    severity: str,
    summary: str,
    probable_causes: list[str] | None = None,
    owner_hint: str | None = None,
    evidence_refs: list[str] | None = None,
) -> None:
    key = (kind, summary)
    if key in seen:
        return
    seen.add(key)
    payload: dict[str, Any] = {
        "kind": kind,
        "severity": severity,
        "summary": summary,
    }
    if probable_causes:
        payload["probable_causes"] = probable_causes
    if owner_hint:
        payload["owner_hint"] = owner_hint
    if evidence_refs:
        payload["evidence_refs"] = evidence_refs
    drifts.append(payload)


def doctor_drifts(
    drifts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    doctor_check: dict[str, Any],
) -> None:
    doctor_ref = command_ref(doctor_check["command"])
    for failure in doctor_check["failures"]:
        add_drift(
            drifts,
            seen,
            kind="host_posture_drift",
            severity="high",
            summary=f"Doctor reported a hard readiness failure: {failure}",
            probable_causes=[failure],
            owner_hint="abyss-stack/runtime-readiness",
            evidence_refs=[doctor_ref],
        )
    for warning in doctor_check["material_warnings"]:
        lowered = warning.lower()
        if "host loadavg" in lowered or "noisy for latency-sensitive" in lowered:
            kind = "noise_envelope"
            severity = "medium"
            owner_hint = "abyss-stack/runtime-envelope"
        elif "machine-fit record missing" in lowered:
            kind = "evidence_gap"
            severity = "medium"
            owner_hint = "abyss-stack/machine-fit"
        else:
            kind = "host_posture_drift"
            severity = "medium"
            owner_hint = "abyss-stack/runtime-readiness"
        add_drift(
            drifts,
            seen,
            kind=kind,
            severity=severity,
            summary=f"Doctor reported a bounded readiness warning: {warning}",
            probable_causes=[warning],
            owner_hint=owner_hint,
            evidence_refs=[doctor_ref],
        )


def autonomy_drifts(
    drifts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    autonomy_check: dict[str, Any],
) -> None:
    autonomy_ref = command_ref(autonomy_check["command"])
    for reason in autonomy_check["degradation_reasons"]:
        if reason == "source_root_unresolved":
            add_drift(
                drifts,
                seen,
                kind="truth_gap",
                severity="medium",
                summary="The canonical source checkout could not be resolved for parity-aware truth checks.",
                probable_causes=["AOA_SOURCE_ROOT is unset or the canonical source checkout is not discoverable."],
                owner_hint="abyss-stack/source-root",
                evidence_refs=[autonomy_ref],
            )
        elif reason == "source_runtime_drift":
            add_drift(
                drifts,
                seen,
                kind="source_deploy_drift",
                severity="high",
                summary="Source/deployed parity drift is present for the current runtime surface.",
                probable_causes=["Sync-managed source changes have not reached the deployed Configs mirror."],
                owner_hint="abyss-stack/config-sync",
                evidence_refs=[autonomy_ref],
            )
        elif reason == "llamacpp_verify_failed":
            add_drift(
                drifts,
                seen,
                kind="runtime_health_drift",
                severity="high",
                summary="The promoted llama.cpp control path did not pass its verify gate.",
                probable_causes=["The current promoted local-worker lane is not healthy enough to trust live runtime claims."],
                owner_hint="abyss-stack/llamacpp-lane",
                evidence_refs=[autonomy_ref],
            )
        elif reason == "route_api_health_failed":
            add_drift(
                drifts,
                seen,
                kind="runtime_health_drift",
                severity="high",
                summary="route-api health is required for this runtime shape but is currently not green.",
                probable_causes=["The federated advisory runtime is active but the route-api health surface is degraded."],
                owner_hint="abyss-stack/route-api",
                evidence_refs=[autonomy_ref],
            )
        elif reason == "route_api_surface_status_invalid":
            add_drift(
                drifts,
                seen,
                kind="closure_drift",
                severity="high",
                summary="route-api closure reporting is invalid for the current runtime shape.",
                probable_causes=["The runtime cannot currently prove closure posture for the federated advisory surface."],
                owner_hint="abyss-stack/route-api",
                evidence_refs=[autonomy_ref],
            )
        elif reason.startswith("closure_gap:"):
            layer = reason.split(":", 1)[1]
            add_drift(
                drifts,
                seen,
                kind="closure_drift",
                severity="medium",
                summary=f"The federated closure summary is degraded for layer `{layer}`.",
                probable_causes=[f"route-api closure reporting still lists `{layer}` as degraded or failing."],
                owner_hint=f"abyss-stack/federation-{layer}",
                evidence_refs=[autonomy_ref],
            )
        elif reason.startswith("federation_layer_failed:"):
            layer = reason.split(":", 1)[1]
            add_drift(
                drifts,
                seen,
                kind="closure_drift",
                severity="medium",
                summary=f"The federation mirror check failed for layer `{layer}`.",
                probable_causes=[f"The runtime mirror for `{layer}` is not green for the current runtime shape."],
                owner_hint=f"abyss-stack/federation-{layer}",
                evidence_refs=[autonomy_ref],
            )
        elif reason.startswith("trial_live_gap:"):
            trial = reason.split(":", 1)[1]
            add_drift(
                drifts,
                seen,
                kind="truth_gap",
                severity="medium",
                summary=f"{trial} remains trial-proven but not live-available on the promoted path.",
                probable_causes=[f"{trial} still needs a live-available promoted runtime claim."],
                owner_hint="abyss-stack/promoted-runtime",
                evidence_refs=[autonomy_ref],
            )
        elif reason.startswith("trial_status_unavailable:"):
            trial = reason.split(":", 1)[1]
            add_drift(
                drifts,
                seen,
                kind="evidence_gap",
                severity="medium",
                summary=f"{trial} truth status is unavailable for the autonomy verdict.",
                probable_causes=[f"{trial} summary artifacts are missing or unreadable."],
                owner_hint="abyss-stack/local-ai-trials",
                evidence_refs=[autonomy_ref],
            )
        elif reason == "autonomy_payload_unavailable":
            add_drift(
                drifts,
                seen,
                kind="evidence_gap",
                severity="high",
                summary="The autonomy status payload could not be collected or parsed.",
                probable_causes=["aoa-status --autonomy --json did not return a machine-readable object."],
                owner_hint="abyss-stack/autonomy-verdict",
                evidence_refs=[autonomy_ref],
            )


def reference_drifts(
    drifts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    refs: dict[str, Any],
    *,
    selector_context: dict[str, Any],
    truth_goal: str,
) -> list[str]:
    unknowns: list[str] = []
    if refs["host_facts_path"] is None:
        add_drift(
            drifts,
            seen,
            kind="evidence_gap",
            severity="medium",
            summary="No current host-facts record is available under Logs/host-facts.",
            probable_causes=["scripts/aoa-host-facts has not been refreshed for the current runtime root."],
            owner_hint="abyss-stack/host-facts",
        )
    if refs["machine_fit_path"] is None:
        add_drift(
            drifts,
            seen,
            kind="evidence_gap",
            severity="medium",
            summary="No current machine-fit record is available under Logs/machine-fit/latest/.",
            probable_causes=["scripts/aoa-machine-fit has not been refreshed for the current runtime root."],
            owner_hint="abyss-stack/machine-fit",
        )
    if refs["platform_adaptation_path"] is None:
        add_drift(
            drifts,
            seen,
            kind="adaptation_staleness",
            severity="low",
            summary="No current platform-adaptation record is available under Logs/platform-adaptations/latest/.",
            probable_causes=["No recent bounded adaptation note was captured for this runtime posture."],
            owner_hint="abyss-stack/platform-adaptation",
        )
    if refs["missing_session_refs"]:
        add_drift(
            drifts,
            seen,
            kind="boundary_confusion",
            severity="medium",
            summary="One or more requested reviewed session refs could not be resolved.",
            probable_causes=refs["missing_session_refs"],
            owner_hint="abyss-stack/diagnostic-spine",
        )
    if refs["missing_diagnosis_refs"]:
        add_drift(
            drifts,
            seen,
            kind="boundary_confusion",
            severity="medium",
            summary="One or more requested reviewed diagnosis refs could not be resolved.",
            probable_causes=refs["missing_diagnosis_refs"],
            owner_hint="abyss-stack/diagnosis-companion",
        )
    if refs["against_label"] and refs["against_missing"]:
        unknowns.append(
            f"No readable `{refs['against_label']}` comparison anchor was available for this diagnostic pass."
        )
    elif not refs["against_label"]:
        unknowns.append("No last-good comparison was requested for this diagnostic pass.")
    else:
        unknowns.append(f"Compared against `{refs['against_label']}` for this diagnostic pass.")

    if not refs["session_refs"]:
        unknowns.append("No reviewed session packet refs were supplied for this diagnostic pass.")
    if not refs["diagnosis_refs"]:
        unknowns.append("No reviewed diagnosis refs were supplied for this diagnostic pass.")
    return unknowns


def axis_from_drift(drifts: list[dict[str, Any]], *kinds: str) -> str | None:
    max_rank = -1
    for drift in drifts:
        if drift["kind"] not in kinds:
            continue
        max_rank = max(max_rank, DRIFT_SEVERITY_RANK[drift["severity"]])
    if max_rank < 0:
        return None
    if max_rank >= DRIFT_SEVERITY_RANK["high"]:
        return "fail"
    return "warn"


def control_truth_status(autonomy_check: dict[str, Any]) -> dict[str, bool]:
    payload = autonomy_check["truth_status"]
    return {field: bool(payload.get(field)) for field in CONTROL_PLANE_FIELDS}


def truth_goal_satisfied(*, truth_status: dict[str, bool], truth_goal: str) -> bool:
    field = TRUTH_GOAL_TO_FIELD[truth_goal]
    return bool(truth_status.get(field))


def reviewed_diagnosis_verdict_for(session: dict[str, Any]) -> str:
    if session["exit_class"] == "repairable_under_governance":
        return "ready_for_repair_handoff"
    if session["exit_class"] in {"live_but_drifted", "trial_proven_not_live", "running_but_unproven"}:
        return "retest_before_repair"
    return "not_repair_fit"


def reviewed_diagnosis_summary_for(session: dict[str, Any], verdict: str) -> str:
    if verdict == "ready_for_repair_handoff":
        return (
            "The diagnosis is reviewed and bounded enough to support an explicit repair handoff "
            "for this target."
        )
    if verdict == "retest_before_repair":
        return (
            "The diagnosis is sound enough to review, but the current drift posture should be "
            "retested before any REPAIR_PACKET is treated as ready."
        )
    return (
        "The reviewed diagnosis does not currently support a repair handoff for this target "
        "shape."
    )


def determine_axes(
    *,
    doctor_check: dict[str, Any],
    render_check: dict[str, Any],
    autonomy_check: dict[str, Any],
    drifts: list[dict[str, Any]],
    refs: dict[str, Any],
) -> dict[str, str]:
    readiness = "pass"
    if doctor_check["status"] == "fail":
        readiness = "fail"
    elif doctor_check["material_warnings"]:
        readiness = "warn"

    posture = axis_from_drift(drifts, "host_posture_drift", "noise_envelope", "adaptation_staleness") or "pass"
    render_truth = "pass" if render_check["status"] == "pass" else "fail"
    render_truth = axis_from_drift(drifts, "render_truth_drift") or render_truth

    runtime_health = "pass"
    if autonomy_check["status"] == "fail":
        runtime_health = "fail"
    elif autonomy_check["status"] != "pass":
        runtime_health = "warn"
    runtime_health = axis_from_drift(drifts, "runtime_health_drift", "truth_gap") or runtime_health

    route_surface_status = (
        autonomy_check["payload"].get("checks", {}).get("route_api_surface_status", {}).get("status")
        if autonomy_check["payload"]
        else None
    )
    if route_surface_status == "not_enabled":
        closure = "skipped"
    else:
        closure = axis_from_drift(drifts, "closure_drift") or ("pass" if autonomy_check["status"] == "pass" else "warn")

    evidence = "pass"
    if (
        refs["host_facts_path"] is None
        or refs["machine_fit_path"] is None
        or autonomy_check["payload"] is None
        or render_check["status"] != "pass"
    ):
        evidence = "warn"
    if refs["missing_session_refs"]:
        evidence = "fail"
    evidence = axis_from_drift(drifts, "evidence_gap") or evidence

    governability = axis_from_drift(drifts, "boundary_confusion", "policy_gate_block") or "pass"
    return {
        "readiness": readiness,
        "posture": posture,
        "render_truth": render_truth,
        "runtime_health": runtime_health,
        "closure": closure,
        "evidence": evidence,
        "governability": governability,
    }


def compare_against_anchor(
    drifts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    current_target: dict[str, Any],
    current_truth_status: dict[str, bool],
    current_axes: dict[str, str],
    refs: dict[str, Any],
) -> None:
    anchor_session = refs["against_session"]
    against_ref = [str(refs["against_ref_path"])] if refs["against_ref_path"] else None
    if anchor_session is None:
        return
    anchor_target = anchor_session.get("target")
    if not isinstance(anchor_target, dict):
        return
    anchor_preset = str(anchor_target.get("preset", ""))
    anchor_profiles = anchor_target.get("profiles")
    anchor_truth_goal = str(anchor_target.get("truth_goal", ""))
    if (
        anchor_preset != current_target["preset"]
        or anchor_truth_goal != current_target["truth_goal"]
        or anchor_profiles != current_target["profiles"]
    ):
        add_drift(
            drifts,
            seen,
            kind="selector_drift",
            severity="medium",
            summary="The selected diagnostic target does not match the supplied comparison anchor.",
            probable_causes=["The last-good anchor was captured for a different preset/profile/truth-goal shape."],
            owner_hint="abyss-stack/diagnostic-target",
            evidence_refs=against_ref,
        )
        return

    anchor_truth_status = anchor_session.get("truth_status")
    if isinstance(anchor_truth_status, dict):
        if anchor_truth_status.get("live_available") and not current_truth_status["live_available"]:
            add_drift(
                drifts,
                seen,
                kind="truth_gap",
                severity="high",
                summary="The current target is no longer live-available compared with the supplied last-good anchor.",
                probable_causes=["A previously live-available target has regressed on the current pass."],
                owner_hint="abyss-stack/diagnostic-spine",
                evidence_refs=against_ref,
            )
        if anchor_truth_status.get("trial_proven") and not current_truth_status["trial_proven"]:
            add_drift(
                drifts,
                seen,
                kind="truth_gap",
                severity="medium",
                summary="The current target lost trial-proven posture compared with the supplied last-good anchor.",
                probable_causes=["The promoted trial truth surface regressed since the anchor was recorded."],
                owner_hint="abyss-stack/diagnostic-spine",
                evidence_refs=against_ref,
            )

    anchor_axes = anchor_session.get("axes")
    if not isinstance(anchor_axes, dict):
        return
    axis_to_kind = {
        "readiness": "host_posture_drift",
        "posture": "host_posture_drift",
        "render_truth": "render_truth_drift",
        "runtime_health": "runtime_health_drift",
        "closure": "closure_drift",
        "evidence": "evidence_gap",
        "governability": "policy_gate_block",
    }
    for axis_name, current_value in current_axes.items():
        anchor_value = anchor_axes.get(axis_name)
        if not isinstance(anchor_value, str):
            continue
        if AXIS_RANK.get(current_value, 0) >= AXIS_RANK.get(anchor_value, 0):
            continue
        severity = "high" if current_value == "fail" else "medium"
        add_drift(
            drifts,
            seen,
            kind=axis_to_kind[axis_name],
            severity=severity,
            summary=f"Axis `{axis_name}` is worse than the supplied last-good anchor.",
            probable_causes=[f"Current `{axis_name}` is `{current_value}` while the anchor recorded `{anchor_value}`."],
            owner_hint="abyss-stack/diagnostic-spine",
            evidence_refs=against_ref,
        )


def choose_exit_class(
    *,
    truth_status: dict[str, bool],
    axes: dict[str, str],
    drifts: list[dict[str, Any]],
) -> str:
    if axes["readiness"] == "fail" or axes["evidence"] == "fail" or axes["governability"] == "fail":
        return "manual_reground_required"
    if truth_status["live_available"]:
        if drifts and any(drift["severity"] in {"high", "critical"} for drift in drifts):
            return "repairable_under_governance"
        if drifts or any(value == "warn" for value in axes.values()):
            return "live_but_drifted"
        return "running_as_intended"
    if truth_status["trial_proven"] and not truth_status["live_available"]:
        if any(drift["severity"] in {"high", "critical"} for drift in drifts):
            return "repairable_under_governance"
        return "trial_proven_not_live"
    if truth_status["deployed"] and not truth_status["trial_proven"]:
        if axes["runtime_health"] == "fail":
            return "repairable_under_governance"
        return "running_but_unproven"
    if axes["readiness"] == "pass" and axes["render_truth"] == "pass":
        return "ready_to_start"
    return "manual_reground_required"


def build_next_moves(
    *,
    exit_class: str,
    drifts: list[dict[str, Any]],
    selector_context: dict[str, Any],
    truth_goal: str,
) -> list[dict[str, Any]]:
    if exit_class == "running_as_intended":
        return [
            {
                "class": "no_action",
                "summary": "The current diagnostic pass is green for the selected target shape.",
                "owner_repo": "abyss-stack",
                "requires_approval": False,
            }
        ]

    retest_move = {
        "class": "retest",
        "summary": "Re-run aoa-diagnose after refreshing the bounded evidence surfaces for the same target.",
        "command": self_command(selector_context, truth_goal=truth_goal),
        "owner_repo": "abyss-stack",
        "requires_approval": False,
    }
    if exit_class == "ready_to_start":
        return [retest_move]

    moves: list[dict[str, Any]] = [retest_move]
    if exit_class in {"live_but_drifted", "repairable_under_governance", "trial_proven_not_live", "running_but_unproven"}:
        moves.append(
            {
                "class": "repair_packet_candidate",
                "summary": "Keep repair explicit: emit a reviewed repair packet before any mutation is attempted.",
                "owner_repo": "aoa-skills",
                "requires_approval": True,
            }
        )
    if drifts:
        moves.append(
            {
                "class": "quest_followup",
                "summary": "Keep repeated diagnostic drift explicit in quest tracking while the route is still being stabilized.",
                "owner_repo": "abyss-stack",
                "requires_approval": False,
            }
        )
    if exit_class == "manual_reground_required":
        moves.insert(
            0,
            {
                "class": "manual_reground",
                "summary": "Reground the target, evidence refs, and runtime boundaries before trusting a repair route.",
                "owner_repo": "abyss-stack",
                "requires_approval": False,
            }
        )
    return moves


def collect_diagnostic_bundle(
    args: argparse.Namespace,
    *,
    selector_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selector = selector_context or resolve_selector_context()
    doctor_check = collect_doctor_check()
    render_check = collect_render_services_check()
    autonomy_check = collect_autonomy_check()
    refs = load_reference_artifacts(args)
    target = build_target(args, selector, render_check)

    drifts: list[dict[str, Any]] = []
    seen_drift_keys: set[tuple[str, str]] = set()
    doctor_drifts(drifts, seen_drift_keys, doctor_check)
    autonomy_drifts(drifts, seen_drift_keys, autonomy_check)
    unknowns = reference_drifts(
        drifts,
        seen_drift_keys,
        refs,
        selector_context=selector,
        truth_goal=args.truth_goal,
    )
    if render_check["status"] != "pass":
        add_drift(
            drifts,
            seen_drift_keys,
            kind="render_truth_drift",
            severity="high",
            summary="The rendered service shape could not be resolved cleanly for the selected target.",
            probable_causes=["aoa-render-services failed for the current selector shape."],
            owner_hint="abyss-stack/render-truth",
            evidence_refs=[command_ref(render_check["command"])],
        )

    truth_status = control_truth_status(autonomy_check)
    provisional_axes = determine_axes(
        doctor_check=doctor_check,
        render_check=render_check,
        autonomy_check=autonomy_check,
        drifts=drifts,
        refs=refs,
    )
    compare_against_anchor(
        drifts,
        seen_drift_keys,
        current_target=target,
        current_truth_status=truth_status,
        current_axes=provisional_axes,
        refs=refs,
    )
    axes = determine_axes(
        doctor_check=doctor_check,
        render_check=render_check,
        autonomy_check=autonomy_check,
        drifts=drifts,
        refs=refs,
    )
    exit_class = choose_exit_class(truth_status=truth_status, axes=axes, drifts=drifts)

    strong_refs: dict[str, list[str]] = {}
    if refs["host_facts_path"] is not None:
        strong_refs["host_facts"] = [relative_ref(refs["host_facts_path"])]
    if refs["machine_fit_path"] is not None:
        strong_refs["machine_fit"] = [relative_ref(refs["machine_fit_path"])]
    if refs["platform_adaptation_path"] is not None:
        strong_refs["platform_adaptation"] = [relative_ref(refs["platform_adaptation_path"])]
    if render_check["status"] == "pass":
        strong_refs["render_truth"] = [command_ref(render_check["command"] + selector_cli_args(selector))]
    if autonomy_check["payload"] is not None:
        strong_refs["autonomy"] = [command_ref(autonomy_check["command"])]
    if refs["session_refs"]:
        strong_refs["session_packets"] = refs["session_refs"]
    if refs["diagnosis_refs"]:
        strong_refs["diagnosis_packets"] = refs["diagnosis_refs"]
    if refs["against_ref_path"] is not None and not refs["against_missing"]:
        strong_refs["comparison_anchor"] = [str(refs["against_ref_path"])]

    captured_at = utc_now()
    captured_at_text = utc_timestamp(captured_at)
    session_id = args.diagnostic_id or f"diag-{captured_at.strftime('%Y%m%dt%H%M%Sz').lower()}-{slugify(selector['preset'])}-{slugify(args.truth_goal)}"

    session: dict[str, Any] = {
        "schema_version": "diagnostic_session_v1",
        "id": session_id,
        "repo": "abyss-stack",
        "captured_at": captured_at_text,
        "runtime_root": str(STACK_ROOT),
        "target": {
            "preset": target["preset"],
            "profiles": target["profiles"],
            "truth_goal": target["truth_goal"],
        },
        "axes": axes,
        "truth_status": truth_status,
        "drifts": drifts,
        "unknowns": unknowns,
        "exit_class": exit_class,
        "next_moves": build_next_moves(
            exit_class=exit_class,
            drifts=drifts,
            selector_context=selector,
            truth_goal=args.truth_goal,
        ),
        "public_safe": True,
    }
    if strong_refs:
        session["strong_refs"] = strong_refs
    return {
        "target": target,
        "session": session,
        "_meta": {
            "selector": selector,
            "refs": refs,
        },
    }


def anchor_ref_for(bundle: dict[str, Any]) -> dict[str, Any]:
    session = bundle["session"]
    target = session["target"]
    records_root = STACK_ROOT / "Logs" / "diagnostics" / "records" / session["id"]
    return {
        "schema_version": "diagnostic_anchor_ref_v1",
        "artifact_kind": "aoa.diagnostic.anchor-ref",
        "anchor_class": "last_good",
        "id": f"anchor-{session['id']}",
        "repo": session["repo"],
        "captured_at": session["captured_at"],
        "target": {
            "preset": target["preset"],
            "profiles": target["profiles"],
            "truth_goal": target["truth_goal"],
        },
        "diagnostic_session_id": session["id"],
        "diagnostic_session_path": str(records_root / "diagnostic_session.json"),
        "diagnostic_target_path": str(records_root / "diagnostic_target.json"),
        "exit_class": session["exit_class"],
        "truth_status": session["truth_status"],
        "public_safe": True,
    }


def anchor_write_eligibility(bundle: dict[str, Any]) -> tuple[bool, str]:
    session = bundle["session"]
    truth_status = session["truth_status"]
    truth_goal = session["target"]["truth_goal"]
    if not truth_goal_satisfied(truth_status=truth_status, truth_goal=truth_goal):
        return False, f"truth goal `{truth_goal}` is not currently satisfied"
    if session["drifts"]:
        return False, "current diagnostic session still records drift items"
    non_green_axes = [
        axis
        for axis, verdict in session["axes"].items()
        if verdict not in {"pass", "skipped"}
    ]
    if non_green_axes:
        return False, "current diagnostic session still has non-green axes: " + ", ".join(sorted(non_green_axes))
    return True, ""


def top_trigger_drifts(drifts: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    sorted_drifts = sorted(
        drifts,
        key=lambda item: (DRIFT_SEVERITY_RANK[item["severity"]], item["kind"], item["summary"]),
        reverse=True,
    )
    return sorted_drifts[:limit]


def repair_shape_for_drift(drift: dict[str, Any]) -> str:
    kind = drift["kind"]
    if kind == "noise_envelope":
        return "Reduce competing local load or wait for the runtime envelope to settle, then retest the same target."
    if kind == "source_deploy_drift":
        return "Replay config sync and rerun parity-aware diagnosis before any repair packet is attempted."
    if kind == "truth_gap":
        return "Treat the gap as diagnosis-first work and review whether a bounded REPAIR_PACKET is honest for the current target."
    if kind in {"runtime_health_drift", "render_truth_drift", "closure_drift"}:
        return "Keep the route diagnostic-first, then author the smallest bounded repair only after the affected runtime surface is reviewed."
    if kind in {"boundary_confusion", "policy_gate_block"}:
        return "Clarify owner-layer law and checkpoint posture before repair planning."
    if kind == "evidence_gap":
        return "Refresh the missing evidence surface before escalating to repair planning."
    return "Keep the route bounded, diagnosis-first, and evidence-linked before naming any repair packet."


def confidence_for_drift(drift: dict[str, Any]) -> str:
    severity = drift["severity"]
    if severity in {"high", "critical"}:
        return "high"
    if severity == "medium":
        return "medium"
    return "low"


def reviewed_diagnosis_ref_for(bundle: dict[str, Any], *, reviewer: str) -> dict[str, Any]:
    session = bundle["session"]
    target = session["target"]
    records_root = STACK_ROOT / "Logs" / "diagnostics" / "records" / session["id"]
    drifts = list(session["drifts"])
    verdict = reviewed_diagnosis_verdict_for(session)
    severity_ranks = [DRIFT_SEVERITY_RANK.get(str(drift.get("severity")), -1) for drift in drifts]
    if not drifts:
        confidence_band = "low"
    elif all(rank >= DRIFT_SEVERITY_RANK["high"] for rank in severity_ranks):
        confidence_band = "high"
    else:
        confidence_band = "medium"

    diagnosis_types = list(dict.fromkeys(str(drift["kind"]) for drift in drifts))
    symptom_refs = list(dict.fromkeys(str(drift["summary"]) for drift in drifts))
    probable_cause_hypotheses = list(
        dict.fromkeys(
            cause
            for drift in drifts
            for cause in (drift.get("probable_causes") or ["The current evidence stays incomplete."])
        )
    )
    owner_hints = list(
        dict.fromkeys(
            str(drift.get("owner_hint") or "abyss-stack/diagnostic-spine")
            for drift in drifts
        )
    )

    reviewed_ref: dict[str, Any] = {
        "schema_version": "reviewed_diagnosis_ref_v1",
        "artifact_kind": "aoa.diagnostic.reviewed-diagnosis-ref",
        "id": f"reviewed-diagnosis-{session['id']}",
        "repo": session["repo"],
        "reviewed_at": utc_timestamp(utc_now()),
        "reviewer": reviewer,
        "source_diagnosis_companion_ref": relative_ref(records_root / "diagnosis_companion.json"),
        "diagnostic_session_ref": relative_ref(records_root / "diagnostic_session.json"),
        "diagnostic_session_id": session["id"],
        "target": {
            "preset": target["preset"],
            "profiles": target["profiles"],
            "truth_goal": target["truth_goal"],
        },
        "skill_name": "aoa-session-self-diagnose",
        "result_kind": "diagnosis_packet_review",
        "review_verdict": verdict,
        "summary": reviewed_diagnosis_summary_for(session, verdict),
        "diagnosis_types": diagnosis_types,
        "symptom_refs": symptom_refs,
        "probable_cause_hypotheses": probable_cause_hypotheses,
        "confidence_band": confidence_band,
        "owner_hints": owner_hints,
        "repair_handoff_ref": relative_ref(records_root / "repair_handoff.json"),
        "public_safe": True,
    }
    if session.get("unknowns"):
        reviewed_ref["unknowns"] = list(session["unknowns"])
    return reviewed_ref


def reviewed_diagnosis_write_eligibility(bundle: dict[str, Any]) -> tuple[bool, str]:
    session = bundle["session"]
    if session["exit_class"] == "running_as_intended":
        return False, "green diagnostic sessions do not need reviewed diagnosis refs"
    if not session["drifts"]:
        return False, "reviewed diagnosis refs require at least one drift to review"
    return True, ""


def diagnosis_companion_for(bundle: dict[str, Any]) -> dict[str, Any]:
    session = bundle["session"]
    target = session["target"]
    refs = bundle.get("_meta", {}).get("refs") or {}
    diagnosis_ref_payloads = list(refs.get("diagnosis_ref_payloads") or [])
    diagnostic_session_ref = (
        STACK_ROOT / "Logs" / "diagnostics" / "records" / session["id"] / "diagnostic_session.json"
    )
    diagnoses: list[dict[str, Any]] = []
    for drift in session["drifts"]:
        diagnoses.append(
            {
                "drift_type": drift["kind"],
                "symptom": drift["summary"],
                "probable_causes": list(drift.get("probable_causes") or ["The current evidence stays incomplete."]),
                "repair_shape": repair_shape_for_drift(drift),
                "owner_hint": str(drift.get("owner_hint") or "abyss-stack/diagnostic-spine"),
                "confidence": confidence_for_drift(drift),
                "evidence_refs": list(drift.get("evidence_refs") or []),
            }
        )

    if session["exit_class"] == "running_as_intended":
        review_status = "not_needed"
        summary = "The current diagnostic pass is green, so no diagnosis companion review is needed for this target."
        suggested_next_skill = None
    elif refs.get("diagnosis_refs"):
        review_status = "reviewed_ref_supplied"
        summary = (
            "Reviewed diagnosis refs were supplied for this target, so this companion stays as a runtime-local bridge rather "
            "than the sole diagnosis input."
        )
        reviewed_ref_payloads = [
            payload
            for payload in diagnosis_ref_payloads
            if payload.get("schema_version") == "reviewed_diagnosis_ref_v1"
        ]
        verdicts = {
            str(payload.get("review_verdict"))
            for payload in reviewed_ref_payloads
        }
        if reviewed_ref_payloads and "ready_for_repair_handoff" in verdicts:
            suggested_next_skill = "aoa-session-self-repair"
        else:
            suggested_next_skill = "aoa-session-self-diagnose"
    else:
        review_status = "candidate_review_required"
        summary = (
            "The runtime is drifted enough to justify a diagnosis-first review pass before any REPAIR_PACKET is treated as honest."
        )
        suggested_next_skill = "aoa-session-self-diagnose"

    companion: dict[str, Any] = {
        "schema_version": "diagnosis_companion_v1",
        "artifact_kind": "aoa.diagnostic.diagnosis-companion",
        "id": f"diagnosis-{session['id']}",
        "repo": session["repo"],
        "captured_at": session["captured_at"],
        "diagnostic_session_ref": relative_ref(diagnostic_session_ref),
        "diagnostic_session_id": session["id"],
        "target": {
            "preset": target["preset"],
            "profiles": target["profiles"],
            "truth_goal": target["truth_goal"],
        },
        "review_status": review_status,
        "summary": summary,
        "diagnoses": diagnoses,
        "public_safe": True,
    }
    if session.get("unknowns"):
        companion["unknowns"] = list(session["unknowns"])
    if refs.get("diagnosis_refs"):
        companion["reviewed_diagnosis_refs"] = list(refs["diagnosis_refs"])
    if suggested_next_skill:
        companion["suggested_next_skill"] = suggested_next_skill
    return companion


def repair_handoff_for(bundle: dict[str, Any]) -> dict[str, Any]:
    session = bundle["session"]
    target = session["target"]
    refs = bundle.get("_meta", {}).get("refs") or {}
    selector = bundle.get("_meta", {}).get("selector") or resolve_selector_context()
    diagnostic_session_ref = (
        STACK_ROOT / "Logs" / "diagnostics" / "records" / session["id"] / "diagnostic_session.json"
    )
    diagnosis_companion_ref = (
        STACK_ROOT / "Logs" / "diagnostics" / "records" / session["id"] / "diagnosis_companion.json"
    )
    trigger_drifts = top_trigger_drifts(session["drifts"])
    reviewed_session_refs = list(refs.get("session_refs") or [])
    reviewed_diagnosis_refs = list(refs.get("diagnosis_refs") or [])
    diagnosis_ref_payloads = list(refs.get("diagnosis_ref_payloads") or [])
    reviewed_ref_payloads = [
        payload
        for payload in diagnosis_ref_payloads
        if payload.get("schema_version") == "reviewed_diagnosis_ref_v1"
    ]
    reviewed_verdicts = {
        str(payload.get("review_verdict"))
        for payload in reviewed_ref_payloads
        if isinstance(payload.get("review_verdict"), str)
    }
    comparison_anchor_ref = (
        str(refs["against_ref_path"])
        if refs.get("against_ref_path") is not None and not refs.get("against_missing")
        else None
    )

    if session["exit_class"] == "running_as_intended":
        handoff_readiness = "not_needed"
        summary = "The current diagnostic pass is green, so no repair handoff is needed for this target shape."
        blocked_by: list[str] = []
    elif reviewed_diagnosis_refs and not reviewed_ref_payloads:
        handoff_readiness = "review_required"
        summary = (
            "Reviewed diagnosis refs were supplied, but none resolved to valid reviewed_diagnosis_ref_v1 artifacts, so repair still requires an explicit reviewed diagnosis before handoff."
        )
        blocked_by = ["valid_reviewed_diagnosis_required"]
    elif reviewed_ref_payloads:
        if "ready_for_repair_handoff" in reviewed_verdicts:
            handoff_readiness = "ready_for_review"
            summary = (
                "A reviewed diagnosis ref explicitly supports repair handoff, so repair can move forward as a reviewable next step."
            )
            blocked_by = []
        elif reviewed_verdicts and reviewed_verdicts <= {"retest_before_repair"}:
            handoff_readiness = "blocked"
            summary = (
                "A reviewed diagnosis ref exists, but it still recommends retest before any REPAIR_PACKET becomes ready for review."
            )
            blocked_by = ["reviewed_diagnosis_requires_retest"]
        else:
            handoff_readiness = "blocked"
            summary = (
                "A reviewed diagnosis ref exists, but it does not currently support a repair handoff for this target."
            )
            blocked_by = ["reviewed_diagnosis_not_repair_fit"]
    else:
        handoff_readiness = "review_required"
        summary = (
            "Repair may be warranted, but the diagnosis companion still needs review before any REPAIR_PACKET should be treated as ready for review."
        )
        blocked_by = ["reviewed_diagnosis_required"]

    handoff: dict[str, Any] = {
        "schema_version": "repair_handoff_v1",
        "artifact_kind": "aoa.diagnostic.repair-handoff",
        "id": f"repair-handoff-{session['id']}",
        "repo": session["repo"],
        "captured_at": session["captured_at"],
        "diagnostic_session_ref": relative_ref(diagnostic_session_ref),
        "diagnostic_session_id": session["id"],
        "diagnosis_companion_ref": relative_ref(diagnosis_companion_ref),
        "target": {
            "preset": target["preset"],
            "profiles": target["profiles"],
            "truth_goal": target["truth_goal"],
        },
        "target_skill": "aoa-session-self-repair",
        "target_owner_repo": "aoa-skills",
        "handoff_readiness": handoff_readiness,
        "summary": summary,
        "trigger_drifts": trigger_drifts,
        "checkpoint_posture": {
            "policy_fit": (
                "Keep repair inside aoa-session-self-repair as a bounded REPAIR_PACKET; "
                "aoa-diagnose remains descriptive and does not grant mutation authority."
            ),
            "approval_gate": (
                "Run the standard mutation gate again before any code, repo-config, or runtime change."
            ),
            "rollback_marker": (
                "Prefer last_good.ref.json when available; otherwise capture a fresh green diagnostic "
                "anchor before mutating important surfaces."
            ),
            "health_check": self_command(selector, truth_goal=target["truth_goal"]),
            "iteration_limit": "One bounded repair unit before rerunning aoa-diagnose.",
            "improvement_log_stub": (
                "Record target owner surface, chosen diff shape, approval outcome, and validation refs "
                "in the eventual REPAIR_PACKET."
            ),
        },
        "validation_refs": [
            self_command(selector, truth_goal=target["truth_goal"]),
            command_ref(["bash", str(CONFIGS_ROOT / "scripts" / "aoa-status"), "--autonomy", "--json"]),
        ],
        "stop_conditions": [
            "Stop if the route widens beyond one bounded repair unit.",
            "Stop if role-law changes become necessary.",
            "Stop if proof-law changes become necessary.",
        ],
        "escalation_routes": [
            {
                "condition": "The repair widens into a scenario rollout.",
                "owner_repo": "aoa-playbooks",
                "note": "Escalate scenario-scale rollout work instead of faking one repair packet.",
            },
            {
                "condition": "The repair changes role law or orchestration posture.",
                "owner_repo": "aoa-agents",
                "note": "Route role-law changes to aoa-agents.",
            },
            {
                "condition": "The repair changes proof or evaluation law.",
                "owner_repo": "aoa-evals",
                "note": "Route proof-law changes to aoa-evals.",
            },
        ],
        "public_safe": True,
    }
    if comparison_anchor_ref:
        handoff["comparison_anchor_ref"] = comparison_anchor_ref
    if reviewed_session_refs:
        handoff["reviewed_session_refs"] = reviewed_session_refs
    if reviewed_diagnosis_refs:
        handoff["reviewed_diagnosis_refs"] = reviewed_diagnosis_refs
    if blocked_by:
        handoff["blocked_by"] = blocked_by
    return handoff


def write_bundle(bundle: dict[str, Any], args: argparse.Namespace) -> None:
    if args.write:
        write_json(Path(args.write).expanduser(), bundle["session"])
    if args.write_last_good_ref and not args.write_latest:
        raise ValueError("--write-last-good-ref requires --write-latest")
    if args.write_reviewed_diagnosis_ref and not args.write_latest:
        raise ValueError("--write-reviewed-diagnosis-ref requires --write-latest")
    if not args.write_latest:
        return

    latest_root = STACK_ROOT / "Logs" / "diagnostics" / "latest"
    records_root = STACK_ROOT / "Logs" / "diagnostics" / "records" / bundle["session"]["id"]
    write_json(latest_root / "diagnostic_target.json", bundle["target"])
    write_json(latest_root / "diagnostic_session.json", bundle["session"])
    write_json(records_root / "diagnostic_target.json", bundle["target"])
    write_json(records_root / "diagnostic_session.json", bundle["session"])
    diagnosis_companion = diagnosis_companion_for(bundle)
    write_json(latest_root / "diagnosis_companion.json", diagnosis_companion)
    write_json(records_root / "diagnosis_companion.json", diagnosis_companion)
    repair_handoff = repair_handoff_for(bundle)
    write_json(latest_root / "repair_handoff.json", repair_handoff)
    write_json(records_root / "repair_handoff.json", repair_handoff)
    if args.write_reviewed_diagnosis_ref:
        eligible, reason = reviewed_diagnosis_write_eligibility(bundle)
        if not eligible:
            raise ValueError(f"diagnostic session is not eligible for reviewed diagnosis promotion: {reason}")
        reviewed_ref = reviewed_diagnosis_ref_for(bundle, reviewer=args.reviewer)
        write_json(latest_root / "reviewed_diagnosis.ref.json", reviewed_ref)
        write_json(records_root / "reviewed_diagnosis.ref.json", reviewed_ref)
    if args.write_last_good_ref:
        eligible, reason = anchor_write_eligibility(bundle)
        if not eligible:
            raise ValueError(f"diagnostic session is not eligible for last-good promotion: {reason}")
        anchor_ref = anchor_ref_for(bundle)
        write_json(latest_root / "last_good.ref.json", anchor_ref)
        write_json(records_root / "last_good.ref.json", anchor_ref)


def exit_code_for(exit_class: str) -> int:
    if exit_class in {
        "running_as_intended",
        "ready_to_start",
        "running_but_unproven",
        "trial_proven_not_live",
    }:
        return 0
    if exit_class in {"live_but_drifted", "repairable_under_governance"}:
        return 1
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Emit a bounded diagnostic_session_v1 from existing abyss-stack runtime evidence."
    )
    parser.add_argument(
        "--truth-goal",
        default="live_available",
        choices=["deployed", "trial_proven", "live_available"],
        help="Truth goal for this diagnosis pass.",
    )
    parser.add_argument(
        "--against",
        help="Comparison anchor path, or the literal value 'last-good'.",
    )
    parser.add_argument(
        "--with-session-ref",
        action="append",
        default=[],
        help="Optional reviewed session packet refs to cite in the diagnostic session.",
    )
    parser.add_argument(
        "--with-reviewed-diagnosis-ref",
        action="append",
        default=[],
        help="Optional reviewed diagnosis packet refs that make repair handoff reviewable.",
    )
    parser.add_argument(
        "--write",
        help="Optional path where diagnostic_session.json should be written.",
    )
    parser.add_argument(
        "--write-latest",
        action="store_true",
        help="Also write diagnostic_target.json and diagnostic_session.json under ${AOA_STACK_ROOT}/Logs/diagnostics/{latest,records}.",
    )
    parser.add_argument(
        "--write-last-good-ref",
        action="store_true",
        help="When the current pass is green for its truth goal, also refresh ${AOA_STACK_ROOT}/Logs/diagnostics/latest/last_good.ref.json.",
    )
    parser.add_argument(
        "--write-reviewed-diagnosis-ref",
        action="store_true",
        help="When the current pass is drifted, also write ${AOA_STACK_ROOT}/Logs/diagnostics/latest/reviewed_diagnosis.ref.json.",
    )
    parser.add_argument(
        "--reviewer",
        default=os.environ.get("AOA_DIAG_REVIEWER", "codex"),
        help="Reviewer label recorded when --write-reviewed-diagnosis-ref is used.",
    )
    parser.add_argument(
        "--diagnostic-id",
        help="Optional explicit diagnostic session id.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        bundle = collect_diagnostic_bundle(args)
        write_bundle(bundle, args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(bundle["session"], indent=2, ensure_ascii=True))
    return exit_code_for(bundle["session"]["exit_class"])


if __name__ == "__main__":
    raise SystemExit(main())
