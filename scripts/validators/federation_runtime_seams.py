from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from typing import Any

BridgeConfigLoader = Callable[[list[str]], dict[str, Any]]
BridgeStringIterator = Callable[[Any], list[str]]


def validate_memo_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-memo-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-memo-candidate")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "memo-seam"
        / "docs"
        / "MEMO_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-memo",
        "/memo/",
        "aoa-export-memo-candidate",
        "Logs/memo-exports/",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md must mention {snippet}")

    schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-memo-export-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if schema.get("title") != "abyss-stack runtime memo export candidate":
        errors.append("runtime-memo-export-candidate.schema.json must describe abyss-stack runtime memo export candidate")

    example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_memo_export_candidate.checkpoint_export.example.json"
        ).read_text(encoding="utf-8")
    )
    if example.get("artifact_kind") != "aoa.runtime-memo-export-candidate":
        errors.append("runtime memo export example must use artifact_kind aoa.runtime-memo-export-candidate")
    if example.get("exported_by") != "scripts/aoa-export-memo-candidate":
        errors.append("runtime memo export example must use exported_by scripts/aoa-export-memo-candidate")


def validate_eval_runtime_seam(
    errors: list[str],
    *,
    root: Path,
    bridge_config_loader: BridgeConfigLoader,
    bridge_string_iterator: BridgeStringIterator,
) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-runtime-evidence-selection" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-runtime-evidence-selection")
    if "aoa-export-artifact-hook-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-artifact-hook-candidate")
    if "aoa-run-memo-contradiction-integrity" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-run-memo-contradiction-integrity")
    if "aoa-a2a-return-closeout-dry-run" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-a2a-return-closeout-dry-run")

    _validate_eval_seam_doc(errors, root=root)
    _validate_eval_upstream_compatibility(
        errors,
        root=root,
        bridge_config_loader=bridge_config_loader,
        bridge_string_iterator=bridge_string_iterator,
    )
    _validate_eval_candidate_exports(errors, root=root)
    _validate_a2a_return_dry_run(errors, root=root)


def _validate_eval_seam_doc(errors: list[str], *, root: Path) -> None:
    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "eval-seam"
        / "docs"
        / "EVAL_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-evals",
        "/evals/",
        "aoa-export-runtime-evidence-selection",
        "aoa-export-artifact-hook-candidate",
        "aoa-a2a-return-closeout-dry-run",
        "aoa-run-memo-contradiction-integrity",
        "Logs/eval-exports/",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md must mention {snippet}")


def _validate_eval_upstream_compatibility(
    errors: list[str],
    *,
    root: Path,
    bridge_config_loader: BridgeConfigLoader,
    bridge_string_iterator: BridgeStringIterator,
) -> None:
    compatibility_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md"
    ).read_text(encoding="utf-8")
    compatibility_legacy_index = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "legacy"
        / "upstream-compatibility"
        / "INDEX.md"
    ).read_text(encoding="utf-8")
    bridge_config = bridge_config_loader(errors)
    bridge_strings = bridge_string_iterator(bridge_config)
    for snippet in (
        "single active bridge",
        "legacy/upstream-compatibility/INDEX.md",
        "upstream-compatibility-bridge.json",
        "Clean local route",
    ):
        if snippet not in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must keep the lightweight active bridge and mention {snippet}"
            )
    for bridge_value in bridge_strings:
        is_legacy_value = any(
            marker in bridge_value for marker in ("phase-alpha", "a2a_wave", "playbook_automation_seeds", "seed_staging")
        )
        if is_legacy_value and bridge_value in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must route detailed legacy value {bridge_value} through legacy/upstream-compatibility/INDEX.md"
            )
        if is_legacy_value and bridge_value not in compatibility_legacy_index:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md "
                f"must mention {bridge_value}"
            )


def _validate_eval_candidate_exports(errors: list[str], *, root: Path) -> None:
    evidence_schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-eval-evidence-selection-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if evidence_schema.get("title") != "abyss-stack runtime eval evidence selection candidate":
        errors.append(
            "runtime-eval-evidence-selection-candidate.schema.json must describe abyss-stack runtime eval evidence selection candidate"
        )

    evidence_example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json"
        ).read_text(encoding="utf-8")
    )
    if evidence_example.get("artifact_kind") != "aoa.runtime-eval-evidence-selection-candidate":
        errors.append(
            "runtime eval evidence selection example must use artifact_kind aoa.runtime-eval-evidence-selection-candidate"
        )
    if evidence_example.get("exported_by") != "scripts/aoa-export-runtime-evidence-selection":
        errors.append(
            "runtime eval evidence selection example must use exported_by scripts/aoa-export-runtime-evidence-selection"
        )

    hook_schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-artifact-hook-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if hook_schema.get("title") != "abyss-stack runtime artifact hook candidate":
        errors.append("runtime-artifact-hook-candidate.schema.json must describe abyss-stack runtime artifact hook candidate")

    hook_example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json"
        ).read_text(encoding="utf-8")
    )
    if hook_example.get("artifact_kind") != "aoa.runtime-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use artifact_kind aoa.runtime-artifact-hook-candidate")
    if hook_example.get("exported_by") != "scripts/aoa-export-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use exported_by scripts/aoa-export-artifact-hook-candidate")


def _validate_a2a_return_dry_run(errors: list[str], *, root: Path) -> None:
    a2a_doc = (
        root
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "docs"
        / "A2A_RETURN_DRY_RUN.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-a2a-return-closeout-dry-run",
        "request_family",
        "upstream_request_kind",
        "UPSTREAM_COMPATIBILITY.md",
        "dry_run",
        "live_automation",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in a2a_doc:
            errors.append(f"mechanics/runtime-repair/parts/a2a-return-dry-run/docs/A2A_RETURN_DRY_RUN.md must mention {snippet}")

    a2a_schema = json.loads(
        (
            root
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "schemas"
            / "runtime-a2a-return-closeout-dry-run.schema.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_schema.get("title") != "abyss-stack runtime A2A return closeout dry-run":
        errors.append(
            "runtime-a2a-return-closeout-dry-run.schema.json must describe abyss-stack runtime A2A return closeout dry-run"
        )

    a2a_example = json.loads(
        (
            root
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "examples"
            / "runtime_a2a_return_closeout_dry_run.example.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_example.get("artifact_kind") != "aoa.runtime-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use artifact_kind aoa.runtime-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("exported_by") != "scripts/aoa-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use exported_by scripts/aoa-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("dry_run") is not True:
        errors.append("runtime A2A return closeout dry-run example must set dry_run true")
    if a2a_example.get("live_automation") is not False:
        errors.append("runtime A2A return closeout dry-run example must set live_automation false")
    if a2a_example.get("request_family") != "a2a-return-closeout":
        errors.append("runtime A2A return closeout dry-run example must set request_family a2a-return-closeout")
    if a2a_example.get("request_kind") != "a2a-return-closeout-request":
        errors.append("runtime A2A return closeout dry-run example must set clean request_kind")
    if "UPSTREAM_COMPATIBILITY_BRIDGE.a2a_return_closeout.upstream_request_kind" not in str(
        a2a_example.get("upstream_request_kind", "")
    ):
        errors.append("runtime A2A return closeout dry-run example must route upstream_request_kind through the bridge")


def validate_playbook_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "playbooks/activation" not in runbook_doc and "/playbooks/" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention playbook advisory seam inspection")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "playbook-seam"
        / "docs"
        / "PLAYBOOK_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-playbooks",
        "/playbooks/",
        "PLAYBOOK.md",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-playbooks",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md must mention {snippet}")


def validate_kag_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "/kag/" not in runbook_doc and "kag/registry" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention KAG advisory seam inspection")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "kag-seam"
        / "docs"
        / "KAG_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-kag",
        "tos-source",
        "/kag/",
        "Tree-of-Sophia",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-kag",
        "aoa-sync-federation-surfaces --layer tos-source",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md must mention {snippet}")
