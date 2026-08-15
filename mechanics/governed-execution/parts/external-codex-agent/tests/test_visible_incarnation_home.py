from __future__ import annotations

import importlib.util
import json
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
    executable = tmp_path / "codex"
    executable.write_text("binary", encoding="utf-8")
    executable.chmod(0o700)
    executable_link = tmp_path / "codex-link"
    executable_link.symlink_to(executable)
    argv = MODULE.bound_codex_argv(
        codex_executable=executable_link,
        manifest=manifest,
        arguments=["resume", "thread-id"],
    )
    assert argv[:3] == [str(executable), "-m", "gpt-5.6-luna"]
    assert (
        f'shell_environment_policy.set={{CODEX_HOME="{actor_home}"}}' in argv
    )
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
        "[history]\n"
        'model = "nested-model"\n'
    )

    bound = MODULE._bound_config(
        ambient_config.encode("utf-8"), "gpt-5.6-luna", "max"
    )
    parsed = tomllib.loads(bound.decode("utf-8"))

    assert parsed["model"] == "gpt-5.6-luna"
    assert parsed["model_reasoning_effort"] == "max"
    assert parsed["history"]["model"] == "nested-model"


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


def test_executable_version_must_match_realization_runtime(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'codex-cli 0.147.0'\n", encoding="utf-8"
    )
    executable.chmod(0o700)

    MODULE._verify_executable_version(executable, "0.147.0")
    with pytest.raises(MODULE.IncarnationHomeError, match="version mismatch"):
        MODULE._verify_executable_version(executable, "0.146.0")
