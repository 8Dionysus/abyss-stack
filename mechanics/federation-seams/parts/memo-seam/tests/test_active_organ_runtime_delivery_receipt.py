from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.validators.federation_runtime_seams import (
    apply_active_organ_delivery_negative_mutations,
    validate_active_organ_runtime_delivery_payload,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = (
    REPO_ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "memo-seam"
)
SCHEMA_PATH = PART_ROOT / "schemas" / "active-organ-runtime-delivery-receipt.schema.json"
EXAMPLES = PART_ROOT / "examples"
NEGATIVE_EXAMPLES = (
    EXAMPLES / "active_organ_runtime_delivery_receipt.negative-examples.json"
)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_schema_and_all_positive_examples_are_valid() -> None:
    schema = load_json(SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    examples = sorted(EXAMPLES.glob("*.example.json"))

    assert {path.stem.split(".")[-2] for path in examples} == {
        "attempted",
        "delivered",
        "expired",
        "failed",
        "suppressed",
    }
    for path in examples:
        payload = load_json(path)
        validator.validate(payload)
        assert validate_active_organ_runtime_delivery_payload(
            payload,
            schema=schema,
        ) == [], path.name


def test_executable_negative_examples_fail_closed() -> None:
    schema = load_json(SCHEMA_PATH)
    corpus = load_json(NEGATIVE_EXAMPLES)
    assert isinstance(corpus, dict)
    assert (
        corpus["schema_version"]
        == "active_organ_runtime_delivery_receipt_negative_examples_v1"
    )

    for case in corpus["cases"]:
        base = load_json(EXAMPLES / case["base_example"])
        mutated = apply_active_organ_delivery_negative_mutations(
            copy.deepcopy(base),
            case["set"],
        )
        errors = validate_active_organ_runtime_delivery_payload(
            mutated,
            schema=schema,
        )
        assert errors, case["case_id"]
        assert any(case["expected_error"] in error for error in errors), (
            case["case_id"],
            errors,
        )


def test_receipt_never_claims_memory_or_effect_authority() -> None:
    for path in sorted(EXAMPLES.glob("*.example.json")):
        payload = load_json(path)
        assert payload["runtime_owner"] == "abyss-stack"
        assert payload["authority"] == {
            "delivery_authority": "already_admitted_packet_only",
            "effect_authority": "none",
            "memory_semantic_authority": False,
            "policy_widening_authority": False,
        }
        assert payload["content_minimization"] == {
            "persistence_mode": "refs_only",
            "packet_content_persisted": False,
            "prompt_content_persisted": False,
            "memory_content_persisted": False,
            "payload_digest_persisted": False,
            "error_detail_persisted": False,
        }


def test_owner_docs_route_c20_without_claiming_live_runtime() -> None:
    readme = (PART_ROOT / "README.md").read_text(encoding="utf-8")
    seam_doc = (PART_ROOT / "docs" / "MEMO_RUNTIME_SEAM.md").read_text(
        encoding="utf-8"
    )

    for token in (
        "RuntimeDeliveryReceipt",
        "active-organ-runtime-delivery-receipt.schema.json",
        "attempted",
        "delivered",
        "suppressed",
        "expired",
        "failed",
    ):
        assert token in readme or token in seam_doc
    assert "does not prove a live" in seam_doc
    assert "delivery service or deployed runtime consumption" in seam_doc
