"""Fail-closed source/runtime preflight for managed MCP contours."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from .canary import (
    CanaryReceipt,
    CanaryRunnerError,
    _bootstrap_unit_name,
    _fallback_unit_name,
    _read_public_key,
    verify_canary_receipt,
)
from .contracts import Identifier, NonEmpty, StrictModel
from .core import canonical_json_bytes


class PreflightError(ValueError):
    """A preflight input is unsafe, malformed, or cannot be observed."""


class ManagedContourBinding(StrictModel):
    binding_id: Identifier
    organ_id: Identifier
    contour_id: Identifier
    policy_family: Literal["read", "candidate", "internal_effect", "external_effect"]
    authority_class: Literal[
        "read", "candidate", "proof_result", "internal_effect", "external_effect"
    ]
    service_id: Identifier
    unit_name: NonEmpty
    unit_path: NonEmpty
    endpoint_ref: NonEmpty
    protocol_version: NonEmpty
    credential_class: Identifier
    principal_id: Identifier
    credential_path: NonEmpty
    auth_manifest_path: NonEmpty
    auth_manifest_key: NonEmpty
    executable_path: NonEmpty
    executable_resolved_path: NonEmpty
    executable_digest: NonEmpty
    deployment_manifest_path: NonEmpty
    deployed_root: NonEmpty
    registry_path: NonEmpty
    schema_paths: tuple[NonEmpty, ...] = Field(min_length=1)
    schema_bundle_digest: NonEmpty
    server_schema_digest: NonEmpty
    dependency_lock_path: NonEmpty | None = None
    owner_validator_path: NonEmpty
    owner_validator_digest: NonEmpty
    observation_route: NonEmpty
    rollback_route: NonEmpty
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
    allowed_mcp_names: tuple[NonEmpty, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_authority(self) -> "ManagedContourBinding":
        if self.authority_class != "proof_result" and (
            self.authority_class != self.policy_family
        ):
            raise ValueError("authority class must match policy family")
        if self.authority_class == "proof_result" and self.policy_family != "read":
            raise ValueError("proof-result binding must remain read-policy")
        if len(self.allowed_mcp_names) != len(set(self.allowed_mcp_names)):
            raise ValueError("MCP allowlist must be unique")
        return self


class ManagedContourCatalog(StrictModel):
    schema_version: Literal["abyss_mcp_managed_contours_v1"] = (
        "abyss_mcp_managed_contours_v1"
    )
    contours: tuple[ManagedContourBinding, ...] = Field(min_length=1)

    @field_validator("contours")
    @classmethod
    def require_unique_contours(
        cls, value: tuple[ManagedContourBinding, ...]
    ) -> tuple[ManagedContourBinding, ...]:
        keys = [(item.organ_id, item.contour_id) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("managed organ contours must be unique")
        credentials = [item.credential_class for item in value]
        principals = [item.principal_id for item in value]
        if len(credentials) != len(set(credentials)):
            raise ValueError("managed credential classes must be contour-distinct")
        if len(principals) != len(set(principals)):
            raise ValueError("managed principals must be contour-distinct")
        binding_ids = [item.binding_id for item in value]
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("managed binding ids must be unique")
        return value


class PreflightCheck(StrictModel):
    check_id: Identifier
    status: Literal["passed", "blocked"]
    reason_code: Identifier | None = None
    expected_identity: NonEmpty | None = None
    observed_identity: NonEmpty | None = None
    evidence_ref: NonEmpty | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "PreflightCheck":
        if self.status == "passed" and self.reason_code is not None:
            raise ValueError("passed preflight checks cannot carry a reason")
        if self.status == "blocked" and self.reason_code is None:
            raise ValueError("blocked preflight checks require a reason")
        return self


class MCPPreflightReport(StrictModel):
    schema_version: Literal["abyss_mcp_preflight_report_v1"] = (
        "abyss_mcp_preflight_report_v1"
    )
    report_id: NonEmpty
    organ_id: Identifier
    contour_id: Identifier
    policy_family: Literal["read", "candidate", "internal_effect", "external_effect"]
    checked_at: datetime
    eligible_to_start: bool
    checks: tuple[PreflightCheck, ...]
    reason_codes: tuple[Identifier, ...]
    next_safe_step: NonEmpty
    restart_loop_allowed: Literal[False] = False
    owner_acceptance_inferred: Literal[False] = False
    registry_admission_inferred: Literal[False] = False
    contains_secrets: Literal[False] = False

    @field_validator("checked_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preflight timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


def run_preflight(
    binding: ManagedContourBinding,
    *,
    checked_at: datetime | None = None,
) -> MCPPreflightReport:
    now = checked_at or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise PreflightError("preflight timestamp must be timezone-aware")
    now = now.astimezone(timezone.utc)
    checks: list[PreflightCheck] = []

    registry = _safe_json(Path(binding.registry_path), "registry")
    contour = _registry_contour(registry, binding.organ_id, binding.contour_id)
    _check_equal(
        checks,
        "registry-schema",
        registry.get("schema_version"),
        "aoa_organ_registry_source_v2",
        "registry_schema_mismatch",
        binding.registry_path,
    )
    expiry = _timestamp(registry.get("expires_at"), "registry expiry")
    _check_bool(
        checks,
        "registry-current",
        expiry > now,
        "registry_source_expired",
        _format_time(expiry),
        _format_time(now),
        binding.registry_path,
    )
    _check_equal(
        checks,
        "registry-state",
        contour.get("registry_state"),
        binding.allowed_registry_states,
        "registry_state_blocked",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "policy-family",
        contour.get("policy_family"),
        binding.policy_family,
        "policy_family_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "authority-class",
        contour.get("authority_class"),
        binding.authority_class,
        "authority_class_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "credential-class",
        contour.get("credential_class"),
        binding.credential_class,
        "credential_class_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "principal",
        contour.get("principal_id"),
        binding.principal_id,
        "principal_identity_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "allowlist",
        sorted(contour.get("allowlist", [])),
        sorted(binding.allowed_mcp_names),
        "tool_allowlist_mismatch",
        binding.registry_path,
    )
    endpoint = (
        contour.get("endpoint") if isinstance(contour.get("endpoint"), dict) else {}
    )
    _check_equal(
        checks,
        "endpoint",
        endpoint.get("endpoint_ref"),
        binding.endpoint_ref,
        "endpoint_binding_mismatch",
        binding.registry_path,
    )
    _check_bool(
        checks,
        "protocol",
        binding.protocol_version in endpoint.get("protocol_versions", []),
        "protocol_binding_mismatch",
        binding.protocol_version,
        json.dumps(endpoint.get("protocol_versions", []), sort_keys=True),
        binding.registry_path,
    )
    _check_equal(
        checks,
        "observation-route",
        contour.get("observation_route"),
        binding.observation_route,
        "observation_route_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "rollback-route",
        contour.get("rollback_route"),
        binding.rollback_route,
        "rollback_route_mismatch",
        binding.registry_path,
    )

    manifest = _safe_json(Path(binding.deployment_manifest_path), "deployment manifest")
    _check_equal(
        checks,
        "deployment-parity",
        manifest.get("parity_state"),
        "exact",
        "deployment_parity_not_exact",
        binding.deployment_manifest_path,
    )
    service = _deployment_service(manifest, binding.service_id)
    source_revision = manifest.get("source", {}).get("revision")
    runtime_identity = contour.get("runtime_identity", {})
    _check_equal(
        checks,
        "source-revision",
        service.get("package_source_revision"),
        source_revision,
        "package_source_revision_mismatch",
        binding.deployment_manifest_path,
    )
    _check_equal(
        checks,
        "required-source-revision",
        runtime_identity.get("deployment_revision"),
        service.get("package_source_revision"),
        "required_source_revision_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "package-name",
        service.get("package_name"),
        runtime_identity.get("package_name"),
        "package_identity_mismatch",
        binding.deployment_manifest_path,
    )
    _check_equal(
        checks,
        "package-version",
        service.get("package_version"),
        runtime_identity.get("package_version"),
        "package_version_mismatch",
        binding.deployment_manifest_path,
    )
    _check_equal(
        checks,
        "package-digest",
        service.get("package_digest"),
        runtime_identity.get("package_digest"),
        "package_digest_mismatch",
        binding.deployment_manifest_path,
    )
    _check_equal(
        checks,
        "deployment-manifest-digest",
        _manifest_digest(manifest),
        runtime_identity.get("deployment_manifest_digest"),
        "deployment_manifest_digest_mismatch",
        binding.deployment_manifest_path,
    )

    receipt: CanaryReceipt | None = None
    canary_authenticated = False
    try:
        canary_payload = _safe_json(Path(binding.canary_receipt_path), "canary receipt")
        receipt = CanaryReceipt.model_validate(canary_payload)
        verify_canary_receipt(
            receipt,
            _read_public_key(Path(binding.canary_public_key_path)),
            checked_at=now,
            require_success=True,
        )
        canary_authenticated = True
    except (CanaryRunnerError, PreflightError, ValidationError):
        pass
    _check_bool(
        checks,
        "canary-authenticated-current",
        canary_authenticated,
        "canary_receipt_invalid_or_expired",
        "authenticated-successful-current",
        "invalid-or-expired",
        binding.canary_receipt_path,
    )
    if receipt is not None:
        _check_equal(
            checks,
            "canary-receipt-id",
            receipt.receipt_id,
            binding.canary_receipt_id,
            "canary_receipt_identity_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-observed-at",
            _format_time(receipt.observed_at),
            _format_time(binding.canary_observed_at),
            "canary_observation_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-expires-at",
            _format_time(receipt.expires_at),
            _format_time(binding.canary_expires_at),
            "canary_expiry_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-deployment",
            receipt.deployment_manifest_id,
            _manifest_digest(manifest),
            "canary_deployment_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "catalog-canary-deployment",
            binding.canary_deployment_manifest_id,
            _manifest_digest(manifest),
            "catalog_canary_deployment_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-organ",
            receipt.organ_id,
            binding.organ_id,
            "canary_organ_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-contour",
            receipt.policy_family,
            binding.policy_family,
            "canary_contour_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-service",
            receipt.deployment_service_id,
            service.get("service_id"),
            "canary_deployment_service_mismatch",
            binding.canary_receipt_path,
        )
        _check_bool(
            checks,
            "canary-process-unit",
            receipt.process_unit_name
            in {
                binding.unit_name,
                _bootstrap_unit_name(binding.unit_name),
                _fallback_unit_name(binding.unit_name),
            },
            "canary_process_unit_mismatch",
            "production-or-bounded-recovery-unit",
            receipt.process_unit_name,
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-source",
            receipt.deployment_source_revision,
            service.get("package_source_revision"),
            "canary_deployment_source_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-package",
            receipt.deployment_package_digest,
            service.get("package_digest"),
            "canary_deployment_package_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-tree",
            receipt.deployment_tree_digest,
            service.get("deployed_tree", {}).get("tree_digest"),
            "canary_deployment_tree_mismatch",
            binding.canary_receipt_path,
        )
        deployment_timestamp = _timestamp(
            manifest.get("deployed_at"), "deployment timestamp"
        )
        _check_equal(
            checks,
            "canary-deployed-at",
            _format_time(receipt.deployment_deployed_at),
            _format_time(deployment_timestamp),
            "canary_deployment_timestamp_mismatch",
            binding.canary_receipt_path,
        )
        _check_equal(
            checks,
            "canary-endpoint",
            receipt.endpoint_ref,
            binding.endpoint_ref,
            "canary_endpoint_mismatch",
            binding.canary_receipt_path,
        )
        _check_bool(
            checks,
            "canary-tool-authority",
            receipt.tool_name in binding.allowed_mcp_names,
            "canary_tool_not_allowed",
            _identity(binding.allowed_mcp_names),
            receipt.tool_name,
            binding.canary_receipt_path,
        )

    deployed_path = _bounded_deployed_path(binding, service)
    tree_digest = _tree_digest(deployed_path)
    expected_tree = service.get("deployed_tree", {}).get("tree_digest")
    _check_equal(
        checks,
        "deployed-tree",
        tree_digest,
        expected_tree,
        "deployed_tree_digest_mismatch",
        str(deployed_path),
    )
    _check_equal(
        checks,
        "required-deployed-tree",
        tree_digest,
        runtime_identity.get("deployed_tree_digest"),
        "required_deployed_tree_digest_mismatch",
        binding.registry_path,
    )

    executable_path = Path(binding.executable_path)
    executable = executable_path.is_file() and os.access(executable_path, os.X_OK)
    _check_bool(
        checks,
        "executable",
        executable,
        "executable_unavailable",
        binding.executable_path,
        "unavailable",
        binding.executable_path,
    )
    resolved_executable = (
        str(executable_path.resolve(strict=False)) if executable else None
    )
    _check_equal(
        checks,
        "executable-realpath",
        resolved_executable,
        binding.executable_resolved_path,
        "executable_realpath_mismatch",
        binding.executable_path,
    )
    executable_digest = (
        _sha256_file(Path(resolved_executable))
        if resolved_executable is not None
        else None
    )
    _check_equal(
        checks,
        "executable-digest",
        executable_digest,
        binding.executable_digest,
        "executable_digest_mismatch",
        binding.executable_path,
    )
    credential = _regular_file(Path(binding.credential_path), "credential", mode=0o600)
    _check_bool(
        checks,
        "credential-file",
        credential,
        "credential_file_unsafe",
        "regular-non-symlink-0600",
        "unsafe-or-missing",
        binding.credential_path,
    )
    auth_manifest = _safe_json(Path(binding.auth_manifest_path), "auth manifest")
    expected_credential_digest = _manifest_credential_digest(
        auth_manifest, binding.auth_manifest_key, binding.policy_family
    )
    observed_credential_digest = (
        _credential_value_digest(Path(binding.credential_path)) if credential else None
    )
    _check_equal(
        checks,
        "credential-identity",
        observed_credential_digest,
        expected_credential_digest,
        "credential_identity_mismatch",
        binding.auth_manifest_path,
    )

    schema_digest = _bundle_digest(tuple(Path(item) for item in binding.schema_paths))
    _check_equal(
        checks,
        "schema-bundle-digest",
        schema_digest,
        binding.schema_bundle_digest,
        "schema_bundle_digest_mismatch",
        binding.registry_path,
    )
    _check_equal(
        checks,
        "server-schema-digest",
        endpoint.get("server_schema_digest"),
        binding.server_schema_digest,
        "server_schema_digest_mismatch",
        binding.registry_path,
    )
    validator_ok = _regular_file(Path(binding.owner_validator_path), "owner validator")
    _check_bool(
        checks,
        "owner-validator",
        validator_ok,
        "owner_validator_unavailable",
        binding.owner_validator_path,
        "unavailable",
        binding.owner_validator_path,
    )
    validator_digest = (
        _sha256_file(Path(binding.owner_validator_path)) if validator_ok else None
    )
    _check_equal(
        checks,
        "owner-validator-digest",
        validator_digest,
        binding.owner_validator_digest,
        "owner_validator_digest_mismatch",
        binding.owner_validator_path,
    )

    unit_ok = _regular_file(Path(binding.unit_path), "unit")
    _check_bool(
        checks,
        "unit-file",
        unit_ok,
        "unit_file_unavailable",
        binding.unit_path,
        "unavailable",
        binding.unit_path,
    )
    unit_text = Path(binding.unit_path).read_text(encoding="utf-8") if unit_ok else ""
    for key, value in sorted(binding.required_environment.items()):
        needle = f"Environment={key}={value}"
        _check_bool(
            checks,
            f"unit-env-{key.lower().replace('_', '-')}",
            needle in unit_text,
            "unit_environment_mismatch",
            needle,
            "absent",
            binding.unit_path,
        )
    _check_bool(
        checks,
        "unit-credential-binding",
        binding.unit_credential_binding in unit_text.splitlines(),
        "unit_credential_binding_mismatch",
        binding.unit_credential_binding,
        "absent",
        binding.unit_path,
    )
    exec_start_lines = tuple(
        line for line in unit_text.splitlines() if line.startswith("ExecStart=")
    )
    _check_bool(
        checks,
        "unit-exec-start-binding",
        exec_start_lines == (binding.unit_exec_start_binding,),
        "unit_exec_start_binding_mismatch",
        binding.unit_exec_start_binding,
        _identity(exec_start_lines),
        binding.unit_path,
    )

    if binding.dependency_lock_path is not None:
        lock_path = Path(binding.dependency_lock_path)
        lock_ok = _regular_file(lock_path, "dependency lock")
        _check_bool(
            checks,
            "dependency-lock",
            lock_ok,
            "dependency_lock_unavailable",
            str(lock_path),
            "unavailable",
            str(lock_path),
        )
        expected_lock = service.get("dependency_lock_digest")
        observed_lock = _sha256_file(lock_path) if lock_ok else None
        _check_equal(
            checks,
            "dependency-graph",
            observed_lock,
            expected_lock,
            "dependency_graph_mismatch",
            binding.deployment_manifest_path,
        )

    reasons = tuple(
        dict.fromkeys(
            item.reason_code for item in checks if item.reason_code is not None
        )
    )
    eligible = not reasons
    unsigned = {
        "organ_id": binding.organ_id,
        "contour_id": binding.contour_id,
        "policy_family": binding.policy_family,
        "checked_at": _format_time(now),
        "eligible_to_start": eligible,
        "checks": [item.model_dump(mode="json") for item in checks],
        "reason_codes": list(reasons),
    }
    return MCPPreflightReport(
        report_id=_digest(unsigned),
        organ_id=binding.organ_id,
        contour_id=binding.contour_id,
        policy_family=binding.policy_family,
        checked_at=now,
        eligible_to_start=eligible,
        checks=tuple(checks),
        reason_codes=reasons,
        next_safe_step=(
            "start managed contour"
            if eligible
            else f"repair {reasons[0]} and rerun this exact preflight"
        ),
    )


def load_catalog(path: Path) -> ManagedContourCatalog:
    return ManagedContourCatalog.model_validate(
        _safe_json(path, "managed contour catalog")
    )


def find_binding(
    catalog: ManagedContourCatalog, organ_id: str, contour_id: str
) -> ManagedContourBinding:
    matches = [
        item
        for item in catalog.contours
        if (item.organ_id, item.contour_id) == (organ_id, contour_id)
    ]
    if len(matches) != 1:
        raise PreflightError("managed contour binding is absent or ambiguous")
    return matches[0]


def find_binding_id(
    catalog: ManagedContourCatalog, binding_id: str
) -> ManagedContourBinding:
    matches = [item for item in catalog.contours if item.binding_id == binding_id]
    if len(matches) != 1:
        raise PreflightError("managed contour binding id is absent or ambiguous")
    return matches[0]


def publish_report(report: MCPPreflightReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.is_symlink():
        raise PreflightError("preflight report directory cannot be a symlink")
    payload = (
        json.dumps(
            report.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True
        ).encode()
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


def _registry_contour(
    registry: dict[str, Any], organ_id: str, contour_id: str
) -> dict[str, Any]:
    for record in registry.get("records", []):
        if isinstance(record, dict) and record.get("organ_id") == organ_id:
            for contour in record.get("contours", []):
                if (
                    isinstance(contour, dict)
                    and contour.get("contour_id") == contour_id
                ):
                    return contour
    raise PreflightError("registry organ contour is absent")


def _deployment_service(manifest: dict[str, Any], service_id: str) -> dict[str, Any]:
    matches = [
        item
        for item in manifest.get("services", [])
        if isinstance(item, dict) and item.get("service_id") == service_id
    ]
    if len(matches) != 1:
        raise PreflightError("deployment service identity is absent or ambiguous")
    return matches[0]


def _bounded_deployed_path(
    binding: ManagedContourBinding, service: dict[str, Any]
) -> Path:
    root = Path(binding.deployed_root).absolute()
    relative = Path(str(service.get("deployed_path", "")))
    path = (root / relative).absolute()
    if root not in path.parents:
        raise PreflightError("deployment service path escapes the deployed root")
    return path


def _safe_json(path: Path, label: str) -> dict[str, Any]:
    if not _regular_file(path, label):
        raise PreflightError(f"{label} must be a regular non-symlink file")
    if path.stat().st_size > 4 * 1024 * 1024:
        raise PreflightError(f"{label} exceeds the 4 MiB bound")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise PreflightError(f"{label} must contain a JSON object")
    return payload


def _regular_file(
    path: Path, label: str, *, mode: int | None = None, executable: bool = False
) -> bool:
    absolute = path.expanduser().absolute()
    for component in (*reversed(absolute.parents), absolute):
        if component.exists() or component.is_symlink():
            if component.is_symlink():
                return False
    if not absolute.is_file():
        return False
    metadata = absolute.stat()
    if mode is not None and stat.S_IMODE(metadata.st_mode) != mode:
        return False
    if executable and not os.access(absolute, os.X_OK):
        return False
    return True


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise PreflightError("deployed package must be a non-symlink directory")
    ignored_dirs = {".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__"}
    records: list[dict[str, Any]] = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        current = Path(directory)
        names[:] = sorted(
            name
            for name in names
            if name not in ignored_dirs and not name.endswith(".egg-info")
        )
        for name in names:
            if (current / name).is_symlink():
                raise PreflightError("deployed package contains a directory symlink")
        for name in sorted(files):
            path = current / name
            relative = path.relative_to(root)
            if (
                name == ".coverage"
                or path.suffix == ".pyc"
                or any(part in ignored_dirs for part in relative.parts)
            ):
                continue
            if path.is_symlink() or not path.is_file():
                raise PreflightError("deployed package contains a non-regular file")
            metadata = path.stat()
            records.append(
                {
                    "path": relative.as_posix(),
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "size": metadata.st_size,
                    "sha256": _sha256_file(path),
                }
            )
    records.sort(key=lambda item: item["path"])
    return _digest(records)


def _bundle_digest(paths: tuple[Path, ...]) -> str:
    records = []
    for path in sorted(paths, key=str):
        if not _regular_file(path, "schema"):
            raise PreflightError("schema bundle contains an unsafe or missing file")
        records.append({"path": str(path), "sha256": _sha256_file(path)})
    return _digest(records)


def _manifest_credential_digest(
    manifest: dict[str, Any], key: str, policy_family: str
) -> str | None:
    credentials = manifest.get("credentials")
    if isinstance(credentials, dict):
        item = credentials.get(key)
        if not isinstance(item, dict) or item.get("policy_family") != policy_family:
            return None
        value = item.get("sha256")
    else:
        value = manifest.get(f"{key}_sha256")
    if not isinstance(value, str) or len(value) != 64:
        return None
    return "sha256:" + value


def _credential_value_digest(path: Path) -> str:
    payload = path.read_bytes()
    if not payload or len(payload) > 4096:
        raise PreflightError("credential value is empty or exceeds its bound")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PreflightError("credential value is not UTF-8") from exc
    token = text.strip()
    if not token or any(character.isspace() for character in token):
        raise PreflightError("credential value contains whitespace")
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _manifest_digest(manifest: dict[str, Any]) -> str:
    claimed = manifest.get("manifest_id")
    return claimed if isinstance(claimed, str) else _digest(manifest)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise PreflightError(f"{label} must be an RFC 3339 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise PreflightError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PreflightError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _identity(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
    return str(value)


def _check_equal(
    checks: list[PreflightCheck],
    check_id: str,
    observed: Any,
    expected: Any,
    reason: str,
    evidence: str,
) -> None:
    matched = (
        observed in expected if isinstance(expected, tuple) else observed == expected
    )
    checks.append(
        PreflightCheck(
            check_id=check_id,
            status="passed" if matched else "blocked",
            reason_code=None if matched else reason,
            expected_identity=_identity(expected),
            observed_identity=_identity(observed),
            evidence_ref=evidence,
        )
    )


def _check_bool(
    checks: list[PreflightCheck],
    check_id: str,
    matched: bool,
    reason: str,
    expected: str,
    observed: str,
    evidence: str,
) -> None:
    checks.append(
        PreflightCheck(
            check_id=check_id,
            status="passed" if matched else "blocked",
            reason_code=None if matched else reason,
            expected_identity=expected,
            observed_identity=observed,
            evidence_ref=evidence,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-preflight")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--organ-id")
    parser.add_argument("--contour-id")
    parser.add_argument("--binding-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.catalog)
        if args.binding_id is not None:
            binding = find_binding_id(catalog, args.binding_id)
        elif args.organ_id is not None and args.contour_id is not None:
            binding = find_binding(catalog, args.organ_id, args.contour_id)
        else:
            raise PreflightError("--binding-id or --contour-id is required")
        report = run_preflight(binding)
    except (OSError, PreflightError, ValidationError) as exc:
        parser.error(str(exc))
    if args.output is not None:
        publish_report(report, args.output)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=True, sort_keys=True))
    return 0 if report.eligible_to_start else 1


if __name__ == "__main__":
    raise SystemExit(main())
