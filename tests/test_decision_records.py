from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import decision_indexes  # noqa: E402
import generate_decision_indexes  # noqa: E402
import validate_decision_records as decisions  # noqa: E402


def canonical_record_text(*, decision_id: str = "ABYSS-STACK-D-9999", date: str = "2026-05-14") -> str:
    return (
        "# Test Decision\n\n"
        f"- Decision ID: {decision_id}\n"
        "- Status: accepted\n"
        f"- Date: {date}\n"
        "- Owner surface: `docs/decisions/`\n\n"
        "## Index Metadata\n\n"
        f"- Original date: {date}\n"
        "- Surface classes: docs route\n"
        "- Stack lanes: decision lane\n"
        "- Mechanic parents: none\n"
        "- Guard families: decision index/read-model\n"
        "- Posture: accepted test rationale\n\n"
        "## Context\n\n"
        "A real choice exists.\n\n"
        "## Options considered\n\n"
        "- One route.\n\n"
        "## Decision\n\n"
        "Choose one route.\n\n"
        "## Rationale\n\n"
        "The reason is durable.\n\n"
        "## Consequences\n\n"
        "- The route is clear.\n\n"
        "## Source surfaces\n\n"
        "- `ROADMAP.md`\n\n"
        "## Follow-up route\n\n"
        "Revisit when the route changes.\n"
    )


class DecisionRecordTests(unittest.TestCase):
    def test_repo_decision_records_validate(self) -> None:
        self.assertEqual(decisions.validate_all(), [])

    def test_current_decision_indexes_are_fresh(self) -> None:
        self.assertEqual(decision_indexes.validate_decision_index_surfaces(ROOT), [])

    def test_record_requires_standard_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root / "ABYSS-STACK-D-9999-test-decision.md"
            record.write_text(
                canonical_record_text().replace("## Options considered\n\n- One route.\n\n", ""),
                encoding="utf-8",
            )

            problems = decisions.validate_record(record)

        self.assertIn(
            "ABYSS-STACK-D-9999-test-decision.md: missing section ## Options considered",
            [problem.split("docs/decisions/")[-1] for problem in problems],
        )

    def test_record_date_must_match_index_metadata_original_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root / "ABYSS-STACK-D-9999-test-decision.md"
            record.write_text(
                canonical_record_text(date="2026-05-14").replace(
                    "- Date: 2026-05-14",
                    "- Date: 2026-05-13",
                ),
                encoding="utf-8",
            )

            problems = decisions.validate_record(record)

        self.assertIn(
            "ABYSS-STACK-D-9999-test-decision.md: Date 2026-05-13 does not match Index Metadata Original date 2026-05-14",
            [problem.split("docs/decisions/")[-1] for problem in problems],
        )

    def test_canonical_filename_must_match_decision_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(ROOT / "docs" / "decisions", temp_root / "docs" / "decisions")
            wrong_path = (
                temp_root
                / "docs"
                / "decisions"
                / "ABYSS-STACK-D-9999-canonical-decision-ids-and-indexes.md"
            )
            source_path = (
                temp_root
                / "docs"
                / "decisions"
                / "ABYSS-STACK-D-0038-canonical-decision-ids-and-indexes.md"
            )
            source_path.rename(wrong_path)

            records, issues = decision_indexes.collect_decision_records(temp_root)

        self.assertTrue(records)
        self.assertIn(
            (
                "docs/decisions/ABYSS-STACK-D-9999-canonical-decision-ids-and-indexes.md",
                "decision path canonical ID must match the note Decision ID",
            ),
            issues,
        )

    def test_generated_index_contract_names_expected_outputs(self) -> None:
        contract, issues = decision_indexes.load_index_contract(ROOT)

        self.assertEqual([], issues)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("ABYSS-STACK-D", contract["decision_id_prefix"])
        self.assertEqual(
            [path.as_posix() for path in decision_indexes.GENERATED_INDEX_PATHS],
            contract["generated_indexes"],
        )

    def test_generate_check_uses_full_contract_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            shutil.copytree(ROOT / "docs" / "decisions", temp_root / "docs" / "decisions")
            contract_path = temp_root / "docs" / "decisions" / "indexes" / "index_contract.yaml"
            contract_text = contract_path.read_text(encoding="utf-8")
            contract_path.write_text(
                contract_text.replace("decision_id_prefix: ABYSS-STACK-D", "decision_id_prefix: ABYSS-BAD-D"),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "generate_decision_indexes.py",
                        "--check",
                        "--repo-root",
                        temp_root.as_posix(),
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                exit_code = generate_decision_indexes.main()

        self.assertEqual(1, exit_code)
        self.assertIn("decision_id_prefix must be ABYSS-STACK-D", stdout.getvalue())

    def test_index_contract_validation_covers_parser_contract_fields(self) -> None:
        contract, issues = decision_indexes.load_index_contract(ROOT)
        self.assertEqual([], issues)
        assert contract is not None

        drifted = dict(contract)
        drifted["path_policy"] = "date_prefixed_filename"
        drifted["source_glob"] = "docs/decisions/*.md"
        drifted["required_metadata"] = ["Original date"]

        contract_issues = decision_indexes.validate_index_contract_payload(drifted)

        self.assertIn(
            (
                "docs/decisions/indexes/index_contract.yaml",
                "path_policy must be full_canonical_id_filename",
            ),
            contract_issues,
        )
        self.assertIn(
            (
                "docs/decisions/indexes/index_contract.yaml",
                "source_glob must be docs/decisions/ABYSS-STACK-D-*.md",
            ),
            contract_issues,
        )
        self.assertIn(
            (
                "docs/decisions/indexes/index_contract.yaml",
                "required_metadata must match the parsed decision metadata fields",
            ),
            contract_issues,
        )


if __name__ == "__main__":
    unittest.main()
