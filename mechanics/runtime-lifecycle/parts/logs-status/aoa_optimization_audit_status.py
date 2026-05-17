#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = SOURCE_ROOT / "scripts"
DEFAULT_STACK_ROOT = Path("/srv/AbyssOS/abyss-stack")
PROTECTED_UNITS = (
    "abyss-tts-server.service",
    "abyss-dictation-server.service",
    "abyss-tts-keepwarm.timer",
    "podman-compose-abyss.service",
)
EXPECTED_SCREENSHOT_SERVICES = {
    "postgres",
    "redis",
    "qdrant",
    "neo4j",
    "llama-cpp",
    "langchain-api",
    "ovms",
    "route-api",
    "n8n",
    "n8n-task-runners",
    "qwen-tts",
    "tts-router",
    "docs-api",
    "aoa-browser",
    "prometheus",
    "grafana",
    "alertmanager",
    "cadvisor",
}
EXPECTED_OVERLAYS = (
    "compose/tuning/storage.intel-285h.resource-guard.yml",
    "compose/tuning/intel-worker.thin-host.yml",
    "compose/tuning/federation.thin-host.yml",
    "compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml",
    "compose/tuning/observability.thin-host.yml",
    "compose/tuning/tools.thin-host.yml",
)
DEFAULT_SOURCE_ROOT = Path.home() / "src" / "abyss-stack"


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_json(argv: list[str]) -> tuple[dict[str, Any] | None, str]:
    result = run_command(argv)
    if result.returncode != 0:
        return None, result.stderr.strip() or result.stdout.strip()
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "payload is not a JSON object"
    return payload, ""


def parse_key_value_tokens(value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for token in shlex.split(value):
        key, separator, raw_value = token.partition("=")
        if separator and key:
            parsed[key] = raw_value
    return parsed


def read_unit_environment() -> dict[str, str]:
    result = run_command(
        [
            "systemctl",
            "--user",
            "show",
            "podman-compose-abyss.service",
            "-p",
            "Environment",
        ]
    )
    if result.returncode != 0:
        return {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "Environment":
            return parse_key_value_tokens(value)
    return {}


def runtime_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update(read_unit_environment())
    stack_root = Path(env.get("AOA_STACK_ROOT", str(DEFAULT_STACK_ROOT)))
    env.setdefault("AOA_STACK_ROOT", str(stack_root))
    env.setdefault("AOA_CONFIGS_ROOT", str(stack_root / "Configs"))
    return env


def read_json(path: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(payload, dict):
        return None, "payload is not a JSON object"
    return payload, ""


def check(
    checks: list[dict[str, Any]],
    check_id: str,
    requirement: str,
    status: str,
    evidence: str,
    *,
    required_for_completion: bool = True,
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(
        {
            "id": check_id,
            "requirement": requirement,
            "status": status,
            "required_for_completion": required_for_completion,
            "evidence": evidence,
            "details": details or {},
        }
    )


def protected_unit_state() -> dict[str, str]:
    result = run_command(["systemctl", "--user", "is-active", *PROTECTED_UNITS])
    states = result.stdout.splitlines()
    return {
        unit: states[index] if index < len(states) else "unknown"
        for index, unit in enumerate(PROTECTED_UNITS)
    }


def post_apply_evidence(stack_root: Path) -> dict[str, Any]:
    latest = stack_root / "Logs" / "resource-guards" / "latest"
    required_files = (
        "post-apply.json",
        "post-service-selection.json",
        "post-resource-plan.json",
        "post-podman-stats.txt",
        "post-memory.txt",
        "post-protected-units.txt",
    )
    existing = [name for name in required_files if (latest / name).is_file()]
    post_guard_status = ""
    post_service_status = ""
    if (latest / "post-apply.json").is_file():
        payload, _ = read_json(latest / "post-apply.json")
        if payload:
            post_guard_status = str(payload.get("summary", {}).get("status", ""))
    if (latest / "post-service-selection.json").is_file():
        payload, _ = read_json(latest / "post-service-selection.json")
        if payload:
            post_service_status = str(payload.get("summary", {}).get("status", ""))
    protected_active = False
    protected_path = latest / "post-protected-units.txt"
    if protected_path.is_file():
        active_count = sum(1 for line in protected_path.read_text(encoding="utf-8", errors="replace").splitlines() if line == "active")
        protected_active = active_count == len(PROTECTED_UNITS)
    return {
        "latest_dir": str(latest),
        "required_files": list(required_files),
        "existing_files": existing,
        "post_guard_status": post_guard_status,
        "post_service_selection_status": post_service_status,
        "post_protected_units_active": protected_active,
    }


def source_runtime_parity(configs_root: Path) -> dict[str, Any]:
    source_root = Path(os.environ.get("AOA_SOURCE_ROOT", str(DEFAULT_SOURCE_ROOT)))
    command = [
        "python3",
        "scripts/validate_stack.py",
        "--parity-check",
        "--deployed-configs-root",
        str(configs_root),
    ]
    if not (source_root / "scripts" / "validate_stack.py").is_file():
        return {
            "ok": False,
            "status": "missing",
            "source_root": str(source_root),
            "command": command,
            "output": "source checkout validate_stack.py not found",
        }

    result = subprocess.run(
        command,
        cwd=source_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "ok": result.returncode == 0,
        "status": "done" if result.returncode == 0 else "failed",
        "source_root": str(source_root),
        "command": command,
        "returncode": result.returncode,
        "output": result.stdout.strip(),
    }


def build_audit() -> dict[str, Any]:
    env = runtime_environment()
    configs_root = Path(env["AOA_CONFIGS_ROOT"])
    stack_root = Path(env["AOA_STACK_ROOT"])
    checks: list[dict[str, Any]] = []

    installer = configs_root / "mechanics" / "runtime-lifecycle" / "parts" / "user-unit" / "aoa_install_systemd.sh"
    installer_text = installer.read_text(encoding="utf-8", errors="replace") if installer.is_file() else ""
    installer_ok = all(token in installer_text for token in ("--overlay", "AOA_EXTRA_COMPOSE_FILES", "20-runtime-selection.conf"))
    check(
        checks,
        "technical_debt_overlay_selection",
        "Host-local overlay selection is source-managed and persisted through the user-unit installer.",
        "done" if installer_ok else "missing",
        str(installer),
        details={"required_tokens": ["--overlay", "AOA_EXTRA_COMPOSE_FILES", "20-runtime-selection.conf"]},
    )

    inventory_path = configs_root / "docs" / "runtime" / "service-inventory-2026-05-14.v1.json"
    inventory, inventory_error = read_json(inventory_path)
    inventory_services = set(inventory.get("screenshotted_services", [])) if inventory else set()
    inventory_ok = inventory is not None and inventory_services == EXPECTED_SCREENSHOT_SERVICES
    check(
        checks,
        "screenshot_baseline",
        "The operator screenshot service list is preserved as a machine-readable baseline.",
        "done" if inventory_ok else "missing",
        str(inventory_path) if not inventory_error else f"{inventory_path}: {inventory_error}",
        details={
            "expected_services": sorted(EXPECTED_SCREENSHOT_SERVICES),
            "observed_services": sorted(str(item) for item in inventory_services),
        },
    )

    policy_path = configs_root / "docs" / "runtime" / "service-selection-policy.v1.json"
    policy, policy_error = read_json(policy_path)
    policy_services = policy.get("services", []) if policy else []
    policy_selected = {
        entry.get("name")
        for entry in policy_services
        if isinstance(entry, dict) and entry.get("posture") == "selected_now"
    }
    policy_ok = (
        policy is not None
        and policy.get("schema") == "abyss_stack_service_selection_policy_v1"
        and len(policy_services) >= 24
        and {"postgres", "redis", "qdrant", "neo4j", "llama-cpp", "ovms", "langchain-api", "route-api", "rerank-api"}.issubset(policy_selected)
    )
    check(
        checks,
        "service_selection_policy",
        "Service posture is classified as resident, opt-in, fallback, or lab-only.",
        "done" if policy_ok else "missing",
        str(policy_path) if not policy_error else f"{policy_path}: {policy_error}",
        details={"service_count": len(policy_services), "selected_now": sorted(str(item) for item in policy_selected)},
    )

    research_path = configs_root / "docs" / "runtime" / "SERVICE_OPTIMIZATION_RESEARCH_2026_05.md"
    research_text = research_path.read_text(encoding="utf-8", errors="replace") if research_path.is_file() else ""
    research_term_groups = (
        ("n8n",),
        ("Qdrant",),
        ("Neo4j",),
        ("Redis",),
        ("PostgreSQL", "Postgres"),
        ("Prometheus",),
        ("cAdvisor",),
        ("llama.cpp",),
        ("Reddit", "reddit", "Self-hosting operator discussion"),
    )
    research_ok = all(any(term in research_text for term in group) for group in research_term_groups)
    check(
        checks,
        "research_packet",
        "Current upstream, field, and forum research is captured for the selected service families.",
        "done" if research_ok else "missing",
        str(research_path),
        details={"required_term_groups": [list(group) for group in research_term_groups]},
    )

    missing_overlays = [overlay for overlay in EXPECTED_OVERLAYS if not (configs_root / overlay).is_file()]
    check(
        checks,
        "resource_guard_overlays",
        "Selected services have source-managed resource guard overlays.",
        "done" if not missing_overlays else "missing",
        ", ".join(EXPECTED_OVERLAYS),
        details={"missing_overlays": missing_overlays},
    )

    unit_overlays = [part for part in env.get("AOA_EXTRA_COMPOSE_FILES", "").split(",") if part]
    selection_ok = (
        env.get("AOA_STACK_PRESET") == "intel-full"
        and {"federation", "reranking"}.issubset({part for part in env.get("AOA_STACK_PROFILE", "").split(",") if part})
        and set(EXPECTED_OVERLAYS).issubset(set(unit_overlays))
    )
    check(
        checks,
        "host_selection_persisted",
        "The live user unit carries the intended preset, profiles, and resource overlays.",
        "done" if selection_ok else "missing",
        "systemctl --user show podman-compose-abyss.service -p Environment",
        details={
            "preset": env.get("AOA_STACK_PRESET", ""),
            "profile": env.get("AOA_STACK_PROFILE", ""),
            "extra_compose_files": unit_overlays,
        },
    )

    parity = source_runtime_parity(configs_root)
    check(
        checks,
        "source_runtime_parity",
        "The source checkout and deployed Configs mirror match for source-managed runtime surfaces.",
        str(parity["status"]),
        " ".join(str(part) for part in parity["command"]),
        details=parity,
    )

    service_selection, service_error = run_json([str(SCRIPTS_DIR / "aoa-status"), "--service-selection", "--json"])
    service_summary = service_selection.get("summary", {}) if service_selection else {}
    service_ok = service_summary.get("status") == "ok"
    check(
        checks,
        "live_service_selection",
        "Live containers match the service-selection policy.",
        "done" if service_ok else "blocked",
        "scripts/aoa-status --service-selection --json" if not service_error else service_error,
        details=service_summary,
    )

    resource_guards, resource_error = run_json([str(SCRIPTS_DIR / "aoa-status"), "--resource-guards", "--json"])
    guard_summary = resource_guards.get("summary", {}) if resource_guards else {}
    guard_status = guard_summary.get("status")
    if guard_status == "applied":
        guard_check_status = "done"
    elif guard_status == "staged_not_applied":
        guard_check_status = "blocked"
    else:
        guard_check_status = "missing"
    check(
        checks,
        "live_resource_guards",
        "Live cgroup state matches the staged resource guard overlays.",
        guard_check_status,
        "scripts/aoa-status --resource-guards --json" if not resource_error else resource_error,
        details=guard_summary,
    )

    game_guard, game_error = run_json(["abyss-machine", "processes", "game-guard", "--json"])
    game_active = game_guard.get("active") if game_guard else None
    check(
        checks,
        "safe_apply_window",
        "Resource guard apply is allowed only when game guard is clear or the operator explicitly forces it.",
        "done" if game_active is False else "blocked",
        "abyss-machine processes game-guard --json" if not game_error else game_error,
        details={"active": game_active, "summary": game_guard.get("summary", {}) if game_guard else {}},
    )

    apply_script = configs_root / "mechanics" / "runtime-lifecycle" / "parts" / "start-stop" / "aoa_apply_resource_guards.sh"
    apply_text = apply_script.read_text(encoding="utf-8", errors="replace") if apply_script.is_file() else ""
    apply_ok = all(token in apply_text for token in ("--dry-run", "--force", "--wait-game-guard-clear", "--wait-resource-plan-clear", "resource plan", "AOA_UP_FORCE_RECREATE", "post-apply.json", "game-guard"))
    check(
        checks,
        "guarded_apply_route",
        "The apply route records evidence, gates on game guard, and recreates containers for cgroup changes by default.",
        "done" if apply_ok else "missing",
        str(apply_script),
        details={"required_tokens": ["--dry-run", "--force", "--wait-game-guard-clear", "--wait-resource-plan-clear", "resource plan", "AOA_UP_FORCE_RECREATE", "post-apply.json", "game-guard"]},
    )

    resource_plan_gate_ok = all(
        token in apply_text
        for token in (
            "abyss-machine resource plan --class medium --kind generic --unattended --json",
            "--wait-resource-plan-clear",
            "pre-resource-plan.json",
            "post-resource-plan.json",
        )
    )
    check(
        checks,
        "resource_plan_apply_gate",
        "Non-forced apply checks the host resource plan so background memory, storage, thermal, or process load can block or delay live mutation.",
        "done" if resource_plan_gate_ok else "missing",
        str(apply_script),
        details={
            "required_tokens": [
                "abyss-machine resource plan --class medium --kind generic --unattended --json",
                "--wait-resource-plan-clear",
                "pre-resource-plan.json",
                "post-resource-plan.json",
            ]
        },
    )

    apply_unit = configs_root / "systemd" / "user" / "abyss-stack-resource-guards-apply.service"
    apply_unit_text = apply_unit.read_text(encoding="utf-8", errors="replace") if apply_unit.is_file() else ""
    apply_unit_link = Path.home() / ".config" / "systemd" / "user" / "abyss-stack-resource-guards-apply.service"
    try:
        apply_unit_link_target = str(apply_unit_link.resolve()) if apply_unit_link.exists() else ""
    except OSError:
        apply_unit_link_target = ""
    apply_unit_linked = apply_unit_link_target == str(apply_unit)
    apply_unit_ok = all(token in apply_unit_text for token in ("Type=oneshot", "--wait-game-guard-clear", "--wait-resource-plan-clear", "TimeoutStartSec=75min")) and apply_unit_linked
    check(
        checks,
        "safe_window_apply_unit",
        "A manual user one-shot unit can run the guarded wait/apply route outside the current shell session.",
        "done" if apply_unit_ok else "missing",
        str(apply_unit),
        details={
            "required_tokens": ["Type=oneshot", "--wait-game-guard-clear", "--wait-resource-plan-clear", "TimeoutStartSec=75min"],
            "user_unit_link": str(apply_unit_link),
            "user_unit_link_target": apply_unit_link_target,
            "linked_to_configs": apply_unit_linked,
        },
    )

    unit_states = protected_unit_state()
    protected_ok = all(state == "active" for state in unit_states.values())
    check(
        checks,
        "protected_host_capabilities",
        "Host TTS, dictation, TTS keep-warm, and stack user unit remain active.",
        "done" if protected_ok else "blocked",
        "systemctl --user is-active " + " ".join(PROTECTED_UNITS),
        details=unit_states,
    )

    post_evidence = post_apply_evidence(stack_root)
    post_ok = (
        guard_status == "applied"
        and len(post_evidence["existing_files"]) == len(post_evidence["required_files"])
        and post_evidence["post_guard_status"] == "applied"
        and post_evidence["post_service_selection_status"] == "ok"
        and post_evidence["post_protected_units_active"]
    )
    check(
        checks,
        "post_apply_evidence",
        "Post-apply guard, service-selection, protected-unit, podman stats, and memory evidence exists for the tuned live state.",
        "done" if post_ok else "blocked",
        post_evidence["latest_dir"],
        details=post_evidence,
    )

    status_counts: dict[str, int] = {}
    for item in checks:
        status = str(item["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    required_checks = [item for item in checks if item["required_for_completion"]]
    completion_ready = all(item["status"] == "done" for item in required_checks)
    if completion_ready:
        overall = "complete"
        next_action = "objective complete; no resource-guard apply needed"
    elif status_counts.get("missing"):
        overall = "incomplete"
        next_action = "inspect missing audit checks"
    elif status_counts.get("blocked"):
        overall = "blocked"
        next_action = "run scripts/aoa-apply-resource-guards --wait-game-guard-clear --wait-resource-plan-clear for supervised safe-window apply, or run scripts/aoa-apply-resource-guards after game guard and resource plan clear"
    else:
        overall = "incomplete"
        next_action = "inspect missing audit checks"

    return {
        "surface_type": "service_optimization_completion_audit",
        "schema_version": "v1",
        "objective": {
            "source_screenshot": "/home/dionysus/\u0418\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f/\u0421\u043d\u0438\u043c\u043a\u0438 \u044d\u043a\u0440\u0430\u043d\u0430/\u0421\u043d\u0438\u043c\u043e\u043a \u044d\u043a\u0440\u0430\u043d\u0430 \u043e\u0442 2026-05-14 21-46-49.png",
            "success_criteria": [
                "technical debt fixed through source-managed overlay persistence",
                "screenshot services classified and covered by policy",
                "current research packet informs tuning decisions",
                "resource guards staged through source and deployed Configs",
                "source checkout and deployed Configs mirror remain in parity",
                "live service selection remains healthy",
                "live cgroup state is applied",
                "protected host TTS and dictation remain active",
                "post-apply evidence exists",
            ],
        },
        "summary": {
            "status": overall,
            "completion_ready": completion_ready,
            "checks": len(checks),
            "done": status_counts.get("done", 0),
            "blocked": status_counts.get("blocked", 0),
            "missing": status_counts.get("missing", 0),
            "failed": status_counts.get("failed", 0),
            "next_action": next_action,
        },
        "checks": checks,
    }


def print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print(f"optimization audit: {summary['status']}")
    print(f"completion ready: {summary['completion_ready']}")
    print(
        "checks: done={done} blocked={blocked} missing={missing} failed={failed} total={checks}".format(
            **summary
        )
    )
    print(f"next: {summary['next_action']}")
    print("")
    for item in payload["checks"]:
        print(f"- {item['id']}: {item['status']} - {item['requirement']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit service optimization objective completion against live evidence.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--require-complete", action="store_true", help="Exit non-zero unless all required objective checks are done.")
    args = parser.parse_args(argv)

    try:
        payload = build_audit()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    if args.require_complete and not payload.get("summary", {}).get("completion_ready"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
