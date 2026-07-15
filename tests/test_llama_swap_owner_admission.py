from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import shlex
import unittest
from unittest import mock

import yaml


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "config-templates" / "Services" / "llama-swap" / "owner_cold_load.py"
CONFIG_PATH = ROOT / "config-templates" / "Configs" / "llama-swap" / "gemma4-e2b.yaml"
SPEC = importlib.util.spec_from_file_location("owner_cold_load", HELPER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {HELPER_PATH}")
OWNER_COLD_LOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER_COLD_LOAD)


def reservation_args(*, wait: float = 120.0) -> argparse.Namespace:
    return argparse.Namespace(
        socket=Path("/run/user/1000/abyss-machine/resource/admission.sock"),
        owner="abyss-stack",
        workload_id="llama-swap/gemma4-e2b-it",
        activity="foreground",
        workload_class="heavy",
        kind="ai",
        latency="interactive",
        memory_demand_mib=2560.0,
        estimate_source="measured-llama-swap-cgroup-growth",
        estimate_confidence="high",
        admission_timeout=15.0,
        admission_wait=wait,
    )


class LlamaSwapOwnerAdmissionTests(unittest.TestCase):
    def test_ambiguous_transport_retry_reuses_reservation_identity(self) -> None:
        allowed = {
            "ok": True,
            "decision": "allow",
            "lease": {"id": "lease-1"},
            "policy": {"release_after_materialization": True},
        }
        with (
            mock.patch.object(
                OWNER_COLD_LOAD,
                "admission_request",
                side_effect=[OWNER_COLD_LOAD.AdmissionError("transport_TimeoutError"), allowed],
            ) as request,
            mock.patch.object(OWNER_COLD_LOAD.time, "sleep", return_value=None),
        ):
            lease_id, release_token = OWNER_COLD_LOAD.reserve(reservation_args(), lambda: False)

        self.assertEqual(lease_id, "lease-1")
        self.assertEqual(request.call_count, 2)
        first = request.call_args_list[0].args[1]["request"]
        second = request.call_args_list[1].args[1]["request"]
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertEqual(first["release_token"], second["release_token"])
        self.assertEqual(release_token, first["release_token"])

    def test_hard_denial_does_not_retry_or_start_a_load(self) -> None:
        denied = {
            "ok": False,
            "decision": "deny",
            "denied_reasons": ["runtime_reservation_state_invalid"],
        }
        with mock.patch.object(OWNER_COLD_LOAD, "admission_request", return_value=denied) as request:
            with self.assertRaisesRegex(OWNER_COLD_LOAD.AdmissionError, "runtime_reservation_state_invalid"):
                OWNER_COLD_LOAD.reserve(reservation_args(), lambda: False)

        request.assert_called_once()

    def test_malformed_reply_fails_closed_without_retry(self) -> None:
        with mock.patch.object(
            OWNER_COLD_LOAD,
            "admission_request",
            side_effect=OWNER_COLD_LOAD.AdmissionError("response_invalid"),
        ) as request:
            with self.assertRaisesRegex(OWNER_COLD_LOAD.AdmissionError, "response_invalid"):
                OWNER_COLD_LOAD.reserve(reservation_args(), lambda: False)

        request.assert_called_once()

    def test_lease_without_materialization_contract_fails_closed(self) -> None:
        allowed_without_policy = {
            "ok": True,
            "decision": "allow",
            "lease": {"id": "lease-1"},
        }
        with mock.patch.object(OWNER_COLD_LOAD, "admission_request", return_value=allowed_without_policy):
            with self.assertRaisesRegex(OWNER_COLD_LOAD.AdmissionError, "lease_policy_invalid"):
                OWNER_COLD_LOAD.reserve(reservation_args(), lambda: False)

    def test_proxy_health_budget_covers_admission_and_child_readiness(self) -> None:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        command = shlex.split(config["models"]["gemma4-e2b-it"]["cmd"])

        admission_wait = float(command[command.index("--admission-wait") + 1])
        child_health_timeout = float(command[command.index("--health-timeout") + 1])

        self.assertGreaterEqual(
            float(config["healthCheckTimeout"]),
            admission_wait + child_health_timeout + 30.0,
        )


if __name__ == "__main__":
    unittest.main()
