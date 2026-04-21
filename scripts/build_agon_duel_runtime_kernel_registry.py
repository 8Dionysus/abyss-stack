#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, hashlib, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / 'config' / 'agon_duel_runtime_kernels.seed.json'
OUT = ROOT / 'generated' / 'agon_duel_runtime_kernel_registry.min.json'
def digest_obj(obj): return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def build():
    data = json.loads(SRC.read_text(encoding='utf-8'))
    kernels = data.get('kernels', [])
    return {'registry_id': data['registry_id'], 'wave': data.get('wave','XII'), 'count': len(kernels), 'runtime_status': data.get('runtime_status'), 'kernels': kernels, 'digest': digest_obj(kernels)}
def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--check', action='store_true'); args = ap.parse_args()
    txt = json.dumps(build(), ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n'
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding='utf-8') != txt:
            print('generated runtime kernel registry drift', file=sys.stderr); return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_text(txt, encoding='utf-8'); return 0
if __name__ == '__main__': raise SystemExit(main())
