from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import socketserver
import stat
import subprocess
import tempfile
import threading
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ADMISSION_PATH = (
    ROOT
    / "mechanics"
    / "runtime-lifecycle"
    / "parts"
    / "user-unit"
    / "aoa_ovms_admission.py"
)
LANGCHAIN_MAIN = (
    ROOT
    / "config-templates"
    / "Services"
    / "langchain-api"
    / "app"
    / "main.py"
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EmbeddingHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request_line = self.rfile.readline().decode("ascii")
        headers: dict[str, str] = {}
        while True:
            line = self.rfile.readline().decode("ascii")
            if line in {"\r\n", "\n", ""}:
                break
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
        body = self.rfile.read(int(headers.get("content-length", "0")))
        payload = json.loads(body)
        response = json.dumps(
            {
                "data": [{"index": 0, "embedding": [0.25, -0.5]}],
                "model": payload["model"],
            }
        ).encode("utf-8")
        self.server.request_line = request_line  # type: ignore[attr-defined]
        self.wfile.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(response)}\r\nConnection: close\r\n\r\n".encode("ascii")
            + response
        )


class OvmsLifecycleTests(unittest.TestCase):
    def test_langchain_reads_ovms_key_from_configured_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "ovms_api_key.txt"
            key_path.write_text("file-owned-test-key\n", encoding="utf-8")
            with mock.patch.dict(
                os.environ,
                {"OVMS_EMBEDDINGS_API_KEY_FILE": str(key_path)},
                clear=False,
            ):
                module = load_module("langchain_main_ovms_file_key_test", LANGCHAIN_MAIN)

        self.assertEqual(module.OVMS_EMBEDDINGS_API_KEY, "file-owned-test-key")

    def test_configured_ovms_key_file_fails_closed_when_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {"OVMS_EMBEDDINGS_API_KEY_FILE": str(Path(tmp) / "missing-key")},
            clear=False,
        ):
            with self.assertRaisesRegex(RuntimeError, "configured_secret_file_unreadable"):
                load_module("langchain_main_ovms_missing_key_test", LANGCHAIN_MAIN)

    def test_unix_transport_sends_real_http_request(self) -> None:
        module = load_module("langchain_main_ovms_test", LANGCHAIN_MAIN)
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = str(Path(tmp) / "ovms.sock")
            server = socketserver.UnixStreamServer(socket_path, _EmbeddingHandler)
            thread = threading.Thread(target=server.handle_request)
            thread.start()
            try:
                result = module._unix_post_json(
                    socket_path,
                    "/v3/embeddings",
                    {"model": "embedding-model", "input": ["owner lifecycle"]},
                    2,
                    headers={"Authorization": "Bearer test-only"},
                )
            finally:
                thread.join(timeout=3)
                server.server_close()

            self.assertEqual(result["model"], "embedding-model")
            self.assertEqual(server.request_line, "POST /v3/embeddings HTTP/1.1\r\n")  # type: ignore[attr-defined]

    def test_admission_lease_is_runtime_only_and_released(self) -> None:
        module = load_module("ovms_admission_test", ADMISSION_PATH)
        reserve_payload = {
            "ok": True,
            "decision": "allow",
            "lease": {"id": "lease-test"},
            "client_capability": {"release_token": "secret-release-token"},
        }
        release_payload = {"ok": True, "decision": "released"}

        def fake_run(argv, **_kwargs):
            payload = release_payload if "release" in argv else reserve_payload
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": tmp}, clear=False
        ), mock.patch.object(module.subprocess, "run", side_effect=fake_run):
            module.reserve()
            path = module.state_path()
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text())["lease_id"], "lease-test")
            reserve_call = module.subprocess.run.call_args_list[0].args[0]
            self.assertIn("--request-id", reserve_call)
            self.assertIn("--release-token", reserve_call)

            module.release()
            self.assertFalse(path.exists())

    def test_denied_admission_never_writes_capability_state(self) -> None:
        module = load_module("ovms_admission_denied_test", ADMISSION_PATH)
        denied = {"ok": False, "decision": "force_required", "reasons": ["reserve_low"]}
        completed = subprocess.CompletedProcess([], 2, json.dumps(denied), "")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {"XDG_RUNTIME_DIR": tmp, "AOA_OVMS_ADMISSION_WAIT_SEC": "0"},
            clear=False,
        ), mock.patch.object(module.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "force_required"):
                module.reserve()
            self.assertFalse(module.state_path().exists())

    def test_retryable_admission_waits_with_one_idempotency_identity(self) -> None:
        module = load_module("ovms_admission_wait_test", ADMISSION_PATH)
        denied = {"ok": False, "decision": "force_required", "blocked_reasons": ["reserve_low"]}
        allowed = {"ok": True, "decision": "allow", "lease": {"id": "lease-after-wait"}}
        responses = [
            subprocess.CompletedProcess([], 2, json.dumps(denied), ""),
            subprocess.CompletedProcess([], 2, json.dumps(denied), ""),
            subprocess.CompletedProcess([], 0, json.dumps(allowed), ""),
        ]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ,
            {"XDG_RUNTIME_DIR": tmp, "AOA_OVMS_ADMISSION_WAIT_SEC": "5"},
            clear=False,
        ), mock.patch.object(module.subprocess, "run", side_effect=responses), mock.patch.object(
            module.time, "sleep"
        ):
            module.reserve()
            calls = [call.args[0] for call in module.subprocess.run.call_args_list]

        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(calls[1], calls[2])

    def test_release_failure_retains_capability_for_retry(self) -> None:
        module = load_module("ovms_admission_release_retry_test", ADMISSION_PATH)
        failed = {"ok": False, "decision": "deny", "denied_reasons": ["temporary"]}
        completed = subprocess.CompletedProcess([], 1, json.dumps(failed), "")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": tmp}, clear=False
        ), mock.patch.object(module.subprocess, "run", return_value=completed):
            module.write_state(
                {
                    "phase": "reserved",
                    "request_id": "request-test",
                    "lease_id": "lease-test",
                    "release_token": "release-token-long-enough-for-test",
                }
            )
            with self.assertRaisesRegex(RuntimeError, "temporary"):
                module.release()
            self.assertTrue(module.state_path().exists())

    def test_pending_state_is_replayed_then_released(self) -> None:
        module = load_module("ovms_admission_pending_replay_test", ADMISSION_PATH)
        reserve_payload = {"ok": True, "decision": "allow", "lease": {"id": "lease-recovered"}}
        release_payload = {"ok": True, "decision": "allow", "released": True}

        def fake_run(argv, **_kwargs):
            payload = release_payload if "release" in argv else reserve_payload
            return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": tmp}, clear=False
        ), mock.patch.object(module.subprocess, "run", side_effect=fake_run):
            module.write_state(
                {
                    "phase": "pending",
                    "request_id": "request-recover",
                    "release_token": "release-token-long-enough-for-replay",
                }
            )
            module.release()
            self.assertFalse(module.state_path().exists())
            self.assertEqual(module.subprocess.run.call_count, 2)

    def test_malformed_state_is_preserved_fail_closed(self) -> None:
        module = load_module("ovms_admission_malformed_test", ADMISSION_PATH)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {"XDG_RUNTIME_DIR": tmp}, clear=False
        ):
            path = module.state_path()
            path.parent.mkdir(parents=True)
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "retained"):
                module.reserve()
            self.assertEqual(path.read_text(encoding="utf-8"), "not-json\n")


if __name__ == "__main__":
    unittest.main()
