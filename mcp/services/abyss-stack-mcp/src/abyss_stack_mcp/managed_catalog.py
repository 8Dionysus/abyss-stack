"""Build a private managed-contour catalog from owner registry and stack topology."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from .contracts import Identifier, NonEmpty, StrictModel
from .preflight import (
    ManagedContourBinding,
    ManagedContourCatalog,
    PreflightError,
    _safe_json,
)


class ManagedContourTopologyEntry(StrictModel):
    binding_id: Identifier
    organ_id: Identifier
    contour_id: Identifier
    service_id: Identifier
    unit_name: NonEmpty
    unit_path: NonEmpty
    endpoint_ref: NonEmpty
    protocol_version: NonEmpty
    credential_path: NonEmpty
    auth_manifest_path: NonEmpty
    auth_manifest_key: NonEmpty
    executable_path: NonEmpty
    executable_resolved_path: NonEmpty
    executable_digest: NonEmpty
    schema_paths: tuple[NonEmpty, ...] = Field(min_length=1)
    schema_bundle_digest: NonEmpty
    dependency_lock_path: NonEmpty | None = None
    owner_validator_path: NonEmpty
    owner_validator_digest: NonEmpty
    required_environment: dict[Identifier, NonEmpty]
    unit_credential_binding: NonEmpty
    unit_exec_start_binding: NonEmpty
    canary_receipt_path: NonEmpty
    canary_receipt_id: NonEmpty
    canary_observed_at: datetime
    canary_expires_at: datetime
    canary_deployment_manifest_id: NonEmpty
    canary_public_key_path: NonEmpty
    allowed_registry_states: tuple[Literal["shadow", "admitted"], ...] = ("admitted",)


class ManagedContourTopology(StrictModel):
    schema_version: Literal["abyss_mcp_managed_contour_topology_v1"] = (
        "abyss_mcp_managed_contour_topology_v1"
    )
    contours: tuple[ManagedContourTopologyEntry, ...] = Field(min_length=1)

    @field_validator("contours")
    @classmethod
    def require_unique(
        cls, value: tuple[ManagedContourTopologyEntry, ...]
    ) -> tuple[ManagedContourTopologyEntry, ...]:
        for identities in (
            [item.binding_id for item in value],
            [(item.organ_id, item.contour_id) for item in value],
        ):
            if len(identities) != len(set(identities)):
                raise ValueError("managed contour topology identities must be unique")
        return value


def build_managed_catalog(
    topology: ManagedContourTopology,
    *,
    registry_path: Path,
    deployment_manifest_path: Path,
    deployed_root: Path,
) -> ManagedContourCatalog:
    registry = _safe_json(registry_path, "v2 organ registry")
    if registry.get("schema_version") != "aoa_organ_registry_source_v2":
        raise PreflightError("managed catalog requires a v2 organ registry")
    bindings: list[ManagedContourBinding] = []
    for topology_entry in topology.contours:
        contour = _find_contour(
            registry, topology_entry.organ_id, topology_entry.contour_id
        )
        endpoint = contour.get("endpoint")
        if not isinstance(endpoint, dict):
            raise PreflightError("managed contour lacks an endpoint contract")
        if endpoint.get("endpoint_ref") != topology_entry.endpoint_ref:
            raise PreflightError("topology endpoint conflicts with owner registry")
        if topology_entry.protocol_version not in endpoint.get("protocol_versions", []):
            raise PreflightError("topology protocol is absent from owner registry")
        server_schema_digest = endpoint.get("server_schema_digest")
        if not isinstance(server_schema_digest, str):
            raise PreflightError("managed contour lacks an observed server schema")
        bindings.append(
            ManagedContourBinding(
                binding_id=topology_entry.binding_id,
                organ_id=topology_entry.organ_id,
                contour_id=topology_entry.contour_id,
                policy_family=contour["policy_family"],
                authority_class=contour["authority_class"],
                service_id=topology_entry.service_id,
                unit_name=topology_entry.unit_name,
                unit_path=topology_entry.unit_path,
                endpoint_ref=topology_entry.endpoint_ref,
                protocol_version=topology_entry.protocol_version,
                credential_class=contour["credential_class"],
                principal_id=contour["principal_id"],
                credential_path=topology_entry.credential_path,
                auth_manifest_path=topology_entry.auth_manifest_path,
                auth_manifest_key=topology_entry.auth_manifest_key,
                executable_path=topology_entry.executable_path,
                executable_resolved_path=topology_entry.executable_resolved_path,
                executable_digest=topology_entry.executable_digest,
                deployment_manifest_path=str(deployment_manifest_path),
                deployed_root=str(deployed_root),
                registry_path=str(registry_path),
                schema_paths=topology_entry.schema_paths,
                schema_bundle_digest=topology_entry.schema_bundle_digest,
                server_schema_digest=server_schema_digest,
                dependency_lock_path=topology_entry.dependency_lock_path,
                owner_validator_path=topology_entry.owner_validator_path,
                owner_validator_digest=topology_entry.owner_validator_digest,
                observation_route=contour["observation_route"],
                rollback_route=contour["rollback_route"],
                required_environment=topology_entry.required_environment,
                unit_credential_binding=topology_entry.unit_credential_binding,
                unit_exec_start_binding=topology_entry.unit_exec_start_binding,
                canary_receipt_path=topology_entry.canary_receipt_path,
                canary_receipt_id=topology_entry.canary_receipt_id,
                canary_observed_at=topology_entry.canary_observed_at,
                canary_expires_at=topology_entry.canary_expires_at,
                canary_deployment_manifest_id=(
                    topology_entry.canary_deployment_manifest_id
                ),
                canary_public_key_path=topology_entry.canary_public_key_path,
                allowed_registry_states=topology_entry.allowed_registry_states,
                allowed_mcp_names=tuple(contour["allowlist"]),
            )
        )
    return ManagedContourCatalog(contours=tuple(bindings))


def _find_contour(registry: dict, organ_id: str, contour_id: str) -> dict:
    for record in registry.get("records", []):
        if isinstance(record, dict) and record.get("organ_id") == organ_id:
            for contour in record.get("contours", []):
                if (
                    isinstance(contour, dict)
                    and contour.get("contour_id") == contour_id
                ):
                    return contour
    raise PreflightError("topology organ contour is absent from owner registry")


def publish_catalog(catalog: ManagedContourCatalog, output: Path) -> None:
    publish_private_json(catalog.model_dump(mode="json"), output)


def publish_private_json(payload_value: Any, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.is_symlink():
        raise PreflightError("managed catalog directory cannot be a symlink")
    payload = (
        json.dumps(payload_value, ensure_ascii=True, indent=2, sort_keys=True).encode()
        + b"\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-managed-catalog")
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--deployment-manifest", type=Path, required=True)
    parser.add_argument("--deployed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        topology = ManagedContourTopology.model_validate(
            _safe_json(args.topology, "managed contour topology")
        )
        catalog = build_managed_catalog(
            topology,
            registry_path=args.registry,
            deployment_manifest_path=args.deployment_manifest,
            deployed_root=args.deployed_root,
        )
        publish_catalog(catalog, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(catalog.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
