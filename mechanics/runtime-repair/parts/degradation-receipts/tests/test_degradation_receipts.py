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
DEGRADATION_PART = (
    REPO_ROOT / "mechanics" / "runtime-repair" / "parts" / "degradation-receipts"
)
SCHEMAS = DEGRADATION_PART / "schemas"
EXAMPLES = DEGRADATION_PART / "examples"


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema(name: str) -> object:
    return load_json(SCHEMAS / name)


def load_example(name: str) -> object:
    return load_json(EXAMPLES / name)


class DegradationReceiptContractTests(unittest.TestCase):
    def test_degradation_receipt_examples_validate_against_schema(self) -> None:
        schema_pairs = [
            ("service-degradation-receipt.schema.json", "service-degradation-receipt.example.json"),
            (
                "service-degradation-receipt.schema.json",
                "service-degradation-receipt.timeout-chaos.example.json",
            ),
            (
                "service-degradation-receipt.schema.json",
                "service-degradation-receipt.honest-degradation.example.json",
            ),
            (
                "service-degradation-receipt.schema.json",
                "service-degradation-receipt.retrieval-outage-honesty.example.json",
            ),
        ]

        for schema_path, example_path in schema_pairs:
            validator = Draft202012Validator(load_schema(schema_path))
            validator.validate(load_example(example_path))

    def test_degradation_examples_stay_explicit_and_operator_visible(self) -> None:
        for path in sorted(EXAMPLES.glob("service-degradation-receipt*.example.json")):
            payload = load_json(path)
            assert isinstance(payload, dict)
            self.assertIs(payload.get("degraded"), True, path.name)
            self.assertIs(payload.get("operator_visible"), True, path.name)
            self.assertIs(payload.get("unsafe_repair_blocked"), True, path.name)

    def test_archive_bridge_points_to_active_part(self) -> None:
        archive_readme = (
            REPO_ROOT
            / "mechanics"
            / "runtime-repair"
            / "legacy"
            / "artifacts"
            / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("parts/degradation-receipts/", archive_readme)
        self.assertIn("parts/repair-safe-closeout/", archive_readme)
        self.assertIn("legacy/raw/RUNTIME_CHAOS_WAVE1.md", archive_readme)


if __name__ == "__main__":
    unittest.main()
