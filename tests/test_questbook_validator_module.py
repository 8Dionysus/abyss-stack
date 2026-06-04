from __future__ import annotations

import json
from pathlib import Path

from scripts.validators import questbook_surface


def test_quest_schema_envelope_reports_required_field_drift() -> None:
    errors: list[str] = []

    questbook_surface.validate_quest_schema_envelope(
        {
            "title": "abyss-stack work_quest_v1",
            "type": "object",
            "additionalProperties": False,
            "required": ["schema_version"],
            "properties": {"schema_version": {"const": "work_quest_v1"}},
        },
        title="abyss-stack work_quest_v1",
        required_fields=("schema_version", "id"),
        schema_version="work_quest_v1",
        label="quests/schemas/quest.schema.json",
        errors=errors,
    )

    assert errors == [
        "quests/schemas/quest.schema.json required fields must stay aligned with the local quest contract"
    ]


def test_questbook_surface_reports_generated_collection_version_drift(tmp_path: Path) -> None:
    generated_root = (
        tmp_path
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "rpg-runtime"
        / "generated"
    )
    generated_root.mkdir(parents=True)
    (generated_root / "agent_build_snapshots.json").write_text(
        json.dumps(
            {
                "schema_version": "agent_build_snapshot_collection_v999",
                "builds": [
                    {
                        "schema_version": "agent_build_snapshot_v1",
                        "public_safe": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    errors: list[str] = []
    questbook_surface.validate_questbook_surface(
        errors,
        root=tmp_path,
        questbook_path=Path("QUESTBOOK.md"),
        questbook_integration_path=Path("docs/governance/QUESTBOOK_STACK_INTEGRATION.md"),
        rpg_runtime_frontend_posture_path=Path("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md"),
        rpg_runtime_collections_path=Path("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md"),
        rpg_runtime_builders_path=Path("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_BUILDERS.md"),
        rpg_route_api_seam_path=Path("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_ROUTE_API_SEAM.md"),
        rpg_frontend_projection_seam_path=Path("mechanics/federation-seams/parts/rpg-runtime/docs/RPG_FRONTEND_PROJECTION_SEAM.md"),
        quest_schema_path=Path("quests/schemas/quest.schema.json"),
        quest_dispatch_schema_path=Path("quests/schemas/quest_dispatch.schema.json"),
        agent_build_snapshot_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot.schema.json"),
        reputation_ledger_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger.schema.json"),
        quest_run_result_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result.schema.json"),
        frontend_projection_bundle_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle.schema.json"),
        agent_build_snapshot_collection_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot_collection.schema.json"),
        reputation_ledger_collection_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger_collection.schema.json"),
        quest_run_result_collection_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result_collection.schema.json"),
        frontend_projection_bundle_collection_schema_path=Path("mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle_collection.schema.json"),
        quest_catalog_example_path=Path("quests/examples/quest_catalog.min.example.json"),
        quest_dispatch_example_path=Path("quests/examples/quest_dispatch.min.example.json"),
        agent_build_snapshot_example_path=Path("mechanics/federation-seams/parts/rpg-runtime/examples/agent_build_snapshot.example.json"),
        reputation_ledger_example_path=Path("mechanics/federation-seams/parts/rpg-runtime/examples/reputation_ledger.example.json"),
        quest_run_result_example_path=Path("mechanics/federation-seams/parts/rpg-runtime/examples/quest_run_result.example.json"),
        frontend_projection_bundle_example_path=Path("mechanics/federation-seams/parts/rpg-runtime/examples/frontend_projection_bundle.example.json"),
        generated_agent_build_snapshots_path=Path("mechanics/federation-seams/parts/rpg-runtime/generated/agent_build_snapshots.json"),
        generated_reputation_ledgers_path=Path("mechanics/federation-seams/parts/rpg-runtime/generated/reputation_ledgers.json"),
        generated_quest_run_results_path=Path("mechanics/federation-seams/parts/rpg-runtime/generated/quest_run_results.json"),
        generated_frontend_projection_bundles_path=Path("mechanics/federation-seams/parts/rpg-runtime/generated/frontend_projection_bundles.json"),
        quest_surface_root=Path("quests"),
        quest_ids=(),
        quest_routes={},
        questbook_required_tokens=(),
        questbook_forbidden_tokens=(),
        questbook_integration_required_tokens=(),
        questbook_integration_forbidden_tokens=(),
        quest_schema_required_fields=(),
        quest_dispatch_required_fields=(),
        closed_quest_states=set(),
        load_structured_object_func=lambda path: {},
        quest_source_path_func=lambda quest_id: Path(f"quests/{quest_id}.yaml"),
        build_expected_quest_catalog_entry_func=lambda quest_id, payload: {},
        build_expected_quest_dispatch_entry_func=lambda quest_id, payload: {},
    )

    assert (
        "mechanics/federation-seams/parts/rpg-runtime/generated/agent_build_snapshots.json "
        "schema_version must equal 'agent_build_snapshot_collection_v1'"
    ) in errors
