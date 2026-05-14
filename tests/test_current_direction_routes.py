from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class CurrentDirectionRoutesTestCase(unittest.TestCase):
    def test_root_entrypoints_route_to_roadmap(self) -> None:
        roadmap_path = REPO_ROOT / "ROADMAP.md"
        design_path = REPO_ROOT / "DESIGN.md"
        design_agents_path = REPO_ROOT / "DESIGN.AGENTS.md"
        route_contract_path = REPO_ROOT / "docs" / "routes" / "START_HERE_ROUTE_CONTRACT.md"
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        docs_agents = (REPO_ROOT / "docs" / "AGENTS.md").read_text(encoding="utf-8")

        self.assertTrue(roadmap_path.is_file())
        self.assertTrue(design_path.is_file())
        self.assertTrue(design_agents_path.is_file())
        self.assertTrue(route_contract_path.is_file())
        self.assertIn("ROADMAP.md", readme)
        self.assertIn("ROADMAP.md", agents)
        self.assertIn("DESIGN.md", readme)
        self.assertIn("DESIGN.md", agents)
        self.assertIn("DESIGN.AGENTS.md", readme)
        self.assertIn("DESIGN.AGENTS.md", agents)
        self.assertIn("docs/routes/START_HERE_ROUTE_CONTRACT.md", readme)
        self.assertIn("docs/routes/START_HERE_ROUTE_CONTRACT.md", agents)
        self.assertIn("START_HERE_ROUTE_CONTRACT.md", docs_readme)
        self.assertIn("START_HERE_ROUTE_CONTRACT.md", docs_agents)

    def test_route_contract_defines_root_route_modes(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        route_contract = (
            REPO_ROOT / "docs" / "routes" / "START_HERE_ROUTE_CONTRACT.md"
        ).read_text(encoding="utf-8")

        for mode in (
            "first-reading",
            "runtime-design",
            "agent-guidance",
            "source-install",
            "runtime-operation",
            "mechanic-change",
            "machine-fit",
            "diagnostics-repair",
            "direction-change",
            "release-history",
            "decision-rationale",
        ):
            with self.subTest(mode=mode):
                self.assertIn(mode, readme)
                self.assertIn(mode, route_contract)

        self.assertIn("scripts/release_check.py", route_contract)
        self.assertIn("Root entry surfaces should point here", route_contract)

    def test_readme_validation_stays_front_door_shaped(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("scripts/release_check.py", readme)
        self.assertIn("scripts/README.md", readme)
        self.assertIn("tests/README.md", readme)
        self.assertNotIn("python scripts/validate_stack.py", readme)
        self.assertNotIn("python scripts/validate_nested_agents.py", readme)
        self.assertNotIn("python -m pytest -q", readme)
        self.assertNotIn("python scripts/build_diagnostic_surface_catalog.py --check", readme)
        self.assertNotIn("python scripts/validate_diagnostic_surface_catalog.py", readme)


if __name__ == "__main__":
    unittest.main()
