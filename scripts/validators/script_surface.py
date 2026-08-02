"""Operator script surface validation for abyss-stack."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping, Set
from pathlib import Path


ExecutableCheck = Callable[[Path], bool]
GitIndexMode = Callable[[Path], str | None]

REQUIRED_SCRIPTS = {
    "aoa-agent-os-runtime",
    "aoa-diagnose",
    "aoa-governed-run",
    "aoa-doctor",
    "aoa-external-codex-agent",
    "aoa-host-facts",
    "aoa-machine-bridge",
    "aoa-machine-fit",
    "aoa-platform-adaptation",
    "aoa-local-ai-trials",
    "aoa-tos-foundation-lab",
    "aoa-langgraph-pilot",
    "aoa-long-horizon-pilot",
    "aoa-bounded-autonomy-pilot",
    "aoa-llamacpp-pilot",
    "aoa-runtime-bench-index",
    "aoa-kag-runtime-family",
    "aoa-kag-runtime-projection",
    "aoa-rpg-runtime-projection",
    "aoa-tos-graph",
    "aoa-qwen-check",
    "aoa-federated-check",
    "aoa-qwen-run",
    "aoa-qwen-bench",
    "aoa-export-memo-candidate",
    "aoa-export-runtime-evidence-selection",
    "aoa-export-artifact-hook-candidate",
    "aoa-a2a-return-closeout-dry-run",
    "aoa-run-memo-contradiction-integrity",
    "aoa-install-layout",
    "aoa-sync-configs",
    "aoa-sync-federation-surfaces",
    "aoa-routing-canary",
    "aoa-routing-cutover",
    "aoa-bootstrap-configs",
    "aoa-check-layout",
    "aoa-warmup",
    "aoa-install-systemd",
    "aoa-first-run",
    "aoa-preset-profiles",
    "aoa-profile-modules",
    "aoa-profile-endpoints",
    "aoa-internal-probes",
    "aoa-render-services",
    "aoa-render-config",
    "aoa-up",
    "aoa-down",
    "aoa-apply-resource-guards",
    "aoa-status",
    "aoa-logs",
    "aoa-smoke",
    "aoa-wait",
    "aoa.ps1",
    "aoa-doctor-win.ps1",
    "aoa-bootstrap-wsl.ps1",
    "tos-up",
}

OPERATOR_BACKEND_SCRIPTS = {
    "aoa-a2a-return-closeout-dry-run": "mechanics/runtime-repair/parts/a2a-return-dry-run/aoa_a2a_return_closeout_dry_run.py",
    "aoa-agent-os-runtime": "mechanics/governed-execution/parts/agent-os-adapter/aoa_agent_os_runtime.py",
    "aoa-bootstrap-configs": "mechanics/config-projection/parts/bootstrap/aoa_bootstrap_configs.sh",
    "aoa-bootstrap-wsl.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_bootstrap_wsl.ps1",
    "aoa-bounded-autonomy-pilot": "mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_bounded_autonomy_pilot.sh",
    "aoa-sync-configs": "mechanics/config-projection/parts/sync/aoa_sync_configs.sh",
    "aoa-sync-federation-surfaces": "mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh",
    "aoa-routing-canary": "mechanics/federation-seams/parts/sync-wrapper/aoa_routing_canary.py",
    "aoa-routing-cutover": "mechanics/federation-seams/parts/sync-wrapper/aoa_routing_cutover.py",
    "aoa-preset-profiles": "mechanics/config-projection/parts/rendering/aoa_preset_profiles.sh",
    "aoa-profile-modules": "mechanics/config-projection/parts/rendering/aoa_profile_modules.sh",
    "aoa-profile-endpoints": "mechanics/config-projection/parts/rendering/aoa_profile_endpoints.sh",
    "aoa-render-services": "mechanics/config-projection/parts/rendering/aoa_render_services.sh",
    "aoa-render-config": "mechanics/config-projection/parts/rendering/aoa_render_config.sh",
    "aoa-diagnose": "mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh",
    "aoa-doctor": "mechanics/diagnostic-spine/parts/doctor-readiness/aoa_doctor.sh",
    "aoa-doctor-win.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_doctor_win.ps1",
    "aoa-export-artifact-hook-candidate": "mechanics/governed-execution/parts/candidate-exports/aoa_export_artifact_hook_candidate.py",
    "aoa-export-memo-candidate": "mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py",
    "aoa-export-runtime-evidence-selection": "mechanics/governed-execution/parts/candidate-exports/aoa_export_runtime_evidence_selection.py",
    "aoa-external-codex-agent": "mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py",
    "aoa-federated-check": "mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py",
    "aoa-install-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_install_layout.sh",
    "aoa-check-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
    "aoa-first-run": "mechanics/runtime-lifecycle/parts/first-run-bootstrap/aoa_first_run.sh",
    "aoa-governed-run": "mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py",
    "aoa-host-facts": "mechanics/machine-fit/parts/host-facts/aoa_host_facts.py",
    "aoa-install-systemd": "mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh",
    "aoa-internal-probes": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_internal_probes.sh",
    "aoa-langgraph-pilot": "mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py",
    "aoa-llamacpp-pilot": "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py",
    "aoa-local-ai-trials": "mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py",
    "aoa-tos-foundation-lab": "mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py",
    "aoa-long-horizon-pilot": "mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_long_horizon_pilot.sh",
    "aoa-machine-bridge": "mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py",
    "aoa-machine-fit": "mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py",
    "aoa-apply-resource-guards": "mechanics/runtime-lifecycle/parts/start-stop/aoa_apply_resource_guards.sh",
    "aoa-up": "mechanics/runtime-lifecycle/parts/start-stop/aoa_up.sh",
    "aoa-down": "mechanics/runtime-lifecycle/parts/start-stop/aoa_down.sh",
    "aoa-platform-adaptation": "mechanics/machine-fit/parts/platform-adaptations/aoa_platform_adaptation.py",
    "aoa-qwen-bench": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_bench.sh",
    "aoa-qwen-check": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_check.py",
    "aoa-qwen-run": "mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py",
    "aoa-kag-runtime-family": "mechanics/federation-seams/parts/kag-seam/aoa_kag_runtime_family.py",
    "aoa-kag-runtime-projection": "mechanics/federation-seams/parts/kag-seam/aoa_kag_runtime_projection.py",
    "aoa-rpg-runtime-projection": "mechanics/federation-seams/parts/rpg-runtime/aoa_rpg_runtime_projection.py",
    "aoa-tos-graph": "mechanics/federation-seams/parts/tos-graph/aoa_tos_graph.sh",
    "aoa-run-memo-contradiction-integrity": "mechanics/runtime-repair/parts/memo-contradiction-sidecar/aoa_memo_contradiction_integrity.py",
    "aoa-runtime-bench-index": "mechanics/inference-pilots/parts/promotion-loop/aoa_runtime_bench_index.py",
    "aoa-warmup": "mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh",
    "aoa-wait": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_wait.sh",
    "aoa-smoke": "mechanics/runtime-lifecycle/parts/wait-smoke/aoa_smoke.sh",
    "aoa-logs": "mechanics/runtime-lifecycle/parts/logs-status/aoa_logs.sh",
    "aoa-status": "mechanics/runtime-lifecycle/parts/logs-status/aoa_status.sh",
    "aoa.ps1": "mechanics/machine-fit/parts/windows-bridge/aoa_windows_bridge.ps1",
    "tos-up": "mechanics/federation-seams/parts/tos-graph/tos_up.sh",
}


def git_index_mode(path: Path, root: Path) -> str | None:
    try:
        rel_path = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None

    completed = subprocess.run(
        ["git", "ls-files", "--stage", "--", rel_path],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None

    first_line = completed.stdout.strip().splitlines()
    if not first_line:
        return None
    fields = first_line[0].split()
    if not fields:
        return None
    return fields[0]


def is_executable_source_path(
    path: Path,
    root: Path,
    *,
    git_index_mode_func: GitIndexMode | None = None,
) -> bool:
    if path.stat().st_mode & 0o111:
        return True
    mode_lookup = git_index_mode_func or (lambda candidate: git_index_mode(candidate, root))
    return mode_lookup(path) == "100755"


def validate_scripts(
    errors: list[str],
    *,
    root: Path,
    required_scripts: Set[str],
    operator_backend_scripts: Mapping[str, str],
    executable_source_path_func: ExecutableCheck | None = None,
) -> None:
    script_names = {path.name for path in (root / "scripts").iterdir() if path.is_file()}
    missing = sorted(required_scripts - script_names)
    missing_backend_routes = sorted(required_scripts - set(operator_backend_scripts))
    extra_backend_routes = sorted(set(operator_backend_scripts) - required_scripts)
    executable_check = executable_source_path_func or (
        lambda candidate: is_executable_source_path(candidate, root)
    )

    for name in missing:
        errors.append(f"missing required script: scripts/{name}")
    for name in missing_backend_routes:
        errors.append(f"missing operator backend route for required script: scripts/{name}")
    for name in extra_backend_routes:
        errors.append(f"operator backend route is not a required script: scripts/{name}")

    for script_name, backend_rel in sorted(operator_backend_scripts.items()):
        backend_path = root / backend_rel
        if not backend_path.is_file():
            errors.append(f"missing operator backend for scripts/{script_name}: {backend_rel}")
            continue
        if backend_path.suffix.lower() != ".ps1" and not executable_check(backend_path):
            errors.append(f"operator backend is not executable: {backend_rel}")

        wrapper_path = root / "scripts" / script_name
        if wrapper_path.exists():
            wrapper_text = wrapper_path.read_text(encoding="utf-8")
            if f"../{backend_rel}" not in wrapper_text:
                errors.append(f"scripts/{script_name} must exec ../{backend_rel}")

    llamacpp_pilot = (root / operator_backend_scripts["aoa-llamacpp-pilot"]).read_text(
        encoding="utf-8"
    )
    if "podman\", \"network\", \"connect\"" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must connect the sidecar to the primary runtime network")
    if "abyss_default" not in llamacpp_pilot:
        errors.append("scripts/aoa-llamacpp-pilot must mention abyss_default as the primary runtime network")

    install_systemd_rel = operator_backend_scripts.get("aoa-install-systemd")
    if install_systemd_rel:
        install_systemd_path = root / install_systemd_rel
        if install_systemd_path.is_file():
            install_systemd = install_systemd_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--preset",
                "--profile",
                "--overlay",
                "--restart-now",
                "--all-user-units",
                "--system-units",
                "AOA_EXTRA_COMPOSE_FILES",
                "managed-units.txt",
                "systemctl daemon-reload",
                "20-runtime-selection.conf",
                "aoa_validate_runtime_spec",
                "aoa_validate_overlay_spec",
                "aoa_append_runtime_spec",
            ):
                if required_snippet not in install_systemd:
                    errors.append(
                        f"scripts/aoa-install-systemd must preserve user-unit runtime selection via `{required_snippet}`"
                    )

    apply_resource_guards_rel = operator_backend_scripts.get("aoa-apply-resource-guards")
    if apply_resource_guards_rel:
        apply_resource_guards_path = root / apply_resource_guards_rel
        if apply_resource_guards_path.is_file():
            apply_resource_guards = apply_resource_guards_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--dry-run",
                "--force",
                "--wait-game-guard-clear",
                "--wait-resource-plan-clear",
                "--wait-timeout-sec",
                "--wait-poll-sec",
                "resource plan",
                "resource plan --class medium --kind generic --unattended --json",
                "--method",
                "recreate",
                "AOA_UP_FORCE_RECREATE",
                "set-environment",
                "aoa-status\" --resource-guards --json",
                "abyss-machine processes game-guard --json",
                "systemctl --user \"$method\" podman-compose-abyss.service",
                "post-apply.json",
                "pre-service-selection.json",
                "post-service-selection.json",
                "pre-resource-plan.json",
                "post-resource-plan.json",
                "pre-podman-stats.txt",
                "post-podman-stats.txt",
                "pre-memory.txt",
                "post-memory.txt",
                "pre-protected-units.txt",
                "post-protected-units.txt",
                "protected user units degraded after apply",
                "abyss-tts-server.service",
                "abyss-dictation-server.service",
                "abyss-tts-keepwarm.timer",
                "podman stats --no-stream",
                "service selection degraded after apply",
                "resource guards still not fully applied",
            ):
                if required_snippet not in apply_resource_guards:
                    errors.append(
                        f"scripts/aoa-apply-resource-guards must preserve guarded apply behavior via `{required_snippet}`"
                    )

    aoa_up_rel = operator_backend_scripts.get("aoa-up")
    if aoa_up_rel:
        aoa_up_path = root / aoa_up_rel
        if aoa_up_path.is_file():
            aoa_up = aoa_up_path.read_text(encoding="utf-8")
            for required_snippet in (
                "AOA_UP_FORCE_RECREATE",
                "--force-recreate",
            ):
                if required_snippet not in aoa_up:
                    errors.append(
                        f"scripts/aoa-up must preserve force-recreate support via `{required_snippet}`"
                    )

    status_rel = operator_backend_scripts.get("aoa-status")
    if status_rel:
        status_path = root / status_rel
        if status_path.is_file():
            status_script = status_path.read_text(encoding="utf-8")
            for required_snippet in (
                "--resource-guards",
                "--service-selection",
                "--optimization",
                "--optimization-audit",
                "--require-complete",
                "aoa_resource_guard_status.py",
                "aoa_service_selection_status.py",
                "aoa_optimization_status.py",
                "aoa_optimization_audit_status.py",
            ):
                if required_snippet not in status_script:
                    errors.append(
                        f"scripts/aoa-status must preserve runtime status modes via `{required_snippet}`"
                    )
