#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import site
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTAINMENT_API_PATH = (
    REPO_ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "process-containment"
    / "contained_invocation.py"
)
SCHEDULER_ENV = "ABYSS_STACK_TEST_SCHEDULER"
CONTAINMENT_ACTIVE_ENV = "ABYSS_CONTAINMENT_ACTIVE"
PROCESS_WORKER_LIMIT = 4
PROCESS_SHARD_COUNT = 32
SCHEDULERS = ("auto", "serial", "process-4x32-file-aware")

# These conservative weights came from repeated complete-suite trials. They
# affect queue order only: collection, partition membership, and the exact
# final union proof are independent of every hint. Stale hints can therefore
# cost time but cannot hide or add a test.
TEST_DURATION_HINTS = {
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py": 1.5,
    "mechanics/governed-execution/parts/agent-os-adapter/tests/test_agent_os_runtime_bridge.py": 2.5,
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_projection.py": 2.0,
    "mechanics/inference-pilots/parts/tos-foundation-lab/tests/test_tos_foundation_lab.py": 1.0,
    "mcp/services/abyss-stack-mcp/tests/test_canary.py": 1.0,
    "mechanics/governed-execution/parts/governed-runner/tests/test_governed_runner_review_packets.py": 0.7,
    "tests/test_runtime_lifecycle_user_unit.py": 0.5,
    "mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_runtime_install.py": 0.5,
}
DEFAULT_DURATION_HINT = 0.01

PARTITION_MODE_ENV = "ABYSS_STACK_PYTEST_PARTITION_MODE"
PARTITION_BASELINE_ENV = "ABYSS_STACK_PYTEST_PARTITION_BASELINE"
PARTITION_ASSIGNMENT_ENV = "ABYSS_STACK_PYTEST_PARTITION_ASSIGNMENT"
PARTITION_OBSERVED_ENV = "ABYSS_STACK_PYTEST_PARTITION_OBSERVED"
PARTITION_RESULT_ENV = "ABYSS_STACK_PYTEST_PARTITION_RESULT"
PARTITION_MANIFEST_SCHEMA = "abyss-stack-pytest-partition-manifest-v1"
PARTITION_RESULT_SCHEMA = "abyss-stack-pytest-partition-result-v1"
FORBIDDEN_EXTERNAL_ENVIRONMENT = (
    "TMPDIR",
    "TEMP",
    "TMP",
    "PYTEST_DEBUG_TEMPROOT",
    "PYTEST_ADDOPTS",
    "PYTHONPYCACHEPREFIX",
)
FORBIDDEN_PYTEST_REDIRECTIONS = (
    "--basetemp",
    "--junitxml",
    "--html",
    "--json-report",
    "--cov-report",
    "--result-log",
)
CONTAINMENT_STATUS_CODES = {
    "containment_unsupported": 125,
    "recovery_required": 126,
    "infrastructure_failure": 127,
}


def nodeid_digest(nodeids: list[str]) -> str:
    payload = "\0".join(nodeids).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_manifest(path: Path, nodeids: list[str]) -> None:
    payload = {
        "schema_version": PARTITION_MANIFEST_SCHEMA,
        "count": len(nodeids),
        "digest": nodeid_digest(nodeids),
        "nodeids": nodeids,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_manifest(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PARTITION_MANIFEST_SCHEMA:
        raise ValueError(f"unsupported pytest partition manifest: {path}")
    nodeids = payload.get("nodeids")
    if not isinstance(nodeids, list) or not all(isinstance(item, str) for item in nodeids):
        raise ValueError(f"invalid pytest partition nodeids: {path}")
    if payload.get("count") != len(nodeids):
        raise ValueError(f"pytest partition count mismatch: {path}")
    if payload.get("digest") != nodeid_digest(nodeids):
        raise ValueError(f"pytest partition digest mismatch: {path}")
    if len(nodeids) != len(set(nodeids)):
        raise ValueError(f"duplicate pytest nodeids are not schedulable: {path}")
    return nodeids


def _manifest_path_from_env(name: str) -> Path:
    raw = os.environ.get(name)
    if not raw:
        raise ValueError(f"missing ${name} for bounded pytest partition")
    return Path(raw)


def pytest_collection_modifyitems(
    config: Any,
    items: list[Any],
) -> None:
    mode = os.environ.get(PARTITION_MODE_ENV)
    if not mode:
        return

    nodeids = [item.nodeid for item in items]
    if len(nodeids) != len(set(nodeids)):
        raise ValueError("duplicate pytest nodeids cannot form an exact partition")

    if mode == "collect":
        write_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV), nodeids)
        return
    if mode != "shard":
        raise ValueError(f"unknown bounded pytest partition mode: {mode!r}")

    baseline = read_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV))
    assignment = read_manifest(_manifest_path_from_env(PARTITION_ASSIGNMENT_ENV))
    if not assignment or not set(assignment).issubset(set(baseline)):
        raise ValueError("pytest shard assignment is empty or outside the baseline")
    if len(nodeids) != len(assignment) or set(nodeids) != set(assignment):
        raise ValueError(
            "pytest shard did not collect its explicit assignment exactly once"
        )
    write_manifest(
        _manifest_path_from_env(PARTITION_OBSERVED_ENV),
        nodeids,
    )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if os.environ.get(PARTITION_MODE_ENV) != "shard":
        return
    result_path = _manifest_path_from_env(PARTITION_RESULT_ENV)
    terminal = session.config.pluginmanager.getplugin("terminalreporter")
    stats: dict[str, int] = {}
    if terminal is not None:
        stats = {
            str(key): len(value)
            for key, value in terminal.stats.items()
            if str(key) and isinstance(value, list)
        }
    payload = {
        "schema_version": PARTITION_RESULT_SCHEMA,
        "exitstatus": int(exitstatus),
        "stats": stats,
    }
    result_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def scheduler_plan(requested: str) -> dict[str, Any]:
    if requested not in SCHEDULERS:
        return {
            "ok": False,
            "requested": requested,
            "effective": None,
            "reason": "unknown_scheduler",
            "error": f"unknown scheduler {requested!r}; expected one of {', '.join(SCHEDULERS)}",
        }
    if requested == "serial":
        return {
            "ok": True,
            "requested": requested,
            "effective": "serial",
            "reason": "explicit_serial_rollback",
            "selection_changed": False,
        }
    return {
        "ok": True,
        "requested": requested,
        "effective": "process-4x32-file-aware",
        "reason": "isolated_process_workstealing",
        "worker_limit": PROCESS_WORKER_LIMIT,
        "shard_count": PROCESS_SHARD_COUNT,
        "ordering": "file_aware_duration_hints",
        "selection_proof": "baseline_manifest_exact_union",
        "selection_changed": False,
    }


def build_pytest_command(*, extra_args: list[str]) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", *extra_args]


class ContainmentAdapterError(ValueError):
    """A canonical pytest request cannot be admitted to the namespace profile."""


def _containment_api() -> Any:
    module_name = "abyss_stack_process_containment_api"
    spec = importlib.util.spec_from_file_location(module_name, CONTAINMENT_API_PATH)
    if spec is None or spec.loader is None:
        raise ContainmentAdapterError(f"process-containment API is unavailable: {CONTAINMENT_API_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _reject_external_redirections(extra_args: list[str]) -> None:
    for index, argument in enumerate(extra_args):
        option = argument.split("=", 1)[0]
        if option in FORBIDDEN_PYTEST_REDIRECTIONS or any(
            argument.startswith(prefix + "=") for prefix in FORBIDDEN_PYTEST_REDIRECTIONS
        ):
            raise ContainmentAdapterError(f"external_pytest_redirection:{option}")
        if option in {"-o", "--override-ini"} and index + 1 < len(extra_args):
            setting = extra_args[index + 1].lower()
            if any(token in setting for token in ("basetemp", "tmp", "cache_dir", "junitxml")):
                raise ContainmentAdapterError(f"external_pytest_redirection:{setting}")
        if any(token in argument.lower() for token in ("basetemp=", "tmpdir=", "temproot=")):
            raise ContainmentAdapterError(f"external_pytest_redirection:{argument}")


def _path_values_for_environment(name: str, value: str) -> list[Path]:
    if name == "PYTHONPATH" or name.endswith("_PATH"):
        values = value.split(os.pathsep)
    else:
        values = [value]
    paths: list[Path] = []
    for raw in values:
        if not raw or not raw.startswith("/"):
            raise ContainmentAdapterError(f"runtime_path_must_be_absolute:{name}")
        path = Path(raw)
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise ContainmentAdapterError(f"runtime_path_unavailable:{name}:{raw}") from exc
        if not resolved.is_dir():
            raise ContainmentAdapterError(f"runtime_path_not_directory:{name}:{raw}")
        paths.append(resolved)
    return paths


def _runtime_roots() -> tuple[Path, ...]:
    candidates: list[Path] = []
    candidate_guests: set[str] = set()

    def add(path: Path) -> None:
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return
        if not resolved.is_dir() or resolved == Path("/"):
            return
        guest = str(path if path.is_absolute() else resolved)
        if guest == "/" or resolved == REPO_ROOT:
            return
        if guest not in candidate_guests:
            candidate_guests.add(guest)
            candidates.append(path if path.is_absolute() else resolved)

    executable = Path(sys.executable).resolve(strict=True)
    add(executable.parent.parent)
    for value in (sys.prefix, sys.base_prefix, sys.exec_prefix):
        add(Path(value))
    for key in ("stdlib", "platstdlib", "purelib", "platlib", "scripts"):
        value = sysconfig.get_path(key)
        if value:
            add(Path(value))
    for value in (*site.getsitepackages(), site.getusersitepackages()):
        if value and value != ".":
            add(Path(value))
    for path in _declared_python_package_roots():
        add(path)
    for executable_name in ("git", "sh", "bash", "shellcheck"):
        executable_path = shutil.which(executable_name)
        if executable_path:
            add(Path(executable_path).resolve().parent.parent)
    try:
        linker_probe = subprocess.run(
            ["ldd", str(executable)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        linker_probe = None
    if linker_probe is not None:
        for line in linker_probe.stdout.splitlines():
            for token in line.replace("=>", " ").split():
                if token.startswith("/") and Path(token).is_file():
                    add(Path(token).parent)
    for name, value in os.environ.items():
        if name == "PYTHONPATH" or (name.startswith("AOA_") and name.endswith(("_ROOT", "_PATH"))):
            for path in _path_values_for_environment(name, value):
                add(path)
    return tuple(sorted(candidates, key=str))


def _declared_python_package_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for module_name in ("pytest",):
        module_spec = importlib.util.find_spec(module_name)
        if module_spec is None or not module_spec.origin or module_spec.origin in {"built-in", "frozen"}:
            continue
        origin = Path(module_spec.origin)
        try:
            package_root = origin.parent if module_spec.submodule_search_locations else origin.parent
            package_root = package_root.resolve(strict=True)
        except OSError:
            continue
        candidate = package_root.parent if package_root.name == module_name else package_root
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return tuple(roots)


def _worktree_metadata_roots() -> tuple[Path, ...]:
    """Expose only the read-only Git admin coordinates needed by a linked worktree."""

    git_entry = REPO_ROOT / ".git"
    if not git_entry.is_file():
        return ()
    line = git_entry.read_text(encoding="utf-8").strip()
    prefix = "gitdir:"
    if not line.startswith(prefix):
        return ()
    gitdir = Path(line[len(prefix) :].strip())
    if not gitdir.is_absolute():
        gitdir = (REPO_ROOT / gitdir).resolve()
    if not gitdir.is_dir():
        return ()
    roots = [gitdir, REPO_ROOT]
    commondir_file = gitdir / "commondir"
    if commondir_file.is_file():
        common = Path(commondir_file.read_text(encoding="utf-8").strip())
        if not common.is_absolute():
            common = (gitdir / common).resolve()
        if common.is_dir():
            roots.append(common)
    return tuple(dict.fromkeys(roots))


def _containment_environment(runtime_roots: tuple[Path, ...]) -> dict[str, str]:
    forbidden = sorted(name for name in FORBIDDEN_EXTERNAL_ENVIRONMENT if name in os.environ)
    if forbidden:
        raise ContainmentAdapterError("external_redirection:" + ",".join(forbidden))

    environment: dict[str, str] = {}
    for name in ("LANG", "LC_ALL", "LC_CTYPE", "TZ", "PYTHONHASHSEED", "CI"):
        value = os.environ.get(name)
        if value is not None:
            environment[name] = value

    path_entries: list[str] = []
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if not raw.startswith("/"):
            continue
        path = Path(raw)
        if not path.is_dir():
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if any(resolved == root or root in resolved.parents for root in runtime_roots):
            path_entries.append(str(resolved))
    executable_dir = str(Path(sys.executable).resolve(strict=True).parent)
    if executable_dir not in path_entries:
        path_entries.insert(0, executable_dir)
    environment["PATH"] = os.pathsep.join(path_entries)

    pythonpath = os.environ.get("PYTHONPATH")
    if pythonpath is not None:
        _path_values_for_environment("PYTHONPATH", pythonpath)
    pythonpath_entries = [
        str(path)
        for path in _path_values_for_environment("PYTHONPATH", pythonpath)
    ] if pythonpath is not None else []
    for path in _declared_python_package_roots():
        if str(path) not in pythonpath_entries:
            pythonpath_entries.append(str(path))
    if pythonpath_entries:
        environment["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

    for name, value in os.environ.items():
        if name.startswith("AOA_"):
            if name.endswith(("_ROOT", "_PATH")):
                if "\x00" in name or "\x00" in value:
                    raise ContainmentAdapterError(f"environment_contains_nul:{name}")
                _path_values_for_environment(name, value)
                environment[name] = value
            continue
        if not name.startswith("RUN_"):
            continue
        if "\x00" in name or "\x00" in value:
            raise ContainmentAdapterError(f"environment_contains_nul:{name}")
        if "/" in value or os.pathsep in value:
            continue
        environment[name] = value
    return environment


def _containment_spec(*, mode: str, extra_args: list[str]) -> Any:
    _reject_external_redirections(extra_args)
    api = _containment_api()
    runtime_paths = (*_runtime_roots(), *_worktree_metadata_roots())
    seen_guests: set[str] = set()
    runtime_roots_list = []
    for path in runtime_paths:
        guest = str(path)
        if guest in seen_guests:
            continue
        seen_guests.add(guest)
        runtime_roots_list.append(api.ReadOnlyRoot(host=path, guest=guest))
    runtime_roots = tuple(runtime_roots_list)
    environment = _containment_environment(runtime_roots)
    guest_python = str(Path(sys.executable).resolve(strict=True))
    if mode == "serial":
        command = (guest_python, "-m", "pytest", "-q", "-p", "no:cacheprovider", *extra_args)
    elif mode == "process-4x32-file-aware":
        command = (
            guest_python,
            "/workspace/scripts/run_pytest_lane.py",
            "--contained-process-worksteal",
            *extra_args,
        )
    else:
        raise ContainmentAdapterError(f"unknown_containment_mode:{mode}")
    export_raw = os.environ.get("ABYSS_STACK_PYTEST_EXPORT_ROOT")
    export_root = Path(export_raw).resolve() if export_raw else None
    return api.ContainmentSpec(
        profile_id="pytest-canonical-namespace-v1",
        source_root=api.ReadOnlyRoot(host=REPO_ROOT, guest="/workspace"),
        runtime_roots=runtime_roots,
        command=tuple(str(item) for item in command),
        environment=environment,
        cwd="/workspace",
        export_root=export_root,
        drain_timeout_seconds=10.0,
        termination_grace_seconds=2.0,
    )


def _run_in_containment(*, mode: str, extra_args: list[str]) -> int:
    try:
        spec = _containment_spec(mode=mode, extra_args=extra_args)
        api = _containment_api()
    except ContainmentAdapterError as exc:
        payload = {
            "status": "containment_unsupported",
            "command_started": False,
            "diagnostic": str(exc),
        }
        print("[pytest-containment] " + json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)
        return CONTAINMENT_STATUS_CODES["containment_unsupported"]
    result = api.run_contained(spec)
    receipt = result.receipt if isinstance(result.receipt, dict) else {}
    print(
        "[pytest-containment] "
        + json.dumps(
            {
                "status": result.status,
                "returncode": result.returncode,
                "command_started": result.command_started,
                "receipt": receipt,
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )
    if result.status == "completed":
        return int(result.returncode or 0)
    return CONTAINMENT_STATUS_CODES.get(result.status, 127)


def partition_nodeids(nodeids: list[str], *, shard_count: int) -> list[list[str]]:
    if not nodeids:
        return []
    effective_count = min(shard_count, len(nodeids))
    target_items = (len(nodeids) + effective_count - 1) // effective_count
    by_file: dict[str, list[str]] = {}
    for nodeid in nodeids:
        by_file.setdefault(nodeid.split("::", 1)[0], []).append(nodeid)

    units: list[list[str]] = []
    for file_nodeids in by_file.values():
        unit_count = (
            effective_count
            if len(by_file) == 1
            else (len(file_nodeids) + target_items - 1) // target_items
        )
        if unit_count == 1:
            units.append(file_nodeids)
            continue
        ranked = sorted(
            file_nodeids,
            key=lambda nodeid: (
                hashlib.sha256(nodeid.encode("utf-8")).digest(),
                nodeid,
            ),
        )
        ownership = {
            nodeid: position % unit_count for position, nodeid in enumerate(ranked)
        }
        units.extend(
            [
                nodeid
                for nodeid in file_nodeids
                if ownership[nodeid] == unit_index
            ]
            for unit_index in range(unit_count)
        )

    partitions: list[list[str]] = [[] for _ in range(effective_count)]
    loads = [0] * effective_count
    for unit in sorted(units, key=lambda value: (-len(value), value[0])):
        destination = min(range(effective_count), key=lambda index: (loads[index], index))
        partitions[destination].extend(unit)
        loads[destination] += len(unit)
    populated = [partition for partition in partitions if partition]
    return sorted(
        populated,
        key=lambda partition: (
            -sum(
                TEST_DURATION_HINTS.get(
                    nodeid.split("::", 1)[0],
                    DEFAULT_DURATION_HINT,
                )
                for nodeid in partition
            ),
            partition[0],
        ),
    )


def _partition_environment(
    *,
    baseline_path: Path,
    assignment_path: Path | None = None,
    observed_path: Path | None = None,
    result_path: Path | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment[PARTITION_BASELINE_ENV] = str(baseline_path)
    if assignment_path is None:
        environment[PARTITION_MODE_ENV] = "collect"
        for name in (
            PARTITION_ASSIGNMENT_ENV,
            PARTITION_OBSERVED_ENV,
            PARTITION_RESULT_ENV,
        ):
            environment.pop(name, None)
        return environment
    environment[PARTITION_MODE_ENV] = "shard"
    environment[PARTITION_ASSIGNMENT_ENV] = str(assignment_path)
    environment[PARTITION_OBSERVED_ENV] = str(observed_path)
    environment[PARTITION_RESULT_ENV] = str(result_path)
    return environment


def _plugin_command(
    *,
    selection_args: list[str],
    collect_only: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "scripts.run_pytest_lane",
    ]
    if collect_only:
        command.append("--collect-only")
    command.extend(selection_args)
    return command


def _read_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PARTITION_RESULT_SCHEMA:
        raise ValueError(f"unsupported pytest partition result: {path}")
    if not isinstance(payload.get("exitstatus"), int) or not isinstance(
        payload.get("stats"), dict
    ):
        raise ValueError(f"invalid pytest partition result: {path}")
    return payload


def _replay_failed_shards(
    records: dict[int, dict[str, Any]],
    failed_shards: list[int],
    *,
    shard_count: int,
) -> None:
    for shard_index in failed_shards:
        record = records[shard_index]
        print(
            f"[pytest-failed-shard {shard_index + 1}/{shard_count}]",
            file=sys.stderr,
        )
        print(
            record["log"].read_text(encoding="utf-8"),
            end="",
            file=sys.stderr,
        )
        print(
            "[pytest-failed-shard-result] "
            f"index={shard_index + 1} selected={record['selected']} "
            f"returncode={record['returncode']} "
            f"selection_proof={record['selection_proof']}",
            file=sys.stderr,
            flush=True,
        )


def run_process_worksteal(*, extra_args: list[str]) -> int:
    if os.environ.get(CONTAINMENT_ACTIVE_ENV) != "1":
        print(
            "[error] process work stealing is only valid inside process containment",
            file=sys.stderr,
        )
        return CONTAINMENT_STATUS_CODES["containment_unsupported"]
    parent = os.environ.get("TMPDIR")
    if parent not in {"/tmp", "/var/tmp", "/dev/shm"}:
        print(
            "[error] process work stealing requires a private tmpfs temporary root",
            file=sys.stderr,
        )
        return CONTAINMENT_STATUS_CODES["containment_unsupported"]
    temporary_parent = parent
    with tempfile.TemporaryDirectory(
        prefix="abyss-stack-pytest-partitions-",
        dir=temporary_parent,
    ) as temporary_raw:
        temporary = Path(temporary_raw)
        baseline_path = temporary / "baseline.json"
        collect_log = temporary / "collect.log"
        collect_command = _plugin_command(selection_args=extra_args, collect_only=True)
        collect_started = time.monotonic()
        with collect_log.open("w", encoding="utf-8") as output:
            collected = subprocess.run(
                collect_command,
                cwd=REPO_ROOT,
                env=_partition_environment(baseline_path=baseline_path),
                stdout=output,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        collect_elapsed = time.monotonic() - collect_started
        if collected.returncode != 0 or not baseline_path.is_file():
            print(collect_log.read_text(encoding="utf-8"), file=sys.stderr, end="")
            print(
                f"[error] exact pytest collection failed: returncode={collected.returncode}",
                file=sys.stderr,
            )
            return collected.returncode or 2

        try:
            baseline = read_manifest(baseline_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[error] invalid exact pytest collection: {exc}", file=sys.stderr)
            return 2
        if not baseline:
            print("[error] exact pytest collection selected no tests", file=sys.stderr)
            return 5

        assignments = partition_nodeids(baseline, shard_count=PROCESS_SHARD_COUNT)
        flattened = [nodeid for assignment in assignments for nodeid in assignment]
        if len(flattened) != len(baseline) or set(flattened) != set(baseline):
            print("[error] pytest partition union does not equal the baseline", file=sys.stderr)
            return 2
        print(
            "[pytest-partition] "
            f"collected={len(baseline)} digest={nodeid_digest(baseline)} "
            f"shards={len(assignments)} workers={min(PROCESS_WORKER_LIMIT, len(assignments))} "
            f"collect_seconds={collect_elapsed:.2f} exact_union=true overlap=false",
            flush=True,
        )

        pending: deque[int] = deque(range(len(assignments)))
        active: dict[int, tuple[subprocess.Popen[str], Any, float]] = {}
        records: dict[int, dict[str, Any]] = {}
        try:
            while pending or active:
                while pending and len(active) < PROCESS_WORKER_LIMIT:
                    shard_index = pending.popleft()
                    assignment_path = temporary / f"assignment-{shard_index}.json"
                    observed_path = temporary / f"observed-{shard_index}.json"
                    result_path = temporary / f"result-{shard_index}.json"
                    log_path = temporary / f"shard-{shard_index}.log"
                    write_manifest(assignment_path, assignments[shard_index])
                    output = log_path.open("w", encoding="utf-8")
                    command = _plugin_command(
                        selection_args=assignments[shard_index],
                    )
                    process = subprocess.Popen(
                        command,
                        cwd=REPO_ROOT,
                        env=_partition_environment(
                            baseline_path=baseline_path,
                            assignment_path=assignment_path,
                            observed_path=observed_path,
                            result_path=result_path,
                        ),
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    active[shard_index] = (process, output, time.monotonic())
                    records[shard_index] = {
                        "assignment": assignment_path,
                        "observed": observed_path,
                        "result": result_path,
                        "log": log_path,
                        "command": command,
                    }

                completed_any = False
                for shard_index, (process, output, started) in list(active.items()):
                    returncode = process.poll()
                    if returncode is None:
                        continue
                    output.close()
                    records[shard_index]["returncode"] = returncode
                    records[shard_index]["elapsed"] = time.monotonic() - started
                    del active[shard_index]
                    completed_any = True
                if not completed_any and active:
                    time.sleep(0.1)
        except BaseException:
            for process, output, _started in active.values():
                process.terminate()
                output.close()
            for process, _output, _started in active.values():
                process.wait()
            raise

        failed = False
        failed_shards: list[int] = []
        totals: Counter[str] = Counter()
        for shard_index in range(len(assignments)):
            record = records[shard_index]
            print(f"[pytest-shard {shard_index + 1}/{len(assignments)}]")
            print(record["log"].read_text(encoding="utf-8"), end="")
            try:
                observed = read_manifest(record["observed"])
                result = _read_result(record["result"])
                expected = assignments[shard_index]
                if len(observed) != len(expected) or set(observed) != set(expected):
                    raise ValueError("observed selection differs from assignment")
                if int(result["exitstatus"]) != int(record["returncode"]):
                    raise ValueError("pytest exit status differs from process return code")
                totals.update(
                    {str(key): int(value) for key, value in result["stats"].items()}
                )
                proof = "exact"
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                proof = f"invalid:{exc}"
                failed = True
            if int(record["returncode"]) != 0:
                failed = True
            record["selected"] = len(assignments[shard_index])
            record["selection_proof"] = proof
            if proof != "exact" or int(record["returncode"]) != 0:
                failed_shards.append(shard_index)
            print(
                "[pytest-shard-result] "
                f"index={shard_index + 1} selected={len(assignments[shard_index])} "
                f"returncode={record['returncode']} seconds={record['elapsed']:.2f} "
                f"selection_proof={proof}",
                flush=True,
            )

        print(
            "[pytest-aggregate] "
            f"verdict={'failed' if failed else 'passed'} selected={len(baseline)} "
            f"shards={len(assignments)} outcomes={json.dumps(dict(sorted(totals.items())), sort_keys=True)}",
            flush=True,
        )
        _replay_failed_shards(
            records,
            failed_shards,
            shard_count=len(assignments),
        )
        return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the complete abyss-stack pytest lane with a bounded scheduler."
    )
    parser.add_argument(
        "--scheduler",
        choices=SCHEDULERS,
        default=os.environ.get(SCHEDULER_ENV, "auto"),
        help=(
            "scheduler selection; auto uses bounded process-isolated work stealing "
            f"(default: ${SCHEDULER_ENV} or auto)"
        ),
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="additional pytest arguments after --",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv[:1] == ["--contained-process-worksteal"]:
        return run_process_worksteal(extra_args=raw_argv[1:])
    args = build_parser().parse_args(raw_argv)
    extra_args = list(args.pytest_args)
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    scheduler = scheduler_plan(args.scheduler)
    if not scheduler["ok"]:
        print(f"[error] {scheduler['error']}", file=sys.stderr, flush=True)
        return 2

    if scheduler["effective"] != "serial" and extra_args:
        if args.scheduler != "auto":
            print(
                "[error] explicit process work stealing admits only the complete "
                "default pytest selection; use serial for targeted arguments",
                file=sys.stderr,
                flush=True,
            )
            return 2
        scheduler = {
            "ok": True,
            "requested": args.scheduler,
            "effective": "serial",
            "reason": "targeted_selection_uses_exact_serial_path",
            "selection_changed": False,
        }

    print(
        "[pytest-scheduler] "
        f"requested={scheduler['requested']} effective={scheduler['effective']} "
        f"reason={scheduler['reason']} selection_changed=false",
        flush=True,
    )
    if scheduler["effective"] == "serial":
        command = build_pytest_command(extra_args=extra_args)
        print(f"[run] namespace-owned tests: {subprocess.list2cmdline(command)}", flush=True)
        return _run_in_containment(mode="serial", extra_args=extra_args)
    return _run_in_containment(
        mode="process-4x32-file-aware",
        extra_args=extra_args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
