from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError("could not find abyss-stack repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
CLOSEOUT_PART = (
    REPO_ROOT / "mechanics" / "runtime-repair" / "parts" / "repair-safe-closeout"
)
SCHEMAS = CLOSEOUT_PART / "schemas"
EXAMPLES = CLOSEOUT_PART / "examples"


def load_json(relative_path: str) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def load_schema(name: str) -> object:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def load_example(name: str) -> object:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


class AntifragilityContractTests(unittest.TestCase):
    def test_repair_safe_closeout_examples_validate_against_schema(self) -> None:
        schema_pairs = [
            ("repair-safe-closeout-receipt.schema.json", "repair-safe-closeout-receipt.example.json"),
            (
                "repair-safe-closeout-receipt.schema.json",
                "repair-safe-closeout-receipt.timeout-chaos.example.json",
            ),
            (
                "repair-safe-closeout-receipt.schema.json",
                "repair-safe-closeout-receipt.retrieval-outage-honesty.example.json",
            ),
        ]

        for schema_path, example_path in schema_pairs:
            validator = Draft202012Validator(load_schema(schema_path))
            validator.validate(load_example(example_path))

    def test_repair_safe_closeout_receipt_requires_reviewed_true(self) -> None:
        schema = load_schema("repair-safe-closeout-receipt.schema.json")
        payload = load_example("repair-safe-closeout-receipt.example.json")
        assert isinstance(schema, dict)
        assert isinstance(payload, dict)
        payload["reviewed"] = False

        validator = Draft202012Validator(schema)
        with self.assertRaises(Exception):
            validator.validate(payload)

    def test_repair_safe_closeout_receipt_requires_at_least_one_action(self) -> None:
        schema = load_schema("repair-safe-closeout-receipt.schema.json")
        payload = load_example("repair-safe-closeout-receipt.example.json")
        assert isinstance(schema, dict)
        assert isinstance(payload, dict)
        payload["actions_taken"] = []

        validator = Draft202012Validator(schema)
        with self.assertRaises(Exception):
            validator.validate(payload)

    def test_runtime_antifragility_docs_keep_source_vs_runtime_boundary(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        runtime_doc = (
            REPO_ROOT
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "antifragility-posture"
            / "docs"
            / "ANTIFRAGILITY_RUNTIME.md"
        ).read_text(encoding="utf-8")
        closeout_doc = (
            REPO_ROOT
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "repair-safe-closeout"
            / "docs"
            / "REPAIR_SAFE_CLOSEOUT.md"
        ).read_text(encoding="utf-8")

        for fragment in [
            "mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md",
            "mechanics/runtime-repair/PROVENANCE.md",
            "mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md",
            "mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json",
            "mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json",
            "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.example.json",
            "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.timeout-chaos.example.json",
            "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.honest-degradation.example.json",
            "mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.retrieval-outage-honesty.example.json",
            "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.example.json",
            "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.timeout-chaos.example.json",
            "mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.retrieval-outage-honesty.example.json",
        ]:
            self.assertIn(fragment, readme)

        self.assertNotIn("mechanics/runtime-repair/legacy/artifacts/schemas", readme)
        self.assertNotIn("mechanics/runtime-repair/legacy/artifacts/examples", readme)

        self.assertIn("`~/src/abyss-stack` is the source checkout.", runtime_doc)
        self.assertIn("`/srv/AbyssOS/abyss-stack` is the deployed runtime mirror.", runtime_doc)
        self.assertIn("Do not patch `/srv/AbyssOS/abyss-stack` and pretend the system learned.", closeout_doc)
