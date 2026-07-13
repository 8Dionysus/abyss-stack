from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_AOA_KAG_ROOT = DEFAULT_WORKSPACE_ROOT / "aoa-kag"
PROVIDER_MAP_RELATIVE_PATH = Path("generated/local_kag_provider_map.min.json")
READINESS_RELATIVE_PATH = Path("manifests/local_kag_readiness.json")
REPO_LOCAL_COVERAGE_RELATIVE_PATH = Path("generated/repo_local_kag_coverage.min.json")
REPOSITORY_INDEX_KINDS = (
    "source",
    "entity",
    "artifact",
    "anchor",
    "event",
    "assertion",
    "relation",
)
RECORD_CLASS_DIRECTORIES = {
    "node": "nodes",
    "edge": "edges",
    "index": "indexes",
    "projection": "projections",
    "receipt": "receipts",
}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"KAG payload is not a JSON object: {path}")
    return payload


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value.lower()
    if isinstance(value, dict):
        return any(_contains(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _provider_child_path(root: Path, ref: str) -> Path:
    root_resolved = root.resolve(strict=False)
    ref_path = Path(ref).expanduser()
    candidate = ref_path if ref_path.is_absolute() else root_resolved / ref_path
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"provider path escapes provider root: {ref}") from exc
    return resolved


@dataclass(slots=True)
class AoAKagMCPState:
    workspace_root: Path
    aoa_kag_root: Path
    provider_map_path: Path
    readiness_path: Path
    coverage_path: Path

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        aoa_kag_root: str | Path | None = None,
        provider_map_path: str | Path | None = None,
        readiness_path: str | Path | None = None,
        coverage_path: str | Path | None = None,
    ) -> "AoAKagMCPState":
        workspace = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or DEFAULT_WORKSPACE_ROOT
        ).expanduser().resolve()
        kag_root = Path(
            aoa_kag_root
            or os.environ.get("AOA_KAG_ROOT")
            or workspace / "aoa-kag"
            or DEFAULT_AOA_KAG_ROOT
        ).expanduser()
        if not kag_root.is_absolute():
            kag_root = workspace / kag_root
        provider_map = Path(
            provider_map_path
            or os.environ.get("AOA_KAG_PROVIDER_MAP_PATH")
            or kag_root / PROVIDER_MAP_RELATIVE_PATH
        ).expanduser()
        if not provider_map.is_absolute():
            provider_map = kag_root / provider_map
        readiness = Path(
            readiness_path
            or os.environ.get("AOA_KAG_READINESS_PATH")
            or kag_root / READINESS_RELATIVE_PATH
        ).expanduser()
        if not readiness.is_absolute():
            readiness = kag_root / readiness
        coverage = Path(
            coverage_path
            or os.environ.get("AOA_KAG_COVERAGE_PATH")
            or kag_root / REPO_LOCAL_COVERAGE_RELATIVE_PATH
        ).expanduser()
        if not coverage.is_absolute():
            coverage = kag_root / coverage
        return cls(
            workspace_root=workspace,
            aoa_kag_root=kag_root.resolve(),
            provider_map_path=provider_map.resolve(),
            readiness_path=readiness.resolve(),
            coverage_path=coverage.resolve(),
        )

    def provider_map_exists(self) -> bool:
        return self.provider_map_path.is_file()

    def readiness_exists(self) -> bool:
        return self.readiness_path.is_file()

    def coverage_exists(self) -> bool:
        return self.coverage_path.is_file()

    def provider_map(self) -> dict[str, Any]:
        return _read_json(self.provider_map_path)

    def readiness(self) -> dict[str, Any]:
        return _read_json(self.readiness_path)

    def coverage(self) -> dict[str, Any]:
        return _read_json(self.coverage_path)

    def _providers(self) -> list[dict[str, Any]]:
        return [item for item in self.provider_map().get("providers", []) if isinstance(item, dict)]

    def _remaining_routes(self) -> list[dict[str, Any]]:
        return [item for item in self.provider_map().get("remaining_routes", []) if isinstance(item, dict)]

    def _os_surfaces(self) -> list[dict[str, Any]]:
        return [item for item in self.provider_map().get("os_surfaces", []) if isinstance(item, dict)]

    def _provider_common_surface_profiles(self) -> dict[str, dict[str, Any]]:
        value = self.provider_map().get("provider_common_surface_profiles")
        if not isinstance(value, dict):
            return {}
        return {str(repo): packet for repo, packet in value.items() if isinstance(packet, dict)}

    def _readiness_os_surfaces(self) -> list[dict[str, Any]]:
        if not self.readiness_exists():
            return []
        return [item for item in self.readiness().get("os_surfaces", []) if isinstance(item, dict)]

    def _rooted_os_surfaces(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for surface in [*self._readiness_os_surfaces(), *self._os_surfaces()]:
            root = str(surface.get("root") or "")
            surface_id = str(surface.get("surface_id") or "")
            key = (surface_id, root)
            if not root or key in seen:
                continue
            seen.add(key)
            rows.append(surface)
        return rows

    def _provider(self, repo: str) -> dict[str, Any] | None:
        return next((item for item in self._providers() if item.get("repo") == repo), None)

    def _remaining_route(self, repo: str) -> dict[str, Any] | None:
        return next((item for item in self._remaining_routes() if item.get("repo") == repo), None)

    def _provider_root_from_os_surfaces(self, repo: str) -> Path | None:
        for surface in self._rooted_os_surfaces():
            owner_return = surface.get("owner_return_route")
            owner_repo = owner_return.get("repo") if isinstance(owner_return, dict) else None
            surface_id = str(surface.get("surface_id") or "")
            provider_ready = surface.get("provider_status") == "provider_ready"
            owner_provider_match = provider_ready and owner_repo == repo
            surface_match = provider_ready and (surface_id == repo or surface_id.endswith(f"/{repo}"))
            if not owner_provider_match and not surface_match:
                continue
            root = Path(str(surface.get("root"))).expanduser()
            if not root.is_absolute():
                root = self.workspace_root / root
            return root.resolve()
        return None

    def _provider_root(self, repo: str) -> Path:
        if repo == "aoa-kag":
            return self.aoa_kag_root
        surface_root = self._provider_root_from_os_surfaces(repo)
        if surface_root is not None:
            return surface_root
        return self.workspace_root / repo

    def _provider_generation_profile(self, repo: str) -> dict[str, Any] | None:
        profiles = self.provider_map().get("provider_generation_profiles", {})
        if isinstance(profiles, dict) and isinstance(profiles.get(repo), dict):
            return profiles[repo]
        provider = self._provider(repo)
        if provider is None:
            return None
        profile = provider.get("generation_profile")
        return profile if isinstance(profile, dict) else None

    def _provider_repo_local_index(self, repo: str) -> dict[str, Any] | None:
        indexes = self.provider_map().get("provider_repo_local_indexes", {})
        if isinstance(indexes, dict) and isinstance(indexes.get(repo), dict):
            return indexes[repo]
        provider = self._provider(repo)
        if provider is None:
            return None
        index = provider.get("repo_local_index")
        return index if isinstance(index, dict) else None

    def _common_surface_profile(self, repo: str) -> dict[str, Any] | None:
        packet = self._provider_common_surface_profiles().get(repo)
        if packet is not None:
            return packet
        repo_local_index = self._provider_repo_local_index(repo)
        value = repo_local_index.get("common_surface_profile") if isinstance(repo_local_index, dict) else None
        return value if isinstance(value, dict) else None

    def _source_index_summary(self, path: Path) -> dict[str, Any]:
        payload = _read_json(path)
        records = payload.get("records", [])
        return {
            "schema_version": payload.get("schema_version"),
            "repo": payload.get("repo"),
            "index_identity": payload.get("index_identity", {}),
            "coverage_summary": payload.get("coverage_summary", {}),
            "classification_summary": payload.get("classification_summary", {}),
            "record_count": len(records) if isinstance(records, list) else None,
        }

    def _repository_index_summary(self, path: Path) -> dict[str, Any]:
        payload = _read_json(path)
        entries = payload.get("entries")
        if not isinstance(entries, list):
            entries = payload.get("records")
        return {
            "schema_version": payload.get("schema_version"),
            "repo": payload.get("repo"),
            "index_identity": payload.get("index_identity", {}),
            "source_index": payload.get("source_index", {}),
            "summary": payload.get("summary", {}),
            "coverage_summary": payload.get("coverage_summary", {}),
            "entry_count": len(entries) if isinstance(entries, list) else None,
        }

    def _domain_index_catalog_summary(self, path: Path) -> dict[str, Any]:
        payload = _read_json(path)
        entries = payload.get("entries")
        return {
            "schema_version": payload.get("schema_version"),
            "repo": payload.get("repo"),
            "catalog_identity": payload.get("catalog_identity", {}),
            "entry_count": len(entries) if isinstance(entries, list) else None,
            "owner_return_route": payload.get("owner_return_route"),
            "consumer_routes": payload.get("consumer_routes", []),
        }

    def status(self) -> dict[str, Any]:
        payload = self.provider_map() if self.provider_map_exists() else {}
        providers = payload.get("providers", []) if isinstance(payload.get("providers"), list) else []
        remaining = payload.get("remaining_routes", []) if isinstance(payload.get("remaining_routes"), list) else []
        provider_map_os_surfaces = payload.get("os_surfaces", []) if isinstance(payload.get("os_surfaces"), list) else []
        os_surfaces = self._readiness_os_surfaces() or provider_map_os_surfaces
        return {
            "schema": "aoa_kag_mcp_status_v1",
            "provider_map_exists": self.provider_map_exists(),
            "readiness_exists": self.readiness_exists(),
            "coverage_exists": self.coverage_exists(),
            "workspace_root": self.workspace_root.as_posix(),
            "aoa_kag_root": self.aoa_kag_root.as_posix(),
            "provider_map_path": self.provider_map_path.as_posix(),
            "readiness_path": self.readiness_path.as_posix(),
            "coverage_path": self.coverage_path.as_posix(),
            "provider_status_counts": payload.get("provider_status_counts", {}),
            "provider_count": len(providers),
            "remaining_route_count": len(remaining),
            "os_surface_count": len(os_surfaces),
            "service_route": payload.get("mcp_handoff", {}).get("service_route") if isinstance(payload.get("mcp_handoff"), dict) else None,
            "authority_boundary": "aoa-kag owns KAG provider map and validation; abyss-stack owns this MCP access plane.",
        }

    def provider_lookup(self, repo: str) -> dict[str, Any]:
        provider = self._provider(repo)
        if provider is not None:
            return {
                "schema": "aoa_kag_provider_lookup_v1",
                "repo": repo,
                "kind": "provider",
                "status": provider.get("provider_status", "provider_ready"),
                "provider": provider,
                "repo_local_index": self._provider_repo_local_index(repo),
                "common_surface_profile": self._common_surface_profile(repo),
                "provider_root": self._provider_root(repo).as_posix(),
                "authority_note": "Provider records route back to the repo-local kag/ home and source-return surfaces.",
            }
        remaining = self._remaining_route(repo)
        if remaining is not None:
            return {
                "schema": "aoa_kag_provider_lookup_v1",
                "repo": repo,
                "kind": "remaining_route",
                "status": remaining.get("provider_status"),
                "remaining_route": remaining,
                "authority_note": "Remaining routes are explicit topology rows, not provider records.",
            }
        return {
            "schema": "aoa_kag_provider_lookup_v1",
            "repo": repo,
            "kind": "missing",
            "status": "missing",
            "authority_note": "Unknown repo in aoa-kag provider map.",
        }

    def provider_status(self, repo: str | None = None) -> dict[str, Any]:
        if repo:
            return self.provider_lookup(repo)
        return {
            "schema": "aoa_kag_provider_status_v1",
            "status": self.status(),
            "providers": [
                {
                    "repo": item.get("repo"),
                    "provider_status": item.get("provider_status", "provider_ready"),
                    "record_counts": item.get("record_counts", {}),
                    "repo_local_index": self._provider_repo_local_index(str(item.get("repo"))),
                    "common_surface_profile": self._common_surface_profile(str(item.get("repo"))),
                    "owner_return_routes": item.get("owner_return_routes", []),
                    "mcp_access_shape": item.get("mcp_access_shape", []),
                }
                for item in self._providers()
            ],
            "remaining_routes": self._remaining_routes(),
        }

    def freshness_check(self, repo: str | None = None) -> dict[str, Any]:
        providers = [self._provider(repo)] if repo else self._providers()
        rows: list[dict[str, Any]] = []
        missing_handles: list[str] = []
        missing_receipts: list[str] = []
        for provider in providers:
            if not isinstance(provider, dict):
                if repo:
                    missing_handles.append(repo)
                continue
            provider_repo = str(provider.get("repo"))
            root = self._provider_root(provider_repo)
            for handle in provider.get("freshness_handles", []):
                if not isinstance(handle, dict):
                    missing_handles.append(f"{provider_repo}:invalid-handle")
                    continue
                receipt_ref = str(handle.get("receipt_ref", ""))
                receipt_path = root / receipt_ref
                receipt_exists = bool(receipt_ref) and receipt_path.is_file()
                rows.append(
                    {
                        "repo": provider_repo,
                        "receipt_ref": receipt_ref,
                        "provider_root_exists": root.is_dir(),
                        "receipt_exists": receipt_exists,
                        "checked_ref": handle.get("checked_ref"),
                        "state": handle.get("state"),
                        "validator": handle.get("validator"),
                        "owner_return_route": handle.get("owner_return_route"),
                    }
                )
                if not receipt_ref:
                    missing_handles.append(f"{provider_repo}:missing-receipt-ref")
                elif not receipt_exists:
                    missing_receipts.append(f"{provider_repo}:{receipt_ref}")
        return {
            "schema": "aoa_kag_freshness_check_v1",
            "repo": repo,
            "ok": not missing_handles and not missing_receipts,
            "missing": missing_handles,
            "missing_receipts": missing_receipts,
            "freshness": rows,
            "authority_boundary": "Freshness handles point to provider receipts and owner validators; MCP reports local receipt materialization without running validators as a hidden side effect.",
        }

    def repo_local_index(self, repo: str) -> dict[str, Any]:
        packet = self._provider_repo_local_index(repo)
        if packet is None:
            raise KeyError(f"unknown KAG provider repo-local index: {repo}")
        return {
            "schema": "aoa_kag_repo_local_index_resource_v1",
            "repo": repo,
            "repo_local_index": packet,
            "authority_note": "Repo-local index status is read from the aoa-kag generated provider map.",
        }

    def common_surface_profile(self, repo: str) -> dict[str, Any]:
        profile = self._common_surface_profile(repo)
        if profile is None:
            raise KeyError(f"unknown KAG provider common surface profile: {repo}")
        return {
            "schema": "aoa_kag_common_surface_profile_resource_v1",
            "repo": repo,
            "common_surface_profile": profile,
            "authority_note": "Common surface profiles summarize source-surface classes; source meaning remains with provider owners.",
        }

    def generation_route_lookup(self, repo: str) -> dict[str, Any]:
        profile = self._provider_generation_profile(repo)
        provider = self._provider(repo)
        if profile is None:
            return {
                "schema": "aoa_kag_generation_route_lookup_v1",
                "repo": repo,
                "status": "missing",
                "lookup": self.provider_lookup(repo),
                "authority_note": "Generation routes are read from the aoa-kag provider map.",
            }
        return {
            "schema": "aoa_kag_generation_route_lookup_v1",
            "repo": repo,
            "status": "available",
            "provider_status": provider.get("provider_status") if provider else None,
            "generation_profile": profile,
            "builder_routes": profile.get("builder_routes", []),
            "source_home_surfaces": profile.get("source_home_surfaces", []),
            "candidate_source_surfaces": profile.get("candidate_source_surfaces", []),
            "source_owned_exports": profile.get("source_owned_exports", []),
            "graph_entities": profile.get("graph_entities", []),
            "event_surfaces": profile.get("event_surfaces", []),
            "document_surfaces": profile.get("document_surfaces", []),
            "validators": profile.get("validators", []),
            "release_gate": profile.get("release_gate"),
            "runtime_consumers": profile.get("runtime_consumers", []),
            "owner_return_routes": provider.get("owner_return_routes", []) if provider else [],
            "authority_note": "Generation routes describe source-owned KAG production and return paths.",
        }

    def source_index_lookup(self, repo: str, *, include_payload: bool = False) -> dict[str, Any]:
        repo_index = self._provider_repo_local_index(repo)
        provider = self._provider(repo)
        if repo_index is None:
            return {
                "schema": "aoa_kag_source_index_lookup_v1",
                "repo": repo,
                "status": "missing",
                "lookup": self.provider_lookup(repo),
                "authority_note": "Repo-local source indexes are read from the aoa-kag provider map.",
            }
        source_index_ref = str(repo_index.get("source_index_ref") or "")
        provider_root = self._provider_root(repo)
        source_index_path = _provider_child_path(provider_root, source_index_ref) if source_index_ref else None
        source_index_exists = bool(source_index_path and source_index_path.is_file())
        source_index_summary = (
            self._source_index_summary(source_index_path)
            if source_index_path is not None and source_index_path.is_file()
            else {}
        )
        source_index_payload = (
            _read_json(source_index_path)
            if include_payload and source_index_path is not None and source_index_path.is_file()
            else None
        )
        return {
            "schema": "aoa_kag_source_index_lookup_v1",
            "repo": repo,
            "status": repo_index.get("status", "unknown"),
            "provider_status": provider.get("provider_status") if provider else None,
            "provider_root": provider_root.as_posix(),
            "repo_local_index": repo_index,
            "source_index_ref": source_index_ref,
            "source_index_path": source_index_path.as_posix() if source_index_path else None,
            "source_index_exists": source_index_exists,
            "source_index_summary": source_index_summary,
            "source_index": source_index_payload,
            "index_files": repo_index.get("index_files", []),
            "coverage": repo_index.get("coverage", {}),
            "common_surface_profile": self._common_surface_profile(repo),
            "coverage_report_ref": repo_index.get("coverage_report_ref"),
            "coverage_owner_key": repo_index.get("coverage_owner_key"),
            "authority_note": "Source index lookup returns compact metadata and owner-local file handles.",
        }

    def source_index_status(self, repo: str, *, include_payload: bool = False) -> dict[str, Any]:
        return self.source_index_lookup(repo, include_payload=include_payload)

    def repository_index_family_lookup(self, repo: str) -> dict[str, Any]:
        repo_index = self._provider_repo_local_index(repo)
        provider = self._provider(repo)
        if repo_index is None:
            return {
                "schema": "aoa_kag_repository_index_family_lookup_v1",
                "repo": repo,
                "status": "missing",
                "family_complete": False,
                "repository_index_family": {},
                "indexes": {},
                "lookup": self.provider_lookup(repo),
                "authority_note": "Repository index families are read from the aoa-kag provider map.",
            }
        raw_family = repo_index.get("repository_index_family")
        family = raw_family if isinstance(raw_family, dict) else {}
        provider_root = self._provider_root(repo)
        indexes: dict[str, dict[str, Any]] = {}
        for index_kind in REPOSITORY_INDEX_KINDS:
            index_ref = str(family.get(index_kind) or "")
            index_path = _provider_child_path(provider_root, index_ref) if index_ref else None
            indexes[index_kind] = {
                "ref": index_ref,
                "path": index_path.as_posix() if index_path else None,
                "exists": bool(index_path and index_path.is_file()),
            }
        return {
            "schema": "aoa_kag_repository_index_family_lookup_v1",
            "repo": repo,
            "status": repo_index.get("status", "unknown"),
            "provider_status": provider.get("provider_status") if provider else None,
            "provider_root": provider_root.as_posix(),
            "family_complete": all(index["ref"] and index["exists"] for index in indexes.values()),
            "repository_index_family": {
                index_kind: indexes[index_kind]["ref"] for index_kind in REPOSITORY_INDEX_KINDS
            },
            "indexes": indexes,
            "domain_index_catalog_ref": str(repo_index.get("domain_index_catalog_ref") or ""),
            "authority_note": "The family is a provider-owned projection of repository source with return handles to local index files.",
        }

    def repository_index_lookup(
        self,
        repo: str,
        index_kind: str,
        *,
        include_payload: bool = False,
    ) -> dict[str, Any]:
        if index_kind not in REPOSITORY_INDEX_KINDS:
            raise KeyError(f"unknown repository index kind: {index_kind}")
        repo_index = self._provider_repo_local_index(repo)
        provider = self._provider(repo)
        if repo_index is None:
            return {
                "schema": "aoa_kag_repository_index_lookup_v1",
                "repo": repo,
                "index_kind": index_kind,
                "status": "missing",
                "index_ref": "",
                "index_path": None,
                "index_exists": False,
                "index_summary": {},
                "index": None,
                "lookup": self.provider_lookup(repo),
            }
        raw_family = repo_index.get("repository_index_family")
        family = raw_family if isinstance(raw_family, dict) else {}
        index_ref = str(family.get(index_kind) or "")
        provider_root = self._provider_root(repo)
        index_path = _provider_child_path(provider_root, index_ref) if index_ref else None
        index_exists = bool(index_path and index_path.is_file())
        return {
            "schema": "aoa_kag_repository_index_lookup_v1",
            "repo": repo,
            "index_kind": index_kind,
            "status": "available" if index_ref else "not_published",
            "provider_index_status": repo_index.get("status", "unknown"),
            "provider_status": provider.get("provider_status") if provider else None,
            "provider_root": provider_root.as_posix(),
            "index_ref": index_ref,
            "index_path": index_path.as_posix() if index_path else None,
            "index_exists": index_exists,
            "index_summary": self._repository_index_summary(index_path) if index_exists and index_path else {},
            "index": _read_json(index_path) if include_payload and index_exists and index_path else None,
            "authority_note": "The returned index remains a derived read model owned by the provider repository.",
        }

    def domain_index_catalog_lookup(
        self,
        repo: str,
        *,
        include_payload: bool = False,
    ) -> dict[str, Any]:
        repo_index = self._provider_repo_local_index(repo)
        provider = self._provider(repo)
        if repo_index is None:
            return {
                "schema": "aoa_kag_domain_index_catalog_lookup_v1",
                "repo": repo,
                "status": "missing",
                "domain_index_catalog_ref": "",
                "catalog_path": None,
                "catalog_exists": False,
                "catalog_summary": {},
                "domain_index_catalog": None,
                "lookup": self.provider_lookup(repo),
            }
        catalog_ref = str(repo_index.get("domain_index_catalog_ref") or "")
        provider_root = self._provider_root(repo)
        catalog_path = _provider_child_path(provider_root, catalog_ref) if catalog_ref else None
        catalog_exists = bool(catalog_path and catalog_path.is_file())
        return {
            "schema": "aoa_kag_domain_index_catalog_lookup_v1",
            "repo": repo,
            "status": "available" if catalog_ref else "not_published",
            "provider_status": provider.get("provider_status") if provider else None,
            "provider_root": provider_root.as_posix(),
            "domain_index_catalog_ref": catalog_ref,
            "catalog_path": catalog_path.as_posix() if catalog_path else None,
            "catalog_exists": catalog_exists,
            "catalog_summary": self._domain_index_catalog_summary(catalog_path) if catalog_exists and catalog_path else {},
            "domain_index_catalog": _read_json(catalog_path) if include_payload and catalog_exists and catalog_path else None,
            "authority_note": "Domain index catalogs route to owner-native indexes while their data and semantics remain with that owner.",
        }

    def repo_local_coverage_status(
        self,
        repo: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if not self.coverage_exists():
            return {
                "schema": "aoa_kag_repo_local_coverage_status_v1",
                "coverage_exists": False,
                "coverage_path": self.coverage_path.as_posix(),
                "repo": repo,
                "status": status,
                "coverage_summary": {},
                "count": 0,
                "owners": [],
            }
        payload = self.coverage()
        owners = [item for item in payload.get("owners", []) if isinstance(item, dict)]
        if repo:
            owners = [item for item in owners if item.get("repo") == repo]
        if status:
            owners = [item for item in owners if item.get("index_status") == status]
        return {
            "schema": "aoa_kag_repo_local_coverage_status_v1",
            "coverage_exists": True,
            "coverage_path": self.coverage_path.as_posix(),
            "repo": repo,
            "status": status,
            "coverage_summary": payload.get("coverage_summary", {}),
            "count": len(owners),
            "owners": owners,
        }

    def source_return_lookup(
        self,
        repo: str,
        local_id: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        provider = self._provider(repo)
        if provider is None:
            return self.provider_lookup(repo)
        matches: list[dict[str, Any]] = []
        if local_id or path:
            root = self._provider_root(repo) / "kag"
            for group in RECORD_CLASS_DIRECTORIES.values():
                directory = root / group
                if not directory.is_dir():
                    continue
                for record_path in sorted(directory.glob("*.json")):
                    record = _read_json(record_path)
                    if local_id and record.get("local_id") != local_id:
                        continue
                    if path and path not in json.dumps(record, ensure_ascii=False):
                        continue
                    matches.append(
                        {
                            "record_ref": f"kag/{group}/{record_path.name}",
                            "local_id": record.get("local_id"),
                            "record_class": record.get("record_class"),
                            "owner_return_route": record.get("owner_return_route"),
                            "source_refs": record.get("source_refs", []),
                        }
                    )
        return {
            "schema": "aoa_kag_source_return_lookup_v1",
            "repo": repo,
            "owner_return_routes": provider.get("owner_return_routes", []),
            "matches": matches,
            "authority_note": "Use the returned owner surface before editing meaning.",
        }

    def registry_slice(
        self,
        status: str | None = None,
        repo: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for provider in self._providers():
            row = {"kind": "provider", **provider}
            items.append(row)
        for route in self._remaining_routes():
            row = {"kind": "remaining_route", **route}
            items.append(row)
        if repo:
            items = [item for item in items if item.get("repo") == repo]
        if status:
            items = [
                item
                for item in items
                if item.get("provider_status", "provider_ready") == status
            ]
        return {
            "schema": "aoa_kag_registry_slice_v1",
            "repo": repo,
            "status": status,
            "count": len(items[:limit]),
            "items": items[:limit],
        }

    def composition_slice(self, query: str = "", limit: int = 20) -> dict[str, Any]:
        needle = query.lower().strip()
        candidates: list[dict[str, Any]] = []
        for collection, rows in (
            ("providers", self._providers()),
            ("remaining_routes", self._remaining_routes()),
            ("os_surfaces", self._os_surfaces()),
        ):
            for row in rows:
                if needle and not _contains(row, needle):
                    continue
                candidates.append({"collection": collection, "item": row})
                if len(candidates) >= limit:
                    break
            if len(candidates) >= limit:
                break
        return {
            "schema": "aoa_kag_composition_slice_v1",
            "query": query,
            "count": len(candidates),
            "results": candidates,
            "authority_note": "Composition search reads generated provider map fields only.",
        }

    def validation_status(self, include_provider_homes: bool = False) -> dict[str, Any]:
        provider_rows = []
        if include_provider_homes:
            for provider in self._providers():
                repo = str(provider.get("repo"))
                root = self._provider_root(repo)
                provider_rows.append(
                    {
                        "repo": repo,
                        "root_exists": root.is_dir(),
                        "manifest_exists": (root / "kag" / "manifest.json").is_file(),
                        "freshness": self.freshness_check(repo=repo)["ok"],
                    }
                )
        return {
            "schema": "aoa_kag_validation_status_v1",
            "status": self.status(),
            "include_provider_homes": include_provider_homes,
            "provider_homes": provider_rows,
            "validation_route": "Run aoa-kag validators outside MCP for blocking validation.",
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-kag":
            raise KeyError(f"unknown aoa-kag MCP resource URI: {uri}")
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc == "registry" and parts == ["provider-map"]:
            return self.provider_map()
        if parsed.netloc == "readiness" and parts == ["os-surfaces"]:
            return {
                "schema": "aoa_kag_readiness_os_surfaces_resource_v1",
                "readiness_path": self.readiness_path.as_posix(),
                "os_surfaces": self.readiness().get("os_surfaces", []),
            }
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "manifest":
            repo = parts[0]
            provider = self._provider(repo)
            if provider is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return _read_json(self._provider_root(repo) / "kag" / "manifest.json")
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "generation":
            repo = parts[0]
            if self._provider(repo) is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return self.generation_route_lookup(repo)
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "source-index":
            repo = parts[0]
            if self._provider(repo) is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return self.source_index_lookup(repo, include_payload=True)
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "repo-local-index":
            return self.repo_local_index(parts[0])
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "common-surface-profile":
            return self.common_surface_profile(parts[0])
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "repository-index-family":
            repo = parts[0]
            if self._provider(repo) is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return self.repository_index_family_lookup(repo)
        if parsed.netloc == "providers" and len(parts) == 3 and parts[1] == "indexes":
            repo = parts[0]
            if self._provider(repo) is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return self.repository_index_lookup(repo, parts[2], include_payload=True)
        if parsed.netloc == "providers" and len(parts) == 2 and parts[1] == "domain-index-catalog":
            repo = parts[0]
            if self._provider(repo) is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            return self.domain_index_catalog_lookup(repo, include_payload=True)
        if parsed.netloc == "providers" and len(parts) == 3 and parts[1] == "records":
            repo = parts[0]
            record_class = parts[2]
            directory = RECORD_CLASS_DIRECTORIES.get(record_class)
            if directory is None:
                raise KeyError(f"unknown KAG record class: {record_class}")
            provider = self._provider(repo)
            if provider is None:
                raise KeyError(f"unknown KAG provider: {repo}")
            root = self._provider_root(repo) / "kag" / directory
            records = [_read_json(path) for path in sorted(root.glob("*.json"))]
            return {
                "schema": "aoa_kag_provider_records_resource_v1",
                "repo": repo,
                "record_class": record_class,
                "count": len(records),
                "records": records,
            }
        if parsed.netloc == "coverage" and parts == ["repo-local-source-indexes"]:
            return self.repo_local_coverage_status()
        raise KeyError(f"unknown aoa-kag MCP resource URI: {uri}")
