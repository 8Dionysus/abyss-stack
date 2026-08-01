from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"

EXPECTED_ACTIVE_SCHEMA_PATHS = {
    Path("mcp/protocol-lab/schemas/kag-cache-pair-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/kag-handle-pair-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/kag-next-pair-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-compatibility-matrix.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-conformance-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-consumer-wire-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-lab-status.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-pair-observation.schema.json"),
    Path("mcp/protocol-lab/schemas/protocol-production-pair-observation.schema.json"),
    Path("mcp/services/abyss-stack-mcp/schemas/policy-audit-summary.schema.json"),
    Path("mcp/services/abyss-stack-mcp/schemas/runtime-observation.schema.json"),
    Path("mcp/services/abyss-stack-mcp/schemas/runtime-plan-candidate.schema.json"),
    Path(
        "mechanics/config-projection/parts/codex-hooks/schemas/codex-hooks-composition-receipt.schema.json"
    ),
    Path(
        "mechanics/config-projection/parts/codex-hooks/schemas/codex-hooks-fragment.schema.json"
    ),
    Path(
        "mechanics/config-projection/parts/sync/schemas/mcp-deployment-manifest.schema.json"
    ),
    Path("schemas/workspace_decision_repo_source_posture.schema.json"),
    Path("schemas/workspace_decision_graph.schema.json"),
    Path("schemas/workspace_decision_graph_edge.schema.json"),
    Path("schemas/workspace_decision_graph_node.schema.json"),
    Path("schemas/workspace_decision_graph_summary.schema.json"),
    Path("mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-event.schema.json"),
    Path(
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-runtime-kernel-registry.schema.json"
    ),
    Path(
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-runtime-kernel.schema.json"
    ),
    Path(
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/mechanical-trial-event-log.schema.json"
    ),
    Path(
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/mechanical-trial-run-registry.schema.json"
    ),
    Path(
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/mechanical-trial-run.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json"
    ),
    Path(
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot_collection.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle_collection.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result_collection.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger_collection.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-agent-local-runtime-namespace-v0.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-runtime-delivery-receipt.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-runtime-erasure-owner-extension-v0.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-shadow-runtime-receipt.schema.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-canary-runtime-receipt.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/agent-os-adapter/schemas/agent-os-runtime-binding.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/agent-os-adapter/schemas/agent-os-runtime-profile.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-artifact-hook-candidate.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-eval-evidence-selection-candidate.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-memo-export-candidate.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/return-policy/schemas/runtime-return-event.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/return-policy/schemas/runtime-return-policy.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/runtime-contracts/schemas/runtime-governed-execution-canary-catalog.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/runtime-contracts/schemas/runtime-governed-execution-policy.schema.json"
    ),
    Path(
        "mechanics/governed-execution/parts/runtime-contracts/schemas/runtime-governed-execution-request.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/local-trials/schemas/runtime-benchmark.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/experiment-suite.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/human-gold-review-manifest.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/human-gold-review-record.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/manual-review-receipt.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/ocr-candidate-review-manifest.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/ocr-render-manifest.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/run-receipt.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/runtime-manifest.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/source-visible-model-inspection.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/structure-vlm-selection.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/translation-lab-readiness.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/translation-source-human-review.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/translation-source-manifest.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/translation-source-model-inspection.schema.json"
    ),
    Path(
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/translation-source-review-manifest.schema.json"
    ),
    Path("mechanics/machine-fit/parts/fit-record/schemas/schema.v1.json"),
    Path("mechanics/machine-fit/parts/host-facts/schemas/schema.v1.json"),
    Path("mechanics/machine-fit/parts/machine-bridge/schemas/schema.v1.json"),
    Path("mechanics/machine-fit/parts/platform-adaptations/schemas/schema.v1.json"),
    Path(
        "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-gateway-cache-status.schema.json"
    ),
    Path(
        "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-usage-snapshot.schema.json"
    ),
    Path(
        "mechanics/runtime-repair/parts/a2a-return-dry-run/schemas/runtime-a2a-return-closeout-dry-run.schema.json"
    ),
    Path(
        "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json"
    ),
    Path(
        "mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json"
    ),
    Path("quests/schemas/quest.schema.json"),
    Path("quests/schemas/quest_dispatch.schema.json"),
}


def load_json(relative_path: str | Path) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def active_schema_paths() -> list[Path]:
    paths: list[Path] = []
    for path in REPO_ROOT.rglob("*.json"):
        relative = path.relative_to(REPO_ROOT)
        if ".git" in relative.parts or "legacy" in relative.parts:
            continue
        if path.name.endswith(".schema.json") or "schemas" in relative.parts:
            paths.append(relative)
    return sorted(paths)


def active_example_paths() -> set[Path]:
    paths: set[Path] = set()
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if ".git" in relative.parts or "legacy" in relative.parts:
            continue
        if "examples" not in relative.parts:
            continue
        if path.name.endswith((".json", ".json.example", ".example.json")):
            paths.add(relative)
    return paths


def validate_payload(
    payload_path: str | Path,
    schema_path: str | Path,
    *,
    mode: str = "object",
) -> None:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    payload = load_json(payload_path)
    if mode == "object":
        validator.validate(payload)
        return
    if mode == "array-items":
        assert isinstance(payload, list), f"{payload_path} must contain an array"
        for index, item in enumerate(payload):
            validator.validate(item)
            assert isinstance(item, dict), (
                f"{payload_path} item {index} must be an object"
            )
        return
    if mode == "events-array":
        assert isinstance(payload, dict), f"{payload_path} must contain an object"
        events = payload.get("events")
        assert isinstance(events, list), f"{payload_path} must contain events[]"
        for index, item in enumerate(events):
            validator.validate(item)
            assert isinstance(item, dict), (
                f"{payload_path} events[{index}] must be an object"
            )
        return
    raise AssertionError(f"unknown validation mode: {mode}")


EXAMPLE_SCHEMA_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "mcp/services/abyss-stack-mcp/examples/runtime-observation.public.example.json",
        "mcp/services/abyss-stack-mcp/schemas/runtime-observation.schema.json",
        "object",
    ),
    (
        "mechanics/governed-execution/parts/agent-os-adapter/runtime-profile.v1.json",
        "mechanics/governed-execution/parts/agent-os-adapter/schemas/agent-os-runtime-profile.schema.json",
        "object",
    ),
    (
        "mechanics/agon-runtime/parts/runtime-kernels/examples/duel-runtime-kernel.example.json",
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-runtime-kernel.schema.json",
        "object",
    ),
    (
        "mechanics/agon-runtime/parts/runtime-kernels/examples/mechanical-duel-event-log.example.json",
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-event.schema.json",
        "events-array",
    ),
    *(
        (
            str(path.relative_to(REPO_ROOT)),
            "mechanics/agon-runtime/parts/runtime-kernels/schemas/mechanical-trial-event-log.schema.json",
            "object",
        )
        for path in sorted(
            (REPO_ROOT / "mechanics/agon-runtime/parts/runtime-kernels/examples").glob(
                "mechanical-trial-event-log.*.example.json"
            )
        )
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json",
        "object",
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json",
        "object",
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json",
        "object",
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_anchor_ref.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json",
        "object",
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json",
        "object",
    ),
    (
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json",
        "mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/examples/agent_build_snapshot.example.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/examples/reputation_ledger.example.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/examples/quest_run_result.example.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/examples/frontend_projection_bundle.example.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle.schema.json",
        "object",
    ),
    *(
        (
            str(path.relative_to(REPO_ROOT)),
            "mechanics/federation-seams/parts/memo-seam/schemas/active-organ-runtime-delivery-receipt.schema.json",
            "object",
        )
        for path in sorted(
            (
                REPO_ROOT
                / "mechanics/federation-seams/parts/memo-seam/examples"
            ).glob("*.example.json")
        )
    ),
    (
        "mechanics/governed-execution/parts/candidate-exports/examples/runtime_memo_export_candidate.checkpoint_export.example.json",
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-memo-export-candidate.schema.json",
        "object",
    ),
    (
        "mechanics/governed-execution/parts/candidate-exports/examples/runtime_eval_evidence_selection_candidate.workhorse-local.example.json",
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-eval-evidence-selection-candidate.schema.json",
        "object",
    ),
    (
        "mechanics/governed-execution/parts/candidate-exports/examples/runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json",
        "mechanics/governed-execution/parts/candidate-exports/schemas/runtime-artifact-hook-candidate.schema.json",
        "object",
    ),
    (
        "mechanics/governed-execution/parts/return-policy/examples/runtime_return_policy.agentic-local.example.json",
        "mechanics/governed-execution/parts/return-policy/schemas/runtime-return-policy.schema.json",
        "object",
    ),
    (
        "mechanics/governed-execution/parts/return-policy/examples/runtime_return_event.workhorse-local.example.json",
        "mechanics/governed-execution/parts/return-policy/schemas/runtime-return-event.schema.json",
        "object",
    ),
    (
        "mechanics/inference-pilots/parts/local-trials/examples/runtime_benchmark.workhorse-local.example.json",
        "mechanics/inference-pilots/parts/local-trials/schemas/runtime-benchmark.schema.json",
        "object",
    ),
    (
        "mechanics/inference-pilots/parts/tos-foundation-lab/examples/tos-foundation-suite.v1.json",
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/experiment-suite.schema.json",
        "object",
    ),
    (
        "mechanics/inference-pilots/parts/tos-foundation-lab/examples/tos-structure-vlm-selection.v1.json",
        "mechanics/inference-pilots/parts/tos-foundation-lab/schemas/structure-vlm-selection.schema.json",
        "object",
    ),
    (
        "mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json",
        "mechanics/machine-fit/parts/host-facts/schemas/schema.v1.json",
        "object",
    ),
    (
        "mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json.example",
        "mechanics/machine-fit/parts/host-facts/schemas/schema.v1.json",
        "object",
    ),
    (
        "mechanics/machine-fit/parts/machine-bridge/examples/machine-bridge.public.json.example",
        "mechanics/machine-fit/parts/machine-bridge/schemas/schema.v1.json",
        "object",
    ),
    (
        "mechanics/machine-fit/parts/fit-record/examples/machine-fit.public.json.example",
        "mechanics/machine-fit/parts/fit-record/schemas/schema.v1.json",
        "object",
    ),
    (
        "mechanics/machine-fit/parts/platform-adaptations/examples/platform-adaptation.public.json.example",
        "mechanics/machine-fit/parts/platform-adaptations/schemas/schema.v1.json",
        "object",
    ),
    (
        "mechanics/runtime-lifecycle/parts/status-readouts/examples/runtime_gateway_cache_status.gateway-local.example.json",
        "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-gateway-cache-status.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-lifecycle/parts/status-readouts/examples/runtime_usage_snapshot.workhorse-local.example.json",
        "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-usage-snapshot.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/a2a-return-dry-run/examples/runtime_a2a_return_closeout_dry_run.example.json",
        "mechanics/runtime-repair/parts/a2a-return-dry-run/schemas/runtime-a2a-return-closeout-dry-run.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.example.json",
        "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.honest-degradation.example.json",
        "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.retrieval-outage-honesty.example.json",
        "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.timeout-chaos.example.json",
        "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.example.json",
        "mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.retrieval-outage-honesty.example.json",
        "mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json",
        "object",
    ),
    (
        "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.timeout-chaos.example.json",
        "mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json",
        "object",
    ),
    (
        "quests/examples/quest_dispatch.min.example.json",
        "quests/schemas/quest_dispatch.schema.json",
        "array-items",
    ),
)

PROJECTION_ONLY_EXAMPLES = {
    Path("quests/examples/quest_catalog.min.example.json"),
    Path(
        "mechanics/federation-seams/parts/memo-seam/examples/"
        "codex_owner_orientation_runtime_compatibility_pin_v0.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/examples/"
        "codex_owner_orientation_shadow_runtime_compatibility_pin_v0.json"
    ),
    Path(
        "mechanics/federation-seams/parts/memo-seam/examples/"
        "codex_owner_orientation_canary_runtime_compatibility_pin_v0.json"
    ),
}

EXECUTABLE_NEGATIVE_EXAMPLES = {
    Path(
        "mechanics/federation-seams/parts/memo-seam/examples/"
        "active_organ_runtime_delivery_receipt.negative-examples.json"
    ),
}

GENERATED_SCHEMA_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "mechanics/agon-runtime/parts/runtime-kernels/generated/duel-runtime-kernel-registry.min.json",
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/duel-runtime-kernel-registry.schema.json",
        "object",
    ),
    (
        "mechanics/agon-runtime/parts/runtime-kernels/generated/mechanical-trial-run-registry.min.json",
        "mechanics/agon-runtime/parts/runtime-kernels/schemas/mechanical-trial-run-registry.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/generated/agent_build_snapshots.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/agent_build_snapshot_collection.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/generated/reputation_ledgers.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/reputation_ledger_collection.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/generated/quest_run_results.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/quest_run_result_collection.schema.json",
        "object",
    ),
    (
        "mechanics/federation-seams/parts/rpg-runtime/generated/frontend_projection_bundles.json",
        "mechanics/federation-seams/parts/rpg-runtime/schemas/frontend_projection_bundle_collection.schema.json",
        "object",
    ),
)


def test_active_schema_documents_are_valid_draft_2020_12_contracts() -> None:
    paths = active_schema_paths()
    assert len(paths) >= 40
    for path in paths:
        payload = load_json(path)
        assert isinstance(payload, dict), f"{path} must contain a JSON object"
        assert payload.get("$schema") == DRAFT_2020_12, f"{path} must use Draft 2020-12"
        assert isinstance(payload.get("$id"), str), f"{path} must declare $id"
        assert payload["$id"].startswith(("https://", "http://")), (
            f"{path} $id must be URI-like"
        )
        assert isinstance(payload.get("title"), str) and payload["title"], (
            f"{path} must declare title"
        )
        assert payload.get("type") == "object", (
            f"{path} must describe a top-level object"
        )
        Draft202012Validator.check_schema(payload)


def test_active_schema_manifest_matches_discovery() -> None:
    assert set(active_schema_paths()) == EXPECTED_ACTIVE_SCHEMA_PATHS


def test_schema_example_mapping_covers_active_json_examples() -> None:
    mapped = {Path(payload) for payload, _, _ in EXAMPLE_SCHEMA_CASES}
    uncovered = (
        active_example_paths()
        - mapped
        - PROJECTION_ONLY_EXAMPLES
        - EXECUTABLE_NEGATIVE_EXAMPLES
    )
    assert sorted(path.as_posix() for path in uncovered) == []


def test_active_examples_validate_against_schema_contracts() -> None:
    for payload_path, schema_path, mode in EXAMPLE_SCHEMA_CASES:
        validate_payload(payload_path, schema_path, mode=mode)


def test_stack_mcp_schema_encodes_conditional_runtime_invariants() -> None:
    schema = load_json(
        "mcp/services/abyss-stack-mcp/schemas/runtime-observation.schema.json"
    )
    example = load_json(
        "mcp/services/abyss-stack-mcp/examples/"
        "runtime-observation.public.example.json"
    )
    assert isinstance(schema, dict)
    assert isinstance(example, dict)
    validator = Draft202012Validator(schema)
    validator.validate(example)

    invalid_payloads: list[dict] = []

    payload = copy.deepcopy(example)
    payload["subjects"][0]["source"]["evidence"]["evidence_refs"] = []
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["state"] = "compatible_drift"
    del source_evidence["reason_codes"]
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["endpoint"]["server_schema_digest"] = None
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["consumers"][0]["observed_protocol_versions"] = []
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["freshness"]["evidence_refs"] = []
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["canary"]["result_grounded"] = False
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["proof"]["proved_canary_route"] = None
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["rollback"]["proof_ref"] = None
    invalid_payloads.append(payload)

    payload = copy.deepcopy(example)
    payload["subjects"][0]["effect_classes"] = ["prepare_candidate"]
    invalid_payloads.append(payload)

    for payload in invalid_payloads:
        assert not validator.is_valid(payload)


def test_generated_schema_artifacts_validate_against_schema_contracts() -> None:
    for payload_path, schema_path, mode in GENERATED_SCHEMA_CASES:
        validate_payload(payload_path, schema_path, mode=mode)
