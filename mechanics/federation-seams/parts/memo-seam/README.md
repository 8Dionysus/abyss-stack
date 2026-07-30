# Memo Seam

Routes `docs/MEMO_RUNTIME_SEAM.md`.

Memo meaning stays owned by `aoa-memo`; abyss-stack owns only the runtime
adapter and candidate export posture.

This part also owns C20 `RuntimeDeliveryReceipt`, the content-minimized
runtime-side record for an `attempted`, `delivered`, `suppressed`, `expired`,
or `failed` delivery. Its source surfaces are:

- `schemas/active-organ-runtime-delivery-receipt.schema.json`
- `examples/active_organ_runtime_delivery_receipt.*.example.json`
- `examples/active_organ_runtime_delivery_receipt.negative-examples.json`
- `tests/test_active_organ_runtime_delivery_receipt.py`
- `examples/codex_owner_orientation_runtime_compatibility_pin_v0.json`
- `examples/codex_owner_orientation_shadow_runtime_compatibility_pin_v0.json`
- `examples/codex_owner_orientation_canary_runtime_compatibility_pin_v0.json`
- `schemas/active-organ-canary-runtime-receipt.schema.json`
- `schemas/active-organ-runtime-erasure-owner-extension-v0.schema.json`
- `tests/test_active_organ_runtime_erasure.py`
- `schemas/active-organ-agent-local-runtime-namespace-v0.schema.json`
- `tests/test_active_organ_agent_local_runtime_namespace.py`
- `mcp/services/aoa-memo-mcp` read-only
`aoa_memo_owner_orientation` delivery adapter and tests

The separate `active-organ-shadow-runtime-receipt` records consumer-invisible
packet construction. It cannot attempt delivery, return a memory payload,
persist content or candidates, rerank, reselect, or widen semantic/policy
authority.

The canary receipt is a third, distinct C20 shape. It can record one
operator-approved, source-visible, non-directive observation or an explicit
holdout, silence, kill-switch, expiry, host denial, or runtime rate-limit
result. Its durable surface is refs-only: the observation text is returned
in-process to the source-local harness but is never copied into the receipt.
The canary adapter is not exposed as an MCP tool or deployed hook.

The receipt carries exact refs and binding state only. It never stores packet,
prompt, or memory content, never grants effect authority, and never becomes
memory truth.

For `codex_owner_orientation_v0`, the adapter accepts one exact SDK plan plus
one memo-authored C08/C09 bundle. It returns the already-selected content to
the explicit caller and emits C20 in the same response. Reranking,
reselection, persistence, retry without readmission, memory semantics, and
effects remain forbidden. `off`, `fresh-start`, policy silence, expiry, and
rollback return no memory payload.

For `codex_owner_orientation_canary_v0`, the source-local adapter additionally
requires the exact shadow plan and bundle, SDK canary release, memo canary
bundle, machine canary admission, eval-owned assignment/counterfactual, and
stats-owned outcome refs. Runtime receipt history independently enforces one
delivery per exact policy window. Any count drift, schema drift, consumer
drift, unavailable gate, or authority widening resolves to no output or
rejection.

The ER4/ER5 owner extension is separate from C20 delivery. ER4 covers runtime
stores, caches, and nervous indexes; ER5 covers exports and backup/restore
descendants. Each extension is refs- and digest-only, requires restore/recovery
checking, forbids project- and host-root mutation, and reports only the
stack-owned result into an `aoa-memo` C14-C17 manifest. It grants no live
deletion, host erasure, memory semantics, model unlearning, deployment, or
global completion authority.

The Phase 12 runtime namespace contract is separately pinned by exact SDK
plan, `aoa-agents` namespace contract, agent, tenant, and generation. It
bounds object count, bytes, and write amplification; makes expiry and rollback
namespace-local; and permits only reviewed nomination to `aoa-memo`.
`isolated` disables the local namespace without disabling shared reviewed
recall. `consumer_zero` requires no remaining local reads, writes, promotions,
or material. This source-local contract performs no live execution.
