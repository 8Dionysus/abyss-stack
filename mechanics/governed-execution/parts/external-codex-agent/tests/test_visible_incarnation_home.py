from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest


PART = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "visible_incarnation_home", PART / "visible_incarnation_home.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _realization(path: Path) -> Path:
    configuration = {
        "runtime": {
            "product": "codex-cli",
            "version": "0.147.0",
            "model_slug": "gpt-5.6-luna",
        },
        "reasoning_effort": "max",
    }
    payload = {
        "schema_version": "aoa_model_realization_v1",
        "model_realization_id": "model-realization:test/luna/max",
        "configuration": configuration,
        "configuration_fingerprint": MODULE.sha256_bytes(
            MODULE.canonical_bytes(configuration)
        ),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_prepared_home_binds_nested_default_without_rehoming_parent(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text(
        'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\n',
        encoding="utf-8",
    )
    (ambient / "auth.json").write_text("{}", encoding="utf-8")
    (ambient / "sessions").mkdir()

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )

    actor_home = Path(manifest["codex_home"])
    actor_config = (actor_home / "config.toml").read_text(encoding="utf-8")
    assert 'model = "gpt-5.6-luna"' in actor_config
    assert 'model_reasoning_effort = "max"' in actor_config
    assert (actor_home / "auth.json").readlink() == ambient / "auth.json"
    assert (actor_home / "sessions").readlink() == ambient / "sessions"
    executable = tmp_path / "codex.js"
    executable.write_text("binary", encoding="utf-8")
    executable.chmod(0o700)
    executable_link = tmp_path / "codex"
    executable_link.symlink_to(executable)
    argv = MODULE.bound_codex_argv(
        codex_executable=executable_link,
        manifest=manifest,
        arguments=["resume", "thread-id"],
    )
    assert argv[:3] == [str(executable_link), "-m", "gpt-5.6-luna"]
    assert any(
        f'shell_environment_policy.set={{CODEX_HOME="{actor_home}", PATH=' in item
        for item in argv
    )
    assert any(
        f'PATH="{actor_home / MODULE.DESCENDANT_BIN_NAME}:/usr/local/bin:/usr/bin:/bin"'
        in item
        for item in argv
    )
    shim = actor_home / MODULE.DESCENDANT_BIN_NAME / "codex"
    assert shim.is_file()
    assert "Codex executable changed after admission" in shim.read_text()
    assert argv[argv.index("--disable") + 1] == "multi_agent"
    assert manifest["ambient_codex_home"] == str(ambient)
    assert manifest["runtime_root"] == str(runtime_root)


def test_preparation_rejects_realization_fingerprint_drift(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")
    payload = json.loads(realization.read_text(encoding="utf-8"))
    payload["configuration"]["reasoning_effort"] = "xhigh"
    realization.write_text(json.dumps(payload), encoding="utf-8")

    try:
        MODULE.prepare_home(
            ambient_home=ambient,
            realization_path=realization,
            runtime_root=runtime_root,
        )
    except MODULE.IncarnationHomeError as exc:
        assert "fingerprint mismatch" in str(exc)
    else:
        raise AssertionError("fingerprint drift was accepted")


def test_bound_config_updates_indented_root_keys_without_touching_tables() -> None:
    ambient_config = (
        '  model = "old-model"\n'
        '  model_reasoning_effort = "high"\n'
        "[features]\n"
        "multi_agent = true\n"
        "[history]\n"
        'model = "nested-model"\n'
    )

    bound = MODULE._bound_config(
        ambient_config.encode("utf-8"), "gpt-5.6-luna", "max"
    )
    parsed = tomllib.loads(bound.decode("utf-8"))

    assert parsed["model"] == "gpt-5.6-luna"
    assert parsed["model_reasoning_effort"] == "max"
    assert parsed["features"]["multi_agent"] is False
    assert parsed["history"]["model"] == "nested-model"


def test_bound_config_preserves_features_table_before_later_table() -> None:
    bound = MODULE._bound_config(
        b'[features]\nuse_legacy = true\n[mcp_servers.foo]\ncommand = "server"\n',
        "gpt-5.6-luna",
        "max",
    )
    parsed = tomllib.loads(bound.decode("utf-8"))

    assert parsed["features"]["multi_agent"] is False
    assert parsed["features"]["use_legacy"] is True
    assert parsed["mcp_servers"]["foo"]["command"] == "server"


@pytest.mark.parametrize(
    "ambient_config",
    [
        '["features"]\nuse_legacy = true\n',
        'features = { use_legacy = true }\n',
    ],
)
def test_bound_config_supports_quoted_and_inline_features_tables(
    ambient_config: str,
) -> None:
    bound = MODULE._bound_config(
        ambient_config.encode("utf-8"), "gpt-5.6-luna", "max"
    )
    parsed = tomllib.loads(bound.decode("utf-8"))

    assert parsed["features"]["multi_agent"] is False
    assert parsed["features"]["use_legacy"] is True


def test_descendant_shim_rejects_executable_drift(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    executable = tmp_path / "codex.js"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    command = tmp_path / "codex"
    command.symlink_to(executable)
    MODULE.bound_codex_argv(
        codex_executable=command,
        manifest=manifest,
        arguments=["exec", "--help"],
    )
    executable.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")

    shim = Path(manifest["codex_home"]) / MODULE.DESCENDANT_BIN_NAME / "codex"
    completed = subprocess.run([str(shim)], capture_output=True, text=True)

    assert completed.returncode == 125
    assert "changed after admission" in completed.stderr


def test_bound_config_rejects_unbound_model_provider() -> None:
    with pytest.raises(MODULE.IncarnationHomeError, match="model_provider"):
        MODULE._bound_config(
            b'model_provider = "custom-endpoint"\nmodel = "old"\n',
            "gpt-5.6-luna",
            "max",
        )


def test_realization_identity_separates_equal_configurations(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    first = _realization(tmp_path / "first.json")
    second_payload = json.loads(first.read_text(encoding="utf-8"))
    second_payload["model_realization_id"] = "model-realization:test/luna/other"
    second = tmp_path / "second.json"
    second.write_text(json.dumps(second_payload), encoding="utf-8")

    first_manifest = MODULE.prepare_home(
        ambient_home=ambient, realization_path=first, runtime_root=runtime_root
    )
    second_manifest = MODULE.prepare_home(
        ambient_home=ambient, realization_path=second, runtime_root=runtime_root
    )

    assert first_manifest["codex_home"] != second_manifest["codex_home"]


def test_preparation_removes_obsolete_managed_shared_link(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    auth = ambient / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
    )
    actor_home = Path(manifest["codex_home"])
    assert (actor_home / "auth.json").is_symlink()

    auth.unlink()
    refreshed = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
    )

    assert "auth.json" not in refreshed["shared_state_names"]
    assert not (actor_home / "auth.json").exists()
    assert not (actor_home / "auth.json").is_symlink()


def test_preparation_rejects_symlinked_shared_state_entry(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    shared_target = tmp_path / "shared-target"
    shared_target.write_text("{}", encoding="utf-8")
    (ambient / "skills").symlink_to(shared_target)

    with pytest.raises(MODULE.IncarnationHomeError, match="may not be a symlink"):
        MODULE.prepare_home(
            ambient_home=ambient,
            realization_path=_realization(tmp_path / "realization.json"),
            runtime_root=runtime_root,
        )

    (ambient / "skills").unlink()
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    assert Path(manifest["codex_home"]).is_dir()


def test_preparation_rejects_runtime_root_nested_under_ambient_home(
    tmp_path: Path,
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = ambient / "incarnations"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")

    with pytest.raises(MODULE.IncarnationHomeError, match="nested"):
        MODULE.prepare_home(
            ambient_home=ambient,
            realization_path=_realization(tmp_path / "realization.json"),
            runtime_root=runtime_root,
        )


def test_preparation_rejects_a_different_ambient_owner(tmp_path: Path) -> None:
    ambient_a = tmp_path / "ambient-a"
    ambient_b = tmp_path / "ambient-b"
    runtime_root = tmp_path / "runtime"
    ambient_a.mkdir()
    ambient_b.mkdir()
    runtime_root.mkdir()
    for ambient in (ambient_a, ambient_b):
        (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")

    MODULE.prepare_home(
        ambient_home=ambient_a,
        realization_path=realization,
        runtime_root=runtime_root,
    )
    with pytest.raises(MODULE.IncarnationHomeError, match="another ambient"):
        MODULE.prepare_home(
            ambient_home=ambient_b,
            realization_path=realization,
            runtime_root=runtime_root,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ["exec", "-m", "other-model"],
        ["exec", "--model=other-model"],
        ["exec", "-c", "model=other-model"],
        ["exec", "--config=shell_environment_policy.set={CODEX_HOME=other}"],
        ["exec", "-p", "other-profile"],
        ["exec", "--enable", "multi_agent"],
        ["exec", "--enable=multi_agent"],
        ["exec", "--oss"],
        ["exec", "--local-provider", "ollama"],
        ["exec", "--local-provider=ollama"],
    ],
)
def test_bound_argv_rejects_incarnation_binding_overrides(
    tmp_path: Path, arguments: list[str]
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    executable = tmp_path / "codex"
    executable.write_text("binary", encoding="utf-8")
    executable.chmod(0o700)

    with pytest.raises(MODULE.IncarnationHomeError, match="binding"):
        MODULE.bound_codex_argv(
            codex_executable=executable,
            manifest=manifest,
            arguments=arguments,
        )


def test_load_manifest_revalidates_realization_and_derived_home(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"

    payload = json.loads(realization.read_text(encoding="utf-8"))
    payload["configuration"]["runtime"]["model_slug"] = "gpt-5.6-other"
    payload["configuration_fingerprint"] = MODULE.sha256_bytes(
        MODULE.canonical_bytes(payload["configuration"])
    )
    realization.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MODULE.IncarnationHomeError, match="binding drift"):
        MODULE._load_manifest(manifest_path)


def test_load_manifest_revalidates_realization_identifier(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"

    payload = json.loads(realization.read_text(encoding="utf-8"))
    payload["model_realization_id"] = "model-realization:test/other"
    realization.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MODULE.IncarnationHomeError, match="binding drift"):
        MODULE._load_manifest(manifest_path)


def test_load_manifest_rejects_scoped_config_binding_drift(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    actor_home = Path(manifest["codex_home"])
    manifest_path = actor_home.parent / "incarnation-home.json"
    (actor_home / "config.toml").write_text(
        'model = "gpt-5.6-other"\nmodel_reasoning_effort = "max"\n',
        encoding="utf-8",
    )
    manifest["config_digest"] = MODULE.sha256_bytes(
        (actor_home / "config.toml").read_bytes()
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(MODULE.IncarnationHomeError, match="scoped Codex config"):
        MODULE._load_manifest(manifest_path)


def test_load_manifest_rejects_ambient_provider_drift(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    ambient_config = ambient / "config.toml"
    ambient_config.write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    ambient_config.write_text(
        'model = "sol"\nmodel_provider = "custom-endpoint"\n',
        encoding="utf-8",
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="model_provider"):
        MODULE._load_manifest(manifest_path)


def test_load_manifest_rejects_shared_state_link_drift(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "auth.json").write_text("{}", encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
    )
    actor_home = Path(manifest["codex_home"])
    manifest_path = actor_home.parent / "incarnation-home.json"
    (actor_home / "auth.json").unlink()
    (actor_home / "auth.json").symlink_to(tmp_path / "replacement.json")
    (tmp_path / "replacement.json").write_text("{}", encoding="utf-8")

    with pytest.raises(MODULE.IncarnationHomeError, match="shared-state link drift"):
        MODULE._load_manifest(manifest_path)


def test_load_manifest_rejects_unexpected_shared_state_entry(tmp_path: Path) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    actor_home = Path(manifest["codex_home"])
    manifest_path = actor_home.parent / "incarnation-home.json"
    (actor_home / "unexpected.json").write_text("{}", encoding="utf-8")

    with pytest.raises(
        MODULE.IncarnationHomeError, match="unexpected incarnation-home entry"
    ):
        MODULE._load_manifest(manifest_path)


def test_executable_version_must_match_realization_runtime(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'codex-cli 0.147.0'\n", encoding="utf-8"
    )
    executable.chmod(0o700)

    MODULE._verify_executable_version(executable, "0.147.0")
    with pytest.raises(MODULE.IncarnationHomeError, match="version mismatch"):
        MODULE._verify_executable_version(executable, "0.146.0")


def test_direct_launch_records_the_actual_responsibility_holder_before_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    executable = tmp_path / "codex"
    executable.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        "  printf '%s\\n' 'codex-cli 0.147.0'\n"
        "fi\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    receipt_path = tmp_path / "holder.json"
    captured: dict[str, object] = {}

    original_content = executable.read_bytes()
    original_executable = tmp_path / "original-codex"
    original_executable.write_bytes(original_content)
    original_executable.chmod(0o700)

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        captured.update(
            path=path,
            argv=argv,
            environment=environment,
            inode_content=Path(path).read_bytes(),
        )

    original_holder_receipt = MODULE._holder_receipt

    def replace_command_path_after_receipt(**kwargs: object) -> dict[str, object]:
        receipt = original_holder_receipt(**kwargs)
        replacement = tmp_path / "replacement-codex"
        replacement.write_text("replacement", encoding="utf-8")
        replacement.chmod(0o700)
        os.replace(replacement, executable)
        return receipt

    monkeypatch.setattr(
        MODULE, "_holder_receipt", replace_command_path_after_receipt
    )

    terminal_pid = os.getppid()
    terminal_argv = ["/usr/bin/kitty", "--detach", "--title", "test-holder"]
    monkeypatch.setattr(
        MODULE,
        "_kitty_ancestor",
        lambda _pid: (terminal_pid, MODULE._proc_start_ticks(terminal_pid), terminal_argv),
    )
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(
        MODULE,
        "_proc_environ",
        lambda _pid: {"KITTY_PID": str(terminal_pid), "KITTY_WINDOW_ID": "1"},
    )
    monkeypatch.setattr(MODULE, "_proc_children", lambda _pid: [os.getpid()])
    monkeypatch.setattr(MODULE.os, "execve", fake_exec)
    args = MODULE.argparse.Namespace(
        holder_receipt=str(receipt_path),
        terminal_title=None,
        kitty_executable="/usr/bin/kitty",
        manifest=str(manifest_path),
        codex_executable=str(executable),
        codex_arguments=["exec", "--help"],
    )

    assert MODULE.command_launch(args) == 127
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == MODULE.HOLDER_RECEIPT_SCHEMA_VERSION
    assert receipt["lifecycle_role"] == "responsibility_holder"
    assert receipt["boot_id"] == MODULE._proc_boot_id()
    assert receipt["receipt_ref"] == str(receipt_path)
    assert receipt["holder"]["pid"] == os.getpid()
    assert receipt["holder"]["start_ticks"] == MODULE._proc_start_ticks(os.getpid())
    assert receipt["holder"]["parent_pid"] == os.getppid()
    assert receipt["holder"]["argv"] == MODULE._post_exec_argv(
        original_executable, captured["argv"]
    )
    assert receipt["terminal"]["binding"] == "kitty_ancestor_at_exec"
    assert receipt["terminal"]["pid"] == terminal_pid
    assert receipt["terminal"]["argv"] == terminal_argv
    assert receipt["terminal"]["window_id"] == "1"
    assert receipt["terminal"]["dedicated"] is True
    assert receipt["runtime"]["incarnation_manifest"] == str(manifest_path)
    assert receipt["runtime"]["model"] == "gpt-5.6-luna"
    assert receipt["runtime"]["reasoning_effort"] == "max"
    assert captured["environment"]["CODEX_HOME"] == str(ambient)
    assert str(captured["path"]).startswith("/proc/self/fd/")
    assert captured["inode_content"] == original_content
    assert executable.read_text(encoding="utf-8") == "replacement"

    executable.write_bytes(original_content)
    executable.chmod(0o700)
    with pytest.raises(MODULE.IncarnationHomeError, match="already exists"):
        MODULE.command_launch(args)


def test_holder_terminal_binds_first_kitty_ancestor_through_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder_pid = 7001
    wrapper_pid = 7002
    kitty_pid = 7003
    parents = {holder_pid: wrapper_pid, wrapper_pid: kitty_pid, kitty_pid: 1}
    commands = {wrapper_pid: "bwrap", kitty_pid: "kitty"}

    monkeypatch.setattr(MODULE, "_proc_parent_pid", parents.__getitem__)
    monkeypatch.setattr(MODULE, "_proc_comm", commands.__getitem__)
    monkeypatch.setattr(MODULE, "_proc_start_ticks", lambda pid: pid + 100)
    monkeypatch.setattr(MODULE, "_proc_argv", lambda pid: [f"process-{pid}"])

    assert MODULE._kitty_ancestor(holder_pid) == (
        kitty_pid,
        kitty_pid + 100,
        [f"process-{kitty_pid}"],
    )


def test_holder_receipt_rejects_detached_kitty_route(tmp_path: Path) -> None:
    args = MODULE.argparse.Namespace(
        holder_receipt=str(tmp_path / "holder.json"),
        terminal_title="visible-holder",
        kitty_executable="/usr/bin/kitty",
        manifest=str(tmp_path / "missing-manifest.json"),
        codex_executable=str(tmp_path / "codex"),
        codex_arguments=["exec", "--help"],
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="detached Kitty"):
        MODULE.command_launch(args)


def test_close_requires_confirmed_handoff_delivery(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff.json"
    handoff.write_text("{}\n", encoding="utf-8")
    wake = tmp_path / "wake.json"
    wake.write_text(
        json.dumps(
            {
                "schema_version": "task_local_actor_wake_receipt_v1",
                "handoff_ref": str(handoff),
                "handoff_sha256": MODULE.sha256_bytes(handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": False},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="does not prove handoff"):
        MODULE._validate_wake_delivery(
            wake_receipt_path=wake,
            handoff_path=handoff,
            holder_receipt_path=tmp_path / "holder.json",
            closure_receipt_path=tmp_path / "closure.json",
            holder_receipt={"holder": {}, "terminal": {}},
        )


def test_post_exec_argv_expands_shebang_interpreter(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env python3 -u\n", encoding="utf-8")
    executable.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable, [str(executable), "exec", "--help"]
    ) == ["/usr/bin/env", "python3 -u", str(executable), "exec", "--help"]


def test_post_exec_argv_resolves_env_interpreter_reexec(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    executable.chmod(0o700)
    node = tmp_path / "bin" / "node"
    node.parent.mkdir()
    node.write_text("", encoding="utf-8")
    node.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable,
        [str(executable), "exec", "--help"],
        path=str(node.parent),
    ) == [str(node), str(executable), "exec", "--help"]


def test_kitty_dedication_rejects_sibling_terminal_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder_pid = 7001
    kitty_pid = 7003
    sibling_pid = 7004
    parents = {holder_pid: kitty_pid, kitty_pid: 1}
    commands = {kitty_pid: "kitty", sibling_pid: "zsh"}

    monkeypatch.setattr(MODULE, "_proc_parent_pid", parents.__getitem__)
    monkeypatch.setattr(MODULE, "_proc_environ", lambda _pid: {
        "KITTY_PID": str(kitty_pid),
        "KITTY_WINDOW_ID": "7",
    })
    monkeypatch.setattr(MODULE, "_proc_children", lambda _pid: [holder_pid, sibling_pid])
    monkeypatch.setattr(MODULE, "_proc_comm", commands.__getitem__)

    with pytest.raises(MODULE.IncarnationHomeError, match="not dedicated"):
        MODULE._kitty_dedication(
            holder_pid=holder_pid,
            kitty_pid=kitty_pid,
            terminal_argv=["/usr/bin/kitty", "--detach", "--title", "holder"],
        )


def test_verified_term_uses_pidfd_after_identity_recheck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(MODULE.os, "pidfd_open", lambda pid, flags: (calls.append(("open", pid, flags)) or 42))
    monkeypatch.setattr(MODULE.signal, "pidfd_send_signal", lambda fd, sig: calls.append(("signal", fd, sig)))
    monkeypatch.setattr(MODULE, "_proc_start_ticks", lambda _pid: 99)
    monkeypatch.setattr(MODULE.os, "close", lambda fd: calls.append(("close", fd)))

    assert MODULE._send_verified_term(7003, 99) is True
    assert calls[0] == ("open", 7003, 0)
    assert calls[1] == ("signal", 42, MODULE.signal.SIGTERM)
    assert calls[2] == ("close", 42)


def test_identity_bound_close_records_already_gone_without_reopening_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    holder_payload = {
        "schema_version": MODULE.HOLDER_RECEIPT_SCHEMA_VERSION,
        "receipt_ref": str(holder),
        "created_at": "2026-08-15T00:00:00Z",
        "lifecycle_role": "responsibility_holder",
        "boot_id": MODULE._proc_boot_id(),
        "holder": {
            "pid": 987654321,
            "start_ticks": 11,
            "parent_pid": 987654322,
            "parent_start_ticks": 12,
            "parent_comm": "kitty",
            "argv": ["/usr/bin/codex", "exec"],
            "argv_digest": MODULE.sha256_bytes(
                MODULE.canonical_bytes(["/usr/bin/codex", "exec"])
            ),
        },
        "runtime": {
            "codex_executable": str(tmp_path / "missing-codex"),
            "codex_executable_digest": "sha256:" + "0" * 64,
            "incarnation_manifest": str(tmp_path / "missing-manifest"),
            "incarnation_manifest_digest": "sha256:" + "1" * 64,
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path),
            "incarnation_codex_home": str(tmp_path),
        },
        "terminal": {
            "binding": "kitty_ancestor_at_exec",
            "required_comm": "kitty",
            "pid": 987654323,
            "start_ticks": 13,
            "argv": ["/usr/bin/kitty", "--detach", "--title", "holder"],
            "window_id": "7",
            "dedicated": True,
        },
    }
    holder.write_text(json.dumps(holder_payload), encoding="utf-8")
    handoff.write_text(
        json.dumps(
            {
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder),
                        "terminal_receipt_sha256": MODULE.sha256_bytes(
                            holder.read_bytes()
                        ),
                        "closure_receipt": str(closure),
                        "holder_pid": holder_payload["holder"]["pid"],
                        "terminal_pid": holder_payload["terminal"]["pid"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    wake.write_text(
        json.dumps(
            {
                "schema_version": "task_local_actor_wake_receipt_v1",
                "handoff_ref": str(handoff),
                "handoff_sha256": MODULE.sha256_bytes(handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _start: "gone")

    assert MODULE.command_close(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            wake_receipt=str(wake),
            closure_receipt=str(closure),
        )
    ) == 0
    recorded = json.loads(closure.read_text(encoding="utf-8"))
    assert recorded["closed"] is True
    assert recorded["outcome"] == "already_gone"
    assert recorded["identity_state"] == "already_gone"
    assert recorded["terminal"]["signal_sent"] is False
    assert recorded["reservation_ref"] == str(
        MODULE._closure_reservation_path(closure).resolve()
    )
    assert MODULE._closure_reservation_path(closure).is_file()


def test_holder_boot_identity_is_bound_to_current_kernel() -> None:
    receipt = {
        "boot_id": "00000000-0000-0000-0000-000000000000",
        "holder": {
            "pid": 101,
            "start_ticks": 11,
            "parent_pid": 102,
            "parent_start_ticks": 12,
            "argv": ["/usr/bin/codex"],
            "argv_digest": MODULE.sha256_bytes(
                MODULE.canonical_bytes(["/usr/bin/codex"])
            ),
        },
        "terminal": {"pid": 103, "start_ticks": 13},
    }
    with pytest.raises(MODULE.IncarnationHomeError, match="boot identity"):
        MODULE._holder_receipt_process_ids(receipt)


def test_closure_reservation_reopens_after_interrupted_attempt(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")

    reservation_fd, reservation_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
    os.close(reservation_fd)
    assert not closure.exists()
    assert reservation_path.is_file()
    reservation = json.loads(reservation_path.read_text(encoding="utf-8"))
    assert reservation["holder_pid"] == 101
    assert reservation["terminal_pid"] == 202
    assert MODULE._closure_reservation_lock_path(closure).is_file()

    retry_fd, retry_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    MODULE.fcntl.flock(retry_fd, MODULE.fcntl.LOCK_UN)
    os.close(retry_fd)
    assert retry_path == reservation_path

    with pytest.raises(MODULE.IncarnationHomeError, match="identity mismatch"):
        MODULE._reserve_closure_receipt(
            closure_receipt_path=closure,
            handoff_path=handoff,
            holder_receipt_path=holder,
            wake_receipt_path=wake,
            holder_pid=303,
            terminal_pid=202,
        )


def test_closure_reservation_rechecks_completed_receipt_after_lock(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")

    reservation_fd, reservation_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
    os.close(reservation_fd)
    closure.write_text(
        json.dumps(
            {
                "reservation_ref": str(reservation_path.resolve()),
                "holder": {"pid": 101},
                "terminal": {"pid": 202},
                "closed": True,
            }
        ),
        encoding="utf-8",
    )

    retry_fd, retry_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=101,
        terminal_pid=202,
    )
    try:
        assert retry_path == reservation_path
        assert completed is not None
        assert completed["closed"] is True
    finally:
        MODULE.fcntl.flock(retry_fd, MODULE.fcntl.LOCK_UN)
        os.close(retry_fd)


def test_completed_unclosed_receipt_preserves_failure_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")

    reservation_fd, reservation_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
    os.close(reservation_fd)
    closure.write_text(
        json.dumps(
            {
                "reservation_ref": str(reservation_path.resolve()),
                "holder": {"pid": 101},
                "terminal": {"pid": 202},
                "closed": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt",
        lambda _path: {
            "holder": {"pid": 101},
            "terminal": {
                "pid": 202,
                "argv": ["/usr/bin/kitty"],
                "required_comm": "kitty",
            },
        },
    )
    monkeypatch.setattr(MODULE, "_validate_wake_delivery", lambda **_kwargs: {})
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="unclosed"):
        MODULE.command_close(
            MODULE.argparse.Namespace(
                handoff=str(handoff),
                holder_receipt=str(holder),
                wake_receipt=str(wake),
                closure_receipt=str(closure),
            )
        )


def test_interrupted_signal_attempt_is_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    holder_payload = {
        "schema_version": MODULE.HOLDER_RECEIPT_SCHEMA_VERSION,
        "receipt_ref": str(holder),
        "created_at": "2026-08-15T00:00:00Z",
        "lifecycle_role": "responsibility_holder",
        "boot_id": MODULE._proc_boot_id(),
        "holder": {
            "pid": 987654321,
            "start_ticks": 11,
            "parent_pid": 987654322,
            "parent_start_ticks": 12,
            "parent_comm": "kitty",
            "argv": ["/usr/bin/codex", "exec"],
            "argv_digest": MODULE.sha256_bytes(
                MODULE.canonical_bytes(["/usr/bin/codex", "exec"])
            ),
        },
        "runtime": {
            "codex_executable": str(tmp_path / "missing-codex"),
            "codex_executable_digest": "sha256:" + "0" * 64,
            "incarnation_manifest": str(tmp_path / "missing-manifest"),
            "incarnation_manifest_digest": "sha256:" + "1" * 64,
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path),
            "incarnation_codex_home": str(tmp_path),
        },
        "terminal": {
            "binding": "kitty_ancestor_at_exec",
            "required_comm": "kitty",
            "pid": 987654323,
            "start_ticks": 13,
            "argv": ["/usr/bin/kitty", "--detach", "--title", "holder"],
            "window_id": "7",
            "dedicated": True,
        },
    }
    holder.write_text(json.dumps(holder_payload), encoding="utf-8")
    handoff.write_text(
        json.dumps(
            {
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder),
                        "terminal_receipt_sha256": MODULE.sha256_bytes(
                            holder.read_bytes()
                        ),
                        "closure_receipt": str(closure),
                        "holder_pid": holder_payload["holder"]["pid"],
                        "terminal_pid": holder_payload["terminal"]["pid"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    wake.write_text(
        json.dumps(
            {
                "schema_version": "task_local_actor_wake_receipt_v1",
                "handoff_ref": str(handoff),
                "handoff_sha256": MODULE.sha256_bytes(handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": True},
            }
        ),
        encoding="utf-8",
    )
    reservation_fd, reservation_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        holder_pid=holder_payload["holder"]["pid"],
        terminal_pid=holder_payload["terminal"]["pid"],
    )
    assert completed is None
    reservation = MODULE._load_json(
        reservation_path, "terminal closure reservation"
    )
    reservation.update(
        {
            "signal": "TERM",
            "signal_target": "holder_process",
            "signal_attempted": True,
            "signal_attempted_at": "2026-08-15T00:00:01Z",
            "signal_delivery": "unknown",
            "signal_sent": False,
        }
    )
    MODULE._write_reservation_json(
        reservation_path, reservation, "terminal closure reservation"
    )
    MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
    os.close(reservation_fd)

    states = iter(["live", "live", "gone", "gone"])
    monkeypatch.setattr(
        MODULE, "_proc_identity_state", lambda _pid, _start: next(states, "gone")
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_terminal_identity",
        lambda _receipt: (987654321, 987654323, "kitty", "7", True),
    )
    monkeypatch.setattr(
        MODULE,
        "_send_verified_term",
        lambda *_args: pytest.fail("interrupted TERM attempt was retried"),
    )

    assert MODULE.command_close(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            wake_receipt=str(wake),
            closure_receipt=str(closure),
        )
    ) == 0
    recorded = json.loads(closure.read_text(encoding="utf-8"))
    assert recorded["closed"] is True
    assert recorded["terminal"]["signal_attempted"] is True
    assert recorded["terminal"]["signal_delivery"] == "unknown"
    assert recorded["terminal"]["signal_sent"] is False
    assert recorded["reservation_ref"] == str(reservation_path.resolve())


def test_wake_delivery_requires_exact_holder_and_closure_binding(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    closure = tmp_path / "closure.json"
    wake = tmp_path / "wake.json"
    holder_payload = {
        "holder": {"pid": 101},
        "terminal": {"pid": 202},
    }
    holder.write_text(json.dumps(holder_payload), encoding="utf-8")
    handoff.write_text(
        json.dumps(
            {
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder),
                        "terminal_receipt_sha256": MODULE.sha256_bytes(holder.read_bytes()),
                        "closure_receipt": str(closure),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    wake.write_text(
        json.dumps(
            {
                "schema_version": "task_local_actor_wake_receipt_v1",
                "handoff_ref": str(handoff),
                "handoff_sha256": MODULE.sha256_bytes(handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": True},
            }
        ),
        encoding="utf-8",
    )

    MODULE._validate_wake_delivery(
        wake_receipt_path=wake,
        handoff_path=handoff,
        holder_receipt_path=holder,
        closure_receipt_path=closure,
        holder_receipt=holder_payload,
    )
    original_handoff = handoff.read_text(encoding="utf-8")
    handoff.write_text(
        original_handoff.replace(str(closure), str(tmp_path / "other.json")),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.IncarnationHomeError, match="handoff digest"):
        MODULE._validate_wake_delivery(
            wake_receipt_path=wake,
            handoff_path=handoff,
            holder_receipt_path=holder,
            closure_receipt_path=closure,
            holder_receipt=holder_payload,
        )
    handoff.write_text(original_handoff, encoding="utf-8")
    handoff.write_text(
        original_handoff.replace(str(closure), str(tmp_path / "other.json")),
        encoding="utf-8",
    )
    wake.write_text(
        wake.read_text(encoding="utf-8").replace(
            MODULE.sha256_bytes(original_handoff.encode("utf-8")),
            MODULE.sha256_bytes(handoff.read_bytes()),
        ),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.IncarnationHomeError, match="closure receipt identity"):
        MODULE._validate_wake_delivery(
            wake_receipt_path=wake,
            handoff_path=handoff,
            holder_receipt_path=holder,
            closure_receipt_path=closure,
            holder_receipt=holder_payload,
        )
