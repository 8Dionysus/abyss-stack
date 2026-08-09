"""Run one bounded authenticated read canary and emit a secret-free receipt."""

from __future__ import annotations

import argparse
import asyncio
import base64
import errno
import hashlib
import json
import os
import re
import stat
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field, ValidationError, field_validator, model_validator

from .contracts import (
    CanaryObservation,
    Digest,
    EndpointObservation,
    EvidenceRef,
    Identifier,
    LinkEvidence,
    NonEmpty,
    StrictModel,
)
from .core import _reject_secret_material, canonical_json_bytes
from .observation import (
    DEFAULT_TARGETS_PATH,
    ObservationProducerError,
    RuntimeCanaryContract,
    RuntimeEvidenceOverlay,
    RuntimeEvidenceOverlaySubject,
    RuntimeTarget,
    _load_deployment,
    _load_targets,
    _process_observation,
    _systemctl,
)


DEFAULT_SECRET_DIR = Path("/srv/AbyssOS/abyss-stack/Secrets/Configs")
DEFAULT_OUTPUT_ROOT = Path("/srv/AbyssOS/abyss-stack/Logs/mcp/canaries")
DEFAULT_DEPLOYMENT_MANIFEST = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/deployments/latest.json"
)
CANARY_SIGNING_KEY_NAME = "abyss-stack-mcp-canary-ed25519-private-key.pem"
CANARY_PUBLIC_KEY_NAME = "abyss-stack-mcp-canary-ed25519-public-key.pem"
MAX_CREDENTIAL_BYTES = 8 * 1024
MAX_SIGNING_KEY_BYTES = 4 * 1024
MAX_SCHEMA_BYTES = 2 * 1024 * 1024
MAX_RESULT_BYTES = 2 * 1024 * 1024
MAX_CANARY_FUTURE_SKEW = timedelta(seconds=30)
MAX_PAGES = 32
Ed25519Signature = Annotated[
    str,
    Field(min_length=86, max_length=86, pattern=r"^[A-Za-z0-9_-]{86}$"),
]
CanaryPurpose = Literal["current", "last-known-good"]
CanaryProcessUnit = Literal["production", "bootstrap"]


class CanaryRunnerError(ValueError):
    """Fail-closed canary error whose message never includes owner output."""


class CanaryInventoryCounts(StrictModel):
    tools: int = Field(ge=0, le=10_000)
    resources: int = Field(ge=0, le=10_000)
    resource_templates: int = Field(ge=0, le=10_000)
    prompts: int = Field(ge=0, le=10_000)


class CanaryProbeResult(StrictModel):
    protocol_version: NonEmpty
    server_name: NonEmpty
    server_version: NonEmpty
    server_schema_digest: Digest
    selected_tool_schema_digest: Digest
    inventory_counts: CanaryInventoryCounts
    call_succeeded: bool
    result: dict[str, Any] | None = None
    call_latency_ms: int = Field(ge=0, le=3_600_000)
    total_latency_ms: int = Field(ge=0, le=3_600_000)
    reason_codes: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_call(self) -> CanaryProbeResult:
        if self.call_succeeded and self.result is None:
            raise ValueError("a successful canary call requires structured result")
        if not self.call_succeeded and not self.reason_codes:
            raise ValueError("a failed canary call requires reason codes")
        return self


class CanaryDeploymentBinding(StrictModel):
    manifest_id: Digest
    service_id: Identifier
    package_source_revision: NonEmpty
    package_digest: Digest
    deployed_tree_digest: Digest
    deployed_at: datetime

    @field_validator("deployed_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canary deployment timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


class CanaryReceipt(StrictModel):
    schema_version: Literal["abyss_stack_mcp_canary_receipt_v3"] = (
        "abyss_stack_mcp_canary_receipt_v3"
    )
    receipt_id: Digest
    signer_id: Digest
    attestation_algorithm: Literal["ed25519"] = "ed25519"
    attestation: Ed25519Signature
    issuer: Literal["abyss-stack"] = "abyss-stack"
    consumer_id: Literal["abyss-stack-mcp-canary"] = "abyss-stack-mcp-canary"
    organ_id: Identifier
    policy_family: Literal["read"] = "read"
    service_id: Identifier
    endpoint_ref: NonEmpty
    deployment_manifest_id: Digest
    deployment_service_id: Identifier
    deployment_source_revision: NonEmpty
    deployment_package_digest: Digest
    deployment_tree_digest: Digest
    deployment_deployed_at: datetime
    process_unit_name: NonEmpty
    process_identity: NonEmpty
    canary_route: NonEmpty
    tool_name: Identifier
    tool_arguments_digest: Digest
    observed_at: datetime
    expires_at: datetime
    protocol_version: NonEmpty
    server_name: NonEmpty
    server_version: NonEmpty
    server_schema_digest: Digest
    selected_tool_schema_digest: Digest
    inventory_counts: CanaryInventoryCounts
    call_succeeded: bool
    result_contract_matched: bool
    result_schema_identity: NonEmpty | None = None
    result_digest: Digest | None = None
    result_artifact_ref: NonEmpty | None = None
    call_latency_ms: int = Field(ge=0, le=3_600_000)
    total_latency_ms: int = Field(ge=0, le=3_600_000)
    reason_codes: tuple[Identifier, ...] = ()
    contains_secrets: Literal[False] = False
    content_trust: Literal["untrusted_data"] = "untrusted_data"
    instruction_authority: Literal["none"] = "none"
    claim_limit: Literal[
        "This stack-issued receipt proves one authenticated loopback MCP "
        "schema observation, bounded read canary, and exact named-systemd "
        "process identity unchanged across the probe only. It does not prove "
        "owner grounding, owner freshness, owner acceptance, central proof, "
        "admission, or rollback."
    ] = (
        "This stack-issued receipt proves one authenticated loopback MCP "
        "schema observation, bounded read canary, and exact named-systemd "
        "process identity unchanged across the probe only. It does not prove "
        "owner grounding, owner freshness, owner acceptance, central proof, "
        "admission, or rollback."
    )

    @field_validator("observed_at", "expires_at", "deployment_deployed_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canary receipt timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_receipt(self) -> CanaryReceipt:
        if self.expires_at <= self.observed_at:
            raise ValueError("canary receipt expiry must follow observation")
        if self.observed_at < self.deployment_deployed_at:
            raise ValueError("canary receipt must follow its exact deployment")
        if self.service_id != self.deployment_service_id:
            raise ValueError("canary deployment service must match the target service")
        if (
            re.fullmatch(
                rf"systemd-user:{re.escape(self.process_unit_name)}:pid:[1-9][0-9]*:start:[1-9][0-9]*",
                self.process_identity,
            )
            is None
        ):
            raise ValueError("canary process identity must bind its named systemd unit")
        if self.result_contract_matched and not self.call_succeeded:
            raise ValueError(
                "a matching canary result contract requires a successful call"
            )
        if self.call_succeeded and (
            self.result_schema_identity is None
            or self.result_digest is None
            or self.result_artifact_ref is None
        ):
            raise ValueError(
                "a successful canary call requires result identity, digest, "
                "and artifact ref"
            )
        if not self.call_succeeded and self.result_artifact_ref is not None:
            raise ValueError("a failed canary call cannot publish a result artifact")
        if self.result_digest is not None and self.result_artifact_ref is not None:
            expected_ref = (
                f"results/{self.organ_id}/"
                f"{self.result_digest.removeprefix('sha256:')}.json"
            )
            if self.result_artifact_ref != expected_ref:
                raise ValueError(
                    "canary result artifact ref must match the result digest"
                )
        if self.result_contract_matched and self.reason_codes:
            raise ValueError(
                "a matching canary result contract cannot carry failure reasons"
            )
        if not self.result_contract_matched and not self.reason_codes:
            raise ValueError(
                "a non-matching canary result contract requires reason codes"
            )
        return self


class CanaryResultArtifact(StrictModel):
    schema_version: Literal["abyss_stack_mcp_canary_result_artifact_v2"] = (
        "abyss_stack_mcp_canary_result_artifact_v2"
    )
    artifact_id: Digest
    signer_id: Digest
    attestation_algorithm: Literal["ed25519"] = "ed25519"
    attestation: Ed25519Signature
    issuer: Literal["abyss-stack"] = "abyss-stack"
    organ_id: Identifier
    policy_family: Literal["read"] = "read"
    service_id: Identifier
    canary_route: NonEmpty
    tool_name: Identifier
    tool_arguments_digest: Digest
    observed_at: datetime
    result_schema_identity: NonEmpty
    result_digest: Digest
    owner_payload: dict[str, Any]
    contains_secrets: Literal[False] = False
    content_trust: Literal["untrusted_data"] = "untrusted_data"
    instruction_authority: Literal["none"] = "none"
    claim_limit: Literal[
        "This private artifact preserves one bounded MCP canary result for "
        "independent owner review. Stack capture and content addressing do "
        "not prove owner grounding, freshness, acceptance, central proof, "
        "admission, or rollback."
    ] = (
        "This private artifact preserves one bounded MCP canary result for "
        "independent owner review. Stack capture and content addressing do "
        "not prove owner grounding, freshness, acceptance, central proof, "
        "admission, or rollback."
    )

    @field_validator("observed_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canary result timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_result_digest(self) -> CanaryResultArtifact:
        if _digest(self.owner_payload) != self.result_digest:
            raise ValueError("canary result artifact digest must match owner payload")
        return self


ProbeRunner = Callable[
    [RuntimeTarget, RuntimeCanaryContract, str, int],
    Awaitable[CanaryProbeResult],
]
ProcessIdentityReader = Callable[[RuntimeTarget, str, datetime], str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _live_process_identity(
    target: RuntimeTarget,
    deployment_revision: str,
    observed_at: datetime,
) -> str:
    process = _process_observation(
        target,
        observed_at=observed_at,
        expires_at=observed_at + timedelta(minutes=5),
        deployment_revision=deployment_revision,
        runner=_systemctl,
    )
    if not process.active or process.process_identity is None:
        raise CanaryRunnerError("canary target process identity is not exact")
    return process.process_identity


def _bootstrap_unit_name(production_unit_name: str) -> str:
    if production_unit_name == "abyss-stack-mcp-read.service":
        return "abyss-stack-mcp-read-bootstrap.service"
    match = re.fullmatch(
        r"aoa-organ-mcp-read@([A-Za-z0-9_.@-]+)\.service",
        production_unit_name,
    )
    if match is None:
        raise CanaryRunnerError("canary target has no bounded bootstrap unit identity")
    return f"aoa-organ-mcp-read-bootstrap@{match.group(1)}.service"


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _signer_id(signing_key: Ed25519PrivateKey) -> str:
    return _public_signer_id(signing_key.public_key())


def _public_signer_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _signed_fields(
    payload: dict[str, Any],
    signing_key: Ed25519PrivateKey,
) -> dict[str, str]:
    return {
        "signer_id": _signer_id(signing_key),
        "attestation_algorithm": "ed25519",
        "attestation": _base64url(signing_key.sign(canonical_json_bytes(payload))),
    }


def _require_no_symlink_components(path: Path, label: str) -> Path:
    absolute = path.expanduser().absolute()
    for component in tuple(reversed(absolute.parents)) + (absolute,):
        if (component.exists() or component.is_symlink()) and component.is_symlink():
            raise CanaryRunnerError(f"{label} cannot traverse a symlink")
    return absolute


def _ensure_private_directory(path: Path) -> Path:
    absolute = _require_no_symlink_components(path, "canary output root")
    absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
    absolute = _require_no_symlink_components(absolute, "canary output root")
    if not absolute.is_dir():
        raise CanaryRunnerError("canary output root must be a non-symlink directory")
    mode = stat.S_IMODE(absolute.stat().st_mode)
    if mode & 0o077:
        raise CanaryRunnerError("canary output root must not be group/world accessible")
    return absolute


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path = _require_no_symlink_components(path, "canary output")
    parent = _ensure_private_directory(path.parent)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise CanaryRunnerError("canary output must be a regular non-symlink file")
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _read_credential(path: Path) -> str:
    path = _require_no_symlink_components(path, "canary read credential")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CanaryRunnerError(
                    "canary read credential must be a regular non-symlink file"
                )
            if stat.S_IMODE(metadata.st_mode) & 0o077:
                raise CanaryRunnerError(
                    "canary read credential must not be group/world accessible"
                )
            if not 1 <= metadata.st_size <= MAX_CREDENTIAL_BYTES:
                raise CanaryRunnerError(
                    "canary read credential has an invalid bounded size"
                )
            chunks: list[bytes] = []
            remaining = MAX_CREDENTIAL_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CanaryRunnerError(
                "canary read credential must be a regular non-symlink file"
            ) from exc
        raise CanaryRunnerError("canary read credential is unavailable") from exc
    if len(raw) > MAX_CREDENTIAL_BYTES:
        raise CanaryRunnerError("canary read credential exceeds its size limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise CanaryRunnerError("canary read credential is not valid text") from exc
    value = text[:-1] if text.endswith("\n") else text
    if not value or value != value.strip() or any(char.isspace() for char in value):
        raise CanaryRunnerError(
            "canary read credential must contain exactly one non-empty value"
        )
    return value


def _read_signing_key(path: Path) -> Ed25519PrivateKey:
    path = _require_no_symlink_components(path, "canary signing key")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CanaryRunnerError(
                    "canary signing key must be a regular non-symlink file"
                )
            if stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}:
                raise CanaryRunnerError(
                    "canary signing key must have owner-only mode 0400 or 0600"
                )
            if metadata.st_uid != os.geteuid():
                raise CanaryRunnerError(
                    "canary signing key must be owned by the current user"
                )
            if not 1 <= metadata.st_size <= MAX_SIGNING_KEY_BYTES:
                raise CanaryRunnerError(
                    "canary signing key has an invalid bounded size"
                )
            chunks: list[bytes] = []
            remaining = MAX_SIGNING_KEY_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(4096, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CanaryRunnerError(
                "canary signing key must be a regular non-symlink file"
            ) from exc
        raise CanaryRunnerError("canary signing key is unavailable") from exc
    if len(raw) > MAX_SIGNING_KEY_BYTES:
        raise CanaryRunnerError("canary signing key exceeds its size limit")
    try:
        signing_key = serialization.load_pem_private_key(raw, password=None)
    except (TypeError, ValueError) as exc:
        raise CanaryRunnerError(
            "canary signing key is not a valid unencrypted private key"
        ) from exc
    if not isinstance(signing_key, Ed25519PrivateKey):
        raise CanaryRunnerError("canary signing key must be Ed25519")
    return signing_key


def _read_public_key(path: Path) -> Ed25519PublicKey:
    path = _require_no_symlink_components(path, "canary public key")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise CanaryRunnerError(
                    "canary public key must be a regular non-symlink file"
                )
            if stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600, 0o644}:
                raise CanaryRunnerError(
                    "canary public key must have mode 0400, 0600, or 0644"
                )
            if metadata.st_uid != os.geteuid():
                raise CanaryRunnerError(
                    "canary public key must be owned by the current user"
                )
            if not 1 <= metadata.st_size <= MAX_SIGNING_KEY_BYTES:
                raise CanaryRunnerError("canary public key has an invalid bounded size")
            raw = os.read(descriptor, MAX_SIGNING_KEY_BYTES + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CanaryRunnerError(
                "canary public key must be a regular non-symlink file"
            ) from exc
        raise CanaryRunnerError("canary public key is unavailable") from exc
    if len(raw) > MAX_SIGNING_KEY_BYTES:
        raise CanaryRunnerError("canary public key exceeds its size limit")
    try:
        public_key = serialization.load_pem_public_key(raw)
    except (TypeError, ValueError) as exc:
        raise CanaryRunnerError("canary public key is not valid PEM") from exc
    if not isinstance(public_key, Ed25519PublicKey):
        raise CanaryRunnerError("canary public key must be Ed25519")
    return public_key


def verify_canary_receipt(
    receipt: CanaryReceipt,
    public_key: Ed25519PublicKey,
    *,
    checked_at: datetime | None = None,
    require_success: bool = False,
) -> CanaryReceipt:
    """Authenticate one content-addressed receipt against a pinned stack key."""

    now = (checked_at or _now()).astimezone(timezone.utc)
    if receipt.signer_id != _public_signer_id(public_key):
        raise CanaryRunnerError(
            "canary receipt signer conflicts with pinned public key"
        )
    signed_payload = receipt.model_dump(mode="json")
    attestation = signed_payload.pop("attestation")
    digest_payload = dict(signed_payload)
    receipt_id = digest_payload.pop("receipt_id")
    if receipt_id != _digest(digest_payload):
        raise CanaryRunnerError("canary receipt identity does not address its content")
    try:
        signature = base64.urlsafe_b64decode(attestation + "==")
        public_key.verify(signature, canonical_json_bytes(signed_payload))
    except (InvalidSignature, ValueError) as exc:
        raise CanaryRunnerError("canary receipt attestation did not verify") from exc
    if receipt.observed_at > now + MAX_CANARY_FUTURE_SKEW:
        raise CanaryRunnerError("canary receipt observation is in the future")
    if receipt.expires_at <= now:
        raise CanaryRunnerError("canary receipt is expired")
    if require_success and (
        not receipt.call_succeeded or not receipt.result_contract_matched
    ):
        raise CanaryRunnerError(
            "canary receipt does not prove a successful matching read"
        )
    return receipt


def _model_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value


def _bounded_digest(value: Any, *, limit: int, label: str) -> str:
    raw = canonical_json_bytes(value)
    if len(raw) > limit:
        raise CanaryRunnerError(f"{label} exceeds its bounded size limit")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_deployment_binding(
    path: Path,
    target: RuntimeTarget,
) -> CanaryDeploymentBinding:
    try:
        payload, _ = _load_deployment(path)
    except ObservationProducerError as exc:
        raise CanaryRunnerError(
            "canary deployment manifest failed content-address validation"
        ) from exc
    matches = [
        item
        for item in payload.get("services", [])
        if isinstance(item, dict) and item.get("service_id") == target.service_id
    ]
    if len(matches) != 1:
        raise CanaryRunnerError("canary deployment service is absent or ambiguous")
    service = matches[0]
    try:
        return CanaryDeploymentBinding.model_validate(
            {
                "manifest_id": payload.get("manifest_id"),
                "service_id": service.get("service_id"),
                "package_source_revision": service.get("package_source_revision"),
                "package_digest": service.get("package_digest"),
                "deployed_tree_digest": service.get("deployed_tree", {}).get(
                    "tree_digest"
                ),
                "deployed_at": payload.get("deployed_at"),
            }
        )
    except ValidationError as exc:
        raise CanaryRunnerError("canary deployment binding is incomplete") from exc


async def _wait_for_endpoint_listener(
    endpoint_ref: str,
    timeout_seconds: int,
) -> int:
    """Wait for one committed loopback listener within the canary budget.

    A systemd ``Type=simple`` process becomes active before Uvicorn has bound
    its socket.  Treating the first connection refusal as a failed canary
    therefore confuses process activation with endpoint readiness.  This
    bounded preflight retries only the TCP listener transition; MCP auth,
    protocol, inventory, tool, and result failures still fail immediately.

    The returned value is the remaining whole-second request budget.
    """

    parsed = urlsplit(endpoint_ref)
    host = parsed.hostname
    try:
        port = parsed.port
    except ValueError as exc:
        raise CanaryRunnerError("canary endpoint has an invalid port") from exc
    if parsed.scheme != "http" or host not in {"127.0.0.1", "::1", "localhost"}:
        raise CanaryRunnerError("canary endpoint must be loopback HTTP")
    if port is None:
        raise CanaryRunnerError("canary endpoint must name an explicit port")

    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CanaryRunnerError(
                "authenticated MCP canary endpoint did not become ready"
            )
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=min(1.0, remaining),
            )
            writer.close()
            await writer.wait_closed()
            return max(1, ceil(deadline - time.monotonic()))
        except (OSError, asyncio.TimeoutError):
            if writer is not None:
                writer.close()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CanaryRunnerError(
                    "authenticated MCP canary endpoint did not become ready"
                )
            await asyncio.sleep(min(0.2, remaining))


async def _collect_pages(
    method: Callable[..., Awaitable[Any]],
    attribute: str,
) -> list[Any]:
    rows: list[Any] = []
    cursor: str | None = None
    for _ in range(MAX_PAGES):
        response = await method(cursor=cursor) if cursor else await method()
        page = getattr(response, attribute, None)
        if not isinstance(page, list):
            raise CanaryRunnerError("MCP inventory response has an invalid shape")
        rows.extend(page)
        cursor = getattr(response, "nextCursor", None)
        if not cursor:
            return rows
    raise CanaryRunnerError("MCP inventory exceeded its pagination limit")


def _structured_result(result: Any) -> dict[str, Any] | None:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", None)
    if not isinstance(content, list) or len(content) != 1:
        return None
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


async def live_probe(
    target: RuntimeTarget,
    contract: RuntimeCanaryContract,
    credential: str,
    timeout_seconds: int,
) -> CanaryProbeResult:
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        raise CanaryRunnerError(
            "MCP canary runtime dependencies are unavailable"
        ) from exc

    started = time.monotonic()
    request_timeout_seconds = await _wait_for_endpoint_listener(
        target.endpoint_ref,
        timeout_seconds,
    )
    try:
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {credential}"},
            timeout=httpx.Timeout(float(request_timeout_seconds)),
        ) as http_client:
            async with streamable_http_client(
                target.endpoint_ref,
                http_client=http_client,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    capabilities = initialized.capabilities
                    tools = await _collect_pages(session.list_tools, "tools")
                    resources: list[Any] = []
                    resource_templates: list[Any] = []
                    prompts: list[Any] = []
                    if getattr(capabilities, "resources", None) is not None:
                        resources = await _collect_pages(
                            session.list_resources,
                            "resources",
                        )
                        resource_templates = await _collect_pages(
                            session.list_resource_templates,
                            "resourceTemplates",
                        )
                    if getattr(capabilities, "prompts", None) is not None:
                        prompts = await _collect_pages(
                            session.list_prompts,
                            "prompts",
                        )
                    inventory = {
                        "protocol_version": initialized.protocolVersion,
                        "tools": sorted(
                            (_model_json(item) for item in tools),
                            key=lambda item: str(item.get("name", "")),
                        ),
                        "resources": sorted(
                            (_model_json(item) for item in resources),
                            key=lambda item: str(item.get("uri", "")),
                        ),
                        "resource_templates": sorted(
                            (_model_json(item) for item in resource_templates),
                            key=lambda item: str(item.get("uriTemplate", "")),
                        ),
                        "prompts": sorted(
                            (_model_json(item) for item in prompts),
                            key=lambda item: str(item.get("name", "")),
                        ),
                    }
                    _reject_secret_material(inventory)
                    server_schema_digest = _bounded_digest(
                        inventory,
                        limit=MAX_SCHEMA_BYTES,
                        label="MCP server schema inventory",
                    )
                    selected = next(
                        (
                            item
                            for item in inventory["tools"]
                            if item.get("name") == contract.tool_name
                        ),
                        None,
                    )
                    if selected is None:
                        raise CanaryRunnerError(
                            "committed canary tool is absent from MCP inventory"
                        )
                    selected_tool_schema_digest = _bounded_digest(
                        selected,
                        limit=MAX_SCHEMA_BYTES,
                        label="selected MCP tool schema",
                    )
                    call_started = time.monotonic()
                    result = await session.call_tool(
                        contract.tool_name,
                        contract.arguments,
                        read_timeout_seconds=timedelta(seconds=request_timeout_seconds),
                    )
                    call_latency_ms = int((time.monotonic() - call_started) * 1000)
                    payload = _structured_result(result)
                    call_succeeded = (
                        not bool(getattr(result, "isError", False))
                        and payload is not None
                    )
                    reason_codes = (
                        ()
                        if call_succeeded
                        else ("mcp-canary-call-or-result-shape-failed",)
                    )
                    if payload is not None:
                        _reject_secret_material(payload)
                        _bounded_digest(
                            payload,
                            limit=MAX_RESULT_BYTES,
                            label="MCP canary result",
                        )
                    return CanaryProbeResult(
                        protocol_version=initialized.protocolVersion,
                        server_name=initialized.serverInfo.name,
                        server_version=initialized.serverInfo.version,
                        server_schema_digest=server_schema_digest,
                        selected_tool_schema_digest=selected_tool_schema_digest,
                        inventory_counts=CanaryInventoryCounts(
                            tools=len(tools),
                            resources=len(resources),
                            resource_templates=len(resource_templates),
                            prompts=len(prompts),
                        ),
                        call_succeeded=call_succeeded,
                        result=payload,
                        call_latency_ms=call_latency_ms,
                        total_latency_ms=int((time.monotonic() - started) * 1000),
                        reason_codes=reason_codes,
                    )
    except CanaryRunnerError:
        raise
    except Exception as exc:
        raise CanaryRunnerError("authenticated MCP canary transport failed") from exc


_MISSING = object()


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for raw_segment in pointer.split("/")[1:]:
        segment = raw_segment.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
            continue
        if isinstance(current, list):
            if not segment.isdecimal():
                return _MISSING
            index = int(segment)
            if index >= len(current):
                return _MISSING
            current = current[index]
            continue
        return _MISSING
    return current


def _nonempty(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, (str, bytes, list, tuple, dict, set)):
        return bool(value)
    return True


def _contains_subset(value: Any, subset: dict[str, Any]) -> bool:
    return isinstance(value, list) and any(
        isinstance(item, dict)
        and all(item.get(key, _MISSING) == expected for key, expected in subset.items())
        for item in value
    )


def validate_result_contract(
    result: dict[str, Any],
    contract: RuntimeCanaryContract,
) -> tuple[bool, tuple[str, ...], str | None]:
    reasons: list[str] = []
    schema_identity = _json_pointer(result, contract.schema_pointer)
    if schema_identity != contract.schema_value:
        reasons.append("canary-result-schema-mismatch")
    for pointer in contract.required_pointers:
        if not _nonempty(_json_pointer(result, pointer)):
            reasons.append("canary-required-result-evidence-missing")
            break
    for pointer, expected in contract.exact_values.items():
        if _json_pointer(result, pointer) != expected:
            reasons.append("canary-exact-result-evidence-mismatch")
            break
    for assertion in contract.array_contains:
        if not _contains_subset(
            _json_pointer(result, assertion.pointer),
            assertion.subset,
        ):
            reasons.append("canary-owner-result-evidence-missing")
            break
    return (
        not reasons,
        tuple(dict.fromkeys(reasons)),
        schema_identity if isinstance(schema_identity, str) else None,
    )


def _receipt_body(
    *,
    target: RuntimeTarget,
    contract: RuntimeCanaryContract,
    probe: CanaryProbeResult,
    observed_at: datetime,
    expires_at: datetime,
    deployment: CanaryDeploymentBinding,
    process_identity: str,
    process_unit_name: str,
) -> dict[str, Any]:
    contract_matched = False
    contract_reasons: tuple[str, ...] = ()
    schema_identity: str | None = None
    result_digest: str | None = None
    if probe.result is not None:
        contract_matched, contract_reasons, schema_identity = validate_result_contract(
            probe.result,
            contract,
        )
        result_digest = _bounded_digest(
            probe.result,
            limit=MAX_RESULT_BYTES,
            label="MCP canary result",
        )
    reasons = tuple(dict.fromkeys((*probe.reason_codes, *contract_reasons)))
    if not probe.call_succeeded and not reasons:
        reasons = ("mcp-canary-call-failed",)
    if probe.call_succeeded and not contract_matched and not reasons:
        reasons = ("mcp-canary-result-contract-mismatch",)
    return {
        "schema_version": "abyss_stack_mcp_canary_receipt_v3",
        "issuer": "abyss-stack",
        "consumer_id": "abyss-stack-mcp-canary",
        "organ_id": target.organ_id,
        "policy_family": target.policy_family,
        "service_id": target.service_id,
        "endpoint_ref": target.endpoint_ref,
        "deployment_manifest_id": deployment.manifest_id,
        "deployment_service_id": deployment.service_id,
        "deployment_source_revision": deployment.package_source_revision,
        "deployment_package_digest": deployment.package_digest,
        "deployment_tree_digest": deployment.deployed_tree_digest,
        "deployment_deployed_at": deployment.deployed_at.isoformat(),
        "process_unit_name": process_unit_name,
        "process_identity": process_identity,
        "canary_route": target.canary_route,
        "tool_name": contract.tool_name,
        "tool_arguments_digest": _digest(contract.arguments),
        "observed_at": observed_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "protocol_version": probe.protocol_version,
        "server_name": probe.server_name,
        "server_version": probe.server_version,
        "server_schema_digest": probe.server_schema_digest,
        "selected_tool_schema_digest": probe.selected_tool_schema_digest,
        "inventory_counts": probe.inventory_counts.model_dump(mode="json"),
        "call_succeeded": probe.call_succeeded,
        "result_contract_matched": probe.call_succeeded and contract_matched,
        "result_schema_identity": schema_identity,
        "result_digest": result_digest,
        "result_artifact_ref": (
            (f"results/{target.organ_id}/{result_digest.removeprefix('sha256:')}.json")
            if probe.call_succeeded and result_digest is not None
            else None
        ),
        "call_latency_ms": probe.call_latency_ms,
        "total_latency_ms": probe.total_latency_ms,
        "reason_codes": list(reasons),
        "contains_secrets": False,
        "content_trust": "untrusted_data",
        "instruction_authority": "none",
        "claim_limit": (
            "This stack-issued receipt proves one authenticated loopback MCP "
            "schema observation, bounded read canary, and exact named-systemd "
            "process identity unchanged across the probe only. It does not prove "
            "owner grounding, owner freshness, owner acceptance, central proof, "
            "admission, or rollback."
        ),
    }


def build_result_artifact(
    *,
    receipt: CanaryReceipt,
    owner_payload: dict[str, Any],
    signing_key: Ed25519PrivateKey,
) -> CanaryResultArtifact:
    _reject_secret_material(owner_payload)
    if receipt.signer_id != _signer_id(signing_key):
        raise CanaryRunnerError(
            "canary result artifact signer does not match its receipt"
        )
    result_digest = _bounded_digest(
        owner_payload,
        limit=MAX_RESULT_BYTES,
        label="MCP canary result",
    )
    if (
        not receipt.call_succeeded
        or receipt.result_digest != result_digest
        or receipt.result_schema_identity is None
        or receipt.result_artifact_ref is None
    ):
        raise CanaryRunnerError(
            "canary result artifact does not bind a successful receipt"
        )
    body = {
        "schema_version": "abyss_stack_mcp_canary_result_artifact_v2",
        "issuer": "abyss-stack",
        "organ_id": receipt.organ_id,
        "policy_family": receipt.policy_family,
        "service_id": receipt.service_id,
        "canary_route": receipt.canary_route,
        "tool_name": receipt.tool_name,
        "tool_arguments_digest": receipt.tool_arguments_digest,
        "observed_at": receipt.observed_at,
        "result_schema_identity": receipt.result_schema_identity,
        "result_digest": result_digest,
        "owner_payload": owner_payload,
        "contains_secrets": False,
        "content_trust": "untrusted_data",
        "instruction_authority": "none",
        "claim_limit": (
            "This private artifact preserves one bounded MCP canary result for "
            "independent owner review. Stack capture and content addressing do "
            "not prove owner grounding, freshness, acceptance, central proof, "
            "admission, or rollback."
        ),
    }
    try:
        normalized = CanaryResultArtifact.model_validate(
            {
                "artifact_id": "sha256:" + ("0" * 64),
                "signer_id": _signer_id(signing_key),
                "attestation_algorithm": "ed25519",
                "attestation": "A" * 86,
                **body,
            }
        )
        normalized_body = normalized.model_dump(mode="json")
        normalized_body.pop("artifact_id")
        normalized_body.pop("attestation")
        artifact_id = _digest(normalized_body)
        signed_payload = {
            "artifact_id": artifact_id,
            **normalized_body,
        }
        artifact = CanaryResultArtifact.model_validate(
            {
                **signed_payload,
                **_signed_fields(signed_payload, signing_key),
            }
        )
    except ValidationError as exc:
        raise CanaryRunnerError(
            "produced canary result artifact failed contract validation"
        ) from exc
    _reject_secret_material(artifact.model_dump(mode="json"))
    return artifact


def build_receipt(
    *,
    target: RuntimeTarget,
    contract: RuntimeCanaryContract,
    probe: CanaryProbeResult,
    observed_at: datetime,
    ttl_seconds: int,
    signing_key: Ed25519PrivateKey,
    deployment: CanaryDeploymentBinding,
    process_identity: str,
    process_unit_name: str | None = None,
) -> CanaryReceipt:
    if not 30 <= ttl_seconds <= 3600:
        raise CanaryRunnerError("canary receipt TTL must be 30..3600 seconds")
    observed_at = observed_at.astimezone(timezone.utc)
    if observed_at < deployment.deployed_at:
        raise CanaryRunnerError("canary receipt must follow its exact deployment")
    expires_at = observed_at + timedelta(seconds=ttl_seconds)
    body = _receipt_body(
        target=target,
        contract=contract,
        probe=probe,
        observed_at=observed_at,
        expires_at=expires_at,
        deployment=deployment,
        process_identity=process_identity,
        process_unit_name=process_unit_name or target.unit_name,
    )
    try:
        normalized = CanaryReceipt.model_validate(
            {
                "receipt_id": "sha256:" + ("0" * 64),
                "signer_id": _signer_id(signing_key),
                "attestation_algorithm": "ed25519",
                "attestation": "A" * 86,
                **body,
            }
        )
        normalized_body = normalized.model_dump(mode="json")
        normalized_body.pop("receipt_id")
        normalized_body.pop("attestation")
        receipt_id = _digest(normalized_body)
        signed_payload = {
            "receipt_id": receipt_id,
            **normalized_body,
        }
        receipt = CanaryReceipt.model_validate(
            {
                **signed_payload,
                **_signed_fields(signed_payload, signing_key),
            }
        )
    except ValidationError as exc:
        raise CanaryRunnerError(
            "produced canary receipt failed contract validation"
        ) from exc
    _reject_secret_material(receipt.model_dump(mode="json"))
    return receipt


def build_overlay(
    receipt: CanaryReceipt,
    *,
    receipt_ref: str,
) -> RuntimeEvidenceOverlay:
    evidence_ref = EvidenceRef(
        owner="abyss-stack",
        evidence_ref=receipt_ref,
        revision=receipt.receipt_id,
        observed_at=receipt.observed_at,
        expires_at=receipt.expires_at,
    )
    endpoint_link = LinkEvidence(
        state="exact",
        observed_at=receipt.observed_at,
        expires_at=receipt.expires_at,
        evidence_refs=(evidence_ref,),
    )
    canary_link = LinkEvidence(
        state="blocked",
        observed_at=receipt.observed_at,
        expires_at=receipt.expires_at,
        evidence_refs=(evidence_ref,),
        reason_codes=(
            ("owner-grounding-review-required",)
            if receipt.result_contract_matched
            else receipt.reason_codes
        ),
    )
    return RuntimeEvidenceOverlay(
        generated_at=receipt.observed_at,
        expires_at=receipt.expires_at,
        subjects=(
            RuntimeEvidenceOverlaySubject(
                organ_id=receipt.organ_id,
                endpoint=EndpointObservation(
                    transport="streamable-http",
                    endpoint_ref=receipt.endpoint_ref,
                    protocol_versions=(receipt.protocol_version,),
                    ready=True,
                    server_schema_digest=receipt.server_schema_digest,
                    evidence=endpoint_link,
                ),
                canary=CanaryObservation(
                    succeeded=False,
                    result_grounded=False,
                    canary_route=receipt.canary_route,
                    canary_ref=None,
                    evidence=canary_link,
                ),
            ),
        ),
    )


async def run_canary(
    *,
    organ_id: str,
    targets_path: Path = DEFAULT_TARGETS_PATH,
    secret_dir: Path = DEFAULT_SECRET_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    deployment_manifest_path: Path = DEFAULT_DEPLOYMENT_MANIFEST,
    ttl_seconds: int = 600,
    timeout_seconds: int = 30,
    purpose: CanaryPurpose = "current",
    process_unit: CanaryProcessUnit = "production",
    clock: Callable[[], datetime] = _now,
    probe_runner: ProbeRunner = live_probe,
    process_identity_reader: ProcessIdentityReader = _live_process_identity,
) -> tuple[CanaryReceipt, Path, Path, Path | None]:
    if not 1 <= timeout_seconds <= 300:
        raise CanaryRunnerError("canary timeout must be 1..300 seconds")
    catalog, _ = _load_targets(targets_path)
    target = next(
        (item for item in catalog.targets if item.organ_id == organ_id),
        None,
    )
    if target is None:
        raise CanaryRunnerError("requested canary organ is absent from target catalog")
    if target.canary_contract is None:
        raise CanaryRunnerError(
            "requested organ has no reviewed runtime canary contract"
        )
    if purpose == "last-known-good":
        target = target.model_copy(
            update={"canary_route": target.canary_route + "/last-known-good"}
        )
    observed_target = target
    if process_unit == "bootstrap":
        observed_target = target.model_copy(
            update={"unit_name": _bootstrap_unit_name(target.unit_name)}
        )
    credential_path = (
        _require_no_symlink_components(secret_dir, "canary secret root")
        / f"{target.service_id}-read-bearer-token"
    )
    credential = _read_credential(credential_path)
    signing_key = _read_signing_key(secret_dir / CANARY_SIGNING_KEY_NAME)
    deployment = _read_deployment_binding(deployment_manifest_path, target)
    process_before = process_identity_reader(
        observed_target,
        deployment.package_source_revision,
        clock().astimezone(timezone.utc),
    )
    probe = await probe_runner(
        target,
        target.canary_contract,
        credential,
        timeout_seconds,
    )
    observed_at = clock().astimezone(timezone.utc)
    process_after = process_identity_reader(
        observed_target,
        deployment.package_source_revision,
        observed_at,
    )
    if process_before != process_after:
        raise CanaryRunnerError("canary target process changed during the probe")
    receipt = build_receipt(
        target=target,
        contract=target.canary_contract,
        probe=probe,
        observed_at=observed_at,
        ttl_seconds=ttl_seconds,
        signing_key=signing_key,
        deployment=deployment,
        process_identity=process_after,
        process_unit_name=observed_target.unit_name,
    )
    root = _ensure_private_directory(output_root)
    result_path: Path | None = None
    if receipt.call_succeeded:
        if probe.result is None or receipt.result_artifact_ref is None:
            raise CanaryRunnerError("successful canary result artifact is unavailable")
        result_artifact = build_result_artifact(
            receipt=receipt,
            owner_payload=probe.result,
            signing_key=signing_key,
        )
        result_path = root / receipt.result_artifact_ref
        _write_private_json(
            result_path,
            result_artifact.model_dump(mode="json"),
        )
    record_path = (
        root
        / "records"
        / target.organ_id
        / f"{receipt.receipt_id.removeprefix('sha256:')}.json"
    )
    receipt_payload = receipt.model_dump(mode="json")
    _write_private_json(record_path, receipt_payload)
    _write_private_json(
        root / "latest" / f"{target.organ_id}.read.json",
        receipt_payload,
    )
    overlay = build_overlay(receipt, receipt_ref=record_path.as_posix())
    overlay_path = root / "overlays" / f"{target.organ_id}.read.json"
    _write_private_json(
        overlay_path,
        overlay.model_dump(mode="json"),
    )
    return receipt, record_path, overlay_path, result_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organ", required=True)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument("--secret-dir", type=Path, default=DEFAULT_SECRET_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--deployment-manifest",
        type=Path,
        default=DEFAULT_DEPLOYMENT_MANIFEST,
    )
    parser.add_argument("--ttl-seconds", type=int, default=600)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument(
        "--purpose",
        choices=("current", "last-known-good"),
        default="current",
    )
    parser.add_argument(
        "--process-unit",
        choices=("production", "bootstrap"),
        default="production",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        receipt, record_path, overlay_path, result_path = asyncio.run(
            run_canary(
                organ_id=args.organ,
                targets_path=args.targets,
                secret_dir=args.secret_dir,
                output_root=args.output_root,
                deployment_manifest_path=args.deployment_manifest,
                ttl_seconds=args.ttl_seconds,
                timeout_seconds=args.timeout_seconds,
                purpose=args.purpose,
                process_unit=args.process_unit,
            )
        )
    except CanaryRunnerError as exc:
        print(f"abyss-stack MCP canary: {exc}", file=os.sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema_version": receipt.schema_version,
                "receipt_id": receipt.receipt_id,
                "organ_id": receipt.organ_id,
                "call_succeeded": receipt.call_succeeded,
                "result_contract_matched": receipt.result_contract_matched,
                "server_schema_digest": receipt.server_schema_digest,
                "record_path": record_path.as_posix(),
                "overlay_path": overlay_path.as_posix(),
                "result_artifact_path": (
                    result_path.as_posix() if result_path is not None else None
                ),
                "claim_limit": receipt.claim_limit,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if receipt.call_succeeded and receipt.result_contract_matched else 2


if __name__ == "__main__":
    raise SystemExit(main())
