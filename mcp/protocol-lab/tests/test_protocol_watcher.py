from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


LAB_ROOT = Path(__file__).resolve().parents[1]
WATCHER_PATH = LAB_ROOT / "scripts" / "protocol_watcher.py"


def _load_watcher() -> Any:
    spec = importlib.util.spec_from_file_location(
        "protocol_watcher_under_test",
        WATCHER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: dict[str, Any], mode: int = 0o644) -> None:
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(mode)


def _fixture(tmp_path: Path, *, expires_in: timedelta = timedelta(days=2)) -> tuple[Path, Path, datetime]:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    (tmp_path / "watched.txt").write_text("v1\n", encoding="utf-8")
    _write_json(
        tmp_path / "protocol-status.json",
        {
            "evidence_expires_at": (now + expires_in).isoformat().replace("+00:00", "Z"),
            "read_only_pilot_allowed": True,
            "core_read_migration_allowed": False,
            "production_cutover_blockers": ["production_modern_pair_not_admitted"],
            "reason_codes": ["tasks_client_extension_capability_absent"],
        },
    )
    plan = {
        "schema_version": "abyss_mcp_protocol_watch_plan_v1",
        "plan_id": "test-watch",
        "ttl_lead_seconds": 3600,
        "ttl_source": {"path": "protocol-status.json", "pointer": "/evidence_expires_at"},
        "inputs": [
            {
                "input_id": "local-contract",
                "kind": "file",
                "path": "watched.txt",
                "required": True,
            }
        ],
        "claim_limits": ["lab only", "no production writes", "receipt gated"],
    }
    plan_path = tmp_path / "plan.json"
    _write_json(plan_path, plan)
    return plan_path, tmp_path / "state", now


def _runtime(tmp_path: Path, protected: Path, *, mutate_protected: bool = False) -> Path:
    code = (
        "from pathlib import Path; import os,sys; "
        "p=Path(sys.argv[1]); p.write_text('{\"passed\":true}\\n'); os.chmod(p,0o600)"
    )
    if mutate_protected:
        code += "; Path(sys.argv[2]).write_text('mutated\\n')"
    argv = [sys.executable, "-c", code, "{run_root}/private-receipt.json"]
    if mutate_protected:
        argv.append(str(protected))
    runtime = {
        "schema_version": "abyss_mcp_protocol_watch_runtime_v1",
        "steps": [
            {
                "step_id": "bounded-lab",
                "argv": argv,
                "environment": {},
                "timeout_seconds": 10,
            }
        ],
        "secret_files": {},
        "protected_paths": [str(protected)],
        "required_receipts": [
            {
                "receipt_id": "private-proof",
                "path": "{run_root}/private-receipt.json",
                "visibility": "private",
            }
        ],
    }
    path = tmp_path / "runtime.json"
    _write_json(path, runtime, mode=0o600)
    return path


def test_success_advances_only_content_addressed_lab_baseline(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    protected = tmp_path / "production-config.toml"
    protected.write_text("stable\n", encoding="utf-8")
    runtime = _runtime(tmp_path, protected)

    first = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=runtime,
        execute=True,
        offline=False,
        timeout=5,
        now=now,
    )
    second = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=runtime,
        execute=True,
        offline=False,
        timeout=5,
        now=now + timedelta(minutes=1),
    )

    assert first["execution_state"] == "lab_passed"
    assert first["trigger_reasons"] == ["no_successful_baseline"]
    assert first["protected_paths_unchanged"] is True
    assert first["production_automatically_changed"] is False
    assert first["verdicts"]["eligible_for_read_canary"] is True
    assert first["verdicts"]["production_cutover_allowed"] is False
    assert second["execution_state"] == "no_change"
    assert second["triggered"] is False
    assert second["previous_success_digest"] == first["input_snapshot_digest"]
    assert protected.read_text(encoding="utf-8") == "stable\n"
    assert (state_root / "current.json").stat().st_mode & 0o777 == 0o600
    assert (state_root / "public-safe.json").stat().st_mode & 0o777 == 0o644
    assert Path(first["private_observation_ref"].removeprefix("local://")).is_file()
    public = json.loads((state_root / "public-safe.json").read_text())
    assert public["private_observation_ref"].startswith("private://")
    assert str(tmp_path) not in json.dumps(public)
    assert all("resolved_path" not in item for item in public["inputs"])

    schema = json.loads(
        (LAB_ROOT / "schemas" / "protocol-watch-status.schema.json").read_text()
    )
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(first)
    )
    assert errors == []
    public_errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(public)
    )
    assert public_errors == []


def test_failed_protected_path_invariant_never_advances_baseline(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    protected = tmp_path / "production-config.toml"
    protected.write_text("stable\n", encoding="utf-8")
    runtime = _runtime(tmp_path, protected, mutate_protected=True)

    result = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=runtime,
        execute=True,
        offline=False,
        timeout=5,
        now=now,
    )

    assert result["execution_state"] == "lab_failed"
    assert result["protected_paths_unchanged"] is False
    assert not (state_root / "last-success.json").exists()
    assert "protected production files changed" in " ".join(result["failures"])


def test_required_observation_failure_is_fail_closed(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    (tmp_path / "watched.txt").unlink()

    result = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=None,
        execute=True,
        offline=False,
        timeout=5,
        now=now,
    )

    assert result["observation_ready"] is False
    assert result["execution_state"] == "observation_blocked"
    assert result["verdicts"]["compatible_for_lab"] is False
    assert not (state_root / "last-success.json").exists()


def test_ttl_due_retriggers_an_unchanged_snapshot(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    protected = tmp_path / "production-config.toml"
    protected.write_text("stable\n", encoding="utf-8")
    runtime = _runtime(tmp_path, protected)
    watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=runtime,
        execute=True,
        offline=False,
        timeout=5,
        now=now,
    )

    result = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=None,
        execute=False,
        offline=False,
        timeout=5,
        now=now + timedelta(days=2),
    )

    assert result["triggered"] is True
    assert result["execution_state"] == "trigger_pending"
    assert result["trigger_reasons"] == ["evidence_ttl_due"]
