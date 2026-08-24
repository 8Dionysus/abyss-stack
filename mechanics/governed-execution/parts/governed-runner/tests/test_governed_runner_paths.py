import shutil
import subprocess

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

    def test_forged_prefix_suffix_and_substring_markers_are_rejected(self) -> None:
        cases = (
            ("# abyss-stack-fork", "Root route card for `abyss-stack`."),
            ("# fork-abyss-stack", "Root route card for `abyss-stack`."),
            ("# abyss-stack", "Root route card for `abyss-stack-fork`."),
            ("# abyss-stack", "owner: abyss-stack"),
        )
        for index, (readme_title, agents_owner_line) in enumerate(cases):
            with self.subTest(case=index):
                foreign_root = self.root / f"foreign-{index}"
                (foreign_root / "docs" / "install").mkdir(parents=True)
                (foreign_root / "scripts").mkdir()
                (foreign_root / "mechanics").mkdir()
                (foreign_root / "README.md").write_text(readme_title + "\n", encoding="utf-8")
                (foreign_root / "AGENTS.md").write_text(agents_owner_line + "\n", encoding="utf-8")
                (foreign_root / "CONTRIBUTING.md").write_text("contrib\n", encoding="utf-8")
                (foreign_root / "scripts" / "validate_stack.py").write_text("# validator\n", encoding="utf-8")
                (foreign_root / "docs" / "install" / "DEPLOYMENT.md").write_text("deploy\n", encoding="utf-8")

                self.assertFalse(self.module.is_abyss_stack_checkout(foreign_root))

    def test_explicit_override_wins_and_invalid_override_does_not_fall_through(self) -> None:
        explicit_root = self.root / "explicit"
        script_root = self.root / "script"
        init_minimal_repo(explicit_root)
        init_minimal_repo(script_root)
        identity_path = self.root / "explicit-source-identity.json"
        write_json(
            identity_path,
            self.module.SOURCE_IDENTITY.make_source_identity(
                explicit_root,
                consumer="shared",
            ),
        )

        with patch.dict(
            "os.environ",
            {
                "AOA_SOURCE_ROOT": str(explicit_root),
                "AOA_SOURCE_IDENTITY": str(identity_path),
            },
            clear=False,
        ):
            with patch.object(self.module, "SCRIPT_ROOT", script_root):
                self.assertEqual(
                    self.module.resolve_default_repo_root("abyss-stack", policy=make_policy()),
                    explicit_root.resolve(),
                )

        invalid_root = self.root / "invalid"
        invalid_root.mkdir()
        with patch.dict("os.environ", {"AOA_SOURCE_ROOT": str(invalid_root)}, clear=False):
            with patch.object(self.module, "SCRIPT_ROOT", script_root):
                self.assertEqual(
                    self.module.candidate_repo_roots_for_target("abyss-stack", policy=make_policy()),
                    [invalid_root],
                )
                with self.assertRaisesRegex(RuntimeError, "source_root_unresolved"):
                    self.module.resolve_default_repo_root("abyss-stack", policy=make_policy())

    def test_source_local_root_is_the_only_implicit_candidate(self) -> None:
        script_root = self.root / "script"
        init_minimal_repo(script_root)

        with patch.dict("os.environ", {}, clear=True):
            with patch.object(self.module, "SCRIPT_ROOT", script_root):
                self.assertEqual(
                    self.module.resolve_default_repo_root("abyss-stack", policy=make_policy()),
                    script_root.resolve(),
                )

    def test_same_shape_foreign_checkout_requires_exact_identity_and_alias_is_allowed(self) -> None:
        foreign_root = self.root / "foreign"
        init_minimal_repo(foreign_root)
        (foreign_root / "docs" / "target.md").write_text("foreign\n", encoding="utf-8")
        subprocess.run(["git", "add", "docs/target.md"], cwd=foreign_root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-qm", "foreign"], cwd=foreign_root, check=True, capture_output=True, text=True)
        identity = self.module.SOURCE_IDENTITY.make_source_identity(
            foreign_root,
            consumer="governed-runner",
        )
        alias_root = self.root / "foreign-alias"
        alias_root.symlink_to(foreign_root, target_is_directory=True)

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(self.module.is_abyss_stack_checkout(foreign_root))
            with self.assertRaisesRegex(RuntimeError, "source root requires an explicit source identity contract"):
                self.module.normalize_repo_root(
                    foreign_root,
                    target_id="abyss-stack",
                )
            self.assertEqual(
                self.module.normalize_repo_root(
                    alias_root,
                    target_id="abyss-stack",
                    expected_identity=identity,
                ),
                foreign_root.resolve(),
            )

    def test_source_replacement_fails_revalidation_before_use(self) -> None:
        identity = self.module.SOURCE_IDENTITY.make_source_identity(
            self.repo_root,
            consumer="governed-runner",
        )
        binding = self.module.SOURCE_IDENTITY.bind_source_root(
            self.repo_root,
            consumer="governed-runner",
            expected_identity=identity,
        )
        replacement_root = self.root / "replacement"
        init_minimal_repo(replacement_root)
        shutil.rmtree(self.repo_root)
        replacement_root.rename(self.repo_root)
        with self.assertRaises(self.module.SOURCE_IDENTITY.SourceIdentityError):
            self.module.SOURCE_IDENTITY.revalidate_source_binding(binding)

    def test_home_default_stack_root_and_projection_are_not_source_candidates(self) -> None:
        portable_home = self.root / "portable-home"
        home_repo_root = portable_home / "src" / "abyss-stack"
        init_minimal_repo(home_repo_root)
        stack_root = self.root / "stack"
        configs_root = stack_root / "Configs"
        init_minimal_repo(configs_root)

        with patch.dict("os.environ", {"HOME": str(portable_home)}, clear=True):
            with patch.object(self.module, "SCRIPT_ROOT", self.root / "missing"):
                with patch.object(self.module, "STACK_ROOT", stack_root):
                    with patch.object(self.module, "CONFIGS_ROOT", configs_root):
                        self.assertEqual(
                            self.module.candidate_repo_roots_for_target("abyss-stack", policy=make_policy()),
                            [],
                        )
                        with self.assertRaisesRegex(RuntimeError, "source_root_unresolved"):
                            self.module.resolve_default_repo_root("abyss-stack", policy=make_policy())
                        self.assertFalse(self.module.is_abyss_stack_checkout(configs_root))
