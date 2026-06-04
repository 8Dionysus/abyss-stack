#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, hashlib, pathlib, sys


def find_repo_root(start):
    for candidate in (start, *start.parents):
        if (candidate / 'AGENTS.md').is_file() and (candidate / 'mechanics').is_dir():
            return candidate
    raise RuntimeError('could not find abyss-stack repository root')


ROOT = find_repo_root(pathlib.Path(__file__).resolve())
PART_ROOT = ROOT / "mechanics" / "agon-runtime" / "parts" / "runtime-kernels"
SRC = PART_ROOT / "definitions" / "mechanical-trial-runs.json"
OUT = PART_ROOT / "generated" / "mechanical-trial-run-registry.min.json"
ITEM_KEY = 'runs'
REGISTRY_ID = 'agon.mechanical_trial_run.registry.v0'
LINEAGE_REF = 'PROVENANCE.md'

def digest_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def build():
    data = json.loads(SRC.read_text(encoding='utf-8'))
    items = data.get(ITEM_KEY, [])
    return {
        'registry_id': data.get('registry_id', REGISTRY_ID),
        'lineage_ref': data.get('lineage_ref', LINEAGE_REF),
        'runtime_posture': data.get('runtime_posture', 'candidate_only'),
        'count': len(items),
        ITEM_KEY: items,
        'digest': digest_obj(items),
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    reg = build()
    txt = json.dumps(reg, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != txt:
            print('generated registry drift: run this builder without --check', file=sys.stderr)
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(txt, encoding='utf-8')
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
