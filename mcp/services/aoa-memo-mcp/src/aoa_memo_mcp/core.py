from __future__ import annotations

import json
import os
import re
import subprocess
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from ._runtime_config import PATH_CONFIG

REQUIRED_PORT_DIRS = ("candidates", "receipts", "exports", "local")
TEXT_SUFFIXES = {".md", ".json", ".txt", ".toml", ".yaml", ".yml"}
LOCAL_MEMO_PORT_LEVELS = {"stub_port", "full_port", "mature_port"}
LEGACY_MEMO_PORT_REPOS = ("Agents-of-Abyss", "abyss-stack", "abyss-machine")

OWNER_ORIENTATION_PIN = (
    "mechanics/federation-seams/parts/memo-seam/examples/"
    "codex_owner_orientation_runtime_compatibility_pin_v0.json"
)
ACTIVE_ORGAN_DELIVERY_SCHEMA = (
    "mechanics/federation-seams/parts/memo-seam/schemas/"
    "active-organ-runtime-delivery-receipt.schema.json"
)
OWNER_ORIENTATION_SHADOW_PIN = (
    "mechanics/federation-seams/parts/memo-seam/examples/"
    "codex_owner_orientation_shadow_runtime_compatibility_pin_v0.json"
)
ACTIVE_ORGAN_SHADOW_RECEIPT_SCHEMA = (
    "mechanics/federation-seams/parts/memo-seam/schemas/"
    "active-organ-shadow-runtime-receipt.schema.json"
)
OWNER_ORIENTATION_CANARY_PIN = (
    "mechanics/federation-seams/parts/memo-seam/examples/"
    "codex_owner_orientation_canary_runtime_compatibility_pin_v0.json"
)
ACTIVE_ORGAN_CANARY_RECEIPT_SCHEMA = (
    "mechanics/federation-seams/parts/memo-seam/schemas/"
    "active-organ-canary-runtime-receipt.schema.json"
)

MEMORY_CONTRACTS = [
    "docs/memory/MEMORY_OPERATION_CYCLE.md",
    "docs/memory/LIVING_MEMORY_TOPOLOGY.md",
    "docs/memory/LOCAL_MEMO_PORT_STANDARD.md",
    "docs/boundaries/MEMORY_WRITE_PATH_GUARDRAILS.md",
    "docs/posture/MEMORY_OPERATION_MODES.md",
    "mechanics/retention/docs/CONSOLIDATION_FORGETTING_OPERATION.md",
]
CENTRAL_VOCABULARY = "config/memory-ports/indexing_vocabulary.json"
LOCAL_PORT_INDEX = "index.min.json"
LOCAL_PORT_INDEX_MD = "INDEX.md"
LOCAL_PORT_CONTRACT = "PORT.yaml"
WORKSPACE_MEMORY_MAP = "generated/workspace_memory_map.min.json"
MEMORY_OBJECT_CATALOG = "generated/memory-objects/memory_object_catalog.min.json"
MEMORY_PORT_SCHEMA_DIR = "schemas/memory-ports"
LOCAL_MEMO_CANDIDATE_SCHEMA = "local_memo_candidate.schema.json"
LOCAL_MEMO_EXPORT_SCHEMA = "local_memo_export.schema.json"
LOCAL_MEMO_PORT_SCHEMA = "local_memo_port.schema.json"
LOCAL_MEMO_PORT_INDEX_SCHEMA = "local_memo_port_index.schema.json"
LOCAL_MEMO_RECEIPT_SCHEMA = "local_memo_receipt.schema.json"
FORMAT_CHECKER = FormatChecker()
SYMBOLIC_REF_PREFIXES = (
    "repo:",
    "http://",
    "https://",
    "web:",
    "operator:",
    "state_capsule:",
    "audit_event:",
    "claim:",
    "bridge:",
    "episode:",
    "memory:",
    "candidate:",
    "receipt:",
    "export:",
    "landing-receipt:",
)
LOCAL_LINE_REF_RE = re.compile(r"^(?P<path>.+):(?P<line>[0-9]+)$")
OPEN_REVIEW_STATES = {"candidate", "validated", "forwarded", "reviewed"}
TERMINAL_REVIEW_STATES = {"rejected", "landed", "superseded", "archived"}
FALLBACK_VOCABULARY_TERMS = {
    "kind": {"decision", "route", "pattern", "lesson", "constraint", "incident", "preference", "checkpoint", "handoff"},
    "family": {"memory-access", "runtime", "topology", "validation", "release", "agent-behavior", "provenance", "kag-bridge", "session-recovery"},
    "scope": {"session", "repo", "workspace", "project", "ecosystem", "host", "agent"},
    "route": {"local_only", "reviewed_intake", "owner_handoff", "quarantine", "archive"},
    "review_state": {"candidate", "validated", "rejected", "forwarded", "reviewed", "landed", "superseded", "archived"},
    "lifecycle": {"captured", "candidate", "reviewed", "current", "superseded", "retracted", "archived", "frozen"},
    "source_trust": {"review_required", "reviewed_owner_source", "untrusted", "unknown", "derived", "generated"},
    "risk": {
        "indirect_prompt_injection",
        "sleeper_memory",
        "poisoned_experience",
        "source_spoofing",
        "private_data_bleed",
        "instruction_as_content",
        "stale_context",
        "permission_leakage",
        "over_promotion",
        "hallucinated_merge",
    },
}


def _require_candidate_write_root(path: Path, *, label: str) -> None:
    policy_family = os.environ.get("AOA_MCP_POLICY_FAMILY", "").strip()
    if not policy_family:
        return
    if policy_family == "read":
        raise PermissionError(f"{label} is denied in the MCP read contour")
    if policy_family != "candidate":
        raise PermissionError(
            "AOA_MCP_POLICY_FAMILY must be read or candidate for MCP writes"
        )
    raw_roots = os.environ.get("AOA_MEMO_MCP_CANDIDATE_ROOTS", "").strip()
    if not raw_roots:
        raise PermissionError(
            "memo candidate writes require AOA_MEMO_MCP_CANDIDATE_ROOTS"
        )
    resolved_path = path.expanduser().resolve()
    for raw_root in raw_roots.split(os.pathsep):
        if not raw_root:
            continue
        configured_root = Path(raw_root).expanduser()
        if not configured_root.is_absolute():
            raise PermissionError(
                "AOA_MEMO_MCP_CANDIDATE_ROOTS must contain absolute paths"
            )
        if configured_root.is_symlink():
            raise PermissionError(
                "AOA_MEMO_MCP_CANDIDATE_ROOTS must not contain symlink roots"
            )
        resolved_root = configured_root.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            continue
        return
    raise PermissionError(
        f"{label} must stay inside an allowlisted memo candidate root"
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _id_slug(text: str, limit: int = 48) -> str:
    lowered = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return (slug or "memo")[:limit].strip("-") or "memo"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_yaml(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def _render_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _canonical_digest(
    payload: dict[str, Any],
    *,
    exclude: set[str] | None = None,
    ensure_ascii: bool = True,
) -> str:
    filtered = {
        key: value
        for key, value in payload.items()
        if key not in (exclude or set())
    }
    encoded = json.dumps(
        filtered,
        ensure_ascii=ensure_ascii,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _artifact_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _parse_aware_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _iso_timestamp(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _stack_source_root() -> Path:
    configured = os.environ.get(PATH_CONFIG.stack_root_env_var)
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser().resolve())
    candidates.append(Path(__file__).resolve().parents[5])
    for candidate in candidates:
        if (candidate / OWNER_ORIENTATION_PIN).is_file():
            return candidate
    raise ValueError(
        "owner-orientation runtime requires an explicit current abyss-stack source root"
    )


def _validate_owner_orientation_inputs(
    *,
    plan: dict[str, Any],
    memo_bundle: dict[str, Any],
    compatibility_pin: dict[str, Any],
) -> None:
    required_plan_keys = {
        "schema_version",
        "plan_id",
        "consumer_id",
        "consumer_mode",
        "status",
        "recall_intent",
        "profile_ref",
        "profile_digest",
        "query_digest",
        "memory_object_catalog_version",
        "memory_object_catalog_ref",
        "memory_object_capsules_ref",
        "memory_object_sections_ref",
        "selection_algorithm",
        "budget",
        "items",
        "omissions",
        "host_capability_ref",
        "host_resource_plan_ref",
        "planned_at",
        "expires_at",
        "no_memory_fallback",
        "memory_write_performed",
        "policy_promotion_performed",
        "effect_authority",
        "action_use",
        "plan_digest",
    }
    if set(plan) != required_plan_keys:
        raise ValueError("owner-orientation plan shape is unknown or incomplete")
    if (
        plan["schema_version"] != compatibility_pin["accepted_plan_version"]
        or plan["consumer_id"] != "codex_owner_orientation_v0"
        or plan["selection_algorithm"]
        != "current-source-plus-deterministic-lexical-v1"
    ):
        raise ValueError("owner-orientation plan version or consumer is not admitted")
    if plan["plan_digest"] != _canonical_digest(
        plan,
        exclude={"plan_digest"},
    ):
        raise ValueError("owner-orientation plan digest is invalid")
    profile_pin = compatibility_pin["memo_consumer_profile"]
    if (
        plan["profile_ref"]["owner_repo"] != "aoa-memo"
        or plan["profile_ref"]["artifact_digest"] != profile_pin["sha256"]
        or plan["profile_digest"] != profile_pin["semantic_digest"]
    ):
        raise ValueError("owner-orientation profile pin drifted")
    if (
        plan["effect_authority"] != "none"
        or plan["action_use"] != "forbidden"
        or plan["memory_write_performed"]
        or plan["policy_promotion_performed"]
    ):
        raise ValueError("owner-orientation plan attempted to widen authority")

    intent = plan["recall_intent"]
    policy_pin = compatibility_pin["memo_influence_policy"]
    if (
        intent.get("contract_id") != "C07"
        or intent.get("consumer_id") != plan["consumer_id"]
        or intent.get("trigger_id") != "operator-explicit-pull"
        or intent.get("mode") != "explicit_public_pull"
        or intent.get("data_class") != "D0"
        or intent.get("risk_class") != "R1"
        or intent.get("effect_ceiling") != "none"
        or intent.get("action_use") != "forbidden"
        or intent.get("policy_pin", {}).get("policy_digest")
        != policy_pin["sha256"]
    ):
        raise ValueError("owner-orientation C07 admission tuple drifted")
    if any(
        ref.get("owner_repo") == ".aoa"
        or str(ref.get("artifact_ref", "")).startswith(".aoa/")
        or str(ref.get("source_ref", "")).startswith("repo:.aoa/")
        for ref in intent.get("source_refs", [])
    ):
        raise ValueError("owner-orientation cannot deliver raw .aoa refs")
    anchor_expires = intent.get("anchor_freshness", {}).get("expires_at")
    if anchor_expires is not None and _parse_aware_timestamp(
        intent.get("expires_at", plan["expires_at"]),
        "recall intent expires_at",
    ) > _parse_aware_timestamp(anchor_expires, "anchor expires_at"):
        raise ValueError("recall intent cannot outlive its current anchor")
    for contract_id, field_name in (
        ("C18", "host_capability_ref"),
        ("C19", "host_resource_plan_ref"),
    ):
        ref = plan[field_name]
        searchable = " ".join(
            str(ref.get(key, ""))
            for key in ("artifact_ref", "source_ref", "schema_ref")
        ).casefold()
        if ref.get("owner_repo") != "abyss-machine" or (
            contract_id.casefold() not in searchable
        ):
            raise ValueError(f"owner-orientation requires exact {contract_id} host evidence")

    mode = plan["consumer_mode"]
    status = plan["status"]
    items = plan["items"]
    budget = plan["budget"]
    if mode == "off" and (status != "off" or items or budget is not None):
        raise ValueError("off plan must remain a no-memory plan")
    if mode == "fresh-start" and (
        status != "no_memory" or items or budget is not None
    ):
        raise ValueError("fresh-start plan must remain a no-memory plan")
    if mode in {"bounded", "high-fidelity"}:
        if not isinstance(budget, dict):
            raise ValueError("memory-bearing plan requires an exact budget")
        if len(items) > budget.get("max_items", -1):
            raise ValueError("owner-orientation plan exceeds item budget")
        if sum(item.get("estimated_tokens", 0) for item in items) > budget.get(
            "max_estimated_tokens",
            -1,
        ):
            raise ValueError("owner-orientation plan exceeds token budget")
        if status != ("bounded_memory" if items else "silence"):
            raise ValueError("owner-orientation plan status and items disagree")
    for ordinal, item in enumerate(items, start=1):
        card = item.get("card", {})
        capsule = item.get("capsule", {})
        if (
            item.get("ordinal") != ordinal
            or card.get("source_kind") != "reviewed_corpus"
            or card.get("review_state") != "confirmed"
            or card.get("current_recall_status") not in {"preferred", "allowed"}
            or capsule.get("source_kind") != "reviewed_corpus"
        ):
            raise ValueError("owner-orientation item is not current reviewed memory")
        content = {
            "card": card,
            "capsule": capsule,
            "expanded": item.get("expanded"),
            "source_route": item.get("source_route"),
        }
        if item.get("content_digest") != _canonical_digest(content):
            raise ValueError("owner-orientation item content digest is invalid")
        if mode == "bounded" and item.get("expanded") is not None:
            raise ValueError("bounded owner-orientation cannot carry expansion")
        if mode == "high-fidelity" and item.get("expanded") is None:
            raise ValueError("high-fidelity owner-orientation requires expansion")

    required_bundle_keys = {
        "schema_version",
        "semantic_owner",
        "control_plane_owner",
        "runtime_delivery_owner",
        "plan_ref",
        "plan_digest",
        "recall_packet",
        "intervention_decision",
        "delivery_eligible",
        "effect_authority",
        "action_use",
        "memory_write_performed",
        "bundle_digest",
    }
    if set(memo_bundle) != required_bundle_keys:
        raise ValueError("memo owner-orientation bundle shape is unknown or incomplete")
    if (
        memo_bundle["schema_version"]
        != compatibility_pin["accepted_bundle_version"]
        or memo_bundle["semantic_owner"] != "aoa-memo"
        or memo_bundle["control_plane_owner"] != "aoa-sdk"
        or memo_bundle["runtime_delivery_owner"] != "abyss-stack"
        or memo_bundle["plan_digest"] != plan["plan_digest"]
        or memo_bundle["effect_authority"] != "none"
        or memo_bundle["action_use"] != "forbidden"
        or memo_bundle["memory_write_performed"]
        or not memo_bundle["delivery_eligible"]
    ):
        raise ValueError("memo owner-orientation bundle authority or plan pin drifted")
    if memo_bundle["bundle_digest"] != _canonical_digest(
        memo_bundle,
        exclude={"bundle_digest"},
    ):
        raise ValueError("memo owner-orientation bundle digest is invalid")

    packet = memo_bundle["recall_packet"]
    decision = memo_bundle["intervention_decision"]
    for payload, contract_id in ((packet, "C08"), (decision, "C09")):
        if (
            payload.get("contract_id") != contract_id
            or payload.get("owner") != "aoa-memo"
            or payload.get("validation_status") != "valid"
            or payload.get("content_digest")
            != _canonical_digest(
                payload,
                exclude={"content_digest"},
                ensure_ascii=False,
            )
        ):
            raise ValueError(f"memo {contract_id} owner envelope is invalid")
    expected_packet_mode = (
        "bounded_memory" if status == "bounded_memory" else "silence"
    )
    expected_decision = (
        "bounded_observation"
        if expected_packet_mode == "bounded_memory"
        else "silence"
    )
    if (
        packet.get("result_mode") != expected_packet_mode
        or packet.get("action_use") != "forbidden"
        or decision.get("recall_packet_ref") != packet.get("instance_id")
        or decision.get("decision") != expected_decision
        or decision.get("effect_authority") != "none"
        or decision.get("observation_refs") != packet.get("result_refs")
        or len(packet.get("object_pins", [])) != len(items)
    ):
        raise ValueError("memo C08/C09 bundle disagrees with the admitted SDK plan")


def _validate_shadow_orientation_inputs(
    *,
    plan: dict[str, Any],
    memo_bundle: dict[str, Any],
    host_admission: dict[str, Any],
    plan_schema: dict[str, Any],
    bundle_schema: dict[str, Any],
    compatibility_pin: dict[str, Any],
) -> None:
    for label, schema, payload in (
        ("SDK shadow plan", plan_schema, plan),
        ("memo shadow bundle", bundle_schema, memo_bundle),
    ):
        errors = sorted(
            Draft202012Validator(
                schema,
                format_checker=FORMAT_CHECKER,
            ).iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = (
                "/".join(str(item) for item in error.absolute_path)
                or "<root>"
            )
            raise ValueError(f"{label} {location}: {error.message}")

    if (
        plan["schema_version"] != compatibility_pin["accepted_plan_version"]
        or plan["consumer_id"] != "codex_owner_orientation_shadow_v0"
        or plan["selection_algorithm"]
        != "current-source-plus-deterministic-lexical-shadow-v1"
        or plan["plan_digest"]
        != _canonical_digest(plan, exclude={"plan_digest"})
    ):
        raise ValueError("shadow plan version, consumer, algorithm, or digest drifted")
    profile_pin = compatibility_pin["memo_consumer_profile"]
    policy_pin = compatibility_pin["memo_influence_policy"]
    intent = plan["recall_intent"]
    if (
        plan["profile_ref"]["owner_repo"] != "aoa-memo"
        or plan["profile_ref"]["artifact_digest"] != profile_pin["sha256"]
        or plan["profile_digest"] != profile_pin["semantic_digest"]
        or intent.get("contract_id") != "C07"
        or intent.get("consumer_id") != plan["consumer_id"]
        or intent.get("trigger_id") != "owner-task-pressure-shadow"
        or intent.get("mode") != "shadow_observation"
        or intent.get("data_class") != "D0"
        or intent.get("risk_class") != "R4"
        or intent.get("effect_ceiling") != "none"
        or intent.get("action_use") != "forbidden"
        or intent.get("policy_pin", {}).get("policy_digest")
        != policy_pin["sha256"]
    ):
        raise ValueError("shadow plan profile or C07 admission tuple drifted")
    denied_plan_flags = (
        "consumer_visible",
        "delivery_authorized",
        "content_persisted",
        "candidate_persisted",
        "memory_write_performed",
        "semantic_transition_performed",
        "policy_promotion_performed",
    )
    if (
        any(plan[field] for field in denied_plan_flags)
        or plan["effect_authority"] != "none"
        or plan["action_use"] != "forbidden"
    ):
        raise ValueError("shadow plan attempted delivery, persistence, or authority")
    refs = [
        *intent["source_refs"],
        plan["pressure_evidence_ref"],
        plan["currentness_probe_ref"],
        plan["erase_reconciliation_ref"],
        *plan["outcome_refs"],
    ]
    if any(
        ref.get("owner_repo") == ".aoa"
        or str(ref.get("artifact_ref", "")).startswith(".aoa/")
        or str(ref.get("source_ref", "")).startswith("repo:.aoa/")
        for ref in refs
    ):
        raise ValueError("shadow runtime cannot consume raw .aoa refs")
    if (
        plan["pressure_evidence_ref"]["owner_repo"] != "aoa-memo"
        or plan["erase_reconciliation_ref"]["owner_repo"] != "aoa-memo"
        or not plan["outcome_refs"]
        or any(ref["owner_repo"] != "aoa-stats" for ref in plan["outcome_refs"])
    ):
        raise ValueError("shadow runtime owner refs drifted")
    for item in plan["items"]:
        content = {
            "card": item["card"],
            "capsule": item["capsule"],
            "expanded": item["expanded"],
            "source_route": item["source_route"],
        }
        if (
            item["content_digest"] != _canonical_digest(content)
            or item["card"]["source_kind"] != "reviewed_corpus"
            or item["card"]["review_state"] != "confirmed"
            or item["card"]["current_recall_status"]
            not in {"preferred", "allowed"}
            or item["expanded"] is not None
        ):
            raise ValueError("shadow runtime received invalid selected memory")

    if (
        memo_bundle["schema_version"]
        != compatibility_pin["accepted_bundle_version"]
        or memo_bundle["plan_digest"] != plan["plan_digest"]
        or memo_bundle["bundle_digest"]
        != _canonical_digest(memo_bundle, exclude={"bundle_digest"})
    ):
        raise ValueError("memo shadow bundle version, plan pin, or digest drifted")
    denied_bundle_flags = (
        "consumer_visible",
        "delivery_eligible",
        "runtime_delivery_requested",
        "content_persisted",
        "candidate_persisted",
        "memory_write_performed",
        "semantic_transition_performed",
        "policy_promotion_performed",
    )
    if (
        any(memo_bundle[field] for field in denied_bundle_flags)
        or memo_bundle["effect_authority"] != "none"
        or memo_bundle["action_use"] != "forbidden"
    ):
        raise ValueError("memo shadow bundle attempted delivery or mutation")
    ingress = memo_bundle["pressure_ingress"]
    expected_ingress = (
        ("evidence_envelope", "C01"),
        ("candidate_packet", "C02"),
    )
    for field, contract_id in expected_ingress:
        if ingress[field].get("contract_id") != contract_id:
            raise ValueError("memo shadow ingress contract sequence drifted")
    quarantine = ingress["quarantine_packet"]
    if (
        plan["pressure_state"] == "quarantine_required"
        and (not isinstance(quarantine, dict) or quarantine.get("contract_id") != "C03")
    ):
        raise ValueError("quarantined pressure requires exact C03")
    if plan["pressure_state"] == "clean" and quarantine is not None:
        raise ValueError("clean pressure must not fabricate C03")
    for payload, contract_id in (
        (memo_bundle["recall_packet"], "C08"),
        (memo_bundle["intervention_decision"], "C09"),
    ):
        if (
            payload.get("contract_id") != contract_id
            or payload.get("owner") != "aoa-memo"
            or payload.get("content_digest")
            != _canonical_digest(
                payload,
                exclude={"content_digest"},
                ensure_ascii=False,
            )
        ):
            raise ValueError(f"memo shadow {contract_id} envelope is invalid")
    expected_result = (
        "bounded_memory" if plan["status"] == "bounded_memory" else "silence"
    )
    expected_decision = (
        "bounded_observation"
        if expected_result == "bounded_memory"
        else "silence"
    )
    if (
        memo_bundle["recall_packet"]["result_mode"] != expected_result
        or memo_bundle["intervention_decision"]["decision"]
        != expected_decision
        or memo_bundle["host_disposition"] != plan["host_disposition"]
        or memo_bundle["metabolism"]["policy_posture"]
        != plan["policy_posture"]
        or memo_bundle["metabolism"]["semantic_transition_performed"]
        or memo_bundle["metabolism"]["proposal_accepted"]
    ):
        raise ValueError("memo shadow bundle disagrees with the SDK plan")

    required_host_keys = {
        "schema_version",
        "owner",
        "workload_id",
        "consumer_id",
        "capability_snapshot_ref",
        "capability_snapshot_digest",
        "resource_plan_ref",
        "resource_plan_digest",
        "host_disposition",
        "softening_constraints",
        "reason_codes",
        "admitted_at",
        "expires_at",
        "launch_executed",
        "project_root_mutation",
        "stack_root_mutation",
        "memory_semantic_authority",
        "effect_authority",
        "admission_digest",
    }
    if set(host_admission) != required_host_keys:
        raise ValueError("host shadow admission shape is unknown or incomplete")
    if (
        host_admission["schema_version"]
        != "abyss_machine_shadow_workload_admission_v0"
        or host_admission["owner"] != "abyss-machine"
        or host_admission["consumer_id"] != "abyss-stack"
        or host_admission["host_disposition"] != plan["host_disposition"]
        or host_admission["capability_snapshot_digest"]
        != plan["host_capability_ref"]["artifact_digest"]
        or host_admission["resource_plan_digest"]
        != plan["host_resource_plan_ref"]["artifact_digest"]
        or host_admission["launch_executed"]
        or host_admission["project_root_mutation"] != "forbidden"
        or host_admission["stack_root_mutation"] != "forbidden"
        or host_admission["memory_semantic_authority"] != "none"
        or host_admission["effect_authority"] != "host_admission_only"
        or host_admission["admission_digest"]
        != _canonical_digest(host_admission, exclude={"admission_digest"})
    ):
        raise ValueError("host shadow admission authority or digest drifted")


def _validate_canary_orientation_inputs(
    *,
    release_plan: dict[str, Any],
    shadow_plan: dict[str, Any],
    shadow_bundle: dict[str, Any],
    canary_bundle: dict[str, Any],
    host_admission: dict[str, Any],
    release_plan_schema: dict[str, Any],
    shadow_plan_schema: dict[str, Any],
    shadow_bundle_schema: dict[str, Any],
    canary_bundle_schema: dict[str, Any],
    compatibility_pin: dict[str, Any],
) -> None:
    for label, schema, payload in (
        ("SDK canary release plan", release_plan_schema, release_plan),
        ("SDK source shadow plan", shadow_plan_schema, shadow_plan),
        ("memo source shadow bundle", shadow_bundle_schema, shadow_bundle),
        ("memo canary bundle", canary_bundle_schema, canary_bundle),
    ):
        errors = sorted(
            Draft202012Validator(
                schema,
                format_checker=FORMAT_CHECKER,
            ).iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = (
                "/".join(str(item) for item in error.absolute_path)
                or "<root>"
            )
            raise ValueError(f"{label} {location}: {error.message}")

    if (
        release_plan["schema_version"]
        != compatibility_pin["accepted_release_plan_version"]
        or shadow_plan["schema_version"]
        != compatibility_pin["accepted_shadow_plan_version"]
        or shadow_bundle["schema_version"]
        != compatibility_pin["accepted_shadow_bundle_version"]
        or canary_bundle["schema_version"]
        != compatibility_pin["accepted_canary_bundle_version"]
    ):
        raise ValueError("canary runtime received an unknown contract version")
    if (
        release_plan["plan_digest"]
        != _canonical_digest(release_plan, exclude={"plan_digest"})
        or shadow_plan["plan_digest"]
        != _canonical_digest(shadow_plan, exclude={"plan_digest"})
        or shadow_bundle["bundle_digest"]
        != _canonical_digest(shadow_bundle, exclude={"bundle_digest"})
        or canary_bundle["bundle_digest"]
        != _canonical_digest(canary_bundle, exclude={"bundle_digest"})
    ):
        raise ValueError("canary runtime artifact self-digest is invalid")

    profile_pin = compatibility_pin["memo_consumer_profile"]
    policy_pin = compatibility_pin["memo_influence_policy"]
    if (
        release_plan["consumer_id"] != compatibility_pin["consumer_id"]
        or release_plan["profile_ref"]["owner_repo"] != "aoa-memo"
        or release_plan["profile_ref"]["artifact_digest"]
        != profile_pin["sha256"]
        or release_plan["profile_digest"] != profile_pin["semantic_digest"]
        or release_plan["policy_ref"]["owner_repo"] != "aoa-memo"
        or release_plan["policy_ref"]["artifact_digest"]
        != policy_pin["sha256"]
        or release_plan["policy_digest"] != policy_pin["sha256"]
        or release_plan["assignment_ref"]["owner_repo"] != "aoa-evals"
        or release_plan["always_shadow_counterfactual_ref"]["owner_repo"]
        != "aoa-evals"
        or not release_plan["outcome_refs"]
        or any(
            ref["owner_repo"] != "aoa-stats"
            for ref in release_plan["outcome_refs"]
        )
    ):
        raise ValueError("canary profile, policy, experiment, or outcome pin drifted")
    if any(
        ref.get("owner_repo") == ".aoa"
        or str(ref.get("artifact_ref", "")).startswith(".aoa/")
        or str(ref.get("source_ref", "")).startswith("repo:.aoa/")
        for ref in (
            release_plan["source_shadow_plan_ref"],
            release_plan["source_shadow_bundle_ref"],
            release_plan["profile_ref"],
            release_plan["policy_ref"],
            release_plan["assignment_ref"],
            release_plan["always_shadow_counterfactual_ref"],
            release_plan["currentness_probe_ref"],
            *release_plan["outcome_refs"],
        )
    ):
        raise ValueError("canary runtime cannot consume raw .aoa refs")
    if (
        release_plan["source_shadow_plan_ref"]["owner_repo"] != "aoa-sdk"
        or release_plan["source_shadow_plan_digest"]
        != shadow_plan["plan_digest"]
        or release_plan["source_shadow_plan_ref"]["artifact_digest"]
        != shadow_plan["plan_digest"]
        or release_plan["source_shadow_bundle_ref"]["owner_repo"] != "aoa-memo"
        or release_plan["source_shadow_bundle_digest"]
        != shadow_bundle["bundle_digest"]
        or release_plan["source_shadow_bundle_ref"]["artifact_digest"]
        != shadow_bundle["bundle_digest"]
        or shadow_plan["consumer_id"]
        != "codex_owner_orientation_shadow_v0"
        or shadow_plan["shadow_mode"] != "selective"
        or shadow_plan["consumer_visible"]
        or shadow_plan["delivery_authorized"]
    ):
        raise ValueError("canary release drifted from its frozen shadow source")

    denied_plan_flags = (
        "content_persisted",
        "candidate_persisted",
        "memory_write_performed",
        "semantic_transition_performed",
        "policy_promotion_performed",
        "directive_authority",
    )
    if (
        any(release_plan[field] for field in denied_plan_flags)
        or release_plan["effect_authority"] != "none"
        or release_plan["action_use"] != "forbidden"
        or release_plan["rollback_target"]
        != compatibility_pin["rollback_target"]
        or release_plan["max_reminders"]
        != compatibility_pin["max_reminders_per_window"]
    ):
        raise ValueError("canary release attempted mutation or authority widening")

    if (
        canary_bundle["semantic_owner"] != "aoa-memo"
        or canary_bundle["control_plane_owner"] != "aoa-sdk"
        or canary_bundle["runtime_owner"] != "abyss-stack"
        or canary_bundle["host_owner"] != "abyss-machine"
        or canary_bundle["outcome_owner"] != "aoa-stats"
        or canary_bundle["proof_owner"] != "aoa-evals"
        or canary_bundle["release_plan_digest"] != release_plan["plan_digest"]
        or canary_bundle["source_shadow_plan_digest"]
        != shadow_plan["plan_digest"]
        or canary_bundle["source_shadow_bundle_digest"]
        != shadow_bundle["bundle_digest"]
        or canary_bundle["assigned_arm"] != release_plan["assigned_arm"]
        or canary_bundle["assignment_ref"]
        != release_plan["assignment_ref"]["source_ref"]
        or canary_bundle["window_id"] != release_plan["window_id"]
        or canary_bundle["rollback_target"]
        != compatibility_pin["rollback_target"]
    ):
        raise ValueError("memo canary bundle owner or source binding drifted")
    denied_bundle_flags = (
        "directive_authority",
        "content_persisted",
        "candidate_persisted",
        "memory_write_performed",
        "semantic_transition_performed",
        "policy_promotion_performed",
    )
    if (
        any(canary_bundle[field] for field in denied_bundle_flags)
        or canary_bundle["effect_authority"] != "none"
        or canary_bundle["action_use"] != "forbidden"
    ):
        raise ValueError("memo canary bundle attempted mutation or authority widening")

    packet = canary_bundle["recall_packet"]
    decision = canary_bundle["intervention_decision"]
    for payload, contract_id in ((packet, "C08"), (decision, "C09")):
        if (
            payload.get("contract_id") != contract_id
            or payload.get("owner") != "aoa-memo"
            or payload.get("content_digest")
            != _canonical_digest(
                payload,
                exclude={"content_digest"},
                ensure_ascii=False,
            )
        ):
            raise ValueError(f"memo canary {contract_id} envelope is invalid")

    bounded = release_plan["status"] == "bounded_observation"
    observation = canary_bundle["observation"]
    if bounded:
        if (
            len(release_plan["items"]) != 1
            or not isinstance(observation, dict)
            or not canary_bundle["consumer_visible"]
            or not canary_bundle["delivery_eligible"]
            or packet["result_mode"] != "bounded_memory"
            or decision["decision"] != "bounded_observation"
            or release_plan["assigned_arm"] != "canary"
            or release_plan["secret_detected"]
            or release_plan["currentness_state"] != "current"
            or release_plan["eval_status"] != "available"
            or release_plan["host_disposition"] != "start"
        ):
            raise ValueError("bounded canary bundle violates release admission")
        source_item = shadow_plan["items"][0]
        release_item = release_plan["items"][0]
        if (
            source_item["card"]["id"] != release_item["object_id"]
            or source_item["content_digest"] != release_item["content_digest"]
            or source_item["source_route"] != release_item["source_route"]
            or observation["object_id"] != release_item["object_id"]
            or observation["source_route"] != release_item["source_route"]
            or observation["currentness"]
            != source_item["card"]["current_recall_status"]
            or observation["directive"]
            or observation["suggested_action"] is not None
            or not observation["source_visible"]
            or not observation["currentness_visible"]
            or observation["content_digest"]
            != _canonical_digest(observation, exclude={"content_digest"})
        ):
            raise ValueError("canary observation drifted from the frozen shadow item")
    elif (
        release_plan["items"]
        or observation is not None
        or canary_bundle["consumer_visible"]
        or canary_bundle["delivery_eligible"]
        or packet["result_mode"] != "silence"
        or decision["decision"] != "silence"
    ):
        raise ValueError("non-delivery canary bundle attempted consumer output")

    required_host_keys = {
        "schema_version",
        "owner",
        "workload_id",
        "consumer_id",
        "capability_snapshot_ref",
        "capability_snapshot_digest",
        "resource_plan_ref",
        "resource_plan_digest",
        "host_disposition",
        "softening_constraints",
        "reason_codes",
        "admitted_at",
        "expires_at",
        "launch_executed",
        "project_root_mutation",
        "stack_root_mutation",
        "memory_semantic_authority",
        "effect_authority",
        "memory_consumer_id",
        "delivery_semantic_authority",
        "canary_effect_authority",
        "admission_digest",
    }
    if set(host_admission) != required_host_keys:
        raise ValueError("host canary admission shape is unknown or incomplete")
    if (
        host_admission["schema_version"]
        != "abyss_machine_canary_workload_admission_v0"
        or host_admission["owner"] != "abyss-machine"
        or host_admission["consumer_id"] != "abyss-stack"
        or host_admission["memory_consumer_id"] != release_plan["consumer_id"]
        or host_admission["host_disposition"]
        != release_plan["host_disposition"]
        or host_admission["capability_snapshot_digest"]
        != release_plan["host_capability_ref"]["artifact_digest"]
        or host_admission["resource_plan_digest"]
        != release_plan["host_resource_plan_ref"]["artifact_digest"]
        or host_admission["launch_executed"]
        or host_admission["project_root_mutation"] != "forbidden"
        or host_admission["stack_root_mutation"] != "forbidden"
        or host_admission["memory_semantic_authority"] != "none"
        or host_admission["delivery_semantic_authority"] != "none"
        or host_admission["canary_effect_authority"] != "none"
        or host_admission["effect_authority"] != "host_admission_only"
        or host_admission["admission_digest"]
        != _canonical_digest(host_admission, exclude={"admission_digest"})
    ):
        raise ValueError("host canary admission authority or digest drifted")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass(slots=True)
class RepoRoute:
    name: str
    source_root: Path | None
    memo_port: Path | None
    default_mode: str
    owner_note: str


@dataclass(slots=True)
class AoAMemoMCPState:
    workspace_root: Path

    @classmethod
    def discover(cls, workspace_root: str | Path | None = None) -> "AoAMemoMCPState":
        root = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or PATH_CONFIG.workspace_root()
        ).expanduser().resolve()
        return cls(workspace_root=root)

    @property
    def aoa_memo_root(self) -> Path:
        return self.workspace_root / "aoa-memo"

    @property
    def aoa_archive_root(self) -> Path:
        return self.workspace_root / ".aoa"

    def repo_route(self, repo: str) -> RepoRoute:
        normalized = self._normalize_repo(repo)
        if normalized == ".aoa":
            source = self.aoa_archive_root
            return RepoRoute(
                name=".aoa",
                source_root=source.resolve() if source.exists() else None,
                memo_port=None,
                default_mode="read_only",
                owner_note="session evidence kernel; use rehydrate/retrieve routes before reviewed memory intake",
            )
        if normalized == "abyss-stack":
            source = PATH_CONFIG.stack_source_root()
            source = source if source.exists() else None
            return RepoRoute(
                name="abyss-stack",
                source_root=source.resolve() if source else None,
                memo_port=(source / "memo").resolve() if source else None,
                default_mode="write_candidate_only",
                owner_note="runtime substrate source checkout; runtime mirror is not the source repo",
            )
        if normalized == "abyss-machine":
            policy_path = PATH_CONFIG.abyss_machine_policy_root(
                os.environ.get("AOA_ABYSS_MACHINE_POLICY_ROOT")
            )
            memo_root = os.environ.get("AOA_ABYSS_MACHINE_MEMO_ROOT")
            machine_state_root = PATH_CONFIG.abyss_machine_state_root()
            memo_port = (
                Path(memo_root).expanduser().resolve()
                if memo_root
                else (machine_state_root / "memo" if machine_state_root else None)
            )
            policy = policy_path if policy_path and policy_path.exists() else None
            return RepoRoute(
                name="abyss-machine",
                source_root=policy,
                memo_port=memo_port,
                default_mode="write_candidate_only",
                owner_note="host-local memory port; policy remains under the configured abyss-machine policy root",
            )
        source = self.workspace_root / normalized
        place = self._workspace_memory_place(normalized)
        default_mode = "write_candidate_only"
        owner_note = "repo-local memory candidate port"
        if place:
            memory_role = str(place.get("memory_role") or "")
            current_level = str(place.get("current_port_level") or "")
            if memory_role == "reviewed-memory-owner":
                default_mode = "read_write_under_review"
                owner_note = "reviewed memory authority; durable memory lands here through source changes and validators"
            elif current_level == "route_only":
                default_mode = "read_only"
                owner_note = "route-only workspace surface; use aoa_memo for recall and the workspace memory map for local-port status"
        return RepoRoute(
            name=normalized,
            source_root=source.resolve() if source.exists() else None,
            memo_port=(source / "memo").resolve() if source.exists() else None,
            default_mode=default_mode,
            owner_note=owner_note,
        )

    def build_brief(self, repo: str, intent: str = "") -> dict[str, Any]:
        route = self.repo_route(repo)
        port = self.build_local_port_status(repo)
        return {
            "schema": "aoa_memo_brief_v1",
            "repo": route.name,
            "intent": intent,
            "operation_mode": route.default_mode,
            "owner_note": route.owner_note,
            "source_hierarchy": [
                "current repository evidence",
                self._local_port_hierarchy_note(port),
                "aoa-memo reviewed memory contracts",
                ".aoa raw session archive evidence",
                "derived MCP brief/search output",
            ],
            "local_port": port,
            "memory_route": {
                "brief": "aoa_memo_brief",
                "candidate": self._candidate_route_note(route, port),
                "validate": "aoa_memo_validate_candidate and aoa_memo_validate_port",
                "export": "aoa_memo_prepare_intake_packet",
                "forwarding_check": "aoa_memo_review_intake writes a local check receipt only",
                "durable_landing": "reviewed source patch in aoa-memo, not MCP direct write",
            },
            "workspace_memory_map": self._workspace_memory_summary(route.name),
            "reviewed_memory": self._reviewed_memory_for_repo(route.name, intent),
            "local_intake": self._local_intake_summary(route.name, port),
            "central_memory_contracts": self._central_contracts(),
            "recommended_route": self._recommended_route(route, port),
            "validation": [
                "python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py",
                "python -m pytest mcp/services/aoa-memo-mcp/tests -q",
                str(
                    PATH_CONFIG.workspace_root()
                    / "aoa-memo"
                    / "scripts"
                    / "memory"
                    / "validate_memory_operations.py"
                ),
            ],
        }

    def build_reviewed_brief(self, repo: str, intent: str = "") -> dict[str, Any]:
        """Return only accepted durable-memory rows and their authority posture."""

        route = self.repo_route(repo)
        return {
            "schema": "aoa_memo_reviewed_brief_v1",
            "repo": route.name,
            "intent": intent,
            "reviewed_memory": self._reviewed_memory_for_repo(route.name, intent),
            "source_owner": "aoa-memo",
            "source_catalog": str(self.aoa_memo_root / MEMORY_OBJECT_CATALOG),
            "access_projection": "reviewed_corpus_only",
            "authority_boundary": (
                "Reviewed memory is durable recall, not proof, current source truth, "
                "routing authority, runtime state, or permission."
            ),
            "state_law": (
                "Current, stale, superseded, retracted, and quarantined recall states "
                "remain distinct and must be checked on the source object."
            ),
            "next_route": "open the exact reviewed object and then verify its stronger owner source",
            "candidate_route_exposed": False,
            "durable_write_authorized": False,
        }

    def deliver_owner_orientation(
        self,
        *,
        plan: dict[str, Any],
        memo_bundle: dict[str, Any],
        observed_at: str | None = None,
        target_ref: str = "codex:current-request",
        attempt_no: int = 1,
    ) -> dict[str, Any]:
        """Return one already-admitted memo packet without reselecting or persisting."""

        if attempt_no < 1:
            raise ValueError("attempt_no must be positive")
        stack_root = _stack_source_root()
        pin_path = stack_root / OWNER_ORIENTATION_PIN
        schema_path = stack_root / ACTIVE_ORGAN_DELIVERY_SCHEMA
        compatibility_pin = _read_json(pin_path)
        delivery_schema = _read_json(schema_path)
        if not isinstance(compatibility_pin, dict):
            raise ValueError("owner-orientation runtime compatibility pin is unavailable")
        if not isinstance(delivery_schema, dict):
            raise ValueError("C20 runtime delivery schema is unavailable")
        if (
            _artifact_digest(schema_path)
            != compatibility_pin["runtime_receipt_schema"]["sha256"]
        ):
            raise ValueError("C20 runtime delivery schema digest drifted")
        _validate_owner_orientation_inputs(
            plan=plan,
            memo_bundle=memo_bundle,
            compatibility_pin=compatibility_pin,
        )

        observed = (
            _parse_aware_timestamp(observed_at, "observed_at")
            if observed_at is not None
            else datetime.now(timezone.utc)
        )
        expires = _parse_aware_timestamp(plan["expires_at"], "plan expires_at")
        anchor_expires_value = plan["recall_intent"]["anchor_freshness"].get(
            "expires_at"
        )
        anchor_expires = (
            _parse_aware_timestamp(anchor_expires_value, "anchor expires_at")
            if anchor_expires_value is not None
            else None
        )
        if plan["status"] != "bounded_memory":
            delivery_state = "suppressed"
            reason_code = "policy_silence"
            delivered = False
            admission_state = "admitted"
            anchor_state = "current"
        elif observed >= expires:
            delivery_state = "expired"
            reason_code = "delivery_window_expired"
            delivered = False
            admission_state = "expired"
            anchor_state = (
                "stale"
                if anchor_expires is not None and observed >= anchor_expires
                else "current"
            )
        elif anchor_expires is not None and observed >= anchor_expires:
            delivery_state = "suppressed"
            reason_code = "anchor_not_current"
            delivered = False
            admission_state = "admitted"
            anchor_state = "stale"
        else:
            delivery_state = "delivered"
            reason_code = "delivery_confirmed"
            delivered = True
            admission_state = "admitted"
            anchor_state = "current"

        plan_suffix = plan["plan_digest"].removeprefix("sha256:")[:20]
        attempt_id = f"active-organ-attempt:{plan_suffix}:{attempt_no}"
        packet = memo_bundle["recall_packet"]
        decision = memo_bundle["intervention_decision"]
        model_host_pin_ref = (
            "aoa-sdk:model-prompt-provider-host-pin:"
            + _canonical_digest(
                {
                    "model_prompt_provider_pin": plan["recall_intent"][
                        "model_prompt_provider_pin"
                    ],
                    "host_capability_ref": plan["host_capability_ref"],
                    "host_resource_plan_ref": plan["host_resource_plan_ref"],
                }
            ).removeprefix("sha256:")
        )
        receipt = {
            "schema_version": "active_organ_runtime_delivery_receipt_v1",
            "contract_id": "C20",
            "receipt_id": (
                f"abyss-stack:active-organ-delivery:{plan_suffix}:"
                f"{attempt_no}:{delivery_state}"
            ),
            "attempt_id": attempt_id,
            "attempt_no": attempt_no,
            "recorded_at": _iso_timestamp(observed),
            "expires_at": plan["expires_at"],
            "runtime_owner": "abyss-stack",
            "runtime_surface": "aoa-memo-mcp/codex-owner-orientation-v0",
            "delivery_state": delivery_state,
            "recall_intent_ref": (
                "aoa-sdk:recall-intent:"
                + plan["recall_intent"]["intent_id"]
            ),
            "admitted_run_plan_ref": (
                f"aoa-sdk:owner-orientation-plan:{plan['plan_id']}"
            ),
            "recall_packet_ref": (
                packet["instance_id"]
                if delivery_state != "suppressed"
                else None
            ),
            "intervention_decision": {
                "ref": decision["decision_id"],
                "decision": decision["decision"],
            },
            "trigger_binding": {
                "trigger_id": plan["recall_intent"]["trigger_id"],
                "trigger_policy_version": plan["recall_intent"]["policy_pin"][
                    "policy_version"
                ],
            },
            "anchor_binding": {
                "anchor_id": plan["recall_intent"]["anchor_id"],
                "anchor_ref": plan["recall_intent"]["anchor_ref"]["source_ref"],
                "freshness": anchor_state,
                "checked_at": _iso_timestamp(observed),
            },
            "policy_binding": {
                "policy_id": plan["recall_intent"]["policy_pin"]["policy_id"],
                "policy_version": plan["recall_intent"]["policy_pin"][
                    "policy_version"
                ],
                "consumer_id": plan["consumer_id"],
                "tenant_id": plan["recall_intent"]["tenant_id"],
                "data_class": plan["recall_intent"]["data_class"],
                "risk_class": plan["recall_intent"]["risk_class"],
                "model_prompt_provider_hardware_pin_ref": model_host_pin_ref,
            },
            "admission": {
                "state": admission_state,
                "ref": (
                    f"aoa-sdk:owner-orientation-admission:{plan_suffix}"
                ),
                "checked_at": _iso_timestamp(observed),
            },
            "delivery_target": {
                "consumer_id": plan["consumer_id"],
                "adapter_id": "abyss-stack:codex-owner-orientation:v0",
                "transport": "internal_queue",
                "target_ref": target_ref,
            },
            "result": {
                "delivered": delivered,
                "reason_code": reason_code,
                "observed_at": _iso_timestamp(observed),
                "failure_ref": None,
            },
            "retry": {
                "implicit_retry_allowed": False,
                "new_attempt_requires_admission_recheck": True,
            },
            "content_minimization": {
                "persistence_mode": "refs_only",
                "packet_content_persisted": False,
                "prompt_content_persisted": False,
                "memory_content_persisted": False,
                "payload_digest_persisted": False,
                "error_detail_persisted": False,
            },
            "authority": {
                "delivery_authority": "already_admitted_packet_only",
                "effect_authority": "none",
                "memory_semantic_authority": False,
                "policy_widening_authority": False,
            },
            "receipt_retention": {
                "retention_class": "T5_content_minimized_receipt",
                "minimization_policy_ref": (
                    "aoa-memo:codex-owner-orientation:"
                    "content-minimized-receipt-v0"
                ),
                "erase_scope_ref": f"aoa-memo:erase-scope:{attempt_id}",
            },
            "evidence_refs": [
                f"aoa-sdk:owner-orientation-plan:{plan['plan_id']}",
                packet["instance_id"],
                decision["decision_id"],
                plan["host_capability_ref"]["source_ref"],
                plan["host_resource_plan_ref"]["source_ref"],
            ],
        }
        errors = sorted(
            Draft202012Validator(
                delivery_schema,
                format_checker=FORMAT_CHECKER,
            ).iter_errors(receipt),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = (
                "/".join(str(item) for item in error.absolute_path)
                or "<root>"
            )
            raise ValueError(f"C20 delivery receipt {location}: {error.message}")

        memory_payload = []
        if delivered:
            memory_payload = [
                {
                    "object_id": item["card"]["id"],
                    "title": item["card"]["title"],
                    "summary": item["card"]["summary"],
                    "capsule": item["capsule"],
                    "expanded": item["expanded"],
                    "source_route": item["source_route"],
                    "current_recall_status": item["card"][
                        "current_recall_status"
                    ],
                    "contradiction_refs": item["card"]["contradiction_refs"],
                    "superseded_by": item["card"]["superseded_by"],
                }
                for item in plan["items"]
            ]
        return {
            "schema_version": "codex_owner_orientation_delivery_v0",
            "delivery_state": delivery_state,
            "memory_payload": memory_payload,
            "recall_packet_ref": packet["instance_id"],
            "intervention_decision_ref": decision["decision_id"],
            "runtime_receipt": receipt,
            "reranking_performed": False,
            "reselection_performed": False,
            "persistence_performed": False,
            "effect_authority": "none",
            "action_use": "forbidden",
        }

    def deliver_canary_orientation(
        self,
        *,
        release_plan: dict[str, Any],
        shadow_plan: dict[str, Any],
        shadow_bundle: dict[str, Any],
        canary_bundle: dict[str, Any],
        host_admission: dict[str, Any],
        release_plan_schema_path: str | Path,
        shadow_plan_schema_path: str | Path,
        shadow_bundle_schema_path: str | Path,
        canary_bundle_schema_path: str | Path,
        window_receipts: list[dict[str, Any]] | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Return at most one already-selected canary observation, refs-only."""

        stack_root = _stack_source_root()
        pin_path = stack_root / OWNER_ORIENTATION_CANARY_PIN
        receipt_schema_path = stack_root / ACTIVE_ORGAN_CANARY_RECEIPT_SCHEMA
        compatibility_pin = _read_json(pin_path)
        receipt_schema = _read_json(receipt_schema_path)
        schema_paths = {
            "sdk_release_plan_schema": Path(
                release_plan_schema_path
            ).expanduser().resolve(),
            "sdk_shadow_plan_schema": Path(
                shadow_plan_schema_path
            ).expanduser().resolve(),
            "memo_shadow_bundle_schema": Path(
                shadow_bundle_schema_path
            ).expanduser().resolve(),
            "memo_canary_bundle_schema": Path(
                canary_bundle_schema_path
            ).expanduser().resolve(),
        }
        schemas = {
            key: _read_json(path)
            for key, path in schema_paths.items()
        }
        if not isinstance(compatibility_pin, dict):
            raise ValueError("canary runtime compatibility pin is unavailable")
        if not isinstance(receipt_schema, dict):
            raise ValueError("canary C20 runtime receipt schema is unavailable")
        if any(not isinstance(schema, dict) for schema in schemas.values()):
            raise ValueError("canary input schemas must be explicit")
        if (
            _artifact_digest(receipt_schema_path)
            != compatibility_pin["runtime_receipt_schema"]["sha256"]
        ):
            raise ValueError("canary C20 receipt schema compatibility pin drifted")
        for key, path in schema_paths.items():
            if _artifact_digest(path) != compatibility_pin[key]["sha256"]:
                raise ValueError(f"canary runtime {key} compatibility pin drifted")

        _validate_canary_orientation_inputs(
            release_plan=release_plan,
            shadow_plan=shadow_plan,
            shadow_bundle=shadow_bundle,
            canary_bundle=canary_bundle,
            host_admission=host_admission,
            release_plan_schema=schemas["sdk_release_plan_schema"],
            shadow_plan_schema=schemas["sdk_shadow_plan_schema"],
            shadow_bundle_schema=schemas["memo_shadow_bundle_schema"],
            canary_bundle_schema=schemas["memo_canary_bundle_schema"],
            compatibility_pin=compatibility_pin,
        )

        observed = (
            _parse_aware_timestamp(observed_at, "observed_at")
            if observed_at is not None
            else datetime.now(timezone.utc)
        )
        window_start = _parse_aware_timestamp(
            release_plan["window_start"],
            "canary window_start",
        )
        window_end = _parse_aware_timestamp(
            release_plan["window_end"],
            "canary window_end",
        )
        release_expires = _parse_aware_timestamp(
            release_plan["expires_at"],
            "canary release expires_at",
        )
        host_expires = _parse_aware_timestamp(
            host_admission["expires_at"],
            "host canary admission expires_at",
        )

        prior_receipts = window_receipts or []
        receipt_ids: set[str] = set()
        delivered_count = 0
        for prior in prior_receipts:
            errors = sorted(
                Draft202012Validator(
                    receipt_schema,
                    format_checker=FORMAT_CHECKER,
                ).iter_errors(prior),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                error = errors[0]
                location = (
                    "/".join(str(item) for item in error.absolute_path)
                    or "<root>"
                )
                raise ValueError(
                    f"prior canary C20 receipt {location}: {error.message}"
                )
            if prior["receipt_digest"] != _canonical_digest(
                prior,
                exclude={"receipt_digest"},
            ):
                raise ValueError("prior canary C20 receipt digest is invalid")
            if (
                prior["consumer_id"] != release_plan["consumer_id"]
                or prior["window_id"] != release_plan["window_id"]
                or prior["window_start"] != release_plan["window_start"]
                or prior["window_end"] != release_plan["window_end"]
            ):
                raise ValueError("prior canary receipt escaped the exact policy window")
            prior_recorded = _parse_aware_timestamp(
                prior["recorded_at"],
                "prior canary receipt recorded_at",
            )
            if not window_start <= prior_recorded < window_end:
                raise ValueError("prior canary receipt is outside its policy window")
            if prior["receipt_id"] in receipt_ids:
                raise ValueError("duplicate prior canary receipt")
            receipt_ids.add(prior["receipt_id"])
            if prior["delivery_state"] == "delivered":
                delivered_count += 1

        status = release_plan["status"]
        release_silence_reason = release_plan["silence_reason"]
        if status == "off":
            delivery_state = "off"
            reason_code = "kill_switch"
        elif status == "holdout":
            delivery_state = "held_out"
            reason_code = "randomized_holdout"
        elif status == "silence":
            delivery_state = "silenced"
            reason_code = "release_plan_silence"
        elif observed >= min(release_expires, host_expires, window_end):
            delivery_state = "expired"
            reason_code = "release_expired"
            release_silence_reason = "window-inactive"
        elif host_admission["host_disposition"] != "start":
            delivery_state = "host_denied"
            reason_code = "host_gate"
            release_silence_reason = (
                f"host-{host_admission['host_disposition']}"
            )
        elif delivered_count >= release_plan["max_reminders"]:
            delivery_state = "rate_limited"
            reason_code = "window_exhausted"
            release_silence_reason = "window-exhausted"
        elif release_plan["prior_reminder_count"] != delivered_count:
            delivery_state = "silenced"
            reason_code = "window_receipt_count_drift"
            release_silence_reason = "window-receipt-count-drift"
        else:
            delivery_state = "delivered"
            reason_code = "canary_observation_delivered"

        delivered = delivery_state == "delivered"
        observation = canary_bundle["observation"] if delivered else None
        observation_ref = None
        observation_digest = None
        if observation is not None:
            observation_digest = observation["content_digest"]
            observation_ref = (
                "aoa-memo:canary-observation:"
                f"{observation['object_id']}:"
                f"{observation_digest.removeprefix('sha256:')[:20]}"
            )

        plan_suffix = release_plan["plan_digest"].removeprefix("sha256:")[:20]
        release_plan_ref = (
            f"aoa-sdk:canary-release:{release_plan['plan_id']}"
        )
        shadow_plan_ref = (
            f"aoa-sdk:shadow-orientation-plan:{shadow_plan['plan_id']}"
        )
        shadow_bundle_ref = (
            "aoa-memo:shadow-bundle:"
            f"{shadow_bundle['bundle_digest'].removeprefix('sha256:')[:20]}"
        )
        bundle_ref = (
            "aoa-memo:canary-bundle:"
            f"{canary_bundle['bundle_digest'].removeprefix('sha256:')[:20]}"
        )
        host_ref = (
            "abyss-machine:canary-admission:"
            f"{host_admission['admission_digest'].removeprefix('sha256:')[:20]}"
        )
        receipt = {
            "schema_version": "active_organ_canary_runtime_receipt_v0",
            "contract_id": "C20",
            "receipt_id": (
                f"abyss-stack:active-organ-canary:{plan_suffix}:"
                f"{delivery_state}"
            ),
            "recorded_at": _iso_timestamp(observed),
            "expires_at": _iso_timestamp(
                min(release_expires, host_expires, window_end)
            ),
            "runtime_owner": "abyss-stack",
            "runtime_surface": (
                "aoa-memo-mcp/codex-owner-orientation-canary-v0"
            ),
            "release_plan_ref": release_plan_ref,
            "release_plan_digest": release_plan["plan_digest"],
            "shadow_plan_ref": shadow_plan_ref,
            "shadow_plan_digest": shadow_plan["plan_digest"],
            "bundle_ref": bundle_ref,
            "bundle_digest": canary_bundle["bundle_digest"],
            "host_admission_ref": host_ref,
            "host_admission_digest": host_admission["admission_digest"],
            "consumer_id": release_plan["consumer_id"],
            "tenant_id": compatibility_pin["tenant_id"],
            "assigned_arm": release_plan["assigned_arm"],
            "assignment_ref": release_plan["assignment_ref"]["source_ref"],
            "window_id": release_plan["window_id"],
            "window_start": release_plan["window_start"],
            "window_end": release_plan["window_end"],
            "prior_window_delivery_count": delivered_count,
            "max_reminders": release_plan["max_reminders"],
            "delivery_state": delivery_state,
            "reason_code": reason_code,
            "release_silence_reason": (
                None if delivered else release_silence_reason
            ),
            "observation_ref": observation_ref,
            "observation_digest": observation_digest,
            "consumer_visible": delivered,
            "consumer_output_count": 1 if delivered else 0,
            "source_visible": True,
            "currentness_visible": True,
            "directive_authority": False,
            "content_persisted": False,
            "candidate_persisted": False,
            "reranking_performed": False,
            "reselection_performed": False,
            "memory_semantic_authority": False,
            "policy_widening_authority": False,
            "effect_authority": "none",
            "action_use": "forbidden",
            "rollback_target": compatibility_pin["rollback_target"],
            "evidence_refs": list(
                dict.fromkeys(
                    [
                        release_plan_ref,
                        shadow_plan_ref,
                        shadow_bundle_ref,
                        bundle_ref,
                        host_ref,
                        release_plan["assignment_ref"]["source_ref"],
                        release_plan[
                            "always_shadow_counterfactual_ref"
                        ]["source_ref"],
                        release_plan["currentness_probe_ref"]["source_ref"],
                        release_plan["outcome_refs"][0]["source_ref"],
                        release_plan["profile_ref"]["source_ref"],
                        release_plan["policy_ref"]["source_ref"],
                    ]
                )
            ),
            "receipt_digest": "sha256:" + ("0" * 64),
        }
        receipt["receipt_digest"] = _canonical_digest(
            receipt,
            exclude={"receipt_digest"},
        )
        errors = sorted(
            Draft202012Validator(
                receipt_schema,
                format_checker=FORMAT_CHECKER,
            ).iter_errors(receipt),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = (
                "/".join(str(item) for item in error.absolute_path)
                or "<root>"
            )
            raise ValueError(f"canary C20 receipt {location}: {error.message}")

        return {
            "schema_version": "codex_owner_orientation_canary_delivery_v0",
            "delivery_state": delivery_state,
            "consumer_output": [observation] if delivered else [],
            "runtime_receipt": receipt,
            "consumer_visible": delivered,
            "source_visible": True,
            "currentness_visible": True,
            "directive_authority": False,
            "persistence_performed": False,
            "candidate_persisted": False,
            "reranking_performed": False,
            "reselection_performed": False,
            "semantic_transition_performed": False,
            "policy_promotion_performed": False,
            "effect_authority": "none",
            "action_use": "forbidden",
            "rollback_target": compatibility_pin["rollback_target"],
        }

    def observe_shadow_orientation(
        self,
        *,
        plan: dict[str, Any],
        memo_bundle: dict[str, Any],
        host_admission: dict[str, Any],
        plan_schema_path: str | Path,
        memo_bundle_schema_path: str | Path,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        """Record packet construction while returning nothing to the consumer."""

        stack_root = _stack_source_root()
        pin_path = stack_root / OWNER_ORIENTATION_SHADOW_PIN
        receipt_schema_path = stack_root / ACTIVE_ORGAN_SHADOW_RECEIPT_SCHEMA
        compatibility_pin = _read_json(pin_path)
        receipt_schema = _read_json(receipt_schema_path)
        resolved_plan_schema = Path(plan_schema_path).expanduser().resolve()
        resolved_bundle_schema = Path(memo_bundle_schema_path).expanduser().resolve()
        plan_schema = _read_json(resolved_plan_schema)
        bundle_schema = _read_json(resolved_bundle_schema)
        if not isinstance(compatibility_pin, dict):
            raise ValueError("shadow runtime compatibility pin is unavailable")
        if not isinstance(receipt_schema, dict):
            raise ValueError("shadow C20 runtime receipt schema is unavailable")
        if not isinstance(plan_schema, dict) or not isinstance(bundle_schema, dict):
            raise ValueError("shadow plan and bundle schemas must be explicit")
        if (
            _artifact_digest(receipt_schema_path)
            != compatibility_pin["runtime_receipt_schema"]["sha256"]
            or _artifact_digest(resolved_plan_schema)
            != compatibility_pin["sdk_plan_schema"]["sha256"]
            or _artifact_digest(resolved_bundle_schema)
            != compatibility_pin["memo_bundle_schema"]["sha256"]
        ):
            raise ValueError("shadow runtime schema compatibility pin drifted")
        _validate_shadow_orientation_inputs(
            plan=plan,
            memo_bundle=memo_bundle,
            host_admission=host_admission,
            plan_schema=plan_schema,
            bundle_schema=bundle_schema,
            compatibility_pin=compatibility_pin,
        )

        observed = (
            _parse_aware_timestamp(observed_at, "observed_at")
            if observed_at is not None
            else datetime.now(timezone.utc)
        )
        plan_expires = _parse_aware_timestamp(
            plan["expires_at"],
            "plan expires_at",
        )
        host_expires = _parse_aware_timestamp(
            host_admission["expires_at"],
            "host admission expires_at",
        )
        if observed >= min(plan_expires, host_expires):
            observation_state = "expired"
        elif host_admission["host_disposition"] in {"defer", "deny"}:
            observation_state = "host_denied"
        elif plan["status"] == "bounded_memory":
            observation_state = "constructed"
        else:
            observation_state = "silence"

        suffix = plan["plan_digest"].removeprefix("sha256:")[:20]
        plan_ref = f"aoa-sdk:shadow-orientation-plan:{plan['plan_id']}"
        bundle_ref = f"aoa-memo:shadow-bundle:{memo_bundle['bundle_digest'][7:27]}"
        host_ref = (
            "abyss-machine:shadow-admission:"
            + host_admission["admission_digest"][7:27]
        )
        packet = memo_bundle["recall_packet"]
        decision = memo_bundle["intervention_decision"]
        ingress = memo_bundle["pressure_ingress"]
        evidence_refs = [
            plan_ref,
            bundle_ref,
            packet["instance_id"],
            decision["decision_id"],
            ingress["evidence_envelope"]["instance_id"],
            ingress["candidate_packet"]["instance_id"],
            host_ref,
            plan["currentness_probe_ref"]["source_ref"],
            plan["outcome_refs"][0]["source_ref"],
        ]
        receipt = {
            "schema_version": "active_organ_shadow_runtime_receipt_v0",
            "contract_id": "C20",
            "receipt_id": (
                f"abyss-stack:active-organ-shadow:{suffix}:{observation_state}"
            ),
            "recorded_at": _iso_timestamp(observed),
            "expires_at": plan["expires_at"],
            "runtime_owner": "abyss-stack",
            "runtime_surface": (
                "aoa-memo-mcp/codex-owner-orientation-shadow-v0"
            ),
            "plan_ref": plan_ref,
            "plan_digest": plan["plan_digest"],
            "bundle_ref": bundle_ref,
            "bundle_digest": memo_bundle["bundle_digest"],
            "host_admission_ref": host_ref,
            "host_admission_digest": host_admission["admission_digest"],
            "observation_state": observation_state,
            "shadow_item_refs": (
                [item["card"]["id"] for item in plan["items"]]
                if observation_state == "constructed"
                else []
            ),
            "consumer_visible": False,
            "delivery_attempted": False,
            "memory_payload_returned": False,
            "content_persisted": False,
            "candidate_persisted": False,
            "reranking_performed": False,
            "reselection_performed": False,
            "memory_semantic_authority": False,
            "policy_widening_authority": False,
            "effect_authority": "none",
            "action_use": "forbidden",
            "evidence_refs": evidence_refs,
        }
        receipt["receipt_digest"] = _canonical_digest(
            receipt,
            exclude={"receipt_digest"},
        )
        errors = sorted(
            Draft202012Validator(
                receipt_schema,
                format_checker=FORMAT_CHECKER,
            ).iter_errors(receipt),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            error = errors[0]
            location = (
                "/".join(str(item) for item in error.absolute_path)
                or "<root>"
            )
            raise ValueError(f"shadow C20 receipt {location}: {error.message}")

        return {
            "schema_version": "codex_owner_orientation_shadow_observation_v0",
            "observation_state": observation_state,
            "consumer_output": [],
            "memory_payload": [],
            "shadow_item_refs": receipt["shadow_item_refs"],
            "runtime_receipt": receipt,
            "consumer_visible": False,
            "delivery_attempted": False,
            "persistence_performed": False,
            "candidate_persisted": False,
            "reranking_performed": False,
            "reselection_performed": False,
            "semantic_transition_performed": False,
            "policy_promotion_performed": False,
            "effect_authority": "none",
            "action_use": "forbidden",
        }

    def build_local_port_status(self, repo: str) -> dict[str, Any]:
        route = self.repo_route(repo)
        port = route.memo_port
        required = []
        if port is not None:
            required = [
                {"path": name, "exists": (port / name).is_dir()}
                for name in REQUIRED_PORT_DIRS
            ]
        return {
            "schema": "aoa_local_memo_port_status_v1",
            "repo": route.name,
            "memory_role": self._workspace_memory_summary(route.name).get("memory_role", ""),
            "memory_route_status": self._workspace_memory_summary(route.name).get("memory_route_status", ""),
            "recommended_port_level": self._workspace_memory_summary(route.name).get("recommended_port_level", ""),
            "source_root": str(route.source_root) if route.source_root else None,
            "memo_port": str(port) if port else None,
            "present": bool(port and port.exists()),
            "port_contract": str(port / LOCAL_PORT_CONTRACT) if port else None,
            "port_contract_exists": bool(port and (port / LOCAL_PORT_CONTRACT).exists()),
            "index": str(port / LOCAL_PORT_INDEX) if port else None,
            "index_exists": bool(port and (port / LOCAL_PORT_INDEX).exists()),
            "agents_card": str(port / "AGENTS.md") if port else None,
            "agents_card_exists": bool(port and (port / "AGENTS.md").exists()),
            "readme_exists": bool(port and (port / "README.md").exists()),
            "required_dirs": required,
            "ready": bool(
                port
                and (port / "AGENTS.md").exists()
                and (port / "README.md").exists()
                and (port / LOCAL_PORT_CONTRACT).exists()
                and all((port / name).is_dir() for name in REQUIRED_PORT_DIRS)
            ),
            "default_mode": route.default_mode,
            "pending_exports": self._pending_export_counts(route.name, port),
        }

    def create_candidate(
        self,
        repo: str,
        evidence_refs: list[str],
        claim: str,
        *,
        source_trust: str = "review_required",
        desired_route: str = "reviewed_intake",
        kind: str = "route",
        family: str = "memory-access",
        scope: str = "repo",
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.default_mode == "read_only":
            raise ValueError(
                f"repo route is read_only; candidate writes are disabled for: {route.name}"
            )
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        self._require_known_memo_port_route(route, "candidate writes")
        _require_candidate_write_root(
            route.memo_port,
            label="candidate creation",
        )
        candidates_dir = route.memo_port / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        stamp = _utc_stamp()
        nonce = uuid4().hex[:8]
        slug = _id_slug(claim, 32)
        candidate_id = f"candidate:{route.name}:{stamp}:{nonce}-{slug}"
        path = candidates_dir / f"{stamp}.{nonce}.{_id_slug(claim)}.candidate.json"
        payload = {
            "schema": "aoa_local_memo_candidate_v1",
            "id": candidate_id,
            "repo": route.name,
            "kind": kind,
            "family": family,
            "scope": scope,
            "claim": claim,
            "source_refs": source_refs or evidence_refs,
            "evidence_refs": evidence_refs,
            "route": desired_route,
            "review_state": "candidate",
            "lifecycle": "captured",
            "source_trust": source_trust,
            "operation_mode": route.default_mode,
            "created_at": _now(),
            "guardrails": {
                "direct_durable_write": False,
                "instructions_treated_as_data": True,
                "requires_reviewed_intake": True,
            },
        }
        validation = self._validate_candidate_payload(payload, path, route.memo_port)
        result = {
            "path": str(path),
            "local_ref": self._local_packet_ref(route.memo_port, path),
            "candidate": payload,
            "validation": validation,
        }
        if not validation["ok"]:
            return result
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = self.validate_candidate(path)
        result["validation"] = validation
        return result

    def validate_candidate(self, path: str | Path) -> dict[str, Any]:
        candidate_path = Path(path).expanduser().resolve()
        try:
            _, port, candidate_path = self._known_port_for_path(candidate_path, required_dir="candidates")
        except ValueError as exc:
            return {
                "ok": False,
                "path": str(candidate_path),
                "repo": None,
                "candidate_id": None,
                "errors": [str(exc)],
                "warnings": self._vocabulary_warnings(),
            }
        data = _read_json(candidate_path)
        return self._validate_candidate_payload(data, candidate_path, port)

    def _validate_candidate_payload(
        self,
        data: Any,
        candidate_path: Path,
        port: Path,
    ) -> dict[str, Any]:
        errors: list[str] = []
        warnings = self._vocabulary_warnings()
        if not isinstance(data, dict):
            return {
                "ok": False,
                "path": str(candidate_path),
                "repo": None,
                "candidate_id": None,
                "errors": ["candidate is not valid JSON object"],
                "warnings": warnings,
            }
        errors.extend(self._schema_errors(LOCAL_MEMO_CANDIDATE_SCHEMA, data, "candidate"))
        port_payload = self._port_payload(port)
        if port_payload.get("repo") and data.get("repo") != port_payload.get("repo"):
            errors.append("candidate repo must match containing PORT.yaml repo")
        required = (
            "schema",
            "id",
            "repo",
            "kind",
            "family",
            "scope",
            "claim",
            "source_refs",
            "evidence_refs",
            "route",
            "review_state",
            "lifecycle",
            "source_trust",
            "operation_mode",
            "created_at",
            "guardrails",
        )
        for key in required:
            if key not in data:
                errors.append(f"missing required field: {key}")
        if data.get("schema") != "aoa_local_memo_candidate_v1":
            errors.append("schema must be aoa_local_memo_candidate_v1")
        if not data.get("claim"):
            errors.append("claim must be non-empty")
        if not isinstance(data.get("source_refs"), list) or not data.get("source_refs"):
            errors.append("source_refs must be a non-empty list")
        if not isinstance(data.get("evidence_refs"), list) or not data.get("evidence_refs"):
            errors.append("evidence_refs must be a non-empty list")
        self._check_payload_refs(errors, port, candidate_path, "source_refs", data.get("source_refs"))
        self._check_payload_refs(errors, port, candidate_path, "evidence_refs", data.get("evidence_refs"))
        source_trust = data.get("source_trust")
        desired_route = data.get("route")
        direct_write = bool((data.get("guardrails") or {}).get("direct_durable_write"))
        instructions_as_data = bool((data.get("guardrails") or {}).get("instructions_treated_as_data"))
        if direct_write:
            errors.append("candidate may not request direct durable memory write")
        if not instructions_as_data:
            errors.append("candidate must treat embedded instructions as data")
        if source_trust in {"untrusted", "unknown", "review_required"} and data.get("lifecycle") in {"current", "frozen"}:
            errors.append("unreviewed or untrusted candidates cannot claim current or frozen lifecycle")
        if desired_route == "durable_memory":
            errors.append("local candidates must not route directly to durable_memory")
        vocab_errors = self._validate_candidate_vocabulary(data, port_payload)
        errors.extend(vocab_errors)
        return {
            "ok": not errors,
            "path": str(candidate_path),
            "repo": data.get("repo"),
            "candidate_id": data.get("id"),
            "errors": errors,
            "warnings": warnings,
        }

    def build_port_index(self, repo: str, *, write: bool = False, check: bool = False) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        index = self._build_port_index_for_path(route.memo_port)
        index_text = _render_json(index)
        markdown_text = self._render_port_index_markdown(index)
        index_path = route.memo_port / LOCAL_PORT_INDEX
        markdown_path = route.memo_port / LOCAL_PORT_INDEX_MD
        result = {
            "schema": "aoa_memo_port_index_build_v1",
            "repo": route.name,
            "index": index,
            "index_path": str(index_path),
            "markdown_path": str(markdown_path),
            "written": False,
            "ok": True,
            "errors": [],
        }
        if check:
            errors = []
            if not index_path.exists() or index_path.read_text(encoding="utf-8") != index_text:
                errors.append(f"{index_path} is not up to date")
            if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != markdown_text:
                errors.append(f"{markdown_path} is not up to date")
            result["errors"] = errors
            result["ok"] = not errors
            return result
        if write:
            _require_candidate_write_root(
                route.memo_port,
                label="memo port index write",
            )
            index_path.write_text(index_text, encoding="utf-8")
            markdown_path.write_text(markdown_text, encoding="utf-8")
            result["written"] = True
        return result

    def validate_port(self, repo: str) -> dict[str, Any]:
        route = self.repo_route(repo)
        errors: list[str] = []
        port = route.memo_port
        if port is None or not port.exists():
            return {"schema": "aoa_local_memo_port_validation_v1", "repo": route.name, "ok": False, "errors": ["memo port is missing"]}
        port_payload = _read_yaml(port / LOCAL_PORT_CONTRACT)
        if not isinstance(port_payload, dict):
            errors.append("PORT.yaml is missing or invalid")
            port_payload = {}
        else:
            errors.extend(self._schema_errors(LOCAL_MEMO_PORT_SCHEMA, port_payload, "PORT.yaml"))
        for directory in REQUIRED_PORT_DIRS:
            if not (port / directory).is_dir():
                errors.append(f"missing directory: {directory}")
        if port_payload.get("repo") != route.name:
            errors.append("PORT.yaml repo must match route repo")
        if port_payload.get("stronger_memory_owner") != "aoa-memo":
            errors.append("PORT.yaml stronger_memory_owner must be aoa-memo")
        allowed_routes = set(port_payload.get("allowed_routes") or [])
        if "reviewed_intake" not in allowed_routes:
            errors.append("PORT.yaml must allow reviewed_intake")
        for candidate in sorted((port / "candidates").glob("*.json")):
            result = self.validate_candidate(candidate)
            if not result["ok"]:
                errors.extend(f"{candidate}: {error}" for error in result["errors"])
        for export in sorted((port / "exports").glob("*.json")):
            payload = _read_json(export)
            if not isinstance(payload, dict):
                errors.append(f"{export}: export is not a JSON object")
            else:
                errors.extend(f"{export}: {error}" for error in self._schema_errors(LOCAL_MEMO_EXPORT_SCHEMA, payload, "export"))
        for receipt in sorted((port / "receipts").glob("*.json")):
            payload = _read_json(receipt)
            if not isinstance(payload, dict):
                errors.append(f"{receipt}: receipt is not a JSON object")
            else:
                errors.extend(f"{receipt}: {error}" for error in self._schema_errors(LOCAL_MEMO_RECEIPT_SCHEMA, payload, "receipt"))
        index_payload = _read_json(port / LOCAL_PORT_INDEX)
        if isinstance(index_payload, dict):
            errors.extend(self._schema_errors(LOCAL_MEMO_PORT_INDEX_SCHEMA, index_payload, "port index"))
        check = self.build_port_index(repo, check=True)
        if not check["ok"]:
            errors.extend(check["errors"])
        return {
            "schema": "aoa_local_memo_port_validation_v1",
            "repo": route.name,
            "port": str(port),
            "ok": not errors,
            "errors": errors,
        }

    def prepare_intake_packet(
        self,
        repo: str,
        candidate_refs: list[str],
        receipt_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        if not candidate_refs:
            raise ValueError("candidate_refs must not be empty")
        errors: list[str] = []
        candidates: list[Path] = []
        for ref in candidate_refs:
            try:
                candidate = self._resolve_local_ref(route.memo_port, ref, "candidates")
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            if candidate is None or not candidate.exists():
                errors.append(f"missing candidate ref: {ref}")
            else:
                candidates.append(candidate)
        receipts: list[Path] = []
        for ref in receipt_refs or []:
            try:
                receipt = self._resolve_local_ref(route.memo_port, ref, "receipts")
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            if receipt is None or not receipt.exists():
                errors.append(f"missing receipt ref: {ref}")
            else:
                receipts.append(receipt)
        if errors:
            return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": False, "errors": errors}
        candidate_payloads: list[dict[str, Any]] = []
        source_refs: list[str] = []
        evidence_refs: list[str] = []
        for path in candidates:
            payload = _read_json(path)
            if not isinstance(payload, dict):
                errors.append(f"{self._local_packet_ref(route.memo_port, path)} is not a JSON object")
                continue
            candidate_payloads.append(payload)
            validation = self.validate_candidate(path)
            if not validation["ok"]:
                errors.extend(validation["errors"])
            source_refs.extend(str(ref) for ref in payload.get("source_refs", []) if isinstance(ref, str))
            evidence_refs.extend(str(ref) for ref in payload.get("evidence_refs", []) if isinstance(ref, str))
        if errors:
            return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": False, "errors": errors}

        _require_candidate_write_root(
            route.memo_port,
            label="memo intake export write",
        )
        stamp = _utc_stamp()
        slug = _id_slug(str(candidate_payloads[0].get("claim", "memo-intake")), 48)
        export_path = route.memo_port / "exports" / f"{stamp}.{slug}.aoa-memo-intake.json"
        payload = {
            "schema": "aoa_local_memo_export_v1",
            "id": f"export:{route.name}:{stamp}:{slug}",
            "repo": route.name,
            "target_owner": "aoa-memo",
            "target_route": "reviewed_intake",
            "candidate_refs": [self._local_packet_ref(route.memo_port, path) for path in candidates if path is not None],
            "receipt_refs": [self._local_packet_ref(route.memo_port, path) for path in receipts],
            "source_refs": sorted(set(source_refs)),
            "evidence_refs": sorted(set(evidence_refs)),
            "allowed_result": "candidate_only",
            "created_at": _now(),
            "notes": "Prepared by aoa-memo-mcp. This is not durable memory landing.",
        }
        errors = self._schema_errors(LOCAL_MEMO_EXPORT_SCHEMA, payload, "export")
        if errors:
            return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": False, "errors": errors}
        export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.build_port_index(repo, write=True)
        return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": True, "path": str(export_path), "export": payload, "errors": []}

    def review_intake(self, path: str | Path) -> dict[str, Any]:
        export_path = Path(path).expanduser().resolve()
        try:
            repo_from_path, port, export_path = self._known_port_for_path(export_path, required_dir="exports")
        except ValueError as exc:
            return {"schema": "aoa_local_memo_intake_review_v1", "ok": False, "path": str(export_path), "errors": [str(exc)]}
        payload = _read_json(export_path)
        errors: list[str] = []
        if not isinstance(payload, dict):
            return {"schema": "aoa_local_memo_intake_review_v1", "ok": False, "path": str(export_path), "errors": ["export packet is not a JSON object"]}
        errors.extend(self._schema_errors(LOCAL_MEMO_EXPORT_SCHEMA, payload, "export"))
        repo = str(payload.get("repo") or "")
        try:
            route = self.repo_route(repo)
        except ValueError as exc:
            route = None
            errors.append(str(exc))
        if route is None or route.memo_port is None:
            errors.append("export repo does not resolve to a known memo port")
        elif route.memo_port.resolve() != port.resolve():
            errors.append(f"export repo must match containing memo port: {repo_from_path}")
        if payload.get("schema") != "aoa_local_memo_export_v1":
            errors.append("export schema must be aoa_local_memo_export_v1")
        if payload.get("target_owner") != "aoa-memo" or payload.get("target_route") != "reviewed_intake":
            errors.append("export must target aoa-memo reviewed_intake")
        for ref in payload.get("candidate_refs", []):
            try:
                candidate = self._resolve_local_ref(port, str(ref), "candidates")
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            if candidate is None or not candidate.exists():
                errors.append(f"missing candidate ref: {ref}")
            else:
                result = self.validate_candidate(candidate)
                if not result["ok"]:
                    errors.extend(result["errors"])
        if not payload.get("source_refs"):
            errors.append("export must preserve source_refs")
        if not payload.get("evidence_refs"):
            errors.append("export must preserve evidence_refs")
        self._check_payload_refs(errors, port, export_path, "source_refs", payload.get("source_refs"))
        self._check_payload_refs(errors, port, export_path, "evidence_refs", payload.get("evidence_refs"))

        stamp = _utc_stamp()
        slug = _id_slug(str(payload.get("id") or "intake-review"), 48)
        receipt_path = port / "receipts" / f"{stamp}.{slug}.forwarding-receipt.json"
        receipt = {
            "schema": "aoa_local_memo_receipt_v2",
            "id": f"receipt:{repo}:{stamp}:{slug}",
            "repo": repo,
            "candidate_ref": str((payload.get("candidate_refs") or [""])[0]),
            "export_ref": self._local_packet_ref(port, export_path),
            "result": "forwarded" if not errors else "rejected",
            "route": "reviewed_intake",
            "checks": ["schema", "candidate_refs", "source_refs", "evidence_refs", "guardrails"],
            "errors": errors,
            "created_at": _now(),
            "checked_by": "aoa-memo-mcp",
            "notes": "Forwarding check receipt only. Durable landing remains an aoa-memo source patch.",
        }
        receipt_errors = self._schema_errors(LOCAL_MEMO_RECEIPT_SCHEMA, receipt, "receipt")
        if receipt_errors:
            errors.extend(receipt_errors)
            receipt["errors"] = errors
            return {
                "schema": "aoa_local_memo_intake_review_v1",
                "repo": repo,
                "ok": False,
                "path": str(export_path),
                "receipt_path": None,
                "receipt": receipt,
                "errors": errors,
            }
        _require_candidate_write_root(
            port,
            label="memo forwarding receipt write",
        )
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.build_port_index(repo_from_path, write=True)
        return {
            "schema": "aoa_local_memo_intake_review_v1",
            "repo": repo,
            "ok": not errors,
            "path": str(export_path),
            "receipt_path": str(receipt_path),
            "receipt": receipt,
            "errors": errors,
        }

    def list_pending_exports(self, repo: str) -> dict[str, Any]:
        route = self.repo_route(repo)
        port = route.memo_port
        if port is None or not port.exists():
            return {
                "schema": "aoa_local_memo_pending_exports_v1",
                "repo": route.name,
                "ok": False,
                "exports": [],
                "counts": {"total": 0, "pending": 0, "ready": 0, "landed": 0},
                "errors": ["memo port is missing"],
            }
        exports: list[dict[str, Any]] = []
        for path in sorted((port / "exports").glob("*.json")):
            payload = _read_json(path)
            readiness = self._export_landing_readiness(port, path, payload)
            exports.append(
                {
                    "path": self._local_packet_ref(port, path),
                    "id": payload.get("id") if isinstance(payload, dict) else path.stem,
                    "allowed_result": payload.get("allowed_result") if isinstance(payload, dict) else None,
                    "created_at": payload.get("created_at") if isinstance(payload, dict) else None,
                    "landing_state": readiness["landing_state"],
                    "ready_for_landing": readiness["ready_for_landing"],
                    "errors": readiness["errors"],
                    "candidate_refs": payload.get("candidate_refs", []) if isinstance(payload, dict) else [],
                    "receipt_refs": payload.get("receipt_refs", []) if isinstance(payload, dict) else [],
                }
            )
        counts = {
            "total": len(exports),
            "pending": sum(1 for item in exports if item["landing_state"] != "landed"),
            "ready": sum(1 for item in exports if item["ready_for_landing"]),
            "landed": sum(1 for item in exports if item["landing_state"] == "landed"),
        }
        return {
            "schema": "aoa_local_memo_pending_exports_v1",
            "repo": route.name,
            "ok": True,
            "exports": exports,
            "counts": counts,
            "errors": [],
        }

    def build_landing_plan(
        self,
        repo: str,
        export_ref: str,
        *,
        object_kind: str = "decision",
        slug: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        reviewed_at: str | None = None,
        run_dry_run: bool = False,
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        port = route.memo_port
        if port is None or not port.exists():
            return {
                "schema": "aoa_memo_landing_plan_v1",
                "repo": route.name,
                "ok": False,
                "errors": ["memo port is missing"],
            }
        try:
            export_path = self._resolve_local_ref(port, export_ref, "exports")
        except ValueError as exc:
            return {
                "schema": "aoa_memo_landing_plan_v1",
                "repo": route.name,
                "ok": False,
                "export_ref": export_ref,
                "errors": [str(exc)],
            }
        if export_path is None:
            return {
                "schema": "aoa_memo_landing_plan_v1",
                "repo": route.name,
                "ok": False,
                "export_ref": export_ref,
                "errors": [f"export ref not found: {export_ref}"],
            }
        payload = _read_json(export_path) if export_path else None
        readiness = self._export_landing_readiness(port, export_path, payload)
        payload_id = payload.get("id") if isinstance(payload, dict) else None
        export_slug = _id_slug(str(payload_id or export_path.stem), 64).replace("export-", "")
        slug = slug or export_slug
        reviewed_at = reviewed_at or _now()
        title_args = ["--title", title] if title else []
        summary_args = ["--summary", summary] if summary else []
        command = [
            "python",
            "scripts/memory/land_reviewed_memo_intake.py",
            "--port",
            str(port),
            "--export",
            self._local_packet_ref(port, export_path),
            "--object-kind",
            object_kind,
            "--slug",
            slug,
            "--reviewed-at",
            reviewed_at,
            *title_args,
            *summary_args,
        ]
        result: dict[str, Any] = {
            "schema": "aoa_memo_landing_plan_v1",
            "repo": route.name,
            "ok": readiness["ok"],
            "export_ref": self._local_packet_ref(port, export_path),
            "readiness": readiness,
            "authority_note": "MCP prepares or dry-runs the plan only; durable memory lands through aoa-memo source change, validators, and review.",
            "dry_run_command": command,
            "write_command": [*command, "--write"],
            "errors": readiness["errors"],
        }
        if run_dry_run:
            script = self.aoa_memo_root / "scripts/memory/land_reviewed_memo_intake.py"
            if not script.exists():
                result["ok"] = False
                result["errors"] = [*result["errors"], f"landing script is missing: {script}"]
            else:
                completed = subprocess.run(
                    command,
                    cwd=self.aoa_memo_root,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                result["dry_run"] = {
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                    "ok": completed.returncode == 0,
                }
                result["ok"] = result["ok"] and completed.returncode == 0
                if completed.returncode != 0:
                    result["errors"] = [*result["errors"], completed.stderr.strip() or "dry-run failed"]
        return result

    def search(self, query: str, scope: str = "all", mode: str = "brief", limit: int = 20) -> dict[str, Any]:
        terms, filters = self._parse_search_query(query)
        needle = " ".join(terms).lower().strip()
        roots = self._search_roots(scope)
        hits = self._search_memory_objects(terms, filters, scope, limit)
        if not needle:
            return self._search_result(query, scope, mode, hits)
        if len(hits) >= limit:
            return self._search_result(query, scope, mode, hits[:limit])
        for root in roots:
            if not root.exists():
                continue
            for path in self._iter_search_files(root):
                text = path.read_text(encoding="utf-8", errors="ignore")
                idx = text.lower().find(needle)
                if idx == -1:
                    continue
                start = max(0, idx - 120)
                end = min(len(text), idx + len(needle) + 120)
                hits.append(
                    {
                        "path": str(path),
                        "root": str(root),
                        "snippet": text[start:end].replace("\n", " "),
                    }
                )
                if len(hits) >= limit:
                    return self._search_result(query, scope, mode, hits)
        return self._search_result(query, scope, mode, hits)

    def _search_result(self, query: str, scope: str, mode: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema": "aoa_memo_search_v1",
            "query": query,
            "scope": scope,
            "mode": mode,
            "hits": hits,
            "low_confidence": not hits,
            "authority_note": "Search is retrieval over reviewed read models and local files; source truth remains in the owning repo.",
        }

    def _parse_search_query(self, query: str) -> tuple[list[str], dict[str, str]]:
        filter_aliases = {
            "repo": "repo",
            "kind": "kind",
            "family": "family",
            "scope": "scope",
            "lifecycle": "lifecycle",
            "recall": "recall_status",
            "recall_status": "recall_status",
            "source": "source_ref",
            "source_ref": "source_ref",
            "source_kind": "source_kind",
            "temperature": "temperature",
            "review": "review_state",
            "review_state": "review_state",
        }
        terms: list[str] = []
        filters: dict[str, str] = {}
        for token in query.split():
            key, separator, value = token.partition(":")
            normalized_key = filter_aliases.get(key.lower())
            if separator and normalized_key and value:
                filters[normalized_key] = value.lower()
            else:
                terms.append(token.lower())
        return terms, filters

    def _search_memory_objects(
        self,
        terms: list[str],
        filters: dict[str, str],
        scope: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if scope not in {"all", "central", "aoa-memo", "corpus", "reviewed", "memory-objects"}:
            return []
        catalog_path = self.aoa_memo_root / MEMORY_OBJECT_CATALOG
        catalog = _read_json(catalog_path)
        if not isinstance(catalog, dict):
            return []
        reviewed_only = scope in {"corpus", "reviewed"}
        hits: list[dict[str, Any]] = []
        for item in catalog.get("memory_objects", []):
            if not isinstance(item, dict):
                continue
            if reviewed_only and item.get("source_kind") != "reviewed_corpus":
                continue
            source_object = self._catalog_source_object(item)
            if not self._memory_object_filters_match(item, source_object, filters):
                continue
            haystack = json.dumps({"catalog": item, "object": source_object}, ensure_ascii=False).lower()
            if terms and not all(term in haystack for term in terms):
                continue
            hits.append(
                {
                    "type": "memory_object",
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "title": item.get("title"),
                    "summary": item.get("summary"),
                    "source_kind": item.get("source_kind"),
                    "current_recall_status": item.get("current_recall_status"),
                    "temperature": item.get("temperature"),
                    "review_state": item.get("review_state"),
                    "source_path": item.get("source_path"),
                    "snippet": str(item.get("summary") or item.get("title") or item.get("id") or ""),
                }
            )
            if len(hits) >= limit:
                break
        return sorted(hits, key=lambda hit: hit.get("source_kind") != "reviewed_corpus")

    def _catalog_source_object(self, item: dict[str, Any]) -> dict[str, Any]:
        source_path = item.get("source_path")
        if not isinstance(source_path, str):
            return {}
        payload = _read_json(self.aoa_memo_root / source_path)
        return payload if isinstance(payload, dict) else {}

    def _memory_object_filters_match(
        self,
        item: dict[str, Any],
        source_object: dict[str, Any],
        filters: dict[str, str],
    ) -> bool:
        if not filters:
            return True
        filter_values = {
            "repo": json.dumps(source_object.get("scope", []), ensure_ascii=False).lower()
            + " "
            + json.dumps(source_object.get("owner_refs", []), ensure_ascii=False).lower()
            + " "
            + json.dumps(item, ensure_ascii=False).lower(),
            "kind": str(item.get("kind") or source_object.get("kind") or "").lower(),
            "family": json.dumps(source_object.get("tags", []), ensure_ascii=False).lower()
            + " "
            + json.dumps(item, ensure_ascii=False).lower(),
            "scope": json.dumps(item.get("scope_classes", []), ensure_ascii=False).lower()
            + " "
            + json.dumps(source_object.get("scope", []), ensure_ascii=False).lower(),
            "lifecycle": json.dumps(source_object.get("lifecycle", {}), ensure_ascii=False).lower(),
            "recall_status": str(
                item.get("current_recall_status")
                or ((source_object.get("lifecycle") or {}).get("current_recall") or {}).get("status")
                or ""
            ).lower(),
            "source_ref": json.dumps((source_object.get("provenance") or {}).get("source_refs", []), ensure_ascii=False).lower()
            + " "
            + str(item.get("source_path") or "").lower(),
            "source_kind": str(item.get("source_kind") or "").lower(),
            "temperature": str(item.get("temperature") or ((source_object.get("trust") or {}).get("temperature")) or "").lower(),
            "review_state": str(item.get("review_state") or ((source_object.get("lifecycle") or {}).get("review_state")) or "").lower(),
        }
        return all(value in filter_values.get(key, "") for key, value in filters.items())

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-memo":
            raise ValueError(f"unsupported resource scheme: {parsed.scheme}")
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc == "brief" and path_parts[:1] == ["repo"] and len(path_parts) == 2:
            return self.build_brief(path_parts[1])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "local-port-status":
            return self.build_local_port_status(path_parts[0])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-port-index":
            return self.build_port_index(path_parts[0])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-open-items":
            return {
                "schema": "aoa_local_memo_open_items_v1",
                "repo": path_parts[0],
                "open_items": self.build_port_index(path_parts[0])["index"]["open_items"],
            }
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "pending-exports":
            return self.list_pending_exports(path_parts[0])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-vocabulary":
            return self.build_memo_port_vocabulary()
        if parsed.netloc == "intake" and len(path_parts) == 2 and path_parts[1] == "review":
            return self.find_intake_review(path_parts[0])
        if parsed.netloc == "memory" and path_parts[:1] == ["object"] and len(path_parts) == 2:
            return self.build_memory_object(path_parts[1])
        if parsed.netloc == "session" and len(path_parts) == 2 and path_parts[1] == "rehydrate":
            return self.build_session_rehydrate(path_parts[0])
        raise ValueError(f"unsupported aoa-memo resource URI: {uri}")

    def build_memo_port_vocabulary(self) -> dict[str, Any]:
        vocab_path = self.aoa_memo_root / CENTRAL_VOCABULARY
        payload = _read_json(vocab_path)
        return {
            "schema": "aoa_memo_port_vocabulary_resource_v1",
            "source_ref": str(vocab_path),
            "found": isinstance(payload, dict),
            "vocabulary": payload,
        }

    def find_intake_review(self, packet_id: str) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        for route in self._known_memo_port_routes():
            port = route.memo_port
            if port is None or not port.exists():
                continue
            for path in sorted((port / "exports").glob("*.json")):
                payload = _read_json(path)
                if isinstance(payload, dict) and packet_id in {str(payload.get("id")), path.stem}:
                    matches.append({"repo": route.name, "path": str(path), "packet": payload})
        return {
            "schema": "aoa_local_memo_intake_review_pointer_v1",
            "packet_id": packet_id,
            "found": bool(matches),
            "matches": matches,
        }

    def build_memory_object(self, object_id: str) -> dict[str, Any]:
        catalog_path = self.aoa_memo_root / MEMORY_OBJECT_CATALOG
        catalog = _read_json(catalog_path)
        matches: list[dict[str, Any]] = []
        if isinstance(catalog, dict):
            for item in catalog.get("memory_objects", []):
                if not isinstance(item, dict):
                    continue
                values = {
                    str(item.get("id") or ""),
                    str(item.get("inspect_key") or ""),
                    str(item.get("expand_key") or ""),
                }
                if object_id in values or object_id in str(item.get("id") or ""):
                    item_copy = dict(item)
                    source_path = item.get("source_path")
                    if isinstance(source_path, str):
                        source_payload = _read_json(self.aoa_memo_root / source_path)
                        if isinstance(source_payload, dict):
                            item_copy["object"] = source_payload
                    matches.append(item_copy)
        if matches:
            return {
                "schema": "aoa_memo_object_lookup_v1",
                "object_id": object_id,
                "catalog": str(catalog_path),
                "found": True,
                "matches": matches,
            }

        registry_path = self.aoa_memo_root / "generated/memory/memo_registry.min.json"
        registry = _read_json(registry_path)
        if isinstance(registry, dict):
            for key in ("memory_object_kinds", "supporting_objects", "recall_modes", "core_docs", "schemas"):
                value = registry.get(key)
                if isinstance(value, list):
                    for item in value:
                        if object_id in str(item):
                            matches.append({"registry_key": key, "value": item})
        return {
            "schema": "aoa_memo_object_lookup_v1",
            "object_id": object_id,
            "catalog": str(catalog_path),
            "fallback_registry": str(registry_path),
            "found": bool(matches),
            "matches": matches,
        }

    def build_reviewed_memory_object(self, object_id: str) -> dict[str, Any]:
        """Resolve one object only when it belongs to the reviewed durable corpus."""

        payload = self.build_memory_object(object_id)
        reviewed = [
            item
            for item in payload.get("matches", [])
            if isinstance(item, dict) and item.get("source_kind") == "reviewed_corpus"
        ]
        return {
            "schema": "aoa_memo_reviewed_object_lookup_v1",
            "object_id": object_id,
            "catalog": payload.get("catalog"),
            "found": bool(reviewed),
            "matches": reviewed,
            "source_owner": "aoa-memo",
            "access_projection": "reviewed_corpus_only",
            "authority_boundary": (
                "The reviewed object remains memory, not proof or current stronger-owner truth."
            ),
        }

    def build_session_rehydrate(self, session_id: str) -> dict[str, Any]:
        registry_path = self.aoa_archive_root / "session-registry.json"
        registry = _read_json(registry_path)
        session = None
        if isinstance(registry, dict):
            for item in registry.get("sessions", []):
                if not isinstance(item, dict):
                    continue
                label = (item.get("display") or {}).get("label")
                if item.get("session_id") == session_id or label == session_id:
                    session = item
                    break
        if not session:
            return {
                "schema": "aoa_session_rehydrate_pointer_v1",
                "session_id": session_id,
                "found": False,
                "registry": str(registry_path),
            }
        display = session.get("display") or {}
        raw_path = display.get("path") or display.get("archive_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return {
                "schema": "aoa_session_rehydrate_pointer_v1",
                "session_id": session.get("session_id"),
                "label": display.get("label"),
                "found": False,
                "registry": str(registry_path),
                "reason": "session archive path is missing",
            }
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (self.aoa_archive_root / path).resolve()
        else:
            path = path.resolve()
        if not path.is_dir():
            return {
                "schema": "aoa_session_rehydrate_pointer_v1",
                "session_id": session.get("session_id"),
                "label": display.get("label"),
                "found": False,
                "registry": str(registry_path),
                "session_path": str(path),
                "reason": "session archive path does not exist",
            }
        return {
            "schema": "aoa_session_rehydrate_pointer_v1",
            "session_id": session.get("session_id"),
            "label": display.get("label"),
            "found": True,
            "session_path": str(path),
            "agents": str(path / "AGENTS.md"),
            "session_md": str(path / "SESSION.md"),
            "manifest": str(path / "session.manifest.json"),
            "index": str(path / "session.index.json"),
        }

    def _central_contracts(self) -> list[dict[str, Any]]:
        return [
            {
                "path": rel,
                "abs_path": str(self.aoa_memo_root / rel),
                "exists": (self.aoa_memo_root / rel).exists(),
            }
            for rel in MEMORY_CONTRACTS
        ]

    def _port_payload(self, port: Path) -> dict[str, Any]:
        payload = _read_yaml(port / LOCAL_PORT_CONTRACT)
        return payload if isinstance(payload, dict) else {}

    def _schema_path(self, schema_name: str) -> Path:
        return self.aoa_memo_root / MEMORY_PORT_SCHEMA_DIR / schema_name

    def _schema_errors(self, schema_name: str, payload: Any, label: str) -> list[str]:
        schema_path = self._schema_path(schema_name)
        schema = _read_json(schema_path)
        if not isinstance(schema, dict):
            return [f"{label} schema file is missing or invalid: {schema_path}"]
        validator = Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
        rendered: list[str] = []
        for error in errors:
            location = "/".join(str(part) for part in error.absolute_path) or "$"
            rendered.append(f"{label} schema error at {location}: {error.message}")
        return rendered

    def _vocabulary_warnings(self) -> list[str]:
        payload = _read_json(self.aoa_memo_root / CENTRAL_VOCABULARY)
        terms_payload = payload.get("terms", {}) if isinstance(payload, dict) else {}
        if not isinstance(terms_payload, dict) or not terms_payload:
            return ["central memo port vocabulary is missing; fallback terms were used"]
        return []

    def _vocabulary_terms(self, port_payload: dict[str, Any] | None = None) -> dict[str, set[str]]:
        payload = _read_json(self.aoa_memo_root / CENTRAL_VOCABULARY)
        terms_payload = payload.get("terms", {}) if isinstance(payload, dict) else {}
        terms = {
            key: {str(value) for value in values}
            for key, values in terms_payload.items()
            if isinstance(values, list)
        }
        if not terms:
            terms = {key: set(values) for key, values in FALLBACK_VOCABULARY_TERMS.items()}
        local_terms = (port_payload or {}).get("local_terms") or {}
        if isinstance(local_terms, dict):
            for key, values in local_terms.items():
                if isinstance(values, list):
                    terms.setdefault(str(key), set()).update(str(value) for value in values)
        return terms

    def _validate_candidate_vocabulary(
        self,
        payload: dict[str, Any],
        port_payload: dict[str, Any] | None = None,
    ) -> list[str]:
        repo = str(payload.get("repo") or "")
        if port_payload is None:
            try:
                route = self.repo_route(repo)
            except ValueError:
                return []
            port_payload = self._port_payload(route.memo_port) if route.memo_port else {}
        terms = self._vocabulary_terms(port_payload)
        field_map = {
            "kind": "kind",
            "family": "family",
            "scope": "scope",
            "route": "route",
            "review_state": "review_state",
            "lifecycle": "lifecycle",
            "source_trust": "source_trust",
        }
        errors: list[str] = []
        for field, term_group in field_map.items():
            value = payload.get(field)
            if isinstance(value, str) and value not in terms.get(term_group, set()):
                errors.append(f"{field} uses unknown vocabulary term: {value}")
        risks = payload.get("risk", [])
        if isinstance(risks, list):
            for risk in risks:
                if isinstance(risk, str) and risk not in terms.get("risk", set()):
                    errors.append(f"risk uses unknown vocabulary term: {risk}")
        return errors

    def _build_port_index_for_path(self, port: Path) -> dict[str, Any]:
        payload = self._port_payload(port)
        candidates_dir = str(payload.get("candidate_dir", "candidates"))
        receipt_dir = str(payload.get("receipt_dir", "receipts"))
        export_dir = str(payload.get("export_dir", "exports"))
        local_dir = str(payload.get("local_dir", "local"))
        candidate_paths = sorted((port / candidates_dir).glob("*.json"))
        by_kind: dict[str, int] = {}
        by_family: dict[str, int] = {}
        by_route: dict[str, int] = {}
        open_items: list[dict[str, str]] = []
        created_at: list[str] = []
        source_refs = [LOCAL_PORT_CONTRACT]

        for directory in (candidates_dir, receipt_dir, export_dir, local_dir):
            for path in sorted((port / directory).glob("*.json")):
                source_refs.append(self._local_packet_ref(port, path))
                packet = _read_json(path)
                if isinstance(packet, dict) and isinstance(packet.get("created_at"), str):
                    created_at.append(packet["created_at"])

        for path in candidate_paths:
            candidate = _read_json(path)
            if not isinstance(candidate, dict):
                continue
            for field, target in (("kind", by_kind), ("family", by_family), ("route", by_route)):
                value = candidate.get(field)
                if isinstance(value, str) and value:
                    target[value] = target.get(value, 0) + 1
            review_state = str(candidate.get("review_state") or "candidate")
            if review_state not in TERMINAL_REVIEW_STATES:
                open_items.append(
                    {
                        "id": str(candidate.get("id") or path.stem),
                        "path": self._local_packet_ref(port, path),
                        "review_state": review_state,
                        "route": str(candidate.get("route") or "reviewed_intake"),
                    }
                )
        return {
            "schema": "aoa_local_memo_port_index_v1",
            "repo": str(payload.get("repo") or port.parent.name),
            "port": port.name,
            "default_mode": str(payload.get("default_mode") or "write_candidate_only"),
            "counts": {
                "candidates": len(candidate_paths),
                "receipts": len(sorted((port / receipt_dir).glob("*.json"))),
                "exports": len(sorted((port / export_dir).glob("*.json"))),
                "local": len(sorted((port / local_dir).glob("*.json"))),
            },
            "by_kind": dict(sorted(by_kind.items())),
            "by_family": dict(sorted(by_family.items())),
            "by_route": dict(sorted(by_route.items())),
            "open_items": sorted(open_items, key=lambda item: item["path"]),
            "generated_at": max(created_at) if created_at else "1970-01-01T00:00:00Z",
            "source_refs": [LOCAL_PORT_CONTRACT, *sorted(ref for ref in source_refs if ref != LOCAL_PORT_CONTRACT)],
        }

    def _render_port_index_markdown(self, index: dict[str, Any]) -> str:
        counts = index["counts"]
        lines = [
            f"# {index['repo']} memo port index",
            "",
            "Generated from `PORT.yaml` and local memo packets.",
            "",
            "## Counts",
            "",
            "| District | Count |",
            "|---|---:|",
            f"| candidates | {counts['candidates']} |",
            f"| receipts | {counts['receipts']} |",
            f"| exports | {counts['exports']} |",
            f"| local | {counts['local']} |",
            "",
            "## Routes",
            "",
        ]
        if index["by_route"]:
            lines.extend(["| Route | Count |", "|---|---:|"])
            for route, count in index["by_route"].items():
                lines.append(f"| `{route}` | {count} |")
        else:
            lines.append("No routed candidates yet.")
        lines.extend(["", "## Open Items", ""])
        if index["open_items"]:
            lines.extend(["| ID | State | Route | Path |", "|---|---|---|---|"])
            for item in index["open_items"]:
                lines.append(f"| `{item['id']}` | `{item['review_state']}` | `{item['route']}` | `{item['path']}` |")
        else:
            lines.append("No open candidate items.")
        lines.extend(
            [
                "",
                "## Agent Route",
                "",
                "Executable validation and rebuild commands live in the nearest `AGENTS.md` for this memo port.",
                "This generated index is a read model; it does not own the operational route.",
                "",
            ]
        )
        return "\n".join(lines)

    def _known_memo_ports(self) -> dict[str, Path]:
        ports: dict[str, Path] = {}
        for route in self._known_memo_port_routes():
            if route.memo_port is not None and route.memo_port.exists():
                ports[route.name] = route.memo_port.resolve()
        return ports

    def _known_memo_port_routes(self) -> list[RepoRoute]:
        routes: list[RepoRoute] = []
        seen: set[str] = set()
        for repo in self._workspace_memo_port_repo_names():
            try:
                route = self.repo_route(repo)
            except ValueError:
                continue
            if route.name in seen:
                continue
            seen.add(route.name)
            routes.append(route)
        return routes

    def _workspace_memo_port_repo_names(self) -> list[str]:
        names: list[str] = []
        places = self._workspace_memory_map().get("places", [])
        if isinstance(places, list):
            for place in places:
                if not isinstance(place, dict):
                    continue
                name = place.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                current_level = str(place.get("current_port_level") or "")
                route_status = str(place.get("memory_route_status") or "")
                if current_level in LOCAL_MEMO_PORT_LEVELS or route_status == "local_port_route":
                    names.append(name)
        for repo in LEGACY_MEMO_PORT_REPOS:
            if repo not in names:
                names.append(repo)
        return names

    def _require_known_memo_port_route(self, route: RepoRoute, action: str) -> None:
        assert route.memo_port is not None
        memo_port = route.memo_port.resolve()
        known_ports = self._known_memo_ports()
        if memo_port in set(known_ports.values()):
            return
        known = ", ".join(str(port) for port in known_ports.values()) or "none"
        raise ValueError(
            f"memo port is not registered as a known local memo port for {action}: "
            f"{route.name} ({memo_port}); known ports: {known}"
        )

    def _assert_under_port(self, port: Path, path: Path, required_dir: str | None = None) -> Path:
        resolved_port = port.expanduser().resolve()
        resolved_path = path.expanduser().resolve()
        try:
            relative = resolved_path.relative_to(resolved_port)
        except ValueError as exc:
            raise ValueError(f"path must stay inside memo port: {resolved_port}") from exc
        if required_dir and (not relative.parts or relative.parts[0] != required_dir):
            raise ValueError(f"path must stay inside memo/{required_dir}")
        return resolved_path

    def _known_port_for_path(self, path: Path, required_dir: str | None = None) -> tuple[str, Path, Path]:
        known_ports = self._known_memo_ports()
        for repo, port in known_ports.items():
            try:
                return repo, port, self._assert_under_port(port, path, required_dir)
            except ValueError:
                continue
        known = ", ".join(str(port) for port in known_ports.values()) or "none"
        raise ValueError(f"path must resolve under a known local memo port ({known})")

    def _export_landing_readiness(self, port: Path, export_path: Path, payload: Any) -> dict[str, Any]:
        errors: list[str] = []
        if not isinstance(payload, dict):
            return {
                "schema": "aoa_memo_export_landing_readiness_v1",
                "ok": False,
                "ready_for_landing": False,
                "landing_state": "invalid",
                "copied_intake": None,
                "errors": ["export packet is not a JSON object"],
            }
        errors.extend(self._schema_errors(LOCAL_MEMO_EXPORT_SCHEMA, payload, "export"))
        if payload.get("target_owner") != "aoa-memo" or payload.get("target_route") != "reviewed_intake":
            errors.append("export must target aoa-memo reviewed_intake")
        if payload.get("allowed_result") != "reviewed_write":
            errors.append("allowed_result must be reviewed_write for landing")
        if not payload.get("candidate_refs"):
            errors.append("candidate_refs must not be empty")
        if not payload.get("receipt_refs"):
            errors.append("receipt_refs must not be empty for landing readiness")
        if not payload.get("source_refs"):
            errors.append("source_refs must not be empty")
        if not payload.get("evidence_refs"):
            errors.append("evidence_refs must not be empty")
        self._check_payload_refs(errors, port, export_path, "source_refs", payload.get("source_refs"))
        self._check_payload_refs(errors, port, export_path, "evidence_refs", payload.get("evidence_refs"))

        for ref in payload.get("candidate_refs", []):
            try:
                candidate = self._resolve_local_ref(port, str(ref), "candidates")
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            if candidate is None or not candidate.exists():
                errors.append(f"missing candidate ref: {ref}")
                continue
            validation = self.validate_candidate(candidate)
            if not validation["ok"]:
                errors.extend(f"{ref}: {error}" for error in validation["errors"])

        for ref in payload.get("receipt_refs", []):
            try:
                receipt_path = self._resolve_local_ref(port, str(ref), "receipts")
            except ValueError as exc:
                errors.append(f"{ref}: {exc}")
                continue
            receipt = _read_json(receipt_path) if receipt_path else None
            if not isinstance(receipt, dict):
                errors.append(f"{ref}: receipt packet is missing or invalid")
                continue
            errors.extend(f"{ref}: {error}" for error in self._schema_errors(LOCAL_MEMO_RECEIPT_SCHEMA, receipt, "receipt"))
            if receipt.get("result") not in {"validated", "forwarded", "landed"}:
                errors.append(f"{ref}: receipt result must be validated, forwarded, or landed")
            if receipt.get("errors"):
                errors.append(f"{ref}: receipt has errors")
            self._check_payload_refs(errors, port, receipt_path, "candidate_ref", [receipt.get("candidate_ref")])

        copied_intake = self._copied_intake_path(str(payload.get("repo") or ""), export_path)
        landing_state = "landed" if copied_intake.exists() else ("ready" if not errors else "blocked")
        ready_for_landing = not errors and landing_state == "ready"
        return {
            "schema": "aoa_memo_export_landing_readiness_v1",
            "ok": not errors,
            "ready_for_landing": ready_for_landing,
            "landing_state": landing_state,
            "copied_intake": str(copied_intake),
            "errors": errors,
        }

    def _copied_intake_path(self, repo: str, export_path: Path) -> Path:
        return self.aoa_memo_root / "memo/intake/reviewed" / f"{_id_slug(repo, 80)}.{export_path.name}"

    def _repo_root_for_port(self, port: Path) -> Path:
        return port.parent if port.name == "memo" else port

    def _resolve_payload_ref(self, port: Path, ref: str) -> Path | None:
        ref = ref.strip()
        if not ref:
            return None
        if ref.startswith(SYMBOLIC_REF_PREFIXES):
            return None
        text = ref.split("#", 1)[0].strip()
        parsed = urlparse(text)
        line_ref = LOCAL_LINE_REF_RE.fullmatch(text)
        if line_ref and "://" not in text and not urlparse(line_ref.group("path")).scheme:
            text = line_ref.group("path").strip()
        elif parsed.scheme:
            return None
        path = Path(text)
        if path.is_absolute():
            raise ValueError("local refs must be relative or symbolic")
        repo_root = self._repo_root_for_port(port).resolve()
        if text.startswith("memo/"):
            target = repo_root / path
        else:
            port_relative = port / path
            target = port_relative if port_relative.exists() else repo_root / path
        resolved = target.resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError as exc:
            raise ValueError("local refs must stay under the repo owning the memo port") from exc
        return resolved

    def _check_payload_refs(
        self,
        errors: list[str],
        port: Path,
        packet_path: Path,
        label: str,
        refs: Any,
    ) -> None:
        if not isinstance(refs, list):
            errors.append(f"{packet_path}:{label} must be a list")
            return
        for index, ref in enumerate(refs):
            if not isinstance(ref, str) or not ref:
                errors.append(f"{packet_path}:{label}[{index}] must be a non-empty string")
                continue
            try:
                target = self._resolve_payload_ref(port, ref)
            except ValueError as exc:
                errors.append(f"{packet_path}:{label}[{index}] {exc}")
                continue
            if target is not None and not target.exists():
                errors.append(f"{packet_path}:{label}[{index}] points to missing ref {ref}")

    def _resolve_local_ref(self, port: Path, ref: str, preferred_dir: str) -> Path | None:
        ref = str(ref).strip()
        if not ref:
            raise ValueError("packet ref must be non-empty")
        if ref.startswith(("candidate:", "receipt:", "export:")):
            for path in sorted((port / preferred_dir).glob("*.json")):
                payload = _read_json(path)
                if isinstance(payload, dict) and payload.get("id") == ref:
                    return self._assert_under_port(port, path, preferred_dir)
            return None
        path = Path(ref.split("#", 1)[0])
        if path.is_absolute():
            raise ValueError("packet refs must be relative to the memo port")
        if ref.startswith("memo/"):
            return self._assert_under_port(port, port.parent / path, preferred_dir)
        candidate = port / path
        if candidate.exists():
            return self._assert_under_port(port, candidate, preferred_dir)
        candidate = port / preferred_dir / path.name
        if candidate.exists():
            return self._assert_under_port(port, candidate, preferred_dir)
        return self._assert_under_port(port, port / path, preferred_dir)

    def _local_packet_ref(self, port: Path, path: Path) -> str:
        return self._assert_under_port(port, path).relative_to(port.resolve()).as_posix()

    def _pending_export_counts(self, repo: str, port_status: dict[str, Any] | Path | None) -> dict[str, int]:
        if isinstance(port_status, dict):
            ready = bool(port_status.get("ready"))
        elif isinstance(port_status, Path):
            ready = bool(
                port_status.exists()
                and (port_status / "AGENTS.md").exists()
                and (port_status / "README.md").exists()
                and (port_status / LOCAL_PORT_CONTRACT).exists()
                and all((port_status / name).is_dir() for name in REQUIRED_PORT_DIRS)
            )
        else:
            ready = False
        if not ready:
            return {"total": 0, "pending": 0, "ready": 0, "landed": 0}
        return self.list_pending_exports(repo)["counts"]

    def _local_intake_summary(self, repo: str, port_status: dict[str, Any]) -> dict[str, Any]:
        if not port_status.get("ready"):
            return {"enabled": False, "pending_exports": 0, "ready_exports": 0, "landed_exports": 0}
        counts = self.list_pending_exports(repo)["counts"]
        return {
            "enabled": True,
            "pending_exports": counts["pending"],
            "ready_exports": counts["ready"],
            "landed_exports": counts["landed"],
            "route": "repo/memo candidate -> receipt -> export -> aoa-memo reviewed landing",
        }

    def _reviewed_memory_for_repo(self, repo: str, intent: str = "", limit: int = 5) -> list[dict[str, Any]]:
        catalog = _read_json(self.aoa_memo_root / MEMORY_OBJECT_CATALOG)
        if not isinstance(catalog, dict):
            return []
        terms = {repo.lower(), *[part.lower() for part in re.findall(r"[a-zA-Z0-9-]+", intent) if len(part) > 2]}
        hits: list[dict[str, Any]] = []
        for item in catalog.get("memory_objects", []):
            if not isinstance(item, dict) or item.get("source_kind") != "reviewed_corpus":
                continue
            haystack = json.dumps(item, ensure_ascii=False).lower()
            if any(term and term in haystack for term in terms):
                hits.append(
                    {
                        "id": item.get("id"),
                        "kind": item.get("kind"),
                        "title": item.get("title"),
                        "summary": item.get("summary"),
                        "current_recall_status": item.get("current_recall_status"),
                        "source_kind": item.get("source_kind"),
                        "source_path": item.get("source_path"),
                    }
                )
            if len(hits) >= limit:
                break
        return hits

    def _read_required_json(self, path: Path | None) -> dict[str, Any]:
        if path is None:
            raise ValueError("missing JSON path")
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} is not a JSON object")
        return payload

    def _workspace_memory_map(self) -> dict[str, Any]:
        payload = _read_json(self.workspace_root / "8Dionysus" / WORKSPACE_MEMORY_MAP)
        return payload if isinstance(payload, dict) else {}

    def _workspace_memory_place(self, repo: str) -> dict[str, Any]:
        payload = self._workspace_memory_map()
        places = payload.get("places", [])
        if not isinstance(places, list):
            return {}
        for place in places:
            if isinstance(place, dict) and place.get("name") == repo:
                return place
        return {}

    def _workspace_memory_summary(self, repo: str) -> dict[str, Any]:
        place = self._workspace_memory_place(repo)
        if not place:
            return {"found": False}
        keys = (
            "memory_role",
            "memory_route_status",
            "current_port_level",
            "recommended_port_level",
            "reviewed_memory_route",
            "evidence_route",
            "issues",
        )
        return {"found": True, **{key: place.get(key) for key in keys}}

    def _local_port_hierarchy_note(self, port: dict[str, Any]) -> str:
        if port.get("repo") == "aoa-memo":
            return "aoa-memo authored reviewed memory contracts and generated read models"
        if port.get("memory_route_status") == "session_evidence_route":
            return ".aoa session evidence and rehydration pointers, not a local memo port"
        if port["ready"]:
            return "repo-local memo port candidates, receipts, exports, and local records"
        return "workspace route-only status unless a repo-local memo port exists"

    def _candidate_route_note(self, route: RepoRoute, port: dict[str, Any]) -> str:
        route_status = str(port.get("memory_route_status") or "")
        memory_role = str(port.get("memory_role") or "")
        if memory_role == "reviewed-memory-owner":
            return "aoa-memo source patch/review path; no repo-local candidate shortcut"
        if route_status == "session_evidence_route":
            return ".aoa carries session evidence; candidate creation routes through a repo memo port or aoa-memo intake"
        if route.default_mode == "read_only" and port["ready"]:
            return "read-only memory route; no local candidate writes from this MCP route"
        if port["ready"]:
            return "repo memo/candidates"
        return "no local candidate route until this place has a memo port"

    def _recommended_route(self, route: RepoRoute, port: dict[str, Any]) -> list[str]:
        place = self._workspace_memory_place(route.name)
        memory_role = str(place.get("memory_role") or "")
        route_status = str(place.get("memory_route_status") or "")
        recommended_level = str(place.get("recommended_port_level") or "")
        current_level = str(place.get("current_port_level") or "")
        if memory_role == "reviewed-memory-owner":
            return [
                "read aoa-memo root AGENTS.md and memory contracts",
                "use MCP for brief/search/access only",
                "land durable memory through aoa-memo source patches, validators, and review",
            ]
        if route_status == "session_evidence_route":
            return [
                "read .aoa owner guidance for session evidence",
                "use session rehydrate or retrieve routes for raw grounding",
                "send reviewed memory candidates through a repo memo port or aoa-memo intake route",
            ]
        if route.default_mode == "read_only" and port["ready"]:
            return [
                "read the workspace memory map for current read-only status",
                "use aoa_memo for reviewed recall and owner evidence routes for grounding",
                "do not create local candidates from this MCP route",
                "land durable memory through aoa-memo reviewed intake only from a writable owner route",
            ]
        if not port["ready"]:
            if recommended_level == "full_port" and current_level == "route_only":
                return [
                    "read the workspace memory map for current route-only status",
                    "use aoa_memo_brief and .aoa evidence routes for recall now",
                    "add this repo's memo port only through a repo-local topology pass",
                    "land durable memory through aoa-memo reviewed intake",
                ]
            return [
                "read the workspace memory map for current route-only status",
                "use aoa_memo for reviewed recall and .aoa for session evidence",
                "write local candidates only after a memo port exists",
                "land durable memory through aoa-memo reviewed intake",
            ]
        return [
            "read local memo/AGENTS.md",
            "create local candidate under memo/candidates",
            "validate candidate through aoa_memo_validate_candidate",
            "export reviewed intake packet for aoa-memo",
            "let aoa-memo decide promote, supersede, retract, archive, or keep local",
        ]

    def _search_roots(self, scope: str) -> list[Path]:
        roots: list[Path] = []
        if scope in ("all", "workspace", "routes", "contracts"):
            roots.extend(
                [
                    self.workspace_root / "8Dionysus" / "docs" / "WORKSPACE_MEMORY_MAP.md",
                    self.workspace_root / "8Dionysus" / WORKSPACE_MEMORY_MAP,
                ]
            )
        if scope in ("all", "central", "aoa-memo"):
            roots.extend([self.aoa_memo_root / "docs", self.aoa_memo_root / "mechanics", self.aoa_memo_root / "generated/memory"])
        if scope in ("all", "local", "ports"):
            for route in self._known_memo_port_routes():
                port = route.memo_port
                if port is not None:
                    roots.append(port)
        if scope in ("all", "session", ".aoa"):
            roots.extend([self.aoa_archive_root / "SESSION_NAMES.md", self.aoa_archive_root / "sessions/INDEX.md", self.aoa_archive_root / "session-registry.json"])
        return roots

    def _iter_search_files(self, root: Path):
        if root.is_file() and root.suffix in TEXT_SUFFIXES:
            yield root
            return
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            if any(part in {".git", "__pycache__", "raw"} for part in path.parts):
                continue
            if path.suffix in TEXT_SUFFIXES:
                yield path

    def _normalize_repo(self, repo: str) -> str:
        if not isinstance(repo, str):
            raise ValueError("repo must be a repository name or approved alias")
        candidate = repo.strip()
        if not candidate:
            raise ValueError("repo must be a repository name or approved alias")
        aliases = {
            "agents": "Agents-of-Abyss",
            "agents-of-abyss": "Agents-of-Abyss",
            "aoa": "Agents-of-Abyss",
            "stack": "abyss-stack",
            "machine": "abyss-machine",
        }
        normalized = aliases.get(candidate, candidate)
        if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
            raise ValueError("repo must be a repository name or approved alias, not a path")
        return normalized
