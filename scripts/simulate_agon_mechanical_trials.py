#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATE = ROOT / 'scripts' / 'validate_agon_mechanical_trial_runs.py'
CONFIG = ROOT / 'config' / 'agon_mechanical_trial_runs.seed.json'

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
