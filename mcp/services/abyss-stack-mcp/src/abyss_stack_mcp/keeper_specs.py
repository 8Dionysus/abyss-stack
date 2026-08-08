"""Build protocol-independent Admission Keeper specs from exact contour inputs."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .contracts import Identifier, NonEmpty, StrictModel
from .preflight import ManagedContourCatalog, PreflightError, _digest, _safe_json


ZERO_DIGEST = "sha256:" + "0" * 64


class KeeperSpecBuildEntry(StrictModel):
    organ_id: Identifier
    contour_id: Identifier
    spec_path: NonEmpty
    spec_id: NonEmpty
    expires_at: datetime
    already_expired: bool


class KeeperSpecBuildStatus(StrictModel):
    schema_version: Literal["abyss_mcp_keeper_spec_build_v1"] = (
        "abyss_mcp_keeper_spec_build_v1"
    )
    generated_at: datetime
    registry_digest: NonEmpty
    entries: tuple[KeeperSpecBuildEntry, ...] = Field(min_length=1)
    owner_evidence_fabricated: Literal[False] = False
    owner_tools_executed: Literal[False] = False
    registry_mutation_performed: Literal[False] = False


def build_keeper_specs(
    registry: dict[str, Any],
    catalog: ManagedContourCatalog,
    *,
    output_root: Path,
    generated_at: datetime | None = None,
) -> KeeperSpecBuildStatus:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    registry_authored = _timestamp(registry.get("authored_at"), "registry authored_at")
    registry_expiry = _timestamp(registry.get("expires_at"), "registry expires_at")
    registry_digest = _digest(registry)
    entries: list[KeeperSpecBuildEntry] = []
    for binding in catalog.contours:
        record, contour = _find_record_contour(
            registry, binding.organ_id, binding.contour_id
        )
        spec = _build_spec(
            registry,
            record,
            contour,
            binding.model_dump(mode="json"),
            registry_digest=registry_digest,
            authored_at=registry_authored,
            expires_at=registry_expiry,
        )
        relative = Path(binding.organ_id) / f"{binding.contour_id}.json"
        destination = output_root / "specs" / relative
        _atomic_json(destination, spec)
        entries.append(
            KeeperSpecBuildEntry(
                organ_id=binding.organ_id,
                contour_id=binding.contour_id,
                spec_path=str(destination),
                spec_id=spec["spec_id"],
                expires_at=registry_expiry,
                already_expired=registry_expiry <= now,
            )
        )
    status = KeeperSpecBuildStatus(
        generated_at=now,
        registry_digest=registry_digest,
        entries=tuple(entries),
    )
    _atomic_json(output_root / "spec-build-status.json", status.model_dump(mode="json"))
    return status


def _build_spec(
    registry: dict[str, Any],
    record: dict[str, Any],
    contour: dict[str, Any],
    binding: dict[str, Any],
    *,
    registry_digest: str,
    authored_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    owners = record.get("owners")
    if not isinstance(owners, dict):
        raise PreflightError("keeper spec requires the full owner map")
    runtime = contour.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise PreflightError("keeper spec requires contour runtime identity")
    source_owner = _required(owners, "source_owner")
    runtime_owner = _required(owners, "runtime_owner")
    proof_owner = _required(owners, "proof_owner")
    acceptance_owner = _required(owners, "acceptance_owner")
    control_owner = _required(owners, "control_owner")
    consumer_owner = str(registry.get("workspace_owner") or "operator")
    stage_inputs: list[tuple[str, str, Any, bool, int, int]] = [
        (
            "owner_source",
            source_owner,
            {
                "source_revision": runtime.get("source_revision"),
                "source_tree_digest": runtime.get("source_tree_digest"),
            },
            source_owner == runtime_owner,
            300,
            5,
        ),
        ("package", runtime_owner, _subset(runtime, "package_name", "package_version", "package_digest"), True, 300, 10),
        ("deployment", runtime_owner, _subset(runtime, "deployment_revision", "deployment_manifest_digest", "deployed_tree_digest"), True, 300, 10),
        ("process", runtime_owner, {"process_ref": runtime.get("process_ref"), "process_identity": runtime.get("process_identity"), "unit_name": binding["unit_name"], "executable_path": binding["executable_path"]}, True, 120, 5),
        ("endpoint", runtime_owner, contour.get("endpoint"), True, 120, 5),
        ("credential", runtime_owner, _subset(contour, "credential_class", "principal_id"), True, 120, 5),
        ("schema", runtime_owner, {"server_schema_digest": binding["server_schema_digest"], "schema_bundle_digest": binding["schema_bundle_digest"], "owner_validator_digest": binding["owner_validator_digest"]}, True, 300, 10),
        ("authenticated_canary", runtime_owner, {"endpoint_ref": binding["endpoint_ref"], "allowlist": contour.get("allowlist"), "observation_route": contour.get("observation_route")}, True, 300, 25),
        ("owner_grounding", acceptance_owner, {"owner_watermark": contour.get("owner_watermark"), "owner_watermark_evidence": contour.get("owner_watermark_evidence"), "freshness_evidence": contour.get("freshness_evidence")}, False, 300, 40),
        ("central_proof", proof_owner, contour.get("proof_refs", []), False, 600, 100),
        ("owner_acceptance", acceptance_owner, contour.get("acceptance_refs", []), False, 600, 100),
        ("rollback", proof_owner, {"rollback_route": contour.get("rollback_route"), "last_good": contour.get("last_good")}, False, 600, 50),
        ("registry_admission", control_owner, {"registry_digest": registry_digest, "record": contour}, False, 300, 25),
        ("consumer_observation", consumer_owner, contour.get("consumer_compatibility", []), False, 300, 25),
    ]
    stages = []
    previous: str | None = None
    for stage, owner, subject, automatic, maximum_age, cost in stage_inputs:
        dependencies = [] if previous is None else [previous]
        stages.append(
            {
                "stage": stage,
                "owner": owner,
                "validator_ref": _validator_ref(stage, owner, binding),
                "validator_revision": binding["owner_validator_digest"],
                "validator_schema_digest": binding["schema_bundle_digest"],
                "subject_digest": _digest(subject),
                "dependency_stages": dependencies,
                "maximum_age_seconds": maximum_age,
                "cost_weight": cost,
                "automatic_execution_allowed": automatic,
            }
        )
        previous = stage
    target_digest = _digest(contour)
    return {
        "schema_version": "aoa_admission_keeper_spec_v1",
        "spec_id": ZERO_DIGEST,
        "organ_id": record["organ_id"],
        "contour_id": contour["contour_id"],
        "transaction_ref": (
            f"keeper://{record['organ_id']}/{contour['contour_id']}/"
            f"{registry_digest}"
        ),
        "registry_anchor_digest": registry_digest,
        "target_record_digest": target_digest,
        "authored_at": authored_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "stages": stages,
    }


def _validator_ref(stage: str, owner: str, binding: dict[str, Any]) -> str:
    if stage in {"owner_source", "package", "deployment", "process", "endpoint", "credential", "schema"}:
        return f"file://{binding['owner_validator_path']}#{stage}"
    return f"owner://{owner}/admission-validator/{stage}"


def _find_record_contour(
    registry: dict[str, Any], organ_id: str, contour_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    for record in registry.get("records", []):
        if isinstance(record, dict) and record.get("organ_id") == organ_id:
            for contour in record.get("contours", []):
                if isinstance(contour, dict) and contour.get("contour_id") == contour_id:
                    return record, contour
    raise PreflightError("keeper contour is absent from registry")


def _required(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise PreflightError(f"keeper owner map lacks {key}")
    return value


def _subset(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: payload.get(key) for key in keys}


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise PreflightError(f"{label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PreflightError(f"{label} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreflightError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise PreflightError("keeper output directory cannot be a symlink")
    rendered = json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-keeper-specs")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        registry = _safe_json(args.registry, "v2 organ registry")
        catalog = ManagedContourCatalog.model_validate(
            _safe_json(args.catalog, "managed contour catalog")
        )
        status = build_keeper_specs(
            registry,
            catalog,
            output_root=args.output_root,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(status.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
