from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_codex_responsibility_movement",
    PART_ROOT / "external_codex_responsibility_movement.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


GOAL_ID = "goal:019fbb8a-e084-7e73-9a98-647a1dd76985"
HOLDER_ID = "holder:codex-goal-master:019fbb8a-e084-7e73-9a98-647a1dd76985"
OBLIGATION_DIGEST = "sha256:99d398ec8b9346c32acef06ce3f354a369e4bdb32f3acc06f3f5954e4c9b69d6"
HANDOFF_DIGEST = "sha256:37079ff08833d749b7fea0fcfa77867b95bb7255ad4e9e6f6feba6a079cc9a9d"
DIGEST = "sha256:" + "1" * 64


def _ref(object_id: str, *, owner_repo: str = "codex-goal") -> dict[str, str]:
    return {
        "object_id": object_id,
        "owner_repo": owner_repo,
        "schema_version": "test-ref-v1",
        "digest": DIGEST,
    }


def _evidence(
    evidence_id: str,
    kind: str,
    *,
    signal: str | None = None,
    observed_at: str = "2026-08-22T12:05:00Z",
    from_state: str | None = None,
    to_state: str | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "evidence_id": evidence_id,
        "kind": kind,
        "signal": signal or kind,
        "observed_at": observed_at,
        "source_ref": _ref(f"evidence:{evidence_id}", owner_repo="abyss-stack"),
    }
    if from_state is not None:
        value["from_state"] = from_state
    if to_state is not None:
        value["to_state"] = to_state
    if details is not None:
        value["details"] = details
    return value


def observation(
    evidence: list[dict[str, object]],
    *,
    estimated_ms: int = 30,
    budget_ms: int = 100,
    due_at: str = "2026-08-22T12:00:00Z",
    current_state: str = "returning",
) -> dict[str, object]:
    holder = _ref(HOLDER_ID)
    return {
        "schema_version": MODULE.OBSERVATION_SCHEMA_VERSION,
        "observation_id": "observation:actor-stasis-detection-20260822:001",
        "obligation_ref": {
            "object_id": "obligation:actor-stasis-detection-20260822",
            "owner_repo": "codex-goal",
            "schema_version": "compiled-obligation-v1",
            "digest": OBLIGATION_DIGEST,
        },
        "holder_ref": holder,
        "return_owner_ref": dict(holder),
        "handoff_ref": {
            "path": "/srv/aoa/role-first-external-embodiment-luna-handoff.json",
            "digest": HANDOFF_DIGEST,
        },
        "state_root": "/srv/aoa/canonical-master-pause-landing/state",
        "observed_at": "2026-08-22T12:05:00Z",
        "lifecycle": {
            "current_state": current_state,
            "expected_to_states": ["terminal"],
            "transition_started_at": "2026-08-22T11:55:00Z",
            "due_at": due_at,
            "next_observation_at": "2026-08-22T12:10:00Z",
        },
        "cost": {
            "one_shot": True,
            "polling": False,
            "estimated_ms": estimated_ms,
            "budget_ms": budget_ms,
        },
        "evidence": evidence,
        "claim_limits": {
            "external_canary": "not_claimed",
            "goal_acceptance": "not_claimed",
            "host_trust_admission": "separate_preserved",
        },
        "protected_residual_refs": [
            {
                "path": "/srv/aoa/actor-stasis-detection-20260822/trust-admission-blocker.json",
                "digest": DIGEST,
            }
        ],
        "stop_line": MODULE.STOP_LINE,
    }


def test_transport_failure_with_live_process_is_causal_stasis_and_typed_wake() -> None:
    value = observation(
        [
            _evidence(
                "process-still-live",
                "process",
                details={"present": True, "identity_bound": True},
            ),
            _evidence(
                "app-server-connect-failure",
                "transport",
                details={"code": "cannot_connect_to_codex_app_server"},
            ),
            _evidence("session-returning", "session"),
        ]
    )

    result = MODULE.observe_once(value)

    assert result["classification"] == "stasis"
    assert result["causal_basis"] == (
        "deadline_elapsed_without_matching_lifecycle_transition"
    )
    assert result["transition_evidence"]["matching_evidence_ids"] == []
    assert result["transition_evidence"]["process_existence_ignored"] is True
    assert result["transition_evidence"]["hook_screen_match_used"] is False
    assert result["event"]["reason"] == "missing_transition"
    assert result["event"]["evidence_summary"]["ignored_process_evidence_ids"] == [
        "process-still-live"
    ]
    assert result["wake"]["action"] == "review_return_owner"
    assert result["wake"]["holder_ref"] == value["holder_ref"]
    assert result["wake"]["runtime_reentry"]["transport"] == (
        "canonical-aoa-external-codex-return"
    )
    assert result["wake"]["effects"] == {
        "auto_kill": False,
        "auto_restart": False,
        "declare_domain_failure": False,
        "accept_goal": False,
        "disturb_unrelated_actors": False,
    }
    assert result["claim_limits"] == {
        "external_canary": "not_claimed",
        "goal_acceptance": "not_claimed",
        "host_trust_admission": "separate_preserved",
    }


def test_matching_transition_changes_only_classification_and_suppresses_wake() -> None:
    value = observation(
        [
            _evidence(
                "process-still-live",
                "process",
                details={"present": True},
            ),
            _evidence(
                "return-completed",
                "lifecycle_transition",
                signal="transition",
                from_state="returning",
                to_state="terminal",
            ),
        ]
    )

    result = MODULE.observe_once(value)

    assert result["classification"] == "progressing"
    assert result["causal_basis"] == "matching_lifecycle_transition"
    assert result["transition_evidence"]["matching_evidence_ids"] == [
        "return-completed"
    ]
    assert result["event"] is None
    assert result["wake"] is None
    assert result["unrelated_actors"]["preserved"] is True


def test_observation_is_one_shot_and_cost_aware() -> None:
    value = observation(
        [_evidence("process-still-live", "process", details={"present": True})],
        estimated_ms=101,
        budget_ms=100,
    )

    result = MODULE.observe_once(value)

    assert result["classification"] == "cost_deferred"
    assert result["next_observation"] == {
        "at": "2026-08-22T12:10:00Z",
        "reason": "cost_budget",
        "one_shot": True,
        "polling": False,
        "max_observations": 1,
    }
    assert result["event"] is None
    assert result["wake"] is None


def test_not_due_does_not_turn_process_evidence_into_progress() -> None:
    value = observation(
        [_evidence("process-still-live", "process", details={"present": True})],
        due_at="2026-08-22T12:20:00Z",
    )

    result = MODULE.observe_once(value)

    assert result["classification"] == "not_due"
    assert result["transition_evidence"]["process_existence_ignored"] is True
    assert result["next_observation"]["reason"] == "transition_deadline"


def test_holder_and_return_owner_must_be_exactly_bound() -> None:
    value = observation([])
    value["return_owner_ref"] = _ref("holder:other")

    with pytest.raises(MODULE.ResponsibilityMovementError, match="same exact holder"):
        MODULE.observe_once(value)


def test_hook_screen_is_not_an_admitted_observation_kind() -> None:
    value = observation([_evidence("screen", "hook_screen")])

    with pytest.raises(MODULE.ResponsibilityMovementError, match="schema mismatch"):
        MODULE.observe_once(value)


def test_cli_writes_typed_result_without_polling(tmp_path: Path) -> None:
    observation_path = tmp_path / "observation.json"
    result_path = tmp_path / "result.json"
    observation_path.write_text(
        json.dumps(
            observation(
                [_evidence("process-still-live", "process", details={"present": True})]
            ),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            str(Path(__file__).resolve().parents[5] / "scripts/aoa-external-codex-stasis"),
            "--observation",
            str(observation_path),
            "--result",
            str(result_path),
        ],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    result = json.loads(result_path.read_text(encoding="utf-8"))
    Draft202012Validator(
        json.loads(
            MODULE.RESULT_SCHEMA_PATH.read_text(encoding="utf-8")
        )
    ).validate(result)
    assert result["one_shot"] is True
    assert result["wake"]["effects"]["auto_kill"] is False
