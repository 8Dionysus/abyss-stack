#!/usr/bin/env python3
"""Validate one protocol-watch run and emit a bounded public-safe verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _write_public(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temporary, path)
    path.chmod(0o644)


def normalize(paths: dict[str, Path]) -> dict[str, Any]:
    conformance = _load(paths["conformance"])
    adapter = _load(paths["adapter"])
    handle = _load(paths["handle"])
    cache = _load(paths["cache"])
    codex = _load(paths["codex"])
    rollback = _load(paths["rollback"])
    _require(
        conformance.get("verdict") == "frozen_requirements_passed"
        and conformance.get("requirements_revision") == "2026-07-28"
        and conformance.get("expected_failure_baseline_used") is False
        and conformance.get("client", {}).get("returncode") == 0
        and conformance.get("server", {}).get("returncode") == 0,
        "frozen conformance receipt is not green",
    )
    cancellation = adapter.get("pair", {}).get("cancellation", {})
    _require(
        adapter.get("verdict") == "passed"
        and cancellation
        == {
            "client_request_cancelled": True,
            "server_dispatch_cancelled": True,
            "server_dispatch_completed_after_client_cancel": False,
        },
        "adapter cancellation did not reach the worker",
    )
    handle_checks = handle.get("pair", {}).get("checks", {})
    _require(
        handle.get("verdict") == "passed"
        and handle_checks.get("valid_round_trip", {}).get("outcome") == "passed"
        and all(
            handle_checks.get(name, {}).get("outcome") == "denied"
            for name in (
                "cross_request_replay",
                "expiry",
                "key_retirement_revocation",
                "principal_isolation",
                "tamper",
            )
        ),
        "requestState handle isolation receipt is incomplete",
    )
    cache_checks = cache.get("pair", {}).get("checks", {})
    _require(
        cache.get("verdict") == "passed"
        and all(
            cache_checks.get(name) is True
            for name in (
                "explicit_refresh_replaces_stale_entry",
                "no_subscription_no_replay",
                "subscription_addition_invalidation",
                "subscription_removal_revocation",
                "ttl_expiry_refetch",
            )
        )
        and cache_checks.get("stale_catalog_cannot_authorize_removed_tool", {}).get("is_error") is True,
        "cache invalidation or removed-tool revocation receipt is incomplete",
    )
    _require(
        codex.get("verdict") == "isolated_stable_pair_passed"
        and codex.get("wire", {}).get("version") == "2026-07-28"
        and codex.get("wire", {}).get("server_discover_observed") is True
        and codex.get("wire", {}).get("tasks_extension_advertised") is False
        and all(codex.get("rollback", {}).values()),
        "stable Codex modern lab receipt is incomplete",
    )
    _require(
        rollback.get("verdict") == "stable_production_route_passed_after_lab_rollback"
        and rollback.get("canary", {}).get("is_error") is False
        and rollback.get("stable_registration", {}).get("unchanged") is True,
        "stable post-rollback canary is incomplete",
    )
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "abyss_mcp_protocol_watch_run_verdict_v1",
        "observed_at": now,
        "verdict": "compatible_for_lab_and_read_canary",
        "facts": {
            "frozen_core_conformance_passed": True,
            "modern_cancellation_propagated": True,
            "auth_schema_trace_limits_passed": True,
            "request_state_isolation_passed": True,
            "cache_refresh_and_removal_revocation_passed": True,
            "stable_modern_codex_lab_passed": True,
            "stable_post_rollback_canary_passed": True,
            "client_extension_capability_absent": True,
            "production_cutover_allowed": False,
        },
        "receipt_digests": {
            name: _sha256(path) for name, path in sorted(paths.items())
        },
        "claim_limits": [
            "This verdict admits only a removable lab and bounded read canary, not production cutover.",
            "The missing Tasks client capability remains an independent extension blocker.",
            "Candidate and effect contours cannot inherit this read-only result.",
            "Owner acceptance, registry admission, deployment and observation remain separate transactions.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("conformance", "adapter", "handle", "cache", "codex", "rollback"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    paths = {name: getattr(args, name) for name in ("conformance", "adapter", "handle", "cache", "codex", "rollback")}
    result = normalize(paths)
    _write_public(args.output, result)
    print(f"[ok] wrote public-safe protocol-watch verdict: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
