from __future__ import annotations

import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def run_aoa_lib(script: str) -> str:
    completed = subprocess.run(
        ["bash", "-lc", script],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class AoaLibEnvCompatTests(unittest.TestCase):
    def test_resource_admission_dir_tracks_runtime_uid_and_allows_override(self) -> None:
        default = run_aoa_lib(
            "unset AOA_RESOURCE_ADMISSION_DIR; export AOA_RUNTIME_UID=4242; "
            "source scripts/aoa-lib.sh; printf '%s' \"$AOA_RESOURCE_ADMISSION_DIR\""
        )
        explicit = run_aoa_lib(
            "export AOA_RUNTIME_UID=4242; export AOA_RESOURCE_ADMISSION_DIR=/private/admission; "
            "source scripts/aoa-lib.sh; printf '%s' \"$AOA_RESOURCE_ADMISSION_DIR\""
        )

        self.assertEqual(default, "/run/user/4242/abyss-machine/resource")
        self.assertEqual(explicit, "/private/admission")

    def test_compat_no_op_offload_true_maps_to_op_offload_zero(self) -> None:
        output = run_aoa_lib(
            "unset AOA_LLAMACPP_OP_OFFLOAD; export AOA_LLAMACPP_NO_OP_OFFLOAD=1; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "0")

    def test_compat_no_op_offload_false_maps_to_op_offload_one(self) -> None:
        output = run_aoa_lib(
            "unset AOA_LLAMACPP_OP_OFFLOAD; export AOA_LLAMACPP_NO_OP_OFFLOAD=0; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "1")

    def test_explicit_op_offload_wins_over_legacy_bridge(self) -> None:
        output = run_aoa_lib(
            "export AOA_LLAMACPP_OP_OFFLOAD=7; export AOA_LLAMACPP_NO_OP_OFFLOAD=1; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "7")

    def test_missing_machine_fit_recommended_overlay_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            module = root / "Configs" / "compose" / "modules" / "41-agent-api.yml"
            module.parent.mkdir(parents=True)
            module.write_text("services:\n  langchain-api:\n    image: busybox\n", encoding="utf-8")
            machine_fit = root / "Logs" / "machine-fit" / "latest" / "latest.private.json"
            machine_fit.parent.mkdir(parents=True)
            machine_fit.write_text(
                json.dumps(
                    {
                        "runtime_recommendation": {
                            "recommended_overlays": ["compose/tuning/missing.yml"],
                        }
                    },
                    ensure_ascii=True,
                )
                + "\n",
                encoding="utf-8",
            )

            output = run_aoa_lib(
                "export AOA_MACHINE_FIT_AUTO_APPLY=true; "
                f"export AOA_MACHINE_FIT_PATH={shlex.quote(str(machine_fit))}; "
                f"export AOA_STACK_ROOT={shlex.quote(str(root))}; "
                f"export AOA_CONFIGS_ROOT={shlex.quote(str(root / 'Configs'))}; "
                "source scripts/aoa-lib.sh; "
                f"AOA_PROFILE_MODULE_FILES=({shlex.quote(str(module))}); "
                "aoa_apply_machine_fit_runtime_posture; "
                "printf '%s|%s' \"${AOA_EXTRA_COMPOSE_FILES:-}\" \"${AOA_MACHINE_FIT_SKIPPED_OVERLAY_SPECS[*]:-}\""
            )

        self.assertEqual(output, "|compose/tuning/missing.yml")

    def test_machine_fit_podman_root_overrides_computed_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            machine_fit = root / "Logs" / "machine-fit" / "latest" / "latest.private.json"
            machine_fit.parent.mkdir(parents=True)
            machine_fit.write_text(
                json.dumps(
                    {
                        "runtime_recommendation": {
                            "validated_settings": {
                                "AOA_PODMAN_CONTAINERS_ROOT": "/srv/podman-rootless/containers",
                            },
                        }
                    },
                    ensure_ascii=True,
                )
                + "\n",
                encoding="utf-8",
            )

            output = run_aoa_lib(
                "unset AOA_PODMAN_CONTAINERS_ROOT; "
                "export AOA_MACHINE_FIT_AUTO_APPLY=true; "
                f"export AOA_MACHINE_FIT_PATH={shlex.quote(str(machine_fit))}; "
                "source scripts/aoa-lib.sh; "
                "aoa_apply_machine_fit_runtime_posture; "
                'printf "%s" "$AOA_PODMAN_CONTAINERS_ROOT"'
            )

        self.assertEqual(output, "/srv/podman-rootless/containers")

    def test_explicit_podman_root_wins_over_machine_fit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            machine_fit = root / "Logs" / "machine-fit" / "latest" / "latest.private.json"
            machine_fit.parent.mkdir(parents=True)
            machine_fit.write_text(
                json.dumps(
                    {
                        "runtime_recommendation": {
                            "validated_settings": {
                                "AOA_PODMAN_CONTAINERS_ROOT": "/srv/podman-rootless/containers",
                            },
                        }
                    },
                    ensure_ascii=True,
                )
                + "\n",
                encoding="utf-8",
            )

            output = run_aoa_lib(
                "export AOA_PODMAN_CONTAINERS_ROOT=/operator/podman; "
                "export AOA_MACHINE_FIT_AUTO_APPLY=true; "
                f"export AOA_MACHINE_FIT_PATH={shlex.quote(str(machine_fit))}; "
                "source scripts/aoa-lib.sh; "
                "aoa_apply_machine_fit_runtime_posture; "
                'printf "%s" "$AOA_PODMAN_CONTAINERS_ROOT"'
            )

        self.assertEqual(output, "/operator/podman")


if __name__ == "__main__":
    unittest.main()
