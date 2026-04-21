from __future__ import annotations
import importlib.util, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod

def test_build_count_and_digest():
    mod = load('builder', 'scripts/build_agon_mechanical_trial_run_registry.py')
    reg = mod.build()
    assert reg['count'] == 7
    assert reg['runtime_posture'] == 'local_dry_run_candidate_only'

def test_validator_green():
    mod = load('validator', 'scripts/validate_agon_mechanical_trial_runs.py')
    assert mod.main() == 0

def test_simulator_check_green():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'simulate_agon_mechanical_trials.py'), '--check'], cwd=str(ROOT))
    assert result.returncode == 0
