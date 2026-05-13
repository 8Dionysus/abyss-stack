#!/usr/bin/env python3
from __future__ import annotations

import ast
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import textwrap
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable


SCRIPT_PATH = Path(__file__).resolve()


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


SCRIPT_ROOT = find_repo_root(SCRIPT_PATH.parent)
STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
CONFIGS_ROOT = Path(os.environ.get("AOA_CONFIGS_ROOT", str(STACK_ROOT / "Configs")))
ROUTE_API_BASE_URL = os.environ.get("AOA_ROUTE_API_BASE_URL", "http://127.0.0.1:5402").rstrip("/")
LANGCHAIN_API_BASE_URL = os.environ.get("AOA_LANGCHAIN_API_BASE_URL", "http://127.0.0.1:5403").rstrip("/")
LOG_ROOT_DEFAULT = Path(
    os.environ.get("AOA_GOVERNED_RUN_LOG_ROOT", str(STACK_ROOT / "Logs" / "governed-runs"))
)
POLICY_PATH_DEFAULT = Path(
    os.environ.get(
        "AOA_GOVERNED_EXECUTION_POLICY_PATH",
        str(STACK_ROOT / "Configs" / "agent-api" / "governed-execution-policy.yaml"),
    )
)
STATUS_SCRIPT_DEFAULT = CONFIGS_ROOT / "scripts" / "aoa-status"
SOURCE_POLICY_FALLBACK = SCRIPT_ROOT / "config-templates" / "Configs" / "agent-api" / "governed-execution-policy.yaml"
CANARY_CATALOG_PATH_DEFAULT = Path(
    os.environ.get(
        "AOA_GOVERNED_EXECUTION_CANARY_CATALOG_PATH",
        str(STACK_ROOT / "Configs" / "agent-api" / "governed-canary-catalog.json"),
    )
)
SOURCE_CANARY_CATALOG_FALLBACK = (
    SCRIPT_ROOT / "config-templates" / "Configs" / "agent-api" / "governed-canary-catalog.json"
)
DEFAULT_PROFILE_CLASS = "workhorse"
TRUST_STATES = {"experimental", "canary_proven", "trusted"}
TASK_CLASSES = {
    "docs_only",
    "policy_surface",
    "validation_tightening",
    "governed_lane",
    "generated_surface",
}
FAILURE_CLASSES = {
    "autonomy_gate_failed",
    "policy_denied",
    "approval_missing",
    "scope_violation",
    "proposal_invalid",
    "post_change_validation_failure",
    "rollback_failed",
}
FOCUS_TERM_STOPWORDS = {
    "about",
    "after",
    "before",
    "change",
    "clarify",
    "completed",
    "compute",
    "computes",
    "current",
    "default",
    "existing",
    "fresher",
    "freshest",
    "goal",
    "improve",
    "keep",
    "latest",
    "older",
    "operator",
    "path",
    "request",
    "retry",
    "running",
    "stale",
    "status",
    "stops",
    "summary",
    "surface",
    "surfacing",
    "update",
    "wording",
}
REQUEST_RETRY_SUFFIX_RE = re.compile(r"-retry(?:\d+)?(?=(?:\.[^.]+)+$|$)")
BUILD_ROUTER_NOOP_GOAL_MARKERS = (
    "no-op rebuild",
    "git-stable",
    "semantically unchanged",
    "on-disk json or jsonl",
    "editing generated files directly",
)
ROUTING_ROADMAP_GENERATED_SURFACE_GOAL_MARKERS = (
    "generated-surface refresh lane",
    "parity maintenance",
    "sibling source repos",
)
BUILD_ROUTER_WRITE_LOOP_START = "for filename, payload in outputs.items():"
BUILD_ROUTER_WRITE_LOOP_END = 'print(f"[ok] wrote {relative_posix(path)}")'
PLAYBOOK_REVIEW_PACKET_CONTRACTS_PATH = Path(
    "Knowledge/federation/aoa-playbooks/generated/playbook_review_packet_contracts.min.json"
)
EVAL_RUNTIME_TEMPLATE_INDEX_PATH = Path(
    "Knowledge/federation/aoa-evals/generated/runtime_candidate_template_index.min.json"
)
MEMO_RUNTIME_WRITEBACK_TARGETS_PATH = Path(
    "Knowledge/federation/aoa-memo/generated/runtime_writeback_targets.min.json"
)
PLAYBOOK_REVIEW_INTAKE_PATH = Path(
    "Knowledge/federation/aoa-playbooks/generated/playbook_review_intake.min.json"
)
EVAL_RUNTIME_CANDIDATE_INTAKE_PATH = Path(
    "Knowledge/federation/aoa-evals/generated/runtime_candidate_intake.min.json"
)
MEMO_RUNTIME_WRITEBACK_INTAKE_PATH = Path(
    "Knowledge/federation/aoa-memo/generated/runtime_writeback_intake.min.json"
)
PLAYBOOK_REVIEW_PACKET_CONTRACTS_SOURCE_REF = (
    "aoa-playbooks/generated/playbook_review_packet_contracts.min.json"
)
EVAL_RUNTIME_TEMPLATE_INDEX_SOURCE_REF = (
    "aoa-evals/generated/runtime_candidate_template_index.min.json"
)
MEMO_RUNTIME_WRITEBACK_TARGETS_SOURCE_REF = (
    "aoa-memo/generated/runtime_writeback_targets.min.json"
)
PLAYBOOK_REVIEW_INTAKE_SOURCE_REF = "aoa-playbooks/generated/playbook_review_intake.min.json"
EVAL_RUNTIME_CANDIDATE_INTAKE_SOURCE_REF = "aoa-evals/generated/runtime_candidate_intake.min.json"
MEMO_RUNTIME_WRITEBACK_INTAKE_SOURCE_REF = "aoa-memo/generated/runtime_writeback_intake.min.json"


def load_trials_module() -> Any:
    target = (
        SCRIPT_ROOT
        / "mechanics"
        / "inference-pilots"
        / "parts"
        / "local-trials"
        / "aoa_local_ai_trials.py"
    )
    loader = importlib.machinery.SourceFileLoader("aoa_local_ai_trials_governed", str(target))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"could not create module spec for {target}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)  # type: ignore[arg-type]
    return module


TRIALS = load_trials_module()


def utc_now() -> str:
    return TRIALS.utc_now()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    TRIALS.write_json(path, payload)


def write_text(path: Path, text: str) -> None:
    TRIALS.write_text(path, text)


def write_text_exact(path: Path, text: str) -> None:
    TRIALS.write_text_exact(path, text)


def run_command(parts: list[str], *, cwd: Path | None = None, timeout_s: float | None = None) -> dict[str, Any]:
    return TRIALS.run_command(parts, cwd=cwd, timeout_s=timeout_s)


def parse_yaml_or_json(text: str) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(text)
    except ImportError:
        payload = json.loads(text)
    if not isinstance(payload, dict):
        raise RuntimeError("expected object payload")
    return payload


def sha256_digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slugify(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = lowered.strip("-")
    return lowered or "candidate"


def resolve_policy_path(path: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    candidates.append(POLICY_PATH_DEFAULT)
    candidates.append(SOURCE_POLICY_FALLBACK)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved
    raise RuntimeError("governed execution policy path could not be resolved")


def load_policy(path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    policy_path = resolve_policy_path(path)
    payload = parse_yaml_or_json(policy_path.read_text(encoding="utf-8"))
    validate_policy(payload)
    return payload, policy_path


def resolve_canary_catalog_path(path: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    candidates.append(CANARY_CATALOG_PATH_DEFAULT)
    candidates.append(SOURCE_CANARY_CATALOG_FALLBACK)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser()
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists():
            return resolved
    raise RuntimeError("governed canary catalog path could not be resolved")


def load_canary_catalog(path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    catalog_path = resolve_canary_catalog_path(path)
    payload = parse_yaml_or_json(catalog_path.read_text(encoding="utf-8"))
    validate_canary_catalog(payload)
    return payload, catalog_path


def validate_criteria_payload(label: str, payload: Any) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must be an object")
    required_fields = (
        "minimum_successful_runs",
        "minimum_task_classes",
        "maximum_scope_violations",
        "maximum_rollback_failures",
        "maximum_break_glass_runs",
        "maximum_post_change_validation_failures",
    )
    for field in required_fields:
        if field not in payload:
            raise RuntimeError(f"{label} is missing {field}")
        value = payload[field]
        if not isinstance(value, int) or value < 0:
            raise RuntimeError(f"{label}.{field} must be a non-negative integer")


def validate_policy(policy: dict[str, Any]) -> None:
    if policy.get("surface_type") != "runtime_governed_execution_policy":
        raise RuntimeError("policy surface_type must equal runtime_governed_execution_policy")
    if policy.get("enabled") is not True:
        raise RuntimeError("governed execution policy must be enabled")
    global_rules = policy.get("global_rules")
    if not isinstance(global_rules, dict):
        raise RuntimeError("policy global_rules must be an object")
    if global_rules.get("gate_mode") != "fail_closed":
        raise RuntimeError("policy gate_mode must be fail_closed")
    validate_criteria_payload(
        "policy global_rules.promotion_criteria.canary_proven",
        (global_rules.get("promotion_criteria") or {}).get("canary_proven"),
    )
    validate_criteria_payload(
        "policy global_rules.promotion_criteria.trusted",
        (global_rules.get("promotion_criteria") or {}).get("trusted"),
    )
    validate_criteria_payload(
        "policy global_rules.repo_scope_expansion_gate",
        global_rules.get("repo_scope_expansion_gate"),
    )
    targets = policy.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise RuntimeError("policy targets must contain at least one entry")
    default_target_id = str(global_rules.get("default_target_id") or "").strip()
    if not default_target_id:
        raise RuntimeError("policy global_rules.default_target_id must be a non-empty string")
    if default_target_id not in targets:
        raise RuntimeError("policy global_rules.default_target_id must refer to a configured target")
    for target_id, target_entry in targets.items():
        if not isinstance(target_entry, dict):
            raise RuntimeError(f"policy target {target_id} must be an object")
        repo_scope = str(target_entry.get("repo_scope") or "").strip()
        if repo_scope != target_id:
            raise RuntimeError(f"policy target {target_id} must declare repo_scope={target_id}")
        if not isinstance(target_entry.get("default_repo_root"), str) or not target_entry["default_repo_root"].strip():
            raise RuntimeError(f"policy target {target_id} must declare a non-empty default_repo_root")
        playbooks = target_entry.get("playbooks")
        if not isinstance(playbooks, dict) or not playbooks:
            raise RuntimeError(f"policy target {target_id} must contain at least one playbook entry")
        for playbook_id, entry in playbooks.items():
            if not isinstance(entry, dict):
                raise RuntimeError(f"policy entry for {target_id}/{playbook_id} must be an object")
            for required in (
                "enabled",
                "execution_kind",
                "repo_scope",
                "allowed_files",
                "acceptance_commands",
                "break_glass_allowed",
                "repair_allowed",
                "trust_state",
                "task_class",
            ):
                if required not in entry:
                    raise RuntimeError(f"policy entry for {target_id}/{playbook_id} is missing {required}")
            if str(entry.get("repo_scope") or "").strip() != target_id:
                raise RuntimeError(f"policy entry for {target_id}/{playbook_id} must keep repo_scope={target_id}")
            if entry.get("trust_state") not in TRUST_STATES:
                raise RuntimeError(f"policy entry for {target_id}/{playbook_id} has invalid trust_state")
            if entry.get("task_class") not in TASK_CLASSES:
                raise RuntimeError(f"policy entry for {target_id}/{playbook_id} has unsupported task_class")


def validate_canary_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("surface_type") != "runtime_governed_execution_canary_catalog":
        raise RuntimeError("governed canary catalog surface_type must equal runtime_governed_execution_canary_catalog")
    canaries = catalog.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        raise RuntimeError("governed canary catalog must contain at least one canary")
    seen: set[str] = set()
    for entry in canaries:
        if not isinstance(entry, dict):
            raise RuntimeError("governed canary entries must be objects")
        for required in ("canary_id", "target_id", "title", "goal", "playbook_id", "task_class", "profile_class"):
            value = entry.get(required)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"governed canary entry is missing a non-empty {required}")
        canary_id = str(entry["canary_id"])
        if canary_id in seen:
            raise RuntimeError(f"duplicate canary_id in governed canary catalog: {canary_id}")
        seen.add(canary_id)
        if entry["task_class"] not in TASK_CLASSES:
            raise RuntimeError(f"unsupported canary task_class for {canary_id}: {entry['task_class']}")


def is_abyss_stack_checkout(path: Path) -> bool:
    return (
        (path / "CONTRIBUTING.md").exists()
        and (path / "scripts" / "validate_stack.py").exists()
        and (path / "docs" / "DEPLOYMENT.md").exists()
    )


def is_aoa_routing_checkout(path: Path) -> bool:
    return (
        (path / "README.md").exists()
        and (path / "scripts" / "build_router.py").exists()
        and (path / "scripts" / "validate_router.py").exists()
        and (path / "docs" / "FEDERATION_ENTRY_ABI.md").exists()
    )


def target_checkout_detector(target_id: str) -> Callable[[Path], bool]:
    detectors: dict[str, Callable[[Path], bool]] = {
        "abyss-stack": is_abyss_stack_checkout,
        "aoa-routing": is_aoa_routing_checkout,
    }
    detector = detectors.get(target_id)
    if detector is None:
        raise RuntimeError(f"unsupported governed target_id: {target_id}")
    return detector


def infer_target_id_from_repo_root(repo_root: str | Path | None) -> str | None:
    if repo_root is None:
        return None
    try:
        resolved = Path(repo_root).expanduser().resolve()
    except Exception:
        return None
    for target_id in ("abyss-stack", "aoa-routing"):
        if target_checkout_detector(target_id)(resolved):
            return target_id
    return None


def resolve_target_policy(policy: dict[str, Any], target_id: str) -> dict[str, Any]:
    targets = policy.get("targets") or {}
    entry = targets.get(target_id)
    if not isinstance(entry, dict):
        raise RuntimeError(f"target {target_id} is not present in governed execution policy")
    return entry


def candidate_repo_roots_for_target(
    target_id: str,
    *,
    policy: dict[str, Any] | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    if policy is not None:
        try:
            target_policy = resolve_target_policy(policy, target_id)
        except RuntimeError:
            target_policy = {}
        default_repo_root = target_policy.get("default_repo_root")
        if isinstance(default_repo_root, str) and default_repo_root.strip():
            candidates.append(Path(default_repo_root).expanduser())
    if target_id == "abyss-stack":
        env_root = os.environ.get("AOA_SOURCE_ROOT")
        if env_root:
            candidates.append(Path(env_root).expanduser())
        if is_abyss_stack_checkout(SCRIPT_ROOT):
            candidates.append(SCRIPT_ROOT)
        candidates.append(Path.home() / "src" / "abyss-stack")
        candidates.append(STACK_ROOT)
    elif target_id == "aoa-routing":
        env_root = os.environ.get("AOA_ROUTING_ROOT")
        if env_root:
            candidates.append(Path(env_root).expanduser())
        candidates.append(Path("/srv/AbyssOS/aoa-routing"))
        candidates.append(Path.home() / "src" / "aoa-routing")
    else:
        raise RuntimeError(f"unsupported governed target_id: {target_id}")
    return candidates


def resolve_default_repo_root(target_id: str = "abyss-stack", *, policy: dict[str, Any] | None = None) -> Path:
    detector = target_checkout_detector(target_id)
    seen: set[str] = set()
    for candidate in candidate_repo_roots_for_target(target_id, policy=policy):
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if detector(candidate):
            return candidate.resolve()
    fallback = candidate_repo_roots_for_target(target_id, policy=policy)[0]
    return fallback.resolve()


def default_request_template() -> dict[str, Any]:
    policy = load_policy_or_none()
    target_id = str(((policy or {}).get("global_rules") or {}).get("default_target_id") or "abyss-stack")
    return {
        "goal": "Describe the bounded abyss-stack change you want to propose.",
        "target_id": target_id,
        "playbook_id": "AOA-P-0011",
        "profile_class": DEFAULT_PROFILE_CLASS,
        "repo_root": str(resolve_default_repo_root(target_id, policy=policy)),
        "memo": None,
        "break_glass_reason": None,
        "canary_id": None,
        "task_class": None,
    }


def validate_request_shape(request: dict[str, Any]) -> None:
    if not isinstance(request.get("goal"), str) or not request["goal"].strip():
        raise RuntimeError("request goal must be a non-empty string")
    if not isinstance(request.get("target_id"), str) or not request["target_id"].strip():
        raise RuntimeError("request target_id must be a non-empty string")
    if bool(request.get("playbook_id")) == bool(request.get("playbook_select")):
        raise RuntimeError("request must include exactly one of playbook_id or playbook_select")
    if not isinstance(request.get("profile_class"), str) or not request["profile_class"].strip():
        raise RuntimeError("request profile_class must be a non-empty string")
    if not isinstance(request.get("repo_root"), str) or not request["repo_root"].strip():
        raise RuntimeError("request repo_root must be a non-empty string")
    memo = request.get("memo")
    if memo is not None and not isinstance(memo, dict):
        raise RuntimeError("request memo must be an object when present")
    if request.get("break_glass_reason") is not None and not isinstance(request["break_glass_reason"], str):
        raise RuntimeError("break_glass_reason must be a string when present")
    if request.get("canary_id") is not None and not isinstance(request["canary_id"], str):
        raise RuntimeError("canary_id must be a string when present")
    if request.get("task_class") is not None and not isinstance(request["task_class"], str):
        raise RuntimeError("task_class must be a string when present")


def load_request(path: str | Path) -> tuple[dict[str, Any], Path]:
    request_path = Path(path).expanduser()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("request file must contain a JSON object")
    validate_request_shape(payload)
    return payload, request_path


def lookup_canary(catalog: dict[str, Any], canary_id: str) -> dict[str, Any]:
    for entry in catalog.get("canaries") or []:
        if isinstance(entry, dict) and entry.get("canary_id") == canary_id:
            return copy.deepcopy(entry)
    raise RuntimeError(f"unknown governed canary_id: {canary_id}")


def request_from_canary(
    canary_id: str,
    *,
    catalog_path: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    catalog, _catalog_path = load_canary_catalog(catalog_path)
    canary = lookup_canary(catalog, canary_id)
    policy = load_policy_or_none()
    target_id = str(canary["target_id"])
    resolved_repo_root = (
        normalize_repo_root(repo_root, target_id=target_id)
        if repo_root is not None
        else resolve_default_repo_root(target_id, policy=policy)
    )
    payload: dict[str, Any] = {
        "goal": canary["goal"],
        "target_id": target_id,
        "playbook_id": canary["playbook_id"],
        "profile_class": canary.get("profile_class") or DEFAULT_PROFILE_CLASS,
        "repo_root": str(resolved_repo_root),
        "memo": copy.deepcopy(canary.get("memo")),
        "break_glass_reason": None,
        "canary_id": canary["canary_id"],
        "task_class": canary["task_class"],
    }
    validate_request_shape(payload)
    return payload


def materialize_canary_requests(
    write_dir: str | Path,
    *,
    catalog_path: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    target_root = Path(write_dir).expanduser()
    target_root.mkdir(parents=True, exist_ok=True)
    catalog, resolved_catalog = load_canary_catalog(catalog_path)
    written: list[dict[str, Any]] = []
    for entry in catalog.get("canaries") or []:
        if not isinstance(entry, dict):
            continue
        request = request_from_canary(
            str(entry["canary_id"]),
            catalog_path=resolved_catalog,
            repo_root=repo_root,
        )
        target = target_root / f"{entry['canary_id']}.request.json"
        target.write_text(json.dumps(request, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        written.append(
            {
                "canary_id": entry["canary_id"],
                "target_id": entry["target_id"],
                "task_class": entry["task_class"],
                "playbook_id": entry["playbook_id"],
                "request_file": str(target),
            }
        )
    return {
        "ok": True,
        "catalog_path": str(resolved_catalog),
        "write_dir": str(target_root),
        "request_count": len(written),
        "requests": written,
    }


def resolve_request_canary_context(
    request: dict[str, Any],
    *,
    catalog_path: str | Path | None = None,
) -> dict[str, Any] | None:
    canary_id = request.get("canary_id")
    if not canary_id:
        return None
    catalog, resolved_catalog = load_canary_catalog(catalog_path)
    canary = lookup_canary(catalog, str(canary_id))
    if request.get("target_id") and request["target_id"] != canary["target_id"]:
        raise RuntimeError("request target_id does not match the selected canary")
    if request.get("playbook_id") and request["playbook_id"] != canary["playbook_id"]:
        raise RuntimeError("request playbook_id does not match the selected canary")
    if request.get("task_class") and request["task_class"] != canary["task_class"]:
        raise RuntimeError("request task_class does not match the selected canary")
    request["target_id"] = canary["target_id"]
    request["task_class"] = canary["task_class"]
    return {
        "catalog_path": str(resolved_catalog),
        "canary": canary,
    }


def http_post_json(url: str, payload: dict[str, Any], *, timeout_s: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="strict")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed for {url}: {exc}") from exc
    parsed = json.loads(body) if body else {}
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object from {url}")
    return parsed


def resolve_playbook_id(
    request: dict[str, Any],
    policy: dict[str, Any],
    advisory_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    provider = advisory_provider or default_advisory_provider
    advisory = provider(request)
    target_id = str(request.get("target_id") or "")
    target_policy = resolve_target_policy(policy, target_id)
    playbook_id = advisory.get("playbook_id") or request.get("playbook_id")
    if not isinstance(playbook_id, str) or not playbook_id:
        raise RuntimeError("could not resolve playbook_id for governed execution")
    playbook_policy = resolve_playbook_policy(policy, playbook_id, target_id)
    advisory["target_id"] = target_id
    advisory["target_policy"] = copy.deepcopy(target_policy)
    advisory["playbook_id"] = playbook_id
    advisory["policy"] = copy.deepcopy(playbook_policy)
    return advisory


def resolve_playbook_policy(policy: dict[str, Any], playbook_id: str, target_id: str) -> dict[str, Any]:
    target_policy = resolve_target_policy(policy, target_id)
    playbooks = target_policy.get("playbooks") or {}
    entry = playbooks.get(playbook_id)
    if not isinstance(entry, dict):
        raise RuntimeError(
            f"playbook {playbook_id} is not present in governed execution policy for target {target_id}"
        )
    return entry


def default_advisory_provider(request: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_files": [],
    }
    if request.get("playbook_id"):
        response = http_post_json(
            f"{ROUTE_API_BASE_URL}/playbooks/inspect",
            {"playbook_id": request["playbook_id"]},
        )
        payload["playbook_id"] = request["playbook_id"]
        payload["playbook"] = response.get("playbook")
        payload["playbook_source_files"] = response.get("source_files") or []
    else:
        response = http_post_json(
            f"{ROUTE_API_BASE_URL}/playbooks/select",
            request["playbook_select"],
        )
        matches = response.get("playbooks") or []
        if not matches:
            raise RuntimeError("route-api playbooks/select returned no matches")
        match = matches[0]
        payload["playbook_id"] = match.get("playbook_id")
        payload["playbook"] = match
        payload["playbook_selection"] = response
        payload["playbook_source_files"] = response.get("source_files") or []
    memo = request.get("memo")
    if isinstance(memo, dict):
        memo_payload = {
            "family": memo.get("family"),
            "mode": memo.get("mode"),
            "return_ready": bool(memo.get("return_ready")),
        }
        payload["memo_contract"] = http_post_json(
            f"{ROUTE_API_BASE_URL}/memo/recall-contract",
            memo_payload,
        )
    return payload


def default_review_packet_trace_provider(request: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_text": str(request.get("goal") or "Produce a bounded advisory trace for governed execution."),
        "temperature": 0.0,
        "max_tokens": 128,
    }
    for key in ("playbook_id", "playbook_select", "memo", "kag", "profile_class"):
        value = request.get(key)
        if value is not None:
            payload[key] = value
    response = http_post_json(f"{LANGCHAIN_API_BASE_URL}/run/federated", payload, timeout_s=180.0)
    advisory_trace = response.get("advisory_trace")
    if not isinstance(advisory_trace, dict):
        raise RuntimeError("langchain-api /run/federated did not return advisory_trace")
    return advisory_trace


def load_runtime_mirror_json(relative_path: Path) -> dict[str, Any]:
    path = STACK_ROOT / relative_path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"runtime mirror missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"runtime mirror invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"runtime mirror must be an object: {path}")
    return payload


def playbook_review_packet_contract_by_id(playbook_id: str) -> dict[str, Any] | None:
    payload = load_runtime_mirror_json(PLAYBOOK_REVIEW_PACKET_CONTRACTS_PATH)
    for entry in payload.get("playbooks", []):
        if isinstance(entry, dict) and entry.get("playbook_id") == playbook_id:
            return entry
    return None


def playbook_review_intake_by_id(playbook_id: str) -> dict[str, Any] | None:
    payload = load_runtime_mirror_json(PLAYBOOK_REVIEW_INTAKE_PATH)
    for entry in payload.get("playbooks", []):
        if isinstance(entry, dict) and entry.get("playbook_id") == playbook_id:
            return entry
    return None


def eval_runtime_candidate_templates() -> list[dict[str, Any]]:
    payload = load_runtime_mirror_json(EVAL_RUNTIME_TEMPLATE_INDEX_PATH)
    templates = payload.get("templates", [])
    if not isinstance(templates, list):
        raise RuntimeError("runtime candidate template index must contain templates list")
    return [entry for entry in templates if isinstance(entry, dict)]


def eval_runtime_candidate_intake_entries() -> list[dict[str, Any]]:
    payload = load_runtime_mirror_json(EVAL_RUNTIME_CANDIDATE_INTAKE_PATH)
    templates = payload.get("templates", [])
    if not isinstance(templates, list):
        raise RuntimeError("runtime candidate intake surface must contain templates list")
    return [entry for entry in templates if isinstance(entry, dict)]


def memo_runtime_writeback_targets() -> list[dict[str, Any]]:
    payload = load_runtime_mirror_json(MEMO_RUNTIME_WRITEBACK_TARGETS_PATH)
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise RuntimeError("runtime writeback targets surface must contain targets list")
    return [entry for entry in targets if isinstance(entry, dict)]


def memo_runtime_writeback_intake_targets() -> list[dict[str, Any]]:
    payload = load_runtime_mirror_json(MEMO_RUNTIME_WRITEBACK_INTAKE_PATH)
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise RuntimeError("runtime writeback intake surface must contain targets list")
    return [entry for entry in targets if isinstance(entry, dict)]


def fallback_review_packet_trace(
    request: dict[str, Any],
    advisory_context: dict[str, Any],
    *,
    playbook_contract: dict[str, Any] | None,
) -> dict[str, Any]:
    playbook_context = advisory_context.get("playbook")
    playbook_summary: dict[str, Any] | None = None
    if isinstance(playbook_context, dict):
        playbook_summary = {
            "playbook_id": playbook_context.get("playbook_id") or request.get("playbook_id"),
            "name": playbook_context.get("name") or playbook_context.get("title"),
            "scenario": ((playbook_context.get("registry_entry") or {}).get("scenario") if isinstance(playbook_context.get("registry_entry"), dict) else None),
            "trigger": ((playbook_context.get("activation_entry") or {}).get("trigger") if isinstance(playbook_context.get("activation_entry"), dict) else None),
        }
        playbook_summary = {key: value for key, value in playbook_summary.items() if value not in (None, [], {})}
    elif playbook_contract is not None:
        playbook_summary = {
            "playbook_id": playbook_contract.get("playbook_id"),
            "name": playbook_contract.get("playbook_name"),
            "scenario": playbook_contract.get("scenario"),
        }

    trace: dict[str, Any] = {
        "selectors": {
            "playbook_id": request.get("playbook_id"),
            "playbook_select": request.get("playbook_select"),
            "kag": request.get("kag"),
            "profile_class": request.get("profile_class") or DEFAULT_PROFILE_CLASS,
        },
        "trace_source": "governed-fallback",
    }
    if playbook_summary is not None:
        trace["playbook"] = {
            "summary": playbook_summary,
            "source_files": advisory_context.get("playbook_source_files") or [],
        }
        review_status = None
        if isinstance(playbook_context, dict) and isinstance(playbook_context.get("review_status"), dict):
            review_status = playbook_context["review_status"]
        if review_status is not None:
            trace["playbook"]["review_status"] = review_status
        if playbook_contract is not None:
            trace["playbook"]["review_packet_contract"] = playbook_contract
    if isinstance(request.get("memo"), dict):
        trace["memo"] = {
            "selector": request["memo"],
            "resolution": "requested_only",
            "source_files": advisory_context.get("memo_contract", {}).get("source_files", []),
        }
    if isinstance(request.get("kag"), dict):
        trace["kag"] = {
            "selector": request["kag"],
            "resolution": "requested_only",
        }
    return trace


def default_gate_provider() -> dict[str, Any]:
    status_script = Path(os.environ.get("AOA_GOVERNED_EXECUTION_STATUS_SCRIPT", str(STATUS_SCRIPT_DEFAULT)))
    command = ["bash", str(status_script), "--autonomy", "--json"]
    raw = run_command(command, cwd=status_script.parent.parent if status_script.exists() else None, timeout_s=180)
    if raw["exit_code"] != 0:
        raise RuntimeError(raw["stderr"].strip() or "aoa-status --autonomy --json failed")
    payload = json.loads(raw["stdout"])
    if not isinstance(payload, dict):
        raise RuntimeError("aoa-status --autonomy --json did not return an object")
    payload["_command_meta"] = {
        "command": command,
        "exit_code": raw["exit_code"],
    }
    return payload


def evaluate_autonomy_gate(
    gate_payload: dict[str, Any],
    *,
    playbook_policy: dict[str, Any],
    break_glass_reason: str | None,
    global_rules: dict[str, Any],
) -> dict[str, Any]:
    overall_status = str(gate_payload.get("overall_status") or "fail")
    if overall_status == "pass":
        return {
            "allowed": True,
            "status": "pass",
            "break_glass_used": False,
            "reasons": [],
        }
    if not playbook_policy.get("break_glass_allowed"):
        return {
            "allowed": False,
            "status": overall_status,
            "break_glass_used": False,
            "reasons": ["break_glass_not_allowed"],
        }
    if global_rules.get("break_glass_requires_reason") and not (break_glass_reason or "").strip():
        return {
            "allowed": False,
            "status": overall_status,
            "break_glass_used": False,
            "reasons": ["break_glass_reason_required"],
        }
    return {
        "allowed": True,
        "status": overall_status,
        "break_glass_used": True,
        "reasons": ["break_glass_used"],
    }


def normalize_repo_root(path: str | Path, *, target_id: str) -> Path:
    repo_root = Path(path).expanduser().resolve()
    if not target_checkout_detector(target_id)(repo_root):
        raise RuntimeError(f"repo_root does not match governed target {target_id}: {repo_root}")
    return repo_root


def matches_allowed_pattern(relative_path: str, pattern: str) -> bool:
    normalized_path = PurePosixPath("/" + relative_path.lstrip("/"))
    normalized_pattern = "/" + pattern.lstrip("/")
    return normalized_path.match(normalized_pattern)


def path_allowed(relative_path: str, patterns: list[str]) -> bool:
    return any(matches_allowed_pattern(relative_path, pattern) for pattern in patterns)


def enumerate_allowed_candidates(repo_root: Path, patterns: list[str]) -> list[str]:
    candidates: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        rel = path.relative_to(repo_root).as_posix()
        if path_allowed(rel, patterns):
            candidates.append(rel)
    return sorted(set(candidates))


def focus_terms_from_goal(goal: str, *, target_file: str) -> list[str]:
    strong_terms: list[str] = []
    weak_terms: list[str] = []
    target_file_key = target_file.lower()
    target_name_key = PurePosixPath(target_file).name.lower()
    target_name_terms = {
        token
        for token in re.split(r"[^A-Za-z0-9]+", PurePosixPath(target_file).name.lower())
        if len(token) >= 4
    }

    def add_term(token: str, *, strong: bool) -> None:
        normalized = token.strip().lower()
        if not normalized or len(normalized) < 4:
            return
        if normalized in FOCUS_TERM_STOPWORDS:
            return
        if normalized == target_file_key or normalized == target_name_key:
            return
        if normalized in target_name_terms and strong_terms:
            return
        if normalized in strong_terms or normalized in weak_terms:
            return
        if strong:
            strong_terms.append(normalized)
        else:
            weak_terms.append(normalized)

    for raw in re.findall(r"`([^`]+)`|([A-Za-z0-9_.:/-]{4,})", goal):
        token = (raw[0] or raw[1]).strip()
        normalized = token.lower()
        add_term(token, strong=any(char in normalized for char in "_./-"))
    for token in re.split(r"[^A-Za-z0-9]+", PurePosixPath(target_file).name.lower()):
        add_term(token, strong=False)
    return strong_terms + weak_terms


def candidate_path_hints_from_goal(goal: str) -> list[str]:
    hints: list[str] = []
    for raw in re.findall(r"`([^`]+)`|([A-Za-z0-9_./:-]{4,})", goal):
        token_block = (raw[0] or raw[1]).strip().lower()
        if not token_block:
            continue
        for piece in re.split(r"\s+", token_block):
            token = piece.strip("()[]{}<>,;:'\"")
            if not token:
                continue
            token = token.rstrip(".")
            if not token:
                continue
            if token.startswith("--"):
                continue
            if "/" not in token and "." not in token:
                continue
            if token and token not in hints:
                hints.append(token)
    return hints


def narrow_candidate_files(candidate_files: list[str], *, goal: str) -> list[str]:
    goal_lower = goal.lower()
    goal_plain = goal_lower.replace("`", "")
    exclusive_matches = []
    for item in candidate_files:
        name = PurePosixPath(item).name.lower()
        stem = PurePosixPath(item).stem.lower()
        match_tokens = {item.lower(), name, stem}
        if any(
            re.search(rf"(?<![a-z0-9_]){re.escape(token)}\s+only(?![a-z0-9_])", goal_plain)
            or re.search(rf"(?<![a-z0-9_])only\s+{re.escape(token)}(?![a-z0-9_])", goal_plain)
            for token in match_tokens
            if len(token) >= 4
        ):
            exclusive_matches.append(item)
    if exclusive_matches:
        return exclusive_matches

    hints = candidate_path_hints_from_goal(goal)
    if not hints:
        return candidate_files
    narrowed = [
        item
        for item in candidate_files
        if any(item.lower() == hint or item.lower().endswith("/" + hint) or hint in item.lower() for hint in hints)
    ]
    return narrowed or candidate_files


def python_symbol_hints_from_goal(goal: str) -> list[str]:
    hints: list[str] = []
    for raw in re.findall(r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_]{2,})", goal):
        token = (raw[0] or raw[1]).strip()
        if "_" not in token:
            continue
        if token.lower() in FOCUS_TERM_STOPWORDS:
            continue
        if token not in hints:
            hints.append(token)
    return hints


def extract_python_named_block(text: str, *, symbol: str) -> str | None:
    match = re.search(rf"(?m)^def {re.escape(symbol)}\(", text)
    if match is None:
        match = re.search(rf"(?m)^class {re.escape(symbol)}\b", text)
    if match is None:
        return None
    start = match.start()
    remainder = text[start:]
    next_match = re.search(r"(?m)^(def|class) ", remainder[len(match.group(0)) :])
    if next_match is None:
        block = remainder
    else:
        block_end = len(match.group(0)) + next_match.start()
        block = remainder[:block_end]
    stripped = block.strip()
    return stripped or None


def extract_python_symbol_excerpt(
    text: str,
    *,
    goal: str,
    char_limit: int,
    focus_terms: list[str] | None = None,
) -> str | None:
    for symbol in python_symbol_hints_from_goal(goal):
        stripped = extract_python_named_block(text, symbol=symbol)
        if stripped is None:
            continue
        if len(stripped) <= char_limit:
            return stripped
        return compact_python_block(
            stripped,
            char_limit=char_limit,
            focus_terms=(focus_terms or []) + [symbol],
        )
    return None


def persist_proposal_attempt_artifacts(
    run_dir: Path | None,
    *,
    kind: str,
    attempt: int,
    prompt: str,
    response: str,
    error: str | None = None,
) -> None:
    if run_dir is None:
        return
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    attempt_label = f"a{attempt:02d}"
    if prompt:
        write_text(artifacts_dir / f"proposal.{kind}.{attempt_label}.prompt.txt", prompt)
    if response:
        write_text_exact(artifacts_dir / f"proposal.{kind}.{attempt_label}.response.txt", response)
    if error:
        write_text_exact(artifacts_dir / f"proposal.{kind}.{attempt_label}.error.txt", error + "\n")


def compact_excerpt(text: str, *, char_limit: int = 1800, focus_terms: list[str] | None = None) -> str:
    stripped = text.strip()
    if len(stripped) <= char_limit:
        return stripped
    lowered = stripped.lower()
    for term in focus_terms or []:
        index = lowered.find(term.lower())
        if index < 0:
            continue
        radius = max(char_limit // 2, 40)
        start = max(index - radius, 0)
        end = min(index + radius, len(stripped))
        snippet = stripped[start:end].strip()
        if start > 0:
            snippet = "...\n" + snippet
        if end < len(stripped):
            snippet = snippet + "\n..."
        return snippet
    head = stripped[: char_limit // 2]
    tail = stripped[-(char_limit // 2) :]
    return head.rstrip() + "\n...\n" + tail.lstrip()


def compact_python_block(text: str, *, char_limit: int, focus_terms: list[str] | None = None) -> str:
    stripped = text.strip()
    if len(stripped) <= char_limit:
        return stripped
    lines = stripped.splitlines()
    if not lines:
        return stripped
    header = lines[0].rstrip()
    body = "\n".join(lines[1:]).strip()
    if not body:
        return header
    body_lines = body.splitlines()
    lowered_lines = [line.lower() for line in body_lines]
    for term in focus_terms or []:
        target = term.lower()
        focus_index = next((index for index, line in enumerate(lowered_lines) if target in line), None)
        if focus_index is None:
            continue
        start = max(focus_index - 1, 0)
        end = min(focus_index + 8, len(body_lines))
        if "return {" in lowered_lines[focus_index]:
            start = focus_index
            brace_balance = body_lines[focus_index].count("{") - body_lines[focus_index].count("}")
            end = focus_index + 1
            while end < len(body_lines) and brace_balance > 0 and end < focus_index + 20:
                brace_balance += body_lines[end].count("{") - body_lines[end].count("}")
                end += 1
        snippet = "\n".join(body_lines[start:end]).strip()
        if snippet:
            if start > 0:
                snippet = "...\n" + snippet
            if end < len(body_lines):
                snippet = snippet + "\n..."
            compacted = header + "\n" + snippet
            if len(compacted) <= char_limit:
                return compacted
    body_limit = max(char_limit - len(header) - 1, 80)
    compacted_body = compact_excerpt(body, char_limit=body_limit, focus_terms=focus_terms)
    return header + "\n" + compacted_body


def markdown_heading_hints_from_goal(goal: str) -> list[str]:
    hints: list[str] = []
    goal_lower = goal.lower()
    for match in re.finditer(r"([A-Za-z][A-Za-z0-9 /&_-]{2,}?)\s+section", goal, flags=re.IGNORECASE):
        hint = re.sub(r"\s+", " ", match.group(1).strip().lower())
        if hint and hint not in hints:
            hints.append(hint)
    if "build" in goal_lower and "validate" in goal_lower and "build and validate" not in hints:
        hints.append("build and validate")
    return hints


def extract_markdown_section_excerpt(text: str, *, goal: str, char_limit: int) -> str | None:
    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if match is None:
            continue
        headings.append((index, len(match.group(1)), match.group(2).strip()))
    if not headings:
        return None

    hints = markdown_heading_hints_from_goal(goal)
    if not hints:
        return None

    for hint in hints:
        hint_terms = [term for term in re.split(r"[^a-z0-9]+", hint) if term]
        for position, (start_index, level, heading_text) in enumerate(headings):
            normalized_heading = heading_text.lower()
            if hint not in normalized_heading and not all(term in normalized_heading for term in hint_terms):
                continue
            end_index = len(lines)
            for next_index, next_level, _next_heading_text in headings[position + 1 :]:
                if next_level <= level:
                    end_index = next_index
                    break
            section_text = "\n".join(lines[start_index:end_index]).strip()
            if not section_text:
                continue
            return compact_excerpt(section_text, char_limit=char_limit, focus_terms=hint_terms)
    return None


def build_target_selection_prompt(
    *,
    request: dict[str, Any],
    playbook_id: str,
    candidate_files: list[str],
    advisory_context: dict[str, Any],
    failure_context: list[str],
) -> str:
    playbook_summary = advisory_context.get("playbook") or {}
    failure_block = "\n".join(f"- {item}" for item in failure_context) if failure_context else "- none"
    candidates_block = "\n".join(f"- {item}" for item in candidate_files)
    return textwrap.dedent(
        f"""\
        Governed execution target selection.
        Choose exactly one existing file from the approved candidate list.
        Return JSON only in this shape:
        {{"target_file":"relative/path/from/list"}}

        Goal:
        {request["goal"]}

        Playbook:
        - {playbook_id}
        - title: {playbook_summary.get("title") or playbook_summary.get("name") or "unknown"}
        - summary: {playbook_summary.get("summary") or playbook_summary.get("description") or "n/a"}

        Candidate files:
        {candidates_block}

        Recent failure context:
        {failure_block}
        """
    ).rstrip() + "\n"


def build_edit_spec_prompt(
    *,
    request: dict[str, Any],
    playbook_id: str,
    target_file: str,
    target_text: str,
    failure_context: list[str],
) -> str:
    failure_block = "\n".join(f"- {item}" for item in failure_context) if failure_context else "- none"
    excerpt_char_limit = 1200 if target_file.endswith((".py", ".sh", ".json", ".yaml", ".yml")) else 1800
    excerpt = None
    related_excerpts: list[str] = []
    goal_lower = request["goal"].lower()
    request_lineage_goal = any(
        marker in goal_lower for marker in ("latest_operator_action", "request lineage", "request_path")
    )
    build_router_noop_goal = target_file.endswith("build_router.py") and any(
        marker in goal_lower
        for marker in (
            "no-op rebuild",
            "git-stable",
            "semantically unchanged",
            "on-disk json or jsonl",
            "editing generated files directly",
        )
    )
    extra_requirements: list[str] = []
    if target_file.endswith(".py"):
        logic_focus_terms = focus_terms_from_goal(request["goal"], target_file=target_file)
        if build_router_noop_goal:
            extra_requirements.append(
                "- for `build_router.py` no-op rebuild goals, change the existing `main()` write loop instead of the import block, comments, or docstrings"
            )
            extra_requirements.append(
                "- prefer changing the `for filename, payload in outputs.items():` write loop after the `if args.check` branch; do not return a proposal that only rewrites the verification branch"
            )
            extra_requirements.append(
                "- the edit must add real write-loop logic such as reading existing file content, comparing parsed payloads, or skipping a write when semantic content already matches"
            )
            extra_requirements.append(
                "- prefer one `exact_replace` that replaces the whole current write loop block from `for filename, payload in outputs.items():` through `print(f\"[ok] wrote ...\")`; do not use `anchored_replace` when that block is already unique"
            )
            extra_requirements.append(
                "- preserve the existing on-disk JSON or JSONL text when parsing that file yields the same payload as the freshly built output"
            )
            extra_requirements.append(
                "- do not edit generated files directly; keep the fix inside `scripts/build_router.py`"
            )
            extra_requirements.append(
                "- do not change `--check` semantics or generated payload meaning; only avoid formatting-only rewrites on semantic no-op rebuilds"
            )
            extra_requirements.append(
                "- do not add explanatory comments; return only executable write-loop logic"
            )
            main_block = extract_python_named_block(target_text, symbol="main")
            if main_block is not None:
                excerpt = compact_python_block(
                    main_block,
                    char_limit=min(excerpt_char_limit, 700),
                    focus_terms=[
                        "for filename, payload",
                        "path.write_text",
                        "render_output_text",
                        "args.check",
                        "generated_dir",
                    ],
                )
            render_output_block = extract_python_named_block(target_text, symbol="render_output_text")
            if render_output_block is not None:
                related_excerpts.append(
                    compact_python_block(
                        render_output_block,
                        char_limit=320,
                        focus_terms=["jsonl", "json.dumps", "sort_keys"],
                    )
                )
            validate_generated_block = extract_python_named_block(
                target_text,
                symbol="validate_generated_dir_matches_outputs",
            )
            if validate_generated_block is not None:
                related_excerpts.append(
                    compact_python_block(
                        validate_generated_block,
                        char_limit=420,
                        focus_terms=["actual_payload", "payload", "mismatches", "stale generated output"],
                    )
                )
        if request_lineage_goal or "recommended_action" in goal_lower:
            logic_focus_terms = [
                "blocked_runs",
                "latest_blocked",
                "recommended_action",
                "triage_summary",
                "blocked_run_count",
                "request_path",
            ] + logic_focus_terms
        if request_lineage_goal:
            extra_requirements.append(
                "- for request-lineage or latest-operator-action goals, prefer changing `list_runs` aggregation first; only extend `build_run_record` when the same patch immediately consumes that new field inside `list_runs`"
            )
            extra_requirements.append(
                "- each governed run state already records `request_path`; prefer a single localized change inside `list_runs` that reads the existing state field instead of adding a helper-only field elsewhere"
            )
            extra_requirements.append(
                "- `operator_triage.latest_operator_action` is rendered through the existing `triage_summary[\"recommended_action\"]` path here; do not reference a separate `operator_triage` field or introduce a standalone `latest_operator_action` local"
            )
            extra_requirements.append(
                '- preserve the current `triage_summary` dict shape; do not add a sibling `"latest_operator_action"` key here'
            )
            extra_requirements.append(
                '- prefer changing the upstream `blocked_runs` / `latest_blocked` lineage selection so the existing `"recommended_action": (` block reads the correct freshest lineage'
            )
            extra_requirements.append(
                '- do not change only the fallback string or return a no-op edit; materially change which run becomes `latest_blocked`'
            )
            extra_requirements.append(
                '- do not sort by the raw `request_path` string; derive a lineage key from the request filename and strip any `-retry<number>` suffix before comparing runs'
            )
            extra_requirements.append(
                '- keep the freshest run by `updated_at` within each request lineage first, then choose `latest_blocked` from those lineage representatives'
            )
            extra_requirements.append(
                '- when a fresher run in the same lineage is running or completed, derive `blocked_runs` from `freshest_runs_by_request_lineage(runs)` before `latest_blocked`; do not keep older blocked retries in the active blocked set'
            )
            extra_requirements.append(
                '- do not submit a no-op replacement of the existing `"recommended_action": (` block; change which runs flow into `blocked_runs` or `latest_blocked`, then let the current consumer read that fresher lineage'
            )
            extra_requirements.append(
                '- do not call `freshest_runs_by_request_lineage()` on `blocked_runs` or `latest_blocked` again; introduce a fresh lineage list from full `runs` first, then filter that fresher list for operator-action runs'
            )
            extra_requirements.append(
                '- prefer one compact `exact_replace` that swaps the current two-line `blocked_runs` / `latest_blocked` block for exactly three short lines: freshest lineage list, filtered blocked runs, then `latest_blocked = blocked_runs[:1]`'
            )
            extra_requirements.append(
                '- the first replacement line should be `freshest_runs = freshest_runs_by_request_lineage(runs)`; do not start by filtering operator-action runs into `lineage_candidates` or any other pre-filtered list'
            )
            extra_requirements.append(
                '- after that first line, filter `blocked_runs` from `freshest_runs`, then set `latest_blocked = blocked_runs[:1]`'
            )
            lineage_helper_block = extract_python_named_block(target_text, symbol="request_lineage_key")
            if lineage_helper_block is not None:
                related_excerpts.append(
                    compact_python_block(
                        lineage_helper_block,
                        char_limit=260,
                        focus_terms=["request_path", "retry", "return"],
                    )
                )
            freshest_helper_block = extract_python_named_block(target_text, symbol="freshest_runs_by_request_lineage")
            if freshest_helper_block is not None:
                related_excerpts.append(
                    compact_python_block(
                        freshest_helper_block,
                        char_limit=380,
                        focus_terms=["representatives", "request_path", "updated_at", "return sorted"],
                    )
                )
        if excerpt is None:
            excerpt = extract_python_symbol_excerpt(
                target_text,
                goal=request["goal"],
                char_limit=min(excerpt_char_limit, 650),
                focus_terms=logic_focus_terms,
            )
        if any(marker in goal_lower for marker in ("request lineage", "request_path")) and "list_runs" not in goal_lower:
            build_run_record_block = extract_python_named_block(target_text, symbol="build_run_record")
            if build_run_record_block is not None:
                related_excerpts.append(
                    compact_python_block(
                        build_run_record_block,
                        char_limit=420,
                        focus_terms=['"request_path"', 'return {', '"run_id"', '"updated_at"'],
                    )
                )
    elif target_file.endswith(".md"):
        excerpt = extract_markdown_section_excerpt(
            target_text,
            goal=request["goal"],
            char_limit=min(excerpt_char_limit, 900),
        )
        if markdown_heading_hints_from_goal(request["goal"]):
            extra_requirements.append(
                "- when the goal names a documentation section, edit inside that named section instead of changing unrelated earlier prose"
            )
    if excerpt is None:
        excerpt = compact_excerpt(
            target_text,
            char_limit=excerpt_char_limit,
            focus_terms=focus_terms_from_goal(request["goal"], target_file=target_file),
        )
    related_excerpt_block = ""
    if related_excerpts:
        related_excerpt_text = "\n\n---\n\n".join(related_excerpts)
        related_excerpt_block = (
            "\n\nRelevant helper excerpt:\n"
            "```text\n"
            f"{related_excerpt_text}\n"
            "```"
        )
    extra_requirements_block = ""
    if extra_requirements:
        extra_requirements_block = "\n" + "\n".join(extra_requirements)
    if build_router_noop_goal:
        failure_block_compact = failure_block if failure_block != "- none" else "none"
        helper_excerpt_block = ""
        if related_excerpts:
            helper_excerpt_text = "\n\n---\n\n".join(related_excerpts)
            helper_excerpt_block = (
                "\n\nHelper excerpts:\n"
                "```text\n"
                f"{helper_excerpt_text}\n"
                "```"
            )
        return textwrap.dedent(
            f"""\
            Governed execution bounded edit proposal.
            Return JSON only. Work on exactly one existing file: `{target_file}`.

            Allowed response shapes:
            {{"mode":"exact_replace","target_file":"{target_file}","old_text":"...","new_text":"..."}}
            {{"mode":"anchored_replace","target_file":"{target_file}","anchor_before":"...","old_text":"...","new_text":"...","anchor_after":"..."}}

            Requirements:
            - prefer one compact edit inside `main()`
            - do not touch imports, comments, docstrings, or generated files
            - preserve the existing on-disk JSON or JSONL text when parsing that file yields the same payload as the freshly built output
            - keep `--check` behavior and generated payload meaning unchanged
            - if the existing parsed payload differs, keep writing the freshly built canonical text
            - no comment-only or placeholder changes

            Goal:
            {request["goal"]}

            Recent failure context:
            {failure_block_compact}

            Current `main()` excerpt:
            ```text
            {excerpt}
            ```{helper_excerpt_block}
            """
        ).rstrip() + "\n"
    return textwrap.dedent(
        f"""\
        Governed execution bounded edit proposal.
        Work on exactly one existing file and return JSON only.

        Allowed response shapes:
        {{"mode":"exact_replace","target_file":"{target_file}","old_text":"...","new_text":"..."}}
        {{"mode":"anchored_replace","target_file":"{target_file}","anchor_before":"...","old_text":"...","new_text":"...","anchor_after":"..."}}

        Requirements:
        - choose a uniquely applicable edit
        - do not create files
        - do not rename files
        - do not widen scope outside `{target_file}`
        - prefer the smallest safe edit
        - `old_text` and `new_text` must be plain JSON strings, not arrays or objects
        - prefer editing a single sentence, list item, or short paragraph rather than a whole section
        - keep `old_text` and `new_text` under 240 characters each whenever possible
        - keep `anchor_before` and `anchor_after` under 160 characters each whenever possible
        - never copy an entire section into `anchor_before` or `anchor_after`
        - prefer `exact_replace` when `old_text` is uniquely applicable by itself
        - for `anchored_replace`, `old_text` must describe only the text between `anchor_before` and `anchor_after`
        - do not repeat `anchor_before` or `anchor_after` inside `old_text`
        - for code files, prefer replacing a complete statement or compact block, not a bare assignment prefix
        - do not invent new dict keys or field names that are absent from the excerpt unless the goal explicitly requires them
        - the edit must be self-contained; do not add placeholder setup or scaffolding for a later edit
        - do not introduce a new local variable unless the same change also uses it to satisfy the goal
        - when the goal names a function or status field, change the logic that computes that behavior rather than adding unused state
        {extra_requirements_block}

        Goal:
        {request["goal"]}

        Playbook:
        - {playbook_id}

        Recent failure context:
        {failure_block}

        Current file content:
        ```text
        {excerpt}
        ```
        {related_excerpt_block}
        """
    ).rstrip() + "\n"


def run_federated_prompt(prompt: str, request: dict[str, Any], *, max_tokens: int = 700) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_text": prompt,
        "temperature": 0.0,
        "max_tokens": max_tokens,
        "profile_class": request["profile_class"],
    }
    if request.get("playbook_id"):
        payload["playbook_id"] = request["playbook_id"]
    if request.get("playbook_select"):
        payload["playbook_select"] = request["playbook_select"]
    if request.get("memo") is not None:
        payload["memo"] = request["memo"]
    return http_post_json(f"{LANGCHAIN_API_BASE_URL}/run/federated", payload, timeout_s=180.0)


def try_salvage_json_block(block: str) -> str | None:
    candidate = block.strip()
    if not candidate:
        return None
    first_object = candidate.find("{")
    first_array = candidate.find("[")
    starts = [index for index in (first_object, first_array) if index >= 0]
    if starts:
        candidate = candidate[min(starts) :]
    if not candidate or candidate[0] not in "{[":
        return None
    opener_to_closer = {"{": "}", "[": "]"}
    stack: list[str] = [opener_to_closer[candidate[0]]]
    in_string = False
    escape = False
    for char in candidate[1:]:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == "\"":
                in_string = False
            continue
        if char == "\"":
            in_string = True
        elif char in opener_to_closer:
            stack.append(opener_to_closer[char])
        elif char in "}]" and stack and char == stack[-1]:
            stack.pop()
    salvaged = candidate.rstrip()
    if in_string:
        if salvaged.endswith("\\"):
            salvaged = salvaged[:-1]
        salvaged += "\""
    if stack:
        salvaged += "".join(reversed(stack))
    if salvaged == candidate:
        return None
    try:
        json.loads(salvaged)
    except json.JSONDecodeError:
        return None
    return salvaged


def parse_json_answer_block(answer_text: str) -> Any:
    block = TRIALS.extract_json_block(answer_text)
    try:
        return json.loads(block)
    except json.JSONDecodeError:
        salvaged = try_salvage_json_block(block)
        if salvaged is None:
            raise
        return json.loads(salvaged)


def coerce_text_like_field(value: Any, *, field_name: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return "".join(value)
    if isinstance(value, dict):
        for key in ("text", "value", "content", "replacement"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
        lines = value.get("lines")
        if isinstance(lines, list) and lines and all(isinstance(item, str) for item in lines):
            return "\n".join(lines)
    raise RuntimeError(f"proposal {field_name} must be a string")


def is_build_router_noop_goal(
    *,
    target_id: str | None,
    selected_target_file: str,
    goal: str,
) -> bool:
    if target_id is not None and target_id != "aoa-routing":
        return False
    if not selected_target_file.endswith("build_router.py"):
        return False
    goal_lower = goal.lower()
    return any(marker in goal_lower for marker in BUILD_ROUTER_NOOP_GOAL_MARKERS)


def is_routing_roadmap_generated_surface_goal(
    *,
    target_id: str | None,
    selected_target_file: str,
    goal: str,
) -> bool:
    if target_id is not None and target_id != "aoa-routing":
        return False
    if selected_target_file != "ROADMAP.md":
        return False
    goal_lower = goal.lower()
    return all(marker in goal_lower for marker in ROUTING_ROADMAP_GENERATED_SURFACE_GOAL_MARKERS)


def normalize_block_shape(text: str) -> str:
    return "\n".join(line.lstrip().rstrip() for line in text.strip().splitlines() if line.strip())


def extract_build_router_write_loop_block(target_text: str) -> str | None:
    lines = target_text.splitlines()
    start_indexes = [
        index for index, line in enumerate(lines) if line.lstrip() == BUILD_ROUTER_WRITE_LOOP_START
    ]
    if not start_indexes:
        return None
    end_indexes = [index for index, line in enumerate(lines) if line.lstrip() == BUILD_ROUTER_WRITE_LOOP_END]
    if len(end_indexes) != 1:
        return None
    end_index = end_indexes[0]
    candidate_starts = [index for index in start_indexes if index < end_index]
    if not candidate_starts:
        return None
    start_index = candidate_starts[-1]
    block = "\n".join(lines[start_index : end_index + 1])
    if "path.write_text(" not in block:
        return None
    return block


def strip_full_line_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines).strip("\n")


def normalize_build_router_new_text(new_text: str, *, loop_block: str) -> str:
    comment_stripped = strip_full_line_comments(new_text)
    if not comment_stripped:
        return comment_stripped
    lines = comment_stripped.splitlines()
    loop_lines = loop_block.splitlines()
    first_line_indent = loop_lines[0][: len(loop_lines[0]) - len(loop_lines[0].lstrip())]
    if lines and lines[0] and not lines[0].startswith((" ", "\t")) and first_line_indent:
        lines[0] = first_line_indent + lines[0]
    return "\n".join(lines)


def normalize_build_router_noop_raw_spec(
    spec: dict[str, Any],
    *,
    target_id: str,
    selected_target_file: str,
    goal: str,
    target_text: str,
) -> dict[str, Any]:
    if not is_build_router_noop_goal(
        target_id=target_id,
        selected_target_file=selected_target_file,
        goal=goal,
    ):
        return spec
    if not isinstance(spec, dict):
        return spec
    if str(spec.get("target_file") or "") != selected_target_file:
        return spec
    loop_block = extract_build_router_write_loop_block(target_text)
    if loop_block is None:
        return spec
    try:
        old_text = coerce_text_like_field(spec.get("old_text"), field_name="old_text")
        new_text = coerce_text_like_field(spec.get("new_text"), field_name="new_text")
    except RuntimeError:
        return spec
    normalized_new_text = normalize_build_router_new_text(new_text, loop_block=loop_block)
    mode = str(spec.get("mode") or "")
    if mode == "anchored_replace":
        anchor_before = spec.get("anchor_before")
        if isinstance(anchor_before, str) and anchor_before.strip():
            if (
                normalize_block_shape(old_text) == normalize_block_shape(anchor_before)
                == normalize_block_shape(loop_block)
            ):
                return {
                    "mode": "exact_replace",
                    "target_file": selected_target_file,
                    "old_text": loop_block,
                    "new_text": normalized_new_text,
                }
    if mode == "exact_replace" and normalize_block_shape(old_text) == normalize_block_shape(loop_block):
        return {
            "mode": "exact_replace",
            "target_file": selected_target_file,
            "old_text": loop_block,
            "new_text": normalized_new_text,
        }
    normalized = dict(spec)
    normalized["old_text"] = old_text
    normalized["new_text"] = normalized_new_text
    return normalized


def synthesize_build_router_noop_spec(
    *,
    selected_target_file: str,
    target_text: str,
) -> dict[str, Any]:
    loop_block = extract_build_router_write_loop_block(target_text)
    if loop_block is None:
        raise RuntimeError("could not locate the unique build_router write loop block")
    loop_lines = loop_block.splitlines()
    if len(loop_lines) < 4:
        raise RuntimeError("build_router write loop block is unexpectedly short")
    loop_indent = loop_lines[0][: len(loop_lines[0]) - len(loop_lines[0].lstrip())]
    body_indent = loop_lines[1][: len(loop_lines[1]) - len(loop_lines[1].lstrip())]
    nested_indent = body_indent + "    "
    deeper_indent = nested_indent + "    "
    new_text = "\n".join(
        [
            f"{loop_indent}for filename, payload in outputs.items():",
            f"{body_indent}path = generated_dir / filename",
            f"{body_indent}rendered_text = render_output_text(filename, payload)",
            f"{body_indent}if path.exists():",
            f"{nested_indent}try:",
            f"{deeper_indent}actual_text = path.read_text(encoding=\"utf-8\")",
            f"{deeper_indent}if filename.endswith(\".jsonl\"):",
            f"{deeper_indent}    actual_payload = [",
            f"{deeper_indent}        json.loads(line)",
            f"{deeper_indent}        for line in actual_text.splitlines()",
            f"{deeper_indent}        if line.strip()",
            f"{deeper_indent}    ]",
            f"{deeper_indent}else:",
            f"{deeper_indent}    actual_payload = json.loads(actual_text)",
            f"{deeper_indent}if actual_payload == payload:",
            f"{deeper_indent}    continue",
            f"{nested_indent}except json.JSONDecodeError:",
            f"{deeper_indent}pass",
            f"{body_indent}path.write_text(rendered_text, encoding=\"utf-8\", newline=\"\\n\")",
            f"{body_indent}print(f\"[ok] wrote {{relative_posix(path)}}\")",
        ]
    )
    spec = {
        "mode": "exact_replace",
        "target_file": selected_target_file,
        "old_text": loop_block,
        "new_text": new_text,
    }
    validate_build_router_noop_spec(spec)
    validate_edit_spec_candidate(
        target_text,
        selected_target_file=selected_target_file,
        spec=spec,
    )
    return spec


def synthesize_routing_roadmap_generated_surface_spec(
    *,
    selected_target_file: str,
    target_text: str,
) -> dict[str, Any]:
    old_text = "- schema-backed validation that orientation never points authority at route-owned generated surfaces"
    new_text = (
        old_text
        + "\n- router-owned generated-surface refresh stays a parity-maintenance lane for routing-owned outputs and must not transfer source authority from sibling repos"
    )
    spec = {
        "mode": "exact_replace",
        "target_file": selected_target_file,
        "old_text": old_text,
        "new_text": new_text,
    }
    validate_edit_spec_candidate(
        target_text,
        selected_target_file=selected_target_file,
        spec=spec,
    )
    return spec


def normalize_edit_spec(spec: dict[str, Any], *, selected_target_file: str) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise RuntimeError("proposal spec must be an object")
    mode = spec.get("mode")
    if mode not in {"exact_replace", "anchored_replace"}:
        raise RuntimeError("proposal mode must be exact_replace or anchored_replace")
    target_file = spec.get("target_file")
    if not isinstance(target_file, str) or target_file != selected_target_file:
        raise RuntimeError("proposal target_file must match the selected target file")
    old_text = coerce_text_like_field(spec.get("old_text"), field_name="old_text")
    new_text = coerce_text_like_field(spec.get("new_text"), field_name="new_text")
    if not old_text:
        raise RuntimeError("proposal old_text must be a non-empty string")
    if old_text == new_text:
        raise RuntimeError("proposal old_text and new_text must differ")
    if selected_target_file.endswith(".py") and "\n" not in old_text and old_text.rstrip().endswith(("=", ":", ",")):
        raise RuntimeError("proposal old_text must not be a partial Python statement")
    payload = {
        "mode": mode,
        "target_file": selected_target_file,
        "old_text": old_text,
        "new_text": new_text,
    }
    if mode == "anchored_replace":
        anchor_before = spec.get("anchor_before")
        anchor_after = spec.get("anchor_after")
        if not isinstance(anchor_before, str) or not anchor_before or not isinstance(anchor_after, str) or not anchor_after:
            payload["mode"] = "exact_replace"
            return payload
        old_text_stripped = old_text.strip()
        markdown_like_target = selected_target_file.endswith(".md")
        if markdown_like_target and old_text_stripped == anchor_before.strip() and new_text.startswith(old_text):
            payload["mode"] = "exact_replace"
            return payload
        if markdown_like_target and old_text_stripped == anchor_after.strip() and new_text.endswith(old_text):
            payload["mode"] = "exact_replace"
            return payload
        if old_text_stripped == anchor_before.strip() or old_text_stripped == anchor_after.strip():
            raise RuntimeError("proposal old_text must not duplicate anchored context")
        payload["anchor_before"] = anchor_before
        payload["anchor_after"] = anchor_after
    return payload


def build_candidate_text(original_text: str, *, selected_target_file: str, spec: dict[str, Any]) -> str:
    mode = spec["mode"]
    if mode == "exact_replace":
        match_count, candidate_text = TRIALS.apply_exact_replace_to_text(
            original_text,
            old_text=spec["old_text"],
            new_text=spec["new_text"],
        )
    else:
        match_count, candidate_text = TRIALS.apply_anchored_replace_to_text(
            original_text,
            anchor_before=spec["anchor_before"],
            old_text=spec["old_text"],
            new_text=spec["new_text"],
            anchor_after=spec["anchor_after"],
        )
        if match_count != 1 or candidate_text is None:
            exact_match_count, exact_candidate_text = TRIALS.apply_exact_replace_to_text(
                original_text,
                old_text=spec["old_text"],
                new_text=spec["new_text"],
            )
            if exact_match_count == 1 and exact_candidate_text is not None:
                match_count = exact_match_count
                candidate_text = exact_candidate_text
                mode = "exact_replace"
    if match_count != 1 or candidate_text is None:
        raise RuntimeError(f"{mode} was not uniquely applicable to {selected_target_file}")
    return candidate_text


def validate_edit_spec_candidate(target_text: str, *, selected_target_file: str, spec: dict[str, Any]) -> str:
    candidate_text = build_candidate_text(
        target_text,
        selected_target_file=selected_target_file,
        spec=spec,
    )
    if selected_target_file.endswith(".py"):
        try:
            parsed_candidate = ast.parse(candidate_text)
        except SyntaxError as exc:
            raise RuntimeError("proposal would produce invalid Python syntax") from exc
        load_counts: dict[str, int] = {}
        for node in ast.walk(parsed_candidate):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                load_counts[node.id] = load_counts.get(node.id, 0) + 1
        introduced_assignments = re.findall(
            r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^\n=]+)?\s*=",
            spec.get("new_text") or "",
        )
        for name in introduced_assignments:
            if load_counts.get(name, 0) == 0:
                raise RuntimeError("proposal introduces unused Python assignment")
    return candidate_text


def validate_build_router_noop_spec(spec: dict[str, Any]) -> None:
    old_text = str(spec.get("old_text") or "")
    new_text = str(spec.get("new_text") or "")
    combined = old_text + "\n" + new_text
    if any(line.lstrip().startswith("#") for line in new_text.splitlines()):
        raise RuntimeError("proposal must not add explanatory comments to the build_router write loop")
    if "if args.check" in combined and BUILD_ROUTER_WRITE_LOOP_START not in combined:
        raise RuntimeError("proposal must change the build_router write loop")
    if BUILD_ROUTER_WRITE_LOOP_START not in combined or "path.write_text(" not in combined:
        raise RuntimeError("proposal must change the build_router write loop")
    if "path.exists()" not in new_text or "path.read_text(" not in new_text:
        raise RuntimeError("proposal must read existing output only when the file already exists")
    if 'filename.endswith(".jsonl")' not in new_text or "splitlines()" not in new_text or "json.loads(" not in new_text:
        raise RuntimeError("proposal must parse both JSON and JSONL output payloads before comparing")
    if not re.search(r"\b[A-Za-z_][A-Za-z0-9_]*_payload\s*==\s*payload\b", new_text):
        raise RuntimeError("proposal must compare parsed on-disk payloads against the freshly built payload")
    if "continue" not in new_text:
        raise RuntimeError("proposal must skip the write only for semantic no-op payload matches")
    if "json.JSONDecodeError" not in new_text:
        raise RuntimeError("proposal must preserve canonical writes when existing output is invalid")
    if "path.write_text(" not in new_text or "render_output_text(" not in new_text:
        raise RuntimeError("proposal must preserve the canonical write path")


def default_proposal_provider(context: dict[str, Any]) -> dict[str, Any]:
    run_dir = context.get("run_dir")
    fixture_path = os.environ.get("AOA_GOVERNED_EXECUTION_PROPOSAL_PATH")
    if fixture_path:
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("fixture proposal payload must be an object")
        selected_target_file = str(payload.get("selected_target_file") or payload.get("target_file") or "")
        target_text = ""
        if selected_target_file:
            candidate_path = context["repo_root"] / selected_target_file
            if candidate_path.exists():
                target_text = candidate_path.read_text(encoding="utf-8")
        raw_spec = payload.get("spec") or payload
        raw_spec = normalize_build_router_noop_raw_spec(
            raw_spec,
            target_id=str(context["request"].get("target_id") or ""),
            selected_target_file=selected_target_file,
            goal=str(context["request"].get("goal") or ""),
            target_text=target_text,
        )
        spec = normalize_edit_spec(
            raw_spec,
            selected_target_file=selected_target_file,
        )
        if is_build_router_noop_goal(
            target_id=str(context["request"].get("target_id") or ""),
            selected_target_file=selected_target_file,
            goal=str(context["request"].get("goal") or ""),
        ):
            validate_build_router_noop_spec(spec)
        return {
            "provider": "fixture",
            "selected_target_file": selected_target_file,
            "spec": spec,
            "candidate_files": [selected_target_file],
            "target_prompt": "",
            "edit_prompt": "",
            "target_answer": json.dumps({"target_file": selected_target_file}, ensure_ascii=True),
            "edit_answer": json.dumps(spec, ensure_ascii=True),
            "notes": ["Loaded proposal from AOA_GOVERNED_EXECUTION_PROPOSAL_PATH."],
        }

    candidate_files = enumerate_allowed_candidates(context["repo_root"], context["allowed_files"])
    if not candidate_files:
        raise RuntimeError("no candidate files matched the governed execution allowlist")
    prompt_candidates = narrow_candidate_files(candidate_files, goal=context["request"]["goal"])

    if len(prompt_candidates) == 1:
        selected_target_file = prompt_candidates[0]
        target_prompt = ""
        target_answer = json.dumps({"target_file": selected_target_file}, ensure_ascii=True)
    else:
        target_prompt = build_target_selection_prompt(
            request=context["request"],
            playbook_id=context["playbook_id"],
            candidate_files=prompt_candidates,
            advisory_context=context["advisory_context"],
            failure_context=context.get("failure_context") or [],
        )
        target_response = run_federated_prompt(target_prompt, context["request"], max_tokens=160)
        target_answer = str(target_response.get("answer") or "")
        persist_proposal_attempt_artifacts(
            run_dir,
            kind="target",
            attempt=0,
            prompt=target_prompt,
            response=target_answer,
        )
        selected_payload = parse_json_answer_block(target_answer)
        if not isinstance(selected_payload, dict):
            raise RuntimeError("target selection response did not contain a JSON object")
        selected_target_file = str(selected_payload.get("target_file") or "")
        if selected_target_file not in candidate_files:
            raise RuntimeError("target selection chose a file outside the governed allowlist")

    target_text = (context["repo_root"] / selected_target_file).read_text(encoding="utf-8")
    build_router_noop_goal = is_build_router_noop_goal(
        target_id=str(context["request"].get("target_id") or ""),
        selected_target_file=selected_target_file,
        goal=str(context["request"].get("goal") or ""),
    )
    routing_roadmap_generated_surface_goal = is_routing_roadmap_generated_surface_goal(
        target_id=str(context["request"].get("target_id") or ""),
        selected_target_file=selected_target_file,
        goal=str(context["request"].get("goal") or ""),
    )
    if build_router_noop_goal:
        spec = synthesize_build_router_noop_spec(
            selected_target_file=selected_target_file,
            target_text=target_text,
        )
        return {
            "provider": "deterministic-build-router-noop",
            "selected_target_file": selected_target_file,
            "spec": spec,
            "candidate_files": prompt_candidates,
            "target_prompt": target_prompt,
            "edit_prompt": "",
            "target_answer": target_answer,
            "edit_answer": json.dumps(spec, ensure_ascii=True),
            "notes": [
                "Target candidate count: "
                + str(len(prompt_candidates))
                + ".",
                "Synthesized deterministic build_router no-op write-loop patch.",
            ],
        }
    if routing_roadmap_generated_surface_goal:
        spec = synthesize_routing_roadmap_generated_surface_spec(
            selected_target_file=selected_target_file,
            target_text=target_text,
        )
        return {
            "provider": "deterministic-routing-roadmap-generated-surface",
            "selected_target_file": selected_target_file,
            "spec": spec,
            "candidate_files": prompt_candidates,
            "target_prompt": target_prompt,
            "edit_prompt": "",
            "target_answer": target_answer,
            "edit_answer": json.dumps(spec, ensure_ascii=True),
            "notes": [
                "Target candidate count: "
                + str(len(prompt_candidates))
                + ".",
                "Synthesized deterministic aoa-routing ROADMAP generated-surface boundary wording patch.",
            ],
        }
    edit_failure_context = list(context.get("failure_context") or [])
    edit_prompt = ""
    edit_answer = ""
    last_error: Exception | None = None
    edit_attempts = 0
    for edit_attempt in range(2):
        edit_attempts = edit_attempt + 1
        attempt_failure_context = list(edit_failure_context)
        if last_error is not None:
            attempt_failure_context.append(
                "Previous edit proposal failed: "
                + str(last_error)
                + ". Retry with the smallest safe exact_replace or very short anchors; do not omit new_text."
            )
        edit_prompt = build_edit_spec_prompt(
            request=context["request"],
            playbook_id=context["playbook_id"],
            target_file=selected_target_file,
            target_text=target_text,
            failure_context=attempt_failure_context,
        )
        request_goal_lower = str(context["request"].get("goal") or "").lower()
        request_lineage_goal = any(
            marker in request_goal_lower for marker in ("latest_operator_action", "request lineage", "request_path")
        )
        edit_max_tokens = 180 if selected_target_file.endswith(".py") else 220
        if build_router_noop_goal:
            edit_max_tokens = 320
        if selected_target_file.endswith(".py") and request_lineage_goal:
            edit_max_tokens = 260
        edit_response = run_federated_prompt(edit_prompt, context["request"], max_tokens=edit_max_tokens)
        edit_answer = str(edit_response.get("answer") or "")
        persist_proposal_attempt_artifacts(
            run_dir,
            kind="edit",
            attempt=edit_attempt,
            prompt=edit_prompt,
            response=edit_answer,
        )
        try:
            parsed_spec = parse_json_answer_block(edit_answer)
            parsed_spec = normalize_build_router_noop_raw_spec(
                parsed_spec,
                target_id=str(context["request"].get("target_id") or ""),
                selected_target_file=selected_target_file,
                goal=str(context["request"].get("goal") or ""),
                target_text=target_text,
            )
            spec = normalize_edit_spec(parsed_spec, selected_target_file=selected_target_file)
            if build_router_noop_goal:
                validate_build_router_noop_spec(spec)
            validate_edit_spec_candidate(
                target_text,
                selected_target_file=selected_target_file,
                spec=spec,
            )
            break
        except Exception as exc:
            persist_proposal_attempt_artifacts(
                run_dir,
                kind="edit",
                attempt=edit_attempt,
                prompt=edit_prompt,
                response=edit_answer,
                error=f"{type(exc).__name__}: {exc}",
            )
            last_error = exc
    else:
        assert last_error is not None
        raise last_error
    return {
        "provider": "langchain-api",
        "selected_target_file": selected_target_file,
        "spec": spec,
        "candidate_files": prompt_candidates,
        "target_prompt": target_prompt,
        "edit_prompt": edit_prompt,
        "target_answer": target_answer,
        "edit_answer": edit_answer,
        "notes": [
            "Proposal generated through langchain-api /run/federated.",
            f"Target candidate count: {len(prompt_candidates)}.",
            f"Edit proposal attempts: {edit_attempts}.",
        ],
    }


def approval_artifact(run_dir: Path) -> Path:
    return run_dir / "approval.status.json"


def state_artifact(run_dir: Path) -> Path:
    return run_dir / "run.state.json"


def result_artifact(run_dir: Path) -> Path:
    return run_dir / "result.summary.json"


def report_artifact(run_dir: Path) -> Path:
    return run_dir / "report.md"


def proposal_summary_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "proposal.summary.json"


def proposal_edit_spec_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "proposal.edit-spec.json"


def advisory_trace_runtime_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "advisory_trace.json"


def review_packet_manifest_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "review_packet_manifest.json"


def review_packet_audit_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "review_packet_audit.json"


def review_handoff_bundle_artifact(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "review_handoff_bundle.json"


def review_packet_inputs_dir(run_dir: Path) -> Path:
    return run_dir / "artifacts" / "review-packets" / "inputs"


def make_run_id() -> str:
    return f"{utc_now().replace(':', '').replace('-', '').lower()}-{uuid.uuid4().hex[:8]}"


def make_failure_summary(
    *,
    run_id: str,
    phase: str,
    failure_class: str,
    reasons: list[str],
    break_glass_used: bool,
    next_action: str,
) -> dict[str, Any]:
    if failure_class not in FAILURE_CLASSES:
        raise RuntimeError(f"unsupported failure class: {failure_class}")
    return {
        "artifact_kind": "aoa.governed-run.result-summary",
        "schema_version": "v1",
        "run_id": run_id,
        "updated_at": utc_now(),
        "status": "fail",
        "phase": phase,
        "failure_class": failure_class,
        "reasons": reasons,
        "break_glass_used": break_glass_used,
        "next_action": next_action,
    }


def make_paused_summary(
    *,
    run_id: str,
    phase: str,
    milestone: str,
    break_glass_used: bool,
    next_action: str,
) -> dict[str, Any]:
    return {
        "artifact_kind": "aoa.governed-run.result-summary",
        "schema_version": "v1",
        "run_id": run_id,
        "updated_at": utc_now(),
        "status": "paused",
        "phase": phase,
        "current_milestone": milestone,
        "break_glass_used": break_glass_used,
        "next_action": next_action,
    }


def make_pass_summary(
    *,
    run_id: str,
    phase: str,
    changed_files: list[str],
    break_glass_used: bool,
    next_action: str,
) -> dict[str, Any]:
    return {
        "artifact_kind": "aoa.governed-run.result-summary",
        "schema_version": "v1",
        "run_id": run_id,
        "updated_at": utc_now(),
        "status": "pass",
        "phase": phase,
        "changed_files": changed_files,
        "break_glass_used": break_glass_used,
        "next_action": next_action,
    }


def validate_approval_against_state(approval: dict[str, Any], state: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if approval.get("run_id") != state.get("run_id"):
        reasons.append("approval run_id does not match governed run state")
    if approval.get("base_head") != state.get("base_head"):
        reasons.append("approval base_head does not match governed run state")
    current_milestone = approval.get("current_milestone")
    milestones = approval.get("milestones")
    if not isinstance(milestones, dict) or current_milestone not in milestones:
        reasons.append("approval current_milestone is not declared in approval milestones")
    if approval.get("status") not in {"pending", "approved", "rejected"}:
        reasons.append("approval status must be pending, approved, or rejected")
    return reasons


def compute_triage(
    state: dict[str, Any],
    summary: dict[str, Any],
    approval: dict[str, Any] | None,
) -> dict[str, Any]:
    status = str(summary.get("status") or state.get("status") or "unknown")
    milestone = str(summary.get("current_milestone") or (approval or {}).get("current_milestone") or "")
    if status == "running":
        return {
            "terminal": False,
            "resumable": False,
            "operator_action_required": False,
            "blocked_reason": None,
            "recommended_action": str(summary.get("next_action") or "Governed execution is still running."),
            "safe_resume_command": None,
        }
    if status == "paused":
        blocked_reason = "plan_approval_required" if milestone == "plan_freeze" else "landing_approval_required"
        return {
            "terminal": False,
            "resumable": True,
            "operator_action_required": True,
            "blocked_reason": blocked_reason,
            "recommended_action": str(summary.get("next_action") or "Review approval.status.json and resume."),
            "safe_resume_command": f"scripts/aoa-governed-run resume {state['run_id']}",
        }
    if status == "fail":
        return {
            "terminal": True,
            "resumable": False,
            "operator_action_required": True,
            "blocked_reason": summary.get("failure_class") or "governed_run_failed",
            "recommended_action": str(summary.get("next_action") or "Inspect governed run artifacts before retrying."),
            "safe_resume_command": None,
        }
    if status == "pass":
        return {
            "terminal": True,
            "resumable": False,
            "operator_action_required": False,
            "blocked_reason": None,
            "recommended_action": str(summary.get("next_action") or "No further action required."),
            "safe_resume_command": None,
        }
    return {
        "terminal": False,
        "resumable": False,
        "operator_action_required": True,
        "blocked_reason": "unknown_state",
        "recommended_action": "Inspect governed run state and approval artifacts.",
        "safe_resume_command": None,
    }


def enrich_summary(run_dir: Path, summary: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    payload = copy.deepcopy(summary)
    if state is None:
        return payload
    approval = None
    approval_path = approval_artifact(run_dir)
    if approval_path.exists():
        approval = load_approval(run_dir)
    payload["canary_id"] = state.get("canary_id")
    payload["task_class"] = state.get("task_class")
    payload["trust_state_snapshot"] = state.get("trust_state_snapshot")
    payload["triage"] = compute_triage(state, payload, approval)
    return payload


def update_report(run_dir: Path, summary: dict[str, Any], state: dict[str, Any] | None = None) -> None:
    triage = summary.get("triage") or (compute_triage(state, summary, load_approval(run_dir)) if state is not None and approval_artifact(run_dir).exists() else None)
    lines = [
        f"# governed-run `{summary['run_id']}`",
        "",
        f"- status: `{summary['status']}`",
        f"- phase: `{summary.get('phase')}`",
    ]
    if state is not None:
        lines.append(f"- repo_root: `{state.get('repo_root')}`")
        lines.append(f"- playbook_id: `{state.get('playbook_id')}`")
        lines.append(f"- task_class: `{state.get('task_class')}`")
        lines.append(f"- trust_state_snapshot: `{state.get('trust_state_snapshot')}`")
        if state.get("canary_id"):
            lines.append(f"- canary_id: `{state.get('canary_id')}`")
    if summary.get("failure_class"):
        lines.append(f"- failure_class: `{summary['failure_class']}`")
    if summary.get("current_milestone"):
        lines.append(f"- milestone: `{summary['current_milestone']}`")
    lines.append(f"- break_glass_used: `{summary.get('break_glass_used', False)}`")
    changed_files = summary.get("changed_files") or []
    if changed_files:
        lines.append(f"- changed_files: `{json.dumps(changed_files, ensure_ascii=True)}`")
    review_packets = summary.get("review_packets")
    if isinstance(review_packets, dict):
        lines.append(f"- review_packet_ready: `{review_packets.get('ready')}`")
        lines.append(f"- emitted_review_packets: `{review_packets.get('emitted_candidate_artifact_count')}`")
        if review_packets.get("manifest_ref"):
            lines.append(f"- review_packet_manifest: `{review_packets.get('manifest_ref')}`")
        if review_packets.get("audit_verdict"):
            lines.append(f"- review_packet_audit_verdict: `{review_packets.get('audit_verdict')}`")
        if review_packets.get("audit_ref"):
            lines.append(f"- review_packet_audit: `{review_packets.get('audit_ref')}`")
        blocked_packet_kinds = review_packets.get("blocked_packet_kinds") or []
        if blocked_packet_kinds:
            lines.append(
                "- blocked_packet_kinds: `"
                + ", ".join(str(item) for item in blocked_packet_kinds if isinstance(item, str) and item)
                + "`"
            )
        if review_packets.get("safe_replay_command"):
            lines.append(f"- safe_replay_command: `{review_packets.get('safe_replay_command')}`")
        if review_packets.get("handoff_readiness"):
            lines.append(f"- handoff_readiness: `{review_packets.get('handoff_readiness')}`")
        if review_packets.get("handoff_ref"):
            lines.append(f"- review_handoff_bundle: `{review_packets.get('handoff_ref')}`")
    reasons = summary.get("reasons") or []
    if reasons:
        lines.extend(["", "## Reasons", ""])
        lines.extend(f"- {item}" for item in reasons)
    if isinstance(triage, dict):
        lines.extend(
            [
                "",
                "## Triage",
                "",
                f"- terminal: `{triage.get('terminal')}`",
                f"- resumable: `{triage.get('resumable')}`",
                f"- operator_action_required: `{triage.get('operator_action_required')}`",
                f"- blocked_reason: `{triage.get('blocked_reason')}`",
            ]
        )
        if triage.get("safe_resume_command"):
            lines.append(f"- safe_resume_command: `{triage['safe_resume_command']}`")
    lines.extend(["", "## Next Action", "", summary.get("next_action") or "None."])
    review_targets = (review_packets or {}).get("recommended_review_targets") if isinstance(review_packets, dict) else []
    if review_targets:
        lines.extend(["", "## Recommended Review Targets", ""])
        for item in review_targets:
            if not isinstance(item, dict):
                continue
            owner_repo = item.get("owner_repo")
            ref = item.get("ref")
            why = item.get("why")
            line = f"- {owner_repo}: `{ref}`" if owner_repo and ref else f"- `{ref or owner_repo}`"
            if why:
                line += f" ({why})"
            lines.append(line)
    grouped_targets = (review_packets or {}).get("grouped_review_targets") if isinstance(review_packets, dict) else {}
    if isinstance(grouped_targets, dict) and grouped_targets:
        lines.extend(["", "## Handoff Review Targets", ""])
        for owner_repo, refs in grouped_targets.items():
            lines.append(f"- {owner_repo}:")
            for ref_entry in refs:
                if not isinstance(ref_entry, dict):
                    continue
                line = f"  `{ref_entry.get('ref')}`"
                if ref_entry.get("why"):
                    line += f" ({ref_entry.get('why')})"
                lines.append(line)
    write_text(report_artifact(run_dir), "\n".join(lines))


def load_state(run_dir: Path) -> dict[str, Any]:
    return json.loads(state_artifact(run_dir).read_text(encoding="utf-8"))


def load_approval(run_dir: Path) -> dict[str, Any]:
    return json.loads(approval_artifact(run_dir).read_text(encoding="utf-8"))


def load_summary_or_synthesize(run_dir: Path, state: dict[str, Any], approval: dict[str, Any] | None) -> dict[str, Any]:
    summary_path = result_artifact(run_dir)
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "artifact_kind": "aoa.governed-run.result-summary",
        "schema_version": "v1",
        "run_id": state.get("run_id") or run_dir.name,
        "updated_at": state.get("updated_at"),
        "status": state.get("status") or "running",
        "phase": state.get("phase"),
        "current_milestone": (approval or {}).get("current_milestone"),
        "break_glass_used": bool(state.get("break_glass_used")),
        "next_action": "Governed execution is still running.",
        "canary_id": state.get("canary_id"),
        "task_class": state.get("task_class"),
        "trust_state_snapshot": state.get("trust_state_snapshot"),
        "triage": compute_triage(state, {"status": state.get("status") or "running"}, approval),
    }


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(state_artifact(run_dir), state)


def save_summary(run_dir: Path, summary: dict[str, Any], state: dict[str, Any] | None = None) -> None:
    payload = enrich_summary(run_dir, summary, state)
    write_json(result_artifact(run_dir), payload)
    update_report(run_dir, payload, state=state)


def initialize_approval(run_dir: Path, *, run_id: str, base_head: str) -> dict[str, Any]:
    payload = {
        "artifact_kind": "aoa.governed-run.approval-status",
        "schema_version": "v1",
        "run_id": run_id,
        "updated_at": utc_now(),
        "base_head": base_head,
        "current_milestone": "plan_freeze",
        "status": "pending",
        "approved": False,
        "milestones": {
            "plan_freeze": {
                "status": "pending",
                "approved": False,
                "updated_at": utc_now(),
                "notes": "Review proposal.summary.json and set this milestone to approved before worktree execution.",
            },
            "landing": {
                "status": "pending",
                "approved": False,
                "updated_at": utc_now(),
                "notes": "Review landing.diff and worktree.manifest.json before applying back to the main checkout.",
            },
        },
    }
    write_json(approval_artifact(run_dir), payload)
    return payload


def advance_milestone(approval: dict[str, Any], *, milestone: str, status: str, notes: str) -> dict[str, Any]:
    approval = copy.deepcopy(approval)
    approval["updated_at"] = utc_now()
    approval["current_milestone"] = milestone
    approval["status"] = status
    approval["approved"] = status == "approved"
    milestone_payload = approval["milestones"][milestone]
    milestone_payload["status"] = status
    milestone_payload["approved"] = status == "approved"
    milestone_payload["updated_at"] = utc_now()
    milestone_payload["notes"] = notes
    return approval


def ensure_policy_repo_scope(playbook_policy: dict[str, Any], repo_root: Path, *, target_id: str) -> None:
    if str(playbook_policy.get("repo_scope") or "").strip() != target_id:
        raise RuntimeError(f"playbook policy repo_scope must stay aligned with target_id={target_id}")
    if not target_checkout_detector(target_id)(repo_root):
        raise RuntimeError(f"repo_root is outside the governed target scope {target_id}: {repo_root}")


def write_proposal_artifacts(
    run_dir: Path,
    *,
    proposal_payload: dict[str, Any],
    allowed_files: list[str],
    base_head: str,
    attempt: int,
) -> dict[str, Any]:
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    attempt_label = f"a{attempt:02d}"
    if proposal_payload.get("target_prompt"):
        write_text(artifacts_dir / f"proposal.target.{attempt_label}.prompt.txt", str(proposal_payload["target_prompt"]))
    if proposal_payload.get("edit_prompt"):
        write_text(artifacts_dir / f"proposal.edit.{attempt_label}.prompt.txt", str(proposal_payload["edit_prompt"]))
    if proposal_payload.get("target_answer") is not None:
        write_text_exact(
            artifacts_dir / f"proposal.target.{attempt_label}.response.txt",
            str(proposal_payload["target_answer"]),
        )
    if proposal_payload.get("edit_answer") is not None:
        write_text_exact(
            artifacts_dir / f"proposal.edit.{attempt_label}.response.txt",
            str(proposal_payload["edit_answer"]),
        )
    edit_spec_payload = {
        "artifact_kind": "aoa.governed-run.proposal-edit-spec",
        "schema_version": "v1",
        "prepared_at": utc_now(),
        "attempt": attempt,
        "provider": proposal_payload.get("provider"),
        "selected_target_file": proposal_payload["selected_target_file"],
        "spec": proposal_payload["spec"],
        "notes": proposal_payload.get("notes") or [],
    }
    write_json(proposal_edit_spec_artifact(run_dir), edit_spec_payload)
    summary = {
        "artifact_kind": "aoa.governed-run.proposal-summary",
        "schema_version": "v1",
        "prepared_at": utc_now(),
        "attempt": attempt,
        "provider": proposal_payload.get("provider"),
        "base_head": base_head,
        "selected_target_file": proposal_payload["selected_target_file"],
        "allowed_files": allowed_files,
        "proposal_valid": True,
        "proposal_failure_reasons": [],
        "candidate_files": proposal_payload.get("candidate_files") or [],
        "notes": proposal_payload.get("notes") or [],
    }
    write_json(proposal_summary_artifact(run_dir), summary)
    return summary


def failure_result(
    run_dir: Path,
    *,
    state: dict[str, Any],
    phase: str,
    failure_class: str,
    reasons: list[str],
    next_action: str,
) -> dict[str, Any]:
    summary = make_failure_summary(
        run_id=state["run_id"],
        phase=phase,
        failure_class=failure_class,
        reasons=reasons,
        break_glass_used=bool(state.get("break_glass_used")),
        next_action=next_action,
    )
    state["phase"] = "failed"
    state["status"] = "fail"
    state["failure_class"] = failure_class
    state["failure_reasons"] = reasons
    save_state(run_dir, state)
    save_summary(run_dir, summary, state=state)
    return json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))


def paused_result(
    run_dir: Path,
    *,
    state: dict[str, Any],
    phase: str,
    milestone: str,
    next_action: str,
) -> dict[str, Any]:
    summary = make_paused_summary(
        run_id=state["run_id"],
        phase=phase,
        milestone=milestone,
        break_glass_used=bool(state.get("break_glass_used")),
        next_action=next_action,
    )
    state["phase"] = phase
    state["status"] = "paused"
    save_state(run_dir, state)
    save_summary(run_dir, summary, state=state)
    return json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))


def review_packet_eval_template_matches(
    playbook_id: str,
    playbook_contract: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hook_templates: list[dict[str, Any]] = []
    evidence_templates: list[dict[str, Any]] = []
    contract_eval_anchors = {
        anchor for anchor in playbook_contract.get("eval_anchors", []) if isinstance(anchor, str) and anchor
    }
    for entry in eval_runtime_candidate_templates():
        template_kind = entry.get("template_kind")
        if template_kind == "artifact_to_verdict_hook":
            if entry.get("playbook_id") not in (None, playbook_id):
                continue
            if contract_eval_anchors and entry.get("eval_anchor") not in contract_eval_anchors:
                continue
            hook_templates.append(entry)
        elif template_kind == "runtime_evidence_selection":
            if entry.get("playbook_id") not in (None, playbook_id):
                continue
            eval_anchor = entry.get("eval_anchor")
            if contract_eval_anchors and eval_anchor is not None and eval_anchor not in contract_eval_anchors:
                continue
            evidence_templates.append(entry)
    return hook_templates, evidence_templates


def review_packet_memo_target_matches(playbook_contract: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = {
        surface
        for surface in playbook_contract.get("memo_runtime_surfaces", [])
        if isinstance(surface, str) and surface
    }
    return [entry for entry in memo_runtime_writeback_targets() if entry.get("runtime_surface") in surfaces]


def write_review_packet_input(
    run_dir: Path,
    *,
    packet_kind: str,
    stem: str,
    payload: dict[str, Any],
) -> Path:
    path = review_packet_inputs_dir(run_dir) / packet_kind / f"{stem}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return path


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return payload


def local_ref_path(ref: Any) -> Path | None:
    if not isinstance(ref, str) or not ref.startswith("local:"):
        return None
    raw_path = ref[len("local:") :].strip()
    if not raw_path:
        return None
    return Path(raw_path).expanduser()


def stored_review_packet_trace_provider(run_dir: Path) -> Callable[[dict[str, Any]], dict[str, Any]]:
    advisory_trace_path = advisory_trace_runtime_artifact(run_dir)

    def provider(_request: dict[str, Any]) -> dict[str, Any]:
        payload = load_json_if_exists(advisory_trace_path)
        if payload is None:
            raise RuntimeError("stored_advisory_trace_unavailable")
        return payload

    return provider


def _playbook_review_packet_contract_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "playbook_id": payload.get("playbook_id"),
        "playbook_name": payload.get("playbook_name"),
        "scenario": payload.get("scenario"),
        "expected_artifacts": payload.get("expected_artifacts"),
        "eval_anchors": payload.get("eval_anchors"),
        "memo_runtime_surfaces": payload.get("memo_runtime_surfaces"),
        "candidate_packet_kinds": payload.get("candidate_packet_kinds"),
        "review_required": payload.get("review_required"),
        "source_review_refs": payload.get("source_review_refs"),
        "gate_verdict": payload.get("gate_verdict"),
    }


def _eval_runtime_template_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_kind": payload.get("template_kind"),
        "template_name": payload.get("template_name"),
        "playbook_id": payload.get("playbook_id"),
        "eval_anchor": payload.get("eval_anchor"),
        "verdict_bundle_ref": payload.get("verdict_bundle_ref"),
        "required_runtime_artifacts": payload.get("required_runtime_artifacts"),
        "review_required": payload.get("review_required"),
        "source_example_ref": payload.get("source_example_ref"),
    }


def _memo_writeback_target_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_surface": payload.get("runtime_surface"),
        "target_kind": payload.get("target_kind"),
        "writeback_class": payload.get("writeback_class"),
        "requires_human_review": payload.get("requires_human_review"),
        "review_state_default": payload.get("review_state_default"),
        "runtime_refs": payload.get("runtime_refs"),
        "notes": payload.get("notes"),
    }


def _playbook_review_intake_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "playbook_id": payload.get("playbook_id"),
        "playbook_name": payload.get("playbook_name"),
        "scenario": payload.get("scenario"),
        "gate_verdict": payload.get("gate_verdict"),
        "gate_review_ref": payload.get("gate_review_ref"),
        "real_run_template_ref": payload.get("real_run_template_ref"),
        "required_artifact_set": payload.get("required_artifact_set"),
        "accepted_packet_kinds": payload.get("accepted_packet_kinds"),
        "source_review_refs": payload.get("source_review_refs"),
        "review_outcome_targets": payload.get("review_outcome_targets"),
        "composition_posture": payload.get("composition_posture"),
    }


def _eval_runtime_candidate_intake_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_kind": payload.get("template_kind"),
        "template_name": payload.get("template_name"),
        "playbook_id": payload.get("playbook_id"),
        "eval_anchor": payload.get("eval_anchor"),
        "verdict_bundle_ref": payload.get("verdict_bundle_ref"),
        "required_runtime_artifacts": payload.get("required_runtime_artifacts"),
        "review_required": payload.get("review_required"),
        "review_guide_ref": payload.get("review_guide_ref"),
        "owner_review_refs": payload.get("owner_review_refs"),
        "candidate_acceptance_posture": payload.get("candidate_acceptance_posture"),
    }


def _memo_writeback_intake_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_surface": payload.get("runtime_surface"),
        "target_kind": payload.get("target_kind"),
        "writeback_class": payload.get("writeback_class"),
        "requires_human_review": payload.get("requires_human_review"),
        "review_state_default": payload.get("review_state_default"),
        "runtime_refs": payload.get("runtime_refs"),
        "owner_review_refs": payload.get("owner_review_refs"),
        "intake_posture": payload.get("intake_posture"),
    }


def append_review_target(
    targets: list[dict[str, str]],
    seen: set[tuple[str, str]],
    *,
    owner_repo: str,
    ref: str,
    why: str,
) -> None:
    if not ref:
        return
    key = (owner_repo, ref)
    if key in seen:
        return
    seen.add(key)
    targets.append({"owner_repo": owner_repo, "ref": ref, "why": why})


def group_review_targets_by_owner(targets: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for item in targets:
        if not isinstance(item, dict):
            continue
        owner_repo = str(item.get("owner_repo") or "").strip()
        ref = str(item.get("ref") or "").strip()
        why = str(item.get("why") or "").strip()
        if not owner_repo or not ref:
            continue
        key = (owner_repo, ref)
        if key in seen:
            continue
        seen.add(key)
        grouped.setdefault(owner_repo, []).append({"ref": ref, "why": why})
    return grouped


def review_packet_summary_with_audit(
    review_packet_status: dict[str, Any] | None,
    audit_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(review_packet_status or {})
    blocked_packet_kinds = [
        entry.get("packet_kind")
        for entry in audit_payload.get("packet_statuses", [])
        if isinstance(entry, dict) and entry.get("status") in {"missing", "stale"}
    ]
    merged.update(
        {
            "audit_verdict": audit_payload.get("audit_verdict"),
            "audit_ref": str(audit_payload.get("review_packet_audit_ref") or ""),
            "replayable": audit_payload.get("replayable"),
            "safe_replay_command": audit_payload.get("safe_replay_command"),
            "blocked_packet_kinds": [item for item in blocked_packet_kinds if isinstance(item, str)],
            "recommended_review_targets": audit_payload.get("recommended_review_targets", []),
        }
    )
    return merged


def review_packet_summary_with_handoff(
    review_packet_status: dict[str, Any] | None,
    handoff_payload: dict[str, Any],
    *,
    handoff_ref: str,
    handoff_readiness: str,
) -> dict[str, Any]:
    merged = dict(review_packet_status or {})
    grouped_review_targets = handoff_payload.get("recommended_review_targets")
    if not isinstance(grouped_review_targets, dict):
        grouped_review_targets = {}
    merged.update(
        {
            "handoff_ref": handoff_ref,
            "handoff_readiness": handoff_readiness,
            "grouped_review_targets": grouped_review_targets,
        }
    )
    return merged


def audit_review_packets(
    run_dir: Path,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = state or load_state(run_dir)
    approval = load_approval(run_dir) if approval_artifact(run_dir).exists() else None
    summary = load_summary_or_synthesize(run_dir, state, approval)
    manifest_path = review_packet_manifest_artifact(run_dir)
    advisory_trace_path = advisory_trace_runtime_artifact(run_dir)
    manifest_payload = load_json_if_exists(manifest_path)

    playbook_id = str(
        state.get("playbook_id")
        or ((manifest_payload or {}).get("selected_playbook") or {}).get("playbook_id")
        or ""
    ).strip()
    candidate_packet_kinds: list[str] = []
    packet_statuses: list[dict[str, Any]] = []
    contract_refs: list[str] = []
    recommended_review_targets: list[dict[str, str]] = []
    review_target_seen: set[tuple[str, str]] = set()
    block_reasons: list[str] = []

    replay_required_paths = [run_dir / "request.json", run_dir / "preflight.summary.json"]
    replayable = bool(summary.get("status") == "pass") and all(path.exists() for path in replay_required_paths)

    if manifest_payload is None:
        block_reasons.append("review_packet_manifest_missing")
    if not advisory_trace_path.exists():
        block_reasons.append("advisory_trace_missing")

    manifest_contract = None
    matched_eval_entries: list[dict[str, Any]] = []
    matched_memo_targets: list[dict[str, Any]] = []
    emitted_refs: list[dict[str, Any]] = []
    skipped_refs: list[dict[str, Any]] = []
    if manifest_payload is not None:
        raw_contract = manifest_payload.get("matched_playbook_packet_contract")
        if isinstance(raw_contract, dict):
            manifest_contract = raw_contract
            candidate_packet_kinds = [
                kind
                for kind in raw_contract.get("candidate_packet_kinds", [])
                if isinstance(kind, str) and kind
            ]
        else:
            block_reasons.append("matched_playbook_packet_contract_missing")

        matched_eval_entries = [
            entry
            for entry in manifest_payload.get("matched_eval_template_entries", [])
            if isinstance(entry, dict)
        ]
        matched_memo_targets = [
            entry
            for entry in manifest_payload.get("matched_memo_writeback_targets", [])
            if isinstance(entry, dict)
        ]
        emitted_refs = [
            entry
            for entry in manifest_payload.get("emitted_candidate_artifact_refs", [])
            if isinstance(entry, dict)
        ]
        skipped_refs = [
            entry
            for entry in manifest_payload.get("skipped_packet_kinds", [])
            if isinstance(entry, dict)
        ]

    if manifest_contract is not None:
        contract_refs.append(PLAYBOOK_REVIEW_PACKET_CONTRACTS_SOURCE_REF)
        for ref in manifest_contract.get("source_review_refs", []):
            if isinstance(ref, str):
                append_review_target(
                    recommended_review_targets,
                    review_target_seen,
                    owner_repo="aoa-playbooks",
                    ref=ref,
                    why="Source-owned playbook review target for the governed packet set.",
                )
        try:
            live_contract = playbook_review_packet_contract_by_id(playbook_id)
        except Exception as exc:
            block_reasons.append(f"live_playbook_review_packet_contract_unavailable:{type(exc).__name__}")
        else:
            if _playbook_review_packet_contract_projection(live_contract) != _playbook_review_packet_contract_projection(
                manifest_contract
            ):
                block_reasons.append("playbook_review_packet_contract_drift")

    if matched_eval_entries:
        contract_refs.append(EVAL_RUNTIME_TEMPLATE_INDEX_SOURCE_REF)
        live_eval_entries: dict[tuple[Any, Any], dict[str, Any]] | None = None
        try:
            live_eval_entries = {
                (entry.get("template_kind"), entry.get("template_name")): entry
                for entry in eval_runtime_candidate_templates()
            }
        except Exception as exc:
            block_reasons.append(f"runtime_candidate_template_index_unavailable:{type(exc).__name__}")
        for entry in matched_eval_entries:
            template_name = str(entry.get("template_name") or "")
            if live_eval_entries is not None:
                key = (entry.get("template_kind"), template_name)
                live_entry = live_eval_entries.get(key)
                if live_entry is None:
                    block_reasons.append(f"runtime_candidate_template_missing:{template_name or 'unknown'}")
                elif _eval_runtime_template_projection(live_entry) != _eval_runtime_template_projection(entry):
                    block_reasons.append(f"runtime_candidate_template_drift:{template_name or 'unknown'}")
            source_example_ref = entry.get("source_example_ref")
            if isinstance(source_example_ref, str):
                append_review_target(
                    recommended_review_targets,
                    review_target_seen,
                    owner_repo="aoa-evals",
                    ref=source_example_ref,
                    why="Runtime candidate packets remain eval-owned review inputs.",
                )

    if matched_memo_targets:
        contract_refs.append(MEMO_RUNTIME_WRITEBACK_TARGETS_SOURCE_REF)
        live_memo_targets: dict[Any, dict[str, Any]] | None = None
        try:
            live_memo_targets = {
                entry.get("runtime_surface"): entry
                for entry in memo_runtime_writeback_targets()
                if isinstance(entry.get("runtime_surface"), str)
            }
        except Exception as exc:
            block_reasons.append(f"runtime_writeback_targets_unavailable:{type(exc).__name__}")
        for entry in matched_memo_targets:
            runtime_surface = str(entry.get("runtime_surface") or "")
            if live_memo_targets is not None:
                live_entry = live_memo_targets.get(runtime_surface)
                if live_entry is None:
                    block_reasons.append(f"runtime_writeback_target_missing:{runtime_surface or 'unknown'}")
                elif _memo_writeback_target_projection(live_entry) != _memo_writeback_target_projection(entry):
                    block_reasons.append(f"runtime_writeback_target_drift:{runtime_surface or 'unknown'}")
            local_runtime_refs = [
                ref
                for ref in entry.get("runtime_refs", [])
                if isinstance(ref, str) and ref and not ref.startswith("repo:")
            ]
            if not local_runtime_refs:
                local_runtime_refs = ["docs/RUNTIME_WRITEBACK_SEAM.md"]
            for ref in local_runtime_refs:
                append_review_target(
                    recommended_review_targets,
                    review_target_seen,
                    owner_repo="aoa-memo",
                    ref=ref,
                    why="Memo writeback targets stay human-reviewed before source adoption.",
                )

    emitted_by_kind: dict[str, list[dict[str, Any]]] = {}
    for entry in emitted_refs:
        packet_kind = entry.get("packet_kind")
        if isinstance(packet_kind, str):
            emitted_by_kind.setdefault(packet_kind, []).append(entry)
    skipped_by_kind = {
        str(entry.get("packet_kind")): str(entry.get("reason") or "")
        for entry in skipped_refs
        if isinstance(entry.get("packet_kind"), str)
    }

    for packet_kind in candidate_packet_kinds:
        emitted_entries = emitted_by_kind.get(packet_kind, [])
        artifact_refs = [
            str(entry.get("artifact_ref"))
            for entry in emitted_entries
            if isinstance(entry.get("artifact_ref"), str)
        ]
        missing_emitted_refs = [
            ref
            for ref in artifact_refs
            if local_ref_path(ref) is None or not local_ref_path(ref).exists()
        ]
        if emitted_entries:
            status = "stale" if missing_emitted_refs else "emitted"
            reason = (
                "missing emitted artifact refs: " + ", ".join(missing_emitted_refs)
                if missing_emitted_refs
                else None
            )
        elif packet_kind in skipped_by_kind:
            status = "skipped"
            reason = skipped_by_kind[packet_kind]
        else:
            status = "missing"
            artifact_refs = []
            reason = "expected packet kind did not emit and did not record a skip reason"
        packet_statuses.append(
            {
                "packet_kind": packet_kind,
                "status": status,
                "artifact_refs": artifact_refs,
                "reason": reason,
            }
        )

    if block_reasons:
        packet_statuses.append(
            {
                "packet_kind": "contract_refs",
                "status": "stale",
                "artifact_refs": [],
                "reason": "; ".join(block_reasons),
            }
        )

    packet_status_values = [entry["status"] for entry in packet_statuses if isinstance(entry.get("status"), str)]
    if any(status in {"missing", "stale"} for status in packet_status_values):
        audit_verdict = "blocked"
    elif any(status == "skipped" for status in packet_status_values):
        audit_verdict = "partial"
    elif packet_status_values and all(status == "emitted" for status in packet_status_values):
        audit_verdict = "ready"
    else:
        audit_verdict = "blocked"

    audit_payload = {
        "schema_version": 1,
        "run_id": state.get("run_id") or run_dir.name,
        "playbook_id": playbook_id,
        "audit_verdict": audit_verdict,
        "review_packet_manifest_ref": str(manifest_path),
        "advisory_trace_ref": str(advisory_trace_path) if advisory_trace_path.exists() else None,
        "packet_statuses": packet_statuses,
        "contract_refs": list(dict.fromkeys(contract_refs)),
        "recommended_review_targets": recommended_review_targets,
        "replayable": replayable,
        "safe_replay_command": (
            f"scripts/aoa-governed-run replay-review-packets {state.get('run_id') or run_dir.name}"
            if replayable
            else None
        ),
    }
    write_json(review_packet_audit_artifact(run_dir), audit_payload)
    audit_payload["review_packet_audit_ref"] = str(review_packet_audit_artifact(run_dir))
    return audit_payload


def persist_review_packet_audit_summary(
    run_dir: Path,
    *,
    state: dict[str, Any] | None = None,
    review_packet_status: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = state or load_state(run_dir)
    approval = load_approval(run_dir) if approval_artifact(run_dir).exists() else None
    summary = load_summary_or_synthesize(run_dir, state, approval)
    audit_payload = audit_review_packets(run_dir, state=state)
    merged_review_packets = review_packet_summary_with_audit(review_packet_status or summary.get("review_packets"), audit_payload)
    summary["review_packets"] = merged_review_packets
    save_summary(run_dir, summary, state=state)
    return audit_payload, merged_review_packets


def materialize_review_handoff_bundle(
    run_dir: Path,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = state or load_state(run_dir)
    audit_payload, review_packets = persist_review_packet_audit_summary(run_dir, state=state)
    manifest_payload = load_json_if_exists(review_packet_manifest_artifact(run_dir)) or {}

    playbook_id = str(
        state.get("playbook_id")
        or ((manifest_payload.get("selected_playbook") or {}).get("playbook_id") if isinstance(manifest_payload, dict) else "")
        or ""
    ).strip()
    emitted_candidate_artifact_refs = [
        entry
        for entry in manifest_payload.get("emitted_candidate_artifact_refs", [])
        if isinstance(entry, dict)
    ] if isinstance(manifest_payload, dict) else []
    matched_eval_entries = [
        entry
        for entry in manifest_payload.get("matched_eval_template_entries", [])
        if isinstance(entry, dict)
    ] if isinstance(manifest_payload, dict) else []
    matched_memo_targets = [
        entry
        for entry in manifest_payload.get("matched_memo_writeback_targets", [])
        if isinstance(entry, dict)
    ] if isinstance(manifest_payload, dict) else []
    matched_playbook_contract = (
        manifest_payload.get("matched_playbook_packet_contract")
        if isinstance(manifest_payload.get("matched_playbook_packet_contract"), dict)
        else None
    ) if isinstance(manifest_payload, dict) else None

    review_targets: list[dict[str, str]] = [
        item for item in audit_payload.get("recommended_review_targets", []) if isinstance(item, dict)
    ]
    review_target_seen = {
        (str(item.get("owner_repo") or ""), str(item.get("ref") or ""))
        for item in review_targets
        if isinstance(item, dict)
    }

    missing_or_blocked_packet_kinds: list[dict[str, Any]] = []
    missing_seen: set[tuple[str, str, str]] = set()

    def append_missing(packet_kind: str, status: str, reason: str) -> None:
        key = (packet_kind, status, reason)
        if key in missing_seen:
            return
        missing_seen.add(key)
        missing_or_blocked_packet_kinds.append(
            {
                "packet_kind": packet_kind,
                "status": status,
                "reason": reason,
            }
        )

    for entry in audit_payload.get("packet_statuses", []):
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "")
        if status == "emitted":
            continue
        append_missing(
            str(entry.get("packet_kind") or "unknown"),
            status or "missing",
            str(entry.get("reason") or ""),
        )

    playbook_intake: dict[str, Any] | None = None
    if playbook_id:
        try:
            playbook_intake = playbook_review_intake_by_id(playbook_id)
        except Exception as exc:
            append_missing("playbook_review_intake", "missing", f"{type(exc).__name__}: {exc}")
        else:
            if playbook_intake is None:
                append_missing("playbook_review_intake", "missing", "playbook_review_intake_missing")
            else:
                if matched_playbook_contract is not None:
                    if playbook_intake.get("accepted_packet_kinds") != matched_playbook_contract.get("candidate_packet_kinds"):
                        append_missing("playbook_review_intake", "stale", "accepted_packet_kinds_drift")
                for ref in playbook_intake.get("source_review_refs", []):
                    if isinstance(ref, str):
                        append_review_target(
                            review_targets,
                            review_target_seen,
                            owner_repo="aoa-playbooks",
                            ref=ref,
                            why="Playbook-owned review targets remain the primary human intake seam.",
                        )
                outcome_targets = playbook_intake.get("review_outcome_targets")
                if isinstance(outcome_targets, dict):
                    for ref in outcome_targets.get("real_runs", []):
                        if isinstance(ref, str):
                            append_review_target(
                                review_targets,
                                review_target_seen,
                                owner_repo="aoa-playbooks",
                                ref=ref,
                                why="Reviewed real-run evidence remains source-owned in aoa-playbooks.",
                            )
                    for ref in outcome_targets.get("gate_reviews", []):
                        if isinstance(ref, str):
                            append_review_target(
                                review_targets,
                                review_target_seen,
                                owner_repo="aoa-playbooks",
                                ref=ref,
                                why="Gate review adoption remains source-owned in aoa-playbooks.",
                            )

    eval_intake_entries: list[dict[str, Any]] = []
    try:
        live_eval_intake = {
            (entry.get("template_kind"), entry.get("template_name")): entry
            for entry in eval_runtime_candidate_intake_entries()
        }
    except Exception as exc:
        live_eval_intake = {}
        append_missing("eval_runtime_candidate_intake", "missing", f"{type(exc).__name__}: {exc}")
    for entry in matched_eval_entries:
        packet_kind = (
            "artifact_hook_candidate"
            if entry.get("template_kind") == "artifact_to_verdict_hook"
            else "runtime_evidence_selection_candidate"
        )
        key = (entry.get("template_kind"), entry.get("template_name"))
        live_entry = live_eval_intake.get(key)
        if live_entry is None:
            append_missing(packet_kind, "missing", f"runtime_candidate_intake_missing:{entry.get('template_name')}")
            continue
        eval_intake_entries.append(live_entry)
        for ref in live_entry.get("owner_review_refs", []):
            if isinstance(ref, str):
                append_review_target(
                    review_targets,
                    review_target_seen,
                    owner_repo="aoa-evals",
                    ref=ref,
                    why="Eval-owned runtime candidate intake remains human-reviewed before adoption.",
                )

    memo_intake_entries: list[dict[str, Any]] = []
    try:
        live_memo_intake = {
            entry.get("runtime_surface"): entry
            for entry in memo_runtime_writeback_intake_targets()
            if isinstance(entry.get("runtime_surface"), str)
        }
    except Exception as exc:
        live_memo_intake = {}
        append_missing("memo_writeback_intake", "missing", f"{type(exc).__name__}: {exc}")
    for entry in matched_memo_targets:
        runtime_surface = str(entry.get("runtime_surface") or "")
        live_entry = live_memo_intake.get(runtime_surface)
        if live_entry is None:
            append_missing("memo_candidate", "missing", f"runtime_writeback_intake_missing:{runtime_surface or 'unknown'}")
            continue
        memo_intake_entries.append(live_entry)
        for ref in live_entry.get("owner_review_refs", []):
            if isinstance(ref, str):
                append_review_target(
                    review_targets,
                    review_target_seen,
                    owner_repo="aoa-memo",
                    ref=ref,
                    why="Memo runtime writeback remains a source-owned human review seam.",
                )

    grouped_review_targets = group_review_targets_by_owner(review_targets)

    missing_statuses = {
        str(entry.get("status") or "")
        for entry in missing_or_blocked_packet_kinds
        if isinstance(entry, dict)
    }
    if "missing" in missing_statuses or "stale" in missing_statuses or audit_payload.get("audit_verdict") == "blocked":
        handoff_readiness = "blocked"
    elif missing_or_blocked_packet_kinds or audit_payload.get("audit_verdict") == "partial":
        handoff_readiness = "partial"
    else:
        handoff_readiness = "ready"

    operator_next_steps: list[str] = []
    if missing_or_blocked_packet_kinds:
        operator_next_steps.append(
            "Resolve blocked or missing packet kinds before any source-owned adoption, then rerun `scripts/aoa-governed-run handoff-brief "
            + f"{state.get('run_id') or run_dir.name}`."
        )
    if grouped_review_targets.get("aoa-playbooks"):
        operator_next_steps.append("Review aoa-playbooks handoff refs first to confirm playbook-owned outcome posture.")
    if grouped_review_targets.get("aoa-evals"):
        operator_next_steps.append("Review aoa-evals intake refs for candidate evidence selection and verdict-hook readiness.")
    if grouped_review_targets.get("aoa-memo"):
        operator_next_steps.append("Review aoa-memo intake refs before any writeback or memory adoption.")
    if not operator_next_steps:
        operator_next_steps.append("No owner intake refs are ready yet; inspect the audit and manifest artifacts directly.")

    handoff_payload = {
        "schema_version": 1,
        "run_id": state.get("run_id") or run_dir.name,
        "playbook_id": playbook_id,
        "audit_verdict": audit_payload.get("audit_verdict"),
        "replayable": audit_payload.get("replayable"),
        "playbook_intake": playbook_intake,
        "eval_intake_entries": eval_intake_entries,
        "memo_intake_entries": memo_intake_entries,
        "emitted_candidate_artifact_refs": emitted_candidate_artifact_refs,
        "recommended_review_targets": grouped_review_targets,
        "missing_or_blocked_packet_kinds": missing_or_blocked_packet_kinds,
        "operator_next_steps": operator_next_steps,
    }
    handoff_path = review_handoff_bundle_artifact(run_dir)
    write_json(handoff_path, handoff_payload)

    approval = load_approval(run_dir) if approval_artifact(run_dir).exists() else None
    summary = load_summary_or_synthesize(run_dir, state, approval)
    summary["review_packets"] = review_packet_summary_with_handoff(
        review_packets or summary.get("review_packets"),
        handoff_payload,
        handoff_ref=str(handoff_path),
        handoff_readiness=handoff_readiness,
    )
    save_summary(run_dir, summary, state=state)
    return handoff_payload


def render_review_handoff_bundle_brief(payload: dict[str, Any]) -> str:
    grouped_targets = payload.get("recommended_review_targets") or {}
    lines = [
        f"# governed-run handoff `{payload.get('run_id')}`",
        "",
        f"- playbook_id: `{payload.get('playbook_id')}`",
        f"- audit_verdict: `{payload.get('audit_verdict')}`",
        f"- replayable: `{payload.get('replayable')}`",
        f"- playbook_intake: `{bool(payload.get('playbook_intake'))}`",
        f"- eval_intake_entries: `{len(payload.get('eval_intake_entries') or [])}`",
        f"- memo_intake_entries: `{len(payload.get('memo_intake_entries') or [])}`",
        f"- emitted_candidate_artifacts: `{len(payload.get('emitted_candidate_artifact_refs') or [])}`",
    ]
    missing = payload.get("missing_or_blocked_packet_kinds") or []
    if missing:
        lines.extend(["", "## Missing Or Blocked", ""])
        for entry in missing:
            if not isinstance(entry, dict):
                continue
            lines.append(
                f"- {entry.get('packet_kind')}: `{entry.get('status')}`"
                + (f" ({entry.get('reason')})" if entry.get("reason") else "")
            )
    if grouped_targets:
        lines.extend(["", "## Review Targets", ""])
        for owner_repo, refs in grouped_targets.items():
            lines.append(f"- {owner_repo}:")
            for ref_entry in refs:
                if not isinstance(ref_entry, dict):
                    continue
                line = f"  `{ref_entry.get('ref')}`"
                if ref_entry.get("why"):
                    line += f" ({ref_entry.get('why')})"
                lines.append(line)
    next_steps = payload.get("operator_next_steps") or []
    if next_steps:
        lines.extend(["", "## Next Steps", ""])
        lines.extend(f"- {step}" for step in next_steps if isinstance(step, str) and step)
    return "\n".join(lines)


def audit_run(
    run_id: str,
    *,
    log_root: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    audit_payload, review_packets = persist_review_packet_audit_summary(run_dir, state=state)
    return {
        "artifact_kind": "aoa.governed-run.review-packet-audit-result",
        "schema_version": "v1",
        "run_id": run_id,
        "audit_verdict": audit_payload.get("audit_verdict"),
        "review_packets": review_packets,
        "review_packet_audit": audit_payload,
    }


def replay_review_packets(
    run_id: str,
    *,
    log_root: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    if str(state.get("status") or "") != "pass":
        raise RuntimeError("replay-review-packets requires a completed governed pass run")
    request_path = run_dir / "request.json"
    preflight_path = run_dir / "preflight.summary.json"
    if not request_path.exists() or not preflight_path.exists():
        missing = [path.name for path in (request_path, preflight_path) if not path.exists()]
        raise RuntimeError("replay-review-packets requires stored inputs: " + ", ".join(missing))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    advisory_context = preflight.get("advisory_context")
    if not isinstance(request, dict) or not isinstance(advisory_context, dict):
        raise RuntimeError("replay-review-packets requires dict-shaped request and advisory_context payloads")

    review_packet_status = materialize_review_packets(
        run_dir,
        request=request,
        state=state,
        advisory_context=advisory_context,
        advisory_trace_provider=stored_review_packet_trace_provider(run_dir),
    )
    audit_payload, merged_review_packets = persist_review_packet_audit_summary(
        run_dir,
        state=state,
        review_packet_status=review_packet_status,
    )
    return {
        "artifact_kind": "aoa.governed-run.review-packet-replay",
        "schema_version": "v1",
        "run_id": run_id,
        "audit_verdict": audit_payload.get("audit_verdict"),
        "review_packets": merged_review_packets,
        "review_packet_audit": audit_payload,
    }


def handoff_brief_run(
    run_id: str,
    *,
    log_root: str | Path | None = None,
) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    handoff_payload = materialize_review_handoff_bundle(run_dir, state=state)
    return {
        "artifact_kind": "aoa.governed-run.review-handoff-brief",
        "schema_version": "v1",
        "run_id": run_id,
        "handoff_ref": str(review_handoff_bundle_artifact(run_dir)),
        "handoff_readiness": (
            (load_summary_or_synthesize(run_dir, state, load_approval(run_dir) if approval_artifact(run_dir).exists() else None)
             .get("review_packets") or {})
            .get("handoff_readiness")
        ),
        "review_handoff_bundle": handoff_payload,
    }


def export_wrapper_command(script_name: str, *, input_file: Path, extra_args: list[str] | None = None) -> list[str]:
    command = [
        "env",
        f"AOA_STACK_ROOT={STACK_ROOT}",
        "python",
        str(SCRIPT_ROOT / "scripts" / script_name),
        "--input-file",
        str(input_file),
    ]
    if extra_args:
        command.extend(extra_args)
    command.append("--write")
    return command


def run_export_wrapper(
    run_dir: Path,
    *,
    label: str,
    command: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = run_command(command, cwd=SCRIPT_ROOT, timeout_s=180.0)
    ref = TRIALS.persist_command_result(run_dir, label, raw)
    if raw["exit_code"] != 0 or raw["timed_out"]:
        raise RuntimeError(raw["stderr"].strip() or f"{label} failed")
    payload = json.loads(raw["stdout"])
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} did not emit a JSON object")
    return payload, ref


def build_memo_candidate_payload(
    *,
    run_id: str,
    playbook_contract: dict[str, Any],
    memo_target: dict[str, Any],
    changed_files: list[str],
    advisory_trace_ref: Path,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "playbook_id": playbook_contract.get("playbook_id"),
        "candidate_kind": "memo_candidate",
        "runtime_surface": memo_target.get("runtime_surface"),
        "target_kind": memo_target.get("target_kind"),
        "writeback_class": memo_target.get("writeback_class"),
        "changed_files": changed_files,
        "advisory_trace_ref": f"local:{advisory_trace_ref}",
        "review_required": memo_target.get("requires_human_review"),
        "notes": memo_target.get("notes"),
    }


def build_runtime_evidence_selection_payload(
    *,
    run_id: str,
    playbook_contract: dict[str, Any],
    template: dict[str, Any],
    changed_files: list[str],
    advisory_trace_ref: Path,
) -> dict[str, Any]:
    selection_id = f"{slugify(run_id)}--{slugify(str(template.get('template_name') or 'runtime-evidence-selection'))}"
    required_runtime_artifacts = [
        artifact for artifact in template.get("required_runtime_artifacts", []) if isinstance(artifact, str) and artifact
    ]
    return {
        "surface_type": "runtime_evidence_selection",
        "selection_id": selection_id,
        "playbook_id": playbook_contract.get("playbook_id"),
        "template_name": template.get("template_name"),
        "candidate_eval_refs": (
            [f"candidate:{template['eval_anchor']}"] if isinstance(template.get("eval_anchor"), str) else []
        ),
        "selected_evidence": [
            {
                "evidence_role": artifact,
                "artifact_ref": f"governed-run:{run_id}:{artifact}",
            }
            for artifact in required_runtime_artifacts
        ],
        "selection_rationale": "Bounded governed-run review packet candidate assembled from advisory trace and contract matches.",
        "review_required": bool(template.get("review_required", True)),
        "source_example_ref": template.get("source_example_ref"),
        "changed_files": changed_files,
        "advisory_trace_ref": f"local:{advisory_trace_ref}",
    }


def build_artifact_hook_payload(
    *,
    run_id: str,
    playbook_contract: dict[str, Any],
    template: dict[str, Any],
    changed_files: list[str],
    advisory_trace_ref: Path,
) -> dict[str, Any]:
    hook_name = str(template.get("template_name") or "artifact-hook")
    return {
        "surface_type": "artifact_to_verdict_hook",
        "hook_id": f"{slugify(hook_name)}--{run_id}",
        "playbook_id": playbook_contract.get("playbook_id"),
        "eval_anchor": template.get("eval_anchor"),
        "verdict_bundle_ref": template.get("verdict_bundle_ref"),
        "artifact_inputs": [
            artifact for artifact in template.get("required_runtime_artifacts", []) if isinstance(artifact, str) and artifact
        ],
        "review_required": bool(template.get("review_required", True)),
        "source_example_ref": template.get("source_example_ref"),
        "changed_files": changed_files,
        "advisory_trace_ref": f"local:{advisory_trace_ref}",
    }


def materialize_review_packets(
    run_dir: Path,
    *,
    request: dict[str, Any],
    state: dict[str, Any],
    advisory_context: dict[str, Any],
    advisory_trace_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    playbook_id = str(state.get("playbook_id") or request.get("playbook_id") or "").strip()
    if not playbook_id:
        payload = {
            "artifact_kind": "aoa.governed-run.review-packet-manifest",
            "schema_version": "v1",
            "run_id": state.get("run_id"),
            "generated_at": utc_now(),
            "selected_playbook": None,
            "matched_playbook_packet_contract": None,
            "matched_eval_template_entries": [],
            "matched_memo_writeback_targets": [],
            "emitted_candidate_artifact_refs": [],
            "skipped_packet_kinds": [{"packet_kind": "all", "reason": "playbook_id_unavailable"}],
        }
        write_json(review_packet_manifest_artifact(run_dir), payload)
        return {
            "ready": False,
            "manifest_ref": str(review_packet_manifest_artifact(run_dir)),
            "advisory_trace_ref": None,
            "emitted_candidate_artifact_count": 0,
            "skipped_packet_kind_count": 1,
        }

    playbook_contract = None
    playbook_context = advisory_context.get("playbook")
    if isinstance(playbook_context, dict) and isinstance(playbook_context.get("review_packet_contract"), dict):
        playbook_contract = playbook_context["review_packet_contract"]
    if playbook_contract is None:
        playbook_contract = playbook_review_packet_contract_by_id(playbook_id)

    advisory_trace_error: str | None = None
    if playbook_contract is not None:
        try:
            provider = advisory_trace_provider or default_review_packet_trace_provider
            advisory_trace = provider(request)
        except Exception as exc:
            advisory_trace_error = f"{type(exc).__name__}: {exc}"
            advisory_trace = fallback_review_packet_trace(
                request,
                advisory_context,
                playbook_contract=playbook_contract,
            )
    else:
        advisory_trace_error = "playbook_review_packet_contract_unavailable"
        advisory_trace = fallback_review_packet_trace(request, advisory_context, playbook_contract=None)

    advisory_trace_path = advisory_trace_runtime_artifact(run_dir)
    write_json(advisory_trace_path, advisory_trace)

    emitted_refs: list[dict[str, Any]] = []
    skipped_packet_kinds: list[dict[str, Any]] = []
    matched_eval_entries: list[dict[str, Any]] = []
    matched_memo_targets: list[dict[str, Any]] = []
    if playbook_contract is not None:
        hook_templates, evidence_templates = review_packet_eval_template_matches(playbook_id, playbook_contract)
        matched_eval_entries = hook_templates + evidence_templates
        matched_memo_targets = review_packet_memo_target_matches(playbook_contract)

    candidate_packet_kinds = [
        kind for kind in (playbook_contract or {}).get("candidate_packet_kinds", []) if isinstance(kind, str) and kind
    ]
    for packet_kind in candidate_packet_kinds:
        if packet_kind == "memo_candidate":
            if not matched_memo_targets:
                skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": "no_matched_memo_writeback_targets"})
                continue
            for memo_target in matched_memo_targets:
                runtime_surface = str(memo_target.get("runtime_surface") or "memo-target")
                input_path = write_review_packet_input(
                    run_dir,
                    packet_kind=packet_kind,
                    stem=slugify(runtime_surface),
                    payload=build_memo_candidate_payload(
                        run_id=state["run_id"],
                        playbook_contract=playbook_contract,
                        memo_target=memo_target,
                        changed_files=list(state.get("changed_files") or []),
                        advisory_trace_ref=advisory_trace_path,
                    ),
                )
                try:
                    export_payload, ref = run_export_wrapper(
                        run_dir,
                        label=f"review-packet-memo-{slugify(runtime_surface)}",
                        command=export_wrapper_command(
                            "aoa-export-memo-candidate",
                            input_file=input_path,
                            extra_args=["--runtime-surface", runtime_surface],
                        ),
                    )
                except Exception as exc:
                    skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": f"{runtime_surface}: {type(exc).__name__}: {exc}"})
                    continue
                emitted_refs.append(
                    {
                        "packet_kind": packet_kind,
                        "runtime_surface": runtime_surface,
                        "input_ref": f"local:{input_path}",
                        "artifact_ref": f"local:{STACK_ROOT / 'Logs' / 'memo-exports' / 'latest' / f'{runtime_surface}.private.json'}",
                        "command_meta": ref["command_meta"],
                        "record_id": export_payload.get("record_id"),
                    }
                )
        elif packet_kind == "runtime_evidence_selection_candidate":
            evidence_entries = [entry for entry in matched_eval_entries if entry.get("template_kind") == "runtime_evidence_selection"]
            if not evidence_entries:
                skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": "no_runtime_evidence_selection_templates"})
                continue
            for template in evidence_entries:
                template_name = str(template.get("template_name") or "runtime-evidence-selection")
                input_path = write_review_packet_input(
                    run_dir,
                    packet_kind=packet_kind,
                    stem=slugify(template_name),
                    payload=build_runtime_evidence_selection_payload(
                        run_id=state["run_id"],
                        playbook_contract=playbook_contract,
                        template=template,
                        changed_files=list(state.get("changed_files") or []),
                        advisory_trace_ref=advisory_trace_path,
                    ),
                )
                try:
                    export_payload, ref = run_export_wrapper(
                        run_dir,
                        label=f"review-packet-evidence-{slugify(template_name)}",
                        command=export_wrapper_command(
                            "aoa-export-runtime-evidence-selection",
                            input_file=input_path,
                        ),
                    )
                except Exception as exc:
                    skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": f"{template_name}: {type(exc).__name__}: {exc}"})
                    continue
                selection_id = str(export_payload.get("selection_id") or "")
                emitted_refs.append(
                    {
                        "packet_kind": packet_kind,
                        "template_name": template_name,
                        "input_ref": f"local:{input_path}",
                        "artifact_ref": f"local:{STACK_ROOT / 'Logs' / 'eval-exports' / 'latest' / 'runtime-evidence-selection' / f'{selection_id}.private.json'}",
                        "command_meta": ref["command_meta"],
                        "record_id": export_payload.get("record_id"),
                    }
                )
        elif packet_kind == "artifact_hook_candidate":
            hook_entries = [entry for entry in matched_eval_entries if entry.get("template_kind") == "artifact_to_verdict_hook"]
            if not hook_entries:
                skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": "no_artifact_hook_templates"})
                continue
            for template in hook_entries:
                template_name = str(template.get("template_name") or "artifact-hook")
                input_path = write_review_packet_input(
                    run_dir,
                    packet_kind=packet_kind,
                    stem=slugify(template_name),
                    payload=build_artifact_hook_payload(
                        run_id=state["run_id"],
                        playbook_contract=playbook_contract,
                        template=template,
                        changed_files=list(state.get("changed_files") or []),
                        advisory_trace_ref=advisory_trace_path,
                    ),
                )
                try:
                    export_payload, ref = run_export_wrapper(
                        run_dir,
                        label=f"review-packet-hook-{slugify(template_name)}",
                        command=export_wrapper_command(
                            "aoa-export-artifact-hook-candidate",
                            input_file=input_path,
                        ),
                    )
                except Exception as exc:
                    skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": f"{template_name}: {type(exc).__name__}: {exc}"})
                    continue
                hook_id = str(export_payload.get("hook_id") or "")
                emitted_refs.append(
                    {
                        "packet_kind": packet_kind,
                        "template_name": template_name,
                        "input_ref": f"local:{input_path}",
                        "artifact_ref": f"local:{STACK_ROOT / 'Logs' / 'eval-exports' / 'latest' / 'artifact-hook' / f'{hook_id}.private.json'}",
                        "command_meta": ref["command_meta"],
                        "record_id": export_payload.get("record_id"),
                    }
                )
        else:
            skipped_packet_kinds.append({"packet_kind": packet_kind, "reason": "unsupported_packet_kind"})

    if advisory_trace_error is not None:
        skipped_packet_kinds.append({"packet_kind": "advisory_trace", "reason": advisory_trace_error})

    manifest_payload = {
        "artifact_kind": "aoa.governed-run.review-packet-manifest",
        "schema_version": "v1",
        "run_id": state["run_id"],
        "generated_at": utc_now(),
        "selected_playbook": {
            "playbook_id": playbook_id,
            "playbook_name": (playbook_contract or {}).get("playbook_name") or (playbook_context or {}).get("name") or (playbook_context or {}).get("title"),
        },
        "matched_playbook_packet_contract": playbook_contract,
        "matched_eval_template_entries": matched_eval_entries,
        "matched_memo_writeback_targets": matched_memo_targets,
        "advisory_trace_ref": f"local:{advisory_trace_path}",
        "emitted_candidate_artifact_refs": emitted_refs,
        "skipped_packet_kinds": skipped_packet_kinds,
    }
    write_json(review_packet_manifest_artifact(run_dir), manifest_payload)
    return {
        "ready": playbook_contract is not None,
        "manifest_ref": str(review_packet_manifest_artifact(run_dir)),
        "advisory_trace_ref": str(advisory_trace_path),
        "emitted_candidate_artifact_count": len(emitted_refs),
        "skipped_packet_kind_count": len(skipped_packet_kinds),
    }


def pass_result(
    run_dir: Path,
    *,
    state: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    review_packet_status: dict[str, Any] | None = None
    request_path = run_dir / "request.json"
    preflight_path = run_dir / "preflight.summary.json"
    if request_path.exists() and preflight_path.exists():
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
            advisory_context = preflight.get("advisory_context")
            if isinstance(request, dict) and isinstance(advisory_context, dict):
                review_packet_status = materialize_review_packets(
                    run_dir,
                    request=request,
                    state=state,
                    advisory_context=advisory_context,
                )
                audit_state = dict(state)
                audit_state["phase"] = "completed"
                audit_state["status"] = "pass"
                review_packet_status = review_packet_summary_with_audit(
                    review_packet_status,
                    audit_review_packets(run_dir, state=audit_state),
                )
        except Exception as exc:
            review_packet_status = {
                "ready": False,
                "manifest_ref": None,
                "advisory_trace_ref": None,
                "emitted_candidate_artifact_count": 0,
                "skipped_packet_kind_count": 1,
                "materialization_error": f"{type(exc).__name__}: {exc}",
            }

    summary = make_pass_summary(
        run_id=state["run_id"],
        phase="completed",
        changed_files=changed_files,
        break_glass_used=bool(state.get("break_glass_used")),
        next_action="Governed execution landed successfully.",
    )
    if review_packet_status is not None:
        summary["review_packets"] = review_packet_status
    state["phase"] = "completed"
    state["status"] = "pass"
    state["changed_files"] = changed_files
    save_state(run_dir, state)
    save_summary(run_dir, summary, state=state)
    return json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))


def apply_edit_spec_in_place(repo_root: Path, *, selected_target_file: str, spec: dict[str, Any]) -> None:
    target_path = repo_root / selected_target_file
    original_text = target_path.read_text(encoding="utf-8")
    candidate_text = build_candidate_text(
        original_text,
        selected_target_file=selected_target_file,
        spec=spec,
    )
    target_path.write_text(candidate_text, encoding="utf-8")


def preview_proposal(
    run_dir: Path,
    *,
    state: dict[str, Any],
    playbook_policy: dict[str, Any],
    attempt_label: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    repo_root = Path(state["repo_root"])
    proposal_summary = json.loads(proposal_summary_artifact(run_dir).read_text(encoding="utf-8"))
    proposal_edit_spec = json.loads(proposal_edit_spec_artifact(run_dir).read_text(encoding="utf-8"))
    selected_target_file = proposal_summary["selected_target_file"]
    allowed_files = proposal_summary["allowed_files"]
    worktree_path, add_raw = TRIALS.with_temp_worktree(repo_root, case_id=state["run_id"], log_root=run_dir.parent)
    add_ref = TRIALS.persist_command_result(run_dir, f"{attempt_label}-worktree-add", add_raw)
    artifact_refs = [add_ref["stdout_path"], add_ref["stderr_path"], add_ref["command_meta"]]
    if add_raw["exit_code"] != 0 or add_raw["timed_out"]:
        raise RuntimeError("git worktree add failed")
    changed_files: list[str] = []
    try:
        apply_edit_spec_in_place(
            worktree_path,
            selected_target_file=selected_target_file,
            spec=proposal_edit_spec["spec"],
        )
        changed_files = TRIALS.list_changed_files(worktree_path)
        unauthorized = sorted(item for item in changed_files if not path_allowed(item, allowed_files))
        if unauthorized:
            raise PermissionError("changed files outside governed scope: " + ", ".join(unauthorized))
        landing_diff_path = run_dir / "landing.diff"
        landing_raw = TRIALS.build_landing_diff(worktree_path, diff_path=landing_diff_path)
        landing_ref = TRIALS.persist_command_result(run_dir, f"{attempt_label}-landing-diff", landing_raw)
        artifact_refs.extend(
            [landing_ref["stdout_path"], landing_ref["stderr_path"], landing_ref["command_meta"], str(landing_diff_path)]
        )
        landing_text = landing_diff_path.read_text(encoding="utf-8")
        if not landing_text.strip():
            raise RuntimeError("landing diff was empty")
        worktree_manifest = {
            "artifact_kind": "aoa.governed-run.worktree-manifest",
            "schema_version": "v1",
            "run_id": state["run_id"],
            "created_at": utc_now(),
            "attempt_label": attempt_label,
            "repo_root": str(repo_root),
            "worktree_path": str(worktree_path),
            "base_head": state["base_head"],
            "selected_target_file": selected_target_file,
            "changed_files": changed_files,
            "allowed_files": allowed_files,
            "landing_diff_sha256": sha256_digest_text(landing_text),
        }
        write_json(run_dir / "worktree.manifest.json", worktree_manifest)
        acceptance_refs, acceptance_ok = TRIALS.run_acceptance_checks(
            run_dir,
            repo_root=worktree_path,
            checks=list(playbook_policy.get("acceptance_commands") or []),
            label_prefix=f"{attempt_label}-worktree-acceptance",
        )
        artifact_refs.extend(
            path
            for ref in acceptance_refs
            for path in (ref["stdout_path"], ref["stderr_path"], ref["command_meta"])
        )
        if not acceptance_ok:
            raise ValueError("one or more acceptance checks failed in the isolated worktree")
        remove_raw = TRIALS.remove_temp_worktree(repo_root, worktree_path)
        remove_ref = TRIALS.persist_command_result(run_dir, f"{attempt_label}-worktree-remove", remove_raw)
        artifact_refs.extend([remove_ref["stdout_path"], remove_ref["stderr_path"], remove_ref["command_meta"]])
        return worktree_manifest, changed_files, artifact_refs
    except Exception:
        remove_raw = TRIALS.remove_temp_worktree(repo_root, worktree_path)
        TRIALS.persist_command_result(run_dir, f"{attempt_label}-worktree-remove", remove_raw)
        raise


def run_main_acceptance(run_dir: Path, *, repo_root: Path, playbook_policy: dict[str, Any], label_prefix: str) -> bool:
    acceptance_refs, acceptance_ok = TRIALS.run_acceptance_checks(
        run_dir,
        repo_root=repo_root,
        checks=list(playbook_policy.get("acceptance_commands") or []),
        label_prefix=label_prefix,
    )
    _ = acceptance_refs
    return acceptance_ok


def apply_landing_diff(run_dir: Path, *, state: dict[str, Any], playbook_policy: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(state["repo_root"])
    landing_diff_path = run_dir / "landing.diff"
    if not landing_diff_path.exists():
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="proposal_invalid",
            reasons=["landing.diff is missing"],
            next_action="Repeat worktree preview before attempting landing.",
        )
    try:
        TRIALS.ensure_repo_tracked_clean(repo_root)
    except RuntimeError as exc:
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="policy_denied",
            reasons=[str(exc)],
            next_action="Restore a clean tracked repo state before retrying landing.",
        )
    if TRIALS.git_head(repo_root) != state["base_head"]:
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="policy_denied",
            reasons=["base_head drifted before landing"],
            next_action="Start a new governed run from the current HEAD.",
        )
    landing_diff_text = landing_diff_path.read_text(encoding="utf-8")
    landing_diff_digest = sha256_digest_text(landing_diff_text)

    main_check_raw = TRIALS.git_command(repo_root, ["apply", "--check", str(landing_diff_path)], timeout_s=60)
    check_ref = TRIALS.persist_command_result(run_dir, "landing-apply-check", main_check_raw)
    _ = check_ref
    if main_check_raw["exit_code"] != 0 or main_check_raw["timed_out"]:
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="policy_denied",
            reasons=["landing diff did not apply cleanly back to the main checkout"],
            next_action="Start a new governed run from the current HEAD.",
        )

    main_apply_raw = TRIALS.git_command(repo_root, ["apply", str(landing_diff_path)], timeout_s=60)
    apply_ref = TRIALS.persist_command_result(run_dir, "landing-apply", main_apply_raw)
    _ = apply_ref
    if main_apply_raw["exit_code"] != 0 or main_apply_raw["timed_out"]:
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="policy_denied",
            reasons=["landing diff apply failed in the main checkout"],
            next_action="Inspect landing-apply artifacts before retrying.",
        )

    if run_main_acceptance(run_dir, repo_root=repo_root, playbook_policy=playbook_policy, label_prefix="landing-acceptance"):
        approval = load_approval(run_dir)
        approval = advance_milestone(
            approval,
            milestone="landing",
            status="approved",
            notes="Landing acceptance passed in the main checkout.",
        )
        write_json(approval_artifact(run_dir), approval)
        return pass_result(run_dir, state=state, changed_files=list(state.get("changed_files") or []))

    reverse_raw = TRIALS.git_command(repo_root, ["apply", "-R", str(landing_diff_path)], timeout_s=60)
    reverse_ref = TRIALS.persist_command_result(run_dir, "landing-rollback", reverse_raw)
    rollback_payload = {
        "artifact_kind": "aoa.governed-run.rollback-status",
        "schema_version": "v1",
        "run_id": state["run_id"],
        "updated_at": utc_now(),
        "landing_diff_sha256": landing_diff_digest,
        "reverse_exit_code": reverse_raw["exit_code"],
        "reverse_timed_out": reverse_raw["timed_out"],
        "reverse_stdout_path": reverse_ref["stdout_path"],
        "reverse_stderr_path": reverse_ref["stderr_path"],
        "reverse_command_meta": reverse_ref["command_meta"],
        "rollback_ok": reverse_raw["exit_code"] == 0 and not reverse_raw["timed_out"],
    }
    write_json(run_dir / "rollback.status.json", rollback_payload)
    if rollback_payload["rollback_ok"]:
        return failure_result(
            run_dir,
            state=state,
            phase="apply_main",
            failure_class="post_change_validation_failure",
            reasons=["main-checkout acceptance failed after landing diff apply"],
            next_action="Inspect landing acceptance artifacts and the rollback packet before retrying.",
        )
    return failure_result(
        run_dir,
        state=state,
        phase="apply_main",
        failure_class="rollback_failed",
        reasons=["main-checkout acceptance failed and rollback could not be applied cleanly"],
        next_action="Repair the checkout manually before any further governed execution.",
    )


def prepare_run(
    request_file: str | Path,
    *,
    until: str = "done",
    policy_path: str | Path | None = None,
    log_root: str | Path | None = None,
    gate_provider: Callable[[], dict[str, Any]] | None = None,
    advisory_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    proposal_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    request, request_path = load_request(request_file)
    request_path_text = str(request_path)
    target_id = str(request.get("target_id") or "")
    run_id = make_run_id()
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        canary_context = resolve_request_canary_context(request)
        policy, resolved_policy_path = load_policy(policy_path)
        advisory = resolve_playbook_id(request, policy, advisory_provider=advisory_provider)
        playbook_policy = advisory["policy"]
        repo_root = normalize_repo_root(request["repo_root"], target_id=target_id)
        ensure_policy_repo_scope(playbook_policy, repo_root, target_id=target_id)
        task_class = str(request.get("task_class") or playbook_policy.get("task_class") or "unknown")
        trust_state_snapshot = str(playbook_policy.get("trust_state") or "experimental")
    except Exception as exc:
        state = {
            "run_id": run_id,
            "target_id": target_id or infer_target_id_from_repo_root(request.get("repo_root")),
            "repo_root": str(request.get("repo_root") or ""),
            "playbook_id": request.get("playbook_id"),
            "task_class": request.get("task_class"),
            "trust_state_snapshot": "experimental",
            "canary_id": request.get("canary_id"),
            "request_path": request_path_text,
            "phase": "preflight",
            "status": "fail",
            "break_glass_used": False,
        }
        return failure_result(
            run_dir,
            state=state,
            phase="preflight",
            failure_class="policy_denied",
            reasons=[f"{type(exc).__name__}: {exc}"],
            next_action="Repair the request target, repo_root, or governed policy before preparing a new run.",
        )
    try:
        TRIALS.ensure_repo_tracked_clean(repo_root)
    except RuntimeError as exc:
        state = {
            "run_id": run_id,
            "target_id": target_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
            "request_path": request_path_text,
            "phase": "preflight",
            "status": "fail",
            "break_glass_used": False,
        }
        return failure_result(
            run_dir,
            state=state,
            phase="preflight",
            failure_class="policy_denied",
            reasons=[str(exc)],
            next_action="Restore a clean tracked repo state before preparing a governed run.",
        )

    if playbook_policy.get("enabled") is not True:
        state = {
            "run_id": run_id,
            "target_id": target_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
            "request_path": request_path_text,
            "phase": "preflight",
            "status": "fail",
            "break_glass_used": False,
        }
        return failure_result(
            run_dir,
            state=state,
            phase="preflight",
            failure_class="policy_denied",
            reasons=[f"governed execution is disabled for playbook {advisory['playbook_id']}"],
            next_action="Choose an enabled governed playbook or update the runtime policy.",
        )
    if playbook_policy.get("execution_kind") != "mutation":
        state = {
            "run_id": run_id,
            "target_id": target_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
            "request_path": request_path_text,
            "phase": "preflight",
            "status": "fail",
            "break_glass_used": False,
        }
        return failure_result(
            run_dir,
            state=state,
            phase="preflight",
            failure_class="policy_denied",
            reasons=[f"playbook {advisory['playbook_id']} is not enabled for mutation execution"],
            next_action="Choose a mutation-enabled governed playbook or update the runtime policy.",
        )
    gate_payload = (gate_provider or default_gate_provider)()
    gate_result = evaluate_autonomy_gate(
        gate_payload,
        playbook_policy=playbook_policy,
        break_glass_reason=request.get("break_glass_reason"),
        global_rules=policy["global_rules"],
    )
    if not gate_result["allowed"]:
        state = {
            "run_id": run_id,
            "target_id": target_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "request_path": request_path_text,
            "phase": "preflight",
            "status": "fail",
            "break_glass_used": False,
        }
        return failure_result(
            run_dir,
            state=state,
            phase="preflight",
            failure_class="autonomy_gate_failed",
            reasons=list(gate_result["reasons"]),
            next_action="Restore aoa-status --autonomy --json to pass or use an allowed break-glass reason.",
        )

    base_head = TRIALS.git_head(repo_root)
    state = {
        "artifact_kind": "aoa.governed-run.state",
        "schema_version": "v1",
        "run_id": run_id,
        "request_path": str(request_path),
        "target_id": target_id,
        "repo_root": str(repo_root),
        "playbook_id": advisory["playbook_id"],
        "task_class": task_class,
        "trust_state_snapshot": trust_state_snapshot,
        "canary_id": request.get("canary_id"),
        "policy_path": str(resolved_policy_path),
        "base_head": base_head,
        "phase": "prepare_proposal",
        "status": "running",
        "break_glass_used": bool(gate_result["break_glass_used"]),
        "repair_attempts": 0,
        "failure_class": None,
        "failure_reasons": [],
    }
    write_json(run_dir / "request.json", request)
    write_json(
        run_dir / "policy.snapshot.json",
        {
            "artifact_kind": "aoa.governed-run.policy-snapshot",
            "schema_version": "v1",
            "captured_at": utc_now(),
            "policy_path": str(resolved_policy_path),
            "policy_id": policy["policy_id"],
            "global_rules": policy["global_rules"],
            "target_id": target_id,
            "target_policy": advisory["target_policy"],
            "playbook_id": advisory["playbook_id"],
            "playbook_policy": playbook_policy,
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
        },
    )
    write_json(
        run_dir / "preflight.summary.json",
        {
            "artifact_kind": "aoa.governed-run.preflight-summary",
            "schema_version": "v1",
            "captured_at": utc_now(),
            "target_id": target_id,
            "repo_root": str(repo_root),
            "base_head": base_head,
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_context": canary_context,
            "break_glass_used": bool(gate_result["break_glass_used"]),
            "break_glass_reason": request.get("break_glass_reason"),
            "gate_result": gate_result,
            "gate_payload": gate_payload,
            "advisory_context": advisory,
        },
    )
    initialize_approval(run_dir, run_id=run_id, base_head=base_head)
    save_state(run_dir, state)

    try:
        proposal_payload = (proposal_provider or default_proposal_provider)(
            {
                "request": request,
                "repo_root": repo_root,
                "run_dir": run_dir,
                "playbook_id": advisory["playbook_id"],
                "advisory_context": advisory,
                "allowed_files": list(playbook_policy.get("allowed_files") or []),
                "failure_context": [],
            }
        )
        proposal_summary = write_proposal_artifacts(
            run_dir,
            proposal_payload=proposal_payload,
            allowed_files=list(playbook_policy.get("allowed_files") or []),
            base_head=base_head,
            attempt=0,
        )
        state["selected_target_file"] = proposal_summary["selected_target_file"]
        state["phase"] = "await_plan_approval"
        save_state(run_dir, state)
    except Exception as exc:
        return failure_result(
            run_dir,
            state=state,
            phase="prepare_proposal",
            failure_class="proposal_invalid",
            reasons=[f"{type(exc).__name__}: {exc}"],
            next_action="Revise the governed request or adjust the playbook allowlist before retrying.",
        )

    return paused_result(
        run_dir,
        state=state,
        phase="await_plan_approval",
        milestone="plan_freeze",
        next_action=(
            "Review proposal.summary.json and proposal.edit-spec.json, then set "
            "approval.status.json current_milestone=plan_freeze status=approved before resume."
        ),
    )


def run_preview_after_plan_approval(
    run_dir: Path,
    *,
    state: dict[str, Any],
    playbook_policy: dict[str, Any],
    request: dict[str, Any],
    proposal_provider: Callable[[dict[str, Any]], dict[str, Any]] | None,
    advisory_context: dict[str, Any],
) -> dict[str, Any]:
    repo_root = Path(state["repo_root"])
    try:
        TRIALS.ensure_repo_tracked_clean(repo_root)
    except RuntimeError as exc:
        return failure_result(
            run_dir,
            state=state,
            phase="worktree_preview",
            failure_class="policy_denied",
            reasons=[str(exc)],
            next_action="Restore a clean tracked repo state before resuming governed execution.",
        )
    if TRIALS.git_head(repo_root) != state["base_head"]:
        return failure_result(
            run_dir,
            state=state,
            phase="worktree_preview",
            failure_class="policy_denied",
            reasons=["base_head drifted before worktree preview"],
            next_action="Start a new governed run from the current HEAD.",
        )

    max_repairs = 1
    try:
        max_repairs = int(
            json.loads((run_dir / "policy.snapshot.json").read_text(encoding="utf-8"))["global_rules"]["max_worktree_repairs"]
        )
    except Exception:
        max_repairs = 1

    failure_context: list[str] = []
    for attempt in range(state.get("repair_attempts", 0), max_repairs + 1):
        if attempt > 0:
            try:
                proposal_payload = (proposal_provider or default_proposal_provider)(
                    {
                        "request": request,
                        "repo_root": repo_root,
                        "run_dir": run_dir,
                        "playbook_id": state["playbook_id"],
                        "advisory_context": advisory_context,
                        "allowed_files": list(playbook_policy.get("allowed_files") or []),
                        "failure_context": failure_context,
                    }
                )
                proposal_summary = write_proposal_artifacts(
                    run_dir,
                    proposal_payload=proposal_payload,
                    allowed_files=list(playbook_policy.get("allowed_files") or []),
                    base_head=state["base_head"],
                    attempt=attempt,
                )
                state["selected_target_file"] = proposal_summary["selected_target_file"]
                save_state(run_dir, state)
            except Exception as exc:
                return failure_result(
                    run_dir,
                    state=state,
                    phase="worktree_preview",
                    failure_class="proposal_invalid",
                    reasons=[f"{type(exc).__name__}: {exc}"],
                    next_action="Repair the proposal contract before retrying governed execution.",
                )
        try:
            worktree_manifest, changed_files, _artifact_refs = preview_proposal(
                run_dir,
                state=state,
                playbook_policy=playbook_policy,
                attempt_label=f"attempt-{attempt:02d}",
            )
            state["phase"] = "await_landing_approval"
            state["status"] = "paused"
            state["repair_attempts"] = attempt
            state["changed_files"] = changed_files
            save_state(run_dir, state)
            approval = load_approval(run_dir)
            approval = advance_milestone(
                approval,
                milestone="landing",
                status="pending",
                notes="Review landing.diff and worktree.manifest.json before setting landing to approved.",
            )
            write_json(approval_artifact(run_dir), approval)
            return paused_result(
                run_dir,
                state=state,
                phase="await_landing_approval",
                milestone="landing",
                next_action="Review landing.diff, then set approval.status.json landing status=approved before resume.",
            )
        except PermissionError as exc:
            return failure_result(
                run_dir,
                state=state,
                phase="worktree_preview",
                failure_class="scope_violation",
                reasons=[str(exc)],
                next_action="Tighten the proposal so the changed files stay inside the governed allowlist.",
            )
        except ValueError as exc:
            failure_context = [str(exc)]
            if attempt >= max_repairs or not playbook_policy.get("repair_allowed"):
                return failure_result(
                    run_dir,
                    state=state,
                    phase="worktree_preview",
                    failure_class="post_change_validation_failure",
                    reasons=[str(exc)],
                    next_action="Inspect worktree acceptance artifacts before retrying.",
                )
            state["repair_attempts"] = attempt + 1
            save_state(run_dir, state)
        except RuntimeError as exc:
            failure_context = [str(exc)]
            if attempt >= max_repairs or not playbook_policy.get("repair_allowed"):
                return failure_result(
                    run_dir,
                    state=state,
                    phase="worktree_preview",
                    failure_class="proposal_invalid",
                    reasons=[str(exc)],
                    next_action="Repair the proposal before retrying governed execution.",
                )
            state["repair_attempts"] = attempt + 1
            save_state(run_dir, state)
    return failure_result(
        run_dir,
        state=state,
        phase="worktree_preview",
        failure_class="post_change_validation_failure",
        reasons=["worktree preview exhausted the bounded repair budget"],
        next_action="Inspect preview artifacts and start a fresh governed run if needed.",
    )


def resume_run(
    run_id: str,
    *,
    until: str = "done",
    log_root: str | Path | None = None,
    advisory_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    proposal_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    request = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    policy_snapshot = json.loads((run_dir / "policy.snapshot.json").read_text(encoding="utf-8"))
    playbook_policy = policy_snapshot["playbook_policy"]
    advisory_context = json.loads((run_dir / "preflight.summary.json").read_text(encoding="utf-8"))["advisory_context"]

    if state.get("phase") in {"failed", "completed"} or state.get("status") in {"fail", "pass"}:
        existing = json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))
        save_summary(run_dir, existing, state=state)
        return json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))

    approval = load_approval(run_dir)
    approval_errors = validate_approval_against_state(approval, state)

    if approval_errors:
        return failure_result(
            run_dir,
            state=state,
            phase=str(state.get("phase") or "resume"),
            failure_class="approval_missing",
            reasons=approval_errors,
            next_action="Repair approval.status.json so run_id, base_head, and milestone state match the governed run before resuming.",
        )

    if state["phase"] == "await_plan_approval":
        if approval.get("current_milestone") != "plan_freeze" or approval.get("status") != "approved":
            return paused_result(
                run_dir,
                state=state,
                phase="await_plan_approval",
                milestone="plan_freeze",
                next_action="Set approval.status.json current_milestone=plan_freeze status=approved before resume.",
            )
        return run_preview_after_plan_approval(
            run_dir,
            state=state,
            playbook_policy=playbook_policy,
            request=request,
            proposal_provider=proposal_provider,
            advisory_context=advisory_context if advisory_provider is None else advisory_provider(request),
        )

    if state["phase"] == "await_landing_approval":
        if approval.get("current_milestone") != "landing" or approval.get("status") != "approved":
            return paused_result(
                run_dir,
                state=state,
                phase="await_landing_approval",
                milestone="landing",
                next_action="Set approval.status.json current_milestone=landing status=approved before resume.",
            )
        return apply_landing_diff(run_dir, state=state, playbook_policy=playbook_policy)

    existing = json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))
    save_summary(run_dir, existing, state=state)
    return json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))


def trust_rank(trust_state: str) -> int:
    order = {"experimental": 0, "canary_proven": 1, "trusted": 2}
    return order.get(trust_state, -1)


def evaluate_criteria(criteria: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if aggregate["pass_count"] < criteria["minimum_successful_runs"]:
        reasons.append(
            f"needs at least {criteria['minimum_successful_runs']} successful runs (has {aggregate['pass_count']})"
        )
    if aggregate["distinct_task_class_count"] < criteria["minimum_task_classes"]:
        reasons.append(
            f"needs at least {criteria['minimum_task_classes']} successful task classes (has {aggregate['distinct_task_class_count']})"
        )
    if aggregate["scope_violation_count"] > criteria["maximum_scope_violations"]:
        reasons.append(
            f"scope violations exceed allowance ({aggregate['scope_violation_count']} > {criteria['maximum_scope_violations']})"
        )
    if aggregate["rollback_failure_count"] > criteria["maximum_rollback_failures"]:
        reasons.append(
            f"rollback failures exceed allowance ({aggregate['rollback_failure_count']} > {criteria['maximum_rollback_failures']})"
        )
    if aggregate["break_glass_count"] > criteria["maximum_break_glass_runs"]:
        reasons.append(
            f"break-glass runs exceed allowance ({aggregate['break_glass_count']} > {criteria['maximum_break_glass_runs']})"
        )
    if aggregate["post_change_validation_failure_count"] > criteria["maximum_post_change_validation_failures"]:
        reasons.append(
            "post-change validation failures exceed allowance "
            f"({aggregate['post_change_validation_failure_count']} > {criteria['maximum_post_change_validation_failures']})"
        )
    return {"met": not reasons, "reasons": reasons}


def aggregate_run_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful_task_classes = sorted(
        {
            str(record.get("task_class"))
            for record in records
            if record.get("status") == "pass" and record.get("task_class")
        }
    )
    return {
        "run_count": len(records),
        "pass_count": sum(1 for record in records if record.get("status") == "pass"),
        "fail_count": sum(1 for record in records if record.get("status") == "fail"),
        "paused_count": sum(1 for record in records if record.get("status") == "paused"),
        "break_glass_count": sum(1 for record in records if record.get("break_glass_used")),
        "scope_violation_count": sum(1 for record in records if record.get("failure_class") == "scope_violation"),
        "rollback_failure_count": sum(1 for record in records if record.get("failure_class") == "rollback_failed"),
        "post_change_validation_failure_count": sum(
            1 for record in records if record.get("failure_class") == "post_change_validation_failure"
        ),
        "successful_task_classes": successful_task_classes,
        "distinct_task_class_count": len(successful_task_classes),
    }


def observed_trust_state(criteria_map: dict[str, Any], aggregate: dict[str, Any]) -> dict[str, Any]:
    trusted = evaluate_criteria(criteria_map["trusted"], aggregate)
    if trusted["met"]:
        return {"observed_trust_state": "trusted", "evidence_gate": trusted}
    canary = evaluate_criteria(criteria_map["canary_proven"], aggregate)
    if canary["met"]:
        return {"observed_trust_state": "canary_proven", "evidence_gate": canary}
    return {"observed_trust_state": "experimental", "evidence_gate": canary}


def filter_records_since_run_id(records: list[dict[str, Any]], since_run_id: str | None) -> list[dict[str, Any]]:
    if not since_run_id:
        return records
    return [record for record in records if str(record.get("run_id") or "") >= since_run_id]


def promotion_summary(records: list[dict[str, Any]], policy: dict[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return {
            "available": False,
            "reason": "policy_unavailable",
        }
    criteria_map = (policy.get("global_rules") or {}).get("promotion_criteria") or {}
    target_summaries: dict[str, Any] = {}
    for target_id, target_entry in (policy.get("targets") or {}).items():
        playbook_summaries: dict[str, Any] = {}
        for playbook_id, entry in (target_entry.get("playbooks") or {}).items():
            matching = [
                record
                for record in records
                if record.get("target_id") == target_id and record.get("playbook_id") == playbook_id
            ]
            evidence_since_run_id = str(entry.get("evidence_since_run_id") or "").strip() or None
            matching = filter_records_since_run_id(matching, evidence_since_run_id)
            aggregate = aggregate_run_records(matching)
            observed = observed_trust_state(criteria_map, aggregate)
            configured = str(entry.get("trust_state") or "experimental")
            recommended_next_state = configured
            if trust_rank(observed["observed_trust_state"]) > trust_rank(configured):
                recommended_next_state = observed["observed_trust_state"]
            playbook_summaries[playbook_id] = {
                "configured_trust_state": configured,
                "observed_trust_state": observed["observed_trust_state"],
                "recommended_next_state": recommended_next_state,
                "task_class": entry.get("task_class"),
                "evidence_since_run_id": evidence_since_run_id,
                "aggregate": aggregate,
                "evidence_gate": observed["evidence_gate"],
                "recommended_action": (
                    f"Promote {playbook_id}@{target_id} from {configured} to {recommended_next_state}."
                    if recommended_next_state != configured
                    else f"Keep {playbook_id}@{target_id} at {configured} until more governed evidence lands."
                ),
            }
        target_summaries[target_id] = {
            "repo_scope": target_entry.get("repo_scope"),
            "default_repo_root": target_entry.get("default_repo_root"),
            "playbooks": playbook_summaries,
        }
    gate_criteria = (policy.get("global_rules") or {}).get("repo_scope_expansion_gate") or {}
    global_aggregate = aggregate_run_records(records)
    gate = evaluate_criteria(gate_criteria, global_aggregate)
    return {
        "available": True,
        "criteria": criteria_map,
        "targets": target_summaries,
        "repo_scope_expansion_gate": {
            "met": gate["met"],
            "aggregate": global_aggregate,
            "reasons": gate["reasons"],
            "recommended_action": (
                "Do not widen governed repo scope yet."
                if gate["reasons"]
                else "Repo-scope expansion gate is green; widening can be reviewed deliberately."
            ),
        },
    }


def build_run_record(run_dir: Path) -> dict[str, Any]:
    state = load_state(run_dir)
    approval = load_approval(run_dir) if approval_artifact(run_dir).exists() else None
    summary = load_summary_or_synthesize(run_dir, state, approval)
    triage = summary.get("triage") or compute_triage(state, summary, approval)
    target_id = state.get("target_id") or infer_target_id_from_repo_root(state.get("repo_root"))
    return {
        "run_id": state.get("run_id") or run_dir.name,
        "phase": state.get("phase"),
        "status": summary.get("status") or state.get("status"),
        "target_id": target_id,
        "playbook_id": state.get("playbook_id"),
        "task_class": state.get("task_class"),
        "trust_state_snapshot": state.get("trust_state_snapshot"),
        "canary_id": state.get("canary_id"),
        "repo_root": state.get("repo_root"),
        "request_path": state.get("request_path"),
        "updated_at": state.get("updated_at") or summary.get("updated_at"),
        "break_glass_used": bool(summary.get("break_glass_used") or state.get("break_glass_used")),
        "failure_class": summary.get("failure_class"),
        "review_packet_audit_verdict": ((summary.get("review_packets") or {}).get("audit_verdict")),
        "triage": triage,
    }


def load_policy_or_none(policy_path: str | Path | None = None) -> dict[str, Any] | None:
    try:
        policy, _ = load_policy(policy_path)
        return policy
    except Exception:
        return None


def render_run_index_explain(payload: dict[str, Any]) -> str:
    lines = [
        "# governed-run status index",
        "",
        f"- runs: `{payload.get('run_count')}`",
    ]
    triage = payload.get("operator_triage") or {}
    if triage:
        lines.append(f"- active_blocked_lineages: `{triage.get('blocked_run_count')}`")
        lines.append(f"- latest_operator_action: `{triage.get('recommended_action')}`")
    gate = (payload.get("promotion_summary") or {}).get("repo_scope_expansion_gate") or {}
    if gate:
        lines.extend(
            [
                "",
                "## Repo Scope Gate",
                "",
                f"- met: `{gate.get('met')}`",
                f"- recommended_action: `{gate.get('recommended_action')}`",
            ]
        )
    targets = (payload.get("promotion_summary") or {}).get("targets") or {}
    if targets:
        lines.extend(["", "## Targets", ""])
        for target_id, target_payload in sorted(targets.items()):
            lines.append(f"- {target_id}:")
            playbooks = target_payload.get("playbooks") or {}
            for playbook_id, item in sorted(playbooks.items()):
                lines.append(
                    f"  {playbook_id}: configured=`{item.get('configured_trust_state')}` observed=`{item.get('observed_trust_state')}` recommended=`{item.get('recommended_next_state')}`"
                )
    return "\n".join(lines)


def render_status_explain(payload: dict[str, Any]) -> str:
    state = payload.get("state") or {}
    summary = payload.get("summary") or {}
    triage = payload.get("triage") or {}
    review_packets = summary.get("review_packets") or {}
    review_packet_audit = payload.get("review_packet_audit") or {}
    review_handoff_bundle = payload.get("review_handoff_bundle") or {}
    blocked_packet_kinds = review_packets.get("blocked_packet_kinds")
    if not isinstance(blocked_packet_kinds, list):
        blocked_packet_kinds = [
            entry.get("packet_kind")
            for entry in review_packet_audit.get("packet_statuses", [])
            if isinstance(entry, dict) and entry.get("status") in {"missing", "stale"}
        ]
    recommended_review_targets = review_packets.get("recommended_review_targets")
    if not isinstance(recommended_review_targets, list):
        recommended_review_targets = review_packet_audit.get("recommended_review_targets") or []
    grouped_review_targets = review_packets.get("grouped_review_targets")
    if not isinstance(grouped_review_targets, dict):
        grouped_review_targets = review_handoff_bundle.get("recommended_review_targets") or {}
    safe_replay_command = review_packets.get("safe_replay_command") or review_packet_audit.get("safe_replay_command")
    lines = [
        f"# governed-run `{payload.get('run_id')}`",
        "",
        f"- status: `{summary.get('status')}`",
        f"- phase: `{state.get('phase')}`",
        f"- target_id: `{state.get('target_id')}`",
        f"- playbook_id: `{state.get('playbook_id')}`",
        f"- task_class: `{state.get('task_class')}`",
        f"- trust_state_snapshot: `{state.get('trust_state_snapshot')}`",
        f"- resumable: `{triage.get('resumable')}`",
        f"- operator_action_required: `{triage.get('operator_action_required')}`",
        f"- blocked_reason: `{triage.get('blocked_reason')}`",
        f"- review_packet_ready: `{review_packets.get('ready')}`",
        f"- emitted_review_packets: `{review_packets.get('emitted_candidate_artifact_count')}`",
        f"- audit_verdict: `{review_packets.get('audit_verdict') or review_packet_audit.get('audit_verdict')}`",
        f"- handoff_readiness: `{review_packets.get('handoff_readiness') or review_handoff_bundle.get('handoff_readiness')}`",
        "",
        "## Next Action",
        "",
        str(triage.get("recommended_action") or summary.get("next_action") or "None."),
    ]
    if review_packets.get("manifest_ref"):
        lines.extend(["", "## Review Packets", "", f"- manifest: `{review_packets['manifest_ref']}`"])
        if review_packets.get("advisory_trace_ref"):
            lines.append(f"- advisory_trace: `{review_packets['advisory_trace_ref']}`")
        if review_packets.get("audit_ref") or review_packet_audit.get("review_packet_audit_ref"):
            lines.append(
                f"- audit: `{review_packets.get('audit_ref') or review_packet_audit.get('review_packet_audit_ref')}`"
            )
        if review_packets.get("handoff_ref"):
            lines.append(f"- handoff: `{review_packets.get('handoff_ref')}`")
        if blocked_packet_kinds:
            lines.append(
                "- blocked_packet_kinds: `"
                + ", ".join(str(item) for item in blocked_packet_kinds if isinstance(item, str) and item)
                + "`"
            )
        if recommended_review_targets:
            lines.append("- recommended_review_targets:")
            for item in recommended_review_targets:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"  {item.get('owner_repo')}: `{item.get('ref')}`"
                    + (f" ({item.get('why')})" if item.get("why") else "")
                )
        if grouped_review_targets:
            lines.append("- grouped_review_targets:")
            for owner_repo, refs in grouped_review_targets.items():
                lines.append(f"  {owner_repo}:")
                for ref_entry in refs:
                    if not isinstance(ref_entry, dict):
                        continue
                    line = f"    `{ref_entry.get('ref')}`"
                    if ref_entry.get("why"):
                        line += f" ({ref_entry.get('why')})"
                    lines.append(line)
    if triage.get("safe_resume_command"):
        lines.extend(["", "## Safe Resume", "", f"`{triage['safe_resume_command']}`"])
    if safe_replay_command:
        lines.extend(["", "## Safe Replay", "", f"- safe_replay_command: `{safe_replay_command}`"])
    return "\n".join(lines)


def request_lineage_key(request_path: Any) -> str:
    path_text = str(request_path or "").strip()
    if not path_text:
        return ""
    return REQUEST_RETRY_SUFFIX_RE.sub("", Path(path_text).name)


def request_lineage_group_key(run: dict[str, Any]) -> str:
    target_id = str(run.get("target_id") or infer_target_id_from_repo_root(run.get("repo_root")) or "")
    lineage = request_lineage_key(run.get("request_path"))
    if not lineage:
        return ""
    return f"{target_id}:{lineage}" if target_id else lineage


def freshest_runs_by_request_lineage(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    representatives: dict[str, dict[str, Any]] = {}
    ungrouped: list[dict[str, Any]] = []
    for run in runs:
        lineage = request_lineage_group_key(run)
        if not lineage:
            ungrouped.append(run)
            continue
        existing = representatives.get(lineage)
        if existing is None or str(run.get("updated_at") or "") > str(existing.get("updated_at") or ""):
            representatives[lineage] = run
    return sorted(
        [*representatives.values(), *ungrouped],
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )


def list_runs(*, log_root: str | Path | None = None, policy_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(log_root or LOG_ROOT_DEFAULT)
    runs: list[dict[str, Any]] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            state_path = state_artifact(child)
            if not state_path.exists():
                continue
            runs.append(build_run_record(child))
    freshest_runs = freshest_runs_by_request_lineage(runs)
    blocked_runs = [run for run in freshest_runs if (run.get("triage") or {}).get("operator_action_required")]
    latest_blocked = blocked_runs[:1]
    triage_summary = {
        "blocked_run_count": len(blocked_runs),
        "blocked_run_ids": [run["run_id"] for run in blocked_runs],
        "recommended_action": (
            latest_blocked[0]["triage"]["recommended_action"]
            if latest_blocked
            else "No operator action required."
        ),
    }
    promotion = promotion_summary(runs, load_policy_or_none(policy_path))
    return {
        "artifact_kind": "aoa.governed-run.status-index",
        "schema_version": "v1",
        "run_count": len(runs),
        "runs": runs,
        "operator_triage": triage_summary,
        "promotion_summary": promotion,
    }


def status_run(run_id: str, *, log_root: str | Path | None = None) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    approval = load_approval(run_dir)
    summary = load_summary_or_synthesize(run_dir, state, approval)
    triage = summary.get("triage") or compute_triage(state, summary, approval)
    review_packet_audit = load_json_if_exists(review_packet_audit_artifact(run_dir))
    review_handoff_bundle = load_json_if_exists(review_handoff_bundle_artifact(run_dir))
    return {
        "artifact_kind": "aoa.governed-run.status",
        "schema_version": "v1",
        "run_id": run_id,
        "state": state,
        "summary": summary,
        "approval": approval,
        "triage": triage,
        "review_packet_audit": review_packet_audit,
        "review_handoff_bundle": review_handoff_bundle,
    }
