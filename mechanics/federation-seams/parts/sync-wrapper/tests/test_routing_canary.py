from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-routing-canary"
SDK_REF = "b" * 40
PREDECESSOR_REF = "a" * 40
G5_AUTHORITY = {
    "archive_authorized": False,
    "canonical_producer_switch_authorized": False,
    "compatibility_window_started": False,
    "live_runtime_mutation_authorized": False,
    "predecessor_maintenance_only": False,
    "sdk_canonical": False,
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def stable_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def run_canary(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def make_fixture(tmp_path: Path) -> dict[str, str]:
    required_files = [
        "generated/aoa_router.min.json",
        "generated/task_to_surface_hints.json",
    ]
    config = tmp_path / "aoa-routing.yaml"
    config.write_text(
        "\n".join(
            [
                "layer: aoa-routing",
                "mirror_root: /app/federation/aoa-routing",
                "required_files:",
                *[f"  - {item}" for item in required_files],
                "",
            ]
        ),
        encoding="utf-8",
    )

    subject_store = tmp_path / "subject-store"
    payloads = {
        "generated/aoa_router.min.json": {
            "router_version": 1,
            "artifact_identity": {
                "owner_repo": "aoa-sdk",
                "artifact_class": "thin_routing_readmodel_bundle",
                "abi_epoch": "aoa_routing_thin_router_v1",
            },
        },
        "generated/task_to_surface_hints.json": {"version": "1", "hints": []},
    }
    files = []
    for relative, payload in payloads.items():
        path = subject_store / relative
        write_json(path, payload)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "bytes": path.stat().st_size,
                "path": relative,
                "role": "routing_readmodel",
                "sha256": f"sha256:{digest}",
                "sha256_hex": digest,
            }
        )
    files.sort(key=lambda item: item["path"])
    subject_digest = stable_digest(files)
    write_json(
        subject_store / "subject-store.json",
        {
            "schema": "abyss_machine_artifact_subject_store_v1",
            "artifact_class": "thin_routing_readmodel_bundle",
            "owner_repo": "aoa-sdk",
            "aggregate_digest": subject_digest,
            "consumer_intent": "runtime_canary",
            "files": files,
        },
    )

    record_id = "sha256:" + ("c" * 64)
    producer_admission = {
        "schema": "abyss_machine_artifact_producer_admission_v1",
        "status": "candidate_admitted",
        "owner_repo": "aoa-sdk",
        "source_ref": SDK_REF,
        "canonical_owner_repo": "aoa-routing",
        "canonical_predecessor_source_ref": PREDECESSOR_REF,
        "runtime_consumer": "abyss-stack",
        "stronger_owner": "abyss-machine",
        "provenance_state": "sdk_g5_candidate",
        "publication_posture": "non_publishing_canary",
        "single_canonical_owner": True,
        "canonical_switch_authorized": False,
        "allowed_consumer_intents": ["agent", "runtime_canary"],
        "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
        "g5_authority": dict(G5_AUTHORITY),
    }
    trust_verdict = {
        "schema": "abyss_machine_artifact_trust_gate_v1",
        "ok": True,
        "verdict": "allow",
        "artifact_class": "thin_routing_readmodel_bundle",
        "consumer_intent": "runtime_canary",
        "subject_digest": subject_digest,
        "record_id": record_id,
        "require_latest": True,
        "latest_record_id": record_id,
        "reasons": [],
        "blockers": [],
        "decision": {
            "model": "fail_closed_consumer_admission",
            "allow": True,
            "consumer_intent": "runtime_canary",
        },
        "inspected_claims": {
            "subject_identity": {
                "subject_digest_expected": subject_digest,
                "subject_digest_matched": True,
            },
            "registry_latest": {
                "required": True,
                "selected_record_is_latest": True,
            },
            "source": {
                "source_repo_matched": True,
                "source_ref_matched": True,
                "source_ref_actual": SDK_REF,
            },
            "trust_root": {
                "trust_root_mode_actual": "host_managed",
                "trust_root_mode_matched": True,
            },
            "artifact_subject_store": {
                "required": True,
                "ok": True,
                "aggregate_digest": subject_digest,
            },
        },
        "record": {
            "record_id": record_id,
            "artifact_class": "thin_routing_readmodel_bundle",
            "source_repo": "aoa-sdk",
            "source_ref": SDK_REF,
            "artifact_subjects_digest": subject_digest,
            "lifecycle_state": "manually-verified",
            "latest_eligible": True,
            "terminal_state": False,
            "verification_ok": True,
            "consumer_refs": ["abyss-stack:routing-canary"],
            "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "verified_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "artifact_subject_store": {
                "required": True,
                "ok": True,
                "aggregate_digest": subject_digest,
            },
            "producer_admission": producer_admission,
        },
    }
    trust_path = tmp_path / "trust-verdict.json"
    write_json(trust_path, trust_verdict)
    return {
        "config": str(config),
        "subject_store": str(subject_store),
        "subject_digest": subject_digest,
        "trust_verdict": str(trust_path),
    }


def exact_args(fixture: dict[str, str], target: Path) -> list[str]:
    return [
        "--subject-store",
        fixture["subject_store"],
        "--trust-verdict",
        fixture["trust_verdict"],
        "--target-root",
        str(target),
        "--sdk-source-ref",
        SDK_REF,
        "--predecessor-source-ref",
        PREDECESSOR_REF,
        "--subject-digest",
        fixture["subject_digest"],
        "--routing-config",
        fixture["config"],
    ]


def test_isolated_canary_materializes_and_checks_exact_candidate(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "isolated" / "aoa-routing"

    materialized = run_canary(["materialize", *exact_args(fixture, target), "--isolated"])
    assert materialized.returncode == 0, materialized.stderr + materialized.stdout
    payload = json.loads(materialized.stdout)
    assert payload["ok"] is True
    assert payload["activation_mode"] == "isolated"
    assert payload["closure_authorized"] is False
    assert all(value is False for value in payload["g5_authority"].values())

    checked = run_canary(["check", *exact_args(fixture, target)])
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert json.loads(checked.stdout)["posture"] == "sdk_g5_candidate_canary"

    manifest = json.loads(
        (target / "manifest" / "federation_mirror_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["candidate_producer"]["owner_repo"] == "aoa-sdk"
    assert manifest["canonical_producer"]["owner_repo"] == "aoa-routing"
    assert manifest["mirror_is_authority"] is False

    router_path = target / "generated" / "aoa_router.min.json"
    router_path.write_text('{"tampered":true}\n', encoding="utf-8")
    manifest["file_sha256"][
        "generated/aoa_router.min.json"
    ] = hashlib.sha256(router_path.read_bytes()).hexdigest()
    write_json(
        target / "manifest" / "federation_mirror_manifest.json",
        manifest,
    )
    rebound = run_canary(["check", *exact_args(fixture, target)])
    assert rebound.returncode == 1
    assert "subject-store ledger" in json.loads(rebound.stdout)["error"]


def test_isolated_canary_rejects_live_target_shape(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"

    result = run_canary(
        ["materialize", *exact_args(fixture, target), "--isolated"]
    )

    assert result.returncode == 1
    assert "requires --authorized-live-canary" in json.loads(result.stdout)[
        "error"
    ]
    assert not target.exists()


def test_canary_rejects_any_asserted_g5_authority(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    trust_path = Path(fixture["trust_verdict"])
    trust = json.loads(trust_path.read_text(encoding="utf-8"))
    trust["record"]["producer_admission"]["g5_authority"]["sdk_canonical"] = True
    write_json(trust_path, trust)

    result = run_canary(
        [
            "materialize",
            *exact_args(fixture, tmp_path / "isolated" / "aoa-routing"),
            "--isolated",
        ]
    )

    assert result.returncode == 1
    assert "asserts forbidden authority" in json.loads(result.stdout)["error"]


def test_live_canary_activation_and_rollback_preserve_both_trees(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime" / "Knowledge" / "federation" / "aoa-routing"
    target.mkdir(parents=True)
    (target / "canonical.txt").write_text("predecessor\n", encoding="utf-8")
    rollback_root = target.parent / "aoa-routing.pre-canary"

    activated = run_canary(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-canary",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-change-record",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout
    assert rollback_root.joinpath("canonical.txt").read_text() == "predecessor\n"
    assert not target.joinpath("canonical.txt").exists()

    Path(fixture["trust_verdict"]).unlink()
    (
        target / "manifest" / "federation_mirror_manifest.json"
    ).write_text("{corrupted canary manifest\n", encoding="utf-8")
    retained = target.parent / "aoa-routing.sdk-canary-retained"
    restored = run_canary(
        [
            "rollback",
            "--authorized-live-canary",
            "--target-root",
            str(target),
            "--rollback-root",
            str(rollback_root),
            "--candidate-retain-root",
            str(retained),
            "--sdk-source-ref",
            SDK_REF,
            "--predecessor-source-ref",
            PREDECESSOR_REF,
            "--subject-digest",
            fixture["subject_digest"],
            "--operator-change-ref",
            "test-change-record",
        ]
    )
    assert restored.returncode == 0, restored.stderr + restored.stdout
    restored_payload = json.loads(restored.stdout)
    assert restored_payload["candidate_identity_inspection"]["verified"] is False
    assert target.joinpath("canonical.txt").read_text(encoding="utf-8") == "predecessor\n"
    assert retained.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()
