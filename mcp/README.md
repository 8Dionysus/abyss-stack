# MCP

`mcp/` contains stack-owned Model Context Protocol access planes.

Use this district when an agent needs a live, addressable route into OS Abyss
context without copying owner-layer memory, runtime evidence, or generated
read models into every prompt.

## Districts

| District | Use for |
|---|---|
| [`services/`](services/README.md) | runnable MCP service packages with package-local source, tests, and route cards |

MCP packages are access planes. Their outputs help agents move, but authority
stays with the source owner named by the package.

`aoa-decisions-mcp` is the access plane for the local workspace decision graph:
it auto-refreshes the ignored graph cache before returning search results,
repo slices, decision neighborhoods, or compact packets.

`tos-corpus-mcp` is the access plane for the Tree of Sophia whole-corpus index
and philosophy graph projection: it reads ToS-owned derived resources and
returns graph-review packets without making `abyss-stack` the owner of ToS
meaning.

`aoa-stats-mcp` is the access plane for the federated stats system: it reads
the `aoa-stats` public contracts and inventory plus owner-local root `stats/`
ports without moving statistical or domain meaning into the runtime adapter.
