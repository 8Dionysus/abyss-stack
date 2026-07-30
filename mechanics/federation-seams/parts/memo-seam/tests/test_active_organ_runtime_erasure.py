from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    PART_ROOT
    / "schemas"
    / "active-organ-runtime-erasure-owner-extension-v0.schema.json"
)


def payload(surface_id: str) -> dict:
    er4 = surface_id == "ER4"
    return {
        "schema_version": "active_organ_owner_erasure_extension_v0",
        "extension_id": f"erase-extension:phase11:{surface_id}",
        "parent_owner": "abyss-stack",
        "worker_owner": f"abyss-stack-{surface_id.lower()}",
        "surface_id": surface_id,
        "work_item_ref": f"erase-work:phase11:{surface_id}",
        "material_classes": (
            ["runtime_store", "cache", "nervous_index"]
            if er4
            else ["export", "backup_restore_descendant"]
        ),
        "target_ref_digests": ["sha256:" + ("1" * 64)],
        "operation_evidence_refs": [f"operation:phase11:{surface_id}"],
        "recovery_probe_ref": f"probe:phase11:{surface_id}",
        "result": "erased",
        "residue_refs": [],
        "retention_exceptions": [],
        "restore_recovery_checked": True,
        "project_root_mutation": "forbidden",
        "host_root_mutation": "forbidden",
        "subject_material_included": False,
        "content_minimized": True,
        "execution_posture": "reference_lab_only",
        "live_execution": False,
        "effect_authority": "owner_local_erasure_only",
        "global_completion_authority": False,
        "content_digest": "sha256:" + ("2" * 64),
    }


def test_er4_er5_extension_covers_runtime_backup_and_restore_race() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    assert list(validator.iter_errors(payload("ER4"))) == []
    assert list(validator.iter_errors(payload("ER5"))) == []

    missing_cache = deepcopy(payload("ER4"))
    missing_cache["material_classes"].remove("cache")
    assert list(validator.iter_errors(missing_cache))

    no_restore_probe = deepcopy(payload("ER5"))
    no_restore_probe["restore_recovery_checked"] = False
    assert list(validator.iter_errors(no_restore_probe))

    host_mutation = deepcopy(payload("ER4"))
    host_mutation["host_root_mutation"] = "allowed"
    assert list(validator.iter_errors(host_mutation))
