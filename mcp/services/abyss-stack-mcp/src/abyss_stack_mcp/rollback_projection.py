"""Project bounded rollback readiness only onto its unchanged live target."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import (
    EvidenceRef,
    LinkEvidence,
    RollbackObservation,
    RollbackProofTarget,
    RuntimeObservation,
)
from .core import _reject_secret_material
from .observation import (
    DEFAULT_REGISTRY_PATH,
    DEFAULT_TARGETS_PATH,
    MAX_OVERLAY_FUTURE_SKEW,
    ObservationProducerError,
    RuntimeEvidenceOverlay,
    RuntimeEvidenceOverlaySubject,
    _digest,
    _parse_timestamp,
    _read_json,
    _write_atomic,
)
from .rollback_candidate import (
    DEFAULT_SECRET_DIR,
    DEFAULT_STACK_RUNTIME_ROOT,
    DEFAULT_STACK_SOURCE_ROOT,
    MAX_TTL_SECONDS,
    RollbackCandidateError,
    _file_digest,
    _git_package_identity,
    _tree_identity,
    build_rollback_candidate,
)


EXPECTED_EVAL_NAME = "aoa-organ-access-admission-integrity"
EXPECTED_REFS = {
    "eval_ref": f"evals/boundary/{EXPECTED_EVAL_NAME}/EVAL.md",
    "manifest_ref": f"evals/boundary/{EXPECTED_EVAL_NAME}/eval.yaml",
    "candidate_schema_ref": (
        f"evals/boundary/{EXPECTED_EVAL_NAME}/"
        "schemas/rollback-readiness-candidate.schema.json"
    ),
    "review_schema_ref": (
        f"evals/boundary/{EXPECTED_EVAL_NAME}/"
        "reports/rollback-review.schema.json"
    ),
    "runner_ref": (
        f"evals/boundary/{EXPECTED_EVAL_NAME}/runners/review_rollback.py"
    ),
}


class RollbackProjectionError(ObservationProducerError):
    """The bounded eval review cannot support live rollback readiness."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RollbackProjectionError(f"{label} must be an object")
    return value


def _source_contract(eval_root: Path) -> dict[str, str]:
    return {
        **EXPECTED_REFS,
        "eval_digest": _file_digest(eval_root / "EVAL.md", "eval contract"),
        "manifest_digest": _file_digest(
            eval_root / "eval.yaml", "eval manifest"
        ),
        "candidate_schema_digest": _file_digest(
            eval_root / "schemas" / "rollback-readiness-candidate.schema.json",
            "rollback candidate schema",
        ),
        "review_schema_digest": _file_digest(
            eval_root / "reports" / "rollback-review.schema.json",
            "rollback review schema",
        ),
        "runner_digest": _file_digest(
            eval_root / "runners" / "review_rollback.py",
            "rollback review runner",
        ),
    }


def _validate_review(
    review: dict[str, Any],
    candidate: dict[str, Any],
    *,
    candidate_path: Path,
    eval_root: Path,
) -> datetime:
    required = {
        "schema_version": "aoa_organ_access_rollback_review_v1",
        "eval_name": EXPECTED_EVAL_NAME,
        "bundle_status": "bounded",
        "verdict": "supported_bounded",
        "rollback_candidate_supported": True,
        "rollback_executed": False,
        "admission_change_authorized": False,
        "higher_effect_authorized": False,
    }
    if any(review.get(key) != value for key, value in required.items()):
        raise RollbackProjectionError(
            "aoa-evals review does not support bounded rollback readiness"
        )
    if review.get("actual_effects") not in ([], ()):
        raise RollbackProjectionError("aoa-evals rollback review reports effects")
    binding = _mapping(review.get("candidate"), "review candidate binding")
    if (
        binding.get("candidate_ref")
        != candidate_path.expanduser().absolute().as_posix()
        or binding.get("candidate_digest") != _digest(candidate)
        or binding.get("candidate_id") != candidate.get("candidate_id")
        or binding.get("organ_id") != candidate.get("organ_id")
        or binding.get("policy_family") != candidate.get("policy_family")
    ):
        raise RollbackProjectionError("aoa-evals review names another candidate")
    validation = _mapping(
        review.get("candidate_validation"), "candidate validation"
    )
    if validation.get("accepted_by_source_contract") is not True or validation.get(
        "issues"
    ) not in ([], ()):
        raise RollbackProjectionError("candidate did not pass its source contract")
    suite = _mapping(review.get("negative_suite"), "rollback negative suite")
    if (
        suite.get("verdict") != "supports bounded claim"
        or suite.get("scenario_count") != 11
        or suite.get("passed_count") != 11
        or suite.get("failed_count") != 0
    ):
        raise RollbackProjectionError("rollback negative suite did not pass")
    if _mapping(review.get("source_contract"), "review source contract") != (
        _source_contract(eval_root)
    ):
        raise RollbackProjectionError("aoa-evals rollback source contract differs")
    return _parse_timestamp(review.get("reviewed_at"), "reviewed_at")


def _unsigned_candidate_digest(candidate: dict[str, Any]) -> str:
    unsigned = dict(candidate)
    claimed = unsigned.pop("candidate_id", None)
    computed = _digest(unsigned)
    if claimed != computed:
        raise RollbackProjectionError("rollback candidate content address differs")
    return computed


def _static_candidate(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"candidate_id", "generated_at", "expires_at"}
    }


def _revalidate_live_candidate(
    candidate: dict[str, Any],
    observation: RuntimeObservation,
    observation_payload: dict[str, Any],
    *,
    observation_path: Path,
    deployment_record_path: Path,
    registry_path: Path,
    targets_path: Path,
    stack_source_root: Path,
    stack_runtime_root: Path,
    secret_dir: Path,
    git_identity: Callable[[Path, str, str], tuple[str, int, int]],
    deployed_identity: Callable[[Path], tuple[str, int, int]],
) -> tuple[Any, datetime, datetime]:
    if (
        candidate.get("schema_version")
        != "abyss_stack_mcp_rollback_candidate_v1"
        or candidate.get("issuer") != "abyss-stack"
        or candidate.get("organ_id") != "aoa-kag"
        or candidate.get("policy_family") != "read"
        or candidate.get("execution_authorized") is not False
        or candidate.get("admission_authorized") is not False
        or candidate.get("rollback_executed") is not False
        or candidate.get("contains_secrets") is not False
    ):
        raise RollbackProjectionError("rollback candidate exceeds its authority")
    _unsigned_candidate_digest(candidate)
    generated_at = _parse_timestamp(candidate.get("generated_at"), "generated_at")
    expires_at = _parse_timestamp(candidate.get("expires_at"), "expires_at")
    if expires_at <= generated_at:
        raise RollbackProjectionError("rollback candidate window is invalid")
    observation_binding = _mapping(
        candidate.get("observation"), "candidate observation binding"
    )
    if (
        observation_binding.get("observation_ref")
        != observation_path.expanduser().absolute().as_posix()
        or observation_binding.get("observation_digest") != _digest(observation_payload)
        or _parse_timestamp(
            observation_binding.get("generated_at"), "observation generated_at"
        )
        != observation.generated_at
        or _parse_timestamp(
            observation_binding.get("expires_at"), "observation expires_at"
        )
        != observation.expires_at
    ):
        raise RollbackProjectionError("candidate names another runtime observation")
    lkg = _mapping(candidate.get("last_known_good"), "last-known-good target")
    matches = [
        subject
        for subject in observation.subjects
        if subject.organ_id == candidate.get("organ_id")
        and subject.policy_family == candidate.get("policy_family")
    ]
    if len(matches) != 1:
        raise RollbackProjectionError("observation lacks the candidate contour")
    subject = matches[0]
    consumers = [
        consumer
        for consumer in subject.consumers
        if consumer.registration_ref == lkg.get("consumer_registration_ref")
    ]
    if len(consumers) != 1:
        raise RollbackProjectionError("candidate consumer is not uniquely live")
    try:
        rebuilt = build_rollback_candidate(
            observation_path=observation_path,
            deployment_record_path=deployment_record_path,
            registry_path=registry_path,
            consumer_id=consumers[0].consumer_id,
            targets_path=targets_path,
            stack_source_root=stack_source_root,
            stack_runtime_root=stack_runtime_root,
            secret_dir=secret_dir,
            ttl_seconds=MAX_TTL_SECONDS,
            clock=lambda: generated_at,
            git_identity=git_identity,
            deployed_identity=deployed_identity,
        )
    except RollbackCandidateError as exc:
        raise RollbackProjectionError(
            "unchanged live inputs no longer reproduce rollback readiness"
        ) from exc
    if _static_candidate(rebuilt) != _static_candidate(candidate):
        raise RollbackProjectionError("live rollback target differs from candidate")
    if _parse_timestamp(rebuilt["expires_at"], "rebuilt expires_at") < expires_at:
        raise RollbackProjectionError("candidate outlives independently rebuilt evidence")
    return subject, generated_at, expires_at


def project_rollback_readiness(
    *,
    review_path: Path,
    candidate_path: Path,
    observation_path: Path,
    deployment_record_path: Path,
    eval_root: Path,
    record_root: Path,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    targets_path: Path = DEFAULT_TARGETS_PATH,
    stack_source_root: Path = DEFAULT_STACK_SOURCE_ROOT,
    stack_runtime_root: Path = DEFAULT_STACK_RUNTIME_ROOT,
    secret_dir: Path = DEFAULT_SECRET_DIR,
    git_identity: Callable[
        [Path, str, str], tuple[str, int, int]
    ] = _git_package_identity,
    deployed_identity: Callable[[Path], tuple[str, int, int]] = _tree_identity,
    output_path: Path | None = None,
    clock: Callable[[], datetime] = _now,
) -> tuple[RuntimeEvidenceOverlay, str, Path]:
    review, _ = _read_json(review_path, "aoa-evals rollback review")
    candidate, _ = _read_json(candidate_path, "rollback candidate")
    observation_payload, _ = _read_json(observation_path, "runtime observation")
    for payload in (review, candidate, observation_payload):
        _reject_secret_material(payload)
    try:
        observation = RuntimeObservation.model_validate(observation_payload)
    except ValidationError as exc:
        raise RollbackProjectionError(
            "runtime observation failed contract validation"
        ) from exc
    now = clock().astimezone(timezone.utc)
    if observation.expires_at <= now:
        raise RollbackProjectionError("runtime observation is expired")
    subject, generated_at, expires_at = _revalidate_live_candidate(
        candidate,
        observation,
        observation_payload,
        observation_path=observation_path,
        deployment_record_path=deployment_record_path,
        registry_path=registry_path,
        targets_path=targets_path,
        stack_source_root=stack_source_root,
        stack_runtime_root=stack_runtime_root,
        secret_dir=secret_dir,
        git_identity=git_identity,
        deployed_identity=deployed_identity,
    )
    reviewed_at = _validate_review(
        review,
        candidate,
        candidate_path=candidate_path,
        eval_root=eval_root,
    )
    if (
        generated_at > reviewed_at
        or reviewed_at > now + MAX_OVERLAY_FUTURE_SKEW
        or expires_at <= now
    ):
        raise RollbackProjectionError("rollback review is stale or causally invalid")

    proof_digest = _digest(review)
    proof_record = (
        record_root.expanduser().absolute()
        / subject.organ_id
        / (proof_digest.removeprefix("sha256:") + ".json")
    )
    proof_record.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    proof_record.parent.chmod(0o700)
    if proof_record.exists():
        existing, _ = _read_json(proof_record, "immutable rollback proof record")
        if existing != review:
            raise RollbackProjectionError("rollback proof record content conflicts")
    else:
        _write_atomic(proof_record, review)
    proof_ref = proof_record.as_posix()
    evidence = LinkEvidence(
        state="exact",
        observed_at=reviewed_at,
        expires_at=expires_at,
        evidence_refs=(
            EvidenceRef(
                owner="aoa-evals",
                evidence_ref=proof_ref,
                revision=proof_digest,
                observed_at=reviewed_at,
                expires_at=expires_at,
            ),
        ),
    )
    lkg = _mapping(candidate.get("last_known_good"), "last-known-good target")
    proved_target = RollbackProofTarget.model_validate(lkg)
    rollback = RollbackObservation(
        ready=True,
        rollback_route=candidate["rollback_route"],
        last_known_good_consumer_registration_ref=(
            proved_target.consumer_registration_ref
        ),
        last_known_good_package_digest=proved_target.package_digest,
        last_known_good_deploy_revision=proved_target.deploy_revision,
        last_known_good_deploy_tree_digest=proved_target.deploy_tree_digest,
        last_known_good_deploy_manifest_ref=proved_target.deploy_manifest_ref,
        last_known_good_deploy_manifest_digest=proved_target.deploy_manifest_digest,
        last_known_good_unit_name=proved_target.unit_name,
        last_known_good_credential_class=proved_target.credential_class,
        last_known_good_executable_ref=proved_target.executable_ref,
        last_known_good_process_identity=proved_target.process_identity,
        last_known_good_canary_route=proved_target.canary_route,
        last_known_good_canary_ref=proved_target.canary_ref,
        proof_ref=proof_ref,
        proved_target=proved_target,
        evidence=evidence,
    )
    overlay = RuntimeEvidenceOverlay(
        generated_at=reviewed_at,
        expires_at=expires_at,
        contains_secrets=False,
        subjects=(
            RuntimeEvidenceOverlaySubject(
                organ_id=subject.organ_id,
                policy_family=subject.policy_family,
                rollback=rollback,
            ),
        ),
    )
    payload = overlay.model_dump(mode="json")
    _reject_secret_material(payload)
    digest = _digest(payload)
    if output_path is not None:
        _write_atomic(output_path, payload)
    return overlay, digest, proof_record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--deployment-record", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--record-root", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    parser.add_argument(
        "--stack-source-root", type=Path, default=DEFAULT_STACK_SOURCE_ROOT
    )
    parser.add_argument(
        "--stack-runtime-root", type=Path, default=DEFAULT_STACK_RUNTIME_ROOT
    )
    parser.add_argument("--secret-dir", type=Path, default=DEFAULT_SECRET_DIR)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        overlay, digest, record = project_rollback_readiness(
            review_path=args.review,
            candidate_path=args.candidate,
            observation_path=args.observation,
            deployment_record_path=args.deployment_record,
            eval_root=args.eval_root,
            record_root=args.record_root,
            registry_path=args.registry,
            targets_path=args.targets,
            stack_source_root=args.stack_source_root,
            stack_runtime_root=args.stack_runtime_root,
            secret_dir=args.secret_dir,
            output_path=args.output,
        )
    except (RollbackProjectionError, OSError, KeyError, ValidationError) as exc:
        print(f"rollback projection: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"output={args.output.expanduser().absolute()}")
    print(f"overlay_digest={digest}")
    print(f"proof_record={record}")
    print(f"proof_ref={overlay.subjects[0].rollback.proof_ref}")
    print("rollback_ready=true")
    print("rollback_executed=false")
    print("admission_authorized=false")
    print("contains_secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
