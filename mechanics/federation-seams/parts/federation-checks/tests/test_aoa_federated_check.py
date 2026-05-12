import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


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
MODULE_PATH = REPO_ROOT / "scripts" / "aoa-federated-check"


def load_module():
    loader = importlib.machinery.SourceFileLoader("aoa_federated_check_under_test", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FederatedCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_run_check_returns_not_enabled_without_failure_by_default(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": False,
                }
            )
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses) as mocked:
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=False,
                query_mode="local_search",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "not_enabled")
        self.assertFalse(result["gate_enabled"])
        self.assertEqual(mocked.call_count, 1)

    def test_run_check_fails_when_enabled_gate_is_required(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": False,
                }
            )
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode="local_search",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "disabled")
        self.assertIn("disabled", result["error"])

    def test_run_check_validates_kag_query_mode_contract(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "advisory seam live",
                    "advisory_trace": {
                        "selectors": {"kag": {"query_mode": "local_search"}},
                        "kag": {
                            "resolution": "query_mode",
                            "context": {"mode": "local_search"},
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode="local_search",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "pass")
        self.assertEqual(
            result["validation"]["observed"]["selector"],
            {"query_mode": "local_search"},
        )
        self.assertEqual(result["validation"]["observed"]["kag_resolution"], "query_mode")

    def test_build_probe_payload_supports_explicit_inspect_selector(self) -> None:
        payload = self.module.build_probe_payload(query_mode=None, inspect_id="AOA-K-0011")

        self.assertEqual(payload["kag"], {"inspect_id": "AOA-K-0011"})
        self.assertIn("Zarathustra retrieval surface", payload["user_text"])

    def test_build_probe_payload_supports_playbook_selector(self) -> None:
        payload = self.module.build_probe_payload(query_mode=None, inspect_id=None, playbook_id="AOA-P-0008")

        self.assertEqual(payload["playbook_id"], "AOA-P-0008")
        self.assertEqual(payload["user_text"], "Summarize the current route in one short line only.")

    def test_build_probe_payload_supports_memo_selector(self) -> None:
        payload = self.module.build_probe_payload(
            query_mode=None,
            inspect_id=None,
            playbook_id=None,
            memo_id="AOA-M-0001",
        )

        self.assertEqual(
            payload["memo"],
            {"family": "router", "mode": "semantic", "id": "AOA-M-0001"},
        )
        self.assertEqual(payload["user_text"], "Use this memo card if it helps. Return one short line only.")

    def test_run_check_validates_kag_inspect_contract(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "zarathustra route pack consulted",
                    "advisory_trace": {
                        "selectors": {"kag": {"inspect_id": "AOA-K-0011"}},
                        "kag": {
                            "resolution": "inspect",
                            "context": {
                                "selector_kind": "inspect_id",
                                "surface_id": "AOA-K-0011",
                            },
                            "source_files": ["aoa-kag/generated/tos_zarathustra_route_retrieval_pack.min.json"],
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id="AOA-K-0011",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "pass")
        self.assertEqual(
            result["validation"]["observed"]["selector"],
            {"inspect_id": "AOA-K-0011"},
        )
        self.assertEqual(result["validation"]["observed"]["kag_resolution"], "inspect")
        self.assertEqual(result["validation"]["observed"]["kag_surface_id"], "AOA-K-0011")
        self.assertTrue(result["validation"]["observed"]["kag_source_files"])

    def test_run_check_validates_playbook_contract(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "Route AOA-P-0008: bounded orchestration with strict evaluation.",
                    "advisory_trace": {
                        "selectors": {"playbook_id": "AOA-P-0008"},
                        "playbook": {
                            "summary": {"playbook_id": "AOA-P-0008", "scenario": "model_tier_orchestration"},
                            "source_files": [
                                "aoa-playbooks/generated/playbook_registry.min.json",
                                "aoa-playbooks/generated/playbook_review_packet_contracts.min.json",
                            ],
                            "review_packet_contract": {
                                "playbook_id": "AOA-P-0008",
                                "candidate_packet_kinds": ["runtime_evidence_selection_candidate"],
                            },
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id=None,
                playbook_id="AOA-P-0008",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "pass")
        self.assertEqual(result["validation"]["observed"]["selector"], "AOA-P-0008")
        self.assertEqual(result["validation"]["observed"]["playbook_summary_id"], "AOA-P-0008")
        self.assertTrue(result["validation"]["observed"]["playbook_source_files"])
        self.assertTrue(result["validation"]["observed"]["review_packet_contract"])

    def test_run_check_validates_memo_contract(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "This memo defines the role, mission, and hard rules of the aoa-memo system.",
                    "advisory_trace": {
                        "selectors": {
                            "playbook_id": None,
                            "playbook_select": None,
                            "kag": None,
                            "profile_class": "workhorse",
                        },
                        "memo": {
                            "selector": {
                                "source": "request",
                                "family": "router",
                                "mode": "semantic",
                                "id": "AOA-M-0001",
                                "section_id": None,
                                "expand_requested": False,
                                "return_ready": False,
                                "read_path": None,
                                "spec": {},
                            },
                            "sequence": ["recall_contract", "inspect", "capsule"],
                            "resolution": "capsule",
                            "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id=None,
                playbook_id=None,
                memo_id="AOA-M-0001",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "pass")
        self.assertEqual(result["validation"]["observed"]["memo_selector_source"], "request")
        self.assertEqual(result["validation"]["observed"]["memo_selector_family"], "router")
        self.assertEqual(result["validation"]["observed"]["memo_selector_mode"], "semantic")
        self.assertEqual(result["validation"]["observed"]["memo_selector_id"], "AOA-M-0001")
        self.assertEqual(result["validation"]["observed"]["memo_resolution"], "capsule")
        self.assertEqual(
            result["validation"]["observed"]["memo_sequence"],
            ["recall_contract", "inspect", "capsule"],
        )
        self.assertTrue(result["validation"]["observed"]["memo_source_files"])

    def test_run_check_fails_when_advisory_trace_contract_is_missing(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "advisory seam live",
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode="local_search",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "fail")
        self.assertIn("advisory contract", result["error"])

    def test_run_check_fails_when_inspect_contract_lacks_surface_id(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "zarathustra route pack consulted",
                    "advisory_trace": {
                        "selectors": {"kag": {"inspect_id": "AOA-K-0011"}},
                        "kag": {
                            "resolution": "inspect",
                            "context": {
                                "selector_kind": "inspect_id",
                            },
                            "source_files": ["aoa-kag/generated/tos_zarathustra_route_retrieval_pack.min.json"],
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id="AOA-K-0011",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "fail")
        self.assertIn("advisory contract", result["error"])

    def test_run_check_fails_when_playbook_contract_lacks_review_packet_contract(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "Route AOA-P-0008: bounded orchestration with strict evaluation.",
                    "advisory_trace": {
                        "selectors": {"playbook_id": "AOA-P-0008"},
                        "playbook": {
                            "summary": {"playbook_id": "AOA-P-0008"},
                            "source_files": ["aoa-playbooks/generated/playbook_registry.min.json"],
                        },
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id=None,
                playbook_id="AOA-P-0008",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "fail")
        self.assertIn("advisory contract", result["error"])

    def test_run_check_fails_when_memo_contract_does_not_hydrate_capsule(self) -> None:
        responses = [
            FakeHTTPResponse(
                {
                    "ok": True,
                    "service": "langchain-api",
                    "federated_run_enabled": True,
                }
            ),
            FakeHTTPResponse(
                {
                    "ok": True,
                    "backend": "stub",
                    "model": "qwen",
                    "answer": "memo consulted",
                    "advisory_trace": {
                        "memo": {
                            "selector": {
                                "source": "request",
                                "family": "router",
                                "mode": "semantic",
                                "id": "AOA-M-0001",
                            },
                            "sequence": ["recall_contract"],
                            "resolution": "contract_only",
                            "source_files": ["aoa-memo/examples/recall_contract.router.semantic.json"],
                        }
                    },
                }
            ),
        ]

        with patch.object(self.module.urllib.request, "urlopen", side_effect=responses):
            result = self.module.run_check(
                url="http://example.test/run/federated",
                health_url="http://example.test/health",
                timeout_s=5.0,
                require_enabled=True,
                query_mode=None,
                inspect_id=None,
                playbook_id=None,
                memo_id="AOA-M-0001",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["state"], "fail")
        self.assertIn("advisory contract", result["error"])
