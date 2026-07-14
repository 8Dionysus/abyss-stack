from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

from .canonical import CanonicalRepoKag
from .core import AoAKagMCPState


RUNTIME_RELATIVE_PATH = Path("mechanics/federation-seams/parts/kag-seam")


def _runtime_package_root() -> Path:
    configured = os.environ.get("AOA_KAG_RUNTIME_PACKAGE_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    stack_root = os.environ.get("AOA_ABYSS_STACK_ROOT") or os.environ.get(
        "AOA_STACK_ROOT"
    )
    if stack_root:
        candidates.append(Path(stack_root).expanduser() / RUNTIME_RELATIVE_PATH)
    source_root = Path(__file__).resolve().parents[5]
    candidates.extend(
        (
            source_root / RUNTIME_RELATIVE_PATH,
            Path("/srv/AbyssOS/abyss-stack/Configs") / RUNTIME_RELATIVE_PATH,
        )
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if (resolved / "kag_runtime" / "application.py").is_file():
            return resolved
    rendered = ", ".join(str(candidate) for candidate in candidates)
    raise RuntimeError(f"KAG runtime package is unavailable; checked: {rendered}")


def build_application(
    state: AoAKagMCPState,
    *,
    stack_root: str | Path | None = None,
) -> Any:
    package_root = _runtime_package_root()
    root = package_root.as_posix()
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module("kag_runtime.application")
    config = module.RuntimeConfig.discover(stack_root=stack_root)
    return module.KagApplication(
        config=config,
        canonical=CanonicalRepoKag(state),
        access_scopes=("public",),
    )
