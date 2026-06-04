from __future__ import annotations

import json
from pathlib import Path

from scripts.validators import federation_surface


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_iter_compatibility_bridge_strings_flattens_nested_values() -> None:
    payload = {
        "a": "one",
        "b": ["two", {"c": "three"}],
        "ignored": 7,
    }

    assert federation_surface.iter_compatibility_bridge_strings(payload) == [
        "one",
        "two",
        "three",
    ]


def test_federation_required_files_requires_runtime_template_fields(tmp_path: Path) -> None:
    config_path = Path("config-templates") / "Configs" / "federation" / "aoa-evals.yaml"
    bridge_path = tmp_path / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json"
    (tmp_path / config_path).parent.mkdir(parents=True)
    (tmp_path / config_path).write_text(
        "required_files:\n  - generated/runtime_candidate_template_index.min.json\n",
        encoding="utf-8",
    )
    bridge_path.write_text(
        json.dumps(
            {
                "artifact_kind": "abyss-stack.upstream-compatibility-bridge",
                "runtime_evidence_templates": {
                    "memo-recall-rerun": {
                        "canonical_selection_id": "memo-recall-rerun",
                    },
                    "memo-contradiction-gap": {
                        "canonical_selection_id": "memo-contradiction-gap",
                        "local_source_ref": "local",
                        "upstream_source_ref": "upstream",
                        "upstream_selection_id": "upstream-id",
                    },
                    "memo-contradiction-rerun": {
                        "canonical_selection_id": "memo-contradiction-rerun",
                        "local_source_ref": "local",
                        "upstream_source_ref": "upstream",
                        "upstream_selection_id": "upstream-id",
                    },
                },
                "playbook_automation_plans": {
                    "upstream_rel_path": "automation-plans",
                },
            }
        ),
        encoding="utf-8",
    )

    errors: list[str] = []
    federation_surface.validate_federation_required_files(
        errors,
        root=tmp_path,
        required_runtime_inputs={
            config_path: {"generated/runtime_candidate_template_index.min.json"}
        },
        bridge_path=bridge_path,
        load_structured_object_func=lambda path: {
            "required_files": [
                "generated/runtime_candidate_template_index.min.json"
            ]
        },
    )

    assert (
        "upstream compatibility bridge runtime template memo-recall-rerun must include local_source_ref"
        in errors
    )


def test_federation_required_files_requires_playbook_automation_bridge_fields(tmp_path: Path) -> None:
    bridge_path = tmp_path / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json"
    write_text(
        bridge_path,
        json.dumps(
            {
                "artifact_kind": "abyss-stack.upstream-compatibility-bridge",
                "runtime_evidence_templates": {
                    "memo-recall-rerun": {
                        "canonical_selection_id": "memo-recall-rerun",
                        "local_source_ref": "local",
                        "upstream_source_ref": "upstream",
                        "upstream_selection_id": "upstream-id",
                    },
                    "memo-contradiction-gap": {
                        "canonical_selection_id": "memo-contradiction-gap",
                        "local_source_ref": "local",
                        "upstream_source_ref": "upstream",
                        "upstream_selection_id": "upstream-id",
                    },
                    "memo-contradiction-rerun": {
                        "canonical_selection_id": "memo-contradiction-rerun",
                        "local_source_ref": "local",
                        "upstream_source_ref": "upstream",
                        "upstream_selection_id": "upstream-id",
                    },
                },
                "playbook_automation_plans": {
                    "owner_repo": "aoa-playbooks",
                    "local_collection_route": "/playbooks/automation-plans",
                    "local_item_route": "/playbooks/automation-plan",
                    "upstream_rel_path": "generated/playbook_automation_seeds.json",
                    "compatibility_collection_route": "/playbooks/automation-seeds",
                    "compatibility_item_route": "/playbooks/automation-seed",
                },
            }
        ),
    )

    errors: list[str] = []
    federation_surface.validate_federation_required_files(
        errors,
        root=tmp_path,
        required_runtime_inputs={},
        bridge_path=bridge_path,
        load_structured_object_func=lambda path: {},
    )

    assert (
        "upstream compatibility bridge playbook automation plan bridge must include upstream_source_ref"
        in errors
    )


def test_federation_upstream_compatibility_keeps_detailed_values_in_legacy_index(
    tmp_path: Path,
) -> None:
    bridge_path = tmp_path / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json"
    write_text(
        bridge_path,
        json.dumps(
            {
                "artifact_kind": "abyss-stack.upstream-compatibility-bridge",
                "runtime_evidence_templates": {
                    "memo-recall-rerun": {
                        "upstream_selection_id": "phase-alpha-runtime-evidence"
                    }
                },
                "playbook_automation_plans": {
                    "upstream_rel_path": "playbook_automation_seeds"
                },
            }
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
        "\n".join(
            [
                "single active bridge",
                "legacy/upstream-compatibility/INDEX.md",
                "upstream-compatibility-bridge.json",
                "memo-recall-rerun",
                "automation-plans",
                "phase-alpha-runtime-evidence",
            ]
        ),
    )
    write_text(
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "README.md",
        "See UPSTREAM_COMPATIBILITY.md\n",
    )
    write_text(
        tmp_path / "mechanics" / "federation-seams" / "PARTS.md",
        "See UPSTREAM_COMPATIBILITY.md\n",
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
        "\n".join(
            [
                "memo-recall-rerun",
                "memo-contradiction-gap",
                "memo-contradiction-rerun",
            ]
        ),
    )
    write_text(
        tmp_path / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml",
        "required_files: []\n",
    )
    write_text(
        tmp_path / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml",
        "required_files: []\n",
    )

    errors: list[str] = []
    federation_surface.validate_federation_upstream_compatibility(
        errors,
        root=tmp_path,
        bridge_path=bridge_path,
        read_text_func=lambda path: path.read_text(encoding="utf-8") if path.exists() else None,
    )

    assert (
        "mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md "
        "must classify bridge value `phase-alpha-runtime-evidence`"
    ) in errors
    assert (
        "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
        "must keep detailed legacy value `phase-alpha-runtime-evidence` in legacy/upstream-compatibility/INDEX.md"
    ) in errors


def test_federation_landing_requires_route_api_catalog_entry(tmp_path: Path) -> None:
    write_text(tmp_path / "config-templates" / "README.md", "Configs/federation/\nServices/aoa-browser/\nServices/route-api/\n")
    write_text(tmp_path / "config-templates" / "Services" / "README.md", "aoa-browser/\naoa-browser/ms-playwright/\nroute-api/\n")
    write_text(
        tmp_path / "docs" / "runtime" / "STORAGE_LAYOUT.md",
        "Knowledge/federation\nsource-managed build context\nServices/aoa-browser/ms-playwright/\n",
    )
    write_text(
        tmp_path / "docs" / "install" / "DEPLOYMENT.md",
        "\n".join(
            [
                "aoa-sync-federation-surfaces --layer aoa-agents",
                "aoa-sync-federation-surfaces --layer aoa-memo",
                "aoa-sync-federation-surfaces --layer aoa-evals",
                "aoa-sync-federation-surfaces --layer aoa-playbooks",
                "aoa-sync-federation-surfaces --layer aoa-kag",
                "aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now",
                "aoa-sync-federation-surfaces --layer tos-source",
            ]
        ),
    )
    write_text(
        tmp_path / "docs" / "runtime" / "PATHS.md",
        "AOA_AGENTS_ROOT\nAOA_MEMO_ROOT\nAOA_EVALS_ROOT\nAOA_PLAYBOOKS_ROOT\nAOA_KAG_ROOT\nAOA_TOS_ROOT\n",
    )
    write_text(
        tmp_path / "docs" / "runtime" / "SERVICE_CATALOG.md",
        "43-federation-router.yml\nPOST /run/federated\n`abyss_default`\n",
    )
    write_text(
        tmp_path / "docs" / "profiles" / "PROFILES.md",
        "`federation`\nAOA_FEDERATED_RUN_ENABLED=true\n",
    )
    write_text(
        tmp_path / "docs" / "profiles" / "PROFILE_RECIPES.md",
        "route-api\naoa-federated-check\n--playbook-id AOA-P-0008\n--inspect-id AOA-K-0011\n--memo-id AOA-M-0001\n",
    )
    write_text(
        tmp_path / "docs" / "operations" / "RUNBOOK.md",
        "aoa-federated-check\n--playbook-id AOA-P-0008\n--inspect-id AOA-K-0011\n--memo-id AOA-M-0001\n",
    )

    errors: list[str] = []
    federation_surface.validate_federation_landing(errors, root=tmp_path)

    assert "docs/runtime/SERVICE_CATALOG.md must mention route-api" in errors
