# abyss-stack local stats port

This directory exposes statistical questions whose domain meaning belongs to
`abyss-stack`. It uses the shared `aoa-stats` measurement grammar without
moving runtime observation or service-selection authority into the central
organ.

## Current measurement

`abyss-stack/selected-service-running-coverage-ratio` asks what fraction of
the services classified as `selected_now` by the loaded owner policy are
observed in the `running` state by one service-selection readout.

The existing `scripts/aoa-status --service-selection --json` read model is the
consumer. Its denominator is every `selected_now` policy entry, including a
selected service whose matching container is missing. Non-selected policy
entries, unknown running services, and duplicate containers do not enter the
ratio.

A zero ratio is an observation only when container inspection succeeded and
the selected population is non-empty. An empty selected population or an
unavailable container observation is `unknown`, not zero.

## Evidence posture

The measurement is live-capable and internal, but the Git export is
declaration-only. Live container state, runtime roots, and generated readouts
remain outside this source port.

## Authority

The ratio describes one runtime observation boundary. It does not establish
individual service health, availability over time, correctness, performance,
quality, user value, routing truth, or permission to restart services or alter
deployment policy.

## Surfaces

- `port.manifest.json` declares the owner-local question and measurement.
- `docs/runtime/service-selection-policy.v1.json` owns the selected population.
- `mechanics/runtime-lifecycle/parts/logs-status/aoa_service_selection_status.py`
  owns observation and derivation.
- `aoa-stats` owns shared validation and cross-owner composition.
