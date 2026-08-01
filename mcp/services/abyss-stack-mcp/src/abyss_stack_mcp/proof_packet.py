"""Bind one independently observed consumer to a bounded eval packet candidate."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import RuntimeObservation
from .core import _reject_secret_material
from .observation import ObservationProducerError, _digest, _read_json, _write_atomic


class ProofPacketBindingError(ObservationProducerError):
    """A consumer observation cannot be bound to the selected packet."""


def bind_consumer_registration(
    *,
    packet_path: Path,
    observation_path: Path,
    consumer_id: str,
    output_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    packet, _ = _read_json(packet_path, "bounded proof packet")
    observation_payload, _ = _read_json(
        observation_path, "runtime observation"
    )
    for payload in (packet, observation_payload):
        _reject_secret_material(payload)
    try:
        observation = RuntimeObservation.model_validate(observation_payload)
    except ValidationError as exc:
        raise ProofPacketBindingError(
            "runtime observation failed contract validation"
        ) from exc
    if packet.get("schema_version") != "organ_access_proof_packet_v1":
        raise ProofPacketBindingError("proof packet schema is unsupported")
    matches = [
        subject
        for subject in observation.subjects
        if subject.organ_id == packet.get("organ_id")
        and subject.policy_family == packet.get("policy_plane")
    ]
    if len(matches) != 1:
        raise ProofPacketBindingError("runtime observation lacks one exact subject")
    subject = matches[0]
    maturity = packet.get("maturity")
    revisions = packet.get("revisions")
    protocol_pair = packet.get("protocol_pair")
    if not all(
        isinstance(value, dict)
        for value in (maturity, revisions, protocol_pair)
    ):
        raise ProofPacketBindingError("proof packet target fields are malformed")
    assert isinstance(maturity, dict)
    assert isinstance(revisions, dict)
    assert isinstance(protocol_pair, dict)
    existing = maturity.get("consumer_registered")
    if existing != {"state": "not_asserted"}:
        raise ProofPacketBindingError(
            "consumer registration axis must be exactly not_asserted"
        )
    consumers = [
        consumer
        for consumer in subject.consumers
        if consumer.consumer_id == consumer_id
    ]
    if len(consumers) != 1:
        raise ProofPacketBindingError("selected consumer is not unique")
    consumer = consumers[0]
    if (
        not consumer.registered
        or consumer.evidence.state != "exact"
        or consumer.evidence.expires_at is None
        or consumer.observed_schema_digest != subject.endpoint.server_schema_digest
        or not (
            set(consumer.observed_protocol_versions)
            & set(subject.endpoint.protocol_versions)
        )
        or not any(
            evidence.evidence_ref == consumer.registration_ref
            for evidence in consumer.evidence.evidence_refs
        )
    ):
        raise ProofPacketBindingError(
            "selected consumer registration is not exact and compatible"
        )
    if revisions.get("consumer_schema") != (
        "consumer-schema:" + consumer.observed_schema_digest
    ):
        raise ProofPacketBindingError(
            "packet consumer schema revision differs from observation"
        )
    if protocol_pair.get("transport") != subject.endpoint.transport:
        raise ProofPacketBindingError("packet transport differs from observation")
    evidence_ref = next(
        evidence
        for evidence in consumer.evidence.evidence_refs
        if evidence.evidence_ref == consumer.registration_ref
    )
    expiries = [consumer.evidence.expires_at]
    if evidence_ref.expires_at is not None:
        expiries.append(evidence_ref.expires_at)
    expiry = min(expiries)
    maturity["consumer_registered"] = {
        "state": "asserted",
        "observed_at": consumer.evidence.observed_at.isoformat(),
        "expires_at": expiry.isoformat(),
        "evidence_ref": consumer.registration_ref,
        "evidence_kind": "consumer_registration",
        "revision": revisions["consumer_schema"],
    }
    base_packet_id = packet.get("packet_id")
    if not isinstance(base_packet_id, str):
        raise ProofPacketBindingError("proof packet id is unavailable")
    binding_digest = _digest(
        {
            "base_packet_id": base_packet_id,
            "consumer_id": consumer.consumer_id,
            "registration_ref": consumer.registration_ref,
            "registration_revision": evidence_ref.revision,
        }
    ).removeprefix("sha256:")[:16]
    packet["packet_id"] = (base_packet_id[:100] + ".consumer." + binding_digest)
    result = packet.get("result")
    if not isinstance(result, dict) or result.get("verdict") != "insufficient_evidence":
        raise ProofPacketBindingError(
            "consumer binding cannot promote the packet result verdict"
        )
    missing = sorted(
        name
        for name, axis in maturity.items()
        if isinstance(axis, dict) and axis.get("state") == "not_asserted"
    )
    limitations = result.get("limitations")
    if not isinstance(limitations, list) or not all(
        isinstance(item, str) for item in limitations
    ):
        raise ProofPacketBindingError("proof packet limitations are malformed")
    limitations = [
        item
        for item in limitations
        if not item.startswith("Missing maturity axes remain not asserted:")
    ]
    limitations.append(
        "Missing maturity axes remain not asserted: " + ", ".join(missing) + "."
    )
    limitations.append(
        "The independently observed consumer registration does not prove central "
        "proof, owner acceptance, admission, effects, cross-organ benefit, or rollback."
    )
    result["limitations"] = list(dict.fromkeys(limitations))
    _reject_secret_material(packet)
    digest = _digest(packet)
    if output_path is not None:
        _write_atomic(output_path, packet)
    return packet, digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--consumer-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        packet, digest = bind_consumer_registration(
            packet_path=args.packet,
            observation_path=args.observation,
            consumer_id=args.consumer_id,
            output_path=args.output,
        )
    except ProofPacketBindingError as exc:
        print(f"proof packet consumer binding: {exc}", file=__import__("sys").stderr)
        return 1
    print(f"output={args.output.expanduser().absolute()}")
    print(f"packet_digest={digest}")
    print(f"packet_id={packet['packet_id']}")
    print("consumer_registered=asserted")
    print("central_proof_asserted=false")
    print("owner_accepted=false")
    print("admission_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
