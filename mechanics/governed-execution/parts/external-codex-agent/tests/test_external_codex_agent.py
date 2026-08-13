from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import http.server
import importlib.util
import json
import os
import re
import shlex
import signal
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from aoa_sdk.a2a.rebase import (
    QuestPassport,
    SummonIntent,
    build_summon_request_payload,
)
from aoa_sdk.contracts.control_plane import (
    ContentRef,
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
    build_agent_incarnation_binding_v2,
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
    SDK_ROOT / "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SUMMON_REQUEST_SCHEMA_REF = (
    "mechanics/checkpoint/parts/child-task-reentry/schemas/"
    "summon-request-v4.schema.json"
)
SUMMON_REQUEST_SCHEMA_VERSION = "urn:aoa-sdk:a2a:summon-request:v4"
OWNER_EXECUTION_REQUEST_SCHEMA_PATH = (
    AGENTS_ROOT / "skills/aoa-summon/references/summon-request-v4.schema.json"
)
OWNER_EXECUTION_REQUEST_COMPILER_PATH = (
    AGENTS_ROOT / "skills/aoa-summon/scripts/compile_external_execution_request.py"
)
TASK_LOCAL_DAG_SCHEMA_PATH = SKILLS_ROOT / "schemas/task_local_dag_v2.schema.json"
CONTROLLER_PATH = PART_ROOT / "external_codex_agent.py"
BINDER_PATH = PART_ROOT / "bind_external_actor_launch.py"
PREPARER_PATH = PART_ROOT / "prepare_landing_study.py"
SUPERVISOR_PATH = PART_ROOT / "external_codex_supervisor.py"
CLI_PATH = PART_ROOT.parents[3] / "scripts/aoa-external-codex-agent"
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
SUMMON_COMPILER = (
    _load_module(
        "aoa_agents_external_execution_request_compiler",
        OWNER_EXECUTION_REQUEST_COMPILER_PATH,
    )
    if OWNER_EXECUTION_REQUEST_COMPILER_PATH.is_file()
    else None
)
SUPERVISOR = _load_module(
    "abyss_stack_external_codex_supervisor_under_test",
    SUPERVISOR_PATH,
)
ACTOR_EXECUTION_ROOT = RUNTIME.ACTOR_EXECUTION_ROOT


def _digest_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _digest_path(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _semantic_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest_bytes(raw)


def _self_digest(value: Mapping[str, Any], field: str) -> str:
    return _semantic_digest(dict(value) | {field: ZERO_DIGEST})


def _refresh_request_digest(value: dict[str, Any]) -> None:
    value["request_digest"] = _semantic_digest(
        {key: item for key, item in value.items() if key != "request_digest"}
    )


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
    tool_profile_id: str | None = None,
) -> None:
    mcp_profiles = {
        "aoa_evals": "abyss-stack:external_codex_agent/eval-reader-v1",
        "aoa_stats": "abyss-stack:external_codex_agent/stats-reader-v1",
        "aoa_memo": "abyss-stack:external_codex_agent/memo-reader-v1",
    }
    profile_id = tool_profile_id or (
        mcp_profiles[role_mcp]
        if role_mcp is not None
        else "abyss-stack:external_codex_agent/bounded-repo-write-v1"
        if workspace_write
        else "abyss-stack:external_codex_agent/bounded-source-readonly-v1"
    )
    required_tools = (
        ["shell-read", "workspace-write"] if workspace_write else ["shell-read"]
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
if "sandbox" in args:
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
if "FAKE_REQUIRE_PRIVATE_GIT" in task["objective"]:
    if not (workspace / ".git" / "HEAD").is_file():
        raise SystemExit(13)
    if workspace.joinpath("README.md").read_text(encoding="utf-8") != "# Landing fixture\n":
        raise SystemExit(14)

def emit(value):
    print(json.dumps(value), flush=True)

emit({"type": "thread.started", "thread_id": thread_id})
emit({"type": "turn.started"})
if "FAKE_PROVIDER_CAPACITY_FAILURE" in task["objective"] and not resume:
    message = (
        "You've hit your usage limit. Visit "
        "https://chatgpt.com/codex/settings/usage to purchase more credits or "
        "try again at Aug 17th, 2026 5:59 PM."
    )
    emit({"type": "error", "message": message})
    emit({"type": "turn.failed", "error": {"message": message}})
    raise SystemExit(1)
if "FAKE_OTHER_PROCESS_FAILURE" in task["objective"] and not resume:
    message = "A non-capacity provider failure occurred."
    emit({"type": "error", "message": message})
    emit({"type": "turn.failed", "error": {"message": message}})
    raise SystemExit(1)
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
if "FAKE_WRITE_NESTED_ALLOWED" in task["objective"]:
    (workspace / "actor-output").mkdir(exist_ok=True)
    (workspace / "actor-output" / "result.json").write_text(
        '{"status":"ready"}\n', encoding="utf-8"
    )
if "FAKE_WRITE_EMPTY_ALLOWED_PARENT" in task["objective"]:
    (workspace / "actor-output").mkdir(exist_ok=True)
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
if "FAKE_REVIEW_TRANSITION_MISMATCH" in task["objective"] and not (
    "FAKE_REVIEW_TRANSITION_MISMATCH_ON_START" in task["objective"] and resume
):
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
if "FAKE_NESTED_ARTIFACT_PRODUCED" in task["objective"]:
    report["artifact_paths"] = ["actor-output/result.json"]
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
        "runtime:workspace-final-manifest#content_entries"
    ]
if "FAKE_VALID_RUNTIME_FINAL_MANIFEST_PATH_EVIDENCE" in task["objective"]:
    report["transition"]["evidence_refs"] = [
        "runtime:workspace-final-manifest#landing-note.md"
    ]
if "FAKE_PARTIAL_RUNTIME_FINAL_MANIFEST_ANCHOR" in task["objective"]:
    report["transition"]["evidence_refs"] = [
        "runtime:workspace-final-manifest#git_head"
    ]
if (
    "FAKE_INVALID_RUNTIME_FINAL_MANIFEST_ANCHOR" in task["objective"]
    and not (
        "FAKE_INVALID_RUNTIME_FINAL_MANIFEST_ANCHOR_ON_START" in task["objective"]
        and resume
    )
):
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
    extra_immutable_inputs: tuple[tuple[str, Path, ProvenanceRef], ...] = (),
    workspace_write: bool = False,
    exact_baseline: bool = False,
    review_required: bool = False,
    ignored_baseline: bool = False,
    prepare_mutation_reviewer_sources: bool = False,
    reviewer_tool_profile_id: str | None = None,
    allowed_paths: tuple[str, ...] = ("README.md", "landing-note.md"),
    source_evidence_paths: tuple[str, ...] | None = None,
    summon_request_mutator: Callable[[dict[str, Any]], None] | None = None,
    validate_summon_request: bool = True,
    owner_contour: bool = False,
    owner_binding_v1: bool = False,
    role_mcp: str | None = None,
    tool_profile_id: str | None = None,
    workspace_projection_seed: Mapping[str, str] | None = None,
    responsibility_transfer_mutator: Callable[[dict[str, Any]], None] | None = None,
    validation_commands: tuple[Mapping[str, Any], ...] | None = None,
    omit_historical_reviewer_inputs: bool = False,
) -> dict[str, Any]:
    if owner_binding_v1 and not owner_contour:
        raise AssertionError(
            "owner_binding_v1 is only meaningful for owner-contour tests"
        )
    if omit_historical_reviewer_inputs and not owner_contour:
        raise AssertionError(
            "historical reviewer-input omission is only meaningful for owner contour"
        )
    if omit_historical_reviewer_inputs and exact_baseline:
        raise AssertionError(
            "historical reviewer-input omission uses the clean writer posture"
        )
    if role_mcp is not None and workspace_write:
        raise AssertionError("role-scoped MCP fixtures are read-only")
    if tool_profile_id is not None and role_mcp is not None:
        raise AssertionError("an explicit tool profile cannot also select a role MCP")
    if reviewer_tool_profile_id is not None and not prepare_mutation_reviewer_sources:
        raise AssertionError(
            "an explicit reviewer tool profile requires reviewer source preparation"
        )
    if owner_contour and (
        not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
        or SUMMON_COMPILER is None
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
    role_ref: ProvenanceRef
    if not owner_contour:
        _write_json(
            role_path,
            {
                "schema_version": "fixture-role-v1",
                "role_id": role_id,
                "obligation": "Return a bounded landing assessment without owner claims.",
            },
        )
        role_ref = _provenance(
            "aoa-agents",
            f"generated/agent_catalog.min.json#agents/{role_id}",
            digest=_digest_path(role_path),
            schema_version="fixture-v1",
        )
    extra_role_refs: tuple[tuple[str, ProvenanceRef], ...] = ()
    reviewer_role_path: Path | None = None
    reviewer_realization_path: Path | None = None
    if prepare_mutation_reviewer_sources:
        reviewer_role_path = (
            tmp_path
            / "aoa-agents"
            / "agents/roles/reviewer/specializations/route-drift-review/specialization.json"
        )
        reviewer_capability_relative = (
            "agents/operating-model/capabilities/packs/"
            "route-drift-review.readonly.capability.json"
        )
        _write_json(
            reviewer_role_path,
            {
                "schema_version": "fixture-reviewer-role-v1",
                "role_id": "reviewer",
                "obligation": "Independently review one bounded writer result.",
                "capability_pack_ref": reviewer_capability_relative,
            },
        )
        reviewer_capability_path = (
            tmp_path / "aoa-agents" / reviewer_capability_relative
        )
        _write_json(
            reviewer_capability_path,
            {
                "$schema": "https://aoa-agents/schemas/capability-pack.schema.json",
                "id": "route-drift-review.readonly",
                "status": "experimental",
            },
        )
        reviewer_role_ref = _provenance(
            "aoa-agents",
            (
                "agents/roles/reviewer/specializations/route-drift-review/"
                "specialization.json"
            ),
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
            reviewer_realization_path,
            workspace_write=False,
            tool_profile_id=reviewer_tool_profile_id,
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
    role_resolution_ref: ProvenanceRef | None = None
    model_fit_query_ref: ProvenanceRef | None = None
    model_fit_projection_ref: ProvenanceRef | None = None
    if owner_contour:
        holder_ref = {
            "object_id": "actor://fixture-goal-owner",
            "owner_repo": "fixture-target",
            "schema_version": "actor-holder-v1",
            "digest": ZERO_DIGEST,
        }
        goal_ref = {
            "object_id": parent_task_id,
            "owner_repo": "fixture-target",
            "schema_version": "goal-anchor-v1",
            "digest": ZERO_DIGEST,
        }
        obligation_path = tmp_path / "agent-obligation.json"
        obligation = {
            "schema_version": "agent-obligation-v1",
            "obligation_id": "obligation:fixture:bounded-duty",
            "goal_ref": goal_ref,
            "phase": "execution",
            "duty": "Perform one independently held bounded owner duty.",
            "domain_owner": "fixture-target",
            "current_holder": holder_ref,
            "responsibility_boundary": "One bounded owner-local duty and its exact return.",
            "missed_consequence": "The independent duty would remain without a holder.",
            "independence_findings": {
                "positive_signals": ["distinct responsibility holder required"],
                "negative_signals": [],
                "rejected_ordinary_step": "The duty must remain independently addressable.",
            },
            "trigger": {
                "strength": "master_decision",
                "authority_ref": holder_ref,
            },
            "expected_outcomes": ["external_codex_agent_result"],
            "return_owner": holder_ref,
            "lifecycle_posture": "role-continuity",
            "stop_line": "Stop before any undelegated or external effect.",
            "evidence_refs": [],
            "uncertainty": [],
            "next_route": "form_actor",
            "obligation_digest": ZERO_DIGEST,
        }
        obligation["obligation_digest"] = _self_digest(obligation, "obligation_digest")
        _write_json(obligation_path, obligation)
        obligation_ref = _provenance(
            "aoa-agents",
            "obligation:fixture:bounded-duty",
            digest=_digest_path(obligation_path),
            schema_version="agent-obligation-v1",
        )
        owner_source_ref = "a" * 40
        base_role_ref = {
            "owner_repo": "aoa-agents",
            "artifact_ref": f"agents/roles/{role_id}/profile.json",
            "source_ref": owner_source_ref,
            "artifact_digest": "sha256:" + "1" * 64,
            "schema_ref": "schemas/agent-profile.schema.json",
            "schema_version": "aoa_agent_profile_v1",
        }
        tier_ref = {
            "owner_repo": "aoa-agents",
            "artifact_ref": "agents/operating-model/tiers/executor.json",
            "source_ref": owner_source_ref,
            "artifact_digest": "sha256:" + "2" * 64,
            "schema_ref": "schemas/model-tier.schema.json",
            "schema_version": "aoa_model_tier_v1",
        }
        role_resolution_path = tmp_path / "role-resolution.json"
        role_resolution = {
            "schema_version": "aoa_role_resolution_v1",
            "resolution_id": f"role-resolution:{role_id}",
            "owner_repo": "aoa-agents",
            "owner_source_ref": owner_source_ref,
            "role_id": role_id,
            "base_role_ref": base_role_ref,
            "specialization_id": None,
            "specialization_ref": None,
            "tier_id": "executor",
            "tier_ref": tier_ref,
            "capability_pack_refs": [],
            "selection_authority": {
                "semantic_selection_performed": False,
                "model_selection_performed": False,
                "runtime_activation_performed": False,
            },
            "resolution_digest": ZERO_DIGEST,
        }
        role_resolution["resolution_digest"] = _self_digest(
            role_resolution, "resolution_digest"
        )
        _write_json(role_resolution_path, role_resolution)
        role_resolution_ref = _provenance(
            "aoa-agents",
            role_resolution["resolution_id"],
            digest=_digest_path(role_resolution_path),
            source_ref=owner_source_ref,
            schema_ref="skills/aoa-agents-skills/references/role-resolution-v1.schema.json",
            schema_version="aoa_role_resolution_v1",
        )
        dag_path = tmp_path / "task-local-dag.json"
        _write_json(
            dag_path,
            {
                "schema_version": "aoa-task-local-dag-v2",
                "authority": False,
                "plan_id": "dag-0123456789abcdef",
                "request": {"query": "Perform the admitted bounded duty."},
                "source_graph": {
                    "path": "generated/capability_graph.json",
                    "content_hash": "0" * 64,
                },
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
            "dag-0123456789abcdef",
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
            "mandate_ref": f"mandate:fixture:{role_id}",
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
        mandate = {
            "schema_version": "actor-mandate-v1",
            "mandate_id": f"mandate:fixture:{role_id}",
            "obligation_ref": {
                "object_id": obligation["obligation_id"],
                "owner_repo": "aoa-agents",
                "schema_version": "agent-obligation-v1",
                "digest": obligation["obligation_digest"],
            },
            "goal_ref": goal_ref,
            "role_resolution_ref": {
                "object_id": role_resolution["resolution_id"],
                "owner_repo": "aoa-agents",
                "schema_version": "aoa_role_resolution_v1",
                "digest": role_resolution["resolution_digest"],
            },
            "role_binding": {
                "role_id": role_id,
                "specialization_id": None,
                "tier_id": "executor",
                "base_role_ref": base_role_ref,
                "specialization_ref": None,
                "tier_ref": tier_ref,
                "capability_pack_refs": [],
            },
            "identity_posture": "role-continuity",
            "domain_owner": "fixture-target",
            "domain_procedure_refs": [
                {
                    "object_id": procedure_ref.artifact_ref,
                    "owner_repo": procedure_ref.owner_repo,
                    "schema_version": procedure_ref.schema_version,
                    "digest": procedure_ref.artifact_digest,
                }
            ],
            "required_executor_properties": [
                {
                    "property_id": "bounded-owner-work",
                    "requirement": "Perform the exact owner-local procedure.",
                    "verification_route": "Validate the named runtime return.",
                }
            ],
            "model_fit_relation": {
                "task_family": "landing",
                "relation_to_duty": "The bounded duty is one landing-family operation.",
                "relation_authority_ref": holder_ref,
            },
            "authority": {
                "permissions": ["inspect exact inputs"],
                "allowed_effects": [
                    "repo_mutation" if workspace_write else "read_only"
                ],
                "prohibited_effects": ["undelegated external effect"],
                "stop_line": "Stop before any undelegated or external effect.",
            },
            "environment": {
                "sandbox_mode": "workspace-write" if workspace_write else "read-only",
                "workspace_requirement": "Use the exact isolated fixture workspace.",
                "required_tools": [
                    "shell-read",
                    *(["workspace-write"] if workspace_write else []),
                ],
                "required_mcp_servers": [role_mcp] if role_mcp else [],
                "state_root_posture": "Use one explicit runtime-owned state root.",
            },
            "continuity": {
                "posture": "role-continuity",
                "identity_key": f"actor://fixture/{role_id}",
                "state_ref": None,
            },
            "named_outputs": [
                {
                    "name": "external_codex_agent_result",
                    "description": "One exact runtime-owned actor result.",
                    "acceptance_route": "Return through the goal owner.",
                }
            ],
            "return_owner": holder_ref,
            "review_policy": "Review every returned named output.",
            "refusal_policy": "Refuse work outside the mandate.",
            "wake_policy": "Wake the parent at an authority boundary.",
            "review_after": "Review after the external process returns.",
            "uncertainty": [],
            "compiler_authority": {
                "obligation_detection_performed": False,
                "role_selection_performed": False,
                "model_selection_performed": False,
                "runtime_activation_performed": False,
            },
            "mandate_digest": ZERO_DIGEST,
        }
        mandate["mandate_digest"] = _self_digest(mandate, "mandate_digest")
        _write_json(role_path, mandate)
        role_ref = _provenance(
            "aoa-agents",
            mandate["mandate_id"],
            digest=_digest_path(role_path),
            source_ref=owner_source_ref,
            schema_ref="skills/aoa-agents-skills/references/actor-mandate-v1.schema.json",
            schema_version="actor-mandate-v1",
        )
        fixture_extra_inputs.extend(
            (
                ("agent-obligation", obligation_path, obligation_ref),
                ("actor-mandate", role_path, role_ref),
                ("role-resolution", role_resolution_path, role_resolution_ref),
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
        fixture_extra_inputs.append(("workspace-manifest", manifest_path, manifest_ref))
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    continuation_id = f"continuation:fixture:{identity_suffix}"
    incarnation_id = f"incarnation:fixture:{identity_suffix}"
    task_id = f"task:fixture:{identity_suffix}"
    session_id = f"session:fixture:{identity_suffix}"
    summon_outputs = (
        ["external_codex_agent_result", "independent_landing_review"]
        if owner_contour and task_family == "landing_review"
        else ["external_codex_agent_result", "landing_report"]
        if owner_contour
        else ["independent_landing_review"]
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
            if input_id in {"writer-runtime-result", "writer-result"}
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
            transport_preference=("a2a_remote" if owner_contour else "codex_local"),
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
            schema_ref=PREPARER.SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH.as_posix(),
            schema_version="urn:aoa-sdk:a2a:summon-result:v4",
        )
        fixture_extra_inputs.append(
            ("summon-decision", summon_decision_path, summon_decision_ref)
        )
    realization_path = tmp_path / "model-realization.json"
    _write_model_realization(
        realization_path,
        workspace_write=workspace_write,
        role_mcp=role_mcp,
        tool_profile_id=tool_profile_id,
    )
    model_ref = load_model_realization_ref(
        realization_path,
        artifact_ref=("source/model-realizations/" + realization_path.name),
        source_ref="b" * 40,
    )
    if owner_contour:
        model_fit_projection_path = tmp_path / "model-fit-projection.json"
        model_fit_projection = {
            "$schema": "https://schemas.aoa.local/models/model-fit-projection.schema.json",
            "schema_version": "aoa_model_fit_projection_v1",
            "kind": "ModelFitProjection",
            "model_fit_projection_id": "model-fit-projection:fixture/luna/max",
            "subject_realization_ref": model_ref.artifact_ref,
            "consumers": ["aoa-agents", "aoa-sdk", "abyss-stack"],
            "generated_from_claim_refs": [
                "source/model-claims/fixture-landing-fit.json"
            ],
            "study_refs": [],
            "posture": "candidate",
            "effect_family": "candidate" if workspace_write else "read",
            "task_fit": [
                {
                    "task_family": "landing",
                    "claim_posture": "hypothesis",
                    "conditions": ["bounded owner procedure"],
                    "exclusions": ["owner acceptance"],
                    "escalation_required": True,
                }
            ],
            "authority": {
                "informational_only": True,
                "activation_authority": False,
                "proof_authority": False,
                "acceptance_authority": False,
            },
            "freshness": {"status": "current", "review_by": None},
            "must_not_claim": ["owner acceptance or general model benefit"],
            "generated_at": "2026-08-10T00:00:00Z",
        }
        _write_json(model_fit_projection_path, model_fit_projection)
        model_fit_projection_ref = _provenance(
            "aoa-models",
            "generated/model-fit-projections/fixture-luna-max.json",
            digest=_digest_path(model_fit_projection_path),
            source_ref=model_ref.source_ref,
            schema_ref="schemas/model-fit-projection.schema.json",
            schema_version="aoa_model_fit_projection_v1",
        )
        fit_query = {
            "schema_version": "aoa_model_fit_query_v1",
            "task_family": "landing",
            "runtime_product": "codex-cli",
            "runtime_version": "0.147.0",
            "reasoning_effort": "max",
            "sandbox_mode": "workspace-write" if workspace_write else "read-only",
            "required_tools": [
                "shell-read",
                *(["workspace-write"] if workspace_write else []),
            ],
            "required_mcp_servers": [role_mcp] if role_mcp else [],
        }
        fit_candidate = {
            "realization_ref": model_ref.artifact_ref,
            "projection_ref": model_fit_projection_ref.artifact_ref,
            "realization_provenance": model_ref.model_dump(mode="json"),
            "projection_provenance": model_fit_projection_ref.model_dump(mode="json"),
            "fit_evidence_refs": [model_fit_projection_ref.model_dump(mode="json")],
            "model_slug": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "sandbox_mode": fit_query["sandbox_mode"],
            "lifecycle_state": "declared",
            "projection_posture": "candidate",
            "freshness": "current",
            "task_fit": model_fit_projection["task_fit"],
            "limitations": ["fit remains a bounded hypothesis"],
        }
        fit_query_result = {
            "schema_version": "aoa_model_fit_query_result_v2",
            "result_id": "model-fit-query-result:" + "3" * 32,
            "query_digest": _semantic_digest(fit_query),
            "query": fit_query,
            "candidate_count": 1,
            "candidates": [fit_candidate],
            "authority": {
                "informational_only": True,
                "activation_authority": False,
                "routing_authority": False,
                "proof_authority": False,
                "acceptance_authority": False,
            },
            "owner_source_ref": model_ref.source_ref,
            "catalog_digest": "sha256:" + "4" * 64,
            "result_digest": ZERO_DIGEST,
        }
        fit_query_result["result_digest"] = _self_digest(
            fit_query_result, "result_digest"
        )
        model_fit_query_path = tmp_path / "model-fit-query-result.json"
        _write_json(model_fit_query_path, fit_query_result)
        model_fit_query_ref = _provenance(
            "aoa-models",
            fit_query_result["result_id"],
            digest=_digest_path(model_fit_query_path),
            source_ref=model_ref.source_ref,
            schema_ref="schemas/model-fit-query-result.schema.json",
            schema_version="aoa_model_fit_query_result_v2",
        )
        fixture_extra_inputs.extend(
            (
                (
                    "model-fit-query-result",
                    model_fit_query_path,
                    model_fit_query_ref,
                ),
                (
                    "model-fit-projection",
                    model_fit_projection_path,
                    model_fit_projection_ref,
                ),
            )
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
    immutable_inputs.append(
        {
            "input_id": (
                "review-summon-request"
                if task_family == "landing_review"
                else "summon-request"
            ),
            "local_path": str(summon_request_path),
            "provenance": summon_request_ref.model_dump(mode="json"),
        }
    )
    if not omit_historical_reviewer_inputs:
        immutable_inputs.append(
            {
                "input_id": "summon-request-schema",
                "local_path": str(SUMMON_REQUEST_SCHEMA_PATH),
                "provenance": summon_request_schema_ref.model_dump(mode="json"),
            }
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
            dict(item)
            for item in (
                validation_commands
                or (
                    {
                        "command_id": "git-status",
                        "argv": ["git", "status", "--short"],
                        "cwd": ".",
                    },
                )
            )
        ],
        "expected_artifacts": [
            "independent_landing_review"
            if task_family == "landing_review"
            else "landing_report"
        ],
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
    if omit_historical_reviewer_inputs:
        assert summon_decision_ref is not None
        mixed_input_refs = list(plan.scenario_binding.input_refs)
        for ref in (summon_request_ref, summon_decision_ref):
            if ref not in mixed_input_refs:
                mixed_input_refs.append(ref)
        mixed_scenario = plan.scenario_binding.model_copy(
            update={
                "input_refs": tuple(mixed_input_refs),
                "input_artifact_bindings": tuple(
                    item
                    for item in plan.scenario_binding.input_artifact_bindings
                    if item.artifact_kind != "summon_decision"
                ),
            }
        )
        plan = plan.model_copy(
            update={
                "scenario_binding": mixed_scenario,
                "plan_digest": ZERO_DIGEST,
            }
        )
        plan = plan.model_copy(
            update={"plan_digest": canonical_digest(plan, exclude={"plan_digest"})}
        )
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, plan.model_dump(mode="json"))
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
    binding_kwargs = {
        "binding_id": f"binding:fixture:{identity_suffix}",
        "incarnation_id": incarnation_id,
        "causation_id": f"causation:fixture:{identity_suffix}",
        "trace_id": f"trace:fixture:{identity_suffix}",
        "task_request_ref": summon_request_ref,
        "role_id": role_id,
        "role_contract_ref": role_ref,
        "model_realization_ref": model_ref,
        "workspace_source_ref": workspace_ref,
        "permission_posture": IncarnationPermissionPosture(
            sandbox_mode="workspace_write" if workspace_write else "read_only",
            approval_policy="never",
            allowed_effect_classes=(
                ("repo_mutation",) if workspace_write else ("read_only",)
            ),
            network_access="disabled",
        ),
        "tool_profile": IncarnationToolProfile(
            profile_id=tool_profile_id
            or (
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
            required_mcp_server_ids=((role_mcp,) if role_mcp is not None else ()),
        ),
        "usage_metering": IncarnationUsageMetering(
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
        "stop_conditions": stop_conditions,
        "expected_result_schema_ref": report_schema_ref,
        "continuation": continuation,
        "wake_policy": wake_policy,
        "provenance": _provenance(
            "aoa-sdk",
            f"bindings/fixture-{identity_suffix}.json",
            digest=ZERO_DIGEST,
        ),
    }
    owner_request_binding = None
    if owner_contour:
        assert role_resolution_ref is not None
        assert model_fit_query_ref is not None
        assert model_fit_projection_ref is not None
        owner_request_binding = build_agent_incarnation_binding_v2(
            plan,
            **binding_kwargs,
            agent_obligation_ref=ContentRef(
                object_id=obligation["obligation_id"],
                owner_repo="aoa-agents",
                schema_version="agent-obligation-v1",
                digest=obligation["obligation_digest"],
            ),
            actor_mandate_ref=ContentRef(
                object_id=mandate["mandate_id"],
                owner_repo="aoa-agents",
                schema_version="actor-mandate-v1",
                digest=mandate["mandate_digest"],
            ),
            role_resolution_ref=ContentRef(
                object_id=role_resolution["resolution_id"],
                owner_repo="aoa-agents",
                schema_version="aoa_role_resolution_v1",
                digest=role_resolution["resolution_digest"],
            ),
            model_fit_query_result_ref=ContentRef(
                object_id=fit_query_result["result_id"],
                owner_repo="aoa-models",
                schema_version="aoa_model_fit_query_result_v2",
                digest=fit_query_result["result_digest"],
            ),
            model_fit_projection_ref=model_fit_projection_ref,
        )
    if owner_binding_v1 or not owner_contour:
        binding = build_agent_incarnation_binding(plan, **binding_kwargs)
    else:
        binding = owner_request_binding
    binding_path = tmp_path / "binding.json"
    _write_json(binding_path, binding.model_dump(mode="json"))
    owner_request_binding_path = binding_path
    if owner_binding_v1:
        assert owner_request_binding is not None
        owner_request_binding_path = tmp_path / "owner-request-binding-v2.json"
        _write_json(
            owner_request_binding_path,
            owner_request_binding.model_dump(mode="json"),
        )
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
                    "artifact_ref": "skills/aoa-summon/references/summon-request-v4.schema.json",
                    "source_ref": "1458393baa90178aae63f1841e3bd58139c13232",
                    "schema_version": "summon-request-v4",
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
        **(
            {"workspace_projection_seed": dict(workspace_projection_seed)}
            if workspace_projection_seed is not None
            else {}
        ),
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
        assert role_resolution_ref is not None
        assert model_fit_query_ref is not None
        assert model_fit_projection_ref is not None
        assert SUMMON_COMPILER is not None
        owner_execution_request = SUMMON_COMPILER.compile_external_execution_request(
            request_ref=(f"task://fixture/{identity_suffix}/owner-execution-request"),
            runtime_interface="abyss_stack_external_codex_agent_v1",
            return_event_object_id=(
                "mechanics/governed-execution/parts/external-codex-agent/"
                "schemas/external-codex-event.schema.json"
            ),
            obligation_path=obligation_path,
            mandate_path=role_path,
            role_resolution_path=role_resolution_path,
            model_fit_query_result_path=model_fit_query_path,
            model_fit_projection_path=model_fit_projection_path,
            task_local_dag_path=dag_path,
            incarnation_binding_path=owner_request_binding_path,
            sdk_summon_request_path=summon_request_path,
            sdk_summon_decision_path=summon_decision_path,
            run_plan_path=plan_path,
            runtime_launch_path=launch_path,
            runtime_task_path=task_path,
            responsibility_transfer_path=transfer_path,
            domain_procedure_paths=[procedure_path],
            return_event_schema_path=RUNTIME.EVENT_SCHEMA_PATH,
        )
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


def _wait_terminal(
    runtime: Any, session_id: str, *, timeout: float = 10
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = runtime.status(session_id)
        if state["status"] != "running":
            return state
        time.sleep(0.05)
    state = runtime.status(session_id)
    if state["status"] != "running":
        return state
    raise AssertionError(
        f"external Codex fixture did not stop: {state}"
    )


def test_wait_terminal_accepts_transition_at_timeout_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter((0.0, 0.0, 1.0))
    states = iter(({"status": "running"}, {"status": "authority_blocked"}))

    class BoundaryRuntime:
        def status(self, session_id: str) -> dict[str, str]:
            assert session_id == "session:boundary"
            return next(states)

    monkeypatch.setattr(time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    terminal = _wait_terminal(BoundaryRuntime(), "session:boundary", timeout=1)

    assert terminal["status"] == "authority_blocked"


def test_actor_manifest_retries_one_transient_descriptor_inventory_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"schema_version": "test-actor-manifest"}
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            raise RUNTIME.ProjectionError(
                "actor projection file changed while being inventoried: actor-output/result.json"
            )
        return expected

    monkeypatch.setattr(RUNTIME, "build_actor_manifest_from_descriptor", fake_manifest)
    monkeypatch.setattr(RUNTIME.time, "sleep", sleeps.append)

    observed = RUNTIME._checked_actor_manifest(
        tmp_path,
        source_manifest_digest="sha256:" + "0" * 64,
        source_git_head="a" * 40,
        projection_fd=7,
    )

    assert observed == expected
    assert len(calls) == 2
    assert sleeps == [RUNTIME.ACTOR_MANIFEST_TRANSIENT_RETRY_SECONDS]


def test_actor_manifest_retries_transient_directory_enumeration_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {"schema_version": "test-actor-manifest"}
    calls: list[int] = []

    def fake_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        if len(calls) == 1:
            raise RUNTIME.ProjectionError(
                "actor projection directory disappeared before enumeration: "
                ".pytest_cache/v/cache"
            )
        return expected

    monkeypatch.setattr(RUNTIME, "build_actor_manifest_from_descriptor", fake_manifest)
    monkeypatch.setattr(RUNTIME.time, "sleep", lambda _: None)

    observed = RUNTIME._checked_actor_manifest(
        tmp_path,
        source_manifest_digest="sha256:" + "0" * 64,
        source_git_head="a" * 40,
        projection_fd=7,
    )

    assert observed == expected
    assert len(calls) == 2


def test_actor_manifest_does_not_retry_other_directory_enumeration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        raise RUNTIME.ProjectionError("actor projection cannot enumerate its tree")

    monkeypatch.setattr(RUNTIME, "build_actor_manifest_from_descriptor", fake_manifest)
    monkeypatch.setattr(RUNTIME.time, "sleep", sleeps.append)

    with pytest.raises(
        RUNTIME.ExternalCodexRuntimeError,
        match="cannot enumerate its tree",
    ) as exc_info:
        RUNTIME._checked_actor_manifest(
            tmp_path,
            source_manifest_digest="sha256:" + "0" * 64,
            source_git_head="a" * 40,
            projection_fd=7,
        )

    assert exc_info.value.code == "actor_projection_observation_gap"
    assert len(calls) == 1
    assert sleeps == []


def test_actor_manifest_does_not_retry_nontransient_projection_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_manifest(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(1)
        raise RUNTIME.ProjectionError(
            "actor projection does not admit special entry: unsafe.pipe"
        )

    monkeypatch.setattr(RUNTIME, "build_actor_manifest_from_descriptor", fake_manifest)
    monkeypatch.setattr(RUNTIME.time, "sleep", sleeps.append)

    with pytest.raises(
        RUNTIME.ExternalCodexRuntimeError,
        match="does not admit special entry",
    ) as exc_info:
        RUNTIME._checked_actor_manifest(
            tmp_path,
            source_manifest_digest="sha256:" + "0" * 64,
            source_git_head="a" * 40,
            projection_fd=7,
        )

    assert exc_info.value.code == "actor_projection_observation_gap"
    assert len(calls) == 1
    assert sleeps == []


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
        lambda supervisor_pid, codex_pid: reaps.append((supervisor_pid, codex_pid)),
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
    monkeypatch.setattr(
        RUNTIME.os, "waitpid", lambda pid, flags: waits.append((pid, flags))
    )
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

    SUPERVISOR._write_process_identity_receipt(
        receipt_path,
        FakeProcess(),
    )

    assert json.loads(receipt_path.read_text(encoding="utf-8")) == {
        "schema_version": "abyss_stack_external_codex_process_identity_v2",
        "supervisor_pid": 31337,
        "supervisor_start_ticks": 111,
        "launcher_pid": 4242,
        "launcher_start_ticks": 222,
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

    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [str(executable), str(output)],
        expected_digest,
    )

    assert gate_write_fd is None
    assert process.wait(timeout=5) == 0
    assert output.read_text(encoding="utf-8") == "verified-open-inode\n"


def test_supervisor_mount_wrapper_masks_target_before_releasing_command(
    tmp_path: Path,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    target = metadata / "repository-config"
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "observed.txt"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("[core]\n\tbare = false\n", encoding="utf-8")
    masks = ((str(sanitized), str(target), _digest_path(sanitized)),)
    private_directory_views = tuple(
        RUNTIME._private_directory_views(
            [
                {
                    "source": str(sanitized),
                    "target": str(target),
                    "digest": _digest_path(sanitized),
                }
            ]
        )
    )

    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [
            str(executable),
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[2]).write_text(pathlib.Path(sys.argv[1]).read_text())",
            str(target),
            str(output),
        ],
        _digest_path(executable),
        mount_wrapper=str(wrapper),
        mount_wrapper_digest=_digest_path(wrapper),
        mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
        private_directory_views=private_directory_views,
        read_only_masks=masks,
    )

    assert gate_write_fd is not None
    os.write(gate_write_fd, b"1")
    os.close(gate_write_fd)
    assert process.wait(timeout=5) == 0
    assert output.read_text(encoding="utf-8") == sanitized.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8") == "credential-marker\n"


def test_supervisor_mount_mask_preserves_verified_bytes_after_source_mutation(
    tmp_path: Path,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    target = metadata / "repository-config"
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "observed.txt"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("verified-safe-bytes\n", encoding="utf-8")
    expected_digest = _digest_path(sanitized)
    masks = ((str(sanitized), str(target), expected_digest),)
    private_directory_views = tuple(
        RUNTIME._private_directory_views(
            [
                {
                    "source": str(sanitized),
                    "target": str(target),
                    "digest": expected_digest,
                }
            ]
        )
    )

    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [
            str(executable),
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[2]).write_text(pathlib.Path(sys.argv[1]).read_text())",
            str(target),
            str(output),
        ],
        _digest_path(executable),
        mount_wrapper=str(wrapper),
        mount_wrapper_digest=_digest_path(wrapper),
        mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
        private_directory_views=private_directory_views,
        read_only_masks=masks,
        mount_setup_callback=lambda: sanitized.write_text(
            "changed-after-readiness\n",
            encoding="utf-8",
        ),
    )

    assert gate_write_fd is not None
    os.write(gate_write_fd, b"1")
    os.close(gate_write_fd)
    assert process.wait(timeout=5) == 0
    assert output.read_text(encoding="utf-8") == "verified-safe-bytes\n"
    assert sanitized.read_text(encoding="utf-8") == "changed-after-readiness\n"


def test_supervisor_rejects_private_view_target_replaced_after_readiness(
    tmp_path: Path,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    moved_metadata = tmp_path / "moved-metadata"
    target = metadata / "repository-config"
    moved_target = moved_metadata / target.name
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "observed.txt"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("safe\n", encoding="utf-8")
    masks = ((str(sanitized), str(target), _digest_path(sanitized)),)
    private_directory_views = tuple(
        RUNTIME._private_directory_views(
            [
                {
                    "source": str(sanitized),
                    "target": str(target),
                    "digest": _digest_path(sanitized),
                }
            ]
        )
    )

    def replace_during_setup() -> None:
        metadata.rename(moved_metadata)
        metadata.mkdir()
        target.write_text("replacement-marker\n", encoding="utf-8")

    with pytest.raises(
        SUPERVISOR.SupervisorError,
        match="did not attach exact views",
    ):
        SUPERVISOR._launch_verified_command(
            [
                str(executable),
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')",
                str(output),
            ],
            _digest_path(executable),
            mount_wrapper=str(wrapper),
            mount_wrapper_digest=_digest_path(wrapper),
            mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
            private_directory_views=private_directory_views,
            read_only_masks=masks,
            mount_setup_callback=replace_during_setup,
        )

    assert not output.exists()
    assert moved_target.read_text(encoding="utf-8") == "credential-marker\n"
    assert target.read_text(encoding="utf-8") == "replacement-marker\n"


def test_supervisor_masks_both_inode_and_live_path_across_post_open_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    moved_metadata = tmp_path / "metadata-moved-race"
    target = metadata / "repository-config"
    moved_target = moved_metadata / target.name
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "observed.txt"
    target.write_text("original-secret\n", encoding="utf-8")
    sanitized.write_text("safe\n", encoding="utf-8")
    expected_digest = _digest_path(sanitized)
    masks = ((str(sanitized), str(target), expected_digest),)
    private_directory_views = tuple(
        RUNTIME._private_directory_views(
            [
                {
                    "source": str(sanitized),
                    "target": str(target),
                    "digest": expected_digest,
                }
            ]
        )
    )
    launcher_source = SUPERVISOR.MOUNT_LAUNCHER_PATH.read_text(encoding="utf-8")
    race_point = (
        "            command_target_fd = "
        "_command_visible_target_descriptor(view, target_fd)\n"
    )
    assert launcher_source.count(race_point) == 1
    race_launcher = tmp_path / "race-mount-launcher.py"
    race_launcher.write_text(
        launcher_source.replace(
            race_point,
            race_point
            + "            race_target = Path(str(view['target']))\n"
            + "            race_moved = race_target.with_name(race_target.name + '-moved-race')\n"
            + "            race_target.rename(race_moved)\n"
            + "            race_target.mkdir()\n"
            + "            (race_target / 'repository-config').write_text('replacement-secret\\n')\n",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(SUPERVISOR, "MOUNT_LAUNCHER_PATH", race_launcher)

    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [
            str(executable),
            "-c",
            (
                "import pathlib,sys; "
                "current=pathlib.Path(sys.argv[1]).read_text().strip(); "
                "moved=pathlib.Path(sys.argv[2]).read_text().strip(); "
                "pathlib.Path(sys.argv[3]).write_text(current + '|' + moved)"
            ),
            str(target),
            str(moved_target),
            str(output),
        ],
        _digest_path(executable),
        mount_wrapper=str(wrapper),
        mount_wrapper_digest=_digest_path(wrapper),
        mount_launcher_digest=_digest_path(race_launcher),
        private_directory_views=private_directory_views,
        read_only_masks=masks,
    )

    assert gate_write_fd is not None
    os.write(gate_write_fd, b"1")
    os.close(gate_write_fd)
    assert process.wait(timeout=5) == 0
    assert output.read_text(encoding="utf-8") == "safe|safe"
    assert target.read_text(encoding="utf-8") == "replacement-secret\n"
    assert moved_target.read_text(encoding="utf-8") == "original-secret\n"


def test_supervisor_rejects_private_view_replaced_before_exact_open(
    tmp_path: Path,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    target = metadata / "repository-config"
    sanitized = tmp_path / "sanitized-config"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("safe\n", encoding="utf-8")
    masks = ((str(sanitized), str(target), _digest_path(sanitized)),)
    private_directory_views = tuple(
        RUNTIME._private_directory_views(
            [
                {
                    "source": str(sanitized),
                    "target": str(target),
                    "digest": _digest_path(sanitized),
                }
            ]
        )
    )
    moved_metadata = tmp_path / "moved-metadata"
    metadata.rename(moved_metadata)
    metadata.mkdir()
    target.write_text("replacement-marker\n", encoding="utf-8")

    with pytest.raises(
        SUPERVISOR.SupervisorError,
        match="mount launcher did not become ready",
    ):
        SUPERVISOR._launch_verified_command(
            [str(executable), "-c", "raise SystemExit(99)"],
            _digest_path(executable),
            mount_wrapper=str(wrapper),
            mount_wrapper_digest=_digest_path(wrapper),
            mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
            private_directory_views=private_directory_views,
            read_only_masks=masks,
        )

    assert (moved_metadata / target.name).read_text(encoding="utf-8") == (
        "credential-marker\n"
    )
    assert target.read_text(encoding="utf-8") == "replacement-marker\n"


def test_supervisor_refuses_launch_gate_after_parent_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate_read_fd, gate_write_fd = os.pipe()
    monkeypatch.setattr(SUPERVISOR, "_termination_signal", signal.SIGTERM)

    with pytest.raises(
        SUPERVISOR.SupervisorError,
        match="parent died before launch gate release",
    ):
        SUPERVISOR._release_launch_gate(
            gate_write_fd,
            parent_pid=os.getppid(),
        )

    os.set_blocking(gate_read_fd, False)
    with pytest.raises(BlockingIOError):
        os.read(gate_read_fd, 1)
    os.close(gate_write_fd)
    assert os.read(gate_read_fd, 1) == b""
    os.close(gate_read_fd)


def _terminate_gated_test_wrapper(process: subprocess.Popen[bytes]) -> int:
    """Stop the direct-launch test tree without relying on supervisor adoption."""

    descendants = SUPERVISOR._descendants(process.pid)
    assert SUPERVISOR._signal_descendants(descendants, signal.SIGTERM)
    process.terminate()
    try:
        return_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        return_code = process.wait(timeout=5)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and any(
        SUPERVISOR._identity_matches(identity) for identity in descendants.values()
    ):
        time.sleep(0.01)
    live = {
        pid: identity
        for pid, identity in descendants.items()
        if SUPERVISOR._identity_matches(identity)
    }
    if live:
        assert SUPERVISOR._signal_descendants(live, signal.SIGKILL)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and any(
        SUPERVISOR._identity_matches(identity) for identity in live.values()
    ):
        time.sleep(0.01)
    assert not any(SUPERVISOR._identity_matches(identity) for identity in live.values())
    return return_code


def test_supervisor_kills_gated_wrapper_before_abort_fd_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    target = metadata / "repository-config"
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "must-not-exist.txt"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("safe\n", encoding="utf-8")
    mask_entry = {
        "source": str(sanitized),
        "target": str(target),
        "digest": _digest_path(sanitized),
    }
    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [
            str(executable),
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('launched')",
            str(output),
        ],
        _digest_path(executable),
        mount_wrapper=str(wrapper),
        mount_wrapper_digest=_digest_path(wrapper),
        mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
        private_directory_views=tuple(RUNTIME._private_directory_views([mask_entry])),
        read_only_masks=((str(sanitized), str(target), _digest_path(sanitized)),),
    )
    assert gate_write_fd is not None
    monkeypatch.setattr(SUPERVISOR, "_termination_signal", signal.SIGTERM)

    with pytest.raises(SUPERVISOR.SupervisorError):
        SUPERVISOR._release_launch_gate(
            gate_write_fd,
            parent_pid=os.getppid(),
        )
    time.sleep(0.1)
    assert process.poll() is None
    assert not output.exists()
    assert _terminate_gated_test_wrapper(process) != 0
    os.close(gate_write_fd)
    assert not output.exists()


def test_supervisor_gate_eof_cannot_release_mount_wrapper(tmp_path: Path) -> None:
    executable = Path(sys.executable).resolve()
    wrapper = Path("/usr/bin/bwrap")
    metadata = tmp_path / "metadata"
    metadata.mkdir()
    target = metadata / "repository-config"
    sanitized = tmp_path / "sanitized-config"
    output = tmp_path / "must-not-exist.txt"
    target.write_text("credential-marker\n", encoding="utf-8")
    sanitized.write_text("safe\n", encoding="utf-8")
    mask_entry = {
        "source": str(sanitized),
        "target": str(target),
        "digest": _digest_path(sanitized),
    }
    process, gate_write_fd = SUPERVISOR._launch_verified_command(
        [
            str(executable),
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('launched')",
            str(output),
        ],
        _digest_path(executable),
        mount_wrapper=str(wrapper),
        mount_wrapper_digest=_digest_path(wrapper),
        mount_launcher_digest=_digest_path(SUPERVISOR.MOUNT_LAUNCHER_PATH),
        private_directory_views=tuple(RUNTIME._private_directory_views([mask_entry])),
        read_only_masks=((str(sanitized), str(target), _digest_path(sanitized)),),
    )
    assert gate_write_fd is not None

    os.close(gate_write_fd)
    time.sleep(0.1)
    assert process.poll() is None
    assert not output.exists()
    assert _terminate_gated_test_wrapper(process) != 0
    assert not output.exists()


def test_supervisor_abort_keeps_gate_open_when_cleanup_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate_read_fd, gate_write_fd = os.pipe()
    monkeypatch.setattr(
        SUPERVISOR, "_cleanup_descendants", lambda *_args, **_kwargs: False
    )

    assert (
        SUPERVISOR._abort_gated_launch(
            object(),
            gate_write_fd,
            term_timeout_seconds=0.0,
            kill_timeout_seconds=0.0,
        )
        is False
    )

    os.set_blocking(gate_read_fd, False)
    with pytest.raises(BlockingIOError):
        os.read(gate_read_fd, 1)
    os.close(gate_write_fd)
    os.close(gate_read_fd)


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
        actor_git_mask: Mapping[str, Any] | None = None,
        mount_wrapper_digest: str | None = None,
        mount_launcher_digest: str | None = None,
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
            actor_git_mask=actor_git_mask,
            mount_wrapper_digest=mount_wrapper_digest,
            mount_launcher_digest=mount_launcher_digest,
        )

    monkeypatch.setattr(runtime, "_containment_command", replace_before_supervisor_open)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.preflight(fixture["launch_path"])

    assert exc_info.value.code == "codex_preflight_failed"


def test_preflight_exercises_masked_nested_codex_sandbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    original_containment_command = runtime._containment_command
    observed: list[tuple[list[str], Mapping[str, Any], tuple[str, ...]]] = []

    def observe_containment(
        command: Any,
        *,
        executable_digest: str,
        identity_path: Path | None = None,
        actor_git_mask: Mapping[str, Any] | None = None,
        mount_wrapper_digest: str | None = None,
        mount_launcher_digest: str | None = None,
    ) -> list[str]:
        if actor_git_mask is not None:
            execution_root = Path(command[command.index("-C") + 1])
            observed.append(
                (
                    list(command),
                    actor_git_mask,
                    tuple(
                        name
                        for name in (".agents", ".codex", ".git")
                        if (execution_root / name).is_dir()
                    ),
                )
            )
        return original_containment_command(
            command,
            executable_digest=executable_digest,
            identity_path=identity_path,
            actor_git_mask=actor_git_mask,
            mount_wrapper_digest=mount_wrapper_digest,
            mount_launcher_digest=mount_launcher_digest,
        )

    monkeypatch.setattr(runtime, "_containment_command", observe_containment)

    runtime.preflight(fixture["launch_path"])

    assert len(observed) == 1
    command, actor_git_mask, protected_mountpoints = observed[0]
    assert "sandbox" in command
    assert command[command.index("-P") + 1] == "aoa_external_actor"
    assert "--strict-config" not in command
    assert "--disable" in command
    assert command[command.index("--disable") + 1] == "use_legacy_landlock"
    permission_override = next(
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "-c"
        and command[index + 1].startswith("permissions.aoa_external_actor=")
    )
    assert f'"{fixture["launch"]["codex_executable"]}"="read"' in permission_override
    assert '":workspace_roots"="write"' in permission_override
    assert protected_mountpoints == (".agents", ".codex", ".git")
    assert actor_git_mask["masks"]
    assert actor_git_mask["private_directory_views"]


def test_containment_rejects_mount_wrapper_drift_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path / "fixture")
    runtime = fixture["runtime"]
    wrapper = tmp_path / "bwrap"
    wrapper.write_bytes(Path("/usr/bin/bwrap").read_bytes())
    wrapper.chmod(0o700)
    preflight_digest = _digest_path(wrapper)
    workspace = Path(fixture["workspace"])
    actor_git_mask = RUNTIME._prepare_actor_git_mask(
        workspace,
        tmp_path / "mask-scratch",
    )
    replacement = tmp_path / "replacement-bwrap"
    replacement.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    replacement.chmod(0o700)
    replacement.replace(wrapper)
    monkeypatch.setattr(RUNTIME, "MOUNT_WRAPPER_PATH", wrapper)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime._containment_command(
            [fixture["launch"]["codex_executable"], "--version"],
            executable_digest=fixture["launch"]["codex_executable_digest"],
            actor_git_mask=actor_git_mask,
            mount_wrapper_digest=preflight_digest,
            mount_launcher_digest=_digest_path(RUNTIME.MOUNT_LAUNCHER_PATH),
        )

    assert exc_info.value.code == "actor_git_mask_unavailable"


def test_containment_rejects_mount_launcher_drift_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path / "fixture")
    runtime = fixture["runtime"]
    launcher = tmp_path / "mount-launcher.py"
    launcher.write_text("ORIGINAL = True\n", encoding="utf-8")
    preflight_digest = _digest_path(launcher)
    workspace = Path(fixture["workspace"])
    actor_git_mask = RUNTIME._prepare_actor_git_mask(
        workspace,
        tmp_path / "mask-scratch",
    )
    launcher.write_text("REPLACED = True\n", encoding="utf-8")
    monkeypatch.setattr(RUNTIME, "MOUNT_LAUNCHER_PATH", launcher)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime._containment_command(
            [fixture["launch"]["codex_executable"], "--version"],
            executable_digest=fixture["launch"]["codex_executable_digest"],
            actor_git_mask=actor_git_mask,
            mount_wrapper_digest=_digest_path(RUNTIME.MOUNT_WRAPPER_PATH),
            mount_launcher_digest=preflight_digest,
        )

    assert exc_info.value.code == "actor_git_mask_unavailable"


def test_worker_rejects_mount_wrapper_drift_after_durable_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    original_preflight = runtime._codex_preflight
    calls = [0]

    def drift_after_admission(*args: Any, **kwargs: Any) -> dict[str, Any]:
        observed = original_preflight(*args, **kwargs)
        calls[0] += 1
        if calls[0] > 1:
            observed = {**observed, "mount_wrapper_digest": ZERO_DIGEST}
        return observed

    monkeypatch.setattr(runtime, "_codex_preflight", drift_after_admission)

    runtime.start(fixture["launch_path"])
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "mount_wrapper_drift"


def test_worker_rejects_mount_launcher_drift_after_durable_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    original_preflight = runtime._codex_preflight
    calls = [0]

    def drift_after_admission(*args: Any, **kwargs: Any) -> dict[str, Any]:
        observed = original_preflight(*args, **kwargs)
        calls[0] += 1
        if calls[0] > 1:
            observed = {**observed, "mount_launcher_digest": ZERO_DIGEST}
        return observed

    monkeypatch.setattr(runtime, "_codex_preflight", drift_after_admission)

    runtime.start(fixture["launch_path"])
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "mount_launcher_drift"


def test_existing_v2_state_without_mount_wrapper_digest_remains_readable(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    terminal = _wait_terminal(runtime, fixture["session_id"])
    assert terminal["status"] == "completed"
    state_path = runtime._state_path(fixture["session_id"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["preflight"].pop("mount_wrapper_digest")
    state["preflight"].pop("mount_launcher_digest")
    _write_json(state_path, state)

    observed = runtime.status(fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert observed["status"] == "completed"
    assert result is not None and result["status"] == "completed"


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
        "schema_version": "abyss_stack_external_codex_process_identity_v2",
        "supervisor_pid": 31337,
        "supervisor_start_ticks": 111,
        "launcher_pid": 4242,
        "launcher_start_ticks": 222,
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
            "schema_version": "abyss_stack_external_codex_process_identity_v2",
            "supervisor_pid": 31337,
            "supervisor_start_ticks": 111,
            "launcher_pid": 4242,
            "launcher_start_ticks": 222,
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


def test_preflight_and_separate_process_return_structured_result(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    _git(
        fixture["workspace"],
        "config",
        "http.https://example.invalid/.extraHeader",
        "Authorization: Bearer FAKE_REPOSITORY_CONFIG_MARKER",
    )
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
    assert result["schema_version"] == "abyss_stack_external_codex_result_v2"
    for required_ref in (
        "actor_baseline_manifest_ref",
        "actor_final_manifest_ref",
        "actor_delta_ref",
        "source_manifest_before_ref",
        "source_manifest_after_ref",
        "source_manifest_final_ref",
    ):
        assert isinstance(result[required_ref], dict)
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
    assert (
        argv[argv.index("--executable-digest") + 1]
        == (fixture["launch"]["codex_executable_digest"])
    )
    assert argv[argv.index("--mount-wrapper") + 1] == "/usr/bin/bwrap"
    assert "--workspace-fd" in argv
    assert argv[argv.index("--workspace-coordinate") + 1] == str(ACTOR_EXECUTION_ROOT)
    assert "--private-directory-view" not in argv
    assert "--read-only-mask" not in argv
    assert "/usr/bin/unshare" not in argv
    assert "/usr/bin/setpriv" not in argv
    assert "exec" in argv
    assert argv[argv.index("--disable") + 1] == "multi_agent"
    assert "use_linux_sandbox_bwrap" not in argv
    assert "use_legacy_landlock" in argv
    assert "spawn_agent" not in argv
    assert "-s" not in argv
    execution_root = Path(invocation["execution_root"])
    actor_projection = Path(state["actor_projection_path"])
    assert execution_root == ACTOR_EXECUTION_ROOT
    assert actor_projection != execution_root
    assert (actor_projection / ".git").is_dir()
    assert argv[argv.index("-C") + 1] == str(execution_root)
    assert execution_root != fixture["workspace"]
    assert "--skip-git-repo-check" not in argv
    config_overrides = [
        argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "-c"
    ]
    assert 'default_permissions="aoa_external_actor"' in config_overrides
    permission_override = next(
        value
        for value in config_overrides
        if value.startswith("permissions.aoa_external_actor=")
    )
    sanitized_config = (
        Path(state["actor_projection_path"]).parent
        / "attempts"
        / "001"
        / "scratch"
        / "actor-git-config"
    )
    assert f'"{sanitized_config}"="read"' in permission_override
    assert f'"{fixture["launch"]["codex_executable"]}"="read"' in permission_override
    assert '":workspace_roots"="read"' in permission_override
    assert str(execution_root) not in permission_override
    assert '":minimal"="read"' in permission_override
    controller_original_root = (
        runtime._session_dir(fixture["session_id"]) / "inputs" / "controller-immutable"
    )
    assert f'"{controller_original_root}"="deny"' in permission_override
    assert str(fixture["workspace"]) not in permission_override
    assert sanitized_config.is_file()
    assert "FAKE_REPOSITORY_CONFIG_MARKER" not in sanitized_config.read_text(
        encoding="utf-8"
    )
    process_identity = json.loads(
        Path(identity_ref["artifact_ref"]).read_text(encoding="utf-8")
    )
    assert process_identity["schema_version"] == (
        "abyss_stack_external_codex_process_identity_v2"
    )
    assert process_identity["launcher_pid"] != process_identity["codex_pid"]
    prompt = (
        Path(state["actor_projection_path"]).parent / "attempts" / "001" / "prompt.txt"
    ).read_text(encoding="utf-8")
    assert f'"target_workspace": "{execution_root}"' in prompt
    assert str(fixture["workspace"]) not in prompt
    assert str(fixture["workspace"]) not in "\0".join(argv)
    assert f'"codex_execution_root": "{execution_root}"' in prompt
    assert '"target_workspace_access": "read_only"' in prompt
    assert result["source_manifest_match"] is True
    actor_baseline = json.loads(
        Path(result["actor_baseline_manifest_ref"]["artifact_ref"]).read_text(
            encoding="utf-8"
        )
    )
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", actor_baseline["private_git_digest"])
    for immutable_input in state["materialized_task_inputs"]:
        immutable_path = Path(immutable_input["path"])
        assert immutable_path.parent.name == "immutable"
        assert str(fixture["workspace"]) not in immutable_path.read_text(
            encoding="utf-8"
        )
        assert f'"{immutable_path}"="read"' in permission_override
    assert result["actor_delta_ref"]["artifact_digest"] == _digest_path(
        Path(result["actor_delta_ref"]["artifact_ref"])
    )
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
    assert (
        execution_schema["properties"]["incarnation_id"]["const"]
        == (state["incarnation_id"])
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
        assert (
            re.fullmatch(
                evidence_pattern,
                "immutable:not-materialized#objective",
            )
            is None
        )
    process_event = next(
        item
        for item in events
        if item["event_type"] == "external_agent.process_started"
    )
    assert (
        process_event["payload"]["supervisor_pid"]
        != (process_event["payload"]["codex_pid"])
    )
    assert process_event["payload"]["codex_pid"] != os.getpid()
    assert (
        json.loads(PROFILE_PATH.read_text())["boundaries"][
            "uses_builtin_codex_subagents"
        ]
        is False
    )

    legacy_result = dict(result)
    legacy_result["schema_version"] = "abyss_stack_external_codex_result_v1"
    for legacy_optional in (
        "actor_projection_path",
        "actor_baseline_manifest_ref",
        "actor_final_manifest_ref",
        "actor_delta_ref",
        "source_manifest_before_ref",
        "source_manifest_after_ref",
        "source_manifest_final_ref",
        "source_manifest_match",
    ):
        legacy_result.pop(legacy_optional)
    RUNTIME.validate_json(
        legacy_result,
        PART_ROOT / "schemas/external-codex-result.schema.json",
        label="legacy external Codex result",
    )


def test_source_race_fails_before_inference_and_persists_no_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, exact_baseline=True)
    runtime = fixture["runtime"]
    original_manifest = RUNTIME.build_workspace_manifest
    calls = 0

    def raced_manifest(path: str | Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        manifest = original_manifest(path)
        manifest = json.loads(json.dumps(manifest))
        if calls == 2:
            manifest["workspace_identity"]["root"]["st_ino"] += 1
        return manifest

    monkeypatch.setattr(RUNTIME, "build_workspace_manifest", raced_manifest)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.start(fixture["launch_path"])

    assert exc_info.value.code == "workspace_source_race"
    assert calls >= 2
    session_dir = runtime._session_dir(fixture["session_id"])
    assert not (session_dir / "state.json").exists()
    assert not (session_dir / "attempts").exists()
    assert not (session_dir / "actor-baseline-manifest.json").exists()
    assert not (session_dir / "actor-workspace").exists()


def test_child_uses_open_projection_inode_and_closeout_rejects_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, objective_marker="FAKE_REQUIRE_PRIVATE_GIT")
    runtime = fixture["runtime"]
    original_popen = RUNTIME.subprocess.Popen

    def replace_projection_before_supervisor(
        command: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if (
            isinstance(command, list)
            and len(command) > 2
            and command[1] == str(SUPERVISOR_PATH)
            and "--workspace-fd" in command
        ):
            state = runtime._load_state(fixture["session_id"])
            projection = Path(state["actor_projection_path"])
            retired = projection.with_name("actor-workspace-open-inode")
            projection.rename(retired)
            projection.mkdir(mode=0o700)
            (projection / "README.md").write_text(
                "replacement pathname tree\n",
                encoding="utf-8",
            )
        return original_popen(command, *args, **kwargs)

    monkeypatch.setattr(
        RUNTIME.subprocess, "Popen", replace_projection_before_supervisor
    )
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])
    state = runtime._load_state(fixture["session_id"])
    replacement = Path(state["actor_projection_path"])
    retired = replacement.with_name("actor-workspace-open-inode")

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "actor_projection_coordinate_drift"
    assert result["exit_code"] == 0
    assert any(
        item.get("validation_command_id") == "git-status"
        and isinstance(item.get("workspace_manifest_digest"), str)
        for item in result["executed_commands"]
    )
    assert (retired / ".git" / "HEAD").is_file()
    assert not (replacement / ".git").exists()
    assert replacement.joinpath("README.md").read_text(encoding="utf-8") == (
        "replacement pathname tree\n"
    )


def test_projection_publication_swap_cannot_become_durable_actor_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    original_materialize = RUNTIME.materialize_actor_projection

    def materialize_then_replace(*args: Any, **kwargs: Any) -> Any:
        projection, manifest = original_materialize(*args, **kwargs)
        retired = projection.with_name("actor-workspace-retired-after-publication")
        projection.rename(retired)
        projection.mkdir(mode=0o700)
        (projection / "README.md").write_text(
            "attacker replacement\n",
            encoding="utf-8",
        )
        (projection / ".git").mkdir(mode=0o700)
        return projection, manifest

    monkeypatch.setattr(
        RUNTIME,
        "materialize_actor_projection",
        materialize_then_replace,
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.start(fixture["launch_path"])

    assert exc_info.value.code == "workspace_projection_cleanup_incomplete"
    assert not runtime._state_path(fixture["session_id"]).exists()
    assert (
        runtime._session_dir(fixture["session_id"])
        / "actor-workspace-retired-after-publication"
        / ".git"
    ).is_dir()


def test_unicode_source_coordinate_is_removed_from_actor_envelopes_and_argv(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "данные")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    state = runtime._load_state(fixture["session_id"])
    source = str(fixture["workspace"].resolve())

    for item in state["materialized_task_inputs"]:
        raw = Path(item["path"]).read_bytes()
        envelope = json.loads(raw)
        assert envelope["schema_version"] == (
            "abyss_stack_external_codex_actor_input_envelope_v1"
        )
        assert source not in json.dumps(envelope, ensure_ascii=False)
        escaped_source = json.dumps(source, ensure_ascii=True)[1:-1].encode("utf-8")
        assert escaped_source not in raw
        if item["input_id"] == "workspace-manifest":
            assert "workspace_identity" not in envelope["payload"]
    assert all(
        source not in argument
        for attempt in state["attempts"]
        for argument in (attempt.get("codex_argv") or [])
    )


def test_prompt_scrub_removes_json_escaped_unicode_source_coordinate() -> None:
    source = "/home/д/repo"
    actor = str(ACTOR_EXECUTION_ROOT)
    raw_role = json.dumps({"workspace": source}, ensure_ascii=True)

    projected = RUNTIME._replace_prompt_source_path(
        raw_role,
        source_path=source,
        projection_path=actor,
    )

    assert source not in projected
    assert json.dumps(source, ensure_ascii=True)[1:-1] not in projected
    assert json.loads(projected)["workspace"] == actor


@pytest.mark.parametrize(
    "source_spelling",
    (
        r"\/tmp\/\u0434\u0430\u043d\u043d\u044b\u0435\/workspace",
        r"/tmp/\u0434\u0430\u043D\u043D\u044B\u0435/workspace",
        r"/tmp/\u0434а\u043dн\u044bе/workspace",
        r"/tmp/\u005cu0434\u005cu0430\u005cu043d\u005cu043d\u005cu044b\u005cu0435/workspace",
    ),
)
def test_actor_envelope_scrubs_preescaped_unicode_text_source_coordinate(
    source_spelling: str,
) -> None:
    source = "/tmp/данные/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }

    envelope, encoded = RUNTIME._actor_safe_input_envelope(
        input_id="preescaped-unicode-text-fixture",
        raw=f"TEXT {source_spelling} END".encode(),
        original_provenance=provenance,
        aliases=(source, "/tmp/данные"),
        source_roots=frozenset({source}),
    )

    assert envelope["payload_kind"] == "utf8_text"
    assert envelope["payload"] == f"TEXT {ACTOR_EXECUTION_ROOT} END"
    assert not RUNTIME._contains_source_path(encoded.decode(), source)


def test_actor_envelope_scrubs_surrogate_pair_source_coordinate() -> None:
    source = "/tmp/😀/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }

    envelope, encoded = RUNTIME._actor_safe_input_envelope(
        input_id="surrogate-pair-text-fixture",
        raw=rb"TEXT /tmp/\ud83d\ude00/workspace END",
        original_provenance=provenance,
        aliases=(source, "/tmp/😀"),
        source_roots=frozenset({source}),
    )

    assert envelope["payload"] == f"TEXT {ACTOR_EXECUTION_ROOT} END"
    assert not RUNTIME._contains_source_path(encoded.decode(), source)


def test_actor_envelope_rejects_excessive_nested_escape_depth() -> None:
    source = "/tmp/данные/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }
    nested = r"\u0434"
    for _ in range(RUNTIME.MAX_JSON_ESCAPE_LAYERS + 1):
        nested = nested.replace("\\", r"\u005c")

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._actor_safe_input_envelope(
            input_id="excessive-escape-depth-fixture",
            raw=f"TEXT /tmp/{nested}/workspace END".encode(),
            original_provenance=provenance,
            aliases=(source,),
            source_roots=frozenset({source}),
        )

    assert exc_info.value.code == "actor_input_escape_depth_exceeded"


def test_actor_envelope_rejects_escaped_source_in_binary_payload() -> None:
    source = "/tmp/данные/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._actor_safe_input_envelope(
            input_id="binary-escaped-source-fixture",
            raw=(
                b"\xffTEXT /tmp/"
                rb"\u0434\u0430\u043d\u043d\u044b\u0435/workspace END"
            ),
            original_provenance=provenance,
            aliases=(source,),
            source_roots=frozenset({source}),
        )

    assert exc_info.value.code == "actor_source_path_exposed"


def test_actor_envelope_scrubs_preescaped_ancestor_text() -> None:
    source = "/tmp/данные/workspace"
    ancestor = "/tmp/данные"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }

    envelope, encoded = RUNTIME._actor_safe_input_envelope(
        input_id="preescaped-ancestor-text-fixture",
        raw=rb"TEXT /tmp/\u0434\u0430\u043d\u043d\u044b\u0435/notes END",
        original_provenance=provenance,
        aliases=(source, ancestor),
        source_roots=frozenset({source}),
    )

    assert envelope["payload"] == "TEXT <controller-path-redacted>/notes END"
    assert not RUNTIME._contains_source_path(encoded.decode(), ancestor)


def test_actor_envelope_rejects_preescaped_mapping_key_collision() -> None:
    source = "/tmp/данные/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }
    preescaped_source = r"/tmp/\u0434\u0430\u043d\u043d\u044b\u0435/workspace"

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._actor_safe_input_envelope(
            input_id="preescaped-key-collision-fixture",
            raw=json.dumps(
                {preescaped_source: "source", str(ACTOR_EXECUTION_ROOT): "actor"}
            ).encode(),
            original_provenance=provenance,
            aliases=(source,),
            source_roots=frozenset({source}),
        )

    assert exc_info.value.code == "actor_input_key_collision"


@pytest.mark.parametrize(
    "source_spelling",
    (
        r"\/home\/\u0434\/repo",
        r"/home/\u0434/repo",
        r"/home/\u005cu0434/repo",
    ),
)
def test_prompt_scrub_removes_unicode_escape_variants(
    source_spelling: str,
) -> None:
    source = "/home/д/repo"

    projected = RUNTIME._replace_prompt_source_path(
        f"ROLE {source_spelling}",
        source_path=source,
        projection_path=str(ACTOR_EXECUTION_ROOT),
    )

    assert projected == f"ROLE {ACTOR_EXECUTION_ROOT}"
    assert not RUNTIME._contains_source_path(projected, source)


def test_actor_envelope_scrubs_unicode_source_keys_and_rejects_collisions() -> None:
    source = "/tmp/данные/workspace"
    ancestor = "/tmp/данные"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }
    envelope, encoded = RUNTIME._actor_safe_input_envelope(
        input_id="unicode-key-fixture",
        raw=json.dumps(
            {
                source: "root-key",
                ancestor + "/recorded": "ancestor-key",
            },
            ensure_ascii=True,
        ).encode("utf-8"),
        original_provenance=provenance,
        aliases=(source, ancestor),
        source_roots=frozenset({source}),
    )

    assert envelope["payload"] == {
        str(ACTOR_EXECUTION_ROOT): "root-key",
        "<controller-path-redacted>/recorded": "ancestor-key",
    }
    assert json.dumps(source, ensure_ascii=True)[1:-1].encode("utf-8") not in encoded
    assert json.dumps(ancestor, ensure_ascii=True)[1:-1].encode("utf-8") not in encoded

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._actor_safe_input_envelope(
            input_id="colliding-key-fixture",
            raw=json.dumps(
                {source: "source", str(ACTOR_EXECUTION_ROOT): "actor"},
                ensure_ascii=True,
            ).encode("utf-8"),
            original_provenance=provenance,
            aliases=(source, ancestor),
            source_roots=frozenset({source}),
        )
    assert exc_info.value.code == "actor_input_key_collision"


def test_prompt_scrub_applies_recorded_source_ancestor_alias(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "данные"
    ancestor = str(fixture_root.resolve())
    fixture = _fixture(
        fixture_root,
        objective_marker=f"RECORDED_SOURCE_ANCESTOR {ancestor}",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    state = runtime._load_state(fixture["session_id"])
    prompt = (
        runtime._session_dir(fixture["session_id"]) / "attempts/001/prompt.txt"
    ).read_text(encoding="utf-8")

    assert f"RECORDED_SOURCE_ANCESTOR {ACTOR_EXECUTION_ROOT}" in prompt
    assert ancestor in str(state["materialized_task_inputs"][0]["path"])


def test_source_under_codex_minimal_read_root_is_not_admitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(
        RUNTIME,
        "CODEX_MINIMAL_READ_ROOTS",
        (tmp_path.resolve(),),
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(fixture["launch_path"])

    assert exc_info.value.code == "workspace_minimal_read_root_unsupported"


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
    assert "AOA_EVALS_MCP_READ_BEARER_TOKEN" not in rendered
    assert "bearer_token_env_var" not in rendered
    assert re.search(r"http://127\.0\.0\.1:[0-9]+/mcp/[A-Za-z0-9_-]+", rendered)
    assert "aoa_stats" not in rendered
    assert "aoa_memo" not in rendered
    assert "eval-token" not in rendered


def test_attempt_environment_excludes_upstream_mcp_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
    )
    monkeypatch.setenv("AOA_EVALS_MCP_READ_BEARER_TOKEN", "upstream-token")
    tool_entry = next(
        item
        for item in fixture["runtime"].profile["tool_profiles"]
        if item["required_mcp_server_ids"] == ["aoa_evals"]
    )
    scratch = tmp_path / "attempt" / "scratch"
    scratch.parent.mkdir(exist_ok=True)
    scratch.mkdir()

    environment = fixture["runtime"]._codex_environment(
        fixture["launch"],
        scratch,
        tool_entry,
    )

    assert "AOA_EVALS_MCP_READ_BEARER_TOKEN" not in environment
    assert "upstream-token" not in environment.values()


def test_attempt_local_mcp_proxy_injects_upstream_credential_only_at_relay() -> None:
    observed: dict[str, Any] = {}

    class UpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            observed["authorization"] = self.headers.get("Authorization")
            observed["path"] = self.path
            observed["body"] = self.rfile.read(length)
            payload = b'{"jsonrpc":"2.0","id":1,"result":{}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()
    try:
        request = urllib.request.Request(
            proxy.endpoint_url,
            data=b'{"jsonrpc":"2.0","id":1,"method":"initialize"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {},
            }
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)

    assert observed == {
        "authorization": "Bearer upstream-token",
        "path": "/mcp",
        "body": b'{"jsonrpc":"2.0","id":1,"method":"initialize"}',
    }
    assert "upstream-token" not in proxy.endpoint_url


def test_mcp_proxy_connect_timeout_does_not_limit_response_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowUpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            time.sleep(0.15)
            payload = b'{"jsonrpc":"2.0","id":1,"result":{}}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    monkeypatch.setattr(RUNTIME, "MCP_PROXY_CONNECT_TIMEOUT_SECONDS", 0.05)
    upstream = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        SlowUpstreamHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()
    try:
        request = urllib.request.Request(
            proxy.endpoint_url,
            data=b"{}",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read())["result"] == {}
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)


def test_mcp_proxy_forwards_stream_events_without_waiting_for_large_buffer() -> None:
    event_payload = b"data: one\n\n"
    upstream_flushed = threading.Event()
    release_upstream = threading.Event()
    received = threading.Event()

    class StreamingUpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(event_payload)
            self.wfile.flush()
            upstream_flushed.set()
            release_upstream.wait(timeout=5)

    upstream = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        StreamingUpstreamHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()

    def read_event() -> None:
        request = urllib.request.Request(proxy.endpoint_url, data=b"{}", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.read(len(event_payload)) == event_payload:
                received.set()

    client_thread = threading.Thread(target=read_event)
    client_thread.start()
    try:
        assert upstream_flushed.wait(timeout=5)
        assert received.wait(timeout=1)
    finally:
        release_upstream.set()
        client_thread.join(timeout=5)
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)


def test_mcp_proxy_close_terminates_client_stalled_before_request_parsing() -> None:
    proxy = RUNTIME._McpCredentialProxy(
        {"url": "http://127.0.0.1:9/mcp"},
        "upstream-token",
    )
    proxy.start()
    host, port = proxy._server.server_address
    idle_client = socket.create_connection((host, port), timeout=5)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with proxy._server._accepted_lock:
            if proxy._server._accepted_requests:
                break
        time.sleep(0.01)
    else:
        pytest.fail("proxy did not track the accepted idle client")

    closed = threading.Event()

    def close_proxy() -> None:
        proxy.close()
        closed.set()

    closer = threading.Thread(target=close_proxy)
    closer.start()
    try:
        assert closed.wait(timeout=2)
    finally:
        try:
            idle_client.close()
        finally:
            closer.join(timeout=5)
            proxy.close()

    assert not closer.is_alive()


def test_mcp_proxy_removes_request_timeout_before_response_streaming() -> None:
    upstream_received = threading.Event()
    release_upstream = threading.Event()

    class WaitingUpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            upstream_received.set()
            release_upstream.wait(timeout=5)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

    upstream = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        WaitingUpstreamHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()
    client_result: list[bytes] = []

    def read_response() -> None:
        request = urllib.request.Request(proxy.endpoint_url, data=b"{}", method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            client_result.append(response.read())

    client_thread = threading.Thread(target=read_response)
    client_thread.start()
    try:
        assert upstream_received.wait(timeout=5)
        with proxy._server._accepted_lock:
            accepted_requests = tuple(proxy._server._accepted_requests)
        assert len(accepted_requests) == 1
        assert accepted_requests[0].gettimeout() is None
    finally:
        release_upstream.set()
        client_thread.join(timeout=5)
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)

    assert client_result == [b"ok"]


def test_mcp_proxy_does_not_append_second_response_after_upstream_truncation() -> None:
    class TruncatedUpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"ok")
            self.wfile.flush()
            self.close_connection = True

    upstream = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        TruncatedUpstreamHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()
    proxy_host, proxy_port = proxy._server.server_address
    client = socket.create_connection((proxy_host, proxy_port), timeout=5)
    request = (
        f"POST {urllib.parse.urlsplit(proxy.endpoint_url).path} HTTP/1.0\r\n"
        "Content-Length: 2\r\n\r\n{}"
    ).encode("ascii")
    client.sendall(request)
    response_parts: list[bytes] = []
    try:
        while True:
            part = client.recv(65_536)
            if not part:
                break
            response_parts.append(part)
    finally:
        client.close()
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)

    raw_response = b"".join(response_parts)
    response_headers, response_body = raw_response.split(b"\r\n\r\n", 1)
    assert response_headers.startswith(b"HTTP/1.0 200")
    assert b"Content-Length:" not in response_headers
    assert response_body == b"ok"
    assert raw_response.count(b"HTTP/1.0 ") == 1
    assert b"502 Bad Gateway" not in raw_response


def test_mcp_proxy_close_terminates_an_active_authenticated_relay() -> None:
    upstream_flushed = threading.Event()
    release_upstream = threading.Event()
    client_received = threading.Event()

    class LongLivedUpstreamHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"x")
            self.wfile.flush()
            upstream_flushed.set()
            release_upstream.wait(timeout=5)

    upstream = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        LongLivedUpstreamHandler,
    )
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    host, port = upstream.server_address
    proxy = RUNTIME._McpCredentialProxy(
        {"url": f"http://{host}:{port}/mcp"},
        "upstream-token",
    )
    proxy.start()

    def hold_client() -> None:
        request = urllib.request.Request(proxy.endpoint_url, data=b"{}", method="POST")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                response.read(1)
                client_received.set()
                response.read()
        except (OSError, http.client.HTTPException):
            return

    client_thread = threading.Thread(target=hold_client)
    client_thread.start()
    try:
        assert upstream_flushed.wait(timeout=5)
        assert client_received.wait(timeout=5)
        proxy.close()
        assert not proxy._active_relay_sockets
        assert not proxy._thread.is_alive()
    finally:
        release_upstream.set()
        client_thread.join(timeout=5)
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=5)


def test_worker_closes_mcp_credential_proxy_before_failure_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    lifecycle: list[str] = []

    class FakeProxy:
        def close(self) -> None:
            lifecycle.append("closed")

    def fail_attempt(_session_id: str, **kwargs: Any) -> None:
        kwargs["credential_proxies"].append(FakeProxy())
        lifecycle.append("raised")
        raise RuntimeError("failure after credential proxy startup")

    monkeypatch.setattr(runtime, "_run_worker_attempt", fail_attempt)

    with pytest.raises(RuntimeError, match="failure after credential proxy startup"):
        runtime._run_worker(
            fixture["session_id"],
            attempt_id="attempt-id",
            attempt_number=1,
            mode="start",
            resume_payload=None,
        )

    assert lifecycle == ["raised", "closed"]


def test_worker_closes_mcp_credential_proxy_before_terminal_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
    )
    monkeypatch.setenv("AOA_EVALS_MCP_READ_BEARER_TOKEN", "upstream-token")
    relay_closed = tmp_path / "relay-closed"
    original_close = RUNTIME._McpCredentialProxy.close
    original_finalize = fixture["runtime"]._finalize_attempt_locked

    def observed_close(proxy: Any) -> None:
        original_close(proxy)
        relay_closed.write_text("closed\n", encoding="utf-8")

    def guarded_finalize(state: dict[str, Any], **kwargs: Any) -> None:
        assert relay_closed.is_file()
        original_finalize(state, **kwargs)

    monkeypatch.setattr(RUNTIME._McpCredentialProxy, "close", observed_close)
    monkeypatch.setattr(
        fixture["runtime"],
        "_finalize_attempt_locked",
        guarded_finalize,
    )

    fixture["runtime"].start(fixture["launch_path"])

    assert _wait_terminal(fixture["runtime"], fixture["session_id"])["status"] == (
        "completed"
    )
    assert relay_closed.is_file()


def test_live_codex_process_environment_has_no_upstream_mcp_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
    )
    monkeypatch.setenv("AOA_EVALS_MCP_READ_BEARER_TOKEN", "upstream-token")
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    codex_pid: int | None = None
    while time.monotonic() < deadline:
        status = runtime.status(fixture["session_id"])
        if isinstance(status.get("codex_pid"), int):
            codex_pid = status["codex_pid"]
            break
        time.sleep(0.05)
    assert codex_pid is not None

    observed_environment = Path(f"/proc/{codex_pid}/environ").read_bytes()

    assert b"AOA_EVALS_MCP_READ_BEARER_TOKEN" not in observed_environment
    assert b"upstream-token" not in observed_environment
    interrupted = runtime.interrupt(fixture["session_id"])
    assert interrupted["status"] == "interrupted"


def test_cli_brokers_mcp_credential_outside_process_environments_and_denies_proc(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="eval_application",
        role_mcp="aoa_evals",
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
    )
    token_name = "AOA_EVALS_MCP_READ_BEARER_TOKEN"
    token = "upstream-token-not-visible-in-proc"
    process = subprocess.Popen(
        [
            str(CLI_PATH),
            "run-to-terminal",
            "--state-root",
            str(fixture["runtime"].state_root),
            "--profile",
            str(PROFILE_PATH),
            "--launch",
            str(fixture["launch_path"]),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, token_name: token},
    )
    runtime = fixture["runtime"]
    status: dict[str, Any] | None = None
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                pytest.fail(
                    f"brokered CLI exited before observation: {stdout} {stderr}"
                )
            try:
                status = runtime.status(fixture["session_id"])
            except RUNTIME.ExternalCodexRuntimeError:
                time.sleep(0.05)
                continue
            if all(
                isinstance(status.get(key), int)
                for key in ("worker_pid", "supervisor_pid", "codex_pid")
            ):
                break
            time.sleep(0.05)
        assert status is not None
        observed_pids = {
            process.pid,
            int(status["worker_pid"]),
            int(status["supervisor_pid"]),
            int(status["codex_pid"]),
        }
        for pid in observed_pids:
            environment = Path(f"/proc/{pid}/environ").read_bytes()
            assert token_name.encode() not in environment
            assert token.encode() not in environment
        state = runtime._load_state(fixture["session_id"])
        rendered = "\n".join(state["attempts"][0]["codex_argv"])
        assert '"/proc"="deny"' in rendered
        assert runtime.interrupt(fixture["session_id"])["status"] == "interrupted"
        stdout, stderr = process.communicate(timeout=15)
        assert process.returncode == 0, stderr
        response = json.loads(stdout)
        assert response["ok"] is True
        assert response["result"]["status"] == "interrupted"
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_runtime_tool_profile_ids_are_model_neutral() -> None:
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_ids = [item["profile_id"] for item in profile["tool_profiles"]]
    assert all("luna" not in item and "sol" not in item for item in profile_ids)


def _enable_specialized_test_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    release = tmp_path / "verified-release"
    (release / "environments/landing-validation-v1/pythonpath").mkdir(parents=True)
    (release / "sdk/src").mkdir(parents=True)
    (release / "owners/aoa-stats").mkdir(parents=True)
    monkeypatch.setenv("AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT", str(release))
    return release


def test_landing_specialized_environment_is_release_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _enable_specialized_test_release(monkeypatch, tmp_path)
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    tool_entry = next(
        item
        for item in profile["tool_profiles"]
        if item["profile_id"]
        == "abyss-stack:external_codex_agent/landing-workspace-write-v2"
    )

    environment, readable = RUNTIME._specialized_environment(
        profile,
        tool_entry,
    )

    assert environment == {
        "AOA_STATS_ROOT": str((release / "owners/aoa-stats").resolve()),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "PYTHONPATH": os.pathsep.join(
            (
                str(
                    (
                        release / "environments/landing-validation-v1/pythonpath"
                    ).resolve()
                ),
                str((release / "sdk/src").resolve()),
            )
        ),
    }
    assert set(readable) == {
        (release / "owners/aoa-stats").resolve(),
        (release / "environments/landing-validation-v1/pythonpath").resolve(),
        (release / "sdk/src").resolve(),
    }


def test_model_organ_landing_readonly_profile_admits_exact_runtime_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = _enable_specialized_test_release(monkeypatch, tmp_path)
    tool_profile_id = "abyss-stack:external_codex_agent/landing-readonly-v2"
    fixture = _fixture(tmp_path, tool_profile_id=tool_profile_id)

    admission = fixture["runtime"].preflight(fixture["launch_path"])
    terminal = fixture["runtime"].run_to_terminal(fixture["launch_path"])
    result = fixture["runtime"].result(fixture["session_id"])

    assert admission["admitted"] is True
    assert admission["tool_profile_id"] == tool_profile_id
    assert terminal["status"] == "completed"
    assert result is not None
    assert result["status"] == "completed"
    assert result["changed_paths"] == []
    codex_argv = result["codex_invocations"][0]["argv"]
    assert (
        "shell_environment_policy.set="
        '{"AOA_STATS_ROOT"="'
        + str((release / "owners/aoa-stats").resolve())
        + '","PYTEST_ADDOPTS"="-p no:cacheprovider",'
        '"PYTHONDONTWRITEBYTECODE"="1","PYTHONNOUSERSITE"="1","PYTHONPATH"="'
        + str((release / "environments/landing-validation-v1/pythonpath").resolve())
        + os.pathsep
        + str((release / "sdk/src").resolve())
        + '"}'
    ) in codex_argv


def test_generic_profile_does_not_inject_specialized_shell_environment(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    fixture["runtime"].run_to_terminal(fixture["launch_path"])
    result = fixture["runtime"].result(fixture["session_id"])

    assert result is not None
    assert not any(
        argument.startswith("shell_environment_policy.set=")
        for argument in result["codex_invocations"][0]["argv"]
    )


@pytest.mark.parametrize(
    "tool_profile_id",
    (
        "abyss-stack:external_codex_agent/landing-workspace-write-v2",
        "abyss-stack:external_codex_agent/structured-owner-duty-workspace-write-v1",
    ),
)
def test_model_organ_workspace_write_profiles_admit_exact_runtime_binding(
    tmp_path: Path,
    tool_profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if tool_profile_id.endswith("landing-workspace-write-v2"):
        _enable_specialized_test_release(monkeypatch, tmp_path)
    fixture = _fixture(
        tmp_path,
        workspace_write=True,
        tool_profile_id=tool_profile_id,
    )

    admission = fixture["runtime"].preflight(fixture["launch_path"])
    terminal = fixture["runtime"].run_to_terminal(fixture["launch_path"])
    result = fixture["runtime"].result(fixture["session_id"])

    assert admission["admitted"] is True
    assert admission["tool_profile_id"] == tool_profile_id
    assert terminal["status"] == "completed"
    assert result is not None
    assert result["status"] == "completed"
    assert result["usage_observation"]["status"] == "complete"


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
    fixture = _fixture(tmp_path / "writer", role_id="reviewer", exact_baseline=True)
    writer_runtime = fixture["runtime"]
    writer_runtime.start(fixture["launch_path"])
    assert (
        _wait_terminal(writer_runtime, fixture["session_id"])["status"] == "completed"
    )
    writer_result_path = (
        writer_runtime._session_dir(fixture["session_id"]) / "result.json"
    )
    output_root = tmp_path / "review-preparation"
    reviewer_state_root = writer_runtime.state_root

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
    launch = json.loads(Path(preparation["launch_path"]).read_text(encoding="utf-8"))
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
        "writer-actor-final-manifest",
        "writer-actor-delta",
    }
    assert task["task_family"] == "landing_review"
    assert task["review_required"] is False
    assert task["transition"]["review_required_status"] == (
        "review_required_source_repair"
    )
    assert task["parent_task_id"] == fixture["task_id"]
    assert {item["input_id"] for item in task["immutable_inputs"]}.issuperset(
        {"summon-request", "summon-request-schema", "review-summon-request"}
    )
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
    assert reviewer_state_root.exists()
    seed = launch["workspace_projection_seed"]
    assert Path(seed["envelope_path"]).parent == writer_result_path.parent
    assert seed["envelope_digest"] == _digest_path(Path(seed["envelope_path"]))
    assert preparation["review_seed_envelope_path"] == seed["envelope_path"]
    assert preparation["review_seed_envelope_digest"] == seed["envelope_digest"]

    retired_source = tmp_path / "retired-writer-source"
    fixture["workspace"].rename(retired_source)
    assert not fixture["workspace"].exists()
    reviewer_runtime = RUNTIME.ExternalCodexRuntime(reviewer_state_root)
    assert (
        reviewer_runtime.preflight(Path(preparation["launch_path"]))["admitted"] is True
    )

    retry_response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(tmp_path / "review-preparation-retry"),
            state_root=str(reviewer_state_root),
            aoa_sdk_root=str(SDK_ROOT),
            review_instance_id="effect-observer-repair-1",
        )
    )
    retry_preparation = json.loads(
        Path(retry_response["preparation_path"]).read_text(encoding="utf-8")
    )
    assert retry_preparation["review_instance_id"] == "effect-observer-repair-1"
    assert (
        retry_preparation["reviewer_session_id"] != preparation["reviewer_session_id"]
    )
    assert (
        retry_preparation["reviewer_incarnation_id"]
        != preparation["reviewer_incarnation_id"]
    )

    reviewer_runtime.start(Path(preparation["launch_path"]))
    assert (
        _wait_terminal(reviewer_runtime, preparation["reviewer_session_id"])["status"]
        == "completed"
    )
    summon_path = fixture["summon_request_path"]
    exported = writer_runtime.export_a2a_result(
        fixture["session_id"],
        reviewer_session_id=preparation["reviewer_session_id"],
        reviewer_state_root=reviewer_state_root,
        summon_request_path=summon_path,
        output_path=tmp_path / "cross-state-child-task-result.json",
    )
    assert exported["child_task_result"]["review_outcome"] == "proceed"


def test_reviewer_semantics_are_generic_outside_landing() -> None:
    assert PREPARER._reviewer_semantics("landing_preparation") == (
        "landing_review",
        "independent_landing_review",
    )
    assert PREPARER._reviewer_semantics("eval_selection") == (
        "eval_selection_review",
        "independent_actor_review",
    )


def test_non_landing_prepared_reviewer_seed_is_runtime_admitted(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "writer",
        role_id="reviewer",
        task_family="eval_selection",
        exact_baseline=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"

    response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(tmp_path / "review-preparation"),
            state_root=str(runtime.state_root),
            aoa_sdk_root=str(SDK_ROOT),
            review_instance_id="eval-selection-review",
        )
    )
    preparation = json.loads(
        Path(response["preparation_path"]).read_text(encoding="utf-8")
    )
    launch_path = Path(preparation["launch_path"])
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    task = json.loads(Path(launch["task"]["path"]).read_text(encoding="utf-8"))

    assert task["task_family"] == "eval_selection_review"
    assert runtime.preflight(launch_path)["admitted"] is True


def test_reviewer_preparation_uses_historical_coordinate_after_ancestor_retarget(
    tmp_path: Path,
) -> None:
    source_parent = tmp_path / "source-parent"
    source_parent.mkdir()
    fixture = _fixture(
        tmp_path / "writer-control",
        role_id="reviewer",
        exact_baseline=True,
        state_root=tmp_path / "state",
        shared_workspace=source_parent / "workspace",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"

    retired_parent = tmp_path / "retired-source-parent"
    source_parent.rename(retired_parent)
    decoy_parent = tmp_path / "decoy-source-parent"
    (decoy_parent / "workspace").mkdir(parents=True)
    source_parent.symlink_to(decoy_parent, target_is_directory=True)

    response = PREPARER._prepare_reviewer(
        argparse.Namespace(
            writer_launch=str(fixture["launch_path"]),
            writer_result=str(writer_result_path),
            output_root=str(tmp_path / "review-preparation-retargeted"),
            state_root=str(runtime.state_root),
            aoa_sdk_root=str(SDK_ROOT),
            review_instance_id="retargeted-ancestor",
        )
    )

    assert response["prepared"] is True
    preparation = json.loads(
        Path(response["preparation_path"]).read_text(encoding="utf-8")
    )
    reviewer_launch = json.loads(
        Path(preparation["launch_path"]).read_text(encoding="utf-8")
    )
    assert (
        reviewer_launch["workspace_projection_seed"]["envelope_digest"]
        == (preparation["review_seed_envelope_digest"])
    )


def test_repo_mutation_writer_enters_explicit_read_only_review_and_a2a_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_specialized_test_release(monkeypatch, tmp_path)
    fixture = _fixture(
        tmp_path / "writer",
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        review_required=True,
        allowed_paths=(".",),
        prepare_mutation_reviewer_sources=True,
        omit_historical_reviewer_inputs=True,
        reviewer_tool_profile_id=(
            "abyss-stack:external_codex_agent/landing-readonly-v2"
        ),
        source_evidence_paths=("README.md",),
        owner_contour=True,
    )
    runtime = fixture["runtime"]
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None
    runtime.start(
        fixture["launch_path"],
        owner_request_path=owner_request_path,
    )
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
        {"path": "landing-note.md", "status": "created"}
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
            reviewer_model_realization=str(fixture["reviewer_realization_path"]),
        )
    )
    preparation = json.loads(
        Path(response["preparation_path"]).read_text(encoding="utf-8")
    )
    reviewer_launch_path = Path(preparation["launch_path"])
    reviewer_launch = json.loads(reviewer_launch_path.read_text(encoding="utf-8"))
    reviewer_binding = json.loads(
        Path(reviewer_launch["incarnation_binding"]["path"]).read_text(encoding="utf-8")
    )
    reviewer_plan = json.loads(
        Path(reviewer_launch["plan"]["path"]).read_text(encoding="utf-8")
    )
    reviewer_task = json.loads(
        Path(reviewer_launch["task"]["path"]).read_text(encoding="utf-8")
    )
    assert preparation["writer_effect_class"] == "repo_mutation"
    assert reviewer_launch["workspace_manifest_input_id"] == (
        "review-workspace-manifest"
    )
    assert reviewer_launch["runtime_profile"] == PREPARER._artifact_coordinate(
        PREPARER.PROFILE_PATH
    )
    assert (
        reviewer_binding["runtime_profile_ref"]
        == reviewer_plan["runtime_profile"]["provenance"]
    )
    assert reviewer_launch["model_realization"]["path"] == str(
        fixture["reviewer_realization_path"]
    )
    assert reviewer_binding["role_id"] == "reviewer"
    assert reviewer_binding["permission_posture"]["sandbox_mode"] == "read_only"
    assert reviewer_binding["permission_posture"]["allowed_effect_classes"] == [
        "read_only"
    ]
    selected_reviewer = next(
        item
        for item in reviewer_plan["scenario_binding"]["agent_refs"]
        if item["agent_id"] == "reviewer"
        and item["provenance"] == reviewer_binding["role_contract_ref"]
    )
    active_reviewer_steps = [
        step
        for step in reviewer_plan["steps"]
        if reviewer_binding["task_request_ref"] in step["input_refs"]
    ]
    reviewer_capabilities = reviewer_plan["scenario_binding"]["capability_refs"]
    selected_reviewer_capability = next(
        item
        for item in reviewer_capabilities
        if item["capability_id"] == "route-drift-review.readonly"
    )
    assert selected_reviewer_capability["provenance"]["owner_repo"] == "aoa-agents"
    review_summon_request = json.loads(
        Path(
            next(
                item["local_path"]
                for item in reviewer_task["immutable_inputs"]
                if item["input_id"] == "review-summon-request"
            )
        ).read_text(encoding="utf-8")
    )
    assert review_summon_request["summon_request"]["capability_refs"] == [
        "route-drift-review.readonly"
    ]
    assert active_reviewer_steps
    assert all(
        selected_reviewer in step["agent_refs"]
        and step["capability_refs"] == [selected_reviewer_capability]
        and step["effect_class"] == "read_only"
        for step in active_reviewer_steps
    )
    assert reviewer_task["indirect_command_policy"] == "sandbox_confined"
    assert reviewer_task["source_evidence_paths"] == ["README.md"]
    assert set(preparation["forwarded_input_ids"]).issuperset(
        {
            "writer-source-baseline-manifest",
            "writer-summon-request-schema",
        }
    )
    assert "workspace-manifest" not in preparation["forwarded_input_ids"]
    assert "summon-request-schema" not in preparation["forwarded_input_ids"]
    reviewer_input_ids = {
        item["input_id"] for item in reviewer_task["immutable_inputs"]
    }
    assert {
        "writer-source-baseline-manifest",
        "writer-summon-request-schema",
        "review-workspace-manifest",
    }.issubset(reviewer_input_ids)

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


def test_owner_contour_reviewer_recovery_rejects_changed_source_baseline(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "writer",
        role_id="reviewer",
        owner_contour=True,
        omit_historical_reviewer_inputs=True,
    )
    runtime = fixture["runtime"]
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None
    runtime.start(
        fixture["launch_path"],
        owner_request_path=owner_request_path,
    )
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"
    writer_result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    source_before_path = writer_result_path.parent / "source-manifest-before.json"
    source_before_path.chmod(0o600)
    source_before_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(
        PREPARER.StudyPreparationError,
        match="source baseline is unavailable or changed",
    ):
        PREPARER._prepare_reviewer(
            argparse.Namespace(
                writer_launch=str(fixture["launch_path"]),
                writer_result=str(writer_result_path),
                output_root=str(tmp_path / "review-preparation"),
                state_root=str(runtime.state_root),
                aoa_sdk_root=str(SDK_ROOT),
            )
        )


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


def test_review_seed_rejects_live_writer_and_stale_terminal_result(
    tmp_path: Path,
) -> None:
    live_writer = _fixture(
        tmp_path / "live-writer",
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
        identity_suffix="live-seed-writer",
    )
    live_runtime = live_writer["runtime"]
    live_runtime.start(live_writer["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if live_runtime.status(live_writer["session_id"])["codex_pid"]:
            break
        time.sleep(0.05)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        live_runtime.issue_review_seed(live_writer["session_id"])
    assert exc_info.value.code == "review_seed_writer_not_terminal"
    assert live_runtime.interrupt(live_writer["session_id"])["status"] == "interrupted"

    writer = _fixture(
        tmp_path / "terminal-writer",
        identity_suffix="stale-seed-writer",
    )
    runtime = writer["runtime"]
    runtime.start(writer["launch_path"])
    assert _wait_terminal(runtime, writer["session_id"])["status"] == "completed"
    result_path = runtime._session_dir(writer["session_id"]) / "result.json"
    stale = json.loads(result_path.read_text(encoding="utf-8"))
    stale["duration_seconds"] = float(stale["duration_seconds"]) + 1.0
    _write_json(result_path, stale)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.issue_review_seed(writer["session_id"])
    assert exc_info.value.code == "review_seed_writer_result_unbound"


def test_review_seed_rejects_writer_session_reuse(tmp_path: Path) -> None:
    shared_state = tmp_path / "shared-state"
    writer = _fixture(
        tmp_path / "writer",
        identity_suffix="seed-session-reuse",
        state_root=shared_state,
    )
    runtime = writer["runtime"]
    runtime.start(writer["launch_path"])
    assert _wait_terminal(runtime, writer["session_id"])["status"] == "completed"
    seed_ref = runtime.issue_review_seed(writer["session_id"])
    reviewer = _fixture(
        tmp_path / "reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="seed-session-reuse",
        state_root=shared_state,
        shared_workspace=writer["workspace"],
        workspace_projection_seed={
            "envelope_path": seed_ref["artifact_ref"],
            "envelope_digest": seed_ref["artifact_digest"],
        },
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.preflight(reviewer["launch_path"])
    assert exc_info.value.code == "review_seed_session_reuse"

    foreign_reviewer = _fixture(
        tmp_path / "foreign-reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id="task:foreign-writer",
        identity_suffix="foreign-seed-reviewer",
        state_root=shared_state,
        shared_workspace=writer["workspace"],
        workspace_projection_seed={
            "envelope_path": seed_ref["artifact_ref"],
            "envelope_digest": seed_ref["artifact_digest"],
        },
    )
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.preflight(foreign_reviewer["launch_path"])
    assert exc_info.value.code == "review_seed_parent_task_mismatch"


def test_reviewer_preparation_rejects_malformed_owner_admission(
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

    with pytest.raises(
        PREPARER.ExternalCodexRuntimeError,
        match="owner_execution_request_schema",
    ):
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
        "artifacts": {key: launch[key]["path"] for key in BINDER.COORDINATE_KEYS},
        "owner_contract_paths": {
            "owner_execution_request_schema": launch["owner_execution_request_schema"][
                "path"
            ],
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
def test_owner_contour_rejects_historical_v1_incarnation_binding(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, owner_contour=True, owner_binding_v1=True)
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(
            fixture["launch_path"],
            owner_request_path=owner_request_path,
        )

    assert exc_info.value.code == "owner_incarnation_binding_v2_required"


@pytest.mark.skipif(
    not OWNER_EXECUTION_REQUEST_SCHEMA_PATH.is_file()
    or not TASK_LOCAL_DAG_SCHEMA_PATH.is_file(),
    reason="paired owner-contour proof requires aoa-agents and aoa-skills source roots",
)
def test_owner_contour_rejects_changed_request_without_new_digest(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, owner_contour=True)
    owner_request_path = fixture["owner_execution_request_path"]
    assert owner_request_path is not None
    request = json.loads(owner_request_path.read_text(encoding="utf-8"))
    request["request_ref"] = request["request_ref"] + ":changed"
    _write_json(owner_request_path, request)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(
            fixture["launch_path"],
            owner_request_path=owner_request_path,
        )

    assert exc_info.value.code == "owner_execution_request_digest_invalid"


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
    _refresh_request_digest(request)
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
def test_owner_request_compiler_rejects_internally_inconsistent_transfer(
    tmp_path: Path,
) -> None:
    assert SUMMON_COMPILER is not None
    with pytest.raises(
        SUMMON_COMPILER.ExternalExecutionRequestError,
        match="transfer obligation",
    ):
        _fixture(
            tmp_path,
            owner_contour=True,
            responsibility_transfer_mutator=lambda value: value.update(
                {"obligation_ref": "obligation:unrelated"}
            ),
        )


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


def test_active_attempts_use_distinct_runtime_owned_projections(
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

    second_started = second["runtime"].start(second["launch_path"])
    assert second_started["status"] in {"prepared", "running"}
    first_state = runtime._load_state(first["session_id"])
    second_state = second["runtime"]._load_state(second["session_id"])
    assert first_state["actor_projection_path"] != second_state["actor_projection_path"]
    assert Path(first_state["actor_projection_path"]).is_dir()
    assert Path(second_state["actor_projection_path"]).is_dir()
    assert (Path(first_state["actor_projection_path"]) / ".git").is_dir()
    assert (Path(second_state["actor_projection_path"]) / ".git").is_dir()

    interrupted = runtime.interrupt(first["session_id"])
    assert interrupted["status"] == "interrupted"
    terminal = _wait_terminal(second["runtime"], second["session_id"])
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
    assert runtime._forbidden_effects(recovered["executed_commands"], task) == [
        "unclassified_indirect_effect"
    ]
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
    assert result["changed_paths"] == [{"path": "dirty-note.txt", "status": "modified"}]


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
    assert result["changed_paths"] == [{"path": "unexpected.txt", "status": "created"}]
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
    assert result["failure_code"] == "actor_projection_observation_gap"
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
    assert result["changed_paths"] == [{"path": "landing-note.md", "status": "created"}]
    invocation = result["codex_invocations"][0]
    argv = invocation["argv"]
    assert "-s" not in argv
    assert 'default_permissions="aoa_external_actor"' in argv
    assert any(
        value.startswith("permissions.aoa_external_actor=")
        and "network={enabled=false}" in value
        for value in argv
    )
    state = runtime._load_state(fixture["session_id"])
    projection = Path(state["actor_projection_path"])
    assert invocation["execution_root"] == str(ACTOR_EXECUTION_ROOT)
    assert argv[argv.index("-C") + 1] == str(ACTOR_EXECUTION_ROOT)
    assert projection != fixture["workspace"]
    assert "--skip-git-repo-check" not in argv
    permission_override = next(
        value for value in argv if value.startswith("permissions.aoa_external_actor=")
    )
    assert '":workspace_roots"="write"' in permission_override
    assert str(ACTOR_EXECUTION_ROOT) not in permission_override
    assert not (fixture["workspace"] / "landing-note.md").exists()
    assert result["source_manifest_match"] is True


def test_workspace_write_admits_only_required_parent_directories(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WRITE_NESTED_ALLOWED FAKE_NESTED_ARTIFACT_PRODUCED"
        ),
        role_id="coder",
        task_family="landing_preparation",
        identity_suffix="luna-nested-output",
        workspace_write=True,
        allowed_paths=("actor-output/result.json",),
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None and result["status"] == "completed"
    assert result["changed_paths"] == [
        {"path": "actor-output", "status": "created"},
        {"path": "actor-output/result.json", "status": "created"},
    ]
    report = json.loads(Path(result["report_ref"]["artifact_ref"]).read_text())
    assert report["artifact_paths"] == ["actor-output/result.json"]


def test_workspace_write_rejects_empty_structural_parent(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_EMPTY_ALLOWED_PARENT",
        role_id="coder",
        task_family="landing_preparation",
        identity_suffix="luna-empty-parent",
        workspace_write=True,
        allowed_paths=("actor-output/result.json",),
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "authority_boundary_crossed"
    assert result["changed_paths"] == [
        {"path": "actor-output", "status": "created"}
    ]


def test_structural_parent_rule_requires_an_exact_allowed_peer_delta() -> None:
    allowed = ("actor-output/result.json",)
    created_parent = {
        "path": "actor-output",
        "status": "created",
        "before": None,
        "after": {"kind": "directory"},
    }
    created_child = {
        "path": "actor-output/result.json",
        "status": "created",
        "before": None,
        "after": {"kind": "file"},
    }
    deleted_parent = {
        "path": "actor-output",
        "status": "deleted",
        "before": {"kind": "directory"},
        "after": None,
    }
    deleted_child = {
        "path": "actor-output/result.json",
        "status": "deleted",
        "before": {"kind": "file"},
        "after": None,
    }

    assert not RUNTIME._actor_delta_change_is_allowed(created_parent, allowed)
    assert RUNTIME._actor_delta_change_is_allowed(
        created_parent,
        allowed,
        peer_changes=(created_parent, created_child),
    )
    assert RUNTIME._actor_delta_changes_out_of_scope(
        (created_parent, created_child), allowed
    ) == []
    assert RUNTIME._actor_delta_changes_out_of_scope(
        (deleted_parent, deleted_child), allowed
    ) == []
    assert RUNTIME._actor_delta_changes_out_of_scope((created_parent,), allowed) == [
        "actor-output"
    ]
    assert not RUNTIME._actor_delta_change_is_allowed(
        {
            "path": "actor-output/other.json",
            "status": "created",
            "before": None,
            "after": {"kind": "file"},
        },
        allowed,
    )
    assert not RUNTIME._actor_delta_change_is_allowed(
        {
            "path": "actor-output",
            "status": "type_changed",
            "before": {"kind": "directory"},
            "after": {"kind": "symlink"},
        },
        allowed,
    )
    assert not RUNTIME._actor_delta_change_is_allowed(
        {
            "path": "actor-output",
            "status": "created",
            "before": None,
            "after": {"kind": "symlink"},
        },
        allowed,
    )
    assert not RUNTIME._actor_delta_change_is_allowed(
        {
            "path": "actor-output/../outside",
            "status": "created",
            "before": None,
            "after": {"kind": "directory"},
        },
        allowed,
    )


def test_failure_closeout_uses_the_exact_actor_delta_parent_relation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_NESTED_ALLOWED FAKE_NESTED_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        identity_suffix="luna-nested-failure-closeout",
        workspace_write=True,
        allowed_paths=("actor-output/result.json",),
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"

    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        attempt_id = state["attempts"][-1]["attempt_id"]
        state["status"] = "failed"
        state["finished_at"] = RUNTIME.iso_now()
        runtime._write_failure_result_locked(
            state,
            attempt_id=attempt_id,
            code="unexpected_worker_failure",
            message="worker failed after writing a nested allowed output",
        )
        runtime._save_state(state)

    result = runtime.result(fixture["session_id"])

    assert runtime.status(fixture["session_id"])["status"] == "failed"
    assert result is not None
    assert result["failure_code"] == "unexpected_worker_failure"
    assert result["changed_paths"] == [
        {"path": "actor-output", "status": "created"},
        {"path": "actor-output/result.json", "status": "created"},
    ]


def test_failure_closeout_preserves_actor_projection_observation_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    assert _wait_terminal(runtime, fixture["session_id"])["status"] == "completed"

    def fail_actor_manifest(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RUNTIME.ExternalCodexRuntimeError(
            "actor_projection_observation_gap",
            "actor projection inventory is unavailable",
        )

    monkeypatch.setattr(RUNTIME, "_checked_actor_manifest", fail_actor_manifest)
    with runtime._lock(fixture["session_id"]):
        state = runtime._load_state(fixture["session_id"])
        attempt_id = state["attempts"][-1]["attempt_id"]
        state["status"] = "failed"
        state["finished_at"] = RUNTIME.iso_now()
        runtime._write_failure_result_locked(
            state,
            attempt_id=attempt_id,
            code="unexpected_worker_failure",
            message="worker failed before actor projection closeout",
        )
        runtime._save_state(state)

    result = runtime.result(fixture["session_id"])

    assert runtime.status(fixture["session_id"])["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "actor_projection_observation_gap"


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


def test_workspace_write_report_accepts_actual_produced_artifact(
    tmp_path: Path,
) -> None:
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
    assert result["changed_paths"] == [{"path": "landing-note.md", "status": "created"}]


def test_workspace_root_source_evidence_scope_admits_only_safe_relative_paths() -> None:
    assert RUNTIME._relative_path_is_allowed("README.md", (".",))
    assert RUNTIME._relative_path_is_allowed("docs/architecture.md", (".",))
    assert not RUNTIME._relative_path_is_allowed("../outside.md", (".",))
    assert not RUNTIME._relative_path_is_allowed("/absolute.md", (".",))
    assert not RUNTIME._relative_path_is_allowed("docs/../outside.md", (".",))


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


def test_runtime_final_workspace_manifest_exact_content_path_is_admitted_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED "
            "FAKE_VALID_RUNTIME_FINAL_MANIFEST_PATH_EVIDENCE"
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
    final_manifest = json.loads(
        Path(result["workspace_manifest_ref"]["artifact_ref"]).read_text(
            encoding="utf-8"
        )
    )
    assert any(
        entry.get("path") == "landing-note.md"
        for entry in final_manifest["content_entries"]
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
            "FAKE_PARTIAL_RUNTIME_FINAL_MANIFEST_ANCHOR",
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
    assert execution["validation_cwd"] == str(ACTOR_EXECUTION_ROOT)
    assert execution["validation_wrapper_argv"] == [
        "/usr/bin/env",
        "-C",
        str(ACTOR_EXECUTION_ROOT),
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
            '/usr/bin/zsh -lc "/usr/bin/nl -ba docs/ONE.md | '
            "/usr/bin/sed -n '1,5p'; /usr/bin/nl -ba docs/TWO.md | "
            "/usr/bin/sed -n '6,10p'\""
        ),
    ),
)
def test_effect_observer_does_not_block_fixed_read_commands(command: str) -> None:
    assert RUNTIME._command_effects(command) == set()


def test_git_tag_listing_is_read_only_but_creation_remains_forbidden() -> None:
    assert RUNTIME._command_effects("/usr/bin/git tag --list") == set()
    assert RUNTIME._command_effects("/usr/bin/git tag v1") == {"tag"}
    assert RUNTIME._command_effects("/usr/bin/git tag --list --delete v1") == {"tag"}


def test_sandbox_confined_policy_admits_local_indirection_only_under_exact_posture() -> (
    None
):
    command = "/usr/bin/python3 -c 'print(42)'"
    task = {
        "allowed_effect_class": "repo_mutation",
        "indirect_command_policy": "sandbox_confined",
        "forbidden_effects": sorted(RUNTIME.RUNTIME_WIDE_FORBIDDEN_EFFECTS),
    }
    binding = SimpleNamespace(
        permission_posture=IncarnationPermissionPosture(
            sandbox_mode="workspace_write",
            approval_policy="never",
            allowed_effect_classes=("repo_mutation",),
            network_access="disabled",
            secret_access=False,
            external_effects=False,
        )
    )
    commands = [{"command": command, "status": "completed", "exit_code": 0}]

    assert (
        RUNTIME.ExternalCodexRuntime._forbidden_effects(None, commands, task, binding)
        == []
    )
    assert RUNTIME.ExternalCodexRuntime._forbidden_effects(
        None, commands, {**task, "indirect_command_policy": "fail_closed"}, binding
    ) == ["unclassified_indirect_effect"]
    assert RUNTIME.ExternalCodexRuntime._forbidden_effects(
        None,
        [
            {
                "command": "/usr/bin/curl -X POST https://example.invalid/upload",
                "status": "completed",
                "exit_code": 0,
            }
        ],
        task,
        binding,
    ) == ["publication"]


def test_prepared_read_only_reviewer_admits_real_composite_command_shape_only_under_exact_posture() -> (
    None
):
    command = (
        '/usr/bin/zsh -lc "base=/srv/actor-inputs; '
        'for id in 001 002; do /usr/bin/wc -l < \\"$base/$id.input\\"; done"'
    )
    task = {
        "allowed_effect_class": "read_only",
        "indirect_command_policy": "sandbox_confined",
        "forbidden_effects": sorted(RUNTIME.RUNTIME_WIDE_FORBIDDEN_EFFECTS),
    }
    exact_binding = SimpleNamespace(
        permission_posture=IncarnationPermissionPosture(
            sandbox_mode="read_only",
            approval_policy="never",
            allowed_effect_classes=("read_only",),
            network_access="disabled",
            secret_access=False,
            external_effects=False,
        )
    )
    widened_binding = SimpleNamespace(
        permission_posture=SimpleNamespace(
            sandbox_mode="read_only",
            approval_policy="never",
            allowed_effect_classes=("read_only",),
            network_access="enabled",
            secret_access=False,
            external_effects=False,
        )
    )
    commands = [{"command": command, "status": "completed", "exit_code": 0}]

    assert RUNTIME._command_has_unclassified_indirection(command) is True
    assert (
        RUNTIME.ExternalCodexRuntime._forbidden_effects(
            None, commands, task, exact_binding
        )
        == []
    )
    assert RUNTIME.ExternalCodexRuntime._forbidden_effects(
        None, commands, task, widened_binding
    ) == ["unclassified_indirect_effect"]


def test_indirect_interpreter_effect_is_unclassified_but_fixed_validation_is_admitted() -> (
    None
):
    command = "/usr/bin/python3 -c 'print(42)'"
    assert RUNTIME._command_has_unclassified_indirection(command) is True
    assert (
        RUNTIME._command_has_unclassified_indirection(
            "/usr/bin/bash -c '/usr/bin/rg -n fixture README.md'"
        )
        is False
    )


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
        "/usr/bin/timeout 5 /usr/bin/env RIPGREP_CONFIG_PATH=./rg.conf "
        "/usr/bin/rg needle input",
        "/usr/bin/command /usr/bin/timeout 5 /usr/bin/env "
        "RIPGREP_CONFIG_PATH=./rg.conf /usr/bin/rg needle input",
    ),
)
def test_wrapped_environment_overrides_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_timeout_without_environment_override_remains_classifiable() -> None:
    assert (
        RUNTIME._command_has_unclassified_indirection(
            "/usr/bin/timeout 5 /usr/bin/rg needle input"
        )
        is False
    )


def test_timeout_wrapped_shell_body_is_recursively_classified() -> None:
    command = "/usr/bin/timeout 5 /usr/bin/bash -c '/usr/bin/python -c pass'"
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_timeout_wrapped_shell_body_preserves_forbidden_effects() -> None:
    command = "/usr/bin/timeout 5 /usr/bin/bash -c '/usr/bin/git push'"
    assert "push" in RUNTIME._command_effects(command)


def test_timeout_wrapped_safe_shell_body_remains_classifiable() -> None:
    command = "/usr/bin/timeout 5 /usr/bin/bash -c '/usr/bin/rg needle input'"
    assert RUNTIME._command_has_unclassified_indirection(command) is False


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
    assert (
        RUNTIME._command_has_unclassified_indirection("/usr/bin/sort -u input") is False
    )


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/sort -o .git/HEAD newhead",
        "/usr/bin/sort -o.git/HEAD newhead",
        "/usr/bin/sort --output .git/HEAD newhead",
        "/usr/bin/sort --output=.git/HEAD newhead",
        "/usr/bin/sort --out=/tmp/repo/.git/HEAD newhead",
    ),
)
def test_sort_git_metadata_output_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/sort -o report.txt input",
        "/usr/bin/sort -oreport.txt input",
        "/usr/bin/sort --output=report.txt input",
    ),
)
def test_sort_ordinary_output_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


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
    assert (
        RUNTIME._command_has_unclassified_indirection("/usr/bin/git show-ref --heads")
        is False
    )


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
    command = "/usr/bin/bash -O extglob -c '/usr/bin/true'"

    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert tokenizations[-1] == ("/usr/bin/true",)
    assert incomplete is False
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/bash -lc '/usr/bin/true'",
        "/usr/bin/bash --login -c '/usr/bin/true'",
        "/usr/bin/bash -ic '/usr/bin/true'",
        "/usr/bin/zsh -lc '/usr/bin/true'",
        "/usr/bin/sh -ilc '/usr/bin/true'",
    ),
)
def test_shell_login_and_interactive_startup_are_fail_closed(command: str) -> None:
    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert tokenizations[-1] == ("/usr/bin/true",)
    assert incomplete is False
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_login_shell_body_effects_remain_visible() -> None:
    command = "/usr/bin/bash -lc '/usr/bin/git push; /usr/bin/true'"

    assert "push" in RUNTIME._command_effects(command)
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_zsh_unconditional_global_startup_is_fail_closed() -> None:
    command = "/usr/bin/zsh -c '/usr/bin/true'"

    tokenizations, incomplete = RUNTIME._shell_tokenization_analysis(command)

    assert tokenizations[-1] == ("/usr/bin/true",)
    assert incomplete is False
    assert RUNTIME._command_has_unclassified_indirection(command) is True


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
    assert (
        RUNTIME._command_has_unclassified_indirection(
            "/usr/bin/git cat-file -p HEAD:README.md"
        )
        is False
    )


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
        "/usr/bin/git rev-list --format=%G? -1 HEAD",
        "/usr/bin/git rev-list --pretty '%GS' -1 HEAD",
        "/usr/bin/git rev-list --show-signature -1 HEAD",
        "/usr/bin/git rev-list --show-sig -1 HEAD",
        "/usr/bin/git rev-list --pretty=verify -1 HEAD",
        "/usr/bin/git rev-list --format=verify -1 HEAD",
        "/usr/bin/git reflog --format=%G? -1 HEAD",
        "/usr/bin/git reflog show --format=%G? -1 HEAD",
        "/usr/bin/git reflog show --pretty='%GK' -1 HEAD",
        "/usr/bin/git reflog --pretty --show-signature -1 HEAD",
    ),
)
def test_git_revision_signature_formats_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/git rev-list --format=%h -1 HEAD",
        "/usr/bin/git rev-list --pretty -1 HEAD",
        "/usr/bin/git rev-list --pretty=short -1 HEAD",
        "/usr/bin/git rev-list --pretty=format:%h -1 HEAD",
        "/usr/bin/git reflog --format=%h -1 HEAD",
        "/usr/bin/git reflog show --format=%h -1 HEAD",
    ),
)
def test_non_signature_revision_formats_remain_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_git_signature_verifier_program_is_neutralized_for_signed_commit(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    original_commit = subprocess.run(
        ["/usr/bin/git", "-C", str(workspace), "cat-file", "commit", "HEAD"],
        check=True,
        capture_output=True,
    ).stdout
    headers, message = original_commit.split(b"\n\n", 1)
    signed_commit = (
        headers
        + b"\n"
        + b"gpgsig -----BEGIN PGP SIGNATURE-----\n"
        + b" \n"
        + b" Zml4dHVyZQ==\n"
        + b" -----END PGP SIGNATURE-----\n"
        + b"\n"
        + message
    )
    signed_oid = (
        subprocess.run(
            [
                "/usr/bin/git",
                "-C",
                str(workspace),
                "hash-object",
                "-t",
                "commit",
                "-w",
                "--stdin",
            ],
            input=signed_commit,
            check=True,
            capture_output=True,
            text=False,
        )
        .stdout.decode("ascii")
        .strip()
    )
    _git(workspace, "update-ref", "HEAD", signed_oid)
    marker = tmp_path / "configured-verifier-ran"
    helper = tmp_path / "configured-verifier"
    helper.write_text(
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(marker))}\nexit 1\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    _git(workspace, "config", "gpg.program", str(helper))

    unsafe_environment = RUNTIME._base_controller_git_environment()
    unsafe_environment["GIT_CONFIG_COUNT"] = "3"
    for index in range(3, 7):
        unsafe_environment.pop(f"GIT_CONFIG_KEY_{index}")
        unsafe_environment.pop(f"GIT_CONFIG_VALUE_{index}")
    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(workspace),
            "rev-list",
            "--format=%G?",
            "-1",
            "HEAD",
        ],
        env=unsafe_environment,
        check=False,
        capture_output=True,
    )
    assert marker.is_file()
    marker.unlink()

    subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(workspace),
            "rev-list",
            "--format=%G?",
            "-1",
            "HEAD",
        ],
        env=RUNTIME._base_controller_git_environment(),
        check=False,
        capture_output=True,
    )
    assert marker.exists() is False


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


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/jq --rawfile cfg .git/config -n '$cfg'",
        "/usr/bin/jq --slurpfile cfg .git/config.worktree -n '$cfg'",
        "/usr/bin/jq --argfile cfg .git/config.lock -n '$cfg'",
        "/usr/bin/jq . .git/config",
    ),
)
def test_jq_git_config_file_inputs_are_fail_closed(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}
    assert RUNTIME._command_has_unclassified_indirection(command) is True


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
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(filter_marker))}\n/bin/cat\n",
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
    assert environment["GIT_CONFIG_COUNT"] == "8"
    assert environment["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    assert environment["GIT_CONFIG_KEY_1"] == "core.fsmonitor"
    assert environment["GIT_CONFIG_VALUE_1"] == "false"
    assert environment["GIT_CONFIG_KEY_2"] == "core.attributesFile"
    assert environment["GIT_CONFIG_VALUE_2"] == "/dev/null"
    assert environment["GIT_CONFIG_KEY_3"] == "gpg.program"
    assert environment["GIT_CONFIG_KEY_4"] == "gpg.openpgp.program"
    assert environment["GIT_CONFIG_KEY_5"] == "gpg.x509.program"
    assert environment["GIT_CONFIG_KEY_6"] == "gpg.ssh.program"
    assert all(
        environment[f"GIT_CONFIG_VALUE_{index}"] == "/usr/bin/false"
        for index in range(3, 7)
    )
    assert environment["GIT_CONFIG_KEY_7"] == "filter.leak.smudge"
    assert environment["GIT_CONFIG_VALUE_7"] == ""
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
    assert RUNTIME._command_effects("/usr/bin/base64 /home/operator/.ssh/id_rsa") == {
        "secret_access"
    }


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/cat client_secret.json",
        "/usr/bin/grep needle client_secret.json",
        "/usr/bin/head credentials.json",
        "/usr/bin/file -m client_secret.json input.txt",
        "/usr/bin/jq . credentials.json",
        "/usr/bin/uniq token.txt output.txt",
    ),
)
def test_direct_reader_bare_secret_file_operands_are_classified(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/echo client_secret.json",
        "/usr/bin/diff --label client_secret.json left right",
        "/usr/bin/file -F client_secret.json input.txt",
        "/usr/bin/grep client_secret.json README.md",
        "/usr/bin/jq --arg name client_secret.json -n '$name'",
        "/usr/bin/uniq input.txt client_secret.json",
    ),
)
def test_non_file_and_output_bare_secret_words_do_not_add_secret_access(
    command: str,
) -> None:
    assert "secret_access" not in RUNTIME._command_effects(command)


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/date -f.env",
        "/usr/bin/date -uf.env",
        "/usr/bin/date -f.git/config",
    ),
)
def test_date_attached_file_operand_cannot_hide_secret_reads(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


def test_date_ordinary_attached_file_operand_remains_classifiable() -> None:
    command = "/usr/bin/date -fdates.txt"
    assert RUNTIME._command_effects(command) == set()
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/file -f.env",
        "/usr/bin/file -0f.env",
        "/usr/bin/file -f.git/config",
    ),
)
def test_file_attached_namefile_cannot_hide_secret_reads(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


def test_file_ordinary_attached_namefile_remains_classifiable() -> None:
    command = "/usr/bin/file -fnames.txt"
    assert RUNTIME._command_effects(command) == set()
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/uniq newhead .git/HEAD",
        "/usr/bin/uniq -f 1 newhead /tmp/repo/.git/HEAD",
        "/usr/bin/uniq --skip-fields=1 -- newhead .git/HEAD",
    ),
)
def test_uniq_git_metadata_output_is_fail_closed(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/uniq input output.txt",
        "/usr/bin/uniq -f1 input output.txt",
        "/usr/bin/uniq --skip-fields 1 input output.txt",
    ),
)
def test_uniq_ordinary_output_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/wc --files0-from=.env",
        "/usr/bin/wc --files0-from .npmrc",
        "/usr/bin/wc --files0-f=.pypirc",
        "/usr/bin/sort --files0-from=.yarnrc.yml",
        "/usr/bin/sort --files0-from .git/config",
    ),
)
def test_file_list_options_cannot_hide_secret_reads(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/find -files0-from client_secret.json -maxdepth 0",
        "/usr/bin/find -files0-from=.npmrc -maxdepth 0",
        "/usr/bin/find client_secret.json -maxdepth 0",
        "/usr/bin/find . -newer credentials.json -print",
        "/usr/bin/find . -newermm token.pem -print",
    ),
)
def test_find_input_coordinates_cannot_hide_secret_reads(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/find -files0-from input-files.list -maxdepth 0",
        "/usr/bin/find input -maxdepth 0",
        "/usr/bin/find . -newer baseline.txt -print",
        "/usr/bin/find . -fprint client_secret.json",
    ),
)
def test_find_non_secret_or_output_coordinates_remain_classifiable(
    command: str,
) -> None:
    assert RUNTIME._command_effects(command) == set()
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/diff --from-file=.env /dev/null",
        "/usr/bin/diff --to-file=.npmrc /dev/null",
        "/usr/bin/diff --exclude-from=.git/config left right",
        "/usr/bin/grep -f.env README.md",
        "/usr/bin/sed -f.git/config README.md",
    ),
)
def test_attached_options_cannot_hide_secret_coordinates(command: str) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/wc --files0-from=input-files.list",
        "/usr/bin/sort --files0-from input-files.list",
        "/usr/bin/diff --from-file=baseline.txt current.txt",
        "/usr/bin/grep -fpatterns.txt README.md",
    ),
)
def test_ordinary_file_options_remain_classifiable(command: str) -> None:
    assert RUNTIME._command_effects(command) == set()
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_direct_repository_git_config_reader_is_fail_closed() -> None:
    command = "/usr/bin/cat .git/config"

    assert RUNTIME._command_effects(command) == {"secret_access"}
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_repository_git_config_lock_reader_is_fail_closed() -> None:
    command = "/usr/bin/cat .git/config.lock"

    assert RUNTIME._command_effects(command) == {"secret_access"}
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/rg -n '.git/config' README.md",
        "/usr/bin/rg -g '*.md' '.git/config' README.md",
        "/usr/bin/echo .git/config",
        "/usr/bin/printf '%s\\n' .git/config",
    ),
)
def test_git_config_text_without_a_file_operand_remains_classifiable(
    command: str,
) -> None:
    assert RUNTIME._command_effects(command) == set()
    assert RUNTIME._command_has_unclassified_indirection(command) is False


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/rg credential .git/config",
        "/usr/bin/rg credential .git/config README.md",
        "/usr/bin/rg -ecredential .git/config",
        "/usr/bin/rg -necredential .git/config",
        "/usr/bin/grep -e credential .git/config.worktree",
        "/usr/bin/grep -necredential .git/config.worktree",
        "/usr/bin/grep credential .git/config.worktree",
        "/usr/bin/sed --sandbox -n p .git/config",
        "/usr/bin/sed --sandbox -ep .git/config",
        "/usr/bin/sed --sandbox -nep .git/config",
        "/usr/bin/rg --ignore-file .git/config credential README.md",
        "/usr/bin/grep --exclude-f=.git/config credential README.md",
        "/usr/bin/grep --exclude-f .git/config credential README.md",
        "/usr/bin/grep --reg=credential .git/config",
        "/usr/bin/grep --reg=credential /other/repo/.git/config",
        "/usr/bin/sed --sandbox --fil=.git/config README.md",
        "/usr/bin/sed --sandbox --expr=p .git/config",
    ),
)
def test_pattern_reader_git_config_file_operands_are_fail_closed(
    command: str,
) -> None:
    assert RUNTIME._command_effects(command) == {"secret_access"}
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/cp --target-directory=.git shallow",
        "/usr/bin/cp --target=.git shallow",
        "/usr/bin/cp -t.git shallow",
        "/usr/bin/mv -t .git shallow",
        "/usr/bin/install --target-directory=.git shallow",
        "/usr/bin/ln --target-directory=.git shallow",
    ),
)
def test_attached_git_metadata_mutator_destinations_are_fail_closed(
    command: str,
) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


def test_actor_git_mask_preserves_linked_worktree_and_masks_both_configs(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    _git(repository, "config", "user.name", "Fixture")
    (repository / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-m", "fixture")
    linked = tmp_path / "linked"
    _git(repository, "worktree", "add", "-b", "actor", str(linked))
    _git(repository, "config", "extensions.worktreeConfig", "true")
    _git(
        linked,
        "config",
        "--worktree",
        "http.https://example.invalid/.extraHeader",
        "Authorization: Bearer FAKE_WORKTREE_CONFIG_MARKER",
    )
    (linked / "landing-note.md").write_text("bounded change\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(linked, scratch)
    targets = {Path(item["target"]) for item in mask["masks"]}
    common_config = Path(_git(linked, "rev-parse", "--git-path", "config")).resolve()
    worktree_config = Path(
        _git(linked, "rev-parse", "--git-path", "config.worktree")
    ).resolve()
    sanitized_config = Path(mask["sanitized_config_path"])

    assert {
        common_config,
        common_config.with_name("config.lock"),
        worktree_config,
        worktree_config.with_name("config.worktree.lock"),
    }.issubset(targets)
    assert "FAKE_WORKTREE_CONFIG_MARKER" not in sanitized_config.read_text(
        encoding="utf-8"
    )
    observed = RUNTIME._masked_git_command(
        linked,
        mask,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    assert observed.returncode == 0
    assert RUNTIME._parse_git_status(observed.stdout) == RUNTIME._git_status(linked)
    for config_path in (common_config, worktree_config):
        direct = RUNTIME._run_actor_masked_command(
            mask,
            ("/usr/bin/cat", str(config_path)),
            environment=dict(os.environ),
        )
        assert direct.returncode == 0
        assert "FAKE_WORKTREE_CONFIG_MARKER" not in direct.stdout
    nested_write_probe = worktree_config.parent / "actor-write-probe"
    direct = RUNTIME._run_actor_masked_command(
        mask,
        ("/usr/bin/touch", str(nested_write_probe)),
        environment=dict(os.environ),
    )
    assert direct.returncode != 0
    assert not nested_write_probe.exists()


def test_actor_git_mask_preserves_native_split_index_and_refs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    _git(workspace, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(workspace, "update-index", "--split-index")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    source_shared_indexes = tuple((workspace / ".git").glob("sharedindex.*"))

    assert source_shared_indexes
    resolved_remote = RUNTIME._masked_git_command(
        workspace,
        mask,
        "rev-parse",
        "origin/main",
    )
    assert resolved_remote.returncode == 0
    assert resolved_remote.stdout.strip() == _git(workspace, "rev-parse", "HEAD")
    completed = RUNTIME._masked_git_command(
        workspace,
        mask,
        "diff",
        "origin/main...HEAD",
    )
    assert completed.returncode == 0


def test_actor_git_mask_hides_existing_config_lockfiles(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    config = workspace / ".git" / "config"
    config_lock = workspace / ".git" / "config.lock"
    config_lock.write_text(
        config.read_text(encoding="utf-8")
        + '[http "https://example.invalid/"]\n'
        + "\textraHeader = Authorization: Bearer FAKE_LOCK_MARKER\n",
        encoding="utf-8",
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    targets = {Path(item["target"]) for item in mask["masks"]}
    observed = RUNTIME._run_actor_masked_command(
        mask,
        ("/usr/bin/cat", str(config_lock)),
        environment=dict(os.environ),
    )

    assert config_lock in targets
    assert workspace / ".git" / "config.worktree.lock" in targets
    assert observed.returncode == 0
    assert "FAKE_LOCK_MARKER" not in observed.stdout
    assert "FAKE_LOCK_MARKER" in config_lock.read_text(encoding="utf-8")


def test_actor_git_mask_keeps_absent_reserved_targets_out_of_host(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    reserved = (
        workspace / ".git" / "config.lock",
        workspace / ".git" / "config.worktree",
        workspace / ".git" / "config.worktree.lock",
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    observed = RUNTIME._run_actor_masked_command(
        mask,
        ("/usr/bin/true",),
        environment=dict(os.environ),
    )

    assert observed.returncode == 0
    assert not any(path.exists() for path in reserved)
    _git(workspace, "config", "test.private-view", "preserved")
    assert _git(workspace, "config", "--get", "test.private-view") == "preserved"


def test_actor_git_mask_preserves_reftable_repository_structure(
    tmp_path: Path,
) -> None:
    git_init_help = subprocess.run(
        ["/usr/bin/git", "init", "-h"],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if "--ref-format" not in git_init_help.stdout + git_init_help.stderr:
        pytest.skip("installed Git cannot create a reftable repository")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "--ref-format=reftable", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    sanitized = Path(mask["sanitized_config_path"]).read_text(encoding="utf-8")
    observed = RUNTIME._masked_git_command(
        workspace,
        mask,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )

    assert "repositoryFormatVersion = 1" in sanitized
    assert "refStorage = reftable" in sanitized
    assert observed.returncode == 0
    assert RUNTIME._parse_git_status(observed.stdout) == RUNTIME._git_status(workspace)


def test_actor_git_mask_preserves_case_sensitivity_semantics(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "foo").write_text("tracked\n", encoding="utf-8")
    _git(workspace, "add", "foo")
    _git(workspace, "commit", "-m", "fixture")
    _git(workspace, "config", "core.ignoreCase", "true")
    (workspace / "FOO").write_text("case variant\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    sanitized = Path(mask["sanitized_config_path"]).read_text(encoding="utf-8")
    observed = RUNTIME._masked_git_command(
        workspace,
        mask,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )

    assert "ignoreCase = true" in sanitized
    assert RUNTIME._parse_git_status(observed.stdout) == RUNTIME._git_status(workspace)


def test_actor_git_mask_normalizes_local_status_rename_display(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "before.txt").write_text("rename fixture\n", encoding="utf-8")
    _git(workspace, "add", "before.txt")
    _git(workspace, "commit", "-m", "fixture")
    _git(workspace, "mv", "before.txt", "after.txt")
    _git(workspace, "config", "status.renames", "false")
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    observed = RUNTIME._masked_git_command(
        workspace,
        mask,
        "status",
        "--no-renames",
        "--porcelain=v1",
        "--untracked-files=all",
    )

    assert observed.returncode == 0
    assert RUNTIME._parse_git_status(observed.stdout) == RUNTIME._git_status(workspace)


def test_actor_git_mask_rejects_core_worktree_redirect(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    redirected = tmp_path / "redirected"
    workspace.mkdir()
    redirected.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("same\n", encoding="utf-8")
    (redirected / "README.md").write_text("same\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    _git(workspace, "config", "core.worktree", str(redirected))
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME._prepare_actor_git_mask(workspace, scratch)

    assert exc_info.value.code == "workspace_git_metadata_invalid"


def test_actor_git_mask_preserves_exact_core_worktree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "core.worktree", str(workspace))
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    sanitized = Path(mask["sanitized_config_path"]).read_text(encoding="utf-8")

    assert f'workTree = "{workspace}"' in sanitized


def test_current_mount_aliases_cover_bind_mounted_repository_alias(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(
        repository,
        "config",
        "http.https://example.invalid/.extraHeader",
        "Authorization: Bearer FAKE_BIND_ALIAS_MARKER",
    )
    alias = tmp_path / "alias"
    alias.mkdir()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    script = (
        "import importlib.util,json,pathlib,sys;"
        f"p=pathlib.Path({str(CONTROLLER_PATH)!r});"
        "s=importlib.util.spec_from_file_location('mount_alias_runtime',p);"
        "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;"
        "s.loader.exec_module(m);"
        f"w=pathlib.Path({str(alias)!r});"
        f"x=pathlib.Path({str(scratch)!r});"
        "mask=m._prepare_actor_git_mask(w,x);"
        "print(json.dumps({'targets':[v['target'] for v in mask['masks']],"
        "'sanitized':pathlib.Path(mask['sanitized_config_path']).read_text()}))"
    )
    completed = subprocess.run(
        [
            "/usr/bin/bwrap",
            "--die-with-parent",
            "--dev-bind",
            "/",
            "/",
            "--bind",
            str(repository),
            str(alias),
            "--",
            sys.executable,
            "-c",
            script,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=dict(os.environ),
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    targets = {Path(value) for value in result["targets"]}
    assert {
        repository / ".git" / "config",
        repository / ".git" / "config.lock",
        alias / ".git" / "config",
        alias / ".git" / "config.lock",
    }.issubset(targets)
    assert "FAKE_BIND_ALIAS_MARKER" not in result["sanitized"]


def test_actor_git_mask_does_not_redirect_nested_repository_commands(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-m", "fixture")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    mask = RUNTIME._prepare_actor_git_mask(workspace, scratch)
    nested = tmp_path / "nested"

    initialized = RUNTIME._masked_git_command(
        workspace,
        mask,
        "init",
        "-b",
        "nested",
        str(nested),
    )
    observed = RUNTIME._masked_git_command(
        workspace,
        mask,
        "-C",
        str(nested),
        "status",
        "--short",
    )

    assert initialized.returncode == 0
    assert observed.returncode == 0
    assert (nested / ".git" / "HEAD").read_text(encoding="utf-8") == (
        "ref: refs/heads/nested\n"
    )


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/tee .git/HEAD",
        "/usr/bin/touch .git/refs/heads/redirected",
        "/usr/bin/sed -i s/main/other/ .git/HEAD",
    ),
)
def test_generic_repository_git_metadata_writers_are_fail_closed(
    command: str,
) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/find . -maxdepth 0 -fprint .git/HEAD",
        "/usr/bin/find . -maxdepth 0 -fprint0 .git/refs/heads/main",
        "/usr/bin/find . -maxdepth 0 -fprintf .git/HEAD '%p\\n'",
        "/usr/bin/find . -maxdepth 0 -fls /tmp/repo/.git/index",
    ),
)
def test_find_output_actions_cannot_mutate_git_metadata(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is True


@pytest.mark.parametrize(
    "command",
    (
        "/usr/bin/find . -maxdepth 1 -print",
        "/usr/bin/find . -maxdepth 0 -fprint inventory.txt",
        "/usr/bin/find . -maxdepth 0 -fprintf report.txt '%p\\n'",
    ),
)
def test_ordinary_find_output_remains_classifiable(command: str) -> None:
    assert RUNTIME._command_has_unclassified_indirection(command) is False


def test_ordinary_source_reader_and_writer_remain_classifiable() -> None:
    assert (
        RUNTIME._command_has_unclassified_indirection("/usr/bin/cat README.md") is False
    )
    assert (
        RUNTIME._command_has_unclassified_indirection("/usr/bin/tee landing-note.md")
        is False
    )


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
    assert "push" in runtime._failure_authority_effects(result["executed_commands"])


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

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["failure_code"] == "authority_boundary_crossed"
    assert result["source_manifest_match"] is False
    assert result["thread_id"] is None
    authority_events = [
        event
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
        if event["event_type"] == "external_agent.failure_authority_drift_detected"
    ]
    assert authority_events[-1]["payload"]["source_drift"] is True
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
    assert {item["path"] for item in result["changed_paths"]} == {"cache/output.txt"}


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


def test_ignored_npmrc_blocks_manifest_and_direct_read_before_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init", "-b", "main")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / ".gitignore").write_text(".npmrc\n", encoding="utf-8")
    _git(workspace, "add", ".gitignore")
    _git(workspace, "commit", "-m", "fixture")
    npmrc = workspace / ".npmrc"
    npmrc.write_text("//registry.example/:_authToken=must-not-leak\n", encoding="utf-8")
    original_sha256_file = RUNTIME.sha256_file

    def guarded_sha256_file(path: Path) -> str:
        if path == npmrc:
            pytest.fail("credential-bearing ignored file was hashed")
        return original_sha256_file(path)

    monkeypatch.setattr(RUNTIME, "sha256_file", guarded_sha256_file)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        RUNTIME.build_workspace_manifest(workspace)

    assert exc_info.value.code == "workspace_secret_path_present"
    assert RUNTIME._command_effects("/usr/bin/cat .npmrc") == {"secret_access"}


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
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(filter_marker))}\n/bin/cat\n",
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
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(marker))}\nexit 1\n",
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
        item for item in baseline["content_entries"] if item["path"] == "tracked.txt"
    )
    current_entry = next(
        item for item in current["content_entries"] if item["path"] == "tracked.txt"
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
        ".npmrc",
        ".pypirc",
        ".yarnrc.yml",
        ".docker/config.json",
        ".kube/config",
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
    assert result["workspace_manifest_match"] is True
    assert result["source_manifest_match"] is None
    assert result["actor_final_manifest_ref"] is not None
    assert result["source_manifest_final_ref"] is None
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
        projection_fd: int | None = None,
    ) -> None:
        original_record_codex_event(
            session_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            line=line,
            projection_fd=projection_fd,
        )
        payload = json.loads(line)
        item = payload.get("item") if payload.get("type") == "item.completed" else None
        if (
            isinstance(item, dict)
            and item.get("type") == "command_execution"
            and str(item.get("command", "")).endswith("git status --short")
        ):
            actor_projection = Path(
                runtime._load_state(session_id)["actor_projection_path"]
            )
            (actor_projection / "landing-note.md").write_text(
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


def test_terminal_validation_suite_may_settle_on_final_workspace_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(
        tmp_path,
        validation_commands=(
            {
                "command_id": "git-status-short",
                "argv": ["git", "status", "--short"],
                "cwd": ".",
            },
            {
                "command_id": "git-status-no-untracked",
                "argv": ["git", "status", "--short", "--untracked-files=no"],
                "cwd": ".",
            },
        ),
    )
    runtime = fixture["runtime"]
    original_record_codex_event = runtime._record_codex_event
    first_validation_observed = False

    def settle_after_first_validation_receipt(
        session_id: str,
        *,
        attempt_id: str,
        attempt_number: int,
        line: bytes,
        projection_fd: int | None = None,
    ) -> None:
        nonlocal first_validation_observed
        payload = json.loads(line)
        item = payload.get("item") if payload.get("type") == "item.completed" else None
        first_validation = (
            not first_validation_observed
            and isinstance(item, dict)
            and item.get("type") == "command_execution"
            and str(item.get("command", "")).endswith("git status --short")
        )
        actor_projection = Path(
            runtime._load_state(session_id)["actor_projection_path"]
        )
        transient_path = actor_projection / "landing-note.md"
        if first_validation:
            first_validation_observed = True
            transient_path.write_text(
                "controller-observed transient command state\n",
                encoding="utf-8",
            )
        original_record_codex_event(
            session_id,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            line=line,
            projection_fd=projection_fd,
        )
        if first_validation:
            transient_path.unlink()

    # The first fixed-command receipt sees a transient controller-side state;
    # the exact second/final command and terminal manifest see the restored
    # bytes. The suite is admissible only because the two exact validations
    # form the complete terminal command suffix and its final receipt binds the
    # final manifest.
    monkeypatch.setattr(
        runtime,
        "_record_codex_event",
        settle_after_first_validation_receipt,
    )
    runtime.start(fixture["launch_path"])

    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "completed"
    assert result is not None
    assert result["failure_code"] is None
    validation_executions = [
        item
        for item in result["executed_commands"]
        if item.get("validation_command_id") is not None
    ]
    assert [item["validation_command_id"] for item in validation_executions] == [
        "git-status-short",
        "git-status-no-untracked",
    ]
    assert (
        validation_executions[0]["workspace_manifest_digest"]
        != validation_executions[1]["workspace_manifest_digest"]
    )


def test_high_token_use_is_counted_without_truncating_agent_work(
    tmp_path: Path,
) -> None:
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


def test_multiple_turns_are_counted_without_truncating_agent_work(
    tmp_path: Path,
) -> None:
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
    interrupted_state = runtime._load_state(fixture["session_id"])
    projection_path = interrupted_state["actor_projection_path"]
    projection_manifest_ref = interrupted_state["actor_baseline_manifest_ref"]
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
    resumed_state = runtime._load_state(fixture["session_id"])
    assert resumed_state["actor_projection_path"] == projection_path
    assert resumed_state["actor_baseline_manifest_ref"] == projection_manifest_ref
    assert {item["execution_root"] for item in result["codex_invocations"]} == {
        str(ACTOR_EXECUTION_ROOT)
    }
    assert result["usage_observation"]["status"] == "partial"
    assert len(result["usage_observation"]["gap_reasons"]) == 1
    preserved_path = (
        runtime._session_dir(fixture["session_id"]) / "attempts/001/runtime-result.json"
    )
    assert _digest_path(preserved_path) == first_result_digest
    closure_path = preserved_path.with_name("runtime-result-evidence-closure.json")
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
    assert (
        _digest_path(Path(events_snapshot_ref["artifact_ref"]))
        == prior_events_ref["artifact_digest"]
    )
    assert (
        _digest_path(Path(prior_events_ref["artifact_ref"]))
        != prior_events_ref["artifact_digest"]
    )
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


def test_workspace_write_resume_continues_from_exact_prior_actor_tree(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    first_terminal = _wait_terminal(runtime, fixture["session_id"])
    first_result = runtime.result(fixture["session_id"])

    assert first_terminal["status"] == "review_required"
    assert first_result is not None
    assert first_result["changed_paths"] == [
        {"path": "landing-note.md", "status": "created"}
    ]
    first_final_ref = first_result["actor_final_manifest_ref"]
    first_delta_ref = first_result["actor_delta_ref"]
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    resume = {
        "schema_version": "abyss_stack_external_codex_resume_v1",
        "session_id": fixture["session_id"],
        "thread_id": first_terminal["thread_id"],
        "after_event_sequence": first_terminal["last_event_sequence"],
        "reason": "review_followup",
        "instruction": "Continue the same bounded writer obligation in its exact actor tree.",
        "previous_result_digest": _digest_path(result_path),
    }
    resume_path = tmp_path / "workspace-write-resume.json"
    _write_json(resume_path, resume)

    resumed = runtime.resume(fixture["session_id"], resume_path)
    assert resumed["status"] == "running"
    second_terminal = _wait_terminal(runtime, fixture["session_id"])
    second_result = runtime.result(fixture["session_id"])

    assert second_terminal["status"] == "review_required"
    assert second_result is not None
    assert second_result["attempt_count"] == 2
    assert second_result["thread_id"] == first_result["thread_id"]
    assert second_result["changed_paths"] == first_result["changed_paths"]
    assert second_result["source_manifest_match"] is True
    assert not (fixture["workspace"] / "landing-note.md").exists()
    preserved_closure = (
        runtime._session_dir(fixture["session_id"])
        / "attempts/001/runtime-result-evidence-closure.json"
    )
    closure = json.loads(preserved_closure.read_text(encoding="utf-8"))
    preserved_sources = [item["source_ref"] for item in closure["preserved_evidence"]]
    assert first_final_ref in preserved_sources
    assert first_delta_ref in preserved_sources


def test_resume_materializes_digest_bound_continuation_evidence(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
        identity_suffix="resume-evidence",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    first_terminal = _wait_terminal(runtime, fixture["session_id"])
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    evidence_raw = (
        "transport audit returned; publication repeat remains held\n"
        f"owner-source={fixture['workspace']}\n"
    ).encode("utf-8")
    evidence_digest = RUNTIME.sha256_bytes(evidence_raw)
    resume = {
        "schema_version": "abyss_stack_external_codex_resume_v1",
        "session_id": fixture["session_id"],
        "thread_id": first_terminal["thread_id"],
        "after_event_sequence": first_terminal["last_event_sequence"],
        "reason": "review_followup",
        "instruction": "Review the exact continuation evidence before returning.",
        "previous_result_digest": _digest_path(result_path),
        "evidence_inputs": [
            {
                "input_id": "transport-audit-handoff",
                "utf8_content": evidence_raw.decode("utf-8"),
                "provenance": {
                    "owner_repo": "codex-goal",
                    "artifact_ref": "task-local:transport-audit-handoff",
                    "source_ref": "goal:transport-audit-handoff",
                    "artifact_digest": evidence_digest,
                    "schema_ref": "task-local/transport-audit-handoff-v1",
                    "schema_version": "task-local-transport-audit-handoff-v1",
                },
            }
        ],
    }
    resume_path = tmp_path / "resume-evidence.json"
    _write_json(resume_path, resume)

    assert runtime.resume(fixture["session_id"], resume_path)["status"] == "running"
    terminal = _wait_terminal(runtime, fixture["session_id"])
    state = runtime._load_state(fixture["session_id"])

    assert terminal["status"] == "review_required"
    actor_input = next(
        item
        for item in state["materialized_task_inputs"]
        if item["input_id"] == "transport-audit-handoff"
    )
    controller_input = next(
        item
        for item in state["controller_materialized_task_inputs"]
        if item["input_id"] == "transport-audit-handoff"
    )
    assert Path(controller_input["path"]).read_bytes() == evidence_raw
    envelope = json.loads(Path(actor_input["path"]).read_text(encoding="utf-8"))
    assert envelope["input_id"] == "transport-audit-handoff"
    assert envelope["payload"] == (
        "transport audit returned; publication repeat remains held\n"
        f"owner-source={ACTOR_EXECUTION_ROOT}\n"
    )
    assert envelope["source_artifact_digest"] == evidence_digest
    assert str(fixture["workspace"]) not in Path(actor_input["path"]).read_text(
        encoding="utf-8"
    )
    prompt = (
        runtime._session_dir(fixture["session_id"]) / "attempts/002/prompt.txt"
    ).read_text(encoding="utf-8")
    assert '"materialized_as": "immutable:transport-audit-handoff"' in prompt
    assert "utf8_content" not in prompt
    execution_schema = Path(
        state["execution_result_schema_ref"]["artifact_ref"]
    ).read_text(encoding="utf-8")
    assert "transport\\\\-audit\\\\-handoff" in execution_schema
    events = runtime.events(fixture["session_id"], after_sequence=-1)
    materialized_event = next(
        event
        for event in events
        if event["event_type"] == "external_agent.resume_evidence_materialized"
    )
    assert materialized_event["payload"]["evidence_inputs"][0]["input_id"] == (
        "transport-audit-handoff"
    )
    assert (
        materialized_event["payload"]["evidence_inputs"][0]["source_artifact_digest"]
        == evidence_digest
    )


def test_resume_rejects_continuation_evidence_digest_mismatch(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WRITE_ALLOWED FAKE_ARTIFACT_PRODUCED",
        role_id="coder",
        task_family="landing_preparation",
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
        identity_suffix="resume-evidence-digest-mismatch",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    first_terminal = _wait_terminal(runtime, fixture["session_id"])
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    prior_result_digest = _digest_path(result_path)
    resume_path = tmp_path / "resume-evidence-digest-mismatch.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": first_terminal["thread_id"],
            "after_event_sequence": first_terminal["last_event_sequence"],
            "reason": "review_followup",
            "instruction": "This evidence must fail closed before inference.",
            "previous_result_digest": prior_result_digest,
            "evidence_inputs": [
                {
                    "input_id": "valid-before-invalid",
                    "utf8_content": "valid bytes\n",
                    "provenance": {
                        "owner_repo": "codex-goal",
                        "artifact_ref": "task-local:valid-before-invalid",
                        "source_ref": "goal:valid-before-invalid",
                        "artifact_digest": RUNTIME.sha256_bytes(b"valid bytes\n"),
                        "schema_ref": "task-local/continuation-evidence-v1",
                        "schema_version": "task-local-continuation-evidence-v1",
                    },
                },
                {
                    "input_id": "transport-audit-handoff",
                    "utf8_content": "different bytes\n",
                    "provenance": {
                        "owner_repo": "codex-goal",
                        "artifact_ref": "task-local:transport-audit-handoff",
                        "source_ref": "goal:transport-audit-handoff",
                        "artifact_digest": "sha256:" + "0" * 64,
                        "schema_ref": "task-local/transport-audit-handoff-v1",
                        "schema_version": "task-local-transport-audit-handoff-v1",
                    },
                },
            ],
        },
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.resume(fixture["session_id"], resume_path)

    assert exc_info.value.code == "resume_evidence_digest_mismatch"
    state = runtime._load_state(fixture["session_id"])
    assert state["status"] == "review_required"
    assert len(state["attempts"]) == 1
    assert _digest_path(result_path) == prior_result_digest
    assert all(
        item["input_id"] not in {"valid-before-invalid", "transport-audit-handoff"}
        for item in state["materialized_task_inputs"]
    )


def test_parent_can_resume_exact_authority_blocked_continuation(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        task_family="landing_ambiguity_stop",
        identity_suffix="authority-parent-followup",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    first_terminal = _wait_terminal(runtime, fixture["session_id"])

    assert first_terminal["status"] == "authority_blocked"
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    resume_path = tmp_path / "authority-parent-followup.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": first_terminal["thread_id"],
            "after_event_sequence": first_terminal["last_event_sequence"],
            "reason": "bounded_repair",
            "instruction": "Apply the exact parent follow-up without widening authority.",
            "previous_result_digest": _digest_path(result_path),
        },
    )

    resumed = runtime.resume(fixture["session_id"], resume_path)
    assert resumed["status"] == "running"
    second_terminal = _wait_terminal(runtime, fixture["session_id"])
    second_result = runtime.result(fixture["session_id"])

    assert second_terminal["status"] == "authority_blocked"
    assert second_result is not None
    assert second_result["thread_id"] == first_terminal["thread_id"]
    assert second_result["attempt_count"] == 2


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
        runtime._session_dir(fixture["session_id"]) / "attempts/001/runtime-result.json"
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


def test_failed_read_only_review_transition_can_resume_exact_thread(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_REVIEW_TRANSITION_MISMATCH_ON_START",
        role_id="reviewer",
        task_family="landing_review",
        identity_suffix="review-transition-followup",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    failed = _wait_terminal(runtime, fixture["session_id"])
    first_result = runtime.result(fixture["session_id"])

    assert failed["status"] == "failed"
    assert first_result is not None
    assert first_result["failure_code"] == "model_report_transition_mismatch"
    assert first_result["workspace_manifest_match"] is True
    assert first_result["changed_paths"] == []
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"
    first_result_digest = _digest_path(result_path)
    resume_path = tmp_path / "review-transition-followup.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": failed["thread_id"],
            "after_event_sequence": failed["last_event_sequence"],
            "reason": "review_followup",
            "instruction": (
                "Preserve the review findings and return them with the exact "
                "task-owned transition binding."
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
    assert result["changed_paths"] == []
    preserved_path = (
        runtime._session_dir(fixture["session_id"]) / "attempts/001/runtime-result.json"
    )
    assert _digest_path(preserved_path) == first_result_digest
    assert any(
        event["event_type"] == "external_agent.failed_review_resume_admitted"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


def test_failed_writer_report_can_resume_exact_thread_without_widening_authority(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker=(
            "FAKE_WRITE_NESTED_ALLOWED FAKE_NESTED_ARTIFACT_PRODUCED "
            "FAKE_INVALID_RUNTIME_FINAL_MANIFEST_ANCHOR_ON_START"
        ),
        identity_suffix="writer-report-followup",
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
        allowed_paths=("actor-output/result.json",),
        source_evidence_paths=("README.md",),
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    failed = _wait_terminal(runtime, fixture["session_id"])
    first_result = runtime.result(fixture["session_id"])

    assert failed["status"] == "failed"
    assert first_result is not None
    assert (
        first_result["failure_code"] == "model_report_runtime_evidence_anchor_invalid"
    )
    assert first_result["source_manifest_match"] is True
    assert first_result["changed_paths"] == [
        {"path": "actor-output", "status": "created"},
        {"path": "actor-output/result.json", "status": "created"},
    ]
    first_result_digest = _digest_path(
        runtime._session_dir(fixture["session_id"]) / "result.json"
    )
    resume_path = tmp_path / "writer-report-followup.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": failed["thread_id"],
            "after_event_sequence": failed["last_event_sequence"],
            "reason": "bounded_repair",
            "instruction": (
                "Return the same completed report with an evidence anchor that "
                "exists literally in the preserved runtime final manifest."
            ),
            "previous_result_digest": first_result_digest,
        },
    )

    wrong_route_path = tmp_path / "writer-report-wrong-route.json"
    wrong_route = json.loads(resume_path.read_text(encoding="utf-8"))
    wrong_route["reason"] = "review_followup"
    _write_json(wrong_route_path, wrong_route)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.resume(fixture["session_id"], wrong_route_path)
    assert exc_info.value.code == "failed_writer_report_resume_unbound"

    assert runtime.resume(fixture["session_id"], resume_path)["status"] == "running"
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "review_required"
    assert result is not None
    assert result["thread_id"] == failed["thread_id"]
    assert result["attempt_count"] == 2
    assert result["failure_code"] is None
    assert result["source_manifest_match"] is True
    assert result["changed_paths"] == [
        {"path": "actor-output", "status": "created"},
        {"path": "actor-output/result.json", "status": "created"},
    ]
    preserved_path = (
        runtime._session_dir(fixture["session_id"]) / "attempts/001/runtime-result.json"
    )
    assert _digest_path(preserved_path) == first_result_digest
    assert any(
        event["event_type"] == "external_agent.failed_writer_report_resume_admitted"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


@pytest.mark.parametrize("legacy_generic_code", (False, True))
def test_provider_capacity_failure_can_resume_exact_thread_and_role(
    tmp_path: Path,
    legacy_generic_code: bool,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_PROVIDER_CAPACITY_FAILURE",
        identity_suffix=(
            "capacity-recovery-legacy"
            if legacy_generic_code
            else "capacity-recovery-current"
        ),
        workspace_write=True,
        exact_baseline=True,
        review_required=True,
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    failed = _wait_terminal(runtime, fixture["session_id"])
    first_result = runtime.result(fixture["session_id"])

    assert failed["status"] == "failed"
    assert first_result is not None
    assert first_result["failure_code"] == "provider_capacity_unavailable"
    assert first_result["changed_paths"] == []
    assert first_result["executed_commands"] == []
    assert first_result["turn_count"] == 0
    assert first_result["source_manifest_match"] is True
    assert first_result["workspace_manifest_match"] is True

    session_dir = runtime._session_dir(fixture["session_id"])
    result_path = session_dir / "result.json"
    preserved_path = session_dir / "attempts/001/runtime-result.json"
    if legacy_generic_code:
        legacy_result = json.loads(result_path.read_text(encoding="utf-8"))
        legacy_result["failure_code"] = "codex_process_failed"
        for path in (result_path, preserved_path):
            path.chmod(0o600)
            _write_json(path, legacy_result)
            path.chmod(0o400)
        closure_path = preserved_path.with_name("runtime-result-evidence-closure.json")
        closure_path.unlink()
        state = runtime._load_state(fixture["session_id"])
        state["result_digest"] = _digest_path(result_path)
        runtime._save_state(state)
    first_result_digest = _digest_path(result_path)
    resume = {
        "schema_version": "abyss_stack_external_codex_resume_v1",
        "session_id": fixture["session_id"],
        "thread_id": failed["thread_id"],
        "after_event_sequence": failed["last_event_sequence"],
        "reason": "capacity_recovery",
        "instruction": (
            "Continue the same role and obligation now that external provider "
            "capacity is available; do not widen scope or authority."
        ),
        "previous_result_digest": first_result_digest,
    }
    resume_path = tmp_path / "capacity-recovery.json"
    _write_json(resume_path, resume)
    wrong_route_path = tmp_path / "capacity-recovery-wrong-route.json"
    wrong_route = dict(resume)
    wrong_route["reason"] = "bounded_repair"
    _write_json(wrong_route_path, wrong_route)

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.resume(fixture["session_id"], wrong_route_path)
    assert exc_info.value.code == "failed_capacity_resume_unbound"

    assert runtime.resume(fixture["session_id"], resume_path)["status"] == "running"
    terminal = _wait_terminal(runtime, fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "review_required"
    assert result is not None
    assert result["thread_id"] == failed["thread_id"]
    assert result["attempt_count"] == 2
    assert result["failure_code"] is None
    assert result["changed_paths"] == []
    assert any(
        event["event_type"] == "external_agent.capacity_recovery_admitted"
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
    )


def test_non_capacity_process_failure_cannot_use_capacity_recovery(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_OTHER_PROCESS_FAILURE",
        identity_suffix="non-capacity-recovery-refused",
    )
    runtime = fixture["runtime"]
    runtime.start(fixture["launch_path"])
    failed = _wait_terminal(runtime, fixture["session_id"])
    result_path = runtime._session_dir(fixture["session_id"]) / "result.json"

    assert failed["status"] == "failed"
    assert runtime.result(fixture["session_id"])["failure_code"] == (
        "codex_process_failed"
    )
    resume_path = tmp_path / "false-capacity-recovery.json"
    _write_json(
        resume_path,
        {
            "schema_version": "abyss_stack_external_codex_resume_v1",
            "session_id": fixture["session_id"],
            "thread_id": failed["thread_id"],
            "after_event_sequence": failed["last_event_sequence"],
            "reason": "capacity_recovery",
            "instruction": "This non-capacity failure must remain terminal.",
            "previous_result_digest": _digest_path(result_path),
        },
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.resume(fixture["session_id"], resume_path)
    assert exc_info.value.code == "failed_terminal_resume_unsupported"


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


@pytest.mark.parametrize("workspace_write", [False, True])
def test_worker_death_promotes_projection_authority_drift(
    tmp_path: Path,
    workspace_write: bool,
) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
        workspace_write=workspace_write,
    )
    runtime = fixture["runtime"]
    running = runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        running = runtime.status(fixture["session_id"])
        if running["worker_pid"] and running["codex_pid"]:
            break
        time.sleep(0.05)
    assert isinstance(running["worker_pid"], int)
    actor_workspace = Path(str(running["actor_projection_path"]))
    (actor_workspace / "unexpected.txt").write_text(
        "authority drift before worker death\n",
        encoding="utf-8",
    )

    os.kill(running["worker_pid"], signal.SIGKILL)
    terminal = runtime.status(fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["status"] == "authority_blocked"
    assert result["failure_code"] == "authority_boundary_crossed"
    assert result["workspace_manifest_match"] is False
    assert result["changed_paths"] == [{"path": "unexpected.txt", "status": "created"}]


def test_worker_death_promotes_owner_source_drift(tmp_path: Path) -> None:
    fixture = _fixture(
        tmp_path,
        objective_marker="FAKE_WAIT_FOR_INTERRUPT",
    )
    runtime = fixture["runtime"]
    running = runtime.start(fixture["launch_path"])
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        running = runtime.status(fixture["session_id"])
        if running["worker_pid"] and running["codex_pid"]:
            break
        time.sleep(0.05)
    assert isinstance(running["worker_pid"], int)
    (fixture["workspace"] / "README.md").write_text(
        "owner source drift before worker death\n",
        encoding="utf-8",
    )

    os.kill(running["worker_pid"], signal.SIGKILL)
    terminal = runtime.status(fixture["session_id"])
    result = runtime.result(fixture["session_id"])

    assert terminal["status"] == "authority_blocked"
    assert result is not None
    assert result["status"] == "authority_blocked"
    assert result["failure_code"] == "authority_boundary_crossed"
    assert result["workspace_manifest_match"] is True
    assert result["source_manifest_match"] is False
    authority_events = [
        event
        for event in runtime.events(fixture["session_id"], after_sequence=-1)
        if event["event_type"] == "external_agent.failure_authority_drift_detected"
    ]
    assert authority_events[-1]["payload"]["source_drift"] is True


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
    ("mutator", "validate_request"),
    (
        (
            lambda request: request.pop("expected_outputs"),
            False,
        ),
        (
            lambda request: request["summon_request"].__setitem__(
                "child_agent_id", "incarnation:fixture:wrong"
            ),
            True,
        ),
    ),
)
def test_summon_request_semantics_fail_closed_before_inference(
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
    validate_request: bool,
) -> None:
    fixture = _fixture(
        tmp_path,
        summon_request_mutator=mutator,
        validate_summon_request=validate_request,
    )
    runtime = fixture["runtime"]
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.preflight(fixture["launch_path"])
    assert exc_info.value.code == "incarnation_task_request_unbound"


def test_preflight_rejects_summon_capability_absent_from_plan(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        summon_request_mutator=lambda request: request["summon_request"].__setitem__(
            "capability_refs", ["fixture:unbound-capability"]
        ),
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(fixture["launch_path"])

    assert exc_info.value.code == "incarnation_task_request_capability_unbound"


def test_preflight_rejects_summon_semantics_that_cannot_export_a2a(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path,
        summon_request_mutator=lambda request: request["summon_request"].__setitem__(
            "session_ref", "session:fixture:foreign"
        ),
    )

    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        fixture["runtime"].preflight(fixture["launch_path"])

    assert exc_info.value.code == "incarnation_task_request_unbound"


def test_a2a_export_accepts_role_first_owner_contour_review(
    tmp_path: Path,
) -> None:
    writer = _fixture(
        tmp_path / "writer",
        identity_suffix="owner-writer",
        owner_contour=True,
        review_required=True,
    )
    writer_runtime = writer["runtime"]
    writer_runtime.start(
        writer["launch_path"],
        owner_request_path=writer["owner_execution_request_path"],
    )
    assert (
        _wait_terminal(writer_runtime, writer["session_id"])["status"]
        == "review_required"
    )
    writer_result_path = (
        writer_runtime._session_dir(writer["session_id"]) / "result.json"
    )
    writer_result = writer_runtime.result(writer["session_id"])
    assert writer_result is not None
    writer_report_path = Path(str(writer_result["report_ref"]["artifact_ref"]))
    writer_result_ref = _provenance(
        "abyss-stack",
        "runtime-results/owner-writer-result.json",
        digest=_digest_path(writer_result_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-result.schema.json"
        ),
        schema_version=str(writer_result["schema_version"]),
    )
    writer_report_ref = _provenance(
        "abyss-stack",
        "runtime-results/owner-writer-report.json",
        digest=_digest_path(writer_report_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-report.schema.json"
        ),
        schema_version="abyss_stack_external_codex_report_v1",
    )
    writer_task_ref = _provenance(
        "abyss-stack",
        "runtime-tasks/owner-writer-task.json",
        digest=_digest_path(writer["task_path"]),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-task.schema.json"
        ),
        schema_version="abyss_stack_external_codex_task_v1",
    )
    reviewer = _fixture(
        tmp_path / "reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="owner-reviewer",
        shared_workspace=writer["workspace"],
        owner_contour=True,
        extra_immutable_inputs=(
            ("writer-result", writer_result_path, writer_result_ref),
            ("writer-report", writer_report_path, writer_report_ref),
            ("writer-task", writer["task_path"], writer_task_ref),
        ),
    )
    reviewer_runtime = reviewer["runtime"]
    reviewer_runtime.start(
        reviewer["launch_path"],
        owner_request_path=reviewer["owner_execution_request_path"],
    )
    assert (
        _wait_terminal(reviewer_runtime, reviewer["session_id"])["status"]
        == "completed"
    )

    exported = writer_runtime.export_a2a_result(
        writer["session_id"],
        reviewer_session_id=reviewer["session_id"],
        reviewer_state_root=reviewer_runtime.state_root,
        summon_request_path=writer["summon_request_path"],
        output_path=tmp_path / "owner-contour-a2a.json",
    )

    assert exported["child_task_result"]["review_outcome"] == "proceed"
    assert (
        exported["child_task_result"]["review_binding_mode"]
        == "owner_contour_immutable_evidence"
    )
    assert exported["writer_thread_id"] != exported["reviewer_thread_id"]

    unbound_reviewer = _fixture(
        tmp_path / "unbound-reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="owner-reviewer-missing-report",
        shared_workspace=writer["workspace"],
        owner_contour=True,
        extra_immutable_inputs=(
            ("writer-result", writer_result_path, writer_result_ref),
            ("writer-task", writer["task_path"], writer_task_ref),
        ),
    )
    unbound_runtime = unbound_reviewer["runtime"]
    unbound_runtime.start(
        unbound_reviewer["launch_path"],
        owner_request_path=unbound_reviewer["owner_execution_request_path"],
    )
    assert (
        _wait_terminal(unbound_runtime, unbound_reviewer["session_id"])["status"]
        == "completed"
    )
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        writer_runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=unbound_reviewer["session_id"],
            reviewer_state_root=unbound_runtime.state_root,
            summon_request_path=writer["summon_request_path"],
            output_path=tmp_path / "unbound-owner-contour-a2a.json",
        )
    assert exc_info.value.code == "a2a_review_not_bound"


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
    review_seed_ref = runtime.issue_review_seed(writer["session_id"])
    workspace_projection_seed = {
        "envelope_path": review_seed_ref["artifact_ref"],
        "envelope_digest": review_seed_ref["artifact_digest"],
    }
    writer_result_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-result.json",
        digest=_digest_path(writer_result_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-result.schema.json"
        ),
        schema_version=str(writer_result["schema_version"]),
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
    writer_source_manifest_path = Path(
        str(writer_result["source_manifest_before_ref"]["artifact_ref"])
    )
    writer_source_manifest_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-workspace-manifest.json",
        digest=_digest_path(writer_source_manifest_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-workspace-manifest.schema.json"
        ),
        schema_version="abyss_stack_external_codex_workspace_manifest_v1",
    )
    writer_actor_final_path = Path(
        str(writer_result["actor_final_manifest_ref"]["artifact_ref"])
    )
    writer_actor_final_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-actor-final-manifest.json",
        digest=_digest_path(writer_actor_final_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-actor-workspace-manifest.schema.json"
        ),
        schema_version="abyss_stack_external_codex_actor_workspace_manifest_v2",
    )
    writer_actor_delta_path = Path(
        str(writer_result["actor_delta_ref"]["artifact_ref"])
    )
    writer_actor_delta_ref = _provenance(
        "abyss-stack",
        "runtime-results/fixture-writer-actor-delta.json",
        digest=_digest_path(writer_actor_delta_path),
        source_ref=str(writer_result["thread_id"]),
        schema_ref=(
            "mechanics/governed-execution/parts/external-codex-agent/schemas/"
            "external-codex-actor-delta.schema.json"
        ),
        schema_version="abyss_stack_external_codex_actor_delta_v1",
    )
    reviewer_actor_inputs = (
        (
            "writer-actor-final-manifest",
            writer_actor_final_path,
            writer_actor_final_ref,
        ),
        ("writer-actor-delta", writer_actor_delta_path, writer_actor_delta_ref),
    )
    reviewer = _fixture(
        tmp_path / "reviewer",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="reviewer",
        state_root=shared_state,
        shared_workspace=writer["workspace"],
        workspace_projection_seed=workspace_projection_seed,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_source_manifest_path,
                writer_source_manifest_ref,
            ),
            *reviewer_actor_inputs,
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
            lock_path = runtime._session_dir(reviewer["session_id"]) / "session.lock"
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
    assert exported["child_task_result"]["reviewed_artifact_path"] == str(
        writer_result_path
    )
    assert output_path.is_file()
    assert reviewer_lock_observed is True
    monkeypatch.setattr(RUNTIME, "_atomic_write_bytes", original_atomic_write)

    family_result_path = runtime._session_dir(reviewer["session_id"]) / "result.json"
    family_state_path = runtime._state_path(reviewer["session_id"])
    original_family_result = family_result_path.read_bytes()
    original_family_state = family_state_path.read_bytes()
    alternate_family_result = json.loads(original_family_result)
    alternate_family_result["task_family"] = "eval_review"
    _write_json(family_result_path, alternate_family_result)
    alternate_family_state = json.loads(original_family_state)
    alternate_family_state["result_digest"] = _digest_path(family_result_path)
    _write_json(family_state_path, alternate_family_state)
    try:
        with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
            runtime.export_a2a_result(
                writer["session_id"],
                reviewer_session_id=reviewer["session_id"],
                summon_request_path=summon_path,
                output_path=tmp_path / "wrong-family-a2a.json",
            )
        assert exc_info.value.code == "a2a_review_not_independent"
    finally:
        family_result_path.write_bytes(original_family_result)
        family_state_path.write_bytes(original_family_state)

    wrong_family_reviewer = _fixture(
        tmp_path / "wrong-family-reviewer",
        role_id="reviewer",
        task_family="eval_review",
        parent_task_id=writer["task_id"],
        identity_suffix="wrong-family-reviewer",
        state_root=shared_state,
        shared_workspace=writer["workspace"],
        workspace_projection_seed=workspace_projection_seed,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_source_manifest_path,
                writer_source_manifest_ref,
            ),
            *reviewer_actor_inputs,
        ),
    )
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.start(wrong_family_reviewer["launch_path"])
    assert exc_info.value.code == "workspace_projection_seed_forbidden"

    writer_state = runtime._load_state(writer["session_id"])
    reviewer_state = runtime._load_state(reviewer["session_id"])

    def controller_input_path(state: Mapping[str, Any], input_id: str) -> Path:
        return next(
            Path(str(item["path"]))
            for item in state["controller_materialized_task_inputs"]
            if item["input_id"] == input_id
        )

    final_publication_refs = (
        Path(str(review_seed_ref["artifact_ref"])),
        writer_result_path,
        Path(str(writer_result["actor_final_manifest_ref"]["artifact_ref"])),
        Path(str(writer_result["actor_delta_ref"]["artifact_ref"])),
        Path(
            str(
                runtime.result(reviewer["session_id"])["actor_final_manifest_ref"][
                    "artifact_ref"
                ]
            )
        ),
        Path(
            str(
                runtime.result(reviewer["session_id"])["actor_delta_ref"][
                    "artifact_ref"
                ]
            )
        ),
        controller_input_path(writer_state, "summon-request"),
        controller_input_path(writer_state, "summon-request-schema"),
        controller_input_path(reviewer_state, "review-summon-request"),
        controller_input_path(reviewer_state, "summon-request-schema"),
    )
    original_snapshot_verify = RUNTIME._verify_a2a_export_snapshot
    for index, artifact_path in enumerate(final_publication_refs, start=1):
        original = artifact_path.read_bytes()
        original_mode = stat.S_IMODE(artifact_path.stat().st_mode)
        injected = False

        def mutate_before_final_snapshot(
            refs: Sequence[tuple[str, Mapping[str, Any]]],
        ) -> None:
            nonlocal injected
            if not injected:
                artifact_path.chmod(0o600)
                artifact_path.write_bytes(original + b"\n")
                injected = True
            original_snapshot_verify(refs)

        monkeypatch.setattr(
            RUNTIME,
            "_verify_a2a_export_snapshot",
            mutate_before_final_snapshot,
        )
        try:
            with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
                runtime.export_a2a_result(
                    writer["session_id"],
                    reviewer_session_id=reviewer["session_id"],
                    summon_request_path=summon_path,
                    output_path=tmp_path / f"interleaved-evidence-{index}.json",
                )
            assert exc_info.value.code in {
                "a2a_artifact_drift",
                "materialized_input_drift",
            }
        finally:
            artifact_path.chmod(0o600)
            artifact_path.write_bytes(original)
            artifact_path.chmod(original_mode)
    monkeypatch.setattr(
        RUNTIME,
        "_verify_a2a_export_snapshot",
        original_snapshot_verify,
    )

    reviewer_result_path = runtime._session_dir(reviewer["session_id"]) / "result.json"
    reviewer_state_path = runtime._state_path(reviewer["session_id"])
    original_reviewer_result = reviewer_result_path.read_bytes()
    original_reviewer_state = reviewer_state_path.read_bytes()
    unseeded_state = json.loads(original_reviewer_state)
    unseeded_state["review_seed_envelope_ref"] = None
    _write_json(reviewer_state_path, unseeded_state)
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "unseeded-reviewer-result.json",
        )
    assert exc_info.value.code == "a2a_review_seed_required"
    reviewer_state_path.write_bytes(original_reviewer_state)

    stale_reviewer = runtime.result(reviewer["session_id"])
    assert stale_reviewer is not None
    changed_reviewer = json.loads(original_reviewer_result)
    changed_reviewer["duration_seconds"] = (
        float(changed_reviewer["duration_seconds"]) + 1.0
    )
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
        writer_source_manifest_path.read_text(encoding="utf-8")
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
            *reviewer_actor_inputs,
        ),
    )
    runtime.start(unbound_reviewer["launch_path"])
    assert (
        _wait_terminal(runtime, unbound_reviewer["session_id"])["status"] == "completed"
    )
    with pytest.raises(RUNTIME.ExternalCodexRuntimeError) as exc_info:
        runtime.export_a2a_result(
            writer["session_id"],
            reviewer_session_id=unbound_reviewer["session_id"],
            summon_request_path=summon_path,
            output_path=tmp_path / "unbound-manifest-child-task-result.json",
        )
    assert exc_info.value.code == "a2a_review_seed_required"

    substituted_summon_path = tmp_path / "substituted-summon-request.json"
    substituted_summon = json.loads(summon_path.read_text(encoding="utf-8"))
    substituted_summon["audit_refs"].append("fixture:substituted")
    substituted_summon["summon_request"]["audit_refs"].append("fixture:substituted")
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
        shared_workspace=writer["workspace"],
        workspace_projection_seed=workspace_projection_seed,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_source_manifest_path,
                writer_source_manifest_ref,
            ),
            *reviewer_actor_inputs,
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
    assert repair_export["child_task_result"]["review_outcome"] == ("return_for_repair")
    assert repair_export["child_task_result"]["remote_task"]["state"] == "failed"

    failed_reviewer = _fixture(
        tmp_path / "failed-reviewer",
        objective_marker="FAKE_INVALID_JSONL",
        role_id="reviewer",
        task_family="landing_review",
        parent_task_id=writer["task_id"],
        identity_suffix="failed-reviewer",
        state_root=shared_state,
        shared_workspace=writer["workspace"],
        workspace_projection_seed=workspace_projection_seed,
        extra_immutable_inputs=(
            ("writer-runtime-result", writer_result_path, writer_result_ref),
            ("writer-model-report", writer_report_path, writer_report_ref),
            (
                "review-workspace-manifest",
                writer_source_manifest_path,
                writer_source_manifest_ref,
            ),
            *reviewer_actor_inputs,
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
    assert {turn["thread_id"] for turn in reentered["turns"]} == {parent_thread_id}
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


def test_parent_turn_disables_tools_before_inference_and_isolates_home(
    tmp_path: Path,
) -> None:
    fixture = _fixture(
        tmp_path / "child",
        role_id="architect",
        task_family="landing_ambiguity_stop",
        identity_suffix="luna-xhigh-parent-passive",
    )
    obligation_path = _parent_reentry_obligation(
        tmp_path,
        fixture,
        reentry_id="reentry:fixture:parent-passive",
    )
    obligation = json.loads(obligation_path.read_text(encoding="utf-8"))
    bridge = RUNTIME.ExternalCodexParentReentry(tmp_path / "reentry-state")
    _, _, realization = bridge._validate_obligation(obligation)
    scratch = tmp_path / "parent-scratch"
    scratch.mkdir()

    environment = bridge._codex_environment(obligation, scratch)
    command = bridge._codex_command(
        obligation,
        realization,
        output_schema=tmp_path / "output.schema.json",
        output_message=tmp_path / "output.json",
        thread_id=None,
    )

    assert Path(environment["HOME"]).parent == scratch
    assert Path(environment["HOME"]).is_dir()
    assert Path(environment["HOME"]).stat().st_mode & 0o777 == 0o500
    disabled = {
        command[index + 1]
        for index, value in enumerate(command[:-1])
        if value == "--disable"
    }
    assert {
        "multi_agent",
        "shell_tool",
        "code_mode_host",
        "apps",
        "browser_use",
        "computer_use",
        "image_generation",
        "view_image",
        "goals",
        "memories",
        "plugins",
        "hooks",
        "tool_suggest",
    }.issubset(disabled)


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
        for line in bridge._events_path(reentry_id)
        .read_text(encoding="utf-8")
        .splitlines()
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
        for line in bridge._events_path(reentry_id)
        .read_text(encoding="utf-8")
        .splitlines()
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
        bridge._reentry_dir(reentry_id) / "turns" / "001-yield-attempt-001"
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
        (bridge._reentry_dir(reentry_id) / "turns").glob("001-yield-attempt-*")
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
        for line in bridge._events_path(reentry_id)
        .read_text(encoding="utf-8")
        .splitlines()
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
        (bridge._reentry_dir(reentry_id) / "turns").glob("002-reentry-attempt-*")
    )
    assert len(attempts) == 1

    monkeypatch.setattr(bridge, "_run_parent_turn", original_run_parent_turn)
    recovered = bridge.reenter_parent(reentry_id, child_result_path)["state"]

    assert recovered["status"] == "reentered"
    assert (
        len(
            list(
                (bridge._reentry_dir(reentry_id) / "turns").glob(
                    "002-reentry-attempt-*"
                )
            )
        )
        == 1
    )


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


def test_owner_contour_mixed_summon_binding_requires_explicit_compatibility() -> None:
    base = RunPlan.model_validate_json(PLAN_FIXTURE.read_text(encoding="utf-8"))
    by_kind = {
        item.artifact_kind: item.artifact_ref
        for item in base.scenario_binding.input_artifact_bindings
    }
    summon_request_ref = by_kind["summon_request"]
    summon_decision_ref = by_kind["summon_decision"].model_copy(
        update={
            "schema_ref": PREPARER.SDK_SUMMON_RESULT_SCHEMA_RELATIVE_PATH.as_posix(),
            "schema_version": PREPARER.SDK_SUMMON_RESULT_SCHEMA_VERSION,
        }
    )
    mixed_scenario = base.scenario_binding.model_copy(
        update={
            "input_artifact_bindings": tuple(
                item
                for item in base.scenario_binding.input_artifact_bindings
                if item.artifact_kind != "summon_decision"
            ),
            "input_refs": (
                *base.scenario_binding.input_refs,
                summon_request_ref,
                summon_decision_ref,
            ),
        }
    )
    mixed_plan = base.model_copy(update={"scenario_binding": mixed_scenario})

    with pytest.raises(
        PREPARER.StudyPreparationError,
        match="one exact canonical summon request/decision",
    ):
        PREPARER._writer_summon_decision_ref(
            plan=mixed_plan,
            task_request_ref=summon_request_ref,
            writer_summon_ref=summon_request_ref,
        )

    decision_ref = PREPARER._writer_summon_decision_ref(
        plan=mixed_plan,
        task_request_ref=summon_request_ref,
        writer_summon_ref=summon_request_ref,
        allow_mixed_binding=True,
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
