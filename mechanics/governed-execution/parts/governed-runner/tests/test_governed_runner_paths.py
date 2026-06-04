from unittest.mock import patch

from governed_runner_test_support import GovernedRunnerTestCase, init_minimal_repo, make_policy, write_json


class GovernedRunnerPathTests(GovernedRunnerTestCase):
    def test_resolve_default_repo_root_expands_portable_home_default(self) -> None:
        portable_home = self.root / "portable-home"
        portable_repo_root = portable_home / "src" / "abyss-stack"
        init_minimal_repo(portable_repo_root)

        policy = make_policy()
        policy["targets"]["abyss-stack"]["default_repo_root"] = "~/src/abyss-stack"

        with patch.dict("os.environ", {"HOME": str(portable_home)}, clear=False):
            resolved = self.module.resolve_default_repo_root("abyss-stack", policy=policy)

        self.assertEqual(resolved, portable_repo_root.resolve())
