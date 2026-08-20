from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.validators import service_selection


REPO_ROOT = Path(__file__).resolve().parents[5]
POLICY_PATH = Path("docs") / "runtime" / "service-selection-policy.v1.json"
INVENTORY_PATH = Path("docs") / "runtime" / "service-inventory-2026-05-14.v1.json"


def write_text(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_names(file_path: Path) -> list[str]:
    names: list[str] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.append(line)
    return names


def compose_service_names(file_path: Path) -> set[str]:
    service_names: set[str] = set()
    in_runtime_workloads = False
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        if raw.strip() in {"services:", "x-abyss-owner-workloads:"}:
            in_runtime_workloads = True
            continue
        if not in_runtime_workloads:
            continue
        if raw and not raw.startswith(" "):
            in_runtime_workloads = False
            continue
        match = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", raw)
        if match:
            service_names.add(match.group(1))
    return service_names


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
        for source_dir in (REPO_ROOT / "compose" / "presets", REPO_ROOT / "compose" / "profiles"):
            for source_path in source_dir.glob("*.txt"):
                write_text(
                    repo_root / source_path.relative_to(REPO_ROOT),
                    source_path.read_text(encoding="utf-8"),
                )
        for entry in policy["services"]:
            write_text(
                repo_root / entry["module"],
                (REPO_ROOT / entry["module"]).read_text(encoding="utf-8"),
            )
            if entry["resource_guard"]:
                resource_guard = REPO_ROOT / entry["resource_guard"]
                write_text(
                    repo_root / entry["resource_guard"],
                    resource_guard.read_text(encoding="utf-8") if resource_guard.is_file() else "",
                )
        return repo_root / POLICY_PATH

    def build_inventory_fixture(self, repo_root: Path) -> Path:
        self.build_policy_fixture(repo_root)
        inventory = json.loads((REPO_ROOT / INVENTORY_PATH).read_text(encoding="utf-8"))
        write_text(repo_root / INVENTORY_PATH, json.dumps(inventory, indent=2) + "\n")
        return repo_root / INVENTORY_PATH

    def validate_fixture(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        service_selection.validate_service_selection_policy(
            errors,
            root=repo_root,
            policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
            required_services=service_selection.SERVICE_SELECTION_POLICY_REQUIRED_SERVICES,
            allowed_postures=service_selection.SERVICE_SELECTION_POLICY_ALLOWED_POSTURES,
            preset_dir=repo_root / "compose" / "presets",
            profile_dir=repo_root / "compose" / "profiles",
            module_dir=repo_root / "compose" / "modules",
            load_names_func=load_names,
            compose_service_names_func=compose_service_names,
            required_runtime_profiles={"federation", "reranking", "rag"},
            required_runtime_overlays=(
                "compose/tuning/storage.intel-285h.resource-guard.yml",
                "compose/tuning/rag.thin-host.yml",
            ),
            unexpected_selected_services={"n8n", "n8n-task-runners", "ollama", "litellm", "babelvox-tts"},
            expected_selected_services={
                "postgres",
                "redis",
                "qdrant",
                "neo4j",
                "llama-cpp",
                "ovms",
                "langchain-api",
                "route-api",
                "rerank-api",
                "rag-api",
            },
            selection_doc_paths=(
                Path("docs") / "runtime" / "SERVICE_SELECTION.md",
                Path("docs") / "runtime" / "README.md",
            ),
        )
        return errors

    def validate_inventory_fixture(self, repo_root: Path) -> list[str]:
        errors: list[str] = []
        service_selection.validate_service_screenshot_inventory(
            errors,
            root=repo_root,
            inventory_path=service_selection.SERVICE_SCREENSHOT_INVENTORY_PATH,
            policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
            required_screenshot_services=service_selection.SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES,
            expected_addon_services=("rerank-api", "rag-api", "loki", "tempo", "alloy"),
            selection_doc_paths=(
                Path("docs") / "runtime" / "SERVICE_SELECTION.md",
                Path("docs") / "runtime" / "README.md",
            ),
        )
        return errors

    def test_current_policy_contract_passes(self) -> None:
        errors: list[str] = []
        service_selection.validate_service_selection_policy(
            errors,
            root=REPO_ROOT,
            policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
            required_services=service_selection.SERVICE_SELECTION_POLICY_REQUIRED_SERVICES,
            allowed_postures=service_selection.SERVICE_SELECTION_POLICY_ALLOWED_POSTURES,
            preset_dir=REPO_ROOT / "compose" / "presets",
            profile_dir=REPO_ROOT / "compose" / "profiles",
            module_dir=REPO_ROOT / "compose" / "modules",
            load_names_func=load_names,
            compose_service_names_func=compose_service_names,
            required_runtime_profiles={"federation", "reranking", "rag"},
            required_runtime_overlays=(
                "compose/tuning/storage.intel-285h.resource-guard.yml",
                "compose/tuning/rag.thin-host.yml",
            ),
            unexpected_selected_services={"n8n", "n8n-task-runners", "ollama", "litellm", "babelvox-tts"},
            expected_selected_services={
                "postgres",
                "redis",
                "qdrant",
                "neo4j",
                "llama-cpp",
                "ovms",
                "langchain-api",
                "route-api",
                "rerank-api",
                "rag-api",
            },
            selection_doc_paths=(
                Path("docs") / "runtime" / "SERVICE_SELECTION.md",
                Path("docs") / "runtime" / "README.md",
            ),
        )
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
        service_selection.validate_service_screenshot_inventory(
            errors,
            root=REPO_ROOT,
            inventory_path=service_selection.SERVICE_SCREENSHOT_INVENTORY_PATH,
            policy_path=service_selection.SERVICE_SELECTION_POLICY_PATH,
            required_screenshot_services=service_selection.SERVICE_SCREENSHOT_INVENTORY_REQUIRED_SERVICES,
            expected_addon_services=("rerank-api", "rag-api", "loki", "tempo", "alloy"),
            selection_doc_paths=(
                Path("docs") / "runtime" / "SERVICE_SELECTION.md",
                Path("docs") / "runtime" / "README.md",
            ),
        )
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
