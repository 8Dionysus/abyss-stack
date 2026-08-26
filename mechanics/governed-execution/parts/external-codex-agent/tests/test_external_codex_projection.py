from __future__ import annotations

from copy import deepcopy
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
    build_private_git_admission_manifest,
    create_review_state_seal,
    materialize_actor_projection,
    materialize_actor_projection_from_seed,
    verify_review_state_seal,
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


def test_projection_accepts_exact_pre_full_index_source_manifest(
    tmp_path: Path,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    _git(source, "config", "core.abbrev", "12")
    filter_marker = tmp_path / "projection-filter-ran"
    filter_helper = tmp_path / "projection-clean-filter"
    filter_helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(filter_marker))}\n"
        "/bin/cat\n",
        encoding="utf-8",
    )
    filter_helper.chmod(0o700)
    (source / ".gitattributes").write_text(
        "tracked.txt filter=projection-clean\n", encoding="utf-8"
    )
    _git(source, "add", ".gitattributes")
    _git(source, "commit", "-qm", "projection filter fixture")
    _git(source, "config", "filter.projection-clean.clean", str(filter_helper))
    (source / "tracked.txt").write_text("dirty owner bytes\n", encoding="utf-8")
    source_manifest = build_workspace_manifest(source)
    assert filter_marker.exists() is False
    legacy_diff = subprocess.run(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-C",
            str(source),
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "HEAD",
            "--",
        ],
        check=True,
        capture_output=True,
        env=PROJECTION._source_git_environment(source),
    ).stdout
    source_manifest["git_diff_binary_sha256"] = PROJECTION.sha256_bytes(legacy_diff)
    _git(source, "config", "core.abbrev", "4")

    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "runtime" / "actor-workspace",
        source_manifest=source_manifest,
        source_manifest_digest="sha256:" + "9" * 64,
    )

    assert (projection / "tracked.txt").read_text(encoding="utf-8") == (
        "dirty owner bytes\n"
    )
    assert baseline["source_manifest_digest"] == "sha256:" + "9" * 64
    assert filter_marker.exists() is False


def test_projection_rejects_real_intent_to_add_zero_oid_before_private_git_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _ = _source_repo(tmp_path)
    (source / "intent.txt").write_text("intent bytes\n", encoding="utf-8")
    _git(source, "add", "-N", "intent.txt")
    source_manifest = build_workspace_manifest(source)
    original_git = PROJECTION._git
    calls: list[tuple[str, ...]] = []
    staged_records: list[bytes] = []

    def traced_git(
        workspace: Path,
        *arguments: str,
        **kwargs: object,
    ) -> bytes:
        calls.append(arguments)
        result = original_git(workspace, *arguments, **kwargs)
        if arguments == ("ls-files", "--stage", "-z"):
            staged_records.append(result)
            # Recent Git versions expose the real intent entry as an empty
            # blob; exercise the lower-level all-zero sentinel as well.
            rewritten: list[bytes] = []
            for record in result.split(b"\0"):
                if record.endswith(b"\tintent.txt"):
                    metadata, separator, path = record.partition(b"\t")
                    assert separator
                    fields = metadata.split()
                    assert len(fields) == 3
                    fields[1] = b"0" * 40
                    record = b" ".join(fields) + b"\t" + path
                rewritten.append(record)
            return b"\0".join(rewritten)
        return result

    monkeypatch.setattr(PROJECTION, "_git", traced_git)
    target = tmp_path / "runtime" / "actor-workspace"

    with pytest.raises(
        ProjectionError,
        match="malformed or zero object ID",
    ):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "a" * 64,
        )

    assert _git(source, "status", "--porcelain=v1") == "A intent.txt"
    assert staged_records and b"intent.txt" in staged_records[0]
    assert calls[-1] == ("ls-files", "--stage", "-z")
    assert not any(
        argument in {"pack-objects", "init", "index-pack", "update-index"}
        for call in calls
        for argument in call
    )
    assert target.exists() is False


def test_projection_rejects_malformed_staged_oid_before_intent_to_add_reconstruction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    original_git = PROJECTION._git
    calls: list[tuple[str, ...]] = []
    malformed_record = b"100644 " + (b"A" * 40) + b" 0\ttracked.txt\0"

    def controlled_git(
        workspace: Path,
        *arguments: str,
        **kwargs: object,
    ) -> bytes:
        calls.append(arguments)
        if arguments == ("ls-files", "--stage", "-z"):
            return malformed_record
        return original_git(workspace, *arguments, **kwargs)

    monkeypatch.setattr(PROJECTION, "_git", controlled_git)
    target = tmp_path / "runtime" / "actor-workspace"

    with pytest.raises(
        ProjectionError,
        match="malformed or zero object ID",
    ):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "b" * 64,
        )

    assert calls[-1] == ("ls-files", "--stage", "-z")
    assert not any(
        argument in {"pack-objects", "init", "index-pack", "update-index"}
        for call in calls
        for argument in call
    )
    assert target.exists() is False


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


def test_recovery_authority_rejects_private_git_poison_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    target = tmp_path / "runtime" / "actor-workspace"
    original_construct = PROJECTION._construct_private_git

    def construct_then_poison(
        source_root: Path,
        staging: Path,
        *,
        source_manifest: dict[str, object],
    ) -> tuple[frozenset[str], bytes]:
        expectation = original_construct(
            source_root,
            staging,
            source_manifest=source_manifest,
        )
        with (staging / ".git" / "config").open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write("[core]\n\tfsmonitor = /tmp/attacker-helper\n")
        return expectation

    monkeypatch.setattr(PROJECTION, "_construct_private_git", construct_then_poison)
    private_git_admission: dict[str, object] = {}

    with pytest.raises(
        ProjectionError,
        match="runtime-authored posture",
    ):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "1" * 64,
            private_git_admission=private_git_admission,
        )

    assert target.exists() is False
    assert private_git_admission == {}


def test_recovery_authority_rejects_object_poison_seen_by_baseline_and_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    target = tmp_path / "runtime" / "actor-workspace"
    original_construct = PROJECTION._construct_private_git

    def construct_then_add_unadmitted_object(
        source_root: Path,
        staging: Path,
        *,
        source_manifest: dict[str, object],
    ) -> tuple[frozenset[str], bytes]:
        object_ids, exclude_bytes = original_construct(
            source_root,
            staging,
            source_manifest=source_manifest,
        )
        poisoned_object_id = PROJECTION._git(
            staging,
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=b"same-uid staging poison\n",
        )
        assert poisoned_object_id.strip().decode("ascii") not in object_ids
        return object_ids, exclude_bytes

    monkeypatch.setattr(
        PROJECTION,
        "_construct_private_git",
        construct_then_add_unadmitted_object,
    )
    private_git_admission: dict[str, object] = {}

    with pytest.raises(
        ProjectionError,
        match="topology contains unadmitted metadata",
    ):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "1" * 64,
            private_git_admission=private_git_admission,
        )

    assert target.exists() is False
    assert private_git_admission == {}


@pytest.mark.parametrize("metadata_path", ["shallow", "packed-refs"])
def test_recovery_authority_rejects_unadmitted_git_metadata_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_path: str,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    target = tmp_path / "runtime" / "actor-workspace"
    original_construct = PROJECTION._construct_private_git

    def construct_then_add_metadata(
        source_root: Path,
        staging: Path,
        *,
        source_manifest: dict[str, object],
    ) -> tuple[frozenset[str], bytes]:
        expectation = original_construct(
            source_root,
            staging,
            source_manifest=source_manifest,
        )
        (staging / ".git" / metadata_path).write_text(
            str(source_manifest["git_head"]) + "\n",
            encoding="ascii",
        )
        return expectation

    monkeypatch.setattr(
        PROJECTION,
        "_construct_private_git",
        construct_then_add_metadata,
    )

    with pytest.raises(
        ProjectionError,
        match="topology contains unadmitted metadata",
    ):
        materialize_actor_projection(
            source,
            target,
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "1" * 64,
        )

    assert target.exists() is False


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


def test_projection_delta_accepts_reviewed_resume_private_git_and_rejects_new_drift(
    tmp_path: Path,
) -> None:
    source, source_identity = _source_repo(tmp_path)
    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "runtime" / "actor-workspace",
        source_manifest=source_identity,
        source_manifest_digest="sha256:" + "5" * 64,
    )

    index_path = projection / ".git" / "index"
    index_path.write_bytes(index_path.read_bytes() + b"accepted resume state\n")
    accepted_resume = build_actor_manifest(
        projection,
        source_manifest_digest=baseline["source_manifest_digest"],
        source_git_head=str(baseline["source_git_head"]),
    )
    assert accepted_resume["private_git_digest"] != baseline["private_git_digest"]

    with pytest.raises(
        ProjectionError,
        match="actor private Git body changed during execution",
    ):
        build_actor_delta(
            baseline,
            accepted_resume,
            baseline_digest="sha256:" + "6" * 64,
            current_digest="sha256:" + "7" * 64,
        )

    delta = build_actor_delta(
        baseline,
        accepted_resume,
        baseline_digest="sha256:" + "6" * 64,
        current_digest="sha256:" + "7" * 64,
        private_git_baseline=accepted_resume,
    )
    assert delta["changes"] == []

    (projection / ".git" / "config").write_bytes(
        (projection / ".git" / "config").read_bytes() + b"\nunauthorized drift\n"
    )
    drifted = build_actor_manifest(
        projection,
        source_manifest_digest=baseline["source_manifest_digest"],
        source_git_head=str(baseline["source_git_head"]),
    )
    with pytest.raises(
        ProjectionError,
        match="actor private Git body changed during execution",
    ):
        build_actor_delta(
            baseline,
            drifted,
            baseline_digest="sha256:" + "6" * 64,
            current_digest="sha256:" + "8" * 64,
            private_git_baseline=accepted_resume,
        )


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


def test_projection_preserves_admitted_shallow_boundary_and_strict_fsck(
    tmp_path: Path,
) -> None:
    full = tmp_path / "full-source"
    full.mkdir()
    _git(full, "init", "-q")
    _git(full, "config", "user.name", "projection-test")
    _git(full, "config", "user.email", "projection@example.invalid")
    (full / "tracked.txt").write_text("first\n", encoding="utf-8")
    _git(full, "add", ".")
    _git(full, "commit", "-qm", "first")
    (full / "tracked.txt").write_text("second\n", encoding="utf-8")
    _git(full, "commit", "-qam", "second")
    source = tmp_path / "shallow-source"
    subprocess.run(
        ["/usr/bin/git", "clone", "--depth", "1", f"file://{full}", str(source)],
        check=True,
        capture_output=True,
    )
    source_manifest = build_workspace_manifest(source)
    assert source_manifest["git_shallow"]["present"] is True

    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "runtime" / "actor-workspace",
        source_manifest=source_manifest,
        source_manifest_digest="sha256:" + "b" * 64,
    )
    assert (projection / ".git" / "shallow").read_bytes() == (
        source / ".git" / "shallow"
    ).read_bytes()
    assert baseline["private_git_digest"].startswith("sha256:")
    assert subprocess.run(
        [
            "/usr/bin/git",
            "-C",
            str(projection),
            "fsck",
            "--strict",
            "--full",
            "--no-reflogs",
            "--no-dangling",
        ],
        check=False,
        capture_output=True,
    ).returncode == 0

    (source / ".git" / "shallow").write_text("0" * 40 + "\n", encoding="ascii")
    with pytest.raises(ProjectionError, match="shallow boundary"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "rejected-shallow",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "c" * 64,
        )


def test_shallow_boundary_validation_fails_closed_for_forged_metadata(
    tmp_path: Path,
) -> None:
    full = tmp_path / "full-source"
    full.mkdir()
    _git(full, "init", "-q")
    _git(full, "config", "user.name", "projection-test")
    _git(full, "config", "user.email", "projection@example.invalid")
    (full / "tracked.txt").write_text("first\n", encoding="utf-8")
    _git(full, "add", ".")
    _git(full, "commit", "-qm", "first")
    (full / "tracked.txt").write_text("second\n", encoding="utf-8")
    _git(full, "commit", "-qam", "second")
    source = tmp_path / "shallow-source"
    subprocess.run(
        ["/usr/bin/git", "clone", "--depth", "1", f"file://{full}", str(source)],
        check=True,
        capture_output=True,
    )
    source_manifest = build_workspace_manifest(source)
    boundary_path = source / ".git" / "shallow"
    boundary = str(source_manifest["git_shallow"]["entries"][0])

    boundary_path.write_text("not-an-object-id\n", encoding="ascii")
    with pytest.raises(ProjectionError, match="malformed"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "malformed",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "1" * 64,
        )

    boundary_path.write_text(f"{boundary}\n{boundary}\n", encoding="ascii")
    with pytest.raises(ProjectionError, match="duplicate"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "duplicate",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "2" * 64,
        )

    boundary_path.write_text("0" * 40 + "\n", encoding="ascii")
    foreign_manifest = deepcopy(source_manifest)
    foreign_manifest["git_shallow"] = PROJECTION.read_source_shallow_boundary(source)
    with pytest.raises(ProjectionError, match="outside the admitted object set"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "foreign",
            source_manifest=foreign_manifest,
            source_manifest_digest="sha256:" + "3" * 64,
        )

    blob = _git(source, "rev-parse", "HEAD:tracked.txt")
    boundary_path.write_text(blob + "\n", encoding="ascii")
    blob_manifest = deepcopy(source_manifest)
    blob_manifest["git_shallow"] = PROJECTION.read_source_shallow_boundary(source)
    with pytest.raises(ProjectionError, match="does not name a commit object"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "blob",
            source_manifest=blob_manifest,
            source_manifest_digest="sha256:" + "4" * 64,
        )

    boundary_path.unlink()
    boundary_path.symlink_to(tmp_path / "outside-shallow")
    with pytest.raises(ProjectionError, match="not a regular file"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "symlink",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "5" * 64,
        )


def test_shallow_root_boundary_is_rejected_as_unnecessary(tmp_path: Path) -> None:
    full = tmp_path / "single-commit-source"
    full.mkdir()
    _git(full, "init", "-q")
    _git(full, "config", "user.name", "projection-test")
    _git(full, "config", "user.email", "projection@example.invalid")
    (full / "tracked.txt").write_text("root\n", encoding="utf-8")
    _git(full, "add", ".")
    _git(full, "commit", "-qm", "root")
    source = tmp_path / "shallow-root"
    subprocess.run(
        ["/usr/bin/git", "clone", "--depth", "1", f"file://{full}", str(source)],
        check=True,
        capture_output=True,
    )
    source_manifest = build_workspace_manifest(source)
    with pytest.raises(ProjectionError, match="unnecessary"):
        materialize_actor_projection(
            source,
            tmp_path / "runtime" / "unnecessary",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "6" * 64,
        )


def test_terminal_review_state_seal_survives_index_refresh_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    source, _ = _source_repo(tmp_path)
    metadata_named_files = ("review-state-seal.json", ".seal-in-progress.json")
    for name in metadata_named_files:
        (source / name).write_text(f"repository file: {name}\n", encoding="utf-8")
    locked = source / "sealed-locked"
    locked.mkdir()
    (locked / "nested.txt").write_text("nested\n", encoding="utf-8")
    _git(source, "add", *metadata_named_files, "sealed-locked/nested.txt")
    _git(source, "commit", "-qm", "sealed read-only directory")
    locked.chmod(0o555)
    try:
        source_manifest = build_workspace_manifest(source)
        projection, baseline = materialize_actor_projection(
            source,
            tmp_path / "writer" / "actor-workspace",
            source_manifest=source_manifest,
            source_manifest_digest="sha256:" + "d" * 64,
        )
        private_git = build_private_git_admission_manifest(
            projection,
            expected_source_git_head=str(baseline["source_git_head"]),
            require_strict_fsck=True,
        )
        legacy_reviewer, _ = materialize_actor_projection_from_seed(
            projection,
            tmp_path / "legacy-reviewer" / "actor-workspace",
            expected_manifest=baseline,
            seed_kind="projection",
        )
        for name in metadata_named_files:
            assert (legacy_reviewer / name).read_text(encoding="utf-8") == (
                f"repository file: {name}\n"
            )
        delta = build_actor_delta(
            baseline,
            baseline,
            baseline_digest="sha256:" + "e" * 64,
            current_digest=PROJECTION._canonical_digest(baseline),
            private_git_baseline=private_git,
        )
        seal = create_review_state_seal(
            projection,
            tmp_path / "writer" / "review-state-seal",
            session_id="session:writer",
            incarnation_id="incarnation:writer",
            writer_status="review_required",
            final_manifest=baseline,
            actor_delta=delta,
        )
        repeated = create_review_state_seal(
            projection,
            tmp_path / "writer" / "review-state-seal",
            session_id="session:writer",
            incarnation_id="incarnation:writer",
            writer_status="review_required",
            final_manifest=baseline,
            actor_delta=delta,
        )
        assert repeated["manifest_digest"] == seal["manifest_digest"]
        index = projection / ".git" / "index"
        index.write_bytes(index.read_bytes() + b"benign post-closeout refresh\n")
        verify_review_state_seal(
            tmp_path / "writer" / "review-state-seal",
            expected_manifest=baseline,
            expected_delta=delta,
            expected_session_id="session:writer",
            expected_incarnation_id="incarnation:writer",
            expected_status="review_required",
        )
        reviewer, reviewer_manifest = materialize_actor_projection_from_seed(
            tmp_path / "writer" / "review-state-seal",
            tmp_path / "reviewer" / "actor-workspace",
            expected_manifest=baseline,
            seed_kind="seal",
        )
        assert reviewer_manifest["private_git_digest"] == baseline["private_git_digest"]
        assert (reviewer / "sealed-locked").stat().st_mode & 0o777 == 0o555
        assert (reviewer / "sealed-locked" / "nested.txt").read_text() == "nested\n"
        for name in metadata_named_files:
            assert (reviewer / name).read_text(encoding="utf-8") == (
                f"repository file: {name}\n"
            )
        object_path = next(
            (tmp_path / "writer" / "review-state-seal" / "objects").iterdir()
        )
        object_path.chmod(0o600)
        with pytest.raises(ProjectionError, match="seal"):
            verify_review_state_seal(tmp_path / "writer" / "review-state-seal")
    finally:
        locked.chmod(0o755)


def test_review_state_seal_reopens_only_from_its_owned_crash_marker(
    tmp_path: Path,
) -> None:
    source, source_manifest = _source_repo(tmp_path)
    projection, baseline = materialize_actor_projection(
        source,
        tmp_path / "writer" / "actor-workspace",
        source_manifest=source_manifest,
        source_manifest_digest="sha256:" + "f" * 64,
    )
    delta = build_actor_delta(
        baseline,
        baseline,
        baseline_digest="sha256:" + "1" * 64,
        current_digest=PROJECTION._canonical_digest(baseline),
    )
    seal_root = tmp_path / "writer" / "review-state-seal"
    create_review_state_seal(
        projection,
        seal_root,
        session_id="session:writer",
        incarnation_id="incarnation:writer",
        writer_status="completed",
        final_manifest=baseline,
        actor_delta=delta,
    )
    (seal_root / "review-state-seal.json").unlink()
    reopened = create_review_state_seal(
        projection,
        seal_root,
        session_id="session:writer",
        incarnation_id="incarnation:writer",
        writer_status="completed",
        final_manifest=baseline,
        actor_delta=delta,
    )
    assert reopened["writer_status"] == "completed"
    (seal_root / "review-state-seal.json").unlink()
    (seal_root / ".seal-in-progress.json").unlink()
    with pytest.raises(ProjectionError, match="recovery marker"):
        create_review_state_seal(
            projection,
            seal_root,
            session_id="session:writer",
            incarnation_id="incarnation:writer",
            writer_status="completed",
            final_manifest=baseline,
            actor_delta=delta,
        )


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
            seed_kind="projection",
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
