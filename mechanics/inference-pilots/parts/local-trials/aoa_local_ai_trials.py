#!/usr/bin/env python3
"""Compatibility bridge for the preserved local AI trial runner."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType

COMPATIBILITY_BACKEND = Path(__file__).resolve().parent / "compatibility-runners" / "aoa-local-ai-trials"


def _load_backend() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("_aoa_local_ai_trials_compatibility", str(COMPATIBILITY_BACKEND))
    spec = importlib.util.spec_from_loader("_aoa_local_ai_trials_compatibility", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load local AI trials compatibility backend: {COMPATIBILITY_BACKEND}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BACKEND = _load_backend()

for _name in dir(_BACKEND):
    if _name.startswith("__") and _name not in {"__all__", "__doc__"}:
        continue
    globals()[_name] = getattr(_BACKEND, _name)


def main() -> None:
    sys.argv[0] = str(COMPATIBILITY_BACKEND)
    runpy.run_path(str(COMPATIBILITY_BACKEND), run_name="__main__")


if __name__ == "__main__":
    main()
