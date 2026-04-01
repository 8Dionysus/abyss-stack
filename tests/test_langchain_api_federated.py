import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    REPO_ROOT / "config-templates" / "Services" / "langchain-api" / "app" / "main.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("langchain_api_main_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LangchainFederatedRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.client = TestClient(cls.module.app)

    def setUp(self) -> None:
        self.module.FEDERATED_RUN_ENABLED = True

    def test_run_endpoint_stays_compatible(self) -> None:
        with patch.object(
            self.module,
            "_invoke_run_backend",
            return_value={"ok": True, "backend": "stub", "model": "m", "answer": "plain"},
        ) as backend:
            response = self.client.post("/run", json={"user_text": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "backend": "stub", "model": "m", "answer": "plain"},
        )
        backend.assert_called_once()

    def test_federated_run_returns_503_when_disabled(self) -> None:
        self.module.FEDERATED_RUN_ENABLED = False

        response = self.client.post("/run/federated", json={"user_text": "hello", "playbook_id": "AOA-P-0008"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("disabled", response.json()["detail"])

    def test_federated_run_returns_503_when_route_api_unreachable(self) -> None:
        with patch.object(
            self.module,
            "_route_api_post",
            side_effect=self.module.RouteAPIUnavailableError("route-api offline"),
        ):
            response = self.client.post(
                "/run/federated",
                json={"user_text": "hello", "playbook_id": "AOA-P-0008"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("route-api offline", response.json()["detail"])

    def test_federated_run_returns_409_for_ambiguous_playbook_select(self) -> None:
        def route_side_effect(path, payload):
            self.assertEqual(path, "/playbooks/select")
            return {
                "ok": True,
                "playbooks": [
                    {"playbook_id": "AOA-P-0008"},
                    {"playbook_id": "AOA-P-0010"},
                ],
            }

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            response = self.client.post(
                "/run/federated",
                json={"user_text": "hello", "playbook_select": {"scenario": "bounded_change_safe"}},
            )

        self.assertEqual(response.status_code, 409)

    def test_federated_run_happy_path_uses_capsule_without_expand_by_default(self) -> None:
        calls: list[tuple[str, dict]] = []
        prompts: list[str] = []
        playbook = {
            "playbook_id": "AOA-P-0008",
            "name": "Cross Repo Boundary Rollout",
            "registry_entry": {"scenario": "bounded_change_safe"},
            "activation_entry": {"trigger": "user_request"},
            "federation_entry": {"required_skills": ["memo-recall"]},
            "source_files": ["aoa-playbooks/generated/playbook_registry.min.json"],
        }

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {
                        "mode": "semantic",
                        "inspect_surface": "generated/memory_catalog.min.json",
                        "capsule_surface": "generated/memory_capsules.json",
                        "expand_surface": "generated/memory_sections.full.json",
                        "source_route_required": True,
                    },
                    "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                }
            if path == "/memo/inspect":
                return {"ok": True, "entry": {"id": "claim-1", "kind": "claim", "summary": "Inspect card"}}
            if path == "/memo/capsule":
                return {"ok": True, "entry": {"id": "claim-1", "summary": "Capsule card"}}
            raise AssertionError(f"unexpected route-api call: {path}")

        def backend_side_effect(req):
            prompts.append(req.user_text)
            return {"ok": True, "backend": "stub", "model": "m", "answer": "done"}

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(self.module, "_invoke_run_backend", side_effect=backend_side_effect):
                with patch.object(
                    self.module,
                    "_load_return_policy_snapshot",
                    return_value={"policy_id": "agentic-default-return", "effective_profile_class": "workhorse"},
                ):
                    response = self.client.post(
                        "/run/federated",
                        json={
                            "user_text": "Summarize the current route",
                            "playbook_id": "AOA-P-0008",
                            "memo": {"family": "router", "mode": "semantic", "id": "claim-1"},
                        },
                    )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answer"], "done")
        self.assertEqual(
            [path for path, _ in calls],
            ["/playbooks/inspect", "/memo/recall-contract", "/memo/inspect", "/memo/capsule"],
        )
        self.assertEqual(body["advisory_trace"]["memo"]["resolution"], "capsule")
        self.assertEqual(body["advisory_trace"]["memo"]["sequence"], ["recall_contract", "inspect", "capsule"])
        self.assertNotIn("writeback_map", body["advisory_trace"]["memo"])
        self.assertTrue(prompts)
        self.assertIn("## core", prompts[0])
        self.assertIn("## short", prompts[0])
        self.assertIn("## memory_access", prompts[0])
        self.assertNotIn("## long", prompts[0])

    def test_federated_run_does_not_hydrate_memo_without_explicit_id(self) -> None:
        calls: list[str] = []

        def route_side_effect(path, payload):
            calls.append(path)
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {
                        "mode": "semantic",
                        "inspect_surface": "generated/memory_catalog.min.json",
                        "capsule_surface": "generated/memory_capsules.json",
                        "expand_surface": "generated/memory_sections.full.json",
                    },
                    "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(
                self.module,
                "_invoke_run_backend",
                return_value={"ok": True, "backend": "stub", "model": "m", "answer": "done"},
            ):
                response = self.client.post(
                    "/run/federated",
                    json={"user_text": "hello", "memo": {"family": "router", "mode": "semantic"}},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, ["/memo/recall-contract"])
        self.assertEqual(response.json()["advisory_trace"]["memo"]["resolution"], "contract_only")

    def test_playbook_surface_can_seed_default_memo_contract_without_override(self) -> None:
        calls: list[tuple[str, dict]] = []
        playbook = {
            "playbook_id": "AOA-P-0010",
            "name": "Split Wave Cross Repo Rollout",
            "registry_entry": {},
            "activation_entry": {
                "memo_recall_modes": ["episodic", "semantic"],
                "memo_read_path": "inspect_capsule_then_expand",
            },
            "federation_entry": {},
            "source_files": ["aoa-playbooks/generated/playbook_activation_surfaces.min.json"],
        }

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {"mode": "semantic", "inspect_surface": "generated/memory_catalog.min.json"},
                    "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(
                self.module,
                "_invoke_run_backend",
                return_value={"ok": True, "backend": "stub", "model": "m", "answer": "done"},
            ):
                response = self.client.post(
                    "/run/federated",
                    json={"user_text": "hello", "playbook_id": "AOA-P-0010"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls,
            [
                ("/playbooks/inspect", {"playbook_id": "AOA-P-0010"}),
                ("/memo/recall-contract", {"family": "router", "mode": "semantic", "return_ready": False}),
            ],
        )
        self.assertEqual(response.json()["advisory_trace"]["memo"]["selector"]["source"], "playbook")

    def test_playbook_surface_can_seed_working_memo_contract_without_override(self) -> None:
        calls: list[tuple[str, dict]] = []
        playbook = {
            "playbook_id": "AOA-P-0019",
            "name": "Release Migration Cutover",
            "registry_entry": {},
            "activation_entry": {
                "memo_recall_modes": ["working", "episodic"],
                "memo_read_path": "inspect_then_expand",
                "memo_checkpoint_posture": "preferred",
            },
            "federation_entry": {},
            "source_files": ["aoa-playbooks/generated/playbook_activation_surfaces.min.json"],
        }

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {
                        "mode": "working",
                        "inspect_surface": "generated/memory_object_catalog.min.json",
                        "expand_surface": "generated/memory_object_sections.full.json",
                    },
                    "source_files": ["aoa-memo/examples/recall_contract.object.working.return.json"],
                }
            if path == "/memo/writeback-map":
                return {
                    "ok": True,
                    "runtime_surface": "checkpoint_export",
                    "contract_id": "aoa-memo.runtime-writeback.v1",
                    "mapping": {
                        "target_kind": "state_capsule",
                        "writeback_class": "checkpoint_export",
                        "temperature_hint": "hot",
                        "review_state_default": "captured",
                        "requires_human_review": False,
                    },
                    "source_files": ["aoa-memo/examples/checkpoint_to_memory_contract.example.json"],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(
                self.module,
                "_invoke_run_backend",
                return_value={"ok": True, "backend": "stub", "model": "m", "answer": "done"},
            ):
                response = self.client.post(
                    "/run/federated",
                    json={"user_text": "hello", "playbook_id": "AOA-P-0019"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls,
            [
                ("/playbooks/inspect", {"playbook_id": "AOA-P-0019"}),
                ("/memo/recall-contract", {"family": "object", "mode": "working", "return_ready": True}),
                ("/memo/writeback-map", {"runtime_surface": "checkpoint_export"}),
            ],
        )
        self.assertEqual(response.json()["advisory_trace"]["memo"]["selector"]["source"], "playbook")
        self.assertEqual(
            response.json()["advisory_trace"]["memo"]["writeback_map"]["runtime_surface"],
            "checkpoint_export",
        )

    def test_explicit_memo_override_beats_playbook_default(self) -> None:
        calls: list[tuple[str, dict]] = []
        playbook = {
            "playbook_id": "AOA-P-0019",
            "name": "Validation Driven Remediation",
            "registry_entry": {},
            "activation_entry": {
                "memo_recall_modes": ["episodic", "semantic"],
                "memo_read_path": "inspect_capsule_then_expand",
            },
            "federation_entry": {},
            "source_files": ["aoa-playbooks/generated/playbook_activation_surfaces.min.json"],
        }

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {
                        "mode": "working",
                        "inspect_surface": "generated/memory_object_catalog.min.json",
                        "expand_surface": "generated/memory_object_sections.full.json",
                    },
                    "source_files": ["aoa-memo/examples/recall_contract.object.working.return.json"],
                }
            if path == "/memo/inspect":
                return {"ok": True, "entry": {"id": "checkpoint-1", "kind": "state_capsule", "summary": "Inspect"}}
            if path == "/memo/expand":
                return {"ok": True, "entry": {"id": "checkpoint-1", "summary": "Expanded"}}
            if path == "/memo/writeback-map":
                return {
                    "ok": True,
                    "runtime_surface": "checkpoint_export",
                    "contract_id": "aoa-memo.runtime-writeback.v1",
                    "mapping": {
                        "target_kind": "state_capsule",
                        "writeback_class": "checkpoint_export",
                        "temperature_hint": "hot",
                        "review_state_default": "captured",
                        "requires_human_review": False,
                    },
                    "source_files": ["aoa-memo/examples/checkpoint_to_memory_contract.example.json"],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(
                self.module,
                "_invoke_run_backend",
                return_value={"ok": True, "backend": "stub", "model": "m", "answer": "done"},
            ):
                response = self.client.post(
                    "/run/federated",
                    json={
                        "user_text": "hello",
                        "playbook_id": "AOA-P-0019",
                        "memo": {
                            "family": "object",
                            "mode": "working",
                            "id": "checkpoint-1",
                            "return_ready": True,
                        },
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [path for path, _ in calls],
            [
                "/playbooks/inspect",
                "/memo/recall-contract",
                "/memo/inspect",
                "/memo/expand",
                "/memo/writeback-map",
            ],
        )
        self.assertEqual(
            calls[1][1],
            {"family": "object", "mode": "working", "return_ready": True},
        )
        self.assertEqual(response.json()["advisory_trace"]["memo"]["selector"]["source"], "request")
        self.assertEqual(
            response.json()["advisory_trace"]["memo"]["writeback_map"]["target_kind"],
            "state_capsule",
        )

    def test_federated_run_accepts_kag_inspect_selector_and_emits_knowledge_access(self) -> None:
        calls: list[tuple[str, dict]] = []
        prompts: list[str] = []
        playbook = {
            "playbook_id": "AOA-P-0010",
            "name": "Split Wave Cross Repo Rollout",
            "registry_entry": {},
            "activation_entry": {
                "memo_recall_modes": ["episodic", "semantic"],
                "memo_read_path": "inspect_capsule_then_expand",
            },
            "federation_entry": {},
            "review_status": {"playbook_id": "AOA-P-0010", "gate_verdict": "hold", "reviewed_run_count": 0},
            "source_files": ["aoa-playbooks/generated/playbook_activation_surfaces.min.json"],
        }

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            if path == "/memo/recall-contract":
                return {
                    "ok": True,
                    "contract": {"mode": "semantic", "inspect_surface": "generated/memory_catalog.min.json"},
                    "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                }
            if path == "/kag/inspect":
                return {
                    "ok": True,
                    "surface_id": "AOA-K-0011",
                    "registry_entry": {"id": "AOA-K-0011", "name": "tos-zarathustra-route-retrieval-surface"},
                    "pack": {"surface_id": "AOA-K-0011", "route_count": 1},
                    "source_files": ["aoa-kag/generated/tos_zarathustra_route_retrieval_pack.min.json"],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        def backend_side_effect(req):
            prompts.append(req.user_text)
            return {"ok": True, "backend": "stub", "model": "m", "answer": "done"}

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(self.module, "_invoke_run_backend", side_effect=backend_side_effect):
                with patch.object(
                    self.module,
                    "_load_return_policy_snapshot",
                    return_value={"policy_id": "agentic-default-return", "effective_profile_class": "workhorse"},
                ):
                    response = self.client.post(
                        "/run/federated",
                        json={
                            "user_text": "hello",
                            "playbook_id": "AOA-P-0010",
                            "memo": {"family": "router", "mode": "semantic"},
                            "kag": {"inspect_id": "AOA-K-0011"},
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [path for path, _ in calls],
            ["/playbooks/inspect", "/memo/recall-contract", "/kag/inspect"],
        )
        self.assertIn("## knowledge_access", prompts[0])
        self.assertEqual(response.json()["advisory_trace"]["kag"]["resolution"], "inspect")
        self.assertEqual(
            response.json()["advisory_trace"]["kag"]["context"]["surface_id"],
            "AOA-K-0011",
        )

    def test_federated_run_accepts_kag_query_mode_selector(self) -> None:
        calls: list[tuple[str, dict]] = []
        prompts: list[str] = []

        def route_side_effect(path, payload):
            calls.append((path, payload))
            if path == "/kag/query-mode":
                return {
                    "ok": True,
                    "mode": "local_search",
                    "reasoning_scenarios": [{"scenario_ref": "AOA-P-0008"}],
                    "regrounding_modes": [{"mode_id": "source_export_reentry"}],
                    "source_files": [
                        "aoa-kag/generated/reasoning_handoff_pack.min.json",
                        "aoa-kag/generated/return_regrounding_pack.min.json",
                    ],
                }
            raise AssertionError(f"unexpected route-api call: {path}")

        def backend_side_effect(req):
            prompts.append(req.user_text)
            return {"ok": True, "backend": "stub", "model": "m", "answer": "done"}

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(self.module, "_invoke_run_backend", side_effect=backend_side_effect):
                with patch.object(
                    self.module,
                    "_load_return_policy_snapshot",
                    return_value={"policy_id": "agentic-default-return", "effective_profile_class": "workhorse"},
                ):
                    response = self.client.post(
                        "/run/federated",
                        json={
                            "user_text": "hello",
                            "kag": {"query_mode": "local_search"},
                        },
                    )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls, [("/kag/query-mode", {"mode": "local_search"})])
        self.assertIn("## knowledge_access", prompts[0])
        self.assertEqual(response.json()["advisory_trace"]["kag"]["resolution"], "query_mode")
        self.assertEqual(
            response.json()["advisory_trace"]["selectors"]["kag"],
            {"query_mode": "local_search"},
        )

    def test_federated_run_carries_playbook_review_packet_contract_in_trace(self) -> None:
        prompts: list[str] = []
        playbook = {
            "playbook_id": "AOA-P-0017",
            "name": "split-wave-cross-repo-rollout",
            "registry_entry": {"scenario": "split_wave_cross_repo_rollout"},
            "activation_entry": {"trigger": "release_window"},
            "federation_entry": {},
            "review_status": {
                "playbook_id": "AOA-P-0017",
                "gate_verdict": "composition-landed",
                "reviewed_run_count": 2,
            },
            "review_packet_contract": {
                "playbook_id": "AOA-P-0017",
                "scenario": "split_wave_cross_repo_rollout",
                "expected_artifacts": ["boundary_map", "handoff_record"],
                "eval_anchors": ["aoa-approval-boundary-adherence"],
                "memo_runtime_surfaces": [],
                "candidate_packet_kinds": [
                    "runtime_evidence_selection_candidate",
                    "artifact_hook_candidate",
                ],
                "review_required": True,
                "gate_verdict": "composition-landed",
            },
            "source_files": ["aoa-playbooks/generated/playbook_review_packet_contracts.min.json"],
        }

        def route_side_effect(path, payload):
            if path == "/playbooks/inspect":
                return {"ok": True, "playbook": playbook}
            raise AssertionError(f"unexpected route-api call: {path}")

        def backend_side_effect(req):
            prompts.append(req.user_text)
            return {"ok": True, "backend": "stub", "model": "m", "answer": "done"}

        with patch.object(self.module, "_route_api_post", side_effect=route_side_effect):
            with patch.object(self.module, "_invoke_run_backend", side_effect=backend_side_effect):
                response = self.client.post(
                    "/run/federated",
                    json={"user_text": "hello", "playbook_id": "AOA-P-0017"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("playbook_review_packet_contract", prompts[0])
        self.assertEqual(
            response.json()["advisory_trace"]["playbook"]["review_packet_contract"]["candidate_packet_kinds"],
            ["runtime_evidence_selection_candidate", "artifact_hook_candidate"],
        )


if __name__ == "__main__":
    unittest.main()
