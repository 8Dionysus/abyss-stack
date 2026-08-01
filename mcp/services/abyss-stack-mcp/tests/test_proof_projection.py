from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest

from abyss_stack_mcp.observation import _digest
from abyss_stack_mcp.proof_packet import (
    ProofPacketBindingError,
    bind_consumer_registration,
)
from abyss_stack_mcp.proof_projection import (
    CentralProofProjectionError,
    project_central_proof,
)
from test_stack_mcp import DIGEST_D, NOW, observation, subject


def _write(path: Path, payload: dict, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(mode)
    return path


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _axis(kind: str, revision: str, ref: str) -> dict:
    return {
        "state": "asserted",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "evidence_ref": ref,
        "evidence_kind": kind,
        "revision": revision,
    }


def _inputs(tmp_path: Path) -> dict[str, Path]:
    live_subject = subject()
    live_subject["proof"] = {
        "verdict": "unknown",
        "proof_ref": None,
        "evaluated_at": None,
        "proved_source_revision": None,
        "proved_source_tree_digest": None,
        "proved_package_digest": None,
        "proved_deploy_revision": None,
        "proved_deploy_tree_digest": None,
        "proved_deploy_manifest_digest": None,
        "proved_process_identity": None,
        "proved_server_schema_digest": None,
        "proved_consumer_registration_ref": None,
        "proved_canary_route": None,
        "proved_canary_ref": None,
        "evidence": {
            "state": "unknown",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "evidence_refs": [],
            "reason_codes": ["central-proof-unobserved"],
        },
    }
    live_subject["acceptance"] = {
        "accepted": False,
        "acceptance_ref": None,
        "accepted_at": None,
        "accepted_source_revision": None,
        "accepted_package_digest": None,
        "evidence": {
            "state": "unknown",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "evidence_refs": [],
            "reason_codes": ["owner-acceptance-unobserved"],
        },
    }
    owner_review_ref = "receipt://aoa-kag/owner-result-review"
    live_subject["canary"]["evidence"]["evidence_refs"].append(
        {
            "owner": "aoa-kag",
            "evidence_ref": owner_review_ref,
            "revision": "owner-review-rev-1",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        }
    )
    live_subject["freshness"]["evidence_refs"] = [
        live_subject["canary"]["evidence"]["evidence_refs"][1]
    ]
    observation_path = _write(
        tmp_path / "observation.json", observation(live_subject)
    )

    source_revision = "source:source-rev-1"
    package_revision = "package:" + live_subject["package"]["artifact_digest"]
    deploy_revision = "deploy:" + live_subject["deploy"]["manifest_digest"]
    schema_revision = "consumer-schema:" + DIGEST_D
    canary_ref = live_subject["canary"]["canary_ref"]
    registration_ref = live_subject["consumers"][0]["registration_ref"]
    packet = {
        "schema_version": "organ_access_proof_packet_v1",
        "packet_id": "live.aoa-kag.read.test",
        "organ_id": "aoa-kag",
        "capability_id": "knowledge-retrieval",
        "policy_plane": "read",
        "protocol_pair": {
            "consumer": "codex-main",
            "server": "aoa-kag-mcp@0.1.0",
            "transport": "streamable-http",
        },
        "observation_window": {
            "started_at": NOW.isoformat(),
            "ended_at": (NOW + timedelta(minutes=4)).isoformat(),
        },
        "owners": {
            "source": "aoa-kag",
            "access": "aoa-kag",
            "control": "aoa-sdk",
            "runtime": "abyss-stack",
            "proof": "aoa-evals",
            "acceptance": "aoa-kag",
        },
        "revisions": {
            "source": source_revision,
            "package": package_revision,
            "deploy": deploy_revision,
            "consumer_schema": schema_revision,
        },
        "maturity": {
            "declared": _axis("source_declaration", source_revision, "owner://aoa-kag/source"),
            "owner_reviewed": {"state": "not_asserted"},
            "packaged": _axis("package_receipt", package_revision, live_subject["deploy"]["manifest_ref"]),
            "exported": _axis("export_receipt", package_revision, live_subject["deploy"]["manifest_ref"]),
            "deployed": _axis("deploy_receipt", deploy_revision, live_subject["deploy"]["manifest_ref"]),
            "process_alive": _axis("process_observation", deploy_revision, live_subject["process"]["process_identity"]),
            "endpoint_ready": _axis("endpoint_probe", deploy_revision, canary_ref + "#endpoint"),
            "registry_indexed": _axis("registry_observation", deploy_revision, "registry://aoa-kag"),
            "consumer_registered": _axis("consumer_registration", schema_revision, registration_ref),
            "schema_observed": _axis("consumer_schema_observation", schema_revision, canary_ref + "#server-schema"),
            "call_succeeded": _axis("call_receipt", deploy_revision, canary_ref + "#call"),
            "result_grounded": _axis("owner_grounding_review", source_revision, owner_review_ref + "#grounding"),
            "freshness_satisfied": _axis("freshness_review", deploy_revision, owner_review_ref + "#freshness"),
            "owner_accepted": {"state": "not_asserted"},
            "cross_organ_proven": {"state": "not_asserted"},
            "rollback_proven": {"state": "not_asserted"},
        },
        "result": {
            "verdict": "insufficient_evidence",
            "admission_change_authorized": False,
            "owner_acceptance_inferred": False,
            "higher_effect_authorized": False,
            "limitations": ["Owner acceptance and rollback remain separate gates."],
        },
    }
    packet_path = _write(tmp_path / "packet.json", packet)

    eval_root = tmp_path / "eval"
    (eval_root / "schemas").mkdir(parents=True)
    (eval_root / "EVAL.md").write_text("# bounded eval\n", encoding="utf-8")
    (eval_root / "eval.yaml").write_text("name: bounded\n", encoding="utf-8")
    (eval_root / "schemas" / "organ-access-proof-packet.schema.json").write_text(
        "{}\n", encoding="utf-8"
    )
    report = {
        "schema_version": "aoa_organ_access_packet_review_v1",
        "eval_name": "aoa-organ-access-admission-integrity",
        "bundle_status": "bounded",
        "reviewed_at": (NOW + timedelta(minutes=5)).isoformat(),
        "packet": {
            "packet_ref": packet_path.absolute().as_posix(),
            "packet_digest": _digest(packet),
            "packet_id": packet["packet_id"],
            "organ_id": packet["organ_id"],
            "capability_id": packet["capability_id"],
            "result_verdict": packet["result"]["verdict"],
        },
        "source_contract": {
            "eval_ref": "evals/boundary/aoa-organ-access-admission-integrity/EVAL.md",
            "eval_digest": _file_digest(eval_root / "EVAL.md"),
            "manifest_ref": "evals/boundary/aoa-organ-access-admission-integrity/eval.yaml",
            "manifest_digest": _file_digest(eval_root / "eval.yaml"),
            "packet_schema_ref": "evals/boundary/aoa-organ-access-admission-integrity/schemas/organ-access-proof-packet.schema.json",
            "packet_schema_digest": _file_digest(eval_root / "schemas" / "organ-access-proof-packet.schema.json"),
        },
        "packet_validation": {"accepted_by_source_contract": True, "issues": []},
        "negative_suite": {
            "verdict": "supports bounded claim",
            "scenario_count": 11,
            "passed_count": 11,
            "failed_count": 0,
            "report_digest": "sha256:" + "1" * 64,
        },
        "verdict": "supported_bounded",
        "central_proof_asserted": True,
        "owner_acceptance_inferred": False,
        "admission_change_authorized": False,
        "higher_effect_authorized": False,
        "cross_organ_benefit_asserted": False,
        "rollback_proven": False,
        "actual_effects": [],
        "limitations": ["Bounded proof only."],
        "claim_limit": "No acceptance, admission, effects, cross-organ benefit, or rollback.",
    }
    review_path = _write(tmp_path / "review.json", report)
    record_root = tmp_path / "records"
    record_root.mkdir(mode=0o700)
    return {
        "review": review_path,
        "packet": packet_path,
        "observation": observation_path,
        "eval_root": eval_root,
        "record_root": record_root,
    }


def _project(paths: dict[str, Path], output: Path | None = None):
    return project_central_proof(
        review_path=paths["review"],
        packet_path=paths["packet"],
        observation_path=paths["observation"],
        eval_root=paths["eval_root"],
        record_root=paths["record_root"],
        output_path=output,
        clock=lambda: NOW + timedelta(minutes=6),
    )


def test_projects_exact_consumer_bound_proof(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    output = tmp_path / "proof.overlay.json"
    overlay, digest, record = _project(paths, output)
    proof = overlay.subjects[0].proof

    assert digest.startswith("sha256:")
    assert proof is not None and proof.verdict == "passed"
    assert proof.proved_consumer_registration_ref == "config://codex/aoa-kag"
    assert proof.proved_canary_ref == "receipt://runtime/canary"
    assert proof.evidence.evidence_refs[0].owner == "aoa-evals"
    assert output.stat().st_mode & 0o777 == 0o600
    assert record.stat().st_mode & 0o777 == 0o600


def test_binds_independent_consumer_before_eval_review(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    base = json.loads(paths["packet"].read_text(encoding="utf-8"))
    base["maturity"]["consumer_registered"] = {"state": "not_asserted"}
    _write(paths["packet"], base)
    bound_path = tmp_path / "bound-packet.json"

    bound, bound_digest = bind_consumer_registration(
        packet_path=paths["packet"],
        observation_path=paths["observation"],
        consumer_id="codex-main",
        output_path=bound_path,
    )

    assert bound_digest == _digest(bound)
    assert bound["maturity"]["consumer_registered"]["state"] == "asserted"
    assert bound["maturity"]["consumer_registered"]["evidence_ref"] == (
        "config://codex/aoa-kag"
    )
    assert bound["result"]["verdict"] == "insufficient_evidence"
    assert bound_path.stat().st_mode & 0o777 == 0o600


def test_consumer_binding_refuses_to_replace_existing_axis(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)

    with pytest.raises(ProofPacketBindingError, match="exactly not_asserted"):
        bind_consumer_registration(
            packet_path=paths["packet"],
            observation_path=paths["observation"],
            consumer_id="codex-main",
        )


def test_rejects_materializer_packet_without_consumer_axis(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    packet = json.loads(paths["packet"].read_text(encoding="utf-8"))
    packet["maturity"]["consumer_registered"] = {"state": "not_asserted"}
    _write(paths["packet"], packet)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    review["packet"]["packet_digest"] = _digest(packet)
    _write(paths["review"], review)

    with pytest.raises(CentralProofProjectionError, match="consumer_registered"):
        _project(paths)


def test_rejects_consumer_ref_not_bound_to_live_registration(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    packet = json.loads(paths["packet"].read_text(encoding="utf-8"))
    packet["maturity"]["consumer_registered"]["evidence_ref"] = "config://codex/other"
    _write(paths["packet"], packet)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    review["packet"]["packet_digest"] = _digest(packet)
    _write(paths["review"], review)

    with pytest.raises(CentralProofProjectionError, match="compatible consumer"):
        _project(paths)


def test_rejects_eval_source_contract_drift(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    (paths["eval_root"] / "EVAL.md").write_text("# changed\n", encoding="utf-8")

    with pytest.raises(CentralProofProjectionError, match="source contract"):
        _project(paths)
