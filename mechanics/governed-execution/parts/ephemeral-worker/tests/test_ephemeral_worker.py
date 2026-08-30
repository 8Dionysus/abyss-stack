from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import UserDict
from pathlib import Path

import jsonschema
import pytest

PART_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PART_ROOT))

from ephemeral_worker import (
    MAX_ACTIVE_WALL_SECONDS,
    MAX_ACTIVE_WALL_RENDER_BYTES,
    MAX_BYTE_CEILING,
    MAX_INPUT_COUNT,
    MAX_STRING_LENGTH,
    AdapterProfileError,
    EphemeralWorkerDisabled,
    EphemeralWorkerError,
    assert_external_adapter_pair,
    codex_cli_adapter_profile,
    ephemeral_read_worker_adapter_profile,
    local_provider_adapter_profile,
    run_ephemeral_read_worker,
    snapshot_digest_for_request,
    validate_ephemeral_read_result,
    _projected_result_base_bytes,
    _normalize_json_value,
)

REQUEST_SCHEMA = PART_ROOT / "schemas/ephemeral-read-worker-request.schema.json"
RESULT_SCHEMA = PART_ROOT / "schemas/ephemeral-read-worker-result.schema.json"
ADAPTER_SCHEMA = PART_ROOT / "schemas/delegation-adapter-profile.schema.json"
PROFILE_DIR = PART_ROOT / "profiles"
ZERO_DIGEST = "sha256:" + "0" * 64


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _resign_result(result: dict[str, object]) -> None:
    unsigned = dict(result)
    unsigned.pop("result_digest")
    result["result_digest"] = _digest(
        json.dumps(
            unsigned,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _request(
    path: Path,
    content: bytes,
    *,
    activation: str = "explicit",
    max_transport_bytes: int = 4096,
) -> dict[str, object]:
    inputs = [
        {
            "artifact_ref": "fixture/input.txt",
            "path": str(path),
            "digest": _digest(content),
            "max_bytes": max(1, len(content)),
        }
    ]
    return {
        "schema_version": "abyss_ephemeral_read_worker_request_v1",
        "request_id": "request:fixture",
        "delegation_class": "ephemeral_read_worker_v1",
        "activation": activation,
        "parent_holder_ref": {
            "object_id": "holder:fixture",
            "owner_repo": "aoa-agents",
            "schema_version": "holder-v1",
            "digest": ZERO_DIGEST,
        },
        "input_snapshot_digest": snapshot_digest_for_request(
            inputs,
            max_input_bytes=len(content),
            max_output_bytes=len(content),
            max_transport_bytes=max_transport_bytes,
        ),
        "inputs": inputs,
        "max_input_bytes": len(content),
        "max_output_bytes": len(content),
        "max_transport_bytes": max_transport_bytes,
    }


def _validate(path: Path, payload: dict[str, object]) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(payload))
    assert errors == []


def test_worker_is_disabled_until_explicitly_activated(tmp_path: Path) -> None:
    content = b"bounded read\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content, activation="disabled")
    _validate(REQUEST_SCHEMA, request)

    with pytest.raises(EphemeralWorkerDisabled, match="disabled by default"):
        run_ephemeral_read_worker(request)


def test_explicit_worker_returns_bounded_parent_retained_result(tmp_path: Path) -> None:
    content = b"bounded read\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)

    _validate(RESULT_SCHEMA, result)
    assert result["delegation_class"] == "ephemeral_read_worker_v1"
    assert result["actual_effects"] == ["read_only"]
    assert result["responsibility_posture"] == "parent_retained"
    assert result["role_formation"] is False
    assert result["durable_responsibility_transfer"] is False
    assert result["economy_observation"]["input_bytes"] == len(content)  # type: ignore[index]
    assert result["economy_observation"]["executed_commands"] == 0  # type: ignore[index]

    result_digest_with_newline = dict(result)
    result_digest_with_newline["result_digest"] = (
        str(result["result_digest"]) + "\n"
    )
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(result_digest_with_newline)
    )

    without_digest = dict(result)
    digest = without_digest.pop("result_digest")
    expected = _digest(
        json.dumps(
            without_digest,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    assert digest == expected
    assert validate_ephemeral_read_result(result, admitted_request=request) == result


@pytest.mark.parametrize("field", ["bytes", "digest", "result_digest"])
def test_result_intake_rejects_corrupted_content_address(
    tmp_path: Path,
    field: str,
) -> None:
    content = b"content-addressed result\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)
    corrupted = json.loads(json.dumps(result))
    if field == "bytes":
        corrupted["records"][0]["bytes"] += 1
    elif field == "digest":
        corrupted["records"][0]["digest"] = ZERO_DIGEST
    else:
        corrupted["result_digest"] = ZERO_DIGEST

    with pytest.raises(EphemeralWorkerError, match="does not match|exceeds"):
        validate_ephemeral_read_result(corrupted, admitted_request=request)


def test_result_intake_binds_records_to_exact_admitted_snapshot(tmp_path: Path) -> None:
    expected_content = b"expected input\n"
    expected_path = tmp_path / "expected.txt"
    expected_path.write_bytes(expected_content)
    admitted_request = _request(expected_path, expected_content)
    admitted_result = run_ephemeral_read_worker(admitted_request)

    with pytest.raises(EphemeralWorkerError, match="exact admitted request"):
        validate_ephemeral_read_result(admitted_result)

    substituted_content = b"self-consistent but unrequested input\n"
    substituted_path = tmp_path / "substituted.txt"
    substituted_path.write_bytes(substituted_content)
    substituted_request = _request(substituted_path, substituted_content)
    substituted_result = run_ephemeral_read_worker(substituted_request)
    substituted_result["input_snapshot_digest"] = admitted_request[
        "input_snapshot_digest"
    ]
    _resign_result(substituted_result)

    with pytest.raises(EphemeralWorkerError, match="admitted input snapshot"):
        validate_ephemeral_read_result(
            substituted_result,
            admitted_request=admitted_request,
        )


def test_result_intake_enforces_output_ceiling_before_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x" * 4096
    path = tmp_path / "alternate-output.bin"
    path.write_bytes(content)
    producer_request = _request(path, content, max_transport_bytes=8192)
    producer_result = run_ephemeral_read_worker(producer_request)
    admitted_request = _request(path, content, max_transport_bytes=8192)
    admitted_request["max_output_bytes"] = 1
    admitted_request["input_snapshot_digest"] = snapshot_digest_for_request(
        admitted_request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=admitted_request["max_input_bytes"],
        max_output_bytes=admitted_request["max_output_bytes"],
        max_transport_bytes=admitted_request["max_transport_bytes"],
    )
    producer_result["input_snapshot_digest"] = admitted_request[
        "input_snapshot_digest"
    ]
    _resign_result(producer_result)

    def unexpected_decode(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("output overflow must reject before base64 decoding")

    worker_base64 = validate_ephemeral_read_result.__globals__["base64"]
    monkeypatch.setattr(worker_base64, "b64decode", unexpected_decode)

    with pytest.raises(EphemeralWorkerError, match="before decode"):
        validate_ephemeral_read_result(
            producer_result,
            admitted_request=admitted_request,
        )


def test_result_intake_bounds_serialized_packet_before_parse() -> None:
    with pytest.raises(EphemeralWorkerError, match="before parse"):
        validate_ephemeral_read_result(b" " * 65, max_transport_bytes=64)


def test_result_intake_bounds_text_before_full_utf8_allocation() -> None:
    class EncodeForbidden(str):
        def encode(self, *_args: object, **_kwargs: object) -> bytes:
            raise AssertionError("oversized text must be rejected before encoding")

    with pytest.raises(EphemeralWorkerError, match="before parse"):
        validate_ephemeral_read_result(
            EncodeForbidden("x" * 65), max_transport_bytes=64
        )

    with pytest.raises(EphemeralWorkerError, match="before parse"):
        validate_ephemeral_read_result("😀" * 20, max_transport_bytes=64)


def test_result_intake_bounds_mapped_base64_before_decode(tmp_path: Path) -> None:
    content = b"mapped transport ceiling"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)

    with pytest.raises(EphemeralWorkerError, match="before validation"):
        validate_ephemeral_read_result(
            result, admitted_request=request, max_transport_bytes=8
        )


def test_result_intake_counts_mapped_metadata_before_record_validation(
    tmp_path: Path,
) -> None:
    content = b"x"
    path = tmp_path / "small.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)
    result["records"][0]["artifact_ref"] = "a" * 4096  # type: ignore[index]
    _resign_result(result)

    with pytest.raises(EphemeralWorkerError, match="before validation"):
        validate_ephemeral_read_result(
            result, admitted_request=request, max_transport_bytes=512
        )


def test_result_intake_accepts_schema_valid_integral_counters(tmp_path: Path) -> None:
    content = b"integral result counters"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)
    result["records"][0]["bytes"] = float(len(content))  # type: ignore[index]
    result["economy_observation"]["input_bytes"] = float(len(content))  # type: ignore[index]
    result["economy_observation"]["output_bytes"] = float(len(content))  # type: ignore[index]
    _resign_result(result)
    _validate(RESULT_SCHEMA, result)

    assert validate_ephemeral_read_result(result, admitted_request=request) == result


def test_result_intake_rejects_boolean_counters_and_unbounded_wall_time(
    tmp_path: Path,
) -> None:
    content = b"economy counter bounds"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)

    boolean_counter = json.loads(json.dumps(result))
    boolean_counter["economy_observation"]["turn_count"] = True
    _resign_result(boolean_counter)
    with pytest.raises(EphemeralWorkerError, match="turn_count"):
        validate_ephemeral_read_result(boolean_counter, admitted_request=request)

    huge_wall = json.loads(json.dumps(result))
    huge_wall["economy_observation"]["active_wall_seconds"] = (
        MAX_ACTIVE_WALL_SECONDS + 1
    )
    _resign_result(huge_wall)
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(huge_wall)
    )
    with pytest.raises(EphemeralWorkerError, match="supported range"):
        validate_ephemeral_read_result(huge_wall, admitted_request=request)


def test_result_intake_normalizes_unencodable_text_to_worker_error() -> None:
    with pytest.raises(EphemeralWorkerError, match="UTF-8"):
        validate_ephemeral_read_result("\ud800")


def test_result_intake_normalizes_nested_mapping_implementations(
    tmp_path: Path,
) -> None:
    content = b"mapping normalization"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)
    mapped = UserDict(result)
    mapped["parent_holder_ref"] = UserDict(result["parent_holder_ref"])  # type: ignore[arg-type]
    mapped["records"] = [UserDict(record) for record in result["records"]]  # type: ignore[union-attr]
    mapped["economy_observation"] = UserDict(result["economy_observation"])  # type: ignore[arg-type]

    assert validate_ephemeral_read_result(mapped, admitted_request=request) == result


def test_result_intake_bounds_mapping_normalization(tmp_path: Path) -> None:
    content = b"bounded mapping normalization"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    result = run_ephemeral_read_worker(request)

    cyclic = UserDict(result)
    cyclic["records"] = [cyclic]
    with pytest.raises(EphemeralWorkerError, match="JSON cycle"):
        validate_ephemeral_read_result(cyclic, admitted_request=request)

    oversized = UserDict(result)
    oversized["records"] = [UserDict(result["records"][0])] * (MAX_INPUT_COUNT + 1)  # type: ignore[index]
    with pytest.raises(EphemeralWorkerError, match="array cardinality"):
        validate_ephemeral_read_result(oversized, admitted_request=request)

    oversized_string = UserDict(result)
    oversized_string["request_id"] = "x" * 1024
    with pytest.raises(EphemeralWorkerError, match="before serialization"):
        validate_ephemeral_read_result(
            oversized_string, admitted_request=request, max_transport_bytes=64
        )

    repeated_strings = UserDict(result)
    repeated_strings["records"] = [result["records"][0]] * 32  # type: ignore[index]
    with pytest.raises(EphemeralWorkerError, match="before serialization"):
        validate_ephemeral_read_result(
            repeated_strings, admitted_request=request, max_transport_bytes=512
        )

    with pytest.raises(EphemeralWorkerError, match="numeric scalar"):
        _normalize_json_value(
            {"numbers": [10**400] * 32},
            "result",
            _remaining_transport_bytes=[128],
        )


def test_result_intake_normalizes_oversized_json_integer_parse_failure() -> None:
    payload = '{"counter":' + ("9" * 5000) + "}"
    with pytest.raises(EphemeralWorkerError, match="canonical JSON"):
        validate_ephemeral_read_result(payload)


def test_worker_rejects_digest_drift_and_symlink_alias(tmp_path: Path) -> None:
    content = b"immutable\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    path.write_bytes(b"drifted\n")
    with pytest.raises(EphemeralWorkerError, match="digest changed"):
        run_ephemeral_read_worker(request)

    path.write_bytes(content)
    alias = tmp_path / "alias.txt"
    alias.symlink_to(path)
    alias_request = _request(alias, content)
    with pytest.raises(EphemeralWorkerError, match="must not be a symlink"):
        run_ephemeral_read_worker(alias_request)

    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    real_file = real_parent / "nested.txt"
    real_file.write_bytes(content)
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(real_parent, target_is_directory=True)
    parent_alias_request = _request(parent_alias / "nested.txt", content)
    with pytest.raises(EphemeralWorkerError, match="symlinked parent"):
        run_ephemeral_read_worker(parent_alias_request)


@pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="O_PATH is not supported")
def test_worker_traverses_execute_only_parent_with_path_descriptors(
    tmp_path: Path,
) -> None:
    content = b"execute-only parent\n"
    parent = tmp_path / "execute-only"
    parent.mkdir()
    path = parent / "input.txt"
    path.write_bytes(content)
    parent.chmod(0o111)
    try:
        result = run_ephemeral_read_worker(_request(path, content))
    finally:
        parent.chmod(0o700)

    assert result["records"][0]["bytes"] == len(content)  # type: ignore[index]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is not supported")
def test_worker_rejects_fifo_without_blocking_before_regular_file_check(
    tmp_path: Path,
) -> None:
    fifo = tmp_path / "candidate.pipe"
    os.mkfifo(fifo)
    request = _request(fifo, b"fifo")

    with pytest.raises(EphemeralWorkerError, match="regular file"):
        run_ephemeral_read_worker(request)


def test_worker_rejects_content_above_declared_byte_ceiling(tmp_path: Path) -> None:
    content = b"too-large"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    request["inputs"][0]["max_bytes"] = len(content) - 1  # type: ignore[index]
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],  # type: ignore[arg-type]
        max_output_bytes=request["max_output_bytes"],  # type: ignore[arg-type]
        max_transport_bytes=request["max_transport_bytes"],  # type: ignore[arg-type]
    )

    with pytest.raises(EphemeralWorkerError, match="byte ceiling"):
        run_ephemeral_read_worker(request)


def test_worker_rejects_oversized_byte_ceiling_before_read(tmp_path: Path) -> None:
    content = b"bounded read\n"
    request = _request(tmp_path / "not-created.txt", content)
    oversized = MAX_BYTE_CEILING + 1
    request["inputs"][0]["max_bytes"] = oversized  # type: ignore[index]
    request["max_input_bytes"] = oversized
    request["max_output_bytes"] = oversized
    request["max_transport_bytes"] = oversized
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=oversized,
        max_output_bytes=oversized,
        max_transport_bytes=oversized,
    )

    with pytest.raises(EphemeralWorkerError, match="supported byte ceiling"):
        run_ephemeral_read_worker(request)


def test_worker_accepts_schema_valid_integral_numeric_ceilings(
    tmp_path: Path,
) -> None:
    content = b"integral ceilings\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    request["inputs"][0]["max_bytes"] = float(len(content))  # type: ignore[index]
    request["max_input_bytes"] = float(len(content))
    request["max_output_bytes"] = float(len(content))
    request["max_transport_bytes"] = 4096.0
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )
    _validate(REQUEST_SCHEMA, request)

    result = run_ephemeral_read_worker(request)

    _validate(RESULT_SCHEMA, result)
    assert result["economy_observation"]["input_bytes"] == len(content)  # type: ignore[index]


def test_worker_rejects_non_integral_numeric_ceiling(tmp_path: Path) -> None:
    content = b"fractional ceiling\n"
    request = _request(tmp_path / "not-created.txt", content)
    request["max_input_bytes"] = 1.5

    with pytest.raises(EphemeralWorkerError, match="positive integer"):
        run_ephemeral_read_worker(request)


def test_request_schema_rejects_oversized_byte_ceilings(tmp_path: Path) -> None:
    content = b"bounded read\n"
    request = _request(tmp_path / "input.txt", content)
    oversized = MAX_BYTE_CEILING + 1
    request["inputs"][0]["max_bytes"] = oversized  # type: ignore[index]
    request["max_input_bytes"] = oversized
    request["max_output_bytes"] = oversized
    request["max_transport_bytes"] = oversized

    errors = list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(request)
    )
    assert errors


def test_request_bounds_input_count_and_metadata(tmp_path: Path) -> None:
    content = b"bounded read\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    oversized_inputs = [dict(request["inputs"][0]) for _ in range(MAX_INPUT_COUNT + 1)]  # type: ignore[index]
    request["inputs"] = oversized_inputs
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(request)
    )
    with pytest.raises(EphemeralWorkerError, match="supported count"):
        run_ephemeral_read_worker(request)

    for field in ("request_id",):
        oversized = dict(request)
        oversized["inputs"] = [dict(request["inputs"][0])]  # type: ignore[index]
        oversized[field] = "x" * (MAX_STRING_LENGTH + 1)
        assert list(
            jsonschema.Draft202012Validator(
                json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
            ).iter_errors(oversized)
        )
        with pytest.raises(EphemeralWorkerError, match="string length"):
            run_ephemeral_read_worker(oversized)

    for field, value in (
        ("artifact_ref", "x" * (MAX_STRING_LENGTH + 1)),
        ("path", "/" + "x" * MAX_STRING_LENGTH),
    ):
        oversized_input = dict(_request(path, content))
        oversized_input["inputs"] = [dict(oversized_input["inputs"][0])]  # type: ignore[index]
        oversized_input["inputs"][0][field] = value  # type: ignore[index]
        assert list(
            jsonschema.Draft202012Validator(
                json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
            ).iter_errors(oversized_input)
        )
        with pytest.raises(EphemeralWorkerError, match="string length"):
            run_ephemeral_read_worker(oversized_input)

    oversized_ref = dict(_request(path, content))
    oversized_ref["parent_holder_ref"] = dict(request["parent_holder_ref"])  # type: ignore[arg-type]
    oversized_ref["parent_holder_ref"]["object_id"] = "x" * (MAX_STRING_LENGTH + 1)  # type: ignore[index]
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(oversized_ref)
    )
    with pytest.raises(EphemeralWorkerError, match="string length"):
        run_ephemeral_read_worker(oversized_ref)


def test_worker_rejects_equivalent_normalized_input_paths(tmp_path: Path) -> None:
    content = b"duplicate path\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)
    second = dict(request["inputs"][0])  # type: ignore[index]
    second["artifact_ref"] = "fixture/other.txt"
    second["path"] = str(path).replace("/input.txt", "//input.txt")
    request["inputs"] = [request["inputs"][0], second]  # type: ignore[index]
    request["max_input_bytes"] = len(content) * 2
    request["max_output_bytes"] = len(content) * 2
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],  # type: ignore[arg-type]
        max_output_bytes=request["max_output_bytes"],  # type: ignore[arg-type]
        max_transport_bytes=request["max_transport_bytes"],  # type: ignore[arg-type]
    )
    with pytest.raises(EphemeralWorkerError, match="canonical components"):
        run_ephemeral_read_worker(request)


def test_worker_rejects_encoded_result_above_transport_ceiling(tmp_path: Path) -> None:
    content = b"bounded read\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)

    with pytest.raises(EphemeralWorkerError, match="max_transport_bytes"):
        run_ephemeral_read_worker(_request(path, content, max_transport_bytes=128))


def test_worker_rejects_projected_base64_before_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x" * 1024
    path = tmp_path / "large-input.bin"
    path.write_bytes(content)

    def unexpected_encode(_content: bytes) -> bytes:
        raise AssertionError("base64 allocation must not occur above transport ceiling")

    worker_base64 = run_ephemeral_read_worker.__globals__["base64"]
    monkeypatch.setattr(worker_base64, "b64encode", unexpected_encode)

    with pytest.raises(EphemeralWorkerError, match="projected result"):
        run_ephemeral_read_worker(_request(path, content, max_transport_bytes=128))


def test_worker_caps_reads_by_remaining_output_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x" * 4096
    path = tmp_path / "output-bounded.bin"
    path.write_bytes(content)
    request = _request(path, content)
    request["max_output_bytes"] = 1
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )
    worker_globals = run_ephemeral_read_worker.__globals__
    original_read = worker_globals["_read_verified"]
    observed_ceilings: list[int] = []

    def observed_read(*args: object) -> bytes:
        observed_ceilings.append(args[2])  # type: ignore[arg-type]
        return original_read(*args)

    monkeypatch.setitem(worker_globals, "_read_verified", observed_read)

    with pytest.raises(EphemeralWorkerError, match="byte ceiling"):
        run_ephemeral_read_worker(request)
    assert observed_ceilings == [1]


def test_worker_verifies_empty_input_after_output_budget_exhaustion(
    tmp_path: Path,
) -> None:
    first_content = b"x"
    first_path = tmp_path / "first.txt"
    first_path.write_bytes(first_content)
    empty_path = tmp_path / "empty.txt"
    empty_path.write_bytes(b"")
    request = _request(first_path, first_content)
    request["inputs"].append(  # type: ignore[union-attr]
        {
            "artifact_ref": "fixture/empty.txt",
            "path": str(empty_path),
            "digest": _digest(b""),
            "max_bytes": 1,
        }
    )
    request["max_input_bytes"] = 2
    request["max_output_bytes"] = 1
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )

    result = run_ephemeral_read_worker(request)

    assert [record["bytes"] for record in result["records"]] == [1, 0]  # type: ignore[union-attr]


def test_worker_caps_reads_by_remaining_transport_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x" * 4096
    path = tmp_path / "transport-bounded.bin"
    path.write_bytes(content)
    request = _request(path, content)
    projected_base = _projected_result_base_bytes(
        request["request_id"],  # type: ignore[arg-type]
        request["parent_holder_ref"],  # type: ignore[arg-type]
        request["input_snapshot_digest"],  # type: ignore[arg-type]
        request["inputs"],  # type: ignore[arg-type]
    )
    request["max_transport_bytes"] = projected_base + 8
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )
    worker_globals = run_ephemeral_read_worker.__globals__
    original_read = worker_globals["_read_verified"]
    observed_ceilings: list[int] = []

    def observed_read(*args: object) -> bytes:
        observed_ceilings.append(args[2])  # type: ignore[arg-type]
        return original_read(*args)

    monkeypatch.setitem(worker_globals, "_read_verified", observed_read)

    with pytest.raises(EphemeralWorkerError, match="byte ceiling"):
        run_ephemeral_read_worker(request)
    assert len(observed_ceilings) == 1
    assert 0 <= observed_ceilings[0] < len(content)


def test_worker_accounts_metadata_before_base64_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x"
    path = tmp_path / "metadata-heavy.txt"
    path.write_bytes(content)
    request = _request(path, content, max_transport_bytes=1024)
    request["inputs"][0]["artifact_ref"] = "a" * 900  # type: ignore[index]
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )

    def unexpected_read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("metadata overflow must reject before file I/O")

    def unexpected_encode(_content: bytes) -> bytes:
        raise AssertionError("metadata overflow must reject before base64 encoding")

    worker_globals = run_ephemeral_read_worker.__globals__
    monkeypatch.setitem(worker_globals, "_read_verified", unexpected_read)
    worker_base64 = worker_globals["base64"]
    monkeypatch.setattr(worker_base64, "b64encode", unexpected_encode)

    with pytest.raises(EphemeralWorkerError, match="projected result"):
        run_ephemeral_read_worker(request)


def test_worker_reserves_wall_time_before_base64_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"x"
    path = tmp_path / "wall-time-bound.txt"
    path.write_bytes(content)
    request = _request(path, content)
    projected_base = _projected_result_base_bytes(
        request["request_id"],  # type: ignore[arg-type]
        request["parent_holder_ref"],  # type: ignore[arg-type]
        request["input_snapshot_digest"],  # type: ignore[arg-type]
        request["inputs"],  # type: ignore[arg-type]
    )
    assert MAX_ACTIVE_WALL_RENDER_BYTES > len(b"0.0")
    request["max_transport_bytes"] = projected_base - 1
    request["input_snapshot_digest"] = snapshot_digest_for_request(
        request["inputs"],  # type: ignore[arg-type]
        max_input_bytes=request["max_input_bytes"],
        max_output_bytes=request["max_output_bytes"],
        max_transport_bytes=request["max_transport_bytes"],
    )

    def unexpected_encode(_content: bytes) -> bytes:
        raise AssertionError("wall-time overflow must reject before base64 encoding")

    worker_base64 = run_ephemeral_read_worker.__globals__["base64"]
    monkeypatch.setattr(worker_base64, "b64encode", unexpected_encode)

    with pytest.raises(EphemeralWorkerError, match="projected result"):
        run_ephemeral_read_worker(request)


def test_request_schema_matches_absolute_nul_free_runtime_paths(tmp_path: Path) -> None:
    content = b"path contract\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    request = _request(path, content)

    relative = dict(request)
    relative["inputs"] = [dict(request["inputs"][0])]  # type: ignore[index]
    relative["inputs"][0]["path"] = "relative.txt"  # type: ignore[index]
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(relative)
    )

    nul = dict(request)
    nul["inputs"] = [dict(request["inputs"][0])]  # type: ignore[index]
    nul["inputs"][0]["path"] = str(path) + "\x00suffix"  # type: ignore[index]
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(nul)
    )

    for raw_path in ("/../tmp/input.txt", "/./tmp/input.txt", "/tmp//input.txt"):
        traversal = dict(request)
        traversal["inputs"] = [dict(request["inputs"][0])]  # type: ignore[index]
        traversal["inputs"][0]["path"] = raw_path  # type: ignore[index]
        assert list(
            jsonschema.Draft202012Validator(
                json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
            ).iter_errors(traversal)
        )
        with pytest.raises(EphemeralWorkerError, match="canonical components"):
            run_ephemeral_read_worker(traversal)

    digest_with_newline = dict(request)
    digest_with_newline["input_snapshot_digest"] = (
        str(request["input_snapshot_digest"]) + "\n"
    )
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(digest_with_newline)
    )


def test_worker_normalizes_unencodable_path_to_worker_error(tmp_path: Path) -> None:
    content = b"path encoding\n"
    request = _request(tmp_path / "input.txt", content)
    request["inputs"][0]["path"] = "/tmp/\ud800"  # type: ignore[index]

    with pytest.raises(EphemeralWorkerError, match="host filesystem"):
        run_ephemeral_read_worker(request)


def test_adapter_profiles_share_abi_and_keep_builtin_transport_disabled() -> None:
    codex = codex_cli_adapter_profile()
    local = local_provider_adapter_profile()
    worker = ephemeral_read_worker_adapter_profile()

    for profile in (codex, local, worker):
        _validate(ADAPTER_SCHEMA, profile)
        assert profile["enabled_by_default"] is False
        assert profile["uses_builtin_codex_subagents"] is False
    assert_external_adapter_pair(codex, local)
    assert codex["adapter_id"] != local["adapter_id"]
    assert codex["command"][-2:] == ["--disable", "multi_agent"]
    assert worker["delegation_class"] == "ephemeral_read_worker_v1"

    invalid = dict(local)
    invalid["delegation_class"] = "ephemeral_read_worker_v1"
    with pytest.raises(AdapterProfileError, match="delegation_class"):
        assert_external_adapter_pair(codex, invalid)

    missing_identity = dict(codex)
    missing_identity.pop("adapter_id")
    with pytest.raises(AdapterProfileError, match="identity"):
        assert_external_adapter_pair(missing_identity, local)

    malformed_identity = dict(codex)
    malformed_identity["adapter_id"] = "Not Schema Conforming"
    with pytest.raises(AdapterProfileError, match="identity"):
        assert_external_adapter_pair(malformed_identity, local)

    trailing_newline_identity = dict(codex)
    trailing_newline_identity["adapter_id"] = f"{codex['adapter_id']}\n"
    assert list(
        jsonschema.Draft202012Validator(
            json.loads(ADAPTER_SCHEMA.read_text(encoding="utf-8"))
        ).iter_errors(trailing_newline_identity)
    )
    with pytest.raises(AdapterProfileError, match="identity"):
        assert_external_adapter_pair(trailing_newline_identity, local)

    unexpected = dict(codex)
    unexpected["unknown_execution_option"] = True
    with pytest.raises(AdapterProfileError, match="unexpected shape"):
        assert_external_adapter_pair(unexpected, local)

    invalid_abi_codex = dict(codex)
    invalid_abi_local = dict(local)
    invalid_abi_codex["abi_version"] = "wrong"
    invalid_abi_local["abi_version"] = "wrong"
    with pytest.raises(AdapterProfileError, match="abi_version"):
        assert_external_adapter_pair(invalid_abi_codex, invalid_abi_local)

    invalid_command = dict(codex)
    invalid_command["command"] = ["codex", "exec", "--json", "multi_agent"]
    with pytest.raises(AdapterProfileError, match="disable"):
        assert_external_adapter_pair(invalid_command, local)

    invalid_executable = dict(codex)
    invalid_executable["command"] = [
        "/bin/rm",
        "exec",
        "--json",
        "--disable",
        "multi_agent",
    ]
    with pytest.raises(AdapterProfileError, match="exact.*codex exec"):
        assert_external_adapter_pair(invalid_executable, local)


def test_checked_in_profiles_match_the_runtime_factories() -> None:
    expected = {
        "codex-cli.external-incarnation.json": codex_cli_adapter_profile(),
        "local-provider.external-incarnation.json": local_provider_adapter_profile(),
        "ephemeral-read-worker.local-provider.json": ephemeral_read_worker_adapter_profile(),
    }
    for filename, profile in expected.items():
        on_disk = json.loads((PROFILE_DIR / filename).read_text(encoding="utf-8"))
        assert on_disk == profile


def test_result_schema_requires_canonical_bounded_base64(tmp_path: Path) -> None:
    content = b"canonical base64\n"
    path = tmp_path / "input.txt"
    path.write_bytes(content)
    result = run_ephemeral_read_worker(_request(path, content))
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))

    for invalid in ("!", "YQ=", "YQ===", "Y Q==", "YQ==\n"):
        candidate = json.loads(json.dumps(result))
        candidate["records"][0]["content_base64"] = invalid
        assert list(jsonschema.Draft202012Validator(schema).iter_errors(candidate))

    oversized_metadata = json.loads(json.dumps(result))
    oversized_metadata["request_id"] = "x" * (MAX_STRING_LENGTH + 1)
    assert list(
        jsonschema.Draft202012Validator(schema).iter_errors(oversized_metadata)
    )

    too_many_records = json.loads(json.dumps(result))
    too_many_records["records"] = too_many_records["records"] * (MAX_INPUT_COUNT + 1)
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(too_many_records))
