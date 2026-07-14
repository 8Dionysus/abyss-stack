# aoa-stats-mcp

`aoa-stats-mcp` is the stack-owned read-only access plane for the federated
OS Abyss stats system.

It reads the public surfaces owned by `aoa-stats` and the root `stats/` ports
named by the canonical owner inventory. It does not define measurements,
attest evidence, infer freshness, execute validators, or make decisions.

## Tools

| Tool | Access |
|---|---|
| `stats_catalog` | Read the active derived-surface catalog, preferring an owner-produced live materialization when present. |
| `stats_surface_read` | Read one catalog-listed derived surface with explicit live/reference and freshness posture. |
| `stats_boundary_rules` | Read compact source-owner references and authority ceilings without copying full owner documents. |
| `stats_owner_port_read` | List the canonical federation inventory or inspect one owner-local port and optional measurement. |
| `stats_packet_check` | Pass one contract and packet to the public `aoa-stats` compatibility reader and return its result unchanged. |

The former repo-local `stats_source_registry` tool is intentionally absent.
The old receipt-source registry is an intake implementation surface, not the
federated owner inventory.

## Transport

Stdio remains the portable default. Authenticated loopback Streamable HTTP
uses the common stack MCP transport contract. This service does not introduce
remote exposure or a shared cross-owner gateway.

## Authority

Returned definitions and evidence references remain owner-local truth. Derived
surface payloads remain weaker than their inputs. Packet checks establish
compatibility only; they do not establish truth, freshness, proof, or
permission to act.

Operational validation lives in [AGENTS.md](AGENTS.md). The parent service
catalog owns the runtime route.
