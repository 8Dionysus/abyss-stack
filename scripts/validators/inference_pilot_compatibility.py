from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

TextReader = Callable[[Path], str | None]
ExecutablePathChecker = Callable[[Path], bool]

LOCAL_TRIALS_BRIDGE_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "local-trials"
    / "aoa_local_ai_trials.py"
)
LOCAL_TRIALS_ADAPTER_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "local-trials"
    / "trial_compatibility_bridge.py"
)
LOCAL_TRIALS_LEGACY_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "legacy"
    / "trials"
    / "artifacts"
    / "scripts"
    / "aoa-local-ai-trials"
)
STALE_LOCAL_TRIALS_ADAPTER_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "local-trials"
    / "legacy_trial_adapter.py"
)
STALE_LANGGRAPH_REQUIREMENTS_PATH = Path("scripts") / "requirements-langgraph-pilot.txt"
LANGGRAPH_CODE_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "langgraph-pilot"
    / "aoa_langgraph_pilot.py"
)
LANGGRAPH_DOC_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "langgraph-pilot"
    / "docs"
    / "LANGGRAPH_PILOT.md"
)
LLAMACPP_CODE_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "llamacpp-pilot"
    / "aoa_llamacpp_pilot.py"
)
LLAMACPP_DOC_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "llamacpp-pilot"
    / "docs"
    / "LLAMACPP_PILOT.md"
)
AUTONOMY_STATUS_CODE_PATH = (
    Path("mechanics")
    / "governed-execution"
    / "parts"
    / "autonomy-status"
    / "aoa_status_autonomy.py"
)
AUTONOMY_STATUS_README_PATH = (
    Path("mechanics")
    / "governed-execution"
    / "parts"
    / "autonomy-status"
    / "README.md"
)
INFERENCE_PILOT_COMPATIBILITY_FILES = (
    LOCAL_TRIALS_BRIDGE_PATH,
    LOCAL_TRIALS_ADAPTER_PATH,
    LOCAL_TRIALS_LEGACY_PATH,
    LANGGRAPH_CODE_PATH,
    LANGGRAPH_DOC_PATH,
    LLAMACPP_CODE_PATH,
    LLAMACPP_DOC_PATH,
    AUTONOMY_STATUS_CODE_PATH,
    AUTONOMY_STATUS_README_PATH,
)


def read_text(root: Path, relative_path: Path, read_text_func: TextReader) -> str:
    return read_text_func(root / relative_path) or ""


def validate_local_trials_compatibility_bridge(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
    is_executable_source_path_func: ExecutablePathChecker,
) -> None:
    bridge_path = root / LOCAL_TRIALS_BRIDGE_PATH
    adapter_path = root / LOCAL_TRIALS_ADAPTER_PATH
    legacy_path = root / LOCAL_TRIALS_LEGACY_PATH
    bridge_text = read_text_func(bridge_path) or ""
    adapter_text = read_text_func(adapter_path) or ""
    legacy_text = read_text_func(legacy_path) or ""

    if "LEGACY_BACKEND" not in bridge_text or "aoa-local-ai-trials" not in bridge_text:
        errors.append("local trials active backend must be a compatibility bridge to the legacy runner")
    for required_snippet in (
        "CompatibilityGate",
        "RUNTIME_GATE",
        "EDIT_GATE",
        "runtime_gate_run_command",
        "edit_gate_approval_path",
    ):
        if required_snippet not in adapter_text:
            errors.append(
                "mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py "
                f"must expose `{required_snippet}`"
            )
    if (root / STALE_LOCAL_TRIALS_ADAPTER_PATH).exists():
        errors.append(
            "mechanics/inference-pilots/parts/local-trials/legacy_trial_adapter.py "
            "must not return as an active module; use trial_compatibility_bridge.py"
        )
    if (root / STALE_LANGGRAPH_REQUIREMENTS_PATH).exists():
        errors.append(
            "scripts/requirements-langgraph-pilot.txt must stay moved to "
            "mechanics/inference-pilots/parts/langgraph-pilot/requirements.txt"
        )
    if "WAVE_METADATA =" in bridge_text:
        errors.append("local trials wave metadata must stay in legacy/trials/artifacts/scripts, not the active bridge")
    if "WAVE_METADATA =" not in legacy_text:
        errors.append("legacy local AI trials runner must preserve the W0-W4 compatibility metadata")
    if not is_executable_source_path_func(legacy_path):
        errors.append("legacy local AI trials runner must stay executable")


def validate_inference_pilot_compatibility_gate_language(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
) -> None:
    langgraph_code = read_text(root, LANGGRAPH_CODE_PATH, read_text_func)
    langgraph_doc = read_text(root, LANGGRAPH_DOC_PATH, read_text_func)
    llamacpp_code = read_text(root, LLAMACPP_CODE_PATH, read_text_func)
    llamacpp_doc = read_text(root, LLAMACPP_DOC_PATH, read_text_func)
    autonomy_status = read_text(root, AUTONOMY_STATUS_CODE_PATH, read_text_func)
    autonomy_status_readme = read_text(root, AUTONOMY_STATUS_README_PATH, read_text_func)

    for required_snippet in (
        "TRIAL_ADAPTER",
        "EDIT_GATE_WIRE_ID",
        "EDIT_GATE_INDEX_NAME",
        "preserved bounded-edit compatibility contract",
    ):
        if required_snippet not in langgraph_code:
            errors.append(
                "mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py "
                f"must route the preserved edit gate through `{required_snippet}`"
            )

    for required_snippet in (
        "preserved local-trials bounded-edit",
        "bounded-edit compatibility gate",
        "legacy/trials/",
    ):
        if required_snippet not in langgraph_doc:
            errors.append(
                "mechanics/inference-pilots/parts/langgraph-pilot/docs/LANGGRAPH_PILOT.md "
                f"must explain `{required_snippet}`"
            )

    for required_snippet in (
        "TRIAL_ADAPTER",
        "RUNTIME_GATE_WIRE_ID",
        "EDIT_GATE_WIRE_ID",
        "LLAMACPP_RUNTIME_GATE_PROGRAM_ID",
        "LLAMACPP_EDIT_GATE_PROGRAM_ID",
        "runtime_gate_result",
        "edit_fixture_gate_result",
    ):
        if required_snippet not in llamacpp_code:
            errors.append(
                "mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py "
                f"must route promotion gates through `{required_snippet}`"
            )

    for required_snippet in (
        "runtime compatibility gate",
        "edit fixture compatibility gate",
        "legacy trial runtime gate ID",
        "legacy trial edit gate ID",
    ):
        if required_snippet not in llamacpp_doc:
            errors.append(
                "mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md "
                f"must explain `{required_snippet}`"
            )

    for required_snippet in (
        "PRESERVED_LONG_HORIZON_PROGRAM_ID",
        "PRESERVED_LONG_HORIZON_INDEX_NAME",
        "PRESERVED_BOUNDED_AUTONOMY_PROGRAM_ID",
        "PRESERVED_BOUNDED_AUTONOMY_INDEX_NAME",
    ):
        if required_snippet not in autonomy_status:
            errors.append(
                "mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py "
                f"must route preserved pilot indexes through `{required_snippet}`"
            )
    if "legacy trial compatibility route" not in autonomy_status_readme:
        errors.append(
            "mechanics/governed-execution/parts/autonomy-status/README.md must explain the legacy trial compatibility route"
        )

    active_texts = {
        LANGGRAPH_CODE_PATH: langgraph_code,
        LANGGRAPH_DOC_PATH: langgraph_doc,
        LLAMACPP_CODE_PATH: llamacpp_code,
        LLAMACPP_DOC_PATH: llamacpp_doc,
    }
    forbidden_active_phrases = (
        "W4-shaped",
        "widen W4",
        "existing W4 bounded runner",
        "W4 bounded edit contract",
        "W4 bounded-mutation contract",
        "W4 supervised-edit contract",
        "W4-compatible",
        "W4 dry-run promotion verdict",
        "bounded W0 + W4 promotion gate",
    )
    for path, text in active_texts.items():
        for phrase in forbidden_active_phrases:
            if phrase in text:
                errors.append(
                    f"{path.as_posix()} must use compatibility gate language instead of `{phrase}`"
                )
