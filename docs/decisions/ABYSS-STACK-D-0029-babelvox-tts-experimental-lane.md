# BabelVox TTS Experimental Lane

- Decision ID: ABYSS-STACK-D-0029
- Status: accepted
- Date: 2026-05-15
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-15
- Surface classes: runtime profile, source/runtime boundary
- Stack lanes: service selection, inference pilots
- Mechanic parents: inference-pilots
- Guard families: service selection, profile composition
- Posture: accepted experimental lane rationale

## Context

The host TTS hot path is protected by `abyss-tts-server.service` and currently
uses the Qwen3 OpenVINO `quality-compact` profile. A BabelVox/OpenVINO 0.6B
path is available on the machine and should be testable through the Intel stack,
but current host evidence shows that NPU/GPU BabelVox cold-path synthesis is
still too slow and can push zram materially upward.

## Options considered

1. Replace the existing `50-speech.yml` route or the protected host warm TTS
   route with BabelVox.
2. Keep BabelVox host-only until it is fast enough.
3. Add BabelVox to the stack as an explicit opt-in experimental lane with lazy
   load and idle unload controls.

## Decision

Add `53-babelvox-tts.yml` and `speech-fast-experimental` as an opt-in
BabelVox/OpenVINO TTS lane. It is not part of `tools`, `intel-full`, or any
current preset. It exposes a localhost-only `babelvox-tts` API on `5102`, mounts
host-owned TTS caches under `/srv/abyss-machine/cache/ai/tts`, and keeps idle
unload/recycle enabled by default.

## Rationale

This gives the Intel stack a concrete service surface for BabelVox experiments
without promoting an unproven route into the interactive voice contract. The
service can be rendered, built, smoke-tested, and later activated with
`--profile speech-fast-experimental` when the operator explicitly wants that
experiment.

## Consequences

- BabelVox TTS becomes a source-owned stack service candidate instead of a
  host-only ad hoc path.
- Current presets stay stable and do not gain a second resident speech model.
- The remaining risk is performance: real synthesis still needs a low-pressure
  live container run before any default-route promotion.

## Source surfaces

- `compose/modules/53-babelvox-tts.yml`
- `compose/profiles/speech-fast-experimental.txt`
- `config-templates/Services/babelvox-tts-api/`
- `docs/runtime/SERVICE_SELECTION.md`
- `docs/runtime/SERVICE_CATALOG.md`

## Follow-up route

Use `scripts/aoa-smoke --profile speech-fast-experimental` for health-only
activation checks. Use `POST /synthesize` only after memory pressure is below
the host policy's hot zram window, then compare latency and zram deltas against
the protected host warm TTS route before considering promotion.
