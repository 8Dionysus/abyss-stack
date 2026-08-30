"""Guard the generated MCP v2 identity against configuration drift."""

from __future__ import annotations

import json
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import jsonschema
import pytest
from packaging.requirements import Requirement
from packaging.version import Version


SHARED_ROOT = Path(__file__).resolve().parent
SERVICES_ROOT = SHARED_ROOT.parent
sys.path.insert(0, str(SHARED_ROOT))

from package_targets import discover_package_targets  # noqa: E402
from build_mcp_bundle_unit import bundle_read_units, render_bundle_unit  # noqa: E402
from runtime_config import load_catalog, raw_config  # noqa: E402
from validate_systemd_projection import validate_systemd_projection  # noqa: E402


def test_runtime_catalog_matches_every_standalone_package() -> None:
    targets = discover_package_targets(SERVICES_ROOT)
    catalog = load_catalog(metadata={
        target.service_id: (target.package_name, target.package_version)
        for target in targets
    })
    assert set(catalog.services) == {target.service_id for target in targets}
    assert len({contour.port for service in catalog.services.values() for contour in service.contours.values()}) == sum(
        len(service.contours) for service in catalog.services.values()
    )
    assert not set(catalog.reserved_ports).intersection(
        contour.port
        for service in catalog.services.values()
        for contour in service.contours.values()
    )


def test_runtime_catalog_json_matches_its_schema() -> None:
    schema = json.loads((SHARED_ROOT / "runtime-config.schema.json").read_text())
    payload = json.loads((SHARED_ROOT / "runtime-config.v1.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)
    assert payload["mcp"]["sdk"]["major"] == 2
    assert payload["mcp"]["sdk"]["requirement"] == "mcp>=2,<3"
    assert re.fullmatch(r"[0-9a-f]{40}", payload["mcp"]["sdk"]["source_revision"])
    assert payload["mcp"]["sdk"]["tested_lock"] == "2.1.1"
    assert payload["mcp"]["sdk"]["companion_distribution"] == "mcp-types"
    assert payload["mcp"]["protocol"]["legacy_version"] != payload["mcp"]["protocol"]["version"]
    assert isinstance(payload["mcp"]["protocol"]["modern_only_rejection_code"], int)
    assert payload["mcp"]["protocol"]["modern_only"] is True
    assert payload["deployment"]["approved_artifacts"]["aoa_sdk"]["distribution"] == "aoa-sdk"


def test_each_package_declares_v2_major_line_and_root_runtime_keeps_test_lock() -> None:
    targets = discover_package_targets(SERVICES_ROOT)
    catalog = load_catalog(
        metadata={
            target.service_id: (target.package_name, target.package_version)
            for target in targets
        }
    )
    for target in targets:
        project = tomllib.loads(
            (target.service_root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        requirements = [
            Requirement(item)
            for item in project.get("dependencies", [])
            if Requirement(item).name.casefold() == "mcp"
        ]
        assert len(requirements) == 1, target.service_id
        requirement = requirements[0]
        assert requirement.specifier.contains(
            Version(catalog.transport.tested_sdk_lock)
        )
        assert str(requirement.specifier) in {">=2,<3", "<3,>=2"}

    # Only the stack runtime owns the checked-in hash-locked environment.  The
    # other standalone packages are intentionally major-line constrained and
    # are projected into that managed runtime at deployment time; requiring a
    # duplicated lock file in every package would recreate the drift this
    # catalog is meant to remove.
    root_lock = SERVICES_ROOT / "abyss-stack-mcp" / "requirements.lock"
    locked = {
        line.split("==", 1)[0].strip().lower(): line.strip()
        for line in root_lock.read_text(encoding="utf-8").splitlines()
        if line.strip().lower().startswith(("mcp==", "mcp-types=="))
    }
    assert set(locked) == {"mcp", "mcp-types"}
    assert locked["mcp"].startswith(f"mcp=={catalog.transport.tested_sdk_lock}")
    assert locked["mcp-types"].startswith(
        f"mcp-types=={catalog.transport.tested_sdk_lock}"
    )


def test_service_sources_use_native_runtime_without_removed_v1_seams() -> None:
    targets = discover_package_targets(SERVICES_ROOT)
    forbidden = tuple(
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])")
        for token in ("AbyssMCPServer", "http_auth_kwargs", "configure_http", "_mcp_server")
    )
    for target in targets:
        source_files = (target.service_root / "src").rglob("*.py")
        for path in source_files:
            if path.name in {"_modern_runtime.py", "_http_auth.py"}:
                continue
            source = path.read_text(encoding="utf-8")
            assert not any(token.search(source) for token in forbidden), path


def test_nonread_probe_entries_are_declared_contours() -> None:
    payload = raw_config()
    services = {
        service["service_id"]: service for service in payload["services"]
    }
    seen: set[tuple[str, str]] = set()
    for item in payload["deployment"]["nonread_probe_contours"]:
        key = (item["service_id"], item["contour_id"])
        assert key not in seen
        assert key[0] in services
        assert key[1] in services[key[0]]["contours"]
        assert key[1] != "read"
        seen.add(key)


def test_shared_bundle_is_catalog_projection() -> None:
    payload = raw_config()
    bundle_path = SHARED_ROOT.parents[2] / "systemd" / "user" / "aoa-mcp-http.service"
    actual = {
        line.removeprefix("Wants=")
        for line in bundle_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("Wants=")
    }
    expected = set(bundle_read_units(payload))
    assert actual == expected
    assert not actual.intersection(
        {
            "aoa-memo-mcp-candidate.service",
            "aoa-evals-mcp-candidate.service",
            "abyss-stack-mcp-candidate.service",
            "abyss-stack-mcp-internal-effect.service",
        }
    )
    assert bundle_path.read_text(encoding="utf-8") == render_bundle_unit(payload)


def test_systemd_mcp_projection_matches_catalog() -> None:
    validate_systemd_projection(raw_config())


def test_systemd_mcp_projection_rejects_port_drift(tmp_path) -> None:
    systemd_root = tmp_path / "systemd"
    systemd_root.mkdir()
    source_root = SHARED_ROOT.parents[2] / "systemd" / "user"
    for path in source_root.glob("*mcp*.service"):
        (systemd_root / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path = systemd_root / "abyss-stack-mcp-read.service"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            f'{raw_config()["mcp"]["transport"]["port_env_var"]}=5431',
            f'{raw_config()["mcp"]["transport"]["port_env_var"]}=1',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="port drift"):
        validate_systemd_projection(raw_config(), systemd_root)


def test_generated_path_projection_resolves_relocatable_roots(monkeypatch, tmp_path) -> None:
    target = next(
        item
        for item in discover_package_targets(SERVICES_ROOT)
        if item.service_id == "aoa-4pda-connector-mcp"
    )
    module_path = target.service_root / "src" / target.package / "_runtime_config.py"
    spec = importlib.util.spec_from_file_location("test_generated_runtime_config", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setenv("AOA_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    connector = tmp_path / "custom" / "fourpda"
    monkeypatch.setenv("AOA_4PDA_CONNECTOR_REPO", str(connector))
    paths = module.PATH_CONFIG
    assert paths.connector_repo("aoa-4pda-connector-mcp") == connector.resolve()
    assert paths.connector_repo("aoa-course-connector-mcp") == (
        tmp_path / "workspace" / "connectors" / "aoa-course-connector"
    ).resolve()
    assert paths.stack_runtime_root(str(tmp_path / "stack" / "Configs")) == (
        tmp_path / "stack"
    ).resolve()
    assert paths.stack_observation_path(str(tmp_path / "stack" / "Configs")) == (
        tmp_path / "stack" / "Logs" / "mcp" / "observations" / "current.json"
    ).resolve()
