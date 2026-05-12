from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateStackRuntimeHygieneTests(unittest.TestCase):
    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in (
            Path("docs") / "GATEWAY_CACHE_POLICY.md",
            Path("docs") / "USAGE_BUDGET_POLICY.md",
            Path("docs") / "LOCAL_OPS_DOCTOR_SPLIT.md",
            Path("docs") / "SERVICE_CATALOG.md",
            Path("docs") / "RUNBOOK.md",
            Path("docs") / "DOCTOR.md",
            Path("schemas") / "runtime-gateway-cache-status.schema.json",
            Path("schemas") / "runtime-usage-snapshot.schema.json",
            Path("examples") / "runtime_gateway_cache_status.gateway-local.example.json",
            Path("examples") / "runtime_usage_snapshot.workhorse-local.example.json",
        ):
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )

    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_runtime_hygiene_contracts(errors)
        return errors

    def test_git_mirror_hygiene_blocks_live_private_and_heavy_paths(self) -> None:
        blocked_paths = (
            "Secrets/Configs/stack.env",
            "Logs/machine-fit/latest/latest.private.json",
            "Models/qwen3.gguf",
            "stack.env",
            "compose/abyss.rendered.yml",
            "runtime/state.sqlite",
            "local/build.tar.gz",
            "cache/model.safetensors",
        )

        for relative_path in blocked_paths:
            with self.subTest(relative_path=relative_path):
                self.assertIsNotNone(
                    validate_stack.tracked_file_git_mirror_hygiene_issue(
                        relative_path
                    )
                )

    def test_git_mirror_hygiene_allows_public_docs_examples_and_fixtures(self) -> None:
        allowed_paths = (
            "env/stack.env.example",
            "docs/SECRETS_BOOTSTRAP.md",
            "docs/reference-platform/reference-host.public.json.example",
            "schemas/runtime-usage-snapshot.schema.json",
            "examples/runtime_usage_snapshot.workhorse-local.example.json",
            "tests/fixtures/latest.private.json",
            "mechanics/machine-fit/docs/machine-bridge/machine-bridge.public.json.example",
            "config-templates/Services/tos-graph/app/models.py",
        )

        for relative_path in allowed_paths:
            with self.subTest(relative_path=relative_path):
                self.assertIsNone(
                    validate_stack.tracked_file_git_mirror_hygiene_issue(
                        relative_path
                    )
                )

    def test_current_repo_runtime_hygiene_contracts_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_runtime_hygiene_contracts(errors)
        self.assertEqual(errors, [])

    def test_missing_gateway_policy_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (repo_root / "docs" / "GATEWAY_CACHE_POLICY.md").unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("docs/GATEWAY_CACHE_POLICY.md" in error for error in errors))

    def test_gateway_schema_surface_type_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "schemas" / "runtime-gateway-cache-status.schema.json",
                (repo_root / "schemas" / "runtime-gateway-cache-status.schema.json")
                .read_text(encoding="utf-8")
                .replace(
                    '"const": "runtime_gateway_cache_status"',
                    '"const": "runtime_gateway_cache_status_v999"',
                    1,
                ),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("runtime_gateway_cache_status" in error for error in errors)
        )

    def test_gateway_schema_top_level_array_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "schemas" / "runtime-gateway-cache-status.schema.json",
                "[]\n",
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any(
                "schemas/runtime-gateway-cache-status.schema.json must contain a top-level JSON object"
                == error
                for error in errors
            )
        )

    def test_cache_example_requires_inflight_replay_and_no_cache_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "examples" / "runtime_gateway_cache_status.gateway-local.example.json",
                (repo_root / "examples" / "runtime_gateway_cache_status.gateway-local.example.json")
                .read_text(encoding="utf-8")
                .replace('"decision": "inflight_replay"', '"decision": "miss"', 1)
                .replace('"cache_control": "no-cache"', '"cache_control": "max-age=60"', 1),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("runtime gateway cache status example" in error for error in errors)
        )

    def test_usage_example_must_avoid_billing_terms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "examples" / "runtime_usage_snapshot.workhorse-local.example.json",
                (repo_root / "examples" / "runtime_usage_snapshot.workhorse-local.example.json")
                .read_text(encoding="utf-8")
                .replace("cross-host economics", "billing dashboard"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("billing semantics" in error for error in errors))

    def test_doctor_doc_must_reference_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / "docs" / "DOCTOR.md",
                (repo_root / "docs" / "DOCTOR.md")
                .read_text(encoding="utf-8")
                .replace("docs/LOCAL_OPS_DOCTOR_SPLIT.md", "docs/LOCAL_OPS_SPLIT.md"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("docs/DOCTOR.md must mention `docs/LOCAL_OPS_DOCTOR_SPLIT.md`" == error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
