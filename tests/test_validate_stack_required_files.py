from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.validate_stack as validate_stack


class ValidateStackRequiredFilesTests(unittest.TestCase):
    def test_current_repo_required_files_pass(self) -> None:
        errors: list[str] = []
        validate_stack.validate_required_files(errors)
        self.assertEqual(errors, [])

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
            doc.write_text(f"Bad link: {host_local_root}/docs/PATHS.md\n", encoding="utf-8")

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

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root):
                with patch.object(validate_stack, "REQUIRED_SCRIPTS", {"aoa-check-layout", "aoa-llamacpp-pilot"}):
                    with patch.object(
                        validate_stack,
                        "OPERATOR_BACKEND_SCRIPTS",
                        {"aoa-check-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh"},
                    ):
                        validate_stack.validate_scripts(errors)

        self.assertIn(
            "missing operator backend for scripts/aoa-check-layout: "
            "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
            errors,
        )

    def test_operator_wrapper_must_point_to_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir) / "abyss-stack"
            scripts_dir = repo_root / "scripts"
            backend = repo_root / "mechanics" / "runtime-lifecycle" / "parts" / "layout-install" / "aoa_check_layout.sh"
            backend.parent.mkdir(parents=True)
            scripts_dir.mkdir(parents=True)
            backend.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
            backend.chmod(0o755)
            (scripts_dir / "aoa-check-layout").write_text(
                "#!/usr/bin/env bash\nexec ../wrong/path.sh \"$@\"\n",
                encoding="utf-8",
            )
            (scripts_dir / "aoa-llamacpp-pilot").write_text(
                'podman", "network", "connect"\nabyss_default\n',
                encoding="utf-8",
            )

            errors: list[str] = []
            with patch.object(validate_stack, "ROOT", repo_root):
                with patch.object(validate_stack, "REQUIRED_SCRIPTS", {"aoa-check-layout", "aoa-llamacpp-pilot"}):
                    with patch.object(
                        validate_stack,
                        "OPERATOR_BACKEND_SCRIPTS",
                        {"aoa-check-layout": "mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh"},
                    ):
                        validate_stack.validate_scripts(errors)

        self.assertIn(
            "scripts/aoa-check-layout must exec "
            "../mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh",
            errors,
        )
