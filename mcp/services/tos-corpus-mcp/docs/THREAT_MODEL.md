# ToS Corpus MCP Threat Model

## Protected Boundary

The protected boundary is the distinction between ToS-owned corpus authority and
stack-owned access behavior.

## Main Risks

- Treating an MCP packet as stronger than the ToS source index.
- Serving stale runtime projections without showing the source index path.
- Adding writeback without ToS validators and explicit operator review.
- Letting UI labels or runtime convenience fields rewrite ToS topology.
- Letting anonymous local HTTP callers read corpus/runtime projection state.
- Reusing a shared bearer so possession for one organ authenticates to ToS.
- Treating a provisioned secret or source-only unit compatibility as proof of
  live ToS admission.

## Mitigations

- Every packet includes authority and runtime-boundary notes from the index.
- The service reads from the ToS index instead of constructing hidden runtime
  meaning.
- The validation script requires real counts, graph views, and server build.
- No write tools are registered.
- Every tool publishes the closed-world read-only safety contract, and the
  validator checks the observed inventory.
- Optional loopback HTTP requires the ToS-specific read bearer, scope, and
  client identity before MCP dispatch; stdio remains the portable default.
- The filesystem-read-only owner unit is the target contour, while the service
  remains outside the bundle until its workspace wrapper and live canary
  exist.
