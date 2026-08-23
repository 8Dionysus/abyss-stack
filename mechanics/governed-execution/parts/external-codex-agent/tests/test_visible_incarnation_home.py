from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


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


def _capability_grant(
    path: Path,
    *,
    ambient: Path,
    realization: Path,
    ambient_entry: str,
    expires_at: str = "2099-01-01T00:00:00Z",
) -> Path:
    realization_payload = json.loads(realization.read_text(encoding="utf-8"))
    payload = {
        "$schema": "schemas/external-codex-capability-grant.schema.json",
        "schema_version": MODULE.CAPABILITY_GRANT_SCHEMA_VERSION,
        "grant_id": f"grant:test/{ambient_entry}",
        "capability_id": f"codex.home.{ambient_entry}",
        "capability_class": "operator_control",
        "ambient_entry": ambient_entry,
        "effect": "project_shared_link",
        "subject": {
            "ambient_home_identity": MODULE._ambient_home_identity(ambient),
            "model_realization_id": realization_payload["model_realization_id"],
            "incarnation_coordinate": MODULE._incarnation_coordinate(
                realization_payload["model_realization_id"],
                realization_payload["configuration_fingerprint"],
            ),
        },
        "expires_at": expires_at,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _terminal_binding_fixture(
    tmp_path: Path,
) -> tuple[socket.socket, dict[str, object], dict[str, object], dict[str, object]]:
    state_root = tmp_path / "state"
    state_root.mkdir()
    closeout_route = tmp_path / "closeout.sh"
    closeout_route.write_text("#!/bin/sh\n", encoding="utf-8")
    context = {
        "goal_ref": "goal:test-terminal-observability",
        "actor_ref": "actor:test-terminal-observability",
        "incarnation_ref": "incarnation:test-terminal-observability",
        "session_ref": "session:test-terminal-observability",
        "runtime_state_root": str(state_root),
        "closeout_route": str(closeout_route),
    }
    socket_path = tmp_path / "kitty.sock"
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    binding = MODULE._terminal_binding(
        context=context,
        control_socket=f"unix:{socket_path}",
        terminal_title="Luna Max — terminal observability repair",
        window_id="7",
        tty="/dev/pts/7",
        holder_pid=101,
        holder_start_ticks=1001,
        holder_argv_digest=MODULE.sha256_bytes(
            MODULE.canonical_bytes(["/usr/bin/codex", "exec"])
        ),
        holder_exe_digest="sha256:" + "1" * 64,
        terminal_pid=202,
        terminal_start_ticks=2002,
    )
    holder = binding["holder"]
    terminal = binding["terminal"]
    assert isinstance(holder, dict) and isinstance(terminal, dict)
    return listener, binding, holder, terminal


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
    assert manifest["top_level_posture"] == "incarnation-home"
    Draft202012Validator(
        json.loads(
            (PART / "schemas" / "external-codex-incarnation-home.schema.json").read_text(
                encoding="utf-8"
            )
        )
    ).validate(manifest)


def test_capability_projection_denies_ambient_operator_control_by_default(
    tmp_path: Path,
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "auth.json").write_text("{}", encoding="utf-8")
    (ambient / "sessions").mkdir()
    (ambient / "skills").mkdir()
    (ambient / "app-server-control").mkdir()
    (ambient / "app-server-daemon").mkdir()
    (ambient / "hooks.json").write_text("{}", encoding="utf-8")
    (ambient / "future-capability").write_text("{}", encoding="utf-8")

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )

    entries = manifest["capability_projection"]["entries"]
    for name in ("auth.json", "sessions", "skills"):
        assert entries[name]["projection"] == "shared_link"
        assert entries[name]["grantable"] is False
        assert (Path(manifest["codex_home"]) / name).is_symlink()
    for name in ("app-server-control", "app-server-daemon", "hooks.json"):
        assert entries[name]["capability_class"] == "operator_control"
        assert entries[name]["projection"] == "denied"
        assert entries[name]["grantable"] is True
        assert not (Path(manifest["codex_home"]) / name).exists()
    assert entries["future-capability"]["capability_class"] == "unknown"
    assert entries["future-capability"]["projection"] == "denied"
    assert entries["future-capability"]["grantable"] is True
    assert manifest["shared_state_names"] == ["auth.json", "sessions", "skills"]
    assert all(
        entry["explicit_grant"] is None for entry in entries.values()
    )


def test_capability_class_registry_is_authored_data_with_explicit_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        (PART / MODULE.CAPABILITY_CLASS_REGISTRY_NAME).read_text(encoding="utf-8")
    )
    registry["classes"]["session_continuity"]["entries"].append(
        "custom-continuity"
    )
    registry_path = tmp_path / MODULE.CAPABILITY_CLASS_REGISTRY_NAME
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    Draft202012Validator(
        json.loads(
            (PART / "schemas" / "external-codex-capability-classes.schema.json").read_text(
                encoding="utf-8"
            )
        )
    ).validate(registry)
    monkeypatch.setattr(MODULE, "CAPABILITY_CLASS_REGISTRY_PATH", registry_path)

    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "custom-continuity").mkdir()
    (ambient / "future-capability").write_text("{}", encoding="utf-8")

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    entries = manifest["capability_projection"]["entries"]
    assert entries["custom-continuity"]["capability_class"] == "session_continuity"
    assert entries["custom-continuity"]["projection"] == "shared_link"
    assert entries["future-capability"]["capability_class"] == "unknown"
    assert entries["future-capability"]["projection"] == "denied"
    assert entries["future-capability"]["grantable"] is True
    assert manifest["capability_projection"]["capability_class_registry"][
        "path"
    ] == str(registry_path)


def test_capability_class_ids_are_unique_structural_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        (PART / MODULE.CAPABILITY_CLASS_REGISTRY_NAME).read_text(encoding="utf-8")
    )
    schema = json.loads(
        (PART / "schemas" / "external-codex-capability-classes.schema.json").read_text(
            encoding="utf-8"
        )
    )
    legacy_array_registry = dict(registry)
    legacy_array_registry["classes"] = list(registry["classes"].values())
    assert list(Draft202012Validator(schema).iter_errors(legacy_array_registry))

    registry["classes"]["future_semantic"] = {
        "projection": "denied",
        "grantable": False,
        "entries": ["future-capability"],
    }
    registry["classes"]["future_semantic_next"] = {
        "projection": "denied",
        "grantable": False,
        "entries": ["future-capability-next"],
    }
    Draft202012Validator(schema).validate(registry)
    registry_path = tmp_path / MODULE.CAPABILITY_CLASS_REGISTRY_NAME
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(MODULE, "CAPABILITY_CLASS_REGISTRY_PATH", registry_path)

    _metadata, definitions, _unknown = MODULE._load_capability_class_registry()
    assert definitions["future-capability"]["capability_class"] == "future_semantic"
    assert (
        definitions["future-capability-next"]["capability_class"]
        == "future_semantic_next"
    )


def test_capability_class_registry_rejects_operator_control_policy_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        (PART / MODULE.CAPABILITY_CLASS_REGISTRY_NAME).read_text(encoding="utf-8")
    )
    operator_control = registry["classes"]["operator_control"]
    operator_control["projection"] = "shared_link"
    registry_path = tmp_path / MODULE.CAPABILITY_CLASS_REGISTRY_NAME
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    schema = json.loads(
        (PART / "schemas" / "external-codex-capability-classes.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(Draft202012Validator(schema).iter_errors(registry))
    monkeypatch.setattr(MODULE, "CAPABILITY_CLASS_REGISTRY_PATH", registry_path)

    with pytest.raises(
        MODULE.IncarnationHomeError, match="safe tuple"
    ):
        MODULE._load_capability_class_registry()


def test_capability_class_registry_rejects_unsafe_future_authority_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        (PART / MODULE.CAPABILITY_CLASS_REGISTRY_NAME).read_text(encoding="utf-8")
    )
    registry["classes"]["future_semantic"] = {
        "projection": "shared_link",
        "grantable": False,
        "entries": ["future-capability"],
    }
    registry_path = tmp_path / MODULE.CAPABILITY_CLASS_REGISTRY_NAME
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    schema = json.loads(
        (PART / "schemas" / "external-codex-capability-classes.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(Draft202012Validator(schema).iter_errors(registry))
    monkeypatch.setattr(MODULE, "CAPABILITY_CLASS_REGISTRY_PATH", registry_path)

    with pytest.raises(
        MODULE.IncarnationHomeError, match="safe tuple"
    ):
        MODULE._load_capability_class_registry()


def test_safe_future_registry_class_produces_schema_valid_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        (PART / MODULE.CAPABILITY_CLASS_REGISTRY_NAME).read_text(encoding="utf-8")
    )
    registry["classes"]["future_semantic"] = {
        "projection": "denied",
        "grantable": False,
        "entries": ["future-capability"],
    }
    registry_path = tmp_path / MODULE.CAPABILITY_CLASS_REGISTRY_NAME
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    registry_schema = json.loads(
        (PART / "schemas" / "external-codex-capability-classes.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(registry_schema).validate(registry)
    monkeypatch.setattr(MODULE, "CAPABILITY_CLASS_REGISTRY_PATH", registry_path)

    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "future-capability").write_text("{}", encoding="utf-8")

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    manifest_schema = json.loads(
        (PART / "schemas" / "external-codex-incarnation-home.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(manifest_schema).validate(manifest)
    entry = manifest["capability_projection"]["entries"]["future-capability"]
    assert entry == {
        "capability_class": "future_semantic",
        "projection": "denied",
        "grantable": False,
        "explicit_grant": None,
    }


def test_capability_projection_reuses_subject_grant_without_binding_endpoint_bytes(
    tmp_path: Path,
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "app-server-control").mkdir()
    realization = _realization(tmp_path / "realization.json")
    grant = _capability_grant(
        tmp_path / "grant.json",
        ambient=ambient,
        realization=realization,
        ambient_entry="app-server-control",
    )
    Draft202012Validator(
        json.loads(
            (PART / "schemas" / "external-codex-capability-grant.schema.json").read_text(
                encoding="utf-8"
            )
        )
    ).validate(json.loads(grant.read_text(encoding="utf-8")))

    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
        capability_grants=[grant],
    )
    control_link = Path(manifest["codex_home"]) / "app-server-control"
    assert control_link.is_symlink()
    projection = manifest["capability_projection"]
    granted_entry = projection["entries"]["app-server-control"]
    assert granted_entry["capability_class"] == "operator_control"
    assert granted_entry["grantable"] is True
    assert granted_entry["explicit_grant"]["grant_id"] == (
        "grant:test/app-server-control"
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    MODULE._load_manifest(manifest_path)

    (ambient / "app-server-control" / "dynamic-state.json").write_text(
        "changed-endpoint-state", encoding="utf-8"
    )
    MODULE._load_manifest(manifest_path)
    second_manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
        capability_grants=[grant],
    )
    assert second_manifest["capability_projection"]["entries"][
        "app-server-control"
    ]["explicit_grant"]["grant_id"] == "grant:test/app-server-control"

    stale_payload = json.loads(grant.read_text(encoding="utf-8"))
    stale_payload["expires_at"] = "2000-01-01T00:00:00Z"
    grant.write_text(json.dumps(stale_payload), encoding="utf-8")
    with pytest.raises(MODULE.IncarnationHomeError, match="stale or expired"):
        MODULE._load_manifest(Path(manifest["codex_home"]).parent / "incarnation-home.json")


def test_manifest_schema_requires_explicit_grant_for_shared_operator_entry(
    tmp_path: Path,
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "app-server-control").mkdir()
    realization = _realization(tmp_path / "realization.json")
    grant = _capability_grant(
        tmp_path / "grant.json",
        ambient=ambient,
        realization=realization,
        ambient_entry="app-server-control",
    )
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
        capability_grants=[grant],
    )
    forged = json.loads(json.dumps(manifest))
    forged["capability_projection"]["entries"]["app-server-control"][
        "explicit_grant"
    ] = None
    manifest_schema = json.loads(
        (PART / "schemas" / "external-codex-incarnation-home.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert list(Draft202012Validator(manifest_schema).iter_errors(forged))

    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    manifest_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(MODULE.IncarnationHomeError, match="projection drift"):
        MODULE._load_manifest(manifest_path)

    forged = json.loads(json.dumps(manifest))
    forged["capability_projection"]["entries"]["app-server-control"][
        "explicit_grant"
    ]["grant_id"] = "forged-without-grant"
    assert not list(Draft202012Validator(manifest_schema).iter_errors(forged))
    manifest_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(MODULE.IncarnationHomeError, match="projection drift"):
        MODULE._load_manifest(manifest_path)


def test_capability_projection_rejects_replayed_grant_subject(
    tmp_path: Path,
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    ambient.mkdir()
    runtime_root.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    (ambient / "future-capability").write_text("{}", encoding="utf-8")
    realization = _realization(tmp_path / "realization.json")
    grant = _capability_grant(
        tmp_path / "grant.json",
        ambient=ambient,
        realization=realization,
        ambient_entry="future-capability",
    )
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=realization,
        runtime_root=runtime_root,
        capability_grants=[grant],
    )
    grant_payload = json.loads(grant.read_text(encoding="utf-8"))
    grant_payload["subject"]["incarnation_coordinate"] = "sha256:" + "0" * 64
    grant.write_text(json.dumps(grant_payload), encoding="utf-8")

    with pytest.raises(
        MODULE.IncarnationHomeError, match="subject does not match incarnation"
    ):
        MODULE._load_manifest(Path(manifest["codex_home"]).parent / "incarnation-home.json")


@pytest.mark.parametrize(
    "schema_name",
    [
        "external-codex-incarnation-home.schema.json",
        "external-codex-capability-grant.schema.json",
        "external-codex-capability-classes.schema.json",
    ],
)
def test_capability_projection_schemas_are_valid_json(schema_name: str) -> None:
    schema = json.loads(
        (PART / "schemas" / schema_name).read_text(encoding="utf-8")
    )
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    Draft202012Validator.check_schema(schema)


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

    with pytest.raises(
        MODULE.IncarnationHomeError, match="capability projection link drift"
    ):
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
    manifest_snapshot = manifest_path.read_bytes()
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
        bwrap_inner_argv = argv[argv.index("--") + 1 :]
        payload_separator = bwrap_inner_argv.index("--")
        payload_argv = bwrap_inner_argv[:payload_separator]
        inner_argv = bwrap_inner_argv[payload_separator + 1 :]
        launcher_file_index = next(
            index
            for index, value in enumerate(argv)
            if value == "--file" and argv[index + 2] == "/var/tmp/codex"
        )
        launcher_fd = int(argv[launcher_file_index + 1])
        launcher_mode_index = next(
            index
            for index, value in enumerate(argv)
            if value == "--chmod" and argv[index + 2] == "/var/tmp/codex"
        )
        os.lseek(launcher_fd, 0, os.SEEK_SET)
        captured.update(
            path=path,
            argv=argv,
            payload_argv=payload_argv,
            inner_argv=inner_argv,
            environment=environment,
            inode_content=os.read(launcher_fd, 1 << 20),
        )
        captured["snapshot_path"] = Path(inner_argv[0])
        captured["snapshot_mode"] = int(
            argv[launcher_mode_index + 1], 8
        )
        MODULE._holder_receipt(
            receipt_path=receipt_path,
            manifest_path=manifest_path,
            manifest=manifest,
            executable=executable,
            argv=inner_argv,
            executable_bytes=original_content,
            executable_digest=MODULE.sha256_bytes(original_content),
            manifest_bytes=manifest_snapshot,
            manifest_digest=MODULE.sha256_bytes(manifest_snapshot),
        )

    original_holder_receipt = MODULE._holder_receipt

    def replace_command_path_after_receipt(**kwargs: object) -> dict[str, object]:
        receipt = original_holder_receipt(**kwargs)
        executable.write_text("mutated-in-place", encoding="utf-8")
        replacement = tmp_path / "replacement-codex"
        replacement.write_text("replacement", encoding="utf-8")
        replacement.chmod(0o700)
        os.replace(replacement, executable)
        manifest_path.write_bytes(manifest_snapshot)
        return receipt

    original_bound_codex_argv = MODULE.bound_codex_argv

    def replace_manifest_after_binding(**kwargs: object) -> list[str]:
        result = original_bound_codex_argv(**kwargs)
        manifest_path.write_bytes(b"replaced-after-manifest-load")
        return result

    monkeypatch.setattr(
        MODULE, "_holder_receipt", replace_command_path_after_receipt
    )
    monkeypatch.setattr(
        MODULE, "bound_codex_argv", replace_manifest_after_binding
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
    monkeypatch.setattr(MODULE, "_spawn_named_snapshot_cleanup", lambda **_: None)
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
        original_executable, captured["inner_argv"]
    )
    assert receipt["holder"]["exe_digest"] == MODULE._post_exec_executable_digest(
        executable,
        path=os.environ.get("PATH"),
        executable_bytes=original_content,
    )
    assert receipt["holder"]["exe_digest"] != MODULE.sha256_bytes(original_content)
    assert receipt["terminal"]["binding"] == "kitty_ancestor_at_exec"
    assert receipt["terminal"]["pid"] == terminal_pid
    assert receipt["terminal"]["argv"] == terminal_argv
    assert receipt["terminal"]["window_id"] == "1"
    assert receipt["terminal"]["dedicated"] is True
    assert receipt["runtime"]["incarnation_manifest"] == str(manifest_path)
    assert receipt["runtime"]["incarnation_manifest_digest"] == MODULE.sha256_bytes(
        manifest_snapshot
    )
    assert base64.b64decode(
        receipt["runtime"]["incarnation_manifest_snapshot_b64"]
    ) == manifest_snapshot
    assert receipt["runtime"]["model"] == "gpt-5.6-luna"
    assert receipt["runtime"]["reasoning_effort"] == "max"
    assert captured["environment"]["CODEX_HOME"] == str(manifest["codex_home"])
    assert captured["path"] == "/usr/bin/bwrap"
    assert captured["payload_argv"][0] == sys.executable
    assert captured["payload_argv"][1] == str(Path(MODULE.__file__).resolve())
    assert captured["payload_argv"][2] == "payload-launch"
    manifest_snapshot_argument_index = captured["payload_argv"].index(
        "--manifest-snapshot-b64"
    )
    assert captured["payload_argv"][manifest_snapshot_argument_index + 1] == (
        base64.b64encode(manifest_snapshot).decode("ascii")
    )
    payload_executable_index = captured["payload_argv"].index(
        "--payload-executable"
    )
    assert captured["payload_argv"][payload_executable_index + 1] == "/var/tmp/codex"
    assert "--die-with-parent" in captured["argv"]
    assert captured["snapshot_path"] == Path("/var/tmp/codex")
    assert captured["inner_argv"][0] == "/var/tmp/codex"
    assert "--tmpfs" in captured["argv"]
    assert "--remount-ro" in captured["argv"]
    snapshot_dir = next(
        path
        for path in (Path(manifest["codex_home"]) / "tmp").iterdir()
        if path.name.startswith("abyss-stack-codex-package-")
    )
    snapshot_path = next(snapshot_dir.rglob("codex"))
    assert snapshot_dir.name.startswith("abyss-stack-codex-package-")
    assert snapshot_path.parent != executable.parent
    assert stat.S_IMODE(snapshot_path.parent.stat().st_mode) == 0o500
    assert captured["snapshot_mode"] == 0o500
    assert captured["inode_content"] == original_content
    assert executable.read_text(encoding="utf-8") == "replacement"
    MODULE._load_manifest_snapshot(manifest_path)
    MODULE._remove_named_snapshot(
        snapshot_path, snapshot_dir=snapshot_dir
    )
    assert not snapshot_dir.exists()

    executable.write_bytes(original_content)
    executable.chmod(0o700)
    with pytest.raises(MODULE.IncarnationHomeError, match="already exists"):
        MODULE.command_launch(args)


def test_payload_launch_binds_receipt_to_payload_process(
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
    manifest_bytes = manifest_path.read_bytes()
    payload = tmp_path / "private-codex"
    payload_bytes = b"#!/bin/sh\nexit 0\n"
    payload.write_bytes(payload_bytes)
    payload.chmod(0o500)
    receipt_path = tmp_path / "holder.json"
    observed: dict[str, object] = {}

    def fake_holder_receipt(**kwargs: object) -> dict[str, object]:
        observed["pid"] = os.getpid()
        observed.update(kwargs)
        return {}

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        observed["exec"] = (path, argv, environment)

    monkeypatch.setattr(MODULE, "_holder_receipt", fake_holder_receipt)
    monkeypatch.setattr(MODULE.os, "execve", fake_exec)
    args = MODULE.argparse.Namespace(
        manifest=str(manifest_path),
        holder_receipt=str(receipt_path),
        codex_executable=str(tmp_path / "codex"),
        payload_executable=str(payload),
        manifest_digest=MODULE.sha256_bytes(manifest_bytes),
        executable_digest=MODULE.sha256_bytes(payload_bytes),
        codex_arguments=[str(payload), "exec", "--help"],
    )

    assert MODULE.command_payload_launch(args) == 127
    assert observed["pid"] == os.getpid()
    assert observed["executable"] == Path(args.codex_executable)
    assert observed["argv"] == args.codex_arguments
    assert observed["executable_bytes"] == payload_bytes
    assert observed["executable_digest"] == args.executable_digest
    exec_path, exec_argv, environment = observed["exec"]
    assert exec_path == str(payload)
    assert exec_argv == args.codex_arguments
    assert environment["CODEX_HOME"] == str(manifest["codex_home"])


@pytest.mark.parametrize(("decision", "exec_expected"), [("admit", True), ("reject", False)])
def test_payload_launch_requires_parent_admission_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    exec_expected: bool,
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
    manifest_bytes = manifest_path.read_bytes()
    payload = tmp_path / "private-codex"
    payload_bytes = b"#!/bin/sh\nexit 0\n"
    payload.write_bytes(payload_bytes)
    payload.chmod(0o500)
    holder_path = tmp_path / "holder.json"
    gate_path = tmp_path / "holder.json.launch-gate.json"
    context_path = tmp_path / "context.json"
    state_root = tmp_path / "state"
    state_root.mkdir()
    context_path.write_text(
        json.dumps(
            {
                "goal_ref": "goal:test",
                "actor_ref": "actor:test",
                "incarnation_ref": "incarnation:test",
                "session_ref": "session:test",
                "runtime_state_root": str(state_root),
                "closeout_route": str(tmp_path / "closeout.sh"),
            }
        ),
        encoding="utf-8",
    )
    context_bytes = context_path.read_bytes()
    token = "launch-gate-test-token"
    MODULE._write_visible_launch_gate(
        gate_path=gate_path,
        holder_receipt_path=holder_path,
        token=token,
        decision=decision,
    )
    observed: dict[str, object] = {}

    def fake_holder_receipt(**_kwargs: object) -> dict[str, object]:
        MODULE._write_new_json(holder_path, {"published": True}, "holder receipt")
        return {"published": True}

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        observed["exec"] = (path, argv, environment)

    monkeypatch.setattr(MODULE, "_holder_receipt", fake_holder_receipt)
    monkeypatch.setattr(MODULE.os, "execve", fake_exec)
    args = MODULE.argparse.Namespace(
        manifest=str(manifest_path),
        holder_receipt=str(holder_path),
        codex_executable=str(payload),
        payload_executable=str(payload),
        manifest_digest=MODULE.sha256_bytes(manifest_bytes),
        executable_digest=MODULE.sha256_bytes(payload_bytes),
        binding_context_snapshot_b64=base64.b64encode(context_bytes).decode("ascii"),
        binding_context_digest=MODULE.sha256_bytes(context_bytes),
        control_socket="unix:/tmp/aoa-launch-gate-test.sock",
        terminal_title="visible-holder",
        launch_gate=str(gate_path),
        launch_gate_token=token,
        codex_arguments=[str(payload), "exec", "--help"],
    )

    if exec_expected:
        assert MODULE.command_payload_launch(args) == 127
        assert "exec" in observed
    else:
        with pytest.raises(
            MODULE.IncarnationHomeError,
            match="admission was rejected before payload execution",
        ):
            MODULE.command_payload_launch(args)
        assert "exec" not in observed


def test_launch_gate_rejects_shared_parent(tmp_path: Path) -> None:
    shared_parent = tmp_path / "shared"
    shared_parent.mkdir()
    shared_parent.chmod(0o777)

    with pytest.raises(MODULE.IncarnationHomeError, match="not private"):
        MODULE._validate_launch_gate_path(shared_parent / "launch-gate.json")


def test_payload_launch_uses_private_companion_after_host_copy_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    private_package = tmp_path / "private-package"
    ambient.mkdir()
    runtime_root.mkdir()
    private_package.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    manifest_bytes = manifest_path.read_bytes()
    host_package = tmp_path / "package"
    host_executable = host_package / "vendor" / "codex" / "codex"
    host_executable.parent.mkdir(parents=True)
    (host_package / "package.json").write_text("{}\n", encoding="utf-8")
    host_executable.write_bytes(b"host-codex")
    host_executable.chmod(0o700)
    host_companion = host_executable.parent / MODULE.CODE_MODE_HOST_NAME
    companion_bytes = b"private-companion"
    host_companion.write_bytes(companion_bytes)
    host_companion.chmod(0o700)
    payload = private_package / "codex"
    payload.write_bytes(b"#!/bin/sh\nexit 0\n")
    payload.chmod(0o500)
    private_companion = private_package / MODULE.CODE_MODE_HOST_NAME
    private_companion.write_bytes(companion_bytes)
    private_companion.chmod(0o500)
    observed: dict[str, object] = {}

    def fake_holder_receipt(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {}

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        observed["exec"] = (path, argv, environment)

    monkeypatch.setattr(MODULE, "_holder_receipt", fake_holder_receipt)
    monkeypatch.setattr(MODULE.os, "execve", fake_exec)
    host_companion.unlink()
    (host_package / "package.json").unlink()
    manifest_path.unlink()
    args = MODULE.argparse.Namespace(
        manifest=str(manifest_path),
        holder_receipt=str(tmp_path / "holder.json"),
        codex_executable=str(host_executable),
        payload_executable=str(payload),
        manifest_digest=MODULE.sha256_bytes(manifest_bytes),
        manifest_snapshot_b64=base64.b64encode(manifest_bytes).decode("ascii"),
        executable_digest=MODULE.sha256_bytes(payload.read_bytes()),
        companion_path=str(host_companion),
        companion_digest=MODULE.sha256_bytes(companion_bytes),
        companion_relative=(
            "vendor/codex/" + MODULE.CODE_MODE_HOST_NAME
        ),
        codex_arguments=[str(payload), "exec", "--help"],
    )

    assert MODULE.command_payload_launch(args) == 127
    assert observed["companion_binding"] == {
        "path": str(host_companion),
        "digest": MODULE.sha256_bytes(companion_bytes),
        "relation": "adjacent_immutable_package",
        "package_relative": "vendor/codex/" + MODULE.CODE_MODE_HOST_NAME,
    }
    exec_path, exec_argv, environment = observed["exec"]
    assert exec_path == str(payload)
    assert exec_argv == args.codex_arguments
    assert environment["CODEX_HOME"] == str(manifest["codex_home"])


def test_payload_launch_accepts_shebang_package_relative_companion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient = tmp_path / "ambient"
    runtime_root = tmp_path / "runtime"
    private_package = tmp_path / "private-package"
    ambient.mkdir()
    runtime_root.mkdir()
    private_package.mkdir()
    (ambient / "config.toml").write_text('model = "sol"\n', encoding="utf-8")
    manifest = MODULE.prepare_home(
        ambient_home=ambient,
        realization_path=_realization(tmp_path / "realization.json"),
        runtime_root=runtime_root,
    )
    manifest_path = Path(manifest["codex_home"]).parent / "incarnation-home.json"
    manifest_bytes = manifest_path.read_bytes()
    host_package = tmp_path / "host-package"
    host_executable = host_package / "vendor" / "codex" / "codex"
    host_executable.parent.mkdir(parents=True)
    (host_package / "package.json").write_text("{}\n", encoding="utf-8")
    host_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    host_executable.chmod(0o700)
    host_companion = host_executable.parent / MODULE.CODE_MODE_HOST_NAME
    companion_bytes = b"private-shebang-companion"
    host_companion.write_bytes(companion_bytes)
    host_companion.chmod(0o700)
    (private_package / "package.json").write_text("{}\n", encoding="utf-8")
    payload = private_package / "vendor" / "codex" / "codex"
    payload.parent.mkdir(parents=True)
    payload.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    payload.chmod(0o500)
    private_companion = payload.parent / MODULE.CODE_MODE_HOST_NAME
    private_companion.write_bytes(companion_bytes)
    private_companion.chmod(0o500)
    observed: dict[str, object] = {}

    def fake_holder_receipt(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {}

    def fake_exec(path: str, argv: list[str], environment: dict[str, str]) -> None:
        observed["exec"] = (path, argv, environment)

    monkeypatch.setattr(MODULE, "_holder_receipt", fake_holder_receipt)
    monkeypatch.setattr(MODULE.os, "execve", fake_exec)
    args = MODULE.argparse.Namespace(
        manifest=str(manifest_path),
        holder_receipt=str(tmp_path / "holder.json"),
        codex_executable=str(host_executable),
        payload_executable=str(payload),
        manifest_digest=MODULE.sha256_bytes(manifest_bytes),
        executable_digest=MODULE.sha256_bytes(payload.read_bytes()),
        companion_path=str(host_companion),
        companion_digest=MODULE.sha256_bytes(companion_bytes),
        companion_relative=(
            "vendor/codex/" + MODULE.CODE_MODE_HOST_NAME
        ),
        codex_arguments=[str(payload), "exec", "--help"],
    )

    assert MODULE.command_payload_launch(args) == 127
    assert observed["companion_binding"] == {
        "path": str(host_companion),
        "digest": MODULE.sha256_bytes(companion_bytes),
        "relation": "adjacent_immutable_package",
        "package_relative": "vendor/codex/" + MODULE.CODE_MODE_HOST_NAME,
    }


def test_elf_binding_rejects_executable_replacement_during_companion_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_bytes(b"original-executable")
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    companion.write_bytes(b"companion")
    companion.chmod(0o700)
    original_adjacent = MODULE._adjacent_code_mode_host

    def replace_before_companion(path: Path) -> tuple[Path, bytes, dict[str, str]]:
        replacement = path.with_name("codex-replacement")
        replacement.write_bytes(b"replacement-executable")
        replacement.chmod(0o700)
        os.replace(replacement, path)
        return original_adjacent(path)

    monkeypatch.setattr(MODULE, "_adjacent_code_mode_host", replace_before_companion)
    with pytest.raises(
        MODULE.IncarnationHomeError,
        match="executable changed while binding companion",
    ):
        MODULE._open_verified_executable(executable)


def test_elf_binding_rechecks_absent_companion_before_anonymous_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_bytes(b"executable")
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    original_adjacent = MODULE._adjacent_code_mode_host
    calls = 0

    def companion_appears(
        path: Path,
    ) -> tuple[Path, bytes, dict[str, str]] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return None
        companion.write_bytes(b"companion")
        companion.chmod(0o700)
        return original_adjacent(path)

    monkeypatch.setattr(MODULE, "_adjacent_code_mode_host", companion_appears)
    with pytest.raises(
        MODULE.IncarnationHomeError,
        match="companion appeared while binding executable",
    ):
        MODULE._open_verified_executable(executable)
    assert calls == 2


def test_companion_binding_rejects_permission_revocation_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_bytes(b"executable")
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    companion.write_bytes(b"companion")
    companion.chmod(0o700)
    original_read = MODULE._read_verified_regular_file

    def revoke_before_open(
        path: Path, *, label: str
    ) -> tuple[bytes, os.stat_result]:
        path.chmod(0o600)
        return original_read(path, label=label)

    monkeypatch.setattr(MODULE, "_read_verified_regular_file", revoke_before_open)
    with pytest.raises(MODULE.IncarnationHomeError, match="identity changed"):
        MODULE._open_verified_executable(executable)


def test_companion_binding_rejects_effective_permission_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable.write_bytes(b"executable")
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    companion.write_bytes(b"companion")
    companion.chmod(0o704)
    original_access = MODULE.os.access

    def deny_companion_execute(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int,
        *args: object,
        **kwargs: object,
    ) -> bool:
        if Path(path) == companion and mode == MODULE.os.X_OK:
            return False
        return original_access(path, mode, *args, **kwargs)

    monkeypatch.setattr(MODULE.os, "access", deny_companion_execute)
    with pytest.raises(MODULE.IncarnationHomeError, match="current user"):
        MODULE._open_verified_executable(executable)


def test_atomic_json_fsyncs_publication_directory(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    fsync_targets: list[str] = []
    original_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_targets.append(os.readlink(f"/proc/self/fd/{fd}"))
        original_fsync(fd)

    original_module_fsync = MODULE.os.fsync
    MODULE.os.fsync = recording_fsync
    try:
        MODULE._write_new_json(path, {"ok": True}, "test receipt")
    finally:
        MODULE.os.fsync = original_module_fsync

    assert str(tmp_path) in fsync_targets
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}


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


def test_holder_terminal_binding_waits_for_causal_kitty_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def transient_ancestor(holder_pid: int) -> tuple[int, int, list[str]]:
        nonlocal attempts
        assert holder_pid == 7001
        attempts += 1
        if attempts < 3:
            raise MODULE.IncarnationHomeError("process ancestry is transient")
        return 7003, 7103, ["kitty", "--detach"]

    monkeypatch.setattr(MODULE, "_kitty_ancestor", transient_ancestor)
    monkeypatch.setattr(
        MODULE,
        "_kitty_dedication",
        lambda *, holder_pid, kitty_pid, terminal_argv: ("7", True),
    )
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    assert MODULE._wait_for_visible_terminal_binding(holder_pid=7001) == (
        7003,
        7103,
        ["kitty", "--detach"],
        "7",
        True,
    )
    assert attempts == 3


def test_holder_receipt_rejects_detached_kitty_route(tmp_path: Path) -> None:
    args = MODULE.argparse.Namespace(
        holder_receipt=str(tmp_path / "holder.json"),
        terminal_title="visible-holder",
        binding_context=None,
        control_socket=None,
        kitty_executable="/usr/bin/kitty",
        manifest=str(tmp_path / "missing-manifest.json"),
        codex_executable=str(tmp_path / "codex"),
        codex_arguments=["exec", "--help"],
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="canonical visible launch"):
        MODULE.command_launch(args)


@pytest.mark.parametrize(
    ("reject_receipt", "reject_identity", "publish_receipt"),
    [(False, False, True), (True, False, True), (False, True, True),
     (False, False, False)],
)
def test_detached_launch_publishes_socket_only_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    reject_receipt: bool,
    reject_identity: bool,
    publish_receipt: bool,
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
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    holder_path = tmp_path / "holder.json"
    context_path = tmp_path / "context.json"
    state_root = tmp_path / "state"
    state_root.mkdir()
    context_path.write_text(
        json.dumps(
            {
                "goal_ref": "goal:test",
                "actor_ref": "actor:test",
                "incarnation_ref": "incarnation:test",
                "session_ref": "session:test",
                "runtime_state_root": str(state_root),
                "closeout_route": str(tmp_path / "closeout.sh"),
            }
        ),
        encoding="utf-8",
    )
    socket_path = tmp_path / "kitty.sock"
    address = f"unix:{socket_path}"
    binding = {
        "schema_version": MODULE.TERMINAL_BINDING_SCHEMA_VERSION,
        "boot_id": MODULE._proc_boot_id(),
        "goal_ref": "goal:test",
        "actor_ref": "actor:test",
        "incarnation_ref": "incarnation:test",
        "session_ref": "session:test",
        "runtime_state_root": str(state_root),
        "closeout_route": str(tmp_path / "closeout.sh"),
        "holder": {"pid": 101, "start_ticks": 1001},
        "terminal": {
            "pid": 202,
            "start_ticks": 2002,
            "window_id": "7",
            "tty": "/dev/pts/7",
            "title": "visible token=<redacted>",
            "control_socket": {
                "address": address,
                "path": str(socket_path),
                "mode": 0o600,
                "device": 1,
                "inode": 1,
            },
        },
        "remote_control": "socket-only",
        "dedicated": True,
    }
    events: list[str] = []

    def accept_pre_exec_identity(
        _receipt: dict[str, object], **_kwargs: object
    ) -> tuple[object, ...]:
        events.append("pre-exec")
        return (101, 202, "kitty", "7", True)

    def accept_post_exec_identity(
        _receipt: dict[str, object]
    ) -> tuple[object, ...]:
        events.append("post-exec")
        return (101, 202, "kitty", "7", True)

    monkeypatch.setattr(
        MODULE,
        "_verify_command_version",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_terminal_identity",
        accept_post_exec_identity,
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_pre_exec_identity",
        accept_pre_exec_identity,
    )
    monkeypatch.setattr(MODULE, "_spawn_named_snapshot_cleanup", lambda **_: None)
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt",
        lambda _path: {"binding": binding, "holder": binding["holder"]},
    )
    termination_targets: list[dict[str, object]] = []
    if reject_receipt:

        def reject_visible_launch_receipt(**_kwargs: object) -> dict[str, object]:
            raise MODULE.IncarnationHomeError("receipt belongs to another launch")

        monkeypatch.setattr(
            MODULE, "_validate_visible_launch_receipt", reject_visible_launch_receipt
        )
        monkeypatch.setattr(
            MODULE,
            "_terminate_rejected_visible_launch",
            lambda receipt: termination_targets.append(receipt) or True,
        )
    else:
        monkeypatch.setattr(
            MODULE,
            "_validate_visible_launch_receipt",
            lambda **kwargs: kwargs["receipt"],
        )
    if reject_identity:

        def reject_holder_identity(_receipt: dict[str, object]) -> tuple[object, ...]:
            events.append("post-exec")
            raise MODULE.IncarnationHomeError("post-exec identity is transient")

        monkeypatch.setattr(
            MODULE,
            "_holder_terminal_identity",
            reject_holder_identity,
        )
        monkeypatch.setattr(
            MODULE,
            "_terminate_rejected_visible_launch",
            lambda receipt: termination_targets.append(receipt) or True,
        )
    captured: dict[str, object] = {}

    original_write_gate = MODULE._write_visible_launch_gate

    def record_write_gate(**kwargs: object) -> None:
        events.append(f"gate:{kwargs['decision']}")
        original_write_gate(**kwargs)  # type: ignore[arg-type]

    original_confirm_admission = MODULE._confirm_visible_launch_admission

    def record_confirm_admission(**kwargs: object) -> None:
        events.append("confirm")
        original_confirm_admission(**kwargs)  # type: ignore[arg-type]

    original_emit_safe_json = MODULE._emit_safe_json

    def record_emit_safe_json(*args: object, **kwargs: object) -> None:
        events.append("emit")
        original_emit_safe_json(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(MODULE, "_write_visible_launch_gate", record_write_gate)
    monkeypatch.setattr(
        MODULE, "_confirm_visible_launch_admission", record_confirm_admission
    )
    monkeypatch.setattr(MODULE, "_emit_safe_json", record_emit_safe_json)

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if publish_receipt:
            holder_path.write_text("published", encoding="utf-8")
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)
    args = MODULE.argparse.Namespace(
        holder_receipt=str(holder_path),
        binding_context=str(context_path),
        control_socket=address,
        terminal_title="visible token=secret",
        kitty_executable="/usr/bin/kitty",
        manifest=str(manifest_path),
        codex_executable=str(executable),
        codex_arguments=["exec", "--json"],
    )

    gate_path = holder_path.with_name(holder_path.name + ".launch-gate.json")
    if not publish_receipt or reject_receipt:
        with pytest.raises(
            MODULE.IncarnationHomeError, match="did not publish a live terminal binding"
        ):
            MODULE.command_launch(args)
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        assert gate["decision"] == "reject"
        if reject_receipt:
            assert termination_targets == []
        elif reject_identity:
            assert len(termination_targets) == 1
        else:
            assert termination_targets == []
        return

    if reject_identity:
        with pytest.raises(
            MODULE.IncarnationHomeError,
            match="post-exec identity acknowledgment",
        ):
            MODULE.command_launch(args)
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        assert gate["decision"] == "admit"
        assert len(termination_targets) == 1
        return

    assert MODULE.command_launch(args) == 0
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["decision"] == "admit"
    assert gate["holder_receipt_ref"] == str(holder_path.resolve())
    assert events[:5] == ["pre-exec", "gate:admit", "confirm", "post-exec", "emit"]
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert "--listen-on" in argv
    assert argv[argv.index("--listen-on") + 1] == address
    assert argv[argv.index("--title") + 1] == "visible token=<redacted>"
    assert argv[argv.index("--override") + 1] == "allow_remote_control=socket-only"
    assert "--launch-gate" in argv
    assert argv[argv.index("--launch-gate") + 1] == str(gate_path)
    output = capsys.readouterr().out
    assert "environment" not in output.casefold()
    assert "credential" not in output.casefold()


def test_holder_identity_uses_bound_manifest_snapshot_after_path_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex.js"
    executable.write_bytes(b"codex-holder\n")
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    companion.write_bytes(b"codex-code-mode-host\n")
    companion.chmod(0o700)
    manifest_path = tmp_path / "incarnation-home.json"
    launch_manifest = {
        "schema_version": MODULE.SCHEMA_VERSION,
        "model_slug": "gpt-5.6-luna",
        "reasoning_effort": "max",
        "ambient_codex_home": str(tmp_path / "ambient"),
        "codex_home": str(tmp_path / "incarnation"),
    }
    snapshot = json.dumps(launch_manifest, sort_keys=True).encode("utf-8")
    manifest_path.write_bytes(b"profile-refresh-replaced-this-path\n")
    holder_pid, parent_pid, kitty_pid = 101, 102, 103
    holder_argv = ["/usr/bin/codex", "exec"]
    kitty_argv = ["/usr/bin/kitty", "--title", "holder"]
    executable_digest = MODULE.sha256_bytes(executable.read_bytes())
    receipt = {
        "boot_id": "00000000-0000-0000-0000-000000000001",
        "holder": {
            "pid": holder_pid,
            "start_ticks": 11,
            "parent_pid": parent_pid,
            "parent_start_ticks": 12,
            "parent_comm": "bwrap",
            "argv": holder_argv,
            "argv_digest": MODULE.sha256_bytes(MODULE.canonical_bytes(holder_argv)),
            "exe_digest": executable_digest,
        },
        "runtime": {
            "codex_executable": str(executable),
            "codex_executable_digest": executable_digest,
            "codex_companion": {
                "path": str(companion),
                "digest": MODULE.sha256_bytes(companion.read_bytes()),
                "relation": "adjacent_immutable_package",
                "package_relative": MODULE.CODE_MODE_HOST_NAME,
            },
            "incarnation_manifest": str(manifest_path),
            "incarnation_manifest_digest": MODULE.sha256_bytes(snapshot),
            "incarnation_manifest_snapshot_b64": base64.b64encode(snapshot).decode(
                "ascii"
            ),
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path / "ambient"),
            "incarnation_codex_home": str(tmp_path / "incarnation"),
        },
        "terminal": {
            "pid": kitty_pid,
            "start_ticks": 13,
            "argv": kitty_argv,
            "window_id": "7",
            "dedicated": True,
        },
    }
    monkeypatch.setattr(MODULE, "_proc_boot_id", lambda: receipt["boot_id"])
    monkeypatch.setattr(
        MODULE, "_proc_start_ticks", lambda pid: {101: 11, 102: 12, 103: 13}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_parent_pid", lambda pid: {101: 102, 102: 103, 103: 1}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_comm", lambda pid: {102: "bwrap", 103: "kitty"}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_argv", lambda pid: {101: holder_argv, 103: kitty_argv}[pid]
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: executable_digest)
    monkeypatch.setattr(
        MODULE, "_kitty_dedication_from_receipt", lambda **_: ("7", True)
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_environ",
        lambda _pid: pytest.fail("post-return identity reopened holder environment"),
    )

    executable.unlink()
    companion.unlink()
    assert MODULE._holder_terminal_identity(receipt) == (
        holder_pid,
        kitty_pid,
        "kitty",
        "7",
        True,
    )


def test_legacy_holder_identity_preserves_path_digest_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable_bytes = b"legacy-holder-executable"
    executable.write_bytes(executable_bytes)
    executable.chmod(0o700)
    manifest = tmp_path / "incarnation-home.json"
    manifest_bytes = b"legacy-incarnation-manifest"
    manifest.write_bytes(manifest_bytes)
    holder_pid, parent_pid, kitty_pid = 101, 102, 103
    holder_argv = [str(executable), "exec"]
    kitty_argv = ["/usr/bin/kitty", "--detach", "--title", "holder"]
    boot_id = "00000000-0000-0000-0000-000000000002"
    receipt = {
        "boot_id": boot_id,
        "holder": {
            "pid": holder_pid,
            "start_ticks": 11,
            "parent_pid": parent_pid,
            "parent_start_ticks": 12,
            "parent_comm": "bwrap",
            "argv": holder_argv,
            "argv_digest": MODULE.sha256_bytes(MODULE.canonical_bytes(holder_argv)),
        },
        "runtime": {
            "codex_executable": str(executable),
            "codex_executable_digest": MODULE.sha256_bytes(executable_bytes),
            "incarnation_manifest": str(manifest),
            "incarnation_manifest_digest": MODULE.sha256_bytes(manifest_bytes),
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path / "ambient"),
            "incarnation_codex_home": str(tmp_path / "incarnation"),
        },
        "terminal": {
            "pid": kitty_pid,
            "start_ticks": 13,
            "argv": kitty_argv,
            "window_id": "7",
            "dedicated": True,
        },
    }
    monkeypatch.setattr(MODULE, "_proc_boot_id", lambda: boot_id)
    monkeypatch.setattr(
        MODULE, "_proc_start_ticks", lambda pid: {101: 11, 102: 12, 103: 13}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_parent_pid", lambda pid: {101: 102, 102: 103, 103: 1}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_comm", lambda pid: {102: "bwrap", 103: "kitty"}[pid]
    )
    monkeypatch.setattr(
        MODULE, "_proc_argv", lambda pid: {101: holder_argv, 103: kitty_argv}[pid]
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_exe_digest",
        lambda _pid: pytest.fail("legacy identity queried repaired executable digest"),
    )
    monkeypatch.setattr(
        MODULE, "_kitty_dedication_from_receipt", lambda **_: ("7", True)
    )

    assert MODULE._holder_terminal_identity(receipt) == (
        holder_pid,
        kitty_pid,
        "kitty",
        "7",
        True,
    )


def test_live_close_uses_holder_bound_companion_after_host_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "codex"
    executable_bytes = b"immutable-holder-executable"
    executable.write_bytes(executable_bytes)
    executable.chmod(0o700)
    companion = tmp_path / MODULE.CODE_MODE_HOST_NAME
    companion_bytes = b"immutable-holder-companion"
    companion.write_bytes(companion_bytes)
    companion.chmod(0o700)
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    manifest_snapshot = MODULE.canonical_bytes(
        {
            "schema_version": MODULE.SCHEMA_VERSION,
            "model_slug": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path / "ambient"),
            "codex_home": str(tmp_path / "incarnation"),
        }
    )
    holder_pid, parent_pid, kitty_pid = 101, 102, 103
    holder_argv = ["/usr/bin/codex", "exec"]
    kitty_argv = ["/usr/bin/kitty", "--detach", "--title", "holder"]
    holder_payload = {
        "schema_version": MODULE.HOLDER_RECEIPT_SCHEMA_VERSION,
        "receipt_ref": str(holder.resolve()),
        "created_at": "2026-08-15T00:00:00Z",
        "lifecycle_role": "responsibility_holder",
        "boot_id": MODULE._proc_boot_id(),
        "holder": {
            "pid": holder_pid,
            "start_ticks": 11,
            "parent_pid": parent_pid,
            "parent_start_ticks": 12,
            "parent_comm": "bwrap",
            "argv": holder_argv,
                "argv_digest": MODULE.sha256_bytes(
                    MODULE.canonical_bytes(holder_argv)
                ),
                "exe_digest": MODULE.sha256_bytes(executable_bytes),
        },
        "runtime": {
            "codex_executable": str(executable),
            "codex_executable_digest": MODULE.sha256_bytes(executable_bytes),
            "codex_companion": {
                "path": str(companion),
                "digest": MODULE.sha256_bytes(companion_bytes),
                "relation": "adjacent_immutable_package",
                "package_relative": MODULE.CODE_MODE_HOST_NAME,
            },
            "incarnation_manifest": str(tmp_path / "missing-manifest"),
            "incarnation_manifest_digest": MODULE.sha256_bytes(manifest_snapshot),
            "incarnation_manifest_snapshot_b64": base64.b64encode(
                manifest_snapshot
            ).decode("ascii"),
            "model": "gpt-5.6-luna",
            "reasoning_effort": "max",
            "ambient_codex_home": str(tmp_path / "ambient"),
            "incarnation_codex_home": str(tmp_path / "incarnation"),
        },
        "terminal": {
            "binding": "kitty_ancestor_at_exec",
            "required_comm": "kitty",
            "pid": kitty_pid,
            "start_ticks": 13,
            "argv": kitty_argv,
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
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": MODULE.sha256_bytes(
                            holder.read_bytes()
                        ),
                        "closure_receipt": str(closure.resolve()),
                        "holder_pid": holder_pid,
                        "terminal_pid": kitty_pid,
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
                "handoff_ref": str(handoff.resolve()),
                "handoff_sha256": MODULE.sha256_bytes(handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": True},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        MODULE,
        "_proc_start_ticks",
        lambda pid: {holder_pid: 11, parent_pid: 12, kitty_pid: 13}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_parent_pid",
        lambda pid: {holder_pid: parent_pid, parent_pid: kitty_pid, kitty_pid: 1}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_comm",
        lambda pid: {parent_pid: "bwrap", kitty_pid: "kitty"}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: {holder_pid: holder_argv, kitty_pid: kitty_argv}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_exe_digest",
        lambda _pid: MODULE.sha256_bytes(executable_bytes),
    )
    monkeypatch.setattr(
        MODULE, "_kitty_dedication_from_receipt", lambda **_: ("7", True)
    )
    states = iter(["live", "live", "gone", "gone"])
    monkeypatch.setattr(
        MODULE, "_proc_identity_state", lambda _pid, _start: next(states)
    )
    monkeypatch.setattr(MODULE, "_send_verified_term", lambda *_args: True)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    executable.unlink()
    companion.unlink()
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
    assert recorded["outcome"] == "closed"
    assert recorded["identity_state"] == "live"
    assert recorded["terminal"]["signal_delivery"] == "confirmed"
    assert recorded["terminal"]["signal_sent"] is True


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


def test_non_waking_terminal_join_authorizes_exact_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    join = tmp_path / "join.json"
    authorization = tmp_path / "authorization.json"
    closure = tmp_path / "closure.json"
    holder_value = {
        "holder": {"pid": 101},
        "terminal": {
            "pid": 202,
            "argv": ["/usr/bin/kitty", "--title", "canary"],
            "required_comm": "kitty",
            "window_id": "7",
            "dedicated": True,
        },
    }
    holder_bytes = json.dumps(holder_value, sort_keys=True).encode("utf-8")
    holder.write_bytes(holder_bytes)
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    handoff.write_text(
        json.dumps(
            {
                "responsibility_state": "returned",
                "terminal_status": "completed",
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": holder_digest,
                        "closure_receipt": str(closure.resolve()),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                        "terminal_action": {
                            "action": "close_exact_bound_holder",
                            "required": True,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (holder_value, holder_bytes, holder_digest),
    )
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )

    assert MODULE.command_join(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            join_receipt=str(join),
            authorization=str(authorization),
            closure_receipt=str(closure),
        )
    ) == 0
    join_bytes = join.read_bytes()
    authorization.unlink()
    assert MODULE.command_join(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            join_receipt=str(join),
            authorization=str(authorization),
            closure_receipt=str(closure),
        )
    ) == 0
    assert join.read_bytes() == join_bytes
    join_value = json.loads(join.read_text(encoding="utf-8"))
    authorization_value = json.loads(authorization.read_text(encoding="utf-8"))
    assert join_value["return"] == {
        "status": "returned",
        "validated": True,
        "owner_acceptance": "separate",
    }
    assert authorization_value["authorization_kind"] == "join_completed"
    MODULE._validate_closure_authorization(
        authorization_path=authorization,
        handoff_path=handoff,
        holder_receipt_path=holder,
        closure_receipt_path=closure,
        holder_receipt=holder_value,
        holder_receipt_bytes=holder_bytes,
        holder_receipt_digest=holder_digest,
    )

    states = iter(["gone", "gone"])
    monkeypatch.setattr(
        MODULE, "_proc_identity_state", lambda _pid, _start: next(states)
    )
    assert MODULE.command_close(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            closure_authorization=str(authorization),
            closure_receipt=str(closure),
        )
    ) == 0
    closure_value = json.loads(closure.read_text(encoding="utf-8"))
    assert closure_value["closed"] is True
    assert closure_value["outcome"] == "already_gone"
    assert closure_value["authorization_kind"] == "join_completed"
    assert closure_value["join_receipt_ref"] == str(join.resolve())
    assert closure_value["trigger"] == "join_after_validated_terminal_return"
    reservation_value = json.loads(
        MODULE._closure_reservation_path(closure).read_text(encoding="utf-8")
    )
    assert reservation_value["authorization_ref"] == str(authorization.resolve())
    assert reservation_value["join_receipt_ref"] == str(join.resolve())


def test_non_waking_join_requires_return_and_exact_terminal_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    join = tmp_path / "join.json"
    authorization = tmp_path / "authorization.json"
    closure = tmp_path / "closure.json"
    holder_value = {"holder": {"pid": 101}, "terminal": {"pid": 202}}
    holder_bytes = json.dumps(holder_value).encode("utf-8")
    holder.write_bytes(holder_bytes)
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    handoff.write_text(
        json.dumps(
            {
                "responsibility_state": "returned",
                "terminal_status": "completed",
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": holder_digest,
                        "closure_receipt": str(closure.resolve()),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (holder_value, holder_bytes, holder_digest),
    )
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )
    with pytest.raises(MODULE.IncarnationHomeError, match="exact bound-holder"):
        MODULE.command_join(
            MODULE.argparse.Namespace(
                handoff=str(handoff),
                holder_receipt=str(holder),
                join_receipt=str(join),
                authorization=str(authorization),
                closure_receipt=str(closure),
            )
        )


def test_non_waking_join_rejects_authorization_for_different_join_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    join = tmp_path / "join.json"
    other_join = tmp_path / "other-join.json"
    authorization = tmp_path / "authorization.json"
    closure = tmp_path / "closure.json"
    holder_value = {"holder": {"pid": 101}, "terminal": {"pid": 202}}
    holder_bytes = json.dumps(holder_value, sort_keys=True).encode("utf-8")
    holder.write_bytes(holder_bytes)
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    handoff.write_text(
        json.dumps(
            {
                "responsibility_state": "returned",
                "terminal_status": "completed",
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": holder_digest,
                        "closure_receipt": str(closure.resolve()),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                        "terminal_action": {
                            "action": "close_exact_bound_holder",
                            "required": True,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (holder_value, holder_bytes, holder_digest),
    )
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )

    MODULE.command_join(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            join_receipt=str(join),
            authorization=str(authorization),
            closure_receipt=str(closure),
        )
    )
    other_join_value = json.loads(join.read_text(encoding="utf-8"))
    other_join_value["join_ref"] = str(other_join.resolve())
    MODULE._write_new_json(
        other_join, other_join_value, "terminal join receipt"
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="exact join receipt"):
        MODULE.command_join(
            MODULE.argparse.Namespace(
                handoff=str(handoff),
                holder_receipt=str(holder),
                join_receipt=str(other_join),
                authorization=str(authorization),
                closure_receipt=str(closure),
            )
        )


def test_closure_authorization_rejects_join_evidence_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder = tmp_path / "holder.json"
    handoff = tmp_path / "handoff.json"
    join = tmp_path / "join.json"
    authorization = tmp_path / "authorization.json"
    closure = tmp_path / "closure.json"
    holder_value = {"holder": {"pid": 101}, "terminal": {"pid": 202}}
    holder_bytes = json.dumps(holder_value, sort_keys=True).encode("utf-8")
    holder.write_bytes(holder_bytes)
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    handoff.write_text(
        json.dumps(
            {
                "responsibility_state": "returned",
                "terminal_status": "completed",
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": holder_digest,
                        "closure_receipt": str(closure.resolve()),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                        "terminal_action": {
                            "action": "close_exact_bound_holder",
                            "required": True,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (holder_value, holder_bytes, holder_digest),
    )
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )
    MODULE.command_join(
        MODULE.argparse.Namespace(
            handoff=str(handoff),
            holder_receipt=str(holder),
            join_receipt=str(join),
            authorization=str(authorization),
            closure_receipt=str(closure),
        )
    )
    authorization_value = json.loads(authorization.read_text(encoding="utf-8"))
    authorization_value["evidence_sha256"] = "sha256:" + "0" * 64
    authorization.write_text(json.dumps(authorization_value), encoding="utf-8")
    with pytest.raises(MODULE.IncarnationHomeError, match="evidence digest mismatch"):
        MODULE._validate_closure_authorization(
            authorization_path=authorization,
            handoff_path=handoff,
            holder_receipt_path=holder,
            closure_receipt_path=closure,
            holder_receipt=holder_value,
            holder_receipt_bytes=holder_bytes,
            holder_receipt_digest=holder_digest,
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
    node.write_bytes(b"node interpreter")
    node.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable,
        [str(executable), "exec", "--help"],
        path=str(node.parent),
    ) == ["node", str(executable), "exec", "--help"]


def test_post_exec_resolution_recurses_through_nested_shebangs(
    tmp_path: Path,
) -> None:
    final_interpreter = tmp_path / "bin" / "python3"
    final_interpreter.parent.mkdir()
    final_bytes = b"final interpreter\n"
    final_interpreter.write_bytes(final_bytes)
    final_interpreter.chmod(0o700)
    nested_interpreter = tmp_path / "nested-interpreter"
    nested_interpreter.write_text(f"#!{final_interpreter}\n", encoding="utf-8")
    nested_interpreter.chmod(0o700)
    executable = tmp_path / "codex"
    executable.write_text(f"#!{nested_interpreter}\n", encoding="utf-8")
    executable.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable, [str(executable), "exec", "--help"]
    ) == [
        str(final_interpreter),
        str(nested_interpreter),
        str(executable),
        "exec",
        "--help",
    ]
    assert MODULE._post_exec_executable_digest(executable) == MODULE.sha256_bytes(
        final_bytes
    )


def test_post_exec_resolution_recurses_through_nested_env_shebang(
    tmp_path: Path,
) -> None:
    final_interpreter = tmp_path / "python3"
    final_bytes = b"final env interpreter\n"
    final_interpreter.write_bytes(final_bytes)
    final_interpreter.chmod(0o700)
    node = tmp_path / "bin" / "node"
    node.parent.mkdir()
    node.write_text(f"#!{final_interpreter}\n", encoding="utf-8")
    node.chmod(0o700)
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    executable.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable,
        [str(executable), "exec"],
        path=str(node.parent),
    ) == [str(final_interpreter), str(node), str(executable), "exec"]
    assert MODULE._post_exec_executable_digest(
        executable, path=str(node.parent)
    ) == MODULE.sha256_bytes(final_bytes)


def test_post_exec_resolution_preserves_path_spelling_for_env_symlink_shebang(
    tmp_path: Path,
) -> None:
    final_interpreter = tmp_path / "final-interpreter"
    final_interpreter.write_bytes(b"final env symlink interpreter\n")
    final_interpreter.chmod(0o700)
    node_wrapper = tmp_path / "lib" / "node-wrapper"
    node_wrapper.parent.mkdir()
    node_wrapper.write_text(f"#!{final_interpreter}\n", encoding="utf-8")
    node_wrapper.chmod(0o700)
    node = tmp_path / "bin" / "node"
    node.parent.mkdir()
    node.symlink_to(node_wrapper)
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    executable.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable,
        [str(executable), "exec"],
        path=str(node.parent),
    ) == [
        str(final_interpreter),
        str(node),
        str(executable),
        "exec",
    ]


def test_post_exec_resolution_preserves_paths_across_consecutive_env_shebangs(
    tmp_path: Path,
) -> None:
    final_interpreter = tmp_path / "final-interpreter"
    final_bytes = b"final consecutive-env interpreter\n"
    final_interpreter.write_bytes(final_bytes)
    final_interpreter.chmod(0o700)
    python = tmp_path / "bin" / "python"
    python.parent.mkdir()
    python.write_text(f"#!{final_interpreter}\n", encoding="utf-8")
    python.chmod(0o700)
    node = tmp_path / "bin" / "node"
    node.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    node.chmod(0o700)
    executable = tmp_path / "codex"
    executable.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    executable.chmod(0o700)

    assert MODULE._post_exec_argv(
        executable,
        [str(executable), "exec"],
        path=str(node.parent),
    ) == [
        str(final_interpreter),
        str(python),
        str(node),
        str(executable),
        "exec",
    ]
    assert MODULE._post_exec_executable_digest(
        executable, path=str(node.parent)
    ) == MODULE.sha256_bytes(final_bytes)


def test_shebang_snapshot_root_rejects_noexec_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    noexec = getattr(MODULE.os, "ST_NOEXEC", 0)
    if not isinstance(noexec, int) or not noexec:
        pytest.skip("host Python does not expose ST_NOEXEC")

    monkeypatch.setattr(
        MODULE.os,
        "statvfs",
        lambda _path: SimpleNamespace(f_flag=noexec),
    )
    with pytest.raises(MODULE.IncarnationHomeError, match="mounted noexec"):
        MODULE._execution_snapshot_root(tmp_path)


@pytest.mark.skipif(
    shutil.which("cc") is None or not Path("/usr/bin/bwrap").is_file(),
    reason="the ELF companion regression needs cc and bubblewrap",
)
def test_elf_companion_survives_the_immutable_execution_binding(
    tmp_path: Path,
) -> None:
    package = tmp_path / "codex-package"
    package.mkdir()
    executable = package / "codex"
    companion = package / MODULE.CODE_MODE_HOST_NAME
    source = tmp_path / "codex.c"
    source.write_text(
        "#include <fcntl.h>\n"
        "#include <limits.h>\n"
        "#include <stdio.h>\n"
        "#include <string.h>\n"
        "#include <unistd.h>\n"
        "int main(int argc, char **argv) {\n"
        "  if (argc > 1 && strcmp(argv[1], \"--version\") == 0) {\n"
        "    puts(\"codex-cli 0.147.0\"); return 0;\n"
        "  }\n"
        "  int null_descriptor = open(\"/dev/null\", O_RDONLY);\n"
        "  if (null_descriptor < 0) {\n"
        "    puts(\"child-device-unavailable\"); return 5;\n"
        "  }\n"
        "  close(null_descriptor);\n"
        "  char path[PATH_MAX];\n"
        "  ssize_t length = readlink(\"/proc/self/exe\", path, sizeof(path) - 1);\n"
        "  if (length < 0 || (size_t)length >= sizeof(path) - 1) return 2;\n"
        "  path[length] = '\\0';\n"
        "  char *slash = strrchr(path, '/');\n"
        "  if (slash == NULL || (size_t)(sizeof(path) - (slash - path)) < "
        "strlen(\"/codex-code-mode-host\") + 1) return 3;\n"
        "  strcpy(slash, \"/codex-code-mode-host\");\n"
        "  int descriptor = open(path, O_RDONLY);\n"
        "  if (descriptor < 0) { puts(\"code-mode-companion-missing\"); return 4; }\n"
        "  close(descriptor); puts(\"code-mode-call-ok\"); return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["/usr/bin/cc", "-O2", "-o", str(executable), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    companion.write_text("sealed-companion\n", encoding="utf-8")
    companion.chmod(0o755)

    anonymous_fd = MODULE._sealed_memfd("anonymous-codex", executable.read_bytes(), mode=0o700)
    try:
        anonymous = subprocess.run(
            [f"/proc/self/fd/{anonymous_fd}", "--code-mode-probe"],
            check=False,
            capture_output=True,
            text=True,
            pass_fds=(anonymous_fd,),
        )
    finally:
        os.close(anonymous_fd)
    assert anonymous.returncode != 0
    assert anonymous.stdout.strip() == "code-mode-companion-missing"

    (
        executable_fd,
        executable_path,
        content,
        executable_digest,
        snapshot_dir,
        snapshot_path,
        snapshot_mount,
    ) = MODULE._open_verified_executable(executable, snapshot_root=tmp_path)
    assert snapshot_dir is None
    assert snapshot_path is None
    assert content == executable.read_bytes()
    assert executable_digest == MODULE.sha256_bytes(content)
    assert snapshot_mount is not None
    assert snapshot_mount["companion"]["path"] == str(companion.resolve())
    assert snapshot_mount["companion"]["digest"] == MODULE.sha256_bytes(
        companion.read_bytes()
    )
    snapshot_fds = tuple(
        descriptor for _, descriptor, _ in snapshot_mount["file_fds"]
    )
    try:
        repaired = subprocess.run(
            [
                *MODULE._snapshot_bwrap_prefix(snapshot_mount),
                "--",
                str(executable_path),
                "--code-mode-probe",
            ],
            check=False,
            capture_output=True,
            text=True,
            pass_fds=snapshot_fds,
        )
    finally:
        MODULE._close_snapshot_mount(snapshot_mount)
        try:
            os.close(executable_fd)
        except OSError:
            pass
    assert repaired.returncode == 0, repaired.stderr
    assert repaired.stdout.strip() == "code-mode-call-ok"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_shebang_node_launcher_reopens_named_snapshot(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    executable = package / "bin" / "codex"
    executable.parent.mkdir()
    (package / "package.json").write_text("{}\n", encoding="utf-8")
    (package / "package-relative.txt").write_text(
        "package-relative\n", encoding="utf-8"
    )
    original = (
        "#!/usr/bin/env node\n"
        "process.stdout.write(String(process.pid) + '\\n');\n"
        "process.stdout.write(require('fs').readFileSync(__dirname + "
        "'/../package-relative.txt', 'utf8'));\n"
        "setTimeout(() => {}, 30000);\n"
    ).encode()
    executable.write_bytes(original)
    executable.chmod(0o700)

    package.chmod(0o555)
    executable.parent.chmod(0o555)
    (
        snapshot_fd,
        snapshot_exec_path,
        content,
        _,
        snapshot_dir,
        snapshot_path,
        snapshot_mount,
    ) = MODULE._open_verified_executable(executable, snapshot_root=tmp_path)
    package.chmod(0o755)
    executable.parent.chmod(0o755)
    snapshot_relative = snapshot_path.relative_to(snapshot_dir)
    moved_snapshot_dir = snapshot_dir.with_name(snapshot_dir.name + "-moved")
    snapshot_dir.rename(moved_snapshot_dir)
    snapshot_dir = moved_snapshot_dir
    snapshot_path = snapshot_dir / snapshot_relative
    snapshot_resource = snapshot_path.parent.parent / "package-relative.txt"
    assert snapshot_resource.is_file()
    assert not snapshot_resource.is_symlink()
    assert snapshot_resource.read_text(encoding="utf-8") == "package-relative\n"
    try:
        executable.write_text("#!/bin/sh\necho replaced\n", encoding="utf-8")
        (package / "package-relative.txt").write_text(
            "replaced-resource\n", encoding="utf-8"
        )
        snapshot_prefix = MODULE._snapshot_bwrap_prefix(snapshot_mount)
        snapshot_component_fds = tuple(
            descriptor
            for _, descriptor, _ in snapshot_mount["file_fds"]
        )
        process = subprocess.Popen(
            [*snapshot_prefix, "--", str(snapshot_exec_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            pass_fds=snapshot_component_fds,
        )
        process_pid = int(process.stdout.readline().strip())
        resource_line = process.stdout.readline()
        observed_argv = [
            os.fsdecode(item)
            for item in Path(f"/proc/{process_pid}/cmdline").read_bytes().split(b"\0")
            if item
        ]
    finally:
        if "process" in locals() and process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        if "process" in locals():
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
        MODULE._close_snapshot_mount(snapshot_mount)
        MODULE._remove_named_snapshot(
            snapshot_path,
            snapshot_dir=snapshot_dir,
            snapshot_dir_fd=snapshot_fd,
        )
        os.close(snapshot_fd)
        assert not snapshot_dir.exists()

    assert content == original
    assert observed_argv[:2] == ["node", str(snapshot_exec_path)]
    assert resource_line == "package-relative\n"


def test_package_snapshot_does_not_mirror_ancestor_siblings(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    executable = package / "bin" / "codex"
    executable.parent.mkdir(parents=True)
    (package / "package.json").write_text("{}\n", encoding="utf-8")
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    unrelated = tmp_path / "unrelated-snapshot"
    unrelated.mkdir()
    (unrelated / "marker").write_text("must not be retained\n", encoding="utf-8")
    snapshot_root = tmp_path / "snapshot-root"
    snapshot_root.mkdir()

    snapshot_exec, snapshot_dir, _records, _target_dir = MODULE._mirror_package_layout(
        executable=executable,
        snapshot_root=snapshot_root,
    )
    try:
        assert snapshot_exec.parent.is_dir()
        assert (_target_dir / "package.json").is_file()
        assert not any(item.is_symlink() for item in snapshot_dir.rglob("*"))
        assert not any(
            item.name == unrelated.name for item in snapshot_dir.rglob("*")
        )
    finally:
        MODULE._remove_named_snapshot(
            snapshot_exec,
            snapshot_dir=snapshot_dir,
        )


def test_shebang_snapshot_preserves_effective_companion_execute_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    package.mkdir()
    executable = package / "vendor" / "codex" / "codex"
    executable.parent.mkdir(parents=True)
    (package / "package.json").write_text("{}\n", encoding="utf-8")
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o700)
    companion = executable.parent / MODULE.CODE_MODE_HOST_NAME
    companion.write_bytes(b"group-executable-companion")
    companion.chmod(0o450)
    original_access = MODULE.os.access

    def allow_companion_execute(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        mode: int,
        *args: object,
        **kwargs: object,
    ) -> bool:
        if Path(path) == companion and mode == MODULE.os.X_OK:
            return True
        return original_access(path, mode, *args, **kwargs)

    monkeypatch.setattr(MODULE.os, "access", allow_companion_execute)
    (
        snapshot_fd,
        _snapshot_exec_path,
        _content,
        _digest,
        _snapshot_dir,
        _snapshot_path,
        snapshot_mount,
    ) = MODULE._open_verified_executable(executable, snapshot_root=tmp_path)
    try:
        companion_relative = Path("vendor/codex") / MODULE.CODE_MODE_HOST_NAME
        modes = {
            relative: mode
            for relative, _descriptor, mode in snapshot_mount["file_fds"]
        }
        assert modes[companion_relative] == 0o500
    finally:
        MODULE._close_snapshot_mount(snapshot_mount)
        os.close(snapshot_fd)


def test_named_snapshot_cleanup_waits_for_exact_holder_exit(tmp_path: Path) -> None:
    snapshot_path = tmp_path / ".codex.aoa-snapshot-test"
    snapshot_path.write_bytes(b"snapshot")
    snapshot_path.chmod(0o500)
    snapshot_fd = os.open(snapshot_path, os.O_RDONLY)
    holder_pid = os.fork()
    if holder_pid == 0:
        MODULE.time.sleep(0.2)
        os._exit(0)

    cleanup_pid = MODULE._spawn_named_snapshot_cleanup(
        snapshot_path=snapshot_path,
        holder_pid=holder_pid,
        holder_start_ticks=MODULE._proc_start_ticks(holder_pid),
        snapshot_fd=snapshot_fd,
    )
    os.close(snapshot_fd)
    _, holder_status = os.waitpid(holder_pid, 0)
    _, cleanup_status = os.waitpid(cleanup_pid, 0)

    assert os.waitstatus_to_exitcode(holder_status) == 0
    assert os.waitstatus_to_exitcode(cleanup_status) == 0
    assert not snapshot_path.exists()


def test_named_snapshot_cleanup_refuses_replacement_directory(
    tmp_path: Path,
) -> None:
    original_dir = tmp_path / "abyss-stack-codex-package-original"
    original_dir.mkdir()
    original_path = original_dir / "codex"
    original_path.write_bytes(b"original")
    original_path.chmod(0o500)
    snapshot_fd = os.open(
        original_dir,
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
    )
    moved_dir = tmp_path / "abyss-stack-codex-package-moved"
    replacement_dir = original_dir
    try:
        original_dir.rename(moved_dir)
        replacement_dir.mkdir()
        replacement_path = replacement_dir / "codex"
        replacement_path.write_bytes(b"replacement")
        replacement_path.chmod(0o500)

        MODULE._remove_named_snapshot(
            replacement_path,
            snapshot_dir=replacement_dir,
            snapshot_dir_fd=snapshot_fd,
        )
        assert replacement_dir.exists()
        assert replacement_path.exists()

        MODULE._remove_named_snapshot(
            moved_dir / "codex",
            snapshot_dir=moved_dir,
            snapshot_dir_fd=snapshot_fd,
        )
        assert not moved_dir.exists()
        assert replacement_dir.exists()
    finally:
        os.close(snapshot_fd)


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


def test_legacy_holder_identity_rejects_process_argv_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder_argv = ["/usr/bin/codex", "exec"]
    kitty_argv = ["/usr/bin/kitty", "--detach", "--title", "holder"]
    monkeypatch.setattr(
        MODULE,
        "_proc_start_ticks",
        lambda pid: {101: 11, 102: 12, 103: 13}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_parent_pid",
        lambda pid: {101: 102, 102: 103, 103: 1}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_comm",
        lambda pid: {102: "bwrap", 103: "kitty"}[pid],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: {
            101: holder_argv,
            103: ["/usr/bin/kitty", "--detach", "--title", "replacement"],
        }[pid],
    )

    with pytest.raises(MODULE.IncarnationHomeError, match="Kitty argv identity"):
        MODULE._validate_legacy_holder_process_identity(
            holder_pid=101,
            holder_start_ticks=11,
            holder_parent_pid=102,
            holder_parent_start_ticks=12,
            holder_parent_comm="bwrap",
            holder_argv=holder_argv,
            kitty_pid=103,
            kitty_start_ticks=13,
            kitty_argv=kitty_argv,
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


def test_rejected_launch_escalates_and_confirms_exact_holder_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        MODULE,
        "_holder_receipt_process_ids",
        lambda _receipt: (101, 11, 202, 12),
    )
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    calls: list[str] = []
    monkeypatch.setattr(
        MODULE,
        "_send_verified_term",
        lambda _pid, _ticks: calls.append("term") or True,
    )
    wait_states = iter(["live", "gone"])
    monkeypatch.setattr(
        MODULE,
        "_wait_for_exact_process_exit",
        lambda _pid, _ticks: calls.append("wait") or next(wait_states),
    )
    monkeypatch.setattr(
        MODULE,
        "_send_verified_kill",
        lambda _pid, _ticks: calls.append("kill") or True,
    )

    assert MODULE._terminate_rejected_visible_launch({}) is True
    assert calls == ["term", "wait", "kill", "wait"]


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
    for missing_terminal_field in ("window_id", "dedicated"):
        invalid_payload = {
            **holder_payload,
            "terminal": {
                **holder_payload["terminal"],
            },
        }
        invalid_payload["terminal"].pop(missing_terminal_field)
        holder.write_text(json.dumps(invalid_payload), encoding="utf-8")
        with pytest.raises(
            MODULE.IncarnationHomeError, match="holder terminal receipt is incomplete"
        ):
            MODULE._load_holder_receipt_snapshot(holder)
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
    states = iter(["live", "gone", "gone", "gone"])
    monkeypatch.setattr(
        MODULE,
        "_proc_identity_state",
        lambda _pid, _start: next(states, "gone"),
    )
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

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


def test_legacy_closure_reservation_replays_only_on_legacy_wake_route(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")
    reservation_path = MODULE._closure_reservation_path(closure)
    MODULE._write_new_json(
        reservation_path,
        {
            "schema_version": MODULE.LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION,
            "closure_receipt_ref": str(closure.resolve()),
            "handoff_ref": str(handoff.resolve()),
            "holder_receipt_ref": str(holder.resolve()),
            "wake_receipt_ref": str(wake.resolve()),
            "holder_pid": 101,
            "terminal_pid": 202,
        },
        "terminal closure reservation",
    )

    reservation_fd, retry_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        allow_legacy_wake_reservation=True,
        holder_pid=101,
        terminal_pid=202,
    )
    try:
        assert retry_path == reservation_path
        assert completed is None
    finally:
        MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
        os.close(reservation_fd)

    with pytest.raises(MODULE.IncarnationHomeError, match="identity mismatch"):
        MODULE._reserve_closure_receipt(
            closure_receipt_path=closure,
            handoff_path=handoff,
            holder_receipt_path=holder,
            wake_receipt_path=wake,
            authorization_path=tmp_path / "authorization.json",
            authorization_kind="join_completed",
            evidence_path=tmp_path / "join.json",
            allow_legacy_wake_reservation=True,
            holder_pid=101,
            terminal_pid=202,
        )


def test_completed_legacy_v1_closure_replays_with_legacy_wake_reservation(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")
    reservation_path = MODULE._closure_reservation_path(closure)
    MODULE._write_new_json(
        reservation_path,
        {
            "schema_version": MODULE.LEGACY_CLOSURE_RESERVATION_SCHEMA_VERSION,
            "closure_receipt_ref": str(closure.resolve()),
            "handoff_ref": str(handoff.resolve()),
            "holder_receipt_ref": str(holder.resolve()),
            "wake_receipt_ref": str(wake.resolve()),
            "holder_pid": 101,
            "terminal_pid": 202,
        },
        "terminal closure reservation",
    )
    MODULE._write_new_json(
        closure,
        {
            "schema_version": MODULE.LEGACY_TERMINAL_CLOSURE_SCHEMA_VERSION,
            "handoff_ref": str(handoff.resolve()),
            "holder_receipt_ref": str(holder.resolve()),
            "wake_receipt_ref": str(wake.resolve()),
            "reservation_ref": str(reservation_path.resolve()),
            "verified_at": "2026-08-20T00:00:00Z",
            "holder": {"pid": 101, "start_ticks": 11, "gone": True},
            "terminal": {
                "pid": 202,
                "start_ticks": 12,
                "comm": "kitty",
                "argv": ["/usr/bin/kitty"],
                "signal": "TERM",
                "signal_target": "holder_process",
                "signal_attempted": False,
                "signal_delivery": "not_attempted",
                "signal_sent": False,
                "gone": True,
            },
            "closed": True,
            "outcome": "already_gone",
            "identity_state": "already_gone",
            "route": "abyss_stack_visible_incarnation_runtime",
            "trigger": "wake_bridge_after_confirmed_handoff_delivery",
        },
        "terminal closure receipt",
    )

    reservation_fd, retry_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=wake,
        allow_legacy_wake_reservation=True,
        holder_pid=101,
        terminal_pid=202,
    )
    try:
        assert retry_path == reservation_path
        assert completed is not None
        assert completed["schema_version"] == MODULE.LEGACY_TERMINAL_CLOSURE_SCHEMA_VERSION
    finally:
        MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
        os.close(reservation_fd)


def test_v2_closure_reservation_rejects_authorization_or_evidence_byte_drift(
    tmp_path: Path,
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    authorization = tmp_path / "authorization.json"
    evidence = tmp_path / "join.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, authorization, evidence):
        path.write_text("{}", encoding="utf-8")

    reservation_fd, reservation_path, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=closure,
        handoff_path=handoff,
        holder_receipt_path=holder,
        wake_receipt_path=evidence,
        authorization_path=authorization,
        authorization_kind="join_completed",
        evidence_path=evidence,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    try:
        reservation = MODULE._load_json(
            reservation_path, "terminal closure reservation"
        )
        assert reservation["authorization_sha256"] == MODULE.sha256_bytes(
            authorization.read_bytes()
        )
        assert reservation["evidence_sha256"] == MODULE.sha256_bytes(evidence.read_bytes())
    finally:
        MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
        os.close(reservation_fd)

    authorization.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(MODULE.IncarnationHomeError, match="identity mismatch"):
        MODULE._reserve_closure_receipt(
            closure_receipt_path=closure,
            handoff_path=handoff,
            holder_receipt_path=holder,
            wake_receipt_path=evidence,
            authorization_path=authorization,
            authorization_kind="join_completed",
            evidence_path=evidence,
            holder_pid=101,
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
                "schema_version": MODULE.TERMINAL_CLOSURE_SCHEMA_VERSION,
                "handoff_ref": str(handoff.resolve()),
                "holder_receipt_ref": str(holder.resolve()),
                "authorization_ref": str(wake.resolve()),
                "authorization_kind": "wake_delivered",
                "authorization_evidence_ref": str(wake.resolve()),
                "reservation_ref": str(reservation_path.resolve()),
                "wake_receipt_ref": str(wake.resolve()),
                "route": "abyss_stack_visible_incarnation_runtime",
                "trigger": "wake_bridge_after_confirmed_handoff_delivery",
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
                "schema_version": MODULE.TERMINAL_CLOSURE_SCHEMA_VERSION,
                "handoff_ref": str(handoff.resolve()),
                "holder_receipt_ref": str(holder.resolve()),
                "authorization_ref": str(wake.resolve()),
                "authorization_kind": "wake_delivered",
                "authorization_evidence_ref": str(wake.resolve()),
                "reservation_ref": str(reservation_path.resolve()),
                "wake_receipt_ref": str(wake.resolve()),
                "route": "abyss_stack_visible_incarnation_runtime",
                "trigger": "wake_bridge_after_confirmed_handoff_delivery",
                "holder": {"pid": 101},
                "terminal": {"pid": 202},
                "closed": False,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (
            {
                "holder": {"pid": 101},
                "terminal": {
                    "pid": 202,
                    "argv": ["/usr/bin/kitty"],
                    "required_comm": "kitty",
                },
            },
            b"{}",
            MODULE.sha256_bytes(b"{}"),
        ),
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


def test_new_closure_target_retries_after_preserved_unclosed_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_handoff = tmp_path / "old-handoff.json"
    retry_handoff = tmp_path / "retry-handoff.json"
    holder = tmp_path / "holder.json"
    old_wake = tmp_path / "old-wake.json"
    retry_wake = tmp_path / "retry-wake.json"
    old_closure = tmp_path / "old-closure.json"
    retry_closure = tmp_path / "retry-closure.json"
    for path in (old_handoff, holder, old_wake):
        path.write_text("{}", encoding="utf-8")

    reservation_fd, old_reservation, completed = MODULE._reserve_closure_receipt(
        closure_receipt_path=old_closure,
        handoff_path=old_handoff,
        holder_receipt_path=holder,
        wake_receipt_path=old_wake,
        holder_pid=101,
        terminal_pid=202,
    )
    assert completed is None
    MODULE.fcntl.flock(reservation_fd, MODULE.fcntl.LOCK_UN)
    os.close(reservation_fd)
    failed = {
        "schema_version": MODULE.TERMINAL_CLOSURE_SCHEMA_VERSION,
        "handoff_ref": str(old_handoff.resolve()),
        "holder_receipt_ref": str(holder.resolve()),
        "authorization_ref": str(old_wake.resolve()),
        "authorization_kind": "wake_delivered",
        "authorization_evidence_ref": str(old_wake.resolve()),
        "reservation_ref": str(old_reservation.resolve()),
        "wake_receipt_ref": str(old_wake.resolve()),
        "route": "abyss_stack_visible_incarnation_runtime",
        "trigger": "wake_bridge_after_confirmed_handoff_delivery",
        "holder": {"pid": 101},
        "terminal": {"pid": 202},
        "closed": False,
    }
    old_closure.write_bytes(MODULE.canonical_bytes(failed) + b"\n")
    preserved_bytes = old_closure.read_bytes()

    retry_handoff.write_bytes(
        MODULE.canonical_bytes(
            {
                "responsibility_state": "returned",
                "terminal_status": "completed",
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder.resolve()),
                        "terminal_receipt_sha256": MODULE.sha256_bytes(
                            holder.read_bytes()
                        ),
                        "closure_receipt": str(retry_closure.resolve()),
                        "holder_pid": 101,
                        "terminal_pid": 202,
                        "terminal_action": {
                            "action": "close_exact_bound_holder",
                            "required": True,
                        },
                    }
                },
            }
        )
        + b"\n"
    )
    retry_wake.write_bytes(
        MODULE.canonical_bytes(
            {
                "schema_version": "task_local_actor_wake_receipt_v1",
                "handoff_ref": str(retry_handoff.resolve()),
                "handoff_sha256": MODULE.sha256_bytes(retry_handoff.read_bytes()),
                "actions": {"handoff_message_sent": True},
                "observed": {"handoff_delivery": True},
            }
        )
        + b"\n"
    )

    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (
            {
                "holder": {"pid": 101},
                "terminal": {
                    "pid": 202,
                    "argv": ["/usr/bin/kitty", "--detach"],
                    "required_comm": "kitty",
                    "window_id": "7",
                    "dedicated": True,
                },
            },
            b"{}",
            MODULE.sha256_bytes(b"{}"),
        ),
    )
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_terminal_identity",
        lambda _receipt: (101, 202, "kitty", "7", True),
    )
    states = iter(["live", "live", "gone", "gone"])
    monkeypatch.setattr(
        MODULE, "_proc_identity_state", lambda _pid, _start: next(states)
    )
    monkeypatch.setattr(MODULE, "_send_verified_term", lambda *_args: True)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    assert MODULE.command_close(
        MODULE.argparse.Namespace(
            handoff=str(retry_handoff),
            holder_receipt=str(holder),
            wake_receipt=str(retry_wake),
            closure_receipt=str(retry_closure),
        )
    ) == 0
    recorded = json.loads(retry_closure.read_text(encoding="utf-8"))
    assert recorded["closed"] is True
    assert recorded["reservation_ref"] == str(
        MODULE._closure_reservation_path(retry_closure).resolve()
    )
    assert old_closure.read_bytes() == preserved_bytes


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


def test_undelivered_term_waits_for_natural_pair_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (
            {
                "holder": {"pid": 101, "start_ticks": 11},
                "terminal": {
                    "pid": 202,
                    "start_ticks": 12,
                    "argv": ["/usr/bin/kitty"],
                    "required_comm": "kitty",
                    "window_id": "7",
                    "dedicated": True,
                },
            },
            b"{}",
            MODULE.sha256_bytes(b"{}"),
        ),
    )
    monkeypatch.setattr(MODULE, "_validate_wake_delivery", lambda **_kwargs: None)
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_terminal_identity",
        lambda _receipt: (101, 202, "kitty", "7", True),
    )
    monkeypatch.setattr(MODULE, "_send_verified_term", lambda *_args: False)
    states = iter(
        [
            "live", "live",  # initial exact identity check
            "live", "gone",  # holder exits before pidfd TERM delivery
            "gone", "gone",  # Kitty follows during bounded natural wait
        ]
    )
    seen: list[str] = []

    def state(_pid: int, _start: int) -> str:
        value = next(states, "gone")
        seen.append(value)
        return value

    monkeypatch.setattr(
        MODULE, "_proc_identity_state", state
    )
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

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
    assert recorded["terminal"]["signal_delivery"] == "not_delivered"
    assert recorded["terminal"]["signal_sent"] is False
    assert seen == ["live", "live", "live", "gone", "gone", "gone"]


def test_signal_failure_waits_for_natural_pair_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handoff = tmp_path / "handoff.json"
    holder = tmp_path / "holder.json"
    wake = tmp_path / "wake.json"
    closure = tmp_path / "closure.json"
    for path in (handoff, holder, wake):
        path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        MODULE,
        "_load_holder_receipt_snapshot",
        lambda _path: (
            {
                "holder": {"pid": 101, "start_ticks": 11},
                "terminal": {
                    "pid": 202,
                    "start_ticks": 12,
                    "argv": ["/usr/bin/kitty"],
                    "required_comm": "kitty",
                    "window_id": "7",
                    "dedicated": True,
                },
            },
            b"{}",
            MODULE.sha256_bytes(b"{}"),
        ),
    )
    monkeypatch.setattr(MODULE, "_validate_wake_delivery", lambda **_kwargs: None)
    monkeypatch.setattr(
        MODULE, "_holder_receipt_process_ids", lambda _receipt: (101, 11, 202, 12)
    )
    monkeypatch.setattr(
        MODULE,
        "_holder_terminal_identity",
        lambda _receipt: (101, 202, "kitty", "7", True),
    )

    def fail_signal(*_args: object) -> bool:
        raise MODULE.IncarnationHomeError("signal race")

    monkeypatch.setattr(MODULE, "_send_verified_term", fail_signal)
    states = iter(
        [
            "live", "live",  # initial exact identity check
            "live", "gone",  # holder exits during signaling
            "gone", "gone",  # Kitty follows during bounded natural wait
        ]
    )
    seen: list[str] = []

    def state(_pid: int, _start: int) -> str:
        value = next(states, "gone")
        seen.append(value)
        return value

    monkeypatch.setattr(MODULE, "_proc_identity_state", state)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

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
    assert recorded["terminal"]["signal_delivery"] == "failed"
    assert recorded["terminal"]["signal_sent"] is False
    assert seen == ["live", "live", "live", "gone", "gone", "gone"]


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


def test_wake_delivery_hashes_the_parsed_holder_snapshot(
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
    holder_bytes = json.dumps(holder_payload).encode("utf-8")
    holder.write_bytes(holder_bytes)
    holder_digest = MODULE.sha256_bytes(holder_bytes)
    handoff.write_text(
        json.dumps(
            {
                "runtime": {
                    "responsibility_holder": {
                        "terminal_receipt": str(holder),
                        "terminal_receipt_sha256": holder_digest,
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
    holder.write_text(json.dumps({"replacement": True}), encoding="utf-8")

    MODULE._validate_wake_delivery(
        wake_receipt_path=wake,
        handoff_path=handoff,
        holder_receipt_path=holder,
        closure_receipt_path=closure,
        holder_receipt=holder_payload,
        holder_receipt_bytes=holder_bytes,
        holder_receipt_digest=holder_digest,
    )


def test_terminal_binding_creation_records_exact_owner_and_terminal_identity(
    tmp_path: Path,
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    try:
        assert binding["schema_version"] == MODULE.TERMINAL_BINDING_SCHEMA_VERSION
        assert binding["goal_ref"] == "goal:test-terminal-observability"
        assert binding["session_ref"] == "session:test-terminal-observability"
        assert holder == {
            "pid": 101,
            "start_ticks": 1001,
            "argv_digest": MODULE.sha256_bytes(
                MODULE.canonical_bytes(["/usr/bin/codex", "exec"])
            ),
            "exe_digest": "sha256:" + "1" * 64,
        }
        assert terminal["pid"] == 202
        assert terminal["start_ticks"] == 2002
        assert terminal["window_id"] == "7"
        assert terminal["tty"] == "/dev/pts/7"
        assert terminal["control_socket"]["mode"] == 0o600
        assert "env" not in json.dumps(binding).casefold()
        assert "credential" not in json.dumps(binding).casefold()
    finally:
        listener.close()


def test_receipt_binding_must_match_top_level_holder_and_terminal() -> None:
    boot_id = MODULE._proc_boot_id()
    binding = {
        "boot_id": boot_id,
        "holder": {"pid": 101, "start_ticks": 1001},
        "terminal": {
            "pid": 202,
            "start_ticks": 2002,
            "window_id": "7",
            "tty": "/dev/pts/7",
            "title": "visible-holder",
            "control_socket": {
                "address": "unix:/tmp/kitty.sock",
                "path": "/tmp/kitty.sock",
                "mode": 0o600,
                "device": 1,
                "inode": 2,
            },
        },
    }
    receipt = {
        "boot_id": boot_id,
        "holder": {"pid": 101, "start_ticks": 1001},
        "terminal": {
            "pid": 202,
            "start_ticks": 2002,
            "window_id": "7",
            "tty": "/dev/pts/7",
            "title": "visible-holder",
            "control_socket": {
                "address": "unix:/tmp/kitty.sock",
                "path": "/tmp/kitty.sock",
                "mode": 0o600,
                "device": 1,
                "inode": 2,
            },
        },
    }
    MODULE._validate_receipt_binding_consistency(receipt, binding)

    binding["holder"]["start_ticks"] = 1002
    with pytest.raises(MODULE.IncarnationHomeError, match="holder identity"):
        MODULE._validate_receipt_binding_consistency(receipt, binding)

    binding["holder"]["start_ticks"] = 1001
    binding["terminal"]["window_id"] = "8"
    with pytest.raises(MODULE.IncarnationHomeError, match="terminal identity"):
        MODULE._validate_receipt_binding_consistency(receipt, binding)

    binding["terminal"]["window_id"] = "7"
    binding["terminal"]["control_socket"]["inode"] = 3
    with pytest.raises(MODULE.IncarnationHomeError, match="socket"):
        MODULE._validate_receipt_binding_consistency(receipt, binding)


def test_terminal_binding_source_receipt_is_typed_before_return(
    tmp_path: Path,
) -> None:
    listener, binding, _holder, _terminal = _terminal_binding_fixture(tmp_path)
    try:
        source_receipt = tmp_path / "holder.json"
        source_receipt.write_text("{}", encoding="utf-8")
        binding["source_receipt"] = {
            "path": str(source_receipt),
            "sha256": "sha256:" + "a" * 64,
        }
        validated = MODULE._validate_terminal_binding_shape(binding)
        assert validated["source_receipt"] == binding["source_receipt"]

        binding["source_receipt"] = {
            "path": {"notes": "private payload"},
            "sha256": [],
        }
        with pytest.raises(MODULE.IncarnationHomeError, match="source receipt"):
            MODULE._validate_terminal_binding_shape(binding)
    finally:
        listener.close()


def test_terminal_binding_validation_reconstructs_redacted_binding_refs(
    tmp_path: Path,
) -> None:
    listener, binding, _holder, _terminal = _terminal_binding_fixture(tmp_path)
    try:
        binding["goal_ref"] = "database_password=hunter2"
        validated = MODULE._validate_terminal_binding_shape(binding)
        assert validated["goal_ref"] == "database_password=<redacted>"
    finally:
        listener.close()


def test_terminal_binding_validation_reconstructs_redacted_nested_strings(
    tmp_path: Path,
) -> None:
    listener, binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    try:
        terminal["title"] = "password=hunter2"
        validated = MODULE._validate_terminal_binding_shape(binding)
        assert validated["terminal"]["title"] == "password=<redacted>"
    finally:
        listener.close()


def test_terminal_binding_rejects_boolean_process_identity() -> None:
    binding = {
        "schema_version": MODULE.TERMINAL_BINDING_SCHEMA_VERSION,
        "boot_id": MODULE._proc_boot_id(),
        "goal_ref": "goal:test",
        "actor_ref": "actor:test",
        "incarnation_ref": "incarnation:test",
        "session_ref": "session:test",
        "runtime_state_root": "/tmp/runtime",
        "closeout_route": "/tmp/closeout.sh",
        "holder": {"pid": True, "start_ticks": 1001},
        "terminal": {
            "pid": 202,
            "start_ticks": 2002,
            "window_id": "7",
            "tty": "/dev/pts/7",
            "title": "visible-holder",
            "control_socket": {
                "address": "unix:/tmp/kitty.sock",
                "path": "/tmp/kitty.sock",
                "mode": 0o600,
                "device": 1,
                "inode": 1,
            },
        },
        "remote_control": "socket-only",
        "dedicated": True,
    }
    with pytest.raises(MODULE.IncarnationHomeError, match="holder identity"):
        MODULE._validate_terminal_binding_shape(binding)


def test_terminal_binding_rejects_credential_bearing_source_receipt_path(
    tmp_path: Path,
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    unsafe_dir = tmp_path / "database_password=hunter2"
    unsafe_dir.mkdir()
    source_receipt = unsafe_dir / "holder.json"
    source_receipt.write_text("{}", encoding="utf-8")
    try:
        with pytest.raises(MODULE.IncarnationHomeError, match="source receipt path"):
            MODULE._write_terminal_binding(
                output_path=tmp_path / "binding.json",
                binding=binding,
                holder=holder,
                terminal=terminal,
                source_receipt=source_receipt,
                source_digest=MODULE.sha256_bytes(source_receipt.read_bytes()),
            )
    finally:
        listener.close()


def test_terminal_binding_rejects_negative_socket_mode(
    tmp_path: Path,
) -> None:
    listener, binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    try:
        terminal["control_socket"]["mode"] = -64
        with pytest.raises(MODULE.IncarnationHomeError, match="socket mode"):
            MODULE._validate_terminal_binding_shape(binding)
    finally:
        listener.close()


def test_terminal_binding_rejects_invalid_tty(
    tmp_path: Path,
) -> None:
    listener, binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    try:
        terminal["tty"] = "/tmp/fake"
        with pytest.raises(MODULE.IncarnationHomeError, match="tty"):
            MODULE._validate_terminal_binding_shape(binding)
    finally:
        listener.close()


def test_control_socket_allocation_is_unique_and_private(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    first = MODULE._allocate_control_socket()
    second = MODULE._allocate_control_socket()

    assert first != second
    socket_root = tmp_path / MODULE.CONTROL_SOCKET_ROOT_NAME
    assert stat.S_IMODE(socket_root.stat().st_mode) == 0o700
    assert not Path(first.removeprefix("unix:")).exists()
    assert not Path(second.removeprefix("unix:")).exists()


def test_control_socket_permissions_fail_closed_then_harden(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "kitty.sock"
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o755)
    address = f"unix:{socket_path}"
    try:
        with pytest.raises(MODULE.IncarnationHomeError, match="not private"):
            MODULE._secure_control_socket(address, harden=False)
        record = MODULE._secure_control_socket(address, harden=True)
        assert record["mode"] == 0o600
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o600
    finally:
        listener.close()


def test_kitty_projection_omits_environment_and_commandline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, _binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    calls: dict[str, object] = {}
    payload = [
        {
            "id": 3,
            "tabs": [
                {
                    "id": 4,
                    "windows": [
                        {
                            "id": 7,
                            "title": "repair token=super-secret",
                            "cwd": "/workspace",
                            "pid": 202,
                            "cmdline": "codex --password=super-secret",
                            "env": {"TOKEN": "super-secret"},
                            "foreground_processes": [
                                {
                                    "pid": 303,
                                    "cwd": "/workspace",
                                    "cmdline": "worker --credential=secret",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload), stderr="raw payload is discarded"
        )

    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "codex")
    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    try:
        matches = MODULE._kitty_ls(
            kitty_executable="/usr/bin/kitty",
            control_socket=terminal["control_socket"]["address"],
            window_id="7",
        )
        rendered = json.dumps(matches, sort_keys=True)
        assert len(matches) == 1
        assert "env" not in rendered.casefold()
        assert "cmdline" not in rendered.casefold()
        assert "super-secret" not in rendered
        assert "token=<redacted>" in rendered
        argv = calls["argv"]
        assert isinstance(argv, list)
        assert "--all-env-vars=no" in argv
        assert "--output-format" in argv
        assert "env:KITTY_WINDOW_ID=1" not in argv
    finally:
        listener.close()


def test_kitty_projection_rejects_boolean_observation_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, _binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    payload = [
        {
            "id": True,
            "tabs": [
                {
                    "id": True,
                    "windows": [
                        {
                            "id": 7,
                            "title": "Luna Max",
                            "cwd": "/workspace",
                            "pid": True,
                            "foreground_processes": [
                                {"pid": True},
                                {"pid": 303},
                            ],
                        }
                    ],
                }
            ],
        }
    ]

    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "codex")
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload), stderr=""
        ),
    )
    try:
        [projection] = MODULE._kitty_ls(
            kitty_executable="/usr/bin/kitty",
            control_socket=terminal["control_socket"]["address"],
            window_id="7",
        )
        assert projection["pid"] is None
        assert projection["tab"]["id"] is None
        assert projection["os_window"]["id"] is None
        assert projection["foreground_processes"] == [
            {"pid": 303, "comm": "codex"}
        ]
    finally:
        listener.close()


def test_safe_projection_redacts_quoted_and_whitespace_credentials() -> None:
    assert MODULE._safe_projection_string(
        '{"password":"hunter2"}', "json-shaped title"
    ) == '{"password":"<redacted>"}'
    assert MODULE._safe_projection_string(
        "password='hunter 2'", "quoted title"
    ) == "password='<redacted>'"
    assert MODULE._safe_projection_string(
        "token=hunter 2", "whitespace title"
    ) == "token=<redacted>"
    assert MODULE._safe_projection_string(
        r'{"password":"hunter\"suffix"}', "escaped json-shaped title"
    ) == '{"password":"<redacted>"}'
    assert MODULE._safe_projection_string(
        r'{\"password\":\"hunter2\"}', "backslash-escaped json-shaped title"
    ) == r'{\"password\":\"<redacted>\"}'
    assert MODULE._safe_projection_string(
        "access_token=hunter2", "access token title"
    ) == "access_token=<redacted>"
    assert MODULE._safe_projection_string(
        "refresh-token=hunter2", "refresh token title"
    ) == "refresh-token=<redacted>"
    assert MODULE._safe_projection_string(
        "client_secret=hunter2", "client secret title"
    ) == "client_secret=<redacted>"
    assert MODULE._safe_projection_string(
        "auth_token=hunter2", "auth token title"
    ) == "auth_token=<redacted>"
    assert MODULE._safe_projection_string(
        "github_token=hunter2", "github token title"
    ) == "github_token=<redacted>"
    assert MODULE._safe_projection_string(
        "database_password=hunter2", "database password title"
    ) == "database_password=<redacted>"
    assert MODULE._safe_projection_string(
        "AWS_SECRET_ACCESS_KEY=hunter2", "cloud secret title"
    ) == "AWS_SECRET_ACCESS_KEY=<redacted>"
    assert MODULE._safe_projection_string(
        "x-api-key=hunter2", "api key title"
    ) == "x-api-key=<redacted>"


def test_socket_path_rejects_credential_shaped_text() -> None:
    with pytest.raises(MODULE.IncarnationHomeError, match="credential-shaped"):
        MODULE._socket_path(
            "unix:/run/user/1000/password=hunter2/kitty.sock"
        )


def test_kitty_projection_rechecks_recorded_socket_identity(
    tmp_path: Path,
) -> None:
    listener, _binding, _holder, terminal = _terminal_binding_fixture(tmp_path)
    socket_record = terminal["control_socket"]
    try:
        with pytest.raises(MODULE.IncarnationHomeError, match="device identity"):
            MODULE._kitty_ls(
                kitty_executable="/usr/bin/kitty",
                control_socket=socket_record["address"],
                window_id="7",
                expected_device=socket_record["device"] + 1,
                expected_inode=socket_record["inode"],
            )
    finally:
        listener.close()


def test_status_is_read_only_and_writes_only_safe_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    binding_path = tmp_path / "binding.json"
    status_path = tmp_path / "status.json"
    MODULE._write_new_json(
        binding_path,
        {
            "schema_version": MODULE.TERMINAL_BINDING_SCHEMA_VERSION,
            "created_at": MODULE._utc_now(),
            "binding": binding,
            "holder": holder,
            "terminal": terminal,
        },
        "test binding",
    )
    before_mode = stat.S_IMODE(
        Path(terminal["control_socket"]["path"]).stat().st_mode
    )
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: "sha256:" + "1" * 64)
    monkeypatch.setattr(MODULE, "_kitty_dedication", lambda **_kwargs: ("7", True))
    monkeypatch.setattr(
        MODULE,
        "_kitty_ls",
        lambda **_kwargs: [
            {
                "id": "7",
                "title": "Luna Max",
                "cwd": "/workspace",
                "pid": 202,
                "is_active": True,
                "is_focused": False,
                "needs_attention": False,
                "in_alternate_screen": False,
                "foreground_processes": [{"pid": 303, "comm": "codex"}],
                "tab": {"id": 4, "is_active": True, "is_focused": False},
                "os_window": {"id": 3, "is_active": True, "is_focused": False},
            }
        ],
    )
    try:
        assert MODULE.command_status(
            MODULE.argparse.Namespace(
                binding=str(binding_path),
                holder_receipt=None,
                binding_context=None,
                kitty_executable="/usr/bin/kitty",
                output=str(status_path),
            )
        ) == 0
        rendered = status_path.read_text(encoding="utf-8")
        assert "env" not in rendered.casefold()
        assert "token" not in rendered.casefold()
        assert "credential" not in rendered.casefold()
        assert stat.S_IMODE(
            Path(terminal["control_socket"]["path"]).stat().st_mode
        ) == before_mode == 0o600
    finally:
        listener.close()


def test_status_sanitizes_allowed_binding_strings_before_echoing(
    tmp_path: Path,
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    binding["goal_ref"] = "goal:credential=hunter2"
    terminal["title"] = "password=hunter2"
    try:
        projection, _state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        rendered = json.dumps(projection, sort_keys=True)
        assert "hunter2" not in rendered
        assert projection["binding"]["goal_ref"] == "goal:credential=<redacted>"
        assert projection["terminal"]["title"] == "password=<redacted>"
    finally:
        listener.close()


def test_safe_status_rejects_forbidden_field_even_if_caller_supplies_it() -> None:
    with pytest.raises(MODULE.IncarnationHomeError, match="unsafe field"):
        MODULE._emit_safe_json(
            {"schema_version": "test", "environment": {"TOKEN": "secret"}},
            label="unsafe test status",
        )


@pytest.mark.parametrize(
    "key",
    ["github_token", "database_password", "AWS_SECRET_ACCESS_KEY", "x-api-key"],
)
def test_safe_status_rejects_composite_credential_field(
    key: str,
) -> None:
    with pytest.raises(MODULE.IncarnationHomeError, match="unsafe field"):
        MODULE._emit_safe_json(
            {"schema_version": "test", key: "secret"},
            label="unsafe composite credential test status",
        )


def test_status_rejects_pid_start_tick_reuse_without_querying_kitty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    queried = False

    def forbidden_query(**_kwargs: object) -> list[dict[str, object]]:
        nonlocal queried
        queried = True
        return []

    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "drifted")
    monkeypatch.setattr(MODULE, "_kitty_ls", forbidden_query)
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "stale"
        assert projection["observation"]["kitty_query"] == "not_attempted"
        assert queried is False
    finally:
        listener.close()


def test_status_rejects_holder_exec_argv_drift_without_querying_kitty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    queried = False

    def forbidden_query(**_kwargs: object) -> list[dict[str, object]]:
        nonlocal queried
        queried = True
        return []

    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/replacement-codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_kitty_ls", forbidden_query)
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "stale"
        assert projection["observation"]["kitty_query"] == "not_attempted"
        assert queried is False
    finally:
        listener.close()


def test_status_rejects_holder_exec_executable_drift_without_querying_kitty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    queried = False

    def forbidden_query(**_kwargs: object) -> list[dict[str, object]]:
        nonlocal queried
        queried = True
        return []

    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: "sha256:" + "2" * 64)
    monkeypatch.setattr(MODULE, "_kitty_ls", forbidden_query)
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "stale"
        assert projection["observation"]["kitty_query"] == "not_attempted"
        assert queried is False
    finally:
        listener.close()


def test_status_preserves_observed_non_kitty_comm_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "zsh")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: "sha256:" + "1" * 64)
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "stale"
        assert projection["processes"]["kitty"]["comm"] == "zsh"
    finally:
        listener.close()


def test_status_rechecks_kitty_dedication_before_querying_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: "sha256:" + "1" * 64)
    monkeypatch.setattr(
        MODULE,
        "_kitty_dedication",
        lambda **_kwargs: (_ for _ in ()).throw(
            MODULE.IncarnationHomeError("holder Kitty process is not dedicated")
        ),
    )
    monkeypatch.setattr(
        MODULE,
        "_kitty_ls",
        lambda **_kwargs: pytest.fail("status queried Kitty after dedication drift"),
    )
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "stale"
        assert projection["observation"]["kitty_query"] == "not_attempted"
    finally:
        listener.close()


def test_status_reclassifies_dedication_race_after_terminal_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    calls: dict[int, int] = {}

    def identity_state(pid: int, _ticks: int) -> str:
        calls[pid] = calls.get(pid, 0) + 1
        if pid == terminal["pid"] and calls[pid] >= 2:
            return "gone"
        return "live"

    monkeypatch.setattr(MODULE, "_proc_identity_state", identity_state)
    monkeypatch.setattr(MODULE, "_proc_comm", lambda _pid: "kitty")
    monkeypatch.setattr(MODULE, "_descends_from", lambda _pid, _ancestor: True)
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/codex", "exec"]
        if pid == holder["pid"]
        else ["kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_exe_digest", lambda _pid: "sha256:" + "1" * 64)
    monkeypatch.setattr(
        MODULE,
        "_kitty_dedication",
        lambda **_kwargs: (_ for _ in ()).throw(
            MODULE.IncarnationHomeError("terminal exited during dedication check")
        ),
    )
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "missing"
        assert projection["processes"]["kitty"]["state"] == "gone"
        assert projection["observation"]["kitty_query"] == "not_available_after_exit"
        assert projection["terminal"]["exists"] is False
    finally:
        listener.close()


@pytest.mark.parametrize(
    ("holder_state", "terminal_state"),
    [("gone", "live"), ("live", "gone")],
)
def test_status_preserves_missing_terminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    holder_state: str,
    terminal_state: str,
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    states = {holder["pid"]: holder_state, terminal["pid"]: terminal_state}
    monkeypatch.setattr(
        MODULE,
        "_proc_identity_state",
        lambda pid, _ticks: states[pid],
    )
    try:
        projection, state = MODULE._observe_terminal_binding(
            binding=binding,
            holder=holder,
            terminal=terminal,
            kitty_executable="/usr/bin/kitty",
        )
        assert state == "missing"
        assert projection["observation"]["kitty_query"] == "not_available_after_exit"
        assert projection["terminal"]["exists"] is False
    finally:
        listener.close()


def test_directed_input_uses_bound_socket_and_window_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        MODULE,
        "_load_terminal_binding_input",
        lambda **_kwargs: (binding, holder, terminal, None, None),
    )
    monkeypatch.setattr(
        MODULE,
        "_observe_terminal_binding",
        lambda **_kwargs: (
            {"observation": {"kitty_query": "present"}},
            "live",
        ),
    )
    monkeypatch.setattr(MODULE, "_kitty_dedication", lambda **_kwargs: ("7", True))
    expected_holder_argv = ["/usr/bin/codex", "exec"]
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: expected_holder_argv
        if pid == holder["pid"]
        else ["/usr/bin/kitty", "--detach"],
    )
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(
        MODULE, "_proc_exe_digest", lambda _pid: holder["exe_digest"]
    )

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    try:
        assert MODULE.command_send_text(
            MODULE.argparse.Namespace(
                binding=str(tmp_path / "binding.json"),
                holder_receipt=None,
                binding_context=None,
                kitty_executable="/usr/bin/kitty",
                text="status\n",
            )
        ) == 0
        argv = calls["argv"]
        assert isinstance(argv, list)
        assert argv[argv.index("--to") + 1] == terminal["control_socket"]["address"]
        assert argv[argv.index("--match") + 1] == "id:7"
        assert "send-text" in argv
        assert "--stdin" in argv
        assert not {"focus-window", "move-window", "close-window"}.intersection(argv)
        assert calls["kwargs"]["input"] == "status\n"
        assert "env" not in capsys.readouterr().out.casefold()
    finally:
        listener.close()


def test_directed_input_rechecks_bound_holder_identity_before_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    monkeypatch.setattr(
        MODULE,
        "_load_terminal_binding_input",
        lambda **_kwargs: (binding, holder, terminal, None, None),
    )
    monkeypatch.setattr(
        MODULE,
        "_observe_terminal_binding",
        lambda **_kwargs: (
            {"observation": {"kitty_query": "present"}},
            "live",
        ),
    )
    monkeypatch.setattr(MODULE, "_kitty_dedication", lambda **_kwargs: ("7", True))
    monkeypatch.setattr(MODULE, "_proc_identity_state", lambda _pid, _ticks: "live")
    monkeypatch.setattr(
        MODULE,
        "_proc_argv",
        lambda pid: ["/usr/bin/replacement-codex", "exec"]
        if pid == holder["pid"]
        else ["/usr/bin/kitty", "--detach"],
    )
    monkeypatch.setattr(
        MODULE,
        "_proc_exe_digest",
        lambda _pid: holder["exe_digest"],
    )
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail(
            "directed input bypassed holder identity recheck"
        ),
    )
    try:
        with pytest.raises(MODULE.IncarnationHomeError, match="argv identity has drifted"):
            MODULE.command_send_text(
                MODULE.argparse.Namespace(
                    binding=str(tmp_path / "binding.json"),
                    holder_receipt=None,
                    binding_context=None,
                    kitty_executable="/usr/bin/kitty",
                    text="status\n",
                )
            )
    finally:
        listener.close()


def test_directed_input_rechecks_kitty_dedication_before_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listener, binding, holder, terminal = _terminal_binding_fixture(tmp_path)
    monkeypatch.setattr(
        MODULE,
        "_load_terminal_binding_input",
        lambda **_kwargs: (binding, holder, terminal, None, None),
    )
    monkeypatch.setattr(
        MODULE,
        "_observe_terminal_binding",
        lambda **_kwargs: (
            {"observation": {"kitty_query": "present"}},
            "live",
        ),
    )
    monkeypatch.setattr(
        MODULE,
        "_kitty_dedication",
        lambda **_kwargs: (_ for _ in ()).throw(
            MODULE.IncarnationHomeError("holder Kitty process is not dedicated")
        ),
    )
    monkeypatch.setattr(MODULE, "_proc_argv", lambda _pid: ["/usr/bin/kitty", "--detach"])
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("directed input bypassed dedication recheck"),
    )
    try:
        with pytest.raises(MODULE.IncarnationHomeError, match="not dedicated"):
            MODULE.command_send_text(
                MODULE.argparse.Namespace(
                    binding=str(tmp_path / "binding.json"),
                    holder_receipt=None,
                    binding_context=None,
                    kitty_executable="/usr/bin/kitty",
                    text="status\n",
                )
            )
    finally:
        listener.close()


def test_launch_rejects_explicit_empty_terminal_title() -> None:
    with pytest.raises(MODULE.IncarnationHomeError, match="terminal title"):
        MODULE.command_launch(MODULE.argparse.Namespace(terminal_title=""))


@pytest.mark.parametrize("field", ["binding_context", "control_socket"])
def test_launch_rejects_binding_options_without_terminal_title(field: str) -> None:
    arguments = MODULE.argparse.Namespace(
        terminal_title=None,
        binding_context=None,
        control_socket=None,
    )
    setattr(arguments, field, "/tmp/owner-binding-option")
    with pytest.raises(
        MODULE.IncarnationHomeError,
        match="binding options require --terminal-title",
    ):
        MODULE.command_launch(arguments)
