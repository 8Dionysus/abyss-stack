import subprocess
import sys


def test_runtime_registry_build_check():
    result = subprocess.run([sys.executable, 'scripts/build_agon_duel_runtime_kernel_registry.py', '--check'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_runtime_registry_validates():
    result = subprocess.run([sys.executable, 'scripts/validate_agon_duel_runtime_kernels.py'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_local_duel_simulation_check():
    result = subprocess.run([sys.executable, 'scripts/simulate_agon_mechanical_duel_kernel.py', '--check'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
