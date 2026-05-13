#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib
import sys


def find_repo_root(start):
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError("could not find abyss-stack repository root")


ROOT = find_repo_root(pathlib.Path(__file__).resolve())
PART_ROOT = ROOT / "mechanics" / "agon-runtime" / "parts" / "runtime-kernels"
REG = PART_ROOT / "generated" / "duel-runtime-kernel-registry.min.json"
LOG = PART_ROOT / "examples" / "mechanical-duel-event-log.example.json"


def digest_obj(obj):
    payload = json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def fail(msg):
    print(msg, file=sys.stderr)
    return 1


def validate_hash_chain(events):
    prev = None
    for expected_seq, event in enumerate(events, start=1):
        if event.get("seq") != expected_seq:
            return fail(f"non-monotonic seq at {expected_seq}")
        if event.get("prev_hash") != prev:
            return fail(f"prev_hash mismatch at seq {expected_seq}")
        event_hash = event.get("event_hash")
        clone = dict(event)
        clone.pop("event_hash", None)
        if digest_obj(clone) != event_hash:
            return fail(f"event_hash mismatch at seq {expected_seq}")
        prev = event_hash
    return 0


def main():
    if not REG.exists():
        return fail(f"missing {REG}")
    if not LOG.exists():
        return fail(f"missing {LOG}")

    reg = json.loads(REG.read_text(encoding="utf-8"))
    kernels = reg.get("kernels", [])
    if reg.get("count") != len(kernels):
        return fail("count mismatch")
    if not kernels:
        return fail("kernel registry must contain at least one kernel")

    kernel = kernels[0]
    if kernel.get("service_activation") is not False:
        return fail("service_activation must be false")
    if kernel.get("runtime_effect") != "local_event_log_candidate_only":
        return fail("runtime_effect must be candidate-only")

    stop_lines = set(kernel.get("stop_lines", []))
    for required in [
        "no_live_verdict_authority",
        "no_durable_scar_write",
        "no_rank_or_trust_mutation",
        "no_network_listener",
        "no_background_daemon",
    ]:
        if required not in stop_lines:
            return fail(f"missing stop-line {required}")

    log = json.loads(LOG.read_text(encoding="utf-8"))
    events = log.get("events", [])
    if validate_hash_chain(events) != 0:
        return 1

    event_types = [event["event_type"] for event in events]
    if "kernel.reveal_view_recorded" in event_types:
        if "kernel.commit_phase_closed" not in event_types:
            return fail("reveal recorded without kernel.commit_phase_closed")
        if event_types.index("kernel.commit_phase_closed") > event_types.index(
            "kernel.reveal_view_recorded"
        ):
            return fail("reveal occurred before commit phase closed")

    commit_count = sum(
        1 for event in events if event["event_type"] == "kernel.sealed_commit_recorded"
    )
    if commit_count != 2:
        return fail("mechanical duel example must contain exactly two sealed commits")

    for event in events:
        if event.get("actor", "").endswith(".assistant") and event.get("payload", {}).get(
            "commit_actor"
        ):
            return fail("assistant appears to commit as contestant")

    print("agon duel runtime kernels ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
