from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import validate

PART_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PART_ROOT))

import external_codex_projection as PROJECTION  # noqa: E402
from external_codex_projection import (  # noqa: E402
    ProjectionError,
    build_actor_delta,
    build_actor_manifest,
    materialize_actor_projection,
    materialize_actor_projection_from_seed,
)
from external_codex_agent import build_workspace_manifest  # noqa: E402


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _source_repo(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source = tmp_path / "owner-source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "projection-test")
    _git(source, "config", "user.email", "projection@example.invalid")
    (source / "tracked.txt").write_text("owner bytes\n", encoding="utf-8")
    (source / "link").symlink_to("tracked.txt")
    _git(source, "add", ".")
    _git(source, "commit", "-qm", "fixture")
    # This is deliberately source-only metadata.  The projection must never
    # carry it into the actor's filesystem.
    _git(
        source,
        "config",
        "http.https://example.invalid/.extraHeader",
        "Authorization: Bearer SOURCE-CONFIG-MARKER",
    )
    return source, build_workspace_manifest(source)


def test_projection_packing_disables_promisor_lazy_fetch_helpers(
    tmp_path: Path,
) -> None:
    source, source_identity = _source_repo(tmp_path)
    blob_oid = _git(source, "rev-parse", "HEAD:tracked.txt")
    blob_path = source / ".git" / "objects" / blob_oid[:2] / blob_oid[2:]
    assert blob_path.is_file()

    marker = tmp_path / "projection-promisor-helper-ran"
    helper = tmp_path / "projection-promisor-helper"
    helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        "exit 1\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    _git(source, "config", "extensions.partialClone", "origin")
    _git(source, "config", "protocol.ext.allow", "always")
    _git(source, "config", "remote.origin.url", f"ext::{helper}")
    _git(source, "config", "remote.origin.promisor", "true")
    _git(source, "config", "remote.origin.partialclonefilter", "blob:none")
    blob_path.unlink()

    unsafe_environment = PROJECTION._git_environment()
    unsafe_environment.pop("GIT_NO_LAZY_FETCH")
    unsafe = subprocess.run(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-C",
            str(source),
            "pack-objects",
            "--stdout",
            "--revs",
        ],
        input=(str(source_identity["git_head"]) + "\n").encode("ascii"),
        env=unsafe_environment,
        check=False,
        capture_output=True,
    )
    assert unsafe.returncode != 0
    assert marker.is_file()
    marker.unlink()

    with pytest.raises(
        ProjectionError,
        match="private actor Git construction rejected the admitted baseline",
    ):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "actor-workspace",
            source_manifest=source_identity,
            source_manifest_digest="sha256:" + "1" * 64,
        )

    assert PROJECTION._git_environment()["GIT_NO_LAZY_FETCH"] == "1"
    assert marker.exists() is False


def test_inventory_distinguishes_disappearing_directory_from_other_scandir_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "actor-workspace"
    volatile = root / ".pytest_cache" / "v" / "cache"
    volatile.mkdir(parents=True)
    original_scandir = PROJECTION.os.scandir

    def missing_scandir(path: Path) -> object:
        if Path(path) == volatile:
            raise FileNotFoundError(str(path))
        return original_scandir(path)

    monkeypatch.setattr(PROJECTION.os, "scandir", missing_scandir)
    with pytest.raises(
        ProjectionError,
        match=r"directory disappeared before enumeration: \.pytest_cache/v/cache",
    ):
        PROJECTION._inventory(root)

    def denied_scandir(path: Path) -> object:
        if Path(path) == volatile:
            raise PermissionError(str(path))
        return original_scandir(path)

    monkeypatch.setattr(PROJECTION.os, "scandir", denied_scandir)
    with pytest.raises(ProjectionError, match="cannot enumerate its tree"):
        PROJECTION._inventory(root)


def test_projection_owns_private_git_and_survives_source_parent_replacement(
    tmp_path: Path,
) -> None:
    source, source_identity = _source_repo(tmp_path)
    projection_path = tmp_path / "runtime" / "actor-workspace"
    projection, baseline = materialize_actor_projection(
        source,
        projection_path,
        source_manifest=source_identity,
        source_manifest_digest="sha256:" + "1" * 64,
    )

    moved_source = tmp_path / "renamed-owner-source"
    source.rename(moved_source)
    replacement = tmp_path / "owner-source"
    replacement.mkdir()
    (replacement / "replacement.txt").write_text(
        "replacement must not be exposed\n", encoding="utf-8"
    )
    (replacement / ".git").mkdir()
    (replacement / ".git" / "config").write_text(
        "[http]\n\tmarker = SOURCE-CONFIG-MARKER\n", encoding="utf-8"
    )

    assert (projection / ".git").is_dir()
    assert _git(projection, "rev-parse", "HEAD") == source_identity["git_head"]
    assert not (projection / "replacement.txt").exists()
    assert "SOURCE-CONFIG-MARKER" not in "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in projection.rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    assert baseline["workspace_path"] == str(projection.resolve())
    assert baseline["private_git_digest"].startswith("sha256:")


def test_projection_delta_is_canonical_for_write_mode_symlink_and_delete(
    tmp_path: Path,
) -> None:
    source, source_identity = _source_repo(tmp_path)
    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "runtime" / "actor-workspace",
        source_manifest=source_identity,
        source_manifest_digest="sha256:" + "2" * 64,
    )
    source_before = (source / "tracked.txt").read_bytes()

    (projection / "tracked.txt").write_text("actor bytes\n", encoding="utf-8")
    (projection / "created.bin").write_bytes(b"\x00\xffactor\n")
    (projection / "link").unlink()
    (projection / "new-link").symlink_to("tracked.txt")
    (projection / "created.bin").chmod(0o700)
    final = build_actor_manifest(
        projection,
        source_manifest_digest=baseline["source_manifest_digest"],
        source_git_head=str(baseline["source_git_head"]),
    )
    delta = build_actor_delta(
        baseline,
        final,
        baseline_digest="sha256:" + "3" * 64,
        current_digest="sha256:" + "4" * 64,
    )
    schema = __import__("json").loads(
        (PART_ROOT / "schemas/external-codex-actor-delta.schema.json").read_text()
    )
    validate(delta, schema)
    assert {item["status"] for item in delta["changes"]} >= {
        "modified",
        "created",
        "deleted",
    }
    assert (source / "tracked.txt").read_bytes() == source_before
    assert not (source / "created.bin").exists()
    assert (source / "link").is_symlink()


def test_projection_reproduces_dirty_git_baseline_and_real_git_validations(
    tmp_path: Path,
) -> None:
    source, _ = _source_repo(tmp_path)
    (source / ".gitignore").write_text("ignored.bin\n", encoding="utf-8")
    (source / "tracked.txt").write_text("staged bytes\n", encoding="utf-8")
    _git(source, "add", "tracked.txt", ".gitignore")
    (source / "tracked.txt").write_text("working bytes\n", encoding="utf-8")
    (source / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    (source / "ignored.bin").write_bytes(b"ignored\x00bytes")
    source_manifest = build_workspace_manifest(source)

    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "runtime" / "actor-workspace",
        source_manifest=source_manifest,
        source_manifest_digest="sha256:" + "5" * 64,
    )

    assert _git(projection, "status", "--porcelain=v1", "--untracked-files=all") == (
        _git(source, "status", "--porcelain=v1", "--untracked-files=all")
    )
    assert (
        subprocess.run(
            ["/usr/bin/git", "-C", str(projection), "diff", "--check", "HEAD"],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )
    before_git_digest = baseline["private_git_digest"]
    observed = build_actor_manifest(
        projection,
        source_manifest_digest=str(baseline["source_manifest_digest"]),
        source_git_head=str(baseline["source_git_head"]),
    )
    assert observed["private_git_digest"] == before_git_digest


def test_projection_handles_read_only_directories_and_cleans_failed_staging(
    tmp_path: Path,
) -> None:
    source, _ = _source_repo(tmp_path)
    locked = source / "locked"
    locked.mkdir()
    (locked / "nested.txt").write_text("nested\n", encoding="utf-8")
    _git(source, "add", "locked/nested.txt")
    _git(source, "commit", "-qm", "read-only directory")
    locked.chmod(0o555)
    try:
        source_manifest = build_workspace_manifest(source)
        projection, _ = materialize_actor_projection(
            source,
            tmp_path / "runtime" / "actor-workspace",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "6" * 64,
        )
        assert (projection / "locked").stat().st_mode & 0o777 == 0o555
        assert (projection / "locked" / "nested.txt").read_text() == "nested\n"
        (projection / "locked").chmod(0o755)
    finally:
        locked.chmod(0o755)


def test_projection_rejects_bytes_not_admitted_by_source_manifest(
    tmp_path: Path,
) -> None:
    source, _ = _source_repo(tmp_path)
    source_manifest = build_workspace_manifest(source)
    (source / "tracked.txt").write_text("changed after admission\n", encoding="utf-8")
    target = tmp_path / "runtime" / "actor-workspace"

    with pytest.raises(ProjectionError, match="admitted source manifest"):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "7" * 64,
        )

    assert not target.exists()
    assert list((tmp_path / "runtime").glob(".actor-projection-*")) == []


def test_source_projection_cleans_exact_inode_after_post_rename_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    target = tmp_path / "runtime" / "actor-workspace"
    original_publish = PROJECTION._publish_staging

    def publish_then_fail(**kwargs: object) -> None:
        original_publish(**kwargs)
        raise ProjectionError("injected post-rename verification failure")

    monkeypatch.setattr(PROJECTION, "_publish_staging", publish_then_fail)
    with pytest.raises(ProjectionError, match="post-rename"):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "8" * 64,
        )

    assert not target.exists()
    assert list(target.parent.glob(".actor-projection-*")) == []


def test_seed_projection_cleans_exact_inode_after_post_rename_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    seed, seed_manifest = materialize_actor_projection(
        source,
        tmp_path / "writer" / "actor-workspace",
        source_manifest=source_manifest,
        source_manifest_digest="sha256:" + "9" * 64,
    )
    target = tmp_path / "reviewer" / "actor-workspace"
    original_publish = PROJECTION._publish_staging

    def publish_then_fail(**kwargs: object) -> None:
        original_publish(**kwargs)
        raise ProjectionError("injected post-rename verification failure")

    monkeypatch.setattr(PROJECTION, "_publish_staging", publish_then_fail)
    with pytest.raises(ProjectionError, match="post-rename"):
        materialize_actor_projection_from_seed(
            seed,
            target,
            expected_manifest=seed_manifest,
        )

    assert not target.exists()
    assert list(target.parent.glob(".review-projection-*")) == []


def test_projection_publication_never_replaces_raced_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    target = tmp_path / "runtime" / "actor-workspace"
    original_publish = PROJECTION._publish_staging

    def race_target_then_publish(**kwargs: object) -> None:
        target.mkdir()
        (target / "attacker.txt").write_text("preserve me\n", encoding="utf-8")
        original_publish(**kwargs)

    monkeypatch.setattr(PROJECTION, "_publish_staging", race_target_then_publish)
    with pytest.raises(ProjectionError, match="target already exists"):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "a" * 64,
        )

    assert (target / "attacker.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert list(target.parent.glob(".actor-projection-*")) == []
