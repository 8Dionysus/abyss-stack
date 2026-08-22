from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys

from jsonschema import Draft202012Validator, FormatChecker
import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PART_ROOT / "scripts" / "render_codex_hooks.py"
FRAGMENT_SCHEMA_PATH = PART_ROOT / "schemas" / "codex-hooks-fragment.schema.json"
RECEIPT_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "codex-hooks-composition-receipt.schema.json"
)
AGENT_FRAGMENT_PATH = (
    PART_ROOT / "config" / "abyss-stack-agent-tool-routing.fragment.json"
)
AGENT_ADAPTER_PATH = PART_ROOT / "scripts" / "codex_pretool_agent_routing.py"

SPEC = importlib.util.spec_from_file_location("render_codex_hooks", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
COMPOSITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPOSITOR)


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def native_session_fragment() -> dict:
    return {
        "description": "Standalone session evidence hooks",
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /opt/session/hook.py SessionStart",
                            "statusMessage": "Session evidence start",
                            "timeout": 20,
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /opt/session/hook.py UserPromptSubmit",
                            "timeout": 20,
                        }
                    ]
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 /opt/session/hook.py Stop",
                            "timeout": 20,
                        }
                    ]
                }
            ],
        },
    }


def memo_owner_fragment() -> dict:
    command = (
        '/usr/bin/python3 "{{AOA_MEMO_HOOK_SCRIPT}}" observe '
        '--state-root "{{AOA_MEMO_STATE_ROOT}}"'
    )
    return {
        "schema_version": "abyss_codex_hooks_fragment_v0",
        "fragment_id": "aoa-memo:participation-shadow:v0",
        "owner": "aoa-memo",
        "mode": "shadow",
        "description": "No-content memo participation observation",
        "bindings": [
            "AOA_MEMO_HOOK_SCRIPT",
            "AOA_MEMO_STATE_ROOT",
        ],
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 2,
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "^mcp__aoa_memo__.*$",
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 2,
                        }
                    ],
                }
            ],
            "SessionEnd": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": command,
                            "timeout": 2,
                        }
                    ]
                }
            ],
        },
    }


def bindings() -> dict[str, str]:
    return {
        "AOA_MEMO_HOOK_SCRIPT": "/opt/aoa-memo/participation.py",
        "AOA_MEMO_STATE_ROOT": "/srv/abyss-machine/state/aoa-memo",
    }


def composed(tmp_path: Path) -> tuple[dict, list[dict], dict[str, str], Path, Path]:
    native_path = write_json(tmp_path / "native.json", native_session_fragment())
    memo_path = write_json(tmp_path / "memo.json", memo_owner_fragment())
    output, fragments, binding_digests = COMPOSITOR.compose(
        [native_path, memo_path],
        bindings(),
    )
    return output, fragments, binding_digests, native_path, memo_path


def test_owner_fragment_schema_and_native_coexistence(tmp_path: Path) -> None:
    schema = load_json(FRAGMENT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(memo_owner_fragment())

    output, fragments, binding_digests, _, _ = composed(tmp_path)
    assert list(output["hooks"]) == [
        "SessionStart",
        "UserPromptSubmit",
        "PostToolUse",
        "Stop",
        "SessionEnd",
    ]
    prompt_groups = output["hooks"]["UserPromptSubmit"]
    assert len(prompt_groups) == 2
    assert prompt_groups[0]["hooks"][0]["command"].endswith("UserPromptSubmit")
    assert prompt_groups[1]["hooks"][0]["command"] == (
        '/usr/bin/python3 "/opt/aoa-memo/participation.py" observe '
        '--state-root "/srv/abyss-machine/state/aoa-memo"'
    )
    assert set(output) == {"description", "hooks"}
    assert "schema_version" not in output
    assert fragments[0]["fragment_id"] == "native-config:0"
    assert fragments[0]["owner"] == "external-native"
    assert fragments[1]["owner"] == "aoa-memo"
    assert set(binding_digests) == set(bindings())
    assert all(value.startswith("sha256:") for value in binding_digests.values())


def test_stack_agent_fragment_preserves_existing_native_handlers(
    tmp_path: Path,
) -> None:
    fragment = load_json(AGENT_FRAGMENT_PATH)
    fragment_schema = load_json(FRAGMENT_SCHEMA_PATH)
    Draft202012Validator.check_schema(fragment_schema)
    Draft202012Validator(fragment_schema).validate(fragment)
    native_path = write_json(tmp_path / "native.json", native_session_fragment())

    output, fragments, binding_digests = COMPOSITOR.compose(
        [AGENT_FRAGMENT_PATH, native_path],
        {"AOA_CODEX_AGENT_ROUTING_HOOK": str(AGENT_ADAPTER_PATH)},
    )

    assert list(output["hooks"]) == [
        "SessionStart",
        "UserPromptSubmit",
        "PreToolUse",
        "Stop",
    ]
    assert output["hooks"]["PreToolUse"] == [
        {
            "matcher": "^collaboration.*$",
            "hooks": [
                {
                    "type": "command",
                    "command": f'/usr/bin/python3 "{AGENT_ADAPTER_PATH}"',
                    "timeout": 10,
                    "statusMessage": "Routing Codex collaboration tool through AoA",
                }
            ],
        }
    ]
    assert output["hooks"]["SessionStart"] == native_session_fragment()[
        "hooks"
    ]["SessionStart"]
    assert output["hooks"]["UserPromptSubmit"] == native_session_fragment()[
        "hooks"
    ]["UserPromptSubmit"]
    assert output["hooks"]["Stop"] == native_session_fragment()["hooks"]["Stop"]
    assert fragment["owner"] == "abyss-stack"
    assert fragments[0]["fragment_id"] == "abyss-stack:agent-tool-routing:v1"
    assert fragments[1]["owner"] == "external-native"
    assert set(binding_digests) == {"AOA_CODEX_AGENT_ROUTING_HOOK"}


def test_exact_duplicate_handler_is_rejected(tmp_path: Path) -> None:
    first = write_json(tmp_path / "first.json", native_session_fragment())
    second = write_json(tmp_path / "second.json", native_session_fragment())
    with pytest.raises(COMPOSITOR.CompositionError, match="exact duplicate"):
        COMPOSITOR.compose([first, second], {})


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (
            lambda payload: payload["hooks"]["UserPromptSubmit"][0].update(
                {"matcher": "ignored"}
            ),
            "cannot use a matcher",
        ),
        (
            lambda payload: payload["hooks"]["UserPromptSubmit"][0]["hooks"][0].update(
                {"type": "prompt"}
            ),
            "must be a command hook",
        ),
        (
            lambda payload: payload["hooks"]["UserPromptSubmit"][0]["hooks"][0].update(
                {"decision": "block"}
            ),
            "unsupported fields",
        ),
        (
            lambda payload: payload["hooks"].update(
                {
                    "FutureEvent": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "true",
                                }
                            ]
                        }
                    ]
                }
            ),
            "unsupported events",
        ),
        (
            lambda payload: payload["hooks"]["SessionEnd"][0]["hooks"][0].update(
                {"timeout": 4}
            ),
            "SessionEnd timeout ceiling",
        ),
    ],
)
def test_unsupported_or_ignored_codex_shapes_fail_closed(
    tmp_path: Path,
    mutation,
    match: str,
) -> None:
    payload = memo_owner_fragment()
    mutation(payload)
    path = write_json(tmp_path / "fragment.json", payload)
    with pytest.raises(COMPOSITOR.CompositionError, match=match):
        COMPOSITOR.compose([path], bindings())


def test_binding_contract_is_exact_and_shell_safe(tmp_path: Path) -> None:
    payload = memo_owner_fragment()
    payload["bindings"].pop()
    path = write_json(tmp_path / "fragment.json", payload)
    with pytest.raises(COMPOSITOR.CompositionError, match="undeclared placeholders"):
        COMPOSITOR.compose([path], bindings())

    with pytest.raises(COMPOSITOR.CompositionError, match="safe absolute path"):
        COMPOSITOR.parse_bindings(
            ['AOA_MEMO_HOOK_SCRIPT=/tmp/hook.py"; touch /tmp/escaped']
        )
    with pytest.raises(COMPOSITOR.CompositionError, match="unused binding"):
        clean = write_json(tmp_path / "native.json", native_session_fragment())
        COMPOSITOR.compose([clean], {"UNUSED": "/safe/path"})


def test_atomic_write_backup_and_receipt_are_content_minimized(tmp_path: Path) -> None:
    output, fragments, binding_digests, native_path, memo_path = composed(tmp_path)
    target = tmp_path / "hooks.json"
    old_bytes = b'{"hooks":{"Old":[]}}\n'
    target.write_bytes(old_bytes)
    target.chmod(0o644)
    receipt_path = tmp_path / "composition-receipt.json"
    backup_dir = tmp_path / "backups"

    receipt = COMPOSITOR.install_composition(
        output=output,
        fragments=fragments,
        binding_digests=binding_digests,
        target=target,
        receipt_path=receipt_path,
        backup_dir=backup_dir,
    )

    assert target.read_bytes() == COMPOSITOR.rendered_json(output)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    backups = list(backup_dir.iterdir())
    assert len(backups) == 1
    assert backups[0].read_bytes() == old_bytes
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600

    schema = load_json(RECEIPT_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(receipt)
    assert receipt["receipt_digest"] == COMPOSITOR.receipt_digest(receipt)
    assert receipt["target_changed"] is True
    assert receipt["backup_name"] == backups[0].name
    assert not any(receipt["authority"].values())

    serialized_receipt = json.dumps(receipt, ensure_ascii=False)
    for forbidden in (
        str(native_path),
        str(memo_path),
        str(target),
        *bindings().values(),
        "/opt/session/hook.py",
    ):
        assert forbidden not in serialized_receipt


def test_receipt_failure_restores_previous_target_and_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output, fragments, binding_digests, _, _ = composed(tmp_path)
    target = tmp_path / "hooks.json"
    old_bytes = b'{"old":true}\n'
    target.write_bytes(old_bytes)
    target.chmod(0o640)
    receipt_path = tmp_path / "receipt.json"
    real_write = COMPOSITOR.atomic_private_write

    def failing_write(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
        if path == receipt_path:
            raise OSError("synthetic receipt failure")
        real_write(path, payload, mode=mode)

    monkeypatch.setattr(COMPOSITOR, "atomic_private_write", failing_write)
    with pytest.raises(OSError, match="synthetic receipt failure"):
        COMPOSITOR.install_composition(
            output=output,
            fragments=fragments,
            binding_digests=binding_digests,
            target=target,
            receipt_path=receipt_path,
            backup_dir=tmp_path / "backups",
        )

    assert target.read_bytes() == old_bytes
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert not receipt_path.exists()


def test_cli_check_output_is_read_only_and_exact(tmp_path: Path) -> None:
    output, _, _, native_path, memo_path = composed(tmp_path)
    candidate = tmp_path / "candidate.json"
    candidate.write_bytes(COMPOSITOR.rendered_json(output))
    command = [
        sys.executable,
        str(SCRIPT_PATH),
        "--fragment",
        str(native_path),
        "--fragment",
        str(memo_path),
        "--binding",
        "AOA_MEMO_HOOK_SCRIPT=/opt/aoa-memo/participation.py",
        "--binding",
        "AOA_MEMO_STATE_ROOT=/srv/abyss-machine/state/aoa-memo",
        "--check-output",
        str(candidate),
    ]
    before = candidate.stat()
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    after = candidate.stat()
    assert result.returncode == 0
    assert result.stdout == "[ok] composed Codex hook output is exact\n"
    assert result.stderr == ""
    assert before.st_mtime_ns == after.st_mtime_ns
    assert before.st_size == after.st_size


def test_native_config_is_self_sufficient_without_owner_envelope(
    tmp_path: Path,
) -> None:
    path = write_json(tmp_path / "standalone.json", native_session_fragment())
    output, fragments, binding_digests = COMPOSITOR.compose([path], {})
    assert output["hooks"] == native_session_fragment()["hooks"]
    assert fragments[0]["mode"] == "standalone"
    assert binding_digests == {}
