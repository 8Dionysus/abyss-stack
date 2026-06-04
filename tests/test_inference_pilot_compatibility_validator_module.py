from __future__ import annotations

import os
from pathlib import Path

from scripts.validators import inference_pilot_compatibility


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    source = REPO_ROOT / relative_path
    target = into / relative_path
    write_text(target, source.read_text(encoding="utf-8"))
    if source.stat().st_mode & 0o111:
        target.chmod(target.stat().st_mode | 0o755)


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in inference_pilot_compatibility.INFERENCE_PILOT_COMPATIBILITY_FILES:
        copy_current_surface(relative_path, into=repo_root)


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def is_executable(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)


def run_inference_pilot_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    inference_pilot_compatibility.validate_local_trials_compatibility_bridge(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
        is_executable_source_path_func=is_executable,
    )
    inference_pilot_compatibility.validate_inference_pilot_compatibility_gate_language(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_inference_pilot_compatibility_module_passes() -> None:
    assert run_inference_pilot_validator(REPO_ROOT) == []


def test_active_local_trials_backend_must_remain_compatibility_bridge(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    bridge_path = tmp_path / inference_pilot_compatibility.LOCAL_TRIALS_BRIDGE_PATH
    write_text(
        bridge_path,
        bridge_path.read_text(encoding="utf-8").replace("LEGACY_BACKEND", "ACTIVE_BACKEND"),
    )

    errors = run_inference_pilot_validator(tmp_path)

    assert "local trials active backend must be a compatibility bridge to the legacy runner" in errors


def test_active_local_trials_bridge_must_not_reown_wave_metadata(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    bridge_path = tmp_path / inference_pilot_compatibility.LOCAL_TRIALS_BRIDGE_PATH
    write_text(bridge_path, bridge_path.read_text(encoding="utf-8") + "\nWAVE_METADATA = {}\n")

    errors = run_inference_pilot_validator(tmp_path)

    assert (
        "local trials wave metadata must stay in legacy/trials/artifacts/scripts, "
        "not the active bridge"
    ) in errors


def test_trial_adapter_must_expose_runtime_gate_command(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    adapter_path = tmp_path / inference_pilot_compatibility.LOCAL_TRIALS_ADAPTER_PATH
    write_text(
        adapter_path,
        adapter_path.read_text(encoding="utf-8").replace(
            "runtime_gate_run_command",
            "runtime_gate_command",
        ),
    )

    errors = run_inference_pilot_validator(tmp_path)

    assert (
        "mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py "
        "must expose `runtime_gate_run_command`"
    ) in errors


def test_langgraph_code_must_route_preserved_edit_gate(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    langgraph_path = tmp_path / inference_pilot_compatibility.LANGGRAPH_CODE_PATH
    write_text(
        langgraph_path,
        langgraph_path.read_text(encoding="utf-8").replace("EDIT_GATE_INDEX_NAME", "EDIT_INDEX_NAME"),
    )

    errors = run_inference_pilot_validator(tmp_path)

    assert (
        "mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py "
        "must route the preserved edit gate through `EDIT_GATE_INDEX_NAME`"
    ) in errors


def test_llamacpp_doc_must_explain_legacy_gate_ids(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    doc_path = tmp_path / inference_pilot_compatibility.LLAMACPP_DOC_PATH
    write_text(
        doc_path,
        doc_path.read_text(encoding="utf-8").replace(
            "legacy trial runtime gate ID",
            "legacy trial runtime identifier",
        ),
    )

    errors = run_inference_pilot_validator(tmp_path)

    assert (
        "mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md "
        "must explain `legacy trial runtime gate ID`"
    ) in errors


def test_active_pilot_surfaces_must_not_restore_w4_labels(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    doc_path = tmp_path / inference_pilot_compatibility.LANGGRAPH_DOC_PATH
    write_text(doc_path, doc_path.read_text(encoding="utf-8") + "\nW4-compatible\n")

    errors = run_inference_pilot_validator(tmp_path)

    assert (
        "mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md "
        "must use compatibility gate language instead of `W4-compatible`"
    ) in errors
