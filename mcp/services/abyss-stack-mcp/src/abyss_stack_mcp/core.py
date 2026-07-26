"""Read-only observation and candidate-plan application for abyss-stack MCP."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import (
    ConsumerObservation,
    EvidenceRef,
    LinkEvidence,
    ObservationView,
    PlanKind,
    PlanStep,
    PolicyFamily,
    RuntimeObservation,
    RuntimePlanCandidate,
    RuntimeSubject,
)


DEFAULT_OBSERVATION_PATH = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/organ-runtime-observation.json"
)
MAX_OBSERVATION_BYTES = 2 * 1024 * 1024
_FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bearer",
        "client_secret",
        "credential_material",
        "password",
        "private_key",
        "refresh_token",
        "secret",
        "token",
    }
)


class StackMCPError(ValueError):
    """Fail-closed stack MCP contract or observation error."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def _reject_secret_material(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS:
                raise StackMCPError(f"secret-bearing key is forbidden at {path}.{key}")
            _reject_secret_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_material(child, f"{path}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        if lowered.startswith(("bearer ", "sk-", "ghp_", "github_pat_")):
            raise StackMCPError(f"secret-like value is forbidden at {path}")


class ObservationStore:
    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("ABYSS_STACK_MCP_OBSERVATION_PATH")
        self.path = Path(configured or DEFAULT_OBSERVATION_PATH).expanduser()

    def load(self) -> tuple[RuntimeObservation, str]:
        path = self.path
        try:
            descriptor = os.open(
                path,
                os.O_RDONLY
                | os.O_CLOEXEC
                | os.O_NOFOLLOW
                | getattr(os, "O_NONBLOCK", 0),
            )
            try:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise StackMCPError(
                        f"runtime observation must be an explicit regular file: {path}"
                    )
                if file_stat.st_size > MAX_OBSERVATION_BYTES:
                    raise StackMCPError("runtime observation exceeds the 2 MiB limit")
                chunks: list[bytes] = []
                remaining = MAX_OBSERVATION_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(65_536, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
            finally:
                os.close(descriptor)
            if len(raw) > MAX_OBSERVATION_BYTES:
                raise StackMCPError("runtime observation exceeds the 2 MiB limit")
            payload = json.loads(raw.decode("utf-8"))
            _reject_secret_material(payload)
            observation = RuntimeObservation.model_validate(payload)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise StackMCPError(
                    f"runtime observation must be an explicit regular file: {path}"
                ) from exc
            raise StackMCPError(f"invalid runtime observation {path}: {exc}") from exc
        except (UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise StackMCPError(f"invalid runtime observation {path}: {exc}") from exc
        digest = sha256_digest(observation.model_dump(mode="json"))
        return observation, digest


class StackMCPApplication:
    def __init__(
        self,
        store: ObservationStore,
        *,
        policy_family: str = "read",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if policy_family not in {"read", "candidate"}:
            raise StackMCPError(
                "abyss-stack-mcp exposes only separate read or candidate processes"
            )
        self.store = store
        self.policy_family = policy_family
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def catalog(
        self,
        *,
        organ_id: str | None = None,
        policy_family: PolicyFamily | None = None,
        max_results: int = 32,
        byte_budget: int = 32_768,
    ) -> dict[str, Any]:
        if max_results < 1 or byte_budget < 512:
            raise StackMCPError("catalog bounds must be positive and explicit")
        observation, digest = self.store.load()
        now = self._now()
        candidates = [
            {
                "organ_id": subject.organ_id,
                "policy_family": subject.policy_family,
                "source_owner": subject.owners.source_owner,
                "access_owner": subject.owners.access_owner,
                "runtime_owner": subject.owners.runtime_owner,
                "registry_state": subject.registry.registry_state,
                "link_states": self._link_states(subject, now),
                "freshness_state": self._effective_freshness(subject, now),
                "views": [
                    "identity",
                    "parity",
                    "process",
                    "endpoint",
                    "registry",
                    "consumer",
                    "schema",
                    "freshness",
                    "canary",
                    "rollback",
                    "drift",
                ],
            }
            for subject in observation.subjects
            if (organ_id is None or subject.organ_id == organ_id)
            and (policy_family is None or subject.policy_family == policy_family)
        ]
        selected: list[dict[str, Any]] = []
        truncated = False
        for candidate in candidates:
            if len(selected) >= max_results:
                truncated = True
                break
            trial = [*selected, candidate]
            if len(canonical_json_bytes(trial)) > byte_budget:
                truncated = True
                break
            selected.append(candidate)
        return self._result(
            observation,
            digest,
            primitive_id="runtime-catalog",
            effect_class="observe",
            payload={
                "entries": selected,
                "result_bytes": len(canonical_json_bytes(selected)),
                "schema_bytes_loaded": 0,
                "truncated": truncated,
            },
            now=now,
            freshness_state=self._worst_state(
                [entry["freshness_state"] for entry in selected] or ["exact"]
            ),
            freshness_scope="selected-subjects",
        )

    def inspect(
        self,
        organ_id: str,
        policy_family: PolicyFamily,
        *,
        view: ObservationView = "identity",
    ) -> dict[str, Any]:
        observation, digest = self.store.load()
        now = self._now()
        subject = self._find_subject(observation, organ_id, policy_family)
        payload = self._view(subject, view, now)
        return self._result(
            observation,
            digest,
            primitive_id="runtime-inspect",
            effect_class="observe",
            payload={
                "organ_id": organ_id,
                "policy_family": policy_family,
                "view": view,
                "observation": payload,
            },
            now=now,
            freshness_state=self._effective_freshness(subject, now),
            freshness_scope=f"{organ_id}/{policy_family}",
        )

    def prepare_plan(
        self,
        organ_id: str,
        target_policy_family: PolicyFamily,
        plan_kind: PlanKind,
        *,
        expected_observation_digest: str,
    ) -> dict[str, Any]:
        if self.policy_family != "candidate":
            raise StackMCPError("plan preparation is absent from the read process")
        observation, digest = self.store.load()
        now = self._now()
        if digest != expected_observation_digest:
            raise StackMCPError("observation digest drift blocks plan preparation")
        if observation.expires_at <= now:
            raise StackMCPError("expired runtime observation blocks plan preparation")
        subject = self._find_subject(
            observation,
            organ_id,
            target_policy_family,
        )
        blockers = self._plan_blockers(subject, plan_kind, now)
        if blockers:
            raise StackMCPError(
                "plan preconditions are not satisfied: " + ", ".join(blockers)
            )
        activation_consumer = (
            self._compatible_consumers(subject, now)[0]
            if plan_kind == "activate"
            else None
        )
        plan_links = self._plan_links(
            subject,
            plan_kind,
            activation_consumer=activation_consumer,
        )
        precondition_evidence = self._plan_evidence(subject, plan_links)
        unsigned = {
            "schema_version": "abyss_stack_runtime_plan_candidate_v1",
            "plan_kind": plan_kind,
            "policy_family": "candidate",
            "effect_class": "prepare_candidate",
            "execution_authorized": False,
            "approval_required_before_execution": True,
            "target_organ_id": subject.organ_id,
            "target_policy_family": subject.policy_family,
            "expected_observation_digest": digest,
            "source_revision": subject.source.revision,
            "package_digest": subject.package.artifact_digest,
            "deployed_revision": subject.deploy.revision,
            "exact_unit_name": subject.process.unit_name,
            "precondition_evidence": [
                evidence.model_dump(mode="json")
                for evidence in precondition_evidence
            ],
            "steps": [
                step.model_dump(mode="json")
                for step in self._steps(
                    subject,
                    plan_kind,
                    activation_consumer=activation_consumer,
                )
            ],
            "rollback_route": subject.rollback.rollback_route,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": self._plan_expiry(
                observation,
                subject,
                plan_links,
                precondition_evidence,
                now,
            )
            .isoformat()
            .replace("+00:00", "Z"),
        }
        plan = RuntimePlanCandidate.model_validate(
            {"plan_id": sha256_digest(unsigned), **unsigned}
        )
        return self._result(
            observation,
            digest,
            primitive_id="prepare-runtime-plan",
            effect_class="prepare_candidate",
            payload={"plan": plan.model_dump(mode="json")},
            now=now,
            freshness_state=self._effective_freshness(subject, now),
            freshness_scope=f"{organ_id}/{target_policy_family}",
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise StackMCPError("application clock must be timezone-aware")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _find_subject(
        observation: RuntimeObservation,
        organ_id: str,
        policy_family: PolicyFamily,
    ) -> RuntimeSubject:
        for subject in observation.subjects:
            if subject.organ_id == organ_id and subject.policy_family == policy_family:
                return subject
        raise StackMCPError(f"unknown runtime subject {organ_id!r}/{policy_family!r}")

    @staticmethod
    def _effective_link_state(
        link: LinkEvidence,
        now: datetime,
    ) -> str:
        if link.state not in {"exact", "compatible_drift"}:
            return link.state
        link_expired = link.expires_at is not None and link.expires_at <= now
        evidence_expired = any(
            evidence.expires_at is not None and evidence.expires_at <= now
            for evidence in link.evidence_refs
        )
        if link_expired or evidence_expired:
            return "stale_readable"
        return link.state

    @classmethod
    def _link_states(
        cls,
        subject: RuntimeSubject,
        now: datetime,
    ) -> dict[str, str]:
        return {
            "source": cls._effective_link_state(subject.source.evidence, now),
            "package": cls._effective_link_state(subject.package.evidence, now),
            "deploy": cls._effective_link_state(subject.deploy.evidence, now),
            "process": cls._effective_link_state(subject.process.evidence, now),
            "endpoint": cls._effective_link_state(subject.endpoint.evidence, now),
            "registry": cls._effective_link_state(subject.registry.evidence, now),
            "consumer": (
                "unknown"
                if not subject.consumers
                else cls._worst_state(
                    [
                        cls._effective_link_state(consumer.evidence, now)
                        for consumer in subject.consumers
                    ]
                )
            ),
            "canary": cls._effective_link_state(subject.canary.evidence, now),
            "rollback": cls._effective_link_state(subject.rollback.evidence, now),
        }

    @staticmethod
    def _worst_state(states: list[str]) -> str:
        order = (
            "exact",
            "compatible_drift",
            "stale_readable",
            "unknown",
            "blocked",
            "rollback_required",
        )
        return max(states, key=order.index)

    @staticmethod
    def _effective_freshness(
        subject: RuntimeSubject,
        now: datetime,
    ) -> str:
        if subject.freshness.state not in {"exact", "compatible_drift"}:
            return subject.freshness.state
        evidence_expired = any(
            evidence.expires_at is not None and evidence.expires_at <= now
            for evidence in subject.freshness.evidence_refs
        )
        if subject.freshness.expires_at <= now or evidence_expired:
            return "stale_readable"
        return subject.freshness.state

    def _view(
        self,
        subject: RuntimeSubject,
        view: ObservationView,
        now: datetime,
    ) -> Any:
        if view == "identity":
            return {
                "owners": subject.owners.model_dump(mode="json"),
                "credential_class": subject.credential_class,
                "effect_classes": list(subject.effect_classes),
                "source": subject.source.model_dump(mode="json"),
                "package": subject.package.model_dump(mode="json"),
                "deploy": subject.deploy.model_dump(mode="json"),
            }
        if view == "parity":
            return {
                "source_revision": subject.source.revision,
                "package_digest": subject.package.artifact_digest,
                "deployed_revision": subject.deploy.revision,
                "deployed_digest": subject.deploy.tree_digest,
                "link_states": self._link_states(subject, now),
            }
        if view == "process":
            return subject.process.model_dump(mode="json")
        if view == "endpoint":
            return subject.endpoint.model_dump(mode="json")
        if view == "registry":
            return subject.registry.model_dump(mode="json")
        if view == "consumer":
            return [consumer.model_dump(mode="json") for consumer in subject.consumers]
        if view == "schema":
            return {
                "server_schema_digest": subject.endpoint.server_schema_digest,
                "consumer_observations": [
                    {
                        "consumer_id": consumer.consumer_id,
                        "observed_schema_digest": consumer.observed_schema_digest,
                        "protocol_versions": list(consumer.observed_protocol_versions),
                    }
                    for consumer in subject.consumers
                ],
            }
        if view == "freshness":
            payload = subject.freshness.model_dump(mode="json")
            payload["effective_state"] = self._effective_freshness(subject, now)
            return payload
        if view == "canary":
            return subject.canary.model_dump(mode="json")
        if view == "rollback":
            return subject.rollback.model_dump(mode="json")
        if view == "drift":
            return {
                "states": self._link_states(subject, now),
                "freshness_state": self._effective_freshness(subject, now),
                "reason_codes": sorted(
                    {
                        reason
                        for link in (
                            subject.source.evidence,
                            subject.package.evidence,
                            subject.deploy.evidence,
                            subject.process.evidence,
                            subject.endpoint.evidence,
                            subject.registry.evidence,
                            *(consumer.evidence for consumer in subject.consumers),
                            subject.canary.evidence,
                            subject.rollback.evidence,
                        )
                        for reason in link.reason_codes
                    }
                ),
            }
        return subject.model_dump(mode="json")

    def _plan_blockers(
        self,
        subject: RuntimeSubject,
        plan_kind: PlanKind,
        now: datetime,
    ) -> list[str]:
        blockers: list[str] = []
        usable_states = {"exact", "compatible_drift"}
        effective_freshness = self._effective_freshness(subject, now)
        if subject.freshness.expires_at <= now:
            blockers.append("subject_freshness_expired")
        elif effective_freshness not in usable_states:
            blockers.append("subject_freshness_not_usable")
        required_links = {
            "source_identity": subject.source.evidence,
            "package_identity": subject.package.evidence,
            "deploy_identity": subject.deploy.evidence,
        }
        for name, link in required_links.items():
            effective_state = self._effective_link_state(link, now)
            if (
                plan_kind == "rollback"
                and effective_state == "rollback_required"
            ):
                continue
            if effective_state not in usable_states:
                blockers.append(f"{name}_not_usable")
        if plan_kind in {"activate", "restart"}:
            if subject.registry.registry_state not in {"shadow", "admitted"}:
                blockers.append("registry_state_blocks_runtime_plan")
            for name, link in (
                ("process", subject.process.evidence),
                ("endpoint", subject.endpoint.evidence),
                ("registry", subject.registry.evidence),
            ):
                if self._effective_link_state(link, now) not in usable_states:
                    blockers.append(f"{name}_evidence_not_usable")
            if subject.endpoint.server_schema_digest is None:
                blockers.append("server_schema_unobserved")
        if plan_kind == "activate":
            if not subject.process.active:
                blockers.append("process_not_active")
            if not subject.endpoint.ready:
                blockers.append("endpoint_not_ready")
            usable_consumers = [
                consumer
                for consumer in subject.consumers
                if consumer.registered
                and self._effective_link_state(consumer.evidence, now)
                in usable_states
            ]
            if not usable_consumers:
                blockers.append("no_registered_consumer")
            elif not self._compatible_consumers(subject, now):
                blockers.append("no_compatible_registered_consumer")
            if (
                not subject.canary.succeeded
                or not subject.canary.result_grounded
                or self._effective_link_state(subject.canary.evidence, now)
                not in usable_states
            ):
                blockers.append("canary_not_proven")
            if (
                not subject.rollback.ready
                or self._effective_link_state(subject.rollback.evidence, now)
                not in usable_states
            ):
                blockers.append("rollback_not_proven")
        if plan_kind == "rollback":
            if not subject.rollback.ready or self._effective_link_state(
                subject.rollback.evidence, now
            ) not in usable_states:
                blockers.append("rollback_not_proven")
        return blockers

    @classmethod
    def _compatible_consumers(
        cls,
        subject: RuntimeSubject,
        now: datetime,
    ) -> tuple[ConsumerObservation, ...]:
        compatible = [
            consumer
            for consumer in subject.consumers
            if consumer.registered
            and cls._effective_link_state(consumer.evidence, now)
            in {"exact", "compatible_drift"}
            and consumer.observed_schema_digest
            == subject.endpoint.server_schema_digest
            and bool(
                set(consumer.observed_protocol_versions)
                & set(subject.endpoint.protocol_versions)
            )
        ]
        return tuple(
            sorted(
                compatible,
                key=lambda consumer: (
                    consumer.consumer_id,
                    consumer.registration_ref,
                ),
            )
        )

    @staticmethod
    def _plan_links(
        subject: RuntimeSubject,
        plan_kind: PlanKind,
        *,
        activation_consumer: ConsumerObservation | None,
    ) -> tuple[LinkEvidence, ...]:
        links = [
            subject.source.evidence,
            subject.package.evidence,
            subject.deploy.evidence,
        ]
        if plan_kind in {"activate", "restart"}:
            links.extend(
                (
                    subject.process.evidence,
                    subject.endpoint.evidence,
                    subject.registry.evidence,
                )
            )
        if plan_kind == "activate":
            if activation_consumer is None:
                raise StackMCPError(
                    "activation plan requires one exact compatible consumer"
                )
            links.extend(
                (
                    activation_consumer.evidence,
                    subject.canary.evidence,
                    subject.rollback.evidence,
                )
            )
        elif plan_kind == "rollback":
            links.append(subject.rollback.evidence)
        return tuple(links)

    @staticmethod
    def _plan_evidence(
        subject: RuntimeSubject,
        links: tuple[LinkEvidence, ...],
    ) -> tuple[EvidenceRef, ...]:
        unique: dict[tuple[str, str, str], EvidenceRef] = {}

        def retain_earliest_expiry(evidence: EvidenceRef) -> None:
            key = (
                evidence.owner,
                evidence.evidence_ref,
                evidence.revision,
            )
            retained = unique.get(key)
            if retained is None or (
                evidence.expires_at is not None
                and (
                    retained.expires_at is None
                    or evidence.expires_at < retained.expires_at
                )
            ):
                unique[key] = evidence

        for link in links:
            for evidence in link.evidence_refs:
                retain_earliest_expiry(evidence)
        for evidence in subject.freshness.evidence_refs:
            retain_earliest_expiry(evidence)
        return tuple(unique[key] for key in sorted(unique))

    @staticmethod
    def _plan_expiry(
        observation: RuntimeObservation,
        subject: RuntimeSubject,
        links: tuple[LinkEvidence, ...],
        precondition_evidence: tuple[EvidenceRef, ...],
        now: datetime,
    ) -> datetime:
        expiries = [
            now + timedelta(minutes=10),
            observation.expires_at,
            subject.freshness.expires_at,
        ]
        expiries.extend(
            link.expires_at for link in links if link.expires_at is not None
        )
        expiries.extend(
            evidence.expires_at
            for evidence in precondition_evidence
            if evidence.expires_at is not None
        )
        return min(expiries)

    @staticmethod
    def _steps(
        subject: RuntimeSubject,
        plan_kind: PlanKind,
        *,
        activation_consumer: ConsumerObservation | None,
    ) -> tuple[PlanStep, ...]:
        if plan_kind == "activate" and activation_consumer is None:
            raise StackMCPError("activation plan requires a compatible consumer")
        actions = {
            "sync": (
                ("verify-source-revision", subject.source.revision),
                ("preview-config-sync", subject.deploy.manifest_ref),
                ("compare-deployed-digest", subject.deploy.tree_digest),
            ),
            "deploy": (
                ("verify-package-digest", subject.package.artifact_digest),
                ("stage-exact-package", subject.package.name),
                ("compare-deployed-digest", subject.deploy.tree_digest),
            ),
            "activate": (
                ("verify-registry-admission", subject.registry.registry_id),
                (
                    "verify-consumer-registration",
                    (
                        activation_consumer.registration_ref
                        if activation_consumer is not None
                        else "missing-compatible-consumer"
                    ),
                ),
                ("run-grounded-canary", subject.canary.canary_route),
            ),
            "restart": (
                ("snapshot-exact-process", subject.process.unit_name),
                ("restart-exact-unit", subject.process.unit_name),
                ("run-grounded-canary", subject.canary.canary_route),
            ),
            "rollback": (
                ("deny-discovery", subject.organ_id),
                (
                    "restore-last-known-good",
                    subject.rollback.last_known_good_package_digest or "missing",
                ),
                ("restore-consumer-registration", subject.organ_id),
                ("run-grounded-canary", subject.canary.canary_route),
            ),
        }[plan_kind]
        return tuple(
            PlanStep(
                order=index,
                action=action,
                exact_target=target,
                expected_effect=f"prepare {action} for operator review",
                stop_on=("unexpected-drift", "precondition-mismatch"),
            )
            for index, (action, target) in enumerate(actions, start=1)
        )

    def _result(
        self,
        observation: RuntimeObservation,
        digest: str,
        *,
        primitive_id: str,
        effect_class: str,
        payload: dict[str, Any],
        now: datetime,
        freshness_state: str,
        freshness_scope: str,
    ) -> dict[str, Any]:
        stale = observation.expires_at <= now
        effective_freshness = (
            self._worst_state([freshness_state, "stale_readable"])
            if stale
            else freshness_state
        )
        trace_id = sha256_digest(
            {
                "observation_digest": digest,
                "primitive_id": primitive_id,
                "payload": payload,
            }
        )
        return {
            "metadata": {
                "contract_version": "abyss_stack_mcp_result_v1",
                "source_owner": "abyss-stack",
                "access_owner": "abyss-stack",
                "runtime_owner": "abyss-stack",
                "authority_ceiling": self.policy_family,
                "observation_digest": digest,
                "provider_watermark": observation.provider_watermark,
                "observed_at": observation.generated_at.isoformat().replace(
                    "+00:00", "Z"
                ),
                "freshness_state": effective_freshness,
                "freshness_scope": freshness_scope,
                "effect_class": effect_class,
                "applied_state": "not_applied",
                "execution_authorized": False,
                "warnings": (["runtime-observation-expired"] if stale else []),
                "trace_id": trace_id,
            },
            "owner_payload": payload,
        }
