from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import abyss_stack_mcp.canary as canary
from abyss_stack_mcp.canary import (
    CANARY_PUBLIC_KEY_NAME,
    CANARY_SIGNING_KEY_NAME,
    CanaryDeploymentBinding,
    CanaryInventoryCounts,
    CanaryProbeResult,
    CanaryRunnerError,
    build_overlay,
    build_receipt as _build_receipt,
    build_result_artifact,
    live_probe,
    run_canary,
    validate_result_contract,
    verify_canary_receipt,
)
from abyss_stack_mcp.observation import (
    RuntimeCanaryContract,
    RuntimeTarget,
    RuntimeTargetCatalog,
)


NOW = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
DIGEST_A = "sha256:" + ("a" * 64)
DIGEST_B = "sha256:" + ("b" * 64)
SIGNING_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PROCESS_IDENTITY = "systemd-user:aoa-organ-mcp-read@aoa-kag.service:pid:321:start:654"


def build_receipt(**kwargs: object):
    kwargs.setdefault("process_identity", PROCESS_IDENTITY)
    return _build_receipt(**kwargs)


def process_identity_reader(
    selected_target: RuntimeTarget,
    deployment_revision: str,
    observed_at: datetime,
) -> str:
    assert selected_target.unit_name == "aoa-organ-mcp-read@aoa-kag.service"
    assert deployment_revision == "a" * 40
    assert observed_at == NOW
    return PROCESS_IDENTITY


def canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def write_signing_key(secret_dir: Path) -> Path:
    path = secret_dir / CANARY_SIGNING_KEY_NAME
    path.write_bytes(
        SIGNING_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    path.chmod(0o600)
    return path


def write_public_key(secret_dir: Path) -> Path:
    path = secret_dir / CANARY_PUBLIC_KEY_NAME
    path.write_bytes(
        SIGNING_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    path.chmod(0o600)
    return path


def verify_signature(payload: dict, id_field: str) -> None:
    signature = payload.pop("attestation")
    assert payload[id_field].startswith("sha256:")
    try:
        SIGNING_KEY.public_key().verify(
            base64.urlsafe_b64decode(signature + "=="),
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
    except InvalidSignature as exc:
        raise AssertionError("capture signature did not verify") from exc


def canary_contract() -> RuntimeCanaryContract:
    return RuntimeCanaryContract(
        tool_name="kag_discover",
        arguments={"owner": "aoa-kag", "detail": "compact"},
        schema_pointer="/schema_version",
        schema_value="aoa-kag-mcp-capabilities-v1",
        required_pointers=(
            "/projection/digest",
            "/projection/updated_at",
        ),
        exact_values={"/projection/distribution/state": "active"},
        array_contains=(
            {
                "pointer": "/owners",
                "subset": {
                    "repo": "aoa-kag",
                    "manifest_uri": "aoa-kag://owners/aoa-kag/manifest",
                },
            },
        ),
    )


def target() -> RuntimeTarget:
    return RuntimeTarget(
        organ_id="aoa-kag",
        registry_organ_id="aoa-kag",
        service_id="aoa-kag-mcp",
        unit_name="aoa-organ-mcp-read@aoa-kag.service",
        executable_ref="/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py",
        endpoint_ref="http://127.0.0.1:5425/mcp",
        protocol_versions=("2025-11-25",),
        effect_classes=("observe",),
        canary_route="runbook://mcp-canary/aoa-kag/read",
        canary_contract=canary_contract(),
        rollback_route="runbook://mcp-rollback/aoa-kag/read",
    )


def deployment_binding() -> CanaryDeploymentBinding:
    return CanaryDeploymentBinding(
        manifest_id="sha256:" + "1" * 64,
        service_id="aoa-kag-mcp",
        package_source_revision="a" * 40,
        package_digest="sha256:" + "3" * 64,
        deployed_tree_digest="sha256:" + "4" * 64,
        deployed_at=NOW - timedelta(minutes=1),
    )


def write_deployment_manifest(tmp_path: Path) -> Path:
    binding = deployment_binding()
    body = {
        "schema_version": "abyss_stack_mcp_deployment_manifest_v1",
        "digest_scope": "abyss_stack_mcp_deployment_body_v1",
        "provider": "abyss-stack",
        "contains_secrets": False,
        "parity_state": "exact",
        "deployed_at": binding.deployed_at.isoformat(),
        "source": {"revision": binding.package_source_revision},
        "services": [
            {
                "service_id": binding.service_id,
                "package_source_revision": binding.package_source_revision,
                "package_digest": binding.package_digest,
                "deployed_tree": {
                    "tree_digest": binding.deployed_tree_digest,
                },
            }
        ],
    }
    manifest_id = canonical_digest(body)
    relative_record = (
        "Logs/mcp/deployments/records/" + manifest_id.removeprefix("sha256:") + ".json"
    )
    manifest = {
        **body,
        "manifest_id": manifest_id,
        "record_ref": relative_record,
        "latest_ref": "Logs/mcp/deployments/latest.json",
    }
    deployment_root = tmp_path / "Logs/mcp/deployments"
    latest = write_json(deployment_root / "latest.json", manifest)
    write_json(
        deployment_root / "records" / Path(relative_record).name,
        manifest,
    )
    return latest


def grounded_result() -> dict:
    return {
        "schema_version": "aoa-kag-mcp-capabilities-v1",
        "owners": [
            {
                "repo": "aoa-kag",
                "manifest_uri": "aoa-kag://owners/aoa-kag/manifest",
            }
        ],
        "projection": {
            "digest": DIGEST_A,
            "updated_at": "2026-07-28T14:59:00Z",
            "distribution": {"state": "active"},
        },
    }


def successful_probe() -> CanaryProbeResult:
    return CanaryProbeResult(
        protocol_version="2025-11-25",
        server_name="aoa-kag-mcp",
        server_version="0.1.0",
        server_schema_digest=DIGEST_A,
        selected_tool_schema_digest=DIGEST_B,
        inventory_counts=CanaryInventoryCounts(
            tools=5,
            resources=1,
            resource_templates=8,
            prompts=0,
        ),
        call_succeeded=True,
        result=grounded_result(),
        call_latency_ms=12,
        total_latency_ms=28,
    )


def write_json(path: Path, payload: object, *, mode: int = 0o640) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)
    return path


def test_result_contract_requires_each_independent_owner_anchor() -> None:
    matched, reasons, identity = validate_result_contract(
        grounded_result(),
        canary_contract(),
    )
    assert matched is True
    assert reasons == ()
    assert identity == "aoa-kag-mcp-capabilities-v1"

    missing_owner = grounded_result()
    missing_owner["owners"] = []
    matched, reasons, identity = validate_result_contract(
        missing_owner,
        canary_contract(),
    )
    assert matched is False
    assert reasons == ("canary-owner-result-evidence-missing",)
    assert identity == "aoa-kag-mcp-capabilities-v1"

    wrong_schema = grounded_result()
    wrong_schema["schema_version"] = "foreign-v1"
    matched, reasons, identity = validate_result_contract(
        wrong_schema,
        canary_contract(),
    )
    assert matched is False
    assert reasons == ("canary-result-schema-mismatch",)
    assert identity == "foreign-v1"


def test_receipt_is_content_addressed_and_preserves_claim_limit() -> None:
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=successful_probe(),
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    payload = receipt.model_dump(mode="json")
    verify_signature(payload, "receipt_id")
    receipt_id = payload.pop("receipt_id")

    assert receipt.schema_version == "abyss_stack_mcp_canary_receipt_v3"
    assert receipt_id == canonical_digest(payload)
    assert receipt.call_succeeded is True
    assert receipt.result_contract_matched is True
    assert receipt.result_schema_identity == "aoa-kag-mcp-capabilities-v1"
    assert receipt.result_digest == canonical_digest(grounded_result())
    assert receipt.result_artifact_ref == (
        "results/aoa-kag/" + receipt.result_digest.removeprefix("sha256:") + ".json"
    )
    assert receipt.reason_codes == ()
    assert receipt.process_unit_name == target().unit_name
    assert receipt.process_identity == PROCESS_IDENTITY
    assert "owner freshness" in receipt.claim_limit
    assert receipt.server_version == "0.1.0"


def test_receipt_verification_requires_current_success_and_pinned_signer() -> None:
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=successful_probe(),
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    verified = verify_canary_receipt(
        receipt,
        SIGNING_KEY.public_key(),
        checked_at=NOW,
        require_success=True,
    )
    assert verified.receipt_id == receipt.receipt_id

    with pytest.raises(CanaryRunnerError, match="expired"):
        verify_canary_receipt(
            receipt,
            SIGNING_KEY.public_key(),
            checked_at=receipt.expires_at,
            require_success=True,
        )

    wrong_key = Ed25519PrivateKey.from_private_bytes(bytes(reversed(range(32))))
    with pytest.raises(CanaryRunnerError, match="pinned public key"):
        verify_canary_receipt(
            receipt,
            wrong_key.public_key(),
            checked_at=NOW,
            require_success=True,
        )

    tampered = receipt.model_copy(update={"server_version": "tampered"})
    with pytest.raises(CanaryRunnerError, match="identity"):
        verify_canary_receipt(
            tampered,
            SIGNING_KEY.public_key(),
            checked_at=NOW,
            require_success=True,
        )

    bad_signature = receipt.model_copy(update={"attestation": "A" * 86})
    with pytest.raises(CanaryRunnerError, match="attestation"):
        verify_canary_receipt(
            bad_signature,
            SIGNING_KEY.public_key(),
            checked_at=NOW,
            require_success=True,
        )


def test_receipt_cannot_predate_its_bound_deployment() -> None:
    future_deployment = deployment_binding().model_copy(
        update={"deployed_at": NOW + timedelta(seconds=1)}
    )
    with pytest.raises(CanaryRunnerError, match="must follow its exact deployment"):
        build_receipt(
            target=target(),
            contract=canary_contract(),
            probe=successful_probe(),
            observed_at=NOW,
            ttl_seconds=600,
            signing_key=SIGNING_KEY,
            deployment=future_deployment,
        )


def test_receipt_verification_rejects_nonmatching_read() -> None:
    probe = successful_probe().model_copy(
        update={"result": {**grounded_result(), "owners": []}}
    )
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=probe,
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    with pytest.raises(CanaryRunnerError, match="successful matching read"):
        verify_canary_receipt(
            receipt,
            SIGNING_KEY.public_key(),
            checked_at=NOW,
            require_success=True,
        )


def test_private_result_artifact_is_independently_content_addressed() -> None:
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=successful_probe(),
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    artifact = build_result_artifact(
        receipt=receipt,
        owner_payload=grounded_result(),
        signing_key=SIGNING_KEY,
    )
    payload = artifact.model_dump(mode="json")
    verify_signature(payload, "artifact_id")
    artifact_id = payload.pop("artifact_id")

    assert artifact_id == canonical_digest(payload)
    assert artifact.result_digest == receipt.result_digest
    assert artifact.owner_payload == grounded_result()
    assert artifact.content_trust == "untrusted_data"
    assert artifact.instruction_authority == "none"
    assert "independent owner review" in artifact.claim_limit


def test_overlay_does_not_infer_grounding_consumer_freshness_or_proof() -> None:
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=successful_probe(),
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    receipt_ref = (
        "/srv/AbyssOS/abyss-stack/Logs/mcp/canaries/records/"
        f"aoa-kag/{receipt.receipt_id.removeprefix('sha256:')}.json"
    )
    overlay = build_overlay(receipt, receipt_ref=receipt_ref)
    subject = overlay.subjects[0]

    assert subject.endpoint is not None
    assert subject.endpoint.ready is True
    assert subject.endpoint.server_schema_digest == DIGEST_A
    assert subject.canary is not None
    assert subject.canary.succeeded is False
    assert subject.canary.result_grounded is False
    assert subject.canary.canary_ref is None
    assert subject.canary.evidence.state == "blocked"
    assert subject.canary.evidence.reason_codes == ("owner-grounding-review-required",)
    assert subject.consumers is None
    assert subject.freshness is None
    assert subject.proof is None
    assert subject.acceptance is None
    assert subject.rollback is None


def test_contract_mismatch_remains_visible_without_positive_canary() -> None:
    probe = successful_probe().model_copy(
        update={
            "result": {
                **grounded_result(),
                "owners": [],
            }
        }
    )
    receipt = build_receipt(
        target=target(),
        contract=canary_contract(),
        probe=probe,
        observed_at=NOW,
        ttl_seconds=600,
        signing_key=SIGNING_KEY,
        deployment=deployment_binding(),
    )
    overlay = build_overlay(
        receipt,
        receipt_ref="/private/canary/receipt.json",
    )
    canary = overlay.subjects[0].canary

    assert receipt.call_succeeded is True
    assert receipt.result_contract_matched is False
    assert receipt.reason_codes == ("canary-owner-result-evidence-missing",)
    assert canary is not None
    assert canary.succeeded is False
    assert canary.result_grounded is False
    assert canary.canary_ref is None
    assert canary.evidence.state == "blocked"


def test_run_canary_reads_one_owner_credential_and_writes_private_outputs(
    tmp_path: Path,
) -> None:
    targets_path = write_json(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target(),)).model_dump(mode="json"),
    )
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential_value = "wave1-private-value"
    credential_path = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential_path.write_text(credential_value + "\n", encoding="utf-8")
    credential_path.chmod(0o600)
    write_signing_key(secret_dir)
    observed_credentials: list[str] = []

    async def fake_probe(
        selected_target: RuntimeTarget,
        contract: RuntimeCanaryContract,
        credential: str,
        timeout_seconds: int,
    ) -> CanaryProbeResult:
        assert selected_target.organ_id == "aoa-kag"
        assert contract.tool_name == "kag_discover"
        assert timeout_seconds == 17
        observed_credentials.append(credential)
        return successful_probe()

    receipt, record_path, overlay_path, result_path = asyncio.run(
        run_canary(
            organ_id="aoa-kag",
            targets_path=targets_path,
            secret_dir=secret_dir,
            output_root=tmp_path / "private-output",
            deployment_manifest_path=write_deployment_manifest(tmp_path),
            timeout_seconds=17,
            clock=lambda: NOW,
            probe_runner=fake_probe,
            process_identity_reader=process_identity_reader,
        )
    )

    assert observed_credentials == [credential_value]
    assert receipt.result_contract_matched is True
    assert record_path.is_file()
    assert overlay_path.is_file()
    assert result_path is not None
    assert result_path.is_file()
    assert stat.S_IMODE(record_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(overlay_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(result_path.stat().st_mode) == 0o600
    assert credential_value not in record_path.read_text(encoding="utf-8")
    assert credential_value not in overlay_path.read_text(encoding="utf-8")
    assert credential_value not in result_path.read_text(encoding="utf-8")
    assert (
        json.loads(record_path.read_text(encoding="utf-8"))["receipt_id"]
        == receipt.receipt_id
    )
    result_artifact = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_artifact["result_digest"] == receipt.result_digest
    assert result_artifact["owner_payload"] == grounded_result()


def test_run_canary_rejects_tampered_claimed_deployment_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = write_deployment_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["services"][0]["package_digest"] = "sha256:" + "8" * 64
    write_json(manifest_path, manifest)

    with pytest.raises(CanaryRunnerError, match="content-address validation"):
        canary._read_deployment_binding(manifest_path, target())


def test_listener_wait_absorbs_only_bounded_startup_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class Writer:
        def close(self) -> None:
            pass

        async def wait_closed(self) -> None:
            pass

    async def connect(host: str, port: int) -> tuple[object, Writer]:
        nonlocal attempts
        assert host == "127.0.0.1"
        assert port == 5431
        attempts += 1
        if attempts < 3:
            raise ConnectionRefusedError
        return object(), Writer()

    monkeypatch.setattr(canary.asyncio, "open_connection", connect)
    remaining = asyncio.run(
        canary._wait_for_endpoint_listener("http://127.0.0.1:5431/mcp", 2)
    )

    assert attempts == 3
    assert remaining in {1, 2}


def test_listener_wait_rejects_non_loopback_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected(*args: object, **kwargs: object) -> tuple[object, object]:
        raise AssertionError("non-loopback endpoint must fail before connect")

    monkeypatch.setattr(canary.asyncio, "open_connection", unexpected)
    with pytest.raises(CanaryRunnerError, match="loopback HTTP"):
        asyncio.run(canary._wait_for_endpoint_listener("https://example.test/mcp", 2))


def test_last_known_good_canary_uses_distinct_committed_route(tmp_path: Path) -> None:
    targets_path = write_json(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target(),)).model_dump(mode="json"),
    )
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential_path = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential_path.write_text("private-value\n", encoding="utf-8")
    credential_path.chmod(0o600)
    write_signing_key(secret_dir)

    async def fake_probe(
        selected_target: RuntimeTarget,
        contract: RuntimeCanaryContract,
        credential: str,
        timeout_seconds: int,
    ) -> CanaryProbeResult:
        assert selected_target.canary_route == (
            "runbook://mcp-canary/aoa-kag/read/last-known-good"
        )
        return successful_probe()

    bootstrap_identity = (
        "systemd-user:aoa-organ-mcp-read-bootstrap@aoa-kag.service:pid:321:start:654"
    )

    def bootstrap_process_identity_reader(
        selected_target: RuntimeTarget,
        deployment_revision: str,
        observed_at: datetime,
    ) -> str:
        assert selected_target.unit_name == (
            "aoa-organ-mcp-read-bootstrap@aoa-kag.service"
        )
        assert deployment_revision == "a" * 40
        assert observed_at == NOW
        return bootstrap_identity

    receipt, _, _, _ = asyncio.run(
        run_canary(
            organ_id="aoa-kag",
            targets_path=targets_path,
            secret_dir=secret_dir,
            output_root=tmp_path / "rollback-canary",
            deployment_manifest_path=write_deployment_manifest(tmp_path),
            purpose="last-known-good",
            process_unit="bootstrap",
            clock=lambda: NOW,
            probe_runner=fake_probe,
            process_identity_reader=bootstrap_process_identity_reader,
        )
    )

    assert receipt.canary_route.endswith("/last-known-good")
    assert receipt.process_unit_name == ("aoa-organ-mcp-read-bootstrap@aoa-kag.service")
    assert receipt.process_identity == bootstrap_identity


def test_run_canary_rejects_process_change_during_probe(tmp_path: Path) -> None:
    targets_path = write_json(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target(),)).model_dump(mode="json"),
    )
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential_path = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential_path.write_text("private-value\n", encoding="utf-8")
    credential_path.chmod(0o600)
    write_signing_key(secret_dir)
    identities = iter(
        (
            PROCESS_IDENTITY,
            "systemd-user:aoa-organ-mcp-read@aoa-kag.service:pid:322:start:655",
        )
    )

    async def fake_probe(*args: object) -> CanaryProbeResult:
        return successful_probe()

    with pytest.raises(CanaryRunnerError, match="changed during the probe"):
        asyncio.run(
            run_canary(
                organ_id="aoa-kag",
                targets_path=targets_path,
                secret_dir=secret_dir,
                output_root=tmp_path / "race-output",
                deployment_manifest_path=write_deployment_manifest(tmp_path),
                clock=lambda: NOW,
                probe_runner=fake_probe,
                process_identity_reader=lambda *args: next(identities),
            )
        )


def test_canary_rejects_broad_or_symlinked_credential(tmp_path: Path) -> None:
    targets_path = write_json(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target(),)).model_dump(mode="json"),
    )
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential.write_text("private-value\n", encoding="utf-8")
    credential.chmod(0o644)

    with pytest.raises(CanaryRunnerError, match="group/world"):
        asyncio.run(
            run_canary(
                organ_id="aoa-kag",
                targets_path=targets_path,
                secret_dir=secret_dir,
                output_root=tmp_path / "output",
                deployment_manifest_path=write_deployment_manifest(tmp_path),
            )
        )

    credential.unlink()
    source = tmp_path / "source-value"
    source.write_text("private-value\n", encoding="utf-8")
    source.chmod(0o600)
    credential.symlink_to(source)
    with pytest.raises(CanaryRunnerError, match="symlink"):
        asyncio.run(
            run_canary(
                organ_id="aoa-kag",
                targets_path=targets_path,
                secret_dir=secret_dir,
                output_root=tmp_path / "output",
                deployment_manifest_path=write_deployment_manifest(tmp_path),
            )
        )


def test_canary_rejects_broad_or_symlinked_signing_key(tmp_path: Path) -> None:
    targets_path = write_json(
        tmp_path / "targets.json",
        RuntimeTargetCatalog(targets=(target(),)).model_dump(mode="json"),
    )
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(mode=0o700)
    credential = secret_dir / "aoa-kag-mcp-read-bearer-token"
    credential.write_text("private-value\n", encoding="utf-8")
    credential.chmod(0o600)
    signing_key = write_signing_key(secret_dir)
    signing_key.chmod(0o640)

    with pytest.raises(CanaryRunnerError, match="owner-only mode 0400 or 0600"):
        asyncio.run(
            run_canary(
                organ_id="aoa-kag",
                targets_path=targets_path,
                secret_dir=secret_dir,
                output_root=tmp_path / "output",
                deployment_manifest_path=write_deployment_manifest(tmp_path),
            )
        )

    signing_key.unlink()
    outside_key = tmp_path / "outside-signing-key.pem"
    outside_key.write_bytes(
        SIGNING_KEY.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    outside_key.chmod(0o600)
    signing_key.symlink_to(outside_key)
    with pytest.raises(CanaryRunnerError, match="symlink"):
        asyncio.run(
            run_canary(
                organ_id="aoa-kag",
                targets_path=targets_path,
                secret_dir=secret_dir,
                output_root=tmp_path / "output",
                deployment_manifest_path=write_deployment_manifest(tmp_path),
            )
        )


def test_canary_accepts_systemd_loadcredential_signing_key_mode(
    tmp_path: Path,
) -> None:
    secret_dir = tmp_path / "credentials"
    secret_dir.mkdir(mode=0o700)
    signing_key = write_signing_key(secret_dir)
    signing_key.chmod(0o400)

    loaded = canary._read_signing_key(signing_key)

    assert loaded.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ) == SIGNING_KEY.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_live_probe_uses_authenticated_http_and_observes_application_version(
    tmp_path: Path,
) -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    test_value = "v" * 64
    script = tmp_path / "canary_server.py"
    script.write_text(
        f"""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing import Any
from abyss_stack_mcp._http_auth import http_auth_kwargs

server = FastMCP(
    "aoa-kag-mcp",
    json_response=True,
    **http_auth_kwargs(
        {port},
        token_env_var="CANARY_TEST_READ_VALUE",
        credential_name="unused-canary-value",
        auth_scope="mcp:test:read",
        client_id="abyss-stack-mcp-canary:test",
    ),
)
server._mcp_server.version = "9.8.7"
read_only = server.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)

@read_only
def kag_discover(owner: str, detail: str = "compact") -> dict[str, Any]:
    return {{
        "schema_version": "aoa-kag-mcp-capabilities-v1",
        "owners": [{{
            "repo": owner,
            "manifest_uri": "aoa-kag://owners/aoa-kag/manifest",
        }}],
        "projection": {{
            "digest": "{DIGEST_A}",
            "updated_at": "2026-07-28T14:59:00Z",
            "distribution": {{"state": "active"}},
        }},
    }}

server.settings.host = "127.0.0.1"
server.settings.port = {port}
server.run(transport="streamable-http")
""",
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "AOA_MCP_TRANSPORT": "streamable-http",
        "AOA_MCP_HOST": "127.0.0.1",
        "AOA_MCP_PORT": str(port),
        "CANARY_TEST_READ_VALUE": test_value,
        "PYTHONPATH": os.pathsep.join(
            filter(
                None,
                (
                    str(Path(__file__).resolve().parents[1] / "src"),
                    os.environ.get("PYTHONPATH"),
                ),
            )
        ),
    }
    process = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            with socket.socket() as probe_socket:
                if probe_socket.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            raise AssertionError("fixture MCP server did not become ready")
        selected = target().model_copy(
            update={"endpoint_ref": f"http://127.0.0.1:{port}/mcp"}
        )
        probe = asyncio.run(
            live_probe(
                selected,
                canary_contract(),
                test_value,
                10,
            )
        )

        assert probe.call_succeeded is True
        assert probe.server_name == "aoa-kag-mcp"
        assert probe.server_version == "9.8.7"
        assert probe.protocol_version == "2025-11-25"
        assert probe.inventory_counts.tools == 1
        assert probe.result == grounded_result()

        with pytest.raises(CanaryRunnerError) as denied:
            asyncio.run(
                live_probe(
                    selected,
                    canary_contract(),
                    "x" * 64,
                    10,
                )
            )
        assert test_value not in str(denied.value)
    finally:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
    assert test_value not in stdout + stderr


def test_committed_catalog_covers_every_migration_wave_target() -> None:
    catalog = RuntimeTargetCatalog.model_validate_json(
        (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abyss_stack_mcp"
            / "runtime-targets.v1.json"
        ).read_text(encoding="utf-8")
    )
    reviewed = {
        item.organ_id for item in catalog.targets if item.canary_contract is not None
    }

    assert reviewed == {
        "aoa-kag",
        "aoa-stats",
        "aoa-decisions",
        "abyss-stack",
        "abyss-machine",
        "tree-of-sophia",
        "aoa-session-memory",
        "aoa-memo",
        "aoa-evals",
        "aoa-4pda-connector",
        "aoa-telegram-connector",
        "aoa-discord-connector",
        "aoa-course-connector",
        "aoa-stackoverflow-connector",
        "aoa-xda-connector",
    }


def test_session_memory_canary_tracks_the_bounded_admission_profile() -> None:
    catalog = RuntimeTargetCatalog.model_validate_json(
        (
            Path(__file__).resolve().parents[1]
            / "src"
            / "abyss_stack_mcp"
            / "runtime-targets.v1.json"
        ).read_text(encoding="utf-8")
    )
    target = next(
        item for item in catalog.targets if item.organ_id == "aoa-session-memory"
    )
    contract = target.canary_contract

    assert contract is not None
    assert contract.tool_name == "aoa_session_literal_query_plan"
    assert contract.arguments == {
        "filters": {},
        "kind": "mcp_service",
        "query": "MCP",
    }
    assert contract.schema_pointer == "/artifact_type"
    assert contract.schema_value == "session_memory_literal_query_plan"
    assert contract.exact_values["/mcp_access/capability_profile"] == (
        "session-evidence-read"
    )
    assert contract.exact_values["/mutates"] is False
    assert "/mcp_access/mutates" not in contract.exact_values
    assert "/truth_status" not in contract.required_pointers
