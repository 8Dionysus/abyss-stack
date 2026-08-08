from __future__ import annotations

import importlib.util
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
from pathlib import Path
from typing import Any

from tests.compose_yaml_subset import load_compose_services


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = REPO_ROOT / "compose" / "modules"
PROFILE_DIR = REPO_ROOT / "compose" / "profiles"
RAG_CONFIG_DIR = REPO_ROOT / "config-templates" / "Configs" / "rag"
MACHINE_BRIDGE_BACKEND = REPO_ROOT / "mechanics" / "machine-fit" / "parts" / "machine-bridge" / "aoa_machine_bridge.py"
RERANK_BACKEND = REPO_ROOT / "config-templates" / "Services" / "rerank-api" / "app" / "main.py"


def load_yaml(path: Path) -> dict[str, Any]:
    data = load_compose_services(path)
    if not isinstance(data, dict):
        raise AssertionError(f"{path} did not parse to a YAML mapping")
    return data


def profile_modules(profile: str) -> list[str]:
    return [
        line.strip()
        for line in (PROFILE_DIR / f"{profile}.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def module_services(module_name: str) -> dict[str, Any]:
    return load_yaml(MODULE_DIR / module_name).get("services", {})


class RagBridgeContractsTests(unittest.TestCase):
    @staticmethod
    def load_rerank_backend() -> Any:
        existing = sys.modules.get("rerank_api_under_test")
        if existing is not None:
            return existing
        spec = importlib.util.spec_from_file_location("rerank_api_under_test", RERANK_BACKEND)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        with mock.patch.dict(os.environ, {"AOA_RERANK_FAKE": "1"}):
            spec.loader.exec_module(module)
        return module

    def test_rag_profile_contains_dependency_modules_before_rag_api(self) -> None:
        modules = profile_modules("rag")

        self.assertIn("45-rerank-api.yml", modules)
        self.assertIn("46-rag-api.yml", modules)
        self.assertLess(modules.index("45-rerank-api.yml"), modules.index("46-rag-api.yml"))
        for required in {
            "10-storage.yml",
            "31-intel-inference.yml",
            "41-agent-api.yml",
            "42-agent-api-intel.yml",
            "43-federation-router.yml",
        }:
            self.assertIn(required, modules)

    def test_rag_api_depends_only_on_services_present_in_rag_profile(self) -> None:
        services: dict[str, Any] = {}
        for module in profile_modules("rag"):
            services.update(module_services(module))
        rag_api = services["rag-api"]
        depends_on = rag_api.get("depends_on", {})

        self.assertTrue(depends_on)
        for service_name in depends_on:
            with self.subTest(service=service_name):
                self.assertIn(service_name, services)

    def test_rag_api_mounts_sources_readonly_and_logs_writable(self) -> None:
        rag_api = module_services("46-rag-api.yml")["rag-api"]
        volumes = rag_api.get("volumes", [])

        readonly_sources = [
            volume
            for volume in volumes
            if "/app/config/rag" in volume or "/sources/" in volume
        ]
        self.assertTrue(readonly_sources)
        for volume in readonly_sources:
            with self.subTest(volume=volume):
                self.assertRegex(volume, r":ro[,]")
        self.assertTrue(any("/Logs/rag-api:/app/logs:Z" in volume for volume in volumes))

    def test_rerank_api_is_lazy_owner_managed_and_host_cache_routed(self) -> None:
        rerank = module_services("45-rerank-api.yml")["rerank-api"]
        env = rerank.get("environment", {})
        volumes = rerank.get("volumes", [])

        self.assertIn("AOA_RERANK_IDLE_UNLOAD_SEC", env)
        self.assertEqual(env.get("AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD"), "${AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD:-true}")
        self.assertNotIn("mem_limit", rerank)
        self.assertNotIn("mem_reservation", rerank)
        self.assertNotIn("cpus", rerank)
        self.assertTrue(any("/srv/abyss-machine/cache/ai/qwen3-reranker" in volume for volume in volumes))
        self.assertTrue(any("/srv/abyss-machine/cache/ai/openvino/qwen3-reranker" in volume for volume in volumes))

    def test_rerank_owner_memory_relief_is_atomic_and_idempotent(self) -> None:
        backend = self.load_rerank_backend()
        scorer = backend.LazyScorer()
        scorer._scorer = SimpleNamespace(load_ms=1.0)
        request = backend.MemoryReliefRequest(
            action="relieve_memory",
            action_id="a" * 32,
            owner="abyss-stack",
            workload_id="rerank-api:qwen3-0.6b",
        )

        first = scorer.owner_memory_relief(request)
        replay = scorer.owner_memory_relief(request)

        self.assertTrue(first["ok"])
        self.assertTrue(first["unloaded"])
        self.assertFalse(first["loaded"])
        self.assertEqual(first["owner_gate"]["active_requests_at_action"], 0)
        self.assertEqual(replay, first)

    def test_rerank_owner_memory_relief_refuses_active_request(self) -> None:
        backend = self.load_rerank_backend()
        scorer = backend.LazyScorer()
        scorer._scorer = SimpleNamespace(load_ms=1.0)
        scorer.begin_request()
        request = backend.MemoryReliefRequest(
            action="relieve_memory",
            action_id="b" * 32,
            owner="abyss-stack",
            workload_id="rerank-api:qwen3-0.6b",
        )

        result = scorer.owner_memory_relief(request)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "active_requests")
        self.assertEqual(result["owner_gate"]["active_requests_at_action"], 1)
        self.assertTrue(result["loaded"])

    def test_rag_manifests_exist_and_are_json_objects(self) -> None:
        for name in ("sources.json", "agentic-graph.v1.json", "dag-jobs.v1.json"):
            with self.subTest(manifest=name):
                path = RAG_CONFIG_DIR / name
                self.assertTrue(path.exists())
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIsInstance(data, dict)

    def test_machine_bridge_contract_declares_readonly_dependency_direction(self) -> None:
        spec = importlib.util.spec_from_file_location("aoa_machine_bridge_under_test", MACHINE_BRIDGE_BACKEND)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        routes = module.topological_routes(Path("/srv/AbyssOS/abyss-stack"), "public")
        catalog = module.command_catalog({"paths": {"commands": {"stack_bridge_export": "abyss-machine stack-bridge export --json"}}})
        summary = module.check_summary({"status": "ready", "summary": {"warnings": 0}, "warnings": []})

        self.assertEqual(
            routes["machine_to_stack"]["direction"],
            "abyss-stack consumes abyss-machine; abyss-machine does not import or mutate abyss-stack",
        )
        self.assertIn("scripts/aoa-machine-bridge --write-latest", catalog["required_stack_side_commands"])
        self.assertEqual(summary["artifact_kind"], "aoa.machine-bridge.check")
        self.assertIn("public-safe", " ".join(summary["non_claims"]))


if __name__ == "__main__":
    unittest.main()
