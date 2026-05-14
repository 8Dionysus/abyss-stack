from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


class ValidateStackRequiredFilesTests(unittest.TestCase):
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
        with patch.object(validate_stack, "ROOT", repo_root):
            with patch.object(validate_stack, "REQUIRED_SCRIPTS", required_scripts):
                with patch.object(validate_stack, "OPERATOR_BACKEND_SCRIPTS", backend_scripts):
                    validate_stack.validate_scripts(errors)

    def test_current_repo_required_files_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_required_files(errors)
        self.assertEqual(errors, [])

    def test_required_operator_scripts_have_backend_routes(self) -> None:
        self.assertEqual(
            validate_stack.REQUIRED_SCRIPTS,
            set(validate_stack.OPERATOR_BACKEND_SCRIPTS),
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
            with patch.object(validate_stack, "ROOT", repo_root):
                with patch.object(validate_stack, "REQUIRED_FILES", required_files):
                    validate_stack.validate_required_files(errors)

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
            doc.write_text(f"Bad link: {host_local_root}/docs/runtime/PATHS.md\n", encoding="utf-8")

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root):
                validate_stack.validate_no_host_local_source_checkout_paths(errors)

        self.assertEqual(
            errors,
            [
                "host-local source checkout path found in "
                f"docs/MODEL_CARD.md: {host_local_root}"
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
            with patch.object(validate_stack, "ROOT", repo_root):
                validate_stack.validate_no_moved_mechanic_doc_refs(errors)

        self.assertEqual(
            errors,
            [
                "moved mechanic doc ref found in "
                f".agents/skills/overlay.md: {moved_ref}"
            ],
        )

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
            with patch.object(validate_stack, "ROOT", repo_root):
                validate_stack.validate_no_stale_active_sibling_roots(errors)

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
            (overlay / "SKILL.md").write_text("# Overlay\n", encoding="utf-8")
            (skill_root / "aoa-change-protocol").symlink_to(
                "/srv/AbyssOS/aoa-skills/.agents/skills/aoa-change-protocol"
            )
            (skill_root / "aoa-source-of-truth-check").symlink_to(
                "/srv/" + "aoa-skills/.agents/skills/aoa-source-of-truth-check"
            )

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root):
                validate_stack.validate_agent_skill_projection_routes(errors)

        self.assertEqual(
            errors,
            [
                ".agents/skills/aoa-source-of-truth-check must target "
                "/srv/AbyssOS/aoa-skills/.agents/skills/aoa-source-of-truth-check, "
                "got " + "/srv/" + "aoa-skills/.agents/skills/aoa-source-of-truth-check"
            ],
        )

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
            with patch.object(validate_stack, "git_index_mode", return_value="100755") as git_index_mode:
                self.validate_operator_backend_fixture(repo_root, backend_rel, errors)

        self.assertEqual(errors, [])
        git_index_mode.assert_called_once_with(backend)

    def test_operator_backend_nonexecutable_index_mode_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            _, backend_rel = self.write_operator_backend_fixture(
                repo_root,
                executable=False,
            )

            errors: list[str] = []
            with patch.object(validate_stack, "git_index_mode", return_value="100644"):
                self.validate_operator_backend_fixture(repo_root, backend_rel, errors)

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
            with patch.object(validate_stack, "ROOT", repo_root):
                with patch.object(validate_stack, "REQUIRED_SCRIPTS", {"aoa-doctor-win.ps1", "aoa-llamacpp-pilot"}):
                    with patch.object(
                        validate_stack,
                        "OPERATOR_BACKEND_SCRIPTS",
                        {
                            "aoa-doctor-win.ps1": backend_rel,
                            "aoa-llamacpp-pilot": pilot_backend_rel,
                        },
                    ):
                        validate_stack.validate_scripts(errors)

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
