from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from aoa_sdk.contracts.organ_admission import AdmissionDecisionStatement
from aoa_sdk.contracts.organ_registry_v2 import (
    ContourRuntimeIdentity,
    OrganContourRecord,
    OrganRecordV2,
    OrganRegistrySourceV2,
)
from aoa_sdk.contracts.organs import (
    CapabilityContract,
    EndpointContract,
    FreshnessPolicy,
    HandoffContract,
    MaturityEvidence,
    OrganMaturityVector,
    OrganOwners,
    OrganRevisions,
    PrimitiveContract,
    QualifiedEvidenceRef,
    RevisionIdentity,
)
from aoa_sdk.organs.admission import materialize_admission_decision
from aoa_sdk.organs.registry import sha256_digest

from abyss_stack_mcp.admission_revision import (
    AdmissionRevisionError,
    compose_admission_revision,
)
from test_stack_mcp import (
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    DIGEST_D,
    DIGEST_MANIFEST,
    NOW,
    observation,
    subject,
)


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)
    return path


def _registry() -> OrganRegistrySourceV2:
    unknown = MaturityEvidence(state="not_asserted")
    maturity = OrganMaturityVector(
        **{name: unknown for name in OrganMaturityVector.model_fields}
    )
    capability = CapabilityContract(
        capability_id="knowledge-retrieval",
        summary="Retrieve owner-qualified KAG knowledge.",
        policy_family="read",
        credential_class="aoa-kag-read",
        primitives=(
            PrimitiveContract(
                primitive_id="retrieve-knowledge",
                kind="tool",
                mcp_name="kag_discover",
                effect_class="observe",
                policy_family="read",
                input_schema_ref="owner://aoa-kag/schema/input",
                output_schema_ref="owner://aoa-kag/schema/output",
                idempotency="read_only",
                maximum_blast_radius="read-only owner response",
            ),
        ),
        owner_payload_schema_ref="owner://aoa-kag/schema/payload",
    )
    contour = OrganContourRecord(
        contour_id="read",
        registry_state="shadow",
        authority_class="read",
        policy_family="read",
        credential_class="aoa-kag-read",
        principal_id="aoa-kag-read-principal",
        allowlist=("kag_discover",),
        capabilities=(capability,),
        endpoint=EndpointContract(
            adapter_id="aoa-kag-mcp-direct",
            transport="streamable-http",
            endpoint_ref="http://127.0.0.1:5425/mcp",
            protocol_versions=("2025-11-25",),
            server_schema_digest=DIGEST_D,
        ),
        runtime_identity=ContourRuntimeIdentity(
            source_revision="source-rev-1",
            source_tree_digest=DIGEST_A,
            package_name="aoa-kag-mcp",
            package_version="0.1.0",
            package_digest=DIGEST_B,
            deployment_revision="deploy-rev-1",
            deployment_manifest_ref=(
                "Logs/mcp/deployments/records/"
                + DIGEST_MANIFEST.removeprefix("sha256:")
                + ".json"
            ),
            deployment_manifest_digest=DIGEST_MANIFEST,
            deployed_tree_digest=DIGEST_C,
            process_ref="/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py",
            process_identity="aoa-kag-mcp/0.1.0",
        ),
        runtime_identity_evidence=(
            QualifiedEvidenceRef(
                owner="abyss-stack",
                evidence_ref="receipt://runtime/deploy",
                revision="stack-rev-1",
                observed_at=NOW,
                expires_at=NOW + timedelta(hours=2),
            ),
        ),
        revisions=OrganRevisions(
            source=RevisionIdentity(revision="source-rev-1", digest=DIGEST_A)
        ),
        freshness_policy=FreshnessPolicy(
            policy_id="kag-owner-freshness",
            max_age_seconds=300,
            cache_scope="task",
        ),
        maturity=maturity,
        currentness_expires_at=NOW + timedelta(hours=2),
        observation_route="runbook://canary/aoa-kag",
        rollback_route="runbook://rollback/aoa-kag",
    )
    return OrganRegistrySourceV2(
        registry_id="abyss-private",
        workspace_owner="os-abyss",
        authored_at=NOW,
        expires_at=NOW + timedelta(hours=2),
        owner_decision_refs=("owner://os-abyss/decision/shadow",),
        records=(
            OrganRecordV2(
                organ_id="aoa-kag",
                display_name="AoA KAG",
                description="Owner-qualified KAG access contour.",
                owners=OrganOwners(
                    source_owner="aoa-kag",
                    access_owner="aoa-kag",
                    runtime_owner="abyss-stack",
                    proof_owner="aoa-evals",
                    acceptance_owner="aoa-kag",
                ),
                authentication_requirements=("bearer",),
                support_route="owner://aoa-kag/support",
                handoff=HandoffContract(
                    input_ref_kind="request",
                    output_ref_kind="result",
                    next_owner="aoa-kag",
                    stop_states=("blocked",),
                ),
                contours=(contour,),
            ),
        ),
    )


def _set_owner(link: dict, owner: str) -> None:
    link["evidence_refs"][0]["owner"] = owner


def _inputs(tmp_path: Path) -> dict[str, Path]:
    registry = _registry()
    production_unit = "aoa-organ-mcp-read@aoa-kag.service"
    current_process_identity = f"systemd-user:{production_unit}:pid:321:start:654"
    lkg_process_identity = f"systemd-user:{production_unit}:pid:322:start:655"
    registry_payload = registry.model_dump(mode="json")
    registry_payload["records"][0]["contours"][0]["runtime_identity"][
        "process_identity"
    ] = current_process_identity
    registry = OrganRegistrySourceV2.model_validate(registry_payload)
    contour = registry.records[0].contours[0]
    current = subject()
    _set_owner(current["source"]["evidence"], "aoa-kag")
    _set_owner(current["registry"]["evidence"], "aoa-sdk")
    _set_owner(current["consumers"][0]["evidence"], "8Dionysus")
    _set_owner(current["freshness"], "aoa-kag")
    current["source"]["expected_sync_tree_digest"] = DIGEST_A
    current["registry"]["registry_digest"] = sha256_digest(
        contour.model_dump(mode="json")
    )
    current["registry"]["registry_id"] = registry.registry_id
    current["process"]["unit_name"] = production_unit
    current["process"]["process_identity"] = current_process_identity
    current["proof"]["proved_process_identity"] = current_process_identity
    rollback_target = current["rollback"]["proved_target"]
    rollback_target["unit_name"] = production_unit
    rollback_target["process_identity"] = lkg_process_identity
    current["rollback"]["last_known_good_unit_name"] = production_unit
    current["rollback"]["last_known_good_process_identity"] = lkg_process_identity
    lkg = json.loads(json.dumps(current))
    lkg["credential_class"] = rollback_target["credential_class"]
    lkg["package"]["artifact_digest"] = rollback_target["package_digest"]
    lkg["package"]["source_revision"] = rollback_target["deploy_revision"]
    lkg["deploy"]["revision"] = rollback_target["deploy_revision"]
    lkg["deploy"]["tree_digest"] = rollback_target["deploy_tree_digest"]
    lkg["deploy"]["manifest_ref"] = rollback_target["deploy_manifest_ref"]
    lkg["deploy"]["manifest_digest"] = rollback_target["deploy_manifest_digest"]
    lkg["deploy"]["evidence"]["evidence_refs"][0]["evidence_ref"] = rollback_target[
        "deploy_manifest_ref"
    ]
    lkg["process"]["unit_name"] = rollback_target["unit_name"]
    lkg["process"]["executable_ref"] = rollback_target["executable_ref"]
    lkg["process"]["process_identity"] = rollback_target["process_identity"]
    lkg["consumers"][0]["registration_ref"] = rollback_target[
        "consumer_registration_ref"
    ]
    lkg["consumers"][0]["evidence"]["evidence_refs"][0]["evidence_ref"] = (
        rollback_target["consumer_registration_ref"]
    )
    lkg["canary"]["canary_route"] = rollback_target["canary_route"]
    lkg["canary"]["canary_ref"] = rollback_target["canary_ref"]
    lkg["canary"]["evidence"]["evidence_refs"][0]["evidence_ref"] = lkg["canary"][
        "canary_ref"
    ]
    lkg["canary"]["evidence"]["evidence_refs"].append(
        {
            "owner": "aoa-kag",
            "evidence_ref": "/private/lkg-owner-review.json",
            "revision": DIGEST_A,
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        }
    )
    registry_path = _write(tmp_path / "registry.json", registry.model_dump(mode="json"))
    current_path = _write(tmp_path / "current.json", observation(current))
    lkg_path = _write(tmp_path / "lkg.json", observation(lkg))
    contour_digest = sha256_digest(contour.model_dump(mode="json"))
    decision = materialize_admission_decision(
        AdmissionDecisionStatement(
            candidate_id=contour_digest,
            decision_kind="operator",
            issuer=registry.workspace_owner,
            decision="accepted",
            decision_ref="owner://os-abyss/goal/mcp-next",
            decision_artifact_digest=contour_digest,
            decided_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )
    )
    decision_path = _write(
        tmp_path / "operator-decision.json", decision.model_dump(mode="json")
    )
    return {
        "registry": registry_path,
        "current": current_path,
        "lkg": lkg_path,
        "decision": decision_path,
    }


def _compose(paths: dict[str, Path]):
    return compose_admission_revision(
        registry_path=paths["registry"],
        observation_path=paths["current"],
        lkg_observation_path=paths["lkg"],
        operator_decision_path=paths["decision"],
        clock=lambda: NOW + timedelta(minutes=2),
        process_executable_digest=lambda identity, path, unit: DIGEST_A,
    )


def test_composes_content_addressed_non_effect_admission_revision(
    tmp_path: Path,
) -> None:
    revision = _compose(_inputs(tmp_path))
    unsigned = revision.model_dump(mode="json", exclude={"revision_digest"})

    assert revision.revision_digest == sha256_digest(unsigned)
    assert revision.admission_authorized is True
    assert revision.effect_authorized is False
    assert revision.rollback_executed is False
    assert revision.last_good.evidence_refs[0].owner == "abyss-stack"
    assert revision.maturity.cross_organ_proven.state == "not_asserted"


def test_accepts_stable_executable_rollback_target_for_live_lkg_process(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    lkg = json.loads(paths["lkg"].read_text())
    subject_payload = current["subjects"][0]
    rollback = subject_payload["rollback"]
    unit_name = rollback["proved_target"]["unit_name"]
    stable_process = f"systemd-user:{unit_name}:executable:{DIGEST_A}"
    rollback["proved_target"]["process_identity"] = stable_process
    rollback["last_known_good_process_identity"] = stable_process
    lkg["subjects"][0]["process"]["process_identity"] = (
        f"systemd-user:{unit_name}:pid:321:start:654"
    )
    _write(paths["current"], current)
    _write(paths["lkg"], lkg)

    revision = _compose(paths)

    assert revision.admission_authorized is True
    assert revision.last_good.runtime_identity.process_identity == (
        f"systemd-user:{unit_name}:pid:321:start:654"
    )


def test_rejects_stable_rollback_target_without_matching_executable_bytes(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    lkg = json.loads(paths["lkg"].read_text())
    rollback = current["subjects"][0]["rollback"]
    unit_name = rollback["proved_target"]["unit_name"]
    stable_process = f"systemd-user:{unit_name}:executable:{DIGEST_B}"
    rollback["proved_target"]["process_identity"] = stable_process
    rollback["last_known_good_process_identity"] = stable_process
    lkg["subjects"][0]["process"]["process_identity"] = (
        f"systemd-user:{unit_name}:pid:321:start:654"
    )
    _write(paths["current"], current)
    _write(paths["lkg"], lkg)

    with pytest.raises(AdmissionRevisionError, match="rollback proof target"):
        _compose(paths)


def test_rejects_operator_decision_for_different_contour(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    registry = OrganRegistrySourceV2.model_validate_json(paths["registry"].read_bytes())
    decision = materialize_admission_decision(
        AdmissionDecisionStatement(
            candidate_id=DIGEST_A,
            decision_kind="operator",
            issuer=registry.workspace_owner,
            decision="accepted",
            decision_ref="owner://os-abyss/goal/different-contour",
            decision_artifact_digest=DIGEST_A,
            decided_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(hours=1),
        )
    )
    _write(paths["decision"], decision.model_dump(mode="json"))

    with pytest.raises(AdmissionRevisionError, match="does not bind"):
        _compose(paths)


def test_rejects_reused_current_canary_as_last_known_good(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    lkg = json.loads(paths["lkg"].read_text())
    lkg["subjects"][0]["canary"]["canary_ref"] = current["subjects"][0]["canary"][
        "canary_ref"
    ]
    lkg["subjects"][0]["canary"]["evidence"]["evidence_refs"][0]["evidence_ref"] = (
        current["subjects"][0]["canary"]["canary_ref"]
    )
    _write(paths["lkg"], lkg)

    with pytest.raises(AdmissionRevisionError, match="exact and distinct"):
        _compose(paths)


def test_rejects_bootstrap_process_as_final_admission_evidence(
    tmp_path: Path,
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    bootstrap_unit = "aoa-organ-mcp-read-bootstrap@aoa-kag.service"
    bootstrap_identity = f"systemd-user:{bootstrap_unit}:pid:777:start:888"
    current["subjects"][0]["process"]["unit_name"] = bootstrap_unit
    current["subjects"][0]["process"]["process_identity"] = bootstrap_identity
    current["subjects"][0]["proof"]["proved_process_identity"] = bootstrap_identity
    _write(paths["current"], current)

    with pytest.raises(AdmissionRevisionError, match="production process"):
        _compose(paths)


@pytest.mark.parametrize(
    ("section", "field", "value", "error"),
    (
        ("source", "tree_digest", DIGEST_D, "registry contour"),
        ("package", "name", "different-mcp", "registry contour"),
        ("package", "version", "9.9.9", "registry contour"),
        ("package", "source_revision", "different-deploy-rev", "registry contour"),
        ("deploy", "revision", "different-deploy-rev", "registry contour"),
        ("deploy", "tree_digest", DIGEST_A, "registry contour"),
        (
            "process",
            "executable_ref",
            "/srv/AbyssOS/bin/different-mcp",
            "registry contour",
        ),
        (
            "process",
            "process_identity",
            "different-mcp/9.9.9",
            "production process",
        ),
    ),
)
def test_rejects_partial_registry_runtime_identity_match(
    tmp_path: Path, section: str, field: str, value: str, error: str
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    current["subjects"][0][section][field] = value
    _write(paths["current"], current)

    with pytest.raises(AdmissionRevisionError, match=error):
        _compose(paths)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("proved_source_revision", "different-source-rev"),
        ("proved_source_tree_digest", DIGEST_D),
        ("proved_package_digest", DIGEST_A),
        ("proved_deploy_revision", "different-deploy-rev"),
        ("proved_deploy_tree_digest", DIGEST_A),
        ("proved_deploy_manifest_digest", DIGEST_A),
        ("proved_process_identity", "different-mcp/9.9.9"),
        ("proved_server_schema_digest", DIGEST_A),
        ("proved_consumer_registration_ref", "config://codex/different"),
        ("proved_canary_route", "runbook://canary/different"),
        ("proved_canary_ref", "receipt://runtime/different-canary"),
    ),
)
def test_rejects_central_proof_for_different_current_contour(
    tmp_path: Path, field: str, value: str
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    current["subjects"][0]["proof"][field] = value
    _write(paths["current"], current)

    with pytest.raises(AdmissionRevisionError, match="different current contour"):
        _compose(paths)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("accepted_source_revision", "different-source-rev"),
        ("accepted_package_digest", DIGEST_A),
    ),
)
def test_rejects_owner_acceptance_for_different_current_contour(
    tmp_path: Path, field: str, value: str
) -> None:
    paths = _inputs(tmp_path)
    current = json.loads(paths["current"].read_text())
    current["subjects"][0]["acceptance"][field] = value
    _write(paths["current"], current)

    with pytest.raises(AdmissionRevisionError, match="different current contour"):
        _compose(paths)


@pytest.mark.parametrize(
    ("section", "field", "value", "error"),
    (
        ("package", "artifact_digest", DIGEST_A, "rollback proof target"),
        ("deploy", "revision", "different-deploy-rev", "rollback proof target"),
        (
            "process",
            "unit_name",
            "aoa-organ-mcp-read@different.service",
            "production process",
        ),
        (
            "process",
            "executable_ref",
            "/srv/AbyssOS/bin/different-mcp",
            "rollback proof target",
        ),
        (
            "process",
            "process_identity",
            "different-mcp/9.9.9",
            "production process",
        ),
    ),
)
def test_rejects_lkg_observation_for_different_rollback_target(
    tmp_path: Path, section: str, field: str, value: str, error: str
) -> None:
    paths = _inputs(tmp_path)
    lkg = json.loads(paths["lkg"].read_text())
    lkg["subjects"][0][section][field] = value
    _write(paths["lkg"], lkg)

    with pytest.raises(AdmissionRevisionError, match=error):
        _compose(paths)
