import importlib.util
import json
import os
import shutil
import subprocess
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


def make_source_checkout(
    root: Path,
    *,
    owner_marker: str = "abyss-stack",
    readme_title: str | None = None,
    agents_owner_line: str | None = None,
) -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "docs" / "install").mkdir(parents=True)
    (root / "mechanics").mkdir()
    (root / "AGENTS.md").write_text(
        (agents_owner_line or f"Root route card for `{owner_marker}`.") + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        (readme_title or f"# {owner_marker}") + "\n",
        encoding="utf-8",
    )
    (root / "CONTRIBUTING.md").write_text("contributing\n", encoding="utf-8")
    (root / "scripts" / "validate_stack.py").write_text("# validator\n", encoding="utf-8")
    (root / "docs" / "install" / "DEPLOYMENT.md").write_text("deploy\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True, capture_output=True, text=True)
    return root


def write_source_identity(module, root: Path, receipt_path: Path, *, consumer: str = "autonomy-status") -> Path:
    receipt_path.write_text(
        json.dumps(module.SOURCE_IDENTITY.make_source_identity(root, consumer=consumer), indent=2) + "\n",
        encoding="utf-8",
    )
    return receipt_path


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


def sdk_canonical_surface_status() -> dict:
    authority = {
        "archive_authorized": False,
        "canonical_producer_switch_authorized": True,
        "compatibility_window_started": True,
        "live_runtime_mutation_authorized": True,
        "predecessor_maintenance_only": True,
        "sdk_canonical": True,
    }
    source_ref = "a" * 40
    predecessor_ref = "b" * 40
    return {
        "ok": True,
        "routing_switch": {
            "posture": "sdk_canonical",
            "activation_mode": "authorized_live_cutover",
            "canonical_posture": True,
            "canonical_ready": True,
            "canonical_reasons": [],
            "closure_ready": True,
            "live_cutover_active": True,
            "compatibility_rollback_active": False,
            "canonical_switch_authorized": True,
            "owner_switch_receipt": {
                "schema": "aoa_sdk_routing_g5_owner_switch_receipt_v1",
                "status": "g5_switch_authorized",
                "digest": "sha256:" + ("c" * 64),
                "compatibility_window": {
                    "started_by_sdk_version": "0.8.0",
                    "started_on": "2026-07-26",
                    "state": "started",
                },
            },
        },
        "layers_status": {
            "aoa-routing": {
                "closure_status": {
                    "mirror_ready": True,
                    "consumer_ready": True,
                    "provenance_ready": True,
                    "closure_ready": True,
                    "canonical_posture": True,
                    "canonical_ready": True,
                    "canonical_reasons": [],
                    "reasons": [],
                },
                "surface_metadata": {
                    "mirror_provenance": {
                        "routing_producer_posture": "sdk_canonical",
                        "cutover_activation_mode": (
                            "authorized_live_cutover"
                        ),
                        "operator_change_ref_present": True,
                        "source_git_commit": source_ref,
                        "artifact_subject_digest": (
                            "sha256:" + ("d" * 64)
                        ),
                        "canonical_producer": {
                            "owner_repo": "aoa-sdk",
                            "source_ref": source_ref,
                        },
                        "predecessor_rollback": {
                            "owner_repo": "aoa-routing",
                            "source_ref": predecessor_ref,
                        },
                        "g5_authority": authority,
                        "trust_verdict_available": True,
                    }
                },
            }
        },
    }


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
            make_source_checkout(source_root)
            receipt_path = write_source_identity(self.module, source_root, Path(tmpdir) / "source-identity.json", consumer="shared")

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(source_root), "AOA_SOURCE_IDENTITY": str(receipt_path)}):
                self.assertEqual(self.module.resolve_source_root(), source_root.resolve())

    def test_explicit_override_wins_over_conflicting_script_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            explicit_root = make_source_checkout(Path(tmpdir) / "explicit")
            script_root = make_source_checkout(Path(tmpdir) / "script")
            receipt_path = write_source_identity(self.module, explicit_root, Path(tmpdir) / "source-identity.json", consumer="shared")

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(explicit_root), "AOA_SOURCE_IDENTITY": str(receipt_path)}):
                with patch.object(self.module, "SCRIPT_ROOT", script_root):
                    self.assertEqual(self.module.resolve_source_root(), explicit_root.resolve())

    def test_invalid_explicit_override_does_not_fall_back_to_script_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_root = make_source_checkout(Path(tmpdir) / "script")
            invalid_root = Path(tmpdir) / "foreign"
            invalid_root.mkdir()

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(invalid_root)}):
                with patch.object(self.module, "SCRIPT_ROOT", script_root):
                    self.assertEqual(self.module.source_root_candidates()[0][0], "explicit_override")
                    self.assertIsNone(self.module.resolve_source_root())

    def test_clean_script_root_is_discovered_without_home_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script_root = make_source_checkout(Path(tmpdir) / "script")

            with patch.dict(os.environ, {}, clear=True):
                with patch.object(self.module, "SCRIPT_ROOT", script_root):
                    self.assertEqual(self.module.resolve_source_root(), script_root.resolve())

    def test_runtime_projection_is_rejected_even_when_it_has_source_markers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = make_source_checkout(stack_root / "Configs")

            with patch.dict(os.environ, {}, clear=True):
                with patch.object(self.module, "STACK_ROOT", stack_root):
                    with patch.object(self.module, "CONFIGS_ROOT", configs_root):
                        with patch.object(self.module, "SCRIPT_ROOT", configs_root):
                            self.assertIsNone(self.module.resolve_source_root())

    def test_deployed_projection_never_uses_home_source_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = make_source_checkout(stack_root / "Configs")
            home_source_root = make_source_checkout(Path(tmpdir) / "home" / "src" / "abyss-stack")

            with patch.dict(os.environ, {}, clear=True):
                with patch.object(self.module, "STACK_ROOT", stack_root):
                    with patch.object(self.module, "CONFIGS_ROOT", configs_root):
                        with patch.object(self.module, "SCRIPT_ROOT", configs_root):
                            with patch.object(self.module, "HOME_SOURCE_ROOT", home_source_root, create=True):
                                self.assertIsNone(self.module.resolve_source_root())

    def test_same_shape_foreign_checkout_requires_exact_identity_and_alias_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            foreign_root = make_source_checkout(Path(tmpdir) / "foreign")
            alias_root = Path(tmpdir) / "foreign-alias"
            alias_root.symlink_to(foreign_root, target_is_directory=True)
            receipt_path = write_source_identity(self.module, foreign_root, Path(tmpdir) / "foreign-identity.json", consumer="shared")

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(foreign_root)}, clear=True):
                self.assertIsNone(self.module.resolve_source_root())

            with patch.dict(
                os.environ,
                {"AOA_SOURCE_ROOT": str(alias_root), "AOA_SOURCE_IDENTITY": str(receipt_path)},
                clear=True,
            ):
                self.assertEqual(self.module.resolve_source_root(), foreign_root.resolve())

    def test_source_replacement_fails_binding_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source_root = make_source_checkout(Path(tmpdir) / "source")
            receipt_path = write_source_identity(self.module, source_root, Path(tmpdir) / "source-identity.json", consumer="shared")
            with patch.dict(
                os.environ,
                {"AOA_SOURCE_ROOT": str(source_root), "AOA_SOURCE_IDENTITY": str(receipt_path)},
                clear=True,
            ):
                binding = self.module.resolve_source_root_binding()
                self.assertIsNotNone(binding)
                replacement_root = make_source_checkout(Path(tmpdir) / "replacement")
                shutil.rmtree(source_root)
                replacement_root.rename(source_root)
                with self.assertRaises(self.module.SOURCE_IDENTITY.SourceIdentityError):
                    self.module.SOURCE_IDENTITY.revalidate_source_binding(binding)
                parity = self.module.run_parity_check(source_root, binding=binding)
                self.assertEqual(parity["detail"]["reason"], "source_root_unresolved")

    def test_foreign_owner_marker_is_not_a_source_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            foreign_root = make_source_checkout(Path(tmpdir) / "foreign", owner_marker="other-repo")

            with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(foreign_root)}):
                self.assertIsNone(self.module.resolve_source_root())

    def test_forged_prefix_suffix_and_substring_markers_are_rejected(self) -> None:
        cases = (
            {"readme_title": "# abyss-stack-fork"},
            {"readme_title": "# fork-abyss-stack"},
            {"agents_owner_line": "Root route card for `abyss-stack-fork`."},
            {"agents_owner_line": "owner: abyss-stack"},
        )
        for index, markers in enumerate(cases):
            with self.subTest(case=index):
                with tempfile.TemporaryDirectory() as tmpdir:
                    foreign_root = make_source_checkout(Path(tmpdir) / "foreign", **markers)

                    with patch.dict(os.environ, {"AOA_SOURCE_ROOT": str(foreign_root)}):
                        self.assertIsNone(self.module.resolve_source_root())

    def test_absent_canonical_source_is_explicitly_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(self.module, "SCRIPT_ROOT", Path(tmpdir) / "missing"):
                    self.assertEqual(self.module.source_root_candidates(), [])
                    self.assertIsNone(self.module.resolve_source_root())

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

    def test_unresolved_source_root_stays_distinct_from_parity_drift(self) -> None:
        payload = self.collect_payload(
            parity=make_check(
                status="fail",
                summary="source root unresolved",
                detail={"reason": "source_root_unresolved"},
            ),
        )

        self.assertIn("source_root_unresolved", payload["degradation_reasons"])
        self.assertNotIn("source_runtime_drift", payload["degradation_reasons"])

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

    def test_routing_sdk_canonical_closure_supersedes_predecessor_sync_mismatch(
        self,
    ) -> None:
        stale_result = {
            "command": ["aoa-sync-federation-surfaces"],
            "cwd": str(self.configs_root),
            "exit_code": 1,
            "stdout": (
                '{"layer":"aoa-routing","status":"stale",'
                '"freshness_status":"source_commit_mismatch"}'
            ),
            "stderr": "",
        }
        surface = sdk_canonical_surface_status()
        surface["ok"] = False
        with patch.object(self.module, "CONFIGS_ROOT", self.configs_root):
            with patch.object(
                self.module,
                "run_command",
                return_value=stale_result,
            ):
                with patch.object(
                    self.module,
                    "http_get_json",
                    return_value=surface,
                ):
                    result = self.module.run_federation_layer_check(
                        "aoa-routing"
                    )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["detail"]["accepted_via"],
            "route_api_sdk_canonical_closure",
        )
        self.assertEqual(result["detail"]["reasons"], [])
        self.assertEqual(
            result["detail"]["predecessor_sync_check"]["payload"]["status"],
            "stale",
        )

    def test_routing_sdk_canonical_fallback_fails_closed_on_isolated_state(
        self,
    ) -> None:
        stale_result = {
            "command": ["aoa-sync-federation-surfaces"],
            "cwd": str(self.configs_root),
            "exit_code": 1,
            "stdout": '{"layer":"aoa-routing","status":"stale"}',
            "stderr": "",
        }
        surface = sdk_canonical_surface_status()
        surface["routing_switch"]["activation_mode"] = "isolated"
        with patch.object(self.module, "CONFIGS_ROOT", self.configs_root):
            with patch.object(
                self.module,
                "run_command",
                return_value=stale_result,
            ):
                with patch.object(
                    self.module,
                    "http_get_json",
                    return_value=surface,
                ):
                    result = self.module.run_federation_layer_check(
                        "aoa-routing"
                    )

        self.assertEqual(result["status"], "degraded")
        self.assertIn(
            "routing_switch_activation_mode_invalid",
            result["detail"]["reasons"],
        )

    def test_current_predecessor_sync_does_not_query_route_api_fallback(
        self,
    ) -> None:
        current_result = {
            "command": ["aoa-sync-federation-surfaces"],
            "cwd": str(self.configs_root),
            "exit_code": 0,
            "stdout": '{"layer":"aoa-routing","status":"ok"}',
            "stderr": "",
        }
        with patch.object(self.module, "CONFIGS_ROOT", self.configs_root):
            with patch.object(
                self.module,
                "run_command",
                return_value=current_result,
            ):
                with patch.object(
                    self.module,
                    "http_get_json",
                    side_effect=AssertionError("fallback should not run"),
                ):
                    result = self.module.run_federation_layer_check(
                        "aoa-routing"
                    )

        self.assertEqual(result["status"], "pass")
