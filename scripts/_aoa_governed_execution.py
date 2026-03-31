#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
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
DEFAULT_PROFILE_CLASS = "workhorse"
FAILURE_CLASSES = {
    "autonomy_gate_failed",
    "policy_denied",
    "approval_missing",
    "scope_violation",
    "proposal_invalid",
    "post_change_validation_failure",
    "rollback_failed",
}


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
        ):
            if required not in entry:
                raise RuntimeError(f"policy entry for {playbook_id} is missing {required}")


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


def load_request(path: str | Path) -> tuple[dict[str, Any], Path]:
    request_path = Path(path).expanduser()
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("request file must contain a JSON object")
    validate_request_shape(payload)
    return payload, request_path


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


def compact_excerpt(text: str, *, char_limit: int = 5000) -> str:
    stripped = text.strip()
    if len(stripped) <= char_limit:
        return stripped
    head = stripped[: char_limit // 2]
    tail = stripped[-(char_limit // 2) :]
    return head.rstrip() + "\n...\n" + tail.lstrip()


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

        Goal:
        {request["goal"]}

        Playbook:
        - {playbook_id}

        Recent failure context:
        {failure_block}

        Current file content:
        ```text
        {compact_excerpt(target_text)}
        ```
        """
    ).rstrip() + "\n"


def run_federated_prompt(prompt: str, request: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_text": prompt,
        "temperature": 0.0,
        "max_tokens": 700,
        "profile_class": request["profile_class"],
    }
    if request.get("playbook_id"):
        payload["playbook_id"] = request["playbook_id"]
    if request.get("playbook_select"):
        payload["playbook_select"] = request["playbook_select"]
    if request.get("memo") is not None:
        payload["memo"] = request["memo"]
    return http_post_json(f"{LANGCHAIN_API_BASE_URL}/run/federated", payload, timeout_s=180.0)


def normalize_edit_spec(spec: dict[str, Any], *, selected_target_file: str) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise RuntimeError("proposal spec must be an object")
    mode = spec.get("mode")
    if mode not in {"exact_replace", "anchored_replace"}:
        raise RuntimeError("proposal mode must be exact_replace or anchored_replace")
    target_file = spec.get("target_file")
    if not isinstance(target_file, str) or target_file != selected_target_file:
        raise RuntimeError("proposal target_file must match the selected target file")
    old_text = spec.get("old_text")
    new_text = spec.get("new_text")
    if not isinstance(old_text, str) or not old_text:
        raise RuntimeError("proposal old_text must be a non-empty string")
    if not isinstance(new_text, str):
        raise RuntimeError("proposal new_text must be a string")
    if old_text == new_text:
        raise RuntimeError("proposal old_text and new_text must differ")
    payload = {
        "mode": mode,
        "target_file": selected_target_file,
        "old_text": old_text,
        "new_text": new_text,
    }
    if mode == "anchored_replace":
        anchor_before = spec.get("anchor_before")
        anchor_after = spec.get("anchor_after")
        if not isinstance(anchor_before, str) or not anchor_before:
            raise RuntimeError("proposal anchor_before must be a non-empty string")
        if not isinstance(anchor_after, str) or not anchor_after:
            raise RuntimeError("proposal anchor_after must be a non-empty string")
        payload["anchor_before"] = anchor_before
        payload["anchor_after"] = anchor_after
    return payload


def default_proposal_provider(context: dict[str, Any]) -> dict[str, Any]:
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

    target_prompt = build_target_selection_prompt(
        request=context["request"],
        playbook_id=context["playbook_id"],
        candidate_files=candidate_files,
        advisory_context=context["advisory_context"],
        failure_context=context.get("failure_context") or [],
    )
    target_response = run_federated_prompt(target_prompt, context["request"])
    target_answer = str(target_response.get("answer") or "")
    selected_payload = json.loads(TRIALS.extract_json_block(target_answer))
    if not isinstance(selected_payload, dict):
        raise RuntimeError("target selection response did not contain a JSON object")
    selected_target_file = str(selected_payload.get("target_file") or "")
    if selected_target_file not in candidate_files:
        raise RuntimeError("target selection chose a file outside the governed allowlist")

    target_text = (context["repo_root"] / selected_target_file).read_text(encoding="utf-8")
    edit_prompt = build_edit_spec_prompt(
        request=context["request"],
        playbook_id=context["playbook_id"],
        target_file=selected_target_file,
        target_text=target_text,
        failure_context=context.get("failure_context") or [],
    )
    edit_response = run_federated_prompt(edit_prompt, context["request"])
    edit_answer = str(edit_response.get("answer") or "")
    parsed_spec = json.loads(TRIALS.extract_json_block(edit_answer))
    spec = normalize_edit_spec(parsed_spec, selected_target_file=selected_target_file)
    return {
        "provider": "langchain-api",
        "selected_target_file": selected_target_file,
        "spec": spec,
        "candidate_files": candidate_files,
        "target_prompt": target_prompt,
        "edit_prompt": edit_prompt,
        "target_answer": target_answer,
        "edit_answer": edit_answer,
        "notes": ["Proposal generated through langchain-api /run/federated."],
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


def update_report(run_dir: Path, summary: dict[str, Any], state: dict[str, Any] | None = None) -> None:
    lines = [
        f"# governed-run `{summary['run_id']}`",
        "",
        f"- status: `{summary['status']}`",
        f"- phase: `{summary.get('phase')}`",
    ]
    if state is not None:
        lines.append(f"- repo_root: `{state.get('repo_root')}`")
        lines.append(f"- playbook_id: `{state.get('playbook_id')}`")
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
    lines.extend(["", "## Next Action", "", summary.get("next_action") or "None."])
    write_text(report_artifact(run_dir), "\n".join(lines))


def load_state(run_dir: Path) -> dict[str, Any]:
    return json.loads(state_artifact(run_dir).read_text(encoding="utf-8"))


def load_approval(run_dir: Path) -> dict[str, Any]:
    return json.loads(approval_artifact(run_dir).read_text(encoding="utf-8"))


def save_state(run_dir: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    write_json(state_artifact(run_dir), state)


def save_summary(run_dir: Path, summary: dict[str, Any], state: dict[str, Any] | None = None) -> None:
    write_json(result_artifact(run_dir), summary)
    update_report(run_dir, summary, state=state)


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
    return summary


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
    return summary


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
    return summary


def apply_edit_spec_in_place(repo_root: Path, *, selected_target_file: str, spec: dict[str, Any]) -> None:
    target_path = repo_root / selected_target_file
    original_text = target_path.read_text(encoding="utf-8")
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
        raise RuntimeError(f"{mode} was not uniquely applicable to {selected_target_file}")
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
    policy, resolved_policy_path = load_policy(policy_path)
    advisory = resolve_playbook_id(request, policy, advisory_provider=advisory_provider)
    playbook_policy = advisory["policy"]
    repo_root = normalize_repo_root(request["repo_root"])
    ensure_policy_repo_scope(playbook_policy, repo_root)
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
    approval = load_approval(run_dir)

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
    return existing


def list_runs(*, log_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(log_root or LOG_ROOT_DEFAULT)
    runs: list[dict[str, Any]] = []
    if root.exists():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            state_path = state_artifact(child)
            if not state_path.exists():
                continue
            state = json.loads(state_path.read_text(encoding="utf-8"))
            runs.append(
                {
                    "run_id": state.get("run_id") or child.name,
                    "phase": state.get("phase"),
                    "status": state.get("status"),
                    "playbook_id": state.get("playbook_id"),
                    "repo_root": state.get("repo_root"),
                    "updated_at": state.get("updated_at"),
                }
            )
    return {
        "artifact_kind": "aoa.governed-run.status-index",
        "schema_version": "v1",
        "run_count": len(runs),
        "runs": runs,
    }


def status_run(run_id: str, *, log_root: str | Path | None = None) -> dict[str, Any]:
    run_dir = Path(log_root or LOG_ROOT_DEFAULT) / run_id
    state = load_state(run_dir)
    summary = json.loads(result_artifact(run_dir).read_text(encoding="utf-8"))
    approval = load_approval(run_dir)
    return {
        "artifact_kind": "aoa.governed-run.status",
        "schema_version": "v1",
        "run_id": run_id,
        "state": state,
        "summary": summary,
        "approval": approval,
    }
