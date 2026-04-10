from __future__ import annotations

import subprocess
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
    def test_legacy_no_op_offload_true_maps_to_op_offload_zero(self) -> None:
        output = run_aoa_lib(
            "unset AOA_LLAMACPP_OP_OFFLOAD; export AOA_LLAMACPP_NO_OP_OFFLOAD=1; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "0")

    def test_legacy_no_op_offload_false_maps_to_op_offload_one(self) -> None:
        output = run_aoa_lib(
            "unset AOA_LLAMACPP_OP_OFFLOAD; export AOA_LLAMACPP_NO_OP_OFFLOAD=0; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "1")

    def test_explicit_op_offload_wins_over_legacy_bridge(self) -> None:
        output = run_aoa_lib(
            "export AOA_LLAMACPP_OP_OFFLOAD=7; export AOA_LLAMACPP_NO_OP_OFFLOAD=1; source scripts/aoa-lib.sh; printf '%s' \"$AOA_LLAMACPP_OP_OFFLOAD\""
        )
        self.assertEqual(output, "7")


if __name__ == "__main__":
    unittest.main()
