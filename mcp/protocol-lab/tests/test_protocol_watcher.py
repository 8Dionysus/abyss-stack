from __future__ import annotations

import importlib.util
import json
import os
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


def _retention_plan(plan_path: Path, **overrides: Any) -> dict[str, Any]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    defaults = {
        "max_successful_runs": 14,
        "max_successful_bytes": 1024 * 1024 * 1024,
        "max_successful_age_seconds": 7 * 24 * 60 * 60,
        "max_failed_runs": 6,
        "max_failed_bytes": 512 * 1024 * 1024,
        "max_failed_age_seconds": 14 * 24 * 60 * 60,
        "retain_failed_diagnostics": 2,
        "max_observations": 64,
        "max_observation_bytes": 16 * 1024 * 1024,
        "max_observation_age_seconds": 30 * 24 * 60 * 60,
        "disposable_roots": ["stable-home", "lab/codex-home", "step-logs"],
        "diagnostic_roots": ["step-logs"],
        "cache_roots": ["stable-home/.tmp/plugins", "lab/codex-home/.tmp/plugins"],
        "receipt_archive_root": "retained-receipts",
        "pin_file": "pinned-runs.json",
    }
    defaults.update(overrides)
    plan["retention"] = defaults
    plan_path.write_text(json.dumps(plan) + "\n", encoding="utf-8")
    return plan


def _write_run(
    state_root: Path,
    run_id: str,
    finished_at: datetime,
    *,
    passed: bool = True,
    include_disposable: bool = True,
    state: str | None = None,
) -> Path:
    run_root = state_root / "runs" / run_id
    run_root.mkdir(parents=True, mode=0o700)
    _write_json(
        run_root / "input-snapshot.json",
        {"run_id": run_id, "input_snapshot_digest": "sha256:" + "1" * 64},
        mode=0o600,
    )
    receipt = {
        "run_id": run_id,
        "passed": passed,
        "receipts": [],
        "failures": [] if passed else ["step bounded-lab returned 1"],
    }
    if passed:
        required = run_root / "private-receipt.json"
        required.write_text("{\"passed\":true}\n", encoding="utf-8")
        required.chmod(0o600)
        receipt["receipts"] = [
            {
                "receipt_id": "private-proof",
                "visibility": "private",
                "path": str(required),
                "sha256": "sha256:" + "2" * 64,
                "size_bytes": required.stat().st_size,
            }
        ]
    _write_json(run_root / "execution-receipt.json", receipt, mode=0o600)
    _write_json(
        run_root / "run-state.json",
        {
            "schema_version": "abyss_mcp_protocol_watch_run_state_v1",
            "run_id": run_id,
            "state": state or ("completed" if passed else "failed"),
            "started_at": (finished_at - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
        },
        mode=0o600,
    )
    if include_disposable:
        (run_root / "stable-home").mkdir(mode=0o700)
        (run_root / "stable-home" / "clone.txt").write_bytes(b"clone-data\n")
        (run_root / "step-logs").mkdir(mode=0o700)
        (run_root / "step-logs" / "bounded-lab.stdout").write_bytes(b"diagnostic\n")
    return run_root


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


def test_normal_watcher_can_apply_retention_without_changing_lab_verdict(
    tmp_path: Path,
) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    _retention_plan(plan_path, max_successful_runs=1)
    protected = tmp_path / "production-config.toml"
    protected.write_text("stable\n", encoding="utf-8")
    runtime = _runtime(tmp_path, protected)

    result = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=runtime,
        execute=True,
        offline=False,
        timeout=5,
        apply_retention=True,
        now=now,
    )

    assert result["execution_state"] == "lab_passed"
    assert result["retention"]["mode"] == "applied"
    assert result["retention"]["errors"] == []
    assert result["retention"]["skipped_operations"] == 0
    assert (state_root / "retention-apply.json").is_file()
    public = json.loads((state_root / "public-safe.json").read_text())
    assert public["retention"]["mode"] == "applied"
    assert public["verdicts"] == result["verdicts"]


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


def test_ttl_due_remains_explicit_after_a_successful_lab_refresh(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path, expires_in=timedelta(hours=2))
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
        now=now + timedelta(hours=3),
    )
    third = watcher.run(
        plan_path=plan_path,
        state_root=state_root,
        runtime_config=None,
        execute=False,
        offline=False,
        timeout=5,
        now=now + timedelta(hours=3, minutes=1),
    )

    assert first["execution_state"] == "lab_passed"
    assert second["execution_state"] == "lab_passed"
    assert second["trigger_reasons"] == ["evidence_ttl_due"]
    assert third["trigger_reasons"] == ["evidence_ttl_due"]
    assert json.loads((state_root / "last-success.json").read_text())["run_id"] == second["run_id"]


def test_retention_dry_run_and_apply_archive_old_run_preserves_receipts(
    tmp_path: Path,
) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(plan_path, max_successful_runs=1)
    old_id = "20260801T120000.000000Z"
    current_id = "20260808T110000.000000Z"
    old_root = _write_run(state_root, old_id, now - timedelta(days=7))
    current_root = _write_run(state_root, current_id, now - timedelta(hours=1))
    _write_json(
        state_root / "last-success.json",
        {
            "schema_version": "abyss_mcp_protocol_watch_success_v1",
            "run_id": current_id,
            "input_snapshot_digest": "sha256:" + "3" * 64,
        },
        mode=0o600,
    )
    required_payload = (old_root / "private-receipt.json").read_bytes()

    dry_run = watcher._retention_plan(state_root, plan, now=now)
    operations = dry_run["operations"]
    old_actions = [item["action"] for item in operations if item.get("run_id") == old_id]

    assert old_actions == ["archive_run", "remove_run"]
    assert all(item.get("run_id") != current_id for item in operations)
    assert old_root.is_dir()
    assert dry_run["summary"]["run_removal_candidate_bytes"] > 0
    assert dry_run["summary"]["run_removal_candidate_logical_bytes"] > 0

    applied = watcher._apply_retention(state_root, plan, now=now)

    assert applied["errors"] == []
    assert applied["skipped_operations"] == 0
    assert not old_root.exists()
    assert current_root.is_dir()
    archive = state_root / "retained-receipts" / old_id
    assert archive.is_dir()
    assert (archive / "input-snapshot.json").is_file()
    assert (archive / "execution-receipt.json").is_file()
    assert (archive / "required" / "000-private-receipt.json").read_bytes() == required_payload

    archive_plan = _retention_plan(
        plan_path,
        max_successful_runs=0,
        max_failed_runs=0,
        retain_failed_diagnostics=0,
    )
    archive_preview = watcher._retention_plan(state_root, archive_plan, now=now)
    assert archive_preview["summary"]["archive_budget_warning"] is True
    assert archive_preview["warnings"] == [
        "receipt_archives_preserved_without_default_expiry"
    ]
    assert not any(item["action"] == "remove_archive" for item in archive_preview["operations"])


def test_retention_prunes_only_declared_disposable_roots_and_keeps_compact_run(
    tmp_path: Path,
) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(plan_path, max_successful_runs=2)
    kept_id = "20260808T100000.000000Z"
    protected_id = "20260808T110000.000000Z"
    kept_root = _write_run(state_root, kept_id, now - timedelta(hours=2))
    _write_run(state_root, protected_id, now - timedelta(hours=1))
    cache = kept_root / "stable-home" / ".tmp" / "plugins"
    cache.mkdir(parents=True, mode=0o700)
    (cache / "cache.db").write_bytes(b"cache\n")
    _write_json(
        state_root / "last-success.json",
        {"run_id": protected_id},
        mode=0o600,
    )

    dry_run = watcher._retention_plan(state_root, plan, now=now)
    disposable = [
        item
        for item in dry_run["operations"]
        if item.get("run_id") == kept_id and item["action"] == "remove_disposable"
    ]
    assert {item["relative_path"] for item in disposable} == {
        f"runs/{kept_id}/stable-home",
        f"runs/{kept_id}/step-logs",
    }
    kept_view = next(item for item in dry_run["runs"] if item["run_id"] == kept_id)
    assert kept_view["cache_allocated_bytes"] > 0
    assert dry_run["summary"]["disposable_candidate_cache_allocated_bytes"] > 0
    assert all(item.get("run_id") != protected_id for item in dry_run["operations"])

    applied = watcher._apply_retention(state_root, plan, now=now)

    assert applied["errors"] == []
    assert not (kept_root / "stable-home").exists()
    assert not (kept_root / "step-logs").exists()
    assert (kept_root / "input-snapshot.json").is_file()
    assert (kept_root / "execution-receipt.json").is_file()
    assert (state_root / "runs" / protected_id / "stable-home").is_dir()


def test_retention_fail_closed_for_running_pinned_and_unsafe_roots(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(
        plan_path,
        max_successful_runs=0,
        max_failed_runs=0,
        retain_failed_diagnostics=0,
    )
    running_id = "20260808T100000.000000Z"
    pinned_id = "20260808T101000.000000Z"
    unsafe_id = "20260808T102000.000000Z"
    _write_run(state_root, running_id, now - timedelta(hours=3), state="running")
    _write_run(state_root, pinned_id, now - timedelta(hours=2))
    unsafe_root = _write_run(state_root, unsafe_id, now - timedelta(hours=1))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "do-not-touch").write_text("outside\n", encoding="utf-8")
    (unsafe_root / "stable-home" / "managed-link").symlink_to(outside / "do-not-touch")
    os.mkfifo(unsafe_root / "stable-home" / "unexpected-fifo")
    _write_json(
        state_root / "pinned-runs.json",
        {"run_ids": [pinned_id]},
        mode=0o600,
    )

    dry_run = watcher._retention_plan(state_root, plan, now=now)

    assert all(item.get("run_id") != running_id for item in dry_run["operations"])
    assert all(item.get("run_id") != pinned_id for item in dry_run["operations"])
    unsafe_view = next(item for item in dry_run["runs"] if item["run_id"] == unsafe_id)
    assert unsafe_view["safe"] is False
    assert unsafe_view["retention_action"] == "blocked_required_or_unsafe"
    assert all(item.get("run_id") != unsafe_id for item in dry_run["operations"])
    assert (outside / "do-not-touch").exists()


def test_tree_measure_reports_allocated_bytes_once_per_inode(tmp_path: Path) -> None:
    watcher = _load_watcher()
    root = tmp_path / "tree"
    root.mkdir()
    payload = root / "one"
    payload.write_bytes(b"x" * 4096)
    (root / "two").hardlink_to(payload)

    measured = watcher._tree_measure(root, owner_uid=__import__("os").getuid())
    file_info = payload.lstat()
    root_info = root.lstat()
    expected_allocated = (file_info.st_blocks + root_info.st_blocks) * 512

    assert measured["logical_bytes"] == 4096
    assert measured["allocated_bytes"] == expected_allocated


def test_tree_measure_does_not_follow_owner_child_symlinks(tmp_path: Path) -> None:
    watcher = _load_watcher()
    root = tmp_path / "tree"
    root.mkdir()
    target = tmp_path / "outside"
    target.write_bytes(b"outside\n")
    (root / "managed-link").symlink_to(target)

    measured = watcher._tree_measure(root, owner_uid=os.getuid())

    assert measured["safe"] is True
    assert measured["files"] == 0
    assert target.read_bytes() == b"outside\n"


def test_tree_measure_rejects_foreign_root_with_stable_shape(tmp_path: Path) -> None:
    watcher = _load_watcher()
    root = tmp_path / "foreign"
    root.mkdir()
    (root / "large-file").write_bytes(b"should not be traversed\n")

    measured = watcher._tree_measure(root, owner_uid=os.getuid() + 1)

    assert measured["safe"] is False
    assert measured["error_class"] == "foreign_owner"
    assert measured["files"] == 0
    assert isinstance(measured["allocated_bytes"], int)


def test_tree_measure_rejects_mountpoint_ancestor_before_traversal(
    tmp_path: Path, monkeypatch: Any
) -> None:
    watcher = _load_watcher()
    state_root = tmp_path / "state"
    runs_root = state_root / "runs"
    run_root = runs_root / "20260808T100000.000000Z"
    run_root.mkdir(parents=True)
    (run_root / "receipt").write_text("receipt\n", encoding="utf-8")
    monkeypatch.setattr(watcher, "_mount_points", lambda: {str(runs_root)})

    measured = watcher._tree_measure(
        run_root,
        owner_uid=os.getuid(),
        boundary_root=state_root,
    )

    assert measured["safe"] is False
    assert "mount_boundary" in measured["error_classes"]


def test_retention_blocks_when_mountinfo_is_unavailable(tmp_path: Path, monkeypatch: Any) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(plan_path, max_successful_runs=0)
    _write_run(state_root, "20260808T100000.000000Z", now - timedelta(days=2))
    monkeypatch.setattr(
        watcher,
        "_mount_points",
        lambda: (_ for _ in ()).throw(watcher._MountInfoError("mountinfo_unavailable")),
    )

    preview = watcher._retention_plan(state_root, plan, now=now)

    assert preview["blocked"] == ["mountinfo_unavailable"]
    assert preview["operations"] == []


def test_retention_plan_does_not_create_or_chmod_state(tmp_path: Path, monkeypatch: Any) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    missing_root = tmp_path / "missing-state"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "protocol_watcher.py",
            "--plan",
            str(plan_path),
            "--state-root",
            str(missing_root),
            "--retention-plan",
        ],
    )

    assert watcher.main() == 0
    assert not missing_root.exists()

    state_root.mkdir(mode=0o755)
    lock = state_root / ".lock"
    lock.write_text("existing\n", encoding="utf-8")
    lock.chmod(0o644)
    root_mode = state_root.stat().st_mode & 0o777
    lock_mode = lock.stat().st_mode & 0o777
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "protocol_watcher.py",
            "--plan",
            str(plan_path),
            "--state-root",
            str(state_root),
            "--retention-plan",
        ],
    )

    assert watcher.main() == 0
    assert state_root.stat().st_mode & 0o777 == root_mode
    assert lock.stat().st_mode & 0o777 == lock_mode


def test_proc_scan_protects_same_user_run_cwd_and_fd(tmp_path: Path) -> None:
    watcher = _load_watcher()
    run_root = tmp_path / "runs" / "20260808T100000.000000Z"
    (run_root / "fd-target").mkdir(parents=True)
    proc_root = tmp_path / "proc"
    process = proc_root / "123" / "fd"
    process.mkdir(parents=True)
    (proc_root / "123" / "status").write_text(
        f"Name:\tchild\nUid:\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\n"
    )
    (proc_root / "123" / "cwd").symlink_to(run_root, target_is_directory=True)
    (process / "4").symlink_to(run_root / "fd-target")

    references, error = watcher._proc_run_references(
        [{"run_id": run_root.name, "path": run_root}],
        owner_uid=os.getuid(),
        proc_root=proc_root,
    )

    assert error is None
    assert references[run_root.name] == ["proc:123/cwd", "proc:123/4"]


def test_proc_scan_indexes_siblings_without_prefix_false_positive(tmp_path: Path) -> None:
    watcher = _load_watcher()
    runs_root = tmp_path / "runs"
    selected_id = "20260808T100000.000000Z"
    sibling_id = "20260808T100001.000000Z"
    other_id = "20260808T100002.000000Z"
    selected = runs_root / selected_id
    sibling = runs_root / sibling_id
    other = runs_root / other_id
    for run_root in (selected, sibling, other):
        (run_root / "nested").mkdir(parents=True)

    proc_root = tmp_path / "proc"
    process = proc_root / "123" / "fd"
    process.mkdir(parents=True)
    (proc_root / "123" / "status").write_text(
        f"Name:\tchild\nUid:\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\t{os.getuid()}\n"
    )
    (proc_root / "123" / "cwd").symlink_to(selected / "nested", target_is_directory=True)
    # This path shares the selected run's lexical prefix but is a sibling.
    (process / "4").symlink_to(
        runs_root / f"{selected_id}-review",
        target_is_directory=True,
    )
    (process / "5").symlink_to(other / "nested", target_is_directory=True)

    references, error = watcher._proc_run_references(
        [
            {"run_id": selected_id, "path": selected},
            {"run_id": sibling_id, "path": sibling},
            {"run_id": other_id, "path": other},
        ],
        owner_uid=os.getuid(),
        proc_root=proc_root,
    )

    assert error is None
    assert references == {
        selected_id: ["proc:123/cwd"],
        other_id: ["proc:123/5"],
    }


def test_retention_protects_run_referenced_by_proc_scan(tmp_path: Path, monkeypatch: Any) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(plan_path, max_successful_runs=0)
    run_id = "20260808T100000.000000Z"
    run_root = _write_run(state_root, run_id, now - timedelta(days=2))
    monkeypatch.setattr(
        watcher,
        "_proc_run_references",
        lambda records, owner_uid: ({run_id: ["proc:123/cwd"]}, None),
    )

    preview = watcher._retention_plan(state_root, plan, now=now)
    view = next(item for item in preview["runs"] if item["run_id"] == run_id)

    assert view["retention_action"] == "protect_reference"
    assert view["proc_references"] == ["proc:123/cwd"]
    assert not any(item.get("run_id") == run_id for item in preview["operations"])
    assert run_root.is_dir()


def test_retention_blocks_whole_run_with_unknown_top_level(tmp_path: Path) -> None:
    watcher = _load_watcher()
    plan_path, state_root, now = _fixture(tmp_path)
    plan = _retention_plan(plan_path, max_successful_runs=0)
    run_id = "20260808T100000.000000Z"
    run_root = _write_run(state_root, run_id, now - timedelta(days=2))
    (run_root / "unclassified-result").write_text("keep for review\n", encoding="utf-8")

    preview = watcher._retention_plan(state_root, plan, now=now)
    view = next(item for item in preview["runs"] if item["run_id"] == run_id)

    assert view["unknown_top_level"] == ["unclassified-result"]
    assert view["retention_action"] == "blocked_unknown_top_level"
    assert not any(item.get("run_id") == run_id for item in preview["operations"])
