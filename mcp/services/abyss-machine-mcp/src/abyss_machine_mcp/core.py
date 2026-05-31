from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")
DEFAULT_ABYSS_MACHINE_BIN = "abyss-machine"
DEFAULT_TIMEOUT_SECONDS = 12.0

TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

STOP_LINES = [
    "Do not execute arbitrary shell commands.",
    "Do not run privileged commands.",
    "Do not restart services or mutate processes.",
    "Do not mutate abyss-machine, abyss-stack, AoA, work, or game roots.",
    "Do not read raw private capture payloads by default.",
    "Do not land durable memory or compute proof verdicts.",
    "Do not widen beyond stdio without a later decision.",
]

OWNER_LAYERS = [
    {
        "layer": "abyss-machine",
        "owns": [
            "host facts",
            "host policies",
            "hardware evidence",
            "generated latest read models",
            "resource and memory planning",
            "typing and nervous state",
            "heartbeats, reactions, responses, and change ledger",
        ],
        "truth_roots": ["/etc/abyss-machine", "/var/lib/abyss-machine", "/srv/abyss-machine"],
    },
    {
        "layer": "abyss-stack",
        "owns": [
            "runnable MCP package",
            "stdio service topology",
            "stack-side access-plane decision record",
        ],
        "truth_roots": ["mcp/services/abyss-machine-mcp", "docs/decisions"],
    },
    {
        "layer": "aoa-memo",
        "owns": ["durable reviewed memory and memory object review"],
        "truth_roots": ["/srv/AbyssOS/aoa-memo"],
    },
    {
        "layer": "aoa-evals",
        "owns": ["proof bundles, bounded verdict logic, and report authority"],
        "truth_roots": ["/srv/AbyssOS/aoa-evals"],
    },
    {
        "layer": "operator",
        "owns": ["intent, authorization, private context permission, and destructive action approval"],
        "truth_roots": ["current session and explicit operator authorization"],
    },
]

SURFACE_META: dict[str, dict[str, str]] = {
    "stack-bridge": {
        "owner": "abyss-machine",
        "truth_level": "bridge_contract",
        "description": "stack-facing owner-aware bridge and evidence map",
    },
    "bridge": {
        "owner": "abyss-machine",
        "truth_level": "host_bridge_contract",
        "description": "host command and integration contract",
    },
    "resource-status": {
        "owner": "abyss-machine",
        "truth_level": "latest_resource_state",
        "description": "current resource orchestration posture",
    },
    "resource-plan": {
        "owner": "abyss-machine",
        "truth_level": "launch_preflight",
        "description": "non-mutating launch route plan for a work class and kind",
    },
    "memory-status": {
        "owner": "abyss-machine",
        "truth_level": "latest_memory_state",
        "description": "RAM, swap, zram, PSI, and memory policy status",
    },
    "memory-pressure": {
        "owner": "abyss-machine",
        "truth_level": "latest_memory_pressure",
        "description": "compact memory pressure and swap state",
    },
    "memory-plan": {
        "owner": "abyss-machine",
        "truth_level": "memory_launch_gate",
        "description": "non-mutating memory gate for new work",
    },
    "storage-pressure": {
        "owner": "abyss-machine",
        "truth_level": "latest_storage_pressure",
        "description": "current storage pressure and routing posture",
    },
    "processes-game-guard": {
        "owner": "abyss-machine",
        "truth_level": "protective_process_read_model",
        "description": "non-mutating game/workload guard posture",
    },
    "typing-status": {
        "owner": "abyss-machine",
        "truth_level": "typing_intake_status",
        "description": "safe typed-text intake status",
    },
    "typing-coverage": {
        "owner": "abyss-machine",
        "truth_level": "typing_intake_coverage",
        "description": "typed-text source coverage read model",
    },
    "typing-causal-context": {
        "owner": "abyss-machine",
        "truth_level": "typing_causal_read_model",
        "description": "causal context around recent typed-text intake",
    },
    "nervous-status": {
        "owner": "abyss-machine",
        "truth_level": "nervous_status",
        "description": "nervous capture/index/retrieval status",
    },
    "nervous-brief": {
        "owner": "abyss-machine",
        "truth_level": "nervous_brief",
        "description": "compact nervous brief for a scope",
    },
    "nervous-recall": {
        "owner": "abyss-machine",
        "truth_level": "evidence_pack",
        "description": "focused nervous recall evidence pack",
    },
    "maps-paths": {
        "owner": "abyss-machine",
        "truth_level": "machine_atlas_paths",
        "description": "generated machine atlas paths, commands, and refresh automation",
    },
    "maps-policy": {
        "owner": "abyss-machine",
        "truth_level": "machine_atlas_policy",
        "description": "source policy for generated machine atlas maps",
    },
    "maps-query": {
        "owner": "abyss-machine",
        "truth_level": "machine_atlas_route_signal",
        "description": "focused query over generated machine atlas axes and route entries",
    },
    "maps-packet": {
        "owner": "abyss-machine",
        "truth_level": "machine_atlas_context_packet",
        "description": "bounded reader-profile context packet over machine atlas route entries",
    },
    "maps-validate": {
        "owner": "abyss-machine",
        "truth_level": "machine_atlas_validation",
        "description": "validator result for generated machine atlas maps and refresh route",
    },
    "rag-paths": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_paths",
        "description": "generated machine RAG trace paths and commands",
    },
    "rag-policy": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_policy",
        "description": "read-only machine RAG trace policy derived from maps source law",
    },
    "rag-trace": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_trace",
        "description": "read-only maps-to-evidence trace with local trace eval",
    },
    "rag-latest": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_trace_latest",
        "description": "latest generated machine RAG trace",
    },
    "rag-eval": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_trace_eval",
        "description": "latest/local machine RAG trace quality eval",
    },
    "rag-validate": {
        "owner": "abyss-machine",
        "truth_level": "machine_rag_validation",
        "description": "validator result for the machine RAG trace loop",
    },
    "ai-llm-registry": {
        "owner": "abyss-machine",
        "truth_level": "llm_registry",
        "description": "local LLM profile registry",
    },
    "ai-llm-resident-status": {
        "owner": "abyss-machine",
        "truth_level": "resident_llm_runtime_state",
        "description": "resident local LLM runtime status",
    },
    "heartbeats-pulse": {
        "owner": "abyss-machine",
        "truth_level": "heartbeat_read_model",
        "description": "OS Abyss heartbeat pulse read model",
    },
    "changes-status": {
        "owner": "abyss-machine",
        "truth_level": "change_ledger_status",
        "description": "host change-ledger status",
    },
    "changes-index": {
        "owner": "abyss-machine",
        "truth_level": "change_ledger_index",
        "description": "host change-ledger index",
    },
    "stack-bridge-validate": {
        "owner": "abyss-machine",
        "truth_level": "bridge_validation",
        "description": "stack bridge validator result",
    },
}


@dataclass(slots=True)
class CommandOutput:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: float


CommandRunner = Callable[[list[str], float], CommandOutput]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_runner(argv: list[str], timeout: float) -> CommandOutput:
    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return CommandOutput(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandOutput(
            argv=argv,
            returncode=124,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=f"command timed out after {timeout}s",
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
        )
    except OSError as exc:
        return CommandOutput(
            argv=argv,
            returncode=127,
            stdout="",
            stderr=str(exc),
            elapsed_ms=round((time.monotonic() - start) * 1000, 1),
        )


def _safe_token(value: str, label: str) -> str:
    if not TOKEN_RE.fullmatch(value):
        raise ValueError(f"{label} must be a short token, got: {value!r}")
    return value


def _safe_query(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("query must not be empty")
    if len(value) > 500:
        raise ValueError("query is too long; keep MCP recall focused")
    return value


def _read_json(stdout: str) -> Any:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _preferred_keys(keys: list[str]) -> list[str]:
    order = [
        "schema",
        "schema_version",
        "ok",
        "status",
        "state",
        "class",
        "generated_at",
        "updated_at",
        "summary",
        "latest",
        "path",
        "paths",
        "issues",
        "warnings",
        "errors",
        "recommendations",
        "pressure",
        "route",
        "decision",
        "source",
        "truth_level",
        "owner",
        "refs",
        "protected_roots",
        "handoff_rules",
        "non_claims",
        "commands",
    ]
    ordered = [key for key in order if key in keys]
    ordered.extend(key for key in keys if key not in ordered)
    return ordered


def _compact(value: Any, *, depth: int = 0, max_depth: int = 5, max_items: int = 12, max_string: int = 500) -> Any:
    if depth >= max_depth:
        if isinstance(value, dict):
            return {"_truncated": "dict", "keys": list(value.keys())[:max_items], "count": len(value)}
        if isinstance(value, list):
            return {"_truncated": "list", "count": len(value)}
        return value
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        keys = _preferred_keys([str(key) for key in value.keys()])
        for key in keys[:max_items]:
            result[key] = _compact(
                value.get(key),
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
            )
        if len(keys) > max_items:
            result["_truncated_keys"] = keys[max_items:]
        return result
    if isinstance(value, list):
        result = [
            _compact(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_string=max_string)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            result.append({"_truncated_items": len(value) - max_items})
        return result
    if isinstance(value, str) and len(value) > max_string:
        return value[:max_string] + f"...[truncated {len(value) - max_string} chars]"
    return value


def _summary(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return None
    for key in ("summary", "status", "state", "pressure"):
        value = payload.get(key)
        if value not in (None, "", []):
            return _compact(value, max_depth=4, max_items=10)
    return _compact(
        {key: payload.get(key) for key in ("ok", "schema", "generated_at", "latest", "issues", "warnings") if key in payload},
        max_depth=3,
    )


def _payload_ok(payload: Any, returncode: int) -> bool:
    if returncode != 0:
        return False
    if isinstance(payload, dict) and payload.get("ok") is False:
        return False
    return True


def _collect_paths(value: Any, *, limit: int = 16) -> list[str]:
    found: list[str] = []

    def walk(item: Any) -> None:
        if len(found) >= limit:
            return
        if isinstance(item, dict):
            path = item.get("path") or item.get("latest")
            if isinstance(path, str) and path.startswith("/"):
                found.append(path)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    unique: list[str] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique[:limit]


def _bounded_limit(value: int, *, default: int, maximum: int) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc
    if limit <= 0:
        return default
    return min(limit, maximum)


def _flatten_refs(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not isinstance(value, dict):
        return records
    if "path" in value and ("exists" in value or "truth_level" in value or "schema" in value):
        records.append(
            {
                "ref": prefix.strip("."),
                "path": value.get("path"),
                "exists": value.get("exists"),
                "ok": value.get("ok"),
                "schema": value.get("schema"),
                "expected_schema": value.get("expected_schema"),
                "schema_ok": value.get("schema_ok"),
                "generated_at": value.get("generated_at"),
                "truth_level": value.get("truth_level"),
                "summary": _compact(value.get("summary"), max_depth=3, max_items=8),
                "load_error": value.get("load_error"),
            }
        )
        return records
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else str(key)
        records.extend(_flatten_refs(child, child_prefix))
    return records


@dataclass(slots=True)
class AbyssMachineMCPState:
    workspace_root: Path
    abyss_machine_bin: str = DEFAULT_ABYSS_MACHINE_BIN
    command_runner: CommandRunner = _default_runner
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        abyss_machine_bin: str | None = None,
        command_runner: CommandRunner | None = None,
        timeout_seconds: float | None = None,
    ) -> "AbyssMachineMCPState":
        root = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or DEFAULT_WORKSPACE_ROOT
        ).expanduser().resolve()
        return cls(
            workspace_root=root,
            abyss_machine_bin=abyss_machine_bin or os.environ.get("ABYSS_MACHINE_BIN") or DEFAULT_ABYSS_MACHINE_BIN,
            command_runner=command_runner or _default_runner,
            timeout_seconds=float(timeout_seconds or os.environ.get("ABYSS_MACHINE_MCP_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        )

    def authority_boundary(self) -> dict[str, Any]:
        return {
            "schema": "abyss_machine_mcp_authority_boundary_v1",
            "mcp_role": "stdio read-only access plane over abyss-machine host read models",
            "service_owner": "abyss-stack owns the runnable MCP package only",
            "stronger_owners": [
                "abyss-machine source contracts under /etc/abyss-machine",
                "abyss-machine generated facts and histories under /var/lib/abyss-machine",
                "operator authorization for mutation or private context",
                "aoa-memo for durable reviewed memory",
                "aoa-evals for proof and verdict authority",
            ],
            "source_hierarchy": [
                "/etc/abyss-machine source contracts and policy JSON",
                "nearest /var/lib/abyss-machine/*/AGENTS.md owner card",
                "/var/lib/abyss-machine generated latest/index JSON",
                "append-only host histories and evidence refs",
                "MCP compact summaries",
            ],
            "exposure": "stdio-only",
            "mutation_posture": "no write, no repair, no privileged command, no arbitrary shell",
            "stop_lines": STOP_LINES,
        }

    def owner_layers(self) -> list[dict[str, Any]]:
        return OWNER_LAYERS

    def available_surfaces(self) -> dict[str, Any]:
        return {
            "schema": "abyss_machine_mcp_surface_catalog_v1",
            "count": len(SURFACE_META),
            "surfaces": [
                {"name": name, **meta, "mutates": False}
                for name, meta in sorted(SURFACE_META.items())
            ],
            "authority_boundary": self.authority_boundary(),
        }

    def _surface_args(
        self,
        name: str,
        *,
        query: str = "",
        work_class: str = "heavy",
        kind: str = "ai",
        scope: str = "now",
        mode: str = "hybrid",
        axis: str = "",
        reader_profile: str = "agent",
        limit: int = 20,
        evidence_limit: int = 12,
    ) -> list[str]:
        if name == "stack-bridge":
            return ["stack-bridge", "--json"]
        if name == "bridge":
            return ["bridge", "--json"]
        if name == "resource-status":
            return ["resource", "status", "--json"]
        if name == "resource-plan":
            return [
                "resource",
                "plan",
                "--class",
                _safe_token(work_class, "work_class"),
                "--kind",
                _safe_token(kind, "kind"),
                "--json",
            ]
        if name == "memory-status":
            return ["memory", "status", "--json"]
        if name == "memory-pressure":
            return ["memory", "pressure", "--json"]
        if name == "memory-plan":
            return ["memory", "plan", "--json"]
        if name == "storage-pressure":
            return ["storage", "pressure", "--json"]
        if name == "processes-game-guard":
            return ["processes", "game-guard", "--json"]
        if name == "typing-status":
            return ["typing", "status", "--json"]
        if name == "typing-coverage":
            return ["typing", "coverage", "--json"]
        if name == "typing-causal-context":
            return ["typing", "causal-context", "--json"]
        if name == "nervous-status":
            return ["nervous", "status", "--json"]
        if name == "nervous-brief":
            return ["nervous", "brief", "--scope", _safe_token(scope, "scope"), "--json"]
        if name == "nervous-recall":
            return [
                "nervous",
                "recall",
                "--mode",
                _safe_token(mode, "mode"),
                "--query",
                _safe_query(query),
                "--json",
            ]
        if name == "maps-paths":
            return ["maps", "paths", "--json"]
        if name == "maps-policy":
            return ["maps", "policy", "--json"]
        if name == "maps-query":
            args = ["maps", "query"]
            if axis:
                args.extend(["--axis", _safe_token(axis, "axis")])
            if query:
                args.extend(["--query", _safe_query(query)])
            args.append("--json")
            return args
        if name == "maps-packet":
            args = ["maps", "packet"]
            if axis:
                args.extend(["--axis", _safe_token(axis, "axis")])
            if query:
                args.extend(["--query", _safe_query(query)])
            args.extend([
                "--reader-profile",
                _safe_token(reader_profile, "reader_profile"),
                "--limit",
                str(_bounded_limit(limit, default=20, maximum=50)),
                "--json",
            ])
            return args
        if name == "maps-validate":
            return ["maps", "validate", "--json"]
        if name == "rag-paths":
            return ["rag", "paths", "--json"]
        if name == "rag-policy":
            return ["rag", "policy", "--json"]
        if name == "rag-trace":
            args = ["rag", "trace", "--query", _safe_query(query or "machine RAG trace")]
            if axis:
                args.extend(["--axis", _safe_token(axis, "axis")])
            if reader_profile:
                args.extend(["--reader-profile", _safe_token(reader_profile, "reader_profile")])
            args.extend([
                "--limit",
                str(_bounded_limit(limit, default=8, maximum=50)),
                "--evidence-limit",
                str(_bounded_limit(evidence_limit, default=12, maximum=40)),
                "--json",
            ])
            return args
        if name == "rag-latest":
            return ["rag", "latest", "--json"]
        if name == "rag-eval":
            return ["rag", "eval", "--json"]
        if name == "rag-validate":
            return ["rag", "validate", "--json"]
        if name == "ai-llm-registry":
            return ["ai", "llm", "registry", "--json"]
        if name == "ai-llm-resident-status":
            return ["ai", "llm", "resident", "status", "--json"]
        if name == "heartbeats-pulse":
            return ["heartbeats", "pulse", "--json"]
        if name == "changes-status":
            return ["changes", "status", "--json"]
        if name == "changes-index":
            return ["changes", "index", "--json"]
        if name == "stack-bridge-validate":
            return ["stack-bridge", "validate", "--json"]
        raise ValueError(f"unknown or disallowed abyss-machine surface: {name}")

    def _run_json(self, surface: str, args: list[str], timeout: float | None = None) -> dict[str, Any]:
        argv = [self.abyss_machine_bin, *args]
        output = self.command_runner(argv, float(timeout or self.timeout_seconds))
        payload = _read_json(output.stdout)
        return {
            "surface": surface,
            "argv": argv,
            "returncode": output.returncode,
            "stderr": output.stderr.strip(),
            "elapsed_ms": output.elapsed_ms,
            "payload": payload,
            "payload_parse_ok": payload is not None,
            "ok": _payload_ok(payload, output.returncode),
        }

    def _public_command_result(self, run: dict[str, Any], *, include_payload: bool = False) -> dict[str, Any]:
        surface = str(run["surface"])
        payload = run.get("payload")
        meta = SURFACE_META.get(surface, {})
        result: dict[str, Any] = {
            "schema": "abyss_machine_mcp_surface_result_v1",
            "surface": surface,
            "owner": meta.get("owner", "abyss-machine"),
            "truth_level": meta.get("truth_level", "host_read_model"),
            "description": meta.get("description", ""),
            "mutates": False,
            "command": run["argv"],
            "ok": run["ok"],
            "returncode": run["returncode"],
            "elapsed_ms": run["elapsed_ms"],
            "payload_parse_ok": run["payload_parse_ok"],
            "payload_schema": payload.get("schema") if isinstance(payload, dict) else None,
            "payload_generated_at": payload.get("generated_at") if isinstance(payload, dict) else None,
            "payload_summary": _summary(payload),
            "evidence_paths": _collect_paths(payload),
            "stderr": run["stderr"] or None,
            "authority_boundary": self.authority_boundary(),
        }
        if include_payload:
            result["payload_compact"] = _compact(payload, max_depth=5, max_items=12)
        return result

    def surface(
        self,
        name: str,
        *,
        query: str = "",
        work_class: str = "heavy",
        kind: str = "ai",
        scope: str = "now",
        mode: str = "hybrid",
        axis: str = "",
        reader_profile: str = "agent",
        limit: int = 20,
        evidence_limit: int = 12,
        include_payload: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        if name not in SURFACE_META:
            raise ValueError(f"unknown or disallowed abyss-machine surface: {name}")
        args = self._surface_args(
            name,
            query=query,
            work_class=work_class,
            kind=kind,
            scope=scope,
            mode=mode,
            axis=axis,
            reader_profile=reader_profile,
            limit=limit,
            evidence_limit=evidence_limit,
        )
        run = self._run_json(name, args, timeout=timeout)
        return self._public_command_result(run, include_payload=include_payload)

    def _stack_bridge_payload(self) -> tuple[dict[str, Any], dict[str, Any]]:
        args = self._surface_args("stack-bridge")
        run = self._run_json("stack-bridge", args)
        payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        return run, payload

    def _evidence_map_from_stack(
        self,
        run: dict[str, Any],
        stack: dict[str, Any],
        *,
        layer: str | None = None,
        limit: int = 40,
    ) -> dict[str, Any]:
        limit = _bounded_limit(limit, default=40, maximum=120)
        refs = _flatten_refs(stack.get("refs", {}))
        if layer:
            needle = layer.casefold()
            refs = [record for record in refs if needle in str(record.get("ref", "")).casefold()]
        refs = sorted(refs, key=lambda item: str(item.get("ref") or ""))[:limit]
        by_layer: dict[str, int] = {}
        for record in refs:
            top = str(record.get("ref") or "").split(".", 1)[0] or "unknown"
            by_layer[top] = by_layer.get(top, 0) + 1
        return {
            "schema": "abyss_machine_mcp_evidence_map_v1",
            "ok": run["ok"],
            "stack_bridge_generated_at": stack.get("generated_at"),
            "stack_bridge_status": stack.get("status"),
            "layer_filter": layer,
            "count": len(refs),
            "by_layer": by_layer,
            "evidence_refs": refs,
            "protected_roots": _compact(stack.get("protected_roots", []), max_depth=3, max_items=16),
            "handoff_rules": _compact(stack.get("handoff_rules", []), max_depth=2, max_items=12),
            "authority_boundary": self.authority_boundary(),
        }

    def evidence_map(self, layer: str | None = None, limit: int = 40) -> dict[str, Any]:
        run, stack = self._stack_bridge_payload()
        return self._evidence_map_from_stack(run, stack, layer=layer, limit=limit)

    def machine_brief(self, profile: str = "fast", evidence_limit: int = 8) -> dict[str, Any]:
        profile = _safe_token(profile, "profile")
        if profile not in {"fast", "live", "full"}:
            raise ValueError("profile must be one of: fast, live, full")
        run, stack = self._stack_bridge_payload()
        commands = stack.get("commands") if isinstance(stack.get("commands"), dict) else {}
        mutation_gates = commands.get("mutation_gates") if isinstance(commands, dict) else []
        safe_read = commands.get("safe_read") if isinstance(commands, dict) else []
        evidence = self._evidence_map_from_stack(run, stack, limit=evidence_limit)
        live_surfaces: dict[str, Any] = {}
        if profile in {"live", "full"}:
            for surface_name in (
                "resource-status",
                "memory-pressure",
                "storage-pressure",
                "processes-game-guard",
                "typing-status",
                "heartbeats-pulse",
            ):
                live_surfaces[surface_name] = self.surface(surface_name, include_payload=(profile == "full"))
        return {
            "schema": "abyss_machine_mcp_brief_v1",
            "profile": profile,
            "ok": run["ok"],
            "generated_at": _now(),
            "workspace_root": self.workspace_root.as_posix(),
            "machine": {
                "bridge_status": stack.get("status"),
                "bridge_schema": stack.get("schema"),
                "bridge_generated_at": stack.get("generated_at"),
                "bridge_summary": _compact(stack.get("summary"), max_depth=3, max_items=12),
                "bridge_latest": stack.get("latest"),
            },
            "owner_layers": self.owner_layers(),
            "constraints": {
                "protected_roots": _compact(stack.get("protected_roots", []), max_depth=3, max_items=16),
                "handoff_rules": _compact(stack.get("handoff_rules", []), max_depth=2, max_items=12),
                "non_claims": _compact(stack.get("non_claims", []), max_depth=2, max_items=12),
                "mutation_gates": _compact(mutation_gates, max_depth=2, max_items=12),
            },
            "safe_next_route": {
                "read_first": "Use evidence refs and targeted surfaces before action.",
                "for_new_work": "Use abyss_machine_route(intent, work_class, kind) before starting medium/heavy work.",
                "for_mutation": "Use abyss-machine changes preflight outside MCP; this MCP does not approve or perform mutation.",
                "for_storage": "Use abyss-machine storage write-preflight outside MCP before large writes.",
                "safe_read_examples": _compact(safe_read, max_depth=2, max_items=10),
            },
            "evidence": {
                "stack_bridge_ok": evidence["ok"],
                "count": evidence["count"],
                "by_layer": evidence["by_layer"],
                "evidence_refs": evidence["evidence_refs"],
            },
            "live_surfaces": live_surfaces,
            "authority_boundary": self.authority_boundary(),
        }

    def machine_route(self, intent: str, work_class: str = "heavy", kind: str = "ai") -> dict[str, Any]:
        intent = intent.strip()
        if not intent:
            raise ValueError("intent must not be empty")
        if len(intent) > 500:
            raise ValueError("intent is too long; keep route requests focused")
        resource = self.surface("resource-plan", work_class=work_class, kind=kind, include_payload=True)
        memory = self.surface("memory-plan", include_payload=True)
        game_guard = self.surface("processes-game-guard", include_payload=True)
        brief = self.machine_brief(profile="fast")
        return {
            "schema": "abyss_machine_mcp_route_v1",
            "intent": intent,
            "work_class": work_class,
            "kind": kind,
            "mutates": False,
            "route_posture": "preflight_only",
            "surface_results": {
                "resource_plan": resource,
                "memory_plan": memory,
                "game_guard": game_guard,
            },
            "constraints": brief["constraints"],
            "safe_next_route": brief["safe_next_route"],
            "evidence": brief["evidence"],
            "authority_boundary": self.authority_boundary(),
        }

    def recall(self, query: str, mode: str = "hybrid") -> dict[str, Any]:
        return self.surface("nervous-recall", query=query, mode=mode, include_payload=True)

    def machine_maps(self, axis: str | None = None, query: str = "", limit: int = 40) -> dict[str, Any]:
        limit = _bounded_limit(limit, default=40, maximum=100)
        args = self._surface_args("maps-query", axis=axis or "", query=query)
        run = self._run_json("maps-query", args, timeout=max(self.timeout_seconds, 20.0))
        payload = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        return {
            "schema": "abyss_machine_mcp_maps_v1",
            "ok": run["ok"],
            "axis": axis,
            "query": query,
            "limit": limit,
            "surface": self._public_command_result(run, include_payload=False),
            "summary": _compact(payload.get("summary"), max_depth=3, max_items=8),
            "truth_status": payload.get("truth_status"),
            "result_count": len(results),
            "results": _compact(results[:limit], max_depth=5, max_items=12),
            "evidence_paths": _collect_paths(payload, limit=24),
            "authority_boundary": self.authority_boundary(),
        }

    def machine_context_packet(
        self,
        axis: str | None = None,
        query: str = "",
        reader_profile: str = "agent",
        limit: int = 20,
    ) -> dict[str, Any]:
        limit = _bounded_limit(limit, default=20, maximum=50)
        args = self._surface_args("maps-packet", axis=axis or "", query=query, reader_profile=reader_profile, limit=limit)
        run = self._run_json("maps-packet", args, timeout=max(self.timeout_seconds, 20.0))
        packet = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        return {
            "schema": "abyss_machine_mcp_context_packet_v1",
            "ok": run["ok"],
            "reader_profile": reader_profile,
            "axis": axis,
            "query": query,
            "limit": limit,
            "surface": self._public_command_result(run, include_payload=False),
            "packet_schema": packet.get("schema"),
            "packet_id": packet.get("packet_id"),
            "packet_truth_status": packet.get("truth_status"),
            "summary": _compact(packet.get("summary"), max_depth=3, max_items=12),
            "profile_route": _compact(packet.get("profile_route"), max_depth=4, max_items=12),
            "entries": _compact(packet.get("entries", []), max_depth=5, max_items=12),
            "evidence_refs": _compact(packet.get("evidence_refs", []), max_depth=4, max_items=20),
            "authority_boundary": self.authority_boundary(),
        }

    def machine_rag_trace(
        self,
        query: str,
        axis: str | None = "by-rag-run",
        reader_profile: str = "retrieval-context",
        limit: int = 8,
        evidence_limit: int = 12,
    ) -> dict[str, Any]:
        query = query.strip()
        if not query:
            query = "machine RAG trace"
        limit = _bounded_limit(limit, default=8, maximum=50)
        evidence_limit = _bounded_limit(evidence_limit, default=12, maximum=40)
        args = self._surface_args(
            "rag-trace",
            query=query,
            axis=axis or "",
            reader_profile=reader_profile,
            limit=limit,
            evidence_limit=evidence_limit,
        )
        run = self._run_json("rag-trace", args, timeout=max(self.timeout_seconds, 20.0))
        trace = run.get("payload") if isinstance(run.get("payload"), dict) else {}
        return {
            "schema": "abyss_machine_mcp_rag_trace_v1",
            "ok": run["ok"],
            "query": query,
            "axis": axis,
            "reader_profile": reader_profile,
            "limit": limit,
            "evidence_limit": evidence_limit,
            "surface": self._public_command_result(run, include_payload=False),
            "trace_schema": trace.get("schema"),
            "trace_id": trace.get("trace_id"),
            "trace_truth_status": trace.get("truth_status"),
            "summary": _compact(trace.get("summary"), max_depth=3, max_items=12),
            "answer": _compact(trace.get("answer"), max_depth=4, max_items=12),
            "eval": _compact(trace.get("eval"), max_depth=4, max_items=12),
            "evidence_snapshots": _compact(trace.get("evidence_snapshots", []), max_depth=4, max_items=16),
            "authority_boundary": self.authority_boundary(),
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "abyss-machine":
            raise ValueError(f"unsupported resource scheme: {uri}")
        name = unquote(parsed.netloc)
        path = unquote(parsed.path.lstrip("/"))
        if name == "brief" and not path:
            return self.machine_brief()
        if name == "authority" and not path:
            return self.authority_boundary()
        if name == "evidence-map" and not path:
            return self.evidence_map()
        if name == "maps":
            return self.machine_maps(axis=path or None, limit=20)
        if name == "context-packet":
            return self.machine_context_packet(reader_profile=path or "agent", limit=20)
        if name == "rag" and not path:
            return self.surface("rag-latest")
        if name == "rag-validate" and not path:
            return self.surface("rag-validate")
        if name == "surface" and path:
            return self.surface(path)
        resource_surface = {
            "stack-bridge": "stack-bridge",
            "resource-status": "resource-status",
            "memory-pressure": "memory-pressure",
            "typing-status": "typing-status",
            "maps-paths": "maps-paths",
            "maps-policy": "maps-policy",
            "maps-packet": "maps-packet",
            "maps-validate": "maps-validate",
            "rag-paths": "rag-paths",
            "rag-policy": "rag-policy",
            "rag-latest": "rag-latest",
            "rag-eval": "rag-eval",
            "rag-validate": "rag-validate",
        }.get(name)
        if resource_surface and not path:
            return self.surface(resource_surface)
        raise ValueError(f"unknown abyss-machine resource: {uri}")
