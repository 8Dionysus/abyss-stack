#!/usr/bin/env python3
"""Run exact Python MCP 2.1.1 client/server conformance for 2026-07-28."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import socket
import subprocess
import time
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


CONFORMANCE_COMMIT = "c321dd32035556e6769d3724a8ee97d87c3faaac"
CONFORMANCE_VERSION = "0.2.0-alpha.11"
PYTHON_SDK_COMMIT = "0921d94a74db900dccd2d534842aa7b6160542d2"
PYTHON_SDK_VERSION = "2.1.1"
REQUIREMENTS_REVISION = "2026-07-28"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _tree_digest(root: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
        count += 1
    return f"sha256:{digest.hexdigest()}", count


def _private_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(0o600)


def _wait_port(port: int, process: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Python conformance server exited with {process.returncode}")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"Python conformance server did not bind port {port}")


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        cwd=cwd,
        check=False,
        capture_output=True,
        timeout=timeout,
    )


def _sdk_identity(sdk_python: Path, sdk_root: Path) -> dict[str, str]:
    """Attest the SDK using the interpreter that actually runs conformance."""
    scripts_root = Path(__file__).resolve().parent
    probe = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(scripts_root)!r})\n"
        "from pathlib import Path\n"
        "from _mcp_sdk_identity import installed_mcp_identity\n"
        f"print(json.dumps(installed_mcp_identity(Path({str(sdk_root)!r})), sort_keys=True))\n"
    )
    completed = subprocess.run(
        [str(sdk_python), "-I", "-B", "-c", probe],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Python MCP SDK identity attestation failed: "
            + completed.stderr.strip()[-2000:]
        )
    try:
        identity = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Python MCP SDK identity attestation returned invalid JSON") from exc
    if not isinstance(identity, dict) or not all(
        isinstance(identity.get(key), str)
        for key in ("version", "commit", "artifact_digest")
    ):
        raise RuntimeError("Python MCP SDK identity attestation returned an incomplete identity")
    return identity


def run(args: argparse.Namespace) -> dict[str, Any]:
    started_at = _timestamp()
    conformance_root = args.conformance_root.resolve(strict=True)
    sdk_root = args.python_sdk_root.resolve(strict=True) if args.python_sdk_root else None
    node = args.node.resolve(strict=True)
    cli = (conformance_root / "dist" / "index.js").resolve(strict=True)
    if args.installed_runtime:
        if sdk_root is not None:
            raise ValueError("installed runtime cannot be combined with SDK source")
        from _lab_runtime_identity import sdk_identity as lab_sdk_identity
        sdk_identity = lab_sdk_identity(args)
        sdk_python = Path(sys.executable)
        fixture = Path(__file__).resolve().parents[1] / "fixtures/sdk-conformance-2.1.1"
        manifest = json.loads((fixture / "manifest.json").read_text())
        if manifest["source_revision"] != sdk_identity["commit"]:
            raise RuntimeError("conformance fixture revision differs from installed SDK")
        expected_files = {"client.py", "LICENSE", "mcp_everything_server/__init__.py", "mcp_everything_server/__main__.py", "mcp_everything_server/server.py"}
        if set(manifest["files"]) != expected_files:
            raise RuntimeError("conformance fixture file set differs")
        for relative, digest in manifest["files"].items():
            path = fixture / relative
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError("conformance fixture bytes differ")
        sdk_client = fixture / "client.py"
        server_command = [str(sdk_python), "-B", "-m", "mcp_everything_server", "--port", str(args.port)]
        server_cwd = fixture
    else:
        if sdk_root is None:
            raise ValueError("development conformance requires --python-sdk-root")
        sdk_python = sdk_root / ".venv/bin/python"
        sdk_client = (sdk_root / ".github/actions/conformance/client.py").resolve(strict=True)
        sdk_server = (sdk_root / ".venv/bin/mcp-everything-server").resolve(strict=True)
        if _git_head(sdk_root) != PYTHON_SDK_COMMIT:
            raise RuntimeError("Python SDK checkout does not match v2.1.1")
        sdk_identity = _sdk_identity(sdk_python, sdk_root)
        server_command = [str(sdk_server), "--port", str(args.port)]
        server_cwd = sdk_root
    if _git_head(conformance_root) != CONFORMANCE_COMMIT:
        raise RuntimeError("conformance checkout does not match the exact current commit")
    package = json.loads((conformance_root / "package.json").read_text())
    if package.get("version") != CONFORMANCE_VERSION:
        raise RuntimeError("conformance package version drifted")
    client_root = args.output_root / "client"
    server_root = args.output_root / "server"
    client_root.mkdir(parents=True, mode=0o700)
    server_root.mkdir(parents=True, mode=0o700)
    client_command = shlex.join([str(sdk_python), str(sdk_client)])
    client = _run(
        [
            str(node),
            str(cli),
            "client",
            "--command",
            client_command,
            "--requirements",
            REQUIREMENTS_REVISION,
            "--output-dir",
            str(client_root),
        ],
        cwd=conformance_root,
        timeout=args.timeout,
    )
    _private_write(args.output_root / "client.stdout", client.stdout)
    _private_write(args.output_root / "client.stderr", client.stderr)
    if client.returncode != 0:
        raise RuntimeError(f"frozen client conformance returned {client.returncode}")

    server_process = subprocess.Popen(
        server_command,
        cwd=server_cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_port(args.port, server_process)
        server = _run(
            [
                str(node),
                str(cli),
                "server",
                "--url",
                f"http://127.0.0.1:{args.port}/mcp",
                "--requirements",
                REQUIREMENTS_REVISION,
                "--output-dir",
                str(server_root),
            ],
            cwd=conformance_root,
            timeout=args.timeout,
        )
    finally:
        server_process.terminate()
        try:
            server_stdout, server_stderr = server_process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server_process.kill()
            server_stdout, server_stderr = server_process.communicate(timeout=10)
        _private_write(args.output_root / "sdk-server.stdout", server_stdout)
        _private_write(args.output_root / "sdk-server.stderr", server_stderr)
    _private_write(args.output_root / "server.stdout", server.stdout)
    _private_write(args.output_root / "server.stderr", server.stderr)
    if server.returncode != 0:
        raise RuntimeError(f"frozen server conformance returned {server.returncode}")
    client_digest, client_files = _tree_digest(client_root)
    server_digest, server_files = _tree_digest(server_root)
    return {
        "schema_version": "abyss_mcp_frozen_conformance_run_v1",
        "observed_at": started_at,
        "finished_at": _timestamp(),
        "requirements_revision": REQUIREMENTS_REVISION,
        "conformance": {
            "commit": CONFORMANCE_COMMIT,
            "version": CONFORMANCE_VERSION,
        },
        "python_sdk": {
            "artifact_digest": sdk_identity["artifact_digest"],
            "commit": sdk_identity["commit"],
            "source_checkout_clean": not args.installed_runtime,
            "input_mode": "installed_runtime" if args.installed_runtime else "source_checkout",
            "version": sdk_identity["version"],
        },
        "client": {
            "returncode": client.returncode,
            "result_tree_sha256": client_digest,
            "result_file_count": client_files,
        },
        "server": {
            "returncode": server.returncode,
            "result_tree_sha256": server_digest,
            "result_file_count": server_files,
        },
        "expected_failure_baseline_used": False,
        "verdict": "frozen_requirements_passed",
        "claim_limits": [
            "This proves the exact Python SDK against frozen 2026-07-28 requirements only.",
            "Later visibility scenarios do not become retroactive scored requirements.",
            "SDK conformance does not prove Codex, Abyss admission, Tasks, or production cutover.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conformance-root", required=True, type=Path)
    parser.add_argument("--python-sdk-root", type=Path)
    parser.add_argument("--installed-runtime", action="store_true")
    parser.add_argument("--node", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--timeout", default=300, type=int)
    args = parser.parse_args()
    result = run(args)
    _private_write(
        args.summary,
        json.dumps(result, indent=2, sort_keys=True).encode() + b"\n",
    )
    print(f"[ok] wrote frozen conformance receipt: {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
