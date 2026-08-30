"""Read the single declarative MCP runtime catalog used by protocol probes.

The protocol-lab scripts run both from a source checkout and from a deployed
Configs projection.  They therefore read JSON instead of importing a package
from either location.  The catalog is the only source for MCP protocol,
transport, contour, credential, and unit identity; live paths remain explicit
operator inputs or are derived from the deployed catalog location.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RUNTIME_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "services"
    / "_shared"
    / "runtime-config.v1.json"
)
RUNTIME_CONFIG_ENV = "ABYSS_MCP_RUNTIME_CONFIG"
LEGACY_STACK_ROOT_ENVS = ("ABYSS_MCP_STACK_ROOT", "AOA_STACK_ROOT")


class RuntimeCatalogError(ValueError):
    """The MCP runtime catalog is missing or does not meet its contract."""


_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_CREDENTIAL_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_UNIT_NAME = re.compile(r"[A-Za-z0-9_.@%-]+\.service")
_UNIT_TEMPLATE = re.compile(r"[A-Za-z0-9_.@%{}-]+\.service")
_CODEX_FEATURE = re.compile(r"mcp_[0-9]{4}_[0-9]{2}_[0-9]{2}")
_VERSION = re.compile(r"2\.[0-9]+\.[0-9]+(?:[+-][0-9A-Za-z.-]+)?")


def _non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeCatalogError(f"{label} must be a non-empty string")
    return value.strip()


def _absolute_path(raw: str, label: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise RuntimeCatalogError(f"{label} must be an absolute path")
    return path


def runtime_config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    configured = os.environ.get(RUNTIME_CONFIG_ENV, "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_RUNTIME_CONFIG


def load_runtime_catalog(explicit: Path | None = None) -> dict[str, Any]:
    path = runtime_config_path(explicit)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeCatalogError(f"unable to read MCP runtime catalog: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeCatalogError("MCP runtime catalog must be a JSON object")
    if payload.get("schema_version") != "abyss_mcp_runtime_config_v1":
        raise RuntimeCatalogError("MCP runtime catalog schema version is unsupported")
    mcp = payload.get("mcp")
    if not isinstance(mcp, dict):
        raise RuntimeCatalogError("MCP runtime catalog lacks its mcp object")
    sdk = mcp.get("sdk")
    protocol = mcp.get("protocol")
    transport = mcp.get("transport")
    if not isinstance(sdk, dict) or sdk.get("major") != 2:
        raise RuntimeCatalogError("MCP runtime catalog must admit SDK major 2 only")
    if sdk.get("requirement") != "mcp>=2,<3":
        raise RuntimeCatalogError("MCP runtime catalog has a non-v2 SDK requirement")
    companion_distribution = _non_empty(
        sdk.get("companion_distribution"), "MCP SDK companion distribution"
    )
    if companion_distribution == sdk.get("distribution"):
        raise RuntimeCatalogError("MCP SDK companion distribution must be distinct")
    tested_lock = _non_empty(sdk.get("tested_lock"), "MCP SDK tested lock")
    if _VERSION.fullmatch(tested_lock) is None:
        raise RuntimeCatalogError("MCP SDK tested lock must be an exact semantic version")
    source_revision = _non_empty(
        sdk.get("source_revision"), "MCP SDK source revision"
    )
    if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
        raise RuntimeCatalogError("MCP SDK source revision is invalid")
    if (
        not isinstance(protocol, dict)
        or not _non_empty(protocol.get("version"), "MCP protocol version")
        or not _non_empty(protocol.get("legacy_version"), "MCP legacy protocol version")
        or not isinstance(protocol.get("modern_only_rejection_code"), int)
        or isinstance(protocol.get("modern_only_rejection_code"), bool)
        or not -32099 <= protocol["modern_only_rejection_code"] <= -32000
        or protocol.get("streamable_http_path") != "/mcp"
        or protocol.get("modern_only") is not True
    ):
        raise RuntimeCatalogError("MCP runtime catalog has an invalid modern protocol")
    if not isinstance(transport, dict):
        raise RuntimeCatalogError("MCP runtime catalog lacks transport settings")
    if transport.get("streamable_http_transport") != "streamable-http":
        raise RuntimeCatalogError("MCP runtime catalog has an invalid HTTP transport")
    if not isinstance(transport.get("loopback_hosts"), list) or not transport["loopback_hosts"]:
        raise RuntimeCatalogError("MCP runtime catalog has no loopback host policy")
    deployment = payload.get("deployment")
    if not isinstance(deployment, dict):
        raise RuntimeCatalogError("MCP runtime catalog lacks deployment settings")
    for key in (
        "credentials_relative",
        "runtime_python_relative_template",
        "registry_relative_to_workspace",
        "contour_unit_template",
        "codex_mcp_feature",
        "recovery_unit",
        "runtime_repair_unit",
        "auto_repair_marker_name",
        "canary_public_key_name",
    ):
        _non_empty(deployment.get(key), f"deployment.{key}")
    if _CODEX_FEATURE.fullmatch(deployment["codex_mcp_feature"]) is None:
        raise RuntimeCatalogError("deployment.codex_mcp_feature is invalid")
    if _UNIT_NAME.fullmatch(deployment["recovery_unit"]) is None:
        raise RuntimeCatalogError("deployment.recovery_unit is invalid")
    if _UNIT_NAME.fullmatch(deployment["runtime_repair_unit"]) is None:
        raise RuntimeCatalogError("deployment.runtime_repair_unit is invalid")
    for key in ("auto_repair_marker_name", "canary_public_key_name"):
        if _CREDENTIAL_NAME.fullmatch(deployment[key]) is None:
            raise RuntimeCatalogError(f"deployment.{key} is invalid")
    client_read_contours = deployment.get("client_read_contours")
    if not isinstance(client_read_contours, list) or not client_read_contours:
        raise RuntimeCatalogError(
            "deployment.client_read_contours must be a non-empty list"
        )
    if not isinstance(deployment.get("nonread_probe_contours"), list):
        raise RuntimeCatalogError("deployment.nonread_probe_contours must be a list")
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        raise RuntimeCatalogError("MCP runtime catalog has no services")
    seen: set[str] = set()
    organ_ids: set[str] = set()
    registry_organ_ids: set[str] = set()
    for service in services:
        if not isinstance(service, dict):
            raise RuntimeCatalogError("MCP service record must be an object")
        service_id = _non_empty(service.get("service_id"), "MCP service id")
        if service_id in seen:
            raise RuntimeCatalogError(f"duplicate MCP service id: {service_id}")
        seen.add(service_id)
        organ_id = _non_empty(service.get("organ_id"), f"{service_id} organ id")
        registry_organ_id = _non_empty(
            service.get("registry_organ_id"), f"{service_id} registry organ id"
        )
        if organ_id in organ_ids or registry_organ_id in registry_organ_ids:
            raise RuntimeCatalogError(
                f"MCP organ identities must be unique: {service_id}"
            )
        organ_ids.add(organ_id)
        registry_organ_ids.add(registry_organ_id)
        read_unit_template = _non_empty(
            service.get("read_unit_template"),
            f"{service_id} read unit template",
        )
        read_unit_instance = _non_empty(
            service.get("read_unit_instance"),
            f"{service_id} read unit instance",
        )
        if re.fullmatch(r"[A-Za-z0-9_.-]+", read_unit_instance) is None:
            raise RuntimeCatalogError(
                f"invalid read unit instance: {service_id}"
            )
        if _UNIT_TEMPLATE.fullmatch(read_unit_template) is None:
            raise RuntimeCatalogError(
                f"invalid read unit template: {service_id}"
            )
        try:
            rendered_unit = read_unit_template.format(
                organ="organ",
                instance=read_unit_instance,
                service_id=service_id,
                contour="read",
            )
        except (KeyError, ValueError) as exc:
            raise RuntimeCatalogError(
                f"invalid read unit template: {service_id}"
            ) from exc
        if _UNIT_NAME.fullmatch(rendered_unit) is None:
            raise RuntimeCatalogError(
                f"read unit template renders an invalid unit: {service_id}"
            )
        contours = service.get("contours")
        if not isinstance(contours, dict) or not contours:
            raise RuntimeCatalogError(f"MCP service has no contours: {service_id}")
        for contour_id, contour in contours.items():
            if not isinstance(contour_id, str) or not contour_id:
                raise RuntimeCatalogError(f"invalid contour id for {service_id}")
            if not isinstance(contour, dict) or not isinstance(contour.get("port"), int):
                raise RuntimeCatalogError(f"invalid contour for {service_id}/{contour_id}")
            auth = contour.get("auth")
            if not isinstance(auth, dict):
                raise RuntimeCatalogError(f"missing auth for {service_id}/{contour_id}")
            for key in ("token_env_var", "credential_name", "auth_scope", "client_id"):
                _non_empty(auth.get(key), f"{service_id}/{contour_id} auth {key}")
            if _ENV_NAME.fullmatch(auth["token_env_var"]) is None:
                raise RuntimeCatalogError("MCP auth environment name is invalid")
            if _CREDENTIAL_NAME.fullmatch(auth["credential_name"]) is None:
                raise RuntimeCatalogError("MCP credential name is invalid")
    client_keys: set[tuple[str, str]] = set()
    client_orgs: set[str] = set()
    for item in client_read_contours:
        if not isinstance(item, dict):
            raise RuntimeCatalogError("MCP client read entry must be an object")
        service_id = _non_empty(item.get("service_id"), "MCP client read service")
        contour_id = _non_empty(item.get("contour_id"), "MCP client read contour")
        organ_id = _non_empty(item.get("organ_id"), "MCP client read organ")
        if contour_id != "read":
            raise RuntimeCatalogError("MCP client read entries must use read contours")
        key = (service_id, contour_id)
        if key in client_keys or organ_id in client_orgs:
            raise RuntimeCatalogError("MCP client read entries must be unique")
        contour_for(payload, service_id, contour_id)
        client_keys.add(key)
        client_orgs.add(organ_id)
    return payload


def mcp_settings(catalog: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    mcp = catalog["mcp"]
    return mcp["sdk"], mcp["protocol"], mcp["transport"]


def probe_limits(catalog: Mapping[str, Any]) -> dict[str, float]:
    """Return the centrally reviewed protocol-probe budgets."""

    limits = catalog.get("limits")
    if not isinstance(limits, Mapping):
        raise RuntimeCatalogError("MCP runtime catalog lacks limits")
    names = (
        "protocol_probe_server_start_timeout_seconds",
        "protocol_probe_request_timeout_seconds",
        "protocol_probe_stdio_call_timeout_seconds",
        "protocol_probe_stdio_timeout_seconds",
        "protocol_probe_connect_timeout_seconds",
        "protocol_probe_process_shutdown_timeout_seconds",
        "protocol_probe_process_kill_timeout_seconds",
    )
    result: dict[str, float] = {}
    for name in names:
        value = limits.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise RuntimeCatalogError(f"MCP runtime catalog has invalid limit: {name}")
        result[name] = float(value)
    return result


def runtime_identity(
    runtime_python: Path,
    sdk_settings: Mapping[str, Any],
) -> dict[str, Any]:
    """Read and compare the exact reviewed SDK pair from one interpreter."""

    distributions = [
        str(sdk_settings["distribution"]),
        str(sdk_settings["companion_distribution"]),
    ]
    code = (
        "import importlib.metadata as metadata, json\n"
        f"names = {distributions!r}\n"
        "versions = {}\n"
        "for name in names:\n"
        "    try:\n"
        "        versions[name] = metadata.version(name)\n"
        "    except metadata.PackageNotFoundError:\n"
        "        versions[name] = None\n"
        "print(json.dumps(versions, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(runtime_python), "-I", "-B", "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    versions = json.loads(completed.stdout.strip())
    expected = {
        str(sdk_settings["distribution"]): str(sdk_settings["tested_lock"]),
        str(sdk_settings["companion_distribution"]): str(sdk_settings["tested_lock"]),
    }
    return {
        "versions": versions,
        "expected": expected,
        "exact_pair": versions == expected,
    }


def deployment_settings(catalog: Mapping[str, Any]) -> dict[str, Any]:
    deployment = catalog.get("deployment")
    if not isinstance(deployment, dict):
        raise RuntimeCatalogError("MCP runtime catalog lacks deployment settings")
    return deployment


def service_for_organ(catalog: Mapping[str, Any], organ_id: str) -> dict[str, Any]:
    services = catalog["services"]
    candidates = [
        service
        for service in services
        if isinstance(service, dict)
        and organ_id in {
            service.get("organ_id"),
            service.get("registry_organ_id"),
        }
    ]
    if len(candidates) != 1:
        raise RuntimeCatalogError(
            f"MCP runtime catalog has no unique service for organ {organ_id!r}"
        )
    return candidates[0]


def contour_for(
    catalog: Mapping[str, Any], service_id: str, contour_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    services = [
        service
        for service in catalog["services"]
        if isinstance(service, dict) and service.get("service_id") == service_id
    ]
    if len(services) != 1:
        raise RuntimeCatalogError(f"unknown MCP service: {service_id}")
    service = services[0]
    contours = service.get("contours")
    contour = contours.get(contour_id) if isinstance(contours, dict) else None
    if not isinstance(contour, dict):
        raise RuntimeCatalogError(f"unknown MCP contour: {service_id}/{contour_id}")
    return service, contour


def stack_root_from_catalog(config_path: Path) -> Path:
    catalog = load_runtime_catalog(config_path)
    paths = catalog.get("paths")
    if not isinstance(paths, Mapping):
        raise RuntimeCatalogError("MCP runtime catalog has no path settings")
    canonical_env = _non_empty(paths.get("stack_root_env_var"), "paths.stack_root_env_var")
    for environment_name in (canonical_env, *LEGACY_STACK_ROOT_ENVS):
        configured = os.environ.get(environment_name, "").strip()
        if not configured:
            continue
        path = _absolute_path(configured, environment_name)
        return path.parent if path.name == "Configs" else path
    for parent in (config_path, *config_path.parents):
        if parent.name == "Configs":
            return parent.parent
    raise RuntimeCatalogError(
        f"{canonical_env} is required when the runtime catalog is not deployed under Configs"
    )


def workspace_root_from_catalog(catalog: Mapping[str, Any], stack_root: Path) -> Path:
    """Resolve the workspace without baking a host-specific deployment root."""

    paths = catalog.get("paths")
    if not isinstance(paths, Mapping):
        raise RuntimeCatalogError("MCP runtime catalog has no path settings")
    env_name = _non_empty(paths.get("workspace_env_var"), "paths.workspace_env_var")
    configured = os.environ.get(env_name, "").strip()
    if configured:
        return _absolute_path(configured, env_name)
    return stack_root.resolve().parent


def stack_relative_path(
    catalog: Mapping[str, Any], stack_root: Path, setting: str
) -> Path:
    """Resolve one relative runtime path from the catalog."""

    paths = catalog.get("paths")
    if not isinstance(paths, Mapping):
        raise RuntimeCatalogError("MCP runtime catalog has no path settings")
    relative = _non_empty(paths.get(setting), f"paths.{setting}")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeCatalogError(f"{setting} must be a relative path")
    return stack_root.resolve() / path


def codex_executable_ref(catalog: Mapping[str, Any], instance: str) -> str:
    """Render a workspace-relative Codex executable reference."""

    paths = catalog.get("paths")
    if not isinstance(paths, Mapping):
        raise RuntimeCatalogError("MCP runtime catalog has no path settings")
    template = _non_empty(
        paths.get("stack_codex_executable_relative_to_workspace_template"),
        "paths.stack_codex_executable_relative_to_workspace_template",
    )
    workspace_var = _non_empty(paths.get("workspace_env_var"), "paths.workspace_env_var")
    try:
        relative = template.format(instance=instance)
    except (KeyError, ValueError) as exc:
        raise RuntimeCatalogError("invalid Codex executable path template") from exc
    return f"${{{workspace_var}}}/{relative}"


def render_template(template: str, **values: str) -> str:
    try:
        rendered = template.format(**values)
    except (KeyError, ValueError) as exc:
        raise RuntimeCatalogError(f"invalid MCP deployment template: {template!r}") from exc
    if not rendered:
        raise RuntimeCatalogError("MCP deployment template rendered an empty value")
    return rendered


def credentials_root(catalog: Mapping[str, Any], stack_root: Path) -> Path:
    relative = deployment_settings(catalog)["credentials_relative"]
    return stack_root / relative


def registry_path(catalog: Mapping[str, Any], stack_root: Path) -> Path:
    relative = deployment_settings(catalog)["registry_relative_to_workspace"]
    return stack_root.parent / relative


def runtime_python_path(
    catalog: Mapping[str, Any], stack_root: Path, service_id: str
) -> Path:
    template = deployment_settings(catalog)["runtime_python_relative_template"]
    return stack_root / render_template(template, service_id=service_id)


def contour_unit_name(
    catalog: Mapping[str, Any], service_id: str, contour_id: str, organ_id: str
) -> str:
    deployment = deployment_settings(catalog)
    service, _ = contour_for(catalog, service_id, contour_id)
    if contour_id == "read":
        template = service.get("read_unit_template")
        if not isinstance(template, str):
            raise RuntimeCatalogError(f"MCP service has no read unit template: {service_id}")
        instance = service.get("read_unit_instance")
        if not isinstance(instance, str) or not instance:
            raise RuntimeCatalogError(f"MCP service has no read unit instance: {service_id}")
        return render_template(
            template,
            service_id=service_id,
            contour=contour_id.replace("_", "-"),
            organ=organ_id,
            instance=instance,
        )
    return render_template(
        deployment["contour_unit_template"],
        service_id=service_id,
        contour=contour_id.replace("_", "-"),
        organ=organ_id,
    )


def admitted_read_entries(
    catalog: Mapping[str, Any], registry: Mapping[str, Any]
) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    records = registry.get("records")
    if not isinstance(records, list):
        raise RuntimeCatalogError("MCP registry has no records list")
    rows: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        organ_id = record.get("organ_id")
        contours = record.get("contours")
        if not isinstance(organ_id, str) or not isinstance(contours, list):
            continue
        for contour in contours:
            if (
                isinstance(contour, dict)
                and contour.get("contour_id") == "read"
                and contour.get("registry_state") == "admitted"
            ):
                service = service_for_organ(catalog, organ_id)
                _, declared = contour_for(catalog, service["service_id"], "read")
                rows.append((organ_id, service["service_id"], service, declared))
    if not rows:
        raise RuntimeCatalogError("MCP registry has no admitted read contours")
    return rows


def declared_client_read_entries(
    catalog: Mapping[str, Any],
) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    entries: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for item in deployment_settings(catalog)["client_read_contours"]:
        service_id = str(item["service_id"])
        contour_id = str(item["contour_id"])
        organ_id = str(item["organ_id"])
        service, contour = contour_for(catalog, service_id, contour_id)
        entries.append((organ_id, service_id, service, contour))
    return entries


def client_read_entries(
    catalog: Mapping[str, Any], registry: Mapping[str, Any] | None = None
) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    """Use admitted registry state when available, with source fallback for tests."""

    if registry is not None:
        return admitted_read_entries(catalog, registry)
    return declared_client_read_entries(catalog)


def codex_client_settings(
    catalog: Mapping[str, Any], stack_root: Path
) -> tuple[str, str, list[tuple[str, int, str, str]]]:
    """Return the client feature, recovery unit, and credential/readiness rows."""

    deployment = deployment_settings(catalog)
    registry_file = registry_path(catalog, stack_root)
    registry: Mapping[str, Any] | None = None
    if registry_file.is_file():
        try:
            loaded = json.loads(registry_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeCatalogError(
                f"unable to read MCP admission registry: {registry_file}"
            ) from exc
        if not isinstance(loaded, dict):
            raise RuntimeCatalogError("MCP admission registry must be a JSON object")
        registry = loaded
    rows: list[tuple[str, int, str, str]] = []
    for organ_id, service_id, _service, contour in client_read_entries(catalog, registry):
        auth = contour["auth"]
        rows.append(
            (
                contour_unit_name(catalog, service_id, "read", organ_id),
                int(contour["port"]),
                str(auth["credential_name"]),
                str(auth["token_env_var"]),
            )
        )
    return (
        str(deployment["codex_mcp_feature"]),
        str(deployment["recovery_unit"]),
        rows,
    )


def _emit_codex_client(catalog: Mapping[str, Any], stack_root: Path) -> int:
    feature, recovery_unit, rows = codex_client_settings(catalog, stack_root)
    print(f"FEATURE\t{feature}")
    print(f"RECOVERY\t{recovery_unit}")
    print(f"STACK_ROOT\t{stack_root}")
    print(f"CREDENTIALS_ROOT\t{credentials_root(catalog, stack_root)}")
    for unit, port, credential, env_name in rows:
        print(f"READ\t{unit}\t{port}\t{credential}\t{env_name}")
    return 0


def nonread_probe_entries(
    catalog: Mapping[str, Any],
) -> list[tuple[str, str, str, dict[str, Any], dict[str, Any]]]:
    deployment = deployment_settings(catalog)
    configured = deployment.get("nonread_probe_contours")
    if not isinstance(configured, list):
        raise RuntimeCatalogError("MCP runtime catalog has no non-read probe list")
    entries: list[tuple[str, str, str, dict[str, Any], dict[str, Any]]] = []
    for item in configured:
        if not isinstance(item, dict):
            raise RuntimeCatalogError("MCP non-read probe entry must be an object")
        service_id = _non_empty(item.get("service_id"), "MCP probe service id")
        contour_id = _non_empty(item.get("contour_id"), "MCP probe contour id")
        service, contour = contour_for(catalog, service_id, contour_id)
        organ_id = str(service["organ_id"])
        unit = contour_unit_name(catalog, service_id, contour_id, organ_id)
        entries.append((organ_id, contour_id, unit, service, contour))
    return entries


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-config", type=Path)
    parser.add_argument("--stack-root", type=Path)
    parser.add_argument("--emit", choices=("codex-client",), required=True)
    args = parser.parse_args()
    config_path = runtime_config_path(args.runtime_config).resolve()
    catalog = load_runtime_catalog(config_path)
    stack_root = args.stack_root or stack_root_from_catalog(config_path)
    if not stack_root.is_absolute():
        raise RuntimeCatalogError("MCP stack root must be absolute")
    if args.emit == "codex-client":
        return _emit_codex_client(catalog, stack_root)
    raise RuntimeCatalogError(f"unsupported MCP catalog projection: {args.emit}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeCatalogError as exc:
        print(f"runtime catalog error: {exc}", file=sys.stderr)
        raise SystemExit(78) from exc
