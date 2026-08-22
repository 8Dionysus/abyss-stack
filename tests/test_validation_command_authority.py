from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace

import pytest

from scripts import ci_gate, release_check, run_pytest_lane, validation_lanes


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "validation" / "validation_lanes.json"


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_manifest_loads_and_names_expected_lanes() -> None:
    manifest = validation_lanes.load_manifest()

    assert set(manifest["lanes"]) >= {
        "source-fast",
        "generated",
        "tests",
        "mechanics-part-local",
        "mcp-services",
        "shellcheck",
        "release",
    }
    assert validation_lanes.lane_command_sequence("release")
    assert validation_lanes.lane_command_sequence("source-fast")


def test_release_check_reads_manifest_backed_release_lane(monkeypatch) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    steps = (
        validation_lanes.CommandStep("first", ("python", "one.py")),
        validation_lanes.CommandStep("second", ("python", "two.py")),
    )

    monkeypatch.setattr(release_check, "release_command_sequence", lambda: steps)
    monkeypatch.setattr(
        release_check,
        "run_step",
        lambda label, command: calls.append((label, command)) or 0,
    )
    monkeypatch.setattr(release_check, "run_parity_step", lambda parity_mode: 0)

    assert release_check.main(["--parity-mode", "synthetic"]) == 0
    assert calls == [("first", ("python", "one.py")), ("second", ("python", "two.py"))]


def test_release_check_returns_artifact_blocker_before_full_suite(monkeypatch) -> None:
    artifact_label = "validate OS Abyss runtime config artifact bundle"
    calls: list[str] = []
    parity_calls: list[str] = []

    def run_step(label: str, command: tuple[str, ...]) -> int:
        calls.append(label)
        return 19 if label == artifact_label else 0

    monkeypatch.setattr(release_check, "run_step", run_step)
    monkeypatch.setattr(
        release_check,
        "run_parity_step",
        lambda parity_mode: parity_calls.append(parity_mode) or 0,
    )

    assert release_check.main(["--parity-mode", "synthetic"]) == 19
    assert calls[-1] == artifact_label
    assert "run tests" not in calls
    assert parity_calls == []


def test_release_check_has_no_inline_command_authority() -> None:
    text = (REPO_ROOT / "scripts" / "release_check.py").read_text(encoding="utf-8")

    assert "COMMANDS =" not in text
    assert "command_sequence(\"release_check\")" in text


def test_ci_gate_dispatches_manifest_lane(monkeypatch) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    steps = (validation_lanes.CommandStep("fake source check", ("python", "--version")),)

    monkeypatch.setattr(ci_gate.validation_lanes, "lane_command_sequence", lambda mode: steps)
    monkeypatch.setattr(
        ci_gate,
        "run_step",
        lambda label, command: calls.append((label, command)) or 0,
    )

    assert ci_gate.run_lane("source-fast") == 0
    assert calls == [("fake source check", ("python", "--version"))]


def test_workflow_routes_reusable_commands_through_ci_gate() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "validate-stack.yml").read_text(
        encoding="utf-8"
    )
    manifest = load_manifest()
    shellcheck_commands = manifest["command_sequences"]["shellcheck"]

    assert "python scripts/ci_gate.py --mode release" in workflow
    assert "python scripts/ci_gate.py --mode shellcheck" in workflow
    assert "run: python scripts/release_check.py" not in workflow
    assert "push:\n    branches:\n      - main\n  pull_request:" in workflow
    assert "group: repo-validation-${{ github.event.pull_request.number || github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "https://github.com/8Dionysus/aoa-sdk" in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-sdk-source\" fetch --depth 1 origin "
        "8a349e5f8ae0d60f840378a91ecea3d101777de0"
    ) in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-agents-source\" fetch --depth 1 origin "
        "5f3936e4bfd67ad33ea608a7d1d1b71a2092da79"
    ) in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-skills-source\" fetch --depth 1 origin "
        "909e59f9d168077d9dc3656bb5afbeb66bfa9c6b"
    ) in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-stats-validator\" fetch --depth 1 origin "
        "85a686a8d6bbcb1b28e8f26ab3d92f946bf8152f"
    ) in workflow
    assert 'python -m pip install "$RUNNER_TEMP/aoa-sdk-source"' in workflow
    assert "AOA_AGENTS_SOURCE_ROOT: ${{ runner.temp }}/aoa-agents-source" in workflow
    assert "AOA_SDK_SOURCE_ROOT: ${{ runner.temp }}/aoa-sdk-source" in workflow
    assert "AOA_SKILLS_SOURCE_ROOT: ${{ runner.temp }}/aoa-skills-source" in workflow
    assert "AOA_STATS_ROOT: ${{ runner.temp }}/aoa-stats-validator" in workflow
    assert "PYTHONPATH: ${{ runner.temp }}/aoa-sdk-source/src" in workflow
    assert "TMPDIR: ${{ runner.temp }}" in workflow
    assert ".deps/aoa-sdk" not in workflow
    assert shellcheck_commands[0]["command"][0] == "shellcheck"


def test_release_lane_runs_release_check_entrypoint_for_parity_stabilization() -> None:
    steps = validation_lanes.lane_command_sequence("release")

    assert len(steps) == 1
    assert steps[0].command[-1] == "scripts/release_check.py"


def test_full_test_sequences_share_the_bounded_scheduler_entrypoint() -> None:
    for sequence in ("tests", "release_check"):
        test_steps = [
            step
            for step in validation_lanes.command_sequence(sequence)
            if step.label == "run tests"
        ]
        assert len(test_steps) == 1
        assert test_steps[0].command[1:] == ("scripts/run_pytest_lane.py",)


def test_release_gate_frontloads_artifact_guard_before_full_suite() -> None:
    labels = [step.label for step in validation_lanes.command_sequence("release_check")]

    assert labels.count("validate OS Abyss runtime config artifact bundle") == 1
    assert labels.count("run tests") == 1
    assert labels.index("validate OS Abyss runtime config artifact bundle") < labels.index(
        "run tests"
    )


def test_pytest_scheduler_uses_process_isolated_workstealing() -> None:
    admitted = run_pytest_lane.scheduler_plan("auto")

    assert admitted == {
        "ok": True,
        "requested": "auto",
        "effective": "process-4x32-file-aware",
        "reason": "isolated_process_workstealing",
        "worker_limit": 4,
        "shard_count": 32,
        "ordering": "file_aware_duration_hints",
        "selection_proof": "baseline_manifest_exact_union",
        "selection_changed": False,
    }


def test_pytest_process_partitions_are_disjoint_and_complete() -> None:
    nodeids = [f"tests/test_example.py::test_{index}" for index in range(19)]
    partitions = run_pytest_lane.partition_nodeids(nodeids, shard_count=8)
    flattened = [nodeid for partition in partitions for nodeid in partition]

    assert len(partitions) == 8
    assert max(map(len, partitions)) - min(map(len, partitions)) <= 1
    assert len(flattened) == len(set(flattened)) == len(nodeids)
    assert set(flattened) == set(nodeids)


def test_pytest_process_partitions_keep_small_files_as_import_units() -> None:
    nodeids = [
        *[f"tests/test_small_a.py::test_{index}" for index in range(3)],
        *[f"tests/test_small_b.py::test_{index}" for index in range(3)],
        *[f"tests/test_large.py::test_{index}" for index in range(20)],
    ]
    partitions = run_pytest_lane.partition_nodeids(nodeids, shard_count=4)

    for path in ("tests/test_small_a.py", "tests/test_small_b.py"):
        owners = [
            index
            for index, partition in enumerate(partitions)
            if any(nodeid.startswith(f"{path}::") for nodeid in partition)
        ]
        assert len(owners) == 1
    large_owners = [
        partition
        for partition in partitions
        if any(nodeid.startswith("tests/test_large.py::") for nodeid in partition)
    ]
    assert len(large_owners) == 3


def test_pytest_process_partitions_queue_measured_slow_units_first() -> None:
    slow_path = (
        "mechanics/governed-execution/parts/external-codex-agent/"
        "tests/test_external_codex_agent.py"
    )
    nodeids = [
        *[f"tests/test_fast.py::test_{index}" for index in range(4)],
        *[f"{slow_path}::test_{index}" for index in range(4)],
    ]

    partitions = run_pytest_lane.partition_nodeids(nodeids, shard_count=2)

    assert all(nodeid.startswith(f"{slow_path}::") for nodeid in partitions[0])


def test_pytest_scheduler_keeps_an_exact_serial_rollback(tmp_path: Path) -> None:
    rollback = run_pytest_lane.scheduler_plan("serial")
    basetemp = tmp_path / "serial"
    command = run_pytest_lane.build_pytest_command(
        extra_args=["tests/test_validation_command_authority.py"],
        basetemp=basetemp,
    )

    assert rollback["reason"] == "explicit_serial_rollback"
    assert rollback["selection_changed"] is False
    assert command[1:] == [
        "-m",
        "pytest",
        "-q",
        "--basetemp",
        str(basetemp),
        "tests/test_validation_command_authority.py",
    ]


def test_pytest_temp_namespace_falls_back_when_actual_candidate_creation_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    debug_root = tmp_path / "debug-root"
    runtime_root = tmp_path / "runtime-root"
    debug_root.mkdir()
    runtime_root.mkdir()
    debug_identity = (debug_root.stat().st_dev, debug_root.stat().st_ino)
    calls: list[tuple[int, str]] = []
    original_mkdir = run_pytest_lane.os.mkdir

    def fake_mkdir(name, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            identity = (os.fstat(dir_fd).st_dev, os.fstat(dir_fd).st_ino)
            calls.append((identity[1], name))
            if identity == debug_identity:
                raise PermissionError("simulated parent became unusable at creation")
        return original_mkdir(name, mode, dir_fd=dir_fd)

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(debug_root))
    monkeypatch.setenv("TMPDIR", str(runtime_root))
    monkeypatch.setattr(run_pytest_lane.os, "mkdir", fake_mkdir)

    with run_pytest_lane.owned_pytest_temp_namespace() as namespace:
        assert namespace.name == run_pytest_lane.PYTEST_TEMP_BASETEMP_NAME
        assert namespace.parent.parent == runtime_root

    assert len(calls) == 2
    assert calls[0][0] == debug_root.stat().st_ino
    assert calls[1][0] == runtime_root.stat().st_ino
    assert all(name.startswith(run_pytest_lane.PYTEST_TEMP_PREFIX) for _inode, name in calls)
    assert not list(debug_root.iterdir())
    assert not list(runtime_root.iterdir())


def test_pytest_temp_namespace_has_no_probe_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    debug_root = tmp_path / "debug-root"
    debug_root.mkdir()
    created: list[str] = []
    original_mkdir = run_pytest_lane.os.mkdir

    def recording_mkdir(name, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            created.append(name)
        return original_mkdir(name, mode, dir_fd=dir_fd)

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(debug_root))
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(run_pytest_lane.os, "mkdir", recording_mkdir)

    with run_pytest_lane.owned_pytest_temp_namespace() as namespace:
        assert created == [namespace.parent.name]
        assert namespace.name == run_pytest_lane.PYTEST_TEMP_BASETEMP_NAME

    assert not list(debug_root.iterdir())


def test_pytest_temp_namespace_falls_through_to_default_tempfile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    debug_root = tmp_path / "debug-root"
    runtime_root = tmp_path / "runtime-root"
    debug_root.mkdir()
    runtime_root.mkdir()
    default_root = tmp_path / "default-root"
    default_root.mkdir()
    identities = {
        root.stat().st_ino: root
        for root in (debug_root, runtime_root, default_root)
    }
    calls: list[Path] = []
    original_mkdir = run_pytest_lane.os.mkdir

    def fake_mkdir(name, mode=0o777, *, dir_fd=None):
        if dir_fd is not None:
            root = identities[os.fstat(dir_fd).st_ino]
            calls.append(root)
            if root in {debug_root, runtime_root}:
                raise PermissionError("simulated unusable candidate")
        return original_mkdir(name, mode, dir_fd=dir_fd)

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(debug_root))
    monkeypatch.setenv("TMPDIR", str(runtime_root))
    monkeypatch.setattr(run_pytest_lane.tempfile, "gettempdir", lambda: str(default_root))
    monkeypatch.setattr(run_pytest_lane.os, "mkdir", fake_mkdir)

    with run_pytest_lane.owned_pytest_temp_namespace() as namespace:
        assert calls == [debug_root, runtime_root, default_root]
        assert namespace.parent.parent == default_root

    assert not list(runtime_root.iterdir())


def test_pytest_temp_namespace_reports_bounded_candidate_exhaustion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    debug_root = tmp_path / "debug-root"
    runtime_root = tmp_path / "runtime-root"
    debug_root.mkdir()
    runtime_root.mkdir()
    default_root = tmp_path / "default-root"
    default_root.mkdir()
    identities = {
        root.stat().st_ino: root
        for root in (debug_root, runtime_root, default_root)
    }
    calls: list[Path] = []

    def fail_mkdir(name, mode=0o777, *, dir_fd=None):
        root = identities[os.fstat(dir_fd).st_ino]
        calls.append(root)
        raise PermissionError("simulated exhausted candidates")

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(debug_root))
    monkeypatch.setenv("TMPDIR", str(runtime_root))
    monkeypatch.setattr(run_pytest_lane.tempfile, "gettempdir", lambda: str(default_root))
    monkeypatch.setattr(run_pytest_lane.os, "mkdir", fail_mkdir)

    with pytest.raises(run_pytest_lane.PytestTempNamespaceCreationError, match="trying all candidates"):
        run_pytest_lane._pytest_temp_directory()

    assert calls == [debug_root, runtime_root, default_root]
    assert not list(debug_root.iterdir())
    assert not list(runtime_root.iterdir())


def test_pytest_temp_namespace_fails_closed_without_identity_handle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delattr(run_pytest_lane.os, "O_PATH", raising=False)

    with pytest.raises(
        run_pytest_lane.PytestTempNamespaceCreationError,
        match="O_PATH",
    ):
        run_pytest_lane._pytest_temp_directory(tmp_path)

    assert not list(tmp_path.iterdir())


def test_pytest_lane_normalizes_candidate_exhaustion_at_runner_boundary(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    debug_root = tmp_path / "debug-root"
    runtime_root = tmp_path / "runtime-root"
    default_root = tmp_path / "default-root"
    for root in (debug_root, runtime_root, default_root):
        root.mkdir()

    def fail_mkdir(name, mode=0o777, *, dir_fd=None):
        raise PermissionError("simulated exhausted candidates")

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(debug_root))
    monkeypatch.setenv("TMPDIR", str(runtime_root))
    monkeypatch.setattr(run_pytest_lane.tempfile, "gettempdir", lambda: str(default_root))
    monkeypatch.setattr(run_pytest_lane.os, "mkdir", fail_mkdir)

    assert (
        run_pytest_lane.main(["--scheduler", "serial"])
        == run_pytest_lane.PYTEST_TEMP_CREATION_FAILURE_EXIT_CODE
    )
    assert "[error] unable to create an owner-owned pytest temporary namespace" in capsys.readouterr().err


def test_pytest_invocation_namespaces_are_unique_and_cleaned(tmp_path: Path) -> None:
    with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as first:
        with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as second:
            assert first != second
            assert first.parent != second.parent
            assert first.parent.parent == second.parent.parent == tmp_path
            first_command = run_pytest_lane.build_pytest_command(
                extra_args=["tests/test_validation_command_authority.py"],
                basetemp=first,
            )
            second_command = run_pytest_lane.build_pytest_command(
                extra_args=["tests/test_validation_command_authority.py"],
                basetemp=second,
            )
            assert first_command[first_command.index("--basetemp") + 1] == str(first)
            assert second_command[second_command.index("--basetemp") + 1] == str(second)
    assert not first.exists()
    assert not second.exists()


def test_pytest_temp_cleanup_failure_leaves_owner_diagnostic(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_cleanup(_namespace: Path) -> None:
        raise OSError("simulated owner cleanup failure")

    monkeypatch.setattr(run_pytest_lane, "_remove_owned_namespace", fail_cleanup)
    monkeypatch.setattr(
        run_pytest_lane,
        "PYTEST_TEMP_CLEANUP_RETRY_DELAY_SECONDS",
        0,
    )

    with pytest.raises(run_pytest_lane.PytestTempCleanupError) as raised:
        with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as namespace:
            (namespace.parent / "owned-state").write_text("owned\n", encoding="utf-8")

    result = raised.value.result
    assert not result.ok
    assert result.attempts == run_pytest_lane.PYTEST_TEMP_CLEANUP_ATTEMPTS
    assert result.diagnostic == (
        tmp_path / f".{namespace.parent.name}.cleanup-failed.json"
    )
    payload = json.loads(result.diagnostic.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        run_pytest_lane.PYTEST_TEMP_CLEANUP_DIAGNOSTIC_SCHEMA
    )
    assert payload["status"] == "cleanup_failed"
    assert payload["namespace"] == str(namespace.parent)
    assert len(payload["failures"]) == run_pytest_lane.PYTEST_TEMP_CLEANUP_ATTEMPTS
    assert "[pytest-temp-cleanup-failed]" in capsys.readouterr().err


def test_pytest_temp_cleanup_diagnostic_is_private_and_closes_fd(
    monkeypatch,
    tmp_path: Path,
) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    try:
        opened: list[int] = []
        closed: list[int] = []
        observed_flags: list[int] = []
        observed_modes: list[int] = []
        original_open = run_pytest_lane.os.open
        original_write = run_pytest_lane.os.write
        original_close = run_pytest_lane.os.close

        def recording_open(path, flags, mode=0o777, **kwargs):
            descriptor = original_open(path, flags, mode, **kwargs)
            opened.append(descriptor)
            observed_flags.append(flags)
            observed_modes.append(mode)
            return descriptor

        def short_write(descriptor: int, content) -> int:
            return original_write(descriptor, content[:3])

        def recording_close(descriptor: int) -> None:
            closed.append(descriptor)
            original_close(descriptor)

        with monkeypatch.context() as patch:
            patch.setattr(run_pytest_lane.os, "open", recording_open)
            patch.setattr(run_pytest_lane.os, "write", short_write)
            patch.setattr(run_pytest_lane.os, "close", recording_close)

            diagnostic = run_pytest_lane._write_cleanup_diagnostic(
                handle,
                [{"attempt": "1", "error_type": "OSError", "error": "failure"}],
            )

        assert diagnostic == run_pytest_lane._cleanup_diagnostic_path(handle.path)
        assert len(opened) == 1
        assert closed == opened
        assert observed_modes == [0o600]
        flags = observed_flags[0]
        assert flags & run_pytest_lane.os.O_CREAT
        assert flags & run_pytest_lane.os.O_EXCL
        if hasattr(run_pytest_lane.os, "O_NOFOLLOW"):
            assert flags & run_pytest_lane.os.O_NOFOLLOW
        assert stat.S_IMODE(diagnostic.lstat().st_mode) == 0o600
        payload = json.loads(diagnostic.read_text(encoding="utf-8"))
        assert payload["status"] == "cleanup_failed"
        assert payload["failures"] == [
            {"attempt": "1", "error_type": "OSError", "error": "failure"}
        ]
    finally:
        assert run_pytest_lane.cleanup_pytest_temp_namespace(handle).ok


def test_pytest_temp_cleanup_diagnostic_rejects_symlink_collision_without_following(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "runner-writable-marker"
    marker.write_bytes(b"outside bytes must survive\n")
    marker.chmod(0o640)
    diagnostic = run_pytest_lane._cleanup_diagnostic_path(handle.path)
    diagnostic.symlink_to(marker)
    before_bytes = marker.read_bytes()
    before_mode = stat.S_IMODE(marker.stat().st_mode)

    result = run_pytest_lane._write_cleanup_diagnostic(
        handle,
        [{"attempt": "1", "error_type": "OSError", "error": "failure"}],
    )

    assert result is None
    assert diagnostic.is_symlink()
    assert diagnostic.readlink() == marker
    assert marker.read_bytes() == before_bytes
    assert stat.S_IMODE(marker.stat().st_mode) == before_mode
    assert "[pytest-temp-cleanup-diagnostic-failed]" in capsys.readouterr().err
    assert run_pytest_lane.cleanup_pytest_temp_namespace(handle).ok
    diagnostic.unlink()


def test_pytest_temp_cleanup_removes_partial_diagnostic_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    original_write = run_pytest_lane.os.write
    writes = 0

    def partial_write(descriptor: int, content) -> int:
        nonlocal writes
        writes += 1
        if writes == 1:
            return original_write(descriptor, content[:5])
        return 0

    diagnostic = run_pytest_lane._cleanup_diagnostic_path(handle.path)
    monkeypatch.setattr(run_pytest_lane.os, "write", partial_write)
    assert (
        run_pytest_lane._write_cleanup_diagnostic(
            handle,
            [{"attempt": "1", "error_type": "OSError", "error": "failure"}],
        )
        is None
    )
    assert not diagnostic.exists()
    assert run_pytest_lane.cleanup_pytest_temp_namespace(handle).ok


def test_pytest_temp_cleanup_removes_diagnostic_after_close_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    original_open = run_pytest_lane.os.open
    original_close = run_pytest_lane.os.close
    diagnostic = run_pytest_lane._cleanup_diagnostic_path(handle.path)
    diagnostic_fd: int | None = None

    def recording_open(path, flags, mode=0o777, **kwargs):
        nonlocal diagnostic_fd
        descriptor = original_open(path, flags, mode, **kwargs)
        if path == diagnostic.name and kwargs.get("dir_fd") == handle.parent_fd:
            diagnostic_fd = descriptor
        return descriptor

    def failing_close(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor == diagnostic_fd:
            raise OSError("simulated diagnostic close failure")

    monkeypatch.setattr(run_pytest_lane.os, "open", recording_open)
    monkeypatch.setattr(run_pytest_lane.os, "close", failing_close)
    assert (
        run_pytest_lane._write_cleanup_diagnostic(
            handle,
            [{"attempt": "1", "error_type": "OSError", "error": "failure"}],
        )
        is None
    )
    assert not diagnostic.exists()
    monkeypatch.undo()
    assert run_pytest_lane.cleanup_pytest_temp_namespace(handle).ok


def test_pytest_temp_namespace_fd_handles_are_independent_and_closed(
    tmp_path: Path,
) -> None:
    serial_handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    shard_handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    descriptors = {
        serial_handle.parent_fd,
        serial_handle.namespace_fd,
        shard_handle.parent_fd,
        shard_handle.namespace_fd,
    }
    assert len(descriptors) == 4
    assert run_pytest_lane.cleanup_pytest_temp_namespace(serial_handle).ok
    assert run_pytest_lane.cleanup_pytest_temp_namespace(shard_handle).ok
    for descriptor in descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_pytest_temp_cleanup_stays_with_original_parent_after_ancestor_swap(
    tmp_path: Path,
) -> None:
    base = tmp_path / "topology"
    parent = base / "parent"
    outside = base / "outside"
    base.mkdir()
    parent.mkdir()
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("outside\n", encoding="utf-8")
    handle = run_pytest_lane._pytest_temp_directory(parent)
    (handle.path / "owned").write_text("owned\n", encoding="utf-8")
    outside_namespace = outside / handle.name
    outside_namespace.mkdir()
    (outside_namespace / "outside-owned").write_text("preserve\n", encoding="utf-8")

    renamed_parent = base / "renamed-parent"
    parent.rename(renamed_parent)
    parent.symlink_to(outside, target_is_directory=True)

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)

    assert result.ok is True
    assert not (renamed_parent / handle.name).exists()
    assert marker.read_text(encoding="utf-8") == "outside\n"
    assert (outside_namespace / "outside-owned").read_text(encoding="utf-8") == "preserve\n"

    (outside_namespace / "outside-owned").unlink()
    outside_namespace.rmdir()
    marker.unlink()
    parent.unlink()
    renamed_parent.rmdir()
    outside.rmdir()
    base.rmdir()


def test_pytest_cleanup_diagnostic_is_published_under_original_parent_after_swap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    base = tmp_path / "diagnostic-topology"
    parent = base / "parent"
    outside = base / "outside"
    base.mkdir()
    parent.mkdir()
    outside.mkdir()
    marker = outside / "marker"
    marker.write_text("outside\n", encoding="utf-8")
    handle = run_pytest_lane._pytest_temp_directory(parent)
    (handle.path / "owned").write_text("owned\n", encoding="utf-8")
    outside_namespace = outside / handle.name
    outside_namespace.mkdir()

    renamed_parent = base / "renamed-parent"
    parent.rename(renamed_parent)
    parent.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        run_pytest_lane,
        "_remove_owned_namespace",
        lambda _handle: (_ for _ in ()).throw(OSError("forced cleanup failure")),
    )
    monkeypatch.setattr(run_pytest_lane, "PYTEST_TEMP_CLEANUP_RETRY_DELAY_SECONDS", 0)

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)
    diagnostic_name = f".{handle.name}.cleanup-failed.json"

    assert result.ok is False
    assert (renamed_parent / diagnostic_name).is_file()
    assert not (outside / diagnostic_name).exists()
    assert marker.read_text(encoding="utf-8") == "outside\n"
    assert outside_namespace.is_dir()
    assert (renamed_parent / handle.name).is_dir()

    (renamed_parent / diagnostic_name).unlink()
    (renamed_parent / handle.name / "owned").unlink()
    (renamed_parent / handle.name).rmdir()
    outside_namespace.rmdir()
    marker.unlink()
    parent.unlink()
    renamed_parent.rmdir()
    outside.rmdir()
    base.rmdir()


def test_pytest_temp_cleanup_handles_readonly_owned_paths(tmp_path: Path) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    readonly_directory = handle.path / "runtime" / "release"
    readonly_directory.mkdir(parents=True)
    (readonly_directory / "manifest.json").write_text("{}\n", encoding="utf-8")
    (readonly_directory / "manifest.json").chmod(0o400)
    readonly_directory.chmod(0o500)

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)

    assert result.ok is True
    assert not handle.path.exists()


def test_pytest_temp_cleanup_repairs_mode_zero_nested_directory_as_owner(
    tmp_path: Path,
) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    nested = handle.path / "mode-zero"
    nested.mkdir()
    payload = nested / "payload.txt"
    payload.write_text("owned\n", encoding="utf-8")
    payload.chmod(0o400)
    nested.chmod(0)

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)

    assert result.ok is True
    assert not handle.path.exists()


def test_pytest_temp_cleanup_fd_chmod_survives_symlink_swap(
    monkeypatch,
    tmp_path: Path,
) -> None:
    if not all(
        hasattr(run_pytest_lane.os, attribute)
        for attribute in ("O_NOFOLLOW", "O_DIRECTORY", "fchmod")
    ):
        pytest.skip("fd no-follow directory permission support is unavailable")

    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    candidate = handle.path / "readonly-directory"
    outside = tmp_path / "outside"
    marker = outside / "keep.txt"
    candidate.mkdir(parents=True)
    outside.mkdir()
    marker.write_text("no-loss\n", encoding="utf-8")
    candidate.chmod(0o500)
    outside.chmod(0o500)

    expected = run_pytest_lane._ObjectIdentity.from_stat(
        os.stat("readonly-directory", dir_fd=handle.namespace_fd, follow_symlinks=False)
    )
    original_fchmod = run_pytest_lane.os.fchmod
    swapped = False

    def swap_before_fchmod(fd: int, mode: int) -> None:
        nonlocal swapped
        candidate.rmdir()
        candidate.symlink_to(outside, target_is_directory=True)
        swapped = True
        original_fchmod(fd, mode)

    monkeypatch.setattr(run_pytest_lane.os, "fchmod", swap_before_fchmod)
    monkeypatch.setattr(
        run_pytest_lane.os,
        "chmod",
        lambda *_args, **_kwargs: pytest.fail("cleanup must not chmod by path"),
    )

    with pytest.raises(OSError, match="identity changed"):
        run_pytest_lane._make_owned_directory_writable(
            handle.namespace_fd,
            candidate.name,
            expected,
        )

    assert swapped is True
    assert stat.S_IMODE(outside.stat().st_mode) == 0o500
    assert marker.read_text(encoding="utf-8") == "no-loss\n"
    assert run_pytest_lane.cleanup_pytest_temp_namespace(handle).ok


def test_pytest_temp_cleanup_does_not_follow_owned_symlinks(tmp_path: Path) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("no-loss\n", encoding="utf-8")
    (handle.path / "external").symlink_to(outside, target_is_directory=True)

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)

    assert result.ok is True
    assert not handle.path.exists()
    assert marker.read_text(encoding="utf-8") == "no-loss\n"


def test_pytest_temp_cleanup_handles_deeply_nested_directories(tmp_path: Path) -> None:
    handle = run_pytest_lane._pytest_temp_directory(tmp_path)
    current = handle.path
    for _ in range(1100):
        current = current / "d"
        current.mkdir()

    result = run_pytest_lane.cleanup_pytest_temp_namespace(handle)

    assert result.ok is True
    assert not handle.path.exists()


def test_pytest_lane_returns_visible_failure_when_cleanup_is_unrecoverable(
    monkeypatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(run_pytest_lane.PYTEST_TEMP_ROOT_ENV, str(tmp_path))
    monkeypatch.delenv(run_pytest_lane.PYTEST_TEMP_PARENT_ENV, raising=False)
    monkeypatch.setattr(
        run_pytest_lane,
        "PYTEST_TEMP_CLEANUP_RETRY_DELAY_SECONDS",
        0,
    )

    def fail_lane_cleanup(_namespace: Path) -> None:
        raise OSError("simulated lane cleanup failure")

    monkeypatch.setattr(
        run_pytest_lane,
        "_remove_owned_namespace",
        fail_lane_cleanup,
    )
    monkeypatch.setattr(
        run_pytest_lane.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    assert (
        run_pytest_lane.main(["--scheduler", "serial"])
        == run_pytest_lane.PYTEST_TEMP_CLEANUP_FAILURE_EXIT_CODE
    )
    namespaces = list(tmp_path.glob(f"{run_pytest_lane.PYTEST_TEMP_PREFIX}*"))
    assert len(namespaces) == 1
    diagnostic = tmp_path / f".{namespaces[0].name}.cleanup-failed.json"
    assert diagnostic.is_file()
    assert "[error] pytest temporary namespace cleanup failed" in capsys.readouterr().err


def test_pytest_collect_and_parallel_shards_get_distinct_basetemps(tmp_path: Path) -> None:
    with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as collect:
        with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as shard_a:
            with run_pytest_lane.owned_pytest_temp_namespace(tmp_path) as shard_b:
                commands = [
                    run_pytest_lane._plugin_command(
                        selection_args=["tests/test_validation_command_authority.py"],
                        basetemp=collect,
                        collect_only=True,
                    ),
                    run_pytest_lane._plugin_command(
                        selection_args=[
                            "tests/test_validation_command_authority.py::"
                            "test_manifest_loads_and_names_expected_lanes"
                        ],
                        basetemp=shard_a,
                    ),
                    run_pytest_lane._plugin_command(
                        selection_args=[
                            "tests/test_validation_command_authority.py::"
                            "test_ci_gate_dispatches_manifest_lane"
                        ],
                        basetemp=shard_b,
                    ),
                ]

                basetemps = {
                    Path(command[command.index("--basetemp") + 1])
                    for command in commands
                }
                assert basetemps == {collect, shard_a, shard_b}
                assert all("-p" in command for command in commands)


def test_process_lane_allocates_and_cleans_collect_and_shard_basetemps(
    monkeypatch,
    tmp_path: Path,
) -> None:
    nodeids = [f"tests/test_lane.py::test_{index}" for index in range(4)]
    commands: list[list[str]] = []

    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(tmp_path))
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(run_pytest_lane, "PROCESS_SHARD_COUNT", 2)
    monkeypatch.setattr(run_pytest_lane, "PROCESS_WORKER_LIMIT", 2)

    def fake_run(command, *, env, **_kwargs):
        commands.append(list(command))
        run_pytest_lane.write_manifest(
            Path(env[run_pytest_lane.PARTITION_BASELINE_ENV]),
            nodeids,
        )
        return SimpleNamespace(returncode=0)

    class FakeProcess:
        def __init__(self, command, *, env, **_kwargs):
            commands.append(list(command))
            assignment = run_pytest_lane.read_manifest(
                Path(env[run_pytest_lane.PARTITION_ASSIGNMENT_ENV])
            )
            run_pytest_lane.write_manifest(
                Path(env[run_pytest_lane.PARTITION_OBSERVED_ENV]),
                assignment,
            )
            Path(env[run_pytest_lane.PARTITION_RESULT_ENV]).write_text(
                json.dumps(
                    {
                        "schema_version": run_pytest_lane.PARTITION_RESULT_SCHEMA,
                        "exitstatus": 0,
                        "stats": {"passed": len(assignment)},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

        def poll(self):
            return 0

        def terminate(self):
            raise AssertionError("the fake process should finish normally")

        def wait(self):
            return 0

    monkeypatch.setattr(run_pytest_lane.subprocess, "run", fake_run)
    monkeypatch.setattr(run_pytest_lane.subprocess, "Popen", FakeProcess)

    assert run_pytest_lane.run_process_worksteal(extra_args=[]) == 0

    basetemps = [
        Path(command[command.index("--basetemp") + 1])
        for command in commands
    ]
    assert len(basetemps) == 3
    assert len(set(basetemps)) == len(basetemps)
    assert all(path.parent.parent == tmp_path for path in basetemps)
    assert all(not path.exists() for path in basetemps)


def test_pytest_lane_rejects_reusable_user_basetemp() -> None:
    with pytest.raises(ValueError, match="fresh --basetemp"):
        run_pytest_lane.build_pytest_command(
            extra_args=["--basetemp", "reused"],
            basetemp=Path("owned"),
        )
    with pytest.raises(ValueError, match="fresh --basetemp"):
        run_pytest_lane._plugin_command(
            selection_args=["--basetemp=reused"],
            basetemp=Path("owned"),
        )


def test_pytest_lane_keeps_tombstone_semantics_upstream_and_paths_generic() -> None:
    source = (REPO_ROOT / "scripts" / "run_pytest_lane.py").read_text(encoding="utf-8")

    assert f"pytest-of-{getpass.getuser()}" not in source
    assert "pytest-of-" not in source
    assert "garbage-" not in source
    assert "/srv/" not in source
    assert "/home/" not in source
    assert "ignore_cleanup_errors" not in source
    assert re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        source,
        flags=re.IGNORECASE,
    ) is None
    assert "PYTEST_DEBUG_TEMPROOT" in source
    assert "cleanup_pytest_temp_namespace" in source


def test_pytest_scheduler_replays_failed_shard_log_at_closeout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_path = tmp_path / "shard-2.log"
    log_path.write_text("FAILED tests/test_example.py::test_failure\n", encoding="utf-8")
    records = {
        1: {
            "log": log_path,
            "selected": 7,
            "returncode": 1,
            "selection_proof": "exact",
        }
    }

    run_pytest_lane._replay_failed_shards(records, [1], shard_count=4)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[pytest-failed-shard 2/4]" in captured.err
    assert "FAILED tests/test_example.py::test_failure" in captured.err
    assert "selected=7 returncode=1 selection_proof=exact" in captured.err


def test_release_dependencies_do_not_add_a_threaded_pytest_scheduler() -> None:
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert not any(
        requirement.startswith("pytest-xdist")
        for requirement in requirements.splitlines()
    )


def test_decision_graph_lane_refreshes_ignored_cache_before_checking_it() -> None:
    steps = validation_lanes.command_sequence("decision_graph")
    command_tails = [step.command[1:] for step in steps]

    refresh = command_tails.index(
        (
            "scripts/build_workspace_decision_graph.py",
            "--write",
            "--json",
        )
    )
    check = command_tails.index(
        (
            "scripts/build_workspace_decision_graph.py",
            "--check",
            "--json",
        )
    )

    assert refresh < check


def test_source_and_generated_lanes_check_vendored_mcp_http_auth() -> None:
    expected = (
        "mcp/services/_shared/build_http_auth_vendors.py",
        "--check",
    )
    for sequence in ("source_fast", "generated", "release_check"):
        commands = [step.command[1:] for step in validation_lanes.command_sequence(sequence)]
        assert expected in commands


def test_manifest_is_stdlib_json_and_python_commands_normalize() -> None:
    steps = validation_lanes.command_sequence("source_fast")

    assert all(isinstance(step, validation_lanes.CommandStep) for step in steps)
    assert steps[0].command[0] != "python"


def test_no_validation_lane_commands_in_root_readme() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "python scripts/validate_stack.py" not in readme
    assert "python scripts/release_check.py" not in readme
