from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = (
    REPO_ROOT
    / "mechanics"
    / "machine-fit"
    / "parts"
    / "platform-adaptations"
    / "aoa_platform_adaptation.py"
)


def load_backend():
    spec = importlib.util.spec_from_file_location("aoa_platform_adaptation_under_test", BACKEND)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_default_host_facts_ref_uses_part_local_snapshot() -> None:
    module = load_backend()

    assert module.default_host_facts_ref("public") == (
        "repo:mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json"
    )

