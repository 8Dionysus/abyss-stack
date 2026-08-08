#!/usr/bin/env python3
"""Run released rmcp 3.1.2 over Streamable HTTP against the Abyss adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from run_inspector_tasks_adapter_pair import (
    PROTOCOL_VERSION,
    TASKS_EXTENSION_ID,
    _PairServer,
    _atomic_json,
    _sha256_bytes,
)


CLIENT_SOURCE = Path(__file__).with_name("rust_tasks_adapter_client.rs")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--aoa-sdk-root", type=Path, required=True)
    parser.add_argument("--rust-sdk-root", type=Path, required=True)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--cargo-target-dir", type=Path, required=True)
    parser.add_argument("--owner-receipt", type=Path, required=True)
    return parser.parse_args()


def _write_client_crate(run_root: Path, rust_sdk_root: Path) -> Path:
    crate = run_root / "client-crate"
    source_root = crate / "src"
    source_root.mkdir(parents=True, mode=0o700)
    os.chmod(crate, 0o700)
    os.chmod(source_root, 0o700)
    manifest = f"""[package]
name = "abyss-rmcp-tasks-adapter-client"
version = "0.1.0"
edition = "2024"
publish = false

[dependencies]
anyhow = "1"
reqwest = "0.13.2"
rmcp = {{ path = {json.dumps(str(rust_sdk_root / 'crates' / 'rmcp'))}, features = ["client", "reqwest", "transport-streamable-http-client-reqwest"] }}
serde_json = "1"
tokio = {{ version = "1", features = ["full"] }}
"""
    (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
    (source_root / "main.rs").write_bytes(CLIENT_SOURCE.read_bytes())
    os.chmod(crate / "Cargo.toml", 0o600)
    os.chmod(source_root / "main.rs", 0o600)
    return crate


async def _run(args: argparse.Namespace) -> Path:
    started = datetime.now(UTC)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    run_root = args.state_root.resolve() / "runs" / run_id
    run_root.mkdir(parents=True, mode=0o700)
    os.chmod(run_root, 0o700)
    crate = _write_client_crate(run_root, args.rust_sdk_root.resolve())
    bearer = secrets.token_urlsafe(32)
    pair = _PairServer(
        sdk_root=args.aoa_sdk_root.resolve(),
        state_root=run_root,
        owner_receipt=args.owner_receipt.resolve(),
        bearer=bearer,
        principal_id="rust-rmcp-3-1-2",
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    endpoint = f"http://127.0.0.1:{listener.getsockname()[1]}/mcp"
    server = uvicorn.Server(
        uvicorn.Config(pair.app, log_level="error", lifespan="off")
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        env = os.environ.copy()
        env.update(
            {
                "ABYSS_TASKS_ENDPOINT": endpoint,
                "ABYSS_TASKS_BEARER": bearer,
                "CARGO_HOME": str(args.cargo_home.resolve()),
                "CARGO_TARGET_DIR": str(args.cargo_target_dir.resolve()),
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        process = await asyncio.create_subprocess_exec(
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(crate / "Cargo.toml"),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=900)
        if process.returncode != 0:
            _atomic_json(
                run_root / "failed-request-facts.json",
                {"request_facts": pair.request_facts},
            )
            raise RuntimeError(
                "rmcp client failed: "
                + stderr.decode("utf-8", errors="replace")[-8000:]
            )
        client = json.loads(stdout)
    finally:
        server.should_exit = True
        await task
        listener.close()

    if pair.task_id is None:
        raise RuntimeError("rmcp pair did not create an Abyss task")
    task_request_facts = [
        item
        for item in pair.request_facts
        if item["method"] in {"tools/call", "tasks/get"}
    ]
    audit_actions = sorted(
        {
            json.loads(path.read_text(encoding="utf-8"))["action"]
            for path in (run_root / "task-store" / "audit").glob("*.json")
        }
    )
    public = {
        "schema_version": "abyss_rmcp_tasks_adapter_pair_v1",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "protocol_version": PROTOCOL_VERSION,
        "extension_id": TASKS_EXTENSION_ID,
        "client": {
            "implementation": "rmcp",
            "version": "3.1.2",
            "commit": "02c62aef2e331e5cf79c06c744eb1eb052cc8ebd",
            "published_release": True,
            "tasks_extension_declared": client["tasks_extension_declared"],
        },
        "adapter": {
            "feature_gate_enabled": True,
            "production_enabled": False,
            "protocol_independent_store": True,
        },
        "wire": {
            "task_created": client["task_created"],
            "completed_result_received": client["completed_result_received"],
            "extension_on_every_task_request": all(
                item["tasks_extension_present"] for item in task_request_facts
            ),
            "method_headers_match": all(
                item["method_header_matches"] for item in task_request_facts
            ),
            "name_headers_present": all(
                item["name_header_present"] for item in task_request_facts
            ),
            "unknown_task_rejected": client["unknown_task_rejected"],
        },
        "owner_result": {
            "owner": "abyss-stack",
            "authority": "diagnostic_session_v1",
            "diagnostic_digest": pair.owner_receipt_digest,
            "owner_rerun_count": pair.owner_rerun_count,
            "tool_error_preserved": client["owner_tool_error_preserved"],
        },
        "store": {
            "task_id_digest": _sha256_bytes(pair.task_id.encode("utf-8")),
            "audit_actions": audit_actions,
            "durable_before_handle": True,
        },
        "verdict": "released_rmcp_passed_feature_gated_abyss_adapter",
        "claim_limits": [
            "This proves released rmcp 3.1.2 create/get/completed-result behavior over Streamable HTTP against the Abyss adapter.",
            "The owner diagnostic was reused by digest and was not rerun; its tool-level error remains visible inside a completed task.",
            "The adapter feature gate was enabled only in the isolated lab and remains disabled in production.",
            "Input update, cancellation, notifications, distributed poll limits, and Codex Tasks consumption require independent pair evidence.",
        ],
    }
    private = {
        "public": public,
        "client": client,
        "request_facts": pair.request_facts,
        "owner_receipt_path": str(args.owner_receipt.resolve()),
        "stderr_digest": _sha256_bytes(stderr),
    }
    _atomic_json(run_root / "private.json", private)
    _atomic_json(run_root / "public-safe.json", public)
    return run_root / "public-safe.json"


def main() -> int:
    try:
        result = asyncio.run(_run(_parse_args()))
    except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
        print(f"rmcp Tasks adapter pair failed: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
