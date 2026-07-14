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

## Mitigations

- Every packet includes authority and runtime-boundary notes from the index.
- The service reads from the ToS index instead of constructing hidden runtime
  meaning.
- The validation script requires real counts, graph views, and server build.
- No write tools are registered.
- Optional loopback HTTP requires the source-owned bearer credential before
  MCP dispatch; stdio remains the portable default.
