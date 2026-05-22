# AoA Memo MCP Design

## Thesis

Memory should work from any place in OS Abyss without copying all memory into
every prompt or repository.

The stable form is a federation:

```text
local work -> repo/memo candidate -> aoa-memo-mcp access -> aoa-memo review -> generated recall/eval/KAG handoff
```

MCP is the access layer. It is intentionally weaker than authored memory
contracts and raw evidence.

## Contexts

`aoa-memo` owns durable reviewed memory.
`.aoa` owns raw session evidence and compaction-derived archive surfaces.
Local `memo/` ports own repo-local candidate intake and receipts.
`aoa-memo-mcp` owns just-in-time access, candidate helpers, and route prompts.

## Operation

An agent should be able to enter any pilot root and run a brief:

```text
aoa_memo_brief(repo, intent)
```

The brief returns:

- local port status;
- pending export counts and landed export counts;
- reviewed corpus memory hits from `aoa-memo` read models;
- default memory operation mode;
- relevant central memory contracts;
- allowed next route;
- validation commands.

Candidate creation is local-first. A candidate may be written under the local
port, validated, and exported for reviewed intake. It does not become durable
memory just because the MCP tool wrote a file.

Local port indexing is also local-first. `PORT.yaml` is the local contract,
`INDEX.md` and `index.min.json` are generated read models, and MCP may rebuild
or validate them as access-plane helpers.

Reviewed intake is a three-step local route:

```text
candidate -> prepared export packet -> forwarding check receipt -> aoa-memo source patch
```

This MCP server owns the first three local packet steps. Each packet must stay
inside a known local `memo/` port and pass the corresponding
`aoa-memo/schemas/memory-ports/` schema. The final durable landing remains an
`aoa-memo` source change with validators and review.

The MCP can also list pending exports and prepare a landing plan. A landing plan
may run the `aoa-memo` dry-run command to show the target object bundle, copied
intake packet, and landing receipt. It does not write the durable object; the
write route stays in `aoa-memo`.

## Pilot Roots

The first pilot roots are:

- `Agents-of-Abyss/memo/`
- `~/src/abyss-stack/memo/`
- `/var/lib/abyss-machine/memo/`

`abyss-machine` uses `/var/lib/abyss-machine/memo/` for the writable host-local
port because `/etc/abyss-machine` is source-policy owned and root-controlled.
The host route card still owns the policy boundary.

## Readiness

The first layer is ready when:

- MCP resources/tools/prompts exist and are smoke-tested;
- each pilot port has `AGENTS.md`, `README.md`, and candidate directories;
- untrusted candidate material cannot validate as direct durable memory;
- another repo can obtain a memory brief through the access plane;
- landed reviewed memory can be returned from the `aoa-memo` corpus-backed
  read models through the same brief/object lookup route.
