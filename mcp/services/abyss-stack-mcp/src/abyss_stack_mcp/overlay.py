"""Compose independently issued runtime evidence overlays without inventing claims."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .core import _reject_secret_material
from .observation import (
    MAX_OVERLAY_FUTURE_SKEW,
    ObservationProducerError,
    RuntimeEvidenceOverlay,
    RuntimeEvidenceOverlaySubject,
    _digest,
    _read_json,
    _write_atomic,
)


OVERLAY_FIELDS = (
    "source",
    "endpoint",
    "consumers",
    "freshness",
    "proof",
    "acceptance",
    "canary",
    "rollback",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_fragment(
    path: Path,
    *,
    observed_at: datetime,
) -> RuntimeEvidenceOverlay:
    payload, _ = _read_json(path, "runtime evidence overlay fragment")
    _reject_secret_material(payload)
    try:
        overlay = RuntimeEvidenceOverlay.model_validate(payload)
    except ValidationError as exc:
        raise ObservationProducerError(
            "runtime evidence overlay fragment failed contract validation"
        ) from exc
    if not overlay.subjects:
        raise ObservationProducerError("runtime evidence overlay fragment has no subjects")
    if overlay.expires_at <= overlay.generated_at:
        raise ObservationProducerError(
            "runtime evidence overlay fragment expiry must follow generation"
        )
    if overlay.generated_at > observed_at + MAX_OVERLAY_FUTURE_SKEW:
        raise ObservationProducerError(
            "runtime evidence overlay fragment is causally future-dated"
        )
    if overlay.expires_at <= observed_at:
        raise ObservationProducerError("runtime evidence overlay fragment is expired")
    return overlay


def _field_payload(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, tuple):
        return [item.model_dump(mode="json") for item in value]
    return value.model_dump(mode="json")


def compose_overlays(
    paths: Sequence[Path],
    *,
    output_path: Path | None = None,
    clock: Callable[[], datetime] = _now,
) -> tuple[RuntimeEvidenceOverlay, str]:
    """Merge disjoint or byte-equivalent typed fields for each exact contour.

    The composer does not choose between competing claims. Two fragments may
    repeat a field only when its validated canonical value is identical.
    """

    if not paths:
        raise ObservationProducerError("at least one overlay fragment is required")
    observed_at = clock().astimezone(timezone.utc)
    overlays = [_load_fragment(path, observed_at=observed_at) for path in paths]
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for overlay in overlays:
        for subject in overlay.subjects:
            key = (subject.organ_id, subject.policy_family)
            target = merged.setdefault(
                key,
                {
                    "organ_id": subject.organ_id,
                    "policy_family": subject.policy_family,
                },
            )
            for field_name in OVERLAY_FIELDS:
                incoming = _field_payload(getattr(subject, field_name))
                if incoming is None:
                    continue
                current = target.get(field_name)
                if current is not None and current != incoming:
                    raise ObservationProducerError(
                        "runtime evidence overlay fragments conflict at "
                        f"{subject.organ_id}/{subject.policy_family}/{field_name}"
                    )
                target[field_name] = incoming
    try:
        composed = RuntimeEvidenceOverlay(
            generated_at=max(overlay.generated_at for overlay in overlays),
            expires_at=min(overlay.expires_at for overlay in overlays),
            contains_secrets=False,
            subjects=tuple(
                RuntimeEvidenceOverlaySubject.model_validate(merged[key])
                for key in sorted(merged)
            ),
        )
    except ValidationError as exc:
        raise ObservationProducerError(
            "composed runtime evidence overlay failed contract validation"
        ) from exc
    payload = composed.model_dump(mode="json")
    _reject_secret_material(payload)
    digest = _digest(payload)
    if output_path is not None:
        _write_atomic(output_path, payload)
    return composed, digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overlay, digest = compose_overlays(args.input, output_path=args.output)
    print(f"output={args.output.expanduser().absolute()}")
    print(f"overlay_digest={digest}")
    print(f"subject_count={len(overlay.subjects)}")
    print("claims_issued=false")
    print("contains_secrets=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
