from __future__ import annotations

import importlib.util
import json
from pathlib import Path


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
    argv = MODULE.bound_codex_argv(
        codex_executable=executable,
        manifest=manifest,
        arguments=["resume", "thread-id"],
    )
    assert argv[:3] == [str(executable), "-m", "gpt-5.6-luna"]
    assert (
        f'shell_environment_policy.set={{CODEX_HOME="{actor_home}"}}' in argv
    )
    assert manifest["ambient_codex_home"] == str(ambient)


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
