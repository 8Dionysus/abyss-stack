from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from abyss_stack_mcp.observation import ObservationProducerError
from abyss_stack_mcp.overlay import compose_overlays


NOW = datetime(2026, 8, 1, 3, 0, tzinfo=timezone.utc)
DIGEST = "sha256:" + "a" * 64


def evidence(owner: str, ref: str) -> dict:
    return {
        "state": "exact",
        "observed_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=20)).isoformat(),
        "evidence_refs": [
            {
                "owner": owner,
                "evidence_ref": ref,
                "revision": DIGEST,
                "observed_at": NOW.isoformat(),
                "expires_at": (NOW + timedelta(minutes=20)).isoformat(),
            }
        ],
        "reason_codes": [],
    }


def fragment(subject: dict, *, expires_minutes: int = 20) -> dict:
    return {
        "schema_version": "abyss_stack_runtime_evidence_overlay_v1",
        "generated_at": NOW.isoformat(),
        "expires_at": (NOW + timedelta(minutes=expires_minutes)).isoformat(),
        "contains_secrets": False,
        "subjects": [subject],
    }


def write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def consumer_subject() -> dict:
    registration_ref = "consumer-registration://8Dionysus/codex/aoa_kag/" + "b" * 64
    return {
        "organ_id": "aoa-kag",
        "policy_family": "read",
        "consumers": [
            {
                "consumer_id": "codex",
                "registration_ref": registration_ref,
                "registered": True,
                "observed_schema_digest": DIGEST,
                "observed_protocol_versions": ["2025-11-25"],
                "evidence": evidence("8Dionysus", registration_ref),
            }
        ],
    }


def endpoint_subject() -> dict:
    return {
        "organ_id": "aoa-kag",
        "policy_family": "read",
        "endpoint": {
            "transport": "streamable-http",
            "endpoint_ref": "http://127.0.0.1:5425/mcp",
            "protocol_versions": ["2025-11-25"],
            "ready": True,
            "server_schema_digest": DIGEST,
            "evidence": evidence("abyss-stack", "receipt://stack/canary"),
        },
    }


def test_compose_disjoint_fields_and_bound_expiry(tmp_path: Path) -> None:
    consumer = write(tmp_path / "consumer.json", fragment(consumer_subject(), expires_minutes=20))
    endpoint = write(tmp_path / "endpoint.json", fragment(endpoint_subject(), expires_minutes=10))
    output = tmp_path / "composed.json"

    composed, digest = compose_overlays(
        [endpoint, consumer],
        output_path=output,
        clock=lambda: NOW,
    )

    assert digest.startswith("sha256:")
    assert composed.expires_at == NOW + timedelta(minutes=10)
    assert composed.subjects[0].endpoint is not None
    assert composed.subjects[0].consumers is not None
    assert output.stat().st_mode & 0o777 == 0o600


def test_composition_is_input_order_independent(tmp_path: Path) -> None:
    consumer = write(tmp_path / "consumer.json", fragment(consumer_subject()))
    endpoint = write(tmp_path / "endpoint.json", fragment(endpoint_subject()))

    first, first_digest = compose_overlays([consumer, endpoint], clock=lambda: NOW)
    second, second_digest = compose_overlays([endpoint, consumer], clock=lambda: NOW)

    assert first == second
    assert first_digest == second_digest


def test_conflicting_claims_fail_closed(tmp_path: Path) -> None:
    first = write(tmp_path / "first.json", fragment(endpoint_subject()))
    changed = endpoint_subject()
    changed["endpoint"]["server_schema_digest"] = "sha256:" + "c" * 64
    second = write(tmp_path / "second.json", fragment(changed))

    with pytest.raises(ObservationProducerError, match="conflict.*endpoint"):
        compose_overlays([first, second], clock=lambda: NOW)


def test_expired_fragment_fails_closed(tmp_path: Path) -> None:
    expired = write(
        tmp_path / "expired.json",
        fragment(consumer_subject(), expires_minutes=1),
    )

    with pytest.raises(ObservationProducerError, match="expired"):
        compose_overlays(
            [expired],
            clock=lambda: NOW + timedelta(minutes=2),
        )
