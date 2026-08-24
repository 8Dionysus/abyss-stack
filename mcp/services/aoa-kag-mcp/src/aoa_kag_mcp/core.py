from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
PROVIDER_MAP_RELATIVE_PATH = Path("generated/local_kag_provider_map.min.json")
READINESS_RELATIVE_PATH = Path("manifests/local_kag_readiness.json")
REPO_LOCAL_COVERAGE_RELATIVE_PATH = Path("generated/repo_local_kag_coverage.min.json")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"KAG payload is not a JSON object: {path}")
    return payload


def _objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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
    """Locate aoa-kag contracts and repository-owned canonical KAG homes."""

    workspace_root: Path
    aoa_kag_root: Path
    artifact_root: Path | None
    canonical_provider_root: Path | None
    provider_map_path: Path
    readiness_path: Path
    coverage_path: Path

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        aoa_kag_root: str | Path | None = None,
        artifact_root: str | Path | None = None,
        canonical_provider_root: str | Path | None = None,
        provider_map_path: str | Path | None = None,
        readiness_path: str | Path | None = None,
        coverage_path: str | Path | None = None,
    ) -> "AoAKagMCPState":
        workspace = (
            Path(
                workspace_root
                or os.environ.get("AOA_WORKSPACE_ROOT")
                or DEFAULT_WORKSPACE_ROOT
            )
            .expanduser()
            .resolve()
        )
        kag_root = Path(
            aoa_kag_root or os.environ.get("AOA_KAG_ROOT") or workspace / "aoa-kag"
        ).expanduser()
        if not kag_root.is_absolute():
            kag_root = workspace / kag_root

        artifact_root_value = artifact_root or os.environ.get("AOA_KAG_ARTIFACT_ROOT")
        if artifact_root_value:
            configured_artifact_root = Path(artifact_root_value).expanduser()
            if not configured_artifact_root.is_absolute():
                raise ValueError("AOA_KAG_ARTIFACT_ROOT must be an absolute path")
            configured_artifact_root = configured_artifact_root.resolve()
        else:
            configured_artifact_root = None

        canonical_root_value = canonical_provider_root or os.environ.get(
            "AOA_KAG_CANONICAL_PROVIDER_ROOT"
        )
        if canonical_root_value:
            canonical_root = Path(canonical_root_value).expanduser()
            if not canonical_root.is_absolute():
                canonical_root = kag_root / canonical_root
            canonical_root = canonical_root.resolve()
        else:
            default_canonical_root = (kag_root / ".deps").resolve()
            canonical_root = (
                default_canonical_root if default_canonical_root.is_dir() else None
            )

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
            artifact_root=configured_artifact_root,
            canonical_provider_root=canonical_root,
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

    def providers(self) -> list[dict[str, Any]]:
        return _objects(self.provider_map().get("providers"))

    def provider(self, repo: str) -> dict[str, Any] | None:
        return next(
            (item for item in self.providers() if item.get("repo") == repo),
            None,
        )

    def repo_local_index(self, repo: str) -> dict[str, Any] | None:
        provider = self.provider(repo)
        if provider is None:
            raise KeyError(f"unknown KAG owner: {repo}")
        packet = provider.get("repo_local_index")
        if isinstance(packet, dict):
            return packet
        indexes = self.provider_map().get("provider_repo_local_indexes")
        fallback = indexes.get(repo) if isinstance(indexes, dict) else None
        return fallback if isinstance(fallback, dict) else None

    def _rooted_surfaces(self) -> list[dict[str, Any]]:
        surfaces: list[dict[str, Any]] = []
        if self.readiness_exists():
            surfaces.extend(_objects(self.readiness().get("os_surfaces")))
        surfaces.extend(_objects(self.provider_map().get("os_surfaces")))
        return surfaces

    def provider_root(self, repo: str) -> Path:
        if self.provider(repo) is None:
            raise KeyError(f"unknown KAG owner: {repo}")
        if repo == "aoa-kag":
            return self.aoa_kag_root

        if self.canonical_provider_root is not None:
            canonical_root = _provider_child_path(self.canonical_provider_root, repo)
            if canonical_root.is_dir():
                return canonical_root

        for surface in self._rooted_surfaces():
            if surface.get("provider_status") != "provider_ready":
                continue
            owner_return = surface.get("owner_return_route")
            owner_repo = (
                owner_return.get("repo") if isinstance(owner_return, dict) else None
            )
            surface_id = str(surface.get("surface_id") or "")
            if owner_repo != repo and surface_id not in {
                repo,
                f"connectors/{repo}",
                f"bundles/{repo}",
            }:
                continue
            raw_root = surface.get("root")
            if not raw_root:
                continue
            root = Path(str(raw_root)).expanduser()
            if not root.is_absolute():
                root = self.workspace_root / root
            return root.resolve()

        return (self.workspace_root / repo).resolve()

    def source_index_path(self, repo: str) -> Path | None:
        packet = self.repo_local_index(repo)
        ref = (
            str(packet.get("source_index_ref") or "")
            if isinstance(packet, dict)
            else ""
        )
        if not ref:
            return None
        return _provider_child_path(self.provider_root(repo), ref)

    def canonical_family_path(self, repo: str) -> Path | None:
        source_index = self.source_index_path(repo)
        if source_index is not None and source_index.is_file():
            return source_index

        packet = self.repo_local_index(repo)
        portable_family = (
            packet.get("portable_family")
            if isinstance(packet, dict)
            else None
        )
        manifest_ref = (
            str(portable_family.get("manifest_ref") or "")
            if (
                isinstance(packet, dict)
                and packet.get("family_storage") == "v3-portable-shards"
                and isinstance(portable_family, dict)
            )
            else ""
        )
        if manifest_ref:
            return _provider_child_path(self.provider_root(repo), manifest_ref)
        return source_index

    def provider_manifest(self, repo: str) -> dict[str, Any] | None:
        provider = self.provider(repo)
        if provider is None:
            raise KeyError(f"unknown KAG owner: {repo}")
        ref = str(provider.get("manifest_ref") or "kag/manifest.json")
        path = _provider_child_path(self.provider_root(repo), ref)
        return _read_json(path) if path.is_file() else None
