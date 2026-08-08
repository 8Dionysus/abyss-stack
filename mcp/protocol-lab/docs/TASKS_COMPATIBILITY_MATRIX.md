# Tasks compatibility matrix

The machine-readable source is
`../tasks-compatibility-matrix.v1.json`. It distinguishes published releases,
current source, upstream self-tests, and an actual strict Abyss wire pair. None
of those evidence levels substitutes for another.

## Current decision

- Codex `0.147.0` remains Tasks-ineligible because its real request does not
  advertise `io.modelcontextprotocol/tasks`.
- Released `rmcp 3.1.2` is the current isolated reference client. It passed
  modern discovery, task creation, `tasks/get`, required routing headers,
  per-request capability, durable owner result retrieval, and unknown-task
  denial against the feature-gated Abyss adapter.
- Inspector `2.1.0` passes its own 11-test modern Tasks suite, but is blocked
  against the strict Abyss adapter: its raw `tasks/get` sends `Mcp-Method` and
  the extension envelope but omits required `Mcp-Name=taskId`. The adapter
  correctly returns `-32020` / HTTP `400`.
- Python `2.0.0`, TypeScript `2.0.0`, and Go `1.7.0` do not provide a released
  modern Tasks implementation. TypeScript explicitly excludes the extension;
  Inspector works around that exclusion locally.
- C# `2.1.0` has the most complete released source/test surface, including the
  task routing header, but no local .NET runtime was available for an Abyss
  pair. It remains source-supported but unpaired here.
- `ext-tasks` is reference schema/source, not a released runtime.

## Consequence for OS Abyss

The Abyss adapter stays disabled by default and the TaskStore remains
protocol-independent. `rmcp` is a replaceable lab witness, not a new owner and
not a reason to migrate organ authority into Rust. Core-read MCP 2026-07-28
migration remains independent from Tasks.

Production Tasks stays false until the exact production consumer advertises
the extension on every request and the same pair proves create/get/update,
cancellation, input, TTL cleanup, restart recovery, auth negatives, bounded
payloads, and rollback. Notifications remain excluded until an
extension-filtered `subscriptions/listen` path is proven end to end.
