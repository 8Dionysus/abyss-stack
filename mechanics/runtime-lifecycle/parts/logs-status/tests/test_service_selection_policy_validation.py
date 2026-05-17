from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


REPO_ROOT = Path(__file__).resolve().parents[5]
POLICY_PATH = Path("docs") / "runtime" / "service-selection-policy.v1.json"
INVENTORY_PATH = Path("docs") / "runtime" / "service-inventory-2026-05-14.v1.json"


def write_text(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ServiceSelectionPolicyValidationTests(unittest.TestCase):
    def build_policy_fixture(self, repo_root: Path) -> Path:
        policy = json.loads((REPO_ROOT / POLICY_PATH).read_text(encoding="utf-8"))
        write_text(repo_root / POLICY_PATH, json.dumps(policy, indent=2) + "\n")
        write_text(
            repo_root / "docs" / "runtime" / "SERVICE_SELECTION.md",
            "service-selection-policy.v1.json\nservice-inventory-2026-05-14.v1.json\n",
        )
        write_text(
            repo_root / "docs" / "runtime" / "README.md",
            "service-selection-policy.v1.json\nservice-inventory-2026-05-14.v1.json\n",
        )
        for overlay in policy["current_runtime_shape"]["overlays"]:
            write_text(repo_root / overlay)
        for entry in policy["services"]:
            write_text(repo_root / entry["module"])
            if entry["resource_guard"]:
                write_text(repo_root / entry["resource_guard"])
        return repo_root / POLICY_PATH

    def build_inventory_fixture(self, repo_root: Path) -> Path:
        self.build_policy_fixture(repo_root)
        inventory = json.loads((REPO_ROOT / INVENTORY_PATH).read_text(encoding="utf-8"))
        write_text(repo_root / INVENTORY_PATH, json.dumps(inventory, indent=2) + "\n")
        return repo_root / INVENTORY_PATH

    def validate_fixture(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_service_selection_policy(errors)
        return errors

    def validate_inventory_fixture(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        with patch.object(validate_stack, "ROOT", repo_root):
            validate_stack.validate_service_screenshot_inventory(errors)
        return errors

    def test_current_policy_contract_passes(self) -> None:
        errors: list[str] = []
        validate_stack.validate_service_selection_policy(errors)
        self.assertEqual(errors, [])

    def test_missing_required_service_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            policy_path = self.build_policy_fixture(repo_root)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["services"] = [
                entry for entry in policy["services"] if entry["name"] != "n8n"
            ]
            write_text(policy_path, json.dumps(policy, indent=2) + "\n")

            errors = self.validate_fixture(repo_root)

        self.assertTrue(any("missing required services: n8n" in error for error in errors))

    def test_opt_in_service_cannot_be_selected_now(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            policy_path = self.build_policy_fixture(repo_root)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            for entry in policy["services"]:
                if entry["name"] == "n8n":
                    entry["posture"] = "selected_now"
            write_text(policy_path, json.dumps(policy, indent=2) + "\n")

            errors = self.validate_fixture(repo_root)

        self.assertTrue(any("must not mark n8n as selected_now" in error for error in errors))

    def test_runtime_shape_services_must_match_selected_now(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            policy_path = self.build_policy_fixture(repo_root)
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            for entry in policy["services"]:
                if entry["name"] == "rerank-api":
                    entry["posture"] = "explicit_opt_in"
            write_text(policy_path, json.dumps(policy, indent=2) + "\n")

            errors = self.validate_fixture(repo_root)

        self.assertTrue(
            any("current runtime shape services must be marked selected_now: rerank-api" in error for error in errors)
        )

    def test_current_screenshot_inventory_contract_passes(self) -> None:
        errors: list[str] = []
        validate_stack.validate_service_screenshot_inventory(errors)
        self.assertEqual(errors, [])

    def test_screenshot_inventory_requires_baseline_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            inventory_path = self.build_inventory_fixture(repo_root)
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["screenshotted_services"] = [
                service for service in inventory["screenshotted_services"] if service != "ovms"
            ]
            for group in inventory["screenshotted_groups"]:
                group["services"] = [
                    service for service in group["services"] if service != "ovms"
                ]
            write_text(inventory_path, json.dumps(inventory, indent=2) + "\n")

            errors = self.validate_inventory_fixture(repo_root)

        self.assertTrue(any("missing screenshot services: ovms" in error for error in errors))

    def test_screenshot_inventory_explains_selected_addons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            inventory_path = self.build_inventory_fixture(repo_root)
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            inventory["current_selected_addons"] = []
            write_text(inventory_path, json.dumps(inventory, indent=2) + "\n")

            errors = self.validate_inventory_fixture(repo_root)

        self.assertTrue(any("current_selected_addons must contain rerank-api and rag-api" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
