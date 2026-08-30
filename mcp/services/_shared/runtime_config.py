"""Load and validate the declarative MCP runtime configuration.

The JSON file is the source of operational identity: SDK major line, wire
revision, transport environment, contours, ports, and authentication names.
Standalone packages receive a generated, package-local projection so an
installed wheel never imports a monorepo path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SHARED_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = SHARED_ROOT / "runtime-config.v1.json"
SCHEMA_PATH = SHARED_ROOT / "runtime-config.schema.json"
SCHEMA_VERSION = "abyss_mcp_runtime_config_v1"
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_CREDENTIAL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_SCOPE = re.compile(r"[A-Za-z0-9:._/-]{1,128}")
_CODEX_FEATURE = re.compile(r"mcp_[0-9]{4}_[0-9]{2}_[0-9]{2}")
_UNIT_NAME = re.compile(r"[A-Za-z0-9_.@%-]+\.service")
_UNIT_TEMPLATE = re.compile(r"[A-Za-z0-9_.@%{}-]+\.service")
_VERSION = re.compile(r"2\.[0-9]+\.[0-9]+(?:[+-][0-9A-Za-z.-]+)?")


@dataclass(frozen=True)
class TransportConfig:
    transport_env_var: str
    host_env_var: str
    port_env_var: str
    default_transport: str
    default_host: str
    loopback_hosts: tuple[str, ...]
    port_min: int
    port_max: int
    protocol_version: str
    legacy_protocol_version: str
    modern_only_rejection_code: int
    streamable_http_transport: str
    streamable_http_path: str
    modern_only: bool
    sdk_distribution: str
    sdk_major: int
    sdk_requirement: str
    sdk_companion_distribution: str
    tested_sdk_lock: str
    sdk_source_revision: str


@dataclass(frozen=True)
class PathConfig:
    workspace_env_var: str
    stack_root_env_var: str
    stack_source_env_var: str
    tos_root_env_var: str
    tos_root_fallback_env_var: str
    connector_repo_bindings: Mapping[str, Mapping[str, str]]
    connector_relative_template: str
    tos_relative_to_workspace: str
    stack_runtime_relative_to_workspace: str
    stack_source_relative_to_workspace: str
    stack_logs_relative_to_runtime: str
    stack_secrets_relative_to_runtime: str
    stack_services_relative_to_runtime: str
    stack_configs_relative_to_runtime: str
    stack_deployment_manifest_relative_to_runtime: str
    stack_observation_relative_to_runtime: str
    stack_overlay_relative_to_runtime: str
    stack_registry_relative_to_workspace: str
    stack_codex_executable_relative_to_workspace_template: str
    stack_orchestration_relative_to_runtime: str
    stack_canaries_relative_to_runtime: str
    stack_effects_relative_to_runtime: str
    abyss_machine_policy_env_var: str
    abyss_machine_state_env_var: str
    abyss_machine_policy_fallback_env_var: str
    abyss_machine_state_fallback_env_var: str


@dataclass(frozen=True)
class RuntimeLimits:
    status_timeout_seconds: float
    search_timeout_seconds: float
    goal_lifecycle_timeout_seconds: float
    evidence_packet_timeout_seconds: float
    usage_neighborhood_timeout_seconds: float
    route_rollup_query_timeout_seconds: float
    direct_event_rollup_query_timeout_seconds: float
    protocol_probe_server_start_timeout_seconds: float
    protocol_probe_request_timeout_seconds: float
    protocol_probe_stdio_call_timeout_seconds: float
    protocol_probe_stdio_timeout_seconds: float
    protocol_probe_connect_timeout_seconds: float
    protocol_probe_process_shutdown_timeout_seconds: float
    protocol_probe_process_kill_timeout_seconds: float


@dataclass(frozen=True)
class AuthConfig:
    token_env_var: str
    credential_name: str
    auth_scope: str
    client_id: str

    def as_kwargs(self) -> dict[str, str]:
        return {
            "token_env_var": self.token_env_var,
            "credential_name": self.credential_name,
            "auth_scope": self.auth_scope,
            "client_id": self.client_id,
        }


@dataclass(frozen=True)
class ContourConfig:
    contour_id: str
    port: int
    auth: AuthConfig


@dataclass(frozen=True)
class ServiceConfig:
    service_id: str
    organ_id: str
    registry_organ_id: str
    runtime_executable_mode: str
    package_name: str
    package_version: str
    module: str
    server_name_template: str
    read_unit_template: str
    read_unit_instance: str
    contours: Mapping[str, ContourConfig]
    auth_manifest_credential: str | None = None
    auth_manifest_schema: str | None = None

    def contour(self, contour_id: str) -> ContourConfig:
        try:
            return self.contours[contour_id]
        except KeyError as exc:
            raise ValueError(
                f"{self.service_id} has no MCP contour {contour_id!r}; "
                f"expected one of {sorted(self.contours)}"
            ) from exc

    def server_name(self, contour_id: str = "read", profile: str | None = None) -> str:
        self.contour(contour_id)
        values = {
            "contour": contour_id.replace("_", "-"),
            "profile": profile or "complete",
        }
        try:
            return self.server_name_template.format(**values)
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"invalid server name template for {self.service_id}: "
                f"{self.server_name_template!r}"
            ) from exc

    def read_unit_name(self, organ_id: str) -> str:
        try:
            rendered = self.read_unit_template.format(
                organ=organ_id,
                instance=self.read_unit_instance,
                service_id=self.service_id,
                contour="read",
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"invalid read unit template for {self.service_id}: "
                f"{self.read_unit_template!r}"
            ) from exc
        if _UNIT_NAME.fullmatch(rendered) is None:
            raise ValueError(
                f"read unit template rendered an invalid unit for {self.service_id}: "
                f"{rendered!r}"
            )
        return rendered


@dataclass(frozen=True)
class RuntimeCatalog:
    schema_version: str
    transport: TransportConfig
    paths: PathConfig
    limits: RuntimeLimits
    services: Mapping[str, ServiceConfig]
    reserved_ports: Mapping[int, str]

    def service(self, service_id: str) -> ServiceConfig:
        try:
            return self.services[service_id]
        except KeyError as exc:
            raise ValueError(f"unknown MCP service {service_id!r}") from exc


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _require_relative_template(value: Any, label: str) -> str:
    text = _require_string(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be a relative path template")
    return text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read MCP runtime config: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"MCP runtime config must be an object: {path}")
    return payload


def _validate_raw(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("MCP runtime config schema version drifted")
    mcp = payload.get("mcp")
    if not isinstance(mcp, dict):
        raise ValueError("MCP runtime config lacks mcp object")
    sdk = mcp.get("sdk")
    protocol = mcp.get("protocol")
    transport = mcp.get("transport")
    if not isinstance(sdk, dict) or sdk.get("distribution") != "mcp":
        raise ValueError("MCP runtime config has invalid SDK distribution")
    if sdk.get("major") != 2 or sdk.get("requirement") != "mcp>=2,<3":
        raise ValueError("MCP runtime config must admit only SDK major 2")
    companion_distribution = _require_string(
        sdk.get("companion_distribution"), "mcp.sdk.companion_distribution"
    )
    if companion_distribution == sdk["distribution"]:
        raise ValueError("MCP SDK companion distribution must be distinct")
    tested_lock = _require_string(sdk.get("tested_lock"), "mcp.sdk.tested_lock")
    if _VERSION.fullmatch(tested_lock) is None:
        raise ValueError("MCP tested lock must be an exact semantic SDK 2 version")
    source_revision = _require_string(
        sdk.get("source_revision"), "mcp.sdk.source_revision"
    )
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise ValueError("MCP SDK source revision must be a 40-character hex commit")
    if (
        not isinstance(protocol, dict)
        or not _require_string(protocol.get("version"), "mcp.protocol.version")
        or not _require_string(
            protocol.get("legacy_version"), "mcp.protocol.legacy_version"
        )
        or not isinstance(protocol.get("modern_only_rejection_code"), int)
        or isinstance(protocol.get("modern_only_rejection_code"), bool)
        or not -32099 <= protocol["modern_only_rejection_code"] <= -32000
        or protocol.get("streamable_http_path") != "/mcp"
        or protocol.get("modern_only") is not True
    ):
        raise ValueError("MCP runtime config has invalid modern protocol policy")
    if not isinstance(transport, dict):
        raise ValueError("MCP runtime config lacks transport object")
    if transport.get("streamable_http_transport") != "streamable-http":
        raise ValueError("MCP streamable HTTP transport identity drifted")
    for key in ("transport_env_var", "host_env_var", "port_env_var"):
        value = _require_string(transport.get(key), f"mcp.transport.{key}")
        if _ENV_NAME.fullmatch(value) is None:
            raise ValueError(f"invalid MCP transport environment name: {value}")
    if transport.get("default_transport") != "stdio":
        raise ValueError("MCP transport must default to stdio")
    loopback_hosts = transport.get("loopback_hosts")
    if (
        not isinstance(loopback_hosts, list)
        or not loopback_hosts
        or any(not isinstance(item, str) or not item for item in loopback_hosts)
        or len(set(loopback_hosts)) != len(loopback_hosts)
    ):
        raise ValueError("MCP loopback host policy is invalid")
    if transport.get("default_host") not in loopback_hosts:
        raise ValueError("MCP default host must be loopback")
    if transport.get("port_min") != 1 or transport.get("port_max") != 65535:
        raise ValueError("MCP port bounds drifted")

    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("MCP runtime config lacks paths object")
    for key in (
        "workspace_env_var",
        "stack_root_env_var",
        "stack_source_env_var",
        "tos_root_env_var",
        "tos_root_fallback_env_var",
        "abyss_machine_policy_env_var",
        "abyss_machine_state_env_var",
        "abyss_machine_policy_fallback_env_var",
        "abyss_machine_state_fallback_env_var",
    ):
        value = _require_string(paths.get(key), f"paths.{key}")
        if _ENV_NAME.fullmatch(value) is None:
            raise ValueError(f"invalid path environment name: {value}")
    connector_bindings = paths.get("connector_repo_bindings")
    if not isinstance(connector_bindings, dict) or not connector_bindings:
        raise ValueError("paths.connector_repo_bindings must be a non-empty object")
    for binding_service_id, binding in connector_bindings.items():
        if not isinstance(binding_service_id, str) or not binding_service_id.strip():
            raise ValueError("paths.connector_repo_bindings has an invalid service id")
        if not isinstance(binding, dict):
            raise ValueError(
                f"paths.connector_repo_bindings.{binding_service_id} must be an object"
            )
        connector_id = _require_string(
            binding.get("connector_id"),
            f"paths.connector_repo_bindings.{binding_service_id}.connector_id",
        )
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", connector_id) is None:
            raise ValueError(f"invalid connector id: {connector_id}")
        env_name = _require_string(
            binding.get("env_var"),
            f"paths.connector_repo_bindings.{binding_service_id}.env_var",
        )
        if _ENV_NAME.fullmatch(env_name) is None:
            raise ValueError(f"invalid connector repository environment name: {env_name}")
    for key in (
        "connector_relative_template",
        "tos_relative_to_workspace",
        "stack_runtime_relative_to_workspace",
        "stack_source_relative_to_workspace",
        "stack_logs_relative_to_runtime",
        "stack_secrets_relative_to_runtime",
        "stack_services_relative_to_runtime",
        "stack_configs_relative_to_runtime",
        "stack_deployment_manifest_relative_to_runtime",
        "stack_observation_relative_to_runtime",
        "stack_overlay_relative_to_runtime",
        "stack_registry_relative_to_workspace",
        "stack_codex_executable_relative_to_workspace_template",
        "stack_orchestration_relative_to_runtime",
        "stack_canaries_relative_to_runtime",
        "stack_effects_relative_to_runtime",
    ):
        _require_relative_template(paths.get(key), f"paths.{key}")

    limits = payload.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("MCP runtime config lacks limits object")
    for key in (
        "status_timeout_seconds",
        "search_timeout_seconds",
        "goal_lifecycle_timeout_seconds",
        "evidence_packet_timeout_seconds",
        "usage_neighborhood_timeout_seconds",
        "route_rollup_query_timeout_seconds",
        "direct_event_rollup_query_timeout_seconds",
    ):
        value = limits.get(key)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 < value <= 600
        ):
            raise ValueError(f"invalid MCP runtime limit: {key}")

    deployment = payload.get("deployment")
    if not isinstance(deployment, dict):
        raise ValueError("MCP runtime config lacks deployment object")
    for key in (
        "credentials_relative",
        "runtime_python_relative_template",
        "registry_relative_to_workspace",
    ):
        _require_relative_template(deployment.get(key), f"deployment.{key}")
    for key in (
        "contour_unit_template",
        "codex_mcp_feature",
        "recovery_unit",
    ):
        _require_string(deployment.get(key), f"deployment.{key}")
    if _CODEX_FEATURE.fullmatch(deployment["codex_mcp_feature"]) is None:
        raise ValueError("deployment.codex_mcp_feature is invalid")
    if _UNIT_NAME.fullmatch(deployment["recovery_unit"]) is None:
        raise ValueError("deployment.recovery_unit is invalid")
    client_read_contours = deployment.get("client_read_contours")
    if not isinstance(client_read_contours, list) or not client_read_contours:
        raise ValueError("deployment.client_read_contours must be a non-empty list")
    nonread_probe_contours = deployment.get("nonread_probe_contours")
    if not isinstance(nonread_probe_contours, list):
        raise ValueError("deployment.nonread_probe_contours must be a list")

    reserved = payload.get("reserved_ports")
    if not isinstance(reserved, list):
        raise ValueError("MCP runtime config lacks reserved_ports list")
    reserved_ports: set[int] = set()
    for item in reserved:
        if not isinstance(item, dict):
            raise ValueError("MCP reserved port entry must be an object")
        port = item.get("port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"invalid reserved MCP port: {port!r}")
        if port in reserved_ports:
            raise ValueError(f"duplicate reserved MCP port: {port}")
        reserved_ports.add(port)
        _require_string(item.get("owner"), "reserved port owner")
        _require_string(item.get("reason"), "reserved port reason")

    services = payload.get("services")
    if not isinstance(services, list) or not services:
        raise ValueError("MCP runtime config has no services")
    service_ids: set[str] = set()
    organ_ids: set[str] = set()
    registry_organ_ids: set[str] = set()
    ports: set[int] = set()
    env_names: set[str] = set()
    credential_names: set[str] = set()
    scopes: set[str] = set()
    clients: set[str] = set()
    contour_keys: set[tuple[str, str]] = set()
    for service in services:
        if not isinstance(service, dict):
            raise ValueError("MCP service entry must be an object")
        service_id = _require_string(service.get("service_id"), "service_id")
        if service_id in service_ids:
            raise ValueError(f"duplicate MCP service: {service_id}")
        service_ids.add(service_id)
        organ_id = _require_string(service.get("organ_id"), f"{service_id}.organ_id")
        registry_organ_id = _require_string(
            service.get("registry_organ_id"), f"{service_id}.registry_organ_id"
        )
        executable_mode = _require_string(
            service.get("runtime_executable_mode"),
            f"{service_id}.runtime_executable_mode",
        )
        if executable_mode not in {"workspace_codex", "stack_venv"}:
            raise ValueError(
                f"invalid runtime executable mode for {service_id}: {executable_mode}"
            )
        if organ_id in organ_ids:
            raise ValueError(f"duplicate MCP organ identity: {organ_id}")
        if registry_organ_id in registry_organ_ids:
            raise ValueError(
                f"duplicate MCP registry organ identity: {registry_organ_id}"
            )
        organ_ids.add(organ_id)
        registry_organ_ids.add(registry_organ_id)
        _require_string(service.get("module"), f"{service_id}.module")
        template = _require_string(
            service.get("server_name_template"),
            f"{service_id}.server_name_template",
        )
        read_unit_template = _require_string(
            service.get("read_unit_template"),
            f"{service_id}.read_unit_template",
        )
        read_unit_instance = _require_string(
            service.get("read_unit_instance"),
            f"{service_id}.read_unit_instance",
        )
        if re.fullmatch(r"[A-Za-z0-9_.-]+", read_unit_instance) is None:
            raise ValueError(
                f"invalid read unit instance for {service_id}: {read_unit_instance}"
            )
        if _UNIT_TEMPLATE.fullmatch(read_unit_template) is None:
            raise ValueError(f"invalid read unit template for {service_id}: {read_unit_template}")
        try:
            rendered_read_unit = read_unit_template.format(
                organ="organ",
                instance=read_unit_instance,
                service_id=service_id,
                contour="read",
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(
                f"invalid read unit template for {service_id}: {read_unit_template}"
            ) from exc
        if _UNIT_NAME.fullmatch(rendered_read_unit) is None:
            raise ValueError(
                f"read unit template renders an invalid unit for {service_id}: "
                f"{rendered_read_unit}"
            )
        if service.get("auth_manifest_credential") is not None:
            _require_string(
                service.get("auth_manifest_credential"),
                f"{service_id}.auth_manifest_credential",
            )
        if service.get("auth_manifest_schema") is not None:
            _require_string(
                service.get("auth_manifest_schema"),
                f"{service_id}.auth_manifest_schema",
            )
        if "{" in template and "}" not in template:
            raise ValueError(f"invalid MCP server name template: {template}")
        contours = service.get("contours")
        if not isinstance(contours, dict) or not contours:
            raise ValueError(f"{service_id} has no MCP contours")
        for contour_id, contour in contours.items():
            if not isinstance(contour_id, str) or not contour_id:
                raise ValueError(f"{service_id} has invalid contour id")
            if not isinstance(contour, dict):
                raise ValueError(f"{service_id}.{contour_id} must be an object")
            contour_keys.add((service_id, contour_id))
            port = contour.get("port")
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise ValueError(f"invalid port for {service_id}.{contour_id}: {port!r}")
            if port in reserved_ports:
                raise ValueError(f"MCP contour {service_id}.{contour_id} uses reserved port {port}")
            if port in ports:
                raise ValueError(f"duplicate MCP contour port: {port}")
            ports.add(port)
            auth = contour.get("auth")
            if not isinstance(auth, dict):
                raise ValueError(f"{service_id}.{contour_id} lacks auth identity")
            env_name = _require_string(auth.get("token_env_var"), "token_env_var")
            credential_name = _require_string(auth.get("credential_name"), "credential_name")
            scope = _require_string(auth.get("auth_scope"), "auth_scope")
            client_id = _require_string(auth.get("client_id"), "client_id")
            if _ENV_NAME.fullmatch(env_name) is None:
                raise ValueError(f"invalid bearer environment variable: {env_name}")
            if _CREDENTIAL_NAME.fullmatch(credential_name) is None:
                raise ValueError(f"invalid credential name: {credential_name}")
            if _SCOPE.fullmatch(scope) is None:
                raise ValueError(f"invalid auth scope: {scope}")
            if len(client_id) > 128:
                raise ValueError(f"invalid auth client id: {client_id}")
            for seen, value, label in (
                (env_names, env_name, "bearer environment variable"),
                (credential_names, credential_name, "credential name"),
                (scopes, scope, "auth scope"),
                (clients, client_id, "auth client id"),
            ):
                if value in seen:
                    raise ValueError(f"duplicate MCP {label}: {value}")
                seen.add(value)
    unknown_connector_services = set(connector_bindings) - service_ids
    if unknown_connector_services:
        raise ValueError(
            "connector repository bindings reference unknown MCP services: "
            f"{sorted(unknown_connector_services)}"
        )
    probe_keys: set[tuple[str, str]] = set()
    for item in nonread_probe_contours:
        if not isinstance(item, dict):
            raise ValueError("deployment.nonread_probe_contours entries must be objects")
        service_id = _require_string(item.get("service_id"), "non-read probe service")
        contour_id = _require_string(item.get("contour_id"), "non-read probe contour")
        key = (service_id, contour_id)
        if key in probe_keys:
            raise ValueError(f"duplicate non-read probe contour: {service_id}/{contour_id}")
        if key not in contour_keys:
            raise ValueError(f"unknown non-read probe contour: {service_id}/{contour_id}")
        if contour_id == "read":
            raise ValueError("non-read probe contour cannot be read")
        probe_keys.add(key)
    client_keys: set[tuple[str, str]] = set()
    client_orgs: set[str] = set()
    services_by_id = {service["service_id"]: service for service in services}
    for item in client_read_contours:
        if not isinstance(item, dict):
            raise ValueError("deployment.client_read_contours entries must be objects")
        service_id = _require_string(item.get("service_id"), "client read service")
        contour_id = _require_string(item.get("contour_id"), "client read contour")
        organ_id = _require_string(item.get("organ_id"), "client read organ")
        key = (service_id, contour_id)
        if key in client_keys:
            raise ValueError(f"duplicate client read contour: {service_id}/{contour_id}")
        if key not in contour_keys or contour_id != "read":
            raise ValueError(f"unknown client read contour: {service_id}/{contour_id}")
        if organ_id != services_by_id[service_id]["organ_id"]:
            raise ValueError(
                f"client read organ does not match service identity: {service_id}"
            )
        if organ_id in client_orgs:
            raise ValueError(f"duplicate client read organ: {organ_id}")
        client_keys.add(key)
        client_orgs.add(organ_id)


def _build_catalog(payload: dict[str, Any], metadata: Mapping[str, tuple[str, str]] | None) -> RuntimeCatalog:
    _validate_raw(payload)
    mcp = payload["mcp"]
    sdk = mcp["sdk"]
    protocol = mcp["protocol"]
    raw_transport = mcp["transport"]
    transport_config = TransportConfig(
        transport_env_var=raw_transport["transport_env_var"],
        host_env_var=raw_transport["host_env_var"],
        port_env_var=raw_transport["port_env_var"],
        default_transport=raw_transport["default_transport"],
        default_host=raw_transport["default_host"],
        loopback_hosts=tuple(raw_transport["loopback_hosts"]),
        port_min=raw_transport["port_min"],
        port_max=raw_transport["port_max"],
        protocol_version=protocol["version"],
        legacy_protocol_version=protocol["legacy_version"],
        modern_only_rejection_code=protocol["modern_only_rejection_code"],
        streamable_http_transport=raw_transport["streamable_http_transport"],
        streamable_http_path=protocol["streamable_http_path"],
        modern_only=protocol["modern_only"],
        sdk_distribution=sdk["distribution"],
        sdk_major=sdk["major"],
        sdk_requirement=sdk["requirement"],
        sdk_companion_distribution=sdk["companion_distribution"],
        tested_sdk_lock=sdk["tested_lock"],
        sdk_source_revision=sdk["source_revision"],
    )
    raw_paths = payload["paths"]
    path_config = PathConfig(
        workspace_env_var=raw_paths["workspace_env_var"],
        stack_root_env_var=raw_paths["stack_root_env_var"],
        stack_source_env_var=raw_paths["stack_source_env_var"],
        tos_root_env_var=raw_paths["tos_root_env_var"],
        tos_root_fallback_env_var=raw_paths["tos_root_fallback_env_var"],
        connector_repo_bindings=raw_paths["connector_repo_bindings"],
        connector_relative_template=raw_paths["connector_relative_template"],
        tos_relative_to_workspace=raw_paths["tos_relative_to_workspace"],
        stack_runtime_relative_to_workspace=raw_paths["stack_runtime_relative_to_workspace"],
        stack_source_relative_to_workspace=raw_paths["stack_source_relative_to_workspace"],
        stack_logs_relative_to_runtime=raw_paths["stack_logs_relative_to_runtime"],
        stack_secrets_relative_to_runtime=raw_paths["stack_secrets_relative_to_runtime"],
        stack_services_relative_to_runtime=raw_paths["stack_services_relative_to_runtime"],
        stack_configs_relative_to_runtime=raw_paths["stack_configs_relative_to_runtime"],
        stack_deployment_manifest_relative_to_runtime=raw_paths["stack_deployment_manifest_relative_to_runtime"],
        stack_observation_relative_to_runtime=raw_paths["stack_observation_relative_to_runtime"],
        stack_overlay_relative_to_runtime=raw_paths["stack_overlay_relative_to_runtime"],
        stack_registry_relative_to_workspace=raw_paths["stack_registry_relative_to_workspace"],
        stack_codex_executable_relative_to_workspace_template=raw_paths["stack_codex_executable_relative_to_workspace_template"],
        stack_orchestration_relative_to_runtime=raw_paths["stack_orchestration_relative_to_runtime"],
        stack_canaries_relative_to_runtime=raw_paths["stack_canaries_relative_to_runtime"],
        stack_effects_relative_to_runtime=raw_paths["stack_effects_relative_to_runtime"],
        abyss_machine_policy_env_var=raw_paths["abyss_machine_policy_env_var"],
        abyss_machine_state_env_var=raw_paths["abyss_machine_state_env_var"],
        abyss_machine_policy_fallback_env_var=raw_paths["abyss_machine_policy_fallback_env_var"],
        abyss_machine_state_fallback_env_var=raw_paths["abyss_machine_state_fallback_env_var"],
    )
    runtime_limits = RuntimeLimits(**payload["limits"])
    services: dict[str, ServiceConfig] = {}
    for raw_service in payload["services"]:
        service_id = raw_service["service_id"]
        package_name, package_version = (metadata or {}).get(
            service_id,
            (service_id, ""),
        )
        contours = {
            contour_id: ContourConfig(
                contour_id=contour_id,
                port=raw_contour["port"],
                auth=AuthConfig(**raw_contour["auth"]),
            )
            for contour_id, raw_contour in raw_service["contours"].items()
        }
        services[service_id] = ServiceConfig(
            service_id=service_id,
            organ_id=raw_service["organ_id"],
            registry_organ_id=raw_service["registry_organ_id"],
            runtime_executable_mode=raw_service["runtime_executable_mode"],
            package_name=package_name,
            package_version=package_version,
            module=raw_service["module"],
            server_name_template=raw_service["server_name_template"],
            read_unit_template=raw_service["read_unit_template"],
            read_unit_instance=raw_service["read_unit_instance"],
            contours=contours,
            auth_manifest_credential=raw_service.get("auth_manifest_credential"),
            auth_manifest_schema=raw_service.get("auth_manifest_schema"),
        )
    reserved_ports = {
        item["port"]: f'{item["owner"]}: {item["reason"]}'
        for item in payload["reserved_ports"]
    }
    return RuntimeCatalog(
        schema_version=payload["schema_version"],
        transport=transport_config,
        paths=path_config,
        limits=runtime_limits,
        services=services,
        reserved_ports=reserved_ports,
    )


def load_catalog(
    path: Path = CONFIG_PATH,
    *,
    metadata: Mapping[str, tuple[str, str]] | None = None,
) -> RuntimeCatalog:
    return _build_catalog(_read_json(path), metadata)


def raw_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    payload = _read_json(path)
    _validate_raw(payload)
    return payload


_CATALOG = load_catalog()
TRANSPORT_CONFIG = _CATALOG.transport
PATH_CONFIG = _CATALOG.paths
RUNTIME_LIMITS = _CATALOG.limits
MCP_PROTOCOL_VERSION = TRANSPORT_CONFIG.protocol_version
MCP_PROTOCOL_PATH = TRANSPORT_CONFIG.streamable_http_path
MCP_SDK_MAJOR = TRANSPORT_CONFIG.sdk_major
MCP_SDK_REQUIREMENT = TRANSPORT_CONFIG.sdk_requirement
MCP_SDK_COMPANION_DISTRIBUTION = TRANSPORT_CONFIG.sdk_companion_distribution
MCP_TESTED_SDK_LOCK = TRANSPORT_CONFIG.tested_sdk_lock
