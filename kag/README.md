# abyss-stack Local KAG Provider

`kag/` exposes portable records and repository indexes for the `abyss-stack`
source checkout.

## Operating Card

| Field | Route |
| --- | --- |
| role | local KAG provider for runtime source topology, mechanics, and MCP access planes |
| records | `nodes/`, `edges/`, `indexes/`, `projections/`, `receipts/` |
| manifest | `manifest.json` |
| source route | `README.md`, `DESIGN.md`, `mechanics/README.md`, `stats/README.md`, and `mcp/README.md` |
| consumer route | `aoa-kag` registry/composition, `aoa-kag-mcp`, runtime services |
| owner return | `README.md` |

## Record Classes

| Class | Current record |
| --- | --- |
| node | runtime source home and MCP access-plane route |
| edge | runtime source returns to its owner route |
| index | content-addressed repository source shards plus exact derived views |
| projection | MCP-readable source-return packet |
| receipt | validation receipt for the current owner route |

Git holds public source records, `indexes/index_family.manifest.json`, and
bounded content-addressed JSONL shards. The canonical source, anchor, and event
records can deterministically assemble the exact legacy seven-index view for
dual-read consumers; the monolithic derived files are not tracked. Live runtime
state remains in the deployed roots owned by `abyss-stack`.
