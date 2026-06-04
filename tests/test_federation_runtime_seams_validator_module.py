from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.validators import federation_runtime_seams


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload))


def test_memo_runtime_seam_requires_exporter_identity(tmp_path: Path) -> None:
    write_text(tmp_path / "docs" / "operations" / "RUNBOOK.md", "aoa-export-memo-candidate\n")
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "memo-seam"
        / "docs"
        / "MEMO_RUNTIME_SEAM.md",
        "aoa-memo\n/memo/\naoa-export-memo-candidate\nLogs/memo-exports/\n",
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "schemas"
        / "runtime-memo-export-candidate.schema.json",
        {"title": "abyss-stack runtime memo export candidate"},
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "examples"
        / "runtime_memo_export_candidate.checkpoint_export.example.json",
        {
            "artifact_kind": "aoa.runtime-memo-export-candidate",
            "exported_by": "scripts/wrong-exporter",
        },
    )

    errors: list[str] = []
    federation_runtime_seams.validate_memo_runtime_seam(errors, root=tmp_path)

    assert "runtime memo export example must use exported_by scripts/aoa-export-memo-candidate" in errors


def test_eval_runtime_seam_requires_a2a_dry_run_true(tmp_path: Path) -> None:
    write_text(
        tmp_path / "docs" / "operations" / "RUNBOOK.md",
        "\n".join(
            [
                "aoa-export-runtime-evidence-selection",
                "aoa-export-artifact-hook-candidate",
                "aoa-run-memo-contradiction-integrity",
                "aoa-a2a-return-closeout-dry-run",
            ]
        ),
    )
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "eval-seam"
        / "docs"
        / "EVAL_RUNTIME_SEAM.md",
        "\n".join(
            [
                "aoa-evals",
                "/evals/",
                "aoa-export-runtime-evidence-selection",
                "aoa-export-artifact-hook-candidate",
                "aoa-a2a-return-closeout-dry-run",
                "aoa-run-memo-contradiction-integrity",
                "Logs/eval-exports/",
                "Logs/a2a-return-closeouts/",
            ]
        ),
    )
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md",
        "single active bridge\nlegacy/upstream-compatibility/INDEX.md\nupstream-compatibility-bridge.json\nClean local route\n",
    )
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "legacy"
        / "upstream-compatibility"
        / "INDEX.md",
        "phase-alpha-id\n",
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "schemas"
        / "runtime-eval-evidence-selection-candidate.schema.json",
        {"title": "abyss-stack runtime eval evidence selection candidate"},
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "examples"
        / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json",
        {
            "artifact_kind": "aoa.runtime-eval-evidence-selection-candidate",
            "exported_by": "scripts/aoa-export-runtime-evidence-selection",
        },
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "schemas"
        / "runtime-artifact-hook-candidate.schema.json",
        {"title": "abyss-stack runtime artifact hook candidate"},
    )
    write_json(
        tmp_path
        / "mechanics"
        / "governed-execution"
        / "parts"
        / "candidate-exports"
        / "examples"
        / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json",
        {
            "artifact_kind": "aoa.runtime-artifact-hook-candidate",
            "exported_by": "scripts/aoa-export-artifact-hook-candidate",
        },
    )
    write_text(
        tmp_path
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "docs"
        / "A2A_RETURN_DRY_RUN.md",
        "aoa-a2a-return-closeout-dry-run\nrequest_family\nupstream_request_kind\nUPSTREAM_COMPATIBILITY.md\ndry_run\nlive_automation\nLogs/a2a-return-closeouts/\n",
    )
    write_json(
        tmp_path
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "schemas"
        / "runtime-a2a-return-closeout-dry-run.schema.json",
        {"title": "abyss-stack runtime A2A return closeout dry-run"},
    )
    write_json(
        tmp_path
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "examples"
        / "runtime_a2a_return_closeout_dry_run.example.json",
        {
            "artifact_kind": "aoa.runtime-a2a-return-closeout-dry-run",
            "exported_by": "scripts/aoa-a2a-return-closeout-dry-run",
            "dry_run": False,
            "live_automation": False,
            "request_family": "a2a-return-closeout",
            "request_kind": "a2a-return-closeout-request",
            "upstream_request_kind": "UPSTREAM_COMPATIBILITY_BRIDGE.a2a_return_closeout.upstream_request_kind",
        },
    )

    errors: list[str] = []
    federation_runtime_seams.validate_eval_runtime_seam(
        errors,
        root=tmp_path,
        bridge_config_loader=lambda current_errors: {},
        bridge_string_iterator=lambda payload: [],
    )

    assert "runtime A2A return closeout dry-run example must set dry_run true" in errors


def test_kag_runtime_seam_requires_runbook_advisory_route(tmp_path: Path) -> None:
    write_text(tmp_path / "docs" / "operations" / "RUNBOOK.md", "no kag route here\n")
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "kag-seam"
        / "docs"
        / "KAG_RUNTIME_SEAM.md",
        "\n".join(
            [
                "aoa-kag",
                "tos-source",
                "/kag/",
                "Tree-of-Sophia",
                "advisory-only",
                "aoa-sync-federation-surfaces --layer aoa-kag",
                "aoa-sync-federation-surfaces --layer tos-source",
            ]
        ),
    )

    errors: list[str] = []
    federation_runtime_seams.validate_kag_runtime_seam(errors, root=tmp_path)

    assert "docs/operations/RUNBOOK.md must mention KAG advisory seam inspection" in errors
