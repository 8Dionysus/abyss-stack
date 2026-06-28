# aoa-kag-mcp Threat Model

## Assets

- Provider map and readiness matrix.
- Repo-local `kag/` records.
- Source-return route handles.
- Local filesystem roots named by the provider map.

## Risks

- Treating MCP output as source authority.
- Reading outside declared provider roots through crafted resource URIs.
- Hiding stale provider-map state behind successful MCP responses.
- Adding write, indexing, embedding, or graph-build actions to the access plane.

## Controls

- Resource URI parsing accepts only the known `aoa-kag://` shapes.
- Provider names and record classes are looked up from the provider map.
- Tools report source-return and freshness handles instead of mutating sources.
- Validation checks the package shape, provider-map readability, and server
  build path.
