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
EXAMPLE = PART_ROOT / "examples" / "mechanical-duel-event-log.example.json"
VALIDATE = PART_ROOT / "validate_duel_runtime_kernels.py"
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='Validate the bundled dry-run event log instead of printing it.')
    args = ap.parse_args()
    if args.check:
        return subprocess.run([sys.executable, str(VALIDATE)]).returncode
    data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
    print(json.dumps({'log_id': data['log_id'], 'kernel_id': data['kernel_id'], 'event_count': len(data['events']), 'final_state': data['final_state']}, ensure_ascii=False, sort_keys=True, indent=2))
    return 0
if __name__ == '__main__': raise SystemExit(main())
