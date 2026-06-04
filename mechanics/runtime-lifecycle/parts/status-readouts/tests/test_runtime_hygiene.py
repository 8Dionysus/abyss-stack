from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validators import runtime_hygiene
from scripts.validators import source_hygiene


REPO_ROOT = Path(__file__).resolve().parents[5]
RUNTIME_LIFECYCLE_SURFACE_ROOT = Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts"
RUNTIME_LIFECYCLE_SCHEMA_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "schemas"
RUNTIME_LIFECYCLE_EXAMPLE_ROOT = RUNTIME_LIFECYCLE_SURFACE_ROOT / "examples"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class RuntimeHygieneContractTests(unittest.TestCase):
    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in (
            Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "GATEWAY_CACHE_POLICY.md",
            Path("mechanics") / "runtime-lifecycle" / "parts" / "status-readouts" / "docs" / "USAGE_BUDGET_POLICY.md",
            Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "LOCAL_OPS_DOCTOR_SPLIT.md",
            Path("docs") / "runtime" / "SERVICE_CATALOG.md",
            Path("docs") / "operations" / "RUNBOOK.md",
            Path("mechanics") / "diagnostic-spine" / "parts" / "doctor-readiness" / "docs" / "DOCTOR.md",
            RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json",
            RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-usage-snapshot.schema.json",
            RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_gateway_cache_status.gateway-local.example.json",
            RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_usage_snapshot.workhorse-local.example.json",
        ):
            write_text(
                repo_root / relative_path,
                (REPO_ROOT / relative_path).read_text(encoding="utf-8"),
            )

    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        runtime_hygiene.validate_runtime_hygiene_contracts(errors, root=repo_root)
        return errors

    def tracked_hygiene_issue(self, relative_path: str) -> str | None:
        return source_hygiene.tracked_file_git_mirror_hygiene_issue(
            relative_path,
            runtime_top_level_dirs=source_hygiene.GIT_MIRROR_RUNTIME_TOP_LEVEL_DIRS,
            cache_parts=source_hygiene.GIT_MIRROR_CACHE_PARTS,
            live_env_names=source_hygiene.GIT_MIRROR_LIVE_ENV_NAMES,
            private_suffixes=source_hygiene.GIT_MIRROR_PRIVATE_SUFFIXES,
            rendered_suffixes=source_hygiene.GIT_MIRROR_RENDERED_SUFFIXES,
            database_suffixes=source_hygiene.GIT_MIRROR_DATABASE_SUFFIXES,
            heavy_suffixes=source_hygiene.GIT_MIRROR_HEAVY_SUFFIXES,
            fixture_prefixes=source_hygiene.GIT_MIRROR_FIXTURE_PREFIXES,
        )

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
                    self.tracked_hygiene_issue(relative_path)
                )

    def test_git_mirror_hygiene_allows_public_docs_examples_and_fixtures(self) -> None:
        allowed_paths = (
            "env/stack.env.example",
            "mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md",
            "mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json.example",
            "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-usage-snapshot.schema.json",
            "mechanics/runtime-lifecycle/parts/status-readouts/examples/runtime_usage_snapshot.workhorse-local.example.json",
            "tests/fixtures/latest.private.json",
            "mechanics/machine-fit/parts/machine-bridge/examples/machine-bridge.public.json.example",
            "config-templates/Services/tos-graph/app/models.py",
        )

        for relative_path in allowed_paths:
            with self.subTest(relative_path=relative_path):
                self.assertIsNone(
                    self.tracked_hygiene_issue(relative_path)
                )

    def test_current_repo_runtime_hygiene_contracts_pass(self) -> None:
        errors: list[str] = []
        runtime_hygiene.validate_runtime_hygiene_contracts(errors, root=REPO_ROOT)
        self.assertEqual(errors, [])

    def test_missing_gateway_policy_doc_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            (
                repo_root
                / "mechanics"
                / "runtime-lifecycle"
                / "parts"
                / "status-readouts"
                / "docs"
                / "GATEWAY_CACHE_POLICY.md"
            ).unlink()
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("mechanics/runtime-lifecycle/parts/status-readouts/docs/GATEWAY_CACHE_POLICY.md" in error for error in errors))

    def test_gateway_schema_surface_type_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json",
                (repo_root / RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json")
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
                repo_root / RUNTIME_LIFECYCLE_SCHEMA_ROOT / "runtime-gateway-cache-status.schema.json",
                "[]\n",
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any(
                "mechanics/runtime-lifecycle/parts/status-readouts/schemas/runtime-gateway-cache-status.schema.json must contain a top-level JSON object"
                == error
                for error in errors
            )
        )

    def test_cache_example_requires_inflight_replay_and_no_cache_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            write_text(
                repo_root / RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_gateway_cache_status.gateway-local.example.json",
                (repo_root / RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_gateway_cache_status.gateway-local.example.json")
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
                repo_root / RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_usage_snapshot.workhorse-local.example.json",
                (repo_root / RUNTIME_LIFECYCLE_EXAMPLE_ROOT / "runtime_usage_snapshot.workhorse-local.example.json")
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
                repo_root
                / "mechanics"
                / "diagnostic-spine"
                / "parts"
                / "doctor-readiness"
                / "docs"
                / "DOCTOR.md",
                (
                    repo_root
                    / "mechanics"
                    / "diagnostic-spine"
                    / "parts"
                    / "doctor-readiness"
                    / "docs"
                    / "DOCTOR.md"
                )
                .read_text(encoding="utf-8")
                .replace("mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md", "docs/LOCAL_OPS_SPLIT.md"),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md must mention `mechanics/diagnostic-spine/parts/doctor-readiness/docs/LOCAL_OPS_DOCTOR_SPLIT.md`" == error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
