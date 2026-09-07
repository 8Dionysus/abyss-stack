from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import (
    ci_gate,
    release_check,
    run_pytest_lane,
    validate_nested_agents,
    validation_lanes,
)


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


def test_agent_cards_route_exact_procedure_to_on_demand_validation() -> None:
    agent_paths = subprocess.check_output(
        ["git", "ls-files", "*AGENTS.md"], cwd=REPO_ROOT, text=True
    ).splitlines()
    for relative in agent_paths:
        card = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert not re.search(r"^```(?:bash|sh|shell|console)\s*$", card, re.MULTILINE)
    route = (REPO_ROOT / "VALIDATION.md").read_text(encoding="utf-8")
    assert "docs/validation/validation_lanes.json" in route
    assert "AGENTS.md" in route


def test_nested_agent_hygiene_rejects_extraction_residue_classes() -> None:
    orphan = "# AGENTS.md\n\n## Validation\nRun:\n\nUse the route.\n"
    empty = "# AGENTS.md\n\n## Smoke\n\n## Closeout\nDone.\n"
    dangling = "# AGENTS.md\n\nProcedure:\n\n## Closeout\nDone.\n"
    fenced_design = "# AGENTS.md\n\n```markdown\nProcedure:\n## Closeout\n```\n"
    inline = "# AGENTS.md\n\nUse python scripts/check.py --strict.\n"
    fenced = "# AGENTS.md\n\n```bash\npython scripts/check.py\n```\n"

    orphan_issues = validate_nested_agents._validate_card_hygiene("fixture", orphan)
    empty_issues = validate_nested_agents._validate_card_hygiene("fixture", empty)
    dangling_issues = validate_nested_agents._validate_card_hygiene("fixture", dangling)
    fenced_design_issues = validate_nested_agents._validate_card_hygiene("fixture", fenced_design)
    inline_issues = validate_nested_agents._validate_card_hygiene("fixture", inline)
    fenced_issues = validate_nested_agents._validate_card_hygiene("fixture", fenced)

    assert any("orphan procedural lead-in" in issue for issue in orphan_issues)
    assert any("empty procedural heading" in issue for issue in empty_issues)
    assert any("dangling colon lead-in" in issue for issue in dangling_issues)
    assert not any("dangling colon lead-in" in issue for issue in fenced_design_issues)
    assert any("imperative command sequence" in issue for issue in inline_issues)
    assert any("runnable command fence" in issue for issue in fenced_issues)


def test_root_validation_rejects_duplicate_source_route_headings() -> None:
    route = "## `pkg/AGENTS.md`\n\n### First\n\n## `pkg/AGENTS.md`\n"

    issues = validate_nested_agents._validate_root_validation_routes(route)

    assert issues == ["VALIDATION.md: duplicate source route heading 'pkg/AGENTS.md'"]


def test_card_validation_route_is_bounded_to_matching_root_section(tmp_path) -> None:
    card = tmp_path / "pkg" / "AGENTS.md"
    card.parent.mkdir()
    card.write_text("# AGENTS.md\n", encoding="utf-8")
    (tmp_path / "VALIDATION.md").write_text(
        "# Routes\n\n"
        "## `pkg/AGENTS.md`\n\n"
        "```bash\npython scripts/check_pkg.py\n```\n\n"
        "## `other/AGENTS.md`\n\n"
        "```bash\npython scripts/check_elsewhere.py\n```\n",
        encoding="utf-8",
    )

    route = validate_nested_agents._validation_route_text(card, tmp_path)

    assert "python scripts/check_pkg.py" in route
    assert "python scripts/check_elsewhere.py" not in route

    (tmp_path / "VALIDATION.md").write_text(
        "# Routes\n\n"
        "## `pkg/AGENTS.md`\n\nNo local command.\n\n"
        "## `other/AGENTS.md`\n\n"
        "```bash\npython scripts/check_pkg.py\n```\n",
        encoding="utf-8",
    )

    missing_local_route = validate_nested_agents._validation_route_text(card, tmp_path)

    assert "python scripts/check_pkg.py" not in missing_local_route


def test_current_nested_agent_hygiene_is_clean() -> None:
    result = validate_nested_agents.validate(REPO_ROOT)

    assert result.issues == ()


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
        "9540358c9443c2b7ef78dd9d1d8a0bc7b50ef240"
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
        "shard_count": 16,
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


def test_pytest_shard_count_scales_small_selections_and_keeps_full_default() -> None:
    assert run_pytest_lane.shard_count_for_selection(0) == 0
    assert run_pytest_lane.shard_count_for_selection(1) == 1
    assert run_pytest_lane.shard_count_for_selection(364) == 4
    assert run_pytest_lane.shard_count_for_selection(369) == 5
    assert run_pytest_lane.shard_count_for_selection(2853) == 16
    assert run_pytest_lane.shard_count_for_selection(2974) == 16


def test_pytest_full_default_partition_is_exactly_sixteen_shards() -> None:
    nodeids = [f"tests/test_example.py::test_{index}" for index in range(2974)]
    shard_count = run_pytest_lane.shard_count_for_selection(len(nodeids))
    partitions = run_pytest_lane.partition_nodeids(nodeids, shard_count=shard_count)
    flattened = [nodeid for partition in partitions for nodeid in partition]

    assert shard_count == len(partitions) == 16
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


def test_pytest_process_shards_use_durable_logs_without_pipe_eof(monkeypatch) -> None:
    nodeid = "tests/test_example.py::test_example"
    popen_stdout: list[object] = []

    def fake_collect(*_args, **kwargs):
        run_pytest_lane.write_manifest(
            Path(kwargs["env"][run_pytest_lane.PARTITION_BASELINE_ENV]),
            [nodeid],
        )
        return subprocess.CompletedProcess([], 0)

    class FakeProcess:
        def poll(self):
            return 0

    def fake_popen(_command, **kwargs):
        popen_stdout.append(kwargs["stdout"])
        kwargs["stdout"].write("fake shard output\n")
        kwargs["stdout"].flush()
        environment = kwargs["env"]
        run_pytest_lane.write_manifest(
            Path(environment[run_pytest_lane.PARTITION_OBSERVED_ENV]),
            [nodeid],
        )
        Path(environment[run_pytest_lane.PARTITION_RESULT_ENV]).write_text(
            json.dumps(
                {
                    "schema_version": run_pytest_lane.PARTITION_RESULT_SCHEMA,
                    "exitstatus": 0,
                    "stats": {"passed": 1},
                    "finished_nodeids": [nodeid],
                }
            ),
            encoding="utf-8",
        )
        return FakeProcess()

    monkeypatch.setattr(run_pytest_lane.subprocess, "run", fake_collect)
    monkeypatch.setattr(run_pytest_lane.subprocess, "Popen", fake_popen)

    assert run_pytest_lane.run_process_worksteal(extra_args=[nodeid]) == 0
    assert popen_stdout
    assert popen_stdout[0] is not subprocess.PIPE


def test_pytest_live_preview_tolerates_partial_utf8() -> None:
    assert run_pytest_lane._decode_live_output(b"prefix \xe2\x82") == "prefix \ufffd"


@pytest.mark.parametrize("cache_enabled", [True, False])
def test_process_retry_cache_preserves_failures_and_clears_fixed_selection(
    tmp_path: Path, monkeypatch, cache_enabled: bool,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "" if cache_enabled else "-p no:cacheprovider")
    (tmp_path / "pytest.ini").write_text("[pytest]\ncache_dir = retry cache\n", encoding="utf-8")
    cache_path = tmp_path / "retry cache/v/cache/lastfailed"
    unselected = {"unselected.py::test_old_failure": True}
    if cache_enabled:
        cache_path.parent.mkdir(parents=True)
        cache_path.write_text(json.dumps(unselected), encoding="utf-8")
    for name, peer in (("a", "b"), ("b", "a")):
        (tmp_path / f"test_{name}.py").write_text(
            "from pathlib import Path\nimport time\n"
            f"def test_{name}():\n"
            f"    Path('ready_{name}').touch()\n"
            "    deadline = time.monotonic() + 10\n"
            f"    while not Path('ready_{peer}').exists():\n"
            "        assert time.monotonic() < deadline, 'peer worker did not start'\n"
            "        time.sleep(0.01)\n"
            f"    assert Path('fixed_{name}').exists(), 'deliberate failure'\n",
            encoding="utf-8",
        )
    selection = ["test_a.py", "test_b.py"]
    assert run_pytest_lane.run_process_worksteal(extra_args=selection) == 1
    if cache_enabled:
        assert json.loads(cache_path.read_text()) == {
            **unselected, "test_a.py::test_a": True, "test_b.py::test_b": True,
        }
    else:
        assert not cache_path.exists()

    (tmp_path / "fixed_a").touch()
    assert run_pytest_lane.run_process_worksteal(extra_args=selection) == 1
    if cache_enabled:
        assert json.loads(cache_path.read_text()) == {**unselected, "test_b.py::test_b": True}

    (tmp_path / "fixed_b").touch()
    assert run_pytest_lane.run_process_worksteal(extra_args=selection) == 0
    if cache_enabled:
        assert json.loads(cache_path.read_text()) == unselected
    else:
        assert not cache_path.exists()


def test_process_retry_collection_baseline_follows_last_failed_filter(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--lf")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_selection.py").write_text(
        "from pathlib import Path\n"
        "def test_old(): Path('old-ran').touch()\n"
        "def test_new(): Path('new-ran').touch()\n",
        encoding="utf-8",
    )
    cache_path = tmp_path / ".pytest_cache/v/cache/lastfailed"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"test_selection.py::test_old": True}), encoding="utf-8")

    assert run_pytest_lane.run_process_worksteal(extra_args=["test_selection.py"]) == 0
    assert (tmp_path / "old-ran").exists()
    assert not (tmp_path / "new-ran").exists()
    assert json.loads(cache_path.read_text()) == {}


def test_process_retry_does_not_cache_passing_tests_on_session_policy_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(wrapper=True, trylast=True)\n"
        "def pytest_runtestloop(session):\n"
        "    result = yield\n"
        "    if not session.config.getoption('collectonly'):\n"
        "        session.testsfailed = 1\n"
        "    return result\n",
        encoding="utf-8",
    )
    (tmp_path / "test_policy.py").write_text("def test_passes(): pass\n", encoding="utf-8")
    cache_path = tmp_path / ".pytest_cache/v/cache/lastfailed"
    cache_path.parent.mkdir(parents=True)
    unselected = {"other.py::test_old": True}
    cache_path.write_text(json.dumps(unselected), encoding="utf-8")

    assert run_pytest_lane.run_process_worksteal(extra_args=["test_policy.py"]) == 1
    assert json.loads(cache_path.read_text()) == unselected


def test_process_retry_records_failures_without_terminal_reporter(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "conftest.py").write_text(
        "def pytest_sessionstart(session):\n"
        "    terminal = session.config.pluginmanager.getplugin('terminalreporter')\n"
        "    if terminal is not None:\n"
        "        session.config.pluginmanager.unregister(terminal)\n",
        encoding="utf-8",
    )
    (tmp_path / "test_no_terminal.py").write_text(
        "def test_failure():\n    assert False\n", encoding="utf-8",
    )

    assert run_pytest_lane.run_process_worksteal(extra_args=["test_no_terminal.py"]) == 1
    assert json.loads(
        (tmp_path / ".pytest_cache/v/cache/lastfailed").read_text()
    ) == {"test_no_terminal.py::test_failure": True}


@pytest.mark.parametrize(
    ("ini_addopts", "env_addopts", "extra_args"),
    [
        ("--sw", "", ["--sw"]),
        ("", "--sw", []),
    ],
)
def test_process_scheduler_preserves_stepwise_cursor_across_invocations(
    tmp_path: Path,
    monkeypatch,
    ini_addopts: str,
    env_addopts: str,
    extra_args: list[str],
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", env_addopts)
    (tmp_path / "pytest.ini").write_text(
        f"[pytest]\naddopts = {ini_addopts}\n", encoding="utf-8",
    )
    (tmp_path / "test_stepwise.py").write_text(
        "from pathlib import Path\n"
        "def test_first():\n"
        "    Path('first-ran').touch()\n"
        "    assert Path('fix').exists()\n"
        "def test_second():\n"
        "    Path('second-ran').touch()\n",
        encoding="utf-8",
    )

    selection = [*extra_args, "test_stepwise.py"]
    assert run_pytest_lane.run_process_worksteal(extra_args=selection) == 2
    assert (tmp_path / "first-ran").exists()
    assert not (tmp_path / "second-ran").exists()
    stepwise_path = tmp_path / ".pytest_cache/v/cache/stepwise"
    assert json.loads(stepwise_path.read_text())["last_failed"] == (
        "test_stepwise.py::test_first"
    )

    (tmp_path / "fix").touch()
    assert run_pytest_lane.run_process_worksteal(extra_args=selection) == 0
    assert (tmp_path / "second-ran").exists()
    assert json.loads(stepwise_path.read_text())["last_failed"] is None


def test_process_scheduler_uses_serial_when_effective_options_are_unresolved(
    monkeypatch,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "_effective_pytest_options", lambda _: None)
    calls: list[list[str]] = []

    monkeypatch.setattr(
        run_pytest_lane,
        "_run_serial",
        lambda args: calls.append(args) or 19,
    )

    assert run_pytest_lane.run_process_worksteal(extra_args=["test_example.py"]) == 19
    assert calls == [["test_example.py"]]


@pytest.mark.parametrize(
    ("mode", "ini_addopts", "env_addopts", "extra_args"),
    [
        ("collect-only", "--collect-only", "", []),
        ("setup-only", "", "--setup-only", []),
        ("setup-plan", "", "", ["--setup-plan"]),
        ("fixtures", "--fixtures", "", []),
        ("fixtures-per-test", "", "--fixtures-per-test", []),
        ("cache-show", "", "", ["--cache-show=cache/"]),
        ("markers", "", "", ["--markers"]),
        ("version", "", "", ["--version"]),
        ("help", "", "", ["--help"]),
    ],
)
def test_process_scheduler_delegates_non_executing_modes_to_native_serial(
    tmp_path: Path,
    monkeypatch,
    mode: str,
    ini_addopts: str,
    env_addopts: str,
    extra_args: list[str],
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", env_addopts)
    (tmp_path / "pytest.ini").write_text(
        f"[pytest]\naddopts = {ini_addopts}\n", encoding="utf-8",
    )
    (tmp_path / "test_non_executing.py").write_text(
        "from pathlib import Path\n"
        "def test_body_is_not_run(): Path('body-ran').touch()\n",
        encoding="utf-8",
    )
    assert run_pytest_lane.run_process_worksteal(
        extra_args=[*extra_args, "test_non_executing.py"]
    ) == 0
    assert not (tmp_path / "body-ran").exists()


@pytest.mark.parametrize("previous", ["not json", "[]", '{"old":true,"fixed":true}'])
def test_retry_hint_repairs_corruption_without_losing_unselected_failures(
    tmp_path: Path, previous: str,
) -> None:
    cache_path = tmp_path / "lastfailed"
    cache_path.write_text(previous, encoding="utf-8")
    run_pytest_lane._update_lastfailed(cache_path, ["fixed"], ["failed"])
    assert json.loads(cache_path.read_text()) == (
        {"old": True, "failed": True} if previous.startswith("{") else {"failed": True}
    )


@pytest.mark.parametrize("failure", ["setup", "teardown", "crash"])
def test_process_retry_retains_fixture_errors_and_worker_crashes(
    tmp_path: Path, monkeypatch, failure: str,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_error.py").write_text(
        "import os\nimport pytest\n"
        "@pytest.fixture\n"
        "def resource():\n"
        f"    assert {failure != 'setup'!r}, 'setup failed'\n"
        "    yield\n"
        f"    assert {failure != 'teardown'!r}, 'teardown failed'\n"
        "def test_error(resource):\n"
        f"    {'os._exit(9)' if failure == 'crash' else 'pass'}\n",
        encoding="utf-8",
    )
    assert run_pytest_lane.run_process_worksteal(extra_args=["test_error.py"]) == 1
    assert json.loads((tmp_path / ".pytest_cache/v/cache/lastfailed").read_text()) == {
        "test_error.py::test_error": True,
    }


def test_interrupted_scheduler_retains_unfinished_selection(tmp_path: Path, monkeypatch) -> None:
    nodeid = "tests/test_pending.py::test_pending"
    cache_path = tmp_path / "lastfailed"

    def collect(*_args, **kwargs):
        run_pytest_lane.write_manifest(
            Path(kwargs["env"][run_pytest_lane.PARTITION_BASELINE_ENV]),
            [nodeid], lastfailed_path=cache_path,
        )
        return subprocess.CompletedProcess([], 0)

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(run_pytest_lane.subprocess, "run", collect)
    monkeypatch.setattr(run_pytest_lane.subprocess, "Popen", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_pytest_lane.run_process_worksteal(extra_args=[])
    assert json.loads(cache_path.read_text()) == {nodeid: True}


def test_process_retry_keeps_unexecuted_tests_and_honors_inherited_lastfailed(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(run_pytest_lane, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_pytest_lane, "shard_count_for_selection", lambda _count: 1)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTEST_ADDOPTS", "")
    (tmp_path / "pytest.ini").write_text("[pytest]\naddopts = -x\n", encoding="utf-8")
    (tmp_path / "test_partial.py").write_text(
        "from pathlib import Path\n"
        "def test_passed():\n    pass\n"
        "def test_failed():\n    assert Path('fixed').exists()\n"
        "def test_pending():\n    Path('executed').touch()\n",
        encoding="utf-8",
    )
    assert run_pytest_lane.run_process_worksteal(extra_args=["test_partial.py"]) == 1
    cache_path = tmp_path / ".pytest_cache/v/cache/lastfailed"
    assert json.loads(cache_path.read_text()) == {
        "test_partial.py::test_failed": True,
        "test_partial.py::test_pending": True,
    }
    assert not (tmp_path / "executed").exists()
    (tmp_path / "fixed").touch()
    monkeypatch.setenv("PYTEST_ADDOPTS", "--lf --last-failed-no-failures=none")
    assert run_pytest_lane.run_process_worksteal(extra_args=["test_partial.py"]) == 0
    assert (tmp_path / "executed").exists()
    assert json.loads(cache_path.read_text()) == {}


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


def test_explicit_process_scheduler_accepts_targeted_selection(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(
        run_pytest_lane,
        "run_process_worksteal",
        lambda *, extra_args: calls.append(extra_args) or 7,
    )

    assert (
        run_pytest_lane.main(
            [
                "--scheduler",
                "process-4x32-file-aware",
                "--",
                "tests/test_example.py",
            ]
        )
        == 7
    )
    assert calls == [["tests/test_example.py"]]


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


def test_pytest_shard_emits_bounded_failure_excerpt_while_running(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(run_pytest_lane.PARTITION_MODE_ENV, "shard")
    run_pytest_lane._LIVE_FAILURES.clear()
    report = SimpleNamespace(
        nodeid="tests/test_example.py::test_failure",
        when="call",
        failed=True,
        longreprtext="traceback\n" + ("x" * (run_pytest_lane.LIVE_FAILURE_MAX_CHARS + 50)),
    )

    try:
        run_pytest_lane.pytest_runtest_logreport(report)
        run_pytest_lane.pytest_runtest_logreport(report)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.count("[pytest-live-failure]") == 1
        assert "nodeid=tests/test_example.py::test_failure phase=call" in captured.err
        assert "[pytest-live-failure-truncated]" in captured.err
        assert len(captured.err) < run_pytest_lane.LIVE_FAILURE_MAX_CHARS + 250
    finally:
        run_pytest_lane._LIVE_FAILURES.clear()


def test_pytest_child_command_is_unbuffered_for_live_diagnostics() -> None:
    command = run_pytest_lane._plugin_command(selection_args=[])

    assert command[1:4] == ["-u", "-m", "pytest"]
    plugin_index = command.index("-p")
    assert command[plugin_index : plugin_index + 2] == [
        "-p",
        "scripts.run_pytest_lane",
    ]


def test_explicit_pytest_plugins_are_carried_into_process_children() -> None:
    assert run_pytest_lane._explicit_plugin_args(
        ["tests", "-p", "custom_plugin", "-pno:cacheprovider", "--", "-p", "literal"]
    ) == ["-p", "custom_plugin", "-pno:cacheprovider"]
    assert run_pytest_lane._plugin_command(
        selection_args=["tests/test_example.py::test_example"],
        explicit_plugin_args=["-p", "custom_plugin"],
    )[-3:] == ["-p", "custom_plugin", "tests/test_example.py::test_example"]


def test_pytest_children_disable_plugin_autoload_by_default_and_preserve_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV, raising=False)
    assert run_pytest_lane._pytest_environment()[run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV] == "1"
    environment = run_pytest_lane._partition_environment(
        baseline_path=Path("/tmp/baseline.json"),
    )
    assert environment[run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV] == "1"

    monkeypatch.setenv(run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV, "")
    assert run_pytest_lane._pytest_environment()[run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV] == ""
    opted_out = run_pytest_lane._partition_environment(
        baseline_path=Path("/tmp/baseline.json"),
    )
    assert opted_out[run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV] == ""

    monkeypatch.setenv(run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV, "0")
    assert run_pytest_lane._pytest_environment()[run_pytest_lane.PYTEST_DISABLE_PLUGIN_AUTOLOAD_ENV] == "0"


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
