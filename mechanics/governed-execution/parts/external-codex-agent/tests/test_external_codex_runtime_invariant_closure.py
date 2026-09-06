from __future__ import annotations

import importlib.util
import json
import shlex
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


_DEEP_SHELL_COMMAND = "/usr/bin/git push"
for _ in range(4):
    _DEEP_SHELL_COMMAND = shlex.join(
        ["/usr/bin/bash", "-lc", _DEEP_SHELL_COMMAND]
    )


@pytest.mark.parametrize(
    ("commands", "expected_effects"),
    (
        pytest.param(
            ("/usr/bin/python3 -c 'print(42)'",),
            ["unclassified_indirect_effect"],
            id="opaque-interpreter",
        ),
        pytest.param(
            ("/usr/bin/nice /usr/bin/cat /home/fixture/.ssh/id_rsa",),
            ["secret_access", "unclassified_indirect_effect"],
            id="launch-wrapper-secret",
        ),
        pytest.param(
            (_DEEP_SHELL_COMMAND,),
            ["unclassified_indirect_effect"],
            id="deep-shell-nesting",
        ),
        pytest.param(
            ("/usr/bin/bash -lc 'echo $(cat /home/operator/.ssh/id_rsa)'",),
            ["secret_access", "unclassified_indirect_effect"],
            id="command-substitution-secret",
        ),
        pytest.param(
            ("/usr/bin/make -f /tmp/leak.mk leak",),
            ["unclassified_indirect_effect"],
            id="build-runner",
        ),
        pytest.param(
            ("/usr/bin/git -c alias.leak='!cat /home/operator/.ssh/id_rsa' leak",),
            ["secret_access", "unclassified_indirect_effect"],
            id="git-alias-indirection",
        ),
        pytest.param(
            ("/usr/bin/bash -lc 'source scripts/helper.sh'",),
            ["unclassified_indirect_effect"],
            id="sourced-shell",
        ),
        pytest.param(
            ("/usr/bin/bash scripts/helper.sh -c '/usr/bin/true'",),
            ["unclassified_indirect_effect"],
            id="shell-script-before-c",
        ),
        pytest.param(
            ("/usr/bin/bash --rcfile -x -ic '/usr/bin/true'",),
            ["unclassified_indirect_effect"],
            id="shell-startup-file",
        ),
        pytest.param(
            ("/usr/bin/git config --local core.hooksPath /tmp/hooks",),
            ["unclassified_indirect_effect"],
            id="git-local-config-write",
        ),
        pytest.param(
            ("/usr/bin/git config --get http.https://example.com/.extraheader",),
            ["unclassified_indirect_effect"],
            id="git-config-read",
        ),
        pytest.param(
            (
                "/usr/bin/git branch --edit-description",
                "/usr/bin/git bisect run scripts/helper",
                "/usr/bin/git verify-commit HEAD",
                "/usr/bin/git fetch --upload-pack=/tmp/helper /tmp/remote",
                "/usr/bin/git notes edit HEAD",
                "/usr/bin/git grep --open-files-in-pager=/tmp/helper pattern",
                "/usr/bin/git init --separate-git-dir=/tmp/repo-meta --template=/tmp/template .",
                "/usr/bin/git ls-remote --upload-pack=/tmp/helper /tmp/remote",
            ),
            ["unclassified_indirect_effect"],
            id="git-hidden-programs",
        ),
        pytest.param(
            ("/usr/bin/git cat-file --filter HEAD:README.md",),
            ["unclassified_indirect_effect"],
            id="git-cat-file-filter",
        ),
        pytest.param(
            ("/usr/bin/git for-each-ref --sort=version:signature:grade",),
            ["unclassified_indirect_effect"],
            id="git-signature-format",
        ),
        pytest.param(
            ("/usr/bin/git hash-object -- README.md --no-filters",),
            ["unclassified_indirect_effect"],
            id="git-hash-object-filter",
        ),
        pytest.param(
            ("/usr/bin/rg --pre=/bin/sh pattern scripts/helper.sh",),
            ["unclassified_indirect_effect"],
            id="ripgrep-hidden-program",
        ),
        pytest.param(
            ("/usr/bin/jq -n env",),
            ["secret_access", "unclassified_indirect_effect"],
            id="jq-environment-read",
        ),
        pytest.param(
            ("/usr/bin/sort -S 4K --compress-program=/tmp/helper input",),
            ["unclassified_indirect_effect"],
            id="sort-hidden-program",
        ),
        pytest.param(
            ("/usr/bin/git update-ref refs/heads/hidden HEAD",),
            ["unclassified_indirect_effect"],
            id="git-hidden-ref-mutation",
        ),
        pytest.param(
            ("/usr/bin/git symbolic-ref HEAD refs/heads/other",),
            ["unclassified_indirect_effect"],
            id="git-symbolic-ref-mutation",
        ),
        pytest.param(
            ("/usr/bin/git reflog expire --expire=now --all",),
            ["unclassified_indirect_effect"],
            id="git-reflog-mutation",
        ),
        pytest.param(
            ("/usr/bin/base64 /home/operator/.ssh/id_rsa",),
            ["secret_access", "unclassified_indirect_effect"],
            id="direct-secret-encoder",
        ),
        pytest.param(
            ("./scripts/helper",),
            ["unclassified_indirect_effect"],
            id="workspace-executable",
        ),
        pytest.param(
            ("/usr/bin/bash -lc 'git${IFS}push'",),
            ["unclassified_indirect_effect"],
            id="parameter-expansion",
        ),
        pytest.param(
            ("helper --emit-secret",),
            ["unclassified_indirect_effect"],
            id="bare-executable",
        ),
        pytest.param(
            ("/usr/bin/bash -O extglob -lc 'g@(it) push'",),
            ["unclassified_indirect_effect"],
            id="extglob-expansion",
        ),
        pytest.param(
            ("/usr/bin/awk 'BEGIN { system(\"git push\") }'",),
            ["unclassified_indirect_effect"],
            id="awk-launcher",
        ),
        pytest.param(
            ("/tmp/bash -lc '/usr/bin/true'",),
            ["unclassified_indirect_effect"],
            id="non-system-shell",
        ),
        pytest.param(
            ("/usr/bin/sed -nf scripts/leak.sed README.md",),
            ["unclassified_indirect_effect"],
            id="unsandboxed-sed",
        ),
        pytest.param(
            ("/usr/bin/git diff --check",),
            ["unclassified_indirect_effect"],
            id="config-driven-git",
        ),
        pytest.param(
            (r"/usr/bin/bash -lc 'true\ngit push'",),
            ["unclassified_indirect_effect"],
            id="multiline-shell",
        ),
    ),
)
def test_opaque_command_guard_covers_each_worker_shape(
    commands: tuple[str, ...],
    expected_effects: list[str],
) -> None:
    task = {
        "allowed_effect_class": "read_only",
        "indirect_command_policy": "fail_closed",
    }
    observed = RUNTIME.ExternalCodexRuntime._forbidden_effects(
        None,
        [
            {"command": command, "status": "completed", "exit_code": 0}
            for command in commands
        ],
        task,
    )

    assert observed == expected_effects


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


def test_preview_writer_profile_matches_preview_bound_coder_effects() -> None:
    tool = _tool_profile(
        "abyss-stack:external_codex_agent/landing-workspace-write-preview-v1"
    )

    assert tool["sandbox_mode"] == "workspace_write"
    assert tool["allowed_effect_classes"] == ["read_only", "repo_mutation"]
    assert tool["network_access"] == "disabled"
    assert tool["external_effects"] is False


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


def test_plain_text_redaction_keeps_identity_span_mapping() -> None:
    source = "/tmp/plain/workspace"
    value = f"prefix {source} suffix"

    redacted = RUNTIME._replace_source_aliases_in_text(
        value,
        ((source, "<controller-path-redacted>"),),
    )

    assert redacted == "prefix <controller-path-redacted> suffix"
    assert not RUNTIME._contains_source_path(redacted, source)


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


def test_actor_envelope_reuses_decoded_layers_only_within_one_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provenance = {
        "artifact_digest": "sha256:" + "a" * 64,
        "schema_ref": "fixture-v1",
        "schema_version": "fixture-v1",
    }
    aliases = (
        "/tmp/данные/workspace",
        "/tmp/данные",
        "/tmp",
    )
    raw = rb"TEXT literal\\n suffix"
    original_decoder = RUNTIME._json_escape_decoding_layers
    decoder_calls: list[str] = []

    def counted_decoder(value: str) -> tuple[str, ...]:
        decoder_calls.append(value)
        return original_decoder(value)

    monkeypatch.setattr(
        RUNTIME,
        "_json_escape_decoding_layers",
        counted_decoder,
    )

    RUNTIME._actor_safe_input_envelope(
        input_id="decoded-layer-cache-first-build",
        raw=raw,
        original_provenance=provenance,
        aliases=aliases,
        source_roots=frozenset(),
    )
    first_build_calls = tuple(decoder_calls)
    assert first_build_calls
    assert len(first_build_calls) == len(set(first_build_calls))

    RUNTIME._actor_safe_input_envelope(
        input_id="decoded-layer-cache-first-build",
        raw=raw,
        original_provenance=provenance,
        aliases=aliases,
        source_roots=frozenset(),
    )
    assert tuple(decoder_calls) == first_build_calls + first_build_calls
