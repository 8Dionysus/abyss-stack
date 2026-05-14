from __future__ import annotations

import argparse
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[5]
MODULE_PATH = (
    REPO_ROOT
    / "mechanics"
    / "diagnostic-spine"
    / "parts"
    / "diagnose-wrapper"
    / "aoa_diagnose.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("aoa_diagnose_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def load_schema(relative_path: str) -> dict:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


class AoADiagnoseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.target_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json"))
        cls.session_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json"))
        cls.companion_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json"))
        cls.anchor_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json"))
        cls.handoff_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json"))
        cls.review_ref_validator = Draft202012Validator(load_schema("mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json"))

    def make_args(
        self,
        *,
        against: str | None = None,
        session_refs: list[str] | None = None,
        diagnosis_refs: list[str] | None = None,
        write: str | None = None,
        write_latest: bool = False,
        diagnostic_id: str = "diag-test",
    ) -> argparse.Namespace:
        return argparse.Namespace(
            truth_goal="live_available",
            against=against,
            with_session_ref=session_refs or [],
            with_reviewed_diagnosis_ref=diagnosis_refs or [],
            write=write,
            write_latest=write_latest,
            write_last_good_ref=False,
            write_reviewed_diagnosis_ref=False,
            reviewer="codex",
            diagnostic_id=diagnostic_id,
        )

    def selector_context(self) -> dict:
        return {
            "presets": ["intel-full"],
            "preset": "intel-full",
            "profiles": ["intel", "tools", "observability"],
            "modules": [
                "10-storage.yml",
                "31-intel-inference.yml",
                "32-llamacpp-inference.yml",
                "41-agent-api.yml",
                "51-browser-tools.yml",
                "60-monitoring.yml",
            ],
            "internal_selected": True,
        }

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

    def green_doctor(self) -> dict:
        return {
            "status": "pass",
            "summary": "aoa-doctor is green for the selected runtime shape",
            "command": ["bash", "/tmp/aoa-doctor"],
            "exit_code": 0,
            "warnings": ["vault mount /abyss not present"],
            "material_warnings": [],
            "advisory_warnings": ["vault mount /abyss not present"],
            "failures": [],
            "stdout": "",
            "stderr": "",
        }

    def green_render(self) -> dict:
        return {
            "status": "pass",
            "summary": "rendered service shape resolved successfully",
            "command": ["bash", "/tmp/aoa-render-services"],
            "exit_code": 0,
            "services": ["neo4j", "postgres", "llama-cpp", "langchain-api", "aoa-browser", "prometheus"],
            "stdout": "",
            "stderr": "",
        }

    def green_autonomy(self) -> dict:
        return {
            "status": "pass",
            "summary": "autonomy control-plane verdict collected",
            "command": ["bash", "/tmp/aoa-status", "--autonomy", "--json"],
            "exit_code": 0,
            "payload": {
                "overall_status": "pass",
                "checks": {
                    "route_api_surface_status": {"status": "not_enabled"},
                },
            },
            "truth_status": {
                "source_authored": True,
                "deployed": True,
                "trial_proven": True,
                "live_available": True,
            },
            "degradation_reasons": [],
            "stdout": "{}",
            "stderr": "",
        }

    def test_collect_diagnostic_bundle_green_path_matches_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {
                    "artifact_kind": "aoa.host-facts",
                    "captured_at": "2026-04-07T00:00:00Z",
                },
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {
                    "artifact_kind": "aoa.machine-fit",
                    "captured_at": "2026-04-07T00:00:00Z",
                },
            )
            write_json(
                stack_root / "Logs" / "platform-adaptations" / "latest" / "latest.private.json",
                {
                    "artifact_kind": "aoa.platform-adaptation",
                    "captured_at": "2026-04-07T00:00:00Z",
                },
            )

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=self.green_autonomy(),
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(),
                    selector_context=self.selector_context(),
                )

        self.target_validator.validate(bundle["target"])
        self.session_validator.validate(bundle["session"])
        self.assertEqual(bundle["session"]["exit_class"], "running_as_intended")
        self.assertEqual(bundle["session"]["axes"]["closure"], "skipped")
        self.assertEqual(bundle["session"]["next_moves"], [
            {
                "class": "no_action",
                "summary": "The current diagnostic pass is green for the selected target shape.",
                "owner_repo": "abyss-stack",
                "requires_approval": False,
            }
        ])

    def test_against_anchor_regression_emits_truth_gap_and_repair_packet_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {"artifact_kind": "aoa.host-facts", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.machine-fit", "captured_at": "2026-04-07T00:00:00Z"},
            )
            anchor_path = stack_root / "anchors" / "last-good.session.json"
            write_json(
                anchor_path,
                {
                    "schema_version": "diagnostic_session_v1",
                    "id": "diag-anchor",
                    "repo": "abyss-stack",
                    "captured_at": "2026-04-06T00:00:00Z",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel", "tools", "observability"],
                        "truth_goal": "live_available",
                    },
                    "axes": {
                        "readiness": "pass",
                        "posture": "pass",
                        "render_truth": "pass",
                        "runtime_health": "pass",
                        "closure": "skipped",
                        "evidence": "pass",
                        "governability": "pass",
                    },
                    "truth_status": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                    },
                    "drifts": [],
                    "exit_class": "running_as_intended",
                    "public_safe": True,
                },
            )
            autonomy = self.green_autonomy()
            autonomy["status"] = "degraded"
            autonomy["payload"]["overall_status"] = "degraded"
            autonomy["truth_status"]["live_available"] = False
            autonomy["degradation_reasons"] = ["trial_live_gap:bounded_autonomy"]

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=autonomy,
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(against=str(anchor_path)),
                    selector_context=self.selector_context(),
                )

        self.assertEqual(bundle["session"]["exit_class"], "repairable_under_governance")
        self.assertTrue(any(drift["kind"] == "truth_gap" for drift in bundle["session"]["drifts"]))
        self.assertTrue(
            any(move["class"] == "repair_packet_candidate" for move in bundle["session"]["next_moves"])
        )

    def test_write_bundle_latest_materializes_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            with patch.object(self.module, "STACK_ROOT", stack_root):
                bundle = {
                    "target": {
                        "schema_version": "diagnostic_target_v1",
                        "id": "intel-full-live",
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                        "required_checks": ["doctor"],
                        "drift_watch": ["source_deploy_drift"],
                        "public_safe": True,
                    },
                    "session": {
                        "schema_version": "diagnostic_session_v1",
                        "id": "diag-materialized",
                        "repo": "abyss-stack",
                        "captured_at": "2026-04-07T00:00:00Z",
                        "target": {
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "truth_goal": "live_available",
                        },
                        "axes": {
                            "readiness": "pass",
                            "posture": "pass",
                            "render_truth": "pass",
                            "runtime_health": "pass",
                            "closure": "skipped",
                            "evidence": "pass",
                            "governability": "pass",
                        },
                        "truth_status": {
                            "source_authored": True,
                            "deployed": True,
                            "trial_proven": True,
                            "live_available": True,
                        },
                        "drifts": [],
                        "exit_class": "running_as_intended",
                        "public_safe": True,
                    },
                    "_meta": {
                        "selector": {
                            "presets": ["intel-full"],
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "modules": [],
                            "internal_selected": False,
                        },
                        "refs": {
                            "session_refs": [],
                            "against_ref_path": None,
                            "against_missing": False,
                        },
                    },
                }
                self.module.write_bundle(
                    bundle,
                    self.make_args(write_latest=True, diagnostic_id="diag-materialized"),
                )

            self.assertTrue((stack_root / "Logs" / "diagnostics" / "latest" / "diagnostic_target.json").is_file())
            self.assertTrue((stack_root / "Logs" / "diagnostics" / "latest" / "diagnostic_session.json").is_file())
            self.assertTrue((stack_root / "Logs" / "diagnostics" / "latest" / "diagnosis_companion.json").is_file())
            self.assertTrue((stack_root / "Logs" / "diagnostics" / "latest" / "repair_handoff.json").is_file())
            self.assertTrue(
                (
                    stack_root
                    / "Logs"
                    / "diagnostics"
                    / "records"
                    / "diag-materialized"
                    / "diagnostic_session.json"
                ).is_file()
            )
            companion = json.loads(
                (stack_root / "Logs" / "diagnostics" / "latest" / "diagnosis_companion.json").read_text(encoding="utf-8")
            )
            self.companion_validator.validate(companion)
            self.assertEqual(companion["review_status"], "not_needed")
            handoff = json.loads(
                (stack_root / "Logs" / "diagnostics" / "latest" / "repair_handoff.json").read_text(encoding="utf-8")
            )
            self.handoff_validator.validate(handoff)
            self.assertEqual(handoff["handoff_readiness"], "not_needed")

    def test_write_last_good_ref_materializes_anchor_for_green_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            with patch.object(self.module, "STACK_ROOT", stack_root):
                bundle = {
                    "target": {
                        "schema_version": "diagnostic_target_v1",
                        "id": "intel-full-live",
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                        "required_checks": ["doctor"],
                        "drift_watch": ["source_deploy_drift"],
                        "public_safe": True,
                    },
                    "session": {
                        "schema_version": "diagnostic_session_v1",
                        "id": "diag-anchor-green",
                        "repo": "abyss-stack",
                        "captured_at": "2026-04-07T00:00:00Z",
                        "target": {
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "truth_goal": "live_available",
                        },
                        "axes": {
                            "readiness": "pass",
                            "posture": "pass",
                            "render_truth": "pass",
                            "runtime_health": "pass",
                            "closure": "skipped",
                            "evidence": "pass",
                            "governability": "pass",
                        },
                        "truth_status": {
                            "source_authored": True,
                            "deployed": True,
                            "trial_proven": True,
                            "live_available": True,
                        },
                        "drifts": [],
                        "exit_class": "running_as_intended",
                        "public_safe": True,
                    },
                    "_meta": {
                        "selector": {
                            "presets": ["intel-full"],
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "modules": [],
                            "internal_selected": False,
                        },
                        "refs": {
                            "session_refs": [],
                            "against_ref_path": None,
                            "against_missing": False,
                        },
                    },
                }
                args = self.make_args(write_latest=True, diagnostic_id="diag-anchor-green")
                args.write_last_good_ref = True
                self.module.write_bundle(bundle, args)

            anchor = json.loads(
                (stack_root / "Logs" / "diagnostics" / "latest" / "last_good.ref.json").read_text(encoding="utf-8")
            )
            self.anchor_validator.validate(anchor)
            self.assertEqual(anchor["anchor_class"], "last_good")
            self.assertEqual(anchor["diagnostic_session_id"], "diag-anchor-green")

    def test_write_last_good_ref_rejects_drifted_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            bundle = {
                "target": {
                    "schema_version": "diagnostic_target_v1",
                    "id": "intel-full-live",
                    "preset": "intel-full",
                    "profiles": ["intel"],
                    "truth_goal": "live_available",
                    "required_checks": ["doctor"],
                    "drift_watch": ["source_deploy_drift"],
                    "public_safe": True,
                },
                "session": {
                    "schema_version": "diagnostic_session_v1",
                    "id": "diag-anchor-reject",
                    "repo": "abyss-stack",
                    "captured_at": "2026-04-07T00:00:00Z",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                    },
                    "axes": {
                        "readiness": "pass",
                        "posture": "warn",
                        "render_truth": "pass",
                        "runtime_health": "pass",
                        "closure": "skipped",
                        "evidence": "pass",
                        "governability": "pass",
                    },
                    "truth_status": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                    },
                    "drifts": [
                        {
                            "kind": "source_deploy_drift",
                            "severity": "medium",
                            "summary": "configs lag source",
                        }
                    ],
                    "exit_class": "live_but_drifted",
                    "public_safe": True,
                },
                "_meta": {
                    "selector": {
                        "presets": ["intel-full"],
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "modules": [],
                        "internal_selected": False,
                    },
                    "refs": {
                        "session_refs": [],
                        "against_ref_path": None,
                        "against_missing": False,
                    },
                },
            }
            args = self.make_args(write_latest=True, diagnostic_id="diag-anchor-reject")
            args.write_last_good_ref = True
            with patch.object(self.module, "STACK_ROOT", stack_root):
                with self.assertRaisesRegex(ValueError, "not eligible for last-good promotion"):
                    self.module.write_bundle(bundle, args)

    def test_against_last_good_ref_adds_comparison_anchor_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {"artifact_kind": "aoa.host-facts", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.machine-fit", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "platform-adaptations" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.platform-adaptation", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "diagnostics" / "latest" / "last_good.ref.json",
                {
                    "schema_version": "diagnostic_anchor_ref_v1",
                    "artifact_kind": "aoa.diagnostic.anchor-ref",
                    "anchor_class": "last_good",
                    "id": "anchor-diag-anchor",
                    "repo": "abyss-stack",
                    "captured_at": "2026-04-06T00:00:00Z",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel", "tools", "observability"],
                        "truth_goal": "live_available",
                    },
                    "diagnostic_session_id": "diag-anchor",
                    "diagnostic_session_path": "../records/diag-anchor/diagnostic_session.json",
                    "diagnostic_target_path": "../records/diag-anchor/diagnostic_target.json",
                    "exit_class": "running_as_intended",
                    "truth_status": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                    },
                    "public_safe": True,
                },
            )
            write_json(
                stack_root / "Logs" / "diagnostics" / "records" / "diag-anchor" / "diagnostic_session.json",
                {
                    "schema_version": "diagnostic_session_v1",
                    "id": "diag-anchor",
                    "repo": "abyss-stack",
                    "captured_at": "2026-04-06T00:00:00Z",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel", "tools", "observability"],
                        "truth_goal": "live_available",
                    },
                    "axes": {
                        "readiness": "pass",
                        "posture": "pass",
                        "render_truth": "pass",
                        "runtime_health": "pass",
                        "closure": "skipped",
                        "evidence": "pass",
                        "governability": "pass",
                    },
                    "truth_status": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                    },
                    "drifts": [],
                    "exit_class": "running_as_intended",
                    "public_safe": True,
                },
            )

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=self.green_autonomy(),
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(against="last-good"),
                    selector_context=self.selector_context(),
                )

        self.session_validator.validate(bundle["session"])
        self.assertEqual(
            bundle["session"]["strong_refs"]["comparison_anchor"],
            [str(stack_root / "Logs" / "diagnostics" / "latest" / "last_good.ref.json")],
        )

    def test_drifted_bundle_materializes_candidate_diagnosis_companion(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            with patch.object(self.module, "STACK_ROOT", stack_root):
                bundle = {
                    "target": {
                        "schema_version": "diagnostic_target_v1",
                        "id": "intel-full-live",
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                        "required_checks": ["doctor"],
                        "drift_watch": ["noise_envelope"],
                        "public_safe": True,
                    },
                    "session": {
                        "schema_version": "diagnostic_session_v1",
                        "id": "diag-drifted",
                        "repo": "abyss-stack",
                        "captured_at": "2026-04-07T00:00:00Z",
                        "target": {
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "truth_goal": "live_available",
                        },
                        "axes": {
                            "readiness": "warn",
                            "posture": "warn",
                            "render_truth": "pass",
                            "runtime_health": "pass",
                            "closure": "skipped",
                            "evidence": "pass",
                            "governability": "pass",
                        },
                        "truth_status": {
                            "source_authored": True,
                            "deployed": True,
                            "trial_proven": True,
                            "live_available": True,
                        },
                        "drifts": [
                            {
                                "kind": "noise_envelope",
                                "severity": "medium",
                                "summary": "host load remains noisy for latency-sensitive trials",
                                "probable_causes": ["loadavg still elevated"],
                                "owner_hint": "abyss-stack/runtime-envelope",
                                "evidence_refs": ["command:bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-doctor"],
                            }
                        ],
                        "exit_class": "live_but_drifted",
                        "public_safe": True,
                    },
                    "_meta": {
                        "selector": {
                            "presets": ["intel-full"],
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "modules": [],
                            "internal_selected": False,
                        },
                        "refs": {
                            "session_refs": [],
                            "diagnosis_refs": [],
                            "against_ref_path": None,
                            "against_missing": False,
                        },
                    },
                }
                self.module.write_bundle(
                    bundle,
                    self.make_args(write_latest=True, diagnostic_id="diag-drifted"),
                )

            companion = json.loads(
                (stack_root / "Logs" / "diagnostics" / "latest" / "diagnosis_companion.json").read_text(encoding="utf-8")
            )
            handoff = json.loads(
                (stack_root / "Logs" / "diagnostics" / "latest" / "repair_handoff.json").read_text(encoding="utf-8")
            )
            self.companion_validator.validate(companion)
            self.handoff_validator.validate(handoff)
            self.assertEqual(companion["review_status"], "candidate_review_required")
            self.assertEqual(companion["suggested_next_skill"], "aoa-session-self-diagnose")
            self.assertEqual(handoff["handoff_readiness"], "review_required")
            self.assertEqual(handoff["blocked_by"], ["reviewed_diagnosis_required"])
            self.assertTrue(handoff["diagnosis_companion_ref"].endswith("diagnosis_companion.json"))

    def test_write_reviewed_diagnosis_ref_materializes_ref_for_drifted_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            with patch.object(self.module, "STACK_ROOT", stack_root):
                bundle = {
                    "target": {
                        "schema_version": "diagnostic_target_v1",
                        "id": "intel-full-live",
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                        "required_checks": ["doctor"],
                        "drift_watch": ["noise_envelope"],
                        "public_safe": True,
                    },
                    "session": {
                        "schema_version": "diagnostic_session_v1",
                        "id": "diag-reviewed-ref",
                        "repo": "abyss-stack",
                        "captured_at": "2026-04-07T00:00:00Z",
                        "target": {
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "truth_goal": "live_available",
                        },
                        "axes": {
                            "readiness": "warn",
                            "posture": "warn",
                            "render_truth": "pass",
                            "runtime_health": "pass",
                            "closure": "skipped",
                            "evidence": "pass",
                            "governability": "pass",
                        },
                        "truth_status": {
                            "source_authored": True,
                            "deployed": True,
                            "trial_proven": True,
                            "live_available": True,
                        },
                        "drifts": [
                            {
                                "kind": "noise_envelope",
                                "severity": "medium",
                                "summary": "host load remains noisy for latency-sensitive trials",
                                "probable_causes": ["loadavg still elevated"],
                                "owner_hint": "abyss-stack/runtime-envelope",
                                "evidence_refs": ["command:bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-doctor"],
                            }
                        ],
                        "unknowns": ["No reviewed diagnosis refs were supplied for this diagnostic pass."],
                        "exit_class": "live_but_drifted",
                        "public_safe": True,
                    },
                    "_meta": {
                        "selector": {
                            "presets": ["intel-full"],
                            "preset": "intel-full",
                            "profiles": ["intel"],
                            "modules": [],
                            "internal_selected": False,
                        },
                        "refs": {
                            "session_refs": [],
                            "diagnosis_refs": [],
                            "diagnosis_ref_payloads": [],
                            "against_ref_path": None,
                            "against_missing": False,
                        },
                    },
                }
                args = self.make_args(write_latest=True, diagnostic_id="diag-reviewed-ref")
                args.write_reviewed_diagnosis_ref = True
                self.module.write_bundle(bundle, args)

            reviewed_ref = json.loads(
                (
                    stack_root / "Logs" / "diagnostics" / "latest" / "reviewed_diagnosis.ref.json"
                ).read_text(encoding="utf-8")
            )
            self.review_ref_validator.validate(reviewed_ref)
            self.assertEqual(reviewed_ref["review_verdict"], "retest_before_repair")
            self.assertEqual(reviewed_ref["reviewer"], "codex")
            self.assertTrue(reviewed_ref["source_diagnosis_companion_ref"].endswith("diagnosis_companion.json"))

    def test_write_reviewed_diagnosis_ref_rejects_green_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            bundle = {
                "target": {
                    "schema_version": "diagnostic_target_v1",
                    "id": "intel-full-live",
                    "preset": "intel-full",
                    "profiles": ["intel"],
                    "truth_goal": "live_available",
                    "required_checks": ["doctor"],
                    "drift_watch": ["source_deploy_drift"],
                    "public_safe": True,
                },
                "session": {
                    "schema_version": "diagnostic_session_v1",
                    "id": "diag-reviewed-ref-green",
                    "repo": "abyss-stack",
                    "captured_at": "2026-04-07T00:00:00Z",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "truth_goal": "live_available",
                    },
                    "axes": {
                        "readiness": "pass",
                        "posture": "pass",
                        "render_truth": "pass",
                        "runtime_health": "pass",
                        "closure": "skipped",
                        "evidence": "pass",
                        "governability": "pass",
                    },
                    "truth_status": {
                        "source_authored": True,
                        "deployed": True,
                        "trial_proven": True,
                        "live_available": True,
                    },
                    "drifts": [],
                    "exit_class": "running_as_intended",
                    "public_safe": True,
                },
                "_meta": {
                    "selector": {
                        "presets": ["intel-full"],
                        "preset": "intel-full",
                        "profiles": ["intel"],
                        "modules": [],
                        "internal_selected": False,
                    },
                    "refs": {
                        "session_refs": [],
                        "diagnosis_refs": [],
                        "diagnosis_ref_payloads": [],
                        "against_ref_path": None,
                        "against_missing": False,
                    },
                },
            }
            args = self.make_args(write_latest=True, diagnostic_id="diag-reviewed-ref-green")
            args.write_reviewed_diagnosis_ref = True
            with patch.object(self.module, "STACK_ROOT", stack_root):
                with self.assertRaisesRegex(ValueError, "not eligible for reviewed diagnosis promotion"):
                    self.module.write_bundle(bundle, args)

    def test_reviewed_diagnosis_ref_retest_blocks_repair_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            reviewed_diagnosis = stack_root / "artifacts" / "reviewed-diagnosis.ref.json"
            write_json(
                reviewed_diagnosis,
                {
                    "schema_version": "reviewed_diagnosis_ref_v1",
                    "artifact_kind": "aoa.diagnostic.reviewed-diagnosis-ref",
                    "id": "reviewed-diag-fixture",
                    "repo": "abyss-stack",
                    "reviewed_at": "2026-04-07T12:12:00Z",
                    "reviewer": "codex",
                    "source_diagnosis_companion_ref": "Logs/diagnostics/records/diag-fixture/diagnosis_companion.json",
                    "diagnostic_session_ref": "Logs/diagnostics/records/diag-fixture/diagnostic_session.json",
                    "diagnostic_session_id": "diag-fixture",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel", "tools", "observability"],
                        "truth_goal": "live_available",
                    },
                    "skill_name": "aoa-session-self-diagnose",
                    "result_kind": "diagnosis_packet_review",
                    "review_verdict": "retest_before_repair",
                    "summary": "Retest before repair.",
                    "diagnosis_types": ["noise_envelope"],
                    "symptom_refs": ["loadavg remains elevated"],
                    "probable_cause_hypotheses": ["host load is still noisy"],
                    "confidence_band": "medium",
                    "owner_hints": ["abyss-stack/runtime-envelope"],
                    "public_safe": True,
                },
            )
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {"artifact_kind": "aoa.host-facts", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.machine-fit", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "platform-adaptations" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.platform-adaptation", "captured_at": "2026-04-07T00:00:00Z"},
            )
            autonomy = self.green_autonomy()
            autonomy["status"] = "degraded"
            autonomy["payload"]["overall_status"] = "degraded"
            autonomy["degradation_reasons"] = ["route_api_surface_status_invalid"]

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=autonomy,
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(diagnosis_refs=[str(reviewed_diagnosis)]),
                    selector_context=self.selector_context(),
                )
                companion = self.module.diagnosis_companion_for(bundle)
                handoff = self.module.repair_handoff_for(bundle)

        self.companion_validator.validate(companion)
        self.handoff_validator.validate(handoff)
        self.assertEqual(companion["review_status"], "reviewed_ref_supplied")
        self.assertEqual(companion["suggested_next_skill"], "aoa-session-self-diagnose")
        self.assertEqual(handoff["handoff_readiness"], "blocked")
        self.assertEqual(handoff["blocked_by"], ["reviewed_diagnosis_requires_retest"])

    def test_invalid_reviewed_diagnosis_ref_keeps_repair_handoff_in_review_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            reviewed_diagnosis = stack_root / "artifacts" / "reviewed-diagnosis.packet.json"
            write_json(reviewed_diagnosis, {"schema_version": "reviewed-diagnosis-fixture"})
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {"artifact_kind": "aoa.host-facts", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.machine-fit", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "platform-adaptations" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.platform-adaptation", "captured_at": "2026-04-07T00:00:00Z"},
            )
            autonomy = self.green_autonomy()
            autonomy["status"] = "degraded"
            autonomy["payload"]["overall_status"] = "degraded"
            autonomy["truth_status"]["live_available"] = False
            autonomy["degradation_reasons"] = ["trial_live_gap:bounded_autonomy"]

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=autonomy,
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(diagnosis_refs=[str(reviewed_diagnosis)]),
                    selector_context=self.selector_context(),
                )
                companion = self.module.diagnosis_companion_for(bundle)
                handoff = self.module.repair_handoff_for(bundle)

        self.session_validator.validate(bundle["session"])
        self.companion_validator.validate(companion)
        self.handoff_validator.validate(handoff)
        self.assertEqual(bundle["session"]["strong_refs"]["diagnosis_packets"], [str(reviewed_diagnosis)])
        self.assertEqual(companion["review_status"], "reviewed_ref_supplied")
        self.assertEqual(companion["suggested_next_skill"], "aoa-session-self-diagnose")
        self.assertEqual(handoff["handoff_readiness"], "review_required")
        self.assertEqual(handoff["blocked_by"], ["valid_reviewed_diagnosis_required"])
        self.assertEqual(handoff["reviewed_diagnosis_refs"], [str(reviewed_diagnosis)])

    def test_reviewed_diagnosis_ref_makes_repair_handoff_ready_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stack_root = Path(tmpdir) / "stack"
            configs_root = stack_root / "Configs"
            reviewed_diagnosis = stack_root / "artifacts" / "reviewed-diagnosis.ref.json"
            write_json(
                reviewed_diagnosis,
                {
                    "schema_version": "reviewed_diagnosis_ref_v1",
                    "artifact_kind": "aoa.diagnostic.reviewed-diagnosis-ref",
                    "id": "reviewed-diag-ready",
                    "repo": "abyss-stack",
                    "reviewed_at": "2026-04-07T12:12:00Z",
                    "reviewer": "codex",
                    "source_diagnosis_companion_ref": "Logs/diagnostics/records/diag-fixture/diagnosis_companion.json",
                    "diagnostic_session_ref": "Logs/diagnostics/records/diag-fixture/diagnostic_session.json",
                    "diagnostic_session_id": "diag-fixture",
                    "target": {
                        "preset": "intel-full",
                        "profiles": ["intel", "tools", "observability"],
                        "truth_goal": "live_available",
                    },
                    "skill_name": "aoa-session-self-diagnose",
                    "result_kind": "diagnosis_packet_review",
                    "review_verdict": "ready_for_repair_handoff",
                    "summary": "Repair handoff is ready for review.",
                    "diagnosis_types": ["trial_live_gap"],
                    "symptom_refs": ["langchain-api is degraded"],
                    "probable_cause_hypotheses": ["runtime lane needs a bounded repair pass"],
                    "confidence_band": "medium",
                    "owner_hints": ["abyss-stack/runtime-envelope"],
                    "public_safe": True,
                },
            )
            write_json(
                stack_root / "Logs" / "host-facts" / "latest.private.json",
                {"artifact_kind": "aoa.host-facts", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "machine-fit" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.machine-fit", "captured_at": "2026-04-07T00:00:00Z"},
            )
            write_json(
                stack_root / "Logs" / "platform-adaptations" / "latest" / "latest.private.json",
                {"artifact_kind": "aoa.platform-adaptation", "captured_at": "2026-04-07T00:00:00Z"},
            )
            autonomy = self.green_autonomy()
            autonomy["status"] = "degraded"
            autonomy["payload"]["overall_status"] = "degraded"
            autonomy["truth_status"]["live_available"] = False
            autonomy["degradation_reasons"] = ["trial_live_gap:bounded_autonomy"]

            with patch.object(self.module, "STACK_ROOT", stack_root), patch.object(
                self.module,
                "CONFIGS_ROOT",
                configs_root,
            ), patch.object(
                self.module,
                "collect_doctor_check",
                return_value=self.green_doctor(),
            ), patch.object(
                self.module,
                "collect_render_services_check",
                return_value=self.green_render(),
            ), patch.object(
                self.module,
                "collect_autonomy_check",
                return_value=autonomy,
            ):
                bundle = self.module.collect_diagnostic_bundle(
                    self.make_args(diagnosis_refs=[str(reviewed_diagnosis)]),
                    selector_context=self.selector_context(),
                )
                handoff = self.module.repair_handoff_for(bundle)

        self.session_validator.validate(bundle["session"])
        self.handoff_validator.validate(handoff)
        self.assertEqual(bundle["session"]["strong_refs"]["diagnosis_packets"], [str(reviewed_diagnosis)])
        self.assertEqual(handoff["handoff_readiness"], "ready_for_review")
        self.assertEqual(handoff["reviewed_diagnosis_refs"], [str(reviewed_diagnosis)])


if __name__ == "__main__":
    unittest.main()
