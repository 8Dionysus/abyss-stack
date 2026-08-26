from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PART_ROOT / "external_codex_nested_evidence.py"


def _load_nested_evidence():
    spec = importlib.util.spec_from_file_location(
        "abyss_stack_external_codex_nested_evidence_focused_test",
        SOURCE_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load nested evidence source: {SOURCE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


NESTED_EVIDENCE = _load_nested_evidence()


def test_cached_review_seal_projection_does_not_reverify(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection = tmp_path / "missing-after-seal"
    record = SimpleNamespace(payload={"actor_projection_path": str(projection)})
    cached_seal = (tmp_path / "review-state-seal", {"tree_entries": []})

    def fail_if_reverified(_record: object) -> object:
        raise AssertionError("cached producer seal was verified again")

    monkeypatch.setattr(
        NESTED_EVIDENCE,
        "_producer_review_seal",
        fail_if_reverified,
    )

    assert NESTED_EVIDENCE._producer_projection(
        record,
        review_seal=cached_seal,
    ) == projection


def _result_shape(
    workspace: Path,
    *,
    session_id: str,
    attempt_count: int,
    observations: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "attempt_count": attempt_count,
        "actor_projection_path": str(workspace),
        "executed_commands": observations,
    }


def _observation(attempt_id: str, command_id: str) -> dict[str, object]:
    return {
        "attempt_id": attempt_id,
        "validation_command_id": command_id,
        "status": "completed",
        "exit_code": 0,
    }


def test_terminal_report_must_match_result_attempt_count(tmp_path: Path) -> None:
    session = tmp_path / "producer-session"
    workspace = session / "actor-workspace"
    workspace.mkdir(parents=True)
    report_002 = session / "attempts/002/model-report.json"
    report_002.parent.mkdir(parents=True)

    result = _result_shape(
        workspace,
        session_id="memo-resumed",
        attempt_count=3,
        observations=[
            _observation("memo-resumed:attempt:1", "validate-memo-decision-v2-json")
        ],
    )
    record = SimpleNamespace(payload=result)
    with pytest.raises(
        NESTED_EVIDENCE.NestedEvidenceNamespaceError,
        match="terminal attempt identity is not result-bound",
    ):
        NESTED_EVIDENCE._terminal_attempt_id(record, report_002)

    report_003 = session / "attempts/003/model-report.json"
    terminal_attempt = NESTED_EVIDENCE._terminal_attempt_id(record, report_003)
    assert terminal_attempt == "memo-resumed:attempt:3"


def test_validation_selector_is_attempt_qualified_and_fail_closed(
    tmp_path: Path,
) -> None:
    session = tmp_path / "producer-session"
    workspace = session / "actor-workspace"
    workspace.mkdir(parents=True)
    command_id = "validate-stats-answer-v2-json"
    terminal_attempt = "stats-resumed:attempt:2"
    result = _result_shape(
        workspace,
        session_id="stats-resumed",
        attempt_count=2,
        observations=[
            _observation("stats-resumed:attempt:2", command_id),
            _observation("stats-resumed:attempt:1", command_id),
        ],
    )

    selected = NESTED_EVIDENCE._select_validation_observation(
        result,
        terminal_attempt,
        command_id,
    )
    assert selected["attempt_id"] == terminal_attempt

    duplicate = dict(result)
    duplicate["executed_commands"] = [
        *result["executed_commands"],
        _observation(terminal_attempt, command_id),
    ]
    with pytest.raises(
        NESTED_EVIDENCE.NestedEvidenceNamespaceError,
        match="has 2 exact observations in terminal attempt",
    ):
        NESTED_EVIDENCE._select_validation_observation(
            duplicate,
            terminal_attempt,
            command_id,
        )

    with pytest.raises(
        NESTED_EVIDENCE.NestedEvidenceNamespaceError,
        match="has 0 exact observations in terminal attempt",
    ):
        NESTED_EVIDENCE._select_validation_observation(
            result,
            "stats-resumed:attempt:3",
            command_id,
        )
