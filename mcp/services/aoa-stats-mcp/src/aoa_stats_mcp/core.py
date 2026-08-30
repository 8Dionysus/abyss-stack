from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ._runtime_config import PATH_CONFIG

CATALOG_RELATIVE = Path("generated/summary_surface_catalog.min.json")
LIVE_CATALOG_RELATIVE = Path("state/generated/summary_surface_catalog.min.json")
OWNER_INVENTORY_RELATIVE = Path("stats/federation/owner-inventory.json")
SOURCE_HOME_RELATIVE = Path("stats/source_home.manifest.json")
BOUNDARIES_RELATIVE = Path("docs/BOUNDARIES.md")
DESIGN_RELATIVE = Path("DESIGN.md")
PACKET_READER_RELATIVE = Path("scripts/read_measurement_packet.py")
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_LIMIT = 100
ACCESS_AUTHORITY_CEILING = (
    "Read-only access only; this service does not attest owner truth, evidence "
    "validity, freshness, proof, or permission to act."
)


class StatsAccessError(RuntimeError):
    """Raised when a bounded stats access operation cannot be completed safely."""


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StatsAccessError(f"{label} is unavailable") from exc
    if size > MAX_JSON_BYTES:
        raise StatsAccessError(f"{label} exceeds the {MAX_JSON_BYTES}-byte access limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StatsAccessError(f"{label} is not readable JSON") from exc
    if not isinstance(payload, dict):
        raise StatsAccessError(f"{label} must be a JSON object")
    return payload


def _child_path(root: Path, ref: str | Path, *, label: str) -> Path:
    relative = Path(ref)
    if relative.is_absolute():
        raise StatsAccessError(f"{label} must be relative")
    root_resolved = root.resolve(strict=False)
    candidate = (root_resolved / relative).resolve(strict=False)
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise StatsAccessError(f"{label} escapes its owner root") from exc
    return candidate


def _preview_json(value: Any, *, limit: int) -> Any:
    if not 1 <= limit <= MAX_PREVIEW_LIMIT:
        raise StatsAccessError(
            f"preview limit must be between 1 and {MAX_PREVIEW_LIMIT}"
        )
    if isinstance(value, list):
        return {
            "preview_only": True,
            "total_items": len(value),
            "preview_limit": limit,
            "items": value[:limit],
        }
    if isinstance(value, dict):
        preview: dict[str, Any] = {
            "preview_only": True,
            "preview_limit": limit,
        }
        for key, item in value.items():
            if isinstance(item, list):
                preview[key] = item[:limit]
                preview[f"{key}_total_items"] = len(item)
            else:
                preview[key] = item
        return preview
    return value


def _parse_source_roots(values: Mapping[str, str | Path] | None) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for repo, value in (values or {}).items():
        roots[str(repo)] = Path(value).expanduser().resolve()
    return roots


@dataclass(slots=True)
class AoAStatsMCPState:
    workspace_root: Path
    aoa_stats_root: Path
    source_roots: dict[str, Path] = field(default_factory=dict)

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        aoa_stats_root: str | Path | None = None,
        source_roots: Mapping[str, str | Path] | None = None,
    ) -> "AoAStatsMCPState":
        workspace = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or PATH_CONFIG.workspace_root()
        ).expanduser().resolve()
        stats_root = Path(
            aoa_stats_root
            or os.environ.get("AOA_STATS_ROOT")
            or os.environ.get("AOA_STATS_REPO_ROOT")
            or workspace / "aoa-stats"
        ).expanduser()
        if not stats_root.is_absolute():
            stats_root = workspace / stats_root

        resolved_sources = _parse_source_roots(source_roots)
        stack_source = os.environ.get(PATH_CONFIG.stack_source_env_var) or os.environ.get(
            PATH_CONFIG.stack_root_env_var
        )
        if stack_source and "abyss-stack" not in resolved_sources:
            resolved_sources["abyss-stack"] = Path(stack_source).expanduser().resolve()
        machine_source = os.environ.get("ABYSS_MACHINE_REPO_ROOT") or os.environ.get(
            "AOA_ABYSS_MACHINE_ROOT"
        )
        if machine_source and "abyss-machine" not in resolved_sources:
            resolved_sources["abyss-machine"] = Path(machine_source).expanduser().resolve()

        return cls(
            workspace_root=workspace,
            aoa_stats_root=stats_root.resolve(),
            source_roots=resolved_sources,
        )

    def _central_path(self, relative: Path, *, label: str) -> Path:
        return _child_path(self.aoa_stats_root, relative, label=label)

    def owner_inventory(self) -> dict[str, Any]:
        return _read_json(
            self._central_path(OWNER_INVENTORY_RELATIVE, label="owner inventory ref"),
            label="aoa-stats owner inventory",
        )

    def source_home(self) -> dict[str, Any]:
        return _read_json(
            self._central_path(SOURCE_HOME_RELATIVE, label="source-home ref"),
            label="aoa-stats source-home manifest",
        )

    def _active_catalog_path(self) -> tuple[Path, str]:
        live = self._central_path(LIVE_CATALOG_RELATIVE, label="live catalog ref")
        if live.is_file():
            return live, "live_materialized"
        return (
            self._central_path(CATALOG_RELATIVE, label="committed catalog ref"),
            "committed_reference",
        )

    def _load_catalog(self, path: Path, *, live: bool) -> dict[str, Any]:
        catalog = _read_json(path, label="aoa-stats summary surface catalog")
        if not live:
            return catalog
        surfaces = catalog.get("surfaces")
        if not isinstance(surfaces, list):
            return catalog
        normalized = dict(catalog)
        normalized["surfaces"] = []
        for item in surfaces:
            if not isinstance(item, dict):
                normalized["surfaces"].append(item)
                continue
            row = dict(item)
            ref = row.get("surface_ref")
            if isinstance(ref, str) and ref.startswith("generated/"):
                row["surface_ref"] = str(Path("state") / ref)
            normalized["surfaces"].append(row)
        return normalized

    def catalog(self) -> dict[str, Any]:
        path, posture = self._active_catalog_path()
        return self._load_catalog(path, live=posture == "live_materialized")

    @staticmethod
    def _catalog_surfaces(catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
        surfaces = catalog.get("surfaces")
        if not isinstance(surfaces, list):
            raise StatsAccessError("summary surface catalog has no surfaces list")
        return [item for item in surfaces if isinstance(item, dict)]

    def _catalog_candidates(self) -> list[tuple[dict[str, Any], str]]:
        active_path, active_posture = self._active_catalog_path()
        candidates = [
            (
                self._load_catalog(
                    active_path,
                    live=active_posture == "live_materialized",
                ),
                active_posture,
            )
        ]
        if active_posture == "live_materialized":
            committed = self._central_path(
                CATALOG_RELATIVE,
                label="committed catalog ref",
            )
            if committed.is_file():
                candidates.append(
                    (self._load_catalog(committed, live=False), "committed_reference")
                )
        return candidates

    def surface_read(
        self,
        *,
        surface_name: str | None = None,
        surface_ref: str | None = None,
        mode: str = "preview",
        limit: int = 5,
    ) -> dict[str, Any]:
        if (surface_name is None) == (surface_ref is None):
            raise StatsAccessError("provide exactly one of surface_name or surface_ref")
        normalized_mode = mode.strip().casefold()
        if normalized_mode not in {"preview", "full"}:
            raise StatsAccessError("mode must be 'preview' or 'full'")
        if not 1 <= limit <= MAX_PREVIEW_LIMIT:
            raise StatsAccessError(
                f"preview limit must be between 1 and {MAX_PREVIEW_LIMIT}"
            )

        selected: dict[str, Any] | None = None
        selected_posture = ""
        for catalog, posture in self._catalog_candidates():
            for profile in self._catalog_surfaces(catalog):
                if surface_name is not None and profile.get("name") == surface_name:
                    selected = profile
                    selected_posture = posture
                    break
                if surface_ref is not None and profile.get("surface_ref") == surface_ref:
                    selected = profile
                    selected_posture = posture
                    break
            if selected is not None:
                break
        if selected is None:
            requested = surface_name if surface_name is not None else surface_ref
            raise StatsAccessError(f"unknown catalog surface: {requested}")

        selected_ref = selected.get("surface_ref")
        if not isinstance(selected_ref, str) or not selected_ref:
            raise StatsAccessError("catalog surface has no usable surface_ref")
        path = self._central_path(Path(selected_ref), label="catalog surface ref")
        live_capable = bool(selected.get("live_state_capable"))
        observation_posture = (
            "live_materialized_freshness_unattested"
            if selected_posture == "live_materialized" and live_capable
            else "reference_only"
        )
        if not path.is_file():
            return {
                "owner_repo": "aoa-stats",
                "surface_kind": "derived_summary_surface",
                "status": "missing",
                "surface_ref": selected_ref,
                "surface_profile": selected,
                "mode": normalized_mode,
                "observation_posture": observation_posture,
                "freshness_status": "not_attested",
                "payload": None,
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }

        data = _read_json(path, label=f"catalog surface {selected.get('name')}")
        payload = (
            _preview_json(data, limit=limit)
            if normalized_mode == "preview"
            else data
        )
        return {
            "owner_repo": "aoa-stats",
            "surface_kind": "derived_summary_surface",
            "status": "available",
            "surface_ref": selected_ref,
            "surface_profile": selected,
            "mode": normalized_mode,
            "observation_posture": observation_posture,
            "freshness_status": "not_attested",
            "payload": payload,
            "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
        }

    def boundary_rules(self) -> dict[str, Any]:
        source_home = self.source_home()
        branches = source_home.get("branches")
        branch_rows = []
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                branch_rows.append(
                    {
                        "id": branch.get("id"),
                        "path": branch.get("path"),
                        "owner_surface": branch.get("owner_surface"),
                        "authority_ceiling": branch.get("authority_ceiling"),
                    }
                )
        return {
            "schema": "aoa_stats_mcp_boundary_rules_v1",
            "truth_status": "source_references_only",
            "source_owner": "aoa-stats",
            "access_owner": "abyss-stack",
            "source_home_ref": SOURCE_HOME_RELATIVE.as_posix(),
            "boundary_ref": BOUNDARIES_RELATIVE.as_posix(),
            "design_ref": DESIGN_RELATIVE.as_posix(),
            "owner_inventory_ref": OWNER_INVENTORY_RELATIVE.as_posix(),
            "packet_reader_ref": PACKET_READER_RELATIVE.as_posix(),
            "source_role": source_home.get("role"),
            "branch_authority_ceilings": branch_rows,
            "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
        }

    def _inventory_entries(self) -> list[dict[str, Any]]:
        entries = self.owner_inventory().get("owners")
        if not isinstance(entries, list):
            raise StatsAccessError("owner inventory has no owners list")
        return [entry for entry in entries if isinstance(entry, dict)]

    def _owner_entry(self, repo: str) -> dict[str, Any] | None:
        return next(
            (entry for entry in self._inventory_entries() if entry.get("repo_id") == repo),
            None,
        )

    def _owner_root(self, entry: Mapping[str, Any]) -> tuple[Path | None, str]:
        repo = str(entry.get("repo_id") or "")
        if repo == "aoa-stats":
            return self.aoa_stats_root, "central_source"
        route = str(entry.get("workspace_route") or "")
        route_kind, separator, route_value = route.partition(":")
        if not separator or not route_value:
            return None, "invalid_route"
        if route_kind == "workspace":
            return (
                _child_path(
                    self.workspace_root,
                    route_value,
                    label=f"{repo} workspace route",
                ),
                "workspace",
            )
        if route_kind == "source":
            source_root = self.source_roots.get(repo)
            return (source_root, "explicit_source" if source_root else "unresolved_source")
        return None, "unsupported_route"

    @staticmethod
    def _port_relative(entry: Mapping[str, Any]) -> Path:
        repo = str(entry.get("repo_id") or "")
        port_ref = str(entry.get("port_ref") or "")
        prefix, separator, relative = port_ref.partition(":")
        if not separator or prefix != repo or not relative:
            raise StatsAccessError(f"invalid port_ref for {repo}")
        return Path(relative)

    def _owner_materialization(self, entry: Mapping[str, Any]) -> dict[str, Any]:
        repo = str(entry.get("repo_id") or "")
        root, route_resolution = self._owner_root(entry)
        row = {
            "repo_id": repo,
            "workspace_route": entry.get("workspace_route"),
            "owner_boundary_ref": entry.get("owner_boundary_ref"),
            "classification": entry.get("classification"),
            "port_ref": entry.get("port_ref"),
            "route_resolution": route_resolution,
            "materialization": "unresolved",
        }
        if root is None:
            return row
        if not root.is_dir():
            row["materialization"] = "owner_root_missing"
            return row
        port_path = _child_path(root, self._port_relative(entry), label=f"{repo} port ref")
        row["materialization"] = "available" if port_path.is_file() else "port_missing"
        return row

    def owner_port_read(
        self,
        *,
        repo: str | None = None,
        measurement_id: str | None = None,
    ) -> dict[str, Any]:
        if repo is None:
            if measurement_id is not None:
                raise StatsAccessError("measurement_id requires repo")
            inventory = self.owner_inventory()
            rows = [self._owner_materialization(entry) for entry in self._inventory_entries()]
            materialization_counts: dict[str, int] = {}
            for row in rows:
                status = str(row["materialization"])
                materialization_counts[status] = materialization_counts.get(status, 0) + 1
            return {
                "schema": "aoa_stats_mcp_owner_port_inventory_v1",
                "truth_status": "inventory_and_local_materialization_only",
                "contract_version": inventory.get("contract_version"),
                "owner_count": len(rows),
                "materialization_counts": materialization_counts,
                "owners": rows,
                "routed_surfaces": inventory.get("routed_surfaces", []),
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }

        entry = self._owner_entry(repo)
        if entry is None:
            return {
                "schema": "aoa_stats_mcp_owner_port_read_v1",
                "truth_status": "inventory_and_local_definition_only",
                "repo": repo,
                "status": "unknown_owner",
                "measurement_id": measurement_id,
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }
        materialization = self._owner_materialization(entry)
        if materialization["materialization"] != "available":
            return {
                "schema": "aoa_stats_mcp_owner_port_read_v1",
                "truth_status": "inventory_and_local_definition_only",
                "repo": repo,
                "status": materialization["materialization"],
                "measurement_id": measurement_id,
                "inventory_entry": entry,
                "materialization": materialization,
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }

        root, _ = self._owner_root(entry)
        assert root is not None
        port_path = _child_path(root, self._port_relative(entry), label=f"{repo} port ref")
        port = _read_json(port_path, label=f"{repo} stats port")
        if port.get("owner_repo") != repo:
            raise StatsAccessError(f"{repo} stats port owner_repo does not match inventory")

        if repo == "aoa-stats":
            branches = port.get("branches") if isinstance(port.get("branches"), list) else []
            return {
                "schema": "aoa_stats_mcp_owner_port_read_v1",
                "truth_status": "central_source_definition_only",
                "repo": repo,
                "status": "available",
                "inventory_entry": entry,
                "source_home": {
                    "schema_version": port.get("schema_version"),
                    "status": port.get("status"),
                    "role": port.get("role"),
                    "branches": [
                        {
                            "id": branch.get("id"),
                            "path": branch.get("path"),
                            "role": branch.get("role"),
                            "owner_surface": branch.get("owner_surface"),
                            "authority_ceiling": branch.get("authority_ceiling"),
                        }
                        for branch in branches
                        if isinstance(branch, dict)
                    ],
                },
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }

        measurements = port.get("measurements")
        measurement_rows = (
            [item for item in measurements if isinstance(item, dict)]
            if isinstance(measurements, list)
            else []
        )
        if measurement_id is None:
            return {
                "schema": "aoa_stats_mcp_owner_port_read_v1",
                "truth_status": "owner_local_definition_only",
                "repo": repo,
                "status": "available",
                "inventory_entry": entry,
                "port": port,
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }

        measurement = next(
            (row for row in measurement_rows if row.get("measurement_id") == measurement_id),
            None,
        )
        if measurement is None:
            return {
                "schema": "aoa_stats_mcp_owner_port_read_v1",
                "truth_status": "owner_local_definition_only",
                "repo": repo,
                "status": "measurement_missing",
                "measurement_id": measurement_id,
                "available_measurement_ids": [
                    row.get("measurement_id") for row in measurement_rows
                ],
                "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
            }
        exports = port.get("exports")
        export_rows = (
            [item for item in exports if isinstance(item, dict)]
            if isinstance(exports, list)
            else []
        )
        matching_exports = [
            row for row in export_rows if row.get("measurement_id") == measurement_id
        ]
        questions = port.get("questions")
        question_rows = (
            [item for item in questions if isinstance(item, dict)]
            if isinstance(questions, list)
            else []
        )
        question = next(
            (row for row in question_rows if row.get("id") == measurement.get("question_ref")),
            None,
        )
        return {
            "schema": "aoa_stats_mcp_owner_port_read_v1",
            "truth_status": "owner_local_definition_only",
            "repo": repo,
            "status": "available",
            "measurement_id": measurement_id,
            "evidence_posture": port.get("evidence_posture"),
            "question": question,
            "measurement": measurement,
            "exports": matching_exports,
            "owner_authority_ceiling": measurement.get("authority_ceiling"),
            "access_authority_ceiling": ACCESS_AUTHORITY_CEILING,
        }

    def packet_check(
        self,
        *,
        contract: Mapping[str, Any],
        packet: Mapping[str, Any],
    ) -> dict[str, Any]:
        reader = self._central_path(PACKET_READER_RELATIVE, label="packet-reader ref")
        if not reader.is_file():
            raise StatsAccessError("aoa-stats public packet reader is unavailable")
        request = {
            "schema_version": "aoa_stats_packet_read_request_v1",
            "contract": dict(contract),
            "packet": dict(packet),
        }
        encoded_request = json.dumps(request, ensure_ascii=False)
        if len(encoded_request.encode("utf-8")) > MAX_JSON_BYTES:
            raise StatsAccessError("aoa-stats packet request exceeds the access limit")
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            completed = subprocess.run(
                [sys.executable, str(reader)],
                cwd=self.aoa_stats_root,
                env=env,
                input=encoded_request,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except subprocess.TimeoutExpired as exc:
            raise StatsAccessError("aoa-stats public packet reader timed out") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip().replace("\n", " ")[:1000]
            raise StatsAccessError(
                f"aoa-stats public packet reader failed with exit {completed.returncode}"
                + (f": {detail}" if detail else "")
            )
        if len(completed.stdout.encode("utf-8")) > MAX_JSON_BYTES:
            raise StatsAccessError("aoa-stats packet result exceeds the access limit")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise StatsAccessError("aoa-stats public packet reader returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise StatsAccessError("aoa-stats public packet reader returned a non-object")
        if result.get("schema_version") != "aoa_stats_packet_read_result_v1":
            raise StatsAccessError("aoa-stats public packet reader returned an unknown contract")
        return result
