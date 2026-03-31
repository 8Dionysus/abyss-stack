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
SCRIPT_ROOT = SCRIPT_PATH.parents[1]
STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/abyss-stack"))
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
REQUEST_RETRY_SUFFIX_RE = re.compile(r"-retry\d+(?=(?:\.[^.]+)+$|$)")


def load_trials_module() -> Any:
    target = SCRIPT_ROOT / "scripts" / "aoa-local-ai-trials"
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
    if not isinstance(policy.get("playbooks"), dict) or not policy["playbooks"]:
        raise RuntimeError("policy playbooks must contain at least one entry")
    for playbook_id, entry in policy["playbooks"].items():
        if not isinstance(entry, dict):
            raise RuntimeError(f"policy entry for {playbook_id} must be an object")
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
                raise RuntimeError(f"policy entry for {playbook_id} is missing {required}")
        if entry.get("trust_state") not in TRUST_STATES:
            raise RuntimeError(f"policy entry for {playbook_id} has invalid trust_state")
        if not isinstance(entry.get("task_class"), str) or not entry["task_class"].strip():
            raise RuntimeError(f"policy entry for {playbook_id} must declare a non-empty task_class")


def validate_canary_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("surface_type") != "runtime_governed_execution_canary_catalog":
        raise RuntimeError("governed canary catalog surface_type must equal runtime_governed_execution_canary_catalog")
    if catalog.get("repo_scope") != "abyss-stack":
        raise RuntimeError("governed canary catalog repo_scope must remain abyss-stack")
    canaries = catalog.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        raise RuntimeError("governed canary catalog must contain at least one canary")
    seen: set[str] = set()
    for entry in canaries:
        if not isinstance(entry, dict):
            raise RuntimeError("governed canary entries must be objects")
        for required in ("canary_id", "title", "goal", "playbook_id", "task_class", "profile_class"):
            value = entry.get(required)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeError(f"governed canary entry is missing a non-empty {required}")
        canary_id = str(entry["canary_id"])
        if canary_id in seen:
            raise RuntimeError(f"duplicate canary_id in governed canary catalog: {canary_id}")
        seen.add(canary_id)
        if entry["task_class"] not in {
            "docs_only",
            "policy_surface",
            "validation_tightening",
            "governed_lane",
        }:
            raise RuntimeError(f"unsupported canary task_class for {canary_id}: {entry['task_class']}")


def is_abyss_stack_checkout(path: Path) -> bool:
    return (
        (path / "CONTRIBUTING.md").exists()
        and (path / "scripts" / "validate_stack.py").exists()
        and (path / "docs" / "DEPLOYMENT.md").exists()
    )


def resolve_default_repo_root() -> Path:
    candidates = []
    env_root = os.environ.get("AOA_SOURCE_ROOT")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    if is_abyss_stack_checkout(SCRIPT_ROOT):
        candidates.append(SCRIPT_ROOT)
    candidates.append(Path.home() / "src" / "abyss-stack")
    for candidate in candidates:
        if is_abyss_stack_checkout(candidate):
            return candidate.resolve()
    return SCRIPT_ROOT.resolve()


def default_request_template() -> dict[str, Any]:
    return {
        "goal": "Describe the bounded abyss-stack change you want to propose.",
        "playbook_id": "AOA-P-0011",
        "profile_class": DEFAULT_PROFILE_CLASS,
        "repo_root": str(resolve_default_repo_root()),
        "memo": None,
        "break_glass_reason": None,
        "canary_id": None,
        "task_class": None,
    }


def validate_request_shape(request: dict[str, Any]) -> None:
    if not isinstance(request.get("goal"), str) or not request["goal"].strip():
        raise RuntimeError("request goal must be a non-empty string")
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
    payload: dict[str, Any] = {
        "goal": canary["goal"],
        "playbook_id": canary["playbook_id"],
        "profile_class": canary.get("profile_class") or DEFAULT_PROFILE_CLASS,
        "repo_root": str(Path(repo_root).expanduser().resolve()) if repo_root is not None else str(resolve_default_repo_root()),
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
    if request.get("playbook_id") and request["playbook_id"] != canary["playbook_id"]:
        raise RuntimeError("request playbook_id does not match the selected canary")
    if request.get("task_class") and request["task_class"] != canary["task_class"]:
        raise RuntimeError("request task_class does not match the selected canary")
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
    playbook_id = advisory.get("playbook_id") or request.get("playbook_id")
    if not isinstance(playbook_id, str) or not playbook_id:
        raise RuntimeError("could not resolve playbook_id for governed execution")
    playbook_policy = resolve_playbook_policy(policy, playbook_id)
    advisory["playbook_id"] = playbook_id
    advisory["policy"] = copy.deepcopy(playbook_policy)
    return advisory


def resolve_playbook_policy(policy: dict[str, Any], playbook_id: str) -> dict[str, Any]:
    playbooks = policy.get("playbooks") or {}
    entry = playbooks.get(playbook_id)
    if not isinstance(entry, dict):
        raise RuntimeError(f"playbook {playbook_id} is not present in governed execution policy")
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


def normalize_repo_root(path: str | Path) -> Path:
    repo_root = Path(path).expanduser().resolve()
    if not is_abyss_stack_checkout(repo_root):
        raise RuntimeError(f"repo_root is not an abyss-stack checkout: {repo_root}")
    return repo_root


def matches_allowed_pattern(relative_path: str, pattern: str) -> bool:
    return PurePosixPath(relative_path).match(pattern)


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
    for raw in re.findall(r"`([^`]+)`|([A-Za-z0-9_./-]{4,})", goal):
        token = (raw[0] or raw[1]).strip().lower()
        if "/" not in token and "." not in token:
            continue
        if token.startswith("--"):
            continue
        if token and token not in hints:
            hints.append(token)
    return hints


def narrow_candidate_files(candidate_files: list[str], *, goal: str) -> list[str]:
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
    extra_code_requirements: list[str] = []
    if target_file.endswith(".py"):
        logic_focus_terms = focus_terms_from_goal(request["goal"], target_file=target_file)
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
            extra_code_requirements.append(
                "- for request-lineage or latest-operator-action goals, prefer changing `list_runs` aggregation first; only extend `build_run_record` when the same patch immediately consumes that new field inside `list_runs`"
            )
            extra_code_requirements.append(
                "- each governed run state already records `request_path`; prefer a single localized change inside `list_runs` that reads the existing state field instead of adding a helper-only field elsewhere"
            )
            extra_code_requirements.append(
                "- `operator_triage.latest_operator_action` is rendered through the existing `triage_summary[\"recommended_action\"]` path here; do not reference a separate `operator_triage` field or introduce a standalone `latest_operator_action` local"
            )
            extra_code_requirements.append(
                '- preserve the current `triage_summary` dict shape; do not add a sibling `"latest_operator_action"` key here'
            )
            extra_code_requirements.append(
                '- prefer changing the upstream `blocked_runs` / `latest_blocked` lineage selection so the existing `"recommended_action": (` block reads the correct freshest lineage'
            )
            extra_code_requirements.append(
                '- do not change only the fallback string or return a no-op edit; materially change which run becomes `latest_blocked`'
            )
            extra_code_requirements.append(
                '- do not sort by the raw `request_path` string; derive a lineage key from the request filename and strip any `-retry<number>` suffix before comparing runs'
            )
            extra_code_requirements.append(
                '- keep the freshest run by `updated_at` within each request lineage first, then choose `latest_blocked` from those lineage representatives'
            )
            extra_code_requirements.append(
                '- rewrite the existing `"recommended_action": (` expression inline; do not insert a new `latest_operator_action = ...` line between `latest_blocked` and `triage_summary`'
            )
            extra_code_requirements.append(
                '- prefer an `exact_replace` of the current `"recommended_action": (` block or a very short anchored replace around that block instead of adding a preparatory assignment'
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
    if extra_code_requirements:
        extra_requirements_block = "\n" + "\n".join(extra_code_requirements)
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


def default_proposal_provider(context: dict[str, Any]) -> dict[str, Any]:
    run_dir = context.get("run_dir")
    fixture_path = os.environ.get("AOA_GOVERNED_EXECUTION_PROPOSAL_PATH")
    if fixture_path:
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("fixture proposal payload must be an object")
        selected_target_file = str(payload.get("selected_target_file") or payload.get("target_file") or "")
        spec = normalize_edit_spec(
            payload.get("spec") or payload,
            selected_target_file=selected_target_file,
        )
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
        edit_max_tokens = 180 if selected_target_file.endswith(".py") else 220
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
            spec = normalize_edit_spec(parsed_spec, selected_target_file=selected_target_file)
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


def ensure_policy_repo_scope(playbook_policy: dict[str, Any], repo_root: Path) -> None:
    if playbook_policy.get("repo_scope") != "abyss-stack":
        raise RuntimeError("playbook policy repo_scope must stay abyss-stack")
    if not is_abyss_stack_checkout(repo_root):
        raise RuntimeError(f"repo_root is outside the first governed scope: {repo_root}")


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


def pass_result(
    run_dir: Path,
    *,
    state: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any]:
    summary = make_pass_summary(
        run_id=state["run_id"],
        phase="completed",
        changed_files=changed_files,
        break_glass_used=bool(state.get("break_glass_used")),
        next_action="Governed execution landed successfully.",
    )
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
    canary_context = resolve_request_canary_context(request)
    policy, resolved_policy_path = load_policy(policy_path)
    advisory = resolve_playbook_id(request, policy, advisory_provider=advisory_provider)
    playbook_policy = advisory["policy"]
    repo_root = normalize_repo_root(request["repo_root"])
    ensure_policy_repo_scope(playbook_policy, repo_root)
    task_class = str(request.get("task_class") or playbook_policy.get("task_class") or "unknown")
    trust_state_snapshot = str(playbook_policy.get("trust_state") or "experimental")
    try:
        TRIALS.ensure_repo_tracked_clean(repo_root)
    except RuntimeError as exc:
        run_id = make_run_id()
        run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "run_id": run_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
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

    run_id = make_run_id()
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if playbook_policy.get("enabled") is not True:
        state = {
            "run_id": run_id,
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
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
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
            "task_class": task_class,
            "trust_state_snapshot": trust_state_snapshot,
            "canary_id": request.get("canary_id"),
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
            "repo_root": str(repo_root),
            "playbook_id": advisory["playbook_id"],
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


def promotion_summary(records: list[dict[str, Any]], policy: dict[str, Any] | None) -> dict[str, Any]:
    if policy is None:
        return {
            "available": False,
            "reason": "policy_unavailable",
        }
    criteria_map = (policy.get("global_rules") or {}).get("promotion_criteria") or {}
    playbook_summaries: dict[str, Any] = {}
    for playbook_id, entry in (policy.get("playbooks") or {}).items():
        matching = [record for record in records if record.get("playbook_id") == playbook_id]
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
            "aggregate": aggregate,
            "evidence_gate": observed["evidence_gate"],
            "recommended_action": (
                f"Promote {playbook_id} from {configured} to {recommended_next_state}."
                if recommended_next_state != configured
                else f"Keep {playbook_id} at {configured} until more governed evidence lands."
            ),
        }
    gate_criteria = (policy.get("global_rules") or {}).get("repo_scope_expansion_gate") or {}
    global_aggregate = aggregate_run_records(records)
    gate = evaluate_criteria(gate_criteria, global_aggregate)
    return {
        "available": True,
        "criteria": criteria_map,
        "playbooks": playbook_summaries,
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
    return {
        "run_id": state.get("run_id") or run_dir.name,
        "phase": state.get("phase"),
        "status": summary.get("status") or state.get("status"),
        "playbook_id": state.get("playbook_id"),
        "task_class": state.get("task_class"),
        "trust_state_snapshot": state.get("trust_state_snapshot"),
        "canary_id": state.get("canary_id"),
        "repo_root": state.get("repo_root"),
        "request_path": state.get("request_path"),
        "updated_at": state.get("updated_at") or summary.get("updated_at"),
        "break_glass_used": bool(summary.get("break_glass_used") or state.get("break_glass_used")),
        "failure_class": summary.get("failure_class"),
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
        lines.append(f"- blocked_runs: `{triage.get('blocked_run_count')}`")
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
    playbooks = (payload.get("promotion_summary") or {}).get("playbooks") or {}
    if playbooks:
        lines.extend(["", "## Playbooks", ""])
        for playbook_id, item in sorted(playbooks.items()):
            lines.append(
                f"- {playbook_id}: configured=`{item.get('configured_trust_state')}` observed=`{item.get('observed_trust_state')}` recommended=`{item.get('recommended_next_state')}`"
            )
    return "\n".join(lines)


def render_status_explain(payload: dict[str, Any]) -> str:
    state = payload.get("state") or {}
    summary = payload.get("summary") or {}
    triage = payload.get("triage") or {}
    lines = [
        f"# governed-run `{payload.get('run_id')}`",
        "",
        f"- status: `{summary.get('status')}`",
        f"- phase: `{state.get('phase')}`",
        f"- playbook_id: `{state.get('playbook_id')}`",
        f"- task_class: `{state.get('task_class')}`",
        f"- trust_state_snapshot: `{state.get('trust_state_snapshot')}`",
        f"- resumable: `{triage.get('resumable')}`",
        f"- operator_action_required: `{triage.get('operator_action_required')}`",
        f"- blocked_reason: `{triage.get('blocked_reason')}`",
        "",
        "## Next Action",
        "",
        str(triage.get("recommended_action") or summary.get("next_action") or "None."),
    ]
    if triage.get("safe_resume_command"):
        lines.extend(["", "## Safe Resume", "", f"`{triage['safe_resume_command']}`"])
    return "\n".join(lines)


def request_lineage_key(request_path: Any) -> str:
    path_text = str(request_path or "").strip()
    if not path_text:
        return ""
    return REQUEST_RETRY_SUFFIX_RE.sub("", Path(path_text).name)


def freshest_runs_by_request_lineage(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    representatives: dict[str, dict[str, Any]] = {}
    ungrouped: list[dict[str, Any]] = []
    for run in runs:
        lineage = request_lineage_key(run.get("request_path"))
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
    blocked_runs = [run for run in runs if (run.get("triage") or {}).get("operator_action_required")]
    latest_blocked = freshest_runs_by_request_lineage(blocked_runs)
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
    return {
        "artifact_kind": "aoa.governed-run.status",
        "schema_version": "v1",
        "run_id": run_id,
        "state": state,
        "summary": summary,
        "approval": approval,
        "triage": triage,
    }
