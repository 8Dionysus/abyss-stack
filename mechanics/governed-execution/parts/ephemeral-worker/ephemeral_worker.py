"""Default-off bounded runtime surface for the ephemeral read worker."""

from __future__ import annotations

import base64
import binascii
import errno
import hashlib
import json
import math
import os
import re
import stat
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

SCHEMA_VERSION = "abyss_ephemeral_read_worker_request_v1"
RESULT_SCHEMA_VERSION = "abyss_ephemeral_read_result_v1"
ADAPTER_SCHEMA_VERSION = "aoa_delegation_adapter_v1"
DELEGATION_ABI_VERSION = "aoa_delegation_class_v1"
EPHEMERAL_CLASS = "ephemeral_read_worker_v1"
EXTERNAL_CLASS = "external_incarnation_v1"
DISABLED_ACTIVATION = "disabled"
EXPLICIT_ACTIVATION = "explicit"
MAX_BYTE_CEILING = 16 * 1024 * 1024
MAX_ACTIVE_WALL_SECONDS = 365 * 24 * 60 * 60
MAX_ACTIVE_WALL_RENDER_BYTES = len(f"{MAX_ACTIVE_WALL_SECONDS:.6f}".encode("ascii"))
MAX_INPUT_COUNT = 1024
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 8
MAX_JSON_MAPPING_ITEMS = 64
MAX_JSON_NODES = MAX_INPUT_COUNT * 8 + 128


class EphemeralWorkerError(ValueError):
    """One request, path, digest, or bounded-read invariant failed."""


class EphemeralWorkerDisabled(EphemeralWorkerError):
    """The caller did not explicitly activate the default-off worker."""


class AdapterProfileError(ValueError):
    """Concrete adapter profiles do not form one provider-neutral pair."""


def _canonical_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EphemeralWorkerError("value must be canonical JSON") from exc
    return rendered.encode("utf-8")


def _consume_transport_budget(
    byte_count: int,
    label: str,
    remaining_bytes: list[int],
) -> None:
    if byte_count > remaining_bytes[0]:
        raise EphemeralWorkerError(
            f"{label} exceeds max_transport_bytes before validation "
            "and before serialization"
        )
    remaining_bytes[0] -= byte_count


def _consume_json_string_budget(
    value: str, label: str, remaining_bytes: list[int]
) -> None:
    """Account for ensure_ascii JSON string bytes without materializing them."""

    if len(value) + 2 > remaining_bytes[0]:
        raise EphemeralWorkerError(
            f"{label} strings exceed max_transport_bytes before validation "
            "and before serialization"
        )
    encoded_bytes = 2
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\"} or character in "\b\f\n\r\t":
            encoded_bytes += 2
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0xFFFF:
            encoded_bytes += 6
        elif codepoint > 0xFFFF:
            encoded_bytes += 12
        else:
            encoded_bytes += 1
        if encoded_bytes > remaining_bytes[0]:
            raise EphemeralWorkerError(
                f"{label} strings exceed max_transport_bytes before validation "
                "and before serialization"
            )
    _consume_transport_budget(encoded_bytes, label, remaining_bytes)


def _normalize_json_value(
    value: object,
    label: str,
    *,
    _depth: int = 0,
    _active_containers: set[int] | None = None,
    _remaining_nodes: list[int] | None = None,
    _remaining_transport_bytes: list[int] | None = None,
) -> object:
    """Copy a JSON-like value through bounded, cycle-safe traversal."""

    if _depth > MAX_JSON_DEPTH:
        raise EphemeralWorkerError(f"{label} exceeds the supported JSON depth")
    if _active_containers is None:
        _active_containers = set()
    if _remaining_nodes is None:
        _remaining_nodes = [MAX_JSON_NODES]
    if _remaining_transport_bytes is None:
        _remaining_transport_bytes = [MAX_BYTE_CEILING]
    _remaining_nodes[0] -= 1
    if _remaining_nodes[0] < 0:
        raise EphemeralWorkerError("result exceeds the supported JSON node count")

    is_sequence = isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    )
    if isinstance(value, Mapping) or is_sequence:
        container_id = id(value)
        if container_id in _active_containers:
            raise EphemeralWorkerError(f"{label} contains a JSON cycle")
        _active_containers.add(container_id)
        try:
            if isinstance(value, Mapping):
                if len(value) > MAX_JSON_MAPPING_ITEMS:
                    raise EphemeralWorkerError(
                        f"{label} exceeds the supported object cardinality"
                    )
                _consume_transport_budget(
                    2 + len(value) + max(0, len(value) - 1),
                    f"{label} object structure",
                    _remaining_transport_bytes,
                )
                normalized: dict[str, object] = {}
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise EphemeralWorkerError(
                            f"{label} object keys must be strings"
                        )
                    _consume_json_string_budget(
                        key,
                        f"{label} object key",
                        _remaining_transport_bytes,
                    )
                    normalized[key] = _normalize_json_value(
                        item,
                        f"{label}.{key}",
                        _depth=_depth + 1,
                        _active_containers=_active_containers,
                        _remaining_nodes=_remaining_nodes,
                        _remaining_transport_bytes=_remaining_transport_bytes,
                    )
                return normalized
            sequence_value = cast(Sequence[object], value)
            if len(sequence_value) > MAX_INPUT_COUNT:
                raise EphemeralWorkerError(
                    f"{label} exceeds the supported array cardinality"
                )
            _consume_transport_budget(
                2 + max(0, len(sequence_value) - 1),
                f"{label} array structure",
                _remaining_transport_bytes,
            )
            return [
                _normalize_json_value(
                    item,
                    f"{label}[{index}]",
                    _depth=_depth + 1,
                    _active_containers=_active_containers,
                    _remaining_nodes=_remaining_nodes,
                    _remaining_transport_bytes=_remaining_transport_bytes,
                )
                for index, item in enumerate(sequence_value)
            ]
        finally:
            _active_containers.remove(container_id)
    if isinstance(value, str):
        _consume_json_string_budget(value, label, _remaining_transport_bytes)
    elif value is None:
        _consume_transport_budget(4, f"{label} null scalar", _remaining_transport_bytes)
    elif isinstance(value, bool):
        _consume_transport_budget(
            4 if value else 5,
            f"{label} boolean scalar",
            _remaining_transport_bytes,
        )
    elif isinstance(value, int):
        try:
            byte_count = len(str(value))
        except ValueError as exc:
            raise EphemeralWorkerError(
                f"{label} integer is too large for canonical JSON"
            ) from exc
        _consume_transport_budget(
            byte_count,
            f"{label} numeric scalar",
            _remaining_transport_bytes,
        )
    elif isinstance(value, float):
        try:
            byte_count = len(json.dumps(value, allow_nan=False))
        except ValueError as exc:
            raise EphemeralWorkerError(
                f"{label} float is not canonical JSON"
            ) from exc
        _consume_transport_budget(
            byte_count,
            f"{label} numeric scalar",
            _remaining_transport_bytes,
        )
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise EphemeralWorkerError(f"{label} contains a non-JSON value")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len("sha256:") + 64
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EphemeralWorkerError(f"{label} must be a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        raise EphemeralWorkerError(
            f"{label} exceeds the supported string length of {MAX_STRING_LENGTH}"
        )
    return value


def _require_digest(value: object, label: str) -> str:
    if not _is_digest(value):
        raise EphemeralWorkerError(f"{label} must be a lowercase sha256 digest")
    return value  # type: ignore[return-value]


def _require_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise EphemeralWorkerError(f"{label} must be a positive integer")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float) and value.is_integer():
        normalized = int(value)
    else:
        raise EphemeralWorkerError(f"{label} must be a positive integer")
    if normalized <= 0:
        raise EphemeralWorkerError(f"{label} must be a positive integer")
    if normalized > MAX_BYTE_CEILING:
        raise EphemeralWorkerError(
            f"{label} exceeds the supported byte ceiling of {MAX_BYTE_CEILING}"
        )
    return normalized


def _normalize_json_integer(value: object) -> object:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _require_filesystem_encodable(path: str, label: str) -> None:
    try:
        os.fsencode(path)
    except UnicodeEncodeError as exc:
        raise EphemeralWorkerError(
            f"{label} cannot be encoded for the host filesystem"
        ) from exc


def _validate_content_ref(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise EphemeralWorkerError(f"{label} must be a content reference object")
    expected = {"object_id", "owner_repo", "schema_version", "digest"}
    if set(value) != expected:
        raise EphemeralWorkerError(f"{label} has an unexpected content-reference shape")
    return {
        field: _require_digest(value[field], f"{label}.{field}")
        if field == "digest"
        else _require_string(value[field], f"{label}.{field}")
        for field in sorted(expected)
    }


def _validate_input_item(value: object, index: int) -> dict[str, object]:
    label = f"inputs[{index}]"
    if not isinstance(value, Mapping):
        raise EphemeralWorkerError(f"{label} must be an object")
    expected = {"artifact_ref", "path", "digest", "max_bytes"}
    if set(value) != expected:
        raise EphemeralWorkerError(f"{label} has an unexpected shape")
    path = _require_string(value["path"], f"{label}.path")
    _require_filesystem_encodable(path, f"{label}.path")
    if "\x00" in path or not Path(path).is_absolute():
        raise EphemeralWorkerError(f"{label}.path must be an absolute NUL-free path")
    raw_components = path.split(os.sep)[1:]
    if not raw_components or any(
        component in {"", ".", ".."} for component in raw_components
    ):
        raise EphemeralWorkerError(
            f"{label}.path must use canonical components without dot traversal"
        )
    return {
        "artifact_ref": _require_string(value["artifact_ref"], f"{label}.artifact_ref"),
        "path": path,
        "digest": _require_digest(value["digest"], f"{label}.digest"),
        "max_bytes": _require_positive_int(value["max_bytes"], f"{label}.max_bytes"),
    }


def _normalized_path_key(path: str) -> str:
    candidate = Path(path)
    return os.sep + os.sep.join(candidate.parts[1:])


def _snapshot_payload(
    inputs: Sequence[Mapping[str, object]],
    max_input_bytes: object,
    max_output_bytes: object,
    max_transport_bytes: object,
) -> dict[str, object]:
    normalized_inputs = []
    for item in inputs:
        normalized_item = dict(item)
        if "max_bytes" in normalized_item:
            normalized_item["max_bytes"] = _normalize_json_integer(
                normalized_item["max_bytes"]
            )
        normalized_inputs.append(normalized_item)
    return {
        "inputs": normalized_inputs,
        "max_input_bytes": _normalize_json_integer(max_input_bytes),
        "max_output_bytes": _normalize_json_integer(max_output_bytes),
        "max_transport_bytes": _normalize_json_integer(max_transport_bytes),
    }


def snapshot_digest_for_request(
    inputs: Sequence[Mapping[str, object]],
    *,
    max_input_bytes: object,
    max_output_bytes: object,
    max_transport_bytes: object,
) -> str:
    """Return the digest required by the immutable request snapshot."""

    return _digest_bytes(
        _canonical_bytes(
            _snapshot_payload(
                inputs, max_input_bytes, max_output_bytes, max_transport_bytes
            )
        )
    )


def _validate_request(request: Mapping[str, object]) -> tuple[
    str,
    dict[str, str],
    list[dict[str, object]],
    str,
    int,
    int,
    int,
]:
    expected = {
        "schema_version",
        "request_id",
        "delegation_class",
        "activation",
        "parent_holder_ref",
        "input_snapshot_digest",
        "inputs",
        "max_input_bytes",
        "max_output_bytes",
        "max_transport_bytes",
    }
    if set(request) != expected:
        raise EphemeralWorkerError("request has an unexpected shape")
    if request["schema_version"] != SCHEMA_VERSION:
        raise EphemeralWorkerError("request schema version is unsupported")
    request_id = _require_string(request["request_id"], "request_id")
    if request["delegation_class"] != EPHEMERAL_CLASS:
        raise EphemeralWorkerError("request is not for ephemeral_read_worker_v1")
    if request["activation"] == DISABLED_ACTIVATION:
        raise EphemeralWorkerDisabled("ephemeral read worker is disabled by default")
    if request["activation"] != EXPLICIT_ACTIVATION:
        raise EphemeralWorkerError("activation must be disabled or explicit")
    parent_holder = _validate_content_ref(request["parent_holder_ref"], "parent_holder_ref")
    snapshot_digest = _require_digest(
        request["input_snapshot_digest"], "input_snapshot_digest"
    )
    raw_inputs = request["inputs"]
    if not isinstance(raw_inputs, Sequence) or isinstance(raw_inputs, (str, bytes)):
        raise EphemeralWorkerError("inputs must be a non-empty array")
    if len(raw_inputs) > MAX_INPUT_COUNT:
        raise EphemeralWorkerError(
            f"inputs exceeds the supported count of {MAX_INPUT_COUNT}"
        )
    inputs = [_validate_input_item(item, index) for index, item in enumerate(raw_inputs)]
    if not inputs:
        raise EphemeralWorkerError("inputs must be a non-empty array")
    artifact_refs = [str(item["artifact_ref"]) for item in inputs]
    paths = [str(item["path"]) for item in inputs]
    if len(artifact_refs) != len(set(artifact_refs)):
        raise EphemeralWorkerError("input artifact refs must be unique")
    normalized_paths = [_normalized_path_key(path) for path in paths]
    if len(normalized_paths) != len(set(normalized_paths)):
        raise EphemeralWorkerError("input paths must be unique")
    max_input_bytes = _require_positive_int(request["max_input_bytes"], "max_input_bytes")
    max_output_bytes = _require_positive_int(
        request["max_output_bytes"], "max_output_bytes"
    )
    max_transport_bytes = _require_positive_int(
        request["max_transport_bytes"], "max_transport_bytes"
    )
    declared_input_bytes = sum(
        _require_positive_int(item["max_bytes"], "input max_bytes")
        for item in inputs
    )
    if declared_input_bytes > max_input_bytes:
        raise EphemeralWorkerError("input ceilings exceed max_input_bytes")
    expected_snapshot = snapshot_digest_for_request(
        inputs,
        max_input_bytes=max_input_bytes,
        max_output_bytes=max_output_bytes,
        max_transport_bytes=max_transport_bytes,
    )
    if snapshot_digest != expected_snapshot:
        raise EphemeralWorkerError("input snapshot digest does not match request bytes")
    return (
        request_id,
        parent_holder,
        inputs,
        snapshot_digest,
        max_input_bytes,
        max_output_bytes,
        max_transport_bytes,
    )


def _read_verified(path: str, expected_digest: str, max_bytes: int, label: str) -> bytes:
    bounded_max_bytes = _require_positive_int(max_bytes, f"{label}.max_bytes")
    _require_filesystem_encodable(path, label)
    candidate = Path(path)
    if (
        "\x00" in path
        or not candidate.is_absolute()
        or candidate.anchor != os.sep
    ):
        raise EphemeralWorkerError(f"{label} must be an absolute NUL-free path")
    components = candidate.parts[1:]
    if not components or any(component in {".", ".."} for component in components):
        raise EphemeralWorkerError(
            f"{label} must not contain dot or dot-dot path components"
        )
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if (
        not directory_flag
        or not nofollow_flag
        or os.open not in getattr(os, "supports_dir_fd", ())
    ):
        raise EphemeralWorkerError(
            f"{label} cannot use descriptor-bound no-follow traversal"
        )
    directory_flags = getattr(os, "O_PATH", os.O_RDONLY) | directory_flag | nofollow_flag
    file_flags = os.O_RDONLY | nofollow_flag | getattr(os, "O_NONBLOCK", 0)
    parent_descriptor: int | None = None
    descriptor = -1
    try:
        parent_descriptor = os.open(os.sep, directory_flags)
        for component in components[:-1]:
            try:
                next_descriptor = os.open(
                    component, directory_flags, dir_fd=parent_descriptor
                )
            except OSError as exc:
                if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                    raise EphemeralWorkerError(
                        f"{label} has a symlinked parent"
                    ) from exc
                raise EphemeralWorkerError(
                    f"{label} could not be opened read-only"
                ) from exc
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        try:
            descriptor = os.open(
                components[-1], file_flags, dir_fd=parent_descriptor
            )
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise EphemeralWorkerError(f"{label} must not be a symlink") from exc
            raise EphemeralWorkerError(f"{label} could not be opened read-only") from exc
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise EphemeralWorkerError(f"{label} must name a regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read(bounded_max_bytes + 1)
    except EphemeralWorkerError:
        raise
    except OSError as exc:
        raise EphemeralWorkerError(f"{label} could not be read") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    if len(content) > bounded_max_bytes:
        raise EphemeralWorkerError(f"{label} exceeds its byte ceiling")
    actual_digest = _digest_bytes(content)
    if actual_digest != expected_digest:
        raise EphemeralWorkerError(f"{label} content digest changed before read")
    return content


def _projected_result_base_bytes(
    request_id: str,
    parent_holder: Mapping[str, str],
    input_snapshot_digest: str,
    inputs: Sequence[Mapping[str, object]],
) -> int:
    """Return a conservative canonical result size before content encoding."""

    skeleton: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "delegation_class": EPHEMERAL_CLASS,
        "parent_holder_ref": parent_holder,
        "input_snapshot_digest": input_snapshot_digest,
        "records": [],
        "economy_observation": {
            "schema_version": "abyss_delegation_economy_observation_v1",
            "input_bytes": 0,
            "output_bytes": 0,
            "active_wall_seconds": 0.0,
            "turn_count": 1,
            "executed_commands": 0,
        },
        "actual_effects": ["read_only"],
        "responsibility_posture": "parent_retained",
        "role_formation": False,
        "durable_responsibility_transfer": False,
        "result_digest": "sha256:" + "0" * 64,
    }
    projected = len(_canonical_bytes(skeleton))
    projected += MAX_ACTIVE_WALL_RENDER_BYTES - len(_canonical_bytes(0.0))
    for item in inputs:
        projected += len(
            _canonical_bytes(
                {
                    "artifact_ref": item["artifact_ref"],
                    "digest": item["digest"],
                    "bytes": 0,
                    "content_base64": "",
                }
            )
        )
    projected += max(0, len(inputs) - 1)
    return projected


def run_ephemeral_read_worker(request: Mapping[str, object]) -> dict[str, object]:
    """Execute one explicit, bounded, read-only request without writing state."""

    started = time.monotonic()
    (
        request_id,
        parent_holder,
        inputs,
        input_snapshot_digest,
        max_input_bytes,
        max_output_bytes,
        max_transport_bytes,
    ) = _validate_request(request)
    records: list[dict[str, object]] = []
    input_bytes = 0
    output_bytes = 0
    projected_result_bytes = _projected_result_base_bytes(
        request_id, parent_holder, input_snapshot_digest, inputs
    )
    if projected_result_bytes > max_transport_bytes:
        raise EphemeralWorkerError(
            "projected result exceeds max_transport_bytes before reading"
        )
    projected_input_digits = 1
    projected_output_digits = 1
    for index, item in enumerate(inputs):
        content = _read_verified(
            str(item["path"]),
            str(item["digest"]),
            _require_positive_int(item["max_bytes"], f"inputs[{index}].max_bytes"),
            f"inputs[{index}]",
        )
        input_bytes += len(content)
        if input_bytes > max_input_bytes:
            raise EphemeralWorkerError("read content exceeds max_input_bytes")
        output_bytes += len(content)
        if output_bytes > max_output_bytes:
            raise EphemeralWorkerError("read content exceeds max_output_bytes")
        input_digits = len(str(input_bytes))
        output_digits = len(str(output_bytes))
        projected_result_bytes += input_digits - projected_input_digits
        projected_result_bytes += output_digits - projected_output_digits
        projected_input_digits = input_digits
        projected_output_digits = output_digits
        projected_result_bytes += len(str(len(content))) - 1
        projected_result_bytes += ((len(content) + 2) // 3) * 4
        if projected_result_bytes > max_transport_bytes:
            raise EphemeralWorkerError(
                "projected result exceeds max_transport_bytes before encoding"
            )
        records.append(
            {
                "artifact_ref": item["artifact_ref"],
                "digest": str(item["digest"]),
                "bytes": len(content),
                "content_base64": base64.b64encode(content).decode("ascii"),
            }
        )
    observation = {
        "schema_version": "abyss_delegation_economy_observation_v1",
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "active_wall_seconds": round(max(0.0, time.monotonic() - started), 6),
        "turn_count": 1,
        "executed_commands": 0,
    }
    result: dict[str, object] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "request_id": request_id,
        "delegation_class": EPHEMERAL_CLASS,
        "parent_holder_ref": parent_holder,
        "input_snapshot_digest": input_snapshot_digest,
        "records": records,
        "economy_observation": observation,
        "actual_effects": ["read_only"],
        "responsibility_posture": "parent_retained",
        "role_formation": False,
        "durable_responsibility_transfer": False,
    }
    result["result_digest"] = _digest_bytes(_canonical_bytes(result))
    return validate_ephemeral_read_result(
        result,
        admitted_request=request,
        max_transport_bytes=max_transport_bytes,
    )


def _require_nonnegative_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise EphemeralWorkerError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, float) and value.is_integer():
        normalized = int(value)
    else:
        raise EphemeralWorkerError(f"{label} must be a non-negative integer")
    if normalized < 0:
        raise EphemeralWorkerError(f"{label} must be a non-negative integer")
    if normalized > MAX_BYTE_CEILING:
        raise EphemeralWorkerError(
            f"{label} exceeds the supported byte ceiling of {MAX_BYTE_CEILING}"
        )
    return normalized


def validate_ephemeral_read_result(
    payload: bytes | str | Mapping[str, object],
    *,
    admitted_request: Mapping[str, object] | None = None,
    max_transport_bytes: int | None = None,
) -> dict[str, object]:
    """Admit one bounded result against the exact request given to its producer."""

    admitted: tuple[
        str,
        dict[str, str],
        list[dict[str, object]],
        str,
        int,
        int,
        int,
    ] | None = None
    if admitted_request is not None:
        admitted = _validate_request(admitted_request)
        admitted_transport_ceiling = admitted[6]
    else:
        admitted_transport_ceiling = MAX_BYTE_CEILING
    if max_transport_bytes is None:
        transport_ceiling = admitted_transport_ceiling
    else:
        transport_ceiling = min(
            _require_positive_int(max_transport_bytes, "max_transport_bytes"),
            admitted_transport_ceiling,
        )
    if isinstance(payload, bytes):
        encoded = payload
        if len(encoded) > transport_ceiling:
            raise EphemeralWorkerError("result exceeds max_transport_bytes before parse")
        try:
            candidate = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise EphemeralWorkerError("result is not canonical JSON input") from exc
    elif isinstance(payload, str):
        if len(payload) > transport_ceiling:
            raise EphemeralWorkerError("result exceeds max_transport_bytes before parse")
        encoded_bytes = 0
        for offset in range(0, len(payload), 4096):
            try:
                encoded_bytes += len(payload[offset : offset + 4096].encode("utf-8"))
            except UnicodeEncodeError as exc:
                raise EphemeralWorkerError("result is not UTF-8 encodable") from exc
            if encoded_bytes > transport_ceiling:
                raise EphemeralWorkerError(
                    "result exceeds max_transport_bytes before parse"
                )
        try:
            candidate = json.loads(payload)
        except (ValueError, RecursionError) as exc:
            raise EphemeralWorkerError("result is not canonical JSON input") from exc
    elif isinstance(payload, Mapping):
        candidate = _normalize_json_value(
            payload,
            "result",
            _remaining_transport_bytes=[transport_ceiling],
        )
        if len(_canonical_bytes(candidate)) > transport_ceiling:
            raise EphemeralWorkerError(
                "mapped result exceeds max_transport_bytes before validation"
            )
    else:
        raise EphemeralWorkerError("result must be JSON bytes, text, or an object")

    if not isinstance(candidate, Mapping):
        raise EphemeralWorkerError("result must decode to an object")
    result = dict(candidate)
    expected = {
        "schema_version",
        "request_id",
        "delegation_class",
        "parent_holder_ref",
        "input_snapshot_digest",
        "records",
        "economy_observation",
        "actual_effects",
        "responsibility_posture",
        "role_formation",
        "durable_responsibility_transfer",
        "result_digest",
    }
    if set(result) != expected:
        raise EphemeralWorkerError("result has an unexpected shape")
    if admitted is None:
        raise EphemeralWorkerError("result intake requires the exact admitted request")
    (
        admitted_request_id,
        admitted_parent_holder,
        admitted_inputs,
        admitted_snapshot_digest,
        admitted_max_input_bytes,
        admitted_max_output_bytes,
        _,
    ) = admitted
    if result["schema_version"] != RESULT_SCHEMA_VERSION:
        raise EphemeralWorkerError("result schema version is unsupported")
    if _require_string(result["request_id"], "request_id") != admitted_request_id:
        raise EphemeralWorkerError("result request_id does not match admitted request")
    if result["delegation_class"] != EPHEMERAL_CLASS:
        raise EphemeralWorkerError("result has the wrong delegation class")
    if (
        _validate_content_ref(result["parent_holder_ref"], "parent_holder_ref")
        != admitted_parent_holder
    ):
        raise EphemeralWorkerError(
            "result parent_holder_ref does not match admitted request"
        )
    if (
        _require_digest(result["input_snapshot_digest"], "input_snapshot_digest")
        != admitted_snapshot_digest
    ):
        raise EphemeralWorkerError(
            "result input_snapshot_digest does not match admitted request"
        )
    records = result["records"]
    if (
        not isinstance(records, Sequence)
        or isinstance(records, (str, bytes))
        or not records
        or len(records) > MAX_INPUT_COUNT
        or len(records) != len(admitted_inputs)
    ):
        raise EphemeralWorkerError("result records exceed the supported cardinality")
    decoded_bytes = 0
    encoded_content_bytes = 0
    artifact_refs: set[str] = set()
    for index, record in enumerate(records):
        label = f"records[{index}]"
        if not isinstance(record, Mapping):
            raise EphemeralWorkerError(f"{label} must be an object")
        if set(record) != {"artifact_ref", "digest", "bytes", "content_base64"}:
            raise EphemeralWorkerError(f"{label} has an unexpected shape")
        artifact_ref = _require_string(
            record["artifact_ref"], f"{label}.artifact_ref"
        )
        if artifact_ref in artifact_refs:
            raise EphemeralWorkerError("result artifact refs must be unique")
        artifact_refs.add(artifact_ref)
        digest = _require_digest(record["digest"], f"{label}.digest")
        byte_count = _require_nonnegative_int(record["bytes"], f"{label}.bytes")
        admitted_input = admitted_inputs[index]
        if (
            artifact_ref != admitted_input["artifact_ref"]
            or digest != admitted_input["digest"]
        ):
            raise EphemeralWorkerError(
                f"{label} does not match the admitted input snapshot"
            )
        if byte_count > int(admitted_input["max_bytes"]):
            raise EphemeralWorkerError(f"{label}.bytes exceeds its admitted ceiling")
        encoded_content = record["content_base64"]
        if not isinstance(encoded_content, str):
            raise EphemeralWorkerError(f"{label}.content_base64 must be a string")
        if len(encoded_content) > MAX_BYTE_CEILING:
            raise EphemeralWorkerError(f"{label}.content_base64 exceeds its ceiling")
        try:
            encoded_content_ascii = encoded_content.encode("ascii")
        except UnicodeEncodeError as exc:
            raise EphemeralWorkerError(
                f"{label}.content_base64 is not canonical base64"
            ) from exc
        encoded_content_bytes += len(encoded_content_ascii)
        if encoded_content_bytes > transport_ceiling:
            raise EphemeralWorkerError(
                "result base64 content exceeds max_transport_bytes before decode"
            )
        try:
            content = base64.b64decode(encoded_content_ascii, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise EphemeralWorkerError(
                f"{label}.content_base64 is not canonical base64"
            ) from exc
        if base64.b64encode(content).decode("ascii") != encoded_content:
            raise EphemeralWorkerError(
                f"{label}.content_base64 is not canonical base64"
            )
        if len(content) != byte_count:
            raise EphemeralWorkerError(f"{label}.bytes does not match decoded content")
        if _digest_bytes(content) != digest:
            raise EphemeralWorkerError(f"{label}.digest does not match decoded content")
        decoded_bytes += byte_count
        if decoded_bytes > MAX_BYTE_CEILING:
            raise EphemeralWorkerError("result decoded content exceeds its ceiling")

    observation = result["economy_observation"]
    if not isinstance(observation, Mapping) or set(observation) != {
        "schema_version",
        "input_bytes",
        "output_bytes",
        "active_wall_seconds",
        "turn_count",
        "executed_commands",
    }:
        raise EphemeralWorkerError("economy_observation has an unexpected shape")
    if observation["schema_version"] != "abyss_delegation_economy_observation_v1":
        raise EphemeralWorkerError("economy_observation schema version is unsupported")
    if _require_nonnegative_int(observation["input_bytes"], "input_bytes") != decoded_bytes:
        raise EphemeralWorkerError("input_bytes does not match admitted records")
    if _require_nonnegative_int(observation["output_bytes"], "output_bytes") != decoded_bytes:
        raise EphemeralWorkerError("output_bytes does not match admitted records")
    if decoded_bytes > admitted_max_input_bytes:
        raise EphemeralWorkerError("input_bytes exceeds the admitted request ceiling")
    if decoded_bytes > admitted_max_output_bytes:
        raise EphemeralWorkerError("output_bytes exceeds the admitted request ceiling")
    active_wall = observation["active_wall_seconds"]
    if (
        isinstance(active_wall, bool)
        or not isinstance(active_wall, (int, float))
        or active_wall < 0
        or active_wall > MAX_ACTIVE_WALL_SECONDS
        or (isinstance(active_wall, float) and not math.isfinite(active_wall))
    ):
        raise EphemeralWorkerError("active_wall_seconds is outside the supported range")
    if (
        _require_nonnegative_int(observation["turn_count"], "turn_count") != 1
        or _require_nonnegative_int(
            observation["executed_commands"], "executed_commands"
        )
        != 0
    ):
        raise EphemeralWorkerError("economy_observation violates worker invariants")
    if result["actual_effects"] != ["read_only"]:
        raise EphemeralWorkerError("result actual effects are not read-only")
    if result["responsibility_posture"] != "parent_retained":
        raise EphemeralWorkerError("result responsibility posture is unsupported")
    if result["role_formation"] is not False:
        raise EphemeralWorkerError("ephemeral result cannot form a role")
    if result["durable_responsibility_transfer"] is not False:
        raise EphemeralWorkerError("ephemeral result cannot transfer responsibility")
    claimed_digest = _require_digest(result["result_digest"], "result_digest")
    unsigned = dict(result)
    unsigned.pop("result_digest")
    if _digest_bytes(_canonical_bytes(unsigned)) != claimed_digest:
        raise EphemeralWorkerError("result_digest does not match result content")
    canonical = _canonical_bytes(result)
    if len(canonical) > transport_ceiling:
        raise EphemeralWorkerError("encoded result exceeds max_transport_bytes ceiling")
    return json.loads(canonical)


def _adapter_profile(
    *,
    adapter_id: str,
    adapter_kind: str,
    delegation_class: str,
    command: Sequence[str],
) -> dict[str, object]:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_id": adapter_id,
        "adapter_kind": adapter_kind,
        "delegation_class": delegation_class,
        "abi_version": DELEGATION_ABI_VERSION,
        "provider_neutral_abi": True,
        "uses_builtin_codex_subagents": False,
        "enabled_by_default": False,
        "command": list(command),
    }


def ephemeral_read_worker_adapter_profile() -> dict[str, object]:
    return _adapter_profile(
        adapter_id="abyss_stack_ephemeral_read_worker_v1",
        adapter_kind="local_provider",
        delegation_class=EPHEMERAL_CLASS,
        command=("abyss-ephemeral-read-worker", "--json"),
    )


def codex_cli_adapter_profile() -> dict[str, object]:
    """First external-incarnation adapter descriptor; never a launcher."""

    return _adapter_profile(
        adapter_id="abyss_stack_codex_cli_external_incarnation_v1",
        adapter_kind="codex_cli",
        delegation_class=EXTERNAL_CLASS,
        command=("codex", "exec", "--json", "--disable", "multi_agent"),
    )


def local_provider_adapter_profile() -> dict[str, object]:
    """Provider-independent local adapter descriptor for the same ABI."""

    return _adapter_profile(
        adapter_id="abyss_stack_local_provider_external_incarnation_v1",
        adapter_kind="local_provider",
        delegation_class=EXTERNAL_CLASS,
        command=("local-provider", "--json"),
    )


def assert_external_adapter_pair(
    codex: Mapping[str, object], local: Mapping[str, object]
) -> None:
    """Fail closed unless Codex and local profiles share the exact class ABI."""

    expected_fields = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "delegation_class": EXTERNAL_CLASS,
        "abi_version": DELEGATION_ABI_VERSION,
        "provider_neutral_abi": True,
        "uses_builtin_codex_subagents": False,
        "enabled_by_default": False,
    }
    for label, profile in (("Codex", codex), ("local/provider", local)):
        if set(profile) != {
            "schema_version",
            "adapter_id",
            "adapter_kind",
            "delegation_class",
            "abi_version",
            "provider_neutral_abi",
            "uses_builtin_codex_subagents",
            "enabled_by_default",
            "command",
        }:
            raise AdapterProfileError(
                f"{label} adapter has an unexpected shape or missing identity"
            )
        for field, expected in expected_fields.items():
            if profile.get(field) != expected:
                raise AdapterProfileError(
                    f"{label} adapter has unsupported {field}"
                )
        adapter_id = profile.get("adapter_id")
        if (
            not isinstance(adapter_id, str)
            or not adapter_id
            or len(adapter_id) > MAX_STRING_LENGTH
            or re.fullmatch(r"[a-z0-9._-]+", adapter_id) is None
        ):
            raise AdapterProfileError(f"{label} adapter identity is invalid")

    common_fields = (
        "schema_version",
        "delegation_class",
        "abi_version",
        "provider_neutral_abi",
        "uses_builtin_codex_subagents",
        "enabled_by_default",
    )
    for field in common_fields:
        if codex.get(field) != local.get(field):
            raise AdapterProfileError(f"adapter pair disagrees on {field}")
    if codex.get("adapter_kind") != "codex_cli":
        raise AdapterProfileError("first adapter must be the Codex CLI")
    if local.get("adapter_kind") != "local_provider":
        raise AdapterProfileError("second adapter must be a local provider")
    if codex.get("adapter_id") == local.get("adapter_id"):
        raise AdapterProfileError("provider adapters need distinct identities")
    commands: list[tuple[str, list[str]]] = []
    for label, profile in (("Codex", codex), ("local/provider", local)):
        command = profile.get("command")
        if (
            not isinstance(command, Sequence)
            or isinstance(command, (str, bytes))
            or not command
            or any(not isinstance(token, str) or not token for token in command)
        ):
            raise AdapterProfileError(f"{label} adapter command surface is invalid")
        tokens = list(command)
        if any("spawn_agent" in token for token in tokens):
            raise AdapterProfileError("built-in Codex child agents are forbidden")
        for index, token in enumerate(tokens):
            if token == "multi_agent":
                if index == 0 or tokens[index - 1] != "--disable":
                    raise AdapterProfileError(
                        "multi_agent must be explicitly disabled with --disable"
                    )
            elif "multi_agent" in token and token != "--disable=multi_agent":
                raise AdapterProfileError("adapter command surface enables multi_agent")
        commands.append((label, tokens))
    codex_command = commands[0][1]
    if codex_command != [
        "codex",
        "exec",
        "--json",
        "--disable",
        "multi_agent",
    ]:
        raise AdapterProfileError(
            "Codex CLI adapter must use the exact codex exec --json "
            "--disable multi_agent command shape"
        )
