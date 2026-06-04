from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence, Set
import json
from pathlib import Path
from typing import Any

StructuredObjectLoader = Callable[[Path], dict[str, object]]
QuestSourcePath = Callable[[str], Path]
QuestEntryBuilder = Callable[[str, dict[str, Any]], dict[str, Any]]

QUESTBOOK_PATH = Path("QUESTBOOK.md")
QUESTBOOK_INTEGRATION_PATH = Path("docs") / "governance" / "QUESTBOOK_STACK_INTEGRATION.md"
RPG_RUNTIME_DOC_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime" / "docs"
RPG_RUNTIME_FRONTEND_POSTURE_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_FRONTEND_POSTURE.md"
RPG_RUNTIME_COLLECTIONS_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_COLLECTIONS.md"
RPG_RUNTIME_BUILDERS_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_RUNTIME_BUILDERS.md"
RPG_ROUTE_API_SEAM_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_ROUTE_API_SEAM.md"
RPG_FRONTEND_PROJECTION_SEAM_PATH = RPG_RUNTIME_DOC_ROOT / "RPG_FRONTEND_PROJECTION_SEAM.md"
QUEST_SURFACE_ROOT = Path("quests")
QUEST_SCHEMA_PATH = QUEST_SURFACE_ROOT / "schemas" / "quest.schema.json"
QUEST_DISPATCH_SCHEMA_PATH = QUEST_SURFACE_ROOT / "schemas" / "quest_dispatch.schema.json"
RPG_RUNTIME_SURFACE_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime"
RPG_RUNTIME_SCHEMA_ROOT = RPG_RUNTIME_SURFACE_ROOT / "schemas"
RPG_RUNTIME_EXAMPLE_ROOT = RPG_RUNTIME_SURFACE_ROOT / "examples"
RPG_RUNTIME_GENERATED_ROOT = RPG_RUNTIME_SURFACE_ROOT / "generated"
AGENT_BUILD_SNAPSHOT_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot.schema.json"
REPUTATION_LEDGER_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger.schema.json"
QUEST_RUN_RESULT_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result.schema.json"
FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle.schema.json"
AGENT_BUILD_SNAPSHOT_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "agent_build_snapshot_collection.schema.json"
REPUTATION_LEDGER_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "reputation_ledger_collection.schema.json"
QUEST_RUN_RESULT_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "quest_run_result_collection.schema.json"
FRONTEND_PROJECTION_BUNDLE_COLLECTION_SCHEMA_PATH = RPG_RUNTIME_SCHEMA_ROOT / "frontend_projection_bundle_collection.schema.json"
QUEST_CATALOG_EXAMPLE_PATH = QUEST_SURFACE_ROOT / "examples" / "quest_catalog.min.example.json"
QUEST_DISPATCH_EXAMPLE_PATH = QUEST_SURFACE_ROOT / "examples" / "quest_dispatch.min.example.json"
AGENT_BUILD_SNAPSHOT_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "agent_build_snapshot.example.json"
REPUTATION_LEDGER_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "reputation_ledger.example.json"
QUEST_RUN_RESULT_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "quest_run_result.example.json"
FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH = RPG_RUNTIME_EXAMPLE_ROOT / "frontend_projection_bundle.example.json"
GENERATED_AGENT_BUILD_SNAPSHOTS_PATH = RPG_RUNTIME_GENERATED_ROOT / "agent_build_snapshots.json"
GENERATED_REPUTATION_LEDGERS_PATH = RPG_RUNTIME_GENERATED_ROOT / "reputation_ledgers.json"
GENERATED_QUEST_RUN_RESULTS_PATH = RPG_RUNTIME_GENERATED_ROOT / "quest_run_results.json"
GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH = RPG_RUNTIME_GENERATED_ROOT / "frontend_projection_bundles.json"
QUESTBOOK_REQUIRED_TOKENS = (
    "deferred infrastructure obligations that belong to `abyss-stack`",
    "render-truth, doctor, first-run, and runtime guardrail follow-through",
    "source-owned meaning from AoA layer repos",
    "quests/<lane>/<state>/ABYSS-STACK-Q-*.yaml",
    "not generated state, deployed runtime state, or runtime authority",
)
QUESTBOOK_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
CLOSED_QUEST_STATES = {"done", "dropped"}
QUESTBOOK_INTEGRATION_REQUIRED_TOKENS = (
    "runtime, deployment, lifecycle, security, storage, and platform posture",
    "specialized AoA repositories still own their own doctrine and public meaning",
    "high-risk routes should default toward stronger control modes and human gates",
    "reviewable and source-owned",
    "do not replace the deployed mirror under `/srv/AbyssOS/abyss-stack`",
)
QUESTBOOK_INTEGRATION_FORBIDDEN_TOKENS = ("ATM10-Agent", "aoa-sdk")
QUEST_SCHEMA_REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "title",
    "repo",
    "lane",
    "owner_surface",
    "kind",
    "state",
    "band",
    "difficulty",
    "risk",
    "control_mode",
    "delegate_tier",
    "write_scope",
    "activation",
    "anchor_ref",
    "evidence",
    "opened_at",
    "touched_at",
    "public_safe",
)
QUEST_DISPATCH_REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "repo",
    "lane",
    "state",
    "band",
    "difficulty",
    "risk",
    "control_mode",
    "delegate_tier",
    "split_required",
    "write_scope",
    "activation_mode",
    "public_safe",
)


def validate_quest_schema_envelope(
    payload: object,
    *,
    title: str,
    required_fields: Sequence[str],
    schema_version: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object")
        return
    if payload.get("title") != title:
        errors.append(f"{label} title must equal '{title}'")
    if payload.get("type") != "object":
        errors.append(f"{label} type must equal 'object'")
    if payload.get("additionalProperties") is not False:
        errors.append(f"{label} must set additionalProperties to false")

    required = payload.get("required")
    if required != list(required_fields):
        errors.append(f"{label} required fields must stay aligned with the local quest contract")

    properties = payload.get("properties")
    if not isinstance(properties, dict):
        errors.append(f"{label} properties must be an object")
        return

    version_payload = properties.get("schema_version")
    if not isinstance(version_payload, dict) or version_payload.get("const") != schema_version:
        errors.append(f"{label} schema_version.const must equal '{schema_version}'")


def validate_questbook_surface(
    errors: list[str],
    *,
    root: Path,
    questbook_path: Path,
    questbook_integration_path: Path,
    rpg_runtime_frontend_posture_path: Path,
    rpg_runtime_collections_path: Path,
    rpg_runtime_builders_path: Path,
    rpg_route_api_seam_path: Path,
    rpg_frontend_projection_seam_path: Path,
    quest_schema_path: Path,
    quest_dispatch_schema_path: Path,
    agent_build_snapshot_schema_path: Path,
    reputation_ledger_schema_path: Path,
    quest_run_result_schema_path: Path,
    frontend_projection_bundle_schema_path: Path,
    agent_build_snapshot_collection_schema_path: Path,
    reputation_ledger_collection_schema_path: Path,
    quest_run_result_collection_schema_path: Path,
    frontend_projection_bundle_collection_schema_path: Path,
    quest_catalog_example_path: Path,
    quest_dispatch_example_path: Path,
    agent_build_snapshot_example_path: Path,
    reputation_ledger_example_path: Path,
    quest_run_result_example_path: Path,
    frontend_projection_bundle_example_path: Path,
    generated_agent_build_snapshots_path: Path,
    generated_reputation_ledgers_path: Path,
    generated_quest_run_results_path: Path,
    generated_frontend_projection_bundles_path: Path,
    quest_surface_root: Path,
    quest_ids: Sequence[str],
    quest_routes: Mapping[str, tuple[str, str]],
    questbook_required_tokens: Sequence[str],
    questbook_forbidden_tokens: Sequence[str],
    questbook_integration_required_tokens: Sequence[str],
    questbook_integration_forbidden_tokens: Sequence[str],
    quest_schema_required_fields: Sequence[str],
    quest_dispatch_required_fields: Sequence[str],
    closed_quest_states: Set[str],
    load_structured_object_func: StructuredObjectLoader,
    quest_source_path_func: QuestSourcePath,
    build_expected_quest_catalog_entry_func: QuestEntryBuilder,
    build_expected_quest_dispatch_entry_func: QuestEntryBuilder,
) -> None:
    required_paths = (
        questbook_path,
        questbook_integration_path,
        rpg_runtime_frontend_posture_path,
        rpg_runtime_collections_path,
        rpg_runtime_builders_path,
        rpg_route_api_seam_path,
        rpg_frontend_projection_seam_path,
        quest_schema_path,
        quest_dispatch_schema_path,
        agent_build_snapshot_schema_path,
        reputation_ledger_schema_path,
        quest_run_result_schema_path,
        frontend_projection_bundle_schema_path,
        agent_build_snapshot_collection_schema_path,
        reputation_ledger_collection_schema_path,
        quest_run_result_collection_schema_path,
        frontend_projection_bundle_collection_schema_path,
        quest_catalog_example_path,
        quest_dispatch_example_path,
        agent_build_snapshot_example_path,
        reputation_ledger_example_path,
        quest_run_result_example_path,
        frontend_projection_bundle_example_path,
        generated_agent_build_snapshots_path,
        generated_reputation_ledgers_path,
        generated_quest_run_results_path,
        generated_frontend_projection_bundles_path,
    ) + tuple(quest_source_path_func(quest_id) for quest_id in quest_ids)

    for relative_path in required_paths:
        path = root / relative_path
        if not path.exists():
            errors.append(f"missing required file: {relative_path.as_posix()}")

    questbook_text = _validate_questbook_docs(
        errors,
        root=root,
        questbook_path=questbook_path,
        questbook_integration_path=questbook_integration_path,
        rpg_runtime_frontend_posture_path=rpg_runtime_frontend_posture_path,
        rpg_runtime_collections_path=rpg_runtime_collections_path,
        rpg_runtime_builders_path=rpg_runtime_builders_path,
        rpg_route_api_seam_path=rpg_route_api_seam_path,
        rpg_frontend_projection_seam_path=rpg_frontend_projection_seam_path,
        questbook_required_tokens=questbook_required_tokens,
        questbook_forbidden_tokens=questbook_forbidden_tokens,
        questbook_integration_required_tokens=questbook_integration_required_tokens,
        questbook_integration_forbidden_tokens=questbook_integration_forbidden_tokens,
    )

    _validate_quest_schemas(
        errors,
        root=root,
        quest_schema_path=quest_schema_path,
        quest_dispatch_schema_path=quest_dispatch_schema_path,
        agent_build_snapshot_schema_path=agent_build_snapshot_schema_path,
        reputation_ledger_schema_path=reputation_ledger_schema_path,
        quest_run_result_schema_path=quest_run_result_schema_path,
        frontend_projection_bundle_schema_path=frontend_projection_bundle_schema_path,
        agent_build_snapshot_collection_schema_path=agent_build_snapshot_collection_schema_path,
        reputation_ledger_collection_schema_path=reputation_ledger_collection_schema_path,
        quest_run_result_collection_schema_path=quest_run_result_collection_schema_path,
        frontend_projection_bundle_collection_schema_path=frontend_projection_bundle_collection_schema_path,
        quest_schema_required_fields=quest_schema_required_fields,
        quest_dispatch_required_fields=quest_dispatch_required_fields,
    )
    _validate_runtime_examples(
        errors,
        root=root,
        agent_build_snapshot_example_path=agent_build_snapshot_example_path,
        reputation_ledger_example_path=reputation_ledger_example_path,
        quest_run_result_example_path=quest_run_result_example_path,
        frontend_projection_bundle_example_path=frontend_projection_bundle_example_path,
    )
    _validate_generated_collections(
        errors,
        root=root,
        generated_agent_build_snapshots_path=generated_agent_build_snapshots_path,
        generated_reputation_ledgers_path=generated_reputation_ledgers_path,
        generated_quest_run_results_path=generated_quest_run_results_path,
        generated_frontend_projection_bundles_path=generated_frontend_projection_bundles_path,
    )
    _validate_quest_sources(
        errors,
        root=root,
        quest_ids=quest_ids,
        quest_routes=quest_routes,
        questbook_text=questbook_text,
        quest_catalog_example_path=quest_catalog_example_path,
        quest_dispatch_example_path=quest_dispatch_example_path,
        quest_surface_root=quest_surface_root,
        closed_quest_states=closed_quest_states,
        load_structured_object_func=load_structured_object_func,
        quest_source_path_func=quest_source_path_func,
        build_expected_quest_catalog_entry_func=build_expected_quest_catalog_entry_func,
        build_expected_quest_dispatch_entry_func=build_expected_quest_dispatch_entry_func,
    )


def _validate_questbook_docs(
    errors: list[str],
    *,
    root: Path,
    questbook_path: Path,
    questbook_integration_path: Path,
    rpg_runtime_frontend_posture_path: Path,
    rpg_runtime_collections_path: Path,
    rpg_runtime_builders_path: Path,
    rpg_route_api_seam_path: Path,
    rpg_frontend_projection_seam_path: Path,
    questbook_required_tokens: Sequence[str],
    questbook_forbidden_tokens: Sequence[str],
    questbook_integration_required_tokens: Sequence[str],
    questbook_integration_forbidden_tokens: Sequence[str],
) -> str:
    try:
        questbook_text = (root / questbook_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        questbook_text = ""
    else:
        for token in questbook_required_tokens:
            if token not in questbook_text:
                errors.append(f"QUESTBOOK.md must contain '{token}'")
        for token in questbook_forbidden_tokens:
            if token in questbook_text:
                errors.append(f"QUESTBOOK.md must not mention '{token}'")

    try:
        integration_text = (root / questbook_integration_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        integration_text = ""
    else:
        for token in questbook_integration_required_tokens:
            if token not in integration_text:
                errors.append(f"{questbook_integration_path.as_posix()} must contain '{token}'")
        for token in questbook_integration_forbidden_tokens:
            if token in integration_text:
                errors.append(f"{questbook_integration_path.as_posix()} must not mention '{token}'")

    try:
        rpg_runtime_frontend_text = (root / rpg_runtime_frontend_posture_path).read_text(
            encoding="utf-8"
        )
    except FileNotFoundError:
        rpg_runtime_frontend_text = ""
    else:
        required_tokens = (
            "`abyss-stack` owns runtime state and service delivery.",
            "It does not own upstream meaning.",
            "The frontend must not become an authority surface.",
            "It must never pretend to be the soul.",
        )
        for token in required_tokens:
            if token not in rpg_runtime_frontend_text:
                errors.append(f"{rpg_runtime_frontend_posture_path.as_posix()} must contain '{token}'")

    doc_expectations = (
        (
            rpg_runtime_collections_path,
            (
                "`abyss-stack` owns the collections.",
                "It does not own the upstream meanings the collections cite.",
                "A runtime collection is a read model with memory.",
            ),
        ),
        (
            rpg_runtime_builders_path,
            (
                "Builders may assemble runtime-owned collections.",
                "Builders may not invent upstream meaning.",
                "Build upstream, collect downstream, project last.",
            ),
        ),
        (
            rpg_route_api_seam_path,
            (
                "It is not implemented in this source contract.",
                "`/rpg/*` is advisory and read-only.",
                "The seam should read like a lantern, not a wand.",
            ),
        ),
        (
            rpg_frontend_projection_seam_path,
            (
                "The frontend reads derived bundles.",
                "It does not become a new authority surface.",
                "Keep the source refs audible.",
            ),
        ),
    )
    for path, tokens in doc_expectations:
        try:
            text = (root / path).read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        for token in tokens:
            if token not in text:
                errors.append(f"{path.as_posix()} must contain '{token}'")

    return questbook_text


def _validate_quest_schemas(
    errors: list[str],
    *,
    root: Path,
    quest_schema_path: Path,
    quest_dispatch_schema_path: Path,
    agent_build_snapshot_schema_path: Path,
    reputation_ledger_schema_path: Path,
    quest_run_result_schema_path: Path,
    frontend_projection_bundle_schema_path: Path,
    agent_build_snapshot_collection_schema_path: Path,
    reputation_ledger_collection_schema_path: Path,
    quest_run_result_collection_schema_path: Path,
    frontend_projection_bundle_collection_schema_path: Path,
    quest_schema_required_fields: Sequence[str],
    quest_dispatch_required_fields: Sequence[str],
) -> None:
    try:
        quest_schema_payload = json.loads((root / quest_schema_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        quest_schema_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{quest_schema_path.as_posix()} must contain valid JSON: {exc}")
        quest_schema_payload = None
    if quest_schema_payload is not None:
        validate_quest_schema_envelope(
            quest_schema_payload,
            title="abyss-stack work_quest_v1",
            required_fields=quest_schema_required_fields,
            schema_version="work_quest_v1",
            label=quest_schema_path.as_posix(),
            errors=errors,
        )

    try:
        dispatch_schema_payload = json.loads(
            (root / quest_dispatch_schema_path).read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        dispatch_schema_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{quest_dispatch_schema_path.as_posix()} must contain valid JSON: {exc}")
        dispatch_schema_payload = None
    if dispatch_schema_payload is not None:
        validate_quest_schema_envelope(
            dispatch_schema_payload,
            title="abyss-stack quest_dispatch_v1",
            required_fields=quest_dispatch_required_fields,
            schema_version="quest_dispatch_v1",
            label=quest_dispatch_schema_path.as_posix(),
            errors=errors,
        )

    schema_expectations = (
        (agent_build_snapshot_schema_path, "agent_build_snapshot_v1"),
        (reputation_ledger_schema_path, "reputation_ledger_v1"),
        (quest_run_result_schema_path, "quest_run_result_v1"),
        (frontend_projection_bundle_schema_path, "frontend_projection_bundle_v1"),
        (agent_build_snapshot_collection_schema_path, "agent_build_snapshot_collection_v1"),
        (reputation_ledger_collection_schema_path, "reputation_ledger_collection_v1"),
        (quest_run_result_collection_schema_path, "quest_run_result_collection_v1"),
        (frontend_projection_bundle_collection_schema_path, "frontend_projection_bundle_collection_v1"),
    )
    for path, expected_title in schema_expectations:
        try:
            payload = json.loads((root / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("title") != expected_title:
            errors.append(f"{path.as_posix()} title must equal '{expected_title}'")


def _validate_runtime_examples(
    errors: list[str],
    *,
    root: Path,
    agent_build_snapshot_example_path: Path,
    reputation_ledger_example_path: Path,
    quest_run_result_example_path: Path,
    frontend_projection_bundle_example_path: Path,
) -> None:
    example_expectations = (
        (agent_build_snapshot_example_path, "agent_build_snapshot_v1"),
        (reputation_ledger_example_path, "reputation_ledger_v1"),
        (quest_run_result_example_path, "quest_run_result_v1"),
        (frontend_projection_bundle_example_path, "frontend_projection_bundle_v1"),
    )
    for path, expected_version in example_expectations:
        try:
            payload = json.loads((root / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("schema_version") != expected_version:
            errors.append(f"{path.as_posix()} schema_version must equal '{expected_version}'")
        if payload.get("public_safe") is not True:
            errors.append(f"{path.as_posix()} public_safe must be true")


def _validate_generated_collections(
    errors: list[str],
    *,
    root: Path,
    generated_agent_build_snapshots_path: Path,
    generated_reputation_ledgers_path: Path,
    generated_quest_run_results_path: Path,
    generated_frontend_projection_bundles_path: Path,
) -> None:
    generated_expectations = (
        (
            generated_agent_build_snapshots_path,
            "agent_build_snapshot_collection_v1",
            "builds",
            "agent_build_snapshot_v1",
        ),
        (
            generated_reputation_ledgers_path,
            "reputation_ledger_collection_v1",
            "ledgers",
            "reputation_ledger_v1",
        ),
        (
            generated_quest_run_results_path,
            "quest_run_result_collection_v1",
            "runs",
            "quest_run_result_v1",
        ),
        (
            generated_frontend_projection_bundles_path,
            "frontend_projection_bundle_collection_v1",
            "bundles",
            "frontend_projection_bundle_v1",
        ),
    )
    for path, expected_version, array_key, item_version in generated_expectations:
        try:
            payload = json.loads((root / path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{path.as_posix()} must contain valid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            errors.append(f"{path.as_posix()} must be a JSON object")
            continue
        if payload.get("schema_version") != expected_version:
            errors.append(f"{path.as_posix()} schema_version must equal '{expected_version}'")
        items = payload.get(array_key)
        if not isinstance(items, list) or not items:
            errors.append(f"{path.as_posix()} must include a non-empty '{array_key}' array")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{path.as_posix()} item {index} must be a JSON object")
                continue
            if item.get("schema_version") != item_version:
                errors.append(
                    f"{path.as_posix()} item {index} schema_version must equal '{item_version}'"
                )
            if item.get("public_safe") is not True:
                errors.append(f"{path.as_posix()} item {index} public_safe must be true")
        if path == generated_frontend_projection_bundles_path:
            first_bundle = items[0]
            if isinstance(first_bundle, dict) and first_bundle.get("vocabulary_overlay_ref") != "Agents-of-Abyss/generated/dual_vocabulary_overlay.json":
                errors.append(
                    "mechanics/federation-seams/parts/rpg-runtime/generated/frontend_projection_bundles.json must reference Agents-of-Abyss/generated/dual_vocabulary_overlay.json"
                )


def _validate_quest_sources(
    errors: list[str],
    *,
    root: Path,
    quest_ids: Sequence[str],
    quest_routes: Mapping[str, tuple[str, str]],
    questbook_text: str,
    quest_catalog_example_path: Path,
    quest_dispatch_example_path: Path,
    quest_surface_root: Path,
    closed_quest_states: Set[str],
    load_structured_object_func: StructuredObjectLoader,
    quest_source_path_func: QuestSourcePath,
    build_expected_quest_catalog_entry_func: QuestEntryBuilder,
    build_expected_quest_dispatch_entry_func: QuestEntryBuilder,
) -> None:
    expected_catalog = []
    expected_dispatch = []
    active_quest_ids: list[str] = []
    closed_quest_ids: list[str] = []
    for quest_id in quest_ids:
        expected_lane, expected_state = quest_routes[quest_id]
        quest_path = root / quest_source_path_func(quest_id)
        try:
            quest_payload = load_structured_object_func(quest_path)
        except FileNotFoundError:
            continue
        except Exception as exc:
            errors.append(f"{quest_path.relative_to(root)} must parse cleanly: {exc}")
            continue

        _validate_single_quest(
            errors,
            root=root,
            quest_id=quest_id,
            quest_path=quest_path,
            quest_payload=quest_payload,
            expected_lane=expected_lane,
            expected_state=expected_state,
            closed_quest_states=closed_quest_states,
            active_quest_ids=active_quest_ids,
            closed_quest_ids=closed_quest_ids,
        )

        try:
            expected_catalog.append(build_expected_quest_catalog_entry_func(quest_id, quest_payload))
            expected_dispatch.append(build_expected_quest_dispatch_entry_func(quest_id, quest_payload))
        except Exception as exc:
            errors.append(f"{quest_id} dispatch alignment failed: {exc}")

    for quest_id in active_quest_ids:
        if quest_id not in questbook_text:
            errors.append(f"QUESTBOOK.md must reference active quest id '{quest_id}'")
    for quest_id in closed_quest_ids:
        if quest_id in questbook_text:
            errors.append(f"QUESTBOOK.md must not list closed quest id '{quest_id}'")

    _validate_generated_quest_examples(
        errors,
        root=root,
        quest_catalog_example_path=quest_catalog_example_path,
        quest_dispatch_example_path=quest_dispatch_example_path,
        expected_catalog=expected_catalog,
        expected_dispatch=expected_dispatch,
    )

    flat_aliases = sorted((root / quest_surface_root).glob("ABYSS-STACK-Q-*.yaml"))
    for path in flat_aliases:
        errors.append(
            f"{path.relative_to(root).as_posix()} is a root quest alias; use quests/<lane>/<state>/"
        )


def _validate_single_quest(
    errors: list[str],
    *,
    root: Path,
    quest_id: str,
    quest_path: Path,
    quest_payload: dict[str, object],
    expected_lane: str,
    expected_state: str,
    closed_quest_states: Set[str],
    active_quest_ids: list[str],
    closed_quest_ids: list[str],
) -> None:
    if quest_payload.get("schema_version") != "work_quest_v1":
        errors.append(f"{quest_id} schema_version must equal 'work_quest_v1'")
    if quest_payload.get("id") != quest_id:
        errors.append(f"{quest_path.relative_to(root)} id must equal '{quest_id}'")
    if quest_payload.get("repo") != "abyss-stack":
        errors.append(f"{quest_id} repo must equal 'abyss-stack'")
    if quest_payload.get("lane") != expected_lane:
        errors.append(f"{quest_id} lane must equal '{expected_lane}'")
    if quest_payload.get("state") != expected_state:
        errors.append(f"{quest_id} state must match path state '{expected_state}'")
    if quest_payload.get("public_safe") is not True:
        errors.append(f"{quest_id} public_safe must be true")
    if quest_payload.get("state") in closed_quest_states:
        closed_quest_ids.append(quest_id)
    else:
        active_quest_ids.append(quest_id)

    notes = quest_payload.get("notes", "")
    if not isinstance(notes, str):
        errors.append(f"{quest_id} notes must be a string")
    elif "ATM10-Agent" in notes or "aoa-sdk" in notes:
        errors.append(f"{quest_id} notes must stay in scope for the current contour")

    if quest_id == "ABYSS-STACK-Q-0003":
        _validate_q0003(errors, quest_payload=quest_payload, notes=notes)
    elif quest_id == "ABYSS-STACK-Q-0005":
        _validate_q0005(errors, quest_payload=quest_payload, notes=notes)
    elif quest_id == "ABYSS-STACK-Q-0006":
        _validate_q0006(errors, quest_payload=quest_payload, notes=notes)
    elif quest_id == "ABYSS-STACK-Q-0007":
        _validate_q0007(errors, quest_payload=quest_payload, notes=notes)


def _validate_q0003(errors: list[str], *, quest_payload: dict[str, object], notes: object) -> None:
    if quest_payload.get("control_mode") != "human_gate":
        errors.append("ABYSS-STACK-Q-0003 control_mode must stay human_gate")
    if quest_payload.get("risk") != "r3_side_effect":
        errors.append("ABYSS-STACK-Q-0003 risk must stay r3_side_effect")
    anchor_ref = quest_payload.get("anchor_ref")
    if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md":
        errors.append("ABYSS-STACK-Q-0003 must stay anchored to mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md")
    note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
    if not isinstance(note, str) or "docs/install/FIRST_RUN.md" not in note or "mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md" not in note:
        errors.append("ABYSS-STACK-Q-0003 anchor note must mention docs/install/FIRST_RUN.md and mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md")


def _validate_q0005(errors: list[str], *, quest_payload: dict[str, object], notes: object) -> None:
    if quest_payload.get("kind") != "doctrine":
        errors.append("ABYSS-STACK-Q-0005 kind must stay doctrine")
    anchor_ref = quest_payload.get("anchor_ref")
    if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md":
        errors.append(
            "ABYSS-STACK-Q-0005 must stay anchored to mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_FRONTEND_POSTURE.md"
        )
    note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
    if not isinstance(note, str) or "shadow authority layer" not in note:
        errors.append(
            "ABYSS-STACK-Q-0005 anchor note must mention the shadow authority risk"
        )
    if not isinstance(notes, str) or "global rank engine" not in notes or "auto-complete quest writer" not in notes:
        errors.append(
            "ABYSS-STACK-Q-0005 notes must keep the runtime authority guardrail language"
        )


def _validate_q0006(errors: list[str], *, quest_payload: dict[str, object], notes: object) -> None:
    if quest_payload.get("kind") != "doctrine":
        errors.append("ABYSS-STACK-Q-0006 kind must stay doctrine")
    anchor_ref = quest_payload.get("anchor_ref")
    if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md":
        errors.append(
            "ABYSS-STACK-Q-0006 must stay anchored to mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_COLLECTIONS.md"
        )
    note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
    if not isinstance(note, str) or "read models" not in note or "route or quest authority" not in note:
        errors.append(
            "ABYSS-STACK-Q-0006 anchor note must mention read models and route or quest authority"
        )
    if not isinstance(notes, str) or "live /rpg/* endpoints" not in notes or "quest mutation" not in notes:
        errors.append(
            "ABYSS-STACK-Q-0006 notes must keep the no-live-endpoints and no-quest-mutation guardrails"
        )


def _validate_q0007(errors: list[str], *, quest_payload: dict[str, object], notes: object) -> None:
    if quest_payload.get("kind") != "doctrine":
        errors.append("ABYSS-STACK-Q-0007 kind must stay doctrine")
    anchor_ref = quest_payload.get("anchor_ref")
    if not isinstance(anchor_ref, dict) or anchor_ref.get("ref") != "mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md":
        errors.append(
            "ABYSS-STACK-Q-0007 must stay anchored to mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md"
        )
    note = anchor_ref.get("note") if isinstance(anchor_ref, dict) else ""
    if not isinstance(note, str) or "read model" not in note or "mutation authority" not in note:
        errors.append(
            "ABYSS-STACK-Q-0007 anchor note must mention read model and mutation authority"
        )
    if not isinstance(notes, str) or "free self-repair" not in notes or "runtime quest authority" not in notes:
        errors.append(
            "ABYSS-STACK-Q-0007 notes must keep the no-free-self-repair and no-runtime-quest-authority guardrails"
        )


def _validate_generated_quest_examples(
    errors: list[str],
    *,
    root: Path,
    quest_catalog_example_path: Path,
    quest_dispatch_example_path: Path,
    expected_catalog: list[dict[str, Any]],
    expected_dispatch: list[dict[str, Any]],
) -> None:
    try:
        catalog_payload = json.loads((root / quest_catalog_example_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        catalog_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{quest_catalog_example_path.as_posix()} must contain valid JSON: {exc}")
        catalog_payload = None
    if catalog_payload is not None and catalog_payload != expected_catalog:
        errors.append(
            f"{quest_catalog_example_path.as_posix()} must stay aligned with quests/<lane>/<state>/*.yaml"
        )

    try:
        dispatch_payload = json.loads((root / quest_dispatch_example_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        dispatch_payload = None
    except json.JSONDecodeError as exc:
        errors.append(f"{quest_dispatch_example_path.as_posix()} must contain valid JSON: {exc}")
        dispatch_payload = None
    if dispatch_payload is not None and dispatch_payload != expected_dispatch:
        errors.append(
            f"{quest_dispatch_example_path.as_posix()} must stay aligned with quests/<lane>/<state>/*.yaml"
        )
