"""Event/backstop sweep for persisted machine-readable MCP preflight reports."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .contracts import Identifier, NonEmpty, StrictModel
from .preflight import (
    MCPPreflightReport,
    ManagedContourBinding,
    PreflightCheck,
    PreflightError,
    _digest,
    _format_time,
    load_catalog,
    publish_report,
    run_preflight,
)


class PreflightSweepEntry(StrictModel):
    binding_id: Identifier
    organ_id: Identifier
    contour_id: Identifier
    report_id: NonEmpty
    report_ref: NonEmpty
    eligible_to_start: bool
    reason_codes: tuple[Identifier, ...]


class MCPPreflightSweepStatus(StrictModel):
    schema_version: Literal["abyss_mcp_preflight_sweep_v1"] = (
        "abyss_mcp_preflight_sweep_v1"
    )
    status_id: NonEmpty
    generated_at: datetime
    contour_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    all_eligible: bool
    entries: tuple[PreflightSweepEntry, ...]
    next_safe_step: NonEmpty
    services_started_or_restarted: Literal[False] = False
    contains_secrets: Literal[False] = False

    @field_validator("generated_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("preflight sweep timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)


def run_sweep(
    catalog_path: Path,
    output_root: Path,
    *,
    generated_at: datetime | None = None,
) -> MCPPreflightSweepStatus:
    now = generated_at or datetime.now(timezone.utc)
    catalog = load_catalog(catalog_path)
    entries: list[PreflightSweepEntry] = []
    for binding in sorted(catalog.contours, key=lambda item: item.binding_id):
        try:
            report = run_preflight(binding, checked_at=now)
        except (OSError, ValueError) as exc:
            report = _input_error_report(binding, now, exc)
        report_path = output_root / "reports" / f"{binding.binding_id}.json"
        publish_report(report, report_path)
        entries.append(
            PreflightSweepEntry(
                binding_id=binding.binding_id,
                organ_id=binding.organ_id,
                contour_id=binding.contour_id,
                report_id=report.report_id,
                report_ref=str(report_path),
                eligible_to_start=report.eligible_to_start,
                reason_codes=report.reason_codes,
            )
        )
    eligible_count = sum(item.eligible_to_start for item in entries)
    unsigned = {
        "generated_at": _format_time(now),
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    return MCPPreflightSweepStatus(
        status_id=_digest(unsigned),
        generated_at=now,
        contour_count=len(entries),
        eligible_count=eligible_count,
        blocked_count=len(entries) - eligible_count,
        all_eligible=eligible_count == len(entries),
        entries=tuple(entries),
        next_safe_step=(
            "managed contours may be started only through their own unit gates"
            if eligible_count == len(entries)
            else "open the first blocked contour report and repair its first reason code"
        ),
    )


def publish_status(status: MCPPreflightSweepStatus, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(
        status.model_dump(mode="json"), ensure_ascii=True, indent=2, sort_keys=True
    ).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _input_error_report(
    binding: ManagedContourBinding, now: datetime, exc: Exception
) -> MCPPreflightReport:
    # Error text is deliberately reduced to its class; paths/values remain in
    # the catalog and no bearer material can enter the status surface.
    reason = "preflight_input_unavailable"
    check = PreflightCheck(
        check_id="preflight-input",
        status="blocked",
        reason_code=reason,
        expected_identity="all declared inputs readable and valid",
        observed_identity=type(exc).__name__,
    )
    unsigned = {
        "organ_id": binding.organ_id,
        "contour_id": binding.contour_id,
        "checked_at": _format_time(now),
        "reason": reason,
        "error_class": type(exc).__name__,
    }
    return MCPPreflightReport(
        report_id=_digest(unsigned),
        organ_id=binding.organ_id,
        contour_id=binding.contour_id,
        policy_family=binding.policy_family,
        checked_at=now,
        eligible_to_start=False,
        checks=(check,),
        reason_codes=(reason,),
        next_safe_step="repair the declared preflight input and rerun the sweep",
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="abyss-stack-mcp-preflight-sweep")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = run_sweep(args.catalog, args.output_root)
        publish_status(status, args.output_root / "current.json")
    except (OSError, PreflightError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(status.model_dump(mode="json"), ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
