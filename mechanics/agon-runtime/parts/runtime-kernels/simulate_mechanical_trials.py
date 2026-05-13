#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys


def find_repo_root(start):
    for candidate in (start, *start.parents):
        if (candidate / 'AGENTS.md').is_file() and (candidate / 'mechanics').is_dir():
            return candidate
    raise RuntimeError('could not find abyss-stack repository root')


ROOT = find_repo_root(pathlib.Path(__file__).resolve())
PART_ROOT = ROOT / "mechanics" / "agon-runtime" / "parts" / "runtime-kernels"
VALIDATE = PART_ROOT / "validate_mechanical_trial_runs.py"
CONFIG = PART_ROOT / "definitions" / "mechanical-trial-runs.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if args.check:
        return subprocess.run([sys.executable, str(VALIDATE)]).returncode
    data = json.loads(CONFIG.read_text(encoding='utf-8'))
    print(json.dumps({'registry_id': data['registry_id'], 'runs': len(data.get('runs', [])), 'posture': data.get('runtime_posture')}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0
if __name__ == '__main__': raise SystemExit(main())
