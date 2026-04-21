#!/usr/bin/env python3
from __future__ import annotations
import json, hashlib, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
REG = ROOT / 'generated' / 'agon_duel_runtime_kernel_registry.min.json'
LOG = ROOT / 'examples' / 'agon_mechanical_duel_event_log.example.json'
def digest_obj(obj): return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def fail(msg): print(msg, file=sys.stderr); return 1
def validate_hash_chain(events):
    prev = None
    for expected_seq, event in enumerate(events, start=1):
        if event.get('seq') != expected_seq: return fail(f'non-monotonic seq at {expected_seq}')
        if event.get('prev_hash') != prev: return fail(f'prev_hash mismatch at seq {expected_seq}')
        h = event.get('event_hash')
        clone = dict(event); clone.pop('event_hash', None)
        if digest_obj(clone) != h: return fail(f'event_hash mismatch at seq {expected_seq}')
        prev = h
    return 0
def main():
    if not REG.exists(): return fail(f'missing {REG}')
    if not LOG.exists(): return fail(f'missing {LOG}')
    reg = json.loads(REG.read_text(encoding='utf-8'))
    if reg.get('count') != len(reg.get('kernels', [])): return fail('count mismatch')
    kernel = reg['kernels'][0]
    if kernel.get('service_activation') is not False: return fail('service_activation must be false')
    if kernel.get('runtime_effect') != 'local_event_log_candidate_only': return fail('runtime_effect must be candidate-only')
    stop = set(kernel.get('stop_lines', []))
    for required in ['no_live_verdict_authority','no_durable_scar_write','no_rank_or_trust_mutation','no_network_listener','no_background_daemon']:
        if required not in stop: return fail(f'missing stop-line {required}')
    log = json.loads(LOG.read_text(encoding='utf-8'))
    events = log.get('events', [])
    if validate_hash_chain(events) != 0: return 1
    types = [e['event_type'] for e in events]
    if 'kernel.reveal_view_recorded' in types:
        if types.index('kernel.commit_phase_closed') > types.index('kernel.reveal_view_recorded'):
            return fail('reveal occurred before commit phase closed')
    commit_count = sum(1 for e in events if e['event_type'] == 'kernel.sealed_commit_recorded')
    if commit_count != 2: return fail('mechanical duel example must contain exactly two sealed commits')
    for e in events:
        if e.get('actor','').endswith('.assistant') and e.get('payload', {}).get('commit_actor'):
            return fail('assistant appears to commit as contestant')
    print('agon duel runtime kernels ok')
    return 0
if __name__ == '__main__': raise SystemExit(main())
