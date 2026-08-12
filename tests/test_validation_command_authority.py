from __future__ import annotations

import json
from pathlib import Path

from scripts import ci_gate, release_check, validation_lanes


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
    assert "https://github.com/8Dionysus/aoa-sdk" in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-sdk-source\" fetch --depth 1 origin "
        "d364da5c76cdd54e88f68c03ca49964fd3f86313"
    ) in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-agents-source\" fetch --depth 1 origin "
        "6eb9b27709fdab241423bf657dfe39fa85e4b159"
    ) in workflow
    assert (
        "git -C \"$RUNNER_TEMP/aoa-skills-source\" fetch --depth 1 origin "
        "d9949a4a4e525bceb04210fc4619d5cb57cf7cb7"
    ) in workflow
    assert 'python -m pip install "$RUNNER_TEMP/aoa-sdk-source"' in workflow
    assert "AOA_AGENTS_SOURCE_ROOT: ${{ runner.temp }}/aoa-agents-source" in workflow
    assert "AOA_SDK_SOURCE_ROOT: ${{ runner.temp }}/aoa-sdk-source" in workflow
    assert "AOA_SKILLS_SOURCE_ROOT: ${{ runner.temp }}/aoa-skills-source" in workflow
    assert "PYTHONPATH: ${{ runner.temp }}/aoa-sdk-source/src" in workflow
    assert "TMPDIR: ${{ runner.temp }}" in workflow
    assert ".deps/aoa-sdk" not in workflow
    assert shellcheck_commands[0]["command"][0] == "shellcheck"


def test_release_lane_runs_release_check_entrypoint_for_parity_stabilization() -> None:
    steps = validation_lanes.lane_command_sequence("release")

    assert len(steps) == 1
    assert steps[0].command[-1] == "scripts/release_check.py"


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
