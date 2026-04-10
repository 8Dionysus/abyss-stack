from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


class AntifragilityContractTests(unittest.TestCase):
    def test_runtime_receipt_examples_validate_against_schemas(self) -> None:
        schema_pairs = [
            (
                "schemas/service_degradation_receipt_v1.json",
                "examples/service_degradation_receipt.example.json",
            ),
            (
                "schemas/repair_safe_closeout_receipt_v1.json",
                "examples/repair_safe_closeout_receipt.example.json",
            ),
        ]

        for schema_path, example_path in schema_pairs:
            validator = Draft202012Validator(load_json(schema_path))
            validator.validate(load_json(example_path))

    def test_repair_safe_closeout_receipt_requires_reviewed_true(self) -> None:
        schema = load_json("schemas/repair_safe_closeout_receipt_v1.json")
        payload = load_json("examples/repair_safe_closeout_receipt.example.json")
        assert isinstance(schema, dict)
        assert isinstance(payload, dict)
        payload["reviewed"] = False

        validator = Draft202012Validator(schema)
        with self.assertRaises(Exception):
            validator.validate(payload)

    def test_repair_safe_closeout_receipt_requires_at_least_one_action(self) -> None:
        schema = load_json("schemas/repair_safe_closeout_receipt_v1.json")
        payload = load_json("examples/repair_safe_closeout_receipt.example.json")
        assert isinstance(schema, dict)
        assert isinstance(payload, dict)
        payload["actions_taken"] = []

        validator = Draft202012Validator(schema)
        with self.assertRaises(Exception):
            validator.validate(payload)

    def test_runtime_antifragility_docs_keep_source_vs_runtime_boundary(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        runtime_doc = (REPO_ROOT / "docs" / "ANTIFRAGILITY_RUNTIME.md").read_text(encoding="utf-8")
        closeout_doc = (REPO_ROOT / "docs" / "REPAIR_SAFE_CLOSEOUT.md").read_text(encoding="utf-8")

        for fragment in [
            "docs/ANTIFRAGILITY_RUNTIME.md",
            "docs/REPAIR_SAFE_CLOSEOUT.md",
            "schemas/service_degradation_receipt_v1.json",
            "schemas/repair_safe_closeout_receipt_v1.json",
            "examples/service_degradation_receipt.example.json",
            "examples/repair_safe_closeout_receipt.example.json",
        ]:
            self.assertIn(fragment, readme)

        self.assertIn("`~/src/abyss-stack` is the source checkout.", runtime_doc)
        self.assertIn("`/srv/abyss-stack` is the deployed runtime mirror.", runtime_doc)
        self.assertIn("Do not patch `/srv/abyss-stack` and pretend the system learned.", closeout_doc)
