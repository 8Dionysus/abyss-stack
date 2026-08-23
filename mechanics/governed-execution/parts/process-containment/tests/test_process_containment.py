from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PART_ROOT / "contained_invocation.py"
SPEC = importlib.util.spec_from_file_location("process_containment_test_api", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
containment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = containment
SPEC.loader.exec_module(containment)


def _spec(tmp_path: Path, command: tuple[str, ...]) -> object:
    return containment.ContainmentSpec(
        profile_id="test-profile",
        source_root=containment.ReadOnlyRoot(Path(__file__).resolve().parents[5], "/workspace"),
        runtime_roots=(
            containment.ReadOnlyRoot(Path(sys.prefix), sys.prefix),
            containment.ReadOnlyRoot(Path("/lib64"), "/lib64"),
            containment.ReadOnlyRoot(Path("/lib"), "/lib"),
            containment.ReadOnlyRoot(Path("/etc"), "/etc"),
        ),
        command=command,
        environment={"PATH": "/runtime/bin:/usr/bin"},
        export_root=tmp_path / "export",
        drain_timeout_seconds=1.0,
        termination_grace_seconds=0.2,
    )


def test_backend_rejects_external_temp_redirection_before_launch(tmp_path: Path) -> None:
    spec = _spec(tmp_path, (sys.executable, "-c", "raise SystemExit(99)"))
    spec = containment.ContainmentSpec(
        **{**spec.__dict__, "environment": {"TMPDIR": "/host/temp"}},
    )
    result = containment.run_contained(spec)
    assert result.status == "containment_unsupported"
    assert result.command_started is False
    assert result.returncode == 125


def test_namespace_init_reaps_sets_id_and_double_fork_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = (
        "import os,signal\n"
        "ready_r,ready_w=os.pipe()\n"
        "hold_r,hold_w=os.pipe()\n"
        "child=os.fork()\n"
        "if child == 0:\n"
        "  os.close(ready_r); os.close(hold_w); os.setsid()\n"
        "  grand=os.fork()\n"
        "  if grand == 0:\n"
        "    great=os.fork()\n"
        "    if great == 0:\n"
        "      os.close(ready_w)\n"
        "      signal.signal(signal.SIGTERM, lambda *_: os._exit(0))\n"
        "      os.fstat(hold_r)\n"
        "      signal.pause()\n"
        "    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))\n"
        "    signal.pause()\n"
        "  os.write(ready_w,b'1'); os.close(ready_w); os._exit(0)\n"
        "os.close(ready_w)\n"
        "assert os.read(ready_r,1)==b'1'\n"
        "os.close(ready_r); os.close(hold_r); os.close(hold_w)\n"
        "os.waitpid(child,0)\n"
    )
    # The readiness pipe makes nested setup deterministic.  The supervisor
    # must still adopt the setsid/double-fork descendants after the main
    # command exits and drain their retained descriptor tree.
    spec = _spec(tmp_path, (sys.executable, "-c", program))
    result = containment.run_contained(spec)
    if result.status == "containment_unsupported":
        # The current host intentionally fails the real same-UID probe.  A
        # deterministic admission mock still exercises the namespace/PID-1
        # lifecycle without presenting it as live adversarial proof.
        launcher = containment._launcher_module()
        monkeypatch.setattr(
            launcher,
            "_same_uid_admission_probe",
            lambda _pid: {"checks": {}, "supported": True, "violations": []},
        )
        result = launcher.run_contained(spec, result_factory=containment.ContainmentResult)
    assert result.status == "completed"
    receipt = result.receipt["receipt"]
    assert receipt["drain_complete"] is True
    assert receipt["live_descendants"] == []
    assert receipt["main_starttime"] is not None
    assert set(receipt["namespace_identity"]) == {"user", "pid", "mnt"}
    assert receipt["host_path_deletion_authority"] is False
    assert receipt["numeric_pgid_authority"] is False


def test_namespace_init_terminates_retained_fd_descendant_and_reports_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = (
        "import os,signal,time\n"
        "r,w=os.pipe()\n"
        "p=os.fork()\n"
        "if p == 0:\n"
        "  os.close(w)\n"
        "  signal.pause()\n"
        "os.close(r)\n"
        "os.close(w)\n"
        "os._exit(0)\n"
    )
    spec = _spec(tmp_path, (sys.executable, "-c", program))
    result = containment.run_contained(spec)
    if result.status == "containment_unsupported":
        launcher = containment._launcher_module()
        monkeypatch.setattr(
            launcher,
            "_same_uid_admission_probe",
            lambda _pid: {"checks": {}, "supported": True, "violations": []},
        )
        result = launcher.run_contained(spec, result_factory=containment.ContainmentResult)
    assert result.status == "completed"
    receipt = result.receipt["receipt"]
    assert receipt["drain_complete"] is True
    assert receipt["live_descendants"] == []
    assert receipt["main_starttime"] is not None
    assert receipt["storage_reclaim"] == "namespace_teardown_only"


def test_bwrap_command_contains_only_read_only_host_binds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        os,
        "get_inheritable",
        lambda fd: False,
    )
    launcher = containment._launcher_module()
    spec = _spec(tmp_path, (sys.executable, "-c", "pass"))
    admission = launcher._validate_spec(spec)
    command = launcher._build_command(admission, spec)
    assert "--bind" not in command
    assert "--ro-bind" in command
    assert command.count("--tmpfs") >= 3
    assert "--proc" in command
    assert "--unshare-pid" in command
    assert "--as-pid-1" in command


def test_teardown_receipt_does_not_use_host_unlink_or_rmdir(tmp_path: Path) -> None:
    text = (PART_ROOT / "namespace_launcher.py").read_text(encoding="utf-8")
    assert "os.unlink" not in text
    assert "os.rmdir" not in text
    assert "namespace_teardown_only" in text
    assert not list((tmp_path / "export").glob(".entry-*"))


def test_private_tmpfs_teardown_does_not_change_host_inode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    host_marker = tmp_path / "host-marker"
    host_marker.write_text("host-owned", encoding="utf-8")
    before = host_marker.stat()
    launcher = containment._launcher_module()
    monkeypatch.setattr(
        launcher,
        "_same_uid_admission_probe",
        lambda _pid: {"checks": {}, "supported": True, "violations": []},
    )
    spec = _spec(
        tmp_path,
        (
            sys.executable,
            "-c",
            "from pathlib import Path; Path('/tmp/private-invocation-byte').write_text('private')",
        ),
    )
    result = launcher.run_contained(spec, result_factory=containment.ContainmentResult)
    assert result.status == "completed"
    after = host_marker.stat()
    assert (after.st_ino, after.st_size, after.st_mtime_ns) == (
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    assert not (tmp_path / "private-invocation-byte").exists()


def test_hidden_recovery_residue_cannot_be_reported_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = containment._launcher_module()
    monkeypatch.setattr(
        launcher,
        "_same_uid_admission_probe",
        lambda _pid: {"checks": {}, "supported": True, "violations": []},
    )
    spec = _spec(
        tmp_path,
        (
            sys.executable,
            "-c",
            "from pathlib import Path; Path('/tmp/.entry-test-residue').write_text('hidden')",
        ),
    )
    result = launcher.run_contained(spec, result_factory=containment.ContainmentResult)
    assert result.status == "infrastructure_failure"
    assert result.receipt["receipt"]["hidden_residue"]


def test_same_uid_procfs_admission_is_explicit_and_fail_closed(tmp_path: Path) -> None:
    result = containment.run_contained(
        _spec(tmp_path, (sys.executable, "-c", "raise SystemExit(0)")),
    )
    if result.status == "containment_unsupported":
        admission = result.receipt.get("same_uid_admission", {})
        assert admission.get("supported") is False
        checks = admission.get("checks", {})
        assert {"proc_root", "proc_fd", "setns_user", "setns_pid", "setns_mnt"} <= set(checks)
        assert result.command_started is False
        assert result.receipt["receipt"]["command_started"] is False
        return
    assert result.status == "completed"
    assert result.command_started is True
    assert result.receipt["same_uid_admission"]["supported"] is True


def test_export_failure_is_visible_recovery_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = containment._launcher_module()

    def fail_export(*_args: object, **_kwargs: object) -> None:
        raise launcher.ExportError("test export failure")

    monkeypatch.setattr(launcher, "_export", fail_export)
    result = launcher.run_contained(
        _spec(tmp_path, (sys.executable, "-c", "raise SystemExit(0)")),
        result_factory=containment.ContainmentResult,
    )
    assert result.status == "recovery_required"
    assert result.returncode == 126
    assert result.receipt["status"] == "recovery_required"
    assert "test export failure" in str(result.receipt["diagnostic"])
    assert result.receipt["recovery_lease"]["owner_controlled"] is True


def test_pidfd_capability_is_required_before_backend_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "pidfd_open", raising=False)
    result = containment.run_contained(_spec(tmp_path, (sys.executable, "-c", "raise SystemExit(41)")))
    assert result.status == "containment_unsupported"
    assert result.command_started is False
    assert any("pidfd_lifecycle_unavailable" in str(item) for item in result.diagnostics)


def test_mount_capability_validation_is_fail_closed() -> None:
    launcher = containment._launcher_module()
    with pytest.raises(OSError, match="required private tmpfs mount missing"):
        launcher._validate_mount_evidence({"/proc": {"matches": [{"filesystem": "proc"}]}})


def test_procfs_capability_validation_is_fail_closed() -> None:
    launcher = containment._launcher_module()
    evidence = {
        "/tmp": {"matches": [{"filesystem": "tmpfs"}]},
        "/var/tmp": {"matches": [{"filesystem": "tmpfs"}]},
        "/dev/shm": {"matches": [{"filesystem": "tmpfs"}]},
    }
    with pytest.raises(OSError, match="required private proc mount missing"):
        launcher._validate_mount_evidence(evidence)


def test_mapping_capability_validation_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = containment._launcher_module()
    original_read_text = launcher.Path.read_text

    def empty_uid_map(path: Path, *args: object, **kwargs: object) -> str:
        if str(path) == "/proc/self/uid_map":
            return ""
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(launcher.Path, "read_text", empty_uid_map)
    with pytest.raises(launcher.AdmissionError, match="user_mapping_empty"):
        launcher._validate_kernel_capabilities()


def test_bwrap_namespace_feature_admission_is_fail_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    launcher = containment._launcher_module()
    real_run = launcher.subprocess.run

    def missing_pid_feature(command: list[str], **kwargs: object) -> object:
        if command[-1] == "--version":
            return SimpleNamespace(stdout="bubblewrap test")
        if command[-1] == "--help":
            return SimpleNamespace(
                stdout="--unshare-user --as-pid-1 --ro-bind --tmpfs --proc --disable-userns"
            )
        return real_run(command, **kwargs)

    monkeypatch.setattr(launcher.subprocess, "run", missing_pid_feature)
    result = containment.run_contained(_spec(tmp_path, (sys.executable, "-c", "raise SystemExit(41)")))
    assert result.status == "containment_unsupported"
    assert result.command_started is False
    assert any("bubblewrap_features_missing" in str(item) for item in result.diagnostics)


def test_unsupported_backend_is_machine_readable_without_child_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launcher = containment._launcher_module()
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: None)
    result = containment.run_contained(_spec(tmp_path, (sys.executable, "-c", "raise SystemExit(41)")))
    assert result.status == "containment_unsupported"
    assert result.command_started is False
    assert result.diagnostics


def test_inheritable_external_fd_is_rejected(tmp_path: Path) -> None:
    fd = os.open(__file__, os.O_RDONLY)
    try:
        os.set_inheritable(fd, True)
        result = containment.run_contained(
            _spec(tmp_path, (sys.executable, "-c", "raise SystemExit(41)")),
        )
    finally:
        os.close(fd)
    assert result.status == "containment_unsupported"
    assert result.command_started is False
    assert any("undeclared_inherited_fds" in str(item) for item in result.diagnostics)
