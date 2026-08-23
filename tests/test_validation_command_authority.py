from __future__ import annotations

import json
from pathlib import Path

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
    assert "TMPDIR: ${{ runner.temp }}" not in workflow
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


def test_pytest_scheduler_keeps_an_exact_serial_rollback() -> None:
    rollback = run_pytest_lane.scheduler_plan("serial")
    command = run_pytest_lane.build_pytest_command(
        extra_args=["tests/test_validation_command_authority.py"],
    )

    assert rollback["reason"] == "explicit_serial_rollback"
    assert rollback["selection_changed"] is False
    assert command[1:] == [
        "-m",
        "pytest",
        "-q",
        "tests/test_validation_command_authority.py",
    ]


def test_canonical_pytest_modes_route_through_one_containment_instance(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        run_pytest_lane,
        "_run_in_containment",
        lambda *, mode, extra_args: calls.append((mode, extra_args)) or 0,
    )

    assert run_pytest_lane.main(["--scheduler", "serial", "tests/test_example.py"]) == 0
    assert run_pytest_lane.main(["--scheduler", "auto"]) == 0

    assert calls == [
        ("serial", ["tests/test_example.py"]),
        ("process-4x32-file-aware", []),
    ]


def test_mocked_admission_runs_serial_and_process_modes_in_containment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in run_pytest_lane.FORBIDDEN_EXTERNAL_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("PYTHONPATH", raising=False)

    api = run_pytest_lane._containment_api()
    launcher = api._launcher_module()
    monkeypatch.setattr(
        launcher,
        "_same_uid_admission_probe",
        lambda _pid: {"checks": {}, "supported": True, "violations": []},
    )
    selection = ["tests/test_test_topology.py"]

    serial_spec = run_pytest_lane._containment_spec(
        mode="serial",
        extra_args=selection,
    )
    try:
        launcher._validate_spec(serial_spec)
    except launcher.AdmissionError as exc:
        pytest.skip(
            f"containment backend unavailable for deterministic integration: {exc}"
        )
    serial = launcher.run_contained(serial_spec, result_factory=api.ContainmentResult)
    if serial.status == "containment_unsupported":
        pytest.skip("containment backend rejected deterministic integration")
    assert serial.status == "completed"
    assert serial.returncode == 0
    assert serial.receipt["receipt"]["drain_complete"] is True
    assert serial.receipt["receipt"]["live_descendants"] == []

    process_spec = run_pytest_lane._containment_spec(
        mode="process-4x32-file-aware",
        extra_args=selection,
    )
    process = launcher.run_contained(process_spec, result_factory=api.ContainmentResult)
    assert process.status == "completed"
    assert process.returncode == 0
    assert process.receipt["receipt"]["drain_complete"] is True
    assert process.receipt["receipt"]["live_descendants"] == []

    output = capsys.readouterr().out
    assert "[pytest-partition] collected=5" in output
    assert "exact_union=true overlap=false" in output
    assert "[pytest-aggregate] verdict=passed selected=5 shards=5" in output
    assert 'outcomes={"passed": 5}' in output


def test_pytest_adapter_rejects_host_temp_and_output_redirections(monkeypatch) -> None:
    for name in run_pytest_lane.FORBIDDEN_EXTERNAL_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TMPDIR", "/host/temp")
    with pytest.raises(run_pytest_lane.ContainmentAdapterError, match="external_redirection:TMPDIR"):
        run_pytest_lane._containment_spec(mode="serial", extra_args=[])

    monkeypatch.delenv("TMPDIR")
    with pytest.raises(run_pytest_lane.ContainmentAdapterError, match="external_pytest_redirection"):
        run_pytest_lane._containment_spec(mode="serial", extra_args=["--basetemp", "/host/temp"])


def test_pytest_adapter_source_has_no_legacy_process_or_path_authority() -> None:
    text = (REPO_ROOT / "scripts" / "run_pytest_lane.py").read_text(encoding="utf-8")

    assert "import pytest" not in text
    assert "TemporaryDirectory" in text  # worker-only private tmpfs manifests
    assert "killpg" not in text
    assert "setpgid" not in text
    assert "quarantine" not in text
    assert "os.unlink" not in text
    assert "os.rmdir" not in text


def test_process_worker_rejects_execution_outside_containment(monkeypatch, capsys) -> None:
    monkeypatch.delenv(run_pytest_lane.CONTAINMENT_ACTIVE_ENV, raising=False)
    assert run_pytest_lane.run_process_worksteal(extra_args=[]) == 125
    assert "only valid inside process containment" in capsys.readouterr().err


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
