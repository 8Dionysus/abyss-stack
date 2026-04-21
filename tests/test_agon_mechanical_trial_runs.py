from __future__ import annotations
import copy, importlib.util, json, pathlib, subprocess, sys
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

def test_validator_rejects_tampered_event_hash(tmp_path):
    mod = load('validator', 'scripts/validate_agon_mechanical_trial_runs.py')
    source = json.loads((ROOT / 'examples/agon_mechanical_trial_event_log.prediction.example.json').read_text(encoding='utf-8'))
    tampered = copy.deepcopy(source)
    tampered['events'][0]['payload']['trial_id'] = 'agon.trial.mechanical.tampered.v0'
    log = tmp_path / 'tampered_log.json'
    log.write_text(json.dumps(tampered), encoding='utf-8')
    assert mod.validate_log(log) == f'event_hash mismatch in {log} at seq 1'

def test_validator_rejects_missing_phase_markers_without_crashing(tmp_path):
    mod = load('validator', 'scripts/validate_agon_mechanical_trial_runs.py')
    source = json.loads((ROOT / 'examples/agon_mechanical_trial_event_log.prediction.example.json').read_text(encoding='utf-8'))
    trimmed = copy.deepcopy(source)
    trimmed['events'] = [event for event in trimmed['events'] if event['event_type'] != 'commit_phase_closed']
    for seq, event in enumerate(trimmed['events'], 1):
        event['seq'] = seq
        event['prev_hash'] = 'GENESIS' if seq == 1 else trimmed['events'][seq - 2]['event_hash']
        clone = dict(event)
        clone.pop('event_hash', None)
        event['event_hash'] = mod.digest_obj(clone)
    log = tmp_path / 'missing_commit_phase_closed.json'
    log.write_text(json.dumps(trimmed), encoding='utf-8')
    assert mod.validate_log(log) == 'missing commit_phase_closed event'

def test_validator_rejects_stale_generated_registry(tmp_path):
    validator = load('validator', 'scripts/validate_agon_mechanical_trial_runs.py')
    builder = load('builder', 'scripts/build_agon_mechanical_trial_run_registry.py')
    stale = builder.build()
    stale['digest'] = '0' * 64
    out = tmp_path / 'agon_mechanical_trial_run_registry.min.json'
    out.write_text(json.dumps(stale), encoding='utf-8')
    validator.OUT = out
    assert validator.main() == 1

def test_simulator_check_green():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'simulate_agon_mechanical_trials.py'), '--check'], cwd=str(ROOT))
    assert result.returncode == 0
