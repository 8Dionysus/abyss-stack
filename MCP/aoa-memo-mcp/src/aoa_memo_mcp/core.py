from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

REQUIRED_PORT_DIRS = ("candidates", "receipts", "exports", "local")
TEXT_SUFFIXES = {".md", ".json", ".txt", ".toml", ".yaml", ".yml"}
DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_ABYSS_STACK_SOURCE = Path.home() / "src" / "abyss-stack"
DEFAULT_ABYSS_MACHINE_PORT = Path("/var/lib/abyss-machine/memo")
DEFAULT_ABYSS_MACHINE_POLICY = Path("/etc/abyss-machine")

MEMORY_CONTRACTS = [
    "docs/memory/MEMORY_OPERATION_CYCLE.md",
    "docs/memory/LIVING_MEMORY_TOPOLOGY.md",
    "docs/memory/LOCAL_MEMO_PORT_STANDARD.md",
    "docs/boundaries/MEMORY_WRITE_PATH_GUARDRAILS.md",
    "docs/posture/MEMORY_OPERATION_MODES.md",
    "mechanics/retention/docs/CONSOLIDATION_FORGETTING_OPERATION.md",
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(text: str, limit: int = 48) -> str:
    lowered = text.lower()
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", lowered, flags=re.IGNORECASE).strip("-")
    return (slug or "candidate")[:limit].strip("-") or "candidate"


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


@dataclass(slots=True)
class RepoRoute:
    name: str
    source_root: Path | None
    memo_port: Path | None
    default_mode: str
    owner_note: str


@dataclass(slots=True)
class AoAMemoMCPState:
    workspace_root: Path

    @classmethod
    def discover(cls, workspace_root: str | Path | None = None) -> "AoAMemoMCPState":
        root = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or DEFAULT_WORKSPACE_ROOT
        ).expanduser().resolve()
        return cls(workspace_root=root)

    @property
    def aoa_memo_root(self) -> Path:
        return self.workspace_root / "aoa-memo"

    @property
    def aoa_archive_root(self) -> Path:
        return self.workspace_root / ".aoa"

    def repo_route(self, repo: str) -> RepoRoute:
        normalized = self._normalize_repo(repo)
        if normalized == "abyss-stack":
            source = Path(os.environ.get("AOA_ABYSS_STACK_ROOT", DEFAULT_ABYSS_STACK_SOURCE)).expanduser()
            if not source.exists():
                source = self.workspace_root / "abyss-stack"
            return RepoRoute(
                name="abyss-stack",
                source_root=source.resolve() if source.exists() else None,
                memo_port=(source / "memo").resolve() if source.exists() else None,
                default_mode="write_candidate_only",
                owner_note="runtime substrate source checkout; runtime mirror is not the source repo",
            )
        if normalized == "abyss-machine":
            policy_path = Path(
                os.environ.get("AOA_ABYSS_MACHINE_POLICY_ROOT", str(DEFAULT_ABYSS_MACHINE_POLICY))
            ).expanduser()
            memo_port = Path(
                os.environ.get("AOA_ABYSS_MACHINE_MEMO_ROOT", str(DEFAULT_ABYSS_MACHINE_PORT))
            ).expanduser()
            policy = policy_path if policy_path.exists() else None
            return RepoRoute(
                name="abyss-machine",
                source_root=policy,
                memo_port=memo_port,
                default_mode="write_candidate_only",
                owner_note="host-local memory port; policy remains under /etc/abyss-machine",
            )
        source = self.workspace_root / normalized
        return RepoRoute(
            name=normalized,
            source_root=source.resolve() if source.exists() else None,
            memo_port=(source / "memo").resolve() if source.exists() else None,
            default_mode="write_candidate_only",
            owner_note="repo-local memory candidate port",
        )

    def build_brief(self, repo: str, intent: str = "") -> dict[str, Any]:
        route = self.repo_route(repo)
        port = self.build_local_port_status(repo)
        return {
            "schema": "aoa_memo_brief_v1",
            "repo": route.name,
            "intent": intent,
            "operation_mode": route.default_mode,
            "owner_note": route.owner_note,
            "source_hierarchy": [
                "current repository evidence",
                "repo-local memo port candidates and receipts",
                "aoa-memo reviewed memory contracts",
                ".aoa raw session archive evidence",
                "derived MCP brief/search output",
            ],
            "local_port": port,
            "central_memory_contracts": self._central_contracts(),
            "recommended_route": self._recommended_route(port),
            "validation": [
                "python MCP/aoa-memo-mcp/scripts/validate_memo_mcp.py",
                "python -m pytest MCP/aoa-memo-mcp/tests -q",
                "python /srv/AbyssOS/aoa-memo/scripts/memory/validate_memory_operations.py",
            ],
        }

    def build_local_port_status(self, repo: str) -> dict[str, Any]:
        route = self.repo_route(repo)
        port = route.memo_port
        required = []
        if port is not None:
            required = [
                {"path": name, "exists": (port / name).is_dir()}
                for name in REQUIRED_PORT_DIRS
            ]
        return {
            "schema": "aoa_local_memo_port_status_v1",
            "repo": route.name,
            "source_root": str(route.source_root) if route.source_root else None,
            "memo_port": str(port) if port else None,
            "present": bool(port and port.exists()),
            "agents_card": str(port / "AGENTS.md") if port else None,
            "agents_card_exists": bool(port and (port / "AGENTS.md").exists()),
            "readme_exists": bool(port and (port / "README.md").exists()),
            "required_dirs": required,
            "ready": bool(
                port
                and (port / "AGENTS.md").exists()
                and (port / "README.md").exists()
                and all((port / name).is_dir() for name in REQUIRED_PORT_DIRS)
            ),
            "default_mode": route.default_mode,
        }

    def create_candidate(
        self,
        repo: str,
        evidence_refs: list[str],
        claim: str,
        *,
        source_trust: str = "review_required",
        desired_route: str = "reviewed_intake",
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        candidates_dir = route.memo_port / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        nonce = uuid4().hex[:8]
        candidate_id = f"candidate:{route.name}:{stamp}:{nonce}:{_slug(claim, 32)}"
        path = candidates_dir / f"{stamp}.{nonce}.{_slug(claim)}.candidate.json"
        payload = {
            "schema": "aoa_memo_candidate_v1",
            "candidate_id": candidate_id,
            "repo": route.name,
            "claim": claim,
            "evidence_refs": evidence_refs,
            "source_trust": source_trust,
            "desired_route": desired_route,
            "operation_mode": route.default_mode,
            "review_status": "candidate",
            "created_at": _now(),
            "guardrails": {
                "direct_durable_write": False,
                "requires_reviewed_intake": True,
            },
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = self.validate_candidate(path)
        return {"path": str(path), "candidate": payload, "validation": validation}

    def validate_candidate(self, path: str | Path) -> dict[str, Any]:
        candidate_path = Path(path).expanduser().resolve()
        data = _read_json(candidate_path)
        errors: list[str] = []
        if not isinstance(data, dict):
            return {"ok": False, "path": str(candidate_path), "errors": ["candidate is not valid JSON object"]}
        for key in ("schema", "candidate_id", "repo", "claim", "evidence_refs", "source_trust", "desired_route"):
            if key not in data:
                errors.append(f"missing required field: {key}")
        if not data.get("claim"):
            errors.append("claim must be non-empty")
        if not isinstance(data.get("evidence_refs"), list) or not data.get("evidence_refs"):
            errors.append("evidence_refs must be a non-empty list")
        source_trust = data.get("source_trust")
        desired_route = data.get("desired_route")
        direct_write = bool((data.get("guardrails") or {}).get("direct_durable_write"))
        if direct_write:
            errors.append("candidate may not request direct durable memory write")
        if desired_route == "durable_memory" and source_trust != "reviewed_owner_source":
            errors.append("unreviewed or untrusted candidates cannot validate as durable_memory")
        if desired_route == "durable_memory" and data.get("review_status") != "reviewed":
            errors.append("durable_memory route requires review_status=reviewed")
        return {
            "ok": not errors,
            "path": str(candidate_path),
            "repo": data.get("repo"),
            "candidate_id": data.get("candidate_id"),
            "errors": errors,
        }

    def search(self, query: str, scope: str = "all", mode: str = "brief", limit: int = 20) -> dict[str, Any]:
        needle = query.lower().strip()
        roots = self._search_roots(scope)
        hits: list[dict[str, Any]] = []
        if not needle:
            return {"query": query, "scope": scope, "mode": mode, "hits": hits}
        for root in roots:
            if not root.exists():
                continue
            for path in self._iter_search_files(root):
                text = path.read_text(encoding="utf-8", errors="ignore")
                idx = text.lower().find(needle)
                if idx == -1:
                    continue
                start = max(0, idx - 120)
                end = min(len(text), idx + len(needle) + 120)
                hits.append(
                    {
                        "path": str(path),
                        "root": str(root),
                        "snippet": text[start:end].replace("\n", " "),
                    }
                )
                if len(hits) >= limit:
                    return {"query": query, "scope": scope, "mode": mode, "hits": hits}
        return {"query": query, "scope": scope, "mode": mode, "hits": hits}

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-memo":
            raise ValueError(f"unsupported resource scheme: {parsed.scheme}")
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc == "brief" and path_parts[:1] == ["repo"] and len(path_parts) == 2:
            return self.build_brief(path_parts[1])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "local-port-status":
            return self.build_local_port_status(path_parts[0])
        if parsed.netloc == "memory" and path_parts[:1] == ["object"] and len(path_parts) == 2:
            return self.build_memory_object(path_parts[1])
        if parsed.netloc == "session" and len(path_parts) == 2 and path_parts[1] == "rehydrate":
            return self.build_session_rehydrate(path_parts[0])
        raise ValueError(f"unsupported aoa-memo resource URI: {uri}")

    def build_memory_object(self, object_id: str) -> dict[str, Any]:
        registry_path = self.aoa_memo_root / "generated/memory/memo_registry.min.json"
        registry = _read_json(registry_path)
        matches: list[dict[str, Any]] = []
        if isinstance(registry, dict):
            for key in ("memory_object_kinds", "supporting_objects", "recall_modes", "core_docs", "schemas"):
                value = registry.get(key)
                if isinstance(value, list):
                    for item in value:
                        if object_id in str(item):
                            matches.append({"registry_key": key, "value": item})
        return {
            "schema": "aoa_memo_object_lookup_v1",
            "object_id": object_id,
            "registry": str(registry_path),
            "found": bool(matches),
            "matches": matches,
        }

    def build_session_rehydrate(self, session_id: str) -> dict[str, Any]:
        registry_path = self.aoa_archive_root / "session-registry.json"
        registry = _read_json(registry_path)
        session = None
        if isinstance(registry, dict):
            for item in registry.get("sessions", []):
                if not isinstance(item, dict):
                    continue
                label = (item.get("display") or {}).get("label")
                if item.get("session_id") == session_id or label == session_id:
                    session = item
                    break
        if not session:
            return {
                "schema": "aoa_session_rehydrate_pointer_v1",
                "session_id": session_id,
                "found": False,
                "registry": str(registry_path),
            }
        display = session.get("display") or {}
        path = Path(display.get("path") or display.get("archive_path") or "")
        return {
            "schema": "aoa_session_rehydrate_pointer_v1",
            "session_id": session.get("session_id"),
            "label": display.get("label"),
            "found": True,
            "session_path": str(path),
            "agents": str(path / "AGENTS.md"),
            "session_md": str(path / "SESSION.md"),
            "manifest": str(path / "session.manifest.json"),
            "index": str(path / "session.index.json"),
        }

    def _central_contracts(self) -> list[dict[str, Any]]:
        return [
            {
                "path": rel,
                "abs_path": str(self.aoa_memo_root / rel),
                "exists": (self.aoa_memo_root / rel).exists(),
            }
            for rel in MEMORY_CONTRACTS
        ]

    def _recommended_route(self, port: dict[str, Any]) -> list[str]:
        if not port["ready"]:
            return ["read central contracts", "create or repair local memo port", "write no durable memory"]
        return [
            "read local memo/AGENTS.md",
            "create local candidate under memo/candidates",
            "validate candidate through aoa_memo_validate_candidate",
            "export reviewed intake packet for aoa-memo",
            "let aoa-memo decide promote, supersede, retract, archive, or keep local",
        ]

    def _search_roots(self, scope: str) -> list[Path]:
        roots: list[Path] = []
        if scope in ("all", "central", "aoa-memo"):
            roots.extend([self.aoa_memo_root / "docs", self.aoa_memo_root / "mechanics", self.aoa_memo_root / "generated/memory"])
        if scope in ("all", "local", "ports"):
            for repo in ("Agents-of-Abyss", "abyss-stack", "abyss-machine"):
                port = self.repo_route(repo).memo_port
                if port is not None:
                    roots.append(port)
        if scope in ("all", "session", ".aoa"):
            roots.extend([self.aoa_archive_root / "SESSION_NAMES.md", self.aoa_archive_root / "sessions/INDEX.md", self.aoa_archive_root / "session-registry.json"])
        return roots

    def _iter_search_files(self, root: Path):
        if root.is_file() and root.suffix in TEXT_SUFFIXES:
            yield root
            return
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            if any(part in {".git", "__pycache__", "raw"} for part in path.parts):
                continue
            if path.suffix in TEXT_SUFFIXES:
                yield path

    def _normalize_repo(self, repo: str) -> str:
        aliases = {
            "agents": "Agents-of-Abyss",
            "agents-of-abyss": "Agents-of-Abyss",
            "aoa": "Agents-of-Abyss",
            "stack": "abyss-stack",
            "machine": "abyss-machine",
        }
        return aliases.get(repo, repo)
