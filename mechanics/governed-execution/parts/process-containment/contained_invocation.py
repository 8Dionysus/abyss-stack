"""Backend-neutral entry point for one namespace-owned invocation.

The directory name is intentionally a mechanic path rather than an importable
Python package.  Adapters load this module by file location and only consume
the small dataclasses and ``run_contained`` function below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import sys
from typing import Mapping, Sequence


PART_ROOT = Path(__file__).resolve().parent
LAUNCHER_PATH = PART_ROOT / "namespace_launcher.py"


@dataclass(frozen=True)
class ReadOnlyRoot:
    """One host root and its explicit guest coordinate."""

    host: Path
    guest: str


@dataclass(frozen=True)
class ContainmentSpec:
    """The backend-neutral invocation contract."""

    profile_id: str
    source_root: ReadOnlyRoot
    runtime_roots: tuple[ReadOnlyRoot, ...]
    command: tuple[str, ...]
    environment: Mapping[str, str]
    cwd: str = "/workspace"
    export_root: Path | None = None
    drain_timeout_seconds: float = 5.0
    termination_grace_seconds: float = 1.0


@dataclass
class ContainmentResult:
    status: str
    returncode: int | None
    command_started: bool
    receipt: dict[str, object] = field(default_factory=dict)
    diagnostics: list[dict[str, object]] = field(default_factory=list)
    export_root: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "completed" and self.returncode == 0


def _launcher_module():
    module_name = "abyss_stack_process_containment_launcher"
    spec = importlib.util.spec_from_file_location(module_name, LAUNCHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load process-containment launcher: {LAUNCHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_contained(spec: ContainmentSpec) -> ContainmentResult:
    """Admit and run one invocation through the selected backend."""

    launcher = _launcher_module()
    return launcher.run_contained(spec, result_factory=ContainmentResult)


def containment_unsupported(reason: str, *, diagnostics: Sequence[dict[str, object]] = ()) -> ContainmentResult:
    return ContainmentResult(
        status="containment_unsupported",
        returncode=125,
        command_started=False,
        diagnostics=[{"code": reason, **item} for item in diagnostics],
    )
