import importlib.util
import os
import tempfile
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
MODULE_PATH = (
    REPO_ROOT
    / "mechanics"
    / "governed-execution"
    / "parts"
    / "autonomy-status"
    / "aoa_status_autonomy.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("aoa_status_autonomy_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_check(*, status: str, summary: str, detail: dict | None = None) -> dict:
    payload = {"status": status, "summary": summary}
    if detail is not None:
        payload["detail"] = detail
    return payload


def trial_check(*, status: str, trial_proven: bool, live_available: bool) -> dict:
    return make_check(
        status=status,
        summary="trial status",
        detail={
            "path": "/tmp/index.json",
            "gate_result": "pass" if trial_proven else "fail",
            "truth_status": {
                "source_authored": True,
                "deployed": True,
                "trial_proven": trial_proven,
                "live_available": live_available,
                "notes": [],
            },
        },
    )


class AutonomyCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.configs_root = Path(self.temp_dir.name)
        scripts_dir = self.configs_root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        for name in ("aoa-status", "aoa-llamacpp-pilot", "aoa-sync-federation-surfaces"):
            (scripts_dir / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    def test_resolve_source_root_accepts_current_install_deployment_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = Path(tmpdir) / "source"
            (source_root / "scripts").mkdir(parents=True)
            (source_root / "docs" / "install").mkdir(parents=True)
            (source_root / "CONTRIBUTING.md").write_text("contributing\n", encoding="utf-8")
            (source_root / "scripts" / "validate_stack.py").write_text("# validator\n", encoding="utf-8")
            (source_root / "docs" / "install" / "DEPLOYMENT.md").write_text("deploy\n", encoding="utf-8")

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(source_root)}):
                self.assertEqual(self.module.resolve_source_root(), source_root.resolve())

    def collect_payload(
        self,
        *,
        parity: dict | None = None,
        verify: dict | None = None,
        route_requirement: dict | None = None,
        route_health: dict | None = None,
        route_surface: dict | None = None,
        federation: dict | None = None,
        long_horizon: dict | None = None,
        bounded_autonomy: dict | None = None,
    ) -> dict:
        parity = parity or make_check(status="pass", summary="parity green", detail={})
        verify = verify or make_check(status="pass", summary="verify green", detail={"payload": {"ok": True}})
        route_requirement = route_requirement or {
            "required": True,
            "route_api_container_state": "running",
            "federated_consumer_enabled": True,
            "reason": "route-api container state is running",
        }
        route_health = route_health or make_check(
            status="pass",
            summary="health green",
            detail={
                "url": "http://127.0.0.1:5402/health",
                "ok": True,
                "mirror_ready": True,
                "closure_summary": {
                    "closure_ready": True,
                    "ready_layer_count": 7,
                    "layer_count": 7,
                    "ready_layers": list(self.module.FEDERATION_LAYERS),
                    "degraded_layers": [],
                    "failing_layers": [],
                },
            },
        )
        route_surface = route_surface or make_check(
            status="pass",
            summary="surface status green",
            detail={
                "url": "http://127.0.0.1:5402/surface-status",
                "ok": True,
                "closure_summary": {
                    "closure_ready": True,
                    "ready_layer_count": 7,
                    "layer_count": 7,
                    "ready_layers": list(self.module.FEDERATION_LAYERS),
                    "degraded_layers": [],
                    "failing_layers": [],
                },
            },
        )
        federation = federation or {
            "status": "pass",
            "summary": "all green",
            "layers": {
                layer: make_check(status="pass", summary="ok", detail={})
                for layer in self.module.FEDERATION_LAYERS
            },
        }
        long_horizon = long_horizon or trial_check(status="pass", trial_proven=True, live_available=True)
        bounded_autonomy = bounded_autonomy or trial_check(status="pass", trial_proven=True, live_available=True)

        with patch.object(self.module, "CONFIGS_ROOT", self.configs_root):
                with patch.object(self.module, "run_parity_check", return_value=parity):
                    with patch.object(self.module, "run_llamacpp_verify", return_value=verify):
                        with patch.object(
                            self.module,
                            "route_api_requirement",
                            return_value=route_requirement,
                        ):
                            with patch.object(self.module, "fetch_route_api_health", return_value=route_health):
                                with patch.object(
                                    self.module,
                                    "fetch_route_api_surface_status",
                                    return_value=route_surface,
                                ):
                                    with patch.object(
                                        self.module,
                                        "run_federation_layer_checks",
                                        return_value=federation,
                                    ):
                                        with patch.object(self.module, "summarize_trial_index", side_effect=[long_horizon, bounded_autonomy]):
                                            return self.module.collect_autonomy_status(source_root=REPO_ROOT)

    def test_green_path_returns_pass_and_live_available(self) -> None:
        payload = self.collect_payload()

        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["degradation_reasons"], [])
        self.assertTrue(payload["truth_status"]["control_plane"]["live_available"])
        self.assertEqual(payload["checks"]["federation_layers"]["status"], "pass")

    def test_parity_failure_returns_fail(self) -> None:
        payload = self.collect_payload(
            parity=make_check(status="fail", summary="parity failed", detail={}),
        )

        self.assertEqual(payload["overall_status"], "fail")
        self.assertIn("source_runtime_drift", payload["degradation_reasons"])
        self.assertFalse(payload["truth_status"]["control_plane"]["live_available"])

    def test_llamacpp_verify_failure_returns_fail(self) -> None:
        payload = self.collect_payload(
            verify=make_check(status="fail", summary="verify failed", detail={"payload": {"ok": False}}),
        )

        self.assertEqual(payload["overall_status"], "fail")
        self.assertIn("llamacpp_verify_failed", payload["degradation_reasons"])

    def test_closure_gap_returns_degraded(self) -> None:
        payload = self.collect_payload(
            route_surface=make_check(
                status="pass",
                summary="surface status green",
                detail={
                    "url": "http://127.0.0.1:5402/surface-status",
                    "ok": True,
                    "closure_summary": {
                        "closure_ready": False,
                        "ready_layer_count": 6,
                        "layer_count": 7,
                        "ready_layers": [
                            layer for layer in self.module.FEDERATION_LAYERS if layer != "aoa-memo"
                        ],
                        "degraded_layers": ["aoa-memo"],
                        "failing_layers": [],
                    },
                },
            ),
        )

        self.assertEqual(payload["overall_status"], "degraded")
        self.assertIn("closure_gap:aoa-memo", payload["degradation_reasons"])

    def test_trial_live_gap_returns_degraded(self) -> None:
        payload = self.collect_payload(
            long_horizon=trial_check(status="degraded", trial_proven=True, live_available=False),
        )

        self.assertEqual(payload["overall_status"], "degraded")
        self.assertIn("trial_live_gap:long_horizon", payload["degradation_reasons"])
        self.assertFalse(payload["truth_status"]["control_plane"]["live_available"])

    def test_route_api_not_enabled_does_not_fail_the_default_runtime_shape(self) -> None:
        payload = self.collect_payload(
            route_requirement={
                "required": False,
                "route_api_container_state": "missing",
                "federated_consumer_enabled": False,
                "reason": "federation profile is not active and federated advisory consumption is disabled",
            },
            route_health=make_check(
                status="not_enabled",
                summary="route-api health is not required in the current runtime shape",
                detail={},
            ),
            route_surface=make_check(
                status="not_enabled",
                summary="route-api closure reporting is not required in the current runtime shape",
                detail={},
            ),
            federation={
                "status": "not_enabled",
                "summary": "federation seam checks are not required in the current runtime shape",
                "layers": {},
                "detail": {},
            },
        )

        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["checks"]["route_api_health"]["status"], "not_enabled")
        self.assertEqual(payload["checks"]["route_api_surface_status"]["status"], "not_enabled")
        self.assertEqual(payload["checks"]["federation_layers"]["status"], "not_enabled")
        self.assertEqual(payload["degradation_reasons"], [])
        self.assertTrue(payload["truth_status"]["control_plane"]["live_available"])

    def test_route_api_requirement_treats_missing_route_api_container_as_optional(self) -> None:
        with patch.object(
            self.module,
            "run_command",
            return_value={
                "command": ["podman", "inspect"],
                "cwd": None,
                "exit_code": 125,
                "stdout": "",
                "stderr": 'Error: no such object: "route-api"',
            },
        ):
            requirement = self.module.route_api_requirement()

        self.assertFalse(requirement["required"])
        self.assertEqual(requirement["route_api_container_state"], "missing")

    def test_route_api_requirement_keeps_inspect_errors_actionable(self) -> None:
        with patch.object(
            self.module,
            "run_command",
            return_value={
                "command": ["podman", "inspect"],
                "cwd": None,
                "exit_code": 125,
                "stdout": "",
                "stderr": "Error: cannot connect to Podman socket",
            },
        ):
            requirement = self.module.route_api_requirement()

        self.assertTrue(requirement["required"])
        self.assertEqual(requirement["route_api_container_state"], "inspect_error")
        self.assertEqual(requirement["reason"], "route-api container state is inspect_error")
