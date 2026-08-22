#!/usr/bin/env python3
"""Detect one bounded loss of responsibility movement for an external actor.

This module observes an already-bound lifecycle snapshot.  It does not poll,
inspect a hook screen, infer domain completion, or mutate an actor.  A
matching lifecycle transition is the only positive movement signal; process
existence and other supporting observations remain evidence but never become
progress by themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


PART_ROOT = Path(__file__).resolve().parent
SCHEMA_ROOT = PART_ROOT / "schemas"
OBSERVATION_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-responsibility-observation.schema.json"
)
RESULT_SCHEMA_PATH = (
    SCHEMA_ROOT / "external-codex-responsibility-movement.schema.json"
)

OBSERVATION_SCHEMA_VERSION = (
    "abyss_stack_external_codex_responsibility_observation_v1"
)
RESULT_SCHEMA_VERSION = "abyss_stack_external_codex_responsibility_movement_v1"
STASIS_EVENT_SCHEMA_VERSION = "abyss_stack_external_codex_stasis_event_v1"
TYPED_WAKE_SCHEMA_VERSION = "abyss_stack_external_codex_typed_wake_v1"

LIFECYCLE_STATES = (
    "accepted",
    "session_started",
    "turn_started",
    "progressing",
    "waiting",
    "returning",
    "terminal",
)
EVIDENCE_KINDS = (
    "lifecycle_transition",
    "session",
    "turn",
    "tool",
    "artifact",
    "resource",
    "process",
    "transport",
)
STOP_LINE = (
    "Return a reviewed implementation and causal proof to the exact master; "
    "do not auto-kill, auto-restart, declare domain failure, accept the Goal, "
    "or disturb unrelated actors."
)


class ResponsibilityMovementError(ValueError):
    """A malformed observation or an unsafe movement result."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _read_schema(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResponsibilityMovementError(f"cannot read schema: {path}") from exc
    if not isinstance(value, dict):
        raise ResponsibilityMovementError(f"schema is not an object: {path}")
    return value


def _schema_errors(value: object, path: Path) -> list[str]:
    validator = Draft202012Validator(_read_schema(path))
    return [error.message for error in sorted(validator.iter_errors(value), key=str)]


def _validate_schema(value: object, path: Path, label: str) -> None:
    errors = _schema_errors(value, path)
    if errors:
        raise ResponsibilityMovementError(f"{label} schema mismatch: {errors[0]}")


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ResponsibilityMovementError(f"{label} must be an RFC3339 timestamp")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ResponsibilityMovementError(f"{label} is not an RFC3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ResponsibilityMovementError(f"{label} must carry a timezone")
    return parsed.astimezone(UTC)


def _ref_identity(value: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(value["object_id"]),
        str(value["owner_repo"]),
        str(value["schema_version"]),
        str(value["digest"]),
    )


def validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the typed, one-shot observation envelope."""

    candidate = dict(value)
    _validate_schema(candidate, OBSERVATION_SCHEMA_PATH, "responsibility observation")
    if candidate["stop_line"] != STOP_LINE:
        raise ResponsibilityMovementError("observation stop line drifted")
    if _ref_identity(candidate["holder_ref"]) != _ref_identity(
        candidate["return_owner_ref"]
    ):
        raise ResponsibilityMovementError(
            "holder and return-owner identities must be the same exact holder"
        )

    observed_at = _parse_time(candidate["observed_at"], "observed_at")
    lifecycle = candidate["lifecycle"]
    transition_started_at = _parse_time(
        lifecycle["transition_started_at"], "transition_started_at"
    )
    due_at = _parse_time(lifecycle["due_at"], "due_at")
    next_observation_at = _parse_time(
        lifecycle["next_observation_at"], "next_observation_at"
    )
    if transition_started_at > observed_at:
        raise ResponsibilityMovementError("transition_started_at is after observation")
    if next_observation_at <= observed_at:
        raise ResponsibilityMovementError(
            "next_observation_at must be after the one-shot observation"
        )
    if due_at < transition_started_at:
        raise ResponsibilityMovementError("due_at precedes transition_started_at")
    for index, evidence in enumerate(candidate["evidence"]):
        evidence_at = _parse_time(evidence["observed_at"], f"evidence[{index}].observed_at")
        if evidence_at > observed_at:
            raise ResponsibilityMovementError(
                f"evidence[{index}] is newer than the observation snapshot"
            )
        if evidence["kind"] == "lifecycle_transition":
            if evidence.get("from_state") not in LIFECYCLE_STATES:
                raise ResponsibilityMovementError(
                    f"evidence[{index}] lacks a valid from_state"
                )
            if evidence.get("to_state") not in LIFECYCLE_STATES:
                raise ResponsibilityMovementError(
                    f"evidence[{index}] lacks a valid to_state"
                )
    return candidate


def _matching_transition_ids(observation: Mapping[str, Any]) -> list[str]:
    lifecycle = observation["lifecycle"]
    current_state = lifecycle["current_state"]
    expected_states = set(lifecycle["expected_to_states"])
    transition_started_at = _parse_time(
        lifecycle["transition_started_at"], "transition_started_at"
    )
    observed_at = _parse_time(observation["observed_at"], "observed_at")
    matches: list[str] = []
    for evidence in observation["evidence"]:
        if evidence["kind"] != "lifecycle_transition":
            continue
        evidence_at = _parse_time(evidence["observed_at"], "lifecycle transition")
        if (
            evidence_at > transition_started_at
            and evidence_at <= observed_at
            and evidence["from_state"] == current_state
            and evidence["to_state"] in expected_states
        ):
            matches.append(evidence["evidence_id"])
    return matches


def _next_observation(observation: Mapping[str, Any], reason: str) -> dict[str, Any]:
    lifecycle = observation["lifecycle"]
    return {
        "at": lifecycle["next_observation_at"],
        "reason": reason,
        "one_shot": True,
        "polling": False,
        "max_observations": 1,
    }


def _event(
    observation: Mapping[str, Any],
    *,
    observation_digest: str,
    process_ids: list[str],
) -> dict[str, Any]:
    lifecycle = observation["lifecycle"]
    evidence_kinds = sorted({evidence["kind"] for evidence in observation["evidence"]})
    event: dict[str, Any] = {
        "schema_version": STASIS_EVENT_SCHEMA_VERSION,
        "event_id": f"stasis:{observation['observation_id']}",
        "classification": "stasis",
        "reason": "missing_transition",
        "holder_ref": observation["holder_ref"],
        "return_owner_ref": observation["return_owner_ref"],
        "handoff_ref": observation["handoff_ref"],
        "observed_at": observation["observed_at"],
        "transition": {
            "from_state": lifecycle["current_state"],
            "expected_to_states": lifecycle["expected_to_states"],
            "transition_started_at": lifecycle["transition_started_at"],
            "due_at": lifecycle["due_at"],
        },
        "evidence_summary": {
            "kinds": evidence_kinds,
            "matching_lifecycle_transition": False,
            "process_existence_ignored": bool(process_ids),
            "ignored_process_evidence_ids": process_ids,
            "hook_screen_match_used": False,
        },
        "source_observation_digest": observation_digest,
        "uncertainty": [
            "process existence is not responsibility progress",
            "domain completion and Goal acceptance remain undecided",
            "the return owner must review the missing transition",
        ],
        "stop_line": STOP_LINE,
    }
    event["event_digest"] = _digest(event)
    return event


def _wake(
    observation: Mapping[str, Any],
    event: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": TYPED_WAKE_SCHEMA_VERSION,
        "wake_id": f"wake:{event['event_id']}",
        "action": "review_return_owner",
        "holder_ref": observation["holder_ref"],
        "return_owner_ref": observation["return_owner_ref"],
        "trigger_ref": {
            "event_id": event["event_id"],
            "event_digest": event["event_digest"],
        },
        "handoff_ref": observation["handoff_ref"],
        "state_root": observation["state_root"],
        "runtime_reentry": {
            "transport": "canonical-aoa-external-codex-return",
            "mode": "bound_return",
            "app_server_resolution": "resolve-current-local-codex-app-server",
            "requires_current_master_binding": True,
            "requires_owner_review": True,
        },
        "effects": {
            "auto_kill": False,
            "auto_restart": False,
            "declare_domain_failure": False,
            "accept_goal": False,
            "disturb_unrelated_actors": False,
        },
        "stop_line": STOP_LINE,
    }


def _result(
    observation: Mapping[str, Any],
    *,
    classification: str,
    causal_basis: str,
    matching_ids: list[str],
    event: dict[str, Any] | None,
    wake: dict[str, Any] | None,
    next_observation: dict[str, Any] | None,
) -> dict[str, Any]:
    process_ids = [
        evidence["evidence_id"]
        for evidence in observation["evidence"]
        if evidence["kind"] == "process"
    ]
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "observation_id": observation["observation_id"],
        "source_observation_digest": _digest(observation),
        "classification": classification,
        "one_shot": True,
        "cost": {
            "estimated_ms": observation["cost"]["estimated_ms"],
            "budget_ms": observation["cost"]["budget_ms"],
            "within_budget": (
                observation["cost"]["estimated_ms"]
                <= observation["cost"]["budget_ms"]
            ),
            "observed_source_count": len(observation["evidence"]),
        },
        "transition_evidence": {
            "current_state": observation["lifecycle"]["current_state"],
            "expected_to_states": observation["lifecycle"]["expected_to_states"],
            "matching_evidence_ids": matching_ids,
            "process_existence_ignored": bool(process_ids),
            "ignored_process_evidence_ids": process_ids,
            "hook_screen_match_used": False,
        },
        "event": event,
        "wake": wake,
        "next_observation": next_observation,
        "causal_basis": causal_basis,
        "stop_line": STOP_LINE,
        "claim_limits": {
            "external_canary": "not_claimed",
            "goal_acceptance": "not_claimed",
            "host_trust_admission": "separate_preserved",
        },
        "unrelated_actors": {
            "preserved": True,
            "automatic_kill": False,
            "automatic_restart": False,
        },
    }
    _validate_schema(result, RESULT_SCHEMA_PATH, "responsibility movement result")
    return result


def observe_once(value: Mapping[str, Any]) -> dict[str, Any]:
    """Classify exactly one observation without starting a polling loop."""

    observation = validate_observation(value)
    now = _parse_time(observation["observed_at"], "observed_at")
    due_at = _parse_time(observation["lifecycle"]["due_at"], "due_at")
    estimated_ms = observation["cost"]["estimated_ms"]
    budget_ms = observation["cost"]["budget_ms"]
    matching_ids = _matching_transition_ids(observation)
    process_ids = [
        evidence["evidence_id"]
        for evidence in observation["evidence"]
        if evidence["kind"] == "process"
    ]

    if estimated_ms > budget_ms:
        return _result(
            observation,
            classification="cost_deferred",
            causal_basis="observation_cost_exceeds_budget",
            matching_ids=matching_ids,
            event=None,
            wake=None,
            next_observation=_next_observation(observation, "cost_budget"),
        )
    if now < due_at:
        return _result(
            observation,
            classification="not_due",
            causal_basis="deadline_not_reached",
            matching_ids=matching_ids,
            event=None,
            wake=None,
            next_observation=_next_observation(observation, "transition_deadline"),
        )
    if matching_ids:
        return _result(
            observation,
            classification="progressing",
            causal_basis="matching_lifecycle_transition",
            matching_ids=matching_ids,
            event=None,
            wake=None,
            next_observation=None,
        )

    observation_digest = _digest(observation)
    event = _event(
        observation,
        observation_digest=observation_digest,
        process_ids=process_ids,
    )
    return _result(
        observation,
        classification="stasis",
        causal_basis="deadline_elapsed_without_matching_lifecycle_transition",
        matching_ids=[],
        event=event,
        wake=_wake(observation, event),
        next_observation=None,
    )


def _read_observation(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ResponsibilityMovementError(
            f"observation must be an absolute regular non-symlink file: {path}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResponsibilityMovementError(f"observation is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ResponsibilityMovementError("observation must be a JSON object")
    return value


def _write_result(path: Path, value: Mapping[str, Any]) -> None:
    if not path.is_absolute() or path.is_symlink():
        raise ResponsibilityMovementError(
            f"result must be an absolute non-symlink path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one bounded external-Codex responsibility movement observation"
    )
    parser.add_argument("--observation", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        observation_path = args.observation.resolve()
        result_path = args.result.resolve()
        if observation_path == result_path:
            raise ResponsibilityMovementError("observation and result paths must differ")
        result = observe_once(_read_observation(observation_path))
        _write_result(result_path, result)
    except ResponsibilityMovementError as exc:
        print(f"error: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
