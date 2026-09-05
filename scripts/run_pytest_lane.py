#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter, deque
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_ENV = "ABYSS_STACK_TEST_SCHEDULER"
PROCESS_WORKER_LIMIT = 4
# A same-selection matrix showed that sixteen shards reduce repeated process,
# import, and fixture work on the four-worker lane; smaller selections still
# use the adaptive target below.
PROCESS_SHARD_COUNT = 16
PROCESS_SHARD_TARGET_ITEMS = 92
PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV = "PYTEST_DISABLE_PLUGIN_AUTOLOAD"
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
LIVE_FAILURE_MAX_CHARS = 4_000

_LIVE_FAILURES: set[tuple[str, str]] = set()


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
        raise pytest.UsageError(f"missing ${name} for bounded pytest partition")
    return Path(raw)


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    mode = os.environ.get(PARTITION_MODE_ENV)
    if not mode:
        return

    nodeids = [item.nodeid for item in items]
    if len(nodeids) != len(set(nodeids)):
        raise pytest.UsageError("duplicate pytest nodeids cannot form an exact partition")

    if mode == "collect":
        write_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV), nodeids)
        return
    if mode != "shard":
        raise pytest.UsageError(f"unknown bounded pytest partition mode: {mode!r}")

    baseline = read_manifest(_manifest_path_from_env(PARTITION_BASELINE_ENV))
    assignment = read_manifest(_manifest_path_from_env(PARTITION_ASSIGNMENT_ENV))
    if not assignment or not set(assignment).issubset(set(baseline)):
        raise pytest.UsageError("pytest shard assignment is empty or outside the baseline")
    if len(nodeids) != len(assignment) or set(nodeids) != set(assignment):
        raise pytest.UsageError(
            "pytest shard did not collect its explicit assignment exactly once"
        )
    write_manifest(
        _manifest_path_from_env(PARTITION_OBSERVED_ENV),
        nodeids,
    )


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
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


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Publish a bounded failure excerpt while a process-isolated shard runs.

    Pytest normally prints failure tracebacks only when its worker session
    finishes.  The parent still replays the complete shard log at aggregate
    closeout, so this is an early diagnostic signal rather than a replacement
    for the full verdict or traceback.
    """

    if os.environ.get(PARTITION_MODE_ENV) != "shard" or not report.failed:
        return
    key = (report.nodeid, report.when)
    if key in _LIVE_FAILURES:
        return
    _LIVE_FAILURES.add(key)
    excerpt = report.longreprtext.strip()
    if len(excerpt) > LIVE_FAILURE_MAX_CHARS:
        excerpt = excerpt[:LIVE_FAILURE_MAX_CHARS].rstrip() + "\n[pytest-live-failure-truncated]"
    print(
        f"[pytest-live-failure] nodeid={report.nodeid} phase={report.when}\n"
        f"{excerpt}\n",
        file=sys.stderr,
        flush=True,
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


def shard_count_for_selection(test_count: int) -> int:
    """Choose enough shards for the selection without spawning empty work.

    The full CI selection defaults to sixteen shards, as measured on the
    four-worker lane.  Smaller selections keep the 92-item target as a soft
    sizing heuristic instead of paying for unnecessary fresh Python
    interpreters and repeated import/fixture setup.
    """

    if test_count <= 0:
        return 0
    sized = (test_count + PROCESS_SHARD_TARGET_ITEMS - 1) // PROCESS_SHARD_TARGET_ITEMS
    return min(test_count, PROCESS_SHARD_COUNT, max(PROCESS_WORKER_LIMIT, sized))


def _pytest_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault(PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV, "1")
    return environment


def _partition_environment(
    *,
    baseline_path: Path,
    assignment_path: Path | None = None,
    observed_path: Path | None = None,
    result_path: Path | None = None,
) -> dict[str, str]:
    environment = _pytest_environment()
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
    explicit_plugin_args: list[str] | None = None,
    collect_only: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        "-u",
        "-m",
        "pytest",
        "-q",
        "-p",
        "scripts.run_pytest_lane",
    ]
    if collect_only:
        command.append("--collect-only")
    if explicit_plugin_args:
        command.extend(explicit_plugin_args)
    command.extend(selection_args)
    return command


def _explicit_plugin_args(selection_args: list[str]) -> list[str]:
    """Keep caller-selected pytest plugins in every process-isolated child."""

    plugins: list[str] = []
    index = 0
    while index < len(selection_args):
        argument = selection_args[index]
        if argument == "--":
            break
        if argument == "-p" and index + 1 < len(selection_args):
            plugins.extend((argument, selection_args[index + 1]))
            index += 2
            continue
        if argument.startswith("-p") and argument != "-p":
            plugins.append(argument)
        index += 1
    return plugins


def _read_result(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PARTITION_RESULT_SCHEMA:
        raise ValueError(f"unsupported pytest partition result: {path}")
    if not isinstance(payload.get("exitstatus"), int) or not isinstance(
        payload.get("stats"), dict
    ):
        raise ValueError(f"invalid pytest partition result: {path}")
    return payload


def _decode_live_output(raw: bytes) -> str:
    """Decode an in-progress log line without making preview a verdict gate."""

    return raw.decode("utf-8", errors="replace")


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
            flush=True,
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
    parent = os.environ.get("TMPDIR")
    temporary_parent = parent if parent and Path(parent).is_dir() else None
    with tempfile.TemporaryDirectory(
        prefix="abyss-stack-pytest-partitions-",
        dir=temporary_parent,
    ) as temporary_raw:
        temporary = Path(temporary_raw)
        baseline_path = temporary / "baseline.json"
        collect_log = temporary / "collect.log"
        collect_command = _plugin_command(selection_args=extra_args, collect_only=True)
        explicit_plugin_args = _explicit_plugin_args(extra_args)
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

        shard_count = shard_count_for_selection(len(baseline))
        assignments = partition_nodeids(baseline, shard_count=shard_count)
        flattened = [nodeid for assignment in assignments for nodeid in assignment]
        if len(flattened) != len(baseline) or set(flattened) != set(baseline):
            print("[error] pytest partition union does not equal the baseline", file=sys.stderr)
            return 2
        print(
            "[pytest-partition] "
            f"collected={len(baseline)} digest={nodeid_digest(baseline)} "
            f"shards={len(assignments)} workers={min(PROCESS_WORKER_LIMIT, len(assignments))} "
            f"target_items={PROCESS_SHARD_TARGET_ITEMS} "
            f"collect_seconds={collect_elapsed:.2f} exact_union=true overlap=false",
            flush=True,
        )

        pending: deque[int] = deque(range(len(assignments)))
        active: dict[int, tuple[subprocess.Popen[str], Any, Any, float]] = {}
        records: dict[int, dict[str, Any]] = {}

        def drain_output_logs() -> None:
            """Stream durable shard logs without waiting for descriptor EOF."""

            for shard_index, (_process, _output, tail, _started) in list(active.items()):
                while True:
                    line = tail.readline()
                    if not line:
                        break
                    decoded = _decode_live_output(line)
                    for chunk in decoded.splitlines(keepends=True) or [decoded]:
                        print(
                            f"[pytest-shard-live {shard_index + 1}/{len(assignments)}] {chunk}",
                            end="",
                            flush=True,
                        )

        try:
            while pending or active:
                drain_output_logs()
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
                        explicit_plugin_args=explicit_plugin_args,
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
                    tail = log_path.open("rb")
                    active[shard_index] = (process, output, tail, time.monotonic())
                    records[shard_index] = {
                        "assignment": assignment_path,
                        "observed": observed_path,
                        "result": result_path,
                        "log": log_path,
                        "command": command,
                    }

                completed_any = False
                for shard_index, (process, output, tail, started) in list(active.items()):
                    returncode = process.poll()
                    if returncode is None:
                        continue
                    drain_output_logs()
                    tail.close()
                    output.close()
                    records[shard_index]["returncode"] = returncode
                    records[shard_index]["elapsed"] = time.monotonic() - started
                    del active[shard_index]
                    completed_any = True
                if not completed_any and active:
                    time.sleep(0.05)
        except BaseException:
            for process, _output, _tail, _started in active.values():
                process.terminate()
            for process, _output, _tail, _started in active.values():
                process.wait()
            for _process, output, tail, _started in active.values():
                tail.close()
                output.close()
            raise
        drain_output_logs()

        failed = False
        failed_shards: list[int] = []
        totals: Counter[str] = Counter()
        for shard_index in range(len(assignments)):
            record = records[shard_index]
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
    args = build_parser().parse_args(argv)
    extra_args = list(args.pytest_args)
    if extra_args[:1] == ["--"]:
        extra_args = extra_args[1:]

    scheduler = scheduler_plan(args.scheduler)
    if not scheduler["ok"]:
        print(f"[error] {scheduler['error']}", file=sys.stderr, flush=True)
        return 2

    if scheduler["effective"] != "serial" and extra_args and args.scheduler == "auto":
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
        print(f"[run] tests: {subprocess.list2cmdline(command)}", flush=True)
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=_pytest_environment(),
            check=False,
        )
        return completed.returncode
    return run_process_worksteal(extra_args=extra_args)


if __name__ == "__main__":
    raise SystemExit(main())
