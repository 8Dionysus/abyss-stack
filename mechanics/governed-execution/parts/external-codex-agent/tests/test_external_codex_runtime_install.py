from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_codex_runtime_install",
    PART_ROOT / "install_external_codex_runtime.py",
)
assert SPEC and SPEC.loader
runtime_install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_install)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(path: Path) -> None:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    git("config", "user.name", "Runtime Test", cwd=path)
    git("config", "user.email", "runtime-test@example.invalid", cwd=path)


def commit_all(path: Path) -> None:
    git("add", ".", cwd=path)
    git("commit", "-qm", "fixture", cwd=path)


def make_sources(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "abyss-stack"
    sdk = tmp_path / "aoa-sdk"
    make_repo(source)
    make_repo(sdk)
    part = source / "mechanics/governed-execution/parts/external-codex-agent"
    schemas = part / "schemas"
    schemas.mkdir(parents=True)
    (part / "external_codex_agent.py").write_text(
        "import aoa_sdk\nprint('agent:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "prepare_landing_study.py").write_text(
        "import aoa_sdk\nprint('study:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "external_codex_supervisor.py").write_text("PASS = True\n", encoding="utf-8")
    (part / "runtime-profile.v1.json").write_text("{}\n", encoding="utf-8")
    (schemas / "external-codex-test.schema.json").write_text("{}\n", encoding="utf-8")
    package = sdk / "src/aoa_sdk"
    (package / "contracts").mkdir(parents=True)
    (package / "__init__.py").write_text("MARKER = 'exact-sdk'\n", encoding="utf-8")
    (package / "contracts/__init__.py").write_text("", encoding="utf-8")
    (package / "contracts/incarnation.py").write_text("ABI = 1\n", encoding="utf-8")
    for relative in runtime_install.SDK_CONTRACT_FILES:
        contract = sdk / relative
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text("{}\n", encoding="utf-8")
    commit_all(source)
    commit_all(sdk)
    return source, sdk


def test_content_addressed_install_and_wrapper_use_exact_sdk(tmp_path: Path) -> None:
    source, sdk = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"

    receipt = runtime_install.install(
        source,
        sdk,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
    )

    active = receipt["active"]
    release_root = Path(active["release_root"])
    assert active["nonproduction_dirty_source"] is False
    assert release_root.name == active["release_id"]
    assert runtime_install.verify_release(release_root)["release_id"] == active["release_id"]
    assert runtime_install.status(runtime_root, bin_dir)["healthy"] is True
    for relative in runtime_install.SDK_CONTRACT_FILES:
        assert (release_root / "sdk" / relative).is_file()
    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == "agent:exact-sdk\n"
    study = subprocess.run(
        [str(bin_dir / "aoa-external-codex-study")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert study.stdout == "study:exact-sdk\n"

    repeated = runtime_install.install(
        source,
        sdk,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
    )
    assert repeated["release_created"] is False
    assert repeated["active"]["release_id"] == active["release_id"]


def test_dirty_source_requires_explicit_admission_and_preserves_rollback(tmp_path: Path) -> None:
    source, sdk = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    first = runtime_install.install(
        source,
        sdk,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
    )
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py"
    )
    controller.write_text(controller.read_text() + "# changed\n", encoding="utf-8")

    with pytest.raises(runtime_install.InstallError, match="--allow-dirty-source"):
        runtime_install.install(
            source,
            sdk,
            runtime_root,
            bin_dir,
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
        )

    second = runtime_install.install(
        source,
        sdk,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=True,
        allow_dirty_sdk=False,
    )
    assert second["active"]["nonproduction_dirty_source"] is True
    assert second["active"]["previous_release_id"] == first["active"]["release_id"]
    assert second["active"]["release_id"] != first["active"]["release_id"]

    restored = runtime_install.activate(
        runtime_root,
        bin_dir,
        first["active"]["release_id"],
        Path(sys.executable),
    )
    assert restored["active"]["release_id"] == first["active"]["release_id"]
    assert json.loads((runtime_root / "active.json").read_text())["release_id"] == first["active"]["release_id"]
