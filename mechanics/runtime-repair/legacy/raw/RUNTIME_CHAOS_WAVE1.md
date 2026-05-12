# Runtime Chaos Wave 1

This note maps the first bounded chaos and stress families that fit the current
`abyss-stack` runtime receipt contracts.

It does not introduce live fault injection, gateway-local harnesses, or hidden
runtime judge behavior.

## Receipt families used here

Wave 1 stays inside the existing runtime-owned receipt schemas:

- `service_degradation_receipt_v1`
- `repair_safe_closeout_receipt_v1`

## First three chaos families

### timeout chaos

A bounded service path exhausts its time budget.

Expected posture:

- degraded remains explicit
- operator visibility stays on
- unrelated services do not restart
- later evidence may travel upward only as a candidate sidecar

### honest degradation chaos

A service continues in a weaker mode.

Expected posture:

- `mode_after` says what changed
- `degraded` is explicit
- blocked action families stay blocked
- routing or playbook consumers may read the receipt later

### retrieval outage honesty

A downstream derived or retrieval-bearing surface is unhealthy.

Expected posture:

- no fake "success"
- no invented derived continuity
- route shifts to source-first or held posture
- KAG quarantine or regrounding may own the next hop

## Wave-1 integration note

Do not overbuild this inside `abyss-stack`.

Use receipt examples and bounded doc guidance first.
Actual injection harnesses and agent-runtime child-run semantics belong later in
`ATM10-Agent`, not in this wave.

## Export boundary

Runtime may prepare:

- runtime evidence-selection candidates
- artifact-hook candidates

Runtime may not:

- compute verdicts
- publish bundle truth
- promote itself into `aoa-evals`
