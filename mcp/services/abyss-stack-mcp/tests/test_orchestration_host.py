from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from abyss_stack_mcp.orchestration import (
    CrossOrganHost,
    CrossOrganHostError,
    CrossOrganRunStore,
    OwnerStagePacket,
    SDKCommandResult,
    _digest,
)


NOW = datetime(2026, 7, 28, 20, 0, tzinfo=timezone.utc)
DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)
DIGEST_C = "sha256:" + ("c" * 64)


def write_private(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def schema(owner: str, version: str, digest: str) -> dict:
    return {
        "owner": owner,
        "schema_ref": f"schema://{owner}/{version}",
        "schema_digest": digest,
        "source_revision": f"{owner}-revision",
        "schema_version": version,
    }


def request() -> dict:
    intent_schema = schema("abyss-stack", "intent-v1", DIGEST_A)
    contracts = [
        {
            "stage_kind": "kag_evidence",
            "owner": "aoa-kag",
            "input_ref_kind": "orchestration_intent",
            "output_ref_kind": "kag_evidence",
            "output_schema": schema("aoa-kag", "kag-v1", DIGEST_B),
            "authority_ceiling": "read",
            "effect_class": "observe",
            "next_owner": "aoa-memo",
        },
        {
            "stage_kind": "memo_candidate",
            "owner": "aoa-memo",
            "input_ref_kind": "kag_evidence",
            "output_ref_kind": "memo_candidate",
            "output_schema": schema("aoa-memo", "memo-v1", DIGEST_C),
            "authority_ceiling": "candidate",
            "effect_class": "prepare_candidate",
            "next_owner": "aoa-evals",
        },
    ]
    return {
        "schema_version": "aoa_cross_organ_orchestration_request_v1",
        "request_id": "host-runtime-test",
        "intent": "Prove host-visible receipt and persistence boundaries.",
        "requested_by": "test",
        "host_id": "abyss-stack-test-host",
        "owners": {
            "evidence_owner": "aoa-kag",
            "memory_owner": "aoa-memo",
            "proof_owner": "aoa-evals",
            "acceptance_owner": "aoa-memo",
            "control_owner": "aoa-sdk",
            "runtime_owner": "abyss-stack",
        },
        "root_input": {
            "ref_kind": "orchestration_intent",
            "owner": "abyss-stack",
            "artifact_ref": "test://intent/1",
            "artifact_digest": DIGEST_A,
            "source_revision": "abyss-stack-revision",
            "schema_identity": intent_schema,
            "authority_ceiling": "read",
            "created_at": (NOW - timedelta(minutes=1)).isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        },
        "stage_contracts": contracts,
        "evidence_refs": [
            {
                "owner": "abyss-stack",
                "evidence_ref": "test://request/1",
                "revision": "abyss-stack-revision",
                "observed_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            }
        ],
        "created_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "hidden_shared_context_allowed": False,
        "hidden_server_chaining_allowed": False,
        "automatic_candidate_promotion_allowed": False,
        "automatic_acceptance_allowed": False,
        "model_confidence_is_acceptance_authority": False,
        "host_visible_receipts_required": True,
    }


class FakeSDK:
    def __call__(self, command: tuple[str, ...], _cwd: Path) -> SDKCommandResult:
        if "orchestration-start" in command:
            request_path = Path(command[command.index("orchestration-start") + 1])
            output = Path(command[command.index("--output") + 1])
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
            run_id = _digest({"request": request_payload})
            run = {
                "schema_version": "aoa_cross_organ_orchestration_run_v1",
                "run_id": run_id,
                "request_digest": _digest(request_payload),
                "request": request_payload,
                "stages": [],
                "snapshot_digest": _digest(
                    {"run_id": run_id, "stage_count": 0}
                ),
                "state": "awaiting_kag_evidence",
                "next_stage_kind": "kag_evidence",
                "next_owner": "aoa-kag",
                "stop_reason_codes": [],
                "owner_tools_executed_by_sdk": False,
                "proof_computed_by_sdk": False,
                "durable_memory_written_by_sdk": False,
                "acceptance_inferred_by_sdk": False,
                "runtime_execution_authorized": False,
            }
            write_private(output, run)
            return SDKCommandResult(0, '{"written": true}', "")
        if "orchestration-advance" in command:
            index = command.index("orchestration-advance")
            run_path = Path(command[index + 1])
            observation_path = Path(command[index + 2])
            output = Path(command[command.index("--output") + 1])
            run = json.loads(run_path.read_text(encoding="utf-8"))
            observation = json.loads(
                observation_path.read_text(encoding="utf-8")
            )
            run["stages"].append(
                {
                    "schema_version": "aoa_cross_organ_stage_v1",
                    "sequence": len(run["stages"]),
                    "previous_stage_digest": None,
                    "stage_digest": _digest(observation),
                    "observation": observation,
                }
            )
            if observation["transition_state"] == "proceed":
                run["state"] = "awaiting_memo_candidate"
                run["next_stage_kind"] = "memo_candidate"
                run["next_owner"] = "aoa-memo"
            run["snapshot_digest"] = _digest(
                {
                    "run_id": run["run_id"],
                    "stage_count": len(run["stages"]),
                    "output": observation["output_ref"]["artifact_digest"],
                }
            )
            write_private(output, run)
            return SDKCommandResult(0, '{"written": true}', "")
        if "orchestration-validate" in command:
            path = Path(command[command.index("orchestration-validate") + 1])
            run = json.loads(path.read_text(encoding="utf-8"))
            return SDKCommandResult(
                0,
                json.dumps(
                    {
                        "valid": True,
                        "run_id": run["run_id"],
                        "snapshot_digest": run["snapshot_digest"],
                        "state": run["state"],
                        "stage_count": len(run["stages"]),
                        "next_stage_kind": run["next_stage_kind"],
                        "next_owner": run["next_owner"],
                        "owner_tools_executed_by_sdk": False,
                        "proof_computed_by_sdk": False,
                        "durable_memory_written_by_sdk": False,
                        "acceptance_inferred_by_sdk": False,
                    }
                ),
                "",
            )
        return SDKCommandResult(2, "", "unexpected command")


def host(tmp_path: Path) -> CrossOrganHost:
    return CrossOrganHost(
        run_root=tmp_path / "runs",
        sdk_command=("fake-sdk",),
        sdk_root=tmp_path,
        runner=FakeSDK(),
        clock=lambda: NOW + timedelta(minutes=5),
    )


def stage_packet() -> dict:
    return {
        "schema_version": "abyss_stack_owner_stage_packet_v1",
        "stage_kind": "kag_evidence",
        "stage_owner": "aoa-kag",
        "source_revision": "aoa-kag-revision",
        "output_ref": {
            "ref_kind": "kag_evidence",
            "owner": "aoa-kag",
            "artifact_ref": "test://aoa-kag/evidence/1",
            "artifact_digest": DIGEST_B,
            "source_revision": "aoa-kag-revision",
            "schema_identity": schema("aoa-kag", "kag-v1", DIGEST_B),
            "authority_ceiling": "read",
            "created_at": (NOW + timedelta(minutes=1)).isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        },
        "output_schema_identity": schema("aoa-kag", "kag-v1", DIGEST_B),
        "evidence_refs": [
            {
                "owner": "aoa-kag",
                "evidence_ref": "test://aoa-kag/evidence/1",
                "revision": "aoa-kag-revision",
                "observed_at": (NOW + timedelta(minutes=1)).isoformat(),
                "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            }
        ],
        "freshness_state": "exact",
        "observed_at": (NOW + timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "authority_ceiling": "read",
        "effect_class": "observe",
        "applied_state": "not_applied",
        "next_owner": "aoa-memo",
        "transition_state": "proceed",
        "stop_reason_codes": [],
        "review_ref": None,
        "acceptance_decision": None,
        "owner_receipt_refs": [],
    }


def test_host_persists_sdk_validated_start_and_bounded_inspection(
    tmp_path: Path,
) -> None:
    request_path = write_private(tmp_path / "request.json", request())

    record = host(tmp_path).start(request_path)
    inspected = CrossOrganRunStore(tmp_path / "runs").inspect(record.run_id)

    assert inspected["state"] == "awaiting_kag_evidence"
    assert inspected["stage_count"] == 0
    assert inspected["next_owner"] == "aoa-kag"
    assert inspected["sdk_validation"]["valid"] is True
    assert inspected["owner_tools_executed_by_stack"] is False
    assert inspected["runtime_execution_authorized"] is False


def test_host_issues_content_addressed_receipt_before_sdk_advance(
    tmp_path: Path,
) -> None:
    request_path = write_private(tmp_path / "request.json", request())
    runtime = host(tmp_path)
    started = runtime.start(request_path)
    packet_path = write_private(tmp_path / "stage.json", stage_packet())

    advanced = runtime.advance(started.run_id, packet_path)
    inspected = CrossOrganRunStore(tmp_path / "runs").inspect(started.run_id)
    receipt_path = tmp_path / "runs" / str(inspected["latest_host_receipt_ref"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected_digest = _digest(
        {
            key: value
            for key, value in receipt.items()
            if key != "receipt_digest"
        }
    )

    assert advanced.state == "awaiting_memo_candidate"
    assert advanced.stage_count == 1
    assert receipt["receipt_digest"] == expected_digest
    assert receipt["run_id"] == started.run_id
    assert receipt["previous_snapshot_digest"] == started.snapshot_digest
    assert receipt["input_artifact_digest"] == DIGEST_A
    assert receipt["output_artifact_digest"] == DIGEST_B
    assert receipt["outcome"] == "observed"


def test_store_rejects_snapshot_drift(tmp_path: Path) -> None:
    request_path = write_private(tmp_path / "request.json", request())
    record = host(tmp_path).start(request_path)
    snapshot = tmp_path / "runs" / record.snapshot_ref
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    payload["next_owner"] = "foreign-owner"
    write_private(snapshot, payload)

    with pytest.raises(CrossOrganHostError, match="file drifted"):
        CrossOrganRunStore(tmp_path / "runs").inspect(record.run_id)


def test_store_rejects_symlinked_current_record(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    run_root.mkdir(mode=0o700)
    foreign = write_private(tmp_path / "foreign.json", {"foreign": True})
    (run_root / "current.json").symlink_to(foreign)

    with pytest.raises(CrossOrganHostError, match="symlink"):
        CrossOrganRunStore(run_root).inspect()


def test_host_rejects_group_readable_request(tmp_path: Path) -> None:
    request_path = write_private(tmp_path / "request.json", request())
    request_path.chmod(0o640)

    with pytest.raises(CrossOrganHostError, match="group/world accessible"):
        host(tmp_path).start(request_path)


def test_host_rejects_naive_persistence_clock(tmp_path: Path) -> None:
    request_path = write_private(tmp_path / "request.json", request())
    runtime = CrossOrganHost(
        run_root=tmp_path / "runs",
        sdk_command=("fake-sdk",),
        sdk_root=tmp_path,
        runner=FakeSDK(),
        clock=lambda: NOW.replace(tzinfo=None),
    )

    with pytest.raises(CrossOrganHostError, match="timezone-aware"):
        runtime.start(request_path)


class FailedSDK:
    def __call__(
        self,
        _command: tuple[str, ...],
        _cwd: Path,
    ) -> SDKCommandResult:
        return SDKCommandResult(71, "", "bounded SDK failure")


def test_host_does_not_persist_failed_sdk_start(tmp_path: Path) -> None:
    request_path = write_private(tmp_path / "request.json", request())
    run_root = tmp_path / "runs"
    runtime = CrossOrganHost(
        run_root=run_root,
        sdk_command=("failed-sdk",),
        sdk_root=tmp_path,
        runner=FailedSDK(),
        clock=lambda: NOW,
    )

    with pytest.raises(CrossOrganHostError, match="return code 71"):
        runtime.start(request_path)

    assert not (run_root / "current.json").exists()


def test_owner_receipt_refs_use_sdk_canonical_timestamp_shape() -> None:
    packet = stage_packet()
    packet["owner_receipt_refs"] = [packet["output_ref"]]

    parsed = OwnerStagePacket.model_validate(packet)
    normalized = parsed.owner_receipt_refs[0].model_dump(mode="json")

    assert normalized["created_at"].endswith("Z")
    assert normalized["expires_at"].endswith("Z")
