from __future__ import annotations

import base64
from io import BytesIO
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest
from unittest import mock
from pathlib import Path

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = REPO_ROOT / "mechanics" / "runtime-lifecycle" / "parts" / "live-code-intelligence"
sys.path.insert(0, str(PART_ROOT))

import live_code_intelligence  # noqa: E402

from live_code_intelligence import (  # noqa: E402
    MACHINE_EVIDENCE_SCHEMA,
    MACHINE_GATE_SCHEMA,
    MACHINE_CONSUMER_ABI,
    PROVIDER_QUEUE_CAPACITY,
    LiveCodeIntelligenceConfig,
    LiveCodeIntelligenceError,
    LiveCodeIntelligenceRuntime,
    ManagedLspSession,
    _digest_bytes,
    _ed25519_verify,
    _digest_payload,
    _validate_machine_evidence_payload,
    machine_evidence_digest,
    machine_evidence_bundle_digest,
    machine_evidence_gate_digest,
)


class LiveCodeIntelligenceRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "source"
        self.state = self.root / "runtime-state"
        self.source.mkdir()
        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        self.config = LiveCodeIntelligenceConfig.from_file(
            config_path,
            source_root=self.source,
            state_root=self.state,
        )
        self.runtime = LiveCodeIntelligenceRuntime(self.config)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_source(self, relative: str, text: str) -> None:
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def machine_evidence(
        self,
        *,
        artifact_digest: str | None = None,
        fresh_health: bool = False,
    ) -> dict:
        artifact_digest = artifact_digest or ("sha256:" + ("a" * 64))
        runtime_manifest: list[dict[str, str]] = []
        for candidate in sorted(self.root.rglob("*")):
            if not candidate.is_file():
                continue
            if _digest_bytes(candidate.read_bytes()) != artifact_digest:
                continue
            runtime_manifest = [
                {"path": path, "digest": digest}
                for path, digest in live_code_intelligence._directory_file_manifest(
                    candidate.parent,
                    "test LSP runtime root",
                )
            ]
            break
        source_manifest = [
            {"path": path, "digest": digest}
            for path, digest in live_code_intelligence._directory_file_manifest(
                self.source,
                "test LSP source root",
            )
        ]
        observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not fresh_health:
            observed_at = "2026-08-25T00:00:00Z"
        health_observed_at = observed_at
        if not fresh_health:
            health_observed_at = "2026-08-25T00:00:01Z"
        payload = {
            "schema_version": MACHINE_EVIDENCE_SCHEMA,
            "evidence_class": "machine-owned-verification",
            "issuer": "abyss-machine",
            "receipt_id": "machine-receipt:live-code-intelligence:fixture",
            "observed_at": "2026-08-25T00:00:00Z",
            "subject": {
                "provider": self.config.provider_identity,
                "provider_source_digest": self.config.provider_source_digest,
                "config_digest": self.config.config_digest,
                "artifact_digest": artifact_digest,
                "artifact_ref": "artifact://machine/live-code-intelligence",
            },
            "installation": {
                "owner": "abyss-machine",
                "state": "verified",
                "identity": "installation://machine/live-code-intelligence",
                "artifact_digest": artifact_digest,
                "evidence_ref": "receipt://machine/installation",
            },
            "admission": {
                "owner": "abyss-machine",
                "state": "admitted",
                "trust_state": "trusted",
                "admission_ref": "receipt://machine/admission",
            },
            "health": {
                "owner": "abyss-machine",
                "state": "healthy",
                "measurement_ref": "receipt://machine/health",
                "observed_at": health_observed_at,
            },
            "verification": {
                "owner": "abyss-machine",
                "state": "verified",
                "method": "abyss-machine-owner-receipt-v1",
                "verification_ref": "receipt://machine/verification",
            },
            "providers": [
                {
                    "id": self.config.provider_id,
                    "version": self.config.provider_version,
                    "language": "python",
                    "protocol": self.config.provider_protocol,
                    "observation_state": "available",
                },
                {
                    "id": "typescript-lsp",
                    "version": "1.0.0",
                    "language": "typescript",
                    "protocol": "lsp",
                    "observation_state": "observed",
                },
            ],
            "lsp_sessions": [
                {
                    "session_id": "lsp-session:typescript:fixture",
                    "provider_id": "typescript-lsp",
                    "language": "typescript",
                    "state": "observed" if runtime_manifest else "unobserved",
                    "transport": "stdio",
                    "source_epoch": "sha256:" + ("b" * 64),
                    "evidence_ref": "receipt://machine/lsp-session",
                    "source_root": str(self.source),
                    "artifact_digest": artifact_digest,
                    "interpreter_digest": _digest_bytes(
                        Path(sys.executable).read_bytes()
                    ),
                    "runtime_manifest": runtime_manifest,
                    "source_manifest": source_manifest,
                }
            ],
            "observations": [
                {
                    "provider_id": "typescript-lsp",
                    "language": "typescript",
                    "state": "observed",
                    "source_epoch": "sha256:" + ("b" * 64),
                    "observation_ref": "receipt://machine/typescript-observation",
                    "semantic_owner": "aoa-kag",
                }
            ],
            "lifecycle": {
                "state": "ready",
                "restart": {
                    "state": "observed",
                    "evidence_ref": "receipt://machine/restart",
                },
                "last_good": {
                    "state": "available",
                    "evidence_ref": "receipt://machine/last-good",
                },
                "canary": {
                    "state": "passed",
                    "evidence_ref": "receipt://machine/canary",
                },
                "rollback": {
                    "state": "ready",
                    "evidence_ref": "receipt://machine/rollback",
                },
            },
            "owner_boundaries": dict(self.config.owner_boundaries),
            "claim_limits": [
                "machine receipt is not proof or owner acceptance",
                "source observation meaning remains aoa-kag-owned",
            ],
        }
        payload["receipt_digest"] = machine_evidence_digest(payload)
        return payload

    def admitted_config(self, evidence: dict) -> LiveCodeIntelligenceConfig:
        evidence_path = self.root / "machine-evidence-gate.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        with mock.patch(
            "live_code_intelligence._validate_machine_evidence_gate_bundle",
            return_value=evidence,
        ):
            config = LiveCodeIntelligenceConfig.from_file(
                PART_ROOT / "config" / "python-ast-live-provider.json",
                source_root=self.source,
                state_root=self.state,
                machine_evidence_path=evidence_path,
                launch_scratch_root=self.root / "lsp-scratch",
            )
        return config

    def test_initial_refresh_emits_provider_neutral_live_handles(self) -> None:
        self.write_source(
            "pkg/provider.py",
            "def helper(value):\n    return value + 1\n",
        )
        self.write_source(
            "pkg/consumer.py",
            "from pkg.provider import helper\n\ndef run(value):\n    return helper(value)\n",
        )

        state = self.runtime.refresh()

        self.assertEqual(state["status"], "current")
        self.assertEqual(state["machine_consumer_abi"], MACHINE_CONSUMER_ABI)
        self.assertEqual(
            state["machine_consumer_abi"]["trust_anchor_posture"],
            "existing_root_owned_anchor_only",
        )
        self.assertEqual(
            state["observation_envelope"]["schema_version"],
            "abyss-stack-machine-bound-code-observation-v1",
        )
        machine_binding = state["machine_binding"]
        self.assertEqual(machine_binding["owner"], "abyss-machine")
        self.assertEqual(
            machine_binding["artifact_subject"]["admission_state"], "unknown"
        )
        self.assertEqual(machine_binding["live_measurement"]["state"], "unobserved")
        self.assertTrue(
            machine_binding["artifact_subject"]["subject_digest"].startswith("sha256:")
        )
        self.assertEqual(
            machine_binding["resource_envelope"]["max_file_bytes"],
            self.config.max_file_bytes,
        )
        expected_provider = self.config.provider_identity
        self.assertEqual(state["provider"], expected_provider)
        self.assertEqual(
            state["observation_envelope"]["provider"], expected_provider
        )
        expected_observation_provider = {
            "id": expected_provider["id"],
            "version": expected_provider["version"],
            "language": expected_provider["language"],
        }
        self.assertTrue(
            all(
                record["observation"]["provider"] == expected_observation_provider
                for record in state["files"].values()
                if record["observation"] is not None
            )
        )
        self.assertTrue(state["source"]["source_epoch"].startswith("sha256:"))
        self.assertEqual(state["invalidation"]["full_rebuild"], True)

        self.assertEqual(state["summary"]["source_file_count"], 2)
        self.assertGreaterEqual(state["summary"]["symbol_count"], 4)
        self.assertTrue(self.runtime.current_path.is_file())
        self.assertFalse(self.runtime.candidate_path.exists())

        definition = self.runtime.definitions("run")
        self.assertEqual(definition["status"], "ok")
        self.assertEqual(definition["freshness"], "current")
        self.assertEqual(definition["results"][0]["name"], "run")
        self.assertTrue(definition["results"][0]["handle"].startswith("python://"))

        references = self.runtime.references("helper")
        self.assertEqual(references["status"], "ok")
        self.assertGreaterEqual(len(references["results"]), 2)
        self.assertEqual(
            self.runtime.discover()["owner_boundaries"]["observation_meaning"],
            "aoa-kag",
        )
        receipt = self.state / "receipts" / (
            state["source"]["source_epoch"].removeprefix("sha256:") + ".json"
        )
        self.assertTrue(receipt.is_file())

    def test_managed_lsp_session_requires_admission_and_survives_restart(self) -> None:
        runtime_root = self.root / "machine-runtime"
        server = runtime_root / "fake-lsp"
        server.parent.mkdir(parents=True)
        server.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "def read():\n"
            "    headers = {}\n"
            "    while True:\n"
            "        line = sys.stdin.buffer.readline()\n"
            "        if line in (b'\\r\\n', b'\\n'): break\n"
            "        if not line: return None\n"
            "        key, value = line.decode().split(':', 1); headers[key.lower()] = value.strip()\n"
            "    return json.loads(sys.stdin.buffer.read(int(headers['content-length'])))\n"
            "def send(value):\n"
            "    body = json.dumps(value, separators=(',', ':')).encode()\n"
            "    sys.stdout.buffer.write(f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode() + body); sys.stdout.buffer.flush()\n"
            "while True:\n"
            "    message = read()\n"
            "    if message is None: break\n"
            "    if 'method' not in message: continue\n"
            "    if message.get('method') == 'initialize':\n"
            "        send({'jsonrpc':'2.0','id':message['id'],'method':'workspace/configuration','params':{}})\n"
            "        for index in range(150): send({'jsonrpc':'2.0','method':'window/logMessage','params':{'message':str(index)}})\n"
            "        send({'jsonrpc':'2.0','id':message['id'],'result':{'capabilities': {}}})\n"
            "    elif 'id' in message:\n"
            "        send({'jsonrpc':'2.0','id':message['id'],'result':[]})\n"
            "    if message.get('method') == 'exit': break\n",
            encoding="utf-8",
        )
        server.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        admitted_config = self.admitted_config(evidence)
        session = ManagedLspSession(
            [str(server)], provider_id="typescript-lsp", language="typescript",
            source_epoch="sha256:" + ("b" * 64), admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        try:
            session.start(root_uri=self.source.as_uri())
            response = session.document_symbols(uri=(self.source / "demo.ts").as_uri())
            self.assertEqual([], response["result"])
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "inside the admitted source root"):
                session.document_symbols(uri=(self.root / "outside.ts").as_uri())
            self.assertEqual("observed", session.snapshot()["state"])
            self.assertLessEqual(session._responses.qsize(), PROVIDER_QUEUE_CAPACITY)
            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(
                    pool.map(
                        lambda index: session.document_symbols(
                            uri=(self.source / f"demo-{index}.ts").as_uri()
                        ),
                        range(16),
                    )
                )
            self.assertEqual(len({item["id"] for item in responses}), 16)
            session.restart(root_uri=self.source.as_uri())
            self.assertEqual(1, session.snapshot()["restart_count"])
            self.assertEqual("observed", session.snapshot()["state"])
        finally:
            session.close()

        plain_config = LiveCodeIntelligenceConfig.from_file(
            PART_ROOT / "config" / "python-ast-live-provider.json",
            source_root=self.source,
            state_root=self.state,
        )
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "owner-authenticated"):
            ManagedLspSession(
                [str(server)], provider_id="typescript-lsp", language="typescript",
                source_epoch="epoch", admission_config=plain_config,
                runtime_root=runtime_root,
            )
        forged_config = plain_config
        object.__setattr__(forged_config, "machine_evidence", evidence)
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "evidence returned"):
            ManagedLspSession(
                [str(server)], provider_id="typescript-lsp", language="typescript",
                source_epoch="sha256:" + ("b" * 64), admission_config=forged_config,
                runtime_root=runtime_root,
            )

    def test_delta_reuses_unchanged_files_and_invalidates_importers(self) -> None:
        self.write_source("provider.py", "def helper(value):\n    return value + 1\n")
        self.write_source(
            "consumer.py",
            "from provider import helper\n\ndef run(value):\n    return helper(value)\n",
        )
        self.write_source("unrelated.py", "VALUE = 3\n")
        first = self.runtime.refresh()

        self.write_source("provider.py", "def helper(value):\n    return value + 2\n")
        second = self.runtime.refresh()

        invalidation = second["invalidation"]
        self.assertFalse(invalidation["full_rebuild"])
        self.assertEqual(invalidation["changed_paths"], ["provider.py"])
        self.assertEqual(invalidation["dependency_impacted_paths"], ["consumer.py"])
        self.assertEqual(
            set(invalidation["invalidated_paths"]),
            {"provider.py", "consumer.py"},
        )
        self.assertIn("unrelated.py", invalidation["reused_paths"])
        self.assertEqual(second["status"], "current")
        self.assertNotEqual(
            first["source"]["source_epoch"], second["source"]["source_epoch"]
        )
        self.assertEqual(second["provenance"]["full_rebuild"], False)

    def test_lsp_start_failure_and_reader_eof_are_immediately_observable(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()

        exits = runtime_root / "exit-lsp"
        exits.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        exits.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(exits.read_bytes()),
            fresh_health=True,
        )
        admitted_config = self.admitted_config(evidence)
        failed = ManagedLspSession(
            [str(exits)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
            request_timeout=1,
        )
        with self.assertRaises(LiveCodeIntelligenceError):
            failed.start(root_uri=self.source.as_uri())
        self.assertIsNone(failed._process)

        eof_server = runtime_root / "eof-lsp"
        eof_server.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "def read():\n"
            "    headers = {}\n"
            "    while True:\n"
            "        line = sys.stdin.buffer.readline()\n"
            "        if line in (b'\\r\\n', b'\\n'): break\n"
            "        if not line: return None\n"
            "        key, value = line.decode().split(':', 1); headers[key.lower()] = value.strip()\n"
            "    return json.loads(sys.stdin.buffer.read(int(headers['content-length'])))\n"
            "def send(value):\n"
            "    body = json.dumps(value, separators=(',', ':')).encode()\n"
            "    sys.stdout.buffer.write(f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode() + body); sys.stdout.buffer.flush()\n"
            "message = read(); send({'jsonrpc':'2.0','id':message['id'],'result':{'capabilities':{}}})\n"
            "read()\n",
            encoding="utf-8",
        )
        eof_server.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(eof_server.read_bytes()),
            fresh_health=True,
        )
        admitted_config = self.admitted_config(evidence)
        session = ManagedLspSession(
            [str(eof_server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
            request_timeout=5,
        )
        try:
            session.start(root_uri=self.source.as_uri())
            started = time.monotonic()
            with self.assertRaises(LiveCodeIntelligenceError):
                session.document_symbols(uri=(self.source / "gone.ts").as_uri())
            self.assertLess(time.monotonic() - started, 2)
            self.assertEqual(session.snapshot()["state"], "degraded")
        finally:
            session.close()

    def test_lsp_launch_binds_artifact_command_and_source_root(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        other_lsp = runtime_root / "other-lsp"
        other_lsp.write_text(
            f"#!{sys.executable}\n# unadmitted\n", encoding="utf-8"
        )
        other_lsp.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        admitted_config = self.admitted_config(evidence)

        with self.assertRaisesRegex(LiveCodeIntelligenceError, "admitted artifact"):
            ManagedLspSession(
                [str(other_lsp)],
                provider_id="typescript-lsp",
                language="typescript",
                source_epoch="sha256:" + ("b" * 64),
                admission_config=admitted_config,
                runtime_root=runtime_root,
            )

        with self.assertRaisesRegex(LiveCodeIntelligenceError, "command arguments"):
            ManagedLspSession(
                [str(server), "--stdio"],
                provider_id="typescript-lsp",
                language="typescript",
                source_epoch="sha256:" + ("b" * 64),
                admission_config=admitted_config,
                runtime_root=runtime_root,
            )

        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        other_source = self.root / "other-source"
        other_source.mkdir()
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "admitted source root"):
            session.start(root_uri=other_source.as_uri())

    def test_lsp_launch_rejects_changed_runtime_dependency_manifest(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        dependency = runtime_root / "dependency.py"
        dependency.write_text("VALUE = 1\n", encoding="utf-8")
        server = runtime_root / "fake-lsp"
        server.write_text(
            f"#!{sys.executable}\nimport dependency\n",
            encoding="utf-8",
        )
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        dependency.write_text("VALUE = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "runtime dependency manifest",
        ):
            session.start(root_uri=self.source.as_uri())

    def test_lsp_launch_rejects_changed_source_manifest(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )

        self.write_source("module.py", "VALUE = 2\n")
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "source epoch manifest",
        ):
            session.start(root_uri=self.source.as_uri())

    def test_generic_lsp_request_rejects_out_of_root_uri(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )

        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "request URI must remain inside",
        ):
            session.request(
                "textDocument/documentSymbol",
                {"textDocument": {"uri": (self.root / "outside.ts").as_uri()}},
            )
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "request URI must remain inside",
        ):
            session.request(
                "workspace/executeCommand",
                {"arguments": [{"value": (self.root / "outside.ts").as_uri()}]},
            )

    def test_lsp_launch_binds_working_directory_and_interpreter(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout = BytesIO()
        with (
            mock.patch(
                "live_code_intelligence.subprocess.Popen",
                return_value=process,
            ) as popen,
            mock.patch.object(session, "request", return_value={"result": {}}),
            mock.patch.object(session, "notify"),
        ):
            session.start(root_uri=self.source.as_uri())
            self.assertEqual(
                popen.call_args.kwargs["cwd"],
                popen.call_args.kwargs["env"]["PYTHONPATH"],
            )
            self.assertNotEqual(str(runtime_root.resolve()), popen.call_args.kwargs["cwd"])
            self.assertTrue(Path(popen.call_args.kwargs["cwd"]).is_dir())
            self.assertEqual(
                self.root / "lsp-scratch",
                Path(popen.call_args.kwargs["cwd"]).parent,
            )
            launch_command = tuple(popen.call_args.args[0])
            self.assertEqual(
                ManagedLspSession._launch_namespace_binary(),
                launch_command[0],
            )
            self.assertIn("--ro-bind-data", launch_command)
            inner_command = launch_command[launch_command.index("--") + 1 :]
            self.assertTrue(inner_command[0].startswith("/proc/self/fd/"))
            self.assertEqual("-S", inner_command[1])
            self.assertTrue(inner_command[2].startswith("/proc/self/fd/"))
            self.assertEqual(
                {
                    int(item.rsplit("/", 1)[-1])
                    for item in inner_command
                    if item.startswith("/proc/self/fd/")
                },
                set(popen.call_args.kwargs["pass_fds"]).intersection(
                    {
                        int(item.rsplit("/", 1)[-1])
                        for item in inner_command
                        if item.startswith("/proc/self/fd/")
                    }
                ),
            )
            self.assertEqual(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PATH": os.defpath,
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": popen.call_args.kwargs["cwd"],
                },
                popen.call_args.kwargs["env"],
            )
        if session._reader is not None:
            session._reader.join(timeout=2)
        session._process = None
        session._cleanup_launch_snapshot()

    def test_lsp_namespace_launcher_ignores_caller_path(self) -> None:
        attacker = self.root / "bwrap"
        attacker.write_text("#!/bin/sh\n", encoding="utf-8")
        attacker.chmod(0o755)
        with mock.patch(
            "live_code_intelligence.shutil.which",
            return_value=str(attacker),
        ):
            self.assertEqual(
                str(live_code_intelligence.MACHINE_BUBBLEWRAP_PATH),
                ManagedLspSession._launch_namespace_binary(),
            )

        attacker.chmod(0o777)
        with mock.patch.object(
            live_code_intelligence,
            "MACHINE_BUBBLEWRAP_PATH",
            attacker,
        ):
            with self.assertRaisesRegex(
                LiveCodeIntelligenceError,
                "root-owned and not writable",
            ):
                ManagedLspSession._launch_namespace_binary()

    def test_lsp_reader_replies_to_string_server_requests(self) -> None:
        session = object.__new__(ManagedLspSession)
        process = mock.Mock()
        process.poll.return_value = None
        session._process = process
        session._closing = False
        session._pending = {}
        session._pending_lock = threading.Lock()
        session._last_error = None
        session._read_message = mock.Mock(
            side_effect=[
                {
                    "jsonrpc": "2.0",
                    "id": "server-request-1",
                    "method": "workspace/configuration",
                    "params": {},
                },
                None,
            ]
        )
        session._send = mock.Mock()
        session._reader_loop()

        session._send.assert_called_once_with(
            {
                "jsonrpc": "2.0",
                "id": "server-request-1",
                "error": {
                    "code": -32601,
                    "message": "server-to-client requests are unsupported",
                },
            }
        )

    @unittest.skipUnless(
        ManagedLspSession._can_use_immutable_launch_fds(),
        "sealed launch descriptors are Linux-only",
    )
    def test_lsp_launch_uses_immutable_artifact_and_runtime_snapshot(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        dependency = runtime_root / "dependency.py"
        dependency.write_text("VALUE = 'admitted'\n", encoding="utf-8")
        config = runtime_root / "config.json"
        config.write_text("admitted\n", encoding="utf-8")
        nested_runtime_file = runtime_root / "nested" / "dependency.json"
        nested_runtime_file.parent.mkdir()
        nested_runtime_file.write_text("nested\n", encoding="utf-8")
        server = runtime_root / "fake-lsp"
        original_script = (
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "from pathlib import Path\n"
            "from dependency import VALUE\n"
            "CONFIG = Path(sys.argv[1].split('=', 1)[1]).read_text().strip()\n"
            "def read():\n"
            "    headers = {}\n"
            "    while True:\n"
            "        line = sys.stdin.buffer.readline()\n"
            "        if line in (b'\\r\\n', b'\\n'): break\n"
            "        if not line: return None\n"
            "        key, value = line.decode().split(':', 1); headers[key.lower()] = value.strip()\n"
            "    return json.loads(sys.stdin.buffer.read(int(headers['content-length'])))\n"
            "def send(value):\n"
            "    body = json.dumps(value, separators=(',', ':')).encode()\n"
            "    sys.stdout.buffer.write(f'Content-Length: {len(body)}\\r\\n\\r\\n'.encode() + body); sys.stdout.buffer.flush()\n"
            "while True:\n"
            "    message = read()\n"
            "    if message is None: break\n"
            "    if message.get('method') == 'initialize':\n"
            "        try:\n"
            "            Path(sys.argv[1].split('=', 1)[1]).write_text('attacker')\n"
            "        except OSError:\n"
            "            write_state = 'readonly'\n"
            "        else:\n"
            "            write_state = 'mutable'\n"
            "        send({'jsonrpc':'2.0','id':message['id'],'result':{'capabilities':{'marker':f'{VALUE}:{CONFIG}:{write_state}'}}})\n"
            "    elif message.get('method') == 'shutdown':\n"
            "        send({'jsonrpc':'2.0','id':message['id'],'result':None})\n"
            "    elif message.get('method') == 'exit':\n"
            "        break\n"
        )
        attacker_script = original_script.replace("'admitted'", "'attacker'")
        server.write_text(original_script, encoding="utf-8")
        server.chmod(0o755)
        command = [str(server), f"--config={config}"]
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        evidence["lsp_sessions"][0]["command_digest"] = _digest_payload(command)
        evidence["receipt_digest"] = machine_evidence_digest(evidence)
        admitted_config = self.admitted_config(
            evidence
        )
        session = ManagedLspSession(
            command,
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        real_popen = subprocess.Popen
        launch = {}

        def replace_after_binding(command, **kwargs):
            launch["command"] = tuple(command)
            launch["pass_fds"] = tuple(kwargs["pass_fds"])
            # This replacement occurs after _prepare_launch_binding has made
            # the sealed executable/interpreter images and runtime snapshot.
            server.write_text(attacker_script, encoding="utf-8")
            dependency.write_text("VALUE = 'attacker'\n", encoding="utf-8")
            config.write_text("attacker\n", encoding="utf-8")
            return real_popen(command, **kwargs)

        try:
            with mock.patch(
                "live_code_intelligence.subprocess.Popen",
                side_effect=replace_after_binding,
            ):
                response = session.start(root_uri=self.source.as_uri())
            self.assertEqual(
                "admitted:admitted:readonly",
                response["result"]["capabilities"]["marker"],
            )
            self.assertEqual(
                ManagedLspSession._launch_namespace_binary(),
                launch["command"][0],
            )
            inner_command = launch["command"][launch["command"].index("--") + 1 :]
            self.assertTrue(inner_command[0].startswith("/proc/self/fd/"))
            self.assertTrue(inner_command[2].startswith("/proc/self/fd/"))
            self.assertGreaterEqual(len(launch["pass_fds"]), 2)
            self.assertIn(
                "--config=",
                launch["command"][-1],
            )
            self.assertIn(str(self.root / "lsp-scratch"), launch["command"][-1])
        finally:
            session.close()

    @unittest.skipUnless(
        ManagedLspSession._can_use_immutable_launch_fds(),
        "sealed launch descriptors are Linux-only",
    )
    def test_lsp_launch_rejects_external_embedded_runtime_path(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        external = self.root / "outside-config.json"
        command = [str(server), f"--config={external}"]
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        evidence["lsp_sessions"][0]["command_digest"] = _digest_payload(command)
        evidence["receipt_digest"] = machine_evidence_digest(evidence)
        admitted_config = self.admitted_config(evidence)
        session = ManagedLspSession(
            command,
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )

        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "path dependency must remain inside",
        ):
            session.start(root_uri=self.source.as_uri())
        self.assertIsNone(session._launch_snapshot_root)

    @unittest.skipUnless(
        ManagedLspSession._can_use_immutable_launch_fds(),
        "sealed launch descriptors are Linux-only",
    )
    def test_lsp_launch_rejects_relative_path_outside_snapshot(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        outside = self.root / "outside-config.json"
        outside.write_text("outside\n", encoding="utf-8")
        command = [str(server), "../outside-config.json"]
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        evidence["lsp_sessions"][0]["command_digest"] = _digest_payload(command)
        evidence["receipt_digest"] = machine_evidence_digest(evidence)
        admitted_config = self.admitted_config(evidence)
        session = ManagedLspSession(
            command,
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )

        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "path dependency must remain inside",
        ):
            session.start(root_uri=self.source.as_uri())
        self.assertIsNone(session._launch_snapshot_root)

    def test_lsp_start_retires_dead_generation_before_relaunch(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        old_snapshot = self.root / "lsp-scratch" / "old-generation"
        old_snapshot.mkdir(parents=True)
        old_file = old_snapshot / "dependency.py"
        old_file.write_text("VALUE = 1\n", encoding="utf-8")
        old_process = mock.Mock()
        old_process.poll.return_value = 1
        old_process.stdin = BytesIO()
        old_process.stdout = BytesIO()
        session._process = old_process
        session._launch_snapshot_root = old_snapshot
        session._last_good_at = "old-generation"
        replacement = mock.Mock()
        replacement.poll.return_value = None
        replacement.stdin = BytesIO()
        replacement.stdout = BytesIO()

        def initialize(*args: object, **kwargs: object) -> dict[str, object]:
            del args, kwargs
            self.assertEqual("starting", session.snapshot()["state"])
            return {"result": {}}

        with (
            mock.patch(
                "live_code_intelligence.subprocess.Popen",
                return_value=replacement,
            ),
            mock.patch.object(session, "request", side_effect=initialize),
            mock.patch.object(session, "notify"),
        ):
            session.start(root_uri=self.source.as_uri())

        self.assertFalse(old_snapshot.exists())
        self.assertTrue(old_process.stdin.closed)
        self.assertTrue(old_process.stdout.closed)
        self.assertEqual("observed", session.snapshot()["state"])
        session._process = None
        session._cleanup_launch_snapshot()

    def test_lsp_launch_fails_closed_without_owner_scratch_root(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        object.__setattr__(admitted_config, "launch_scratch_root", None)
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "launch scratch root is required",
        ):
            session.start(root_uri=self.source.as_uri())
        self.assertIsNone(session._launch_snapshot_root)

    def test_lsp_script_interpreter_digest_is_admitted(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        evidence["lsp_sessions"][0]["interpreter_digest"] = "sha256:" + ("c" * 64)
        admitted_config = self.admitted_config(evidence)

        with self.assertRaisesRegex(LiveCodeIntelligenceError, "script interpreter"):
            ManagedLspSession(
                [str(server)],
                provider_id="typescript-lsp",
                language="typescript",
                source_epoch="sha256:" + ("b" * 64),
                admission_config=admitted_config,
                runtime_root=runtime_root,
            )

    def test_lsp_open_document_rejects_unbound_buffer(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        document = self.source / "demo.ts"
        document.write_text("const value = 1;\n", encoding="utf-8")
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "admitted source epoch"):
            session.open_document(uri=document.as_uri(), text="const value = 2;\n")
        document.write_text("const value = 2;\n", encoding="utf-8")
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "source epoch manifest",
        ):
            session.open_document(uri=document.as_uri(), text="const value = 2;\n")
        document.write_text("const value = 1;\n", encoding="utf-8")
        with mock.patch.object(session, "notify") as notify:
            session.open_document(uri=document.as_uri(), text="const value = 1;\n")
            notify.assert_called_once()

    @unittest.skipUnless(os.name == "posix", "descriptor-relative opens are POSIX-only")
    def test_source_metadata_rejects_parent_symlink(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
        link = self.source / "linked"
        link.symlink_to(outside, target_is_directory=True)

        self.assertIsNone(
            LiveCodeIntelligenceRuntime._read_source_metadata(
                link / "module.py",
                self.source,
                self.config.max_file_bytes,
            )
        )

    @unittest.skipUnless(os.name == "posix", "FIFO open flags are POSIX-only")
    def test_source_scan_rejects_fifo_without_blocking(self) -> None:
        os.mkfifo(self.source / "blocked.py")

        started = time.monotonic()
        state = self.runtime.refresh()

        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(state["status"], "current")
        self.assertEqual(state["summary"]["source_file_count"], 0)
        self.assertFalse(self.runtime.candidate_path.exists())

    def test_concurrent_lsp_starts_launch_one_process(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        admitted_config = self.admitted_config(
            self.machine_evidence(
                artifact_digest=_digest_bytes(server.read_bytes()),
                fresh_health=True,
            )
        )
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        process = mock.Mock()
        process.poll.return_value = None
        process.stdout = BytesIO()
        with (
            mock.patch(
                "live_code_intelligence.subprocess.Popen",
                return_value=process,
            ) as popen,
            mock.patch.object(session, "request", return_value={"result": {}}),
            mock.patch.object(session, "notify"),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            results = list(
                pool.map(
                    lambda _: session.start(root_uri=self.source.as_uri()),
                    range(2),
                )
            )
        self.assertEqual(1, popen.call_count)
        self.assertEqual(2, len(results))
        if session._reader is not None:
            session._reader.join(timeout=2)
        session._process = None
        session._cleanup_launch_snapshot()

    def test_state_readers_hold_refresh_lock_for_complete_snapshot(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        self.runtime.refresh()
        reader_entered = threading.Event()
        release_reader = threading.Event()
        scan_entered = threading.Event()
        original_read_json = live_code_intelligence._read_json
        original_scan = self.runtime._scan

        def blocking_read(path: Path) -> dict:
            if path == self.runtime.current_path:
                reader_entered.set()
                release_reader.wait(timeout=3)
            return original_read_json(path)

        def observed_scan() -> dict:
            scan_entered.set()
            return original_scan()

        with (
            mock.patch("live_code_intelligence._read_json", side_effect=blocking_read),
            mock.patch.object(self.runtime, "_scan", side_effect=observed_scan),
        ):
            reader = threading.Thread(target=self.runtime.status)
            reader.start()
            self.assertTrue(reader_entered.wait(timeout=3))
            refresher = threading.Thread(target=self.runtime.refresh)
            refresher.start()
            self.assertFalse(scan_entered.wait(timeout=0.2))
            release_reader.set()
            reader.join(timeout=3)
            refresher.join(timeout=3)
        self.assertFalse(reader.is_alive())
        self.assertFalse(refresher.is_alive())
        self.assertTrue(scan_entered.is_set())

    def test_managed_lsp_session_rejects_non_stdio_transport(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        evidence["lsp_sessions"][0]["transport"] = "tcp"
        admitted_config = self.admitted_config(evidence)

        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "admitted provider and source epoch",
        ):
            ManagedLspSession(
                [str(server)],
                provider_id="typescript-lsp",
                language="typescript",
                source_epoch="sha256:" + ("b" * 64),
                admission_config=admitted_config,
                runtime_root=runtime_root,
            )

    def test_observed_lsp_sessions_require_source_root_in_schema_and_validator(self) -> None:
        evidence = self.machine_evidence(fresh_health=True)
        session = evidence["lsp_sessions"][0]
        session["state"] = "observed"
        session["runtime_manifest"] = [
            {"path": "provider", "digest": "sha256:" + ("a" * 64)}
        ]
        session.pop("source_root")
        evidence["receipt_digest"] = machine_evidence_digest(evidence)

        schema = json.loads(
            (
                PART_ROOT
                / "config"
                / "schemas"
                / "machine-code-intelligence-evidence.schema.json"
            ).read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(evidence))
        self.assertTrue(
            any(
                tuple(error.path) == ("lsp_sessions", 0)
                and "source_root" in error.message
                for error in errors
            )
        )
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "source_root is required for observed",
        ):
            _validate_machine_evidence_payload(
                evidence,
                expected_provider=self.config.provider_identity,
                expected_provider_source_digest=self.config.provider_source_digest,
                expected_config_digest=self.config.config_digest,
            )

        session["source_root"] = str(self.source)
        session["runtime_manifest"] = []
        evidence["receipt_digest"] = machine_evidence_digest(evidence)
        errors = list(Draft202012Validator(schema).iter_errors(evidence))
        self.assertTrue(
            any(
                tuple(error.path) == ("lsp_sessions", 0, "runtime_manifest")
                and error.validator == "minItems"
                for error in errors
            )
        )
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError,
            "runtime_manifest must be a non-empty array",
        ):
            _validate_machine_evidence_payload(
                evidence,
                expected_provider=self.config.provider_identity,
                expected_provider_source_digest=self.config.provider_source_digest,
                expected_config_digest=self.config.config_digest,
            )

    def test_manifest_schema_rejects_runtime_unsafe_paths(self) -> None:
        evidence = self.machine_evidence(fresh_health=True)
        unsafe_paths = ("/tmp/provider.py", "../provider.py", "pkg\\provider.py")
        digest = "sha256:" + ("a" * 64)
        schema = json.loads(
            (
                PART_ROOT
                / "config"
                / "schemas"
                / "machine-code-intelligence-evidence.schema.json"
            ).read_text(encoding="utf-8")
        )
        for field in ("runtime_manifest", "source_manifest"):
            for unsafe_path in unsafe_paths:
                with self.subTest(field=field, path=unsafe_path):
                    evidence["lsp_sessions"][0][field] = [
                        {"path": unsafe_path, "digest": digest}
                    ]
                    errors = list(Draft202012Validator(schema).iter_errors(evidence))
                    self.assertTrue(
                        any(
                            tuple(error.path)
                            == ("lsp_sessions", 0, field, 0, "path")
                            and error.validator == "pattern"
                            for error in errors
                        )
                    )
            evidence["lsp_sessions"][0][field] = []

    def test_lsp_response_header_line_is_bounded(self) -> None:
        runtime_root = self.root / "machine-runtime"
        runtime_root.mkdir()
        server = runtime_root / "fake-lsp"
        server.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        server.chmod(0o755)
        evidence = self.machine_evidence(
            artifact_digest=_digest_bytes(server.read_bytes()),
            fresh_health=True,
        )
        admitted_config = self.admitted_config(evidence)
        session = ManagedLspSession(
            [str(server)],
            provider_id="typescript-lsp",
            language="typescript",
            source_epoch="sha256:" + ("b" * 64),
            admission_config=admitted_config,
            runtime_root=runtime_root,
        )
        process = mock.Mock()
        process.stdout = BytesIO(b"X" * 16_385 + b"\n")
        session._process = process

        with self.assertRaisesRegex(LiveCodeIntelligenceError, "bounded header"):
            session._read_message()

    def test_stale_machine_health_is_not_emitted_as_current_posture(self) -> None:
        evidence = self.machine_evidence()
        admitted_config = self.admitted_config(evidence)
        status = LiveCodeIntelligenceRuntime(admitted_config).status()

        self.assertEqual(status["machine_binding"]["live_measurement"]["state"], "unobserved")
        self.assertEqual(status["machine_binding"]["admission"]["state"], "unknown")
        self.assertEqual(status["lsp_sessions"]["state"], "unobserved")
        self.assertEqual(status["lifecycle"]["state"], "source-candidate")
        self.assertEqual(status["owner_review"]["machine_evidence"], "stale")

    def test_parser_resource_failures_degrade_without_masking_other_errors(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        for failure in (MemoryError, RecursionError, SystemError):
            with self.subTest(failure=failure.__name__):
                with mock.patch("live_code_intelligence.ast.parse", side_effect=failure):
                    state = self.runtime.refresh()
                self.assertEqual(state["status"], "degraded")
                self.assertEqual(
                    state["degradation"][0]["code"],
                    "python_parse_resource_error",
                )

        with mock.patch(
            "live_code_intelligence._PythonObservationVisitor.visit",
            side_effect=SystemError,
        ):
            state = self.runtime.refresh()
        self.assertEqual(state["status"], "degraded")
        self.assertEqual(
            state["degradation"][0]["code"],
            "python_ast_traversal_error",
        )

    def test_query_reports_truncated_results(self) -> None:
        self.write_source(
            "many.py",
            "\n".join(f"def function_{index}(): return {index}" for index in range(120))
            + "\n",
        )
        self.runtime.refresh()
        with mock.patch.object(
            self.runtime,
            "_query_result",
            wraps=self.runtime._query_result,
        ) as query_result:
            result = self.runtime.definitions()

        self.assertEqual(result["status"], "truncated")
        self.assertEqual(result["result_limit"], 100)
        self.assertEqual(result["result_count"], 100)
        self.assertEqual(result["total_results"], 121)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(query_result.call_args.args[1]), 100)
        self.assertEqual(query_result.call_args.kwargs["total_results"], 121)

        self.write_source(
            "references.py",
            "\n".join(f"value_{index} = helper" for index in range(120)) + "\n",
        )
        self.runtime.refresh()
        with mock.patch.object(
            self.runtime,
            "_query_result",
            wraps=self.runtime._query_result,
        ) as query_result:
            references = self.runtime.references("helper")
        self.assertEqual(references["status"], "truncated")
        self.assertEqual(references["result_count"], 100)
        self.assertEqual(references["total_results"], 120)
        self.assertEqual(len(query_result.call_args.args[1]), 100)
        self.assertEqual(query_result.call_args.kwargs["total_results"], 120)

    def test_relative_imports_invalidate_their_importers(self) -> None:
        self.write_source("pkg/__init__.py", "\n")
        self.write_source("pkg/provider.py", "def helper():\n    return 1\n")
        self.write_source(
            "pkg/consumer.py",
            "from .provider import helper\n\ndef run():\n    return helper()\n",
        )
        self.runtime.refresh()

        self.write_source("pkg/provider.py", "def helper():\n    return 2\n")
        state = self.runtime.refresh()

        self.assertEqual(state["invalidation"]["changed_paths"], ["pkg/provider.py"])
        self.assertEqual(
            state["invalidation"]["dependency_impacted_paths"], ["pkg/consumer.py"]
        )

    def test_package_level_relative_imports_invalidate_their_importers(self) -> None:
        self.write_source("pkg/__init__.py", "\n")
        self.write_source("pkg/provider.py", "VALUE = 1\n")
        self.write_source(
            "pkg/consumer.py",
            "from . import provider\n\ndef read():\n    return provider.VALUE\n",
        )
        self.runtime.refresh()

        self.write_source("pkg/provider.py", "VALUE = 2\n")
        state = self.runtime.refresh()

        self.assertEqual(state["invalidation"]["changed_paths"], ["pkg/provider.py"])
        self.assertEqual(
            state["invalidation"]["dependency_impacted_paths"], ["pkg/consumer.py"]
        )

    def test_deleted_module_invalidates_existing_importers(self) -> None:
        self.write_source("provider.py", "def helper():\n    return 1\n")
        self.write_source(
            "consumer.py",
            "from provider import helper\n\ndef run():\n    return helper()\n",
        )
        self.write_source("unrelated.py", "VALUE = 3\n")
        first = self.runtime.refresh()

        (self.source / "provider.py").unlink()
        second = self.runtime.refresh()

        invalidation = second["invalidation"]
        self.assertEqual(invalidation["deleted_paths"], ["provider.py"])
        self.assertEqual(
            invalidation["dependency_impacted_paths"], ["consumer.py"]
        )
        self.assertIn("consumer.py", invalidation["invalidated_paths"])
        self.assertNotIn("consumer.py", invalidation["reused_paths"])
        self.assertEqual(
            second["files"]["consumer.py"]["observation"],
            first["files"]["consumer.py"]["observation"],
        )
        self.assertEqual(
            invalidation["blast_radius_universe"]["kind"],
            "previous-and-current-source-files",
        )
        self.assertEqual(invalidation["blast_radius_universe"]["count"], 3)
        self.assertEqual(invalidation["blast_radius"], round(2 / 3, 6))
        self.assertLessEqual(invalidation["blast_radius"], 1.0)

    def test_deletion_blast_radius_uses_stable_universe_for_complete_deletion(self) -> None:
        self.write_source("provider.py", "def helper():\n    return 1\n")
        self.write_source(
            "consumer.py",
            "from provider import helper\n\ndef run():\n    return helper()\n",
        )
        self.runtime.refresh()

        (self.source / "provider.py").unlink()
        partial = self.runtime.refresh()["invalidation"]

        self.assertEqual(partial["blast_radius_universe"]["count"], 2)
        self.assertEqual(partial["blast_radius"], 1.0)

        (self.source / "consumer.py").unlink()
        complete = self.runtime.refresh()["invalidation"]

        self.assertEqual(complete["deleted_paths"], ["consumer.py"])
        self.assertEqual(complete["blast_radius_universe"]["count"], 1)
        self.assertEqual(complete["blast_radius"], 1.0)
        self.assertLessEqual(complete["blast_radius"], 1.0)

    def test_config_digest_tracks_state_route_and_owner_boundaries(self) -> None:
        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        base_payload = json.loads(config_path.read_text(encoding="utf-8"))

        state_payload = json.loads(json.dumps(base_payload))
        state_payload["state"]["relative_root"] = "Knowledge/other-live-root"
        state_config_path = self.root / "state-route-config.json"
        state_config_path.write_text(json.dumps(state_payload), encoding="utf-8")
        state_config = LiveCodeIntelligenceConfig.from_file(
            state_config_path,
            source_root=self.source,
            state_root=self.state,
        )

        self.assertNotEqual(self.config.config_digest, state_config.config_digest)
        boundary_payload = json.loads(json.dumps(base_payload))
        boundary_payload["owner_boundaries"]["proof_and_verdict"] = "other-owner"
        boundary_config_path = self.root / "boundary-config.json"
        boundary_config_path.write_text(json.dumps(boundary_payload), encoding="utf-8")
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig.from_file(
                boundary_config_path,
                source_root=self.source,
                state_root=self.state,
            )

        self.assertEqual(
            LiveCodeIntelligenceRuntime(state_config).discover()["config"][
                "state_relative_root"
            ],
            "Knowledge/other-live-root",
        )

        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        refreshed = LiveCodeIntelligenceRuntime(state_config).refresh()
        self.assertTrue(refreshed["invalidation"]["full_rebuild"])
        self.assertEqual(refreshed["config"]["digest"], state_config.config_digest)

    def test_config_loader_rejects_forged_provider_machine_and_schema_claims(self) -> None:
        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        base_payload = json.loads(config_path.read_text(encoding="utf-8"))
        mutations = {
            "provider id": lambda payload: payload["provider"].update(
                {"id": "forged-provider"}
            ),
            "provider version": lambda payload: payload["provider"].update(
                {"version": "999"}
            ),
            "provider language": lambda payload: payload["provider"].update(
                {"language": "javascript"}
            ),
            "provider mode": lambda payload: payload["provider"].update(
                {"mode": "forged"}
            ),
            "provider observation schema": lambda payload: payload["provider"].update(
                {"observation_schema": "forged-observation-v1"}
            ),
            "provider boundary schema": lambda payload: payload["provider"].update(
                {"boundary_schema": "forged-boundary-v1"}
            ),
            "missing installation identity": lambda payload: payload[
                "machine_binding"
            ].pop("installation_identity"),
            "forged trust state": lambda payload: payload["machine_binding"][
                "artifact_subject"
            ].update({"trust_state": "trusted"}),
            "forged admission state": lambda payload: payload["machine_binding"][
                "artifact_subject"
            ].update({"admission_state": "admitted"}),
            "forged observation owner": lambda payload: payload["owner_boundaries"].update(
                {"observation_meaning": "abyss-stack"}
            ),
            "unexpected top-level key": lambda payload: payload.update(
                {"unexpected": True}
            ),
            "unexpected machine key": lambda payload: payload["machine_binding"].update(
                {"evidence": "self-asserted"}
            ),
            "null machine binding": lambda payload: payload.update(
                {"machine_binding": None}
            ),
        }

        for label, mutate in mutations.items():
            with self.subTest(label=label):
                payload = json.loads(json.dumps(base_payload))
                mutate(payload)
                forged_path = self.root / f"{label.replace(' ', '-')}.json"
                forged_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(LiveCodeIntelligenceError):
                    LiveCodeIntelligenceConfig.from_file(
                        forged_path,
                        source_root=self.source,
                        state_root=self.state,
                    )

    def test_direct_config_constructor_rejects_forged_identity(self) -> None:
        with self.assertRaises(LiveCodeIntelligenceError):
            replace(self.config, provider_id="forged-provider")

        machine_binding = json.loads(json.dumps(self.config.machine_binding_identity))
        machine_binding["artifact_subject"]["admission_state"] = "admitted"
        with self.assertRaises(LiveCodeIntelligenceError):
            replace(self.config, machine_binding=machine_binding)

        with self.assertRaises(LiveCodeIntelligenceError):
            replace(self.config, machine_evidence=self.machine_evidence())

    def test_machine_evidence_is_external_owner_qualified_and_provider_neutral(self) -> None:
        evidence = self.machine_evidence()
        evidence_path = self.root / "machine-evidence.json"
        evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        with self.assertRaisesRegex(
            LiveCodeIntelligenceError, "owner-authenticated registry gate"
        ):
            LiveCodeIntelligenceConfig.from_file(
                PART_ROOT / "config" / "python-ast-live-provider.json",
                source_root=self.source,
                state_root=self.state,
                machine_evidence_path=evidence_path,
            )

        self.write_source("module.py", "def stable():\n    return 1\n")
        state = self.runtime.refresh()
        self.assertEqual(state["machine_binding"]["installation"]["state"], "source-candidate")
        self.assertEqual(state["machine_binding"]["admission"]["state"], "unknown")
        self.assertEqual(state["machine_binding"]["live_measurement"]["state"], "unobserved")
        self.assertEqual(state["lsp_sessions"]["state"], "unobserved")
        self.assertEqual(state["lifecycle"]["state"], "source-candidate")
        self.assertEqual(state["owner_review"]["machine_evidence"], "missing")
        self.assertTrue(
            any(
                lane["language"] == "second-language"
                and lane["evidence_class"] == "not-observed"
                for lane in state["observation_lanes"]
            )
        )

    def test_provider_worker_queue_is_bounded_and_second_language_stays_receipt_only(self) -> None:
        for index in range(PROVIDER_QUEUE_CAPACITY + 1):
            self.write_source(
                f"module_{index:03d}.py",
                f"VALUE_{index} = {index}\n",
            )

        state = self.runtime.refresh()
        workers = state["provider_workers"]
        self.assertEqual(
            workers["schema_version"],
            "abyss-stack-live-code-intelligence-provider-worker-v1",
        )
        self.assertEqual(
            workers["queue"],
            {
                "schema_version": "abyss-stack-live-code-intelligence-provider-work-queue-v1",
                "queue_id": "queue:live-code-intelligence",
                "state": "idle",
                "capacity": PROVIDER_QUEUE_CAPACITY,
                "depth": 0,
                "ordering": "path-lexicographic",
                "delivery": "bounded-serialized",
            },
        )
        self.assertEqual(
            [worker["language"] for worker in workers["workers"]],
            ["python", "typescript"],
        )
        self.assertEqual(workers["workers"][0]["state"], "source-candidate")
        self.assertEqual(workers["workers"][0]["execution"], "in-process")
        self.assertEqual(workers["workers"][1]["state"], "receipt-only")
        self.assertEqual(workers["workers"][1]["execution"], "not-started")
        self.assertEqual(state["summary"]["source_file_count"], PROVIDER_QUEUE_CAPACITY + 1)
        self.assertEqual(self.runtime.status()["provider_workers"], workers)

    def test_self_asserted_registry_gate_requires_the_machine_trust_anchor(self) -> None:
        evidence = self.machine_evidence()
        record_digest = _digest_payload(evidence)
        record_ref = f"cas://{record_digest}"
        key_digest = "sha256:" + ("f" * 64)
        verification_ref = "cas://sha256:" + ("e" * 64)
        signed_payload = {
            "schema_version": "abyss-machine-admission-gate-signed-payload-v1",
            "owner": "abyss-machine",
            "gate_id": "gate:fixture",
            "state": "authenticated",
            "algorithm": "ed25519",
            "verification_method": "ed25519-owner-signature-v1",
            "key_id": "key:fixture",
            "key_digest": key_digest,
            "verification_ref": verification_ref,
            "registry_record_ref": record_ref,
            "registry_record_digest": record_digest,
            "evidence_digest": record_digest,
            "subject_digest": _digest_payload(evidence["subject"]),
            "provider_source_digest": self.config.provider_source_digest,
            "config_digest": self.config.config_digest,
            "claim_limits_digest": _digest_payload(evidence["claim_limits"]),
        }
        gate = {
            "schema_version": "abyss-machine-admission-gate-v1",
            "owner": "abyss-machine",
            "state": "authenticated",
            "algorithm": "ed25519",
            "verification_method": "ed25519-owner-signature-v1",
            "key_id": "key:fixture",
            "key_digest": key_digest,
            "gate_id": "gate:fixture",
            "verification_ref": verification_ref,
            "subject_digest": signed_payload["subject_digest"],
            "signed_payload": signed_payload,
            "signature": base64.b64encode(b"\0" * 64).decode("ascii"),
        }
        gate["gate_digest"] = machine_evidence_gate_digest(gate)
        bundle = {
            "schema_version": MACHINE_GATE_SCHEMA,
            "registry": {
                "schema_version": "abyss-machine-content-addressed-registry-record-v1",
                "owner": "abyss-machine",
                "record_ref": record_ref,
                "record_digest": record_digest,
                "gate_ref": f"cas://{gate['gate_digest']}",
                "gate_digest": gate["gate_digest"],
            },
            "evidence": evidence,
            "gate": gate,
        }
        bundle["bundle_digest"] = machine_evidence_bundle_digest(bundle)
        bundle_path = self.root / "self-asserted-gate.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig.from_file(
                PART_ROOT / "config" / "python-ast-live-provider.json",
                source_root=self.source,
                state_root=self.state,
                machine_evidence_path=bundle_path,
            )

    def test_owner_signature_verifier_accepts_only_the_exact_signed_bytes(self) -> None:
        public_key = bytes.fromhex(
            "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
        )
        signature = bytes.fromhex(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
        )
        self.assertTrue(_ed25519_verify(public_key, signature, b""))
        self.assertFalse(_ed25519_verify(public_key, signature, b"tampered"))

    def test_machine_evidence_digest_and_source_path_boundary_fail_closed(self) -> None:
        evidence = self.machine_evidence()
        tampered = json.loads(json.dumps(evidence))
        tampered["admission"]["state"] = "unknown"
        tampered["receipt_digest"] = machine_evidence_digest(tampered)
        tampered_path = self.root / "tampered-machine-evidence.json"
        tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig.from_file(
                PART_ROOT / "config" / "python-ast-live-provider.json",
                source_root=self.source,
                state_root=self.state,
                machine_evidence_path=tampered_path,
            )

        inside_path = self.source / "machine-evidence.json"
        inside_path.write_text(json.dumps(evidence), encoding="utf-8")
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig.from_file(
                PART_ROOT / "config" / "python-ast-live-provider.json",
                source_root=self.source,
                state_root=self.state,
                machine_evidence_path=inside_path,
            )

        self.assertNotEqual(
            machine_evidence_digest(evidence),
            machine_evidence_digest({**evidence, "receipt_id": "changed"}),
        )

    def test_concurrent_refreshes_serialize_state_transitions(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        runtimes = [LiveCodeIntelligenceRuntime(self.config) for _ in range(4)]
        active = 0
        maximum_active = 0
        counter_lock = threading.Lock()
        original = LiveCodeIntelligenceRuntime._refresh_unlocked

        def wrapped(runtime: LiveCodeIntelligenceRuntime) -> dict:
            nonlocal active, maximum_active
            with counter_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                time.sleep(0.02)
                return original(runtime)
            finally:
                with counter_lock:
                    active -= 1

        for runtime in runtimes:
            runtime._refresh_unlocked = wrapped.__get__(
                runtime, LiveCodeIntelligenceRuntime
            )

        with ThreadPoolExecutor(max_workers=len(runtimes)) as pool:
            states = list(pool.map(lambda runtime: runtime.refresh(), runtimes))

        self.assertEqual(maximum_active, 1)
        self.assertTrue(all(state["status"] == "current" for state in states))
        self.assertEqual(self.read_json(self.runtime.current_path)["status"], "current")
        self.assertFalse(self.runtime.candidate_path.exists())

    def test_source_and_state_symlinks_are_fail_closed(self) -> None:
        outside_source = self.root / "outside.py"
        outside_source.write_text("VALUE = 7\n", encoding="utf-8")
        (self.source / "linked.py").symlink_to(outside_source)
        state = self.runtime.refresh()
        self.assertEqual(state["summary"]["source_file_count"], 0)

        outside_state = self.root / "outside-state.json"
        outside_state.write_text("sentinel", encoding="utf-8")
        self.runtime.current_path.unlink()
        self.runtime.current_path.symlink_to(outside_state)
        with self.assertRaises(LiveCodeIntelligenceError):
            self.runtime.refresh()
        self.assertEqual(outside_state.read_text(encoding="utf-8"), "sentinel")

    def test_source_and_state_root_symlinks_are_rejected_before_resolution(self) -> None:
        outside_source = self.root / "outside-source"
        outside_source.mkdir()
        source_link = self.root / "source-link"
        source_link.symlink_to(outside_source, target_is_directory=True)
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig(
                source_root=source_link,
                state_root=self.state,
            )

        outside_state = self.root / "outside-state-root"
        outside_state.mkdir()
        state_link = self.root / "state-link"
        state_link.symlink_to(outside_state, target_is_directory=True)
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig(
                source_root=self.source,
                state_root=state_link,
            )

    def test_oversized_source_is_degraded_without_retaining_file_bytes(self) -> None:
        machine_binding = json.loads(json.dumps(self.config.machine_binding))
        machine_binding["resource_envelope"]["max_file_bytes"] = 8
        bounded_config = replace(
            self.config,
            max_file_bytes=8,
            machine_binding=machine_binding,
        )
        bounded_runtime = LiveCodeIntelligenceRuntime(bounded_config)
        self.write_source("large.py", "VALUE = 'this is larger'\n")

        state = bounded_runtime.refresh()

        self.assertEqual(state["status"], "degraded")
        self.assertEqual(state["degradation"][0]["code"], "file_too_large")
        self.assertNotIn("content", state["files"]["large.py"])

    def test_source_scan_does_not_retain_aggregate_file_bytes(self) -> None:
        self.write_source("one.py", "VALUE = 1\n")
        self.write_source("two.py", "VALUE = 2\n")

        scanned = self.runtime._scan()

        self.assertTrue(scanned)
        self.assertTrue(all(item.get("content") is None for item in scanned.values()))
        self.assertEqual(self.runtime.refresh()["status"], "current")

    def test_incompatible_last_good_is_not_used_after_config_drift(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        self.write_source("module.py", "VALUE = 2\n")
        self.runtime.refresh()

        drifted_config = replace(
            self.config,
            state_relative_root="Knowledge/drifted-live-root",
        )
        drifted_runtime = LiveCodeIntelligenceRuntime(drifted_config)

        self.assertEqual(drifted_runtime.status()["state"], "unavailable")
        self.assertIsNone(drifted_runtime.status()["last_good"])
        self.assertEqual(drifted_runtime.definitions()["freshness"], "unknown")

    def test_tampered_persisted_file_record_is_not_a_query_source(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        self.runtime.refresh()
        persisted = self.read_json(self.runtime.current_path)
        persisted["files"]["module.py"]["size_bytes"] += 1
        self.runtime.current_path.write_text(json.dumps(persisted), encoding="utf-8")

        self.assertEqual(self.runtime.status()["state"], "unavailable")
        self.assertEqual(self.runtime.definitions()["freshness"], "unknown")

    def test_tampered_persisted_observation_is_not_a_query_source(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        self.runtime.refresh()
        persisted = self.read_json(self.runtime.current_path)
        persisted["files"]["module.py"]["observation"]["symbols"][0][
            "name"
        ] = "forged"
        self.runtime.current_path.write_text(json.dumps(persisted), encoding="utf-8")

        self.assertEqual(self.runtime.status()["state"], "unavailable")
        self.assertEqual(self.runtime.definitions()["freshness"], "unknown")

    def test_tampered_persisted_lifecycle_is_not_a_query_source(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        persisted = self.read_json(self.runtime.current_path)
        persisted["lifecycle"]["restart"]["state"] = "ready"
        self.runtime.current_path.write_text(json.dumps(persisted), encoding="utf-8")

        self.assertEqual(self.runtime.status()["state"], "unavailable")
        self.assertEqual(self.runtime.definitions()["freshness"], "unknown")

    def test_discover_does_not_overclaim_malformed_last_good(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        self.write_source("module.py", "VALUE = 2\n")
        self.runtime.refresh()
        self.assertTrue(self.runtime.last_good_path.is_file())

        self.runtime.last_good_path.write_text("{\"forged\": true}", encoding="utf-8")

        self.assertEqual(self.runtime.status()["state"], "current")
        self.assertEqual(
            self.runtime.discover()["lifecycle"]["last_good"]["state"],
            "unavailable",
        )

    def test_new_runtime_instance_reads_current_after_restart(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        first = self.runtime.refresh()

        restarted_runtime = LiveCodeIntelligenceRuntime(self.config)

        self.assertEqual(restarted_runtime.status()["state"], "current")
        self.assertEqual(
            restarted_runtime.definitions("stable")["source_epoch"],
            first["source"]["source_epoch"],
        )

    def test_forged_persisted_machine_binding_is_not_reused(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        self.runtime.refresh()
        persisted = self.read_json(self.runtime.current_path)
        persisted["machine_binding"]["trust_binding"]["state"] = "trusted"
        self.runtime.current_path.write_text(json.dumps(persisted), encoding="utf-8")

        status = self.runtime.status()

        self.assertEqual(status["state"], "unavailable")
        self.assertIsNone(status["current"])
        self.assertEqual(self.runtime.definitions()["freshness"], "unknown")

    def test_executable_provider_boundary_emits_machine_bound_json(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(PART_ROOT / "live_code_intelligence.py"),
                "refresh",
                "--config",
                str(config_path),
                "--source-root",
                str(self.source),
                "--state-root",
                str(self.state),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["schema_version"],
            "abyss-stack-live-code-intelligence-provider-boundary-v1",
        )
        self.assertEqual(payload["operation"], "refresh")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["result"]["status"], "current")
        self.assertEqual(
            payload["machine_binding"]["admission"]["state"], "unknown"
        )

    def test_executable_lifecycle_operations_are_bounded_and_recoverable(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        first = self.runtime.refresh()
        first_epoch = first["source"]["source_epoch"]

        self.write_source("module.py", "def stable():\n    return 2\n")
        second = self.runtime.refresh()
        second_epoch = second["source"]["source_epoch"]
        self.assertNotEqual(first_epoch, second_epoch)

        last_good = self.runtime.execute("last_good")
        self.assertEqual(last_good["schema_version"], "abyss-stack-live-code-intelligence-operation-v1")
        self.assertEqual(last_good["operation"], "last_good")
        self.assertEqual(last_good["state"], "available")
        self.assertEqual(last_good["target_source_epoch"], first_epoch)
        self.assertEqual(last_good["target"]["label"], "last-good")

        current_before_canary = self.runtime.current_path.read_bytes()
        canary = self.runtime.execute("canary")
        self.assertEqual(canary["operation"], "canary")
        self.assertEqual(canary["state"], "passed")
        self.assertEqual(canary["promotion"], "none")
        self.assertEqual(self.runtime.current_path.read_bytes(), current_before_canary)

        restarted = self.runtime.execute("restart")
        self.assertEqual(restarted["operation"], "restart")
        self.assertEqual(restarted["state"], "current")
        self.assertEqual(restarted["rebuild"], "full")
        self.assertEqual(restarted["target_source_epoch"], second_epoch)

        self.write_source("module.py", "def broken(:\n    return 3\n")
        current_before_failed_canary = self.runtime.current_path.read_bytes()
        failed_canary = self.runtime.execute("canary")
        self.assertEqual(failed_canary["state"], "failed")
        self.assertTrue(failed_canary["diagnostics"])
        self.assertEqual(
            self.runtime.current_path.read_bytes(), current_before_failed_canary
        )

        rolled_back = self.runtime.execute("rollback")
        self.assertEqual(rolled_back["operation"], "rollback")
        self.assertEqual(rolled_back["state"], "rolled-back")
        self.assertEqual(rolled_back["target_source_epoch"], first_epoch)
        self.assertEqual(self.runtime.status()["state"], "current")
        self.assertEqual(
            self.read_json(self.runtime.current_path)["source"]["source_epoch"],
            first_epoch,
        )
        self.assertFalse(self.runtime.candidate_path.exists())
        for operation in ("last_good", "canary", "restart", "rollback"):
            self.assertTrue(
                (self.runtime.operation_receipts_path / f"{operation}.json").is_file()
            )

        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(PART_ROOT / "live_code_intelligence.py"),
                "last_good",
                "--config",
                str(config_path),
                "--source-root",
                str(self.source),
                "--state-root",
                str(self.state),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["operation"], "last_good")
        self.assertEqual(payload["result"]["state"], "available")

    def test_executable_boundary_rejects_unsigned_machine_evidence(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        config_path = PART_ROOT / "config" / "python-ast-live-provider.json"
        evidence_path = self.root / "machine-evidence.json"
        evidence_path.write_text(json.dumps(self.machine_evidence()), encoding="utf-8")
        completed = subprocess.run(
            [
                sys.executable,
                str(PART_ROOT / "live_code_intelligence.py"),
                "refresh",
                "--config",
                str(config_path),
                "--machine-evidence",
                str(evidence_path),
                "--source-root",
                str(self.source),
                "--state-root",
                str(self.state),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        payload = json.loads(completed.stderr)
        self.assertEqual(payload["status"], "error")
        self.assertIn("owner-authenticated registry gate", payload["error"]["message"])

    def test_parse_failure_keeps_current_and_recovers_through_last_good(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        first = self.runtime.refresh()
        first_epoch = first["source"]["source_epoch"]

        self.write_source("module.py", "def broken(:\n    return 2\n")
        degraded = self.runtime.refresh()

        self.assertEqual(degraded["status"], "degraded")
        self.assertTrue(self.runtime.candidate_path.is_file())
        self.assertEqual(
            self.read_json(self.runtime.current_path)["source"]["source_epoch"],
            first_epoch,
        )
        status = self.runtime.status()
        self.assertEqual(status["state"], "degraded")
        self.assertEqual(status["current"]["source_epoch"], first_epoch)
        self.assertEqual(status["candidate"]["status"], "degraded")
        self.assertEqual(status["degradation"][0]["code"], "python_parse_error")

        self.write_source("module.py", "def stable():\n    return 3\n")
        recovered = self.runtime.refresh()

        self.assertEqual(recovered["status"], "current")
        self.assertFalse(self.runtime.candidate_path.exists())
        self.assertEqual(
            self.read_json(self.runtime.last_good_path)["source"]["source_epoch"],
            first_epoch,
        )
        self.assertEqual(self.runtime.status()["state"], "current")

    def test_parse_failure_without_current_points_to_last_good_fallback(self) -> None:
        self.write_source("module.py", "def stable():\n    return 1\n")
        first = self.runtime.refresh()
        self.write_source("module.py", "def stable():\n    return 2\n")
        self.runtime.refresh()
        self.runtime.current_path.unlink()
        self.write_source("module.py", "def broken(:\n    return 3\n")

        degraded = self.runtime.refresh()

        self.assertEqual(degraded["status"], "degraded")
        self.assertEqual(
            degraded["fallback"],
            {"state": "last-good", "source_epoch": first["source"]["source_epoch"]},
        )
        self.assertEqual(self.runtime.status()["state"], "degraded")
        result = self.runtime.definitions("stable")
        self.assertEqual(result["freshness"], "fallback-last-good")
        self.assertEqual(result["degradation"][0]["code"], "python_parse_error")

    def test_python_definition_expressions_remain_in_enclosing_scope(self) -> None:
        self.write_source(
            "scopes.py",
            "@decorate(factory())\ndef run(value: annotation(call())) -> returns(done()):\n"
            "    return body()\n\nclass Child(base(make()), metaclass=meta(select())):\n"
            "    field = inside()\n",
        )
        state = self.runtime.refresh()
        relations = state["files"]["scopes.py"]["observation"]["relations"]
        calls = {item["target"]: item["from_id"] for item in relations if item["relation_kind"] == "calls"}
        module_id = next(
            item["id"]
            for item in state["files"]["scopes.py"]["observation"]["symbols"]
            if item["kind"] == "module"
        )
        for target in ("decorate", "factory", "annotation", "call", "returns", "done", "base", "make", "meta", "select"):
            self.assertEqual(calls[target], module_id)
        self.assertNotEqual(calls["body"], module_id)
        self.assertNotEqual(calls["inside"], module_id)

    def test_repeated_definitions_and_duplicate_imports_remain_queryable(self) -> None:
        self.write_source(
            "duplicates.py",
            "import os as first, os as second\nif flag:\n    def choose(): return 1\nelse:\n    def choose(): return 2\n",
        )
        state = self.runtime.refresh()
        self.assertEqual(state["status"], "current")
        self.assertEqual(self.runtime.status()["state"], "current")
        self.assertEqual(len(self.runtime.definitions("choose")["results"]), 2)
        relations = state["files"]["duplicates.py"]["observation"]["relations"]
        import_ids = [item["id"] for item in relations if item["relation_kind"] == "imports"]
        self.assertEqual(len(import_ids), len(set(import_ids)))

    def test_attribute_references_and_declared_python_encoding_are_observed(self) -> None:
        encoded = (
            "# -*- coding: latin-1 -*-\n"
            "label = 'café'\n"
            "def run(module):\n    return module.helper()\n"
        ).encode("latin-1")
        (self.source / "encoded.py").write_bytes(encoded)
        state = self.runtime.refresh()
        self.assertEqual(state["status"], "current")
        references = self.runtime.references("helper")
        self.assertEqual(references["status"], "ok")
        self.assertTrue(references["results"])

    def test_src_import_root_and_transitive_dependency_closure(self) -> None:
        self.write_source("src/pkg/a.py", "VALUE = 1\n")
        self.write_source("src/pkg/b.py", "from pkg.a import VALUE\n")
        self.write_source("src/pkg/c.py", "from pkg.b import VALUE\n")
        self.runtime.refresh()
        self.write_source("src/pkg/a.py", "VALUE = 2\n")
        state = self.runtime.refresh()
        self.assertEqual(
            state["invalidation"]["dependency_impacted_paths"],
            ["src/pkg/b.py", "src/pkg/c.py"],
        )

    def test_discovered_package_import_root_invalidates_importers(self) -> None:
        self.write_source("workspace/lib/pkg/__init__.py", "\n")
        self.write_source("workspace/lib/pkg/provider.py", "VALUE = 1\n")
        self.write_source(
            "workspace/lib/pkg/consumer.py",
            "from pkg.provider import VALUE\n",
        )
        self.runtime.refresh()

        self.write_source("workspace/lib/pkg/provider.py", "VALUE = 2\n")
        state = self.runtime.refresh()

        self.assertEqual(
            state["invalidation"]["dependency_impacted_paths"],
            ["workspace/lib/pkg/consumer.py"],
        )

    def test_persisted_snapshot_survives_expired_machine_health(self) -> None:
        self.write_source("module.py", "def stable(): return 1\n")
        evidence = self.machine_evidence(fresh_health=True)
        admitted_config = self.admitted_config(evidence)
        runtime = LiveCodeIntelligenceRuntime(admitted_config)
        state = runtime.refresh()
        self.assertEqual(state["status"], "current")

        authenticated = admitted_config.machine_evidence
        self.assertIsNotNone(authenticated)
        authenticated._payload["health"]["observed_at"] = "2026-08-25T00:00:01Z"

        status = runtime.status()
        self.assertEqual(status["state"], "current")
        self.assertEqual(status["owner_review"]["machine_evidence"], "stale")
        self.assertEqual(
            status["machine_binding"]["live_measurement"]["state"],
            "unobserved",
        )
        self.assertEqual(runtime.definitions("stable")["freshness"], "current")

    def test_persisted_epoch_and_missing_observation_fail_closed(self) -> None:
        self.write_source("module.py", "def stable(): return 1\n")
        state = self.runtime.refresh()
        tampered = json.loads(json.dumps(state))
        tampered["source"]["source_epoch"] = "sha256:" + ("f" * 64)
        tampered["freshness"]["source_epoch"] = tampered["source"]["source_epoch"]
        tampered["observation_envelope"]["source_epoch"] = tampered["source"]["source_epoch"]
        tampered["machine_binding"]["runtime_binding"]["source_epoch"] = tampered["source"]["source_epoch"]
        tampered["observation_envelope"]["machine_binding"] = tampered["machine_binding"]
        self.runtime.current_path.write_text(json.dumps(tampered), encoding="utf-8")
        self.assertEqual(self.runtime.status()["state"], "unavailable")

        missing = json.loads(json.dumps(state))
        missing["files"]["module.py"]["observation"] = None
        missing["summary"]["symbol_count"] = 0
        missing["summary"]["occurrence_count"] = 0
        missing["summary"]["relation_count"] = 0
        self.runtime.current_path.write_text(json.dumps(missing), encoding="utf-8")
        self.assertEqual(self.runtime.status()["state"], "unavailable")

    def test_persisted_observations_are_rederived_from_source_bytes(self) -> None:
        self.write_source(
            "module.py",
            "def stable(value):\n    return value\n",
        )
        state = self.runtime.refresh()
        tampered = json.loads(json.dumps(state))
        reference = next(
            occurrence
            for occurrence in tampered["files"]["module.py"]["observation"][
                "occurrences"
            ]
            if occurrence["kind"] == "reference"
        )
        reference["name"] = "forged"
        tampered["files"]["module.py"]["observation"]["occurrences"].sort(
            key=lambda item: (item["location"], item["kind"], item["name"])
        )
        self.runtime.current_path.write_text(json.dumps(tampered), encoding="utf-8")

        self.assertEqual(self.runtime.status()["state"], "unavailable")
        self.assertEqual(
            [],
            self.runtime.definitions("forged")["results"],
        )

    def test_persisted_authenticated_summary_must_match_capture(self) -> None:
        self.write_source("module.py", "def stable(): return 1\n")
        evidence = self.machine_evidence(fresh_health=True)
        admitted_config = self.admitted_config(evidence)
        runtime = LiveCodeIntelligenceRuntime(admitted_config)
        state = runtime.refresh()
        self.assertIn("verified_evidence", state["machine_binding"])

        tampered = json.loads(json.dumps(state))
        for binding in (
            tampered["machine_binding"],
            tampered["observation_envelope"]["machine_binding"],
        ):
            binding["verified_evidence"]["receipt_id"] = "machine-receipt:forged"
            binding["verified_evidence"]["receipt_digest"] = "sha256:" + ("f" * 64)
        runtime.current_path.write_text(json.dumps(tampered), encoding="utf-8")

        self.assertEqual(runtime.status()["state"], "unavailable")

    @unittest.skipUnless(os.name == "posix", "literal backslash names are POSIX-only")
    def test_unsupported_backslash_path_fails_before_promotion(self) -> None:
        self.write_source("stable.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        self.write_source("bad\\name.py", "VALUE = 2\n")
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "backslash"):
            self.runtime.refresh()
        self.assertEqual(
            self.read_json(self.runtime.current_path)["source"]["source_epoch"],
            first["source"]["source_epoch"],
        )

    def test_config_rejects_policy_and_resource_envelope_drift(self) -> None:
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "promotion identity"):
            replace(self.config, state_promotion="anything")
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "resource envelope"):
            replace(self.config, max_file_bytes=7)
        oversized_binding = json.loads(
            json.dumps(self.config.machine_binding_identity)
        )
        oversized_binding["resource_envelope"]["max_file_bytes"] = (
            self.config.max_file_bytes + 1
        )
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "authored"):
            replace(
                self.config,
                max_file_bytes=self.config.max_file_bytes + 1,
                machine_binding=oversized_binding,
            )

    def test_low_order_ed25519_points_are_rejected(self) -> None:
        identity = bytes([1]) + bytes(31)
        self.assertFalse(_ed25519_verify(identity, identity + bytes(32), b"anything"))

    def test_receipt_failure_rolls_back_current_promotion(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        backup = self.state / "receipts-backup"
        self.runtime.receipts_path.rename(backup)
        self.runtime.receipts_path.write_text("not a directory", encoding="utf-8")
        self.write_source("module.py", "VALUE = 2\n")
        with self.assertRaises(LiveCodeIntelligenceError):
            self.runtime.refresh()
        self.assertEqual(
            self.read_json(self.runtime.current_path)["source"]["source_epoch"],
            first["source"]["source_epoch"],
        )
        self.runtime.receipts_path.unlink()
        backup.rename(self.runtime.receipts_path)

    def test_operation_receipt_failure_restores_refresh_snapshots(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        current_before = self.runtime.current_path.read_bytes()
        last_good_before = (
            self.runtime.last_good_path.read_bytes()
            if self.runtime.last_good_path.exists()
            else None
        )
        operation_before = (
            self.runtime.operation_receipts_path / "refresh.json"
        ).read_bytes()

        self.write_source("module.py", "VALUE = 2\n")
        with mock.patch.object(
            self.runtime,
            "_write_operation_receipt",
            side_effect=LiveCodeIntelligenceError("operation receipt unavailable"),
        ):
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "operation receipt"):
                self.runtime.refresh()

        self.assertEqual(self.runtime.current_path.read_bytes(), current_before)
        if last_good_before is None:
            self.assertFalse(self.runtime.last_good_path.exists())
        else:
            self.assertEqual(self.runtime.last_good_path.read_bytes(), last_good_before)
        self.assertEqual(
            (self.runtime.operation_receipts_path / "refresh.json").read_bytes(),
            operation_before,
        )
        self.assertFalse(self.runtime.candidate_path.exists())

    def test_source_change_during_reread_records_failed_operation_receipt(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        current_before = self.runtime.current_path.read_bytes()
        first_epoch = first["source"]["source_epoch"]
        self.write_source("module.py", "VALUE = 2\n")
        changed = False
        original_read_and_parse = self.runtime._read_and_parse

        def race(path: str, metadata: dict[str, object]) -> dict[str, object]:
            nonlocal changed
            if not changed:
                changed = True
                self.write_source("module.py", "VALUE = 3\n")
            return original_read_and_parse(path, metadata)

        with mock.patch.object(self.runtime, "_read_and_parse", side_effect=race):
            with self.assertRaisesRegex(
                LiveCodeIntelligenceError,
                "source changed during refresh",
            ):
                self.runtime.refresh()

        self.assertEqual(current_before, self.runtime.current_path.read_bytes())
        self.assertFalse(self.runtime.candidate_path.exists())
        failed_receipt = self.read_json(
            self.runtime.operation_receipts_path / "refresh.json"
        )
        self.assertEqual("failed", failed_receipt["state"])
        self.assertNotEqual(first_epoch, failed_receipt["source_epoch"])
        self.assertEqual(first_epoch, failed_receipt["previous_source_epoch"])
        self.assertIsNone(failed_receipt["target_source_epoch"])

    def test_refresh_scan_failure_records_failed_operation_receipt(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        first_epoch = first["source"]["source_epoch"]

        with mock.patch.object(
            self.runtime,
            "_scan",
            side_effect=PermissionError("source tree disappeared"),
        ):
            with self.assertRaisesRegex(PermissionError, "source tree disappeared"):
                self.runtime.refresh()

        failed_receipt = self.read_json(
            self.runtime.operation_receipts_path / "refresh.json"
        )
        self.assertEqual("failed", failed_receipt["state"])
        self.assertEqual(first_epoch, failed_receipt["source_epoch"])
        self.assertEqual(first_epoch, failed_receipt["previous_source_epoch"])
        self.assertIsNone(failed_receipt["target_source_epoch"])
        self.assertEqual(first_epoch, self.read_json(self.runtime.current_path)["source"]["source_epoch"])

    def test_canary_source_change_records_failed_operation_receipt(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        current_before = self.runtime.current_path.read_bytes()
        first_epoch = first["source"]["source_epoch"]
        self.write_source("module.py", "VALUE = 2\n")
        changed = False
        original_read_and_parse = self.runtime._read_and_parse

        def race(path: str, metadata: dict[str, object]) -> dict[str, object]:
            nonlocal changed
            if not changed:
                changed = True
                self.write_source("module.py", "VALUE = 3\n")
            return original_read_and_parse(path, metadata)

        with mock.patch.object(self.runtime, "_read_and_parse", side_effect=race):
            with self.assertRaisesRegex(
                LiveCodeIntelligenceError,
                "source changed during refresh",
            ):
                self.runtime.canary()

        self.assertEqual(current_before, self.runtime.current_path.read_bytes())
        failed_receipt = self.read_json(
            self.runtime.operation_receipts_path / "canary.json"
        )
        self.assertEqual("failed", failed_receipt["state"])
        self.assertNotEqual(first_epoch, failed_receipt["source_epoch"])
        self.assertEqual(first_epoch, failed_receipt["previous_source_epoch"])
        self.assertIsNone(failed_receipt["target_source_epoch"])

    def test_canary_scan_failure_records_failed_operation_receipt(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        first = self.runtime.refresh()
        first_epoch = first["source"]["source_epoch"]
        current_before = self.runtime.current_path.read_bytes()

        with mock.patch.object(
            self.runtime,
            "_scan",
            side_effect=PermissionError("source tree disappeared"),
        ):
            with self.assertRaisesRegex(PermissionError, "source tree disappeared"):
                self.runtime.canary()

        failed_receipt = self.read_json(
            self.runtime.operation_receipts_path / "canary.json"
        )
        self.assertEqual("failed", failed_receipt["state"])
        self.assertEqual(first_epoch, failed_receipt["source_epoch"])
        self.assertEqual(first_epoch, failed_receipt["previous_source_epoch"])
        self.assertIsNone(failed_receipt["target_source_epoch"])
        self.assertEqual(current_before, self.runtime.current_path.read_bytes())

    def test_rollback_receipt_failure_restores_degraded_candidate(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        self.write_source("module.py", "VALUE = 2\n")
        self.runtime.refresh()
        self.write_source("module.py", "def broken(:\n    return 3\n")
        self.runtime.refresh()
        current_before = self.runtime.current_path.read_bytes()
        candidate_before = self.runtime.candidate_path.read_bytes()
        last_good_before = self.runtime.last_good_path.read_bytes()

        with mock.patch.object(
            self.runtime,
            "_write_operation_receipt",
            side_effect=LiveCodeIntelligenceError("operation receipt unavailable"),
        ):
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "operation receipt"):
                self.runtime.rollback()

        self.assertEqual(self.runtime.current_path.read_bytes(), current_before)
        self.assertEqual(self.runtime.candidate_path.read_bytes(), candidate_before)
        self.assertEqual(self.runtime.last_good_path.read_bytes(), last_good_before)

    def test_already_current_rollback_clears_candidate_transactionally(self) -> None:
        self.write_source("module.py", "VALUE = 1\n")
        self.runtime.refresh()
        self.write_source("module.py", "VALUE = 2\n")
        self.runtime.refresh()
        self.runtime.rollback()

        self.write_source("module.py", "def broken(:\n    return 3\n")
        self.assertEqual(self.runtime.refresh()["status"], "degraded")
        candidate_before = self.runtime.candidate_path.read_bytes()

        with mock.patch.object(
            self.runtime,
            "_write_operation_receipt",
            side_effect=LiveCodeIntelligenceError("operation receipt unavailable"),
        ):
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "operation receipt"):
                self.runtime.rollback()

        self.assertEqual(self.runtime.candidate_path.read_bytes(), candidate_before)
        self.assertEqual(self.runtime.status()["state"], "degraded")

        result = self.runtime.rollback()
        self.assertEqual(result["state"], "already-current")
        self.assertFalse(self.runtime.candidate_path.exists())
        self.assertEqual(self.runtime.status()["state"], "current")

    def test_degraded_refresh_does_not_leave_candidate_when_receipts_unavailable(self) -> None:
        self.runtime.receipts_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime.receipts_path.write_text("not a directory", encoding="utf-8")
        self.write_source("module.py", "def broken(:\n    return 1\n")

        with self.assertRaisesRegex(LiveCodeIntelligenceError, "receipt"):
            self.runtime.refresh()

        self.assertFalse(self.runtime.candidate_path.exists())

    def test_refresh_fails_closed_without_cross_process_lock(self) -> None:
        with mock.patch("live_code_intelligence.fcntl", None):
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "locking"):
                self.runtime.refresh()

        self.assertFalse(self.state.exists())

    @unittest.skipUnless(os.name == "posix", "undecodable names are POSIX-only")
    def test_undecodable_posix_filename_degrades_with_diagnostic(self) -> None:
        invalid_path = os.fsencode(str(self.source)) + b"/bad\xff.py"
        descriptor = os.open(invalid_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(b"VALUE = 2\n")

        state = self.runtime.refresh()

        self.assertEqual(state["status"], "degraded")
        self.assertTrue(
            any(
                diagnostic["code"] == "source_path_not_utf8"
                for diagnostic in state["degradation"]
            )
        )
        self.assertTrue(self.runtime.candidate_path.is_file())
        self.assertTrue(
            any(
                any(0xDC80 <= ord(character) <= 0xDCFF for character in path)
                for path in state["files"]
            )
        )

    def test_source_traversal_error_fails_refresh(self) -> None:
        error = PermissionError("denied")
        error.filename = str(self.source / "blocked")

        def broken_walk(*args, **kwargs):
            kwargs["onerror"](error)
            return iter(())

        with mock.patch("live_code_intelligence.os.walk", broken_walk):
            with self.assertRaisesRegex(LiveCodeIntelligenceError, "traverse"):
                self.runtime.refresh()

    def test_stale_machine_health_is_not_current_evidence(self) -> None:
        evidence = self.machine_evidence()
        evidence["receipt_digest"] = machine_evidence_digest(evidence)
        with self.assertRaisesRegex(LiveCodeIntelligenceError, "live health window"):
            _validate_machine_evidence_payload(
                evidence,
                expected_provider=self.config.provider_identity,
                expected_provider_source_digest=self.config.provider_source_digest,
                expected_config_digest=self.config.config_digest,
            )

    def test_state_root_inside_source_is_rejected(self) -> None:
        with self.assertRaises(LiveCodeIntelligenceError):
            LiveCodeIntelligenceConfig(
                source_root=self.source,
                state_root=self.source / "Knowledge",
            )


if __name__ == "__main__":
    unittest.main()
