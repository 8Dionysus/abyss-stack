from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from abyss_stack_mcp.contracts import RuntimeObservation
from abyss_stack_mcp.cli import main as cli_main
from abyss_stack_mcp.core import (
    ObservationStore,
    StackMCPApplication,
    StackMCPError,
)
from abyss_stack_mcp.server import _auth_kwargs, _contour, build_server


NOW = datetime(2026, 7, 26, 5, 0, tzinfo=timezone.utc)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
DIGEST_F = "sha256:" + "f" * 64


def evidence(
    name: str,
    *,
    state: str = "exact",
    owner: str = "abyss-stack",
) -> dict:
    ref = {
        "owner": owner,
        "evidence_ref": f"receipt://runtime/{name}",
        "revision": "stack-rev-1",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }
    return {
        "state": state,
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "evidence_refs": [ref] if state == "exact" else [],
        "reason_codes": [] if state == "exact" else ["fixture-drift"],
    }


def subject(
    organ_id: str = "aoa-kag",
    *,
    policy_family: str = "read",
    credential_class: str = "aoa-kag-read",
) -> dict:
    effect_classes = {
        "read": ["observe", "derive"],
        "candidate": ["prepare_candidate"],
        "internal_effect": ["apply_runtime"],
        "external_effect": ["external_emit"],
    }[policy_family]
    return {
        "organ_id": organ_id,
        "policy_family": policy_family,
        "owners": {
            "source_owner": organ_id,
            "access_owner": organ_id,
            "runtime_owner": "abyss-stack",
            "proof_owner": "aoa-evals",
            "acceptance_owner": organ_id,
        },
        "credential_class": credential_class,
        "effect_classes": effect_classes,
        "source": {
            "revision": "source-rev-1",
            "tree_digest": DIGEST_A,
            "expected_sync_tree_digest": DIGEST_E,
            "evidence": evidence("source"),
        },
        "package": {
            "name": f"{organ_id}-mcp",
            "version": "0.1.0",
            "artifact_digest": DIGEST_B,
            "expected_deploy_tree_digest": DIGEST_F,
            "evidence": evidence("package"),
        },
        "deploy": {
            "revision": "deploy-rev-1",
            "tree_digest": DIGEST_C,
            "manifest_ref": f"receipt://deploy/{organ_id}",
            "deployed_at": NOW.isoformat(),
            "evidence": evidence("deploy"),
        },
        "process": {
            "unit_name": f"aoa-mcp-http@{organ_id}.service",
            "executable_ref": f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py",
            "process_identity": f"{organ_id}-mcp/0.1.0",
            "active": True,
            "evidence": evidence("process"),
        },
        "endpoint": {
            "transport": "streamable-http",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "protocol_versions": ["2025-11-25"],
            "ready": True,
            "server_schema_digest": DIGEST_D,
            "evidence": evidence("endpoint"),
        },
        "registry": {
            "registry_id": "abyss-private",
            "registry_digest": DIGEST_A,
            "registry_state": "shadow",
            "evidence": evidence("registry"),
        },
        "consumers": [
            {
                "consumer_id": "codex-main",
                "registration_ref": "config://codex/aoa-kag",
                "registered": True,
                "observed_schema_digest": DIGEST_D,
                "observed_protocol_versions": ["2025-11-25"],
                "evidence": evidence("consumer"),
            }
        ],
        "freshness": {
            "state": "exact",
            "provider_watermark": "kag-owner-watermark-1",
            "observed_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(hours=1)).isoformat(),
            "evidence_refs": evidence("freshness")["evidence_refs"],
        },
        "proof": {
            "verdict": "passed",
            "proof_ref": f"receipt://central-proof/{organ_id}",
            "evaluated_at": NOW.isoformat(),
            "proved_source_revision": "source-rev-1",
            "proved_source_tree_digest": DIGEST_A,
            "proved_package_digest": DIGEST_B,
            "proved_deploy_revision": "deploy-rev-1",
            "proved_deploy_tree_digest": DIGEST_C,
            "proved_process_identity": f"{organ_id}-mcp/0.1.0",
            "proved_server_schema_digest": DIGEST_D,
            "proved_consumer_registration_ref": f"config://codex/{organ_id}",
            "proved_canary_ref": f"receipt://canary/{organ_id}",
            "evidence": evidence("central-proof", owner="aoa-evals"),
        },
        "acceptance": {
            "accepted": True,
            "acceptance_ref": f"receipt://acceptance/{organ_id}",
            "accepted_at": NOW.isoformat(),
            "accepted_source_revision": "source-rev-1",
            "accepted_package_digest": DIGEST_B,
            "evidence": evidence("acceptance", owner=organ_id),
        },
        "canary": {
            "succeeded": True,
            "result_grounded": True,
            "canary_route": f"runbook://canary/{organ_id}",
            "canary_ref": f"receipt://canary/{organ_id}",
            "evidence": evidence("canary"),
        },
        "rollback": {
            "ready": True,
            "rollback_route": f"runbook://rollback/{organ_id}",
            "last_known_good_consumer_registration_ref": (
                f"config://codex/{organ_id}"
            ),
            "last_known_good_package_digest": DIGEST_B,
            "last_known_good_deploy_revision": "deploy-rev-0",
            "last_known_good_deploy_tree_digest": DIGEST_C,
            "last_known_good_unit_name": (
                f"aoa-mcp-http@{organ_id}.service"
            ),
            "last_known_good_credential_class": credential_class,
            "last_known_good_executable_ref": (
                f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py"
            ),
            "last_known_good_process_identity": f"{organ_id}-mcp/0.0.9",
            "last_known_good_canary_route": (
                f"runbook://canary/{organ_id}/last-known-good"
            ),
            "last_known_good_canary_ref": (
                f"receipt://canary/{organ_id}/last-known-good"
            ),
            "proof_ref": f"receipt://rollback/{organ_id}",
            "proved_target": {
                "consumer_registration_ref": f"config://codex/{organ_id}",
                "package_digest": DIGEST_B,
                "deploy_revision": "deploy-rev-0",
                "deploy_tree_digest": DIGEST_C,
                "unit_name": f"aoa-mcp-http@{organ_id}.service",
                "credential_class": credential_class,
                "executable_ref": (
                    f"/srv/AbyssOS/.codex/bin/{organ_id}-mcp-server.py"
                ),
                "process_identity": f"{organ_id}-mcp/0.0.9",
                "canary_route": (
                    f"runbook://canary/{organ_id}/last-known-good"
                ),
                "canary_ref": (
                    f"receipt://canary/{organ_id}/last-known-good"
                ),
            },
            "evidence": evidence("rollback"),
        },
    }


def observation(*subjects: dict) -> dict:
    return {
        "schema_version": "abyss_stack_runtime_observation_v1",
        "provider": "abyss-stack",
        "provider_watermark": "stack-runtime-observation-1",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "contains_secrets": False,
        "subjects": list(subjects or (subject(),)),
    }


def set_proof_event_time(
    payload: dict,
    event_surface: str,
    event_time: str,
) -> None:
    event = payload["subjects"][0][event_surface]
    event[
        {
            "proof": "evaluated_at",
            "acceptance": "accepted_at",
        }[event_surface]
    ] = event_time
    event["evidence"]["observed_at"] = event_time
    event["evidence"]["evidence_refs"][0]["observed_at"] = event_time


def write_observation(path: Path, payload: dict | None = None) -> Path:
    path.write_text(
        json.dumps(payload or observation(subject()), indent=2),
        encoding="utf-8",
    )
    return path


def application(
    tmp_path: Path,
    *,
    policy_family: str = "read",
    payload: dict | None = None,
) -> StackMCPApplication:
    path = write_observation(tmp_path / "observation.json", payload)
    return StackMCPApplication(
        ObservationStore(path),
        policy_family=policy_family,
        clock=lambda: NOW + timedelta(minutes=5),
    )


def test_contract_is_strict_and_policy_effects_are_bounded() -> None:
    payload = observation(subject())
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="extra"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject(policy_family="read", credential_class="read-only"))
    payload["subjects"][0]["effect_classes"] = ["apply_runtime"]
    with pytest.raises(ValidationError, match="exceed"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    duplicate_consumer = json.loads(
        json.dumps(payload["subjects"][0]["consumers"][0])
    )
    duplicate_consumer["consumer_id"] = "duplicate-registration"
    payload["subjects"][0]["consumers"].append(duplicate_consumer)
    with pytest.raises(ValidationError, match="registration refs must be unique"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="compatible_drift",
    )
    with pytest.raises(ValidationError, match="usable link requires evidence"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="rollback_required",
    )
    with pytest.raises(ValidationError, match="rollback-required link requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    freshness = payload["subjects"][0]["freshness"]
    freshness["state"] = "compatible_drift"
    freshness["evidence_refs"] = []
    freshness["reason_codes"] = ["watermark-drift"]
    with pytest.raises(ValidationError, match="usable freshness requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["last_known_good_process_identity"] = None
    with pytest.raises(ValidationError, match="complete last-known-good contour"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["proved_target"]["package_digest"] = DIGEST_A
    with pytest.raises(ValidationError, match="proof target must match"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["process"]["process_identity"] = None
    with pytest.raises(ValidationError, match="active process requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proof_ref"] = None
    with pytest.raises(ValidationError, match="passed central proof requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["proof"]["evidence"] = evidence(
        "central-proof",
        owner="unrelated-owner",
    )
    with pytest.raises(ValidationError, match="issued by proof_owner"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["accepted_at"] = (
        NOW - timedelta(seconds=1)
    ).isoformat()
    with pytest.raises(ValidationError, match="cannot precede central proof"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["acceptance_ref"] = None
    with pytest.raises(ValidationError, match="owner acceptance requires"):
        RuntimeObservation.model_validate(payload)

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["evidence"] = evidence(
        "acceptance",
        owner="unrelated-owner",
    )
    with pytest.raises(ValidationError, match="issued by acceptance_owner"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize("canary_time_surface", ("link", "evidence"))
def test_central_proof_cannot_predate_its_canary(
    canary_time_surface: str,
) -> None:
    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    if canary_time_surface == "link":
        canary_evidence["observed_at"] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        canary_evidence["evidence_refs"][0]["observed_at"] = (
            NOW + timedelta(seconds=1)
        ).isoformat()

    with pytest.raises(ValidationError, match="cannot precede canary evidence"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize("canary_time_surface", ("link", "evidence"))
def test_successful_canary_cannot_predate_deployment(
    canary_time_surface: str,
) -> None:
    payload = observation(subject())
    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    if canary_time_surface == "link":
        canary_evidence["observed_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat()
    else:
        canary_evidence["evidence_refs"][0]["observed_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat()

    with pytest.raises(ValidationError, match="cannot precede deployment"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    ("event_surface", "expected_error"),
    (
        ("proof", "central proof evidence cannot predate"),
        ("acceptance", "owner acceptance evidence cannot predate"),
    ),
)
@pytest.mark.parametrize("evidence_time_surface", ("link", "evidence"))
def test_proof_events_reject_unrelated_old_receipts(
    event_surface: str,
    expected_error: str,
    evidence_time_surface: str,
) -> None:
    payload = observation(subject())
    event_evidence = payload["subjects"][0][event_surface]["evidence"]
    old_receipt_time = (NOW - timedelta(seconds=31)).isoformat()
    if evidence_time_surface == "link":
        event_evidence["observed_at"] = old_receipt_time
    else:
        event_evidence["evidence_refs"][0]["observed_at"] = old_receipt_time

    with pytest.raises(ValidationError, match=expected_error):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    "field_path",
    (
        ("deploy", "manifest_ref"),
        ("consumers", 0, "registration_ref"),
        ("canary", "canary_route"),
        ("rollback", "rollback_route"),
        ("source", "evidence", "evidence_refs", 0, "evidence_ref"),
    ),
)
def test_contract_rejects_whitespace_only_exact_targets(
    field_path: tuple[str | int, ...],
) -> None:
    payload = observation(subject())
    target = payload["subjects"][0]
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = " \t\n"

    with pytest.raises(ValidationError, match="pattern"):
        RuntimeObservation.model_validate(payload)


def test_observation_store_rejects_secrets_symlinks_and_oversize(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["credential_material"] = "not-allowed"
    path = write_observation(tmp_path / "secret.json", payload)
    with pytest.raises(StackMCPError, match="secret-bearing"):
        ObservationStore(path).load()

    real = write_observation(tmp_path / "real.json")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with pytest.raises(StackMCPError, match="regular file"):
        ObservationStore(link).load()

    large = tmp_path / "large.json"
    large.write_text(" " * (2 * 1024 * 1024 + 1), encoding="utf-8")
    with pytest.raises(StackMCPError, match="2 MiB"):
        ObservationStore(large).load()

    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["endpoint_ref"] = (
        "http://user:password@127.0.0.1:5425/mcp"
    )
    with pytest.raises(ValidationError, match="user information"):
        RuntimeObservation.model_validate(payload)


@pytest.mark.parametrize(
    "secret_key",
    (
        "apiKey",
        "clientSecret",
        "private.key",
        "refresh token",
        "github_api_key",
        "backupClientSecretValue",
    ),
)
def test_observation_store_rejects_separator_and_case_secret_keys_without_value(
    tmp_path: Path,
    secret_key: str,
) -> None:
    secret_value = "unprefixed-sensitive-material"
    payload = observation(subject())
    payload["subjects"][0][secret_key] = secret_value
    path = write_observation(tmp_path / "secret-key.json", payload)

    with pytest.raises(StackMCPError, match="secret-bearing") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


@pytest.mark.parametrize(
    "reference_surface",
    (
        "query",
        "relative-query",
        "userinfo",
        "scheme-relative-userinfo",
        "fragment",
        "fragment-token",
        "secret-value",
        "leading-token",
        "leading-direct",
        "basic-auth",
        "encoded-basic-auth",
        "raw-jwt",
        "encoded-jwt",
        "pem-private-key",
        "embedded-pem-private-key",
        "encoded-pem-private-key",
        "top-level-encoded",
        "nested-value",
        "double-key",
        "path",
        "encoded-path",
        "path-token",
        "namespaced-query-key",
        "concatenated-namespaced-query-key",
        "suffixed-query-key",
        "namespaced-path-key",
        "bare-assignment",
        "embedded-bare-assignment",
        "namespaced-bare-assignment",
        "encoded-bare-assignment",
        "unparseable",
    ),
)
def test_observation_store_rejects_credentials_inside_references(
    tmp_path: Path,
    reference_surface: str,
) -> None:
    secret_value = "reference-secret-value"
    payload = observation(subject())
    if reference_surface == "query":
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "evidence_ref"
        ] = f"https://evidence.invalid/report?api_key={secret_value}"
    elif reference_surface == "relative-query":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"receipt?api_key={secret_value}"
        )
    elif reference_surface == "userinfo":
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"https://operator:{secret_value}@deploy.invalid/manifest"
        )
    elif reference_surface == "scheme-relative-userinfo":
        payload["subjects"][0]["deploy"]["manifest_ref"] = (
            f"//operator:{secret_value}@deploy.invalid/manifest"
        )
    elif reference_surface == "fragment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt#client_secret={secret_value}"
        )
    elif reference_surface == "fragment-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt#sk-{secret_value}"
        )
    elif reference_surface == "secret-value":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?value=sk-{secret_value}"
        )
    elif reference_surface == "leading-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?value=%20sk-{secret_value}"
        )
    elif reference_surface == "leading-direct":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f" Bearer {secret_value}"
        )
    elif reference_surface == "basic-auth":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"  bAsIc {secret_value}"
        )
    elif reference_surface == "encoded-basic-auth":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"Basic%20{secret_value}"
        )
    elif reference_surface == "raw-jwt":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiJvcGVyYXRvciIsInNlY3JldCI6InJlZmVyZW5jZSJ9."
            "c2lnbmF0dXJlLW1hdGVyaWFs"
        )
    elif reference_surface == "encoded-jwt":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "eyJhbGciOiJIUzI1NiJ9%2E"
            "eyJzdWIiOiJvcGVyYXRvciJ9%2E"
            "c2lnbmF0dXJlLW1hdGVyaWFs"
        )
    elif reference_surface == "pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "-----BEGIN PRIVATE KEY-----\n"
            f"{secret_value}\n"
            "-----END PRIVATE KEY-----"
        )
    elif reference_surface == "embedded-pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "captured material:\n"
            "-----BEGIN EC PRIVATE KEY-----\n"
            f"{secret_value}"
        )
    elif reference_surface == "encoded-pem-private-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "-----BEGIN%20OPENSSH%20PRIVATE%20KEY-----"
            f"%0A{secret_value}"
        )
    elif reference_surface == "top-level-encoded":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https%3A%2F%2Facceptance.invalid%2Freceipt"
            f"%3Fapi_key%3D{secret_value}"
        )
    elif reference_surface == "nested-value":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            "https://acceptance.invalid/receipt?"
            "next=https%3A%2F%2Fhost.invalid%2Freport"
            f"%3Fapi_key%3D{secret_value}"
        )
    elif reference_surface == "double-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/receipt?%2561pi_key={secret_value}"
        )
    elif reference_surface == "path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/api_key/{secret_value}"
        )
    elif reference_surface == "encoded-path":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/%2561pi_key/{secret_value}"
        )
    elif reference_surface == "path-token":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/sk-{secret_value}"
        )
    elif reference_surface == "namespaced-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?github_api_key={secret_value}"
        )
    elif reference_surface == "concatenated-namespaced-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?githubapikey={secret_value}"
            f"&dbpassword={secret_value}"
        )
    elif reference_surface == "suffixed-query-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report?api_key_backup={secret_value}"
        )
    elif reference_surface == "namespaced-path-key":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://acceptance.invalid/report/github_api_key/{secret_value}"
        )
    elif reference_surface == "bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"api_key={secret_value}"
        )
    elif reference_surface == "embedded-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"review receipt carries api_key={secret_value}"
        )
    elif reference_surface == "namespaced-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"github_api_key:{secret_value}"
        )
    elif reference_surface == "encoded-bare-assignment":
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"github_api_key%3D{secret_value}"
        )
    else:
        payload["subjects"][0]["acceptance"]["acceptance_ref"] = (
            f"https://[bad?api_key={secret_value}"
        )
    path = write_observation(tmp_path / f"{reference_surface}.json", payload)

    with pytest.raises(StackMCPError, match="forbidden") as caught:
        ObservationStore(path).load()

    assert secret_value not in str(caught.value)


def test_observation_store_redacts_contract_validation_input_values(
    tmp_path: Path,
) -> None:
    sensitive_value = "unclassified-sensitive-material"
    payload = observation(subject())
    payload["subjects"][0]["unrecognizedField"] = sensitive_value
    path = write_observation(tmp_path / "invalid-contract.json", payload)

    with pytest.raises(StackMCPError, match="contract validation failed") as caught:
        ObservationStore(path).load()

    assert sensitive_value not in str(caught.value)
    assert caught.value.__suppress_context__ is True


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_observation_store_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "observation.fifo"
    os.mkfifo(fifo)

    with pytest.raises(StackMCPError, match="regular file"):
        ObservationStore(fifo).load()


@pytest.mark.parametrize(
    "endpoint_ref",
    (
        "http://localhost:abc/mcp",
        "http://localhost:0/mcp",
        "http://localhost:65536/mcp",
    ),
)
def test_contract_rejects_invalid_http_endpoint_ports(endpoint_ref: str) -> None:
    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["endpoint_ref"] = endpoint_ref

    with pytest.raises(ValidationError, match="invalid port"):
        RuntimeObservation.model_validate(payload)


def test_catalog_is_compact_and_does_not_flatten_health(tmp_path: Path) -> None:
    app = application(tmp_path)
    result = app.catalog()
    payload = result["owner_payload"]
    assert payload["schema_bytes_loaded"] == 0
    assert payload["entries"][0]["organ_id"] == "aoa-kag"
    assert "proof" in payload["entries"][0]["views"]
    assert "acceptance" in payload["entries"][0]["views"]
    assert "healthy" not in json.dumps(result).lower()
    assert result["metadata"]["execution_authorized"] is False
    assert result["metadata"]["applied_state"] == "not_applied"


def test_read_plane_cannot_enumerate_or_inspect_higher_policy_subjects(
    tmp_path: Path,
) -> None:
    payload = observation(
        subject("read-organ", credential_class="read-organ-read"),
        subject(
            "candidate-organ",
            policy_family="candidate",
            credential_class="candidate-organ-candidate",
        ),
        subject(
            "internal-organ",
            policy_family="internal_effect",
            credential_class="internal-organ-effect",
        ),
        subject(
            "external-organ",
            policy_family="external_effect",
            credential_class="external-organ-effect",
        ),
    )
    app = application(tmp_path, payload=payload)

    entries = app.catalog()["owner_payload"]["entries"]
    assert [(entry["organ_id"], entry["policy_family"]) for entry in entries] == [
        ("read-organ", "read")
    ]
    for policy_family in ("candidate", "internal_effect", "external_effect"):
        with pytest.raises(StackMCPError, match="only read-policy"):
            app.catalog(policy_family=policy_family)
        with pytest.raises(StackMCPError, match="only read-policy"):
            app.inspect(f"{policy_family}-organ", policy_family)

    candidate_app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    with pytest.raises(StackMCPError, match="discovery is absent"):
        candidate_app.catalog()
    with pytest.raises(StackMCPError, match="inspection is absent"):
        candidate_app.inspect("read-organ", "read")


def test_inspection_keeps_process_endpoint_freshness_independent(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["ready"] = False
    payload["subjects"][0]["endpoint"]["server_schema_digest"] = None
    payload["subjects"][0]["endpoint"]["evidence"] = evidence(
        "endpoint",
        state="blocked",
    )
    app = application(tmp_path, payload=payload)
    process = app.inspect("aoa-kag", "read", view="process")
    endpoint = app.inspect("aoa-kag", "read", view="endpoint")
    assert process["owner_payload"]["observation"]["active"] is True
    assert endpoint["owner_payload"]["observation"]["ready"] is False
    assert endpoint["owner_payload"]["observation"]["evidence"]["state"] == ("blocked")


def test_read_process_has_no_plan_capability(tmp_path: Path) -> None:
    app = application(tmp_path)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="absent from the read process"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_candidate_plan_is_content_addressed_and_never_authorized(
    tmp_path: Path,
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()
    first = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    second = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    assert first == second
    plan = first["owner_payload"]["plan"]
    assert plan["execution_authorized"] is False
    assert plan["approval_required_before_execution"] is True
    assert plan["exact_unit_name"] == "aoa-mcp-http@aoa-kag.service"
    assert [step["order"] for step in plan["steps"]] == [1, 2, 3, 4, 5, 6]
    assert plan["steps"][0]["exact_target"] == "aoa-kag-mcp/0.1.0"
    assert plan["steps"][1]["exact_target"] == "receipt://central-proof/aoa-kag"
    assert plan["steps"][2]["exact_target"] == "receipt://acceptance/aoa-kag"
    assert plan["steps"][3]["action"] == "admit-registry-entry"
    assert plan["steps"][3]["exact_target"] == f"abyss-private@{DIGEST_A}"
    assert plan["steps"][4]["exact_target"] == "config://codex/aoa-kag"
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "receipt://runtime/consumer" in evidence_refs
    assert "receipt://runtime/freshness" in evidence_refs
    assert "receipt://runtime/central-proof" in evidence_refs
    assert "receipt://runtime/acceptance" in evidence_refs


def test_activation_verifies_an_already_admitted_registry(tmp_path: Path) -> None:
    payload = observation(subject())
    payload["subjects"][0]["registry"]["registry_state"] = "admitted"
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )

    assert result["owner_payload"]["plan"]["steps"][3]["action"] == (
        "verify-registry-admission"
    )
    assert result["owner_payload"]["plan"]["steps"][3]["exact_target"] == (
        f"abyss-private@{DIGEST_A}"
    )


@pytest.mark.parametrize(
    ("plan_kind", "expected_steps"),
    (
        (
            "sync",
            (
                ("verify-source-revision", "source-rev-1"),
                ("verify-source-tree-digest", DIGEST_A),
                ("preview-config-sync", "receipt://deploy/aoa-kag"),
                ("apply-exact-config-sync", "receipt://deploy/aoa-kag"),
                ("compare-deployed-digest", DIGEST_E),
            ),
        ),
        (
            "deploy",
            (
                ("verify-package-digest", DIGEST_B),
                ("stage-exact-package", f"aoa-kag-mcp@{DIGEST_B}"),
                ("deploy-staged-package", f"aoa-kag-mcp@{DIGEST_B}"),
                ("compare-deployed-digest", DIGEST_F),
            ),
        ),
    ),
)
def test_sync_and_deploy_plans_include_exact_transition_steps(
    tmp_path: Path,
    plan_kind: str,
    expected_steps: tuple[tuple[str, str], ...],
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        plan_kind,
        expected_observation_digest=digest,
    )

    plan = result["owner_payload"]["plan"]
    assert plan["execution_authorized"] is False
    assert plan["postcondition_deploy_tree_digest"] == {
        "sync": DIGEST_E,
        "deploy": DIGEST_F,
    }[plan_kind]
    assert tuple(
        (step["action"], step["exact_target"]) for step in plan["steps"]
    ) == expected_steps


def test_candidate_plan_denies_drift_expiry_and_unproven_rollback(
    tmp_path: Path,
) -> None:
    app = application(tmp_path, policy_family="candidate")
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="digest drift"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=DIGEST_A,
        )

    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    source_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    read_app = application(
        tmp_path,
        payload=payload,
    )
    catalog = read_app.catalog()
    assert catalog["owner_payload"]["entries"][0]["link_states"]["source"] == (
        "stale_readable"
    )
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    payload["subjects"][0]["rollback"]["ready"] = False
    payload["subjects"][0]["rollback"]["last_known_good_package_digest"] = None
    payload["subjects"][0]["rollback"]["proof_ref"] = None
    payload["subjects"][0]["rollback"]["evidence"] = evidence(
        "rollback",
        state="unknown",
    )
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="rollback_not_proven"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    payload["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    app = application(
        tmp_path,
        policy_family="candidate",
        payload=payload,
    )
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="expired runtime observation"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_rollback_plan_accepts_fresh_rollback_required_deploy_links(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["state"] = "rollback_required"
    source_evidence["reason_codes"] = ["failed-rollout"]
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "rollback",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    assert plan["plan_kind"] == "rollback"
    assert [
        (step["action"], step["exact_target"]) for step in plan["steps"]
    ] == [
        ("deny-discovery", f"abyss-private@{DIGEST_A}"),
        ("deny-activation", "aoa-kag/read"),
        ("verify-rollback-proof", "receipt://rollback/aoa-kag"),
        ("restore-exact-package", DIGEST_B),
        ("restore-deployed-tree", DIGEST_C),
        ("restore-deploy-revision", "deploy-rev-0"),
        ("restore-unit", "aoa-mcp-http@aoa-kag.service"),
        ("restore-credential-class", "aoa-kag-read"),
        (
            "restore-executable",
            "/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py",
        ),
        ("restart-restored-process", "aoa-mcp-http@aoa-kag.service"),
        ("verify-process-identity", "aoa-kag-mcp/0.0.9"),
        ("restore-consumer-registration", "config://codex/aoa-kag"),
        (
            "run-grounded-canary",
            "runbook://canary/aoa-kag/last-known-good",
        ),
    ]
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert {
        "receipt://runtime/source",
        "receipt://runtime/registry",
        "receipt://runtime/consumer",
        "receipt://runtime/canary",
        "receipt://runtime/rollback",
    } <= evidence_refs

    payload = observation(subject())
    payload["subjects"][0]["source"]["evidence"] = evidence(
        "source",
        state="blocked",
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    source_evidence = payload["subjects"][0]["source"]["evidence"]
    source_evidence["state"] = "rollback_required"
    source_evidence["reason_codes"] = ["failed-rollout"]
    source_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    source_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="source_identity_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    ("evidence_path", "expected_blocker"),
    (
        (("registry", "evidence"), "registry_evidence_not_usable"),
        (
            ("consumers", 0, "evidence"),
            "rollback_consumer_evidence_not_usable",
        ),
        (("canary", "evidence"), "canary_evidence_not_usable"),
    ),
)
def test_rollback_plan_requires_fresh_evidence_for_every_step(
    tmp_path: Path,
    evidence_path: tuple[str | int, ...],
    expected_blocker: str,
) -> None:
    payload = observation(subject())
    target = payload["subjects"][0]
    for part in evidence_path:
        target = target[part]
    target["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    target["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match=expected_blocker):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "rollback",
            expected_observation_digest=digest,
        )


def test_restart_plan_requires_and_carries_fresh_canary_evidence(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "restart",
        expected_observation_digest=digest,
    )
    assert "receipt://runtime/canary" in {
        item["evidence_ref"]
        for item in result["owner_payload"]["plan"]["precondition_evidence"]
    }

    canary_evidence = payload["subjects"][0]["canary"]["evidence"]
    canary_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    canary_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="canary_evidence_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "restart",
            expected_observation_digest=digest,
        )


def test_activation_requires_usable_freshness_and_runtime_readiness(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    assert result["owner_payload"]["plan"]["plan_kind"] == "activate"

    cases: list[tuple[dict, str]] = []

    payload = observation(subject())
    payload["subjects"][0]["freshness"]["state"] = "blocked"
    payload["subjects"][0]["freshness"]["reason_codes"] = ["provider-blocked"]
    cases.append((payload, "subject_freshness_not_usable"))

    payload = observation(subject())
    payload["subjects"][0]["process"]["active"] = False
    cases.append((payload, "process_not_active"))

    payload = observation(subject())
    payload["subjects"][0]["endpoint"]["ready"] = False
    cases.append((payload, "endpoint_not_ready"))

    payload = observation(subject())
    proof = payload["subjects"][0]["proof"]
    proof["verdict"] = "unknown"
    proof["proof_ref"] = None
    proof["evaluated_at"] = None
    proof["proved_source_revision"] = None
    proof["proved_source_tree_digest"] = None
    proof["proved_package_digest"] = None
    proof["proved_deploy_revision"] = None
    proof["proved_deploy_tree_digest"] = None
    proof["proved_process_identity"] = None
    proof["proved_server_schema_digest"] = None
    proof["proved_consumer_registration_ref"] = None
    proof["proved_canary_ref"] = None
    proof["evidence"] = evidence("central-proof", state="unknown")
    cases.append((payload, "central_proof_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_source_tree_digest"] = DIGEST_B
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_package_digest"] = DIGEST_A
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_deploy_tree_digest"] = DIGEST_A
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    payload["subjects"][0]["proof"]["proved_process_identity"] = (
        "aoa-kag-mcp/previous-process"
    )
    cases.append((payload, "central_proof_target_mismatch"))

    payload = observation(subject())
    proof_evidence = payload["subjects"][0]["proof"]["evidence"]
    proof_evidence["expires_at"] = (NOW + timedelta(minutes=1)).isoformat()
    proof_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    cases.append((payload, "central_proof_not_proven"))

    payload = observation(subject())
    acceptance = payload["subjects"][0]["acceptance"]
    acceptance["accepted"] = False
    acceptance["acceptance_ref"] = None
    acceptance["accepted_at"] = None
    acceptance["accepted_source_revision"] = None
    acceptance["accepted_package_digest"] = None
    acceptance["evidence"] = evidence("acceptance", state="unknown")
    cases.append((payload, "owner_acceptance_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["acceptance"]["accepted_source_revision"] = (
        "different-source-revision"
    )
    cases.append((payload, "owner_acceptance_target_mismatch"))

    payload = observation(subject())
    acceptance_evidence = payload["subjects"][0]["acceptance"]["evidence"]
    acceptance_evidence["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    acceptance_evidence["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    cases.append((payload, "owner_acceptance_not_proven"))

    payload = observation(subject())
    payload["subjects"][0]["canary"]["succeeded"] = False
    cases.append((payload, "canary_not_proven"))

    payload = observation(subject())
    rollback = payload["subjects"][0]["rollback"]
    rollback["ready"] = False
    rollback["last_known_good_package_digest"] = None
    rollback["proof_ref"] = None
    rollback["evidence"] = evidence("rollback", state="unknown")
    cases.append((payload, "rollback_not_proven"))

    for case_index, (case_payload, blocker) in enumerate(cases):
        case_root = tmp_path / f"case-{case_index}"
        case_root.mkdir()
        app = application(
            case_root,
            policy_family="candidate",
            payload=case_payload,
        )
        _, digest = app.store.load()
        with pytest.raises(StackMCPError, match=blocker):
            app.prepare_plan(
                "aoa-kag",
                "read",
                "activate",
                expected_observation_digest=digest,
            )


@pytest.mark.parametrize("policy_family", ("internal_effect", "external_effect"))
@pytest.mark.parametrize("plan_kind", ("activate", "restart"))
def test_runtime_activation_blocks_effect_planes_until_effect_contracts_exist(
    tmp_path: Path,
    policy_family: str,
    plan_kind: str,
) -> None:
    payload = observation(
        subject(
            organ_id=f"{policy_family}-organ",
            policy_family=policy_family,
            credential_class=f"{policy_family}-credential",
        )
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="effect_activation_contracts_absent"):
        app.prepare_plan(
            f"{policy_family}-organ",
            policy_family,
            plan_kind,
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    ("consumer_schema", "consumer_protocols"),
    [
        (DIGEST_A, ["2025-11-25"]),
        (DIGEST_D, ["2026-07-28"]),
    ],
)
def test_activation_rejects_incompatible_registered_consumer(
    tmp_path: Path,
    consumer_schema: str,
    consumer_protocols: list[str],
) -> None:
    payload = observation(subject())
    consumer = payload["subjects"][0]["consumers"][0]
    consumer["observed_schema_digest"] = consumer_schema
    consumer["observed_protocol_versions"] = consumer_protocols
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="no_compatible_registered_consumer"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_activation_targets_only_the_selected_compatible_consumer(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    good = payload["subjects"][0]["consumers"][0]
    good["consumer_id"] = "z-compatible"
    good["registration_ref"] = "config://codex/compatible"
    good["evidence"] = evidence("consumer-good")
    payload["subjects"][0]["proof"]["proved_consumer_registration_ref"] = (
        "config://codex/compatible"
    )
    unselected = json.loads(json.dumps(good))
    unselected["consumer_id"] = "a-compatible-unselected"
    unselected["registration_ref"] = "config://codex/compatible-unselected"
    unselected["evidence"] = evidence("consumer-unselected")
    payload["subjects"][0]["consumers"] = [unselected, good]

    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    assert plan["steps"][4]["exact_target"] == "config://codex/compatible"
    evidence_refs = {
        item["evidence_ref"] for item in plan["precondition_evidence"]
    }
    assert "receipt://runtime/consumer-good" in evidence_refs
    assert "receipt://runtime/consumer-unselected" not in evidence_refs


def test_freshness_reference_expiry_is_stale_and_blocks_plans(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["subjects"][0]["freshness"]["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    read_app = application(tmp_path, payload=payload)
    catalog = read_app.catalog()
    assert catalog["owner_payload"]["entries"][0]["freshness_state"] == (
        "stale_readable"
    )
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    with pytest.raises(StackMCPError, match="subject_freshness_not_usable"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )

    payload = observation(subject())
    freshness = payload["subjects"][0]["freshness"]
    freshness["state"] = "blocked"
    freshness["reason_codes"] = ["provider-blocked"]
    freshness["evidence_refs"][0]["expires_at"] = (
        NOW + timedelta(minutes=1)
    ).isoformat()
    read_app = application(tmp_path, payload=payload)
    assert read_app.catalog()["owner_payload"]["entries"][0]["freshness_state"] == (
        "blocked"
    )


@pytest.mark.parametrize(
    ("expiry_surface", "expected_expiry"),
    [
        ("link", NOW + timedelta(minutes=7)),
        ("evidence", NOW + timedelta(minutes=8)),
    ],
)
def test_plan_expires_with_its_earliest_precondition(
    tmp_path: Path,
    expiry_surface: str,
    expected_expiry: datetime,
) -> None:
    payload = observation(subject())
    if expiry_surface == "link":
        payload["subjects"][0]["endpoint"]["evidence"]["expires_at"] = (
            expected_expiry.isoformat()
        )
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "expires_at"
        ] = expected_expiry.isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()
    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan_expiry = datetime.fromisoformat(
        result["owner_payload"]["plan"]["expires_at"].replace("Z", "+00:00")
    )
    assert plan_expiry == expected_expiry


@pytest.mark.parametrize(
    "future_surface",
    (
        "observation",
        "deploy",
        "freshness",
        "proof",
        "acceptance",
        "link",
        "evidence",
    ),
)
def test_plan_rejects_timestamps_beyond_bounded_future_skew(
    tmp_path: Path,
    future_surface: str,
) -> None:
    payload = observation(subject())
    future = (NOW + timedelta(minutes=5, seconds=31)).isoformat()
    if future_surface == "observation":
        payload["generated_at"] = future
    elif future_surface == "deploy":
        payload["subjects"][0]["deploy"]["deployed_at"] = future
        canary_evidence = payload["subjects"][0]["canary"]["evidence"]
        canary_evidence["observed_at"] = future
        canary_evidence["evidence_refs"][0]["observed_at"] = future
        set_proof_event_time(payload, "proof", future)
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "freshness":
        payload["subjects"][0]["freshness"]["observed_at"] = future
    elif future_surface == "proof":
        set_proof_event_time(payload, "proof", future)
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "acceptance":
        set_proof_event_time(payload, "acceptance", future)
    elif future_surface == "link":
        payload["subjects"][0]["source"]["evidence"]["observed_at"] = future
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "observed_at"
        ] = future
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="future-dated"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


@pytest.mark.parametrize(
    "post_snapshot_surface",
    ("deploy", "freshness", "proof", "acceptance", "link", "evidence"),
)
def test_plan_rejects_evidence_that_postdates_its_snapshot(
    tmp_path: Path,
    post_snapshot_surface: str,
) -> None:
    payload = observation(subject())
    post_snapshot = (NOW + timedelta(seconds=31)).isoformat()
    if post_snapshot_surface == "deploy":
        payload["subjects"][0]["deploy"]["deployed_at"] = post_snapshot
        canary_evidence = payload["subjects"][0]["canary"]["evidence"]
        canary_evidence["observed_at"] = post_snapshot
        canary_evidence["evidence_refs"][0]["observed_at"] = post_snapshot
        set_proof_event_time(payload, "proof", post_snapshot)
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "freshness":
        payload["subjects"][0]["freshness"]["observed_at"] = post_snapshot
    elif post_snapshot_surface == "proof":
        set_proof_event_time(payload, "proof", post_snapshot)
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "acceptance":
        set_proof_event_time(payload, "acceptance", post_snapshot)
    elif post_snapshot_surface == "link":
        payload["subjects"][0]["source"]["evidence"]["observed_at"] = post_snapshot
    else:
        payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0][
            "observed_at"
        ] = post_snapshot
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="future-dated"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_plan_allows_observation_within_bounded_future_skew(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    payload["generated_at"] = (
        NOW + timedelta(minutes=5, seconds=30)
    ).isoformat()
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )

    assert result["owner_payload"]["plan"]["plan_kind"] == "activate"


def test_plan_deduplication_retains_earliest_evidence_expiry(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_ref = payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0]
    earliest_expiry = NOW + timedelta(minutes=6)
    source_ref["expires_at"] = earliest_expiry.isoformat()
    endpoint_refs = payload["subjects"][0]["endpoint"]["evidence"]["evidence_refs"]
    endpoint_refs[0] = {
        **source_ref,
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    result = app.prepare_plan(
        "aoa-kag",
        "read",
        "activate",
        expected_observation_digest=digest,
    )
    plan = result["owner_payload"]["plan"]
    retained = [
        item
        for item in plan["precondition_evidence"]
        if item["evidence_ref"] == source_ref["evidence_ref"]
    ]

    assert len(retained) == 1
    assert (
        datetime.fromisoformat(retained[0]["expires_at"].replace("Z", "+00:00"))
        == earliest_expiry
    )
    assert (
        datetime.fromisoformat(plan["expires_at"].replace("Z", "+00:00"))
        == earliest_expiry
    )


def test_plan_rejects_conflicting_duplicate_evidence_timestamps(
    tmp_path: Path,
) -> None:
    payload = observation(subject())
    source_ref = payload["subjects"][0]["source"]["evidence"]["evidence_refs"][0]
    endpoint_refs = payload["subjects"][0]["endpoint"]["evidence"]["evidence_refs"]
    endpoint_refs[0] = {
        **source_ref,
        "observed_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    app = application(tmp_path, policy_family="candidate", payload=payload)
    _, digest = app.store.load()

    with pytest.raises(StackMCPError, match="conflicting timestamps"):
        app.prepare_plan(
            "aoa-kag",
            "read",
            "activate",
            expected_observation_digest=digest,
        )


def test_read_and_candidate_servers_expose_disjoint_tools(tmp_path: Path) -> None:
    path = write_observation(tmp_path / "observation.json")
    read = build_server(path, policy_family="read")
    candidate = build_server(path, policy_family="candidate")
    read_tools = {tool.name for tool in asyncio.run(read.list_tools())}
    candidate_tools = {tool.name for tool in asyncio.run(candidate.list_tools())}
    assert read_tools == {"stack_runtime_catalog", "stack_runtime_inspect"}
    assert candidate_tools == {"stack_prepare_runtime_plan"}
    read_tool_contracts = {
        tool.name: tool.inputSchema for tool in asyncio.run(read.list_tools())
    }
    catalog_policy = read_tool_contracts["stack_runtime_catalog"]["properties"][
        "policy_family"
    ]
    inspect_policy = read_tool_contracts["stack_runtime_inspect"]["properties"][
        "policy_family"
    ]
    inspect_views = read_tool_contracts["stack_runtime_inspect"]["properties"]["view"][
        "enum"
    ]
    assert catalog_policy["anyOf"][0]["const"] == "read"
    assert inspect_policy["const"] == "read"
    assert "proof" in inspect_views
    assert "acceptance" in inspect_views


@pytest.mark.parametrize("view", ("proof", "acceptance"))
def test_portable_cli_exposes_governed_activation_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    view: str,
) -> None:
    path = write_observation(tmp_path / "observation.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abyss-stack-mcp",
            "--observation-path",
            str(path),
            "inspect",
            "aoa-kag",
            "read",
            "--view",
            view,
        ],
    )

    cli_main()

    result = json.loads(capsys.readouterr().out)
    assert result["owner_payload"]["view"] == view


@pytest.mark.parametrize(
    ("arguments", "expected_error"),
    (
        (
            ["inspect", "aoa-kag", "candidate"],
            "invalid choice",
        ),
        (
            [
                "--policy-family",
                "candidate",
                "inspect",
                "aoa-kag",
                "read",
            ],
            "inspect requires --policy-family read",
        ),
        (
            [
                "plan",
                "aoa-kag",
                "read",
                "restart",
                "--expected-observation-digest",
                DIGEST_A,
            ],
            "plan requires --policy-family candidate",
        ),
    ),
)
def test_portable_cli_rejects_cross_contour_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    expected_error: str,
) -> None:
    path = write_observation(tmp_path / "observation.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "abyss-stack-mcp",
            "--observation-path",
            str(path),
            *arguments,
        ],
    )

    with pytest.raises(SystemExit) as caught:
        cli_main()

    assert caught.value.code == 2
    assert expected_error in capsys.readouterr().err


def test_policy_contours_use_distinct_ports_credentials_and_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _contour("read") == (
        5431,
        "ABYSS_STACK_MCP_READ_BEARER_TOKEN",
        "abyss-stack-mcp-read-bearer-token",
        "abyss-stack-mcp:read",
    )
    assert _contour("candidate") == (
        5433,
        "ABYSS_STACK_MCP_CANDIDATE_BEARER_TOKEN",
        "abyss-stack-mcp-candidate-bearer-token",
        "abyss-stack-mcp:candidate",
    )
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / "aoa-mcp-http-bearer-token").write_text(
        "a" * 64,
        encoding="utf-8",
    )
    monkeypatch.setenv("AOA_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    monkeypatch.delenv("ABYSS_STACK_MCP_READ_BEARER_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="abyss-stack-mcp-read-bearer-token"):
        _auth_kwargs("read")

    (credentials / "abyss-stack-mcp-read-bearer-token").write_text(
        "r" * 64,
        encoding="utf-8",
    )
    assert "auth" in _auth_kwargs("read")
    with pytest.raises(
        SystemExit,
        match="abyss-stack-mcp-candidate-bearer-token",
    ):
        _auth_kwargs("candidate")

    (credentials / "abyss-stack-mcp-candidate-bearer-token").write_text(
        "c" * 64,
        encoding="utf-8",
    )
    assert "auth" in _auth_kwargs("candidate")
