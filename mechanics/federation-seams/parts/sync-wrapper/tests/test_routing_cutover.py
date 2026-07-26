from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[5]
SCRIPT = REPO_ROOT / "scripts" / "aoa-routing-cutover"
BACKEND = (
    REPO_ROOT
    / "mechanics/federation-seams/parts/sync-wrapper/aoa_routing_cutover.py"
)
sys.path.insert(0, str(BACKEND.parent))
BACKEND_SPEC = importlib.util.spec_from_file_location(
    "aoa_routing_cutover_under_test",
    BACKEND,
)
assert BACKEND_SPEC is not None and BACKEND_SPEC.loader is not None
CUTOVER_BACKEND = importlib.util.module_from_spec(BACKEND_SPEC)
BACKEND_SPEC.loader.exec_module(CUTOVER_BACKEND)
SDK_REF = "d" * 40
PREDECESSOR_REF = "a" * 40
AUTHORITY = {
    "archive_authorized": False,
    "canonical_producer_switch_authorized": True,
    "compatibility_window_started": True,
    "live_runtime_mutation_authorized": True,
    "predecessor_maintenance_only": True,
    "sdk_canonical": True,
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def stable_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def run_cutover(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *arguments],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def owner_switch_receipt() -> dict[str, object]:
    return {
        "schema": "aoa_sdk_routing_g5_owner_switch_receipt_v1",
        "status": "g5_switch_authorized",
        "transition": {
            "from_state": "predecessor_canonical",
            "to_state": "sdk_canonical",
            "canonical_owner_before": "aoa-routing",
            "canonical_owner_after": "aoa-sdk",
        },
        "sdk": {
            "owner_repo": "aoa-sdk",
            "source_ref": SDK_REF,
            "version": "0.8.0",
            "abi_epoch": "aoa_routing_thin_router_v1",
        },
        "predecessor": {
            "owner_repo": "aoa-routing",
            "source_ref": PREDECESSOR_REF,
            "rollback_posture": "retained",
        },
        "public_release": {
            "release_ref": "https://example.invalid/aoa-sdk/v0.8.0",
            "asset_digest": "sha256:" + ("e" * 64),
        },
        "compatibility_window": {
            "state": "started",
            "started_on": "2026-07-25",
            "started_by_sdk_version": "0.8.0",
        },
        "g5_authority": dict(AUTHORITY),
        "archive_stop_line": (
            "Repository archival remains forbidden without consumer-zero, "
            "compatibility exit, and separate exact operator approval."
        ),
    }


def make_fixture(tmp_path: Path) -> dict[str, str]:
    required_files = [
        "generated/aoa_router.min.json",
        "generated/task_to_surface_hints.json",
    ]
    config = tmp_path / "aoa-routing.yaml"
    config.write_text(
        "\n".join(
            [
                "layer: aoa-routing",
                "mirror_root: /app/federation/aoa-routing",
                "required_files:",
                *[f"  - {item}" for item in required_files],
                "",
            ]
        ),
        encoding="utf-8",
    )
    store = tmp_path / "subject-store"
    payloads: dict[str, object] = {
        "generated/aoa_router.min.json": {
            "router_version": 1,
            "artifact_identity": {
                "owner_repo": "aoa-sdk",
                "artifact_class": "thin_routing_readmodel_bundle",
                "abi_epoch": "aoa_routing_thin_router_v1",
            },
        },
        "generated/task_to_surface_hints.json": {
            "version": "1",
            "hints": [],
        },
        "succession/routing-g5-owner-switch.json": owner_switch_receipt(),
    }
    files: list[dict[str, object]] = []
    for relative, payload in payloads.items():
        path = store / relative
        write_json(path, payload)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "bytes": path.stat().st_size,
                "path": relative,
                "role": (
                    "owner_switch_receipt"
                    if relative.startswith("succession/")
                    else "routing_readmodel"
                ),
                "sha256": f"sha256:{digest}",
                "sha256_hex": digest,
            }
        )
    files.sort(key=lambda item: str(item["path"]))
    subject_digest = stable_digest(files)
    write_json(
        store / "subject-store.json",
        {
            "schema": "abyss_machine_artifact_subject_store_v1",
            "artifact_class": "thin_routing_readmodel_bundle",
            "owner_repo": "aoa-sdk",
            "aggregate_digest": subject_digest,
            "consumer_intent": "runtime",
            "files": files,
        },
    )
    receipt = owner_switch_receipt()
    receipt_summary = {
        "schema": "aoa_sdk_routing_g5_owner_switch_receipt_v1",
        "status": "g5_switch_authorized",
        "digest": stable_digest(receipt),
    }
    admission = {
        "schema": "abyss_machine_artifact_producer_admission_v1",
        "status": "canonical_producer",
        "profile_id": "aoa-sdk-g5-canonical",
        "owner_repo": "aoa-sdk",
        "source_ref": SDK_REF,
        "canonical_owner_repo": "aoa-sdk",
        "canonical_predecessor_source_ref": PREDECESSOR_REF,
        "runtime_consumer": "abyss-stack",
        "stronger_owner": "abyss-machine",
        "provenance_state": "sdk_canonical",
        "publication_posture": "public_release_canonical",
        "single_canonical_owner": True,
        "canonical_switch_authorized": True,
        "allowed_consumer_intents": ["release_consumer", "runtime"],
        "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
        "g5_authority": dict(AUTHORITY),
        "owner_switch_receipt": receipt_summary,
    }
    record_id = "sha256:" + ("c" * 64)
    trust = {
        "schema": "abyss_machine_artifact_trust_gate_v1",
        "ok": True,
        "verdict": "allow",
        "artifact_class": "thin_routing_readmodel_bundle",
        "consumer_intent": "runtime",
        "subject_digest": subject_digest,
        "record_id": record_id,
        "require_latest": True,
        "latest_record_id": record_id,
        "reasons": [],
        "blockers": [],
        "decision": {
            "model": "fail_closed_consumer_admission",
            "allow": True,
            "consumer_intent": "runtime",
        },
        "inspected_claims": {
            "subject_identity": {
                "subject_digest_expected": subject_digest,
                "subject_digest_matched": True,
            },
            "registry_latest": {
                "required": True,
                "selected_record_is_latest": True,
            },
            "source": {
                "source_repo_matched": True,
                "source_ref_matched": True,
                "source_ref_actual": SDK_REF,
            },
            "trust_root": {
                "trust_root_mode_actual": "public_release",
                "trust_root_mode_matched": True,
            },
            "artifact_subject_store": {
                "required": True,
                "ok": True,
                "aggregate_digest": subject_digest,
            },
            "producer_admission": admission,
        },
        "record": {
            "record_id": record_id,
            "artifact_class": "thin_routing_readmodel_bundle",
            "source_repo": "aoa-sdk",
            "source_ref": SDK_REF,
            "artifact_subjects_digest": subject_digest,
            "lifecycle_state": "release-ready",
            "latest_eligible": True,
            "terminal_state": False,
            "verification_ok": True,
            "trust_root_mode": "public_release",
            "consumer_refs": ["abyss-stack:routing-canonical"],
            "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "verified_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "artifact_subject_store": {
                "required": True,
                "ok": True,
                "aggregate_digest": subject_digest,
            },
            "producer_admission": admission,
        },
    }
    trust_path = tmp_path / "trust-verdict.json"
    write_json(trust_path, trust)
    return {
        "config": str(config),
        "subject_store": str(store),
        "receipt": str(store / "succession/routing-g5-owner-switch.json"),
        "subject_digest": subject_digest,
        "trust_verdict": str(trust_path),
    }


def exact_args(fixture: dict[str, str], target: Path) -> list[str]:
    return [
        "--subject-store",
        fixture["subject_store"],
        "--trust-verdict",
        fixture["trust_verdict"],
        "--owner-switch-receipt",
        fixture["receipt"],
        "--target-root",
        str(target),
        "--sdk-source-ref",
        SDK_REF,
        "--predecessor-source-ref",
        PREDECESSOR_REF,
        "--subject-digest",
        fixture["subject_digest"],
        "--routing-config",
        fixture["config"],
    ]


def make_predecessor_root(
    target: Path,
    fixture: dict[str, str],
) -> None:
    payloads: dict[str, object] = {
        "generated/aoa_router.min.json": {
            "router_version": 1,
            "artifact_identity": {
                "owner_repo": "aoa-routing",
                "artifact_class": "thin_routing_readmodel_bundle",
                "abi_epoch": "aoa_routing_thin_router_v1",
            },
        },
        "generated/task_to_surface_hints.json": {
            "version": "1",
            "hints": [],
        },
    }
    for relative, payload in payloads.items():
        write_json(target / relative, payload)
    required_files = list(payloads)
    write_json(
        target / "manifest/federation_mirror_manifest.json",
        {
            "schema": "abyss_stack_federation_mirror_manifest_v1",
            "layer": "aoa-routing",
            "source_git_commit": PREDECESSOR_REF,
            "required_file_count": len(required_files),
            "required_files": required_files,
            "file_sha256": {
                relative: hashlib.sha256(
                    (target / relative).read_bytes()
                ).hexdigest()
                for relative in required_files
            },
            "mirror_is_authority": False,
        },
    )
    (target / "predecessor.txt").write_text(
        "rollback\n",
        encoding="utf-8",
    )


def rollback_args(
    fixture: dict[str, str],
    *,
    target: Path,
    rollback_root: Path,
    retain_root: Path,
) -> list[str]:
    return [
        "rollback",
        "--authorized-live-cutover",
        "--target-root",
        str(target),
        "--rollback-root",
        str(rollback_root),
        "--canonical-retain-root",
        str(retain_root),
        "--sdk-source-ref",
        SDK_REF,
        "--predecessor-source-ref",
        PREDECESSOR_REF,
        "--subject-digest",
        fixture["subject_digest"],
        "--operator-change-ref",
        "test-g5-change",
        "--routing-config",
        fixture["config"],
    ]


def test_isolated_canonical_materialization_is_receipt_bound(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "isolated" / "aoa-routing"

    materialized = run_cutover(
        ["materialize", *exact_args(fixture, target), "--isolated"]
    )
    assert materialized.returncode == 0, materialized.stderr + materialized.stdout
    result = json.loads(materialized.stdout)
    assert result["posture"] == "sdk_canonical"
    assert result["canonical_switch_authorized"] is True
    assert result["closure_authorized"] is True
    assert result["g5_authority"] == AUTHORITY

    checked = run_cutover(["check", *exact_args(fixture, target)])
    assert checked.returncode == 0, checked.stderr + checked.stdout
    manifest = json.loads(
        (target / "manifest/federation_mirror_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["canonical_producer"]["owner_repo"] == "aoa-sdk"
    assert manifest["predecessor_rollback"]["owner_repo"] == "aoa-routing"
    assert manifest["mirror_is_authority"] is False


def test_isolated_cutover_rejects_live_target_shape(tmp_path: Path) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"

    result = run_cutover(
        ["materialize", *exact_args(fixture, target), "--isolated"]
    )

    assert result.returncode == 1
    assert "requires --authorized-live-cutover" in json.loads(result.stdout)[
        "error"
    ]
    assert not target.exists()


def test_canonical_cutover_rejects_receipt_or_admission_authority_drift(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    receipt_path = Path(fixture["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["g5_authority"]["archive_authorized"] = True
    write_json(receipt_path, receipt)

    result = run_cutover(
        [
            "materialize",
            *exact_args(fixture, tmp_path / "isolated" / "aoa-routing"),
            "--isolated",
        ]
    )
    assert result.returncode == 1
    assert "subject-store file digest drifted" in json.loads(result.stdout)[
        "error"
    ]


def test_live_cutover_and_runtime_rollback_preserve_source_owner_state(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout
    assert json.loads(activated.stdout)["predecessor_validation"][
        "verified"
    ] is True
    assert rollback_root.joinpath("predecessor.txt").is_file()

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    restored = run_cutover(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )
    assert restored.returncode == 0, restored.stderr + restored.stdout
    result = json.loads(restored.stdout)
    assert result["runtime_owner_state"] == "compatibility_rollback_active"
    assert result["source_owner_state"] == "sdk_canonical_unchanged"
    assert result["archive_authorized"] is False
    assert target.joinpath("predecessor.txt").is_file()
    marker = json.loads(
        target.joinpath(
            "manifest/routing_g5_compatibility_rollback.json"
        ).read_text(encoding="utf-8")
    )
    assert marker["state"] == "compatibility_rollback_active"
    assert marker["source_owner_state"] == "sdk_canonical_unchanged"
    assert marker["archive_authorized"] is False


@pytest.mark.parametrize(
    "termination_point",
    ["before_first_swap", "between_swaps", "after_second_swap"],
)
def test_live_cutover_retry_recovers_each_rename_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    termination_point: str,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    prepared = target.parent / ".aoa-routing.sdk-canonical-prepared"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    real_replace = os.replace

    def terminate_at_selected_boundary(
        source: Path,
        destination: Path,
    ) -> None:
        pair = (Path(source), Path(destination))
        if (
            termination_point == "before_first_swap"
            and pair == (target, rollback_root)
        ):
            raise KeyboardInterrupt("injected live cutover termination")
        real_replace(source, destination)
        if (
            termination_point == "between_swaps"
            and pair == (target, rollback_root)
        ):
            raise KeyboardInterrupt("injected live cutover termination")
        if (
            termination_point == "after_second_swap"
            and pair == (prepared, target)
        ):
            raise KeyboardInterrupt("injected live cutover termination")

    monkeypatch.setattr(
        CUTOVER_BACKEND.os,
        "replace",
        terminate_at_selected_boundary,
    )
    with pytest.raises(
        KeyboardInterrupt,
        match="injected live cutover termination",
    ):
        CUTOVER_BACKEND.materialize(parsed)

    if termination_point == "before_first_swap":
        assert target.is_dir()
        assert not rollback_root.exists()
        assert prepared.is_dir()
    elif termination_point == "between_swaps":
        assert not target.exists()
        assert rollback_root.is_dir()
        assert prepared.is_dir()
    else:
        assert target.is_dir()
        assert rollback_root.is_dir()
        assert not prepared.exists()

    monkeypatch.setattr(CUTOVER_BACKEND.os, "replace", real_replace)
    recovered = CUTOVER_BACKEND.materialize(parsed)

    assert recovered["activated"] is True
    assert recovered["retry_state"] in {
        "continued_prepared_activation",
        "continued_after_predecessor_rename",
        "already_activated",
    }
    assert recovered["idempotent_retry"] is (
        termination_point == "after_second_swap"
    )
    assert target.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()
    assert rollback_root.joinpath("predecessor.txt").is_file()
    assert not prepared.exists()


def test_live_cutover_fsyncs_parent_after_each_tree_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    prepared = target.parent / ".aoa-routing.sdk-canonical-prepared"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    events: list[tuple[str, Path, Path | None]] = []
    real_replace = os.replace
    real_fsync_directory = CUTOVER_BACKEND.fsync_directory

    def record_replace(source: Path, destination: Path) -> None:
        events.append(("replace", Path(source), Path(destination)))
        real_replace(source, destination)

    def record_fsync_directory(path: Path) -> None:
        events.append(("fsync_directory", Path(path), None))
        real_fsync_directory(path)

    monkeypatch.setattr(CUTOVER_BACKEND.os, "replace", record_replace)
    monkeypatch.setattr(
        CUTOVER_BACKEND,
        "fsync_directory",
        record_fsync_directory,
    )

    CUTOVER_BACKEND.materialize(parsed)

    for pair in {
        (target, rollback_root),
        (prepared, target),
    }:
        rename_index = events.index(("replace", *pair))
        assert events[rename_index + 1] == (
            "fsync_directory",
            target.parent,
            None,
        )


def test_rollback_rejects_corrupt_predecessor_before_restore(
    tmp_path: Path,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout
    write_json(
        rollback_root / "generated/task_to_surface_hints.json",
        {"tampered": True},
    )

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    restored = run_cutover(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )

    assert restored.returncode == 1
    assert "predecessor rollback file digest drifted" in json.loads(
        restored.stdout
    )["error"]
    assert target.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()
    assert rollback_root.is_dir()
    assert not retained.exists()


@pytest.mark.parametrize("failing_replace_call", [1, 2])
def test_failed_rollback_swap_removes_marker_and_preserves_retryable_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_replace_call: int,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )
    replace_calls = 0
    real_replace = os.replace

    def fail_selected_replace(source: Path, destination: Path) -> None:
        nonlocal replace_calls
        swap_pair = (Path(source), Path(destination))
        if swap_pair in {
            (target, retained),
            (rollback_root, target),
        }:
            replace_calls += 1
            if replace_calls == failing_replace_call:
                raise PermissionError("injected rollback swap failure")
        real_replace(source, destination)

    monkeypatch.setattr(
        CUTOVER_BACKEND.os,
        "replace",
        fail_selected_replace,
    )

    with pytest.raises(
        PermissionError,
        match="injected rollback swap failure",
    ):
        CUTOVER_BACKEND.rollback(parsed)

    assert target.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()
    assert rollback_root.is_dir()
    assert not retained.exists()
    assert not rollback_root.joinpath(
        "manifest/routing_g5_compatibility_rollback.json"
    ).exists()


@pytest.mark.parametrize(
    "termination_point",
    ["before_first_swap", "between_swaps", "after_second_swap"],
)
def test_retry_recovers_each_process_termination_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    termination_point: str,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )
    real_replace = os.replace

    def terminate_at_selected_boundary(
        source: Path,
        destination: Path,
    ) -> None:
        pair = (Path(source), Path(destination))
        if (
            termination_point == "before_first_swap"
            and pair == (target, retained)
        ):
            raise KeyboardInterrupt("injected process termination")
        real_replace(source, destination)
        if (
            termination_point == "between_swaps"
            and pair == (target, retained)
        ):
            raise KeyboardInterrupt("injected process termination")
        if (
            termination_point == "after_second_swap"
            and pair == (rollback_root, target)
        ):
            raise KeyboardInterrupt("injected process termination")

    monkeypatch.setattr(
        CUTOVER_BACKEND.os,
        "replace",
        terminate_at_selected_boundary,
    )
    with pytest.raises(
        KeyboardInterrupt,
        match="injected process termination",
    ):
        CUTOVER_BACKEND.rollback(parsed)

    if termination_point == "before_first_swap":
        assert target.is_dir()
        assert rollback_root.is_dir()
        assert not retained.exists()
    elif termination_point == "between_swaps":
        assert not target.exists()
        assert rollback_root.is_dir()
        assert retained.is_dir()
    else:
        assert target.is_dir()
        assert not rollback_root.exists()
        assert retained.is_dir()

    monkeypatch.setattr(CUTOVER_BACKEND.os, "replace", real_replace)
    recovered = CUTOVER_BACKEND.rollback(parsed)

    assert recovered["restored"] is True
    assert recovered["retry_state"] in {
        "fresh_restore",
        "continued_after_first_swap",
        "already_restored",
    }
    assert recovered["idempotent_retry"] is (
        termination_point == "after_second_swap"
    )
    assert target.joinpath("predecessor.txt").is_file()
    assert target.joinpath(
        "manifest/routing_g5_compatibility_rollback.json"
    ).is_file()
    assert retained.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()


def test_rollback_marker_is_durable_before_tree_swap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )
    marker_path = rollback_root.joinpath(
        "manifest/routing_g5_compatibility_rollback.json"
    )
    events: list[tuple[str, Path, Path | None]] = []
    real_replace = os.replace
    real_fsync_file = CUTOVER_BACKEND.fsync_file
    real_fsync_directory = CUTOVER_BACKEND.fsync_directory

    def record_replace(source: Path, destination: Path) -> None:
        events.append(("replace", Path(source), Path(destination)))
        real_replace(source, destination)

    def record_fsync_file(path: Path) -> None:
        events.append(("fsync_file", Path(path), None))
        real_fsync_file(path)

    def record_fsync_directory(path: Path) -> None:
        events.append(("fsync_directory", Path(path), None))
        real_fsync_directory(path)

    monkeypatch.setattr(CUTOVER_BACKEND.os, "replace", record_replace)
    monkeypatch.setattr(CUTOVER_BACKEND, "fsync_file", record_fsync_file)
    monkeypatch.setattr(
        CUTOVER_BACKEND,
        "fsync_directory",
        record_fsync_directory,
    )

    CUTOVER_BACKEND.rollback(parsed)

    marker_rename_index = next(
        index
        for index, event in enumerate(events)
        if event[0] == "replace" and event[2] == marker_path
    )
    assert events[marker_rename_index - 1][0] == "fsync_file"
    assert events[marker_rename_index + 1] == (
        "fsync_directory",
        marker_path.parent,
        None,
    )
    first_tree_swap_index = events.index(
        ("replace", target, retained)
    )
    assert marker_rename_index < first_tree_swap_index


def test_rollback_parent_fsync_failure_restores_retryable_initial_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = make_fixture(tmp_path)
    target = tmp_path / "runtime/Knowledge/federation/aoa-routing"
    make_predecessor_root(target, fixture)
    rollback_root = target.parent / "aoa-routing.pre-g5"
    activated = run_cutover(
        [
            "materialize",
            *exact_args(fixture, target),
            "--authorized-live-cutover",
            "--rollback-root",
            str(rollback_root),
            "--operator-change-ref",
            "test-g5-change",
        ]
    )
    assert activated.returncode == 0, activated.stderr + activated.stdout

    retained = target.parent / "aoa-routing.sdk-canonical-retained"
    parsed = CUTOVER_BACKEND.build_parser().parse_args(
        rollback_args(
            fixture,
            target=target,
            rollback_root=rollback_root,
            retain_root=retained,
        )
    )
    real_fsync_directory = CUTOVER_BACKEND.fsync_directory
    parent_failure_injected = False

    def fail_first_transaction_parent_fsync(path: Path) -> None:
        nonlocal parent_failure_injected
        if Path(path) == target.parent and not parent_failure_injected:
            parent_failure_injected = True
            raise OSError("injected parent fsync failure")
        real_fsync_directory(path)

    monkeypatch.setattr(
        CUTOVER_BACKEND,
        "fsync_directory",
        fail_first_transaction_parent_fsync,
    )

    with pytest.raises(OSError, match="injected parent fsync failure"):
        CUTOVER_BACKEND.rollback(parsed)

    assert target.joinpath(
        "manifest/federation_mirror_manifest.json"
    ).is_file()
    assert rollback_root.is_dir()
    assert not retained.exists()
    assert not rollback_root.joinpath(
        "manifest/routing_g5_compatibility_rollback.json"
    ).exists()
