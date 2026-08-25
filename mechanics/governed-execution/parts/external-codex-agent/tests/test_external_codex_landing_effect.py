from __future__ import annotations

import hashlib
import json
import os
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

from external_codex_landing_effect import (  # noqa: E402
    LANDING_EFFECTS,
    MAX_GRANT_BYTES,
    RUNTIME_WIDE_FORBIDDEN_EFFECTS,
    LandingEffectGrantError,
    admit_landing_effect_grant,
    landing_effect_grant_allows,
    load_landing_effect_grant,
    validate_landing_effect_grant,
)


AT = datetime(2026, 8, 24, 12, tzinfo=UTC)
ZERO_DIGEST = "sha256:" + "0" * 64
REF_DIGEST = "sha256:" + "1" * 64


def _ref(owner: str, artifact: str, schema: str) -> dict[str, str]:
    return {
        "owner_repo": owner,
        "artifact_ref": artifact,
        "source_ref": "source-ref:landing-fixture",
        "artifact_digest": REF_DIGEST,
        "schema_ref": "schemas/fixture.json",
        "schema_version": schema,
    }


def _grant(
    *,
    effects: list[str] | None = None,
    target_kind: str = "pull_request",
    review_status: str = "approved",
    expires_at: str = "2026-08-25T00:00:00Z",
) -> dict[str, Any]:
    if target_kind == "branch":
        target = {
            "kind": "branch",
            "branch": "refs/heads/main",
            "base_revision": "e" * 40,
        }
    else:
        target = {
            "kind": "pull_request",
            "pull_request_id": "pr:42",
            "base_branch": "refs/heads/main",
            "head_branch": "refs/heads/feature",
            "base_revision": "e" * 40,
            "head_revision": "f" * 40,
        }
    grant: dict[str, Any] = {
        "$schema": "schemas/external-codex-governed-landing-effect-grant.schema.json",
        "schema_version": "abyss_stack_external_codex_governed_landing_effect_grant_v1",
        "grant_id": "grant:landing-fixture",
        "capability_id": "governed_git_landing_v1",
        "grant_ref": _ref(
            "abyss-stack",
            "runtime/landing-grants/grant-landing-fixture.json",
            "abyss_stack_external_codex_governed_landing_effect_grant_v1",
        ),
        "goal_ref": _ref("codex-goal", "goal:fixture", "goal-v1"),
        "holder_ref": _ref(
            "codex-goal", "holder:fixture", "holder-v1"
        )
        | {"incarnation_id": "incarnation:fixture"},
        "repository": {
            "repository_id": "abyss-stack/abyss-stack",
            "revision": "e" * 40,
        },
        "target": target,
        "allowed_effects": effects or ["push", "pull_request", "merge"],
        "review": {
            "required": True,
            "posture": "independent_review",
            "status": review_status,
            "reviewer_ref": _ref("aoa-agents", "holder:reviewer", "holder-v1"),
            "evidence_ref": _ref("abyss-stack", "review:fixture", "review-v1"),
        },
        "return_posture": {
            "owner_ref": _ref("codex-goal", "holder:master", "holder-v1"),
            "route": "holder:codex-master:fixture",
            "status": "review_required",
            "wake_condition": "validated-return",
        },
        "issued_at": "2026-08-23T00:00:00Z",
        "expires_at": expires_at,
    }
    grant["grant_ref"][
        "schema_ref"
    ] = "schemas/external-codex-governed-landing-effect-grant.schema.json"
    semantic = deepcopy(grant)
    semantic["grant_ref"]["artifact_digest"] = ZERO_DIGEST
    grant["grant_ref"]["artifact_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return grant


def _raw(grant: dict[str, Any]) -> bytes:
    return (
        json.dumps(grant, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _raw_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _refresh_semantic_digest(grant: dict[str, Any]) -> None:
    semantic = deepcopy(grant)
    semantic["grant_ref"]["artifact_digest"] = ZERO_DIGEST
    grant["grant_ref"]["artifact_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(
            semantic,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _request(grant: dict[str, Any], *, effect: str | None = None) -> dict[str, Any]:
    request = {
        key: deepcopy(grant[key])
        for key in (
            "goal_ref",
            "holder_ref",
            "repository",
            "target",
            "review",
            "return_posture",
        )
    }
    if effect is None:
        request["allowed_effects"] = list(grant["allowed_effects"])
    else:
        request["effect"] = effect
    return request


def test_landing_effect_abi_keeps_four_landing_effects_inside_ten_effect_closure() -> None:
    assert LANDING_EFFECTS == {"commit", "push", "pull_request", "merge"}
    assert RUNTIME_WIDE_FORBIDDEN_EFFECTS == {
        "commit",
        "push",
        "pull_request",
        "merge",
        "tag",
        "release",
        "publication",
        "service_mutation",
        "secret_access",
        "global_config_mutation",
    }


def test_exact_grant_binds_goal_holder_repository_target_review_and_return() -> None:
    grant = _grant()
    raw = _raw(grant)

    admitted = admit_landing_effect_grant(
        grant,
        _request(grant),
        grant_raw=raw,
        expected_artifact_digest=_raw_digest(raw),
        at=AT,
    )

    assert admitted["admission"]["status"] == "admitted"
    assert admitted["admission"]["effects"] == sorted(grant["allowed_effects"])
    assert admitted["holder_ref"]["incarnation_id"] == "incarnation:fixture"
    assert admitted["return_posture"]["status"] == "review_required"


def test_exact_grant_can_bind_a_pull_request_target() -> None:
    grant = _grant()
    grant["target"] = {
        "kind": "pull_request",
        "pull_request_id": "pr:43",
        "base_branch": "refs/heads/main",
        "head_branch": "refs/heads/feature",
        "base_revision": "e" * 40,
        "head_revision": "f" * 40,
    }
    _refresh_semantic_digest(grant)

    admitted = admit_landing_effect_grant(
        grant,
        _request(grant),
        grant_raw=_raw(grant),
        expected_artifact_digest=_raw_digest(_raw(grant)),
        at=AT,
    )

    assert admitted["target"]["kind"] == "pull_request"
    assert admitted["target"]["pull_request_id"] == "pr:43"
    assert admitted["target"]["head_revision"] == "f" * 40


@pytest.mark.parametrize("repository_id", ["../..", "./.git", "owner/.."])
def test_repository_id_rejects_traversal_components(repository_id: str) -> None:
    grant = _grant()
    grant["repository"]["repository_id"] = repository_id
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_schema_invalid"


@pytest.mark.parametrize(
    "ref_path",
    [
        ("goal_ref",),
        ("holder_ref",),
        ("review", "reviewer_ref"),
        ("review", "evidence_ref"),
        ("return_posture", "owner_ref"),
    ],
)
def test_owner_references_reject_zero_digest(ref_path: tuple[str, ...]) -> None:
    grant = _grant()
    reference: dict[str, Any] = grant
    for key in ref_path:
        reference = reference[key]
    reference["artifact_digest"] = ZERO_DIGEST
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_schema_invalid"


def test_revision_coordinates_reject_trailing_newlines() -> None:
    for ref_path in (
        ("repository", "revision"),
        ("target", "base_revision"),
        ("target", "head_revision"),
    ):
        grant = _grant()
        reference: dict[str, Any] = grant
        for key in ref_path[:-1]:
            reference = reference[key]
        field = ref_path[-1]
        reference[field] += "\n"
        _refresh_semantic_digest(grant)

        with pytest.raises(LandingEffectGrantError) as exc:
            validate_landing_effect_grant(grant)
        assert exc.value.code == "landing_effect_grant_schema_invalid"


def test_commit_cannot_share_a_grant_with_push_or_merge() -> None:
    for downstream_effect in ("push", "merge"):
        grant = _grant(effects=["commit", downstream_effect])
        with pytest.raises(LandingEffectGrantError) as exc:
            validate_landing_effect_grant(grant)
        assert exc.value.code == "landing_effect_grant_schema_invalid"


def test_pull_request_target_requires_immutable_head_revision() -> None:
    grant = _grant()
    del grant["target"]["head_revision"]
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_schema_invalid"


def test_pull_request_head_revision_is_exactly_request_bound() -> None:
    grant = _grant()
    raw = _raw(grant)
    request = _request(grant)
    request["target"]["head_revision"] = "a" * 40

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            request,
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_binding_mismatch"


def test_admission_requires_an_independent_artifact_digest() -> None:
    grant = _grant()
    raw = _raw(grant)

    assert not landing_effect_grant_allows(
        grant,
        _request(grant),
        grant_raw=raw,
        at=AT,
    )
    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_artifact_unbound"


def test_reviewer_identity_must_differ_from_holder() -> None:
    grant = _grant()
    grant["review"]["reviewer_ref"] = {
        key: value
        for key, value in grant["holder_ref"].items()
        if key != "incarnation_id"
    }
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_review_invalid"


def test_reviewer_stable_identity_cannot_be_versioned_away() -> None:
    grant = _grant()
    grant["review"]["reviewer_ref"] = _ref(
        grant["holder_ref"]["owner_repo"],
        grant["holder_ref"]["artifact_ref"],
        "reviewer-v2",
    )
    grant["review"]["reviewer_ref"]["source_ref"] = "source-ref:reviewer-v2"
    grant["review"]["reviewer_ref"]["artifact_digest"] = "sha256:" + "1" * 64
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_review_invalid"


def test_duplicate_artifact_members_are_rejected() -> None:
    grant = _grant()
    raw = _raw(grant).replace(
        b'"grant_id": "grant:landing-fixture",',
        b'"grant_id": "grant:landing-fixture",\n  "grant_id": "grant:landing-fixture",',
        1,
    )

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_duplicate_key"


def test_branch_target_allows_only_single_commit_or_push_effects() -> None:
    for effect in ("commit", "push"):
        grant = _grant(target_kind="branch", effects=[effect])
        raw = _raw(grant)

        admitted = admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
        assert admitted["target"]["kind"] == "branch"

    invalid = _grant(target_kind="branch", effects=["merge"])
    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(invalid)
    assert exc.value.code == "landing_effect_grant_schema_invalid"


@pytest.mark.parametrize(
    "invalid_ref",
    ["refs/heads/main..backup", "refs/heads/topic.lock", "refs/heads/foo//bar"],
)
def test_invalid_git_refs_are_rejected_by_git_ref_rules(invalid_ref: str) -> None:
    grant = _grant(target_kind="branch", effects=["commit"])
    grant["target"]["branch"] = invalid_ref
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_target_invalid"


def test_loader_uses_bounded_no_follow_descriptor_and_byte_digest(tmp_path: Path) -> None:
    grant = _grant()
    raw = _raw(grant)
    path = tmp_path / "grant.json"
    path.write_bytes(raw)

    loaded, loaded_raw = load_landing_effect_grant(
        path,
        expected_digest=_raw_digest(raw),
    )
    assert loaded == grant
    assert loaded_raw == raw

    with pytest.raises(LandingEffectGrantError) as unbound_exc:
        load_landing_effect_grant(path)
    assert unbound_exc.value.code == "landing_effect_grant_artifact_unbound"

    link = tmp_path / "grant-link.json"
    link.symlink_to(path)
    with pytest.raises(LandingEffectGrantError) as link_exc:
        load_landing_effect_grant(link, expected_digest=_raw_digest(raw))
    assert link_exc.value.code == "landing_effect_grant_unavailable"


def test_loader_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO fixtures are unavailable on this platform")
    fifo = tmp_path / "grant.fifo"
    os.mkfifo(fifo)

    with pytest.raises(LandingEffectGrantError) as exc:
        load_landing_effect_grant(fifo, expected_digest="sha256:" + "0" * 64)
    assert exc.value.code == "landing_effect_grant_unavailable"


def test_loader_rejects_oversized_artifacts_before_json_parse(tmp_path: Path) -> None:
    path = tmp_path / "oversized-grant.json"
    path.write_bytes(b"{" + (b" " * MAX_GRANT_BYTES))

    with pytest.raises(LandingEffectGrantError) as exc:
        load_landing_effect_grant(path, expected_digest="sha256:" + "0" * 64)
    assert exc.value.code == "landing_effect_grant_too_large"


def test_large_json_integer_is_a_typed_artifact_denial(tmp_path: Path) -> None:
    integer_limit = sys.get_int_max_str_digits()
    if integer_limit == 0:
        pytest.skip("this Python has no JSON integer digit limit")

    grant = _grant()
    raw = _raw(grant).replace(
        b'"grant_id": "grant:landing-fixture"',
        b'"grant_id": ' + (b"9" * (integer_limit + 1)),
    )
    path = tmp_path / "large-integer-grant.json"
    path.write_bytes(raw)

    with pytest.raises(LandingEffectGrantError) as load_exc:
        load_landing_effect_grant(path, expected_digest=_raw_digest(raw))
    assert load_exc.value.code == "landing_effect_grant_unavailable"

    with pytest.raises(LandingEffectGrantError) as direct_exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert direct_exc.value.code == "landing_effect_grant_artifact_invalid"


def test_direct_admission_rejects_oversized_artifact_before_json_parse() -> None:
    grant = _grant()
    base_raw = _raw(grant)
    raw = base_raw + (b" " * (MAX_GRANT_BYTES + 1 - len(base_raw)))

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_too_large"


def test_direct_admission_bounds_untrusted_mapping_after_artifact_validation() -> None:
    grant = _grant()
    raw = _raw(grant)
    oversized_mapping = deepcopy(grant)
    oversized_mapping["grant_id"] = "x" * (MAX_GRANT_BYTES + 1)

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            oversized_mapping,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_too_large"


def test_request_mapping_is_bounded_before_absent_grant_denial() -> None:
    request = {"untrusted": "x" * (MAX_GRANT_BYTES + 1)}

    assert not landing_effect_grant_allows(None, request)
    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(None, request)
    assert exc.value.code == "landing_effect_request_too_large"


def test_git_ref_validation_ignores_ambient_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_git = tmp_path / "git"
    fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    grant = _grant(target_kind="branch", effects=["commit"])
    grant["target"]["branch"] = "refs/heads/main..backup"
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_target_invalid"


def test_git_ref_validation_ignores_ambient_trace_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = tmp_path / "git-trace.json"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace_path))

    validate_landing_effect_grant(_grant())

    assert not trace_path.exists()


def test_absent_grant_is_default_denied() -> None:
    grant = _grant()
    request = _request(grant)

    assert not landing_effect_grant_allows(None, request)
    with pytest.raises(LandingEffectGrantError, match="no landing-effect grant") as exc:
        admit_landing_effect_grant(None, request)
    assert exc.value.code == "landing_effect_grant_absent"


def test_malformed_request_is_default_denied() -> None:
    grant = _grant()
    raw = _raw(grant)

    assert not landing_effect_grant_allows(None, None)  # type: ignore[arg-type]
    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant) | {"wildcard": True},
            grant_raw=raw,
            at=AT,
        )
    assert exc.value.code == "landing_effect_request_invalid"


@pytest.mark.parametrize(
    "malformed",
    [
        {"grant_ref": {"artifact_digest": {"nested": object()}}},
        {"grant_ref": {"artifact_digest": {"nested": {1, 2}}}},
        {"grant_ref": {"artifact_digest": {"nested": b"bytes"}}},
    ],
)
def test_malformed_mapping_values_are_default_denied_without_typeerror(
    malformed: dict[str, Any],
) -> None:
    assert not landing_effect_grant_allows(malformed, {})

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(malformed, {})
    assert exc.value.code == "landing_effect_grant_not_json"


def test_cyclic_mapping_is_default_denied_with_normalized_error() -> None:
    cyclic: dict[str, Any] = {}
    cyclic["self"] = cyclic

    assert not landing_effect_grant_allows(cyclic, {})

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(cyclic, {})
    assert exc.value.code == "landing_effect_grant_not_json"


def test_deeply_nested_mapping_is_default_denied_with_schema_invalid_error() -> None:
    deeply_nested: dict[str, Any] = {}
    current = deeply_nested
    for _ in range(256):
        child: dict[str, Any] = {}
        current["nested"] = child
        current = child

    assert not landing_effect_grant_allows(deeply_nested, {})

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(deeply_nested, {})
    assert exc.value.code == "landing_effect_grant_schema_invalid"


def test_boundary_timestamp_overflow_is_a_typed_time_denial() -> None:
    grant = _grant()
    grant["issued_at"] = "0001-01-01T00:00:00+14:00"
    _refresh_semantic_digest(grant)

    with pytest.raises(LandingEffectGrantError) as exc:
        validate_landing_effect_grant(grant)
    assert exc.value.code == "landing_effect_grant_time_invalid"


def test_admission_time_overflow_is_a_typed_time_denial() -> None:
    grant = _grant()
    raw = _raw(grant)
    boundary = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14)))

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=boundary,
        )
    assert exc.value.code == "landing_effect_grant_time_invalid"


def test_stale_grant_is_default_denied() -> None:
    grant = _grant(expires_at="2026-08-24T11:59:59Z")
    raw = _raw(grant)

    assert not landing_effect_grant_allows(
        grant,
        _request(grant),
        grant_raw=raw,
        expected_artifact_digest=_raw_digest(raw),
        at=AT,
    )
    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_stale"


def test_wider_grant_is_rejected_for_single_effect_request() -> None:
    grant = _grant(effects=["push", "merge"])
    raw = _raw(grant)

    assert not landing_effect_grant_allows(
        grant,
        _request(grant, effect="commit"),
        grant_raw=raw,
        expected_artifact_digest=_raw_digest(raw),
        at=AT,
    )
    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            _request(grant, effect="commit"),
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_scope_wider"


def test_contradictory_target_or_holder_is_rejected() -> None:
    grant = _grant()
    raw = _raw(grant)
    request = _request(grant)
    request["target"]["head_branch"] = "refs/heads/release"

    with pytest.raises(LandingEffectGrantError) as exc:
        admit_landing_effect_grant(
            grant,
            request,
            grant_raw=raw,
            expected_artifact_digest=_raw_digest(raw),
            at=AT,
        )
    assert exc.value.code == "landing_effect_grant_binding_mismatch"


def test_review_pending_and_artifact_drift_are_rejected() -> None:
    pending = _grant(review_status="required")
    pending_raw = _raw(pending)
    with pytest.raises(LandingEffectGrantError) as pending_exc:
        admit_landing_effect_grant(
            pending,
            _request(pending),
            grant_raw=pending_raw,
            expected_artifact_digest=_raw_digest(pending_raw),
            at=AT,
        )
    assert pending_exc.value.code == "landing_effect_grant_review_pending"

    grant = _grant()
    raw = _raw(grant)
    with pytest.raises(LandingEffectGrantError) as drift_exc:
        admit_landing_effect_grant(
            grant,
            _request(grant),
            grant_raw=raw,
            expected_artifact_digest="sha256:" + "f" * 64,
            at=AT,
        )
    assert drift_exc.value.code == "landing_effect_grant_artifact_drift"


def test_schema_validation_rejects_non_landing_effects_and_unknown_fields() -> None:
    grant = _grant(effects=["commit"])
    assert validate_landing_effect_grant(grant)["allowed_effects"] == ["commit"]

    invalid = deepcopy(grant)
    invalid["allowed_effects"] = ["release"]
    with pytest.raises(LandingEffectGrantError) as effect_exc:
        validate_landing_effect_grant(invalid)
    assert effect_exc.value.code == "landing_effect_grant_schema_invalid"

    invalid = deepcopy(grant)
    invalid["unbound"] = True
    with pytest.raises(LandingEffectGrantError) as field_exc:
        validate_landing_effect_grant(invalid)
    assert field_exc.value.code == "landing_effect_grant_schema_invalid"
