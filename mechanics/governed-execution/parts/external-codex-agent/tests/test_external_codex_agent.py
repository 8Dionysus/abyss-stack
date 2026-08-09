from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from aoa_sdk.a2a.rebase import (
    QuestPassport,
    SummonIntent,
    build_summon_request_payload,
)
from aoa_sdk.contracts.control_plane import (
    ProvenanceRef,
    RunPlan,
    canonical_digest,
)
from aoa_sdk.control_plane import (
    ContinuationObligation,
    IncarnationPermissionPosture,
    IncarnationStopCondition,
    IncarnationToolProfile,
    IncarnationUsageMetering,
    WakeCondition,
    WakeEscalationPolicy,
    build_agent_incarnation_binding,
    load_model_realization_ref,
)
from aoa_sdk.runtime_adapters import (
    load_abyss_stack_external_codex_runtime_profile,
)


pytestmark = pytest.mark.skipif(
    "AOA_SDK_SOURCE_ROOT" not in os.environ,
    reason="paired source proof requires AOA_SDK_SOURCE_ROOT",
)

PART_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = Path(os.environ.get("AOA_SDK_SOURCE_ROOT", "/unavailable"))
AGENTS_ROOT = Path(os.environ.get("AOA_AGENTS_SOURCE_ROOT", "/unavailable"))
SKILLS_ROOT = Path(os.environ.get("AOA_SKILLS_SOURCE_ROOT", "/unavailable"))
PLAN_FIXTURE = (
    SDK_ROOT
    / "mechanics/boundary-bridge/parts/plan-compilation-control-plane/examples"
    / "a2a-eval-only.run-plan.json"
)
PROFILE_PATH = PART_ROOT / "runtime-profile.v1.json"
REPORT_SCHEMA_PATH = PART_ROOT / "schemas/external-codex-report.schema.json"
SUMMON_REQUEST_SCHEMA_PATH = (
    SDK_ROOT
    / "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SUMMON_REQUEST_SCHEMA_REF = (
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SUMMON_REQUEST_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-request:v4"
OWNER_EXECUTION_REQUEST_SCHEMA_PATH = (
    AGENTS_ROOT / "skills/aoa-summon/references/summon-request-v3.schema.json"
)
TASK_LOCAL_DAG_SCHEMA_PATH = SKILLS_ROOT / "schemas/task_local_dag_v2.schema.json"
CONTROLLER_PATH = PART_ROOT / "external_codex_agent.py"
BINDER_PATH = PART_ROOT / "bind_external_actor_launch.py"
PREPARER_PATH = PART_ROOT / "prepare_landing_study.py"
SUPERVISOR_PATH = PART_ROOT / "external_codex_supervisor.py"
ZERO_DIGEST = "sha256:" + "0" * 64


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load controller: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


RUNTIME = _load_module("abyss_stack_external_codex_agent_under_test", CONTROLLER_PATH)
BINDER = _load_module("abyss_stack_external_actor_launch_binder", BINDER_PATH)
PREPARER = _load_module("abyss_stack_external_codex_study_preparer", PREPARER_PATH)
SUPERVISOR = _load_module(
    "abyss_stack_external_codex_supervisor_under_test",
    SUPERVISOR_PATH,
)


def _digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _digest_path(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_model_realization(
    path: Path,
    *,
    workspace_write: bool,
    role_mcp: str | None = None,
) -> None:
    mcp_profiles = {
        "aoa_evals": "abyss-stack:external_codex_agent/eval-reader-v1",
        "aoa_stats": "abyss-stack:external_codex_agent/stats-reader-v1",
        "aoa_memo": "abyss-stack:external_codex_agent/memo-reader-v1",
    }
    profile_id = (
        mcp_profiles[role_mcp]
        if role_mcp is not None
        else "abyss-stack:external_codex_agent/bounded-repo-write-v1"
        if workspace_write
        else "abyss-stack:external_codex_agent/bounded-source-readonly-v1"
    )
    required_tools = (
        ["shell-read", "workspace-write"]
        if workspace_write
        else ["shell-read"]
    )
    _write_json(
        path,
        {
            "$schema": "https://schemas.aoa.local/models/model-realization.schema.json",
            "schema_version": "aoa_model_realization_v1",
            "kind": "ModelRealization",
            "lifecycle_state": "declared",
            "model_realization_id": (
                "model-realization:transport-fixture/luna/max/"
                + ("workspace-write" if workspace_write else "read-only")
            ),
            "configuration": {
                "access": {
                    "auth_regime": "chatgpt_login",
                    "billing_regime": "chatgpt_quota",
                },
                "runtime": {
                    "product": "codex-cli",
                    "version": "0.147.0",
                    "transport": "exec-jsonl",
                    "model_slug": "gpt-5.6-luna",
                },
                "reasoning_effort": "max",
                "tools": {
                    "profile_ref": profile_id,
                    "required_tools": required_tools,
                    "required_mcp_servers": (
                        [role_mcp] if role_mcp is not None else []
                    ),
                    "inheritance_allowed": False,
                },
                "permissions": {
                    "sandbox_mode": (
                        "workspace-write" if workspace_write else "read-only"
                    ),
                    "approval_policy": "never",
                    "network_access": "disabled",
                    "external_effects": False,
                },
            },
            "configuration_fingerprint": ZERO_DIGEST,
        },
    )


def _provenance(
    owner: str,
    artifact_ref: str,
    *,
    digest: str,
    source_ref: str = "fixture-source",
    schema_ref: str = "schemas/fixture.schema.json",
    schema_version: str = "fixture-v1",
) -> ProvenanceRef:
    return ProvenanceRef(
        owner_repo=owner,
        artifact_ref=artifact_ref,
        source_ref=source_ref,
        artifact_digest=digest,
        schema_ref=schema_ref,
        schema_version=schema_version,
    )


def _git(workspace: Path, *args: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _fake_codex(path: Path) -> None:
    path.write_text(
        r"""#!/usr/bin/python3
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("codex-cli 0.147.0")
    raise SystemExit(0)
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT", file=sys.stderr)
    raise SystemExit(0)
if args[:3] == ["debug", "models", "--bundled"]:
    print(json.dumps({"models": [
        {"slug": "gpt-5.6-luna", "supported_reasoning_levels": [
            {"effort": "xhigh"}, {"effort": "max"}
        ]},
        {"slug": "gpt-5.6-sol", "supported_reasoning_levels": [
            {"effort": "max"}
        ]}
    ]}))
    raise SystemExit(0)

prompt = sys.stdin.read()
parent_match = re.search(
    r"<parent_payload>\n(.*?)\n</parent_payload>", prompt, re.S
)
if parent_match is not None:
    parent = json.loads(parent_match.group(1))
    thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, parent["reentry_id"]))
    print(json.dumps({"type": "thread.started", "thread_id": thread_id}), flush=True)
    print(json.dumps({"type": "turn.started"}), flush=True)
    if "parent-tool-event" in parent["reentry_id"]:
        print(json.dumps({"type": "item.completed", "item": {
            "type": "command_execution",
            "command": "/usr/bin/true",
            "status": "completed",
            "exit_code": 0,
        }}), flush=True)
    if "distilled_child_return" in parent:
        distilled = parent["distilled_child_return"]
        child_ref = distilled["child_result_ref"]
        output_value = {
            "schema_version": "abyss_stack_external_codex_parent_reentry_v1",
            "reentry_id": parent["reentry_id"],
            "continuation_id": parent["continuation_id"],
            "child_task_id": distilled["child_task_id"],
            "child_result_digest": child_ref["artifact_digest"],
            "observed_event_digest": distilled["observed_event_digest"],
            "decision": "authority_review_required",
            "next_action": "request_human_authority",
            "summary": "The exact authority event returned to the parent thread.",
        }
    else:
        output_value = {
            "schema_version": "abyss_stack_external_codex_parent_yield_v1",
            "reentry_id": parent["reentry_id"],
            "decision": "yield",
            "continuation_id": parent["continuation"]["continuation_id"],
            "child_task_id": parent["child_task"]["task_id"],
            "expected_event_kind": parent["expected_wake"]["event_kind"],
            "deferred_parent_decisions": parent["deferred_parent_decisions"],
            "summary": "The parent inference ended with one durable wait obligation.",
        }
    output = Path(args[args.index("-o") + 1])
    output.write_text(json.dumps(output_value) + "\n", encoding="utf-8")
    print(json.dumps({
        "type": "turn.completed",
        "usage": {
            "input_tokens": 80,
            "cached_input_tokens": 10,
            "output_tokens": 20,
        },
    }), flush=True)
    raise SystemExit(0)
task_match = re.search(r"<task>\n(.*?)\n</task>", prompt, re.S)
projection_match = re.search(
    r"<workspace_projection>\n(.*?)\n</workspace_projection>", prompt, re.S
)
identity_match = re.search(r"incarnation_id='([^']+)'", prompt)
if task_match is None or projection_match is None or identity_match is None:
    raise SystemExit(11)
task = json.loads(task_match.group(1))
workspace_projection = json.loads(projection_match.group(1))
incarnation_id = identity_match.group(1)
resume = "resume" in args
thread_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, incarnation_id))
execution_root = Path(args[args.index("-C") + 1])
workspace = Path(workspace_projection["target_workspace"])
if execution_root != Path(workspace_projection["codex_execution_root"]):
    raise SystemExit(12)

def emit(value):
    print(json.dumps(value), flush=True)

emit({"type": "thread.started", "thread_id": thread_id})
emit({"type": "turn.started"})
if "FAKE_INVALID_JSONL" in task["objective"]:
    print("{not-json", flush=True)
    time.sleep(60)
if "FAKE_OVERSIZED_UNTERMINATED_EVENT" in task["objective"]:
    sys.stdout.write("x" * 65536)
    sys.stdout.flush()
    time.sleep(60)
if "FAKE_SPAWN_DESCENDANT" in task["objective"] and not resume:
    ignore_term = "FAKE_TERM_RESISTANT_DESCENDANT" in task["objective"]
    child_code = (
        "import os,signal,time; "
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_term else "")
        + "fields=next(line for line in open('/proc/self/status') "
        "if line.startswith('NSpid:')).split()[1:]; "
        "print(fields[0], flush=True); time.sleep(60)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session="FAKE_SETSID_DESCENDANT" in task["objective"],
    )
    descendant_pid = int(child.stdout.readline())
    time.sleep(0.2)
    emit({"type": "item.completed", "item": {
        "type": "agent_message", "text": f"fixture-descendant:{descendant_pid}"
    }})
if "FAKE_WAIT_FOR_INTERRUPT" in task["objective"] and not resume:
    time.sleep(60)
if "FAKE_WRITE_OUT_OF_SCOPE" in task["objective"]:
    (workspace / "unexpected.txt").write_text("drift\n", encoding="utf-8")
if "FAKE_CREATE_FIFO_OUT_OF_SCOPE" in task["objective"]:
    os.mkfifo(workspace / "unexpected.pipe")
if "FAKE_WRITE_ALLOWED" in task["objective"]:
    (workspace / "landing-note.md").write_text("bounded preparation\n", encoding="utf-8")
if "FAKE_SAME_STATUS_MUTATION" in task["objective"]:
    (workspace / "dirty-note.txt").write_text("same status, changed bytes\n", encoding="utf-8")
if "FAKE_WRITE_IGNORED" in task["objective"]:
    (workspace / "cache" / "output.txt").write_text(
        "ignored bytes changed\n", encoding="utf-8"
    )
if "FAKE_UNKNOWN_COMMAND" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution", "status": "completed", "exit_code": 0
    }})
if "FAKE_OPAQUE_INDIRECT_COMMAND" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/python3 -c 'print(42)'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_OPAQUE_LAUNCH_WRAPPER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/nice /usr/bin/cat /home/fixture/.ssh/id_rsa",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_DEEP_SHELL_NESTING" in task["objective"]:
    nested_command = "/usr/bin/git push"
    for _ in range(4):
        nested_command = shlex.join(["/usr/bin/bash", "-lc", nested_command])
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": nested_command,
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_COMMAND_SUBSTITUTION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash -lc 'echo $(cat /home/operator/.ssh/id_rsa)'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_OPAQUE_BUILD_RUNNER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/make -f /tmp/leak.mk leak",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_ALIAS_INDIRECTION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git -c alias.leak='!cat /home/operator/.ssh/id_rsa' leak",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_SOURCE_INDIRECTION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash -lc 'source scripts/helper.sh'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_SHELL_SCRIPT_BEFORE_C" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash scripts/helper.sh -c '/usr/bin/true'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_SHELL_STARTUP_FILE" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash --rcfile -x -ic '/usr/bin/true'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_LOCAL_CONFIG_WRITE" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git config --local core.hooksPath /tmp/hooks",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_CONFIG_READ" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git config --get http.https://example.com/.extraheader",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_HIDDEN_PROGRAMS" in task["objective"]:
    for command in (
        "/usr/bin/git branch --edit-description",
        "/usr/bin/git bisect run scripts/helper",
        "/usr/bin/git verify-commit HEAD",
        "/usr/bin/git fetch --upload-pack=/tmp/helper /tmp/remote",
        "/usr/bin/git notes edit HEAD",
        "/usr/bin/git grep --open-files-in-pager=/tmp/helper pattern",
        "/usr/bin/git init --separate-git-dir=/tmp/repo-meta --template=/tmp/template .",
        "/usr/bin/git ls-remote --upload-pack=/tmp/helper /tmp/remote",
    ):
        emit({"type": "item.completed", "item": {
            "type": "command_execution",
            "command": command,
            "status": "completed",
            "exit_code": 0,
        }})
if "FAKE_GIT_CAT_FILE_FILTER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git cat-file --filter HEAD:README.md",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_SIGNATURE_FORMAT" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": (
            "/usr/bin/git for-each-ref --sort=version:signature:grade"
        ),
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_HASH_OBJECT_FILTER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": (
            "/usr/bin/git hash-object -- README.md --no-filters"
        ),
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_RIPGREP_HIDDEN_PROGRAM" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/rg --pre=/bin/sh pattern scripts/helper.sh",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_JQ_ENVIRONMENT_READ" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/jq -n env",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_SORT_HIDDEN_PROGRAM" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/sort -S 4K --compress-program=/tmp/helper input",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_HIDDEN_REF_MUTATION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git update-ref refs/heads/hidden HEAD",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_SYMBOLIC_REF_MUTATION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git symbolic-ref HEAD refs/heads/other",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_GIT_REFLOG_MUTATION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git reflog expire --expire=now --all",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_DIRECT_SECRET_ENCODER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/base64 /home/operator/.ssh/id_rsa",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_WORKSPACE_EXECUTABLE" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "./scripts/helper",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_PARAMETER_EXPANSION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash -lc 'git${IFS}push'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_BARE_EXECUTABLE" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "helper --emit-secret",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_EXTGLOB_EXPANSION" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash -O extglob -lc 'g@(it) push'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_AWK_LAUNCHER" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/awk 'BEGIN { system(\"git push\") }'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_NON_SYSTEM_SHELL" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/tmp/bash -lc '/usr/bin/true'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_UNSANDBOXED_SED" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/sed -nf scripts/leak.sed README.md",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_CONFIG_DRIVEN_GIT" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/git diff --check",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_MULTILINE_SHELL" in task["objective"]:
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": "/usr/bin/bash -lc 'true\\ngit push'",
        "status": "completed",
        "exit_code": 0,
    }})
if "FAKE_STARTED_FORBIDDEN_COMMAND" in task["objective"]:
    emit({"type": "item.started", "item": {
        "id": "fixture-command-started-before-interruption",
        "type": "command_execution",
        "command": "/usr/bin/git push; /usr/bin/true",
        "status": "in_progress",
    }})
    time.sleep(60)
for validation in task["validation_commands"]:
    validation_argv = validation["argv"]
    if "FAKE_UNBOUND_VALIDATION_CWD" not in task["objective"]:
        validation_argv = [
            "/usr/bin/env", "-C", str(workspace), "--", *validation_argv
        ]
    emit({"type": "item.completed", "item": {
        "type": "command_execution",
        "command": shlex.join(validation_argv),
        "status": "completed",
        "exit_code": 0,
    }})
report_status = "review_required" if task["review_required"] else "completed"
report = {
    "schema_version": "abyss_stack_external_codex_report_v1",
    "task_id": task["task_id"],
    "incarnation_id": incarnation_id,
    "status": report_status,
    "decision": (
        "return_for_repair"
        if report_status == "review_required" and task["task_family"] == "landing_review"
        else "submit_for_review"
        if report_status == "review_required"
        else "proceed"
    ),
    "transition": {
        "from_status": task["transition"]["from_status"],
        "to_status": task["transition"]["target_status"],
        "owner": task["target_owner"],
        "evidence_refs": ["source:README.md#L1"],
        "approval_posture": task["transition"]["approval_posture"],
        "rollback_reentry_route": task["transition"]["rollback_reentry_route"],
    },
    "summary": "Bounded fixture landing result.",
    "findings": [],
    "artifact_paths": [],
    "validation_claims": [{
        "command_id": item["command_id"],
        "status": "passed",
        "evidence_ref": "runtime:validation:" + item["command_id"],
    } for item in task["validation_commands"]],
    "residuals": [],
    "reentry_request": {
        "condition_id": "review-required" if task["review_required"] else "result-ready",
        "proposed_action": "activate_review_role",
        "reason": "The exact structured result is ready for independent review.",
    },
    "owner_acceptance_claimed": False,
    "external_effects_claimed": False,
}
if task["task_family"] == "landing_ambiguity_stop":
    report["status"] = "authority_blocked"
    report["decision"] = "escalate"
    report["reentry_request"] = {
        "condition_id": "authority-needed",
        "proposed_action": "wake_parent",
        "reason": "The fixed ambiguity requires the sole human authority.",
    }
    report["residuals"] = ["Human authority must choose the intended owner meaning."]
prepared_review = "Проведи независимый" in task["objective"]
if prepared_review:
    report["reentry_request"] = {
        "condition_id": (
            "review-required" if task["review_required"] else "review-complete"
        ),
        "proposed_action": "stop",
        "reason": "The independent review reached one terminal decision.",
    }
if "FAKE_BYPASS_REVIEW" in task["objective"]:
    report["status"] = "completed"
    report["decision"] = "proceed"
    report["reentry_request"]["condition_id"] = "result-ready"
if "FAKE_RETURN_FOR_REPAIR" in task["objective"]:
    report["status"] = "review_required"
    report["decision"] = "return_for_repair"
    report["transition"]["to_status"] = task["transition"][
        "review_required_status"
    ]
    report["reentry_request"]["condition_id"] = "review-required"
    if prepared_review:
        report["reentry_request"]["proposed_action"] = "stop"
if "FAKE_STATUS_DECISION_MISMATCH" in task["objective"]:
    report["decision"] = "return_for_repair"
if "FAKE_IDENTITY_MISMATCH_ON_START" in task["objective"] and not resume:
    report["incarnation_id"] = incarnation_id.replace("incarnation:", "incation:", 1)
if "FAKE_REVIEW_TRANSITION_MISMATCH" in task["objective"]:
    report["status"] = "review_required"
    report["decision"] = (
        "return_for_repair"
        if task["task_family"] == "landing_review"
        else "submit_for_review"
    )
    report["transition"]["to_status"] = "unbound-review-target"
    report["reentry_request"]["condition_id"] = "review-required"
if "FAKE_FALSE_VALIDATION_CLAIM" in task["objective"]:
    report["validation_claims"][0]["status"] = "failed"
if "FAKE_FALSE_VALIDATION_EVIDENCE" in task["objective"]:
    report["validation_claims"][0]["evidence_ref"] = "runtime:validation:other-command"
if "FAKE_INVALID_CLAIMS" in task["objective"]:
    report["validation_claims"] = []
if "FAKE_WAKE_MISMATCH" in task["objective"]:
    report["reentry_request"]["proposed_action"] = "stop"
if "FAKE_WAKE_CONDITION_MISMATCH" in task["objective"]:
    report["reentry_request"] = {
        "condition_id": "authority-needed",
        "proposed_action": "wake_parent",
        "reason": "Crafted condition mismatch.",
    }
if "FAKE_ARTIFACT_PREEXISTING" in task["objective"]:
    report["artifact_paths"] = ["README.md"]
if "FAKE_ARTIFACT_PRODUCED" in task["objective"]:
    report["artifact_paths"] = ["landing-note.md"]
if "FAKE_INVALID_SOURCE_EVIDENCE" in task["objective"]:
    report["findings"] = [{
        "severity": "blocking",
        "category": "invalid-source-evidence",
        "summary": "A deliberately absent source path must fail closed.",
        "evidence_refs": ["source:README.md/does-not-exist#L1"],
    }]
if "FAKE_INVALID_SOURCE_LINE" in task["objective"]:
    report["findings"] = [{
        "severity": "blocking",
        "category": "invalid-source-line",
        "summary": "A deliberately invalid source line must fail closed.",
        "evidence_refs": ["source:README.md#L999"],
    }]
if "FAKE_OUT_OF_SCOPE_SOURCE_EVIDENCE" in task["objective"]:
    report["findings"] = [{
        "severity": "blocking",
        "category": "out-of-scope-source-evidence",
        "summary": "An existing source outside allowed_paths must fail closed.",
        "evidence_refs": ["source:.git/HEAD#L1"],
    }]
if "FAKE_VALID_IMMUTABLE_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = ["immutable:fixture-readme#L1"]
if "FAKE_DUPLICATE_EVIDENCE_REFS" in task["objective"]:
    report["transition"]["evidence_refs"] = [
        "source:README.md#L1",
        "source:README.md#L1",
    ]
    report["findings"] = [{
        "category": "idempotent-evidence",
        "evidence_refs": [
            "source:README.md#L1",
            "source:README.md#L1",
        ],
        "severity": "info",
        "summary": "The exact evidence identity is repeated without changing meaning.",
    }]
if "FAKE_MISSING_IMMUTABLE_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = ["immutable:missing-input#L1"]
if "FAKE_INVALID_IMMUTABLE_LINE" in task["objective"]:
    report["transition"]["evidence_refs"] = ["immutable:fixture-readme#L999"]
if "FAKE_ORDINAL_IMMUTABLE_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = ["immutable:001.input#L1"]
if "FAKE_OPAQUE_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = ["artifact:/tmp/unbound#L1"]
if "FAKE_VALID_RUNTIME_FINAL_MANIFEST_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = [
        "runtime:workspace-final-manifest#status_entries"
    ]
if "FAKE_INVALID_RUNTIME_FINAL_MANIFEST_ANCHOR" in task["objective"]:
    report["transition"]["evidence_refs"] = [
        "runtime:workspace-final-manifest#absent-final-manifest-key"
    ]
output = Path(args[args.index("-o") + 1])
usage = {
    "input_tokens": 12000 if "FAKE_TOKEN_OVERRUN" in task["objective"] else 120,
    "cached_input_tokens": 20,
    "output_tokens": 40,
}
if "FAKE_TURN_OVERRUN" in task["objective"]:
    emit({"type": "turn.completed", "usage": usage})
if "FAKE_TOKEN_OVERRUN" in task["objective"]:
    emit({"type": "turn.completed", "usage": usage})
    output.write_text(json.dumps(report) + "\n", encoding="utf-8")
else:
    output.write_text(json.dumps(report) + "\n", encoding="utf-8")
    emit({"type": "turn.completed", "usage": usage})
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _adapt_plan(
    *,
    task_ref: ProvenanceRef,
    summon_request_ref: ProvenanceRef,
    role_id: str,
    role_ref: ProvenanceRef,
    role_effect_class: str,
    workspace_ref: ProvenanceRef,
    immutable_refs: tuple[ProvenanceRef, ...],
    report_schema_ref: ProvenanceRef,
    extra_role_refs: tuple[tuple[str, ProvenanceRef], ...] = (),
) -> RunPlan:
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    runtime_profile = load_abyss_stack_external_codex_runtime_profile(PROFILE_PATH)
    old_summon_request_ref = next(
        item.artifact_ref
        for item in base.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_request"
    )
    replacement_roles = {role_id: role_ref}
    replacement_roles.update(extra_role_refs)
    old_role_refs = {
        item.provenance: replacement_roles[item.agent_id]
        for item in base.scenario_binding.agent_refs
        if item.agent_id in replacement_roles
    }
    old_runtime_ref = base.runtime_profile.provenance

    def replace_ref(value: ProvenanceRef) -> ProvenanceRef:
        if value == old_summon_request_ref:
            return summon_request_ref
        if value in old_role_refs:
            return old_role_refs[value]
        if value == old_runtime_ref:
            return runtime_profile.provenance
        return value

    def unique_refs(*values: ProvenanceRef) -> tuple[ProvenanceRef, ...]:
        result: list[ProvenanceRef] = []
        for value in values:
            if value not in result:
                result.append(value)
        return tuple(result)

    scenario = base.scenario_binding.model_copy(
        update={
            "agent_refs": tuple(
                item.model_copy(update={"provenance": replace_ref(item.provenance)})
                for item in base.scenario_binding.agent_refs
            ),
            "input_refs": tuple(
                replace_ref(item) for item in base.scenario_binding.input_refs
            ),
            "input_artifact_bindings": tuple(
                item.model_copy(update={"artifact_ref": replace_ref(item.artifact_ref)})
                for item in base.scenario_binding.input_artifact_bindings
            ),
        }
    )
    steps = tuple(
        step.model_copy(
            update={
                "agent_refs": tuple(
                    item.model_copy(update={"provenance": replace_ref(item.provenance)})
                    for item in step.agent_refs
                ),
                "input_refs": tuple(replace_ref(item) for item in step.input_refs),
                **(
                    {"effect_class": role_effect_class}
                    if any(item.agent_id == role_id for item in step.agent_refs)
                    else {}
                ),
            }
        )
        for step in base.steps
    )
    source_refs = tuple(replace_ref(item) for item in base.snapshot.source_refs)
    source_refs = unique_refs(
        *source_refs,
        task_ref,
        workspace_ref,
        *immutable_refs,
        report_schema_ref,
    )
    snapshot = base.snapshot.model_copy(
        update={"source_refs": source_refs, "snapshot_digest": ZERO_DIGEST}
    )
    snapshot = snapshot.model_copy(
        update={
            "snapshot_digest": canonical_digest(
                snapshot,
                exclude={"snapshot_digest"},
            )
        }
    )
    runtime_profile = runtime_profile.model_copy(
        update={
            "constraint_refs": unique_refs(
                *runtime_profile.constraint_refs,
                task_ref,
                workspace_ref,
                *immutable_refs,
                report_schema_ref,
            )
        }
    )
    plan = base.model_copy(
        update={
            "scenario_binding": scenario,
            "runtime_profile": runtime_profile,
            "snapshot": snapshot,
            "steps": steps,
            "plan_digest": ZERO_DIGEST,
        }
    )
    plan = plan.model_copy(
        update={"plan_digest": canonical_digest(plan, exclude={"plan_digest"})}
    )
    return RunPlan.model_validate(plan.model_dump(mode="python"))


def _fixture(
    tmp_path: Path,
    *,
    objective_marker: str = "",
    role_id: str = "architect",
    task_family: str = "landing_readiness",
    parent_task_id: str = "parent:fixture:goal",
    identity_suffix: str = "luna-max",
    state_root: Path | None = None,
    shared_workspace: Path | None = None,
    extra_immutable_inputs: tuple[
        tuple[str, Path, ProvenanceRef], ...
    ] = (),
    workspace_write: bool = False,
    exact_baseline: bool = False,
    review_required: bool = False,
    ignored_baseline: bool = False,
    prepare_mutation_reviewer_sources: bool = False,
    allowed_paths: tuple[str, ...] = ("README.md", "landing-note.md"),
    source_evidence_paths: tuple[str, ...] | None = None,
    summon_request_mutator: Callable[[dict[str, Any]], None] | None = None,
    validate_summon_request: bool = True,
    owner_contour: bool = False,
    role_mcp: str | None = None,
    responsibility_transfer_mutator: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if role_mcp is not None and workspace_write:
        raise AssertionError("role-scoped MCP fixtures are read-only")
    if owner_contour and (
        not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
        or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file()
    ):
        raise AssertionError(
            "owner-contour fixture requires exact aoa-agents and aoa-skills source roots"
        )
    tmp_path.mkdir(parents=True, exist_ok=True)
    workspace = shared_workspace or (tmp_path / "workspace")
    initialize_workspace = not workspace.exists()
    if initialize_workspace:
        workspace.mkdir()
        _git(workspace, "init", "-b", "main")
        _git(workspace, "config", "user.email", "fixture@example.invalid")
        _git(workspace, "config", "user.name", "Fixture")
    readme = workspace / "README.md"
    if initialize_workspace:
        readme.write_text("# Landing fixture\n", encoding="utf-8")
        _git(workspace, "add", "README.md")
        if ignored_baseline:
            (workspace / ".gitignore").write_text("cache/\n", encoding="utf-8")
            _git(workspace, "add", ".gitignore")
        _git(workspace, "commit", "-m", "fixture")
    elif ignored_baseline or exact_baseline:
        raise AssertionError(
            "shared workspace fixtures cannot create a second baseline posture"
        )
    head = _git(workspace, "rev-parse", "HEAD")
    if ignored_baseline:
        cache = workspace / "cache"
        cache.mkdir()
        (cache / "output.txt").write_text("ignored baseline\n", encoding="utf-8")
    if exact_baseline:
        (workspace / "dirty-note.txt").write_text(
            "exact dirty baseline\n", encoding="utf-8"
        )

    role_path = tmp_path / "role.json"
    _write_json(
        role_path,
        (
            {
                "schema_version": "actor-mandate-v1",
                "mandate_id": f"mandate:fixture:{role_id}",
                "role_id": role_id,
                "obligation_ref": "obligation:fixture:bounded-duty",
                "authority": ["bounded owner-local evidence and effects only"],
                "domain_procedure_refs": ["procedure:fixture:bounded-duty"],
                "continuity_posture": "role-continuity",
                "return_owner": "actor://fixture-goal-owner",
                "stop_line": "Stop before any undelegated or external effect.",
            }
            if owner_contour
            else {
                "schema_version": "fixture-role-v1",
                "role_id": role_id,
                "obligation": "Return a bounded landing assessment without owner claims.",
            }
        ),
    )
    role_ref = _provenance(
        "aoa-agents",
        (
            f"mandate:fixture:{role_id}"
            if owner_contour
            else f"generated/agent_catalog.min.json#agents/{role_id}"
        ),
        digest=_digest_path(role_path),
        schema_version=("actor-mandate-v1" if owner_contour else "fixture-v1"),
    )
    extra_role_refs: tuple[tuple[str, ProvenanceRef], ...] = ()
    reviewer_role_path: Path | None = None
    reviewer_realization_path: Path | None = None
    if prepare_mutation_reviewer_sources:
        reviewer_role_path = (
            tmp_path
            / "aoa-agents"
            / "agents/roles/reviewer/profile.json"
        )
        _write_json(
            reviewer_role_path,
            {
                "schema_version": "fixture-reviewer-role-v1",
                "role_id": "reviewer",
                "obligation": "Independently review one bounded writer result.",
            },
        )
        reviewer_role_ref = _provenance(
            "aoa-agents",
            "agents/roles/reviewer/profile.json",
            digest=_digest_path(reviewer_role_path),
        )
        extra_role_refs = (("reviewer", reviewer_role_ref),)
        reviewer_realization_path = (
            tmp_path
            / "aoa-models"
            / "source/model-realizations/fixture-luna-max-readonly.json"
        )
        reviewer_realization_path.parent.mkdir(parents=True, exist_ok=True)
        _write_model_realization(
            reviewer_realization_path, workspace_write=False
        )
    workspace_ref = _provenance(
        "fixture-target",
        "workspace/HEAD",
        digest=_digest_bytes(head.encode()),
        source_ref=head,
        schema_ref="git:commit",
        schema_version="sha1",
    )
    immutable_ref = _provenance(
        "fixture-target",
        "README.md",
        digest=_digest_path(readme),
        source_ref=head,
        schema_ref="text/markdown",
        schema_version="fixture-v1",
    )
    report_schema_ref = _provenance(
        "abyss-stack",
        "mechanics/governed-execution/parts/external-codex-agent/schemas/"
        "external-codex-report.schema.json",
        digest=_digest_path(REPORT_SCHEMA_PATH),
        source_ref="fixture-stack-source",
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version="abyss_stack_external_codex_report_v1",
    )
    fixture_extra_inputs = list(extra_immutable_inputs)
    obligation_ref: ProvenanceRef | None = None
    dag_ref: ProvenanceRef | None = None
    transfer_ref: ProvenanceRef | None = None
    procedure_ref: ProvenanceRef | None = None
    if owner_contour:
        obligation_path = tmp_path / "agent-obligation.json"
        _write_json(
            obligation_path,
            {
                "schema_version": "agent-obligation-v1",
                "obligation_id": "obligation:fixture:bounded-duty",
                "goal_anchor": parent_task_id,
                "phase": "execution",
                "duty": "Perform one independently held bounded owner duty.",
                "domain_owner": "fixture-target",
                "current_holder": "actor://fixture-goal-owner",
                "trigger_strength": "master_decision",
                "return_owner": "actor://fixture-goal-owner",
                "stop_line": "Stop before undelegated effects.",
            },
        )
        obligation_ref = _provenance(
            "aoa-agents",
            "obligation:fixture:bounded-duty",
            digest=_digest_path(obligation_path),
            schema_version="agent-obligation-v1",
        )
        dag_path = tmp_path / "task-local-dag.json"
        _write_json(
            dag_path,
            {
                "schema_version": "aoa-task-local-dag-v2",
                "authority": False,
                "plan_id": "dag-0123456789abcdef",
                "request": {"query": "Perform the admitted bounded duty."},
                "source_graph": {"path": "generated/capability_graph.json", "content_hash": "0" * 64},
                "status": "ready",
                "selected_capabilities": ["mode.agents.transfer-responsibility"],
                "nodes": [],
                "edges": [],
                "external_inputs": [],
                "execution_stages": [["mode.agents.transfer-responsibility"]],
                "checkpoints": [],
                "terminal": {
                    "lifetime": "task-local",
                    "success_condition": "all selected nodes reached verified terminal conditions",
                },
                "warnings": [],
                "blockers": [],
            },
        )
        dag_ref = _provenance(
            "aoa-skills",
            "dag:fixture:bounded-duty",
            digest=_digest_path(dag_path),
            schema_version="aoa-task-local-dag-v2",
        )
        transfer_path = tmp_path / "responsibility-transfer.json"
        responsibility_transfer = {
                "schema_version": "responsibility-transfer-v1",
                "transfer_id": "transfer:fixture:goal-owner-to-actor",
                "state": "accepted",
                "holder_ids": [
                    "actor://fixture-goal-owner",
                    f"actor://fixture/{role_id}",
                ],
                "obligation_ref": obligation_ref.artifact_ref,
                "mandate_ref": role_ref.artifact_ref,
                "task_local_dag_ref": dag_ref.artifact_ref,
                "return_owner": "actor://fixture-goal-owner",
            }
        if responsibility_transfer_mutator is not None:
            responsibility_transfer_mutator(responsibility_transfer)
        _write_json(transfer_path, responsibility_transfer)
        transfer_ref = _provenance(
            "aoa-agents",
            "transfer:fixture:goal-owner-to-actor",
            digest=_digest_path(transfer_path),
            schema_version="responsibility-transfer-v1",
        )
        procedure_path = tmp_path / "domain-procedure.json"
        _write_json(
            procedure_path,
            {
                "schema_version": "owner-procedure-v1",
                "procedure_id": "procedure:fixture:bounded-duty",
                "owner": "fixture-target",
                "instruction": "Inspect exact inputs and return the named output.",
            },
        )
        procedure_ref = _provenance(
            "fixture-target",
            "procedure:fixture:bounded-duty",
            digest=_digest_path(procedure_path),
            schema_version="owner-procedure-v1",
        )
        fixture_extra_inputs.extend(
            (
                ("agent-obligation", obligation_path, obligation_ref),
                ("actor-mandate", role_path, role_ref),
                ("task-local-dag", dag_path, dag_ref),
                ("responsibility-transfer", transfer_path, transfer_ref),
                ("domain-procedure", procedure_path, procedure_ref),
            )
        )
    if exact_baseline:
        manifest_path = tmp_path / "workspace-manifest.json"
        _write_json(manifest_path, RUNTIME.build_workspace_manifest(workspace))
        manifest_ref = _provenance(
            "fixture-target",
            "workspace-manifest.json",
            digest=_digest_path(manifest_path),
            source_ref=head,
            schema_ref=(
                "mechanics/governed-execution/parts/external-codex-agent/"
                "schemas/external-codex-workspace-manifest.schema.json"
            ),
            schema_version="abyss_stack_external_codex_workspace_manifest_v1",
        )
        fixture_extra_inputs.append(
            ("workspace-manifest", manifest_path, manifest_ref)
        )
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    continuation_id = f"continuation:fixture:{identity_suffix}"
    incarnation_id = f"incarnation:fixture:{identity_suffix}"
    task_id = f"task:fixture:{identity_suffix}"
    session_id = f"session:fixture:{identity_suffix}"
    summon_outputs = (
        ["independent_landing_review"]
        if task_family == "landing_review"
        else ["external_codex_agent_result", "independent_landing_review"]
    )
    capability_id = {
        "coder": "workflow.operations.repository-change",
        "reviewer": "mode.verification.contract",
    }.get(role_id, "mode.knowledge.authority-map")
    reviewed_artifact_path = next(
        (
            str(path)
            for input_id, path, _ in fixture_extra_inputs
            if input_id == "writer-runtime-result"
        ),
        None,
    )
    summon_request = build_summon_request_payload(
        QuestPassport(
            difficulty="d2_slice",
            risk="r1_repo_local" if workspace_write else "r0_readonly",
            control_mode="codex_supervised",
            delegate_tier="executor" if role_id == "coder" else "verifier",
            route_anchor="fixture:a2a-summon-return",
            expected_artifacts=summon_outputs,
            self_agent=False,
        ),
        SummonIntent(
            desired_role=role_id,
            child_agent_id=incarnation_id,
            capability_refs=[capability_id],
            expected_outputs=summon_outputs,
            parent_task_id=parent_task_id,
            session_ref=session_id,
            reviewed_artifact_path=reviewed_artifact_path,
            audit_refs=["fixture:a2a-summon-return"],
            playbook_ref="fixture:a2a-summon-return",
            review_required=review_required,
            transport_preference="codex_local",
            require_progression=False,
            workspace_root=str(workspace),
        ),
        expected_outputs=summon_outputs,
        reviewed_artifact_path=reviewed_artifact_path,
        audit_refs=["fixture:a2a-summon-return"],
    )
    if summon_request_mutator is not None:
        summon_request_mutator(summon_request)
    summon_request_path = tmp_path / "summon-request.json"
    _write_json(summon_request_path, summon_request)
    if validate_summon_request:
        RUNTIME.validate_json(
            summon_request,
            SUMMON_REQUEST_SCHEMA_PATH,
            label="fixture canonical summon request",
        )
    summon_request_ref = _provenance(
        "aoa-sdk" if owner_contour else "abyss-stack",
        f"runtime-studies/fixtures/{identity_suffix}/summon-request.json",
        digest=_digest_path(summon_request_path),
        source_ref="fixture-a2a-summon-source",
        schema_ref=SUMMON_REQUEST_SCHEMA_REF,
        schema_version=SUMMON_REQUEST_SCHEMA_VERSION,
    )
    summon_decision_ref: ProvenanceRef | None = None
    if owner_contour:
        summon_decision_path = tmp_path / "summon-decision.json"
        _write_json(
            summon_decision_path,
            {
                "schema_version": "urn:aoa-sdk:a2a:summon-result:v4",
                "allowed": True,
                "execution_surface": "external_cli",
                "request_artifact_digest": summon_request_ref.artifact_digest,
            },
        )
        summon_decision_ref = _provenance(
            "aoa-sdk",
            f"runtime-studies/fixtures/{identity_suffix}/summon-decision.json",
            digest=_digest_path(summon_decision_path),
            source_ref=summon_request_ref.artifact_digest,
            schema_version="urn:aoa-sdk:a2a:summon-result:v4",
        )
        fixture_extra_inputs.append(
            ("summon-decision", summon_decision_path, summon_decision_ref)
        )
    summon_request_schema_ref = _provenance(
        "aoa-sdk",
        SUMMON_REQUEST_SCHEMA_REF,
        digest=_digest_path(SUMMON_REQUEST_SCHEMA_PATH),
        source_ref=(
            "uncommitted-sdk-source@" + _digest_path(SUMMON_REQUEST_SCHEMA_PATH)
        ),
        schema_ref="https://json-schema.org/draft/2020-12/schema",
        schema_version=SUMMON_REQUEST_SCHEMA_VERSION,
    )
    immutable_inputs = [
        {
            "input_id": "fixture-readme",
            "local_path": str(readme),
            "provenance": immutable_ref.model_dump(mode="json"),
        }
    ]
    immutable_inputs.extend(
        {
            "input_id": input_id,
            "local_path": str(path),
            "provenance": provenance.model_dump(mode="json"),
        }
        for input_id, path, provenance in fixture_extra_inputs
    )
    immutable_inputs.extend(
        (
            {
                "input_id": (
                    "review-summon-request"
                    if task_family == "landing_review"
                    else "summon-request"
                ),
                "local_path": str(summon_request_path),
                "provenance": summon_request_ref.model_dump(mode="json"),
            },
            {
                "input_id": "summon-request-schema",
                "local_path": str(SUMMON_REQUEST_SCHEMA_PATH),
                "provenance": summon_request_schema_ref.model_dump(mode="json"),
            },
        )
    )
    task = {
        "schema_version": "abyss_stack_external_codex_task_v1",
        "task_id": task_id,
        "correlation_id": base.correlation_id,
        "continuation_id": continuation_id,
        "expected_incarnation_id": incarnation_id,
        "task_family": task_family,
        "execution_posture": (
            "independent_review"
            if task_family == "landing_review"
            else "bounded_execution"
        ),
        "parent_task_id": parent_task_id,
        "objective": f"Inspect the exact landing fixture. {objective_marker}".strip(),
        "transition": {
            "from_status": "candidate",
            "target_status": "ready_for_review",
            **(
                {"review_required_status": "review_required_source_repair"}
                if task_family == "landing_review"
                else {}
            ),
            "approval_posture": "human_owner_required_after_review",
            "rollback_reentry_route": "return_to_parent_without_effect",
        },
        "target_owner": "fixture-target",
        "authority_scope": ["fixture-target", "aoa-agents", "abyss-stack"],
        "allowed_effect_class": "repo_mutation" if workspace_write else "read_only",
        "allowed_paths": list(allowed_paths),
        "immutable_inputs": immutable_inputs,
        "done_state": ["Return one schema-valid evidence-bearing report."],
        "validation_commands": [
            {"command_id": "git-status", "argv": ["git", "status", "--short"], "cwd": "."}
        ],
        "expected_artifacts": ["landing_report"],
        "forbidden_effects": [
            "commit",
            "push",
            "pull_request",
            "merge",
            "tag",
            "release",
            "publication",
            "service_mutation",
            "secret_access",
            "global_config_mutation",
        ],
        "ambiguity_policy": "escalate",
        "review_required": review_required,
        "return_owner": "fixture-target",
    }
    if source_evidence_paths is not None:
        task["source_evidence_paths"] = list(source_evidence_paths)
    task_path = tmp_path / "task.json"
    _write_json(task_path, task)
    task_ref = _provenance(
        "fixture-target",
        f"tasks/{identity_suffix}.json",
        digest=_digest_path(task_path),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/"
            "schemas/external-codex-task.schema.json"
        ),
        schema_version="abyss_stack_external_codex_task_v1",
    )
    plan = _adapt_plan(
        task_ref=task_ref,
        summon_request_ref=summon_request_ref,
        role_id=role_id,
        role_ref=role_ref,
        role_effect_class="repo_mutation" if workspace_write else "read_only",
        workspace_ref=workspace_ref,
        immutable_refs=(
            immutable_ref,
            *(item[2] for item in fixture_extra_inputs),
            summon_request_ref,
            summon_request_schema_ref,
        ),
        report_schema_ref=report_schema_ref,
        extra_role_refs=extra_role_refs,
    )
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, plan.model_dump(mode="json"))
    realization_path = tmp_path / "model-realization.json"
    _write_model_realization(
        realization_path,
        workspace_write=workspace_write,
        role_mcp=role_mcp,
    )
    model_ref = load_model_realization_ref(
        realization_path,
        artifact_ref=(
            "source/model-realizations/"
            + realization_path.name
        ),
        source_ref="fixture-aoa-models-source",
    )
    stop_conditions = (
        IncarnationStopCondition(
            condition_id="authority-boundary",
            kind="authority_boundary",
            description="Stop before any non-delegated effect.",
        ),
    )
    wake_policy = WakeEscalationPolicy(
        default_action="stop",
        conditions=(
            WakeCondition(
                condition_id="result-ready",
                event_kind="result.validated",
                action="activate_review_role",
                description="A validated result can enter independent review.",
            ),
            WakeCondition(
                condition_id="review-required",
                event_kind="result.review_required",
                action="activate_review_role",
                description="A review-gated result can enter independent review.",
            ),
            WakeCondition(
                condition_id="runtime-interrupted",
                event_kind="runtime.interrupted",
                action="continue_without_parent",
                description="Resume the exact thread from its durable checkpoint.",
            ),
            WakeCondition(
                condition_id="authority-needed",
                event_kind="run.authority_required",
                action="wake_parent",
                description="The human-owned authority boundary needs re-entry.",
            ),
        ),
        escalation_conditions=("authority-needed",),
    )
    continuation = ContinuationObligation(
        continuation_id=continuation_id,
        parent_objective_ref=workspace_ref,
        established_decision_refs=(),
        delegated_obligation="Inspect one exact landing transition and return evidence.",
        delegation_reason="The bounded landing check is repeatable and independently reviewable.",
        exact_child_identity=incarnation_id,
        owner_scope=(
            "fixture-target",
            "aoa-agents",
            "aoa-models",
            "abyss-stack",
        ),
        immutable_input_refs=(
            task_ref,
            workspace_ref,
            immutable_ref,
            *(item[2] for item in fixture_extra_inputs),
            summon_request_ref,
            summon_request_schema_ref,
        ),
        expected_output="One schema-valid landing report and runtime receipt.",
        validation_refs=(report_schema_ref,),
        deferred_parent_decisions=("Whether to accept or perform any landing effect.",),
        invariants=(
            "No external effect is authorized.",
            "The user remains the sole human authority.",
        ),
        stop_condition_ids=tuple(item.condition_id for item in stop_conditions),
        wake_condition_ids=tuple(item.condition_id for item in wake_policy.conditions),
        return_owner=workspace_ref,
        rollback_reentry_anchor=workspace_ref,
    )
    binding = build_agent_incarnation_binding(
        plan,
        binding_id=f"binding:fixture:{identity_suffix}",
        incarnation_id=incarnation_id,
        causation_id=f"causation:fixture:{identity_suffix}",
        trace_id=f"trace:fixture:{identity_suffix}",
        task_request_ref=summon_request_ref,
        role_id=role_id,
        role_contract_ref=role_ref,
        model_realization_ref=model_ref,
        workspace_source_ref=workspace_ref,
        permission_posture=IncarnationPermissionPosture(
            sandbox_mode="workspace_write" if workspace_write else "read_only",
            approval_policy="never",
            allowed_effect_classes=(
                ("repo_mutation",) if workspace_write else ("read_only",)
            ),
            network_access="disabled",
        ),
        tool_profile=IncarnationToolProfile(
            profile_id=(
                {
                    "aoa_evals": "abyss-stack:external_codex_agent/eval-reader-v1",
                    "aoa_stats": "abyss-stack:external_codex_agent/stats-reader-v1",
                    "aoa_memo": "abyss-stack:external_codex_agent/memo-reader-v1",
                }[role_mcp]
                if role_mcp is not None
                else "abyss-stack:external_codex_agent/bounded-repo-write-v1"
                if workspace_write
                else "abyss-stack:external_codex_agent/bounded-source-readonly-v1"
            ),
            profile_ref=plan.runtime_profile.provenance,
            required_tool_ids=(
                ("shell-read", "workspace-write")
                if workspace_write
                else ("shell-read",)
            ),
            required_mcp_server_ids=(
                (role_mcp,) if role_mcp is not None else ()
            ),
        ),
        usage_metering=IncarnationUsageMetering(
            metering_regime="chatgpt_quota",
            dimensions=(
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "active_wall_seconds",
                "turn_count",
                "output_bytes",
                "executed_commands",
            ),
        ),
        stop_conditions=stop_conditions,
        expected_result_schema_ref=report_schema_ref,
        continuation=continuation,
        wake_policy=wake_policy,
        provenance=_provenance(
            "aoa-sdk",
            f"bindings/fixture-{identity_suffix}.json",
            digest=ZERO_DIGEST,
        ),
    )
    binding_path = tmp_path / "binding.json"
    _write_json(binding_path, binding.model_dump(mode="json"))
    fake_codex = tmp_path / "fake-codex"
    _fake_codex(fake_codex)
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    launch = {
        "schema_version": "abyss_stack_external_codex_launch_v1",
        "launch_id": f"launch:fixture:{identity_suffix}",
        "session_id": session_id,
        "admission_class": (
            "owner_contour" if owner_contour else "transport_study_fixture"
        ),
        "plan": {"path": str(plan_path), "digest": _digest_path(plan_path)},
        "incarnation_binding": {
            "path": str(binding_path),
            "digest": _digest_path(binding_path),
        },
        "model_realization": {
            "path": str(realization_path),
            "digest": _digest_path(realization_path),
        },
        "task": {"path": str(task_path), "digest": _digest_path(task_path)},
        "runtime_profile": {
            "path": str(PROFILE_PATH),
            "digest": _digest_path(PROFILE_PATH),
        },
        "role_contract": {"path": str(role_path), "digest": _digest_path(role_path)},
        "result_schema": {
            "path": str(REPORT_SCHEMA_PATH),
            "digest": _digest_path(REPORT_SCHEMA_PATH),
        },
        **(
            {
                "owner_execution_request_schema": {
                    "path": str(OWNER_EXECUTION_REQUEST_SCHEMA_PATH),
                    "digest": _digest_path(OWNER_EXECUTION_REQUEST_SCHEMA_PATH),
                    "owner_repo": "aoa-agents",
                    "artifact_ref": "skills/aoa-summon/references/summon-request-v3.schema.json",
                    "source_ref": "84321efcb463b44a3491bdc1bbe825bf576886e7",
                    "schema_version": "summon-request-v3",
                },
                "task_local_dag_schema": {
                    "path": str(TASK_LOCAL_DAG_SCHEMA_PATH),
                    "digest": _digest_path(TASK_LOCAL_DAG_SCHEMA_PATH),
                    "owner_repo": "aoa-skills",
                    "artifact_ref": "schemas/task_local_dag_v2.schema.json",
                    "source_ref": "6515f35dd89c7902830aeac305da312d258da6ba",
                    "schema_version": "aoa-task-local-dag-v2",
                },
            }
            if owner_contour
            else {}
        ),
        "workspace_path": str(workspace),
        "workspace_expected_head": head,
        "workspace_initial_posture": (
            "exact_baseline" if exact_baseline else "clean_required"
        ),
        "workspace_manifest_input_id": "workspace-manifest",
        "codex_executable": str(fake_codex.resolve()),
        "codex_executable_digest": _digest_path(fake_codex),
        "codex_home": str(codex_home),
        "environment_allowlist": ["HOME", "LANG", "PATH"],
    }
    launch_path = tmp_path / "launch.json"
    _write_json(launch_path, launch)
    owner_execution_request_path: Path | None = None
    if owner_contour:
        assert obligation_ref is not None
        assert dag_ref is not None
        assert transfer_ref is not None
        assert procedure_ref is not None
        assert summon_decision_ref is not None

        def content_ref(
            provenance: ProvenanceRef,
            *,
            digest: str | None = None,
            schema_version: str | None = None,
            object_id: str | None = None,
        ) -> dict[str, str]:
            return {
                "object_id": object_id or provenance.artifact_ref,
                "owner_repo": provenance.owner_repo,
                "schema_version": schema_version or provenance.schema_version,
                "digest": digest or provenance.artifact_digest,
            }

        owner_execution_request = {
            "quest_passport": {
                "difficulty": "d2_slice",
                "risk": "r1_repo_local" if workspace_write else "r0_readonly",
                "control_mode": "codex_supervised",
                "delegate_tier": "executor",
                "route_anchor": parent_task_id,
                "expected_artifacts": [
                    "external_codex_agent_result",
                    *task["expected_artifacts"],
                ],
                "self_agent": False,
            },
            "summon_request": {
                "desired_role": role_id,
                "child_agent_id": incarnation_id,
                "transport_preference": "external_cli",
                "parent_task_id": parent_task_id,
                "session_ref": session_id,
                "require_progression": False,
            },
            "expected_outputs": [
                "external_codex_agent_result",
                *task["expected_artifacts"],
            ],
            "intent": "execute",
            "request_ref": f"task://fixture/{identity_suffix}/owner-execution-request",
            "request_digest": ZERO_DIGEST,
            "return_owner": "actor://fixture-goal-owner",
            "child_scope": {
                "task": task["objective"],
                "allowed_tools": list(binding.tool_profile.required_tool_ids),
                "allowed_effects": [task["allowed_effect_class"]],
                "authority_limit": "No undelegated or external effect.",
            },
            "child_stop_line": "Stop before any undelegated or external effect.",
            "child_inputs": [],
            "external_incarnation": {
                "obligation_ref": content_ref(obligation_ref),
                "actor_mandate_ref": content_ref(role_ref),
                "task_local_dag_ref": content_ref(dag_ref),
                "incarnation_binding_ref": content_ref(
                    binding.provenance,
                    digest=_digest_path(binding_path),
                    schema_version="aoa_agent_incarnation_binding_v1",
                ),
                "sdk_summon_request_ref": content_ref(summon_request_ref),
                "sdk_summon_decision_ref": content_ref(summon_decision_ref),
                "runtime_launch_ref": {
                    "object_id": launch["launch_id"],
                    "owner_repo": "abyss-stack",
                    "schema_version": "abyss_stack_external_codex_launch_v1",
                    "digest": _digest_path(launch_path),
                },
                "runtime_interface": "abyss_stack_external_codex_agent_v1",
                "responsibility_transfer_ref": {
                    **content_ref(transfer_ref),
                    "admitted_state": "accepted",
                    "holder_ids": [
                        "actor://fixture-goal-owner",
                        f"actor://fixture/{role_id}",
                    ],
                },
                "domain_procedure_refs": [content_ref(procedure_ref)],
                "continuity_ref": {
                    "object_id": continuation_id,
                    "owner_repo": "aoa-sdk",
                    "schema_version": "continuation-obligation-v1",
                    "digest": _digest_path(binding_path),
                },
                "return_event_schema_ref": {
                    "object_id": (
                        "mechanics/governed-execution/parts/external-codex-agent/"
                        "schemas/external-codex-event.schema.json"
                    ),
                    "owner_repo": "abyss-stack",
                    "schema_version": "abyss_stack_external_codex_event_v1",
                    "digest": _digest_path(RUNTIME.EVENT_SCHEMA_PATH),
                },
                "launches_separate_os_process": True,
                "uses_builtin_codex_subagents": False,
                "separate_cli_session": True,
                "usage_metering": "observe_only_no_budget",
            },
        }
        owner_execution_request_path = tmp_path / "owner-execution-request.json"
        _write_json(owner_execution_request_path, owner_execution_request)
    return {
        "runtime": RUNTIME.ExternalCodexRuntime(state_root or (tmp_path / "state")),
        "launch_path": launch_path,
        "launch": launch,
        "binding_path": binding_path,
        "task_path": task_path,
        "role_path": role_path,
        "realization_path": realization_path,
        "workspace": workspace,
        "session_id": launch["session_id"],
        "task_id": task["task_id"],
        "summon_request_path": summon_request_path,
        "owner_execution_request_path": owner_execution_request_path,
        "reviewer_role_path": reviewer_role_path,
        "reviewer_realization_path": reviewer_realization_path,
    }


def _wait_terminal(runtime: Any, session_id: str, *, timeout: float = 10) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runtime.status(session_id)
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    raise AssertionError(f"external Codex fixture did not stop: {runtime.status(session_id)}")


def test_supervisor_waits_on_signal_notification_without_20hz_procfs_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 4242

        def __init__(self) -> None:
            self.exited = False

        def poll(self) -> int | None:
            return 0 if self.exited else None

    process = FakeProcess()
    clock = [10.0]
    reaps: list[tuple[int, int | None]] = []
    waits: list[float] = []

    monkeypatch.setattr(SUPERVISOR.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        SUPERVISOR,
        "_reap_adopted_children",
        lambda supervisor_pid, codex_pid: reaps.append(
            (supervisor_pid, codex_pid)
        ),
    )

    def complete_after_notification(_read_fd: int, timeout_seconds: float) -> None:
        waits.append(timeout_seconds)
        clock[0] += 0.2
        process.exited = True

    monkeypatch.setattr(
        SUPERVISOR,
        "_wait_for_signal_or_timeout",
        complete_after_notification,
    )
    monkeypatch.setattr(SUPERVISOR.os, "getpid", lambda: 31337)
    SUPERVISOR._termination_signal = None
    SUPERVISOR._child_state_changed = True

    result = SUPERVISOR._wait_for_codex(process, signal_read_fd=7)

    assert result == 0
    assert reaps == [(31337, 4242)]
    assert waits == [pytest.approx(SUPERVISOR.ADOPTED_REAP_INTERVAL_SECONDS)]


def test_worker_reap_refuses_reused_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[tuple[int, int]] = []
    monkeypatch.setattr(RUNTIME.os, "waitpid", lambda pid, flags: waits.append((pid, flags)))
    monkeypatch.setattr(
        RUNTIME,
        "_process_group_identity",
        lambda _pid: ("Z", 4242, 4242, 999),
    )

    RUNTIME._reap_owned_child(4242, 998)
    assert waits == []

    RUNTIME._reap_owned_child(4242, 999)
    assert waits == [(4242, os.WNOHANG)]


def test_process_identity_receipt_retries_partial_kernel_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 4242

    identities = {
        31337: SUPERVISOR.ProcessIdentity(
            pid=31337,
            parent_pid=30000,
            state="S",
            start_ticks=111,
        ),
        4242: SUPERVISOR.ProcessIdentity(
            pid=4242,
            parent_pid=31337,
            state="R",
            start_ticks=222,
        ),
    }
    real_write = SUPERVISOR.os.write

    def partial_write(descriptor: int, payload: bytes | memoryview) -> int:
        return real_write(descriptor, bytes(payload[:3]))

    monkeypatch.setattr(SUPERVISOR.os, "getpid", lambda: 31337)
    monkeypatch.setattr(
        SUPERVISOR,
        "_proc_identity",
        lambda pid: identities.get(pid),
    )
    monkeypatch.setattr(SUPERVISOR.os, "write", partial_write)
    receipt_path = tmp_path / "process-identity.json"

    SUPERVISOR._write_process_identity_receipt(receipt_path, FakeProcess())

    assert json.loads(receipt_path.read_text(encoding="utf-8")) == {
        "schema_version": "abyss_stack_external_codex_process_identity_v1",
        "supervisor_pid": 31337,
        "supervisor_start_ticks": 111,
        "codex_pid": 4242,
        "codex_start_ticks": 222,
    }


def test_supervisor_executes_verified_open_inode_after_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "codex"
    output = tmp_path / "observed.txt"
    executable.write_text(
        "#!/usr/bin/python3\n"
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text('verified-open-inode\\n')\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    expected_digest = _digest_path(executable)
    original_open = SUPERVISOR._open_verified_executable

    def replace_after_verified_open(path: str, digest: str) -> int:
        descriptor = original_open(path, digest)
        replacement = tmp_path / "replacement"
        replacement.write_text(
            "#!/usr/bin/python3\n"
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[1]).write_text('replacement-path\\n')\n",
            encoding="utf-8",
        )
        replacement.chmod(0o700)
        replacement.replace(executable)
        return descriptor

    monkeypatch.setattr(
        SUPERVISOR,
        "_open_verified_executable",
        replace_after_verified_open,
    )

    process = SUPERVISOR._launch_verified_command(
        [str(executable), str(output)],
        expected_digest,
    )

    assert process.wait(timeout=5) == 0
    assert output.read_text(encoding="utf-8") == "verified-open-inode\n"


def test_supervisor_rejects_executable_digest_drift(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    executable.chmod(0o700)

    with pytest.raises(SUPERVISOR.SupervisorError, match="digest changed"):
        SUPERVISOR._open_verified_executable(executable.as_posix(), ZERO_DIGEST)


def test_preflight_rejects_path_replacement_after_controller_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    original_containment_command = runtime._containment_command
    replaced = [False]

    def replace_before_supervisor_open(
        command: Any,
        *,
        executable_digest: str,
        identity_path: Path | None = None,
    ) -> list[str]:
        if not replaced[0] and command[0] == fixture["launch"]["codex_executable"]:
            replacement = tmp_path / "replacement-codex"
            replacement.write_text("#!/usr/bin/python3\n", encoding="utf-8")
            replacement.chmod(0o700)
            replacement.replace(Path(command[0]))
            replaced[0] = True
        return original_containment_command(
            command,
            executable_digest=executable_digest,
            identity_path=identity_path,
        )

    monkeypatch.setattr(runtime, "_containment_command", replace_before_supervisor_open)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.preflight(fixture["launch_path"])

    assert exc_info.value.code == "codex_preflight_failed"


@pytest.mark.parametrize("supervisor_return_code", (0, 17))
def test_completed_supervisor_preserves_terminal_child_identity_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_return_code: int,
) -> None:
    class FakeProcess:
        pid = 31337

        def poll(self) -> int:
            return supervisor_return_code

    receipt_path = tmp_path / "process-identity.json"
    receipt = {
        "schema_version": "abyss_stack_external_codex_process_identity_v1",
        "supervisor_pid": 31337,
        "supervisor_start_ticks": 111,
        "codex_pid": 4242,
        "codex_start_ticks": 222,
    }
    _write_json(receipt_path, receipt)
    monkeypatch.setattr(
        RUNTIME,
        "_process_parent_identity",
        lambda _pid: ("S", 1, 9000, 9000, 333),
    )

    observed, artifact_ref = RUNTIME._wait_for_process_identity_receipt(
        receipt_path,
        process=FakeProcess(),
        supervisor_start_ticks=111,
    )

    assert observed == receipt
    assert artifact_ref["artifact_digest"] == _digest_path(receipt_path)


def test_live_supervisor_rejects_mismatched_child_identity_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 31337

        def poll(self) -> None:
            return None

    receipt_path = tmp_path / "process-identity.json"
    _write_json(
        receipt_path,
        {
            "schema_version": "abyss_stack_external_codex_process_identity_v1",
            "supervisor_pid": 31337,
            "supervisor_start_ticks": 111,
            "codex_pid": 4242,
            "codex_start_ticks": 222,
        },
    )
    monkeypatch.setattr(
        RUNTIME,
        "_process_parent_identity",
        lambda _pid: ("S", 1, 9000, 9000, 333),
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._wait_for_process_identity_receipt(
            receipt_path,
            process=FakeProcess(),
            supervisor_start_ticks=111,
        )

    assert exc_info.value.code == "codex_process_identity_invalid"


def test_preflight_and_separate_process_return_structured_result(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    preflight = runtime.preflight(fixture["launch_path"])

    assert preflight["admitted"] is True
    assert preflight["model_slug"] == "gpt-5.6-luna"
    assert preflight["reasoning_effort"] == "max"
    started = runtime.start(fixture["launch_path"])
    assert started["status"] == "running"
    assert started["worker_pid"] != os.getpid()

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])
    events = runtime.events(fixture["session_id"], after_sequence=-1)
    state = json.loads(
        runtime._state_path(fixture["session_id"]).read_text(encoding="utf-8")
    )

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["status"] == "completed"
    assert isinstance(result["thread_id"], str) and result["thread_id"]
    assert result["attempt_count"] == 1
    assert result["turn_count"] == 1
    assert result["usage_observation"] == {
        "status": "complete",
        "gap_reasons": [],
    }
    argv = result["codex_invocations"][0]["argv"]
    invocation = result["codex_invocations"][0]
    assert isinstance(invocation["supervisor_pid"], int)
    assert isinstance(invocation["codex_pid"], int)
    assert invocation["supervisor_pid"] != invocation["codex_pid"]
    identity_ref = invocation["process_identity_ref"]
    assert identity_ref["artifact_digest"] == _digest_path(
        Path(identity_ref["artifact_ref"])
    )
    assert argv[1] == str(PART_ROOT / "external_codex_supervisor.py")
    assert "--parent-pid" in argv
    assert argv[argv.index("--executable-digest") + 1] == (
        fixture["launch"]["codex_executable_digest"]
    )
    assert "/usr/bin/unshare" not in argv
    assert "/usr/bin/setpriv" not in argv
    assert "exec" in argv
    assert argv[argv.index("--disable") + 1] == "multi_agent"
    assert "spawn_agent" not in argv
    assert argv[argv.index("-s") + 1] == "workspace-write"
    execution_root = Path(invocation["execution_root"])
    assert execution_root.name == "execution-root"
    assert execution_root.parent.name == "001"
    assert argv[argv.index("-C") + 1] == str(execution_root)
    assert execution_root != fixture["workspace"]
    assert "--skip-git-repo-check" in argv
    config_overrides = [
        argv[index + 1]
        for index, value in enumerate(argv[:-1])
        if value == "-c"
    ]
    assert "sandbox_workspace_write.network_access=false" in config_overrides
    assert not any(value.startswith("default_permissions=") for value in config_overrides)
    prompt = (
        execution_root.parent / "prompt.txt"
    ).read_text(encoding="utf-8")
    assert f'"target_workspace": "{fixture["workspace"]}"' in prompt
    assert f'"codex_execution_root": "{execution_root}"' in prompt
    assert '"target_workspace_access": "read_only"' in prompt
    assert "A line anchor is spelled exactly L<number>" in prompt
    assert "A bare numeric anchor such as #35" in prompt
    execution_schema_ref = state["execution_result_schema_ref"]
    execution_schema_path = Path(execution_schema_ref["artifact_ref"])
    execution_schema = json.loads(execution_schema_path.read_text(encoding="utf-8"))
    assert execution_schema_ref["artifact_digest"] == _digest_path(
        execution_schema_path
    )
    assert argv[argv.index("--output-schema") + 1] == str(execution_schema_path)
    assert execution_schema["properties"]["task_id"]["const"] == fixture["task_id"]
    assert execution_schema["properties"]["incarnation_id"]["const"] == (
        state["incarnation_id"]
    )
    finding_evidence_pattern = execution_schema["properties"]["findings"]["items"][
        "properties"
    ]["evidence_refs"]["items"]["pattern"]
    transition_evidence_pattern = execution_schema["properties"]["transition"][
        "properties"
    ]["evidence_refs"]["items"]["pattern"]
    materialized_input_ids = {
        item["input_id"] for item in state["materialized_task_inputs"]
    }
    assert materialized_input_ids
    for evidence_pattern in (finding_evidence_pattern, transition_evidence_pattern):
        for input_id in materialized_input_ids:
            assert re.fullmatch(
                evidence_pattern,
                f"immutable:{input_id}#objective",
            )
        assert re.fullmatch(evidence_pattern, "source:AGENTS.md#L1")
        assert re.fullmatch(
            evidence_pattern,
            "runtime:workspace-final-manifest#git_head",
        )
        assert re.fullmatch(
            evidence_pattern,
            "immutable:not-materialized#objective",
        ) is None
    process_event = next(
        item for item in events if item["event_type"] == "external_agent.process_started"
    )
    assert process_event["payload"]["supervisor_pid"] != (
        process_event["payload"]["codex_pid"]
    )
    assert process_event["payload"]["codex_pid"] != os.getpid()
    assert json.loads(PROFILE_PATH.read_text())["boundaries"][
        "uses_builtin_codex_subagents"
    ] is False


def test_role_scoped_mcp_requires_only_its_exact_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
    )
    monkeypatch.delenv("AOA_EVALS_MCP_READ_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("AOA_STATS_MCP_READ_BEARER_TOKEN", "wrong-role-token")
    monkeypatch.setenv("AOA_MEMO_MCP_READ_BEARER_TOKEN", "wrong-role-token")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(fixture["launch_path"])

    assert exc_info.value.code == "mcp_credential_unavailable"


def test_role_scoped_mcp_injects_only_selected_server_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
    )
    monkeypatch.setenv("AOA_EVALS_MCP_READ_BEARER_TOKEN", "eval-token")
    monkeypatch.setenv("AOA_STATS_MCP_READ_BEARER_TOKEN", "stats-token")
    monkeypatch.setenv("AOA_MEMO_MCP_READ_BEARER_TOKEN", "memo-token")

    fixture["runtime"].start(fixture["launch_path"])
    terminal = _wait_terminal(fixture["runtime"], fixture["session_id"])
    assert terminal["status"] == "completed"
    state = fixture["runtime"]._load_state(fixture["session_id"])
    argv = state["attempts"][0]["codex_argv"]
    rendered = "\n".join(argv)
    assert "mcp_servers.aoa_evals=" in rendered
    assert "AOA_EVALS_MCP_READ_BEARER_TOKEN" in rendered
    assert "aoa_stats" not in rendered
    assert "aoa_memo" not in rendered
    assert "eval-token" not in rendered


def test_runtime_tool_profile_ids_are_model_neutral() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_ids = [item["profile_id"] for item in profile["tool_profiles"]]
    assert all("luna" not in item and "sol" not in item for item in profile_ids)


def test_run_to_terminal_keeps_caller_until_terminal_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]

    terminal = runtime.run_to_terminal(fixture["launch_path"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert terminal["worker_pid"] is None
    assert result is not None
    assert result["status"] == "completed"
    assert result["attempt_count"] == 1


def test_reviewer_preparation_forwards_exact_writer_evidence_without_starting(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "writer", role_id="reviewer", exact_baseline=True
    )
    writer_runtime = fixture["runtime"]
    writer_runtime.start(fixture["launch_path"])
    assert _wait_terminal(writer_runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = (
        writer_runtime._session_dir(fixture["session_id"]) / "result.json"
    )
    output_root = tmp_path / "review-preparation"
    reviewer_state_root = tmp_path / "reviewer-state"

    response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(output_root),
            state_root=str(reviewer_state_root),
            aoa_sdk_root=str(SDK_ROOT),
            review_instance_id="initial",
        )
    )

    preparation = json.loads(
        Path(response["preparation_path"]).read_text(encoding="utf-8")
    )
    launch = json.loads(
        Path(preparation["launch_path"]).read_text(encoding="utf-8")
    )
    task = json.loads(Path(launch["task"]["path"]).read_text(encoding="utf-8"))
    binding = json.loads(
        Path(launch["incarnation_binding"]["path"]).read_text(encoding="utf-8")
    )

    assert response["prepared"] is True
    assert response["started"] is False
    assert preparation["writer_session_id"] == fixture["session_id"]
    assert preparation["review_instance_id"] == "initial"
    assert preparation["reviewer_session_id"] != fixture["session_id"]
    assert preparation["usage_metering"]["mode"] == "observe_only"
    assert preparation["usage_metering"]["execution_limit_policy"] == "none"
    assert preparation["writer_runtime_state_path"] == str(
        writer_result_path.parent / "state.json"
    )
    assert preparation["writer_runtime_state_digest"] == _digest_path(
        writer_result_path.parent / "state.json"
    )
    assert preparation["aoa_sdk_import_provenance"]["capture_point"] == (
        "after_reviewer_plan_and_binding_compilation"
    )
    assert set(preparation["forwarded_input_ids"]) == {
        "fixture-readme",
        "workspace-manifest",
        "summon-request",
        "summon-request-schema",
        "writer-runtime-result",
        "writer-model-report",
        "review-workspace-manifest",
    }
    assert task["task_family"] == "landing_review"
    assert task["review_required"] is False
    assert task["transition"]["review_required_status"] == (
        "review_required_source_repair"
    )
    assert task["parent_task_id"] == fixture["task_id"]
    assert {
        item["input_id"] for item in task["immutable_inputs"]
    }.issuperset({"summon-request", "summon-request-schema", "review-summon-request"})
    assert preparation["review_summon_request_digest"] == _digest_path(
        Path(preparation["review_summon_request_path"])
    )
    assert binding["role_id"] == "reviewer"
    assert launch["workspace_manifest_input_id"] == "review-workspace-manifest"
    assert preparation["writer_effect_class"] == "read_only"
    assert preparation["review_workspace_manifest_digest"] == _digest_path(
        Path(preparation["review_workspace_manifest_path"])
    )
    assert binding["usage_metering"]["execution_limit_policy"] == "none"
    assert not reviewer_state_root.exists()

    reviewer_runtime = RUNTIME.ExternalCodexRuntime(reviewer_state_root)
    assert reviewer_runtime.preflight(Path(preparation["launch_path"]))["admitted"] is True

    retry_response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(tmp_path / "review-preparation-retry"),
            state_root=str(tmp_path / "reviewer-state-retry"),
            aoa_sdk_root=str(SDK_ROOT),
            review_instance_id="effect-observer-repair-1",
        )
    )
    retry_preparation = json.loads(
        Path(retry_response["preparation_path"]).read_text(encoding="utf-8")
    )
    assert retry_preparation["review_instance_id"] == "effect-observer-repair-1"
    assert retry_preparation["reviewer_session_id"] != preparation["reviewer_session_id"]
    assert retry_preparation["reviewer_incarnation_id"] != preparation[
        "reviewer_incarnation_id"
    ]

    reviewer_runtime.start(Path(preparation["launch_path"]))
    assert _wait_terminal(
        reviewer_runtime, preparation["reviewer_session_id"]
    )["status"] == "completed"
    summon_path = fixture["summon_request_path"]
    exported = writer_runtime.export_a2a_result(
        fixture["session_id"],
        reviewer_session_id=preparation["reviewer_session_id"],
        reviewer_state_root=reviewer_state_root,
        summon_request_path=summon_path,
        output_path=tmp_path / "cross-state-child-task-result.json",
    )
    assert exported["child_task_result"]["review_outcome"] == "proceed"


def test_repo_mutation_writer_enters_explicit_read_only_review_and_a2a_return(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "writer",
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
        prepare_mutation_reviewer_sources=True,
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == (
        "review_required"
    )
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    writer_result = runtime.result(fixture["session_id"])
    assert writer_result is not None
    writer_report = json.loads(
        Path(str(writer_result["report_ref"]["artifact_ref"])).read_text(
            encoding="utf-8"
        )
    )
    assert writer_report["decision"] == "submit_for_review"
    assert writer_result["workspace_manifest_match"] is False
    assert writer_result["changed_paths"] == [
        {"path": "landing-note.md", "status": "??"}
    ]
    assert writer_result["workspace_manifest_ref"]["artifact_digest"] == (
        _digest_path(Path(writer_result["workspace_manifest_ref"]["artifact_ref"]))
    )

    response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(tmp_path / "review-preparation"),
            state_root=str(runtime.state_root),
            aoa_sdk_root=str(SDK_ROOT),
            reviewer_role_contract=str(fixture["reviewer_role_path"]),
            reviewer_model_realization=str(
                fixture["reviewer_realization_path"]
            ),
        )
    )
    preparation = json.loads(
        Path(response["preparation_path"]).read_text(encoding="utf-8")
    )
    reviewer_launch_path = Path(preparation["launch_path"])
    reviewer_launch = json.loads(reviewer_launch_path.read_text(encoding="utf-8"))
    reviewer_binding = json.loads(
        Path(reviewer_launch["incarnation_binding"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    reviewer_task = json.loads(
        Path(reviewer_launch["task"]["path"]).read_text(encoding="utf-8")
    )
    assert preparation["writer_effect_class"] == "repo_mutation"
    assert reviewer_launch["workspace_manifest_input_id"] == (
        "review-workspace-manifest"
    )
    assert reviewer_launch["model_realization"]["path"] == str(
        fixture["reviewer_realization_path"]
    )
    assert reviewer_binding["role_id"] == "reviewer"
    assert reviewer_binding["permission_posture"]["sandbox_mode"] == "read_only"
    assert reviewer_binding["permission_posture"]["allowed_effect_classes"] == [
        "read_only"
    ]
    assert reviewer_task["source_evidence_paths"] == ["README.md"]

    reviewer_runtime = RUNTIME.ExternalCodexRuntime(runtime.state_root)
    assert reviewer_runtime.preflight(reviewer_launch_path)["admitted"] is True
    reviewer_runtime.start(reviewer_launch_path)
    reviewer_session_id = preparation["reviewer_session_id"]
    assert _wait_terminal(reviewer_runtime, reviewer_session_id)["status"] == (
        "completed"
    )
    reviewer_result = reviewer_runtime.result(reviewer_session_id)
    assert reviewer_result is not None
    assert reviewer_result["workspace_manifest_match"] is True
    summon_path = fixture["summon_request_path"]
    exported = runtime.export_a2a_result(
        fixture["session_id"],
        reviewer_session_id=reviewer_session_id,
        summon_request_path=summon_path,
        output_path=tmp_path / "child-task-result.json",
    )
    assert exported["child_task_result"]["review_outcome"] == "proceed"


def test_reviewer_preparation_requires_canonical_durable_writer_result(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "writer", exact_baseline=True)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    copied_result_path = tmp_path / "detached-writer-result.json"
    copied_result_path.write_bytes(writer_result_path.read_bytes())

    with pytest.raises(PREPARER.StudyPreparationError, match="durable runtime state"):
        PREPARER._prepare_reviewer(
            argparse.Namespace(
                writer_launch=str(fixture["launch_path"]),
                writer_result=str(copied_result_path),
                output_root=str(tmp_path / "review-preparation"),
                state_root=str(tmp_path / "reviewer-state"),
                aoa_sdk_root=str(SDK_ROOT),
            )
        )


def test_reviewer_preparation_rejects_non_fixture_writer_admission(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "writer", exact_baseline=True)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    launch = json.loads(fixture["launch_path"].read_text(encoding="utf-8"))
    launch["admission_class"] = "owner_contour"
    _write_json(fixture["launch_path"], launch)

    with pytest.raises(PREPARER.StudyPreparationError, match="transport_study_fixture"):
        PREPARER._prepare_reviewer(
            argparse.Namespace(
                writer_launch=str(fixture["launch_path"]),
                writer_result=str(writer_result_path),
                output_root=str(tmp_path / "review-preparation"),
                state_root=str(tmp_path / "reviewer-state"),
                aoa_sdk_root=str(SDK_ROOT),
            )
        )


def test_owner_contour_requires_separate_semantic_admission(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    launch = json.loads(fixture["launch_path"].read_text(encoding="utf-8"))
    launch["admission_class"] = "owner_contour"
    _write_json(fixture["launch_path"], launch)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(fixture["launch_path"])

    assert exc_info.value.code == "owner_contour_admission_unbound"


@pytest.mark.skipif(
    not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
    or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file(),
    reason="paired owner-contour proof requires aoa-agents and aoa-skills source roots",
)
def test_neutral_binder_reproduces_exact_owner_contour_launch(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "fixture", owner_contour=True)
    launch = fixture["launch"]
    manifest = {
        "schema_version": "abyss_stack_external_actor_launch_manifest_v1",
        "launch_id": launch["launch_id"],
        "session_id": launch["session_id"],
        "artifacts": {
            key: launch[key]["path"]
            for key in BINDER.COORDINATE_KEYS
        },
        "owner_contract_paths": {
            "owner_execution_request_schema": launch[
                "owner_execution_request_schema"
            ]["path"],
            "task_local_dag_schema": launch["task_local_dag_schema"]["path"],
        },
        "workspace_path": launch["workspace_path"],
        "workspace_initial_posture": launch["workspace_initial_posture"],
        "workspace_manifest_input_id": launch["workspace_manifest_input_id"],
        "codex_executable": launch["codex_executable"],
        "codex_home": launch["codex_home"],
        "environment_allowlist": launch["environment_allowlist"],
    }
    manifest_path = tmp_path / "launch-manifest.json"
    output_path = tmp_path / "bound-launch.json"
    _write_json(manifest_path, manifest)

    response = BINDER.bind(manifest_path, output_path)

    assert response["bound"] is True
    assert response["started"] is False
    assert response["next_route"] == (
        "aoa-agents:aoa-summon/form-owner-execution-request"
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == launch
    assert response["launch_ref"]["digest"] == _digest_path(output_path)


def test_neutral_binder_uses_exact_git_outside_ambient_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("bounded\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    expected = _git(workspace, "rev-parse", "HEAD")
    malicious_bin = tmp_path / "bin"
    malicious_bin.mkdir()
    marker = tmp_path / "replacement-git-ran"
    replacement = malicious_bin / "git"
    replacement.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        "/usr/bin/printf '0000000000000000000000000000000000000000\\n'\n",
        encoding="utf-8",
    )
    replacement.chmod(0o700)
    monkeypatch.setenv("PATH", f"{malicious_bin}:/usr/bin:/bin")

    assert BINDER._git_head(workspace) == expected
    assert marker.exists() is False


@pytest.mark.skipif(
    not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
    or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file(),
    reason="paired owner-contour proof requires aoa-agents and aoa-skills source roots",
)
def test_owner_contour_admits_exact_role_first_request_and_runs_separate_process(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, owner_contour=True)
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None

    preflight = fixture["runtime"].preflight(
        fixture["launch_path"],
        owner_request_path=owner_request_path,
    )
    assert preflight["admitted"] is True
    assert preflight["admission_class"] == "owner_contour"
    assert preflight["owner_admission_digest"] == _digest_path(owner_request_path)

    started = fixture["runtime"].start(
        fixture["launch_path"],
        owner_request_path=owner_request_path,
    )
    terminal = _wait_terminal(fixture["runtime"], started["session_id"])
    assert terminal["status"] == "completed"
    result = fixture["runtime"].result(started["session_id"])
    assert result["admission_class"] == "owner_contour"
    assert result["owner_admission_ref"]["artifact_digest"] == _digest_path(
        owner_request_path
    )
    assert result["usage"]["input_tokens"] == 120


@pytest.mark.skipif(
    not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
    or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file(),
    reason="paired owner-contour proof requires aoa-agents and aoa-skills source roots",
)
def test_owner_contour_rejects_request_that_changes_responsibility_holders(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, owner_contour=True)
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None
    request = json.loads(owner_request_path.read_text(encoding="utf-8"))
    request["external_incarnation"]["responsibility_transfer_ref"]["holder_ids"] = [
        "actor://fixture-goal-owner",
        "actor://different-holder",
    ]
    _write_json(owner_request_path, request)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(
            fixture["launch_path"],
            owner_request_path=owner_request_path,
        )

    assert exc_info.value.code == "responsibility_transfer_content_mismatch"


@pytest.mark.skipif(
    not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
    or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file(),
    reason="paired owner-contour proof requires aoa-agents and aoa-skills source roots",
)
def test_owner_contour_rejects_internally_inconsistent_transfer(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        owner_contour=True,
        responsibility_transfer_mutator=lambda value: value.update(
            {"obligation_ref": "obligation:unrelated"}
        ),
    )
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(
            fixture["launch_path"],
            owner_request_path=owner_request_path,
        )

    assert exc_info.value.code == "responsibility_transfer_content_mismatch"


def test_durable_state_requires_exact_workspace_manifest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    state = json.loads(
        runtime._state_path(fixture["session_id"]).read_text(encoding="utf-8")
    )
    del state["workspace_manifest_baseline"]

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.validate_json(
            state,
            RUNTIME.STATE_SCHEMA_PATH,
            label="fixture state without workspace manifest",
        )

    assert exc_info.value.code == "schema_validation_failed"


def test_main_runtime_recovers_event_append_before_state_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    monkeypatch.setattr(runtime, "_spawn_worker", lambda *args, **kwargs: None)
    prepared = runtime.start(fixture["launch_path"])
    assert prepared["status"] == "prepared"
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        old_digest = state["events_digest"]
        runtime._append_event(
            state,
            event_type="external_agent.recovery_fixture",
            payload={"cause": "crash-before-state-save"},
            significance="trace",
        )

    recovered = runtime.status(fixture["session_id"])
    durable_state = runtime._load_state(fixture["session_id"])
    events = runtime.events(fixture["session_id"], after_sequence=-1)

    assert recovered["status"] == "prepared"
    assert durable_state["events_digest"] != old_digest
    assert durable_state["last_event_sequence"] == len(events) - 1
    assert [event["sequence"] for event in events] == list(range(len(events)))


def test_prepared_session_retries_launch_after_spawn_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    calls = 0

    def fail_once_then_hold(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("fixture fork failure")

    monkeypatch.setattr(runtime, "_spawn_worker", fail_once_then_hold)
    with pytest.raises(OSError, match="fixture fork failure"):
        runtime.start(fixture["launch_path"])

    persisted = runtime._load_state(fixture["session_id"])
    assert persisted["status"] == "prepared"
    assert persisted["attempts"] == []

    retried = runtime.start(fixture["launch_path"])
    assert retried["status"] == "prepared"
    assert calls == 2


def test_active_attempt_exclusively_holds_its_exact_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "shared-workspace"
    first = _fixture(
        tmp_path / "first",
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
        identity_suffix="workspace-holder-one",
        state_root=tmp_path / "first-state",
        shared_workspace=workspace,
    )
    second = _fixture(
        tmp_path / "second",
        identity_suffix="workspace-holder-two",
        state_root=tmp_path / "second-state",
        shared_workspace=workspace,
    )
    runtime = first["runtime"]
    running = runtime.start(first["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        running = runtime.status(first["session_id"])
        if running["codex_pid"]:
            break
        time.sleep(0.05)
    assert running["codex_pid"]

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        second["runtime"].start(second["launch_path"])
    assert exc_info.value.code == "workspace_active_attempt_conflict"

    interrupted = runtime.interrupt(first["session_id"])
    assert interrupted["status"] == "interrupted"
    terminal = second["runtime"].run_to_terminal(second["launch_path"])
    assert terminal["status"] == "completed"


def test_recovered_codex_events_replay_thread_usage_and_command_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    monkeypatch.setattr(runtime, "_spawn_worker", lambda *args, **kwargs: None)
    runtime.start(fixture["launch_path"])
    attempt_id = f"{fixture['session_id']}:attempt:1"
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        state["attempts"].append(
            {
                "attempt_id": attempt_id,
                "attempt_number": 1,
                "mode": "start",
                "status": "starting",
                "worker_pid": None,
                "worker_start_ticks": None,
                "supervisor_pid": None,
                "supervisor_start_ticks": None,
                "process_identity_ref": None,
                "codex_pid": None,
                "codex_start_ticks": None,
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "thread_id": None,
                "codex_argv": None,
                "execution_root": None,
                "output_bytes": 0,
                "active_wall_seconds": 0.0,
                "wall_time_accounted": False,
            }
        )
        state["active_attempt_id"] = attempt_id
        runtime._save_state(state)

    original_save_state = runtime._save_state

    def append_then_lose_state(payload: dict[str, Any]) -> None:
        monkeypatch.setattr(runtime, "_save_state", lambda state: None)
        runtime._record_codex_event(
            fixture["session_id"],
            attempt_id=attempt_id,
            attempt_number=1,
            line=(json.dumps(payload) + "\n").encode("utf-8"),
        )
        monkeypatch.setattr(runtime, "_save_state", original_save_state)
        runtime.status(fixture["session_id"])

    thread_id = "thread:semantic-recovery"
    append_then_lose_state({"type": "thread.started", "thread_id": thread_id})
    append_then_lose_state(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 101,
                "cached_input_tokens": 17,
                "output_tokens": 23,
            },
        }
    )
    command = "/usr/bin/python3 -c 'print(42)'"
    append_then_lose_state(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": command,
                "status": "completed",
                "exit_code": 0,
            },
        }
    )

    recovered = runtime._load_state(fixture["session_id"])
    task = json.loads(fixture["task_path"].read_text(encoding="utf-8"))
    assert recovered["thread_id"] == thread_id
    assert recovered["attempts"][0]["thread_id"] == thread_id
    assert recovered["turn_count"] == 1
    assert recovered["usage"] == {
        "input_tokens": 101,
        "cached_input_tokens": 17,
        "output_tokens": 23,
    }
    assert recovered["executed_commands"] == [
        {
            "attempt_id": attempt_id,
            "command": command,
            "status": "completed",
            "exit_code": 0,
        }
    ]
    assert runtime._forbidden_effects(
        recovered["executed_commands"], task
    ) == ["unclassified_indirect_effect"]
    with runtime._lock(fixture["session_id"]):
        failed_state = runtime._load_state(fixture["session_id"])
        runtime._worker_failure_locked(
            failed_state,
            attempt_id=attempt_id,
            code="unexpected_worker_death",
            message="fixture worker died after the durable command event",
        )
    result = runtime.result(fixture["session_id"])
    assert result is not None
    assert result["status"] == "authority_blocked"
    assert result["failure_code"] == "authority_boundary_crossed"


def test_main_event_recovery_streams_without_aggregate_control_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    monkeypatch.setattr(runtime, "_spawn_worker", lambda *args, **kwargs: None)
    runtime.start(fixture["launch_path"])
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        runtime._append_event(
            state,
            event_type="external_agent.streaming_recovery_fixture",
            payload={"cause": "append-before-state-save"},
            significance="trace",
        )

    events_path = runtime._events_path(fixture["session_id"])
    original_read_bounded = RUNTIME.read_bounded

    def reject_aggregate_event_read(path: Path, *args: Any, **kwargs: Any) -> bytes:
        if Path(path) == events_path:
            raise AssertionError("event history must not use a bounded aggregate read")
        return original_read_bounded(path, *args, **kwargs)

    monkeypatch.setattr(RUNTIME, "read_bounded", reject_aggregate_event_read)

    recovered = runtime.status(fixture["session_id"])
    events = runtime.events(fixture["session_id"], after_sequence=-1)

    assert recovered["status"] == "prepared"
    assert events[-1]["event_type"] == "external_agent.streaming_recovery_fixture"


@pytest.mark.parametrize("mutation", ("missing-type", "unsupported-not"))
def test_output_schema_subset_gate_fails_before_inference(mutation: str) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    if mutation == "missing-type":
        schema["properties"]["schema_version"].pop("type")
    else:
        schema["properties"]["summary"]["not"] = {"const": ""}

    with pytest.raises(
        RUNTIME.ExternalCodexRuntimeError,
        match="output schema",
    ):
        RUNTIME.validate_structured_output_schema(schema)


def test_launch_rejects_bytes_not_named_by_incarnation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    launch = json.loads(fixture["launch_path"].read_text(encoding="utf-8"))
    replacement = tmp_path / "replacement-realization.json"
    payload = json.loads(fixture["realization_path"].read_text(encoding="utf-8"))
    payload["configuration"]["reasoning_effort"] = "xhigh"
    _write_json(replacement, payload)
    launch["model_realization"] = {
        "path": str(replacement),
        "digest": _digest_path(replacement),
    }
    _write_json(fixture["launch_path"], launch)

    with pytest.raises(
        RUNTIME.ExternalCodexRuntimeError,
        match="incarnation model_realization ref differs",
    ):
        fixture["runtime"].preflight(fixture["launch_path"])


def test_exact_baseline_pins_dirty_file_bytes_not_only_status(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, exact_baseline=True)
    runtime = fixture["runtime"]

    assert runtime.preflight(fixture["launch_path"])["admitted"] is True
    (fixture["workspace"] / "dirty-note.txt").write_text(
        "same status, different bytes\n", encoding="utf-8"
    )

    with pytest.raises(
        RUNTIME.ExternalCodexRuntimeError,
        match="workspace bytes differ from the exact immutable baseline manifest",
    ):
        runtime.preflight(fixture["launch_path"])


def test_finalization_detects_same_status_byte_mutation(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        exact_baseline=True,
        objective_marker="FAKE_SAME_STATUS_MUTATION",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["workspace_manifest_match"] is False
    assert result["changed_paths"] == [
        {"path": "dirty-note.txt", "status": "content_changed"}
    ]


def test_allowed_path_rejects_embedded_parent_traversal() -> None:
    assert RUNTIME._relative_path_is_allowed("docs/report.md", ["docs"])
    assert not RUNTIME._relative_path_is_allowed("docs/../outside.md", ["docs"])
    assert not RUNTIME._relative_path_is_allowed("docs\\..\\outside.md", ["docs"])


def test_study_preparer_binds_actual_sdk_import_root(tmp_path: Path) -> None:
    PREPARER._assert_aoa_sdk_import_root(SDK_ROOT)
    coordinates = PREPARER._aoa_sdk_import_coordinates(SDK_ROOT)
    expected_root = (SDK_ROOT / "src" / "aoa_sdk").resolve()

    assert any(item["label"] == "aoa_sdk package" for item in coordinates)
    assert all(
        Path(item["path"]).resolve().is_relative_to(expected_root)
        for item in coordinates
    )
    with pytest.raises(PREPARER.StudyPreparationError, match="outside exact"):
        PREPARER._assert_aoa_sdk_import_root(tmp_path / "different-sdk")


def test_study_preparer_rejects_auxiliary_sdk_module_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthetic = ModuleType("aoa_sdk.synthetic_outside")
    synthetic.__file__ = str(tmp_path / "outside-sdk" / "synthetic.py")
    monkeypatch.setitem(sys.modules, synthetic.__name__, synthetic)

    with pytest.raises(PREPARER.StudyPreparationError, match="outside exact"):
        PREPARER._assert_aoa_sdk_import_root(SDK_ROOT)


def test_study_preparer_materializes_exact_manifest(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "fixture")
    output = tmp_path / "workspace-manifest.json"

    prepared = PREPARER._prepare_manifest(
        argparse.Namespace(workspace=str(fixture["workspace"]), output=str(output))
    )

    assert output.is_file()
    assert prepared["workspace_manifest"] == str(output)
    RUNTIME.assert_workspace_manifest(
        json.loads(output.read_text(encoding="utf-8")),
        fixture["workspace"],
    )


def test_read_only_workspace_drift_is_authority_blocked(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_WRITE_OUT_OF_SCOPE")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None and result["status"] == "authority_blocked"
    assert result["changed_paths"] == [{"path": "unexpected.txt", "status": "??"}]
    assert result["wake_evaluation"]["wake_parent"] is True


def test_special_workspace_entry_is_authority_blocked_at_closeout(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_CREATE_FIFO_OUT_OF_SCOPE")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "workspace_manifest_observation_gap"
    assert result["workspace_manifest_match"] is None


def test_workspace_write_preparation_stays_inside_allowed_paths(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED",
        role_id="coder",
        task_family="landing_preparation",
        identity_suffix="luna-max-preparation",
        workspace_write=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None and result["status"] == "completed"
    assert result["changed_paths"] == [{"path": "landing-note.md", "status": "??"}]
    invocation = result["codex_invocations"][0]
    argv = invocation["argv"]
    assert argv[argv.index("-s") + 1] == "workspace-write"
    assert "sandbox_workspace_write.network_access=false" in argv
    assert invocation["execution_root"] == str(fixture["workspace"])
    assert argv[argv.index("-C") + 1] == str(fixture["workspace"])
    assert "--skip-git-repo-check" not in argv


@pytest.mark.parametrize(
    ("workspace_write", "marker", "failure_code"),
    (
        (
            False,
            "FAKE_ARTIFACT_PREEXISTING",
            "model_report_artifact_forbidden_read_only",
        ),
        (
            True,
            "FAKE_ARTIFACT_PREEXISTING",
            "model_report_artifact_not_produced",
        ),
    ),
)
def test_report_cannot_claim_preexisting_workspace_artifact(
    tmp_path: Path,
    workspace_write: bool,
    marker: str,
    failure_code: str,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=marker,
        workspace_write=workspace_write,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None and result["failure_code"] == failure_code
    failure = json.loads(
        Path(result["report_ref"]["artifact_ref"]).read_text(encoding="utf-8")
    )
    assert failure["failure_code"] == failure_code
    assert isinstance(failure["message"], str) and failure["message"]


def test_workspace_write_report_accepts_actual_produced_artifact(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        identity_suffix="luna-max-produced-artifact",
        workspace_write=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    report = json.loads(Path(result["report_ref"]["artifact_ref"]).read_text())
    assert report["artifact_paths"] == ["landing-note.md"]


def test_source_evidence_scope_is_distinct_from_mutation_scope(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        allowed_paths=("landing-note.md",),
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["changed_paths"] == [{"path": "landing-note.md", "status": "??"}]


def test_runtime_final_workspace_manifest_is_admitted_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED "
            "FAKE_VALID_RUNTIME_FINAL_MANIFEST_EVIDENCE"
        ),
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["workspace_manifest_ref"]["artifact_digest"] == _digest_path(
        Path(result["workspace_manifest_ref"]["artifact_ref"])
    )


@pytest.mark.parametrize(
    ("marker", "failure_code"),
    (
        ("FAKE_INVALID_CLAIMS", "model_report_validation_claims_incomplete"),
        ("FAKE_WAKE_MISMATCH", "model_report_wake_action_mismatch"),
        (
            "FAKE_WAKE_CONDITION_MISMATCH",
            "model_report_wake_condition_mismatch",
        ),
        (
            "FAKE_INVALID_SOURCE_EVIDENCE",
            "model_report_source_evidence_unavailable",
        ),
        (
            "FAKE_INVALID_SOURCE_LINE",
            "model_report_source_evidence_anchor_invalid",
        ),
        (
            "FAKE_OUT_OF_SCOPE_SOURCE_EVIDENCE",
            "model_report_source_evidence_out_of_scope",
        ),
        (
            "FAKE_MISSING_IMMUTABLE_EVIDENCE",
            "model_report_immutable_evidence_unavailable",
        ),
        (
            "FAKE_INVALID_IMMUTABLE_LINE",
            "model_report_immutable_evidence_anchor_invalid",
        ),
        ("FAKE_ORDINAL_IMMUTABLE_EVIDENCE", "schema_validation_failed"),
        ("FAKE_OPAQUE_EVIDENCE", "schema_validation_failed"),
        (
            "FAKE_INVALID_RUNTIME_FINAL_MANIFEST_ANCHOR",
            "model_report_runtime_evidence_anchor_invalid",
        ),
        (
            "FAKE_FALSE_VALIDATION_EVIDENCE",
            "model_report_validation_evidence_unbound",
        ),
        (
            "FAKE_STATUS_DECISION_MISMATCH",
            "model_report_status_decision_mismatch",
        ),
        (
            "FAKE_REVIEW_TRANSITION_MISMATCH",
            "model_report_transition_mismatch",
        ),
    ),
)
def test_report_semantics_fail_closed(
    tmp_path: Path,
    marker: str,
    failure_code: str,
) -> None:
    fixture = _fixture(tmp_path, objective_marker=marker)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None and result["failure_code"] == failure_code


def test_stable_immutable_input_evidence_is_admitted(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_VALID_IMMUTABLE_EVIDENCE",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None and result["failure_code"] is None


def test_exact_duplicate_evidence_refs_are_idempotent_and_preserved(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_DUPLICATE_EVIDENCE_REFS",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None and result["failure_code"] is None
    report = json.loads(
        Path(result["report_ref"]["artifact_ref"]).read_text(encoding="utf-8")
    )
    assert report["transition"]["evidence_refs"] == [
        "source:README.md#L1",
        "source:README.md#L1",
    ]
    assert report["findings"][0]["evidence_refs"] == [
        "source:README.md#L1",
        "source:README.md#L1",
    ]


def test_required_review_cannot_return_completed(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_BYPASS_REVIEW",
        review_required=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "model_report_review_gate_bypassed"


def test_validation_claim_must_match_observed_exact_command(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_FALSE_VALIDATION_CLAIM")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "model_report_validation_claim_unbound"


def test_fixed_validation_requires_explicit_workspace_cwd_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_UNBOUND_VALIDATION_CWD",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "model_report_validation_not_executed"
    validation_events = [
        event
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
        if event["event_type"] == "external_agent.report_validated"
    ]
    assert validation_events[-1]["payload"]["detected_forbidden_effects"] == [
        "unclassified_indirect_effect"
    ]


def test_fixed_validation_receipt_records_exact_argv_and_cwd(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    result = runtime.result(fixture["session_id"])

    assert result is not None
    execution = next(
        item
        for item in result["executed_commands"]
        if item.get("validation_command_id") == "git-status"
    )
    assert execution["validation_argv"] == ["git", "status", "--short"]
    assert execution["validation_cwd"] == str(fixture["workspace"])
    assert execution["validation_wrapper_argv"] == [
        "/usr/bin/env",
        "-C",
        str(fixture["workspace"]),
        "--",
        "git",
        "status",
        "--short",
    ]


@pytest.mark.parametrize(
    ("command", "effect"),
    (
        (
            "/usr/bin/zsh -lc '/usr/bin/git -C /tmp/repo -c user.name=test commit -m bounded'",
            "commit",
        ),
        (
            "/usr/bin/zsh -lc '/usr/bin/env -C /tmp/repo -- /usr/bin/git commit -m bounded'",
            "commit",
        ),
        (
            "/usr/bin/zsh -lc '/usr/bin/gh --repo owner/repo pr create --title test'",
            "pull_request",
        ),
        ("/usr/bin/systemctl --user restart fixture.service", "service_mutation"),
        ("/usr/bin/cat /run/secrets/provider-token", "secret_access"),
        ("/usr/bin/git config --global user.name fixture", "global_config_mutation"),
        (
            "/usr/bin/sed -i.bak 's/old/new/' /etc/fixture.conf",
            "global_config_mutation",
        ),
        ("/usr/bin/curl -X POST https://example.invalid/upload", "publication"),
    ),
)
def test_forbidden_effect_observer_handles_wrappers_and_effect_families(
    command: str,
    effect: str,
) -> None:
    assert effect in RUNTIME._command_effects(command)


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git status --short",
        "/usr/bin/env PYTHONDONTWRITEBYTECODE=1 /usr/bin/python -m pytest -q",
        "/usr/bin/rg -n secret_access mechanics/runtime.py",
        (
            "/usr/bin/zsh -lc \"/usr/bin/nl -ba docs/ONE.md | "
            "/usr/bin/sed -n '1,5p'; /usr/bin/nl -ba docs/TWO.md | "
            "/usr/bin/sed -n '6,10p'\""
        ),
    ),
)
def test_effect_observer_does_not_block_fixed_read_commands(command: str) -> None:
    assert RUNTIME._command_effects(command) == set()


def test_indirect_interpreter_effect_is_unclassified_but_fixed_validation_is_admitted() -> None:
    command = "/usr/bin/python3 -c 'print(42)'"
    assert RUNTIME._command_has_unclassified_indirection(command) is True
    assert RUNTIME._command_has_unclassified_indirection(
        "/usr/bin/zsh -lc '/usr/bin/rg -n fixture README.md'"
    ) is False


def test_attached_shell_separator_does_not_hide_forbidden_effect() -> None:
    command = "/usr/bin/bash -lc '/usr/bin/git push; /usr/bin/true'"
    assert "push" in RUNTIME._command_effects(command)


def test_env_split_string_is_opaque_and_cannot_hide_secret_access() -> None:
    command = "/usr/bin/env -S 'cat /home/fixture/.ssh/id_rsa'"
    assert RUNTIME._command_has_unclassified_indirection(command) is True
    assert "secret_access" in RUNTIME._command_effects(command)


def test_attached_redirection_cannot_hide_git_commit() -> None:
    command = "/usr/bin/bash -lc 'git commit>/tmp/log -am bounded'"
    assert "commit" in RUNTIME._command_effects(command)
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/timeout -s TERM 30 /usr/bin/git push",
        "/usr/bin/timeout --signal=TERM 30 /usr/bin/git push",
        "/usr/bin/timeout -k 5 30 /usr/bin/git push",
        "/usr/bin/timeout --kill-after 5 30 /usr/bin/git push",
    ),
)
def test_timeout_value_options_cannot_hide_git_push(command: str) -> None:
    assert "push" in RUNTIME._command_effects(command)


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/nice /usr/bin/cat /home/fixture/.ssh/id_rsa",
        "/usr/bin/nohup /usr/bin/git push",
        "/usr/bin/setsid /usr/bin/systemctl restart fixture.service",
        "/usr/bin/stdbuf -oL /usr/bin/git commit -m bounded",
    ),
)
def test_process_launch_wrappers_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/rg --pre=/bin/sh pattern scripts/helper.sh",
        "/usr/bin/rg --pre /bin/sh pattern scripts/helper.sh",
        "/usr/bin/rg --hostname-bin=/tmp/helper --hyperlink-format=default pattern .",
        "/usr/bin/rg --search-zip pattern archive.gz",
        "/usr/bin/rg -zH pattern archive.gz",
    ),
)
def test_ripgrep_helper_process_dispatch_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/rg -n pattern .",
        "/usr/bin/rg --no-pre --no-search-zip pattern .",
        "/usr/bin/rg --pre= pattern .",
        "/usr/bin/rg -- --pre",
    ),
)
def test_ordinary_ripgrep_search_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/sort -S 4K --compress-program=/tmp/helper input",
        "/usr/bin/sort --compress-program /tmp/helper input",
        "/usr/bin/sort --compress-program= input",
        "/usr/bin/sort --comp=/tmp/helper input",
        "/usr/bin/sort --co /tmp/helper input",
    ),
)
def test_sort_compression_program_dispatch_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_ordinary_sort_remains_classifiable() -> None:
    assert RUNTIME._command_has_unclassified_indirection(
        "/usr/bin/sort -u input"
    ) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git update-ref refs/heads/hidden HEAD",
        "/usr/bin/git update-ref -d refs/heads/hidden",
        "/usr/bin/git update-ref --stdin",
    ),
)
def test_git_update_ref_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_git_show_ref_remains_classifiable() -> None:
    assert RUNTIME._command_has_unclassified_indirection(
        "/usr/bin/git show-ref --heads"
    ) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git symbolic-ref HEAD refs/heads/other",
        "/usr/bin/git symbolic-ref -m bounded HEAD refs/heads/other",
        "/usr/bin/git symbolic-ref -d refs/heads/hidden",
        "/usr/bin/git symbolic-ref --del refs/heads/hidden",
        "/usr/bin/git reflog expire --expire=now --all",
        "/usr/bin/git reflog delete HEAD@{0}",
        "/usr/bin/git reflog drop --all",
        "/usr/bin/git branch hidden",
        "/usr/bin/git bisect start",
        "/usr/bin/git mktree",
        "/usr/bin/git merge-tree HEAD HEAD",
        "/usr/bin/git write-tree",
        "/usr/bin/git hash-object -w README.md",
        "/usr/bin/git hash-object --literally -w README.md",
        "/usr/bin/git hash-object -wt blob README.md",
        "/usr/bin/git fsck --lost-found",
        "/usr/bin/git fsck --lost-f",
    ),
)
def test_git_hidden_metadata_mutations_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git symbolic-ref HEAD",
        "/usr/bin/git symbolic-ref --short HEAD",
        "/usr/bin/git reflog",
        "/usr/bin/git reflog show HEAD",
        "/usr/bin/git reflog exists refs/heads/main",
        "/usr/bin/git reflog list",
        "/usr/bin/git hash-object --no-filters README.md",
        "/usr/bin/git fsck --no-reflogs",
    ),
)
def test_git_metadata_inspection_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_shell_nesting_beyond_inspection_limit_is_fail_closed() -> None:
    command = "/usr/bin/git push"
    for _ in range(RUNTIME.SHELL_NESTING_INSPECTION_LIMIT):
        command = RUNTIME.shlex.join(["/usr/bin/bash", "-lc", command])

    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert len(tokenizations) == RUNTIME.SHELL_NESTING_INSPECTION_LIMIT
    assert incomplete is True
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash -lc 'echo $(cat /home/operator/.ssh/id_rsa)'",
        "/usr/bin/bash -lc 'echo `cat /home/operator/.ssh/id_rsa`'",
        "/usr/bin/bash -lc 'cat <(printf secret)'",
    ),
)
def test_shell_command_substitution_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/make -f /tmp/leak.mk leak",
        "/usr/bin/npm run leak",
        "/usr/bin/cargo build",
    ),
)
def test_build_and_task_runners_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash -lc 'source scripts/helper.sh'",
        "/usr/bin/bash -lc '. scripts/helper.sh'",
    ),
)
def test_sourced_shell_bodies_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash scripts/helper.sh -c '/usr/bin/true'",
        "/usr/bin/bash scripts/helper.sh -lc '/usr/bin/true'",
        "/usr/bin/bash -- scripts/helper.sh -c '/usr/bin/true'",
        "/usr/bin/bash -O extglob scripts/helper.sh -c '/usr/bin/true'",
    ),
)
def test_shell_c_after_script_operand_is_fail_closed(command: str) -> None:
    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert tokenizations == (tuple(shlex.split(command)),)
    assert incomplete is False
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_shell_c_in_option_position_remains_classifiable() -> None:
    command = "/usr/bin/bash -O extglob -lc '/usr/bin/true'"

    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert tokenizations[-1] == ("/usr/bin/true",)
    assert incomplete is False
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash --rcfile -x -ic '/usr/bin/true'",
        "/usr/bin/bash --rcfile=/tmp/helper -ic '/usr/bin/true'",
        "/usr/bin/bash --rcf=/tmp/helper -ic '/usr/bin/true'",
        "/usr/bin/bash --init-file /tmp/helper -ic '/usr/bin/true'",
        "/usr/bin/bash --init-file=/tmp/helper -ic '/usr/bin/true'",
        "/usr/bin/bash --init-f=/tmp/helper -ic '/usr/bin/true'",
    ),
)
def test_shell_startup_file_options_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "./scripts/helper",
        "scripts/helper",
        "/home/operator/workspace/scripts/helper",
        "/tmp/generated-helper",
        "/usr/bin/../local/bin/helper",
    ),
)
def test_direct_non_system_executables_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash -lc 'git${IFS}push'",
        "/usr/bin/bash -lc 'git p*'",
        "/usr/bin/bash -lc 'g{it,rep} push'",
        "/usr/bin/bash -lc '~/bin/helper'",
        "/usr/bin/bash -O extglob -lc 'g@(it) push'",
        "/usr/bin/bash -lc 'true\ngit push'",
    ),
)
def test_active_shell_expansions_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/rg '$schema' README.md",
        r"/usr/bin/printf '%s\\n' \$HOME",
        "/usr/bin/printf '%s\\n' '{static,braces}'",
    ),
)
def test_quoted_or_escaped_shell_literals_remain_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "helper --emit-secret",
        "/usr/bin/helper --emit-secret",
        "/usr/bin/awk 'BEGIN { system(\"git push\") }'",
        "awk 'BEGIN { system(\"git push\") }'",
    ),
)
def test_unadmitted_bare_names_and_awk_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/tmp/bash -lc '/usr/bin/true'",
        "./bash -lc '/usr/bin/true'",
        "/usr/bin/sed -nf scripts/leak.sed README.md",
        "/usr/bin/sed -n '1e git push' README.md",
        "/usr/bin/git diff --check",
        "/usr/bin/git status --short",
        "/usr/bin/git checkout HEAD -- README.md",
        "/usr/bin/git add README.md",
        "/usr/bin/git cat-file --filters HEAD:README.md",
        "/usr/bin/git cat-file --filter HEAD:README.md",
        "/usr/bin/git cat-file --textc HEAD:README.md",
        "/usr/bin/git grep --textconv bounded",
        "/usr/bin/git hash-object --path=README.md README.md",
        "/usr/bin/git hash-object --pa=README.md README.md",
        "/usr/bin/git hash-object README.md",
        "/usr/bin/git hash-object --filters README.md",
        "/usr/bin/git hash-object --no-filters --filters README.md",
        "/usr/bin/git hash-object --no-filters --f README.md",
        "/usr/bin/git hash-object -- README.md --no-filters",
        "/usr/bin/git for-each-ref '--format=%(signature:grade)'",
        "/usr/bin/git for-each-ref --format '%(signature:signer)'",
        "/usr/bin/git for-each-ref '--f=%(signature:key)'",
        "/usr/bin/git for-each-ref '--fo=%(signature:fingerprint)'",
        "/usr/bin/git for-each-ref '--format=%(*signature:grade)'",
        "/usr/bin/git for-each-ref --sort=signature:grade",
        "/usr/bin/git for-each-ref --sort -signature:grade",
        "/usr/bin/git for-each-ref --sort '*signature:grade'",
        "/usr/bin/git for-each-ref --sort=version:signature:grade",
        "/usr/bin/git for-each-ref --sort=v:signature:signer",
        "/usr/bin/git for-each-ref --sort=-version:*signature:key",
        "/usr/bin/git for-each-ref --so signature:signer",
    ),
)
def test_startup_and_config_driven_dispatch_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "git rev-parse HEAD",
        "grep pattern README.md",
        "/usr/bin/sed --sandbox -n '1,5p' README.md",
    ),
)
def test_allowlisted_system_commands_remain_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_ordinary_git_cat_file_remains_classifiable() -> None:
    assert RUNTIME._command_has_unclassified_indirection(
        "/usr/bin/git cat-file -p HEAD:README.md"
    ) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git for-each-ref",
        "/usr/bin/git for-each-ref '--format=%(refname)'",
        "/usr/bin/git hash-object --no-filters README.md",
        "/usr/bin/git hash-object --no-filters -- README.md",
    ),
)
def test_non_dispatching_git_ref_and_hash_reads_remain_classifiable(
    command: str,
) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/jq -n env",
        "/usr/bin/jq -n 'env.MCP_TOKEN'",
        "/usr/bin/jq -n '$ENV'",
        "/usr/bin/jq --from-file helper.jq input.json",
        "/usr/bin/jq -Lmodules 'import \"helper\" as h; h::run' input.json",
        "/usr/bin/jq --run-tests tests.jq",
    ),
)
def test_jq_environment_and_external_program_sources_are_fail_closed(
    command: str,
) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_jq_environment_read_is_secret_access() -> None:
    assert RUNTIME._command_effects("/usr/bin/jq -n env") == {"secret_access"}


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/jq -n '{}'",
        "/usr/bin/jq -r '.env' input.json",
        "/usr/bin/jq -n '{\"env\": 1}'",
        "/usr/bin/jq --arg name env -n '$name'",
    ),
)
def test_ordinary_jq_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_allowlisted_but_unavailable_system_command_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RUNTIME.shutil, "which", lambda *_args, **_kwargs: None)

    assert RUNTIME._command_has_unclassified_indirection("rg pattern README.md") is True


def test_codex_environment_isolates_shell_startup_and_repository_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambient_home = tmp_path / "ambient-home"
    ambient_home.mkdir()
    marker = tmp_path / "ambient-profile-ran"
    (ambient_home / ".bash_profile").write_text(
        f"touch {shlex.quote(str(marker))}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(ambient_home))
    monkeypatch.setenv("PATH", f"{ambient_home / 'bin'}:/usr/bin:/bin")
    ripgrep_config = tmp_path / "ambient-ripgrep-config"
    ripgrep_config.write_text("--pre=/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(ripgrep_config))
    scratch = tmp_path / "attempt" / "scratch"
    scratch.parent.mkdir()
    scratch.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    (workspace / "README.md").write_text("bounded\n", encoding="utf-8")
    (workspace / ".gitattributes").write_text(
        "README.md filter=leak\n",
        encoding="utf-8",
    )
    _git(workspace, "add", "README.md", ".gitattributes")
    _git(
        workspace,
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "fixture",
    )
    hook_marker = tmp_path / "post-checkout-ran"
    post_checkout = workspace / ".git" / "hooks" / "post-checkout"
    post_checkout.write_text(
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(hook_marker))}\n",
        encoding="utf-8",
    )
    post_checkout.chmod(0o700)
    filter_marker = tmp_path / "smudge-filter-ran"
    filter_helper = tmp_path / "smudge-filter"
    filter_helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(filter_marker))}\n"
        "/bin/cat\n",
        encoding="utf-8",
    )
    filter_helper.chmod(0o700)
    _git(workspace, "config", "filter.leak.smudge", str(filter_helper))

    environment = RUNTIME.ExternalCodexRuntime._codex_environment(
        None,
        {
            "environment_allowlist": ["HOME", "PATH"],
            "codex_home": str(tmp_path / "codex-home"),
            "workspace_path": str(workspace),
        },
        scratch,
        {"mcp_server_configs": []},
    )
    completed = subprocess.run(
        ["/usr/bin/bash", "-lc", "/usr/bin/true"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    checkout = subprocess.run(
        ["/usr/bin/git", "checkout", "HEAD", "--", "README.md"],
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    ripgrep_marker = tmp_path / "ripgrep-preprocessor-ran"
    ripgrep_input = workspace / "ripgrep-input.sh"
    ripgrep_input.write_text(
        f"/usr/bin/touch {shlex.quote(str(ripgrep_marker))}\n"
        "/usr/bin/printf 'bounded\\n'\n",
        encoding="utf-8",
    )
    ripgrep = subprocess.run(
        ["/usr/bin/rg", "bounded", str(ripgrep_input)],
        cwd=workspace,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert environment["HOME"] != str(ambient_home)
    assert environment["PATH"] == RUNTIME.CODEX_EXECUTABLE_PATH
    assert environment["BASH_ENV"] == "/dev/null"
    assert environment["ENV"] == "/dev/null"
    assert environment["RIPGREP_CONFIG_PATH"] == "/dev/null"
    assert environment["GIT_CONFIG_COUNT"] == "4"
    assert environment["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert environment["GIT_CONFIG_KEY_1"] == "core.fsmonitor"
    assert environment["GIT_CONFIG_VALUE_1"] == "false"
    assert environment["GIT_CONFIG_KEY_2"] == "core.attributesFile"
    assert environment["GIT_CONFIG_VALUE_2"] == "/dev/null"
    assert environment["GIT_CONFIG_KEY_3"] == "filter.leak.smudge"
    assert environment["GIT_CONFIG_VALUE_3"] == ""
    assert environment["GIT_NO_LAZY_FETCH"] == "1"
    assert Path(environment["GIT_CONFIG_VALUE_0"]).stat().st_mode & 0o222 == 0
    assert Path(environment["HOME"]).stat().st_mode & 0o222 == 0
    assert marker.exists() is False
    assert checkout.returncode == 0
    assert hook_marker.exists() is False
    assert filter_marker.exists() is False
    assert ripgrep.returncode == 0
    assert ripgrep_marker.exists() is False

    isolated_home = Path(environment["HOME"])
    isolated_home.chmod(0o700)
    (isolated_home / ".bash_profile").write_text("/usr/bin/false\n", encoding="utf-8")
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.ExternalCodexRuntime._codex_environment(
            None,
            {
                "environment_allowlist": ["HOME", "PATH"],
                "codex_home": str(tmp_path / "codex-home"),
                "workspace_path": str(workspace),
            },
            scratch,
            {"mcp_server_configs": []},
        )
    assert exc_info.value.code == "isolated_shell_home_unavailable"


def test_codex_environment_rejects_nonempty_git_hooks_directory(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "attempt" / "scratch"
    scratch.parent.mkdir()
    scratch.mkdir()
    hooks_root = scratch.parent / f"{scratch.name}-git-hooks"
    hooks_root.mkdir()
    (hooks_root / "post-checkout").write_text("#!/bin/false\n", encoding="utf-8")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.ExternalCodexRuntime._codex_environment(
            None,
            {
                "environment_allowlist": [],
                "codex_home": str(tmp_path / "codex-home"),
            },
            scratch,
            {"mcp_server_configs": []},
        )

    assert exc_info.value.code == "isolated_git_hooks_unavailable"


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git -c alias.leak='!cat /home/operator/.ssh/id_rsa' leak",
        "/usr/bin/git -calias.leak='!cat /home/operator/.ssh/id_rsa' leak",
        "/usr/bin/git --config-env=alias.leak=LEAK_COMMAND leak",
        "/usr/bin/git -c core.hooksPath=.git/hooks checkout HEAD -- README.md",
        "/usr/bin/git leak",
        "/usr/bin/git --exec-path=/tmp leak",
        "/usr/bin/git -C/tmp leak",
        "GIT_CONFIG_COUNT=1 /usr/bin/git status",
        "/usr/bin/env GIT_CONFIG_COUNT=1 /usr/bin/git status",
    ),
)
def test_git_config_and_external_dispatch_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git config --local core.hooksPath /tmp/hooks",
        "/usr/bin/git config --worktree core.hooksPath /tmp/hooks",
        "/usr/bin/git config --add core.hooksPath /tmp/hooks",
        "/usr/bin/git config set core.hooksPath /tmp/hooks",
        "/usr/bin/git config --get http.https://example.com/.extraheader",
        "/usr/bin/git config --list",
        "/usr/bin/git config core.hooksPath",
        "/usr/bin/git config --local --get core.hooksPath",
        "/usr/bin/git config get core.hooksPath",
    ),
)
def test_git_repository_config_access_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git remote add leak https://example.invalid/repo.git",
        "/usr/bin/git remote set-url origin https://example.invalid/repo.git",
        "/usr/bin/git remote rename origin upstream",
        "/usr/bin/git remote remove origin",
        "/usr/bin/git remote set-branches origin main",
        "/usr/bin/git remote update origin",
        "/usr/bin/git remote -v",
        "/usr/bin/git remote --verbose",
        "/usr/bin/git remote get-url origin",
    ),
)
def test_git_remote_mutations_and_dispatch_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git remote --help",
        "/usr/bin/git remote -h",
        "/usr/bin/git --help remote",
        "/usr/bin/git status --help",
    ),
)
def test_git_help_dispatch_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git branch --edit-description",
        "/usr/bin/git branch --edit-description=main",
        "/usr/bin/git bisect run scripts/helper",
        "/usr/bin/git verify-commit HEAD",
        "/usr/bin/git verify-tag v1.0.0",
        "/usr/bin/git fetch origin",
        "/usr/bin/git fetch --upload-pack=/tmp/helper /tmp/remote",
        "/usr/bin/git notes edit HEAD",
        "/usr/bin/git grep --open-files-in-pager=/tmp/helper pattern",
        "/usr/bin/git init .",
        "/usr/bin/git init --separate-git-dir=/tmp/repo-meta --template=/tmp/template .",
        "/usr/bin/git ls-remote /tmp/remote",
        "/usr/bin/git ls-remote --upload-pack=/tmp/helper /tmp/remote",
    ),
)
def test_git_editor_runner_and_verifier_dispatch_is_fail_closed(
    command: str,
) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_direct_secret_file_encoder_is_classified() -> None:
    assert RUNTIME._command_effects(
        "/usr/bin/base64 /home/operator/.ssh/id_rsa"
    ) == {"secret_access"}


def test_runtime_forbidden_effects_do_not_trust_a_task_subset() -> None:
    assert RUNTIME.ExternalCodexRuntime._forbidden_effects(
        None,
        [
            {
                "command": "/usr/bin/base64 /home/operator/.ssh/id_rsa",
                "status": "completed",
                "exit_code": 0,
            }
        ],
        {"forbidden_effects": ["commit"]},
    ) == ["secret_access", "unclassified_indirect_effect"]


def test_task_schema_requires_the_complete_runtime_forbidden_set(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    task = json.loads(fixture["task_path"].read_text(encoding="utf-8"))
    task["forbidden_effects"].remove("secret_access")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.validate_json(
            task,
            RUNTIME.TASK_SCHEMA_PATH,
            label="external Codex task",
        )

    assert exc_info.value.code == "schema_validation_failed"


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git --version",
        "/usr/bin/git rev-parse HEAD",
        "/usr/bin/git ls-files",
        "/usr/bin/git show-ref --head",
        "/usr/bin/git remote",
    ),
)
def test_direct_git_builtins_remain_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_started_command_survives_interruption_and_blocks_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_STARTED_FORBIDDEN_COMMAND")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with runtime._lock(fixture["session_id"]):
            state = runtime._load_state(fixture["session_id"])
        if state["executed_commands"]:
            break
        time.sleep(0.05)
    else:
        pytest.fail("started command was not durably observed")

    terminal = runtime.interrupt(fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["status"] == "authority_blocked"
    assert result["executed_commands"][0]["event_phase"] == "started"
    assert "push" in runtime._failure_authority_effects(
        result["executed_commands"]
    )


@pytest.mark.parametrize(
    ("objective_marker", "expected_effects"),
    (
        ("FAKE_OPAQUE_INDIRECT_COMMAND", ["unclassified_indirect_effect"]),
        (
            "FAKE_OPAQUE_LAUNCH_WRAPPER",
            ["secret_access", "unclassified_indirect_effect"],
        ),
        ("FAKE_DEEP_SHELL_NESTING", ["unclassified_indirect_effect"]),
        (
            "FAKE_COMMAND_SUBSTITUTION",
            ["secret_access", "unclassified_indirect_effect"],
        ),
        ("FAKE_OPAQUE_BUILD_RUNNER", ["unclassified_indirect_effect"]),
        (
            "FAKE_GIT_ALIAS_INDIRECTION",
            ["secret_access", "unclassified_indirect_effect"],
        ),
        ("FAKE_SOURCE_INDIRECTION", ["unclassified_indirect_effect"]),
        ("FAKE_SHELL_SCRIPT_BEFORE_C", ["unclassified_indirect_effect"]),
        ("FAKE_SHELL_STARTUP_FILE", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_LOCAL_CONFIG_WRITE", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_CONFIG_READ", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_HIDDEN_PROGRAMS", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_CAT_FILE_FILTER", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_SIGNATURE_FORMAT", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_HASH_OBJECT_FILTER", ["unclassified_indirect_effect"]),
        ("FAKE_RIPGREP_HIDDEN_PROGRAM", ["unclassified_indirect_effect"]),
        (
            "FAKE_JQ_ENVIRONMENT_READ",
            ["secret_access", "unclassified_indirect_effect"],
        ),
        ("FAKE_SORT_HIDDEN_PROGRAM", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_HIDDEN_REF_MUTATION", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_SYMBOLIC_REF_MUTATION", ["unclassified_indirect_effect"]),
        ("FAKE_GIT_REFLOG_MUTATION", ["unclassified_indirect_effect"]),
        (
            "FAKE_DIRECT_SECRET_ENCODER",
            ["secret_access", "unclassified_indirect_effect"],
        ),
        ("FAKE_WORKSPACE_EXECUTABLE", ["unclassified_indirect_effect"]),
        ("FAKE_PARAMETER_EXPANSION", ["unclassified_indirect_effect"]),
        ("FAKE_BARE_EXECUTABLE", ["unclassified_indirect_effect"]),
        ("FAKE_EXTGLOB_EXPANSION", ["unclassified_indirect_effect"]),
        ("FAKE_AWK_LAUNCHER", ["unclassified_indirect_effect"]),
        ("FAKE_NON_SYSTEM_SHELL", ["unclassified_indirect_effect"]),
        ("FAKE_UNSANDBOXED_SED", ["unclassified_indirect_effect"]),
        ("FAKE_CONFIG_DRIVEN_GIT", ["unclassified_indirect_effect"]),
        ("FAKE_MULTILINE_SHELL", ["unclassified_indirect_effect"]),
    ),
)
def test_opaque_command_authority_blocks_terminal_result(
    tmp_path: Path,
    objective_marker: str,
    expected_effects: list[str],
) -> None:
    fixture = _fixture(tmp_path, objective_marker=objective_marker)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])
    validation_events = [
        event
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
        if event["event_type"] == "external_agent.report_validated"
    ]

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "authority_boundary_crossed"
    assert validation_events[-1]["payload"]["detected_forbidden_effects"] == (
        expected_effects
    )


@pytest.mark.parametrize(
    "drift_kind",
    ("ignored", "assume-unchanged", "skip-worktree"),
)
def test_clean_required_rechecks_hidden_bytes_after_worker_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    fixture = _fixture(tmp_path, ignored_baseline=drift_kind == "ignored")
    runtime = fixture["runtime"]
    original_preflight = runtime._codex_preflight
    calls = [0]

    def mutate_after_worker_preflight(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_preflight(*args, **kwargs)
        calls[0] += 1
        if calls[0] == 2:
            if drift_kind == "ignored":
                target = fixture["workspace"] / "cache" / "output.txt"
            else:
                target = fixture["workspace"] / "README.md"
                _git(
                    fixture["workspace"],
                    "update-index",
                    f"--{drift_kind}",
                    "README.md",
                )
            target.write_text("drift during worker preflight\n", encoding="utf-8")
        return result

    monkeypatch.setattr(runtime, "_codex_preflight", mutate_after_worker_preflight)
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "workspace_manifest_drift"
    assert result["thread_id"] is None
    assert not (
        runtime._session_dir(fixture["session_id"])
        / "attempts"
        / "001"
        / "model-report.json"
    ).exists()


def test_ignored_workspace_bytes_are_manifested_and_drift_is_blocked(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_IGNORED",
        ignored_baseline=True,
    )
    runtime = fixture["runtime"]
    preflight = runtime.preflight(fixture["launch_path"])
    assert preflight["admitted"] is True
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["workspace_manifest_match"] is False
    assert {item["path"] for item in result["changed_paths"]} == {
        "cache/output.txt"
    }


def test_secret_shaped_ignored_path_blocks_manifest_without_hashing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(workspace, "add", ".gitignore")
    _git(workspace, "commit", "-m", "fixture")
    (workspace / ".env").write_text("DO_NOT_READ=this-value\n", encoding="utf-8")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_secret_path_present"


def test_workspace_manifest_disables_repository_diff_and_filter_programs(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    tracked = workspace / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    (workspace / ".gitattributes").write_text(
        "tracked.txt filter=leak\n",
        encoding="utf-8",
    )
    _git(workspace, "add", "tracked.txt", ".gitattributes")
    _git(workspace, "commit", "-m", "fixture")

    diff_marker = tmp_path / "external-diff-ran"
    diff_helper = tmp_path / "external-diff"
    diff_helper.write_text(
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(diff_marker))}\n",
        encoding="utf-8",
    )
    diff_helper.chmod(0o700)
    filter_marker = tmp_path / "clean-filter-ran"
    filter_helper = tmp_path / "clean-filter"
    filter_helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(filter_marker))}\n"
        "/bin/cat\n",
        encoding="utf-8",
    )
    filter_helper.chmod(0o700)
    _git(workspace, "config", "diff.external", str(diff_helper))
    _git(workspace, "config", "filter.leak.clean", str(filter_helper))
    tracked.write_text("changed\n", encoding="utf-8")

    manifest = RUNTIME.build_workspace_manifest(workspace)

    assert manifest["status_entries"] == [{"path": "tracked.txt", "status": " M"}]
    assert diff_marker.exists() is False
    assert filter_marker.exists() is False


def test_workspace_manifest_disables_promisor_lazy_fetch_helpers(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    tracked = workspace / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    _git(workspace, "add", "tracked.txt")
    _git(workspace, "commit", "-m", "fixture")
    blob_oid = _git(workspace, "rev-parse", "HEAD:tracked.txt")
    blob_path = workspace / ".git" / "objects" / blob_oid[:2] / blob_oid[2:]
    assert blob_path.is_file()

    marker = tmp_path / "promisor-helper-ran"
    helper = tmp_path / "promisor-helper"
    helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        "exit 1\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    _git(workspace, "config", "extensions.partialClone", "origin")
    _git(workspace, "config", "protocol.ext.allow", "always")
    _git(workspace, "config", "remote.origin.url", f"ext::{helper}")
    _git(workspace, "config", "remote.origin.promisor", "true")
    _git(workspace, "config", "remote.origin.partialclonefilter", "blob:none")
    blob_path.unlink()
    tracked.write_text("changed\n", encoding="utf-8")

    unsafe_environment = RUNTIME._base_controller_git_environment()
    unsafe_environment.pop("GIT_NO_LAZY_FETCH")
    unsafe = subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(workspace),
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "HEAD",
            "--",
        ],
        env=unsafe_environment,
        check=False,
        capture_output=True,
    )
    assert unsafe.returncode != 0
    assert marker.is_file()
    marker.unlink()

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_manifest_failed"
    assert marker.exists() is False


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_workspace_manifest_hashes_tracked_bytes_hidden_by_index_flags(
    tmp_path: Path,
    index_flag: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    tracked = workspace / "tracked.txt"
    tracked.write_text("baseline\n", encoding="utf-8")
    _git(workspace, "add", "tracked.txt")
    _git(workspace, "commit", "-m", "fixture")
    baseline = RUNTIME.build_workspace_manifest(workspace)

    _git(workspace, "update-index", index_flag, "tracked.txt")
    tracked.write_text("hidden mutation\n", encoding="utf-8")
    current = RUNTIME.build_workspace_manifest(workspace)

    baseline_entry = next(
        item
        for item in baseline["content_entries"]
        if item["path"] == "tracked.txt"
    )
    current_entry = next(
        item
        for item in current["content_entries"]
        if item["path"] == "tracked.txt"
    )
    assert current_entry["sha256"] != baseline_entry["sha256"]
    assert current_entry["index_flags"]
    assert RUNTIME.compare_workspace_manifest(baseline, current) == [
        {"path": "tracked.txt", "status": "content_changed"}
    ]


def test_workspace_manifest_rejects_tracked_submodule_worktree(
    tmp_path: Path,
) -> None:
    submodule = tmp_path / "submodule-source"
    submodule.mkdir()
    _git(submodule, "init", "-b", "main")
    _git(submodule, "config", "user.email", "fixture@example.invalid")
    _git(submodule, "config", "user.name", "Fixture")
    (submodule / "tracked.txt").write_text("submodule\n", encoding="utf-8")
    _git(submodule, "add", "tracked.txt")
    _git(submodule, "commit", "-m", "fixture")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    _git(
        workspace,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(submodule),
        "nested",
    )
    _git(workspace, "commit", "-am", "add submodule")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_submodule_unsupported"


def test_workspace_manifest_rejects_symlink_target_outside_checkout(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "host-secret.txt"
    outside.write_text("must remain outside actor reach\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "reference.txt").symlink_to(outside)
    _git(workspace, "add", "reference.txt")
    _git(workspace, "commit", "-m", "fixture")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_symlink_target_unsupported"


@pytest.mark.parametrize("ignored", (False, True))
def test_workspace_manifest_rejects_untracked_or_ignored_embedded_repository(
    tmp_path: Path,
    ignored: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "tracked.txt").write_text("outer\n", encoding="utf-8")
    if ignored:
        (workspace / ".gitignore").write_text("nested/\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "fixture")
    nested = workspace / "nested"
    nested.mkdir()
    _git(nested, "init", "-b", "main")
    (nested / "hidden.txt").write_text("nested\n", encoding="utf-8")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_embedded_repository_unsupported"


@pytest.mark.parametrize("entry_kind", ("fifo", "unix_socket"))
def test_workspace_manifest_rejects_git_invisible_special_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entry_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "tracked.txt").write_text("baseline\n", encoding="utf-8")
    _git(workspace, "add", "tracked.txt")
    _git(workspace, "commit", "-m", "fixture")
    special_path = workspace / f"unexpected-{entry_kind}"
    if entry_kind == "fifo":
        os.mkfifo(special_path)
    else:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            monkeypatch.chdir(workspace)
            listener.bind(special_path.name)
        finally:
            listener.close()

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_entry_type_unsupported"


@pytest.mark.parametrize(
    "relative_path",
    (
        "client_secret.json",
        "provider-token.txt",
        "config/secrets.toml",
        "private/service.credentials.json",
    ),
)
def test_secret_shaped_name_recognition_covers_provider_files(
    relative_path: str,
) -> None:
    assert RUNTIME._secret_shaped_path(relative_path) is True


def test_source_evidence_refuses_secret_shaped_path_before_read(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret_path = workspace / "client_secret.json"
    secret_path.write_text("must-not-be-read\n", encoding="utf-8")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._validate_source_evidence_ref(
            "source:client_secret.json#L1",
            workspace,
            source_evidence_paths=("client_secret.json",),
        )

    assert exc_info.value.code == "model_report_source_evidence_secret_shaped"


def test_invalid_jsonl_protocol_record_is_typed_terminal_failure(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_INVALID_JSONL")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "codex_event_invalid_json"
    assert all(
        event["event_type"] != "codex.invalid_jsonl"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


def test_unterminated_oversized_event_is_stopped_while_streaming(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RUNTIME, "MAX_EVENT_LINE_BYTES", 1024)
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_OVERSIZED_UNTERMINATED_EVENT",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "codex_event_too_large"


def test_failure_closeout_blocks_when_workspace_manifest_is_unobservable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"

    def fail_manifest(_workspace: str | Path) -> dict[str, Any]:
        raise RUNTIME.ExternalCodexRuntimeError(
            "workspace_secret_path_present",
            "manifest bytes cannot be observed",
        )

    monkeypatch.setattr(RUNTIME, "build_workspace_manifest", fail_manifest)
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        attempt_id = state["attempts"][-1]["attempt_id"]
        state["status"] = "failed"
        state["finished_at"] = RUNTIME.iso_now()
        runtime._write_failure_result_locked(
            state,
            attempt_id=attempt_id,
            code="unexpected_worker_failure",
            message="worker failed before closeout",
        )
        runtime._save_state(state)

    result = runtime.result(fixture["session_id"])

    assert runtime.status(fixture["session_id"])["status"] == "authority_blocked"
    assert result is not None
    assert result["status"] == "authority_blocked"
    assert result["failure_code"] == "workspace_manifest_observation_gap"
    assert result["workspace_manifest_match"] is None
    assert result["workspace_manifest_ref"] is None
    assert any(
        event["event_type"] == "external_agent.failure_manifest_unobserved"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


def test_unavailable_command_observation_is_authority_blocked(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_UNKNOWN_COMMAND")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "command_observation_gap"


def test_validation_receipt_must_match_final_workspace_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        workspace_write=True,
    )
    runtime = fixture["runtime"]
    original_record_codex_event = runtime._record_codex_event

    def mutate_after_validation_receipt(
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        line: bytes,
    ) -> None:
        original_record_codex_event(
            session_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            line=line,
        )
        payload = json.loads(line)
        item = payload.get("item") if payload.get("type") == "item.completed" else None
        if (
            isinstance(item, dict)
            and item.get("type") == "command_execution"
            and str(item.get("command", "")).endswith("git status --short")
        ):
            (fixture["workspace"] / "landing-note.md").write_text(
                "mutation after validation receipt\n", encoding="utf-8"
            )

    # The worker is forked from this runtime. Mutating immediately after the
    # controller durably records the validation event proves the intended
    # receipt/final-workspace mismatch without a scheduler-dependent sleep.
    monkeypatch.setattr(
        runtime,
        "_record_codex_event",
        mutate_after_validation_receipt,
    )
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "model_report_validation_workspace_unbound"


def test_high_token_use_is_counted_without_truncating_agent_work(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_TOKEN_OVERRUN",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["failure_code"] is None
    assert result["usage"]["input_tokens"] == 12_000
    assert result["usage"]["metering_mode"] == "observe_only"
    assert result["report_ref"]["artifact_ref"].endswith("model-report.json")
    assert Path(result["report_ref"]["artifact_ref"]).is_file()


def test_multiple_turns_are_counted_without_truncating_agent_work(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_TURN_OVERRUN",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["failure_code"] is None
    assert result["turn_count"] == 2
    assert result["report_ref"]["artifact_ref"].endswith("model-report.json")


def test_interrupted_process_resumes_exact_thread(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WAIT_FOR_INTERRUPT FAKE_SPAWN_DESCENDANT "
            "FAKE_TERM_RESISTANT_DESCENDANT"
        ),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    running: dict[str, Any] | None = None
    descendant_pid: int | None = None
    while time.monotonic() < deadline:
        running = runtime.status(fixture["session_id"])
        for event in runtime.events(fixture["session_id"], after_sequence=-1):
            payload = event.get("payload", {})
            item = payload.get("item") if isinstance(payload, dict) else None
            text = item.get("text") if isinstance(item, dict) else None
            if isinstance(text, str) and text.startswith("fixture-descendant:"):
                descendant_pid = int(text.split(":", 1)[1])
        if running["thread_id"] and running["codex_pid"] and descendant_pid:
            break
        time.sleep(0.05)
    assert running is not None and running["thread_id"]
    assert descendant_pid is not None

    interrupted = runtime.interrupt(fixture["session_id"])
    assert interrupted["status"] == "interrupted"
    assert RUNTIME._process_start_ticks(descendant_pid) is None
    interrupted_result = runtime.result(fixture["session_id"])
    assert interrupted_result is not None
    assert interrupted_result["usage_observation"]["status"] == "partial"
    assert interrupted_result["usage_observation"]["gap_reasons"] == [
        {
            "attempt_id": f"{fixture['session_id']}:attempt:1",
            "reason": "controlled_interruption_before_turn_usage",
            "event_sequence": interrupted_result["usage_observation"]["gap_reasons"][0][
                "event_sequence"
            ],
        }
    ]
    first_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    first_result_digest = _digest_path(first_result_path)
    resume = {
        "schema_version": "abyss_stack_external_codex_resume_v1",
        "session_id": fixture["session_id"],
        "thread_id": interrupted["thread_id"],
        "after_event_sequence": interrupted["last_event_sequence"],
        "reason": "process_death_recovery",
        "instruction": "Resume the exact bounded fixture and return the structured result.",
        "previous_result_digest": first_result_digest,
    }
    resume_path = tmp_path / "resume.json"
    _write_json(resume_path, resume)

    resumed = runtime.resume(fixture["session_id"], resume_path)
    assert resumed["status"] == "running"
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["thread_id"] == interrupted["thread_id"]
    assert result["attempt_count"] == 2
    assert result["turn_count"] == 1
    assert result["usage_observation"]["status"] == "partial"
    assert len(result["usage_observation"]["gap_reasons"]) == 1
    preserved_path = (
        runtime._session_dir(fixture["session_id"])
        / "attempts/001/runtime-result.json"
    )
    assert _digest_path(preserved_path) == first_result_digest
    closure_path = preserved_path.with_name(
        "runtime-result-evidence-closure.json"
    )
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    RUNTIME.validate_json(
        closure,
        RUNTIME.RESULT_EVIDENCE_CLOSURE_SCHEMA_PATH,
        label="test preserved result evidence closure",
    )
    assert closure["source_result_ref"] == RUNTIME._artifact_ref(preserved_path)
    prior_events_ref = interrupted_result["events_ref"]
    events_snapshot_ref = next(
        item["snapshot_ref"]
        for item in closure["preserved_evidence"]
        if item["source_ref"] == prior_events_ref
    )
    assert events_snapshot_ref["artifact_digest"] == prior_events_ref["artifact_digest"]
    assert _digest_path(Path(events_snapshot_ref["artifact_ref"])) == prior_events_ref[
        "artifact_digest"
    ]
    assert _digest_path(Path(prior_events_ref["artifact_ref"])) != prior_events_ref[
        "artifact_digest"
    ]
    assert any(
        item["artifact_ref"] == str(preserved_path)
        and item["artifact_digest"] == first_result_digest
        for item in result["evidence_refs"]
    )
    assert RUNTIME._artifact_ref(closure_path) in result["evidence_refs"]
    assert any(
        event["event_type"] == "external_agent.resume_source_preserved"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


def test_failed_read_only_review_identity_can_resume_exact_thread(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_IDENTITY_MISMATCH_ON_START",
        role_id="reviewer",
        task_family="landing_review",
        identity_suffix="review-identity-followup",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    failed = _wait_terminal(runtime, fixture["session_id"])
    first_result = runtime.result(fixture["session_id"])

    assert failed["status"] == "failed"
    assert first_result is not None
    assert first_result["failure_code"] == "model_report_identity_mismatch"
    first_result_digest = _digest_path(
        runtime._session_dir(fixture["session_id"]) / "result.json"
    )
    resume_path = tmp_path / "review-followup.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": failed["thread_id"],
            "after_event_sequence": failed["last_event_sequence"],
            "reason": "review_followup",
            "instruction": (
                "Return the completed review again with the exact task and "
                "incarnation identities required by the session-local schema."
            ),
            "previous_result_digest": first_result_digest,
        },
    )

    assert runtime.resume(fixture["session_id"], resume_path)["status"] == "running"
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["thread_id"] == failed["thread_id"]
    assert result["attempt_count"] == 2
    preserved_path = (
        runtime._session_dir(fixture["session_id"])
        / "attempts/001/runtime-result.json"
    )
    assert _digest_path(preserved_path) == first_result_digest
    assert any(
        item["artifact_ref"] == str(preserved_path)
        and item["artifact_digest"] == first_result_digest
        for item in result["evidence_refs"]
    )
    assert any(
        event["event_type"] == "external_agent.failed_review_resume_admitted"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


@pytest.mark.parametrize(
    ("drift_target", "failure_code"),
    (
        ("launch", "materialized_launch_drift"),
        ("task", "materialized_input_drift"),
        ("immutable", "materialized_input_drift"),
        ("execution-schema", "execution_result_schema_drift"),
    ),
)
def test_post_admission_input_drift_keeps_typed_terminal_closeout(
    tmp_path: Path,
    drift_target: str,
    failure_code: str,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
        identity_suffix=f"drift-{drift_target}",
    )
    runtime = fixture["runtime"]
    running = runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        running = runtime.status(fixture["session_id"])
        if running["thread_id"] and running["codex_pid"]:
            break
        time.sleep(0.05)
    assert running["thread_id"] and running["codex_pid"]

    interrupted = runtime.interrupt(fixture["session_id"])
    assert interrupted["status"] == "interrupted"
    state_path = runtime._state_path(fixture["session_id"])
    admitted_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert admitted_state["schema_version"] == RUNTIME.STATE_SCHEMA_VERSION
    closeout = admitted_state["failure_closeout"]
    if drift_target == "launch":
        target = state_path.parent / "inputs" / "launch.json"
    elif drift_target == "task":
        target = Path(admitted_state["materialized_inputs"]["task"])
    elif drift_target == "immutable":
        target = Path(admitted_state["materialized_task_inputs"][0]["path"])
    else:
        target = Path(admitted_state["execution_result_schema_ref"]["artifact_ref"])
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b"\n")

    resume_path = tmp_path / f"resume-{drift_target}.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": interrupted["thread_id"],
            "after_event_sequence": interrupted["last_event_sequence"],
            "reason": "process_death_recovery",
            "instruction": "Resume and preserve a typed drift failure receipt.",
        },
    )
    assert runtime.resume(fixture["session_id"], resume_path)["status"] == "running"

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None and result["failure_code"] == failure_code
    assert result["wake_evaluation"] == closeout["wake_evaluations"]["failed"]
    assert result["evidence_refs"][3:5] == [
        closeout["task_ref"],
        closeout["incarnation_binding_ref"],
    ]
    assert result["evidence_refs"][5] == result["workspace_manifest_ref"]
    failure = json.loads(
        (state_path.parent / "runtime-failure.json").read_text(encoding="utf-8")
    )
    assert failure["failure_code"] == failure_code
    assert "drift" in failure["message"] or "changed" in failure["message"]


def test_setsid_descendant_dies_with_completed_subreaper_supervisor(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_SPAWN_DESCENDANT FAKE_TERM_RESISTANT_DESCENDANT "
            "FAKE_SETSID_DESCENDANT"
        ),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    descendant_pid: int | None = None
    for event in runtime.events(fixture["session_id"], after_sequence=-1):
        payload = event.get("payload", {})
        item = payload.get("item") if isinstance(payload, dict) else None
        text = item.get("text") if isinstance(item, dict) else None
        if isinstance(text, str) and text.startswith("fixture-descendant:"):
            descendant_pid = int(text.split(":", 1)[1])

    assert terminal["status"] == "completed"
    assert descendant_pid is not None
    assert RUNTIME._process_start_ticks(descendant_pid) is None


def test_unexpected_worker_death_cleans_codex_group_and_returns_failure(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WAIT_FOR_INTERRUPT FAKE_SPAWN_DESCENDANT "
            "FAKE_TERM_RESISTANT_DESCENDANT"
        ),
    )
    runtime = fixture["runtime"]
    running = runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    descendant_pid: int | None = None
    while time.monotonic() < deadline:
        running = runtime.status(fixture["session_id"])
        for event in runtime.events(fixture["session_id"], after_sequence=-1):
            payload = event.get("payload", {})
            item = payload.get("item") if isinstance(payload, dict) else None
            text = item.get("text") if isinstance(item, dict) else None
            if isinstance(text, str) and text.startswith("fixture-descendant:"):
                descendant_pid = int(text.split(":", 1)[1])
        if running["worker_pid"] and running["codex_pid"] and descendant_pid:
            break
        time.sleep(0.05)
    assert isinstance(running["worker_pid"], int)
    assert isinstance(running["codex_pid"], int)
    assert descendant_pid is not None
    worker_pid = running["worker_pid"]
    codex_pid = running["codex_pid"]

    os.kill(worker_pid, signal.SIGKILL)
    terminal = runtime.status(fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "unexpected_worker_death"
    assert result["workspace_manifest_match"] is True
    assert RUNTIME._process_start_ticks(codex_pid) is None
    assert RUNTIME._process_start_ticks(descendant_pid) is None


def test_terminal_result_recovers_when_final_state_save_is_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    parent_pid = os.getpid()
    original_save_state = runtime._save_state

    def lose_worker_terminal_state_save(state: dict[str, Any]) -> None:
        if (
            os.getpid() != parent_pid
            and state["status"] in {*RUNTIME.TERMINAL_STATES, "interrupted"}
            and (runtime._session_dir(state["session_id"]) / "result.json").is_file()
        ):
            return
        original_save_state(state)

    monkeypatch.setattr(runtime, "_save_state", lose_worker_terminal_state_save)
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])
    event_types = [
        item["event_type"]
        for item in runtime.events(fixture["session_id"], after_sequence=-1)
    ]

    assert terminal["status"] == "completed"
    assert result is not None and result["status"] == "completed"
    assert "external_agent.worker_death_observed" not in event_types
    persisted = runtime._load_state(fixture["session_id"])
    assert persisted["result_digest"] == _digest_path(
        runtime._session_dir(fixture["session_id"]) / "result.json"
    )


@pytest.mark.parametrize(
    ("mutator", "validate_request", "failure_code"),
    (
        (
            lambda request: request.pop("expected_outputs"),
            False,
            "a2a_summon_request_invalid",
        ),
        (
            lambda request: request["summon_request"].__setitem__(
                "child_agent_id", "incarnation:fixture:wrong"
            ),
            True,
            "a2a_summon_request_unbound",
        ),
    ),
)
def test_a2a_summon_request_validation_fails_closed(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
    validate_request: bool,
    failure_code: str,
) -> None:
    fixture = _fixture(
        tmp_path,
        summon_request_mutator=mutator,
        validate_summon_request=validate_request,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    _wait_terminal(runtime, fixture["session_id"])
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        _, plan, binding, task, _, _ = runtime._materialized_payloads(state)
        with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
            runtime._validated_a2a_summon_request(
                state=state,
                plan=plan,
                binding=binding,
                task=task,
                request_input_id="summon-request",
                supplied_path=fixture["summon_request_path"],
            )
    assert exc_info.value.code == failure_code


def test_a2a_export_requires_exact_independent_review_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_state = tmp_path / "shared-state"
    writer = _fixture(
        tmp_path / "writer",
        identity_suffix="writer",
        state_root=shared_state,
    )
    runtime = writer["runtime"]
    runtime.start(writer["launch_path"])
    assert _wait_terminal(runtime, writer["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(writer["session_id"]) / "result.json"
    writer_result = runtime.result(writer["session_id"])
    assert writer_result is not None
    writer_result_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-result.json",
        digest=_digest_path(writer_result_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-result.schema.json"
        ),
        schema_version="abyss_stack_external_codex_result_v1",
    )
    writer_report_path = Path(str(writer_result["report_ref"]["artifact_ref"]))
    writer_report_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-report.json",
        digest=_digest_path(writer_report_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-report.schema.json"
        ),
        schema_version="abyss_stack_external_codex_report_v1",
    )
    writer_workspace_manifest_path = Path(
        str(writer_result["workspace_manifest_ref"]["artifact_ref"])
    )
    writer_workspace_manifest_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-workspace-manifest.json",
        digest=_digest_path(writer_workspace_manifest_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-workspace-manifest.schema.json"
        ),
        schema_version="abyss_stack_external_codex_workspace_manifest_v1",
    )
    reviewer = _fixture(
        tmp_path / "reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="reviewer",
        state_root=shared_state,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_workspace_manifest_path,
                writer_workspace_manifest_ref,
            ),
        ),
    )
    reviewer_runtime = reviewer["runtime"]
    reviewer_runtime.start(reviewer["launch_path"])
    assert (
        _wait_terminal(reviewer_runtime, reviewer["session_id"])["status"]
        == "completed"
    )
    summon_path = writer["summon_request_path"]
    output_path = tmp_path / "child-task-result.json"

    original_atomic_write = RUNTIME._atomic_write_bytes
    reviewer_lock_observed = False

    def atomic_write_with_reviewer_lock_check(
        path: Path,
        data: bytes,
        *,
        mode: int = 0o600,
    ) -> None:
        nonlocal reviewer_lock_observed
        if Path(path) == output_path:
            lock_path = (
                runtime._session_dir(reviewer["session_id"]) / "session.lock"
            )
            with lock_path.open("a+b") as competing_lock:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(
                        competing_lock.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
            reviewer_lock_observed = True
        original_atomic_write(path, data, mode=mode)

    monkeypatch.setattr(
        RUNTIME,
        "_atomic_write_bytes",
        atomic_write_with_reviewer_lock_check,
    )

    exported = runtime.export_a2a_result(
        writer["session_id"],
        reviewer_session_id=reviewer["session_id"],
        summon_request_path=summon_path,
        output_path=output_path,
    )

    assert exported["writer_thread_id"] != exported["reviewer_thread_id"]
    assert exported["child_task_result"]["reviewed"] is True
    assert exported["child_task_result"]["review_outcome"] == "proceed"
    assert exported["child_task_result"]["remote_task"]["state"] == "completed"
    assert (
        exported["child_task_result"]["reviewed_artifact_path"]
        == str(writer_result_path)
    )
    assert output_path.is_file()
    assert reviewer_lock_observed is True
    monkeypatch.setattr(RUNTIME, "_atomic_write_bytes", original_atomic_write)

    reviewer_result_path = runtime._session_dir(reviewer["session_id"]) / "result.json"
    reviewer_state_path = runtime._state_path(reviewer["session_id"])
    original_reviewer_result = reviewer_result_path.read_bytes()
    original_reviewer_state = reviewer_state_path.read_bytes()
    stale_reviewer = runtime.result(reviewer["session_id"])
    assert stale_reviewer is not None
    changed_reviewer = json.loads(original_reviewer_result)
    changed_reviewer["duration_seconds"] = float(
        changed_reviewer["duration_seconds"]
    ) + 1.0
    _write_json(reviewer_result_path, changed_reviewer)
    changed_state = json.loads(original_reviewer_state)
    changed_state["result_digest"] = _digest_path(reviewer_result_path)
    _write_json(reviewer_state_path, changed_state)
    original_result_method = runtime.result

    def stale_result(session_id: str) -> dict[str, Any] | None:
        if session_id == reviewer["session_id"]:
            return stale_reviewer
        return original_result_method(session_id)

    monkeypatch.setattr(runtime, "result", stale_result)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "raced-reviewer-result.json",
        )
    assert exc_info.value.code == "a2a_review_state_unbound"
    monkeypatch.setattr(runtime, "result", original_result_method)
    reviewer_result_path.write_bytes(original_reviewer_result)
    reviewer_state_path.write_bytes(original_reviewer_state)

    mismatched_manifest_path = tmp_path / "mismatched-review-workspace-manifest.json"
    mismatched_manifest = json.loads(
        writer_workspace_manifest_path.read_text(encoding="utf-8")
    )
    mismatched_manifest["git_diff_binary_sha256"] = "sha256:" + ("0" * 64)
    _write_json(mismatched_manifest_path, mismatched_manifest)
    mismatched_manifest_ref = _provenance(
        "abyss-stack",
        "runtime-results/mismatched-review-workspace-manifest.json",
        digest=_digest_path(mismatched_manifest_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-workspace-manifest.schema.json"
        ),
        schema_version="abyss_stack_external_codex_workspace_manifest_v1",
    )
    unbound_reviewer = _fixture(
        tmp_path / "unbound-reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="unbound-reviewer",
        state_root=shared_state,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                mismatched_manifest_path,
                mismatched_manifest_ref,
            ),
        ),
    )
    runtime.start(unbound_reviewer["launch_path"])
    assert (
        _wait_terminal(runtime, unbound_reviewer["session_id"])["status"]
        == "completed"
    )
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=unbound_reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "unbound-manifest-child-task-result.json",
        )
    assert exc_info.value.code == "a2a_review_not_bound"

    substituted_summon_path = tmp_path / "substituted-summon-request.json"
    substituted_summon = json.loads(summon_path.read_text(encoding="utf-8"))
    substituted_summon["audit_refs"].append("fixture:substituted")
    substituted_summon["summon_request"]["audit_refs"].append(
        "fixture:substituted"
    )
    _write_json(substituted_summon_path, substituted_summon)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=reviewer["session_id"],
            summon_request_path=substituted_summon_path,
            output_path=tmp_path / "substituted-summon-result.json",
        )
    assert exc_info.value.code == "a2a_summon_request_unbound"

    reviewer_result = runtime.result(reviewer["session_id"])
    assert reviewer_result is not None
    for index, report_path in enumerate(
        (
            writer_report_path,
            Path(str(reviewer_result["report_ref"]["artifact_ref"])),
        ),
        start=1,
    ):
        original = report_path.read_bytes()
        tampered = json.loads(original)
        tampered["summary"] += " tampered"
        _write_json(report_path, tampered)
        with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
            runtime.export_a2a_result(
                writer["session_id"],
                reviewer_session_id=reviewer["session_id"],
                summon_request_path=summon_path,
                output_path=tmp_path / f"tampered-report-{index}.json",
            )
        assert exc_info.value.code == "a2a_artifact_drift"
        report_path.write_bytes(original)

    for index, manifest_path in enumerate(
        (
            Path(str(writer_result["workspace_manifest_ref"]["artifact_ref"])),
            Path(str(reviewer_result["workspace_manifest_ref"]["artifact_ref"])),
        ),
        start=1,
    ):
        original = manifest_path.read_bytes()
        manifest_path.write_bytes(original + b"\n")
        with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
            runtime.export_a2a_result(
                writer["session_id"],
                reviewer_session_id=reviewer["session_id"],
                summon_request_path=summon_path,
                output_path=tmp_path / f"tampered-manifest-{index}.json",
            )
        assert exc_info.value.code == "a2a_artifact_drift"
        manifest_path.write_bytes(original)

    repair_reviewer = _fixture(
        tmp_path / "repair-reviewer",
        objective_marker="FAKE_RETURN_FOR_REPAIR",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="repair-reviewer",
        state_root=shared_state,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_workspace_manifest_path,
                writer_workspace_manifest_ref,
            ),
        ),
    )
    runtime.start(repair_reviewer["launch_path"])
    assert (
        _wait_terminal(runtime, repair_reviewer["session_id"])["status"]
        == "review_required"
    )
    repair_export = runtime.export_a2a_result(
        writer["session_id"],
        reviewer_session_id=repair_reviewer["session_id"],
        summon_request_path=summon_path,
        output_path=tmp_path / "repair-child-task-result.json",
    )
    assert repair_export["child_task_result"]["review_outcome"] == (
        "return_for_repair"
    )
    assert repair_export["child_task_result"]["remote_task"]["state"] == "failed"

    failed_reviewer = _fixture(
        tmp_path / "failed-reviewer",
        objective_marker="FAKE_INVALID_JSONL",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="failed-reviewer",
        state_root=shared_state,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_workspace_manifest_path,
                writer_workspace_manifest_ref,
            ),
        ),
    )
    runtime.start(failed_reviewer["launch_path"])
    assert _wait_terminal(runtime, failed_reviewer["session_id"])["status"] == "failed"
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=failed_reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "failed-reviewer-child-task-result.json",
        )
    assert exc_info.value.code == "a2a_review_runtime_failed"

    failed_reviewer_result = runtime.result(reviewer["session_id"])
    assert failed_reviewer_result is not None
    failed_reviewer_result["status"] = "failed"
    failed_reviewer_result["failure_code"] = "provider_limit_reached"
    _write_json(reviewer_result_path, failed_reviewer_result)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "failed-review-child-task-result.json",
        )

    assert exc_info.value.code == "runtime_result_drift"


def _parent_reentry_obligation(
    tmp_path: Path,
    fixture: dict[str, Any],
    *,
    reentry_id: str,
) -> Path:
    child_realization = json.loads(
        fixture["realization_path"].read_text(encoding="utf-8")
    )
    child_realization["model_realization_id"] = (
        "model-realization:transport-fixture/sol/max/read-only"
    )
    child_realization["configuration"]["runtime"]["model_slug"] = "gpt-5.6-sol"
    child_realization["configuration"]["reasoning_effort"] = "max"
    parent_realization_path = tmp_path / "parent-sol-realization.json"
    _write_json(parent_realization_path, child_realization)
    obligation = {
        "schema_version": "abyss_stack_external_codex_parent_obligation_v1",
        "reentry_id": reentry_id,
        "parent_task_id": "parent:fixture:goal",
        "parent_model_realization_ref": {
            "owner_repo": "aoa-models",
            "artifact_ref": str(parent_realization_path.resolve()),
            "artifact_digest": _digest_path(parent_realization_path),
        },
        "parent_role_ref": {
            "owner_repo": "aoa-agents",
            "artifact_ref": str(fixture["role_path"].resolve()),
            "artifact_digest": _digest_path(fixture["role_path"]),
        },
        "child_task_ref": {
            "owner_repo": "fixture-target",
            "artifact_ref": str(fixture["task_path"].resolve()),
            "artifact_digest": _digest_path(fixture["task_path"]),
        },
        "child_incarnation_binding_ref": {
            "owner_repo": "aoa-sdk",
            "artifact_ref": str(fixture["binding_path"].resolve()),
            "artifact_digest": _digest_path(fixture["binding_path"]),
        },
        "parent_workspace": str(fixture["workspace"].resolve()),
        "codex_executable": fixture["launch"]["codex_executable"],
        "codex_executable_digest": fixture["launch"]["codex_executable_digest"],
        "codex_home": fixture["launch"]["codex_home"],
        "return_owner": "fixture-target",
        "expected_wake_condition_id": "authority-needed",
        "expected_wake_event_kind": "run.authority_required",
        "permission_posture": {
            "sandbox_mode": "read-only",
            "approval_policy": "never",
            "network_access": "disabled",
            "external_effects": False,
            "multi_agent_enabled": False,
        },
        "usage_metering": {
            "mode": "observe_only",
            "execution_limit_policy": "none",
            "metering_regime": "chatgpt_quota",
        },
        "deferred_parent_decisions": [
            "Whether to accept or perform any landing effect."
        ],
    }
    obligation_path = tmp_path / "parent-obligation.json"
    _write_json(obligation_path, obligation)
    return obligation_path


def test_parent_inference_yields_and_exact_authority_event_reenters_same_thread(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-ambiguity",
    )
    reentry_id = "reentry:fixture:luna-xhigh-ambiguity"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")

    yielded = bridge.yield_parent(obligation_path)["state"]
    assert yielded["status"] == "waiting"
    assert len(yielded["turns"]) == 1
    parent_thread_id = yielded["parent_thread_id"]

    child_terminal = fixture["runtime"].run_to_terminal(fixture["launch_path"])
    assert child_terminal["status"] == "authority_blocked"
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    reentered = bridge.reenter_parent(reentry_id, child_result_path)["state"]

    assert reentered["status"] == "reentered"
    assert len(reentered["turns"]) == 2
    assert {turn["thread_id"] for turn in reentered["turns"]} == {
        parent_thread_id
    }
    assert reentered["wake_evaluation"]["event_kind"] == "run.authority_required"
    assert reentered["wake_evaluation"]["wake_parent"] is True
    admitted_result_path = Path(reentered["child_result_ref"]["artifact_ref"])
    assert admitted_result_path != child_result_path
    assert admitted_result_path.parent.parent.name == "attempts"
    assert admitted_result_path.name.startswith("runtime-result")
    reentry_output = RUNTIME._load_verified_json_ref(
        reentered["reentry_result_ref"], label="test re-entry result"
    )
    assert reentry_output["next_action"] == "request_human_authority"
    events = [
        json.loads(line)
        for line in Path(reentered["events_ref"]["artifact_ref"])
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event_type"] for event in events] == [
        "external_parent.yield_prepared",
        "external_parent.inference_yielded",
        "external_parent.wait_registered",
        "external_parent.child_event_admitted",
        "external_parent.reentry_started",
        "external_parent.reentry_completed",
    ]


def test_parent_yield_rejects_any_tool_event(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-parent-tool-event",
    )
    reentry_id = "reentry:fixture:parent-tool-event"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        bridge.yield_parent(obligation_path)

    assert exc_info.value.code == "reentry_parent_tool_event_forbidden"
    assert bridge.status(reentry_id)["state"]["status"] == "yielding"


def test_parent_reentry_recovers_admitted_snapshot_without_live_child_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-admission-crash",
    )
    reentry_id = "reentry:fixture:luna-xhigh-admission-crash"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    original_append = bridge._append_event
    crashed = False

    def crash_after_child_admission(*args: Any, **kwargs: Any) -> Any:
        nonlocal crashed
        event = original_append(*args, **kwargs)
        if (
            kwargs.get("event_type") == "external_parent.child_event_admitted"
            and not crashed
        ):
            crashed = True
            raise KeyboardInterrupt("fixture crash after immutable admission")
        return event

    monkeypatch.setattr(bridge, "_append_event", crash_after_child_admission)
    with pytest.raises(KeyboardInterrupt, match="immutable admission"):
        bridge.reenter_parent(reentry_id, child_result_path)

    admitted = bridge.status(reentry_id)["state"]
    admitted_path = Path(admitted["child_result_ref"]["artifact_ref"])
    assert admitted["status"] == "waiting"
    assert admitted_path != child_result_path
    assert admitted_path.parent.parent.name == "attempts"

    monkeypatch.setattr(bridge, "_append_event", original_append)

    def forbid_live_child_lookup(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("admitted retry consulted the mutable child result")

    monkeypatch.setattr(bridge, "_child_runtime_lock_target", forbid_live_child_lookup)
    recovered = bridge.reenter_parent(reentry_id, child_result_path)["state"]
    events = [
        json.loads(line)
        for line in bridge._events_path(reentry_id).read_text(encoding="utf-8").splitlines()
    ]

    assert recovered["status"] == "reentered"
    assert recovered["child_result_ref"] == admitted["child_result_ref"]
    assert [event["event_type"] for event in events].count(
        "external_parent.child_event_admitted"
    ) == 1


def test_parent_reentry_recovers_started_event_before_state_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-start-event-crash",
    )
    reentry_id = "reentry:fixture:luna-xhigh-start-event-crash"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    original_save = bridge._save_state
    crashed = False

    def crash_before_reentering_state_save(state: dict[str, Any]) -> None:
        nonlocal crashed
        if state["status"] == "reentering" and not crashed:
            crashed = True
            raise KeyboardInterrupt("fixture crash after re-entry start event")
        original_save(state)

    monkeypatch.setattr(bridge, "_save_state", crash_before_reentering_state_save)
    with pytest.raises(KeyboardInterrupt, match="start event"):
        bridge.reenter_parent(reentry_id, child_result_path)

    recovered_start = bridge.status(reentry_id)["state"]
    assert recovered_start["status"] == "reentering"

    monkeypatch.setattr(bridge, "_save_state", original_save)
    completed = bridge.reenter_parent(reentry_id, child_result_path)["state"]
    events = [
        json.loads(line)
        for line in bridge._events_path(reentry_id).read_text(encoding="utf-8").splitlines()
    ]

    assert completed["status"] == "reentered"
    assert [event["event_type"] for event in events].count(
        "external_parent.child_event_admitted"
    ) == 1
    assert [event["event_type"] for event in events].count(
        "external_parent.reentry_started"
    ) == 1


def test_parent_yield_retries_from_durable_state_without_rewriting_partial_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-yield-retry",
    )
    reentry_id = "reentry:fixture:luna-xhigh-yield-retry"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    original_run_parent_turn = bridge._run_parent_turn
    partial_attempt = (
        bridge._reentry_dir(reentry_id)
        / "turns"
        / "001-yield-attempt-001"
    )

    def crash_after_pre_yield_state(*args: Any, **kwargs: Any) -> Any:
        durable = RUNTIME.load_json(
            bridge._state_path(reentry_id), label="durable pre-yield state"
        )
        assert durable["status"] == "yielding"
        assert durable["turns"] == []
        partial_attempt.mkdir(parents=True)
        (partial_attempt / "prompt.txt").write_text(
            "preserved partial attempt\n", encoding="utf-8"
        )
        raise RUNTIME.ExternalCodexRuntimeError(
            "fixture_controller_crash", "controller stopped before parent inference"
        )

    monkeypatch.setattr(bridge, "_run_parent_turn", crash_after_pre_yield_state)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        bridge.yield_parent(obligation_path)
    assert exc_info.value.code == "fixture_controller_crash"

    monkeypatch.setattr(bridge, "_run_parent_turn", original_run_parent_turn)
    recovered = bridge.yield_parent(obligation_path)["state"]

    assert recovered["status"] == "waiting"
    assert recovered["schema_version"] == RUNTIME.REENTRY_STATE_SCHEMA_VERSION
    assert partial_attempt.joinpath("prompt.txt").read_text(encoding="utf-8") == (
        "preserved partial attempt\n"
    )
    assert (
        bridge._reentry_dir(reentry_id)
        / "turns"
        / "001-yield-attempt-002"
        / "model-output.json"
    ).is_file()


def test_parent_yield_recovers_completed_turn_event_without_second_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-yield-event-recovery",
    )
    reentry_id = "reentry:fixture:luna-xhigh-yield-event-recovery"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    original_save_state = bridge._save_state
    dropped_yielded_save = False

    def crash_after_yield_event(state: dict[str, Any]) -> None:
        nonlocal dropped_yielded_save
        if state["status"] == "yielded" and not dropped_yielded_save:
            dropped_yielded_save = True
            raise RUNTIME.ExternalCodexRuntimeError(
                "fixture_controller_crash",
                "controller stopped after the complete yield event",
            )
        original_save_state(state)

    monkeypatch.setattr(bridge, "_save_state", crash_after_yield_event)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        bridge.yield_parent(obligation_path)
    assert exc_info.value.code == "fixture_controller_crash"

    dropped_waiting_save = False

    def crash_after_wait_event(state: dict[str, Any]) -> None:
        nonlocal dropped_waiting_save
        if state["status"] == "waiting" and not dropped_waiting_save:
            dropped_waiting_save = True
            raise RUNTIME.ExternalCodexRuntimeError(
                "fixture_wait_registration_crash",
                "controller stopped after the durable wait event",
            )
        original_save_state(state)

    monkeypatch.setattr(bridge, "_save_state", crash_after_wait_event)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as wait_exc_info:
        bridge.yield_parent(obligation_path)
    assert wait_exc_info.value.code == "fixture_wait_registration_crash"

    monkeypatch.setattr(bridge, "_save_state", original_save_state)
    recovered = bridge.yield_parent(obligation_path)["state"]

    assert recovered["status"] == "waiting"
    assert len(recovered["turns"]) == 1
    attempts = list(
        (bridge._reentry_dir(reentry_id) / "turns").glob(
            "001-yield-attempt-*"
        )
    )
    assert len(attempts) == 1


def test_parent_reentry_resumes_after_crash_before_turn_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-reentry-pre-turn-crash",
    )
    reentry_id = "reentry:fixture:luna-xhigh-reentry-pre-turn-crash"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    original_run_parent_turn = bridge._run_parent_turn

    def crash_before_reentry_turn(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("kind") == "reentry":
            raise KeyboardInterrupt("fixture controller crash")
        return original_run_parent_turn(*args, **kwargs)

    monkeypatch.setattr(bridge, "_run_parent_turn", crash_before_reentry_turn)
    with pytest.raises(KeyboardInterrupt, match="fixture controller crash"):
        bridge.reenter_parent(reentry_id, child_result_path)
    assert bridge.status(reentry_id)["state"]["status"] == "reentering"

    monkeypatch.setattr(bridge, "_run_parent_turn", original_run_parent_turn)
    recovered = bridge.reenter_parent(reentry_id, child_result_path)["state"]
    events = [
        json.loads(line)
        for line in bridge._events_path(reentry_id).read_text(encoding="utf-8").splitlines()
    ]

    assert recovered["status"] == "reentered"
    assert [item["event_type"] for item in events].count(
        "external_parent.child_event_admitted"
    ) == 1
    assert [item["event_type"] for item in events].count(
        "external_parent.reentry_started"
    ) == 1


def test_parent_reentry_recovers_completed_turn_artifacts_without_second_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-reentry-turn-recovery",
    )
    reentry_id = "reentry:fixture:luna-xhigh-reentry-turn-recovery"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    original_run_parent_turn = bridge._run_parent_turn

    def crash_after_reentry_turn(*args: Any, **kwargs: Any) -> Any:
        result = original_run_parent_turn(*args, **kwargs)
        if kwargs.get("kind") == "reentry":
            raise KeyboardInterrupt("fixture post-turn controller crash")
        return result

    monkeypatch.setattr(bridge, "_run_parent_turn", crash_after_reentry_turn)
    with pytest.raises(KeyboardInterrupt, match="post-turn"):
        bridge.reenter_parent(reentry_id, child_result_path)
    attempts = list(
        (bridge._reentry_dir(reentry_id) / "turns").glob(
            "002-reentry-attempt-*"
        )
    )
    assert len(attempts) == 1

    monkeypatch.setattr(bridge, "_run_parent_turn", original_run_parent_turn)
    recovered = bridge.reenter_parent(reentry_id, child_result_path)["state"]

    assert recovered["status"] == "reentered"
    assert len(
        list(
            (bridge._reentry_dir(reentry_id) / "turns").glob(
                "002-reentry-attempt-*"
            )
        )
    ) == 1


def test_parent_admits_child_event_while_canonical_child_lock_is_held(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-child-lock",
    )
    reentry_id = "reentry:fixture:luna-xhigh-child-lock"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )

    child_lock_active = False
    original_child_lock = RUNTIME.ExternalCodexRuntime._lock

    @RUNTIME.contextmanager
    def observed_child_lock(runtime: Any, session_id: str) -> Any:
        nonlocal child_lock_active
        with original_child_lock(runtime, session_id):
            child_lock_active = True
            try:
                yield
            finally:
                child_lock_active = False

    original_parent_append = bridge._append_event

    def require_child_lock_for_admission(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("event_type") == "external_parent.child_event_admitted":
            assert child_lock_active is True
        original_parent_append(*args, **kwargs)

    monkeypatch.setattr(RUNTIME.ExternalCodexRuntime, "_lock", observed_child_lock)
    monkeypatch.setattr(bridge, "_append_event", require_child_lock_for_admission)

    reentered = bridge.reenter_parent(reentry_id, child_result_path)["state"]

    assert reentered["status"] == "reentered"
    assert child_lock_active is False


def test_parent_reentry_rejects_standalone_child_result_without_runtime_state(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-standalone-result",
    )
    reentry_id = "reentry:fixture:luna-xhigh-standalone-result"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    source_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    standalone_dir = (
        tmp_path
        / "standalone"
        / "sessions"
        / RUNTIME._session_token(fixture["session_id"])
    )
    standalone_dir.mkdir(parents=True)
    standalone_result_path = standalone_dir / "result.json"
    standalone_result_path.write_bytes(source_result_path.read_bytes())

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        bridge.reenter_parent(reentry_id, standalone_result_path)

    assert exc_info.value.code == "reentry_child_state_missing"


def test_parent_reentry_recovers_valid_event_appended_before_state_save(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-event-recovery",
    )
    reentry_id = "reentry:fixture:luna-xhigh-event-recovery"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    waiting = bridge.yield_parent(obligation_path)["state"]
    old_digest = waiting["events_ref"]["artifact_digest"]
    bridge._append_event(
        reentry_id,
        event_type="external_parent.recovery_fixture",
        payload={"cause": "crash-before-state-save"},
        significance="trace",
    )

    recovered = bridge.status(reentry_id)["state"]

    assert recovered["status"] == "waiting"
    assert recovered["events_ref"]["artifact_digest"] != old_digest
    assert recovered["events_ref"]["artifact_digest"] == RUNTIME.sha256_file(
        bridge._events_path(reentry_id)
    )


def test_parent_reentry_status_uses_transition_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        identity_suffix="luna-xhigh-status-lock",
    )
    reentry_id = "reentry:fixture:luna-xhigh-status-lock"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    original_lock = bridge._lock
    lock_entries = 0

    @RUNTIME.contextmanager
    def observed_lock(value: str) -> Any:
        nonlocal lock_entries
        lock_entries += 1
        with original_lock(value):
            yield

    monkeypatch.setattr(bridge, "_lock", observed_lock)
    observed = bridge.status(reentry_id)

    assert observed["state"]["status"] == "waiting"
    assert lock_entries == 1


def test_parent_reentry_recovers_completed_semantic_state_after_event_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-semantic-recovery",
    )
    reentry_id = "reentry:fixture:luna-xhigh-semantic-recovery"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)
    assert fixture["runtime"].run_to_terminal(fixture["launch_path"])["status"] == (
        "authority_blocked"
    )
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    original_save_state = bridge._save_state

    def crash_before_completed_state_save(state: dict[str, Any]) -> None:
        if state["status"] != "reentered":
            original_save_state(state)

    monkeypatch.setattr(bridge, "_save_state", crash_before_completed_state_save)
    recovered = bridge.reenter_parent(reentry_id, child_result_path)["state"]

    assert recovered["status"] == "reentered"
    assert len(recovered["turns"]) == 2
    assert recovered["reentry_result_ref"] == recovered["turns"][1]["output_ref"]
    persisted = json.loads(bridge._state_path(reentry_id).read_text(encoding="utf-8"))
    assert persisted["status"] == "reentered"


def test_non_parent_child_event_is_filtered_without_second_sol_turn(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_execution",
        identity_suffix="luna-xhigh-filtered",
    )
    reentry_id = "reentry:fixture:luna-xhigh-filtered"
    obligation_path = _parent_reentry_obligation(
        tmp_path, fixture, reentry_id=reentry_id
    )
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    bridge.yield_parent(obligation_path)

    child_terminal = fixture["runtime"].run_to_terminal(fixture["launch_path"])
    assert child_terminal["status"] == "completed"
    child_result_path = (
        fixture["runtime"]._session_dir(fixture["session_id"]) / "result.json"
    )
    filtered = bridge.reenter_parent(reentry_id, child_result_path)["state"]
    assert filtered["status"] == "filtered"
    assert len(filtered["turns"]) == 1


def test_domain_scenario_resolves_summon_responsibility_from_exact_refs() -> None:
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    by_kind = {
        item.artifact_kind: item.artifact_ref
        for item in base.scenario_binding.input_artifact_bindings
    }
    summon_decision_ref = by_kind["summon_decision"].model_copy(
        update={
            "schema_ref": PREPARER.SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH.as_posix(),
            "schema_version": PREPARER.SDK_SUMMON_RESULT_SCHEMA_VERSION,
        }
    )
    generic_scenario = base.scenario_binding.model_copy(
        update={
            "input_artifact_bindings": (),
            "input_refs": (
                *base.scenario_binding.input_refs,
                by_kind["summon_request"],
                summon_decision_ref,
            ),
        }
    )
    generic_plan = base.model_copy(update={"scenario_binding": generic_scenario})

    decision_ref = PREPARER._writer_summon_decision_ref(
        plan=generic_plan,
        task_request_ref=by_kind["summon_request"],
        writer_summon_ref=by_kind["summon_request"],
    )

    assert decision_ref == summon_decision_ref


def test_runtime_accepts_exact_domain_scenario_summon_request_binding() -> None:
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    request_ref = next(
        item.artifact_ref
        for item in base.scenario_binding.input_artifact_bindings
        if item.artifact_kind == "summon_request"
    )
    generic_scenario = base.scenario_binding.model_copy(
        update={
            "input_artifact_bindings": (),
            "input_refs": (*base.scenario_binding.input_refs, request_ref),
        }
    )
    generic_plan = base.model_copy(update={"scenario_binding": generic_scenario})

    assert RUNTIME._plan_binds_active_summon_request(generic_plan, request_ref)
