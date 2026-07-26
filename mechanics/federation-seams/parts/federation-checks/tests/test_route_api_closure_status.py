import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)
MODULE_PATH = REPO_ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py"
BRIDGE_CONFIG = json.loads(
    (REPO_ROOT / "config-templates" / "Configs" / "federation" / "upstream-compatibility-bridge.json").read_text(
        encoding="utf-8"
    )
)


def load_module():
    previous_fastapi = sys.modules.get("fastapi")
    fastapi_module = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def get(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def post(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def on_event(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi_module.FastAPI = FastAPI
    fastapi_module.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi_module

    spec = importlib.util.spec_from_file_location("route_api_main_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_fastapi is None:
            sys.modules.pop("fastapi", None)
        else:
            sys.modules["fastapi"] = previous_fastapi
    return module


class RouteAPIClosureStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def make_required_files(self, root: Path, layer_name: str) -> list[str]:
        rel_path = f"generated/{layer_name}.json"
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
        return [rel_path]

    def write_json(self, root: Path, rel_path: str, payload: object) -> None:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    def test_grafana_datasource_inventory_is_bounded_and_redacted(self) -> None:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        datasource_file = root / "prometheus.yml"
        datasource_file.write_text(
            """
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prom-main
    type: prometheus
    access: proxy
    url: http://user:secret@prometheus:9090
    isDefault: true
    editable: true
    jsonData:
      httpMethod: POST
    secureJsonData:
      basicAuthPassword: super-secret
""",
            encoding="utf-8",
        )

        inventory = self.module.grafana_datasource_inventory(root)
        entry = inventory["datasource_inventory"]["entries"][0]

        self.assertTrue(inventory["ok"])
        self.assertEqual(entry["datasource_uid_or_id"], "prom-main")
        self.assertEqual(entry["type"], "prometheus")
        self.assertEqual(entry["url"], "http://prometheus:9090")
        self.assertEqual(entry["json_data_keys"], ["httpMethod"])
        self.assertFalse(entry["redaction"]["secure_json_data_included"])
        self.assertFalse(entry["redaction"]["json_data_values_included"])
        self.assertNotIn("super-secret", json.dumps(inventory))

    def make_store(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        module = self.module
        runtime_templates = BRIDGE_CONFIG["runtime_evidence_templates"]
        routing_root = root / "aoa-routing"
        routing_required_files = self.make_required_files(
            routing_root,
            "aoa-routing",
        )
        routing_source_ref = "a" * 40
        routing_subject_digest = "sha256:" + ("b" * 64)
        routing_record_id = "routing-record-1"
        routing_manifest = {
            "schema": "abyss_stack_federation_mirror_manifest_v1",
            "layer": "aoa-routing",
            "source_git_commit": routing_source_ref,
            "required_file_count": len(routing_required_files),
            "required_files": routing_required_files,
            "file_sha256": {
                rel_path: hashlib.sha256(
                    (routing_root / rel_path).read_bytes()
                ).hexdigest()
                for rel_path in routing_required_files
            },
            "artifact_subject_digest": routing_subject_digest,
            "mirror_is_authority": False,
            "trust_verdict": {
                "ok": True,
                "schema": "abyss_machine_artifact_trust_gate_v1",
                "verdict": "allow",
                "artifact_class": "thin_routing_readmodel_bundle",
                "consumer_intent": "runtime",
                "subject_digest": routing_subject_digest,
                "record_id": routing_record_id,
                "require_latest": True,
                "latest_record_id": routing_record_id,
                "inspected_claims": {
                    "subject_identity": {
                        "subject_digest_expected": routing_subject_digest,
                        "subject_digest_matched": True,
                    }
                },
                "record": {
                    "record_id": routing_record_id,
                    "artifact_class": "thin_routing_readmodel_bundle",
                    "source_repo": "aoa-routing",
                    "source_ref": routing_source_ref,
                },
            },
        }

        return module.AppStore(
            agents=module.LayerStore(
                layer="aoa-agents",
                config_path=root / "aoa-agents.yaml",
                mirror_root=root / "aoa-agents",
                required_files=self.make_required_files(root / "aoa-agents", "aoa-agents"),
                flags={"thin_routing_only": True, "allow_free_text_task_routing": False},
                payloads={
                    "agents": {"layer": "aoa-agents", "version": "1", "agents": [{"name": "router"}]},
                    "tiers": {"layer": "aoa-agents", "version": "1", "model_tiers": [{"id": "t1"}]},
                    "bindings": {
                        "layer": "aoa-agents",
                        "version": "1",
                        "bindings": [
                            {
                                "phase": "route",
                                "tier_id": "t1",
                                "artifact_type": "task",
                                "role_names": ["router"],
                            }
                        ],
                    },
                    "cohorts": {
                        "layer": "aoa-agents",
                        "version": "1",
                        "cohort_patterns": [{"preferred_tier_ids": ["t1"], "allowed_role_sets": [["router"]]}],
                    },
                    "artifact_contracts": {"task": {"artifact_type": "task"}},
                },
            ),
            routing=module.LayerStore(
                layer="aoa-routing",
                config_path=root / "aoa-routing.yaml",
                mirror_root=routing_root,
                required_files=routing_required_files,
                flags={"advisory_only": True, "allow_free_text_task_routing": False},
                payloads={
                    "router": {
                        "router_version": 1,
                        "artifact_identity": {
                            "owner_repo": "aoa-routing",
                            "artifact_class": (
                                "thin_routing_readmodel_bundle"
                            ),
                            "abi_epoch": "aoa_routing_thin_router_v1",
                        },
                    },
                    "cross_repo_registry": {"registry_version": 1},
                    "surface_hints": {"version": "1"},
                    "tier_hints": {"version": "1"},
                    "recommended_paths": {"version": "1"},
                    "pairing_hints": {"version": "1"},
                    "kag_source_lift_relation_hints": {"version": "1"},
                    "federation_entrypoints": {
                        "schema_version": "aoa_routing_federation_entrypoints_v2"
                    },
                    "return_hints": {
                        "schema_version": "aoa_routing_return_navigation_hints_v2"
                    },
                    "tiny_model_entrypoints": {
                        "schema_version": "aoa_routing_tiny_model_entrypoints_v2"
                    },
                    "mirror_manifest": routing_manifest,
                },
            ),
            memo=module.LayerStore(
                layer="aoa-memo",
                config_path=root / "aoa-memo.yaml",
                mirror_root=root / "aoa-memo",
                required_files=self.make_required_files(root / "aoa-memo", "aoa-memo"),
                flags={"read_only": True, "export_only_writeback": True, "allow_free_text_recall": False},
                payloads={
                    "registry": {"version": "1"},
                    "catalog": {"catalog_version": "1"},
                    "object_catalog": {"catalog_version": "1"},
                    "checkpoint_contract": {"contract_id": "checkpoint-contract"},
                    "runtime_writeback_targets": {
                        "schema_version": 1,
                        "targets": [
                            {
                                "runtime_surface": "checkpoint_export",
                                "target_kind": "state_capsule",
                                "writeback_class": "checkpoint_export",
                                "requires_human_review": False,
                                "review_state_default": "captured",
                                "runtime_refs": ["docs/example.md"],
                                "notes": "fixture",
                            }
                        ],
                    },
                    "recall_contracts": {
                        "router": {"semantic": {}, "lineage": {}},
                        "object": {
                            "working": {},
                            "semantic": {},
                            "lineage": {},
                            "working_return": {"return_ready": True},
                        },
                    },
                },
            ),
            evals=module.LayerStore(
                layer="aoa-evals",
                config_path=root / "aoa-evals.yaml",
                mirror_root=root / "aoa-evals",
                required_files=self.make_required_files(root / "aoa-evals", "aoa-evals"),
                flags={"read_only": True, "export_only_evidence": True, "allow_free_text_eval_selection": False},
                payloads={
                    "catalog": {"catalog_version": "1"},
                    "capsules": {"capsule_version": "1"},
                    "sections": {"section_version": "1"},
                    "comparison_spine": {"comparison_spine_version": "1"},
                    "runtime_candidate_template_index": {
                        "schema_version": 1,
                        "templates": [
                            {
                                "template_kind": "artifact_to_verdict_hook",
                                "template_name": "fixture-hook",
                                "playbook_id": "AOA-P-0001",
                                "eval_anchor": "aoa-approval-boundary-adherence",
                                "verdict_bundle_ref": "repo:aoa-evals/bundles/fixture/EVAL.md",
                                "required_runtime_artifacts": ["approval_record"],
                                "review_required": True,
                                "source_example_ref": "examples/fixture.json",
                            }
                        ],
                    },
                    "runtime_evidence_templates": {
                        "workhorse-local": {},
                        "memo-recall-rerun": {
                            "selection_id": runtime_templates["memo-recall-rerun"]["upstream_selection_id"]
                        },
                        "memo-contradiction-gap": {
                            "selection_id": runtime_templates["memo-contradiction-gap"]["upstream_selection_id"]
                        },
                        "memo-contradiction-rerun": {
                            "selection_id": runtime_templates["memo-contradiction-rerun"]["upstream_selection_id"]
                        },
                    },
                    "hook_templates": {"restartable-inquiry-loop": {}},
                },
            ),
            playbooks=module.LayerStore(
                layer="aoa-playbooks",
                config_path=root / "aoa-playbooks.yaml",
                mirror_root=root / "aoa-playbooks",
                required_files=self.make_required_files(root / "aoa-playbooks", "aoa-playbooks"),
                flags={
                    "read_only": True,
                    "advisory_only": True,
                    "allow_runtime_execution": False,
                    "include_composition_surfaces": True,
                },
                payloads={
                    "registry": {
                        "playbooks": [
                            {
                                "id": "AOA-P-0001",
                                "name": "fixture-playbook",
                                "scenario": "fixture_scenario",
                            }
                        ]
                    },
                    "activation": [{"playbook_id": "AOA-P-0001", "name": "fixture-playbook"}],
                    "federation": [{"playbook_id": "AOA-P-0001", "name": "fixture-playbook"}],
                    "review_status": {
                        "schema_version": 1,
                        "playbooks": [
                            {
                                "playbook_id": "AOA-P-0001",
                                "playbook_name": "fixture-playbook",
                                "scenario": "fixture_scenario",
                                "gate_review_ref": "docs/gate-reviews/fixture-playbook.md",
                                "gate_verdict": "composition-landed",
                                "reviewed_run_count": 1,
                                "reviewed_run_refs": ["docs/real-runs/fixture-playbook.md"],
                                "latest_reviewed_run_ref": "docs/real-runs/fixture-playbook.md",
                                "minimum_evidence_threshold": "One reviewed fixture run.",
                                "next_trigger": "Only reopen if the fixture path materially changes.",
                                "composition_signal_summary": {
                                    "failure_or_follow_up": "Fixture follow-up posture is stable.",
                                    "adjunct_candidate": "Fixture adjunct posture is stable.",
                                },
                            }
                        ],
                    },
                    "review_packet_contracts": {
                        "schema_version": 1,
                        "playbooks": [
                            {
                                "playbook_id": "AOA-P-0001",
                                "playbook_name": "fixture-playbook",
                                "scenario": "fixture_scenario",
                                "expected_artifacts": ["approval_record"],
                                "eval_anchors": ["aoa-approval-boundary-adherence"],
                                "memo_runtime_surfaces": ["checkpoint_export"],
                                "candidate_packet_kinds": ["memo_candidate", "artifact_hook_candidate"],
                                "review_required": True,
                                "source_review_refs": ["docs/gate-reviews/fixture-playbook.md"],
                                "gate_verdict": "composition-landed",
                            }
                        ],
                    },
                    "handoffs": {"playbooks": [{"playbook_id": "AOA-P-0001", "name": "fixture-playbook"}]},
                    "failures": {"failures": [{"failure_id": "F-1"}]},
                    "subagent_recipes": {
                        "recipes": [{"recipe_id": "R-1", "name": "fixture-recipe", "playbook": "fixture-playbook"}]
                    },
                    "automation_plans": {
                        "seeds": [{"seed_id": "S-1", "name": "fixture-plan", "playbook": "fixture-playbook"}]
                    },
                    "composition_manifest": {"manifest_version": "1"},
                },
            ),
            kag=module.LayerStore(
                layer="aoa-kag",
                config_path=root / "aoa-kag.yaml",
                mirror_root=root / "aoa-kag",
                required_files=self.make_required_files(root / "aoa-kag", "aoa-kag"),
                flags={
                    "advisory_only": True,
                    "allow_free_text_querying": False,
                    "allow_runtime_reasoning_handoff": True,
                },
                payloads={
                    "registry": {"surfaces": [{"id": "AOA-K-0005"}, {"id": "AOA-K-0011"}]},
                    "federation_spine": {"repos": [{"repo": "Tree-of-Sophia"}]},
                    "tiny_consumer_bundle": {},
                    "reasoning_handoff_pack": {
                        "scenarios": [
                            {
                                "scenario_ref": "AOA-P-0008",
                                "compatible_query_modes": ["local_search"],
                            }
                        ]
                    },
                    "return_regrounding_pack": {
                        "modes": [
                            {
                                "mode_id": "source_export_reentry",
                                "query_mode_hint": "local_search",
                            }
                        ]
                    },
                    "technique_lift_pack": {},
                    "tos_retrieval_axis_pack": {"axes": [{"axis_id": "ontology"}]},
                    "tos_text_chunk_map": {"chunks": [{"chunk_id": "c1"}]},
                    "cross_source_node_projection": {"projections": [{"projection_id": "p1"}]},
                    "counterpart_exposure_review": {},
                    "tos_zarathustra_route_retrieval_pack": {
                        "surface_id": "AOA-K-0011",
                        "routes": [{"retrieval_id": "AOA-K-0011::thus-spoke-zarathustra/prologue-1"}],
                    },
                },
            ),
            tos_source=module.LayerStore(
                layer="tos-source",
                config_path=root / "tos-source.yaml",
                mirror_root=root / "tos-source",
                required_files=self.make_required_files(root / "tos-source", "tos-source"),
                flags={"read_only": True, "source_owned": True, "allow_runtime_mutation": False},
                payloads={
                    "export": {
                        "object_id": "TOS-1",
                        "entry_surface": {"path": "examples/source_node.example.json"},
                        "section_handles": [],
                    },
                    "entry_surface": {"node_id": "node-1"},
                    "tiny_entry_surface": {"route_id": "route-1"},
                },
            ),
            compatibility_bridge=BRIDGE_CONFIG,
        )

    def make_sdk_canary_store(self):
        store = self.make_store()
        sdk_source_ref = "d" * 40
        predecessor_ref = "a" * 40
        subject_digest = store.routing.payloads["mirror_manifest"][
            "artifact_subject_digest"
        ]
        record_id = "routing-sdk-canary-record-1"
        authority = {
            "archive_authorized": False,
            "canonical_producer_switch_authorized": False,
            "compatibility_window_started": False,
            "live_runtime_mutation_authorized": False,
            "predecessor_maintenance_only": False,
            "sdk_canonical": False,
        }
        admission = {
            "schema": "abyss_machine_artifact_producer_admission_v1",
            "status": "candidate_admitted",
            "owner_repo": "aoa-sdk",
            "source_ref": sdk_source_ref,
            "canonical_owner_repo": "aoa-routing",
            "canonical_predecessor_source_ref": predecessor_ref,
            "runtime_consumer": "abyss-stack",
            "stronger_owner": "abyss-machine",
            "provenance_state": "sdk_g5_candidate",
            "publication_posture": "non_publishing_canary",
            "single_canonical_owner": True,
            "canonical_switch_authorized": False,
            "allowed_consumer_intents": ["agent", "runtime_canary"],
            "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "g5_authority": dict(authority),
        }
        manifest = store.routing.payloads["mirror_manifest"]
        manifest.update(
            {
                "routing_producer_posture": "sdk_g5_candidate_canary",
                "canary_activation_mode": "isolated",
                "operator_change_ref": None,
                "source_git_commit": sdk_source_ref,
                "canonical_producer": {
                    "owner_repo": "aoa-routing",
                    "source_ref": predecessor_ref,
                },
                "candidate_producer": {
                    "owner_repo": "aoa-sdk",
                    "source_ref": sdk_source_ref,
                    "canonical_switch_authorized": False,
                },
                "g5_authority": authority,
                "trust_verdict": {
                    "ok": True,
                    "schema": "abyss_machine_artifact_trust_gate_v1",
                    "verdict": "allow",
                    "artifact_class": "thin_routing_readmodel_bundle",
                    "consumer_intent": "runtime_canary",
                    "subject_digest": subject_digest,
                    "record_id": record_id,
                    "require_latest": True,
                    "latest_record_id": record_id,
                    "reasons": [],
                    "blockers": [],
                    "decision": {
                        "model": "fail_closed_consumer_admission",
                        "allow": True,
                        "consumer_intent": "runtime_canary",
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
                            "source_ref_actual": sdk_source_ref,
                        },
                        "trust_root": {
                            "trust_root_mode_actual": "host_managed",
                            "trust_root_mode_matched": True,
                        },
                        "artifact_subject_store": {
                            "required": True,
                            "ok": True,
                            "aggregate_digest": subject_digest,
                        },
                    },
                    "record": {
                        "record_id": record_id,
                        "artifact_class": "thin_routing_readmodel_bundle",
                        "source_repo": "aoa-sdk",
                        "source_ref": sdk_source_ref,
                        "artifact_subjects_digest": subject_digest,
                        "lifecycle_state": "manually-verified",
                        "latest_eligible": True,
                        "terminal_state": False,
                        "verification_ok": True,
                        "consumer_refs": ["abyss-stack:routing-canary"],
                        "required_controls": [
                            "abi_signature",
                            "sbom",
                            "slsa_in_toto",
                        ],
                        "verified_controls": [
                            "abi_signature",
                            "sbom",
                            "slsa_in_toto",
                        ],
                        "artifact_subject_store": {
                            "required": True,
                            "ok": True,
                            "aggregate_digest": subject_digest,
                        },
                        "producer_admission": admission,
                    },
                },
            }
        )
        store.routing.payloads["router"]["artifact_identity"] = {
            "owner_repo": "aoa-sdk",
            "artifact_class": "thin_routing_readmodel_bundle",
            "abi_epoch": "aoa_routing_thin_router_v1",
        }
        return store

    def make_sdk_canonical_store(self):
        store = self.make_sdk_canary_store()
        manifest = store.routing.payloads["mirror_manifest"]
        sdk_source_ref = manifest["source_git_commit"]
        predecessor_ref = manifest["canonical_producer"]["source_ref"]
        subject_digest = manifest["artifact_subject_digest"]
        authority = {
            "archive_authorized": False,
            "canonical_producer_switch_authorized": True,
            "compatibility_window_started": True,
            "live_runtime_mutation_authorized": True,
            "predecessor_maintenance_only": True,
            "sdk_canonical": True,
        }
        receipt = {
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
                "source_ref": sdk_source_ref,
                "version": "0.8.0",
                "abi_epoch": "aoa_routing_thin_router_v1",
            },
            "predecessor": {
                "owner_repo": "aoa-routing",
                "source_ref": predecessor_ref,
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
            "g5_authority": authority,
            "archive_stop_line": (
                "Repository archival remains forbidden without consumer-zero, "
                "compatibility exit, and separate exact operator approval."
            ),
        }
        receipt_digest = self.module.routing_receipt_digest(receipt)
        admission = {
            "schema": "abyss_machine_artifact_producer_admission_v1",
            "status": "canonical_producer",
            "profile_id": "aoa-sdk-g5-canonical",
            "owner_repo": "aoa-sdk",
            "source_ref": sdk_source_ref,
            "canonical_owner_repo": "aoa-sdk",
            "canonical_predecessor_source_ref": predecessor_ref,
            "runtime_consumer": "abyss-stack",
            "stronger_owner": "abyss-machine",
            "provenance_state": "sdk_canonical",
            "publication_posture": "public_release_canonical",
            "single_canonical_owner": True,
            "canonical_switch_authorized": True,
            "allowed_consumer_intents": ["release_consumer", "runtime"],
            "required_controls": ["abi_signature", "sbom", "slsa_in_toto"],
            "g5_authority": authority,
            "owner_switch_receipt": {
                "schema": receipt["schema"],
                "status": receipt["status"],
                "digest": receipt_digest,
            },
        }
        trust = manifest["trust_verdict"]
        trust.update(
            {
                "consumer_intent": "runtime",
                "decision": {
                    "model": "fail_closed_consumer_admission",
                    "allow": True,
                    "consumer_intent": "runtime",
                },
            }
        )
        trust["inspected_claims"]["trust_root"] = {
            "trust_root_mode_actual": "public_release",
            "trust_root_mode_matched": True,
        }
        trust["inspected_claims"]["producer_admission"] = admission
        trust["record"].update(
            {
                "lifecycle_state": "release-ready",
                "trust_root_mode": "public_release",
                "consumer_refs": ["abyss-stack:routing-canonical"],
                "producer_admission": admission,
            }
        )
        manifest.update(
            {
                "routing_producer_posture": "sdk_canonical",
                "cutover_activation_mode": "authorized_live_cutover",
                "canary_activation_mode": None,
                "operator_change_ref": "test-g5-live-cutover",
                "canonical_producer": {
                    "owner_repo": "aoa-sdk",
                    "source_ref": sdk_source_ref,
                },
                "candidate_producer": None,
                "predecessor_rollback": {
                    "owner_repo": "aoa-routing",
                    "source_ref": predecessor_ref,
                    "posture": (
                        "compatibility_security_rollback_deprecation_only"
                    ),
                },
                "g5_authority": authority,
                "owner_switch_receipt": receipt,
                "owner_switch_receipt_digest": receipt_digest,
            }
        )
        return store

    def make_compatibility_rollback_store(self):
        store = self.make_store()
        manifest = store.routing.payloads["mirror_manifest"]
        identity = store.routing.payloads["router"]["artifact_identity"]
        store.routing.payloads["compatibility_rollback"] = {
            "schema": "abyss_stack_routing_g5_compatibility_rollback_v1",
            "state": "compatibility_rollback_active",
            "source_owner_state": "sdk_canonical_unchanged",
            "sdk_source_ref": "d" * 40,
            "predecessor_source_ref": manifest["source_git_commit"],
            "artifact_subject_digest": "sha256:" + ("e" * 64),
            "operator_change_ref": "private-test-rollback-change",
            "rolled_back_at_utc": "2026-07-26T00:00:00+00:00",
            "predecessor_manifest_digest": (
                self.module.routing_receipt_digest(manifest)
            ),
            "predecessor_file_hashes_digest": (
                self.module.routing_receipt_digest(
                    manifest["file_sha256"]
                )
            ),
            "predecessor_artifact_identity": {
                "owner_repo": identity["owner_repo"],
                "artifact_class": identity["artifact_class"],
                "abi_epoch": identity["abi_epoch"],
            },
            "archive_authorized": False,
        }
        return store

    def test_health_reports_closure_summary_when_all_layers_are_ready(self) -> None:
        self.module.STORE = self.make_store()

        payload = self.module.health()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["layer_readiness"]["aoa-routing"])
        self.assertTrue(payload["routing_provenance"]["trust_verdict_available"])
        self.assertEqual(
            payload["routing_provenance"]["source_git_commit"],
            "a" * 40,
        )
        self.assertTrue(payload["closure_summary"]["closure_ready"])
        self.assertEqual(payload["closure_summary"]["ready_layer_count"], 7)
        self.assertEqual(payload["operator_verdict_command"], "aoa-status --autonomy --json")

    def test_sdk_canary_is_ready_without_becoming_runtime_closure(self) -> None:
        store = self.make_sdk_canary_store()
        store.routing.payloads["mirror_manifest"]["candidate_producer"][
            "private_evidence_ref"
        ] = "/deploy-local/private-candidate.json"
        store.routing.payloads["mirror_manifest"]["canonical_producer"][
            "private_evidence_ref"
        ] = "/deploy-local/private-predecessor.json"
        self.module.STORE = store

        health = self.module.health()
        surface = self.module.surface_status()
        routing_closure = surface["layers_status"]["aoa-routing"]["closure_status"]

        self.assertFalse(health["ok"])
        self.assertFalse(health["layer_readiness"]["aoa-routing"])
        self.assertTrue(health["routing_canary"]["canary_ready"])
        self.assertFalse(health["routing_canary"]["closure_ready"])
        self.assertFalse(
            health["routing_canary"]["canonical_switch_authorized"]
        )
        self.assertTrue(routing_closure["mirror_ready"])
        self.assertTrue(routing_closure["consumer_ready"])
        self.assertTrue(routing_closure["canary_ready"])
        self.assertFalse(routing_closure["provenance_ready"])
        self.assertFalse(routing_closure["closure_ready"])
        self.assertEqual(routing_closure["canary_reasons"], [])
        self.assertIn(
            "routing SDK canary is non-canonical and cannot satisfy runtime closure",
            routing_closure["provenance_reasons"],
        )
        self.assertNotIn("/deploy-local/private-candidate.json", json.dumps(health))
        self.assertNotIn("/deploy-local/private-predecessor.json", json.dumps(health))

    def test_sdk_canary_fails_closed_when_authority_is_asserted(self) -> None:
        store = self.make_sdk_canary_store()
        store.routing.payloads["mirror_manifest"]["g5_authority"][
            "sdk_canonical"
        ] = True
        self.module.STORE = store

        payload = self.module.surface_status()
        closure = payload["layers_status"]["aoa-routing"]["closure_status"]

        self.assertFalse(closure["canary_ready"])
        self.assertIn(
            "routing SDK canary asserts forbidden G5 authority: sdk_canonical",
            closure["canary_reasons"],
        )

    def test_sdk_canonical_receipt_can_satisfy_runtime_closure(self) -> None:
        store = self.make_sdk_canonical_store()
        self.module.STORE = store

        health = self.module.health()
        surface = self.module.surface_status()
        closure = surface["layers_status"]["aoa-routing"]["closure_status"]

        self.assertTrue(health["ok"])
        self.assertTrue(health["routing_switch"]["canonical_posture"])
        self.assertTrue(health["routing_switch"]["canonical_ready"])
        self.assertTrue(health["routing_switch"]["live_cutover_active"])
        self.assertTrue(
            health["routing_switch"]["canonical_switch_authorized"]
        )
        self.assertFalse(
            health["routing_switch"]["owner_switch_receipt"][
                "compatibility_window"
            ]
            is None
        )
        self.assertTrue(closure["closure_ready"])
        self.assertTrue(closure["canonical_ready"])
        self.assertEqual(closure["canonical_reasons"], [])

    def test_sdk_isolated_canonical_rehearsal_cannot_close_live_runtime(
        self,
    ) -> None:
        store = self.make_sdk_canonical_store()
        manifest = store.routing.payloads["mirror_manifest"]
        manifest["cutover_activation_mode"] = "isolated"
        manifest["operator_change_ref"] = None
        self.module.STORE = store

        health = self.module.health()
        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertTrue(closure["canonical_ready"])
        self.assertFalse(closure["closure_ready"])
        self.assertFalse(health["routing_switch"]["live_cutover_active"])
        self.assertIn(
            "routing SDK isolated canonical rehearsal cannot satisfy "
            "live runtime closure",
            closure["provenance_reasons"],
        )

    def test_sdk_canonical_receipt_fails_closed_on_archive_authority(
        self,
    ) -> None:
        store = self.make_sdk_canonical_store()
        store.routing.payloads["mirror_manifest"]["g5_authority"][
            "archive_authorized"
        ] = True
        self.module.STORE = store

        health = self.module.health()
        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertFalse(closure["canonical_ready"])
        self.assertFalse(
            health["routing_switch"]["canonical_switch_authorized"]
        )
        self.assertIn(
            "routing SDK canonical G5 authority posture is invalid",
            closure["canonical_reasons"],
        )

    def test_compatibility_rollback_marker_persists_degraded_owner_state(
        self,
    ) -> None:
        store = self.make_compatibility_rollback_store()
        self.module.STORE = store

        health = self.module.health()
        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertFalse(health["ok"])
        self.assertTrue(closure["compatibility_rollback_posture"])
        self.assertTrue(closure["compatibility_rollback_valid"])
        self.assertFalse(closure["closure_ready"])
        self.assertTrue(
            health["routing_switch"]["compatibility_rollback_active"]
        )
        self.assertEqual(
            health["routing_switch"]["runtime_owner_state"],
            "compatibility_rollback_active",
        )
        self.assertEqual(
            health["routing_switch"]["source_owner_state"],
            "sdk_canonical_unchanged",
        )
        self.assertIn(
            "routing compatibility rollback is degraded runtime posture "
            "and cannot satisfy ordinary closure",
            closure["provenance_reasons"],
        )
        self.assertNotIn("private-test-rollback-change", json.dumps(health))

    def test_invalid_compatibility_rollback_marker_stays_non_closing(
        self,
    ) -> None:
        store = self.make_compatibility_rollback_store()
        store.routing.payloads["compatibility_rollback"][
            "archive_authorized"
        ] = True
        self.module.STORE = store

        health = self.module.health()
        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertFalse(closure["compatibility_rollback_valid"])
        self.assertFalse(closure["closure_ready"])
        self.assertFalse(
            health["routing_switch"]["compatibility_rollback_active"]
        )
        self.assertIn(
            "routing compatibility rollback must deny archive authority",
            closure["compatibility_rollback_reasons"],
        )

    def test_sdk_live_canary_requires_named_operator_change(self) -> None:
        store = self.make_sdk_canary_store()
        store.routing.payloads["mirror_manifest"][
            "canary_activation_mode"
        ] = "authorized_live_canary"
        self.module.STORE = store

        payload = self.module.surface_status()
        closure = payload["layers_status"]["aoa-routing"]["closure_status"]

        self.assertFalse(closure["canary_ready"])
        self.assertIn(
            "routing SDK live canary operator change ref is missing",
            closure["canary_reasons"],
        )

    def test_health_sanitizes_routing_trust_record(self) -> None:
        store = self.make_store()
        store.routing.payloads["mirror_manifest"]["trust_verdict"]["record"][
            "private_evidence_ref"
        ] = "/deploy-local/registry/private.json"
        self.module.STORE = store

        payload = self.module.health()
        trust_summary = payload["routing_provenance"]["trust_verdict"]

        self.assertEqual(trust_summary["source_repo"], "aoa-routing")
        self.assertEqual(trust_summary["record_id"], "routing-record-1")
        self.assertNotIn("record", trust_summary)
        self.assertNotIn("/deploy-local/registry/private.json", json.dumps(payload))

    def test_routing_version_prefers_current_surface_field(self) -> None:
        payload = {
            "version": "legacy-v1",
            "schema_version": "schema-v2",
            "router_version": 3,
        }

        self.assertEqual(
            self.module.routing_surface_version(
                payload,
                legacy_key="router_version",
            ),
            3,
        )

    def test_surface_status_reports_degraded_layer_when_consumer_gap_exists(self) -> None:
        store = self.make_store()
        store.playbooks.payloads["registry"]["playbooks"] = []
        self.module.STORE = store

        payload = self.module.surface_status()

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["closure_summary"]["closure_ready"])
        self.assertIn("aoa-playbooks", payload["closure_summary"]["degraded_layers"])
        closure = payload["layers_status"]["aoa-playbooks"]["closure_status"]
        self.assertFalse(closure["consumer_ready"])
        self.assertIn("playbook registry missing entries", closure["reasons"])

    def test_routing_layer_reports_content_ready_but_not_closed_without_trust(self) -> None:
        store = self.make_store()
        del store.routing.payloads["mirror_manifest"]["trust_verdict"]
        self.module.STORE = store

        payload = self.module.surface_status()
        closure = payload["layers_status"]["aoa-routing"]["closure_status"]

        self.assertFalse(payload["ok"])
        self.assertTrue(closure["mirror_ready"])
        self.assertTrue(closure["consumer_ready"])
        self.assertFalse(closure["provenance_ready"])
        self.assertFalse(closure["closure_ready"])
        self.assertEqual(
            closure["provenance_reasons"],
            ["routing mirror trust verdict is unavailable"],
        )
        self.assertFalse(payload["routing_provenance"]["trust_verdict_available"])

    def test_routing_layer_rejects_tampered_manifest_content_hash(self) -> None:
        store = self.make_store()
        rel_path = store.routing.required_files[0]
        store.routing.payloads["mirror_manifest"]["file_sha256"][rel_path] = "0" * 64

        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertTrue(closure["consumer_ready"])
        self.assertFalse(closure["provenance_ready"])
        self.assertIn(
            f"routing mirror provenance content hashes do not match: {rel_path}",
            closure["provenance_reasons"],
        )

    def test_routing_layer_rejects_unbound_trust_verdict(self) -> None:
        store = self.make_store()
        store.routing.payloads["mirror_manifest"]["trust_verdict"][
            "subject_digest"
        ] = "sha256:" + ("c" * 64)

        closure = self.module.layer_status(store.routing)["closure_status"]

        self.assertTrue(closure["consumer_ready"])
        self.assertFalse(closure["provenance_ready"])
        self.assertIn(
            "routing mirror trust verdict subject digest drifted",
            closure["provenance_reasons"],
        )

    def test_evals_layer_status_includes_bridge_managed_runtime_evidence_files(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        mirror_root = root / "aoa-evals"
        required_files = [
            "generated/eval_catalog.min.json",
            "generated/eval_capsules.json",
            "generated/eval_sections.full.json",
            "generated/comparison_spine.json",
            "generated/runtime_candidate_template_index.min.json",
            "examples/runtime_evidence_selection.workhorse-local.example.json",
            "examples/runtime_evidence_selection.return-anchor-integrity.example.json",
            "examples/artifact_to_verdict_hook.self-agent-checkpoint-rollout.example.json",
            "examples/artifact_to_verdict_hook.long-horizon-model-tier-orchestra.example.json",
            "examples/artifact_to_verdict_hook.restartable-inquiry-loop.example.json",
        ]
        for rel_path in required_files:
            payload: object = {"templates": []} if rel_path.endswith("runtime_candidate_template_index.min.json") else {}
            self.write_json(mirror_root, rel_path, payload)
        bridge_refs = [
            entry["upstream_source_ref"]
            for entry in BRIDGE_CONFIG["runtime_evidence_templates"].values()
        ]
        for rel_path in bridge_refs:
            self.write_json(mirror_root, rel_path, {})

        layer = self.module.load_evals_layer(
            root / "aoa-evals.yaml",
            {
                "required_files": required_files,
                "read_only": True,
                "export_only_evidence": True,
                "allow_free_text_eval_selection": False,
            },
            mirror_root,
            BRIDGE_CONFIG,
        )
        status = self.module.layer_status(layer)

        for rel_path in bridge_refs:
            self.assertIn(rel_path, layer.required_files)
            self.assertTrue(status["required_files"][rel_path]["present"])

    def test_playbooks_layer_status_includes_bridge_managed_automation_file(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        mirror_root = root / "aoa-playbooks"
        required_files = [
            "generated/playbook_registry.min.json",
            "generated/playbook_activation_surfaces.min.json",
            "generated/playbook_federation_surfaces.min.json",
            "generated/playbook_review_status.min.json",
            "generated/playbook_review_packet_contracts.min.json",
            "generated/playbook_review_intake.min.json",
            "generated/playbook_handoff_contracts.json",
            "generated/playbook_failure_catalog.json",
            "generated/playbook_subagent_recipes.json",
            "generated/playbook_composition_manifest.json",
            "schemas/playbook-registry.schema.json",
        ]
        payloads: dict[str, object] = {
            "generated/playbook_registry.min.json": {"playbooks": []},
            "generated/playbook_activation_surfaces.min.json": [],
            "generated/playbook_federation_surfaces.min.json": [],
            "generated/playbook_review_status.min.json": {"playbooks": []},
            "generated/playbook_review_packet_contracts.min.json": {"playbooks": []},
            "generated/playbook_review_intake.min.json": {"playbooks": []},
            "generated/playbook_handoff_contracts.json": {"playbooks": []},
            "generated/playbook_failure_catalog.json": {"failures": []},
            "generated/playbook_subagent_recipes.json": {"recipes": []},
            "generated/playbook_composition_manifest.json": {"manifest_version": "1"},
            "schemas/playbook-registry.schema.json": {},
        }
        for rel_path, payload in payloads.items():
            self.write_json(mirror_root, rel_path, payload)
        automation_ref = BRIDGE_CONFIG["playbook_automation_plans"]["upstream_rel_path"]
        self.write_json(mirror_root, automation_ref, {"seeds": []})

        layer = self.module.load_playbooks_layer(
            root / "aoa-playbooks.yaml",
            {
                "required_files": required_files,
                "read_only": True,
                "advisory_only": True,
                "allow_runtime_execution": False,
                "include_composition_surfaces": True,
            },
            mirror_root,
            BRIDGE_CONFIG,
        )
        status = self.module.layer_status(layer)

        self.assertIn(automation_ref, layer.required_files)
        self.assertTrue(status["required_files"][automation_ref]["present"])

    def test_memo_recall_runtime_evidence_template_resolves_source_files(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            "memo-recall-rerun",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["canonical_selection_id"], "memo-recall-rerun-v1")
        self.assertEqual(
            payload["template"]["selection_id"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-recall-rerun"]["upstream_selection_id"],
        )
        self.assertEqual(payload["upstream_contract"]["local_route"], "memo-recall-rerun")
        self.assertEqual(payload["upstream_contract"]["owner_repo"], "aoa-evals")
        self.assertIn(
            f"aoa-evals/{BRIDGE_CONFIG['runtime_evidence_templates']['memo-recall-rerun']['upstream_source_ref']}",
            payload["source_files"],
        )

    def test_runtime_evidence_template_keeps_compatibility_bridge_but_reports_clean_name(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-recall-rerun"]["bridge_names"][0],
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["name"], "memo-recall-rerun")
        self.assertEqual(
            payload["requested_name"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-recall-rerun"]["bridge_names"][0],
        )
        self.assertEqual(payload["compatibility_bridge_for"], "memo-recall-rerun")

    def test_memo_contradiction_gap_runtime_evidence_template_resolves_source_files(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            "memo-contradiction-gap",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["canonical_selection_id"], "memo-contradiction-gap-v1")
        self.assertEqual(
            payload["template"]["selection_id"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-contradiction-gap"]["upstream_selection_id"],
        )
        self.assertIn(
            f"aoa-evals/{BRIDGE_CONFIG['runtime_evidence_templates']['memo-contradiction-gap']['upstream_source_ref']}",
            payload["source_files"],
        )

    def test_memo_contradiction_rerun_runtime_evidence_template_resolves_source_files(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            "memo-contradiction-rerun",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["canonical_selection_id"], "memo-contradiction-rerun-v1")
        self.assertEqual(
            payload["template"]["selection_id"],
            BRIDGE_CONFIG["runtime_evidence_templates"]["memo-contradiction-rerun"]["upstream_selection_id"],
        )
        self.assertIn(
            f"aoa-evals/{BRIDGE_CONFIG['runtime_evidence_templates']['memo-contradiction-rerun']['upstream_source_ref']}",
            payload["source_files"],
        )

    def test_playbook_card_exposes_clean_automation_plan_names(self) -> None:
        store = self.make_store()

        card = self.module.playbook_card(store, "AOA-P-0001")
        compact = self.module.compact_playbook_card(store, "AOA-P-0001")

        self.assertEqual(card["automation_plans"][0]["name"], "fixture-plan")
        self.assertNotIn("automation_seeds", card)
        self.assertEqual(compact["automation_plan_names"], ["fixture-plan"])

    def test_playbook_automation_plans_endpoint_exposes_clean_payload(self) -> None:
        self.module.STORE = self.make_store()

        payload = self.module.playbooks_automation_plans()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["plans"][0]["name"], "fixture-plan")
        self.assertNotIn("seeds", payload["data"])

    def test_playbook_automation_seed_endpoint_is_compatibility_bridge(self) -> None:
        self.module.STORE = self.make_store()

        payload = self.module.playbooks_automation_seed_compatibility(
            self.module.PlaybookAutomationPlanRequest(name="fixture-plan")
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["compatibility_bridge_for"], "/playbooks/automation-plan")
        self.assertEqual(payload["plan"]["name"], "fixture-plan")
        self.assertEqual(payload["seed"], payload["plan"])
        self.assertEqual(payload["seed"]["name"], "fixture-plan")

    def test_kag_structured_reads_stay_mirror_backed(self) -> None:
        store = self.make_store()

        inspect_payload = self.module.resolve_kag_inspect(store, "AOA-K-0011")
        query_payload = self.module.resolve_kag_query_mode(store, "local_search")
        regrounding_payload = self.module.resolve_kag_regrounding(store, "source_export_reentry")
        repo_payload = self.module.resolve_kag_repo_entry(store, "Tree-of-Sophia")

        self.assertEqual(inspect_payload["surface_id"], "AOA-K-0011")
        self.assertEqual(inspect_payload["pack"]["surface_id"], "AOA-K-0011")
        self.assertIn(
            "aoa-kag/generated/tos_zarathustra_route_retrieval_pack.min.json",
            inspect_payload["source_files"],
        )
        self.assertNotIn("tos_support", inspect_payload)

        self.assertEqual(query_payload["mode"], "local_search")
        self.assertTrue(query_payload["reasoning_scenarios"])
        self.assertTrue(query_payload["regrounding_modes"])
        self.assertEqual(
            query_payload["source_files"],
            [
                "aoa-kag/generated/reasoning_handoff_pack.min.json",
                "aoa-kag/generated/return_regrounding_pack.min.json",
            ],
        )

        self.assertEqual(regrounding_payload["mode_id"], "source_export_reentry")
        self.assertEqual(
            regrounding_payload["source_files"],
            ["aoa-kag/generated/return_regrounding_pack.min.json"],
        )

        self.assertEqual(repo_payload["repo"], "Tree-of-Sophia")
        self.assertIn("aoa-kag/generated/federation_spine.min.json", repo_payload["source_files"])
        self.assertIn("tos-source/generated/kag_export.min.json", repo_payload["source_files"])

    def test_playbook_card_includes_review_status_when_available(self) -> None:
        store = self.make_store()

        payload = self.module.playbook_card(store, "AOA-P-0001")

        self.assertEqual(payload["review_status"]["gate_verdict"], "composition-landed")
        self.assertEqual(payload["review_status"]["reviewed_run_count"], 1)
        self.assertEqual(payload["review_packet_contract"]["candidate_packet_kinds"], ["memo_candidate", "artifact_hook_candidate"])
        self.assertIn(
            "aoa-playbooks/generated/playbook_review_status.min.json",
            payload["source_files"],
        )
        self.assertIn(
            "aoa-playbooks/generated/playbook_review_packet_contracts.min.json",
            payload["source_files"],
        )
