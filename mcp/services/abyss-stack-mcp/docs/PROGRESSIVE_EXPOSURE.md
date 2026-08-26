# Progressive exposure runtime contour

`exposure.py` is the stack-side adapter for the SDK's
`aoa_organ_exposure_plan_v1` candidate. It is deliberately separate from the
normal read and candidate MCP server registrations until baseline admission
and a later owner decision authorize a live route.

The adapter performs three bounded operations:

1. normalize the owner-qualified capability and exact rendered snapshot;
2. materialize only an unexpired candidate when the local feature flag and an
   explicit baseline-admission receipt are both present; and
3. invoke only a visible read/derive/validate tool when a separate caller
   authorization reference is supplied.

Every operation emits a content-addressed receipt. Receipts record visible
tool IDs, bytes, and token posture, plus denial reasons and the exact plan or
materialization identity. `activation_authorized`, `execution_authorized`, and
`runtime_effect_authorized` remain fixed false. The receipt sink is an
explicit caller-owned persistence seam; this module does not create a hidden
journal or mutate registry state.

The default `ExposureRuntime()` is disabled and baseline-denied. A green local
test proves only normalization, fail-closed gating, and receipt shape. It does
not prove a live MCP endpoint, admission, owner acceptance, central proof, or
economic effect.
