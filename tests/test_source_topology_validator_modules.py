from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validators import agent_skill_projection
from scripts.validators import script_surface
from scripts.validators import source_hygiene
from scripts.validators import source_structure

REPO_ROOT = Path(__file__).resolve().parents[1]
VALID_LOCAL_OVERLAY_SKILL = """---
name: abyss-self-diagnostic-spine
description: Diagnose a concrete abyss runtime target through the repo-local read-only overlay.
metadata:
  aoa_canonical_skill_repo: 8Dionysus/aoa-skills
  aoa_canonical_skill_path: skills/project/abyss/abyss-self-diagnostic-spine/SKILL.md
---

# Overlay
"""


class SourceTopologyValidatorModulesTests(unittest.TestCase):
    def iter_text_files(self, repo_root: Path) -> list[Path]:
        return source_hygiene.iter_text_files(
            repo_root,
            binary_suffixes=source_hygiene.BINARY_SUFFIXES,
        )

    def write_operator_backend_fixture(
        self,
        repo_root: Path,
        *,
        executable: bool,
    ) -> tuple[Path, str]:
        scripts_dir = repo_root / "scripts"
        backend_rel = "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh"
        backend = repo_root / backend_rel
        backend.parent.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        backend.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        backend.chmod(0o755 if executable else 0o644)
        (scripts_dir / "aoa-check-layout").write_text(
            f"#!/usr/bin/env bash\nexec ../{backend_rel} \"$@\"\n",
            encoding="utf-8",
        )
        (scripts_dir / "aoa-llamacpp-pilot").write_text(
            'podman", "network", "connect"\nabyss_default\n',
            encoding="utf-8",
        )
        return backend, backend_rel

    def validate_operator_backend_fixture(
        self,
        repo_root: Path,
        backend_rel: str,
        errors: list[str],
        git_index_mode_func: script_surface.GitIndexMode | None = None,
    ) -> None:
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        pilot_backend_rel = "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py"
        pilot_backend = repo_root / pilot_backend_rel
        pilot_backend.parent.mkdir(parents=True, exist_ok=True)
        pilot_backend.write_text(
            'podman", "network", "connect"\nabyss_default\n',
            encoding="utf-8",
        )
        pilot_backend.chmod(0o755)
        (scripts_dir / "aoa-llamacpp-pilot").write_text(
            f"#!/usr/bin/env python3\n# ../{pilot_backend_rel}\n",
            encoding="utf-8",
        )
        (scripts_dir / "aoa-llamacpp-pilot").chmod(0o755)
        required_scripts = {"aoa-check-layout", "aoa-llamacpp-pilot"}
        backend_scripts = {
            "aoa-check-layout": backend_rel,
            "aoa-llamacpp-pilot": pilot_backend_rel,
        }
        script_surface.validate_scripts(
            errors,
            root=repo_root,
            required_scripts=required_scripts,
            operator_backend_scripts=backend_scripts,
            executable_source_path_func=lambda candidate: script_surface.is_executable_source_path(
                candidate,
                repo_root,
                git_index_mode_func=git_index_mode_func,
            ),
        )

    def test_current_repo_required_files_pass(self) -> None:
        errors: list[str] = []
        source_structure.validate_required_files(
            errors,
            root=REPO_ROOT,
            required_files=source_structure.required_files(REPO_ROOT),
        )
        self.assertEqual(errors, [])

    def test_repo_self_indexes_are_outside_authored_text_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            indexes = repo_root / "kag" / "indexes"
            indexes.mkdir(parents=True)
            source_index = indexes / "source_surface_index.json"
            repository_index = indexes / "repo_event_index.json"
            owner_index = indexes / "provider_readiness_index.json"
            authored_doc = repo_root / "docs" / "ROUTE.md"
            authored_doc.parent.mkdir(parents=True)
            source_index.write_text(
                '{"schema_version":"aoa-repo-local-kag-index-v2"}\n',
                encoding="utf-8",
            )
            repository_index.write_text(
                '{"schema_version":"aoa-repo-local-kag-repository-index-v2"}\n',
                encoding="utf-8",
            )
            owner_index.write_text(
                '{"schema_version":"aoa-local-kag-record-v1"}\n',
                encoding="utf-8",
            )
            authored_doc.write_text("Current route\n", encoding="utf-8")

            paths = self.iter_text_files(repo_root)

        self.assertNotIn(source_index, paths)
        self.assertNotIn(repository_index, paths)
        self.assertIn(owner_index, paths)
        self.assertIn(authored_doc, paths)

    def test_required_operator_scripts_have_backend_routes(self) -> None:
        self.assertEqual(
            script_surface.REQUIRED_SCRIPTS,
            set(script_surface.OPERATOR_BACKEND_SCRIPTS),
        )

    def test_missing_aoa_browser_template_files_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            existing = repo_root / "config-templates" / "Services" / "aoa-browser" / "Dockerfile"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("FROM scratch\n", encoding="utf-8")
            missing = repo_root / "config-templates" / "Services" / "aoa-browser" / "app.py"

            required_files = {existing, missing}
            errors: list[str] = []
            source_structure.validate_required_files(
                errors,
                root=repo_root,
                required_files=required_files,
            )

        self.assertEqual(
            errors,
            ["missing required file: config-templates/Services/aoa-browser/app.py"],
        )

    def test_host_local_source_checkout_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            doc = repo_root / "docs" / "MODEL_CARD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            host_local_root = "/home/dionysus/src/" + "abyss-stack"
            other_user_root = "/home/alice/src/" + "abyss-stack"
            doc.write_text(
                "\n".join(
                    [
                        f"Bad link: {host_local_root}/docs/runtime/PATHS.md",
                        f"Another bad link: {other_user_root}/docs/runtime/PATHS.md",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            errors: list[str] = []
            source_hygiene.validate_no_host_local_source_checkout_paths(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                host_local_source_checkout_patterns=source_hygiene.HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS,
                skip_paths=(),
            )

        self.assertEqual(
            errors,
            [
                "host-local source checkout path found in "
                f"docs/MODEL_CARD.md: {host_local_root}",
                "host-local source checkout path found in "
                f"docs/MODEL_CARD.md: {other_user_root}",
            ],
        )

    def test_host_local_source_checkout_path_allows_prefix_sibling_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            doc = repo_root / "docs" / "MODEL_CARD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text(
                "Allowed sibling: /home/alice/src/abyss-stack-docs/README.md\n",
                encoding="utf-8",
            )

            errors: list[str] = []
            source_hygiene.validate_no_host_local_source_checkout_paths(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                host_local_source_checkout_patterns=source_hygiene.HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS,
                skip_paths=(),
            )

        self.assertEqual(errors, [])

    def test_host_local_source_checkout_path_matches_sentence_punctuation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            doc = repo_root / "docs" / "MODEL_CARD.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            dotted_root = "/home/alice/src/" + "abyss-stack"
            parenthesized_root = "/home/bob/src/" + "abyss-stack"
            doc.write_text(
                "\n".join(
                    [
                        f"Bad sentence path: {dotted_root}.",
                        f"Bad parenthesized path: ({parenthesized_root})",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            errors: list[str] = []
            source_hygiene.validate_no_host_local_source_checkout_paths(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                host_local_source_checkout_patterns=source_hygiene.HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS,
                skip_paths=(),
            )

        self.assertEqual(
            errors,
            [
                "host-local source checkout path found in "
                f"docs/MODEL_CARD.md: {dotted_root}",
                "host-local source checkout path found in "
                f"docs/MODEL_CARD.md: {parenthesized_root}",
            ],
        )

    def test_moved_mechanic_doc_ref_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            doc = repo_root / ".agents" / "skills" / "overlay.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            moved_ref = "mechanics/diagnostic-spine/docs/" + "DIAGNOSTIC_SPINE.md"
            doc.write_text(f"Old ref: {moved_ref}\n", encoding="utf-8")

            errors: list[str] = []
            source_hygiene.validate_no_moved_mechanic_doc_refs(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                moved_mechanic_doc_refs=source_hygiene.MOVED_MECHANIC_DOC_REFS,
                skip_paths=(),
            )

        self.assertEqual(
            errors,
            [
                "moved mechanic doc ref found in "
                f".agents/skills/overlay.md: {moved_ref}"
            ],
        )

    def test_moved_mechanic_doc_ref_owner_manifest_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            owner_manifest = repo_root / source_hygiene.SOURCE_HYGIENE_VALIDATOR_PATH
            owner_manifest.parent.mkdir(parents=True, exist_ok=True)
            moved_ref = source_hygiene.MOVED_MECHANIC_DOC_REFS[0]
            owner_manifest.write_text(f'"{moved_ref}",\n', encoding="utf-8")

            errors: list[str] = []
            source_hygiene.validate_no_moved_mechanic_doc_refs(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                moved_mechanic_doc_refs=source_hygiene.MOVED_MECHANIC_DOC_REFS,
                skip_paths=(owner_manifest,),
            )

        self.assertEqual(errors, [])

    def test_stale_active_sibling_root_fails_outside_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            active_doc = repo_root / "docs" / "ROUTE.md"
            legacy_doc = repo_root / "mechanics" / "inference-pilots" / "legacy" / "raw" / "ROUTE.md"
            stale_root = "/srv/" + "aoa-routing"
            active_doc.parent.mkdir(parents=True, exist_ok=True)
            legacy_doc.parent.mkdir(parents=True, exist_ok=True)
            active_doc.write_text(f"Old active route: {stale_root}\n", encoding="utf-8")
            legacy_doc.write_text(f"Preserved lineage route: {stale_root}\n", encoding="utf-8")

            errors: list[str] = []
            source_hygiene.validate_no_stale_active_sibling_roots(
                errors,
                root=repo_root,
                text_file_iter_func=lambda: self.iter_text_files(repo_root),
                stale_active_sibling_root_pattern=source_hygiene.STALE_ACTIVE_SIBLING_ROOT_PATTERN,
            )

        self.assertEqual(
            errors,
            [
                "stale active sibling root found in "
                f"docs/ROUTE.md: {stale_root}"
            ],
        )

    def test_skill_projection_symlink_target_must_use_abyssos_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            skill_root = repo_root / ".agents" / "skills"
            skill_root.mkdir(parents=True)
            (skill_root / "AGENTS.md").write_text("# Skill surface\n", encoding="utf-8")
            overlay = skill_root / "abyss-self-diagnostic-spine"
            overlay.mkdir()
            (overlay / "SKILL.md").write_text(VALID_LOCAL_OVERLAY_SKILL, encoding="utf-8")
            (skill_root / "aoa-change-protocol").symlink_to(
                "/srv/AbyssOS/aoa-skills/.agents/skills/aoa-change-protocol"
            )
            (skill_root / "aoa-source-of-truth-check").symlink_to(
                "/srv/" + "aoa-skills/.agents/skills/aoa-source-of-truth-check"
            )

            errors: list[str] = []
            agent_skill_projection.validate_agent_skill_projection_routes(
                errors,
                root=repo_root,
            )

        self.assertEqual(
            errors,
            [
                ".agents/skills/aoa-source-of-truth-check must target "
                "/srv/AbyssOS/aoa-skills/.agents/skills/aoa-source-of-truth-check, "
                "got " + "/srv/" + "aoa-skills/.agents/skills/aoa-source-of-truth-check"
            ],
        )

    def test_skill_projection_accepts_checkout_safe_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            skill_root = repo_root / ".agents" / "skills"
            skill_root.mkdir(parents=True)
            (skill_root / "AGENTS.md").write_text("# Skill surface\n", encoding="utf-8")
            overlay = skill_root / "abyss-self-diagnostic-spine"
            overlay.mkdir()
            (overlay / "SKILL.md").write_text(VALID_LOCAL_OVERLAY_SKILL, encoding="utf-8")
            expected_target = "/srv/AbyssOS/aoa-skills/.agents/skills/aoa-change-protocol"
            (skill_root / "aoa-change-protocol").write_text(expected_target + "\n", encoding="utf-8")

            errors: list[str] = []
            agent_skill_projection.validate_agent_skill_projection_routes(
                errors,
                root=repo_root,
            )

        self.assertEqual(errors, [])

    def test_missing_operator_backend_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            scripts_dir = repo_root / "scripts"
            scripts_dir.mkdir(parents=True)
            wrapper = scripts_dir / "aoa-check-layout"
            wrapper.write_text(
                "#!/usr/bin/env bash\nexec \"${BASH_SOURCE[0]}\" \"$@\"\n",
                encoding="utf-8",
            )
            pilot = scripts_dir / "aoa-llamacpp-pilot"
            pilot.write_text('podman", "network", "connect"\nabyss_default\n', encoding="utf-8")
            backend_rel = "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh"

            errors: list[str] = []
            self.validate_operator_backend_fixture(repo_root, backend_rel, errors)

        self.assertIn(
            "missing operator backend for scripts/aoa-check-layout: "
            "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
            errors,
        )

    def test_operator_backend_accepts_git_index_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            backend, backend_rel = self.write_operator_backend_fixture(
                repo_root,
                executable=False,
            )

            errors: list[str] = []
            git_index_mode_calls: list[Path] = []

            def git_index_mode(path: Path) -> str:
                git_index_mode_calls.append(path)
                return "100755"

            self.validate_operator_backend_fixture(
                repo_root,
                backend_rel,
                errors,
                git_index_mode_func=git_index_mode,
            )

        self.assertEqual(errors, [])
        self.assertEqual(git_index_mode_calls, [backend])

    def test_operator_backend_nonexecutable_index_mode_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            _, backend_rel = self.write_operator_backend_fixture(
                repo_root,
                executable=False,
            )

            errors: list[str] = []
            self.validate_operator_backend_fixture(
                repo_root,
                backend_rel,
                errors,
                git_index_mode_func=lambda _path: "100644",
            )

        self.assertIn(
            "operator backend is not executable: "
            "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
            errors,
        )

    def test_powershell_operator_backend_does_not_require_posix_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            scripts_dir = repo_root / "scripts"
            backend_rel = "mechanics/machine-fit/parts/windows-bridge/aoa_doctor_win.ps1"
            backend = repo_root / backend_rel
            backend.parent.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)
            backend.write_text("Write-Host 'ok'\n", encoding="utf-8")
            backend.chmod(0o644)
            (scripts_dir / "aoa-doctor-win.ps1").write_text(
                f"$Backend = Join-Path $PSScriptRoot \"../{backend_rel}\"\n",
                encoding="utf-8",
            )
            pilot_backend_rel = "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py"
            pilot_backend = repo_root / pilot_backend_rel
            pilot_backend.parent.mkdir(parents=True)
            pilot_backend.write_text(
                'podman", "network", "connect"\nabyss_default\n',
                encoding="utf-8",
            )
            pilot_backend.chmod(0o755)
            (scripts_dir / "aoa-llamacpp-pilot").write_text(
                f"#!/usr/bin/env python3\n# ../{pilot_backend_rel}\n",
                encoding="utf-8",
            )
            (scripts_dir / "aoa-llamacpp-pilot").chmod(0o755)

            errors: list[str] = []
            script_surface.validate_scripts(
                errors,
                root=repo_root,
                required_scripts={"aoa-doctor-win.ps1", "aoa-llamacpp-pilot"},
                operator_backend_scripts={
                    "aoa-doctor-win.ps1": backend_rel,
                    "aoa-llamacpp-pilot": pilot_backend_rel,
                },
                executable_source_path_func=lambda candidate: script_surface.is_executable_source_path(
                    candidate,
                    repo_root,
                ),
            )

        self.assertEqual(errors, [])

    def test_operator_wrapper_must_point_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            _, backend_rel = self.write_operator_backend_fixture(
                repo_root,
                executable=True,
            )
            scripts_dir = repo_root / "scripts"
            (scripts_dir / "aoa-check-layout").write_text(
                "#!/usr/bin/env bash\nexec ../wrong/path.sh \"$@\"\n",
                encoding="utf-8",
            )

            errors: list[str] = []
            self.validate_operator_backend_fixture(repo_root, backend_rel, errors)

        self.assertIn(
            "scripts/aoa-check-layout must exec "
            "../mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
            errors,
        )
