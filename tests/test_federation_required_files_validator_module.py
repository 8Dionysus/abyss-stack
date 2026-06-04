from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path

from scripts.validators import federation_surface


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_structured_object(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must parse as an object")
    return payload


class FederationRequiredFilesValidatorTests(unittest.TestCase):
    def validate_surface(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        federation_surface.validate_federation_required_files(
            errors,
            root=repo_root,
            required_runtime_inputs=federation_surface.FEDERATION_REQUIRED_RUNTIME_INPUTS,
            bridge_path=repo_root / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
            load_structured_object_func=load_structured_object,
        )
        return errors

    def write_valid_surface(self, repo_root: Path) -> None:
        for relative_path in federation_surface.FEDERATION_REQUIRED_RUNTIME_INPUTS:
            source_path = REPO_ROOT / relative_path
            write_text(repo_root / relative_path, source_path.read_text(encoding="utf-8"))
        write_text(
            repo_root / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
            (REPO_ROOT / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH).read_text(
                encoding="utf-8"
            ),
        )

    def test_current_repo_federation_required_files_pass(self) -> None:
        errors: list[str] = []
        federation_surface.validate_federation_required_files(
            errors,
            root=REPO_ROOT,
            required_runtime_inputs=federation_surface.FEDERATION_REQUIRED_RUNTIME_INPUTS,
            bridge_path=REPO_ROOT / federation_surface.UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
            load_structured_object_func=load_structured_object,
        )
        self.assertEqual(errors, [])

    def test_missing_runtime_template_index_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            aoa_evals_path = (
                repo_root / "config-templates" / "Configs" / "federation" / "aoa-evals.yaml"
            )
            write_text(
                aoa_evals_path,
                aoa_evals_path
                .read_text(encoding="utf-8")
                .replace("  - generated/runtime_candidate_template_index.min.json\n", ""),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(
            any("generated/runtime_candidate_template_index.min.json" in error for error in errors)
        )

    def test_missing_playbook_runtime_surface_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            aoa_playbooks_path = (
                repo_root / "config-templates" / "Configs" / "federation" / "aoa-playbooks.yaml"
            )
            write_text(
                aoa_playbooks_path,
                aoa_playbooks_path
                .read_text(encoding="utf-8")
                .replace("  - generated/playbook_registry.min.json\n", ""),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("generated/playbook_registry.min.json" in error for error in errors))

    def test_missing_kag_runtime_surface_contract_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            self.write_valid_surface(repo_root)
            aoa_kag_path = (
                repo_root / "config-templates" / "Configs" / "federation" / "aoa-kag.yaml"
            )
            write_text(
                aoa_kag_path,
                aoa_kag_path
                .read_text(encoding="utf-8")
                .replace("  - generated/reasoning_handoff_pack.min.json\n", ""),
            )
            errors = self.validate_surface(repo_root)

        self.assertTrue(any("generated/reasoning_handoff_pack.min.json" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
