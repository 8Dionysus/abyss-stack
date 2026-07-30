from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    PART_ROOT
    / "schemas"
    / "active-organ-agent-local-runtime-namespace-v0.schema.json"
)


def payload(state: str) -> dict:
    zero = state == "consumer_zero"
    isolated = state == "isolated"
    return {
        "schema_version": "active_organ_agent_local_runtime_namespace_v0",
        "runtime_namespace_id": "runtime-namespace:coder-alpha",
        "namespace_id": "namespace:coder-alpha",
        "namespace_generation": 3,
        "agent_id": "AOA-A-0002",
        "tenant_id": "tenant:operator",
        "state": state,
        "sdk_plan_ref": f"plan:coder:{state}",
        "sdk_plan_digest": "sha256:" + "1" * 64,
        "agent_namespace_contract_ref": (
            "schemas/active-organ-agent-local-namespace-v0.schema.json"
        ),
        "agent_namespace_contract_digest": "sha256:" + "2" * 64,
        "case_classes": ["episodic", "procedural"],
        "storage_budget": {
            "max_objects": 128,
            "max_bytes": 1048576,
            "write_amplification_ceiling": 3,
        },
        "isolation": {
            "storage_key": "tenant-operator/coder-alpha/3",
            "read_scope": "exact_namespace_generation",
            "write_scope": "exact_namespace_generation",
            "cross_agent_read": "forbidden",
            "cross_tenant_read": "forbidden",
            "failure_scope": "namespace_only",
        },
        "expiry": {
            "namespace_local": True,
            "expires_at": "2026-08-05T12:00:00Z",
            "shared_lifecycle_effect": "none",
        },
        "rollback": {
            "target_generation": 2,
            "scope": "namespace_only",
            "receipt_ref": "rollback:coder-alpha/3-to-2",
            "shared_ledger_effect": "none",
        },
        "promotion": {
            "mode": "reviewed_nomination_only",
            "handoff_owner": "aoa-memo",
            "direct_shared_write": "forbidden",
        },
        "shared_organ": {
            "available_when_local_isolated": True,
            "dependency_on_local_namespace": "none",
        },
        "consumer_zero": {
            "evidence_ref": "consumer-zero:coder-alpha" if zero else None,
            "local_material_state": (
                "absent" if zero else "isolated" if isolated else "present"
            ),
            "new_reads": not (zero or isolated),
            "new_writes": not (zero or isolated),
            "new_promotions": not (zero or isolated),
        },
        "execution_posture": "reference_lab_only",
        "live_execution": False,
        "effect_authority": "none",
    }


def test_active_isolated_and_consumer_zero_states_are_exact() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for state in ("active", "isolated", "consumer_zero"):
        assert list(validator.iter_errors(payload(state))) == []


def test_cross_namespace_and_shared_write_drift_fail_closed() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    leaked = deepcopy(payload("active"))
    leaked["isolation"]["cross_agent_read"] = "allowed"
    assert list(validator.iter_errors(leaked))

    shared_write = deepcopy(payload("active"))
    shared_write["promotion"]["direct_shared_write"] = "allowed"
    assert list(validator.iter_errors(shared_write))


def test_isolation_preserves_shared_organ_and_consumer_zero_removes_local_use() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    broken_shared = deepcopy(payload("isolated"))
    broken_shared["shared_organ"]["available_when_local_isolated"] = False
    assert list(validator.iter_errors(broken_shared))

    residual = deepcopy(payload("consumer_zero"))
    residual["consumer_zero"]["new_reads"] = True
    assert list(validator.iter_errors(residual))
