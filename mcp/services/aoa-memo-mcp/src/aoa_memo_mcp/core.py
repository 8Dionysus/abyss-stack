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

import yaml

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
CENTRAL_VOCABULARY = "config/memory-ports/indexing_vocabulary.json"
LOCAL_PORT_INDEX = "index.min.json"
LOCAL_PORT_INDEX_MD = "INDEX.md"
LOCAL_PORT_CONTRACT = "PORT.yaml"
OPEN_REVIEW_STATES = {"candidate", "validated", "forwarded", "reviewed"}
TERMINAL_REVIEW_STATES = {"rejected", "landed", "superseded", "archived"}
FALLBACK_VOCABULARY_TERMS = {
    "kind": {"decision", "route", "pattern", "lesson", "constraint", "incident", "preference", "checkpoint", "handoff"},
    "family": {"memory-access", "runtime", "topology", "validation", "release", "agent-behavior", "provenance", "kag-bridge", "session-recovery"},
    "scope": {"session", "repo", "workspace", "project", "ecosystem", "host", "agent"},
    "route": {"local_only", "reviewed_intake", "owner_handoff", "quarantine", "archive"},
    "review_state": {"candidate", "validated", "rejected", "forwarded", "reviewed", "landed", "superseded", "archived"},
    "lifecycle": {"captured", "candidate", "reviewed", "current", "superseded", "retracted", "archived", "frozen"},
    "source_trust": {"review_required", "reviewed_owner_source", "untrusted", "unknown", "derived", "generated"},
    "risk": {
        "indirect_prompt_injection",
        "sleeper_memory",
        "poisoned_experience",
        "source_spoofing",
        "private_data_bleed",
        "instruction_as_content",
        "stale_context",
        "permission_leakage",
        "over_promotion",
        "hallucinated_merge",
    },
}


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


def _read_yaml(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def _render_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
            "memory_route": {
                "brief": "aoa_memo_brief",
                "candidate": "repo memo/candidates",
                "validate": "aoa_memo_validate_candidate and aoa_memo_validate_port",
                "export": "aoa_memo_prepare_intake_packet",
                "review": "aoa_memo_review_intake",
                "durable_landing": "reviewed source patch in aoa-memo, not MCP direct write",
            },
            "central_memory_contracts": self._central_contracts(),
            "recommended_route": self._recommended_route(port),
            "validation": [
                "python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py",
                "python -m pytest mcp/services/aoa-memo-mcp/tests -q",
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
            "port_contract": str(port / LOCAL_PORT_CONTRACT) if port else None,
            "port_contract_exists": bool(port and (port / LOCAL_PORT_CONTRACT).exists()),
            "index": str(port / LOCAL_PORT_INDEX) if port else None,
            "index_exists": bool(port and (port / LOCAL_PORT_INDEX).exists()),
            "agents_card": str(port / "AGENTS.md") if port else None,
            "agents_card_exists": bool(port and (port / "AGENTS.md").exists()),
            "readme_exists": bool(port and (port / "README.md").exists()),
            "required_dirs": required,
            "ready": bool(
                port
                and (port / "AGENTS.md").exists()
                and (port / "README.md").exists()
                and (port / LOCAL_PORT_CONTRACT).exists()
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
        kind: str = "route",
        family: str = "memory-access",
        scope: str = "repo",
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        candidates_dir = route.memo_port / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=True)
        stamp = _utc_stamp()
        nonce = uuid4().hex[:8]
        slug = _slug(claim, 32)
        candidate_id = f"candidate:{route.name}:{stamp}:{nonce}-{slug}"
        path = candidates_dir / f"{stamp}.{nonce}.{_slug(claim)}.candidate.json"
        payload = {
            "schema": "aoa_local_memo_candidate_v1",
            "id": candidate_id,
            "repo": route.name,
            "kind": kind,
            "family": family,
            "scope": scope,
            "claim": claim,
            "source_refs": source_refs or evidence_refs,
            "evidence_refs": evidence_refs,
            "route": desired_route,
            "review_state": "candidate",
            "lifecycle": "captured",
            "source_trust": source_trust,
            "operation_mode": route.default_mode,
            "created_at": _now(),
            "guardrails": {
                "direct_durable_write": False,
                "instructions_treated_as_data": True,
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
        required = (
            "schema",
            "id",
            "repo",
            "kind",
            "family",
            "scope",
            "claim",
            "source_refs",
            "evidence_refs",
            "route",
            "review_state",
            "lifecycle",
            "source_trust",
            "operation_mode",
            "created_at",
            "guardrails",
        )
        for key in required:
            if key not in data:
                errors.append(f"missing required field: {key}")
        if data.get("schema") != "aoa_local_memo_candidate_v1":
            errors.append("schema must be aoa_local_memo_candidate_v1")
        if not data.get("claim"):
            errors.append("claim must be non-empty")
        if not isinstance(data.get("source_refs"), list) or not data.get("source_refs"):
            errors.append("source_refs must be a non-empty list")
        if not isinstance(data.get("evidence_refs"), list) or not data.get("evidence_refs"):
            errors.append("evidence_refs must be a non-empty list")
        source_trust = data.get("source_trust")
        desired_route = data.get("route")
        direct_write = bool((data.get("guardrails") or {}).get("direct_durable_write"))
        instructions_as_data = bool((data.get("guardrails") or {}).get("instructions_treated_as_data"))
        if direct_write:
            errors.append("candidate may not request direct durable memory write")
        if not instructions_as_data:
            errors.append("candidate must treat embedded instructions as data")
        if source_trust in {"untrusted", "unknown", "review_required"} and data.get("lifecycle") in {"current", "frozen"}:
            errors.append("unreviewed or untrusted candidates cannot claim current or frozen lifecycle")
        if desired_route == "durable_memory":
            errors.append("local candidates must not route directly to durable_memory")
        vocab_errors = self._validate_candidate_vocabulary(data)
        errors.extend(vocab_errors)
        return {
            "ok": not errors,
            "path": str(candidate_path),
            "repo": data.get("repo"),
            "candidate_id": data.get("id"),
            "errors": errors,
        }

    def build_port_index(self, repo: str, *, write: bool = False, check: bool = False) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        index = self._build_port_index_for_path(route.memo_port)
        index_text = _render_json(index)
        markdown_text = self._render_port_index_markdown(index)
        index_path = route.memo_port / LOCAL_PORT_INDEX
        markdown_path = route.memo_port / LOCAL_PORT_INDEX_MD
        result = {
            "schema": "aoa_memo_port_index_build_v1",
            "repo": route.name,
            "index": index,
            "index_path": str(index_path),
            "markdown_path": str(markdown_path),
            "written": False,
            "ok": True,
            "errors": [],
        }
        if check:
            errors = []
            if not index_path.exists() or index_path.read_text(encoding="utf-8") != index_text:
                errors.append(f"{index_path} is not up to date")
            if not markdown_path.exists() or markdown_path.read_text(encoding="utf-8") != markdown_text:
                errors.append(f"{markdown_path} is not up to date")
            result["errors"] = errors
            result["ok"] = not errors
            return result
        if write:
            index_path.write_text(index_text, encoding="utf-8")
            markdown_path.write_text(markdown_text, encoding="utf-8")
            result["written"] = True
        return result

    def validate_port(self, repo: str) -> dict[str, Any]:
        route = self.repo_route(repo)
        errors: list[str] = []
        port = route.memo_port
        if port is None or not port.exists():
            return {"schema": "aoa_local_memo_port_validation_v1", "repo": route.name, "ok": False, "errors": ["memo port is missing"]}
        port_payload = _read_yaml(port / LOCAL_PORT_CONTRACT)
        if not isinstance(port_payload, dict):
            errors.append("PORT.yaml is missing or invalid")
            port_payload = {}
        for directory in REQUIRED_PORT_DIRS:
            if not (port / directory).is_dir():
                errors.append(f"missing directory: {directory}")
        if port_payload.get("repo") != route.name:
            errors.append("PORT.yaml repo must match route repo")
        if port_payload.get("stronger_memory_owner") != "aoa-memo":
            errors.append("PORT.yaml stronger_memory_owner must be aoa-memo")
        allowed_routes = set(port_payload.get("allowed_routes") or [])
        if "reviewed_intake" not in allowed_routes:
            errors.append("PORT.yaml must allow reviewed_intake")
        for candidate in sorted((port / "candidates").glob("*.json")):
            result = self.validate_candidate(candidate)
            if not result["ok"]:
                errors.extend(f"{candidate}: {error}" for error in result["errors"])
        check = self.build_port_index(repo, check=True)
        if not check["ok"]:
            errors.extend(check["errors"])
        return {
            "schema": "aoa_local_memo_port_validation_v1",
            "repo": route.name,
            "port": str(port),
            "ok": not errors,
            "errors": errors,
        }

    def prepare_intake_packet(
        self,
        repo: str,
        candidate_refs: list[str],
        receipt_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        route = self.repo_route(repo)
        if route.memo_port is None:
            raise ValueError(f"unknown repo or missing source root: {repo}")
        if not candidate_refs:
            raise ValueError("candidate_refs must not be empty")
        candidates = [self._resolve_local_ref(route.memo_port, ref, "candidates") for ref in candidate_refs]
        missing = [candidate_refs[index] for index, path in enumerate(candidates) if path is None or not path.exists()]
        if missing:
            return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": False, "errors": [f"missing candidate ref: {ref}" for ref in missing]}
        candidate_payloads = [self._read_required_json(path) for path in candidates if path is not None]
        errors: list[str] = []
        source_refs: list[str] = []
        evidence_refs: list[str] = []
        for path, payload in zip(candidates, candidate_payloads, strict=False):
            validation = self.validate_candidate(path)
            if not validation["ok"]:
                errors.extend(validation["errors"])
            source_refs.extend(str(ref) for ref in payload.get("source_refs", []) if isinstance(ref, str))
            evidence_refs.extend(str(ref) for ref in payload.get("evidence_refs", []) if isinstance(ref, str))
        if errors:
            return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": False, "errors": errors}

        stamp = _utc_stamp()
        slug = _slug(str(candidate_payloads[0].get("claim", "memo-intake")), 48)
        export_path = route.memo_port / "exports" / f"{stamp}.{slug}.aoa-memo-intake.json"
        payload = {
            "schema": "aoa_local_memo_export_v1",
            "id": f"export:{route.name}:{stamp}:{slug}",
            "repo": route.name,
            "target_owner": "aoa-memo",
            "target_route": "reviewed_intake",
            "candidate_refs": [self._local_packet_ref(route.memo_port, path) for path in candidates if path is not None],
            "receipt_refs": receipt_refs or [],
            "source_refs": sorted(set(source_refs)),
            "evidence_refs": sorted(set(evidence_refs)),
            "allowed_result": "candidate_only",
            "created_at": _now(),
            "notes": "Prepared by aoa-memo-mcp. This is not durable memory landing.",
        }
        export_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.build_port_index(repo, write=True)
        return {"schema": "aoa_local_memo_intake_prepare_v1", "repo": route.name, "ok": True, "path": str(export_path), "export": payload, "errors": []}

    def review_intake(self, path: str | Path) -> dict[str, Any]:
        export_path = Path(path).expanduser().resolve()
        payload = _read_json(export_path)
        errors: list[str] = []
        if not isinstance(payload, dict):
            return {"schema": "aoa_local_memo_intake_review_v1", "ok": False, "path": str(export_path), "errors": ["export packet is not a JSON object"]}
        repo = str(payload.get("repo") or "")
        route = self.repo_route(repo)
        port = route.memo_port
        if port is None:
            errors.append("export repo does not resolve to a known memo port")
            port = export_path.parents[1]
        if payload.get("schema") != "aoa_local_memo_export_v1":
            errors.append("export schema must be aoa_local_memo_export_v1")
        if payload.get("target_owner") != "aoa-memo" or payload.get("target_route") != "reviewed_intake":
            errors.append("export must target aoa-memo reviewed_intake")
        for ref in payload.get("candidate_refs", []):
            candidate = self._resolve_local_ref(port, str(ref), "candidates")
            if candidate is None or not candidate.exists():
                errors.append(f"missing candidate ref: {ref}")
            else:
                result = self.validate_candidate(candidate)
                if not result["ok"]:
                    errors.extend(result["errors"])
        if not payload.get("source_refs"):
            errors.append("export must preserve source_refs")
        if not payload.get("evidence_refs"):
            errors.append("export must preserve evidence_refs")

        stamp = _utc_stamp()
        slug = _slug(str(payload.get("id") or "intake-review"), 48)
        receipt_path = port / "receipts" / f"{stamp}.{slug}.review-receipt.json"
        receipt = {
            "schema": "aoa_local_memo_receipt_v1",
            "id": f"receipt:{repo}:{stamp}:{slug}",
            "repo": repo,
            "candidate_ref": str((payload.get("candidate_refs") or [""])[0]),
            "export_ref": self._local_packet_ref(port, export_path),
            "result": "reviewed" if not errors else "rejected",
            "route": "reviewed_intake",
            "checks": ["schema", "candidate_refs", "source_refs", "evidence_refs", "guardrails"],
            "errors": errors,
            "created_at": _now(),
            "reviewed_by": "aoa-memo-mcp",
            "notes": "Review receipt only. Durable landing remains an aoa-memo source patch.",
        }
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if repo:
            self.build_port_index(repo, write=True)
        return {
            "schema": "aoa_local_memo_intake_review_v1",
            "repo": repo,
            "ok": not errors,
            "path": str(export_path),
            "receipt_path": str(receipt_path),
            "receipt": receipt,
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
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-port-index":
            return self.build_port_index(path_parts[0])
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-open-items":
            return {
                "schema": "aoa_local_memo_open_items_v1",
                "repo": path_parts[0],
                "open_items": self.build_port_index(path_parts[0])["index"]["open_items"],
            }
        if parsed.netloc == "repo" and len(path_parts) == 2 and path_parts[1] == "memo-vocabulary":
            return self.build_memo_port_vocabulary()
        if parsed.netloc == "intake" and len(path_parts) == 2 and path_parts[1] == "review":
            return self.find_intake_review(path_parts[0])
        if parsed.netloc == "memory" and path_parts[:1] == ["object"] and len(path_parts) == 2:
            return self.build_memory_object(path_parts[1])
        if parsed.netloc == "session" and len(path_parts) == 2 and path_parts[1] == "rehydrate":
            return self.build_session_rehydrate(path_parts[0])
        raise ValueError(f"unsupported aoa-memo resource URI: {uri}")

    def build_memo_port_vocabulary(self) -> dict[str, Any]:
        vocab_path = self.aoa_memo_root / CENTRAL_VOCABULARY
        payload = _read_json(vocab_path)
        return {
            "schema": "aoa_memo_port_vocabulary_resource_v1",
            "source_ref": str(vocab_path),
            "found": isinstance(payload, dict),
            "vocabulary": payload,
        }

    def find_intake_review(self, packet_id: str) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        for repo in ("Agents-of-Abyss", "abyss-stack", "abyss-machine"):
            port = self.repo_route(repo).memo_port
            if port is None or not port.exists():
                continue
            for path in sorted((port / "exports").glob("*.json")):
                payload = _read_json(path)
                if isinstance(payload, dict) and packet_id in {str(payload.get("id")), path.stem}:
                    matches.append({"repo": repo, "path": str(path), "packet": payload})
        return {
            "schema": "aoa_local_memo_intake_review_pointer_v1",
            "packet_id": packet_id,
            "found": bool(matches),
            "matches": matches,
        }

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
        raw_path = display.get("path") or display.get("archive_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return {
                "schema": "aoa_session_rehydrate_pointer_v1",
                "session_id": session.get("session_id"),
                "label": display.get("label"),
                "found": False,
                "registry": str(registry_path),
                "reason": "session archive path is missing",
            }
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = (self.aoa_archive_root / path).resolve()
        else:
            path = path.resolve()
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

    def _port_payload(self, port: Path) -> dict[str, Any]:
        payload = _read_yaml(port / LOCAL_PORT_CONTRACT)
        return payload if isinstance(payload, dict) else {}

    def _vocabulary_terms(self, port_payload: dict[str, Any] | None = None) -> dict[str, set[str]]:
        payload = _read_json(self.aoa_memo_root / CENTRAL_VOCABULARY)
        terms_payload = payload.get("terms", {}) if isinstance(payload, dict) else {}
        terms = {
            key: {str(value) for value in values}
            for key, values in terms_payload.items()
            if isinstance(values, list)
        }
        if not terms:
            terms = {key: set(values) for key, values in FALLBACK_VOCABULARY_TERMS.items()}
        local_terms = (port_payload or {}).get("local_terms") or {}
        if isinstance(local_terms, dict):
            for key, values in local_terms.items():
                if isinstance(values, list):
                    terms.setdefault(str(key), set()).update(str(value) for value in values)
        return terms

    def _validate_candidate_vocabulary(self, payload: dict[str, Any]) -> list[str]:
        repo = str(payload.get("repo") or "")
        try:
            route = self.repo_route(repo)
        except ValueError:
            return []
        port_payload = self._port_payload(route.memo_port) if route.memo_port else {}
        terms = self._vocabulary_terms(port_payload)
        field_map = {
            "kind": "kind",
            "family": "family",
            "scope": "scope",
            "route": "route",
            "review_state": "review_state",
            "lifecycle": "lifecycle",
            "source_trust": "source_trust",
        }
        errors: list[str] = []
        for field, term_group in field_map.items():
            value = payload.get(field)
            if isinstance(value, str) and value not in terms.get(term_group, set()):
                errors.append(f"{field} uses unknown vocabulary term: {value}")
        risks = payload.get("risk", [])
        if isinstance(risks, list):
            for risk in risks:
                if isinstance(risk, str) and risk not in terms.get("risk", set()):
                    errors.append(f"risk uses unknown vocabulary term: {risk}")
        return errors

    def _build_port_index_for_path(self, port: Path) -> dict[str, Any]:
        payload = self._port_payload(port)
        candidates_dir = str(payload.get("candidate_dir", "candidates"))
        receipt_dir = str(payload.get("receipt_dir", "receipts"))
        export_dir = str(payload.get("export_dir", "exports"))
        local_dir = str(payload.get("local_dir", "local"))
        candidate_paths = sorted((port / candidates_dir).glob("*.json"))
        by_kind: dict[str, int] = {}
        by_family: dict[str, int] = {}
        by_route: dict[str, int] = {}
        open_items: list[dict[str, str]] = []
        created_at: list[str] = []
        source_refs = [LOCAL_PORT_CONTRACT]

        for directory in (candidates_dir, receipt_dir, export_dir, local_dir):
            for path in sorted((port / directory).glob("*.json")):
                source_refs.append(self._local_packet_ref(port, path))
                packet = _read_json(path)
                if isinstance(packet, dict) and isinstance(packet.get("created_at"), str):
                    created_at.append(packet["created_at"])

        for path in candidate_paths:
            candidate = _read_json(path)
            if not isinstance(candidate, dict):
                continue
            for field, target in (("kind", by_kind), ("family", by_family), ("route", by_route)):
                value = candidate.get(field)
                if isinstance(value, str) and value:
                    target[value] = target.get(value, 0) + 1
            review_state = str(candidate.get("review_state") or "candidate")
            if review_state not in TERMINAL_REVIEW_STATES:
                open_items.append(
                    {
                        "id": str(candidate.get("id") or path.stem),
                        "path": self._local_packet_ref(port, path),
                        "review_state": review_state,
                        "route": str(candidate.get("route") or "reviewed_intake"),
                    }
                )
        return {
            "schema": "aoa_local_memo_port_index_v1",
            "repo": str(payload.get("repo") or port.parent.name),
            "port": port.name,
            "default_mode": str(payload.get("default_mode") or "write_candidate_only"),
            "counts": {
                "candidates": len(candidate_paths),
                "receipts": len(sorted((port / receipt_dir).glob("*.json"))),
                "exports": len(sorted((port / export_dir).glob("*.json"))),
                "local": len(sorted((port / local_dir).glob("*.json"))),
            },
            "by_kind": dict(sorted(by_kind.items())),
            "by_family": dict(sorted(by_family.items())),
            "by_route": dict(sorted(by_route.items())),
            "open_items": sorted(open_items, key=lambda item: item["path"]),
            "generated_at": max(created_at) if created_at else "1970-01-01T00:00:00Z",
            "source_refs": [LOCAL_PORT_CONTRACT, *sorted(ref for ref in source_refs if ref != LOCAL_PORT_CONTRACT)],
        }

    def _render_port_index_markdown(self, index: dict[str, Any]) -> str:
        counts = index["counts"]
        lines = [
            f"# {index['repo']} memo port index",
            "",
            "Generated from `PORT.yaml` and local memo packets.",
            "",
            "## Counts",
            "",
            "| District | Count |",
            "|---|---:|",
            f"| candidates | {counts['candidates']} |",
            f"| receipts | {counts['receipts']} |",
            f"| exports | {counts['exports']} |",
            f"| local | {counts['local']} |",
            "",
            "## Routes",
            "",
        ]
        if index["by_route"]:
            lines.extend(["| Route | Count |", "|---|---:|"])
            for route, count in index["by_route"].items():
                lines.append(f"| `{route}` | {count} |")
        else:
            lines.append("No routed candidates yet.")
        lines.extend(["", "## Open Items", ""])
        if index["open_items"]:
            lines.extend(["| ID | State | Route | Path |", "|---|---|---|---|"])
            for item in index["open_items"]:
                lines.append(f"| `{item['id']}` | `{item['review_state']}` | `{item['route']}` | `{item['path']}` |")
        else:
            lines.append("No open candidate items.")
        lines.extend(
            [
                "",
                "## Agent Route",
                "",
                "Executable validation and rebuild commands live in the nearest `AGENTS.md` for this memo port.",
                "This generated index is a read model; it does not own the operational route.",
                "",
            ]
        )
        return "\n".join(lines)

    def _resolve_local_ref(self, port: Path, ref: str, preferred_dir: str) -> Path | None:
        if ref.startswith(("candidate:", "receipt:", "export:")):
            for path in sorted((port / preferred_dir).glob("*.json")):
                payload = _read_json(path)
                if isinstance(payload, dict) and payload.get("id") == ref:
                    return path
            return None
        path = Path(ref.split("#", 1)[0])
        if path.is_absolute():
            return path
        if ref.startswith("memo/"):
            return port.parent / path
        candidate = port / path
        if candidate.exists():
            return candidate
        candidate = port / preferred_dir / path.name
        if candidate.exists():
            return candidate
        return port / path

    def _local_packet_ref(self, port: Path, path: Path) -> str:
        try:
            return path.resolve().relative_to(port.resolve()).as_posix()
        except ValueError:
            return str(path)

    def _read_required_json(self, path: Path | None) -> dict[str, Any]:
        if path is None:
            raise ValueError("missing JSON path")
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"{path} is not a JSON object")
        return payload

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
        if not isinstance(repo, str):
            raise ValueError("repo must be a repository name or approved alias")
        candidate = repo.strip()
        if not candidate:
            raise ValueError("repo must be a repository name or approved alias")
        aliases = {
            "agents": "Agents-of-Abyss",
            "agents-of-abyss": "Agents-of-Abyss",
            "aoa": "Agents-of-Abyss",
            "stack": "abyss-stack",
            "machine": "abyss-machine",
        }
        normalized = aliases.get(candidate, candidate)
        if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
            raise ValueError("repo must be a repository name or approved alias, not a path")
        return normalized
