"""MCP transport surface for separate abyss-stack read and candidate planes."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from ._http_auth import http_auth_config, transport_settings
from ._modern_runtime import run_server
from ._runtime_config import SERVICE_CONFIG
from .audit import (
    DEFAULT_MAX_BYTES,
    PolicyAuditError,
    PolicyAuditJournal,
)
from .core import ObservationStore, StackMCPApplication
from .orchestration import CrossOrganRunStore
from .policy import PolicyIdentity, StackPolicySeam, ToolPolicy


LOGGER = logging.getLogger(__name__)
AUTH_MANIFEST_CREDENTIAL = SERVICE_CONFIG.auth_manifest_credential
AUTH_MANIFEST_SCHEMA = SERVICE_CONFIG.auth_manifest_schema
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
PolicyMode = Literal["read", "candidate"]
CredentialContour = Literal["read", "candidate", "internal_effect"]
CatalogLimit = Annotated[int, Field(ge=1, le=64)]
CatalogBudget = Annotated[int, Field(ge=512, le=131_072)]


def configured_policy_family() -> PolicyMode:
    value = os.environ.get("ABYSS_STACK_MCP_POLICY_FAMILY", "read").strip()
    if value not in {"read", "candidate"}:
        raise SystemExit("ABYSS_STACK_MCP_POLICY_FAMILY must be read or candidate")
    return value  # type: ignore[return-value]


def _contour(policy_family: CredentialContour) -> Any:
    return SERVICE_CONFIG.contour(policy_family)


def _credential_text(credential_name: str, label: str) -> str:
    credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
    if not credential_dir:
        raise SystemExit(f"managed startup requires {label}")
    credential_path = Path(credential_dir) / credential_name
    if credential_path.is_symlink() or not credential_path.is_file():
        raise SystemExit(f"managed startup requires a regular {label}")
    try:
        return credential_path.read_text(encoding="utf-8").removesuffix("\n")
    except (OSError, UnicodeError) as exc:
        raise SystemExit(f"managed startup cannot read {label}") from exc


def _require_managed_credential_separation(
    policy_family: CredentialContour,
) -> None:
    required = os.environ.get(
        "ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST",
        "",
    ).strip()
    if not required:
        return
    if required != "1":
        raise SystemExit(
            "ABYSS_STACK_MCP_REQUIRE_AUTH_MANIFEST must be 1 when configured"
        )
    credential_name = _contour(policy_family).auth.credential_name
    token = _credential_text(
        credential_name,
        f"{policy_family} bearer credential",
    )
    manifest_text = _credential_text(
        AUTH_MANIFEST_CREDENTIAL,
        "credential separation manifest",
    )
    try:
        manifest = json.loads(manifest_text)
    except (json.JSONDecodeError, TypeError):
        raise SystemExit("managed credential separation manifest is invalid") from None
    expected_keys = {
        "schema_version",
        "read_sha256",
        "candidate_sha256",
        "internal_effect_sha256",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != expected_keys
        or manifest.get("schema_version") != AUTH_MANIFEST_SCHEMA
        or any(
            not isinstance(manifest.get(key), str)
            or _SHA256_PATTERN.fullmatch(manifest[key]) is None
            for key in (
                "read_sha256",
                "candidate_sha256",
                "internal_effect_sha256",
            )
        )
    ):
        raise SystemExit("managed credential separation manifest is invalid")
    read_digest = manifest["read_sha256"]
    candidate_digest = manifest["candidate_sha256"]
    internal_effect_digest = manifest["internal_effect_sha256"]
    if len({read_digest, candidate_digest, internal_effect_digest}) != 3:
        raise SystemExit(
            "managed read, candidate, and internal-effect bearer credentials "
            "must be distinct"
        )
    observed_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(
        observed_digest,
        manifest[f"{policy_family}_sha256"],
    ):
        raise SystemExit(
            f"managed {policy_family} bearer does not match "
            "the credential separation manifest"
        )


def _auth_config(policy_family: CredentialContour) -> Any:
    contour = _contour(policy_family)
    _require_managed_credential_separation(policy_family)
    return http_auth_config(contour.port, **contour.auth.as_kwargs())


def _policy_identity(policy_family: CredentialContour) -> PolicyIdentity:
    contour = _contour(policy_family)
    expected_scope = contour.auth.auth_scope
    settings = transport_settings(contour.port)
    if settings.transport == "stdio":
        return PolicyIdentity(
            identity_id="local-os-stdio",
            auth_mode="os_process",
            scope=expected_scope,
        )
    from mcp.server.auth.middleware.auth_context import (  # type: ignore[import-not-found]
        get_access_token,
    )

    token = get_access_token()
    expected_client = contour.auth.client_id
    assert settings.host is not None and settings.port is not None
    rendered_host = (
        f"[{settings.host}]" if ":" in settings.host else settings.host
    )
    expected_authority = f"http://{rendered_host}:{settings.port}"
    if (
        token is None
        or token.client_id != expected_client
        or expected_scope not in token.scopes
        or token.resource != f"{expected_authority}{settings.streamable_http_path}"
        or token.subject != "local-operator"
        or not isinstance(token.claims, dict)
        or token.claims.get("iss") != f"{expected_authority}/"
    ):
        return PolicyIdentity(
            identity_id="unverified-http-caller",
            auth_mode="bearer",
            scope="invalid",
        )
    return PolicyIdentity(
        identity_id=token.client_id,
        auth_mode="bearer",
        scope=expected_scope,
    )


def _configured_audit_journal(
    policy_family: PolicyMode,
) -> PolicyAuditJournal | None:
    required = os.environ.get(
        "ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL",
        "",
    ).strip()
    if required not in {"", "1"}:
        raise SystemExit(
            "ABYSS_STACK_MCP_REQUIRE_AUDIT_JOURNAL must be 1 when configured"
        )
    path = os.environ.get(
        "ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH",
        "",
    ).strip()
    max_bytes_text = os.environ.get(
        "ABYSS_STACK_MCP_AUDIT_MAX_BYTES",
        "",
    ).strip()
    if not path:
        if required:
            raise SystemExit(
                "managed startup requires ABYSS_STACK_MCP_AUDIT_JOURNAL_PATH"
            )
        if max_bytes_text:
            raise SystemExit(
                "ABYSS_STACK_MCP_AUDIT_MAX_BYTES requires an audit journal path"
            )
        return None
    max_bytes = DEFAULT_MAX_BYTES
    if max_bytes_text:
        if not max_bytes_text.isascii() or not max_bytes_text.isdecimal():
            raise SystemExit(
                "ABYSS_STACK_MCP_AUDIT_MAX_BYTES must be a decimal integer"
            )
        max_bytes = int(max_bytes_text)
    try:
        return PolicyAuditJournal(
            path,
            owner="abyss-stack",
            policy_family=policy_family,
            max_bytes=max_bytes,
        )
    except PolicyAuditError as exc:
        raise SystemExit(f"policy audit startup failed: {exc}") from None


def _build_policy_seam(policy_family: PolicyMode) -> StackPolicySeam:
    scope = _contour(policy_family).auth.auth_scope
    if policy_family == "read":
        tools = (
            ToolPolicy(
                tool_id="stack_runtime_catalog",
                effect_class="observe",
                max_input_bytes=16_384,
                max_output_bytes=262_144,
                timeout_seconds=3.0,
                filesystem_access="configured_observation_read",
                network_access="none",
                source_to_sink="runtime_observation_to_typed_result",
            ),
            ToolPolicy(
                tool_id="stack_runtime_inspect",
                effect_class="observe",
                max_input_bytes=16_384,
                max_output_bytes=2_200_000,
                timeout_seconds=5.0,
                filesystem_access="configured_observation_read",
                network_access="none",
                source_to_sink="runtime_observation_to_typed_result",
            ),
            ToolPolicy(
                tool_id="stack_orchestration_inspect",
                effect_class="observe",
                max_input_bytes=4096,
                max_output_bytes=262_144,
                timeout_seconds=3.0,
                filesystem_access=(
                    "configured_observation_and_orchestration_record_read"
                ),
                network_access="none",
                source_to_sink=(
                    "sdk_validated_runtime_record_to_bounded_inspection"
                ),
            ),
        )
        max_in_flight = 8
        rate_limit = 120
    else:
        tools = (
            ToolPolicy(
                tool_id="stack_prepare_runtime_plan",
                effect_class="prepare_candidate",
                max_input_bytes=16_384,
                max_output_bytes=262_144,
                timeout_seconds=5.0,
                filesystem_access="configured_observation_read",
                network_access="none",
                source_to_sink=(
                    "runtime_observation_to_nonexecuting_candidate"
                ),
            ),
        )
        max_in_flight = 2
        rate_limit = 30
    return StackPolicySeam(
        owner="abyss-stack",
        policy_family=policy_family,
        expected_scope=scope,
        tools=tools,
        max_in_flight=max_in_flight,
        rate_limit=rate_limit,
        rate_window_seconds=60.0,
        audit_journal=_configured_audit_journal(policy_family),
    )


def _run_server(server: Any, policy_family: PolicyMode) -> None:
    run_server(server, _auth_config(policy_family))


def build_server(
    observation_path: str | Path | None = None,
    *,
    policy_family: PolicyMode | None = None,
    orchestration_root: str | Path | None = None,
) -> Any:
    try:
        from ._modern_runtime import ModernMCPServer  # type: ignore[import-not-found]
        from mcp.types import ToolAnnotations  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'mcp'. Install with: python -m pip install -e ."
        ) from exc

    mode = policy_family or configured_policy_family()
    auth_config = _auth_config(mode)
    application = StackMCPApplication(
        ObservationStore(observation_path),
        policy_family=mode,
        orchestration_store=CrossOrganRunStore(orchestration_root),
    )
    extensions: list[Any] = []
    if mode == "read":
        from .tasks_extension import (
            StackReadTasksExtension,
            task_root_from_environment,
            tasks_enabled_from_environment,
        )

        if tasks_enabled_from_environment():
            extensions.append(
                StackReadTasksExtension(application, task_root_from_environment())
            )
    policy = _build_policy_seam(mode)
    read_annotations = ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    candidate_annotations = ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
    mcp = ModernMCPServer(
        SERVICE_CONFIG.server_name(mode),
        version=SERVICE_CONFIG.package_version,
        instructions=(
            "Inspect stack-owned source/package/deploy/process/endpoint/consumer "
            "evidence or prepare non-executing bounded runtime plans. This server "
            "does not proxy owner tools and never executes a plan."
        ),
        extensions=extensions,
        **auth_config.server_kwargs,
    )

    if mode == "read":

        @mcp.tool(annotations=read_annotations, structured_output=True)
        async def stack_runtime_catalog(
            organ_id: str | None = None,
            policy_family: Literal["read"] | None = None,
            max_results: CatalogLimit = 32,
            byte_budget: CatalogBudget = 32_768,
        ) -> dict[str, Any]:
            """List compact runtime subjects without loading detailed schemas."""
            arguments = {
                "organ_id": organ_id,
                "policy_family": policy_family,
                "max_results": max_results,
                "byte_budget": byte_budget,
            }
            return await policy.invoke(
                request_id=uuid.uuid4().hex,
                identity=_policy_identity(mode),
                tool_id="stack_runtime_catalog",
                arguments=arguments,
                dispatch=lambda: application.catalog(**arguments),
            )

        @mcp.tool(annotations=read_annotations, structured_output=True)
        async def stack_runtime_inspect(
            organ_id: str,
            policy_family: Literal["read"] = "read",
            view: Literal[
                "identity",
                "parity",
                "process",
                "endpoint",
                "registry",
                "consumer",
                "schema",
                "freshness",
                "proof",
                "acceptance",
                "canary",
                "rollback",
                "drift",
                "full",
            ] = "identity",
        ) -> dict[str, Any]:
            """Inspect one exact runtime subject and one bounded evidence view."""
            arguments = {
                "organ_id": organ_id,
                "policy_family": policy_family,
                "view": view,
            }
            return await policy.invoke(
                request_id=uuid.uuid4().hex,
                identity=_policy_identity(mode),
                tool_id="stack_runtime_inspect",
                arguments=arguments,
                dispatch=lambda: application.inspect(
                    organ_id,
                    policy_family,
                    view=view,
                ),
            )

        @mcp.tool(annotations=read_annotations, structured_output=True)
        async def stack_orchestration_inspect(
            run_id: str | None = None,
        ) -> dict[str, Any]:
            """Inspect one host-persisted SDK orchestration snapshot."""
            arguments = {"run_id": run_id}
            return await policy.invoke(
                request_id=uuid.uuid4().hex,
                identity=_policy_identity(mode),
                tool_id="stack_orchestration_inspect",
                arguments=arguments,
                dispatch=lambda: application.inspect_orchestration(run_id),
            )
    else:

        @mcp.tool(annotations=candidate_annotations, structured_output=True)
        async def stack_prepare_runtime_plan(
            organ_id: str,
            target_policy_family: Literal[
                "read", "candidate", "internal_effect", "external_effect"
            ],
            plan_kind: Literal["sync", "deploy", "activate", "restart", "rollback"],
            expected_observation_digest: str,
        ) -> dict[str, Any]:
            """Prepare a content-addressed candidate; never execute runtime effects."""
            arguments = {
                "organ_id": organ_id,
                "target_policy_family": target_policy_family,
                "plan_kind": plan_kind,
                "expected_observation_digest": expected_observation_digest,
            }
            return await policy.invoke(
                request_id=uuid.uuid4().hex,
                identity=_policy_identity(mode),
                tool_id="stack_prepare_runtime_plan",
                arguments=arguments,
                dispatch=lambda: application.prepare_plan(
                    organ_id,
                    target_policy_family,
                    plan_kind,
                    expected_observation_digest=expected_observation_digest,
                ),
            )

    LOGGER.info("abyss-stack MCP %s plane ready", mode)
    return mcp


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mode = configured_policy_family()
    _run_server(build_server(policy_family=mode), mode)


if __name__ == "__main__":
    main()
