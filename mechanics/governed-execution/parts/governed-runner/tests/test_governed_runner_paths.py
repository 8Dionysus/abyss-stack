from unittest.mock import patch

from governed_runner_test_support import (
    REPO_ROOT,
    GovernedRunnerTestCase,
    init_minimal_repo,
    make_policy,
    write_json,
)


class GovernedRunnerPathTests(GovernedRunnerTestCase):
    def test_current_checkout_uses_canonical_deployment_marker(self) -> None:
        self.assertTrue(self.module.is_abyss_stack_checkout(REPO_ROOT))

    def test_stale_deployment_marker_does_not_identify_a_checkout(self) -> None:
        stale_root = self.root / "stale-marker"
        (stale_root / "docs").mkdir(parents=True)
        (stale_root / "scripts").mkdir()
        (stale_root / "CONTRIBUTING.md").write_text(
            "contrib\n",
            encoding="utf-8",
        )
        (stale_root / "scripts" / "validate_stack.py").write_text(
            "print('ok')\n",
            encoding="utf-8",
        )
        (stale_root / "docs" / "DEPLOYMENT.md").write_text(
            "stale\n",
            encoding="utf-8",
        )

        self.assertFalse(self.module.is_abyss_stack_checkout(stale_root))

    def test_resolve_default_repo_root_expands_portable_home_default(self) -> None:
        portable_home = self.root / "portable-home"
        portable_repo_root = portable_home / "src" / "abyss-stack"
        init_minimal_repo(portable_repo_root)

        policy = make_policy()
        policy["targets"]["abyss-stack"]["default_repo_root"] = "~/src/abyss-stack"

        with patch.dict("os.environ", {"HOME": str(portable_home)}, clear=False):
            resolved = self.module.resolve_default_repo_root("abyss-stack", policy=policy)

        self.assertEqual(resolved, portable_repo_root.resolve())
