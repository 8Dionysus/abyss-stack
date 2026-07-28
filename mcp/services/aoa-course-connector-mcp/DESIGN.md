# Design

`aoa-course-connector` already owns an MCP API. This package does not reimplement
its retrieval logic: it calls the owner dispatcher with owner-rooted storage,
publishes a finite read allowlist, forces source refs off, and rejects any owner
result reporting network access.
