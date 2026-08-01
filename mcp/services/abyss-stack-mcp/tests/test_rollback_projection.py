from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from abyss_stack_mcp.contracts import RuntimeObservation, RuntimeSubject
from abyss_stack_mcp.observation import _digest
from abyss_stack_mcp.rollback_projection import (
    RollbackProjectionError,
    _source_contract,
    project_rollback_readiness,
)
from test_rollback_candidate import PACKAGE_DIGEST, _build, _inputs
from test_stack_mcp import NOW


def _write(path: Path, payload: dict, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    path.chmod(mode)
    return path


def _review_inputs(tmp_path: Path) -> dict[str, Path]:
    paths = _inputs(tmp_path)
    candidate = _build(paths)
    candidate_path = _write(tmp_path / "candidate.json", candidate)
    eval_root = tmp_path / "eval"
    files = {
        "EVAL.md": "# rollback contract\n",
        "eval.yaml": "name: aoa-organ-access-admission-integrity\n",
        "schemas/rollback-readiness-candidate.schema.json": "{}\n",
        "reports/rollback-review.schema.json": "{}\n",
        "runners/review_rollback.py": "# exact runner\n",
    }
    for relative, content in files.items():
        target = eval_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    review = {
        "schema_version": "aoa_organ_access_rollback_review_v1",
        "eval_name": "aoa-organ-access-admission-integrity",
        "bundle_status": "bounded",
        "reviewed_at": (NOW + timedelta(minutes=2)).isoformat(),
        "candidate": {
            "candidate_ref": candidate_path.absolute().as_posix(),
            "candidate_digest": _digest(candidate),
            "candidate_id": candidate["candidate_id"],
            "organ_id": "aoa-kag",
            "policy_family": "read",
        },
        "source_contract": _source_contract(eval_root),
        "candidate_validation": {
            "accepted_by_source_contract": True,
            "issues": [],
        },
        "negative_suite": {
            "verdict": "supports bounded claim",
            "scenario_count": 11,
            "passed_count": 11,
            "failed_count": 0,
            "report_digest": "sha256:" + "5" * 64,
        },
        "verdict": "supported_bounded",
        "rollback_candidate_supported": True,
        "rollback_executed": False,
        "admission_change_authorized": False,
        "higher_effect_authorized": False,
        "actual_effects": [],
        "limitations": ["Bounded review only."],
        "claim_limit": "No rollback execution, admission, or effects.",
    }
    paths.update(
        {
            "candidate": candidate_path,
            "review": _write(tmp_path / "review.json", review),
            "eval_root": eval_root,
            "record_root": tmp_path / "records",
        }
    )
    return paths


def _project(paths: dict[str, Path], output: Path | None = None):
    return project_rollback_readiness(
        review_path=paths["review"],
        candidate_path=paths["candidate"],
        observation_path=paths["observation"],
        deployment_record_path=paths["manifest"],
        eval_root=paths["eval_root"],
        record_root=paths["record_root"],
        registry_path=paths["registry"],
        targets_path=paths["targets"],
        stack_source_root=paths["source_root"],
        stack_runtime_root=paths["runtime_root"],
        secret_dir=paths["secret_dir"],
        output_path=output,
        clock=lambda: NOW + timedelta(minutes=3),
        git_identity=lambda *_: (PACKAGE_DIGEST, 5, 100),
        deployed_identity=lambda *_: (PACKAGE_DIGEST, 5, 100),
    )


def test_projects_exact_non_executed_rollback_readiness(tmp_path: Path) -> None:
    paths = _review_inputs(tmp_path)
    output = tmp_path / "rollback.overlay.json"
    overlay, digest, record = _project(paths, output)
    rollback = overlay.subjects[0].rollback

    assert digest.startswith("sha256:")
    assert rollback is not None and rollback.ready is True
    assert rollback.last_known_good_canary_route.endswith("/last-known-good")
    assert rollback.proved_target is not None
    assert rollback.proof_ref == record.as_posix()
    assert rollback.evidence.evidence_refs[0].owner == "aoa-evals"
    assert output.stat().st_mode & 0o777 == 0o600
    assert record.stat().st_mode & 0o777 == 0o600

    observation = RuntimeObservation.model_validate_json(
        paths["observation"].read_text(encoding="utf-8")
    )
    live = observation.subjects[0].model_dump(mode="json")
    live["rollback"] = rollback.model_dump(mode="json")
    RuntimeSubject.model_validate(live)


def test_rejects_eval_source_contract_drift(tmp_path: Path) -> None:
    paths = _review_inputs(tmp_path)
    (paths["eval_root"] / "EVAL.md").write_text("# changed\n", encoding="utf-8")

    with pytest.raises(RollbackProjectionError, match="source contract"):
        _project(paths)


def test_rejects_candidate_content_address_drift(tmp_path: Path) -> None:
    paths = _review_inputs(tmp_path)
    candidate = json.loads(paths["candidate"].read_text(encoding="utf-8"))
    candidate["last_known_good"]["credential_class"] = "other-read"
    _write(paths["candidate"], candidate)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    review["candidate"]["candidate_digest"] = _digest(candidate)
    _write(paths["review"], review)

    with pytest.raises(RollbackProjectionError, match="content address"):
        _project(paths)


def test_rejects_review_that_reports_an_effect(tmp_path: Path) -> None:
    paths = _review_inputs(tmp_path)
    review = json.loads(paths["review"].read_text(encoding="utf-8"))
    review["actual_effects"] = ["restart"]
    _write(paths["review"], review)

    with pytest.raises(RollbackProjectionError, match="reports effects"):
        _project(paths)


def test_rejects_candidate_observation_drift(tmp_path: Path) -> None:
    paths = _review_inputs(tmp_path)
    observation = json.loads(paths["observation"].read_text(encoding="utf-8"))
    observation["subjects"][0]["registry"]["registry_state"] = "admitted"
    _write(paths["observation"], observation)

    with pytest.raises(RollbackProjectionError, match="another runtime observation"):
        _project(paths)
