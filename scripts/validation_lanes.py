#!/usr/bin/env python3
"""Load abyss-stack validation lane command sequences."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "validation" / "validation_lanes.json"


@dataclass(frozen=True)
class CommandStep:
    label: str
    command: tuple[str, ...]


class ManifestError(ValueError):
    """Raised when validation_lanes.json is malformed."""


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"missing validation lane manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{path} must contain valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("validation lane manifest must contain a JSON object")
    validate_manifest(payload)
    return payload


def validate_manifest(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise ManifestError("validation lane manifest schema_version must be 1")
    lanes = payload.get("lanes")
    sequences = payload.get("command_sequences")
    if not isinstance(lanes, dict) or not lanes:
        raise ManifestError("validation lane manifest must define lanes")
    if not isinstance(sequences, dict) or not sequences:
        raise ManifestError("validation lane manifest must define command_sequences")

    for lane_id, lane in lanes.items():
        if not isinstance(lane, dict):
            raise ManifestError(f"lane {lane_id!r} must be an object")
        sequence_id = lane.get("command_sequence")
        if not isinstance(sequence_id, str) or not sequence_id:
            raise ManifestError(f"lane {lane_id!r} must name a command_sequence")
        if sequence_id not in sequences:
            raise ManifestError(
                f"lane {lane_id!r} references missing command_sequence {sequence_id!r}"
            )

    for sequence_id, steps in sequences.items():
        if not isinstance(steps, list) or not steps:
            raise ManifestError(f"command_sequence {sequence_id!r} must be a non-empty list")
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ManifestError(f"{sequence_id}[{index}] must be an object")
            label = step.get("label")
            command = step.get("command")
            if not isinstance(label, str) or not label:
                raise ManifestError(f"{sequence_id}[{index}] must have a label")
            if (
                not isinstance(command, list)
                or not command
                or not all(isinstance(part, str) and part for part in command)
            ):
                raise ManifestError(f"{sequence_id}[{index}] must have a string command list")


def lane_ids(path: Path = MANIFEST_PATH) -> tuple[str, ...]:
    manifest = load_manifest(path)
    return tuple(sorted(manifest["lanes"]))


def lane_command_sequence(lane_id: str, path: Path = MANIFEST_PATH) -> tuple[CommandStep, ...]:
    manifest = load_manifest(path)
    lanes = manifest["lanes"]
    if lane_id not in lanes:
        available = ", ".join(sorted(lanes))
        raise ManifestError(f"unknown validation lane {lane_id!r}; available lanes: {available}")
    sequence_id = lanes[lane_id]["command_sequence"]
    return command_sequence(sequence_id, path)


def command_sequence(sequence_id: str, path: Path = MANIFEST_PATH) -> tuple[CommandStep, ...]:
    manifest = load_manifest(path)
    sequences = manifest["command_sequences"]
    if sequence_id not in sequences:
        available = ", ".join(sorted(sequences))
        raise ManifestError(f"unknown command sequence {sequence_id!r}; available sequences: {available}")

    steps: list[CommandStep] = []
    for step in sequences[sequence_id]:
        command = tuple(sys.executable if part == "python" else part for part in step["command"])
        steps.append(CommandStep(label=step["label"], command=command))
    return tuple(steps)


def main() -> int:
    try:
        manifest = load_manifest()
    except ManifestError as exc:
        print(f"validation lane manifest failed: {exc}")
        return 1
    print("validation lane manifest passed")
    for lane_id in sorted(manifest["lanes"]):
        sequence_id = manifest["lanes"][lane_id]["command_sequence"]
        print(f"- {lane_id}: {sequence_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
