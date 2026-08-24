from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
MODULE_PATH = (
    REPO_ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "deployment-route"
    / "aoa_deploy_owner_package.py"
)
SPEC = importlib.util.spec_from_file_location("aoa_deploy_owner_package", MODULE_PATH)
assert SPEC and SPEC.loader
ROUTE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ROUTE)


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def create_repo(root: Path) -> tuple[str, str]:
    root.mkdir()
    run_git(root, "init", "--initial-branch=main", "-q")
    run_git(root, "config", "user.email", "route-tests@example.invalid")
    run_git(root, "config", "user.name", "route tests")
    (root / "payload.txt").write_text("one\n", encoding="utf-8")
    run_git(root, "add", "payload.txt")
    run_git(root, "commit", "-qm", "initial")
    return run_git(root, "rev-parse", "HEAD"), run_git(root, "rev-parse", "HEAD^{tree}")


def commit_repo(root: Path, value: str) -> tuple[str, str]:
    (root / "payload.txt").write_text(value, encoding="utf-8")
    run_git(root, "add", "payload.txt")
    run_git(root, "commit", "-qm", "next")
    return run_git(root, "rev-parse", "HEAD"), run_git(root, "rev-parse", "HEAD^{tree}")


def write_admission(
    root: Path,
    *,
    source: Path,
    ref: str,
    tree: str,
    destination: Path,
    expires: datetime | None = None,
    name: str = "admission.json",
) -> Path:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "schema_version": ROUTE.ADMISSION_SCHEMA,
        "admission_kind": ROUTE.SOURCE_ROUTE_ADMISSION_KIND,
        "status": "admitted",
        "admission_id": f"test-admission-{name}",
        "admission_ref": f"test://{name}",
        "owner_repo": "aoa-stats",
        "source_root": str(source.resolve()),
        "source_ref": ref,
        "source_tree": tree,
        "destination": str(destination.absolute()),
        "authority_ceiling": "disposable-source-package-canary",
        "issued_at": ROUTE._iso(now - timedelta(seconds=1)),
        "expires_at": ROUTE._iso(expires or now + timedelta(hours=1)),
    }
    path = root / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def invoke(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def route_fixture(tmp_path: Path) -> dict[str, Path | str]:
    source = tmp_path / "source"
    ref, tree = create_repo(source)
    destination = tmp_path / "installed" / "aoa-stats"
    destination.parent.mkdir(parents=True, exist_ok=True)
    release_root = tmp_path / "releases" / "aoa-stats"
    receipt_dir = tmp_path / "receipts"
    admission = write_admission(
        tmp_path,
        source=source,
        ref=ref,
        tree=tree,
        destination=destination,
    )
    return {
        "source": source,
        "ref": ref,
        "tree": tree,
        "destination": destination,
        "release_root": release_root,
        "receipt_dir": receipt_dir,
        "admission": admission,
    }


def prepare_command(fixture: dict[str, Path | str], *extra: str) -> list[str]:
    return [
        "prepare",
        "--owner-repo",
        "aoa-stats",
        "--source-root",
        str(fixture["source"]),
        "--source-ref",
        str(fixture["ref"]),
        "--source-tree",
        str(fixture["tree"]),
        "--destination",
        str(fixture["destination"]),
        "--release-root",
        str(fixture["release_root"]),
        "--receipt-dir",
        str(fixture["receipt_dir"]),
        "--admission-receipt",
        str(fixture["admission"]),
        *extra,
    ]


def output(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_dry_run_is_source_only_and_creates_no_route_state(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    result = invoke(*prepare_command(fixture, "--dry-run"))
    payload = output(result)

    assert payload["status"] == "dry_run"
    assert payload["dependency_posture"] == "source_only_no_install"
    assert payload["effects"] == []
    assert not Path(fixture["release_root"]).exists()
    assert not Path(fixture["receipt_dir"]).exists()
    assert not Path(fixture["destination"]).exists()


def test_prepare_activate_and_rollback_preserve_predecessor(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    first_prepare = output(invoke(*prepare_command(fixture)))
    first_activate = output(invoke("activate", "--prepare-receipt", first_prepare["receipt_path"]))
    first_release = Path(first_prepare["release_path"])
    assert Path(fixture["destination"]).is_symlink()
    assert Path(fixture["destination"]).resolve() == first_release

    ref, tree = commit_repo(Path(fixture["source"]), "two\n")
    fixture["ref"] = ref
    fixture["tree"] = tree
    fixture["admission"] = write_admission(
        tmp_path,
        source=Path(fixture["source"]),
        ref=ref,
        tree=tree,
        destination=Path(fixture["destination"]),
        name="second-admission.json",
    )
    second_prepare = output(invoke(*prepare_command(fixture)))
    assert second_prepare["predecessor"]["target"] == str(first_release)
    second_activate = output(invoke("activate", "--prepare-receipt", second_prepare["receipt_path"]))
    second_release = Path(second_prepare["release_path"])
    assert Path(fixture["destination"]).resolve() == second_release
    assert first_release.is_dir()
    assert second_activate["claim_ceiling"] == "source_activation_only_no_runtime_claim"

    rolled_back = output(invoke("rollback", "--activation-receipt", second_activate["receipt_path"]))
    assert rolled_back["status"] == "rolled_back"
    assert Path(fixture["destination"]).resolve() == first_release
    assert first_release.is_dir()
    assert second_release.is_dir()


def test_dirty_source_fails_closed_before_staging(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    Path(fixture["source"], "untracked.txt").write_text("dirty\n", encoding="utf-8")
    result = invoke(*prepare_command(fixture))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "dirty_source"
    assert not Path(fixture["release_root"]).exists()


def test_stale_admission_fails_closed(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    fixture["admission"] = write_admission(
        tmp_path,
        source=Path(fixture["source"]),
        ref=str(fixture["ref"]),
        tree=str(fixture["tree"]),
        destination=Path(fixture["destination"]),
        expires=datetime.now(timezone.utc) - timedelta(seconds=1),
        name="stale.json",
    )
    result = invoke(*prepare_command(fixture, "--dry-run"))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "admission_stale"


def test_wrong_source_identity_fails_closed(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    result = invoke(
        *prepare_command(
            fixture,
            "--source-ref",
            "0" * 40,
            "--dry-run",
        )
    )

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "source_ref_mismatch"


def test_incomplete_staging_and_non_symlink_destination_are_rejected(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    release_root = Path(fixture["release_root"])
    release_root.parent.mkdir(parents=True)
    (release_root.parent / ".aoa-stats-stale-staging").mkdir()
    result = invoke(*prepare_command(fixture, "--dry-run"))
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "incomplete_staging"

    (release_root.parent / ".aoa-stats-stale-staging").rmdir()
    Path(fixture["destination"]).mkdir(parents=True)
    result = invoke(*prepare_command(fixture, "--dry-run"))
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "destination_not_atomic_switchable"


def test_concurrent_lock_is_rejected(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    release_root = Path(fixture["release_root"])
    release_root.parent.mkdir(parents=True)
    lock_path = release_root.parent / ".aoa-stats.deployment.lock"
    import fcntl

    with lock_path.open("w+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = invoke(*prepare_command(fixture))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "concurrent_deployment"


def test_activation_rejects_destination_race_and_receipt_tampering(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    destination = Path(fixture["destination"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    other_release = Path(fixture["release_root"]) / "external-release"
    shutil.copytree(Path(prepared["release_path"]), other_release, symlinks=True)
    destination.symlink_to(other_release)
    result = invoke("activate", "--prepare-receipt", prepared["receipt_path"])
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "concurrent_deployment"

    payload = json.loads(Path(prepared["receipt_path"]).read_text(encoding="utf-8"))
    payload["claim_ceiling"] = "tampered"
    Path(prepared["receipt_path"]).write_text(json.dumps(payload), encoding="utf-8")
    result = invoke("activate", "--prepare-receipt", prepared["receipt_path"])
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "receipt_digest_mismatch"


def test_cross_device_preflight_is_rejected_when_tmpfs_is_distinct(tmp_path: Path) -> None:
    destination_parent = tmp_path / "installed"
    destination_parent.mkdir()
    if destination_parent.stat().st_dev == Path("/dev/shm").stat().st_dev:
        pytest.skip("/dev/shm is not a distinct filesystem on this host")
    fixture = route_fixture(tmp_path)
    fixture["release_root"] = Path("/dev/shm") / f"aoa-route-{tmp_path.name}" / "releases"
    fixture["destination"] = destination_parent / "aoa-stats"
    fixture["admission"] = write_admission(
        tmp_path,
        source=Path(fixture["source"]),
        ref=str(fixture["ref"]),
        tree=str(fixture["tree"]),
        destination=Path(fixture["destination"]),
        name="cross-device.json",
    )
    result = invoke(*prepare_command(fixture, "--dry-run"))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "cross_device_route"
