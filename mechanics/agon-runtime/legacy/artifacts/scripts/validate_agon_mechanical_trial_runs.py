#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, pathlib, sys


def find_repo_root(start):
    for candidate in (start, *start.parents):
        if (candidate / 'AGENTS.md').is_file() and (candidate / 'mechanics').is_dir():
            return candidate
    raise RuntimeError('could not find abyss-stack repository root')


ROOT = find_repo_root(pathlib.Path(__file__).resolve())
ARTIFACTS = ROOT / 'mechanics' / 'agon-runtime' / 'legacy' / 'artifacts'
SRC = ARTIFACTS / 'config' / 'agon_mechanical_trial_runs.seed.json'
OUT = ARTIFACTS / 'generated' / 'agon_mechanical_trial_run_registry.min.json'
EXPECTED_COUNT = 7

def fail(msg):
    print(msg, file=sys.stderr)
    return 1

def digest_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def expected_registry(data, runs):
    return {
        'registry_id': data.get('registry_id', 'agon.mechanical_trial_run.registry.v0'),
        'wave': data.get('wave', 'XIII'),
        'runtime_posture': data.get('runtime_posture', 'candidate_only'),
        'count': len(runs),
        'runs': runs,
        'digest': digest_obj(runs),
    }

def validate_log(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('live_protocol') is not False:
        return 'live_protocol must be false'
    events = data.get('events', [])
    if not events:
        return 'missing events'
    prev = 'GENESIS'
    seen = []
    for expected_seq, ev in enumerate(events, 1):
        if ev.get('seq') != expected_seq:
            return f'non-monotonic seq in {path}'
        if ev.get('prev_hash') != prev:
            return f'broken hash chain in {path} at seq {expected_seq}'
        event_hash = ev.get('event_hash')
        clone = dict(ev)
        clone.pop('event_hash', None)
        if digest_obj(clone) != event_hash:
            return f'event_hash mismatch in {path} at seq {expected_seq}'
        prev = event_hash
        seen.append(ev.get('event_type'))
    if 'commit_phase_closed' not in seen:
        return 'missing commit_phase_closed event'
    if 'reveal_phase_closed' not in seen:
        return 'missing reveal_phase_closed event'
    if seen.index('commit_phase_closed') > seen.index('reveal_phase_closed'):
        return 'reveal occurred before commit phase closure'
    if 'adjudication_requested' in seen and any(ev.get('payload', {}).get('live_verdict') for ev in events):
        return 'live verdict leaked into dry-run log'
    last = events[-1]
    if last.get('event_type') != 'closeout_candidate':
        return 'final event must be closeout_candidate'
    payload = last.get('payload', {})
    if payload.get('closure_granted') or payload.get('durable_scar_written') or payload.get('rank_mutated'):
        return 'forbidden final mutation in closeout candidate'
    return None

def main():
    data = json.loads(SRC.read_text(encoding='utf-8'))
    runs = data.get('runs', [])
    if len(runs) != EXPECTED_COUNT:
        return fail(f'expected {EXPECTED_COUNT} runs, got {len(runs)}')
    seen = set()
    for run in runs:
        rid = run.get('run_id')
        if not rid or rid in seen:
            return fail(f'duplicate or missing run id {rid}')
        seen.add(rid)
        if run.get('live_protocol') is not False:
            return fail(f'run {rid} must keep live_protocol=false')
        if run.get('assistant_contestant_allowed') is not False:
            return fail(f'run {rid} allows assistant contestant drift')
        p = ROOT / run['event_log_example']
        if not p.exists():
            return fail(f'missing event log {p}')
        err = validate_log(p)
        if err:
            return fail(f'{rid}: {err}')
    if not OUT.exists():
        return fail(f'missing generated registry {OUT}')
    reg = json.loads(OUT.read_text(encoding='utf-8'))
    if reg != expected_registry(data, runs):
        return fail('generated registry does not match source rebuild')
    print(json.dumps({'ok': True, 'runs': len(runs)}, sort_keys=True))
    return 0
if __name__ == '__main__': raise SystemExit(main())
