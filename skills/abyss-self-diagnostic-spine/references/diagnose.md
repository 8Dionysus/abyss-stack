# Diagnose one Abyss runtime target

## Preflight

Resolve the canonical owner root. If it was supplied or returned by the
installed source receipt, do not rediscover it through the workspace, sibling
repositories, Git history, or directory contents.

Honor owner route guidance already supplied by the host. For a routine
read-only diagnosis, do not pre-read mechanic editing cards. If a required
owner path or boundary is ambiguous, read only:

- `mechanics/diagnostic-spine/AGENTS.md`;
- `mechanics/diagnostic-spine/README.md`.

Use
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json`
as validator input. Do not print the full schema into model context. Validate
the exact packet programmatically. The validator must output only validity,
error paths/messages, and explicitly requested fields; never echo the full
packet or schema. Inspect only a validation error or a specific field
definition when needed.

Make the first packet read the validation operation itself. Use an existing
owner validator or one inline interpreter invocation that validates the schema
and emits only the bounded fields needed for review. Do not pre-read the packet
with `jq`, `sed`, or another broad field dump. Do not use a heredoc, create a
temporary script, transform the packet, or create a validation fixture. After
successful validation, run a second targeted read only when one explicitly
named field was not included in the bounded validator output.

For repeated arrays such as drifts or evidence refs, never emit the complete
array when it contains more than eight entries. Emit the count, sorted unique
kind/severity/owner classifications, and reference count. When one requested
claim needs examples, emit at most three matching entries plus the omitted
count. `actual_effects`, `skipped_checks`, `handoff`, and `claim_limit` belong
to the returned review result. They are not required packet fields, and their
absence from a valid packet must not trigger schema search or wider packet
reads.

Do not pre-read the owner doctrine document for routine `observe` or `capture`;
this procedure and the owner CLI are sufficient. For `review`, do not read
sibling examples, runtime-repair material, catalogs, generated surfaces, or
unrelated root docs unless the packet and schema leave one field meaning
unresolved. For any unresolved field or owner boundary, read only the relevant
section of
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`
and name the ambiguity it resolved.

Record:

- exactly one operation: `observe`, `capture`, or `review`;
- one concrete preset/profile target or exact packet path;
- `truth_goal`: `deployed`, `trial_proven`, or `live_available`;
- whether current observation is required or an existing packet may be reused;
- read-only or exact write authority;
- optional bounded `against`, reviewed-session, or reviewed-diagnosis refs.

Stop before target reads when any operation-required input is absent.

## Review an existing packet

1. Read only the supplied packet and validate it against the exact owner schema.
2. Confirm `schema_version=diagnostic_session_v1` and required fields.
3. Compare capture time, target, selectors, truth goal, and evidence refs with
   the request.
4. Mark it `fresh`, `stale`, or `freshness_unknown`; do not silently probe.
5. Review per-axis states, truth-status flags, drift classes, unknowns, exit
   class, and evidence refs.

The supplied packet is the only observation target for this branch. If current
evidence is required and the packet is not fresh enough, stop with
`blocked_current_observation_required` unless `observe` is separately
authorized.

## Observe current state

Build one owner command from the exact request:

```text
scripts/aoa-diagnose <one preset/profile selection> --truth-goal <goal>
```

Add `--against`, `--with-session-ref`, or
`--with-reviewed-diagnosis-ref` only when the exact ref was supplied. Do not
add a write flag.

Run the command once from the canonical owner root. Exit codes `0`, `1`, and
`2` express diagnostic exit classes; they are not by themselves tool failure.
Require JSON stdout with `schema_version=diagnostic_session_v1`, the requested
selector, target, axes, truth status, drift, exit, and public-safe fields.
Report this as `owner_cli_shape_checked`, not independent full-schema
validation.

Run the owner CLI as a standalone command. Do not wrap, pipe, redirect, or
capture it in shell substitution. If the host returns a running exec handle,
poll that handle until terminal result or owner timeout. Do not start a second
command or infer failure from initially empty stdout.

If the host returns neither stdout nor an exit code, report an attempted effect
and `blocked_tool_host`; do not claim that an observation ran.

## Capture an owner artifact

Use the same one-command route, adding only the exact requested owner write:

- `--write <path>` for one named packet;
- `--write-latest` for the owner latest and record bundle;
- `--write-last-good-ref` only with `--write-latest` and an eligible green pass;
- `--write-reviewed-diagnosis-ref` only with `--write-latest` and an eligible
  drifted pass.

Do not infer latest refresh or promotion from a request to diagnose. Record
every written path and compare it with the requested effect. For a named
destination, inspect only that path after the original command terminates.

## Review and hand off

1. Preserve mixed axis states; never flatten one axis into a whole-system
   claim.
2. Preserve `source_authored`, `deployed`, `trial_proven`, and
   `live_available` separately.
3. Ground drift, probable cause, confidence, and freshness in packet fields or
   current owner sources; keep unknowns explicit.
4. Compare with last-good only when its target and time remain relevant.
5. Select one bounded next route:
   - no handoff when the target runs as intended;
   - reviewed diagnosis or retest when evidence remains incomplete;
   - `aoa-session-recovery` repair only after an explicit repair-fit handoff;
   - the named owner when the gap crosses repository authority;
   - manual regrounding when no bounded owner route exists.
6. Report claim limit and actual effects.

Stop after this review. Do not execute the handoff, mutate runtime state,
refresh unrelated evidence, or convert a candidate into approval.
