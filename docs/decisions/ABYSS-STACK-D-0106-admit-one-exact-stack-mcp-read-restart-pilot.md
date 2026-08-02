# Admit One Exact Stack MCP Read Restart Pilot

- Decision ID: ABYSS-STACK-D-0106
- Status: accepted
- Date: 2026-08-02
- Owner surface: `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/effect.py`

## Index Metadata

- Original date: 2026-08-02
- Surface classes: MCP access plane, internal runtime effect, owner contract
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: exact target, explicit approval, credential isolation, canary, mandatory rollback
- Posture: accepted bounded internal-effect pilot

## Context

The stack MCP read and candidate contours can prove runtime state and prepare a
content-addressed restart candidate, but neither contour may execute it. OS
Abyss needs one real, low-risk runtime-effect proof without creating a generic
lifecycle executor, allowing read discovery to imply effect authority, or
granting the stack authority over sibling owner tools.

The selected target is the user-level `abyss-stack-mcp-read.service`. It is
loopback-only, has an existing authenticated canary, can be restarted without
source mutation or external network effects, and can be restored through a
second exact restart followed by the same bounded health proof.

## Options considered

- Keep all restart execution operator-only and outside the organ access fabric.
- Add a generic lifecycle or shell executor parameterized by unit and command.
- Add one separately credentialed process containing one exact approved
  restart-and-rollback primitive for `abyss-stack-mcp-read.service`.

## Decision

Choose the one-primitive separate process.

The `internal_effect` contour has its own bearer, scope, loopback port `5439`,
systemd unit, runtime root, and process entry point. It exposes only
`stack_execute_approved_read_restart_pilot`. The primitive accepts only the IDs
of an already staged content-addressed restart candidate and an explicit,
expiring approval plus their bound idempotency key.

The executor revalidates the current observation digest, source, package,
deploy, exact unit, and systemd process identity before writing a pre-effect
receipt. It can invoke only `/usr/bin/systemctl --user restart
abyss-stack-mcp-read.service`. After the first restart it runs an authenticated
read canary, always performs a second restart as the pilot restoration action,
and runs a post-rollback canary. Pre-effect denials and post-attempt recovery
states are persisted as secret-free receipts. No external effect, source
mutation, arbitrary unit, arbitrary action, or generic shell is represented.

The owner capability manifest records the primitive identity but continues to
set `effect_activation_authorized=false`: source presence is not a live
approval, admission, or execution transaction. A live call still requires the
separate effect credential, exact plan, explicit approval, fresh runtime
binding, and runtime deployment proof.

## Rationale

A separate one-tool process makes the blast radius structural rather than
prompt-dependent. Reusing the candidate process would let a non-executing
credential cross an authority boundary; a generic unit or command parameter
would turn a bounded proof into a permanent confused deputy. The forced second
transition makes rollback execution observable instead of treating a written
rollback route as proof.

Keeping approval and plan artifacts content-addressed, private, expiring, and
revalidated against the live observation prevents an older catalog or approval
from authorizing a changed process. Process isolation gives timeout and caller
cancellation a boundary outside the effect executor while allowing the worker
to finish its mandatory restoration sequence.

## Consequences

- Positive: OS Abyss can prove one real internal runtime effect with exact
  approval, canary, rollback execution, and post-rollback health.
- Positive: read and candidate credentials cannot authenticate to the effect
  process, and the effect credential cannot select another tool or target.
- Positive: denied requests and incomplete recovery become durable audit
  evidence instead of disappearing behind an MCP error.
- Tradeoff: the pilot deliberately performs two read-service restarts and is
  unsuitable for services without a restart-safe restoration contour.
- Tradeoff: any broader effect requires a new owner decision, threat model,
  credential contour, proof bundle, and rollback contract; this primitive must
  not be generalized in place.
- Claim limit: this decision accepts the source contract only. It does not prove
  deployed parity, live effect admission, successful execution, benefit, or a
  healthy post-rollback process until the corresponding receipts and canaries
  exist.

## Source surfaces

- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/effect.py`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/effect_server.py`
- `mcp/services/abyss-stack-mcp/organ-access.v1.json`
- `mcp/services/abyss-stack-mcp/docs/THREAT_MODEL.md`
- `systemd/user/abyss-stack-mcp-internal-effect.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `mcp/services/abyss-stack-mcp/tests/test_effect.py`

## Follow-up route

Land and deploy the exact source, provision the third credential and private
effect root, then create a fresh admitted read observation, candidate, approval,
and live pilot receipt. Refresh the observation after restoration and prove
source/deploy parity plus authenticated read health. Any request for another
unit, action, external effect, or continuing applied state returns to the stack
owner as a new decision rather than extending this primitive.
