#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.machinery
import importlib.util
import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

try:
    from langgraph.graph import END, START, StateGraph
    from langgraph.types import Command
except ImportError as exc:  # pragma: no cover - guarded by runtime usage
    raise SystemExit(
        "langgraph is not installed. Install dependencies from "
        "`mechanics/inference-pilots/parts/langgraph-pilot/requirements.txt` first."
    ) from exc


DEFAULT_PROGRAM_ID = "langgraph-sidecar-pilot-v1"
FIXTURE_PROGRAM_ID = "langgraph-sidecar-llamacpp-v1"
PROGRAM_ID = DEFAULT_PROGRAM_ID
MODEL = "qwen3.5:9b"
DEFAULT_LANGCHAIN_RUN_URL = "http://127.0.0.1:5403/run"
LANGCHAIN_RUN_URL = DEFAULT_LANGCHAIN_RUN_URL

def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "scripts").is_dir() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError(f"could not find abyss-stack root from {start}")


SOURCE_ROOT = find_repo_root(Path(__file__).resolve().parent)
LOCAL_TRIALS_PART = SOURCE_ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials"
if str(LOCAL_TRIALS_PART) not in sys.path:
    sys.path.insert(0, str(LOCAL_TRIALS_PART))

import trial_compatibility_bridge as TRIAL_ADAPTER  # noqa: E402

EDIT_GATE_WIRE_ID = TRIAL_ADAPTER.EDIT_GATE.wire_id
EDIT_GATE_INDEX_NAME = TRIAL_ADAPTER.EDIT_GATE_INDEX_STEM
EDIT_GATE_CLOSEOUT_NAME = TRIAL_ADAPTER.EDIT_GATE.closeout_name or ""
STACK_ROOT = Path("/srv/AbyssOS/abyss-stack")
CONFIGS_ROOT = STACK_ROOT / "Configs"
SCRIPTS_ROOT = CONFIGS_ROOT / "scripts"
LOG_ROOT_DEFAULT = STACK_ROOT / "Logs" / "local-ai-trials" / PROGRAM_ID
MIRROR_ROOT_DEFAULT = Path("/srv/Dionysus/reports/local-ai-trials") / PROGRAM_ID
BASELINE_PROGRAM_ID = "qwen-local-pilot-v1"
BASELINE_LOG_ROOT = STACK_ROOT / "Logs" / "local-ai-trials" / BASELINE_PROGRAM_ID
COMPARISON_MEMO_NAME = "LANGGRAPH_COMPARISON.md"
PILOT_INDEX_NAME = EDIT_GATE_INDEX_NAME

DEFAULT_DOCS_CASE_ID = "8dionysus-profile-routing-clarity"
FIXTURE_DOCS_CASE_ID = "fixture-docs-wording-alignment"
FIXTURE_VERSION = "v2"
DOCS_CASE_ID = DEFAULT_DOCS_CASE_ID
DOC_CASE_IDS = {DOCS_CASE_ID}


class PilotState(TypedDict, total=False):
    case_id: str
    until: str
    execution_mode: str
    current_node: str
    next_node: str | None
    proposal_valid: bool
    approval_status: str | None
    paused: bool
    pause_reason: str | None
    terminal_status: str | None
    failure_class: str | None
    resume_count: int
    history: list[dict[str, Any]]
    note: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def absolute(path: Path) -> str:
    return str(path.resolve())


def default_log_root_for(program_id: str) -> Path:
    return STACK_ROOT / "Logs" / "local-ai-trials" / program_id


def default_mirror_root_for(program_id: str) -> Path:
    return Path("/srv/Dionysus/reports/local-ai-trials") / program_id


def configure_program_runtime(*, program_id: str, run_url: str) -> None:
    global PROGRAM_ID, DOCS_CASE_ID, DOC_CASE_IDS, LOG_ROOT_DEFAULT, MIRROR_ROOT_DEFAULT, LANGCHAIN_RUN_URL
    PROGRAM_ID = program_id
    DOCS_CASE_ID = FIXTURE_DOCS_CASE_ID if is_fixture_program(program_id) else DEFAULT_DOCS_CASE_ID
    DOC_CASE_IDS = {DOCS_CASE_ID}
    LOG_ROOT_DEFAULT = default_log_root_for(program_id)
    MIRROR_ROOT_DEFAULT = default_mirror_root_for(program_id)
    LANGCHAIN_RUN_URL = run_url


def is_fixture_program(program_id: str | None = None) -> bool:
    return (program_id or PROGRAM_ID) == FIXTURE_PROGRAM_ID


def load_trials_module() -> Any:
    target = SOURCE_ROOT / "mechanics" / "inference-pilots" / "parts" / "local-trials" / "aoa_local_ai_trials.py"
    loader = importlib.machinery.SourceFileLoader("aoa_local_ai_trials_sidecar", str(target))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"could not create module spec for {target}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)  # type: ignore[arg-type]
    return module


TRIALS = load_trials_module()
ORIGINAL_TRIALS_BUILD_CATALOG = TRIALS.build_catalog


def fixture_repo_root(log_root: Path) -> Path:
    return log_root / "_fixtures" / FIXTURE_DOCS_CASE_ID / "repo"


def fixture_case_from_template(log_root: Path) -> dict[str, Any]:
    catalog = ORIGINAL_TRIALS_BUILD_CATALOG()
    template = next(case for case in TRIAL_ADAPTER.edit_gate_catalog(catalog) if case["case_id"] == DEFAULT_DOCS_CASE_ID)
    item = copy.deepcopy(template)
    repo_root = fixture_repo_root(log_root)
    readme = repo_root / "README.md"
    style = repo_root / "docs" / "STYLE.md"
    check_script = repo_root / "scripts" / "check_fixture.py"
    item["case_id"] = FIXTURE_DOCS_CASE_ID
    item["program_id"] = PROGRAM_ID
    item["title"] = "Disposable Docs Fixture Wording Alignment"
    item["repo_scope"] = ["langgraph-fixture-docs"]
    item["source_refs"] = [absolute(readme), absolute(style)]
    item["inputs"] = [
        "Align the README wording to the style note without widening ownership claims.",
        "Keep the fixture framed as a coordination surface rather than a source-of-truth implementation repo.",
        "Replace `It is not the source of truth for implementation details or routing policy authorship.` with exactly `Implementation details and routing policy live elsewhere.`",
    ]
    item["acceptance_checks"] = ["python3 scripts/check_fixture.py"]
    item["mutation_policy"]["allowed_files"] = [absolute(readme)]
    item["expected_result"]["allowed_files"] = [absolute(readme)]
    item["notes"] = list(item.get("notes") or []) + [
        "This disposable fixture exists only for the llama.cpp promotion dry-run and must not touch any live repo.",
    ]
    return item


def available_cases(log_root: Path | None = None) -> list[dict[str, Any]]:
    catalog = ORIGINAL_TRIALS_BUILD_CATALOG()
    if is_fixture_program():
        if log_root is None:
            raise RuntimeError("fixture program requires a log_root to build its disposable repo case")
        return [fixture_case_from_template(log_root)]
    selected = []
    for case in TRIAL_ADAPTER.edit_gate_catalog(catalog):
        if case["case_id"] != DEFAULT_DOCS_CASE_ID:
            continue
        item = copy.deepcopy(case)
        item["program_id"] = PROGRAM_ID
        item["notes"] = list(item.get("notes") or []) + [
            "This case is frozen into the LangGraph sidecar pilot and intentionally reuses the preserved bounded-edit compatibility gate.",
        ]
        selected.append(item)
    by_id = {case["case_id"]: case for case in selected}
    return [by_id[DEFAULT_DOCS_CASE_ID]]


def pilot_catalog(log_root: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    return TRIAL_ADAPTER.edit_gate_catalog_payload(available_cases(log_root))


def run_git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(repo_root), check=True, text=True, capture_output=True)


def ensure_fixture_repo(log_root: Path) -> Path:
    repo_root = fixture_repo_root(log_root)
    parent = repo_root.parent
    version_file = repo_root / ".fixture-version"
    expected_files = [
        repo_root / ".git",
        repo_root / "README.md",
        repo_root / "docs" / "STYLE.md",
        repo_root / "AGENTS.md",
        repo_root / "scripts" / "check_fixture.py",
        version_file,
    ]
    if all(path.exists() for path in expected_files) and version_file.read_text(encoding="utf-8").strip() == FIXTURE_VERSION:
        return repo_root
    if parent.exists():
        shutil.rmtree(parent)
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)
    (repo_root / "scripts").mkdir(parents=True, exist_ok=True)
    (repo_root / "README.md").write_text(
        "\n".join(
            [
                "# Fixture Docs Repo",
                "",
                "This repository is the public coordination surface for the fixture ecosystem.",
                "It should help people navigate to the right source repo quickly.",
                "It is not the source of truth for implementation details or routing policy authorship.",
                "",
                "Use the docs folder for compact guidance about what this fixture owns.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "docs" / "STYLE.md").write_text(
        "\n".join(
            [
                "# Style",
                "",
                "- Frame the fixture as a coordination surface.",
                '- Replace the long source-of-truth sentence with exactly: `Implementation details and routing policy live elsewhere.`',
                "- Keep wording compact and navigation-first.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "AGENTS.md").write_text(
        "\n".join(
            [
                "# AGENTS.md",
                "",
                "## Purpose",
                "",
                "This disposable repository exists only for bounded local-ai pilot checks.",
                "",
                "## Editing rules",
                "",
                "- Keep README.md concise and navigation-first.",
                "- Do not claim this repo authors implementation truth.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (repo_root / "scripts" / "check_fixture.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "",
                "readme = Path('README.md').read_text(encoding='utf-8')",
                "required = 'coordination surface'",
                "required_replacement = 'Implementation details and routing policy live elsewhere.'",
                "forbidden = 'source of truth for implementation details or routing policy authorship'",
                "if required not in readme:",
                "    raise SystemExit('missing required wording')",
                "if required_replacement not in readme:",
                "    raise SystemExit('replacement wording missing')",
                "if forbidden in readme:",
                "    raise SystemExit('forbidden wording still present')",
                "print('fixture acceptance passed')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    version_file.write_text(FIXTURE_VERSION + "\n", encoding="utf-8")
    run_git(repo_root, "init", "-b", "main")
    run_git(repo_root, "config", "user.name", "Codex Fixture")
    run_git(repo_root, "config", "user.email", "codex-fixture@example.invalid")
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "-m", "Initialize disposable fixture docs repo")
    return repo_root


def case_root(log_root: Path, case_id: str) -> Path:
    return TRIAL_ADAPTER.edit_gate_case_dir(log_root, case_id)


def state_path(log_root: Path, case_id: str) -> Path:
    return case_root(log_root, case_id) / "graph.state.json"


def history_path(log_root: Path, case_id: str) -> Path:
    return case_root(log_root, case_id) / "graph.history.jsonl"


def interrupt_path(log_root: Path, case_id: str) -> Path:
    return case_root(log_root, case_id) / "interrupt.json"


def node_artifacts_dir(log_root: Path, case_id: str) -> Path:
    path = case_root(log_root, case_id) / "node-artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def program_readme() -> str:
    return (
        f"# {PROGRAM_ID}\n\n"
        "This directory stores the runtime-truth artifacts for the bounded LangGraph sidecar pilot.\n\n"
        "It reuses the preserved local-trials bounded-edit compatibility gate while comparing a graph-shaped orchestration layer to the runner.\n"
    )


def mirror_readme() -> str:
    return (
        f"# {PROGRAM_ID}\n\n"
        "This folder mirrors human+AI-readable LangGraph sidecar pilot reports.\n\n"
        "Machine-readable runtime truth stays local under `/srv/AbyssOS/abyss-stack/Logs/local-ai-trials/`.\n"
    )


def comparison_memo(log_root: Path) -> str:
    docs_result = load_result_summary(log_root, DOCS_CASE_ID)
    docs_state = load_graph_state(log_root, DOCS_CASE_ID)
    docs_history = docs_state.get("history", []) if docs_state else []
    pause_seen = any(item.get("node") == "await_approval" and item.get("status") == "paused" for item in docs_history)
    resumed = (docs_state or {}).get("resume_count", 0) > 0
    docs_pass = docs_result is not None and docs_result.get("status") == "pass"

    if is_fixture_program():
        recommendation = (
            "This fixture pilot is suitable as a bounded promotion gate for backend comparison before the long-horizon pilot."
            if docs_pass
            else "This fixture pilot is not yet suitable as a promotion gate because the disposable docs case has not passed."
        )
    elif docs_pass and pause_seen and resumed:
        recommendation = (
            "LangGraph sidecar is recommended as the next bounded long-horizon execution substrate, "
            "while keeping `aoa-local-ai-trials` as the baseline comparator."
        )
    else:
        recommendation = (
            "LangGraph sidecar is not yet the recommended long-horizon substrate. Keep the current runner as the execution baseline "
            "until the bounded docs case passes and pause/resume is proven end-to-end."
        )

    return "\n".join(
        [
            f"# {PROGRAM_ID} Comparison Memo",
            "",
            "## Summary",
            "- This pilot compares graph-shaped orchestration against the preserved bounded-edit local-trials runner.",
            "",
            "## Current Evidence",
            f"- Docs case pass: `{docs_pass}`",
            f"- Pause observed: `{pause_seen}`",
            f"- Resume observed: `{resumed}`",
            "",
            "## Comparison Notes",
            "- Pause/resume is explicit through persisted `graph.state.json`, `graph.history.jsonl`, and `approval.status.json`.",
            "- Proposal and worktree safety continue to reuse the preserved bounded-edit compatibility gate.",
            "- Glue code increases slightly because the pilot stays side-by-side with the existing runner instead of replacing it.",
            "",
            "## Recommendation",
            recommendation,
        ]
    ) + "\n"


def render_index_md(index_payload: dict[str, Any]) -> str:
    return TRIAL_ADAPTER.render_edit_gate_index_md(index_payload)


# The preserved local-trials backend still exposes archived compatibility schema
# details. Active LangGraph code routes those details through the edit-gate
# adapter instead of treating them as current topology.


def write_json(path: Path, payload: dict[str, Any]) -> None:
    TRIALS.write_json(path, payload)


def write_text(path: Path, text: str) -> None:
    TRIALS.write_text(path, text)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_case_spec(log_root: Path, case_id: str) -> dict[str, Any]:
    return load_json(case_root(log_root, case_id) / "case.spec.json")


def load_result_summary(log_root: Path, case_id: str) -> dict[str, Any] | None:
    path = case_root(log_root, case_id) / "result.summary.json"
    if not path.exists():
        return None
    return load_json(path)


def load_graph_state(log_root: Path, case_id: str) -> PilotState | None:
    path = state_path(log_root, case_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_graph_state(log_root: Path, case_id: str, state: PilotState) -> None:
    sanitized = {
        "case_id": state.get("case_id"),
        "until": state.get("until"),
        "execution_mode": state.get("execution_mode"),
        "current_node": state.get("current_node"),
        "next_node": state.get("next_node"),
        "proposal_valid": state.get("proposal_valid"),
        "approval_status": state.get("approval_status"),
        "paused": state.get("paused", False),
        "pause_reason": state.get("pause_reason"),
        "terminal_status": state.get("terminal_status"),
        "failure_class": state.get("failure_class"),
        "resume_count": state.get("resume_count", 0),
        "note": state.get("note"),
        "history": state.get("history", []),
    }
    write_json(state_path(log_root, case_id), sanitized)
    history_lines = [json.dumps(item, ensure_ascii=True) for item in sanitized["history"]]
    history_file = history_path(log_root, case_id)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text("\n".join(history_lines) + ("\n" if history_lines else ""), encoding="utf-8")


def record_event(state: PilotState, *, node: str, status: str, note: str, extra: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    history = list(state.get("history", []))
    payload: dict[str, Any] = {
        "at": utc_now(),
        "node": node,
        "status": status,
        "note": note,
    }
    if extra:
        payload.update(extra)
    history.append(payload)
    return history


def make_index_payload(log_root: Path, mirror_root: Path) -> dict[str, Any]:
    cases = available_cases(log_root)
    case_entries: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    planned_count = 0
    critical_failures: list[str] = []
    pause_resume_proved = False

    for case in cases:
        result = load_result_summary(log_root, case["case_id"])
        graph_state = load_graph_state(log_root, case["case_id"])
        terminal_status = (graph_state or {}).get("terminal_status")
        if result:
            status = result["status"]
            if status == "pass":
                pass_count += 1
            elif status == "fail":
                fail_count += 1
            if result.get("failure_class") in TRIALS.W4_CRITICAL_FAILURES:
                critical_failures.append(case["case_id"])
        elif terminal_status == "rejected":
            status = "rejected"
            fail_count += 1
            if (graph_state or {}).get("failure_class") in TRIALS.W4_CRITICAL_FAILURES:
                critical_failures.append(case["case_id"])
        elif graph_state:
            status = "in-progress" if graph_state.get("paused") else "prepared"
        else:
            status = "planned"
            planned_count += 1

        if case["case_id"] == DOCS_CASE_ID and graph_state:
            history = graph_state.get("history", [])
            pause_resume_proved = (
                any(item.get("node") == "await_approval" and item.get("status") == "paused" for item in history)
                and graph_state.get("resume_count", 0) > 0
            )

        case_entries.append(
            {
                "case_id": case["case_id"],
                "status": status,
                "repo_scope": case["repo_scope"],
                "task_family": case["task_family"],
                "case_spec": str(case_root(log_root, case["case_id"]) / "case.spec.json"),
                "summary": case["title"],
                **(
                    {"report_md": str(mirror_root / TRIAL_ADAPTER.edit_gate_case_report_name(case["case_id"]))}
                    if (case_root(log_root, case["case_id"]) / "report.md").exists()
                    else {}
                ),
                "current_node": (graph_state or {}).get("current_node"),
                "approval_status": (graph_state or {}).get("approval_status"),
                "landing_status": "landed" if result and result.get("status") == "pass" else "not-landed",
            }
        )

    required_passes = 1 if is_fixture_program() else 2
    gate_pass = pass_count == required_passes and not critical_failures and (True if is_fixture_program() else pause_resume_proved)
    if gate_pass:
        gate_result = "pass"
        next_action = (
            "Use the fixture packet as the legacy edit-gate dry-run promotion verdict for the candidate backend."
            if is_fixture_program()
            else "Use the comparison memo to decide whether the long-horizon pilot should run on the LangGraph sidecar substrate."
        )
    elif fail_count or critical_failures:
        gate_result = "fail"
        next_action = "Inspect the failed case packet and compare it against the preserved bounded-edit runner before promoting LangGraph."
    elif planned_count == len(cases):
        gate_result = "not-run"
        next_action = "Materialize the sidecar pilot and run the docs case to the approval boundary first."
    else:
        gate_result = "in-progress"
        next_action = "Resume the paused docs case or execute the remaining generated case to complete the comparison."

    return {
        **TRIAL_ADAPTER.edit_gate_index_fields(
            title="LangGraph Sidecar Pilot",
            summary=(
                "Bounded disposable edit-gate fixture used as a backend promotion gate."
                if is_fixture_program()
                else "Bounded comparison pilot for a graph-shaped bounded-edit execution layer."
            ),
        ),
        "program_id": PROGRAM_ID,
        "case_count": len(cases),
        "status_counts": {
            "pass": pass_count,
            "fail": fail_count,
            "planned": planned_count,
        },
        "gate_result": gate_result,
        "next_action": next_action,
        "cases": case_entries,
        "gate_detail": {
            "pass_count": pass_count,
            "fail_count": fail_count,
            "planned_count": planned_count,
            "critical_failures": critical_failures,
            "pause_resume_proved": pause_resume_proved,
            "comparison_memo": str(mirror_root / COMPARISON_MEMO_NAME),
            "fixture_mode": is_fixture_program(),
            "next_action": next_action,
        },
    }


def refresh_sidecar_outputs(log_root: Path, mirror_root: Path) -> None:
    index_payload = make_index_payload(log_root, mirror_root)
    write_json(log_root / f"{PILOT_INDEX_NAME}.json", index_payload)
    index_md = render_index_md(index_payload)
    write_text(log_root / f"{PILOT_INDEX_NAME}.md", index_md)
    write_text(mirror_root / f"{PILOT_INDEX_NAME}.md", index_md)
    write_text(mirror_root / COMPARISON_MEMO_NAME, comparison_memo(log_root))


def materialize(log_root: Path, mirror_root: Path) -> None:
    log_root.mkdir(parents=True, exist_ok=True)
    mirror_root.mkdir(parents=True, exist_ok=True)
    write_text(log_root / "README.md", program_readme())
    write_text(mirror_root / "README.md", mirror_readme())
    if is_fixture_program():
        ensure_fixture_repo(log_root)

    contracts = {
        "case.spec.schema.json": TRIALS.CASE_SCHEMA,
        "run.manifest.schema.json": TRIALS.RUN_MANIFEST_SCHEMA,
        "result.summary.schema.json": TRIALS.RESULT_SUMMARY_SCHEMA,
        TRIAL_ADAPTER.WIRE_INDEX_SCHEMA_NAME: TRIAL_ADAPTER.WIRE_INDEX_SCHEMA,
    }
    for name, payload in contracts.items():
        write_json(log_root / "contracts" / name, payload)

    for case in available_cases(log_root):
        write_json(case_root(log_root, case["case_id"]) / "case.spec.json", case)
        node_artifacts_dir(log_root, case["case_id"])

    refresh_sidecar_outputs(log_root, mirror_root)


def ensure_baseline_edit_gate_closeout() -> None:
    closeout_path = BASELINE_LOG_ROOT / EDIT_GATE_CLOSEOUT_NAME
    if not closeout_path.exists():
        raise RuntimeError(f"missing preserved edit-gate closeout artifact: {closeout_path}")
    payload = load_json(closeout_path)
    if payload.get("gate_result") != "pass":
        raise RuntimeError(f"preserved edit-gate closeout is not pass: {closeout_path}")


def ensure_runtime_ready(case_dir_path: Path) -> None:
    doctor_raw = TRIALS.run_command(
        [absolute(SCRIPTS_ROOT / "aoa-doctor"), "--preset", "intel-full"],
        cwd=CONFIGS_ROOT,
        timeout_s=120,
    )
    TRIALS.persist_command_result(case_dir_path, "graph-preflight-doctor", doctor_raw)
    if doctor_raw["exit_code"] != 0 or doctor_raw["timed_out"]:
        raise RuntimeError("aoa-doctor preflight failed")

    health_raw = TRIALS.run_command(
        ["curl", "-fsS", TRIALS.langchain_endpoint("/health")],
        cwd=CONFIGS_ROOT,
        timeout_s=30,
    )
    TRIALS.persist_command_result(case_dir_path, "graph-preflight-langchain-health", health_raw)
    if health_raw["exit_code"] != 0 or health_raw["timed_out"]:
        raise RuntimeError("langchain-api /health preflight failed")
    payload = json.loads(health_raw["stdout"])
    if not payload.get("ok") or payload.get("service") != "langchain-api":
        raise RuntimeError("langchain-api /health returned an unexpected payload")


def write_interrupt(log_root: Path, state: PilotState, *, reason: str) -> None:
    payload = {
        "artifact_kind": "aoa.local-ai-trial.langgraph-interrupt",
        "program_id": PROGRAM_ID,
        **TRIAL_ADAPTER.edit_gate_wire_id_entry(),
        "case_id": state["case_id"],
        "paused_at": utc_now(),
        "reason": reason,
        "approval_status": state.get("approval_status"),
        "resume_hint": "Set approval.status.json to approved or rejected, then run `scripts/aoa-langgraph-pilot resume-case <case-id>`.",
    }
    write_json(interrupt_path(LOG_ROOT_DEFAULT, state["case_id"]), payload)


def write_rejected_terminal(case: dict[str, Any], *, log_root: Path, mirror_root: Path, approval_payload: dict[str, Any]) -> None:
    command_refs: list[dict[str, Any]] = []
    approval_path = case_root(log_root, case["case_id"]) / "artifacts" / "approval.status.json"
    run_manifest = {
        "artifact_kind": "aoa.local-ai-trial.run-manifest",
        "program_id": PROGRAM_ID,
        **TRIAL_ADAPTER.edit_gate_wire_id_entry(),
        "case_id": case["case_id"],
        "executed_at": utc_now(),
        "runtime_selection": case["runtime_selection"],
        "model": MODEL,
        "backend": "langgraph-sidecar",
        "commands": command_refs,
        "artifact_refs": [str(approval_path)],
        "notes": [
            "The case was explicitly rejected at the approval boundary and no mutation was attempted.",
        ],
    }
    result_summary = TRIALS.build_result_summary(
        case=case,
        status="fail",
        score_breakdown={
            "proposal_valid": True,
            "approval_present": True,
            "approval_rejected": True,
            "unauthorized_scope_expansion": False,
            "post_change_validation_failure": False,
        },
        observed={
            "highlights": [
                "The LangGraph sidecar reached the explicit approval boundary.",
                f"Approval status: `{approval_payload.get('status')}`.",
            ],
            "failures": ["The operator rejected the proposal before any mutation was attempted."],
        },
        failure_class="approval_rejected",
        reviewer_notes="The case was intentionally stopped at the approval boundary.",
        boundary_notes=TRIALS.w4_boundary_note(),
        next_action="Review the rejected proposal or refresh the case before retrying.",
    )
    TRIALS.finalize_case(
        case=case,
        log_root=log_root,
        mirror_root=mirror_root,
        run_manifest=run_manifest,
        result_summary=result_summary,
    )


def node_json(log_root: Path, case_id: str, name: str, payload: dict[str, Any]) -> None:
    write_json(node_artifacts_dir(log_root, case_id) / f"{name}.json", payload)


def approval_payload(log_root: Path, case_id: str) -> dict[str, Any] | None:
    path = case_root(log_root, case_id) / "artifacts" / "approval.status.json"
    if not path.exists():
        return None
    return load_json(path)


@contextmanager
def patched_trials_context(*, active_log_root: Path | None = None, active_mirror_root: Path | None = None) -> Any:
    active_log_root = active_log_root or LOG_ROOT_DEFAULT
    active_mirror_root = active_mirror_root or MIRROR_ROOT_DEFAULT
    originals = {
        "PROGRAM_ID": TRIALS.PROGRAM_ID,
        "LOG_ROOT_DEFAULT": TRIALS.LOG_ROOT_DEFAULT,
        "MIRROR_ROOT_DEFAULT": TRIALS.MIRROR_ROOT_DEFAULT,
        "LANGCHAIN_RUN_URL": getattr(TRIALS, "LANGCHAIN_RUN_URL", None),
        "LANGCHAIN_BASE_URL": getattr(TRIALS, "LANGCHAIN_BASE_URL", None),
        "W4_DOC_CASE_IDS": TRIALS.W4_DOC_CASE_IDS,
        "W4_GENERATED_CASE_IDS": TRIALS.W4_GENERATED_CASE_IDS,
        "W4_DOC_PREPARE_ORDER": TRIALS.W4_DOC_PREPARE_ORDER,
        "W4_GENERATED_PREPARE_ORDER": TRIALS.W4_GENERATED_PREPARE_ORDER,
        "W4_DOC_TARGET_FALLBACKS": TRIALS.W4_DOC_TARGET_FALLBACKS,
        "build_catalog": TRIALS.build_catalog,
        "w4_docs_lane_state": TRIALS.w4_docs_lane_state,
        "repo_root_for_w4_case": TRIALS.repo_root_for_w4_case,
    }

    def custom_build_catalog() -> dict[str, list[dict[str, Any]]]:
        return pilot_catalog(active_log_root)

    def custom_w4_docs_lane_state(log_root: Path, catalog: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        results_by_id = {
            result["case_id"]: result
            for result in TRIALS.load_w4_results(log_root, catalog)
        }
        docs_results = [
            results_by_id[case_id]
            for case_id in DOC_CASE_IDS
            if case_id in results_by_id
        ]
        docs_pass = sum(1 for item in docs_results if item["status"] == "pass")
        docs_criticals = [
            item["case_id"]
            for item in docs_results
            if item.get("failure_class") in TRIALS.W4_CRITICAL_FAILURES
        ]
        return {
            "pass_count": docs_pass,
            "critical_case_ids": docs_criticals,
            "unlock_generated_lane": docs_pass >= 1 and not docs_criticals,
        }

    def custom_repo_root_for_w4_case(case: dict[str, Any]) -> Path:
        if case["case_id"] == FIXTURE_DOCS_CASE_ID:
            return fixture_repo_root(active_log_root)
        return originals["repo_root_for_w4_case"](case)

    TRIALS.configure_program_runtime(program_id=PROGRAM_ID, run_url=LANGCHAIN_RUN_URL)
    TRIALS.LOG_ROOT_DEFAULT = active_log_root
    TRIALS.MIRROR_ROOT_DEFAULT = active_mirror_root
    TRIALS.W4_DOC_CASE_IDS = set(DOC_CASE_IDS)
    TRIALS.W4_GENERATED_CASE_IDS = set()
    TRIALS.W4_DOC_PREPARE_ORDER = [DOCS_CASE_ID]
    TRIALS.W4_GENERATED_PREPARE_ORDER = []
    target_fallbacks = dict(TRIALS.W4_DOC_TARGET_FALLBACKS)
    if is_fixture_program():
        target_fallbacks[FIXTURE_DOCS_CASE_ID] = "README.md"
    TRIALS.W4_DOC_TARGET_FALLBACKS = target_fallbacks
    TRIALS.build_catalog = custom_build_catalog
    TRIALS.w4_docs_lane_state = custom_w4_docs_lane_state
    TRIALS.repo_root_for_w4_case = custom_repo_root_for_w4_case
    try:
        yield TRIALS
    finally:
        TRIALS.PROGRAM_ID = originals["PROGRAM_ID"]
        TRIALS.LOG_ROOT_DEFAULT = originals["LOG_ROOT_DEFAULT"]
        TRIALS.MIRROR_ROOT_DEFAULT = originals["MIRROR_ROOT_DEFAULT"]
        if originals["LANGCHAIN_RUN_URL"] is not None:
            TRIALS.LANGCHAIN_RUN_URL = originals["LANGCHAIN_RUN_URL"]
        if originals["LANGCHAIN_BASE_URL"] is not None:
            TRIALS.LANGCHAIN_BASE_URL = originals["LANGCHAIN_BASE_URL"]
        TRIALS.W4_DOC_CASE_IDS = originals["W4_DOC_CASE_IDS"]
        TRIALS.W4_GENERATED_CASE_IDS = originals["W4_GENERATED_CASE_IDS"]
        TRIALS.W4_DOC_PREPARE_ORDER = originals["W4_DOC_PREPARE_ORDER"]
        TRIALS.W4_GENERATED_PREPARE_ORDER = originals["W4_GENERATED_PREPARE_ORDER"]
        TRIALS.W4_DOC_TARGET_FALLBACKS = originals["W4_DOC_TARGET_FALLBACKS"]
        TRIALS.build_catalog = originals["build_catalog"]
        TRIALS.w4_docs_lane_state = originals["w4_docs_lane_state"]
        TRIALS.repo_root_for_w4_case = originals["repo_root_for_w4_case"]


def build_graph(log_root: Path, mirror_root: Path):
    def route_from_phase(state: PilotState) -> Command[str]:
        next_node = state.get("next_node") or "preflight"
        return Command(update={"current_node": "route"}, goto=next_node)

    def preflight(state: PilotState) -> Command[str]:
        case_id = state["case_id"]
        root = case_root(log_root, case_id)
        try:
            ensure_baseline_edit_gate_closeout()
            ensure_runtime_ready(root)
            history = record_event(state, node="preflight", status="pass", note="Preserved edit-gate closeout and local runtime preflight are green.")
            node_json(
                log_root,
                case_id,
                "preflight",
                {
                    "case_id": case_id,
                    "checked_at": utc_now(),
                    "baseline_closeout": str(BASELINE_LOG_ROOT / EDIT_GATE_CLOSEOUT_NAME),
                    "doctor_preset": "intel-full",
                    "langchain_health": TRIALS.langchain_endpoint("/health"),
                    "status": "pass",
                },
            )
            return Command(
                update={
                    "current_node": "preflight",
                    "next_node": "load_case",
                    "history": history,
                    "paused": False,
                    "pause_reason": None,
                    "failure_class": None,
                    "terminal_status": None,
                },
                goto="load_case",
            )
        except Exception as exc:
            history = record_event(state, node="preflight", status="fail", note=str(exc))
            node_json(
                log_root,
                case_id,
                "preflight",
                {
                    "case_id": case_id,
                    "checked_at": utc_now(),
                    "status": "fail",
                    "error": str(exc),
                },
            )
            case = load_case_spec(log_root, case_id)
            with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
                run_manifest = {
                    "artifact_kind": "aoa.local-ai-trial.run-manifest",
                    "program_id": PROGRAM_ID,
                    **TRIAL_ADAPTER.edit_gate_wire_id_entry(),
                    "case_id": case_id,
                    "executed_at": utc_now(),
                    "runtime_selection": case["runtime_selection"],
                    "model": MODEL,
                    "backend": "langgraph-sidecar",
                    "commands": [],
                    "artifact_refs": [],
                    "notes": ["Pilot stopped before proposal preparation because preflight failed."],
                }
                result_summary = TRIALS.build_result_summary(
                    case=case,
                    status="fail",
                    score_breakdown={"preflight_ok": False},
                    observed={
                        "highlights": ["The sidecar pilot stopped before proposal preparation."],
                        "failures": [str(exc)],
                    },
                    failure_class="preflight_failure",
                    reviewer_notes="The LangGraph sidecar preflight did not satisfy the required preserved edit-gate closeout and runtime-health posture.",
                    boundary_notes=TRIALS.w4_boundary_note(),
                    next_action="Repair the preserved edit-gate baseline or runtime readiness before retrying the sidecar pilot.",
                )
                TRIALS.finalize_case(case=case, log_root=log_root, mirror_root=mirror_root, run_manifest=run_manifest, result_summary=result_summary)
            return Command(
                update={
                    "current_node": "preflight",
                    "next_node": "finalize_report",
                    "history": history,
                    "failure_class": "preflight_failure",
                    "terminal_status": "fail",
                },
                goto="finalize_report",
            )

    def load_case(state: PilotState) -> Command[str]:
        case = load_case_spec(log_root, state["case_id"])
        execution_mode = case["execution_mode"]
        history = record_event(state, node="load_case", status="pass", note=f"Loaded `{case['case_id']}` with execution_mode `{execution_mode}`.")
        node_json(
            log_root,
            state["case_id"],
            "load-case",
            {
                "loaded_at": utc_now(),
                "case_id": case["case_id"],
                "execution_mode": execution_mode,
                "repo_scope": case["repo_scope"],
            },
        )
        next_node = "write_initial_packet"
        return Command(
            update={
                "current_node": "load_case",
                "next_node": next_node,
                "execution_mode": execution_mode,
                "history": history,
            },
            goto=next_node,
        )

    def write_initial_packet(state: PilotState) -> Command[str]:
        case_id = state["case_id"]
        croot = case_root(log_root, case_id)
        croot.mkdir(parents=True, exist_ok=True)
        node_artifacts_dir(log_root, case_id)
        ipath = interrupt_path(log_root, case_id)
        if ipath.exists():
            ipath.unlink()
        history = record_event(state, node="write_initial_packet", status="pass", note="Initial pilot packet and runtime-side artifact directories are ready.")
        node_json(
            log_root,
            case_id,
            "write-initial-packet",
            {
                "prepared_at": utc_now(),
                "case_root": str(croot),
                "node_artifacts": str(node_artifacts_dir(log_root, case_id)),
            },
        )
        next_node = "collect_refs" if state["execution_mode"] == "qwen_patch" else "prepare_generated_proposal"
        return Command(
            update={
                "current_node": "write_initial_packet",
                "next_node": next_node,
                "history": history,
            },
            goto=next_node,
        )

    def collect_refs(state: PilotState) -> Command[str]:
        case = load_case_spec(log_root, state["case_id"])
        with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
            agents_refs = TRIALS.collect_applicable_agents_refs(case)
        history = record_event(state, node="collect_refs", status="pass", note=f"Collected {len(case.get('source_refs', []))} source refs and {len(agents_refs)} AGENTS refs.")
        node_json(
            log_root,
            state["case_id"],
            "collect-refs",
            {
                "collected_at": utc_now(),
                "source_refs": case.get("source_refs", []),
                "agents_refs": agents_refs,
            },
        )
        return Command(
            update={
                "current_node": "collect_refs",
                "next_node": "build_edit_proposal",
                "history": history,
            },
            goto="build_edit_proposal",
        )

    def build_edit_proposal(state: PilotState) -> Command[str]:
        case = load_case_spec(log_root, state["case_id"])
        with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
            result = TRIALS.prepare_w4_case(case, log_root=log_root)
        proposal_summary = load_json(case_root(log_root, state["case_id"]) / "artifacts" / "proposal.summary.json")
        history = record_event(
            state,
            node="build_edit_proposal",
            status="pass" if result.get("proposal_valid") else "fail",
            note="Docs proposal prepared through the preserved edit-spec compatibility contract.",
            extra={"proposal_valid": bool(result.get("proposal_valid"))},
        )
        node_json(
            log_root,
            state["case_id"],
            "build-edit-proposal",
            {
                "prepared_at": utc_now(),
                "proposal_valid": bool(result.get("proposal_valid")),
                "proposal_summary_path": str(case_root(log_root, state["case_id"]) / "artifacts" / "proposal.summary.json"),
                "proposal_failure_reasons": proposal_summary.get("proposal_failure_reasons", []),
            },
        )
        next_node = "persist_proposal" if result.get("proposal_valid") else "finalize_report"
        terminal_status = None if result.get("proposal_valid") else "fail"
        return Command(
            update={
                "current_node": "build_edit_proposal",
                "next_node": next_node,
                "proposal_valid": bool(result.get("proposal_valid")),
                "history": history,
                "failure_class": None if result.get("proposal_valid") else "proposal_invalid",
                "terminal_status": terminal_status,
            },
            goto=next_node,
        )

    def persist_proposal(state: PilotState) -> Command[str]:
        case_id = state["case_id"]
        proposal_summary_path = case_root(log_root, case_id) / "artifacts" / "proposal.summary.json"
        approval_path = case_root(log_root, case_id) / "artifacts" / "approval.status.json"
        if not proposal_summary_path.exists() or not approval_path.exists():
            history = record_event(state, node="persist_proposal", status="fail", note="Proposal artifacts were missing after preparation.")
            return Command(
                update={
                    "current_node": "persist_proposal",
                    "next_node": "finalize_report",
                    "history": history,
                    "failure_class": "proposal_invalid",
                    "terminal_status": "fail",
                },
                goto="finalize_report",
            )
        history = record_event(state, node="persist_proposal", status="pass", note="Proposal summary and approval contract are persisted.")
        node_json(
            log_root,
            case_id,
            "persist-proposal",
            {
                "persisted_at": utc_now(),
                "proposal_summary": str(proposal_summary_path),
                "approval_status": str(approval_path),
            },
        )
        return Command(
            update={
                "current_node": "persist_proposal",
                "next_node": "await_approval",
                "history": history,
            },
            goto="await_approval",
        )

    def prepare_generated_proposal(state: PilotState) -> Command[str]:
        case = load_case_spec(log_root, state["case_id"])
        with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
            result = TRIALS.prepare_w4_case(case, log_root=log_root)
        proposal_summary = load_json(case_root(log_root, state["case_id"]) / "artifacts" / "proposal.summary.json")
        history = record_event(
            state,
            node="prepare_generated_proposal",
            status="pass" if result.get("proposal_valid") else "fail",
            note="Generated proposal prepared through the canonical deterministic script_refresh path.",
            extra={"proposal_valid": bool(result.get("proposal_valid"))},
        )
        node_json(
            log_root,
            state["case_id"],
            "prepare-generated-proposal",
            {
                "prepared_at": utc_now(),
                "proposal_valid": bool(result.get("proposal_valid")),
                "builder_command": proposal_summary.get("builder_command"),
                "proposal_failure_reasons": proposal_summary.get("proposal_failure_reasons", []),
            },
        )
        next_node = "await_approval" if result.get("proposal_valid") else "finalize_report"
        return Command(
            update={
                "current_node": "prepare_generated_proposal",
                "next_node": next_node,
                "proposal_valid": bool(result.get("proposal_valid")),
                "history": history,
                "failure_class": None if result.get("proposal_valid") else "proposal_invalid",
                "terminal_status": None if result.get("proposal_valid") else "fail",
            },
            goto=next_node,
        )

    def await_approval(state: PilotState) -> Command[str]:
        payload = approval_payload(log_root, state["case_id"])
        status = str((payload or {}).get("status") or "pending")
        history = record_event(state, node="await_approval", status="seen", note=f"Observed approval status `{status}`.")
        node_json(
            log_root,
            state["case_id"],
            "await-approval",
            {
                "checked_at": utc_now(),
                "approval_status": status,
                "approval_path": str(case_root(log_root, state["case_id"]) / "artifacts" / "approval.status.json"),
            },
        )
        if status == "approved":
            return Command(
                update={
                    "current_node": "await_approval",
                    "next_node": "worktree_apply",
                    "approval_status": status,
                    "history": history,
                    "paused": False,
                    "pause_reason": None,
                },
                goto="worktree_apply",
            )
        if status == "rejected":
            case = load_case_spec(log_root, state["case_id"])
            with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
                write_rejected_terminal(case, log_root=log_root, mirror_root=mirror_root, approval_payload=payload or {})
            history = record_event(
                {"history": history},
                node="await_approval",
                status="rejected",
                note="Approval was explicitly rejected before mutation.",
            )
            return Command(
                update={
                    "current_node": "await_approval",
                    "next_node": "finalize_report",
                    "approval_status": status,
                    "history": history,
                    "paused": False,
                    "pause_reason": None,
                    "terminal_status": "rejected",
                    "failure_class": "approval_rejected",
                },
                goto="finalize_report",
            )
        history = record_event(
            {"history": history},
            node="await_approval",
            status="paused",
            note="Pilot paused at the human approval boundary.",
        )
        interrupt_payload = {
            "artifact_kind": "aoa.local-ai-trial.langgraph-interrupt",
            "program_id": PROGRAM_ID,
            **TRIAL_ADAPTER.edit_gate_wire_id_entry(),
            "case_id": state["case_id"],
            "paused_at": utc_now(),
            "reason": "approval_pending",
            "approval_status": status,
            "resume_hint": "Set approval.status.json to approved or rejected, then run `scripts/aoa-langgraph-pilot resume-case <case-id>`.",
        }
        write_json(interrupt_path(log_root, state["case_id"]), interrupt_payload)
        return Command(
            update={
                "current_node": "await_approval",
                "next_node": "await_approval",
                "approval_status": status,
                "history": history,
                "paused": True,
                "pause_reason": "approval_pending",
                "terminal_status": "paused",
            },
            goto=END,
        )

    def worktree_apply(state: PilotState) -> Command[str]:
        case = load_case_spec(log_root, state["case_id"])
        with patched_trials_context(active_log_root=log_root, active_mirror_root=mirror_root):
            TRIALS.apply_w4_case(
                case,
                log_root=log_root,
                mirror_root=mirror_root,
                land_back=not is_fixture_program(),
            )
        result_summary = load_result_summary(log_root, state["case_id"]) or {}
        status = str(result_summary.get("status") or "fail")
        history = record_event(
            state,
            node="worktree_apply",
            status=status,
            note="Reused the preserved worktree-first bounded apply path.",
            extra={"failure_class": result_summary.get("failure_class")},
        )
        node_json(
            log_root,
            state["case_id"],
            "worktree-apply",
            {
                "applied_at": utc_now(),
                "result_status": status,
                "failure_class": result_summary.get("failure_class"),
            },
        )
        return Command(
            update={
                "current_node": "worktree_apply",
                "next_node": "acceptance_validate",
                "history": history,
                "failure_class": result_summary.get("failure_class"),
            },
            goto="acceptance_validate",
        )

    def acceptance_validate(state: PilotState) -> Command[str]:
        result_summary = load_result_summary(log_root, state["case_id"]) or {}
        status = str(result_summary.get("status") or "fail")
        history = record_event(
            state,
            node="acceptance_validate",
            status=status,
            note="Acceptance outcome was read from the landed legacy-compatible result summary.",
        )
        node_json(
            log_root,
            state["case_id"],
            "acceptance-validate",
            {
                "checked_at": utc_now(),
                "result_status": status,
                "failure_class": result_summary.get("failure_class"),
            },
        )
        return Command(
            update={
                "current_node": "acceptance_validate",
                "next_node": "land_or_rollback",
                "history": history,
            },
            goto="land_or_rollback",
        )

    def land_or_rollback(state: PilotState) -> Command[str]:
        result_summary = load_result_summary(log_root, state["case_id"]) or {}
        landed = result_summary.get("status") == "pass"
        history = record_event(
            state,
            node="land_or_rollback",
            status="pass" if landed else "fail",
            note="Landing status was read from the legacy-compatible case result.",
        )
        node_json(
            log_root,
            state["case_id"],
            "land-or-rollback",
            {
                "checked_at": utc_now(),
                "landing_status": "landed" if landed else "not-landed",
                "result_status": result_summary.get("status"),
            },
        )
        return Command(
            update={
                "current_node": "land_or_rollback",
                "next_node": "finalize_report",
                "history": history,
                "terminal_status": "pass" if landed else "fail",
            },
            goto="finalize_report",
        )

    def finalize_report(state: PilotState) -> Command[str]:
        refresh_sidecar_outputs(log_root, mirror_root)
        result_summary = load_result_summary(log_root, state["case_id"])
        terminal_status = state.get("terminal_status")
        if result_summary:
            terminal_status = str(result_summary.get("status") or terminal_status or "fail")
        history = record_event(
            state,
            node="finalize_report",
            status=terminal_status or "unknown",
            note="Pilot index and comparison memo were refreshed.",
        )
        node_json(
            log_root,
            state["case_id"],
            "finalize-report",
            {
                "finalized_at": utc_now(),
                "terminal_status": terminal_status,
                "pilot_index": str(log_root / f"{PILOT_INDEX_NAME}.json"),
                "comparison_memo": str(mirror_root / COMPARISON_MEMO_NAME),
            },
        )
        return Command(
            update={
                "current_node": "finalize_report",
                "next_node": None,
                "history": history,
                "terminal_status": terminal_status,
            },
            goto=END,
        )

    graph = StateGraph(PilotState)
    graph.add_node("route_from_phase", route_from_phase)
    graph.add_node("preflight", preflight)
    graph.add_node("load_case", load_case)
    graph.add_node("write_initial_packet", write_initial_packet)
    graph.add_node("collect_refs", collect_refs)
    graph.add_node("build_edit_proposal", build_edit_proposal)
    graph.add_node("persist_proposal", persist_proposal)
    graph.add_node("prepare_generated_proposal", prepare_generated_proposal)
    graph.add_node("await_approval", await_approval)
    graph.add_node("worktree_apply", worktree_apply)
    graph.add_node("acceptance_validate", acceptance_validate)
    graph.add_node("land_or_rollback", land_or_rollback)
    graph.add_node("finalize_report", finalize_report)
    graph.add_edge(START, "route_from_phase")
    return graph.compile()


def run_graph_case(log_root: Path, mirror_root: Path, *, case_id: str, until: str, resume: bool) -> PilotState:
    graph = build_graph(log_root, mirror_root)
    existing = load_graph_state(log_root, case_id) or {}
    state: PilotState = {
        **existing,
        "case_id": case_id,
        "until": until,
        "paused": False,
        "pause_reason": None,
        "current_node": existing.get("current_node"),
        "next_node": existing.get("next_node") or ("await_approval" if resume else "preflight"),
        "resume_count": int(existing.get("resume_count", 0)) + (1 if resume else 0),
        "history": list(existing.get("history", [])),
    }
    final_state = graph.invoke(state)
    save_graph_state(log_root, case_id, final_state)
    refresh_sidecar_outputs(log_root, mirror_root)
    return final_state


def print_status(log_root: Path, case_id: str) -> None:
    graph_state = load_graph_state(log_root, case_id)
    result_summary = load_result_summary(log_root, case_id)
    approval = approval_payload(log_root, case_id)
    payload = {
        "case_id": case_id,
        "graph_state": graph_state,
        "approval": approval,
        "result_summary": result_summary,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the LangGraph sidecar pilot on top of the preserved bounded-edit compatibility contract."
    )
    parser.add_argument("--url", default=DEFAULT_LANGCHAIN_RUN_URL)
    parser.add_argument("--program-id", default=DEFAULT_PROGRAM_ID)
    parser.add_argument("--log-root", default=None)
    parser.add_argument("--mirror-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("materialize", help="Materialize the LangGraph sidecar pilot program.")

    run_case = sub.add_parser("run-case", help="Run one sidecar pilot case.")
    run_case.add_argument("case_id")
    run_case.add_argument("--until", choices=["approval", "done"], default="done")

    resume_case = sub.add_parser("resume-case", help="Resume a paused LangGraph sidecar case from graph.state.json.")
    resume_case.add_argument("case_id")

    status_case = sub.add_parser("status", help="Print the current sidecar status for one case.")
    status_case.add_argument("case_id")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_program_runtime(program_id=args.program_id, run_url=args.url)
    log_root = Path(args.log_root) if args.log_root else default_log_root_for(PROGRAM_ID)
    mirror_root = Path(args.mirror_root) if args.mirror_root else default_mirror_root_for(PROGRAM_ID)
    valid_case_ids = {case["case_id"] for case in available_cases(log_root)}

    if args.command == "materialize":
        materialize(log_root, mirror_root)
        print(f"materialized {PROGRAM_ID} at {log_root}")
        return 0

    if args.command == "run-case":
        if args.case_id not in valid_case_ids:
            parser.error(f"unknown case_id for {PROGRAM_ID}: {args.case_id}")
            return 2
        materialize(log_root, mirror_root)
        final_state = run_graph_case(log_root, mirror_root, case_id=args.case_id, until=args.until, resume=False)
        print(json.dumps({"case_id": args.case_id, "terminal_status": final_state.get("terminal_status"), "paused": final_state.get("paused", False)}, ensure_ascii=True))
        return 0

    if args.command == "resume-case":
        if args.case_id not in valid_case_ids:
            parser.error(f"unknown case_id for {PROGRAM_ID}: {args.case_id}")
            return 2
        materialize(log_root, mirror_root)
        final_state = run_graph_case(log_root, mirror_root, case_id=args.case_id, until="done", resume=True)
        print(json.dumps({"case_id": args.case_id, "terminal_status": final_state.get("terminal_status"), "paused": final_state.get("paused", False)}, ensure_ascii=True))
        return 0

    if args.command == "status":
        if args.case_id not in valid_case_ids:
            parser.error(f"unknown case_id for {PROGRAM_ID}: {args.case_id}")
            return 2
        print_status(log_root, args.case_id)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
