import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py"


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

    def make_store(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        module = self.module

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
                mirror_root=root / "aoa-routing",
                required_files=self.make_required_files(root / "aoa-routing", "aoa-routing"),
                flags={"advisory_only": True, "allow_free_text_task_routing": False},
                payloads={
                    "router": {"router_version": "1"},
                    "cross_repo_registry": {"version": "1"},
                    "surface_hints": {"version": "1"},
                    "tier_hints": {"version": "1"},
                    "recommended_paths": {"version": "1"},
                    "pairing_hints": {"version": "1"},
                    "kag_source_lift_relation_hints": {"version": "1"},
                    "federation_entrypoints": {"version": "1"},
                    "return_hints": {"version": "1"},
                    "tiny_model_entrypoints": {"version": "1"},
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
                        "phase-alpha-memo-recall-rerun": {
                            "selection_id": "phase-alpha-memo-recall-rerun-v1"
                        },
                        "phase-alpha-memo-contradiction-gap": {
                            "selection_id": "phase-alpha-memo-contradiction-gap-v1"
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
                    "subagent_recipes": {"recipes": [{"recipe_id": "R-1", "playbook": "fixture-playbook"}]},
                    "automation_seeds": {"seeds": [{"seed_id": "S-1", "playbook": "fixture-playbook"}]},
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
        )

    def test_health_reports_closure_summary_when_all_layers_are_ready(self) -> None:
        self.module.STORE = self.make_store()

        payload = self.module.health()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["closure_summary"]["closure_ready"])
        self.assertEqual(payload["closure_summary"]["ready_layer_count"], 7)
        self.assertEqual(payload["operator_verdict_command"], "aoa-status --autonomy --json")

    def test_surface_status_reports_degraded_layer_when_consumer_gap_exists(self) -> None:
        store = self.make_store()
        store.playbooks.payloads["registry"]["playbooks"] = []
        self.module.STORE = store

        payload = self.module.surface_status()

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["closure_summary"]["closure_ready"])
        self.assertIn("aoa-playbooks", payload["closure_summary"]["degraded_layers"])
        closure = payload["layers_status"]["aoa-playbooks"]["closure_status"]
        self.assertFalse(closure["consumer_ready"])
        self.assertIn("playbook registry missing entries", closure["reasons"])

    def test_phase_alpha_memo_recall_runtime_evidence_template_resolves_source_files(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            "phase-alpha-memo-recall-rerun",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["template"]["selection_id"], "phase-alpha-memo-recall-rerun-v1")
        self.assertIn(
            "aoa-evals/examples/runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json",
            payload["source_files"],
        )

    def test_phase_alpha_memo_contradiction_gap_runtime_evidence_template_resolves_source_files(self) -> None:
        store = self.make_store()

        payload = self.module.resolve_runtime_evidence_template(
            store,
            "phase-alpha-memo-contradiction-gap",
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["template"]["selection_id"], "phase-alpha-memo-contradiction-gap-v1")
        self.assertIn(
            "aoa-evals/examples/runtime_evidence_selection.phase-alpha-memo-contradiction-gap.example.json",
            payload["source_files"],
        )

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
