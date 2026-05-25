# MCP Services

`mcp/services/` contains runnable stack-owned MCP service packages.

Use this district for service packages with their own source, tests, local
route card, and validation path.

| Service | Use for |
|---|---|
| [`aoa-memo-mcp`](aoa-memo-mcp/README.md) | memory briefs, local memo port status, candidate creation and validation, session rehydration pointers |
| [`aoa-evals-mcp`](aoa-evals-mcp/README.md) | bounded eval selection, bundle inspection, comparison readers, runtime evidence templates, candidate-only report skeletons |
| [`abyss-machine-mcp`](abyss-machine-mcp/README.md) | compact owner-aware machine brief, host evidence map, resource/memory/typing/nervous read models, non-mutating route preflight |

For district law, read [AGENTS](AGENTS.md). For the parent access-plane route,
read [mcp/AGENTS](../AGENTS.md).
