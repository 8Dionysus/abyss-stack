# Codex Consumer Handoff

This route connects stack runtime evidence to the source-owned Codex
organ-fabric projection without transferring admission or live-configuration
authority into `abyss-stack`.

## Owner split

| Handoff fact | Issuing owner | Stack role |
| --- | --- | --- |
| registry admission | `aoa-sdk` | report the exact registry record and digest |
| expected server schema | `abyss-stack` runtime package | report endpoint schema digest and protocol |
| consumer-observed schema | `8Dionysus` consumer route plus operator observation | report the received evidence ref; never self-observe on the consumer's behalf |
| grounded runtime canary | `abyss-stack` | issue stack-local canary evidence bound to the exact contour |
| owner acceptance | organ owner | carry the owner-issued evidence and exact accepted source/package identity |
| rollback readiness | `abyss-stack` plus operator rollout | report stack rollback target; do not claim that consumer rollback was executed |
| Codex config apply and credentials | operator | no write or secret access |

The `RuntimeObservation` subject already carries the source, package, deploy,
process, endpoint, registry, consumer, proof, acceptance, canary, and rollback
links. This is the runtime handoff contract. Do not create a second,
stack-owned consumer manifest.

## Mapping to the consumer gate

For one exact organ and policy contour:

- `endpoint.server_schema_digest` identifies the server schema;
- one `consumers[]` entry must name the exact registration ref, record
  `registered=true`, and carry an equal `observed_schema_digest`;
- endpoint and consumer must share at least one exact protocol version;
- `registry.registry_state` and registry evidence link to the private
  `aoa-sdk` record;
- `canary` must be successful and grounded for the same selected route;
- `proof` must bind the same source, package, deploy, process, schema,
  consumer registration, and canary;
- `acceptance` must be issued by the named organ owner for the same source and
  package, after central proof;
- `rollback` must bind the exact last-known-good consumer registration and
  runtime target.

These fields are evidence inputs to the `8Dionysus` consumer projection. They
do not directly populate or edit its source manifest. Exact receipt refs enter
that manifest only through the reviewed cross-repository landing.

## Denied in this package

`abyss-stack-mcp` must not:

- edit user-global or project Codex configuration;
- issue or read Codex bearer-token values;
- infer registry admission from a running process or endpoint;
- issue consumer-schema evidence on behalf of Codex;
- manufacture central proof or owner acceptance;
- infer consumer-zero from an absent current observation;
- remove a suspended registration;
- restart or reload Codex;
- turn a prepared runtime plan into execution.

The candidate process may prepare a bounded runtime plan. It still has
`execution_authorized=false`.

## Fresh-client and suspension rule

A changed registration or tool schema requires a fresh Codex process unless an
exact supported reload receipt exists for the observed client version. The
post-change observation must be new evidence, not a reused pre-change catalog.

Suspension is two-sided:

1. `aoa-sdk` marks the registry record suspended;
2. the operator removes the live consumer registration only after
   consumer-zero and rollback evidence exist.

Stack runtime shutdown is neither step and cannot substitute for either.

## Verification boundary

The source validator checks that this route remains documented and that the
typed runtime example still validates. It does not inspect a live Codex
process, change config, provision credentials, start services, execute a
canary, or prove consumer-zero.
