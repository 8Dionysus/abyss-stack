import subprocess
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError("could not find abyss-stack repository root")


ROOT = find_repo_root(Path(__file__).resolve())
PART_ROOT = ROOT / "mechanics" / "agon-runtime" / "parts" / "runtime-kernels"


def test_runtime_registry_build_check():
    result = subprocess.run(
        [sys.executable, str(PART_ROOT / "build_duel_runtime_kernel_registry.py"), "--check"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_runtime_registry_validates():
    result = subprocess.run(
        [sys.executable, str(PART_ROOT / "validate_duel_runtime_kernels.py")],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_local_duel_simulation_check():
    result = subprocess.run(
        [sys.executable, str(PART_ROOT / "simulate_mechanical_duel_kernel.py"), "--check"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
