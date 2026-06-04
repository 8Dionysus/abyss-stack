from __future__ import annotations

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TESTING_DIR = REPO_ROOT / "docs" / "testing"
INVENTORY_PATH = TESTING_DIR / "test_inventory.json"


def load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def tracked_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    files = set(result.stdout.splitlines())

    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    deleted = {
        line[3:]
        for line in status.stdout.splitlines()
        if len(line) > 3 and (line[0] == "D" or line[1] == "D")
    }
    return files - deleted


def inventory_paths() -> set[str]:
    paths: set[str] = set()
    for entry in load_inventory()["entries"]:
        paths.update(entry["paths"])
    return paths


def test_testing_docs_and_inventory_exist() -> None:
    for relative in ("AGENTS.md", "README.md", "TEST_TOPOLOGY.md", "test_inventory.json"):
        assert (TESTING_DIR / relative).is_file(), relative


def test_test_inventory_entries_have_required_fields_and_existing_paths() -> None:
    inventory = load_inventory()
    required = set(inventory["required_fields"])

    for entry in inventory["entries"]:
        assert required <= set(entry), entry
        assert entry["paths"], entry
        for relative in entry["paths"]:
            assert (REPO_ROOT / relative).exists(), relative


def test_tracked_tests_are_inventory_covered() -> None:
    test_paths = {
        path
        for path in tracked_files()
        if path.startswith("tests/test")
        or ("/tests/test" in path and path.endswith(".py"))
    }

    assert test_paths <= inventory_paths()


def test_legacy_tests_are_explicitly_labeled() -> None:
    inventory = load_inventory()
    legacy_entries = [
        entry
        for entry in inventory["entries"]
        if any("/legacy/" in path for path in entry["paths"])
    ]

    assert legacy_entries
    for entry in legacy_entries:
        assert entry["disposition"] == "legacy-provenance-active"
        assert "provenance" in entry["mode"]
        assert "default pytest" in entry["protects"]


def test_test_inventory_does_not_store_shell_commands() -> None:
    inventory_text = INVENTORY_PATH.read_text(encoding="utf-8")

    assert "python -m pytest" not in inventory_text
    assert "shellcheck" not in inventory_text
