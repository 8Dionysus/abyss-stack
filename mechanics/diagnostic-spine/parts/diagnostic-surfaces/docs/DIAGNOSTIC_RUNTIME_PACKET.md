# Diagnostic Runtime Packet

## Role

This packet closes the diagnostic runtime obligation by proving that
`aoa-diagnose` can write a complete runtime diagnosis packet while staying
read-only and subordinate to repair governance.

It is not free self-repair, not runtime quest authority, and not a live-health
success claim.

## Packet Surface

Run from the source checkout against a synthetic or operator-selected runtime
root:

```bash
AOA_STACK_ROOT=/tmp/<runtime> AOA_CONFIGS_ROOT=/tmp/<runtime>/Configs scripts/aoa-install-layout
AOA_STACK_ROOT=/tmp/<runtime> AOA_CONFIGS_ROOT=/tmp/<runtime>/Configs scripts/aoa-sync-configs --delete
AOA_SOURCE_ROOT=$(pwd) AOA_STACK_ROOT=/tmp/<runtime> AOA_CONFIGS_ROOT=/tmp/<runtime>/Configs \
  scripts/aoa-diagnose --profile substrate --truth-goal deployed --write-latest
```

The packet writes:

- `Logs/diagnostics/latest/diagnostic_target.json`
- `Logs/diagnostics/latest/diagnostic_session.json`
- `Logs/diagnostics/latest/diagnosis_companion.json`
- `Logs/diagnostics/latest/repair_handoff.json`
- `Logs/diagnostics/records/<diagnostic-id>/diagnostic_target.json`
- `Logs/diagnostics/records/<diagnostic-id>/diagnostic_session.json`
- `Logs/diagnostics/records/<diagnostic-id>/diagnosis_companion.json`
- `Logs/diagnostics/records/<diagnostic-id>/repair_handoff.json`

## 2026-05-13 Verdict

The packet wrote all diagnostic latest and record artifacts in a synthetic
runtime root. The session truth status reported `source_authored=true` and
`deployed=true`; it did not claim `trial_proven` or `live_available`.

The run exited drifted with `repairable_under_governance`, with
`repair_handoff.json` marked `review_required` and blocked by
`reviewed_diagnosis_required`. That is the correct closeout for this source
quest: the diagnostic route emits evidence and a governed handoff candidate
without granting mutation authority.

## Stop-Lines

- `aoa-diagnose` remains descriptive and read-only
- repair remains a reviewed handoff, not a diagnostic side effect
- generated diagnostic artifacts are evidence, not stronger than source docs
- no runtime quest authority is created by diagnostic output
