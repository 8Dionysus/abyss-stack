from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

from jsonschema import Draft202012Validator, ValidationError
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
SCHEMA_ROOT = MODULE_PATH.parent / "schemas"
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


def validate_instance(path: Path, schema_name: str) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads((SCHEMA_ROOT / schema_name).read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    return payload


def make_release_writable(release: Path) -> None:
    for path in [release, *release.rglob("*")]:
        if path.is_symlink():
            continue
        os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | 0o222)


def direct_activate(prepared: dict[str, object]) -> dict[str, object]:
    return ROUTE.activate(argparse.Namespace(prepare_receipt=prepared["receipt_path"]))


def two_release_fixture(tmp_path: Path) -> tuple[dict[str, Path | str], Path, dict[str, object]]:
    fixture = route_fixture(tmp_path)
    first_prepare = output(invoke(*prepare_command(fixture)))
    first_activate = output(invoke("activate", "--prepare-receipt", first_prepare["receipt_path"]))
    first_release = Path(first_prepare["release_path"])
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
    second_activate = output(invoke("activate", "--prepare-receipt", second_prepare["receipt_path"]))
    assert first_activate["status"] == "activated"
    return fixture, first_release, second_activate


def test_dry_run_is_source_only_and_creates_no_route_state(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    result = invoke(*prepare_command(fixture, "--dry-run"))
    payload = output(result)

    admission_payload = json.loads(Path(fixture["admission"]).read_text(encoding="utf-8"))
    Draft202012Validator(
        json.loads((SCHEMA_ROOT / "admission.v1.json").read_text(encoding="utf-8"))
    ).validate(admission_payload)
    Draft202012Validator(
        json.loads((SCHEMA_ROOT / "prepare-receipt.v1.json").read_text(encoding="utf-8"))
    ).validate(payload)
    assert payload["status"] == "dry_run"
    assert payload["dependency_posture"] == "source_only_no_install"
    assert payload["effects"] == []
    assert not Path(fixture["release_root"]).exists()
    assert not Path(fixture["receipt_dir"]).exists()
    assert not Path(fixture["destination"]).exists()


def test_prepare_activate_and_rollback_preserve_predecessor(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    first_prepare = output(invoke(*prepare_command(fixture)))
    validate_instance(Path(first_prepare["receipt_path"]), "prepare-receipt.v1.json")
    first_activate = output(invoke("activate", "--prepare-receipt", first_prepare["receipt_path"]))
    validate_instance(Path(first_activate["receipt_path"]), "activate-receipt.v1.json")
    recovery_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    validate_instance(recovery_path, "recovery-receipt.v1.json")
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
    validate_instance(Path(second_activate["receipt_path"]), "activate-receipt.v1.json")
    validate_instance(Path(rolled_back["receipt_path"]), "rollback-receipt.v1.json")
    validate_instance(recovery_path, "recovery-receipt.v1.json")
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


def test_activation_revalidates_release_immediately_before_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    original_verify = ROUTE._verify_recorded_release
    mutated = False

    def mutate_after_first_verify(*args: object, **kwargs: object) -> object:
        nonlocal mutated
        result = original_verify(*args, **kwargs)
        if not mutated and kwargs.get("label") == "activated_release":
            mutated = True
            make_release_writable(release_path)
            (release_path / "payload.txt").write_text("non-cooperating writer\n", encoding="utf-8")
        return result

    monkeypatch.setattr(ROUTE, "_verify_recorded_release", mutate_after_first_verify)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    assert not os.path.lexists(fixture["destination"])
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "intent_written"
    assert "activation_receipt" not in journal


def test_activation_rolls_back_tracked_mutation_after_final_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    destination = Path(fixture["destination"])
    original_replace = ROUTE.os.replace
    fired = False

    def mutate_before_switch(source: Path, target: Path) -> None:
        nonlocal fired
        if not fired and Path(target) == destination:
            fired = True
            make_release_writable(release_path)
            (release_path / "payload.txt").write_text("late non-cooperating writer\n", encoding="utf-8")
        original_replace(source, target)

    monkeypatch.setattr(ROUTE.os, "replace", mutate_before_switch)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    assert not os.path.lexists(destination)
    assert fired is True
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = validate_instance(journal_path, "recovery-receipt.v1.json")
    assert journal["status"] == "rollback_switch_complete"
    assert "activation_receipt" not in journal
    assert not Path(journal["activation_receipt_path"]).exists()


def test_activation_finalization_rejects_mutation_after_post_switch_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    destination = Path(fixture["destination"])
    original_verify = ROUTE._verify_post_switch_state
    mutated = False

    def mutate_after_post_switch_verify(*args: object, **kwargs: object) -> object:
        nonlocal mutated
        result = original_verify(*args, **kwargs)
        if not mutated:
            mutated = True
            make_release_writable(release_path)
            (release_path / "payload.txt").write_text("mutation after final check\n", encoding="utf-8")
        return result

    monkeypatch.setattr(ROUTE, "_verify_post_switch_state", mutate_after_post_switch_verify)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    assert mutated is True
    assert not os.path.lexists(destination)
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = validate_instance(journal_path, "recovery-receipt.v1.json")
    assert journal["status"] == "rollback_switch_complete"
    assert "finalization" not in journal
    assert "activation_receipt" not in journal
    assert not Path(journal["activation_receipt_path"]).exists()


def test_post_switch_rollback_compare_and_swap_preserves_same_target_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    destination = Path(fixture["destination"])
    original_verify = ROUTE._verify_post_switch_state
    original_link_target = ROUTE._destination_link_target
    observed_identity: dict[str, object] = {}
    replaced = False

    def fail_after_post_switch_verify(*args: object, **kwargs: object) -> object:
        original_verify(*args, **kwargs)
        raise ROUTE.DeploymentError("injected_post_switch_failure", "test rollback CAS interleaving")

    def replace_after_rollback_observation(path: Path) -> Path:
        nonlocal replaced
        observed = original_link_target(path)
        if not replaced:
            replaced = True
            observed_identity.update(ROUTE._destination_identity(path))
            replacement = path.parent / f".{path.name}.same-target-writer"
            replacement.unlink(missing_ok=True)
            replacement.symlink_to(release_path)
            os.replace(replacement, path)
        return observed

    monkeypatch.setattr(ROUTE, "_verify_post_switch_state", fail_after_post_switch_verify)
    monkeypatch.setattr(ROUTE, "_destination_link_target", replace_after_rollback_observation)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    assert replaced is True
    assert destination.is_symlink()
    assert destination.resolve() == release_path
    assert ROUTE._destination_identity(destination)["inode"] != observed_identity["inode"]
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = validate_instance(journal_path, "recovery-receipt.v1.json")
    assert journal["status"] == "rollback_intent"
    assert "rollback_switch_complete_sha256" not in journal
    assert "activation_receipt" not in journal


def test_activation_rejects_same_ref_replacement_with_ignored_poison_after_final_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    source = Path(fixture["source"])
    (source / ".gitignore").write_text("ignored-cache/\n", encoding="utf-8")
    run_git(source, "add", ".gitignore")
    run_git(source, "commit", "-qm", "define ignored cache policy")
    fixture["ref"] = run_git(source, "rev-parse", "HEAD")
    fixture["tree"] = run_git(source, "rev-parse", "HEAD^{tree}")
    fixture["admission"] = write_admission(
        tmp_path,
        source=source,
        ref=str(fixture["ref"]),
        tree=str(fixture["tree"]),
        destination=Path(fixture["destination"]),
        name="same-ref-replacement-admission.json",
    )
    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    destination = Path(fixture["destination"])
    replacement = release_path.with_name(f"{release_path.name}.replacement")
    displaced = release_path.with_name(f"{release_path.name}.displaced")
    original_replace = ROUTE.os.replace
    fired = False

    def replace_with_ignored_poison(source_path: Path, target: Path) -> None:
        nonlocal fired
        if not fired and Path(target) == destination:
            fired = True
            shutil.copytree(release_path, replacement, symlinks=True)
            make_release_writable(replacement)
            poison = replacement / "ignored-cache" / "poison.txt"
            poison.parent.mkdir()
            poison.write_text("ignored poison\n", encoding="utf-8")
            ROUTE._set_release_read_only(replacement)
            original_replace(release_path, displaced)
            original_replace(replacement, release_path)
        original_replace(source_path, target)

    monkeypatch.setattr(ROUTE.os, "replace", replace_with_ignored_poison)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    assert not os.path.lexists(destination)
    assert fired is True
    assert (release_path / "ignored-cache" / "poison.txt").read_text(encoding="utf-8") == "ignored poison\n"
    assert run_git(release_path, "status", "--porcelain=v1") == ""
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = validate_instance(journal_path, "recovery-receipt.v1.json")
    assert journal["status"] == "rollback_switch_complete"
    assert "activation_receipt" not in journal
    assert not Path(journal["activation_receipt_path"]).exists()


def test_activation_rejects_predecessor_seal_drift(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    first_prepare = output(invoke(*prepare_command(fixture)))
    first_activate = output(invoke("activate", "--prepare-receipt", first_prepare["receipt_path"]))
    first_release = Path(first_prepare["release_path"])
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
    ROUTE._release_seal_path(first_release).unlink()

    result = invoke("activate", "--prepare-receipt", second_prepare["receipt_path"])

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "receipt_missing"
    assert Path(fixture["destination"]).resolve() == first_release
    assert first_activate["status"] == "activated"


def test_rollback_revalidates_recorded_predecessor_identity(tmp_path: Path) -> None:
    fixture, first_release, second_activate = two_release_fixture(tmp_path)
    make_release_writable(first_release)
    run_git(first_release, "config", "user.email", "tamper@example.invalid")
    run_git(first_release, "config", "user.name", "tamper")
    (first_release / "payload.txt").write_text("predecessor tamper\n", encoding="utf-8")
    run_git(first_release, "add", "payload.txt")
    run_git(first_release, "commit", "-qm", "tamper predecessor identity")

    result = invoke("rollback", "--activation-receipt", second_activate["receipt_path"])

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "predecessor_ref_mismatch"
    assert Path(fixture["destination"]).resolve() == Path(second_activate["activated_release"])


def test_rollback_revalidates_activated_release_identity(tmp_path: Path) -> None:
    fixture, _, second_activate = two_release_fixture(tmp_path)
    activated_release = Path(second_activate["activated_release"])
    make_release_writable(activated_release)
    run_git(activated_release, "config", "user.email", "tamper@example.invalid")
    run_git(activated_release, "config", "user.name", "tamper")
    (activated_release / "payload.txt").write_text("activated ref tamper\n", encoding="utf-8")
    run_git(activated_release, "add", "payload.txt")
    run_git(activated_release, "commit", "-qm", "tamper activated identity")

    result = invoke("rollback", "--activation-receipt", second_activate["receipt_path"])

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "activated_release_ref_mismatch"
    assert Path(fixture["destination"]).resolve() == activated_release


def test_rollback_rejects_dirty_activated_release(tmp_path: Path) -> None:
    fixture, _, second_activate = two_release_fixture(tmp_path)
    activated_release = Path(second_activate["activated_release"])
    make_release_writable(activated_release)
    (activated_release / "payload.txt").write_text("tampered\n", encoding="utf-8")

    result = invoke("rollback", "--activation-receipt", second_activate["receipt_path"])

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "activated_release_dirty"
    assert Path(fixture["destination"]).resolve() == activated_release


@pytest.mark.parametrize(
    ("tampered_field", "expected_code"),
    [("predecessor", "predecessor_tree_mismatch"), ("source", "activated_release_tree_mismatch")],
)
def test_rollback_rejects_tampered_recorded_tree(
    tmp_path: Path, tampered_field: str, expected_code: str
) -> None:
    fixture, _, second_activate = two_release_fixture(tmp_path)
    activation_path = Path(second_activate["receipt_path"])
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    activation.pop("receipt_digest")
    if tampered_field == "predecessor":
        activation["predecessor"]["source_tree"] = "0" * 40
    else:
        activation["source"]["tree"] = "0" * 40
    ROUTE._write_json(activation_path, activation)

    result = invoke("rollback", "--activation-receipt", str(activation_path))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == expected_code
    assert Path(fixture["destination"]).resolve() == Path(second_activate["activated_release"])


def test_ignored_cache_is_excluded_from_source_identity_and_package(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    source = Path(fixture["source"])
    (source / ".gitignore").write_text("ignored-cache/\n", encoding="utf-8")
    run_git(source, "add", ".gitignore")
    run_git(source, "commit", "-qm", "ignore local cache")
    ref = run_git(source, "rev-parse", "HEAD")
    tree = run_git(source, "rev-parse", "HEAD^{tree}")
    fixture["ref"] = ref
    fixture["tree"] = tree
    fixture["admission"] = write_admission(
        tmp_path,
        source=source,
        ref=ref,
        tree=tree,
        destination=Path(fixture["destination"]),
        name="ignored-cache-admission.json",
    )
    ignored = source / "ignored-cache"
    ignored.mkdir()
    (ignored / "cache.bin").write_text("cache\n", encoding="utf-8")
    assert "ignored-cache" in run_git(source, "status", "--porcelain=v1", "--ignored", "--untracked-files=all")

    prepared = output(invoke(*prepare_command(fixture)))
    release_path = Path(prepared["release_path"])
    assert not (release_path / "ignored-cache").exists()
    assert not (release_path / ".git" / "objects" / "info" / "alternates").exists()
    activated = output(invoke("activate", "--prepare-receipt", prepared["receipt_path"]))
    validate_instance(Path(activated["receipt_path"]), "activate-receipt.v1.json")
    assert Path(fixture["destination"]).resolve() == release_path


def test_tracked_mutation_is_not_hidden_by_ignored_cache_policy(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    (Path(fixture["source"]) / "payload.txt").write_text("tracked mutation\n", encoding="utf-8")

    result = invoke(*prepare_command(fixture, "--dry-run"))

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "dirty_source"


@pytest.mark.parametrize(
    "interruption",
    ["durable_intent", "switch", "switch_receipt", "activation_receipt", "final_journal"],
)
def test_activation_interruption_is_durable_and_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    original_write = ROUTE._write_json
    original_replace = ROUTE.os.replace
    fired = False

    def injected_write(path: Path, payload: dict[str, object]) -> dict[str, object]:
        nonlocal fired
        if (
            not fired
            and interruption == "final_journal"
            and path.name.endswith(".recovery.json")
            and payload.get("status") == "finalized"
        ):
            fired = True
            raise ROUTE.DeploymentError("injected_final_journal_write", "test interruption")
        result = original_write(path, payload)
        if fired:
            return result
        if interruption == "durable_intent" and path.name.endswith(".recovery.json") and payload.get("status") == "intent_written":
            fired = True
            raise ROUTE.DeploymentError("injected_after_intent", "test interruption")
        if interruption == "switch_receipt" and path.name.endswith(".recovery.json") and payload.get("status") == "switch_complete":
            fired = True
            raise ROUTE.DeploymentError("injected_after_switch_receipt", "test interruption")
        return result

    def injected_receipt_write(path: Path, payload: dict[str, object]) -> dict[str, object]:
        nonlocal fired
        if (
            not fired
            and interruption == "activation_receipt"
            and path.name.startswith("activate-")
            and not path.name.endswith(".recovery.json")
        ):
            fired = True
            raise ROUTE.DeploymentError("injected_activation_receipt_write", "test interruption")
        return original_write(path, payload)

    def injected_replace(source: Path, destination: Path) -> None:
        nonlocal fired
        if not fired and interruption == "switch" and Path(source).name.endswith(".switch"):
            fired = True
            raise OSError("injected switch interruption")
        original_replace(source, destination)

    if interruption == "activation_receipt":
        monkeypatch.setattr(ROUTE, "_write_json", injected_receipt_write)
    else:
        monkeypatch.setattr(ROUTE, "_write_json", injected_write)
    if interruption == "switch":
        monkeypatch.setattr(ROUTE.os, "replace", injected_replace)

    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)
    assert raised.value.code == "activation_recovery_required"
    assert raised.value.context["recovery_required"] is True
    journals = list(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    assert len(journals) == 1
    journal_path = journals[0]
    validate_instance(journal_path, "recovery-receipt.v1.json")

    if interruption in {"durable_intent", "switch"}:
        assert not os.path.lexists(fixture["destination"])
        rolled_back = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "rollback"))
        assert rolled_back["activation_receipt"]["status"] == "not_written"
    else:
        assert Path(fixture["destination"]).resolve() == Path(prepared["release_path"])
        finalized = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "finalize"))
        validate_instance(Path(finalized["receipt_path"]), "activate-receipt.v1.json")
        finalized_retry = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "finalize"))
        assert finalized_retry["receipt_path"] == finalized["receipt_path"]
        rolled_back = output(invoke("rollback", "--activation-receipt", finalized["receipt_path"]))

    validate_instance(Path(rolled_back["receipt_path"]), "rollback-receipt.v1.json")
    validate_instance(journal_path, "recovery-receipt.v1.json")
    retry = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "rollback"))
    assert retry["receipt_path"] == rolled_back["receipt_path"]


def test_recovery_finalization_uses_shared_admission_and_rolls_back_late_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    original_write = ROUTE._write_json
    interrupted = False

    def interrupt_after_switch_complete(path: Path, payload: dict[str, object]) -> dict[str, object]:
        nonlocal interrupted
        result = original_write(path, payload)
        if not interrupted and path.name.endswith(".recovery.json") and payload.get("status") == "switch_complete":
            interrupted = True
            raise ROUTE.DeploymentError("injected_switch_complete_boundary", "test recovery finalization boundary")
        return result

    monkeypatch.setattr(ROUTE, "_write_json", interrupt_after_switch_complete)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)
    assert raised.value.code == "activation_recovery_required"
    assert interrupted is True
    monkeypatch.undo()

    release_path = Path(prepared["release_path"])
    destination = Path(fixture["destination"])
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    validate_instance(journal_path, "recovery-receipt.v1.json")
    original_verify = ROUTE._verify_post_switch_state
    mutated = False

    def mutate_during_recovery_finalization(*args: object, **kwargs: object) -> object:
        nonlocal mutated
        result = original_verify(*args, **kwargs)
        if not mutated:
            mutated = True
            make_release_writable(release_path)
            (release_path / "payload.txt").write_text("mutation during recovery finalize\n", encoding="utf-8")
        return result

    monkeypatch.setattr(ROUTE, "_verify_post_switch_state", mutate_during_recovery_finalization)
    with pytest.raises(ROUTE.DeploymentError) as recovered:
        ROUTE._recover_finalize(journal_path)

    assert recovered.value.code == "activation_recovery_required"
    assert mutated is True
    assert not os.path.lexists(destination)
    journal = validate_instance(journal_path, "recovery-receipt.v1.json")
    assert journal["status"] == "rollback_switch_complete"
    assert "finalization" not in journal
    assert "activation_receipt" not in journal
    assert not Path(journal["activation_receipt_path"]).exists()


def test_rollback_receipt_persistence_failure_requires_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, first_release, second_activate = two_release_fixture(tmp_path)
    activation_path = Path(second_activate["receipt_path"])
    original_write = ROUTE._write_json
    fired = False

    def fail_rollback_receipt(path: Path, payload: dict[str, object]) -> dict[str, object]:
        nonlocal fired
        if not fired and path.name.startswith("rollback-") and not path.name.endswith(".recovery.json"):
            fired = True
            raise ROUTE.DeploymentError("injected_rollback_receipt_write", "test interruption")
        return original_write(path, payload)

    monkeypatch.setattr(ROUTE, "_write_json", fail_rollback_receipt)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        ROUTE.rollback(argparse.Namespace(activation_receipt=str(activation_path), receipt_dir=None))

    assert raised.value.code == "activation_recovery_required"
    journal_path = Path(second_activate["recovery_journal"]["path"])
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "rollback_switch_complete"
    assert "rollback_receipt" not in journal
    assert Path(fixture["destination"]).resolve() == first_release

    monkeypatch.undo()
    recovered = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "rollback"))
    validate_instance(Path(recovered["receipt_path"]), "rollback-receipt.v1.json")
    validate_instance(journal_path, "recovery-receipt.v1.json")


def test_directory_fsync_failure_fails_closed_before_receipt_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    destination_parent = Path(fixture["destination"]).parent
    original_fsync = ROUTE._fsync_directory
    fired = False

    def fail_destination_fsync(directory: Path) -> None:
        nonlocal fired
        if not fired and directory == destination_parent:
            fired = True
            raise OSError("injected directory fsync failure")
        original_fsync(directory)

    monkeypatch.setattr(ROUTE, "_fsync_directory", fail_destination_fsync)
    with pytest.raises(ROUTE.DeploymentError) as raised:
        direct_activate(prepared)

    assert raised.value.code == "activation_recovery_required"
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["status"] == "intent_written"
    assert "activation_receipt" not in journal
    monkeypatch.undo()
    rolled_back = output(invoke("recover", "--recovery-journal", str(journal_path), "--action", "rollback"))
    assert rolled_back["activation_receipt"]["status"] == "not_written"
    validate_instance(journal_path, "recovery-receipt.v1.json")


def test_tampered_recovery_journal_is_rejected_before_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    original_write = ROUTE._write_json

    def fail_after_intent(path: Path, payload: dict[str, object]) -> dict[str, object]:
        result = original_write(path, payload)
        if path.name.endswith(".recovery.json") and payload.get("status") == "intent_written":
            raise ROUTE.DeploymentError("injected_after_intent", "test interruption")
        return result

    monkeypatch.setattr(ROUTE, "_write_json", fail_after_intent)
    with pytest.raises(ROUTE.DeploymentError):
        direct_activate(prepared)
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    tampered = json.loads(journal_path.read_text(encoding="utf-8"))
    tampered["source"]["ref"] = "0" * 40
    journal_path.write_text(json.dumps(tampered), encoding="utf-8")

    result = invoke("recover", "--recovery-journal", str(journal_path), "--action", "finalize")

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "receipt_digest_mismatch"
    assert not os.path.lexists(fixture["destination"])


def test_recovery_status_references_are_exact_and_fail_closed(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    activated = output(invoke("activate", "--prepare-receipt", prepared["receipt_path"]))
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    recovery_schema = json.loads((SCHEMA_ROOT / "recovery-receipt.v1.json").read_text(encoding="utf-8"))

    for status, opposite in (
        ("intent_written", "activation_receipt"),
        ("switch_complete", "activation_receipt"),
        ("finalized", "rollback_receipt"),
        ("rolled_back", "activation_receipt"),
    ):
        malformed = deepcopy(journal)
        malformed["status"] = status
        if status in {"intent_written", "switch_complete"}:
            malformed[opposite] = deepcopy(journal["activation_receipt"])
        elif status == "finalized":
            malformed["rollback_receipt"] = deepcopy(journal["activation_receipt"])
        else:
            malformed["activation_receipt"] = deepcopy(journal["activation_receipt"])
        with pytest.raises(ValidationError):
            Draft202012Validator(recovery_schema).validate(malformed)

    malformed = deepcopy(journal)
    malformed.pop("activation_receipt")
    malformed["rollback_receipt"] = deepcopy(journal["activation_receipt"])
    ROUTE._write_json(journal_path, malformed)
    result = invoke("recover", "--recovery-journal", str(journal_path), "--action", "finalize")
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "recovery_record_invalid"
    assert Path(fixture["destination"]).resolve() == Path(activated["activated_release"])


def test_rollback_switch_complete_cannot_repair_activated_target(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    activated = output(invoke("activate", "--prepare-receipt", prepared["receipt_path"]))
    journal_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    journal = ROUTE._load_recovery_journal(journal_path)
    ROUTE._write_json(journal_path, ROUTE._rollback_switch_complete_payload(journal))

    result = invoke("recover", "--recovery-journal", str(journal_path), "--action", "rollback")

    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "recovery_state_unrecognized"
    assert Path(fixture["destination"]).resolve() == Path(activated["activated_release"])


def test_nested_receipt_contract_rejects_malformed_emitted_instances(tmp_path: Path) -> None:
    fixture = route_fixture(tmp_path)
    prepared = output(invoke(*prepare_command(fixture)))
    prepare_schema = json.loads((SCHEMA_ROOT / "prepare-receipt.v1.json").read_text(encoding="utf-8"))
    malformed_prepare = deepcopy(prepared)
    del malformed_prepare["source"]["tree"]
    with pytest.raises(ValidationError):
        Draft202012Validator(prepare_schema).validate(malformed_prepare)

    activated = output(invoke("activate", "--prepare-receipt", prepared["receipt_path"]))
    recovery_path = next(Path(fixture["receipt_dir"]).glob("activate-*.recovery.json"))
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    recovery["atomicity"]["switch"] = "non-atomic"
    recovery_schema = json.loads((SCHEMA_ROOT / "recovery-receipt.v1.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        Draft202012Validator(recovery_schema).validate(recovery)
    validate_instance(Path(activated["receipt_path"]), "activate-receipt.v1.json")


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
