from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

BridgeConfigLoader = Callable[[list[str]], dict[str, Any]]
BridgeStringIterator = Callable[[Any], list[str]]


ACTIVE_ORGAN_DELIVERY_SCHEMA = (
    "mechanics/federation-seams/parts/memo-seam/schemas/"
    "active-organ-runtime-delivery-receipt.schema.json"
)
ACTIVE_ORGAN_DELIVERY_EXAMPLES = (
    "mechanics/federation-seams/parts/memo-seam/examples"
)
ACTIVE_ORGAN_DELIVERY_NEGATIVE_EXAMPLES = (
    "active_organ_runtime_delivery_receipt.negative-examples.json"
)


def _json_path(error_path: Any) -> str:
    return "/".join(str(item) for item in error_path) or "<root>"


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_active_organ_runtime_delivery_payload(
    payload: object,
    *,
    schema: object,
) -> list[str]:
    errors = [
        f"{_json_path(error.absolute_path)}: {error.message}"
        for error in sorted(
            Draft202012Validator(
                schema,
                format_checker=FormatChecker(),
            ).iter_errors(payload),
            key=lambda item: list(item.absolute_path),
        )
    ]
    if not isinstance(payload, dict):
        return errors

    policy = payload.get("policy_binding")
    target = payload.get("delivery_target")
    if isinstance(policy, dict) and isinstance(target, dict):
        if policy.get("consumer_id") != target.get("consumer_id"):
            errors.append(
                "consumer_id: policy_binding and delivery_target must match exactly"
            )

    recorded_at = _parse_datetime(payload.get("recorded_at"))
    expires_at = _parse_datetime(payload.get("expires_at"))
    state = payload.get("delivery_state")
    if recorded_at is not None and expires_at is not None:
        if state == "expired" and recorded_at < expires_at:
            errors.append(
                "recorded_at: expired receipt cannot precede expires_at"
            )
        if state != "expired" and recorded_at > expires_at:
            errors.append(
                "recorded_at: non-expired receipt cannot outlive expires_at"
            )

    anchor = payload.get("anchor_binding")
    result = payload.get("result")
    admission = payload.get("admission")
    if (
        state == "suppressed"
        and isinstance(result, dict)
        and result.get("reason_code") == "anchor_not_current"
        and isinstance(anchor, dict)
        and anchor.get("freshness") == "current"
    ):
        errors.append(
            "anchor_binding/freshness: anchor_not_current requires non-current freshness"
        )
    if (
        state == "suppressed"
        and isinstance(result, dict)
        and result.get("reason_code") == "policy_silence"
        and isinstance(admission, dict)
        and admission.get("state") != "admitted"
    ):
        errors.append(
            "admission/state: policy_silence requires an admitted packet"
        )

    return errors


def apply_active_organ_delivery_negative_mutations(
    payload: dict[str, Any],
    mutations: object,
) -> dict[str, Any]:
    if not isinstance(mutations, dict):
        raise ValueError("negative example set must be an object")
    result = deepcopy(payload)
    for pointer, value in mutations.items():
        if not isinstance(pointer, str) or not pointer.startswith("/"):
            raise ValueError(f"invalid JSON pointer: {pointer!r}")
        parts = [
            part.replace("~1", "/").replace("~0", "~")
            for part in pointer[1:].split("/")
        ]
        current: Any = result
        for part in parts[:-1]:
            if not isinstance(current, dict) or part not in current:
                raise ValueError(f"negative example pointer is unresolved: {pointer}")
            current = current[part]
        if not isinstance(current, dict) or parts[-1] not in current:
            raise ValueError(f"negative example pointer is unresolved: {pointer}")
        current[parts[-1]] = value
    return result


def validate_active_organ_runtime_delivery_contract(
    errors: list[str],
    *,
    root: Path,
) -> None:
    schema_path = root / ACTIVE_ORGAN_DELIVERY_SCHEMA
    examples_root = root / ACTIVE_ORGAN_DELIVERY_EXAMPLES
    negative_path = examples_root / ACTIVE_ORGAN_DELIVERY_NEGATIVE_EXAMPLES
    required_paths = [schema_path, negative_path]
    missing = [path for path in required_paths if not path.is_file()]
    if missing:
        for path in missing:
            errors.append(
                f"{path.relative_to(root)} must exist for C20 RuntimeDeliveryReceipt"
            )
        return

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        errors.append(
            f"{ACTIVE_ORGAN_DELIVERY_SCHEMA} must be a valid Draft 2020-12 schema: {exc}"
        )
        return

    expected_states = {
        "attempted",
        "delivered",
        "suppressed",
        "expired",
        "failed",
    }
    observed_states: set[str] = set()
    positive_examples = sorted(examples_root.glob("*.example.json"))
    for path in positive_examples:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(root)} must be valid JSON: {exc}")
            continue
        observed_states.add(str(payload.get("delivery_state")))
        for error in validate_active_organ_runtime_delivery_payload(
            payload,
            schema=schema,
        ):
            errors.append(f"{path.relative_to(root)}: {error}")
    if observed_states != expected_states:
        errors.append(
            "C20 positive examples must cover exactly attempted, delivered, "
            "suppressed, expired, and failed"
        )

    try:
        negative_corpus = json.loads(negative_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{negative_path.relative_to(root)} must be valid JSON: {exc}")
        return
    if not isinstance(negative_corpus, dict) or negative_corpus.get(
        "schema_version"
    ) != "active_organ_runtime_delivery_receipt_negative_examples_v1":
        errors.append(
            f"{negative_path.relative_to(root)} must use the versioned C20 negative corpus"
        )
        return
    cases = negative_corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(
            f"{negative_path.relative_to(root)} must contain executable negative cases"
        )
        return
    for case in cases:
        if not isinstance(case, dict):
            errors.append("C20 negative case must be an object")
            continue
        base_path = examples_root / str(case.get("base_example", ""))
        try:
            base = json.loads(base_path.read_text(encoding="utf-8"))
            mutated = apply_active_organ_delivery_negative_mutations(
                base,
                case.get("set"),
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(
                f"C20 negative case {case.get('case_id', '<unknown>')} is invalid: {exc}"
            )
            continue
        negative_errors = validate_active_organ_runtime_delivery_payload(
            mutated,
            schema=schema,
        )
        if not negative_errors:
            errors.append(
                f"C20 negative case {case.get('case_id', '<unknown>')} must fail closed"
            )
            continue
        expected = case.get("expected_error")
        if not isinstance(expected, str) or not any(
            expected in error for error in negative_errors
        ):
            errors.append(
                f"C20 negative case {case.get('case_id', '<unknown>')} must expose "
                f"expected error token {expected!r}"
            )


def validate_memo_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-memo-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-memo-candidate")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "memo-seam"
        / "docs"
        / "MEMO_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-memo",
        "/memo/",
        "aoa-export-memo-candidate",
        "Logs/memo-exports/",
        "RuntimeDeliveryReceipt",
        "active-organ-runtime-delivery-receipt.schema.json",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md must mention {snippet}")

    schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-memo-export-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if schema.get("title") != "abyss-stack runtime memo export candidate":
        errors.append("runtime-memo-export-candidate.schema.json must describe abyss-stack runtime memo export candidate")

    example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_memo_export_candidate.checkpoint_export.example.json"
        ).read_text(encoding="utf-8")
    )
    if example.get("artifact_kind") != "aoa.runtime-memo-export-candidate":
        errors.append("runtime memo export example must use artifact_kind aoa.runtime-memo-export-candidate")
    if example.get("exported_by") != "scripts/aoa-export-memo-candidate":
        errors.append("runtime memo export example must use exported_by scripts/aoa-export-memo-candidate")

    validate_active_organ_runtime_delivery_contract(errors, root=root)


def validate_eval_runtime_seam(
    errors: list[str],
    *,
    root: Path,
    bridge_config_loader: BridgeConfigLoader,
    bridge_string_iterator: BridgeStringIterator,
) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "aoa-export-runtime-evidence-selection" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-runtime-evidence-selection")
    if "aoa-export-artifact-hook-candidate" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-export-artifact-hook-candidate")
    if "aoa-run-memo-contradiction-integrity" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-run-memo-contradiction-integrity")
    if "aoa-a2a-return-closeout-dry-run" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention aoa-a2a-return-closeout-dry-run")

    _validate_eval_seam_doc(errors, root=root)
    _validate_eval_upstream_compatibility(
        errors,
        root=root,
        bridge_config_loader=bridge_config_loader,
        bridge_string_iterator=bridge_string_iterator,
    )
    _validate_eval_candidate_exports(errors, root=root)
    _validate_a2a_return_dry_run(errors, root=root)


def _validate_eval_seam_doc(errors: list[str], *, root: Path) -> None:
    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "eval-seam"
        / "docs"
        / "EVAL_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-evals",
        "/evals/",
        "aoa-export-runtime-evidence-selection",
        "aoa-export-artifact-hook-candidate",
        "aoa-a2a-return-closeout-dry-run",
        "aoa-run-memo-contradiction-integrity",
        "Logs/eval-exports/",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md must mention {snippet}")


def _validate_eval_upstream_compatibility(
    errors: list[str],
    *,
    root: Path,
    bridge_config_loader: BridgeConfigLoader,
    bridge_string_iterator: BridgeStringIterator,
) -> None:
    compatibility_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY.md"
    ).read_text(encoding="utf-8")
    compatibility_detail = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "federation-checks"
        / "docs"
        / "UPSTREAM_COMPATIBILITY_DETAIL.md"
    ).read_text(encoding="utf-8")
    bridge_config = bridge_config_loader(errors)
    bridge_strings = bridge_string_iterator(bridge_config)
    for snippet in (
        "single active bridge",
        "UPSTREAM_COMPATIBILITY_DETAIL.md",
        "upstream-compatibility-bridge.json",
        "Clean local route",
    ):
        if snippet not in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must keep the lightweight active bridge and mention {snippet}"
            )
    for bridge_value in bridge_strings:
        is_detail_value = any(
            marker in bridge_value for marker in ("phase-alpha", "a2a_wave", "playbook_automation_seeds", "seed_staging")
        )
        if is_detail_value and bridge_value in compatibility_doc:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md "
                f"must route detailed upstream value {bridge_value} through UPSTREAM_COMPATIBILITY_DETAIL.md"
            )
        if is_detail_value and bridge_value not in compatibility_detail:
            errors.append(
                "mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY_DETAIL.md "
                f"must mention {bridge_value}"
            )


def _validate_eval_candidate_exports(errors: list[str], *, root: Path) -> None:
    evidence_schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-eval-evidence-selection-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if evidence_schema.get("title") != "abyss-stack runtime eval evidence selection candidate":
        errors.append(
            "runtime-eval-evidence-selection-candidate.schema.json must describe abyss-stack runtime eval evidence selection candidate"
        )

    evidence_example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_eval_evidence_selection_candidate.workhorse-local.example.json"
        ).read_text(encoding="utf-8")
    )
    if evidence_example.get("artifact_kind") != "aoa.runtime-eval-evidence-selection-candidate":
        errors.append(
            "runtime eval evidence selection example must use artifact_kind aoa.runtime-eval-evidence-selection-candidate"
        )
    if evidence_example.get("exported_by") != "scripts/aoa-export-runtime-evidence-selection":
        errors.append(
            "runtime eval evidence selection example must use exported_by scripts/aoa-export-runtime-evidence-selection"
        )

    hook_schema = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "schemas"
            / "runtime-artifact-hook-candidate.schema.json"
        ).read_text(encoding="utf-8")
    )
    if hook_schema.get("title") != "abyss-stack runtime artifact hook candidate":
        errors.append("runtime-artifact-hook-candidate.schema.json must describe abyss-stack runtime artifact hook candidate")

    hook_example = json.loads(
        (
            root
            / "mechanics"
            / "governed-execution"
            / "parts"
            / "candidate-exports"
            / "examples"
            / "runtime_artifact_hook_candidate.self-agent-checkpoint-rollout.example.json"
        ).read_text(encoding="utf-8")
    )
    if hook_example.get("artifact_kind") != "aoa.runtime-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use artifact_kind aoa.runtime-artifact-hook-candidate")
    if hook_example.get("exported_by") != "scripts/aoa-export-artifact-hook-candidate":
        errors.append("runtime artifact hook example must use exported_by scripts/aoa-export-artifact-hook-candidate")


def _validate_a2a_return_dry_run(errors: list[str], *, root: Path) -> None:
    a2a_doc = (
        root
        / "mechanics"
        / "runtime-repair"
        / "parts"
        / "a2a-return-dry-run"
        / "docs"
        / "A2A_RETURN_DRY_RUN.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-a2a-return-closeout-dry-run",
        "request_family",
        "upstream_request_kind",
        "UPSTREAM_COMPATIBILITY.md",
        "dry_run",
        "live_automation",
        "Logs/a2a-return-closeouts/",
    ):
        if snippet not in a2a_doc:
            errors.append(f"mechanics/runtime-repair/parts/a2a-return-dry-run/docs/A2A_RETURN_DRY_RUN.md must mention {snippet}")

    a2a_schema = json.loads(
        (
            root
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "schemas"
            / "runtime-a2a-return-closeout-dry-run.schema.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_schema.get("title") != "abyss-stack runtime A2A return closeout dry-run":
        errors.append(
            "runtime-a2a-return-closeout-dry-run.schema.json must describe abyss-stack runtime A2A return closeout dry-run"
        )

    a2a_example = json.loads(
        (
            root
            / "mechanics"
            / "runtime-repair"
            / "parts"
            / "a2a-return-dry-run"
            / "examples"
            / "runtime_a2a_return_closeout_dry_run.example.json"
        ).read_text(encoding="utf-8")
    )
    if a2a_example.get("artifact_kind") != "aoa.runtime-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use artifact_kind aoa.runtime-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("exported_by") != "scripts/aoa-a2a-return-closeout-dry-run":
        errors.append(
            "runtime A2A return closeout dry-run example must use exported_by scripts/aoa-a2a-return-closeout-dry-run"
        )
    if a2a_example.get("dry_run") is not True:
        errors.append("runtime A2A return closeout dry-run example must set dry_run true")
    if a2a_example.get("live_automation") is not False:
        errors.append("runtime A2A return closeout dry-run example must set live_automation false")
    if a2a_example.get("request_family") != "a2a-return-closeout":
        errors.append("runtime A2A return closeout dry-run example must set request_family a2a-return-closeout")
    if a2a_example.get("request_kind") != "a2a-return-closeout-request":
        errors.append("runtime A2A return closeout dry-run example must set clean request_kind")
    if "UPSTREAM_COMPATIBILITY_BRIDGE.a2a_return_closeout.upstream_request_kind" not in str(
        a2a_example.get("upstream_request_kind", "")
    ):
        errors.append("runtime A2A return closeout dry-run example must route upstream_request_kind through the bridge")


def validate_playbook_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "playbooks/activation" not in runbook_doc and "/playbooks/" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention playbook advisory seam inspection")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "playbook-seam"
        / "docs"
        / "PLAYBOOK_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-playbooks",
        "/playbooks/",
        "PLAYBOOK.md",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-playbooks",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md must mention {snippet}")


def validate_kag_runtime_seam(errors: list[str], *, root: Path) -> None:
    runbook_doc = (root / "docs" / "operations" / "RUNBOOK.md").read_text(encoding="utf-8")
    if "/kag/" not in runbook_doc and "kag/registry" not in runbook_doc:
        errors.append("docs/operations/RUNBOOK.md must mention KAG advisory seam inspection")

    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "kag-seam"
        / "docs"
        / "KAG_RUNTIME_SEAM.md"
    ).read_text(encoding="utf-8")
    for snippet in (
        "aoa-kag",
        "tos-source",
        "/kag/",
        "Tree-of-Sophia",
        "advisory-only",
        "aoa-sync-federation-surfaces --layer aoa-kag",
        "aoa-sync-federation-surfaces --layer tos-source",
    ):
        if snippet not in seam_doc:
            errors.append(f"mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md must mention {snippet}")


def validate_routing_canary_runtime_seam(
    errors: list[str],
    *,
    root: Path,
) -> None:
    backend = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "sync-wrapper"
        / "aoa_routing_canary.py"
    ).read_text(encoding="utf-8")
    route_api = (
        root / "config-templates" / "Services" / "route-api" / "app" / "main.py"
    ).read_text(encoding="utf-8")
    seam_doc = (
        root
        / "mechanics"
        / "federation-seams"
        / "parts"
        / "sync-wrapper"
        / "README.md"
    ).read_text(encoding="utf-8")
    deployment_doc = (
        root / "docs" / "install" / "DEPLOYMENT.md"
    ).read_text(encoding="utf-8")

    backend_snippets = (
        "sdk_g5_candidate_canary",
        "--isolated",
        "--authorized-live-canary",
        "--rollback-root",
        "--candidate-retain-root",
        "--operator-change-ref",
        "canonical_switch_authorized",
        "subject-store aggregate digest",
    )
    for snippet in backend_snippets:
        if snippet not in backend:
            errors.append(
                "routing canary backend must preserve fail-closed activation "
                f"contract token {snippet}"
            )

    route_api_snippets = (
        "ROUTING_SDK_CANARY_POSTURE",
        "routing_sdk_canary_provenance_reasons",
        "canary_ready",
        "routing SDK canary is non-canonical and cannot satisfy runtime closure",
    )
    for snippet in route_api_snippets:
        if snippet not in route_api:
            errors.append(
                "route-api must preserve routing canary/closure separation "
                f"token {snippet}"
            )

    for snippet in (
        "scripts/aoa-routing-canary",
        "runtime_canary",
        "closure_ready",
        "rollback",
    ):
        if snippet not in seam_doc:
            errors.append(
                "mechanics/federation-seams/parts/sync-wrapper/README.md must "
                f"mention {snippet}"
            )
    for snippet in (
        "scripts/aoa-routing-canary",
        "--authorized-live-canary",
        "--rollback-root",
    ):
        if snippet not in deployment_doc:
            errors.append(
                f"docs/install/DEPLOYMENT.md must mention routing canary token {snippet}"
            )
