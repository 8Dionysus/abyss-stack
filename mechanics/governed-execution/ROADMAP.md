# Governed Execution Roadmap

## Current route

- keep governed-runner behavior reviewable and schema-backed
- keep autonomy status as a runtime readout
- keep return policy config, examples, and schemas package-local
- keep candidate exports as handoff artifacts for owner review
- keep the Agent OS adapter limited to the three exact proven contours:
  governed `bounded_change_safe`, read-only reviewed A2A return, and
  degradation pause/restore/resume

## Next candidates

- split large governed-runner internals only when the tests can stay tight
- add a package-level candidate export index if exported families multiply
- add stronger invariant tests for return policy if recurrence behavior grows
- widen Agent OS scenarios only after a new owner contour, explicit execution
  lane, runtime phase map, failure matrix, and paired SDK/runtime proof exist

## Stop-lines

- do not bypass operator intent, review records, or owner handoffs
- do not treat exported candidates as accepted owner truth
- do not treat local-worker execution as permission to mutate sibling repos
  without the owning workflow
- do not restore the retired `aoa-routing` predecessor as a governed mutation
  target
- do not treat runtime completion as eval, memory, or final closeout authority
