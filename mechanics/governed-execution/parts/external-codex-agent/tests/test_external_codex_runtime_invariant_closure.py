from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = PART_ROOT / "external_codex_agent.py"


def _load_runtime_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "abyss_stack_external_codex_runtime_invariant_closure",
        CONTROLLER_PATH,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load controller: {CONTROLLER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME = _load_runtime_module()
PROFILE = json.loads(
    (PART_ROOT / "runtime-profile.v1.json").read_text(encoding="utf-8")
)


def _tool_profile(profile_id: str) -> dict[str, object]:
    return next(
        item for item in PROFILE["tool_profiles"] if item["profile_id"] == profile_id
    )


def _launch(workspace: Path, codex_home: Path) -> dict[str, object]:
    return {
        "environment_allowlist": [],
        "codex_home": str(codex_home),
        "workspace_path": str(workspace),
    }


def _git_workspace(path: Path) -> None:
    path.mkdir()
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_preflight_does_not_bind_state_root_as_attempt_python_cache(
    tmp_path: Path,
) -> None:
    state_root = tmp_path / "state-root"
    state_root.mkdir()
    workspace = tmp_path / "workspace"
    _git_workspace(workspace)
    runtime = RUNTIME.ExternalCodexRuntime(state_root)
    launch = _launch(workspace, tmp_path / "codex-home")
    tool = _tool_profile(
        "abyss-stack:external_codex_agent/structured-owner-duty-workspace-write-v1"
    )

    preflight_environment = runtime._codex_environment(
        launch,
        state_root,
        tool,
        apply_attempt_hygiene=False,
    )

    assert "PYTHONPYCACHEPREFIX" not in preflight_environment
    assert not (state_root / "python-pycache").exists()
    assert preflight_environment["TMPDIR"] == str(state_root)


@pytest.mark.parametrize(
    "profile_id",
    tuple(
        item["profile_id"]
        for item in PROFILE["tool_profiles"]
        if item["codex_sandbox"] == "workspace-write"
    ),
)
def test_real_attempt_environment_is_distinct_and_scratch_bound(
    tmp_path: Path,
    profile_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _git_workspace(workspace)
    runtime = RUNTIME.ExternalCodexRuntime(tmp_path / "state-root")
    launch = _launch(workspace, tmp_path / "codex-home")
    tool = _tool_profile(profile_id)
    first_scratch = tmp_path / "attempts" / "001" / "scratch"
    second_scratch = tmp_path / "attempts" / "002" / "scratch"
    first_scratch.mkdir(parents=True)
    second_scratch.mkdir(parents=True)
    if _tool_profile(profile_id).get("specialized_environment") is not None:
        release = tmp_path / "verified-release"
        (release / "environments/landing-validation-v1/pythonpath").mkdir(
            parents=True
        )
        (release / "sdk/src").mkdir(parents=True)
        (release / "owners/aoa-stats").mkdir(parents=True)
        monkeypatch.setenv("AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT", str(release))

    first = runtime._codex_environment(launch, first_scratch, tool)
    second = runtime._codex_environment(launch, second_scratch, tool)

    assert Path(first["PYTHONPYCACHEPREFIX"]) == first_scratch / "python-pycache"
    assert Path(second["PYTHONPYCACHEPREFIX"]) == second_scratch / "python-pycache"
    assert first["PYTHONPYCACHEPREFIX"] != second["PYTHONPYCACHEPREFIX"]


@pytest.mark.parametrize(
    "source_spelling",
    (
        "/tmp/данные/workspace",
        r"/tmp/\u0434\u0430\u043d\u043d\u044b\u0435/workspace",
        r"\/tmp\/\u0434\u0430\u043d\u043d\u044b\u0435\/workspace",
        r"/tmp\/\u0434а\u043dн\u044bе/workspace",
        r"/tmp/\u005cu0434\u005cu0430\u005cu043d\u005cu043d\u005cu044b\u005cu0435/workspace",
    ),
)
def test_text_redaction_replaces_only_the_mapped_source_span(
    source_spelling: str,
) -> None:
    source = "/tmp/данные/workspace"
    value = rf"prefix\n\t\\before {source_spelling} after \/tail"

    redacted = RUNTIME._replace_source_aliases_in_text(
        value,
        ((source, "<controller-path-redacted>"),),
    )

    assert redacted == r"prefix\n\t\\before <controller-path-redacted> after \/tail"
    assert not RUNTIME._contains_source_path(redacted, source)


def test_nested_text_redaction_prefers_longest_alias_and_preserves_suffix() -> None:
    source = "/tmp/данные/workspace"
    ancestor = "/tmp/данные"
    value = r"left\n/tmp/\u0434\u0430\u043d\u043d\u044b\u0435/workspace/notes\tend"

    redacted = RUNTIME._replace_source_aliases_in_text(
        value,
        (
            (source, "/tmp/aoa-external-actor-workspace"),
            (ancestor, "<controller-path-redacted>"),
        ),
    )

    assert redacted == r"left\n/tmp/aoa-external-actor-workspace/notes\tend"
    assert not RUNTIME._contains_source_path(redacted, source)
    assert not RUNTIME._contains_source_path(redacted, ancestor)


def test_actor_safe_utf8_fixture_keeps_literal_backslash_bytes_outside_redaction() -> None:
    source = "/tmp/данные/workspace"
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }
    raw = (
        r"literal\n prefix "
        + source
        + r" suffix \/literal\t\n"
    ).encode("utf-8")

    envelope, encoded = RUNTIME._actor_safe_input_envelope(
        input_id="runtime-invariant-closure-text",
        raw=raw,
        original_provenance=provenance,
        aliases=(source,),
        source_roots=frozenset(),
    )

    assert envelope["payload"] == (
        r"literal\n prefix <controller-path-redacted> suffix \/literal\t\n"
    )
    encoded_payload = json.dumps(
        envelope["payload"],
        ensure_ascii=True,
    )[1:-1].encode("utf-8")
    assert encoded_payload in encoded
    assert source.encode("utf-8") not in encoded
