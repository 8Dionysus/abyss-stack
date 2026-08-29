# Tasks compatibility matrix

The machine-readable source is
`../tasks-compatibility-matrix.v1.json`. It distinguishes published releases,
current source, upstream self-tests, and an actual strict Abyss wire pair. None
of those evidence levels substitutes for another.

## Current decision

- OS Abyss Codex `0.147.0-abyss.2` is the bounded production consumer. Its
  exact production pair with `abyss-stack-mcp` advertises the extension and
  passes task creation, completed retrieval, cancellation acknowledgement,
  cancelled retrieval, auth/owner binding, observe-only output, and
  missing-extension denial.
- Codex `0.147.0` remains Tasks-ineligible because its real request does not
  advertise `io.modelcontextprotocol/tasks`; this row represents the upstream
  fallback, not the OS Abyss derivative.
- Released `rmcp 3.1.2` is the current isolated reference client. It passed
  modern discovery, task creation, `tasks/get`, required routing headers,
  per-request capability, durable owner result retrieval, and unknown-task
  denial against the feature-gated Abyss adapter.
- Inspector `2.1.0` passes its own 11-test modern Tasks suite, but is blocked
  against the strict Abyss adapter: its raw `tasks/get` sends `Mcp-Method` and
  the extension envelope but omits required `Mcp-Name=taskId`. The adapter
  correctly returns `-32020` / HTTP `400`.
- Python `2.1.1` (the current source candidate), TypeScript `2.0.0`, and Go
  `1.7.0` do not provide a released modern Tasks implementation. TypeScript
  explicitly excludes the extension;
  Inspector works around that exclusion locally.
- C# `2.1.0` has the most complete released source/test surface, including the
  task routing header, but no local .NET runtime was available for an Abyss
  pair. It remains source-supported but unpaired here.
- `ext-tasks` is reference schema/source, not a released runtime.

## Consequence for OS Abyss

The `abyss-stack` read adapter enables Tasks explicitly; other organ adapters
do not inherit it. The TaskStore remains protocol-independent and owner-bound.
`rmcp` remains a replaceable reference witness, not a new owner and not a
reason to migrate organ authority into Rust. Core-read MCP migration and Tasks
admission remain independently derived. The Tasks production receipt is
deployment-bound to the historical MCP `2.0.0` runtime and is not re-admitted
for the source candidate until its pair is refreshed.

Production Tasks is true only for the proved bounded lifecycle. Update and
input-required remain source-present but live-unpaired. Notifications remain
excluded until an extension-filtered `subscriptions/listen` path is proven end
to end, and distributed poll enforcement requires its own evidence. Those
limits do not erase the useful create/get/cancel production capability.
