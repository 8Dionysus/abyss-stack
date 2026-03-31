import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "config-templates" / "Services" / "route-api" / "app" / "main.py"


def load_module():
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
    spec.loader.exec_module(module)
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
                    "runtime_evidence_templates": {"workhorse-local": {}},
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
                    "registry": {"playbooks": [{"playbook_id": "AOA-P-0001"}]},
                    "activation": [{"playbook_id": "AOA-P-0001"}],
                    "federation": [{"playbook_id": "AOA-P-0001"}],
                    "handoffs": {"playbooks": [{"playbook_id": "AOA-P-0001"}]},
                    "failures": {"failures": [{"failure_id": "F-1"}]},
                    "subagent_recipes": {"recipes": [{"recipe_id": "R-1"}]},
                    "automation_seeds": {"seeds": [{"seed_id": "S-1"}]},
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
                    "registry": {"surfaces": [{"surface_id": "AOA-K-0005"}]},
                    "federation_spine": {"repos": [{"repo": "Tree-of-Sophia"}]},
                    "tiny_consumer_bundle": {},
                    "reasoning_handoff_pack": {"scenarios": [{"scenario_id": "S-1"}]},
                    "return_regrounding_pack": {"modes": [{"mode_id": "local_search"}]},
                    "technique_lift_pack": {},
                    "tos_retrieval_axis_pack": {"axes": [{"axis_id": "ontology"}]},
                    "tos_text_chunk_map": {"chunks": [{"chunk_id": "c1"}]},
                    "cross_source_node_projection": {"projections": [{"projection_id": "p1"}]},
                    "counterpart_exposure_review": {},
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
