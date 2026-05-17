from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts" / "validate_stack.py").is_file()
        ):
            return candidate
    raise RuntimeError("could not find repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve())


def load_json(relative_path: str) -> object:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def test_machine_bridge_example_validates_against_schema() -> None:
    validator = Draft202012Validator(
        load_json("mechanics/machine-fit/parts/machine-bridge/schemas/schema.v1.json")
    )
    validator.validate(
        load_json(
            "mechanics/machine-fit/parts/machine-bridge/examples/machine-bridge.public.json.example"
        )
    )


def test_machine_bridge_capture_with_fake_abyss_machine(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "abyss-machine"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import sys

cmd = sys.argv[1:]

def emit(payload):
    print(json.dumps(payload))

if cmd[:2] == ["stack-bridge", "export"]:
    emit({
        "schema": "abyss_machine_stack_bridge_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"layers": 2, "refs": 2, "required_missing": 0, "schema_mismatches": 0},
        "paths": {"commands": {"export": "abyss-machine stack-bridge export --json"}},
        "artifacts": {
            "machine": {"bridge": {"path": "/etc/abyss-machine/bridge.json", "schema": "abyss_machine_bridge_v1", "truth_level": "contract"}},
            "processes": {"containers": {"path": "/var/lib/abyss-machine/processes/containers/latest.json", "schema": "abyss_machine_process_container_health_v1", "truth_level": "latest_container_evidence"}}
        },
        "first_commands": ["abyss-machine stack-bridge --json"]
    })
elif cmd[:2] == ["stack-bridge", "validate"]:
    emit({"schema": "abyss_machine_stack_bridge_validate_v1", "version": "0.test", "generated_at": "2026-05-11T00:00:00Z", "ok": True, "summary": {"fails": 0, "warnings": 0}})
elif cmd[:1] == ["bridge"]:
    emit({"schema": "abyss_machine_bridge_v1", "version": "0.test", "generated_at": "2026-05-11T00:00:00Z", "ok": True, "commands": {"stack_bridge_export_json": ["abyss-machine", "stack-bridge", "export", "--json"]}})
else:
    emit({"schema": "abyss_machine_stub_v1", "version": "0.test", "generated_at": "2026-05-11T00:00:00Z", "ok": True, "summary": {"status": "ok"}})
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    stack_root = tmp_path / "runtime"
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["AOA_STACK_ROOT"] = str(stack_root)

    completed = subprocess.run(
        [sys.executable, "scripts/aoa-machine-bridge", "--write-latest", "--check"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    latest = stack_root / "Logs" / "machine-bridge" / "latest" / "latest.private.json"
    index = stack_root / "Logs" / "machine-bridge" / "index.json"
    assert latest.is_file()
    assert index.is_file()

    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["artifact_kind"] == "aoa.machine-bridge"
    assert payload["captured_by"] == "scripts/aoa-machine-bridge"
    assert payload["status"] == "ready"
    assert payload["summary"]["stack_bridge_validate_ok"] is True
    assert "processes" in payload["artifact_index"]["classes"]
    assert payload["written_paths"]["index"] == str(index)

    index_payload = json.loads(index.read_text(encoding="utf-8"))
    assert index_payload["latest"] == str(latest)
    assert index_payload["records"][0]["bridge_id"] == payload["bridge_id"]
    assert index_payload["records"][0]["path"] == payload["written_paths"]["record"]
    assert index_payload["records"][0]["status"] == "ready"


def test_machine_bridge_check_prints_compact_public_safe_status(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "abyss-machine"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import sys

cmd = sys.argv[1:]

if cmd[:2] == ["stack-bridge", "export"]:
    print(json.dumps({
        "schema": "abyss_machine_stack_bridge_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"layers": 1, "refs": 1, "required_missing": 0, "schema_mismatches": 0},
        "paths": {"commands": {"export": "abyss-machine stack-bridge export --json"}},
        "artifacts": {
            "machine": {
                "bridge": {
                    "path": "/etc/abyss-machine/bridge.json",
                    "schema": "abyss_machine_bridge_v1",
                    "truth_level": "contract"
                }
            }
        }
    }))
elif cmd[:2] == ["stack-bridge", "validate"]:
    print(json.dumps({
        "schema": "abyss_machine_stack_bridge_validate_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"fails": 0, "warnings": 0}
    }))
elif cmd[:1] == ["bridge"]:
    print(json.dumps({
        "schema": "abyss_machine_bridge_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True
    }))
else:
    print(json.dumps({
        "schema": "abyss_machine_stub_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"status": "ok"}
    }))
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    completed = subprocess.run(
        [sys.executable, "scripts/aoa-machine-bridge", "--check"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["artifact_kind"] == "aoa.machine-bridge.check"
    assert payload["status"] == "ready"
    assert "artifact_index" not in payload
    assert "/etc/abyss-machine/bridge.json" not in completed.stdout


def test_machine_bridge_check_stays_ready_when_optional_probes_warn(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "abyss-machine"
    fake.write_text(
        """#!/usr/bin/env python3
import json
import sys

cmd = sys.argv[1:]

if cmd[:2] == ["stack-bridge", "export"]:
    print(json.dumps({
        "schema": "abyss_machine_stack_bridge_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"layers": 1, "refs": 1, "required_missing": 0, "schema_mismatches": 0},
        "paths": {"commands": {"export": "abyss-machine stack-bridge export --json"}},
        "artifacts": {"machine": {"bridge": {"path": "/etc/abyss-machine/bridge.json", "schema": "abyss_machine_bridge_v1", "truth_level": "contract"}}}
    }))
elif cmd[:2] == ["stack-bridge", "validate"]:
    print(json.dumps({
        "schema": "abyss_machine_stack_bridge_validate_v1",
        "version": "0.test",
        "generated_at": "2026-05-11T00:00:00Z",
        "ok": True,
        "summary": {"fails": 0, "warnings": 0}
    }))
elif cmd[:1] == ["bridge"]:
    print(json.dumps({"schema": "abyss_machine_bridge_v1", "version": "0.test", "generated_at": "2026-05-11T00:00:00Z", "ok": True}))
else:
    print("optional probe unavailable", file=sys.stderr)
    sys.exit(2)
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"

    completed = subprocess.run(
        [sys.executable, "scripts/aoa-machine-bridge", "--check"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ready"
    assert payload["summary"]["warnings"] > 0
    assert any("unavailable" in warning for warning in payload["warnings"])
