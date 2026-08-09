#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from abyss_stack_mcp.contracts import (  # noqa: E402
    RuntimeObservation,
    RuntimePlanCandidate,
)
from abyss_stack_mcp.organ_access import StackOrganAccessManifest  # noqa: E402
from abyss_stack_mcp.effect import (  # noqa: E402
    InternalEffectApproval,
    InternalEffectDenialReceipt,
    InternalEffectRecoveryReceipt,
    InternalEffectReceipt,
)
from abyss_stack_mcp.preflight import (  # noqa: E402
    MCPPreflightReport,
    ManagedContourCatalog,
)
from abyss_stack_mcp.preflight_sweep import MCPPreflightSweepStatus  # noqa: E402
from abyss_stack_mcp.managed_catalog import ManagedContourTopology  # noqa: E402
from abyss_stack_mcp.keeper_specs import KeeperSpecBuildStatus  # noqa: E402
from abyss_stack_mcp.admission_automation import (  # noqa: E402
    AdmissionAutomationStatus,
)
from abyss_stack_mcp.system_status import MCPSystemStatus  # noqa: E402


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
DIGESTS = {
    name: "sha256:" + value * 64
    for name, value in (
        ("source", "a"),
        ("package", "b"),
        ("deploy", "c"),
        ("schema", "d"),
        ("registry", "e"),
        ("sync_target", "f"),
        ("deploy_target", "0"),
        ("manifest", "1"),
        ("rollback_manifest", "2"),
    )
}


def deployment_manifest_ref(digest: str) -> str:
    return (
        "Logs/mcp/deployments/records/"
        + digest.removeprefix("sha256:")
        + ".json"
    )


def evidence(
    name: str,
    *,
    owner: str = "abyss-stack",
    evidence_ref: str | None = None,
) -> dict[str, Any]:
    ref = {
        "owner": owner,
        "evidence_ref": evidence_ref or f"example://runtime/{name}",
        "revision": "public-example-revision",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }
    return {
        "state": "exact",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "evidence_refs": [ref],
        "reason_codes": [],
    }


def observation_example() -> dict[str, Any]:
    return {
        "schema_version": "abyss_stack_runtime_observation_v1",
        "provider": "abyss-stack",
        "provider_watermark": "public-example-not-live",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "contains_secrets": False,
        "subjects": [
            {
                "organ_id": "aoa-kag",
                "policy_family": "read",
                "owners": {
                    "source_owner": "aoa-kag",
                    "access_owner": "aoa-kag",
                    "runtime_owner": "abyss-stack",
                    "proof_owner": "aoa-evals",
                    "acceptance_owner": "aoa-kag",
                },
                "credential_class": "aoa-kag-read-example",
                "effect_classes": ["observe", "derive"],
                "source": {
                    "revision": "source-example-revision",
                    "tree_digest": DIGESTS["source"],
                    "expected_sync_tree_digest": DIGESTS["sync_target"],
                    "evidence": evidence("source"),
                },
                "package": {
                    "name": "aoa-kag-mcp",
                    "version": "0.0.0-example",
                    "source_revision": "source-example-revision",
                    "artifact_digest": DIGESTS["package"],
                    "expected_deploy_tree_digest": DIGESTS["deploy_target"],
                    "evidence": evidence("package"),
                },
                "deploy": {
                    "revision": "deploy-example-revision",
                    "tree_digest": DIGESTS["deploy"],
                    "manifest_ref": deployment_manifest_ref(
                        DIGESTS["manifest"]
                    ),
                    "manifest_digest": DIGESTS["manifest"],
                    "deployed_at": NOW.isoformat(),
                    "evidence": evidence(
                        "deploy",
                        evidence_ref=deployment_manifest_ref(
                            DIGESTS["manifest"]
                        ),
                    ),
                },
                "process": {
                    "unit_name": "aoa-organ-mcp-read@aoa-kag.service",
                    "executable_ref": "/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py",
                    "process_identity": "aoa-kag-mcp/0.0.0-example",
                    "active": True,
                    "evidence": evidence("process"),
                },
                "endpoint": {
                    "transport": "streamable-http",
                    "endpoint_ref": "http://127.0.0.1:5425/mcp",
                    "protocol_versions": ["2026-07-28"],
                    "ready": True,
                    "server_schema_digest": DIGESTS["schema"],
                    "evidence": evidence("endpoint"),
                },
                "registry": {
                    "registry_id": "abyss-private-example",
                    "registry_digest": DIGESTS["registry"],
                    "registry_state": "shadow",
                    "evidence": evidence("registry"),
                },
                "consumers": [
                    {
                        "consumer_id": "codex-example",
                        "registration_ref": "example://consumer/aoa-kag",
                        "registered": True,
                        "observed_schema_digest": DIGESTS["schema"],
                        "observed_protocol_versions": ["2026-07-28"],
                        "evidence": evidence(
                            "consumer",
                            evidence_ref="example://consumer/aoa-kag",
                        ),
                    }
                ],
                "freshness": {
                    "state": "exact",
                    "provider_watermark": "owner-example-watermark",
                    "observed_at": NOW.isoformat(),
                    "expires_at": (NOW + timedelta(hours=1)).isoformat(),
                    "evidence_refs": evidence("freshness")["evidence_refs"],
                    "reason_codes": [],
                },
                "proof": {
                    "verdict": "passed",
                    "proof_ref": "example://runtime/central-proof",
                    "evaluated_at": NOW.isoformat(),
                    "proved_source_revision": "source-example-revision",
                    "proved_source_tree_digest": DIGESTS["source"],
                    "proved_package_digest": DIGESTS["package"],
                    "proved_deploy_revision": "deploy-example-revision",
                    "proved_deploy_tree_digest": DIGESTS["deploy"],
                    "proved_deploy_manifest_digest": DIGESTS["manifest"],
                    "proved_process_identity": "aoa-kag-mcp/0.0.0-example",
                    "proved_server_schema_digest": DIGESTS["schema"],
                    "proved_consumer_registration_ref": (
                        "example://consumer/aoa-kag"
                    ),
                    "proved_canary_route": (
                        "example://canary-route/aoa-kag"
                    ),
                    "proved_canary_ref": "example://runtime/canary",
                    "evidence": evidence("central-proof", owner="aoa-evals"),
                },
                "acceptance": {
                    "accepted": True,
                    "acceptance_ref": "example://runtime/acceptance",
                    "accepted_at": NOW.isoformat(),
                    "accepted_source_revision": "source-example-revision",
                    "accepted_package_digest": DIGESTS["package"],
                    "evidence": evidence("acceptance", owner="aoa-kag"),
                },
                "canary": {
                    "succeeded": True,
                    "result_grounded": True,
                    "canary_route": "example://canary-route/aoa-kag",
                    "canary_ref": "example://runtime/canary",
                    "evidence": evidence("canary"),
                },
                "rollback": {
                    "ready": True,
                    "rollback_route": "example://rollback/aoa-kag",
                    "last_known_good_consumer_registration_ref": (
                        "example://consumer/aoa-kag"
                    ),
                    "last_known_good_package_digest": DIGESTS["package"],
                    "last_known_good_deploy_revision": "deploy-example-revision",
                    "last_known_good_deploy_tree_digest": DIGESTS["deploy"],
                    "last_known_good_deploy_manifest_ref": (
                        deployment_manifest_ref(DIGESTS["rollback_manifest"])
                    ),
                    "last_known_good_deploy_manifest_digest": (
                        DIGESTS["rollback_manifest"]
                    ),
                    "last_known_good_unit_name": (
                        "aoa-organ-mcp-read@aoa-kag.service"
                    ),
                    "last_known_good_credential_class": (
                        "aoa-kag-read-example"
                    ),
                    "last_known_good_executable_ref": (
                        "/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py"
                    ),
                    "last_known_good_process_identity": (
                        "aoa-kag-mcp/0.0.0-example"
                    ),
                    "last_known_good_canary_route": (
                        "example://canary-route/aoa-kag/last-known-good"
                    ),
                    "last_known_good_canary_ref": (
                        "example://canary/aoa-kag/last-known-good"
                    ),
                    "proof_ref": "example://runtime/rollback",
                    "proved_target": {
                        "consumer_registration_ref": (
                            "example://consumer/aoa-kag"
                        ),
                        "package_digest": DIGESTS["package"],
                        "deploy_revision": "deploy-example-revision",
                        "deploy_tree_digest": DIGESTS["deploy"],
                        "deploy_manifest_ref": deployment_manifest_ref(
                            DIGESTS["rollback_manifest"]
                        ),
                        "deploy_manifest_digest": DIGESTS["rollback_manifest"],
                        "unit_name": "aoa-organ-mcp-read@aoa-kag.service",
                        "credential_class": "aoa-kag-read-example",
                        "executable_ref": (
                            "/srv/AbyssOS/.codex/bin/aoa-kag-mcp-server.py"
                        ),
                        "process_identity": "aoa-kag-mcp/0.0.0-example",
                        "canary_route": (
                            "example://canary-route/aoa-kag/last-known-good"
                        ),
                        "canary_ref": (
                            "example://canary/aoa-kag/last-known-good"
                        ),
                    },
                    "evidence": evidence("rollback", owner="aoa-evals"),
                },
            }
        ],
    }


def schema(filename: str, model: type) -> str:
    payload = model.model_json_schema()
    payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    payload["$id"] = f"https://8dionysus.github.io/schemas/abyss-stack-mcp/{filename}"
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def contour_supplement() -> dict[str, Any]:
    manifest_path = SERVICE_ROOT / "organ-access.v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    by_policy = {item["policy_family"]: item for item in manifest["capabilities"]}
    contours = []
    for policy in ("candidate", "internal_effect"):
        capability = by_policy[policy]
        contours.append(
            {
                "contour_id": policy.replace("_", "-"),
                "authority_class": policy,
                "policy_family": policy,
                "credential_class": capability["credential_class"],
                "principal_id": f"abyss-stack-{policy.replace('_', '-')}-principal",
                "capabilities": [capability],
                "observation_route": f"owner://abyss-stack/observation/{policy}",
                "rollback_route": f"owner://abyss-stack/rollback/{policy}",
            }
        )
    return {
        "schema_version": "aoa_organ_contour_supplement_v1",
        "supplement_id": "abyss-stack-additional-contours-v1",
        "organ_id": "abyss-stack",
        "source_owner": "abyss-stack",
        "source_evidence": {
            "owner": "abyss-stack",
            "evidence_ref": (
                "repo://abyss-stack/mcp/services/abyss-stack-mcp/"
                "organ-access.v1.json"
            ),
            "revision": source_digest,
            "observed_at": "2026-08-08T08:03:38Z",
        },
        "owner_decision_ref": (
            "owner://abyss-stack/decision/ABYSS-STACK-D-0105"
        ),
        "contours": contours,
        "admission_asserted": False,
        "proof_asserted": False,
        "acceptance_asserted": False,
        "runtime_identity_asserted": False,
        "contains_secrets": False,
    }


def rendered_outputs() -> dict[Path, str]:
    return {
        SERVICE_ROOT / "schemas" / "runtime-observation.schema.json": schema(
            "runtime-observation.schema.json",
            RuntimeObservation,
        ),
        SERVICE_ROOT / "schemas" / "runtime-plan-candidate.schema.json": schema(
            "runtime-plan-candidate.schema.json",
            RuntimePlanCandidate,
        ),
        SERVICE_ROOT / "schemas" / "organ-access.schema.json": schema(
            "organ-access.schema.json",
            StackOrganAccessManifest,
        ),
        SERVICE_ROOT / "schemas" / "internal-effect-approval.schema.json": schema(
            "internal-effect-approval.schema.json",
            InternalEffectApproval,
        ),
        SERVICE_ROOT / "schemas" / "internal-effect-receipt.schema.json": schema(
            "internal-effect-receipt.schema.json",
            InternalEffectReceipt,
        ),
        SERVICE_ROOT / "schemas" / "internal-effect-denial-receipt.schema.json": schema(
            "internal-effect-denial-receipt.schema.json",
            InternalEffectDenialReceipt,
        ),
        SERVICE_ROOT / "schemas" / "internal-effect-recovery-receipt.schema.json": schema(
            "internal-effect-recovery-receipt.schema.json",
            InternalEffectRecoveryReceipt,
        ),
        SERVICE_ROOT / "schemas" / "managed-contours.schema.json": schema(
            "managed-contours.schema.json",
            ManagedContourCatalog,
        ),
        SERVICE_ROOT / "schemas" / "mcp-preflight-report.schema.json": schema(
            "mcp-preflight-report.schema.json",
            MCPPreflightReport,
        ),
        SERVICE_ROOT / "schemas" / "mcp-preflight-sweep.schema.json": schema(
            "mcp-preflight-sweep.schema.json",
            MCPPreflightSweepStatus,
        ),
        SERVICE_ROOT / "schemas" / "managed-contour-topology.schema.json": schema(
            "managed-contour-topology.schema.json",
            ManagedContourTopology,
        ),
        SERVICE_ROOT / "schemas" / "keeper-spec-build.schema.json": schema(
            "keeper-spec-build.schema.json",
            KeeperSpecBuildStatus,
        ),
        SERVICE_ROOT / "schemas" / "admission-automation-status.schema.json": schema(
            "admission-automation-status.schema.json",
            AdmissionAutomationStatus,
        ),
        SERVICE_ROOT / "schemas" / "mcp-system-status.schema.json": schema(
            "mcp-system-status.schema.json",
            MCPSystemStatus,
        ),
        SERVICE_ROOT / "examples" / "runtime-observation.public.example.json": (
            json.dumps(
                RuntimeObservation.model_validate(observation_example()).model_dump(
                    mode="json"
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ),
        SERVICE_ROOT / "organ-contour-supplement.v1.json": (
            json.dumps(contour_supplement(), indent=2, sort_keys=True) + "\n"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale: list[Path] = []
    for path, expected in rendered_outputs().items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == expected:
            continue
        stale.append(path)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    if args.check and stale:
        for path in stale:
            print(f"stale abyss-stack MCP contract: {path.relative_to(SERVICE_ROOT)}")
        return 1
    if not args.check:
        print(f"generated {len(rendered_outputs())} abyss-stack MCP artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
